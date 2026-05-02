"""
Kumiki - Plain joint construction functions
Contains functions for creating joints between timbers
"""

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .joint_shavings import *
from kumiki.measuring import locate_top_center_position, locate_bottom_center_position, mark_distance_from_end_along_centerline, get_point_on_face_global, Space
from kumiki.joints.build_a_butt_joint_shavings import (
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
)


# ============================================================================
# Joint Construction Functions
# ============================================================================


def cut_plain_miter_joint(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two timbers, cutting each end at half the angle between them.

    Both ends are cut by the same bisecting plane so they meet flush at the corner.
    Works for any non-parallel angle.

    Args:
        arrangement: Corner joint arrangement with timber1, timber2, timber1_end, timber2_end.

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        ValueError: If the timbers are parallel or the intersection is degenerate.
    """
    import warnings
    
    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end
    
    # Get the end directions for each timber (pointing outward from the timber)
    if timberA_end == TimberReferenceEnd.TOP:
        directionA = timberA.get_length_direction_global()
        endA_position = locate_top_center_position(timberA).position
    else:  # BOTTOM
        directionA = -timberA.get_length_direction_global() 
        endA_position = locate_bottom_center_position(timberA).position
    
    if timberB_end == TimberReferenceEnd.TOP:
        directionB = timberB.get_length_direction_global()
        endB_position = locate_top_center_position(timberB).position
    else:  # BOTTOM
        directionB = -timberB.get_length_direction_global()
        endB_position = locate_bottom_center_position(timberB).position
    
    # Check that the timbers are not parallel
    if are_vectors_parallel(directionA, directionB):
        raise ValueError("Timbers cannot be parallel for a miter joint")
    
    # Find the intersection point (or closest point) between the two timber centerlines
    # Using the formula for closest point between two lines in 3D
    # Line 1: P1 = endA_position + t * directionA
    # Line 2: P2 = endB_position + s * directionB
    
    w0 = endA_position - endB_position
    a = directionA.dot(directionA)  # always >= 0
    b = directionA.dot(directionB)
    c = directionB.dot(directionB)  # always >= 0
    d = directionA.dot(w0)
    e = directionB.dot(w0)
    
    denom = a * c - b * b
    if zero_test(denom):
        raise ValueError("Cannot compute intersection point (degenerate case)")
    
    # Parameters for closest points on each line
    t = (b * e - c * d) / denom
    s = (a * e - b * d) / denom
    
    # Get the closest points on each centerline
    pointA = endA_position + directionA * t
    pointB = endB_position + directionB * s
    
    # The intersection point is the midpoint between the two closest points
    intersection_point = (pointA + pointB) / 2
    
    # Create the miter plane normal
    # Normalize the directions first
    normA = normalize_vector(directionA)
    normB = normalize_vector(directionB)
    
    # The bisecting direction is the normalized sum of the two directions
    # This points "into" the joint (towards the acute angle)
    # IMPORTANT: The bisector lives IN the miter plane (it's the line you draw on the wood)
    bisector = normalize_vector(normA + normB)
    
    # The plane formed by the two timber directions has normal:
    plane_normal = cross_product(normA, normB)
    
    # The miter plane:
    # 1. Contains the bisector line
    # 2. Is perpendicular to the plane formed by directionA and directionB
    # Therefore, the miter plane's normal is perpendicular to both the bisector
    # and the plane_normal. This is the cross product: bisector × plane_normal
    miter_normal = normalize_vector(cross_product(bisector, plane_normal))
    
    # The miter plane passes through the intersection point
    # Both timbers will be cut by this same plane, but each timber needs its half-plane
    # normal oriented to point "away from" that timber (into the material to remove).
    
    # For each timber, we need to create a HalfSpaceCut with the miter plane
    # The key is that the half-plane normal must be oriented so that:
    # 1. It represents the miter plane (normal perpendicular to the bisector line)
    # 2. The normal points "away from" the timber (into the material to remove)
    #
    # The miter_normal is perpendicular to both the bisector and the plane formed by
    # the two timbers. For each timber, we need to determine which orientation of the
    # miter plane normal points "away from" that timber.
    #
    # If directionA · miter_normal > 0, then miter_normal points away from timberA,
    # so we use +miter_normal. Otherwise, we use -miter_normal.
    
    # For timberA: check if miter_normal points away from or towards the timber
    from kumiki.rule import safe_compare, Comparison, safe_dot_product, safe_transform_vector
    dot_A = safe_dot_product(normA, miter_normal)
    if safe_compare(dot_A, 0, Comparison.GT):
        # Miter normal points away from timberA (in the direction of timberA's end)
        # This is what we want - the half-plane removes material in this direction
        normalA = miter_normal
    else:
        # Miter normal points towards timberA, so flip it
        normalA = -miter_normal
    
    # Convert to LOCAL coordinates for timberA
    # Transform normal: local_normal = orientation^T * global_normal
    # Transform offset: local_offset = global_offset - (global_normal · timber.get_bottom_position_global())
    local_normalA = safe_transform_vector(timberA.orientation.matrix.T, normalA)
    local_offsetA = safe_dot_product(intersection_point, normalA) - safe_dot_product(normalA, timberA.get_bottom_position_global())
    
    # For timberB: check if miter_normal points away from or towards the timber
    dot_B = safe_dot_product(normB, miter_normal)
    if safe_compare(dot_B, 0, Comparison.GT):
        # Miter normal points away from timberB (in the direction of timberB's end)
        normalB = miter_normal
    else:
        # Miter normal points towards timberB, so flip it
        normalB = -miter_normal
    
    # Convert to LOCAL coordinates for timberB
    local_normalB = safe_transform_vector(timberB.orientation.matrix.T, normalB)
    local_offsetB = safe_dot_product(intersection_point, normalB) - safe_dot_product(normalB, timberB.get_bottom_position_global())
    
    # Create the end cut HalfSpaces (in LOCAL coordinates relative to each timber)
    end_cut_A = HalfSpace(normal=local_normalA, offset=local_offsetA)
    end_cut_B = HalfSpace(normal=local_normalB, offset=local_offsetB)
    
    # Create the Cuts
    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut=end_cut_A if timberA_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=end_cut_A if timberA_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=None
    )
    
    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut=end_cut_B if timberB_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=end_cut_B if timberB_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=None
    )
    
    # Create CutTimbers with cuts passed at construction
    cut_timberA = CutTimber(timberA, cuts=[cutA])
    cut_timberB = CutTimber(timberB, cuts=[cutB])
    
    # Create and return the Joint with all data at construction
    joint = Joint(
        cut_timbers={"timberA": cut_timberA, "timberB": cut_timberB},
        ticket=JointTicket(joint_type="plain_miter"),
        jointAccessories={},
    )
    
    return joint

def cut_plain_miter_joint_on_face_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two face-aligned timbers meeting at a 90-degree corner.

    Like `cut_plain_miter_joint`, but requires the timbers to be orthogonal (perpendicular
    length axes). This is the common case for timber-frame corners.

    Args:
        arrangement: Corner joint arrangement with timber1, timber2, timber1_end, timber2_end.
                     Timbers must be face-aligned and orthogonal.

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        AssertionError: If the timbers are not orthogonal.
    """
    # Assert that the timber length axes are perpendicular (90-degree corner)
    assert are_timbers_orthogonal(arrangement.timber1, arrangement.timber2), \
        "Timbers must have perpendicular length axes (90-degree angle) for this joint type"
    
    return cut_plain_miter_joint(arrangement)


def cut_plain_butt_joint_on_face_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the face of the receiving timber.

    The receiving timber is not cut. The butt timber's end is trimmed to sit flat against the
    receiving timber's face. Timbers must be face-aligned and non-parallel.

    Args:
        arrangement: Butt joint arrangement with butt_timber, receiving_timber, butt_timber_end.
                     Timbers must be face-aligned and non-parallel.

    Returns:
        Joint object containing the cut butt timber and uncut receiving timber.

    Raises:
        AssertionError: If the timbers are not face-aligned or are parallel.
    """
    receiving_timber = arrangement.receiving_timber
    butt_timber = arrangement.butt_timber
    butt_end = arrangement.butt_timber_end
    
    assert are_timbers_face_aligned(receiving_timber, butt_timber), \
        "Timbers must be face-aligned (orientations related by 90-degree rotations) for this joint type"
    
    # Check that timbers are not parallel (butt joints require timbers to be at an angle)
    assert not are_vectors_parallel(receiving_timber.get_length_direction_global(), butt_timber.get_length_direction_global()), \
        "Timbers cannot be parallel for a butt joint"
    
    # Get the direction of the butt end (pointing outward from the timber)
    if butt_end == TimberReferenceEnd.TOP:
        butt_direction = butt_timber.get_length_direction_global()
        butt_end_position = locate_top_center_position(butt_timber).position
    else:  # BOTTOM
        butt_direction = -butt_timber.get_length_direction_global()
        butt_end_position = locate_bottom_center_position(butt_timber).position
    
    # Find which face of the receiving timber the butt is approaching
    # The butt approaches opposite to its end direction
    receiving_face = receiving_timber.get_closest_oriented_face_from_global_direction(-butt_direction)
    receiving_face_direction = receiving_timber.get_face_direction_global(receiving_face)
    
    # Compute the center position of the receiving face
    face_center = _get_face_center_position(receiving_timber, receiving_face)
    
    # Calculate distance from the specified butt end to the receiving face
    from kumiki.rule import safe_dot_product
    distance_from_bottom = safe_dot_product(face_center - butt_timber.get_bottom_position_global(), butt_timber.get_length_direction_global())
    distance_from_end = butt_timber.length - distance_from_bottom if butt_end == TimberReferenceEnd.TOP else distance_from_bottom
    
    # Create the end cut HalfSpace
    end_cut_half_space = Cutting.make_end_cut(butt_timber, butt_end, distance_from_end)
    
    # Create the Cut
    cut = Cutting(
        timber=butt_timber,
        maybe_top_end_cut=end_cut_half_space if butt_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=end_cut_half_space if butt_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=None
    )
    
    # Create CutTimber for the butt timber with cut passed at construction
    cut_butt = CutTimber(butt_timber, cuts=[cut])
    
    # Create CutTimber for the receiving timber (no cuts)
    cut_receiving = CutTimber(receiving_timber, cuts=[])
    
    # Create and return the Joint with all data at construction
    joint = Joint(
        cut_timbers={"receiving_timber": cut_receiving, "butt_timber": cut_butt},
        ticket=JointTicket(joint_type="plain_butt"),
        jointAccessories={},
    )
    
    return joint


def cut_tongue_and_fork_corner_joint(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = Rational(0),
) -> Joint:
    """
    Creates a plain tongue-and-fork corner joint (corner bridle style).

    In this joint, timber1 forms the tongue (material removed on both cheeks), and timber2
    forms the fork (slot cut into its end). Tongue thickness is measured along the shared
    plane normal between the two timbers and defaults to one-third of the tongue timber
    dimension in that axis. Tongue position is an offset from the tongue timber centerline
    in that same axis.

    End cuts are aligned to the opposing timber's opposite face:
    - Tongue timber end is cut to the face opposite the fork entry face.
    - Fork timber end is cut to the face opposite the tongue entry face.

    Args:
        arrangement: Corner arrangement where timber1 is the tongue timber and timber2 is
            the fork timber.
        tongue_thickness: Tongue thickness along the shared plane normal. If None, defaults
            to 1/3 of the tongue timber dimension in that axis.
        tongue_position: Offset of the tongue center from the tongue timber centerline along
            the shared plane normal. 0 means centered.

    Returns:
        Joint containing both cut timbers.

    Raises:
        AssertionError: If timbers are not plane aligned, are parallel, or tongue parameters
            are out of bounds.
    """
    from kumiki.cutcsg import RectangularPrism, HalfSpace, Difference, adopt_csg
    from kumiki.rule import safe_dot_product, safe_compare, Comparison

    error = arrangement.check_plane_aligned()
    assert error is None, error

    tongue_timber = arrangement.timber1
    fork_timber = arrangement.timber2
    tongue_end = arrangement.timber1_end
    fork_end = arrangement.timber2_end

    assert not are_vectors_parallel(
        tongue_timber.get_length_direction_global(),
        fork_timber.get_length_direction_global(),
    ), "Timbers cannot be parallel for a tongue-and-fork corner joint"

    # -------------------------------------------------------------------------
    # Tongue geometry: shared plane normal, thickness, width
    # -------------------------------------------------------------------------
    shared_plane_normal_hint = arrangement.compute_normalized_timber_cross_product()
    tongue_normal_face = tongue_timber.get_closest_oriented_long_face_from_global_direction(shared_plane_normal_hint)
    tongue_normal_direction = tongue_timber.get_face_direction_global(tongue_normal_face)

    tongue_normal_dimension = tongue_timber.get_size_in_face_normal_axis(tongue_normal_face)
    if tongue_thickness is None:
        tongue_thickness = tongue_normal_dimension / Rational(3)

    assert safe_compare(tongue_thickness, 0, Comparison.GT), "tongue_thickness must be greater than 0"
    assert safe_compare(tongue_normal_dimension - tongue_thickness, 0, Comparison.GE), \
        "tongue_thickness must be <= the tongue timber size in the shared plane normal axis"

    half_tongue_dimension = tongue_normal_dimension / Rational(2)
    half_tongue_thickness = tongue_thickness / Rational(2)
    assert safe_compare(half_tongue_dimension - (Abs(tongue_position) + half_tongue_thickness), 0, Comparison.GE), \
        "tongue_position and tongue_thickness place the tongue outside the tongue timber boundary"

    tongue_normal_axis_index = tongue_timber.get_size_index_in_long_face_normal_axis(tongue_normal_face)
    tongue_width_axis_index = 1 if tongue_normal_axis_index == 0 else 0
    tongue_width = tongue_timber.size[tongue_width_axis_index]

    tongue_end_direction = tongue_timber.get_face_direction_global(tongue_end)
    fork_end_direction = fork_timber.get_face_direction_global(fork_end)

    # -------------------------------------------------------------------------
    # Shoulder plane (M&T pattern): compute on fork timber, mark onto tongue
    # -------------------------------------------------------------------------
    butt_arrangement_for_shoulder = ButtJointTimberArrangement(
        receiving_timber=fork_timber,
        butt_timber=tongue_timber,
        butt_timber_end=tongue_end,
    )
    # Push the shoulder plane from the fork's centerline to its entry face
    fork_entry_long_face = fork_timber.get_closest_oriented_long_face_from_global_direction(-tongue_end_direction)
    fork_shoulder_distance = fork_timber.get_size_in_face_normal_axis(fork_entry_long_face) / Rational(2)

    shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
        butt_arrangement_for_shoulder, fork_shoulder_distance
    )
    shoulder_from_tongue_end_mark = mark_distance_from_end_along_centerline(
        shoulder_plane, tongue_timber, tongue_end
    )
    shoulder_point_global = shoulder_from_tongue_end_mark.locate().position

    # -------------------------------------------------------------------------
    # Marking space at shoulder (M&T pattern)
    # -------------------------------------------------------------------------
    marking_origin_global = shoulder_point_global + tongue_normal_direction * tongue_position

    tongue_orientation_global = Orientation.from_z_and_y(
        z_direction=normalize_vector(tongue_end_direction),
        y_direction=normalize_vector(tongue_normal_direction),
    )
    marking_space_transform = Transform(position=marking_origin_global, orientation=tongue_orientation_global)
    marking_space = Space(transform=marking_space_transform)

    # -------------------------------------------------------------------------
    # Tongue prism and shoulder half-space (M&T pattern)
    # -------------------------------------------------------------------------
    tongue_back_extension = max(tongue_timber.size[0], tongue_timber.size[1])
    tongue_prism_global = RectangularPrism(
        size=create_v2(tongue_width, tongue_thickness),
        transform=marking_space.transform,
        start_distance=-tongue_back_extension,
        end_distance=tongue_timber.length,
    )

    # Shoulder half-space: normal = -shoulder_plane.normal (points from fork toward tongue end)
    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
    )

    tongue_prism_local = adopt_csg(None, tongue_timber.transform, tongue_prism_global)
    shoulder_half_space_local = adopt_csg(None, tongue_timber.transform, shoulder_half_space_global)

    tongue_negative_csg = Difference(
        base=shoulder_half_space_local,
        subtract=[tongue_prism_local],
    )

    # -------------------------------------------------------------------------
    # Fork slot: depth extends to the fork's far face so the slot matches
    # the tongue after its end-cut extension (same orientation as tongue)
    # -------------------------------------------------------------------------
    fork_entry_long_face_for_end_cut = fork_timber.get_closest_oriented_long_face_from_global_direction(-tongue_end_direction)
    fork_far_face = fork_entry_long_face_for_end_cut.to.face().get_opposite_face()
    fork_far_face_normal_global = fork_timber.get_face_direction_global(fork_far_face)
    fork_far_face_point_global = get_point_on_face_global(fork_far_face, fork_timber)

    # Slot depth = distance from shoulder to fork far face along tongue direction
    fork_slot_depth = safe_dot_product(
        fork_far_face_point_global - shoulder_point_global,
        normalize_vector(tongue_end_direction),
    )
    assert safe_compare(fork_slot_depth, 0, Comparison.GT), \
        "Fork slot depth must be > 0; check timber arrangement and end selections"

    # Fork slot uses the same orientation as the tongue prism so the slot
    # receives the tongue correctly at any joint angle
    fork_slot_back_extension = max(fork_timber.size[0], fork_timber.size[1]) * Rational(2)
    fork_slot_prism_global = RectangularPrism(
        size=create_v2(tongue_width, tongue_thickness),
        transform=marking_space.transform,
        start_distance=-fork_slot_back_extension,
        end_distance=fork_slot_depth,
    )
    fork_negative_csg = adopt_csg(None, fork_timber.transform, fork_slot_prism_global)

    # -------------------------------------------------------------------------
    # End cuts: each timber is cut to align with the far face of the
    # opposing timber (the face opposite the entry face).  The cut planes
    # use the actual face orientation of the opposing timber so they are
    # correct at any joint angle.
    # -------------------------------------------------------------------------

    # Tongue end cut — aligns with the fork face opposite the entry face
    # (fork_far_face already computed above for slot depth)

    # HalfSpace normal points in the tongue end direction (away from the tongue body)
    tongue_end_hs_normal_global = (
        fork_far_face_normal_global
        if safe_dot_product(fork_far_face_normal_global, tongue_end_direction) > 0
        else -fork_far_face_normal_global
    )
    # Convert to tongue timber local coordinates
    from kumiki.rule import safe_transform_vector
    tongue_end_cut_local_normal = safe_transform_vector(
        tongue_timber.orientation.matrix.T, tongue_end_hs_normal_global
    )
    tongue_end_cut_local_offset = (
        safe_dot_product(tongue_end_hs_normal_global, fork_far_face_point_global)
        - safe_dot_product(tongue_end_hs_normal_global, tongue_timber.get_bottom_position_global())
    )
    tongue_end_cut = HalfSpace(normal=tongue_end_cut_local_normal, offset=tongue_end_cut_local_offset)

    # Fork end cut — aligns with the tongue face opposite the entry face
    tongue_entry_long_face = tongue_timber.get_closest_oriented_long_face_from_global_direction(-fork_end_direction)
    tongue_far_face = tongue_entry_long_face.to.face().get_opposite_face()
    tongue_far_face_normal_global = tongue_timber.get_face_direction_global(tongue_far_face)
    tongue_far_face_point_global = get_point_on_face_global(tongue_far_face, tongue_timber)

    fork_end_hs_normal_global = (
        tongue_far_face_normal_global
        if safe_dot_product(tongue_far_face_normal_global, fork_end_direction) > 0
        else -tongue_far_face_normal_global
    )
    fork_end_cut_local_normal = safe_transform_vector(
        fork_timber.orientation.matrix.T, fork_end_hs_normal_global
    )
    fork_end_cut_local_offset = (
        safe_dot_product(fork_end_hs_normal_global, tongue_far_face_point_global)
        - safe_dot_product(fork_end_hs_normal_global, fork_timber.get_bottom_position_global())
    )
    fork_end_cut = HalfSpace(normal=fork_end_cut_local_normal, offset=fork_end_cut_local_offset)

    # -------------------------------------------------------------------------
    # Assemble cuts and joint
    # -------------------------------------------------------------------------
    tongue_cut = Cutting(
        timber=tongue_timber,
        maybe_top_end_cut=tongue_end_cut if tongue_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=tongue_end_cut if tongue_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=tongue_negative_csg,
    )

    fork_cut = Cutting(
        timber=fork_timber,
        maybe_top_end_cut=fork_end_cut if fork_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=fork_end_cut if fork_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=fork_negative_csg,
    )

    return Joint(
        cut_timbers={
            "tongue_timber": CutTimber(tongue_timber, cuts=[tongue_cut]),
            "fork_timber": CutTimber(fork_timber, cuts=[fork_cut]),
        },
        ticket=JointTicket(joint_type="tongue_and_fork_corner"),
        jointAccessories={},
    )


def cut_plain_tongue_and_fork_joint(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = Rational(0),
) -> Joint:
    """Compatibility alias for `cut_tongue_and_fork_corner_joint`."""
    return cut_tongue_and_fork_corner_joint(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
    )


def cut_tongue_and_fork_butt_joint(
    arrangement: ButtJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = Rational(0),
) -> Joint:
    """
    Creates a plain tongue-and-fork butt joint.

    Like the corner variant, the butt timber forms the tongue (cheeks removed)
    and the receiving timber forms the fork (slot cut into it). The difference
    is that the receiving (fork) timber does **not** receive an end cut — it
    continues through the joint.

    Args:
        arrangement: Butt arrangement where butt_timber is the tongue and
            receiving_timber is the fork.
        tongue_thickness: Tongue thickness along the shared plane normal.
            If None, defaults to 1/3 of the tongue timber dimension in that axis.
        tongue_position: Offset of the tongue center from the tongue timber
            centerline along the shared plane normal. 0 means centered.

    Returns:
        Joint containing both cut timbers.

    Raises:
        AssertionError: If timbers are not plane aligned, are parallel, or
            tongue parameters are out of bounds.
    """
    from kumiki.cutcsg import RectangularPrism, HalfSpace, Difference, adopt_csg
    from kumiki.rule import safe_dot_product, safe_compare, Comparison

    error = arrangement.check_plane_aligned()
    assert error is None, error

    tongue_timber = arrangement.butt_timber
    fork_timber = arrangement.receiving_timber
    tongue_end = arrangement.butt_timber_end

    assert not are_vectors_parallel(
        tongue_timber.get_length_direction_global(),
        fork_timber.get_length_direction_global(),
    ), "Timbers cannot be parallel for a tongue-and-fork butt joint"

    # -------------------------------------------------------------------------
    # Tongue geometry: shared plane normal, thickness, width
    # -------------------------------------------------------------------------
    shared_plane_normal_hint = arrangement.compute_normalized_timber_cross_product()
    tongue_normal_face = tongue_timber.get_closest_oriented_long_face_from_global_direction(shared_plane_normal_hint)
    tongue_normal_direction = tongue_timber.get_face_direction_global(tongue_normal_face)

    tongue_normal_dimension = tongue_timber.get_size_in_face_normal_axis(tongue_normal_face)
    if tongue_thickness is None:
        tongue_thickness = tongue_normal_dimension / Rational(3)

    assert safe_compare(tongue_thickness, 0, Comparison.GT), "tongue_thickness must be greater than 0"
    assert safe_compare(tongue_normal_dimension - tongue_thickness, 0, Comparison.GE), \
        "tongue_thickness must be <= the tongue timber size in the shared plane normal axis"

    half_tongue_dimension = tongue_normal_dimension / Rational(2)
    half_tongue_thickness = tongue_thickness / Rational(2)
    assert safe_compare(half_tongue_dimension - (Abs(tongue_position) + half_tongue_thickness), 0, Comparison.GE), \
        "tongue_position and tongue_thickness place the tongue outside the tongue timber boundary"

    tongue_normal_axis_index = tongue_timber.get_size_index_in_long_face_normal_axis(tongue_normal_face)
    tongue_width_axis_index = 1 if tongue_normal_axis_index == 0 else 0
    tongue_width = tongue_timber.size[tongue_width_axis_index]

    tongue_end_direction = tongue_timber.get_face_direction_global(tongue_end)

    # -------------------------------------------------------------------------
    # Shoulder plane (M&T pattern): compute on fork timber, mark onto tongue
    # -------------------------------------------------------------------------
    butt_arrangement_for_shoulder = ButtJointTimberArrangement(
        receiving_timber=fork_timber,
        butt_timber=tongue_timber,
        butt_timber_end=tongue_end,
    )
    fork_entry_long_face = fork_timber.get_closest_oriented_long_face_from_global_direction(-tongue_end_direction)
    fork_shoulder_distance = fork_timber.get_size_in_face_normal_axis(fork_entry_long_face) / Rational(2)

    shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
        butt_arrangement_for_shoulder, fork_shoulder_distance
    )
    shoulder_from_tongue_end_mark = mark_distance_from_end_along_centerline(
        shoulder_plane, tongue_timber, tongue_end
    )
    shoulder_point_global = shoulder_from_tongue_end_mark.locate().position

    # -------------------------------------------------------------------------
    # Marking space at shoulder (M&T pattern)
    # -------------------------------------------------------------------------
    marking_origin_global = shoulder_point_global + tongue_normal_direction * tongue_position

    tongue_orientation_global = Orientation.from_z_and_y(
        z_direction=normalize_vector(tongue_end_direction),
        y_direction=normalize_vector(tongue_normal_direction),
    )
    marking_space_transform = Transform(position=marking_origin_global, orientation=tongue_orientation_global)
    marking_space = Space(transform=marking_space_transform)

    # -------------------------------------------------------------------------
    # Tongue prism and shoulder half-space (M&T pattern)
    # -------------------------------------------------------------------------
    tongue_back_extension = max(tongue_timber.size[0], tongue_timber.size[1])
    tongue_prism_global = RectangularPrism(
        size=create_v2(tongue_width, tongue_thickness),
        transform=marking_space.transform,
        start_distance=-tongue_back_extension,
        end_distance=tongue_timber.length,
    )

    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
    )

    tongue_prism_local = adopt_csg(None, tongue_timber.transform, tongue_prism_global)
    shoulder_half_space_local = adopt_csg(None, tongue_timber.transform, shoulder_half_space_global)

    tongue_negative_csg = Difference(
        base=shoulder_half_space_local,
        subtract=[tongue_prism_local],
    )

    # -------------------------------------------------------------------------
    # Fork slot: extends through the full fork timber depth.
    # Unlike the corner variant (where the fork timber is end-cut), here
    # the fork is not end-cut, so the slot must extend far enough to
    # accommodate the tongue after its angled end cut.  We over-extend
    # by the fork timber's max cross-section to guarantee coverage at
    # any joint angle — the extra length is harmlessly outside the timber.
    # -------------------------------------------------------------------------
    fork_entry_long_face_for_end_cut = fork_timber.get_closest_oriented_long_face_from_global_direction(-tongue_end_direction)
    fork_far_face = fork_entry_long_face_for_end_cut.to.face().get_opposite_face()
    fork_far_face_normal_global = fork_timber.get_face_direction_global(fork_far_face)
    fork_far_face_point_global = get_point_on_face_global(fork_far_face, fork_timber)

    fork_slot_depth = safe_dot_product(
        fork_far_face_point_global - shoulder_point_global,
        normalize_vector(tongue_end_direction),
    )
    assert safe_compare(fork_slot_depth, 0, Comparison.GT), \
        "Fork slot depth must be > 0; check timber arrangement and end selections"

    fork_slot_end_overshoot = max(fork_timber.size[0], fork_timber.size[1])
    fork_slot_back_extension = max(fork_timber.size[0], fork_timber.size[1]) * Rational(2)
    fork_slot_prism_global = RectangularPrism(
        size=create_v2(tongue_width, tongue_thickness),
        transform=marking_space.transform,
        start_distance=-fork_slot_back_extension,
        end_distance=fork_slot_depth + fork_slot_end_overshoot,
    )
    fork_negative_csg = adopt_csg(None, fork_timber.transform, fork_slot_prism_global)

    # -------------------------------------------------------------------------
    # Tongue end cut — aligns with the fork face opposite the entry face
    # (same as corner variant)
    # -------------------------------------------------------------------------
    tongue_end_hs_normal_global = (
        fork_far_face_normal_global
        if safe_dot_product(fork_far_face_normal_global, tongue_end_direction) > 0
        else -fork_far_face_normal_global
    )
    from kumiki.rule import safe_transform_vector
    tongue_end_cut_local_normal = safe_transform_vector(
        tongue_timber.orientation.matrix.T, tongue_end_hs_normal_global
    )
    tongue_end_cut_local_offset = (
        safe_dot_product(tongue_end_hs_normal_global, fork_far_face_point_global)
        - safe_dot_product(tongue_end_hs_normal_global, tongue_timber.get_bottom_position_global())
    )
    tongue_end_cut = HalfSpace(normal=tongue_end_cut_local_normal, offset=tongue_end_cut_local_offset)

    # -------------------------------------------------------------------------
    # No fork end cut — fork timber continues through the joint
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Assemble cuts and joint
    # -------------------------------------------------------------------------
    tongue_cut = Cutting(
        timber=tongue_timber,
        maybe_top_end_cut=tongue_end_cut if tongue_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=tongue_end_cut if tongue_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=tongue_negative_csg,
    )

    fork_cut = Cutting(
        timber=fork_timber,
        maybe_top_end_cut=None,
        maybe_bottom_end_cut=None,
        negative_csg=fork_negative_csg,
    )

    return Joint(
        cut_timbers={
            "tongue_timber": CutTimber(tongue_timber, cuts=[tongue_cut]),
            "fork_timber": CutTimber(fork_timber, cuts=[fork_cut]),
        },
        ticket=JointTicket(joint_type="tongue_and_fork_butt"),
        jointAccessories={},
    )

def cut_plain_butt_splice_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement, splice_point: Optional[V3] = None) -> Joint:
    """
    Creates a plain butt splice joint between two parallel timbers cut at a shared plane.

    Both timbers are cut at the splice plane, creating a flush end-to-end connection.

    Args:
        arrangement: Splice joint arrangement with timber1, timber2, timber1_end, timber2_end.
                     Timbers must have parallel length axes.
        splice_point: Point where the splice occurs. If not provided, the midpoint between
            the two timber ends is used. If provided but off the centerline, it is projected
            onto timber1's centerline.

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        ValueError: If the timbers do not have parallel length axes.
    """
    import warnings
    from kumiki.construction import _are_directions_parallel
    
    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end
    
    # Assert that the length axes are parallel
    if not _are_directions_parallel(timberA.get_length_direction_global(), timberB.get_length_direction_global()):
        raise ValueError("Timbers must have parallel length axes for a splice joint")
    
    # Get the end positions for each timber
    if timberA_end == TimberReferenceEnd.TOP:
        endA_position = locate_top_center_position(timberA).position
        directionA = timberA.get_length_direction_global()
    else:  # BOTTOM
        endA_position = locate_bottom_center_position(timberA).position
        directionA = -timberA.get_length_direction_global()
    
    if timberB_end == TimberReferenceEnd.TOP:
        endB_position = locate_top_center_position(timberB).position
        directionB = timberB.get_length_direction_global()
    else:  # BOTTOM
        endB_position = locate_bottom_center_position(timberB).position
        directionB = -timberB.get_length_direction_global()
    
    # Normalize length direction for later use
    length_dir_norm = normalize_vector(timberA.get_length_direction_global())
    
    # Calculate or validate the splice point
    if splice_point is None:
        # Calculate as the midpoint between the two timber ends
        splice_point = (endA_position + endB_position) / 2
    else:
        # Project the splice point onto timberA's centerline if it's not already on it
        # Vector from timberA's bottom to the splice point
        to_splice = splice_point - timberA.get_bottom_position_global()
        
        # Project onto the centerline
        from kumiki.rule import safe_dot_product
        distance_along_centerline = safe_dot_product(to_splice, length_dir_norm)
        projected_point = timberA.get_bottom_position_global() + length_dir_norm * distance_along_centerline
        
        # Check if the point needed projection (warn if not on centerline)
        distance_from_centerline = vector_magnitude(splice_point - projected_point)
        if not zero_test(distance_from_centerline):
            warnings.warn(f"Splice point was not on timberA's centerline (distance: {float(distance_from_centerline)}). Projecting onto centerline.")
            splice_point = projected_point
    
    # Check if timber cross sections overlap (approximate check using bounding boxes)
    # Project both timber cross-sections onto a plane perpendicular to the length direction
    # For simplicity, we'll warn if the centerlines are far apart
    from kumiki.rule import safe_dot_product
    centerline_distance = vector_magnitude(
        (splice_point - timberA.get_bottom_position_global()) - 
        length_dir_norm * safe_dot_product(splice_point - timberA.get_bottom_position_global(), length_dir_norm) -
        ((splice_point - timberB.get_bottom_position_global()) - 
         length_dir_norm * safe_dot_product(splice_point - timberB.get_bottom_position_global(), length_dir_norm))
    )
    
    # Approximate overlap check: centerlines should be close
    max_dimension = max(timberA.size[0], timberA.size[1], timberB.size[0], timberB.size[1])
    from sympy import Rational
    if centerline_distance > max_dimension / Rational(2):
        warnings.warn(f"Timber cross sections may not overlap (centerline distance: {float(centerline_distance)}). Check joint geometry.")
    
    # Calculate distance from each timber end to the splice point
    distance_A_from_bottom = safe_dot_product(splice_point - timberA.get_bottom_position_global(), timberA.get_length_direction_global())
    distance_A_from_end = timberA.length - distance_A_from_bottom if timberA_end == TimberReferenceEnd.TOP else distance_A_from_bottom
    
    distance_B_from_bottom = safe_dot_product(splice_point - timberB.get_bottom_position_global(), timberB.get_length_direction_global())
    distance_B_from_end = timberB.length - distance_B_from_bottom if timberB_end == TimberReferenceEnd.TOP else distance_B_from_bottom
    
    # Create the end cut HalfSpaces
    end_cut_A = Cutting.make_end_cut(timberA, timberA_end, distance_A_from_end)
    end_cut_B = Cutting.make_end_cut(timberB, timberB_end, distance_B_from_end)
    
    # Create the Cuts
    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut=end_cut_A if timberA_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=end_cut_A if timberA_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=None
    )
    
    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut=end_cut_B if timberB_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=end_cut_B if timberB_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=None
    )
    
    # Create CutTimbers with cuts passed at construction
    cut_timberA = CutTimber(timberA, cuts=[cutA])
    cut_timberB = CutTimber(timberB, cuts=[cutB])
    
    # Create and return the Joint with all data at construction
    joint = Joint(
        cut_timbers={"timberA": cut_timberA, "timberB": cut_timberB},
        ticket=JointTicket(joint_type="plain_butt_splice"),
        jointAccessories={},
    )
    
    return joint


def cut_plain_cross_lap_joint(arrangement: CrossJointTimberArrangement, cut_ratio: Numeric = Rational(1, 2)) -> Joint:
    """
    Creates a cross-lap joint between two intersecting timbers.

    Each timber has a notch cut into it so they interlock at their crossing point,
    maintaining a flush outer face on both sides. By default material removal is split
    equally (half from each timber).

    Args:
        arrangement: Cross-joint arrangement with timber1 and timber2, and optional
                     front_face_on_timber1 (the cut face on timber1). If not provided,
                     front_face_on_timber1 is chosen automatically to minimize material removed.
                     The cut face on timber2 is implicitly the opposite face.
        cut_ratio: Fraction [0, 1] controlling how much is removed from each timber.
            0 = only timber2 is cut; 1 = only timber1 is cut; 0.5 = equal split (default).

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        AssertionError: If the timbers don't intersect, are parallel, or cut_ratio is out of range.
    """
    from kumiki.cutcsg import Difference, RectangularPrism, HalfSpace
    from kumiki.rule import safe_dot_product, safe_transform_vector, safe_norm
    from sympy import Rational
    
    timberA = arrangement.timber1
    timberB = arrangement.timber2
    timberA_cut_face = arrangement.front_face_on_timber1
    
    # Verify that cut_ratio is in valid range [0, 1]
    assert 0 <= cut_ratio <= 1, f"cut_ratio must be in range [0, 1], got {cut_ratio}"
    
    # Verify that the timbers are not parallel (their length directions must differ)
    dot_product = safe_dot_product(timberA.get_length_direction_global(), timberB.get_length_direction_global())
    assert abs(abs(dot_product) - 1) > Rational(1, 1000000), \
        "Timbers must not be parallel (their length directions must differ)"
    
    # Check that the timbers intersect when extended infinitely
    # Calculate closest points between two lines in 3D
    d1 = timberA.get_length_direction_global()
    d2 = timberB.get_length_direction_global()
    p1 = timberA.get_bottom_position_global()
    p2 = timberB.get_bottom_position_global()
    w = p1 - p2
    
    a = safe_dot_product(d1, d1)
    b = safe_dot_product(d1, d2)
    c = safe_dot_product(d2, d2)
    d = safe_dot_product(d1, w)
    e = safe_dot_product(d2, w)
    
    denom = a * c - b * b
    
    if abs(denom) < Rational(1, 1000000):
        # Lines are parallel (already checked above)
        t = -safe_dot_product(d1, w) / a if a > 0 else 0
        closest_on_1 = p1 + t * d1
        distance = safe_norm(p2 - closest_on_1)
    else:
        t1 = (b * e - c * d) / denom
        t2 = (a * e - b * d) / denom
        
        closest_on_1 = p1 + t1 * d1
        closest_on_2 = p2 + t2 * d2
        
        distance = safe_norm(closest_on_1 - closest_on_2)
    
    # Check if timbers are close enough to intersect
    max_separation = (timberA.size[0] + timberA.size[1] + 
                     timberB.size[0] + timberB.size[1]) / 2
    
    assert float(distance) < float(max_separation), \
        f"Timbers do not intersect (closest distance: {float(distance):.4f}m, max allowed: {float(max_separation):.4f}m)"
    

    # Auto-select cut faces if not provided
    # Find the axis perpendicular to the length axis of both timbers
    # Choose the face on that axis on timberA that's closest to timberB
    # Then pick the opposite face on timberB
    if timberA_cut_face is None:
        from kumiki.rule import cross_product, safe_normalize_vector as normalize_vector, safe_norm
        
        # Get length directions of both timbers
        d1 = timberA.get_length_direction_global()
        d2 = timberB.get_length_direction_global()
        
        # Find axis perpendicular to both length directions (cross product)
        perpendicular_axis = cross_product(d1, d2)
        perpendicular_axis = normalize_vector(perpendicular_axis)
        
        # Get center positions of both timbers
        from sympy import Rational
        centerA = timberA.get_bottom_position_global() + timberA.get_length_direction_global() * (timberA.length / Rational(2))
        centerB = timberB.get_bottom_position_global() + timberB.get_length_direction_global() * (timberB.length / Rational(2))
        
        # Vector from timberA center to timberB center
        A_to_B = centerB - centerA
        
        # Project A_to_B onto the perpendicular axis to get direction
        projection = safe_dot_product(A_to_B, perpendicular_axis)
        
        # Direction along perpendicular axis (toward timberB from timberA)
        direction_toward_B = perpendicular_axis if projection >= 0 else -perpendicular_axis
        
        # Find face on timberA whose normal is closest to direction_toward_B
        faces = [TimberFace.RIGHT, TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK]
        max_dot = None
        best_face = TimberFace.RIGHT  # Default
        
        for face in faces:
            face_normal = timberA.get_face_direction_global(face)
            dot = safe_dot_product(face_normal, direction_toward_B)
            
            if max_dot is None or dot > max_dot:
                max_dot = dot
                best_face = face
        
        timberA_cut_face = best_face
    
    # timberB_cut_face is computed as the opposite of timberA_cut_face
    normalA = timberA.get_face_direction_global(timberA_cut_face)
    faces = [TimberFace.RIGHT, TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK]
    min_dot = None
    timberB_cut_face = TimberFace.RIGHT  # Default
    
    for face in faces:
        face_normal = timberB.get_face_direction_global(face)
        dot = safe_dot_product(face_normal, normalA)
        
        # We want the face with the most negative dot product (most opposing)
        if min_dot is None or dot < min_dot:
            min_dot = dot
            timberB_cut_face = face

    # Both cut faces are now set (narrow type for type checker)
    assert timberA_cut_face is not None and timberB_cut_face is not None
    # Get face normals (pointing outward from the timber) in GLOBAL space
    # get_face_direction returns the direction vector in world coordinates
    normalA = timberA.get_face_direction_global(timberA_cut_face)
    normalB = timberB.get_face_direction_global(timberB_cut_face)
    
    # Verify that the face normals oppose each other (point toward each other)
    # For a valid cross lap joint, the normals must strictly oppose (dot product < 0)
    # This ensures the cutting plane can properly separate the two timber volumes
    normal_dot = safe_dot_product(normalA, normalB)
    
    # The faces must be opposing (normals pointing toward each other)
    # Perpendicular faces (dot product = 0) are NOT valid for cross lap joints
    assert normal_dot < 0, \
        f"Face normals must oppose each other (dot product < 0, got {float(normal_dot):.4f})"
    
    # Create the cutting plane by lerping between the two faces
    # Get the position of each face (center point on the face)
    # Calculate face center positions
    faceA_position = _get_face_center_position(timberA, timberA_cut_face)
    faceB_position = _get_face_center_position(timberB, timberB_cut_face)
    
    # The cutting plane position is interpolated based on cut_ratio
    # cut_ratio = 0: plane at faceA (timberB is cut entirely)
    # cut_ratio = 0.5: plane halfway between faces
    # cut_ratio = 1: plane at faceB (timberA is cut entirely)
    cutting_plane_position = faceA_position * (1 - cut_ratio) + faceB_position * cut_ratio
    
    # The cutting plane normal should be interpolated between the two face normals
    # cut_ratio = 0: normal is normalA (pointing from faceA)
    # cut_ratio = 1: normal is -normalB (pointing toward faceB from the opposite direction)
    # Since normalA and normalB oppose each other (normalA · normalB < 0), we interpolate:
    cutting_plane_normal = normalA * (1 - cut_ratio) - normalB * cut_ratio
    cutting_plane_normal_normalized = cutting_plane_normal / safe_norm(cutting_plane_normal)
    
    # Calculate the offset for the cutting plane
    # offset = normal · point_on_plane
    cutting_plane_offset = safe_dot_product(cutting_plane_normal_normalized, cutting_plane_position)
    
    # Create cuts for both timbers
    cuts_A = []
    cuts_B = []
    
    # TimberA: Cut by (timberB prism) intersected with (region on the timberB side of cutting plane)
    # The HalfSpace keeps points where normal·P >= offset
    # We want to keep the region on the timberB side (positive normal direction from A)
    # So we use the cutting plane as-is
    
    if safe_compare(cut_ratio, 0, Comparison.GT):  # Only cut timberA if cut_ratio > 0
        # Transform timberB prism to timberA's local coordinates
        relative_orientation_B_in_A = Orientation(safe_transform_vector(timberA.orientation.matrix.T, timberB.orientation.matrix))
        timberB_origin_in_A_local = safe_transform_vector(timberA.orientation.matrix.T, timberB.get_bottom_position_global() - timberA.get_bottom_position_global())
        
        # Create timberB prism in timberA's local coordinates (infinite extent)
        transform_B_in_A = Transform(position=timberB_origin_in_A_local, orientation=relative_orientation_B_in_A)
        timberB_prism_in_A = RectangularPrism(
            size=timberB.size,
            transform=transform_B_in_A,
            start_distance=None,  # Infinite
            end_distance=None     # Infinite
        )
        
        # Transform cutting plane to timberA's local coordinates
        cutting_plane_normal_in_A = safe_transform_vector(timberA.orientation.matrix.T, cutting_plane_normal_normalized)
        cutting_plane_position_in_A = safe_transform_vector(timberA.orientation.matrix.T, cutting_plane_position - timberA.get_bottom_position_global())
        cutting_plane_offset_in_A = safe_dot_product(cutting_plane_normal_in_A, cutting_plane_position_in_A)
        
        # Create HalfSpace that keeps the region on the positive side of the plane
        # (toward timberB from the cutting plane)
        half_plane_A = HalfSpace(
            normal=cutting_plane_normal_in_A,
            offset=cutting_plane_offset_in_A
        )
        
        # TimberA is cut by: (timberB prism) intersected with half_plane
        # This means: Difference(timberA, Difference(timberB_prism, half_plane))
        # Which simplifies to: Difference(timberA, timberB_prism ∩ half_plane_positive_region)
        # The CSG for this is: subtract (timberB_prism AND above_cutting_plane)
        # Which is: subtract Difference(timberB_prism, NOT(half_plane))
        # Since HalfSpace keeps >= side, we want to subtract the >= side
        # So: negative_csg = Difference(timberB_prism, half_plane) keeps the < side
        # Actually, we want to subtract: timberB_prism ∩ (normal·P >= offset region)
        # 
        # Let me think again: we want to remove from timberA the intersection of timberB_prism 
        # with the region on the timberB side of cutting plane.
        # The cutting plane normal points from A to B.
        # HalfSpace(normal, offset) keeps points where normal·P >= offset (positive side)
        # So we want to subtract: Difference(timberB_prism, NOT(half_plane))
        # Which is the same as: (timberB_prism) with everything on the negative side removed
        # That's just: subtract Difference(timberB_prism, inverse_half_plane)
        
        # Actually, simpler: subtract (timberB_prism ∩ positive_half_space)
        # In CSG: we can't directly intersect with HalfSpace
        # But Difference(A, B) - Difference(A, C) = A ∩ C if B contains C...
        # 
        # Even simpler approach: use two cuts
        # Cut 1: Subtract timberB prism
        # Cut 2: Add back the negative side using inverse half plane
        # Actually that's complicated too.
        #
        # Cleanest approach: Just use Difference(timberB_prism, inverse_halfspace)
        # inverse_halfspace keeps points where normal·P < offset
        # Which is HalfSpace(-normal, -offset) keeps points where -normal·P >= -offset, i.e., normal·P <= offset
        
        inverse_half_plane_A = HalfSpace(
            normal=-cutting_plane_normal_in_A,
            offset=-cutting_plane_offset_in_A
        )
        
        # Subtract the portion of timberB that's on the positive side of cutting plane
        negative_csg_A = Difference(
            base=timberB_prism_in_A,
            subtract=[inverse_half_plane_A]  # Remove the negative side, keeping positive side
        )
        
        cut_A = Cutting(
            timber=timberA,
            maybe_top_end_cut=None,
            maybe_bottom_end_cut=None,
            negative_csg=negative_csg_A
        )
        cuts_A.append(cut_A)
    
    # TimberB: Cut by (timberA prism) intersected with (region on the timberA side of cutting plane)
    if cut_ratio < 1:  # Only cut timberB if cut_ratio < 1
        # Transform timberA prism to timberB's local coordinates
        relative_orientation_A_in_B = Orientation(safe_transform_vector(timberB.orientation.matrix.T, timberA.orientation.matrix))
        timberA_origin_in_B_local = safe_transform_vector(timberB.orientation.matrix.T, timberA.get_bottom_position_global() - timberB.get_bottom_position_global())
        
        # Create timberA prism in timberB's local coordinates (infinite extent)
        transform_A_in_B = Transform(position=timberA_origin_in_B_local, orientation=relative_orientation_A_in_B)
        timberA_prism_in_B = RectangularPrism(
            size=timberA.size,
            transform=transform_A_in_B,
            start_distance=None,  # Infinite
            end_distance=None     # Infinite
        )
        
        # Transform cutting plane to timberB's local coordinates
        cutting_plane_normal_in_B = safe_transform_vector(timberB.orientation.matrix.T, cutting_plane_normal_normalized)
        cutting_plane_position_in_B = safe_transform_vector(timberB.orientation.matrix.T, cutting_plane_position - timberB.get_bottom_position_global())
        cutting_plane_offset_in_B = safe_dot_product(cutting_plane_normal_in_B, cutting_plane_position_in_B)
        
        # For timberB, we want to subtract the region on the negative side (timberA side) of the plane
        # So we use the inverse half plane (keeps normal·P <= offset, the negative side)
        half_plane_B = HalfSpace(
            normal=cutting_plane_normal_in_B,
            offset=cutting_plane_offset_in_B
        )
        
        # Subtract the portion of timberA that's on the negative side of cutting plane
        negative_csg_B = Difference(
            base=timberA_prism_in_B,
            subtract=[half_plane_B]  # Remove the positive side, keeping negative side
        )
        
        cut_B = Cutting(
            timber=timberB,
            maybe_top_end_cut=None,
            maybe_bottom_end_cut=None,
            negative_csg=negative_csg_B
        )
        cuts_B.append(cut_B)
    
    # Create CutTimbers
    cut_timberA = CutTimber(timberA, cuts=cuts_A)
    cut_timberB = CutTimber(timberB, cuts=cuts_B)
    
    # Create and return the Joint
    joint = Joint(
        cut_timbers={"timberA": cut_timberA, "timberB": cut_timberB},
        ticket=JointTicket(joint_type="plain_cross_lap"),
        jointAccessories={},
    )
    
    return joint


def _get_face_center_position(timber: PerfectTimberWithin, face: SomeTimberFace) -> V3:
    """
    Helper function to calculate the center position of a timber face.
    
    Args:
        timber: The timber object
        face: The face to get the center position for
        
    Returns:
        3D position vector at the center of the specified face
    """
    face = face.to.face()

    if face == TimberFace.TOP:
        return locate_top_center_position(timber).position
    elif face == TimberFace.BOTTOM:
        return locate_bottom_center_position(timber).position
    else:
        # For long faces (LEFT, RIGHT, FRONT, BACK), center is at mid-length
        from sympy import Rational
        face_center = timber.get_bottom_position_global() + (timber.length / Rational(2)) * timber.get_length_direction_global()
        
        # Offset to the face surface
        if face == TimberFace.RIGHT:
            face_center = face_center + (timber.size[0] / Rational(2)) * timber.get_width_direction_global()
        elif face == TimberFace.LEFT:
            face_center = face_center - (timber.size[0] / Rational(2)) * timber.get_width_direction_global()
        elif face == TimberFace.FRONT:
            face_center = face_center + (timber.size[1] / Rational(2)) * timber.get_height_direction_global()
        else:  # BACK
            face_center = face_center - (timber.size[1] / Rational(2)) * timber.get_height_direction_global()
        
        return face_center


def _find_closest_face_to_timber(timber: PerfectTimberWithin, other_timber: PerfectTimberWithin) -> TimberFace:
    """
    Helper function to find which face of timber is closest to other_timber's centerline.
    Returns the face that minimizes material removal for a cross lap joint.
    Uses the 4 side faces (not the end faces TOP/BOTTOM).
    """
    # Get the centerline point of other_timber (midpoint)
    from sympy import Rational
    other_center = other_timber.get_bottom_position_global() + other_timber.get_length_direction_global() * (other_timber.length / Rational(2))
    
    # Check distance from each side face to the other timber's center
    # Don't include TOP/BOTTOM as those are the end faces
    faces = [TimberFace.RIGHT, TimberFace.LEFT, 
             TimberFace.FRONT, TimberFace.BACK]
    
    min_distance = None
    closest_face = TimberFace.RIGHT  # Default
    
    for face in faces:
        face_center = _get_face_center_position(timber, face)
        distance = safe_norm(face_center - other_center)
        
        if min_distance is None or distance < min_distance:
            min_distance = distance
            closest_face = face
    
    return closest_face


def cut_plain_house_joint(arrangement: CrossJointTimberArrangement) -> Joint:
    """
    Creates a house (dado/housing) joint where the housing timber is notched to receive the housed timber.

    Only the housing timber is cut (timber1); the housed timber (timber2) is not modified.
    Implemented as a cross-lap joint with cut_ratio=1.

    Args:
        arrangement: Cross-joint arrangement where timber1 is the housing timber (to be notched)
                     and timber2 is the housed timber (remains uncut). front_face_on_timber1
                     specifies the notch face; if None, chosen automatically.

    Returns:
        Joint object containing both timbers.

    Raises:
        AssertionError: If the timbers don't intersect or are parallel.
    """
    # Use cross lap joint with cut_ratio=1 (only cut timber1, not timber2)
    return cut_plain_cross_lap_joint(arrangement, cut_ratio=Rational(1, 1))


# TODO DELETE
def cut_plain_house_joint_DEPRECATED(housing_timber: TimberLike, housed_timber: TimberLike, extend_housed_timber_to_infinity: bool = False) -> Joint:
    """
    DEPRECATED: Use cut_plain_house_joint() instead.
    
    Creates a plain housed joint (also called housing joint or dado joint) where the 
    housing_timber is notched to fit the housed_timber. The housed timber fits completely
    into a notch cut in the housing timber.
    
    Args:
        housing_timber: Timber that will receive the housing cut (gets the groove)
        housed_timber: Timber that will be housed (fits into the groove, remains uncut)
        extend_housed_timber_to_infinity: If True, the housed timber is extended to infinity in both directions, otherwise the finite timber is used
        
    Returns:
        Joint object containing both timbers
        
    Raises:
        AssertionError: If timbers don't intersect or are parallel
        
    Example:
        A shelf (housed_timber) fitting into the side of a cabinet (housing_timber).
        The cabinet side gets a groove cut into it to receive the shelf.
    """
    from kumiki.cutcsg import Difference, RectangularPrism
    
    # Verify that the timbers are not parallel (their length directions must differ)
    from kumiki.rule import safe_dot_product
    dot_product = safe_dot_product(housing_timber.get_length_direction_global(), housed_timber.get_length_direction_global())
    assert abs(abs(dot_product) - 1) > Rational(1, 1000000), \
        "Timbers must not be parallel (their length directions must differ)"
    
    # Check that the timbers intersect when extended infinitely
    # For two lines to intersect, they must either:
    # 1. Actually intersect at a point, or
    # 2. Be skew lines that would intersect if one were translated
    # For housed joints, we require that they actually overlap in 3D space
    
    # A simple check: compute the closest points between the two timber centerlines
    # If the distance is less than the sum of half their cross-sections, they overlap
    
    # Direction vectors
    d1 = housing_timber.get_length_direction_global()
    d2 = housed_timber.get_length_direction_global()
    
    # Points on each line (use bottom positions)
    p1 = housing_timber.get_bottom_position_global()
    p2 = housed_timber.get_bottom_position_global()
    
    # Vector between the two line points
    w = p1 - p2
    
    # Calculate closest points between two lines in 3D
    # See: http://paulbourke.net/geometry/pointlineplane/
    a = safe_dot_product(d1, d1)
    b = safe_dot_product(d1, d2)
    c = safe_dot_product(d2, d2)
    d = safe_dot_product(d1, w)
    e = safe_dot_product(d2, w)
    
    denom = a * c - b * b
    
    # If denom is very small, lines are parallel (already checked above)
    # Calculate parameters for closest points
    if abs(denom) < Rational(1, 1000000):
        # Lines are parallel, use simple distance check
        # Project p2 onto the line defined by p1 and d1
        t = -safe_dot_product(d1, w) / a if a > Integer(0) else Integer(0)
        closest_on_1 = p1 + t * d1
        distance = safe_norm(p2 - closest_on_1)
    else:
        t1 = (b * e - c * d) / denom
        t2 = (a * e - b * d) / denom
        
        closest_on_1 = p1 + t1 * d1
        closest_on_2 = p2 + t2 * d2
        
        distance = safe_norm(closest_on_1 - closest_on_2)
    
    # Check if timbers are close enough to intersect
    # They should intersect if the closest distance is less than the sum of half their cross-sections
    max_separation = (housing_timber.size[0] + housing_timber.size[1] + 
                     housed_timber.size[0] + housed_timber.size[1]) / 2
    
    assert float(distance) < float(max_separation), \
        f"Timbers do not intersect (closest distance: {float(distance):.4f}m, max allowed: {float(max_separation):.4f}m)"
    
    # Create a CSG difference: housing_timber - housed_timber
    # The housed timber's prism will be subtracted from the housing timber
    
    # Calculate the relative transformation
    # housed_prism in housing_timber's local frame = housing_orientation^T * housed_orientation
    from kumiki.rule import safe_transform_vector
    relative_orientation = Orientation(safe_transform_vector(housing_timber.orientation.matrix.T, housed_timber.orientation.matrix))
    
    # Transform the housed timber's position to housing timber's local coordinates
    housed_origin_local = safe_transform_vector(housing_timber.orientation.matrix.T, housed_timber.get_bottom_position_global() - housing_timber.get_bottom_position_global())
    
    # Determine start and end distances based on extend_housed_timber_to_infinity
    if extend_housed_timber_to_infinity:
        # Use infinite prism to ensure it cuts through the housing timber completely
        start_distance = None
        end_distance = None
    else:
        # Use finite timber dimensions
        # The prism's position and orientation already place it in the housing timber's local space
        # So we just need the housed timber's own start (0) and end (length) distances
        start_distance = Integer(0)
        end_distance = housed_timber.length
    
    # Create the housed prism in housing timber's LOCAL coordinate system
    housed_transform_local = Transform(position=housed_origin_local, orientation=relative_orientation)
    housed_prism_local = RectangularPrism(
        size=housed_timber.size,
        transform=housed_transform_local,
        start_distance=start_distance,
        end_distance=end_distance
    )
    
    # Create the CSG cut for the housing timber
    cut = Cutting(
        timber=housing_timber,
        maybe_top_end_cut=None,
        maybe_bottom_end_cut=None,
        negative_csg=housed_prism_local  # Subtract the housed timber's volume
    )
    
    # Create CutTimber for the housing timber (with cut)
    cut_housing = CutTimber(housing_timber, cuts=[cut])
    
    # Create CutTimber for the housed timber (no cuts)
    cut_housed = CutTimber(housed_timber, cuts=[])
    
    # Create and return the Joint
    joint = Joint(
        cut_timbers={"housing_timber": cut_housing, "housed_timber": cut_housed},
        ticket=JointTicket(joint_type="plain_housing"),
        jointAccessories={},
    )
    
    return joint

def cut_plain_splice_lap_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
    lap_length: Numeric,
    top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Numeric,
    lap_depth: Optional[Numeric] = None
) -> Joint:
    """
    Creates a splice lap joint between two parallel timber ends with interlocking notches.

    One timber has material removed from the specified face; the other has material
    removed from the opposite face. Timbers must be parallel and face-aligned.
    
        arrangement.front_face_on_timber1
        v           |--------| lap_length
    ╔════════════════════════╗╔══════╗  -
    ║timber1                 ║║      ║  | lap_depth
    ║               ╔════════╝║      ║  -
    ║               ║╔════════╝      ║ 
    ║               ║║ timber2       ║ 
    ╚═══════════════╝╚═══════════════╝
                    ^ top_lap_shoulder_position_from_top_lap_shoulder_timber_end
    
    Args:
        arrangement: Splice joint arrangement with timber1, timber2, timber1_end, timber2_end,
                     and optionally front_face_on_timber1 (the lap cut face on timber1).
                     If front_face_on_timber1 is None, defaults to FRONT face.
                     Timbers must be parallel and face-aligned.
        lap_length: Length of the lap region along the timber length.
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Distance from the
            timber1 end to the shoulder, measured inward along the timber.
        lap_depth: Depth of material to remove perpendicular to the face. If None,
            defaults to half the timber thickness in the face normal axis.

    Returns:
        Joint object containing the two CutTimbers with lap cuts.
    """
    # Extract arrangement fields
    top_lap_timber = arrangement.timber1
    top_lap_timber_end = arrangement.timber1_end
    bottom_lap_timber = arrangement.timber2
    bottom_lap_timber_end = arrangement.timber2_end
    top_lap_timber_face = arrangement.front_face_on_timber1 if arrangement.front_face_on_timber1 is not None else TimberLongFace.FRONT
    
    from sympy import Rational
    
    # Calculate default lap_depth if not provided
    if lap_depth is None:
        # Use half the thickness in the axis perpendicular to top_lap_timber_face
        if top_lap_timber_face == TimberLongFace.LEFT or top_lap_timber_face == TimberLongFace.RIGHT:
            # Face is on Y-axis, so thickness is in Y direction (height)
            lap_depth = top_lap_timber.size[1] / Rational(2)
        else:  # TOP or BOTTOM
            # Face is on Z-axis (end face), use the smaller of width/height
            lap_depth = min(top_lap_timber.size[0], top_lap_timber.size[1]) / Rational(2)
    
    # Create the CSG cuts using the helper function
    # Returns tuples of (lap_prism, end_cut) for each timber
    (top_lap_prism, top_end_cut), (bottom_lap_prism, bottom_end_cut) = chop_lap_on_timber_ends(
        top_lap_timber=top_lap_timber,
        top_lap_timber_end=top_lap_timber_end,
        bottom_lap_timber=bottom_lap_timber,
        bottom_lap_timber_end=bottom_lap_timber_end,
        top_lap_timber_face=top_lap_timber_face,
        lap_length=lap_length,
        lap_depth=lap_depth,
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end=top_lap_shoulder_position_from_top_lap_shoulder_timber_end
    )

    # Create Cuts for both timbers with separated lap and end cuts
    cut_top = Cutting(
        timber=top_lap_timber,
        maybe_top_end_cut=top_end_cut if top_lap_timber_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=top_end_cut if top_lap_timber_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=top_lap_prism
    )
    
    cut_bottom = Cutting(
        timber=bottom_lap_timber,
        maybe_top_end_cut=bottom_end_cut if bottom_lap_timber_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=bottom_end_cut if bottom_lap_timber_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=bottom_lap_prism
    )
    
    # Create CutTimbers
    cut_top_timber = CutTimber(top_lap_timber, cuts=[cut_top])
    cut_bottom_timber = CutTimber(bottom_lap_timber, cuts=[cut_bottom])
    
    # Create and return the Joint
    joint = Joint(
        cut_timbers={"top_lap_timber": cut_top_timber, "bottom_lap_timber": cut_bottom_timber},
        ticket=JointTicket(joint_type="plain_splice_lap"),
        jointAccessories={},
    )
    
    return joint


