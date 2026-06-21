"""
Kumiki - Corner joint construction functions
Contains miter, tongue-and-fork corner, and corner lap joint implementations.
"""

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *
from .shavings.notching import CrossJointScribeNotchingConfig, chop_scribe_notch_and_apply, warn_if_arrangement_timbers_imperfect
from kumiki.measuring import locate_top_center_position, locate_bottom_center_position, mark_distance_from_end_along_centerline, get_point_on_face_global, Space
from .shavings.build_a_butt import locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber


_raw_safe_dot_product = safe_dot_product
_raw_safe_norm = safe_norm
_raw_safe_transform_vector = safe_transform_vector


def safe_dot_product(*args, **kwargs):
    return prune(_raw_safe_dot_product(*args, **kwargs))


def safe_norm(*args, **kwargs):
    return prune(_raw_safe_norm(*args, **kwargs))


def safe_transform_vector(*args, **kwargs):
    return prune(_raw_safe_transform_vector(*args, **kwargs))


# Aliases for backwards compatibility
CSGUnion = SolidUnion


# ============================================================================
# Helper functions (used by multiple functions in this file)
# ============================================================================


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


# ============================================================================
# Corner Joint Construction Functions
# ============================================================================


def cut_plain_miter_joint(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two timbers, cutting each end at half the angle between them.

    Both ends are cut by the same bisecting plane so they meet flush at the corner.
    Works for any angle including parallel timbers (parallel produces a perpendicular end cut).

    Args:
        arrangement: Corner joint arrangement with timber1, timber2, timber1_end, timber2_end.

    Returns:
        Joint object containing the two CutTimbers.
    """
    import warnings

    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end

    warn_if_arrangement_timbers_imperfect(arrangement)

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

    # Find the intersection point (or closest point) between the two timber centerlines
    # Using the formula for closest point between two lines in 3D
    # Line 1: P1 = endA_position + t * directionA
    # Line 2: P2 = endB_position + s * directionB

    w0 = prune(endA_position - endB_position)
    a = safe_dot_product(directionA, directionA)  # always >= 0
    b = safe_dot_product(directionA, directionB)
    c = safe_dot_product(directionB, directionB)  # always >= 0
    d = safe_dot_product(directionA, w0)
    e = safe_dot_product(directionB, w0)

    denom = prune(a * c - b * b)
    if zero_test(denom):
        # Parallel timbers: lines don't converge; bisect between the two end positions
        intersection_point = prune((endA_position + endB_position) / 2)
    else:
        # Parameters for closest points on each line
        t = prune((b * e - c * d) / denom)
        s = prune((a * e - b * d) / denom)

        # Get the closest points on each centerline
        pointA = prune(endA_position + directionA * t)
        pointB = prune(endB_position + directionB * s)

        # The intersection point is the midpoint between the two closest points
        intersection_point = prune((pointA + pointB) / 2)

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
    # For parallel timbers plane_normal is zero, so fall back to a perpendicular end cut.
    plane_normal_sq = safe_dot_product(plane_normal, plane_normal)
    if zero_test(plane_normal_sq):
        miter_normal = normA
    else:
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
    end_cut_A_distance_from_bottom = safe_dot_product(
        intersection_point - timberA.get_bottom_position_global(),
        timberA.get_length_direction_global(),
    )
    end_cut_B_distance_from_bottom = safe_dot_product(
        intersection_point - timberB.get_bottom_position_global(),
        timberB.get_length_direction_global(),
    )

    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=end_cut_A_distance_from_bottom if timberA_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=end_cut_A_distance_from_bottom if timberA_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=end_cut_A,
    )

    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=end_cut_B_distance_from_bottom if timberB_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=end_cut_B_distance_from_bottom if timberB_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=end_cut_B,
    )

    # Create CutTimbers with cuts passed at construction
    cut_timberA = cutA
    cut_timberB = cutB

    # Create and return the Joint with all data at construction
    joint = Joint(
        cuttings={"timberA": cut_timberA, "timberB": cut_timberB},
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
    from kumiki.cutcsg import RectangularPrism, HalfSpace, Difference, CutCSG, adopt_csg
    from kumiki.rule import safe_dot_product, safe_compare, Comparison

    error = arrangement.check_plane_aligned()
    assert error is None, error

    tongue_timber = arrangement.timber1
    fork_timber = arrangement.timber2
    tongue_end = arrangement.timber1_end
    fork_end = arrangement.timber2_end

    warn_if_arrangement_timbers_imperfect(arrangement)

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

    tongue_end_cut_distance_from_bottom = safe_dot_product(
        fork_far_face_point_global - tongue_timber.get_bottom_position_global(),
        tongue_timber.get_length_direction_global(),
    )
    fork_end_cut_distance_from_bottom = safe_dot_product(
        tongue_far_face_point_global - fork_timber.get_bottom_position_global(),
        fork_timber.get_length_direction_global(),
    )

    tongue_negative_parts: list[CutCSG] = [tongue_negative_csg, tongue_end_cut]
    fork_negative_parts: list[CutCSG] = [fork_negative_csg, fork_end_cut]

    # -------------------------------------------------------------------------
    # Assemble cuts and joint
    # -------------------------------------------------------------------------
    tongue_cut = Cutting(
        timber=tongue_timber,
        maybe_top_end_cut_distance_from_bottom=tongue_end_cut_distance_from_bottom if tongue_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tongue_end_cut_distance_from_bottom if tongue_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=CSGUnion(children=tongue_negative_parts),
    )

    fork_cut = Cutting(
        timber=fork_timber,
        maybe_top_end_cut_distance_from_bottom=fork_end_cut_distance_from_bottom if fork_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=fork_end_cut_distance_from_bottom if fork_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=CSGUnion(children=fork_negative_parts),
    )

    return Joint(
        cuttings={
            "tongue_timber": tongue_cut,
            "fork_timber": fork_cut,
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


def cut_plain_corner_lap_joint(arrangement: CornerJointTimberArrangement, cut_ratio: Numeric = Rational(1, 2)) -> Joint:
    """
    Creates a corner-lap joint between two corner timbers with trimmed ends.

    Geometry is the same lap construction as `cut_plain_cross_lap_joint`, but applied
    to corner-arranged timbers and augmented with one end cut per timber so neither
    member extends past the corner.

    Args:
        arrangement: Corner-joint arrangement with timber1, timber2, timber1_end,
            timber2_end, and optional front_face_on_timber1.
        cut_ratio: Fraction [0, 1] controlling how much lap material is removed
            from each timber (same semantics as cross lap).

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        AssertionError: If timbers are not plane-aligned.
    """
    from .cross_joints import cut_plain_cross_lap_joint

    error = arrangement.check_plane_aligned()
    assert error is None, error

    timberA = arrangement.timber1
    timberB = arrangement.timber2
    timberA_end = arrangement.timber1_end
    timberB_end = arrangement.timber2_end

    # Reuse cross-lap geometry for the lap volume split.
    cross_lap_joint = cut_plain_cross_lap_joint(
        CrossJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            front_face_on_timber1=arrangement.front_face_on_timber1,
        ),
        cut_ratio=cut_ratio,
    )

    from kumiki.rule import safe_dot_product

    timberA_end_direction = timberA.get_face_direction_global(timberA_end)
    timberB_end_direction = timberB.get_face_direction_global(timberB_end)

    timberB_entry_face = timberB.get_closest_oriented_face_from_global_direction(-timberA_end_direction)
    timberB_far_face = timberB_entry_face.get_opposite_face()
    timberB_far_face_point_global = get_point_on_face_global(timberB_far_face, timberB)

    timberA_entry_face = timberA.get_closest_oriented_face_from_global_direction(-timberB_end_direction)
    timberA_far_face = timberA_entry_face.get_opposite_face()
    timberA_far_face_point_global = get_point_on_face_global(timberA_far_face, timberA)

    timberA_end_cut_distance_from_bottom = safe_dot_product(
        timberB_far_face_point_global - timberA.get_bottom_position_global(),
        timberA.get_length_direction_global(),
    )
    timberB_end_cut_distance_from_bottom = safe_dot_product(
        timberA_far_face_point_global - timberB.get_bottom_position_global(),
        timberB.get_length_direction_global(),
    )

    # LOL so smart, whatever
    cross_lap_cutA = cross_lap_joint.cuttings["timberA"]
    cross_lap_cutB = cross_lap_joint.cuttings["timberB"]

    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=(
            timberA_end_cut_distance_from_bottom
            if timberA_end == TimberReferenceEnd.TOP
            else cross_lap_cutA.maybe_top_end_cut_distance_from_bottom
        ),
        maybe_bottom_end_cut_distance_from_bottom=(
            timberA_end_cut_distance_from_bottom
            if timberA_end == TimberReferenceEnd.BOTTOM
            else cross_lap_cutA.maybe_bottom_end_cut_distance_from_bottom
        ),
        negative_csg=cross_lap_cutA.negative_csg,
        label=cross_lap_cutA.label,
    )
    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=(
            timberB_end_cut_distance_from_bottom
            if timberB_end == TimberReferenceEnd.TOP
            else cross_lap_cutB.maybe_top_end_cut_distance_from_bottom
        ),
        maybe_bottom_end_cut_distance_from_bottom=(
            timberB_end_cut_distance_from_bottom
            if timberB_end == TimberReferenceEnd.BOTTOM
            else cross_lap_cutB.maybe_bottom_end_cut_distance_from_bottom
        ),
        negative_csg=cross_lap_cutB.negative_csg,
        label=cross_lap_cutB.label,
    )

    return Joint(
        cuttings={
            "timberA": cutA,
            "timberB": cutB,
        },
        ticket=JointTicket(joint_type="plain_corner_lap"),
        jointAccessories={},
    )


# ============================================================================
# Japanese corner joints (moved from japanese_joints.py)
# ============================================================================


def cut_mitered_and_keyed_lap_joint(arrangement: CornerJointTimberArrangement, lap_thickness: Optional[Numeric] = None, lap_start_distance_from_reference_miter_face: Optional[Numeric] = None, distance_between_lap_and_outside: Optional[Numeric] = None, num_laps: int = 2, key_width: Optional[Numeric] = None, key_thickness: Optional[Numeric] = None) -> Joint:
    """
    Creates a mitered and keyed lap joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)
    between two timbers.

    This is a traditional Japanese timber joint that combines a miter joint with interlocking
    finger laps on the inside of the miter for additional mechanical strength.

    Args:
        arrangement: Corner joint arrangement where timber1 and timber2 are the joined
            timbers, timber1_end and timber2_end are the joined ends, and
            front_face_on_timber1 defines the reference miter face on timber1.
        lap_thickness: Thickness of each lap/finger (optional, auto-calculated if None)
        lap_start_distance_from_reference_miter_face: Distance from miter face to first lap (optional)
        distance_between_lap_and_outside: Inset distance from outer face (optional)
        num_laps: Number of interlocking laps/fingers (minimum 2)
        key_width: Width of each key measured along the diagonal direction. If None,
            defaults to lap_thickness.
        key_thickness: Thickness of each key (the narrow dimension). If None,
            defaults to lap_thickness / 3.

    Returns:
        Joint object containing the two CutTimbers with miter and finger cuts applied

    Raises:
        ValueError: If parameters are invalid or timbers are not properly positioned
    """
    require_check(arrangement.check_plane_aligned())
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the reference miter face"
    )
    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberA_reference_miter_face = arrangement.front_face_on_timber1
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end
    from sympy import acos, pi

    # ========================================================================
    # Step 1: Parameter validation and find matching miter faces
    # ========================================================================

    # Validate num_laps
    if num_laps < 2:
        raise ValueError(f"num_laps must be at least 2, got {num_laps}")

    # Find matching miter face on timberB
    timberA_miter_face_normal = timberA.get_face_direction_global(timberA_reference_miter_face)
    timberB_reference_miter_face_enum = timberB.get_closest_oriented_face_from_global_direction(
        timberA_miter_face_normal
    )

    # Convert to TimberLongFace if it's a long face
    if timberB_reference_miter_face_enum == TimberFace.RIGHT:
        timberB_reference_miter_face = TimberLongFace.RIGHT
    elif timberB_reference_miter_face_enum == TimberFace.LEFT:
        timberB_reference_miter_face = TimberLongFace.LEFT
    elif timberB_reference_miter_face_enum == TimberFace.FRONT:
        timberB_reference_miter_face = TimberLongFace.FRONT
    elif timberB_reference_miter_face_enum == TimberFace.BACK:
        timberB_reference_miter_face = TimberLongFace.BACK
    else:
        raise ValueError(
            f"timberB matching face must be a long face (not TOP or BOTTOM), got {timberB_reference_miter_face_enum}"
        )

    # Verify the normals are parallel
    timberB_miter_face_normal = timberB.get_face_direction_global(timberB_reference_miter_face)
    if not are_vectors_parallel(timberA_miter_face_normal, timberB_miter_face_normal):
        raise ValueError(
            f"Miter face normals must be parallel. "
            f"timberA face normal: {timberA_miter_face_normal.T}, "
            f"timberB face normal: {timberB_miter_face_normal.T}"
        )


    # ========================================================================
    # Step 2: Calculate and validate angle between timbers
    # ========================================================================

    # Get end directions (pointing outward from timber)
    if timberA_end == TimberReferenceEnd.TOP:
        directionA = timberA.get_length_direction_global()
    else:  # BOTTOM
        directionA = -timberA.get_length_direction_global()

    if timberB_end == TimberReferenceEnd.TOP:
        directionB = timberB.get_length_direction_global()
    else:  # BOTTOM
        directionB = -timberB.get_length_direction_global()

    # Calculate angle between timbers using dot product
    # angle = acos(directionA · directionB)
    dot_product = safe_dot_product(normalize_vector(directionA), normalize_vector(directionB))

    # Clamp to [-1, 1] to avoid numerical issues with acos
    from sympy import Max, Min
    dot_product_clamped = Max(Rational(-1), Min(Rational(1), dot_product))
    angle = acos(dot_product_clamped)

    # Validate angle is between 45 and 135 degrees
    min_angle = radians(pi / Integer(4))  # 45 degrees
    max_angle = radians(Rational(3) * pi / Integer(4))  # 135 degrees

    if angle < min_angle or angle > max_angle:
        raise ValueError(
            f"Angle between timbers must be between 45° and 135°, "
            f"got {float(angle * 180 / pi):.1f}°"
        )

    # ========================================================================
    # Step 3: Calculate dimensions and default values
    # ========================================================================

    # Get miter face dimensions
    miter_face_depth = timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.to.face())
    miter_face_width = timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.rotate_right().to.face())

    # Calculate lap_thickness and lap_start_distance defaults
    lap_thickness_final: Numeric
    lap_start_distance_final: Numeric

    if lap_thickness is None and lap_start_distance_from_reference_miter_face is None:
        # Both None: distribute evenly
        # Total space for laps plus margins: miter_face_depth
        # We want: margin + num_laps * thickness + margin = miter_face_depth
        # With equal margins: 2*margin + num_laps*thickness = miter_face_depth
        # Let's use: margin = thickness, so: (num_laps + 2)*thickness = miter_face_depth
        lap_thickness_final = miter_face_depth / (num_laps + Integer(2))
        lap_start_distance_final = lap_thickness_final

    elif lap_thickness is None:
        # Only start distance given, calculate thickness
        assert lap_start_distance_from_reference_miter_face is not None  # Type narrowing
        remaining_depth: Numeric = miter_face_depth - lap_start_distance_from_reference_miter_face
        lap_thickness_final = remaining_depth / Integer(num_laps+1)
        lap_start_distance_final = lap_start_distance_from_reference_miter_face
    elif lap_start_distance_from_reference_miter_face is None:
        # Only thickness given, calculate start distance
        total_lap_depth: Numeric = lap_thickness * num_laps
        lap_start_distance_final = (miter_face_depth - total_lap_depth) / Rational(2)
        lap_thickness_final = lap_thickness
    else:
        # Both provided
        lap_thickness_final = lap_thickness
        lap_start_distance_final = lap_start_distance_from_reference_miter_face

    # Default distance_between_lap_and_outside
    if distance_between_lap_and_outside is None:
        distance_between_lap_and_outside = miter_face_width * Rational(1, 5)


    # ========================================================================
    # Step 4: Validate fit
    # ========================================================================

    # Check laps fit in depth
    total_lap_depth = lap_start_distance_final + lap_thickness_final * num_laps
    if total_lap_depth >= miter_face_depth:
        raise ValueError(
            f"Laps do not fit in timber depth. "
            f"Total lap depth: {float(total_lap_depth):.3f}, "
            f"Miter face depth: {float(miter_face_depth):.3f}"
        )

    # Check laps fit on timberB
    # TODO fix, you need to mark the lap start/end positions and measure on timberB to see that they are both within the timberB miter face depth
    timberB_miter_face_depth = timberB.get_size_in_face_normal_axis(timberB_reference_miter_face.to.face())
    if total_lap_depth >= timberB_miter_face_depth:
        raise ValueError(
            f"Laps do not fit on timberB. "
            f"Total lap depth: {float(total_lap_depth):.3f}, "
            f"TimberB miter face depth: {float(timberB_miter_face_depth):.3f}"
        )

    # ========================================================================
    # Step 5: Find inner face normals and inner shoulder direction
    # ========================================================================

    # Determine which faces are on the "inside" of the corner
    # The inside faces are perpendicular to the miter face and point toward each other

    # For a corner joint, we need to find the faces that face toward the other timber
    # Use cross product of miter normal and length direction to find the perpendicular faces

    # Calculate the diagonal direction (bisector between timberA and timberB)
    # This is the average of the two end directions
    diagonal_direction = normalize_vector(directionA + directionB)

    # Find inner faces by looking for the closest oriented face to the negative diagonal direction
    # The negative diagonal points toward the inside of the corner
    negative_diagonal = -diagonal_direction
    timberA_inner_face_enum = timberA.get_closest_oriented_long_face_from_global_direction(negative_diagonal).to.face()
    timberB_inner_face_enum = timberB.get_closest_oriented_long_face_from_global_direction(negative_diagonal).to.face()

    # Get the inner face normals
    timberA_inner_face_normal = timberA.get_face_direction_global(timberA_inner_face_enum)
    timberB_inner_face_normal = timberB.get_face_direction_global(timberB_inner_face_enum)

    # The inner shoulder axis is the intersection line of the two inner face planes
    # Direction of intersection line = cross product of the two normals
    inner_shoulder_direction = cross_product(timberA_inner_face_normal, timberB_inner_face_normal)
    inner_shoulder_direction = normalize_vector(inner_shoulder_direction)

    # validate that the timber size in the inner_face axis direction is the same on both timbers
    timberA_inner_face_size = timberA.get_size_in_face_normal_axis(timberA_inner_face_enum)
    timberB_inner_face_size = timberB.get_size_in_face_normal_axis(timberB_inner_face_enum)
    if not zero_test(timberA_inner_face_size - timberB_inner_face_size):
        raise ValueError(
            f"Timber widths in the miter plane are not the same. "
            f"TimberA size: {float(timberA_inner_face_size):.3f}, "
            f"TimberB size: {float(timberB_inner_face_size):.3f}"
        )

    # ========================================================================
    # Step 6: Create marking transform on timberA
    # ========================================================================


    # Find where timberB's centerline intersects timberA's centerline
    timberB_centerline = locate_centerline(timberB)
    centerline_marking = mark_distance_from_end_along_centerline(timberB_centerline, timberA, end=TimberReferenceEnd.BOTTOM)

    marking_position = timberA.get_bottom_position_global()
    marking_position = marking_position + timberA.get_length_direction_global() * centerline_marking.distance

    marking_position_on_centerline = marking_position + timberA_miter_face_normal * (-timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.to.face()) / Rational(2))

    # Compute the angle between the two timbers to get the correct scale factor
    # The half-angle is the angle between the diagonal and either timber's length direction
    from sympy import acos, sin, sqrt
    cos_angle = safe_dot_product(directionA, directionB)
    timber_angle = acos(cos_angle)  # Angle between the two timbers
    half_angle = timber_angle / Rational(2)  # Angle between diagonal and timber length

    # Scale factor for moving along diagonal to achieve perpendicular offset
    # For 90° joint: half_angle = 45°, scale = 1/sin(45°) = sqrt(2)
    # For 180° joint: half_angle = 90°, scale = 1/sin(90°) = 1
    # For 135° joint: half_angle = 67.5°, scale = 1/sin(67.5°)
    diagonal_scale_factor = Rational(1) / sin(half_angle)

    # Move to the inner shoulder edge along the diagonal direction
    inner_edge_offset = timberA.get_size_in_face_normal_axis(timberA_inner_face_enum) / Rational(2)
    diagonal_offset = inner_edge_offset * diagonal_scale_factor
    marking_position = marking_position_on_centerline - diagonal_direction * diagonal_offset

    # Create orientation for the marking transform
    # Z-axis points toward the end (along timber length direction or opposite)
    if timberA_end == TimberReferenceEnd.TOP:
        marking_z = timberA.get_length_direction_global()
    else:
        marking_z = -timberA.get_length_direction_global()

    # X-axis aligns with the inner shoulder direction
    marking_x = inner_shoulder_direction

    # Ensure correct orientation (might need to flip based on handedness)
    # Y-axis from cross product
    marking_y = cross_product(marking_z, marking_x)
    marking_y = normalize_vector(marking_y)

    # Re-orthogonalize X to be perpendicular to Z
    marking_x = cross_product(marking_y, marking_z)
    marking_x = normalize_vector(marking_x)

    # ========================================================================
    # Step 7: Generate finger prisms
    # ========================================================================

    # Calculate finger dimensions
    finger_length = lap_thickness_final

    # Finger size: X = miter_face_width, Y = miter_face_width * tan(half_angle)
    from sympy import pi, tan
    finger_size_x = miter_face_width
    finger_size_y = miter_face_width * tan(half_angle)
    finger_size = create_v2(finger_size_x, finger_size_y)

    # Create all fingers in global space
    all_fingers_global = []

    for i in range(num_laps):
        # Determine if this lap belongs to timber A or B
        # Even indices (0, 2, 4, ...) = timber A, odd indices (1, 3, 5, ...) = timber B
        is_timber_a = (i % 2 == 0)

        # Calculate Z position along timber length for this lap
        z_offset = lap_start_distance_final + i * lap_thickness_final

        # Start from marking_position (at centerline intersection, on miter face surface)
        finger_position = marking_position_on_centerline

        # Move along miter face normal (into timber) by z_offset
        finger_position = finger_position + timberA_miter_face_normal * z_offset

        # Create finger orientation with Z-axis pointing along miter face normal
        # Z-axis: points along miter face normal (into timber)
        finger_z = timberA_miter_face_normal

        # X-axis: along the inner face normal direction based on which timber this lap belongs to
        if is_timber_a:
            finger_x = timberA_inner_face_normal
        else:
            finger_x = timberB_inner_face_normal

        # Y-axis: perpendicular to both (computed via cross product)
        finger_y = cross_product(finger_z, finger_x)
        finger_y = normalize_vector(finger_y)

        finger_orientation = Orientation(Matrix([
            [finger_x[0], finger_y[0], finger_z[0]],
            [finger_x[1], finger_y[1], finger_z[1]],
            [finger_x[2], finger_y[2], finger_z[2]]
        ]))

        # Rotate the finger transform around the inner shoulder edge axis
        finger_transform_global = Transform(position=finger_position, orientation=finger_orientation)

        # Create finger prism in global space
        finger_prism_global = RectangularPrism(
            size=finger_size,
            transform=finger_transform_global,
            start_distance=Integer(0),
            end_distance=finger_length
        )

        all_fingers_global.append((finger_prism_global, is_timber_a))

    # Separate fingers by which timber they belong to (even = A, odd = B)
    A_finger_indices = [i for i in range(num_laps) if i % 2 == 0]
    B_finger_indices = [i for i in range(num_laps) if i % 2 == 1]

    # Helper function to convert finger from global to local and apply crop
    def convert_finger_to_local(finger_global: RectangularPrism, target_timber: TimberLike, is_timber_a_finger: bool) -> CutCSG:
        """Convert finger from global to local coordinates and apply crop using opposing timber's inner face."""
        # Determine opposing timber from finger type
        if is_timber_a_finger:
            # Crop A fingers using timberB's inner face
            opposing_timber = timberB
            opposing_inner_face_enum = timberB_inner_face_enum
        else:
            # Crop B fingers using timberA's inner face
            opposing_timber = timberA
            opposing_inner_face_enum = timberA_inner_face_enum

        # Convert to local space
        finger_transform_local = finger_global.transform.to_local_transform(target_timber.transform)
        finger_local = replace(finger_global, transform=finger_transform_local)

        # Apply crop using the opposing timber's inner face
        from kumiki.measuring import locate_into_face
        from kumiki.rule import safe_transform_vector

        # Measure into opposing timber's inner face to create a cutting plane (in global space)
        crop_distance = miter_face_width - distance_between_lap_and_outside
        crop_plane = locate_into_face(crop_distance, opposing_inner_face_enum, opposing_timber)

        # Convert crop plane to local space of target timber
        # Convert UnsignedPlane point and normal to local coordinates
        crop_point_local = target_timber.transform.global_to_local(crop_plane.point)
        crop_normal_local = safe_transform_vector(target_timber.orientation.matrix.T, crop_plane.normal)

        # Convert to HalfSpace in local coordinates
        crop_offset_local = safe_dot_product(crop_point_local, crop_normal_local)
        # Use negative normal to represent the "too far into opposing timber" side
        crop_halfspace_local = HalfSpace(normal=-crop_normal_local, offset=-crop_offset_local)

        # Crop the finger by subtracting everything beyond the half space
        finger_local = Difference(base=finger_local, subtract=[crop_halfspace_local])

        return finger_local

    # A fingers in timberA local space (for subtracting from timberA)
    A_fingers_in_timberA = []
    for idx in A_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberA, is_timber_a_finger)
        A_fingers_in_timberA.append(finger_local)

    # B fingers in timberA local space (for adding voids to timberA)
    B_fingers_in_timberA = []
    for idx in B_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberA, is_timber_a_finger)
        B_fingers_in_timberA.append(finger_local)

    # A fingers in timberB local space (for adding voids to timberB)
    A_fingers_in_timberB = []
    for idx in A_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberB, is_timber_a_finger)
        A_fingers_in_timberB.append(finger_local)

    # B fingers in timberB local space (for subtracting from timberB)
    B_fingers_in_timberB = []
    for idx in B_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberB, is_timber_a_finger)
        B_fingers_in_timberB.append(finger_local)

    # ========================================================================
    # Step 7.5: Create Keys
    # ========================================================================

    # Set default key dimensions if not provided
    if key_width is None:
        key_width = lap_thickness_final
    if key_thickness is None:
        key_thickness = lap_thickness_final / Rational(3)


    key_depth = miter_face_width/sin(half_angle)-distance_between_lap_and_outside/sin(half_angle)

    keys_in_timberA = []
    keys_in_timberB = []
    key_wedges = []

    num_keys = num_laps - 1
    for i in range(num_keys):
        key_position = marking_position
        z_offset = lap_start_distance_final + (i+1) * lap_thickness_final
        key_position = key_position + timberA_miter_face_normal * z_offset

        # set key_orientation, it should point in the diagonal direction with y axis in the -timberA_miter_face_normal direction
        key_orientation_before_rotation = Orientation.from_z_and_y(
            z_direction=diagonal_direction,
            y_direction=-timberA_miter_face_normal
        )

        # Rotate it around the diagonal direction (X-axis) by the same rotation angle as the fingers
        # This aligns the key with the finger geometry
        from sympy import atan2
        key_rotation_sign = -1 if i % 2 == 0 else 1
        key_rotation_angle = key_rotation_sign * atan2(key_thickness, key_width)
        rotation_for_key = Orientation.from_axis_angle(diagonal_direction, radians(key_rotation_angle))
        key_orientation = rotation_for_key * key_orientation_before_rotation
        key_transform_global = Transform(position=key_position, orientation=key_orientation)

        # Create key prism in global space
        # Size: key_width (X) x key_thickness (Y), depth (Z) in start/end_distance
        key_size = create_v2(key_width, key_thickness)
        key_prism_global = RectangularPrism(
            size=key_size,
            transform=key_transform_global,
            start_distance=-key_depth,
            end_distance=key_depth
        )

        # Convert to timberA's local space using replace
        key_transform_local_A = key_transform_global.to_local_transform(timberA.transform)
        key_prism_in_timberA = replace(key_prism_global, transform=key_transform_local_A)
        keys_in_timberA.append(key_prism_in_timberA)

        # Convert to timberB's local space using replace
        key_transform_local_B = key_transform_global.to_local_transform(timberB.transform)
        key_prism_in_timberB = replace(key_prism_global, transform=key_transform_local_B)
        keys_in_timberB.append(key_prism_in_timberB)

        # Create Wedge accessory matching the key prism
        # The wedge has the same transform as the key prism (in global space)
        # base_width and tip_width are the same (key_width) since it's a rectangular shape
        # height is key_thickness, length is 2 * key_depth (from -key_depth to +key_depth)
        key_wedge = Wedge(
            transform=key_transform_global,
            base_width=key_width,
            tip_width=key_width,  # Same as base_width for rectangular shape
            height=key_thickness,
            length=key_depth,
            stickout_length=key_depth*Rational(1,4)
        )
        key_wedges.append(key_wedge)

    # ========================================================================
    # Step 8: Create rough end cuts and miter half plane cuts
    # ========================================================================

    # Create rough end cuts perpendicular to timbers
    # These cross the corner of the miter


    if timberA_end == TimberReferenceEnd.TOP:
        # Cut the top: position is outward from marking, normal points up (to cut away top)
        rough_cut_position_A = marking_position + timberA.get_length_direction_global() * finger_size_y
        rough_cut_normal_A_global = timberA.get_length_direction_global()
    else:  # BOTTOM
        # Cut the bottom: position is outward from marking, normal points down (to cut away bottom)
        rough_cut_position_A = marking_position - timberA.get_length_direction_global() * finger_size_y
        rough_cut_normal_A_global = -timberA.get_length_direction_global()

    local_normal_A_rough = safe_transform_vector(timberA.orientation.matrix.T, rough_cut_normal_A_global)
    local_offset_A_rough = safe_dot_product(rough_cut_position_A, rough_cut_normal_A_global) - safe_dot_product(rough_cut_normal_A_global, timberA.get_bottom_position_global())
    rough_end_cut_A = HalfSpace(normal=local_normal_A_rough, offset=local_offset_A_rough)

    if timberB_end == TimberReferenceEnd.TOP:
        rough_cut_position_B = marking_position + timberB.get_length_direction_global() * finger_size_y
        rough_cut_normal_B_global = timberB.get_length_direction_global()
    else:  # BOTTOM
        rough_cut_position_B = marking_position - timberB.get_length_direction_global() * finger_size_y
        rough_cut_normal_B_global = -timberB.get_length_direction_global()

    local_normal_B_rough = safe_transform_vector(timberB.orientation.matrix.T, rough_cut_normal_B_global)
    local_offset_B_rough = safe_dot_product(rough_cut_position_B, rough_cut_normal_B_global) - safe_dot_product(rough_cut_normal_B_global, timberB.get_bottom_position_global())
    rough_end_cut_B = HalfSpace(normal=local_normal_B_rough, offset=local_offset_B_rough)

    # Create miter half plane cuts (for negative_csg)
    intersection_point = marking_position

    # Create miter plane normal
    normA = normalize_vector(directionA)
    normB = normalize_vector(directionB)
    bisector = normalize_vector(normA + normB)
    plane_normal = cross_product(normA, normB)
    miter_normal = normalize_vector(cross_product(bisector, plane_normal))

    # Create HalfSpace cuts for miter planes
    dot_A = safe_dot_product(normA, miter_normal)
    if safe_compare(dot_A, 0, Comparison.GT):
        normalA = miter_normal
    else:
        normalA = -miter_normal

    local_normalA = safe_transform_vector(timberA.orientation.matrix.T, normalA)
    local_offsetA = safe_dot_product(intersection_point, normalA) - safe_dot_product(normalA, timberA.get_bottom_position_global())

    dot_B = safe_dot_product(normB, miter_normal)
    if safe_compare(dot_B, 0, Comparison.GT):
        normalB = miter_normal
    else:
        normalB = -miter_normal

    local_normalB = safe_transform_vector(timberB.orientation.matrix.T, normalB)
    local_offsetB = safe_dot_product(intersection_point, normalB) - safe_dot_product(normalB, timberB.get_bottom_position_global())

    miter_half_plane_A = HalfSpace(normal=local_normalA, offset=local_offsetA)
    miter_half_plane_B = HalfSpace(normal=local_normalB, offset=local_offsetB)

    # ========================================================================
    # Step 9: Combine cuts and return Joint
    # ========================================================================

    # For A fingers: SUBTRACT from timberA's half plane, ADD to timberB's half plane
    # For B fingers: SUBTRACT from timberB's half plane, ADD to timberA's half plane

    # TimberA negative_csg:
    # - Start with miter_half_plane_A
    # - Subtract A fingers (they protrude, so remove them from the half plane cut)
    # - Add B fingers (they create voids)
    # - Add keys (they create voids)
    if A_fingers_in_timberA:
        # A fingers subtract from half plane
        miter_cut_A_with_fingers = Difference(miter_half_plane_A, A_fingers_in_timberA)
    else:
        miter_cut_A_with_fingers = miter_half_plane_A

    # Collect all voids for timberA: B fingers and keys
    voids_in_A = []
    if B_fingers_in_timberA:
        voids_in_A.extend(B_fingers_in_timberA)
    if keys_in_timberA:
        voids_in_A.extend(keys_in_timberA)

    if voids_in_A:
        negative_csg_A = CSGUnion([miter_cut_A_with_fingers] + voids_in_A)
    else:
        negative_csg_A = miter_cut_A_with_fingers

    # TimberB negative_csg:
    # - Start with miter_half_plane_B
    # - Subtract B fingers (they protrude)
    # - Add A fingers (they create voids)
    # - Add keys (they create voids)
    if B_fingers_in_timberB:
        # B fingers subtract from half plane
        miter_cut_B_with_fingers = Difference(miter_half_plane_B, B_fingers_in_timberB)
    else:
        miter_cut_B_with_fingers = miter_half_plane_B

    # Collect all voids for timberB: A fingers and keys
    voids_in_B = []
    if A_fingers_in_timberB:
        voids_in_B.extend(A_fingers_in_timberB)
    if keys_in_timberB:
        voids_in_B.extend(keys_in_timberB)

    if voids_in_B:
        negative_csg_B = CSGUnion([miter_cut_B_with_fingers] + voids_in_B)
    else:
        negative_csg_B = miter_cut_B_with_fingers

    rough_end_cut_A_z = (
        rough_end_cut_A.offset
        if timberA_end == TimberReferenceEnd.TOP
        else -rough_end_cut_A.offset
    )
    rough_end_cut_B_z = (
        rough_end_cut_B.offset
        if timberB_end == TimberReferenceEnd.TOP
        else -rough_end_cut_B.offset
    )

    # Create Cutting objects
    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=rough_end_cut_A_z if timberA_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=rough_end_cut_A_z if timberA_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=negative_csg_A
    )

    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=rough_end_cut_B_z if timberB_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=rough_end_cut_B_z if timberB_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=negative_csg_B
    )

    # Create CutTimber objects
    cut_timberA = cutA
    cut_timberB = cutB


    # Create jointAccessories dict with key wedges
    joint_accessories = {}
    for i, wedge in enumerate(key_wedges):
        joint_accessories[f"key_{i}"] = wedge

    # Return Joint
    return Joint(
        cuttings={
            timberA.ticket.name: cut_timberA,
            timberB.ticket.name: cut_timberB
        },
        ticket=JointTicket(joint_type="mitered_and_keyed_lap"),
        jointAccessories=joint_accessories,
    )


# ============================================================================
# Aliases for Japanese joint functions
# ============================================================================

cut_箱相欠き車知栓仕口 = cut_mitered_and_keyed_lap_joint
cut_hako_aikaki_shachi_sen_shikuchi = cut_mitered_and_keyed_lap_joint
