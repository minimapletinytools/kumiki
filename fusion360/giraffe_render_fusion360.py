"""
Fusion 360 rendering module for Kumiki timber framing system using CSG.

This module provides functions to render timber structures in Autodesk Fusion 360
using the CutCSG system for constructive solid geometry operations.
"""

# Module load tracker - must use app.log for Fusion 360 console
try:
    app = adsk.core.Application.get()
    if app:
        app.log("🦒 MODULE RELOAD TRACKER: giraffe_render_fusion360.py LOADED - Recursive Union Flattening v3 🦒")
except:
    pass  # Ignore if app not available during import

import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import time
from typing import Optional, List, Tuple
from sympy import Matrix, Float
from kumiki import CutTimber, Timber, JointAccessory, Peg, PegShape, Wedge, Frame
from kumiki.rule import Orientation
from kumiki.cutcsg import (
    CutCSG, HalfSpace, RectangularPrism, Cylinder, SolidUnion, Difference, ConvexPolygonExtrusion
)
from kumiki.rendering_utils import (
    calculate_structure_extents,
    transform_halfspace_to_timber_local,
    sympy_to_float
)


def get_fusion_app() -> Optional[adsk.core.Application]:
    """Get the Fusion 360 application instance."""
    try:
        app = adsk.core.Application.get()
        return app
    except:
        return None


def get_active_design() -> Optional[adsk.fusion.Design]:
    """Get the active design in Fusion 360."""
    app = get_fusion_app()
    if not app:
        return None
    
    try:
        design = app.activeProduct
        if isinstance(design, adsk.fusion.Design):
            return design
        else:
            return None
    except:
        return None


def clear_design():
    """Clear all objects from the current design and ensure it's an assembly."""
    design = get_active_design()
    if not design:
        print("No active design found")
        return False
    
    app = get_fusion_app()
    
    # Ensure we're working with an assembly design
    # Part designs can only contain one component, but we need multiple
    if design.designType != adsk.fusion.DesignTypes.DirectDesignType:
        print(f"Converting to DirectDesign (Assembly) mode...")
        if app:
            app.log("Converting to DirectDesign (Assembly) mode...")
        
        try:
            design.designType = adsk.fusion.DesignTypes.DirectDesignType
            print("Successfully converted to DirectDesign mode")
            if app:
                app.log("Successfully converted to DirectDesign mode")
        except Exception as e:
            error_msg = f"ERROR: Failed to convert to DirectDesign mode: {e}\nMultiple components cannot be created in Part Design mode. Please create a new Design or change to DirectDesign mode manually."
            print(error_msg)
            if app:
                app.log(error_msg)
            return False
    
    root = design.rootComponent
    
    # Remove all occurrences
    while root.occurrences.count > 0:
        root.occurrences.item(0).deleteMe()
    
    # Remove all bodies
    while root.bRepBodies.count > 0:
        root.bRepBodies.item(0).deleteMe()
    
    print("Design cleared")
    return True


def create_matrix3d_from_orientation(position: Matrix, orientation: Orientation) -> adsk.core.Matrix3D:
    """
    Convert sympy position vector and Orientation to Fusion 360 Matrix3D.
    
    Args:
        position: 3x1 sympy Matrix representing position
        orientation: Orientation object with 3x3 rotation matrix
        
    Returns:
        adsk.core.Matrix3D for use in Fusion 360
    """
    app = get_fusion_app()
    if not app:
        raise RuntimeError("Cannot access Fusion 360 application")
    
    # Create Fusion 360 Matrix3D
    matrix3d = adsk.core.Matrix3D.create()
    
    # Extract rotation matrix values (convert sympy expressions to floats)
    # The orientation matrix columns are [width_direction, height_direction, length_direction]
    # For Fusion 360, we want to create a coordinate system where:
    # - X-axis (col 0) = width_direction
    # - Y-axis (col 1) = height_direction  
    # - Z-axis (col 2) = length_direction
    r00 = float(orientation.matrix[0, 0])
    r01 = float(orientation.matrix[0, 1])
    r02 = float(orientation.matrix[0, 2])
    r10 = float(orientation.matrix[1, 0])
    r11 = float(orientation.matrix[1, 1])
    r12 = float(orientation.matrix[1, 2])
    r20 = float(orientation.matrix[2, 0])
    r21 = float(orientation.matrix[2, 1])
    r22 = float(orientation.matrix[2, 2])
    
    # Extract translation values
    tx = float(position[0])
    ty = float(position[1])
    tz = float(position[2])
    
    # Set the matrix values (4x4 transformation matrix in row-major order)
    matrix3d.setWithArray([
        r00, r01, r02, tx,
        r10, r11, r12, ty,
        r20, r21, r22, tz,
        0.0, 0.0, 0.0, 1.0
    ])
    
    return matrix3d


def render_prism_in_local_space(component: adsk.fusion.Component, prism: RectangularPrism, infinite_extent: float = 10000.0) -> Optional[adsk.fusion.BRepBody]:
    """
    Render a Prism CSG in the component's local coordinate system with its orientation and position applied.
    
    The prism is first rendered axis-aligned where:
    - Width (size[0]) is along X axis
    - Height (size[1]) is along Y axis
    - Length is along Z axis from start_distance to end_distance
    
    Then the prism's orientation matrix is applied to rotate it, and finally it's translated to its position.
    
    Args:
        component: Fusion 360 component to create geometry in
        prism: Prism CSG object
        infinite_extent: Extent to use for infinite dimensions (in cm)
        
    Returns:
        Created BRepBody, or None if creation failed
    """
    try:
        # Extract dimensions
        width = float(prism.size[0])
        height = float(prism.size[1])
        
        # Get start and end distances along the length axis
        # For infinite prisms, use the provided extent
        LARGE_NUMBER = infinite_extent
        
        if prism.start_distance is None and prism.end_distance is None:
            # Fully infinite prism - extend both ways
            start_dist = -LARGE_NUMBER
            end_dist = LARGE_NUMBER
            print(f"  Warning: Rendering fully infinite prism, cropping to ±{LARGE_NUMBER}")
        elif prism.start_distance is None:
            # Semi-infinite extending in negative direction
            end_dist = float(prism.end_distance)
            start_dist = end_dist - 2 * LARGE_NUMBER
            print(f"  Warning: Rendering semi-infinite prism (negative), cropping start to {start_dist}")
        elif prism.end_distance is None:
            # Semi-infinite extending in positive direction
            start_dist = float(prism.start_distance)
            end_dist = start_dist + 2 * LARGE_NUMBER
            print(f"  Warning: Rendering semi-infinite prism (positive), cropping end to {end_dist}")
        else:
            # Finite prism
            start_dist = float(prism.start_distance)
            end_dist = float(prism.end_distance)
        
        length = end_dist - start_dist
        
        # Create a sketch on the XY plane
        sketches = component.sketches
        xy_plane = component.xYConstructionPlane
        sketch = sketches.add(xy_plane)
        
        # Create rectangle centered at origin in the XY plane
        # This represents the cross-section in the prism's local coordinate system
        corner1 = adsk.core.Point3D.create(-width/2, -height/2, 0)
        corner2 = adsk.core.Point3D.create(width/2, height/2, 0)
        rect = sketch.sketchCurves.sketchLines.addTwoPointRectangle(corner1, corner2)
        
        # Get the profile for extrusion
        profile = sketch.profiles.item(0)
        
        # Create extrusion along +Z axis
        extrudes = component.features.extrudeFeatures
        extrude_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        
        # Set extrusion to go from start_dist to end_dist along Z
        distance = adsk.core.ValueInput.createByReal(length)
        extrude_input.setDistanceExtent(False, distance)
        
        # Set the start position to start_dist (so extrusion goes from start_dist to end_dist)
        start_offset = adsk.core.ValueInput.createByReal(start_dist)
        extrude_input.startExtent = adsk.fusion.OffsetStartDefinition.create(start_offset)
        
        # Create the extrusion
        extrude = extrudes.add(extrude_input)
        
        if not extrude or not extrude.bodies or extrude.bodies.count == 0:
            print("Failed to create extrusion")
            return None
        
        body = extrude.bodies.item(0)
        
        # Apply the prism's orientation and position
        orientation_matrix = prism.transform.orientation.matrix
        
        # Check if transformation is needed
        is_identity = (orientation_matrix == Matrix.eye(3))
        is_at_origin = (prism.transform.position == Matrix([0, 0, 0]))
        
        app = get_fusion_app()
        if app:
            # log start and end distances
            app.log(f"  render_prism_in_local_space: Start distance: {prism.start_distance}")
            app.log(f"  render_prism_in_local_space: End distance: {prism.end_distance}")
            app.log(f"  render_prism_in_local_space: Position: {prism.transform.position.T}")
            app.log(f"  render_prism_in_local_space: Identity: {is_identity}, At origin: {is_at_origin}")
        
        # Only apply transformation if needed (non-identity rotation or non-zero position)
        if not is_identity or not is_at_origin:
            transform = create_matrix3d_from_orientation(prism.transform.position, prism.transform.orientation)
            
            # Apply the transformation to the body
            move_features = component.features.moveFeatures
            bodies = adsk.core.ObjectCollection.create()
            bodies.add(body)
            move_input = move_features.createInput(bodies, transform)
            move_input.defineAsFreeMove(transform)
            move_features.add(move_input)
        
        return body
        
    except Exception as e:
        print(f"Error rendering prism: {e}")
        traceback.print_exc()
        return None


def render_cutcsg_component_at_origin(csg: CutCSG, component_name: str = "CSG_Component", timber: Optional[Timber] = None, infinite_extent: float = 10000.0) -> Optional[adsk.fusion.Occurrence]:
    """
    Render a CutCSG object as a new component in Fusion 360 AT THE ORIGIN.
    
    This creates all geometry in local space at the origin. Transforms should be applied
    separately in a later pass for better reliability.
    
    Args:
        csg: CutCSG object to render
        component_name: Name for the created component
        timber: Optional timber object (needed for coordinate transformations during cuts)
        infinite_extent: Extent to use for infinite geometry (in cm)
        
    Returns:
        Created Occurrence, or None if creation failed
    """
    design = get_active_design()
    if not design:
        print("No active design found")
        return None
    
    try:
        # Create a new component at origin
        root = design.rootComponent
        transform = adsk.core.Matrix3D.create()
        occurrence = root.occurrences.addNewComponent(transform)
        component = occurrence.component
        component.name = component_name
        
        # Render the CSG in local space
        body = render_csg_in_local_space(component, csg, timber, infinite_extent)
        
        if body is None:
            print(f"Failed to render CSG in local space for {component_name}")
            return None
        
        return occurrence
        
    except Exception as e:
        print(f"Error rendering CutCSG component: {e}")
        traceback.print_exc()
        return None


def render_csg_pattern(csg: CutCSG, pattern_name: str = "CSG", infinite_extent: float = 10000.0) -> int:
    """
    Render a standalone CSG object (not associated with a timber) in Fusion 360.
    
    This is a convenience function for rendering CSG patterns from PatternBook.
    
    Args:
        csg: CutCSG object to render
        pattern_name: Name for the component
        infinite_extent: Extent for infinite geometry (in cm)
        
    Returns:
        1 if successful, 0 if failed
    """
    app = get_fusion_app()
    
    if app:
        app.log(f"Rendering CSG pattern: {pattern_name}")
    
    # Use existing render_cutcsg_component_at_origin() which already handles CSG rendering
    occurrence = render_cutcsg_component_at_origin(
        csg=csg, 
        component_name=pattern_name,
        timber=None,
        infinite_extent=infinite_extent
    )
    
    if occurrence:
        print(f"Successfully rendered CSG pattern: {pattern_name}")
        if app:
            app.log(f"Successfully rendered CSG pattern: {pattern_name}")
        return 1
    else:
        print(f"Failed to render CSG pattern: {pattern_name}")
        if app:
            app.log(f"Failed to render CSG pattern: {pattern_name}")
        return 0


def render_csg_in_local_space(component: adsk.fusion.Component, csg: CutCSG, timber: Optional[Timber] = None, infinite_extent: float = 10000.0) -> Optional[adsk.fusion.BRepBody]:
    """
    Render a CSG object in the component's (timber's) local coordinate system.
    
    This recursively processes CSG operations (Union, Difference, etc.) and
    creates the corresponding Fusion 360 geometry.
    
    Args:
        component: Component to render into
        csg: CSG object to render
        timber: Optional timber object (needed for coordinate transformations during cuts)
        infinite_extent: Extent to use for infinite geometry (in cm)
        
    Returns:
        Created BRepBody, or None if creation failed
    """
    app = get_fusion_app()
    
    if isinstance(csg, RectangularPrism):
        if app:
            app.log(f"  render_csg_in_local_space: Rendering Prism with orientation")
        return render_prism_in_local_space(component, csg, infinite_extent)
    
    elif isinstance(csg, Cylinder):
        if app:
            app.log(f"  render_csg_in_local_space: Rendering Cylinder with orientation")
        return render_cylinder_in_local_space(component, csg)
    
    elif isinstance(csg, ConvexPolygonExtrusion):
        if app:
            app.log(f"  render_csg_in_local_space: Rendering ConvexPolygonExtrusion with orientation")
        return render_convex_polygon_extrusion_in_local_space(component, csg)
    
    elif isinstance(csg, HalfSpace):
        # HalfSpace is typically used for cutting operations, not standalone rendering
        print("Warning: HalfSpace rendering not implemented (typically used in Difference operations)")
        if app:
            app.log("Warning: HalfSpace standalone rendering not implemented")
        return None
    
    elif isinstance(csg, SolidUnion):
        if app:
            app.log(f"  render_csg_in_local_space: Rendering Union with {len(csg.children)} children")
        return render_union_at_origin(component, csg, timber, infinite_extent)
    
    elif isinstance(csg, Difference):
        if app:
            app.log(f"  render_csg_in_local_space: Rendering Difference (base={type(csg.base).__name__}, {len(csg.subtract)} subtractions)")
        return render_difference_at_origin(component, csg, timber, infinite_extent)
    
    else:
        print(f"Unknown CSG type: {type(csg)}")
        if app:
            app.log(f"Unknown CSG type: {type(csg)}")
        return None


def render_cylinder_in_local_space(component: adsk.fusion.Component, cylinder: Cylinder) -> Optional[adsk.fusion.BRepBody]:
    """
    Render a Cylinder CSG in the component's local coordinate system with orientation and position applied.
    
    The cylinder is created with its axis aligned along +Z, then rotated to match axis_direction
    and translated to the cylinder's position.
    
    Args:
        component: Fusion 360 component to create geometry in
        cylinder: Cylinder CSG object
        
    Returns:
        Created BRepBody, or None if creation failed
    """
    try:
        # Extract parameters
        radius = float(cylinder.radius)
        
        if cylinder.start_distance is None or cylinder.end_distance is None:
            raise ValueError("Cannot render infinite cylinder - must have finite start and end distances")
        
        start_dist = float(cylinder.start_distance)
        end_dist = float(cylinder.end_distance)
        length = end_dist - start_dist
        
        # Get axis direction (normalized)
        axis_dir = cylinder.axis_direction
        axis_norm = axis_dir.norm()
        axis_normalized = axis_dir / axis_norm
        
        # Create a sketch on the XY plane
        sketches = component.sketches
        xy_plane = component.xYConstructionPlane
        sketch = sketches.add(xy_plane)
        
        # Create circle centered at origin
        center = adsk.core.Point3D.create(0, 0, 0)
        circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(center, radius)
        
        # Get the profile for extrusion
        profile = sketch.profiles.item(0)
        
        # Create extrusion along +Z axis initially
        extrudes = component.features.extrudeFeatures
        extrude_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        
        # Set extrusion distance
        distance = adsk.core.ValueInput.createByReal(length)
        extrude_input.setDistanceExtent(False, distance)
        
        # Set start offset to position the cylinder correctly along its axis
        start_offset = adsk.core.ValueInput.createByReal(start_dist)
        extrude_input.startExtent = adsk.fusion.OffsetStartDefinition.create(start_offset)
        
        # Create the extrusion
        extrude = extrudes.add(extrude_input)
        
        if not extrude or not extrude.bodies or extrude.bodies.count == 0:
            print("Failed to create cylinder extrusion")
            return None
        
        body = extrude.bodies.item(0)
        
        # Now we need to rotate the cylinder from +Z axis to the axis_direction
        # and translate it to the cylinder's position
        z_axis = Matrix([0, 0, 1])
        
        # Check if axis is already along Z
        dot_with_z = (axis_normalized.T * z_axis)[0, 0]
        is_aligned_with_z = abs(float(dot_with_z) - 1.0) < 0.001
        
        # Check if position is at origin
        is_at_origin = (cylinder.position == Matrix([0, 0, 0]))
        
        app = get_fusion_app()
        if app:
            app.log(f"  render_cylinder_in_local_space: Position: {cylinder.position.T}")
            app.log(f"  render_cylinder_in_local_space: Aligned with Z: {is_aligned_with_z}, At origin: {is_at_origin}")
        
        # Only apply transformation if needed
        if not is_aligned_with_z or not is_at_origin:
            # Calculate rotation matrix if not aligned with Z
            if not is_aligned_with_z:
                # Use Rodrigues' rotation formula
                # Rotation axis: cross product of z_axis and axis_normalized
                rotation_axis = z_axis.cross(axis_normalized)
                rotation_axis_norm = rotation_axis.norm()
                
                if rotation_axis_norm > 0.001:  # Not parallel
                    rotation_axis_unit = rotation_axis / rotation_axis_norm
                    
                    # Rotation angle
                    import math
                    cos_angle = float(dot_with_z)
                    angle = math.acos(max(-1.0, min(1.0, cos_angle)))  # Clamp to avoid numerical errors
                    
                    # Create rotation matrix using Rodrigues' formula
                    K = Matrix([
                        [0, -rotation_axis_unit[2], rotation_axis_unit[1]],
                        [rotation_axis_unit[2], 0, -rotation_axis_unit[0]],
                        [-rotation_axis_unit[1], rotation_axis_unit[0], 0]
                    ])
                    
                    rotation_matrix = Matrix.eye(3) + math.sin(angle) * K + (1 - math.cos(angle)) * (K * K)
                    cylinder_orientation = Orientation(rotation_matrix)
                else:
                    # Parallel but might be anti-parallel, use identity
                    cylinder_orientation = Orientation.identity()
            else:
                # Already aligned with Z, use identity orientation
                cylinder_orientation = Orientation.identity()
            
            # Apply rotation and translation
            transform = create_matrix3d_from_orientation(cylinder.position, cylinder_orientation)
            
            # Apply the transformation
            move_features = component.features.moveFeatures
            bodies = adsk.core.ObjectCollection.create()
            bodies.add(body)
            move_input = move_features.createInput(bodies, transform)
            move_input.defineAsFreeMove(transform)
            move_features.add(move_input)
        
        return body
        
    except Exception as e:
        print(f"Error rendering cylinder: {e}")
        traceback.print_exc()
        return None


def render_convex_polygon_extrusion_in_local_space(component: adsk.fusion.Component, extrusion: ConvexPolygonExtrusion) -> Optional[adsk.fusion.BRepBody]:
    """
    Render a ConvexPolygonExtrusion CSG in the component's local coordinate system with orientation and position applied.
    
    The polygon is extruded along the Z axis from z=start_distance to z=end_distance,
    then the orientation and position are applied.
    
    For infinite extrusions (start_distance or end_distance is None), the extrusion 
    cannot be rendered and None is returned.
    
    Args:
        component: Fusion 360 component to create geometry in
        extrusion: ConvexPolygonExtrusion CSG object
        
    Returns:
        Created BRepBody, or None if creation failed
    """
    app = get_fusion_app()
    try:
        # Check if the extrusion is finite
        if extrusion.start_distance is None or extrusion.end_distance is None:
            print(f"Warning: Cannot render infinite ConvexPolygonExtrusion")
            if app:
                app.log(f"Warning: Cannot render infinite ConvexPolygonExtrusion")
            return None
        
        if app:
            app.log(f"  render_convex_polygon_extrusion_in_local_space: {len(extrusion.points)} points, start={float(extrusion.start_distance):.3f}, end={float(extrusion.end_distance):.3f}")
        
        # Create a sketch on the XY plane
        sketches = component.sketches
        xy_plane = component.xYConstructionPlane
        sketch = sketches.add(xy_plane)
        
        # Convert 2D points to Fusion 360 Point3D (in the XY plane, Z=0)
        points_3d = []
        for pt in extrusion.points:
            x = float(pt[0])
            y = float(pt[1])
            points_3d.append(adsk.core.Point3D.create(x, y, 0.0))
        
        # Create polygon lines by connecting consecutive points
        lines = sketch.sketchCurves.sketchLines
        for i in range(len(points_3d)):
            start_point = points_3d[i]
            end_point = points_3d[(i + 1) % len(points_3d)]  # Wrap around to first point
            lines.addByTwoPoints(start_point, end_point)
        
        # Get the profile for extrusion (should be a closed profile)
        if sketch.profiles.count == 0:
            print("Error: No closed profile created from polygon points")
            return None
        
        profile = sketch.profiles.item(0)
        
        # Calculate extrusion length from start_distance to end_distance
        extrusion_length = extrusion.end_distance - extrusion.start_distance
        length = float(extrusion_length)
        
        # Create extrusion along +Z axis
        extrudes = component.features.extrudeFeatures
        extrude_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        
        # Set extrusion distance
        distance = adsk.core.ValueInput.createByReal(length)
        extrude_input.setDistanceExtent(False, distance)
        
        # Set start offset to position the extrusion at start_distance along Z
        start_offset = adsk.core.ValueInput.createByReal(float(extrusion.start_distance))
        extrude_input.startExtent = adsk.fusion.OffsetStartDefinition.create(start_offset)
        
        # Create the extrusion
        extrude = extrudes.add(extrude_input)
        
        if not extrude or not extrude.bodies or extrude.bodies.count == 0:
            print("Failed to create convex polygon extrusion")
            return None
        
        body = extrude.bodies.item(0)
        
        # Apply the extrusion's orientation and position if not at origin with identity orientation
        from sympy import Matrix
        is_identity = (extrusion.transform.orientation.matrix == Matrix.eye(3))
        is_at_origin = (extrusion.transform.position == Matrix([0, 0, 0]))
        
        app = get_fusion_app()
        if app:
            app.log(f"  render_convex_polygon_extrusion_in_local_space: Position: {extrusion.transform.position.T}")
            app.log(f"  render_convex_polygon_extrusion_in_local_space: Identity: {is_identity}, At origin: {is_at_origin}")
        
        # Only apply transformation if needed (non-identity rotation or non-zero position)
        if not is_identity or not is_at_origin:
            transform = create_matrix3d_from_orientation(extrusion.transform.position, extrusion.transform.orientation)
            
            # Apply the transformation to the body
            move_features = component.features.moveFeatures
            bodies = adsk.core.ObjectCollection.create()
            bodies.add(body)
            move_input = move_features.createInput(bodies, transform)
            move_input.defineAsFreeMove(transform)
            move_features.add(move_input)
        
        if app:
            app.log(f"  ✓ ConvexPolygonExtrusion rendered successfully")
        return body
        
    except Exception as e:
        print(f"Error rendering convex polygon extrusion: {e}")
        if app:
            app.log(f"ERROR rendering convex polygon extrusion: {e}")
        traceback.print_exc()
        return None


def render_union_at_origin(component: adsk.fusion.Component, union: SolidUnion, timber: Optional[Timber] = None, infinite_extent: float = 10000.0) -> Optional[adsk.fusion.BRepBody]:
    """
    Render a Union CSG operation at the origin.
    
    Args:
        component: Component to render into
        union: Union CSG object
        
    Returns:
        Combined BRepBody, or None if creation failed
    """
    app = get_fusion_app()
    
    if not union.children:
        print("Warning: Empty union")
        if app:
            app.log("Warning: Empty union in render_union_at_origin")
        return None
    
    if app:
        app.log(f"render_union_at_origin: Rendering Union with {len(union.children)} children")
        for i, child in enumerate(union.children):
            app.log(f"  Child {i}: {type(child).__name__}")
    
    # Render the first child
    if app:
        app.log(f"  Rendering first child (type: {type(union.children[0]).__name__})...")
    result_body = render_csg_in_local_space(component, union.children[0], timber, infinite_extent)
    
    if result_body is None:
        print("Failed to render first child of union")
        if app:
            app.log(f"ERROR: Failed to render first child of union (type: {type(union.children[0]).__name__})")
        return None
    
    if app:
        app.log(f"  ✓ First child rendered successfully")
    
    # Render all remaining children and collect them as tool bodies
    tools = adsk.core.ObjectCollection.create()
    for i, child in enumerate(union.children[1:], start=1):
        if app:
            app.log(f"  Rendering union child {i+1} (type: {type(child).__name__})...")
        child_body = render_csg_in_local_space(component, child, timber, infinite_extent)
        
        if child_body is None:
            print(f"Failed to render union child {i}")
            if app:
                app.log(f"ERROR: Failed to render union child {i+1} (type: {type(child).__name__})")
            continue
        
        if app:
            app.log(f"  ✓ Union child {i+1} rendered successfully")
        tools.add(child_body)
    
    # Perform a single union operation with all tool bodies
    if tools.count > 0:
        try:
            if app:
                app.log(f"  Performing union combine operation with {tools.count} tool bodies...")
            combine_features = component.features.combineFeatures
            
            # Create combine input (union operation) with all tools at once
            combine_input = combine_features.createInput(result_body, tools)
            combine_input.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
            combine_input.isKeepToolBodies = False
            
            # Execute the combine
            combine_features.add(combine_input)
            
            if app:
                app.log(f"  ✓ Union combine operation completed successfully")
            
            # Give Fusion 360 time to process the union
            time.sleep(0.05)
            adsk.doEvents()
            
        except Exception as e:
            print(f"Error performing union operation: {e}")
            if app:
                app.log(f"ERROR performing union operation: {e}")
            traceback.print_exc()
    else:
        if app:
            app.log("  Note: No additional tools to union (only first child)")
    
    return result_body


def transform_halfspace_to_component_space(half_plane: HalfSpace, timber_orientation: Orientation) -> Tuple[adsk.core.Vector3D, float]:
    """
    Prepare a HalfSpace for rendering in Fusion 360's component space.
    
    Uses the shared rendering utility function and converts to Fusion-specific types.
    
    Args:
        half_plane: HalfSpace in timber's local coordinates
        timber_orientation: Timber's orientation matrix (not used, kept for API compatibility)
        
    Returns:
        Tuple of (component_space_normal_vector, component_space_offset)
    """
    # Use shared utility function
    component_normal, component_offset = transform_halfspace_to_timber_local(half_plane, timber_orientation)
    
    # Debug logging
    app = get_fusion_app()
    if app:
        app.log(f"      HalfSpace normal (local/component): ({component_normal[0,0]:.4f}, {component_normal[1,0]:.4f}, {component_normal[2,0]:.4f})")
        app.log(f"      HalfSpace offset (local/component): {component_offset:.4f}")
    
    # Convert to Fusion 360 types
    component_normal_vector = adsk.core.Vector3D.create(
        float(component_normal[0,0]),
        float(component_normal[1,0]),
        float(component_normal[2,0])
    )
    
    return component_normal_vector, float(component_offset)


def apply_halfspace_cut(component: adsk.fusion.Component, body: adsk.fusion.BRepBody, half_plane: HalfSpace, timber: Optional[Timber] = None, infinite_extent: float = 10000.0) -> bool:
    """
    Apply a HalfSpace cut to a body using a large box and boolean difference.
    
    The HalfSpace is defined in global coordinates but must be transformed to the timber's
    local coordinate system for rendering.
    
    Args:
        component: Component containing the body
        body: Body to cut
        half_plane: HalfSpace defining the cut (in global coordinates)
        timber: Timber object (needed for coordinate transformation)
        infinite_extent: Extent to use for the cutting box (in cm)
        
    Returns:
        True if cut was applied successfully
    """
    app = get_fusion_app()
    
    try:
        if app:
            app.log(f"    apply_halfspace_cut: Starting (global coords)")
            
        # Log global coordinates
        global_nx = float(half_plane.normal[0])
        global_ny = float(half_plane.normal[1])
        global_nz = float(half_plane.normal[2])
        global_d = float(half_plane.offset)
        if app:
            app.log(f"      Global: normal=({global_nx:.4f}, {global_ny:.4f}, {global_nz:.4f}), offset={global_d:.4f}")
        
        # Transform to local coordinates if timber is provided
        # The body is rendered axis-aligned, then the occurrence is transformed later
        # Cuts must be in the body's local space to be correct after transform
        if timber is not None:
            plane_normal, plane_offset = transform_halfspace_to_component_space(half_plane, timber.orientation)
            if app:
                app.log(f"      Local:  normal=({plane_normal.x:.4f}, {plane_normal.y:.4f}, {plane_normal.z:.4f}), offset={plane_offset:.4f}")
        else:
            # No transformation - use global coordinates directly
            plane_normal = adsk.core.Vector3D.create(global_nx, global_ny, global_nz)
            plane_offset = global_d
            if app:
                app.log(f"      WARNING: No timber provided, using global coordinates")
        
        # The plane equation is: normal · P = offset
        # We need to find a point on the plane within the timber's bounds
        # The timber's centerline in local coords is along the Z-axis: (0, 0, z)
        # Find where the plane intersects the centerline:
        # normal · (0, 0, z) = offset
        # normal_z * z = offset
        # z = offset / normal_z
        #
        # However, if normal_z is close to 0, the plane is parallel to the centerline
        # In that case, use the origin (0, 0, 0) projected onto the plane
        
        if abs(plane_normal.z) > 0.01:
            # Plane intersects the centerline at z = offset / normal_z
            z_intersect = plane_offset / plane_normal.z
            plane_point = adsk.core.Point3D.create(0, 0, z_intersect)
        else:
            # Plane is parallel to centerline, use normal * offset / |normal|^2
            normal_mag_sq = plane_normal.x**2 + plane_normal.y**2 + plane_normal.z**2
            plane_point = adsk.core.Point3D.create(
                plane_normal.x * plane_offset / normal_mag_sq,
                plane_normal.y * plane_offset / normal_mag_sq,
                plane_normal.z * plane_offset / normal_mag_sq
            )
        
        if app:
            app.log(f"    Creating cutting half-space at point ({plane_point.x:.4f}, {plane_point.y:.4f}, {plane_point.z:.4f})")
        
        # Create a large box representing the half-space to subtract
        # The box extends from the plane in the direction of -normal (the "outside" to remove)
        try:
            # Use the provided extent for the cutting box
            BOX_SIZE = infinite_extent * 2  # Double for safety
            
            # Create a sketch on XY plane to make the cutting box
            sketches = component.sketches
            xy_plane = component.xYConstructionPlane
            sketch = sketches.add(xy_plane)
            
            # Create a large rectangle centered at origin
            corner1 = adsk.core.Point3D.create(-BOX_SIZE, -BOX_SIZE, 0)
            corner2 = adsk.core.Point3D.create(BOX_SIZE, BOX_SIZE, 0)
            rect = sketch.sketchCurves.sketchLines.addTwoPointRectangle(corner1, corner2)
            
            # Get the profile for extrusion
            profile = sketch.profiles.item(0)
            
            # Extrude the box
            extrudes = component.features.extrudeFeatures
            extrude_input = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            
            # Extrude a very large distance
            distance = adsk.core.ValueInput.createByReal(BOX_SIZE)
            extrude_input.setDistanceExtent(False, distance)
            
            # Create the extrusion
            extrude = extrudes.add(extrude_input)
            
            if not extrude or not extrude.bodies or extrude.bodies.count == 0:
                print("    Failed to create cutting box")
                if app:
                    app.log("    ERROR: Failed to create cutting box")
                return False
            
            cutting_box = extrude.bodies.item(0)
            
            if app:
                app.log(f"    Cutting box created, now positioning it...")
            
            # Transform the cutting box to align with the half-plane
            # We need to position it so the cutting plane is at plane_point with normal plane_normal
            # The box currently extends from Z=0 to Z=BOX_SIZE
            # We want to position it so that Z=0 aligns with our cutting plane
            
            # Create transformation matrix
            # We need to:
            # 1. Rotate so Z-axis aligns with -plane_normal (because we want the Z=0 face to be the cutting plane)
            # 2. Translate so the Z=0 face passes through plane_point
            
            # Build rotation matrix to align Z-axis with +plane_normal
            # In giraffe.py, we do Difference(timber, [HalfSpace])
            # HalfSpace represents points where normal · P >= offset (material to REMOVE)
            # Difference removes those points, so we remove where normal · P >= offset
            # Therefore, the cutting box should represent the region where normal · P >= offset
            # The box extends from Z=0 in the +Z direction
            # So we align Z-axis with +normal to remove the correct half-space
            new_z = adsk.core.Vector3D.create(plane_normal.x, plane_normal.y, plane_normal.z)
            new_z.normalize()
            
            # Choose an arbitrary X axis perpendicular to new_z
            if abs(new_z.z) < 0.9:
                new_x = adsk.core.Vector3D.create(0, 0, 1)
            else:
                new_x = adsk.core.Vector3D.create(1, 0, 0)
            
            # Make new_x perpendicular to new_z
            temp = new_z.crossProduct(new_x)
            new_y = temp
            new_y.normalize()
            new_x = new_y.crossProduct(new_z)
            new_x.normalize()
            
            # Create transformation matrix
            transform = adsk.core.Matrix3D.create()
            
            if app:
                app.log(f"    Aligning cutting box:")
                app.log(f"      From: origin=(0,0,0), Z=(0,0,1)")
                app.log(f"      To: origin=({plane_point.x:.4f},{plane_point.y:.4f},{plane_point.z:.4f}), Z=({new_z.x:.4f},{new_z.y:.4f},{new_z.z:.4f})")
            
            transform.setToAlignCoordinateSystems(
                adsk.core.Point3D.create(0, 0, 0),
                adsk.core.Vector3D.create(1, 0, 0),
                adsk.core.Vector3D.create(0, 1, 0),
                adsk.core.Vector3D.create(0, 0, 1),
                plane_point,
                new_x,
                new_y,
                new_z
            )
            
            # Create a move feature to position the cutting box
            move_features = component.features.moveFeatures
            bodies_to_move = adsk.core.ObjectCollection.create()
            bodies_to_move.add(cutting_box)
            move_input = move_features.createInput(bodies_to_move, transform)
            move_features.add(move_input)
            
            if app:
                app.log(f"    Cutting box positioned, performing boolean cut...")
            
            # Perform boolean difference: body - cutting_box
            combine_features = component.features.combineFeatures
            tools = adsk.core.ObjectCollection.create()
            tools.add(cutting_box)
            combine_input = combine_features.createInput(body, tools)
            combine_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            combine_input.isKeepToolBodies = False
            
            combine_feature = combine_features.add(combine_input)
            
            if combine_feature is None:
                print(f"    ERROR: Halfspace boolean cut returned None")
                if app:
                    app.log(f"    ERROR: Halfspace combine_features.add() returned None")
                return False
            
            if app:
                app.log(f"    Boolean cut complete")
            
        except Exception as e:
            print(f"    ERROR during half-plane cut: {e}")
            if app:
                app.log(f"    ERROR during half-plane cut: {e}")
            traceback.print_exc()
            return False
        
        time.sleep(0.05)
        adsk.doEvents()
        
        return True
        
    except Exception as e:
        print(f"  Error applying HalfSpace cut: {e}")
        traceback.print_exc()
        return False


def render_difference_at_origin(component: adsk.fusion.Component, difference: Difference, timber: Optional[Timber] = None, infinite_extent: float = 10000.0) -> Optional[adsk.fusion.BRepBody]:
    """
    Render a Difference CSG operation at the origin.
    
    For HalfSpace cuts, uses split operations instead of creating infinite solids.
    For other CSG types, creates the solid and performs boolean difference.
    
    Args:
        component: Component to render into
        difference: Difference CSG object
        timber: Optional timber object (needed for coordinate transformations during cuts)
        infinite_extent: Extent to use for infinite geometry (in cm)
        
    Returns:
        Resulting BRepBody after subtraction, or None if creation failed
    """
    app = get_fusion_app()
    
    if app:
        app.log(f"render_difference_at_origin: Starting - base type={type(difference.base).__name__}, {len(difference.subtract)} cuts")
    
    # Render the base body
    base_body = render_csg_in_local_space(component, difference.base, timber, infinite_extent)
    
    if base_body is None:
        print("Failed to render base of difference")
        if app:
            app.log("ERROR: Failed to render base of difference")
        return None
    
    if app:
        app.log(f"render_difference_at_origin: Base body created successfully, now applying {len(difference.subtract)} cuts (may be flattened)")
    
    # Flatten the subtract list to handle SolidUnion objects that contain Halfspaces
    # A SolidUnion in a subtract list means "remove all these things", so we flatten it
    # to apply each child separately. We need to flatten recursively for nested SolidUnions.
    def flatten_union_recursively(csg_list):
        """Recursively flatten SolidUnion objects in a list"""
        result = []
        for csg in csg_list:
            if isinstance(csg, SolidUnion):
                # Recursively flatten the SolidUnion's children
                result.extend(flatten_union_recursively(csg.children))
            else:
                result.append(csg)
        return result
    
    flattened_subtracts = flatten_union_recursively(difference.subtract)
    
    if len(flattened_subtracts) != len(difference.subtract) and app:
        app.log(f"  Flattened Unions: {len(difference.subtract)} original subtracts → {len(flattened_subtracts)} flattened cuts")
        app.log(f"  Flattened cut types: {[type(c).__name__ for c in flattened_subtracts]}")
    
    # Subtract each child
    for i, subtract_csg in enumerate(flattened_subtracts):
        # Special handling for HalfSpace cuts
        if isinstance(subtract_csg, HalfSpace):
            print(f"  Applying HalfSpace cut {i+1}/{len(flattened_subtracts)} using split operation")
            if app:
                app.log(f"  Applying HalfSpace cut {i+1}/{len(flattened_subtracts)} using split operation")
            success = apply_halfspace_cut(component, base_body, subtract_csg, timber, infinite_extent)
            if not success:
                print(f"  Failed to apply HalfSpace cut {i+1}")
                if app:
                    app.log(f"  ERROR: Failed to apply HalfSpace cut {i+1}")
            else:
                if app:
                    app.log(f"  SUCCESS: Applied HalfSpace cut {i+1}")
            continue
        
        # For other CSG types, render and perform boolean difference
        print(f"  Applying {type(subtract_csg).__name__} cut {i+1}/{len(flattened_subtracts)} using boolean difference")
        if app:
            app.log(f"  Applying {type(subtract_csg).__name__} cut {i+1}/{len(flattened_subtracts)} using boolean difference")
        
        subtract_body = render_csg_in_local_space(component, subtract_csg, timber, infinite_extent)
        
        if subtract_body is None:
            print(f"  Failed to render subtract child {i+1}")
            if app:
                app.log(f"  ERROR: Failed to render subtract child {i+1}")
            continue
        
        # Perform difference operation
        try:
            combine_features = component.features.combineFeatures
            
            # Create tool collection with the subtract body
            tools = adsk.core.ObjectCollection.create()
            tools.add(subtract_body)
            
            # Create combine input (cut operation)
            combine_input = combine_features.createInput(base_body, tools)
            combine_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
            combine_input.isKeepToolBodies = False
            
            # Execute the combine
            combine_feature = combine_features.add(combine_input)
            
            if combine_feature is None:
                print(f"  ✗ Boolean cut failed for child {i+1}")
                if app:
                    app.log(f"    ERROR: combine_features.add() returned None")
            elif app:
                app.log(f"    SUCCESS: Boolean cut applied for child {i+1}")
            
            # Give Fusion 360 time to process the difference
            time.sleep(0.05)
            adsk.doEvents()
            
        except Exception as e:
            print(f"  ✗ Error performing difference with child {i+1}: {e}")
            if app:
                app.log(f"  ERROR performing difference with child {i+1}: {e}")
                app.log(f"  Exception type: {type(e).__name__}")
                app.log(f"  Exception details: {str(e)}")
            traceback.print_exc()
            continue
    
    if app:
        app.log(f"render_difference_at_origin: COMPLETE - all {len(flattened_subtracts)} cuts processed (from {len(difference.subtract)} original subtracts)")
    
    return base_body


def apply_timber_transform(occurrence: adsk.fusion.Occurrence, position: Matrix, 
                           orientation: Orientation, component_name: str, 
                           use_body_transform: bool = True) -> bool:
    """
    Apply a transform to move a timber occurrence from origin to its final position.
    
    Two methods are supported:
    1. Body transform (use_body_transform=True): Apply moveFeatures to the bodies within the component
    2. Occurrence transform (use_body_transform=False): Set occurrence.transform2 on the occurrence
    
    Args:
        occurrence: The occurrence to transform
        position: Target position vector
        orientation: Target orientation
        component_name: Name for debugging
        use_body_transform: If True, transform bodies within component. If False, transform occurrence.
        
    Returns:
        True if transform was applied successfully
    """
    try:
        # Get the design
        design = get_active_design()
        if not design:
            print(f"Error: No active design for {component_name}")
            return False
        
        # Create the transformation matrix
        global_transform = create_matrix3d_from_orientation(position, orientation)
        
        if use_body_transform:
            # METHOD 1: Apply transform to bodies within the component
            component = occurrence.component
            
            # Collect all bodies in the component
            bodies = adsk.core.ObjectCollection.create()
            for i in range(component.bRepBodies.count):
                bodies.add(component.bRepBodies.item(i))
            
            if bodies.count == 0:
                print(f"Warning: No bodies found in {component_name}")
                return False
            
            # Apply move transform to all bodies
            move_features = component.features.moveFeatures
            move_input = move_features.createInput(bodies, global_transform)
            move_input.defineAsFreeMove(global_transform)
            move_features.add(move_input)
            
            # Give Fusion 360 time to process
            time.sleep(0.05)
            adsk.doEvents()
            
            # Verify by checking the bounding box of the first body
            if component.bRepBodies.count > 0:
                first_body = component.bRepBodies.item(0)
                bbox = first_body.boundingBox
                center_x = (bbox.minPoint.x + bbox.maxPoint.x) / 2
                center_y = (bbox.minPoint.y + bbox.maxPoint.y) / 2
                center_z = (bbox.minPoint.z + bbox.maxPoint.z) / 2
                
                expected_tx = float(position[0])
                expected_ty = float(position[1])
                expected_tz = float(position[2])
                
                # The center should be approximately at the expected position
                # (within a reasonable tolerance based on timber size)
                tolerance = 50.0  # 50 cm tolerance for verification
                translation_correct = (abs(center_x - expected_tx) < tolerance and 
                                      abs(center_y - expected_ty) < tolerance and 
                                      abs(center_z - expected_tz) < tolerance)
                
                if not translation_correct:
                    print(f"⚠️  Transform verification warning for {component_name}")
                    print(f"  Expected position: ({expected_tx:.3f}, {expected_ty:.3f}, {expected_tz:.3f})")
                    print(f"  Body center: ({center_x:.3f}, {center_y:.3f}, {center_z:.3f})")
                    # Don't fail, just warn
            
        else:
            # METHOD 2: Set transform using occurrence.transform2 property
            # transform2 is the proper way to set occurrence transforms and records them
            occurrence.transform2 = global_transform
            
            # Give Fusion 360 time to process
            time.sleep(0.05)
            adsk.doEvents()
            
            # Verify the transform was applied correctly
            applied_transform = occurrence.transform2
            expected_tx = float(position[0])
            expected_ty = float(position[1])
            expected_tz = float(position[2])
            applied_tx = applied_transform.getCell(0, 3)
            applied_ty = applied_transform.getCell(1, 3)
            applied_tz = applied_transform.getCell(2, 3)
            
            translation_correct = (abs(applied_tx - expected_tx) < 0.001 and 
                                  abs(applied_ty - expected_ty) < 0.001 and 
                                  abs(applied_tz - expected_tz) < 0.001)
            
            if not translation_correct:
                print(f"⚠️  Transform verification failed for {component_name}")
                print(f"  Expected: ({expected_tx:.3f}, {expected_ty:.3f}, {expected_tz:.3f})")
                print(f"  Applied:  ({applied_tx:.3f}, {applied_ty:.3f}, {applied_tz:.3f})")
                return False
        
        return True
        
    except Exception as e:
        print(f"Error applying transform to {component_name}: {e}")
        traceback.print_exc()
        return False


def log_structure_extents(extent: float, cut_timbers: List[CutTimber]):
    """
    Log structure extents using Fusion 360's app logger.
    
    Args:
        extent: Maximum extent value
        cut_timbers: List of CutTimber objects (for calculating detailed extents)
    """
    app = get_fusion_app()
    if app:
        # Calculate detailed extents for logging
        from kumiki.rendering_utils import calculate_timber_corners
        
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    
    for cut_timber in cut_timbers:
        corners = calculate_timber_corners(cut_timber.timber)
        for corner in corners:
            x, y, z = float(corner[0]), float(corner[1]), float(corner[2])
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            min_z = min(min_z, z)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            max_z = max(max_z, z)
    
    extent_x = (max_x - min_x) / 2
    extent_y = (max_y - min_y) / 2
    extent_z = (max_z - min_z) / 2

    app.log(f"Structure extents: {extent_x:.2f} x {extent_y:.2f} x {extent_z:.2f} cm")
    app.log(f"Maximum extent: {extent:.2f} cm")


def check_body_extents(body: adsk.fusion.BRepBody, max_allowed_extent: float, component_name: str) -> bool:
    """
    Check if a body extends beyond the allowed extent and warn if so.
    
    Args:
        body: Body to check
        max_allowed_extent: Maximum allowed extent in cm
        component_name: Name of component for warning message
        
    Returns:
        True if within bounds, False if too large
    """
    try:
        if not body or not body.boundingBox:
            return True
        
        bbox = body.boundingBox
        extent_x = (bbox.maxPoint.x - bbox.minPoint.x) / 2
        extent_y = (bbox.maxPoint.y - bbox.minPoint.y) / 2
        extent_z = (bbox.maxPoint.z - bbox.minPoint.z) / 2
        
        max_extent = max(extent_x, extent_y, extent_z)
        
        if max_extent > max_allowed_extent:
            print(f"⚠️  WARNING: {component_name} extends {max_extent:.2f} cm (exceeds limit of {max_allowed_extent:.2f} cm)")
            app = get_fusion_app()
            if app:
                app.log(f"⚠️  WARNING: {component_name} extends {max_extent:.2f} cm (exceeds limit of {max_allowed_extent:.2f} cm)")
            return False
        
        return True
        
    except Exception as e:
        print(f"Warning: Could not check extents for {component_name}: {e}")
        return True


def render_accessory_at_origin(accessory: JointAccessory, component_name: str, infinite_extent: float = 10000.0) -> Optional[adsk.fusion.Occurrence]:
    """
    Render a JointAccessory at the origin in Fusion 360 using its CSG representation.
    
    The accessory is created at origin with identity orientation. Transform should be applied later.
    
    Args:
        accessory: JointAccessory object (Peg, Wedge, etc.)
        component_name: Name for the created component
        infinite_extent: Extent to use for infinite geometry (in cm)
        
    Returns:
        Created Occurrence, or None if creation failed
    """
    try:
        # Get the CSG representation from the accessory
        accessory_csg = accessory.render_csg_local()
        
        # Render using the standard CSG rendering pipeline
        occurrence = render_cutcsg_component_at_origin(
            csg=accessory_csg,
            component_name=component_name,
            timber=None,  # No timber needed for accessories
            infinite_extent=infinite_extent
        )
        
        if occurrence is None:
            print(f"Failed to render accessory geometry for {component_name}")
            return None
        
        return occurrence
        
    except Exception as e:
        print(f"Error rendering accessory at origin: {e}")
        traceback.print_exc()
        return None


def render_frame(frame: Frame, base_name: str = None, use_body_transform: bool = True) -> int:
    """
    Render a complete Frame in Fusion 360.
    
    Args:
        frame: Frame object containing cut timbers and accessories
        base_name: Optional base name override (defaults to frame.name or "Timber")
        use_body_transform: Whether to use body transform method
    
    Returns:
        Number of components created
    """
    name = base_name if base_name is not None else (frame.name or "Timber")
    return render_multiple_timbers(
        cut_timbers=frame.cut_timbers,
        joint_accessories=frame.accessories,
        base_name=name,
        use_body_transform=use_body_transform
    )


def render_multiple_timbers(cut_timbers: List[CutTimber], base_name: str = "Timber", 
                           joint_accessories: List[JointAccessory] = None,
                           use_body_transform: bool = True) -> int:
    """
    Render multiple CutTimber objects and joint accessories in Fusion 360 using a three-pass approach.
    
    Pass 1: Create all geometry at origin
    Pass 2: Apply CSG operations (cuts) at origin
    Pass 3: Transform all occurrences to final positions
    Pass 4: Render joint accessories (pegs, wedges, etc.)
    
    This approach is more reliable than transforming each timber immediately after creation,
    as it avoids Fusion 360's asynchronous update issues.
    
    Component names are automatically determined from:
    1. CutTimber.name if set
    2. CutTimber.timber.name if set
    3. {base_name}_{index} as fallback
    
    Two transform methods are supported:
    1. Body transform (use_body_transform=True, default): Apply moveFeatures to bodies within component
    2. Occurrence transform (use_body_transform=False): Set transform2 on the occurrence
    
    Args:
        cut_timbers: List of CutTimber objects to render
        base_name: Base name for the components (used if timber has no name)
        joint_accessories: Optional list of (JointAccessory, Timber) tuples to render
        use_body_transform: If True, transform bodies within component. If False, transform occurrence.
        
    Returns:
        Number of successfully rendered timbers and accessories
    """
    app = get_fusion_app()
    
    if app:
        app.log(f"=== THREE-PASS RENDERING: {len(cut_timbers)} timbers ===")
        app.log(f"Transform method: {'Body transform (moveFeatures)' if use_body_transform else 'Occurrence transform (transform2)'}")
    
    print(f"\n=== THREE-PASS RENDERING ===")
    print(f"Transform method: {'Body transform (moveFeatures)' if use_body_transform else 'Occurrence transform (transform2)'}")
    
    # Calculate structure extents for intelligent sizing of infinite geometry
    print(f"\n=== Calculating structure extents ===")
    if app:
        app.log(f"=== Calculating structure extents ===")
    
    structure_extent = calculate_structure_extents(cut_timbers)
    infinite_geometry_extent = structure_extent * 10  # 10x for infinite geometry
    validation_extent = structure_extent * 5  # 5x for validation warnings
    
    print(f"Structure extent: {structure_extent:.2f} cm")
    print(f"Infinite geometry will extend to: {infinite_geometry_extent:.2f} cm")
    print(f"Validation threshold: {validation_extent:.2f} cm")
    
    if app:
        log_structure_extents(structure_extent, cut_timbers)
        app.log(f"Infinite geometry extent: {infinite_geometry_extent:.2f} cm")
        app.log(f"Validation threshold: {validation_extent:.2f} cm")
    
    # PASS 1: Create all geometry at origin with cuts applied
    print(f"\n=== PASS 1: Creating geometry at origin (with cuts) ===")
    if app:
        app.log(f"=== PASS 1: Creating geometry at origin (with cuts) ===")
    
    created_components: List[Tuple[adsk.fusion.Occurrence, CutTimber, str]] = []
    
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
                    'location': 'giraffe_render_fusion360.py:1200',
                    'message': 'Rendering cut timber in Fusion360',
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
            print(f"Creating {component_name}...")
            if app:
                app.log(f"Creating {component_name}...")
            
            # Get the timber with cuts applied in LOCAL coordinates
            # Local coordinates means the prism distances are relative to the timber's bottom_position
            # and all cuts are also in local coordinates. This allows us to render at origin and then transform.
            csg = cut_timber.render_timber_with_cuts_csg_local()
            
            if cut_timber.cuts:
                print(f"  Applying {len(cut_timber.cuts)} cut(s)")
                if app:
                    app.log(f"  Applying {len(cut_timber.cuts)} cut(s)")
            
            # Render at origin (no transform yet)
            # Pass timber info for coordinate transformations
            if app:
                app.log(f"  About to render CSG (type: {type(csg).__name__})")
            
            occurrence = render_cutcsg_component_at_origin(csg, component_name, cut_timber.timber, infinite_geometry_extent)
            
            if occurrence is not None:
                # Validate geometry extents
                component = occurrence.component
                if component.bRepBodies.count > 0:
                    for body_idx in range(component.bRepBodies.count):
                        body = component.bRepBodies.item(body_idx)
                        check_body_extents(body, validation_extent, component_name)
                
                created_components.append((occurrence, cut_timber, component_name))
                print(f"  ✓ Created {component_name}")
                if app:
                    app.log(f"  ✓ Created {component_name} - CSG rendered successfully")
            else:
                print(f"  ✗ Failed to create {component_name}")
                if app:
                    app.log(f"  ✗ Failed to create {component_name}")
                    
        except Exception as e:
            print(f"  ✗ Error creating {component_name}: {e}")
            if app:
                app.log(f"  ✗ Error creating {component_name}: {e}")
            traceback.print_exc()
    
    # Force Fusion 360 to process all geometry creation
    time.sleep(0.2)
    adsk.doEvents()
    
    # PASS 2: No longer needed - cuts are applied in Pass 1
    print(f"\n=== PASS 2: CSG operations (already applied in Pass 1) ===")
    if app:
        app.log(f"=== PASS 2: CSG operations (already applied in Pass 1) ===")
    
    # Force refresh
    time.sleep(0.1)
    adsk.doEvents()
    
    # PASS 2: Render joint accessories at origin (pegs, wedges, etc.)
    created_accessories = []  # List of (occurrence, accessory, name) tuples
    if joint_accessories:
        print(f"\n=== PASS 2: Creating {len(joint_accessories)} joint accessories at origin ===")
        if app:
            app.log(f"=== PASS 2: Creating {len(joint_accessories)} joint accessories at origin ===")
        
        for i, accessory in enumerate(joint_accessories):
            try:
                # Determine accessory name based on type
                if isinstance(accessory, Peg):
                    accessory_name = f"Peg_{i+1}"
                    print(f"Creating {accessory_name} ({accessory.shape.value}, size={float(accessory.size):.3f}cm)...")
                elif isinstance(accessory, Wedge):
                    accessory_name = f"Wedge_{i+1}"
                    print(f"Creating {accessory_name} (width={float(accessory.base_width):.3f}cm, height={float(accessory.height):.3f}cm)...")
                else:
                    accessory_name = f"Accessory_{i+1}"
                    print(f"Creating {accessory_name} ({type(accessory).__name__})...")
                
                # Render the accessory using its CSG representation
                occurrence = render_accessory_at_origin(accessory, accessory_name, infinite_geometry_extent)
                
                if occurrence:
                    created_accessories.append((occurrence, accessory, accessory_name))
                    print(f"  ✓ Created {accessory_name}")
                    if app:
                        app.log(f"  ✓ Created {accessory_name}")
                else:
                    print(f"  ✗ Failed to create {accessory_name}")
                    if app:
                        app.log(f"  ✗ Failed to create {accessory_name}")
                
            except Exception as e:
                print(f"  ✗ Error creating accessory {i+1}: {e}")
                if app:
                    app.log(f"  ✗ Error creating accessory {i+1}: {e}")
                traceback.print_exc()
    
    # Force Fusion 360 to process all geometry creation
    time.sleep(0.2)
    adsk.doEvents()
    
    # PASS 3: Apply all transforms to move to final positions (timbers AND accessories)
    total_objects = len(created_components) + len(created_accessories)
    print(f"\n=== PASS 3: Applying transforms to {total_objects} objects ({len(created_components)} timbers, {len(created_accessories)} accessories) ===")
    if app:
        app.log(f"=== PASS 3: Applying transforms to {total_objects} objects ({len(created_components)} timbers, {len(created_accessories)} accessories) ===")
    
    transform_success_count = 0
    accessories_transformed = 0
    
    # First, transform all timbers
    for occurrence, cut_timber, component_name in created_components:
        try:
            print(f"Transforming {component_name}... (method: {'body' if use_body_transform else 'occurrence'})")
            if app:
                app.log(f"Transforming {component_name}... (method: {'body' if use_body_transform else 'occurrence'})")
            
            # Get timber position and orientation
            position = cut_timber.timber.get_bottom_position_global()
            orientation = cut_timber.timber.orientation
            
            # Apply the transform
            success = apply_timber_transform(occurrence, position, orientation, component_name, use_body_transform)
            
            if success:
                transform_success_count += 1
                print(f"  ✓ Transformed {component_name}")
                if app:
                    app.log(f"  ✓ Transformed {component_name}")
            else:
                print(f"  ✗ Failed to transform {component_name}")
                if app:
                    app.log(f"  ✗ Failed to transform {component_name}")
            
            # Small delay between transforms to avoid race conditions
            time.sleep(0.05)
            adsk.doEvents()
                    
        except Exception as e:
            print(f"  ✗ Error transforming {component_name}: {e}")
            if app:
                app.log(f"  ✗ Error transforming {component_name}: {e}")
            traceback.print_exc()
    
    # Then, transform all accessories
    for occurrence, accessory, accessory_name in created_accessories:
        try:
            print(f"Transforming {accessory_name}... (method: {'body' if use_body_transform else 'occurrence'})")
            has_transform = hasattr(accessory, "transform")

            if not has_transform:
                accessories_transformed += 1
                print(f"  ✓ {accessory_name} has no transform field; geometry already in global space")
                if app:
                    app.log(f"  ✓ {accessory_name} has no transform field; geometry already in global space")
                time.sleep(0.05)
                adsk.doEvents()
                continue

            if app:
                app.log(f"  Transforming {accessory_name}: (method: {'body' if use_body_transform else 'occurrence'})")
                app.log(f"    Accessory position (global): {[float(x) for x in accessory.transform.position]}")
                app.log(f"    Accessory orientation matrix:")
                for i in range(3):
                    row = [float(accessory.transform.orientation.matrix[i, j]) for j in range(3)]
                    app.log(f"      [{row[0]:.3f}, {row[1]:.3f}, {row[2]:.3f}]")

            # Accessory position and orientation are already in global space
            # Use them directly without transformation
            success = apply_timber_transform(occurrence, accessory.transform.position, accessory.transform.orientation, accessory_name, use_body_transform)
            
            if not success:
                if app:
                    app.log(f"    ERROR: apply_timber_transform returned False")
                raise RuntimeError(f"Failed to apply transform to {accessory_name}")
            
            if app and not use_body_transform:
                # Only verify occurrence transform if using occurrence method
                actual_transform = occurrence.transform2
                actual_tx = actual_transform.getCell(0, 3)
                actual_ty = actual_transform.getCell(1, 3)
                actual_tz = actual_transform.getCell(2, 3)
                app.log(f"    Verified occurrence transform: [{actual_tx:.3f}, {actual_ty:.3f}, {actual_tz:.3f}]")
            
            accessories_transformed += 1
            print(f"  ✓ Transformed {accessory_name}")
            if app:
                app.log(f"  ✓ Transformed {accessory_name}")
            
            # Small delay between transforms
            time.sleep(0.05)
            adsk.doEvents()
            
        except Exception as e:
            print(f"  ✗ Error transforming {accessory_name}: {e}")
            if app:
                app.log(f"  ✗ Error transforming {accessory_name}: {e}")
            traceback.print_exc()
    
    # Final refresh
    time.sleep(0.2)
    adsk.doEvents()
    
    accessories_rendered = len(created_accessories)
    
    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"Created: {len(created_components)}/{len(cut_timbers)} timbers")
    print(f"Transformed: {transform_success_count}/{len(created_components)} timber components")
    if joint_accessories:
        print(f"Accessories Created: {accessories_rendered}/{len(joint_accessories)}")
        print(f"Accessories Transformed: {accessories_transformed}/{accessories_rendered}")
    
    if app:
        app.log(f"=== SUMMARY ===")
        app.log(f"Created: {len(created_components)}/{len(cut_timbers)} timbers")
        app.log(f"Transformed: {transform_success_count}/{len(created_components)} timber components")
        if joint_accessories:
            app.log(f"Accessories Created: {accessories_rendered}/{len(joint_accessories)}")
            app.log(f"Accessories Transformed: {accessories_transformed}/{accessories_rendered}")
    
    return transform_success_count + accessories_transformed
