"""
Kumiki - Plain corner lap joint construction function
"""

from dataclasses import replace

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import get_center_point_on_face_global
from kumiki.csg.cutcsg import (
    HALF_SPACE_PLANE, FeatureGroup, FeatureOverride, FeatureProperties, HalfSpace, SolidUnion,
)
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

    def trim_end(cutting: Cutting, end: TimberEnd, opposing_timber: PerfectTimberWithin) -> Cutting:
        timber = cutting.timber
        end_direction_global = timber.get_face_direction_global(end)
        far_face = opposing_timber.get_closest_oriented_long_face_from_global_direction(end_direction_global)
        normal_global = opposing_timber.get_face_direction_global(far_face)
        face_point_global = get_center_point_on_face_global(far_face, opposing_timber)
        normal_timber_local = timber.orientation.matrix.T * normal_global
        face_point_timber_local = timber.transform.global_to_local(face_point_global)
        offset_timber_local = safe_dot_product(normal_timber_local, face_point_timber_local)
        end_cut = HalfSpace(
            normal=normal_timber_local, offset=offset_timber_local, label=CutCSGLabel("lap_end_cut"),
            feature_overrides=[FeatureOverride(
                HALF_SPACE_PLANE, properties=FeatureProperties(group=FeatureGroup.END_CUT),
            )],
        )

        # Bound the angled end by its intersections with the rough stock's longitudinal edges.
        width_halves, height_halves = timber.get_rough_half_sizes()
        end_distances = [
            (offset_timber_local - normal_timber_local[0] * x - normal_timber_local[1] * y) / normal_timber_local[2]
            for x in (width_halves[0], -width_halves[1])
            for y in (height_halves[0], -height_halves[1])
        ]
        end_distance = max(end_distances) if end == TimberEnd.TOP else min(end_distances)
        negative_parts = [end_cut] if cutting.negative_csg is None else [cutting.negative_csg, end_cut]
        return replace(
            cutting,
            maybe_top_end_cut_distance_from_bottom=(
                end_distance if end == TimberEnd.TOP else cutting.maybe_top_end_cut_distance_from_bottom
            ),
            maybe_bottom_end_cut_distance_from_bottom=(
                end_distance if end == TimberEnd.BOTTOM else cutting.maybe_bottom_end_cut_distance_from_bottom
            ),
            negative_csg=SolidUnion(negative_parts),
        )

    cutA = trim_end(cross_lap_joint.cuttings["timberA"], timberA_end, timberB)
    cutB = trim_end(cross_lap_joint.cuttings["timberB"], timberB_end, timberA)

    return Joint(
        cuttings={
            "timberA": cutA,
            "timberB": cutB,
        },
        ticket=JointTicket(joint_type="plain_corner_lap"),
        jointAccessories={},
    )
