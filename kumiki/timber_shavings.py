"""
Random timber-related helper functions.

Contains utility functions for working with timbers that don't fit into a more specific category.
"""

from .rule import *
from .timber import *



# ============================================================================
# Various geometric helper functions that should all be replaced with marking/measuring functions
# TODO DELETE ME 
# ============================================================================

def find_opposing_face_on_another_timber(reference_timber: PerfectTimberWithin, reference_face: TimberLongFace, target_timber: PerfectTimberWithin) -> TimberFace:
    """
    Find the opposing face on another timber. Assumes that the target_timber has a face parallel to the reference face on the reference_timber.
    """
    assert isinstance(reference_face, TimberLongFace), f"expected TimberLongFace, got {type(reference_face).__name__}"
    target_face = target_timber.get_closest_oriented_face_from_global_direction(-reference_timber.get_face_direction_global(reference_face))

    # assert that the target_face is parallel to the reference_face
    assert are_vectors_parallel(reference_timber.get_face_direction_global(reference_face), target_timber.get_face_direction_global(target_face)), \
        f"Target face {target_face} is not parallel to reference face {reference_face} on timber {reference_timber.ticket.name}"
    
    return target_face


# ============================================================================
# Helper Functions for Creating Joint Accessories
# ============================================================================

def create_peg_going_into_face(
    timber: Timber,
    face: TimberLongFace,
    distance_from_bottom: Numeric,
    distance_from_centerline: Numeric,
    peg_size: Numeric,
    peg_shape: PegShape,
    forward_length: Numeric,
    stickout_length: Numeric
) -> Peg:
    """
    Create a peg that goes into a specified long face of a timber.
    
    The peg is created in the local space of the timber, with the insertion end
    at the timber's surface and pointing inward perpendicular to the face.
    
    Args:
        timber: The timber to insert the peg into
        face: Which long face the peg enters from (RIGHT, LEFT, FRONT, or BACK)
        distance_from_bottom: Distance along the timber's length from the bottom end
        distance_from_centerline: Distance from the timber's centerline along the face
        peg_size: Size/diameter of the peg (for square pegs, this is the side length)
        peg_shape: Shape of the peg (SQUARE or ROUND)
        forward_length: How far the peg reaches in the forward direction
        stickout_length: How far the peg sticks out in the back direction
        
    Returns:
        Peg object positioned and oriented appropriately in timber's local space
    """
    assert isinstance(face, TimberLongFace), f"expected TimberLongFace, got {type(face).__name__}"
    # Get the face direction in local space (timber coordinate system)
    # In local coords: X = width, Y = height, Z = length
    face_normal_local = face.to.face().get_direction()
    
    # Position the peg on the timber's surface
    # Start at centerline, then move along length and offset from centerline
    position_local = create_v3(0, 0, distance_from_bottom)
    
    # Offset from centerline depends on which face we're on
    if face == TimberLongFace.RIGHT:
        # RIGHT face: offset in +X (width) direction, surface at +width/2
        position_local = create_v3(
            timber.size[0] / Rational(2),  # At right surface
            distance_from_centerline,  # Offset in height direction
            distance_from_bottom
        )
        # Peg points inward (-X direction in local space)
        length_dir = create_v3(-1, 0, 0)
        width_dir = create_v3(0, 1, 0)
        
    elif face == TimberLongFace.LEFT:
        # LEFT face: offset in -X (width) direction
        position_local = create_v3(
            -timber.size[0] / Rational(2),  # At left surface
            distance_from_centerline,  # Offset in height direction
            distance_from_bottom
        )
        # Peg points inward (+X direction in local space)
        length_dir = create_v3(1, 0, 0)
        width_dir = create_v3(0, 1, 0)
        
    elif face == TimberLongFace.FRONT:
        # FRONT face: offset in +Y (height) direction
        position_local = create_v3(
            distance_from_centerline,  # Offset in width direction
            timber.size[1] / Rational(2),  # At forward surface
            distance_from_bottom
        )
        # Peg points inward (-Y direction in local space)
        length_dir = create_v3(0, -1, 0)
        width_dir = create_v3(1, 0, 0)
        
    else:  # BACK
        # BACK face: offset in -Y (height) direction
        position_local = create_v3(
            distance_from_centerline,  # Offset in width direction
            -timber.size[1] / Rational(2),  # At back surface
            distance_from_bottom
        )
        # Peg points inward (+Y direction in local space)
        length_dir = create_v3(0, 1, 0)
        width_dir = create_v3(1, 0, 0)
    
    # Compute peg orientation (peg's Z-axis points into the timber)
    peg_orientation = compute_timber_orientation(length_dir, width_dir)
    peg_transform = Transform(position=position_local, orientation=peg_orientation)
    
    return Peg(
        transform=peg_transform,
        size=peg_size,
        shape=peg_shape,
        forward_length=forward_length,
        stickout_length=stickout_length
    )


def create_wedge_in_timber_end(
    timber: Timber,
    end: TimberReferenceEnd,
    position: V3,
    shape: WedgeShape
) -> Wedge:
    """
    Create a wedge at the end of a timber.
    
    The wedge is created in the local space of the timber. In identity orientation,
    the point of the wedge goes in the length direction (Z-axis in local space).
    
    Args:
        timber: The timber to insert the wedge into
        end: Which end of the timber (TOP or BOTTOM)
        position: Position in the timber's cross-section (X, Y in local space, Z ignored)
        shape: Specification of wedge dimensions
        
    Returns:
        Wedge object positioned and oriented appropriately in timber's local space
    """
    # Determine wedge position and orientation based on which end
    if end == TimberReferenceEnd.TOP:
        # At top end, wedge points downward into timber (-Z in local space)
        # Position at the top of the timber
        wedge_position = create_v3(
            position[0],  # X position (cross-section)
            position[1],  # Y position (cross-section)
            timber.length  # At the top end
        )
        # Wedge points downward
        length_dir = create_v3(0, 0, -1)
        width_dir = create_v3(1, 0, 0)
        
    else:  # BOTTOM
        # At bottom end, wedge points upward into timber (+Z in local space)
        # Position at the bottom of the timber
        wedge_position = create_v3(
            position[0],  # X position (cross-section)
            position[1],  # Y position (cross-section)
            0  # At the bottom end
        )
        # Wedge points upward
        length_dir = create_v3(0, 0, 1)
        width_dir = create_v3(1, 0, 0)
    
    # Compute wedge orientation
    wedge_orientation = compute_timber_orientation(length_dir, width_dir)
    wedge_transform = Transform(position=wedge_position, orientation=wedge_orientation)
    
    return Wedge(
        transform=wedge_transform,
        base_width=shape.base_width,
        tip_width=shape.tip_width,
        height=shape.height,
        length=shape.length
    )


# ============================================================================
# Timber Relationship Helper Functions
# ============================================================================

def are_timbers_parallel(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin, tolerance: Optional[Numeric] = None) -> bool:
    """
    Check if two timbers have parallel length directions.
    
    Args:
        timber1: First timber
        timber2: Second timber
        tolerance: Optional tolerance for approximate comparison. If None, attempts exact comparison and uses default epsilon if not possible.
                   
    Returns:
        True if timbers have parallel length directions, False otherwise
    """
    dot_product = Abs(numeric_dot_product(timber1.get_length_direction_global(), timber2.get_length_direction_global()))
    
    if tolerance is None:
        return equality_test(dot_product, 1)
    else:
        return Abs(dot_product - 1) < tolerance

def are_timbers_orthogonal(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin, tolerance: Optional[Numeric] = None) -> bool:
    """
    Check if two timbers have orthogonal (perpendicular) length directions.
    
    Args:
        timber1: First timber
        timber2: Second timber
        tolerance: Optional tolerance for approximate comparison. If None, automatically
                   uses exact comparison for rational values or fuzzy comparison for floats.
                   
    Returns:
        True if timbers have orthogonal length directions, False otherwise
    """
    dot_product = numeric_dot_product(timber1.get_length_direction_global(), timber2.get_length_direction_global())
    
    if tolerance is None:
        return zero_test(dot_product)
    else:
        return Abs(dot_product) < tolerance

def are_timbers_face_aligned(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin, tolerance: Optional[Numeric] = None) -> bool:
    """
    Check if two timbers are face-aligned.
    
    Two timbers are face-aligned if any face of one timber is parallel to any face 
    of the other timber. This occurs when their orientations are related by 90-degree 
    rotations around any axis (i.e., they share the same coordinate grid alignment).
    
    Mathematically, timbers are face-aligned if any of their orthogonal direction 
    vectors (length_direction, width_direction, height_direction) are parallel to each other.
    
    Args:
        timber1: First timber
        timber2: Second timber  
        tolerance: Optional numerical tolerance for parallel check. If None, uses exact
                   equality (recommended when using SymPy Rational types). If provided,
                   uses approximate floating-point comparison.
        
    Returns:
        True if timbers are face-aligned, False otherwise
    """
    # Get the three orthogonal direction vectors for each timber
    dirs1 = [timber1.get_length_direction_global(), timber1.get_width_direction_global(), timber1.get_height_direction_global()]
    dirs2 = [timber2.get_length_direction_global(), timber2.get_width_direction_global(), timber2.get_height_direction_global()]
    
    # Check all pairs of directions
    for dir1 in dirs1:
        for dir2 in dirs2:
            dot_product = Abs(numeric_dot_product(dir1, dir2))
            
            if tolerance is None:
                if equality_test(dot_product, 1):
                    return True
            else:
                if Abs(dot_product - 1) < tolerance:
                    return True
    
    return False

def are_timbers_plane_aligned(timber1: PerfectTimberWithin, timber2: PerfectTimberWithin, tolerance: Optional[Numeric] = None) -> bool:
    """
    Check if two timbers are plane aligned
    
    Args:
        timber1: First timber
        timber2: Second timber  
        tolerance: Optional numerical tolerance for parallel check. If None, uses exact
                   equality (recommended when using SymPy Rational types). If provided,
                   uses approximate floating-point comparison.
        
    Returns:
        True if timbers have at least one pair of parallel long faces, False otherwise
    """
    # Long faces are determined by width_direction and height_direction
    # RIGHT/LEFT faces are perpendicular to width_direction
    # FRONT/BACK faces are perpendicular to height_direction
    long_face_normals1 = [timber1.get_width_direction_global(), timber1.get_height_direction_global()]
    long_face_normals2 = [timber2.get_width_direction_global(), timber2.get_height_direction_global()]
    
    # Check if any pair of long face normals are parallel
    for normal1 in long_face_normals1:
        for normal2 in long_face_normals2:
            dot_product = Abs(numeric_dot_product(normal1, normal2))
            
            if tolerance is None:
                if equality_test(dot_product, 1):
                    return True
            else:
                if Abs(dot_product - 1) < tolerance:
                    return True
    
    return False

def do_xy_cross_section_on_parallel_timbers_overlap(timberA: PerfectTimberWithin, timberB: PerfectTimberWithin) -> bool:
    """
    Check if the cross-section of two parallel timbers overlap.
    
    Converts timberB into timberA's local space and checks if the XY cross-sections
    (defined by bottom_position and size) overlap.

    Args:
        timberA: First timber
        timberB: Second timber

    Returns:
        True if the cross-sections overlap, False otherwise
    """
    from sympy import Rational
    
    assert are_vectors_parallel(timberA.get_length_direction_global(), timberB.get_length_direction_global()), "Timbers must be parallel"

    # Convert timberB's bottom position into timberA's local space
    timberB_bottom_local = timberA.transform.global_to_local(timberB.get_bottom_position_global())
    
    # In timberA's local space:
    # - timberA's cross section is centered at (0, 0) in XY plane
    # - timberA spans from (-width/2, -height/2) to (width/2, height/2)
    timberA_x_min = -timberA.size[0] / Rational(2)
    timberA_x_max = timberA.size[0] / Rational(2)
    timberA_y_min = -timberA.size[1] / Rational(2)
    timberA_y_max = timberA.size[1] / Rational(2)
    
    # timberB's cross section is centered at (timberB_bottom_local.x, timberB_bottom_local.y)
    # We need to transform timberB's width and height directions into timberA's local space
    # to determine the extents of timberB's cross section
    
    # Get timberB's width and height directions in global space
    timberB_width_dir_global = timberB.get_width_direction_global()
    timberB_height_dir_global = timberB.get_height_direction_global()
    
    # Convert to timberA's local space (just rotate, don't translate)
    from kumiki.rule import safe_transform_vector
    timberB_width_dir_local = safe_transform_vector(timberA.orientation.matrix.T, timberB_width_dir_global)
    timberB_height_dir_local = safe_transform_vector(timberA.orientation.matrix.T, timberB_height_dir_global)
    
    # Get the four corners of timberB's cross section in timberA's local space
    # Start from timberB's center in local space
    timberB_center_local_xy = create_v2(timberB_bottom_local[0], timberB_bottom_local[1])
    
    # Offset vectors for the corners (in timberA's local XY plane)
    half_width = timberB.size[0] / Rational(2)
    half_height = timberB.size[1] / Rational(2)
    
    # Corner offsets in timberA's local space
    offset_width_local = create_v2(timberB_width_dir_local[0], timberB_width_dir_local[1]) * half_width
    offset_height_local = create_v2(timberB_height_dir_local[0], timberB_height_dir_local[1]) * half_height
    
    # Four corners of timberB in timberA's local XY coordinates
    corner1 = timberB_center_local_xy + offset_width_local + offset_height_local
    corner2 = timberB_center_local_xy + offset_width_local - offset_height_local
    corner3 = timberB_center_local_xy - offset_width_local + offset_height_local
    corner4 = timberB_center_local_xy - offset_width_local - offset_height_local
    
    # Find axis-aligned bounding box of timberB in timberA's local space
    from sympy import Min, Max
    timberB_x_min = Min(corner1[0], corner2[0], corner3[0], corner4[0])
    timberB_x_max = Max(corner1[0], corner2[0], corner3[0], corner4[0])
    timberB_y_min = Min(corner1[1], corner2[1], corner3[1], corner4[1])
    timberB_y_max = Max(corner1[1], corner2[1], corner3[1], corner4[1])
    
    # Check if the axis-aligned bounding boxes overlap
    # Two rectangles overlap if they overlap in both X and Y dimensions
    x_overlap = timberA_x_max >= timberB_x_min and timberB_x_max >= timberA_x_min
    y_overlap = timberA_y_max >= timberB_y_min and timberB_y_max >= timberA_y_min
    
    return x_overlap and y_overlap

