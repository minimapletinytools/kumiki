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

import ast
import contextlib
from dataclasses import dataclass, field, replace
import inspect
import math
from pathlib import Path
import hashlib
import importlib.util
import sys
import textwrap
import traceback
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Tuple, get_args, get_origin

from sympy import Float, Rational

from .librarian_analysis import ModuleStaticInfo, analyze_file
from .rule import scalar
from .patternbook import Pattern


_DYNAMIC_MODULE_PREFIX = "giraffe_librarian_dynamic"

_PARAM_KIND_VALUES: Tuple[str, ...] = ("number", "boolean", "string", "enum", "v3")


@dataclass(frozen=True)
class Param:
    """Author-facing parameter declaration helper.

    Use as a callable default value, e.g.:

        def build_frame(width=Param(scalar(2), description="Timber width")):
            ...
    """

    default: Any
    description: str = ""
    kind: Optional[Literal["number", "boolean", "string", "enum", "v3"]] = None
    options: Optional[Tuple[str, ...]] = None
    minimum: Optional[Any] = None
    maximum: Optional[Any] = None
    optional: Optional[bool] = None


@dataclass(frozen=True)
class RenderParameterDescriptor:
    name: str
    default_value: Any
    kind: Literal["number", "boolean", "string", "enum", "v3"]
    description: str = ""
    options: Tuple[str, ...] = ()
    minimum: Optional[Any] = None
    maximum: Optional[Any] = None
    optional: bool = False

    def to_protocol_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "default": serialize_render_parameter_value(self.default_value),
        }
        if self.options:
            payload["options"] = [str(option) for option in self.options]
        if self.minimum is not None:
            payload["minimum"] = serialize_render_parameter_value(self.minimum)
        if self.maximum is not None:
            payload["maximum"] = serialize_render_parameter_value(self.maximum)
        if self.optional:
            payload["optional"] = True
        return payload


def _looks_like_sympy_number(value: Any) -> bool:
    return hasattr(value, "is_real") and hasattr(value, "evalf")


def _looks_like_v3_value(value: Any) -> bool:
    shape = getattr(value, "shape", None)
    return shape in ((3, 1), (1, 3))


def _infer_parameter_kind_from_annotation(annotation: Any, annotation_text: Optional[str]) -> Optional[Literal["number", "boolean", "string", "enum", "v3"]]:
    text = (annotation_text or "").replace(" ", "")
    if "V3" in text:
        return "v3"
    if annotation is bool:
        return "boolean"
    if annotation is str:
        return "string"
    if annotation in (int, float, Rational, Float):
        return "number"
    return None


def _infer_parameter_kind(default_value: Any, annotation: Any = None, annotation_text: Optional[str] = None) -> Literal["number", "boolean", "string", "enum", "v3"]:
    annotation_kind = _infer_parameter_kind_from_annotation(annotation, annotation_text)
    if annotation_kind is not None:
        return annotation_kind
    if isinstance(default_value, bool):
        return "boolean"
    if isinstance(default_value, str):
        return "string"
    if _looks_like_v3_value(default_value):
        return "v3"
    if isinstance(default_value, (int, float, Rational, Float)):
        return "number"
    if _looks_like_sympy_number(default_value):
        return "number"
    return "string"


def _normalize_param_options(options: Optional[Iterable[Any]]) -> Tuple[str, ...]:
    if options is None:
        return ()
    return tuple(str(option) for option in options)


def _strip_optional_annotation_text(annotation_text: Optional[str]) -> Optional[str]:
    if annotation_text is None:
        return None
    stripped = annotation_text.strip()
    compact = stripped.replace(" ", "")
    if compact.startswith("Optional[") and compact.endswith("]"):
        return stripped[stripped.find("[") + 1:-1].strip()
    return stripped


def _unwrap_optional_annotation(annotation: Any, annotation_text: Optional[str]) -> Tuple[Any, bool, Optional[str]]:
    optional = False
    inner_annotation = annotation
    inner_text = annotation_text

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None and args:
        non_none_args = tuple(arg for arg in args if arg is not type(None))
        if len(non_none_args) == len(args) - 1:
            optional = True
            inner_annotation = non_none_args[0]

    compact = (annotation_text or "").replace(" ", "")
    if "Optional[" in compact or "|None" in compact or "None|" in compact:
        optional = True
        inner_text = _strip_optional_annotation_text(annotation_text)

    return inner_annotation, optional, inner_text


def _extract_parameter_annotation_texts(callable_obj: Any) -> Dict[str, str]:
    try:
        source = textwrap.dedent(inspect.getsource(callable_obj))
    except (OSError, TypeError):
        return {}

    try:
        module = ast.parse(source)
    except SyntaxError:
        return {}

    target_name = getattr(callable_obj, "__name__", None)
    if not target_name:
        return {}

    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_name:
            parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            result: Dict[str, str] = {}
            for param in parameters:
                if param.annotation is not None:
                    result[param.arg] = ast.unparse(param.annotation)
            return result
    return {}


def _descriptor_from_signature_parameter(
    parameter: inspect.Parameter,
    annotation_text: Optional[str] = None,
) -> Optional[RenderParameterDescriptor]:
    if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
        return None

    if parameter.default is inspect.Parameter.empty:
        # Only optional/defaulted parameters are currently exposed in the UI.
        return None

    annotation = parameter.annotation if parameter.annotation is not inspect.Parameter.empty else None
    inner_annotation, annotation_is_optional, inner_annotation_text = _unwrap_optional_annotation(annotation, annotation_text)

    if parameter.default is None and not annotation_is_optional:
        return None

    if isinstance(parameter.default, Param):
        declared = parameter.default
        default_value = declared.default
        declared_kind = declared.kind
        if declared_kind is None:
            kind = _infer_parameter_kind(default_value, inner_annotation, inner_annotation_text)
        else:
            kind = str(declared_kind)
            if kind not in _PARAM_KIND_VALUES:
                raise ValueError(
                    f"Parameter '{parameter.name}' has invalid kind '{declared_kind}'. "
                    f"Expected one of: {_PARAM_KIND_VALUES}"
                )
        options = _normalize_param_options(declared.options)
        if kind == "enum" and not options:
            raise ValueError(
                f"Parameter '{parameter.name}' declared as enum must provide options"
            )
        optional = declared.optional if declared.optional is not None else (default_value is None or annotation_is_optional)
        return RenderParameterDescriptor(
            name=parameter.name,
            default_value=default_value,
            kind=kind,  # type: ignore[arg-type]
            description=declared.description,
            options=options,
            minimum=declared.minimum,
            maximum=declared.maximum,
            optional=optional,
        )

    if parameter.default is None:
        kind = _infer_parameter_kind_from_annotation(inner_annotation, inner_annotation_text)
        if kind is None:
            return None
        return RenderParameterDescriptor(
            name=parameter.name,
            default_value=None,
            kind=kind,
            description="",
            options=(),
            minimum=None,
            maximum=None,
            optional=True,
        )

    inferred_kind = _infer_parameter_kind(parameter.default, inner_annotation, inner_annotation_text)
    return RenderParameterDescriptor(
        name=parameter.name,
        default_value=parameter.default,
        kind=inferred_kind,
        description="",
        options=(),
        minimum=None,
        maximum=None,
        optional=annotation_is_optional,
    )


def discover_callable_render_parameters(
    callable_obj: Any,
    *,
    skip_first_parameter: bool = False,
) -> List[RenderParameterDescriptor]:
    """Inspect a callable signature and return render-parameter descriptors."""
    signature = inspect.signature(callable_obj)
    annotation_texts = _extract_parameter_annotation_texts(callable_obj)
    discovered: List[RenderParameterDescriptor] = []
    parameters = list(signature.parameters.values())

    if skip_first_parameter and parameters:
        parameters = parameters[1:]

    for parameter in parameters:
        descriptor = _descriptor_from_signature_parameter(
            parameter,
            annotation_text=annotation_texts.get(parameter.name),
        )
        if descriptor is not None:
            discovered.append(descriptor)
    return discovered


def _coerce_bool(value: Any, param_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"Parameter '{param_name}' expects a boolean value")


def _coerce_number(value: Any, param_name: str) -> Any:
    if isinstance(value, bool):
        return scalar(1 if value else 0)
    if isinstance(value, int):
        return scalar(value)
    if isinstance(value, float):
        return scalar(str(value))
    if isinstance(value, (Rational, Float)):
        return value
    if _looks_like_sympy_number(value):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"Parameter '{param_name}' expects a non-empty number")
        try:
            return scalar(stripped)
        except Exception:
            try:
                return scalar(stripped)
            except Exception as exc:
                raise ValueError(
                    f"Parameter '{param_name}' expects a numeric value, got '{value}'"
                ) from exc
    raise ValueError(f"Parameter '{param_name}' expects a numeric value")


def _coerce_v3(value: Any, param_name: str) -> Any:
    from .rule import create_v3, scalar

    if _looks_like_v3_value(value):
        return create_v3(
            _coerce_number(value[0], f"{param_name}.x"),
            _coerce_number(value[1], f"{param_name}.y"),
            _coerce_number(value[2], f"{param_name}.z"),
        )
    if isinstance(value, dict):
        return create_v3(
            _coerce_number(value.get("x"), f"{param_name}.x"),
            _coerce_number(value.get("y"), f"{param_name}.y"),
            _coerce_number(value.get("z"), f"{param_name}.z"),
        )
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return create_v3(
            _coerce_number(value[0], f"{param_name}.x"),
            _coerce_number(value[1], f"{param_name}.y"),
            _coerce_number(value[2], f"{param_name}.z"),
        )
    raise ValueError(f"Parameter '{param_name}' expects a V3 value")


def _coerce_parameter_value(value: Any, descriptor: RenderParameterDescriptor) -> Any:
    if descriptor.kind == "boolean":
        return _coerce_bool(value, descriptor.name)
    if descriptor.kind == "number":
        coerced = _coerce_number(value, descriptor.name)
        if descriptor.minimum is not None and coerced < descriptor.minimum:
            raise ValueError(
                f"Parameter '{descriptor.name}' must be >= {descriptor.minimum}, got {coerced}"
            )
        if descriptor.maximum is not None and coerced > descriptor.maximum:
            raise ValueError(
                f"Parameter '{descriptor.name}' must be <= {descriptor.maximum}, got {coerced}"
            )
        return coerced
    if descriptor.kind == "v3":
        return _coerce_v3(value, descriptor.name)
    if descriptor.kind == "enum":
        coerced = str(value)
        if coerced not in descriptor.options:
            raise ValueError(
                f"Parameter '{descriptor.name}' must be one of {list(descriptor.options)}, got '{coerced}'"
            )
        return coerced
    return str(value)


def resolve_callable_render_parameters(
    callable_obj: Any,
    provided_values: Optional[Mapping[str, Any]],
    *,
    skip_first_parameter: bool = False,
) -> Tuple[List[RenderParameterDescriptor], Dict[str, Any]]:
    """Return (descriptors, resolved kwargs) for a callable.

    Resolved kwargs include defaults plus any provided overrides.
    """
    descriptors = discover_callable_render_parameters(
        callable_obj,
        skip_first_parameter=skip_first_parameter,
    )

    provided = dict(provided_values or {})
    resolved: Dict[str, Any] = {}
    for descriptor in descriptors:
        if descriptor.name in provided:
            value = provided[descriptor.name]
        else:
            value = descriptor.default_value
        if value is None:
            resolved[descriptor.name] = None
            continue
        resolved[descriptor.name] = _coerce_parameter_value(value, descriptor)

    return descriptors, resolved


def serialize_render_parameter_value(value: Any) -> Any:
    """Convert render parameter values to JSON-friendly primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _looks_like_v3_value(value):
        return {
            "x": serialize_render_parameter_value(value[0]),
            "y": serialize_render_parameter_value(value[1]),
            "z": serialize_render_parameter_value(value[2]),
        }
    if isinstance(value, (Rational, Float)):
        return str(value)
    if _looks_like_sympy_number(value):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serialize_render_parameter_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): serialize_render_parameter_value(item)
            for key, item in value.items()
        }
    return str(value)


@dataclass
class LibrarianModuleRecord:
    relative_path: str
    module_name: str
    pattern_list: Optional[List[Pattern]] = None
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
    def pattern_lists(self) -> List[List[Pattern]]:
        return [
            module.pattern_list
            for module in self.modules
            if module.pattern_list is not None
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
    "oldcrap", "test-fixtures", "test_fixtures",
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


def _resolve_pattern_list(module: Any, warnings: List[str]) -> Optional[List[Pattern]]:
    """Return List[Pattern] from module.patterns if it's a valid pattern list."""
    if not hasattr(module, "patterns"):
        return None
    candidate = getattr(module, "patterns")
    if not isinstance(candidate, list):
        warnings.append(
            f"module.patterns exists but is {type(candidate).__name__}, expected list"
        )
        return None
    patterns: List[Pattern] = []
    for i, item in enumerate(candidate):
        if not isinstance(item, Pattern):
            warnings.append(
                f"module.patterns[{i}] is {type(item).__name__}, expected Pattern — skipping"
            )
            continue
        patterns.append(item)
    return patterns if patterns else None


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

    needs_import = bool(static_info.pattern_lists) or (
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

    if static_info.pattern_lists:
        record.pattern_list = _resolve_pattern_list(module, record.warnings)
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

        if rec.pattern_list is not None or (static and static.pattern_lists):
            pl = rec.pattern_list or []
            patterns_payload = [
                {"path": p.path, "tags": list(p.tags), "pattern_type": p.pattern_type}
                for p in pl
            ]
            patternbooks.append({
                "file_path": abs_path,
                "relative_path": rec.relative_path,
                "module_name": rec.module_name,
                "patterns": patterns_payload,
                "pattern_names": [p.name for p in pl],
                "patternbook_loaded": rec.pattern_list is not None,
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


# ──────────────────────────────────────────────────────────────────────────────
# Multi-pattern grid: merge a pattern list into a single tiled Frame
# ──────────────────────────────────────────────────────────────────────────────

def _pattern_frame_xy_extent(frame: Any) -> "tuple[float, float, float, float]":
    """Return (min_x, min_y, max_x, max_y) of a frame's timbers without triangulating."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for ct in frame.cut_timbers:
        t = ct.timber
        bp = t.get_bottom_position_global()
        ld = t.get_length_direction_global()
        wd = t.get_width_direction_global()
        hd = t.get_height_direction_global()
        length = float(t.length)
        w = float(t.get_perfect_size()[0])
        h = float(t.get_perfect_size()[1])
        for sl in (0.0, length):
            for sw in (-w / 2, w / 2):
                for sh in (-h / 2, h / 2):
                    x = float(bp[0] + ld[0] * sl + wd[0] * sw + hd[0] * sh)
                    y = float(bp[1] + ld[1] * sl + wd[1] * sw + hd[1] * sh)
                    if x < min_x: min_x = x
                    if x > max_x: max_x = x
                    if y < min_y: min_y = y
                    if y > max_y: max_y = y
    if min_x == float("inf"):
        return (-0.5, -0.5, 0.5, 0.5)
    return (min_x, min_y, max_x, max_y)


def _pattern_grid_offsets(
    extents: "list[tuple[float, float, float, float]]",
    padding: float = 0.5,
) -> "list[tuple[float, float]]":
    """Return (dx, dy) per pattern to tile frames in a square-ish grid at origin.

    Each frame is centered within its grid cell; the whole grid is centered at (0, 0).
    """
    N = len(extents)
    cols = math.ceil(math.sqrt(N))
    rows = math.ceil(N / cols)

    widths  = [ex - wx for wx, wy, ex, ey in extents]
    heights = [ey - wy for wx, wy, ex, ey in extents]
    cx_list = [(wx + ex) / 2 for wx, wy, ex, ey in extents]
    cy_list = [(wy + ey) / 2 for wx, wy, ex, ey in extents]

    col_widths  = [0.0] * cols
    row_heights = [0.0] * rows
    for i in range(N):
        col_widths[i % cols]   = max(col_widths[i % cols],   widths[i])
        row_heights[i // cols] = max(row_heights[i // cols], heights[i])

    col_starts = [0.0] * cols
    for c in range(1, cols):
        col_starts[c] = col_starts[c - 1] + col_widths[c - 1] + padding

    row_starts = [0.0] * rows
    for r in range(1, rows):
        row_starts[r] = row_starts[r - 1] + row_heights[r - 1] + padding

    total_w = col_starts[-1] + col_widths[-1]
    total_h = row_starts[-1] + row_heights[-1]

    offsets = []
    for i in range(N):
        cell_cx = col_starts[i % cols]   + col_widths[i % cols]   / 2 - total_w / 2
        cell_cy = row_starts[i // cols]  + row_heights[i // cols] / 2 - total_h / 2
        offsets.append((cell_cx - cx_list[i], cell_cy - cy_list[i]))
    return offsets


def _translate_frame(frame: Any, dx: float, dy: float) -> Any:
    """Return a new Frame with every timber, accessory, footprint, and joint shifted by (dx, dy, 0).

    Cuts are stored in LOCAL timber coordinates so they follow the timber automatically.
    We maintain an old_cut → new_cut identity map so that source_joints.cuttings
    references are rewritten to point at the new cut objects — serialize_layers uses
    identity (`is`) checks to match joints to their timbers in the frame.
    """
    from .rule import Transform, create_v2, create_v3
    from .timber import CutTimber, Frame
    from .footprint import Footprint

    offset = create_v3(scalar(dx), scalar(dy), scalar(0))

    cut_map: Dict[int, Any] = {}  # id(old_cut) → new_cut

    new_cut_timbers = []
    for ct in frame.cut_timbers:
        t = ct.timber
        new_pos = t.get_bottom_position_global() + offset
        new_timber = replace(t, transform=Transform(position=new_pos, orientation=t.orientation))
        new_cuts = []
        for cut in ct.cuts:
            new_cut = replace(cut, timber=new_timber)
            cut_map[id(cut)] = new_cut
            new_cuts.append(new_cut)
        new_cut_timbers.append(CutTimber(timber=new_timber, cuts=new_cuts))

    new_accessories: List[Any] = []
    for acc in (frame.accessories or []):
        if hasattr(acc, "transform"):
            new_pos_acc = acc.transform.position + offset
            new_accessories.append(replace(acc, transform=Transform(position=new_pos_acc, orientation=acc.transform.orientation)))
        else:
            new_accessories.append(acc)

    new_footprints: List[Any] = []
    for fp in (getattr(frame, "footprints", None) or []):
        new_corners = tuple(create_v2(c[0] + scalar(dx), c[1] + scalar(dy)) for c in fp.corners)
        new_footprints.append(Footprint(corners=new_corners))

    # Rewrite source_joints so their cuttings dict uses the new cut objects,
    # preserving the identity relationship that serialize_layers depends on.
    new_source_joints: List[Any] = []
    for joint in (getattr(frame, "source_joints", None) or []):
        old_cuttings = getattr(joint, "cuttings", {})
        new_cuttings = {name: cut_map.get(id(cut), cut) for name, cut in old_cuttings.items()}
        new_source_joints.append(replace(joint, cuttings=new_cuttings))

    return Frame(
        cut_timbers=new_cut_timbers,
        accessories=new_accessories,
        footprints=new_footprints,
        source_joints=new_source_joints if new_source_joints else None,
    )


def build_pattern_grid_frame(pattern_list: List[Any], padding: float = 0.5) -> Any:
    """Render all patterns and merge into one Frame arranged in a square-ish grid at the origin.

    Each pattern is rendered at origin=(0,0,0). Its XY footprint is computed from
    timber bounding boxes, and each frame is then translated to its grid cell by
    rebuilding timbers and accessories at their new positions (rather than post-hoc
    vertex manipulation). The result is a single Frame that passes through the normal
    build_real_geometry path, so accessories, joints, and fallback geometry all work.
    """
    from .rule import create_v3
    from .timber import Frame

    if not pattern_list:
        raise ValueError("Pattern list is empty")

    origin = create_v3(scalar(0), scalar(0), scalar(0))

    frames: List[Any] = []
    for p in pattern_list:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = p.lambda_(origin)
            if hasattr(result, "cut_timbers") and hasattr(result, "accessories"):
                frames.append(result)
            else:
                print(f"[grid] skipping pattern '{getattr(p, 'name', '?')}': lambda returned {type(result).__name__}, expected Frame", file=sys.stderr)
        except Exception as exc:
            print(f"[grid] skipping pattern '{getattr(p, 'name', '?')}': {exc}", file=sys.stderr)

    if not frames:
        raise ValueError("No patterns produced a renderable Frame")

    extents = []
    for f in frames:
        try:
            extents.append(_pattern_frame_xy_extent(f))
        except Exception:
            extents.append((-0.5, -0.5, 0.5, 0.5))

    offsets = _pattern_grid_offsets(extents, padding=padding)

    all_cut_timbers: List[Any] = []
    all_accessories: List[Any] = []
    all_footprints: List[Any] = []
    all_source_joints: List[Any] = []
    for f, (dx, dy) in zip(frames, offsets):
        translated = _translate_frame(f, dx, dy)
        all_cut_timbers.extend(translated.cut_timbers)
        all_accessories.extend(translated.accessories or [])
        all_footprints.extend(getattr(translated, "footprints", None) or [])
        all_source_joints.extend(getattr(translated, "source_joints", None) or [])

    return Frame(
        cut_timbers=all_cut_timbers,
        accessories=all_accessories,
        footprints=all_footprints,
        source_joints=all_source_joints if all_source_joints else None,
    )


