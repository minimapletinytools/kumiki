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
into free space -- away from the camera where it can be -- so it is tested from
just behind itself. Only what is frontmost is seen: where two features lie on one
line of the sheet, like a box's near and far arrises on its outline, the far one is
hidden, since what is in front of it is the near one. A measurement to it would be
to something the view does not show.

A cylinder (a peg, a bore) cuts P in an ellipse, or a pair of lines, so its outline
is no longer straight. What is hidden then changes only at finitely many stations --
straight pieces' ends, each wall's extremes along the line, and where walls meet
face lines or each other -- and one line of sight between each pair decides.

What cannot be done exactly is not guessed at: any other curved primitive the lines
of sight could reach makes the answer "visible, not exact".
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..csg.cropcsg import crop_line_to_boundary_segments_on_csg, crop_line_to_segments_on_csg
from ..csg.cutcsg import CSGFeatureType, Cylinder, FeatureSource, HasFeatures, csg_children
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
        return _edge_visibility(located, root, transform, toward_camera, occluders, cut_timber, _owners(handle))
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
        if _curves_in_reach(root, [local, local + direction * REACH]) is None:
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


def _owners(handle) -> List:
    """What declares a feature: its owner, or for a derived one, its two parents' owners."""
    parents = getattr(handle.feature, "parents", None)
    if parents:
        return [parent.owner for parent in parents if parent is not None]
    return [handle.owner]


def _edge_visibility(line, root, transform, toward_camera, occluders, cut_timber, owners) -> Visibility:
    """An edge: where it exists on its own timber, each stretch tested."""
    stretches = _on_surface(line, root, owners)
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
        result = _edge_visibility(line, root, transform, toward_camera, occluders, cut_timber, [handle.owner])
        if not result.exact or result.visible:
            return result
    return Visibility(visible=False)


def _on_surface(line, root, owners) -> List[Tuple[float, float]]:
    """Where a line (timber local) is an edge: on the cut timber's surface, and within what
    declares it -- as a highlight is cropped. Its line can lie on the surface elsewhere too,
    where it is some other edge: a tenon's arris lines up with the tenon at the other end."""
    direction = _unit(_np(line.direction))
    unit_line = Line(direction=_v3(direction), point=line.point)
    origin = _np(line.point)

    def stations(pieces):
        found = []
        for piece in pieces or []:
            one = float(np.dot(_np(piece.start) - origin, direction))
            other = float(np.dot(_np(piece.end) - origin, direction))
            found.append((min(one, other), max(one, other)))
        return found

    for tolerance in (0.0, 1e-6):
        on_surface = stations(crop_line_to_boundary_segments_on_csg(
            unit_line, root, seed_reach=REACH, near=line.point, tolerance=tolerance))
        for owner in owners:
            within = stations(crop_line_to_segments_on_csg(
                unit_line, owner, seed_reach=REACH, near=line.point, tolerance=1e-6))
            on_surface = _intersect(on_surface, within)
        if on_surface:
            return on_surface
    return []


def _intersect(one: List[Tuple[float, float]], other: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    found = []
    for low, high in one:
        for other_low, other_high in other:
            start, end = max(low, other_low), min(high, other_high)
            if end - start > NOISE:
                found.append((start, end))
    return found


def _off_the_surface(at: np.ndarray, along: Optional[np.ndarray], own,
                     toward_camera: np.ndarray) -> Optional[np.ndarray]:
    """*at* moved NUDGE into free space beside its own timber, square to *along* if given.

    Away from the camera first, so it is tested from just behind itself: anything at
    all in front of it -- a surface its line of sight would only graze included --
    hides it. None when no direction leads out: then it is not on that timber's
    surface at all.
    """
    if own is None:
        return at
    root = own.render_timber_with_cuts_csg_local()
    transform = own.timber.transform
    directions = sorted(_directions(along), key=lambda d: round(float(np.dot(d, toward_camera)), 6))
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
    cylinders = _curves_in_reach(root, strip)
    if cylinders is None:
        return None
    normal = _unit(np.cross(u, c))
    gram = np.array([[np.dot(u, u), np.dot(u, c)], [np.dot(u, c), np.dot(c, c)]])
    hidden: List[Tuple[float, float]] = []

    def stations(point):
        s, v = np.linalg.solve(gram, [np.dot(u, point - a_local), np.dot(c, point - a_local)])
        return float(s), float(v)

    # The region's outline: where the plane of sight meets each face plane, on the surface.
    planes = _face_planes(root) + [cap for cylinder in cylinders for cap in _caps(cylinder)]
    lines, breaks = [], [0.0, length]
    for face_normal, face_point in planes:
        direction = np.cross(normal, face_normal)
        if np.linalg.norm(direction) <= 1e-9:
            continue
        on_both = _point_on_both(normal, a_local, face_normal, face_point, direction)
        lines.append((np.array(stations(on_both)), np.array(stations(on_both + _unit(direction))) - stations(on_both)))
        line = Line(direction=_v3(_unit(direction)), point=_v3(on_both))
        pieces = crop_line_to_boundary_segments_on_csg(line, root, seed_reach=REACH, near=_v3(a_local))
        if pieces is None:
            return None
        for piece in pieces:
            ends = stations(_np(piece.start)), stations(_np(piece.end))
            breaks.extend(end[0] for end in ends)
            hidden.extend(_in_front(*ends))
    if cylinders:
        # A cylinder's outline in the plane is curved, so the straight pieces no longer bound
        # the region. What is hidden changes only at the stations listed here; between them
        # one line of sight decides.
        conics = [_conic(cylinder, a_local, u, c) for cylinder in cylinders]
        breaks.extend(_conic_stations(conics, lines))
        hidden = []
        cuts = sorted(b for b in breaks if 0.0 <= b <= length)
        for low, high in zip(cuts, cuts[1:]):
            if high - low <= NOISE:
                continue
            middle = a_local + u * (low + high) / 2
            pieces = crop_line_to_segments_on_csg(
                Line(direction=_v3(c), point=_v3(middle)), root, seed_reach=REACH, near=_v3(middle))
            if pieces is None:
                return None
            if any(max(float(np.dot(_np(piece.start) - middle, c)), float(np.dot(_np(piece.end) - middle, c))) > NOISE
                   for piece in pieces):
                hidden.append((low, high))
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


def _curves_in_reach(root, points: Sequence[np.ndarray]) -> Optional[List[Cylinder]]:
    """The cylinders the lines of sight could reach, or None if another curved primitive could."""
    reach = _box(points)
    found: List[Cylinder] = []

    def walk(node) -> bool:
        if isinstance(node, Cylinder):
            if _meets_cylinder(points, node):
                found.append(node)
            return True
        if isinstance(node, HasFeatures) and any(
                feature.feature_type() is CSGFeatureType.CURVED_FACE
                for feature in node.get_declared_features(FeatureSource.DEFAULTS)):
            return not _boxes_meet(reach, _aabb(node))
        return all(walk(child) for child in csg_children(node))

    return found if walk(root) else None


def _caps(cylinder: Cylinder) -> List[Tuple[np.ndarray, np.ndarray]]:
    axis = _unit(_np(cylinder.axis_direction))
    return [(axis, _np(cylinder.position) + axis * float(d))
            for d in (cylinder.start_distance, cylinder.end_distance) if d is not None]


def _conic(cylinder: Cylinder, a, u, c):
    """The cylinder's wall in the plane a + u s + c v, as f(s, v) = z'Mz + 2 b'z + k."""
    axis = _unit(_np(cylinder.axis_direction))
    square = np.eye(3) - np.outer(axis, axis)
    w0 = a - _np(cylinder.position)
    basis = np.array([u, c]).T
    return (basis.T @ square @ basis, basis.T @ square @ w0,
            float(w0 @ square @ w0) - float(cylinder.radius) ** 2)


def _on_conic(conic):
    """The conic as parametrised pieces: ('ellipse', centre, L) for z = centre + L (cos t, sin t),
    or ('line', point, direction); empty if it has no points."""
    m, b, k = conic
    if np.linalg.det(m) > 1e-12 * max(1.0, float(np.trace(m)) ** 2):
        centre = -np.linalg.solve(m, b)
        level = -(k - float(centre @ m @ centre))
        if level <= 0:
            return []
        values, vectors = np.linalg.eigh(m)
        return [("ellipse", centre, vectors @ np.diag(np.sqrt(level / values)))]
    # Seen along its axis or parallel to it: the wall is a pair of parallel lines.
    values, vectors = np.linalg.eigh(m)
    across, along = vectors[:, 1], vectors[:, 0]
    if values[1] <= 1e-12:
        return []
    # f along `across` (t) is values[1] t^2 + 2 (b.across) t + k, taking z = t across + r along.
    roots = _real_roots([values[1], 2 * float(b @ across), k])
    return [("line", across * t, along) for t in roots]


def _real_roots(coefficients) -> List[float]:
    coefficients = np.array(coefficients, dtype=float)
    while len(coefficients) > 1 and abs(coefficients[0]) <= 1e-14:
        coefficients = coefficients[1:]
    if len(coefficients) <= 1:
        return []
    return [float(r.real) for r in np.roots(coefficients) if abs(r.imag) <= 1e-7 * max(1.0, abs(r))]


def _on_line_meets(conic, point, direction) -> List[np.ndarray]:
    m, b, k = conic
    roots = _real_roots([direction @ m @ direction, 2 * (point @ m @ direction + b @ direction),
                         point @ m @ point + 2 * b @ point + k])
    return [point + direction * t for t in roots]


def _ellipse_meets(conic, centre, shape) -> List[np.ndarray]:
    """Where z = centre + shape (cos t, sin t) meets the conic, with tan(t/2) as the unknown."""
    m, b, k = conic
    # f(z) along the ellipse in terms of x = cos t, y = sin t.
    p, q = shape[:, 0], shape[:, 1]
    xx, yy, xy = p @ m @ p, q @ m @ q, 2 * p @ m @ q
    x1, y1 = 2 * (centre @ m @ p + b @ p), 2 * (centre @ m @ q + b @ q)
    k0 = centre @ m @ centre + 2 * b @ centre + k
    # x = (1 - h^2)/(1 + h^2), y = 2h/(1 + h^2), times (1 + h^2)^2.
    quartic = [xx - x1 + k0, 2 * xy - 2 * y1, -2 * xx + 4 * yy + 2 * k0, -2 * xy + 2 * y1, xx + x1 + k0]
    found = [centre + p * (1 - h * h) / (1 + h * h) + q * 2 * h / (1 + h * h) for h in _real_roots(quartic)]
    if abs(xx - x1 + k0) <= 1e-12:
        found.append(centre - p)  # t = pi, where tan(t/2) runs off
    return found


def _conic_stations(conics, lines) -> List[float]:
    """Every station where the outline might turn back or cross: each wall's extremes
    along the edge and where it meets a face line or another wall."""
    pieces = [piece for conic in conics for piece in _on_conic(conic)]
    found: List[float] = []
    for kind, origin, shape in pieces:
        if kind == "ellipse":
            reach = float(np.hypot(shape[0, 0], shape[0, 1]))
            found.extend([origin[0] - reach, origin[0] + reach])
        elif abs(shape[0]) <= 1e-9:
            found.append(float(origin[0]))
    for conic in conics:
        for point, direction in lines:
            found.extend(float(z[0]) for z in _on_line_meets(conic, point, direction))
        for kind, origin, shape in pieces:
            if kind == "ellipse":
                found.extend(float(z[0]) for z in _ellipse_meets(conic, origin, shape))
            else:
                found.extend(float(z[0]) for z in _on_line_meets(conic, origin, shape))
    return found


def _meets_cylinder(points: Sequence[np.ndarray], cylinder: Cylinder) -> bool:
    """Whether the convex hull of *points* (a segment or a flat parallelogram from
    points[0]) meets the cylinder's bounding box, by separating axes."""
    axis = _unit(_np(cylinder.axis_direction))
    start = -1e9 if cylinder.start_distance is None else float(cylinder.start_distance)
    end = 1e9 if cylinder.end_distance is None else float(cylinder.end_distance)
    center = _np(cylinder.position) + axis * (start + end) / 2
    across = _unit(np.cross(axis, [1.0, 0, 0] if abs(axis[0]) < 0.9 else [0, 1.0, 0]))
    box = [(axis, (end - start) / 2), (across, float(cylinder.radius)),
           (np.cross(axis, across), float(cylinder.radius))]
    spans = [p - points[0] for p in points[1:3]]
    tests = [d for d, _ in box] + [np.cross(d, span) for d, _ in box for span in spans]
    if len(spans) == 2:
        tests.append(np.cross(spans[0], spans[1]))
    for test in tests:
        size = np.linalg.norm(test)
        if size <= 1e-12:
            continue
        test = test / size
        mine = [float(np.dot(p, test)) for p in points]
        middle = float(np.dot(center, test))
        radius = sum(half * abs(float(np.dot(d, test))) for d, half in box)
        if min(mine) > middle + radius + NOISE or max(mine) < middle - radius - NOISE:
            return False
    return True


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
