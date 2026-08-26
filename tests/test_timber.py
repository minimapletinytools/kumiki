"""
Tests for Kumiki timber framing system
"""

import pytest
from kumiki.rule import Orientation
from kumiki.timber import _get_rough_size_and_offset
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    assert_is_valid_rotation_matrix,
    assert_vectors_perpendicular,
    assert_vectors_parallel,
    assert_vector_normalized,
    MockCutting
)


# ============================================================================
# Tests for timber.py - Types, Enums, Constants, and Core Classes
# ============================================================================

class TestVectorHelpers:
    """Test vector helper functions."""
    
    def test_create_v2(self):
        """Test 2D vector creation."""
        v = create_v2(scalar(3, 2), scalar(5, 2))  # 1.5, 2.5 as exact rationals
        assert v.shape == (2, 1)
        assert v[0] == scalar(3, 2)
        assert v[1] == scalar(5, 2)
    
    def test_create_v3(self):
        """Test 3D vector creation."""
        v = create_v3(1, 2, 3)  # Use exact integers
        assert v.shape == (3, 1)
        assert v[0] == 1
        assert v[1] == 2
        assert v[2] == 3
    
    def test_normalize_vector(self):
        """Test vector normalization."""
        v = create_v3(3, 4, 0)  # Use integers for exact computation
        normalized = safe_normalize_vector(v)
        
        # Should have magnitude 1
        magnitude = safe_magnitude(normalized)
        assert magnitude == 1
        
        # Should preserve direction ratios exactly
        assert normalized[0] == scalar(3, 5)  # 3/5
        assert normalized[1] == scalar(4, 5)  # 4/5
        assert normalized[2] == 0
    
    def test_normalize_zero_vector(self):
        """Test normalization of zero vector."""
        v = create_v3(scalar(0), scalar(0), scalar(0))  # Use exact integers
        normalized = safe_normalize_vector(v)
        assert normalized == v  # Should return original zero vector
    
    def test_cross_product(self):
        """Test cross product calculation."""
        v1 = create_v3(1, 0, 0)  # Use exact integers
        v2 = create_v3(scalar(0), scalar(1), scalar(0))  # Use exact integers
        cross = cross_product(v1, v2)
        
        expected = create_v3(scalar(0), scalar(0), scalar(1))  # Use exact integers
        assert cross[0] == 0
        assert cross[1] == 0
        assert cross[2] == 1
    
    def test_vector_magnitude(self):
        """Test vector magnitude calculation."""
        v = create_v3(3, 4, 0)  # Use integers for exact computation
        magnitude = safe_magnitude(v)
        assert magnitude == 5


class TestTimberEnumConversions:
    """Test timber enum type conversions."""
    
    def test_timber_feature_to_face(self):
        """Test TimberFeature to TimberFace conversion."""
        # Note: TimberFeature face values (1-6) map directly to TimberFace values
        assert TimberFeature.TOP_FACE.face() == TimberFace.TOP
        assert TimberFeature.BOTTOM_FACE.face() == TimberFace.BOTTOM
        assert TimberFeature.RIGHT_FACE.face() == TimberFace.RIGHT
        assert TimberFeature.FRONT_FACE.face() == TimberFace.FRONT
        assert TimberFeature.LEFT_FACE.face() == TimberFace.LEFT
        assert TimberFeature.BACK_FACE.face() == TimberFace.BACK
    
    def test_timber_long_face_to_feature(self):
        """Test TimberLongFace to TimberFeature conversion."""
        assert TimberLongFace.RIGHT.to == TimberFeature.RIGHT_FACE
        assert TimberLongFace.FRONT.to == TimberFeature.FRONT_FACE
        assert TimberLongFace.LEFT.to == TimberFeature.LEFT_FACE
        assert TimberLongFace.BACK.to == TimberFeature.BACK_FACE
    
    def test_timber_feature_to_long_face(self):
        """Test TimberFeature to TimberLongFace conversion."""
        assert TimberFeature.RIGHT_FACE.long_face() == TimberLongFace.RIGHT
        assert TimberFeature.FRONT_FACE.long_face() == TimberLongFace.FRONT
        assert TimberFeature.LEFT_FACE.long_face() == TimberLongFace.LEFT
        assert TimberFeature.BACK_FACE.long_face() == TimberLongFace.BACK
    
    def test_timber_reference_end_to_feature(self):
        """Test TimberEnd to TimberFeature conversion."""
        assert TimberEnd.TOP.to == TimberFeature.TOP_FACE
        assert TimberEnd.BOTTOM.to == TimberFeature.BOTTOM_FACE
    
    def test_timber_feature_to_end(self):
        """Test TimberFeature to TimberEnd conversion."""
        assert TimberFeature.TOP_FACE.end() == TimberEnd.TOP
        assert TimberFeature.BOTTOM_FACE.end() == TimberEnd.BOTTOM
    
    def test_timber_long_edge_to_feature(self):
        """Test TimberLongEdge to TimberFeature conversion."""
        assert TimberLongEdge.RIGHT_FRONT.to == TimberFeature.RIGHT_FRONT_EDGE
        assert TimberLongEdge.FRONT_LEFT.to == TimberFeature.FRONT_LEFT_EDGE
        assert TimberLongEdge.LEFT_BACK.to == TimberFeature.LEFT_BACK_EDGE
        assert TimberLongEdge.BACK_RIGHT.to == TimberFeature.BACK_RIGHT_EDGE
    
    def test_timber_feature_to_long_edge(self):
        """Test TimberFeature to TimberLongEdge conversion."""
        assert TimberFeature.RIGHT_FRONT_EDGE.long_edge() == TimberLongEdge.RIGHT_FRONT
        assert TimberFeature.FRONT_LEFT_EDGE.long_edge() == TimberLongEdge.FRONT_LEFT
        assert TimberFeature.LEFT_BACK_EDGE.long_edge() == TimberLongEdge.LEFT_BACK
        assert TimberFeature.BACK_RIGHT_EDGE.long_edge() == TimberLongEdge.BACK_RIGHT
    
    def test_timber_edge_to_feature(self):
        """Test TimberEdge to TimberFeature conversion."""
        assert TimberCenterline.CENTERLINE.to == TimberFeature.CENTERLINE
        # Long edges
        assert TimberEdge.RIGHT_FRONT.to == TimberFeature.RIGHT_FRONT_EDGE
        assert TimberEdge.FRONT_LEFT.to == TimberFeature.FRONT_LEFT_EDGE
        assert TimberEdge.LEFT_BACK.to == TimberFeature.LEFT_BACK_EDGE
        assert TimberEdge.BACK_RIGHT.to == TimberFeature.BACK_RIGHT_EDGE
        # Short edges - bottom
        assert TimberEdge.BOTTOM_RIGHT.to == TimberFeature.BOTTOM_RIGHT_EDGE
        assert TimberEdge.BOTTOM_FRONT.to == TimberFeature.BOTTOM_FRONT_EDGE
        assert TimberEdge.BOTTOM_LEFT.to == TimberFeature.BOTTOM_LEFT_EDGE
        assert TimberEdge.BOTTOM_BACK.to == TimberFeature.BOTTOM_BACK_EDGE
        # Short edges - top
        assert TimberEdge.TOP_RIGHT.to == TimberFeature.TOP_RIGHT_EDGE
        assert TimberEdge.TOP_FRONT.to == TimberFeature.TOP_FRONT_EDGE
        assert TimberEdge.TOP_LEFT.to == TimberFeature.TOP_LEFT_EDGE
        assert TimberEdge.TOP_BACK.to == TimberFeature.TOP_BACK_EDGE
    
    def test_timber_feature_to_edge(self):
        """Test TimberFeature to TimberEdge conversion."""
        assert TimberFeature.CENTERLINE.centerline() == TimberCenterline.CENTERLINE
        # Long edges
        assert TimberFeature.RIGHT_FRONT_EDGE.edge() == TimberEdge.RIGHT_FRONT
        assert TimberFeature.FRONT_LEFT_EDGE.edge() == TimberEdge.FRONT_LEFT
        assert TimberFeature.LEFT_BACK_EDGE.edge() == TimberEdge.LEFT_BACK
        assert TimberFeature.BACK_RIGHT_EDGE.edge() == TimberEdge.BACK_RIGHT
        # Short edges - bottom
        assert TimberFeature.BOTTOM_RIGHT_EDGE.edge() == TimberEdge.BOTTOM_RIGHT
        assert TimberFeature.BOTTOM_FRONT_EDGE.edge() == TimberEdge.BOTTOM_FRONT
        assert TimberFeature.BOTTOM_LEFT_EDGE.edge() == TimberEdge.BOTTOM_LEFT
        assert TimberFeature.BOTTOM_BACK_EDGE.edge() == TimberEdge.BOTTOM_BACK
        # Short edges - top
        assert TimberFeature.TOP_RIGHT_EDGE.edge() == TimberEdge.TOP_RIGHT
        assert TimberFeature.TOP_FRONT_EDGE.edge() == TimberEdge.TOP_FRONT
        assert TimberFeature.TOP_LEFT_EDGE.edge() == TimberEdge.TOP_LEFT
        assert TimberFeature.TOP_BACK_EDGE.edge() == TimberEdge.TOP_BACK
    
    def test_timber_feature_face_conversion_invalid(self):
        """Test that converting non-face features to face raises error."""
        with pytest.raises(ValueError, match="Cannot convert.*to TimberFace"):
            TimberFeature.CENTERLINE.face()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberFace"):
            TimberFeature.RIGHT_FRONT_EDGE.face()
    
    def test_timber_feature_long_face_conversion_invalid(self):
        """Test that converting non-long-face features to long face raises error."""
        with pytest.raises(ValueError, match="Cannot convert.*to TimberLongFace"):
            TimberFeature.TOP_FACE.long_face()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberLongFace"):
            TimberFeature.BOTTOM_FACE.long_face()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberLongFace"):
            TimberFeature.CENTERLINE.long_face()
    
    def test_timber_feature_end_conversion_invalid(self):
        """Test that converting non-end features to end raises error."""
        with pytest.raises(ValueError, match="Cannot convert.*to TimberEnd"):
            TimberFeature.RIGHT_FACE.end()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberEnd"):
            TimberFeature.CENTERLINE.end()
    
    def test_timber_feature_edge_conversion_invalid(self):
        """Test that converting non-edge features to edge raises error."""
        with pytest.raises(ValueError, match="Cannot convert.*to TimberEdge"):
            TimberFeature.TOP_FACE.edge()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberEdge"):
            TimberFeature.RIGHT_FACE.edge()
    
    def test_timber_feature_long_edge_conversion_invalid(self):
        """Test that converting non-long-edge features to long edge raises error."""
        with pytest.raises(ValueError, match="Cannot convert.*to TimberLongEdge"):
            TimberFeature.TOP_FACE.long_edge()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberLongEdge"):
            TimberFeature.CENTERLINE.long_edge()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberLongEdge"):
            TimberFeature.BOTTOM_RIGHT_EDGE.long_edge()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberLongEdge"):
            TimberFeature.TOP_BACK_EDGE.long_edge()

    def test_timber_short_edge_to_feature(self):
        """Test TimberShortEdge to TimberFeature conversion."""
        assert TimberShortEdge.BOTTOM_RIGHT.to == TimberFeature.BOTTOM_RIGHT_EDGE
        assert TimberShortEdge.BOTTOM_FRONT.to == TimberFeature.BOTTOM_FRONT_EDGE
        assert TimberShortEdge.BOTTOM_LEFT.to == TimberFeature.BOTTOM_LEFT_EDGE
        assert TimberShortEdge.BOTTOM_BACK.to == TimberFeature.BOTTOM_BACK_EDGE
        assert TimberShortEdge.TOP_RIGHT.to == TimberFeature.TOP_RIGHT_EDGE
        assert TimberShortEdge.TOP_FRONT.to == TimberFeature.TOP_FRONT_EDGE
        assert TimberShortEdge.TOP_LEFT.to == TimberFeature.TOP_LEFT_EDGE
        assert TimberShortEdge.TOP_BACK.to == TimberFeature.TOP_BACK_EDGE

    def test_timber_feature_to_short_edge(self):
        """Test TimberFeature to TimberShortEdge conversion."""
        assert TimberFeature.BOTTOM_RIGHT_EDGE.short_edge() == TimberShortEdge.BOTTOM_RIGHT
        assert TimberFeature.BOTTOM_FRONT_EDGE.short_edge() == TimberShortEdge.BOTTOM_FRONT
        assert TimberFeature.BOTTOM_LEFT_EDGE.short_edge() == TimberShortEdge.BOTTOM_LEFT
        assert TimberFeature.BOTTOM_BACK_EDGE.short_edge() == TimberShortEdge.BOTTOM_BACK
        assert TimberFeature.TOP_RIGHT_EDGE.short_edge() == TimberShortEdge.TOP_RIGHT
        assert TimberFeature.TOP_FRONT_EDGE.short_edge() == TimberShortEdge.TOP_FRONT
        assert TimberFeature.TOP_LEFT_EDGE.short_edge() == TimberShortEdge.TOP_LEFT
        assert TimberFeature.TOP_BACK_EDGE.short_edge() == TimberShortEdge.TOP_BACK

    def test_timber_edge_to_short_edge(self):
        """Test TimberEdge to TimberShortEdge and TimberLongEdge conversion."""
        assert TimberEdge.BOTTOM_RIGHT.short_edge() == TimberShortEdge.BOTTOM_RIGHT
        assert TimberEdge.TOP_FRONT.short_edge() == TimberShortEdge.TOP_FRONT
        assert TimberEdge.RIGHT_FRONT.long_edge() == TimberLongEdge.RIGHT_FRONT

    def test_timber_feature_short_edge_conversion_invalid(self):
        """Test that converting non-short-edge features to short edge raises error."""
        with pytest.raises(ValueError, match="Cannot convert.*to TimberShortEdge"):
            TimberFeature.TOP_FACE.short_edge()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberShortEdge"):
            TimberFeature.CENTERLINE.short_edge()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberShortEdge"):
            TimberFeature.RIGHT_FRONT_EDGE.short_edge()



class TestTimber:
    """Test Timber class."""
    
    def test_timber_creation(self):
        """Test basic timber creation."""
        length = 3  # Use exact integer
        size = create_v2(scalar(1, 10), scalar(1, 10))  # 0.1 as exact rational
        position = create_v3(scalar(0), scalar(0), scalar(0))  # Use exact integers
        length_dir = create_v3(scalar(0), scalar(0), scalar(1))  # Use exact integers
        width_dir = create_v3(1, 0, 0)   # Use exact integers
        
        timber = create_timber(length, size, position, length_dir, width_dir)
        
        assert timber.length == 3
        assert timber.size.shape == (2, 1)
        assert timber.get_bottom_position_global().shape == (3, 1)
        assert isinstance(timber.orientation, Orientation)
    
    def test_timber_orientation_computation(self):
        """Test that timber orientation is computed correctly."""
        # Create vertical timber facing east
        timber = create_standard_vertical_timber(height=2, size=(scalar(1, 10), scalar(1, 10)), position=(0, 0, 0))
        
        # Check that orientation matrix is reasonable
        matrix = timber.orientation.matrix
        assert matrix.shape == (3, 3)
        
        # Check that it's a valid rotation matrix
        assert_is_valid_rotation_matrix(matrix)
    
    def test_get_transform_matrix(self):
        """Test 4x4 transformation matrix generation."""
        timber = create_standard_vertical_timber(height=1, size=(scalar(1, 10), scalar(1, 10)), position=(1, 2, 3))
        
        transform = timber.get_transform_matrix()
        assert transform.shape == (4, 4)
        
        # Check translation part (exact comparison since we used integers)
        assert transform[0, 3] == 1
        assert transform[1, 3] == 2
        assert transform[2, 3] == 3
        assert transform[3, 3] == 1
    
    def test_orientation_computed_from_directions(self):
        """Test that orientation is correctly computed from input face and length directions."""
        # Test with standard vertical timber facing east
        input_length_dir = create_v3(scalar(0), scalar(0), scalar(1))  # Up - exact integers
        input_width_dir = create_v3(1, 0, 0)    # East - exact integers
        
        timber = create_timber(
            length=2,  # Use exact integer
            size=create_v2(scalar(1, 10), scalar(1, 10)),  # 0.1 as exact rational
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),  # Use exact integers
            length_direction=input_length_dir,
            width_direction=input_width_dir
        )
        
        # Verify that the property getters return the correct normalized directions
        length_dir = timber.get_length_direction_global()
        width_dir = timber.get_width_direction_global()
        height_dir = timber.get_height_direction_global()
        
        # Check that returned directions match input exactly (exact integers now)
        assert length_dir[0] == 0
        assert length_dir[1] == 0
        assert length_dir[2] == 1  # Exact integer from input
        
        assert width_dir[0] == 1    # Exact integer from input
        assert width_dir[1] == 0
        assert width_dir[2] == 0
        
        # Height direction should be cross product of length x face = Z x X = Y
        assert height_dir[0] == 0
        assert height_dir[1] == 1  # Exact integer from calculation
        assert height_dir[2] == 0
    
    def test_orientation_with_horizontal_timber(self):
        """Test orientation computation with a horizontal timber."""
        # Horizontal timber running north, facing up
        input_length_dir = create_v3(scalar(0), scalar(1), scalar(0))  # North - exact integers
        input_width_dir = create_v3(scalar(0), scalar(0), scalar(1))    # Up - exact integers
        
        timber = create_timber(
            length=3,  # Use exact integer
            size=create_v2(scalar(1, 10), scalar(1, 10)),  # 0.1 as exact rational
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),  # Use exact integers
            length_direction=input_length_dir,
            width_direction=input_width_dir
        )
        
        length_dir = timber.get_length_direction_global()
        width_dir = timber.get_width_direction_global()
        height_dir = timber.get_height_direction_global()
        
        # Check length direction (north) - exact integers now
        assert length_dir[0] == 0
        assert length_dir[1] == 1
        assert length_dir[2] == 0
        
        # Check face direction (up) - exact integers now
        assert width_dir[0] == 0
        assert width_dir[1] == 0
        assert width_dir[2] == 1
        
        # Height direction should be Y x Z = +X (east) - exact integers now
        assert height_dir[0] == 1
        assert height_dir[1] == 0
        assert height_dir[2] == 0
    
    def test_orientation_directions_are_orthonormal(self):
        """Test that the computed direction vectors form an orthonormal basis."""
        timber = create_timber(
            length=scalar(1),
            size=create_v2(scalar("0.1"), scalar("0.1")),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(1), scalar(0)),  # Non-axis-aligned
            width_direction=create_v3(scalar(0), scalar(0), scalar(1))     # Up
        )
        
        length_dir = timber.get_length_direction_global()
        width_dir = timber.get_width_direction_global()
        height_dir = timber.get_height_direction_global()
        
        # Check that each vector has unit length
        assert_vector_normalized(length_dir)
        assert_vector_normalized(width_dir)
        assert_vector_normalized(height_dir)
        
        # Check that vectors are orthogonal
        assert_vectors_perpendicular(length_dir, width_dir)
        assert_vectors_perpendicular(length_dir, height_dir)
        assert_vectors_perpendicular(width_dir, height_dir)
    
    def test_orientation_handles_non_normalized_inputs(self):
        """Test that orientation computation works with non-normalized input vectors."""
        # Use vectors that aren't unit length
        input_length_dir = create_v3(scalar(0), scalar(0), scalar(5))  # Up, but length 5
        input_width_dir = create_v3(scalar(3), scalar(0), scalar(0))    # East, but length 3
        
        timber = create_timber(
            length=scalar(1),
            size=create_v2(scalar("0.1"), scalar("0.1")),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length_direction=input_length_dir,
            width_direction=input_width_dir
        )
        
        # Despite non-normalized inputs, the output should be normalized
        length_dir = timber.get_length_direction_global()
        width_dir = timber.get_width_direction_global()
        
        # Check that directions are normalized (can be scalar(1) or scalar(1))
        assert length_dir[0] == 0
        assert length_dir[1] == 0
        assert length_dir[2] == 1
        
        assert width_dir[0] == 1
        assert width_dir[1] == 0
        assert width_dir[2] == 0
    
    def test_get_position_on_centerline_from_bottom_global(self):
        """Test the get_centerline_position_from_bottom method."""
        timber = create_timber(
            length=scalar(5),
            size=create_v2(scalar("0.2"), scalar("0.3")),
            bottom_position=create_v3(scalar(1), scalar(2), scalar(3)),
            length_direction=create_v3(scalar(0), scalar(1), scalar(0)),  # North
            width_direction=create_v3(scalar(0), scalar(0), scalar(1))     # Up
        )
        
        # Test at bottom position (position = 0)
        pos_at_bottom = locate_position_on_centerline_from_bottom(timber, scalar(0)).position
        assert pos_at_bottom[0] == 1
        assert pos_at_bottom[1] == 2
        assert pos_at_bottom[2] == 3
        
        # Test at midpoint (position = 2.5)
        pos_at_middle = locate_position_on_centerline_from_bottom(timber, scalar("2.5")).position
        assert pos_at_middle[0] == 1
        assert pos_at_middle[1] == scalar("4.5")  # 2.0 + 2.5 * 1.0
        assert pos_at_middle[2] == 3
        
        # Test at top (position = 5.0)
        pos_at_top = locate_position_on_centerline_from_bottom(timber, scalar(5)).position
        assert pos_at_top[0] == 1
        assert pos_at_top[1] == 7  # 2.0 + 5.0 * 1.0
        assert pos_at_top[2] == 3
        
        # Test with negative position (beyond bottom)
        pos_neg = locate_position_on_centerline_from_bottom(timber, -scalar(1)).position
        assert pos_neg[0] == 1
        assert pos_neg[1] == 1  # 2.0 + (-1.0) * 1.0
        assert pos_neg[2] == 3
    
    def test_get_position_on_centerline_from_bottom_global(self):
        """Test get_centerline_position_from_bottom method."""
        timber = create_timber(
            length=scalar(10),
            size=create_v2(scalar("0.2"), scalar("0.3")),
            bottom_position=create_v3(scalar(1), scalar(2), scalar(3)),
            length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Up
            width_direction=create_v3(scalar(1), scalar(0), scalar(0))     # East
        )
        
        # Test position at bottom (0)
        pos_bottom = locate_position_on_centerline_from_bottom(timber, scalar(0)).position
        assert pos_bottom[0] == 1
        assert pos_bottom[1] == 2
        assert pos_bottom[2] == 3
        
        # Test position at 3.0 from bottom
        pos_3 = locate_position_on_centerline_from_bottom(timber, scalar(3)).position
        assert pos_3[0] == 1
        assert pos_3[1] == 2
        assert pos_3[2] == 6  # 3.0 + 3.0
        
        # Test position at top (10)
        pos_top = locate_position_on_centerline_from_bottom(timber, scalar(10)).position
        assert pos_top[0] == 1
        assert pos_top[1] == 2
        assert pos_top[2] == 13  # 3.0 + 10.0
    
    def test_get_position_on_centerline_from_top_global(self):
        """Test get_centerline_position_from_top method."""
        timber = create_timber(
            length=scalar(10),
            size=create_v2(scalar("0.2"), scalar("0.3")),
            bottom_position=create_v3(scalar(1), scalar(2), scalar(3)),
            length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Up
            width_direction=create_v3(scalar(1), scalar(0), scalar(0))     # East
        )
        
        # Test position at top (0 from top = 10 from bottom)
        pos_top = locate_position_on_centerline_from_top(timber, scalar(0)).position
        assert pos_top[0] == 1
        assert pos_top[1] == 2
        assert pos_top[2] == 13  # 3.0 + 10.0
        
        # Test position at 3.0 from top (= 7.0 from bottom)
        pos_3 = locate_position_on_centerline_from_top(timber, scalar(3)).position
        assert pos_3[0] == 1
        assert pos_3[1] == 2
        assert pos_3[2] == 10  # 3.0 + 7.0
        
        # Test at bottom (10 from top = 0 from bottom)
        pos_bottom = locate_position_on_centerline_from_top(timber, scalar(10)).position
        assert pos_bottom[0] == 1
        assert pos_bottom[1] == 2
        assert pos_bottom[2] == 3  # 3.0 + 0.0

    def test_get_size_in_face_normal_axis(self):
        """Test get_size_in_face_normal_axis method returns correct dimensions for each face."""
        # Create a timber with distinct dimensions:
        # length = 10, width (size[0]) = 0.2, height (size[1]) = 0.3
        timber = create_timber(
            length=scalar(10),
            size=create_v2(scalar("0.2"), scalar("0.3")),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Up (Z-axis)
            width_direction=create_v3(scalar(1), scalar(0), scalar(0))     # East (X-axis)
        )
        
        # TOP and BOTTOM faces are perpendicular to the length direction (Z-axis)
        # So they should return the length
        assert timber.get_size_in_face_normal_axis(TimberFace.TOP) == scalar(10)
        assert timber.get_size_in_face_normal_axis(TimberFace.BOTTOM) == scalar(10)
        
        # RIGHT and LEFT faces are perpendicular to the width direction (X-axis)
        # So they should return the width (size[0])
        assert timber.get_size_in_face_normal_axis(TimberFace.RIGHT) == scalar("0.2")
        assert timber.get_size_in_face_normal_axis(TimberFace.LEFT) == scalar("0.2")
        
        # FRONT and BACK faces are perpendicular to the height direction (Y-axis)
        # So they should return the height (size[1])
        assert timber.get_size_in_face_normal_axis(TimberFace.FRONT) == scalar("0.3")
        assert timber.get_size_in_face_normal_axis(TimberFace.BACK) == scalar("0.3")


class TestEnumsAndDataStructures:
    """Test enums and data structures."""
    
    def test_timber_location_type_enum(self):
        """Test FootprintLocation enum."""
        assert FootprintLocation.INSIDE.value == 1
        assert FootprintLocation.CENTER.value == 2
        assert FootprintLocation.OUTSIDE.value == 3
    
    def test_timber_face_enum(self):
        """Test TimberFace enum."""
        assert TimberFace.TOP.value == 1
        assert TimberFace.BOTTOM.value == 2
        assert TimberFace.RIGHT.value == 3
        assert TimberFace.FRONT.value == 4
        assert TimberFace.LEFT.value == 5
        assert TimberFace.BACK.value == 6

    def test_timber_face_is_perpendicular(self):
        """Test TimberFace.is_perpendicular() method."""
        # Test X-axis faces perpendicular to Y-axis faces
        assert TimberFace.RIGHT.is_perpendicular(TimberFace.FRONT)
        assert TimberFace.RIGHT.is_perpendicular(TimberFace.BACK)
        assert TimberFace.LEFT.is_perpendicular(TimberFace.FRONT)
        assert TimberFace.LEFT.is_perpendicular(TimberFace.BACK)
        assert TimberFace.FRONT.is_perpendicular(TimberFace.RIGHT)
        assert TimberFace.FRONT.is_perpendicular(TimberFace.LEFT)
        assert TimberFace.BACK.is_perpendicular(TimberFace.RIGHT)
        assert TimberFace.BACK.is_perpendicular(TimberFace.LEFT)
        
        # Test X-axis faces perpendicular to Z-axis faces
        assert TimberFace.RIGHT.is_perpendicular(TimberFace.TOP)
        assert TimberFace.RIGHT.is_perpendicular(TimberFace.BOTTOM)
        assert TimberFace.LEFT.is_perpendicular(TimberFace.TOP)
        assert TimberFace.LEFT.is_perpendicular(TimberFace.BOTTOM)
        assert TimberFace.TOP.is_perpendicular(TimberFace.RIGHT)
        assert TimberFace.TOP.is_perpendicular(TimberFace.LEFT)
        assert TimberFace.BOTTOM.is_perpendicular(TimberFace.RIGHT)
        assert TimberFace.BOTTOM.is_perpendicular(TimberFace.LEFT)
        
        # Test Y-axis faces perpendicular to Z-axis faces
        assert TimberFace.FRONT.is_perpendicular(TimberFace.TOP)
        assert TimberFace.FRONT.is_perpendicular(TimberFace.BOTTOM)
        assert TimberFace.BACK.is_perpendicular(TimberFace.TOP)
        assert TimberFace.BACK.is_perpendicular(TimberFace.BOTTOM)
        assert TimberFace.TOP.is_perpendicular(TimberFace.FRONT)
        assert TimberFace.TOP.is_perpendicular(TimberFace.BACK)
        assert TimberFace.BOTTOM.is_perpendicular(TimberFace.FRONT)
        assert TimberFace.BOTTOM.is_perpendicular(TimberFace.BACK)
        
        # Test non-perpendicular pairs (opposite faces on same axis)
        assert not TimberFace.RIGHT.is_perpendicular(TimberFace.LEFT)
        assert not TimberFace.LEFT.is_perpendicular(TimberFace.RIGHT)
        assert not TimberFace.FRONT.is_perpendicular(TimberFace.BACK)
        assert not TimberFace.BACK.is_perpendicular(TimberFace.FRONT)
        assert not TimberFace.TOP.is_perpendicular(TimberFace.BOTTOM)
        assert not TimberFace.BOTTOM.is_perpendicular(TimberFace.TOP)
        
        # Test same face (not perpendicular to itself)
        assert not TimberFace.RIGHT.is_perpendicular(TimberFace.RIGHT)
        assert not TimberFace.LEFT.is_perpendicular(TimberFace.LEFT)
        assert not TimberFace.FRONT.is_perpendicular(TimberFace.FRONT)
        assert not TimberFace.BACK.is_perpendicular(TimberFace.BACK)
        assert not TimberFace.TOP.is_perpendicular(TimberFace.TOP)
        assert not TimberFace.BOTTOM.is_perpendicular(TimberFace.BOTTOM)
    
    def test_timber_face_rotate_about(self):
        """Test TimberFace.rotate_about() method."""
        # Rotating about TOP's normal (+Z) axis, right-hand rule:
        # RIGHT -> FRONT -> LEFT -> BACK -> RIGHT
        assert TimberFace.RIGHT.rotate_about(TimberFace.TOP) == TimberFace.FRONT
        assert TimberFace.FRONT.rotate_about(TimberFace.TOP) == TimberFace.LEFT
        assert TimberFace.LEFT.rotate_about(TimberFace.TOP) == TimberFace.BACK
        assert TimberFace.BACK.rotate_about(TimberFace.TOP) == TimberFace.RIGHT

        # Rotating about BOTTOM's normal (-Z) is the reverse cycle
        assert TimberFace.RIGHT.rotate_about(TimberFace.BOTTOM) == TimberFace.BACK
        assert TimberFace.BACK.rotate_about(TimberFace.BOTTOM) == TimberFace.LEFT
        assert TimberFace.LEFT.rotate_about(TimberFace.BOTTOM) == TimberFace.FRONT
        assert TimberFace.FRONT.rotate_about(TimberFace.BOTTOM) == TimberFace.RIGHT

        # A face on the rotation axis is unaffected
        assert TimberFace.TOP.rotate_about(TimberFace.TOP) == TimberFace.TOP
        assert TimberFace.BOTTOM.rotate_about(TimberFace.TOP) == TimberFace.BOTTOM

        # Four quarter-turns about the same axis return to the start
        face = TimberFace.RIGHT
        for _ in range(4):
            face = face.rotate_about(TimberFace.FRONT)
        assert face == TimberFace.RIGHT

        # A rotated face is always perpendicular to the rotation axis
        # (unless it started on the axis, handled above)
        for axis in TimberFace:
            for face in TimberFace:
                if face == axis or face == axis.get_opposite_face():
                    continue
                assert face.rotate_about(axis).is_perpendicular(axis)

    def test_timber_reference_long_face_to_timber_face(self):
        """Test TimberLongFace.to.face() conversion method."""
        assert TimberLongFace.RIGHT.to.face() == TimberFace.RIGHT
        assert TimberLongFace.FRONT.to.face() == TimberFace.FRONT
        assert TimberLongFace.LEFT.to.face() == TimberFace.LEFT
        assert TimberLongFace.BACK.to.face() == TimberFace.BACK
    
    def test_timber_reference_long_face_is_perpendicular(self):
        """Test TimberLongFace.is_perpendicular() method."""
        # Test perpendicular pairs
        assert TimberLongFace.RIGHT.is_perpendicular(TimberLongFace.FRONT)
        assert TimberLongFace.RIGHT.is_perpendicular(TimberLongFace.BACK)
        assert TimberLongFace.LEFT.is_perpendicular(TimberLongFace.FRONT)
        assert TimberLongFace.LEFT.is_perpendicular(TimberLongFace.BACK)
        assert TimberLongFace.FRONT.is_perpendicular(TimberLongFace.RIGHT)
        assert TimberLongFace.FRONT.is_perpendicular(TimberLongFace.LEFT)
        assert TimberLongFace.BACK.is_perpendicular(TimberLongFace.RIGHT)
        assert TimberLongFace.BACK.is_perpendicular(TimberLongFace.LEFT)
        
        # Test non-perpendicular pairs (opposite faces)
        assert not TimberLongFace.RIGHT.is_perpendicular(TimberLongFace.LEFT)
        assert not TimberLongFace.LEFT.is_perpendicular(TimberLongFace.RIGHT)
        assert not TimberLongFace.FRONT.is_perpendicular(TimberLongFace.BACK)
        assert not TimberLongFace.BACK.is_perpendicular(TimberLongFace.FRONT)
        
        # Test same face (not perpendicular to itself)
        assert not TimberLongFace.RIGHT.is_perpendicular(TimberLongFace.RIGHT)
        assert not TimberLongFace.LEFT.is_perpendicular(TimberLongFace.LEFT)
        assert not TimberLongFace.FRONT.is_perpendicular(TimberLongFace.FRONT)
        assert not TimberLongFace.BACK.is_perpendicular(TimberLongFace.BACK)
    
    def test_timber_reference_long_face_rotate_right(self):
        """Test TimberLongFace.rotate_right() method."""
        # Test single rotation clockwise (when viewed from above/+Z)
        # RIGHT (3) -> FRONT (4) -> LEFT (5) -> BACK (6) -> RIGHT (3)
        assert TimberLongFace.RIGHT.rotate_right() == TimberLongFace.FRONT
        assert TimberLongFace.FRONT.rotate_right() == TimberLongFace.LEFT
        assert TimberLongFace.LEFT.rotate_right() == TimberLongFace.BACK
        assert TimberLongFace.BACK.rotate_right() == TimberLongFace.RIGHT
        
        # Test chaining: rotating right 4 times should return to original
        assert TimberLongFace.RIGHT.rotate_right().rotate_right().rotate_right().rotate_right() == TimberLongFace.RIGHT
        assert TimberLongFace.FRONT.rotate_right().rotate_right().rotate_right().rotate_right() == TimberLongFace.FRONT
        assert TimberLongFace.LEFT.rotate_right().rotate_right().rotate_right().rotate_right() == TimberLongFace.LEFT
        assert TimberLongFace.BACK.rotate_right().rotate_right().rotate_right().rotate_right() == TimberLongFace.BACK
        
        # Test rotating right twice (180 degrees) gives opposite face
        assert TimberLongFace.RIGHT.rotate_right().rotate_right() == TimberLongFace.LEFT
        assert TimberLongFace.LEFT.rotate_right().rotate_right() == TimberLongFace.RIGHT
        assert TimberLongFace.FRONT.rotate_right().rotate_right() == TimberLongFace.BACK
        assert TimberLongFace.BACK.rotate_right().rotate_right() == TimberLongFace.FRONT
    
    def test_timber_reference_long_face_rotate_left(self):
        """Test TimberLongFace.rotate_left() method."""
        # Test single rotation counter-clockwise (when viewed from above/+Z)
        # RIGHT (3) -> BACK (6) -> LEFT (5) -> FRONT (4) -> RIGHT (3)
        assert TimberLongFace.RIGHT.rotate_left() == TimberLongFace.BACK
        assert TimberLongFace.BACK.rotate_left() == TimberLongFace.LEFT
        assert TimberLongFace.LEFT.rotate_left() == TimberLongFace.FRONT
        assert TimberLongFace.FRONT.rotate_left() == TimberLongFace.RIGHT
        
        # Test chaining: rotating left 4 times should return to original
        assert TimberLongFace.RIGHT.rotate_left().rotate_left().rotate_left().rotate_left() == TimberLongFace.RIGHT
        assert TimberLongFace.FRONT.rotate_left().rotate_left().rotate_left().rotate_left() == TimberLongFace.FRONT
        assert TimberLongFace.LEFT.rotate_left().rotate_left().rotate_left().rotate_left() == TimberLongFace.LEFT
        assert TimberLongFace.BACK.rotate_left().rotate_left().rotate_left().rotate_left() == TimberLongFace.BACK
        
        # Test rotating left twice (180 degrees) gives opposite face
        assert TimberLongFace.RIGHT.rotate_left().rotate_left() == TimberLongFace.LEFT
        assert TimberLongFace.LEFT.rotate_left().rotate_left() == TimberLongFace.RIGHT
        assert TimberLongFace.FRONT.rotate_left().rotate_left() == TimberLongFace.BACK
        assert TimberLongFace.BACK.rotate_left().rotate_left() == TimberLongFace.FRONT
    
    def test_timber_reference_long_face_rotate_right_left_inverse(self):
        """Test that rotate_right() and rotate_left() are inverses of each other."""
        # Test that rotating right then left returns to original
        assert TimberLongFace.RIGHT.rotate_right().rotate_left() == TimberLongFace.RIGHT
        assert TimberLongFace.FRONT.rotate_right().rotate_left() == TimberLongFace.FRONT
        assert TimberLongFace.LEFT.rotate_right().rotate_left() == TimberLongFace.LEFT
        assert TimberLongFace.BACK.rotate_right().rotate_left() == TimberLongFace.BACK
        
        # Test that rotating left then right returns to original
        assert TimberLongFace.RIGHT.rotate_left().rotate_right() == TimberLongFace.RIGHT
        assert TimberLongFace.FRONT.rotate_left().rotate_right() == TimberLongFace.FRONT
        assert TimberLongFace.LEFT.rotate_left().rotate_right() == TimberLongFace.LEFT
        assert TimberLongFace.BACK.rotate_left().rotate_right() == TimberLongFace.BACK
        
        # Test multiple rotations in opposite directions cancel out
        assert TimberLongFace.RIGHT.rotate_right().rotate_right().rotate_left().rotate_left() == TimberLongFace.RIGHT
        assert TimberLongFace.FRONT.rotate_left().rotate_left().rotate_left().rotate_right().rotate_right().rotate_right() == TimberLongFace.FRONT
    
    def test_timber_reference_long_face_rotate_perpendicularity(self):
        """Test that rotating by 90 degrees produces perpendicular faces."""
        # Single rotation should produce perpendicular face
        assert TimberLongFace.RIGHT.is_perpendicular(TimberLongFace.RIGHT.rotate_right())
        assert TimberLongFace.RIGHT.is_perpendicular(TimberLongFace.RIGHT.rotate_left())
        assert TimberLongFace.FRONT.is_perpendicular(TimberLongFace.FRONT.rotate_right())
        assert TimberLongFace.FRONT.is_perpendicular(TimberLongFace.FRONT.rotate_left())
        assert TimberLongFace.LEFT.is_perpendicular(TimberLongFace.LEFT.rotate_right())
        assert TimberLongFace.LEFT.is_perpendicular(TimberLongFace.LEFT.rotate_left())
        assert TimberLongFace.BACK.is_perpendicular(TimberLongFace.BACK.rotate_right())
        assert TimberLongFace.BACK.is_perpendicular(TimberLongFace.BACK.rotate_left())



class TestGetCornerPositionGlobal:
    """Test PerfectTimberWithin.get_corner_position_global."""

    def test_bot_right_front_vertical_timber(self):
        """BOT_RIGHT_FRONT corner of a 10x20x100 vertical timber at origin = (5, 10, 0)."""
        timber = create_timber(
            length=scalar(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        pos = timber.get_corner_position_global(TimberCorner.BOT_RIGHT_FRONT)
        assert pos[0] == scalar(5)
        assert pos[1] == scalar(10)
        assert pos[2] == scalar(0)


class TestCutTimber:
    """Test CutTimber CSG operations."""
    
    def test_extended_timber_without_cuts_finite(self):
        """Test _extended_timber_without_cuts_csg for a timber with no cuts (finite)."""
        # Create a simple timber
        length = scalar(100)
        size = Matrix([scalar(4), scalar(6)])
        bottom_position = Matrix([scalar(0), scalar(0), scalar(10)])
        length_direction = Matrix([scalar(0), scalar(0), scalar(1)])
        width_direction = Matrix([scalar(1), scalar(0), scalar(0)])
        
        timber = create_timber(length, size, bottom_position, length_direction, width_direction, ticket='test_timber')
        cut_timber = CutTimber(timber)
        
        # Get the CSG
        csg = cut_timber._extended_timber_without_cuts_csg_local()
        
        # Should be a finite prism
        from kumiki.cutcsg import RectangularPrism
        assert isinstance(csg, RectangularPrism)
        
        # In LOCAL coordinates (relative to bottom_position):
        # Start should be at 0 (local bottom)
        assert csg.start_distance == 0
        
        # End should be at timber's length (local top)
        assert csg.end_distance == 100
        
        # Size should match timber
        assert csg.size == size
        # In LOCAL coordinates, the prism is always axis-aligned (identity orientation)
        # The timber's orientation transforms from local to global coordinates
        from kumiki.rule import Orientation
        assert safe_zero_test((csg.transform.orientation.matrix - Orientation.identity().matrix).norm())
    
    def test_extended_timber_without_cuts_positioned(self):
        """Test that CSG works correctly for timber at different position."""
        # Create a timber at a different position
        length = scalar(50)
        size = Matrix([scalar(3), scalar(4)])
        bottom_position = Matrix([scalar(5), scalar(10), scalar(20)])
        length_direction = Matrix([scalar(0), scalar(0), scalar(1)])
        width_direction = Matrix([scalar(1), scalar(0), scalar(0)])
        
        timber = create_timber(length, size, bottom_position, length_direction, width_direction)
        cut_timber = CutTimber(timber)
        
        csg = cut_timber._extended_timber_without_cuts_csg_local()
        assert isinstance(csg, RectangularPrism), "Expected csg to be a RectangularPrism"
        
        # In LOCAL coordinates (relative to bottom_position):
        # Start distance is 0 (at bottom)
        assert csg.start_distance == 0
        
        # End distance is the timber's length
        assert csg.end_distance == 50
    
    def test_extended_timber_horizontal(self):
        """Test CSG for a horizontal timber in local coordinates."""
        length = scalar(80)
        size = Matrix([scalar(5), scalar(5)])
        bottom_position = Matrix([scalar(10), scalar(20), scalar(5)])
        length_direction = Matrix([scalar(1), scalar(0), scalar(0)])  # Along X
        width_direction = Matrix([scalar(0), scalar(1), scalar(0)])
        
        timber = create_timber(length, size, bottom_position, length_direction, width_direction)
        cut_timber = CutTimber(timber)
        
        csg = cut_timber._extended_timber_without_cuts_csg_local()
        assert isinstance(csg, RectangularPrism), "Expected csg to be a RectangularPrism"
        
        # In LOCAL coordinates (relative to bottom_position):
        # Start distance is 0
        assert csg.start_distance == 0
        
        # End distance is the timber's length
        assert csg.end_distance == 80
        
        # the csg is in local coordinates, so it should have identity orientation
        from kumiki.rule import Orientation
        assert csg.transform.orientation.matrix.equals(Orientation.identity().matrix)
    
    def test_render_timber_with_cuts_no_cuts(self):
        """Test render_timber_with_cuts_csg_local with no cuts."""
        length = scalar(100)
        size = Matrix([scalar(4), scalar(6)])
        bottom_position = Matrix([scalar(0), scalar(0), scalar(0)])
        length_direction = Matrix([scalar(0), scalar(0), scalar(1)])
        width_direction = Matrix([scalar(1), scalar(0), scalar(0)])
        
        timber = create_timber(length, size, bottom_position, length_direction, width_direction)
        cut_timber = CutTimber(timber, cuts=[])
        
        # Get the CSG with cuts applied (should be same as without cuts since there are none)
        csg = cut_timber.render_timber_with_cuts_csg_local()
        
        # Should be a RectangularPrism (since no cuts means no Difference operation)
        from kumiki.cutcsg import RectangularPrism
        assert isinstance(csg, RectangularPrism)
        assert csg.size == size
        assert csg.start_distance == 0
        assert csg.end_distance == length
    
    def test_render_timber_with_cuts_one_cut(self):
        """Test render_timber_with_cuts_csg_local with one cut."""
        length = scalar(100)
        size = Matrix([scalar(4), scalar(6)])
        bottom_position = Matrix([scalar(0), scalar(0), scalar(10)])
        length_direction = Matrix([scalar(0), scalar(0), scalar(1)])
        width_direction = Matrix([scalar(1), scalar(0), scalar(0)])
        
        timber = create_timber(length, size, bottom_position, length_direction, width_direction)
        
        # Add a cut (a simple half-plane cut at z=50 in local coordinates)
        from kumiki.cutcsg import HalfSpace
        # Create a half plane that cuts perpendicular to the timber length
        # Normal pointing in +Z direction, offset at 50
        half_plane = HalfSpace(
            normal=Matrix([scalar(0), scalar(0), scalar(1)]),
            offset=scalar(50)
        )
        cut = Cutting(
            timber=timber,
            negative_csg=half_plane
        )
        
        cut_timber = CutTimber(timber, cuts=[cut])
        
        # Get the CSG with cuts applied
        csg = cut_timber.render_timber_with_cuts_csg_local()
        
        # Should be a Difference operation
        from kumiki.cutcsg import Difference
        assert isinstance(csg, Difference)
        assert isinstance(csg.base, RectangularPrism)
        assert len(csg.subtract) == 1
        # Each cutting contributes its own SolidUnion, holding what it removes.
        only_cut = csg.subtract[0]
        assert isinstance(only_cut, SolidUnion)
        assert isinstance(only_cut.children[0], HalfSpace)
    
    def test_render_timber_with_cuts_multiple_cuts(self):
        """Test render_timber_with_cuts_csg_local with multiple cuts."""
        length = scalar(100)
        size = Matrix([scalar(4), scalar(6)])
        bottom_position = Matrix([scalar(0), scalar(0), scalar(0)])
        length_direction = Matrix([scalar(0), scalar(0), scalar(1)])
        width_direction = Matrix([scalar(1), scalar(0), scalar(0)])
        
        timber = create_timber(length, size, bottom_position, length_direction, width_direction)
        
        # Add two cuts
        from kumiki.cutcsg import HalfSpace
        half_plane1 = HalfSpace(
            normal=Matrix([scalar(0), scalar(0), scalar(1)]),
            offset=scalar(25)
        )
        cut1 = Cutting(
            timber=timber,
            negative_csg=half_plane1
        )
        
        half_plane2 = HalfSpace(
            normal=Matrix([scalar(0), scalar(0), scalar(-1)]),
            offset=scalar(-75)
        )
        cut2 = Cutting(
            timber=timber,
            negative_csg=half_plane2
        )
        
        cut_timber = CutTimber(timber, cuts=[cut1, cut2])
        
        # Get the CSG with cuts applied
        csg = cut_timber.render_timber_with_cuts_csg_local()
        
        # Should be a Difference operation
        from kumiki.cutcsg import Difference
        assert isinstance(csg, Difference)
        assert isinstance(csg.base, RectangularPrism)
        assert len(csg.subtract) == 2
        # Each cutting contributes its own SolidUnion, holding what it removes.
        for sub in csg.subtract:
            assert isinstance(sub, SolidUnion)
            assert isinstance(sub.children[0], HalfSpace)
    
    def test_render_timber_with_cuts_with_end_cuts(self):
        """Test render_timber_with_cuts_csg_local with end cuts."""
        length = scalar(100)
        size = Matrix([scalar(4), scalar(6)])
        bottom_position = Matrix([scalar(0), scalar(0), scalar(0)])
        length_direction = Matrix([scalar(0), scalar(0), scalar(1)])
        width_direction = Matrix([scalar(1), scalar(0), scalar(0)])
        
        timber = create_timber(length, size, bottom_position, length_direction, width_direction)
        
        # Add an end cut at the top
        from kumiki.cutcsg import HalfSpace
        half_plane = HalfSpace(
            normal=Matrix([scalar(0), scalar(0), scalar(-1)]),
            offset=scalar(-50)
        )
        end_cut = Cutting(
            timber=timber,
            maybe_top_end_cut_distance_from_bottom=scalar(50),
            negative_csg=None
        )
        
        cut_timber = CutTimber(timber, cuts=[end_cut])
        
        # Get the CSG with cuts applied
        csg = cut_timber.render_timber_with_cuts_csg_local()
        
        # Should be a Difference operation
        from kumiki.cutcsg import Difference, RectangularPrism
        assert isinstance(csg, Difference)
        assert isinstance(csg.base, RectangularPrism)
        
        # Base prism should be semi-infinite at the top (end_distance = None)
        assert csg.base.start_distance == 0
        assert csg.base.end_distance is None
        
        # Should have one cut
        assert len(csg.subtract) == 1
        # Each cutting contributes its own SolidUnion, holding what it removes.
        only_cut = csg.subtract[0]
        assert isinstance(only_cut, SolidUnion)
        assert isinstance(only_cut.children[0], HalfSpace)


class TestCutTimberFromJoints:
    """Test CutTimber.from_joints."""

    def test_collects_cuttings_for_timber_across_joints(self):
        """Cuttings for `timber` from every joint are collected, in joint order."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber A"
        )
        cut1 = Cutting(timber=timber, maybe_bottom_end_cut_distance_from_bottom=scalar(5))
        cut2 = Cutting(timber=timber, maybe_top_end_cut_distance_from_bottom=scalar(90))
        joint1 = Joint(cuttings={"timberA": cut1}, ticket=JointTicket(joint_type="j1"), jointAccessories={})
        joint2 = Joint(cuttings={"timberA": cut2}, ticket=JointTicket(joint_type="j2"), jointAccessories={})

        cut_timber = CutTimber.from_joints(timber, [joint1, joint2])

        assert cut_timber.timber is timber
        assert cut_timber.cuts == [cut1, cut2]

    def test_ignores_cuttings_for_other_timbers(self):
        """Cuttings whose .timber is a different (even if structurally identical) timber are excluded."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber A"
        )
        other_timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber B"
        )
        cut_for_timber = Cutting(timber=timber, negative_csg=EmptyCSG())
        cut_for_other = Cutting(timber=other_timber, negative_csg=EmptyCSG())
        joint = Joint(
            cuttings={"timberA": cut_for_timber, "timberB": cut_for_other},
            ticket=JointTicket(joint_type="j"),
            jointAccessories={},
        )

        cut_timber = CutTimber.from_joints(timber, [joint])

        assert cut_timber.cuts == [cut_for_timber]

    def test_empty_when_no_joints_reference_timber(self):
        """A timber not referenced by any joint gets an empty (uncut) CutTimber."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Lonely Timber"
        )
        cut_timber = CutTimber.from_joints(timber, [])
        assert cut_timber.timber is timber
        assert cut_timber.cuts == []


class TestFrameFromJoints:
    """Test Frame.from_joints constructor."""
    
    def test_from_joints_simple(self):
        """Test creating a frame from a list of joints."""
        # Create two simple timbers
        timber1 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber 1"
        )
        
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(10), 0, 0),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber 2"
        )
        
        # Create cuts for each timber
        cut1 = Cutting(timber=timber1, negative_csg=EmptyCSG())
        cut2 = Cutting(timber=timber2, negative_csg=EmptyCSG())
        
        # Create a joint
        joint = Joint(
            cuttings={"timber1": cut1, "timber2": cut2},
            ticket=JointTicket(joint_type="test_simple_joint"),
            jointAccessories={}
        )
        
        # Create frame from joints
        frame = Frame.from_joints([joint], name="Test Frame")
        
        # Verify frame has 2 cut timbers
        assert len(frame.cut_timbers) == 2
        assert frame.name == "Test Frame"
        assert len(frame.accessories) == 0
        
        # Verify each timber appears once
        timber_names = [ct.timber.ticket.path for ct in frame.cut_timbers]
        assert "Timber 1" in timber_names
        assert "Timber 2" in timber_names
    
    def test_from_joints_merges_same_timber(self):
        """Test that cut timbers with the same underlying timber reference are merged."""
        # Create a single timber
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Shared Timber"
        )
        
        # Create different cuts for the same timber
        cut1 = Cutting(timber=timber, negative_csg=EmptyCSG())
        cut2 = Cutting(timber=timber, negative_csg=EmptyCSG())
        cut3 = Cutting(timber=timber, negative_csg=EmptyCSG())
        
        # Create joints that all reference the same timber
        joint1 = Joint(
            cuttings={"timber": cut1},
            ticket=JointTicket(joint_type="test_merge_shared_1"),
            jointAccessories={}
        )
        
        joint2 = Joint(
            cuttings={"timber": cut2},
            ticket=JointTicket(joint_type="test_merge_shared_2"),
            jointAccessories={}
        )

        joint3 = Joint(
            cuttings={"timber": cut3},
            ticket=JointTicket(joint_type="test_merge_shared_3"),
            jointAccessories={}
        )
        
        # Create frame from joints
        frame = Frame.from_joints([joint1, joint2, joint3])
        
        # Verify only one cut timber in the frame (merged)
        assert len(frame.cut_timbers) == 1
        
        # Verify all cuts are present
        merged_cut_timber = frame.cut_timbers[0]
        assert len(merged_cut_timber.cuts) == 3
        assert cut1 in merged_cut_timber.cuts
        assert cut2 in merged_cut_timber.cuts
        assert cut3 in merged_cut_timber.cuts
    
    def test_from_joints_collects_accessories(self):
        """Test that accessories from all joints are collected."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber"
        )
        
        # Create a peg accessory
        peg = Peg(
            transform=Transform(
                position=create_v3(0, 0, scalar(50)),
                orientation=Orientation.identity()
            ),
            size=scalar(1),
            shape=PegShape.ROUND,
            forward_length=scalar(10),
            stickout_length=scalar(2)
        )
        
        # Create a wedge accessory
        wedge = Wedge(
            transform=Transform(
                position=create_v3(0, 0, scalar(100)),
                orientation=Orientation.identity()
            ),
            base_width=scalar(2),
            tip_width=scalar(1),
            height=scalar(3),
            length=scalar(5)
        )
        
        # Create joints with accessories
        joint1 = Joint(
            cuttings={"timber": Cutting(timber=timber, negative_csg=EmptyCSG())},
            ticket=JointTicket(joint_type="test_accessories_peg"),
            jointAccessories={"peg": peg}
        )
        
        joint2 = Joint(
            cuttings={"timber": Cutting(timber=timber, negative_csg=EmptyCSG())},
            ticket=JointTicket(joint_type="test_accessories_wedge"),
            jointAccessories={"wedge": wedge}
        )
        
        # Create frame from joints
        frame = Frame.from_joints([joint1, joint2])
        
        # Verify accessories are collected
        assert len(frame.accessories) == 2
        assert peg in frame.accessories
        assert wedge in frame.accessories
    
    def test_from_joints_with_additional_unjointed_timbers(self):
        """Test adding additional unjointed timbers to the frame."""
        # Create a timber with a joint
        timber1 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Jointed Timber"
        )
        
        # Create an unjointed timber
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(10), 0, 0),
            length=scalar(50),
            size=create_v2(scalar(2), scalar(2)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Unjointed Timber"
        )
        
        # Create a joint with timber1
        joint = Joint(
            cuttings={"timber1": MockCutting(timber1, create_v3(scalar(0), scalar(0), scalar(0)))},  # type: ignore[arg-type]
            ticket=JointTicket(joint_type="test_with_unjointed"),
            jointAccessories={}
        )
        
        # Create frame with additional unjointed timber
        frame = Frame.from_joints([joint], additional_unjointed_timbers=[timber2])
        
        # Verify both timbers are in the frame
        assert len(frame.cut_timbers) == 2
        
        timber_names = [ct.timber.ticket.path for ct in frame.cut_timbers]
        assert "Jointed Timber" in timber_names
        assert "Unjointed Timber" in timber_names
        
        # Verify unjointed timber has no cuts
        unjointed_ct = [ct for ct in frame.cut_timbers if ct.timber.ticket.path == "Unjointed Timber"][0]
        assert len(unjointed_ct.cuts) == 0
    
    def test_from_joints_warns_on_different_timbers_same_name(self):
        """Test that a warning is issued when different timbers have the same name."""
        # Create two different timbers with the same name
        timber1 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"
        )
        
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(10), 0, 0),
            length=scalar(80),  # Different length
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"  # Same name
        )
        
        # Create joints
        joint1 = Joint(
            cuttings={"timber1": Cutting(timber=timber1, negative_csg=EmptyCSG())},
            ticket=JointTicket(joint_type="test_same_name_warn_1"),
            jointAccessories={}
        )
        
        joint2 = Joint(
            cuttings={"timber2": Cutting(timber=timber2, negative_csg=EmptyCSG())},
            ticket=JointTicket(joint_type="test_same_name_warn_2"),
            jointAccessories={}
        )
        
        # Create frame - should issue a warning
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            frame = Frame.from_joints([joint1, joint2])
            
            # Verify a warning was issued
            assert len(w) == 1
            assert "multiple timbers with the same name" in str(w[0].message).lower()
            assert "Post" in str(w[0].message)
    
    def test_from_joints_errors_on_duplicate_timber_data(self):
        """Test that an error is raised when same timber data exists with different references."""
        # Create two timbers with identical data
        timber1 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"
        )
        
        # Create an identical timber (same data, different object)
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"
        )
        
        # Verify they are different objects but equal data
        assert timber1 is not timber2
        assert timber1 == timber2
        
        # Create joints
        joint1 = Joint(
            cuttings={"timber1": Cutting(timber=timber1, negative_csg=EmptyCSG())},
            ticket=JointTicket(joint_type="test_dup_data_1"),
            jointAccessories={}
        )
        
        joint2 = Joint(
            cuttings={"timber2": Cutting(timber=timber2, negative_csg=EmptyCSG())},
            ticket=JointTicket(joint_type="test_dup_data_2"),
            jointAccessories={}
        )
        
        # Create frame - should raise an error
        with pytest.raises(ValueError) as exc_info:
            Frame.from_joints([joint1, joint2])
        
        assert "identical underlying timber data" in str(exc_info.value).lower()
        assert "Post" in str(exc_info.value)
    
    def test_from_joints_empty_list(self):
        """Test creating a frame from an empty list of joints."""
        frame = Frame.from_joints([], name="Empty Frame")
        
        assert len(frame.cut_timbers) == 0
        assert len(frame.accessories) == 0
        assert frame.name == "Empty Frame"


class TestFrameBoundingBox:
    """Test Frame bounding box calculations."""
    
    def test_single_timber_bounding_box_matches_timber_prism(self):
        """Test that a frame with a single timber has a bounding box matching the timber's prism."""
        # Create a simple vertical timber
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(10, 20, 5),
            length=scalar(96),  # 8 feet
            size=create_v2(scalar(4), scalar(4)),  # 4x4 inches
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="TestPost"
        )
        
        # Create a frame with just this timber
        cut_timber = CutTimber(timber, cuts=[])
        frame = Frame(cut_timbers=[cut_timber])
        
        # Get bounding box
        min_corner, max_corner = frame.get_bounding_box()
        
        # Expected bounds: timber goes from (10, 20, 5) to (10, 20, 5+96)
        # with cross section centered at (10, 20), spanning ±2 inches in X and Y
        expected_min = create_v3(
            10 - scalar(2),  # 10 - 4/2
            20 - scalar(2),  # 20 - 4/2
            5                   # bottom z
        )
        expected_max = create_v3(
            10 + scalar(2),  # 10 + 4/2
            20 + scalar(2),  # 20 + 4/2
            5 + 96             # top z
        )
        
        # Check each component
        assert min_corner[0] == expected_min[0], f"min_x: {min_corner[0]} != {expected_min[0]}"
        assert min_corner[1] == expected_min[1], f"min_y: {min_corner[1]} != {expected_min[1]}"
        assert min_corner[2] == expected_min[2], f"min_z: {min_corner[2]} != {expected_min[2]}"
        
        assert max_corner[0] == expected_max[0], f"max_x: {max_corner[0]} != {expected_max[0]}"
        assert max_corner[1] == expected_max[1], f"max_y: {max_corner[1]} != {expected_max[1]}"
        assert max_corner[2] == expected_max[2], f"max_z: {max_corner[2]} != {expected_max[2]}"
    
    def test_x_shaped_timbers_with_butt_joint(self):
        """Test bounding box for two timbers in a crossing configuration with a butt joint cut."""
        from kumiki.joints.workshop.butt_joints import cut_plain_butt_joint_on_face_aligned_timbers
        
        # Create two timbers in a crossing configuration that meet near the origin
        # Timber A: receiving timber (uncut), runs perpendicular to timberB
        timberA = create_axis_aligned_timber(
            bottom_position=create_v3(0, -10, 0),
            length=scalar(20),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.RIGHT,
            width_direction=TimberFace.FRONT,
            ticket="TimberA"
        )
        
        # Timber B: butt timber (will be cut), runs perpendicular to timberA
        # Position it so its TOP end will be cut when it meets timberA
        timberB = create_axis_aligned_timber(
            bottom_position=create_v3(-10, 0, 0),
            length=scalar(20),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.FRONT,
            width_direction=TimberFace.RIGHT,
            ticket="TimberB"
        )
        
        # Create a butt joint where timberB's TOP end is cut to butt against timberA
        joint = cut_plain_butt_joint_on_face_aligned_timbers(
            ButtJointTimberArrangement(
                receiving_timber=timberA,
                butt_timber=timberB,
                butt_timber_end=TimberEnd.TOP
            )
        )
        
        # Create frame from the joint
        frame = Frame.from_joints([joint])
        
        # Verify that timberB has cuts applied
        cut_timberB = next(ct for ct in frame.cut_timbers if ct.timber.ticket.path == "TimberB")
        assert len(cut_timberB.cuts) > 0, "TimberB should have cuts applied"
        
        # Receiving timber carries a no-op cut in strict one-cut-per-member mode.
        cut_timberA = next(ct for ct in frame.cut_timbers if ct.timber.ticket.path == "TimberA")
        assert len(cut_timberA.cuts) == 1, "TimberA should have one no-op cutting"
        assert cut_timberA.cuts[0].negative_csg is None
        
        # Get the bounding prisms for both timbers
        timberA_prism = cut_timberA.DEPRECATED_approximate_bounding_prism()
        timberB_prism = cut_timberB.DEPRECATED_approximate_bounding_prism()
        assert timberA_prism.start_distance is not None and timberA_prism.end_distance is not None
        assert timberB_prism.start_distance is not None and timberB_prism.end_distance is not None
        
        # TimberA should still be 20" long (uncut)
        timberA_length = abs(timberA_prism.end_distance - timberA_prism.start_distance)
        assert timberA_length == scalar(20), f"Uncut timber length {timberA_length} should be 20"
        
        # TimberB should be shorter than 20" due to the cut
        timberB_length = abs(timberB_prism.end_distance - timberB_prism.start_distance)
        assert timberB_length < scalar(20), f"Cut timber length {timberB_length} should be < 20"
        
        # The cut should remove a significant amount (at least the thickness of timberA)
        assert timberB_length < scalar(18), f"Cut timber length {timberB_length} should be < 18 (20 - 2)"
        
        # Get overall bounding box
        min_corner, max_corner = frame.get_bounding_box()
        size = max_corner - min_corner
        
        # Z span should be about 4 (timber thickness)
        assert abs(float(size[2]) - 4) < 0.5, f"Z size: {float(size[2])} should be ~4"
        
        # The bounding box should be reasonable (not larger than if both timbers were uncut)
        # Each timber is 20" + some cross-sectional thickness (4" cross-section)
        # So maximum would be 20 + 4 + some margin = ~30
        assert float(size[0]) < 35, f"X size {float(size[0])} should be < 35"
        assert float(size[1]) < 35, f"Y size {float(size[1])} should be < 35"
    
    def test_empty_frame_raises_error(self):
        """Test that computing bounding box for an empty frame raises an error."""
        frame = Frame(cut_timbers=[])
        
        with pytest.raises(ValueError) as exc_info:
            frame.get_bounding_box()
        
        assert "empty frame" in str(exc_info.value).lower()


class TestCutTimberBoundingBoxPrisms:
    """Tests for CutTimber.get_perfect_timber_within_bounding_box_prism and
    get_rough_bounding_box_prism (and the shared _bounding_box_prism_for_cross_section
    helper they're both built on)."""

    def test_uncut_matches_timber_exactly(self):
        """With no cuts, the PTW bounding box prism matches the timber's own bounds."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(10), scalar(20), scalar(5)),
            length=scalar(96),
            size=create_v2(scalar(4), scalar(6)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
        )
        cut_timber = CutTimber(timber, cuts=[])
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()

        assert prism.size == timber.size
        assert prism.start_distance == scalar(0)
        assert prism.end_distance == timber.length
        assert prism.transform.position == timber.get_bottom_position_global()

    def test_single_end_cut_crops(self):
        """A single top end cut crops end_distance; start_distance stays at 0."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
        )
        cut = Cutting(timber=timber, maybe_top_end_cut_distance_from_bottom=scalar(80))
        cut_timber = CutTimber(timber, cuts=[cut])
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()

        assert prism.start_distance == scalar(0)
        assert prism.end_distance == scalar(80)

    def test_multiple_cuts_tightest_crop_wins(self):
        """The most restrictive end cut wins independently at each end, across every
        Cutting on the timber -- this is the "minimal end cuts across the frame's
        cuttings" behavior the no-joints box feature is built on."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(48),
            size=create_v2(scalar(4), scalar(6)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
        )
        cut_a = Cutting(
            timber=timber,
            maybe_top_end_cut_distance_from_bottom=scalar(40),
            maybe_bottom_end_cut_distance_from_bottom=scalar(5),
        )
        cut_b = Cutting(
            timber=timber,
            maybe_top_end_cut_distance_from_bottom=scalar(35),
            maybe_bottom_end_cut_distance_from_bottom=scalar(2),
        )
        cut_timber = CutTimber(timber, cuts=[cut_a, cut_b])
        prism = cut_timber.get_perfect_timber_within_bounding_box_prism()

        # Bottom: max(5, 2) = 5 (tighter cut wins)
        assert prism.start_distance == scalar(5)
        # Top: min(40, 35) = 35 (tighter cut wins)
        assert prism.end_distance == scalar(35)

    def test_deprecated_aliases_still_delegate(self):
        """get_bounding_box_prism and DEPRECATED_approximate_bounding_prism still
        delegate to get_perfect_timber_within_bounding_box_prism post-refactor."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
        )
        cut = Cutting(timber=timber, maybe_top_end_cut_distance_from_bottom=scalar(80))
        cut_timber = CutTimber(timber, cuts=[cut])

        expected = cut_timber.get_perfect_timber_within_bounding_box_prism()
        for actual in (cut_timber.get_bounding_box_prism(), cut_timber.DEPRECATED_approximate_bounding_prism()):  # ty: ignore[deprecated]
            assert actual.size == expected.size
            assert actual.start_distance == expected.start_distance
            assert actual.end_distance == expected.end_distance
            assert actual.transform.position == expected.transform.position

    def test_rough_box_symmetric_matches_ptw_box(self):
        """With symmetric (default) rough half-sizes, the rough box matches the PTW box."""
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
        )
        cut = Cutting(timber=timber, maybe_top_end_cut_distance_from_bottom=scalar(80))
        cut_timber = CutTimber(timber, cuts=[cut])

        ptw_prism = cut_timber.get_perfect_timber_within_bounding_box_prism()
        rough_prism = cut_timber.get_rough_bounding_box_prism()

        assert rough_prism.size == ptw_prism.size
        assert rough_prism.start_distance == ptw_prism.start_distance
        assert rough_prism.end_distance == ptw_prism.end_distance
        assert rough_prism.transform.position == ptw_prism.transform.position

    def test_rough_box_asymmetric_size_and_offset(self):
        """Rough box with asymmetric rough_half_sizes has the correct total size and
        is offset from the centerline (reuses the fixture from test_csg_asymmetric_offset)."""
        t = Timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),   # right=3, left=1 -> total=4, offset_x=+1
                create_v2(scalar(4), scalar(2)),   # front=4, back=2 -> total=6, offset_y=+1
            ),
        )
        cut_timber = CutTimber(t, cuts=[])
        prism = cut_timber.get_rough_bounding_box_prism()

        assert prism.size == create_v2(scalar(4), scalar(6))
        assert prism.transform.position == create_v3(scalar(1), scalar(1), scalar(0))
        assert prism.start_distance == scalar(0)
        assert prism.end_distance == scalar(100)

    def test_rough_box_offset_on_rotated_timber(self):
        """The local (offset_x, offset_y) -> global transform.position conversion uses
        the timber's own (non-axis-aligned) width/height direction vectors, not raw
        global XY -- this is the key regression guard for rotated timbers."""
        base = create_timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            bottom_position=create_v3(scalar(10), scalar(20), scalar(5)),
            length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            width_direction=create_v3(scalar(1), scalar(1), scalar(0)),  # 45 degrees in XY
        )
        t = Timber(
            length=base.length,
            size=base.size,
            transform=base.transform,
            ticket=base.ticket,
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),
                create_v2(scalar(4), scalar(2)),
            ),
        )
        # Sanity check that this timber really is rotated off-axis (guards against the
        # test silently degrading to the axis-aligned case above).
        width_dir = t.get_width_direction_global()
        assert safe_zero_test(width_dir[0] - width_dir[1])
        assert width_dir[2] == 0

        cut_timber = CutTimber(t, cuts=[])
        prism = cut_timber.get_rough_bounding_box_prism()

        _, offset = _get_rough_size_and_offset(t)
        expected_position = (
            t.get_bottom_position_global()
            + t.get_width_direction_global() * offset[0]
            + t.get_height_direction_global() * offset[1]
        )
        assert safe_zero_test((prism.transform.position - expected_position).norm())

    def test_rough_box_polymorphic_on_round_timber(self):
        """get_rough_bounding_box_prism works on a non-Timber PerfectTimberWithin
        subclass (RoundTimber), whose rough half-sizes are always symmetric."""
        rt = RoundTimber(
            length=scalar(100),
            size=create_v2(scalar(12), scalar(12)),
            transform=Transform.identity(),
            diameter=scalar(12),
        )
        cut_timber = CutTimber(rt, cuts=[])
        prism = cut_timber.get_rough_bounding_box_prism()

        assert prism.size == create_v2(scalar(12), scalar(12))
        assert prism.transform.position == rt.get_bottom_position_global()
        assert prism.start_distance == scalar(0)
        assert prism.end_distance == scalar(100)


class TestGetSizeInDirection:
    """Tests for get_size_in_direction_2d and get_size_in_direction_3d."""

    def test_2d_matches_face_normal_width(self):
        """2D +x direction should match get_size_in_face_normal_axis for RIGHT."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_2d(create_v2(1, 0)) == t.get_size_in_face_normal_axis(TimberFace.RIGHT)

    def test_2d_matches_face_normal_height(self):
        """2D +y direction should match get_size_in_face_normal_axis for FRONT."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_2d(create_v2(0, 1)) == t.get_size_in_face_normal_axis(TimberFace.FRONT)

    def test_2d_negative_axes(self):
        """Negative axis directions should give the same result as positive."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_2d(create_v2(-1, 0)) == t.get_size_in_face_normal_axis(TimberFace.LEFT)
        assert t.get_size_in_direction_2d(create_v2(0, -1)) == t.get_size_in_face_normal_axis(TimberFace.BACK)

    def test_2d_diagonal_of_cross_section(self):
        """Direction along the cross-section diagonal of a 4x6 timber."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        # Diagonal direction is (4, 6), normalized = (4, 6) / sqrt(52)
        # Size = 4 * |4/sqrt(52)| + 6 * |6/sqrt(52)| = (16 + 36) / sqrt(52) = 52 / sqrt(52) = sqrt(52)
        result = t.get_size_in_direction_2d(create_v2(4, 6))
        expected = sqrt(52)
        assert safe_zero_test(result - expected)

    def test_2d_arbitrary_direction(self):
        """Non-orthogonal direction at 45 degrees for a square cross-section."""
        t = create_standard_vertical_timber(size=(scalar(3), scalar(3)))
        # Direction (1, 1), normalized = (1/sqrt(2), 1/sqrt(2))
        # Size = 3 * 1/sqrt(2) + 3 * 1/sqrt(2) = 6/sqrt(2) = 3*sqrt(2)
        result = t.get_size_in_direction_2d(create_v2(1, 1))
        expected = 3 * sqrt(2)
        assert safe_zero_test(result - expected)

    def test_2d_unnormalized_input(self):
        """Should handle unnormalized direction vectors correctly."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        # (10, 0) should give same result as (1, 0)
        assert t.get_size_in_direction_2d(create_v2(10, 0)) == scalar(4)

    def test_3d_matches_face_normal_width(self):
        """3D global +x direction should match get_size_in_face_normal_axis for RIGHT on a vertical timber."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_3d(create_v3(1, 0, 0)) == t.get_size_in_face_normal_axis(TimberFace.RIGHT)

    def test_3d_matches_face_normal_height(self):
        """3D global +y direction should match get_size_in_face_normal_axis for FRONT on a vertical timber."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_3d(create_v3(0, 1, 0)) == t.get_size_in_face_normal_axis(TimberFace.FRONT)

    def test_3d_matches_face_normal_length(self):
        """3D global +z direction should match get_size_in_face_normal_axis for TOP on a vertical timber."""
        t = create_standard_vertical_timber(height=100, size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_3d(create_v3(0, 0, 1)) == t.get_size_in_face_normal_axis(TimberFace.TOP)

    def test_3d_negative_axes(self):
        """Negative axis directions should give same result as positive."""
        t = create_standard_vertical_timber(height=100, size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_3d(create_v3(-1, 0, 0)) == t.get_size_in_face_normal_axis(TimberFace.LEFT)
        assert t.get_size_in_direction_3d(create_v3(0, -1, 0)) == t.get_size_in_face_normal_axis(TimberFace.BACK)
        assert t.get_size_in_direction_3d(create_v3(0, 0, -1)) == t.get_size_in_face_normal_axis(TimberFace.BOTTOM)

    def test_3d_diagonal_of_two_long_faces(self):
        """Direction along the diagonal of the two long faces (width and height, no length component)."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        # Global (1, 1, 0) on a vertical timber maps to local (1, 1, 0) (width and height directions)
        # Normalized: (1/sqrt(2), 1/sqrt(2), 0)
        # Size = 4 * 1/sqrt(2) + 6 * 1/sqrt(2) = 10/sqrt(2) = 5*sqrt(2)
        result = t.get_size_in_direction_3d(create_v3(1, 1, 0))
        expected = 5 * sqrt(2)
        assert safe_zero_test(result - expected)

    def test_3d_arbitrary_direction(self):
        """Arbitrary non-orthogonal 3D direction."""
        t = create_standard_vertical_timber(height=100, size=(scalar(4), scalar(6)))
        # Direction (1, 0, 1) on a vertical timber maps to local (1, 0, 1) (width and length)
        # Normalized: (1/sqrt(2), 0, 1/sqrt(2))
        # Size = 4 * 1/sqrt(2) + 6 * 0 + 100 * 1/sqrt(2) = 104/sqrt(2) = 52*sqrt(2)
        result = t.get_size_in_direction_3d(create_v3(1, 0, 1))
        expected = 52 * sqrt(2)
        assert safe_zero_test(result - expected)

    def test_3d_horizontal_timber_axes(self):
        """3D method should respect timber orientation for a horizontal timber."""
        t = create_standard_horizontal_timber(direction='x', length=100, size=(scalar(4), scalar(6)))
        # Horizontal timber in +x direction: length along x, width along y(?), let's check via face normals
        # For horizontal +x timber: length_direction = +x, width_direction = +y
        # So RIGHT face normal = width_direction = +y, FRONT face normal = height_direction
        # Global +x = length direction → should give length = 100
        assert t.get_size_in_direction_3d(create_v3(1, 0, 0)) == t.get_size_in_face_normal_axis(TimberFace.TOP)

    def test_3d_unnormalized_input(self):
        """Should handle unnormalized direction vectors correctly."""
        t = create_standard_vertical_timber(height=100, size=(scalar(4), scalar(6)))
        assert t.get_size_in_direction_3d(create_v3(5, 0, 0)) == scalar(4)


class TestGetRoughHalfSizes:
    """Tests for get_rough_half_sizes and get_half_rough_size_in_face_normal_axis."""

    # -- symmetric defaults on each subclass --

    def test_timber_default_symmetric(self):
        """Timber with no override returns symmetric halves of self.size."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        width_halves, height_halves = t.get_rough_half_sizes()
        assert width_halves[0] == scalar(2)
        assert width_halves[1] == scalar(2)
        assert height_halves[0] == scalar(3)
        assert height_halves[1] == scalar(3)

    def test_board_default_symmetric(self):
        """Board returns symmetric halves of self.size."""
        b = Board(
            length=scalar(2),
            size=create_v2(scalar(10), scalar(8)),
            transform=Transform.identity(),
        )
        width_halves, height_halves = b.get_rough_half_sizes()
        assert width_halves[0] == scalar(5)
        assert width_halves[1] == scalar(5)
        assert height_halves[0] == scalar(4)
        assert height_halves[1] == scalar(4)

    def test_round_timber_symmetric(self):
        """RoundTimber returns symmetric halves using diameter."""
        rt = RoundTimber(
            length=scalar(100),
            size=create_v2(scalar(12), scalar(12)),
            transform=Transform.identity(),
            diameter=scalar(12),
        )
        width_halves, height_halves = rt.get_rough_half_sizes()
        assert width_halves[0] == scalar(6)
        assert width_halves[1] == scalar(6)
        assert height_halves[0] == scalar(6)
        assert height_halves[1] == scalar(6)

    # -- custom asymmetric half-sizes on Timber --

    def test_timber_custom_asymmetric(self):
        """Timber with explicit asymmetric rough_half_sizes returns them."""
        t = Timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),   # right=3, left=1
                create_v2(scalar(4), scalar(2)),   # front=4, back=2
            ),
        )
        width_halves, height_halves = t.get_rough_half_sizes()
        assert width_halves[0] == scalar(3)
        assert width_halves[1] == scalar(1)
        assert height_halves[0] == scalar(4)
        assert height_halves[1] == scalar(2)

    # -- get_rough_size_in_face_normal_axis still returns full size --

    def test_full_rough_size_symmetric(self):
        """get_rough_size_in_face_normal_axis returns full width/height for symmetric timber."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_rough_size_in_face_normal_axis(TimberFace.RIGHT) == scalar(4)
        assert t.get_rough_size_in_face_normal_axis(TimberFace.LEFT) == scalar(4)
        assert t.get_rough_size_in_face_normal_axis(TimberFace.FRONT) == scalar(6)
        assert t.get_rough_size_in_face_normal_axis(TimberFace.BACK) == scalar(6)
        assert t.get_rough_size_in_face_normal_axis(TimberFace.TOP) == scalar(100)

    def test_full_rough_size_asymmetric(self):
        """get_rough_size_in_face_normal_axis returns right+left / front+back for asymmetric timber."""
        t = Timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),   # right=3, left=1 → total 4
                create_v2(scalar(4), scalar(2)),   # front=4, back=2 → total 6
            ),
        )
        assert t.get_rough_size_in_face_normal_axis(TimberFace.RIGHT) == scalar(4)
        assert t.get_rough_size_in_face_normal_axis(TimberFace.FRONT) == scalar(6)


    # -- get_half_rough_size_in_face_normal_axis per-face --

    def test_half_rough_size_symmetric(self):
        """get_half_rough_size_in_face_normal_axis returns half of size for symmetric timber."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.RIGHT) == scalar(2)
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.LEFT) == scalar(2)
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.FRONT) == scalar(3)
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.BACK) == scalar(3)

    def test_half_rough_size_asymmetric(self):
        """get_half_rough_size_in_face_normal_axis returns correct per-face values for asymmetric timber."""
        t = Timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),   # right=3, left=1
                create_v2(scalar(4), scalar(2)),   # front=4, back=2
            ),
        )
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.RIGHT) == scalar(3)
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.LEFT) == scalar(1)
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.FRONT) == scalar(4)
        assert t.get_half_rough_size_in_face_normal_axis(TimberFace.BACK) == scalar(2)

    def test_half_rough_size_raises_for_end_faces(self):
        """get_half_rough_size_in_face_normal_axis raises ValueError for TOP/BOTTOM."""
        t = create_standard_vertical_timber()
        with pytest.raises(ValueError):
            t.get_half_rough_size_in_face_normal_axis(TimberFace.TOP)
        with pytest.raises(ValueError):
            t.get_half_rough_size_in_face_normal_axis(TimberFace.BOTTOM)

    def test_half_rough_size_accepts_long_face(self):
        """get_half_rough_size_in_face_normal_axis works with TimberLongFace."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.get_half_rough_size_in_face_normal_axis(TimberLongFace.RIGHT) == scalar(2)
        assert t.get_half_rough_size_in_face_normal_axis(TimberLongFace.FRONT) == scalar(3)

    # -- is_perfect_timber --

    def test_is_perfect_timber_symmetric(self):
        """Symmetric defaults → is_perfect_timber returns True."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        assert t.is_perfect_timber() == True

    def test_is_perfect_timber_asymmetric(self):
        """Asymmetric half-sizes → is_perfect_timber returns False."""
        t = Timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),
                create_v2(scalar(3), scalar(3)),
            ),
        )
        assert t.is_perfect_timber() == False

    # -- CSG offset for asymmetric half-sizes --

    def test_csg_symmetric_centered(self):
        """Symmetric timber CSG should be centered on the centerline."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        csg = t.get_actual_csg_local()
        # Point on centerline at mid-length should be contained
        assert csg.contains_point(create_v3(scalar(0), scalar(0), scalar(50)))
        # Point at RIGHT face boundary
        assert csg.contains_point(create_v3(scalar(2), scalar(0), scalar(50)))
        # Point just outside RIGHT face
        assert not csg.contains_point(create_v3(scalar(3), scalar(0), scalar(50)))

    def test_csg_asymmetric_offset(self):
        """Asymmetric timber CSG should be offset from the centerline."""
        t = Timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),   # right=3, left=1 → total=4, offset_x=+1
                create_v2(scalar(4), scalar(2)),   # front=4, back=2 → total=6, offset_y=+1
            ),
        )
        csg = t.get_actual_csg_local()
        # The CSG center in local space is at (1, 1, 0) due to offset
        # Right boundary is at offset_x + total_w/2 = 1 + 2 = 3
        assert csg.contains_point(create_v3(scalar(3), scalar(1), scalar(50)))
        assert not csg.contains_point(create_v3(scalar(4), scalar(1), scalar(50)))
        # Left boundary is at offset_x - total_w/2 = 1 - 2 = -1
        assert csg.contains_point(create_v3(scalar(-1), scalar(1), scalar(50)))
        assert not csg.contains_point(create_v3(scalar(-2), scalar(1), scalar(50)))
        # Front boundary is at offset_y + total_h/2 = 1 + 3 = 4
        assert csg.contains_point(create_v3(scalar(1), scalar(4), scalar(50)))
        assert not csg.contains_point(create_v3(scalar(1), scalar(5), scalar(50)))
        # Back boundary is at offset_y - total_h/2 = 1 - 3 = -2
        assert csg.contains_point(create_v3(scalar(1), scalar(-2), scalar(50)))
        assert not csg.contains_point(create_v3(scalar(1), scalar(-3), scalar(50)))


class TestGetRoughSizeAndOffset:
    """Tests for the internal kumiki.timber._get_rough_size_and_offset helper."""

    def test_symmetric_timber_zero_offset(self):
        """Symmetric (default) Timber returns size == self.size and offset (0, 0)."""
        t = create_standard_vertical_timber(size=(scalar(4), scalar(6)))
        size, offset = _get_rough_size_and_offset(t)
        assert size == create_v2(scalar(4), scalar(6))
        assert offset == create_v3(scalar(0), scalar(0), scalar(0))

    def test_asymmetric_timber_size_and_offset(self):
        """Asymmetric rough_half_sizes produce the summed size and the correct offset."""
        t = Timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(1)),   # right=3, left=1 -> total=4, offset_x=+1
                create_v2(scalar(4), scalar(2)),   # front=4, back=2 -> total=6, offset_y=+1
            ),
        )
        size, offset = _get_rough_size_and_offset(t)
        assert size == create_v2(scalar(4), scalar(6))
        assert offset == create_v3(scalar(1), scalar(1), scalar(0))

    def test_round_timber_zero_offset(self):
        """RoundTimber (always symmetric) returns offset (0, 0)."""
        rt = RoundTimber(
            length=scalar(100),
            size=create_v2(scalar(12), scalar(12)),
            transform=Transform.identity(),
            diameter=scalar(12),
        )
        size, offset = _get_rough_size_and_offset(rt)
        assert size == create_v2(scalar(12), scalar(12))
        assert offset == create_v3(scalar(0), scalar(0), scalar(0))

    def test_board_zero_offset(self):
        """Board (always symmetric) returns size == self.size and offset (0, 0)."""
        b = Board(
            length=scalar(2),
            size=create_v2(scalar(10), scalar(8)),
            transform=Transform.identity(),
        )
        size, offset = _get_rough_size_and_offset(b)
        assert size == create_v2(scalar(10), scalar(8))
        assert offset == create_v3(scalar(0), scalar(0), scalar(0))


class TestJointAssembly:
    """Tests for Joint.with_order and solve_frame_assembly."""

    def build_joint(self, ticket_a="post", ticket_b="beam", offset_x=0,
                    freedoms=False, suborders=False):
        timber_a = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(offset_x), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket=ticket_a,
        )
        timber_b = create_axis_aligned_timber(
            bottom_position=create_v3(scalar(offset_x + 10), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket=ticket_b,
        )
        peg = Peg(
            transform=Transform(position=create_v3(scalar(offset_x + 5), 0, scalar(50)), orientation=Orientation.identity()),
            size=scalar(1),
            shape=PegShape.ROUND,
            forward_length=scalar(10),
            stickout_length=scalar(2),
            ticket=AccessoryTicket(path=f"{ticket_a}_peg"),
            assembly_freedom=AssemblyFreedom.translation(create_v3(0, 1, 0), freed_after=scalar(2)) if freedoms else None,
            assembly_ordering=Ordering(0, 0),
        )
        cutting_suborder = 1 if suborders else 0
        joint = Joint(
            cuttings={
                "a": Cutting(
                    timber=timber_a,
                    assembly_freedom=AssemblyFreedom.translation(create_v3(0, 0, 1), freed_after=scalar(4)) if freedoms else None,
                    assembly_ordering=Ordering(0, cutting_suborder),
                    negative_csg=EmptyCSG(),
                ),
                "b": Cutting(
                    timber=timber_b,
                    assembly_freedom=AssemblyFreedom.translation(create_v3(0, 0, -1), freed_after=scalar(4)) if freedoms else None,
                    assembly_ordering=Ordering(0, cutting_suborder),
                    negative_csg=EmptyCSG(),
                ),
            },
            ticket=JointTicket(path=f"{ticket_a}_{ticket_b}", joint_type="test_joint"),
            jointAccessories={"peg": peg},
        )
        return timber_a, timber_b, joint

    def test_with_order_uniform_preserves_suborders(self):
        _, _, joint = self.build_joint(suborders=True)

        ordered = joint.with_order(2)

        assert ordered.cuttings["a"].assembly_ordering == Ordering(2, 1)
        assert ordered.cuttings["b"].assembly_ordering == Ordering(2, 1)
        assert ordered.jointAccessories["peg"].assembly_ordering == Ordering(2, 0)
        # The original joint is untouched (immutability), timber refs preserved.
        assert joint.cuttings["a"].assembly_ordering == Ordering(0, 1)
        assert ordered.cuttings["a"].timber is joint.cuttings["a"].timber

    def test_with_order_mapping_by_key_and_object(self):
        timber_a, timber_b, joint = self.build_joint()
        peg = joint.jointAccessories["peg"]

        # Object references are unhashable (sympy content), so the per-member
        # form also accepts (reference, order) pairs.
        ordered = joint.with_order([("a", 1), (timber_b, 2), (peg, 3)])

        assert ordered.cuttings["a"].assembly_ordering == Ordering(1, 0)
        assert ordered.cuttings["b"].assembly_ordering == Ordering(2, 0)
        assert ordered.jointAccessories["peg"].assembly_ordering == Ordering(3, 0)

    def test_with_order_mapping_partial_keeps_unnamed(self):
        _, _, joint = self.build_joint()

        ordered = joint.with_order({"a": 5})

        assert ordered.cuttings["a"].assembly_ordering == Ordering(5, 0)
        assert ordered.cuttings["b"].assembly_ordering == Ordering(0, 0)
        assert ordered.jointAccessories["peg"].assembly_ordering == Ordering(0, 0)

    def test_with_order_rejects_unknown_references(self):
        _, _, joint = self.build_joint()
        _, foreign_timber, _ = self.build_joint(ticket_a="x", ticket_b="y", offset_x=50)

        with pytest.raises(ValueError, match="unknown member key"):
            joint.with_order({"nope": 1})
        with pytest.raises(ValueError, match="not a timber or accessory"):
            joint.with_order([(foreign_timber, 1)])

    def test_with_order_mapping_rejects_suborder_precedence_violations(self):
        # The peg (suborder 0) must come out before the cuttings (suborder 1);
        # explicit orders may not invert or collapse that.
        _, _, joint = self.build_joint(suborders=True)

        with pytest.raises(ValueError, match="must be extracted before"):
            joint.with_order({"peg": 3, "a": 1, "b": 1})
        with pytest.raises(ValueError, match="must be extracted before"):
            joint.with_order({"peg": 1, "a": 1, "b": 1})

        # A compliant refinement is fine.
        ordered = joint.with_order({"peg": 1, "a": 2, "b": 2})
        assert ordered.jointAccessories["peg"].assembly_ordering == Ordering(1, 0)
        assert ordered.cuttings["a"].assembly_ordering == Ordering(2, 0)

    def test_solve_frame_assembly_end_to_end(self):
        _, _, joint_one = self.build_joint(ticket_a="post_one", ticket_b="beam_one", freedoms=True, suborders=True)
        _, _, joint_two = self.build_joint(ticket_a="post_two", ticket_b="beam_two", offset_x=50, freedoms=True, suborders=True)
        joint_one = joint_one.with_order(1)
        joint_two = joint_two.with_order(2)
        frame = Frame.from_joints([joint_one, joint_two], name="assembly test")

        solution = solve_frame_assembly(frame)

        assert solution is not None
        assert solution.failure is None
        # Pegs pop at (n, 0), one timber separates the joint at (n, 1).
        assert [step.ordering for step in solution.steps] == [
            Ordering(1, 0), Ordering(1, 1), Ordering(2, 0), Ordering(2, 1),
        ]
        peg_step = solution.steps[0]
        assert len(peg_step.movements) == 1
        assert peg_step.movements[0].member_key == joint_one.jointAccessories["peg"].ticket.kumiki_id
        # Both sides are freed by the cut, but the joint only needs one member
        # to depart; the other is skipped as already separated.
        assert len(solution.steps[1].movements) == 1
        assert solution.steps[1].movements[0].member_key in {
            joint_one.cuttings["a"].timber.ticket.kumiki_id,
            joint_one.cuttings["b"].timber.ticket.kumiki_id,
        }

    def test_solve_frame_assembly_returns_none_without_freedoms(self):
        _, _, joint = self.build_joint()
        frame = Frame.from_joints([joint], name="no assembly")

        assert solve_frame_assembly(frame) is None

    def test_solve_frame_assembly_combines_duplicate_timber_entries(self):
        # A compound-style joint where the same timber appears under two
        # cutting keys: freedoms union, earliest ordering wins.
        timber_a, timber_b, joint = self.build_joint()
        freedom_up = AssemblyFreedom.translation(create_v3(0, 0, 1), freed_after=scalar(4))
        freedom_x = AssemblyFreedom.translation(create_v3(1, 0, 0), freed_after=scalar(2))
        compound = Joint(
            cuttings={
                "a": Cutting(timber=timber_a, assembly_freedom=freedom_up, assembly_ordering=Ordering(2, 0), negative_csg=EmptyCSG()),
                "a_2": Cutting(timber=timber_a, assembly_freedom=freedom_x, assembly_ordering=Ordering(1, 0), negative_csg=EmptyCSG()),
                "b": Cutting(timber=timber_b, negative_csg=EmptyCSG()),
            },
            ticket=joint.ticket,
            jointAccessories={},
        )
        frame = Frame.from_joints([compound], name="compound assembly")

        solution = solve_frame_assembly(frame)

        assert solution is not None
        assert solution.failure is None
        assert len(solution.steps) == 1
        step = solution.steps[0]
        assert step.ordering == Ordering(1, 0)
        assert step.movements[0].member_key == timber_a.ticket.kumiki_id


class TestCutTimberJoints:
    """CutTimber.joints -- which joints cut this timber.

    The field existed for a long while but was only ever initialised to [],
    never populated, so it looked like the answer to "which joints touch this
    timber?" and silently was not. Joint attribution in the viewer reads it.
    """

    def _timber(self, name):
        return create_axis_aligned_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket=name,
        )

    def test_from_joints_records_the_joints_that_cut_the_timber(self):
        timber = self._timber("A")
        joint1 = Joint(cuttings={"a": Cutting(timber=timber, negative_csg=EmptyCSG())},
                       ticket=JointTicket(path="joints/one"), jointAccessories={})
        joint2 = Joint(cuttings={"a": Cutting(timber=timber, negative_csg=EmptyCSG())},
                       ticket=JointTicket(path="joints/two"), jointAccessories={})

        cut_timber = CutTimber.from_joints(timber, [joint1, joint2])
        assert cut_timber.joints == [joint1, joint2]

    def test_joints_that_do_not_touch_the_timber_are_excluded(self):
        timber = self._timber("A")
        other = self._timber("B")
        mine = Joint(cuttings={"a": Cutting(timber=timber, negative_csg=EmptyCSG())},
                     ticket=JointTicket(path="joints/mine"), jointAccessories={})
        theirs = Joint(cuttings={"b": Cutting(timber=other, negative_csg=EmptyCSG())},
                       ticket=JointTicket(path="joints/theirs"), jointAccessories={})

        cut_timber = CutTimber.from_joints(timber, [mine, theirs])
        assert cut_timber.joints == [mine]

    def test_a_joint_cutting_the_timber_twice_is_listed_once(self):
        """Deduplicated by joint, not counted per cutting."""
        timber = self._timber("A")
        joint = Joint(
            cuttings={"a": Cutting(timber=timber, negative_csg=EmptyCSG()), "b": Cutting(timber=timber, negative_csg=EmptyCSG())},
            ticket=JointTicket(path="joints/one"),
            jointAccessories={},
        )
        cut_timber = CutTimber.from_joints(timber, [joint])
        assert cut_timber.joints == [joint]
        assert len(cut_timber.cuts) == 2

    def test_frame_from_joints_populates_it_too(self):
        timber = self._timber("A")
        joint = Joint(cuttings={"a": Cutting(timber=timber, negative_csg=EmptyCSG())},
                      ticket=JointTicket(path="joints/one"), jointAccessories={})

        frame = Frame.from_joints([joint])
        assert len(frame.cut_timbers) == 1
        assert frame.cut_timbers[0].joints == [joint]

    def test_an_unjointed_timber_has_none(self):
        jointed = self._timber("A")
        unjointed = self._timber("B")
        joint = Joint(cuttings={"a": Cutting(timber=jointed, negative_csg=EmptyCSG())},
                      ticket=JointTicket(path="joints/one"), jointAccessories={})

        frame = Frame.from_joints([joint], additional_unjointed_timbers=[unjointed])
        by_name = {ct.timber.ticket.path: ct for ct in frame.cut_timbers}
        assert by_name["B"].joints == []

    def test_a_hand_built_cut_timber_has_none(self):
        """No joints to name, which is the honest answer rather than a guess."""
        assert CutTimber(self._timber("A"), cuts=[]).joints == []


class TestTimberCSGLabels:
    """Every shape a timber builds names itself in the CSG tree.

    Without this the timber body is an unlabeled node: the viewer cannot
    address it by path, so its faces are unreachable next to the cuts that
    do have names.
    """

    def _timber(self, cls=Timber, **kwargs):
        return cls(
            length=scalar(100),
            size=Matrix([scalar(4), scalar(6)]),
            transform=Transform.identity(),
            ticket=TimberTicket(path="t"),
            **kwargs,
        )

    def test_the_name_comes_from_the_class(self):
        assert Timber.csg_label_name() == "timber"
        assert Board.csg_label_name() == "board"

    def test_a_compound_class_name_reads_as_words(self):
        assert RoundTimber.csg_label_name() == "round_timber"
        assert RegularPolygonTimber.csg_label_name() == "regular_polygon_timber"

    def test_qualifiers_are_spelled_out_after_the_name(self):
        assert Board.csg_label("rough", "extended").name == "board (rough, extended)"

    def test_no_qualifiers_is_just_the_name(self):
        assert Board.csg_label().name == "board"

    def test_each_shape_says_which_one_it_is(self):
        timber = self._timber()
        assert timber.get_perfect_timber_within_csg_local().label.name == "timber (perfect)"
        assert timber.get_actual_csg_local().label.name == "timber (rough)"
        assert timber.get_extended_perfect_csg_local(True, True).label.name == (
            "timber (perfect, extended)")
        assert timber.get_extended_actual_csg_local(True, True).label.name == (
            "timber (rough, extended)")

    def test_the_label_follows_the_derived_class(self):
        # The whole reason csg_label is a classmethod: a Board's shapes must
        # not report themselves as a plain timber.
        board = self._timber(Board)
        assert board.get_actual_csg_local().label.name == "board (rough)"
        assert board.get_extended_actual_csg_local(True, True).label.name == (
            "board (rough, extended)")

    def test_non_prism_timbers_label_their_own_shapes_too(self):
        # These build a Cylinder / ConvexPolygonExtrusion rather than going
        # through the rectangular-prism helper.
        log = self._timber(RoundTimber, diameter=scalar(4))
        assert log.get_actual_csg_local().label.name == "round_timber (rough)"

        pole = self._timber(RegularPolygonTimber, num_sides=6)
        assert pole.get_extended_actual_csg_local(False, True).label.name == (
            "regular_polygon_timber (rough, extended)")

    def test_the_rendered_body_carries_the_label(self):
        # What the viewer actually navigates: the body node of a cut timber.
        timber = self._timber()
        cut_timber = CutTimber(timber, cuts=[])
        rendered = cut_timber.render_timber_with_cuts_csg_local()
        assert rendered.label.name == "timber (rough, extended)"


class TestDuplicatePlanes:
    """A cutting can describe the same plane twice -- once as its negative_csg
    and once as end-cut metadata. Both are kept: subtracting a plane twice
    removes the same material, so there is nothing to reconcile, and order
    decides which copy answers when something searches for that plane."""

    def _plane(self, label=None, offset=90):
        return HalfSpace(
            normal=create_v3(scalar(0), scalar(0), scalar(1)),
            offset=scalar(offset),
            label=CutCSGLabel(label) if label else CutCSGLabel.NoLabel(),
        )

    def _timber(self):
        return Timber(
            length=scalar(100),
            size=Matrix([scalar(4), scalar(6)]),
            transform=Transform.identity(),
            ticket=TimberTicket(path="t"),
        )

    def _rendered(self, negative_csg):
        cutting = Cutting(
            timber=self._timber(),
            negative_csg=negative_csg,
            maybe_top_end_cut_distance_from_bottom=scalar(90),
        )
        rendered = cutting.get_negative_csg_local()
        assert isinstance(rendered, SolidUnion)
        return rendered

    def test_both_copies_of_a_plane_are_kept(self):
        labels = [c.label.name for c in self._rendered(self._plane("miter_cut")).children]
        assert labels == ["miter_cut", "top_end_cut"]

    def test_the_joints_own_cut_comes_first_and_so_answers_for_the_plane(self):
        # A search resolves to the first match, so the cut the joint authored
        # is the one that names the plane; the generated end cut trails it.
        first = self._rendered(self._plane("miter_cut")).children[0]
        assert first.label.name == "miter_cut"

    def test_duplicating_a_plane_removes_the_same_material(self):
        cutting = Cutting(
            timber=self._timber(),
            negative_csg=self._plane("miter_cut"),
            maybe_top_end_cut_distance_from_bottom=scalar(90),
        )
        once = Cutting(timber=self._timber(), negative_csg=self._plane("miter_cut"))
        both = triangulate_cutcsg(
            CutTimber(self._timber(), cuts=[cutting]).render_timber_with_cuts_csg_local()).mesh
        single = triangulate_cutcsg(
            CutTimber(self._timber(), cuts=[once]).render_timber_with_cuts_csg_local()).mesh
        assert both.is_watertight and single.is_watertight
        assert both.volume == pytest.approx(single.volume)

    def test_a_different_plane_is_kept_alongside(self):
        labels = [c.label.name for c in
                  self._rendered(self._plane("somewhere_else", offset=50)).children]
        assert set(labels) == {"somewhere_else", "top_end_cut"}
