"""
Tests for rule.py module.

This module contains tests for the Orientation class which represents
3D rotations using sympy matrices.
"""

import pytest
import math
import sympy as sp
from sympy import Matrix, pi, simplify, Abs, eye, det, Rational, Integer, cos, sin, sqrt
from kumiki.rule import (
    Orientation,
    Transform,
    Axis,
    inches, feet, mm, cm, m,
    shaku, sun, bu,
    INCH_TO_METER, FOOT_TO_METER, SHAKU_TO_METER,
    create_v3,
    safe_normalize_vector,
    normalize_vector,
    radians,
    is_complex_expr,
    safe_det,
    safe_simplify,
    safe_compare,
    Comparison,
    equality_test,
    safe_equality_test,
    safe_zero_test,
    degrees,
    are_vectors_perpendicular,
    giraffe_evalf,
    CollapseMode,
    giraffe_dot_product,
    giraffe_norm,
    numeric_dot_product,
    numeric_norm,
    numeric_normalize_vector,
    GIRAFFE_EVALF_PRECISION,
)
import random
from tests.testing_shavings import generate_random_orientation, assert_is_valid_rotation_matrix


class TestOrientation:
    """Test cases for the Orientation class."""
    
    def test_init_default(self):
        """Test default initialization creates identity matrix."""
        orientation = Orientation()
        expected = Matrix.eye(3)
        assert orientation.matrix == expected
    
    def test_init_with_matrix(self):
        """Test initialization with a custom matrix."""
        matrix = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
        orientation = Orientation(matrix)  # type: ignore
        assert orientation.matrix == Matrix(matrix)
    
    def test_init_invalid_shape(self):
        """Test initialization with invalid matrix shape raises error."""
        with pytest.raises(ValueError, match="Rotation matrix must be 3x3"):
            Orientation([[1, 0], [0, 1]])  # type: ignore
    
    def test_multiply_basic(self):
        """Test basic multiplication of orientations."""
        orient1 = Orientation.rotate_left()  # 90° CCW around Z
        orient2 = Orientation.rotate_left()  # Another 90° CCW around Z
        result = orient1.multiply(orient2)
        
        # Two 90° rotations should equal 180° rotation
        expected = Orientation(Matrix([[-1, 0, 0], [0, -1, 0], [0, 0, 1]]))  # 180° rotation
        assert simplify(result.matrix - expected.matrix) == Matrix.zeros(3, 3)
    
    def test_multiply_operator(self):
        """Test multiplication using * operator."""
        orient1 = Orientation.rotate_right()
        orient2 = Orientation.rotate_right()
        result1 = orient1 * orient2
        result2 = orient1.multiply(orient2)
        assert result1.matrix == result2.matrix
    
    def test_multiply_type_error(self):
        """Test multiplication with non-Orientation raises error."""
        orientation = Orientation.identity()
        with pytest.raises(TypeError, match="Can only multiply with another Orientation"):
            orientation.multiply("not an orientation")  # type: ignore
    
    def test_invert_basic(self):
        """Test basic inversion of orientations."""
        orientation = Orientation.rotate_left()
        inverted = orientation.invert()
        
        # Left rotation inverted should be right rotation
        expected = Orientation.rotate_right()
        assert simplify(inverted.matrix - expected.matrix) == Matrix.zeros(3, 3)
    
    def test_invert_identity_property(self):
        """Test that orientation * invert = identity."""
        for _ in range(5):  # Test with multiple random orientations
            orientation = generate_random_orientation()
            inverted = orientation.invert()
            result = orientation * inverted
            
            # Should be very close to identity
            identity = Matrix.eye(3)
            diff = simplify(result.matrix - identity)
            # For randomly generated orientations with float components, check that each element is close to 0
            for i in range(3):
                for j in range(3):
                    assert abs(float(diff[i, j])) < 1e-10
    
    def test_invert_double_invert(self):
        """Test that double inversion returns original."""
        orientation = generate_random_orientation()
        double_inverted = orientation.invert().invert()
        
        diff = simplify(orientation.matrix - double_inverted.matrix)
        # For randomly generated orientations with float components, check that each element is close to 0
        for i in range(3):
            for j in range(3):
                assert abs(float(diff[i, j])) < 1e-10


class TestOrientationFromVectors:
    """Test creating Orientations from direction vectors."""
    
    def test_from_z_and_y_basic(self):
        """Test from_z_and_y with basic orthogonal vectors."""
        z_dir = create_v3(0, 0, 1)  # Up
        y_dir = create_v3(0, 1, 0)  # North
        orient = Orientation.from_z_and_y(z_dir, y_dir)
        
        # Check the matrix columns are correct
        assert orient.matrix[:, 2] == z_dir  # Z column
        assert orient.matrix[:, 1] == y_dir  # Y column
        # X should be y × z = [0,1,0] × [0,0,1] = [1,0,0]
        assert orient.matrix[:, 0] == create_v3(1, 0, 0)
        assert_is_valid_rotation_matrix(orient.matrix)
    
    def test_from_z_and_x_basic(self):
        """Test from_z_and_x with basic orthogonal vectors."""
        z_dir = create_v3(0, 0, 1)  # Up
        x_dir = create_v3(1, 0, 0)  # East
        orient = Orientation.from_z_and_x(z_dir, x_dir)
        
        # Check the matrix columns are correct
        assert orient.matrix[:, 2] == z_dir  # Z column
        assert orient.matrix[:, 0] == x_dir  # X column
        # Y should be z × x = [0,0,1] × [1,0,0] = [0,1,0]
        assert orient.matrix[:, 1] == create_v3(0, 1, 0)
        assert_is_valid_rotation_matrix(orient.matrix)
    
    def test_from_x_and_y_basic(self):
        """Test from_x_and_y with basic orthogonal vectors."""
        x_dir = create_v3(1, 0, 0)  # East
        y_dir = create_v3(0, 1, 0)  # North
        orient = Orientation.from_x_and_y(x_dir, y_dir)
        
        # Check the matrix columns are correct
        assert orient.matrix[:, 0] == x_dir  # X column
        assert orient.matrix[:, 1] == y_dir  # Y column
        # Z should be x × y = [1,0,0] × [0,1,0] = [0,0,1]
        assert orient.matrix[:, 2] == create_v3(0, 0, 1)
        assert_is_valid_rotation_matrix(orient.matrix)
    
    def test_from_z_and_y_gives_identity(self):
        """Test that standard up/north vectors give identity."""
        orient = Orientation.from_z_and_y(
            create_v3(0, 0, 1),  # Z up
            create_v3(0, 1, 0)   # Y north
        )
        # This should give identity matrix
        assert orient.matrix == Matrix.eye(3)
    
    def test_from_vectors_consistency(self):
        """Test all three methods give same result for same orientation."""
        # All three should produce identity when given standard basis vectors
        orient_zy = Orientation.from_z_and_y(create_v3(0, 0, 1), create_v3(0, 1, 0))
        orient_zx = Orientation.from_z_and_x(create_v3(0, 0, 1), create_v3(1, 0, 0))
        orient_xy = Orientation.from_x_and_y(create_v3(1, 0, 0), create_v3(0, 1, 0))
        
        assert orient_zy.matrix == Matrix.eye(3)
        assert orient_zx.matrix == Matrix.eye(3)
        assert orient_xy.matrix == Matrix.eye(3)


class TestOrientationConstants:
    """Test the static orientation constants."""
    
    def test_identity_is_eye(self):
        """Test identity constant is 3x3 identity matrix."""
        assert Orientation.identity().matrix == Matrix.eye(3)
    
    def test_rotate_left_right_are_inverses(self):
        """Test rotate_left and rotate_right are inverses."""
        left = Orientation.rotate_left()
        right = Orientation.rotate_right()
        
        result = left * right
        identity = Matrix.eye(3)
        assert simplify(result.matrix - identity) == Matrix.zeros(3, 3)


class TestEulerAngles:
    """Test Euler angle functionality."""
    
    def test_from_euleryZYX_zero_angles(self):
        """Test from_euleryZYX with zero angles gives identity."""
        orientation = Orientation.from_euleryZYX(radians(0), radians(0), radians(0))
        expected = Matrix.eye(3)
        assert simplify(orientation.matrix - expected) == Matrix.zeros(3, 3)
    
    def test_from_euleryZYX_yaw_only(self):
        """Test from_euleryZYX with only yaw rotation."""
        # 90° yaw should match rotate_left
        orientation = Orientation.from_euleryZYX(radians(pi/2), radians(0), radians(0))
        expected = Orientation.rotate_left().matrix
        assert simplify(orientation.matrix - expected) == Matrix.zeros(3, 3)
    
    def test_from_euleryZYX_pitch_only(self):
        """Test from_euleryZYX with only pitch rotation."""
        orientation = Orientation.from_euleryZYX(radians(0), radians(pi/2), radians(0))
        
        # Verify it's a valid rotation matrix
        matrix = orientation.matrix
        # Check determinant is 1
        assert simplify(det(matrix)) == 1
        
        # Check orthogonality: R * R^T = I
        should_be_identity = simplify(matrix * matrix.T)
        identity = Matrix.eye(3)
        assert should_be_identity == identity
    
    def test_from_euleryZYX_roll_only(self):
        """Test from_euleryZYX with only roll rotation."""
        orientation = Orientation.from_euleryZYX(radians(0), radians(0), radians(pi/2))
        
        # Verify it's a valid rotation matrix
        matrix = orientation.matrix
        assert simplify(det(matrix)) == 1


class TestRotationMatrixProperties:
    """Test mathematical properties of rotation matrices."""
    
    def test_determinant_is_one(self):
        """Test all orientation matrices have determinant 1."""
        orientations = [
            Orientation.identity(),
            Orientation.rotate_left(), 
            generate_random_orientation()
        ]
        
        for orientation in orientations:
            assert_is_valid_rotation_matrix(orientation.matrix)
    
    def test_orthogonality(self):
        """Test all orientation matrices are orthogonal (R * R^T = I)."""
        for _ in range(3):  # Test with random orientations
            orientation = generate_random_orientation()
            matrix = orientation.matrix
            
            product = simplify(matrix * matrix.T)
            identity = Matrix.eye(3)
            
            diff = product - identity
            # For randomly generated orientations with float components, check that each element is close to 0
            for i in range(3):
                for j in range(3):
                    assert abs(float(diff[i, j])) < 1e-10
    
    def test_inverse_equals_transpose(self):
        """Test that inverse equals transpose for rotation matrices."""
        orientation = generate_random_orientation()
        
        inverse_matrix = orientation.invert().matrix
        transpose_matrix = orientation.matrix.T
        
        diff = simplify(inverse_matrix - transpose_matrix)
        # For randomly generated orientations with float components, check that each element is close to 0
        for i in range(3):
            for j in range(3):
                assert abs(float(diff[i, j])) < 1e-10


class TestTimberOrientations:
    """Test timber-specific orientation methods."""
    
    def test_facing_west_is_identity(self):
        """Test facing_west is the identity orientation."""
        orient = Orientation.facing_west()
        assert orient.matrix == Matrix.eye(3)
    
    def test_pointing_up_is_identity(self):
        """Test pointing_up has LENGTH pointing upward (+Z)."""
        orient = Orientation.pointing_up()
        # Length points up (+Z)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, 0, 1])
        # Width points north (+Y)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([0, 1, 0])
        # Facing points west (-X)
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([-1, 0, 0])
    
    def test_facing_west_directions(self):
        """Test facing_west timber directions (identity)."""
        orient = Orientation.facing_west()
        # Length along +X (local)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([1, 0, 0])
        # Width along +Y (local)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([0, 1, 0])
        # Facing +Z (up)
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([0, 0, 1])
    
    def test_facing_east_directions(self):
        """Test facing_east timber directions (180° around Z)."""
        orient = Orientation.facing_east()
        # Length along -X (local becomes +X global/east)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([-1, 0, 0])
        # Width along -Y (local becomes +Y global/north)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([0, -1, 0])
        # Facing +Z (up)
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([0, 0, 1])
    
    def test_facing_north_directions(self):
        """Test facing_north timber directions (90° CCW around Z)."""
        orient = Orientation.facing_north()
        # Length along +Y (north)  
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, 1, 0])
        # Width along -X (west)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([-1, 0, 0])
        # Facing +Z (up)
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([0, 0, 1])
    
    def test_facing_south_directions(self):
        """Test facing_south timber directions (90° CW around Z)."""
        orient = Orientation.facing_south()
        # Length along -Y (south)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, -1, 0])
        # Width along +X (east)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([1, 0, 0])
        # Facing +Z (up)
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([0, 0, 1])
    
    def test_pointing_down_directions(self):
        """Test pointing_down has LENGTH pointing downward (-Z)."""
        orient = Orientation.pointing_down()
        # Length points down (-Z)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, 0, -1])
        # Width points north (+Y)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([0, 1, 0])
        # Facing points east (+X)
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([1, 0, 0])
    
    def test_pointing_forward_directions(self):
        """Test pointing_forward: +X points to +Z, facing upward."""
        orient = Orientation.pointing_forward()
        # Length should map to +Z (up)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, 0, 1])
        # Width along +Y
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([0, 1, 0])
        # Facing direction
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([-1, 0, 0])
    
    def test_pointing_backward_directions(self):
        """Test pointing_backward: +X points to +Z, facing upward, rotated 180°."""
        orient = Orientation.pointing_backward()
        # Length should map to +Z (up)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, 0, 1])
        # Width along -Y
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([0, -1, 0])
        # Facing direction
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([1, 0, 0])
    
    def test_pointing_left_directions(self):
        """Test pointing_left: +X points to +Z, facing upward, rotated 90° CCW."""
        orient = Orientation.pointing_left()
        # Length should map to +Z (up)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, 0, 1])
        # Width along -X (west/left)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([-1, 0, 0])
        # Facing direction maps to [0,-1,0]
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([0, -1, 0])
    
    def test_pointing_right_directions(self):
        """Test pointing_right: +X points to +Z, facing upward, rotated 90° CW."""
        orient = Orientation.pointing_right()
        # Length should map to +Z (up)
        assert orient.matrix * Matrix([1, 0, 0]) == Matrix([0, 0, 1])
        # Width along +X (east/right)
        assert orient.matrix * Matrix([0, 1, 0]) == Matrix([1, 0, 0])
        # Facing direction maps to [0,1,0]
        assert orient.matrix * Matrix([0, 0, 1]) == Matrix([0, 1, 0])
    
    def test_horizontal_timbers_all_face_up(self):
        """Test that all horizontal timber orientations have facing = +Z (up)."""
        horizontal_orientations = [
            Orientation.facing_east(),
            Orientation.facing_west(),
            Orientation.facing_north(),
            Orientation.facing_south()
        ]
        
        facing_vector = Matrix([0, 0, 1])  # Original facing direction
        expected_up = Matrix([0, 0, 1])     # Should always point up
        
        for orient in horizontal_orientations:
            result = orient.matrix * facing_vector
            assert result == expected_up, f"Failed for orientation: {orient}"
    
    def test_all_pointing_verticals_length_points_up(self):
        """Test that pointing_forward/backward/left/right all have length (+X) pointing to +Z."""
        vertical_orientations = [
            Orientation.pointing_forward(),
            Orientation.pointing_backward(),
            Orientation.pointing_left(),
            Orientation.pointing_right()
        ]
        
        length_vector = Matrix([1, 0, 0])  # Length direction
        expected_up = Matrix([0, 0, 1])     # Should point up (+Z)
        
        for orient in vertical_orientations:
            result = orient.matrix * length_vector
            assert result == expected_up, f"Failed for orientation: {orient}"
    
    def test_all_timber_orientations_are_valid_rotations(self):
        """Test that all timber orientations are valid rotation matrices."""
        timber_orientations = [
            Orientation.facing_east(),
            Orientation.facing_west(),
            Orientation.facing_north(),
            Orientation.facing_south(),
            Orientation.pointing_up(),
            Orientation.pointing_down(),
            Orientation.pointing_forward(),
            Orientation.pointing_backward(),
            Orientation.pointing_left(),
            Orientation.pointing_right()
        ]
        
        for orient in timber_orientations:
            assert_is_valid_rotation_matrix(orient.matrix)
    
    def test_facing_east_is_180_from_west(self):
        """Test facing_east is 180° rotation from facing_west."""
        east = Orientation.facing_east()
        west = Orientation.facing_west()
        
        # east * east should give identity (180° + 180° = 360°)
        result = east * east
        identity = Matrix.eye(3)
        assert simplify(result.matrix - identity) == Matrix.zeros(3, 3)
    
    def test_facing_north_south_are_90_apart(self):
        """Test facing_north and facing_south are 90° rotations from west."""
        north = Orientation.facing_north()
        south = Orientation.facing_south()
        
        # north * north * north * north should be identity (4 * 90° = 360°)
        result = north * north * north * north
        identity = Matrix.eye(3)
        assert simplify(result.matrix - identity) == Matrix.zeros(3, 3)


class TestFlipOrientation:
    """Test cases for flip method."""
    
    def test_flip_no_flips(self):
        """Test flip with no flips returns the same orientation."""
        orientation = Orientation.facing_north()
        flipped = orientation.flip()
        
        # With no flips, should be identical
        assert flipped.matrix == orientation.matrix
    
    def test_flip_flip_x(self):
        """Test flip with flip_x negates the first row."""
        orientation = Orientation.identity()
        flipped = orientation.flip(flip_x=True)
        
        # Should negate first row (x-axis basis vector)
        expected = Matrix([
            [-1, 0, 0],  # First row negated
            [0, 1, 0],
            [0, 0, 1]
        ])
        assert flipped.matrix == expected
    
    def test_flip_flip_y(self):
        """Test flip with flip_y negates the first column."""
        orientation = Orientation.identity()
        flipped = orientation.flip(flip_y=True)
        
        # Should negate first column
        expected = Matrix([
            [-1, 0, 0],  # First column negated
            [0, 1, 0],
            [0, 0, 1]
        ])
        assert flipped.matrix == expected
    
    def test_flip_flip_z(self):
        """Test flip with flip_z negates the third column."""
        orientation = Orientation.identity()
        flipped = orientation.flip(flip_z=True)
        
        # Should negate third column (z-axis)
        expected = Matrix([
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, -1]  # Third column negated
        ])
        assert flipped.matrix == expected
    
    def test_flip_flip_x_and_y(self):
        """Test flip with both flip_x and flip_y."""
        orientation = Orientation.identity()
        flipped = orientation.flip(flip_x=True, flip_y=True)
        
        # Should negate first row and first column
        # For identity: flip_x negates row 0, flip_y negates column 0
        # Starting: [[1,0,0], [0,1,0], [0,0,1]]
        # After flip_x: [[-1,0,0], [0,1,0], [0,0,1]]
        # After flip_y: [[1,0,0], [0,1,0], [0,0,1]] (negates first column of the result)
        expected = Matrix([
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1]
        ])
        assert flipped.matrix == expected
    
    def test_flip_flip_all(self):
        """Test flip with all axes flipped."""
        orientation = Orientation.identity()
        flipped = orientation.flip(flip_x=True, flip_y=True, flip_z=True)
        
        # Identity after all flips
        expected = Matrix([
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, -1]
        ])
        assert flipped.matrix == expected
    
    def test_flip_non_identity(self):
        """Test flip on a non-identity orientation."""
        # Start with facing_north (90° CCW rotation around Z)
        orientation = Orientation.facing_north()
        # Matrix is [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        
        flipped = orientation.flip(flip_x=True)
        
        # Should negate first row
        expected = Matrix([
            [0, 1, 0],   # First row negated
            [1, 0, 0],
            [0, 0, 1]
        ])
        assert flipped.matrix == expected
    
    def test_flip_pointing_up(self):
        """Test flip on a vertical orientation."""
        orientation = Orientation.pointing_up()  # Length points +Z
        flipped = orientation.flip(flip_z=True)
        
        # Should negate third column (Facing direction)
        # pointing_up is [[0,0,-1], [0,1,0], [1,0,0]]
        # After flipping Z: [[0,0,1], [0,1,0], [1,0,0]]
        expected = Matrix([
            [0, 0, 1],
            [0, 1, 0],
            [1, 0, 0]
        ])
        assert flipped.matrix == expected
    
    def test_flip_double_flip_x(self):
        """Test that flipping X twice returns the original."""
        orientation = Orientation.facing_north()
        flipped_once = orientation.flip(flip_x=True)
        flipped_twice = flipped_once.flip(flip_x=True)
        
        # Double flip should return to original
        assert flipped_twice.matrix == orientation.matrix
    
    def test_flip_double_flip_y(self):
        """Test that flipping Y twice returns the original."""
        orientation = Orientation.facing_east()
        flipped_once = orientation.flip(flip_y=True)
        flipped_twice = flipped_once.flip(flip_y=True)
        
        # Double flip should return to original
        assert flipped_twice.matrix == orientation.matrix
    
    def test_flip_double_flip_z(self):
        """Test that flipping Z twice returns the original."""
        orientation = Orientation.facing_south()
        flipped_once = orientation.flip(flip_z=True)
        flipped_twice = flipped_once.flip(flip_z=True)
        
        # Double flip should return to original
        assert flipped_twice.matrix == orientation.matrix
    
    def test_flip_with_random_orientation(self):
        """Test flip preserves orientation properties on random matrices."""
        orientation = generate_random_orientation()
        flipped = orientation.flip(flip_x=True, flip_z=True)
        
        # The flipped matrix should still be a valid rotation matrix
        # Note: flipping may change determinant, so we just verify it's orthogonal
        matrix = flipped.matrix
        product = simplify(matrix * matrix.T)
        identity = Matrix.eye(3)
        
        diff = product - identity
        # Check orthogonality
        for i in range(3):
            for j in range(3):
                assert abs(float(diff[i, j])) < 1e-10
    
    def test_flip_immutability(self):
        """Test that flip doesn't modify the original orientation."""
        orientation = Orientation.facing_north()
        original_matrix = orientation.matrix.copy()
        
        # Call flip
        flipped = orientation.flip(flip_x=True, flip_y=True, flip_z=True)
        
        # Original should be unchanged
        assert orientation.matrix == original_matrix
        # Flipped should be different
        assert flipped.matrix != original_matrix


class TestReprAndString:
    """Test string representation."""
    
    def test_repr_contains_matrix(self):
        """Test __repr__ contains the matrix."""
        orientation = Orientation.identity()
        repr_str = repr(orientation)
        
        assert "Orientation(" in repr_str
        assert "Matrix(" in repr_str
        assert "1" in repr_str  # Should contain identity matrix elements 


class TestDimensionalHelpers:
    """Test dimensional helper functions."""
    
    def test_inches_integer(self):
        """Test inches with integer input."""
        result = inches(1)
        expected = Rational(1) * INCH_TO_METER
        assert result == expected
    
    def test_inches_fraction(self):
        """Test inches with fractional input (1/32 inch)."""
        result = inches(1, 32)
        expected = Rational(1, 32) * INCH_TO_METER
        assert result == expected
    
    def test_inches_float(self):
        """Test inches with float input (converts to Rational)."""
        result = inches(3.5)
        expected = Rational(7, 2) * INCH_TO_METER
        assert result == expected
    
    def test_inches_string(self):
        """Test inches with string input."""
        result = inches("1.5")
        expected = Rational(3, 2) * INCH_TO_METER
        assert result == expected
    
    def test_inches_fraction_string(self):
        """Test inches with fraction string."""
        result = inches("1/32")
        expected = Rational(1, 32) * INCH_TO_METER
        assert result == expected
    
    def test_feet_integer(self):
        """Test feet with integer input."""
        result = feet(8)
        expected = Rational(8) * FOOT_TO_METER
        assert result == expected
    
    def test_feet_fraction(self):
        """Test feet with fractional input."""
        result = feet(1, 2)
        expected = Rational(1, 2) * FOOT_TO_METER
        assert result == expected
    
    def test_feet_float(self):
        """Test feet with float input."""
        result = feet(6.5)
        expected = Rational(13, 2) * FOOT_TO_METER
        assert result == expected
    
    def test_mm_integer(self):
        """Test millimeters with integer input."""
        result = mm(90)
        expected = Rational(90, 1000)
        assert result == expected
    
    def test_mm_fraction(self):
        """Test millimeters with fractional input."""
        result = mm(1, 2)
        expected = Rational(1, 2000)
        assert result == expected
    
    def test_mm_float(self):
        """Test millimeters with Rational input for exact comparison."""
        # Use exact Rational instead of float to avoid binary representation issues
        result = mm(Rational(254, 10))  # Exactly 25.4mm
        # Float conversion creates exact Rational from binary representation
        assert isinstance(result, Rational)
        # Check it equals exactly 1 inch
        expected = inches(1)
        assert result == expected
    
    def test_cm_integer(self):
        """Test centimeters with integer input."""
        result = cm(9)
        expected = Rational(9, 100)
        assert result == expected
    
    def test_cm_fraction(self):
        """Test centimeters with fractional input."""
        result = cm(1, 2)
        expected = Rational(1, 200)
        assert result == expected
    
    def test_m_integer(self):
        """Test meters with integer input."""
        result = m(1)
        expected = Rational(1)
        assert result == expected
    
    def test_m_fraction(self):
        """Test meters with fractional input."""
        result = m(1, 2)
        expected = Rational(1, 2)
        assert result == expected
    
    def test_m_float(self):
        """Test meters with float input."""
        result = m(2.5)
        expected = Rational(5, 2)
        assert result == expected
    
    def test_shaku_integer(self):
        """Test shaku with integer input."""
        result = shaku(1)
        expected = Rational(1) * SHAKU_TO_METER
        assert result == expected
    
    def test_shaku_fraction(self):
        """Test shaku with fractional input."""
        result = shaku(3, 2)
        expected = Rational(3, 2) * SHAKU_TO_METER
        assert result == expected
    
    def test_shaku_float(self):
        """Test shaku with float input."""
        result = shaku(2.5)
        expected = Rational(5, 2) * SHAKU_TO_METER
        assert result == expected
    
    def test_sun_integer(self):
        """Test sun with integer input (1 sun = 1/10 shaku)."""
        result = sun(1)
        expected = SHAKU_TO_METER / 10
        assert result == expected
    
    def test_sun_fraction(self):
        """Test sun with fractional input."""
        result = sun(1, 2)
        expected = Rational(1, 2) * SHAKU_TO_METER / 10
        assert result == expected
    
    def test_sun_multiple(self):
        """Test that 10 sun equals 1 shaku."""
        result_sun = sun(10)
        result_shaku = shaku(1)
        assert result_sun == result_shaku
    
    def test_bu_integer(self):
        """Test bu with integer input (1 bu = 1/100 shaku)."""
        result = bu(1)
        expected = SHAKU_TO_METER / 100
        assert result == expected
    
    def test_bu_fraction(self):
        """Test bu with fractional input."""
        result = bu(1, 2)
        expected = Rational(1, 2) * SHAKU_TO_METER / 100
        assert result == expected
    
    def test_bu_multiple(self):
        """Test that 10 bu equals 1 sun and 100 bu equals 1 shaku."""
        result_10bu = bu(10)
        result_1sun = sun(1)
        result_100bu = bu(100)
        result_1shaku = shaku(1)
        assert result_10bu == result_1sun
        assert result_100bu == result_1shaku
    
    def test_all_return_rational(self):
        """Test that all helper functions return Rational types."""
        # Test with integer inputs
        assert isinstance(inches(1), Rational)
        assert isinstance(feet(1), Rational)
        assert isinstance(mm(1), Rational)
        assert isinstance(cm(1), Rational)
        assert isinstance(m(1), Rational)
        assert isinstance(shaku(1), Rational)
        assert isinstance(sun(1), Rational)
        assert isinstance(bu(1), Rational)
        
        # Test with float inputs (should convert to Rational)
        assert isinstance(inches(1.5), Rational)
        assert isinstance(feet(6.5), Rational)
        assert isinstance(mm(25.4), Rational)
    
    def test_conversion_consistency(self):
        """Test that 1 inch equals 25.4 mm exactly."""
        result_inch = inches(1)
        result_mm = mm(Rational(254, 10))  # 25.4 mm
        assert result_inch == result_mm
    
    def test_practical_example_imperial(self):
        """Test a practical carpentry example with imperial units."""
        # 2x4 nominal dimensions (actual: 1.5" x 3.5")
        width = inches(3, 2)  # 1.5 inches
        height = inches(7, 2)  # 3.5 inches
        
        # Verify they're Rational
        assert isinstance(width, Rational)
        assert isinstance(height, Rational)
        
        # Verify exact metric values
        assert width == Rational(381, 10000)  # Exactly 38.1mm
        assert height == Rational(889, 10000)  # Exactly 88.9mm
    
    def test_practical_example_metric(self):
        """Test a practical carpentry example with metric units."""
        # Common timber: 90mm x 90mm
        width = mm(90)
        height = mm(90)
        
        assert isinstance(width, Rational)
        assert isinstance(height, Rational)
        assert width == Rational(9, 100)  # 0.09 meters
    
    def test_practical_example_japanese(self):
        """Test a practical carpentry example with Japanese traditional units."""
        # Common post: 4 sun x 4 sun (approximately 120mm x 120mm)
        width = sun(4)
        height = sun(4)
        
        assert isinstance(width, Rational)
        assert isinstance(height, Rational)
        
        # Verify they're equal and exact
        assert width == height
        assert width == Rational(4) * SHAKU_TO_METER / 10


class TestTransformRotateAroundAxis:
    """Test cases for the Transform.rotate_around_axis method."""
    
    def test_rotate_around_z_axis_through_origin_90_degrees(self):
        """Test rotation around Z axis through origin by 90 degrees."""
        # Create a transform at (1, 0, 0) with identity orientation
        transform = Transform(
            position=create_v3(Integer(1), Integer(0), Integer(0)),
            orientation=Orientation.identity()
        )
        
        # Create Z axis through origin
        z_axis = Axis(
            position=create_v3(Integer(0), Integer(0), Integer(0)),
            direction=create_v3(Integer(0), Integer(0), Integer(1))
        )
        
        # Rotate 90 degrees counterclockwise around Z axis
        rotated = transform.rotate_around_axis(z_axis, radians(pi / 2))
        
        # Position should move from (1, 0, 0) to (0, 1, 0)
        expected_pos = create_v3(Integer(0), Integer(1), Integer(0))
        diff = simplify(rotated.position - expected_pos)
        for i in range(3):
            assert abs(float(diff[i])) < 1e-10, f"Position mismatch at index {i}"
        
        # Orientation should be rotated by 90 degrees around Z
        expected_orient = Orientation.rotate_left()
        diff_orient = simplify(rotated.orientation.matrix - expected_orient.matrix)
        for i in range(3):
            for j in range(3):
                assert abs(float(diff_orient[i, j])) < 1e-10
    
    def test_rotate_around_x_axis_through_origin_180_degrees(self):
        """Test rotation around X axis through origin by 180 degrees."""
        # Create a transform at (0, 1, 0) with identity orientation
        transform = Transform(
            position=create_v3(Integer(0), Integer(1), Integer(0)),
            orientation=Orientation.identity()
        )
        
        # Create X axis through origin
        x_axis = Axis(
            position=create_v3(Integer(0), Integer(0), Integer(0)),
            direction=create_v3(Integer(1), Integer(0), Integer(0))
        )
        
        # Rotate 180 degrees around X axis
        rotated = transform.rotate_around_axis(x_axis, radians(pi))
        
        # Position should move from (0, 1, 0) to (0, -1, 0)
        expected_pos = create_v3(Integer(0), Integer(-1), Integer(0))
        diff = simplify(rotated.position - expected_pos)
        for i in range(3):
            assert abs(float(diff[i])) < 1e-10
        
        # Orientation should be rotated by 180 degrees around X
        expected_matrix = Matrix([
            [Integer(1), Integer(0), Integer(0)],
            [Integer(0), Integer(-1), Integer(0)],
            [Integer(0), Integer(0), Integer(-1)]
        ])
        expected_orient = Orientation(expected_matrix)
        diff_orient = simplify(rotated.orientation.matrix - expected_orient.matrix)
        for i in range(3):
            for j in range(3):
                assert abs(float(diff_orient[i, j])) < 1e-10
    
    def test_rotate_around_offset_z_axis(self):
        """Test rotation around Z axis NOT through origin."""
        # Create a transform at (2, 0, 0)
        transform = Transform(
            position=create_v3(Integer(2), Integer(0), Integer(0)),
            orientation=Orientation.identity()
        )
        
        # Create Z axis through (1, 0, 0) - offset from origin
        z_axis = Axis(
            position=create_v3(Integer(1), Integer(0), Integer(0)),
            direction=create_v3(Integer(0), Integer(0), Integer(1))
        )
        
        # Rotate 90 degrees counterclockwise
        # Point (2, 0, 0) is distance 1 from axis at (1, 0, 0)
        # After rotation, should be at (1, 1, 0)
        rotated = transform.rotate_around_axis(z_axis, radians(pi / 2))
        
        expected_pos = create_v3(Integer(1), Integer(1), Integer(0))
        diff = simplify(rotated.position - expected_pos)
        for i in range(3):
            assert abs(float(diff[i])) < 1e-10
    
    def test_rotate_around_offset_y_axis(self):
        """Test rotation around Y axis offset from origin."""
        # Create a transform at (1, 0, 0)
        transform = Transform(
            position=create_v3(Integer(1), Integer(0), Integer(0)),
            orientation=Orientation.identity()
        )
        
        # Create Y axis through (1, 0, 0) - axis passes through the point
        y_axis = Axis(
            position=create_v3(Integer(1), Integer(0), Integer(0)),
            direction=create_v3(Integer(0), Integer(1), Integer(0))
        )
        
        # Rotate 90 degrees - point is ON the axis, so should not move
        rotated = transform.rotate_around_axis(y_axis, radians(pi / 2))
        
        # Position should stay at (1, 0, 0)
        expected_pos = create_v3(Integer(1), Integer(0), Integer(0))
        diff = simplify(rotated.position - expected_pos)
        for i in range(3):
            assert abs(float(diff[i])) < 1e-10
    
    def test_rotate_zero_angle(self):
        """Test that rotation by 0 degrees returns unchanged transform."""
        transform = Transform(
            position=create_v3(Integer(1), Integer(2), Integer(3)),
            orientation=Orientation.rotate_left()
        )
        
        axis = Axis(
            position=create_v3(Integer(5), Integer(6), Integer(7)),
            direction=create_v3(Integer(0), Integer(0), Integer(1))
        )
        
        # Rotate by 0 degrees
        rotated = transform.rotate_around_axis(axis, radians(Integer(0)))
        
        # Should be essentially unchanged
        pos_diff = simplify(rotated.position - transform.position)
        for i in range(3):
            assert abs(float(pos_diff[i])) < 1e-10
        
        orient_diff = simplify(rotated.orientation.matrix - transform.orientation.matrix)
        for i in range(3):
            for j in range(3):
                assert abs(float(orient_diff[i, j])) < 1e-10
    
    def test_rotate_arbitrary_axis_preserves_distance(self):
        """Test rotation around arbitrary axis preserves distance from axis."""
        # Point at (2, 0, 0)
        transform = Transform(
            position=create_v3(Integer(2), Integer(0), Integer(0)),
            orientation=Orientation.identity()
        )
        
        # Axis through (1, 1, 1) in direction (1, 1, 1)
        axis = Axis(
            position=create_v3(Integer(1), Integer(1), Integer(1)),
            direction=create_v3(Integer(1), Integer(1), Integer(1))
        )
        
        # Rotate by 120 degrees
        rotated = transform.rotate_around_axis(axis, radians(2 * pi / 3))
        
        # Calculate distance from point to axis before and after rotation
        # Distance from point P to axis through Q with direction D:
        # dist = ||(P - Q) - ((P - Q) · D̂)D̂||
        
        def distance_to_axis(point, axis_pos, axis_dir):
            axis_normalized = normalize_vector(axis_dir)
            point_to_axis_pos = point - axis_pos
            projection_length = sum(point_to_axis_pos[i] * axis_normalized[i] for i in range(3))
            projection = axis_normalized * projection_length
            perpendicular = point_to_axis_pos - projection
            dist_sq = sum(perpendicular[i]**2 for i in range(3))
            return simplify(dist_sq)
        
        dist_before = distance_to_axis(transform.position, axis.position, axis.direction)
        dist_after = distance_to_axis(rotated.position, axis.position, axis.direction)
        
        dist_diff = simplify(dist_after - dist_before)
        assert abs(float(dist_diff)) < 1e-9, "Rotation should preserve distance from axis"
    
    def test_rotate_with_non_unit_axis_direction(self):
        """Test that non-unit axis directions are normalized correctly."""
        # Use a non-unit axis direction (2, 0, 0) which should behave same as (1, 0, 0)
        transform = Transform(
            position=create_v3(Integer(0), Integer(1), Integer(0)),
            orientation=Orientation.identity()
        )
        
        axis = Axis(
            position=create_v3(Integer(0), Integer(0), Integer(0)),
            direction=create_v3(Integer(2), Integer(0), Integer(0))
        )
        
        # Rotate 90 degrees around (2, 0, 0) - should be same as rotating around (1, 0, 0)
        rotated = transform.rotate_around_axis(axis, radians(pi / 2))
        
        # Position should move from (0, 1, 0) to (0, 0, 1)
        expected_pos = create_v3(Integer(0), Integer(0), Integer(1))
        diff = simplify(rotated.position - expected_pos)
        for i in range(3):
            assert abs(float(diff[i])) < 1e-10
    
    def test_rotate_composed_orientation(self):
        """Test rotation of a transform that already has a non-identity orientation."""
        # Start with a transform that's already rotated
        initial_orientation = Orientation.rotate_left()  # 90° around Z
        transform = Transform(
            position=create_v3(Integer(0), Integer(1), Integer(0)),
            orientation=initial_orientation
        )
        
        axis = Axis(
            position=create_v3(Integer(0), Integer(0), Integer(0)),
            direction=create_v3(Integer(0), Integer(0), Integer(1))
        )
        
        # Rotate 90° around Z again
        rotated = transform.rotate_around_axis(axis, radians(pi / 2))
        
        # Position should move from (0, 1, 0) to (-1, 0, 0)
        expected_pos = create_v3(Integer(-1), Integer(0), Integer(0))
        diff = simplify(rotated.position - expected_pos)
        for i in range(3):
            assert abs(float(diff[i])) < 1e-10
        
        # Orientation should be 180° around Z (two 90° rotations)
        expected_matrix = Matrix([
            [Integer(-1), Integer(0), Integer(0)],
            [Integer(0), Integer(-1), Integer(0)],
            [Integer(0), Integer(0), Integer(1)]
        ])
        expected_orient = Orientation(expected_matrix)
        diff_orient = simplify(rotated.orientation.matrix - expected_orient.matrix)
        for i in range(3):
            for j in range(3):
                assert abs(float(diff_orient[i, j])) < 1e-10
    
    def test_rotate_full_circle(self):
        """Test that rotating 360 degrees returns to original (approximately)."""
        transform = Transform(
            position=create_v3(Integer(1), Integer(2), Integer(3)),
            orientation=Orientation.rotate_left()
        )
        
        axis = Axis(
            position=create_v3(Integer(0), Integer(1), Integer(0)),
            direction=create_v3(Integer(0), Integer(1), Integer(0))
        )
        
        # Rotate full circle (2*pi radians)
        rotated = transform.rotate_around_axis(axis, radians(2 * pi))
        
        # Should be back to original position and orientation (within numerical precision)
        pos_diff = simplify(rotated.position - transform.position)
        for i in range(3):
            assert abs(float(pos_diff[i])) < 1e-9
        
        orient_diff = simplify(rotated.orientation.matrix - transform.orientation.matrix)
        for i in range(3):
            for j in range(3):
                assert abs(float(orient_diff[i, j])) < 1e-9
    
    def test_rotate_orientation_matrix_stays_valid(self):
        """Test that the rotated orientation matrix remains a valid rotation matrix."""
        transform = Transform(
            position=create_v3(Integer(1), Integer(2), Integer(3)),
            orientation=Orientation.rotate_left()
        )
        
        axis = Axis(
            position=create_v3(Integer(2), Integer(3), Integer(4)),
            direction=create_v3(Integer(1), Integer(1), Integer(1))
        )
        
        # Rotate by some arbitrary angle
        rotated = transform.rotate_around_axis(axis, radians(pi / 7))
        
        # Check that the resulting orientation is a valid rotation matrix
        assert_is_valid_rotation_matrix(rotated.orientation.matrix)


# =============================================================================
# Simple tests for previously uncovered rule.py functions (one test per method)
# =============================================================================

class TestIsComplexExpr:
    def test_simple_rational_is_not_complex(self):
        assert is_complex_expr(Rational(1, 2)) is False


class TestGiraffeEvalf:
    def test_evaluates_rational(self):
        result = giraffe_evalf(Rational(1, 3))
        assert isinstance(result, sp.Float)
        assert abs(float(result) - 1/3) < 10**(-GIRAFFE_EVALF_PRECISION + 2)

    def test_evaluates_sqrt(self):
        result = giraffe_evalf(sqrt(2))
        assert abs(float(result) - 1.41421356237) < 1e-8

    def test_evaluates_plain_int(self):
        result = giraffe_evalf(Integer(42))
        assert float(result) == 42.0


class TestCollapseMode:
    def test_smart_preserves_simple_in_symbolic_mode(self, symbolic_mode):
        from kumiki.rule import _collapse_scalar
        expr = Rational(1, 2)
        result = _collapse_scalar(expr, CollapseMode.SMART)
        assert result == Rational(1, 2)

    def test_always_collapses_simple(self):
        from kumiki.rule import _collapse_scalar
        expr = Rational(1, 2)
        result = _collapse_scalar(expr, CollapseMode.ALWAYS)
        assert isinstance(result, sp.Float)

    def test_never_preserves_complex(self):
        from kumiki.rule import _collapse_scalar
        # sin(1) is flagged as complex by is_complex_expr
        expr = sin(Integer(1)) + cos(Integer(2))
        result = _collapse_scalar(expr, CollapseMode.NEVER)
        assert result is expr  # unchanged


class TestNumericWrappers:
    def test_numeric_dot_product_returns_float(self):
        v1 = create_v3(1, 0, 0)
        v2 = create_v3(0, 1, 0)
        result = numeric_dot_product(v1, v2)
        assert isinstance(result, sp.Float)

    def test_numeric_norm_returns_float(self):
        v = create_v3(3, 4, 0)
        result = numeric_norm(v)
        assert isinstance(result, sp.Float)
        assert abs(float(result) - 5.0) < 1e-10

    def test_numeric_normalize_returns_float_elements(self):
        v = create_v3(3, 4, 0)
        result = numeric_normalize_vector(v)
        for elem in result:
            assert isinstance(elem, (sp.Float, sp.Rational))
        # Should be unit vector
        assert abs(float(result[0]) - 0.6) < 1e-10
        assert abs(float(result[1]) - 0.8) < 1e-10


class TestGiraffeDotProduct:
    def test_orthogonal_is_zero(self, symbolic_mode):
        v1 = create_v3(1, 0, 0)
        v2 = create_v3(0, 1, 0)
        result = giraffe_dot_product(v1, v2, CollapseMode.NEVER)
        assert result == 0

    def test_parallel_unit_is_one(self, symbolic_mode):
        v = create_v3(1, 0, 0)
        result = giraffe_dot_product(v, v, CollapseMode.NEVER)
        assert result == 1


class TestSafeDet:
    def test_det_identity_is_one(self):
        M = Matrix.eye(3)
        assert safe_det(M) == 1


class TestSafeSimplify:
    def test_simplify_leaves_rational_unchanged(self):
        x = Rational(1, 2) + Rational(1, 3)
        assert safe_simplify(x) == Rational(5, 6)


class TestSafeCompare:
    def test_gt_positive(self):
        assert safe_compare(Rational(1, 2), 0, Comparison.GT) == True

    def test_two_arg_equality(self):
        assert safe_compare(Rational(1, 2), Rational(1, 2), Comparison.EQ) == True

    def test_two_arg_gt(self):
        assert safe_compare(Rational(3, 4), Rational(1, 4), Comparison.GT) == True


class TestSafeEqualityTest:
    def test_equal_rationals(self):
        assert safe_equality_test(Rational(1, 2), Rational(1, 2)) == True

    def test_zero_test(self):
        assert safe_zero_test(Integer(0)) == True
        assert safe_zero_test(Rational(1, 2)) == False


class TestEqualityTest:
    def test_equal_rationals(self):
        assert equality_test(Rational(1, 2), Rational(1, 2)) == True


class TestDegrees:
    def test_90_degrees_to_radians(self):
        assert degrees(90) == pi / 2


class TestAreVectorsPerpendicular:
    def test_orthogonal_vectors(self):
        v1 = create_v3(1, 0, 0)
        v2 = create_v3(0, 1, 0)
        assert are_vectors_perpendicular(v1, v2) == True


class TestTransformMul:
    def test_identity_times_identity(self, symbolic_mode):
        T = Transform(position=create_v3(0, 0, 0), orientation=Orientation.identity())
        result = T * T
        assert result.position == create_v3(0, 0, 0)
        assert result.orientation.matrix == Matrix.eye(3)


class TestTransformInvert:
    def test_invert_identity_is_identity(self):
        T = Transform(position=create_v3(0, 0, 0), orientation=Orientation.identity())
        inv = T.invert()
        assert inv.position == create_v3(0, 0, 0)
        assert inv.orientation.matrix == Matrix.eye(3)


class TestTransformToGlobalTransform:
    def test_to_global_with_identity_parent(self, symbolic_mode):
        T = Transform(position=create_v3(1, 2, 3), orientation=Orientation.identity())
        parent = Transform(position=create_v3(0, 0, 0), orientation=Orientation.identity())
        global_t = T.to_global_transform(parent)
        assert global_t.position == T.position
        assert global_t.orientation.matrix == T.orientation.matrix


class TestTransformToLocalTransform:
    def test_to_local_with_identity_parent(self, symbolic_mode):
        T = Transform(position=create_v3(1, 2, 3), orientation=Orientation.identity())
        parent = Transform(position=create_v3(0, 0, 0), orientation=Orientation.identity())
        local_t = T.to_local_transform(parent)
        assert local_t.position == T.position
        assert local_t.orientation.matrix == T.orientation.matrix