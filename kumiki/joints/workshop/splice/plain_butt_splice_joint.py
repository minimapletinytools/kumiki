"""
Kumiki - Plain butt splice joint construction function
"""

import warnings
from typing import Optional

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import locate_top_center_position, locate_bottom_center_position


def cut_plain_butt_splice_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
    splice_point: Optional[V3] = None,
) -> Joint:
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
    from kumiki.construction import _are_directions_parallel

    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end

    if not _are_directions_parallel(timberA.get_length_direction_global(), timberB.get_length_direction_global()):
        raise ValueError("Timbers must have parallel length axes for a splice joint")

    if timberA_end == TimberEnd.TOP:
        endA_position = locate_top_center_position(timberA).position
    else:
        endA_position = locate_bottom_center_position(timberA).position

    if timberB_end == TimberEnd.TOP:
        endB_position = locate_top_center_position(timberB).position
    else:
        endB_position = locate_bottom_center_position(timberB).position

    length_dir_norm = safe_normalize_vector(timberA.get_length_direction_global())

    if splice_point is None:
        splice_point = (endA_position + endB_position) / 2
    else:
        to_splice = splice_point - timberA.get_bottom_position_global()
        distance_along_centerline = safe_dot_product(to_splice, length_dir_norm)
        projected_point = timberA.get_bottom_position_global() + length_dir_norm * distance_along_centerline

        distance_from_centerline = safe_magnitude(splice_point - projected_point)
        if not safe_zero_test(distance_from_centerline):
            warnings.warn(
                f"Splice point was not on timberA's centerline (distance: {float(distance_from_centerline)}). "
                f"Projecting onto centerline."
            )
            splice_point = projected_point

    centerline_distance = safe_magnitude(
        (splice_point - timberA.get_bottom_position_global()) -
        length_dir_norm * safe_dot_product(splice_point - timberA.get_bottom_position_global(), length_dir_norm) -
        ((splice_point - timberB.get_bottom_position_global()) -
         length_dir_norm * safe_dot_product(splice_point - timberB.get_bottom_position_global(), length_dir_norm))
    )

    max_dimension = max(timberA.size[0], timberA.size[1], timberB.size[0], timberB.size[1])
    if centerline_distance > max_dimension / scalar(2):
        warnings.warn(
            f"Timber cross sections may not overlap (centerline distance: {float(centerline_distance)}). "
            f"Check joint geometry."
        )

    distance_A_from_bottom = safe_dot_product(splice_point - timberA.get_bottom_position_global(), timberA.get_length_direction_global())
    distance_B_from_bottom = safe_dot_product(splice_point - timberB.get_bottom_position_global(), timberB.get_length_direction_global())

    endA_direction = timberA.get_face_direction_global(timberA_end)
    endB_direction = timberB.get_face_direction_global(timberB_end)

    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=distance_A_from_bottom if timberA_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=distance_A_from_bottom if timberA_end == TimberEnd.BOTTOM else None,
        negative_csg=None,
        assembly_freedom=AssemblyFreedom.translation(-endA_direction, freed_after=scalar(0)),
        label=CutCSGLabel("splice_cross_cut"),
    )

    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=distance_B_from_bottom if timberB_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=distance_B_from_bottom if timberB_end == TimberEnd.BOTTOM else None,
        negative_csg=None,
        assembly_freedom=AssemblyFreedom.translation(-endB_direction, freed_after=scalar(0)),
        label=CutCSGLabel("splice_cross_cut"),
    )

    return Joint(
        cuttings={"timberA": cutA, "timberB": cutB},
        ticket=JointTicket(joint_type="plain_butt_splice"),
        jointAccessories={},
    )
