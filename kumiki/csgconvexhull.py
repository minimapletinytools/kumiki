"""Where a feature actually is: convex hulls of the CSG, sectioned.

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

Some primitives are described approximately -- see bounding_half_spaces -- the
cylinder by a hexagon, a loft by planes pushed out to its corners. Those
approximations are deliberately made *outwards*, so a region always CONTAINS
the truth.

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


def bounding_half_spaces(csg) -> Optional[BoundingHalfSpaces]:
    """The planes that bound a convex primitive, or None if it is not one.

    None rather than an empty list, because "this solid does not bound the
    region" and "this solid is not one I can describe" are different answers and
    only the second should make a caller give up.
    """
    from .cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, Cylinder,
                         HalfSpace, RectangularPrism)
    from .pathcsg import PathExtrusion

    if isinstance(csg, HalfSpace):
        # Inside is p . normal >= offset, so the outward normal is the other way.
        normal = unit_vector(csg.normal)
        return [(-normal, normal * csg.offset)]

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
        return faces

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
        return faces + _extrusion_caps(axis, csg.position,
                                       csg.start_distance, csg.end_distance)

    if isinstance(csg, ConvexPolygonExtrusion):
        return _extruded_hull_half_spaces(
            [(float(x), float(y)) for x, y in csg.points],
            csg.transform, csg.start_distance, csg.end_distance,
        )

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
        points = [seg.start() for seg in csg.path.segments]
        return _extruded_hull_half_spaces(
            [(float(point[0, 0]), float(point[1, 0])) for point in points],
            csg.transform, csg.start_distance, csg.end_distance,
        )

    if isinstance(csg, ConvexPolygonSimpleLoft):
        return _loft_half_spaces(csg)

    return None


def _loft_half_spaces(csg) -> Optional[BoundingHalfSpaces]:
    """The planes bounding a loft between two convex profiles.

    A loft's side faces are ruled surfaces, and planar only when the taper is a
    pure per-axis scale -- which is the case the primitive is actually for, a
    taper or a relief pocket. There, each side quad lies in one plane and those
    planes bound the solid exactly.

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
    region clipped by only some of them would be silently too large.
    """
    frame = frame_for_plane(plane, near)
    reach = float(seed_reach)
    corners = [(-reach, -reach), (reach, -reach), (reach, reach), (-reach, reach)]

    for solid in bounding:
        faces = bounding_half_spaces(solid)
        if faces is None:
            # Clipped by only the solids it understood, the region would be
            # silently larger than the truth -- which is worse than no answer,
            # because nothing downstream can tell.
            return None

        for normal, point in faces:
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

    `removing` says this solid is being taken away rather than added, which
    changes only the degenerate case: a line lying exactly IN one of the faces.
    Added, such a line is on the solid and is kept. Removed, it lies in the wall
    of the void rather than inside it, so it survives the cut -- which is what
    an arris shared with a mortise wall is. Getting this backwards eats every
    edge a cut passes through the plane of.
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
    """
    from .cutcsg import Difference, EmptyCSG, Intersection, SolidUnion

    if isinstance(csg, EmptyCSG):
        # Bounds nothing and contains nothing -- an answer, not a failure.
        return []

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

    faces = bounding_half_spaces(csg)
    if faces is None:
        return None
    return _spans_within_primitive(faces, line, seed, tolerance, removing)


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
