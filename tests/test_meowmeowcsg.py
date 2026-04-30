"""
Tests for cutcsg.py module.

This module contains tests for the CSG primitives and operations.
"""

import pytest
from sympy import Matrix, Rational, Integer, simplify, sqrt, cos, sin, pi
from kumiki.rule import Orientation, Transform, create_v3, radians
from kumiki.cutcsg import (
    HalfSpace,
    RectangularPrism,
    Cylinder,
    SolidUnion,
    Difference,
    ConvexPolygonExtrusion,
    BoundingBox,
    PrismFace,
    HalfSpaceFeature,
    RectangularPrismFeature,
    adopt_csg,
    translate_csg,
    translate_profile,
    translate_profiles,
)
from kumiki.rule import create_v2
from tests.testing_shavings import assert_is_valid_rotation_matrix, create_standard_vertical_timber
import random


# ============================================================================
# Helper Functions for Random Shape Generation and Boundary Point Testing
# ============================================================================

def generate_random_prism():
    """Generate a random prism with random size, orientation, position, and distances."""
    size = Matrix([Rational(random.randint(2, 10)), Rational(random.randint(2, 10))])
    orientation = Orientation()  # Identity orientation for simplicity
    position = Matrix([Rational(random.randint(-50, 50)), 
                      Rational(random.randint(-50, 50)), 
                      Rational(random.randint(-50, 50))])
    start_dist = Rational(random.randint(0, 10))
    end_dist = Rational(random.randint(15, 30))
    
    transform = Transform(position=position, orientation=orientation)
    return RectangularPrism(size=size, transform=transform,
                start_distance=start_dist, end_distance=end_dist)


def generate_random_cylinder():
    """Generate a random cylinder with random axis, radius, position, and distances."""
    # Use simple axis directions for predictability
    axes = [Matrix([Integer(1), Integer(0), Integer(0)]), Matrix([Integer(0), Integer(1), Integer(0)]), Matrix([Integer(0), Integer(0), Integer(1)])]
    axis = random.choice(axes)
    radius = Rational(random.randint(2, 8))
    position = Matrix([Rational(random.randint(-50, 50)), 
                      Rational(random.randint(-50, 50)), 
                      Rational(random.randint(-50, 50))])
    start_dist = Rational(random.randint(0, 10))
    end_dist = Rational(random.randint(15, 30))
    
    return Cylinder(axis_direction=axis, radius=radius, position=position,
                   start_distance=start_dist, end_distance=end_dist)


def generate_random_halfspace():
    """Generate a random half-plane with random normal and offset."""
    # Use simple normalized normals for predictability
    normals = [Matrix([Integer(1), Integer(0), Integer(0)]), Matrix([Integer(0), Integer(1), Integer(0)]), Matrix([Integer(0), Integer(0), Integer(1)]),
               Matrix([Integer(1), Integer(1), Integer(0)]) / sqrt(2), Matrix([Integer(1), Integer(0), Integer(1)]) / sqrt(2)]
    normal = random.choice(normals)
    offset = Rational(random.randint(-20, 20))
    
    return HalfSpace(normal=normal, offset=offset)


def generate_random_convex_polygon_extrusion():
    """Generate a random extruded convex polygon with 3-6 vertices."""
    num_vertices = random.randint(3, 6)
    
    # Generate a regular polygon for simplicity and guaranteed convexity
    radius = Rational(random.randint(3, 8))
    vertices = []
    for i in range(num_vertices):
        angle = radians(Integer(2) * pi * i / num_vertices)
        x = radius * cos(angle)
        y = radius * sin(angle)
        vertices.append(Matrix([x, y]))
    
    start_distance = Rational(random.randint(0, 5))
    end_distance = start_distance + Rational(random.randint(10, 25))
    orientation = Orientation()  # Identity for simplicity
    position = Matrix([Rational(random.randint(-30, 30)), 
                      Rational(random.randint(-30, 30)), 
                      Rational(random.randint(-30, 30))])
    
    transform = Transform(position=position, orientation=orientation)
    return ConvexPolygonExtrusion(points=vertices, start_distance=start_distance,
                                  end_distance=end_distance,
                                  transform=transform)


def generate_prism_boundary_points(prism):
    """Generate points on the boundary of a prism: corners, edge midpoints, face centers."""
    points = []
    hw = prism.size[0] / Integer(2)  # half width
    hh = prism.size[1] / Integer(2)  # half height
    
    # Extract orientation axes
    width_dir = Matrix([prism.transform.orientation.matrix[0, 0],
                       prism.transform.orientation.matrix[1, 0],
                       prism.transform.orientation.matrix[2, 0]])
    height_dir = Matrix([prism.transform.orientation.matrix[0, 1],
                        prism.transform.orientation.matrix[1, 1],
                        prism.transform.orientation.matrix[2, 1]])
    length_dir = Matrix([prism.transform.orientation.matrix[0, 2],
                        prism.transform.orientation.matrix[1, 2],
                        prism.transform.orientation.matrix[2, 2]])
    
    # 8 corners (if finite)
    if prism.start_distance is not None and prism.end_distance is not None:
        for z in [prism.start_distance, prism.end_distance]:
            for x_sign in [-1, 1]:
                for y_sign in [-1, 1]:
                    point = (prism.transform.position + 
                            width_dir * (x_sign * hw) + 
                            height_dir * (y_sign * hh) + 
                            length_dir * z)
                    points.append(point)
    
    # 6 face centers (if finite)
    if prism.start_distance is not None and prism.end_distance is not None:
        z_mid = (prism.start_distance + prism.end_distance) / Integer(2)
        # Top and bottom faces
        points.append(prism.transform.position + length_dir * prism.start_distance)
        points.append(prism.transform.position + length_dir * prism.end_distance)
        # Side faces
        points.append(prism.transform.position + width_dir * hw + length_dir * z_mid)
        points.append(prism.transform.position + width_dir * (-hw) + length_dir * z_mid)
        points.append(prism.transform.position + height_dir * hh + length_dir * z_mid)
        points.append(prism.transform.position + height_dir * (-hh) + length_dir * z_mid)
    
    return points


def generate_prism_non_boundary_points(prism):
    """Generate points NOT on the boundary of a prism: center and far-away point."""
    points = []
    
    # Center point (if finite)
    if prism.start_distance is not None and prism.end_distance is not None:
        length_dir = Matrix([prism.transform.orientation.matrix[0, 2],
                            prism.transform.orientation.matrix[1, 2],
                            prism.transform.orientation.matrix[2, 2]])
        z_mid = (prism.start_distance + prism.end_distance) / Integer(2)
        points.append(prism.transform.position + length_dir * z_mid)
    
    # Far-away point
    points.append(prism.transform.position + Matrix([Rational(1000), Rational(1000), Rational(1000)]))
    
    return points


def generate_cylinder_boundary_points(cylinder):
    """Generate points on cylinder boundary: caps, surface, and round edges."""
    points = []
    
    # Normalize axis
    axis = cylinder.axis_direction / cylinder.axis_direction.norm()
    
    # Find perpendicular vectors for constructing points on circles
    if abs(axis[0]) < Rational(1, 2):
        perp1 = Matrix([Integer(1), Integer(0), Integer(0)])
    else:
        perp1 = Matrix([Integer(0), Integer(1), Integer(0)])
    
    perp1 = perp1 - axis * (perp1.T * axis)[0, 0]
    perp1 = perp1 / perp1.norm()
    perp2 = axis.cross(perp1)
    perp2 = perp2 / perp2.norm()
    
    # Cap centers (if finite)
    if cylinder.start_distance is not None:
        points.append(cylinder.position + axis * cylinder.start_distance)
    if cylinder.end_distance is not None:
        points.append(cylinder.position + axis * cylinder.end_distance)
    
    # Points on cap circumferences (round edges) - 8 points per cap
    for angle_frac in [0, Rational(1, 4), Rational(1, 2), Rational(3, 4)]:
        angle = radians(Integer(2) * pi * angle_frac)
        radial = cylinder.radius * (perp1 * cos(angle) + perp2 * sin(angle))
        
        if cylinder.start_distance is not None:
            points.append(cylinder.position + axis * cylinder.start_distance + radial)
        if cylinder.end_distance is not None:
            points.append(cylinder.position + axis * cylinder.end_distance + radial)
    
    # Points on cylindrical surface (if finite)
    if cylinder.start_distance is not None and cylinder.end_distance is not None:
        z_mid = (cylinder.start_distance + cylinder.end_distance) / Integer(2)
        for angle_frac in [0, Rational(1, 4), Rational(1, 2), Rational(3, 4)]:
            angle = radians(Integer(2) * pi * angle_frac)
            radial = cylinder.radius * (perp1 * cos(angle) + perp2 * sin(angle))
            points.append(cylinder.position + axis * z_mid + radial)
    
    return points


def generate_cylinder_non_boundary_points(cylinder):
    """Generate points NOT on cylinder boundary: center and far-away point."""
    points = []
    
    # Center point (if finite)
    if cylinder.start_distance is not None and cylinder.end_distance is not None:
        axis = cylinder.axis_direction / cylinder.axis_direction.norm()
        z_mid = (cylinder.start_distance + cylinder.end_distance) / Integer(2)
        points.append(cylinder.position + axis * z_mid)
    
    # Far-away point
    points.append(cylinder.position + Matrix([Rational(1000), Rational(1000), Rational(1000)]))
    
    return points


def generate_halfspace_boundary_points(halfspace):
    """Generate points on the half-plane boundary."""
    points = []
    
    # Plane origin
    points.append(halfspace.normal * halfspace.offset)
    
    # Find two perpendicular vectors in the plane
    normal = halfspace.normal / halfspace.normal.norm()
    if abs(normal[0]) < Rational(1, 2):
        perp1 = Matrix([Integer(1), Integer(0), Integer(0)])
    else:
        perp1 = Matrix([Integer(0), Integer(1), Integer(0)])
    
    perp1 = perp1 - normal * (perp1.T * normal)[0, 0]
    perp1 = perp1 / perp1.norm()
    perp2 = normal.cross(perp1)
    perp2 = perp2 / perp2.norm()
    
    # Random points on the plane
    plane_origin = halfspace.normal * halfspace.offset
    for i in range(5):
        offset_x = Rational(random.randint(-20, 20))
        offset_y = Rational(random.randint(-20, 20))
        points.append(plane_origin + perp1 * offset_x + perp2 * offset_y)
    
    return points


def generate_halfspace_non_boundary_points(halfspace):
    """Generate points NOT on half-plane boundary: points on both sides of plane."""
    points = []
    normal_normalized = halfspace.normal / halfspace.normal.norm()
    plane_origin = halfspace.normal * halfspace.offset
    
    # Point on positive side (in direction of normal, inside half-plane)
    points.append(plane_origin + normal_normalized * Rational(10))
    
    # Point on negative side (opposite to normal, outside half-plane)
    points.append(plane_origin - normal_normalized * Rational(10))
    
    return points


def generate_convex_polygon_boundary_points(extrusion):
    """Generate points on convex polygon extrusion boundary: vertices, edges, faces."""
    points = []
    
    # Only generate boundary points for finite extrusions
    if extrusion.start_distance is None or extrusion.end_distance is None:
        return points
    
    # All vertices at z=start_distance and z=end_distance
    for vertex_2d in extrusion.points:
        # Bottom (z=start_distance)
        point_local = Matrix([vertex_2d[0], vertex_2d[1], extrusion.start_distance])
        point_global = extrusion.transform.position + extrusion.transform.orientation.matrix * point_local
        points.append(point_global)
        
        # Top (z=end_distance)
        point_local = Matrix([vertex_2d[0], vertex_2d[1], extrusion.end_distance])
        point_global = extrusion.transform.position + extrusion.transform.orientation.matrix * point_local
        points.append(point_global)
    
    # Face centers on top and bottom
    if len(extrusion.points) > 0:
        # Calculate centroid
        centroid_x = sum(p[0] for p in extrusion.points) / len(extrusion.points)
        centroid_y = sum(p[1] for p in extrusion.points) / len(extrusion.points)
        
        # Bottom face center
        point_local = Matrix([centroid_x, centroid_y, extrusion.start_distance])
        point_global = extrusion.transform.position + extrusion.transform.orientation.matrix * point_local
        points.append(point_global)
        
        # Top face center
        point_local = Matrix([centroid_x, centroid_y, extrusion.end_distance])
        point_global = extrusion.transform.position + extrusion.transform.orientation.matrix * point_local
        points.append(point_global)
    
    # Edge midpoints (on vertical edges)
    for vertex_2d in extrusion.points:
        z_mid = (extrusion.start_distance + extrusion.end_distance) / Integer(2)
        point_local = Matrix([vertex_2d[0], vertex_2d[1], z_mid])
        point_global = extrusion.transform.position + extrusion.transform.orientation.matrix * point_local
        points.append(point_global)
    
    return points


def generate_convex_polygon_non_boundary_points(extrusion):
    """Generate points NOT on convex polygon boundary: interior and far-away points."""
    points = []
    
    # Only generate interior points for finite extrusions
    if extrusion.start_distance is not None and extrusion.end_distance is not None:
        # Interior point at mid-height
        if len(extrusion.points) > 0:
            centroid_x = sum(p[0] for p in extrusion.points) / len(extrusion.points)
            centroid_y = sum(p[1] for p in extrusion.points) / len(extrusion.points)
            z_mid = (extrusion.start_distance + extrusion.end_distance) / Integer(2)
            
            point_local = Matrix([centroid_x, centroid_y, z_mid])
            point_global = extrusion.transform.position + extrusion.transform.orientation.matrix * point_local
            points.append(point_global)
    
    # Far-away point
    points.append(extrusion.transform.position + Matrix([Rational(1000), Rational(1000), Rational(1000)]))
    
    return points


class TestConstructors:
    """Test the RectangularPrism and Cylinder constructors."""
    
    def test_prism_constructor_finite(self):
        """Test creating a finite prism."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        
        assert prism.size == size
        assert prism.transform.orientation == orientation
        assert prism.start_distance == 0
        assert prism.end_distance == Integer(10)
    
    def test_prism_constructor_semi_infinite(self):
        """Test creating a semi-infinite prism."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), end_distance=10)
        
        assert prism.start_distance is None
        assert prism.end_distance == Integer(10)
    
    def test_prism_constructor_infinite(self):
        """Test creating an infinite prism."""
        size = Matrix([Integer(4), Integer(6)])
        prism = RectangularPrism(size=size, transform=Transform.identity())
        
        assert prism.start_distance is None
        assert prism.end_distance is None
    
    def test_cylinder_constructor_finite(self):
        """Test creating a finite cylinder."""
        axis = Matrix([Integer(1), Integer(0), Integer(0)])
        radius = Rational(5)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=-5, end_distance=5)
        
        assert cylinder.axis_direction == axis
        assert cylinder.radius == radius
        assert cylinder.start_distance == -5
        assert cylinder.end_distance == 5
    
    def test_cylinder_constructor_infinite(self):
        """Test creating an infinite cylinder."""
        axis = Matrix([Integer(1), Integer(0), Integer(0)])
        radius = Rational(5)
        cylinder = Cylinder(axis_direction=axis, radius=radius)
        
        assert cylinder.start_distance is None
        assert cylinder.end_distance is None


class TestPrismPositionMethods:
    """Test RectangularPrism get_bottom_position and get_top_position methods."""
    
    def test_get_bottom_position_finite_prism(self):
        """Test get_bottom_position on a finite prism."""
        # Create a prism with identity orientation
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        position = Matrix([Integer(10), Integer(20), Integer(30)])
        start_distance = Rational(5)
        end_distance = Rational(15)
        transform = Transform(position=position, orientation=orientation)
        prism = RectangularPrism(size=size, transform=transform, 
                     start_distance=start_distance, end_distance=end_distance)
        
        # Bottom position should be position - (0, 0, start_distance) in local frame
        # With identity orientation, this is position - Matrix([0, 0, start_distance])
        bottom = prism.get_bottom_position()
        expected_bottom = Matrix([Integer(10), Integer(20), Integer(25)])  # 30 - 5 = 25
        assert bottom.equals(expected_bottom), f"Expected {expected_bottom.T}, got {bottom.T}"
    
    def test_get_top_position_finite_prism(self):
        """Test get_top_position on a finite prism."""
        # Create a prism with identity orientation
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        position = Matrix([Integer(10), Integer(20), Integer(30)])
        start_distance = Rational(5)
        end_distance = Rational(15)
        transform = Transform(position=position, orientation=orientation)
        prism = RectangularPrism(size=size, transform=transform, 
                     start_distance=start_distance, end_distance=end_distance)
        
        # Top position should be position + (0, 0, end_distance) in local frame
        # With identity orientation, this is position + Matrix([0, 0, end_distance])
        top = prism.get_top_position()
        expected_top = Matrix([Integer(10), Integer(20), Integer(45)])  # 30 + 15 = 45
        assert top.equals(expected_top), f"Expected {expected_top.T}, got {top.T}"
    
    def test_get_bottom_position_rotated_prism(self):
        """Test get_bottom_position on a rotated prism."""
        # Create a prism with a specific rotation
        # Rotation matrix: local X -> global Z, local Y -> global Y, local Z -> global X
        # This is: [[0, 0, 1], [0, 1, 0], [1, 0, 0]]
        size = Matrix([Integer(4), Integer(6)])
        rotation = Matrix([
            [0, 0, 1],   # X column: local X maps to global Z
            [0, 1, 0],   # Y column: local Y maps to global Y  
            [1, 0, 0]    # Z column: local Z maps to global X
        ])
        orientation = Orientation(rotation)
        position = Matrix([Integer(10), Integer(20), Integer(30)])
        start_distance = Rational(5)
        end_distance = Rational(15)
        transform = Transform(position=position, orientation=orientation)
        prism = RectangularPrism(size=size, transform=transform,
                     start_distance=start_distance, end_distance=end_distance)
        
        # With this rotation: local Z becomes global X
        # So bottom should be position - rotation * [0, 0, 5]
        # rotation * [0, 0, 5] = 5 * (third column) = 5 * [1, 0, 0] = [5, 0, 0]
        # position - [5, 0, 0] = [10, 20, 30] - [5, 0, 0] = [5, 20, 30]
        bottom = prism.get_bottom_position()
        expected_bottom = Matrix([Integer(5), Integer(20), Integer(30)])
        assert bottom.equals(expected_bottom), f"Expected {expected_bottom.T}, got {bottom.T}"
    
    def test_get_bottom_position_infinite_prism_raises_error(self):
        """Test that get_bottom_position raises error for infinite prism."""
        size = Matrix([Integer(4), Integer(6)])
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=None, end_distance=10)
        
        with pytest.raises(ValueError, match="infinite prism"):
            prism.get_bottom_position()
    
    def test_get_top_position_infinite_prism_raises_error(self):
        """Test that get_top_position raises error for infinite prism."""
        size = Matrix([Integer(4), Integer(6)])
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=None)
        
        with pytest.raises(ValueError, match="infinite prism"):
            prism.get_top_position()


class TestHalfspaceContainsPoint:
    """Test HalfSpace contains_point and is_point_on_boundary methods."""
    
    def test_halfspace_contains_point_on_positive_side(self):
        """Test that a point on the positive side is contained."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal, offset)
        
        # Point at z=10 (above the plane at z=5)
        point = Matrix([Integer(0), Integer(0), Integer(10)])
        assert halfspace.contains_point(point) == True
    
    def test_halfspace_contains_point_on_boundary(self):
        """Test that a point on the boundary is contained."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal, offset)
        
        # Point at z=5 (on the plane)
        point = Matrix([Integer(1), Integer(2), Integer(5)])
        assert halfspace.contains_point(point) == True
    
    def test_halfspace_contains_point_on_negative_side(self):
        """Test that a point on the negative side is not contained."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal, offset)
        
        # Point at z=0 (below the plane at z=5)
        point = Matrix([Integer(0), Integer(0), Integer(0)])
        assert halfspace.contains_point(point) == False
    
    def test_halfspace_is_point_on_boundary(self):
        """Test boundary detection."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal, offset)
        
        # Point on boundary
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == True
        assert halfspace.is_point_on_boundary(Matrix([Integer(1), Integer(1), Integer(5)])) == True
        
        # Point not on boundary
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(6)])) == False
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(4)])) == False
    
    def test_halfspace_diagonal_normal(self):
        """Test half-plane with diagonal normal."""
        normal = Matrix([Integer(1), Integer(1), Integer(1)])
        offset = Rational(0)
        halfspace = HalfSpace(normal, offset)
        
        # Point where x+y+z > 0
        assert halfspace.contains_point(Matrix([Integer(1), Integer(0), Integer(0)])) == True
        assert halfspace.contains_point(Matrix([Integer(1), Integer(1), Integer(1)])) == True
        
        # Point where x+y+z = 0
        assert halfspace.contains_point(Matrix([Integer(0), Integer(0), Integer(0)])) == True
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True
        
        # Point where x+y+z < 0
        assert halfspace.contains_point(Matrix([Integer(-1), Integer(0), Integer(0)])) == False


class TestPrismContainsPoint:
    """Test RectangularPrism contains_point and is_point_on_boundary methods."""
    
    def test_prism_contains_point_inside(self):
        """Test that a point inside the prism is contained."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        
        # Point inside: within ±2 in x, ±3 in y, 0-10 in z
        point = Matrix([Integer(0), Integer(0), Integer(5)])
        assert prism.contains_point(point) == True
    
    def test_prism_contains_point_on_face(self):
        """Test that a point on a face is contained."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        
        # Point on face (x = 2, which is half-width)
        point = Matrix([Integer(2), Integer(0), Integer(5)])
        assert prism.contains_point(point) == True
    
    def test_prism_contains_point_outside(self):
        """Test that a point outside the prism is not contained."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        
        # Point outside in x direction
        point = Matrix([Integer(3), Integer(0), Integer(5)])
        assert prism.contains_point(point) == False
        
        # Point outside in z direction
        point = Matrix([Integer(0), Integer(0), Integer(11)])
        assert prism.contains_point(point) == False
    
    def test_prism_is_point_on_boundary_face(self, symbolic_mode):
        """Test boundary detection on prism faces."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        
        # On width face (x = ±2)
        assert prism.is_point_on_boundary(Matrix([Integer(2), Integer(0), Integer(5)])) == True
        assert prism.is_point_on_boundary(Matrix([-2, 0, 5])) == True
        
        # On height face (y = ±3)
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(3), Integer(5)])) == True
        assert prism.is_point_on_boundary(Matrix([0, -3, 5])) == True
        
        # On end caps (z = 0 or 10)
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(10)])) == True
    
    def test_prism_is_point_on_boundary_inside(self):
        """Test that interior points are not on boundary."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        
        # Interior point
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
    
    def test_prism_semi_infinite_contains(self):
        """Test semi-infinite prism containment."""
        size = Matrix([Integer(4), Integer(6)])
        orientation = Orientation()  # Identity orientation
        prism = RectangularPrism(size=size, transform=Transform.identity(), end_distance=10)  # Infinite in negative direction
        
        # Point at z = -100 should be contained
        assert prism.contains_point(Matrix([Integer(0), Integer(0), Integer(-100)])) == True
        
        # Point at z = 100 should not be contained
        assert prism.contains_point(Matrix([Integer(0), Integer(0), Integer(100)])) == False


class TestCylinderContainsPoint:
    """Test Cylinder contains_point and is_point_on_boundary methods."""
    
    def test_cylinder_contains_point_inside(self):
        """Test that a point inside the cylinder is contained."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=0, end_distance=10)
        
        # Point inside: radial distance < 3, z in [0, 10]
        point = Matrix([Integer(1), Integer(1), Integer(5)])
        assert cylinder.contains_point(point) == True
    
    def test_cylinder_contains_point_on_surface(self):
        """Test that a point on the cylindrical surface is contained."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=0, end_distance=10)
        
        # Point on surface: radial distance = 3
        point = Matrix([Integer(3), Integer(0), Integer(5)])
        assert cylinder.contains_point(point) == True
    
    def test_cylinder_contains_point_outside_radially(self):
        """Test that a point outside radially is not contained."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=0, end_distance=10)
        
        # Point outside: radial distance > 3
        point = Matrix([Integer(4), Integer(0), Integer(5)])
        assert cylinder.contains_point(point) == False
    
    def test_cylinder_contains_point_outside_axially(self):
        """Test that a point outside axially is not contained."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=0, end_distance=10)
        
        # Point outside in z direction
        point = Matrix([Integer(0), Integer(0), Integer(11)])
        assert cylinder.contains_point(point) == False
    
    def test_cylinder_is_point_on_boundary_surface(self, symbolic_mode):
        """Test boundary detection on cylindrical surface."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=0, end_distance=10)
        
        # On cylindrical surface (radial distance = 3)
        assert cylinder.is_point_on_boundary(Matrix([Integer(3), Integer(0), Integer(5)])) == True
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(3), Integer(5)])) == True
    
    def test_cylinder_is_point_on_boundary_end_caps(self, symbolic_mode):
        """Test boundary detection on cylinder end caps."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=0, end_distance=10)
        
        # On end caps
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(10)])) == True
        assert cylinder.is_point_on_boundary(Matrix([Integer(1), Integer(1), Integer(0)])) == True
    
    def test_cylinder_is_point_on_boundary_inside(self):
        """Test that interior points are not on boundary."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, start_distance=0, end_distance=10)
        
        # Interior point
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
        assert cylinder.is_point_on_boundary(Matrix([Integer(1), Integer(0), Integer(5)])) == False
    
    def test_cylinder_semi_infinite_contains(self):
        """Test semi-infinite cylinder containment."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, end_distance=10)  # Infinite in negative direction
        
        # Point at z = -100 should be contained (if within radius)
        assert cylinder.contains_point(Matrix([Integer(1), Integer(0), Integer(-100)])) == True
        
        # Point at z = 100 should not be contained
        assert cylinder.contains_point(Matrix([Integer(1), Integer(0), Integer(100)])) == False


class TestUnionContainsPoint:
    """Test SolidUnion contains_point and is_point_on_boundary methods."""
    
    def test_union_contains_point_in_first_child(self):
        """Test that a point in the first child is contained."""
        size = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        prism1 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=5)
        prism2 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=10, end_distance=15)
        
        union = SolidUnion([prism1, prism2])
        
        # Point in first prism
        assert union.contains_point(Matrix([Integer(0), Integer(0), Integer(3)])) == True
    
    def test_union_contains_point_in_second_child(self):
        """Test that a point in the second child is contained."""
        size = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        prism1 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=5)
        prism2 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=10, end_distance=15)
        
        union = SolidUnion([prism1, prism2])
        
        # Point in second prism
        assert union.contains_point(Matrix([Integer(0), Integer(0), Integer(12)])) == True
    
    def test_union_contains_point_outside_all(self):
        """Test that a point outside all children is not contained."""
        size = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        prism1 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=5)
        prism2 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=10, end_distance=15)
        
        union = SolidUnion([prism1, prism2])
        
        # Point between the two prisms
        assert union.contains_point(Matrix([Integer(0), Integer(0), Integer(7)])) == False
    
    def test_union_is_point_on_boundary(self, symbolic_mode):
        """Test boundary detection for union."""
        size = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        prism1 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=5)
        prism2 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=10, end_distance=15)
        
        union = SolidUnion([prism1, prism2])
        
        # Point on boundary of first prism
        assert union.is_point_on_boundary(Matrix([Integer(1), Integer(0), Integer(3)])) == True
        
        # Point on boundary of second prism
        assert union.is_point_on_boundary(Matrix([Integer(1), Integer(0), Integer(12)])) == True
    
    def test_union_is_point_on_boundary_interior(self):
        """Test that interior points are not on boundary."""
        size = Matrix([Integer(4), Integer(4)])
        orientation = Orientation()
        
        prism1 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        prism2 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=5, end_distance=15)
        
        union = SolidUnion([prism1, prism2])
        
        # Point strictly inside first prism (not on boundary)
        assert union.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(3)])) == False
        
        # Point strictly inside second prism (not on boundary)
        assert union.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(12)])) == False
    
    def test_union_is_point_on_boundary_overlapping(self, symbolic_mode):
        """Test boundary detection when prisms overlap."""
        size = Matrix([Integer(4), Integer(4)])
        orientation = Orientation()
        
        # Two overlapping prisms
        prism1 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=10)
        prism2 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=5, end_distance=15)
        
        union = SolidUnion([prism1, prism2])
        
        # Point on outer boundary of union (on prism1 face, not inside prism2)
        assert union.is_point_on_boundary(Matrix([Integer(2), Integer(0), Integer(3)])) == True
        
        # Point on outer boundary of union (on prism2 face, not inside prism1)
        assert union.is_point_on_boundary(Matrix([Integer(2), Integer(0), Integer(12)])) == True
        
        # Point in overlap region is NOT on boundary (it's interior to the union)
        # At z=5, this is inside prism1 and on the start face of prism2
        # Since it's strictly inside prism1, it's not on the union boundary
        assert union.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
    
    def test_union_is_point_on_boundary_outside(self):
        """Test that points outside all children are not on boundary."""
        size = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()
        
        prism1 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=0, end_distance=5)
        prism2 = RectangularPrism(size=size, transform=Transform.identity(), start_distance=10, end_distance=15)
        
        union = SolidUnion([prism1, prism2])
        
        # Point between the two prisms (not on boundary)
        assert union.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(7)])) == False
        
        # Point far outside
        assert union.is_point_on_boundary(Matrix([Integer(10), Integer(10), Integer(10)])) == False


num_random_samples = 10

class TestDifferenceContainsPoint:
    """Test Difference contains_point and is_point_on_boundary methods."""
    
    def test_difference_contains_point_in_base_not_subtracted(self):
        """Test that a point in base but not in subtract is contained."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point in base but outside subtract region
        assert diff.contains_point(Matrix([Integer(4), Integer(4), Integer(5)])) == True
    
    def test_difference_contains_point_subtracted(self):
        """Test that a point in subtract region is not contained."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point in subtract region
        assert diff.contains_point(Matrix([Integer(0), Integer(0), Integer(5)])) == False
    
    def test_difference_contains_point_outside_base(self):
        """Test that a point outside base is not contained."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point outside base
        assert diff.contains_point(Matrix([Integer(10), Integer(10), Integer(5)])) == False
    
    def test_difference_is_point_on_boundary_base(self, symbolic_mode):
        """Test boundary detection on base boundary."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point on base boundary (not in subtract region)
        assert diff.is_point_on_boundary(Matrix([Integer(5), Integer(4), Integer(5)])) == True
    
    def test_difference_is_point_on_boundary_subtract(self, symbolic_mode):
        """Test boundary detection on subtract boundary."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()  # Identity orientation
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point on subtract boundary (creates new boundary in difference)
        # At x=1 (edge of subtract), y=0, z=5
        assert diff.is_point_on_boundary(Matrix([Integer(1), Integer(0), Integer(5)])) == True
    
    def test_difference_is_point_on_boundary_interior(self):
        """Test that interior points are not on boundary."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(2), Integer(2)])
        orientation = Orientation()
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point in base but not on boundary (not near subtract)
        assert diff.is_point_on_boundary(Matrix([Integer(4), Integer(4), Integer(5)])) == False
    
    def test_difference_is_point_on_boundary_strictly_inside_subtract(self):
        """Test that points strictly inside subtract are not contained or on boundary."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(4), Integer(4)])
        orientation = Orientation()
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point strictly inside subtract (not on subtract boundary)
        point = Matrix([Rational(1, 2), Rational(1, 2), 5])
        assert diff.contains_point(point) == False
        assert diff.is_point_on_boundary(point) == False
    
    def test_difference_contains_point_on_subtract_boundary(self, symbolic_mode):
        """Test that points on subtract boundary are contained in the difference."""
        size_base = Matrix([Integer(10), Integer(10)])
        size_subtract = Matrix([Integer(4), Integer(4)])
        orientation = Orientation()
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        subtract = RectangularPrism(size=size_subtract, transform=Transform.identity(), start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract])
        
        # Point on subtract boundary should be contained (forms the cut surface)
        point = Matrix([Integer(2), Integer(0), Integer(5)])  # On width face of subtract
        assert diff.contains_point(point) == True
        assert diff.is_point_on_boundary(point) == True
    
    def test_difference_with_halfspace_boundary(self):
        """Test boundary detection when subtracting with a half-plane."""
        size_base = Matrix([Integer(10), Integer(10)])
        orientation = Orientation()
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        # Half-plane at z=5, normal pointing in +z direction
        half_plane = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=5)
        
        diff = Difference(base, [half_plane])
        
        # Point on half-plane boundary (z=5) should be on difference boundary
        assert diff.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == True
        assert diff.is_point_on_boundary(Matrix([Integer(3), Integer(3), Integer(5)])) == True
        
        # Point strictly below plane (inside difference) should not be on boundary
        assert diff.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(3)])) == False
        
        # Point strictly above plane (removed by difference) should not be contained
        assert diff.contains_point(Matrix([Integer(0), Integer(0), Integer(7)])) == False
    
    def test_difference_multiple_subtracts(self, symbolic_mode):
        """Test boundary detection with multiple subtract objects."""
        size_base = Matrix([Integer(10), Integer(10)])
        orientation = Orientation()
        
        base = RectangularPrism(size=size_base, transform=Transform.identity(), start_distance=0, end_distance=10)
        # Two small prisms to subtract
        subtract1 = RectangularPrism(size=Matrix([Integer(2), Integer(2)]), transform=Transform(position=Matrix([Integer(2), Integer(2), Integer(0)]), orientation=Orientation()), 
                         start_distance=2, end_distance=8)
        subtract2 = RectangularPrism(size=Matrix([Integer(2), Integer(2)]), transform=Transform(position=Matrix([-2, -2, 0]), orientation=Orientation()),
                         start_distance=2, end_distance=8)
        
        diff = Difference(base, [subtract1, subtract2])
        
        # Points on subtract1 boundary
        assert diff.is_point_on_boundary(Matrix([Integer(3), Integer(2), Integer(5)])) == True
        
        # Points on subtract2 boundary
        assert diff.is_point_on_boundary(Matrix([-1, -2, 5])) == True
        
        # Point on base boundary (not near subtracts)
        assert diff.is_point_on_boundary(Matrix([Integer(5), Integer(0), Integer(0)])) == True
    
    def test_difference_nested_differences(self, symbolic_mode):
        """Test boundary detection with nested difference operations."""
        orientation = Orientation()
        
        # Create base prism
        base = RectangularPrism(size=Matrix([Integer(10), Integer(10)]), transform=Transform.identity(), 
                    start_distance=0, end_distance=10)
        
        # Create a subtract prism at the center
        subtract_inner = RectangularPrism(size=Matrix([Integer(2), Integer(2)]), transform=Transform.identity(),
                              start_distance=3, end_distance=7)
        
        # Create a nested difference (prism with hole in center)
        inner_diff = Difference(base, [subtract_inner])
        
        # Now subtract another prism from a different location
        # Place it off to the side so it doesn't overlap with subtract_inner
        subtract_outer = RectangularPrism(size=Matrix([Integer(2), Integer(2)]), transform=Transform(position=Matrix([Integer(4), Integer(0), Integer(0)]), orientation=orientation),
                              start_distance=1, end_distance=9)
        
        outer_diff = Difference(inner_diff, [subtract_outer])
        
        # Point on inner subtract boundary (the central hole)
        # This should still be on boundary in outer_diff
        assert outer_diff.is_point_on_boundary(Matrix([Integer(1), Integer(0), Integer(5)])) == True
        
        # Point on outer subtract boundary (the side hole)
        assert outer_diff.is_point_on_boundary(Matrix([Integer(5), Integer(0), Integer(5)])) == True
        
        # Point in the remaining material (not on any boundary)
        assert outer_diff.is_point_on_boundary(Matrix([Rational(-7, 2), 0, 5])) == False
    
    def test_difference_shape_minus_itself_should_be_empty(self):
        """Test that subtracting a shape from itself results in an empty shape.
        
        This test demonstrates a bug: when you subtract a shape from itself,
        the result should contain NO points (not even boundary points).
        Currently, this fails for points on the boundary.
        """
        orientation = Orientation()
        
        # Create a prism
        prism = RectangularPrism(size=Matrix([Integer(10), Integer(10)]), transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation),
                     start_distance=Rational(0), end_distance=Rational(10))
        
        # Subtract the prism from itself
        empty_diff = Difference(prism, [prism])
        
        # Test interior points - should NOT be contained
        interior_points = [
            Matrix([Integer(0), Integer(0), Integer(5)]),           # Center
            Matrix([Integer(1), Integer(1), Integer(5)]),           # Off-center interior
            Matrix([Rational(-2), 2, 3]) # Another interior point
        ]
        
        for point in interior_points:
            assert empty_diff.contains_point(point) == False, \
                f"Interior point {point.T} should NOT be in empty difference"
        
        # Test boundary points - should NOT be contained (THIS WILL FAIL)
        boundary_points = [
            Matrix([Integer(5), Integer(0), Integer(5)]),     # On width face
            Matrix([Integer(0), Integer(5), Integer(5)]),     # On height face
            Matrix([Integer(0), Integer(0), Integer(0)]),     # On bottom face
            Matrix([Integer(0), Integer(0), Integer(10)]),    # On top face
            Matrix([Integer(5), Integer(5), Integer(0)]),     # Corner on bottom
            Matrix([Integer(5), Integer(5), Integer(10)]),    # Corner on top
        ]
        
        for point in boundary_points:
            # This assertion is EXPECTED TO FAIL - that's the bug we're testing for
            assert empty_diff.contains_point(point) == False, \
                f"Boundary point {point.T} should NOT be in empty difference"
        
        # Test exterior points - should NOT be contained
        exterior_points = [
            Matrix([Integer(20), Integer(0), Integer(5)]),      # Outside in x
            Matrix([0, 20, 5]),      # Outside in y
            Matrix([0, 0, 20]),      # Outside in z
            Matrix([100, 100, 100])  # Far away
        ]
        
        for point in exterior_points:
            assert empty_diff.contains_point(point) == False, \
                f"Exterior point {point.T} should NOT be in empty difference"
    
    def test_difference_two_prisms_sharing_one_plane_no_overlap(self, symbolic_mode):
        """Test difference with two prisms that share one plane but don't overlap.
        
        When two prisms just touch at a shared face (no volume overlap),
        their outward normals point in opposite directions. The boundary points
        should be included in the difference (dot product <= 0).
        """
        orientation = Orientation()
        
        # Create prism A: from z=0 to z=10
        prismA = RectangularPrism(
            size=Matrix([Integer(10), Integer(10)]), 
            transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation),
            start_distance=Rational(0), 
            end_distance=Rational(10)
        )
        
        # Create prism B: from z=10 to z=20 (shares the z=10 plane with A)
        prismB = RectangularPrism(
            size=Matrix([Integer(10), Integer(10)]), 
            transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation),
            start_distance=Rational(10), 
            end_distance=Rational(20)
        )
        
        # Create difference: A - B
        diff = Difference(prismA, [prismB])
        
        # Test interior points of A (not near shared boundary) - should be contained
        assert diff.contains_point(Matrix([Integer(0), Integer(0), Integer(5)])) == True
        assert diff.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
        
        # Test points on the shared plane (z=10)
        # The outward normals point in opposite directions (dot < 0),
        # so these points should be included in the difference
        shared_plane_points = [
            Matrix([Integer(0), Integer(0), Integer(10)]),  # Center of shared face
            Matrix([3, 3, 10]),  # Point on shared face
            Matrix([5, 0, 10]),  # Edge of prism A's boundary on shared plane
        ]
        
        for point in shared_plane_points:
            # The point is on boundary of both base and subtract
            assert prismA.is_point_on_boundary(point) == True
            assert prismB.is_point_on_boundary(point) == True
            
            # Check the normals point in opposite directions
            normalA = prismA.get_outward_normal(point)
            normalB = prismB.get_outward_normal(point)
            assert normalA is not None
            assert normalB is not None
            dot_product = (normalA.T * normalB)[0, 0]
            assert dot_product < 0, f"Normals should point in opposite directions at {point.T}"
            
            # In the difference, since dot product < 0, points should be included
            assert diff.contains_point(point) == True, \
                f"Point {point.T} on shared boundary should be in difference (dot={dot_product})"
            assert diff.is_point_on_boundary(point) == True, \
                f"Point {point.T} should be on boundary of difference"
        
        # Test points in prism B (z > 10) - should NOT be in the difference
        assert diff.contains_point(Matrix([0, 0, 15])) == False
        
        # Test points on A's other boundaries - should be on boundary
        assert diff.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True  # Bottom face
        assert diff.is_point_on_boundary(Matrix([Integer(5), Integer(0), Integer(5)])) == True  # Side face


class TestConvexPolygonExtrusion:
    """Test ConvexPolygonExtrusion class."""
    
    def test_constructor_square(self):
        """Test creating a square extrusion."""
        # Square with corners at (±1, ±1)
        points = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()  # Identity orientation
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance, 
                                          end_distance=end_distance, transform=Transform.identity())
        
        assert extrusion.points == points
        assert extrusion.start_distance == start_distance
        assert extrusion.end_distance == end_distance
        assert extrusion.transform.orientation == orientation
    
    def test_is_valid_enough_points(self):
        """Test that is_valid requires at least 3 points."""
        # Triangle (valid)
        points_valid = [
            Matrix([0, 0]),
            Matrix([1, 0]),
            Matrix([0, 1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(5)
        orientation = Orientation()
        
        extrusion_valid = ConvexPolygonExtrusion(points=points_valid, start_distance=start_distance,
                                                 end_distance=end_distance, transform=Transform.identity())
        assert extrusion_valid.is_valid() == True
        
        # Only 2 points (invalid)
        points_invalid = [
            Matrix([0, 0]),
            Matrix([1, 0])
        ]
        extrusion_invalid = ConvexPolygonExtrusion(points=points_invalid, start_distance=start_distance,
                                                   end_distance=end_distance, transform=Transform.identity())
        assert extrusion_invalid.is_valid() == False
    
    def test_is_valid_distance_configuration(self):
        """Test that is_valid requires valid distance configuration."""
        points = [
            Matrix([0, 0]),
            Matrix([1, 0]),
            Matrix([0, 1])
        ]
        orientation = Orientation()
        
        # Valid: end > start (valid)
        extrusion_valid = ConvexPolygonExtrusion(points=points, start_distance=Rational(0),
                                                 end_distance=Rational(5), transform=Transform.identity())
        assert extrusion_valid.is_valid() == True
        
        # Invalid: end = start (no volume)
        extrusion_zero = ConvexPolygonExtrusion(points=points, start_distance=Rational(5),
                                               end_distance=Rational(5), transform=Transform.identity())
        assert extrusion_zero.is_valid() == False
        
        # Invalid: end < start
        extrusion_negative = ConvexPolygonExtrusion(points=points, start_distance=Rational(5),
                                                    end_distance=Rational(0), transform=Transform.identity())
        assert extrusion_negative.is_valid() == False
        
        # Valid: infinite in both directions
        extrusion_infinite = ConvexPolygonExtrusion(points=points, start_distance=None,
                                                    end_distance=None, transform=Transform.identity())
        assert extrusion_infinite.is_valid() == True
    
    def test_is_valid_convex_polygon(self):
        """Test that is_valid accepts convex polygons."""
        orientation = Orientation()
        start_distance = Rational(0)
        end_distance = Rational(5)
        
        # Convex square (counter-clockwise)
        points_ccw = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        extrusion_ccw = ConvexPolygonExtrusion(points=points_ccw, start_distance=start_distance,
                                               end_distance=end_distance, transform=Transform.identity())
        assert extrusion_ccw.is_valid() == True
        
        # Convex square (clockwise)
        points_cw = [
            Matrix([1, 1]),
            Matrix([1, -1]),
            Matrix([-1, -1]),
            Matrix([-1, 1])
        ]
        extrusion_cw = ConvexPolygonExtrusion(points=points_cw, start_distance=start_distance,
                                              end_distance=end_distance, transform=Transform.identity())
        assert extrusion_cw.is_valid() == True
        
        # Convex hexagon
        points_hex = [
            Matrix([2, 0]),
            Matrix([1, sqrt(3)]),
            Matrix([-1, sqrt(3)]),
            Matrix([-2, 0]),
            Matrix([-1, -sqrt(3)]),
            Matrix([1, -sqrt(3)])
        ]
        extrusion_hex = ConvexPolygonExtrusion(points=points_hex, start_distance=start_distance,
                                               end_distance=end_distance, transform=Transform.identity())
        assert extrusion_hex.is_valid() == True
    
    def test_is_valid_non_convex_polygon(self):
        """Test that is_valid rejects non-convex (concave) polygons."""
        orientation = Orientation()
        
        # Non-convex polygon (indented square - concave)
        # Makes an arrow shape pointing right
        points_concave = [
            Matrix([0, 2]),
            Matrix([2, 0]),
            Matrix([0, -2]),
            Matrix([1, 0])  # This point makes it concave
        ]
        extrusion_concave = ConvexPolygonExtrusion(points=points_concave, start_distance=Rational(0),
                                                   end_distance=Rational(5), transform=Transform.identity())
        assert extrusion_concave.is_valid() == False
    
    def test_is_valid_collinear_points(self):
        """Test that is_valid rejects collinear points."""
        orientation = Orientation()
        
        # All points on a line
        points_collinear = [
            Matrix([0, 0]),
            Matrix([1, 0]),
            Matrix([2, 0])
        ]
        extrusion_collinear = ConvexPolygonExtrusion(points=points_collinear, start_distance=Rational(0),
                                                     end_distance=Rational(5), transform=Transform.identity())
        assert extrusion_collinear.is_valid() == False
    
    def test_contains_point_inside_square(self):
        """Test that a point inside a square extrusion is contained."""
        # Unit square centered at origin
        points = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Point inside
        assert extrusion.contains_point(Matrix([Integer(0), Integer(0), Integer(5)])) == True
    
    def test_contains_point_on_face_square(self):
        """Test that a point on a face is contained."""
        points = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Point on top face (z = end_distance)
        assert extrusion.contains_point(Matrix([Integer(0), Integer(0), Integer(10)])) == True
        
        # Point on bottom face (z = start_distance)
        assert extrusion.contains_point(Matrix([Integer(0), Integer(0), Integer(0)])) == True
    
    def test_contains_point_outside_square(self):
        """Test that a point outside is not contained."""
        points = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Outside in XY plane
        assert extrusion.contains_point(Matrix([Integer(2), Integer(0), Integer(5)])) == False
        
        # Outside in Z direction
        assert extrusion.contains_point(Matrix([Integer(0), Integer(0), Integer(11)])) == False
        assert extrusion.contains_point(Matrix([0, 0, -1])) == False
    
    def test_contains_point_triangle(self):
        """Test containment for a triangular extrusion."""
        # Right triangle with vertices at origin, (1,0), (0,1)
        points = [
            Matrix([0, 0]),
            Matrix([1, 0]),
            Matrix([0, 1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(5)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Point inside triangle
        assert extrusion.contains_point(Matrix([Rational(1, 4), Rational(1, 4), Rational(5, 2)])) == True
        
        # Point outside triangle but in XY bounding box
        assert extrusion.contains_point(Matrix([Rational(3, 4), Rational(3, 4), Rational(5, 2)])) == False
    
    def test_is_point_on_boundary_top_bottom(self):
        """Test boundary detection on top and bottom faces."""
        points = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # On bottom face (z = start_distance)
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True
        
        # On top face (z = end_distance)
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(10)])) == True
    
    def test_is_point_on_boundary_side_face(self):
        """Test boundary detection on side faces."""
        points = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # On edge at x=1 (right edge)
        assert extrusion.is_point_on_boundary(Matrix([Integer(1), Integer(0), Integer(5)])) == True
        
        # On edge at y=-1 (bottom edge)
        assert extrusion.is_point_on_boundary(Matrix([0, -1, 5])) == True
    
    def test_is_point_on_boundary_inside(self):
        """Test that interior points are not on boundary."""
        points = [
            Matrix([1, 1]),
            Matrix([-1, 1]),
            Matrix([-1, -1]),
            Matrix([1, -1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Interior point
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
    
    def test_repr(self):
        """Test string representation."""
        points = [
            Matrix([0, 0]),
            Matrix([1, 0]),
            Matrix([0, 1])
        ]
        start_distance = Rational(0)
        end_distance = Rational(5)
        orientation = Orientation()
        
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        repr_str = repr(extrusion)
        assert "ConvexPolygonExtrusion" in repr_str
        assert "3 points" in repr_str
        assert "5" in repr_str


class TestBoundaryDetectionComprehensive:
    """Comprehensive tests for is_point_on_boundary across all CSG shapes."""
    
    # ========================================================================
    # RectangularPrism Boundary Tests
    # ========================================================================
    
    def test_prism_all_corners_on_boundary(self, symbolic_mode):
        """Test that all 8 corners of a finite prism are on the boundary."""
        size = Matrix([Rational(4), Rational(6)])
        orientation = Orientation()
        prism = RectangularPrism(size=size, transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation), start_distance=Rational(0), end_distance=Rational(10))
        
        # Generate all 8 corners
        hw, hh = Rational(2), Rational(3)
        corners = []
        for z in [Rational(0), Rational(10)]:
            for x in [-hw, hw]:
                for y in [-hh, hh]:
                    corners.append(Matrix([x, y, z]))
        
        # All corners should be on boundary
        for corner in corners:
            assert prism.is_point_on_boundary(corner) == True, \
                f"Corner {corner.T} should be on boundary"
    
    def test_prism_edge_points_on_boundary(self, symbolic_mode):
        """Test that points along prism edges are on the boundary."""
        size = Matrix([Rational(4), Rational(6)])
        orientation = Orientation()
        prism = RectangularPrism(size=size, transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation), start_distance=Rational(0), end_distance=Rational(10))
        
        hw, hh = Rational(2), Rational(3)
        
        # Test edge midpoints (12 edges)
        # 4 edges on bottom face
        assert prism.is_point_on_boundary(Matrix([0, hh, 0])) == True
        assert prism.is_point_on_boundary(Matrix([0, -hh, 0])) == True
        assert prism.is_point_on_boundary(Matrix([hw, 0, 0])) == True
        assert prism.is_point_on_boundary(Matrix([-hw, 0, 0])) == True
        
        # 4 edges on top face
        assert prism.is_point_on_boundary(Matrix([0, hh, 10])) == True
        assert prism.is_point_on_boundary(Matrix([0, -hh, 10])) == True
        assert prism.is_point_on_boundary(Matrix([hw, 0, 10])) == True
        assert prism.is_point_on_boundary(Matrix([-hw, 0, 10])) == True
        
        # 4 vertical edges
        assert prism.is_point_on_boundary(Matrix([hw, hh, 5])) == True
        assert prism.is_point_on_boundary(Matrix([hw, -hh, 5])) == True
        assert prism.is_point_on_boundary(Matrix([-hw, hh, 5])) == True
        assert prism.is_point_on_boundary(Matrix([-hw, -hh, 5])) == True
    
    def test_prism_face_centers_on_boundary(self, symbolic_mode):
        """Test that face centers are on the boundary."""
        size = Matrix([Rational(4), Rational(6)])
        orientation = Orientation()
        prism = RectangularPrism(size=size, transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation), start_distance=Rational(0), end_distance=Rational(10))
        
        hw, hh = Rational(2), Rational(3)
        
        # 6 face centers
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True  # Bottom
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(10)])) == True  # Top
        assert prism.is_point_on_boundary(Matrix([hw, 0, 5])) == True  # Right
        assert prism.is_point_on_boundary(Matrix([-hw, 0, 5])) == True  # Left
        assert prism.is_point_on_boundary(Matrix([0, hh, 5])) == True  # Front
        assert prism.is_point_on_boundary(Matrix([0, -hh, 5])) == True  # Back
    
    def test_prism_interior_not_on_boundary(self):
        """Test that interior points are NOT on the boundary."""
        size = Matrix([Rational(4), Rational(6)])
        orientation = Orientation()
        prism = RectangularPrism(size=size, transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation), start_distance=Rational(0), end_distance=Rational(10))
        
        # Center point should not be on boundary
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
        
        # Other interior points
        assert prism.is_point_on_boundary(Matrix([Rational(1), Rational(1), Rational(5)])) == False
    
    def test_prism_exterior_not_on_boundary(self):
        """Test that exterior points are NOT on the boundary."""
        size = Matrix([Rational(4), Rational(6)])
        orientation = Orientation()
        prism = RectangularPrism(size=size, transform=Transform(position=create_v3(Integer(0), Integer(0), Integer(0)), orientation=orientation), start_distance=Rational(0), end_distance=Rational(10))
        
        # Far-away point
        assert prism.is_point_on_boundary(Matrix([100, 100, 100])) == False
        
        # Just outside the prism
        assert prism.is_point_on_boundary(Matrix([Integer(3), Integer(0), Integer(5)])) == False
        assert prism.is_point_on_boundary(Matrix([0, 4, 5])) == False
        assert prism.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(11)])) == False
    
    # ========================================================================
    # Cylinder Boundary Tests
    # ========================================================================
    
    def test_cylinder_cap_centers_on_boundary(self, symbolic_mode):
        """Test that cylinder cap centers are on the boundary."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, 
                           start_distance=Rational(0), end_distance=Rational(10))
        
        # Bottom cap center
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True
        
        # Top cap center
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(10)])) == True
    
    def test_cylinder_cap_circumference_on_boundary(self, symbolic_mode):
        """Test that points on cap circumferences are on the boundary."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, 
                           start_distance=Rational(0), end_distance=Rational(10))
        
        # Points on bottom cap circumference
        assert cylinder.is_point_on_boundary(Matrix([3, 0, 0])) == True
        assert cylinder.is_point_on_boundary(Matrix([0, 3, 0])) == True
        assert cylinder.is_point_on_boundary(Matrix([-3, 0, 0])) == True
        assert cylinder.is_point_on_boundary(Matrix([0, -3, 0])) == True
        
        # Points on top cap circumference
        assert cylinder.is_point_on_boundary(Matrix([3, 0, 10])) == True
        assert cylinder.is_point_on_boundary(Matrix([0, 3, 10])) == True
        assert cylinder.is_point_on_boundary(Matrix([-3, 0, 10])) == True
        assert cylinder.is_point_on_boundary(Matrix([0, -3, 10])) == True
    
    def test_cylinder_surface_points_on_boundary(self, symbolic_mode):
        """Test that points on the cylindrical surface are on the boundary."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, 
                           start_distance=Rational(0), end_distance=Rational(10))
        
        # Points on cylindrical surface at mid-height
        assert cylinder.is_point_on_boundary(Matrix([Integer(3), Integer(0), Integer(5)])) == True
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(3), Integer(5)])) == True
        assert cylinder.is_point_on_boundary(Matrix([-3, 0, 5])) == True
        assert cylinder.is_point_on_boundary(Matrix([0, -3, 5])) == True
    
    def test_cylinder_round_edges_on_boundary(self, symbolic_mode):
        """Test that points on round edges (cap circumferences) are on boundary."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, 
                           start_distance=Rational(0), end_distance=Rational(10))
        
        # Points on the round edge at bottom
        assert cylinder.is_point_on_boundary(Matrix([3, 0, 0])) == True
        
        # Points on the round edge at top
        assert cylinder.is_point_on_boundary(Matrix([3, 0, 10])) == True
    
    def test_cylinder_interior_not_on_boundary(self):
        """Test that interior points are NOT on the boundary."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, 
                           start_distance=Rational(0), end_distance=Rational(10))
        
        # Center point
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
        
        # Interior point not on axis
        assert cylinder.is_point_on_boundary(Matrix([Integer(1), Integer(1), Integer(5)])) == False
    
    def test_cylinder_exterior_not_on_boundary(self):
        """Test that exterior points are NOT on the boundary."""
        axis = Matrix([Integer(0), Integer(0), Integer(1)])
        radius = Rational(3)
        cylinder = Cylinder(axis_direction=axis, radius=radius, 
                           start_distance=Rational(0), end_distance=Rational(10))
        
        # Far-away point
        assert cylinder.is_point_on_boundary(Matrix([100, 100, 100])) == False
        
        # Just outside radially
        assert cylinder.is_point_on_boundary(Matrix([Integer(4), Integer(0), Integer(5)])) == False
        
        # Just outside axially
        assert cylinder.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(11)])) == False
    
    # ========================================================================
    # HalfSpace Boundary Tests
    # ========================================================================
    
    def test_halfspace_origin_on_boundary(self):
        """Test that the plane origin is on the boundary."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal=normal, offset=offset)
        
        # Plane origin (normal * offset)
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == True
    
    def test_halfspace_random_plane_points_on_boundary(self):
        """Test that random points on the plane are on the boundary."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal=normal, offset=offset)
        
        # Points on the plane (z = 5)
        assert halfspace.is_point_on_boundary(Matrix([10, 20, 5])) == True
        assert halfspace.is_point_on_boundary(Matrix([-15, 7, 5])) == True
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == True
        assert halfspace.is_point_on_boundary(Matrix([100, -50, 5])) == True
    
    def test_halfspace_positive_side_not_on_boundary(self):
        """Test that points on the positive side (inside) are NOT on boundary."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal=normal, offset=offset)
        
        # Points above the plane (z > 5) are inside but not on boundary
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(6)])) == False
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(10)])) == False
        assert halfspace.is_point_on_boundary(Matrix([5, 5, 20])) == False
    
    def test_halfspace_negative_side_not_on_boundary(self):
        """Test that points on the negative side (outside) are NOT on boundary."""
        normal = Matrix([Integer(0), Integer(0), Integer(1)])
        offset = Rational(5)
        halfspace = HalfSpace(normal=normal, offset=offset)
        
        # Points below the plane (z < 5) are outside and not on boundary
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(4)])) == False
        assert halfspace.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == False
        assert halfspace.is_point_on_boundary(Matrix([5, 5, -10])) == False
    
    # ========================================================================
    # ConvexPolygonExtrusion Boundary Tests
    # ========================================================================
    
    def test_convex_polygon_vertices_on_boundary(self):
        """Test that all vertices at both ends are on the boundary."""
        points = [
            Matrix([2, 0]),
            Matrix([0, 2]),
            Matrix([-2, 0]),
            Matrix([0, -2])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Vertices at z=start_distance
        assert extrusion.is_point_on_boundary(Matrix([2, 0, 0])) == True
        assert extrusion.is_point_on_boundary(Matrix([0, 2, 0])) == True
        assert extrusion.is_point_on_boundary(Matrix([-2, 0, 0])) == True
        assert extrusion.is_point_on_boundary(Matrix([0, -2, 0])) == True
        
        # Vertices at z=end_distance
        assert extrusion.is_point_on_boundary(Matrix([2, 0, 10])) == True
        assert extrusion.is_point_on_boundary(Matrix([0, 2, 10])) == True
        assert extrusion.is_point_on_boundary(Matrix([-2, 0, 10])) == True
        assert extrusion.is_point_on_boundary(Matrix([0, -2, 10])) == True
    
    def test_convex_polygon_edge_points_on_boundary(self):
        """Test that points along vertical edges are on the boundary."""
        points = [
            Matrix([2, 0]),
            Matrix([0, 2]),
            Matrix([-2, 0]),
            Matrix([0, -2])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Points along vertical edges at mid-height
        assert extrusion.is_point_on_boundary(Matrix([Integer(2), Integer(0), Integer(5)])) == True
        assert extrusion.is_point_on_boundary(Matrix([0, 2, 5])) == True
        assert extrusion.is_point_on_boundary(Matrix([-2, 0, 5])) == True
        assert extrusion.is_point_on_boundary(Matrix([0, -2, 5])) == True
    
    def test_convex_polygon_face_points_on_boundary(self):
        """Test that points on top/bottom faces are on the boundary."""
        points = [
            Matrix([2, 0]),
            Matrix([0, 2]),
            Matrix([-2, 0]),
            Matrix([0, -2])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Points on bottom face (z=start_distance)
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(0)])) == True
        assert extrusion.is_point_on_boundary(Matrix([Integer(1), Integer(0), Integer(0)])) == True
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(1), Integer(0)])) == True
        
        # Points on top face (z=end_distance)
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(10)])) == True
        assert extrusion.is_point_on_boundary(Matrix([1, 0, 10])) == True
        assert extrusion.is_point_on_boundary(Matrix([0, 1, 10])) == True
    
    def test_convex_polygon_interior_not_on_boundary(self):
        """Test that interior points are NOT on the boundary."""
        points = [
            Matrix([2, 0]),
            Matrix([0, 2]),
            Matrix([-2, 0]),
            Matrix([0, -2])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Interior point at mid-height
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(5)])) == False
        assert extrusion.is_point_on_boundary(Matrix([Rational(1, 2), Rational(1, 2), 5])) == False
    
    def test_convex_polygon_exterior_not_on_boundary(self):
        """Test that exterior points are NOT on the boundary."""
        points = [
            Matrix([2, 0]),
            Matrix([0, 2]),
            Matrix([-2, 0]),
            Matrix([0, -2])
        ]
        start_distance = Rational(0)
        end_distance = Rational(10)
        orientation = Orientation()
        extrusion = ConvexPolygonExtrusion(points=points, start_distance=start_distance,
                                          end_distance=end_distance, transform=Transform.identity())
        
        # Far-away point
        assert extrusion.is_point_on_boundary(Matrix([100, 100, 100])) == False
        
        # Just outside the polygon
        assert extrusion.is_point_on_boundary(Matrix([Integer(3), Integer(0), Integer(5)])) == False
        assert extrusion.is_point_on_boundary(Matrix([Integer(0), Integer(0), Integer(11)])) == False
    
    # ========================================================================
    # Random Shape Tests
    # ========================================================================
    
    
    def test_random_prisms_boundary_points(self, symbolic_mode):
        """Test boundary detection on 25 random prisms."""
        random.seed(42)  # For reproducibility
        
        for i in range(num_random_samples):
            prism = generate_random_prism()
            
            # Get boundary points
            boundary_points = generate_prism_boundary_points(prism)
            
            # All boundary points should be on boundary
            for point in boundary_points:
                assert prism.is_point_on_boundary(point) == True, \
                    f"RectangularPrism {i}: Point {point.T} should be on boundary"
            
            # Get non-boundary points
            non_boundary_points = generate_prism_non_boundary_points(prism)
            
            # Non-boundary points should NOT be on boundary
            for point in non_boundary_points:
                assert prism.is_point_on_boundary(point) == False, \
                    f"RectangularPrism {i}: Point {point.T} should NOT be on boundary"
    
    def test_random_cylinders_boundary_points(self, symbolic_mode):
        """Test boundary detection on 25 random cylinders."""
        random.seed(43)  # For reproducibility
        
        for i in range(num_random_samples):
            cylinder = generate_random_cylinder()
            
            # Get boundary points
            boundary_points = generate_cylinder_boundary_points(cylinder)
            
            # All boundary points should be on boundary
            for point in boundary_points:
                assert cylinder.is_point_on_boundary(point) == True, \
                    f"Cylinder {i}: Point {point.T} should be on boundary"
            
            # Get non-boundary points
            non_boundary_points = generate_cylinder_non_boundary_points(cylinder)
            
            # Non-boundary points should NOT be on boundary
            for point in non_boundary_points:
                assert cylinder.is_point_on_boundary(point) == False, \
                    f"Cylinder {i}: Point {point.T} should NOT be on boundary"
    
    def test_random_halfspaces_boundary_points(self, symbolic_mode):
        """Test boundary detection on 25 random half-planes."""
        random.seed(44)  # For reproducibility
        
        for i in range(num_random_samples):
            halfspace = generate_random_halfspace()
            
            # Get boundary points
            boundary_points = generate_halfspace_boundary_points(halfspace)
            
            # All boundary points should be on boundary
            for point in boundary_points:
                assert halfspace.is_point_on_boundary(point) == True, \
                    f"HalfSpace {i}: Point {point.T} should be on boundary"
            
            # Get non-boundary points - these are NOT on boundary
            non_boundary_points = generate_halfspace_non_boundary_points(halfspace)
            
            # Non-boundary points should NOT be on boundary
            for point in non_boundary_points:
                assert halfspace.is_point_on_boundary(point) == False, \
                    f"HalfSpace {i}: Point {point.T} should NOT be on boundary"
    
    def test_random_convex_polygons_boundary_points(self, symbolic_mode):
        """Test boundary detection on 25 random convex polygon extrusions."""
        random.seed(45)  # For reproducibility
        
        for i in range(num_random_samples):
            extrusion = generate_random_convex_polygon_extrusion()
            
            # Get boundary points
            boundary_points = generate_convex_polygon_boundary_points(extrusion)
            
            # All boundary points should be on boundary
            for point in boundary_points:
                assert extrusion.is_point_on_boundary(point) == True, \
                    f"ConvexPolygon {i}: Point {point.T} should be on boundary"
            
            # Get non-boundary points
            non_boundary_points = generate_convex_polygon_non_boundary_points(extrusion)
            
            # Non-boundary points should NOT be on boundary
            for point in non_boundary_points:
                assert extrusion.is_point_on_boundary(point) == False, \
                    f"ConvexPolygon {i}: Point {point.T} should NOT be on boundary"


# =============================================================================
# Simple tests for translate_profile, translate_profiles, translate_csg, adopt_csg
# =============================================================================

class TestTranslateProfile:
    def test_translate_profile_moves_points(self):
        profile = [Matrix([Rational(0), Rational(0)]), Matrix([Rational(1), Rational(0)])]
        trans = create_v2(Rational(2), Rational(3))
        result = translate_profile(profile, trans)
        assert result[0] == Matrix([Rational(2), Rational(3)])
        assert result[1] == Matrix([Rational(3), Rational(3)])


class TestTranslateProfiles:
    def test_translate_profiles_moves_all_profiles(self):
        p1 = [Matrix([Rational(0), Rational(0)])]
        p2 = [Matrix([Rational(1), Rational(1)])]
        profiles = [p1, p2]
        trans = create_v2(Rational(1), Rational(1))
        result = translate_profiles(profiles, trans)
        assert result[0][0] == Matrix([Rational(1), Rational(1)])
        assert result[1][0] == Matrix([Rational(2), Rational(2)])


class TestTranslateCsg:
    def test_translate_csg_halfspace(self):
        hs = HalfSpace(normal=Matrix([Integer(1), Integer(0), Integer(0)]), offset=Rational(0))
        trans = Matrix([Rational(5), Integer(0), Integer(0)])
        translated = translate_csg(hs, trans)
        # Original: x >= 0. After translate by (5,0,0): (x-5) >= 0 => x >= 5
        assert translated.contains_point(Matrix([Rational(6), Integer(0), Integer(0)])) == True
        assert translated.contains_point(Matrix([Rational(4), Integer(0), Integer(0)])) == False


class TestAdoptCsg:
    def test_adopt_csg_global_to_timber_local_identity_timber(self):
        # Timber at origin with identity orientation: global = local
        timber = create_standard_vertical_timber(ticket="t")
        hs_global = HalfSpace(normal=Matrix([Integer(1), Integer(0), Integer(0)]), offset=Rational(10))
        adopted = adopt_csg(None, timber.transform, hs_global)
        assert isinstance(adopted, HalfSpace)
        # In global, point (11,0,0) is inside (x >= 10). In local same coords.
        assert adopted.contains_point(Matrix([Rational(11), Integer(0), Integer(0)])) == True


# ============================================================================
# TestGetAABB
# ============================================================================

class TestGetAABB:
    """Tests for CutCSG.get_aabb() — axis-aligned bounding boxes."""

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------

    def test_bbox_axis_aligned_prism(self, symbolic_mode):
        """Identity-oriented prism at origin — AABB equals the exact local extents."""
        prism = RectangularPrism(
            size=Matrix([Rational(6), Rational(4)]),
            transform=Transform.identity(),
            start_distance=Rational(0),
            end_distance=Rational(10),
        )
        bbox = prism.get_aabb()
        assert bbox.min_x == Rational(-3)
        assert bbox.max_x == Rational(3)
        assert bbox.min_y == Rational(-2)
        assert bbox.max_y == Rational(2)
        assert bbox.min_z == Rational(0)
        assert bbox.max_z == Rational(10)

    def test_bbox_rotated_prism(self, symbolic_mode):
        """Prism rotated 90° around Z — local X and Y axes swap in global space."""
        # rotate_left: local +X → global +Y, local +Y → global -X
        orientation = Orientation.rotate_left()
        prism = RectangularPrism(
            size=Matrix([Rational(6), Rational(4)]),
            transform=Transform(position=Matrix([Integer(0), Integer(0), Integer(0)]), orientation=orientation),
            start_distance=Rational(0),
            end_distance=Rational(10),
        )
        bbox = prism.get_aabb()
        # width (6) is now along global Y: [-3, 3]
        # height (4) is now along global -X direction: [-2, 2]
        assert bbox.min_x == Rational(-2)
        assert bbox.max_x == Rational(2)
        assert bbox.min_y == Rational(-3)
        assert bbox.max_y == Rational(3)
        assert bbox.min_z == Rational(0)
        assert bbox.max_z == Rational(10)

    def test_bbox_axis_aligned_cylinder(self, symbolic_mode):
        """Z-axis cylinder at origin — AABB is [-r,r]×[-r,r]×[start,end]."""
        cyl = Cylinder(
            axis_direction=Matrix([Integer(0), Integer(0), Integer(1)]),
            radius=Rational(5),
            position=Matrix([Integer(0), Integer(0), Integer(0)]),
            start_distance=Rational(2),
            end_distance=Rational(8),
        )
        bbox = cyl.get_aabb()
        assert bbox.min_x == Rational(-5)
        assert bbox.max_x == Rational(5)
        assert bbox.min_y == Rational(-5)
        assert bbox.max_y == Rational(5)
        assert bbox.min_z == Rational(2)
        assert bbox.max_z == Rational(8)

    def test_bbox_convex_polygon_extrusion(self, symbolic_mode):
        """Square polygon extrusion at origin — matches equivalent prism bounds."""
        # Square with corners at (±3, ±3) in CCW order
        points = [
            Matrix([Rational(3), Rational(-3)]),
            Matrix([Rational(3), Rational(3)]),
            Matrix([Rational(-3), Rational(3)]),
            Matrix([Rational(-3), Rational(-3)]),
        ]
        extrusion = ConvexPolygonExtrusion(
            points=points,
            transform=Transform.identity(),
            start_distance=Rational(0),
            end_distance=Rational(5),
        )
        bbox = extrusion.get_aabb()
        assert bbox.min_x == Rational(-3)
        assert bbox.max_x == Rational(3)
        assert bbox.min_y == Rational(-3)
        assert bbox.max_y == Rational(3)
        assert bbox.min_z == Rational(0)
        assert bbox.max_z == Rational(5)

    # ------------------------------------------------------------------
    # Infinite-extent warnings
    # ------------------------------------------------------------------

    def test_bbox_halfspace_warns(self, symbolic_mode):
        """HalfSpace.get_aabb() should emit a UserWarning and return all-None."""
        hs = HalfSpace(
            normal=Matrix([Integer(1), Integer(0), Integer(0)]),
            offset=Rational(5),
        )
        with pytest.warns(UserWarning, match="HalfSpace"):
            bbox = hs.get_aabb()
        assert bbox.min_x is None
        assert bbox.max_x is None
        assert bbox.min_y is None
        assert bbox.max_y is None
        assert bbox.min_z is None
        assert bbox.max_z is None

    def test_bbox_infinite_prism_warns(self, symbolic_mode):
        """RectangularPrism with end_distance=None should emit a UserWarning."""
        prism = RectangularPrism(
            size=Matrix([Rational(4), Rational(4)]),
            transform=Transform.identity(),
            start_distance=Rational(0),
            end_distance=None,
        )
        with pytest.warns(UserWarning, match="infinite"):
            bbox = prism.get_aabb()
        assert bbox.min_x is None
        assert bbox.max_x is None

    # ------------------------------------------------------------------
    # Composites
    # ------------------------------------------------------------------

    def test_bbox_union(self, symbolic_mode):
        """Union of two offset prisms — merged bbox spans both."""
        # Prism A at origin: [-2,2]×[-2,2]×[0,5]
        prism_a = RectangularPrism(
            size=Matrix([Rational(4), Rational(4)]),
            transform=Transform.identity(),
            start_distance=Rational(0),
            end_distance=Rational(5),
        )
        # Prism B shifted (+10, +10, +10): [8,12]×[8,12]×[10,15]
        prism_b = RectangularPrism(
            size=Matrix([Rational(4), Rational(4)]),
            transform=Transform(
                position=Matrix([Rational(10), Rational(10), Rational(10)]),
                orientation=Orientation.identity(),
            ),
            start_distance=Rational(0),
            end_distance=Rational(5),
        )
        union = SolidUnion(children=[prism_a, prism_b])
        bbox = union.get_aabb()
        assert bbox.min_x == Rational(-2)
        assert bbox.max_x == Rational(12)
        assert bbox.min_y == Rational(-2)
        assert bbox.max_y == Rational(12)
        assert bbox.min_z == Rational(0)
        assert bbox.max_z == Rational(15)

    def test_bbox_difference_halfspace_crop_non_orthogonal(self, symbolic_mode):
        """Box [0,10]³ minus diagonal halfspace — bbox is tightened on X and Y."""
        # Prism centred at (5,5,5): spans [0,10]×[0,10]×[0,10]
        prism = RectangularPrism(
            size=Matrix([Rational(10), Rational(10)]),
            transform=Transform(
                position=Matrix([Rational(5), Rational(5), Rational(5)]),
                orientation=Orientation.identity(),
            ),
            start_distance=Rational(-5),
            end_distance=Rational(5),
        )
        # Halfspace: n = (1,1,0)/√2, offset = 5
        # Contains {P : (x+y)/√2 >= 5}, i.e., x+y >= 5√2 ≈ 7.07
        normal = Matrix([Integer(1), Integer(1), Integer(0)]) / sqrt(Integer(2))
        hs = HalfSpace(normal=normal, offset=Rational(5))

        diff = Difference(base=prism, subtract=[hs])
        bbox = diff.get_aabb()

        # Z is unaffected by the cut
        assert bbox.min_z == Rational(0)
        assert bbox.max_z == Rational(10)

        # X and Y should be tightened to [0, 5√2]
        assert bbox.min_x == Rational(0)
        assert bbox.min_y == Rational(0)
        assert simplify(bbox.max_x - 5 * sqrt(Integer(2))) == Integer(0)
        assert simplify(bbox.max_y - 5 * sqrt(Integer(2))) == Integer(0)


# ============================================================================
# CSG Feature Tests
# ============================================================================

class TestCSGFeatures:
    """Tests for opt-in named CSG features on primitives."""

    def test_halfspace_named_feature(self):
        """HalfSpace with named_feature returns a HalfSpaceFeature for boundary points."""
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(5), named_feature="shoulder")
        on_boundary = create_v3(Integer(0), Integer(0), Integer(5))
        off_boundary = create_v3(Integer(0), Integer(0), Integer(6))

        feat = hs.find_feature(on_boundary)
        assert feat is not None
        assert isinstance(feat, HalfSpaceFeature)
        assert feat.name == "shoulder"
        assert feat.owner is hs

        assert hs.find_feature(off_boundary) is None

    def test_halfspace_no_named_feature(self):
        """HalfSpace without named_feature returns no features."""
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(5))
        on_boundary = create_v3(Integer(0), Integer(0), Integer(5))
        assert hs.find_feature(on_boundary) is None
        assert hs.get_all_features(on_boundary) == []

    def test_rectangular_prism_named_features(self):
        """RectangularPrism with named_features returns features only for named faces."""
        prism = RectangularPrism(
            size=Matrix([Integer(4), Integer(6)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(10),
            named_features=[("my_right", PrismFace.RIGHT), ("my_top", PrismFace.TOP)],
        )
        # Point on right face (x = +2, within height and length bounds)
        right_pt = create_v3(Integer(2), Integer(0), Integer(5))
        feat = prism.find_feature(right_pt)
        assert feat is not None
        assert isinstance(feat, RectangularPrismFeature)
        assert feat.name == "my_right"
        assert feat.face == PrismFace.RIGHT

        # Point on top face (z = 10)
        top_pt = create_v3(Integer(0), Integer(0), Integer(10))
        feat = prism.find_feature(top_pt)
        assert feat is not None
        assert isinstance(feat, RectangularPrismFeature)
        assert feat.name == "my_top"
        assert feat.face == PrismFace.TOP

        # Point on left face — not named, so no feature
        left_pt = create_v3(Integer(-2), Integer(0), Integer(5))
        assert prism.find_feature(left_pt) is None

    def test_rectangular_prism_no_named_features(self):
        """RectangularPrism without named_features returns nothing."""
        prism = RectangularPrism(
            size=Matrix([Integer(4), Integer(6)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(10),
        )
        right_pt = create_v3(Integer(2), Integer(0), Integer(5))
        assert prism.find_feature(right_pt) is None

    def test_cylinder_returns_no_features(self):
        """Cylinder has no feature support — always returns empty."""
        cyl = Cylinder(
            axis_direction=Matrix([Integer(0), Integer(0), Integer(1)]),
            radius=Integer(3),
            position=create_v3(Integer(0), Integer(0), Integer(0)),
            start_distance=Integer(0),
            end_distance=Integer(10),
        )
        on_boundary = create_v3(Integer(3), Integer(0), Integer(5))
        assert cyl.get_all_features(on_boundary) == []

    def test_solid_union_collects_child_features(self):
        """SolidUnion collects features from children that have named features."""
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(0), named_feature="floor")
        prism = RectangularPrism(
            size=Matrix([Integer(4), Integer(4)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(10),
            named_features=[("wall", PrismFace.RIGHT)],
        )
        union = SolidUnion(children=[hs, prism])

        # Point on the halfspace boundary (z=0) and inside prism bottom face
        pt = create_v3(Integer(0), Integer(0), Integer(0))
        features = union.get_all_features(pt)
        names = [f.name for f in features]
        assert "floor" in names

    def test_difference_collects_features_from_base_and_subtract(self):
        """Difference collects features from base and subtract children."""
        base = RectangularPrism(
            size=Matrix([Integer(10), Integer(10)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(20),
            named_features=[("base_top", PrismFace.TOP)],
        )
        cut = HalfSpace(
            normal=Matrix([Integer(0), Integer(0), Integer(-1)]),
            offset=Integer(-15),
            named_feature="cut_plane",
        )
        diff = Difference(base=base, subtract=[cut])

        # Point on the cut plane (z=15) which is now a boundary of the difference
        pt = create_v3(Integer(0), Integer(0), Integer(15))
        features = diff.get_all_features(pt)
        names = [f.name for f in features]
        assert "cut_plane" in names


class TestCSGNaming:
    """Tests for the hierarchical name field on CutCSG subclasses."""

    def test_halfspace_name_field(self):
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(0), tag="shoulder")
        assert hs.tag == "shoulder"

    def test_halfspace_name_default_none(self):
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(0))
        assert hs.tag is None

    def test_rectangular_prism_name_field(self):
        prism = RectangularPrism(
            size=Matrix([Integer(4), Integer(6)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(10),
            tag="tenon",
        )
        assert prism.tag == "tenon"

    def test_solid_union_name_field(self):
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(0))
        union = SolidUnion(children=[hs], tag="my_cut")
        assert union.tag == "my_cut"

    def test_difference_name_field(self):
        base = RectangularPrism(
            size=Matrix([Integer(4), Integer(4)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(10),
        )
        cut = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(-1)]), offset=Integer(-5))
        diff = Difference(base=base, subtract=[cut], tag="tenon_cut")
        assert diff.tag == "tenon_cut"

    def test_adopt_csg_preserves_name_on_solid_union(self):
        """adopt_csg should preserve the name field when transforming SolidUnion."""
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(0), tag="plane_a")
        union = SolidUnion(children=[hs], tag="my_joint")
        adopted = adopt_csg(None, Transform.identity(), union)
        assert isinstance(adopted, SolidUnion)
        assert adopted.tag == "my_joint"
        assert adopted.children[0].tag == "plane_a"

    def test_adopt_csg_preserves_name_on_difference(self):
        """adopt_csg should preserve the name field when transforming Difference."""
        base = RectangularPrism(
            size=Matrix([Integer(4), Integer(4)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(10),
            tag="base_prism",
        )
        cut = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(-1)]), offset=Integer(-5), tag="cut_plane")
        diff = Difference(base=base, subtract=[cut], tag="my_diff")
        adopted = adopt_csg(None, Transform.identity(), diff)
        assert isinstance(adopted, Difference)
        assert adopted.tag == "my_diff"
        assert adopted.base.tag == "base_prism"
        assert adopted.subtract[0].tag == "cut_plane"

    def test_adopt_csg_preserves_name_on_primitives(self):
        """adopt_csg should preserve name on primitive types that use replace()."""
        prism = RectangularPrism(
            size=Matrix([Integer(4), Integer(4)]),
            transform=Transform.identity(),
            start_distance=Integer(0),
            end_distance=Integer(10),
            tag="my_prism",
        )
        adopted = adopt_csg(None, Transform.identity(), prism)
        assert adopted.tag == "my_prism"

    def test_cutting_name_wraps_in_named_solid_union(self):
        """Cutting with a name wraps get_negative_csg_local() in a named SolidUnion."""
        from kumiki.timber import Cutting, Timber
        from kumiki.ticket import TimberTicket
        timber = Timber(
            size=Matrix([Rational(4), Rational(6)]),
            length=Rational(100),
            transform=Transform.identity(),
            ticket=TimberTicket(name="test_timber"),
        )
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(50))
        cutting = Cutting(timber=timber, maybe_top_end_cut=hs, tag="my_joint")
        result = cutting.get_negative_csg_local()
        assert isinstance(result, SolidUnion)
        assert result.tag == "my_joint"

    def test_cutting_no_name_returns_raw_csg(self):
        """Cutting without a name returns the raw CSG, not wrapped."""
        from kumiki.timber import Cutting, Timber
        from kumiki.ticket import TimberTicket
        timber = Timber(
            size=Matrix([Rational(4), Rational(6)]),
            length=Rational(100),
            transform=Transform.identity(),
            ticket=TimberTicket(name="test_timber"),
        )
        hs = HalfSpace(normal=Matrix([Integer(0), Integer(0), Integer(1)]), offset=Integer(50))
        cutting = Cutting(timber=timber, maybe_top_end_cut=hs)
        result = cutting.get_negative_csg_local()
        assert isinstance(result, HalfSpace)

