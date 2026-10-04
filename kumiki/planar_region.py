"""Regions in a plane, and whether a flat face is on the finished surface of a CSG.

A region is a list of disjoint convex polygons in a plane's own 2D frame. For a plane, every CSG
node gives two regions: where it has material just above the plane, and just below. The finished
surface in the plane is where those differ. `face_reaches_surface` is the only public entry point.
"""

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .cropcsg import _loft_sides_are_planar, solid_bounds
from .cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, CutCSG, Cylinder, Difference, EmptyCSG,
                     Intersection, SolidUnion)
from .feature_paths import FeatureHandle
from .geometry import Plane, perpendicular_axes
from .pathcsg import PathExtrusion, decompose_path_into_convex_pieces
from .rule import Matrix, V3

Polygon = List[Tuple[float, float]]
Region = List[Polygon]

# Two planes this close count as the same plane, in model units.
COINCIDENT = 1e-7
# Pieces smaller than this, in model units squared, are rounding slivers.
SLIVER_AREA = 1e-10
# Points on an elliptical cylinder section.
ELLIPSE_POINTS = 64


class _CannotSection(Exception):
    """A primitive this module can't cut by a plane."""


def _np(vector: V3) -> np.ndarray:
    return np.array([float(vector[i, 0]) for i in range(3)])


class _Frame:
    """A plane's 2D frame: origin, two in-plane axes, and its unit normal (the "above" side)."""

    def __init__(self, plane: Plane, near: V3):
        self.normal = _np(plane.normal) / np.linalg.norm(_np(plane.normal))
        point, centre = _np(plane.point), _np(near)
        self.origin = centre - self.normal * float((centre - point) @ self.normal)
        u, v = perpendicular_axes(Matrix(self.normal))
        self.u, self.v = _np(u), _np(v)

    def to_2d(self, point: np.ndarray) -> Tuple[float, float]:
        offset = point - self.origin
        return float(offset @ self.u), float(offset @ self.v)


def _area(polygon: Polygon) -> float:
    total = 0.0
    for i, (x, y) in enumerate(polygon):
        nx, ny = polygon[(i + 1) % len(polygon)]
        total += x * ny - nx * y
    return abs(total) / 2.0


def _clean(region: Region) -> Region:
    return [polygon for polygon in region if len(polygon) >= 3 and _area(polygon) > SLIVER_AREA]


def _clip(polygon: Polygon, a: float, b: float, c: float) -> Polygon:
    """The part of a convex polygon where a*x + b*y <= c."""
    kept: Polygon = []
    for i, current in enumerate(polygon):
        previous = polygon[i - 1]
        current_in = a * current[0] + b * current[1] <= c
        previous_in = a * previous[0] + b * previous[1] <= c
        if current_in != previous_in:
            denominator = a * (current[0] - previous[0]) + b * (current[1] - previous[1])
            if denominator != 0:
                t = (c - a * previous[0] - b * previous[1]) / denominator
                kept.append((previous[0] + t * (current[0] - previous[0]),
                             previous[1] + t * (current[1] - previous[1])))
        if current_in:
            kept.append(current)
    return kept


def _inside_lines(polygon: Polygon) -> List[Tuple[float, float, float]]:
    """A convex polygon as the half-planes a*x + b*y <= c it is the intersection of."""
    signed = sum(x * ny - nx * y for (x, y), (nx, ny) in zip(polygon, polygon[1:] + polygon[:1]))
    turn = 1.0 if signed > 0 else -1.0
    lines = []
    for (x, y), (nx, ny) in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = nx - x, ny - y
        if math.hypot(dx, dy) < 1e-15:
            continue
        a, b = turn * dy, -turn * dx
        lines.append((a, b, a * x + b * y))
    return lines


def _intersect(one: Region, other: Region) -> Region:
    out: Region = []
    for polygon in one:
        for clipper in other:
            piece = polygon
            for a, b, c in _inside_lines(clipper):
                piece = _clip(piece, a, b, c)
                if not piece:
                    break
            out.append(piece)
    return _clean(out)


def _subtract(one: Region, other: Region) -> Region:
    pieces = list(one)
    for clipper in other:
        remaining: Region = []
        for polygon in pieces:
            rest = polygon
            for a, b, c in _inside_lines(clipper):
                remaining.append(_clip(rest, -a, -b, -c))
                rest = _clip(rest, a, b, c)
                if not rest:
                    break
        pieces = _clean(remaining)
    return pieces


def _union(one: Region, other: Region) -> Region:
    return one + _subtract(other, one)


def _xor(one: Region, other: Region) -> Region:
    return _subtract(one, other) + _subtract(other, one)


def _square(half: float) -> Polygon:
    return [(-half, -half), (half, -half), (half, half), (-half, half)]


Sides = Tuple[Region, Region]


def _half_space_section(
    faces: Sequence[Tuple[V3, V3]], frame: _Frame, start: Region,
) -> Sides:
    """(above, below) for the intersection of half spaces dot(normal, p - point) <= 0, from `start`."""
    region, above, below = start, True, True
    for normal, point in faces:
        n, q = _np(normal), _np(point)
        a, b = float(n @ frame.u), float(n @ frame.v)
        c = float(n @ (q - frame.origin))
        length = float(np.linalg.norm(n))
        if math.hypot(a, b) < 1e-9 * length:
            if c < -COINCIDENT * length:
                return [], []
            if c <= COINCIDENT * length:
                if float(n @ frame.normal) > 0:
                    above = False
                else:
                    below = False
            continue
        region = [_clip(polygon, a, b, c) for polygon in region]
    region = _clean(region)
    return (region if above else []), (region if below else [])


def _cylinder_section(csg: Cylinder, frame: _Frame, seed: Region) -> Sides:
    axis = _np(csg.axis_direction) / np.linalg.norm(_np(csg.axis_direction))
    centre, radius = _np(csg.position), float(csg.radius)
    across = float(axis @ frame.normal)
    if abs(across) < 1e-9:
        height = float(frame.normal @ (centre - frame.origin))
        if abs(height) >= radius - COINCIDENT:
            return [], []
        half_width = math.sqrt(radius * radius - height * height)
        side = np.cross(frame.normal, axis)
        a, b = float(side @ frame.u), float(side @ frame.v)
        c = float(side @ (centre - frame.origin))
        region = [_clip(_clip(polygon, a, b, c + half_width), -a, -b, -c + half_width) for polygon in seed]
    else:
        middle = centre + axis * float(frame.normal @ (frame.origin - centre)) / across
        e1, e2 = (_np(axis_) for axis_ in perpendicular_axes(Matrix(axis)))
        points = []
        for k in range(ELLIPSE_POINTS):
            angle = 2 * math.pi * k / ELLIPSE_POINTS
            ring = radius * (math.cos(angle) * e1 + math.sin(angle) * e2)
            points.append(frame.to_2d(middle + ring - axis * float(frame.normal @ ring) / across))
        region = _intersect([points], seed)
    caps = []
    if csg.start_distance is not None:
        caps.append((Matrix(-axis), Matrix(centre + axis * float(csg.start_distance))))
    if csg.end_distance is not None:
        caps.append((Matrix(axis), Matrix(centre + axis * float(csg.end_distance))))
    return _half_space_section(caps, frame, region)


def _sides(csg: CutCSG, frame: _Frame, seed: Region) -> Sides:
    """Where `csg` has material just above, and just below, the frame's plane."""
    if isinstance(csg, EmptyCSG):
        return [], []
    if isinstance(csg, SolidUnion):
        above: Region = []
        below: Region = []
        for child in csg.children:
            child_above, child_below = _sides(child, frame, seed)
            above, below = _union(above, child_above), _union(below, child_below)
        return above, below
    if isinstance(csg, Intersection):
        left_above, left_below = _sides(csg.left, frame, seed)
        right_above, right_below = _sides(csg.right, frame, seed)
        return _intersect(left_above, right_above), _intersect(left_below, right_below)
    if isinstance(csg, Difference):
        above, below = _sides(csg.base, frame, seed)
        for cut in csg.subtract:
            cut_above, cut_below = _sides(cut, frame, seed)
            above, below = _subtract(above, cut_above), _subtract(below, cut_below)
        return above, below
    if isinstance(csg, Cylinder):
        return _cylinder_section(csg, frame, seed)
    if isinstance(csg, PathExtrusion):
        above, below = [], []
        for piece in decompose_path_into_convex_pieces(csg.path, tolerance=1e-4):
            convex = ConvexPolygonExtrusion(points=piece, transform=csg.transform,
                                            start_distance=csg.start_distance, end_distance=csg.end_distance)
            piece_above, piece_below = _sides(convex, frame, seed)
            above, below = _union(above, piece_above), _union(below, piece_below)
        return above, below

    if isinstance(csg, ConvexPolygonSimpleLoft) and not _loft_sides_are_planar(csg):
        raise _CannotSection("a loft with twisted sides")
    bounds = solid_bounds(csg)
    if bounds.is_empty:
        return [], []
    if bounds.is_unknown:
        raise _CannotSection(type(csg).__name__)
    return _half_space_section(bounds.require_faces(), frame, seed)


def face_reaches_surface(face: FeatureHandle, root: CutCSG, near: V3, reach: float) -> bool:
    """Whether some patch of this flat face, with area, is on the finished surface of `root`.

    `near` and `reach` bound the work: everything that matters must lie within `reach` of `near`.
    A face, or a tree, this module can't cut by a plane counts as on the surface.
    """
    plane = face.feature.locate_simple_unbounded(face.owner)
    if not isinstance(plane, Plane):
        raise ValueError(f"{face.feature.name!r} is not a flat face")
    frame = _Frame(plane, near)
    seed = [_square(reach)]
    try:
        own_above, own_below = _sides(face.owner, frame, seed)
        own = own_above or own_below
        if not own:
            return False
        above, below = _sides(root, frame, own)
    except _CannotSection:
        return True
    surface = _xor(above, below)
    return sum(_area(polygon) for polygon in _intersect(own, surface)) > SLIVER_AREA
