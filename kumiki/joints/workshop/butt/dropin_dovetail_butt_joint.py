"""
Kumiki - Drop-in dovetail butt joint construction functions (蟻仕口 / Ari Shiguchi)
"""

from __future__ import annotations

from typing import Optional, Union

from kumiki.timber import (
    AssemblyFreedom,
    Cutting,
    Joint,
    JointTicket,
    TimberEnd,
    require_check,
)
from kumiki.construction import ButtJointTimberArrangement
from kumiki.rule import (
    Numeric,
    safe_dot_product,
    are_vectors_parallel,
    scalar,
    Matrix,
    Transform,
)
from kumiki.measuring import (
    mark_distance_from_end_along_centerline,
)
from kumiki.cutcsg import (
    CutCSGLabel,
    Difference,
    SolidUnion,
    adopt_csg,
)
from ..shavings.shavings import (
    chop_profile_on_timber_face,
    chop_timber_end_with_prism,
    orientation_pointing_towards_face_sitting_on_face,
    scribe_face_plane_onto_centerline,
    scribe_centerline_onto_centerline,
)
from ..shavings.relief import (
    chop_shoulder_notch_on_timber_face,
    warn_if_arrangement_timbers_imperfect,
)


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

    # Validate positive dimensions
    if dovetail_length <= 0:
        raise ValueError(f"dovetail_length must be positive, got {dovetail_length}")
    if dovetail_small_width <= 0:
        raise ValueError(f"dovetail_small_width must be positive, got {dovetail_small_width}")
    if dovetail_large_width <= 0:
        raise ValueError(f"dovetail_large_width must be positive, got {dovetail_large_width}")
    if receiving_timber_shoulder_inset < 0:
        raise ValueError(f"receiving_timber_shoulder_inset must be non-negative, got {receiving_timber_shoulder_inset}")

    if dovetail_large_width <= dovetail_small_width:
        raise ValueError(
            f"dovetail_large_width ({dovetail_large_width}) must be greater than "
            f"dovetail_small_width ({dovetail_small_width})"
        )

    if dovetail_depth is not None and dovetail_depth <= 0:
        raise ValueError(f"dovetail_depth must be positive if provided, got {dovetail_depth}")

    if are_vectors_parallel(dovetail_timber.get_face_direction_global(dovetail_timber_face), receiving_timber.get_length_direction_global()):
        raise ValueError(
            "Dovetail timber face must be perpendicular to receiving timber length direction for dovetail butt joint. "
            "The face should be oriented such that the dovetail profile is visible when looking along the receiving timber. "
            "Try rotating the dovetail face by 90 degrees."
        )

    if dovetail_depth is None:
        dovetail_depth = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.to.face()) / scalar(2)

    # Dovetail profile in 2D (X = lateral, Y = along timber length from end)
    dovetail_profile = [
        Matrix([-dovetail_small_width / scalar(2) + dovetail_lateral_offset, 0]),
        Matrix([dovetail_small_width / scalar(2) + dovetail_lateral_offset, 0]),
        Matrix([dovetail_large_width / scalar(2) + dovetail_lateral_offset, dovetail_length]),
        Matrix([-dovetail_large_width / scalar(2) + dovetail_lateral_offset, dovetail_length]),
    ]

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

    dovetail_profile_csg = chop_profile_on_timber_face(
        timber=dovetail_timber,
        end=dovetail_timber_end,
        face=dovetail_timber_face.to.face(),
        profile=dovetail_profile,
        depth=dovetail_depth,
        profile_y_offset_from_end=shoulder_distance_from_end,
        label=CutCSGLabel("dovetail"),
    )

    dovetail_housing_prism = chop_timber_end_with_prism(
        timber=dovetail_timber,
        end=dovetail_timber_end,
        distance_from_end_to_cut=shoulder_distance_from_end,
        label=CutCSGLabel("dovetail_housing"),
    )

    dovetail_centerline = scribe_centerline_onto_centerline(dovetail_timber)
    marking_receiving = mark_distance_from_end_along_centerline(dovetail_centerline, receiving_timber)
    receiving_timber_notch_center = marking_receiving.distance

    if receiving_timber_shoulder_inset > 0:
        notch_width = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.rotate_right().to.face())
        notch_depth = receiving_timber_shoulder_inset

        receiving_timber_shoulder_notch = chop_shoulder_notch_on_timber_face(
            timber=receiving_timber,
            notch_face=receiving_timber_shoulder_face,
            distance_along_timber=receiving_timber_notch_center,
            notch_width=notch_width,
            notch_depth=notch_depth,
        )

    dovetail_socket_csg = adopt_csg(dovetail_timber.transform, receiving_timber.transform, dovetail_profile_csg)

    if dovetail_timber_end == TimberEnd.TOP:
        dovetail_end_local_z = dovetail_timber.length - shoulder_distance_from_end + dovetail_length
    else:
        dovetail_end_local_z = shoulder_distance_from_end - dovetail_length

    dovetail_lift_direction_global = dovetail_timber.get_face_direction_global(dovetail_timber_face.to.face())
    dovetail_timber_cut_obj = Cutting(
        timber=dovetail_timber,
        maybe_top_end_cut_distance_from_bottom=dovetail_end_local_z if dovetail_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=dovetail_end_local_z if dovetail_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=Difference(
            dovetail_housing_prism, [dovetail_profile_csg],
            label=CutCSGLabel("dovetail_waste"),
        ),
        label=CutCSGLabel("dovetail_cut"),
        assembly_freedom=AssemblyFreedom.translation(dovetail_lift_direction_global, freed_after=dovetail_depth),
    )

    if receiving_timber_shoulder_inset > 0:
        receiving_timber_negative_csg = SolidUnion([receiving_timber_shoulder_notch, dovetail_socket_csg])
    else:
        receiving_timber_negative_csg = dovetail_socket_csg

    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        negative_csg=receiving_timber_negative_csg,
        label=CutCSGLabel("dovetail_socket_cut"),
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


# Aliases for Japanese joint functions
cut_蟻仕口 = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers
cut_ari_shiguchi = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers
