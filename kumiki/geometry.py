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
stretch of a Line, a SegmentedLine all the stretches of one that survived
cropping, and a PlanarRegion the part of a Plane. They are what you get back
from cropping an unbounded primitive to a solid (see kumiki.csgconvexhull), and
they are plain geometry -- none of them knows what a feature or a timber is.

measuring.py re-exports all of these, so `from kumiki.measuring import Plane`
keeps working.
"""

from dataclasses import dataclass

from typing import List, Optional, Sequence, Tuple

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
    """A vector scaled to length one, or left alone if it has no length."""
    length = float((vector.T * vector)[0, 0]) ** 0.5
    return vector / scalar(length) if length > 0 else vector


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


@dataclass(frozen=True)
class SegmentedLine:
    """A line, and the parts of it that are actually there.

    What you get back from cropping an infinite line to a solid. Several parts,
    because a solid can be non-convex: a cut through the middle of an edge
    leaves a piece either side of it, and one segment spanning both would run
    straight through the hole.

    No segments means nothing survived -- the line is not on the solid at all --
    which is worth knowing rather than an error. That is why emptiness lives
    here and not on LineSegment: a segment with no ends was never a thing, only
    a way of saying "none of them".
    """

    line: Line
    segments: Tuple[LineSegment, ...] = ()

    @property
    def is_empty(self) -> bool:
        return len(self.segments) == 0

    def __len__(self) -> int:
        return len(self.segments)

    def __iter__(self):
        return iter(self.segments)

    def longest(self) -> Optional[LineSegment]:
        """The biggest piece, for anything that has to pick just one."""
        if self.is_empty:
            return None
        return max(self.segments, key=lambda segment: segment.length())

    def total_length(self) -> float:
        return sum(segment.length() for segment in self.segments)

    def extent_along(self, direction: V3) -> Optional[Tuple[float, float]]:
        """How far the whole thing reaches, as (min, max). Gaps included."""
        if self.is_empty:
            return None
        reach = [
            value for segment in self.segments
            for value in segment.extent_along(direction)
        ]
        return (min(reach), max(reach))


@dataclass(frozen=True)
class PlanarRegion:
    """The part of a Plane that is actually there: a convex area lying in it.

    `boundary` is in order around the region, and lies on `plane`. An empty
    boundary means nothing survived cropping -- the plane meets the solid
    nowhere -- which is a thing worth knowing rather than an error.

    Convex because what produces one is half-space clipping, and a section of a
    convex solid is convex.
    """

    plane: Plane
    boundary: Tuple[V3, ...]

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
