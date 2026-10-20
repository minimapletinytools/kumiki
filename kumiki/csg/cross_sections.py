"""Cross-sections of a CSG by a plane, and whether a flat face is on the finished surface of a CSG.

A cross-section is PolygonRegions: disjoint convex polygons in a plane's own 2D frame. For a
plane, every CSG node gives two regions: where it has material just in front of the plane, and just behind. The finished
surface in the plane is where those differ. `face_reaches_surface` asks that of a face; the
`SightFrame` functions below ask, in a plane holding a line of sight, what material is in the way.
"""

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .edges_on_csg import _loft_sides_are_planar, solid_bounds
from .cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, CutCSG, Cylinder, Difference, EmptyCSG,
                     FaceFeature, Intersection, SolidUnion)
from .feature_paths import FeatureHandle
from ..geometry import Plane, perpendicular_axes
from .pathcsg import PathExtrusion, decompose_path_into_convex_pieces
from ..rule import Matrix, V3, as_ndarray, unit_ndarray

Polygon = List[Tuple[float, float]]
PolygonRegions = List[Polygon]

# Two planes this close count as the same plane, in model units.
COINCIDENT = 1e-7
# Pieces smaller than this, in model units squared, are rounding slivers.
SLIVER_AREA = 1e-10
# Points on an elliptical cylinder section.
ELLIPSE_POINTS = 64


class _CannotCrossSection(Exception):
    """A primitive this module can't cut by a plane."""


class _Frame:
    """A plane's 2D frame: origin, two in-plane axes, and its unit normal (the front side)."""

    def __init__(self, plane: Plane, near: V3):
        self.normal = as_ndarray(plane.normal) / np.linalg.norm(as_ndarray(plane.normal))
        point, centre = as_ndarray(plane.point), as_ndarray(near)
        self.origin = centre - self.normal * float((centre - point) @ self.normal)
        u, v = perpendicular_axes(Matrix(self.normal))
        self.u, self.v = as_ndarray(u), as_ndarray(v)

    def to_2d(self, point: np.ndarray) -> Tuple[float, float]:
        offset = point - self.origin
        return float(offset @ self.u), float(offset @ self.v)

    @classmethod
    def with_axes(cls, origin: np.ndarray, u: np.ndarray, v: np.ndarray, normal: np.ndarray) -> '_Frame':
        """A frame whose 2D axes are given rather than chosen, so frames in several spaces agree."""
        frame = cls.__new__(cls)
        frame.origin, frame.u, frame.v, frame.normal = origin, u, v, normal
        return frame


def _area(polygon: Polygon) -> float:
    total = 0.0
    for i, (x, y) in enumerate(polygon):
        nx, ny = polygon[(i + 1) % len(polygon)]
        total += x * ny - nx * y
    return abs(total) / 2.0


def _clean(region: PolygonRegions) -> PolygonRegions:
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
                # In [0, 1] whenever the ends are on opposite sides; an edge lying all but along the
                # line can be put either side of it by rounding, and the ratio of two near-zeros
                # then lands anywhere -- a spike to the far end of the plane.
                t = min(1.0, max(0.0, (c - a * previous[0] - b * previous[1]) / denominator))
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


def _box(polygon: Polygon) -> Tuple[float, float, float, float]:
    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _apart(one: Tuple[float, float, float, float], other: Tuple[float, float, float, float]) -> bool:
    """Whether two bounding boxes miss each other: then their polygons do too, and clipping one by
    the other is all cost for no change."""
    return (one[2] < other[0] - COINCIDENT or other[2] < one[0] - COINCIDENT
            or one[3] < other[1] - COINCIDENT or other[3] < one[1] - COINCIDENT)


def _intersect(one: PolygonRegions, other: PolygonRegions) -> PolygonRegions:
    out: PolygonRegions = []
    other_boxes = [_box(clipper) for clipper in other]
    for polygon in one:
        box = _box(polygon)
        for clipper, clipper_box in zip(other, other_boxes):
            if _apart(box, clipper_box):
                continue
            piece = polygon
            for a, b, c in _inside_lines(clipper):
                piece = _clip(piece, a, b, c)
                if not piece:
                    break
            out.append(piece)
    return _clean(out)


def _subtract(one: PolygonRegions, other: PolygonRegions) -> PolygonRegions:
    pieces = list(one)
    for clipper in other:
        clipper_box = _box(clipper)
        remaining: PolygonRegions = []
        for polygon in pieces:
            if _apart(_box(polygon), clipper_box):
                remaining.append(polygon)
                continue
            rest = polygon
            for a, b, c in _inside_lines(clipper):
                remaining.append(_clip(rest, -a, -b, -c))
                rest = _clip(rest, a, b, c)
                if not rest:
                    break
        pieces = _clean(remaining)
    return pieces


def _union(one: PolygonRegions, other: PolygonRegions) -> PolygonRegions:
    return one + _subtract(other, one)


def _xor(one: PolygonRegions, other: PolygonRegions) -> PolygonRegions:
    return _subtract(one, other) + _subtract(other, one)


def _square(half: float) -> Polygon:
    return [(-half, -half), (half, -half), (half, half), (-half, half)]


Sides = Tuple[PolygonRegions, PolygonRegions]


def _half_space_cross_section(
    faces: Sequence[Tuple[V3, V3]], frame: _Frame, start: PolygonRegions,
) -> Sides:
    """(front, back) for the intersection of half spaces dot(normal, p - point) <= 0, from `start`."""
    region, front, back = start, True, True
    for normal, point in faces:
        n, q = as_ndarray(normal), as_ndarray(point)
        a, b = float(n @ frame.u), float(n @ frame.v)
        c = float(n @ (q - frame.origin))
        length = float(np.linalg.norm(n))
        if math.hypot(a, b) < 1e-9 * length:
            if c < -COINCIDENT * length:
                return [], []
            if c <= COINCIDENT * length:
                if float(n @ frame.normal) > 0:
                    front = False
                else:
                    back = False
            continue
        region = [_clip(polygon, a, b, c) for polygon in region]
    region = _clean(region)
    return (region if front else []), (region if back else [])


def _cylinder_cross_section(csg: Cylinder, frame: _Frame, seed: PolygonRegions) -> Sides:
    axis = as_ndarray(csg.axis_direction) / np.linalg.norm(as_ndarray(csg.axis_direction))
    centre, radius = as_ndarray(csg.position), float(csg.radius)
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
        e1, e2 = (as_ndarray(axis_) for axis_ in perpendicular_axes(Matrix(axis)))
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
    return _half_space_cross_section(caps, frame, region)


def _sides(csg: CutCSG, frame: _Frame, seed: PolygonRegions) -> Sides:
    """Where `csg` has material just in front of the frame's plane (the side its normal points to), and just behind."""
    if isinstance(csg, EmptyCSG):
        return [], []
    if isinstance(csg, SolidUnion):
        front: PolygonRegions = []
        back: PolygonRegions = []
        for child in csg.children:
            child_front, child_back = _sides(child, frame, seed)
            front, back = _union(front, child_front), _union(back, child_back)
        return front, back
    if isinstance(csg, Intersection):
        left_front, left_back = _sides(csg.left, frame, seed)
        if not left_front and not left_back:
            return [], []
        right_front, right_back = _sides(csg.right, frame, seed)
        return _intersect(left_front, right_front), _intersect(left_back, right_back)
    if isinstance(csg, Difference):
        front, back = _sides(csg.base, frame, seed)
        for cut in csg.subtract:
            if not front and not back:
                break  # nothing left to cut from
            cut_front, cut_back = _sides(cut, frame, seed)
            front, back = _subtract(front, cut_front), _subtract(back, cut_back)
        return front, back
    if isinstance(csg, Cylinder):
        return _cylinder_cross_section(csg, frame, seed)
    if isinstance(csg, PathExtrusion):
        front, back = [], []
        for piece in decompose_path_into_convex_pieces(csg.path, tolerance=1e-4):
            convex = ConvexPolygonExtrusion(points=piece, transform=csg.transform,
                                            start_distance=csg.start_distance, end_distance=csg.end_distance)
            piece_front, piece_back = _sides(convex, frame, seed)
            front, back = _union(front, piece_front), _union(back, piece_back)
        return front, back

    if isinstance(csg, ConvexPolygonSimpleLoft) and not _loft_sides_are_planar(csg):
        raise _CannotCrossSection("a loft with twisted sides")
    bounds = solid_bounds(csg)
    if bounds.is_empty:
        return [], []
    if bounds.is_unknown:
        raise _CannotCrossSection(type(csg).__name__)
    return _half_space_cross_section(bounds.require_faces(), frame, seed)


def face_reaches_surface(face: FeatureHandle[FaceFeature], root: CutCSG, near: V3, reach: float) -> bool:
    """Determines whether part of `face`, with area, is on the finished surface of `root`.

    For each spot on the face, check whether `root` has material just in front of it and just
    behind it, and XOR those two sets together. If that comes out empty, the face is either
    entirely embedded in `root` or entirely away from it. "Just in front/behind" means arbitrarily
    close; the tolerance only decides when a primitive's face counts as flush with this plane.

    `near` and `reach` bound the work: everything that matters must lie within `reach` of `near`.
    A face, or a tree, this module can't cut by a plane counts as on the surface.
    """
    plane = face.feature.locate_simple_unbounded(face.owner)
    if plane is None:
        raise ValueError(f"{face.feature.name!r} has no plane")
    frame = _Frame(plane, near)
    seed = [_square(reach)]
    try:
        own_front, own_back = _sides(face.owner, frame, seed)
        own = own_front or own_back
        if not own:
            return False
        front, back = _sides(root, frame, own)
    except _CannotCrossSection:
        return True
    surface = _xor(front, back)
    return sum(_area(polygon) for polygon in _intersect(own, surface)) > SLIVER_AREA


# --- lines of sight ---------------------------------------------------------------------------

CannotCrossSection = _CannotCrossSection
# A plane's 2D frame, given as (origin, u, v, normal) in a CSG's own space.
SightFrame = Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


def material_crossing(root: CutCSG, frame: SightFrame, reach: float,
                      across: Optional[Tuple[float, float]] = None) -> PolygonRegions:
    """Where `root` has material on both sides of the frame's plane: what a line of sight lying in
    the plane cannot pass. Material on one side only is surface, which a sight line runs along.

    `across`, a (low, high) span of u, cuts only that strip of the plane, the whole way along v:
    all a feature spanning it can be hidden by, and far less to cut than the plane.

    Raises CannotCrossSection for a tree this module can't cut by a plane.
    """
    seed = _square(reach) if across is None else [(across[0], -reach), (across[1], -reach),
                                                  (across[1], reach), (across[0], reach)]
    front, back = _sides(root, _Frame.with_axes(*frame), [seed])
    return _intersect(front, back)


def shadow(region: PolygonRegions, reach: float) -> PolygonRegions:
    """What `region` hides from a viewer looking along +v: each piece swept that way, `reach` far."""
    swept: PolygonRegions = []
    for polygon in region:
        far = [(x, y + reach) for x, y in polygon]
        swept.append(_convex_hull(polygon + far))
    return _clean(swept)


def subtract(one: PolygonRegions, other: PolygonRegions) -> PolygonRegions:
    return _subtract(one, other)


def area(region: PolygonRegions) -> float:
    return sum(_area(polygon) for polygon in region)


Segment2D = Tuple[Tuple[float, float], Tuple[float, float]]


def segments_outside(segments: Sequence[Segment2D], region: PolygonRegions) -> List[Segment2D]:
    """The parts of `segments` outside every polygon of `region`."""
    pieces = list(segments)
    for polygon in region:
        lines = _inside_lines(polygon)
        kept: List[Segment2D] = []
        for start, end in pieces:
            # Where the segment is inside this convex polygon, as a parameter span (Cyrus-Beck).
            low, high = 0.0, 1.0
            dx, dy = end[0] - start[0], end[1] - start[1]
            for a, b, c in lines:
                along = a * dx + b * dy
                gap = c - (a * start[0] + b * start[1])
                if abs(along) < 1e-15:
                    if gap < 0:
                        low, high = 1.0, 0.0
                        break
                    continue
                t = gap / along
                if along > 0:
                    high = min(high, t)
                else:
                    low = max(low, t)
            point = lambda t: (start[0] + dx * t, start[1] + dy * t)
            if low >= high:
                kept.append((start, end))
                continue
            if low > 0:
                kept.append((start, point(low)))
            if high < 1:
                kept.append((point(high), end))
        pieces = [(a, b) for a, b in kept if math.hypot(b[0] - a[0], b[1] - a[1]) > math.sqrt(SLIVER_AREA)]
    return pieces


def _convex_hull(points: Polygon) -> Polygon:
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return ordered

    def half(sequence: Sequence[Tuple[float, float]]) -> Polygon:
        out: Polygon = []
        for point in sequence:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (point[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (point[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(point)
        return out

    lower, upper = half(ordered), half(list(reversed(ordered)))
    return lower[:-1] + upper[:-1]


# --- a plane cropped to a solid ----------------------------------------------------------------

CrossSection = Tuple[_Frame, PolygonRegions]


def plane_cross_section(plane: Plane, root: CutCSG, near: V3, reach: float) -> Optional[CrossSection]:
    """The part of `plane` that `root` has material against, on either side (front ∪ back): the
    plane cropped to the solid, interior included, as a region in the plane's own frame. None for
    a tree this module can't cut."""
    frame = _Frame(plane, near)
    try:
        front, back = _sides(root, frame, [_square(reach)])
    except _CannotCrossSection:
        return None
    return frame, _union(front, back)


def face_cross_section(
    face: FaceFeature, owner: CutCSG, root: Optional[CutCSG], near: V3, reach: float,
) -> Optional[CrossSection]:
    """The part of `face` (declared on `owner`) that is on the finished surface of `root`: where
    `root` has material on one side only (front XOR back), within the face. A region in the face's
    own plane frame -- or, with no `root`, all of the face `owner` gives it. None for a tree this
    module can't cut by a plane. See face_reaches_surface."""
    plane = face.locate_simple_unbounded(owner)
    if plane is None:
        return None
    frame = _Frame(plane, near)
    try:
        own_front, own_back = _sides(owner, frame, [_square(reach)])
        own = own_front or own_back
        if not own or root is None:
            return frame, own
        front, back = _sides(root, frame, own)
    except _CannotCrossSection:
        return None
    return frame, _intersect(own, _xor(front, back))


def cross_section_polygons(cross_section: CrossSection) -> List[List[np.ndarray]]:
    """The cross_section's pieces, each a convex polygon of points in the solid's space."""
    frame, region = cross_section
    return [[_to_3d(frame, point) for point in polygon] for polygon in region]


def _to_3d(frame: _Frame, point: Tuple[float, float]) -> np.ndarray:
    return frame.origin + frame.u * point[0] + frame.v * point[1]


def cross_section_outline(cross_section: CrossSection) -> List[Tuple[np.ndarray, np.ndarray]]:
    """The cross_section's boundary, in the solid's space: every piece's edges, less the seams where two
    pieces of the one region meet."""
    frame, region = cross_section
    edges = [(polygon[i], polygon[(i + 1) % len(polygon)]) for polygon in region for i in range(len(polygon))]
    outline: List[Tuple[np.ndarray, np.ndarray]] = []
    for index, (start, end) in enumerate(edges):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_sq = dx * dx + dy * dy
        if length_sq < SLIVER_AREA:
            continue
        kept = [(0.0, 1.0)]
        for other_index, (other_start, other_end) in enumerate(edges):
            if other_index == index:
                continue
            # A seam: another piece's edge along this one, running the other way.
            ox, oy = other_end[0] - other_start[0], other_end[1] - other_start[1]
            if ox * dx + oy * dy >= 0:
                continue
            off = [((p[0] - start[0]) * dy - (p[1] - start[1]) * dx) / math.sqrt(length_sq)
                   for p in (other_start, other_end)]
            if max(abs(off[0]), abs(off[1])) > COINCIDENT:
                continue
            along = sorted(((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / length_sq
                           for p in (other_start, other_end))
            kept = [piece for low, high in kept for piece in
                    ((low, min(high, along[0])), (max(low, along[1]), high)) if piece[1] - piece[0] > 1e-9]
        for low, high in kept:
            point = lambda t: (start[0] + dx * t, start[1] + dy * t)
            outline.append((_to_3d(frame, point(low)), _to_3d(frame, point(high))))
    return outline


def cross_section_centroid(cross_section: CrossSection) -> Optional[np.ndarray]:
    """The cross_section's centroid, in the solid's space; None if it has no area."""
    frame, region = cross_section
    total, x, y = 0.0, 0.0, 0.0
    for polygon in region:
        for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
            cross = ax * by - bx * ay  # signed: each piece's own winding cancels out below
            total, x, y = total + cross, x + (ax + bx) * cross, y + (ay + by) * cross
    if abs(total) / 2 <= SLIVER_AREA:
        return None
    return _to_3d(frame, (x / (3 * total), y / (3 * total)))
