"""
FreeCAD rendering module for Kumiki timber framing system using CSG.

This module provides functions to render timber structures in FreeCAD
using the CutCSG system for constructive solid geometry operations.

UNIT CONVERSION:
    Kumiki uses METERS internally, FreeCAD uses MILLIMETERS by default.
    This module handles conversion using these helper functions:
    - distance_to_mm(value): Convert distances/positions (meters -> mm)
    - direction_to_float(value): Convert direction vectors (no scaling)
    - meters_to_mm(value): Convert float meters to millimeters
    
    All geometric values are converted at the boundary between Kumiki
    and FreeCAD to ensure consistency and avoid unit mixing bugs.

Usage (as FreeCAD macro):
    # Import this module in your FreeCAD macro
    import kumiki_render_freecad
    
    # Your timber structure code here...
    cut_timbers = [...]
    
    # Clear and render
    giraffe_render_freecad.clear_document()
    giraffe_render_freecad.render_multiple_timbers(cut_timbers)
"""

import sys
import os
from typing import Optional, List, Tuple
import traceback
import math

# Add parent directory to path to import Kumiki modules
script_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# FreeCAD imports (available when running as a FreeCAD macro)
try:
    import FreeCAD
    import Part
    from FreeCAD import Base, Vector, Rotation, Placement
except ImportError:
    print("Warning: FreeCAD modules not available.")
    print("This module is designed to run as a FreeCAD macro.")

# Kumiki imports
from sympy import Matrix
from kumiki import CutTimber, Timber, Frame
from kumiki.timber import JointAccessory, Peg, Wedge, PegShape
from kumiki.rule import Orientation
from kumiki.cutcsg import (
    CutCSG, HalfSpace, RectangularPrism, Cylinder, SolidUnion, Difference, ConvexPolygonExtrusion
)
from kumiki.rendering_utils import (
    calculate_structure_extents,
    sympy_to_float as _sympy_to_float_base
)


# ============================================================================
# Unit Conversion Helpers
# ============================================================================
# Kumiki uses METERS as base unit, FreeCAD uses MILLIMETERS by default.
# These helpers ensure we convert correctly and avoid mixing units.

def distance_to_mm(value):
    """
    Convert a distance/position from meters to millimeters.
    Use for: positions, dimensions, lengths, radii, offsets.
    """
    return _sympy_to_float_base(value) * 1000.0

def direction_to_float(value):
    """
    Convert a direction vector component to float (no unit conversion).
    Use for: normals, axis directions, rotation matrix elements.
    """
    return _sympy_to_float_base(value)

def meters_to_mm(meters: float) -> float:
    """
    Convert a float value from meters to millimeters.
    Use for: extent parameters and other runtime float values.
    """
    return meters * 1000.0

# Legacy name for backward compatibility (use distance_to_mm for new code)
def sympy_to_float(value):
    """
    DEPRECATED: Use distance_to_mm() or direction_to_float() for clarity.
    Convert SymPy expression to float and convert from meters to millimeters.
    """
    return distance_to_mm(value)


def get_active_document(doc_name: str = "Kumiki") -> Optional['FreeCAD.Document']:
    """
    Get or create a FreeCAD document.
    
    Args:
        doc_name: Name for the document (default: "Kumiki")
        
    Returns:
        FreeCAD.Document instance or None on error
    """
    try:
        doc = FreeCAD.activeDocument()
        if doc is None:
            doc = FreeCAD.newDocument(doc_name)
        return doc
    except Exception as e:
        print(f"Error getting active document: {str(e)}")
        traceback.print_exc()
        return None


def create_new_document(doc_name: str = "Kumiki") -> Optional['FreeCAD.Document']:
    """
    Create a new FreeCAD document.
    
    Args:
        doc_name: Name for the document (default: "Kumiki")
        
    Returns:
        FreeCAD.Document instance or None on error
    """
    try:
        # Close active document if any
        active_doc = FreeCAD.activeDocument()
        if active_doc is not None:
            FreeCAD.closeDocument(active_doc.Name)
        
        # Create new document
        doc = FreeCAD.newDocument(doc_name)
        return doc
    except Exception as e:
        print(f"Error creating new document: {str(e)}")
        traceback.print_exc()
        return None


def clear_document():
    """Clear all objects from the current document."""
    try:
        doc = get_active_document()
        if doc is None:
            print("No active document found")
            return None
        
        # Remove all objects
        for obj in doc.Objects:
            doc.removeObject(obj.Name)
        
        print("Document cleared")
        return True
    except Exception as e:
        print(f"Error clearing document: {e}")
        traceback.print_exc()
        return False


def create_placement_from_orientation(position: Matrix, orientation: Orientation) -> 'Base.Placement':
    """
    Convert sympy position vector and Orientation to FreeCAD Placement.
    
    Args:
        position: 3x1 sympy Matrix representing position
        orientation: Orientation object with 3x3 rotation matrix
        
    Returns:
        Base.Placement for use in FreeCAD
    """
    # Extract rotation matrix values (convert sympy expressions to floats)
    # The orientation matrix columns are [width_direction, height_direction, length_direction]
    # For FreeCAD, we want to create a coordinate system where:
    # - X-axis (col 0) = width_direction
    # - Y-axis (col 1) = height_direction  
    # - Z-axis (col 2) = length_direction
    r00 = direction_to_float(orientation.matrix[0, 0])
    r01 = direction_to_float(orientation.matrix[0, 1])
    r02 = direction_to_float(orientation.matrix[0, 2])
    r10 = direction_to_float(orientation.matrix[1, 0])
    r11 = direction_to_float(orientation.matrix[1, 1])
    r12 = direction_to_float(orientation.matrix[1, 2])
    r20 = direction_to_float(orientation.matrix[2, 0])
    r21 = direction_to_float(orientation.matrix[2, 1])
    r22 = direction_to_float(orientation.matrix[2, 2])
    
    # Extract translation values (positions - convert to mm)
    tx = distance_to_mm(position[0])
    ty = distance_to_mm(position[1])
    tz = distance_to_mm(position[2])
    
    # Create FreeCAD Matrix (4x4 transformation matrix)
    matrix = Base.Matrix(
        r00, r01, r02, tx,
        r10, r11, r12, ty,
        r20, r21, r22, tz,
        0.0, 0.0, 0.0, 1.0
    )
    
    # Create Placement from matrix
    placement = Base.Placement(matrix)
    
    return placement


def create_prism_shape(prism: RectangularPrism, infinite_extent: float = 10000.0) -> 'Part.Shape':
    """
    Create a FreeCAD shape from a RectangularPrism CSG.
    
    The prism is created axis-aligned where:
    - Width (size[0]) is along X axis
    - Height (size[1]) is along Y axis
    - Length is along Z axis from start_distance to end_distance
    
    Then the prism's orientation and position are applied.
    
    Args:
        prism: RectangularPrism CSG object
        infinite_extent: Extent to use for infinite dimensions (in meters)
        
    Returns:
        Part.Shape representing the prism
    """
    try:
        # Extract dimensions (convert to mm)
        width = distance_to_mm(prism.size[0])
        height = distance_to_mm(prism.size[1])
        
        # Get start and end distances along the length axis
        # Convert infinite_extent from meters to mm for consistency
        # hack divide by 5 to make it work will with half space cuts at an angle
        LARGE_NUMBER_MM = meters_to_mm(infinite_extent/5)
        
        if prism.start_distance is None and prism.end_distance is None:
            # Fully infinite prism - extend both ways
            start_dist = -LARGE_NUMBER_MM
            end_dist = LARGE_NUMBER_MM
        elif prism.start_distance is None:
            # Semi-infinite extending in negative direction
            end_dist = distance_to_mm(prism.end_distance)
            start_dist = end_dist - 2 * LARGE_NUMBER_MM
        elif prism.end_distance is None:
            # Semi-infinite extending in positive direction
            start_dist = distance_to_mm(prism.start_distance)
            end_dist = start_dist + 2 * LARGE_NUMBER_MM
        else:
            # Finite prism
            start_dist = distance_to_mm(prism.start_distance)
            end_dist = distance_to_mm(prism.end_distance)
        
        length = end_dist - start_dist
        
        # Create box at origin (corner at origin, extending in +X, +Y, +Z)
        box = Part.makeBox(width, height, length)
        
        # We need to center the cross-section (X and Y) and position Z at start_dist
        # This will be done via a local Placement transformation
        # NOTE: We DON'T use box.translate() because it modifies vertices, 
        # and then the global Placement won't compose correctly
        local_offset = Vector(-width/2, -height/2, start_dist)
        box.Placement = Base.Placement(local_offset, Base.Rotation())
        
        # Only apply the prism's orientation and position if it's not at origin with identity orientation
        # For local coordinates (used in render_timber_with_cuts_csg_local), prism is at origin with identity
        # The global transformation will be applied later in render_multiple_timbers
        from sympy import Matrix, eye
        is_identity = (prism.transform.orientation.matrix == eye(3))
        is_at_origin = (prism.transform.position == Matrix([0, 0, 0]))
        
        if not is_identity or not is_at_origin:
            # Apply the prism's orientation and position
            prism_placement = create_placement_from_orientation(prism.transform.position, prism.transform.orientation)
            box.Placement = prism_placement.multiply(box.Placement)
        
        return box
        
    except Exception as e:
        print(f"Error creating prism: {e}")
        #traceback.print_exc()
        return None


def create_cylinder_shape(cylinder: Cylinder) -> 'Part.Shape':
    """
    Create a FreeCAD shape from a Cylinder CSG.
    
    The cylinder is created with its axis aligned along +Z, then rotated to match
    axis_direction and translated to the cylinder's position.
    
    Args:
        cylinder: Cylinder CSG object
        
    Returns:
        Part.Shape representing the cylinder
    """
    try:
        # Extract parameters (convert to mm)
        radius = distance_to_mm(cylinder.radius)
        
        if cylinder.start_distance is None or cylinder.end_distance is None:
            raise ValueError("Cannot render infinite cylinder - must have finite start and end distances")
        
        start_dist = distance_to_mm(cylinder.start_distance)
        end_dist = distance_to_mm(cylinder.end_distance)
        height = end_dist - start_dist
        
        # Get axis direction (normalized)
        axis_dir = cylinder.axis_direction
        axis_norm = axis_dir.norm()
        axis_normalized = axis_dir / axis_norm
        
        # Create cylinder along +Z axis at origin
        cyl = Part.makeCylinder(radius, height)
        
        # Translate to start at start_dist along Z
        cyl.translate(Vector(0, 0, start_dist))
        
        # Now we need to rotate the cylinder from +Z axis to the axis_direction
        # and translate it to the cylinder's position
        z_axis = Matrix([0, 0, 1])
        
        # Check if axis is already along Z
        dot_with_z = (axis_normalized.T * z_axis)[0, 0]
        is_aligned_with_z = abs(direction_to_float(dot_with_z) - 1.0) < 0.001
        
        # Check if position is at origin
        is_at_origin = (cylinder.position == Matrix([0, 0, 0]))
        
        # Only apply transformation if needed
        if not is_aligned_with_z or not is_at_origin:
            # Calculate rotation if not aligned with Z
            if not is_aligned_with_z:
                # Use Rodrigues' rotation formula
                # Rotation axis: cross product of z_axis and axis_normalized
                rotation_axis = z_axis.cross(axis_normalized)
                rotation_axis_norm = rotation_axis.norm()
                
                if direction_to_float(rotation_axis_norm) > 0.001:  # Not parallel
                    rotation_axis_unit = rotation_axis / rotation_axis_norm
                    
                    # Rotation angle (unitless, no conversion needed)
                    cos_angle = direction_to_float(dot_with_z)
                    angle = math.acos(max(-1.0, min(1.0, cos_angle)))  # Clamp to avoid numerical errors
                    
                    # Create rotation using axis and angle (direction vector, no unit conversion)
                    axis_vec = Vector(
                        direction_to_float(rotation_axis_unit[0]),
                        direction_to_float(rotation_axis_unit[1]),
                        direction_to_float(rotation_axis_unit[2])
                    )
                    cyl.rotate(Vector(0, 0, 0), axis_vec, math.degrees(angle))
            
            # Apply translation to cylinder's position (convert to mm)
            if not is_at_origin:
                pos = Vector(
                    distance_to_mm(cylinder.position[0]),
                    distance_to_mm(cylinder.position[1]),
                    distance_to_mm(cylinder.position[2])
                )
                cyl.translate(pos)
        
        return cyl
        
    except Exception as e:
        print(f"Error creating cylinder: {e}")
        traceback.print_exc()
        return None


def create_convex_polygon_extrusion_shape(extrusion: ConvexPolygonExtrusion) -> 'Part.Shape':
    """
    Create a FreeCAD shape from a ConvexPolygonExtrusion CSG.
    
    The polygon is extruded along the Z axis from z=start_distance to z=end_distance,
    then the orientation and position are applied.
    
    For infinite extrusions (start_distance or end_distance is None), the extrusion 
    cannot be rendered and None is returned.
    
    Args:
        extrusion: ConvexPolygonExtrusion CSG object
        
    Returns:
        Part.Shape representing the extruded polygon, or None if infinite
    """
    try:
        # Check if the extrusion is finite
        if extrusion.start_distance is None or extrusion.end_distance is None:
            print(f"Warning: Cannot render infinite ConvexPolygonExtrusion")
            return None
        
        # Convert 2D points to FreeCAD Vectors (in mm)
        # Points are in the XY plane (Z=0)
        points_2d = [
            Vector(distance_to_mm(pt[0]), distance_to_mm(pt[1]), 0.0)
            for pt in extrusion.points
        ]
        
        # Close the polygon by adding the first point at the end
        polygon_wire = Part.makePolygon(points_2d + [points_2d[0]])
        
        # Create a face from the polygon
        polygon_face = Part.Face(polygon_wire)
        
        # Calculate extrusion length from start_distance to end_distance
        extrusion_length = extrusion.end_distance - extrusion.start_distance
        length_mm = distance_to_mm(extrusion_length)
        extrusion_vector = Vector(0, 0, length_mm)
        solid = polygon_face.extrude(extrusion_vector)
        
        # Translate to start_distance position in local coordinates
        start_mm = distance_to_mm(extrusion.start_distance)
        solid.translate(Vector(0, 0, start_mm))
        
        # Apply the extrusion's orientation and position if not at origin with identity orientation
        from sympy import Matrix, eye
        is_identity = (extrusion.transform.orientation.matrix == eye(3))
        is_at_origin = (extrusion.transform.position == Matrix([0, 0, 0]))
        
        if not is_identity or not is_at_origin:
            # Apply the extrusion's orientation and position
            extrusion_placement = create_placement_from_orientation(extrusion.transform.position, extrusion.transform.orientation)
            solid.Placement = extrusion_placement.multiply(solid.Placement)
        
        return solid
        
    except Exception as e:
        print(f"Error creating convex polygon extrusion: {e}")
        traceback.print_exc()
        return None


def render_csg_shape(csg: CutCSG, timber: Optional[Timber] = None, 
                     infinite_extent: float = 10000.0,
                     halfspace_as_solid: bool = False) -> Optional['Part.Shape']:
    """
    Render a CSG object to a FreeCAD shape.
    
    This recursively processes CSG operations (Union, Difference, etc.) and
    creates the corresponding FreeCAD geometry.
    
    Args:
        csg: CSG object to render
        timber: Optional timber object (needed for coordinate transformations during cuts)
        infinite_extent: Extent to use for infinite geometry (in meters)
        
    Returns:
        Part.Shape, or None if creation failed
    """
    if isinstance(csg, RectangularPrism):
        return create_prism_shape(csg, infinite_extent)
    
    elif isinstance(csg, Cylinder):
        return create_cylinder_shape(csg)
    
    elif isinstance(csg, ConvexPolygonExtrusion):
        return create_convex_polygon_extrusion_shape(csg)
    
    elif isinstance(csg, HalfSpace):
        return create_halfspace_shape(csg, infinite_extent = infinite_extent, render_as_solid = True)
    
    elif isinstance(csg, SolidUnion):
        return render_union(csg, timber, infinite_extent)
    
    elif isinstance(csg, Difference):
        return render_difference(csg, timber, infinite_extent)
    
    else:
        return None


def render_union(union: SolidUnion, timber: Optional[Timber] = None, 
                 infinite_extent: float = 10000.0) -> Optional['Part.Shape']:
    """
    Render a SolidUnion CSG operation.
    
    Args:
        union: SolidUnion CSG object
        timber: Optional timber object
        infinite_extent: Extent to use for infinite geometry
        
    Returns:
        Combined Part.Shape, or None if creation failed
    """
    if not union.children:
        print("Warning: Empty union")
        return None
    
    # Render the first child
    result_shape = render_csg_shape(union.children[0], timber, infinite_extent)
    
    if result_shape is None:
        print("Failed to render first child of union")
        return None
    
    # Union with remaining children
    for i, child in enumerate(union.children[1:], start=1):
        child_shape = render_csg_shape(child, timber, infinite_extent)
        
        if child_shape is None:
            print(f"Failed to render union child {i}")
            continue
        
        # Perform union operation
        try:
            result_shape = result_shape.fuse(child_shape)
        except Exception as e:
            print(f"Error performing union fuse with child {i}: {e}")
            continue
    
    return result_shape


def create_halfspace_shape(half_plane: HalfSpace, infinite_extent: float = 10000.0, render_as_solid: bool = True) -> Optional['Part.Shape']:
    """
    Create a shape representing the half-space defined by a HalfSpace.
    
    The HalfSpace keeps all points P where (P · normal) >= offset.
    
    Args:
        half_plane: HalfSpace object defining the half-space
        render_as_solid: If True, renders as a solid box filling the half-space.
                        If False, renders as a thin plane surface. Set to False for debugging only!
        infinite_extent: Extent to use for the plane/box (in meters)
        
        
    Returns:
        Part.Shape representing the half-space (plane or box), or None if creation failed
    """
    try:
        # HalfSpace is in local coordinates
        plane_normal = half_plane.normal
        plane_offset = distance_to_mm(half_plane.offset)  # Convert meters to mm
        
        # The plane equation is: normal · P = offset
        # Find a point on the plane
        normal_norm = plane_normal.norm()
        normal_normalized = plane_normal / normal_norm
        
        # Point on the plane along the normal direction
        plane_point = normal_normalized * plane_offset
        plane_point_vec = Vector(
            direction_to_float(plane_point[0]),
            direction_to_float(plane_point[1]),
            direction_to_float(plane_point[2])
        )
        
        # Normal vector (direction, not position - don't scale)
        normal_vec = Vector(
            direction_to_float(plane_normal[0]),
            direction_to_float(plane_normal[1]),
            direction_to_float(plane_normal[2])
        )
        
        # Build rotation to align Z-axis with the plane normal
        normalized = normal_vec.normalize()
        
        # Find the rotation that takes the +Z axis to the normal direction
        z_axis = Vector(0, 0, 1)
        dot_product = z_axis.dot(normalized)
        
        if abs(dot_product - 1.0) < 0.001:
            # Normal is already aligned with +Z, no rotation needed
            rotation = Base.Rotation()
        elif abs(dot_product + 1.0) < 0.001:
            # Normal is opposite to +Z, rotate 180° around X axis
            rotation = Base.Rotation(Vector(1, 0, 0), 180)
        else:
            # General case: rotate around the cross product axis
            axis = z_axis.cross(normalized)
            angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot_product))))
            rotation = Base.Rotation(axis, angle_deg)
        
        if render_as_solid:
            # Render as a solid box filling the half-space
            BOX_SIZE = meters_to_mm(infinite_extent) * 2  # Double for safety, in mm
            
            # Create box centered at origin, extending in +Z direction
            box = Part.makeBox(BOX_SIZE, BOX_SIZE, BOX_SIZE)
            box.translate(Vector(-BOX_SIZE/2, -BOX_SIZE/2, 0))  # Box extends from 0 to BOX_SIZE in Z
            
            # Create placement with rotation and translation to plane point
            placement = Base.Placement(plane_point_vec, rotation)
            box.Placement = placement.multiply(box.Placement)
            
            return box
        else:
            # Render as a thin plane surface
            PLANE_SIZE = meters_to_mm(infinite_extent) * 2  # Size of the plane, in mm
            
            # Create a rectangular plane in the XY plane centered at origin
            plane = Part.makePlane(PLANE_SIZE, PLANE_SIZE, 
                                  Vector(-PLANE_SIZE/2, -PLANE_SIZE/2, 0))
            
            # Create placement with rotation and translation to plane point
            placement = Base.Placement(plane_point_vec, rotation)
            plane.Placement = placement.multiply(plane.Placement)
            
            return plane
        
    except Exception as e:
        print(f"Error creating HalfSpace shape: {e}")
        traceback.print_exc()
        return None


def apply_halfspace_cut(shape: 'Part.Shape', half_plane: HalfSpace, 
                       timber: Optional[Timber] = None, 
                       infinite_extent: float = 10000.0) -> 'Part.Shape':
    """
    Apply a HalfSpace cut to a shape using a large box and boolean difference.
    
    The HalfSpace is defined in the timber's local coordinates.
    
    Args:
        shape: Shape to cut
        half_plane: HalfSpace defining the cut (in timber's local coordinates)
        timber: Timber object (needed for coordinate transformation)
        infinite_extent: Extent to use for the cutting box (in meters)
        
    Returns:
        Modified shape after cut
    """
    try:
        # HalfSpace is already in local coordinates, use as-is
        plane_normal = half_plane.normal
        plane_offset = distance_to_mm(half_plane.offset)  # Convert meters to mm
        
        # The plane equation is: normal · P = offset
        # Find a point on the plane
        normal_norm = plane_normal.norm()
        normal_normalized = plane_normal / normal_norm
        
        # Point on the plane along the normal direction
        # plane_offset is in mm, normal_normalized is unitless, so plane_point is in mm
        plane_point = normal_normalized * plane_offset
        plane_point_vec = Vector(
            direction_to_float(plane_point[0]),  # Already in mm (from plane_offset), just convert to float
            direction_to_float(plane_point[1]),
            direction_to_float(plane_point[2])
        )
        
        # Normal vector (direction, not position - don't scale)
        normal_vec = Vector(
            direction_to_float(plane_normal[0]),
            direction_to_float(plane_normal[1]),
            direction_to_float(plane_normal[2])
        )
        
        # Create a large cutting box
        # Convert infinite_extent from meters to mm
        BOX_SIZE = meters_to_mm(infinite_extent) * 2  # Double for safety, in mm
        
        # HalfSpace keeps points where (normal · P >= offset)
        # When used in Difference(timber, halfspace), we SUBTRACT what the HalfSpace KEEPS
        # So we need to remove the region where (normal · P >= offset)
        # 
        # Strategy: Create a box that fills the half-space where (normal · P >= offset)
        # by positioning it on the plane and extending in the +normal direction
        
        # Create box centered at origin
        cutting_box = Part.makeBox(BOX_SIZE, BOX_SIZE, BOX_SIZE)
        cutting_box.translate(Vector(-BOX_SIZE/2, -BOX_SIZE/2, 0))  # Box extends from 0 to BOX_SIZE in Z
        
        # Build rotation to align Z-axis with the plane normal
        # After rotation, the box will extend from the plane in the -normal direction
        normalized = normal_vec.normalize()
        
        # For the rotation, we need to find the rotation that takes the +Z axis to the normal direction
        # Use Rodrigues' rotation formula or build an orthonormal basis
        
        # Find the angle between +Z and the normal
        z_axis = Vector(0, 0, 1)
        dot_product = z_axis.dot(normalized)
        
        if abs(dot_product - 1.0) < 0.001:
            # Normal is already aligned with +Z, no rotation needed
            rotation = Base.Rotation()
        elif abs(dot_product + 1.0) < 0.001:
            # Normal is opposite to +Z, rotate 180° around X axis
            rotation = Base.Rotation(Vector(1, 0, 0), 180)
        else:
            # General case: rotate around the cross product axis
            axis = z_axis.cross(normalized)
            angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot_product))))
            rotation = Base.Rotation(axis, angle_deg)
        
        # Create placement with rotation and translation to plane point
        placement = Base.Placement(plane_point_vec, rotation)
        cutting_box.Placement = placement.multiply(cutting_box.Placement)
        
        # Perform boolean difference: shape - cutting_box
        result_shape = shape.cut(cutting_box)
        
        return result_shape
        
    except Exception as e:
        print(f"  Error applying HalfSpace cut: {e}")
        traceback.print_exc()
        return shape  # Return original shape on error


def render_difference(difference: Difference, timber: Optional[Timber] = None, 
                      infinite_extent: float = 10000.0) -> Optional['Part.Shape']:
    """
    Render a Difference CSG operation.
    
    For HalfSpace cuts, uses large box and boolean operations.
    For other CSG types, creates the solid and performs boolean difference.
    
    Args:
        difference: Difference CSG object
        timber: Optional timber object (needed for coordinate transformations during cuts)
        infinite_extent: Extent to use for infinite geometry (in meters)
        
    Returns:
        Resulting Part.Shape after subtraction, or None if creation failed
    """
    # Render the base shape
    base_shape = render_csg_shape(difference.base, timber, infinite_extent)
    
    if base_shape is None:
        return None
    
    # Flatten the subtract list to handle nested SolidUnions
    # This ensures HalfSpace objects within SolidUnions are handled correctly
    flattened_subtracts = []
    for sub_csg in difference.subtract:
        if isinstance(sub_csg, SolidUnion):
            # Recursively flatten nested unions
            def _flatten_union_recursive(union_csg, result_list):
                for child in union_csg.children:
                    if isinstance(child, SolidUnion):
                        _flatten_union_recursive(child, result_list)
                    else:
                        result_list.append(child)
            _flatten_union_recursive(sub_csg, flattened_subtracts)
        else:
            flattened_subtracts.append(sub_csg)
    
    # Subtract each child from the flattened list
    for i, subtract_csg in enumerate(flattened_subtracts):
        # Special handling for HalfSpace cuts
        if isinstance(subtract_csg, HalfSpace):
            base_shape = apply_halfspace_cut(base_shape, subtract_csg, timber, infinite_extent)
            continue
        
        # For other CSG types, render and perform boolean difference
        subtract_shape = render_csg_shape(subtract_csg, timber, infinite_extent)
        
        if subtract_shape is None:
            print(f"  Warning: Failed to render subtract child {i+1}")
            continue
        
        # Perform difference operation
        try:
            base_shape = base_shape.cut(subtract_shape)
        except Exception as e:
            print(f"  Error performing difference with child {i+1}: {e}")
            continue
    
    return base_shape


def render_accessory_at_origin(accessory: JointAccessory, component_name: str, 
                               infinite_extent: float = 10000.0) -> Optional['Part.Shape']:
    """
    Render a JointAccessory at the origin in FreeCAD using its CSG representation.
    
    The accessory is created at origin with identity orientation. Transform should be applied later.
    
    Args:
        accessory: JointAccessory object (Peg, Wedge, etc.)
        component_name: Name for the component (for error messages)
        infinite_extent: Extent for infinite geometry (in meters)
        
    Returns:
        Part.Shape or None if rendering failed
    """
    try:
        # Get the CSG representation from the accessory
        accessory_csg = accessory.render_csg_local()
        
        # Render the CSG to a shape
        shape = render_csg_shape(
            csg=accessory_csg,
            timber=None,  # Accessory CSG is already in local space
            infinite_extent=infinite_extent
        )
        
        if shape is None:
            print(f"Failed to render accessory geometry for {component_name}")
            return None
        
        return shape
        
    except Exception as e:
        print(f"Error rendering accessory at origin: {e}")
        traceback.print_exc()
        return None


def render_frame(frame: Frame, base_name: str = None, doc: Optional['FreeCAD.Document'] = None) -> int:
    """
    Render a complete Frame in FreeCAD.
    
    Args:
        frame: Frame object containing cut timbers and accessories
        base_name: Optional base name override (defaults to frame.name or "Timber")
        doc: Optional FreeCAD document (creates new if not provided)
    
    Returns:
        Number of objects created
    """
    name = base_name if base_name is not None else (frame.name or "Timber")
    return render_multiple_timbers(
        cut_timbers=frame.cut_timbers,
        joint_accessories=frame.accessories,
        base_name=name,
        doc=doc
    )


def render_multiple_timbers(cut_timbers: List[CutTimber], base_name: str = "Timber", 
                           joint_accessories: Optional[List[JointAccessory]] = None,
                           doc: Optional['FreeCAD.Document'] = None) -> int:
    """
    Render multiple CutTimber objects and optional joint accessories in FreeCAD.
    
    Component names are automatically determined from:
    1. CutTimber.name if set
    2. CutTimber.timber.name if set
    3. {base_name}_{index} as fallback
    
    Args:
        cut_timbers: List of CutTimber objects to render
        base_name: Base name for the objects (used if timber has no name)
        joint_accessories: Optional list of JointAccessory objects to render (in global space)
        doc: Optional FreeCAD document to render into (creates/uses active if None)
        
    Returns:
        Number of successfully rendered timbers (does not include accessories)
    """
    if doc is None:
        doc = get_active_document()
    
    if not doc:
        print("No active document found")
        return 0
    
    print(f"\n=== Rendering {len(cut_timbers)} timbers ===")
    
    # Calculate structure extents for intelligent sizing of infinite geometry
    structure_extent = calculate_structure_extents(cut_timbers)
    infinite_geometry_extent = structure_extent * 100  # 10x for infinite geometry
    
    # Render all timbers
    success_count = 0
    
    for i, cut_timber in enumerate(cut_timbers):
        # Use the timber's name if available, otherwise use index
        if cut_timber.name:
            component_name = cut_timber.name
        elif hasattr(cut_timber, 'timber') and cut_timber.timber.name:
            component_name = cut_timber.timber.name
        else:
            component_name = f"{base_name}_{i}"
        
        # #region agent log
        import json
        import datetime
        try:
            with open('/Users/peter.lu/kitchen/faucet/kumiki-proto/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({
                    'location': 'giraffe_render_freecad.py:754',
                    'message': 'Rendering cut timber in FreeCAD',
                    'data': {
                        'index': i,
                        'component_name': component_name,
                        'timber_name': cut_timber.timber.name if hasattr(cut_timber.timber, 'name') else 'unnamed',
                        'cuts_count': len(cut_timber.cuts)
                    },
                    'timestamp': int(datetime.datetime.now().timestamp() * 1000),
                    'sessionId': 'debug-session',
                    'hypothesisId': 'H2'
                }) + '\n')
        except: pass
        # #endregion
        
        try:
            # Get the timber with cuts applied in LOCAL coordinates
            csg = cut_timber.render_timber_with_cuts_csg_local()
            
            # Render the CSG to a shape (in local coordinates)
            shape = render_csg_shape(csg, cut_timber.timber, infinite_geometry_extent)
            
            if shape is not None:
                # Add to document
                obj = doc.addObject("Part::Feature", component_name)
                obj.Shape = shape
                
                # Apply the timber's global transformation (position + orientation)
                # The shape already has local centering placement applied
                timber = cut_timber.timber
                global_placement = create_placement_from_orientation(timber.get_bottom_position_global(), timber.orientation)
                
                # Compose placements: global * local
                # The shape was created with a local centering placement, now apply global transform
                local_placement = shape.Placement
                obj.Placement = global_placement.multiply(local_placement)
                
                # Recompute to update bounding box
                doc.recompute()
                
                success_count += 1
                print(f"  ✓ {component_name}")
            else:
                print(f"  ✗ {component_name} - failed to create shape")
                    
        except Exception as e:
            print(f"  ✗ {component_name} - {e}")
            traceback.print_exc()
    
    # Render joint accessories if provided
    accessory_count = 0
    if joint_accessories:
        print(f"\n=== Rendering {len(joint_accessories)} accessories ===")
        
        for i, accessory in enumerate(joint_accessories):
            try:
                # Determine accessory name based on type
                if isinstance(accessory, Peg):
                    accessory_name = f"Peg_{i+1}"
                    shape_str = accessory.shape.value
                    size_mm = distance_to_mm(accessory.size)
                    print(f"Creating {accessory_name} ({shape_str}, size={size_mm:.1f}mm)...")
                elif isinstance(accessory, Wedge):
                    accessory_name = f"Wedge_{i+1}"
                    width_mm = distance_to_mm(accessory.base_width)
                    height_mm = distance_to_mm(accessory.height)
                    print(f"Creating {accessory_name} (width={width_mm:.1f}mm, height={height_mm:.1f}mm)...")
                else:
                    accessory_name = f"Accessory_{i+1}"
                    print(f"Creating {accessory_name} ({type(accessory).__name__})...")
                
                # Render the accessory at origin using its CSG representation
                shape = render_accessory_at_origin(accessory, accessory_name, infinite_geometry_extent)
                
                if shape is not None:
                    # Add to document
                    obj = doc.addObject("Part::Feature", accessory_name)
                    obj.Shape = shape

                    if hasattr(accessory, "transform"):
                        # Accessory position and orientation are already in global space
                        # Simply use them directly to create the global placement
                        global_placement = create_placement_from_orientation(accessory.transform.position, accessory.transform.orientation)

                        # Compose placements: global * local
                        # The shape already has local centering placement applied (e.g., for prism cross-section centering)
                        local_placement = shape.Placement
                        obj.Placement = global_placement.multiply(local_placement)
                    
                    # Recompute to update bounding box
                    doc.recompute()
                    
                    accessory_count += 1
                    print(f"  ✓ {accessory_name}")
                else:
                    print(f"  ✗ {accessory_name} - failed to create shape")
                    
            except Exception as e:
                print(f"  ✗ Error creating accessory {i+1}: {e}")
                traceback.print_exc()
        
        print(f"\n=== Complete: {accessory_count}/{len(joint_accessories)} accessories ===")
    
    # Recompute document to update display
    doc.recompute()
    
    # Summary
    print(f"\n=== Complete: {success_count}/{len(cut_timbers)} timbers ===")
    
    return success_count


def save_document(doc: 'FreeCAD.Document', filepath: str) -> bool:
    """
    Save a FreeCAD document to file.
    
    Args:
        doc: FreeCAD document to save
        filepath: Path to save to (should end in .FCStd)
        
    Returns:
        True if save succeeded, False otherwise
    """
    try:
        # Ensure filepath has .FCStd extension
        if not filepath.endswith('.FCStd'):
            filepath += '.FCStd'
        
        doc.saveAs(filepath)
        print(f"\n✓ Saved document to: {filepath}")
        return True
    except Exception as e:
        print(f"\n✗ Error saving document: {e}")
        traceback.print_exc()
        return False



