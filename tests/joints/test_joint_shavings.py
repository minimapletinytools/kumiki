"""
Tests for joint_shavings.py - Helper functions for joint validation
"""

import pytest
from sympy import Rational
from kumiki.joints.joint_shavings import (
    check_timber_overlap_for_splice_joint_is_sensible, 
    chop_timber_end_with_prism,
    chop_timber_end_with_half_plane,
    chop_lap_on_timber_end,
    chop_shoulder_notch_on_timber_face,
    scribe_face_plane_onto_centerline,
    scribe_centerline_onto_centerline
)
from kumiki.timber import timber_from_directions, TimberReferenceEnd, TimberFace, TimberLongFace
from kumiki.rule import create_v3, create_v2, inches, are_vectors_parallel
from kumiki.cutcsg import SolidUnion, RectangularPrism, HalfSpace
from kumiki.measuring import mark_distance_from_end_along_centerline

# TODO too many tests, just delete some lol... or combine into 1 test that varies only the timber length...
class TestCheckTimberOverlapForSpliceJoint:
    """Tests for check_timber_overlap_for_splice_joint_is_sensible function."""
    
    def test_valid_splice_configuration_overlapping(self):
        """Test a valid splice joint with overlapping timbers pointing opposite directions."""
        # Create two 4x4 timbers, 3 feet long, overlapping in the middle
        timber_length = inches(36)
        timber_size = create_v2(inches(4), inches(4))
        
        # TimberA pointing east (left to right)
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        # TimberB pointing west (right to left), positioned to overlap
        # For timbers pointing opposite directions, join matching ends (TOP to TOP)
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(timber_length * 2, 0, 0),
            length_direction=create_v3(-1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        # Check the configuration - join TOP to TOP so ends face each other
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP
        )
        
        assert error is None, f"Expected no error, but got: {error}"
    
    def test_valid_splice_configuration_just_touching(self):
        """Test a valid splice joint where timber ends just touch."""
        timber_length = inches(36)
        timber_size = create_v2(inches(4), inches(4))
        
        # TimberA pointing east
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        # TimberB pointing west, TOP ends exactly touch
        # For opposite direction timbers, join matching ends so they face each other
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(2 * timber_length, 0, 0),  # Start further right
            length_direction=create_v3(-1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        # Join TOP to TOP so ends face each other
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP
        )
        
        assert error is None, f"Expected no error for touching ends, but got: {error}"
    
    def test_invalid_same_direction(self):
        """Test that ends facing away from each other trigger an error."""
        timber_length = inches(36)
        timber_size = create_v2(inches(4), inches(4))
        
        # Both timbers pointing east
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(timber_length, 0, 0),
            length_direction=create_v3(1, 0, 0),  # Same direction!
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        # Invalid: joining TOP to TOP when both point same direction
        # (both ends face same direction, away from each other)
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP
        )
        
        assert error is not None, "Expected error for ends facing away from each other"
        assert "same direction" in error.lower()
        assert "dot product" in error.lower()
    
    def test_invalid_not_parallel(self):
        """Test that non-parallel timbers trigger an error."""
        timber_length = inches(36)
        timber_size = create_v2(inches(4), inches(4))
        
        # TimberA pointing east
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        # TimberB pointing up (perpendicular, not parallel)
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(timber_length, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Perpendicular!
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP
        )
        
        assert error is not None, "Expected error for non-parallel timbers"
        assert "not parallel" in error.lower()
    
    def test_invalid_separated_by_gap(self):
        """Test that timbers separated by a gap trigger an error."""
        timber_length = inches(36)
        timber_size = create_v2(inches(4), inches(4))
        gap = inches(6)  # 6 inch gap
        
        # TimberA pointing east, TOP end at inches(36)
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        # TimberB pointing west, TOP end at inches(36-6)=inches(30)
        # So there's a 6 inch gap between timberA's TOP and timberB's TOP
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(inches(30) - timber_length, 0, 0),  # Bottom at -6 inches
            length_direction=create_v3(-1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP
        )
        
        assert error is not None, "Expected error for separated timbers"
        assert "separated" in error.lower() or "gap" in error.lower()
    
    def test_vertical_timbers(self):
        """Test validation works with vertical timbers."""
        timber_length = inches(96)  # 8 feet tall
        timber_size = create_v2(inches(6), inches(6))
        
        # TimberA pointing up (vertical post)
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timberA"
        )
        
        # TimberB pointing down, overlapping in the middle
        # For opposite direction timbers, join matching ends (TOP to TOP)
        # TimberA TOP is at z=timber_length
        # Position TimberB so its TOP is at z=1.5*timber_length (overlapping)
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, timber_length * Rational(5, 2)),  # Start at 2.5*L
            length_direction=create_v3(0, 0, -1),  # Pointing down, so TOP is at 1.5*L
            width_direction=create_v3(1, 0, 0),
            ticket="timberB"
        )
        
        # Join TOP to TOP so ends face each other
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP
        )
        
        assert error is None, f"Expected no error for vertical splice, but got: {error}"
    
    def test_different_timber_sizes(self):
        """Test validation works with different sized timbers."""
        # 4x4 timber, 36 inches long
        timberA_length = inches(36)
        timberA = timber_from_directions(
            length=timberA_length,
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        # 6x8 timber, 48 inches long, pointing opposite direction
        # For opposite direction timbers, join matching ends (TOP to TOP)
        # TimberA TOP is at x=36"
        # Position TimberB so its TOP is at x=48" (overlapping)
        timberB_length = inches(48)
        timberB = timber_from_directions(
            length=timberB_length,
            size=create_v2(inches(6), inches(8)),
            bottom_position=create_v3(timberA_length + timberB_length, 0, 0),  # Start at 84"
            length_direction=create_v3(-1, 0, 0),  # Pointing left, so TOP is at 36"
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        # Join TOP to TOP so ends face each other (both at x=36")
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP
        )
        
        # Should be valid - sizes don't matter for this check
        assert error is None, f"Expected no error for different sizes, but got: {error}"
    
    def test_valid_same_direction_opposite_ends(self):
        """Test that same direction timbers can have valid splice when joining opposite ends (oscarshed case)."""
        timber_length = inches(36)
        timber_size = create_v2(inches(4), inches(4))
        
        # Both timbers pointing east (e.g., split from same timber)
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(timber_length, 0, 0),
            length_direction=create_v3(1, 0, 0),  # Same direction!
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        # Valid: joining TOP to BOTTOM when both point same direction
        # (ends face towards each other)
        error = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.BOTTOM
        )
        
        assert error is None, f"Expected no error for same direction opposite ends (oscarshed case), but got: {error}"
    
    def test_swapped_end_references(self):
        """Test that using BOTTOM/TOP vs TOP/BOTTOM both work correctly."""
        timber_length = inches(36)
        timber_size = create_v2(inches(4), inches(4))
        
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(timber_length * 2, 0, 0),
            length_direction=create_v3(-1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        # Test with TOP/BOTTOM (normal)
        error1 = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.TOP, TimberReferenceEnd.BOTTOM
        )
        
        # Test with BOTTOM/TOP (swapped)
        error2 = check_timber_overlap_for_splice_joint_is_sensible(
            timberA, timberB, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP
        )
        
        # Both should work (one will likely give an error about direction or separation)
        # Just checking it doesn't crash
        assert isinstance(error1, (str, type(None)))
        assert isinstance(error2, (str, type(None)))


class TestChopTimberEndWithPrism:
    """Tests for chop_timber_end_with_prism function."""
    
    def test_chop_top_end(self):
        """Test chopping from the top end of a timber."""
        # Create a simple vertical timber: 4x4 inches, 10 feet tall
        timber = timber_from_directions(
            length=inches(120),  # 10 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        # Chop 2 feet from the top
        chop_distance = inches(24)
        prism = chop_timber_end_with_prism(timber, TimberReferenceEnd.TOP, chop_distance)
        
        # Verify the prism properties
        assert prism.size == timber.size
        # Should be in local coordinates (identity transform)
        assert prism.transform == timber.transform.identity()
        
        # For TOP end with distance 24 from end:
        # start_distance should be at (120 - 24) = 96 inches from bottom
        # end_distance should be None (infinite upward)
        assert prism.start_distance == inches(96)
        assert prism.end_distance is None
    
    def test_chop_bottom_end(self):
        """Test chopping from the bottom end of a timber."""
        # Create a simple vertical timber: 4x4 inches, 10 feet tall
        timber = timber_from_directions(
            length=inches(120),  # 10 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        # Chop 2 feet from the bottom
        chop_distance = inches(24)
        prism = chop_timber_end_with_prism(timber, TimberReferenceEnd.BOTTOM, chop_distance)
        
        # Verify the prism properties
        assert prism.size == timber.size
        assert prism.transform == timber.transform.identity()
        
        # For BOTTOM end with distance 24 from end:
        # start_distance should be None (infinite downward)
        # end_distance should be at 24 inches from bottom
        assert prism.start_distance is None
        assert prism.end_distance == inches(24)
    
    def test_chop_horizontal_timber(self):
        """Test chopping a horizontal timber to ensure it works in any orientation."""
        # Create a horizontal timber pointing east
        timber = timber_from_directions(
            length=inches(48),  # 4 feet
            size=create_v2(inches(6), inches(6)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="horizontal_timber"
        )
        
        # Chop 6 inches from the top (east) end
        chop_distance = inches(6)
        prism = chop_timber_end_with_prism(timber, TimberReferenceEnd.TOP, chop_distance)
        
        # Verify the prism has correct dimensions
        assert prism.size == timber.size
        assert prism.transform == timber.transform.identity()
        assert prism.start_distance == inches(42)  # 48 - 6
        assert prism.end_distance is None
    
    def test_chop_with_rational_distances(self):
        """Test that the function works with Rational arithmetic."""
        timber = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(2), Rational(2)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        # Chop 1/3 from the top
        chop_distance = Rational(1, 3)
        prism = chop_timber_end_with_prism(timber, TimberReferenceEnd.TOP, chop_distance)
        
        # Should get exact rational arithmetic
        expected_start = Rational(10) - Rational(1, 3)
        assert prism.start_distance == expected_start
        assert prism.end_distance is None


class TestChopTimberEndWithHalfspace:
    """Tests for chop_timber_end_with_half_plane function."""
    
    def test_chop_top_end(self):
        """Test chopping from the top end of a timber with a half-plane."""
        # Create a simple vertical timber: 4x4 inches, 10 feet tall
        timber = timber_from_directions(
            length=inches(120),  # 10 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        # Chop 2 feet from the top
        chop_distance = inches(24)
        half_plane = chop_timber_end_with_half_plane(timber, TimberReferenceEnd.TOP, chop_distance)
        
        # For TOP end with distance 24 from end:
        # - Normal should point in +Z direction (0, 0, 1)
        # - Offset should be at (120 - 24) = 96 inches from bottom
        assert half_plane.normal == create_v3(0, 0, 1)
        assert half_plane.offset == inches(96)
    
    def test_chop_bottom_end(self):
        """Test chopping from the bottom end of a timber with a half-plane."""
        # Create a simple vertical timber: 4x4 inches, 10 feet tall
        timber = timber_from_directions(
            length=inches(120),  # 10 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        # Chop 2 feet from the bottom
        chop_distance = inches(24)
        half_plane = chop_timber_end_with_half_plane(timber, TimberReferenceEnd.BOTTOM, chop_distance)
        
        # For BOTTOM end with distance 24 from end:
        # - Normal should point in -Z direction (0, 0, -1)
        # - Offset should be -24 inches
        assert half_plane.normal == create_v3(0, 0, -1)
        assert half_plane.offset == -inches(24)
    
    def test_chop_with_rational_distances(self):
        """Test that the function works with Rational arithmetic."""
        timber = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(2), Rational(2)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        
        # Chop 1/3 from the top
        chop_distance = Rational(1, 3)
        half_plane = chop_timber_end_with_half_plane(timber, TimberReferenceEnd.TOP, chop_distance)
        
        # Should get exact rational arithmetic
        expected_offset = Rational(10) - Rational(1, 3)
        assert half_plane.offset == expected_offset
        assert half_plane.normal == create_v3(0, 0, 1)


class TestChopLapOnTimberEnd:
    """Tests for chop_lap_on_timber_end function."""
    
    def test_lap_on_right_face_geometry(self, symbolic_mode):
        """
        Test lap joint cut on RIGHT face of a timber.
        
        Creates a 4"x6" timber that is 4 ft long.
        Lap length is 1ft, shoulder 6" from end, lap face is RIGHT.
        lap_depth=2" means we KEEP 2" on the RIGHT side and REMOVE from the LEFT side.
        Tests boundary points and verifies CSG structure.
        """
        # Create a 4"x6" timber that is 4 ft long
        timber = timber_from_directions(
            length=inches(48),  # 4 ft
            size=create_v2(inches(4), inches(6)),  # 4" wide x 6" high
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Along Z axis
            width_direction=create_v3(1, 0, 0),   # Width along X axis
            ticket="test_timber"
        )
        
        # Lap parameters
        lap_length = inches(12)  # 1 ft
        shoulder_distance = inches(6)  # 6" from end
        lap_depth = inches(2)  # 2" depth to KEEP on RIGHT side (half of 4" width for half-lap)
        lap_face = TimberFace.RIGHT  # Lap on RIGHT face (keep material here)
        lap_end = TimberReferenceEnd.TOP  # Cutting from top end
        
        # Create the lap cut
        lap_prism, lap_end_cut = chop_lap_on_timber_end(
            lap_timber=timber,
            lap_timber_end=lap_end,
            lap_timber_face=lap_face,
            lap_length=lap_length,
            lap_shoulder_position_from_lap_timber_end=shoulder_distance,
            lap_depth=lap_depth
        )
        
        # Verify the components
        assert isinstance(lap_prism, RectangularPrism), "Lap prism should be a RectangularPrism"
        assert isinstance(lap_end_cut, HalfSpace), "Lap end cut should be a HalfSpace"
        
        # Use the prism and end cut
        prism = lap_prism
        half_plane = lap_end_cut
        
        # Create a union for testing the combined behavior
        lap_csg = SolidUnion([prism, half_plane])
        
        # Verify geometry based on the implementation:
        # For TOP end with shoulder_distance=6", lap_length=12":
        # - Timber end at 48" from bottom
        # - Shoulder at 48" - 6" = 42" from bottom
        # - Lap extends from shoulder in +Z direction by lap_length = 42" + 12" = 54" from bottom
        # - RectangularPrism from 42" to 54", HalfSpace at 54"
        expected_shoulder_z = inches(42)  # 48" - 6"
        expected_lap_end_z = inches(54)   # 42" + 12"
        
        # Check that prism extends from shoulder to lap end
        assert prism.start_distance == expected_shoulder_z, \
            f"RectangularPrism should start at shoulder (z={expected_shoulder_z}), got {prism.start_distance}"
        assert prism.end_distance == expected_lap_end_z, \
            f"RectangularPrism should end at lap end (z={expected_lap_end_z}), got {prism.end_distance}"
        
        # Check that half plane coincides with lap end
        assert half_plane.offset == expected_lap_end_z, \
            f"HalfSpace should be at lap end (z={expected_lap_end_z}), got {half_plane.offset}"
        
        # Test point 1: 6" down from timber end (at shoulder), on the LEFT face (removed side)
        # Timber is 4" wide centered at x=0, so LEFT face is at x=-2"
        # With lap_face=RIGHT and lap_depth=2", we keep x=0 to x=+2", remove x=-2" to x=0
        # LEFT face at x=-2" should be IN the CSG (material removed)
        point1 = create_v3(inches(-2), 0, expected_shoulder_z)
        assert lap_csg.contains_point(point1), \
            "Point at shoulder on LEFT face (removed side) should be in the removed region"
        
        # Test point 2: At the boundary between removed and kept material (x=0)
        # This should be at the boundary (on the edge of the prism)
        point2 = create_v3(0, 0, expected_shoulder_z)
        assert lap_csg.contains_point(point2), \
            "Point at boundary (x=0) at shoulder should be on boundary (contained)"
        
        # Test point 3: On the RIGHT face (kept side) at x=+2"
        # This should NOT be in the removed region (material is kept here)
        point3 = create_v3(inches(2), 0, expected_shoulder_z)
        assert not lap_csg.contains_point(point3), \
            "Point at shoulder on RIGHT face (kept side) should NOT be in the removed region"
        
        # Test point 4: Below the shoulder (outside lap region)
        # This is BELOW the prism start (shoulder at 42"), so should NOT be in CSG
        point4 = create_v3(0, 0, expected_shoulder_z - inches(3))
        assert not lap_csg.contains_point(point4), \
            "Point 3\" below shoulder (outside lap region) should NOT be in the removed region"


class TestChopShoulderNotchOnTimberFace:
    """Tests for chop_shoulder_notch_on_timber_face function."""
    
    def test_shoulder_notch_on_each_face(self):
        """
        Test that shoulder notch correctly removes material from the specified face only.
        
        For each long face (LEFT, RIGHT, FRONT, BACK), create a notch and verify:
        - A point on the notched face (in the middle) IS contained in the notch CSG (will be removed)
        - Points on the other three faces are NOT contained in the notch CSG (will remain)
        """
        # Create a vertical 4"x4"x4' timber
        timber_width = inches(4)
        timber_height = inches(4)
        timber_length = inches(48)  # 4 feet
        
        timber = timber_from_directions(
            length=timber_length,
            size=create_v2(timber_width, timber_height),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Vertical (along Z)
            width_direction=create_v3(1, 0, 0),   # Width along X
            ticket='test_timber'
        )
        # Timber orientation:
        # - width_direction (X): RIGHT face at +X, LEFT face at -X
        # - height_direction (Y): FRONT face at +Y, BACK face at -Y
        # - length_direction (Z): TOP face at +Z, BOTTOM face at -Z
        
        # Notch parameters
        notch_depth = inches(1)    # 1" deep into the timber
        notch_width = inches(4)    # 4" wide along timber length
        notch_center = timber_length / Rational(2)  # Middle of timber (24" from bottom)
        
        # Test each long face
        long_faces = [TimberFace.LEFT, TimberFace.RIGHT, TimberFace.FRONT, TimberFace.BACK]
        
        for notch_face in long_faces:
            # Create the shoulder notch on this face
            notch_csg = chop_shoulder_notch_on_timber_face(
                timber=timber,
                notch_face=notch_face,
                distance_along_timber=notch_center,
                notch_width=notch_width,
                notch_depth=notch_depth
            )
            
            # Verify it's a RectangularPrism
            assert isinstance(notch_csg, RectangularPrism), f"Expected RectangularPrism, got {type(notch_csg).__name__}"
            
            # Define test points on each face at the middle of the timber
            # All points are at the center height (notch_center) and centered on the timber cross-section
            # but offset to be on the surface of each face
            half_width = timber_width / Rational(2)
            half_height = timber_height / Rational(2)
            
            # Points on each face (on the surface, at the middle of timber length)
            test_points = {
                TimberFace.RIGHT: create_v3(half_width, 0, notch_center),
                TimberFace.LEFT: create_v3(-half_width, 0, notch_center),
                TimberFace.FRONT: create_v3(0, half_height, notch_center),
                TimberFace.BACK: create_v3(0, -half_height, notch_center)
            }
            
            # Test each point
            for test_face, test_point in test_points.items():
                point_contained = notch_csg.contains_point(test_point)
                
                if test_face == notch_face:
                    # Point on the notched face should be contained in the notch CSG (will be removed)
                    assert point_contained, \
                        f"Point on notched face {notch_face.name} should be contained in notch CSG, but was not"
                else:
                    # Points on other faces should NOT be contained in the notch CSG (will remain)
                    assert not point_contained, \
                        f"Point on face {test_face.name} should NOT be contained in notch on {notch_face.name}, but was"


class TestScribeFaceOnCenterline:
    """Tests for scribe_face_plane_onto_centerline function."""
    
    def test_horizontal_timbers_butt_joint(self, symbolic_mode):
        """
        Test scribing from timber_a's TOP end to timber_b's LEFT face.
        
        Classic butt joint scenario: horizontal timber approaching a vertical face.
        """
        # Create timber_a pointing east (horizontal)
        timber_a = timber_from_directions(
            length=inches(48),  # 4 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, inches(4)),  # 4 inches above ground
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="timber_a"
        )
        # timber_a's TOP end is at (48", 0, 4"), centerline runs along x-axis
        
        # Create timber_b vertical with LEFT face that will intersect timber_a's centerline
        timber_b = timber_from_directions(
            length=inches(96),  # 8 feet tall
            size=create_v2(inches(6), inches(6)),
            bottom_position=create_v3(inches(60), 0, 0),  # Bottom at x=60"
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_b"
        )
        # timber_b's LEFT face is at x = 60" - 3" = 57" (normal pointing in -x direction)
        
        # Scribe timber_b's LEFT face plane and measure onto timber_a's centerline from TOP
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.LEFT,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.TOP)
        distance = marking.distance
        
        # Expected calculation (true geometric intersection):
        # - timber_a's centerline: P = (48", 0, 4") + t*(-1, 0, 0) [measuring from TOP, going backward]
        # - timber_b's LEFT face plane: normal = (-1, 0, 0), plane at x = 57"
        # - Intersection: -1 * (x - 57") = 0 => x = 57"
        # - From line: 48" - t = 57" => t = -9"
        # - Negative means we need to go backward from the TOP end (past the end)
        expected_distance = inches(-9)
        assert distance == expected_distance, \
            f"Expected distance {expected_distance}, got {distance}"
    
    def test_vertical_timbers_face_to_face(self, symbolic_mode):
        """
        Test scribing between a vertical timber and a horizontal timber's vertical face.
        """
        # Create timber_a pointing up
        timber_a = timber_from_directions(
            length=inches(96),  # 8 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_a"
        )
        # timber_a's TOP end is at (0, 0, 96"), centerline runs along z-axis
        
        # Create timber_b horizontal so its BACK face (pointing down) intersects timber_a's centerline
        timber_b = timber_from_directions(
            length=inches(48),  # 4 feet
            size=create_v2(inches(6), inches(6)),
            bottom_position=create_v3(inches(-10), 0, inches(50)),  # BACK face at z=50"-3"=47"
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="timber_b"
        )
        # timber_b's BACK face is at z = 50" - 3" = 47" (normal pointing in -z direction, downward)
        
        # Scribe timber_b's BACK face plane and measure onto timber_a's centerline from TOP
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.BACK,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.TOP)
        distance = marking.distance
        
        # Expected calculation (true geometric intersection):
        # - timber_a's centerline: P = (0, 0, 96") + t*(0, 0, -1) [measuring from TOP, going down]
        # - timber_b's BACK face plane: normal = (0, 0, -1), plane at z = 47"
        # - Intersection: -1 * (z - 47") = 0 => z = 47"
        # - From line: 96" - t = 47" => t = 49"
        # - Positive means going into the timber from the TOP end
        expected_distance = inches(49)
        assert distance == expected_distance, \
            f"Expected distance {expected_distance}, got {distance}"
    
    def test_scribe_from_bottom_end(self, symbolic_mode):
        """Test scribing from the BOTTOM end of a timber."""
        # Create timber_a pointing up
        timber_a = timber_from_directions(
            length=inches(96),  # 8 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, inches(12)),  # Bottom at z=12"
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_a"
        )
        # timber_a's BOTTOM end is at (0, 0, 12"), centerline runs along z-axis
        # timber_a's TOP end is at (0, 0, 108")
        
        # Create timber_b horizontal with FRONT face (pointing up) intersecting timber_a's centerline
        timber_b = timber_from_directions(
            length=inches(48),  # 4 feet
            size=create_v2(inches(6), inches(6)),
            bottom_position=create_v3(0, 0, 0),  # FRONT face at z=3"
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="timber_b"
        )
        # timber_b's FRONT face is at z = 0" + 3" = 3" (normal pointing in +z direction, upward)
        
        # Scribe timber_b's FRONT face plane and measure onto timber_a's centerline from BOTTOM
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.FRONT,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.BOTTOM)
        distance = marking.distance
        
        # Expected calculation (true geometric intersection):
        # - timber_a's centerline: P = (0, 0, 12") + t*(0, 0, 1) [measuring from BOTTOM, going up]
        # - timber_b's FRONT face plane: normal = (0, 0, 1), plane at z = 3"
        # - Intersection: 1 * (z - 3") = 0 => z = 3"
        # - From line: 12" + t = 3" => t = -9"
        # - Negative means going backward from the BOTTOM end (below the timber)
        expected_distance = inches(-9)
        assert distance == expected_distance, \
            f"Expected distance {expected_distance}, got {distance}"
    
    def test_scribe_to_end_face_top(self, symbolic_mode):
        """Test scribing to an upward-pointing face."""
        # Create timber_a vertical
        timber_a = timber_from_directions(
            length=inches(48),  # 4 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_a"
        )
        # timber_a's TOP end is at (0, 0, 48"), centerline runs along z-axis
        
        # Create timber_b horizontal with its FRONT face (pointing up) intersecting timber_a's centerline
        timber_b = timber_from_directions(
            length=inches(60),  # 5 feet
            size=create_v2(inches(6), inches(6)),
            bottom_position=create_v3(inches(-10), 0, inches(27)),  # FRONT face at z=27"+3"=30"
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="timber_b"
        )
        # timber_b's FRONT face is at z = 27" + 3" = 30" (normal pointing in +z direction, upward)
        
        # Scribe timber_b's FRONT face plane and measure onto timber_a's centerline from TOP
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.FRONT,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.TOP)
        distance = marking.distance
        
        # Expected calculation (true geometric intersection):
        # - timber_a's centerline: P = (0, 0, 48") + t*(0, 0, -1) [measuring from TOP, going down]
        # - timber_b's FRONT face plane: normal = (0, 0, 1), plane at z = 30"
        # - Intersection: 1 * (z - 30") = 0 => z = 30"
        # - From line: 48" - t = 30" => t = 18"
        # - Positive means going into the timber from the TOP end
        expected_distance = inches(18)
        assert distance == expected_distance, \
            f"Expected distance {expected_distance}, got {distance}"
    
    def test_scribe_to_long_face(self, symbolic_mode):
        """Test scribing to a long face (FRONT/BACK/LEFT/RIGHT)."""
        # Create timber_a horizontal
        timber_a = timber_from_directions(
            length=inches(36),  # 3 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="timber_a"
        )
        # timber_a's TOP end is at x=36"
        
        # Create timber_b vertical
        timber_b = timber_from_directions(
            length=inches(96),  # 8 feet
            size=create_v2(inches(6), inches(6)),
            bottom_position=create_v3(inches(50), 0, 0),
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_b"
        )
        # timber_b's LEFT face is at x = 50" - 3" = 47"
        # timber_b's LEFT face center (mid-length) is at (47", 0, 48")
        
        # Scribe timber_b's LEFT face plane and measure onto timber_a's centerline from TOP
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.LEFT,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.TOP)
        distance = marking.distance
        
        # Expected calculation:
        # - timber_a's TOP end position: (36", 0, 0)
        # - timber_b's LEFT face center: (47", 0, 48")
        # - Vector from timber_a TOP to timber_b LEFT face: (11", 0, 48")
        # - timber_a's into_timber_direction from TOP = -length_direction = (-1, 0, 0)
        # - Signed distance = (11", 0, 48") · (-1, 0, 0) = -11"
        # Negative means moving in opposite direction along timber_a
        expected_distance = inches(-11)
        assert distance == expected_distance, \
            f"Expected distance {expected_distance}, got {distance}"
    
    def test_with_rational_arithmetic(self, symbolic_mode):
        """Test that the function works correctly with exact Rational arithmetic."""
        # Create timber_a vertical with Rational dimensions
        timber_a = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational(2), Rational(2)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_a"
        )
        # timber_a's TOP end is at (0, 0, 10), centerline runs along z-axis
        
        # Create timber_b horizontal with its BACK face (pointing down) intersecting timber_a's centerline
        timber_b = timber_from_directions(
            length=Rational(20),
            size=create_v2(Rational(3), Rational(3)),
            bottom_position=create_v3(Rational(-5), 0, Rational(7) + Rational(3)/2),  # BACK face at z=7
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="timber_b"
        )
        # timber_b's BACK face is at z = 7 + 3/2 - 3/2 = 7 (normal pointing in -z direction, downward)
        
        # Scribe timber_b's BACK face plane and measure onto timber_a's centerline from TOP
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.BACK,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.TOP)
        distance = marking.distance
        
        # Expected calculation (true geometric intersection):
        # - timber_a's centerline: P = (0, 0, 10) + t*(0, 0, -1) [measuring from TOP, going down]
        # - timber_b's BACK face plane: normal = (0, 0, -1), plane at z = 7
        # - Intersection: -1 * (z - 7) = 0 => z = 7
        # - From line: 10 - t = 7 => t = 3
        # - Positive means going into the timber from the TOP end
        expected_distance = Rational(3)
        assert distance == expected_distance, \
            f"Expected exact rational {expected_distance}, got {distance}"
    
    def test_positive_distance_into_timber(self, symbolic_mode):
        """Test a case where the intersection is in the positive direction (into the timber)."""
        # Create timber_a pointing east
        timber_a = timber_from_directions(
            length=inches(48),  # 4 feet
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),  # Pointing east
            width_direction=create_v3(0, 1, 0),
            ticket="timber_a"
        )
        # timber_a's TOP end is at (48", 0, 0), centerline runs along x-axis
        
        # Create timber_b vertical with LEFT face that intersects at x=36" (before timber_a's TOP end)
        timber_b = timber_from_directions(
            length=inches(60),  # 5 feet
            size=create_v2(inches(6), inches(6)),
            bottom_position=create_v3(inches(36), 0, 0),  # LEFT face at x=36"-3"=33"
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_b"
        )
        # timber_b's LEFT face is at x = 36" - 3" = 33" (normal pointing in -x direction)
        
        # Scribe timber_b's LEFT face plane and measure onto timber_a's centerline from TOP
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.LEFT,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.TOP)
        distance = marking.distance
        
        # Expected calculation (true geometric intersection):
        # - timber_a's centerline: P = (48", 0, 0) + t*(-1, 0, 0) [measuring from TOP, going backward]
        # - timber_b's LEFT face plane: normal = (-1, 0, 0), plane at x = 33"
        # - Intersection: -1 * (x - 33") = 0 => x = 33"
        # - From line: 48" - t = 33" => t = 15"
        # - Positive means going into the timber from the TOP end (backward toward BOTTOM)
        expected_distance = inches(15)
        assert distance == expected_distance, \
            f"Expected distance {expected_distance}, got {distance}"
    
    def test_different_timber_sizes(self, symbolic_mode):
        """Test scribing between timbers of different cross-sectional sizes."""
        # Create small timber_a
        timber_a = timber_from_directions(
            length=inches(24),  # 2 feet
            size=create_v2(inches(2), inches(4)),  # 2x4
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_a"
        )
        # timber_a's TOP end is at z=24"
        
        # Create larger timber_b
        timber_b = timber_from_directions(
            length=inches(48),  # 4 feet
            size=create_v2(inches(8), inches(8)),  # 8x8
            bottom_position=create_v3(0, 0, inches(36)),  # Start at z=36"
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="timber_b"
        )
        # timber_b's BOTTOM face (end face) is at z=36"
        # timber_b's BOTTOM face center: (0, 0, 36")
        
        # Scribe timber_b's BOTTOM face plane and measure onto timber_a's centerline from TOP
        face_plane = scribe_face_plane_onto_centerline(
            face=TimberFace.BOTTOM,
            face_timber=timber_b
        )
        marking = mark_distance_from_end_along_centerline(face_plane, timber_a, TimberReferenceEnd.TOP)
        distance = marking.distance
        
        # Expected calculation (true geometric intersection):
        # - timber_a's centerline from TOP: P = (0, 0, 24") + t*(0, 0, -1) [going down]
        # - timber_b's BOTTOM face plane: normal = (0, 0, -1), point at center of bottom face = (0, 0, 36")
        # - Intersection: (0,0,-1) · ((0,0,36") - (0,0,24")) / ((0,0,-1) · (0,0,-1)) = -12/1 = -12"
        # - Distance = -12" (negative = plane is outside the timber, above TOP end)
        expected_distance = -inches(12)
        assert distance == expected_distance, \
            f"Expected distance {expected_distance}, got {distance}"


class TestFindProjectedIntersectionOnCenterlines:
    """Tests for scribe_centerline_onto_centerline function."""
    
    def test_orthogonal_timbers_t_joint(self, symbolic_mode):
        """Test with orthogonal timbers forming a T-joint."""
        # Vertical timber (receiving)
        timber_vertical = timber_from_directions(
            length=inches(36),
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),  # Pointing up
            width_direction=create_v3(1, 0, 0),
            ticket="vertical"
        )
        
        # Horizontal timber intersecting at middle of vertical
        timber_horizontal = timber_from_directions(
            length=inches(24),
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, inches(12), inches(18)),  # 18" up on vertical
            length_direction=create_v3(0, -1, 0),  # Pointing toward vertical
            width_direction=create_v3(1, 0, 0),
            ticket="horizontal"
        )
        
        # Find closest points
        # Mark the horizontal timber's centerline and measure onto vertical timber
        centerline_horizontal = scribe_centerline_onto_centerline(timber_horizontal)
        marking_vertical = mark_distance_from_end_along_centerline(centerline_horizontal, timber_vertical)
        distA = marking_vertical.distance
        
        # Mark the vertical timber's centerline and measure onto horizontal timber
        centerline_vertical = scribe_centerline_onto_centerline(timber_vertical)
        marking_horizontal = mark_distance_from_end_along_centerline(centerline_vertical, timber_horizontal)
        distB = marking_horizontal.distance
        
        # Vertical timber: closest point should be at 18" from bottom
        assert distA == inches(18)
        # Horizontal timber: closest point should be at 12" from its bottom (where it intersects)
        assert distB == inches(12)
    
    def test_parallel_timbers(self):
        """Test with parallel timbers - should return zero distances."""
        # Two parallel timbers
        timberA = timber_from_directions(
            length=inches(36),
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberA"
        )
        
        timberB = timber_from_directions(
            length=inches(36),
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, inches(6), 0),  # 6" away parallel
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="timberB"
        )
        
        # expect this to raise ValueError when trying to find closest point on parallel lines
        with pytest.raises(ValueError):
            centerline_b = scribe_centerline_onto_centerline(timberB)
            marking_a = mark_distance_from_end_along_centerline(centerline_b, timberA)
            distA = marking_a.distance
        
    
    def test_with_different_reference_ends(self, symbolic_mode):
        """Test measuring from different reference ends (TOP vs BOTTOM)."""
        # Vertical timber
        timber_vertical = timber_from_directions(
            length=inches(36),
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="vertical"
        )
        
        # Horizontal timber at middle
        timber_horizontal = timber_from_directions(
            length=inches(24),
            size=create_v2(inches(4), inches(4)),
            bottom_position=create_v3(0, inches(12), inches(18)),
            length_direction=create_v3(0, -1, 0),
            width_direction=create_v3(1, 0, 0),
            ticket="horizontal"
        )
        
        # Measure from TOP of vertical timber and BOTTOM of horizontal
        # Mark the horizontal timber's centerline and measure onto vertical timber from TOP
        centerline_horizontal = scribe_centerline_onto_centerline(timber_horizontal)
        marking_vertical = mark_distance_from_end_along_centerline(centerline_horizontal, timber_vertical, TimberReferenceEnd.TOP)
        distA = marking_vertical.distance
        
        # Mark the vertical timber's centerline and measure onto horizontal timber from BOTTOM
        centerline_vertical = scribe_centerline_onto_centerline(timber_vertical)
        marking_horizontal = mark_distance_from_end_along_centerline(centerline_vertical, timber_horizontal, TimberReferenceEnd.BOTTOM)
        distB = marking_horizontal.distance
        
        # From TOP of vertical (36" high), intersection at 18" from bottom = 18" from top down
        assert distA == inches(-18)  # Negative because going down from top
        assert distB == inches(12)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
