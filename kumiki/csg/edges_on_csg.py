"""Cropping unbounded lines to a CSG solid, and the half spaces that bound each primitive.

- `solid_bounds`: a primitive as the intersection of half spaces. Approximations (a cylinder's
  hexagon, a twisted loft, a path extrusion's point hull) always err outward, so a region always
  contains the true solid.
- `crop_line_to_*_segments_on_csg`: the pieces of a line on a solid, its surface, its interior, or
  where its surface creases (an arris). Exact for cylinders and for primitives that are exactly
  their half spaces; others use their bounds.

Faces are cropped by plane in cross_sections.py.
"""

import math
from dataclasses import dataclass
from enum import Enum
import warnings
from typing import List, Optional, Sequence, Tuple

from ..geometry import (
    Line,
    LineSegment,
    perpendicular_axes,
    unit_vector,
)
from ..rule import V3, Matrix, Numeric, safe_magnitude, scalar
from .identity_memo import memo_by_identity


def convex_hull_2d(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Return the convex hull of 2D points, counter-clockwise (monotone chain)."""
    unique = sorted(set(points))
    if len(unique) < 3:
        return unique

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: List[Tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


# A solid, as the half spaces that bound it: each an outward normal and a point
# on its plane, so a point is inside when (p - point) . normal <= 0 for all.
BoundingHalfSpaces = List[Tuple[V3, V3]]


class BoundsKind(Enum):
    """Which kind of answer solid_bounds gave."""

    HALF_SPACES = 0
    EMPTY = 1
    UNKNOWN = 2


# TODO this is Convex right? can we rename this to 3dConvexHull or something?
@dataclass(frozen=True)
class SolidBounds:
    """What solid_bounds knows about a solid:

    - HALF_SPACES: the solid is the intersection of `faces`.
    - EMPTY: the solid contains nothing.
    - UNKNOWN: a solid it can't describe; callers must give up.

    `faces` is None unless HALF_SPACES.
    """

    kind: BoundsKind
    faces: Optional[BoundingHalfSpaces] = None

    @staticmethod
    def of(faces: BoundingHalfSpaces) -> 'SolidBounds':
        return SolidBounds(kind=BoundsKind.HALF_SPACES, faces=faces)

    def require_faces(self) -> BoundingHalfSpaces:
        """Return `faces`; raises TypeError unless the kind is HALF_SPACES."""
        if self.faces is None:
            raise TypeError(
                f"bounds of kind {self.kind.name} have no half spaces -- check kind, "
                f"or is_empty / is_unknown, before asking for them"
            )
        return self.faces

    @property
    def is_empty(self) -> bool:
        return self.kind is BoundsKind.EMPTY

    @property
    def is_unknown(self) -> bool:
        return self.kind is BoundsKind.UNKNOWN


EMPTY_BOUNDS = SolidBounds(kind=BoundsKind.EMPTY)
UNKNOWN_BOUNDS = SolidBounds(kind=BoundsKind.UNKNOWN)


@memo_by_identity
def solid_bounds(csg) -> SolidBounds:
    """Return a primitive's bounding half spaces (outward approximations), EMPTY, or UNKNOWN."""
    from .cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, Cylinder,
                         EmptyCSG, HalfSpace, RectangularPrism)
    from .pathcsg import PathExtrusion

    if isinstance(csg, EmptyCSG):
        return EMPTY_BOUNDS

    if isinstance(csg, HalfSpace):
        # Inside is p . normal >= offset, so the outward normal is the other way.
        normal = unit_vector(csg.normal)
        return SolidBounds.of([(-normal, normal * csg.offset)])

    if isinstance(csg, RectangularPrism):
        width_dir, height_dir, length_dir = csg._local_axes()
        centre = csg.transform.position
        half_width = csg.size[0] / scalar(2)
        half_height = csg.size[1] / scalar(2)
        faces: BoundingHalfSpaces = [
            (width_dir, centre + width_dir * half_width),
            (-width_dir, centre - width_dir * half_width),
            (height_dir, centre + height_dir * half_height),
            (-height_dir, centre - height_dir * half_height),
        ]
        # An end that runs to infinity bounds nothing, and says so by being None.
        if csg.end_distance is not None:
            faces.append((length_dir, centre + length_dir * csg.end_distance))
        if csg.start_distance is not None:
            faces.append((-length_dir, centre + length_dir * csg.start_distance))
        return SolidBounds.of(faces)

    if isinstance(csg, Cylinder):
        # A circumscribing hexagon.
        axis = unit_vector(csg.axis_direction)
        across, up = perpendicular_axes(axis)
        faces = []
        for step in range(6):
            angle = math.pi * step / 3
            normal = across * scalar(math.cos(angle)) + up * scalar(math.sin(angle))
            faces.append((normal, csg.position + normal * csg.radius))
        return SolidBounds.of(faces + _extrusion_caps(
            axis, csg.position, csg.start_distance, csg.end_distance))

    if isinstance(csg, ConvexPolygonExtrusion):
        return _bounds_or_unknown(_extruded_hull_half_spaces(
            [(float(x), float(y)) for x, y in csg.points],
            csg.transform, csg.start_distance, csg.end_distance,
        ))

    if isinstance(csg, PathExtrusion):
        # The hull of the path's segment start points.
        # KNOWN BUG: an arc bulging outward lies outside this hull, so the bound is too small.
        points = [seg.start for seg in csg.path.segments]
        return _bounds_or_unknown(_extruded_hull_half_spaces(
            [(float(point[0, 0]), float(point[1, 0])) for point in points],
            csg.transform, csg.start_distance, csg.end_distance,
        ))

    if isinstance(csg, ConvexPolygonSimpleLoft):
        return _bounds_or_unknown(_loft_half_spaces(csg))

    return UNKNOWN_BOUNDS


def _bounds_or_unknown(faces: Optional[BoundingHalfSpaces]) -> SolidBounds:
    """Wrap `faces` as SolidBounds, or UNKNOWN if None."""
    return UNKNOWN_BOUNDS if faces is None else SolidBounds.of(faces)


def _loft_half_spaces(csg) -> Optional[BoundingHalfSpaces]:
    """Return the half spaces bounding a loft between two convex profiles, or None if malformed.

    Exact when each side is planar; otherwise each side's plane is pushed out to the furthest corner.
    """
    matrix = csg.transform.orientation.matrix
    across = Matrix([matrix[0, 0], matrix[1, 0], matrix[2, 0]])
    up = Matrix([matrix[0, 1], matrix[1, 1], matrix[2, 1]])
    axis = Matrix([matrix[0, 2], matrix[1, 2], matrix[2, 2]])
    origin = csg.transform.position

    def lift(point, distance) -> V3:
        return (origin + axis * distance
                + across * scalar(float(point[0]))
                + up * scalar(float(point[1])))

    bottom = [lift(point, csg.bottom_points_z_pos) for point in csg.bottom_points]
    top = [lift(point, csg.top_points_z_pos) for point in csg.top_points]
    if len(bottom) < 3 or len(bottom) != len(top):
        return None

    corners = bottom + top
    middle = corners[0]
    for corner in corners[1:]:
        middle = middle + corner
    middle = middle / scalar(len(corners))

    faces: BoundingHalfSpaces = _extrusion_caps(
        axis, origin, csg.bottom_points_z_pos, csg.top_points_z_pos)

    for index in range(len(bottom)):
        following = (index + 1) % len(bottom)
        along = bottom[following] - bottom[index]
        rising = top[index] - bottom[index]
        normal = _cross(along, rising)
        if safe_magnitude(normal) < 1e-12:
            return None
        normal = unit_vector(normal)
        # Outward, whichever way the profiles were wound.
        if float(((middle - bottom[index]).T * normal)[0, 0]) > 0:
            normal = -normal
        # Pushed out to the furthest corner.
        reach = max(float(((corner - bottom[index]).T * normal)[0, 0])
                    for corner in corners)
        faces.append((normal, bottom[index] + normal * scalar(reach)))

    return faces


def _cross(a: V3, b: V3) -> V3:
    return Matrix([
        float(a[1, 0]) * float(b[2, 0]) - float(a[2, 0]) * float(b[1, 0]),
        float(a[2, 0]) * float(b[0, 0]) - float(a[0, 0]) * float(b[2, 0]),
        float(a[0, 0]) * float(b[1, 0]) - float(a[1, 0]) * float(b[0, 0]),
    ])


def _extrusion_caps(axis: V3, position: V3, start_distance, end_distance) -> BoundingHalfSpaces:
    """Return the two end caps of an extrusion as half spaces, skipping an end at infinity."""
    caps: BoundingHalfSpaces = []
    if end_distance is not None:
        caps.append((axis, position + axis * end_distance))
    if start_distance is not None:
        caps.append((-axis, position + axis * start_distance))
    return caps


def _extruded_hull_half_spaces(
    points: Sequence[Tuple[float, float]],
    transform,
    start_distance,
    end_distance,
) -> Optional[BoundingHalfSpaces]:
    """Return the half spaces bounding the extrusion of the convex hull of `points`, or None if degenerate."""
    hull = convex_hull_2d(points)
    if len(hull) < 3:
        return None

    matrix = transform.orientation.matrix
    across = Matrix([matrix[0, 0], matrix[1, 0], matrix[2, 0]])
    up = Matrix([matrix[0, 1], matrix[1, 1], matrix[2, 1]])
    axis = Matrix([matrix[0, 2], matrix[1, 2], matrix[2, 2]])
    origin = transform.position

    middle = (
        sum(corner[0] for corner in hull) / len(hull),
        sum(corner[1] for corner in hull) / len(hull),
    )

    faces: BoundingHalfSpaces = []
    for index, corner in enumerate(hull):
        following = hull[(index + 1) % len(hull)]
        edge = (following[0] - corner[0], following[1] - corner[1])
        normal = (edge[1], -edge[0])
        # Outward, whichever way round the hull was wound.
        towards_middle = (middle[0] - corner[0], middle[1] - corner[1])
        if normal[0] * towards_middle[0] + normal[1] * towards_middle[1] > 0:
            normal = (-normal[0], -normal[1])
        length = math.hypot(normal[0], normal[1])
        if length == 0:
            continue
        direction = across * scalar(normal[0] / length) + up * scalar(normal[1] / length)
        point = origin + across * scalar(corner[0]) + up * scalar(corner[1])
        faces.append((direction, point))

    return faces + _extrusion_caps(axis, origin, start_distance, end_distance)


# A stretch of the line, as the two parameter values bounding it.
Span = Tuple[float, float]

# How close to the surface a checked midpoint may be and still count as on it.
_VERIFY_EPS = 1e-9


# Slack for deciding whether a line lying in a face plane is on the solid.
_IN_PLANE_EPS = 1e-9


def _spans_within_primitive(
    faces: BoundingHalfSpaces,
    line: Line,
    seed: Span,
    tolerance: float,
    removing: bool = False,
) -> List[Span]:
    """Clip `seed` by one convex solid's half spaces; returns one span or none.

    A line lying on a boundary is kept: `removing` flips the comparison so that holds for a
    subtracted solid too.
    """
    direction = unit_vector(line.direction)
    origin = line.point
    low, high = seed
    for normal, point in faces:
        # Keep where dot(normal, p - point) <= 0, with p = origin + s * direction.
        along = float((normal.T * direction)[0, 0])
        offset = float((normal.T * (origin - point))[0, 0])
        if abs(along) < 1e-12:
            # Parallel to the line: keeps all of it or none.
            if (offset >= tolerance - _IN_PLANE_EPS if removing
                    else offset > tolerance + _IN_PLANE_EPS):
                return []
            continue
        bound = (tolerance - offset) / along
        if along > 0:
            high = min(high, bound)
        else:
            low = max(low, bound)
        if low > high:
            return []
    return [(low, high)]


def _merged_spans(spans: Sequence[Span]) -> List[Span]:
    """Return `spans` with overlapping and touching ones joined, in order."""
    ordered = sorted(span for span in spans if span[1] > span[0])
    merged: List[Span] = []
    for low, high in ordered:
        if merged and low <= merged[-1][1]:
            if high > merged[-1][1]:
                merged[-1] = (merged[-1][0], high)
            continue
        merged.append((low, high))
    return merged


def _intersected_spans(left: Sequence[Span], right: Sequence[Span]) -> List[Span]:
    """Return the stretches covered by both span lists."""
    out: List[Span] = []
    for a_low, a_high in left:
        for b_low, b_high in right:
            low, high = max(a_low, b_low), min(a_high, b_high)
            if high > low:
                out.append((low, high))
    return _merged_spans(out)


def _subtracted_spans(keep: Sequence[Span], remove: Sequence[Span]) -> List[Span]:
    """Return `keep` with `remove` taken out."""
    out = list(keep)
    for cut_low, cut_high in _merged_spans(remove):
        next_out: List[Span] = []
        for low, high in out:
            if cut_high <= low or cut_low >= high:
                next_out.append((low, high))
                continue
            if cut_low > low:
                next_out.append((low, cut_low))
            if cut_high < high:
                next_out.append((cut_high, high))
        out = next_out
    return _merged_spans(out)


def _cylinder_spans(
    csg, line: Line, seed: Span, tolerance: float, removing: bool,
) -> List[Span]:
    """Return where a line runs inside a cylinder (solved exactly), clipped to `seed`."""
    axis = unit_vector(csg.axis_direction)
    direction = unit_vector(line.direction)
    offset = line.point - csg.position

    def perpendicular(vector: V3) -> V3:
        return vector - axis * scalar(float((vector.T * axis)[0, 0]))

    across = perpendicular(direction)
    start = perpendicular(offset)
    radius = float(csg.radius) + tolerance
    if radius <= 0.0:
        # Shrunk past nothing by a tolerance bigger than the bore itself.
        return []

    a = float((across.T * across)[0, 0])
    b = 2.0 * float((start.T * across)[0, 0])
    c = float((start.T * start)[0, 0]) - radius * radius

    low, high = seed
    if a < 1e-18:
        # Parallel to the axis: wholly in or out; a line on the barrel is kept.
        outside = c >= 0.0 if removing else c > 0.0
        if outside:
            return []
    else:
        discriminant = b * b - 4.0 * a * c
        if discriminant <= 0.0:
            # Misses it, or touches at a single point, which is no length.
            return []
        root = discriminant ** 0.5
        low = max(low, (-b - root) / (2.0 * a))
        high = min(high, (-b + root) / (2.0 * a))
        if low >= high:
            return []

    caps = _extrusion_caps(axis, csg.position, csg.start_distance, csg.end_distance)
    if not caps:
        return [(low, high)] if high > low else []
    return _spans_within_primitive(caps, line, (low, high), tolerance, removing)


def _loft_sides_are_planar(csg) -> bool:
    """Return whether every side quad of a loft is planar, so its half spaces describe it exactly."""
    bottom, top = csg.bottom_points, csg.top_points
    if csg.bottom_points_z_pos is None or csg.top_points_z_pos is None:
        return False
    if len(bottom) < 3 or len(bottom) != len(top):
        return False

    matrix = csg.transform.orientation.matrix
    across = Matrix([matrix[0, 0], matrix[1, 0], matrix[2, 0]])
    up = Matrix([matrix[0, 1], matrix[1, 1], matrix[2, 1]])
    axis = Matrix([matrix[0, 2], matrix[1, 2], matrix[2, 2]])
    origin = csg.transform.position

    def lift(point, distance) -> V3:
        return (origin + axis * distance
                + across * scalar(float(point[0]))
                + up * scalar(float(point[1])))

    for index in range(len(bottom)):
        following = (index + 1) % len(bottom)
        corners = [
            lift(bottom[index], csg.bottom_points_z_pos),
            lift(bottom[following], csg.bottom_points_z_pos),
            lift(top[following], csg.top_points_z_pos),
            lift(top[index], csg.top_points_z_pos),
        ]
        first = corners[1] - corners[0]
        second = corners[2] - corners[0]
        third = corners[3] - corners[0]
        normal = _cross(first, second)
        scale = safe_magnitude(normal) * safe_magnitude(third)
        if scale == 0.0:
            # Degenerate side.
            continue
        if abs(float((third.T * normal)[0, 0])) / scale > _PLANAR_ENOUGH:
            return False
    return True


# Sine of the angle a quad's fourth corner may miss the plane of the other three by and count as flat.
_PLANAR_ENOUGH = 1e-9


def _exact_spans(
    csg, line: Line, seed: Span, tolerance: float, removing: bool,
) -> Optional[List[Span]]:
    """Return where a line runs inside a primitive, exactly, or None if the shape isn't solved.

    Prisms, half spaces, convex extrusions and planar-sided lofts are exactly their half spaces;
    cylinders are solved directly. Path extrusions and twisted lofts return None.
    """
    from .cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, Cylinder,
                         HalfSpace, RectangularPrism)

    if isinstance(csg, Cylinder):
        return _cylinder_spans(csg, line, seed, tolerance, removing)

    exactly_bounded = isinstance(csg, (HalfSpace, RectangularPrism, ConvexPolygonExtrusion))
    if isinstance(csg, ConvexPolygonSimpleLoft):
        exactly_bounded = _loft_sides_are_planar(csg)

    if not exactly_bounded:
        return None

    bounds = solid_bounds(csg)
    if bounds.is_unknown:
        return None
    if bounds.is_empty:
        return []
    return _spans_within_primitive(bounds.require_faces(), line, seed, tolerance, removing)


def _spans_on_csg(
    csg, line: Line, seed: Span, tolerance: float, removing: bool = False,
    flush_removes: bool = True,
) -> Optional[List[Span]]:
    """Return where a line runs inside a CSG tree, as parameter spans, or None if any primitive is UNKNOWN.

    `tolerance` and `removing` flip on the way into a subtracted solid, so a cut removes less rather
    than more and a line on a cut's wall is kept. With `flush_removes`, a line on a cut's wall is
    removed where it is also on the base's surface (a face planed away flush).
    """
    from .cutcsg import Difference, Intersection, SolidUnion

    if isinstance(csg, SolidUnion):
        out: List[Span] = []
        for child in csg.children:
            spans = _spans_on_csg(child, line, seed, tolerance, removing, flush_removes)
            if spans is None:
                return None
            out.extend(spans)
        return _merged_spans(out)

    if isinstance(csg, Intersection):
        left = _spans_on_csg(csg.left, line, seed, tolerance, removing, flush_removes)
        if left is None:
            return None
        if not left:
            return []
        right = _spans_on_csg(csg.right, line, seed, tolerance, removing, flush_removes)
        if right is None:
            return None
        return _intersected_spans(left, right)

    if isinstance(csg, Difference):
        kept = _spans_on_csg(csg.base, line, seed, tolerance, removing, flush_removes)
        if kept is None:
            return None
        if not kept:
            # Nothing to cut from, whatever the cuts are.
            return []

        # Where the line lies on the base's surface rather than inside it.
        inside = _spans_on_csg(csg.base, line, seed, tolerance, not removing, flush_removes)
        if inside is None:
            return None
        on_surface = _subtracted_spans(kept, inside)

        removed: List[Span] = []
        for solid in csg.subtract:
            strictly_in = _spans_on_csg(solid, line, seed, -tolerance, not removing, flush_removes)
            if strictly_in is None:
                return None
            removed.extend(strictly_in)

            # A line on a cut's wall is removed only where it is also on the base's surface.
            if not flush_removes:
                continue
            touching = _spans_on_csg(solid, line, seed, -tolerance, removing, flush_removes)
            if touching is None:
                return None
            removed.extend(_intersected_spans(touching, on_surface))

        return _subtracted_spans(kept, removed)

    exact = _exact_spans(csg, line, seed, tolerance, removing)
    if exact is not None:
        return exact

    bounds = solid_bounds(csg)
    if bounds.is_unknown:
        return None
    if bounds.is_empty:
        return []
    return _spans_within_primitive(bounds.require_faces(), line, seed, tolerance, removing)


def crop_line_to_segments_on_csg(
    line: Line,
    csg,

    # TODO this parameter is questionable, just use NaN for bounds?
    seed_reach: Numeric,

    near: Optional[V3] = None,
    tolerance: float = 0.0,
) -> Optional[List[LineSegment]]:
    """Return the pieces of `line` on the solid `csg`, surface included.

    Returns None if the tree has a primitive it can't describe, [] if the line misses the solid.
    The search starts from an interval `seed_reach` either side of `near` (or of the line's point).
    Pass the same `tolerance` used to find the line (e.g. a derived edge's meeting tolerance).
    """
    seed = _seed_span(line, seed_reach, near)
    spans = _closed_spans(line, csg, seed, tolerance)
    if spans is None:
        return None
    return _segments(line, spans)


def crop_line_to_interior_segments_on_csg(
    line: Line,
    csg,
    seed_reach: Numeric,
    near: Optional[V3] = None,
) -> Optional[List[LineSegment]]:
    """Return the pieces of `line` strictly inside `csg` (not on its surface). Same returns as crop_line_to_segments_on_csg."""
    interior = _interior_spans(line, csg, _seed_span(line, seed_reach, near), 0.0)
    return None if interior is None else _segments(line, interior)


def crop_line_to_boundary_segments_on_csg(
    line: Line,
    csg,
    seed_reach: Numeric,
    near: Optional[V3] = None,
    tolerance: float = 0.0,
) -> Optional[List[LineSegment]]:
    """Return the pieces of `line` on the surface of `csg` (not inside it). Same returns as crop_line_to_segments_on_csg.

    The closed pieces less the interior, taken at minus `tolerance`.
    """
    spans = _boundary_spans(line, csg, _seed_span(line, seed_reach, near), tolerance)
    return None if spans is None else _segments(line, spans)


def _boundary_spans(line: Line, csg, seed: Span, tolerance: float) -> Optional[List[Span]]:
    closed = _closed_spans(line, csg, seed, tolerance)
    if closed is None:
        return None
    interior = _interior_spans(line, csg, seed, -tolerance)
    if interior is None:
        return None
    return _subtracted_spans(closed, interior)


def crop_line_to_crease_segments_on_csg(
    line: Line,
    csg,
    seed_reach: Numeric,
    near: Optional[V3] = None,
    tolerance: float = 0.0,
) -> Optional[List[LineSegment]]:
    """Return the pieces of `line` where the surface of `csg` creases along it: a real edge.

    The boundary pieces less where the line lies within one flat face. Same returns as
    crop_line_to_segments_on_csg.
    """
    seed = _seed_span(line, seed_reach, near)
    spans = _boundary_spans(line, csg, seed, tolerance)
    if spans is None:
        return None
    return _segments(line, _crease_spans(line, csg, spans, seed, tolerance))


def is_crease_at(line: Line, csg, point: V3, tolerance: float = 0.0) -> bool:
    """Return whether the surface of `csg` creases along `line` at `point`. True when unsure."""
    direction = unit_vector(line.direction)
    station = float(((point - line.point).T * direction)[0, 0])
    return _directions_at(csg, line, station, tolerance) is not _FLAT


# --- which way the solid lies around a line ---------------------------------------------------
#
# At a point on a line, the solid occupies spans of angle around it. None or all: off the solid or
# inside it. One half turn: the line lies in a flat face. Anything else: the surface creases there.

# How close, in radians, two angles may be and count as one.
_ANGLE_EPS = 1e-6
_TAU = 2.0 * math.pi
_FLAT = "flat"
# A span of angle around the line, (low, high) in radians within [0, 2pi].
AngleSpan = Tuple[float, float]
AngleSpans = List[AngleSpan]


def _angles_union(one: AngleSpans, other: AngleSpans) -> AngleSpans:
    merged: AngleSpans = []
    for low, high in sorted(one + other):
        if merged and low <= merged[-1][1] + _ANGLE_EPS:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


def _angles_intersection(one: AngleSpans, other: AngleSpans) -> AngleSpans:
    out = [(max(a, c), min(b, d)) for a, b in one for c, d in other if min(b, d) - max(a, c) > _ANGLE_EPS]
    return _angles_union(out, [])


def _angles_less(one: AngleSpans, other: AngleSpans) -> AngleSpans:
    rest = [(0.0, _TAU)]
    for low, high in other:
        rest = [piece for a, b in rest for piece in ((a, min(b, low)), (max(a, high), b))
                if piece[1] - piece[0] > _ANGLE_EPS]
    return _angles_intersection(one, rest)


def _half_turn(normal, basis) -> AngleSpans:
    """Return the angles around the line on a plane's solid side: within a quarter turn of -normal."""
    u, v = basis
    centre = math.atan2(-float(normal @ v), -float(normal @ u)) % _TAU
    low, high = centre - math.pi / 2, centre + math.pi / 2
    if low < 0:
        return [(0.0, high), (low + _TAU, _TAU)]
    if high > _TAU:
        return [(0.0, high - _TAU), (low, _TAU)]
    return [(low, high)]


def _plane_angles(faces, at, direction, basis, tolerance) -> AngleSpans:
    """Return the angles around the line occupied by a convex solid given as half spaces."""
    import numpy as np

    angles: AngleSpans = [(0.0, _TAU)]
    for normal, point in faces:
        n = np.array([float(normal[i, 0]) for i in range(3)])
        n /= np.linalg.norm(n)
        distance = float(n @ (at - np.array([float(point[i, 0]) for i in range(3)])))
        if distance > tolerance + _IN_PLANE_EPS:
            return []
        if distance < -(tolerance + _IN_PLANE_EPS):
            continue
        across = n - direction * float(n @ direction)
        if float(np.linalg.norm(across)) < 1e-12:
            continue  # square to the line: only where it crosses, which no tested place is
        angles = _angles_intersection(angles, _half_turn(across, basis))
    return angles


def _primitive_angles(csg, at, direction, basis, tolerance) -> Optional[AngleSpans]:
    """Return the angles around the line a primitive occupies at `at`, or None if the shape isn't solved."""
    import numpy as np
    from .cutcsg import ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, Cylinder, HalfSpace, RectangularPrism

    if isinstance(csg, Cylinder):
        axis = np.array([float(v) for v in unit_vector(csg.axis_direction)])
        offset = at - np.array([float(csg.position[i, 0]) for i in range(3)])
        radial = offset - axis * float(offset @ axis)
        distance = float(np.linalg.norm(radial)) - float(csg.radius)
        if distance > tolerance + _IN_PLANE_EPS:
            return []
        caps = _extrusion_caps(unit_vector(csg.axis_direction), csg.position, csg.start_distance, csg.end_distance)
        angles = _plane_angles(caps, at, direction, basis, tolerance)
        if angles and distance >= -(tolerance + _IN_PLANE_EPS):
            across = radial - direction * float(radial @ direction)
            if float(np.linalg.norm(across)) > 1e-12:
                angles = _angles_intersection(angles, _half_turn(across, basis))
        return angles
    exact = isinstance(csg, (HalfSpace, RectangularPrism, ConvexPolygonExtrusion))
    if isinstance(csg, ConvexPolygonSimpleLoft):
        exact = _loft_sides_are_planar(csg)
    if not exact:
        return None
    bounds = solid_bounds(csg)
    if bounds.is_unknown:
        return None
    if bounds.is_empty:
        return []
    return _plane_angles(bounds.require_faces(), at, direction, basis, tolerance)


def _tree_angles(csg, at, direction, basis, tolerance) -> Optional[AngleSpans]:
    from .cutcsg import Difference, Intersection, SolidUnion

    if isinstance(csg, SolidUnion):
        out: AngleSpans = []
        for child in csg.children:
            angles = _tree_angles(child, at, direction, basis, tolerance)
            if angles is None:
                return None
            out = _angles_union(out, angles)
        return out
    if isinstance(csg, Intersection):
        left = _tree_angles(csg.left, at, direction, basis, tolerance)
        right = _tree_angles(csg.right, at, direction, basis, tolerance) if left else []
        return None if left is None or right is None else _angles_intersection(left, right)
    if isinstance(csg, Difference):
        kept = _tree_angles(csg.base, at, direction, basis, tolerance)
        if not kept:
            return kept
        for solid in csg.subtract:
            removed = _tree_angles(solid, at, direction, basis, tolerance)
            if removed is None:
                return None
            kept = _angles_less(kept, removed)
        return kept
    return _primitive_angles(csg, at, direction, basis, tolerance)


def _directions_at(csg, line: Line, station: float, tolerance: float):
    """Return _FLAT if the solid lies in one flat face at `station` along `line`, else its angles (None if unsure)."""
    import numpy as np

    direction = np.array([float(v) for v in unit_vector(line.direction)])
    at = np.array([float(line.point[i, 0]) for i in range(3)]) + direction * station
    seed = np.eye(3)[int(np.argmin(np.abs(direction)))]
    u = np.cross(direction, seed)
    u /= np.linalg.norm(u)
    basis = (u, np.cross(direction, u))
    angles = _tree_angles(csg, at, direction, basis, tolerance)
    if angles is None:
        return None
    if len(angles) == 1 and abs(angles[0][1] - angles[0][0] - math.pi) < 1e-4:
        return _FLAT
    if len(angles) == 2 and angles[0][0] < _ANGLE_EPS and angles[1][1] > _TAU - _ANGLE_EPS \
            and abs(angles[0][1] + _TAU - angles[1][0] - math.pi) < 1e-4:
        return _FLAT  # one half turn, across angle 0 where the spans wrap
    return angles


def _stations(csg, line: Line, seed: Span) -> List[float]:
    """Return where along the line, within `seed`, it crosses a primitive's plane or a cylinder's barrel."""
    import numpy as np
    from .cutcsg import Cylinder, csg_children

    direction = np.array([float(v) for v in unit_vector(line.direction)])
    origin = np.array([float(line.point[i, 0]) for i in range(3)])
    found: List[float] = []

    def planes(faces) -> None:
        for normal, point in faces:
            n = np.array([float(normal[i, 0]) for i in range(3)])
            along = float(n @ direction)
            if abs(along) > 1e-12:
                found.append(float(n @ (np.array([float(point[i, 0]) for i in range(3)]) - origin)) / along)

    def walk(node) -> None:
        children = csg_children(node)
        if children:
            for child in children:
                walk(child)
            return
        if isinstance(node, Cylinder):
            axis = np.array([float(v) for v in unit_vector(node.axis_direction)])
            start = origin - np.array([float(node.position[i, 0]) for i in range(3)])
            across, offset = direction - axis * float(direction @ axis), start - axis * float(start @ axis)
            a, b = float(across @ across), 2 * float(offset @ across)
            c = float(offset @ offset) - float(node.radius) ** 2
            if a > 1e-18 and b * b - 4 * a * c > 0:
                root = (b * b - 4 * a * c) ** 0.5
                found.extend([(-b - root) / (2 * a), (-b + root) / (2 * a)])
            planes(_extrusion_caps(unit_vector(node.axis_direction), node.position, node.start_distance,
                                   node.end_distance))
            return
        bounds = solid_bounds(node)
        if not bounds.is_unknown and not bounds.is_empty:
            planes(bounds.require_faces())

    walk(csg)
    return sorted(station for station in found if seed[0] < station < seed[1])


def _crease_spans(line: Line, csg, spans: Sequence[Span], seed: Span, tolerance: float) -> List[Span]:
    """Return `spans` less where the surface is one flat face across the line."""
    stations = _stations(csg, line, seed)
    kept: List[Span] = []
    for low, high in spans:
        cuts = [low] + [station for station in stations if low < station < high] + [high]
        for start, end in zip(cuts, cuts[1:]):
            if end - start > 0 and _directions_at(csg, line, (start + end) / 2, tolerance) is not _FLAT:
                kept.append((start, end))
    return _merged_spans(kept)


def _seed_span(line: Line, seed_reach: Numeric, near: Optional[V3]) -> Span:
    """Return the starting parameter interval: `seed_reach` either side of `near`."""
    direction = unit_vector(line.direction)
    reach = float(seed_reach)
    centre = (0.0 if near is None
              else float(((near - line.point).T * direction)[0, 0]))
    return (centre - reach, centre + reach)


def _segments(line: Line, spans: Sequence[Span]) -> List[LineSegment]:
    """Return parameter spans as LineSegments."""
    direction = unit_vector(line.direction)
    origin = line.point
    return [
        LineSegment(
            line=line,
            start=origin + direction * scalar(low),
            end=origin + direction * scalar(high),
        )
        for low, high in spans
    ]


def _closed_spans(
    line: Line, csg, seed: Span, tolerance: float,
) -> Optional[List[Span]]:
    """Return where a line lies on a solid, surface included, or None.

    A line in a cut's wall is ambiguous: an arris the cut made, or one it planed away. Computes both
    readings and checks each disputed stretch's midpoint with is_point_on_boundary.
    """
    direction = unit_vector(line.direction)
    origin = line.point

    permissive = _spans_on_csg(csg, line, seed, tolerance, flush_removes=False)
    if permissive is None:
        return None
    strict = _spans_on_csg(csg, line, seed, tolerance, flush_removes=True)
    if strict is None:
        return None

    doubtful = _subtracted_spans(permissive, strict)
    gone = []
    for low, high in doubtful:
        middle = origin + direction * scalar((low + high) / 2.0)
        if not csg.is_point_on_boundary(middle, eps=scalar(_VERIFY_EPS)):
            gone.append((low, high))
    return _subtracted_spans(permissive, gone)


def _interior_spans(
    line: Line, csg, seed: Span, tolerance: float,
) -> Optional[List[Span]]:
    """Return where a line is strictly inside a solid: `_spans_on_csg` with `removing` inverted."""
    return _spans_on_csg(csg, line, seed, tolerance, removing=True)
