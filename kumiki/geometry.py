"""
Unbounded geometric primitives -- points, lines, planes -- shared by the CSG
layer and the measuring layer.

These live here rather than in measuring.py so that cutcsg.py can use them too:
measuring.py imports timber.py which imports cutcsg.py, so anything cutcsg needs
has to sit below that chain. They depend on nothing but rule.py.

The primitives are deliberately UNBOUNDED. A Line is an infinite line, not a
segment; a Plane is an infinite plane, not a face. That is what measurement
wants -- "the distance between two parallel edges" means the distance between
the infinite lines they lie on.

Their BOUNDED counterparts live here too, beside them: a LineSegment is a
stretch of a Line, a ConvexPlanarRegion an area of a Plane. They are what you
get back from cropping an unbounded primitive to a solid (see
kumiki.csgconvexhull) -- a line comes back as a list of LineSegments, since a
cut through the middle of one leaves a piece either side. Both are plain
geometry: neither knows what a feature or a timber is.

measuring.py re-exports all of these, so `from kumiki.measuring import Plane`
keeps working.
"""

from dataclasses import dataclass

from typing import Optional, Tuple

from .rule import (
    Direction3D,
    Matrix,
    Transform,
    V3,
    scalar,
    are_vectors_parallel,
    cross_product,
    safe_dot_product,
    safe_normalize_vector,
    safe_transform_vector,
    safe_zero_test_sq,
)


@dataclass(frozen=True)
class Point:
    """
    Represents a point in 3D space.
    """
    position: V3

    def __repr__(self) -> str:
        return f"Point(position={self.position})"


@dataclass(frozen=True)
class Line:
    """
    Represents an oriented, infinite line with origin in 3D space.
    """
    direction: Direction3D
    point: V3

    def __repr__(self) -> str:
        return f"Line(direction={self.direction}, point={self.point})"


@dataclass(frozen=True)
class Plane:
    """
    Represents an oriented, infinite plane with origin in 3D space.
    """
    normal: Direction3D
    point: V3

    def __repr__(self) -> str:
        return f"Plane(normal={self.normal}, point={self.point})"

    @staticmethod
    def from_transform_and_direction(transform: Transform, direction: Direction3D) -> 'Plane':
        """
        Create a plane from a transform and a direction.

        Args:
            transform: Transform defining the position and orientation
            direction: Direction in the transform's local coordinate system

        Returns:
            Plane with normal in global coordinates and point at transform position
        """
        return Plane(safe_transform_vector(transform.orientation.matrix, direction), transform.position)


@dataclass(frozen=True)
class UnsignedPlane(Plane):
    """
    Same as Plane but the sign on the normal should be ignored.
    """
    normal: Direction3D
    point: V3

    def __repr__(self) -> str:
        return f"UnsignedPlane(normal={self.normal}, point={self.point})"

    @staticmethod
    def from_transform_and_direction(transform: Transform, direction: Direction3D) -> 'UnsignedPlane':
        """
        Create an unsigned plane from a transform and a direction.

        Args:
            transform: Transform defining the position and orientation
            direction: Direction in the transform's local coordinate system

        Returns:
            UnsignedPlane with normal in global coordinates and point at transform position
        """
        return UnsignedPlane(safe_transform_vector(transform.orientation.matrix, direction), transform.position)


# TODO rename to LineOnPlane
@dataclass(frozen=True)
class HalfPlane:
    """
    Represents an oriented half-plane with origin in 3D space.
    """
    normal: Direction3D  # this is the + direction of any measurements
    point_on_line: V3
    line_direction: Direction3D  # MUST be perpendicular to the normal

    def __repr__(self) -> str:
        return f"HalfPlane(normal={self.normal}, point_on_line={self.point_on_line}, line_direction={self.line_direction})"


def unit_vector(vector: V3) -> V3:
    """A vector scaled to length one, or left alone if it has barely any.

    safe_normalize_vector, under its own name. Kept as a thin alias because
    "unit_vector" is what the geometry here is doing, and because dividing by
    anything merely above zero -- which is what this used to do -- turns the
    cross product of two nearly parallel edges into a direction made of
    rounding noise.
    """
    return safe_normalize_vector(vector)


def perpendicular_axes(direction: V3) -> Tuple[V3, V3]:
    """Two unit axes at right angles to a direction, and to each other.

    Which two does not matter, so long as neither is parallel to the direction:
    the world axis it leans on least is the safe one to start from.
    """
    forward = unit_vector(direction)
    components = [abs(float(forward[i, 0])) for i in range(3)]
    least = components.index(min(components))
    seed = Matrix([scalar(1) if i == least else scalar(0) for i in range(3)])
    u = unit_vector(seed - forward * (seed.T * forward)[0, 0])
    v = Matrix([
        forward[1, 0] * u[2, 0] - forward[2, 0] * u[1, 0],
        forward[2, 0] * u[0, 0] - forward[0, 0] * u[2, 0],
        forward[0, 0] * u[1, 0] - forward[1, 0] * u[0, 0],
    ])
    return u, unit_vector(v)


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


def frame_for_plane(plane: 'Plane', near: Optional[V3] = None) -> PlaneFrame:
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
    normal = unit_vector(plane.normal)
    u, v = perpendicular_axes(normal)
    origin = plane.point
    if near is not None:
        # Drop `near` onto the plane along the normal.
        away = (near - plane.point).T * normal
        origin = near - normal * away[0, 0]
    return PlaneFrame(origin=origin, u=u, v=v)


@dataclass(frozen=True)
class LineSegment:
    """One stretch of a Line: the bounded counterpart of it.

    Carries the line as well as the two ends, so it keeps the line's direction.
    Working that out from the ends instead would flip it whenever the ends came
    back in the other order, and for a cropped edge the parent line's
    orientation is the one that means something.
    """

    line: Line
    start: V3
    end: V3

    def midpoint(self) -> V3:
        """The middle of it, for a dimension to attach to."""
        return (self.start + self.end) / scalar(2)

    def length(self) -> float:
        return float(sum(
            (float(self.start[axis, 0]) - float(self.end[axis, 0])) ** 2
            for axis in range(3)
        )) ** 0.5

    def extent_along(self, direction: V3) -> Tuple[float, float]:
        """How far it reaches along any direction, as (min, max)."""
        reach = [float((point.T * direction)[0, 0]) for point in (self.start, self.end)]
        return (min(reach), max(reach))


# The sine of the angle below which a corner counts as straight rather than as
# turning. Dimensionless on purpose: it is an angle, so it means the same thing
# on a 5mm face and a 5m one. Generous next to double-precision rounding, which
# leaves a corner that should be exactly straight at around 1e-15.
STRAIGHT_ENOUGH = 1e-9

# How short an edge may be, as a fraction of the outline's longest, before it
# counts as no edge at all.
_DEGENERATE_EDGE = 1e-9


@dataclass(frozen=True)
class ConvexPlanarRegion:
    """An area of a Plane, bounded by a convex outline lying in it.

    `boundary` is in order around the region, and lies on `plane`. An empty
    boundary means nothing survived cropping -- the plane meets the solid
    nowhere -- which is a thing worth knowing rather than an error.

    Convex is in the name because it is a promise the readers rely on, not a
    description of how it usually turns out. centroid() averages the corners,
    which is the centre only of a convex outline; extent_along() reads the
    corners alone, which bounds the area only if nothing bulges between them.
    Hand either a concave outline and it answers confidently and wrongly, so
    the outline is checked once here instead.
    """

    plane: Plane
    boundary: Tuple[V3, ...]

    def __post_init__(self) -> None:
        corners = self.boundary
        if len(corners) < 3:
            # Nothing to be concave about: empty, a point, or an edge.
            return
        normal = unit_vector(self.plane.normal)
        edges = [corners[(i + 1) % len(corners)] - corners[i] for i in range(len(corners))]
        lengths = [float((edge.T * edge)[0, 0]) ** 0.5 for edge in edges]
        # An edge of no length has no direction, so no corner it touches turns.
        # Negligible RELATIVE to the outline rather than absolutely zero:
        # clipping a polygon routinely lands two corners a rounding error apart,
        # and dividing by that length turns the noise between them into an
        # arbitrary angle. This used to crash on real joinery.
        longest = max(lengths) if lengths else 0.0
        too_short = longest * _DEGENERATE_EDGE
        turning = 0
        for i in range(len(corners)):
            after = (i + 1) % len(corners)
            # The cross product is an AREA -- |e1||e2|sin(t) -- so comparing it
            # against one number for the whole outline asks a different question
            # at every corner. Dividing the two edge lengths back out leaves
            # sin(t) itself: the angle turned through, which is what "straight
            # on" is actually about, and which no longer depends on how long
            # this corner's edges happen to be or how long the longest one is.
            # Measured absolutely, a real reflex corner between two 14um edges
            # sits below the slack a 1m edge sets, and passes as convex.
            if lengths[i] <= too_short or lengths[after] <= too_short:
                # A repeated corner, or one the clip left a rounding error away
                # from its neighbour.
                continue
            scale = lengths[i] * lengths[after]
            turn = float(
                (cross_product(edges[i], edges[after]).T * normal)[0, 0]
            ) / scale
            if abs(turn) <= STRAIGHT_ENOUGH:
                # Straight on. Clipping makes these whenever a cut passes
                # exactly through a corner.
                continue
            direction = 1 if turn > 0 else -1
            if turning == 0:
                turning = direction
            elif direction != turning:
                raise ValueError(
                    "ConvexPlanarRegion boundary turns both ways, so it is not "
                    f"convex: corner {i} reverses. Boundary: {corners}"
                )

    @property
    def is_empty(self) -> bool:
        return len(self.boundary) < 3

    def centroid(self) -> Optional[V3]:
        """A point in the middle of it, for a dimension to attach to."""
        if not self.boundary:
            return None
        total = self.boundary[0]
        for point in self.boundary[1:]:
            total = total + point
        return total / scalar(len(self.boundary))

    def extent_along(self, direction: V3) -> Optional[Tuple[float, float]]:
        """How far it reaches along any direction, as (min, max).

        This is what makes orienting to a viewport unnecessary: ask along the
        viewport's own axes and the answer is the bounds in that view.
        """
        if not self.boundary:
            return None
        reach = [float((point.T * direction)[0, 0]) for point in self.boundary]
        return (min(reach), max(reach))


@dataclass(frozen=True)
class Space:
    """
    Represents an ORIENTED 3D space.
    """
    transform: Transform

    def __repr__(self) -> str:
        return f"Space(transform={self.transform})"


def intersect_planes(a: Optional[Plane], b: Optional[Plane]) -> Optional[Line]:
    """The infinite line where two planes meet, or None if they never do.

    None covers three cases that all mean "no line here": either plane missing
    (a caller passing through a locate() that declined), the planes parallel,
    and the planes coincident. Coincident planes are geometrically a whole
    shared plane rather than a line, so they are not an intersection this can
    describe -- that relation is worth capturing separately, since two
    coincident faces is exactly the rough-matches-perfect test, but it is not
    an edge.

    The returned direction is normalised; the returned point is the point on
    the line closest to the origin.
    """
    if a is None or b is None:
        return None

    direction = cross_product(a.normal, b.normal)
    # |n1 x n2| is |n1||n2|sin(theta), so this is zero exactly when the normals
    # are parallel. It is a SQUARED magnitude, hence safe_zero_test_sq.
    magnitude_squared = safe_dot_product(direction, direction)
    if safe_zero_test_sq(magnitude_squared):
        return None

    # Each plane is dot(normal, x) == offset; solve the pair for a point on both.
    offset_a = safe_dot_product(a.normal, a.point)
    offset_b = safe_dot_product(b.normal, b.point)
    point = (
        cross_product(b.normal, direction) * offset_a
        + cross_product(direction, a.normal) * offset_b
    ) / magnitude_squared
    return Line(direction=safe_normalize_vector(direction), point=point)


def planes_are_parallel(a: Optional[Plane], b: Optional[Plane]) -> bool:
    """Whether two planes never meet in a line (parallel, or the same plane)."""
    if a is None or b is None:
        return False
    return are_vectors_parallel(a.normal, b.normal)
