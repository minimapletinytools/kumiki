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
import math
import os
import select
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Mapping, NamedTuple, Optional, List, Tuple

from kumiki.librarian import (
    RenderParameterDescriptor,
    resolve_callable_render_parameters,
    serialize_render_parameter_value,
)

if TYPE_CHECKING:
    # Annotations only. kumiki must NOT be imported at module scope for
    # anything used at runtime: _purge_project_modules drops modules under the
    # project root that are not in a venv, which in a dev checkout includes
    # kumiki itself. A module-level class reference would then leave isinstance
    # comparing against a stale class object after a reload. Under
    # TYPE_CHECKING there is no runtime import at all, so annotations can be
    # concrete while every isinstance check still imports inside its function.
    from kumiki.cutcsg import CutCSG
    from kumiki.timber import CutTimber, Cutting, Joint


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
    # Drawings made in this session and not yet saved. They live here rather
    # than in the viewer so python stays the one place a drawing comes from,
    # and they are lost on reload, which is what "unsaved" should mean.
    pending_drawings: List[Dict[str, Any]] = field(default_factory=list)


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


# stdout carries the newline-delimited JSON protocol and is written from both
# the main request/response loop and the background assembly-solve thread
# (see the `get_assembly` handler below). A write of more than PIPE_BUF bytes
# is not atomic, so unsynchronized concurrent prints can interleave their
# bytes on the pipe and corrupt the line-based protocol -- serialize all
# stdout writes through this lock.
_stdout_lock = threading.Lock()


def emit_message(payload: Dict[str, Any]) -> None:
    with _stdout_lock:
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


def _vector3_to_floats(vec: Any) -> list:
    """Exact float triple from a 3x1 sympy Matrix, for numeric (non-display) use."""
    return [float(vec[i, 0]) for i in range(3)]


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
    from kumiki.cutcsg import SolidUnion, Difference

    nodes = 1
    features = 0

    features += len(_declared_feature_names(csg))

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
    # Face naming matches kumiki.timber.TimberFace: RIGHT=+X, FRONT=+Y, LEFT=-X, BACK=-Y
    # (see RectangularPrismFeature.test_point in kumiki/cutcsg.py).
    indices = [
        0, 2, 1,   0, 3, 2,  # bottom (-Z face)
        4, 5, 6,   4, 6, 7,  # top    (+Z face)
        0, 1, 5,   0, 5, 4,  # back   (-Y face)
        3, 7, 6,   3, 6, 2,  # front  (+Y face)
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
    from kumiki.timber import _create_extended_rectangular_prism, _ptw_face_tags

    timber = cut_timber.timber
    has_bottom_cut = any(c.get_maybe_bottom_end_cut() is not None for c in cut_timber.cuts)
    has_top_cut = any(c.get_maybe_top_end_cut() is not None for c in cut_timber.cuts)

    # face_tags is required; omitting it raised TypeError, so this preview
    # never rendered. It is the perfect-timber-within prism, so it carries the
    # ptw faces and names itself the way the timber's own perfect shape does.
    base_prism = _create_extended_rectangular_prism(
        face_tags=_ptw_face_tags(),
        size=timber.get_perfect_size(),
        length=timber.length,
        extend_bot=has_bottom_cut,
        extend_top=has_top_cut,
        label=type(timber).csg_label("perfect", "extended"),
    )

    if not cut_timber.cuts:
        return base_prism
    # A cut that removes nothing contributes no node, exactly as in
    # render_timber_with_cuts_csg_local.
    negs = [
        csg for csg in (c.get_negative_csg_local() for c in cut_timber.cuts)
        if csg is not None
    ]
    if not negs:
        return base_prism
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
        "kumikiEphemeralId": kumiki_id,
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


def _cut_length(cut_timber: Any) -> Optional[float]:
    """How long the timber is once its end cuts are made.

    A timber with an end joint is not cut to length first -- the joint decides
    where its end lands, so `timber.length` is the stock it was cut from rather
    than the piece that comes out. The bounding prism is already cropped to the
    end cuts, so its extent along the length axis is the finished piece.
    """
    try:
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
        return round(float(prism.end_distance - prism.start_distance), 6)
    except Exception as exc:
        log_stderr(f"Warning: could not measure cut length: {exc}")
        return None


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
    timber_tags = _serialize_timber_tags(getattr(timber, "ticket", None))
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
        "cut_length": _cut_length(cut_timber),
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

    # No-joints box geometry: plain rectangular boxes with no CSG cuts applied at
    # all (no joint cuts, no mortise holes), cropped in length only by this
    # timber's aggregated end-cut trims. Built unconditionally (not gated behind
    # has_non_rectangular_actual) since a joint cut changes what a no-joints box
    # looks like for every timber shape, not just non-rectangular ones.
    try:
        perfect_box_mesh = prism_to_mesh(cut_timber.get_perfect_timber_within_bounding_box_prism())
        payload["perfectBoxNoJointsVertices"] = perfect_box_mesh["vertices"]
        payload["perfectBoxNoJointsIndices"] = perfect_box_mesh["indices"]
    except Exception as exc:  # noqa: BLE001 — best-effort optional payload
        log_stderr(
            f"Warning: failed to build perfect-box-no-joints mesh for "
            f"{get_timber_display_name(timber)}: {exc}"
        )

    try:
        rough_box_mesh = prism_to_mesh(cut_timber.get_rough_bounding_box_prism())
        payload["roughBoxNoJointsVertices"] = rough_box_mesh["vertices"]
        payload["roughBoxNoJointsIndices"] = rough_box_mesh["indices"]
    except Exception as exc:  # noqa: BLE001 — best-effort optional payload
        log_stderr(
            f"Warning: failed to build rough-box-no-joints mesh for "
            f"{get_timber_display_name(timber)}: {exc}"
        )

    return payload


def _accessory_to_triangle_mesh_payload(
    accessory: Any,
    local_csg: Any,
    accessory_key: str,
    accessory_name: str,
) -> Dict[str, Any]:
    import math

    from kumiki.cutcsg import Cylinder, adopt_csg
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
    payload = _base_member_payload(
        name=accessory_name,
        member_type="accessory",
        member_key=accessory_key,
        kumiki_id=accessory_kumiki_id,
        # Only timbers carry tags; an accessory has no ticket field for them.
        tags=[],
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

    # Round accessories (pegs, dowels, ...) mesh as a faceted polygon
    # approximation, so EdgesGeometry's fixed angle threshold never catches
    # the curved barrel -- only the flat end caps get outlined. Ship the
    # exact cylinder primitive so the viewer can draw the two true,
    # camera-facing silhouette lines each frame instead (see
    # updateCylinderSilhouettes() in viewer-app.js).
    if (
        isinstance(global_csg, Cylinder)
        and global_csg.start_distance is not None
        and global_csg.end_distance is not None
    ):
        axis = _vector3_to_floats(global_csg.axis_direction)
        axis_len = math.sqrt(sum(c * c for c in axis)) or 1.0
        axis = [c / axis_len for c in axis]
        position = _vector3_to_floats(global_csg.position)
        start = float(global_csg.start_distance)
        end = float(global_csg.end_distance)
        payload["cylinderAxis"] = {
            "axisStart": [position[i] + axis[i] * start for i in range(3)],
            "axisEnd": [position[i] + axis[i] * end for i in range(3)],
            "radius": float(global_csg.radius),
        }

    return payload


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
    timber_tags = _serialize_timber_tags(getattr(timber, "ticket", None))
    perfect_size = timber.get_perfect_size()
    nominal_size = timber.get_nominal_size()
    prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
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
        "cut_length": _cut_length(cut_timber),
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

            local_csg = accessory.get_csg_local()

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
    Each timber entry: {memberKey, kumikiEphemeralId, timber, cutTimber, displayName}.
    Each accessory entry: {memberKey, kumikiEphemeralId, accessory, displayName, type}.
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
            "kumikiEphemeralId": int(timber.ticket.kumiki_id),
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
            "kumikiEphemeralId": kumiki_id,
            "accessory": accessory,
            "displayName": display,
            "type": accessory_type,
        })

    return timber_entries, accessory_entries


def _serialize_cutting_summary(cut_timber: Any) -> List[Dict[str, Any]]:
    cuts_meta: List[Dict[str, Any]] = []
    cuts = list(getattr(cut_timber, "cuts", []) or [])
    for idx, cut in enumerate(cuts):
        label = _label_name(cut)
        has_csg = getattr(cut, "negative_csg", None) is not None
        has_top = getattr(cut, "maybe_top_end_cut_distance_from_bottom", None) is not None
        has_bot = getattr(cut, "maybe_bottom_end_cut_distance_from_bottom", None) is not None
        if label and isinstance(label, str):
            display = label
        elif has_csg:
            display = f"cut {idx + 1}"
        elif has_top or has_bot:
            display = f"end-cut {idx + 1}"
        else:
            display = f"cut {idx + 1}"
        cuts_meta.append({
            "cutIndex": idx,
            "label": label,
            "hasCSG": has_csg,
            "hasEndCut": has_top or has_bot,
            "displayName": display,
        })
    return cuts_meta


def _timber_tag_kinds() -> List[Tuple[type, str]]:
    """The kumiki tag classes paired with their wire names, most specific first.

    Imported per call rather than at module scope: a reload purges and
    re-imports kumiki, which would leave a module-level class object matching
    nothing an isinstance check is ever handed.
    """
    from kumiki.ticket import GenericTag, MemberTag, SliceTag

    return [(SliceTag, "slice"), (MemberTag, "member"), (GenericTag, "generic")]


def _serialize_timber_tags(ticket: Any) -> List[Dict[str, str]]:
    """Typed tags off a timber ticket, as {"kind", "name"} sorted by both.

    Only TimberTicket carries tags. A tag class with no wire name is skipped
    with a warning rather than raised on: this runs inside the per-timber
    geometry build, where an exception costs the whole timber's mesh. The
    kumiki-side test that every tag class is listed here is the loud half.
    """
    raw_tags = getattr(ticket, "tags", ())
    if not isinstance(raw_tags, (list, tuple)):
        return []

    kinds = _timber_tag_kinds()
    tags: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for tag in raw_tags:
        if isinstance(tag, str):
            kind, name = "generic", tag
        else:
            kind = next((wire for cls, wire in kinds if isinstance(tag, cls)), "")
            if not kind:
                log_stderr(f"Warning: skipping tag of unknown kind {type(tag).__name__}")
                continue
            name = getattr(tag, "name", "")
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or (kind, name) in seen:
            continue
        seen.add((kind, name))
        tags.append({"kind": kind, "name": name})
    tags.sort(key=lambda tag: (tag["kind"], tag["name"]))
    return tags


# --- drawings ---------------------------------------------------------------
#
# TESTING SCAFFOLDING. This builds one hard-coded drawing so the viewer's
# multi-viewport path has something to render before real drawing sets exist.
# Nothing in kumiki produces or stores it, no UI creates it, and it is expected
# to be deleted once drawings are authored for real.


# Camera frames, in kumiki world axes (Z up, +Y north, +X east). `look` is the
# direction the camera faces; the viewer derives the position back along it, so
# a frame is purely an orientation. right x up == -look, matching a camera that
# looks down its own -Z.
_DEBUG_DRAWING_VIEWS: List[Tuple[str, List[float], List[float], List[float]]] = [
    # id        right          up             look
    ("front", [1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]),
    ("top", [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]),
    ("right", [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [-1.0, 0.0, 0.0]),
]

# A3 landscape, in metres. Customizable per drawing in the real thing; this one
# is scaffolding, so it just picks a common sheet.
_DEBUG_DRAWING_PAGE = {"width": 0.420, "height": 0.297}

# Quadrants of the page, as normalized [x, y, width, height] with a top-left
# origin.
_DEBUG_DRAWING_RECTS: Dict[str, List[float]] = {
    "front": [0.0, 0.0, 0.5, 0.5],
    "top": [0.5, 0.0, 0.5, 0.5],
    "right": [0.0, 0.5, 0.5, 0.5],
    "preview": [0.5, 0.5, 0.5, 0.5],
}

# Leaves a margin around the model rather than framing it edge to edge.
_DRAWING_EXTENT_PADDING = 1.15


def _cut_extent(cut_timber: Any, stock_length: float) -> Tuple[float, float]:
    """Where the finished piece starts and ends along its own length.

    The same distinction the member list draws (see _cut_length): a timber with
    an end joint is not cut to length first, so its stock is not the piece that
    gets drawn. Framing a view on the stock leaves the piece sitting off centre
    by whatever the joint took off.
    """
    try:
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
        start = float(prism.start_distance) if prism.start_distance is not None else 0.0
        end = float(prism.end_distance) if prism.end_distance is not None else stock_length
        return start, end
    except Exception as exc:
        log_stderr(f"Warning: could not measure cut extent: {exc}")
        return 0.0, stock_length


def _timber_world_corners(cut_timber: Any) -> List[List[float]]:
    """The 8 corners of a timber's finished piece, in world space."""
    timber = cut_timber.timber
    origin = _vector3_to_floats(timber.get_bottom_position_global())
    along = _vector3_to_floats(timber.get_length_direction_global())
    across = _vector3_to_floats(timber.get_width_direction_global())
    up = _vector3_to_floats(timber.get_height_direction_global())
    length = float(timber.length)
    half_width = float(timber.size[0]) / 2.0
    half_height = float(timber.size[1]) / 2.0

    corners: List[List[float]] = []
    for distance in _cut_extent(cut_timber, length):
        for width_sign in (-half_width, half_width):
            for height_sign in (-half_height, half_height):
                corners.append([
                    origin[axis]
                    + along[axis] * distance
                    + across[axis] * width_sign
                    + up[axis] * height_sign
                    for axis in range(3)
                ])
    return corners


def _frame_world_bounds(frame: Any) -> Tuple[List[float], List[float]]:
    """(centre, half_size) of everything in the frame; a unit box if it is empty."""
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for cut_timber in frame.cut_timbers:
        for corner in _timber_world_corners(cut_timber):
            for axis in range(3):
                lows[axis] = min(lows[axis], corner[axis])
                highs[axis] = max(highs[axis], corner[axis])

    if any(low == float("inf") for low in lows):
        return [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]

    centre = [(lows[axis] + highs[axis]) / 2.0 for axis in range(3)]
    half_size = [(highs[axis] - lows[axis]) / 2.0 for axis in range(3)]
    return centre, half_size


def _view_extent(
    half_size: List[float],
    right: List[float],
    up: List[float],
    aspect: float = 1.0,
) -> float:
    """Half-height that fits the model in a view with these screen axes.

    The viewer widens the frustum from the half-height by the viewport's aspect,
    so the width the model needs has to be divided by that aspect before the two
    are compared. Skipping that is only harmless while viewports are square; a
    long timber drawn across a wide strip needs far less height than its length.
    """
    def projected(axis: List[float]) -> float:
        return sum(abs(axis[i]) * half_size[i] for i in range(3))

    safe_aspect = aspect if aspect > 0 else 1.0
    needed = max(projected(up), projected(right) / safe_aspect)
    return max(0.001, needed * _DRAWING_EXTENT_PADDING)


def _viewport_aspect(rect: List[float], page: Dict[str, float]) -> float:
    """A viewport's aspect: its share of the sheet, times the sheet's own."""
    height = rect[3] * page["height"]
    return (rect[2] * page["width"]) / height if height > 0 else 1.0


def _cross(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _camera_looking_at_face(normal: List[float], along: List[float]) -> Dict[str, Any]:
    """A camera frame square-on to a face, with the timber's length across screen.

    The camera sits outside the face along its outward normal and looks back at
    it. `up` is chosen so right x up == -look, the frame of a camera looking down
    its own -Z, which is what keeps the view from coming out mirrored.
    """
    return {
        "right": list(along),
        "up": _cross(normal, along),
        "look": [-component for component in normal],
    }


def build_default_drawing_for_debugging(frame: Any) -> Dict[str, Any]:
    """A four-viewport scene over the whole frame: three elevations and a preview.

    Testing scaffolding -- see the note at the top of this section. The three
    orthographic viewports are locked, so the viewer holds their angle and only
    lets pan/zoom deltas ride on top; the perspective one is left free and is
    the same kind of viewport the default 3D scene uses.
    """
    centre, half_size = _frame_world_bounds(frame)
    viewports: List[Dict[str, Any]] = []
    for view_id, right, up, look in _DEBUG_DRAWING_VIEWS:
        rect = _DEBUG_DRAWING_RECTS[view_id]
        viewports.append({
            "id": view_id,
            "rect": rect,
            "locked": True,
            "projection": "orthographic",
            "camera": {
                "right": right,
                "up": up,
                "look": look,
                "target": centre,
                "extent": _view_extent(half_size, right, up, _viewport_aspect(rect, _DEBUG_DRAWING_PAGE)),
            },
            # Every timber, which is also what a scene defaults to; spelled out
            # because a real drawing is the interesting case and would not.
            "members": None,
            "ghostOthers": True,
            "measurements": [],
        })

    viewports.append(_preview_viewport(
        _DEBUG_DRAWING_RECTS["preview"], _world_box(centre, half_size), _DEBUG_DRAWING_PAGE,
        {"mode": "free"}, orient_by_search,
    ))

    return {
        "id": "debug-default-drawing",
        # The sheet these sit on. Rects above are fractions of it, so the four
        # views tile an A3 page rather than the window.
        "page": dict(_DEBUG_DRAWING_PAGE),
        # A drawing shows no camera gizmos.
        "cameraControls": [],
        "viewports": viewports,
    }


# A3 landscape, in metres. Fixed for now; the page is meant to be the drawing's
# to choose, and this is where that choice will arrive from.
_SELECTION_DRAWING_PAGE = {"width": 0.420, "height": 0.297}

SELECTION_DRAWING_ID = "selection-drawing"

# One timber gets its four long faces rolled out down the left of the sheet,
# with a live preview beside them -- the shop drawing for a single piece. Which
# face each view looks at, in the timber's own frame, going around it.
_LONG_FACE_VIEWS: List[Tuple[str, str, int]] = [
    # id       axis      sign
    ("front", "height", 1),
    ("right", "width", 1),
    ("back", "height", -1),
    ("left", "width", -1),
]

_LONG_FACE_RECTS: Dict[str, List[float]] = {
    "front": [0.0, 0.0, 0.5, 0.25],
    "right": [0.0, 0.25, 0.5, 0.25],
    "back": [0.0, 0.5, 0.5, 0.25],
    "left": [0.0, 0.75, 0.5, 0.25],
    "preview": [0.5, 0.0, 0.5, 1.0],
}

# Several members are drawn as world elevations instead: there is no single
# piece whose faces the sheet could be about.
_SELECTION_QUADRANTS: Dict[str, List[float]] = {
    "front": [0.0, 0.0, 0.5, 0.5],
    "top": [0.5, 0.0, 0.5, 0.5],
    "right": [0.0, 0.5, 0.5, 0.5],
    "preview": [0.5, 0.5, 0.5, 0.5],
}


def _members_world_bounds(entries: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    """(centre, half_size) over the given timber entries."""
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for entry in entries:
        for corner in _timber_world_corners(entry["cutTimber"]):
            for axis in range(3):
                lows[axis] = min(lows[axis], corner[axis])
                highs[axis] = max(highs[axis], corner[axis])
    if any(low == float("inf") for low in lows):
        return [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]
    return (
        [(lows[axis] + highs[axis]) / 2.0 for axis in range(3)],
        [(highs[axis] - lows[axis]) / 2.0 for axis in range(3)],
    )


def _normalize(vec: List[float]) -> List[float]:
    length = math.sqrt(sum(component * component for component in vec))
    return [component / length for component in vec] if length > 0 else [0.0, 0.0, 1.0]


def _camera_frame_looking(look: List[float]) -> Dict[str, Any]:
    """An orthonormal frame looking along `look`, kept upright.

    `up` is world Z with the part along the view direction taken out, which is
    what stops a three-quarter view from arriving on its side. right x up ==
    -look, the frame of a camera looking down its own -Z.
    """
    forward = _normalize(look)
    world_up = [0.0, 0.0, 1.0]
    along = sum(world_up[i] * forward[i] for i in range(3))
    up = _normalize([world_up[i] - along * forward[i] for i in range(3)])
    return {"right": _normalize(_cross(forward, up)), "up": up, "look": forward}


# --- preview orientation strategies -----------------------------------------
#
# Where the preview looks from. Two strategies, because what makes a good angle
# depends on what is being drawn, and neither is obviously the last word --
# `orient_by_search` in particular is a guess-and-check and may not survive, so
# it is kept behind the same seam as the other and can be dropped without
# touching anything that calls it.
#
# Both take an OrientedBox and the viewport's aspect, and return a camera frame.


class OrientedBox(NamedTuple):
    """A box in the world: where it is, which way it lies, and how big it is.

    Not an axis-aligned bounding box. A single timber has its own axes and is
    usually not square to the world, and orienting a view around its true box
    rather than the world box it happens to occupy is the difference between
    seeing the piece and seeing the space it takes up.
    """

    centre: List[float]
    axes: Tuple[List[float], List[float], List[float]]
    half_sizes: Tuple[float, float, float]

    def reach(self, direction: List[float]) -> float:
        """How far the box extends along a direction, from its centre."""
        return sum(
            abs(sum(direction[i] * self.axes[axis][i] for i in range(3))) * self.half_sizes[axis]
            for axis in range(3)
        )

    def silhouette_area(self, look: List[float]) -> float:
        """How much of the box a viewer sees, looking along `look`.

        Exact for a box: each face pair contributes its area scaled by how
        squarely it faces the camera.
        """
        a, b, c = self.half_sizes
        faces = ((a, 4 * b * c), (b, 4 * a * c), (c, 4 * a * b))
        return sum(
            abs(sum(look[i] * self.axes[axis][i] for i in range(3))) * area
            for axis, (_, area) in enumerate(faces)
        )

    @property
    def longest_axis(self) -> int:
        return max(range(3), key=lambda axis: self.half_sizes[axis])


def _world_box(centre: List[float], half_size: List[float]) -> OrientedBox:
    """The world-aligned box a group of members occupies."""
    return OrientedBox(
        centre=centre,
        axes=([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]),
        half_sizes=(half_size[0], half_size[1], half_size[2]),
    )


def _timber_box(entry: Dict[str, Any]) -> OrientedBox:
    """One timber's own box: its axes, its section, and its cut extent.

    The cut extent rather than the stock, for the same reason the elevations use
    it -- a timber with an end joint is not cut to length first, so its stock is
    not the piece anyone is looking at.
    """
    timber = entry["timber"]
    along = _vector3_to_floats(timber.get_length_direction_global())
    across = _vector3_to_floats(timber.get_width_direction_global())
    up = _vector3_to_floats(timber.get_height_direction_global())
    origin = _vector3_to_floats(timber.get_bottom_position_global())
    start, finish = _cut_extent(entry["cutTimber"], float(timber.length))
    middle = (start + finish) / 2.0
    return OrientedBox(
        centre=[origin[i] + along[i] * middle for i in range(3)],
        axes=(along, across, up),
        half_sizes=(
            (finish - start) / 2.0,
            float(timber.size[0]) / 2.0,
            float(timber.size[1]) / 2.0,
        ),
    )


def _preview_extent(box: OrientedBox, frame: Dict[str, Any], aspect: float) -> float:
    """How much of the world the preview has to hold, at this angle."""
    needed = max(box.reach(frame["up"]), box.reach(frame["right"]) / aspect)
    return max(0.001, needed * _PREVIEW_EXTENT_PADDING)


# A perspective view wants more room around the piece than an elevation does.
_PREVIEW_EXTENT_PADDING = 1.6

# Where the search may look from. Every compass direction, and a few heights
# above the horizon -- never level with it or straight down, where an upright
# camera has no up left to speak of.
_PREVIEW_AZIMUTH_STEPS = 24
_PREVIEW_ELEVATIONS_DEG = (20.0, 35.0, 50.0)


def _preview_look_candidates() -> List[List[float]]:
    candidates: List[List[float]] = []
    for elevation_deg in _PREVIEW_ELEVATIONS_DEG:
        elevation = math.radians(elevation_deg)
        for step in range(_PREVIEW_AZIMUTH_STEPS):
            azimuth = 2 * math.pi * step / _PREVIEW_AZIMUTH_STEPS
            # Looking down from above, so the z part is negative.
            candidates.append([
                math.cos(azimuth) * math.cos(elevation),
                math.sin(azimuth) * math.cos(elevation),
                -math.sin(elevation),
            ])
    return candidates


def orient_by_search(box: OrientedBox, aspect: float, preserve_up: bool = True) -> Dict[str, Any]:
    """Try a few dozen angles and keep the one that shows the piece best.

    What is maximized is how long the box's longest axis appears once the view
    has been sized to fit it. The obvious measure -- how much of the viewport
    the silhouette fills -- is worse than useless, because it is always won by
    looking straight down the length of the piece: an end-on view fits
    beautifully and shows nothing. Length on screen goes to zero there instead.

    Two angles that show the piece equally long are separated by which shows
    more of it, so a square-on view loses to a three-quarter one.

    With `preserve_up` the candidates are upright, so world +Z stays up the
    screen. That is what several timbers want: a frame read at a tilt is harder
    to follow than one drawn slightly smaller, and which way is up is part of
    what the preview is telling you.

    There is very likely a closed form for this -- the best angle for a box in a
    viewport of a given aspect is not a hard problem, and someone has certainly
    solved it. Guessing and checking is fine here: it is a few dozen candidates
    against one box, it runs once when a drawing is asked for rather than per
    frame, and being able to change the scoring by reading it is worth more than
    being clever.
    """
    longest = box.half_sizes[box.longest_axis]
    axis = box.axes[box.longest_axis]
    best_frame = _camera_frame_looking([-1.0, 1.0, -0.75])
    best_length = -1.0
    best_area = -1.0
    for look in _preview_look_candidates():
        frames = [_camera_frame_looking(look)]
        if not preserve_up:
            # Also allow the piece's own length to be the screen's up, which
            # suits a long timber in a tall viewport and puts the world on its
            # side to get it.
            frames.append(_frame_from_look_and_up(look, axis))
        for frame in frames:
            extent = _preview_extent(box, frame, aspect)
            across = sum(frame["right"][i] * axis[i] for i in range(3)) * longest
            up_screen = sum(frame["up"][i] * axis[i] for i in range(3)) * longest
            on_screen = math.sqrt(across * across + up_screen * up_screen) / extent
            area = box.silhouette_area(_normalize(look))
            # Within a couple of percent counts as the same length, and then
            # the view that shows more of the piece wins.
            if on_screen > best_length * 1.02 or (on_screen > best_length * 0.98 and area > best_area):
                best_length = max(best_length, on_screen)
                best_area = area
                best_frame = frame
    return best_frame


# Where a single piece is looked at from, in its own frame: off to one side,
# above, and a little towards one end, so a long face, a short face and an end
# are all in view.
_PIECE_LOOK_IN_BOX = (0.38, 0.86, -0.55)


def orient_from_box(box: OrientedBox, aspect: float) -> Dict[str, Any]:
    """Look at a box from a fixed three-quarter angle in its own frame.

    For a single piece there is nothing to search for: the box is the timber, so
    the angle that shows it well is the same angle every time, expressed in the
    timber's own axes rather than the world's. A post and a brace lying at forty
    degrees get the same view of themselves.

    The piece is laid along whichever way the viewport is longer, since that is
    the direction there is room in.
    """
    length, across, up = box.axes
    look = _normalize([
        length[i] * _PIECE_LOOK_IN_BOX[0]
        + across[i] * _PIECE_LOOK_IN_BOX[1]
        + up[i] * _PIECE_LOOK_IN_BOX[2]
        for i in range(3)
    ])
    longest = box.axes[box.longest_axis]
    # A tall viewport wants the piece standing up in it, a wide one wants it
    # lying down -- so the long axis goes up the screen only in the first.
    up_hint = longest if aspect < 1 else up
    return _frame_from_look_and_up(look, up_hint)


def _frame_from_look_and_up(look: List[float], up_hint: List[float]) -> Dict[str, Any]:
    """An orthonormal frame looking along `look`, as close to `up_hint` as it can.

    Falls back to the upright frame when the hint is along the view direction,
    where it says nothing about which way is up.
    """
    forward = _normalize(look)
    along = sum(up_hint[i] * forward[i] for i in range(3))
    up = [up_hint[i] - along * forward[i] for i in range(3)]
    if sum(component * component for component in up) < 1e-9:
        return _camera_frame_looking(look)
    up = _normalize(up)
    return {"right": _normalize(_cross(forward, up)), "up": up, "look": forward}


def _preview_viewport(
    rect: List[float],
    box: OrientedBox,
    page: Dict[str, Any],
    orbit: Dict[str, Any],
    orient,
) -> Dict[str, Any]:
    """The live 3D view beside the elevations, pointed at what is being drawn.

    Left to itself the viewer builds a camera at the origin looking at nothing
    in particular, which for a piece standing away from the origin means an
    empty preview. `orient` is the strategy that picks the angle and `orbit`
    says how far it may be turned afterwards.
    """
    aspect = _viewport_aspect(rect, page)
    frame = orient(box, aspect)
    centre = box.centre
    return {
        "id": "preview",
        "rect": rect,
        "locked": False,
        "projection": "perspective",
        "orbit": orbit,
        "camera": {
            **frame,
            "target": centre,
            "extent": _preview_extent(box, frame, aspect),
        },
    }


def _long_face_viewports(entry: Dict[str, Any], page: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The four long sides of one timber, stacked, each square-on to its face."""
    timber = entry["timber"]
    along = _vector3_to_floats(timber.get_length_direction_global())
    axes = {
        "width": _vector3_to_floats(timber.get_width_direction_global()),
        "height": _vector3_to_floats(timber.get_height_direction_global()),
    }
    centre, half_size = _members_world_bounds([entry])

    viewports: List[Dict[str, Any]] = []
    for view_id, axis_name, sign in _LONG_FACE_VIEWS:
        normal = [component * sign for component in axes[axis_name]]
        frame = _camera_looking_at_face(normal, along)
        rect = _LONG_FACE_RECTS[view_id]
        viewports.append({
            "id": view_id,
            "rect": rect,
            "locked": True,
            "projection": "orthographic",
            "camera": {
                **frame,
                "target": centre,
                "extent": _view_extent(
                    half_size, frame["right"], frame["up"], _viewport_aspect(rect, page),
                ),
            },
        })
    return viewports


def _world_elevation_viewports(
    entries: List[Dict[str, Any]], page: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Front, top and right elevations in world axes, for a group of members."""
    centre, half_size = _members_world_bounds(entries)
    viewports: List[Dict[str, Any]] = []
    for view_id, right, up, look in _DEBUG_DRAWING_VIEWS:
        rect = _SELECTION_QUADRANTS[view_id]
        viewports.append({
            "id": view_id,
            "rect": rect,
            "locked": True,
            "projection": "orthographic",
            "camera": {
                "right": right,
                "up": up,
                "look": look,
                "target": centre,
                "extent": _view_extent(half_size, right, up, _viewport_aspect(rect, page)),
            },
        })
    return viewports


def _unique_drawing_id(base: str, taken: set) -> str:
    """A drawing id nothing else is using. Drawing the same piece twice is fine."""
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def _selection_drawing_name(entries: List[Dict[str, Any]], total: int) -> str:
    """What to call a drawing nobody has named.

    One piece is called after the piece, which is what anyone would call it.
    Several are counted, since listing them would not fit and would not help.
    """
    if len(entries) == 1:
        return entries[0]["displayName"]
    if not entries:
        return f"whole frame ({total})"
    return f"{len(entries)} members"


def create_drawing_from_selection(frame: Any, member_keys: List[str]) -> Dict[str, Any]:
    """A drawing of the selected members, on a sheet.

    One timber is drawn the way a piece is drawn for the shop: its four long
    faces rolled out down the sheet with a live preview beside them, each view
    square-on to a face and with the length running across the page. Several
    members have no single piece whose faces the drawing could be about, so they
    get world elevations instead.

    The drawing names its members. The scene still holds every timber -- the
    rest are ghosted, present for context and not part of what is drawn.
    """
    page = dict(_SELECTION_DRAWING_PAGE)
    timber_entries, _ = _assign_member_keys(frame)
    wanted = list(member_keys or [])
    by_key = {entry["memberKey"]: entry for entry in timber_entries}
    entries = [by_key[key] for key in wanted if key in by_key]

    drawn = entries or timber_entries
    centre, half_size = _members_world_bounds(drawn)

    if len(entries) == 1:
        viewports = _long_face_viewports(entries[0], page)
        preview_rect = _LONG_FACE_RECTS["preview"]
        # One piece: oriented from its own box rather than the world box it
        # happens to occupy, and turned about its own length, so it can be
        # looked at from every side without ever being tumbled out of the
        # attitude it is drawn in.
        preview_box = _timber_box(entries[0])
        orient = orient_from_box
        orbit = {"mode": "axis", "axis": list(preview_box.axes[0])}
    else:
        # No selection is treated as the whole frame, so asking for a drawing
        # before selecting anything gives you something rather than nothing.
        viewports = _world_elevation_viewports(entries or timber_entries, page)
        preview_rect = _SELECTION_QUADRANTS["preview"]
        # Several pieces have no length of their own to speak of, so the angle
        # is searched for -- and kept upright, since which way is up is part of
        # what a preview of an assembly is telling you.
        preview_box = _world_box(centre, half_size)
        orient = orient_by_search
        orbit = {"mode": "free"}

    members = [entry["memberKey"] for entry in entries]
    for viewport in viewports:
        viewport["members"] = members or None
        viewport["ghostOthers"] = True
        viewport["measurements"] = []
    viewports.append(_preview_viewport(preview_rect, preview_box, page, orbit, orient))

    return {
        "id": SELECTION_DRAWING_ID,
        "name": _selection_drawing_name(entries, len(timber_entries)),
        "members": members,
        "page": page,
        # A drawing shows no camera gizmos.
        "cameraControls": [],
        "viewports": viewports,
    }


# --- where drawings come from ------------------------------------------------
#
# Two sources. The frame asks for drawings in code (Frame.drawings), and a
# drawings file may override those and add its own. Which of the two a drawing
# came from is carried on it, because it is the first thing you want to know
# when one looks wrong: whether to edit the python or the file.

ORIGIN_CODE = "code"
ORIGIN_OVERRIDDEN = "overridden"
ORIGIN_FILE = "file"


# --- measurements -----------------------------------------------------------
#
# Two tiers: from the file, and not. A file measurement overrides the one
# beneath it with the same identity, which is the whole rule. It still produces
# the three states worth marking -- untouched code, code the file has overridden,
# and one the file introduced.

MEASURE_SUPPRESSED = "suppressed"

# Warned about once per parse rather than per duplicate: a hand-edited file with
# a repeated entry would otherwise fill the log with the same sentence.
_duplicate_warning_given = False


def _measure_identity(measure: Dict[str, Any]) -> Tuple[str, str, str]:
    """What makes a measurement itself, within the viewport it is drawn in.

    The anchors unordered, since measuring A to B is measuring B to A, plus an
    id for when the same pair is measured twice in the same viewport. Scoped to
    the viewport because that is where a measurement lives: the same anchors in
    the plan view are a different dimension with a different number, not this
    one seen from elsewhere.
    """
    anchors = sorted((str(measure.get("a") or ""), str(measure.get("b") or "")))
    return (anchors[0], anchors[1], str(measure.get("measureId") or ""))


def _serialize_code_measure(measure: Any) -> Dict[str, Any]:
    return {
        "a": measure.anchor_a,
        "b": measure.anchor_b,
        "measureId": measure.measure_id,
        "origin": ORIGIN_CODE,
    }


def merge_measurements(
    code_measures: List[Dict[str, Any]],
    file_measures: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """The measurements of one drawing, from both tiers.

    A file entry with the same identity as a code one replaces it and is marked
    as overriding; one with an identity nothing else has is the file's own. An
    entry marked suppressed removes the code measurement instead of replacing
    it, which is how a measurement an algorithm produced and nobody wants goes
    away without the algorithm being changed.

    A repeated identity within a tier is a mistake rather than a case to
    resolve, so the later one wins. Refusing the file outright would cost
    someone their drawings over a stray duplicate, which is the same trade the
    file parser already makes.
    """
    global _duplicate_warning_given
    from_file: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for measure in file_measures:
        identity = _measure_identity(measure)
        if identity in from_file and not _duplicate_warning_given:
            log_stderr(
                "Warning: two measurements share an identity; the later one wins. "
                "Give one of them a measureId to tell them apart."
            )
            _duplicate_warning_given = True
        from_file[identity] = measure

    merged: List[Dict[str, Any]] = []
    used = set()
    for measure in code_measures:
        identity = _measure_identity(measure)
        override = from_file.get(identity)
        if override is None:
            merged.append({**measure, "origin": ORIGIN_CODE})
            continue
        used.add(identity)
        if override.get(MEASURE_SUPPRESSED) is True:
            continue
        merged.append({**measure, **override, "origin": ORIGIN_OVERRIDDEN})

    for identity, measure in from_file.items():
        if identity in used or measure.get(MEASURE_SUPPRESSED) is True:
            continue
        merged.append({**measure, "origin": ORIGIN_FILE})

    return merged


def _file_measurements_by_viewport(entry: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """A file drawing's measurements, off the viewports they hang from."""
    by_viewport: Dict[str, List[Dict[str, Any]]] = {}
    for viewport in (entry or {}).get("viewports") or []:
        if isinstance(viewport, dict) and isinstance(viewport.get("id"), str):
            by_viewport[viewport["id"]] = list(viewport.get("measurements") or [])
    return by_viewport


def _measurements_by_viewport(
    declared: Any,
    override: Optional[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """A drawing's measurements, merged tier over tier, under each viewport.

    Both tiers hang them off viewports, and the merge happens within one: the
    same anchors in another viewport are a different dimension, not this one
    again.
    """
    code_by_viewport = dict(getattr(declared, "measurements", None) or {}) if declared is not None else {}
    file_by_viewport = _file_measurements_by_viewport(override)
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for viewport in list(code_by_viewport) + [v for v in file_by_viewport if v not in code_by_viewport]:
        merged[viewport] = merge_measurements(
            [_serialize_code_measure(m) for m in code_by_viewport.get(viewport, ())],
            list(file_by_viewport.get(viewport) or []),
        )
    return merged


def _drawings_file_path(example_path: Path) -> Path:
    """Where a frame's drawings file lives.

    Under .kigumi rather than beside the source: writes there are already known
    not to wake the file watcher, since refresh stats land there on every
    refresh.
    """
    return example_path.parent / ".kigumi" / "drawings" / f"{example_path.stem}.json"


# What a file drawing names when it is overriding one the code declares. Kept
# separate from its own id so that an override is always recognisably an
# override: delete the python drawing and what is left is plainly a dangling
# entry, rather than something that quietly becomes a drawing in its own right.
OVERRIDES_KEY = "overridesPythonDrawing"


def _read_drawings_file(path: Path) -> List[Dict[str, Any]]:
    """The drawings file, in order, or nothing. A broken file is reported, not fatal.

    Losing a viewer because a hand-edited file has a comma out of place would be
    a poor trade for strictness, and the file is meant to be hand-edited.
    """
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log_stderr(f"Warning: could not read {path}: {exc}")
        return []
    if not isinstance(loaded, dict):
        return []
    drawings = loaded.get("drawings")
    if not isinstance(drawings, list):
        return []
    return [
        drawing for drawing in drawings
        if isinstance(drawing, dict) and isinstance(drawing.get("id"), str)
    ]


def _member_keys_for_paths(frame: Any, paths: List[str]) -> List[str]:
    """The member keys of the timbers a code drawing names, by ticket path."""
    timber_entries, _ = _assign_member_keys(frame)
    wanted = set(paths or [])
    return [entry["memberKey"] for entry in timber_entries if entry["displayName"] in wanted]


def _drawing_from_code(frame: Any, declared: Any) -> Dict[str, Any]:
    """Turn what the frame asked for into a scene the viewer can render."""
    member_keys = _member_keys_for_paths(frame, list(declared.timber_paths))
    scene = create_drawing_from_selection(frame, member_keys)
    scene["id"] = declared.drawing_id
    scene["name"] = declared.name
    scene["members"] = member_keys
    return scene


def collect_drawings(
    frame: Any,
    example_path: Optional[Path],
    pending: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Every drawing for a frame: from the code, from the file, and unsaved.

    The file mirrors the code -- drawings holding viewports holding measurements
    -- and a file drawing says outright which code drawing it overrides, if any.
    So an override contributes measurements to a drawing the code still lays out,
    a file drawing that overrides nothing is a drawing in its own right, and one
    naming a code drawing that has gone is plainly a dangling override rather
    than something that has quietly become its own.

    `dirty` says a drawing is not in the file yet. It is worked out here rather
    than left for the viewer to infer, so there is one answer to it.
    """
    from_file = _read_drawings_file(_drawings_file_path(example_path)) if example_path else []
    overrides = {
        entry[OVERRIDES_KEY]: entry for entry in from_file
        if isinstance(entry.get(OVERRIDES_KEY), str)
    }
    drawings: List[Dict[str, Any]] = []
    overridden = set()

    for declared in list(getattr(frame, "drawings", None) or []):
        # The layout is always the code's. A file entry that wants a layout of
        # its own is a drawing of its own, which is what keeps adding one
        # dimension from taking a drawing's page and viewports with it.
        scene = _drawing_from_code(frame, declared)
        override = overrides.get(declared.drawing_id)
        if override is not None:
            overridden.add(id(override))
            scene["overriddenBy"] = override["id"]
        scene["origin"] = ORIGIN_CODE if override is None else ORIGIN_OVERRIDDEN
        _attach_measurements(scene, _measurements_by_viewport(declared, override), scene["name"])
        drawings.append(scene)

    for entry in from_file:
        if id(entry) in overridden:
            continue
        scene = dict(entry)
        scene.setdefault("name", scene["id"])
        target = entry.get(OVERRIDES_KEY)
        if isinstance(target, str):
            # It says it overrides something the code no longer declares. Shown
            # rather than dropped, and shown as what it is, so it can be pointed
            # somewhere else or deleted on purpose.
            scene["dangling"] = True
            log_stderr(
                f"Warning: drawing {scene['id']!r} overrides {target!r}, "
                "which the frame no longer declares."
            )
        scene["origin"] = ORIGIN_FILE
        _attach_measurements(scene, _measurements_by_viewport(None, entry), scene["name"])
        drawings.append(scene)

    for drawing in drawings:
        drawing["dirty"] = False

    # Made this session and not saved. A pending drawing that shares an id with
    # a saved one has been made since, so it wins -- it is the newer answer.
    for scene in (pending or []):
        entry = dict(scene)
        entry["dirty"] = True
        entry.setdefault("origin", ORIGIN_FILE)
        replaced = next((d for d in drawings if d["id"] == entry["id"]), None)
        if replaced is None:
            drawings.append(entry)
        else:
            drawings[drawings.index(replaced)] = entry

    return drawings


def _attach_measurements(
    scene: Dict[str, Any],
    by_viewport: Dict[str, List[Dict[str, Any]]],
    drawing_name: str,
) -> None:
    """Put each viewport's measurements on the viewport they belong to.

    A measurement is drawn in a viewport and means nothing outside it, so it
    travels with the viewport rather than with the drawing.

    Measurements naming a viewport this layout does not produce cannot be drawn,
    so they are not shown and the mismatch is warned about. They are kept all the
    same: a viewport can come back when the code changes, and dropping them here
    would mean the next save deleted them from the file for good.
    """
    remaining = dict(by_viewport)
    for viewport in scene.get("viewports") or []:
        viewport["measurements"] = remaining.pop(viewport.get("id"), [])
    unplaceable = {
        viewport: measures for viewport, measures in remaining.items() if measures
    }
    for viewport in unplaceable:
        log_stderr(
            f"Warning: drawing {drawing_name!r} has measurements for viewport "
            f"{viewport!r}, which it does not have. They are kept but not shown."
        )
    scene["unplaceableMeasurements"] = unplaceable


def _savable_drawing(drawing: Dict[str, Any]) -> Dict[str, Any]:
    """One drawing as the file should hold it.

    Measurements the code produced are left out. Writing them would freeze what
    an algorithm generates into the file, and it would stop following the
    algorithm the moment the frame changed -- the same reason an untouched code
    drawing is not written out either.
    """
    saved = {
        key: value for key, value in drawing.items()
        if key not in ("origin", "dirty", "unplaceableMeasurements", "overriddenBy", "dangling")
    }

    def keepers(measures):
        return [
            {key: value for key, value in measure.items() if key != "origin"}
            for measure in (measures or [])
            if measure.get("origin") in (ORIGIN_OVERRIDDEN, ORIGIN_FILE)
        ]

    # Written back the way the file holds them: on the viewports. An override
    # keeps only the ids, since the layout is the code's; a drawing of its own
    # keeps whatever it had.
    is_override = isinstance(drawing.get(OVERRIDES_KEY), str)
    viewports: List[Dict[str, Any]] = []
    for viewport in saved.get("viewports") or []:
        kept = keepers(viewport.get("measurements"))
        if is_override and not kept:
            continue
        entry = {"id": viewport.get("id")} if is_override else dict(viewport)
        entry["measurements"] = kept
        viewports.append(entry)
    # Ones that could not be placed keep their viewport, so they come back if it
    # does rather than being deleted by the next save.
    for viewport, measures in (drawing.get("unplaceableMeasurements") or {}).items():
        kept = keepers(measures)
        if kept:
            viewports.append({"id": viewport, "measurements": kept})
    saved["viewports"] = viewports
    return saved


def write_drawings_file(example_path: Path, drawings: List[Dict[str, Any]]) -> str:
    """Save the drawings that are the file's to keep.

    Only the ones the file is responsible for: a drawing that came from code and
    was never touched has nothing to save, and writing it out would freeze a
    copy that stops following the code it was asked for by.
    """
    path = _drawings_file_path(example_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = [_savable_drawing(drawing) for drawing in drawings
            if drawing.get("origin") in (ORIGIN_OVERRIDDEN, ORIGIN_FILE)]
    path.write_text(json.dumps({"drawings": keep}, indent=2) + "\n", encoding="utf-8")
    return str(path)


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
        timber_to_kumiki_and_cut[timber_id] = (entry["kumikiEphemeralId"], entry["cutTimber"])

    timber_tags_by_kumiki_id: Dict[int, List[str]] = {}
    for entry in timber_entries:
        timber_ticket = getattr(entry.get("timber"), "ticket", None)
        timber_tags_by_kumiki_id[entry["kumikiEphemeralId"]] = _serialize_timber_tags(timber_ticket)

    # Extract joint records from source_joints
    source_joints = list(getattr(frame, "source_joints", ()) or ())
    accessory_kumiki_ephemeral_to_joint: Dict[int, int] = {}

    joints_payload: List[Dict[str, Any]] = []
    for joint in source_joints:
        joint_ticket = getattr(joint, "ticket", None)
        if joint_ticket is None:
            continue
        
        joint_kumiki_id = int(getattr(joint_ticket, "kumiki_id", 0))
        joint_name = _joint_display_name(joint)
        joint_type = getattr(joint_ticket, "joint_type", None)
        
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
                    "timberKumikiEphemeralId": timber_kumiki_id,
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
                accessory_kumiki_ephemeral_to_joint[accessory_kumiki_id] = joint_kumiki_id

        joints_payload.append({
            "kumikiEphemeralId": joint_kumiki_id,
            "name": joint_name,
            "jointType": joint_type,
            "members": members_list,
            "accessoryKumikiEphemeralIds": accessory_kumiki_ids,
        })

    timbers_payload: List[Dict[str, Any]] = []
    for entry in timber_entries:
        cuts_meta = _serialize_cutting_summary(entry["cutTimber"])
        timbers_payload.append({
            "kumikiEphemeralId": entry["kumikiEphemeralId"],
            "memberKey": entry["memberKey"],
            "name": entry["displayName"],
            "tags": list(timber_tags_by_kumiki_id.get(entry["kumikiEphemeralId"], [])),
            "cuts": cuts_meta,
        })

    accessories_payload: List[Dict[str, Any]] = []
    for entry in accessory_entries:
        accessories_payload.append({
            "kumikiEphemeralId": entry["kumikiEphemeralId"],
            "memberKey": entry["memberKey"],
            "name": entry["displayName"],
            "type": entry["type"],
            "jointKumikiEphemeralId": accessory_kumiki_ephemeral_to_joint.get(entry["kumikiEphemeralId"]),
        })

    # Solving the disassembly can take a while on big frames, so the layers
    # payload only announces whether a solve is COMING ({"pending": true});
    # the extension then issues a separate get_assembly request and forwards
    # the solved payload to the viewer, which shows a loading state meanwhile.
    return {
        "frameName": frame.name if hasattr(frame, "name") else None,
        "timbers": timbers_payload,
        "accessories": accessories_payload,
        "joints": joints_payload,
        "assembly": {"pending": True} if _frame_has_assembly_freedoms(frame) else None,
    }


def _frame_has_assembly_freedoms(frame: Any) -> bool:
    """Cheap gate mirroring solve_frame_assembly's: does any joint member
    declare an assembly freedom? (No solving involved.)"""
    source_joints = list(getattr(frame, "source_joints", ()) or ())
    for joint in source_joints:
        for cutting in joint.cuttings.values():
            if cutting.assembly_freedom is not None:
                return True
        for accessory in joint.jointAccessories.values():
            if accessory.assembly_freedom is not None:
                return True
    return False


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
    should_cancel: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Solve the frame's assembly sequence for the viewer's preview timeline.

    Returns None when no member of any joint declares an assembly freedom
    (the viewer hides the timeline). Payload shape:

        {"steps": [{"order": int, "suborder": int, "substep": int,  # substep is 1-based
                    "movements": [{"kumikiEphemeralId": int, "memberKey": str,
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
        member_key_by_kumiki_id[entry["kumikiEphemeralId"]] = entry["memberKey"]
    for entry in accessory_entries:
        member_key_by_kumiki_id[entry["kumikiEphemeralId"]] = entry["memberKey"]

    try:
        solution = solve_frame_assembly(frame, should_cancel=should_cancel)
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
                "kumikiEphemeralId": int(movement.member_key),
                "memberKey": member_key,
                "direction": [_assembly_float(movement.direction[i, 0]) for i in range(3)],
                "distance": _assembly_float(movement.distance),
                "dragged": bool(movement.dragged),
            })
        steps_payload.append({
            "order": int(step.ordering.order),
            "suborder": int(step.ordering.suborder),
            "substep": int(step.substep),
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


def _serialize_feature(feature: Any) -> Dict[str, Any]:
    """One declared feature, with the metadata the tree view wants to show."""
    return {
        "name": feature.name,
        "type": feature.feature_type().name,
        "group": feature.group.name,
        "real": feature.real,
    }


def _serialize_csg_node(
    csg: 'CutCSG',
    path: List[str],
    role: Optional[str],
    attribution: _CutAttribution,
    cut_timber: 'CutTimber',
    parity: 'CSGParity',
) -> Dict[str, Any]:
    """One CSG node and everything beneath it.

    Nested rather than flattened, and every node rather than only labelled
    ones. This is a debugging surface: the shape of the tree, and the untagged
    intermediates in it, are exactly what you need when the shape is what has
    gone wrong. `path` still carries labels only, since that is what
    find_csg_by_path navigates by.
    """
    from kumiki.cutcsg import (
        Difference, Intersection, SolidUnion, csg_children, csg_children_with_parity,
    )

    # role says which edge a child sits on; parity says what that edge means
    # for the finished solid, and the two differ -- two subtract edges cancel.
    # The rule itself lives in kumiki, stated once.
    child_parity = {
        id(child): child_par
        for child, child_par in csg_children_with_parity(csg, parity)
    }

    label = _label_name(csg)
    node_path = path + [label] if label else path

    node: Dict[str, Any] = {
        # kind is the class name and stays machine-readable -- the viewer keys
        # structural decisions off it. displayName is the word people read.
        "kind": type(csg).__name__,
        "displayName": type(csg).display_name(),
        "label": label,
        "path": list(node_path),
        "role": role,
        "parity": parity.name,
        "jointName": attribution.joint_name,
        "jointId": attribution.joint_id,
        "cutIndex": attribution.cut_index,
        "features": [_serialize_feature(f) for f in csg.get_declared_features()],
        "children": [],
    }

    def child(node_csg: 'CutCSG', child_role: str, child_attribution: _CutAttribution) -> None:
        node["children"].append(_serialize_csg_node(
            node_csg, node_path, child_role, child_attribution, cut_timber,
            child_parity.get(id(node_csg), parity),
        ))

    if isinstance(csg, Difference):
        child(csg.base, "base", attribution)
        cuts = list(getattr(cut_timber, "cuts", []) or [])
        # Only the timber's own top-level Difference lines up with its cuts;
        # a nested one inside a joint's own geometry does not, so attribution
        # is inherited there rather than re-derived.
        aligned = len(csg.subtract) == len(cuts) and not path
        joints_by_cutting = _joint_by_cutting_id(cut_timber) if aligned else {}
        for index, sub_csg in enumerate(csg.subtract):
            sub_attribution = attribution
            if aligned:
                sub_attribution = _cut_attribution(joints_by_cutting, cuts[index], index)
            child(sub_csg, "subtract", sub_attribution)
    elif isinstance(csg, SolidUnion):
        for member in csg.children:
            child(member, "child", attribution)
    elif isinstance(csg, Intersection):
        child(csg.left, "left", attribution)
        child(csg.right, "right", attribution)

    return node


def serialize_cut_csg_tree(cut_timber: 'CutTimber') -> Dict[str, Any]:
    """The whole rendered CSG of a timber, as a nested tree.

    Deliberately the rendered tree -- what picking actually runs against --
    rather than one cutting's negative CSG, which is a piece of the input and
    not the thing on screen.
    """
    from kumiki.cutcsg import CSGParity

    local_csg = cut_timber.render_timber_with_cuts_csg_local()
    return {"tree": _serialize_csg_node(
        local_csg, [], None, NO_CUT_ATTRIBUTION, cut_timber, CSGParity.ADDITIVE)}


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
            "get_default_drawing_for_debugging",
            "create_drawing_from_selection",
            "get_drawings", "save_drawings",
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

def _build_inv_transform_float(transform: Any) -> Tuple[List[List[float]], List[float]]:
    """Pre-compute float data for global→local.  Returns (rot_cols, position).
    local = R^T * (global - pos) where rot_cols is the FORWARD rotation matrix."""
    M = transform.orientation.matrix
    P = transform.position
    rot = [[float(M[r, c]) for c in range(3)] for r in range(3)]
    pos = [float(P[i]) for i in range(3)]
    return rot, pos


def _inv_transform_point(rot: List[List[float]], pos: List[float], global_pt: List[float]) -> List[float]:
    """Apply inverse transform: local = R^T * (global_pt - pos)."""
    dx = global_pt[0] - pos[0]
    dy = global_pt[1] - pos[1]
    dz = global_pt[2] - pos[2]
    return [
        rot[0][0]*dx + rot[1][0]*dy + rot[2][0]*dz,
        rot[0][1]*dx + rot[1][1]*dy + rot[2][1]*dz,
        rot[0][2]*dx + rot[1][2]*dy + rot[2][2]*dz,
    ]


def _subtree_contains(root: 'CutCSG', target: 'CutCSG') -> bool:
    """Whether *target* is *root* or somewhere beneath it.

    """
    from kumiki.cutcsg import csg_children

    # note this is identity comparison, not quality as 2 CutCSGs can be `==` equivalent but not the same
    if root is target:
        return True
    return any(_subtree_contains(child, target) for child in csg_children(root))


def _joint_by_cutting_id(cut_timber: 'CutTimber') -> Dict[int, 'Joint']:
    """{id(cutting): joint} for the joints that cut this timber.

    A Joint already owns its cuttings, so the reverse link is derived here.

    Reads CutTimber.joints rather than Frame.source_joints, which keeps this
    local to the timber being picked: no frame has to be threaded through, and
    a Frame assembled by some route other than from_joints does not silently
    lose the ability to name joints. Empty for a CutTimber built by hand,
    where attribution is unavailable rather than wrong.
    """
    lookup: Dict[int, 'Joint'] = {}
    for joint in getattr(cut_timber, "joints", None) or ():
        for cutting in (getattr(joint, "cuttings", None) or {}).values():
            lookup[id(cutting)] = joint
    return lookup


def _cutting_for_node(
    local_csg: 'CutCSG',
    cut_timber: 'CutTimber',
    target: 'CutCSG',
) -> Optional['Cutting']:
    """Which Cutting produced *target*, or None if it is the timber body.

    render_timber_with_cuts_csg_local() builds
    ``Difference(body, [cut.get_negative_csg_local() for cut in cuts])`` -- one
    subtract child per cutting, in order. That correspondence is created in a
    single function, so this reads it in a single function; everything else
    here is identity-based.
    """
    from kumiki.cutcsg import Difference

    if not isinstance(local_csg, Difference):
        return None
    cuts = list(getattr(cut_timber, "cuts", []) or [])
    if len(local_csg.subtract) != len(cuts):
        return None  # shape changed under us; decline rather than guess
    for subtree, cutting in zip(local_csg.subtract, cuts):
        if _subtree_contains(subtree, target):
            return cutting
    return None


def _joint_display_name(joint: 'Joint') -> str:
    """How to show *joint* wherever a joint is named.

    The one implementation of that rule, in name-then-type-then-id order:
    the name its ticket was given, else the kind of joint it is, else its
    kumiki id. The id rather than a shared placeholder because several
    unnamed joints can touch one timber, and "which of these did I just
    click?" is the question the display exists to answer. It is runtime-only,
    which is fine here -- this string is shown, never stored.

    The layers payload and the CSG tree both call this. They used to derive
    it separately and disagree: a joint with a type but no name showed as its
    type in the joint list and as an id everywhere else.
    """
    from kumiki.ticket import UNNAMED_TICKET_PATH

    ticket = getattr(joint, "ticket", None)
    if ticket is None:
        return "<unnamed joint>"  # no ticket, so no id to distinguish it by
    name = ticket.get_name()
    if name and name != UNNAMED_TICKET_PATH:
        return name
    joint_type = getattr(ticket, "joint_type", None)
    if joint_type:
        return joint_type
    return f"<unnamed joint - {ticket.kumiki_id}>"


def _joint_for_cutting(cut_timber: 'CutTimber', cutting: 'Cutting') -> Optional['Joint']:
    """The joint that owns *cutting*, or None if none does."""
    return _joint_by_cutting_id(cut_timber).get(id(cutting))


def _joint_name_for_cutting(cut_timber: 'CutTimber', cutting: 'Cutting') -> Optional[str]:
    """Display name of the joint that owns *cutting*, or None if it owns none."""
    joint = _joint_for_cutting(cut_timber, cutting)
    return None if joint is None else _joint_display_name(joint)


class _CutAttribution(NamedTuple):
    """Which cutting -- and which joint -- a CSG node belongs to.

    Inherited by the whole subtree under a cutting's negative CSG, so the
    viewer can read attribution off any node instead of walking back up to the
    top tier to find it. All three fields are None for the timber body.

    joint_id is the joint ticket's kumiki_id as a string, matching the id the
    layers payload uses, so the joint list can join against it directly.
    """

    joint_name: Optional[str] = None
    joint_id: Optional[str] = None
    cut_index: Optional[int] = None


NO_CUT_ATTRIBUTION = _CutAttribution()


def _cut_attribution(
    joints_by_cutting: Dict[int, 'Joint'],
    cutting: 'Cutting',
    cut_index: int,
) -> _CutAttribution:
    """Attribution for one top-tier cutting, given a prebuilt joint lookup."""
    joint = joints_by_cutting.get(id(cutting))
    if joint is None:
        # The cut is real and indexable even when no joint claims it.
        return _CutAttribution(cut_index=cut_index)
    ticket = getattr(joint, "ticket", None)
    joint_id = None if ticket is None else str(ticket.kumiki_id)
    return _CutAttribution(_joint_display_name(joint), joint_id, cut_index)


def _joint_name_for_node(
    local_csg: 'CutCSG',
    cut_timber: 'CutTimber',
    target: 'CutCSG',
) -> Optional[str]:
    """Display name of the joint that produced *target*, if any."""
    cutting = _cutting_for_node(local_csg, cut_timber, target)
    if cutting is None:
        return None
    return _joint_name_for_cutting(cut_timber, cutting)


def _label_name(labeled: Any) -> Optional[str]:
    """The name a CSG node or a Cutting carries, or None if nobody named it.

    Both hold a CutCSGLabel, never a bare string and never None, so the name
    lives one level in. Kept in one place because the runner reads it from a
    dozen spots while navigating -- and because a CutCSGLabel that reaches the
    payload unwrapped would serialize as an object where the viewer expects a
    string.
    """
    return getattr(getattr(labeled, "label", None), "name", None)


def _declared_feature_names(csg: Any) -> List[str]:
    """Names of the features *csg* declares, in declaration order."""
    names: List[str] = []
    for declared in csg.get_declared_features():
        if declared.name not in names:
            names.append(declared.name)
    return names


def _to_v3(pt: List[float]) -> Any:
    """Wrap a plain [x, y, z] in the V3 kumiki's CSG API expects."""
    from kumiki.rule import create_v3
    return create_v3(float(pt[0]), float(pt[1]), float(pt[2]))


def _csg_contains_point(csg: Any, local_pt: List[float], eps: float = 1e-4) -> bool:
    """True if *local_pt* (timber-local floats) is inside *csg*, within *eps*."""
    return csg.contains_point(_to_v3(local_pt), eps)


def _csg_point_on_boundary(csg: Any, local_pt: List[float], eps: float = 1e-4) -> bool:
    """True if *local_pt* (timber-local floats) lies on the boundary of *csg*, within *eps*.

    These two are thin adapters over kumiki's own CutCSG methods. kigumi used to
    carry a parallel float reimplementation of both, from when kumiki was
    sympy-backed and a symbolic point test was too slow to run per raycast.
    kumiki is plain floats now, so the shadow copy bought nothing but drift --
    it covered only HalfSpace, RectangularPrism and Cylinder, which silently
    made every ConvexPolygonExtrusion, PathExtrusion, ConvexPolygonSimpleLoft
    and Intersection surface unselectable (the click fell through to the timber
    body and reported a bare "face").
    """
    return csg.is_point_on_boundary(_to_v3(local_pt), eps)


# Timber-local outward directions, used to name an unnamed face by whichever of
# the timber's own six faces it most points toward.
_TIMBER_LOCAL_FACE_NORMALS = (
    ("right", (1.0, 0.0, 0.0)), ("left", (-1.0, 0.0, 0.0)),
    ("front", (0.0, 1.0, 0.0)), ("back", (0.0, -1.0, 0.0)),
    ("top", (0.0, 0.0, 1.0)), ("bottom", (0.0, 0.0, -1.0)),
)


def _nearest_timber_local_face_name(normal: Any) -> str:
    """Name an outward *normal* (in timber-local space) by the timber face it
    most closely points along.

    A CSG primitive often lives in its own local frame, unrelated to the
    timber's length axis -- a tenon's marking_space local Z points along
    whichever way the tenon protrudes, not the timber's own top/bottom. Someone
    browsing a timber's faces only ever wants an answer relative to THAT
    timber, so the answer is always reported in the timber's own six
    directions.
    """
    n = [float(normal[0]), float(normal[1]), float(normal[2])]
    best_name, best_dot = "face", -2.0
    for name, direction in _TIMBER_LOCAL_FACE_NORMALS:
        dot = n[0] * direction[0] + n[1] * direction[1] + n[2] * direction[2]
        if dot > best_dot:
            best_dot, best_name = dot, name
    return best_name


def _detect_face_label(csg: Any, local_pt: List[float], eps: float = 1e-4) -> str:
    """Name the feature of primitive *csg* that *local_pt* lies on.

    Two layers, in order:

    1. The primitive's own named feature, via kumiki's CSGFeature lookup. This
       is authoritative -- a prism built in its own local frame (a tenon's
       marking_space, say) has a "top" that is not the timber's top, so a
       declared name always beats a geometric guess.
    2. Failing that, a generic label. Most joint geometry is still unnamed, so
       this is the common path today: name the face by whichever of the
       timber's own six directions its outward normal points along.

    HalfSpace and a cylinder's barrel get fixed names instead -- neither has a
    "face" in the timber's sense, and naming them by direction would read as a
    timber face that isn't there.
    """
    from kumiki.cutcsg import Cylinder, FeatureTestTolerances, HalfSpace
    from kumiki.rule import are_vectors_perpendicular

    point = _to_v3(local_pt)

    # The raycast tolerance is a surface tolerance: it covers the gap between
    # the analytic face and the triangulated mesh the ray actually hit. Edges
    # and points keep their (wider) defaults, since hitting one is a snap
    # rather than a direct hit.
    feature = csg.find_feature(point, FeatureTestTolerances(face=eps))
    if feature is not None:
        return feature.name

    if isinstance(csg, HalfSpace):
        return "cut_plane"

    normal = csg.get_outward_normal(point, eps)
    if normal is None:
        return "face"

    if isinstance(csg, Cylinder) and are_vectors_perpendicular(normal, csg.axis_direction):
        return "cylindrical_surface"

    # TODO this needs to know face parity
    return _nearest_timber_local_face_name(normal)


def _node_positions(root: 'CutCSG') -> Dict[int, Tuple[int, int, List[str]]]:
    """Every node in *root* keyed by id, as (depth, document order, label path).

    The label path is what the viewer navigates by, so unlabeled nodes
    contribute nothing to it -- the same way navigation drills through them
    transparently.
    """
    from kumiki.cutcsg import csg_children

    positions: Dict[int, Tuple[int, int, List[str]]] = {}
    order = 0

    def walk(node: Any, depth: int, path: List[str]) -> None:
        nonlocal order
        label = _label_name(node)
        node_path = path + [label] if label else path
        positions[id(node)] = (depth, order, node_path)
        order += 1
        for child in csg_children(node):
            walk(child, depth + 1, node_path)

    walk(root, 0, [])
    return positions


def _edge_owner(root: 'CutCSG', edge: Any) -> Optional[Tuple[Any, List[str]]]:
    """Which node a derived edge is shown under, and its path.

    A plane-plane edge belongs to two CSGs at once -- the shoulder half-space
    and the timber body, say -- and a tree can only show it in one place. The
    rule is the deeper of its two parents, with document order breaking a tie.

    That is sufficient for now: the edges worth marking are the ones where joint
    geometry meets a timber face, and the timber body sits at the top of every
    tree, so the joint side is always deeper and always wins. An edge between
    two nodes at the same depth is not something the joint library produces
    today; when it does, this is the rule to revisit.
    """
    parents = [hit for hit in (getattr(edge, "a", None), getattr(edge, "b", None))
               if hit is not None]
    if len(parents) != 2:
        return None

    positions = _node_positions(root)
    ranked = []
    for hit in parents:
        position = positions.get(id(hit.owner))
        if position is None:
            return None
        depth, order, path = position
        ranked.append(((depth, order), hit.owner, path))

    _rank, owner, path = max(ranked, key=lambda entry: entry[0])
    return owner, path


def _edge_tolerance() -> Any:
    """How close a vertex must be to an edge to count as on it.

    The same tolerance the edge was found with -- an edge is selected by
    snapping to it, so the highlight has to be as forgiving as the pick was.
    """
    from kumiki.cutcsg import FEATURE_EDGE_TOLERANCE

    return FEATURE_EDGE_TOLERANCE


def _edge_highlight_segment(
    edge_feature: Any,
    owner: 'CutCSG',
    mesh_vertices: List[float],
    timber_rot: List[List[float]],
    timber_pos: List[float],
) -> Optional[Dict[str, List[float]]]:
    """The stretch of a derived edge the mesh actually shows, in global space.

    An edge is a line, and a highlight built out of triangles can only ever
    approximate one -- it lights the strip beside it, which reads as a stray
    wedge rather than as the edge. The viewer draws a line instead, and this
    says where that line runs: the mesher puts vertices on edges, so the
    vertices lying on this one are the visible span, and its two extremes are
    its ends.

    Returns None when fewer than two vertices land on the edge, which leaves
    the caller its triangle-strip fallback.
    """
    on_edge: List[List[float]] = []
    tolerance = _edge_tolerance()
    for index in range(0, len(mesh_vertices), 3):
        vertex = [mesh_vertices[index], mesh_vertices[index + 1], mesh_vertices[index + 2]]
        local = _inv_transform_point(timber_rot, timber_pos, vertex)
        if edge_feature.test_point(owner, _to_v3(local), tolerance):
            on_edge.append(vertex)

    if len(on_edge) < 2:
        return None

    # The two furthest apart are the ends: everything on an edge is collinear,
    # so no projection axis is needed to order them.
    start, end, longest = on_edge[0], on_edge[1], -1.0
    for i in range(len(on_edge)):
        for j in range(i + 1, len(on_edge)):
            span = sum((on_edge[i][axis] - on_edge[j][axis]) ** 2 for axis in range(3))
            if span > longest:
                start, end, longest = on_edge[i], on_edge[j], span

    if longest <= 0:
        return None
    return {"start": start, "end": end}


def _features_at_point(root: 'CutCSG', local_pt: List[float], eps: float) -> List[Any]:
    """Every feature the WHOLE tree sees at the click, best first.

    Asked of the root rather than the node navigation landed on: a derived edge
    comes from a face on each of two different primitives, so it exists only
    where both are in scope. A leaf can never see one, which is why edges were
    unselectable from a click while the machinery for them worked.
    """
    from kumiki.cutcsg import FeatureTestTolerances

    return root.get_all_features(_to_v3(local_pt), FeatureTestTolerances(face=eps))


def _resolve_derived_edge(hits: List[Any]) -> Optional[Any]:
    """The derived edge under the click, if one is the best answer there."""
    from kumiki.cutcsg import CSGFeatureType

    if not hits:
        return None
    best = hits[0]
    if best.feature.feature_type() != CSGFeatureType.EDGE:
        return None
    return best.feature


def _describe_pick(
    target: 'CutCSG',
    local_csg: 'CutCSG',
    cut_timber: 'CutTimber',
    local_pt: List[float],
    eps: float,
    feature_label: Optional[str],
    feature_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Everything the selection display wants to say about one click.

    Kept separate from _detect_face_label, which runs per triangle during
    highlight extraction and must stay a cheap string lookup. This runs once.

    The three CSG-ish arguments are all about one timber and are easy to
    confuse, so, concretely:

    Args:
        target: the node the click resolved to. An ordinary click drills
            straight to a leaf primitive; a ctrl-click descends one level at a
            time, so under ctrl this is often a compound -- a SolidUnion or a
            Difference selected whole.
        local_csg: the ROOT of the tree `target` sits in, i.e.
            ``cut_timber.render_timber_with_cuts_csg_local()``. Needed because
            two of the four answers are about where `target` sits in the tree
            rather than about `target` itself: which joint produced it, and how
            many Difference.subtract edges lie above it (which decides whether
            its outward normal points the way the visible surface does).
        cut_timber: the timber that owns that tree. Supplies `cuts`, which line
            up with the root Difference's subtract children, and `joints`,
            which map a cutting back to the joint that made it.
        local_pt: the clicked point in TIMBER-LOCAL coordinates -- the same space as
            `local_csg` and `target`, not global. The caller converts.
        eps: surface tolerance for the hit, covering the gap between the
            analytic face and the triangulated mesh the ray struck.
        feature_label: the feature navigation actually resolved to, or None when
            the click selected `target` as a whole. Passed in rather than
            re-derived: asking `target` what lies under the point finds a face
            on a descendant even when no feature was selected, which made the
            display name a face while the highlight lit a whole union.
        feature_type: the type of that feature, when the caller already knows
            it. A derived edge has to be passed this way for the same reason
            its label does -- it belongs to two primitives, so `target` alone
            answers FACE for it. None means re-derive from `target`.

    Returns:
        nodeKind and nodeLabel, which always describe `target` itself;
        featureLabel, featureType and facesToward, which are None unless a
        feature was selected; and jointName, which is None for the timber's own
        body, since no joint produced that.
    """
    from kumiki.cutcsg import CSGFeatureType, FeatureTestTolerances

    described: Dict[str, Any] = {
        "nodeKind": type(target).__name__,
        "nodeDisplayName": type(target).display_name(),
        "nodeLabel": _label_name(target),
        "jointName": _joint_name_for_node(local_csg, cut_timber, target),
    }

    if feature_label is None:
        return {
            **described,
            "featureLabel": None,
            "featureType": None,
            "facesToward": None,
            "outwardNormal": None,
        }

    point = _to_v3(local_pt)
    hit = target.find_feature(point, FeatureTestTolerances(face=eps))
    resolved_type = feature_type
    if resolved_type is None and hit is not None:
        resolved_type = hit.feature_type().name
    normal, faces_toward = _outward_normal_and_face(target, local_csg, local_pt, eps)
    return {
        **described,
        # featureLabel is only a name when the primitive declared one. Without
        # that it is _detect_face_label's geometric guess, which the display
        # must not present as a name -- it is a direction, and one that has not
        # been sign-corrected, unlike the normal below.
        "featureLabel": feature_label,
        "featureType": resolved_type,
        "facesToward": faces_toward,
        "outwardNormal": normal,
    }


def _outward_normal_and_face(
    target: 'CutCSG',
    local_csg: 'CutCSG',
    local_pt: List[float],
    eps: float,
) -> Tuple[Optional[List[float]], Optional[str]]:
    """The outward normal at the pick, and which of the timber's own six faces
    it points most nearly along.

    The tree is already in the timber's local frame, so the normal is matched
    against the six local directions directly -- going via
    get_closest_oriented_face_from_global_direction would convert to global and
    straight back.

    The primitive supplies the direction and its parity supplies the sign. A
    primitive's own normal points out of that primitive, which is not always
    out of the finished timber: a mortise prism's points out of the hole and
    into the material, so the wall you clicked faces the other way. A
    SUBTRACTIVE node bounds a void, so its surface faces the opposite way to
    the solid.

    Parity rather than the root's own normal at the point, which is what this
    used to ask. That is a local geometric answer and it assumes the point is
    on the composed boundary without rechecking: Difference returns the base's
    normal without asking whether a subtract removed that point, and SolidUnion
    averages whichever children contain it without asking whether the result is
    on the union's surface. Both answer confidently for points that are not on
    the boundary at all, and averaging at an edge gives a bisector rather than
    a normal. Parity never consults the point, so none of that applies.

    Args:
        target: the leaf primitive that was hit, for the face direction.
        local_csg: the root of the tree it sits in, for the parity.
        local_pt: the clicked point, in that tree's (timber-local) space.
        eps: surface tolerance for the normal lookup.

    Returns:
        (normal, face name) in timber-local space, or (None, None) if no normal
        is available. The normal is the exact answer and the face name is the
        nearest of six, so the display can show both rather than rounding
        silently.
    """
    from kumiki.cutcsg import CSGParity, walk_csg_with_parity

    point = _to_v3(local_pt)
    normal = target.get_outward_normal(point, eps)
    if normal is None:
        return None, None
    # First occurrence: parity belongs to a position, and navigation hands back
    # the node rather than the path it took, so a subtree placed twice in one
    # tree could not be told apart here anyway.
    parity = next(
        (p for node, p in walk_csg_with_parity(local_csg) if node is target),
        None,
    )
    if parity is CSGParity.SUBTRACTIVE:
        normal = -normal
    as_floats = [float(normal[0]), float(normal[1]), float(normal[2])]
    return as_floats, _nearest_timber_local_face_name(normal)


def _resolve_csg_at_path(csg: Any, path: List[str], local_pt: Optional[List[float]] = None, eps: float = 1e-4) -> Any:
    """Walk the CSG tree following *path* of labeled CSG nodes.

    Searches through unlabeled intermediate Difference/SolidUnion nodes
    transparently.  When *local_pt* is given and multiple children share the
    same label, prefer the one whose boundary contains *local_pt*.
    """
    from kumiki.cutcsg import SolidUnion, Difference

    def _find_labeled(node: Any, label_name: str) -> List[Any]:
        """Return all descendants of *node* with the given *label*, searching
        through unlabeled compound intermediaries."""
        results: List[Any] = []
        children: List[Any] = []
        if isinstance(node, Difference):
            children = list(node.subtract)
            # Also check base
            base_label = _label_name(node.base)
            if base_label == label_name:
                results.append(node.base)
            elif isinstance(node.base, (SolidUnion, Difference)) and base_label is None:
                results.extend(_find_labeled(node.base, label_name))
        elif isinstance(node, SolidUnion):
            children = list(node.children)
        for ch in children:
            ch_label = _label_name(ch)
            if ch_label == label_name:
                results.append(ch)
            elif isinstance(ch, (SolidUnion, Difference)) and ch_label is None:
                results.extend(_find_labeled(ch, label_name))
        return results

    node = csg
    for name in path:
        candidates = _find_labeled(node, name)
        if not candidates:
            break
        if len(candidates) == 1 or local_pt is None:
            node = candidates[0]
        else:
            # Multiple with same name — pick the one on boundary
            picked = candidates[0]
            for c in candidates:
                if _csg_point_on_boundary(c, local_pt, eps):
                    picked = c
                    break
                if _csg_contains_point(c, local_pt, eps):
                    picked = c
            node = picked
    return node


def _navigate_csg_one_level(
    node: Any,
    local_pt: List[float],
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
            if _csg_point_on_boundary(sub, local_pt, eps):
                sub_label = _label_name(sub)
                if sub_label:
                    return (current_path + [sub_label], sub, None)
                # Unlabeled compound → drill through transparently
                if isinstance(sub, (SolidUnion, Difference)):
                    return _navigate_csg_one_level(sub, local_pt, current_path, eps)
                return (current_path, sub, _detect_face_label(sub, local_pt, eps))
        # Point is on the base surface
        base_label = _label_name(node.base)
        if base_label:
            return (current_path + [base_label], node.base, None)
        if isinstance(node.base, (SolidUnion, Difference)):
            return _navigate_csg_one_level(node.base, local_pt, current_path, eps)
        return (current_path, node.base, _detect_face_label(node.base, local_pt, eps))

    if isinstance(node, SolidUnion):
        for ch in node.children:
            if _csg_point_on_boundary(ch, local_pt, eps):
                ch_label = _label_name(ch)
                if ch_label:
                    return (current_path + [ch_label], ch, None)
                # Unlabeled compound → drill through transparently
                if isinstance(ch, (SolidUnion, Difference)):
                    return _navigate_csg_one_level(ch, local_pt, current_path, eps)
                return (current_path, ch, _detect_face_label(ch, local_pt, eps))
        # Couldn't match a specific child — report face of whole union
        return (current_path, node, "face")

    # Leaf primitive — report face
    return (current_path, node, _detect_face_label(node, local_pt, eps))


def _navigate_csg_to_leaf(
    csg: Any,
    local_pt: List[float],
    eps: float = 1e-4,
) -> Tuple[List[str], Any, Optional[str]]:
    """A plain click: traverse from root to deepest labeled node, then report face."""
    from kumiki.cutcsg import SolidUnion, Difference

    path: List[str] = []
    node = csg
    while True:
        new_path, target, label = _navigate_csg_one_level(node, local_pt, path, eps)
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
    edge_feature: Optional[Any] = None,
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
        if _csg_point_on_boundary(target_csg, local_c, eps):
            if enforce_owner:
                owner = _resolve_csg_at_path(root_csg, selected_path, local_c, eps)
                if owner is not selected_ref:
                    continue
            if edge_feature is not None:
                # An edge is a line, and no triangle's centroid sits on one --
                # matching the way a face does would light nothing at all. The
                # mesher puts vertices on edges, so the strip along an edge is
                # the triangles with two vertices on it.
                on_edge = 0
                for corner in (i0, i1, i2):
                    corner_local = _inv_transform_point(timber_rot, timber_pos, [
                        mesh_vertices[corner * 3],
                        mesh_vertices[corner * 3 + 1],
                        mesh_vertices[corner * 3 + 2],
                    ])
                    if edge_feature.test_point(
                        target_csg, _to_v3(corner_local), _edge_tolerance()
                    ):
                        on_edge += 1
                if on_edge < 2:
                    continue
            elif feature_label is not None:
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
    local_pt = _inv_transform_point(timber_rot, timber_pos, [float(p) for p in point])

    t0 = time.monotonic()

    # A plain click goes straight to the feature, which is what someone
    # clicking a shoulder or an edge is after. Ctrl holds it back to one level
    # per click, for walking down through the compounds on the way.
    if not ctrl_click:
        new_path, target_csg, feature_label = _navigate_csg_to_leaf(local_csg, local_pt, eps)
    else:
        if current_path:
            node = _resolve_csg_at_path(local_csg, current_path, local_pt, eps)
            on_boundary = _csg_point_on_boundary(node, local_pt, eps)
            if not on_boundary:
                node = local_csg
                current_path = []
        else:
            node = local_csg

        new_path, target_csg, feature_label = _navigate_csg_one_level(
            node, local_pt, current_path, eps,
        )

    # A click that has drilled far enough to name a face can name an edge
    # instead, when one is the better answer at that point. Only then: while a
    # click is still descending through compounds it selects them whole, and
    # jumping to an edge deep inside would skip the levels between.
    feature_type = None
    feature_hits = _features_at_point(local_csg, local_pt, eps)
    edge = _resolve_derived_edge(feature_hits) if feature_label is not None else None
    if edge is not None:
        owned = _edge_owner(local_csg, edge)
        if owned is not None:
            target_csg, new_path = owned[0], owned[1]
            feature_label = edge.name
            feature_type = "EDGE"

    parent_csg = None
    if new_path:
        parent_csg = _resolve_csg_at_path(local_csg, new_path, local_pt, eps)

    highlight_edge = None
    if edge is not None:
        highlight_edge = _edge_highlight_segment(
            edge, target_csg, mesh["vertices"], timber_rot, timber_pos,
        )

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
        edge_feature=edge if highlight_edge is None else None,
    )

    # When a feature (face) is selected, also extract the parent labeled CSG mesh
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
        # Echoed back because the viewer can have several timbers selected at
        # once, so it cannot infer which one a result belongs to.
        "memberKey": member_key,
        "path": new_path,
        # What was selected, and the feature within it if navigation resolved
        # one. feature_label is None while a click is still drilling down
        # through compounds, and the display has to say so rather than name a
        # face belonging to something further in.
        **_describe_pick(target_csg, local_csg, cut_timber, local_pt, eps, feature_label, feature_type),
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
    if highlight_edge is not None:
        result["highlightEdge"] = highlight_edge
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

    # If a feature name was requested, confirm the target actually declares it.
    # The mesh target stays the CSG either way -- _extract_highlight_mesh does
    # the per-face narrowing itself, via feature_label.
    actual_feature_label = None
    if feature_label and feature_label in _declared_feature_names(target_csg):
        actual_feature_label = feature_label

    hl_verts, hl_idx, matched, total = _extract_highlight_mesh(
        mesh["vertices"],
        mesh["indices"],
        target_csg,
        timber_rot,
        timber_pos,
        eps,
        root_csg=local_csg,
        selected_path=path,
        selected_ref=target_csg,
        feature_label=actual_feature_label,
    )

    parent_hl = None
    if actual_feature_label:
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
        "memberKey": member_key,
        "path": path,
        "featureLabel": actual_feature_label,
        # Same two fields _describe_pick reports, so the display reads the same
        # whether a node was picked in 3D or clicked in the tree.
        "nodeKind": type(target_csg).__name__,
        "nodeDisplayName": type(target_csg).display_name(),
        "nodeLabel": _label_name(target_csg),
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


def _require_str(payload: Dict[str, Any], key: str, message: str) -> str:
    """Return payload[key] if it is a non-empty string, else raise ValueError(message)."""
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(message)
    return value


def _opt_dict(payload: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """Return payload[key] if it is a dict, else None."""
    value = payload.get(key)
    return value if isinstance(value, dict) else None


_active_assembly_cancels: Dict[str, threading.Event] = {}

def _cancel_active_assembly(slot_name: str) -> None:
    event = _active_assembly_cancels.pop(slot_name, None)
    if event is not None:
        event.set()


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
        _cancel_active_assembly(slot_name)
        old_slot = state.slots.get(slot_name)
        next_path = payload.get("filePath", str(state.get_slot(slot_name).file_path))
        render_parameters = _opt_dict(payload, "renderParameters")
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

    if command == "get_drawings":
        ss = _resolve_slot(state, payload)
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "save_drawings":
        # Everything at once, and only what the file is responsible for.
        ss = _resolve_slot(state, payload)
        drawings = collect_drawings(ss.frame, ss.file_path, ss.pending_drawings)
        written = write_drawings_file(ss.file_path, drawings)
        # They are the file's now, so nothing is pending and the next read finds
        # them there. Keeping them would give the same drawing two answers.
        ss.pending_drawings = []
        return state, make_success_response(request_id, command, {
            "path": written,
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
        }), False

    if command == "create_drawing_from_selection":
        ss = _resolve_slot(state, payload)
        drawing = create_drawing_from_selection(ss.frame, payload.get("member_keys") or [])
        existing = collect_drawings(ss.frame, ss.file_path, ss.pending_drawings)
        drawing["id"] = _unique_drawing_id(drawing["name"], {d["id"] for d in existing})
        # The name follows the id, so drawing the same piece twice gives two
        # rows you can tell apart rather than two called the same thing.
        drawing["name"] = drawing["id"]
        drawing["origin"] = ORIGIN_FILE
        ss.pending_drawings.append(drawing)
        return state, make_success_response(request_id, command, {
            "scenes": collect_drawings(ss.frame, ss.file_path, ss.pending_drawings),
            "enterId": drawing["id"],
        }), False

    if command == "get_default_drawing_for_debugging":
        # Testing scaffolding; see build_default_drawing_for_debugging. Kept out
        # of the frame payload so a drawing never re-serializes geometry.
        ss = _resolve_slot(state, payload)
        drawing = build_default_drawing_for_debugging(ss.frame)
        return state, make_success_response(request_id, command, {"scenes": [drawing]}), False

    if command == "get_layers_tree":
        ss = _resolve_slot(state, payload)
        return state, make_success_response(request_id, command, serialize_layers(ss.frame)), False

    if command == "get_assembly":
        # Deferred from get_layers_tree so the frame renders before the
        # (potentially slow) disassembly solve runs.
        slot_name = _resolve_slot_name(state, payload)
        ss = _resolve_slot(state, payload)

        _cancel_active_assembly(slot_name)
        cancel_event = threading.Event()
        _active_assembly_cancels[slot_name] = cancel_event

        log_stderr(f"[assembly] [{slot_name}] Starting async background assembly solve for frame '{getattr(ss.frame, 'name', '?')}' ({len(ss.frame.cut_timbers)} timbers)...")
        t0 = time.monotonic()

        def _worker():
            try:
                timber_entries, accessory_entries = _assign_member_keys(ss.frame)
                payload_data = _build_assembly_payload(
                    ss.frame, timber_entries, accessory_entries, should_cancel=cancel_event.is_set
                )
                assembly_s = time.monotonic() - t0
                _active_assembly_cancels.pop(slot_name, None)
                if not cancel_event.is_set():
                    log_stderr(f"[assembly] [{slot_name}] Background assembly solve completed in {assembly_s:.3f}s")
                    emit_message({
                        "type": "assembly_result",
                        "slot": slot_name,
                        "result": {"assembly": payload_data},
                        "profiling": {"assembly_s": assembly_s},
                    })
                else:
                    log_stderr(f"[assembly] [{slot_name}] Background assembly solve canceled after {assembly_s:.3f}s")
            except Exception as exc:
                _active_assembly_cancels.pop(slot_name, None)
                if not cancel_event.is_set():
                    log_stderr(f"[assembly] [{slot_name}] Background assembly solve failed: {exc}")

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        return state, make_success_response(request_id, command, {"assembly": {"pending": True}}), False

    if command == "get_csg_tree":
        ss = _resolve_slot(state, payload)
        member_key = _require_str(payload, "memberKey", "get_csg_tree requires payload.memberKey")
        cached = ss.mesh_cache.get(member_key)
        cut_timber = cached.get("cut_timber") if cached else None
        if cut_timber is None:
            # Fall back to scanning frame for the matching memberKey by name+occurrence.
            timber_entries, _ = _assign_member_keys(ss.frame)
            match = next((e for e in timber_entries if e["memberKey"] == member_key), None)
            if match is None:
                raise ValueError(f"Unknown memberKey: {member_key}")
            cut_timber = match["cutTimber"]
        result = serialize_cut_csg_tree(cut_timber)
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
        member_name = _require_str(payload, "name", "get_member requires payload.name")
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
        slot_name = _require_str(payload, "slot", "load_slot requires payload.slot")
        _cancel_active_assembly(slot_name)
        file_path = _require_str(payload, "filePath", "load_slot requires payload.filePath")
        render_parameters = _opt_dict(payload, "renderParameters")
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
        slot_name = _require_str(payload, "slot", "unload_slot requires payload.slot")
        _cancel_active_assembly(slot_name)
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
        slot_name = _require_str(payload, "slot", "raise_specific_pattern requires payload.slot")
        source_file = _require_str(payload, "sourceFile", "raise_specific_pattern requires payload.sourceFile")
        pattern_name = _require_str(payload, "patternName", "raise_specific_pattern requires payload.patternName")
        render_parameters = _opt_dict(payload, "renderParameters")
        new_slot, result = _raise_specific_pattern(
            source_file,
            pattern_name,
            render_parameters=render_parameters,
        )
        state.slots[slot_name] = new_slot
        result["slot"] = slot_name
        log_stderr(f"[slot] Raised pattern '{pattern_name}' in slot '{slot_name}'")
        return state, make_success_response(request_id, command, result), False

    if command == "export_member":
        ss = _resolve_slot(state, payload)
        member_key = payload.get("memberKey")
        export_format = str(payload.get("format", "stl")).lower()
        output_dir_raw = payload.get("outputDir")

        if export_format not in {"stl", "step"}:
            raise ValueError("export_member requires payload.format to be 'stl' or 'step'")
        if not isinstance(member_key, str) or not member_key:
            raise ValueError("export_member requires payload.memberKey")
        if not isinstance(output_dir_raw, str) or not output_dir_raw:
            raise ValueError("export_member requires payload.outputDir")

        output_dir = Path(output_dir_raw).resolve()
        if _project_root is not None:
            allowed_root = (_project_root / "kigumi_exports").resolve()
            try:
                output_dir.relative_to(allowed_root)
            except ValueError as exc:
                raise ValueError("export_member outputDir must be inside project kigumi_exports/") from exc

        timber_entries, _accessory_entries = _assign_member_keys(ss.frame)
        entry = next((e for e in timber_entries if e["memberKey"] == member_key), None)
        if entry is None:
            raise ValueError(f"Unknown memberKey: {member_key}")

        from kumiki.blueprint import export_cut_timber_stl, export_cut_timber_step

        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = entry["timber"].ticket.path or entry["displayName"]
        dest = output_dir / f"{base_name}.{export_format}"
        if export_format == "stl":
            export_cut_timber_stl(entry["cutTimber"], dest, local=True)
        else:
            export_cut_timber_step(entry["cutTimber"], dest, local=True)

        return state, make_success_response(request_id, command, {
            "format": export_format,
            "memberKey": member_key,
            "outputDir": str(output_dir),
            "files": [str(dest)],
        }), False

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

        from kumiki.blueprint import (
            export_frame_stl,
            export_frame_3mf,
            export_frame_obj,
            export_frame_step,
        )

        # export_format is validated above, and the file extension equals the
        # format name for every supported format — so combined_name/glob are
        # derived from it directly (no per-format string can drift).
        exporters = {
            "stl": export_frame_stl,
            "3mf": export_frame_3mf,
            "obj": export_frame_obj,
            "step": export_frame_step,
        }
        written = exporters[export_format](
            ss.frame,
            output_dir,
            combined=include_combined,
            include_accessories=include_accessories,
        )
        combined_name = f"_combined.{export_format}"
        extension_glob = f"*.{export_format}"

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
