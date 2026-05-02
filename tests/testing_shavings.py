"""
Shared test utilities and fixtures for Kumiki test suite (testing_shavings.py).

This module contains:
- Common constants (INCH_TO_METER, TOLERANCE, etc.)
- Timber factory functions (create_standard_vertical_timber, etc.)
- Assertion helpers (assert_is_valid_rotation_matrix, etc.)
- Test data generators (generate_random_orientation, etc.)
- Mock objects (MockCutting)
- Pytest fixtures
"""

import pytest
import random
import math
from typing import Optional, Tuple
from sympy import Matrix, Rational, simplify, det, eye
from kumiki.rule import *
from kumiki import *


# ============================================================================
# Constants
# ============================================================================

TOLERANCE = 1e-10  # Default tolerance for float comparisons


# ============================================================================
# Timber Factory Functions
# ============================================================================

def create_standard_vertical_timber(
    height=100,
    size: Optional[Tuple] = None,
    position: Optional[Tuple] = None,
    ticket: str = "test_timber"
) -> Timber:
    """
    Create a standard vertical timber for testing. The timber has its bottom point at the origin by default and extends upward in the +Z direction.
    The width of the timber is in the X direction and the height is in the Y direction.
    
    Args:
        height: Length of timber (default 100)
        size: (width, height) tuple (default (4, 6))
        position: (x, y, z) tuple for bottom position (default (0, 0, 0))
        ticket: Ticket for the timber
        
    Returns:
        Timber: A vertical timber extending upward in +Z direction
    """
    if size is None:
        size = (Rational(4), Rational(6))
    if position is None:
        position = (Rational(0), Rational(0), Rational(0))
    
    return timber_from_directions(
        length=Rational(height),
        size=Matrix([Rational(size[0]), Rational(size[1])]),
        bottom_position=Matrix([Rational(position[0]), Rational(position[1]), Rational(position[2])]),
        length_direction=Matrix([Rational(0), Rational(0), Rational(1)]),  # Up
        width_direction=Matrix([Rational(1), Rational(0), Rational(0)]),   # East
        ticket=ticket
    )


def create_standard_horizontal_timber(
    direction='x',
    length=100,
    size: Optional[Tuple] = None,
    position: Optional[Tuple] = None,
    ticket: str = "test_timber"
) -> Timber:
    """
    Create a standard horizontal timber for testing. The timber has its bottom point at the origin by default and extends in the `direction` direction.
    The width of the timber is in the Z axis, so a 4x6 timber has the 4 size in the Z axis and the 6 size in either the X or Y axis.
    
    Args:
        direction: 'x', 'y', '+x', '-x', '+y', '-y'
        length: Length of timber (default 100)
        size: (width, height) tuple (default (4, 6))
        position: (x, y, z) tuple for bottom position (default (0, 0, 0))
        ticket: Ticket for the timber
        
    Returns:
        Timber: A horizontal timber
    """
    if size is None:
        size = (Rational(4), Rational(6))
    if position is None:
        position = (Rational(0), Rational(0), Rational(0))
    
    # Determine length and width directions based on specified direction
    direction_map = {
        'x': (Matrix([Rational(1), Rational(0), Rational(0)]), Matrix([Rational(0), Rational(1), Rational(0)])),
        '+x': (Matrix([Rational(1), Rational(0), Rational(0)]), Matrix([Rational(0), Rational(1), Rational(0)])),
        '-x': (Matrix([Rational(-1), Rational(0), Rational(0)]), Matrix([Rational(0), Rational(1), Rational(0)])),
        'y': (Matrix([Rational(0), Rational(1), Rational(0)]), Matrix([Rational(1), Rational(0), Rational(0)])),
        '+y': (Matrix([Rational(0), Rational(1), Rational(0)]), Matrix([Rational(1), Rational(0), Rational(0)])),
        '-y': (Matrix([Rational(0), Rational(-1), Rational(0)]), Matrix([Rational(1), Rational(0), Rational(0)])),
    }
    
    length_dir, width_dir = direction_map[direction]
    
    return timber_from_directions(
        length=Rational(length),
        size=Matrix([Rational(size[0]), Rational(size[1])]),
        bottom_position=Matrix([Rational(position[0]), Rational(position[1]), Rational(position[2])]),
        length_direction=length_dir,
        width_direction=width_dir,
        ticket=ticket
    )

def create_centered_horizontal_timber(
    direction='x',
    length=100,
    size: Optional[Tuple] = None,
    zoffset = Integer(0),
    name: str = "test_timber"
) -> Timber:
    """
    Create a centered horizontal timber for testing. The timber has its bottom point at the origin by default and extends in the `direction` direction.
    The width of the timber is in the Z axis, so a 4x6 timber has the 4 size in the Z axis and the 6 size in either the X or Y axis.
    """
    
    # compute position based on direction
    if direction == 'x' or direction == '+x':
        position = (Rational(-length/2), Rational(0), Rational(zoffset))
    elif direction == 'y' or direction == '+y':
        position = (Rational(0), Rational(-length/2), Rational(zoffset))
    elif direction == '-x':
        position = (Rational(length/2), Rational(0), Rational(zoffset))
    elif direction == '-y':
        position = (Rational(0), Rational(length/2), Rational(zoffset))
    else:
        raise ValueError(f"Invalid direction: {direction}")

    return create_standard_horizontal_timber(
        direction=direction,
        length=length,
        size=size,
        position=position,
        ticket=name)

# ============================================================================
# Assertion Helpers
# ============================================================================

def assert_is_valid_rotation_matrix(matrix: Matrix, tolerance: float = TOLERANCE):
    """
    Assert that a matrix is a valid rotation matrix.
    
    Checks:
    - Determinant equals 1
    - Matrix is orthogonal (M * M^T = I)
    
    Args:
        matrix: Matrix to check
        tolerance: Tolerance for float comparisons
    """
    # Check determinant is 1
    det_val = float(simplify(det(matrix)))
    assert abs(det_val - Integer(1)) < tolerance, \
        f"Rotation matrix determinant should be 1, got {det_val}"
    
    # Check orthogonality: M * M^T = I
    product = simplify(matrix * matrix.T)
    identity = Matrix.eye(3)
    diff_norm = float((product - identity).norm())
    assert diff_norm < tolerance, \
        f"Rotation matrix should be orthogonal (M * M^T = I), norm of difference is {diff_norm}"


def assert_vectors_perpendicular(v1: Matrix, v2: Matrix, tolerance: float = TOLERANCE):
    """
    Assert that two vectors are perpendicular (dot product = 0).
    
    Args:
        v1: First vector
        v2: Second vector
        tolerance: Tolerance for float comparison
    """
    dot_product = float(simplify((v1.T * v2)[0, 0]))
    assert abs(dot_product) < tolerance, \
        f"Vectors should be perpendicular (dot product = 0), got {dot_product}"


def assert_vectors_parallel(v1: Matrix, v2: Matrix, tolerance: float = TOLERANCE):
    """
    Assert that two vectors are parallel (cross product = 0 or |dot product| = 1 for unit vectors).
    
    Args:
        v1: First vector
        v2: Second vector
        tolerance: Tolerance for float comparison
    """
    # Normalize vectors
    v1_norm = v1 / v1.norm()
    v2_norm = v2 / v2.norm()
    
    # Check if dot product is ±1
    dot_product = float(simplify((v1_norm.T * v2_norm)[0, 0]))
    assert abs(abs(dot_product) - Integer(1)) < tolerance, \
        f"Vectors should be parallel (|dot product| = 1 for normalized), got {abs(dot_product)}"


def assert_vector_normalized(v: Matrix, tolerance: float = TOLERANCE):
    """
    Assert that a vector is normalized (magnitude = 1).
    
    Args:
        v: Vector to check
        tolerance: Tolerance for float comparison
    """
    magnitude = float(v.norm())
    assert abs(magnitude - Integer(1)) < tolerance, \
        f"Vector should be normalized (magnitude = 1), got {magnitude}"


# uh this is questionable, let's keep it for now and get rid of it when,.. if casuse problems later
def assert_rational_equal(actual, expected, msg: str = ""):
    """
    Assert that two values are equal, handling both Rational and numeric types.
    
    Args:
        actual: Actual value
        expected: Expected value
        msg: Optional message to display on failure
    """
    diff = simplify(actual - expected)
    assert diff == 0, \
        f"{msg}: Expected {expected}, got {actual}" if msg else f"Expected {expected}, got {actual}"



# ============================================================================
# Test Data Generators
# ============================================================================

def generate_random_orientation() -> Orientation:
    """
    Generate a random valid rotation matrix as an Orientation.
    
    Uses the method of generating random unit quaternions and converting
    to rotation matrix to ensure we get valid rotation matrices.
    
    Returns:
        Orientation: A randomly oriented Orientation object
    """
    # Generate random unit quaternion (Shepperd's method)
    u1, u2, u3 = [random.random() for _ in range(3)]
    
    # Convert to unit quaternion components
    q0 = math.sqrt(1 - u1) * math.sin(2 * math.pi * u2)
    q1 = math.sqrt(1 - u1) * math.cos(2 * math.pi * u2)
    q2 = math.sqrt(u1) * math.sin(2 * math.pi * u3)
    q3 = math.sqrt(u1) * math.cos(2 * math.pi * u3)
    
    # Convert quaternion to rotation matrix
    matrix = [
        [1 - 2*(q2**2 + q3**2), 2*(q1*q2 - q0*q3), 2*(q1*q3 + q0*q2)],
        [2*(q1*q2 + q0*q3), 1 - 2*(q1**2 + q3**2), 2*(q2*q3 - q0*q1)],
        [2*(q1*q3 - q0*q2), 2*(q2*q3 + q0*q1), 1 - 2*(q1**2 + q2**2)]
    ]
    
    return Orientation(matrix)  # type: ignore[arg-type]


def create_test_footprint(width=4, height=3) -> Footprint:
    """
    Create a standard rectangular footprint for testing.
    
    Args:
        width: Width of footprint (x dimension)
        height: Height of footprint (y dimension)
        
    Returns:
        Footprint: A rectangular footprint with corners at (0,0), (width,0), (width,height), (0,height)
    """
    corners = [
        create_v2(0, 0),
        create_v2(width, 0),
        create_v2(width, height),
        create_v2(0, height)
    ]
    return Footprint(corners)  # type: ignore[arg-type]


# ============================================================================
# Mock Objects
# ============================================================================

class MockCutting:
    """
    Mock Cutting implementation for testing.
    
    This mock can be used in place of actual Cut objects when testing
    CutTimber functionality without needing full cut implementations.
    """
    def __init__(self, timber: Timber, end_position: V3, maybe_end_cut: Optional[TimberReferenceEnd] = None):
        """
        Initialize a mock cut.
        
        Args:
            timber: The timber this cut belongs to
            end_position: The end position of the cut
            maybe_end_cut: Optional indication of which end is being cut (for backwards compatibility)
        """
        self.timber = timber
        self._end_position = end_position
        # Convert old maybe_end_cut to new format
        if maybe_end_cut == TimberReferenceEnd.TOP:
            self.maybe_top_end_cut = True  # Mock value
            self.maybe_bottom_end_cut = None
        elif maybe_end_cut == TimberReferenceEnd.BOTTOM:
            self.maybe_top_end_cut = None
            self.maybe_bottom_end_cut = True  # Mock value
        else:
            self.maybe_top_end_cut = None
            self.maybe_bottom_end_cut = None
        self.origin = Matrix([0, 0, 0])
        self.orientation = Orientation()
        self.negative_csg = None  # Mock CSG - not actually used
    
    def get_negative_csg_local(self):
        """Get the negative CSG (not implemented for mock)."""
        return self.negative_csg


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest.fixture
def standard_vertical_timber():
    """Fixture providing a standard vertical timber."""
    return create_standard_vertical_timber()


@pytest.fixture
def standard_horizontal_timber_x():
    """Fixture providing a standard horizontal timber along X axis."""
    return create_standard_horizontal_timber(direction='x')


@pytest.fixture
def standard_horizontal_timber_y():
    """Fixture providing a standard horizontal timber along Y axis."""
    return create_standard_horizontal_timber(direction='y')


@pytest.fixture
def test_footprint():
    """Fixture providing a standard rectangular footprint."""
    return create_test_footprint()


@pytest.fixture
def identity_orientation():
    """Fixture providing an identity orientation."""
    return Orientation.identity()



@pytest.fixture
def standard_4x4_timber_size():
    """Fixture providing standard 4x4 inch timber dimensions."""
    return create_v2(inches(4), inches(4))

