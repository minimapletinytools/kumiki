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
        v = create_v2(Rational(3, 2), Rational(5, 2))  # 1.5, 2.5 as exact rationals
        assert v.shape == (2, 1)
        assert v[0] == Rational(3, 2)
        assert v[1] == Rational(5, 2)
    
    def test_create_v3(self):
        """Test 3D vector creation."""
        v = create_v3(1, 2, 3)  # Use exact integers
        assert v.shape == (3, 1)
        assert v[0] == 1
        assert v[1] == 2
        assert v[2] == 3
    
    def test_normalize_vector(self, symbolic_mode):
        """Test vector normalization."""
        v = create_v3(3, 4, 0)  # Use integers for exact computation
        normalized = normalize_vector(v)
        
        # Should have magnitude 1
        magnitude = vector_magnitude(normalized)
        assert magnitude == 1
        
        # Should preserve direction ratios exactly
        assert normalized[0] == Rational(3, 5)  # 3/5
        assert normalized[1] == Rational(4, 5)  # 4/5
        assert normalized[2] == 0
    
    def test_normalize_zero_vector(self):
        """Test normalization of zero vector."""
        v = create_v3(Integer(0), Integer(0), Integer(0))  # Use exact integers
        normalized = normalize_vector(v)
        assert normalized == v  # Should return original zero vector
    
    def test_cross_product(self):
        """Test cross product calculation."""
        v1 = create_v3(1, 0, 0)  # Use exact integers
        v2 = create_v3(Integer(0), Integer(1), Integer(0))  # Use exact integers
        cross = cross_product(v1, v2)
        
        expected = create_v3(Integer(0), Integer(0), Integer(1))  # Use exact integers
        assert cross[0] == 0
        assert cross[1] == 0
        assert cross[2] == 1
    
    def test_vector_magnitude(self, symbolic_mode):
        """Test vector magnitude calculation."""
        v = create_v3(3, 4, 0)  # Use integers for exact computation
        magnitude = vector_magnitude(v)
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
        """Test TimberReferenceEnd to TimberFeature conversion."""
        assert TimberReferenceEnd.TOP.to == TimberFeature.TOP_FACE
        assert TimberReferenceEnd.BOTTOM.to == TimberFeature.BOTTOM_FACE
    
    def test_timber_feature_to_end(self):
        """Test TimberFeature to TimberReferenceEnd conversion."""
        assert TimberFeature.TOP_FACE.end() == TimberReferenceEnd.TOP
        assert TimberFeature.BOTTOM_FACE.end() == TimberReferenceEnd.BOTTOM
    
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
        with pytest.raises(ValueError, match="Cannot convert.*to TimberReferenceEnd"):
            TimberFeature.RIGHT_FACE.end()
        with pytest.raises(ValueError, match="Cannot convert.*to TimberReferenceEnd"):
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



class TestTimber:
    """Test Timber class."""
    
    def test_timber_creation(self):
        """Test basic timber creation."""
        length = 3  # Use exact integer
        size = create_v2(Rational(1, 10), Rational(1, 10))  # 0.1 as exact rational
        position = create_v3(Integer(0), Integer(0), Integer(0))  # Use exact integers
        length_dir = create_v3(Integer(0), Integer(0), Integer(1))  # Use exact integers
        width_dir = create_v3(1, 0, 0)   # Use exact integers
        
        timber = timber_from_directions(length, size, position, length_dir, width_dir)
        
        assert timber.length == 3
        assert timber.size.shape == (2, 1)
        assert timber.get_bottom_position_global().shape == (3, 1)
        assert isinstance(timber.orientation, Orientation)
    
    def test_timber_orientation_computation(self):
        """Test that timber orientation is computed correctly."""
        # Create vertical timber facing east
        timber = create_standard_vertical_timber(height=2, size=(Rational(1, 10), Rational(1, 10)), position=(0, 0, 0))
        
        # Check that orientation matrix is reasonable
        matrix = timber.orientation.matrix
        assert matrix.shape == (3, 3)
        
        # Check that it's a valid rotation matrix
        assert_is_valid_rotation_matrix(matrix)
    
    def test_get_transform_matrix(self):
        """Test 4x4 transformation matrix generation."""
        timber = create_standard_vertical_timber(height=1, size=(Rational(1, 10), Rational(1, 10)), position=(1, 2, 3))
        
        transform = timber.get_transform_matrix()
        assert transform.shape == (4, 4)
        
        # Check translation part (exact comparison since we used integers)
        assert transform[0, 3] == 1
        assert transform[1, 3] == 2
        assert transform[2, 3] == 3
        assert transform[3, 3] == 1
    
    def test_orientation_computed_from_directions(self, symbolic_mode):
        """Test that orientation is correctly computed from input face and length directions."""
        # Test with standard vertical timber facing east
        input_length_dir = create_v3(Integer(0), Integer(0), Integer(1))  # Up - exact integers
        input_width_dir = create_v3(1, 0, 0)    # East - exact integers
        
        timber = timber_from_directions(
            length=2,  # Use exact integer
            size=create_v2(Rational(1, 10), Rational(1, 10)),  # 0.1 as exact rational
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),  # Use exact integers
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
    
    def test_orientation_with_horizontal_timber(self, symbolic_mode):
        """Test orientation computation with a horizontal timber."""
        # Horizontal timber running north, facing up
        input_length_dir = create_v3(Integer(0), Integer(1), Integer(0))  # North - exact integers
        input_width_dir = create_v3(Integer(0), Integer(0), Integer(1))    # Up - exact integers
        
        timber = timber_from_directions(
            length=3,  # Use exact integer
            size=create_v2(Rational(1, 10), Rational(1, 10)),  # 0.1 as exact rational
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),  # Use exact integers
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
        timber = timber_from_directions(
            length=Rational(1),
            size=create_v2(Rational("0.1"), Rational("0.1")),
            bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
            length_direction=create_v3(Rational(1), Rational(1), Rational(0)),  # Non-axis-aligned
            width_direction=create_v3(Rational(0), Rational(0), Rational(1))     # Up
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
    
    def test_orientation_handles_non_normalized_inputs(self, symbolic_mode):
        """Test that orientation computation works with non-normalized input vectors."""
        # Use vectors that aren't unit length
        input_length_dir = create_v3(Rational(0), Rational(0), Rational(5))  # Up, but length 5
        input_width_dir = create_v3(Rational(3), Rational(0), Rational(0))    # East, but length 3
        
        timber = timber_from_directions(
            length=Rational(1),
            size=create_v2(Rational("0.1"), Rational("0.1")),
            bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
            length_direction=input_length_dir,
            width_direction=input_width_dir
        )
        
        # Despite non-normalized inputs, the output should be normalized
        length_dir = timber.get_length_direction_global()
        width_dir = timber.get_width_direction_global()
        
        # Check that directions are normalized (can be Rational(1) or Float(1))
        assert length_dir[0] == 0
        assert length_dir[1] == 0
        assert length_dir[2] == 1
        
        assert width_dir[0] == 1
        assert width_dir[1] == 0
        assert width_dir[2] == 0
    
    def test_get_position_on_centerline_from_bottom_global(self, symbolic_mode):
        """Test the get_centerline_position_from_bottom method."""
        timber = timber_from_directions(
            length=Rational(5),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(Rational(1), Rational(2), Rational(3)),
            length_direction=create_v3(Rational(0), Rational(1), Rational(0)),  # North
            width_direction=create_v3(Rational(0), Rational(0), Rational(1))     # Up
        )
        
        # Test at bottom position (position = 0)
        pos_at_bottom = locate_position_on_centerline_from_bottom(timber, Rational(0)).position
        assert pos_at_bottom[0] == 1
        assert pos_at_bottom[1] == 2
        assert pos_at_bottom[2] == 3
        
        # Test at midpoint (position = 2.5)
        pos_at_middle = locate_position_on_centerline_from_bottom(timber, Rational("2.5")).position
        assert pos_at_middle[0] == 1
        assert pos_at_middle[1] == Rational("4.5")  # 2.0 + 2.5 * 1.0
        assert pos_at_middle[2] == 3
        
        # Test at top (position = 5.0)
        pos_at_top = locate_position_on_centerline_from_bottom(timber, Rational(5)).position
        assert pos_at_top[0] == 1
        assert pos_at_top[1] == 7  # 2.0 + 5.0 * 1.0
        assert pos_at_top[2] == 3
        
        # Test with negative position (beyond bottom)
        pos_neg = locate_position_on_centerline_from_bottom(timber, -Rational(1)).position
        assert pos_neg[0] == 1
        assert pos_neg[1] == 1  # 2.0 + (-1.0) * 1.0
        assert pos_neg[2] == 3
    
    def test_get_position_on_centerline_from_bottom_global(self, symbolic_mode):
        """Test get_centerline_position_from_bottom method."""
        timber = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(Rational(1), Rational(2), Rational(3)),
            length_direction=create_v3(Rational(0), Rational(0), Rational(1)),  # Up
            width_direction=create_v3(Rational(1), Rational(0), Rational(0))     # East
        )
        
        # Test position at bottom (0)
        pos_bottom = locate_position_on_centerline_from_bottom(timber, Rational(0)).position
        assert pos_bottom[0] == 1
        assert pos_bottom[1] == 2
        assert pos_bottom[2] == 3
        
        # Test position at 3.0 from bottom
        pos_3 = locate_position_on_centerline_from_bottom(timber, Rational(3)).position
        assert pos_3[0] == 1
        assert pos_3[1] == 2
        assert pos_3[2] == 6  # 3.0 + 3.0
        
        # Test position at top (10)
        pos_top = locate_position_on_centerline_from_bottom(timber, Rational(10)).position
        assert pos_top[0] == 1
        assert pos_top[1] == 2
        assert pos_top[2] == 13  # 3.0 + 10.0
    
    def test_get_position_on_centerline_from_top_global(self, symbolic_mode):
        """Test get_centerline_position_from_top method."""
        timber = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(Rational(1), Rational(2), Rational(3)),
            length_direction=create_v3(Rational(0), Rational(0), Rational(1)),  # Up
            width_direction=create_v3(Rational(1), Rational(0), Rational(0))     # East
        )
        
        # Test position at top (0 from top = 10 from bottom)
        pos_top = locate_position_on_centerline_from_top(timber, Rational(0)).position
        assert pos_top[0] == 1
        assert pos_top[1] == 2
        assert pos_top[2] == 13  # 3.0 + 10.0
        
        # Test position at 3.0 from top (= 7.0 from bottom)
        pos_3 = locate_position_on_centerline_from_top(timber, Rational(3)).position
        assert pos_3[0] == 1
        assert pos_3[1] == 2
        assert pos_3[2] == 10  # 3.0 + 7.0
        
        # Test at bottom (10 from top = 0 from bottom)
        pos_bottom = locate_position_on_centerline_from_top(timber, Rational(10)).position
        assert pos_bottom[0] == 1
        assert pos_bottom[1] == 2
        assert pos_bottom[2] == 3  # 3.0 + 0.0

    def test_get_size_in_face_normal_axis(self):
        """Test get_size_in_face_normal_axis method returns correct dimensions for each face."""
        # Create a timber with distinct dimensions:
        # length = 10, width (size[0]) = 0.2, height (size[1]) = 0.3
        timber = timber_from_directions(
            length=Rational(10),
            size=create_v2(Rational("0.2"), Rational("0.3")),
            bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
            length_direction=create_v3(Rational(0), Rational(0), Rational(1)),  # Up (Z-axis)
            width_direction=create_v3(Rational(1), Rational(0), Rational(0))     # East (X-axis)
        )
        
        # TOP and BOTTOM faces are perpendicular to the length direction (Z-axis)
        # So they should return the length
        assert timber.get_size_in_face_normal_axis(TimberFace.TOP) == Rational(10)
        assert timber.get_size_in_face_normal_axis(TimberFace.BOTTOM) == Rational(10)
        
        # RIGHT and LEFT faces are perpendicular to the width direction (X-axis)
        # So they should return the width (size[0])
        assert timber.get_size_in_face_normal_axis(TimberFace.RIGHT) == Rational("0.2")
        assert timber.get_size_in_face_normal_axis(TimberFace.LEFT) == Rational("0.2")
        
        # FRONT and BACK faces are perpendicular to the height direction (Y-axis)
        # So they should return the height (size[1])
        assert timber.get_size_in_face_normal_axis(TimberFace.FRONT) == Rational("0.3")
        assert timber.get_size_in_face_normal_axis(TimberFace.BACK) == Rational("0.3")


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

    def test_bot_right_front_vertical_timber(self, symbolic_mode):
        """BOT_RIGHT_FRONT corner of a 10x20x100 vertical timber at origin = (5, 10, 0)."""
        timber = timber_from_directions(
            length=Rational(100),
            size=create_v2(10, 20),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 0, 1),
            width_direction=create_v3(1, 0, 0),
            ticket="test_timber"
        )
        pos = timber.get_corner_position_global(TimberCorner.BOT_RIGHT_FRONT)
        assert pos[0] == Rational(5)
        assert pos[1] == Rational(10)
        assert pos[2] == Rational(0)


class TestCutTimber:
    """Test CutTimber CSG operations."""
    
    def test_extended_timber_without_cuts_finite(self):
        """Test _extended_timber_without_cuts_csg for a timber with no cuts (finite)."""
        # Create a simple timber
        length = Rational(100)
        size = Matrix([Rational(4), Rational(6)])
        bottom_position = Matrix([Rational(0), Rational(0), Rational(10)])
        length_direction = Matrix([Rational(0), Rational(0), Rational(1)])
        width_direction = Matrix([Rational(1), Rational(0), Rational(0)])
        
        timber = timber_from_directions(length, size, bottom_position, length_direction, width_direction, ticket='test_timber')
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
        assert simplify(csg.transform.orientation.matrix - Orientation.identity().matrix).norm() == 0
    
    def test_extended_timber_without_cuts_positioned(self):
        """Test that CSG works correctly for timber at different position."""
        # Create a timber at a different position
        length = Rational(50)
        size = Matrix([Rational(3), Rational(4)])
        bottom_position = Matrix([Rational(5), Rational(10), Rational(20)])
        length_direction = Matrix([Rational(0), Rational(0), Rational(1)])
        width_direction = Matrix([Rational(1), Rational(0), Rational(0)])
        
        timber = timber_from_directions(length, size, bottom_position, length_direction, width_direction)
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
        length = Rational(80)
        size = Matrix([Rational(5), Rational(5)])
        bottom_position = Matrix([Rational(10), Rational(20), Rational(5)])
        length_direction = Matrix([Rational(1), Rational(0), Rational(0)])  # Along X
        width_direction = Matrix([Rational(0), Rational(1), Rational(0)])
        
        timber = timber_from_directions(length, size, bottom_position, length_direction, width_direction)
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
        length = Rational(100)
        size = Matrix([Rational(4), Rational(6)])
        bottom_position = Matrix([Rational(0), Rational(0), Rational(0)])
        length_direction = Matrix([Rational(0), Rational(0), Rational(1)])
        width_direction = Matrix([Rational(1), Rational(0), Rational(0)])
        
        timber = timber_from_directions(length, size, bottom_position, length_direction, width_direction)
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
        length = Rational(100)
        size = Matrix([Rational(4), Rational(6)])
        bottom_position = Matrix([Rational(0), Rational(0), Rational(10)])
        length_direction = Matrix([Rational(0), Rational(0), Rational(1)])
        width_direction = Matrix([Rational(1), Rational(0), Rational(0)])
        
        timber = timber_from_directions(length, size, bottom_position, length_direction, width_direction)
        
        # Add a cut (a simple half-plane cut at z=50 in local coordinates)
        from kumiki.cutcsg import HalfSpace
        # Create a half plane that cuts perpendicular to the timber length
        # Normal pointing in +Z direction, offset at 50
        half_plane = HalfSpace(
            normal=Matrix([Rational(0), Rational(0), Rational(1)]),
            offset=Rational(50)
        )
        cut = Cutting(
            timber=timber,
            maybe_top_end_cut=None,
            maybe_bottom_end_cut=None,
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
        assert isinstance(csg.subtract[0], HalfSpace)
    
    def test_render_timber_with_cuts_multiple_cuts(self):
        """Test render_timber_with_cuts_csg_local with multiple cuts."""
        length = Rational(100)
        size = Matrix([Rational(4), Rational(6)])
        bottom_position = Matrix([Rational(0), Rational(0), Rational(0)])
        length_direction = Matrix([Rational(0), Rational(0), Rational(1)])
        width_direction = Matrix([Rational(1), Rational(0), Rational(0)])
        
        timber = timber_from_directions(length, size, bottom_position, length_direction, width_direction)
        
        # Add two cuts
        from kumiki.cutcsg import HalfSpace
        half_plane1 = HalfSpace(
            normal=Matrix([Rational(0), Rational(0), Rational(1)]),
            offset=Rational(25)
        )
        cut1 = Cutting(
            timber=timber,
            maybe_top_end_cut=None,
            maybe_bottom_end_cut=None,
            negative_csg=half_plane1
        )
        
        half_plane2 = HalfSpace(
            normal=Matrix([Rational(0), Rational(0), Rational(-1)]),
            offset=Rational(-75)
        )
        cut2 = Cutting(
            timber=timber,
            maybe_top_end_cut=None,
            maybe_bottom_end_cut=None,
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
        assert all(isinstance(sub, HalfSpace) for sub in csg.subtract)
    
    def test_render_timber_with_cuts_with_end_cuts(self):
        """Test render_timber_with_cuts_csg_local with end cuts."""
        length = Rational(100)
        size = Matrix([Rational(4), Rational(6)])
        bottom_position = Matrix([Rational(0), Rational(0), Rational(0)])
        length_direction = Matrix([Rational(0), Rational(0), Rational(1)])
        width_direction = Matrix([Rational(1), Rational(0), Rational(0)])
        
        timber = timber_from_directions(length, size, bottom_position, length_direction, width_direction)
        
        # Add an end cut at the top
        from kumiki.cutcsg import HalfSpace
        half_plane = HalfSpace(
            normal=Matrix([Rational(0), Rational(0), Rational(-1)]),
            offset=Rational(-50)
        )
        end_cut = Cutting(
            timber=timber,
            maybe_top_end_cut=half_plane,
            maybe_bottom_end_cut=None,
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
        assert isinstance(csg.subtract[0], HalfSpace)


class TestFrameFromJoints:
    """Test Frame.from_joints constructor."""
    
    def test_from_joints_simple(self):
        """Test creating a frame from a list of joints."""
        # Create two simple timbers
        timber1 = create_axis_aligned_timber(
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber 1"
        )
        
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(Rational(10), 0, 0),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber 2"
        )
        
        # Create mock cuts for each timber
        cut1 = MockCutting(timber1, create_v3(Integer(0), Integer(0), Integer(0)))
        cut2 = MockCutting(timber2, create_v3(Integer(0), Integer(0), Integer(0)))
        
        # Create CutTimbers
        cut_timber1 = CutTimber(timber1, cuts=[cut1])  # type: ignore
        cut_timber2 = CutTimber(timber2, cuts=[cut2])  # type: ignore
        
        # Create a joint
        joint = Joint(
            cut_timbers={"timber1": cut_timber1, "timber2": cut_timber2},
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
        timber_names = [ct.timber.ticket.name for ct in frame.cut_timbers]
        assert "Timber 1" in timber_names
        assert "Timber 2" in timber_names
    
    def test_from_joints_merges_same_timber(self):
        """Test that cut timbers with the same underlying timber reference are merged."""
        # Create a single timber
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Shared Timber"
        )
        
        # Create different cuts for the same timber
        cut1 = MockCutting(timber, create_v3(Integer(0), Integer(0), Integer(0)))
        cut2 = MockCutting(timber, create_v3(Integer(0), Integer(0), Integer(0)))
        cut3 = MockCutting(timber, create_v3(Integer(0), Integer(0), Integer(0)))
        
        # Create multiple CutTimber instances for the same timber
        cut_timber1 = CutTimber(timber, cuts=[cut1])  # type: ignore
        cut_timber2 = CutTimber(timber, cuts=[cut2, cut3])  # type: ignore
        
        # Create two joints that both reference the same timber
        joint1 = Joint(
            cut_timbers={"timber": cut_timber1},
            ticket=JointTicket(joint_type="test_merge_shared_1"),
            jointAccessories={}
        )
        
        joint2 = Joint(
            cut_timbers={"timber": cut_timber2},
            ticket=JointTicket(joint_type="test_merge_shared_2"),
            jointAccessories={}
        )
        
        # Create frame from joints
        frame = Frame.from_joints([joint1, joint2])
        
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
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Timber"
        )
        
        # Create a peg accessory
        peg = Peg(
            transform=Transform(
                position=create_v3(0, 0, Rational(50)),
                orientation=Orientation.identity()
            ),
            size=Rational(1),
            shape=PegShape.ROUND,
            forward_length=Rational(10),
            stickout_length=Rational(2)
        )
        
        # Create a wedge accessory
        wedge = Wedge(
            transform=Transform(
                position=create_v3(0, 0, Rational(100)),
                orientation=Orientation.identity()
            ),
            base_width=Rational(2),
            tip_width=Rational(1),
            height=Rational(3),
            length=Rational(5)
        )
        
        # Create joints with accessories
        joint1 = Joint(
            cut_timbers={"timber": CutTimber(timber, cuts=[])},
            ticket=JointTicket(joint_type="test_accessories_peg"),
            jointAccessories={"peg": peg}
        )
        
        joint2 = Joint(
            cut_timbers={"timber": CutTimber(timber, cuts=[])},
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
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Jointed Timber"
        )
        
        # Create an unjointed timber
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(Rational(10), 0, 0),
            length=Rational(50),
            size=create_v2(Rational(2), Rational(2)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Unjointed Timber"
        )
        
        # Create a joint with timber1
        joint = Joint(
            cut_timbers={"timber1": CutTimber(timber1, cuts=[MockCutting(timber1, create_v3(Integer(0), Integer(0), Integer(0)))])},  # type: ignore
            ticket=JointTicket(joint_type="test_with_unjointed"),
            jointAccessories={}
        )
        
        # Create frame with additional unjointed timber
        frame = Frame.from_joints([joint], additional_unjointed_timbers=[timber2])
        
        # Verify both timbers are in the frame
        assert len(frame.cut_timbers) == 2
        
        timber_names = [ct.timber.ticket.name for ct in frame.cut_timbers]
        assert "Jointed Timber" in timber_names
        assert "Unjointed Timber" in timber_names
        
        # Verify unjointed timber has no cuts
        unjointed_ct = [ct for ct in frame.cut_timbers if ct.timber.ticket.name == "Unjointed Timber"][0]
        assert len(unjointed_ct.cuts) == 0
    
    def test_from_joints_warns_on_different_timbers_same_name(self):
        """Test that a warning is issued when different timbers have the same name."""
        # Create two different timbers with the same name
        timber1 = create_axis_aligned_timber(
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"
        )
        
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(Rational(10), 0, 0),
            length=Rational(80),  # Different length
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"  # Same name
        )
        
        # Create joints
        joint1 = Joint(
            cut_timbers={"timber1": CutTimber(timber1, cuts=[])},
            ticket=JointTicket(joint_type="test_same_name_warn_1"),
            jointAccessories={}
        )
        
        joint2 = Joint(
            cut_timbers={"timber2": CutTimber(timber2, cuts=[])},
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
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"
        )
        
        # Create an identical timber (same data, different object)
        timber2 = create_axis_aligned_timber(
            bottom_position=create_v3(Integer(0), Integer(0), Integer(0)),
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Post"
        )
        
        # Verify they are different objects but equal data
        assert timber1 is not timber2
        assert timber1 == timber2
        
        # Create joints
        joint1 = Joint(
            cut_timbers={"timber1": CutTimber(timber1, cuts=[])},
            ticket=JointTicket(joint_type="test_dup_data_1"),
            jointAccessories={}
        )
        
        joint2 = Joint(
            cut_timbers={"timber2": CutTimber(timber2, cuts=[])},
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
    
    def test_single_timber_bounding_box_matches_timber_prism(self, symbolic_mode):
        """Test that a frame with a single timber has a bounding box matching the timber's prism."""
        # Create a simple vertical timber
        timber = create_axis_aligned_timber(
            bottom_position=create_v3(10, 20, 5),
            length=Rational(96),  # 8 feet
            size=create_v2(Rational(4), Rational(4)),  # 4x4 inches
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
            10 - Rational(2),  # 10 - 4/2
            20 - Rational(2),  # 20 - 4/2
            5                   # bottom z
        )
        expected_max = create_v3(
            10 + Rational(2),  # 10 + 4/2
            20 + Rational(2),  # 20 + 4/2
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
        from kumiki.joints.plain_joints import cut_plain_butt_joint_on_face_aligned_timbers
        
        # Create two timbers in a crossing configuration that meet near the origin
        # Timber A: receiving timber (uncut), runs perpendicular to timberB
        timberA = create_axis_aligned_timber(
            bottom_position=create_v3(0, -10, 0),
            length=Rational(20),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.RIGHT,
            width_direction=TimberFace.FRONT,
            ticket="TimberA"
        )
        
        # Timber B: butt timber (will be cut), runs perpendicular to timberA
        # Position it so its TOP end will be cut when it meets timberA
        timberB = create_axis_aligned_timber(
            bottom_position=create_v3(-10, 0, 0),
            length=Rational(20),
            size=create_v2(Rational(4), Rational(4)),
            length_direction=TimberFace.FRONT,
            width_direction=TimberFace.RIGHT,
            ticket="TimberB"
        )
        
        # Create a butt joint where timberB's TOP end is cut to butt against timberA
        joint = cut_plain_butt_joint_on_face_aligned_timbers(
            ButtJointTimberArrangement(
                receiving_timber=timberA,
                butt_timber=timberB,
                butt_timber_end=TimberReferenceEnd.TOP
            )
        )
        
        # Create frame from the joint
        frame = Frame.from_joints([joint])
        
        # Verify that timberB has cuts applied
        cut_timberB = next(ct for ct in frame.cut_timbers if ct.timber.ticket.name == "TimberB")
        assert len(cut_timberB.cuts) > 0, "TimberB should have cuts applied"
        
        # Verify that timberA is uncut
        cut_timberA = next(ct for ct in frame.cut_timbers if ct.timber.ticket.name == "TimberA")
        assert len(cut_timberA.cuts) == 0, "TimberA should be uncut (receiving timber)"
        
        # Get the bounding prisms for both timbers
        timberA_prism = cut_timberA.DEPRECATED_approximate_bounding_prism()
        timberB_prism = cut_timberB.DEPRECATED_approximate_bounding_prism()
        
        # TimberA should still be 20" long (uncut)
        timberA_length = abs(timberA_prism.end_distance - timberA_prism.start_distance)
        assert timberA_length == Rational(20), f"Uncut timber length {timberA_length} should be 20"
        
        # TimberB should be shorter than 20" due to the cut
        timberB_length = abs(timberB_prism.end_distance - timberB_prism.start_distance)
        assert timberB_length < Rational(20), f"Cut timber length {timberB_length} should be < 20"
        
        # The cut should remove a significant amount (at least the thickness of timberA)
        assert timberB_length < Rational(18), f"Cut timber length {timberB_length} should be < 18 (20 - 2)"
        
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


class TestGetSizeInDirection:
    """Tests for get_size_in_direction_2d and get_size_in_direction_3d."""

    def test_2d_matches_face_normal_width(self, symbolic_mode):
        """2D +x direction should match get_size_in_face_normal_axis for RIGHT."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_2d(create_v2(1, 0)) == t.get_size_in_face_normal_axis(TimberFace.RIGHT)

    def test_2d_matches_face_normal_height(self, symbolic_mode):
        """2D +y direction should match get_size_in_face_normal_axis for FRONT."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_2d(create_v2(0, 1)) == t.get_size_in_face_normal_axis(TimberFace.FRONT)

    def test_2d_negative_axes(self, symbolic_mode):
        """Negative axis directions should give the same result as positive."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_2d(create_v2(-1, 0)) == t.get_size_in_face_normal_axis(TimberFace.LEFT)
        assert t.get_size_in_direction_2d(create_v2(0, -1)) == t.get_size_in_face_normal_axis(TimberFace.BACK)

    def test_2d_diagonal_of_cross_section(self, symbolic_mode):
        """Direction along the cross-section diagonal of a 4x6 timber."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        # Diagonal direction is (4, 6), normalized = (4, 6) / sqrt(52)
        # Size = 4 * |4/sqrt(52)| + 6 * |6/sqrt(52)| = (16 + 36) / sqrt(52) = 52 / sqrt(52) = sqrt(52)
        result = t.get_size_in_direction_2d(create_v2(4, 6))
        expected = sqrt(52)
        assert simplify(result - expected) == 0

    def test_2d_arbitrary_direction(self, symbolic_mode):
        """Non-orthogonal direction at 45 degrees for a square cross-section."""
        t = create_standard_vertical_timber(size=(Rational(3), Rational(3)))
        # Direction (1, 1), normalized = (1/sqrt(2), 1/sqrt(2))
        # Size = 3 * 1/sqrt(2) + 3 * 1/sqrt(2) = 6/sqrt(2) = 3*sqrt(2)
        result = t.get_size_in_direction_2d(create_v2(1, 1))
        expected = 3 * sqrt(2)
        assert simplify(result - expected) == 0

    def test_2d_unnormalized_input(self, symbolic_mode):
        """Should handle unnormalized direction vectors correctly."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        # (10, 0) should give same result as (1, 0)
        assert t.get_size_in_direction_2d(create_v2(10, 0)) == Rational(4)

    def test_3d_matches_face_normal_width(self, symbolic_mode):
        """3D global +x direction should match get_size_in_face_normal_axis for RIGHT on a vertical timber."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_3d(create_v3(1, 0, 0)) == t.get_size_in_face_normal_axis(TimberFace.RIGHT)

    def test_3d_matches_face_normal_height(self, symbolic_mode):
        """3D global +y direction should match get_size_in_face_normal_axis for FRONT on a vertical timber."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_3d(create_v3(0, 1, 0)) == t.get_size_in_face_normal_axis(TimberFace.FRONT)

    def test_3d_matches_face_normal_length(self, symbolic_mode):
        """3D global +z direction should match get_size_in_face_normal_axis for TOP on a vertical timber."""
        t = create_standard_vertical_timber(height=100, size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_3d(create_v3(0, 0, 1)) == t.get_size_in_face_normal_axis(TimberFace.TOP)

    def test_3d_negative_axes(self, symbolic_mode):
        """Negative axis directions should give same result as positive."""
        t = create_standard_vertical_timber(height=100, size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_3d(create_v3(-1, 0, 0)) == t.get_size_in_face_normal_axis(TimberFace.LEFT)
        assert t.get_size_in_direction_3d(create_v3(0, -1, 0)) == t.get_size_in_face_normal_axis(TimberFace.BACK)
        assert t.get_size_in_direction_3d(create_v3(0, 0, -1)) == t.get_size_in_face_normal_axis(TimberFace.BOTTOM)

    def test_3d_diagonal_of_two_long_faces(self, symbolic_mode):
        """Direction along the diagonal of the two long faces (width and height, no length component)."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        # Global (1, 1, 0) on a vertical timber maps to local (1, 1, 0) (width and height directions)
        # Normalized: (1/sqrt(2), 1/sqrt(2), 0)
        # Size = 4 * 1/sqrt(2) + 6 * 1/sqrt(2) = 10/sqrt(2) = 5*sqrt(2)
        result = t.get_size_in_direction_3d(create_v3(1, 1, 0))
        expected = 5 * sqrt(2)
        assert simplify(result - expected) == 0

    def test_3d_arbitrary_direction(self, symbolic_mode):
        """Arbitrary non-orthogonal 3D direction."""
        t = create_standard_vertical_timber(height=100, size=(Rational(4), Rational(6)))
        # Direction (1, 0, 1) on a vertical timber maps to local (1, 0, 1) (width and length)
        # Normalized: (1/sqrt(2), 0, 1/sqrt(2))
        # Size = 4 * 1/sqrt(2) + 6 * 0 + 100 * 1/sqrt(2) = 104/sqrt(2) = 52*sqrt(2)
        result = t.get_size_in_direction_3d(create_v3(1, 0, 1))
        expected = 52 * sqrt(2)
        assert simplify(result - expected) == 0

    def test_3d_horizontal_timber_axes(self, symbolic_mode):
        """3D method should respect timber orientation for a horizontal timber."""
        t = create_standard_horizontal_timber(direction='x', length=100, size=(Rational(4), Rational(6)))
        # Horizontal timber in +x direction: length along x, width along y(?), let's check via face normals
        # For horizontal +x timber: length_direction = +x, width_direction = +y
        # So RIGHT face normal = width_direction = +y, FRONT face normal = height_direction
        # Global +x = length direction → should give length = 100
        assert t.get_size_in_direction_3d(create_v3(1, 0, 0)) == t.get_size_in_face_normal_axis(TimberFace.TOP)

    def test_3d_unnormalized_input(self, symbolic_mode):
        """Should handle unnormalized direction vectors correctly."""
        t = create_standard_vertical_timber(height=100, size=(Rational(4), Rational(6)))
        assert t.get_size_in_direction_3d(create_v3(5, 0, 0)) == Rational(4)


class TestGetNominalHalfSizes:
    """Tests for get_nominal_half_sizes and get_half_nominal_size_in_face_normal_axis."""

    # -- symmetric defaults on each subclass --

    def test_timber_default_symmetric(self):
        """Timber with no override returns symmetric halves of self.size."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        width_halves, height_halves = t.get_nominal_half_sizes()
        assert width_halves[0] == Rational(2)
        assert width_halves[1] == Rational(2)
        assert height_halves[0] == Rational(3)
        assert height_halves[1] == Rational(3)

    def test_board_default_symmetric(self):
        """Board returns symmetric halves of self.size."""
        b = Board(
            length=Rational(2),
            size=create_v2(Rational(10), Rational(8)),
            transform=Transform.identity(),
        )
        width_halves, height_halves = b.get_nominal_half_sizes()
        assert width_halves[0] == Rational(5)
        assert width_halves[1] == Rational(5)
        assert height_halves[0] == Rational(4)
        assert height_halves[1] == Rational(4)

    def test_round_timber_symmetric(self):
        """RoundTimber returns symmetric halves using diameter."""
        rt = RoundTimber(
            length=Rational(100),
            size=create_v2(Rational(12), Rational(12)),
            transform=Transform.identity(),
            diameter=Rational(12),
        )
        width_halves, height_halves = rt.get_nominal_half_sizes()
        assert width_halves[0] == Rational(6)
        assert width_halves[1] == Rational(6)
        assert height_halves[0] == Rational(6)
        assert height_halves[1] == Rational(6)

    # -- custom asymmetric half-sizes on Timber --

    def test_timber_custom_asymmetric(self):
        """Timber with explicit asymmetric nominal_half_sizes returns them."""
        t = Timber(
            length=Rational(100),
            size=create_v2(Rational(4), Rational(6)),
            transform=Transform.identity(),
            nominal_half_sizes=(
                create_v2(Rational(3), Rational(1)),   # right=3, left=1
                create_v2(Rational(4), Rational(2)),   # front=4, back=2
            ),
        )
        width_halves, height_halves = t.get_nominal_half_sizes()
        assert width_halves[0] == Rational(3)
        assert width_halves[1] == Rational(1)
        assert height_halves[0] == Rational(4)
        assert height_halves[1] == Rational(2)

    # -- get_nominal_size_in_face_normal_axis still returns full size --

    def test_full_nominal_size_symmetric(self):
        """get_nominal_size_in_face_normal_axis returns full width/height for symmetric timber."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_nominal_size_in_face_normal_axis(TimberFace.RIGHT) == Rational(4)
        assert t.get_nominal_size_in_face_normal_axis(TimberFace.LEFT) == Rational(4)
        assert t.get_nominal_size_in_face_normal_axis(TimberFace.FRONT) == Rational(6)
        assert t.get_nominal_size_in_face_normal_axis(TimberFace.BACK) == Rational(6)
        assert t.get_nominal_size_in_face_normal_axis(TimberFace.TOP) == Rational(100)

    def test_full_nominal_size_asymmetric(self):
        """get_nominal_size_in_face_normal_axis returns right+left / front+back for asymmetric timber."""
        t = Timber(
            length=Rational(100),
            size=create_v2(Rational(4), Rational(6)),
            transform=Transform.identity(),
            nominal_half_sizes=(
                create_v2(Rational(3), Rational(1)),   # right=3, left=1 → total 4
                create_v2(Rational(4), Rational(2)),   # front=4, back=2 → total 6
            ),
        )
        assert t.get_nominal_size_in_face_normal_axis(TimberFace.RIGHT) == Rational(4)
        assert t.get_nominal_size_in_face_normal_axis(TimberFace.FRONT) == Rational(6)

    # -- get_half_nominal_size_in_face_normal_axis per-face --

    def test_half_nominal_size_symmetric(self):
        """get_half_nominal_size_in_face_normal_axis returns half of size for symmetric timber."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.RIGHT) == Rational(2)
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.LEFT) == Rational(2)
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.FRONT) == Rational(3)
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.BACK) == Rational(3)

    def test_half_nominal_size_asymmetric(self):
        """get_half_nominal_size_in_face_normal_axis returns correct per-face values for asymmetric timber."""
        t = Timber(
            length=Rational(100),
            size=create_v2(Rational(4), Rational(6)),
            transform=Transform.identity(),
            nominal_half_sizes=(
                create_v2(Rational(3), Rational(1)),   # right=3, left=1
                create_v2(Rational(4), Rational(2)),   # front=4, back=2
            ),
        )
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.RIGHT) == Rational(3)
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.LEFT) == Rational(1)
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.FRONT) == Rational(4)
        assert t.get_half_nominal_size_in_face_normal_axis(TimberFace.BACK) == Rational(2)

    def test_half_nominal_size_raises_for_end_faces(self):
        """get_half_nominal_size_in_face_normal_axis raises ValueError for TOP/BOTTOM."""
        t = create_standard_vertical_timber()
        with pytest.raises(ValueError):
            t.get_half_nominal_size_in_face_normal_axis(TimberFace.TOP)
        with pytest.raises(ValueError):
            t.get_half_nominal_size_in_face_normal_axis(TimberFace.BOTTOM)

    def test_half_nominal_size_accepts_long_face(self):
        """get_half_nominal_size_in_face_normal_axis works with TimberLongFace."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.get_half_nominal_size_in_face_normal_axis(TimberLongFace.RIGHT) == Rational(2)
        assert t.get_half_nominal_size_in_face_normal_axis(TimberLongFace.FRONT) == Rational(3)

    # -- is_perfect_timber --

    def test_is_perfect_timber_symmetric(self):
        """Symmetric defaults → is_perfect_timber returns True."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        assert t.is_perfect_timber() == True

    def test_is_perfect_timber_asymmetric(self):
        """Asymmetric half-sizes → is_perfect_timber returns False."""
        t = Timber(
            length=Rational(100),
            size=create_v2(Rational(4), Rational(6)),
            transform=Transform.identity(),
            nominal_half_sizes=(
                create_v2(Rational(3), Rational(1)),
                create_v2(Rational(3), Rational(3)),
            ),
        )
        assert t.is_perfect_timber() == False

    # -- CSG offset for asymmetric half-sizes --

    def test_csg_symmetric_centered(self):
        """Symmetric timber CSG should be centered on the centerline."""
        t = create_standard_vertical_timber(size=(Rational(4), Rational(6)))
        csg = t.get_actual_csg_local()
        # Point on centerline at mid-length should be contained
        assert csg.contains_point(create_v3(Integer(0), Integer(0), Rational(50)))
        # Point at RIGHT face boundary
        assert csg.contains_point(create_v3(Rational(2), Integer(0), Rational(50)))
        # Point just outside RIGHT face
        assert not csg.contains_point(create_v3(Rational(3), Integer(0), Rational(50)))

    def test_csg_asymmetric_offset(self):
        """Asymmetric timber CSG should be offset from the centerline."""
        t = Timber(
            length=Rational(100),
            size=create_v2(Rational(4), Rational(6)),
            transform=Transform.identity(),
            nominal_half_sizes=(
                create_v2(Rational(3), Rational(1)),   # right=3, left=1 → total=4, offset_x=+1
                create_v2(Rational(4), Rational(2)),   # front=4, back=2 → total=6, offset_y=+1
            ),
        )
        csg = t.get_actual_csg_local()
        # The CSG center in local space is at (1, 1, 0) due to offset
        # Right boundary is at offset_x + total_w/2 = 1 + 2 = 3
        assert csg.contains_point(create_v3(Rational(3), Integer(1), Rational(50)))
        assert not csg.contains_point(create_v3(Rational(4), Integer(1), Rational(50)))
        # Left boundary is at offset_x - total_w/2 = 1 - 2 = -1
        assert csg.contains_point(create_v3(Rational(-1), Integer(1), Rational(50)))
        assert not csg.contains_point(create_v3(Rational(-2), Integer(1), Rational(50)))
        # Front boundary is at offset_y + total_h/2 = 1 + 3 = 4
        assert csg.contains_point(create_v3(Integer(1), Rational(4), Rational(50)))
        assert not csg.contains_point(create_v3(Integer(1), Rational(5), Rational(50)))
        # Back boundary is at offset_y - total_h/2 = 1 - 3 = -2
        assert csg.contains_point(create_v3(Integer(1), Rational(-2), Rational(50)))
        assert not csg.contains_point(create_v3(Integer(1), Rational(-3), Rational(50)))


