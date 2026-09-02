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

Some primitives are described by a convex hull of their points rather than
exactly -- see bounding_half_spaces -- and the cylinder by a hexagon. Those
approximations are deliberately made *inwards*, so a region comes out no larger
than the truth: an anchor placed inside a region that is too small is still on
the feature, where one placed inside a region that is too large may not be.

What this does not do yet: subtracted solids, which remove convex holes from the
region. Clipping by what encloses is exact; ignoring what has been taken away is
the other approximation, and it shows up only as an anchor placed where a later
cut has since removed the material.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .geometry import Line, Plane
from .rule import V3, Matrix, Numeric, scalar


@dataclass(frozen=True)
class PlaneFrame:
    """Two axes on a plane, for working in it as if it were flat."""

    origin: V3
    u: V3
    v: V3

    def to_2d(self, point: V3) -> Tuple[float, float]:
        offset = point - self.origin
        return (
            float((offset.T * self.u)[0, 0]),
            float((offset.T * self.v)[0, 0]),
        )

    def to_3d(self, x: float, y: float) -> V3:
        return self.origin + self.u * scalar(x) + self.v * scalar(y)


@dataclass(frozen=True)
class FeatureRegion:
    """A convex region of a plane: where a feature is, once cropped.

    `boundary` is in order around the region, and lies on `plane`. An empty
    boundary means the feature has nothing left after cropping -- it is not on
    the finished piece at all, which is a thing worth knowing rather than an
    error.
    """

    plane: Plane
    boundary: Tuple[V3, ...]

    @property
    def is_empty(self) -> bool:
        return len(self.boundary) < 3

    def centroid(self) -> Optional[V3]:
        """A point in the middle of the region, for a dimension to attach to."""
        if not self.boundary:
            return None
        total = self.boundary[0]
        for point in self.boundary[1:]:
            total = total + point
        return total / scalar(len(self.boundary))

    def extent_along(self, direction: V3) -> Optional[Tuple[float, float]]:
        """How far the region reaches along any direction, as (min, max).

        This is what makes orienting to a viewport unnecessary: ask along the
        viewport's own axes and the answer is the bounds in that view.
        """
        if not self.boundary:
            return None
        reach = [float((point.T * direction)[0, 0]) for point in self.boundary]
        return (min(reach), max(reach))


@dataclass(frozen=True)
class FeatureSegment:
    """A stretch of a line: where an edge is, once cropped.

    The counterpart to FeatureRegion for a feature that locates to a line. An
    empty `ends` means nothing survived -- the edge is not on the finished piece
    -- which is worth knowing rather than an error.
    """

    line: Line
    ends: Tuple[V3, ...]

    @property
    def is_empty(self) -> bool:
        return len(self.ends) < 2

    def midpoint(self) -> Optional[V3]:
        """The middle of the edge, for a dimension to attach to."""
        if self.is_empty:
            return None
        return (self.ends[0] + self.ends[1]) / scalar(2)

    def extent_along(self, direction: V3) -> Optional[Tuple[float, float]]:
        """How far the segment reaches along any direction, as (min, max)."""
        if self.is_empty:
            return None
        reach = [float((point.T * direction)[0, 0]) for point in self.ends]
        return (min(reach), max(reach))


def _unit(vector: V3) -> V3:
    length = float((vector.T * vector)[0, 0]) ** 0.5
    return vector / scalar(length) if length > 0 else vector


def _perpendicular_axes(direction: V3) -> Tuple[V3, V3]:
    """Two unit axes at right angles to a direction, and to each other.

    Which two does not matter, so long as neither is parallel to the direction:
    the world axis it leans on least is the safe one to start from.
    """
    forward = _unit(direction)
    components = [abs(float(forward[i, 0])) for i in range(3)]
    least = components.index(min(components))
    seed = Matrix([scalar(1) if i == least else scalar(0) for i in range(3)])
    u = _unit(seed - forward * (seed.T * forward)[0, 0])
    v = Matrix([
        forward[1, 0] * u[2, 0] - forward[2, 0] * u[1, 0],
        forward[2, 0] * u[0, 0] - forward[0, 0] * u[2, 0],
        forward[0, 0] * u[1, 0] - forward[1, 0] * u[0, 0],
    ])
    return u, _unit(v)


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


def frame_for_plane(plane: Plane, near: Optional[V3] = None) -> PlaneFrame:
    """Two perpendicular axes lying in a plane, with an origin near something.

    The first axis is whichever world axis the normal leans on least, made
    perpendicular -- any choice does, so long as it is never parallel to the
    normal.

    The origin matters more than it looks. A plane's stored point is any point
    on it, and for a face declared on a cutter extended far past the timber it
    is far past the timber too. Working from there and clipping to the timber
    leaves nothing, having started nowhere near it. So the caller says what the
    region is expected to be near -- the timber -- and that is projected onto
    the plane to start from.
    """
    normal = _unit(plane.normal)
    u, v = _perpendicular_axes(normal)
    origin = plane.point
    if near is not None:
        # Drop `near` onto the plane along the normal.
        away = (near - plane.point).T * normal
        origin = near - normal * away[0, 0]
    return PlaneFrame(origin=origin, u=u, v=v)


# A solid, as the half spaces that bound it: each an outward normal and a point
# on its plane, so a point is inside when (p - point) . normal <= 0 for all.
BoundingHalfSpaces = List[Tuple[V3, V3]]


def bounding_half_spaces(csg) -> Optional[BoundingHalfSpaces]:
    """The planes that bound a convex primitive, or None if it is not one.

    None rather than an empty list, because "this solid does not bound the
    region" and "this solid is not one I can describe" are different answers and
    only the second should make a caller give up.
    """
    from .cutcsg import ConvexPolygonExtrusion, Cylinder, HalfSpace, RectangularPrism
    from .pathcsg import PathExtrusion

    if isinstance(csg, HalfSpace):
        # Inside is p . normal >= offset, so the outward normal is the other way.
        normal = _unit(csg.normal)
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
        # A hexagon inscribed in the circle: its faces sit at the apothem, so
        # the hexagon is contained by the cylinder rather than containing it.
        # Erring inwards keeps a region no larger than the truth, and an anchor
        # inside a region that is slightly too small is still on the feature.
        axis = _unit(csg.axis_direction)
        across, up = _perpendicular_axes(axis)
        apothem = csg.radius * scalar(math.cos(math.pi / 6))
        faces = []
        for step in range(6):
            angle = math.pi * step / 3
            normal = across * scalar(math.cos(angle)) + up * scalar(math.sin(angle))
            faces.append((normal, csg.position + normal * apothem))
        return faces + _extrusion_caps(axis, csg.position,
                                       csg.start_distance, csg.end_distance)

    if isinstance(csg, ConvexPolygonExtrusion):
        return _extruded_hull_half_spaces(
            [(float(x), float(y)) for x, y in csg.points],
            csg.transform, csg.start_distance, csg.end_distance,
        )

    if isinstance(csg, PathExtrusion):
        # The hull of the points the path is built from. A segment that curves
        # outwards -- an arc bulging away from the chord between its ends --
        # lies outside that hull, so this omits it. Inwards again, and fine:
        # the region comes out no larger than the truth.
        points = [seg.start() for seg in csg.path.segments]
        return _extruded_hull_half_spaces(
            [(float(point[0, 0]), float(point[1, 0])) for point in points],
            csg.transform, csg.start_distance, csg.end_distance,
        )

    return None


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


def region_in_plane(
    plane: Plane,
    bounding: Sequence,
    seed_reach: Numeric,
    near: Optional[V3] = None,
) -> Optional[FeatureRegion]:
    """The part of a plane left after clipping by a set of convex solids.

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
                    return FeatureRegion(plane=plane, boundary=())
                continue
            corners = _clip_polygon(corners, a, b, c)
            if not corners:
                return FeatureRegion(plane=plane, boundary=())

    return FeatureRegion(
        plane=plane,
        boundary=tuple(frame.to_3d(x, y) for x, y in corners),
    )


def segment_on_line(
    line: Line,
    bounding: Sequence,
    seed_reach: Numeric,
    near: Optional[V3] = None,
) -> Optional[FeatureSegment]:
    """The part of a line left after clipping by a set of convex solids.

    The one-dimensional twin of region_in_plane, and the same clipping: each
    half space becomes a bound on the parameter along the line rather than a cut
    across a polygon.

    `near` is where the edge is expected to be. As with a plane, a line's own
    point may be nowhere near the timber -- it is wherever the primitive that
    declared it put it -- so the starting interval is centred on `near` instead.

    None when any solid cannot be described as half spaces, since a segment
    clipped by only some of them would be silently too long.

    Not crop_line_to_csg, which samples and bisects against one solid around the
    line's own origin. That one handles shapes this cannot, and is right for
    drawing a bore axis; for an anchor it would search in the wrong place when
    the origin is far off, and step straight over an edge shorter than its
    sample spacing.
    """
    direction = _unit(line.direction)
    origin = line.point
    reach = float(seed_reach)
    centre = 0.0 if near is None else float(((near - origin).T * direction)[0, 0])
    low, high = centre - reach, centre + reach

    for solid in bounding:
        faces = bounding_half_spaces(solid)
        if faces is None:
            return None
        for normal, point in faces:
            # Keep where dot(normal, p - point) <= 0, with p = origin + s * direction.
            along = float((normal.T * direction)[0, 0])
            offset = float((normal.T * (origin - point))[0, 0])
            if abs(along) < 1e-12:
                # Parallel to the line: it either keeps all of it or none.
                if offset > 0:
                    return FeatureSegment(line=line, ends=())
                continue
            bound = -offset / along
            if along > 0:
                high = min(high, bound)
            else:
                low = max(low, bound)
            if low > high:
                return FeatureSegment(line=line, ends=())

    return FeatureSegment(
        line=line,
        ends=(origin + direction * scalar(low), origin + direction * scalar(high)),
    )
