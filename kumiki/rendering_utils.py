"""
Shared utilities for all rendering backends (Fusion 360, Rhino, FreeCAD, Blender, IFC).

This module contains common functions used across different CAD rendering implementations
to minimize code duplication and ensure consistent behavior.
"""

from sympy import Matrix, Expr
from typing import List, Tuple, Union, Optional
from .timber import *
from .rule import *


def sympy_to_float(value: Union[Expr, float, int]) -> float:
    """
    Convert SymPy expression to Python float.
    
    Args:
        value: SymPy expression, float, or int to convert
        
    Returns:
        Python float value
    """
    return float(value)


def matrix_to_floats(matrix: Matrix) -> List[float]:
    """
    Convert a SymPy matrix to a list of Python floats.
    
    Args:
        matrix: SymPy Matrix to convert
        
    Returns:
        List of float values in row-major order
    """
    return [float(matrix[i]) for i in range(matrix.rows * matrix.cols)]


def extract_rotation_matrix_columns(orientation: Orientation) -> Tuple[V3, V3, V3]:
    """
    Extract the three column vectors from an orientation matrix.
    
    Args:
        orientation: Orientation object with 3x3 rotation matrix
        
    Returns:
        Tuple of (width_direction, height_direction, length_direction) as 3x1 vectors
    """
    # Width direction (X-axis) is first column
    width_dir = Matrix([
        orientation.matrix[0, 0],
        orientation.matrix[1, 0],
        orientation.matrix[2, 0]
    ])
    
    # Height direction (Y-axis) is second column
    height_dir = Matrix([
        orientation.matrix[0, 1],
        orientation.matrix[1, 1],
        orientation.matrix[2, 1]
    ])
    
    # Length direction (Z-axis) is third column
    length_dir = Matrix([
        orientation.matrix[0, 2],
        orientation.matrix[1, 2],
        orientation.matrix[2, 2]
    ])
    
    return width_dir, height_dir, length_dir


def calculate_timber_corners(timber: PerfectTimberWithin) -> List[V3]:
    """
    Get all 8 corners of a timber's bounding box.
    
    Args:
        timber: Timber object to get corners for
        
    Returns:
        List of 8 corner position vectors
    """
    # Get the bottom and top center positions
    bottom_pos = timber.get_bottom_position_global()
    top_pos = timber.get_bottom_position_global() + timber.get_length_direction_global() * timber.length
    
    # Extract direction vectors
    width_dir, height_dir, length_dir = extract_rotation_matrix_columns(timber.orientation)
    
    # Half-size offsets
    half_width = timber.size[0] / 2
    half_height = timber.size[1] / 2
    
    # All 8 corners (4 on bottom, 4 on top)
    corners = [
        # Bottom 4 corners
        bottom_pos + width_dir * half_width + height_dir * half_height,
        bottom_pos + width_dir * half_width - height_dir * half_height,
        bottom_pos - width_dir * half_width + height_dir * half_height,
        bottom_pos - width_dir * half_width - height_dir * half_height,
        # Top 4 corners
        top_pos + width_dir * half_width + height_dir * half_height,
        top_pos + width_dir * half_width - height_dir * half_height,
        top_pos - width_dir * half_width + height_dir * half_height,
        top_pos - width_dir * half_width - height_dir * half_height,
    ]
    
    return corners


def calculate_structure_extents(cut_timbers: List[CutTimber]) -> float:
    """
    Calculate the bounding box extent of all timbers in the structure.
    
    This is used to determine appropriate sizes for infinite geometry
    (e.g., how far to extend semi-infinite prisms for cutting operations).
    
    Args:
        cut_timbers: List of CutTimber objects
        
    Returns:
        Maximum extent (half-size of bounding box) in the same units as timber dimensions
    """
    if not cut_timbers:
        return 1000.0  # Default 10m for empty structures
    
    # Find min and max coordinates across all timbers
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    
    for cut_timber in cut_timbers:
        timber = cut_timber.timber
        
        # Get all 8 corners of this timber
        corners = calculate_timber_corners(timber)
        
        # Update min/max
        for corner in corners:
            x, y, z = float(corner[0]), float(corner[1]), float(corner[2])
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            min_z = min(min_z, z)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            max_z = max(max_z, z)
    
    # Calculate extent (maximum half-dimension)
    extent_x = (max_x - min_x) / 2
    extent_y = (max_y - min_y) / 2
    extent_z = (max_z - min_z) / 2
    
    extent = max(extent_x, extent_y, extent_z)
    
    return extent


def transform_halfspace_to_timber_local(half_plane, timber_orientation: Orientation) -> Tuple[V3, float]:
    """
    Transform a HalfSpace from global coordinates to timber's local coordinate system.
    
    The HalfSpace is already in the timber's LOCAL coordinate system where:
    - X-component is along width direction
    - Y-component is along height direction
    - Z-component is along length direction
    
    For rendering where the timber is created axis-aligned at the origin and then
    transformed, we can use the local normal and offset directly without additional
    transformation.
    
    Args:
        half_plane: HalfSpace object with normal and offset
        timber_orientation: Timber's orientation matrix (kept for API compatibility)
        
    Returns:
        Tuple of (local_normal_vector, local_offset)
    """
    # Extract local normal and offset
    local_normal = half_plane.normal
    local_offset = half_plane.offset
    
    # The local normal is already in the correct space for component rendering
    # No transformation needed!
    component_normal = local_normal
    component_offset = local_offset
    
    return component_normal, float(component_offset)

