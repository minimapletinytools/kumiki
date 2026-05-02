"""
Joint Helper Functions (joint_shavings.py)

Collection of helper functions for validating and checking timber joint configurations.
These functions help ensure that joints are geometrically valid and sensibly constructed.
"""

from typing import Optional, Tuple, List, Union, cast
from kumiki.timber import *
from kumiki.rule import *
from kumiki.cutcsg import *
from kumiki.construction import *
from kumiki.measuring import *
from sympy import Abs, Rational



    

def orientation_pointing_towards_face_sitting_on_face(towards_face : TimberFace, sitting_face : TimberFace) -> 'Orientation':
    """
    Returns a marking orientation with +z toward towards_face and +y pointing into the timber from sitting_face.

    Marking transforms use a convention where, for transforms sitting on a timber face,
    +y points into the timber. This helper builds that orientation from two perpendicular faces.

    Args:
        towards_face: The face the orientation's +z axis should point toward.
        sitting_face: The face the orientation is sitting on; its outward normal becomes -y.

    Returns:
        Orientation with +z pointing toward towards_face and +y pointing into the timber.

    Raises:
        AssertionError: If towards_face and sitting_face are not perpendicular.
    """
    assert are_vectors_perpendicular(towards_face.get_direction(), sitting_face.get_direction())
    return Orientation.from_z_and_y(towards_face.get_direction(), -sitting_face.get_direction())

def scribe_face_plane_onto_centerline(face: TimberFace, face_timber: TimberLike) -> UnsignedPlane:
    """
    Mark the face plane on a timber.
    
    Returns the plane defined by the face on face_timber. This plane can then be measured 
    onto another timber's centerline to find shoulder plane positions in various butt joints.
    
    Args:
        face: The face on face_timber to mark
        face_timber: The timber whose face defines the plane
    
    Returns:
        UnsignedPlane representing the face plane. This can be measured onto a centerline using
        mark_distance_from_end_along_centerline() to find intersection points.
    
    Example:
        >>> # Mark the plane for timber_b's FRONT face
        >>> face_plane = scribe_face_plane_onto_centerline(
        ...     face=TimberFace.FRONT,
        ...     face_timber=timber_b
        ... )
        >>> # Then measure onto timber_a's centerline
        >>> marking = mark_distance_from_end_along_centerline(face_plane, timber_a)
        >>> shoulder_distance = measurement.distance
    """
    # Get the face plane (any point on the face works - we use locate_into_face for simplicity)
    return locate_into_face(0, face, face_timber)


def locate_pat_shoulder_plane_from_centerline_to_reference_face(
    shoulder_timber: TimberLike,
    reference_timber: TimberLike,
    reference_face: TimberFace,
) -> Plane:
    """
    Compute a shoulder plane on `shoulder_timber` using a face plane on `reference_timber`.

    This helper assumes a plane-aligned arrangement (PAT-style usage). It scribes the
    reference face plane onto the shoulder timber centerline, then returns the timber
    cross-section plane at that mark (normal = shoulder timber length direction).

    Args:
        shoulder_timber: Timber receiving the shoulder plane.
        reference_timber: Timber that owns the reference face.
        reference_face: Face on `reference_timber` that defines where the shoulder lands.

    Returns:
        Plane perpendicular to `shoulder_timber` length axis at the marked shoulder.
    """
    reference_plane = scribe_face_plane_onto_centerline(reference_face, reference_timber)
    shoulder_distance_from_bottom = mark_distance_from_end_along_centerline(
        reference_plane,
        shoulder_timber,
        TimberReferenceEnd.BOTTOM,
    ).distance

    shoulder_length_direction = shoulder_timber.get_length_direction_global()
    shoulder_point = (
        shoulder_timber.get_bottom_position_global()
        + shoulder_length_direction * shoulder_distance_from_bottom
    )

    return Plane(normal=shoulder_length_direction, point=shoulder_point)


# TODO DELETE THIS just 
def scribe_centerline_onto_centerline(timber: TimberLike) -> Line:
    """
    Mark the centerline of a timber.
    
    Returns the Line representing the timber's centerline. This line can then be measured 
    onto another timber's centerline to find closest points between skew centerlines.
    
    This is useful for positioning timbers relative to each other, especially in
    complex 3D joints where centerlines may be skew (non-intersecting, non-parallel).

    Args:
        timber: The timber whose centerline to mark

    Returns:
        Line representing the timber's centerline. This can be measured onto another
        timber's centerline using mark_distance_from_end_along_centerline() to find closest points.
        
    Example:
        >>> # Mark the centerline of timber_b
        >>> centerline_b = scribe_centerline_onto_centerline(timber_b)
        >>> # Then measure onto timber_a's centerline
        >>> measurement_a = mark_distance_from_end_along_centerline(centerline_b, timber_a)
        >>> dist_a = measurement_a.distance
    """
    # Mark the centerline of the timber as a Line feature
    return locate_centerline(timber)

def check_timber_overlap_for_splice_joint_is_sensible(
    timberA: TimberLike,
    timberB: TimberLike,
    timberA_end: TimberReferenceEnd,
    timberB_end: TimberReferenceEnd
) -> Optional[str]:
    """
    Check if two timbers overlap in a sensible way for a splice joint.
    
    A sensible splice joint configuration requires:
    1. The joint ends are pointing in opposite directions (anti-parallel)
    2. The joint end planes either touch each other or go past each other
    3. The joint end planes have not gone so far past each other that they reach 
       the opposite end of the other timber
    
    ASCII diagram of a sensible splice joint:
    A |==================| <- timberA_end
       timberB_end -> |==================| B
    
    Args:
        timberA: First timber in the splice joint
        timberB: Second timber in the splice joint
        timberA_end: Which end of timberA is being joined (TOP or BOTTOM)
        timberB_end: Which end of timberB is being joined (TOP or BOTTOM)
    
    Returns:
        Optional[str]: None if the configuration is sensible, otherwise a string
                      explaining why the configuration fails the sensibility check
    
    Example:
        >>> error = check_timber_overlap_for_splice_joint_is_sensible(
        ...     gooseneck, receiving, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP
        ... )
        >>> if error:
        ...     print(f"Joint configuration error: {error}")
    """
    assert isinstance(timberA_end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(timberA_end).__name__}"
    assert isinstance(timberB_end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(timberB_end).__name__}"
    # Get the length directions for both timbers
    timberA_length_direction = timberA.get_length_direction_global()
    timberB_length_direction = timberB.get_length_direction_global()
    
    # First, check that timbers are parallel (not perpendicular or skewed)
    dot_product = numeric_dot_product(timberA_length_direction, timberB_length_direction)
    
    if not are_vectors_parallel(timberA_length_direction, timberB_length_direction):
        return (
            f"Timbers are not parallel. TimberA length direction {timberA_length_direction.T} "
            f"and timberB length direction {timberB_length_direction.T} must be parallel "
            f"(dot product should be ±1, got {float(dot_product):.3f})"
        )
    
    # Get the end positions and directions in world coordinates
    # Note: end_direction points AWAY from the timber (outward from the end)
    if timberA_end == TimberReferenceEnd.TOP:
        timberA_end_pos = locate_top_center_position(timberA).position
        timberA_end_direction = timberA.get_length_direction_global()  # Points away from timber
        timberA_opposite_end_pos = timberA.get_bottom_position_global()
    else:  # BOTTOM
        timberA_end_pos = timberA.get_bottom_position_global()
        timberA_end_direction = -timberA.get_length_direction_global()  # Points away from timber
        timberA_opposite_end_pos = locate_top_center_position(timberA).position
    
    if timberB_end == TimberReferenceEnd.TOP:
        timberB_end_pos = locate_top_center_position(timberB).position
        timberB_end_direction = timberB.get_length_direction_global()  # Points away from timber
        timberB_opposite_end_pos = timberB.get_bottom_position_global()
    else:  # BOTTOM
        timberB_end_pos = timberB.get_bottom_position_global()
        timberB_end_direction = -timberB.get_length_direction_global()  # Points away from timber
        timberB_opposite_end_pos = locate_top_center_position(timberB).position
    
    # Check 1: The joint ends must be pointing in opposite directions (anti-parallel)
    # For a proper splice joint, the specified ends should point towards each other
    # (dot product of end directions should be close to -1)
    from kumiki.rule import safe_compare, Comparison
    end_dot_product = numeric_dot_product(timberA_end_direction, timberB_end_direction)
    
    if safe_compare(end_dot_product, 0, Comparison.GT):
        return (
            f"Joint ends are pointing in the same direction (dot product = {float(end_dot_product):.3f}). "
            f"For a splice joint, the ends should point in opposite directions (dot product should be -1). "
            f"TimberA {timberA_end.name} end direction: {timberA_end_direction.T}, "
            f"TimberB {timberB_end.name} end direction: {timberB_end_direction.T}"
        )
    
    # Check 2: The joint ends should either touch or overlap (not be separated)
    # Vector from timberA end to timberB end
    end_to_end_vector = timberB_end_pos - timberA_end_pos
    
    # Project this vector onto timberA's end direction
    # If positive, timberB end is in the direction timberA end is pointing (they overlap or touch)
    # If negative, timberB end is behind timberA end (they're separated)
    projection_A = numeric_dot_product(end_to_end_vector, timberA_end_direction)
    
    # Also check from timberB's perspective
    projection_B = -numeric_dot_product(end_to_end_vector, timberB_end_direction)
    
    # For a valid splice, at least one timber should be extending towards or past the other
    # Both projections should be >= 0 (allowing for small numerical errors)
    gap_threshold = -EPSILON_GENERIC * 10  # Allow small numerical errors
    
    if projection_A < gap_threshold and projection_B < gap_threshold:
        return (
            f"Joint ends are separated by a gap. The ends should touch or overlap. "
            f"Distance from timberA end to timberB end along timberA direction: {float(projection_A):.6f}. "
            f"Distance from timberB end to timberA end along timberB direction: {float(projection_B):.6f}"
        )
    
    # Check 3: The joint ends should not have gone so far past each other that they 
    # reach the opposite end of the other timber
    
    # Check if timberA end has passed through timberB's opposite end
    # Vector from timberB's opposite end to timberA's end
    vector_to_timberA_end = timberA_end_pos - timberB_opposite_end_pos
    # Project onto timberB's end direction (pointing from joined end towards opposite end)
    penetration_into_B = vector_to_timberA_end.dot(-timberB_end_direction)
    
    # If positive and large, timberA has penetrated through timberB
    if penetration_into_B > timberB.length + EPSILON_GENERIC:
        return (
            f"TimberA end has penetrated too far through timberB. "
            f"TimberA end extends {float(penetration_into_B):.3f} past timberB's joined end, "
            f"but timberB is only {float(timberB.length):.3f} long. "
            f"The joint should not extend past the opposite end of the timber."
        )
    
    # Check if timberB end has passed through timberA's opposite end
    vector_to_timberB_end = timberB_end_pos - timberA_opposite_end_pos
    penetration_into_A = vector_to_timberB_end.dot(-timberA_end_direction)
    
    if penetration_into_A > timberA.length + EPSILON_GENERIC:
        return (
            f"TimberB end has penetrated too far through timberA. "
            f"TimberB end extends {float(penetration_into_A):.3f} past timberA's joined end, "
            f"but timberA is only {float(timberA.length):.3f} long. "
            f"The joint should not extend past the opposite end of the timber."
        )
    
    # All checks passed
    return None


# TODO add nominal dimension variant instead
# TODO when you add actual dimensions on top of perfect timber within dimensions, you probably want a version that sizes to the actual dimensions...
def chop_timber_end_with_prism(timber: TimberLike, end: TimberReferenceEnd, distance_from_end_to_cut: Numeric) -> RectangularPrism:
    """
    Create a RectangularPrism CSG for chopping off material from a timber end (in local coordinates).
    
    Creates a CSG prism in the timber's local coordinate system that starts at 
    distance_from_end_to_cut from the timber end and extends to infinity in the timber 
    length direction. The prism has the same cross-section size as the timber.
    
    This is useful when you need a volumetric cut that exactly matches the timber's 
    cross-section (e.g., for CSGCut objects in compound cuts).
    
    Args:
        timber: The timber to create a chop prism for
        end: Which end to chop from (TOP or BOTTOM)
        distance_from_end_to_cut: Distance from the end where the cut begins
    
    Returns:
        RectangularPrism: A CSG prism in local coordinates representing the material beyond 
               distance_from_end_to_cut from the end, extending to infinity
    
    Example:
        >>> # Chop everything beyond 2 inches from the top of a timber
        >>> chop_prism = chop_timber_end_with_prism(my_timber, TimberReferenceEnd.TOP, Rational(2))
        >>> # This creates a semi-infinite prism starting 2 inches from the top
    """
    assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
    # In timber local coordinates:
    # - Bottom is at 0
    # - Top is at timber.length
    # - Z-axis points along the length direction (bottom to top)
    
    if end == TimberReferenceEnd.TOP:
        # For TOP end:
        # - Start at (timber.length - distance_from_end_to_cut)
        # - Extend to infinity in the +Z direction (beyond the top)
        start_distance_local = timber.length - distance_from_end_to_cut
        end_distance_local = None  # Infinite in +Z direction
    else:  # BOTTOM
        # For BOTTOM end:
        # - Start at infinity in the -Z direction (below the bottom)
        # - End at distance_from_end_to_cut from the bottom
        start_distance_local = None  # Infinite in -Z direction
        end_distance_local = distance_from_end_to_cut
    
    # Create the prism with identity transform (local coordinates)
    return RectangularPrism(
        size=timber.size,
        transform=Transform.identity(),
        start_distance=start_distance_local,
        end_distance=end_distance_local
    )


def chop_timber_end_with_half_plane(timber: TimberLike, end: TimberReferenceEnd, distance_from_end_to_cut: Numeric) -> HalfSpace:
    """
    Create a HalfSpace CSG for chopping off material from a timber end (in local coordinates).
    
    Creates a half-plane cut in the timber's local coordinate system, perpendicular to the 
    timber's length direction, positioned at distance_from_end_to_cut from the specified end.
    The half-plane removes everything beyond that distance.
    
    This is simpler and more efficient than a prism-based cut when you just need a planar
    cut perpendicular to the timber's length (e.g., for simple butt joints or splice joints).
    
    Args:
        timber: The timber to create a chop half-plane for
        end: Which end to chop from (TOP or BOTTOM)
        distance_from_end_to_cut: Distance from the end where the cut plane is positioned
    
    Returns:
        HalfSpace: A half-plane in local coordinates that removes material beyond 
                   distance_from_end_to_cut from the end
    
    Example:
        >>> # Chop everything beyond 2 inches from the top of a timber
        >>> chop_plane = chop_timber_end_with_half_plane(my_timber, TimberReferenceEnd.TOP, Rational(2))
        >>> # This creates a half-plane 2 inches from the top, removing everything beyond
    """
    assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
    # In timber local coordinates:
    # - Bottom is at 0
    # - Top is at timber.length
    # - Z-axis (local) points along the length direction (bottom to top)
    
    # The half-plane is perpendicular to the length direction (Z-axis in local coords)
    # Normal vector in local coordinates is always +Z or -Z
    
    if end == TimberReferenceEnd.TOP:
        # For TOP end:
        # - Cut plane is at (timber.length - distance_from_end_to_cut)
        # - Normal points in +Z direction (away from the timber body, toward the top)
        # - We want to remove everything beyond this point (in +Z direction)
        # - HalfSpace keeps points where normal·P >= offset
        # - So normal should point in +Z and offset should be the cut position
        normal = create_v3(0, 0, 1)
        # note offset is measured from the timber bottom position, not the timber top end position
        offset = timber.length - distance_from_end_to_cut
    else:  # BOTTOM
        # For BOTTOM end:
        # - Cut plane is at distance_from_end_to_cut from bottom
        # - Normal points in -Z direction (away from the timber body, toward the bottom)
        # - We want to remove everything beyond this point (in -Z direction)
        # - HalfSpace keeps points where normal·P >= offset
        # - So normal should point in -Z and offset should be negative of cut position
        normal = create_v3(0, 0, -1)
        offset = -distance_from_end_to_cut
    
    return HalfSpace(normal=normal, offset=offset)

def chop_lap_on_timber_end(
    lap_timber: TimberLike,
    lap_timber_end: TimberReferenceEnd,
    lap_timber_face: TimberFace,
    lap_length: Numeric,
    lap_shoulder_position_from_lap_timber_end: Numeric,
    lap_depth: Numeric
) -> Tuple[CutCSG, HalfSpace]:
    """
    Create CSG cuts for a lap joint between two timber ends.
    
    Creates material removal volumes for both timbers in a lap joint configuration where
    one timber (top lap) has material removed from one face, and the other timber (bottom lap)
    has material removed from the opposite face so they interlock.
    
        lap_timber_face
        v           |--------| lap_length
    ╔════════════════════════╗          -
    ║face_lap_timber         ║          | lap_depth
    ║               ╔════════╝          -
    ║               ║
    ║               ║
    ╚═══════════════╝
                    ^ lap_shoulder_position_from_lap_timber_end
    
    Args:
        lap_timber: The timber that will have material removed from the specified face
        lap_timber_end: Which end of the top lap timber is being joined
        lap_timber_face: Which face of the top lap timber to remove material from
        lap_length: Length of the lap region along the timber length
        lap_shoulder_position_from_lap_timber_end: Distance from the timber end to the shoulder (inward)
        lap_depth: Depth of material to remove (measured from lap_timber_face)
    
    Returns:
        Tuple of (lap_prism, end_cut_half_plane) representing material to remove from the timber
        Both CSGs are in local coordinates of the timber
    
    Example:
        >>> # Create a half-lap joint
        >>> top_lap, top_end_cut = chop_lap_on_timber_end(
        ...     timber_a, TimberReferenceEnd.TOP,
        ...     TimberFace.BOTTOM, lap_length=4, lap_depth=2, shoulder_pos=1
        ... )
    """
    assert isinstance(lap_timber_end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(lap_timber_end).__name__}"
    from sympy import Rational
    
    # Step 1: Determine the end positions and shoulder position of the top lap timber
    if lap_timber_end == TimberReferenceEnd.TOP:
        lap_end_pos = locate_top_center_position(lap_timber).position
        lap_direction = lap_timber.get_length_direction_global() 
    else:  # BOTTOM
        lap_end_pos = locate_bottom_center_position(lap_timber).position
        lap_direction = -lap_timber.get_length_direction_global()
    
    # Calculate the shoulder position (where the lap starts)
    shoulder_pos_global = lap_end_pos - lap_direction * lap_shoulder_position_from_lap_timber_end
    
    # Calculate the end of the lap (shoulder + lap_length)
    lap_end_pos_global = shoulder_pos_global + lap_direction * lap_length
    
    # Step 3: Create half-plane cuts to remove the ends beyond the lap region
    # Top lap: remove everything beyond the shoulder position (towards the timber end)
    lap_end_distance_from_bottom = ((lap_end_pos_global - lap_timber.get_bottom_position_global()).T * lap_timber.get_length_direction_global())[0, 0]
    lap_shoulder_distance_from_bottom = ((shoulder_pos_global - lap_timber.get_bottom_position_global()).T * lap_timber.get_length_direction_global())[0, 0]
    
    lap_shoulder_distance_from_end = (lap_timber.length - lap_end_distance_from_bottom
                                         if lap_timber_end == TimberReferenceEnd.TOP 
                                         else lap_end_distance_from_bottom)
                                  
    lap_half_plane = chop_timber_end_with_half_plane(lap_timber, lap_timber_end, lap_shoulder_distance_from_end)
    
    
    # Step 4: Determine the orientation of the lap based on lap_timber_face
    
    # For the top lap timber: remove material on the specified face
    # The prism should extend from shoulder to lap_end in length direction
    # And remove lap_depth of material perpendicular to the face
    
    # Calculate the prism dimensions and position for top lap
    # Start and end distances in local coordinates
    # Ensure start <= end for RectangularPrism
    prism_start = min(lap_shoulder_distance_from_bottom, lap_end_distance_from_bottom)
    prism_end = max(lap_shoulder_distance_from_bottom, lap_end_distance_from_bottom)
    
    # Step 5: Find where the two laps meet based on lap_depth
    # The top lap removes material from lap_timber_face
    # The bottom lap removes material from the opposite side
    
    # For a face-based lap, we need to offset the prism perpendicular to the face
    # Get the face direction and offset
    if lap_timber_face == TimberFace.TOP or lap_timber_face == TimberFace.BOTTOM:
        raise ValueError("cannot cut lap on end faces")
    elif lap_timber_face == TimberFace.LEFT or lap_timber_face == TimberFace.RIGHT:
        # Lap is on a width face (X-axis in local coords)
        # Remove material from the OPPOSITE side of lap_timber_face
        # lap_depth is the thickness of material we KEEP on the lap_timber_face side
        if lap_timber_face == TimberFace.RIGHT:
            # Keep lap_depth on RIGHT side, remove from LEFT side
            # Remove from x = -size[0]/2 to x = +size[0]/2 - lap_depth
            removal_width = lap_timber.size[0] - lap_depth
            x_offset = -lap_timber.size[0] / Rational(2) + removal_width / Rational(2)
        else:  # LEFT
            # Keep lap_depth on LEFT side, remove from RIGHT side
            # Remove from x = -size[0]/2 + lap_depth to x = +size[0]/2
            removal_width = lap_timber.size[0] - lap_depth
            x_offset = lap_timber.size[0] / Rational(2) - removal_width / Rational(2)
        
        lap_prism = RectangularPrism(
            size=create_v2(removal_width, lap_timber.size[1]),
            transform=Transform(position=create_v3(x_offset, 0, 0), orientation=Orientation.identity()),
            start_distance=prism_start,
            end_distance=prism_end
        )
    else:  # FRONT or BACK
        # Lap is on a height face (Y-axis in local coords)
        # Remove material from the OPPOSITE side of lap_timber_face
        # lap_depth is the thickness of material we KEEP on the lap_timber_face side
        if lap_timber_face == TimberFace.FRONT:
            # Keep lap_depth on FRONT side, remove from BACK side
            # Remove from y = -size[1]/2 to y = +size[1]/2 - lap_depth
            removal_height = lap_timber.size[1] - lap_depth
            y_offset = -lap_timber.size[1] / Rational(2) + removal_height / Rational(2)
        else:  # BACK
            # Keep lap_depth on BACK side, remove from FRONT side
            # Remove from y = -size[1]/2 + lap_depth to y = +size[1]/2
            removal_height = lap_timber.size[1] - lap_depth
            y_offset = lap_timber.size[1] / Rational(2) - removal_height / Rational(2)
        
        lap_prism = RectangularPrism(
            size=create_v2(lap_timber.size[0], removal_height),
            transform=Transform(position=create_v3(0, y_offset, 0), orientation=Orientation.identity()),
            start_distance=prism_start,
            end_distance=prism_end
        )
    
    # Step 7: Return the lap prism and end cut separately
    return lap_prism, lap_half_plane

def chop_lap_on_timber_ends(
    top_lap_timber: TimberLike,
    top_lap_timber_end: TimberReferenceEnd,
    bottom_lap_timber: TimberLike,
    bottom_lap_timber_end: TimberReferenceEnd,
    top_lap_timber_face: TimberLongFace,
    lap_length: Numeric,
    top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Numeric,
    lap_depth: Numeric
) -> Tuple[Tuple[CutCSG, HalfSpace], Tuple[CutCSG, HalfSpace]]:
    """
    Create CSG cuts for a lap joint between two timber ends.
    
    Creates material removal volumes for both timbers in a lap joint configuration where
    one timber (top lap) has material removed from one face, and the other timber (bottom lap)
    has material removed from the opposite face so they interlock.
    
        top_lap_timber_face
        v           |--------| lap_length
    ╔════════════════════════╗╔══════╗  -
    ║face_lap_timber         ║║      ║  | lap_depth
    ║               ╔════════╝║      ║  -
    ║               ║╔════════╝      ║ 
    ║               ║║      timberB  ║ 
    ╚═══════════════╝╚═══════════════╝
                    ^ top_lap_shoulder_position_from_top_lap_shoulder_timber_end
    
    Args:
        top_lap_timber: The timber that will have material removed from the specified face
        top_lap_timber_end: Which end of the top lap timber is being joined
        bottom_lap_timber: The timber that will have material removed from the opposite face
        bottom_lap_timber_end: Which end of the bottom lap timber is being joined
        top_lap_timber_face: Which face of the top lap timber to remove material from
        lap_length: Length of the lap region along the timber length
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Distance from the timber end to the shoulder (inward)
        lap_depth: Depth of material to remove (measured from top_lap_timber_face)
    
    Returns:
        Tuple of ((top_lap_prism, top_end_cut), (bottom_lap_prism, bottom_end_cut))
        Each tuple contains the lap CSG and end cut HalfSpace for that timber
        All CSGs are in local coordinates of their respective timbers
    
    Example:
        >>> # Create a half-lap joint
        >>> (top_lap, top_end), (bottom_lap, bottom_end) = chop_lap_on_timber_ends(
        ...     timber_a, TimberReferenceEnd.TOP,
        ...     timber_b, TimberReferenceEnd.BOTTOM,
        ...     TimberFace.BOTTOM, lap_length=4, lap_depth=2, shoulder_pos=1
        ... )
    """

    # assert the face types are correct
    assert isinstance(top_lap_timber_end, TimberReferenceEnd), \
        f"expected TimberReferenceEnd, got {type(top_lap_timber_end).__name__}"
    assert isinstance(bottom_lap_timber_end, TimberReferenceEnd), \
        f"expected TimberReferenceEnd, got {type(bottom_lap_timber_end).__name__}"
    assert isinstance(top_lap_timber_face, TimberLongFace), \
        f"expected TimberLongFace, got {type(top_lap_timber_face).__name__}"

    # Assert that the 2 timbers are face aligned
    assert are_timbers_face_aligned(top_lap_timber, bottom_lap_timber), \
        f"Timbers must be face-aligned for a splice lap joint. " \
        f"{top_lap_timber.ticket.name} and {bottom_lap_timber.ticket.name} orientations are not related by 90-degree rotations."
    
    # Assert the 2 timbers are parallel (either same direction or opposite)
    assert are_vectors_parallel(top_lap_timber.get_length_direction_global(), bottom_lap_timber.get_length_direction_global()), \
        f"Timbers must be parallel for a splice lap joint. " \
        f"{top_lap_timber.ticket.name} length_direction {top_lap_timber.get_length_direction_global().T} and " \
        f"{bottom_lap_timber.ticket.name} length_direction {bottom_lap_timber.get_length_direction_global().T} are not parallel."
    
    # Assert the 2 timber cross sections overlap at least a little
    assert do_xy_cross_section_on_parallel_timbers_overlap(top_lap_timber, bottom_lap_timber), \
        f"Timber cross sections should overlap for a splice lap joint or there is nothing to cut! " \
        f"{top_lap_timber.ticket.name} and {bottom_lap_timber.ticket.name} cross sections do not overlap."

    
    top_lap_prism, top_end_cut = chop_lap_on_timber_end(top_lap_timber, top_lap_timber_end, top_lap_timber_face.to.face(), lap_length, top_lap_shoulder_position_from_top_lap_shoulder_timber_end, lap_depth)
    top_lap_csg = (top_lap_prism, top_end_cut)

    # Step 2: Find the corresponding face on the bottom lap timber
    # Get top_lap_timber_face direction in global space
    top_lap_face_direction_global = top_lap_timber.get_face_direction_global(top_lap_timber_face)
    
    # Negate it to get the direction for the bottom timber face
    bottom_lap_face_direction_global = -top_lap_face_direction_global
    
    # Find which face of the bottom timber aligns with this direction
    bottom_lap_timber_face = bottom_lap_timber.get_closest_oriented_face_from_global_direction(bottom_lap_face_direction_global)
    
    # Step 3: Calculate the depth for the bottom lap
    # The bottom lap depth is measured from the bottom timber's face to the top timber's cutting plane
    # This accounts for any rotation or offset between the timbers
    # Create a plane at lap_depth from the top timber's face
    top_cutting_plane = locate_into_face(lap_depth, top_lap_timber_face, top_lap_timber)
    # Find the opposing face on the bottom timber
    top_face_direction = top_lap_timber.get_face_direction_global(top_lap_timber_face)
    bottom_face_direction = -top_face_direction
    bottom_face = bottom_lap_timber.get_closest_oriented_face_from_global_direction(bottom_face_direction)
    # Measure from the bottom face to the cutting plane
    marking = mark_distance_from_face_in_normal_direction(top_cutting_plane, bottom_lap_timber, bottom_face)
    bottom_lap_depth = Abs(marking.distance)
    
    # Step 4: Calculate the shoulder position for the bottom lap timber
    # Starting from scratch to avoid confusion between timber END and lap END
    #
    # For interlocking splice lap joint:
    # - Top timber SHOULDER → Bottom timber LAP END
    # - Top timber LAP END → Bottom timber SHOULDER
    
    # Calculate top timber's shoulder and lap end positions in global space
    if top_lap_timber_end == TimberReferenceEnd.TOP:
        top_timber_end_pos = locate_top_center_position(top_lap_timber).position
        top_lap_direction = top_lap_timber.get_length_direction_global() 
    else:  # BOTTOM
        top_timber_end_pos = locate_bottom_center_position(top_lap_timber).position
        top_lap_direction = -top_lap_timber.get_length_direction_global() 
    
    # Top timber shoulder: move inward from timber end by shoulder distance
    top_shoulder_global = top_timber_end_pos - top_lap_direction * top_lap_shoulder_position_from_top_lap_shoulder_timber_end
    
    # Top timber lap end: move outward from shoulder by lap_length
    top_lap_end_global = top_shoulder_global + top_lap_direction * lap_length
    
    bottom_shoulder_global = top_lap_end_global

    # Project bottom shoulder position onto bottom timber's length axis
    bottom_shoulder_from_bottom_timber_bottom = safe_dot_product((bottom_shoulder_global - bottom_lap_timber.get_bottom_position_global()), bottom_lap_timber.get_length_direction_global())
    
    # Calculate shoulder distance from bottom timber's reference end
    if bottom_lap_timber_end == TimberReferenceEnd.TOP:
        # Measuring from top end
        bottom_lap_shoulder_position_from_bottom_timber_end = bottom_lap_timber.length - bottom_shoulder_from_bottom_timber_bottom
    else:  # BOTTOM
        # Measuring from bottom end
        bottom_lap_shoulder_position_from_bottom_timber_end = bottom_shoulder_from_bottom_timber_bottom

    bottom_lap_prism, bottom_end_cut = chop_lap_on_timber_end(bottom_lap_timber, bottom_lap_timber_end, bottom_lap_timber_face, lap_length, bottom_lap_shoulder_position_from_bottom_timber_end, bottom_lap_depth)
    bottom_lap_csg = (bottom_lap_prism, bottom_end_cut)
    return (top_lap_csg, bottom_lap_csg)


# TODO I think this is cutting on the wrong face...
def chop_profile_on_timber_face(timber: TimberLike, end: TimberReferenceEnd, face: TimberFace, profile: Union[List[V2], List[List[V2]]], depth: Numeric, profile_y_offset_from_end: Numeric = Integer(0)) -> Union[SolidUnion, ConvexPolygonExtrusion]:
    """
    Create a CSG extrusion of a profile (or multiple profiles) on a timber face.
    See the diagram below for understanding how to interpret the profile in the timber's local space based on the end and face arguments.


                            end
    timber                   v                                                  ^
    ╔════════════════════════╗                                                  -x
    ║face                    ║< (0,profile_y_offset_from_end) of the profile    +y ->
    ╚════════════════════════╝                                                  +x
                                                                                v


    Args:
        timber: The timber to create a profile for
        end: Which end to create the profile on (determines the origin and rotation of the profile)
        face: Which face to create the profile on (determines the origin, rotation, and extrusion direction of the profile)
        profile: Either a single profile (List[V2]) or multiple profiles (List[List[V2]]).
                 Multiple profiles are provided as a convenience for creating non-convex shapes
                 by unioning multiple convex polygon extrusions.
        depth: Depth to extrude the profile through the timber's face
        profile_y_offset_from_end: Offset in the Y direction (along timber length from end).
                                   The profile will be translated by -profile_y_offset_from_end,
                                   so the origin (0,0) in profile coordinates corresponds to
                                   (0, profile_y_offset_from_end) in the timber's end-face coordinate system.

    Returns:
        CutCSG representing the extruded profile(s) in the timber's local coordinates.
        If multiple profiles are provided, returns a SolidUnion of all extruded profiles.
        
    Notes:
        - The profile is positioned at the intersection of the specified end and face
        - Profile coordinates: X-axis points into timber from end, Y-axis across face, origin at (0,0) on face
        - The extrusion extends inward from the face by the specified depth
        - For non-convex shapes, provide multiple profiles (List[List[V2]]) which will be 
          individually extruded and unioned together
        - Each individual profile uses ConvexPolygonExtrusion, so complex non-convex shapes
          should be decomposed into multiple convex profiles
    """
    assert isinstance(end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(end).__name__}"
    from sympy import Rational, Matrix
    from kumiki.rule import Orientation, Transform, create_v3, cross_product, safe_normalize_vector as normalize_vector
    from kumiki.cutcsg import ConvexPolygonExtrusion
    
    # Check if we have a single profile or multiple profiles
    # If the first element is a list, we have multiple profiles
    is_multiple_profiles = isinstance(profile, list) and len(profile) > 0 and isinstance(profile[0], list)
    
    if is_multiple_profiles:
        # Recursively call this function for each profile and union the results
        extrusions = []
        for single_profile in profile:
            extrusion = chop_profile_on_timber_face(timber, end, face, cast(List[V2], single_profile), depth, profile_y_offset_from_end)
            extrusions.append(extrusion)
        return SolidUnion(extrusions)
    
    # Single profile case - continue with original logic
    
    # Translate the profile by -profile_y_offset_from_end in the Y direction
    # This allows the user to specify profiles with arbitrary Y origins and position them correctly
    translated_profile = [point + create_v2(0, -profile_y_offset_from_end) for point in profile]
    
    # ========================================================================
    # Step 1: Determine the origin position in timber local coordinates
    # ========================================================================
    # The origin is at the intersection of the end and the face
    # In timber local coordinates:
    # - Local X-axis = width_direction
    # - Local Y-axis = height_direction
    # - Local Z-axis = length_direction (bottom to top)
    # - Origin is at bottom_position (center of bottom face)
    
    # Get Z coordinate based on end
    if end == TimberReferenceEnd.TOP:
        origin_z = timber.length
    else:  # BOTTOM
        origin_z = Rational(0)
    
    # Get X and Y offset based on face
    # The face determines where on the cross-section the origin is
    half_width = timber.size[0] / Rational(2)
    half_height = timber.size[1] / Rational(2)
    
    if face == TimberFace.TOP or face == TimberFace.BOTTOM:
        # For end faces, we can't really position a profile "on" them in the way described
        # This shouldn't happen based on the function's design
        raise ValueError(f"Face cannot be an end face (TOP or BOTTOM), got {face}")
    elif face == TimberFace.RIGHT:
        origin_x = half_width
        origin_y = Rational(0)
    elif face == TimberFace.LEFT:
        origin_x = -half_width
        origin_y = Rational(0)
    elif face == TimberFace.FRONT:
        origin_x = Rational(0)
        origin_y = half_height
    else:  # BACK
        origin_x = Rational(0)
        origin_y = -half_height
    
    origin_local = create_v3(origin_x, origin_y, origin_z)
    
    # ========================================================================
    # Step 2: Determine the profile coordinate system orientation
    # ========================================================================
    # The profile's coordinate system needs:
    # - X-axis: points along timber length (into timber from end)
    # - Y-axis: points across the face (perpendicular to length and face normal)
    # - Z-axis: points inward from face (extrusion direction)
    
    # Get face normal direction in timber local coordinates
    face_normal_local = face.get_direction()  # This gives the outward normal
    
    # Profile Y-axis: points towards the reference end
    if end == TimberReferenceEnd.TOP:
        profile_y_axis = create_v3(0, 0, 1)
    else:  # BOTTOM
        profile_y_axis = create_v3(0, 0, -1)
    
    # Profile Z-axis (extrusion): points outward from face (negative of face normal)
    profile_z_axis = face_normal_local
    
    # Profile Y-axis: perpendicular to X and Z, using right-hand rule
    # X = Y × Z (so that X, Y, Z form a right-handed system)
    profile_x_axis = cross_product(profile_y_axis, profile_z_axis)
    profile_x_axis = normalize_vector(profile_x_axis)
    
    # Create the orientation matrix for the profile
    # Columns are: X-axis, Y-axis, Z-axis
    profile_orientation_matrix = Matrix([
        [profile_x_axis[0], profile_y_axis[0], profile_z_axis[0]],
        [profile_x_axis[1], profile_y_axis[1], profile_z_axis[1]],
        [profile_x_axis[2], profile_y_axis[2], profile_z_axis[2]]
    ])
    
    profile_orientation = Orientation(profile_orientation_matrix)
    profile_transform = Transform(position=origin_local, orientation=profile_orientation)
    
    # ========================================================================
    # Step 3: Create the ConvexPolygonExtrusion
    # ========================================================================
    # The extrusion starts at the origin (start_distance=0) and extends 
    # inward by depth along the profile's Z-axis
    
    extrusion = ConvexPolygonExtrusion(
        points=translated_profile,
        transform=profile_transform,
        start_distance=-depth,
        end_distance=Rational(0),
    )
    
    return extrusion


def chop_shoulder_notch_aligned_with_timber(notch_timber: TimberLike, butting_timber: TimberLike, butting_timber_end: TimberReferenceEnd, distance_from_centerline: Numeric, notch_wall_relief_cut_angle_radians: Numeric = Integer(0)) -> Union[RectangularPrism, 'SolidUnion']:
    """
    Create a shoulder notch on notch_timber at a given distance from its centerline,
    oriented by the butting_timber's approach direction.

    Unlike chop_shoulder_notch_on_timber_face which is aligned to a specific face,
    this notch is aligned to the shoulder plane derived from the butting timber's
    approach direction (projected perpendicular to the notch timber's length axis).

    The notch bottom (shoulder plane) is distance_from_centerline away from the
    notch_timber's centerline. The notch opens outward from the centerline.
    The notch width is along the notch_timber's length axis. Both the width and
    span dimensions are oversized (max(size) * sqrt(2)) to guarantee full
    coverage regardless of the cross-section rotation.

    Args:
        notch_timber: The timber to cut the notch into
        butting_timber: The timber approaching the notch_timber (defines the notch direction)
        butting_timber_end: Which end of butting_timber approaches notch_timber
        distance_from_centerline: Distance from notch_timber's centerline to the shoulder plane
        notch_wall_relief_cut_angle_radians: Angle in radians for the side walls (default 0 = perpendicular).
                    Positive angles make walls slant outward.

    Returns:
        RectangularPrism (if notch_wall_relief_cut_angle=0) or SolidUnion (if notch_wall_relief_cut_angle>0)
        representing the material to remove (in notch_timber's local coordinates)
    """
    from sympy import sqrt, cos, Max

    notch_length_dir_global = notch_timber.get_length_direction_global()

    # Determine the butting timber's approach direction (pointing toward the notch timber)
    if butting_timber_end == TimberReferenceEnd.TOP:
        raw_approach = -butting_timber.get_length_direction_global()
    else:
        raw_approach = butting_timber.get_length_direction_global()

    # Project out the component along notch_timber's length axis to get the
    # approach direction in the plane perpendicular to the notch timber
    projected = raw_approach - notch_length_dir_global * safe_dot_product(raw_approach, notch_length_dir_global)
    approach_direction_global = normalize_vector(projected)

    # Find where the butting timber's centerline intersects the shoulder plane.
    # The shoulder plane is at distance_from_centerline from the notch timber's
    # centerline in the approach direction.
    shoulder_plane = locate_plane_from_edge_in_direction(
        notch_timber, TimberCenterline.CENTERLINE, approach_direction_global, distance_from_centerline
    )
    butting_centerline = locate_centerline(butting_timber)
    # Intersect butting centerline with shoulder plane
    denom = safe_dot_product(shoulder_plane.normal, butting_centerline.direction)
    assert not zero_test(denom), "Butting timber centerline is parallel to the shoulder plane"
    t = safe_dot_product(shoulder_plane.normal, shoulder_plane.point - butting_centerline.point) / denom
    intersection_global = butting_centerline.point + butting_centerline.direction * t

    
    # Oversized notch dimensions to guarantee full coverage at any rotation:
    # max cross-section dimension * sqrt(2) covers the worst-case diagonal
    max_size = Max(notch_timber.size[0], notch_timber.size[1])
    notch_span = max_size * sqrt(Integer(2))

    # Notch depth: from the shoulder plane outward past the timber surface.
    # The shoulder plane is distance_from_centerline from centerline; the timber
    # surface at worst is max_size * sqrt(2) / 2 from centerline.
    notch_depth = max_size * sqrt(Integer(2)) / Integer(2)

    # Notch width along the notch_timber length axis: compute the projection of the butting timber's
    # cross-section onto the notch_timber length axis. We also account for the shift along the notch
    # length due to the approach angle over the depth of the notch.
    w_dir = butting_timber.get_width_direction_global()
    h_dir = butting_timber.get_height_direction_global()
    
    # Cross-section span projected onto notch length
    cross_section_span_on_notch_length = (
        Abs(safe_dot_product(w_dir, notch_length_dir_global)) * butting_timber.size[0] +
        Abs(safe_dot_product(h_dir, notch_length_dir_global)) * butting_timber.size[1]
    )

    # Calculate shift of the butting timber along the notch length axis over the depth of the notch
    approach_dot_depth = safe_dot_product(raw_approach, approach_direction_global)
    approach_dot_length = safe_dot_product(raw_approach, notch_length_dir_global)
    
    if not zero_test(approach_dot_depth):
        shift_along_length = notch_depth * Abs(approach_dot_length / approach_dot_depth)
    else:
        shift_along_length = Integer(0)
        
    notch_width = cross_section_span_on_notch_length + shift_along_length

    # Build the notch prism in notch_timber local coordinates.
    # In local coords: Z = length, X = width (size[0]), Y = height (size[1]).
    # We need to express approach_direction_global in local coords.
    approach_direction_local = safe_transform_vector(
        notch_timber.orientation.matrix.T, approach_direction_global
    )
    notch_length_dir_local = create_v3(Integer(0), Integer(0), Integer(1))

    # Prism orientation in local coords:
    #   Z-axis = approach direction (outward from centerline, into the notch opening)
    #   X-axis = timber length direction (notch width runs along this)
    #   Y-axis = cross product to complete the right-handed system (notch span)
    prism_orientation = Orientation.from_z_and_x(approach_direction_local, notch_length_dir_local)

    prism_position_local = notch_timber.transform.global_to_local(intersection_global)

    prism_size = create_v2(notch_width, notch_span)

    notch_prism = RectangularPrism(
        size=prism_size,
        transform=Transform(position=prism_position_local, orientation=prism_orientation),
        start_distance=Integer(0),
        end_distance=notch_depth
    )

    if notch_wall_relief_cut_angle_radians == 0:
        return notch_prism

    angle_rad = notch_wall_relief_cut_angle_radians

    # The two wall edges run along the Y-axis of the prism (the span direction),
    # located at +/- notch_width/2 along the X-axis (timber length direction)
    span_direction_local = cross_product(approach_direction_local, notch_length_dir_local)
    span_direction_local = normalize_vector(span_direction_local)

    corner_point_1 = prism_position_local + notch_length_dir_local * (notch_width / Rational(2))
    corner_point_2 = prism_position_local - notch_length_dir_local * (notch_width / Rational(2))

    axis_1 = Axis(position=corner_point_1, direction=span_direction_local)
    axis_2 = Axis(position=corner_point_2, direction=span_direction_local)

    extended_end_distance = notch_depth / cos(angle_rad)

    left_wall_transform = notch_prism.transform.rotate_around_axis(axis_1, angle_rad)
    left_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=left_wall_transform,
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance
    )

    right_wall_transform = notch_prism.transform.rotate_around_axis(axis_2, -angle_rad)
    right_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=right_wall_transform,
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance
    )

    from kumiki.cutcsg import SolidUnion
    return SolidUnion([notch_prism, left_wall_prism, right_wall_prism])

def chop_shoulder_notch_on_timber_face(
    timber: TimberLike,
    notch_face: TimberFace,
    distance_along_timber: Numeric,
    notch_width: Numeric,
    notch_depth: Numeric,
    notch_wall_relief_cut_angle: Numeric = Integer(0)
) -> Union[RectangularPrism, 'SolidUnion']:
    """
    Create a rectangular shoulder notch on a timber face with optional angled walls.
    
    This creates a rectangular notch/pocket on a specified face of a timber.
    The notch is centered at a specific position along the timber's length.
    
    Args:
        timber: The timber to notch
        notch_face: The face to cut the notch into (LEFT, RIGHT, FRONT, or BACK)
        distance_along_timber: Distance from the timber's BOTTOM end to the center of the notch
        notch_width: Width of the notch (measured along timber length direction)
        notch_depth: Depth of the notch (measured perpendicular to the face, into the timber)
        notch_wall_relief_cut_angle: Angle in degrees for the side walls (default 0 = perpendicular).
                    Positive angles make walls slant outward like \\___/
    
    Returns:
        RectangularPrism (if notch_wall_relief_cut_angle=0) or SolidUnion (if notch_wall_relief_cut_angle>0) representing 
        the material to remove (in timber's local coordinates)
    
    Example:
        >>> # Create a 2" wide, 1" deep notch on the front face, 6" from bottom
        >>> notch = chop_shoulder_notch_on_timber_face(
        ...     timber, TimberFace.FRONT, inches(6), inches(2), inches(1)
        ... )
        >>> # Create the same notch but with 45° angled walls
        >>> notch_angled = chop_shoulder_notch_on_timber_face(
        ...     timber, TimberFace.FRONT, inches(6), inches(2), inches(1), notch_wall_relief_cut_angle=45
        ... )
    """
    from sympy import Rational, sin, cos, tan, pi
    
    # Validate face is a long face (not TOP or BOTTOM)
    if notch_face == TimberFace.TOP or notch_face == TimberFace.BOTTOM:
        raise ValueError("Cannot cut shoulder notch on end faces (TOP or BOTTOM)")
    
    # Validate dimensions
    if notch_width <= 0:
        raise ValueError(f"notch_width must be positive, got {notch_width}")
    if notch_depth <= 0:
        raise ValueError(f"notch_depth must be positive, got {notch_depth}")
    if distance_along_timber < 0 or distance_along_timber > timber.length:
        raise ValueError(
            f"distance_along_timber must be between 0 and timber.length ({timber.length}), "
            f"got {distance_along_timber}"
        )
    if notch_wall_relief_cut_angle < 0 or notch_wall_relief_cut_angle >= 90:
        raise ValueError(f"notch_wall_relief_cut_angle must be between 0 and 90 degrees, got {notch_wall_relief_cut_angle}")
    
    # Create notch prism with length direction perpendicular to the face (into timber)
    # Position the prism ON the face surface at distance_along_timber
    # Prism extends from surface (start_distance=0) to depth (end_distance=notch_depth)
    
    if notch_face == TimberFace.FRONT:
        # FRONT face: notch opens in -Y direction (into timber)
        # Position at BOTTOM of notch (inside timber by notch_depth), centered on timber width
        position = create_v3(Integer(0), timber.size[1] / Rational(2) - notch_depth, distance_along_timber)
        # Orientation: Z-axis points +Y (OUT from timber towards surface), X-axis along timber length (Z)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(0), Integer(1), Integer(0)),   # Z → +Y (out towards surface)
            create_v3(Integer(0), Integer(0), Integer(1))    # X → +Z (timber length)
        )
        # Size: notch_width along timber length, timber.size[0] (timber width) perpendicular
        prism_size = create_v2(notch_width, timber.size[0])
        # Corner points: at bottom of notch at ± notch_width/2 along timber length
        corner_point_1 = create_v3(Integer(0), timber.size[1] / Rational(2) - notch_depth, 
                                   distance_along_timber + notch_width / Rational(2))
        corner_point_2 = create_v3(Integer(0), timber.size[1] / Rational(2) - notch_depth, 
                                   distance_along_timber - notch_width / Rational(2))
        
    elif notch_face == TimberFace.BACK:
        # BACK face: notch opens in +Y direction (into timber)
        # Position at BOTTOM of notch (inside timber by notch_depth)
        position = create_v3(Integer(0), -timber.size[1] / Rational(2) + notch_depth, distance_along_timber)
        # Orientation: Z-axis points -Y (OUT from timber towards surface), X-axis along timber length (Z)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(0), Integer(-1), Integer(0)),  # Z → -Y (out towards surface)
            create_v3(Integer(0), Integer(0), Integer(1))    # X → +Z (timber length)
        )
        prism_size = create_v2(notch_width, timber.size[0])
        corner_point_1 = create_v3(Integer(0), -timber.size[1] / Rational(2) + notch_depth, 
                                   distance_along_timber + notch_width / Rational(2))
        corner_point_2 = create_v3(Integer(0), -timber.size[1] / Rational(2) + notch_depth, 
                                   distance_along_timber - notch_width / Rational(2))
        
    elif notch_face == TimberFace.RIGHT:
        # RIGHT face: notch opens in -X direction (into timber)
        # Position at BOTTOM of notch (inside timber by notch_depth)
        position = create_v3(timber.size[0] / Rational(2) - notch_depth, Integer(0), distance_along_timber)
        # Orientation: Z-axis points +X (OUT from timber towards surface), X-axis along timber length (Z)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(1), Integer(0), Integer(0)),   # Z → +X (out towards surface)
            create_v3(Integer(0), Integer(0), Integer(1))    # X → +Z (timber length)
        )
        # Size: notch_width along timber length, timber.size[1] (timber height) perpendicular
        prism_size = create_v2(notch_width, timber.size[1])
        corner_point_1 = create_v3(timber.size[0] / Rational(2) - notch_depth, Integer(0), 
                                   distance_along_timber + notch_width / Rational(2))
        corner_point_2 = create_v3(timber.size[0] / Rational(2) - notch_depth, Integer(0), 
                                   distance_along_timber - notch_width / Rational(2))
        
    else:  # LEFT
        # LEFT face: notch opens in +X direction (into timber)
        # Position at BOTTOM of notch (inside timber by notch_depth)
        position = create_v3(-timber.size[0] / Rational(2) + notch_depth, Integer(0), distance_along_timber)
        # Orientation: Z-axis points -X (OUT from timber towards surface), X-axis along timber length (Z)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(-1), Integer(0), Integer(0)),  # Z → -X (out towards surface)
            create_v3(Integer(0), Integer(0), Integer(1))    # X → +Z (timber length)
        )
        prism_size = create_v2(notch_width, timber.size[1])
        corner_point_1 = create_v3(-timber.size[0] / Rational(2) + notch_depth, Integer(0), 
                                   distance_along_timber + notch_width / Rational(2))
        corner_point_2 = create_v3(-timber.size[0] / Rational(2) + notch_depth, Integer(0), 
                                   distance_along_timber - notch_width / Rational(2))
    
    notch_additional_depth = timber.get_half_nominal_size_in_face_normal_axis(notch_face)

    # Create the notch prism
    notch_prism = RectangularPrism(
        size=prism_size,
        transform=Transform(position=position, orientation=orientation),
        start_distance=Integer(0),
        end_distance=notch_depth + notch_additional_depth
    )
    
    # If notch_wall_relief_cut_angle is 0, return the simple notch prism
    if notch_wall_relief_cut_angle == 0:
        return notch_prism
    
    # Create angled wall prisms by rotating copies of the notch prism around the corner edges
    # Convert angle to radians
    angle_rad = degrees(notch_wall_relief_cut_angle)
    
    # Determine the axis direction for rotation (parallel to notch face, perpendicular to timber length)
    # The rotation axes are perpendicular to the timber length direction
    if notch_face == TimberFace.FRONT or notch_face == TimberFace.BACK:
        # For FRONT/BACK faces, rotation axis is X (timber width direction)
        axis_direction = create_v3(Integer(1), Integer(0), Integer(0))
    else:  # LEFT or RIGHT faces
        # For LEFT/RIGHT faces, rotation axis is Y (timber height direction)
        axis_direction = create_v3(Integer(0), Integer(1), Integer(0))
    
    # Create axes through the corner edges
    axis_1 = Axis(position=corner_point_1, direction=axis_direction)
    axis_2 = Axis(position=corner_point_2, direction=axis_direction)
    
    # Calculate extended end_distance for angled walls
    # When the wall is angled, the prism needs to extend further to cover the full depth
    # The length along the angled surface is notch_depth / cos(angle)
    from sympy import cos
    extended_end_distance = (notch_depth + notch_additional_depth) / cos(angle_rad)
    
    # Create left wall prism by rotating the notch prism transform around the first corner
    left_wall_transform = notch_prism.transform.rotate_around_axis(axis_1, radians(angle_rad))
    left_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=left_wall_transform,
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance
    )
    
    # Create right wall prism by rotating around the second corner (opposite direction)
    right_wall_transform = notch_prism.transform.rotate_around_axis(axis_2, radians(-angle_rad))
    right_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=right_wall_transform,
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance
    )
    
    # Union the main notch with the two angled wall prisms
    from kumiki.cutcsg import SolidUnion
    return SolidUnion([notch_prism, left_wall_prism, right_wall_prism])