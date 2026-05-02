"""
Tests for the measuring module (geometric primitives).
"""

import pytest
from kumiki.measuring import *
from kumiki.timber import timber_from_directions, TimberFace, TimberLongEdge, TimberEdge, TimberCenterline, TimberCorner
from kumiki.rule import create_v3, create_v2, Transform, Orientation
from sympy import Matrix, Rational


class TestGetPointOnFace:
    """Tests for get_point_on_face_global helper function"""
    
    def test_get_point_on_right_face(self, symbolic_mode):
        """Test getting a point on the RIGHT face of a vertical timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        point = get_point_on_face_global(TimberFace.RIGHT, timber)
        
        # RIGHT face center: x=5 (half the width), y=0, z=50 (mid-length)
        assert point[0] == Rational(5)
        assert point[1] == Rational(0)
        assert point[2] == Rational(50)
    
    def test_get_point_on_top_face(self, symbolic_mode):
        """Test getting a point on the TOP face of a vertical timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        point = get_point_on_face_global(TimberFace.TOP, timber)
        
        # TOP face center: x=0, y=0, z=100 (actual top of 100-long timber)
        assert point[0] == Rational(0)
        assert point[1] == Rational(0)
        assert point[2] == Rational(100)


class TestMeasureOntoFace:
    """Tests for project_point_onto_face_global helper function"""
    
    def test_project_point_on_face_surface(self):
        """Test projecting a point that's exactly on the face surface"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Point exactly on RIGHT face (x=5)
        point = create_v3(5, 0, 50)
        marking = mark_distance_from_face_in_normal_direction(Point(point), timber, TimberFace.RIGHT)
        
        # Should be 0 (on the surface)
        assert marking.distance == Rational(0)
    
    def test_project_point_inside_timber(self, symbolic_mode):
        """Test projecting a point inside the timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Point at x=2 (3 units inside from RIGHT face which is at x=5)
        point = create_v3(2, 0, 50)
        marking = mark_distance_from_face_in_normal_direction(Point(point), timber, TimberFace.RIGHT)
        
        # Should be positive (inside the timber)
        assert marking.distance == Rational(3)
    
    def test_project_point_outside_timber(self, symbolic_mode):
        """Test projecting a point outside the timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Point at x=8 (3 units outside from RIGHT face which is at x=5)
        point = create_v3(8, 0, 50)
        marking = mark_distance_from_face_in_normal_direction(Point(point), timber, TimberFace.RIGHT)
        
        # Should be negative (outside the timber)
        assert marking.distance == Rational(-3)
    
    def test_project_point_on_left_face(self, symbolic_mode):
        """Test projection onto LEFT face"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # LEFT face is at x=-5
        # Point at x=-2 (3 units inside from LEFT face)
        point = create_v3(-2, 0, 50)
        marking = mark_distance_from_face_in_normal_direction(Point(point), timber, TimberFace.LEFT)
        
        # Should be positive (inside the timber from LEFT face)
        assert marking.distance == Rational(3)
    
    def test_project_point_on_front_face(self, symbolic_mode):
        """Test projection onto FRONT face"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),  # 10" wide (X), 20" height (Y)
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # FRONT face is at y=10
        # Point at y=5 (5 units inside from FRONT face)
        point = create_v3(0, 5, 50)
        marking = mark_distance_from_face_in_normal_direction(Point(point), timber, TimberFace.FRONT)
        
        # Should be positive (inside the timber from FRONT face)
        assert marking.distance == Rational(5)
    
    def test_project_point_with_offset_timber(self, symbolic_mode):
        """Test projection on a timber not centered at origin"""
        timber = timber_from_directions(
            length=Rational(48),
            size=create_v2(6, 6),
            bottom_position=create_v3(10, 20, 5),  # Offset position
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # RIGHT face is at x=10+3=13
        # Point at x=11 (2 units inside from RIGHT face)
        point = create_v3(11, 20, 20)
        marking = mark_distance_from_face_in_normal_direction(Point(point), timber, TimberFace.RIGHT)
        
        # Should be positive (inside the timber)
        assert marking.distance == Rational(2)


class TestPoint:
    """Tests for Point class"""
    
    def test_point_creation(self):
        """Test creating a point"""
        pos = create_v3(1, 2, 3)
        point = Point(pos)
        assert point.position.equals(pos)
    
    def test_point_is_frozen(self):
        """Test that Point is immutable"""
        point = Point(create_v3(1, 2, 3))
        with pytest.raises(Exception):
            point.position = create_v3(4, 5, 6)  # type: ignore
    
    def test_point_repr(self):
        """Test Point string representation"""
        point = Point(create_v3(1, 2, 3))
        assert "Point" in repr(point)
        assert "position" in repr(point)


class TestLine:
    """Tests for Line class"""
    
    def test_line_creation(self):
        """Test creating a line"""
        direction = create_v3(0, 0, 1)
        point = create_v3(1, 2, 3)
        line = Line(direction, point)
        assert line.direction.equals(direction)
        assert line.point.equals(point)
    
    def test_line_is_frozen(self):
        """Test that Line is immutable"""
        line = Line(create_v3(0, 0, 1), create_v3(1, 2, 3))
        with pytest.raises(Exception):
            line.direction = create_v3(1, 0, 0)  # type: ignore
    
    def test_line_repr(self):
        """Test Line string representation"""
        line = Line(create_v3(0, 0, 1), create_v3(1, 2, 3))
        assert "Line" in repr(line)
        assert "direction" in repr(line)
        assert "point" in repr(line)


class TestPlane:
    """Tests for Plane class"""
    
    def test_plane_creation(self):
        """Test creating a plane"""
        normal = create_v3(0, 0, 1)
        point = create_v3(1, 2, 3)
        plane = Plane(normal, point)
        assert plane.normal.equals(normal)
        assert plane.point.equals(point)
    
    def test_plane_is_frozen(self):
        """Test that Plane is immutable"""
        plane = Plane(create_v3(0, 0, 1), create_v3(1, 2, 3))
        with pytest.raises(Exception):
            plane.normal = create_v3(1, 0, 0)  # type: ignore
    
    def test_plane_repr(self):
        """Test Plane string representation"""
        plane = Plane(create_v3(0, 0, 1), create_v3(1, 2, 3))
        assert "Plane" in repr(plane)
        assert "normal" in repr(plane)
        assert "point" in repr(plane)
    
    def test_plane_from_transform_and_direction_identity(self):
        """Test creating plane from identity transform"""
        transform = Transform.identity()
        local_direction = create_v3(0, 1, 0)
        
        plane = Plane.from_transform_and_direction(transform, local_direction)
        
        # For identity transform, global direction should equal local direction
        assert plane.normal.equals(local_direction)
        # Point should be at origin
        assert plane.point.equals(create_v3(0, 0, 0))
    
    def test_plane_from_transform_and_direction_rotated(self):
        """Test creating plane from rotated transform"""
        # Create a transform rotated 90 degrees around Z axis
        # This transforms local +X to global +Y and local +Y to global -X
        orientation = Orientation(Matrix([
            [0, -1, 0],
            [1,  0, 0],
            [0,  0, 1]
        ]))
        position = create_v3(5, 0, 0)
        transform = Transform(position, orientation)
        
        # Local direction pointing in +X
        local_direction = create_v3(1, 0, 0)
        
        plane = Plane.from_transform_and_direction(transform, local_direction)
        
        # After rotation, local +X becomes global +Y
        expected_normal = create_v3(0, 1, 0)
        assert plane.normal.equals(expected_normal)
        # Point should be at transform position
        assert plane.point.equals(position)
    
    def test_plane_from_transform_and_direction_translated(self):
        """Test that plane point is at transform position"""
        position = create_v3(10, 20, 30)
        transform = Transform(position, Orientation.identity())
        local_direction = create_v3(0, 0, 1)
        
        plane = Plane.from_transform_and_direction(transform, local_direction)
        
        assert plane.point.equals(position)
        assert plane.normal.equals(local_direction)


class TestGetPointOnFeature:
    """Tests for get_point_on_feature helper function"""
    
    def test_get_point_on_point_feature(self):
        """Test getting point from Point feature"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        test_position = create_v3(1, 2, 3)
        point_feature = Point(test_position)
        
        result = get_point_on_feature(point_feature, timber)
        assert result.equals(test_position)
    
    def test_get_point_on_plane_feature(self):
        """Test getting point from Plane feature"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        test_point = create_v3(5, 5, 5)
        plane_feature = Plane(create_v3(1, 0, 0), test_point)
        
        result = get_point_on_feature(plane_feature, timber)
        assert result.equals(test_point)


class TestMeasureFromFace:
    """Tests for locate_into_face function"""
    
    def test_locate_zero_distance_from_face(self, symbolic_mode):
        """Test measuring zero distance creates plane at face surface"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        plane = locate_into_face(Rational(0), TimberFace.RIGHT, timber)
        
        # Should be an UnsignedPlane
        assert isinstance(plane, UnsignedPlane)
        # Normal should point in the face direction (outward)
        assert plane.normal.equals(create_v3(1, 0, 0))
        # Point should be at the face surface (x=5)
        assert plane.point[0] == Rational(5)
    
    def test_locate_positive_distance_from_face(self, symbolic_mode):
        """Test measuring positive distance INTO the face"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        plane = locate_into_face(Rational(3), TimberFace.RIGHT, timber)
        
        # Point should be 3 units inside from face (x=5-3=2)
        assert plane.point[0] == Rational(2)
        assert plane.normal.equals(create_v3(1, 0, 0))


class TestMarkFromFace:
    """Tests for mark_distance_from_face_in_normal_direction function"""
    
    def test_mark_onto_face_round_trip(self, symbolic_mode):
        """Test that mark_distance_from_face_in_normal_direction is inverse of locate_into_face"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Test round trip for various distances
        for distance in [Rational(0), Rational(5), Rational(10), Rational(-2)]:
            plane = locate_into_face(distance, TimberFace.RIGHT, timber)
            marking = mark_distance_from_face_in_normal_direction(plane, timber, TimberFace.RIGHT)
            assert marking.distance == distance
    
    def test_mark_point_from_face(self, symbolic_mode):
        """Test marking a point feature from a face"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Point at x=2 (3 units inside from RIGHT face which is at x=5)
        point = Point(create_v3(2, 0, 0))
        marking = mark_distance_from_face_in_normal_direction(point, timber, TimberFace.RIGHT)
        
        assert marking.distance == Rational(3)


class TestMeasureFace:
    """Tests for locate_face function"""
    
    def test_locate_face_right(self, symbolic_mode):
        """Test measuring the RIGHT face of a vertical timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),  # 10" wide (X), 20" height (Y)
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Vertical
            width_direction=create_v3(1, 0, 0),   # Width along X
            ticket="test_timber"
        )
        
        plane = locate_face(timber, TimberFace.RIGHT)
        
        # Should be a Plane
        assert isinstance(plane, Plane)
        # Normal should point outward (+X for RIGHT face)
        assert plane.normal.equals(create_v3(1, 0, 0))
        # Point should be at the face center (x=5, y=0, z=50)
        assert plane.point[0] == Rational(5)
        assert plane.point[1] == Rational(0)
        assert plane.point[2] == Rational(50)
    
    def test_locate_face_front(self, symbolic_mode):
        """Test measuring the FRONT face of a vertical timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        plane = locate_face(timber, TimberFace.FRONT)
        
        # Normal should point outward (+Y for FRONT face)
        assert plane.normal.equals(create_v3(0, 1, 0))
        # Point should be at the face center (x=0, y=10, z=50)
        assert plane.point[0] == Rational(0)
        assert plane.point[1] == Rational(10)
        assert plane.point[2] == Rational(50)


class TestMeasureLongEdge:
    """Tests for locate_long_edge function"""
    
    def test_locate_long_edge_right_front(self, symbolic_mode):
        """Test measuring the RIGHT_FRONT edge of a vertical timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),  # 10" wide (X), 20" height (Y)
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Vertical
            width_direction=create_v3(1, 0, 0),   # Width along X
            ticket="test_timber"
        )
        
        line = locate_long_edge(timber, TimberLongEdge.RIGHT_FRONT)
        
        # Should be a Line
        assert isinstance(line, Line)
        # Direction should be along timber length (+Z)
        assert line.direction.equals(create_v3(0, 0, 1))
        # Point should be at the edge (x=5, y=10, z=0)
        assert line.point[0] == Rational(5)   # Right face at x=5
        assert line.point[1] == Rational(10)  # Front face at y=10
        assert line.point[2] == Rational(0)   # At bottom
    
    def test_locate_long_edge_left_back(self, symbolic_mode):
        """Test measuring the LEFT_BACK edge of a vertical timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        line = locate_long_edge(timber, TimberLongEdge.LEFT_BACK)
        
        # Direction should be along timber length (+Z)
        assert line.direction.equals(create_v3(0, 0, 1))
        # Point should be at the edge (x=-5, y=-10, z=0)
        assert line.point[0] == Rational(-5)   # Left face at x=-5
        assert line.point[1] == Rational(-10)  # Back face at y=-10
        assert line.point[2] == Rational(0)    # At bottom
    
    def test_locate_long_edge_horizontal_timber(self, symbolic_mode):
        """Test measuring edge on a horizontal timber"""
        # Horizontal timber pointing in +X direction
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(4, 6),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # Horizontal, pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="test_timber"
        )
        
        line = locate_long_edge(timber, TimberLongEdge.RIGHT_FRONT)
        
        # Direction should be along timber length (+X in this case)
        assert line.direction.equals(create_v3(1, 0, 0))
        # Point should be at the edge
        assert line.point[0] == Rational(0)   # At bottom
        assert line.point[1] == Rational(2)   # Right face (width/2)
        assert line.point[2] == Rational(3)   # Front face (height/2)


class TestMeasureShortEdge:
    """Tests for locate_edge with short edges"""

    def test_bottom_right_edge_vertical_timber(self, symbolic_mode):
        """BOTTOM_RIGHT edge on a vertical 10x20 timber at origin.

        The edge runs from the back-right corner (5, -10, 0) to the
        front-right corner (5, 10, 0). Direction = FRONT = +Y.
        Point = BOT_BACK_RIGHT corner = (5, -10, 0).
        """
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        line = locate_edge(timber, TimberEdge.BOTTOM_RIGHT)
        assert isinstance(line, Line)
        assert line.direction.equals(create_v3(0, 1, 0))
        assert line.point[0] == Rational(5)
        assert line.point[1] == Rational(-10)
        assert line.point[2] == Rational(0)

    def test_top_front_edge_vertical_timber(self, symbolic_mode):
        """TOP_FRONT edge on a vertical 10x20 timber at origin.

        The edge runs from the front-left corner (-5, 10, 100) to the
        right-front corner (5, 10, 100). Direction = RIGHT = +X.
        Point = TOP_FRONT_LEFT corner = (-5, 10, 100).
        """
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        line = locate_edge(timber, TimberEdge.TOP_FRONT)
        assert isinstance(line, Line)
        assert line.direction.equals(create_v3(1, 0, 0))
        assert line.point[0] == Rational(-5)
        assert line.point[1] == Rational(10)
        assert line.point[2] == Rational(100)


class TestMeasurePlaneFromEdgeInDirection:
    """Tests for locate_plane_from_edge_in_direction function"""

    def test_plane_from_centerline_offset_in_x(self, symbolic_mode):
        """Plane through centerline offset 3 in +X should have normal +X and point at (3, 0, 50)."""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        plane = locate_plane_from_edge_in_direction(
            timber, TimberCenterline.CENTERLINE, create_v3(1, 0, 0), Rational(3)
        )
        assert isinstance(plane, Plane)
        assert plane.normal.equals(create_v3(1, 0, 0))
        assert plane.point[0] == Rational(3)
        assert plane.point[1] == Rational(0)
        assert plane.point[2] == Rational(50)


class TestMeasureCenterLine:
    """Tests for locate_centerline function"""
    
    def test_locate_centerline_vertical(self, symbolic_mode):
        """Test measuring the center line of a vertical timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Vertical
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        line = locate_centerline(timber)
        
        # Should be a Line
        assert isinstance(line, Line)
        # Direction should be along timber length (+Z)
        assert line.direction.equals(create_v3(0, 0, 1))
        # Point should be at the center (x=0, y=0, z=50)
        assert line.point[0] == Rational(0)
        assert line.point[1] == Rational(0)
        assert line.point[2] == Rational(50)  # Mid-length
    
    def test_locate_centerline_horizontal(self, symbolic_mode):
        """Test measuring the center line of a horizontal timber"""
        timber = timber_from_directions(
            length=Rational(48),
            size=create_v2(4, 6),
            bottom_position=create_v3(10, 20, 5),  # Offset position
            length_direction=create_v3(1, 0, 0),   # Horizontal, pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="test_timber"
        )
        
        line = locate_centerline(timber)
        
        # Direction should be along timber length (+X)
        assert line.direction.equals(create_v3(1, 0, 0))
        # Point should be at the center
        assert line.point[0] == Rational(34)  # 10 + 48/2 = 34
        assert line.point[1] == Rational(20)  # Centered in Y
        assert line.point[2] == Rational(5)   # Centered in Z
    
    def test_locate_centerline_diagonal(self):
        """Test measuring the center line of a diagonally oriented timber"""
        # Timber pointing in diagonal direction
        from kumiki.rule import safe_normalize_vector as normalize_vector
        
        direction = normalize_vector(create_v3(1, 1, 1))  # Diagonal
        timber = timber_from_directions(
            length=Rational(60),
            size=create_v2(4, 4),
            bottom_position=create_v3(0, 0, 0),
            length_direction=direction,
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        line = locate_centerline(timber)
        
        # Direction should be along timber length (diagonal)
        assert line.direction.equals(direction)
        # Point should be at mid-length along the diagonal
        expected_point = direction * Rational(30)  # 60/2 = 30
        assert line.point.equals(expected_point)


class TestDistanceFromPointIntoFaceMark:
    """Test DistanceFromPointIntoFace.mark() method"""
    
    def test_mark_from_face_center(self):
        """Test marking a line from face center going into timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Create measurement: 5 units into timber from RIGHT face center
        measurement = DistanceFromPointIntoFace(
            distance=Rational(5),
            timber=timber,
            face=TimberFace.RIGHT,
            point=None  # Use face center
        )
        
        point = measurement.locate()
        
        # Starting from face center (5, 0, 50), measuring 5 into timber (-X)
        # gives position (0, 0, 50)
        assert point.position.equals(create_v3(0, 0, 50))
    
    def test_mark_from_custom_point(self):
        """Test marking a line from a custom point going into timber"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Create measurement: 3 units into timber from FRONT face at custom point
        custom_point = create_v3(2, 5, 30)  # FRONT face is at y=5
        measurement = DistanceFromPointIntoFace(
            distance=Rational(3),
            timber=timber,
            face=TimberFace.FRONT,
            point=custom_point
        )
        
        point = measurement.locate()
        
        # Line should point away from FRONT face (negative Y direction)
        assert point.position.equals(create_v3(2, 2, 30))


class TestDistanceFromLongEdgeOnFaceMark:
    """Test DistanceFromLongEdgeOnFace.mark() method"""
    
    def test_mark_on_right_face(self):
        """Test marking a line parallel to edge on RIGHT face"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Create measurement: 2 units from RIGHT_FRONT edge onto RIGHT face
        measurement = DistanceFromLongEdgeOnFace(
            distance=Rational(2),
            timber=timber,
            edge=TimberLongEdge.RIGHT_FRONT,
            face=TimberFace.RIGHT
        )
        
        line = measurement.locate()
        
        # Line should be parallel to timber length (Z direction)
        assert line.direction.equals(create_v3(0, 0, 1))
        # RIGHT_FRONT edge is at (5, 5, 0), moving 2 units in +Y (FRONT) direction gives (5, 7, 0)
        assert line.point.equals(create_v3(5, 7, 0))
    
    def test_mark_on_front_face(self):
        """Test marking a line parallel to edge on FRONT face"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Create measurement: 3 units from LEFT_BACK edge onto BACK face
        measurement = DistanceFromLongEdgeOnFace(
            distance=Rational(3),
            timber=timber,
            edge=TimberLongEdge.LEFT_BACK,
            face=TimberFace.BACK
        )
        
        line = measurement.locate()
        
        # Line should be parallel to timber length (Z direction)
        assert line.direction.equals(create_v3(0, 0, 1))
        # LEFT_BACK edge is at (-5, -5, 0), moving 3 units in -X (LEFT) direction gives (-8, -5, 0)
        assert line.point.equals(create_v3(-8, -5, 0))


class TestMeasureOntoCenterline:
    """Test mark_distance_from_end_along_centerline function"""
    
    def test_locate_plane_onto_centerline(self, symbolic_mode):
        """Test measuring a plane intersection onto centerline"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Create a horizontal plane at z=30
        plane = UnsignedPlane(create_v3(0, 0, 1), create_v3(0, 0, 30))
        
        marking = mark_distance_from_end_along_centerline(plane, timber)
        
        # Should return a DistanceFromPointIntoFace measurement
        assert isinstance(marking, DistanceFromPointIntoFace)
        # Distance should be 30 (from bottom at z=0 to plane at z=30)
        assert marking.distance == Rational(30)
        # Face should be BOTTOM (measuring from bottom)
        assert marking.face == TimberFace.BOTTOM
        # Timber should be the one we passed
        assert marking.timber == timber
        # Point should be at bottom centerline position
        assert marking.point is not None
        assert marking.point.equals(create_v3(0, 0, 0))
        
        # Test round-trip: mark should return a line at the correct position
        point = marking.locate()
        assert point.position.equals(create_v3(0, 0, 30))  # At the plane location
    
    def test_locate_line_onto_centerline(self, symbolic_mode):
        """Test measuring closest point between a line and centerline"""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 10),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Create a line parallel to X-axis at z=40, y=5
        line = Line(create_v3(1, 0, 0), create_v3(0, 5, 40))
        
        marking = mark_distance_from_end_along_centerline(line, timber)
        
        # Should return a DistanceFromPointIntoFace measurement
        assert isinstance(marking, DistanceFromPointIntoFace)
        # Distance should be 40 (closest point on centerline to the line is at z=40)
        assert marking.distance == Rational(40)
        # Face should be BOTTOM
        assert marking.face == TimberFace.BOTTOM
        # Timber should be the one we passed
        assert marking.timber == timber
        # Point should be at bottom centerline position
        assert marking.point is not None
        assert marking.point.equals(create_v3(0, 0, 0))
        
        # Test round-trip
        marked_point = marking.locate()
        assert marked_point.position.equals(create_v3(0, 0, 40))


class TestMarkPlaneFromEdgeInDirection:
    """Tests for mark_plane_from_edge_in_direction function"""

    def test_round_trip_with_measure(self, symbolic_mode):
        """measure then mark should recover the original direction and distance."""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        direction = create_v3(1, 0, 0)
        distance = Rational(7)
        plane = locate_plane_from_edge_in_direction(timber, TimberCenterline.CENTERLINE, direction, distance)
        result = mark_plane_from_edge_in_direction(plane, timber, TimberCenterline.CENTERLINE)
        assert result.direction.equals(direction)
        assert result.distance == distance
        assert result.locate().point.equals(plane.point)

    def test_round_trip_diagonal_timber_and_direction(self):
        """Round-trip on a diagonal timber with a non-axis-aligned direction."""
        from kumiki.rule import safe_normalize_vector as normalize_vector, zero_test
        from sympy import simplify

        timber = timber_from_directions(
            length=Rational(60),
            size=create_v2(4, 6),
            bottom_position=create_v3(10, 20, 5),
            length_direction=normalize_vector(create_v3(1, 1, 0)),
            width_direction=normalize_vector(create_v3(-1, 1, 0)),
            ticket="diag_timber"
        )
        direction = normalize_vector(create_v3(2, -1, 3))
        distance = Rational(11, 3)
        plane = locate_plane_from_edge_in_direction(
            timber, TimberEdge.RIGHT_FRONT, direction, distance
        )
        result = mark_plane_from_edge_in_direction(plane, timber, TimberEdge.RIGHT_FRONT)
        assert result.direction.equals(direction)
        assert zero_test(simplify(result.distance - distance))
        round_trip_plane = result.locate()
        for i in range(3):
            assert zero_test(simplify(round_trip_plane.point[i] - plane.point[i]))


class TestPointFromCornerInFaceDirection:
    """Tests for PointFromCornerInFaceDirection"""

    def test_valid_and_invalid_face_direction(self, symbolic_mode):
        """TOP is valid from BOT_RIGHT_FRONT (points inward); RIGHT is invalid (points outward)."""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        valid = PointFromCornerInFaceDirection(
            timber=timber,
            corner=TimberCorner.BOT_RIGHT_FRONT,
            face=TimberFace.TOP,
            distance=Rational(3),
        )
        pt = valid.locate()
        assert pt.position[0] == Rational(5)
        assert pt.position[1] == Rational(10)
        assert pt.position[2] == Rational(3)

        import pytest
        invalid = PointFromCornerInFaceDirection(
            timber=timber,
            corner=TimberCorner.BOT_RIGHT_FRONT,
            face=TimberFace.RIGHT,
            distance=Rational(3),
        )
        with pytest.raises(AssertionError, match="points away"):
            invalid.locate()


class TestMarkDistanceFromCornerAlongEdge:
    """Tests for mark_distance_from_corner_along_edge_by_intersecting_plane"""

    def test_intersect_plane_with_centerline(self, symbolic_mode):
        """Plane at z=30 intersects the centerline of a 100-long vertical timber.
        From BOTTOM (z=0), distance should be 30."""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        plane = Plane(normal=create_v3(0, 0, 1), point=create_v3(0, 0, 30))
        result = mark_distance_from_corner_along_edge_by_intersecting_plane(
            plane, timber, TimberCenterline.CENTERLINE, TimberReferenceEnd.BOTTOM
        )
        assert isinstance(result, DistanceFromCornerAlongEdge)
        assert result.distance == Rational(30)
        assert result.end == TimberReferenceEnd.BOTTOM
        pt = result.locate()
        assert pt.position[2] == Rational(30)

    def test_closest_point_on_centerline_to_perpendicular_line(self, symbolic_mode):
        """A horizontal line at z=40 perpendicular to a vertical timber's centerline.
        The closest point on the centerline is at z=40, so distance from BOTTOM = 40."""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        horiz_line = Line(direction=create_v3(1, 0, 0), point=create_v3(5, 0, 40))
        result = mark_distance_from_corner_along_edge_by_finding_closest_point_on_line(
            horiz_line, timber, TimberCenterline.CENTERLINE, TimberReferenceEnd.BOTTOM
        )
        assert isinstance(result, DistanceFromCornerAlongEdge)
        assert result.distance == Rational(40)
        pt = result.locate()
        assert pt.position[0] == Rational(0)
        assert pt.position[1] == Rational(0)
        assert pt.position[2] == Rational(40)
