"""Whether a feature can be seen in an orthographic view, and which part of it.

A 2D view can only measure points and lines -- an edge, or a face seen edge-on --
so that is all this answers. Both are exact, with no sampling:

- A point is hidden when the line from it to the camera passes through material.
- A line: the lines of sight from it fill a half-plane, P. Each blocking solid
  cuts P in a 2D region, and the stretch of the line that region hides is the
  region's camera-side part projected back onto the line. A region projects as its
  outline does, and its outline is where P meets the solid's surface: P against
  each flat face plane in the CSG tree, cropped to the surface (an exact 1D crop).
  So the hidden stretch is a union of intervals, exactly.

Before either, the point or line is nudged a few micrometres off its own timber
into free space, sideways to the view where it can be, so a line of sight grazing
a surface -- an arris, a face seen edge-on -- is not hidden by the surface it lies
on. That makes an outline visible, the way a drawing draws it: a box's far
arrises lie on its outline, and count as seen.

What cannot be done exactly is not guessed at: a curved primitive the lines of
sight could reach (a peg, a bore) makes the answer "visible, not exact".
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..csg.cropcsg import crop_line_to_boundary_segments_on_csg, crop_line_to_segments_on_csg
from ..csg.cutcsg import CSGFeatureType, FeatureSource, HasFeatures, csg_children
from ..geometry import Line, Plane, Point
from ..rule import create_v3

#: How far a point or line is moved off its own timber into free space before it is tested.
NUDGE = 1e-5
#: Float noise: a stretch shorter than this, or material nearer the line than this, is nothing.
NOISE = 1e-9
#: How far the lines of sight are followed toward the camera. Only has to pass every solid.
REACH = 1e3


@dataclass(frozen=True)
class Visibility:
    """Whether a feature shows in a view.

    `exact` is False when it could not be decided exactly; `visible` is then True,
    since what cannot be decided is not called hidden. `stretches` are the visible
    parts of a line, as world-space (start, end) pairs.
    """
    visible: bool
    exact: bool = True
    stretches: Tuple[Tuple[Tuple[float, float, float], Tuple[float, float, float]], ...] = ()


UNKNOWN = Visibility(visible=True, exact=False)


def _np(vector) -> np.ndarray:
    return np.array([float(vector[i]) for i in range(3)])


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _v3(vector: np.ndarray):
    return create_v3(*(float(x) for x in vector))


def feature_visibility(handle, cut_timber, look, occluders: Sequence) -> Visibility:
    """Whether *handle*'s feature shows in an orthographic view looking along *look* (into the scene).

    *cut_timber* is the feature's own; *occluders* are every cut timber that can hide it,
    its own included.
    """
    located = handle.feature.locate_simple_unbounded(handle.owner)
    root = cut_timber.render_timber_with_cuts_csg_local()
    transform = cut_timber.timber.transform
    toward_camera = -_unit(_np(look))
    if isinstance(located, Point):
        at = _np(transform.local_to_global(located.position))
        return point_visibility(at, toward_camera, occluders, own=cut_timber)
    if isinstance(located, Line):
        return _edge_visibility(located, root, transform, toward_camera, occluders, cut_timber)
    if isinstance(located, Plane):
        normal = _np(transform.local_to_global_direction(located.normal))
        if abs(float(np.dot(_unit(normal), toward_camera))) > 1e-9:
            # Seen at an angle a face is an area, which a 2D view cannot measure anyway.
            return UNKNOWN
        return _edge_on_face_visibility(handle, root, transform, toward_camera, occluders, cut_timber)
    return UNKNOWN


def point_visibility(at: np.ndarray, toward_camera: np.ndarray, occluders: Sequence, own=None) -> Visibility:
    """Whether a world point is seen: no material between it and the camera."""
    start = _off_the_surface(at, None, own, toward_camera)
    if start is None:
        return UNKNOWN
    for occluder in occluders:
        root = occluder.render_timber_with_cuts_csg_local()
        transform = occluder.timber.transform
        local = _np(transform.global_to_local(_v3(start)))
        direction = _unit(_np(transform.global_to_local_direction(_v3(toward_camera))))
        if _reaches_curves(root, [local, local + direction * REACH]):
            return UNKNOWN
        pieces = crop_line_to_segments_on_csg(
            Line(direction=_v3(direction), point=_v3(local)), root, seed_reach=REACH, near=_v3(local))
        if pieces is None:
            return UNKNOWN
        for piece in pieces:
            far = max(float(np.dot(_np(piece.start) - local, direction)),
                      float(np.dot(_np(piece.end) - local, direction)))
            if far > NOISE:
                return Visibility(visible=False)
    return Visibility(visible=True)


def line_visibility(a: np.ndarray, b: np.ndarray, toward_camera: np.ndarray, occluders: Sequence) -> Visibility:
    """Which parts of the world segment *a*-*b* are seen. *a* and *b* should be in free space."""
    length = float(np.linalg.norm(b - a))
    if length <= NOISE:
        return point_visibility(a, toward_camera, occluders)
    along = (b - a) / length
    if np.linalg.norm(np.cross(along, toward_camera)) <= 1e-9:
        # Seen end on: it is a point on the sheet, the end nearer the camera.
        nearer = a if np.dot(a - b, toward_camera) > 0 else b
        return point_visibility(nearer, toward_camera, occluders)
    hidden: List[Tuple[float, float]] = []
    for occluder in occluders:
        found = _hidden_by(occluder, a, along, length, toward_camera)
        if found is None:
            return UNKNOWN
        hidden.extend(found)
    stretches = _complement(_union(hidden), length)
    return Visibility(
        visible=bool(stretches),
        stretches=tuple((tuple(a + along * low), tuple(a + along * high)) for low, high in stretches),
    )


def _edge_visibility(line, root, transform, toward_camera, occluders, cut_timber) -> Visibility:
    """An edge: where it exists on its own timber, each stretch tested."""
    stretches = _on_surface(line, root)
    if not stretches:
        return UNKNOWN
    found = []
    for low, high in stretches:
        a = _np(line.point) + _unit(_np(line.direction)) * low
        b = _np(line.point) + _unit(_np(line.direction)) * high
        middle = (a + b) / 2
        off = _off_the_surface(_np(transform.local_to_global(_v3(middle))),
                               _np(transform.local_to_global_direction(_v3(b - a))), cut_timber, toward_camera)
        if off is None:
            return UNKNOWN
        shift = off - _np(transform.local_to_global(_v3(middle)))
        result = line_visibility(_np(transform.local_to_global(_v3(a))) + shift,
                                 _np(transform.local_to_global(_v3(b))) + shift, toward_camera, occluders)
        if not result.exact:
            return UNKNOWN
        found.extend(result.stretches)
    return Visibility(visible=bool(found), stretches=tuple(found))


def _edge_on_face_visibility(handle, root, transform, toward_camera, occluders, cut_timber) -> Visibility:
    """A face seen edge on is a line on the sheet, and what shows of it is its edges: any of them seen."""
    plane = handle.feature.locate_simple_unbounded(handle.owner)
    normal, point = _unit(_np(plane.normal)), _np(plane.point)
    edges = []
    for feature in handle.owner.get_declared_features():
        if feature.feature_type() is not CSGFeatureType.EDGE:
            continue
        line = feature.locate_simple_unbounded(handle.owner)
        if (isinstance(line, Line) and abs(float(np.dot(_np(line.direction), normal))) <= 1e-9
                and abs(float(np.dot(_np(line.point) - point, normal))) <= 1e-9):
            edges.append(line)
    if not edges:
        return UNKNOWN
    for line in edges:
        result = _edge_visibility(line, root, transform, toward_camera, occluders, cut_timber)
        if not result.exact or result.visible:
            return result
    return Visibility(visible=False)


def _on_surface(line, root) -> List[Tuple[float, float]]:
    """Where a line (timber local) lies on the cut timber's surface, as stations along it."""
    direction = _unit(_np(line.direction))
    unit_line = Line(direction=_v3(direction), point=line.point)
    for tolerance in (0.0, 1e-6):
        pieces = crop_line_to_boundary_segments_on_csg(
            unit_line, root, seed_reach=REACH, near=line.point, tolerance=tolerance)
        if pieces:
            origin = _np(line.point)
            found = []
            for piece in pieces:
                one = float(np.dot(_np(piece.start) - origin, direction))
                other = float(np.dot(_np(piece.end) - origin, direction))
                found.append((min(one, other), max(one, other)))
            return found
    return []


def _off_the_surface(at: np.ndarray, along: Optional[np.ndarray], own,
                     toward_camera: np.ndarray) -> Optional[np.ndarray]:
    """*at* moved NUDGE into free space beside its own timber, square to *along* if given.

    Sideways to the view first, so a line of sight grazing a surface stays beside it
    rather than being pushed behind it. None when no direction leads out: then it is
    not on that timber's surface at all.
    """
    if own is None:
        return at
    root = own.render_timber_with_cuts_csg_local()
    transform = own.timber.transform
    directions = sorted(_directions(along), key=lambda d: (round(abs(float(np.dot(d, toward_camera))), 6),
                                                          -float(np.dot(d, toward_camera))))
    for direction in directions:
        moved = at + direction * NUDGE
        if not root.contains_point(transform.global_to_local(_v3(moved))):
            return moved
    return None


def _directions(along: Optional[np.ndarray]) -> List[np.ndarray]:
    """Directions to try for leaving a surface: the axes and diagonals, square to *along* if given."""
    found = []
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            for z in (-1, 0, 1):
                direction = np.array([x, y, z], dtype=float)
                if along is not None:
                    unit = _unit(along)
                    direction = direction - unit * np.dot(direction, unit)
                if np.linalg.norm(direction) > 1e-6:
                    found.append(_unit(direction))
    return found


def _hidden_by(occluder, a, along, length, toward_camera) -> Optional[List[Tuple[float, float]]]:
    """The stations along the world segment that *occluder* hides, or None if it cannot say exactly."""
    root = occluder.render_timber_with_cuts_csg_local()
    transform = occluder.timber.transform
    a_local = _np(transform.global_to_local(_v3(a)))
    u = _unit(_np(transform.global_to_local_direction(_v3(along))))
    c = _unit(_np(transform.global_to_local_direction(_v3(toward_camera))))
    strip = [a_local, a_local + u * length, a_local + c * REACH, a_local + u * length + c * REACH]
    if not _boxes_meet(_box(strip), _aabb(root)):
        return []
    if _reaches_curves(root, strip):
        return None
    normal = _unit(np.cross(u, c))
    gram = np.array([[np.dot(u, u), np.dot(u, c)], [np.dot(u, c), np.dot(c, c)]])
    hidden: List[Tuple[float, float]] = []

    def stations(point):
        s, v = np.linalg.solve(gram, [np.dot(u, point - a_local), np.dot(c, point - a_local)])
        return float(s), float(v)

    # The region's outline: where the plane of sight meets each face plane, on the surface.
    for face_normal, face_point in _face_planes(root):
        direction = np.cross(normal, face_normal)
        if np.linalg.norm(direction) <= 1e-9:
            continue
        on_both = _point_on_both(normal, a_local, face_normal, face_point, direction)
        line = Line(direction=_v3(_unit(direction)), point=_v3(on_both))
        pieces = crop_line_to_boundary_segments_on_csg(line, root, seed_reach=REACH, near=_v3(a_local))
        if pieces is None:
            return None
        for piece in pieces:
            hidden.extend(_in_front(stations(_np(piece.start)), stations(_np(piece.end))))
    # And the region where it reaches the line itself.
    pieces = crop_line_to_segments_on_csg(
        Line(direction=_v3(u), point=_v3(a_local)), root, seed_reach=REACH, near=_v3(a_local))
    if pieces is None:
        return None
    for piece in pieces:
        low, high = sorted((float(np.dot(_np(piece.start) - a_local, u)), float(np.dot(_np(piece.end) - a_local, u))))
        hidden.append((low, high))
    return [(max(low, 0.0), min(high, length)) for low, high in hidden if min(high, length) - max(low, 0.0) > NOISE]


def _in_front(one: Tuple[float, float], other: Tuple[float, float]) -> List[Tuple[float, float]]:
    """The stations a piece of outline covers on the camera side (v > 0), as an interval."""
    (s0, v0), (s1, v1) = one, other
    if v0 <= NOISE and v1 <= NOISE:
        return []
    if v0 <= NOISE or v1 <= NOISE:
        # It crosses the line of the segment: keep the camera side.
        t = (NOISE - v0) / (v1 - v0)
        crossing = s0 + (s1 - s0) * t
        s0, s1 = (crossing, s1) if v0 <= NOISE else (s0, crossing)
    return [(min(s0, s1), max(s0, s1))]


def _point_on_both(n1, p1, n2, p2, direction) -> np.ndarray:
    """A point on two planes, given their line's direction."""
    matrix = np.array([n1, n2, direction])
    return np.linalg.solve(matrix, [np.dot(n1, p1), np.dot(n2, p2), np.dot(direction, p1)])


def _face_planes(root) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Every flat face plane in the tree, as (unit normal, point), timber local."""
    found = []

    def walk(node):
        if isinstance(node, HasFeatures):
            for feature in node.get_declared_features(FeatureSource.DEFAULTS):
                if feature.feature_type() is CSGFeatureType.FACE:
                    plane = feature.locate_simple_unbounded(node)
                    if isinstance(plane, Plane):
                        found.append((_unit(_np(plane.normal)), _np(plane.point)))
        for child in csg_children(node):
            walk(child)

    walk(root)
    return found


def _reaches_curves(root, points: Sequence[np.ndarray]) -> bool:
    """Whether a primitive with a curved face sits where the lines of sight could reach it."""
    reach = _box(points)

    def curved(node) -> bool:
        if isinstance(node, HasFeatures) and any(
                feature.feature_type() is CSGFeatureType.CURVED_FACE
                for feature in node.get_declared_features(FeatureSource.DEFAULTS)):
            return _boxes_meet(reach, _aabb(node))
        return any(curved(child) for child in csg_children(node))

    return curved(root)


def _box(points: Sequence[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    stacked = np.array(points)
    return stacked.min(axis=0), stacked.max(axis=0)


def _aabb(node) -> Optional[Tuple[List[Optional[float]], List[Optional[float]]]]:
    """A node's bounds, an unbounded side as None, or None if it cannot say."""
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            box = node.get_aabb()
    except Exception:
        return None
    if box is None:
        return None
    if getattr(box, "is_empty", False):
        return ([1.0, 1.0, 1.0], [-1.0, -1.0, -1.0])
    as_float = lambda value: None if value is None else float(value)  # noqa: E731
    return ([as_float(box.min_x), as_float(box.min_y), as_float(box.min_z)],
            [as_float(box.max_x), as_float(box.max_y), as_float(box.max_z)])


def _boxes_meet(box, bounds) -> bool:
    """Whether a box meets bounds that may be open on any side (unknown bounds meet everything)."""
    if bounds is None:
        return True
    low, high = box
    lows, highs = bounds
    for axis in range(3):
        if lows[axis] is not None and high[axis] < lows[axis]:
            return False
        if highs[axis] is not None and low[axis] > highs[axis]:
            return False
    return True


def _union(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    merged: List[List[float]] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1] + NOISE:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return [(low, high) for low, high in merged]


def _complement(hidden: List[Tuple[float, float]], length: float) -> List[Tuple[float, float]]:
    found, at = [], 0.0
    for low, high in hidden:
        if low - at > NOISE:
            found.append((at, low))
        at = max(at, high)
    if length - at > NOISE:
        found.append((at, length))
    return found
