"""
Tests for timber_shavings module (random timber-related helpers).
"""

import pytest
from kumiki.timber_shavings import *
from kumiki.timber import *
from kumiki.rule import create_v3, create_v2, radians
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber,
)
from sympy import Rational


class TestFindOpposingFaceOnAnotherTimber:
    """Tests for find_opposing_face_on_another_timber function."""
    
    def test_face_aligned_timbers(self):
        """Test finding opposing face on two face-aligned timbers."""
        # Create two 4x6 timbers that are face-aligned
        timber_size = create_v2(inches(4), inches(6))
        
        # Timber A pointing east (along X-axis)
        timber_a = timber_from_directions(
            length=inches(36),
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # East
            width_direction=create_v3(0, 1, 0),   # North
            ticket="timber_a"
        )
        # Timber A has:
        # - length_direction = (1, 0, 0) = East
        # - width_direction = (0, 1, 0) = North
        # - height_direction = (0, 0, 1) = Up
        # - RIGHT face points North: (0, 1, 0)
        # - LEFT face points South: (0, -1, 0)
        # - FRONT face points Up: (0, 0, 1)
        # - BACK face points Down: (0, 0, -1)
        
        # Timber B pointing east, offset in Y direction (north)
        timber_b = timber_from_directions(
            length=inches(36),
            size=timber_size,
            bottom_position=create_v3(0, inches(10), 0),  # 10 inches north
            length_direction=create_v3(1, 0, 0),  # East
            width_direction=create_v3(0, 1, 0),   # North
            ticket="timber_b"
        )
        # Timber B has same orientation as Timber A
        # - RIGHT face points North: (0, 1, 0)
        # - LEFT face points South: (0, -1, 0)
        
        # Find opposing face: Timber A's RIGHT face (North) should oppose Timber B's LEFT face (South)
        opposing_face = find_opposing_face_on_another_timber(
            reference_timber=timber_a,
            reference_face=TimberLongFace.RIGHT,
            target_timber=timber_b
        )
        
        # The opposing face should be LEFT (which points South, opposite of RIGHT which points North)
        assert opposing_face == TimberFace.LEFT, \
            f"Expected LEFT face, got {opposing_face}"
        
        # Verify the faces are parallel by checking their directions
        reference_direction = timber_a.get_face_direction_global(TimberLongFace.RIGHT)
        target_direction = timber_b.get_face_direction_global(opposing_face)
        assert are_vectors_parallel(reference_direction, target_direction), \
            "Reference and target faces should be parallel"
    
    def test_timbers_at_30_degrees_in_xy_plane(self):
        """Test finding opposing face on two timbers at 30 degrees to each other in the XY plane."""
        from sympy import cos, sin, pi, sqrt
        
        # Both timbers lying flat in XY plane (height points up in Z)
        timber_size = create_v2(inches(4), inches(6))
        
        # Timber A pointing along X-axis (East)
        timber_a = timber_from_directions(
            length=inches(36),
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # East
            width_direction=create_v3(0, 1, 0),   # North
            ticket="timber_a"
        )
        # Timber A:
        # - length_direction = (1, 0, 0) = East
        # - width_direction = (0, 1, 0) = North  
        # - height_direction = (0, 0, 1) = Up
        # - RIGHT face points North: (0, 1, 0)
        # - BACK face points Down: (0, 0, -1)
        # - FRONT face points Up: (0, 0, 1)
        
        # Timber B at 30 degrees counterclockwise from X-axis in XY plane
        # length_direction at 30 degrees: (cos(30°), sin(30°), 0)
        angle = radians(pi / 6)  # 30 degrees in radians
        length_dir_b = create_v3(cos(angle), sin(angle), 0)
        
        # width_direction perpendicular to length in XY plane: (-sin(30°), cos(30°), 0)
        width_dir_b = create_v3(-sin(angle), cos(angle), 0)
        
        timber_b = timber_from_directions(
            length=inches(36),
            size=timber_size,
            bottom_position=create_v3(inches(20), 0, 0),
            length_direction=length_dir_b,
            width_direction=width_dir_b,
            ticket="timber_b"
        )
        # Timber B:
        # - length_direction = (cos(30°), sin(30°), 0) ≈ (0.866, 0.5, 0)
        # - width_direction = (-sin(30°), cos(30°), 0) ≈ (-0.5, 0.866, 0)
        # - height_direction = (0, 0, 1) = Up (same as Timber A)
        # - FRONT face points Up: (0, 0, 1) - parallel to Timber A's FRONT
        # - BACK face points Down: (0, 0, -1) - parallel to Timber A's BACK
        
        # Find opposing face: Timber A's FRONT face (Up) should oppose Timber B's BACK face (Down)
        opposing_face = find_opposing_face_on_another_timber(
            reference_timber=timber_a,
            reference_face=TimberLongFace.FRONT,
            target_timber=timber_b
        )
        
        # The opposing face should be BACK (which points Down, opposite of FRONT which points Up)
        assert opposing_face == TimberFace.BACK, \
            f"Expected BACK face, got {opposing_face}"
        
        # Verify the faces are parallel by checking their directions
        reference_direction = timber_a.get_face_direction_global(TimberLongFace.FRONT)
        target_direction = timber_b.get_face_direction_global(opposing_face)
        assert are_vectors_parallel(reference_direction, target_direction), \
            "Reference and target faces should be parallel"
        
        # Also verify that they point in opposite directions
        dot_product = reference_direction.dot(target_direction)
        assert dot_product < 0, \
            f"Faces should point in opposite directions (negative dot product), got {dot_product}"
    
    def test_assertion_fails_for_non_parallel_faces(self):
        """Test that the function raises an assertion error when no parallel face exists."""
        timber_size = create_v2(inches(4), inches(6))
        
        # Timber A pointing east
        timber_a = timber_from_directions(
            length=inches(36),
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # East
            width_direction=create_v3(0, 1, 0),   # North
            ticket="timber_a"
        )
        
        # Timber B pointing up (perpendicular to Timber A)
        # This timber has no faces parallel to Timber A's RIGHT face
        timber_b = timber_from_directions(
            length=inches(36),
            size=timber_size,
            bottom_position=create_v3(inches(20), 0, 0),
            length_direction=create_v3(0, 0, 1),  # Up
            width_direction=create_v3(1, 0, 0),   # East
            ticket="timber_b"
        )
        # Timber B:
        # - length_direction = (0, 0, 1) = Up
        # - width_direction = (1, 0, 0) = East
        # - height_direction = (0, 1, 0) = North
        # - RIGHT face points East: (1, 0, 0)
        # - FRONT face points North: (0, 1, 0)
        # - BACK face points South: (0, -1, 0)
        # None of these are parallel to Timber A's RIGHT face which points North (0, 1, 0)
        # Actually wait, FRONT points North which IS parallel to Timber A's RIGHT
        
        # Let me use a more complex orientation
        from sympy import sqrt
        
        # Timber B with non-axis-aligned orientation
        timber_b = timber_from_directions(
            length=inches(36),
            size=timber_size,
            bottom_position=create_v3(inches(20), 0, 0),
            length_direction=create_v3(1, 1, 1) / sqrt(3),  # Diagonal direction
            width_direction=create_v3(-1, 1, 0) / sqrt(2),  # Perpendicular in a different plane
            ticket="timber_b"
        )
        
        # Should raise an AssertionError because no face on timber_b is parallel to timber_a's RIGHT face
        with pytest.raises(AssertionError) as excinfo:
            find_opposing_face_on_another_timber(
                reference_timber=timber_a,
                reference_face=TimberLongFace.RIGHT,
                target_timber=timber_b
            )
        
        # Check that the error message mentions parallel
        assert "parallel" in str(excinfo.value).lower()
        


# ============================================================================
# Tests for Peg and Wedge Joint Accessories
# ============================================================================

class TestPegShape:
    """Test PegShape enum."""
    
    def test_peg_shape_enum(self):
        """Test PegShape enum values."""
        assert PegShape.SQUARE.value == "square"
        assert PegShape.ROUND.value == "round"


class TestPeg:
    """Test Peg class."""
    
    def test_peg_creation(self):
        """Test basic Peg creation."""
        orientation = Orientation.identity()
        position = create_v3(1, 2, 3)
        
        peg = Peg(
            transform=Transform(position=position, orientation=orientation),
            size=Rational(2),
            shape=PegShape.SQUARE,
            forward_length=Rational(10),
            stickout_length=Rational(1)
        )
        
        assert peg.transform.orientation == orientation
        assert peg.transform.position == position
        assert peg.size == Rational(2)
        assert peg.shape == PegShape.SQUARE
        assert peg.forward_length == Rational(10)
        assert peg.stickout_length == Rational(1)
    
    def test_peg_is_frozen(self):
        """Test that Peg is immutable."""
        peg = Peg(
            transform=Transform.identity(),
            size=Rational(2),
            shape=PegShape.ROUND,
            forward_length=Rational(10),
            stickout_length=Rational(1)
        )
        
        with pytest.raises(Exception):  # FrozenInstanceError
            peg.size = Rational(3)  # type: ignore
    
    def test_peg_render_csg_local_square(self):
        """Test rendering square peg CSG in local space."""
        peg = Peg(
            transform=Transform.identity(),
            size=Rational(2),
            shape=PegShape.SQUARE,
            forward_length=Rational(10),
            stickout_length=Rational(1)
        )
        
        csg = peg.render_csg_local()
        
        # Should return a RectangularPrism
        from kumiki.cutcsg import RectangularPrism
        assert isinstance(csg, RectangularPrism)
        
        # Verify dimensions
        assert csg.size[0] == Rational(2)  # width
        assert csg.size[1] == Rational(2)  # height
        assert csg.start_distance == Rational(-1)  # stickout_length
        assert csg.end_distance == Rational(10)  # forward_length
    
    def test_peg_render_csg_local_round(self):
        """Test rendering round peg CSG in local space."""
        peg = Peg(
            transform=Transform.identity(),
            size=Rational(4),
            shape=PegShape.ROUND,
            forward_length=Rational(12),
            stickout_length=Rational(2)
        )
        
        csg = peg.render_csg_local()
        
        # Should return a Cylinder
        from kumiki.cutcsg import Cylinder
        assert isinstance(csg, Cylinder)
        
        # Verify dimensions
        assert csg.radius == Rational(2)  # diameter / 2
        assert csg.start_distance == Rational(-2)  # stickout_length
        assert csg.end_distance == Rational(12)  # forward_length


class TestWedge:
    """Test Wedge class."""
    
    def test_wedge_creation(self):
        """Test basic Wedge creation."""
        orientation = Orientation.identity()
        position = create_v3(1, 2, 3)
        
        wedge = Wedge(
            transform=Transform(position=position, orientation=orientation),
            base_width=Rational(5),
            tip_width=Rational(1),
            height=Rational(2),
            length=Rational(10)
        )
        
        assert wedge.transform.orientation == orientation
        assert wedge.transform.position == position
        assert wedge.base_width == Rational(5)
        assert wedge.tip_width == Rational(1)
        assert wedge.height == Rational(2)
        assert wedge.length == Rational(10)
    
    def test_wedge_width_property(self):
        """Test that width property is an alias for base_width."""
        wedge = Wedge(
            transform=Transform.identity(),
            base_width=Rational(5),
            tip_width=Rational(1),
            height=Rational(2),
            length=Rational(10)
        )
        
        assert wedge.width == wedge.base_width
        assert wedge.width == Rational(5)
    
    def test_wedge_is_frozen(self):
        """Test that Wedge is immutable."""
        wedge = Wedge(
            transform=Transform.identity(),
            base_width=Rational(5),
            tip_width=Rational(1),
            height=Rational(2),
            length=Rational(10)
        )
        
        with pytest.raises(Exception):  # FrozenInstanceError
            wedge.base_width = Rational(6)  # type: ignore
    
    def test_wedge_render_csg_local(self):
        """Test rendering wedge CSG in local space."""
        wedge = Wedge(
            transform=Transform.identity(),
            base_width=Rational(5),
            tip_width=Rational(1),
            height=Rational(2),
            length=Rational(10)
        )
        
        csg = wedge.render_csg_local()
        
        # Should return a ConvexPolygonExtrusion 
        from kumiki.cutcsg import ConvexPolygonExtrusion
        assert isinstance(csg, ConvexPolygonExtrusion)
        


class TestCreatePegGoingIntoFace:
    """Test create_peg_going_into_face helper function."""
    
    def setup_method(self):
        """Create a standard vertical timber for testing."""
        self.timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(Rational(10), Rational(15)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
    
    def test_peg_into_right_face(self):
        """Test creating a peg going into the RIGHT face."""
        peg = create_peg_going_into_face(
            timber=self.timber,
            face=TimberLongFace.RIGHT,
            distance_from_bottom=Rational(50),
            distance_from_centerline=Rational(0),
            peg_size=Rational(2),
            peg_shape=PegShape.ROUND,
            forward_length=Rational(8),
            stickout_length=Rational(1)
        )
        
        assert peg.size == Rational(2)
        assert peg.shape == PegShape.ROUND
        assert peg.forward_length == Rational(8)
        assert peg.stickout_length == Rational(1)
        
        # Position should be at the right surface (width/2 = 5)
        assert peg.transform.position[0] == Rational(5)  # X = width/2
        assert peg.transform.position[1] == Rational(0)  # Y = distance_from_centerline
        assert peg.transform.position[2] == Rational(50)  # Z = distance_from_bottom
    
    def test_peg_into_left_face(self):
        """Test creating a peg going into the LEFT face."""
        peg = create_peg_going_into_face(
            timber=self.timber,
            face=TimberLongFace.LEFT,
            distance_from_bottom=Rational(30),
            distance_from_centerline=Rational(2),
            peg_size=Rational(2),
            peg_shape=PegShape.ROUND,
            forward_length=Rational(8),
            stickout_length=Rational(1)
        )
        
        # Position should be at the left surface (-width/2 = -5)
        assert peg.transform.position[0] == Rational(-5)  # X = -width/2
        assert peg.transform.position[1] == Rational(2)  # Y = distance_from_centerline
        assert peg.transform.position[2] == Rational(30)  # Z = distance_from_bottom
    
    def test_peg_into_forward_face(self):
        """Test creating a peg going into the FRONT face."""
        peg = create_peg_going_into_face(
            timber=self.timber,
            face=TimberLongFace.FRONT,
            distance_from_bottom=Rational(40),
            distance_from_centerline=Rational(-1),
            peg_size=Rational(2),
            peg_shape=PegShape.ROUND,
            forward_length=Rational(8),
            stickout_length=Rational(1)
        )
        
        # Position should be at the forward surface (height/2 = 7.5)
        assert peg.transform.position[0] == Rational(-1)  # X = distance_from_centerline
        assert peg.transform.position[1] == Rational(15, 2)  # Y = height/2 = 7.5
        assert peg.transform.position[2] == Rational(40)  # Z = distance_from_bottom
    
    def test_peg_into_back_face(self):
        """Test creating a peg going into the BACK face."""
        peg = create_peg_going_into_face(
            timber=self.timber,
            face=TimberLongFace.BACK,
            distance_from_bottom=Rational(60),
            distance_from_centerline=Rational(3),
            peg_size=Rational(2),
            peg_shape=PegShape.ROUND,
            forward_length=Rational(8),
            stickout_length=Rational(1)
        )
        
        # Position should be at the back surface (-height/2 = -7.5)
        assert peg.transform.position[0] == Rational(3)  # X = distance_from_centerline
        assert peg.transform.position[1] == Rational(-15, 2)  # Y = -height/2 = -7.5
        assert peg.transform.position[2] == Rational(60)  # Z = distance_from_bottom
    
    def test_square_peg(self):
        """Test creating a square peg."""
        peg = create_peg_going_into_face(
            timber=self.timber,
            face=TimberLongFace.RIGHT,
            distance_from_bottom=Rational(50),
            distance_from_centerline=Rational(0),
            peg_size=Rational(3),
            peg_shape=PegShape.SQUARE,
            forward_length=Rational(8),
            stickout_length=Rational(1)
        )
        
        assert peg.shape == PegShape.SQUARE
        assert peg.size == Rational(3)


class TestProjectGlobalPointOntoTimberFace:
    """Test Timber.project_global_point_onto_timber_face_global() method."""
    
    def test_project_onto_top_face_axis_aligned(self, symbolic_mode):
        """Test projecting a point onto the top face of an axis-aligned timber."""
        # Create a simple vertical timber
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
        # Project a point in the middle of the timber onto the top face
        global_point = create_v3(0, 0, Rational("0.5"))  # Halfway up the timber
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.TOP)
        
        # The projected point should be at the top face (Z = length = 2)
        # In local coords, top face is at Z = length/2 = 1
        # In global coords (since timber bottom is at 0,0,0), top face center is at 0,0,1
        expected_global = create_v3(0, 0, 1)
        assert projected_global == expected_global
    
    def test_project_onto_bottom_face_axis_aligned(self, symbolic_mode):
        """Test projecting a point onto the bottom face."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Project a point onto the bottom face
        global_point = create_v3(Rational("0.05"), Rational("0.1"), Rational("0.5"))
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.BOTTOM)
        
        # Bottom face is at Z = -length/2 = -1 in local coords
        # In global coords, that's 0,0,-1 relative to bottom_position (0,0,0)
        # So the projected point should maintain X,Y but be at Z = -1
        expected_global = create_v3(Rational("0.05"), Rational("0.1"), -1)
        assert projected_global == expected_global
    
    def test_project_onto_right_face_axis_aligned(self, symbolic_mode):
        """Test projecting a point onto the right face."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Project a point in the middle onto the right face
        global_point = create_v3(0, 0, 0)  # Center of timber
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.RIGHT)
        
        # Right face is at X = width/2 = 0.1 in local coords
        # In global coords (axis-aligned), that's 0.1, 0, 0
        expected_global = create_v3(Rational("0.1"), 0, 0)
        assert projected_global == expected_global
    
    def test_project_onto_left_face_axis_aligned(self, symbolic_mode):
        """Test projecting a point onto the left face."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Project a point onto the left face
        global_point = create_v3(Rational("0.05"), Rational("0.1"), Rational("0.5"))
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.LEFT)
        
        # Left face is at X = -width/2 = -0.1 in local coords
        expected_global = create_v3(Rational("-0.1"), Rational("0.1"), Rational("0.5"))
        assert projected_global == expected_global
    
    def test_project_onto_front_face_axis_aligned(self, symbolic_mode):
        """Test projecting a point onto the front face."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Project a point onto the front face
        global_point = create_v3(0, 0, 0)
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.FRONT)
        
        # Front face is at Y = height/2 = 0.15 in local coords
        expected_global = create_v3(0, Rational("0.15"), 0)
        assert projected_global == expected_global
    
    def test_project_onto_back_face_axis_aligned(self, symbolic_mode):
        """Test projecting a point onto the back face."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Project a point onto the back face
        global_point = create_v3(Rational("0.05"), Rational("0.05"), Rational("0.5"))
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.BACK)
        
        # Back face is at Y = -height/2 = -0.15 in local coords
        expected_global = create_v3(Rational("0.05"), Rational("-0.15"), Rational("0.5"))
        assert projected_global == expected_global
    
    def test_project_point_already_on_face(self, symbolic_mode):
        """Test that projecting a point already on the face returns the same point."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Point already on the top face (Z = 1 in global coords)
        global_point = create_v3(Rational("0.05"), Rational("0.1"), 1)
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.TOP)
        
        # Should return the same point in global coords
        expected_global = create_v3(Rational("0.05"), Rational("0.1"), 1)
        assert projected_global == expected_global
    
    def test_project_onto_rotated_timber(self, symbolic_mode):
        """Test projecting onto a face of a rotated timber."""
        # Create a timber pointing east (along X-axis)
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),   # X-direction (east)
            width_direction=create_v3(0, 1, 0)      # Y-direction (north)
        )
        
        # Project a point in the middle onto the TOP face
        # In global coords, center of timber is at origin
        global_point = create_v3(0, 0, 0)
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.TOP)
        
        # For this timber, local Z-axis (length) points in global X direction
        # So top face center in local coords (0, 0, 1) maps to global (1, 0, 0)
        expected_global = create_v3(1, 0, 0)
        assert projected_global == expected_global
    
    def test_project_with_offset_bottom_position(self, symbolic_mode):
        """Test projection on a timber with non-zero bottom position."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(5, 10, 20),  # Offset position
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        # Project center of timber (in global coords: 5, 10, 20) onto top face
        global_point = create_v3(5, 10, 20)
        projected_global = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.TOP)
        
        # Top face in local coords is at Z=1, which in global should be at (5, 10, 21)
        expected_global = create_v3(5, 10, 21)
        assert projected_global == expected_global
    
    def test_project_accepts_timber_reference_end(self, symbolic_mode):
        """Test that the method accepts TimberReferenceEnd as well as TimberFace."""
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        global_point = create_v3(0, 0, 0)
        
        # Should work with TimberReferenceEnd.TOP
        projected_with_end = timber.project_global_point_onto_timber_face_global(global_point, TimberReferenceEnd.TOP)
        projected_with_face = timber.project_global_point_onto_timber_face_global(global_point, TimberFace.TOP)
        
        # Both should give the same result
        assert projected_with_end == projected_with_face


class TestCreateWedgeInTimberEnd:
    """Test create_wedge_in_timber_end helper function."""
    
    def setup_method(self):
        """Create a standard vertical timber for testing."""
        self.timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(Rational(10), Rational(15)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        self.wedge_spec = WedgeShape(
            base_width=Rational(5),
            tip_width=Rational(1),
            height=Rational(2),
            length=Rational(10)
        )
    
    def test_wedge_at_top_end(self):
        """Test creating a wedge at the TOP end."""
        wedge = create_wedge_in_timber_end(
            timber=self.timber,
            end=TimberReferenceEnd.TOP,
            position=create_v3(Rational(2), Rational(3), 0),
            shape=self.wedge_spec
        )
        
        assert wedge.base_width == Rational(5)
        assert wedge.tip_width == Rational(1)
        assert wedge.height == Rational(2)
        assert wedge.length == Rational(10)
        assert wedge.width == Rational(5)  # Test width property
        
        # Position should be at the top end (Z = length)
        assert wedge.transform.position[0] == Rational(2)  # X from position
        assert wedge.transform.position[1] == Rational(3)  # Y from position
        assert wedge.transform.position[2] == Rational(100)  # Z = timber length
    
    def test_wedge_at_bottom_end(self):
        """Test creating a wedge at the BOTTOM end."""
        wedge = create_wedge_in_timber_end(
            timber=self.timber,
            end=TimberReferenceEnd.BOTTOM,
            position=create_v3(Rational(-1), Rational(2), 0),
            shape=self.wedge_spec
        )
        
        # Position should be at the bottom end (Z = 0)
        assert wedge.transform.position[0] == Rational(-1)  # X from position
        assert wedge.transform.position[1] == Rational(2)  # Y from position
        assert wedge.transform.position[2] == Rational(0)  # Z = 0 (bottom)
    
    def test_wedge_at_centerline(self):
        """Test creating a wedge at the timber centerline."""
        wedge = create_wedge_in_timber_end(
            timber=self.timber,
            end=TimberReferenceEnd.TOP,
            position=create_v3(0, 0, 0),  # Center of cross-section
            shape=self.wedge_spec
        )
        
        # Position should be at center of top end
        assert wedge.transform.position[0] == Rational(0)
        assert wedge.transform.position[1] == Rational(0)
        assert wedge.transform.position[2] == Rational(100)


class TestWedgeShape:
    """Test WedgeShape specification class."""
    
    def test_wedge_shape_creation(self):
        """Test WedgeShape creation."""
        shape = WedgeShape(
            base_width=Rational(6),
            tip_width=Rational(2),
            height=Rational(3),
            length=Rational(12)
        )
        
        assert shape.base_width == Rational(6)
        assert shape.tip_width == Rational(2)
        assert shape.height == Rational(3)
        assert shape.length == Rational(12)
    
    def test_wedge_shape_is_frozen(self):
        """Test that WedgeShape is immutable."""
        shape = WedgeShape(
            base_width=Rational(5),
            tip_width=Rational(1),
            height=Rational(2),
            length=Rational(10)
        )
        
        with pytest.raises(Exception):  # FrozenInstanceError
            shape.base_width = Rational(7)  # type: ignore


class TestTimberRelationshipHelpers:
    """Tests for timber relationship helper functions."""
    
    def testare_timbers_parallel(self):
        """Test are_timbers_parallel helper function."""
        from kumiki.timber_shavings import are_timbers_parallel
        # Create two timbers with parallel length directions
        timber1 = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
        timber2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.15"), Rational("0.25")),
            bottom_position=create_v3(2, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Same direction
            width_direction=create_v3(0, 1, 0)      # Different face direction
        )
        
        # Should be parallel (parallel length directions)
        assert are_timbers_parallel(timber1, timber2)
        
        # Create a timber with opposite direction (still parallel)
        timber3 = timber_from_directions(
            length=Rational("1.5"),
            size=create_v2(Rational("0.1"), Rational("0.2")),
            bottom_position=create_v3(-1, 0, 0),
            length_direction=create_v3(0, 0, -1),  # Opposite direction
            width_direction=create_v3(1, 0, 0)
        )
        
        # Should still be parallel (anti-parallel is still parallel)
        assert are_timbers_parallel(timber1, timber3)
        
        # Create a timber with perpendicular direction
        timber4 = timber_from_directions(
            length=Rational("2.5"),
            size=create_v2(Rational("0.3"), Rational("0.3")),
            bottom_position=create_v3(1, 1, 0),
            length_direction=create_v3(1, 0, 0),   # Perpendicular
            width_direction=create_v3(0, 0, 1)
        )
        
        # Should NOT be parallel
        assert not are_timbers_parallel(timber1, timber4)
    
    def testare_timbers_orthogonal(self):
        """Test are_timbers_orthogonal helper function."""
        from kumiki.timber_shavings import are_timbers_orthogonal
        # Create two timbers with perpendicular length directions
        timber1 = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
        timber2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.15"), Rational("0.25")),
            bottom_position=create_v3(2, 0, 0),
            length_direction=create_v3(1, 0, 0),   # X-right (perpendicular to timber1)
            width_direction=create_v3(0, 0, 1)      # Z-up
        )
        
        # Should be orthogonal
        assert are_timbers_orthogonal(timber1, timber2)
        
        # Create a timber with parallel direction
        timber3 = timber_from_directions(
            length=Rational("1.5"),
            size=create_v2(Rational("0.1"), Rational("0.2")),
            bottom_position=create_v3(-1, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Same as timber1
            width_direction=create_v3(1, 0, 0)
        )
        
        # Should NOT be orthogonal
        assert not are_timbers_orthogonal(timber1, timber3)
        
        # Test with Y-direction
        timber4 = timber_from_directions(
            length=Rational("2.5"),
            size=create_v2(Rational("0.3"), Rational("0.3")),
            bottom_position=create_v3(1, 1, 0),
            length_direction=create_v3(0, 1, 0),   # Y-forward (perpendicular to timber1)
            width_direction=create_v3(1, 0, 0)
        )
        
        # Should be orthogonal
        assert are_timbers_orthogonal(timber1, timber4)
    
    def testare_timbers_face_aligned(self):
        """Test are_timbers_face_aligned helper function."""
        from kumiki.timber_shavings import are_timbers_face_aligned
        # Create a reference timber with standard orientation
        timber1 = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        # timber1 directions: length=[0,0,1], face=[1,0,0], height=[0,1,0]
        
        # Test 1: Timber with same orientation - should be face-aligned
        timber2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.15"), Rational("0.25")),
            bottom_position=create_v3(2, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Same as timber1
            width_direction=create_v3(1, 0, 0)      # Same as timber1
        )
        assert are_timbers_face_aligned(timber1, timber2)
        
        # Test 2: Timber rotated 90° around Z - should be face-aligned  
        # (length stays Z, but face becomes Y, height becomes -X)
        timber3 = timber_from_directions(
            length=Rational("1.5"),
            size=create_v2(Rational("0.1"), Rational("0.2")),
            bottom_position=create_v3(-1, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Same Z
            width_direction=create_v3(0, 1, 0)      # Y direction
        )
        assert are_timbers_face_aligned(timber1, timber3)
        
        # Test 3: Timber rotated 90° around X - should be face-aligned
        # (length becomes -Y, face stays X, height becomes Z) 
        timber4 = timber_from_directions(
            length=Rational("2.5"),
            size=create_v2(Rational("0.3"), Rational("0.3")),
            bottom_position=create_v3(1, 1, 0),
            length_direction=create_v3(0, -1, 0),  # -Y direction
            width_direction=create_v3(1, 0, 0)      # Same X
        )
        assert are_timbers_face_aligned(timber1, timber4)
        
        # Test 4: Timber with perpendicular orientation but face-aligned
        # (length becomes X, face becomes Z, height becomes Y)
        timber5 = timber_from_directions(
            length=Rational("1.8"),
            size=create_v2(Rational("0.2"), Rational("0.2")),
            bottom_position=create_v3(0, 2, 0),
            length_direction=create_v3(1, 0, 0),   # X direction  
            width_direction=create_v3(0, 0, 1)      # Z direction
        )
        assert are_timbers_face_aligned(timber1, timber5)
        
        # Test 5: Timber with arbitrary 3D rotation - should NOT be face-aligned
        # Using a rotation that doesn't align any direction with cardinal axes
        import math
        # Create a rotation that's 30° around X, then 45° around the new Y
        cos30 = math.cos(math.pi/6)
        sin30 = math.sin(math.pi/6)
        cos45 = math.cos(math.pi/4)
        sin45 = math.sin(math.pi/4)
        
        # This creates a timber whose directions don't align with any cardinal axes
        timber6 = timber_from_directions(
            length=Rational(1),
            size=create_v2(Rational("0.1"), Rational("0.1")),
            bottom_position=create_v3(0, 0, 2),
            length_direction=create_v3(Float(sin45*cos30), Float(sin45*sin30), Float(cos45)),  # Complex 3D direction
            width_direction=create_v3(Float(cos45*cos30), Float(cos45*sin30), Float(-sin45))    # Perpendicular complex direction
        )
        assert not are_timbers_face_aligned(timber1, timber6)
        
        # Test 6: Verify that 45° rotation in XY plane IS face-aligned 
        # (because height direction is still Z, parallel to timber1's length direction)
        cos45_xy = math.cos(math.pi/4)
        sin45_xy = math.sin(math.pi/4)
        timber7 = timber_from_directions(
            length=Rational(1),
            size=create_v2(Rational("0.1"), Rational("0.1")),
            bottom_position=create_v3(0, 0, 2),
            length_direction=create_v3(Float(cos45_xy), Float(sin45_xy), 0),  # 45° in XY plane
            width_direction=create_v3(Float(-sin45_xy), Float(cos45_xy), 0)    # Perpendicular in XY
        )
        # This SHOULD be face-aligned because height direction = [0,0,1] = timber1.get_length_direction_global()
        assert are_timbers_face_aligned(timber1, timber7)
        
        # Test 8: Verify face-aligned timbers can be orthogonal
        # timber1 length=[0,0,1], timber5 length=[1,0,0] - these are orthogonal but face-aligned
        assert are_timbers_face_aligned(timber1, timber5)
        assert are_timbers_orthogonal(timber1, timber5)
        
        # Test 9: Verify face-aligned timbers can be parallel  
        # timber1 and timber2 have same length direction - parallel and face-aligned
        assert are_timbers_face_aligned(timber1, timber2)
        assert are_timbers_parallel(timber1, timber2)
    
    def testare_timbers_parallel_rational(self):
        """Test are_timbers_parallel with rational (exact) values."""
        from kumiki.timber_shavings import are_timbers_parallel
        from sympy import Rational
        
        # Create timbers with exact rational directions
        timber1 = timber_from_directions(
            length=2,
            size=create_v2(Rational(1, 5), Rational(3, 10)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        timber2 = timber_from_directions(
            length=3,
            size=create_v2(Rational(1, 10), Rational(1, 4)),
            bottom_position=create_v3(2, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Parallel
            width_direction=create_v3(0, 1, 0)
        )
        
        # Should be parallel (exact comparison)
        assert are_timbers_parallel(timber1, timber2)
        
        # Test anti-parallel (should still be parallel)
        timber3 = timber_from_directions(
            length=Rational(3, 2),
            size=create_v2(Rational(1, 10), Rational(1, 5)),
            bottom_position=create_v3(-1, 0, 0),
            length_direction=create_v3(0, 0, -1),  # Anti-parallel
            width_direction=create_v3(1, 0, 0)
        )
        
        assert are_timbers_parallel(timber1, timber3)
        
        # Test perpendicular (should not be parallel)
        timber4 = timber_from_directions(
            length=2,
            size=create_v2(Rational(3, 10), Rational(3, 10)),
            bottom_position=create_v3(1, 1, 0),
            length_direction=create_v3(1, 0, 0),  # Perpendicular
            width_direction=create_v3(0, 0, 1)
        )
        
        assert not are_timbers_parallel(timber1, timber4)
    
    def testare_timbers_parallel_float(self):
        """Test are_timbers_parallel with float (fuzzy) values."""
        from kumiki.timber_shavings import are_timbers_parallel
        import math
        
        # Create timbers with float directions
        timber1 = create_standard_vertical_timber(height=2, size=(0.2, 0.3), position=(0, 0, 0))
        
        # Slightly off parallel (within tolerance)
        small_angle = 1e-11
        timber2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.15"), Rational("0.25")),
            bottom_position=create_v3(Rational(2), Rational(0), Rational(0)),
            length_direction=create_v3(Float(math.sin(small_angle)), Rational(0), Float(math.cos(small_angle))),
            width_direction=create_v3(Float(math.cos(small_angle)), Rational(0), Float(-math.sin(small_angle)))
        )
        
        # Should be parallel (fuzzy comparison)
        assert are_timbers_parallel(timber1, timber2)
    
    def testare_timbers_orthogonal_rational(self):
        """Test are_timbers_orthogonal with rational (exact) values."""
        from kumiki.timber_shavings import are_timbers_orthogonal
        from sympy import Rational
        
        # Create timbers with exact rational perpendicular directions
        timber1 = timber_from_directions(
            length=2,
            size=create_v2(Rational(1, 5), Rational(3, 10)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0)
        )
        
        timber2 = timber_from_directions(
            length=3,
            size=create_v2(Rational(15, 100), Rational(1, 4)),
            bottom_position=create_v3(2, 0, 0),
            length_direction=create_v3(1, 0, 0),  # Perpendicular
            width_direction=create_v3(0, 0, 1)
        )
        
        # Should be orthogonal (exact comparison)
        assert are_timbers_orthogonal(timber1, timber2)
        
        # Test non-orthogonal
        timber3 = timber_from_directions(
            length=Rational(3, 2),
            size=create_v2(Rational(1, 10), Rational(1, 5)),
            bottom_position=create_v3(-1, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Parallel to timber1
            width_direction=create_v3(1, 0, 0)
        )
        
        assert not are_timbers_orthogonal(timber1, timber3)
    
    def testare_timbers_orthogonal_fuzzy_fallback(self):
        """Test are_timbers_orthogonal with float (fuzzy) values."""
        from kumiki.timber_shavings import are_timbers_orthogonal
        import math
        
        # Create timbers with float perpendicular directions
        timber1 = create_standard_vertical_timber(height=2, size=(0.2, 0.3), position=(0, 0, 0))
        
        # Nearly perpendicular (within numeric fallback test tolerance)
        small_offset = Rational(1e-20)
        timber2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.15"), Rational("0.25")),
            bottom_position=create_v3(Rational(2), Rational(0), Rational(0)),
            length_direction=create_v3(Rational(1), Rational(0), small_offset),
            width_direction=create_v3(Rational(0), Rational(1), Rational(0))
        )
        
        # Should be orthogonal (fuzzy comparison)
        assert are_timbers_orthogonal(timber1, timber2)
    
    def testare_timbers_face_aligned_exact_equality(self):
        """Test are_timbers_face_aligned with exact equality (no tolerance)."""
        from kumiki.timber_shavings import are_timbers_face_aligned
        # Create two face-aligned timbers using exact rational values
        timber1 = timber_from_directions(
            length=2,  # Integer
            size=create_v2(Rational(1, 5), Rational(3, 10)),  # Exact rationals
            bottom_position=create_v3(0, 0, 0),  # Integers
            length_direction=create_v3(0, 0, 1),   # Vertical - integers
            width_direction=create_v3(1, 0, 0)      # East - integers
        )
        
        timber2 = timber_from_directions(
            length=3,  # Integer
            size=create_v2(Rational(3, 20), Rational(1, 4)),  # Exact rationals
            bottom_position=create_v3(2, 0, 0),  # Integers
            length_direction=create_v3(1, 0, 0),   # East (perpendicular to timber1) - integers
            width_direction=create_v3(0, 0, 1)      # Up - integers
        )
        
        # These should be face-aligned with exact equality (no tolerance)
        assert are_timbers_face_aligned(timber1, timber2, tolerance=None)
        
        # Create a non-face-aligned timber (3D rotation with no aligned axes)
        # Using a timber rotated in 3D such that none of its axes align with timber1's axes
        timber3 = timber_from_directions(
            length=2,  # Integer
            size=create_v2(Rational(1, 5), Rational(1, 5)),  # Exact rationals
            bottom_position=create_v3(3, 3, 0),  # Integers
            length_direction=create_v3(1, 1, 1),   # 3D diagonal (will be normalized to Float)
            width_direction=create_v3(1, -1, 0)     # Perpendicular in 3D (will be normalized to Float)
        )
        
        # timber1 and timber3 should NOT be face-aligned
        # Note: timber3's normalized directions contain Float values, but the new
        # system automatically handles this without warnings
        result = are_timbers_face_aligned(timber1, timber3, tolerance=None)
        assert not result
        
        # Test with tolerance parameter (no warning)
        assert are_timbers_face_aligned(timber1, timber2, tolerance=Float(1e-10))

    def test_do_xy_cross_section_on_parallel_timbers_overlap(self):
        """Test do_xy_cross_section_on_parallel_timbers_overlap function."""
        from kumiki.timber_shavings import do_xy_cross_section_on_parallel_timbers_overlap
        from sympy import Rational
        
        # Test 1: Two aligned timbers that overlap
        timber1 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber1'
        )
        
        timber2 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(5, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber2'
        )
        
        assert do_xy_cross_section_on_parallel_timbers_overlap(timber1, timber2), \
            "Aligned timbers at same cross-section should overlap"
        
        # Test 2: Two aligned timbers that don't overlap (separated in Y)
        timber3 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(5, 10, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber3'
        )
        
        assert not do_xy_cross_section_on_parallel_timbers_overlap(timber1, timber3), \
            "Timbers separated in Y should not overlap"
        
        # Test 3: Two rotated timbers that overlap
        timber4 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber4'
        )
        
        timber5 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 0, 1),  # Rotated 90 degrees
            ticket='timber5'
        )
        
        assert do_xy_cross_section_on_parallel_timbers_overlap(timber4, timber5), \
            "Rotated timbers at same position should overlap"
        
        # Test 4: Timbers that just touch at edge (should overlap)
        timber6 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber6'
        )
        
        # timber6 spans Y: -2 to 2
        # timber7 at Y=4 spans Y: 2 to 6, so they just touch
        timber7 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, Rational(4), 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber7'
        )
        
        assert do_xy_cross_section_on_parallel_timbers_overlap(timber6, timber7), \
            "Timbers touching at edge should overlap"
        
        # Test 5: Timbers with small gap (should not overlap)
        timber8 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, Rational(4) + Rational('0.01'), 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber8'
        )
        
        assert not do_xy_cross_section_on_parallel_timbers_overlap(timber6, timber8), \
            "Timbers with small gap should not overlap"
        
        # Test 6: Anti-parallel timbers (same direction but opposite ends)
        timber9 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber9'
        )
        
        timber10 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(20, 0, 0),
            length_direction=create_v3(-1, 0, 0),  # Opposite direction
            width_direction=create_v3(0, 1, 0),
            ticket='timber10'
        )
        
        assert do_xy_cross_section_on_parallel_timbers_overlap(timber9, timber10), \
            "Anti-parallel timbers at same cross-section should overlap"
        
        # Test 7: Offset rotated timbers
        timber11 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(6)),  # 4 wide, 6 high
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket='timber11'
        )
        
        # Rotated 90 degrees and offset
        timber12 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(6), Rational(4)),  # 6 wide, 4 high
            bottom_position=create_v3(Rational(4), 0, 0),  # Offset in X
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(0, 1, 0),  # Rotated 90 degrees
            ticket='timber12'
        )
        
        # timber11: X spans -2 to 2, Y spans -3 to 3
        # timber12: X spans 1 to 7, Y spans -2 to 2
        # They should overlap in the region X: 1 to 2, Y: -2 to 2
        assert do_xy_cross_section_on_parallel_timbers_overlap(timber11, timber12), \
            "Offset rotated timbers with partial overlap should overlap"
        
        # Test 8: Assertion error for non-parallel timbers
        timber13 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timber13'
        )
        
        timber14 = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 1, 0),  # Perpendicular
            width_direction=create_v3(1, 0, 0),
            ticket='timber14'
        )
        
        # Should raise assertion error for non-parallel timbers
        try:
            do_xy_cross_section_on_parallel_timbers_overlap(timber13, timber14)
            assert False, "Should have raised AssertionError for non-parallel timbers"
        except AssertionError as e:
            assert "must be parallel" in str(e)


# =============================================================================
# Simple tests for are_timbers_parallel, are_timbers_orthogonal, are_timbers_plane_aligned
# =============================================================================

class TestAreTimbersParallel:
    def test_two_horizontal_same_direction_are_parallel(self):
        t1 = create_standard_horizontal_timber(direction='x', ticket="t1")
        t2 = create_standard_horizontal_timber(direction='x', ticket="t2")
        assert are_timbers_parallel(t1, t2) == True

    def test_horizontal_and_vertical_are_not_parallel(self):
        t_h = create_standard_horizontal_timber(direction='x', ticket="th")
        t_v = create_standard_vertical_timber(ticket="tv")
        assert are_timbers_parallel(t_h, t_v) == False


class TestAreTimbersOrthogonal:
    def test_vertical_and_horizontal_are_orthogonal(self):
        t_v = create_standard_vertical_timber(ticket="tv")
        t_h = create_standard_horizontal_timber(direction='x', ticket="th")
        assert are_timbers_orthogonal(t_v, t_h) == True

    def test_two_horizontal_same_direction_not_orthogonal(self):
        t1 = create_standard_horizontal_timber(direction='x', ticket="t1")
        t2 = create_standard_horizontal_timber(direction='x', ticket="t2")
        assert are_timbers_orthogonal(t1, t2) == False


class TestAreTimbersPlaneAligned:
    def test_two_horizontal_same_orientation_plane_aligned(self):
        t1 = create_standard_horizontal_timber(direction='x', ticket="t1")
        t2 = create_standard_horizontal_timber(direction='x', ticket="t2")
        assert are_timbers_plane_aligned(t1, t2) == True

    def test_horizontal_x_and_horizontal_y_share_z_face_so_plane_aligned(self):
        # Both have a long face in Z, so at least one pair of faces is parallel
        t_x = create_standard_horizontal_timber(direction='x', ticket="tx")
        t_y = create_standard_horizontal_timber(direction='y', ticket="ty")
        assert are_timbers_plane_aligned(t_x, t_y) == True

