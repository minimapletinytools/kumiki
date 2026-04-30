"""
Tests for rendering utilities shared across all rendering backends.
"""

import pytest
from sympy import Matrix, Rational, Integer
from kumiki.timber import timber_from_directions, create_v2, create_v3, CutTimber
from kumiki.rule import Orientation
from kumiki.rendering_utils import (
    sympy_to_float,
    matrix_to_floats,
    extract_rotation_matrix_columns,
    calculate_timber_corners,
    calculate_structure_extents
)
from tests.testing_shavings import create_standard_vertical_timber, create_standard_horizontal_timber


def test_sympy_to_float():
    """Test conversion of SymPy expressions to floats."""
    # Test with Rational
    assert sympy_to_float(Rational(1, 2)) == 0.5
    
    # Test with Integer
    assert sympy_to_float(Integer(42)) == 42.0
    
    # Test with float
    assert sympy_to_float(3.14) == 3.14
    
    # Test with int
    assert sympy_to_float(7) == 7.0


def test_matrix_to_floats():
    """Test conversion of SymPy matrix to list of floats."""
    matrix = Matrix([
        [Rational(1, 2), Rational(3, 4)],
        [Integer(1), Integer(2)]
    ])
    
    result = matrix_to_floats(matrix)
    
    assert len(result) == 4
    assert result[0] == 0.5
    assert result[1] == 0.75
    assert result[2] == 1.0
    assert result[3] == 2.0


def test_extract_rotation_matrix_columns():
    """Test extraction of rotation matrix columns."""
    # Create identity orientation
    orientation = Orientation.identity()
    
    width_dir, height_dir, length_dir = extract_rotation_matrix_columns(orientation)
    
    # Check dimensions
    assert width_dir.shape == (3, 1)
    assert height_dir.shape == (3, 1)
    assert length_dir.shape == (3, 1)
    
    # Check values for identity matrix
    assert width_dir == Matrix([1, 0, 0])
    assert height_dir == Matrix([0, 1, 0])
    assert length_dir == Matrix([0, 0, 1])


def test_calculate_timber_corners():
    """Test calculation of timber corner positions."""
    # Create a simple timber
    timber = timber_from_directions(
        length=Rational(100, 1),
        size=create_v2(Rational(10, 1), Rational(10, 1)),
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0)
    )
    
    corners = calculate_timber_corners(timber)
    
    # Should have 8 corners
    assert len(corners) == 8
    
    # All corners should be 3D vectors
    for corner in corners:
        assert corner.shape == (3, 1)
    
    # Check that corners span the expected range
    # Width: -5 to 5, Height: -5 to 5, Length: 0 to 100
    x_coords = [float(c[0]) for c in corners]
    y_coords = [float(c[1]) for c in corners]
    z_coords = [float(c[2]) for c in corners]
    
    assert min(x_coords) == -5.0
    assert max(x_coords) == 5.0
    assert min(y_coords) == -5.0
    assert max(y_coords) == 5.0
    assert min(z_coords) == 0.0
    assert max(z_coords) == 100.0


def test_calculate_structure_extents_empty():
    """Test structure extents calculation with empty list."""
    extent = calculate_structure_extents([])
    assert extent == 1000.0  # Default value


def test_calculate_structure_extents_single_timber():
    """Test structure extents calculation with single timber."""
    timber = timber_from_directions(
        length=Rational(100, 1),
        size=create_v2(Rational(10, 1), Rational(10, 1)),
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0)
    )
    
    cut_timber = CutTimber(timber)
    extent = calculate_structure_extents([cut_timber])
    
    # Extent should be half of the maximum dimension
    # Timber spans: X: -5 to 5 (10), Y: -5 to 5 (10), Z: 0 to 100 (100)
    # Maximum dimension is 100, so extent should be 50
    assert extent == 50.0


def test_calculate_structure_extents_multiple_timbers():
    """Test structure extents calculation with multiple timbers."""
    # Create two timbers at different positions
    timber1 = timber_from_directions(
        length=Rational(100, 1),
        size=create_v2(Rational(10, 1), Rational(10, 1)),
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(1, 0, 0),
        width_direction=create_v3(0, 1, 0)
    )
    
    timber2 = timber_from_directions(
        length=Rational(50, 1),
        size=create_v2(Rational(10, 1), Rational(10, 1)),
        bottom_position=create_v3(50, 0, 0),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0)
    )
    
    cut_timbers = [CutTimber(timber1), CutTimber(timber2)]
    extent = calculate_structure_extents(cut_timbers)
    
    # Timber1 spans X: 0 to 100, Y: -5 to 5, Z: -5 to 5
    # Timber2 spans X: 45 to 55, Y: -5 to 5, Z: 0 to 50
    # Overall: X: 0 to 100 (100), Y: -5 to 5 (10), Z: -5 to 50 (55)
    # Maximum dimension is 100, so extent should be 50
    assert extent == 50.0


def test_calculate_structure_extents_with_offsets():
    """Test structure extents with timbers at various positions."""
    # Create a timber far from origin
    timber = timber_from_directions(
        length=Rational(20, 1),
        size=create_v2(Rational(5, 1), Rational(5, 1)),
        bottom_position=create_v3(100, 100, 100),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0)
    )
    
    cut_timber = CutTimber(timber)
    extent = calculate_structure_extents([cut_timber])
    
    # Timber spans: X: 97.5 to 102.5 (5), Y: 97.5 to 102.5 (5), Z: 100 to 120 (20)
    # Center is at approximately (100, 100, 110)
    # Extents from center: X: 2.5, Y: 2.5, Z: 10
    # Maximum extent is 10
    assert extent == 10.0

