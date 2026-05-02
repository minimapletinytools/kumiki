"""
Kumiki - Blueprint export module (STL and STEP)

Exports CutTimber and Frame objects to standard CAD interchange formats.

STL export uses trimesh (triangle mesh). STEP export uses OCP
(OpenCascade Python bindings from cadquery-ocp) to produce exact B-rep geometry.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional, Union, cast

from .cutcsg import (
    ConvexPolygonExtrusion,
    CutCSG,
    Cylinder,
    Difference,
    HalfSpace,
    RectangularPrism,
    SolidUnion,
    adopt_csg,
)
from .rule import Transform
from .rendering_utils import sympy_to_float
from .timber import CutTimber, Frame

import numpy as np
import trimesh

BRepPrimAPI_MakeBox = cast(Any, None)
BRepPrimAPI_MakeCylinder = cast(Any, None)
BRepAlgoAPI_Fuse = cast(Any, None)
BRepAlgoAPI_Cut = cast(Any, None)
BRepBuilderAPI_MakeEdge = cast(Any, None)
BRepBuilderAPI_MakeWire = cast(Any, None)
BRepBuilderAPI_MakeFace = cast(Any, None)
BRepBuilderAPI_Transform = cast(Any, None)
BRepPrimAPI_MakePrism = cast(Any, None)
gp_Pnt = cast(Any, None)
gp_Vec = cast(Any, None)
gp_Dir = cast(Any, None)
gp_Ax2 = cast(Any, None)
gp_Trsf = cast(Any, None)
gp_Mat = cast(Any, None)
gp_XYZ = cast(Any, None)
TopoDS_Shape = cast(Any, None)
TopoDS_Compound = cast(Any, None)
BRep_Builder = cast(Any, None)
STEPControl_Writer = cast(Any, None)
STEPControl_AsIs = cast(Any, None)
Interface_Static = cast(Any, None)
TopLoc_Location = cast(Any, None)

try:
    import OCP.BRepPrimAPI as _BRepPrimAPI
    import OCP.BRepAlgoAPI as _BRepAlgoAPI
    import OCP.BRepBuilderAPI as _BRepBuilderAPI
    import OCP.gp as _gp
    import OCP.TopoDS as _TopoDS
    import OCP.BRep as _BRep
    import OCP.STEPControl as _STEPControl
    import OCP.Interface as _Interface
    import OCP.TopLoc as _TopLoc

    BRepPrimAPI_MakeBox = getattr(_BRepPrimAPI, "BRepPrimAPI_MakeBox")
    BRepPrimAPI_MakeCylinder = getattr(_BRepPrimAPI, "BRepPrimAPI_MakeCylinder")
    BRepPrimAPI_MakePrism = getattr(_BRepPrimAPI, "BRepPrimAPI_MakePrism")

    BRepAlgoAPI_Fuse = getattr(_BRepAlgoAPI, "BRepAlgoAPI_Fuse")
    BRepAlgoAPI_Cut = getattr(_BRepAlgoAPI, "BRepAlgoAPI_Cut")

    BRepBuilderAPI_MakeEdge = getattr(_BRepBuilderAPI, "BRepBuilderAPI_MakeEdge")
    BRepBuilderAPI_MakeWire = getattr(_BRepBuilderAPI, "BRepBuilderAPI_MakeWire")
    BRepBuilderAPI_MakeFace = getattr(_BRepBuilderAPI, "BRepBuilderAPI_MakeFace")
    BRepBuilderAPI_Transform = getattr(_BRepBuilderAPI, "BRepBuilderAPI_Transform")

    gp_Pnt = getattr(_gp, "gp_Pnt")
    gp_Vec = getattr(_gp, "gp_Vec")
    gp_Dir = getattr(_gp, "gp_Dir")
    gp_Ax2 = getattr(_gp, "gp_Ax2")
    gp_Trsf = getattr(_gp, "gp_Trsf")
    gp_Mat = getattr(_gp, "gp_Mat")
    gp_XYZ = getattr(_gp, "gp_XYZ")

    TopoDS_Shape = getattr(_TopoDS, "TopoDS_Shape")
    TopoDS_Compound = getattr(_TopoDS, "TopoDS_Compound")
    BRep_Builder = getattr(_BRep, "BRep_Builder")
    STEPControl_Writer = getattr(_STEPControl, "STEPControl_Writer")
    STEPControl_AsIs = getattr(_STEPControl, "STEPControl_AsIs")
    Interface_Static = getattr(_Interface, "Interface_Static")
    TopLoc_Location = getattr(_TopLoc, "TopLoc_Location")

    _OCP_AVAILABLE = True
except ImportError:
    _OCP_AVAILABLE = False


# ---------------------------------------------------------------------------
# STL export
# ---------------------------------------------------------------------------


def _cut_timber_to_trimesh(cut_timber: CutTimber) -> "trimesh.Trimesh":
    """Return a trimesh in global coordinates for a single CutTimber."""
    from .triangles import triangulate_cutcsg

    local_csg = cut_timber.render_timber_with_cuts_csg_local()
    global_csg = adopt_csg(cut_timber.timber.transform, Transform.identity(), local_csg)
    return triangulate_cutcsg(global_csg).mesh


def export_cut_timber_stl(cut_timber: CutTimber, filepath: Union[str, Path]) -> None:
    """Export a single CutTimber to an STL file (global coordinates, metres).

    Args:
        cut_timber: The timber (with cuts applied) to export.
        filepath: Destination path. Parent directories are created if needed.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    mesh = _cut_timber_to_trimesh(cut_timber)
    mesh.export(str(filepath), file_type="stl")


def export_frame_stl(
    frame: Frame,
    output_dir: Union[str, Path],
    *,
    combined: bool = False,
) -> List[Path]:
    """Export every timber in a Frame to STL files.

    Args:
        frame: The frame to export.
        output_dir: Directory for the STL files.
        combined: If True, also write a single ``_combined.stl`` with all
            timbers merged into one mesh.

    Returns:
        List of paths written.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    meshes: list[trimesh.Trimesh] = []
    for i, ct in enumerate(frame.cut_timbers):
        name = ct.timber.ticket.name or f"timber_{i}"
        mesh = _cut_timber_to_trimesh(ct)
        meshes.append(mesh)
        dest = output_dir / f"{name}.stl"
        mesh.export(str(dest), file_type="stl")
        written.append(dest)

    if combined and meshes:
        merged = trimesh.util.concatenate(meshes)
        dest = output_dir / "_combined.stl"
        merged.export(str(dest), file_type="stl")
        written.append(dest)

    return written


# ---------------------------------------------------------------------------
# STEP export helpers (OCP / OpenCascade direct)
# ---------------------------------------------------------------------------

# Kumiki uses metres; OCP/STEP uses millimetres
_M_TO_MM = 1000.0
_STEP_HALF_SPACE_EXTENT = 10_000.0  # mm — large box stand-in for HalfSpace


def _to_mm(val) -> float:
    """Convert a SymPy linear value (in metres) to float millimetres."""
    return sympy_to_float(val) * _M_TO_MM


def _csg_to_ocp(csg: CutCSG) -> "TopoDS_Shape":
    """Recursively convert a CutCSG tree (in global coords) to an OCP shape."""
    import sys
    try:
        if isinstance(csg, RectangularPrism):
            return _prism_to_ocp(csg)
        if isinstance(csg, Cylinder):
            return _cylinder_to_ocp(csg)
        if isinstance(csg, ConvexPolygonExtrusion):
            return _extrusion_to_ocp(csg)
        if isinstance(csg, HalfSpace):
            return _halfspace_to_ocp(csg)
        if isinstance(csg, SolidUnion):
            return _union_to_ocp(csg)
        if isinstance(csg, Difference):
            return _difference_to_ocp(csg)
        raise TypeError(f"Unsupported CutCSG type for STEP export: {type(csg).__name__}")
    except Exception as exc:
        print(
            f"[blueprint] STEP error in {type(csg).__name__}: {exc}",
            file=sys.stderr, flush=True,
        )
        if isinstance(csg, (RectangularPrism, ConvexPolygonExtrusion)):
            m = csg.transform.orientation.matrix
            p = csg.transform.position
            print(
                f"[blueprint]   transform matrix:\n"
                f"    [{float(m[0,0]):.15f}, {float(m[0,1]):.15f}, {float(m[0,2]):.15f}]\n"
                f"    [{float(m[1,0]):.15f}, {float(m[1,1]):.15f}, {float(m[1,2]):.15f}]\n"
                f"    [{float(m[2,0]):.15f}, {float(m[2,1]):.15f}, {float(m[2,2]):.15f}]\n"
                f"    position: [{float(p[0])}, {float(p[1])}, {float(p[2])}]",
                file=sys.stderr, flush=True,
            )
        if isinstance(csg, Cylinder):
            print(
                f"[blueprint]   axis: [{float(csg.axis_direction[0])}, {float(csg.axis_direction[1])}, {float(csg.axis_direction[2])}]"
                f"  pos: [{float(csg.position[0])}, {float(csg.position[1])}, {float(csg.position[2])}]",
                file=sys.stderr, flush=True,
            )
        if isinstance(csg, HalfSpace):
            print(
                f"[blueprint]   normal: [{float(csg.normal[0])}, {float(csg.normal[1])}, {float(csg.normal[2])}]"
                f"  offset: {float(csg.offset)}",
                file=sys.stderr, flush=True,
            )
        raise


def _make_trsf(rot: list[list[float]], tx: float, ty: float, tz: float) -> "gp_Trsf":
    """Build a gp_Trsf from a 3x3 rotation matrix and translation."""
    trsf = gp_Trsf()
    trsf.SetValues(
        rot[0][0], rot[0][1], rot[0][2], tx,
        rot[1][0], rot[1][1], rot[1][2], ty,
        rot[2][0], rot[2][1], rot[2][2], tz,
    )
    return trsf


def _rotation_matrix_from_z_to_dir(dx: float, dy: float, dz: float) -> list[list[float]]:
    """Build an orthogonal 3x3 rotation matrix that maps +Z to (dx, dy, dz)."""
    import math
    import numpy as _np
    norm = math.sqrt(dx * dx + dy * dy + dz * dz)
    if norm < 1e-12:
        return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    dx, dy, dz = dx / norm, dy / norm, dz / norm
    new_z = _np.array([dx, dy, dz])
    if abs(dx) < 0.9:
        ref = _np.array([1.0, 0.0, 0.0])
    else:
        ref = _np.array([0.0, 1.0, 0.0])
    new_x = _np.cross(ref, new_z)
    new_x /= _np.linalg.norm(new_x)
    new_y = _np.cross(new_z, new_x)
    rot = _np.column_stack([new_x, new_y, new_z])
    return _orthogonalize_rotation(rot.tolist())


def _orthogonalize_rotation(rot: list[list[float]]) -> list[list[float]]:
    """Re-orthogonalize a 3x3 rotation matrix via SVD to satisfy OpenCascade."""
    import numpy as _np
    u, _, vt = _np.linalg.svd(_np.array(rot, dtype=float))
    r = u @ vt
    if _np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r.tolist()


def _apply_transform(shape: "TopoDS_Shape", trsf: "gp_Trsf") -> "TopoDS_Shape":
    """Apply a gp_Trsf to a shape, returning a new shape."""
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _transform_shape(shape: "TopoDS_Shape", transform: Transform) -> "TopoDS_Shape":
    """Apply a Kumiki Transform to an OCP shape."""
    m = transform.orientation.matrix
    p = transform.position
    rot = [
        [sympy_to_float(m[0, 0]), sympy_to_float(m[0, 1]), sympy_to_float(m[0, 2])],
        [sympy_to_float(m[1, 0]), sympy_to_float(m[1, 1]), sympy_to_float(m[1, 2])],
        [sympy_to_float(m[2, 0]), sympy_to_float(m[2, 1]), sympy_to_float(m[2, 2])],
    ]
    rot = _orthogonalize_rotation(rot)
    px, py, pz = _to_mm(p[0]), _to_mm(p[1]), _to_mm(p[2])
    trsf = _make_trsf(rot, px, py, pz)
    return _apply_transform(shape, trsf)


def _prism_to_ocp(prism: RectangularPrism) -> "TopoDS_Shape":
    w = _to_mm(prism.size[0])
    h = _to_mm(prism.size[1])
    start = _to_mm(prism.start_distance) if prism.start_distance is not None else -_STEP_HALF_SPACE_EXTENT
    end = _to_mm(prism.end_distance) if prism.end_distance is not None else _STEP_HALF_SPACE_EXTENT
    length = end - start

    # BRepPrimAPI_MakeBox takes two corner points
    box = BRepPrimAPI_MakeBox(
        gp_Pnt(-w / 2, -h / 2, start),
        gp_Pnt(w / 2, h / 2, start + length),
    ).Shape()
    return _transform_shape(box, prism.transform)


def _cylinder_to_ocp(cyl: Cylinder) -> "TopoDS_Shape":
    r = _to_mm(cyl.radius)
    start = _to_mm(cyl.start_distance) if cyl.start_distance is not None else -_STEP_HALF_SPACE_EXTENT
    end = _to_mm(cyl.end_distance) if cyl.end_distance is not None else _STEP_HALF_SPACE_EXTENT
    length = end - start

    # Create cylinder along Z, then rotate/translate to match axis
    ax = gp_Ax2(gp_Pnt(0, 0, start), gp_Dir(0, 0, 1))
    shape = BRepPrimAPI_MakeCylinder(ax, r, length).Shape()

    # Rotate to align with actual axis direction
    adx = sympy_to_float(cyl.axis_direction[0])
    ady = sympy_to_float(cyl.axis_direction[1])
    adz = sympy_to_float(cyl.axis_direction[2])
    px = _to_mm(cyl.position[0])
    py = _to_mm(cyl.position[1])
    pz = _to_mm(cyl.position[2])

    rot = _rotation_matrix_from_z_to_dir(adx, ady, adz)
    trsf = _make_trsf(rot, px, py, pz)
    return _apply_transform(shape, trsf)


def _extrusion_to_ocp(ext: ConvexPolygonExtrusion) -> "TopoDS_Shape":
    pts = [(_to_mm(p[0]), _to_mm(p[1])) for p in ext.points]
    start = _to_mm(ext.start_distance) if ext.start_distance is not None else -_STEP_HALF_SPACE_EXTENT
    end = _to_mm(ext.end_distance) if ext.end_distance is not None else _STEP_HALF_SPACE_EXTENT
    length = end - start

    # Build a wire from the polygon points
    wire_builder = BRepBuilderAPI_MakeWire()
    for i in range(len(pts)):
        p1 = pts[i]
        p2 = pts[(i + 1) % len(pts)]
        edge = BRepBuilderAPI_MakeEdge(
            gp_Pnt(p1[0], p1[1], start),
            gp_Pnt(p2[0], p2[1], start),
        ).Edge()
        wire_builder.Add(edge)
    wire = wire_builder.Wire()

    # Make face from wire, then extrude along Z
    face = BRepBuilderAPI_MakeFace(wire).Face()
    shape = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, length)).Shape()

    return _transform_shape(shape, ext.transform)


def _halfspace_to_ocp(hs: HalfSpace) -> "TopoDS_Shape":
    """Approximate a HalfSpace as a very large box on the 'kept' side.

    HalfSpace keeps {P : P·normal >= offset}. In the normal-aligned frame
    (Z = normal direction), this is Z >= offset/|normal|. The box extends
    from offset/|n| to offset/|n| + extent along Z and ±extent in X/Y.
    """
    import math

    nx = sympy_to_float(hs.normal[0])
    ny = sympy_to_float(hs.normal[1])
    nz = sympy_to_float(hs.normal[2])
    offset = _to_mm(hs.offset)
    norm = math.sqrt(nx * nx + ny * ny + nz * nz)
    if norm < 1e-12:
        raise ValueError("HalfSpace normal is zero")
    nx, ny, nz = nx / norm, ny / norm, nz / norm

    extent = _STEP_HALF_SPACE_EXTENT
    # Box covers the kept half: Z from offset/norm to offset/norm + extent
    box = BRepPrimAPI_MakeBox(
        gp_Pnt(-extent, -extent, offset / norm),
        gp_Pnt(extent, extent, offset / norm + extent),
    ).Shape()

    rot = _rotation_matrix_from_z_to_dir(nx, ny, nz)
    trsf = _make_trsf(rot, 0.0, 0.0, 0.0)
    return _apply_transform(box, trsf)


def _union_to_ocp(union: SolidUnion) -> "TopoDS_Shape":
    children = [_csg_to_ocp(c) for c in union.children]
    if not children:
        raise ValueError("SolidUnion has no children")
    result = children[0]
    for child in children[1:]:
        result = BRepAlgoAPI_Fuse(result, child).Shape()
    return result


def _difference_to_ocp(diff: Difference) -> "TopoDS_Shape":
    result = _csg_to_ocp(diff.base)
    for sub in diff.subtract:
        sub_shape = _csg_to_ocp(sub)
        result = BRepAlgoAPI_Cut(result, sub_shape).Shape()
    return result


def _write_step(shape: "TopoDS_Shape", filepath: str) -> None:
    """Write a TopoDS_Shape to a STEP file."""
    writer = STEPControl_Writer()
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 1)
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(filepath)
    if status != 1:  # IFSelect_RetDone = 1
        raise RuntimeError(f"STEP write failed with status {status}")


# ---------------------------------------------------------------------------
# STEP export public API
# ---------------------------------------------------------------------------


def export_cut_timber_step(cut_timber: CutTimber, filepath: Union[str, Path]) -> None:
    """Export a single CutTimber to a STEP file (global coordinates, millimetres).

    Requires OCP (cadquery-ocp). Install with: ``pip install cadquery-ocp``

    Args:
        cut_timber: The timber (with cuts applied) to export.
        filepath: Destination path. Parent directories are created if needed.
    """
    if not _OCP_AVAILABLE:
        raise ImportError(
            "OCP (cadquery-ocp) is required for STEP export. "
            "Install it with: pip install cadquery-ocp"
        )
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    local_csg = cut_timber.render_timber_with_cuts_csg_local()
    global_csg = adopt_csg(cut_timber.timber.transform, Transform.identity(), local_csg)
    shape = _csg_to_ocp(global_csg)
    _write_step(shape, str(filepath))


def export_frame_step(
    frame: Frame,
    output_dir: Union[str, Path],
    *,
    combined: bool = False,
) -> List[Path]:
    """Export every timber in a Frame to individual STEP files.

    Requires OCP (cadquery-ocp). Install with: ``pip install cadquery-ocp``

    Geometry is in millimetres (standard STEP/CAD convention).

    Args:
        frame: The frame to export.
        output_dir: Directory for the STEP files.
        combined: If True, also write a single ``_combined.step`` containing
            all timbers as a compound shape.

    Returns:
        List of paths written.
    """
    if not _OCP_AVAILABLE:
        raise ImportError(
            "OCP (cadquery-ocp) is required for STEP export. "
            "Install it with: pip install cadquery-ocp"
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    shapes: list[TopoDS_Shape] = []
    for i, ct in enumerate(frame.cut_timbers):
        name = ct.timber.ticket.name or f"timber_{i}"
        local_csg = ct.render_timber_with_cuts_csg_local()
        global_csg = adopt_csg(ct.timber.transform, Transform.identity(), local_csg)
        shape = _csg_to_ocp(global_csg)
        shapes.append(shape)
        dest = output_dir / f"{name}.step"
        _write_step(shape, str(dest))
        written.append(dest)

    if combined and shapes:
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        for shape in shapes:
            builder.Add(compound, shape)
        dest = output_dir / "_combined.step"
        _write_step(compound, str(dest))
        written.append(dest)

    return written