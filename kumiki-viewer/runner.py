#!/usr/bin/env python3
"""
Persistent stdio runner for the Kumiki Viewer VS Code extension.

Protocol:
- stdin: newline-delimited JSON requests
- stdout: newline-delimited JSON responses/events only
- stderr: logs, warnings, tracebacks
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple


def _find_project_root_from_argv() -> "Tuple[Path | None, bool]":
    """Walk up from the target file path (argv[1]) to find the project root and type.
    Returns (root_path, is_local_dev) or (None, False)."""
    if len(sys.argv) < 2:
        return None, False
    candidate = Path(sys.argv[1]).resolve().parent
    while True:
        if (candidate / "kumiki").is_dir():
            return candidate, True
        if (candidate / ".kumiki.yaml").is_file():
            return candidate, False
        parent = candidate.parent
        if parent == candidate:
            return None, False
        candidate = parent


_project_root, _is_local_dev = _find_project_root_from_argv()
if _project_root is not None:
    _project_root_str = str(_project_root)
    if _is_local_dev and _project_root_str not in sys.path:
        sys.path.insert(0, _project_root_str)

    # If we're not running from the venv, re-exec with the venv python so all
    # dependencies (sympy etc.) are available.
    def _find_venv_python(root: Path) -> "Path | None":
        for rel in (".venv/bin/python3", ".venv/bin/python", "venv/bin/python3", "venv/bin/python"):
            p = root / rel
            if p.exists():
                return p
        return None

    _venv_python = _find_venv_python(_project_root)
    if _venv_python is not None and Path(sys.executable).resolve() != _venv_python.resolve():
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)
        # os.execv replaces the current process; code below never runs if it succeeds


# Enable milestone emission so pattern scripts can report progress to the viewer.
os.environ["KUMIKI_VIEWER_MILESTONES"] = "1"

TARGET_MODULE_NAME = "_kumiki_viewer_target"


@dataclass
class ProfilingStats:
    """Timing data collected during runner operations (seconds)."""
    reload_s: Optional[float] = None
    geometry_s: Optional[float] = None


@dataclass
class SlotState:
    """State for a single named viewer slot (e.g. 'main' or a pattern)."""
    file_path: Path
    module: Any
    frame: Any
    mesh_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    patternbook: Optional[Any] = None
    single_pattern_name: Optional[str] = None


@dataclass
class RunnerState:
    """Top-level runner state containing one or more named slots."""
    slots: Dict[str, SlotState] = field(default_factory=dict)
    active_slot: str = "main"

    # --- backwards-compat shims so existing code that reads state.frame etc. still works ---
    @property
    def _active(self) -> SlotState:
        return self.slots[self.active_slot]

    @property
    def file_path(self) -> Path:
        return self._active.file_path

    @property
    def module(self) -> Any:
        return self._active.module

    @property
    def frame(self) -> Any:
        return self._active.frame

    @property
    def mesh_cache(self) -> Dict[str, Dict[str, Any]]:
        return self._active.mesh_cache

    def get_slot(self, slot: str) -> SlotState:
        if slot not in self.slots:
            raise KeyError(f"No slot named '{slot}'. Active slots: {list(self.slots.keys())}")
        return self.slots[slot]


def log_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit_message(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload), flush=True)


def serialize_sympy(obj: Any) -> Any:
    if hasattr(obj, "evalf"):
        return str(obj)
    if hasattr(obj, "__float__"):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    return obj if isinstance(obj, (str, int, float, bool)) or obj is None else str(obj)


def serialize_vector(vec: Any) -> Any:
    if vec is None:
        return None
    try:
        return [serialize_sympy(vec[i, 0]) for i in range(vec.shape[0])]
    except Exception:
        return str(vec)


def get_timber_display_name(timber: Any) -> str:
    if hasattr(timber, "ticket") and hasattr(timber.ticket, "name"):
        return timber.ticket.name
    if hasattr(timber, "name"):
        return timber.name
    return type(timber).__name__


def _compute_csg_depth(csg: Any) -> int:
    from kumiki.cutcsg import SolidUnion, Difference

    if isinstance(csg, SolidUnion):
        if not csg.children:
            return 1
        return 1 + max(_compute_csg_depth(child) for child in csg.children)

    if isinstance(csg, Difference):
        depths: List[int] = [_compute_csg_depth(csg.base)]
        depths.extend(_compute_csg_depth(child) for child in csg.subtract)
        return 1 + max(depths)

    return 1


def _count_csg_nodes_and_features(csg: Any) -> Tuple[int, int]:
    """Return (node_count, named_feature_count) for the CSG tree."""
    from kumiki.cutcsg import SolidUnion, Difference, HalfSpace, RectangularPrism

    nodes = 1
    features = 0

    if isinstance(csg, HalfSpace):
        if getattr(csg, "named_feature", None) is not None:
            features += 1
    elif isinstance(csg, RectangularPrism):
        nf = getattr(csg, "named_features", None)
        if nf is not None:
            features += len(nf)

    if isinstance(csg, SolidUnion):
        for child in csg.children:
            cn, cf = _count_csg_nodes_and_features(child)
            nodes += cn
            features += cf
    elif isinstance(csg, Difference):
        cn, cf = _count_csg_nodes_and_features(csg.base)
        nodes += cn
        features += cf
        for sub in csg.subtract:
            cn, cf = _count_csg_nodes_and_features(sub)
            nodes += cn
            features += cf

    return (nodes, features)


def serialize_cut_timber(cut_timber: Any) -> Dict[str, Any]:
    timber = cut_timber.timber
    return {
        "name": get_timber_display_name(timber),
        "length": serialize_sympy(timber.length),
        "width": serialize_sympy(timber.size[0]),
        "height": serialize_sympy(timber.size[1]),
        "bottom_position": serialize_vector(timber.get_bottom_position_global()),
        "length_direction": serialize_vector(timber.get_length_direction_global()),
        "width_direction": serialize_vector(timber.get_width_direction_global()),
        "height_direction": serialize_vector(timber.get_height_direction_global()),
        "cuts_count": len(cut_timber.cuts) if hasattr(cut_timber, "cuts") else 0,
    }


def prism_to_mesh(prism: Any) -> Dict[str, Any]:
    """Convert a RectangularPrism to a flat vertex list + index list triangle mesh.

    Vertex layout (8 corners, indices 0-7):
        0: -hw, -hh, z0    1: +hw, -hh, z0    2: +hw, +hh, z0    3: -hw, +hh, z0
        4: -hw, -hh, z1    5: +hw, -hh, z1    6: +hw, +hh, z1    7: -hw, +hh, z1
    where z0 = start_distance (bottom) and z1 = end_distance (top) in local Z.
    """
    hw = float(prism.size[0]) / 2.0
    hh = float(prism.size[1]) / 2.0
    z0 = float(prism.start_distance) if prism.start_distance is not None else 0.0
    z1 = float(prism.end_distance) if prism.end_distance is not None else 0.0

    M = prism.transform.orientation.matrix
    P = prism.transform.position
    # Convert SymPy values to Python floats once
    m = [[float(M[r, c]) for c in range(3)] for r in range(3)]
    p = [float(P[0]), float(P[1]), float(P[2])]

    def g(x: float, y: float, z: float) -> list:
        return [
            p[0] + m[0][0] * x + m[0][1] * y + m[0][2] * z,
            p[1] + m[1][0] * x + m[1][1] * y + m[1][2] * z,
            p[2] + m[2][0] * x + m[2][1] * y + m[2][2] * z,
        ]

    verts = [
        g(-hw, -hh, z0),  # 0
        g( hw, -hh, z0),  # 1
        g( hw,  hh, z0),  # 2
        g(-hw,  hh, z0),  # 3
        g(-hw, -hh, z1),  # 4
        g( hw, -hh, z1),  # 5
        g( hw,  hh, z1),  # 6
        g(-hw,  hh, z1),  # 7
    ]

    # 12 triangles with outward-facing CCW normals (verified via cross-product)
    indices = [
        0, 2, 1,   0, 3, 2,  # bottom (-Z face)
        4, 5, 6,   4, 6, 7,  # top    (+Z face)
        0, 1, 5,   0, 5, 4,  # front  (-Y face)
        3, 7, 6,   3, 6, 2,  # back   (+Y face)
        3, 0, 4,   3, 4, 7,  # left   (-X face)
        1, 2, 6,   1, 6, 5,  # right  (+X face)
    ]

    return {
        "vertices": [coord for v in verts for coord in v],  # flat [x0,y0,z0, x1,y1,z1, ...]
        "indices": indices,
    }


def _cut_timber_to_triangle_mesh_payload(
    cut_timber: Any,
    local_csg: Any,
    timber_key: str,
) -> Dict[str, Any]:
    from kumiki.cutcsg import adopt_csg
    from kumiki.rule import Transform
    from kumiki.triangles import triangulate_cutcsg

    global_csg = adopt_csg(cut_timber.timber.transform, Transform.identity(), local_csg)
    triangle_mesh = triangulate_cutcsg(global_csg).mesh

    vertices = triangle_mesh.vertices.reshape(-1).tolist()
    indices = triangle_mesh.faces.reshape(-1).tolist()

    bounds = triangle_mesh.bounds
    dims = bounds[1] - bounds[0]

    timber = cut_timber.timber
    csg_nodes, csg_features = _count_csg_nodes_and_features(local_csg)
    return {
        "name": get_timber_display_name(timber),
        "memberName": get_timber_display_name(timber),
        "memberType": "timber",
        "memberKey": timber_key,
        "timberKey": timber_key,
        "vertices": vertices,
        "indices": indices,
        "prism_length": round(float(getattr(timber, "length", dims[2])), 6),
        "prism_width": round(float(getattr(timber, "size", [dims[0], dims[1]])[0]), 6),
        "prism_height": round(float(getattr(timber, "size", [dims[0], dims[1]])[1]), 6),
        "csg_nodes": csg_nodes,
        "csg_features": csg_features,
    }


def _accessory_to_triangle_mesh_payload(
    accessory: Any,
    local_csg: Any,
    accessory_key: str,
    accessory_name: str,
) -> Dict[str, Any]:
    from kumiki.cutcsg import adopt_csg
    from kumiki.rule import Transform
    from kumiki.triangles import triangulate_cutcsg

    if hasattr(accessory, "transform"):
        global_csg = adopt_csg(accessory.transform, Transform.identity(), local_csg)
    else:
        # Accessories that already carry global-space CSG (e.g. CSGAccessory)
        # do not need an additional transform adoption.
        global_csg = local_csg
    triangle_mesh = triangulate_cutcsg(global_csg).mesh

    vertices = triangle_mesh.vertices.reshape(-1).tolist()
    indices = triangle_mesh.faces.reshape(-1).tolist()

    bounds = triangle_mesh.bounds
    dims = bounds[1] - bounds[0]

    return {
        "name": accessory_name,
        "memberName": accessory_name,
        "memberType": "accessory",
        "memberKey": accessory_key,
        "timberKey": accessory_key,
        "vertices": vertices,
        "indices": indices,
        "prism_length": round(float(dims[2]), 6),
        "prism_width": round(float(dims[0]), 6),
        "prism_height": round(float(dims[1]), 6),
    }


def build_real_geometry(state: RunnerState, slot_state: Optional['SlotState'] = None) -> Dict[str, Any]:
    """Build triangle mesh geometry for every cut timber."""
    ss = slot_state if slot_state is not None else state._active
    frame = ss.frame
    meshes = []
    changed_keys = []
    remesh_metrics = []
    seen_keys = set()
    key_counts: Dict[str, int] = {}

    for cut_timber in frame.cut_timbers:
        try:
            timber = cut_timber.timber
            key_base = get_timber_display_name(timber)

            occurrence = key_counts.get(key_base, 0)
            key_counts[key_base] = occurrence + 1
            timber_key = f"{key_base}#{occurrence}"

            local_csg = cut_timber.render_timber_with_cuts_csg_local()

            remesh_t0 = time.monotonic()
            csg_depth = _compute_csg_depth(local_csg)
            mesh_payload = _cut_timber_to_triangle_mesh_payload(
                cut_timber,
                local_csg,
                timber_key,
            )
            remesh_s = time.monotonic() - remesh_t0
            triangle_count = len(mesh_payload.get("indices", [])) // 3
            ss.mesh_cache[timber_key] = {
                "mesh": mesh_payload,
                "local_csg": local_csg,
                "cut_timber": cut_timber,
            }
            changed_keys.append(timber_key)
            remesh_metrics.append({
                "timberKey": timber_key,
                "remesh_s": remesh_s,
                "csg_depth": csg_depth,
                "triangle_count": triangle_count,
            })

            meshes.append(mesh_payload)
            seen_keys.add(timber_key)
        except Exception as exc:
            log_stderr(f"Warning: skipping geometry for {get_timber_display_name(cut_timber.timber)}: {exc}")

    accessories = list(frame.accessories) if hasattr(frame, "accessories") and frame.accessories else []
    for accessory in accessories:
        try:
            accessory_type = type(accessory).__name__
            key_base = f"accessory:{accessory_type}"

            occurrence = key_counts.get(key_base, 0)
            key_counts[key_base] = occurrence + 1
            accessory_key = f"{key_base}#{occurrence}"
            accessory_name = f"{accessory_type} {occurrence + 1}"

            local_csg = accessory.render_csg_local()

            remesh_t0 = time.monotonic()
            csg_depth = _compute_csg_depth(local_csg)
            mesh_payload = _accessory_to_triangle_mesh_payload(
                accessory,
                local_csg,
                accessory_key,
                accessory_name,
            )
            remesh_s = time.monotonic() - remesh_t0
            triangle_count = len(mesh_payload.get("indices", [])) // 3
            ss.mesh_cache[accessory_key] = {
                "mesh": mesh_payload,
            }
            changed_keys.append(accessory_key)
            remesh_metrics.append({
                "timberKey": accessory_key,
                "memberType": "accessory",
                "remesh_s": remesh_s,
                "csg_depth": csg_depth,
                "triangle_count": triangle_count,
            })

            meshes.append(mesh_payload)
            seen_keys.add(accessory_key)
        except Exception as exc:
            log_stderr(f"Warning: skipping geometry for accessory {type(accessory).__name__}: {exc}")

    removed_keys = []
    for cached_key in list(ss.mesh_cache.keys()):
        if cached_key not in seen_keys:
            removed_keys.append(cached_key)
            del ss.mesh_cache[cached_key]

    return {
        "kind": "triangle-geometry",
        "meshes": meshes,
        "changedKeys": changed_keys,
        "removedKeys": removed_keys,
        "remeshMetrics": remesh_metrics,
        "counts": {
            "totalTimbers": len(meshes),
            "changedTimbers": len(changed_keys),
            "removedTimbers": len(removed_keys),
            "totalAccessories": len(accessories),
            "totalMembers": len(meshes),
        },
    }


def serialize_frame(frame: Any) -> Dict[str, Any]:
    accessories = list(frame.accessories) if hasattr(frame, "accessories") and frame.accessories else []
    timbers = [serialize_cut_timber(cut_timber) for cut_timber in frame.cut_timbers]
    return {
        "name": frame.name if hasattr(frame, "name") else None,
        "timber_count": len(frame.cut_timbers),
        "accessories_count": len(accessories),
        "timbers": timbers,
        "accessories": [
            {
                "type": type(accessory).__name__,
            }
            for accessory in accessories
        ],
    }


def build_placeholder_geometry(frame: Any) -> Dict[str, Any]:
    # kept for reference – use build_real_geometry instead
    slot = SlotState(file_path=Path("."), module=None, frame=frame)
    dummy_state = RunnerState(slots={"main": slot}, active_slot="main")
    return build_real_geometry(dummy_state)


def _module_file_path(module: Any) -> Optional[Path]:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return None
    try:
        return Path(module_file).resolve()
    except Exception:
        return None


def _is_venv_path(path: Path) -> bool:
    path_parts = path.parts
    return ".venv" in path_parts or "venv" in path_parts


def _purge_project_modules(project_root: Path, keep_paths: set[Path], verbose: bool = False) -> None:
    """Aggressively purge all project modules from sys.modules to force clean reloads.
    
    This ensures that modified code is actually reflected when reloading, preventing
    stale cached implementations from being used due to import chain caching.
    """
    removable: list[str] = []
    removed_count = 0

    for module_name, module in list(sys.modules.items()):
        module_path = _module_file_path(module)
        if module_path is None:
            continue

        if module_path in keep_paths:
            continue

        if _is_venv_path(module_path):
            continue

        if project_root not in module_path.parents and module_path != project_root:
            continue

        removable.append(module_name)

    # Remove all project modules
    for module_name in removable:
        sys.modules.pop(module_name, None)
        removed_count += 1

    if verbose:
        if removed_count > 0:
            log_stderr(f"[reload] Purged {removed_count} project module(s): {', '.join(sorted(removable))}")
        else:
            log_stderr("[reload] No project modules to purge (first load or all already clean)")


def _looks_like_frame(value: Any) -> bool:
    return hasattr(value, "cut_timbers") and hasattr(value, "accessories")


def _looks_like_patternbook(value: Any) -> bool:
    return callable(getattr(value, "list_patterns", None)) and callable(getattr(value, "raise_pattern", None))


def _is_valid_module_part(name: str) -> bool:
    return name.isidentifier() and not name.startswith("_")


def _module_name_for_path(file_path: Path) -> str:
    if _project_root is None:
        return TARGET_MODULE_NAME

    try:
        rel = file_path.resolve().relative_to(_project_root)
    except ValueError:
        return TARGET_MODULE_NAME

    if rel.suffix != ".py":
        return TARGET_MODULE_NAME

    parts = list(rel.with_suffix("").parts)
    if not parts:
        return TARGET_MODULE_NAME
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return TARGET_MODULE_NAME
    if not all(_is_valid_module_part(part) for part in parts):
        return TARGET_MODULE_NAME
    return ".".join(parts)


def load_module_from_path(file_path: Path, verbose: bool = False) -> Any:
    """Load a Python module from file path with aggressive cache invalidation.
    
    This function ensures that:
    1. Python's import cache is invalidated
    2. All project modules are purged from sys.modules
    3. The target module and its dependencies are loaded fresh
    """
    # Step 1: Invalidate Python's built-in import caches
    importlib.invalidate_caches()
    
    # Step 2: Aggressively purge project modules
    if _project_root is not None:
        keep_paths = {Path(__file__).resolve(), file_path.resolve()}
        _purge_project_modules(_project_root, keep_paths, verbose=verbose)
    else:
        if verbose:
            log_stderr("[reload] WARNING: _project_root is None — project module purge skipped!")
            log_stderr(f"[reload]   sys.argv = {sys.argv}")
            log_stderr("[reload]   Module changes to kumiki/ will NOT be picked up until runner restarts.")

    # Step 3: Ensure target module doesn't exist in sys.modules
    module_name = _module_name_for_path(file_path)
    if TARGET_MODULE_NAME in sys.modules:
        del sys.modules[TARGET_MODULE_NAME]
    if module_name in sys.modules:
        del sys.modules[module_name]

    # Step 4: Load the module fresh
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    if module_name != TARGET_MODULE_NAME:
        sys.modules[TARGET_MODULE_NAME] = module

    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
    
    if verbose:
        log_stderr(f"[reload] Loaded module: {module_name} from {file_path}")
    
    return module


def frame_from_patternbook(patternbook: Any) -> Any:
    with contextlib.redirect_stdout(sys.stderr):
        result = patternbook.raise_patternbook_as_frame()

    return _coerce_viewable_frame(result, "patternbook")


def _coerce_viewable_frame(value: Any, name: Optional[str] = None) -> Any:
    if _looks_like_frame(value):
        return value

    from kumiki.cutcsg import CutCSG
    from kumiki.rule import Transform
    from kumiki.timber import CSGAccessory, Frame

    frame_name = name or type(value).__name__

    if isinstance(value, CutCSG):
        return Frame(
            cut_timbers=[],
            accessories=[
                CSGAccessory(
                    transform=Transform.identity(),
                    positive_csg=value,
                )
            ],
            name=frame_name,
        )

    if isinstance(value, list) and all(isinstance(item, CutCSG) for item in value):
        return Frame(
            cut_timbers=[],
            accessories=[
                CSGAccessory(
                    transform=Transform.identity(),
                    positive_csg=item,
                )
                for item in value
            ],
            name=frame_name,
        )

    raise TypeError(
        f"{frame_name} returned {type(value).__name__}, expected frame-like object or CutCSG"
    )


def resolve_frame_from_module(module: Any) -> "tuple[Any, Optional[Any]]":
    """Resolve a frame from a loaded module.

    Returns (frame, patternbook_or_None).

    The module-level ``example`` may be a Frame/PatternBook *instance* (legacy)
    or a **callable** that returns one (preferred — avoids heavy work at import
    time).
    """
    if hasattr(module, "example"):
        example = getattr(module, "example")
        # If example is a callable (function reference), invoke it now
        if callable(example):
            with contextlib.redirect_stdout(sys.stderr):
                example = example()
        if _looks_like_frame(example):
            return example, None
        try:
            return _coerce_viewable_frame(example, "example"), None
        except TypeError:
            pass
        if _looks_like_patternbook(example):
            return frame_from_patternbook(example), example

    if hasattr(module, "build_frame") and callable(module.build_frame):
        with contextlib.redirect_stdout(sys.stderr):
            frame = module.build_frame()
        return _coerce_viewable_frame(frame, "build_frame"), None

    if hasattr(module, "patternbook"):
        patternbook = getattr(module, "patternbook")
        if _looks_like_patternbook(patternbook):
            return frame_from_patternbook(patternbook), patternbook

    raise AttributeError(
        "Module must expose a module-level 'example' Frame, a 'patternbook', or a build_frame() function"
    )


def load_slot_state(file_path: str, previous_mesh_cache: Optional[Dict[str, Dict[str, Any]]] = None) -> SlotState:
    resolved_path = Path(file_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"File not found: {resolved_path}")

    module = load_module_from_path(resolved_path, verbose=True)
    frame, patternbook = resolve_frame_from_module(module)
    return SlotState(
        file_path=resolved_path,
        module=module,
        frame=frame,
        mesh_cache=previous_mesh_cache if previous_mesh_cache is not None else {},
        patternbook=patternbook,
    )


def make_ready_event(state: RunnerState) -> Dict[str, Any]:
    ss = state._active
    frame_summary = serialize_frame(ss.frame)
    return {
        "type": "ready",
        "examplePath": str(ss.file_path),
        "commands": [
            "ping", "reload_example", "get_frame", "get_geometry",
            "get_member", "find_csg_at_point",
            "load_slot", "unload_slot", "list_slots",
            "list_available_patterns", "raise_specific_pattern",
            "shutdown",
        ],
        "frame": {
            "name": frame_summary["name"],
            "timber_count": frame_summary["timber_count"],
            "accessories_count": frame_summary["accessories_count"],
        },
    }


def make_success_response(request_id: Any, command: str, result: Any) -> Dict[str, Any]:
    return {
        "id": request_id,
        "ok": True,
        "command": command,
        "result": result,
    }


def make_error_response(request_id: Any, command: str, exc: Exception) -> Dict[str, Any]:
    return {
        "id": request_id,
        "ok": False,
        "command": command,
        "error": {
            "message": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        },
    }


def get_member_result(frame: Any, member_name: str) -> Dict[str, Any]:
    for cut_timber in frame.cut_timbers:
        if get_timber_display_name(cut_timber.timber) == member_name:
            return {
                "member": serialize_cut_timber(cut_timber),
                "geometry": {
                    "kind": "placeholder-member-geometry",
                    "name": member_name,
                },
            }
    raise KeyError(f"No timber named '{member_name}' in frame")


# ===========================================================================
# CSG navigation + highlight-mesh extraction (Phase B)
# ===========================================================================

def _dot3(a: List[float], b: List[float]) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _build_inv_transform_float(transform: Any) -> Tuple[List[List[float]], List[float]]:
    """Pre-compute float data for global→local.  Returns (rot_cols, position).
    local = R^T * (global - pos) where rot_cols is the FORWARD rotation matrix."""
    M = transform.orientation.matrix
    P = transform.position
    rot = [[float(M[r, c]) for c in range(3)] for r in range(3)]
    pos = [float(P[i]) for i in range(3)]
    return rot, pos


def _inv_transform_point(rot: List[List[float]], pos: List[float], pt: List[float]) -> List[float]:
    """Apply inverse transform: local = R^T * (pt - pos)."""
    dx = pt[0] - pos[0]
    dy = pt[1] - pos[1]
    dz = pt[2] - pos[2]
    return [
        rot[0][0]*dx + rot[1][0]*dy + rot[2][0]*dz,
        rot[0][1]*dx + rot[1][1]*dy + rot[2][1]*dz,
        rot[0][2]*dx + rot[1][2]*dy + rot[2][2]*dz,
    ]


def _is_point_inside_csg_float(csg: Any, pt: List[float], eps: float = 1e-4) -> bool:
    """True if *pt* (timber-local floats) is inside *csg* (±eps tolerance)."""
    from kumiki.cutcsg import (
        HalfSpace, RectangularPrism, Cylinder, SolidUnion, Difference,
        ConvexPolygonExtrusion,
    )

    if isinstance(csg, HalfSpace):
        n = [float(csg.normal[i]) for i in range(3)]
        return _dot3(n, pt) >= float(csg.offset) - eps

    if isinstance(csg, RectangularPrism):
        rot, pos = _build_inv_transform_float(csg.transform)
        lp = _inv_transform_point(rot, pos, pt)
        hw = float(csg.size[0]) / 2.0
        hh = float(csg.size[1]) / 2.0
        z0 = float(csg.start_distance) if csg.start_distance is not None else -1e9
        z1 = float(csg.end_distance) if csg.end_distance is not None else 1e9
        return (-hw - eps <= lp[0] <= hw + eps
                and -hh - eps <= lp[1] <= hh + eps
                and z0 - eps <= lp[2] <= z1 + eps)

    if isinstance(csg, Cylinder):
        n = [float(csg.axis_direction[i]) for i in range(3)]
        c = [float(csg.position[i]) for i in range(3)]
        d = [pt[i] - c[i] for i in range(3)]
        along = _dot3(d, n)
        perp = [d[i] - along * n[i] for i in range(3)]
        dist_sq = _dot3(perp, perp)
        r = float(csg.radius)
        z0 = float(csg.start_distance) if csg.start_distance is not None else -1e9
        z1 = float(csg.end_distance) if csg.end_distance is not None else 1e9
        return dist_sq <= (r + eps) ** 2 and z0 - eps <= along <= z1 + eps

    if isinstance(csg, SolidUnion):
        return any(_is_point_inside_csg_float(ch, pt, eps) for ch in csg.children)

    if isinstance(csg, Difference):
        if not _is_point_inside_csg_float(csg.base, pt, eps):
            return False
        return not any(_is_point_inside_csg_float(sub, pt, -eps) for sub in csg.subtract)

    if isinstance(csg, ConvexPolygonExtrusion):
        # Conservative fallback — treat as always inside
        return True

    return False


def _is_point_on_csg_boundary_float(csg: Any, pt: List[float], eps: float = 1e-4) -> bool:
    """True if *pt* (timber-local floats) lies on the boundary of *csg*."""
    from kumiki.cutcsg import (
        HalfSpace, RectangularPrism, Cylinder, SolidUnion, Difference,
        ConvexPolygonExtrusion,
    )

    if isinstance(csg, HalfSpace):
        n = [float(csg.normal[i]) for i in range(3)]
        return abs(_dot3(n, pt) - float(csg.offset)) < eps

    if isinstance(csg, RectangularPrism):
        rot, pos = _build_inv_transform_float(csg.transform)
        lp = _inv_transform_point(rot, pos, pt)
        hw = float(csg.size[0]) / 2.0
        hh = float(csg.size[1]) / 2.0
        z0 = float(csg.start_distance) if csg.start_distance is not None else None
        z1 = float(csg.end_distance) if csg.end_distance is not None else None
        # Must be within bounds
        if lp[0] < -hw - eps or lp[0] > hw + eps:
            return False
        if lp[1] < -hh - eps or lp[1] > hh + eps:
            return False
        if z0 is not None and lp[2] < z0 - eps:
            return False
        if z1 is not None and lp[2] > z1 + eps:
            return False
        # Must be on at least one face
        on_x = abs(lp[0] + hw) < eps or abs(lp[0] - hw) < eps
        on_y = abs(lp[1] + hh) < eps or abs(lp[1] - hh) < eps
        on_z0 = z0 is not None and abs(lp[2] - z0) < eps
        on_z1 = z1 is not None and abs(lp[2] - z1) < eps
        return on_x or on_y or on_z0 or on_z1

    if isinstance(csg, Cylinder):
        n = [float(csg.axis_direction[i]) for i in range(3)]
        c = [float(csg.position[i]) for i in range(3)]
        d = [pt[i] - c[i] for i in range(3)]
        along = _dot3(d, n)
        perp = [d[i] - along * n[i] for i in range(3)]
        dist = _dot3(perp, perp) ** 0.5
        r = float(csg.radius)
        z0 = float(csg.start_distance) if csg.start_distance is not None else None
        z1 = float(csg.end_distance) if csg.end_distance is not None else None
        if z0 is not None and along < z0 - eps:
            return False
        if z1 is not None and along > z1 + eps:
            return False
        on_side = abs(dist - r) < eps
        on_cap_lo = z0 is not None and abs(along - z0) < eps and dist <= r + eps
        on_cap_hi = z1 is not None and abs(along - z1) < eps and dist <= r + eps
        return on_side or on_cap_lo or on_cap_hi

    if isinstance(csg, SolidUnion):
        return any(_is_point_on_csg_boundary_float(ch, pt, eps) for ch in csg.children)

    if isinstance(csg, Difference):
        on_base = _is_point_on_csg_boundary_float(csg.base, pt, eps)
        if on_base and not any(_is_point_inside_csg_float(sub, pt, -eps) for sub in csg.subtract):
            return True
        if _is_point_inside_csg_float(csg.base, pt, eps):
            return any(_is_point_on_csg_boundary_float(sub, pt, eps) for sub in csg.subtract)
        return False

    # ConvexPolygonExtrusion — not yet implemented
    return False


def _detect_face_label(csg: Any, pt: List[float], eps: float = 1e-4) -> str:
    """Determine which face of a primitive CSG node *pt* lies on."""
    from kumiki.cutcsg import HalfSpace, RectangularPrism, Cylinder

    if isinstance(csg, HalfSpace):
        return getattr(csg, "named_feature", None) or "cut_plane"

    if isinstance(csg, RectangularPrism):
        rot, pos = _build_inv_transform_float(csg.transform)
        lp = _inv_transform_point(rot, pos, pt)
        hw = float(csg.size[0]) / 2.0
        hh = float(csg.size[1]) / 2.0
        z0 = float(csg.start_distance) if csg.start_distance is not None else None
        z1 = float(csg.end_distance) if csg.end_distance is not None else None

        # Collect candidates (label, distance_from_face)
        candidates: List[Tuple[str, float]] = []
        candidates.append(("left", abs(lp[0] + hw)))
        candidates.append(("right", abs(lp[0] - hw)))
        candidates.append(("front", abs(lp[1] + hh)))
        candidates.append(("back", abs(lp[1] - hh)))
        if z0 is not None:
            candidates.append(("bottom", abs(lp[2] - z0)))
        if z1 is not None:
            candidates.append(("top", abs(lp[2] - z1)))

        within_eps = [(label, d) for label, d in candidates if d < eps]
        if within_eps:
            within_eps.sort(key=lambda c: c[1])
            return within_eps[0][0]
        return "face"

    if isinstance(csg, Cylinder):
        return "cylindrical_surface"

    return "face"


def _resolve_csg_at_path(csg: Any, path: List[str], pt: Optional[List[float]] = None, eps: float = 1e-4) -> Any:
    """Walk the CSG tree following *path* of tagged CSG nodes.

    Searches through untagged intermediate Difference/SolidUnion nodes
    transparently.  When *pt* is given and multiple children share the
    same tag, prefer the one whose boundary contains *pt*.
    """
    from kumiki.cutcsg import SolidUnion, Difference

    def _find_tagged(node: Any, tag_name: str) -> List[Any]:
        """Return all descendants of *node* with the given *tag*, searching
        through untagged compound intermediaries."""
        results: List[Any] = []
        children: List[Any] = []
        if isinstance(node, Difference):
            children = list(node.subtract)
            # Also check base
            base_tag = getattr(node.base, "tag", None)
            if base_tag == tag_name:
                results.append(node.base)
            elif isinstance(node.base, (SolidUnion, Difference)) and base_tag is None:
                results.extend(_find_tagged(node.base, tag_name))
        elif isinstance(node, SolidUnion):
            children = list(node.children)
        for ch in children:
            ch_tag = getattr(ch, "tag", None)
            if ch_tag == tag_name:
                results.append(ch)
            elif isinstance(ch, (SolidUnion, Difference)) and ch_tag is None:
                results.extend(_find_tagged(ch, tag_name))
        return results

    node = csg
    for name in path:
        candidates = _find_tagged(node, name)
        if not candidates:
            break
        if len(candidates) == 1 or pt is None:
            node = candidates[0]
        else:
            # Multiple with same name — pick the one on boundary
            picked = candidates[0]
            for c in candidates:
                if _is_point_on_csg_boundary_float(c, pt, eps):
                    picked = c
                    break
                if _is_point_inside_csg_float(c, pt, eps):
                    picked = c
            node = picked
    return node


def _navigate_csg_one_level(
    node: Any,
    pt_local: List[float],
    current_path: List[str],
    eps: float = 1e-4,
) -> Tuple[List[str], Any, Optional[str]]:
    """Navigate one level deeper into *node* based on click point.

    Returns (new_path, target_csg_to_highlight, feature_label_or_None).
    """
    from kumiki.cutcsg import SolidUnion, Difference

    if isinstance(node, Difference):
        # Check which subtract child the point lies on
        for sub in node.subtract:
            if _is_point_on_csg_boundary_float(sub, pt_local, eps):
                sub_tag = getattr(sub, "tag", None)
                if sub_tag:
                    return (current_path + [sub_tag], sub, None)
                # Unnamed compound → drill through transparently
                if isinstance(sub, (SolidUnion, Difference)):
                    return _navigate_csg_one_level(sub, pt_local, current_path, eps)
                return (current_path, sub, _detect_face_label(sub, pt_local, eps))
        # Point is on the base surface
        base_tag = getattr(node.base, "tag", None)
        if base_tag:
            return (current_path + [base_tag], node.base, None)
        if isinstance(node.base, (SolidUnion, Difference)):
            return _navigate_csg_one_level(node.base, pt_local, current_path, eps)
        return (current_path, node.base, _detect_face_label(node.base, pt_local, eps))

    if isinstance(node, SolidUnion):
        for ch in node.children:
            if _is_point_on_csg_boundary_float(ch, pt_local, eps):
                ch_tag = getattr(ch, "tag", None)
                if ch_tag:
                    return (current_path + [ch_tag], ch, None)
                # Unnamed compound → drill through transparently
                if isinstance(ch, (SolidUnion, Difference)):
                    return _navigate_csg_one_level(ch, pt_local, current_path, eps)
                return (current_path, ch, _detect_face_label(ch, pt_local, eps))
        # Couldn't match a specific child — report face of whole union
        return (current_path, node, "face")

    # Leaf primitive — report face
    return (current_path, node, _detect_face_label(node, pt_local, eps))


def _navigate_csg_to_leaf(
    csg: Any,
    pt_local: List[float],
    eps: float = 1e-4,
) -> Tuple[List[str], Any, Optional[str]]:
    """Ctrl+click: traverse from root to deepest named node, then report face."""
    from kumiki.cutcsg import SolidUnion, Difference

    path: List[str] = []
    node = csg
    while True:
        new_path, target, label = _navigate_csg_one_level(node, pt_local, path, eps)
        if label is not None:
            # Reached a leaf
            return (new_path, target, label)
        if new_path == path:
            # No progress — shouldn't happen but guard against infinite loop
            return (path, node, "face")
        path = new_path
        node = target


def _extract_highlight_mesh(
    mesh_vertices: List[float],
    mesh_indices: List[int],
    target_csg: Any,
    timber_rot: List[List[float]],
    timber_pos: List[float],
    eps: float = 1e-4,
    root_csg: Optional[Any] = None,
    selected_path: Optional[List[str]] = None,
    selected_ref: Optional[Any] = None,
    feature_label: Optional[str] = None,
) -> Tuple[List[float], List[int], int, int]:
    """Extract triangles belonging to *target_csg* from the rendered mesh.

    *mesh_vertices* / *mesh_indices* are in global coords (flat lists).
    Returns (highlight_vertices, highlight_indices, matched_tris, total_tris).
    """
    total_tris = len(mesh_indices) // 3
    out_verts: List[float] = []
    out_idx: List[int] = []
    matched = 0

    enforce_owner = (
        root_csg is not None
        and selected_ref is not None
        and selected_path is not None
        and len(selected_path) > 0
    )

    for tri in range(total_tris):
        i0 = mesh_indices[tri * 3]
        i1 = mesh_indices[tri * 3 + 1]
        i2 = mesh_indices[tri * 3 + 2]
        # Centroid in global
        cx = (mesh_vertices[i0*3] + mesh_vertices[i1*3] + mesh_vertices[i2*3]) / 3.0
        cy = (mesh_vertices[i0*3+1] + mesh_vertices[i1*3+1] + mesh_vertices[i2*3+1]) / 3.0
        cz = (mesh_vertices[i0*3+2] + mesh_vertices[i1*3+2] + mesh_vertices[i2*3+2]) / 3.0
        # Convert centroid to timber-local
        local_c = _inv_transform_point(timber_rot, timber_pos, [cx, cy, cz])
        if _is_point_on_csg_boundary_float(target_csg, local_c, eps):
            if enforce_owner:
                owner = _resolve_csg_at_path(root_csg, selected_path, local_c, eps)
                if owner is not selected_ref:
                    continue
            if feature_label is not None:
                tri_face_label = _detect_face_label(target_csg, local_c, eps)
                if tri_face_label != feature_label:
                    continue
            base = len(out_verts) // 3
            out_verts.extend(mesh_vertices[i0*3 : i0*3+3])
            out_verts.extend(mesh_vertices[i1*3 : i1*3+3])
            out_verts.extend(mesh_vertices[i2*3 : i2*3+3])
            out_idx.extend([base, base+1, base+2])
            matched += 1

    return out_verts, out_idx, matched, total_tris


def _debug_prism_distances(prism: Any, pt: List[float], eps: float, indent: int = 4) -> None:
    """Log detailed distances from point to each face of a RectangularPrism."""
    rot, pos = _build_inv_transform_float(prism.transform)
    lp = _inv_transform_point(rot, pos, pt)
    hw = float(prism.size[0]) / 2.0
    hh = float(prism.size[1]) / 2.0
    z0 = float(prism.start_distance) if prism.start_distance is not None else None
    z1 = float(prism.end_distance) if prism.end_distance is not None else None
    pad = " " * indent
    log_stderr(f"[csg-nav] {pad}prism local_pt={[round(v,6) for v in lp]}, hw={hw:.4f}, hh={hh:.4f}, z0={z0}, z1={z1}")
    log_stderr(f"[csg-nav] {pad}  dist to -X: {abs(lp[0]+hw):.6f}, +X: {abs(lp[0]-hw):.6f}")
    log_stderr(f"[csg-nav] {pad}  dist to -Y: {abs(lp[1]+hh):.6f}, +Y: {abs(lp[1]-hh):.6f}")
    if z0 is not None:
        log_stderr(f"[csg-nav] {pad}  dist to z0: {abs(lp[2]-z0):.6f}")
    else:
        log_stderr(f"[csg-nav] {pad}  z0=None (infinite)")
    if z1 is not None:
        log_stderr(f"[csg-nav] {pad}  dist to z1: {abs(lp[2]-z1):.6f}")
    else:
        log_stderr(f"[csg-nav] {pad}  z1=None (infinite)")


def _debug_difference_distances(diff: Any, pt: List[float], eps: float, indent: int = 4) -> None:
    """Log detailed distances for a Difference CSG."""
    from kumiki.cutcsg import HalfSpace as _HS, RectangularPrism as _RP
    pad = " " * indent
    base = diff.base
    if isinstance(base, _HS):
        n = [float(base.normal[k]) for k in range(3)]
        dot_val = _dot3(n, pt)
        offset = float(base.offset)
        dist = abs(dot_val - offset)
        inside = dot_val >= offset
        log_stderr(f"[csg-nav] {pad}Diff.base HalfSpace: dot={dot_val:.6f}, offset={offset:.6f}, dist={dist:.6f}, inside={inside} (eps={eps})")
    elif isinstance(base, _RP):
        log_stderr(f"[csg-nav] {pad}Diff.base RectangularPrism:")
        _debug_prism_distances(base, pt, eps, indent + 2)
    for i, sub in enumerate(diff.subtract):
        if isinstance(sub, _HS):
            n = [float(sub.normal[k]) for k in range(3)]
            dot_val = _dot3(n, pt)
            offset = float(sub.offset)
            dist = abs(dot_val - offset)
            log_stderr(f"[csg-nav] {pad}Diff.sub[{i}] HalfSpace: dot={dot_val:.6f}, offset={offset:.6f}, dist={dist:.6f}")
        elif isinstance(sub, _RP):
            log_stderr(f"[csg-nav] {pad}Diff.sub[{i}] RectangularPrism:")
            _debug_prism_distances(sub, pt, eps, indent + 2)


def _handle_find_csg_at_point(state: RunnerState, payload: Dict[str, Any], slot_state: Optional['SlotState'] = None) -> Dict[str, Any]:
    """Process a find_csg_at_point request and return the result dict."""
    ss = slot_state if slot_state is not None else state._active
    member_key = payload.get("memberKey")
    point = payload.get("point")
    current_path = payload.get("currentPath") or []
    ctrl_click = payload.get("ctrlClick", False)
    eps = 5e-4  # generous epsilon for raycast-based click points

    if not isinstance(member_key, str) or member_key not in ss.mesh_cache:
        raise ValueError(f"Unknown memberKey: {member_key}")
    if not isinstance(point, list) or len(point) != 3:
        raise ValueError("point must be [x, y, z]")

    cached = ss.mesh_cache[member_key]
    local_csg = cached.get("local_csg")
    cut_timber = cached.get("cut_timber")
    mesh = cached.get("mesh")

    if local_csg is None or cut_timber is None or mesh is None:
        raise ValueError(f"No CSG data cached for {member_key}")

    timber = cut_timber.timber
    timber_rot, timber_pos = _build_inv_transform_float(timber.transform)

    # Convert global click point to timber-local
    pt_local = _inv_transform_point(timber_rot, timber_pos, [float(p) for p in point])

    t0 = time.monotonic()

    # --- Debug: describe the CSG tree ---
    def _csg_debug_label(c: Any) -> str:
        tag = getattr(c, "tag", None)
        ctype = type(c).__name__
        label = f"{ctype}"
        if tag:
            label += f'(tag="{tag}")'
        return label

    def _csg_tree_debug(c: Any, depth: int = 0) -> List[str]:
        from kumiki.cutcsg import SolidUnion, Difference
        indent = "  " * depth
        lines = [f"{indent}{_csg_debug_label(c)}"]
        if isinstance(c, Difference):
            lines.append(f"{indent}  base: {_csg_debug_label(c.base)}")
            for i, s in enumerate(c.subtract):
                lines.append(f"{indent}  subtract[{i}]:")
                lines.extend(_csg_tree_debug(s, depth + 2))
        elif isinstance(c, SolidUnion):
            for i, ch in enumerate(c.children):
                lines.append(f"{indent}  child[{i}]:")
                lines.extend(_csg_tree_debug(ch, depth + 2))
        return lines

    log_stderr(f"[csg-nav] === find_csg_at_point ===")
    log_stderr(f"[csg-nav] memberKey={member_key}, ctrlClick={ctrl_click}")
    log_stderr(f"[csg-nav] global point={[round(float(p), 4) for p in point]}")
    log_stderr(f"[csg-nav] local point={[round(v, 4) for v in pt_local]}")
    log_stderr(f"[csg-nav] currentPath={current_path}")
    log_stderr(f"[csg-nav] CSG tree:")
    for line in _csg_tree_debug(local_csg):
        log_stderr(f"[csg-nav]   {line}")

    if ctrl_click:
        new_path, target_csg, feature_label = _navigate_csg_to_leaf(local_csg, pt_local, eps)
    else:
        if current_path:
            node = _resolve_csg_at_path(local_csg, current_path, pt_local, eps)
            on_boundary = _is_point_on_csg_boundary_float(node, pt_local, eps)
            log_stderr(f"[csg-nav] resolved node at path: {_csg_debug_label(node)}, point on boundary={on_boundary}")
            if not on_boundary:
                node = local_csg
                current_path = []
                log_stderr(f"[csg-nav] popped back to root")
        else:
            node = local_csg
        log_stderr(f"[csg-nav] navigating from: {_csg_debug_label(node)}")

        # Debug: test each subtract child boundary for Difference nodes
        from kumiki.cutcsg import Difference as _Diff, SolidUnion as _SU, HalfSpace as _HS, RectangularPrism as _RP
        if isinstance(node, _Diff):
            for i, sub in enumerate(node.subtract):
                on_b = _is_point_on_csg_boundary_float(sub, pt_local, eps)
                log_stderr(f"[csg-nav]   subtract[{i}] {_csg_debug_label(sub)} boundary={on_b}")
                if isinstance(sub, _SU):
                    for j, ch in enumerate(sub.children):
                        on_ch = _is_point_on_csg_boundary_float(ch, pt_local, eps)
                        log_stderr(f"[csg-nav]     child[{j}] {_csg_debug_label(ch)} boundary={on_ch}")
                        # Deep debug: show distances for primitives inside this child
                        if isinstance(ch, _Diff):
                            _debug_difference_distances(ch, pt_local, eps, indent=6)
                        elif isinstance(ch, _HS):
                            n = [float(ch.normal[k]) for k in range(3)]
                            dist = abs(_dot3(n, pt_local) - float(ch.offset))
                            log_stderr(f"[csg-nav]       HalfSpace dist={dist:.6f} (eps={eps}), n={[round(v,4) for v in n]}, offset={float(ch.offset):.4f}")
            on_base = _is_point_on_csg_boundary_float(node.base, pt_local, eps)
            log_stderr(f"[csg-nav]   base {_csg_debug_label(node.base)} boundary={on_base}")
            if isinstance(node.base, _RP):
                _debug_prism_distances(node.base, pt_local, eps, indent=4)

        new_path, target_csg, feature_label = _navigate_csg_one_level(
            node, pt_local, current_path, eps,
        )

    log_stderr(f"[csg-nav] result: path={new_path}, featureLabel={feature_label}, target={_csg_debug_label(target_csg)}")

    parent_csg = None
    if new_path:
        parent_csg = _resolve_csg_at_path(local_csg, new_path, pt_local, eps)

    # Extract highlight mesh for the selected target
    hl_verts, hl_idx, matched, total = _extract_highlight_mesh(
        mesh["vertices"],
        mesh["indices"],
        target_csg,
        timber_rot,
        timber_pos,
        eps,
        root_csg=local_csg,
        selected_path=new_path,
        selected_ref=parent_csg if feature_label is not None else target_csg,
        feature_label=feature_label,
    )
    log_stderr(f"[csg-nav] highlight mesh: {matched}/{total} triangles matched")

    # When a feature (face) is selected, also extract the parent tagged CSG mesh
    # so the viewer can render the parent dimmer and the feature brighter.
    parent_hl = None
    if feature_label is not None and parent_csg is not None:
        p_verts, p_idx, _, _ = _extract_highlight_mesh(
            mesh["vertices"],
            mesh["indices"],
            parent_csg,
            timber_rot,
            timber_pos,
            eps,
            root_csg=local_csg,
            selected_path=new_path,
            selected_ref=parent_csg,
        )
        if p_verts:
            parent_hl = {"vertices": p_verts, "indices": p_idx}

    mesh_walk_ms = (time.monotonic() - t0) * 1000.0

    result: Dict[str, Any] = {
        "path": new_path,
        "featureLabel": feature_label,
        "highlightMesh": {
            "vertices": hl_verts,
            "indices": hl_idx,
        },
        "stats": {
            "meshWalkMs": round(mesh_walk_ms, 2),
            "trianglesMatched": matched,
            "totalTriangles": total,
        },
    }
    if parent_hl is not None:
        result["parentHighlightMesh"] = parent_hl
    return result


def _resolve_slot(state: RunnerState, payload: Dict[str, Any]) -> SlotState:
    """Return the SlotState targeted by the request payload (defaults to active_slot)."""
    slot_name = payload.get("slot", state.active_slot)
    return state.get_slot(slot_name)


def _resolve_slot_name(state: RunnerState, payload: Dict[str, Any]) -> str:
    return payload.get("slot", state.active_slot)


# ---------------------------------------------------------------------------
# Pattern discovery
# ---------------------------------------------------------------------------

_patterns_cache: Optional[Dict[str, Any]] = None


def _list_available_patterns(force_rescan: bool = False) -> Dict[str, Any]:
    """Scan shipped and local pattern folders and return pattern metadata.

    Results are cached after the first scan. Pass *force_rescan=True* (or
    send ``"rescan": true`` in the command payload) to re-import everything.
    """
    global _patterns_cache
    if _patterns_cache is not None and not force_rescan:
        return _patterns_cache

    t0 = time.monotonic()
    from kumiki.librarian import scan_library_folder

    sources: List[Dict[str, Any]] = []

    # Shipped patterns — bundled inside the kumiki package as kumiki/patterns/
    # (pip-installed) or at the sibling patterns/ folder in a dev checkout.
    try:
        import kumiki
        kumiki_dir = Path(kumiki.__file__).resolve().parent
        # Installed wheel: patterns are inside the package directory.
        # Dev checkout fallback: patterns/ sits next to the kumiki/ folder.
        shipped_patterns_dir = kumiki_dir / "patterns"
        if not shipped_patterns_dir.is_dir():
            shipped_patterns_dir = kumiki_dir.parent / "patterns"
        if shipped_patterns_dir.is_dir():
            with contextlib.redirect_stdout(sys.stderr):
                scan = scan_library_folder(str(shipped_patterns_dir))
            patterns_list = []
            for mod_record in scan.modules:
                if mod_record.patternbook is not None:
                    for name in mod_record.patternbook.list_patterns():
                        groups = []
                        for g in mod_record.patternbook.list_groups():
                            if name in mod_record.patternbook.get_patterns_in_group(g):
                                groups.append(g)
                        patterns_list.append({
                            "name": name,
                            "groups": groups,
                            "source_file": str(shipped_patterns_dir / mod_record.relative_path),
                        })
            if patterns_list:
                sources.append({"source": "shipped", "folder": str(shipped_patterns_dir), "patterns": patterns_list})
    except Exception as exc:
        log_stderr(f"[patterns] Error scanning shipped patterns: {exc}")

    # Local project patterns
    if _project_root is not None:
        local_patterns_dir = _project_root / "patterns"
        if local_patterns_dir.is_dir():
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    scan = scan_library_folder(str(local_patterns_dir))
                patterns_list = []
                for mod_record in scan.modules:
                    if mod_record.patternbook is not None:
                        for name in mod_record.patternbook.list_patterns():
                            groups = []
                            for g in mod_record.patternbook.list_groups():
                                if name in mod_record.patternbook.get_patterns_in_group(g):
                                    groups.append(g)
                            patterns_list.append({
                                "name": name,
                                "groups": groups,
                                "source_file": str(local_patterns_dir / mod_record.relative_path),
                            })
                if patterns_list:
                    sources.append({"source": "local", "folder": str(local_patterns_dir), "patterns": patterns_list})
            except Exception as exc:
                log_stderr(f"[patterns] Error scanning local patterns: {exc}")

    scan_s = time.monotonic() - t0
    total_patterns = sum(len(s["patterns"]) for s in sources)
    log_stderr(f"[patterns] Scanned {total_patterns} patterns in {scan_s:.2f}s")
    result = {"sources": sources, "scan_s": scan_s}
    _patterns_cache = result
    return result


def _raise_specific_pattern(source_file: str, pattern_name: str) -> "tuple[SlotState, Dict[str, Any]]":
    """Load a specific pattern from a source file and return (SlotState, result_dict)."""
    resolved = Path(source_file).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Pattern source file not found: {resolved}")

    t0 = time.monotonic()
    module = load_module_from_path(resolved, verbose=True)

    # Find patternbook
    patternbook = None
    if hasattr(module, "patternbook") and _looks_like_patternbook(module.patternbook):
        patternbook = module.patternbook
    elif hasattr(module, "example"):
        candidate = getattr(module, "example")
        # Resolve callable example references
        if callable(candidate) and not _looks_like_patternbook(candidate):
            with contextlib.redirect_stdout(sys.stderr):
                candidate = candidate()
        if _looks_like_patternbook(candidate):
            patternbook = candidate
    else:
        # Try factory functions
        for attr_name in dir(module):
            if attr_name.startswith("create_") and attr_name.endswith("_patternbook"):
                factory = getattr(module, attr_name)
                if callable(factory):
                    result = factory()
                    if _looks_like_patternbook(result):
                        patternbook = result
                        break

    if patternbook is None:
        raise ValueError(f"No patternbook found in {source_file}")

    available = patternbook.list_patterns()
    if pattern_name not in available:
        raise ValueError(f"Pattern '{pattern_name}' not found. Available: {available}")

    with contextlib.redirect_stdout(sys.stderr):
        pattern_result = patternbook.raise_pattern(pattern_name)
    frame = _coerce_viewable_frame(pattern_result, f"Pattern '{pattern_name}'")

    reload_s = time.monotonic() - t0
    slot = SlotState(
        file_path=resolved,
        module=module,
        frame=frame,
        mesh_cache={},
        patternbook=patternbook,
        single_pattern_name=pattern_name,
    )
    result = {
        "examplePath": str(resolved),
        "patternName": pattern_name,
        "frame": {
            "name": frame.name if hasattr(frame, "name") else pattern_name,
            "timber_count": len(frame.cut_timbers),
            "accessories_count": len(frame.accessories) if hasattr(frame, "accessories") else 0,
        },
        "profiling": {"reload_s": reload_s},
    }
    return slot, result


def handle_request(state: RunnerState, request: Dict[str, Any]) -> tuple[RunnerState, Dict[str, Any], bool]:
    request_id = request.get("id")
    command = request.get("command")
    payload = request.get("payload") or {}

    if not isinstance(command, str):
        raise ValueError("Request must include a string 'command'")

    if command == "ping":
        return state, make_success_response(request_id, command, {"pong": True}), False

    if command == "reload_example":
        slot_name = _resolve_slot_name(state, payload)
        old_slot = state.slots.get(slot_name)
        next_path = payload.get("filePath", str(state.get_slot(slot_name).file_path))
        old_cache = old_slot.mesh_cache if old_slot else {}
        t0 = time.monotonic()

        # If this slot was loaded for a single pattern, re-raise just that pattern
        if old_slot and old_slot.single_pattern_name:
            next_slot, _ = _raise_specific_pattern(next_path, old_slot.single_pattern_name)
            next_slot.mesh_cache = old_cache
        else:
            next_slot = load_slot_state(next_path, old_cache)

        reload_s = time.monotonic() - t0
        state.slots[slot_name] = next_slot
        frame_name = next_slot.frame.name if hasattr(next_slot.frame, "name") else "?"
        log_stderr(f"[reload] [{slot_name}] Frame loaded: '{frame_name}', {len(next_slot.frame.cut_timbers)} timbers")
        result = {
            "examplePath": str(next_slot.file_path),
            "frame": {
                "name": next_slot.frame.name,
                "timber_count": len(next_slot.frame.cut_timbers),
                "accessories_count": len(next_slot.frame.accessories),
            },
            "profiling": {"reload_s": reload_s},
        }
        return state, make_success_response(request_id, command, result), False

    if command == "get_frame":
        ss = _resolve_slot(state, payload)
        return state, make_success_response(request_id, command, serialize_frame(ss.frame)), False

    if command == "get_geometry":
        ss = _resolve_slot(state, payload)
        t0 = time.monotonic()
        geometry = build_real_geometry(state, ss)
        geometry_s = time.monotonic() - t0
        geometry["profiling"] = {"geometry_s": geometry_s}
        return state, make_success_response(request_id, command, geometry), False

    if command == "get_member":
        ss = _resolve_slot(state, payload)
        member_name = payload.get("name")
        if not isinstance(member_name, str) or not member_name:
            raise ValueError("get_member requires payload.name")
        return state, make_success_response(request_id, command, get_member_result(ss.frame, member_name)), False

    if command == "find_csg_at_point":
        ss = _resolve_slot(state, payload)
        result = _handle_find_csg_at_point(state, payload, ss)
        return state, make_success_response(request_id, command, result), False

    # --- Slot management ---

    if command == "load_slot":
        slot_name = payload.get("slot")
        file_path = payload.get("filePath")
        if not isinstance(slot_name, str) or not slot_name:
            raise ValueError("load_slot requires payload.slot")
        if not isinstance(file_path, str) or not file_path:
            raise ValueError("load_slot requires payload.filePath")
        t0 = time.monotonic()
        new_slot = load_slot_state(file_path)
        reload_s = time.monotonic() - t0
        state.slots[slot_name] = new_slot
        log_stderr(f"[slot] Loaded slot '{slot_name}' from {file_path}")
        result = {
            "slot": slot_name,
            "examplePath": str(new_slot.file_path),
            "frame": {
                "name": new_slot.frame.name if hasattr(new_slot.frame, "name") else None,
                "timber_count": len(new_slot.frame.cut_timbers),
                "accessories_count": len(new_slot.frame.accessories) if hasattr(new_slot.frame, "accessories") else 0,
            },
            "profiling": {"reload_s": reload_s},
        }
        return state, make_success_response(request_id, command, result), False

    if command == "unload_slot":
        slot_name = payload.get("slot")
        if not isinstance(slot_name, str) or not slot_name:
            raise ValueError("unload_slot requires payload.slot")
        if slot_name == state.active_slot:
            raise ValueError(f"Cannot unload the active slot '{slot_name}'")
        removed = slot_name in state.slots
        if removed:
            del state.slots[slot_name]
            log_stderr(f"[slot] Unloaded slot '{slot_name}'")
        return state, make_success_response(request_id, command, {"slot": slot_name, "removed": removed}), False

    if command == "list_slots":
        slot_info = {}
        for name, ss in state.slots.items():
            slot_info[name] = {
                "filePath": str(ss.file_path),
                "frameName": ss.frame.name if hasattr(ss.frame, "name") else None,
                "timberCount": len(ss.frame.cut_timbers),
            }
        return state, make_success_response(request_id, command, {
            "slots": slot_info,
            "activeSlot": state.active_slot,
        }), False

    # --- Pattern discovery ---

    if command == "list_available_patterns":
        force_rescan = bool(payload.get("rescan", False))
        result = _list_available_patterns(force_rescan=force_rescan)
        return state, make_success_response(request_id, command, result), False

    if command == "raise_specific_pattern":
        slot_name = payload.get("slot")
        source_file = payload.get("sourceFile")
        pattern_name = payload.get("patternName")
        if not isinstance(slot_name, str) or not slot_name:
            raise ValueError("raise_specific_pattern requires payload.slot")
        if not isinstance(source_file, str) or not source_file:
            raise ValueError("raise_specific_pattern requires payload.sourceFile")
        if not isinstance(pattern_name, str) or not pattern_name:
            raise ValueError("raise_specific_pattern requires payload.patternName")
        new_slot, result = _raise_specific_pattern(source_file, pattern_name)
        state.slots[slot_name] = new_slot
        result["slot"] = slot_name
        log_stderr(f"[slot] Raised pattern '{pattern_name}' in slot '{slot_name}'")
        return state, make_success_response(request_id, command, result), False

    if command == "shutdown":
        return state, make_success_response(request_id, command, {"shutting_down": True}), True

    raise ValueError(f"Unknown command: {command}")


def main() -> None:
    if len(sys.argv) < 2:
        emit_message({
            "type": "fatal_error",
            "error": "No example file path provided",
        })
        sys.exit(1)

    target_path = sys.argv[1]

    log_stderr(f"[startup] runner.py ready. executable={sys.executable}")
    log_stderr(f"[startup] _project_root={_project_root}")
    log_stderr(f"[startup] target={target_path}")

    try:
        initial_slot = load_slot_state(target_path)
        state = RunnerState(slots={"main": initial_slot}, active_slot="main")
    except Exception as exc:
        emit_message({
            "type": "fatal_error",
            "error": {
                "message": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            },
        })
        sys.exit(1)

    emit_message(make_ready_event(state))

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        request_id = None
        command = "unknown"
        try:
            request = json.loads(line)
            request_id = request.get("id")
            command = request.get("command", "unknown")
            state, response, should_exit = handle_request(state, request)
            emit_message(response)
            if should_exit:
                return
        except Exception as exc:
            emit_message(make_error_response(request_id, command, exc))


if __name__ == "__main__":
    main()
