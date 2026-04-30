"""
Tests for Kumiki timber framing system
"""

import pytest
from sympy import Matrix, sqrt, simplify, Abs, Float, Rational
from kumiki.rule import Orientation
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    assert_vectors_perpendicular
)
from kumiki.rule import inches, feet

# ============================================================================
# Tests for construction.py - Timber Creation and Manipulation
# ============================================================================

class TestTimberCreation:
    """Test timber creation functions."""
    
    def test_create_timber(self):
        """Test basic create_timber function."""
        position = create_v3(Rational(1), Rational(1), Rational(0))
        size = create_v2(Rational("0.2"), Rational("0.3"))
        length_dir = create_v3(Rational(0), Rational(0), Rational(1))
        width_dir = create_v3(Rational(1), Rational(0), Rational(0))
        
        timber = create_timber(position, Rational("2.5"), size, length_dir, width_dir)
        
        assert timber.length == Rational("2.5")
        assert timber.get_bottom_position_global()[0] == Rational(1)
        assert timber.get_bottom_position_global()[1] == Rational(1)
        assert timber.get_bottom_position_global()[2] == Rational(0)
    
    def test_create_axis_aligned_timber(self, symbolic_mode):
        """Test axis-aligned timber creation with explicit width_direction."""
        position = create_v3(0, 0, 0)  # Use exact integers
        size = create_v2(Rational(1, 10), Rational(1, 10))  # 0.1 as exact rational
        
        timber = create_axis_aligned_timber(
            position, 3, size,  # Use exact integer for length
            TimberFace.TOP,    # Length direction (up)
            TimberFace.RIGHT   # Width direction (east)
        )
        
        assert timber.length == 3  # Exact integer
        # Check that directions are correct
        assert timber.get_length_direction_global()[2] == 1  # Up (exact integer)
        assert timber.get_width_direction_global()[0] == 1    # East (exact integer)
    
    def test_create_axis_aligned_timber_default_width(self, symbolic_mode):
        """Test axis-aligned timber creation with default width_direction."""
        position = create_v3(0, 0, 0)
        size = create_v2(Rational(1, 10), Rational(1, 10))
        
        # Test with length in +Z direction (default width should be +X)
        timber1 = create_axis_aligned_timber(
            position, 3, size,
            TimberFace.TOP  # Length in +Z
            # width_direction not provided - should default to RIGHT (+X)
        )
        
        assert timber1.get_length_direction_global()[2] == 1  # Length in +Z
        assert timber1.get_width_direction_global()[0] == 1    # Width in +X (default)
        
        # Test with length in +Y direction (default width should be +X)
        timber2 = create_axis_aligned_timber(
            position, 3, size,
            TimberFace.FRONT  # Length in +Y
            # width_direction not provided - should default to RIGHT (+X)
        )
        
        assert timber2.get_length_direction_global()[1] == 1  # Length in +Y
        assert timber2.get_width_direction_global()[0] == 1    # Width in +X (default)
        
        # Test with length in +X direction (default width should be +Z)
        timber3 = create_axis_aligned_timber(
            position, 3, size,
            TimberFace.RIGHT  # Length in +X
            # width_direction not provided - should default to TOP (+Z)
        )
        
        assert timber3.get_length_direction_global()[0] == 1  # Length in +X
        assert timber3.get_width_direction_global()[2] == 1    # Width in +Z (special case)
    
    def test_create_axis_aligned_timber_explicit_overrides_default(self, symbolic_mode):
        """Test that explicit width_direction overrides the default."""
        position = create_v3(0, 0, 0)
        size = create_v2(Rational(1, 10), Rational(1, 10))
        
        # Even with length in +X, we can explicitly set width to +Y
        timber = create_axis_aligned_timber(
            position, 3, size,
            TimberFace.RIGHT,    # Length in +X
            TimberFace.FRONT   # Explicit width in +Y (not the default +Z)
        )
        
        assert timber.get_length_direction_global()[0] == 1  # Length in +X
        assert timber.get_width_direction_global()[1] == 1    # Width in +Y (explicit)
    
    def test_create_vertical_timber_on_footprint_corner(self, symbolic_mode):
        """Test vertical timber creation on footprint corner with INSIDE, OUTSIDE, and CENTER."""
        # Create a square footprint with exact integer corners
        corners = [
            create_v2(0, 0),  # Corner 0: Bottom-left
            create_v2(3, 0),  # Corner 1: Bottom-right  
            create_v2(3, 4),  # Corner 2: Top-right
            create_v2(0, 4)   # Corner 3: Top-left
        ]
        footprint = Footprint(tuple(corners))
        
        # Post size: 9cm x 9cm (exact rational)
        size = create_v2(Rational(9, 100), Rational(9, 100))
        post_height = Rational(5, 2)  # 2.5 meters
        
        # Test INSIDE positioning
        # Vertex of bottom face is at corner, post extends inside
        timber_inside = create_vertical_timber_on_footprint_corner(
            footprint, 0, post_height, FootprintLocation.INSIDE, size
        )
        
        assert timber_inside.length == Rational(5, 2)
        # For INSIDE, center is shifted inward by half dimensions.
        assert timber_inside.get_bottom_position_global()[0] == Rational(9, 200)
        assert timber_inside.get_bottom_position_global()[1] == Rational(9, 200)
        assert timber_inside.get_bottom_position_global()[2] == 0
        # Should be vertical
        assert timber_inside.get_length_direction_global()[2] == 1
        # Face direction should align with outgoing boundary side (+X)
        # For axis-aligned case, direction is exactly 1
        assert timber_inside.get_width_direction_global()[0] == 1
        assert timber_inside.get_width_direction_global()[1] == 0
        assert timber_inside.get_width_direction_global()[2] == 0
        
        # Test CENTER positioning  
        # Center of bottom face is at corner
        timber_center = create_vertical_timber_on_footprint_corner(
            footprint, 0, post_height, FootprintLocation.CENTER, size
        )
        
        assert timber_center.length == Rational(5, 2)
        # For CENTER, center lies on corner.
        assert timber_center.get_bottom_position_global()[0] == 0
        assert timber_center.get_bottom_position_global()[1] == 0
        assert timber_center.get_bottom_position_global()[2] == 0
        # Should be vertical
        assert timber_center.get_length_direction_global()[2] == 1
        # Face direction should align with outgoing boundary side (+X)
        # For axis-aligned case, direction is exactly 1
        assert timber_center.get_width_direction_global()[0] == 1
        assert timber_center.get_width_direction_global()[1] == 0
        
        # Test OUTSIDE positioning
        # Opposite vertex is at corner, post extends outside
        timber_outside = create_vertical_timber_on_footprint_corner(
            footprint, 0, post_height, FootprintLocation.OUTSIDE, size
        )
        
        assert timber_outside.length == Rational(5, 2)
        # For OUTSIDE, center is shifted outward by half dimensions.
        assert timber_outside.get_bottom_position_global()[0] == Rational(-9, 200)
        assert timber_outside.get_bottom_position_global()[1] == Rational(-9, 200)
        assert timber_outside.get_bottom_position_global()[2] == 0
        # Should be vertical
        assert timber_outside.get_length_direction_global()[2] == 1
        # Face direction should align with outgoing boundary side (+X)
        # For axis-aligned case, direction is exactly 1
        assert timber_outside.get_width_direction_global()[0] == 1
        assert timber_outside.get_width_direction_global()[1] == 0
    
    def test_create_vertical_timber_on_footprint_side(self, symbolic_mode):
        """Test vertical timber creation on footprint side with INSIDE, OUTSIDE, and CENTER."""
        # Create a square footprint with exact integer corners
        corners = [
            create_v2(0, 0),  # Corner 0: Bottom-left
            create_v2(4, 0),  # Corner 1: Bottom-right
            create_v2(4, 3),  # Corner 2: Top-right
            create_v2(0, 3)   # Corner 3: Top-left
        ]
        footprint = Footprint(tuple(corners))
        
        # Post size: 10cm x 10cm (exact rational)
        size = create_v2(Rational(1, 10), Rational(1, 10))
        post_height = Rational(3, 1)  # 3 meters
        
        # Place post 1 meter along the bottom side (from corner 0 to corner 1)
        distance_along_side = Rational(1, 1)
        
        # Test CENTER positioning
        # Center of bottom face is on the point (1, 0)
        timber_center = create_vertical_timber_on_footprint_side(
            footprint, 0, distance_along_side, post_height, FootprintLocation.CENTER, size
        )
        
        assert timber_center.length == Rational(3, 1)
        # For CENTER, center is exactly at (1, 0) - exact!
        assert timber_center.get_bottom_position_global()[0] == 1
        assert timber_center.get_bottom_position_global()[1] == 0
        assert timber_center.get_bottom_position_global()[2] == 0
        # Should be vertical
        assert timber_center.get_length_direction_global()[2] == 1
        # Face direction should be parallel to the side (along +X)
        assert timber_center.get_width_direction_global()[0] == 1
        assert timber_center.get_width_direction_global()[1] == 0
        
        # Test INSIDE positioning
        # One edge center is at the point, post extends inside (toward +Y)
        timber_inside = create_vertical_timber_on_footprint_side(
            footprint, 0, distance_along_side, post_height, FootprintLocation.INSIDE, size
        )
        
        assert timber_inside.length == Rational(3, 1)
        # For INSIDE, offset by half depth inward (toward +Y)
        assert timber_inside.get_bottom_position_global()[0] == 1
        assert timber_inside.get_bottom_position_global()[1] == size[1] / 2
        assert timber_inside.get_bottom_position_global()[2] == 0
        # Should be vertical
        assert timber_inside.get_length_direction_global()[2] == 1
        # Face direction parallel to side
        assert timber_inside.get_width_direction_global()[0] == 1
        assert timber_inside.get_width_direction_global()[1] == 0
        
        # Test OUTSIDE positioning
        # One edge center is at the point, post extends outside (toward -Y)
        timber_outside = create_vertical_timber_on_footprint_side(
            footprint, 0, distance_along_side, post_height, FootprintLocation.OUTSIDE, size
        )
        
        assert timber_outside.length == Rational(3, 1)
        # For OUTSIDE, offset by half depth outward (toward -Y)
        assert timber_outside.get_bottom_position_global()[0] == 1
        assert timber_outside.get_bottom_position_global()[1] == -size[1] / 2
        assert timber_outside.get_bottom_position_global()[2] == 0
        # Should be vertical
        assert timber_outside.get_length_direction_global()[2] == 1
        # Face direction parallel to side
        assert timber_outside.get_width_direction_global()[0] == 1
        assert timber_outside.get_width_direction_global()[1] == 0

    def test_inside_corner_lines_up_with_inside_side(self, symbolic_mode):
        """INSIDE corner and INSIDE side placement should lie on the same inside boundary line."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 3),
            create_v2(0, 3),
        ]
        footprint = Footprint(tuple(corners))
        size = create_v2(Rational(1, 10), Rational(1, 10))
        post_height = Rational(3, 1)

        corner_post_inside = create_vertical_timber_on_footprint_corner(
            footprint, 0, post_height, FootprintLocation.INSIDE, size
        )
        side_post_inside = create_vertical_timber_on_footprint_side(
            footprint, 0, Rational(1, 1), post_height, FootprintLocation.INSIDE, size
        )

        # Side-0 inside line is y = +depth/2 for this rectangular footprint.
        assert side_post_inside.get_bottom_position_global()[1] == size[1] / 2
        assert corner_post_inside.get_bottom_position_global()[1] == side_post_inside.get_bottom_position_global()[1]

    def test_corner_side_location_alignment_pairs(self, symbolic_mode):
        """CENTER/CENTER and OUTSIDE/OUTSIDE align, while INSIDE/CENTER do not."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 3),
            create_v2(0, 3),
        ]
        footprint = Footprint(tuple(corners))
        size = create_v2(Rational(1, 10), Rational(1, 10))
        post_height = Rational(3, 1)

        corner_center = create_vertical_timber_on_footprint_corner(
            footprint, 0, post_height, FootprintLocation.CENTER, size
        )
        side_center = create_vertical_timber_on_footprint_side(
            footprint, 0, Rational(1, 1), post_height, FootprintLocation.CENTER, size
        )
        corner_outside = create_vertical_timber_on_footprint_corner(
            footprint, 0, post_height, FootprintLocation.OUTSIDE, size
        )
        side_outside = create_vertical_timber_on_footprint_side(
            footprint, 0, Rational(1, 1), post_height, FootprintLocation.OUTSIDE, size
        )
        corner_inside = create_vertical_timber_on_footprint_corner(
            footprint, 0, post_height, FootprintLocation.INSIDE, size
        )

        assert corner_center.get_bottom_position_global()[1] == side_center.get_bottom_position_global()[1]
        assert corner_outside.get_bottom_position_global()[1] == side_outside.get_bottom_position_global()[1]
        assert corner_inside.get_bottom_position_global()[1] != side_center.get_bottom_position_global()[1]
    
    def test_create_horizontal_timber_on_footprint(self, symbolic_mode):
        """Test horizontal timber creation on footprint."""
        corners = [
            create_v2(Rational(0), Rational(0)),
            create_v2(Rational(3), Rational(0)),
            create_v2(Rational(3), Rational(4)),
            create_v2(Rational(0), Rational(4))
        ]
        footprint = Footprint(tuple(corners))
        
        # Default size for test
        size = create_v2(Rational(3, 10), Rational(3, 10))
        
        timber = create_horizontal_timber_on_footprint(
            footprint, 0, FootprintLocation.INSIDE, size, length=Rational(3)
        )
        
        assert timber.length == Rational(3)
        # Should be horizontal in X direction
        assert timber.get_length_direction_global()[0] == 1
        assert timber.get_length_direction_global()[2] == 0
    
    def test_create_horizontal_timber_on_footprint_location_types(self, symbolic_mode):
        """Test horizontal timber positioning with INSIDE, OUTSIDE, and CENTER location types."""
        # Create a square footprint with exact integer coordinates
        corners = [
            create_v2(0, 0),  # Bottom-left
            create_v2(2, 0),  # Bottom-right
            create_v2(2, 2),  # Top-right
            create_v2(0, 2)   # Top-left
        ]
        footprint = Footprint(tuple(corners))
        
        # Define timber size: width (vertical) x height (perpendicular to boundary)
        # For a horizontal timber: size[0] = width (vertical), size[1] = height (horizontal perpendicular)
        timber_width = Rational(3, 10)   # Vertical dimension (face direction = up)
        timber_height = Rational(2, 10)  # Perpendicular to boundary in XY plane
        size = create_v2(timber_width, timber_height)
        
        # Test bottom boundary side (from corner 0 to corner 1)
        # This side has inward normal pointing up: (0, 1, 0)
        
        # Test INSIDE positioning
        timber_inside = create_horizontal_timber_on_footprint(
            footprint, 0, FootprintLocation.INSIDE, size, length=Rational(2)
        )
        # Timber should extend inward (in +Y direction)
        # Bottom position Y should be half timber height (perpendicular dimension) inside the footprint
        assert timber_inside.get_bottom_position_global()[1] == timber_height / Rational(2)
        assert timber_inside.get_bottom_position_global()[0] == 0  # X unchanged
        assert timber_inside.get_bottom_position_global()[2] == 0  # Z at ground
        
        # Test OUTSIDE positioning
        timber_outside = create_horizontal_timber_on_footprint(
            footprint, 0, FootprintLocation.OUTSIDE, size, length=Rational(2)
        )
        # Timber should extend outward (in -Y direction)
        # Bottom position Y should be half timber height (perpendicular dimension) outside the footprint
        # Note: get_inward_normal returns Direction3D with exact Numeric types
        assert timber_outside.get_bottom_position_global()[1] == -timber_height / Rational(2)
        assert timber_outside.get_bottom_position_global()[0] == 0  # X unchanged
        assert timber_outside.get_bottom_position_global()[2] == 0  # Z at ground
        
        # Test CENTER positioning
        timber_center = create_horizontal_timber_on_footprint(
            footprint, 0, FootprintLocation.CENTER, size, length=Rational(2)
        )
        # Centerline should be on the boundary side
        assert timber_center.get_bottom_position_global()[1] == Rational(0)  # Y on boundary
        assert timber_center.get_bottom_position_global()[0] == Rational(0)  # X unchanged
        assert timber_center.get_bottom_position_global()[2] == Rational(0)  # Z at ground
        
        # Verify all timbers have correct length direction (along +X for bottom side)
        assert timber_inside.get_length_direction_global()[0] == Rational(1)
        assert timber_inside.get_length_direction_global()[1] == Rational(0)
        assert timber_inside.get_length_direction_global()[2] == Rational(0)
        
        assert timber_outside.get_length_direction_global()[0] == Rational(1)
        assert timber_outside.get_length_direction_global()[1] == Rational(0)
        assert timber_outside.get_length_direction_global()[2] == Rational(0)
        
        assert timber_center.get_length_direction_global()[0] == Rational(1)
        assert timber_center.get_length_direction_global()[1] == Rational(0)
        assert timber_center.get_length_direction_global()[2] == Rational(0)
        
        # Test right boundary side (from corner 1 to corner 2)
        # This side has inward normal pointing left: (-1, 0, 0)
        
        timber_inside_right = create_horizontal_timber_on_footprint(
            footprint, 1, FootprintLocation.INSIDE, size, length=Rational(2)
        )
        # Timber should extend inward (in -X direction)
        # Use timber_height (size[1]) as it's the dimension perpendicular to boundary
        assert timber_inside_right.get_bottom_position_global()[0] == Rational(2) - timber_height / Rational(2)
        assert timber_inside_right.get_bottom_position_global()[1] == Rational(0)  # Y unchanged
        
        timber_outside_right = create_horizontal_timber_on_footprint(
            footprint, 1, FootprintLocation.OUTSIDE, size, length=Rational(2)
        )
        # Timber should extend outward (in +X direction)
        # Use timber_height (size[1]) as it's the dimension perpendicular to boundary
        assert timber_outside_right.get_bottom_position_global()[0] == Rational(2) + timber_height / Rational(2)
        assert timber_outside_right.get_bottom_position_global()[1] == Rational(0)  # Y unchanged
        
        timber_center_right = create_horizontal_timber_on_footprint(
            footprint, 1, FootprintLocation.CENTER, size, length=Rational(2)
        )
        # Centerline should be on the boundary side
        assert timber_center_right.get_bottom_position_global()[0] == Rational(2)  # X on boundary
        assert timber_center_right.get_bottom_position_global()[1] == Rational(0)  # Y unchanged
    
    def test_stretch_timber(self, symbolic_mode):
        """Test timber extension creation with correct length calculation."""
        # Create a vertical timber from Z=0 to Z=10
        original_timber = create_standard_vertical_timber(height=10, size=(0.2, 0.2), position=(0, 0, 0))
        
        # Extend from top with 2 units of overlap and 5 units of extension
        # overlap_length = 2.0 (overlaps with last 2 units of original timber)
        # extend_length = 5.0 (extends 5 units beyond the end)
        extended = stretch_timber(
            original_timber, 
            TimberReferenceEnd.TOP, 
            overlap_length=Rational(2), 
            extend_length=Rational(5)
        )
        
        # Verify length: original_length + extend_length + overlap_length
        # = 10.0 + 5.0 + 2.0 = 17.0
        assert extended.length == Rational(17), f"Expected length Rational(17), got {extended.length}"
        
        # Verify bottom position moved up by (original_length - overlap_length)
        # = 0.0 + (10.0 - 2.0) = 8.0
        assert extended.get_bottom_position_global()[2] == Rational(8), \
            f"Expected bottom Z at Rational(8), got {float(extended.get_bottom_position_global()[2])}"



class TestHelperFunctions:
    """Test helper functions."""
    
    def test_timber_face_get_direction(self):
        """Test TimberFace.get_direction() method."""
        # Test all faces
        top = TimberFace.TOP.get_direction()
        assert top[2] == Rational(1)
        
        bottom = TimberFace.BOTTOM.get_direction()
        assert bottom[2] == -Rational(1)
        
        right = TimberFace.RIGHT.get_direction()
        assert right[0] == Rational(1)
        
        left = TimberFace.LEFT.get_direction()
        assert left[0] == -Rational(1)
        
        front = TimberFace.FRONT.get_direction()
        assert front[1] == Rational(1)
        
        back = TimberFace.BACK.get_direction()
        assert back[1] == -Rational(1)



class TestJoinTimbers:
    """Test timber joining functions."""
    
    def test_join_timbers_basic(self):
        """Test basic timber joining."""
        timber1 = create_standard_vertical_timber(height=3, size=(0.2, 0.2), position=(0, 0, 0))
        timber2 = create_standard_vertical_timber(height=2, size=(0.2, 0.2), position=(2, 0, 0))
        
        joining_timber = join_timbers(
            timber1, timber2,
            location_on_timber1=Rational("1.5"),  # Midpoint of timber1
            stickout=Stickout(Rational("0.1"), Rational("0.1")),  # Symmetric stickout
            location_on_timber2=Rational(1),   # Explicit position on timber2
            lateral_offset=Rational(0)
        )
        
        assert isinstance(joining_timber, Timber)
        # Length direction should be from pos1=[0,0,1.5] to pos2=[2,0,1.0], so direction=[2,0,-0.5]
        # Normalized: [0.970, 0, -0.243] approximately
        length_dir = joining_timber.get_length_direction_global()
        assert abs(float(length_dir[0]) - Rational("0.970")) < Rational("0.1")  # X component ~0.97
        assert abs(float(length_dir[1])) < Rational("0.1")          # Y component ~0
        assert abs(float(length_dir[2]) + Rational("0.243")) < Rational("0.1")  # Z component ~-0.24
        
        # Face direction should be orthogonal to length direction
        # Default behavior: projects timber1's length direction [0,0,1] onto perpendicular plane
        # Result should be perpendicular to joining direction
        width_dir = joining_timber.get_width_direction_global()
        assert_vectors_perpendicular(length_dir, width_dir)
        
        # Verify the joining timber is positioned correctly
        # pos1 = [0, 0, 1.5] (location 1.5 on timber1), pos2 = [2, 0, 1.0] (location 1.0 on timber2)
        # center would be [1, 0, 1.25], but bottom_position is at the start of the timber
        # The timber should span from one connection point to the other with stickout
        
        # Check that the timber actually spans the connection points correctly
        # The timber should start before pos1 and end after pos2 (or vice versa)
        timber_start = joining_timber.get_bottom_position_global()
        timber_end = locate_position_on_centerline_from_bottom(joining_timber, joining_timber.length).position
        
        # Verify timber spans the connection region
        assert joining_timber.length > Rational(2)  # Should be longer than just the span between points

    def test_join_timbers_with_non_perpendicular_orientation_vector(self):
        """Test that join_timbers automatically projects non-perpendicular orientation_width_vector."""
        # Create two vertical posts
        timber1 = create_standard_vertical_timber(height=3, size=(0.2, 0.2), position=(0, 0, 0))
        timber2 = create_standard_vertical_timber(height=3, size=(0.2, 0.2), position=(2, 0, 0))
        
        # Create a horizontal beam connecting them, specifying "face up" (0,0,1)
        # The joining direction is horizontal [1,0,0], so [0,0,1] is NOT perpendicular
        # The function should automatically project it onto the perpendicular plane
        joining_timber = join_timbers(
            timber1, timber2,
            location_on_timber1=Rational("1.5"),  # Midpoint of timber1
            stickout=Stickout(Rational("0.1"), Rational("0.1")),  # Symmetric stickout
            location_on_timber2=Rational("1.5"),   # Same height on timber2
            orientation_width_vector=create_v3(0, 0, 1)  # "Face up" - not perpendicular to joining direction
        )
        
        # Verify the timber was created successfully (no assertion error)
        assert isinstance(joining_timber, Timber)
        
        # The joining direction should be horizontal [1,0,0] (normalized)
        length_dir = joining_timber.get_length_direction_global()
        assert abs(float(length_dir[0]) - Rational(1)) < 1e-6, "Length direction should be [1,0,0]"
        assert abs(float(length_dir[1])) < 1e-6
        assert abs(float(length_dir[2])) < 1e-6
        
        # The width direction should be perpendicular to the joining direction
        # Since we specified [0,0,1] and joining is [1,0,0], projection should give [0,0,1]
        width_dir = joining_timber.get_width_direction_global()
        dot_product = length_dir.dot(width_dir)
        assert abs(float(dot_product)) < 1e-6, "Width direction should be perpendicular to length direction"
        
        # The projected width direction should be close to [0,0,1] (our desired "face up")
        assert abs(float(width_dir[0])) < 1e-6, "Width X component should be ~0"
        assert abs(float(width_dir[1])) < 1e-6, "Width Y component should be ~0"
        assert abs(abs(float(width_dir[2])) - Rational(1)) < 1e-6, "Width Z component should be ~±1"

    def test_join_timbers_with_angled_orientation_vector(self):
        """Test projection of angled orientation_width_vector onto perpendicular plane."""
        # Create two vertical posts
        timber1 = create_standard_vertical_timber(height=3, size=(0.2, 0.2), position=(0, 0, 0))
        timber2 = create_standard_vertical_timber(height=3, size=(0.2, 0.2), position=(2, 1, 0))
        
        # Provide an orientation vector at an angle: [1, 1, 1]
        # This should be projected onto the plane perpendicular to the joining direction
        joining_timber = join_timbers(
            timber1, timber2,
            location_on_timber1=Rational("1.5"),
            stickout=Stickout(Rational(0), Rational(0)),
            location_on_timber2=Rational("1.5"),
            orientation_width_vector=create_v3(1, 1, 1)  # Angled vector
        )
        
        # Verify the timber was created successfully
        assert isinstance(joining_timber, Timber)
        
        # Verify width direction is perpendicular to length direction
        length_dir = joining_timber.get_length_direction_global()
        width_dir = joining_timber.get_width_direction_global()
        dot_product = length_dir.dot(width_dir)
        assert abs(float(dot_product)) < 1e-6, "Width direction should be perpendicular to length direction"

    # helper function to create 2 parallel timbers 
    def make_parallel_timbers(self):
        timber1 = create_standard_horizontal_timber(direction='x', length=3, size=(0.2, 0.2), position=(0, 0, 0))
        timber2 = create_standard_horizontal_timber(direction='x', length=3, size=(0.2, 0.2), position=(0, 2, 0))
        return timber1, timber2
    
    def test_join_face_aligned_on_face_aligned_timbers_position_is_correct(self):
        """Test perpendicular joining of face-aligned timbers."""
        timber1, timber2 = self.make_parallel_timbers()

        joining_timber2 = join_face_aligned_on_face_aligned_timbers(
            timber1, timber2,
            location_on_timber1=Rational("1.5"),
            stickout=Stickout(0, 0),  # No stickout
            lateral_offset_from_timber1=Rational(0),
            size=create_v2(Rational("0.15"), Rational("0.15")),
            feature_to_mark_on_joining_timber=None,
            orientation_face_on_timber1=TimberFace.TOP
        )
   
        assert joining_timber2.get_bottom_position_global() == locate_position_on_centerline_from_bottom(timber1, Rational("1.5")).position
        print(joining_timber2.orientation)
        
        
    def test_join_face_aligned_on_face_aligned_timbers_length_is_correct(self):
        """Test perpendicular joining of face-aligned timbers."""
        timber1, timber2 = self.make_parallel_timbers()
        
        joining_timber2 = join_face_aligned_on_face_aligned_timbers(
            timber1, timber2,
            location_on_timber1=Rational("1.5"),
            stickout=Stickout(Rational("1.2"), Rational("1.2")),  # Symmetric stickout
            lateral_offset_from_timber1=Rational(0),
            size=create_v2(Rational("0.15"), Rational("0.15")),
            feature_to_mark_on_joining_timber=None,
            orientation_face_on_timber1=TimberFace.TOP
        )
        
        assert isinstance(joining_timber2, Timber)
        # Length should be centerline distance (2.0) + stickout1 (1.2) + stickout2 (1.2) = 4.4
        assert abs(joining_timber2.length - Rational("4.4")) < 1e-10
    
    def test_join_face_aligned_on_face_aligned_timbers_assertion(self):
        """Test that join_face_aligned_on_face_aligned_timbers asserts when timbers are not face-aligned."""
        import pytest
        
        # Create two timbers that are NOT face-aligned
        # Timber1: vertical, facing east
        timber1 = create_standard_vertical_timber(height=3, size=(0.15, 0.15), position=(0, 0, 0))
        
        # Timber2: 3D rotation not aligned with timber1's coordinate grid
        timber2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.15"), Rational("0.15")),
            bottom_position=create_v3(Rational(2), Rational(2), Rational(0)),
            length_direction=create_v3(1, 1, 1),  # 3D diagonal (will be normalized)
            width_direction=create_v3(1, -1, 0)    # Perpendicular in 3D (will be normalized)
        )
        
        # Verify they are NOT face-aligned
        assert not are_timbers_face_aligned(timber1, timber2), "Timbers should not be face-aligned"
        
        # Now try to join them - should raise AssertionError
        with pytest.raises(AssertionError, match="must be face-aligned"):
            join_face_aligned_on_face_aligned_timbers(
                timber1, timber2,
                location_on_timber1=Rational("1.5"),
                stickout=Stickout(Rational(0), Rational(0)),
                lateral_offset_from_timber1=Rational(0),
                size=create_v2(Rational("0.15"), Rational("0.15")),
                feature_to_mark_on_joining_timber=None,
                orientation_face_on_timber1=TimberFace.TOP
            )
    
    def test_join_face_aligned_on_face_aligned_timbers_auto_size(self, symbolic_mode):
        """Test automatic size determination in join_face_aligned_on_face_aligned_timbers."""
        # Create two vertical posts with 1" x 2" cross-section
        post1 = create_standard_vertical_timber(height=3, size=(inches(1), inches(2)), position=(0, 0, 0))
        # Post2 is 5 feet away in the X direction
        post2 = create_standard_vertical_timber(height=3, size=(inches(1), inches(2)), position=(feet(5), 0, 0))
        
        # Join perpendicular with size=None (auto-determine)
        beam = join_face_aligned_on_face_aligned_timbers(
            timber1=post1,
            timber2=post2,
            location_on_timber1=Rational(3, 2),  # 1.5m up the post (exact rational)
            stickout=Stickout.nostickout(),
            lateral_offset_from_timber1=Rational(0),
            size=None,  # Auto-determine size  # type: ignore
            feature_to_mark_on_joining_timber=None,
            orientation_face_on_timber1=TimberFace.TOP
        )
        
        # The beam runs horizontally (X direction) connecting the two vertical posts
        # The beam should match the post's cross-section dimensions
        # Since the beam is perpendicular to the posts, it should use post1's size
        # The beam's face direction aligns with the TOP face of post1 (which is Z+)
        # So the beam should have the same cross-section as the post
        assert beam.size[0] == post1.size[0], f"Expected beam width {post1.size[0]}, got {beam.size[0]}"
        assert beam.size[1] == post1.size[1], f"Expected beam height {post1.size[1]}, got {beam.size[1]}"
        
        # Verify the beam's orientation
        # The beam runs in X direction (from post1 to post2)
        assert beam.get_length_direction_global()[0] == 1, "Beam should run in X+ direction"
        assert beam.get_length_direction_global()[1] == 0, "Beam Y component should be 0"
        assert beam.get_length_direction_global()[2] == 0, "Beam Z component should be 0"
        
        # The beam's face direction should align with TOP of post1 (Z+)
        # Since orientation_face_on_timber1=TOP, the beam's right face aligns with the top face of post1
        assert beam.get_width_direction_global()[0] == 0, "Beam face X component should be 0"
        assert beam.get_width_direction_global()[1] == 0, "Beam face Y component should be 0"
        assert beam.get_width_direction_global()[2] == 1, "Beam should face up (Z+)"
        
        # Verify the beam connects the posts at the correct height
        expected_bottom_z = Rational(3, 2)  # At 1.5m up post1 (exact rational)
        assert beam.get_bottom_position_global()[2] == expected_bottom_z, \
            f"Beam should be at Z={expected_bottom_z}, got Z={beam.get_bottom_position_global()[2]}"

    def test_join_timbers_creates_orthogonal_rotation_matrix(self, symbolic_mode):
        """Test that join_timbers creates valid orthogonal orientation matrices."""
        # Create two non-parallel timbers to ensure non-trivial orientation
        # Use exact integer/rational inputs for exact SymPy results
        timber1 = create_standard_vertical_timber(height=1, size=(0.1, 0.1), position=(-0.5, 0, 0))
        
        timber2 = timber_from_directions(
            length=1,  # Integer
            size=create_v2(Rational(1, 10), Rational(1, 10)),  # Exact rationals
            bottom_position=create_v3(Rational(1, 2), 0, 0),   # Exact rationals
            length_direction=create_v3(0, 1, 0),  # Integers (horizontal north)
            width_direction=create_v3(0, 0, 1)     # Integers
        )
        
        joining_timber = join_timbers(
            timber1, timber2,
            location_on_timber1=Rational(1, 2),     # Exact rational
            stickout=Stickout(Rational(1, 10), Rational(1, 10)),  # Exact symmetric stickout
            location_on_timber2=Rational(1, 2),     # Exact rational
            lateral_offset=0                  # Integer
        )
        
        # Get the orientation matrix
        orientation_matrix = joining_timber.orientation.matrix
        
        # Check that it's orthogonal: M * M^T = I (exact SymPy comparison)
        product = orientation_matrix * orientation_matrix.T
        identity = Matrix.eye(3)
        
        # Check that M * M^T = I exactly
        assert simplify(product - identity) == Matrix.zeros(3, 3), "M * M^T should equal identity matrix"
        
        # Check determinant is exactly 1 (proper rotation, not reflection)
        det = orientation_matrix.det()
        assert simplify(det - 1) == 0, "Determinant should be exactly 1"
        
        # Verify direction vectors are unit length (exact SymPy comparison)
        length_dir = joining_timber.get_length_direction_global()
        width_dir = joining_timber.get_width_direction_global()  
        height_dir = joining_timber.get_height_direction_global()
        
        assert simplify(length_dir.norm() - 1) == 0, "Length direction should be unit vector"
        assert simplify(width_dir.norm() - 1) == 0, "Face direction should be unit vector"
        assert simplify(height_dir.norm() - 1) == 0, "Height direction should be unit vector"
        
        # Verify directions are orthogonal to each other
        assert_vectors_perpendicular(length_dir, width_dir)
        assert_vectors_perpendicular(length_dir, height_dir)
        assert_vectors_perpendicular(width_dir, height_dir)

    def test_create_timber_creates_orthogonal_matrix(self, symbolic_mode):
        """Test that create_timber creates valid orthogonal orientation matrices."""
        # Test with arbitrary (but orthogonal) input directions using exact inputs
        length_dir = create_v3(1, 1, 0)  # Will be normalized (integers)
        width_dir = create_v3(0, 0, 1)    # Up direction (integers)
        
        timber = create_timber(
            bottom_position=create_v3(0, 0, 0),  # Integers
            length=1,  # Integer
            size=create_v2(Rational(1, 10), Rational(1, 10)),  # Exact rationals
            length_direction=length_dir,
            width_direction=width_dir
        )
        
        # Get the orientation matrix
        orientation_matrix = timber.orientation.matrix
        
        # Check that it's orthogonal: M * M^T = I (exact SymPy comparison)
        product = orientation_matrix * orientation_matrix.T
        identity = Matrix.eye(3)
        
        # Check that M * M^T = I exactly
        assert simplify(product - identity) == Matrix.zeros(3, 3), "M * M^T should equal identity matrix"
        
        # Check determinant is exactly 1
        det = orientation_matrix.det()
        assert simplify(det - 1) == 0, "Determinant should be exactly 1"

    def test_orthogonal_matrix_with_non_orthogonal_input(self, symbolic_mode):
        """Test that orthogonal matrix is created even with non-orthogonal input directions."""
        # Use non-orthogonal input directions to test the orthogonalization process
        # Using exact rational numbers for exact results
        length_dir = create_v3(2, 0, 1)         # Not orthogonal to width_dir (integers)
        width_dir = create_v3(0, 1, 2)           # Not orthogonal to length_dir (integers)
        
        timber = create_timber(
            bottom_position=create_v3(0, 0, 0),  # Integers
            length=1,  # Integer
            size=create_v2(Rational(1, 10), Rational(1, 10)),  # Exact rationals
            length_direction=length_dir,
            width_direction=width_dir
        )
        
        # The resulting orientation should still be orthogonal
        orientation_matrix = timber.orientation.matrix
        
        # Check orthogonality using exact SymPy comparison
        product = orientation_matrix * orientation_matrix.T
        identity = Matrix.eye(3)
        
        # Check that M * M^T = I exactly
        assert simplify(product - identity) == Matrix.zeros(3, 3), "M * M^T should equal identity matrix"
        
        # Check determinant is exactly 1
        det = orientation_matrix.det()
        assert simplify(det - 1) == 0, "Determinant should be exactly 1"

    def test_join_perpendicular_face_aligned_timbers_comprehensive(self):
        """Test comprehensive face-aligned timber joining with random configurations."""
        import random
        from sympy import Rational
        
        # Set a fixed seed for reproducible tests
        random.seed(42)
        
        # Create several horizontal timbers at the same Z level (face-aligned on their top faces)
        base_z = Rational(1, 10)  # 0.1m height
        timber_size = create_v2(Rational(1, 10), Rational(1, 10))  # 10cm x 10cm
        
        base_timbers = []
        positions = [
            create_v3(-1, 0, base_z),    # Left
            create_v3(0, 0, base_z),     # Center  
            create_v3(1, 0, base_z),     # Right
            create_v3(0, -1, base_z),    # Back
            create_v3(0, 1, base_z),     # Front
        ]
        
        # Create base timbers - all horizontal and face-aligned
        for i, pos in enumerate(positions):
            timber = timber_from_directions(
                length=2,  # 2m long
                size=timber_size,
                bottom_position=pos,
                length_direction=create_v3(1, 0, 0),  # All point east
                width_direction=create_v3(0, 1, 0),    # All face north
                ticket=f"Base_Timber_{i}"
            )
            base_timbers.append(timber)
        
        # Create a beam at a higher level
        beam_z = Rational(3, 2)  # 1.5m height
        beam = timber_from_directions(
            length=4,  # 4m long beam
            size=create_v2(Rational(15, 100), Rational(15, 100)),  # 15cm x 15cm
            bottom_position=create_v3(-2, 0, beam_z),
            length_direction=create_v3(1, 0, 0),  # East direction
            width_direction=create_v3(0, 1, 0),    # North facing
            ticket="Top_Beam"
        )
        
        # Verify that base timbers are face-aligned (same top face Z coordinate)
        for timber in base_timbers:
            top_face_z = timber.get_bottom_position_global()[2] + timber.get_height_direction_global()[2] * timber.size[1]
            expected_top_z = base_z + timber_size[1]  # base_z + height
            assert simplify(top_face_z - expected_top_z) == 0, f"Base timber {timber.ticket.name} not at expected height"
        
        # Test joining multiple base timbers to the beam
        joining_timbers = []
        locations_used = []  # Store for later verification
        
        # Use deterministic rational positions instead of random floats
        rational_positions = [
            Rational(1, 4),    # 0.25
            Rational(1, 2),    # 0.5
            Rational(3, 4),    # 0.75
            Rational(2, 3),    # 0.667...
            Rational(1, 3),    # 0.333...
        ]
        
        rational_stickouts = [
            Rational(1, 40),   # 0.025
            Rational(3, 100),  # 0.03
            Rational(1, 25),   # 0.04
            Rational(1, 20),   # 0.05
            Rational(3, 50),   # 0.06
        ]
        
        for i, base_timber in enumerate(base_timbers):
            # Use exact rational position along the base timber
            location_on_base = rational_positions[i]
            locations_used.append(location_on_base)
            
            # Use exact rational stickout
            stickout = rational_stickouts[i]
            
            # Join base timber to beam
            # Let the function determine the orientation automatically by projecting
            # timber1's length direction onto the perpendicular plane
            joining_timber = join_face_aligned_on_face_aligned_timbers(
                timber1=base_timber,
                timber2=beam,
                location_on_timber1=location_on_base,
                stickout=Stickout(stickout, stickout),  # Symmetric stickout
                lateral_offset_from_timber1=Rational(0),
                size=create_v2(Rational(8, 100), Rational(8, 100)),  # 8cm x 8cm posts
                feature_to_mark_on_joining_timber=None
                # Note: orientation_face_on_timber1 not specified - uses default projection
            )
            # Note: Cannot set name after construction since Timber is frozen
            joining_timbers.append(joining_timber)
        
        # Verify properties of joining timbers
        for i, joining_timber in enumerate(joining_timbers):
            base_timber = base_timbers[i]
            location_used = locations_used[i]
            
            # 1. Verify the joining timber is approximately vertical (perpendicular to horizontal base)
            # For horizontal base timbers, the joining timber should be mostly vertical
            length_dir = joining_timber.get_length_direction_global()
            vertical_component = abs(float(length_dir[2]))  # Z component
            assert vertical_component > Rational("0.8"), f"Post_{i} should be mostly vertical, got length_direction={[float(x) for x in length_dir]}"
            
            # 2. Verify the joining timber connects to the correct position on the base timber
            expected_base_pos = locate_position_on_centerline_from_bottom(base_timber, location_used).position
            
            # The joining timber should start from approximately the top face of the base timber
            expected_start_z = expected_base_pos[2] + base_timber.size[1]  # Top of base timber
            actual_start_z = joining_timber.get_bottom_position_global()[2]
            
            # Use exact comparison for rational arithmetic - allow for stickout adjustments
            start_z_diff = abs(actual_start_z - expected_start_z)
            assert start_z_diff < Rational("0.2"), f"Post_{i} should start near top of base timber, diff={float(start_z_diff)}"
            
            # 3. Verify the joining timber connects to the beam
            # The top of the joining timber should be near the beam
            joining_top = locate_top_center_position(joining_timber).position
            beam_bottom_z = beam.get_bottom_position_global()[2]
            
            # Should connect somewhere on or near the beam - use exact comparison
            beam_connection_diff = abs(joining_top[2] - beam_bottom_z)
            assert beam_connection_diff < Rational("0.2"), f"Post_{i} should connect near beam level, diff={float(beam_connection_diff)}"
            
            # 4. Verify orthogonality of orientation matrix
            orientation_matrix = joining_timber.orientation.matrix
            product = orientation_matrix * orientation_matrix.T
            identity = Matrix.eye(3)
            
            # Check orthogonality with tolerance for floating-point precision
            diff_matrix = product - identity
            max_error = max([abs(float(diff_matrix[i, j])) for i in range(3) for j in range(3)])
            assert max_error < 1e-12, f"Post_{i} orientation matrix should be orthogonal, max error: {max_error}"
            
            # 5. Verify determinant is 1 (proper rotation)
            det = orientation_matrix.det()
            det_error = abs(float(det - 1))
            assert det_error < 1e-12, f"Post_{i} orientation matrix determinant should be 1, error: {det_error}"
        
        # Test cross-connections between base timbers
        cross_connections = []
        
        # Use deterministic pairs and rational parameters for cross-connections
        cross_connection_configs = [
            # Use non-colinear pairs so projected points are distinct under
            # unclamped join_face_aligned_on_face_aligned_timbers behavior.
            (0, 3, Rational(1, 3), Rational(1, 20)),   # Left to Back, loc=0.333, stickout=0.05
            (1, 4, Rational(1, 2), Rational(3, 40)),   # Center to Front, loc=0.5, stickout=0.075
            (2, 3, Rational(2, 3), Rational(1, 10)),   # Right to Back, loc=0.667, stickout=0.1
        ]
        
        # Connect some base timbers to each other horizontally
        for i, (timber1_idx, timber2_idx, loc1, stickout) in enumerate(cross_connection_configs):
            timber1 = base_timbers[timber1_idx]
            timber2 = base_timbers[timber2_idx]
            
            cross_timber = join_face_aligned_on_face_aligned_timbers(
                timber1=timber1,
                timber2=timber2,
                location_on_timber1=loc1,
                stickout=Stickout(stickout, stickout),  # Symmetric stickout
                lateral_offset_from_timber1=Rational(0),
                size=create_v2(Rational(6, 100), Rational(6, 100)),  # 6cm x 6cm
                feature_to_mark_on_joining_timber=None,
                orientation_face_on_timber1=TimberFace.TOP
            )
            # Note: Cannot set name after construction since Timber is frozen
            cross_connections.append(cross_timber)
        
        # Verify cross-connections
        for i, cross_timber in enumerate(cross_connections):
            # Cross-connections between horizontal face-aligned timbers should also be horizontal
            length_dir = cross_timber.get_length_direction_global()
            horizontal_component = (float(length_dir[0])**2 + float(length_dir[1])**2)**Rational("0.5")
            assert horizontal_component > Rational("0.8"), f"Cross_{i} should be mostly horizontal for face-aligned horizontal timbers"
            
            # Should be at the same Z level as the base timbers (face-aligned)
            cross_z = cross_timber.get_bottom_position_global()[2]
            expected_z = base_z + timber_size[1]  # Top face level of base timbers
            z_level_diff = abs(cross_z - expected_z)
            assert z_level_diff <= Rational("0.15"), f"Cross_{i} should be at the same level as base timbers, diff={float(z_level_diff)}"
            
            # Verify orthogonality with tolerance for floating-point precision
            orientation_matrix = cross_timber.orientation.matrix
            product = orientation_matrix * orientation_matrix.T
            identity = Matrix.eye(3)
            diff_matrix = product - identity
            max_error = max([abs(float(diff_matrix[i, j])) for i in range(3) for j in range(3)])
            assert max_error < 1e-12, f"Cross_{i} orientation matrix should be orthogonal, max error: {max_error}"
        
        print(f"✅ Successfully tested {len(joining_timbers)} vertical posts and {len(cross_connections)} cross-connections")
        print(f"   All joining timbers maintain proper face alignment and orthogonal orientation matrices")
    
    def test_join_perpendicular_with_different_face_features(self):
        """Test that using different TimberFeature face references results in different beam positions."""
        # Create two vertical posts 8" apart (similar to construction_examples)
        post_size = create_v2(inches(4), inches(4))
        post_height = inches(96)  # 8 feet
        beam_size = create_v2(inches(4), inches(4))
        
        # Left post at origin
        post_left = timber_from_directions(
            length=post_height,
            size=post_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Vertical (up)
            width_direction=create_v3(1, 0, 0),    # Width points East
            ticket="Post_Left"
        )
        
        # Right post 8" away in X direction
        post_right = timber_from_directions(
            length=post_height,
            size=post_size,
            bottom_position=create_v3(inches(8), 0, 0),
            length_direction=create_v3(0, 0, 1),  # Vertical (up)
            width_direction=create_v3(1, 0, 0),    # Width points East
            ticket="Post_Right"
        )
        
        # Create beams using all 4 lateral face features
        face_features = [
            TimberFeature.RIGHT_FACE,
            TimberFeature.LEFT_FACE,
            TimberFeature.FRONT_FACE,
            TimberFeature.BACK_FACE,
        ]
        
        beams = {}
        for feature in face_features:
            beam = join_face_aligned_on_face_aligned_timbers(
                timber1=post_left,
                timber2=post_right,
                location_on_timber1=inches(48),  # Mid-height
                stickout=Stickout.nostickout(),
                lateral_offset_from_timber1=Rational(0),  # No additional offset
                size=beam_size,
                feature_to_mark_on_joining_timber=feature,
                orientation_face_on_timber1=TimberFace.TOP,
                ticket=f"Beam_{feature.name}"
            )
            beams[feature] = beam
        
        # Verify all beams are different
        beam_list = list(beams.values())
        for i in range(len(beam_list)):
            for j in range(i + 1, len(beam_list)):
                beam_i = beam_list[i]
                beam_j = beam_list[j]
                
                # Check that bottom positions are different
                pos_i = beam_i.get_bottom_position_global()
                pos_j = beam_j.get_bottom_position_global()
                
                diff = pos_i - pos_j
                magnitude = float((diff.T * diff)[0, 0] ** Rational("0.5"))
                
                assert magnitude > 1e-6, \
                    f"Beams {beam_i.name} and {beam_j.name} should be at different positions, " \
                    f"but positions differ by only {magnitude}"
        
        # Verify specific geometric properties
        # For a beam joining horizontally between vertical posts with orientation_face_on_timber1=TOP:
        # - The beam's length direction should be horizontal (pointing from post_left to post_right)
        # - The beam's width direction should be vertical (pointing up, aligned with TOP face)
        # - The beam's height direction should be horizontal (perpendicular to both)
        
        # RIGHT_FACE and LEFT_FACE: These affect the width dimension (vertical for our beam)
        # The difference should be along the beam's width direction (which is vertical)
        beam_right = beams[TimberFeature.RIGHT_FACE]
        beam_left = beams[TimberFeature.LEFT_FACE]
        
        right_center = locate_position_on_centerline_from_bottom(beam_right, beam_right.length / Integer(2)).position
        left_center = locate_position_on_centerline_from_bottom(beam_left, beam_left.length / Integer(2)).position
        
        # The difference should be along the Z axis (vertical, which is the beam's width direction)
        diff_right_left = right_center - left_center
        # Width of beam is 4", so RIGHT should be 4" higher than LEFT (since RIGHT is +width, LEFT is -width)
        expected_z_diff = beam_size[0]  # 4 inches in width direction (vertical)
        
        actual_z_diff = diff_right_left[2]
        assert abs(float(actual_z_diff - expected_z_diff)) < 1e-10, \
            f"RIGHT_FACE beam should be {float(expected_z_diff)}m higher than LEFT_FACE beam, " \
            f"but difference is {float(actual_z_diff)}m"
        
        # FRONT_FACE and BACK_FACE: These affect the height dimension (Y direction for our beam)
        # The difference should be along the beam's height direction (Y axis)
        beam_front = beams[TimberFeature.FRONT_FACE]
        beam_back = beams[TimberFeature.BACK_FACE]
        
        front_center = locate_position_on_centerline_from_bottom(beam_front, beam_front.length / Integer(2)).position
        back_center = locate_position_on_centerline_from_bottom(beam_back, beam_back.length / Integer(2)).position
        
        # The difference should be along the Y axis (beam's height direction)
        diff_front_back = front_center - back_center
        # Height of beam is 4", so FRONT should be 4" forward (positive Y) from BACK
        expected_y_diff = beam_size[1]  # 4 inches in height direction (Y axis)
        
        actual_y_diff = diff_front_back[1]
        assert abs(float(actual_y_diff - expected_y_diff)) < 1e-10, \
            f"FRONT_FACE beam should be {float(expected_y_diff)}m forward from BACK_FACE beam, " \
            f"but difference is {float(actual_y_diff)}m"
        
        # Verify that RIGHT/LEFT don't affect Y position (they should only differ in Z)
        assert abs(float(diff_right_left[1])) < 1e-10, \
            "RIGHT_FACE and LEFT_FACE beams should have the same Y coordinate"
        
        # Verify that FRONT/BACK don't affect Z position (they should only differ in Y)
        assert abs(float(diff_front_back[2])) < 1e-10, \
            "FRONT_FACE and BACK_FACE beams should have the same Z coordinate"
        
        print(f"✅ Successfully verified 4 beams with different face features are positioned correctly")
        print(f"   RIGHT vs LEFT: {float(actual_z_diff):.6f}m Z difference (expected {float(expected_z_diff):.6f}m)")
        print(f"   FRONT vs BACK: {float(actual_y_diff):.6f}m Y difference (expected {float(expected_y_diff):.6f}m)")



class TestHelperFunctions:
    """Test helper functions for timber operations."""
    
    def test_timber_get_closest_oriented_face_axis_aligned(self):
        """Test Timber.get_closest_oriented_face_from_global_direction() with axis-aligned timber."""
        # Create an axis-aligned timber (standard orientation)
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),  # width=0.2, height=0.3
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Z-up (length)
            width_direction=create_v3(1, 0, 0)     # X-right (face/width)
        )
        
                # Test alignment with each cardinal direction
        # Note: CORRECTED timber coordinate system:
        # - TOP/BOTTOM faces are along length_direction (Z-axis)
        # - RIGHT/LEFT faces are along width_direction (X-axis)  
        # - FRONT/BACK faces are along height_direction (Y-axis)

        # Target pointing in +Z (length direction) should align with TOP face
        target_length_pos = create_v3(0, 0, 1)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_length_pos)
        assert aligned_face == TimberFace.TOP

        # Target pointing in -Z (negative length direction) should align with BOTTOM face
        target_length_neg = create_v3(0, 0, -1)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_length_neg)
        assert aligned_face == TimberFace.BOTTOM

        # Target pointing in +X (face direction) should align with RIGHT face
        target_face_pos = create_v3(1, 0, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_face_pos)
        assert aligned_face == TimberFace.RIGHT

        # Target pointing in -X (negative face direction) should align with LEFT face
        target_face_neg = create_v3(-1, 0, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_face_neg)
        assert aligned_face == TimberFace.LEFT

        # Target pointing in +Y (height direction) should align with FRONT face
        target_height_pos = create_v3(0, 1, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_height_pos)
        assert aligned_face == TimberFace.FRONT

        # Target pointing in -Y (negative height direction) should align with BACK face
        target_height_neg = create_v3(0, -1, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_height_neg)
        assert aligned_face == TimberFace.BACK
    
    def test_timber_get_closest_oriented_face_rotated(self):
        """Test Timber.get_closest_oriented_face_from_global_direction() with rotated timber."""
        # Create a timber rotated 90 degrees around Z axis
        # length_direction stays Z-up, but width_direction becomes Y-forward
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Z-up (length)
            width_direction=create_v3(0, 1, 0)     # Y-forward (face/width)
        )
        
                # Now the timber's faces are rotated (CORRECTED):
        # TOP face points in +Z direction (length_direction)
        # BOTTOM face points in -Z direction (negative length_direction)
        # RIGHT face points in +Y direction (width_direction)
        # LEFT face points in -Y direction (negative width_direction)
        # FRONT face points in -X direction (height_direction)
        # BACK face points in +X direction (negative height_direction)

        # Target pointing in +Y direction should align with RIGHT face
        target_y_pos = create_v3(0, 1, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_y_pos)
        assert aligned_face == TimberFace.RIGHT

        # Target pointing in -Y direction should align with LEFT face
        target_y_neg = create_v3(0, -1, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_y_neg)
        assert aligned_face == TimberFace.LEFT

        # Target pointing in -X direction should align with FRONT face
        target_x_neg = create_v3(-1, 0, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_x_neg)
        assert aligned_face == TimberFace.FRONT

        # Target pointing in +X direction should align with BACK face
        target_x_pos = create_v3(1, 0, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_x_pos)
        assert aligned_face == TimberFace.BACK
    
    def test_timber_get_closest_oriented_face_horizontal(self):
        """Test Timber.get_closest_oriented_face_from_global_direction() with horizontal timber."""
        # Create a horizontal timber lying along X axis
        # Note: create_standard_horizontal_timber uses width_direction=[0,1,0] by default,
        # so we need to use timber_from_directions here for width_direction=[0,0,1]
        timber = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),   # X-right (length)
            width_direction=create_v3(0, 0, 1)      # Z-up (face/width)
        )
        
        # For this horizontal timber (CORRECTED):
        # TOP face points in +X direction (length_direction)
        # BOTTOM face points in -X direction (negative length_direction)
        # RIGHT face points in +Z direction (width_direction)
        # LEFT face points in -Z direction (negative width_direction)
        # FRONT face points in -Y direction (height_direction)  
        # BACK face points in +Y direction (negative height_direction)
        
        # Target pointing in +Z should align with RIGHT face
        target_z_pos = create_v3(0, 0, 1)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_z_pos)
        assert aligned_face == TimberFace.RIGHT
        
        # Target pointing in -Z should align with LEFT face
        target_z_neg = create_v3(0, 0, -1)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_z_neg)
        assert aligned_face == TimberFace.LEFT
        
        # Target pointing in +X (length direction) should align with TOP face
        target_x_pos = create_v3(1, 0, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_x_pos)
        assert aligned_face == TimberFace.TOP
        
        # Target pointing in +Y should align with BACK face
        target_y_pos = create_v3(0, 1, 0)
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_y_pos)
        assert aligned_face == TimberFace.BACK
    
    def test_timber_get_closest_oriented_face_diagonal(self):
        """Test Timber.get_closest_oriented_face_from_global_direction() with diagonal target direction."""
        # Create an axis-aligned timber
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
                # Test with diagonal direction that's closer to +Z than +X
        # This should align with TOP face (Z-direction)
        target_diagonal_z = normalize_vector(create_v3(Rational("0.3"), 0, 1))  # Mostly +Z, little bit +X
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_diagonal_z)
        assert aligned_face == TimberFace.TOP

        # Test with diagonal direction that's closer to +X than +Z
        # This should align with RIGHT face (X-direction)
        target_diagonal_x = normalize_vector(create_v3(1, 0, Rational("0.3")))  # Mostly +X, little bit +Z
        aligned_face = timber.get_closest_oriented_face_from_global_direction(target_diagonal_x)
        assert aligned_face == TimberFace.RIGHT
    
    def test_timber_get_face_direction(self):
        """Test Timber.get_face_direction_global() method."""
        # Create an axis-aligned timber
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
        # Test that face directions match expected values (CORRECTED MAPPING)
        top_dir = timber.get_face_direction_global(TimberFace.TOP)
        assert top_dir == timber.get_length_direction_global()
        
        bottom_dir = timber.get_face_direction_global(TimberFace.BOTTOM)
        assert bottom_dir == -timber.get_length_direction_global()
        
        right_dir = timber.get_face_direction_global(TimberFace.RIGHT)
        assert right_dir == timber.get_width_direction_global()
        
        left_dir = timber.get_face_direction_global(TimberFace.LEFT)
        assert left_dir == -timber.get_width_direction_global()
        
        # FRONT should be the height direction
        front_dir = timber.get_face_direction_global(TimberFace.FRONT)
        assert front_dir == timber.get_height_direction_global()
        
        # BACK should be the negative height direction
        back_dir = timber.get_face_direction_global(TimberFace.BACK)
        assert back_dir == -timber.get_height_direction_global()
    
    def test_timber_get_face_direction_for_ends(self):
        """Test using Timber.get_face_direction_global() for timber ends."""
        # Create a timber
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
        # Test TOP end direction (using TimberFace.TOP)
        top_dir = timber.get_face_direction_global(TimberFace.TOP)
        assert top_dir == timber.get_length_direction_global()
        
        # Test BOTTOM end direction (using TimberFace.BOTTOM)
        bottom_dir = timber.get_face_direction_global(TimberFace.BOTTOM)
        assert bottom_dir == -timber.get_length_direction_global()
    
    def test_timber_get_face_direction_with_timber_reference_end(self):
        """Test that Timber.get_face_direction_global() accepts TimberReferenceEnd."""
        # Create a timber
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
        # Test TOP end direction using TimberReferenceEnd.TOP
        top_dir = timber.get_face_direction_global(TimberReferenceEnd.TOP)
        assert top_dir == timber.get_length_direction_global()
        
        # Test BOTTOM end direction using TimberReferenceEnd.BOTTOM
        bottom_dir = timber.get_face_direction_global(TimberReferenceEnd.BOTTOM)
        assert bottom_dir == -timber.get_length_direction_global()
        
        # Verify that results are the same whether using TimberFace or TimberReferenceEnd
        assert timber.get_face_direction_global(TimberReferenceEnd.TOP) == timber.get_face_direction_global(TimberFace.TOP)
        assert timber.get_face_direction_global(TimberReferenceEnd.BOTTOM) == timber.get_face_direction_global(TimberFace.BOTTOM)
    
    def test_timber_get_size_in_face_normal_axis_with_timber_reference_end(self):
        """Test that Timber.get_size_in_face_normal_axis() accepts TimberReferenceEnd."""
        # Create a timber
        timber = timber_from_directions(
            length=Rational(2),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),   # Z-up
            width_direction=create_v3(1, 0, 0)      # X-right
        )
        
        # Test that TimberReferenceEnd works
        top_size = timber.get_size_in_face_normal_axis(TimberReferenceEnd.TOP)
        assert top_size == timber.length
        
        bottom_size = timber.get_size_in_face_normal_axis(TimberReferenceEnd.BOTTOM)
        assert bottom_size == timber.length
        
        # Verify that results are the same whether using TimberFace or TimberReferenceEnd
        assert timber.get_size_in_face_normal_axis(TimberReferenceEnd.TOP) == timber.get_size_in_face_normal_axis(TimberFace.TOP)
        assert timber.get_size_in_face_normal_axis(TimberReferenceEnd.BOTTOM) == timber.get_size_in_face_normal_axis(TimberFace.BOTTOM)
    
    def test_timber_reference_end_to_timber_face_conversion(self):
        """Test TimberReferenceEnd.to.face() conversion method."""
        # Test TOP conversion
        assert TimberReferenceEnd.TOP.to.face() == TimberFace.TOP
        
        # Test BOTTOM conversion
        assert TimberReferenceEnd.BOTTOM.to.face() == TimberFace.BOTTOM
        
    def test_stickout_with_join_timbers(self):
        """Test that stickout produces correct timber length in join_timbers."""
        # Create two vertical posts 2.5 meters apart
        post1 = create_standard_vertical_timber(height=2, size=(0.15, 0.15), position=(0, 0, 0))
        post2 = create_standard_vertical_timber(height=2, size=(0.15, 0.15), position=(2.5, 0, 0))
        
        # Join with asymmetric stickout: 0.1m on post1 side, 0.3m on post2 side
        stickout1 = Rational("0.1")
        stickout2 = Rational("0.3")
        beam = join_timbers(
            timber1=post1,
            timber2=post2,
            location_on_timber1=Rational(1),
            stickout=Stickout(stickout1, stickout2),
            location_on_timber2=Rational(1),
            lateral_offset=Rational(0)
        )
        
        # Expected length: distance between posts (2.5m) + stickout1 (0.1m) + stickout2 (0.3m)
        expected_length = Rational("2.5") + stickout1 + stickout2
        assert abs(beam.length - expected_length) < 1e-10
        assert abs(beam.length - Rational("2.9")) < 1e-10
    
    def test_stickout_reference_assertions(self):
        """Test that join_timbers asserts when non-CENTER_LINE references are used."""
        import pytest
        from kumiki import StickoutReference
        
        # Create two posts 2.0 meters apart
        post1 = create_standard_vertical_timber(height=2, size=(0.2, 0.2), position=(0, 0, 0))
        post2 = create_standard_vertical_timber(height=2, size=(0.2, 0.2), position=(2, 0, 0))
        
        # Try to use INSIDE reference - should assert
        with pytest.raises(AssertionError, match="CENTER_LINE stickout reference"):
            join_timbers(
                timber1=post1,
                timber2=post2,
                location_on_timber1=Rational(1),
                stickout=Stickout(Rational("0.1"), Rational("0.1"), StickoutReference.INSIDE, StickoutReference.CENTER_LINE),
                location_on_timber2=Rational(1),
                lateral_offset=Rational(0)
            )
        
        # Try to use OUTSIDE reference - should assert
        with pytest.raises(AssertionError, match="CENTER_LINE stickout reference"):
            join_timbers(
                timber1=post1,
                timber2=post2,
                location_on_timber1=Rational(1),
                stickout=Stickout(Rational("0.1"), Rational("0.1"), StickoutReference.CENTER_LINE, StickoutReference.OUTSIDE),
                location_on_timber2=Rational(1),
                lateral_offset=Rational(0)
            )
    
    def test_stickout_reference_inside_face_aligned(self):
        """Test INSIDE stickout reference with face-aligned timbers."""
        from kumiki import StickoutReference, join_face_aligned_on_face_aligned_timbers, TimberFace
        
        # Create two parallel horizontal posts 2.0 meters apart
        post1 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.2"), Rational("0.2")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # East
            width_direction=create_v3(0, 0, 1)     # Up
        )
        
        post2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.2"), Rational("0.2")),
            bottom_position=create_v3(0, 2, 0),  # 2m north
            length_direction=create_v3(1, 0, 0),  # East (parallel)
            width_direction=create_v3(0, 0, 1)     # Up
        )
        
        # Join with INSIDE reference
        beam = join_face_aligned_on_face_aligned_timbers(
            post1, post2,
            location_on_timber1=Rational("1.5"),
            stickout=Stickout(Rational("0.1"), Rational("0.1"), StickoutReference.INSIDE, StickoutReference.INSIDE),
            lateral_offset_from_timber1=Rational(0),
            size=create_v2(Rational("0.2"), Rational("0.2")),
            feature_to_mark_on_joining_timber=None,
            orientation_face_on_timber1=TimberFace.TOP
        )
        
        # Expected length: distance (2.0) + effective_stickout1 (0.1 + 0.1) + effective_stickout2 (0.1 + 0.1)
        # = 2.0 + 0.2 + 0.2 = 2.4
        assert abs(beam.length - Rational("2.4")) < 1e-10
    
    def test_stickout_reference_outside_face_aligned(self):
        """Test OUTSIDE stickout reference with face-aligned timbers."""
        from kumiki import StickoutReference, join_face_aligned_on_face_aligned_timbers, TimberFace
        
        # Create two parallel horizontal posts 2.0 meters apart
        post1 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.2"), Rational("0.2")),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # East
            width_direction=create_v3(0, 0, 1)     # Up
        )
        
        post2 = timber_from_directions(
            length=Rational(3),
            size=create_v2(Rational("0.2"), Rational("0.2")),
            bottom_position=create_v3(0, 2, 0),  # 2m north
            length_direction=create_v3(1, 0, 0),  # East (parallel)
            width_direction=create_v3(0, 0, 1)     # Up
        )
        
        # Join with OUTSIDE reference
        beam = join_face_aligned_on_face_aligned_timbers(
            post1, post2,
            location_on_timber1=Rational("1.5"),
            stickout=Stickout(Rational("0.2"), Rational("0.2"), StickoutReference.OUTSIDE, StickoutReference.OUTSIDE),
            lateral_offset_from_timber1=Rational(0),
            size=create_v2(Rational("0.2"), Rational("0.2")),
            feature_to_mark_on_joining_timber=None,
            orientation_face_on_timber1=TimberFace.TOP
        )
        
        # Expected length: distance (2.0) + effective_stickout1 (0.2 - 0.1) + effective_stickout2 (0.2 - 0.1)
        # = 2.0 + 0.1 + 0.1 = 2.2
        assert abs(beam.length - Rational("2.2")) < 1e-10
    


class TestTimberFootprintOrientation:
    """Test timber inside/outside face determination relative to footprint."""
    
    def test_get_inside_outside_faces(self):
        """Test get_inside_face and get_outside_face for various timber configurations."""
        # Create a square footprint
        corners = [
            create_v2(0, 0),
            create_v2(10, 0),
            create_v2(10, 10),
            create_v2(0, 10)
        ]
        footprint = Footprint(tuple(corners))
        
        # Test configurations: (description, bottom_pos, length_dir, width_dir, length, expected_inside, expected_outside)
        test_cases = [
            # Horizontal timber near bottom edge (y=1), running along X
            ("bottom_edge", 
             create_v3(1, 1, 0), create_v3(1, 0, 0), create_v3(0, 1, 0), Rational(8),
             TimberFace.RIGHT, TimberFace.LEFT),
            
            # Timber near right edge (x=9), running along Y
            ("right_edge", 
             create_v3(9, 1, 0), create_v3(0, 1, 0), create_v3(-1, 0, 0), Rational(8),
             TimberFace.TOP, TimberFace.BOTTOM),
            
            # Horizontal timber near top edge (y=9), running along X
            ("top_edge", 
             create_v3(1, 9, 0), create_v3(1, 0, 0), create_v3(0, -1, 0), Rational(8),
             TimberFace.BOTTOM, TimberFace.TOP),
            
            # Timber near left edge (x=1), running along Y
            ("left_edge", 
             create_v3(1, 1, 0), create_v3(0, 1, 0), create_v3(1, 0, 0), Rational(8),
             TimberFace.TOP, TimberFace.BOTTOM),
            
            # Vertical timber near bottom edge
            ("vertical", 
             create_v3(5, 1, 0), create_v3(0, 0, 1), create_v3(0, 1, 0), Rational(3),
             TimberFace.RIGHT, TimberFace.LEFT),
        ]
        
        for description, bottom_pos, length_dir, width_dir, length, expected_inside, expected_outside in test_cases:
            timber = timber_from_directions(
                length=length,
                size=create_v2(Rational("0.2"), Rational("0.3")),
                bottom_position=bottom_pos,
                length_direction=length_dir,
                width_direction=width_dir
            )
            
            inside_face = timber.get_inside_face_from_footprint(footprint)
            outside_face = timber.get_outside_face_from_footprint(footprint)
            
            assert inside_face == expected_inside, \
                f"{description}: Expected inside face {expected_inside}, got {inside_face}"
            assert outside_face == expected_outside, \
                f"{description}: Expected outside face {expected_outside}, got {outside_face}"
    
    def test_get_inside_face_diagonal_timber(self):
        """Test get_inside_face for timber at diagonal orientation."""
        corners = [
            create_v2(0, 0),
            create_v2(10, 0),
            create_v2(10, 10),
            create_v2(0, 10)
        ]
        footprint = Footprint(tuple(corners))
        
        # Diagonal timber from (1,1) going toward (9,9), but oriented so width points inward
        timber = timber_from_directions(
            length=Rational("11.31"),  # ~8*sqrt(2)
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(1, 1, 0),
            length_direction=normalize_vector(create_v3(1, 1, 0)),  # Diagonal
            width_direction=normalize_vector(create_v3(-1, 1, 0))   # Perpendicular to length, pointing "inward-ish"
        )
        
        inside_face = timber.get_inside_face_from_footprint(footprint)
        outside_face = timber.get_outside_face_from_footprint(footprint)
        
        # Should determine a consistent inside/outside face based on nearest boundary
        # The exact face depends on which boundary is closest, but they should be opposite
        assert inside_face != outside_face
        
        # Verify that the inside and outside faces are opposite
        inside_dir = timber.get_face_direction_global(inside_face)
        outside_dir = timber.get_face_direction_global(outside_face)
        # Dot product should be negative (opposite directions)
        assert inside_dir.dot(outside_dir) < 0



class TestSplitTimber:
    """Test the split_timber method"""
    
    def test_split_timber_basic(self, symbolic_mode):
        """Test basic timber splitting at midpoint"""
        # Create a simple vertical timber
        timber = create_standard_vertical_timber(height=10, size=(4, 4), position=(0, 0, 0), ticket="Test Timber")
        
        # Split at 30% (distance 3)
        bottom_timber, top_timber = split_timber(timber, Rational(3))
        
        # Check bottom timber
        assert bottom_timber.length == Rational(3)
        assert bottom_timber.size[0] == Rational(4)
        assert bottom_timber.size[1] == Rational(4)
        assert bottom_timber.get_bottom_position_global() == create_v3(Rational(0), Rational(0), Rational(0))
        assert bottom_timber.get_length_direction_global() == create_v3(Rational(0), Rational(0), Rational(1))
        assert bottom_timber.get_width_direction_global() == create_v3(Rational(1), Rational(0), Rational(0))
        assert bottom_timber.ticket.name == "Test Timber_bottom"
        
        # Check top timber
        assert top_timber.length == Rational(7)
        assert top_timber.size[0] == Rational(4)
        assert top_timber.size[1] == Rational(4)
        assert top_timber.get_bottom_position_global() == create_v3(Rational(0), Rational(0), Rational(3))
        assert top_timber.get_length_direction_global() == create_v3(Rational(0), Rational(0), Rational(1))
        assert top_timber.get_width_direction_global() == create_v3(Rational(1), Rational(0), Rational(0))
        assert top_timber.ticket.name == "Test Timber_top"
    
    def test_split_timber_horizontal(self, symbolic_mode):
        """Test splitting a horizontal timber"""
        # Create a horizontal timber along X axis
        timber = timber_from_directions(
            length=Rational(20),
            size=create_v2(Rational(6), Rational(4)),
            bottom_position=create_v3(Rational(5), Rational(10), Rational(2)),
            length_direction=create_v3(Rational(1), Rational(0), Rational(0)),
            width_direction=create_v3(Rational(0), Rational(1), Rational(0))
        )
        
        # Split at 8 units from bottom
        bottom_timber, top_timber = split_timber(timber, Rational(8))
        
        # Check bottom timber
        assert bottom_timber.length == Rational(8)
        assert bottom_timber.get_bottom_position_global() == create_v3(Rational(5), Rational(10), Rational(2))
        
        # Check top timber
        assert top_timber.length == Rational(12)
        assert top_timber.get_bottom_position_global() == create_v3(Rational(13), Rational(10), Rational(2))  # 5 + 8
    
    def test_split_timber_diagonal(self, symbolic_mode):
        """Test splitting a diagonal timber"""
        # Create a diagonal timber at 45 degrees
        length_dir = normalize_vector(create_v3(Rational(1), Rational(1), Rational(0)))
        
        timber = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
            length_direction=length_dir,
            width_direction=normalize_vector(create_v3(Rational(-1), Rational(1), Rational(0)))
        )
        
        # Split at 4 units from bottom
        bottom_timber, top_timber = split_timber(timber, Rational(4))
        
        # Check lengths
        assert bottom_timber.length == Rational(4)
        assert top_timber.length == Rational(6)
        
        # Check positions
        assert bottom_timber.get_bottom_position_global() == create_v3(Rational(0), Rational(0), Rational(0))
        
        # Top timber should start at 4 units along the diagonal
        expected_top_pos = create_v3(Rational(0), Rational(0), Rational(0)) + Rational(4) * length_dir
        assert top_timber.get_bottom_position_global() == expected_top_pos
        
        # Both should maintain same orientation
        assert bottom_timber.get_length_direction_global() == length_dir
        assert top_timber.get_length_direction_global() == length_dir
    
    def test_split_timber_with_rational(self, symbolic_mode):
        """Test splitting with exact rational arithmetic"""
        # Create a timber with rational values
        timber = timber_from_directions(
            length=Rational(10, 1),
            size=create_v2(Rational(4, 1), Rational(4, 1)),
            bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
            length_direction=create_v3(Rational(0), Rational(0), Rational(1)),
            width_direction=create_v3(Rational(1), Rational(0), Rational(0))
        )
        
        # Split at exact rational point
        split_distance = Rational(3, 1)
        bottom_timber, top_timber = split_timber(timber, split_distance)
        
        # Check exact rational values
        assert bottom_timber.length == Rational(3, 1)
        assert top_timber.length == Rational(7, 1)
        assert top_timber.get_bottom_position_global()[2] == Rational(3, 1)
    
    def test_split_timber_invalid_distance(self):
        """Test that invalid split distances raise assertions"""
        timber = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
            length_direction=create_v3(Rational(0), Rational(0), Rational(1)),
            width_direction=create_v3(Rational(1), Rational(0), Rational(0))
        )
        
        # Test split at 0 (should fail)
        try:
            split_timber(timber, Rational(0))
            assert False, "Should have raised assertion for distance = 0"
        except AssertionError:
            pass
        
        # Test split at length (should fail)
        try:
            split_timber(timber, Rational(10))
            assert False, "Should have raised assertion for distance = length"
        except AssertionError:
            pass
        
        # Test split beyond length (should fail)
        try:
            split_timber(timber, Rational(15))
            assert False, "Should have raised assertion for distance > length"
        except AssertionError:
            pass
        
        # Test negative distance (should fail)
        try:
            split_timber(timber, Rational(-5))
            assert False, "Should have raised assertion for negative distance"
        except AssertionError:
            pass
    
    def test_split_timber_preserves_orientation(self):
        """Test that both resulting timbers preserve the original orientation"""
        # Create a timber with non-standard orientation
        timber = timber_from_directions(
            length=Rational(15),
            size=create_v2(Rational(6), Rational(8)),
            bottom_position=create_v3(Rational(1), Rational(2), Rational(3)),
            length_direction=normalize_vector(create_v3(Rational(0), Rational(1), Rational(1))),
            width_direction=normalize_vector(create_v3(Rational(1), Rational(0), Rational(0)))
        )
        
        bottom_timber, top_timber = split_timber(timber, Rational(5))
        
        # Both should have same orientation as original
        assert bottom_timber.get_length_direction_global() == timber.get_length_direction_global()
        assert bottom_timber.get_width_direction_global() == timber.get_width_direction_global()
        assert bottom_timber.get_height_direction_global() == timber.get_height_direction_global()
        
        assert top_timber.get_length_direction_global() == timber.get_length_direction_global()
        assert top_timber.get_width_direction_global() == timber.get_width_direction_global()
        assert top_timber.get_height_direction_global() == timber.get_height_direction_global()
        
        # Both should have same size as original
        assert bottom_timber.size[0] == timber.size[0]
        assert bottom_timber.size[1] == timber.size[1]
        assert top_timber.size[0] == timber.size[0]
        assert top_timber.size[1] == timber.size[1]


def test_join_plane_aligned_on_place_aligned_timbers():
    # Let's use create_timber
    t1 = create_timber(create_v3(0, 0, 0), Rational(100), create_v2(10, 10), length_direction=create_v3(0, 1, 0), width_direction=create_v3(0, 0, 1))
    t2 = create_timber(create_v3(50, -50, 0), Rational(100), create_v2(10, 10), length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 0, 1))
    
    stickout = Stickout(stickout1=Rational(0), stickout2=Rational(0))
    size = create_v2(10, 10)
    
    res = join_plane_aligned_on_place_aligned_timbers(t1, t2, Rational(20), Rational(70), stickout, size)
    assert float(res.length) == pytest.approx(138.924, 0.01)
    assert are_vectors_parallel(
        res.get_face_direction_global(TimberLongFace.RIGHT),
        t1.get_face_direction_global(TimberLongFace.LEFT),
    )

