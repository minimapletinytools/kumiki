"""
Kumiki - Plain corner lap joint construction function
"""

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import get_center_point_on_face_global
from ..cross.plain_cross_lap_joint import cut_plain_cross_lap_joint


def cut_plain_corner_lap_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
    cut_ratio: Numeric = scalar(1, 2),
) -> Joint:
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

    timberA_end_direction = timberA.get_face_direction_global(timberA_end)
    timberB_end_direction = timberB.get_face_direction_global(timberB_end)

    timberB_entry_face = timberB.get_closest_oriented_face_from_global_direction(-timberA_end_direction)
    timberB_far_face = timberB_entry_face.get_opposite_face()
    timberB_far_face_point_global = get_center_point_on_face_global(timberB_far_face, timberB)

    timberA_entry_face = timberA.get_closest_oriented_face_from_global_direction(-timberB_end_direction)
    timberA_far_face = timberA_entry_face.get_opposite_face()
    timberA_far_face_point_global = get_center_point_on_face_global(timberA_far_face, timberA)

    timberA_end_cut_distance_from_bottom = safe_dot_product(
        timberB_far_face_point_global - timberA.get_bottom_position_global(),
        timberA.get_length_direction_global(),
    )
    timberB_end_cut_distance_from_bottom = safe_dot_product(
        timberA_far_face_point_global - timberB.get_bottom_position_global(),
        timberB.get_length_direction_global(),
    )

    cross_lap_cutA = cross_lap_joint.cuttings["timberA"]
    cross_lap_cutB = cross_lap_joint.cuttings["timberB"]

    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=(
            timberA_end_cut_distance_from_bottom
            if timberA_end == TimberEnd.TOP
            else cross_lap_cutA.maybe_top_end_cut_distance_from_bottom
        ),
        maybe_bottom_end_cut_distance_from_bottom=(
            timberA_end_cut_distance_from_bottom
            if timberA_end == TimberEnd.BOTTOM
            else cross_lap_cutA.maybe_bottom_end_cut_distance_from_bottom
        ),
        negative_csg=cross_lap_cutA.negative_csg,
        label=cross_lap_cutA.label,
        assembly_freedom=cross_lap_cutA.assembly_freedom,
    )
    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=(
            timberB_end_cut_distance_from_bottom
            if timberB_end == TimberEnd.TOP
            else cross_lap_cutB.maybe_top_end_cut_distance_from_bottom
        ),
        maybe_bottom_end_cut_distance_from_bottom=(
            timberB_end_cut_distance_from_bottom
            if timberB_end == TimberEnd.BOTTOM
            else cross_lap_cutB.maybe_bottom_end_cut_distance_from_bottom
        ),
        negative_csg=cross_lap_cutB.negative_csg,
        label=cross_lap_cutB.label,
        assembly_freedom=cross_lap_cutB.assembly_freedom,
    )

    return Joint(
        cuttings={
            "timberA": cutA,
            "timberB": cutB,
        },
        ticket=JointTicket(joint_type="plain_corner_lap"),
        jointAccessories={},
    )
