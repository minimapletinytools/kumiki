"""
Kumiki - Butt joint construction functions
Contains plain butt, tongue-and-fork butt, mortise-and-tenon, and housed dovetail butt joint implementations.
"""

from __future__ import annotations  # Enable deferred annotation evaluation

import warnings
from dataclasses import replace
from functools import wraps

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *
from .shavings.relief import warn_if_arrangement_timbers_imperfect, chop_shoulder_notch_on_timber_face, ShoulderReliefCSGGeometry, chop_relief_for_butt_joint_arrangement, chop_shoulder_notch_aligned_with_timber, does_shoulder_plane_need_notching
from kumiki.measuring import (
    locate_top_center_position,
    locate_bottom_center_position,
    locate_position_on_centerline_from_bottom,
    locate_position_on_centerline_from_top,
    locate_into_face,
    locate_edge,
    locate_plane_from_edge_in_direction,
    mark_distance_from_end_along_centerline,
    mark_plane_from_edge_in_direction,
    get_center_point_on_face_global,
    Space,
)
from kumiki.timber_shavings import are_timbers_plane_aligned
from kumiki.cutcsg import CutCSG, RectangularPrism, HalfSpace, Difference, SolidUnion, adopt_csg, PrismFace, Cylinder
from .shavings.build_a_butt import (
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
    PegPositionResult,
    PegPositionSpace,
    SimplePegParameters,
    compute_peg_positions,
    compute_butt_joint_shoulder,
    dovetail_tenon_geometry,
    DovetailTenonGeometeryResult,
    DovetailTenonWedgeAccessoryParameters,
)


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
# Helper functions
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
        face_center = timber.get_bottom_position_global() + (timber.length / scalar(2)) * timber.get_length_direction_global()

        # Offset to the face surface
        if face == TimberFace.RIGHT:
            face_center = face_center + (timber.size[0] / scalar(2)) * timber.get_width_direction_global()
        elif face == TimberFace.LEFT:
            face_center = face_center - (timber.size[0] / scalar(2)) * timber.get_width_direction_global()
        elif face == TimberFace.FRONT:
            face_center = face_center + (timber.size[1] / scalar(2)) * timber.get_height_direction_global()
        else:  # BACK
            face_center = face_center - (timber.size[1] / scalar(2)) * timber.get_height_direction_global()

        return face_center


# ============================================================================
# Butt Joint Construction Functions
# ============================================================================


def cut_plain_butt_joint(arrangement: ButtJointTimberArrangement) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the face of the receiving timber.

    The butt timber's end is trimmed along the plane of the best-matching long face of the
    receiving timber. The receiving timber is not cut.

    Works for any non-parallel angle between the timbers, including oblique 3D angles.
    The cut plane follows the actual receiving face geometry rather than being perpendicular
    to the butt timber's axis, so the mating face is always flush.

    Args:
        arrangement: Butt joint arrangement with butt_timber, receiving_timber, butt_timber_end.

    Returns:
        Joint object containing the cut butt timber and uncut receiving timber.

    Raises:
        AssertionError: If the timbers are parallel.
    """

    receiving_timber = arrangement.receiving_timber
    butt_timber = arrangement.butt_timber
    butt_end = arrangement.butt_timber_end

    warn_if_arrangement_timbers_imperfect(arrangement)

    assert not are_vectors_parallel(
        receiving_timber.get_length_direction_global(),
        butt_timber.get_length_direction_global(),
    ), "Timbers cannot be parallel for a butt joint"

    # Get the direction of the butt end (pointing outward from the timber body)
    if butt_end == TimberEnd.TOP:
        butt_direction = butt_timber.get_length_direction_global()
    else:
        butt_direction = -butt_timber.get_length_direction_global()

    # Find the long face of the receiving timber that faces the incoming butt timber.
    # We pass -butt_direction because the face we want has its outward normal pointing
    # toward the butt timber (i.e., opposite to the butt travel direction).
    receiving_face = receiving_timber.get_closest_oriented_long_face_from_global_direction(-butt_direction)
    receiving_face_dir_global = receiving_timber.get_face_direction_global(receiving_face)

    # A point on the receiving face plane (use face center)
    face_center = _get_face_center_position(receiving_timber, receiving_face)

    # Orient the cut-plane normal to point in the direction material is removed
    # (i.e., away from the butt timber body, toward the receiving timber).
    # The receiving face normal points toward the butt, so flip it.
    dot_check = safe_dot_product(receiving_face_dir_global, butt_direction)
    if safe_compare(dot_check, 0, Comparison.GT):
        cut_normal_global = receiving_face_dir_global
    else:
        cut_normal_global = -receiving_face_dir_global

    # Convert cut plane to butt timber local coordinates
    local_normal = safe_transform_vector(butt_timber.orientation.matrix.T, cut_normal_global)
    local_offset = (
        safe_dot_product(cut_normal_global, face_center)
        - safe_dot_product(cut_normal_global, butt_timber.get_bottom_position_global())
    )
    end_cut_distance_from_bottom = safe_dot_product(
        face_center - butt_timber.get_bottom_position_global(),
        butt_timber.get_length_direction_global(),
    )

    end_cut = HalfSpace(normal=local_normal, offset=local_offset)

    cut = Cutting(
        timber=butt_timber,
        maybe_top_end_cut_distance_from_bottom=end_cut_distance_from_bottom if butt_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=end_cut_distance_from_bottom if butt_end == TimberEnd.BOTTOM else None,
        negative_csg=end_cut,
    )

    # Assembly: a plain butt has no mechanical engagement (it is free after 0
    # travel), so use the receiving timber's thickness along the butt axis as
    # a nominal freed_after to make the preview separation visible.
    nominal_travel = receiving_timber.get_size_in_direction_3d(butt_direction)
    joint = Joint(
        cuttings={
            "receiving_timber": Cutting(
                timber=receiving_timber,
                assembly_freedom=AssemblyFreedom.translation(butt_direction, freed_after=nominal_travel),
            ),
            "butt_timber": replace(
                cut,
                assembly_freedom=AssemblyFreedom.translation(-butt_direction, freed_after=nominal_travel),
            ),
        },
        ticket=JointTicket(joint_type="plain_butt"),
        jointAccessories={},
    )

    return joint


def cut_plain_butt_joint_on_face_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the face of the receiving timber.

    Requires the timbers to be face-aligned. For an unrestricted version that works at any
    angle, use `cut_plain_butt_joint` directly.

    Args:
        arrangement: Butt joint arrangement with butt_timber, receiving_timber, butt_timber_end.
                     Timbers must be face-aligned and non-parallel.

    Returns:
        Joint object containing the cut butt timber and uncut receiving timber.

    Raises:
        AssertionError: If the timbers are not face-aligned or are parallel.
    """
    assert are_timbers_face_aligned(arrangement.receiving_timber, arrangement.butt_timber), \
        "Timbers must be face-aligned (orientations related by 90-degree rotations) for this joint type"
    return cut_plain_butt_joint(arrangement)


def cut_plain_butt_joint_on_face_aligned_timbers_DEPRECATED(arrangement: ButtJointTimberArrangement) -> Joint:
    """
    DEPRECATED: Use `cut_plain_butt_joint_on_face_aligned_timbers` instead.

    Original implementation kept for reference. The new thin wrapper delegates to
    `cut_plain_butt_joint` which uses the receiving face plane directly, producing
    identical results for face-aligned perpendicular timbers.
    """
    receiving_timber = arrangement.receiving_timber
    butt_timber = arrangement.butt_timber
    butt_end = arrangement.butt_timber_end

    assert are_timbers_face_aligned(receiving_timber, butt_timber), \
        "Timbers must be face-aligned (orientations related by 90-degree rotations) for this joint type"

    assert not are_vectors_parallel(receiving_timber.get_length_direction_global(), butt_timber.get_length_direction_global()), \
        "Timbers cannot be parallel for a butt joint"

    if butt_end == TimberEnd.TOP:
        butt_direction = butt_timber.get_length_direction_global()
    else:
        butt_direction = -butt_timber.get_length_direction_global()

    receiving_face = receiving_timber.get_closest_oriented_face_from_global_direction(-butt_direction)

    face_center = _get_face_center_position(receiving_timber, receiving_face)

    distance_from_bottom = safe_dot_product(face_center - butt_timber.get_bottom_position_global(), butt_timber.get_length_direction_global())
    distance_from_end = butt_timber.length - distance_from_bottom if butt_end == TimberEnd.TOP else distance_from_bottom

    cut = Cutting(
        timber=butt_timber,
        maybe_top_end_cut_distance_from_bottom=distance_from_bottom if butt_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=distance_from_bottom if butt_end == TimberEnd.BOTTOM else None,
        negative_csg=None
    )

    joint = Joint(
        cuttings={"receiving_timber": Cutting(timber=receiving_timber), "butt_timber": cut},
        ticket=JointTicket(joint_type="plain_butt"),
        jointAccessories={},
    )

    return joint


def cut_tongue_and_fork_butt_joint(
    arrangement: ButtJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = scalar(0),
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

    error = arrangement.check_plane_aligned()
    assert error is None, error

    tongue_timber = arrangement.butt_timber
    fork_timber = arrangement.receiving_timber
    tongue_end = arrangement.butt_timber_end

    warn_if_arrangement_timbers_imperfect(arrangement)

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
        tongue_thickness = tongue_normal_dimension / scalar(3)

    assert safe_compare(tongue_thickness, 0, Comparison.GT), "tongue_thickness must be greater than 0"
    assert safe_compare(tongue_normal_dimension - tongue_thickness, 0, Comparison.GE), \
        "tongue_thickness must be <= the tongue timber size in the shared plane normal axis"

    half_tongue_dimension = tongue_normal_dimension / scalar(2)
    half_tongue_thickness = tongue_thickness / scalar(2)
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
    fork_shoulder_distance = fork_timber.get_size_in_face_normal_axis(fork_entry_long_face) / scalar(2)

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
    fork_far_face_point_global = get_center_point_on_face_global(fork_far_face, fork_timber)

    fork_slot_depth = safe_dot_product(
        fork_far_face_point_global - shoulder_point_global,
        normalize_vector(tongue_end_direction),
    )
    assert safe_compare(fork_slot_depth, 0, Comparison.GT), \
        "Fork slot depth must be > 0; check timber arrangement and end selections"

    fork_slot_end_overshoot = max(fork_timber.size[0], fork_timber.size[1])
    fork_slot_back_extension = max(fork_timber.size[0], fork_timber.size[1]) * scalar(2)
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
    tongue_end_cut_local_normal = safe_transform_vector(
        tongue_timber.orientation.matrix.T, tongue_end_hs_normal_global
    )
    tongue_end_cut_local_offset = (
        safe_dot_product(tongue_end_hs_normal_global, fork_far_face_point_global)
        - safe_dot_product(tongue_end_hs_normal_global, tongue_timber.get_bottom_position_global())
    )
    tongue_end_cut = HalfSpace(normal=tongue_end_cut_local_normal, offset=tongue_end_cut_local_offset)
    tongue_end_cut_distance_from_bottom = safe_dot_product(
        fork_far_face_point_global - tongue_timber.get_bottom_position_global(),
        tongue_timber.get_length_direction_global(),
    )

    # -------------------------------------------------------------------------
    # No fork end cut — fork timber continues through the joint
    # -------------------------------------------------------------------------

    tongue_negative_parts: list[CutCSG] = [tongue_negative_csg, tongue_end_cut]

    # -------------------------------------------------------------------------
    # Assemble cuts and joint
    # -------------------------------------------------------------------------
    # Assembly: the tongue withdraws back out of the fork slot along its own
    # axis; it passes fully through the fork, so it is free after traveling
    # the fork's thickness in that direction.
    tongue_engagement = fork_timber.get_size_in_direction_3d(tongue_end_direction)
    tongue_cut = Cutting(
        timber=tongue_timber,
        maybe_top_end_cut_distance_from_bottom=tongue_end_cut_distance_from_bottom if tongue_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tongue_end_cut_distance_from_bottom if tongue_end == TimberEnd.BOTTOM else None,
        negative_csg=CSGUnion(children=tongue_negative_parts),
        assembly_freedom=AssemblyFreedom.translation(-tongue_end_direction, freed_after=tongue_engagement),
    )

    fork_cut = Cutting(
        timber=fork_timber,
        negative_csg=fork_negative_csg,
        assembly_freedom=AssemblyFreedom.translation(tongue_end_direction, freed_after=tongue_engagement),
    )

    return Joint(
        cuttings={
            "tongue_timber": tongue_cut,
            "fork_timber": fork_cut,
        },
        ticket=JointTicket(joint_type="tongue_and_fork_butt"),
        jointAccessories={},
    )


# ============================================================================
# Mortise and Tenon helpers
# ============================================================================


def convert_mortise_shoulder_inset_to_centerline_distance(
    mortise_shoulder_inset: Numeric,
    mortise_face: TimberFace,
    receiving_timber: TimberLike,
) -> Numeric:
    """
    Convert user-facing mortise shoulder inset parameter to centerline-relative distance.

    Inset is measured from the mortise entry face surface toward the centerline (inward).
    This function converts it to the signed distance from centerline (measured toward the tenon).

    Args:
        mortise_shoulder_inset: Distance from mortise entry face inward. 0 = shoulder flush
            with the entry face. Positive = shoulder deeper into the timber.
        mortise_face: The face of the receiving timber where the mortise enters.
        receiving_timber: The receiving timber.

    Returns:
        Signed distance from the timber centerline to the shoulder plane, measured toward
        the tenon side. 0 = shoulder at centerline.
    """
    inset_plane = locate_into_face(mortise_shoulder_inset, mortise_face, receiving_timber)
    inset_marking = mark_plane_from_edge_in_direction(inset_plane, receiving_timber, TimberCenterline.CENTERLINE)
    return inset_marking.distance


@dataclass(frozen=True)
class WedgeParameters:
    """
    Parameters for wedges in mortise and tenon joints.

    Attributes:
        shape: Shape specification for the wedge
        depth: Depth of the wedge cut (may differ from length of wedge)
        width_axis: Wedges run along this axis. When looking perpendicular to this
                    and the length axis, you see the trapezoidal "sides" of the wedges
        positions: Positions from center of timber in the width axis
        expand_mortise: Amount to fan out bottom of mortise to fit wedges
                        - 0 means straight sides (default)
                        - X means expand both sides of mortise bottom by X (total), the shoulder of the mortise remains the original size
    """
    shape: WedgeShape
    depth: Numeric
    width_axis: Direction3D
    positions: List[Numeric]
    expand_mortise: Numeric = scalar(0)


# ============================================================================
# Mortise and Tenon Joint Construction Functions
# ============================================================================


def cut_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,

    mortise_shoulder_distance_from_centerline: Numeric = scalar(0),

    tenon_position: Optional[V2] = None,
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,

    # TODO rename this parameter, and also assert that mortise_depth is None if this is true
    crop_tenon_to_mortise_orientation_on_angled_joints: bool = False,
    use_round_tenon: bool = False,
) -> Joint:
    """
    Creates a mortise and tenon joint with full control over all parameters.

    This is the generic implementation used by all specialized variants
    (`cut_mortise_and_tenon_joint_on_plane_aligned_timbers`, `cut_mortise_and_tenon_joint_on_face_aligned_timbers`).
    Prefer those variants for common cases.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length: Length of the tenon extending from the mortise entry face. For angled
            joints, set this slightly longer than expected to ensure full penetration.
        mortise_depth: Depth of the mortise (None = through mortise). 
            Measures along the tenon axis if crop_tenon_to_mortise_orientation_on_angled_joints is False; along the mortise face axis if True.
        mortise_shoulder_distance_from_centerline: Signed distance from the mortise
            centerline to the shoulder plane, measured within the mortise cross-section
            in the direction toward the tenon centerline. 0 = shoulder at the mortise
            centerline. Positive pushes the shoulder toward the tenon.
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional). Note: peg
            distance_from_shoulder is measured along the tenon axis, while
            distance_from_centerline is measured along the mortise axis — this makes
            positioning pegs on angled braces easier.
        crop_tenon_to_mortise_orientation_on_angled_joints: If True, the tenon is cropped
            so its depth along the mortise face axis equals mortise_depth and its tip is
            trimmed to the mortise hole boundary. If False, mortise depth is measured along
            the tenon axis from the shoulder.
        use_round_tenon: If True, creates a round (cylindrical) tenon and mortise instead of
            rectangular. When True, tenon_size[0] and tenon_size[1] must be equal (no ovals),
            and peg_parameters must be None. Default is False.

    Returns:
        Joint object containing the two CutTimbers and any accessories, all in global space.
    """
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    # TODO fix relief, not sure why it broke again..
    warn_if_arrangement_timbers_imperfect(arrangement)

    # Default tenon_position to centered (0, 0)
    if tenon_position is None:
        tenon_position = Matrix([scalar(0), scalar(0)])

    # Validation for round tenon mode
    if use_round_tenon:
        require_check(
            None if tenon_size[0] == tenon_size[1] else "Round tenon requires tenon_size[0] == tenon_size[1]"
        )
        require_check(
            None if peg_parameters is None else "Round tenon does not support pegs (peg_parameters must be None)"
        )

    # TODO default mortise depth if mortise_depth is None

    # -------------------------------------------------------------------------
    # Step 3: Shoulder plane from centerline toward tenon
    # -------------------------------------------------------------------------
    shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
        arrangement, mortise_shoulder_distance_from_centerline
    )
    shoulder_from_tenon_end_mark = mark_distance_from_end_along_centerline(shoulder_plane, tenon_timber, tenon_end)

    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    shoulder_point_global = shoulder_from_tenon_end_mark.locate().position

    tenon_right = tenon_timber.get_face_direction_global(TimberFace.RIGHT)
    tenon_front = tenon_timber.get_face_direction_global(TimberFace.FRONT)
    marking_origin_global = (
        shoulder_point_global
        + tenon_right * tenon_position[0]
        + tenon_front * tenon_position[1]
    )

    # -------------------------------------------------------------------------
    # Step 4: Define marking_space (global Space at shoulder, toward tenon end)
    # -------------------------------------------------------------------------
    tenon_orientation = compute_timber_orientation(
        normalize_vector(tenon_end_direction), tenon_timber.get_width_direction_global()
    )
    tenon_base_transform = Transform(position=marking_origin_global, orientation=tenon_orientation)
    marking_space: Space = Space(transform=tenon_base_transform)

    # -------------------------------------------------------------------------
    # Step 5: Determine the angle between the mortise entry direction and tenon
    # -------------------------------------------------------------------------
    mortise_face_normal = shoulder_plane.normal
    cos_angle = safe_dot_product(
        normalize_vector(mortise_face_normal), normalize_vector(tenon_end_direction)
    )

    # -------------------------------------------------------------------------
    # Tenon prism (origin at marking_space) and shoulder half-space
    # -------------------------------------------------------------------------
    from sympy import Abs, sqrt

    # Back-extension from shoulder so prism fully contains tenon at oblique angles
    sin_angle_sq = scalar(1) - cos_angle * cos_angle
    sin_angle_safe = scalar(1, 10000) if safe_zero_test(sin_angle_sq) else sqrt(Abs(sin_angle_sq))
    back_extension = max(tenon_size[0], tenon_size[1]) / sin_angle_safe

    tenon_tip_name = "tenon_top" if tenon_end == TimberEnd.TOP else "tenon_bot"

    if use_round_tenon:
        # Round tenon: use cylinder with diameter = tenon_size[0]
        tenon_radius = tenon_size[0] / scalar(2)
        axis_direction_global = normalize_vector(tenon_end_direction)
        tenon_prism_global = Cylinder(
            axis_direction=axis_direction_global,
            radius=tenon_radius,
            position=marking_space.transform.position,
            start_distance=-back_extension,
            end_distance=tenon_length,
            label="tenon",
        )
    else:
        tenon_prism_global = RectangularPrism(
            size=tenon_size,
            transform=marking_space.transform,
            start_distance=-back_extension,
            end_distance=tenon_length,
            named_features=[
                ("tenon_right", PrismFace.RIGHT),
                ("tenon_left", PrismFace.LEFT),
                ("tenon_front", PrismFace.FRONT),
                ("tenon_back", PrismFace.BACK),
                (tenon_tip_name, PrismFace.TOP),
            ],
            label="tenon",
        )

    tenon_prism_cropping_csgs: Optional[List[CutCSG]] = None
    do_cropping = crop_tenon_to_mortise_orientation_on_angled_joints and not zero_test(cos_angle)
    if do_cropping:
        # Compute mortise_face locally — cropping is only used for plane-aligned timbers
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        mortise_face_direction = mortise_timber.get_face_direction_global(mortise_face)

        mortise_oblique_end = mortise_timber.get_closest_oriented_end_face_from_global_direction(tenon_end_direction)
        joint_angle_axis_face = tenon_timber.get_closest_oriented_long_face_from_global_direction(mortise_timber.get_face_direction_global(mortise_oblique_end))
        joint_angle_axis_index = tenon_timber.get_size_index_in_long_face_normal_axis(joint_angle_axis_face)

        mortise_hole_length_oblique_direction = mortise_timber.get_face_direction_global(mortise_oblique_end)
        end_crop_distance = tenon_size[joint_angle_axis_index] / sin_angle_safe / scalar(2)

        # Crop 1: far end of prism perpendicular to mortise face
        mortise_hole_end_crop_global = HalfSpace(
            normal=mortise_hole_length_oblique_direction,
            offset=end_crop_distance + safe_dot_product(mortise_hole_length_oblique_direction, shoulder_point_global),
        )

        # Crop 2: depth of tenon — plane parallel to the mortise face surface,
        # mortise_depth measured from the face inward.
        mortise_depth_crop_global = HalfSpace(
            normal=-mortise_face_direction,
            offset=mortise_depth - safe_dot_product(mortise_face_direction, get_center_point_on_face_global(mortise_face, mortise_timber)),
        )

        tenon_prism_cropping_csgs = [mortise_hole_end_crop_global, mortise_depth_crop_global]

    # Shoulder half-space: plane through centerline ∩ shoulder (marking origin), normal = shoulder plane normal
    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
        label="shoulder",
    )

    tenon_prism_cropped = (
        tenon_prism_global
        if tenon_prism_cropping_csgs is None
        else Difference(base=tenon_prism_global, subtract=tenon_prism_cropping_csgs)
    )

    # Convert from global to tenon timber local (orig_timber=None => CSG is in global space)
    tenon_prism_local = adopt_csg(None, tenon_timber.transform, tenon_prism_cropped)
    shoulder_half_space_local = adopt_csg(None, tenon_timber.transform, shoulder_half_space_global)

    # -------------------------------------------------------------------------
    # mortise hole
    # -------------------------------------------------------------------------

    mortise_hole_prism_global = None

    if do_cropping:
        if use_round_tenon:
            # Round mortise hole at an angle: use cylinder
            mortise_radius = tenon_size[0] / scalar(2)
            axis_direction_global = normalize_vector(-mortise_face_normal)
            mortise_hole_prism_global = Cylinder(
                axis_direction=axis_direction_global,
                radius=mortise_radius,
                position=marking_space.transform.position,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label="mortise_hole",
            )
        else:
            mortise_hole_size = create_v2(0,0)
            mortise_hole_size[1] = tenon_size[joint_angle_axis_index] / sin_angle_safe
            opp_index = 1 if joint_angle_axis_index == 0 else 0
            mortise_hole_size[0] = tenon_size[opp_index]

            mortise_hole_orientation = Orientation.from_z_and_y(
                z_direction=-mortise_face_normal,
                y_direction=mortise_hole_length_oblique_direction,
            )

            mortise_hole_transform = Transform(
                position=marking_space.transform.position,
                orientation=mortise_hole_orientation,
            )

            mortise_hole_prism_global = RectangularPrism(
                size=mortise_hole_size,
                transform=mortise_hole_transform,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label="mortise_hole",
            )
    else:
        if use_round_tenon:
            # Round mortise hole: use cylinder with same diameter as tenon
            mortise_radius = tenon_size[0] / scalar(2)
            axis_direction_global = normalize_vector(-mortise_face_normal)
            mortise_hole_prism_global = Cylinder(
                axis_direction=axis_direction_global,
                radius=mortise_radius,
                position=marking_space.transform.position,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label="mortise_hole",
            )
        else:
            mortise_hole_prism_global = RectangularPrism(
                size=tenon_size,
                transform=marking_space.transform,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label="mortise_hole",
            )

    # -------------------------------------------------------------------------
    # shoulder notch on mortise timber and matching relief on tenon timber
    # (when shoulder is inset from the mortise entry face)
    # -------------------------------------------------------------------------

    from sympy import pi as _pi

    relief_geom = chop_relief_for_butt_joint_arrangement(
        arrangement,
        mortise_shoulder_distance_from_centerline,
        # pass pi/2 so the relief angle naturally follows the butt approach angle
        notch_wall_min_relief_cut_angle=_pi / scalar(2),
    )

    # -------------------------------------------------------------------------
    # make the final cut CSGs
    # -------------------------------------------------------------------------

    tenon_cut_csg = Difference(
        base=shoulder_half_space_local,
        subtract=[tenon_prism_local],
    )

    mortise_hole_prism_local = adopt_csg(None, mortise_timber.transform, mortise_hole_prism_global)

    if relief_geom is not None:
        mortise_negative_csg = CSGUnion(
            children=[mortise_hole_prism_local, relief_geom.receiving_timber_notch_negative_CSG]
        )
    else:
        mortise_negative_csg = mortise_hole_prism_local

    mortise_cut = Cutting(
        timber=mortise_timber,
        negative_csg=mortise_negative_csg,
        label="mortise_and_tenon",
    )

    tenon_length_direction_global = tenon_timber.get_face_direction_global(tenon_end)
    tip_position_global = marking_space.transform.position + tenon_length_direction_global * max(tenon_length, max(tenon_size[0], tenon_size[1])/cos_angle)
    tip_position_local = tenon_timber.transform.global_to_local(tip_position_global)
    tip_z_local = tip_position_local[2]

    tenon_cut = Cutting(
        timber=tenon_timber,
        maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.BOTTOM else None,
        negative_csg=tenon_cut_csg,
        label="mortise_and_tenon",
    )

    joint_accessories = {}
    if peg_parameters is not None:
        peg_results = compute_peg_positions(
            arrangement=arrangement,
            shoulder_plane=shoulder_plane,
            peg_parameters=peg_parameters,
            tenon_position=tenon_position,
        )

        peg_size = peg_parameters.size
        peg_holes_in_tenon_local = []
        peg_holes_in_mortise_local = []

        def _build_peg_hole_global(center_global: V3, orientation_global: Orientation, depth: Numeric, label: str) -> CutCSG:
            if peg_parameters.shape == PegShape.ROUND:
                # Cylinder axis is the Z column of the orientation in global space.
                axis_direction_global = orientation_global.matrix * create_v3(scalar(0), scalar(0), scalar(1))
                return Cylinder(
                    axis_direction=axis_direction_global,
                    radius=peg_size / scalar(2),
                    position=center_global,
                    start_distance=scalar(0),
                    end_distance=depth,
                    label=label,
                )
            return RectangularPrism(
                size=Matrix([peg_size, peg_size]),
                transform=Transform(
                    position=center_global,
                    orientation=orientation_global,
                ),
                start_distance=scalar(0),
                end_distance=depth,
                label=label,
            )

        for peg_idx, peg_result in enumerate(peg_results):
            # Create peg hole CSG in tenon local space (using offset position for draw-bore tightening)
            peg_hole_tenon_global = _build_peg_hole_global(
                peg_result.tenon_face_position_with_offset_global,
                peg_result.orientation_global,
                peg_result.peg_depth,
                f"peg_hole_{peg_idx}",
            )
            peg_holes_in_tenon_local.append(adopt_csg(None, tenon_timber.transform, peg_hole_tenon_global))

            # Create peg hole CSG in mortise local space
            peg_hole_mortise_global = _build_peg_hole_global(
                peg_result.mortise_entry_position_global,
                peg_result.orientation_global,
                peg_result.peg_depth,
                f"peg_hole_{peg_idx}",
            )
            peg_holes_in_mortise_local.append(adopt_csg(None, mortise_timber.transform, peg_hole_mortise_global))

            # Create Peg accessory in global space (positioned at mortise entry)
            # Assembly: the peg backs out along its drill axis; it locks the
            # joint, so it pops (suborder 0) before the tenon slides (suborder 1).
            peg_drill_direction_global = peg_result.orientation_global.matrix * create_v3(scalar(0), scalar(0), scalar(1))
            peg_accessory = Peg(
                transform=Transform(
                    position=peg_result.mortise_entry_position_global,
                    orientation=peg_result.orientation_global,
                ),
                size=peg_size,
                shape=peg_parameters.shape,
                forward_length=peg_result.peg_depth,
                stickout_length=peg_result.stickout_length,
                assembly_freedom=AssemblyFreedom.translation(
                    -peg_drill_direction_global,
                    freed_after=peg_result.peg_depth + peg_result.stickout_length,
                ),
                assembly_ordering=Ordering(0, 0),
            )
            joint_accessories[f"peg_{peg_idx}"] = peg_accessory

        if peg_holes_in_tenon_local:
            tenon_cut_with_pegs_csg = CSGUnion(children=[tenon_cut_csg] + peg_holes_in_tenon_local)
            tenon_cut = Cutting(
                timber=tenon_timber,
                maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.TOP else None,
                maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.BOTTOM else None,
                negative_csg=tenon_cut_with_pegs_csg,
                label="mortise_and_tenon",
            )
        if peg_holes_in_mortise_local:
            mortise_cut_with_pegs_csg = CSGUnion(children=[mortise_negative_csg] + peg_holes_in_mortise_local)
            mortise_cut = Cutting(
                timber=mortise_timber,
                negative_csg=mortise_cut_with_pegs_csg,
                label="mortise_and_tenon",
            )

    # Assembly: the tenon backs out of the mortise along the tenon axis; the
    # mortise timber's view of the same separation is the inverse direction.
    # When pegs lock the joint they pop first (suborder 0), so the timbers
    # slide at suborder 1.
    timber_suborder = 1 if joint_accessories else 0
    tenon_cut_timber = replace(
        tenon_cut,
        assembly_freedom=AssemblyFreedom.translation(-tenon_length_direction_global, freed_after=tenon_length),
        assembly_ordering=Ordering(0, timber_suborder),
    )
    mortise_cut_timber = replace(
        mortise_cut,
        assembly_freedom=AssemblyFreedom.translation(tenon_length_direction_global, freed_after=tenon_length),
        assembly_ordering=Ordering(0, timber_suborder),
    )

    return Joint(
        cuttings={
            tenon_timber.ticket.path: tenon_cut_timber,
            mortise_timber.ticket.path: mortise_cut_timber,
        },
        ticket=JointTicket(joint_type="mortise_and_tenon"),
        jointAccessories=joint_accessories,
    )


def cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,
    crop_tenon_to_mortise_orientation_on_angled_joints = False,
    use_round_tenon: bool = False,
) -> Joint:
    """
    Creates a mortise and tenon joint for plane-aligned timbers.

    Plane-aligned timbers means both timbers lie in the same plane. The timbers may
    meet at any angle — use `cut_mortise_and_tenon_joint_on_face_aligned_timbers` for the standard 90-degree
    case.

    Like the generic `cut_mortise_and_tenon_joint`, but accepts `mortise_shoulder_inset`
    measured from the mortise entry face surface (the intuitive user-facing parameter),
    converting it internally to `mortise_shoulder_distance_from_centerline`.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must satisfy arrangement.check_plane_aligned().
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length: Length of the tenon extending from the mortise entry face. For angled
            joints, set this slightly longer than expected.
        mortise_depth: Depth of the mortise (None = through mortise).
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional).
        crop_tenon_to_mortise_orientation_on_angled_joints: If True, the tenon tip is cropped
            to the mortise hole boundary. If False, mortise depth is measured along the tenon axis.

    Returns:
        Joint object containing the two CutTimbers and any accessories.

    Raises:
        CheckFailure: If the arrangement is not plane-aligned.
    """

    require_check(arrangement.check_plane_aligned())

    # -------------------------------------------------------------------------
    # Step 2: Determine which face of the mortise timber the tenon enters from
    # -------------------------------------------------------------------------
    tenon_end_direction = arrangement.butt_timber.get_face_direction_global(
        TimberFace.TOP if arrangement.butt_timber_end == TimberEnd.TOP else TimberFace.BOTTOM
    )
    mortise_face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()

    mortise_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=arrangement.receiving_timber,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline=mortise_shoulder_distance_from_centerline,
        tenon_position=tenon_position,
        wedge_parameters=wedge_parameters,
        peg_parameters=peg_parameters,
        crop_tenon_to_mortise_orientation_on_angled_joints=crop_tenon_to_mortise_orientation_on_angled_joints,
        use_round_tenon=use_round_tenon,
    )



def cut_mortise_and_tenon_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,
    use_round_tenon: bool = False,
) -> Joint:
    """
    Creates a mortise and tenon joint for face-aligned orthogonal timbers.

    Face-aligned orthogonal timbers means both timbers are face-aligned
    (orientations related by 90-degree rotations) and their length axes are perpendicular.
    This is the standard configuration for timber-frame T-joints and corners. For angled
    joints in the same plane, use `cut_mortise_and_tenon_joint_on_plane_aligned_timbers`.

    This is a stricter variant of `cut_mortise_and_tenon_joint_on_plane_aligned_timbers` that enforces
    perpendicularity and does not support crop_tenon_to_mortise_orientation_on_angled_joints.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must satisfy arrangement.check_face_aligned_and_orthogonal().
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length: Length of the tenon extending from the mortise entry face.
        mortise_depth: Depth of the mortise (None = through mortise).
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional).

    Returns:
        Joint object containing the two CutTimbers and any accessories.

    Raises:
        CheckFailure: If the arrangement is not face-aligned and orthogonal.
    """

    require_check(arrangement.check_face_aligned_and_orthogonal())

    return cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        mortise_shoulder_inset=mortise_shoulder_inset,
        wedge_parameters=wedge_parameters,
        peg_parameters=peg_parameters,
        use_round_tenon=use_round_tenon,
    )

def cut_round_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_distance_from_centerline: Numeric = scalar(0),
) -> Joint:
    """
    Creates a simplified round mortise and tenon joint with any orientation.

    This is a convenience wrapper around `cut_mortise_and_tenon_joint` for
    common round tenon use cases with a single diameter parameter instead of V2 tenon_size.
    Allows any timber arrangement orientation.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
        diameter: Diameter of the round tenon and mortise.
        tenon_length: Length of the tenon extending from the mortise entry face.
        mortise_depth: Depth of the mortise (None = through mortise).
        mortise_shoulder_distance_from_centerline: Signed distance from the mortise centerline
            to the shoulder plane. 0 = shoulder at centerline.

    Returns:
        Joint object containing the two CutTimbers, all in global space.
    """
    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([diameter, diameter]),
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline=mortise_shoulder_distance_from_centerline,
        use_round_tenon=True,
    )


def cut_round_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
) -> Joint:
    """
    Creates a simplified round mortise and tenon joint for plane-aligned timbers.

    This is a convenience wrapper around `cut_mortise_and_tenon_joint` for
    round tenon use cases with a single diameter parameter.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
                     Must satisfy arrangement.check_plane_aligned().
        diameter: Diameter of the round tenon and mortise.
        tenon_length: Length of the tenon extending from the mortise entry face.
        mortise_depth: Depth of the mortise (None = through mortise).
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.

    Returns:
        Joint object containing the two CutTimbers, all in global space.
    """
    require_check(arrangement.check_plane_aligned())

    # -------------------------------------------------------------------------
    # Step 2: Determine which face of the mortise timber the tenon enters from
    # -------------------------------------------------------------------------
    tenon_end_direction = arrangement.butt_timber.get_face_direction_global(
        TimberFace.TOP if arrangement.butt_timber_end == TimberEnd.TOP else TimberFace.BOTTOM
    )
    mortise_face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()

    mortise_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=arrangement.receiving_timber,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([diameter, diameter]),
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline=mortise_shoulder_distance_from_centerline,
        use_round_tenon=True,
    )


# ============================================================================
# Wedged Half-Dovetail Mortise and Tenon Joint
# ============================================================================

def cut_wedged_half_dovetail_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    dovetail_top_side_on_butt_timber: TimberLongFace,
    tenon_size: V2,
    tenon_depth: Numeric,
    dovetail_depth: Numeric,
    tenon_lateral_offset: Numeric = scalar(0),
    receiving_timber_mortise_extra_depth: Numeric = scalar(0),
    mortise_shoulder_inset: Numeric = scalar(0),
    wedge_accessory_parameters: Optional[DovetailTenonWedgeAccessoryParameters] = None,
) -> Joint:
    """
    Create a half-dovetail mortise-and-tenon joint (with an optional wedge accessory).

    Built on top of `dovetail_tenon_geometry`. The "top" of the dovetail is flush with
    `dovetail_top_side_on_butt_timber`; the opposite side slopes outward by `dovetail_depth`
    over `tenon_depth` to give the joint its mechanical pull-out resistance.

    Args:
        arrangement: Butt joint arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must be face-aligned and orthogonal.
        dovetail_top_side_on_butt_timber: Which face of the butt timber the dovetail's flat
            "top" is flush with. The opposite face is the sloped side.
        tenon_size: Cross-section of the tenon (X = butt RIGHT axis, Y = butt TOP axis).
        tenon_depth: Depth of the tenon into the receiving timber, measured from the shoulder.
        dovetail_depth: How far the sloped side of the dovetail kicks out over `tenon_depth`.
        tenon_lateral_offset: Offset of the tenon along the lateral direction (perpendicular
            to both length and top-to-bottom). 0 = centered on the butt timber.
        receiving_timber_mortise_extra_depth: Extra mortise depth in the receiving timber past
            the tenon tip.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the entry face inward. 0 = shoulder flush with the
            entry face (the default). Positive pushes the shoulder deeper into the receiving
            timber.
        wedge_accessory_parameters: If provided, a wedge accessory is added on the
            `dovetail_top_side_on_butt_timber` side of the tenon and a matching slot is cut
            into the receiving timber.

    Returns:
        Joint object with cuts on both timbers and (optionally) a "wedge" accessory.
    """
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    # Convert the user-facing `mortise_shoulder_inset` (measured inward from the mortise
    # entry face) into the signed-from-centerline distance that `compute_butt_joint_shoulder`
    # expects. This mirrors how `cut_mortise_and_tenon_joint_on_plane_aligned_timbers`
    # and `cut_mortise_and_tenon_joint_on_face_aligned_timbers` handle the inset.
    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    mortise_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=mortise_timber,
    )

    # The shoulder marking space's up_direction only orients the marking frame; the geometry
    # function derives its own frame from `dovetail_top_side_on_butt_timber`. Pick the butt
    # timber's height direction (a stable, non-parallel choice for any orthogonal arrangement).
    up_direction = tenon_timber.get_height_direction_global()

    shoulder_result = compute_butt_joint_shoulder(
        arrangement=arrangement,
        distance_from_centerline=mortise_shoulder_distance_from_centerline,
        up_direction=up_direction,
    )

    geo = dovetail_tenon_geometry(
        arrangement=arrangement,
        shoulder_result=shoulder_result,
        dovetail_top_side_on_butt_timber=dovetail_top_side_on_butt_timber,
        tenon_size=tenon_size,
        tenon_depth=tenon_depth,
        dovetail_depth=dovetail_depth,
        tenon_lateral_offset=tenon_lateral_offset,
        receiving_timber_mortise_extra_depth=receiving_timber_mortise_extra_depth,
        wedge_accessory_parameters=wedge_accessory_parameters,
    )

    # The CSGs from dovetail_tenon_geometry are in global space. Adopt them into each
    # timber's local frame for cutting.
    tenon_negative_local = adopt_csg(None, tenon_timber.transform, geo.tenon_negative_csg)
    mortise_negative_local = adopt_csg(None, mortise_timber.transform, geo.mortise_negative_csg)

    # Shoulder notch on the receiving timber (and matching relief on the butting
    # timber) when the shoulder is inset from the entry face. For face-aligned
    # orthogonal arrangements the approach angle is pi/2 (no relief walls).
    relief_geom = chop_relief_for_butt_joint_arrangement(
        arrangement,
        mortise_shoulder_distance_from_centerline,
        notch_wall_min_relief_cut_angle=degrees(45),
    )
    if relief_geom is not None:
        mortise_negative_local = CSGUnion(
            children=[
                mortise_negative_local,
                relief_geom.receiving_timber_notch_negative_CSG,
            ]
        )
        if relief_geom.butting_timber_relief_negative_CSG is not None:
            # Add the relief volume to the tenon negative CSG so the butting timber
            # gets carved away against the receiving timber's notch walls.
            tenon_negative_local = CSGUnion(
                children=[
                    tenon_negative_local,
                    relief_geom.butting_timber_relief_negative_CSG,
                ]
            )

    tenon_tip_position_global = (
        shoulder_result.marking_space.transform.position
        + shoulder_result.butt_direction * tenon_depth
    )
    tip_position_local = tenon_timber.transform.global_to_local(tenon_tip_position_global)
    tip_z_local = tip_position_local[2]

    # Assembly: the tenon backs out of the mortise along the butt axis; the
    # wedge (if any) locks it and pops first, so the timbers slide at
    # suborder 1 when a wedge is present.
    timber_suborder = 1 if geo.wedge_accessory_csg is not None else 0
    tenon_cut = Cutting(
        timber=tenon_timber,
        maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.BOTTOM else None,
        negative_csg=tenon_negative_local,
        label="wedged_half_dovetail_mortise_and_tenon",
        assembly_freedom=AssemblyFreedom.translation(-shoulder_result.butt_direction, freed_after=tenon_depth),
        assembly_ordering=Ordering(0, timber_suborder),
    )

    mortise_cut = Cutting(
        timber=mortise_timber,
        negative_csg=mortise_negative_local,
        label="wedged_half_dovetail_mortise_and_tenon",
        assembly_freedom=AssemblyFreedom.translation(shoulder_result.butt_direction, freed_after=tenon_depth),
        assembly_ordering=Ordering(0, timber_suborder),
    )

    joint_accessories = {}
    if geo.wedge_accessory_csg is not None:
        joint_accessories["wedge"] = geo.wedge_accessory_csg

    return Joint(
        cuttings={
            tenon_timber.ticket.path: tenon_cut,
            mortise_timber.ticket.path: mortise_cut,
        },
        ticket=JointTicket(joint_type="wedged_half_dovetail_mortise_and_tenon"),
        jointAccessories=joint_accessories,
    )


# ============================================================================
# Japanese butt joints (moved from japanese_joints.py)
# ============================================================================


def cut_dropin_dovetail_butt_joint(
    arrangement: ButtJointTimberArrangement,
    receiving_timber_shoulder_inset: Numeric,
    dovetail_length: Numeric,
    dovetail_small_width: Numeric,
    dovetail_large_width: Numeric,
    dovetail_lateral_offset: Numeric = scalar(0),
    dovetail_depth: Optional[Numeric] = None
) -> Joint:
    """
    Creates a dovetail butt joint (蟻継ぎ / Ari Tsugi) between two orthogonal timbers.

    This is a traditional Japanese timber joint where a dovetail-shaped tenon on one timber
    fits into a matching dovetail socket on another timber. The dovetail shape provides
    mechanical resistance to pulling apart.

    Args:
        arrangement: Butt joint arrangement where butt_timber is the dovetail timber,
            receiving_timber receives the dovetail socket, butt_timber_end is the cut end,
            and front_face_on_butt_timber is the face where the dovetail profile is visible.
        receiving_timber_shoulder_inset: Distance to inset the shoulder notch on the receiving timber
        dovetail_length: Length of the dovetail tenon
        dovetail_small_width: Width of the narrow end of the dovetail (at the tip)
        dovetail_large_width: Width of the wide end of the dovetail (at the base)
        dovetail_lateral_offset: Lateral offset of the dovetail from center (default 0)
        dovetail_depth: Depth of the dovetail cut. If None, defaults to half the timber dimension

    Returns:
        Joint object containing the two CutTimbers with the dovetail cuts applied

    Raises:
        ValueError: If the parameters are invalid or the timbers are not orthogonal

    Notes:
        - The dovetail provides mechanical resistance to pulling apart
        - Timbers must be orthogonal (at 90 degrees) for this joint
        - No lap is used in this joint (unlike the lapped gooseneck joint)
    """

    require_check(arrangement.check_face_aligned_and_orthogonal())
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_butt_timber is not None, (
        "arrangement.front_face_on_butt_timber must be set to determine the dovetail face"
    )
    dovetail_timber = arrangement.butt_timber
    receiving_timber = arrangement.receiving_timber
    dovetail_timber_end = arrangement.butt_timber_end
    dovetail_timber_face = arrangement.front_face_on_butt_timber

    # ========================================================================
    # Parameter validation
    # ========================================================================

    # Validate positive dimensions
    if dovetail_length <= 0:
        raise ValueError(f"dovetail_length must be positive, got {dovetail_length}")
    if dovetail_small_width <= 0:
        raise ValueError(f"dovetail_small_width must be positive, got {dovetail_small_width}")
    if dovetail_large_width <= 0:
        raise ValueError(f"dovetail_large_width must be positive, got {dovetail_large_width}")
    if receiving_timber_shoulder_inset < 0:
        raise ValueError(f"receiving_timber_shoulder_inset must be non-negative, got {receiving_timber_shoulder_inset}")

    # Validate that large_width > small_width (dovetail taper requirement)
    if dovetail_large_width <= dovetail_small_width:
        raise ValueError(
            f"dovetail_large_width ({dovetail_large_width}) must be greater than "
            f"dovetail_small_width ({dovetail_small_width})"
        )

    # Validate dovetail_depth if provided
    if dovetail_depth is not None and dovetail_depth <= 0:
        raise ValueError(f"dovetail_depth must be positive if provided, got {dovetail_depth}")

    # assert that dovetail_timber_face is perpendicular to receiving_timber.get_length_direction_global()
    if are_vectors_parallel(dovetail_timber.get_face_direction_global(dovetail_timber_face), receiving_timber.get_length_direction_global()):
        raise ValueError(
            "Dovetail timber face must be perpendicular to receiving timber length direction for dovetail butt joint. "
            "The face should be oriented such that the dovetail profile is visible when looking along the receiving timber. "
            "Try rotating the dovetail face by 90 degrees. "
            f"Got dovetail_timber_face direction: {dovetail_timber.get_face_direction_global(dovetail_timber_face).T}, "
            f"receiving_timber length_direction: {receiving_timber.get_length_direction_global().T}"
        )

    # ========================================================================
    # Calculate default depth if not provided
    # ========================================================================

    if dovetail_depth is None:
        # Default: half the timber dimension perpendicular to the dovetail face
        dovetail_depth = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.to.face()) / scalar(2)

    # ========================================================================
    # Create the dovetail profile (simple trapezoid)
    # TODO move into separate function
    # ========================================================================

    # Dovetail profile in 2D (X = lateral, Y = along timber length from end)
    # Y=0 is at the timber end, Y increases going into the timber
    # Small width at Y=0 (tip), large width at Y=dovetail_length (base)

    dovetail_profile = [
        # Tip (narrow end at the timber end)
        Matrix([-dovetail_small_width / scalar(2) + dovetail_lateral_offset, 0]),
        Matrix([dovetail_small_width / scalar(2) + dovetail_lateral_offset, 0]),
        # Base (wide end)
        Matrix([dovetail_large_width / scalar(2) + dovetail_lateral_offset, dovetail_length]),
        Matrix([-dovetail_large_width / scalar(2) + dovetail_lateral_offset, dovetail_length]),
    ]


    # ========================================================================
    # create the marking transform
    # it is on the centerline of the dovetail face where it intersects the inset shoulder of the mortise timber
    # ========================================================================

    receiving_timber_shoulder_face = receiving_timber.get_closest_oriented_face_from_global_direction(-dovetail_timber.get_face_direction_global(dovetail_timber_end.to.face()))
    face_plane = scribe_face_plane_onto_centerline(
        face=receiving_timber_shoulder_face,
        face_timber=receiving_timber
    )
    marking = mark_distance_from_end_along_centerline(face_plane, dovetail_timber, dovetail_timber_end)
    shoulder_distance_from_end = marking.distance - receiving_timber_shoulder_inset

    offset_to_dovetail_face = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face) / scalar(2) * dovetail_timber.get_face_direction_global(dovetail_timber_face)

    marking_transform_position = dovetail_timber.get_bottom_position_global() + shoulder_distance_from_end * dovetail_timber.get_length_direction_global() + offset_to_dovetail_face
    marking_transform_orientation = orientation_pointing_towards_face_sitting_on_face(towards_face=dovetail_timber_end.to.face(), sitting_face=dovetail_timber_face.to.face())
    dovetail_timber_marking_transform = Transform(position=marking_transform_position, orientation=marking_transform_orientation)


    # ========================================================================
    # Cut dovetail shape into dovetail timber
    # ========================================================================

    # Create the dovetail profile CSG using chop_profile_on_timber_face
    # This creates the profile extrusion
    dovetail_profile_csg = chop_profile_on_timber_face(
        timber=dovetail_timber,
        end=dovetail_timber_end,
        face=dovetail_timber_face.to.face(),
        profile=dovetail_profile,
        depth=dovetail_depth,
        profile_y_offset_from_end=shoulder_distance_from_end
    )

    # dovetail housing prism
    dovetail_housing_prism = chop_timber_end_with_prism(
        timber=dovetail_timber,
        end=dovetail_timber_end,
        distance_from_end_to_cut=shoulder_distance_from_end
    )

    # ========================================================================
    # Cut shoulder notch on receiving timber
    # ========================================================================

    # Calculate where along the receiving timber the shoulder should be
    dovetail_centerline = scribe_centerline_onto_centerline(dovetail_timber)
    marking_receiving = mark_distance_from_end_along_centerline(dovetail_centerline, receiving_timber)
    receiving_timber_notch_center = marking_receiving.distance

    # Create shoulder notch if inset is specified
    if receiving_timber_shoulder_inset > 0:
        # Notch dimensions match the dovetail timber's cross-section at the housing
        # Width is the length of the housing (shoulder_distance_from_end on dovetail timber)
        notch_width = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.rotate_right().to.face())

        # Depth is the amount of inset
        notch_depth = receiving_timber_shoulder_inset

        receiving_timber_shoulder_notch = chop_shoulder_notch_on_timber_face(
            timber=receiving_timber,
            notch_face=receiving_timber_shoulder_face,
            distance_along_timber=receiving_timber_notch_center,
            notch_width=notch_width,
            notch_depth=notch_depth
        )

    # ========================================================================
    # Adopt the dovetail socket CSG to the receiving timber
    # ========================================================================

    # Transform the dovetail profile CSG from dovetail_timber coordinates to receiving_timber coordinates
    dovetail_socket_csg = adopt_csg(dovetail_timber.transform, receiving_timber.transform, dovetail_profile_csg)

    # ========================================================================
    # Create Cut objects for each timber
    # ========================================================================

    # Create a redundant end cut for the dovetail timber
    # The end cut should be at the end of the dovetail profile
    # The dovetail extends from the shoulder (at shoulder_distance_from_end) toward the end for dovetail_length

    if dovetail_timber_end == TimberEnd.TOP:
        # For TOP end: shoulder is at (timber.length - shoulder_distance_from_end)
        # Dovetail extends toward +Z for dovetail_length
        dovetail_end_local_z = dovetail_timber.length - shoulder_distance_from_end + dovetail_length
        dovetail_timber_end_cut = HalfSpace(normal=create_v3(0, 0, 1), offset=dovetail_end_local_z)
    else:  # BOTTOM
        # For BOTTOM end: shoulder is at shoulder_distance_from_end
        # Dovetail extends toward -Z for dovetail_length
        dovetail_end_local_z = shoulder_distance_from_end - dovetail_length
        dovetail_timber_end_cut = HalfSpace(normal=create_v3(0, 0, -1), offset=-dovetail_end_local_z)

    # Assembly: the dovetail taper blocks axial pull, so the ONLY escape is
    # lifting back out of the socket along the profile-face normal — a strictly
    # unidirectional single DOF, freed after the drop-in depth.
    dovetail_lift_direction_global = dovetail_timber.get_face_direction_global(dovetail_timber_face.to.face())
    dovetail_timber_cut_obj = Cutting(
        timber=dovetail_timber,
        maybe_top_end_cut_distance_from_bottom=dovetail_end_local_z if dovetail_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=dovetail_end_local_z if dovetail_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=Difference(dovetail_housing_prism, [dovetail_profile_csg]),
        assembly_freedom=AssemblyFreedom.translation(dovetail_lift_direction_global, freed_after=dovetail_depth),
    )

    # Combine shoulder notch and dovetail socket if shoulder inset is specified
    if receiving_timber_shoulder_inset > 0:
        receiving_timber_negative_csg = CSGUnion([receiving_timber_shoulder_notch, dovetail_socket_csg])
    else:
        receiving_timber_negative_csg = dovetail_socket_csg

    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        negative_csg=receiving_timber_negative_csg,
        assembly_freedom=AssemblyFreedom.translation(-dovetail_lift_direction_global, freed_after=dovetail_depth),
    )

    return Joint(
        cuttings={
            dovetail_timber.ticket.path: dovetail_timber_cut_obj,
            receiving_timber.ticket.path: receiving_timber_cut_obj
        },
        ticket=JointTicket(joint_type="housed_dovetail_butt"),
        jointAccessories={},
    )


# ============================================================================
# Aliases for Japanese joint functions
# ============================================================================

cut_蟻仕口 = cut_dropin_dovetail_butt_joint
cut_ari_shiguchi = cut_dropin_dovetail_butt_joint
