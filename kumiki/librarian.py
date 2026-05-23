"""
Librarian: discovery and loading of kumiki frame examples and pattern books.

Discovery is **AST-driven** (see :mod:`kumiki.librarian_analysis`); the regex
prefilter has been removed.  Files are only imported when their runtime objects
are needed:

* Patternbook files are imported during scan so we can enumerate their pattern
  and group names.
* Frame files are *not* imported during a scan — the analyzer reports only the
  filename plus a chosen entry name (the **last** module-level frame value or
  frame-returning function in source order).  Frame loading is the runner's
  job and happens on demand.

The legacy ``LibrarianModuleRecord`` / ``LibrarianScanResult`` shape is
preserved for backward compatibility (notably ``scan_result.examples`` is still
populated when ``load_frame_examples=True``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import importlib.util
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

from .librarian_analysis import ModuleStaticInfo, analyze_file
from .patternbook import PatternBook


_DYNAMIC_MODULE_PREFIX = "giraffe_librarian_dynamic"


@dataclass
class LibrarianModuleRecord:
    relative_path: str
    module_name: str
    patternbook: Optional[PatternBook] = None
    example: Optional[Any] = None
    warnings: List[str] = field(default_factory=list)
    load_error: Optional[str] = None
    load_error_traceback: Optional[str] = None
    static_info: Optional[ModuleStaticInfo] = None
    content_sha256: Optional[str] = None


@dataclass
class LibrarianScanResult:
    root_folder: str
    modules: List[LibrarianModuleRecord] = field(default_factory=list)

    @property
    def errors(self) -> List[str]:
        return [
            f"{module.relative_path}: {module.load_error}"
            for module in self.modules
            if module.load_error is not None
        ]

    @property
    def pattern_books(self) -> List[PatternBook]:
        return [
            module.patternbook
            for module in self.modules
            if module.patternbook is not None
        ]

    @property
    def examples(self) -> Dict[str, Any]:
        return {
            module.relative_path: module.example
            for module in self.modules
            if module.example is not None
        }


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


_DEFAULT_SKIP_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".nox", ".eggs", ".idea", ".vscode", ".vscode-test",
    "oldcrap",
})

_DEFAULT_SKIP_PATH_SEGMENTS = (
    "site-packages", "htmlcov", "coverage", "step_test_output",
)

# Well-known third-party Python package directory names.  Any subdirectory
# with one of these names is treated as a vendored dependency and never
# scanned — kumiki's own deps (sympy, numpy, trimesh, manifold3d) plus other
# popular scientific packages.  This prevents vendored copies (e.g.
# ``fusion360/libs/numpy/``) from being walked.  Users can extend via
# ``.kigumi/config.json`` if they have a directory legitimately named after
# one of these packages.
_KNOWN_THIRD_PARTY_PACKAGE_DIRS = frozenset({
    # kumiki runtime deps
    "sympy", "numpy", "trimesh", "manifold3d",
    # common scientific / utility deps that often get vendored
    "mpmath", "scipy", "pandas", "matplotlib", "sklearn", "scikit_learn",
    "networkx", "shapely", "rtree", "pillow", "PIL",
    "cython", "Cython",
    # testing / packaging machinery that sometimes ends up vendored
    "pytest", "_pytest", "iniconfig", "pluggy", "exceptiongroup",
    "setuptools", "pkg_resources", "_distutils_hack", "wheel",
    "coverage", "tomli", "packaging",
})


def _load_workspace_skip_extras(root_folder: Path) -> Tuple[frozenset[str], Tuple[str, ...]]:
    """Read additional skip-dir names/path-segments from ``.kigumi/config.json``.

    Supported keys (both optional):
      * ``scan_skip_dirs``: list of directory names to skip (matched against
        ``Path.name``).
      * ``scan_skip_path_segments``: list of strings; a directory is skipped
        if any segment appears anywhere in its absolute path parts.
    """
    config_path = root_folder / ".kigumi" / "config.json"
    if not config_path.exists():
        return frozenset(), ()
    try:
        import json as _json
        data = _json.loads(config_path.read_text())
    except (OSError, ValueError):
        return frozenset(), ()
    if not isinstance(data, dict):
        return frozenset(), ()
    names = data.get("scan_skip_dirs") or []
    segs = data.get("scan_skip_path_segments") or []
    name_set = frozenset(str(n) for n in names if isinstance(n, str))
    seg_tuple = tuple(str(s) for s in segs if isinstance(s, str))
    return name_set, seg_tuple


def _should_skip_dir(
    name: str,
    full_path: Path,
    *,
    extra_names: frozenset[str] = frozenset(),
    extra_segments: Tuple[str, ...] = (),
) -> bool:
    if not name:
        return True
    if name in _DEFAULT_SKIP_DIR_NAMES or name in extra_names:
        return True
    if name in _KNOWN_THIRD_PARTY_PACKAGE_DIRS:
        return True
    if name.endswith(".egg-info") or name.endswith(".dist-info"):
        return True
    parts = full_path.parts
    if any(seg in parts for seg in _DEFAULT_SKIP_PATH_SEGMENTS):
        return True
    if extra_segments and any(seg in parts for seg in extra_segments):
        return True
    return False


def _discover_python_files(root_folder: Path) -> List[Path]:
    extra_names, extra_segments = _load_workspace_skip_extras(root_folder)
    python_files: List[Path] = []
    stack: List[Path] = [root_folder]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except (OSError, PermissionError):
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    if not _should_skip_dir(
                        entry.name,
                        entry,
                        extra_names=extra_names,
                        extra_segments=extra_segments,
                    ):
                        stack.append(entry)
                    continue
                if not entry.is_file() or entry.suffix != ".py":
                    continue
                if entry.name == "__init__.py":
                    continue
                python_files.append(entry)
            except OSError:
                continue
    python_files.sort()
    return python_files


def _make_dynamic_module_name(root_folder: Path, file_path: Path) -> str:
    try:
        relative = file_path.relative_to(root_folder).with_suffix("")
    except ValueError:
        relative = Path(file_path.stem)
    flattened = "_".join(relative.parts) or file_path.stem
    return f"{_DYNAMIC_MODULE_PREFIX}_{flattened}"


def _file_sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_module_from_path(
    root_folder: Path, file_path: Path
) -> Tuple[Optional[Any], Optional[str], Optional[str], str]:
    module_name = _make_dynamic_module_name(root_folder, file_path)
    attempted_file = str(file_path)

    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return None, f"{attempted_file}: Could not create import spec", None, module_name

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
        return module, None, None, module_name
    except Exception as exc:
        if module_name in sys.modules:
            del sys.modules[module_name]
        tb = traceback.format_exc()
        return None, f"{attempted_file}: {type(exc).__name__}: {exc}", tb, module_name


def _resolve_patternbook(module: Any, warnings: List[str]) -> Optional[PatternBook]:
    if hasattr(module, "patternbook"):
        candidate = getattr(module, "patternbook")
        if isinstance(candidate, PatternBook):
            return candidate
        warnings.append(
            f"module.patternbook exists but is {type(candidate).__name__}, expected PatternBook"
        )

    factory_names = [
        name
        for name in dir(module)
        if name.startswith("create_") and name.endswith("_patternbook")
    ]

    for name in sorted(factory_names):
        factory = getattr(module, name)
        if not callable(factory):
            continue
        try:
            result = factory()
        except Exception as exc:
            warnings.append(f"{name}() failed: {type(exc).__name__}: {exc}")
            continue
        if isinstance(result, PatternBook):
            return result
        warnings.append(f"{name}() returned {type(result).__name__}, expected PatternBook")

    return None


def _resolve_example(module: Any) -> Optional[Any]:
    """Return the legacy module-level ``example`` attribute if present."""
    return getattr(module, "example", None)


# ---------------------------------------------------------------------------
# Per-file analysis (no imports)
# ---------------------------------------------------------------------------


def might_contain_kumiki_frame(file_path: str) -> bool:
    """Return True iff ``file_path`` has any module-level frame or patternbook
    entry detected by the AST analyzer."""
    info = analyze_file(file_path)
    return info.has_anything


# ---------------------------------------------------------------------------
# Scan API
# ---------------------------------------------------------------------------


def _scan_single_file(
    root: Path,
    file_path: Path,
    *,
    load_frame_examples: bool,
) -> LibrarianModuleRecord:
    try:
        relative_path = str(file_path.relative_to(root))
    except ValueError:
        relative_path = str(file_path)
    module_name = _make_dynamic_module_name(root, file_path)
    static_info = analyze_file(str(file_path))
    sha = _file_sha256(file_path)
    record = LibrarianModuleRecord(
        relative_path=relative_path,
        module_name=module_name,
        static_info=static_info,
        content_sha256=sha,
    )

    if not static_info.has_anything:
        return record

    needs_import = bool(static_info.patternbooks) or (
        load_frame_examples and bool(static_info.frames)
    )
    if not needs_import:
        return record

    module, load_error, load_error_traceback, real_module_name = _load_module_from_path(
        root, file_path
    )
    record.module_name = real_module_name
    record.load_error = load_error
    record.load_error_traceback = load_error_traceback

    if module is None:
        return record

    if static_info.patternbooks:
        record.patternbook = _resolve_patternbook(module, record.warnings)
    if load_frame_examples and static_info.frames:
        record.example = _resolve_example(module)
    return record


def scan_library_folder(
    folder_path: str,
    *,
    load_frame_examples: bool = False,
) -> LibrarianScanResult:
    """Scan *folder_path* recursively.

    By default frame files are not imported — only their static info is
    captured.  Pass ``load_frame_examples=True`` to import frame files and
    populate ``record.example`` (used by the FreeCAD example runner).
    """
    root_folder = Path(folder_path).resolve()
    if not root_folder.exists() or not root_folder.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")

    result = LibrarianScanResult(root_folder=str(root_folder))
    for file_path in _discover_python_files(root_folder):
        record = _scan_single_file(
            root_folder, file_path, load_frame_examples=load_frame_examples
        )
        result.modules.append(record)
    return result


def scan_specific_files(
    file_paths: List[str],
    root_folder: str,
    *,
    load_frame_examples: bool = False,
) -> LibrarianScanResult:
    root = Path(root_folder).resolve()
    result = LibrarianScanResult(root_folder=str(root))
    for fp_str in file_paths:
        file_path = Path(fp_str).resolve()
        record = _scan_single_file(
            root, file_path, load_frame_examples=load_frame_examples
        )
        result.modules.append(record)
    return result


# ---------------------------------------------------------------------------
# Index payload (JSON-friendly)
# ---------------------------------------------------------------------------


def _pattern_names_from_patternbook(patternbook: PatternBook) -> List[str]:
    try:
        return [pattern_name for pattern_name in patternbook.list_patterns()]
    except Exception:
        return []


def _group_names_from_patternbook(patternbook: PatternBook) -> List[str]:
    try:
        return [group_name for group_name in patternbook.list_groups()]
    except Exception:
        return []


def _frame_record_for_index(
    abs_path: str,
    rec: LibrarianModuleRecord,
) -> Dict[str, Any]:
    static = rec.static_info
    all_frame_names = [entry.name for entry in (static.frames if static else [])]
    chosen = static.chosen_frame if static else None
    chosen_name = chosen.name if chosen is not None else None
    chosen_kind = chosen.kind if chosen is not None else None
    return {
        "file_path": abs_path,
        "relative_path": rec.relative_path,
        "module_name": rec.module_name,
        # New, type-aware fields:
        "chosen_frame_name": chosen_name,
        "chosen_frame_kind": chosen_kind,
        "all_frame_names": all_frame_names,
        "multiple_frames": bool(static and static.multiple_frames),
        # Back-compat: previously the JS bridge inferred these from regex.
        "has_example": any(
            e.kind == "var" and e.name == "example"
            for e in (static.frames if static else [])
        ),
        "has_build_frame": any(
            e.kind == "function" and e.name == "build_frame"
            for e in (static.frames if static else [])
        ),
        "content_sha256": rec.content_sha256,
        "load_error": rec.load_error,
        "warnings": list(rec.warnings or []),
    }


def build_scan_index(scan_result: LibrarianScanResult) -> Dict[str, Any]:
    """Build a JSON-friendly index from a :class:`LibrarianScanResult`."""
    root_folder = Path(scan_result.root_folder).resolve()
    patternbooks: List[Dict[str, Any]] = []
    frame_examples: List[Dict[str, Any]] = []

    for rec in scan_result.modules:
        abs_path = str((root_folder / rec.relative_path).resolve())
        warnings = list(rec.warnings or [])
        static = rec.static_info

        if rec.patternbook is not None or (static and static.patternbooks):
            pb = rec.patternbook
            patternbooks.append({
                "file_path": abs_path,
                "relative_path": rec.relative_path,
                "module_name": rec.module_name,
                "pattern_names": _pattern_names_from_patternbook(pb) if pb else [],
                "group_names": _group_names_from_patternbook(pb) if pb else [],
                "patternbook_loaded": pb is not None,
                "content_sha256": rec.content_sha256,
                "load_error": rec.load_error,
                "warnings": warnings,
            })

        if static and static.frames:
            frame_examples.append(_frame_record_for_index(abs_path, rec))

    patternbooks.sort(key=lambda item: item["relative_path"])
    frame_examples.sort(key=lambda item: item["relative_path"])

    return {
        "root_folder": str(root_folder),
        "patternbooks": patternbooks,
        "frame_examples": frame_examples,
    }


def scan_library_index(folder_path: str) -> Dict[str, Any]:
    return build_scan_index(scan_library_folder(folder_path))


def scan_specific_files_index(
    file_paths: List[str],
    root_folder: str,
) -> Dict[str, Any]:
    return build_scan_index(scan_specific_files(file_paths, root_folder))


def scan_workspace_index(workspace_root: str) -> Dict[str, Any]:
    """Walk a workspace root (with sensible skip-dirs) and return the index.

    This is the single entrypoint used by the kigumi extension: it owns
    directory traversal, AST analysis, and patternbook loading so the JS
    side never duplicates any scanning logic.
    """
    return scan_library_index(workspace_root)


# ---------------------------------------------------------------------------
# Anthology helper
# ---------------------------------------------------------------------------


def create_anthology_pattern_book_from_folder(
    folder_path: str,
) -> Tuple[PatternBook, LibrarianScanResult]:
    scan_result = scan_library_folder(folder_path, load_frame_examples=True)
    if not scan_result.pattern_books:
        raise ValueError(
            "No valid PatternBook objects discovered. "
            f"Import errors: {len(scan_result.errors)}"
        )

    anthology = PatternBook.merge_multiple(scan_result.pattern_books)
    return anthology, scan_result
