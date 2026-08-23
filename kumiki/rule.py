'''
The library uses RHS coordinates with Z facing up, Y facing north, and X facing east.
The main class is the Orientation class which stores rotation in 2 components.

Coordinate System (RHS):

(up) Z
     ^  ^ Y (north)
     | /
     |/
     +-----> X (east)
    /
   /
  v
-Y (south)

RHS = Right Hand System
- X-axis: points east
- Y-axis: points north
- Z-axis: points up
- Thumb = X, Index = Y, Middle = Z


All numeric values in this library are plain Python floats. Users declare
measurements with the helpers below (`scalar`, `inches`, `mm`, `degrees`, ...)
for convenience and unit-conversion, but the values themselves are ordinary
floats -- there is no lazy/symbolic expression tree, and no separate
"numeric mode" to switch between.
'''

import math
import numpy as np
from typing import Optional, Union, List, Tuple
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# Scalar constructors
# ============================================================================


def scalar(numerator, denominator=1) -> float:
    """
    Create a float scalar value.

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value

    Examples:
        scalar(3)             # 3.0
        scalar(1, 2)          # 0.5
        scalar(2.5)           # 2.5
        scalar("1.5")         # 1.5 from string
        scalar("1/32")        # Parses fraction string
    """
    if isinstance(numerator, str):
        text = numerator.strip()
        if "/" in text:
            num_str, den_str = text.split("/", 1)
            value = float(num_str) / float(den_str)
        else:
            value = float(text)
    else:
        value = float(numerator)
    return value / denominator if denominator != 1 else value


# ============================================================================
# sympy-compatibility shims
#
# These exist so files that used to do `from sympy import X` can instead do
# `from kumiki.rule import X` with an otherwise-unchanged import list. Real
# symbolic/arbitrary-precision behavior is gone -- these are plain float/math
# equivalents. `Rational` is deliberately NOT provided here: it was used both
# as a 2-arg exact-fraction constructor (now `scalar`) and as an isinstance
# target (now `float`), which can't share one name.
# ============================================================================

Expr = float
Float = float
Integer = int
S = float
sympify = float
oo = math.inf

Abs = abs
Min = min
Max = max
pi = math.pi


def sin(x):
    return math.sin(x)


def cos(x):
    return math.cos(x)


def tan(x):
    return math.tan(x)


def atan(x):
    return math.atan(x)


def atan2(y, x):
    return math.atan2(y, x)


def acos(x):
    return math.acos(x)


def sqrt(x):
    # Tolerate tiny float noise around zero (e.g. two squares that should be
    # exactly equal, now computed with float rounding) without masking real
    # negative-argument bugs further away from zero.
    if -EPSILON_GENERIC < x < 0:
        return 0.0
    return math.sqrt(x)


def simplify(expr):
    """No-op: floats need no symbolic simplification. Kept so old call sites
    (mostly `simplify(a - b) == 0`-style exactness checks) still parse; see
    `safe_equality_test`/`safe_zero_test` for the epsilon-based replacement."""
    return expr


# ============================================================================
# Type Aliases
# ============================================================================

# Numeric leaf values are plain floats (ints are accepted for convenience and
# coerce naturally through arithmetic).
Numeric = Union[float, int]


# ============================================================================
# Matrix -- thin numpy-backed replacement for sympy.Matrix
#
# Duck-types exactly the subset of sympy.Matrix's API used across this
# codebase: nested/flat-list construction, (i, j)/slice indexing, matrix
# multiplication via `*` (not elementwise, unlike raw numpy), elementwise
# +/-/negation, `.T`, `.shape`, `.rows`/`.cols`, `.dot`, `.cross`, `.det`,
# `.copy`, and the `Matrix.eye`/`Matrix.zeros` constructors.
# ============================================================================

class Matrix:
    """Immutable: `_data` is set once at construction and never written to
    again (enforced both by omitting `__setitem__` and by marking the
    underlying numpy buffer read-only), matching the frozen dataclasses
    (Transform/Orientation/Axis) that hold Matrix-typed fields elsewhere in
    this module -- without this, `some_frozen_transform.position[0] = 5`
    would silently succeed despite the dataclass being frozen.
    """

    __slots__ = ("_data",)

    def __init__(self, data):
        if isinstance(data, Matrix):
            arr = np.array(data._data, dtype=float, copy=True)
        elif isinstance(data, np.ndarray):
            arr = np.array(data, dtype=float)
            arr = arr.reshape(-1, 1) if arr.ndim == 1 else arr
        else:
            data = list(data)
            if len(data) > 0 and isinstance(data[0], (list, tuple)):
                arr = np.array([[float(v) for v in row] for row in data], dtype=float)
            else:
                arr = np.array([float(v) for v in data], dtype=float).reshape(-1, 1)
        arr.setflags(write=False)
        self._data = arr

    @classmethod
    def _wrap(cls, arr: np.ndarray) -> 'Matrix':
        arr.setflags(write=False)
        out = cls.__new__(cls)
        out._data = arr
        return out

    @classmethod
    def eye(cls, n: int) -> 'Matrix':
        return cls._wrap(np.eye(n, dtype=float))

    @classmethod
    def zeros(cls, rows: int, cols: Optional[int] = None) -> 'Matrix':
        return cls._wrap(np.zeros((rows, cols if cols is not None else rows), dtype=float))

    @property
    def shape(self) -> Tuple[int, int]:
        rows, cols = self._data.shape
        return (rows, cols)

    @property
    def rows(self) -> int:
        return self._data.shape[0]

    @property
    def cols(self) -> int:
        return self._data.shape[1]

    @property
    def T(self) -> 'Matrix':
        return Matrix._wrap(np.ascontiguousarray(self._data.T))

    def det(self) -> float:
        return float(np.linalg.det(self._data))

    def dot(self, other: 'Matrix') -> float:
        other_data = other._data if isinstance(other, Matrix) else np.asarray(other, dtype=float)
        return float(np.dot(self._data.flatten(), other_data.flatten()))

    def cross(self, other: 'Matrix') -> 'Matrix':
        other_data = other._data if isinstance(other, Matrix) else np.asarray(other, dtype=float)
        result = np.cross(self._data.flatten(), other_data.flatten())
        return Matrix._wrap(result.reshape(-1, 1))

    def equals(self, other: 'Matrix', tolerance: Optional[float] = None) -> bool:
        """Elementwise approximate equality (tolerates float noise from trig/sqrt)."""
        if not isinstance(other, Matrix) or self._data.shape != other._data.shape:
            return False
        tol = EPSILON_GENERIC if tolerance is None else tolerance
        return bool(np.all(np.abs(self._data - other._data) < tol))

    def norm(self) -> float:
        return float(np.linalg.norm(self._data))

    def tolist(self) -> list:
        return self._data.tolist()

    def __getitem__(self, key):
        if isinstance(key, tuple):
            result = self._data[key]
        else:
            result = self._data.flat[key]
        if isinstance(result, np.ndarray):
            if result.ndim == 1:
                # A row-slice (int row, slice col) -> keep as a row vector;
                # anything else (col-slice, or a flat slice) -> column vector,
                # matching sympy's Matrix slicing shapes.
                if isinstance(key, tuple) and isinstance(key[0], int):
                    result = result.reshape(1, -1)
                else:
                    result = result.reshape(-1, 1)
            return Matrix._wrap(result)
        return float(result)

    def __iter__(self):
        return iter(self._data.flatten().tolist())

    def __len__(self) -> int:
        return int(self._data.size)

    def __mul__(self, other):
        if isinstance(other, Matrix):
            return Matrix._wrap(self._data @ other._data)
        return Matrix._wrap(self._data * float(other))

    def __rmul__(self, other):
        return Matrix._wrap(self._data * float(other))

    def __truediv__(self, other):
        return Matrix._wrap(self._data / float(other))

    def __add__(self, other):
        other_data = other._data if isinstance(other, Matrix) else other
        return Matrix._wrap(self._data + other_data)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        other_data = other._data if isinstance(other, Matrix) else other
        return Matrix._wrap(self._data - other_data)

    def __rsub__(self, other):
        other_data = other._data if isinstance(other, Matrix) else other
        return Matrix._wrap(other_data - self._data)

    def __neg__(self):
        return Matrix._wrap(-self._data)

    def __eq__(self, other):
        if not isinstance(other, Matrix):
            return NotImplemented
        return self._data.shape == other._data.shape and bool(np.array_equal(self._data, other._data))

    def __repr__(self) -> str:
        return f"Matrix({self._data.tolist()!r})"


def eye(n: int) -> Matrix:
    return Matrix.eye(n)


def det(matrix: Matrix) -> float:
    return matrix.det()


# Type aliases for vectors, these are just to provide some semantic clarity
# in the interfaces and are not enforced by the type system.
V2 = Matrix  # 2D vector - 2x1 Matrix
V3 = Matrix  # 3D vector - 3x1 Matrix
Direction3D = Matrix  # 3D direction vector - 3x1 Matrix


# ============================================================================
# Epsilon constants for numerical comparisons
# ============================================================================

# The single tolerance every approximate comparison in the library falls back
# to. There used to be a second, tighter EPSILON_FLOAT (1e-10) used by the
# safe_* comparisons while this one covered Matrix.equals and sqrt's
# small-negative guard; two thresholds a hundred times apart, with no rule for
# which applied where, was a trap rather than a feature.
EPSILON_GENERIC = scalar('1e-8')


# ============================================================================
# prune() -- kept as a compatibility identity
#
# There is no expression tree left to collapse, but `prune()` is called
# directly in real geometry logic (not just internally), so it stays as a
# no-op rather than being deleted outright.
# ============================================================================

def prune(value, collapse_mode=None):
    return value


safe_prune = prune
numeric_prune = prune


# ============================================================================
# giraffe_evalf -- kept as a compatibility shim
#
# Several call sites use this purely to "get a definite float for sorting/
# comparison"; with float-native scalars this is just float().
# ============================================================================

def giraffe_evalf(expr) -> float:
    return float(expr)


# ============================================================================
# Transform Class
# ============================================================================

@dataclass(frozen=True)
class Axis:
    position: V3
    direction: Direction3D

@dataclass(frozen=True)
class Transform:
    """
    Represents a 3D transformation with position and orientation.
    Encapsulates both translation and rotation for objects in 3D space.
    """
    position: V3
    orientation: 'Orientation'

    @classmethod
    def identity(cls) -> 'Transform':
        """Create an identity transform at origin with identity orientation."""
        return cls(
            position=create_v3(scalar(0), scalar(0), scalar(0)),
            orientation=Orientation.identity()
        )

    # TODO consider renaming to do_transform
    def local_to_global(self, local_point: V3) -> V3:
        """
        Convert a point from local coordinates to global world coordinates.

        Args:
            local_point: A point in local coordinates

        Returns:
            The same point in global world coordinates
        """
        # Rotate to global frame, then translate to position
        # global = R * local + position
        return safe_transform_vector(self.orientation.matrix, local_point) + self.position

    # TODO consider renaming to undo_transform
    def global_to_local(self, global_point: V3) -> V3:
        """
        Convert a point from global world coordinates to local coordinates.

        Args:
            global_point: A point in global world coordinates

        Returns:
            The same point in local coordinates
        """
        # Translate to origin, then rotate to local frame
        # local = R^T * (global - position)
        translated = global_point - self.position
        return safe_transform_vector(self.orientation.matrix.T, translated)

    def numeric_local_to_global(self, local_point: V3) -> V3:
        """Convert local to global using numeric (Float) math. For hot paths like CSG."""
        return numeric_transform_vector(self.orientation.matrix, local_point) + self.position

    def numeric_global_to_local(self, global_point: V3) -> V3:
        """Convert global to local using numeric (Float) math. For hot paths like CSG."""
        translated = global_point - self.position
        return numeric_transform_vector(self.orientation.matrix.T, translated)

    # TODO consider renaming to leave_parent_transform
    def to_global_transform(self, old_parent: 'Transform') -> 'Transform':
        """
        Convert this transform to global coordinates relative to a parent transform.
        """
        return old_parent * self

    def invert(self) -> 'Transform':
        """
        Return the inverse of this transform.

        For a transform T that converts local to global (global = T * local),
        the inverse converts global to local (local = T^-1 * global).
        """
        # Invert the orientation (transpose for rotation matrices)
        inv_orientation = self.orientation.invert()
        # Transform the position by the inverted orientation and negate
        inv_position = -safe_transform_vector(inv_orientation.matrix, self.position)
        return Transform(position=inv_position, orientation=inv_orientation)

    def __mul__(self, other: 'Transform') -> 'Transform':
        """
        Compose two transforms: result = self * other.

        This applies other first, then self.
        Equivalent to: global = self.local_to_global(other.local_to_global(local))
        """
        new_orientation = self.orientation * other.orientation
        new_position = safe_transform_vector(self.orientation.matrix, other.position) + self.position
        return Transform(position=new_position, orientation=new_orientation)

    # TODO consider renaming to become_child_transform
    def to_local_transform(self, new_parent: 'Transform') -> 'Transform':
        """
        Convert this transform to local coordinates relative to a parent transform.
        """
        return new_parent.invert() * self

    def rotate_around_axis(self, axis: Axis, radians: Numeric) -> 'Transform':
        """
        Rotate this transform counterclockwise around an axis and return the new transform.

        The axis can be positioned anywhere in space (not just through the origin).
        Uses Rodrigues' rotation formula after translating to make the axis pass through origin.

        Args:
            axis: Axis with position and direction to rotate around
            radians: Angle to rotate in radians (counterclockwise when looking along axis direction)

        Returns:
            New Transform with rotated position and orientation
        """
        # Normalize the axis direction
        axis_normalized = safe_normalize_vector(axis.direction)
        kx, ky, kz = axis_normalized[0], axis_normalized[1], axis_normalized[2]

        # Rodrigues' rotation formula for rotation matrix around axis k by angle θ:
        # R = I + sin(θ)K + (1 - cos(θ))K²
        # where K is the skew-symmetric cross-product matrix of k

        # K = [[0, -kz, ky], [kz, 0, -kx], [-ky, kx, 0]]
        K = Matrix([
            [scalar(0), -kz, ky],
            [kz, scalar(0), -kx],
            [-ky, kx, scalar(0)]
        ])

        # K² = K * K
        K_squared = K * K

        # R = I + sin(θ)K + (1 - cos(θ))K²
        I = eye(3)
        rotation_matrix = I + sin(radians) * K + (scalar(1) - cos(radians)) * K_squared

        # To rotate around an axis not through origin:
        # 1. Translate so axis passes through origin
        # 2. Rotate
        # 3. Translate back

        # Translate position relative to axis position
        position_relative = self.position - axis.position

        # Apply rotation to the relative position
        rotated_relative = rotation_matrix * position_relative

        # Translate back
        new_position = rotated_relative + axis.position

        # Apply rotation to orientation (orientation is independent of translation)
        new_orientation_matrix = rotation_matrix * self.orientation.matrix
        new_orientation = Orientation(new_orientation_matrix)

        return Transform(position=new_position, orientation=new_orientation)

# ============================================================================
# Giraffe Math Operations
#
# `safe_*`/`numeric_*`/`giraffe_*` are kept as aliases of the same plain
# float/numpy implementation -- the three-way split used to control when a
# sympy expression tree got collapsed to Float, which no longer applies.
# ============================================================================

def giraffe_norm(vec: Matrix, collapse_mode=None) -> float:
    """Compute vector norm."""
    return vec.norm()


def giraffe_det(matrix: Matrix, collapse_mode=None) -> float:
    """Compute matrix determinant."""
    return matrix.det()


def giraffe_simplify(expr, collapse_mode=None):
    """No-op (see module-level `simplify`)."""
    return expr


class Comparison(Enum):
    """Enum for safe comparison operations"""
    GT = ">"      # Greater than
    LT = "<"      # Less than
    GE = ">="     # Greater than or equal
    LE = "<="     # Less than or equal
    EQ = "=="     # Equal
    NE = "!="     # Not equal


def _apply_comparison(val: float, comp: Comparison, eps: Optional[float] = None) -> bool:
    """Apply comparison operation to a float value against zero.

    GT/LT/GE/LE are epsilon-widened around zero, not just EQ/NE: exact
    rational arithmetic used to make e.g. a polygon-edge containment check
    land on exactly 0 at a vertex; float arithmetic can now land a hair to
    either side of 0 for the same geometrically-exact case, so a strict
    `val > 0`/`val < 0` here would flip the answer on noise alone.

    *eps* defaults to EPSILON_GENERIC. Callers doing geometry against meshed
    (rather than analytic) input pass a wider one -- see cutcsg's
    FeatureEpsilons and the ``eps`` parameter threaded through its point
    queries.
    """
    if eps is None:
        eps = EPSILON_GENERIC
    if comp == Comparison.GT:
        return val > eps
    elif comp == Comparison.LT:
        return val < -eps
    elif comp == Comparison.GE:
        return val >= -eps
    elif comp == Comparison.LE:
        return val <= eps
    elif comp == Comparison.EQ:
        return abs(val) < eps
    elif comp == Comparison.NE:
        return abs(val) >= eps
    else:
        raise ValueError(f"Unknown comparison: {comp}")


def giraffe_compare(a, b, comparison: Comparison, collapse_mode=None, eps: Optional[float] = None) -> bool:
    """
    Compare two values: evaluates ``a - b`` and applies *comparison* against zero.

    *eps* overrides the default comparison tolerance for this one call.

    Examples:
        giraffe_compare(x, y, Comparison.GT)   # x > y ?
        giraffe_compare(x, 0, Comparison.EQ)   # x == 0 ?
    """
    try:
        val = float(a) - float(b)
    except Exception:
        return False
    return _apply_comparison(val, comparison, eps)


def giraffe_dot_product(vec1: Matrix, vec2: Matrix, collapse_mode=None) -> float:
    """Compute dot product."""
    return vec1.dot(vec2)


def giraffe_transform_vector(matrix: Matrix, vector: Matrix, collapse_mode=None) -> Matrix:
    """Compute matrix * vector (or matrix * matrix) transformation."""
    return matrix * vector


def giraffe_normalize_vector(vec: Matrix, collapse_mode=None) -> Matrix:
    """Normalize a vector."""
    norm = giraffe_norm(vec)
    if norm < EPSILON_GENERIC:
        return vec
    return vec / norm


def giraffe_magnitude(vec: Matrix, collapse_mode=None) -> float:
    """Compute vector magnitude. Alias for giraffe_norm."""
    return giraffe_norm(vec)


# ============================================================================
# safe_* / numeric_* aliases -- kept for the ~800 existing call sites
# ============================================================================

safe_norm = giraffe_norm
numeric_norm = giraffe_norm

safe_det = giraffe_det
numeric_det = giraffe_det

safe_simplify = giraffe_simplify

safe_compare = giraffe_compare
numeric_compare = giraffe_compare

safe_dot_product = giraffe_dot_product
numeric_dot_product = giraffe_dot_product

safe_transform_vector = giraffe_transform_vector
numeric_transform_vector = giraffe_transform_vector

safe_normalize_vector = giraffe_normalize_vector
numeric_normalize_vector = giraffe_normalize_vector

safe_magnitude = giraffe_magnitude
numeric_magnitude = giraffe_magnitude


# ============================================================================
# Helper Functions for Vector Operations
# ============================================================================

def create_v2(x: Numeric, y: Numeric) -> V2:
    """Create a 2D vector"""
    return Matrix([x, y])

def create_v3(x: Numeric, y: Numeric, z: Numeric) -> V3:
    """Create a 3D vector"""
    return Matrix([x, y, z])

def cross_product(v1: V3, v2: V3) -> V3:
    """Calculate cross product of two 3D vectors"""
    return Matrix([
        v1[1]*v2[2] - v1[2]*v2[1],
        v1[2]*v2[0] - v1[0]*v2[2],
        v1[0]*v2[1] - v1[1]*v2[0]
    ])

# ============================================================================
# Angle Conversion Functions
# ============================================================================

def radians(angle: Numeric) -> Numeric:
    """
    Identity function for angles already in radians.
    Use this to make it explicit that an angle is in radians.

    Args:
        angle: Angle value in radians

    Returns:
        The same angle value (unchanged)

    Examples:
        radians(pi / 2)      # 90 degrees in radians
        radians(pi / 4)       # 45 degrees in radians
    """
    return angle

def degrees(angle: Numeric) -> Numeric:
    """
    Convert an angle from degrees to radians.

    Args:
        angle: Angle value in degrees

    Returns:
        Angle value in radians

    Examples:
        degrees(90)           # 90 degrees = pi/2 radians
        degrees(45)           # 45 degrees = pi/4 radians
        degrees(180)          # 180 degrees = pi radians
    """
    return angle * pi / scalar(180)


# ============================================================================
# Unit Conversion Constants
# ============================================================================

# Conversion factors to meters
INCH_TO_METER = scalar(254, 10000)      # 0.0254 m (exact by definition)
FOOT_TO_METER = scalar(3048, 10000)     # 0.3048 m (exact by definition)
SHAKU_TO_METER = scalar(10, 33)         # ~0.303030... m (1 shaku = 10/33 m, traditional)

# Note: The traditional Japanese shaku is defined as 10/33 meters
# This gives approximately 303.03mm


# ============================================================================
# Dimensional Helper Functions
# ============================================================================

def inches(numerator, denominator=1):
    """
    Create a measurement in meters from inches.

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        inches(1, 32)        # 1/32 inch
        inches(4)            # 4 inches
        inches(3.5)          # 3.5 inches
        inches("1.5")        # 1.5 inches from string
        inches("1/32")       # Parses fraction string
    """
    return scalar(numerator, denominator) * INCH_TO_METER


def feet(numerator, denominator=1):
    """
    Create a measurement in meters from feet.

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        feet(8)              # 8 feet
        feet(1, 2)           # 1/2 foot
        feet(6.5)            # 6.5 feet
    """
    return scalar(numerator, denominator) * FOOT_TO_METER


def mm(numerator, denominator=1):
    """
    Create a measurement in meters from millimeters.

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        mm(90)               # 90 millimeters
        mm(1, 2)             # 1/2 millimeter
        mm(25.4)             # 25.4 millimeters
    """
    return scalar(numerator, denominator) / 1000


def cm(numerator, denominator=1):
    """
    Create a measurement in meters from centimeters.

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        cm(9)                # 9 centimeters
        cm(1, 2)             # 1/2 centimeter
        cm(2.54)             # 2.54 centimeters
    """
    return scalar(numerator, denominator) / 100


def m(numerator, denominator=1):
    """
    Create a measurement in meters.

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        m(1)                 # 1 meter
        m(1, 2)              # 1/2 meter
        m(2.5)               # 2.5 meters
    """
    return scalar(numerator, denominator)


def shaku(numerator, denominator=1):
    """
    Create a measurement in meters from shaku (尺).
    Traditional Japanese carpentry unit.

    1 shaku ≈ 303.03 mm (exactly 10/33 meters)

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        shaku(1)             # 1 shaku
        shaku(3, 2)          # 3/2 shaku (1.5 shaku)
        shaku(2.5)           # 2.5 shaku
    """
    return scalar(numerator, denominator) * SHAKU_TO_METER


def sun(numerator, denominator=1):
    """
    Create a measurement in meters from sun (寸).
    Traditional Japanese carpentry unit.

    1 sun = 1/10 shaku ≈ 30.303 mm

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        sun(1)               # 1 sun
        sun(5)               # 5 sun
        sun(1, 2)            # 1/2 sun
    """
    return scalar(numerator, denominator) * SHAKU_TO_METER / 10


def bu(numerator, denominator=1):
    """
    Create a measurement in meters from bu (分).
    Traditional Japanese carpentry unit.

    1 bu = 1/10 sun = 1/100 shaku ≈ 3.0303 mm

    Args:
        numerator: The numerator (can be int, float, or str)
        denominator: The denominator (default=1)

    Returns:
        float value in meters

    Examples:
        bu(1)                # 1 bu
        bu(5)                # 5 bu
        bu(1, 2)             # 1/2 bu
    """
    return scalar(numerator, denominator) * SHAKU_TO_METER / 100


# ============================================================================
# Zero / Equality Test Helper Functions
# ============================================================================

def safe_zero_test(value, eps: Optional[float] = None) -> bool:
    """Test if a value is approximately zero, within *eps* (default EPSILON_GENERIC)."""
    return safe_compare(value, 0, Comparison.EQ, eps=eps)


def safe_equality_test(value, expected, eps: Optional[float] = None) -> bool:
    """Test if two values are approximately equal, within *eps* (default EPSILON_GENERIC)."""
    return safe_compare(value, expected, Comparison.EQ, eps=eps)


def safe_zero_test_sq(value_squared, eps: Optional[float] = None) -> bool:
    """Test whether a SQUARED quantity is approximately zero.

    Takes a LINEAR tolerance and squares it internally, so *eps* means the
    same thing here as everywhere else in the library: a distance in model
    units, never a distance squared.

        safe_zero_test_sq(dx * dx + dy * dy, eps)   # is the distance ~0?

    Use this rather than safe_zero_test wherever the value under test is a
    square. Passing a squared value to safe_zero_test compares it against a
    linear tolerance, which sounds harmless and is not: at eps=5e-4 it treats
    any length below 22mm as zero. That has been the shape of two real bugs
    here already -- polygon edges declared degenerate, and pick tolerances
    meaning millimetres on one primitive and centimetres on another.
    """
    tolerance = EPSILON_GENERIC if eps is None else eps
    return safe_compare(value_squared, 0, Comparison.EQ, eps=tolerance * tolerance)


# ============================================================================
# Parallel and Perpendicular Check Functions
# ============================================================================

def are_vectors_parallel(vector1: Matrix, vector2: Matrix, eps: Optional[float] = None) -> bool:
    """
    Check if two vectors are parallel.

    For normalized vectors: dot product ≈ ±1 means parallel

    Args:
        vector1: First direction vector
        vector2: Second direction vector

    Returns:
        True if |abs(dot_product) - 1| is approximately zero (vectors are parallel)
    """
    # Compute dot product
    dot_product = vector1.dot(vector2)

    # Check if |abs(dot_product) - 1| is approximately zero
    # This is equivalent to checking if abs(dot_product) is approximately 1
    deviation = Abs(Abs(dot_product) - 1)

    return safe_zero_test(deviation, eps)

def are_vectors_perpendicular(vector1: Matrix, vector2: Matrix, eps: Optional[float] = None) -> bool:
    """
    Check if two vectors are perpendicular.

    For any vectors: dot product ≈ 0 means perpendicular

    Args:
        vector1: First direction vector
        vector2: Second direction vector

    Returns:
        True if dot_product is approximately zero (vectors are perpendicular)
    """
    # Compute dot product
    dot_product = vector1.dot(vector2)

    # Check if dot product is approximately zero
    return safe_zero_test(dot_product, eps)


# ============================================================================
# Orientation Class
# ============================================================================

@dataclass(frozen=True)
class Orientation:
    """
    Represents a 3D rotation using a 3x3 rotation matrix.
    I guess we never slerp and don't care about memory usage so apparently we're using matrices to implement this class.
    """
    matrix: Matrix = field(default_factory=lambda: Matrix.eye(3))

    def __post_init__(self):
        """Convert to Matrix and validate that the matrix is 3x3."""
        # Convert to Matrix if necessary (handles list/tuple inputs)
        if not isinstance(self.matrix, Matrix):
            object.__setattr__(self, 'matrix', Matrix(self.matrix))

        if self.matrix.shape != (3, 3):
            raise ValueError("Rotation matrix must be 3x3")

    def multiply(self, other: 'Orientation') -> 'Orientation':
        """
        Multiply this orientation with another orientation.
        Returns a new Orientation representing the combined rotation.
        """
        if not isinstance(other, Orientation):
            raise TypeError("Can only multiply with another Orientation")
        return Orientation(safe_transform_vector(self.matrix, other.matrix))

    def invert(self) -> 'Orientation':
        """
        Return the inverse of this orientation.
        For rotation matrices, the inverse is the transpose.
        """
        return Orientation(self.matrix.T)

    def flip(self, flip_x: bool = False, flip_y: bool = False, flip_z: bool = False) -> 'Orientation':
        """
        Return the orientation with the given axes flipped.
        """
        # Matrix is frozen, so mutate a raw numpy buffer here and wrap it
        # fresh at the end rather than assigning into an existing Matrix.
        arr = self.matrix._data.copy()
        if flip_x:
            arr[0, :] = -arr[0, :]
        if flip_y:
            arr[:, 0] = -arr[:, 0]
        if flip_z:
            arr[:, 2] = -arr[:, 2]
        return Orientation(Matrix._wrap(arr))

    def __mul__(self, other: 'Orientation') -> 'Orientation':
        """Allow using * operator for multiplication"""
        return self.multiply(other)

    def __repr__(self) -> str:
        return f"Orientation(\n{self.matrix}\n)"

    @classmethod
    def rotate_right(cls) -> 'Orientation':
        """Rotate right: +X axis rotates to -Y axis (clockwise around Z)"""
        matrix = Matrix([
            [0, 1, 0],
            [-1, 0, 0],
            [0, 0, 1]
        ])
        return cls(matrix)

    @classmethod
    def rotate_left(cls) -> 'Orientation':
        """Rotate left: +X axis rotates to +Y axis (counterclockwise around Z)"""
        matrix = Matrix([
            [0, -1, 0],
            [1, 0, 0],
            [0, 0, 1]
        ])
        return cls(matrix)

    @classmethod
    def from_angle_axis(cls, radians: Numeric, axis: Direction3D) -> 'Orientation':
        """Create an orientation from an angle-axis rotation (Rodrigues' formula)."""
        k = safe_normalize_vector(axis)
        kx, ky, kz = k[0], k[1], k[2]
        K = Matrix([
            [scalar(0), -kz, ky],
            [kz, scalar(0), -kx],
            [-ky, kx, scalar(0)]
        ])
        R = eye(3) + sin(radians) * K + (scalar(1) - cos(radians)) * K * K
        return cls(R)


    # Static constants for cardinal directions
    @staticmethod
    def identity() -> 'Orientation':
        """Identity orientation - facing east (+X)"""
        return Orientation()

    @staticmethod
    def from_z_and_y(z_direction: Direction3D, y_direction: Direction3D) -> 'Orientation':
        """
        Create an Orientation from z and y direction vectors.
        Computes x = y × z to complete the right-handed coordinate system.
        """
        x_direction = cross_product(y_direction, z_direction)
        return Orientation(Matrix([
            [x_direction[0], y_direction[0], z_direction[0]],
            [x_direction[1], y_direction[1], z_direction[1]],
            [x_direction[2], y_direction[2], z_direction[2]]
        ]))

    @staticmethod
    def from_z_and_x(z_direction: Direction3D, x_direction: Direction3D) -> 'Orientation':
        """
        Create an Orientation from z and x direction vectors.
        Computes y = z × x to complete the right-handed coordinate system.
        """
        y_direction = cross_product(z_direction, x_direction)
        return Orientation(Matrix([
            [x_direction[0], y_direction[0], z_direction[0]],
            [x_direction[1], y_direction[1], z_direction[1]],
            [x_direction[2], y_direction[2], z_direction[2]]
        ]))

    @staticmethod
    def from_x_and_y(x_direction: Direction3D, y_direction: Direction3D) -> 'Orientation':
        """
        Create an Orientation from x and y direction vectors.
        Computes z = x × y to complete the right-handed coordinate system.
        """
        z_direction = cross_product(x_direction, y_direction)
        return Orientation(Matrix([
            [x_direction[0], y_direction[0], z_direction[0]],
            [x_direction[1], y_direction[1], z_direction[1]],
            [x_direction[2], y_direction[2], z_direction[2]]
        ]))

    @staticmethod
    def from_axis_angle(axis: Direction3D, radians: Numeric) -> 'Orientation':
        """
        Create an Orientation representing a rotation around an axis by an angle.
        Uses Rodrigues' rotation formula.

        Args:
            axis: Direction vector to rotate around (will be normalized)
            radians: Angle to rotate in radians

        Returns:
            Orientation object representing the rotation
        """
        # Normalize the axis
        axis_normalized = safe_normalize_vector(axis)
        kx, ky, kz = axis_normalized[0], axis_normalized[1], axis_normalized[2]

        # Rodrigues' rotation formula: R = I + sin(θ)K + (1 - cos(θ))K²
        # where K is the skew-symmetric cross-product matrix of k
        K = Matrix([
            [scalar(0), -kz, ky],
            [kz, scalar(0), -kx],
            [-ky, kx, scalar(0)]
        ])
        K_squared = K * K
        I = Matrix.eye(3)
        rotation_matrix = I + sin(radians) * K + (scalar(1) - cos(radians)) * K_squared

        return Orientation(rotation_matrix)

    @staticmethod
    def from_euleryZYX(yaw: Numeric, pitch: Numeric, roll: Numeric) -> 'Orientation':
        """
        Create an Orientation from Euler angles using ZYX rotation sequence.

        Args:
            yaw: Rotation around Z-axis (radians)
            pitch: Rotation around Y-axis (radians)
            roll: Rotation around X-axis (radians)

        Returns:
            Orientation object with combined rotation matrix

        The rotation sequence is:
        1. Yaw (Z-axis rotation)
        2. Pitch (Y-axis rotation)
        3. Roll (X-axis rotation)
        """
        # Individual rotation matrices
        Rz = Matrix([
            [cos(yaw), -sin(yaw), 0],
            [sin(yaw), cos(yaw), 0],
            [0, 0, 1]
        ])

        Ry = Matrix([
            [cos(pitch), 0, sin(pitch)],
            [0, 1, 0],
            [-sin(pitch), 0, cos(pitch)]
        ])

        Rx = Matrix([
            [1, 0, 0],
            [0, cos(roll), -sin(roll)],
            [0, sin(roll), cos(roll)]
        ])

        # Combined rotation: R = Rz * Ry * Rx
        combined_matrix = Rz * Ry * Rx
        return Orientation(combined_matrix)


    # ========================================================================
    # TIMBER ORIENTATION METHODS
    # ========================================================================
    #
    # TODO prefix all these method with orient_timber_
    #
    # These methods provide orientations specifically for orienting timbers.
    #
    # CANONICAL CONVENTIONS:
    # - facing_* methods: HORIZONTAL timbers with LENGTH along the horizontal plane
    #   and FACING (top) pointing up (+Z). The name indicates which direction the
    #   LENGTH axis points. Example: facing_east has Length pointing +X (east).
    #
    # - pointing_* methods: Timbers with LENGTH pointing in the named direction.
    #   Example: pointing_up has Length pointing +Z (up), pointing_down has Length
    #   pointing -Z (down).
    #
    # COORDINATE SYSTEM (timber local space):
    # - Timber LENGTH runs along local +X axis (column 0 of rotation matrix)
    # - Timber WIDTH runs along local +Y axis (column 1 of rotation matrix)
    # - Timber HEIGHT/FACING runs along local +Z axis (column 2 of rotation matrix)
    # ========================================================================

    @staticmethod
    def facing_west() -> 'Orientation':
        """
        Horizontal timber with top face up.
        This is the IDENTITY orientation.

        - Length: +X (local) = -X (west) in global
        - Width: +Y (local) = -Y (south) in global
        - Facing: +Z (up)
        """
        return Orientation()  # Identity matrix

    @staticmethod
    def facing_east() -> 'Orientation':
        """
        Horizontal timber with top face up.
        180° rotation around Z axis from facing_west.

        - Length: +X (local) = +X (east) in global
        - Width: +Y (local) = +Y (north) in global
        - Facing: +Z (up)
        """
        matrix = Matrix([
            [-1, 0, 0],
            [0, -1, 0],
            [0, 0, 1]
        ])
        return Orientation(matrix)

    @staticmethod
    def facing_north() -> 'Orientation':
        """
        Horizontal timber with top face up.
        90° counterclockwise rotation around Z axis from facing_west.

        - Length: +X (local) = +Y (north) in global
        - Width: +Y (local) = -X (west) in global
        - Facing: +Z (up)
        """
        matrix = Matrix([
            [0, -1, 0],
            [1, 0, 0],
            [0, 0, 1]
        ])
        return Orientation(matrix)

    @staticmethod
    def facing_south() -> 'Orientation':
        """
        Horizontal timber with top face up.
        90° clockwise rotation around Z axis from facing_west.

        - Length: +X (local) = -Y (south) in global
        - Width: +Y (local) = +X (east) in global
        - Facing: +Z (up)
        """
        matrix = Matrix([
            [0, 1, 0],
            [-1, 0, 0],
            [0, 0, 1]
        ])
        return Orientation(matrix)

    @staticmethod
    def pointing_up() -> 'Orientation':
        """
        Vertical timber with LENGTH pointing upward (+Z).
        This is the same as pointing_forward.

        - Length (local +X) → +Z (up) in global
        - Width (local +Y) → +Y (north) in global
        - Facing (local +Z) → -X (west) in global
        """
        matrix = Matrix([
            [0, 0, -1],
            [0, 1, 0],
            [1, 0, 0]
        ])
        return Orientation(matrix)

    @staticmethod
    def pointing_down() -> 'Orientation':
        """
        Vertical timber with LENGTH pointing downward (-Z).

        - Length (local +X) → -Z (down) in global
        - Width (local +Y) → +Y (north) in global
        - Facing (local +Z) → +X (east) in global
        """
        matrix = Matrix([
            [0, 0, 1],
            [0, 1, 0],
            [-1, 0, 0]
        ])
        return Orientation(matrix)

    @staticmethod
    def pointing_forward() -> 'Orientation':
        """
        Vertical timber with LENGTH pointing upward (+Z).
        Identical to pointing_up.

        - Length (local +X) → +Z (up) in global
        - Width (local +Y) → +Y (north) in global
        - Facing (local +Z) → -X (west) in global
        """
        matrix = Matrix([
            [0, 0, -1],
            [0, 1, 0],
            [1, 0, 0]
        ])
        return Orientation(matrix)

    @staticmethod
    def pointing_backward() -> 'Orientation':
        """
        Vertical timber with LENGTH pointing upward (+Z), rotated 180° from pointing_forward.

        - Length (local +X) → +Z (up) in global
        - Width (local +Y) → -Y (south) in global
        - Facing (local +Z) → +X (east) in global
        """
        matrix = Matrix([
            [0, 0, 1],
            [0, -1, 0],
            [1, 0, 0]
        ])
        return Orientation(matrix)

    @staticmethod
    def pointing_left() -> 'Orientation':
        """
        Vertical timber with LENGTH pointing upward (+Z), rotated 90° CCW from pointing_forward.

        - Length (local +X) → +Z (up) in global
        - Width (local +Y) → -X (west) in global
        - Facing (local +Z) → -Y (south) in global
        """
        matrix = Matrix([
            [0, -1, 0],
            [0, 0, -1],
            [1, 0, 0]
        ])
        return Orientation(matrix)

    @staticmethod
    def pointing_right() -> 'Orientation':
        """
        Vertical timber with LENGTH pointing upward (+Z), rotated 90° CW from pointing_forward.

        - Length (local +X) → +Z (up) in global
        - Width (local +Y) → +X (east) in global
        - Facing (local +Z) → +Y (north) in global
        """
        matrix = Matrix([
            [0, 1, 0],
            [0, 0, 1],
            [1, 0, 0]
        ])
        return Orientation(matrix)
