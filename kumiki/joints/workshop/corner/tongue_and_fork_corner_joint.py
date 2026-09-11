"""
Kumiki - Tongue and fork corner joint construction function
"""

from typing import Optional

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import (
    get_center_point_on_face_global,
    mark_distance_from_end_along_centerline,
    Space,
)
from ..shavings import *
from ..shavings.build_a_butt import (
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
)
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


def cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = scalar(0),
) -> Joint:
    """
    Creates a plain tongue-and-fork corner joint (corner bridle style).
    Note, you can make an identical joint with cut_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers setting tenon_distance_from_end to 0

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
        tongue_thickness = tongue_normal_dimension / scalar(3)

    assert safe_compare(tongue_thickness, 0, Comparison.GT), "tongue_thickness must be greater than 0"
    assert safe_compare(tongue_normal_dimension - tongue_thickness, 0, Comparison.GE), (
        "tongue_thickness must be <= the tongue timber size in the shared plane normal axis"
    )

    half_tongue_dimension = tongue_normal_dimension / scalar(2)
    half_tongue_thickness = tongue_thickness / scalar(2)
    assert safe_compare(half_tongue_dimension - (Abs(tongue_position) + half_tongue_thickness), 0, Comparison.GE), (
        "tongue_position and tongue_thickness place the tongue outside the tongue timber boundary"
    )

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
        z_direction=safe_normalize_vector(tongue_end_direction),
        y_direction=safe_normalize_vector(tongue_normal_direction),
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
        label=CutCSGLabel("tongue"),
    )

    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
        label=CutCSGLabel("shoulder"),
    )

    tongue_prism_local = adopt_csg(None, tongue_timber.transform, tongue_prism_global)
    shoulder_half_space_local = adopt_csg(None, tongue_timber.transform, shoulder_half_space_global)

    tongue_negative_csg = Difference(
        base=shoulder_half_space_local,
        subtract=[tongue_prism_local],
        label=CutCSGLabel("tongue_waste"),
    )

    # -------------------------------------------------------------------------
    # Fork slot: depth extends to the fork's far face so the slot matches
    # the tongue after its end-cut extension (same orientation as tongue)
    # -------------------------------------------------------------------------
    fork_entry_long_face_for_end_cut = fork_timber.get_closest_oriented_long_face_from_global_direction(-tongue_end_direction)
    fork_far_face = fork_entry_long_face_for_end_cut.to.face().get_opposite_face()
    fork_far_face_normal_global = fork_timber.get_face_direction_global(fork_far_face)
    fork_far_face_point_global = get_center_point_on_face_global(fork_far_face, fork_timber)

    fork_slot_depth = safe_dot_product(
        fork_far_face_point_global - shoulder_point_global,
        safe_normalize_vector(tongue_end_direction),
    )
    assert safe_compare(fork_slot_depth, 0, Comparison.GT), (
        "Fork slot depth must be > 0; check timber arrangement and end selections"
    )

    fork_slot_back_extension = max(fork_timber.size[0], fork_timber.size[1]) * scalar(2)
    fork_slot_prism_global = RectangularPrism(
        size=create_v2(tongue_width, tongue_thickness),
        transform=marking_space.transform,
        start_distance=-fork_slot_back_extension,
        end_distance=fork_slot_depth,
        label=CutCSGLabel("fork_slot"),
    )
    fork_negative_csg = adopt_csg(None, fork_timber.transform, fork_slot_prism_global)

    # -------------------------------------------------------------------------
    # End cuts: each timber is cut to align with the far face of the opposing timber
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
    tongue_end_cut = HalfSpace(
        normal=tongue_end_cut_local_normal,
        offset=tongue_end_cut_local_offset,
        label=CutCSGLabel("tongue_end_cut"),
    )

    tongue_entry_long_face = tongue_timber.get_closest_oriented_long_face_from_global_direction(-fork_end_direction)
    tongue_far_face = tongue_entry_long_face.to.face().get_opposite_face()
    tongue_far_face_normal_global = tongue_timber.get_face_direction_global(tongue_far_face)
    tongue_far_face_point_global = get_center_point_on_face_global(tongue_far_face, tongue_timber)

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
    fork_end_cut = HalfSpace(
        normal=fork_end_cut_local_normal,
        offset=fork_end_cut_local_offset,
        label=CutCSGLabel("fork_end_cut"),
    )

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

    tongue_cut = Cutting(
        timber=tongue_timber,
        maybe_top_end_cut_distance_from_bottom=tongue_end_cut_distance_from_bottom if tongue_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tongue_end_cut_distance_from_bottom if tongue_end == TimberEnd.BOTTOM else None,
        negative_csg=CSGUnion(children=tongue_negative_parts),
        label=CutCSGLabel("tongue_cut"),
        assembly_freedom=AssemblyFreedom.combine(
            AssemblyFreedom.translation(
                -tongue_end_direction,
                freed_after=fork_timber.get_size_in_direction_3d(tongue_end_direction),
            ),
            AssemblyFreedom.translation(
                fork_end_direction,
                freed_after=fork_timber.get_size_in_direction_3d(fork_end_direction),
            ),
        ),
    )

    fork_cut = Cutting(
        timber=fork_timber,
        maybe_top_end_cut_distance_from_bottom=fork_end_cut_distance_from_bottom if fork_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=fork_end_cut_distance_from_bottom if fork_end == TimberEnd.BOTTOM else None,
        negative_csg=CSGUnion(children=fork_negative_parts),
        label=CutCSGLabel("fork_cut"),
        assembly_freedom=AssemblyFreedom.combine(
            AssemblyFreedom.translation(
                tongue_end_direction,
                freed_after=fork_timber.get_size_in_direction_3d(tongue_end_direction),
            ),
            AssemblyFreedom.translation(
                -fork_end_direction,
                freed_after=fork_timber.get_size_in_direction_3d(fork_end_direction),
            ),
        ),
    )

    return Joint(
        cuttings={
            "tongue_timber": tongue_cut,
            "fork_timber": fork_cut,
        },
        ticket=JointTicket(joint_type="tongue_and_fork_corner"),
        jointAccessories={},
    )


def cut_plain_tongue_and_fork_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = scalar(0),
) -> Joint:
    """Compatibility alias for `cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers`."""
    return cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
    )
