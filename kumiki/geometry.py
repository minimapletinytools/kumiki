"""
Unbounded geometric primitives -- points, lines, planes -- shared by the CSG
layer and the measuring layer.

These live here rather than in measuring.py so that cutcsg.py can use them too:
measuring.py imports timber.py which imports cutcsg.py, so anything cutcsg needs
has to sit below that chain. They depend on nothing but rule.py.

They are deliberately UNBOUNDED. A Line is an infinite line, not a segment; a
Plane is an infinite plane, not a face. That is what measurement wants -- "the
distance between two parallel edges" means the distance between the infinite
lines they lie on -- and bounds, where they matter, are carried separately (see
cutcsg.CSGFeatureExtent).

measuring.py re-exports all of these, so `from kumiki.measuring import Plane`
keeps working.
"""

from dataclasses import dataclass

from typing import Optional

from .rule import (
    Direction3D,
    Transform,
    V3,
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
