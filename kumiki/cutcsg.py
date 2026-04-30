"""
CutCSG - Constructive Solid Geometry operations for Kumiki

This module provides CSG primitives and operations for representing timber cuts
and geometry operations. All operations use SymPy symbolic math for exact computation.
"""

from sympy import Matrix, Rational, Expr, sqrt, oo
from typing import List, Optional, Tuple, Union, cast
from dataclasses import dataclass, field, replace
from abc import ABC, abstractmethod
from enum import Enum
import warnings
from .rule import *


# ============================================================================
# AABB utilities
# ============================================================================

def _numeric_min(*vals):
    """Return the minimum of given SymPy numeric values using safe comparison."""
    result = vals[0]
    for v in vals[1:]:
        if safe_compare(v - result, 0, Comparison.LT):
            result = v
    return result


def _numeric_max(*vals):
    """Return the maximum of given SymPy numeric values using safe comparison."""
    result = vals[0]
    for v in vals[1:]:
        if safe_compare(v - result, 0, Comparison.GT):
            result = v
    return result


@dataclass(frozen=True)
class BoundingBox:
    """
    Axis-aligned bounding box (AABB) for a CSG object.

    Each bound is Optional[Numeric] where None means unbounded in that direction.
    """
    min_x: Optional[Numeric]
    min_y: Optional[Numeric]
    min_z: Optional[Numeric]
    max_x: Optional[Numeric]
    max_y: Optional[Numeric]
    max_z: Optional[Numeric]

class PrismFace(Enum):
    """Face of a RectangularPrism, indices match TimberFace."""
    TOP = 1
    BOTTOM = 2
    RIGHT = 3
    FRONT = 4
    LEFT = 5
    BACK = 6


@dataclass(frozen=True)
class CSGFeature(ABC):
    """
    Represents a feature of a CSG object, such as a face or edge, that can be used for referencing in tickets.
    """
    name: str
    priority: int 

    @abstractmethod
    def test_point(self, point: V3) -> bool:
        """
        Test if a given point is on this feature (e.g. on the face or edge).
        This can be used to determine if a cut should reference this feature.
        """
        pass


@dataclass(frozen=True)
class HalfSpaceFeature(CSGFeature):
    """Feature representing the entire boundary plane of a HalfSpace."""
    owner: 'HalfSpace'

    def test_point(self, point: V3) -> bool:
        return self.owner.is_point_on_boundary(point)


@dataclass(frozen=True)
class RectangularPrismFeature(CSGFeature):
    """Feature representing a single face of a RectangularPrism."""
    owner: 'RectangularPrism'
    face: PrismFace

    def test_point(self, point: V3) -> bool:
        if not self.owner.is_point_on_boundary(point):
            return False
        local_point = point - self.owner.transform.position
        m = self.owner.transform.orientation.matrix
        width_dir = Matrix([m[0, 0], m[1, 0], m[2, 0]])
        height_dir = Matrix([m[0, 1], m[1, 1], m[2, 1]])
        length_dir = Matrix([m[0, 2], m[1, 2], m[2, 2]])
        x = safe_dot_product(local_point, width_dir)
        y = safe_dot_product(local_point, height_dir)
        z = safe_dot_product(local_point, length_dir)
        hw = self.owner.size[0] / 2
        hh = self.owner.size[1] / 2
        if self.face == PrismFace.RIGHT:
            return equality_test(x, hw)
        elif self.face == PrismFace.LEFT:
            return equality_test(x, -hw)
        elif self.face == PrismFace.FRONT:
            return equality_test(y, hh)
        elif self.face == PrismFace.BACK:
            return equality_test(y, -hh)
        elif self.face == PrismFace.TOP:
            return self.owner.end_distance is not None and equality_test(z, self.owner.end_distance)
        elif self.face == PrismFace.BOTTOM:
            return self.owner.start_distance is not None and equality_test(z, self.owner.start_distance)
        return False


@dataclass(frozen=True)
class CutCSG(ABC):
    """Base class for all CSG operations."""
    tag: Optional[str] = field(default=None, kw_only=True)

    @abstractmethod
    def __repr__(self) -> str:
        """String representation for debugging."""
        pass

    def find_feature(self, point: V3) -> Optional[CSGFeature]:
        """Return the highest-priority feature at *point*, or None."""
        features = self.get_all_features(point)
        if not features:
            return None
        features.sort(key=lambda f: f.priority)
        for f in features:
            if f.test_point(point):
                return f
        return None

    def get_all_features(self, point: V3) -> List[CSGFeature]:
        """Return all features that the point may belong to."""
        return []


    @abstractmethod
    def contains_point(self, point: V3) -> bool:
        """
        Check if a point is contained within the CSG object.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is inside or on the boundary of the CSG object, False otherwise
        """
        pass

    @abstractmethod
    def is_point_on_boundary(self, point: V3) -> bool:
        """
        Check if a point is on the boundary of the CSG object.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the CSG object, False otherwise
        """
        pass
    
    @abstractmethod
    def get_outward_normal(self, point: V3) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        This method should only be called if is_point_on_boundary(point) is True.
        For points not on the boundary, behavior is undefined.
        
        Args:
            point: A point on the boundary (3x1 Matrix)
            
        Returns:
            The outward normal vector at the point, or None if cannot be determined
        """
        pass

    @abstractmethod
    def get_aabb(self) -> 'BoundingBox':
        """
        Return the axis-aligned bounding box (AABB) of this CSG object.

        Each bound is Optional[Numeric] — None means unbounded in that direction.

        Primitives with infinite extent (HalfSpace, or prisms/cylinders with
        start_distance or end_distance set to None) cannot produce a finite AABB.
        They emit a UserWarning and return a BoundingBox with all fields set to None.
        """
        pass


@dataclass(frozen=True)
class HalfSpace(CutCSG):
    """
    An infinite half-plane defined by a normal vector and offset from origin.
    
    The half-plane includes all points P such that: P · normal >= offset    
    The offset represents the signed distance from the origin along the normal direction
    where the plane is located. Positive offset moves the plane in the direction of the normal.
    
    Args:
        normal: Normal vector pointing into the half-space (3x1 Matrix)
        offset: Distance from origin along normal direction where plane is located (default: 0)
    """
    normal: Direction3D
    offset: Numeric = Integer(0)
    named_feature: Optional[str] = None

    def __repr__(self) -> str:
        return f"HalfSpace(normal={self.normal.T}, offset={self.offset})"
    
    def contains_point(self, point: V3) -> bool:
        """
        Check if a point is contained within the half-plane.
        
        A point P is in the half-plane if (P · normal) >= offset
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is in the half-plane (including boundary), False otherwise
        """
        # Compute dot product: point · normal
        dot_product = safe_dot_product(point, self.normal)
        return dot_product >= self.offset
    
    def is_point_on_boundary(self, point: V3) -> bool:
        """
        Check if a point is on the boundary of the half-plane.
        
        A point P is on the boundary if (P · normal) == offset
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary plane, False otherwise
        """
        from kumiki.rule import zero_test
        # Compute dot product: point · normal
        dot_product = safe_dot_product(point, self.normal)
        # Use zero_test to handle Float vs Integer comparison with tolerance
        return zero_test(dot_product - self.offset)
    
    def get_outward_normal(self, point: V3) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a HalfSpace, the outward normal is always the opposite of thenormal vector itself.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector (the HalfSpace's normal)
        """
        return -self.normal

    def get_all_features(self, point: V3) -> List[CSGFeature]:
        if self.named_feature is not None and self.is_point_on_boundary(point):
            return [HalfSpaceFeature(name=self.named_feature, priority=0, owner=self)]
        return []

    def get_aabb(self) -> BoundingBox:
        warnings.warn(
            "get_aabb() called on HalfSpace, which has infinite extent — result is unbounded",
            UserWarning,
            stacklevel=2,
        )
        return BoundingBox(None, None, None, None, None, None)


@dataclass(frozen=True)
class RectangularPrism(CutCSG):
    """
    A prism with rectangular cross-section, optionally infinite in one or both ends.
    Note,they are parameterized similar to the Timber class which is atypical for such a primitive.
    
    The prism is defined by:
    - A transform (position and orientation in global coordinates)
    - A cross-section size (width (x-axis)) x height (y-axis)) in the local XY plane
    - Start and end distances along the local Z-axis from the position

    So the center point of the size cross section is at position and the timber extends out in -z by start_distance and +z by end_distance.
    
    Use None for start_distance or end_distance to make the prism infinite in that direction.
    
    The orientation matrix defines the local coordinate system where:
    - X-axis (first column) is the width direction (size[0])
    - Y-axis (second column) is the height direction (size[1])
    - Z-axis (third column) is the length/axis direction
    
    Args:
        size: Cross-section dimensions [width, height] (2x1 Matrix)
        transform: Transform (position and orientation) in global coordinates (default: identity)
        start_distance: Distance from position along Z-axis to start of prism (None = 
        -infinite)
        end_distance: Distance from position along Z-axis to end of prism (None = infinite)
    """
    size: V2
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None  # starting distance of the prism in the direction of the +Z axis. None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # ending distance of the prism in the direction of the +Z axis. None means infinite in positive direction
    named_features: Optional[List[Tuple[str, PrismFace]]] = None

    def get_bottom_position(self) -> V3:
        """
        Get the position of the bottom of the prism (at start_distance).
        Only valid for prisms with finite start_distance.
        
        Returns:
            The 3D position at the bottom of the prism
            
        Raises:
            ValueError: If start_distance is None (infinite prism)
        """
        if self.start_distance is None:
            raise ValueError("Cannot get bottom position of infinite prism (start_distance is None)")
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([Integer(0), Integer(0), self.start_distance]))
    
    def get_top_position(self) -> V3:
        """
        Get the position of the top of the prism (at end_distance).
        Only valid for prisms with finite end_distance.
        
        Returns:
            The 3D position at the top of the prism
            
        Raises:
            ValueError: If end_distance is None (infinite prism)
        """
        if self.end_distance is None:
            raise ValueError("Cannot get top position of infinite prism (end_distance is None)")
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([Integer(0), Integer(0), self.end_distance]))
    
    def __repr__(self) -> str:
        return (f"RectangularPrism(size={self.size.T}, transform={self.transform}, "
                f"start={self.start_distance}, end={self.end_distance})")
    
    def equals_prism(self, other: 'RectangularPrism') -> bool:
        """
        Check if this prism equals another prism.
        
        Uses SymPy's equals() method for numeric comparisons to handle symbolic values.
        
        Args:
            other: Another RectangularPrism to compare with
            
        Returns:
            True if all components are equal, False otherwise
        """
        # Check size components
        if not self.size[0].equals(other.size[0]) or not self.size[1].equals(other.size[1]):
            return False
        
        # Check transform position
        if not (self.transform.position[0].equals(other.transform.position[0]) and
                self.transform.position[1].equals(other.transform.position[1]) and
                self.transform.position[2].equals(other.transform.position[2])):
            return False
        
        # Check transform orientation matrix
        for i in range(3):
            for j in range(3):
                if not self.transform.orientation.matrix[i, j].equals(other.transform.orientation.matrix[i, j]):
                    return False
        
        # Check start_distance (handle None case)
        if self.start_distance is None and other.start_distance is None:
            pass  # Both None, equal
        elif self.start_distance is None or other.start_distance is None:
            return False  # One is None, other isn't
        elif not safe_compare(self.start_distance - other.start_distance, 0, Comparison.EQ):
            return False
        
        # Check end_distance (handle None case)
        if self.end_distance is None and other.end_distance is None:
            pass  # Both None, equal
        elif self.end_distance is None or other.end_distance is None:
            return False  # One is None, other isn't
        elif not safe_compare(self.end_distance - other.end_distance, 0, Comparison.EQ):
            return False
        
        return True
    
    def contains_point(self, point: V3) -> bool:
        """
        Check if a point is contained within the prism.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is inside or on the boundary of the prism, False otherwise
        """
        # Transform point to local coordinates
        # Local origin is at self.transform.position
        local_point = point - self.transform.position
        
        # Extract axes from orientation matrix
        width_dir = Matrix([
            self.transform.orientation.matrix[0, 0],
            self.transform.orientation.matrix[1, 0],
            self.transform.orientation.matrix[2, 0]
        ])
        height_dir = Matrix([
            self.transform.orientation.matrix[0, 1],
            self.transform.orientation.matrix[1, 1],
            self.transform.orientation.matrix[2, 1]
        ])
        length_dir = Matrix([
            self.transform.orientation.matrix[0, 2],
            self.transform.orientation.matrix[1, 2],
            self.transform.orientation.matrix[2, 2]
        ])
        
        # Project onto local axes
        x_coord = safe_dot_product(local_point, width_dir)
        y_coord = safe_dot_product(local_point, height_dir)
        z_coord = safe_dot_product(local_point, length_dir)
        
        # Check bounds in each dimension
        half_width = self.size[0] / 2
        half_height = self.size[1] / 2
        
        # Check width and height bounds
        if abs(x_coord) > half_width or abs(y_coord) > half_height:
            return False
        
        # Check length bounds
        if self.start_distance is not None and z_coord < self.start_distance:
            return False
        if self.end_distance is not None and z_coord > self.end_distance:
            return False
        
        return True

    def is_point_on_boundary(self, point: V3) -> bool:
        """
        Check if a point is on the boundary of the prism.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the prism, False otherwise
        """
        # First check if point is contained
        if not self.contains_point(point):
            return False
        
        # Transform point to local coordinates
        local_point = point - self.transform.position
        
        # Extract axes from orientation matrix
        width_dir = Matrix([
            self.transform.orientation.matrix[0, 0],
            self.transform.orientation.matrix[1, 0],
            self.transform.orientation.matrix[2, 0]
        ])
        height_dir = Matrix([
            self.transform.orientation.matrix[0, 1],
            self.transform.orientation.matrix[1, 1],
            self.transform.orientation.matrix[2, 1]
        ])
        length_dir = Matrix([
            self.transform.orientation.matrix[0, 2],
            self.transform.orientation.matrix[1, 2],
            self.transform.orientation.matrix[2, 2]
        ])
        
        # Project onto local axes
        x_coord = safe_dot_product(local_point, width_dir)
        y_coord = safe_dot_product(local_point, height_dir)
        z_coord = safe_dot_product(local_point, length_dir)
        
        # Check if on any face
        half_width = self.size[0] / 2
        half_height = self.size[1] / 2
        
        # On width faces
        if abs(x_coord) == half_width:
            return True
        
        # On height faces
        if abs(y_coord) == half_height:
            return True
        
        # On length faces (if finite)
        if self.start_distance is not None and z_coord == self.start_distance:
            return True
        if self.end_distance is not None and z_coord == self.end_distance:
            return True
        
        return False
    
    def get_outward_normal(self, point: V3) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        Returns the normalized outward normal for the face that contains this point.
        If the point is on multiple faces (edge or corner), returns one of the normals.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector at the point, or None if cannot be determined
        """
        # Transform point to local coordinates
        local_point = point - self.transform.position
        
        # Extract axes from orientation matrix
        width_dir = Matrix([
            self.transform.orientation.matrix[0, 0],
            self.transform.orientation.matrix[1, 0],
            self.transform.orientation.matrix[2, 0]
        ])
        height_dir = Matrix([
            self.transform.orientation.matrix[0, 1],
            self.transform.orientation.matrix[1, 1],
            self.transform.orientation.matrix[2, 1]
        ])
        length_dir = Matrix([
            self.transform.orientation.matrix[0, 2],
            self.transform.orientation.matrix[1, 2],
            self.transform.orientation.matrix[2, 2]
        ])
        
        # Project onto local axes
        x_coord = safe_dot_product(local_point, width_dir)
        y_coord = safe_dot_product(local_point, height_dir)
        z_coord = safe_dot_product(local_point, length_dir)
        
        half_width = self.size[0] / 2
        half_height = self.size[1] / 2
        
        # Check which face(s) the point is on
        # For edges/corners, we'll return one of the normals
        # Prioritize: length faces (top/bottom), then width faces, then height faces
        # This prioritization makes sense for typical CSG operations where end faces are often involved

        # TODO you should check if point is on edges and return averages instead
        
        # On length faces (top/bottom) - check these first
        if self.start_distance is not None and z_coord == self.start_distance:
            return -length_dir  # Bottom face, normal points in -length direction (outward)
        if self.end_distance is not None and z_coord == self.end_distance:
            return length_dir  # Top face, normal points in +length direction (outward)
        
        # On width faces (right/left)
        if abs(x_coord) == half_width:
            if x_coord > 0:
                return width_dir  # Right face, normal points in +width direction
            else:
                return -width_dir  # Left face, normal points in -width direction
        
        # On height faces (front/back)
        if abs(y_coord) == half_height:
            if y_coord > 0:
                return height_dir  # Front face, normal points in +height direction
            else:
                return -height_dir  # Back face, normal points in -height direction
        
        # Should not reach here if point is actually on boundary
        return None

    def get_all_features(self, point: V3) -> List[CSGFeature]:
        if self.named_features is None or not self.is_point_on_boundary(point):
            return []
        # Transform to local coords
        local_point = point - self.transform.position
        m = self.transform.orientation.matrix
        width_dir = Matrix([m[0, 0], m[1, 0], m[2, 0]])
        height_dir = Matrix([m[0, 1], m[1, 1], m[2, 1]])
        length_dir = Matrix([m[0, 2], m[1, 2], m[2, 2]])
        x = safe_dot_product(local_point, width_dir)
        y = safe_dot_product(local_point, height_dir)
        z = safe_dot_product(local_point, length_dir)
        hw = self.size[0] / 2
        hh = self.size[1] / 2
        face_checks = {
            PrismFace.RIGHT: lambda: equality_test(x, hw),
            PrismFace.LEFT: lambda: equality_test(x, -hw),
            PrismFace.FRONT: lambda: equality_test(y, hh),
            PrismFace.BACK: lambda: equality_test(y, -hh),
            PrismFace.TOP: lambda: self.end_distance is not None and equality_test(z, self.end_distance),
            PrismFace.BOTTOM: lambda: self.start_distance is not None and equality_test(z, self.start_distance),
        }
        features: List[CSGFeature] = []
        for name, face in self.named_features:
            if face_checks[face]():
                features.append(RectangularPrismFeature(name=name, priority=0, owner=self, face=face))
        return features

    def get_aabb(self) -> BoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite RectangularPrism — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return BoundingBox(None, None, None, None, None, None)

        half_w = self.size[0] / Integer(2)
        half_h = self.size[1] / Integer(2)

        corners_global = [
            self.transform.local_to_global(Matrix([x_sign * half_w, y_sign * half_h, z]))
            for x_sign in (Integer(-1), Integer(1))
            for y_sign in (Integer(-1), Integer(1))
            for z in (self.start_distance, self.end_distance)
        ]

        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]
        return BoundingBox(
            _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
            _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
        )


@dataclass(frozen=True)
class Cylinder(CutCSG):
    """
    A cylinder with circular cross-section, optionally infinite in one or both ends.
    
    The cylinder is defined by:
    - A position (translation from origin)
    - An axis direction
    - A radius
    - Start and end distances along the axis from the position
    
    So the center point of the radius cross section is at position and the cylinder extends out in -z by start_distance and +z by end_distance.

    Use None for start_distance or end_distance to make the cylinder infinite in that direction.
    
    Args:
        axis_direction: Direction of the cylinder's axis (3x1 Matrix)
        radius: Radius of the cylinder
        position: Position of the cylinder origin in global coordinates (3x1 Matrix, default: origin)
        start_distance: Distance from position to start of cylinder (None = -infinite)
        end_distance: Distance from position to end of cylinder (None = infinite)
    """
    # TODO consider just making this a Transform object, even though we don't care about one of the DOFs
    axis_direction: Direction3D  # direction of the cylinder's axis, which is the +Z local axis
    radius: Numeric
    position: V3 = field(default_factory=lambda: Matrix([Integer(0), Integer(0), Integer(0)]))  # Position in global coordinates
    start_distance: Optional[Numeric] = None  # None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # None means infinite in positive direction

    def __repr__(self) -> str:
        return (f"Cylinder(axis={self.axis_direction.T}, "
                f"radius={self.radius}, "
                f"position={self.position.T}, "
                f"start={self.start_distance}, end={self.end_distance})")
    
    def contains_point(self, point: V3) -> bool:
        """
        Check if a point is contained within the cylinder.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is inside or on the boundary of the cylinder, False otherwise
        """
        # Transform point to local coordinates
        local_point = point - self.position
        
        # Normalize axis
        axis = self.axis_direction / safe_norm(self.axis_direction)
        
        # Project onto axis to get axial coordinate
        axial_coord = safe_dot_product(local_point, axis)
        
        # Check axial bounds
        if self.start_distance is not None and axial_coord < self.start_distance:
            return False
        if self.end_distance is not None and axial_coord > self.end_distance:
            return False
        
        # Calculate radial distance from axis
        axial_projection = axis * axial_coord
        radial_vector = local_point - axial_projection
        radial_distance = safe_norm(radial_vector)
        
        # Check if within radius
        return radial_distance <= self.radius

    def is_point_on_boundary(self, point: V3) -> bool:
        """
        Check if a point is on the boundary of the cylinder.
        
        A point is on the boundary if it's either:
        1. On the cylindrical surface (at radius distance from axis)
        2. On one of the end caps (if finite)
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the cylinder, False otherwise
        """
        # First check if point is contained
        if not self.contains_point(point):
            return False
        
        # Transform point to local coordinates
        local_point = point - self.position
        
        # Normalize axis
        axis = self.axis_direction / safe_norm(self.axis_direction)
        
        # Project onto axis to get axial coordinate
        axial_coord = safe_dot_product(local_point, axis)
        
        # Calculate radial distance from axis
        axial_projection = axis * axial_coord
        radial_vector = local_point - axial_projection
        radial_distance = safe_norm(radial_vector)
        
        # On cylindrical surface
        if radial_distance == self.radius:
            return True
        
        # On end caps (if finite and at the end)
        if self.start_distance is not None and axial_coord == self.start_distance:
            return True
        if self.end_distance is not None and axial_coord == self.end_distance:
            return True
        
        return False
    
    def get_outward_normal(self, point: V3) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a cylinder, the normal depends on which surface the point is on.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector at the point
        """
        # Transform point to local coordinates
        local_point = point - self.position
        
        # Normalize axis
        axis = self.axis_direction / safe_norm(self.axis_direction)
        
        # Project onto axis to get axial coordinate
        axial_coord = safe_dot_product(local_point, axis)
        
        # Calculate radial distance from axis
        axial_projection = axis * axial_coord
        radial_vector = local_point - axial_projection
        radial_distance = safe_norm(radial_vector)
        
        # Check if on cylindrical surface first (most common case)
        if radial_distance == self.radius:
            # Normal is the radial direction (normalized)
            if radial_distance == Integer(0):
                # Point is on the axis, which shouldn't happen for the cylindrical surface
                # This might be an edge case on the cap center
                pass
            else:
                return radial_vector / radial_distance
        
        # Check if on end caps
        if self.start_distance is not None and axial_coord == self.start_distance:
            # Bottom cap, normal points in -axis direction (outward)
            return -axis
        if self.end_distance is not None and axial_coord == self.end_distance:
            # Top cap, normal points in +axis direction (outward)
            return axis
        
        # Should not reach here if point is on boundary
        return None

    def get_aabb(self) -> BoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite Cylinder — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return BoundingBox(None, None, None, None, None, None)

        axis_norm = self.axis_direction / safe_norm(self.axis_direction)
        p1 = self.position + axis_norm * self.start_distance
        p2 = self.position + axis_norm * self.end_distance

        bounds = []
        for i in range(3):
            ai = axis_norm[i]
            radial_i = self.radius * sqrt(Integer(1) - ai * ai)
            lo = _numeric_min(p1[i], p2[i]) - radial_i
            hi = _numeric_max(p1[i], p2[i]) + radial_i
            bounds.append((lo, hi))

        return BoundingBox(
            bounds[0][0], bounds[1][0], bounds[2][0],
            bounds[0][1], bounds[1][1], bounds[2][1],
        )


@dataclass(frozen=True)
class SolidUnion(CutCSG):
    """
    CSG union operation - combines multiple CSG objects.
    
    The union represents the set of all points that are in ANY of the child CSG objects.
    
    Args:
        children: List of CSG objects to union together
    """
    children: List[CutCSG]

    def __repr__(self) -> str:
        return f"SolidUnion({len(self.children)} children)"
    
    def contains_point(self, point: V3) -> bool:
        """
        Check if a point is contained within the union.
        
        A point is in the union if it's in ANY of the children.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is in any of the children, False otherwise
        """
        return any(child.contains_point(point) for child in self.children)

    def is_point_on_boundary(self, point: V3) -> bool:
        """
        Check if a point is on the boundary of the union.
        
        A point is on the boundary if it's on the boundary of at least one child
        and not in the interior of any other child.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the union, False otherwise
        """
        # Point must be contained in the union
        if not self.contains_point(point):
            return False
        
        # Check if on boundary of any child and not strictly inside all others
        on_any_boundary = False
        for child in self.children:
            if child.contains_point(point):
                if child.is_point_on_boundary(point):
                    on_any_boundary = True
                else:
                    # Point is strictly inside this child, so not on union boundary
                    return False
        
        return on_any_boundary
    
    def get_outward_normal(self, point: V3) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a union, we check all children that have the point on their boundary
        and return the average of their outward normals. The reason we do this is because this method is used to check if a point is on the boundary through Differences and using an average normal here tends to behave better on weird non-convex geometry.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The average outward normal vector, or None if cannot be determined
        """
        normals = []
        
        for child in self.children:
            if child.is_point_on_boundary(point):
                normal = child.get_outward_normal(point)
                if normal is not None:
                    normals.append(normal)
        
        if len(normals) == Integer(0):
            return None
        elif len(normals) == Integer(1):
            return normals[0]
        else:
            # Average the normals
            avg_normal = normals[0]
            for n in normals[1:]:
                avg_normal = avg_normal + n
            # Normalize
            norm = safe_norm(avg_normal)
            if norm == Integer(0):
                return None
            return avg_normal / norm

    def get_all_features(self, point: V3) -> List[CSGFeature]:
        features: List[CSGFeature] = []
        for child in self.children:
            features.extend(child.get_all_features(point))
        features.sort(key=lambda f: f.priority)
        return features

    def get_aabb(self) -> BoundingBox:
        if not self.children:
            return BoundingBox(None, None, None, None, None, None)

        bboxes = [child.get_aabb() for child in self.children]

        def union_min(vals):
            if any(v is None for v in vals):
                return None
            return _numeric_min(*vals)

        def union_max(vals):
            if any(v is None for v in vals):
                return None
            return _numeric_max(*vals)

        return BoundingBox(
            union_min([b.min_x for b in bboxes]),
            union_min([b.min_y for b in bboxes]),
            union_min([b.min_z for b in bboxes]),
            union_max([b.max_x for b in bboxes]),
            union_max([b.max_y for b in bboxes]),
            union_max([b.max_z for b in bboxes]),
        )


@dataclass(frozen=True)
class Difference(CutCSG):
    """
    CSG difference operation - subtracts multiple CSG objects from a base object.
    
    The difference represents: base - subtract[0] - subtract[1] - ...
    All points in base that are NOT in any of the subtract objects.
    
    Args:
        base: The base CSG object to subtract from
        subtract: List of CSG objects to subtract from the base
    """
    base: CutCSG
    subtract: List[CutCSG]

    def __repr__(self) -> str:
        return f"Difference(base={self.base}, subtract={len(self.subtract)} objects)"
    
    def contains_point(self, point: V3) -> bool:
        """
        Check if a point is contained within the difference.
        
        A point is in the difference if it's in the base and NOT strictly inside any subtract object.
        Special case: if a point is on the boundary of both base and subtract, it's excluded.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is in base but not in any subtract objects, False otherwise
        """
        # Point must be in base
        if not self.base.contains_point(point):
            return False
        
        # Check if on base boundary
        on_base_boundary = self.base.is_point_on_boundary(point)
        
        # Point must not be strictly inside any subtract object
        # If point is on boundary of both base and subtract, check normals
        for sub in self.subtract:
            if sub.contains_point(point):
                if not sub.is_point_on_boundary(point):
                    # Point is strictly inside a subtract object
                    return False
                elif on_base_boundary:
                    # Point is on boundary of both base and subtract
                    # Check the outward normals
                    base_normal = self.base.get_outward_normal(point)
                    sub_normal = sub.get_outward_normal(point)
                    
                    if base_normal is not None and sub_normal is not None:
                        # Compute dot product of normals
                        dot_product = safe_dot_product(base_normal, sub_normal)
                        
                        # If dot product == 1, surfaces overlap, exclude the point
                        # TODO what were really wanting to chec khere is that the surfaces are the same locally which may not be the case if the normal was on an edge with this condition. To fix this you should introduce an is_on_edge function HOWEVER this also won't work in the case of stuff like cylinders, so to fix that you probably really need a surface_derivative (curvature) function...
                        if equality_test(dot_product, 1):
                            return False
                    else:
                        # Cannot determine normals, use conservative approach: exclude
                        return False
        
        return True

    def is_point_on_boundary(self, point: V3) -> bool:
        """
        Check if a point is on the boundary of the difference.
        
        A point is on the boundary if:
        1. It's contained in the difference (base - subtract), AND
        2. Either:
           a. It's on the boundary of the base, OR
           b. It's strictly inside the base but on the boundary of at least one subtract object
        
        Note: For case 2b, the point creates a new boundary surface (the "hole" surface).
        The point must be on the subtract boundary but NOT inside the subtract (i.e., on the
        surface of the hole facing the remaining material).
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the difference, False otherwise
        """
        # Point must be contained in base
        if not self.base.contains_point(point):
            return False
        
        # Check if point is in any subtract region (strictly inside, not just boundary)
        in_subtract_interior = False
        on_subtract_boundary = False
        
        for sub in self.subtract:
            if sub.contains_point(point):
                if sub.is_point_on_boundary(point):
                    on_subtract_boundary = True
                else:
                    # Point is strictly inside a subtract object
                    in_subtract_interior = True
                    break
        
        # If point is strictly inside any subtract, it's not on the difference boundary
        if in_subtract_interior:
            return False
        
        # If point is on subtract boundary, it's on the difference boundary
        if on_subtract_boundary:
            return True
        
        # Otherwise, check if it's on the base boundary
        return self.base.is_point_on_boundary(point)
    
    def get_outward_normal(self, point: V3) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a difference, if the point is on the boundary of the base CSG, return that normal.
        Otherwise, go through the subtract CSGs and return the average of their normals (negated).
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector, or None if cannot be determined
        """
        # If point is on base boundary, return base's normal
        if self.base.is_point_on_boundary(point):
            return self.base.get_outward_normal(point)
        
        # Otherwise, point must be on subtract boundary (creating a "hole")
        # The normal should point inward to the subtract (which is outward from the difference)
        # So we negate the subtract's outward normal
        normals = []
        for sub in self.subtract:
            if sub.is_point_on_boundary(point):
                normal = sub.get_outward_normal(point)
                if normal is not None:
                    # Negate because we want the normal pointing into the remaining material
                    normals.append(-normal)
        
        if len(normals) == Integer(0):
            return None
        elif len(normals) == Integer(1):
            return normals[0]
        else:
            # Average the normals
            avg_normal = normals[0]
            for n in normals[1:]:
                avg_normal = avg_normal + n
            # Normalize
            norm = safe_norm(avg_normal)
            if norm == Integer(0):
                return None
            return avg_normal / norm

    def get_all_features(self, point: V3) -> List[CSGFeature]:
        if not self.is_point_on_boundary(point):
            return []
        # Collect features from both the base and subtract children
        features: List[CSGFeature] = []
        features.extend(self.base.get_all_features(point))
        for sub in self.subtract:
            features.extend(sub.get_all_features(point))
        features.sort(key=lambda f: f.priority)
        return features

    def get_aabb(self) -> BoundingBox:
        bbox = self.base.get_aabb()
        for sub in self.subtract:
            if isinstance(sub, HalfSpace):
                bbox = _clip_bbox_by_halfspace_complement(bbox, sub)
        return bbox


# TODO come upw ith a cuter/better name for these
Profile = List[V2]
Profiles = List[Profile]

def translate_profile(profile: Profile, translation: V2) -> Profile:
    """
    Translate a profile by a given translation vector.
    """
    return [point + translation for point in profile]

def translate_profiles(profiles: Profiles, translation: V2) -> Profiles:
    """
    Translate a list of profiles by a given translation vector.
    """
    return [translate_profile(profile, translation) for profile in profiles]


@dataclass(frozen=True)
class ConvexPolygonExtrusion(CutCSG):
    """
    An extruded Convex Polygon shape, optionally infinite in one or both ends.
    
    The extrusion is defined by:
    - A list of ordered (x,y) points in the polygon (must be convex!)
    - A transform (position and orientation in global coordinates)
    - Start and end distances along the local Z-axis from the position
    
    The polygon is in the local XY plane at the position, and the extrusion extends
    out in -z by start_distance and +z by end_distance.
    
    Use None for start_distance or end_distance to make the extrusion infinite in that direction.
    
    Args:
        points: List of ordered (x,y) points in the polygon (last connects to first, must be convex)
        transform: Transform (position and orientation) in global coordinates (default: identity)
        start_distance: Distance from position along Z-axis to start of extrusion (None = -infinite)
        end_distance: Distance from position along Z-axis to end of extrusion (None = infinite)
    """
    points: Profile
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None  # starting distance in the direction of the -Z axis. None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # ending distance in the direction of the +Z axis. None means infinite in positive direction

    def get_bottom_position(self) -> V3:
        """
        Get the position of the bottom of the extrusion (at start_distance).
        Only valid for extrusions with finite start_distance.
        
        Returns:
            The 3D position at the bottom of the extrusion
            
        Raises:
            ValueError: If start_distance is None (infinite extrusion)
        """
        if self.start_distance is None:
            raise ValueError("Cannot get bottom position of infinite extrusion (start_distance is None)")
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([Integer(0), Integer(0), self.start_distance]))
    
    def get_top_position(self) -> V3:
        """
        Get the position of the top of the extrusion (at end_distance).
        Only valid for extrusions with finite end_distance.
        
        Returns:
            The 3D position at the top of the extrusion
            
        Raises:
            ValueError: If end_distance is None (infinite extrusion)
        """
        if self.end_distance is None:
            raise ValueError("Cannot get top position of infinite extrusion (end_distance is None)")
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([Integer(0), Integer(0), self.end_distance]))

    def __repr__(self) -> str:
        return (f"ConvexPolygonExtrusion({len(self.points)} points, "
                f"transform={self.transform}, start={self.start_distance}, end={self.end_distance})")
    
    def is_valid(self) -> bool:
        """
        Check if the ConvexPolygonExtrusion is valid
        
        Checks:
        1. At least 3 points
        2. Valid distance configuration (if both finite, end > start)
        3. Polygon is convex (all turns go the same direction)
        
        Returns:
            True if valid, False otherwise
        """
        if len(self.points) < 3:
            return False
        
        # Check distance configuration
        if self.start_distance is not None and self.end_distance is not None:
            if self.end_distance <= self.start_distance:
                return False
        
        # Check convexity: all cross products of consecutive edges should have the same sign
        # For a convex polygon, as we traverse the vertices, we should always turn the same way
        n = len(self.points)
        
        # Compute 2D cross product for each triplet of consecutive points
        def cross_product(i):
            p0, p1, p2 = self.points[i], self.points[(i + 1) % n], self.points[(i + 2) % n]
            edge1, edge2 = p1 - p0, p2 - p1
            return edge1[0] * edge2[1] - edge1[1] * edge2[0]
        
        # Generate all cross products and filter out zeros (collinear points)
        cross_products = [cross_product(i) for i in range(n)]
        non_zero_crosses = [cp for cp in cross_products if cp != Integer(0)]
        
        # Reject if all collinear, otherwise check all turns go the same direction
        return (len(non_zero_crosses) > Integer(0) and 
                (all(cp > Integer(0) for cp in non_zero_crosses) or 
                 all(cp < Integer(0) for cp in non_zero_crosses)))

    def contains_point(self, point: V3) -> bool:
        """
        Check if a point is contained within the extruded polygon.
        
        A point is inside if:
        1. Its Z coordinate (in local space) is between start_distance and end_distance
        2. Its XY coordinates (in local space) are inside the convex polygon
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is inside or on the boundary, False otherwise
        """
        # Transform point to local coordinates
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        
        x_coord = local_coords[0]
        y_coord = local_coords[1]
        z_coord = local_coords[2]
        
        # Check Z bounds (use safe_compare for tolerance with Float vs Integer)
        from kumiki.rule import safe_compare, Comparison
        if self.start_distance is not None and safe_compare(z_coord - self.start_distance, 0, Comparison.LT):
            return False
        if self.end_distance is not None and safe_compare(z_coord - self.end_distance, 0, Comparison.GT):
            return False
        
        # Check if (x_coord, y_coord) is inside the convex polygon
        # For a convex polygon, a point is inside if it's on the correct side
        # of all edges
        point_2d = Matrix([x_coord, y_coord])
        
        for i in range(len(self.points)):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % len(self.points)]
            
            # Edge vector from p1 to p2
            edge = p2 - p1
            
            # Vector from p1 to test point
            to_point = point_2d - p1
            
            # Cross product in 2D: edge × to_point
            # If polygon vertices are ordered counter-clockwise, 
            # cross product should be >= 0 for point to be inside
            cross = edge[0] * to_point[1] - edge[1] * to_point[0]
            
            # Use safe_compare with tolerance to handle Float vs Integer comparisons
            from kumiki.rule import safe_compare, Comparison
            if safe_compare(cross, 0, Comparison.LT):
                return False
        
        return True

    def is_point_on_boundary(self, point: V3) -> bool:
        """
        Check if a point is on the boundary of the extruded polygon.
        
        A point is on the boundary if it's contained and either:
        1. On the top or bottom face (z = start_distance or z = end_distance, if finite)
        2. On one of the side faces (on an edge of the polygon)
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary, False otherwise
        """
        # First check if point is contained
        if not self.contains_point(point):
            return False
        
        # Transform point to local coordinates
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        
        x_coord = local_coords[0]
        y_coord = local_coords[1]
        z_coord = local_coords[2]
        
        from kumiki.rule import zero_test
        # Check if on top or bottom face (if finite)
        if self.start_distance is not None and zero_test(z_coord - self.start_distance):
            return True
        if self.end_distance is not None and zero_test(z_coord - self.end_distance):
            return True
        
        # Check if on a vertical edge (point is at a vertex XY coordinate)
        point_2d = Matrix([x_coord, y_coord])
        for vertex_2d in self.points:
            distance_sq = (point_2d[0] - vertex_2d[0])**2 + (point_2d[1] - vertex_2d[1])**2
            if zero_test(distance_sq):
                return True  # Point is on a vertical edge
        
        # Check if on any horizontal edge of the polygon (side face at this z)
        for i in range(len(self.points)):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % len(self.points)]
            
            # Check if point is on the line segment from p1 to p2
            # Use parametric form: p = p1 + t*(p2-p1), where 0 <= t <= 1
            edge = p2 - p1
            to_point = point_2d - p1
            
            # If edge is zero-length, skip it
            edge_length_sq = edge[0]**2 + edge[1]**2
            if zero_test(edge_length_sq):
                continue
            
            # Project to_point onto edge
            t = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq
            
            # Check if projection is on the segment [0, 1]
            from kumiki.rule import safe_compare, Comparison
            t_in_range = safe_compare(t, 0, Comparison.GE) and safe_compare(t - Integer(1), 0, Comparison.LE)
            
            if t_in_range:
                closest_point = p1 + edge * t
                distance_sq = (point_2d[0] - closest_point[0])**2 + (point_2d[1] - closest_point[1])**2
                if zero_test(distance_sq):
                    return True
        
        return False
    
    def get_outward_normal(self, point: V3) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a convex polygon extrusion, the normal depends on which surface.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector at the point
        """
        # Transform point to local coordinates
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        
        x_coord = local_coords[0]
        y_coord = local_coords[1]
        z_coord = local_coords[2]
        
        # Check if on top face
        if self.end_distance is not None and z_coord == self.end_distance:
            # Top face, normal points in +Z direction in local coords
            local_normal = Matrix([Integer(0), Integer(0), Integer(1)])
            return safe_transform_vector(self.transform.orientation.matrix, local_normal)
        
        # Check if on bottom face
        if self.start_distance is not None and z_coord == self.start_distance:
            # Bottom face, normal points in -Z direction in local coords
            local_normal = Matrix([Integer(0), Integer(0), Integer(-1)])
            return safe_transform_vector(self.transform.orientation.matrix, local_normal)
        
        # Otherwise, point is on a side face (edge of polygon extruded)
        # Find which edge it's on and compute the normal
        point_2d = Matrix([x_coord, y_coord])
        
        for i in range(len(self.points)):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % len(self.points)]
            
            # Check if point is on the line segment from p1 to p2
            edge = p2 - p1
            to_point = point_2d - p1
            
            edge_length_sq = edge[0]**2 + edge[1]**2
            if edge_length_sq == Integer(0):
                continue
            
            t = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq
            
            if Integer(0) <= t <= Integer(1):
                closest_point = p1 + edge * t
                distance_sq = (point_2d[0] - closest_point[0])**2 + (point_2d[1] - closest_point[1])**2
                if distance_sq == Integer(0):
                    # Point is on this edge
                    # Normal is perpendicular to edge (in 2D), pointing outward
                    # Left perpendicular of (dx, dy) is (-dy, dx)
                    edge_normal_2d = Matrix([-edge[1], edge[0]])
                    edge_normal_2d = edge_normal_2d / sqrt(edge_normal_2d[0]**2 + edge_normal_2d[1]**2)
                    
                    # Check if this normal points outward (away from polygon center)
                    # Calculate polygon center
                    center_x = sum(p[0] for p in self.points) / len(self.points)
                    center_y = sum(p[1] for p in self.points) / len(self.points)
                    center = Matrix([center_x, center_y])
                    
                    # Vector from center to point on edge
                    to_edge = closest_point - center
                    
                    # If dot product is negative, flip the normal
                    if (edge_normal_2d[0] * to_edge[0] + edge_normal_2d[1] * to_edge[1]) < Integer(0):
                        edge_normal_2d = -edge_normal_2d
                    
                    # Convert to 3D local normal (no Z component for side faces)
                    local_normal = Matrix([edge_normal_2d[0], edge_normal_2d[1], 0])
                    
                    # Transform to global coordinates
                    return safe_transform_vector(self.transform.orientation.matrix, local_normal)
        
        return None

    def get_aabb(self) -> BoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite ConvexPolygonExtrusion — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return BoundingBox(None, None, None, None, None, None)

        corners_global = [
            self.transform.local_to_global(Matrix([pt[0], pt[1], z]))
            for pt in self.points
            for z in (self.start_distance, self.end_distance)
        ]

        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]
        return BoundingBox(
            _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
            _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
        )


# ============================================================================
# AABB clipping utility
# ============================================================================

def _clip_bbox_by_halfspace_complement(bbox: BoundingBox, hs: HalfSpace) -> BoundingBox:
    """
    Tighten a bounding box by removing the region inside ``hs``.

    Returns the AABB of the intersection of ``bbox`` with the complement of ``hs``
    (i.e., the set of points where ``hs.contains_point()`` is False).

    If any bound of ``bbox`` is None the box is returned unchanged, because
    we cannot enumerate the corners of an infinite box.
    """
    if any(v is None for v in [bbox.min_x, bbox.min_y, bbox.min_z,
                                bbox.max_x, bbox.max_y, bbox.max_z]):
        return bbox

    # 8 corners of the AABB
    corners = [
        Matrix([x, y, z])
        for x in (bbox.min_x, bbox.max_x)
        for y in (bbox.min_y, bbox.max_y)
        for z in (bbox.min_z, bbox.max_z)
    ]

    # 12 edges (each edge connects two corners that differ in exactly one coordinate)
    edges = [
        # 4 edges parallel to X
        (Matrix([bbox.min_x, bbox.min_y, bbox.min_z]), Matrix([bbox.max_x, bbox.min_y, bbox.min_z])),
        (Matrix([bbox.min_x, bbox.max_y, bbox.min_z]), Matrix([bbox.max_x, bbox.max_y, bbox.min_z])),
        (Matrix([bbox.min_x, bbox.min_y, bbox.max_z]), Matrix([bbox.max_x, bbox.min_y, bbox.max_z])),
        (Matrix([bbox.min_x, bbox.max_y, bbox.max_z]), Matrix([bbox.max_x, bbox.max_y, bbox.max_z])),
        # 4 edges parallel to Y
        (Matrix([bbox.min_x, bbox.min_y, bbox.min_z]), Matrix([bbox.min_x, bbox.max_y, bbox.min_z])),
        (Matrix([bbox.max_x, bbox.min_y, bbox.min_z]), Matrix([bbox.max_x, bbox.max_y, bbox.min_z])),
        (Matrix([bbox.min_x, bbox.min_y, bbox.max_z]), Matrix([bbox.min_x, bbox.max_y, bbox.max_z])),
        (Matrix([bbox.max_x, bbox.min_y, bbox.max_z]), Matrix([bbox.max_x, bbox.max_y, bbox.max_z])),
        # 4 edges parallel to Z
        (Matrix([bbox.min_x, bbox.min_y, bbox.min_z]), Matrix([bbox.min_x, bbox.min_y, bbox.max_z])),
        (Matrix([bbox.max_x, bbox.min_y, bbox.min_z]), Matrix([bbox.max_x, bbox.min_y, bbox.max_z])),
        (Matrix([bbox.min_x, bbox.max_y, bbox.min_z]), Matrix([bbox.min_x, bbox.max_y, bbox.max_z])),
        (Matrix([bbox.max_x, bbox.max_y, bbox.min_z]), Matrix([bbox.max_x, bbox.max_y, bbox.max_z])),
    ]

    valid_points = []

    # Keep corners that lie outside (or on the boundary of) the halfspace
    for c in corners:
        if not hs.contains_point(c):
            valid_points.append(c)

    # Find intersections of each AABB edge with the halfspace boundary plane
    for a, b in edges:
        na = safe_dot_product(hs.normal, a)
        nb = safe_dot_product(hs.normal, b)
        denom = nb - na
        if safe_compare(denom, 0, Comparison.EQ):
            # Edge parallel to the plane — no intersection
            continue
        t = (hs.offset - na) / denom
        if safe_compare(t, 0, Comparison.GE) and safe_compare(t - Integer(1), 0, Comparison.LE):
            valid_points.append(a + (b - a) * t)

    if not valid_points:
        # The entire bbox is consumed by the halfspace — return a degenerate (point) bbox
        return BoundingBox(bbox.min_x, bbox.min_y, bbox.min_z,
                           bbox.min_x, bbox.min_y, bbox.min_z)

    xs = [p[0] for p in valid_points]
    ys = [p[1] for p in valid_points]
    zs = [p[2] for p in valid_points]
    return BoundingBox(
        _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
        _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
    )


# ============================================================================
# CSG Coordinate Transform Utility
# ============================================================================

def translate_csg(csg: CutCSG, translation: V3) -> CutCSG:
    """
    Return a copy of the CSG object translated by the given vector.

    Args:
        csg: The CSG object to translate
        translation: 3D translation vector (3x1 Matrix)

    Returns:
        A new CSG object with the same structure but translated by translation
    """
    if isinstance(csg, SolidUnion):
        return SolidUnion(children=[translate_csg(c, translation) for c in csg.children], tag=csg.tag)
    if isinstance(csg, Difference):
        return Difference(
            base=translate_csg(csg.base, translation),
            subtract=[translate_csg(s, translation) for s in csg.subtract],
            tag=csg.tag,
        )
    if isinstance(csg, HalfSpace):
        # HalfSpace: normal·P >= offset. After translating by T: normal·(P - T) >= offset => normal·P >= offset + normal·T
        new_offset = csg.offset + safe_dot_product(csg.normal, translation)
        return replace(csg, offset=new_offset)
    if isinstance(csg, RectangularPrism):
        new_position = csg.transform.position + translation
        new_transform = replace(csg.transform, position=new_position)
        return replace(csg, transform=new_transform)
    if isinstance(csg, ConvexPolygonExtrusion):
        new_position = csg.transform.position + translation
        new_transform = replace(csg.transform, position=new_position)
        return replace(csg, transform=new_transform)
    if isinstance(csg, Cylinder):
        return replace(csg, position=csg.position + translation)
    # Unknown CSG type: return as-is
    return csg


def adopt_csg(
    orig_transform: Optional[Transform],
    adopting_transform: Transform,
    csg_in_orig_space: CutCSG,
) -> CutCSG:
    """
    Transform a CSG object into adopting_transform's local coordinate system.

    If orig_transform is provided, the CSG is treated as being in that transform's local
    coordinates. If orig_transform is None, the CSG is treated as being in global coordinates.

    Args:
        orig_transform: The transform whose local space the CSG is in, or None for global
        adopting_transform: The transform whose local space we want the CSG in
        csg_in_orig_space: The CSG object (in orig_transform local, or global if orig_transform is None)

    Returns:
        A new CSG object in adopting_transform's local coordinates

    Example:
        >>> cut_on_b = adopt_csg(timber_a.transform, timber_b.transform, cut_csg)
        >>> csg_in_tenon_local = adopt_csg(None, tenon_timber.transform, csg_global)
    """
    # Helper: Transform from orig (or global) to adopting local
    def transform_transform(trans: Transform) -> Transform:
        if orig_transform is not None:
            global_position = orig_transform.numeric_local_to_global(trans.position)
            global_orientation = orig_transform.orientation * trans.orientation
        else:
            global_position = trans.position
            global_orientation = trans.orientation

        local_position = adopting_transform.numeric_global_to_local(global_position)
        local_orientation = adopting_transform.orientation.invert() * global_orientation
        return Transform(position=local_position, orientation=local_orientation)

    # Helper: HalfSpace from orig (or global) to adopting local
    def transform_halfspace(hp: HalfSpace) -> HalfSpace:
        if orig_transform is not None:
            global_normal = numeric_transform_vector(orig_transform.orientation.matrix, hp.normal)
        else:
            global_normal = hp.normal

        new_local_normal = numeric_transform_vector(
            adopting_transform.orientation.matrix.T, global_normal
        )

        normal_length_sq = numeric_dot_product(hp.normal, hp.normal)
        if normal_length_sq == Integer(0):
            return replace(hp, normal=new_local_normal, offset=hp.offset)

        point_on_plane_in_orig = hp.normal * (hp.offset / normal_length_sq)
        if orig_transform is not None:
            point_on_plane_global = orig_transform.numeric_local_to_global(point_on_plane_in_orig)
        else:
            point_on_plane_global = point_on_plane_in_orig

        point_on_plane_new_local = adopting_transform.numeric_global_to_local(point_on_plane_global)
        new_offset = numeric_dot_product(new_local_normal, point_on_plane_new_local)
        return replace(hp, normal=new_local_normal, offset=new_offset)

    # Recursively transform based on CSG type
    if isinstance(csg_in_orig_space, SolidUnion):
        transformed_children = [
            adopt_csg(orig_transform, adopting_transform, child)
            for child in csg_in_orig_space.children
        ]
        return SolidUnion(transformed_children, tag=csg_in_orig_space.tag)

    elif isinstance(csg_in_orig_space, Difference):
        transformed_base = adopt_csg(orig_transform, adopting_transform, csg_in_orig_space.base)
        transformed_subtract = [
            adopt_csg(orig_transform, adopting_transform, sub)
            for sub in csg_in_orig_space.subtract
        ]
        return Difference(base=transformed_base, subtract=transformed_subtract, tag=csg_in_orig_space.tag)

    elif isinstance(csg_in_orig_space, HalfSpace):
        return transform_halfspace(csg_in_orig_space)

    elif hasattr(csg_in_orig_space, "transform"):
        new_transform = transform_transform(cast(Transform, csg_in_orig_space.transform))
        return replace(csg_in_orig_space, transform=new_transform)

    else:
        return csg_in_orig_space