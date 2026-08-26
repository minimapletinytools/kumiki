"""
Kumiki - Butt joint construction functions
Contains plain butt, tongue-and-fork butt, and dropin dovetail/housed butt joint implementations.
Mortise-and-tenon joints live in mortise_and_tenon_joints.py.
"""

from __future__ import annotations  # Enable deferred annotation evaluation

import warnings
from dataclasses import replace
from functools import wraps

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *
from .shavings.relief import warn_if_arrangement_timbers_imperfect, chop_shoulder_notch_on_timber_face, ShoulderReliefCSGGeometry, chop_relief_for_butt_joint_arrangement, chop_shoulder_notch_aligned_with_timber, does_shoulder_plane_need_notching, ButtJointScribeReliefConfig, chop_scribe_relief_and_apply_for_butt_joint_arrangement
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
    locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face,
    resolve_parallel_shoulder_face,
    PegPositionResult,
    PegPositionSpace,
    SimplePegParameters,
    compute_peg_positions,
    compute_butt_joint_shoulder,
    dovetail_tenon_geometry,
    DovetailTenonGeometeryResult,
    DovetailTenonWedgeAccessoryParameters,
    tusk_tenon_geometry,
    TuskTenonGeometryResult,
)


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


def _apply_scribe_relief_if_configured(
    relief: Optional[ButtJointScribeReliefConfig],
    butt_cut: Cutting,
    receiving_cut: Cutting,
) -> tuple[Cutting, Cutting]:
    """
    Callsite-local wrapper around ``chop_scribe_relief_and_apply_for_butt_joint_arrangement``:
    passes ``butt_cut``/``receiving_cut`` through unchanged when ``relief`` is None, otherwise
    delegates to apply the configured scribe relief.
    """
    if relief is None:
        return butt_cut, receiving_cut
    return chop_scribe_relief_and_apply_for_butt_joint_arrangement(
        relief=relief,
        butt_cut=butt_cut,
        receiving_cut=receiving_cut,
    )


# ============================================================================
# Butt Joint Construction Functions
# ============================================================================


def cut_plain_butt_joint(
    arrangement: ButtJointTimberArrangement,
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the face of the receiving timber.

    The butt timber's end is trimmed along the plane of the best-matching long face of the
    receiving timber. The receiving timber otherwise isn't cut, aside from any scribe relief.

    Works for any non-parallel angle between the timbers, including oblique 3D angles.
    The cut plane follows the actual receiving face geometry rather than being perpendicular
    to the butt timber's axis, so the mating face is always flush.

    Args:
        arrangement: Butt joint arrangement with butt_timber, receiving_timber, butt_timber_end.
        relief: Scribe-relief configuration for imperfect timbers. Defaults to scribing the
            butt timber onto the receiving timber. Pass None to skip scribe relief entirely.

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

    cut_no_relief = Cutting(
        timber=butt_timber,
        maybe_top_end_cut_distance_from_bottom=end_cut_distance_from_bottom if butt_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=end_cut_distance_from_bottom if butt_end == TimberEnd.BOTTOM else None,
        negative_csg=end_cut,
        label=CutCSGLabel("butt_cross_cut"),
    )
    receiving_cut_no_relief = Cutting(timber=receiving_timber)

    cut, receiving_cut = _apply_scribe_relief_if_configured(
        relief=relief,
        butt_cut=cut_no_relief,
        receiving_cut=receiving_cut_no_relief,
    )

    # Assembly: a plain butt has no mechanical engagement, so it is free after
    # 0 travel. Disassembly code adds its own visual-separation padding on top
    # of freed_after, so no nominal travel is needed here.
    joint = Joint(
        cuttings={
            "receiving_timber": replace(
                receiving_cut,
                assembly_freedom=AssemblyFreedom.translation(butt_direction, freed_after=scalar(0)),
            ),
            "butt_timber": replace(
                cut,
                assembly_freedom=AssemblyFreedom.translation(-butt_direction, freed_after=scalar(0)),
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


# TODO DELETE ME
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


def cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = scalar(0),
    shoulder_inset: Numeric = scalar(0),
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Creates a plain tongue-and-fork butt joint.

    In this joint, the butt timber forms the fork (2 prongs with a central slot cut into it)
    and the receiving timber forms the tongue (material removed from both cheeks). The receiving
    (tongue) timber does **not** receive an end cut — it continues through the joint.

    Args:
        arrangement: Butt arrangement where butt_timber is the fork and
            receiving_timber is the tongue.
        tongue_thickness: Tongue thickness along the shared plane normal.
            If None, defaults to 1/3 of the receiving timber dimension in that axis.
        tongue_position: Offset of the tongue center from the receiving timber
            centerline along the shared plane normal. 0 means centered.
        shoulder_inset: Distance from the receiving timber entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        relief: Scribe-relief configuration for imperfect timbers. Defaults to scribing the
            fork (butt) timber onto the tongue (receiving) timber. Pass None to skip.

    Returns:
        Joint containing both cut timbers.

    Raises:
        AssertionError: If timbers are not plane aligned, are parallel, or
            tongue parameters are out of bounds.
    """

    error = arrangement.check_plane_aligned()
    assert error is None, error

    fork_timber = arrangement.butt_timber
    tongue_timber = arrangement.receiving_timber
    fork_end = arrangement.butt_timber_end

    warn_if_arrangement_timbers_imperfect(arrangement)

    assert not are_vectors_parallel(
        fork_timber.get_length_direction_global(),
        tongue_timber.get_length_direction_global(),
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

    fork_end_direction = fork_timber.get_face_direction_global(fork_end)

    # -------------------------------------------------------------------------
    # Shoulder plane (M&T pattern): compute on tongue (receiving) timber
    # -------------------------------------------------------------------------
    fork_entry_long_face = tongue_timber.get_closest_oriented_long_face_from_global_direction(-fork_end_direction)
    fork_shoulder_distance = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=shoulder_inset,
        mortise_face=fork_entry_long_face.to.face(),
        receiving_timber=tongue_timber,
    )

    shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
        arrangement, fork_shoulder_distance
    )
    shoulder_from_fork_end_mark = mark_distance_from_end_along_centerline(
        shoulder_plane, fork_timber, fork_end
    )
    shoulder_point_global = shoulder_from_fork_end_mark.locate().position

    # -------------------------------------------------------------------------
    # Marking space at shoulder (M&T pattern)
    # -------------------------------------------------------------------------
    marking_origin_global = shoulder_point_global + tongue_normal_direction * tongue_position

    fork_orientation_global = Orientation.from_z_and_y(
        z_direction=safe_normalize_vector(fork_end_direction),
        y_direction=safe_normalize_vector(tongue_normal_direction),
    )
    marking_space_transform = Transform(position=marking_origin_global, orientation=fork_orientation_global)
    marking_space = Space(transform=marking_space_transform)

    # Dimension of fork timber along marking space local x (receiving timber length axis)
    marking_space_x_dir = safe_transform_vector(marking_space.transform.orientation.matrix, create_v3(1, 0, 0))
    fork_width_along_tongue = fork_timber.get_size_in_direction_3d(marking_space_x_dir)

    # -------------------------------------------------------------------------
    # Fork slot depth and far face of tongue timber
    # -------------------------------------------------------------------------
    fork_far_face = fork_entry_long_face.to.face().get_opposite_face()
    fork_far_face_normal_global = tongue_timber.get_face_direction_global(fork_far_face)
    fork_far_face_point_global = get_center_point_on_face_global(fork_far_face, tongue_timber)

    fork_slot_depth = safe_dot_product(
        fork_far_face_point_global - shoulder_point_global,
        safe_normalize_vector(fork_end_direction),
    )
    assert safe_compare(fork_slot_depth, 0, Comparison.GT), \
        "Fork slot depth must be > 0; check timber arrangement and end selections"

    # Fork slot: bounded at the shoulder by shoulder_half_space so the slot shoulder matches the angle of the receiving timber face
    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, shoulder_point_global),
    )
    shoulder_half_space_local = adopt_csg(None, fork_timber.transform, shoulder_half_space_global)

    fork_slot_end_overshoot = max(tongue_timber.size[0], tongue_timber.size[1])
    fork_slot_back_extension = max(fork_timber.size[0], fork_timber.size[1]) * scalar(2)
    fork_max_cross = max(fork_timber.size[0], fork_timber.size[1]) * scalar(2)
    fork_slot_prism_global = RectangularPrism(
        size=create_v2(fork_max_cross, tongue_thickness),
        transform=marking_space.transform,
        start_distance=-fork_slot_back_extension,
        end_distance=fork_slot_depth + fork_slot_end_overshoot,
    )
    fork_slot_prism_local = adopt_csg(None, fork_timber.transform, fork_slot_prism_global)
    fork_slot_csg_local = Intersection(
        left=shoulder_half_space_local,
        right=fork_slot_prism_local,
    )

    fork_end_hs_normal_global = (
        fork_far_face_normal_global
        if safe_dot_product(fork_far_face_normal_global, fork_end_direction) > 0
        else -fork_far_face_normal_global
    )
    fork_end_cut_local_normal = safe_transform_vector(
        fork_timber.orientation.matrix.T, fork_end_hs_normal_global
    )
    fork_end_cut_local_offset = (
        safe_dot_product(fork_end_hs_normal_global, fork_far_face_point_global)
        - safe_dot_product(fork_end_hs_normal_global, fork_timber.get_bottom_position_global())
    )
    fork_end_cut = HalfSpace(normal=fork_end_cut_local_normal, offset=fork_end_cut_local_offset)
    # Calculate local z coordinates of the 4 cross-section corners on fork_end_cut plane
    sx = fork_timber.size[0] / scalar(2)
    sy = fork_timber.size[1] / scalar(2)
    corners = [(sx, sy), (sx, -sy), (-sx, sy), (-sx, -sy)]
    nx, ny, nz = fork_end_cut.normal[0], fork_end_cut.normal[1], fork_end_cut.normal[2]
    
    z_corners = []
    if not safe_zero_test(nz):
        for cx, cy in corners:
            cz = (fork_end_cut.offset - nx * cx - ny * cy) / nz
            z_corners.append(cz)
    else:
        z_corners = [fork_timber.length / scalar(2)]

    if fork_end == TimberEnd.TOP:
        fork_end_cut_distance_from_bottom = max(z_corners)
    else:
        fork_end_cut_distance_from_bottom = min(z_corners)

    fork_negative_csg = CSGUnion(children=[fork_slot_csg_local, fork_end_cut])

    # -------------------------------------------------------------------------
    # Tongue timber cuts (receiving_timber: housing + 2 cheeks removed)
    # -------------------------------------------------------------------------
    shoulder_half_space_tongue_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, shoulder_point_global),
    )
    shoulder_half_space_tongue_local = adopt_csg(None, tongue_timber.transform, shoulder_half_space_tongue_global)

    overshoot = max(tongue_timber.size[0], tongue_timber.size[1]) * scalar(2)
    tongue_cheek_box_global = RectangularPrism(
        size=create_v2(fork_width_along_tongue, tongue_normal_dimension * scalar(2)),
        transform=marking_space.transform,
        start_distance=-overshoot,
        end_distance=fork_slot_depth + overshoot,
    )
    tongue_cheek_box_local = adopt_csg(None, tongue_timber.transform, tongue_cheek_box_global)

    tongue_central_prism_global = RectangularPrism(
        size=create_v2(fork_width_along_tongue * scalar(3), tongue_thickness),
        transform=marking_space.transform,
        start_distance=-overshoot * scalar(2),
        end_distance=fork_slot_depth + overshoot * scalar(2),
    )
    tongue_central_prism_local = adopt_csg(None, tongue_timber.transform, tongue_central_prism_global)

    # The tongue only exists on the joint side of shoulder_plane (inside shoulder_half_space).
    # Between entry face and shoulder_plane, the full housing box is removed to house the fork stem.
    tongue_preserved_local = Intersection(
        left=shoulder_half_space_tongue_local,
        right=tongue_central_prism_local,
    )

    tongue_negative_csg_local = Difference(
        base=tongue_cheek_box_local,
        subtract=[tongue_preserved_local],
    )

    # -------------------------------------------------------------------------
    # Assemble cuts and joint
    # -------------------------------------------------------------------------
    fork_engagement = tongue_timber.get_size_in_direction_3d(fork_end_direction)
    fork_cut_no_relief = Cutting(
        timber=fork_timber,
        maybe_top_end_cut_distance_from_bottom=fork_end_cut_distance_from_bottom if fork_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=fork_end_cut_distance_from_bottom if fork_end == TimberEnd.BOTTOM else None,
        negative_csg=fork_negative_csg,
        assembly_freedom=AssemblyFreedom.translation(-fork_end_direction, freed_after=fork_engagement),
    )

    tongue_cut_no_relief = Cutting(
        timber=tongue_timber,
        negative_csg=tongue_negative_csg_local,
        assembly_freedom=AssemblyFreedom.translation(fork_end_direction, freed_after=fork_engagement),
    )

    fork_cut, tongue_cut = _apply_scribe_relief_if_configured(
        relief=relief,
        butt_cut=fork_cut_no_relief,
        receiving_cut=tongue_cut_no_relief,
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

# TODO rename to convert_butt_shoulder_inset_to_centerline_distance and rename args as well
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


# ============================================================================
# Japanese butt joints (moved from japanese_joints.py)
# ============================================================================


def cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    receiving_timber_shoulder_inset: Numeric,
    dovetail_length: Numeric,
    dovetail_small_width: Numeric,
    dovetail_large_width: Numeric,
    dovetail_lateral_offset: Numeric = scalar(0),
    dovetail_depth: Optional[Numeric] = None,
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
        - No scribe-relief support yet: the drop-in socket needs a more complex
          notching algorithm than the shared butt-joint relief helper provides
    """

    require_check(arrangement.check_face_aligned_and_orthogonal())

    # TODO cutting algorithm needs to be updated in order to support imperfect timbers:
    # 1. needs to extrude the dovetail profile upwards further 
    # 2. the shoulder notch doesn't seem to work correctly on imperfect timbers either
    # 3. the tenon cutout shape only cuts to the perfect timber dimensions
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

    # Create a 90 degree shoulder notch if inset is specified
    if receiving_timber_shoulder_inset > 0:
        # Notch dimensions match the dovetail timber's cross-section at the housing
        # Width is the length of the housing (shoulder_distance_from_end on dovetail timber)
        notch_width = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.rotate_right().to.face())

        # Depth is the amount of inset
        notch_depth = receiving_timber_shoulder_inset

        # TODO you may want to switch to CSG scribe logic as this seems to be broken on imperfect timbers
        receiving_timber_shoulder_notch = chop_shoulder_notch_on_timber_face(
            timber=receiving_timber,
            notch_face=receiving_timber_shoulder_face,
            distance_along_timber=receiving_timber_notch_center,
            notch_width=notch_width,
            notch_depth=notch_depth,
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

cut_蟻仕口 = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers
cut_ari_shiguchi = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers


def cut_dropin_housed_butt_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    receiving_timber_shoulder_inset: Numeric,
    housing_length: Numeric,
    housing_width: Numeric,
    housing_lateral_offset: Numeric = scalar(0),
    housing_depth: Optional[Numeric] = None,
) -> Joint:
    """
    Creates a drop-in housed butt joint (housing slot pocket) between two orthogonal timbers.

    Only the housing timber is cut to receive the square end of the housed timber.
    The housed timber drops into the pocket along the housing face normal.

    Args:
        arrangement: Butt joint arrangement where butt_timber is the housed timber,
            receiving_timber receives the housing pocket socket, butt_timber_end is the cut end,
            and front_face_on_butt_timber is the face where the pocket profile is open (normally the top face).
        receiving_timber_shoulder_inset: Distance to inset the shoulder notch on the receiving timber
        housing_length: Length of the housing slot pocket (the joist extension depth into the mudsill)
        housing_width: Width of the housing pocket
        housing_lateral_offset: Lateral offset of the housing pocket from center (default 0)
        housing_depth: Depth of the pocket. If None, defaults to half the timber dimension

    Returns:
        Joint object containing the two CutTimbers with the housing cuts applied

    Notes:
        - No scribe-relief support yet: the drop-in pocket needs a more complex
          notching algorithm than the shared butt-joint relief helper provides
    """
    require_check(arrangement.check_face_aligned_and_orthogonal())
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_butt_timber is not None, (
        "arrangement.front_face_on_butt_timber must be set to determine the housing face"
    )
    housed_timber = arrangement.butt_timber
    receiving_timber = arrangement.receiving_timber
    housed_timber_end = arrangement.butt_timber_end
    housed_timber_face = arrangement.front_face_on_butt_timber

    # Validate positive dimensions
    if housing_length <= 0:
        raise ValueError(f"housing_length must be positive, got {housing_length}")
    if housing_width <= 0:
        raise ValueError(f"housing_width must be positive, got {housing_width}")
    if receiving_timber_shoulder_inset < 0:
        raise ValueError(f"receiving_timber_shoulder_inset must be non-negative, got {receiving_timber_shoulder_inset}")
    if housing_depth is not None and housing_depth <= 0:
        raise ValueError(f"housing_depth must be positive if provided, got {housing_depth}")

    if are_vectors_parallel(housed_timber.get_face_direction_global(housed_timber_face), receiving_timber.get_length_direction_global()):
        raise ValueError(
            "Housed timber face must be perpendicular to receiving timber length direction for drop-in housed butt joint. "
            "Try rotating the housing face."
        )

    if housing_depth is None:
        # Default: half the timber dimension perpendicular to the housing face
        housing_depth = housed_timber.get_size_in_face_normal_axis(housed_timber_face.to.face()) / scalar(2)

    # Housing profile in 2D (X = lateral, Y = along timber length from end)
    # Width is housing_width from Y=0 to Y=housing_length (simple rectangle)
    housing_profile = [
        Matrix([-housing_width / scalar(2) + housing_lateral_offset, 0]),
        Matrix([housing_width / scalar(2) + housing_lateral_offset, 0]),
        Matrix([housing_width / scalar(2) + housing_lateral_offset, housing_length]),
        Matrix([-housing_width / scalar(2) + housing_lateral_offset, housing_length]),
    ]

    # Calculate marking transform
    receiving_timber_shoulder_face = receiving_timber.get_closest_oriented_face_from_global_direction(-housed_timber.get_face_direction_global(housed_timber_end.to.face()))
    face_plane = scribe_face_plane_onto_centerline(
        face=receiving_timber_shoulder_face,
        face_timber=receiving_timber
    )
    marking = mark_distance_from_end_along_centerline(face_plane, housed_timber, housed_timber_end)
    shoulder_distance_from_end = marking.distance - receiving_timber_shoulder_inset

    # Extrude housing profile along the face normal
    housing_profile_csg = chop_profile_on_timber_face(
        timber=housed_timber,
        end=housed_timber_end,
        face=housed_timber_face.to.face(),
        profile=housing_profile,
        depth=housing_depth,
        profile_y_offset_from_end=shoulder_distance_from_end
    )

    # Housing prism
    housing_housing_prism = chop_timber_end_with_prism(
        timber=housed_timber,
        end=housed_timber_end,
        distance_from_end_to_cut=shoulder_distance_from_end
    )

    # Calculate where along the receiving timber the shoulder should be
    housed_centerline = scribe_centerline_onto_centerline(housed_timber)
    marking_receiving = mark_distance_from_end_along_centerline(housed_centerline, receiving_timber)
    receiving_timber_notch_center = marking_receiving.distance

    # Create shoulder notch if inset is specified
    if receiving_timber_shoulder_inset > 0:
        notch_width = housed_timber.get_size_in_face_normal_axis(housed_timber_face.rotate_right().to.face())
        notch_depth = receiving_timber_shoulder_inset
        receiving_timber_shoulder_notch = chop_shoulder_notch_on_timber_face(
            timber=receiving_timber,
            notch_face=receiving_timber_shoulder_face,
            distance_along_timber=receiving_timber_notch_center,
            notch_width=notch_width,
            notch_depth=notch_depth
        )

    # Transform the housing profile CSG to receiving timber coordinates
    housing_socket_csg = adopt_csg(housed_timber.transform, receiving_timber.transform, housing_profile_csg)

    # Create redundant end cut for the housed timber
    if housed_timber_end == TimberEnd.TOP:
        housing_end_local_z = housed_timber.length - shoulder_distance_from_end + housing_length
    else:  # BOTTOM
        housing_end_local_z = shoulder_distance_from_end - housing_length

    housed_lift_direction_global = housed_timber.get_face_direction_global(housed_timber_face.to.face())
    housed_timber_cut_obj = Cutting(
        timber=housed_timber,
        maybe_top_end_cut_distance_from_bottom=housing_end_local_z if housed_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=housing_end_local_z if housed_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=Difference(housing_housing_prism, [housing_profile_csg]),
        assembly_freedom=AssemblyFreedom.translation(housed_lift_direction_global, freed_after=housing_depth),
    )

    # Combine shoulder notch and housing socket
    if receiving_timber_shoulder_inset > 0:
        receiving_timber_negative_csg = CSGUnion([receiving_timber_shoulder_notch, housing_socket_csg])
    else:
        receiving_timber_negative_csg = housing_socket_csg

    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        negative_csg=receiving_timber_negative_csg,
        assembly_freedom=AssemblyFreedom.translation(-housed_lift_direction_global, freed_after=housing_depth),
    )

    return Joint(
        cuttings={
            housed_timber.ticket.path: housed_timber_cut_obj,
            receiving_timber.ticket.path: receiving_timber_cut_obj
        },
        ticket=JointTicket(joint_type="housed_butt"),
        jointAccessories={},
    )

