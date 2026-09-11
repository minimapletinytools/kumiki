"""
Kumiki - Lapped gooseneck joint (Koshikake Kama Tsugi) construction functions
"""

import warnings
from typing import Optional

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import (
    locate_top_center_position,
    mark_distance_from_face_in_normal_direction,
    locate_into_face,
)
from ..shavings import (
    chop_lap_on_timber_end,
    chop_profile_on_timber_face,
    chop_timber_end_with_prism,
)
from ..shavings.shavings import (
    draw_gooseneck_polygon,
    check_timber_overlap_for_splice_joint_is_sensible,
)
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


def cut_lapped_gooseneck_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
    gooseneck_length: Numeric,
    gooseneck_small_width: Numeric,
    gooseneck_large_width: Numeric,
    gooseneck_head_length: Numeric,
    lap_length: Numeric = scalar(0),
    gooseneck_lateral_offset: Numeric = scalar(0),
    gooseneck_depth: Optional[Numeric] = None,
) -> Joint:
    """
    Creates a lapped gooseneck joint (腰掛鎌継ぎ / Koshikake Kama Tsugi) between two timbers.

    This is a traditional Japanese timber joint that combines a lap joint with a gooseneck-shaped
    profile. The gooseneck profile provides mechanical interlock while the lap provides additional
    bearing surface.

    Args:
        arrangement: Splice arrangement where timber1 is the gooseneck timber,
            timber2 is the receiving timber, timber1_end/timber2_end are the joined
            ends, and front_face_on_timber1 is the face on timber1 where the
            gooseneck profile is visible.
        gooseneck_length: Length of the gooseneck shape (does not include lap length)
        gooseneck_small_width: Width of the narrow end of the gooseneck taper
        gooseneck_large_width: Width of the wide end of the gooseneck taper
        gooseneck_head_length: Length of the head portion of the gooseneck
        lap_length: Length of the lap portion of the joint
        gooseneck_lateral_offset: Lateral offset of gooseneck profile
        gooseneck_depth: Optional depth of the gooseneck cut. If None, defaults to half the timber dimension
                        perpendicular to arrangement.front_face_on_timber1

    Returns:
        Joint object containing the two CutTimbers with the gooseneck cuts applied

    Raises:
        ValueError: If the parameters are invalid or the timbers are not properly positioned
    """
    require_check(arrangement.check_face_aligned_and_parallel_axis())
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the gooseneck face"
    )
    gooseneck_timber = arrangement.timber1
    receiving_timber = arrangement.timber2
    gooseneck_timber_end = arrangement.timber1_end
    receiving_timber_end = arrangement.timber2_end
    gooseneck_timber_face = arrangement.front_face_on_timber1

    if gooseneck_length <= 0:
        raise ValueError(f"gooseneck_length must be positive, got {gooseneck_length}")
    if gooseneck_small_width <= 0:
        raise ValueError(f"gooseneck_small_width must be positive, got {gooseneck_small_width}")
    if gooseneck_large_width <= 0:
        raise ValueError(f"gooseneck_large_width must be positive, got {gooseneck_large_width}")
    if gooseneck_head_length <= 0:
        raise ValueError(f"gooseneck_head_length must be positive, got {gooseneck_head_length}")

    if gooseneck_large_width <= gooseneck_small_width:
        raise ValueError(
            f"gooseneck_large_width ({gooseneck_large_width}) must be greater than "
            f"gooseneck_small_width ({gooseneck_small_width})"
        )

    if gooseneck_depth is not None and gooseneck_depth <= 0:
        raise ValueError(f"gooseneck_depth must be positive if provided, got {gooseneck_depth}")

    overlap_error = check_timber_overlap_for_splice_joint_is_sensible(
        gooseneck_timber, receiving_timber, gooseneck_timber_end, receiving_timber_end
    )
    if overlap_error:
        warnings.warn(f"Gooseneck joint configuration may not be sensible: {overlap_error}")

    gooseneck_direction_global = -receiving_timber.get_face_direction_global(receiving_timber_end)
    gooseneck_lateral_offset_direction_global = receiving_timber.get_face_direction_global(gooseneck_timber_face.rotate_right())

    if receiving_timber_end == TimberEnd.TOP:
        receiving_timber_end_position_global = locate_top_center_position(receiving_timber).position
    else:
        receiving_timber_end_position_global = receiving_timber.get_bottom_position_global()

    gooseneck_starting_position_on_receiving_timber_centerline_with_lateral_offset_global = (
        receiving_timber_end_position_global
        + gooseneck_direction_global * lap_length
        + gooseneck_lateral_offset_direction_global * gooseneck_lateral_offset
    )

    gooseneck_shape = draw_gooseneck_polygon(gooseneck_length, gooseneck_small_width, gooseneck_large_width, gooseneck_head_length)

    if gooseneck_depth is None:
        gooseneck_depth = gooseneck_timber.get_size_in_face_normal_axis(
            gooseneck_timber_face.to.face()
        ) / scalar(2)

    gooseneck_starting_position_on_receiving_timber = (
        (gooseneck_starting_position_on_receiving_timber_centerline_with_lateral_offset_global - receiving_timber.get_bottom_position_global()).T
        * receiving_timber.get_length_direction_global()
    )[0, 0]

    gooseneck_cutting_plane = locate_into_face(gooseneck_depth, gooseneck_timber_face, gooseneck_timber)
    gooseneck_face_direction = gooseneck_timber.get_face_direction_global(gooseneck_timber_face)
    receiving_face_direction = -gooseneck_face_direction
    receiving_face = receiving_timber.get_closest_oriented_face_from_global_direction(receiving_face_direction)
    marking = mark_distance_from_face_in_normal_direction(gooseneck_cutting_plane, receiving_timber, receiving_face)
    receiving_timber_lap_depth = Abs(marking.distance)

    if receiving_timber_end == TimberEnd.TOP:
        receiving_timber_shoulder_from_end = receiving_timber.length - gooseneck_starting_position_on_receiving_timber
    else:
        receiving_timber_shoulder_from_end = gooseneck_starting_position_on_receiving_timber

    receiving_timber_lap_face_direction = -gooseneck_timber.get_face_direction_global(gooseneck_timber_face)
    receiving_timber_lap_face = receiving_timber.get_closest_oriented_face_from_global_direction(receiving_timber_lap_face_direction)

    if lap_length > 0:
        receiving_timber_lap_prism, receiving_timber_end_cut = chop_lap_on_timber_end(
            lap_timber=receiving_timber,
            lap_timber_end=receiving_timber_end,
            lap_timber_face=receiving_timber_lap_face,
            lap_length=lap_length,
            lap_shoulder_position_from_lap_timber_end=receiving_timber_shoulder_from_end,
            lap_depth=receiving_timber_lap_depth,
            label=CutCSGLabel("gooseneck_lap"),
        )
    else:
        receiving_timber_end_cut = None

    gooseneck_lap_start_global = receiving_timber_end_position_global
    gooseneck_lap_start_on_gooseneck_timber = (
        (gooseneck_lap_start_global - gooseneck_timber.get_bottom_position_global()).T
        * gooseneck_timber.get_length_direction_global()
    )[0, 0]

    if gooseneck_timber_end == TimberEnd.TOP:
        gooseneck_timber_lap_shoulder_from_end = gooseneck_timber.length - gooseneck_lap_start_on_gooseneck_timber
    else:
        gooseneck_timber_lap_shoulder_from_end = gooseneck_lap_start_on_gooseneck_timber

    gooseneck_timber_lap_prism, _ = chop_lap_on_timber_end(
        lap_timber=gooseneck_timber,
        lap_timber_end=gooseneck_timber_end,
        lap_timber_face=TimberFace(gooseneck_timber_face.value),
        lap_length=lap_length + gooseneck_length,
        lap_shoulder_position_from_lap_timber_end=gooseneck_timber_lap_shoulder_from_end,
        lap_depth=gooseneck_depth,
        label=CutCSGLabel("gooseneck_lap"),
    )

    gooseneck_profile_y_position = gooseneck_timber_lap_shoulder_from_end + lap_length

    gooseneck_profile_csg = chop_profile_on_timber_face(
        timber=gooseneck_timber,
        end=gooseneck_timber_end,
        face=gooseneck_timber_face.to.face(),
        profile=gooseneck_shape,
        depth=gooseneck_depth,
        profile_y_offset_from_end=-gooseneck_profile_y_position,
        label=CutCSGLabel("gooseneck"),
    )

    gooseneck_profile_prism = chop_timber_end_with_prism(
        timber=gooseneck_timber,
        end=gooseneck_timber_end,
        distance_from_end_to_cut=-(gooseneck_profile_y_position),
        label=CutCSGLabel("gooseneck_shoulder"),
    )

    gooseneck_profile_difference_csg = Difference(
        gooseneck_profile_prism, [gooseneck_profile_csg],
        label=CutCSGLabel("gooseneck_waste"),
    )

    gooseneck_timber_combined_csg = SolidUnion([gooseneck_timber_lap_prism, gooseneck_profile_difference_csg])

    gooseneck_extension_from_receiving_end = lap_length + gooseneck_length
    gooseneck_end_position_from_timber_end = gooseneck_timber_lap_shoulder_from_end - gooseneck_extension_from_receiving_end

    if gooseneck_timber_end == TimberEnd.TOP:
        gooseneck_end_cut_local_z = gooseneck_timber.length - gooseneck_end_position_from_timber_end
    else:
        gooseneck_end_cut_local_z = gooseneck_end_position_from_timber_end

    receiving_end_cut_local_z = None
    if receiving_timber_end_cut is not None:
        receiving_end_cut_local_z = (
            receiving_timber_end_cut.offset
            if receiving_timber_end == TimberEnd.TOP
            else -receiving_timber_end_cut.offset
        )

    gooseneck_csg_on_receiving_timber = adopt_csg(gooseneck_timber.transform, receiving_timber.transform, gooseneck_profile_csg)

    if lap_length > 0:
        receiving_timber_negative_csg: CutCSG = SolidUnion([receiving_timber_lap_prism, gooseneck_csg_on_receiving_timber])
    else:
        receiving_timber_negative_csg = gooseneck_csg_on_receiving_timber

    gooseneck_timber_freedom = AssemblyFreedom.translation(gooseneck_face_direction, freed_after=gooseneck_depth)
    receiving_timber_freedom = AssemblyFreedom.translation(-gooseneck_face_direction, freed_after=gooseneck_depth)

    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        maybe_top_end_cut_distance_from_bottom=receiving_end_cut_local_z if receiving_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=receiving_end_cut_local_z if receiving_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=receiving_timber_negative_csg,
        label=CutCSGLabel("gooseneck_socket_cut"),
        assembly_freedom=receiving_timber_freedom,
    )
    gooseneck_timber_cut_obj = Cutting(
        timber=gooseneck_timber,
        maybe_top_end_cut_distance_from_bottom=gooseneck_end_cut_local_z if gooseneck_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=gooseneck_end_cut_local_z if gooseneck_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=gooseneck_timber_combined_csg,
        label=CutCSGLabel("gooseneck_cut"),
        assembly_freedom=gooseneck_timber_freedom,
    )

    return Joint(
        cuttings={
            receiving_timber.ticket.path: receiving_timber_cut_obj,
            gooseneck_timber.ticket.path: gooseneck_timber_cut_obj,
        },
        ticket=JointTicket(joint_type="lapped_gooseneck"),
        jointAccessories={},
    )


# Aliases for Japanese joint functions
cut_腰掛鎌継ぎ_joint_on_aligned_timbers = cut_lapped_gooseneck_joint_on_aligned_timbers
cut_koshikake_kama_tsugi_joint_on_aligned_timbers = cut_lapped_gooseneck_joint_on_aligned_timbers
