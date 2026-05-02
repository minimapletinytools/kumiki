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


This library supports both numeric and symbolic computations. This library comes with 2 variants of each math function:
- `numeric_*` variant always evals expressions to numeric Floats and returns Floats
- `safe_*` variant returns symbolic expressions when possible, but will automatically eval to Float when expressions get too complex (e.g. large node count, or contain transcendental functions).

Avoid `safe_*` variants in general unless it's being used for some top level geometry declaration where having symbolic exactness might be nice, otherwise just stick with numeric. 

'''

import sympy as sp
from sympy import Matrix, cos, sin, pi, Float, Rational, Integer, Abs, S, sympify, Expr
from typing import Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import warnings


# ============================================================================
# Global Numeric Mode
# ============================================================================

# TODO DELETE this does not do anything meaningufl, just determines whether we "warn on complex expressions in symbolic mode" or something less heavy-handed.
# so rename this varibale
NUMERIC_MODE = "float"


def set_numeric_mode(mode: str) -> None:
    """Set global numeric mode. Valid values: 'symbolic' or 'float'."""
    global NUMERIC_MODE
    if mode not in ("symbolic", "float"):
        raise ValueError(f"Invalid numeric mode: {mode}. Expected 'symbolic' or 'float'.")
    NUMERIC_MODE = mode


def get_numeric_mode() -> str:
    """Get current global numeric mode."""
    return NUMERIC_MODE


def is_float_numeric_mode() -> bool:
    """Return True when float-first numeric mode is enabled."""
    return NUMERIC_MODE == "float"


# ============================================================================
# Type Aliases
# ============================================================================

# Type aliases for vectors using sympy, these are just to provide some semantic 
# clarity in the interfaces and are not enforced by the type system.
V2 = Matrix  # 2D vector - 2x1 Matrix
V3 = Matrix  # 3D vector - 3x1 Matrix  
Direction3D = Matrix  # 3D direction vector - 3x1 Matrix


# python floats must be explicitly converted to Expr using Rational or Float
# but python ints are allowed for conevience.... RIP
Numeric = Union[Expr, int] 


# ============================================================================
# Giraffe Math Utilities - Complexity Detection & Collapse Control
# ============================================================================


# Precision for all numeric evaluation — single constant to tune globally.
GIRAFFE_EVALF_PRECISION = 10
# Epsilon constants for numerical comparisons
EPSILON_GENERIC = Float('1e-8')      # Generic epsilon threshold for float comparisons, make sure this is larger than GIRAFFE_EVALF_PRECISION to avoid false positives
EPSILON_FLOAT = 1e-10                # Epsilon for plain Python float comparisons (used in safe_compare)
COMPLEX_NUM_NODES_THRESHOLD = 50  # Max number of nodes in expression tree before considering it complex


class CollapseMode(Enum):
    """Controls when symbolic expressions are collapsed to numeric Floats."""
    ALWAYS = "always"    # Eagerly collapse to Float via giraffe_evalf
    NEVER = "never"      # Keep symbolic form (for testing/debugging)
    SMART = "smart"      # Collapse only when expression complexity exceeds threshold


def giraffe_evalf(expr):
    """
    Evaluate a SymPy expression to a numeric Float. All numeric evaluation in the
    library is bottlenecked through this function so we can swap strategy later
    (e.g. lambdify, caching, timeouts) without touching callers.
    """
    if hasattr(expr, 'evalf'):
        result = expr.evalf(GIRAFFE_EVALF_PRECISION)
        # Ensure we always return a Float (e.g. Integer(0).evalf() returns Zero)
        if not isinstance(result, Float):
            return Float(float(result), GIRAFFE_EVALF_PRECISION)
        return result
    return Float(float(expr), GIRAFFE_EVALF_PRECISION)


def _should_collapse(expr, collapse_mode: CollapseMode) -> bool:
    """
    Decide whether *expr* should be collapsed to a numeric Float.

    - ALWAYS → True
    - NEVER  → False
    - SMART  → True when the expression exceeds the complexity threshold
               (is_complex_expr).  In symbolic mode, also emits a warning.
    """
    if collapse_mode == CollapseMode.ALWAYS:
        return True
    if collapse_mode == CollapseMode.NEVER:
        return False
    # SMART mode — collapse only when expression is complex
    if is_complex_expr(expr):
        if not is_float_numeric_mode():
            warnings.warn(
                f"Expression exceeded complexity threshold and will be collapsed to Float: {repr(expr)[:120]}",
                stacklevel=3,
            )
        return True
    return False


def _collapse_scalar(value, collapse_mode: CollapseMode):
    """Optionally collapse a scalar SymPy expression to Float."""
    if _should_collapse(value, collapse_mode):
        return giraffe_evalf(value)
    return value


def _collapse_matrix(mat: Matrix, collapse_mode: CollapseMode) -> Matrix:
    """Optionally collapse each element of a vector/matrix to Float, preserving shape."""
    if collapse_mode == CollapseMode.NEVER:
        return mat
    rows, cols = mat.shape
    if collapse_mode == CollapseMode.ALWAYS:
        collapsed = [[giraffe_evalf(mat[i, j]) for j in range(cols)] for i in range(rows)]
        if cols == 1:
            return Matrix([row[0] for row in collapsed])
        return Matrix(collapsed)
    # SMART: only collapse elements that are individually complex
    collapsed = []
    for i in range(rows):
        row = []
        for j in range(cols):
            elem = mat[i, j]
            if is_complex_expr(elem):
                if not is_float_numeric_mode():
                    warnings.warn(
                        f"Matrix element exceeded complexity threshold and will be collapsed "
                        f"to Float: {repr(elem)[:120]}",
                        stacklevel=3,
                    )
                row.append(giraffe_evalf(elem))
            else:
                row.append(elem)
        collapsed.append(row)
    if cols == 1:
        return Matrix([row[0] for row in collapsed])
    return Matrix(collapsed)


def is_complex_expr(expr, max_nodes: int = COMPLEX_NUM_NODES_THRESHOLD) -> bool:
    """
    Detect if a SymPy expression is complex enough to potentially cause slow operations.
    
    Uses heuristics with early bailout for performance:
    - Contains transcendental functions (sin, cos, exp, log) - always complex
    - Node count > max_nodes in expression tree (uses lazy traversal with early exit)
    - Contains sqrt with node count > COMPLEX_NUM_NODES_THRESHOLD
    
    Args:
        expr: SymPy expression to check
        max_nodes: Maximum node count before considering complex (default 50)
    
    Returns:
        True if expression is complex, False otherwise
    """
    from sympy import sin, cos, exp, log, sqrt, Number
    from sympy import preorder_traversal as _pot
    
    # Fast check: SymPy Number types (One, Zero, NegativeOne, Integer, Rational, Float, etc.)
    # are always simple and don't have preorder_traversal()
    if isinstance(expr, Number):
        return False
    
    if not hasattr(expr, 'has'):
        return False
    
    # Check for transcendental functions first (fast check)
    has_transcendental = any(expr.has(f) for f in [sin, cos, exp, log])
    if has_transcendental:
        return True
    
    # Check for sqrt (may use lower threshold)
    has_sqrt = expr.has(sqrt)
    threshold = 30 if has_sqrt else max_nodes
    
    # Count nodes with early bailout (uses module-level preorder_traversal
    # because not all expression types expose the method)
    try:
        for i, _ in enumerate(_pot(expr)):
            if i >= threshold:
                return True  # Hit threshold, expression is complex
        return False  # Finished traversal, expression is simple
    except:
        # If traversal fails, assume complex to be safe
        return True


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
            position=create_v3(Integer(0), Integer(0), Integer(0)),
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
        from sympy import cos, sin, eye
        
        # Normalize the axis direction
        axis_normalized = safe_normalize_vector(axis.direction)
        kx, ky, kz = axis_normalized[0], axis_normalized[1], axis_normalized[2]
        
        # Rodrigues' rotation formula for rotation matrix around axis k by angle θ:
        # R = I + sin(θ)K + (1 - cos(θ))K²
        # where K is the skew-symmetric cross-product matrix of k
        
        # K = [[0, -kz, ky], [kz, 0, -kx], [-ky, kx, 0]]
        K = Matrix([
            [Integer(0), -kz, ky],
            [kz, Integer(0), -kx],
            [-ky, kx, Integer(0)]
        ])
        
        # K² = K * K
        K_squared = K * K
        
        # R = I + sin(θ)K + (1 - cos(θ))K²
        I = eye(3)
        rotation_matrix = I + sin(radians) * K + (Integer(1) - cos(radians)) * K_squared
        
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
# Giraffe Math Operations — Base Layer
#
# Each giraffe_* function does the actual computation with a collapse_mode
# parameter.  The public API is:
#   safe_*    → giraffe_*(…, CollapseMode.SMART)   — default, backwards-compatible
#   numeric_* → giraffe_*(…, CollapseMode.ALWAYS)  — for hot paths (e.g. CSG)
# ============================================================================

def giraffe_norm(vec: Matrix, collapse_mode: CollapseMode = CollapseMode.SMART):
    """
    Compute vector norm with optional collapse to Float.

    Uses manual element-wise sum-of-squares to bypass SymPy's matrix internals,
    then applies *collapse_mode* to the result.
    """
    from sympy import sqrt

    # Manual sum of squares — avoids SymPy matrix .norm() which triggers
    # slow property checking on complex expressions.
    sum_sq = sum(c * c for c in vec)
    result = sqrt(sum_sq)
    return _collapse_scalar(result, collapse_mode)


def giraffe_det(matrix: Matrix, collapse_mode: CollapseMode = CollapseMode.SMART):
    """Compute matrix determinant with optional collapse."""
    result = matrix.det()
    return _collapse_scalar(result, collapse_mode)


def giraffe_simplify(expr, collapse_mode: CollapseMode = CollapseMode.SMART):
    """
    Simplify a SymPy expression.

    If the expression is complex, skip simplification entirely (SymPy simplify
    can be extremely slow on large trees).  Otherwise simplify, then optionally
    collapse.
    """
    from sympy import simplify as sp_simplify

    if is_complex_expr(expr):
        return _collapse_scalar(expr, collapse_mode)

    result = sp_simplify(expr)
    return _collapse_scalar(result, collapse_mode)


class Comparison(Enum):
    """Enum for safe comparison operations"""
    GT = ">"      # Greater than
    LT = "<"      # Less than
    GE = ">="     # Greater than or equal
    LE = "<="     # Less than or equal
    EQ = "=="     # Equal
    NE = "!="     # Not equal


def _apply_comparison(val: float, comp: Comparison) -> bool:
    """Apply comparison operation to a float value against zero."""
    if comp == Comparison.GT:
        return val > 0
    elif comp == Comparison.LT:
        return val < 0
    elif comp == Comparison.GE:
        return val >= 0
    elif comp == Comparison.LE:
        return val <= 0
    elif comp == Comparison.EQ:
        return abs(val) < EPSILON_FLOAT
    elif comp == Comparison.NE:
        return abs(val) >= EPSILON_FLOAT
    else:
        raise ValueError(f"Unknown comparison: {comp}")


def giraffe_compare(a, b, comparison: Comparison, collapse_mode: CollapseMode = CollapseMode.SMART) -> bool:
    """
    Compare two SymPy expressions: evaluates ``a - b`` and applies *comparison*
    against zero.

    Examples:
        giraffe_compare(x, y, Comparison.GT)   # x > y ?
        giraffe_compare(x, 0, Comparison.EQ)   # x == 0 ?
    """
    diff = a - b
    # Fast path: always collapse or expression is complex → evaluate numerically
    if collapse_mode == CollapseMode.ALWAYS or _should_collapse(diff, collapse_mode):
        try:
            val = float(giraffe_evalf(diff))
            return _apply_comparison(val, comparison)
        except Exception:
            return False

    # Symbolic path (NEVER mode, or SMART mode with simple expr in symbolic numeric mode)
    try:
        if comparison == Comparison.GT:
            return bool(diff > 0)
        elif comparison == Comparison.LT:
            return bool(diff < 0)
        elif comparison == Comparison.GE:
            return bool(diff >= 0)
        elif comparison == Comparison.LE:
            return bool(diff <= 0)
        elif comparison == Comparison.EQ:
            return bool(diff == 0)
        elif comparison == Comparison.NE:
            return bool(diff != 0)
        else:
            raise ValueError(f"Unknown comparison: {comparison}")
    except Exception:
        # Fallback to numerical evaluation
        try:
            val = float(giraffe_evalf(diff))
            return _apply_comparison(val, comparison)
        except Exception:
            return False


def giraffe_dot_product(vec1: Matrix, vec2: Matrix, collapse_mode: CollapseMode = CollapseMode.SMART):
    """
    Compute dot product manually (bypasses SymPy's matrix multiplication).
    Optionally collapse result to Float.
    """
    result = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))  # type: ignore[arg-type]
    return _collapse_scalar(result, collapse_mode)


def giraffe_transform_vector(matrix: Matrix, vector: Matrix, collapse_mode: CollapseMode = CollapseMode.SMART) -> Matrix:
    """
    Compute matrix * vector (or matrix * matrix) transformation manually
    to avoid SymPy's property checking.  Optionally collapse elements to Float.
    """
    mat_data = [[matrix[i, j] for j in range(matrix.cols)] for i in range(matrix.rows)]
    vec_data = [[vector[i, j] for j in range(vector.cols)] for i in range(vector.rows)]

    result = []
    for i in range(len(mat_data)):
        row = []
        for k in range(len(vec_data[0])):
            elem = sum(mat_data[i][j] * vec_data[j][k] for j in range(len(vec_data)))
            if collapse_mode == CollapseMode.ALWAYS:
                elem = giraffe_evalf(elem)
            elif collapse_mode == CollapseMode.SMART and is_complex_expr(elem):
                if not is_float_numeric_mode():
                    warnings.warn(
                        f"Matrix element exceeded complexity threshold and will be collapsed "
                        f"to Float: {repr(elem)[:120]}",
                        stacklevel=3,
                    )
                elem = giraffe_evalf(elem)
            row.append(elem)
        result.append(row)

    if len(result[0]) == 1:
        return Matrix([row[0] for row in result])
    return Matrix(result)


def giraffe_normalize_vector(vec: Matrix, collapse_mode: CollapseMode = CollapseMode.SMART) -> Matrix:
    """
    Normalize a vector.  Uses giraffe_norm for the magnitude, then divides
    element-wise.  Result elements are optionally collapsed to Float.
    """
    from fractions import Fraction

    norm = giraffe_norm(vec, collapse_mode)

    if safe_zero_test(norm):
        return vec

    # For Float / numeric norms, divide and convert back to Rational for stability
    if isinstance(norm, Float):
        norm_val = float(norm)
        if abs(norm_val) < 1e-15:
            return vec
        normalized = []
        for component in vec:
            comp_val = float(giraffe_evalf(component)) / norm_val
            frac = Fraction(comp_val).limit_denominator(10**9)
            normalized.append(Rational(frac.numerator, frac.denominator))
        return Matrix(normalized)

    # For exact symbolic norms (sqrt, Rational, Integer) — divide exactly
    return vec / norm


def giraffe_magnitude(vec: Matrix, collapse_mode: CollapseMode = CollapseMode.SMART):
    """Compute vector magnitude.  Alias for giraffe_norm."""
    return giraffe_norm(vec, collapse_mode)


# ============================================================================
# safe_* wrappers — backwards-compatible, use CollapseMode.SMART
# ============================================================================

def safe_norm(vec: Matrix):
    """Compute vector norm with smart collapse."""
    return giraffe_norm(vec, CollapseMode.SMART)


def safe_det(matrix: Matrix):
    """Compute matrix determinant with smart collapse."""
    return giraffe_det(matrix, CollapseMode.SMART)


def safe_simplify(expr):
    """Simplify with smart collapse."""
    return giraffe_simplify(expr, CollapseMode.SMART)


def safe_compare(a, b, comparison: Comparison) -> bool:
    """Compare two expressions with smart collapse: ``a <op> b``."""
    return giraffe_compare(a, b, comparison, CollapseMode.SMART)


def safe_dot_product(vec1: Matrix, vec2: Matrix):
    """Compute dot product with smart collapse."""
    return giraffe_dot_product(vec1, vec2, CollapseMode.SMART)


def safe_transform_vector(matrix: Matrix, vector: Matrix) -> Matrix:
    """Compute matrix * vector transformation with smart collapse."""
    return giraffe_transform_vector(matrix, vector, CollapseMode.SMART)


def safe_normalize_vector(vec: Matrix) -> Matrix:
    """Normalize a vector with smart collapse."""
    return giraffe_normalize_vector(vec, CollapseMode.SMART)


def safe_magnitude(vec: Matrix):
    """Compute vector magnitude with smart collapse."""
    return giraffe_magnitude(vec, CollapseMode.SMART)


# ============================================================================
# numeric_* wrappers — always collapse to Float, for hot paths
# ============================================================================

def numeric_norm(vec: Matrix):
    """Compute vector norm, always collapsed to Float."""
    return giraffe_norm(vec, CollapseMode.ALWAYS)


def numeric_det(matrix: Matrix):
    """Compute determinant, always collapsed to Float."""
    return giraffe_det(matrix, CollapseMode.ALWAYS)


def numeric_compare(a, b, comparison: Comparison) -> bool:
    """Compare two expressions, always using numeric evaluation: ``a <op> b``."""
    return giraffe_compare(a, b, comparison, CollapseMode.ALWAYS)


def numeric_dot_product(vec1: Matrix, vec2: Matrix):
    """Compute dot product, always collapsed to Float."""
    return giraffe_dot_product(vec1, vec2, CollapseMode.ALWAYS)


def numeric_transform_vector(matrix: Matrix, vector: Matrix) -> Matrix:
    """Compute matrix * vector transformation, always collapsed to Float."""
    return giraffe_transform_vector(matrix, vector, CollapseMode.ALWAYS)


def numeric_normalize_vector(vec: Matrix) -> Matrix:
    """Normalize a vector, always collapsed to Float."""
    return giraffe_normalize_vector(vec, CollapseMode.ALWAYS)


def numeric_magnitude(vec: Matrix):
    """Compute vector magnitude, always collapsed to Float."""
    return giraffe_magnitude(vec, CollapseMode.ALWAYS)

# ============================================================================
# Helper Functions for Vector Operations
# ============================================================================

def create_v2(x: Numeric, y: Numeric) -> V2:
    """Create a 2D vector"""
    return Matrix([x, y])

def create_v3(x: Numeric, y: Numeric, z: Numeric) -> V3:
    """Create a 3D vector"""
    return Matrix([x, y, z])

def normalize_vector(vec: Matrix) -> Matrix:
    """Deprecated: use safe_normalize_vector instead."""
    return safe_normalize_vector(vec)

def cross_product(v1: V3, v2: V3) -> V3:
    """Calculate cross product of two 3D vectors"""
    return Matrix([
        v1[1]*v2[2] - v1[2]*v2[1],
        v1[2]*v2[0] - v1[0]*v2[2], 
        v1[0]*v2[1] - v1[1]*v2[0]
    ])

def vector_magnitude(vec: Matrix):
    """Deprecated: use safe_magnitude instead."""
    return safe_magnitude(vec)


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
    return angle * pi / Rational(180)


# ============================================================================
# Unit Conversion Constants
# ============================================================================

# Conversion factors to meters (exact Rationals)
INCH_TO_METER = Rational(254, 10000)      # 0.0254 m (exact by definition)
FOOT_TO_METER = Rational(3048, 10000)     # 0.3048 m (exact by definition)
SHAKU_TO_METER = Rational(10, 33)         # ~0.303030... m (1 shaku = 10/33 m, traditional)

# Note: The traditional Japanese shaku is defined as 10/33 meters
# This gives approximately 303.03mm, and ensures exact rational arithmetic


# ============================================================================
# Dimensional Helper Functions
# ============================================================================

def inches(numerator, denominator=1):
    """
    Create a Rational measurement in meters from inches.
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        inches(1, 32)        # 1/32 inch
        inches(4)            # 4 inches
        inches(3.5)          # 3.5 inches (converted to Rational)
        inches("1.5")        # 1.5 inches from string
        inches("1/32")       # Parses fraction string
    """
    return Rational(numerator, denominator) * INCH_TO_METER


def feet(numerator, denominator=1):
    """
    Create a Rational measurement in meters from feet.
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        feet(8)              # 8 feet
        feet(1, 2)           # 1/2 foot
        feet(6.5)            # 6.5 feet (converted to Rational)
    """
    return Rational(numerator, denominator) * FOOT_TO_METER


def mm(numerator, denominator=1):
    """
    Create a Rational measurement in meters from millimeters.
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        mm(90)               # 90 millimeters
        mm(1, 2)             # 1/2 millimeter
        mm(25.4)             # 25.4 millimeters (converted to Rational)
    """
    return Rational(numerator, denominator) / 1000


def cm(numerator, denominator=1):
    """
    Create a Rational measurement in meters from centimeters.
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        cm(9)                # 9 centimeters
        cm(1, 2)             # 1/2 centimeter
        cm(2.54)             # 2.54 centimeters (converted to Rational)
    """
    return Rational(numerator, denominator) / 100


def m(numerator, denominator=1):
    """
    Create a Rational measurement in meters.
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        m(1)                 # 1 meter
        m(1, 2)              # 1/2 meter
        m(2.5)               # 2.5 meters (converted to Rational)
    """
    return Rational(numerator, denominator)


def shaku(numerator, denominator=1):
    """
    Create a Rational measurement in meters from shaku (尺).
    Traditional Japanese carpentry unit.
    
    1 shaku ≈ 303.03 mm (exactly 10/33 meters)
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        shaku(1)             # 1 shaku
        shaku(3, 2)          # 3/2 shaku (1.5 shaku)
        shaku(2.5)           # 2.5 shaku (converted to Rational)
    """
    return Rational(numerator, denominator) * SHAKU_TO_METER


def sun(numerator, denominator=1):
    """
    Create a Rational measurement in meters from sun (寸).
    Traditional Japanese carpentry unit.
    
    1 sun = 1/10 shaku ≈ 30.303 mm
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        sun(1)               # 1 sun
        sun(5)               # 5 sun
        sun(1, 2)            # 1/2 sun
    """
    return Rational(numerator, denominator) * SHAKU_TO_METER / 10


def bu(numerator, denominator=1):
    """
    Create a Rational measurement in meters from bu (分).
    Traditional Japanese carpentry unit.
    
    1 bu = 1/10 sun = 1/100 shaku ≈ 3.0303 mm
    
    Args:
        numerator: The numerator (can be int, float, str, or Rational)
        denominator: The denominator (default=1)
    
    Returns:
        Rational value in meters
    
    Examples:
        bu(1)                # 1 bu
        bu(5)                # 5 bu
        bu(1, 2)             # 1/2 bu
    """
    return Rational(numerator, denominator) * SHAKU_TO_METER / 100


# ============================================================================
# Zero / Equality Test Helper Functions
# ============================================================================

def safe_zero_test(value) -> bool:
    """Test if a value is approximately zero."""
    return safe_compare(value, 0, Comparison.EQ)


def safe_equality_test(value, expected) -> bool:
    """Test if two values are approximately equal."""
    return safe_compare(value, expected, Comparison.EQ)


# Deprecated aliases — use safe_zero_test / safe_equality_test
def zero_test(value) -> bool:
    """Deprecated: use safe_zero_test instead."""
    return safe_zero_test(value)

def equality_test(value, expected) -> bool:
    """Deprecated: use safe_equality_test instead."""
    return safe_equality_test(value, expected)


# ============================================================================
# Parallel and Perpendicular Check Functions
# ============================================================================

def are_vectors_parallel(vector1: Matrix, vector2: Matrix) -> bool:
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
    
    return safe_zero_test(deviation)

def are_vectors_perpendicular(vector1: Matrix, vector2: Matrix) -> bool:
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
    return safe_zero_test(dot_product)


# ============================================================================
# Orientation Class
# ============================================================================

@dataclass(frozen=True)
class Orientation:
    """
    Represents a 3D rotation using a 3x3 rotation matrix.
    Uses sympy for symbolic mathematics.
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
        new_matrix = self.matrix.copy()
        if flip_x:
            new_matrix[0, :] = -new_matrix[0, :]
        if flip_y:
            new_matrix[:, 0] = -new_matrix[:, 0]
        if flip_z:
            new_matrix[:, 2] = -new_matrix[:, 2]
        return Orientation(new_matrix)
    
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
        from sympy import cos, sin, eye
        k = safe_normalize_vector(axis)
        kx, ky, kz = k[0], k[1], k[2]
        K = Matrix([
            [Integer(0), -kz, ky],
            [kz, Integer(0), -kx],
            [-ky, kx, Integer(0)]
        ])
        R = eye(3) + sin(radians) * K + (Integer(1) - cos(radians)) * K * K
        return cls(R)
        
    
    # TODO change veeryhting below to static methods....
    # Static constants for cardinal directions
    @classmethod
    def identity(cls) -> 'Orientation':
        """Identity orientation - facing east (+X)"""
        return cls()

    @classmethod
    def from_z_and_y(cls, z_direction: Direction3D, y_direction: Direction3D) -> 'Orientation':
        """
        Create an Orientation from z and y direction vectors.
        Computes x = y × z to complete the right-handed coordinate system.
        """
        x_direction = cross_product(y_direction, z_direction)
        return cls(Matrix([
            [x_direction[0], y_direction[0], z_direction[0]],
            [x_direction[1], y_direction[1], z_direction[1]],
            [x_direction[2], y_direction[2], z_direction[2]]
        ]))
    
    @classmethod
    def from_z_and_x(cls, z_direction: Direction3D, x_direction: Direction3D) -> 'Orientation':
        """
        Create an Orientation from z and x direction vectors.
        Computes y = z × x to complete the right-handed coordinate system.
        """
        y_direction = cross_product(z_direction, x_direction)
        return cls(Matrix([
            [x_direction[0], y_direction[0], z_direction[0]],
            [x_direction[1], y_direction[1], z_direction[1]],
            [x_direction[2], y_direction[2], z_direction[2]]
        ]))
    
    @classmethod
    def from_x_and_y(cls, x_direction: Direction3D, y_direction: Direction3D) -> 'Orientation':
        """
        Create an Orientation from x and y direction vectors.
        Computes z = x × y to complete the right-handed coordinate system.
        """
        z_direction = cross_product(x_direction, y_direction)
        return cls(Matrix([
            [x_direction[0], y_direction[0], z_direction[0]],
            [x_direction[1], y_direction[1], z_direction[1]],
            [x_direction[2], y_direction[2], z_direction[2]]
        ]))
    
    @classmethod
    def from_axis_angle(cls, axis: Direction3D, radians: Numeric) -> 'Orientation':
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
            [Integer(0), -kz, ky],
            [kz, Integer(0), -kx],
            [-ky, kx, Integer(0)]
        ])
        K_squared = K * K
        I = Matrix.eye(3)
        rotation_matrix = I + sin(radians) * K + (Integer(1) - cos(radians)) * K_squared
        
        return cls(rotation_matrix)
            
    @classmethod
    def from_euleryZYX(cls, yaw: Union[float, int, sp.Basic], pitch: Union[float, int, sp.Basic], roll: Union[float, int, sp.Basic]) -> 'Orientation':
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
        return cls(combined_matrix)

    
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
    
    @classmethod
    def facing_west(cls) -> 'Orientation':
        """
        Horizontal timber with top face up.
        This is the IDENTITY orientation.
        
        - Length: +X (local) = -X (west) in global
        - Width: +Y (local) = -Y (south) in global
        - Facing: +Z (up)
        """
        return cls()  # Identity matrix
    
    @classmethod
    def facing_east(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def facing_north(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def facing_south(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def pointing_up(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def pointing_down(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def pointing_forward(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def pointing_backward(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def pointing_left(cls) -> 'Orientation':
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
        return cls(matrix)
    
    @classmethod
    def pointing_right(cls) -> 'Orientation':
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
        return cls(matrix)
