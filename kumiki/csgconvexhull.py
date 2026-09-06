# TODO rename this file, not just convex hull testing

"""Where a feature actually is: the CSG, sectioned by a line or a plane.

A feature's declared extent is the extent of the primitive it was declared on,
and primitives are deliberately not the finished piece: a half space is unbounded
by definition, and a cutter is extended past the timber on purpose so the cut
comes out clean. Asking such a primitive where its face is gives an answer that
is nowhere near the timber.

What a dimension wants instead is the part of the feature that survives cropping
by what encloses it: a region in its own plane for a face, a segment along its
own line for an edge. Both are computed here, and both are tractable for one
reason: every primitive kumiki has is convex, so a section of one is convex and
clipping one against another is half-space intersection rather than general
boolean work.

Deliberately not oriented to any viewport. Bounds along any axes -- a viewport's
included -- fall out of projecting the polygon's corners, so a polygon answers
the question for every viewport at once, where a baked-in orientation answers it
for one.

Some primitives are described approximately -- see solid_bounds -- a loft by
planes pushed out to its corners, a path extrusion by the hull of the points
its segments start at. Those approximations are deliberately made *outwards*,
so a region always CONTAINS the truth.

A line does better than that where a shape has been solved for outright rather
than bounded: a cylinder is a quadratic along a line, and the answer is the
chord that is really there rather than the hexagon's. The rest still go through
the bound, which is why solving one more shape can only tighten the answer and
never invalidate anything built on it.

One direction, consistently, is the point. Subtractions are not accounted for
either (see below), which already makes a region too large, so erring inwards
on primitives would leave a region that is neither a subset nor a superset of
the truth -- no guarantee at all. Erring outwards everywhere keeps one:
whatever the region says is not there, really is not there. What it costs is
that a point inside a region is not certainly on the feature, so an anchor on a
curved primitive can sit slightly off it.

The two dimensions differ in how far they get. A LINE is done properly: clipping
one by a convex solid gives an interval, and intervals union, intersect and
subtract exactly, so crop_line_to_segments_on_csg walks the whole tree and
returns as many pieces as the cuts leave. A PLANE is not: subtracting in the
plane means polygon booleans, and a result that can have holes, so
approximately_crop_plane_to_area_on_csg still only intersects the solids that
ENCLOSE the region and counts anything subtracted as still present. Its name
says so. It shows up as an anchor placed where a later cut has since removed the
material.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from .geometry import (
    Line,
    Plane,
    ConvexPlanarRegion,
    LineSegment,
    frame_for_plane,
    perpendicular_axes,
    unit_vector,
)
from .rule import V3, Matrix, Numeric, safe_magnitude, scalar


def convex_hull_2d(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """The convex hull of some points, counter-clockwise.

    Monotone chain. Used where a shape is described by points rather than by
    planes, so that its bounding planes can be derived from the hull of them.
    """
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
    """Which of the three answers solid_bounds gave."""

    HALF_SPACES = 0
    EMPTY = 1
    UNKNOWN = 2


@dataclass(frozen=True)
class SolidBounds:
    """What can be said about a solid in half spaces. Three answers, not two.

    Conflating any two of them has already cost something, so they are tagged
    rather than encoded:

      HALF_SPACES  the solid is the intersection of `faces`. An EMPTY list of
                   them would mean no bounds at all, which is EVERYTHING.
      EMPTY        describable, and contains nothing. The opposite of the line
                   above, which is exactly why it cannot be said in faces.
      UNKNOWN      not a solid this can describe. A caller must give up rather
                   than carry on with a partial answer, which would be wrong in
                   a direction nothing downstream can see.

    `faces` is None unless the answer is HALF_SPACES, so a caller that forgets
    to look at `kind` fails loudly instead of reading an empty list as
    "unbounded" and quietly returning too much.
    """

    kind: BoundsKind
    faces: Optional[BoundingHalfSpaces] = None

    @staticmethod
    def of(faces: BoundingHalfSpaces) -> 'SolidBounds':
        return SolidBounds(kind=BoundsKind.HALF_SPACES, faces=faces)

    @property
    def is_empty(self) -> bool:
        return self.kind is BoundsKind.EMPTY

    @property
    def is_unknown(self) -> bool:
        return self.kind is BoundsKind.UNKNOWN


EMPTY_BOUNDS = SolidBounds(kind=BoundsKind.EMPTY)
UNKNOWN_BOUNDS = SolidBounds(kind=BoundsKind.UNKNOWN)


def solid_bounds(csg) -> SolidBounds:
    """How a solid is bounded: half spaces, nothing at all, or no idea.

    See SolidBounds for what the three answers mean and why there are three.
    """
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
        # A hexagon circumscribing the circle: its faces are tangent to it, so
        # the hexagon contains the cylinder. Outwards, per the rule at the top
        # of this file -- a region that contains the truth is one that can be
        # trusted to say a feature is NOT somewhere.
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
        # The hull of the points the path is built from.
        #
        # KNOWN BUG: a segment that curves outwards -- an arc bulging away from
        # the chord between its ends -- lies outside this hull, so the bound is
        # too small. That is the wrong direction for this file, which errs
        # outwards everywhere else. Fixing it means bounding the arc rather
        # than its endpoints. Left for later; it only bites on a curved path.
        #
        # Which way it is wrong now depends on what the solid is doing. Added,
        # too small crops a feature shorter than it really is. SUBTRACTED, too
        # small removes less than it should, which is the safe direction -- so
        # a curved cutter is the milder half of this bug and a curved body the
        # sharper one.
        #
        # For analytic purposes, treat a path extrusion as if it was created
        # from all straight line extrusions. Proper support for curves is
        # unlikely to be added anytime soon.
        points = [seg.start() for seg in csg.path.segments]
        return _bounds_or_unknown(_extruded_hull_half_spaces(
            [(float(point[0, 0]), float(point[1, 0])) for point in points],
            csg.transform, csg.start_distance, csg.end_distance,
        ))

    if isinstance(csg, ConvexPolygonSimpleLoft):
        return _bounds_or_unknown(_loft_half_spaces(csg))

    return UNKNOWN_BOUNDS


def _bounds_or_unknown(faces: Optional[BoundingHalfSpaces]) -> SolidBounds:
    """For the helpers that still answer None when they cannot describe a shape."""
    return UNKNOWN_BOUNDS if faces is None else SolidBounds.of(faces)


def _loft_half_spaces(csg) -> Optional[BoundingHalfSpaces]:
    """The planes bounding a loft between two convex profiles.

    A loft's side faces are ruled surfaces, and planar only when each pair of
    matching edges happens to come out parallel. A pure per-axis scale does
    that for a profile whose edges RUN ALONG the axes being scaled -- a
    rectangle, which is the case the primitive is actually for -- and a uniform
    scale does it for any profile. Scale a hexagon per axis and its sides bend.
    _loft_sides_are_planar tests the quads rather than trusting the taper,
    because that is the property, and the two part company more easily than
    they look like they should.

    Twist the correspondence and a side stops being planar. Each plane is then
    pushed out to the furthest corner, which bounds the corners' hull -- larger
    than the loft, and containing it. The primitive already calls a twisted loft
    undefined behaviour, so a loose bound there is the honest answer.
    """
    if csg.start_distance is None or csg.end_distance is None:
        return None

    matrix = csg.transform.orientation.matrix
    across = Matrix([matrix[0, 0], matrix[1, 0], matrix[2, 0]])
    up = Matrix([matrix[0, 1], matrix[1, 1], matrix[2, 1]])
    axis = Matrix([matrix[0, 2], matrix[1, 2], matrix[2, 2]])
    origin = csg.transform.position

    def lift(point, distance) -> V3:
        return (origin + axis * distance
                + across * scalar(float(point[0]))
                + up * scalar(float(point[1])))

    bottom = [lift(point, csg.start_distance) for point in csg.bottom_points]
    top = [lift(point, csg.end_distance) for point in csg.top_points]
    if len(bottom) < 3 or len(bottom) != len(top):
        return None

    corners = bottom + top
    middle = corners[0]
    for corner in corners[1:]:
        middle = middle + corner
    middle = middle / scalar(len(corners))

    faces: BoundingHalfSpaces = _extrusion_caps(
        axis, origin, csg.start_distance, csg.end_distance)

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
        # Pushed out to whichever corner reaches furthest along the normal. For
        # a pure taper every side is planar and nothing moves, so the bound is
        # exact. Twist the correspondence and the side becomes a ruled surface
        # with no plane of its own -- this then bounds the corners' hull, which
        # contains the loft. Loose rather than wrong, which is the direction
        # this file errs in.
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
    """The two ends of an extrusion, skipping any that runs to infinity."""
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
    """The planes bounding a shape extruded from a cross-section of points.

    The hull of the points rather than the points in order, so a cross-section
    that is not convex, or has a point inside its own outline, still gives a
    convex solid to clip against.
    """
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


def _clip_polygon(corners: List[Tuple[float, float]], a: float, b: float, c: float
                  ) -> List[Tuple[float, float]]:
    """Keep the part of a convex polygon where a*x + b*y <= c.

    Sutherland-Hodgman, which is exact and stays convex because the polygon and
    the half plane both are.
    """
    if not corners:
        return corners
    kept: List[Tuple[float, float]] = []
    for index, current in enumerate(corners):
        previous = corners[index - 1]
        current_in = a * current[0] + b * current[1] <= c
        previous_in = a * previous[0] + b * previous[1] <= c
        if current_in != previous_in:
            denominator = (a * (current[0] - previous[0]) + b * (current[1] - previous[1]))
            if denominator != 0:
                t = (c - a * previous[0] - b * previous[1]) / denominator
                kept.append((
                    previous[0] + t * (current[0] - previous[0]),
                    previous[1] + t * (current[1] - previous[1]),
                ))
        if current_in:
            kept.append(current)
    return kept


def approximately_crop_plane_to_area_on_csg(
    plane: Plane,
    bounding: Sequence,

    # TODO this parameter is questionable, just use NaN for bounds?
    seed_reach: Numeric,

    near: Optional[V3] = None,
) -> Optional[ConvexPlanarRegion]:
    """The part of a plane left after clipping by a set of convex solids.

    APPROXIMATELY, and the name says so because the difference matters. This
    takes the solids that ENCLOSE the region and intersects them; it does not
    walk the tree, so anything subtracted is still counted as present. A face
    half removed by a housing comes back whole, and its centroid can sit over
    material that is no longer there.

    Its one-dimensional counterpart, crop_line_to_segments_on_csg, is exact:
    clipping a line gives an interval, and intervals subtract cleanly, so it
    walks the whole tree. Doing the same here means polygon booleans in the
    plane, and a result that can have holes and several pieces -- worth doing,
    not yet done.

    Erring outwards is what keeps this useful meanwhile: the region always
    CONTAINS the truth, so whatever it says is not there really is not there.

    `near` is where the region is expected to be -- the timber, usually -- and
    is what the work starts from, since a plane's own point may be nowhere near
    it. `seed_reach` is how far the starting square extends from there: it
    stands in for "everything", and only has to be bigger than the solids doing
    the clipping. Anything still touching its edge afterwards was never bounded
    in that direction.

    None when any of the solids cannot be described as half spaces, since a
    region clipped by only some of them would be silently too large. An empty
    solid is not one of those: it contains nothing, so it crops everything away
    and the region comes back empty -- the same answer the line crop gives.
    """
    frame = frame_for_plane(plane, near)
    reach = float(seed_reach)
    corners = [(-reach, -reach), (reach, -reach), (reach, reach), (-reach, reach)]

    for solid in bounding:
        bounds = solid_bounds(solid)
        if bounds.is_unknown:
            # Clipped by only the solids it understood, the region would be
            # silently larger than the truth -- which is worse than no answer,
            # because nothing downstream can tell.
            return None
        if bounds.is_empty:
            # Nothing is inside it, so nothing survives being clipped by it.
            return ConvexPlanarRegion(plane=plane, boundary=())

        for normal, point in bounds.faces:
            # The half space, written in the plane's own two axes.
            a = float((normal.T * frame.u)[0, 0])
            b = float((normal.T * frame.v)[0, 0])
            offset = point - frame.origin
            c = float((normal.T * offset)[0, 0])
            if abs(a) < 1e-12 and abs(b) < 1e-12:
                # Parallel to the plane: it either keeps all of it or none.
                if c < 0:
                    return ConvexPlanarRegion(plane=plane, boundary=())
                continue
            corners = _clip_polygon(corners, a, b, c)
            if not corners:
                return ConvexPlanarRegion(plane=plane, boundary=())

    return ConvexPlanarRegion(
        plane=plane,
        boundary=tuple(frame.to_3d(x, y) for x, y in corners),
    )


# A stretch of the line, as the two parameter values bounding it.
Span = Tuple[float, float]


def _spans_within_primitive(
    faces: BoundingHalfSpaces,
    line: Line,
    seed: Span,
    tolerance: float,
    removing: bool = False,
) -> List[Span]:
    """Clip `seed` by one convex solid's half spaces. One span, or none.

    A LINE ON A BOUNDARY IS ALWAYS KEPT, whichever role the solid has. That is
    the rule; `removing` is how it is enforced, and it needs the opposite
    comparison to reach the same answer. Added, "on the face" means on the
    solid, so only a line strictly outside is dropped. Removed, "on the wall"
    means on the surface of the void rather than inside it, so a line merely
    touching it must not be taken away -- which is what an arris shared with a
    mortise wall is. Getting this backwards eats every edge a cut passes
    through the plane of.
    """
    direction = unit_vector(line.direction)
    origin = line.point
    low, high = seed
    for normal, point in faces:
        # Keep where dot(normal, p - point) <= 0, with p = origin + s * direction.
        along = float((normal.T * direction)[0, 0])
        offset = float((normal.T * (origin - point))[0, 0])
        if abs(along) < 1e-12:
            # Parallel to the line: it either keeps all of it or none.
            if offset >= tolerance if removing else offset > tolerance:
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
    """Overlapping and touching spans joined, in order along the line."""
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
    """The stretches covered by both sets."""
    out: List[Span] = []
    for a_low, a_high in left:
        for b_low, b_high in right:
            low, high = max(a_low, b_low), min(a_high, b_high)
            if high > low:
                out.append((low, high))
    return _merged_spans(out)


def _subtracted_spans(keep: Sequence[Span], remove: Sequence[Span]) -> List[Span]:
    """`keep` with `remove` taken out of it. This is what splits an edge in two."""
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
    """Where a line runs inside a cylinder, solved rather than approximated.

    The barrel is a quadratic: the distance from the axis, measured in the
    plane perpendicular to it, is |w_perp + t d_perp| and the line is inside
    where that is at most the radius. The caps are two planes, so they go
    through the same linear clipping every other primitive uses -- including
    its handling of a line that runs parallel to them.

    Beats the hexagon solid_bounds describes a cylinder with, which
    circumscribes it and so reports a chord longer than the one that is there.
    """
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
        # Parallel to the axis: either wholly within the barrel or wholly
        # outside it, and a line lying exactly ON the barrel is kept when the
        # cylinder is being added and left alone when it is being removed --
        # the same rule the flat faces follow.
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
    """Whether a loft's sides are flat, so its half spaces describe it exactly.

    A side is the quad between one edge of the bottom profile and the matching
    edge of the top, and it is a ruled surface in general -- flat only when
    those two edges happen to be parallel. Which is a property of the shape, not
    a promise the primitive makes: a rectangle scaled per axis keeps its sides
    flat because its edges run along the axes being scaled, and the same scaling
    applied to any other polygon does not.

    So the quads are tested rather than the taper inferred. Relative, because
    the check is an angle: the same rounding noise is huge on a 5mm loft and
    invisible on a 5m one.
    """
    bottom, top = csg.bottom_points, csg.top_points
    if csg.start_distance is None or csg.end_distance is None:
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
            lift(bottom[index], csg.start_distance),
            lift(bottom[following], csg.start_distance),
            lift(top[following], csg.end_distance),
            lift(top[index], csg.end_distance),
        ]
        first = corners[1] - corners[0]
        second = corners[2] - corners[0]
        third = corners[3] - corners[0]
        normal = _cross(first, second)
        scale = safe_magnitude(normal) * safe_magnitude(third)
        if scale == 0.0:
            # A degenerate side -- a repeated corner, or a profile collapsed to
            # a point. Nothing to be non-planar about.
            continue
        if abs(float((third.T * normal)[0, 0])) / scale > _PLANAR_ENOUGH:
            return False
    return True


# The sine of the angle by which a quad's fourth corner may miss the plane of
# the other three and still count as flat. Dimensionless, so it means the same
# on a loft of any size.
_PLANAR_ENOUGH = 1e-9


def _exact_spans(
    csg, line: Line, seed: Span, tolerance: float, removing: bool,
) -> Optional[List[Span]]:
    """Where a line runs inside a primitive, worked out exactly.

    None when this shape cannot be solved yet, and the caller falls back to
    clipping by the half spaces that BOUND it. That fallback errs outwards, so a
    tree with some shapes solved and others bounded still keeps the guarantee
    the whole file rests on: what the answer says is not there, really is not
    there. Solving one more shape only ever tightens it.

    Most shapes are solved BY their half spaces rather than despite them. A
    prism, a half space and a convex polygon extrusion are each exactly the
    intersection of their bounding planes, so clipping by those planes is not an
    approximation of the answer, it IS the answer -- and saying so here is worth
    a line of code, because otherwise they reach the fallback and read as shapes
    nobody has got round to.

    Not solved: PathExtrusion, which needs the line intersected with the path in
    2D with arcs included, and a loft whose sides are not flat.
    """
    from .cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, Cylinder,
                         HalfSpace, RectangularPrism)

    if isinstance(csg, Cylinder):
        return _cylinder_spans(csg, line, seed, tolerance, removing)

    # Exactly its own half spaces. The extrusion counts because its points are
    # a convex polygon by the primitive's own contract, so the hull taken of
    # them is the polygon itself rather than something larger.
    exactly_bounded = isinstance(csg, (HalfSpace, RectangularPrism, ConvexPolygonExtrusion))
    if isinstance(csg, ConvexPolygonSimpleLoft):
        exactly_bounded = _loft_sides_are_planar(csg)

    if not exactly_bounded:
        return None

    bounds = solid_bounds(csg)
    if bounds.is_unknown:
        # A shape that says it is exactly its half spaces, and then has none.
        return None
    if bounds.is_empty:
        return []
    return _spans_within_primitive(bounds.faces, line, seed, tolerance, removing)


def _spans_on_csg(
    csg, line: Line, seed: Span, tolerance: float, removing: bool = False,
) -> Optional[List[Span]]:
    """Where a line runs inside a whole CSG tree, as spans of its parameter.

    None if any primitive in the tree cannot be described as half spaces --
    a partial answer would be silently wrong in an unknown direction.

    The tolerance flips sign on the way into a subtraction. Everywhere else in
    this file the approximation is made outwards, so that whatever the answer
    says is NOT there really is not there; for a solid being removed, erring
    outwards means removing LESS, not more. Widening a subtractor instead would
    eat the very edge it forms -- a mortise wall flush with the face it opens
    onto would delete the arris it shares with it. Nesting takes care of itself:
    a difference inside a subtraction flips back and is additive again.

    `removing` flips with it, and enforces the rule that a line lying ON a
    boundary is kept whichever role the solid has. See _spans_within_primitive.
    """
    from .cutcsg import Difference, Intersection, SolidUnion

    if isinstance(csg, SolidUnion):
        out: List[Span] = []
        for child in csg.children:
            spans = _spans_on_csg(child, line, seed, tolerance, removing)
            if spans is None:
                return None
            out.extend(spans)
        return _merged_spans(out)

    if isinstance(csg, Intersection):
        left = _spans_on_csg(csg.left, line, seed, tolerance, removing)
        if left is None:
            return None
        right = _spans_on_csg(csg.right, line, seed, tolerance, removing)
        if right is None:
            return None
        return _intersected_spans(left, right)

    if isinstance(csg, Difference):
        kept = _spans_on_csg(csg.base, line, seed, tolerance, removing)
        if kept is None:
            return None
        removed: List[Span] = []
        for solid in csg.subtract:
            spans = _spans_on_csg(solid, line, seed, -tolerance, not removing)
            if spans is None:
                return None
            removed.extend(spans)
        return _subtracted_spans(kept, removed)

    exact = _exact_spans(csg, line, seed, tolerance, removing)
    if exact is not None:
        return exact

    bounds = solid_bounds(csg)
    if bounds.is_unknown:
        return None
    if bounds.is_empty:
        # Contains nothing, so the line is nowhere on it. An answer, not a
        # failure -- and not the same as no bounding planes, which would mean
        # the line is everywhere on it.
        return []
    return _spans_within_primitive(bounds.faces, line, seed, tolerance, removing)


def crop_line_to_segments_on_csg(
    line: Line,
    csg,

    # TODO this parameter is questionable, just use NaN for bounds?
    seed_reach: Numeric,

    near: Optional[V3] = None,
    tolerance: float = 0.0,
) -> Optional[List[LineSegment]]:
    """The parts of a line that lie on a CSG solid.

    The one-dimensional counterpart to approximately_crop_plane_to_area_on_csg,
    and exact where that one is not: clipping a line by a convex solid gives an
    interval, and intervals can be unioned, intersected and subtracted, so the
    whole tree is walked rather than only the solids that bound it. A cut that
    removes part of an edge shortens it, and a cut through the middle of one
    splits it in two -- which is why this returns a list.

    Three different answers, so three return values:

        None   a primitive in the tree cannot be described as half spaces, so
               there is no answer -- the caller should not treat it as one.
        []     the line is not on this solid at all. Worth knowing: two planes
               can meet somewhere that is on neither face.
        [...]  one segment per surviving piece, in order along the line.

    `near` is where the edge is expected to be. A line's own point may be
    nowhere near the timber -- it is wherever the primitive that declared it put
    it -- so the starting interval is centred on `near` instead. `seed_reach` is
    how far that interval runs each way, and only has to outreach the solid.

    `tolerance` widens every bound, and a caller that found this line by a
    tolerant test must pass the same one. A derived edge is the case that
    matters: two faces count as meeting when they come within the edge
    tolerance, so the line through them can sit a fraction outside the very
    solids that formed it -- a third of a millimetre, in the case that turned
    this up. Clipped exactly, a real edge comes back empty and reads as not
    being on the piece at all.

    KNOWN OVER-REPORT, and a deliberate one. A line lying exactly IN a
    subtracted solid's face is kept, because that is what an arris shared with
    a flush cut is -- a mortise wall meeting the face it opens onto forms a real
    edge, and removing it would delete every such edge on the piece. Along one
    dimension there is no way to tell that case from a cut that grazes the line
    while eating the material behind it, so the second is kept too, and shows up
    as a short extra piece where a cut has taken a corner off. Outwards, per the
    rule at the top of this file: what the answer says is NOT there really is
    not. Telling the two apart needs the surface either side of the line, not
    just the line.
    """
    direction = unit_vector(line.direction)
    origin = line.point
    reach = float(seed_reach)
    centre = 0.0 if near is None else float(((near - origin).T * direction)[0, 0])

    spans = _spans_on_csg(csg, line, (centre - reach, centre + reach), tolerance)
    if spans is None:
        return None
    return [
        LineSegment(
            line=line,
            start=origin + direction * scalar(low),
            end=origin + direction * scalar(high),
        )
        for low, high in spans
    ]
