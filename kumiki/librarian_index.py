"""
Pattern index file and layered search-root discovery for the librarian.

This module owns two responsibilities that sit on top of :mod:`kumiki.librarian`:

1. **Pattern index files** — a JSON cache (per file sha256) summarizing every
   kumiki source file's frames and patternbooks under a root.  Used both as a
   build-time artifact shipped with the kumiki wheel (``kumiki/_pattern_index.json``)
   and as a workspace-side cache (``<workspace>/.kigumi/pattern_index.json``).

2. **Layered search roots** — workspace, the installed ``kumiki`` package
   directory, and any explicitly declared kumiki-aware dependencies, in that
   order.  Dependencies are gated by both an explicit declaration in
   ``.kigumi/config.json`` and an ``importlib.metadata`` ``Requires-Dist``
   relationship with ``kumiki``.

The JS bridge never reads these files directly — it always goes through the
librarian CLI.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .librarian import (
    LibrarianModuleRecord,
    LibrarianScanResult,
    _discover_python_files,
    _file_sha256,
    _make_dynamic_module_name,
    _scan_single_file,
)
from .librarian_analysis import StaticEntry, analyze_file


PATTERN_INDEX_SCHEMA_VERSION = 1
WORKSPACE_INDEX_RELATIVE_PATH = ".kigumi/pattern_index.json"
PACKAGE_INDEX_FILENAME = "_pattern_index.json"


# ---------------------------------------------------------------------------
# Index entry shape
# ---------------------------------------------------------------------------


def _entry_from_static(static_frames: Iterable[StaticEntry]) -> List[Dict[str, Any]]:
    return [
        {"name": entry.name, "kind": entry.kind, "lineno": entry.lineno}
        for entry in static_frames
    ]


def _entry_from_record(rec: LibrarianModuleRecord) -> Dict[str, Any]:
    static = rec.static_info
    frames = list(static.frames) if static else []
    patternbooks_static = list(static.patternbooks) if static else []
    chosen = static.chosen_frame if static else None

    entry: Dict[str, Any] = {
        "relative_path": rec.relative_path,
        "module_name": rec.module_name,
        "sha256": rec.content_sha256,
        "frames": _entry_from_static(frames),
        "chosen_frame_name": chosen.name if chosen is not None else None,
        "chosen_frame_kind": chosen.kind if chosen is not None else None,
        "multiple_frames": bool(static and static.multiple_frames),
        "warnings": list(rec.warnings or []),
        "load_error": rec.load_error,
    }

    if patternbooks_static or rec.patternbook is not None:
        pb = rec.patternbook
        names: List[str] = []
        groups: List[str] = []
        if pb is not None:
            try:
                names = list(pb.list_patterns())
            except Exception:
                names = []
            try:
                groups = list(pb.list_groups())
            except Exception:
                groups = []
        entry["patternbook"] = {
            "loaded": pb is not None,
            "names": names,
            "groups": groups,
            "static_entries": _entry_from_static(patternbooks_static),
        }
    else:
        entry["patternbook"] = None

    return entry


# ---------------------------------------------------------------------------
# Build / read / write
# ---------------------------------------------------------------------------


def build_pattern_index(
    root_folder: str,
    *,
    prior_index: Optional[Dict[str, Any]] = None,
    load_patternbooks: bool = True,
) -> Dict[str, Any]:
    """Build a pattern index dict for *root_folder*.

    When *prior_index* is supplied, entries whose source ``sha256`` still
    matches are reused verbatim — in particular their cached
    ``patternbook.names`` / ``patternbook.groups`` — which avoids re-importing
    unchanged patternbook modules.

    Frame files are never imported here (the underlying scan keeps
    ``load_frame_examples=False``); only patternbook files are imported, and
    only when their sha256 has changed.
    """
    root = Path(root_folder).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {root_folder}")

    prior_entries: Dict[str, Dict[str, Any]] = {}
    if prior_index and isinstance(prior_index.get("entries"), dict):
        prior_entries = prior_index["entries"]

    entries: Dict[str, Dict[str, Any]] = {}
    for file_path in _discover_python_files(root):
        try:
            relative_path = str(file_path.relative_to(root))
        except ValueError:
            relative_path = str(file_path)

        sha = _file_sha256(file_path)
        cached = prior_entries.get(relative_path)
        if (
            cached is not None
            and sha is not None
            and cached.get("sha256") == sha
        ):
            entries[relative_path] = cached
            continue

        # No reusable cache: do a real scan of just this file.
        static = analyze_file(str(file_path))
        if not static.has_anything:
            continue

        record = _scan_single_file(
            root,
            file_path,
            load_frame_examples=False,
        )
        # _scan_single_file already imports patternbooks when present; only
        # skip the import when caller asked us to.
        if not load_patternbooks and record.patternbook is not None:
            record.patternbook = None

        entries[relative_path] = _entry_from_record(record)

    return {
        "schema_version": PATTERN_INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_folder": str(root),
        "entries": entries,
    }


def write_pattern_index(path: str, index: Dict[str, Any]) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(json.dumps(index, indent=2, sort_keys=True))


def read_pattern_index(path: str) -> Optional[Dict[str, Any]]:
    path_obj = Path(path)
    if not path_obj.exists():
        return None
    try:
        data = json.loads(path_obj.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != PATTERN_INDEX_SCHEMA_VERSION:
        return None
    return data


def refresh_pattern_index(root_folder: str, index_path: str) -> Dict[str, Any]:
    """Read the index at *index_path*, refresh it against *root_folder*, write it back."""
    prior = read_pattern_index(index_path)
    new_index = build_pattern_index(root_folder, prior_index=prior)
    write_pattern_index(index_path, new_index)
    return new_index


# ---------------------------------------------------------------------------
# Index → flat scan-result shim (for legacy consumers)
# ---------------------------------------------------------------------------


def scan_result_from_index(index: Dict[str, Any]) -> LibrarianScanResult:
    """Best-effort reconstruction of a ``LibrarianScanResult`` from an index.

    Patternbook *objects* are not rebuilt — only their cached name lists.  This
    is sufficient for the JSON shape consumed by the kigumi bridge.
    """
    root = index.get("root_folder") or ""
    result = LibrarianScanResult(root_folder=root)
    entries = index.get("entries") or {}
    for relative_path, entry in entries.items():
        record = LibrarianModuleRecord(
            relative_path=relative_path,
            module_name=entry.get("module_name")
            or _make_dynamic_module_name(Path(root), Path(root) / relative_path),
            content_sha256=entry.get("sha256"),
            warnings=list(entry.get("warnings") or []),
            load_error=entry.get("load_error"),
        )
        result.modules.append(record)
    return result


# ---------------------------------------------------------------------------
# Layered search roots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchRoot:
    name: str
    kind: str  # "workspace" | "kumiki" | "dep"
    root_path: Path


def _kumiki_package_root() -> Optional[Path]:
    spec = importlib.util.find_spec("kumiki")
    if spec is None or spec.origin is None:
        return None
    return Path(spec.origin).resolve().parent


def _dep_package_root(dist_name: str) -> Optional[Path]:
    try:
        dist = importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return None
    # Prefer top_level.txt
    try:
        top_text = dist.read_text("top_level.txt") or ""
    except Exception:
        top_text = ""
    top_pkgs = [line.strip() for line in top_text.splitlines() if line.strip()]
    if not top_pkgs:
        top_pkgs = [dist_name.replace("-", "_")]
    for top_pkg in top_pkgs:
        spec = importlib.util.find_spec(top_pkg)
        if spec is None or spec.origin is None:
            continue
        return Path(spec.origin).resolve().parent
    return None


def _dep_requires_kumiki(dist_name: str) -> bool:
    if dist_name.lower() == "kumiki":
        return True
    try:
        dist = importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return False
    requires = dist.requires or []
    for req in requires:
        # ``req`` looks like ``"kumiki>=0.1; python_version >= '3.10'"`` etc.
        head = req.split(";", 1)[0].strip()
        # Strip extras: ``kumiki[extra]>=0.1`` → ``kumiki``
        name = head.split("[", 1)[0]
        for sep in ("=", "<", ">", "!", "~", " "):
            name = name.split(sep, 1)[0]
        if name.strip().lower() == "kumiki":
            return True
    return False


def _read_workspace_config(workspace_root: Path) -> Dict[str, Any]:
    config_path = workspace_root / ".kigumi" / "config.json"
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def discover_search_roots(
    workspace_root: str,
    *,
    extra_dependency_names: Optional[Iterable[str]] = None,
) -> List[SearchRoot]:
    """Return ordered search roots: workspace, kumiki, then declared deps.

    A declared dependency is included only if it is both (a) listed in the
    workspace's ``.kigumi/config.json`` (key ``kumiki_dependencies``) or
    passed via *extra_dependency_names*, **and** (b) its installed metadata's
    ``Requires-Dist`` lists ``kumiki``.
    """
    workspace_path = Path(workspace_root).resolve()
    roots: List[SearchRoot] = [
        SearchRoot(name="workspace", kind="workspace", root_path=workspace_path)
    ]

    kumiki_root = _kumiki_package_root()
    if kumiki_root is not None and kumiki_root != workspace_path:
        roots.append(SearchRoot(name="kumiki", kind="kumiki", root_path=kumiki_root))

    config = _read_workspace_config(workspace_path)
    declared = list(config.get("kumiki_dependencies") or [])
    if extra_dependency_names:
        for name in extra_dependency_names:
            if name not in declared:
                declared.append(name)

    for dep_name in declared:
        if dep_name.lower() == "kumiki":
            continue
        if not _dep_requires_kumiki(dep_name):
            continue
        dep_root = _dep_package_root(dep_name)
        if dep_root is None:
            continue
        roots.append(SearchRoot(name=dep_name, kind="dep", root_path=dep_root))

    return roots


# ---------------------------------------------------------------------------
# Per-root index resolution (bundled-or-build)
# ---------------------------------------------------------------------------


def load_or_build_pattern_index_for_root(root: SearchRoot) -> Dict[str, Any]:
    """Return a pattern index for *root*.

    For kumiki/dep roots, prefer a bundled ``_pattern_index.json`` if it
    exists and is valid; otherwise scan the root.  For workspace roots we
    always scan (the workspace cache is managed via
    :func:`refresh_pattern_index` separately).
    """
    if root.kind in ("kumiki", "dep"):
        bundled = root.root_path / PACKAGE_INDEX_FILENAME
        cached = read_pattern_index(str(bundled))
        if cached is not None:
            return cached
    return build_pattern_index(str(root.root_path))


def scan_all_roots(
    workspace_root: str,
    *,
    extra_dependency_names: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Aggregate per-root pattern indexes in search-path order.

    The aggregated payload preserves every entry; conflicts (same chosen frame
    name across roots) are not collapsed — the UI decides what to surface.
    """
    roots = discover_search_roots(
        workspace_root, extra_dependency_names=extra_dependency_names
    )
    per_root: List[Dict[str, Any]] = []
    for root in roots:
        index = load_or_build_pattern_index_for_root(root)
        per_root.append({
            "name": root.name,
            "kind": root.kind,
            "root_path": str(root.root_path),
            "index": index,
        })
    return {
        "schema_version": PATTERN_INDEX_SCHEMA_VERSION,
        "workspace_root": str(Path(workspace_root).resolve()),
        "roots": per_root,
    }
