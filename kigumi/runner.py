#!/usr/bin/env python3
"""
Persistent stdio runner for the Kigumi VS Code extension.

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
from typing import Any, Dict, Mapping, Optional, List, Tuple

from kumiki.librarian import (
    RenderParameterDescriptor,
    resolve_callable_render_parameters,
    serialize_render_parameter_value,
)


def _find_project_root_from_argv() -> "Tuple[Path | None, bool]":
    """Resolve project root and mode.

    Priority:
    1) argv[2] explicit project root from extension (if provided)
    2) walk up from argv[1] target file path

    Returns (root_path, is_local_dev) or (None, False).
    """
    explicit_root: Path | None = None
    if len(sys.argv) >= 3 and sys.argv[2]:
        candidate_root = Path(sys.argv[2]).resolve()
        if candidate_root.exists():
            explicit_root = candidate_root

    if explicit_root is not None:
        if (explicit_root / "kumiki").is_dir() and (explicit_root / "pyproject.toml").is_file():
            return explicit_root, True
        return explicit_root, False

    if len(sys.argv) < 2:
        return None, False

    candidate = Path(sys.argv[1]).resolve().parent
    while True:
        # Local-dev should only match an actual kumiki repo root.
        if (candidate / "kumiki").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate, True
        if (candidate / ".kigumi" / "kumiki.yaml").is_file():
            return candidate, False
        if (candidate / ".kigumi.yaml").is_file():
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
os.environ["KIGUMI_VIEWER_MILESTONES"] = "1"

TARGET_MODULE_NAME = "_kigumi_viewer_target"


@dataclass
class SlotState:
    """State for a single named viewer slot (e.g. 'main' or a pattern)."""
    file_path: Path
    module: Any
    frame: Any
    mesh_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    patternbook: Optional[Any] = None
    single_pattern_name: Optional[str] = None
    render_parameter_schema: List[RenderParameterDescriptor] = field(default_factory=list)
    applied_render_parameters: Dict[str, Any] = field(default_factory=dict)


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
    if hasattr(timber, "ticket") and hasattr(timber.ticket, "path"):
        return timber.ticket.path
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


def _build_perfect_timber_within_csg_local(cut_timber: Any) -> Any:
    """Build a perfect-timber-within (rectangular prism) CSG with the same cuts applied.

    This mirrors CutTimber.render_timber_with_cuts_csg_local, but substitutes a
    plain rectangular prism (sized to the timber's perfect bounding box) for the
    timber's actual base CSG. Used to render a "perfect timber within" preview of
    non-perfect timbers (e.g. RoundTimber, RegularPolygonTimber, MeshTimber).
    """
    from kumiki.cutcsg import Difference
    from kumiki.timber import _create_extended_rectangular_prism

    timber = cut_timber.timber
    has_bottom_cut = any(c.get_maybe_bottom_end_cut() is not None for c in cut_timber.cuts)
    has_top_cut = any(c.get_maybe_top_end_cut() is not None for c in cut_timber.cuts)

    base_prism = _create_extended_rectangular_prism(
        size=timber.get_perfect_size(),
        length=timber.length,
        extend_bot=has_bottom_cut,
        extend_top=has_top_cut,
    )

    if not cut_timber.cuts:
        return base_prism
    negs = [c.get_negative_csg_local() for c in cut_timber.cuts]
    return Difference(base_prism, negs)


def _triangulate_local_csg(cut_timber: Any, local_csg: Any) -> Dict[str, Any]:
    """Triangulate a local CSG in the timber's frame, returning flat vertex/index lists."""
    from kumiki.cutcsg import adopt_csg
    from kumiki.rule import Transform
    from kumiki.triangles import triangulate_cutcsg

    global_csg = adopt_csg(cut_timber.timber.transform, Transform.identity(), local_csg)
    triangle_mesh = triangulate_cutcsg(global_csg).mesh

    if triangle_mesh.vertices.size == 0 or triangle_mesh.faces.size == 0:
        raise RuntimeError("triangulate_cutcsg produced empty mesh")

    bounds = triangle_mesh.bounds
    if bounds is None:
        raise RuntimeError("triangulate_cutcsg produced mesh without bounds")

    return {
        "vertices": triangle_mesh.vertices.reshape(-1).tolist(),
        "indices": triangle_mesh.faces.reshape(-1).tolist(),
        "bounds": bounds,
    }


def _base_member_payload(
    *,
    name: str,
    member_type: str,
    member_key: str,
    kumiki_id: int,
    tags: Any,
    vertices: Any,
    indices: Any,
    prism_length: Any,
    prism_width: Any,
    prism_height: Any,
    perfect_width: Any,
    perfect_height: Any,
    nominal_width: Any,
    nominal_height: Any,
) -> Dict[str, Any]:
    """Common member-mesh payload shared by every geometry serializer.

    Callers add type-specific extras (csg counts, timber class, fallback
    markers, perfect-within meshes) to the returned dict.
    """
    return {
        "name": name,
        "memberName": name,
        "memberType": member_type,
        "memberKey": member_key,
        "timberKey": member_key,
        "kumikiId": kumiki_id,
        "tags": tags,
        "vertices": vertices,
        "indices": indices,
        "prism_length": round(float(prism_length), 6),
        "prism_width": round(float(prism_width), 6),
        "prism_height": round(float(prism_height), 6),
        "perfect_width": round(float(perfect_width), 6),
        "perfect_height": round(float(perfect_height), 6),
        "nominal_width": round(float(nominal_width), 6),
        "nominal_height": round(float(nominal_height), 6),
    }


def _cut_timber_to_triangle_mesh_payload(
    cut_timber: Any,
    local_csg: Any,
    timber_key: str,
) -> Dict[str, Any]:
    actual = _triangulate_local_csg(cut_timber, local_csg)
    vertices = actual["vertices"]
    indices = actual["indices"]
    dims = actual["bounds"][1] - actual["bounds"][0]

    timber = cut_timber.timber
    timber_tags = _normalize_ticket_tags(getattr(timber, "ticket", None))
    perfect_size = timber.get_perfect_size()
    nominal_size = timber.get_nominal_size()
    csg_nodes, csg_features = _count_csg_nodes_and_features(local_csg)
    timber_kumiki_id = int(timber.ticket.kumiki_id)
    timber_class = type(timber).__name__
    is_perfect = bool(timber.is_perfect_timber())
    # is_perfect_timber() only checks nominal half-sizes vs perfect size; it
    # does not detect actual non-rectangular geometry (e.g. RoundTimber has
    # is_perfect_timber()==True when diameter==size, but its actual CSG is a
    # cylinder, not a rectangular prism). Use class identity to determine
    # whether the actual geometry differs from the perfect timber within.
    non_rectangular_classes = ('RoundTimber', 'MeshTimber', 'RegularPolygonTimber')
    has_non_rectangular_actual = timber_class in non_rectangular_classes

    # Top-level vertices/indices remain the actual-geometry mesh for
    # backwards compatibility with viewers that pre-date the dual mesh.
    payload: Dict[str, Any] = _base_member_payload(
        name=get_timber_display_name(timber),
        member_type="timber",
        member_key=timber_key,
        kumiki_id=timber_kumiki_id,
        tags=timber_tags,
        vertices=vertices,
        indices=indices,
        prism_length=getattr(timber, "length", dims[2]),
        prism_width=getattr(timber, "size", [dims[0], dims[1]])[0],
        prism_height=getattr(timber, "size", [dims[0], dims[1]])[1],
        perfect_width=perfect_size[0],
        perfect_height=perfect_size[1],
        nominal_width=nominal_size[0],
        nominal_height=nominal_size[1],
    )
    payload.update({
        "csg_nodes": csg_nodes,
        "csg_features": csg_features,
        "timberClass": timber_class,
        "isPerfectTimber": is_perfect,
    })

    # For non-rectangular-actual timbers, also triangulate the perfect-AABB CSG
    # so the viewer can swap meshes locally without round-tripping to Python.
    if has_non_rectangular_actual:
        try:
            perfect_csg = _build_perfect_timber_within_csg_local(cut_timber)
            perfect = _triangulate_local_csg(cut_timber, perfect_csg)
            payload["perfectTimberWithinVertices"] = perfect["vertices"]
            payload["perfectTimberWithinIndices"] = perfect["indices"]
            payload["hasActualGeometryDifferentFromPerfect"] = True
        except Exception as exc:  # noqa: BLE001 — best-effort optional payload
            log_stderr(
                f"Warning: failed to build perfect-AABB mesh for "
                f"{get_timber_display_name(timber)}: {exc}"
            )
            payload["hasActualGeometryDifferentFromPerfect"] = False
    else:
        payload["hasActualGeometryDifferentFromPerfect"] = False

    return payload


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

    accessory_kumiki_id = int(accessory.ticket.kumiki_id) if getattr(accessory, "ticket", None) is not None else 0
    accessory_tags = _normalize_ticket_tags(getattr(accessory, "ticket", None))
    return _base_member_payload(
        name=accessory_name,
        member_type="accessory",
        member_key=accessory_key,
        kumiki_id=accessory_kumiki_id,
        tags=accessory_tags,
        vertices=vertices,
        indices=indices,
        prism_length=dims[2],
        prism_width=dims[0],
        prism_height=dims[1],
        perfect_width=dims[0],
        perfect_height=dims[1],
        nominal_width=dims[0],
        nominal_height=dims[1],
    )


def _cut_timber_to_bbox_mesh_payload(
    cut_timber: Any,
    timber_key: str,
) -> Dict[str, Any]:
    """Fallback mesh payload based on a cut timber's oriented bounding prism.

    This path avoids trimesh boolean triangulation and keeps rendering usable
    when optional backend dependencies are unavailable.

    haven't tried this, not sure how well it works, I guess the bbox might not be oriented correctly in this version...
    """
    timber = cut_timber.timber
    timber_tags = _normalize_ticket_tags(getattr(timber, "ticket", None))
    perfect_size = timber.get_perfect_size()
    nominal_size = timber.get_nominal_size()
    prism = cut_timber.get_bounding_box_prism()
    mesh = prism_to_mesh(prism)

    csg_nodes, csg_features = _count_csg_nodes_and_features(cut_timber.render_timber_with_cuts_csg_local())
    timber_kumiki_id = int(timber.ticket.kumiki_id)
    timber_class = type(timber).__name__
    is_perfect = bool(timber.is_perfect_timber())
    payload = _base_member_payload(
        name=get_timber_display_name(timber),
        member_type="timber",
        member_key=timber_key,
        kumiki_id=timber_kumiki_id,
        tags=timber_tags,
        vertices=mesh["vertices"],
        indices=mesh["indices"],
        prism_length=getattr(timber, "length", 0.0),
        prism_width=getattr(timber, "size", [0.0, 0.0])[0],
        prism_height=getattr(timber, "size", [0.0, 0.0])[1],
        perfect_width=perfect_size[0],
        perfect_height=perfect_size[1],
        nominal_width=nominal_size[0],
        nominal_height=nominal_size[1],
    )
    payload.update({
        "csg_nodes": csg_nodes,
        "csg_features": csg_features,
        "meshSource": "bounding-prism-fallback",
        "timberClass": timber_class,
        "isPerfectTimber": is_perfect,
        "hasActualGeometryDifferentFromPerfect": False,
    })
    return payload


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
            triangulation_empty_or_invalid = (
                "triangulate_cutcsg produced empty mesh" in str(exc)
                or "triangulate_cutcsg produced mesh without bounds" in str(exc)
                or "'NoneType' object is not subscriptable" in str(exc)
            )

            if triangulation_empty_or_invalid:
                try:
                    mesh_payload = _cut_timber_to_bbox_mesh_payload(cut_timber, timber_key)
                    triangle_count = len(mesh_payload.get("indices", [])) // 3
                    ss.mesh_cache[timber_key] = {
                        "mesh": mesh_payload,
                        "local_csg": None,
                        "cut_timber": cut_timber,
                    }
                    changed_keys.append(timber_key)
                    remesh_metrics.append({
                        "timberKey": timber_key,
                        "remesh_s": 0.0,
                        "csg_depth": 1,
                        "triangle_count": triangle_count,
                    })

                    meshes.append(mesh_payload)
                    seen_keys.add(timber_key)
                    log_stderr(
                        "Warning: triangulation produced empty/invalid mesh; "
                        f"rendered fallback bounding prism for {get_timber_display_name(cut_timber.timber)}"
                    )
                    continue
                except Exception as fallback_exc:
                    log_stderr(
                        f"Warning: fallback geometry failed for {get_timber_display_name(cut_timber.timber)}: {fallback_exc}"
                    )

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

    # Footprints are flat polygons in the XY (z=0) ground plane. We send their corners (as
    # [x, y, 0] points) and let the viewer build a light fill + darkened edge.
    footprints_payload = []
    frame_footprints = list(getattr(frame, "footprints", None) or [])
    for index, footprint in enumerate(frame_footprints):
        try:
            corners = []
            for corner in footprint.corners:
                corners.append([float(corner[0]), float(corner[1]), 0.0])
            footprints_payload.append({
                "key": f"footprint#{index}",
                "corners": corners,
            })
        except Exception as exc:
            log_stderr(f"Warning: skipping footprint {index}: {exc}")

    return {
        "kind": "triangle-geometry",
        "meshes": meshes,
        "footprints": footprints_payload,
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


def _assign_member_keys(frame: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Compute the same memberKey scheme used by build_real_geometry.

    Returns (timber_entries, accessory_entries) with stable ordering.
    Each timber entry: {memberKey, kumikiId, timber, cutTimber, displayName}.
    Each accessory entry: {memberKey, kumikiId, accessory, displayName, type}.
    """
    timber_entries: List[Dict[str, Any]] = []
    accessory_entries: List[Dict[str, Any]] = []
    key_counts: Dict[str, int] = {}

    for cut_timber in frame.cut_timbers:
        timber = cut_timber.timber
        display = get_timber_display_name(timber)
        occurrence = key_counts.get(display, 0)
        key_counts[display] = occurrence + 1
        member_key = f"{display}#{occurrence}"
        timber_entries.append({
            "memberKey": member_key,
            "kumikiId": int(timber.ticket.kumiki_id),
            "timber": timber,
            "cutTimber": cut_timber,
            "displayName": display,
        })

    accessories = list(frame.accessories) if hasattr(frame, "accessories") and frame.accessories else []
    for accessory in accessories:
        accessory_type = type(accessory).__name__
        key_base = f"accessory:{accessory_type}"
        occurrence = key_counts.get(key_base, 0)
        key_counts[key_base] = occurrence + 1
        member_key = f"{key_base}#{occurrence}"
        ticket = getattr(accessory, "ticket", None)
        kumiki_id = int(ticket.kumiki_id) if ticket is not None else 0
        ticket_name = getattr(ticket, "name", None) if ticket is not None else None
        display = ticket_name if ticket_name and ticket_name != "[no-name]" else f"{accessory_type} {occurrence + 1}"
        accessory_entries.append({
            "memberKey": member_key,
            "kumikiId": kumiki_id,
            "accessory": accessory,
            "displayName": display,
            "type": accessory_type,
        })

    return timber_entries, accessory_entries


def _serialize_cutting_summary(cut_timber: Any) -> List[Dict[str, Any]]:
    cuts_meta: List[Dict[str, Any]] = []
    cuts = list(getattr(cut_timber, "cuts", []) or [])
    for idx, cut in enumerate(cuts):
        tag = getattr(cut, "tag", None)
        has_csg = getattr(cut, "negative_csg", None) is not None
        has_top = getattr(cut, "maybe_top_end_cut_distance_from_bottom", None) is not None
        has_bot = getattr(cut, "maybe_bottom_end_cut_distance_from_bottom", None) is not None
        if tag and isinstance(tag, str):
            display = tag
        elif has_csg:
            display = f"cut {idx + 1}"
        elif has_top or has_bot:
            display = f"end-cut {idx + 1}"
        else:
            display = f"cut {idx + 1}"
        cuts_meta.append({
            "cutIndex": idx,
            "tag": tag,
            "hasCSG": has_csg,
            "hasEndCut": has_top or has_bot,
            "displayName": display,
        })
    return cuts_meta


def _normalize_ticket_tags(ticket: Any) -> List[str]:
    raw_tags = getattr(ticket, "tags", ())
    if not isinstance(raw_tags, (list, tuple)):
        return []

    tags: List[str] = []
    seen: set[str] = set()
    for tag in raw_tags:
        if not isinstance(tag, str):
            continue
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tags.append(normalized)
    tags.sort()
    return tags


def serialize_layers(frame: Any) -> Dict[str, Any]:
    """Build the data payload consumed by the viewer's Layers panel.

    Stable identities use ``ticket.kumiki_id`` for tickets-bearing entities
    (timbers, joints, accessories). Cuts have no ticket and are referenced as
    ``"<timber_kumiki_id>/cut/<cut_index>"`` on the JS side.
    """
    timber_entries, accessory_entries = _assign_member_keys(frame)

    # Build a map of timber object to (timber_kumiki_id, frame's CutTimber)
    timber_to_kumiki_and_cut: Dict[int, tuple[int, Any]] = {}
    for entry in timber_entries:
        timber_id = id(entry["timber"])
        timber_to_kumiki_and_cut[timber_id] = (entry["kumikiId"], entry["cutTimber"])

    timber_tags_by_kumiki_id: Dict[int, List[str]] = {}
    for entry in timber_entries:
        timber_ticket = getattr(entry.get("timber"), "ticket", None)
        timber_tags_by_kumiki_id[entry["kumikiId"]] = _normalize_ticket_tags(timber_ticket)

    # Extract joint records from source_joints
    source_joints = list(getattr(frame, "source_joints", ()) or ())
    accessory_kumiki_to_joint: Dict[int, int] = {}

    joints_payload: List[Dict[str, Any]] = []
    for joint in source_joints:
        joint_ticket = getattr(joint, "ticket", None)
        if joint_ticket is None:
            continue
        
        joint_kumiki_id = int(getattr(joint_ticket, "kumiki_id", 0))
        joint_name = getattr(joint_ticket, "name", None)
        if joint_name and joint_name == "[no-name]":
            joint_name = None
        joint_type = getattr(joint_ticket, "joint_type", None)
        joint_name = joint_name or (joint_type or "joint")
        joint_tags = _normalize_ticket_tags(joint_ticket)
        
        # Extract members (timbers) from cuttings
        members_list: List[Dict[str, Any]] = []
        cuttings_dict = getattr(joint, "cuttings", {})
        for cutting in cuttings_dict.values():
            timber = getattr(cutting, "timber", None)
            if timber is None:
                continue
            timber_id = id(timber)
            if timber_id not in timber_to_kumiki_and_cut:
                continue
            timber_kumiki_id, frame_cut_timber = timber_to_kumiki_and_cut[timber_id]
            
            # Find which cuts from this timber (in the joint) appear in the frame's merged CutTimber
            # by comparing object identity
            joint_cuts = [cutting]
            frame_cuts = getattr(frame_cut_timber, "cuts", [])
            
            cut_indices = []
            for frame_cut_idx, frame_cut in enumerate(frame_cuts):
                # Check if this frame cut is one of the joint's cuts (by identity)
                for joint_cut in joint_cuts:
                    if frame_cut is joint_cut:
                        cut_indices.append(frame_cut_idx)
                        break
            
            if cut_indices:
                members_list.append({
                    "timberKumikiId": timber_kumiki_id,
                    "cutIndices": cut_indices,
                })
        
        # Extract accessories
        accessory_kumiki_ids: List[int] = []
        joint_accessories = getattr(joint, "jointAccessories", {})
        for accessory in joint_accessories.values():
            accessory_ticket = getattr(accessory, "ticket", None)
            if accessory_ticket is not None:
                accessory_kumiki_id = int(getattr(accessory_ticket, "kumiki_id", 0))
                accessory_kumiki_ids.append(accessory_kumiki_id)
                accessory_kumiki_to_joint[accessory_kumiki_id] = joint_kumiki_id
        
        joints_payload.append({
            "kumikiId": joint_kumiki_id,
            "name": joint_name,
            "jointType": joint_type,
            "tags": joint_tags,
            "members": members_list,
            "accessoryKumikiIds": accessory_kumiki_ids,
        })

    timbers_payload: List[Dict[str, Any]] = []
    for entry in timber_entries:
        cuts_meta = _serialize_cutting_summary(entry["cutTimber"])
        timbers_payload.append({
            "kumikiId": entry["kumikiId"],
            "memberKey": entry["memberKey"],
            "name": entry["displayName"],
            "tags": list(timber_tags_by_kumiki_id.get(entry["kumikiId"], [])),
            "cuts": cuts_meta,
        })

    accessories_payload: List[Dict[str, Any]] = []
    for entry in accessory_entries:
        accessories_payload.append({
            "kumikiId": entry["kumikiId"],
            "memberKey": entry["memberKey"],
            "name": entry["displayName"],
            "type": entry["type"],
            "jointKumikiId": accessory_kumiki_to_joint.get(entry["kumikiId"]),
        })

    return {
        "frameName": frame.name if hasattr(frame, "name") else None,
        "timbers": timbers_payload,
        "accessories": accessories_payload,
        "joints": joints_payload,
        "assembly": _build_assembly_payload(frame, timber_entries, accessory_entries),
    }


def _assembly_float(value: Any) -> float:
    """Strict numeric conversion for assembly payloads (no string fallback)."""
    try:
        return float(value)
    except TypeError:
        return float(value.evalf())


def _build_assembly_payload(
    frame: Any,
    timber_entries: List[Dict[str, Any]],
    accessory_entries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Solve the frame's assembly sequence for the viewer's preview timeline.

    Returns None when no member of any joint declares an assembly freedom
    (the viewer hides the timeline). Payload shape:

        {"steps": [{"order": int, "suborder": int,
                    "movements": [{"kumikiId": int, "memberKey": str,
                                   "direction": [x, y, z],  # unit
                                   "distance": float,       # base freed_after amount
                                   "dragged": bool}]}],
         "warnings": [str],
         "failure": {"order": int | None, "suborder": int,
                     "message": str, "diagnostics": [str]} | None}

    ``distance`` is unscaled; the viewer multiplies by its configurable
    disassembly multiplier. On failure the solved steps are still included so
    the timeline stays scrubbable up to the failure point.
    """
    try:
        from kumiki.timber import solve_frame_assembly
    except ImportError:
        return None

    member_key_by_kumiki_id: Dict[int, str] = {}
    for entry in timber_entries:
        member_key_by_kumiki_id[entry["kumikiId"]] = entry["memberKey"]
    for entry in accessory_entries:
        member_key_by_kumiki_id[entry["kumikiId"]] = entry["memberKey"]

    try:
        solution = solve_frame_assembly(frame)
    except Exception as exc:  # noqa: BLE001 — assembly must never break the layers tree
        log_stderr(f"[assembly] solve failed: {exc}")
        return {
            "steps": [],
            "warnings": [],
            "failure": {"order": None, "suborder": 0, "message": str(exc), "diagnostics": []},
        }
    if solution is None:
        return None

    steps_payload: List[Dict[str, Any]] = []
    for step in solution.steps:
        movements_payload: List[Dict[str, Any]] = []
        for movement in step.movements:
            member_key = member_key_by_kumiki_id.get(movement.member_key)
            if member_key is None:
                # Member not rendered (e.g. filtered out of the frame); skip defensively.
                continue
            movements_payload.append({
                "kumikiId": int(movement.member_key),
                "memberKey": member_key,
                "direction": [_assembly_float(movement.direction[i, 0]) for i in range(3)],
                "distance": _assembly_float(movement.distance),
                "dragged": bool(movement.dragged),
            })
        steps_payload.append({
            "order": int(step.ordering.order),
            "suborder": int(step.ordering.suborder),
            "movements": movements_payload,
        })

    failure_payload = None
    if solution.failure is not None:
        failure_payload = {
            "order": int(solution.failure.ordering.order),
            "suborder": int(solution.failure.ordering.suborder),
            "message": solution.failure.message,
            "diagnostics": list(solution.failure.diagnostics),
        }

    return {
        "steps": steps_payload,
        "warnings": list(solution.warnings),
        "failure": failure_payload,
    }


def _walk_tagged_csg(csg: Any, current_path: List[str], collected: List[Dict[str, Any]]) -> None:
    """Walk a CSG tree, collecting tagged nodes with their path and feature labels."""
    from kumiki.cutcsg import (
        SolidUnion, Difference, HalfSpace, RectangularPrism,
    )

    tag = getattr(csg, "tag", None)
    next_path = current_path
    if tag:
        next_path = current_path + [tag]
        features: List[str] = []
        if isinstance(csg, RectangularPrism):
            named_features = getattr(csg, "named_features", None)
            if named_features:
                for label, _face in named_features:
                    if label and label not in features:
                        features.append(label)
        elif isinstance(csg, HalfSpace):
            named_feature = getattr(csg, "named_feature", None)
            if named_feature and named_feature not in features:
                features.append(named_feature)
        collected.append({
            "tag": tag,
            "path": list(next_path),
            "type": type(csg).__name__,
            "features": features,
        })

    if isinstance(csg, SolidUnion):
        for child in csg.children:
            _walk_tagged_csg(child, next_path, collected)
    elif isinstance(csg, Difference):
        _walk_tagged_csg(csg.base, next_path, collected)
        for sub in csg.subtract:
            _walk_tagged_csg(sub, next_path, collected)


def serialize_cut_csg_tree(cut_timber: Any, cut_index: int) -> Dict[str, Any]:
    cuts = list(getattr(cut_timber, "cuts", []) or [])
    if cut_index < 0 or cut_index >= len(cuts):
        raise IndexError(f"cutIndex {cut_index} out of range for timber with {len(cuts)} cuts")
    cut = cuts[cut_index]
    csg = cut.get_negative_csg_local() if hasattr(cut, "get_negative_csg_local") else getattr(cut, "negative_csg", None)
    collected: List[Dict[str, Any]] = []
    if csg is not None:
        _walk_tagged_csg(csg, [], collected)
    return {
        "cutIndex": cut_index,
        "taggedCSGs": collected,
    }


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


def _looks_like_pattern_list(value: Any) -> bool:
    """True if value is a non-empty list of Pattern objects."""
    if not isinstance(value, list) or not value:
        return False
    first = value[0]
    return hasattr(first, "path") and hasattr(first, "lambda_") and hasattr(first, "tags")


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


def _frame_from_pattern_list(pattern_list: List[Any]) -> "tuple[Any, Any]":
    """Render pattern(s) from a List[Pattern] as a single frame.

    Single pattern: raises the first 'main'-tagged pattern at origin.
    Multiple patterns: delegates to librarian.build_pattern_grid_frame which renders
    all patterns at origin, computes a square-ish grid layout by translating timbers
    and accessories, and returns one merged Frame.
    """
    from kumiki.rule import create_v3, scalar

    if not pattern_list:
        raise ValueError("Pattern list is empty")

    if len(pattern_list) == 1:
        origin = create_v3(scalar(0), scalar(0), scalar(0))
        target = pattern_list[0]
        with contextlib.redirect_stdout(sys.stderr):
            result = target.lambda_(origin)
        return _coerce_viewable_frame(result, target.name), pattern_list

    from kumiki.librarian import build_pattern_grid_frame
    return build_pattern_grid_frame(pattern_list), pattern_list


def _serialize_render_parameters_for_slot(slot_state: SlotState) -> Dict[str, Any]:
    return {
        "schema": [descriptor.to_protocol_dict() for descriptor in slot_state.render_parameter_schema],
        "applied": {
            name: serialize_render_parameter_value(value)
            for name, value in slot_state.applied_render_parameters.items()
        },
    }


def _resolve_callable_entry_with_render_parameters(
    callable_entry: Any,
    render_parameters: Optional[Mapping[str, Any]],
) -> Tuple[Any, List[RenderParameterDescriptor], Dict[str, Any]]:
    descriptors, resolved_kwargs = resolve_callable_render_parameters(
        callable_entry,
        render_parameters,
    )
    with contextlib.redirect_stdout(sys.stderr):
        value = callable_entry(**resolved_kwargs)
    return value, descriptors, resolved_kwargs


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


def resolve_frame_from_module(
    module: Any,
    render_parameters: Optional[Mapping[str, Any]] = None,
) -> "tuple[Any, Optional[Any], List[RenderParameterDescriptor], Dict[str, Any]]":
    """Resolve a frame from a loaded module.

    Returns (frame, patternbook_or_None, schema, applied).
    """
    if hasattr(module, "patterns"):
        pattern_list = getattr(module, "patterns")
        if _looks_like_pattern_list(pattern_list):
            frame, patternbook = _frame_from_pattern_list(pattern_list)
            return frame, patternbook, [], {}

    if hasattr(module, "build_frame") and callable(module.build_frame):
        frame, descriptors, applied = _resolve_callable_entry_with_render_parameters(
            module.build_frame,
            render_parameters,
        )
        return _coerce_viewable_frame(frame, "build_frame"), None, descriptors, applied

    if hasattr(module, "example"):
        example = getattr(module, "example")
        if callable(example):
            example, descriptors, applied = _resolve_callable_entry_with_render_parameters(
                example,
                render_parameters,
            )
        else:
            descriptors = []
            applied = {}
        if _looks_like_frame(example):
            return example, None, descriptors, applied
        try:
            return _coerce_viewable_frame(example, "example"), None, descriptors, applied
        except TypeError:
            pass

    raise AttributeError(
        "Module must expose a module-level 'patterns' list, 'example' Frame, or a 'build_frame()' function"
    )


def load_slot_state(
    file_path: str,
    previous_mesh_cache: Optional[Dict[str, Dict[str, Any]]] = None,
    render_parameters: Optional[Mapping[str, Any]] = None,
) -> SlotState:
    resolved_path = Path(file_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"File not found: {resolved_path}")

    module = load_module_from_path(resolved_path, verbose=True)
    frame, patternbook, render_parameter_schema, applied_render_parameters = resolve_frame_from_module(
        module,
        render_parameters=render_parameters,
    )
    return SlotState(
        file_path=resolved_path,
        module=module,
        frame=frame,
        mesh_cache=previous_mesh_cache if previous_mesh_cache is not None else {},
        patternbook=patternbook,
        render_parameter_schema=render_parameter_schema,
        applied_render_parameters=applied_render_parameters,
    )


def make_ready_event(state: RunnerState) -> Dict[str, Any]:
    ss = state._active
    frame_summary = serialize_frame(ss.frame)
    return {
        "type": "ready",
        "examplePath": str(ss.file_path),
        "commands": [
            "ping", "reload_example", "get_frame", "get_geometry",
            "get_member", "find_csg_at_point", "find_csg_by_path",
            "get_layers_tree", "get_csg_tree",
            "load_slot", "unload_slot", "list_slots",
            "list_available_patterns", "raise_specific_pattern",
            "shutdown",
        ],
        "frame": {
            "name": frame_summary["name"],
            "timber_count": frame_summary["timber_count"],
            "accessories_count": frame_summary["accessories_count"],
        },
        "renderParameters": _serialize_render_parameters_for_slot(ss),
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

    if ctrl_click:
        new_path, target_csg, feature_label = _navigate_csg_to_leaf(local_csg, pt_local, eps)
    else:
        if current_path:
            node = _resolve_csg_at_path(local_csg, current_path, pt_local, eps)
            on_boundary = _is_point_on_csg_boundary_float(node, pt_local, eps)
            if not on_boundary:
                node = local_csg
                current_path = []
        else:
            node = local_csg

        new_path, target_csg, feature_label = _navigate_csg_one_level(
            node, pt_local, current_path, eps,
        )

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


def _handle_find_csg_by_path(state: RunnerState, payload: Dict[str, Any], slot_state: Optional['SlotState'] = None) -> Dict[str, Any]:
    """Resolve a CSG at a known path and return highlight mesh for the viewer."""
    ss = slot_state if slot_state is not None else state._active
    member_key = payload.get("memberKey")
    path = payload.get("path") or []
    feature_label = payload.get("featureLabel") or None
    eps = 5e-4

    if not isinstance(member_key, str) or member_key not in ss.mesh_cache:
        raise ValueError(f"Unknown memberKey: {member_key}")
    if not isinstance(path, list) or len(path) == 0:
        raise ValueError("path must be a non-empty list of tag strings")

    cached = ss.mesh_cache[member_key]
    local_csg = cached.get("local_csg")
    cut_timber = cached.get("cut_timber")
    mesh = cached.get("mesh")

    if local_csg is None or cut_timber is None or mesh is None:
        raise ValueError(f"No CSG data cached for {member_key}")

    timber = cut_timber.timber
    timber_rot, timber_pos = _build_inv_transform_float(timber.transform)

    # Resolve the CSG node at the given path (no point hint needed)
    target_csg = _resolve_csg_at_path(local_csg, path, None, eps)

    # If a feature label is specified, resolve the named face on the target
    actual_feature_label = None
    feature_target = target_csg
    if feature_label:
        from kumiki.cutcsg import RectangularPrism, HalfSpace
        if isinstance(target_csg, RectangularPrism):
            named_features = getattr(target_csg, "named_features", None)
            if named_features:
                for label, face in named_features:
                    if label == feature_label:
                        feature_target = face
                        actual_feature_label = label
                        break
        elif isinstance(target_csg, HalfSpace):
            named_feature = getattr(target_csg, "named_feature", None)
            if named_feature == feature_label:
                actual_feature_label = feature_label
                feature_target = target_csg

    hl_verts, hl_idx, matched, total = _extract_highlight_mesh(
        mesh["vertices"],
        mesh["indices"],
        feature_target if actual_feature_label else target_csg,
        timber_rot,
        timber_pos,
        eps,
        root_csg=local_csg,
        selected_path=path,
        selected_ref=target_csg,
        feature_label=actual_feature_label,
    )

    parent_hl = None
    if actual_feature_label and target_csg is not feature_target:
        p_verts, p_idx, _, _ = _extract_highlight_mesh(
            mesh["vertices"],
            mesh["indices"],
            target_csg,
            timber_rot,
            timber_pos,
            eps,
            root_csg=local_csg,
            selected_path=path,
            selected_ref=target_csg,
        )
        if p_verts:
            parent_hl = {"vertices": p_verts, "indices": p_idx}

    result: Dict[str, Any] = {
        "path": path,
        "featureLabel": actual_feature_label,
        "highlightMesh": {
            "vertices": hl_verts,
            "indices": hl_idx,
        },
        "stats": {
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
    from kumiki.librarian import scan_library_index

    sources: List[Dict[str, Any]] = []

    # Shipped patterns — bundled inside the kumiki package as kumiki/patterns/
    # (pip-installed) or at the sibling patterns/ folder in a dev checkout.
    def _extract_patterns_from_index(index: Any) -> List[Any]:
        items = []
        for pb_record in index.get("patternbooks", []):
            source_file = pb_record.get("file_path")
            for p in (pb_record.get("patterns") or []):
                path = p.get("path", "")
                tags = list(p.get("tags") or [])
                name = path.split("/")[-1] if path else ""
                items.append({
                    "path": path,
                    "name": name,
                    "tags": tags,
                    "groups": [],
                    "source_file": source_file,
                })
        return items

    try:
        import kumiki
        kumiki_dir = Path(kumiki.__file__).resolve().parent
        shipped_patterns_dir = kumiki_dir / "patterns"
        if not shipped_patterns_dir.is_dir():
            shipped_patterns_dir = kumiki_dir.parent / "patterns"
        if shipped_patterns_dir.is_dir():
            with contextlib.redirect_stdout(sys.stderr):
                index = scan_library_index(str(shipped_patterns_dir))
            patterns_list = _extract_patterns_from_index(index)
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
                    index = scan_library_index(str(local_patterns_dir))
                patterns_list = _extract_patterns_from_index(index)
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


def _find_pattern_in_list(pattern_list: List[Any], pattern_name: str) -> Optional[Any]:
    """Find a Pattern in a List[Pattern] by path or name."""
    for p in pattern_list:
        path = getattr(p, "path", "")
        if path == pattern_name or path.split("/")[-1] == pattern_name:
            return p
    return None


def _raise_specific_pattern(
    source_file: str,
    pattern_name: str,
    render_parameters: Optional[Mapping[str, Any]] = None,
) -> "tuple[SlotState, Dict[str, Any]]":
    """Load a specific pattern from a source file and return (SlotState, result_dict)."""
    resolved = Path(source_file).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Pattern source file not found: {resolved}")

    t0 = time.monotonic()
    module = load_module_from_path(resolved, verbose=True)

    # --- New: List[Pattern] system ---
    if hasattr(module, "patterns") and _looks_like_pattern_list(getattr(module, "patterns")):
        pattern_list = getattr(module, "patterns")
        pattern = _find_pattern_in_list(pattern_list, pattern_name)
        if pattern is None:
            available = [getattr(p, "path", "") for p in pattern_list]
            raise ValueError(f"Pattern '{pattern_name}' not found. Available: {available}")

        pattern_lambda = pattern.lambda_
        render_parameter_schema, applied_render_parameters = resolve_callable_render_parameters(
            pattern_lambda,
            render_parameters,
            skip_first_parameter=True,
        )

        from kumiki.rule import create_v3, scalar
        origin = create_v3(scalar(0), scalar(0), scalar(0))
        with contextlib.redirect_stdout(sys.stderr):
            pattern_result = pattern_lambda(origin, **applied_render_parameters)
        frame = _coerce_viewable_frame(pattern_result, f"Pattern '{pattern.name}'")

        reload_s = time.monotonic() - t0
        slot = SlotState(
            file_path=resolved,
            module=module,
            frame=frame,
            mesh_cache={},
            patternbook=pattern_list,
            single_pattern_name=pattern.path,
            render_parameter_schema=render_parameter_schema,
            applied_render_parameters=applied_render_parameters,
        )
        result = {
            "examplePath": str(resolved),
            "patternName": pattern.path,
            "frame": {
                "name": frame.name if hasattr(frame, "name") else pattern.name,
                "timber_count": len(frame.cut_timbers),
                "accessories_count": len(frame.accessories) if hasattr(frame, "accessories") else 0,
            },
            "renderParameters": _serialize_render_parameters_for_slot(slot),
            "profiling": {"reload_s": reload_s},
        }
        return slot, result

    raise ValueError(
        f"No patterns list found in {source_file}. "
        "Pattern files must expose a module-level 'patterns = [Pattern(...), ...]' list."
    )


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
        render_parameters = payload.get("renderParameters") if isinstance(payload.get("renderParameters"), dict) else None
        old_cache = old_slot.mesh_cache if old_slot else {}
        t0 = time.monotonic()

        # If this slot was loaded for a single pattern, re-raise just that pattern
        if old_slot and old_slot.single_pattern_name:
            next_slot, _ = _raise_specific_pattern(
                next_path,
                old_slot.single_pattern_name,
                render_parameters=render_parameters,
            )
            next_slot.mesh_cache = old_cache
        else:
            next_slot = load_slot_state(
                next_path,
                old_cache,
                render_parameters=render_parameters,
            )

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
            "renderParameters": _serialize_render_parameters_for_slot(next_slot),
            "profiling": {"reload_s": reload_s},
        }
        return state, make_success_response(request_id, command, result), False

    if command == "get_frame":
        ss = _resolve_slot(state, payload)
        frame_payload = serialize_frame(ss.frame)
        frame_payload["renderParameters"] = _serialize_render_parameters_for_slot(ss)
        return state, make_success_response(request_id, command, frame_payload), False

    if command == "get_layers_tree":
        ss = _resolve_slot(state, payload)
        return state, make_success_response(request_id, command, serialize_layers(ss.frame)), False

    if command == "get_csg_tree":
        ss = _resolve_slot(state, payload)
        member_key = payload.get("memberKey")
        cut_index = payload.get("cutIndex")
        if not isinstance(member_key, str) or not member_key:
            raise ValueError("get_csg_tree requires payload.memberKey")
        if not isinstance(cut_index, int):
            raise ValueError("get_csg_tree requires integer payload.cutIndex")
        cached = ss.mesh_cache.get(member_key)
        cut_timber = cached.get("cut_timber") if cached else None
        if cut_timber is None:
            # Fall back to scanning frame for the matching memberKey by name+occurrence.
            timber_entries, _ = _assign_member_keys(ss.frame)
            match = next((e for e in timber_entries if e["memberKey"] == member_key), None)
            if match is None:
                raise ValueError(f"Unknown memberKey: {member_key}")
            cut_timber = match["cutTimber"]
        result = serialize_cut_csg_tree(cut_timber, cut_index)
        result["memberKey"] = member_key
        return state, make_success_response(request_id, command, result), False

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

    if command == "find_csg_by_path":
        ss = _resolve_slot(state, payload)
        result = _handle_find_csg_by_path(state, payload, ss)
        return state, make_success_response(request_id, command, result), False

    # --- Slot management ---

    if command == "load_slot":
        slot_name = payload.get("slot")
        file_path = payload.get("filePath")
        render_parameters = payload.get("renderParameters") if isinstance(payload.get("renderParameters"), dict) else None
        if not isinstance(slot_name, str) or not slot_name:
            raise ValueError("load_slot requires payload.slot")
        if not isinstance(file_path, str) or not file_path:
            raise ValueError("load_slot requires payload.filePath")
        t0 = time.monotonic()
        new_slot = load_slot_state(file_path, render_parameters=render_parameters)
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
            "renderParameters": _serialize_render_parameters_for_slot(new_slot),
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
        render_parameters = payload.get("renderParameters") if isinstance(payload.get("renderParameters"), dict) else None
        if not isinstance(slot_name, str) or not slot_name:
            raise ValueError("raise_specific_pattern requires payload.slot")
        if not isinstance(source_file, str) or not source_file:
            raise ValueError("raise_specific_pattern requires payload.sourceFile")
        if not isinstance(pattern_name, str) or not pattern_name:
            raise ValueError("raise_specific_pattern requires payload.patternName")
        new_slot, result = _raise_specific_pattern(
            source_file,
            pattern_name,
            render_parameters=render_parameters,
        )
        state.slots[slot_name] = new_slot
        result["slot"] = slot_name
        log_stderr(f"[slot] Raised pattern '{pattern_name}' in slot '{slot_name}'")
        return state, make_success_response(request_id, command, result), False

    if command == "export_frame":
        ss = _resolve_slot(state, payload)
        export_format = str(payload.get("format", "stl")).lower()
        output_dir_raw = payload.get("outputDir")
        include_combined = bool(payload.get("includeCombined", True))
        include_individuals = bool(payload.get("includeIndividuals", True))
        include_accessories = bool(payload.get("includeAccessories", True))

        if export_format not in {"stl", "step", "3mf", "obj"}:
            raise ValueError("export_frame requires payload.format to be 'stl', 'step', '3mf', or 'obj'")
        if not isinstance(output_dir_raw, str) or not output_dir_raw:
            raise ValueError("export_frame requires payload.outputDir")

        output_dir = Path(output_dir_raw).resolve()
        if _project_root is not None:
            allowed_root = (_project_root / "kigumi_exports").resolve()
            try:
                output_dir.relative_to(allowed_root)
            except ValueError as exc:
                raise ValueError("export_frame outputDir must be inside project kigumi_exports/") from exc

        if export_format == "stl":
            from kumiki.blueprint import export_frame_stl

            written = export_frame_stl(
                ss.frame,
                output_dir,
                combined=include_combined,
                include_accessories=include_accessories,
            )
            combined_name = "_combined.stl"
            extension_glob = "*.stl"
        elif export_format == "3mf":
            from kumiki.blueprint import export_frame_3mf

            written = export_frame_3mf(
                ss.frame,
                output_dir,
                combined=include_combined,
                include_accessories=include_accessories,
            )
            combined_name = "_combined.3mf"
            extension_glob = "*.3mf"
        elif export_format == "obj":
            from kumiki.blueprint import export_frame_obj

            written = export_frame_obj(
                ss.frame,
                output_dir,
                combined=include_combined,
                include_accessories=include_accessories,
            )
            combined_name = "_combined.obj"
            extension_glob = "*.obj"
        else:
            from kumiki.blueprint import export_frame_step

            written = export_frame_step(
                ss.frame,
                output_dir,
                combined=include_combined,
                include_accessories=include_accessories,
            )
            combined_name = "_combined.step"
            extension_glob = "*.step"

        if not include_individuals:
            for candidate in output_dir.glob(extension_glob):
                if candidate.name == combined_name:
                    continue
                try:
                    candidate.unlink()
                except OSError as exc:
                    log_stderr(f"Warning: failed to remove individual export '{candidate}': {exc}")

            combined_path = output_dir / combined_name
            written = [combined_path] if combined_path.exists() else []

        return state, make_success_response(request_id, command, {
            "format": export_format,
            "outputDir": str(output_dir),
            "includeCombined": include_combined,
            "includeIndividuals": include_individuals,
            "includeAccessories": include_accessories,
            "files": [str(path) for path in written],
            "count": len(written),
        }), False

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
