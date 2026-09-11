"""
Kumiki - Tongue and fork butt joint construction functions
"""

from __future__ import annotations

from typing import Optional, Union

from kumiki.timber import (
    AssemblyFreedom,
    Cutting,
    Joint,
    JointTicket,
    TimberEnd,
)
from kumiki.construction import ButtJointTimberArrangement
from kumiki.rule import (
    Comparison,
    Numeric,
    safe_compare,
    safe_dot_product,
    safe_transform_vector,
    safe_normalize_vector,
    safe_zero_test,
    are_vectors_parallel,
    Abs,
    scalar,
    create_v2,
    create_v3,
    Matrix,
    Transform,
    Orientation,
)
from kumiki.measuring import (
    mark_distance_from_end_along_centerline,
    get_center_point_on_face_global,
    Space,
)
from kumiki.cutcsg import (
    CutCSG,
    CutCSGLabel,
    HalfSpace,
    RectangularPrism,
    Intersection,
    Difference,
    SolidUnion,
    adopt_csg,
)
from ..shavings.relief import (
    warn_if_arrangement_timbers_imperfect,
    ButtJointScribeReliefConfig,
    apply_scribe_relief_if_configured,
)
from ..shavings.build_a_butt import (
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
    convert_mortise_shoulder_inset_to_centerline_distance,
)


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
        label=CutCSGLabel("shoulder"),
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
        label=CutCSGLabel("fork_slot"),
    )
    fork_slot_prism_local = adopt_csg(None, fork_timber.transform, fork_slot_prism_global)
    fork_slot_csg_local = Intersection(
        left=shoulder_half_space_local,
        right=fork_slot_prism_local,
        label=CutCSGLabel("fork_slot_waste"),
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
    fork_end_cut = HalfSpace(
        normal=fork_end_cut_local_normal,
        offset=fork_end_cut_local_offset,
        label=CutCSGLabel("fork_end_cut"),
    )
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

    fork_negative_csg = SolidUnion(children=[fork_slot_csg_local, fork_end_cut])

    # -------------------------------------------------------------------------
    # Tongue timber cuts (receiving_timber: housing + 2 cheeks removed)
    # -------------------------------------------------------------------------
    shoulder_half_space_tongue_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, shoulder_point_global),
        label=CutCSGLabel("shoulder"),
    )
    shoulder_half_space_tongue_local = adopt_csg(None, tongue_timber.transform, shoulder_half_space_tongue_global)

    overshoot = max(tongue_timber.size[0], tongue_timber.size[1]) * scalar(2)
    tongue_cheek_box_global = RectangularPrism(
        size=create_v2(fork_width_along_tongue, tongue_normal_dimension * scalar(2)),
        transform=marking_space.transform,
        start_distance=-overshoot,
        end_distance=fork_slot_depth + overshoot,
        label=CutCSGLabel("tongue_cheeks"),
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
        label=CutCSGLabel("tongue"),
    )

    tongue_negative_csg_local = Difference(
        base=tongue_cheek_box_local,
        subtract=[tongue_preserved_local],
        label=CutCSGLabel("tongue_waste"),
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
        label=CutCSGLabel("fork_cut"),
        assembly_freedom=AssemblyFreedom.translation(-fork_end_direction, freed_after=fork_engagement),
    )

    tongue_cut_no_relief = Cutting(
        timber=tongue_timber,
        negative_csg=tongue_negative_csg_local,
        label=CutCSGLabel("tongue_cut"),
        assembly_freedom=AssemblyFreedom.translation(fork_end_direction, freed_after=fork_engagement),
    )

    fork_cut, tongue_cut = apply_scribe_relief_if_configured(
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
