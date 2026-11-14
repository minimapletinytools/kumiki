"""
Tests for Kumiki timber framing system
"""

import pytest
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber,
)
from kumiki.rule import inches, degrees, are_vectors_parallel, safe_dot_product, safe_normalize_vector
from kumiki.ticket import TimberTicket
from kumiki.csg.cutcsg import Difference, SolidUnion, ConvexPolygonExtrusion, RectangularPrism, HalfSpace
from kumiki.example_shavings import (
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
)


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()

class TestCornerLapJoint:
    def test_corner_lap_joint_has_two_end_cuts_aligned_to_opposing_faces(self):
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))

        arrangement = CornerJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.FRONT,
        )

        joint = cut_plain_corner_lap_joint_on_plane_aligned_timbers(arrangement)

        assert len(joint.cuttings) == 2
        cutA = joint.cuttings["timberA"]
        cutB = joint.cuttings["timberB"]
        assert cutA.get_maybe_bottom_end_cut() is not None
        assert cutB.get_maybe_bottom_end_cut() is not None

        timberA_end_direction = -timberA.get_length_direction_global()
        timberB_entry_face = timberB.get_closest_oriented_face_from_global_direction(-timberA_end_direction)
        timberB_far_face_center = get_center_point_on_face_global(timberB_entry_face.get_opposite_face(), timberB)

        timberB_end_direction = -timberB.get_length_direction_global()
        timberA_entry_face = timberA.get_closest_oriented_face_from_global_direction(-timberB_end_direction)
        timberA_far_face_center = get_center_point_on_face_global(timberA_entry_face.get_opposite_face(), timberA)

        expected_A_distance = safe_dot_product(
            timberB_far_face_center - timberA.get_bottom_position_global(),
            timberA.get_length_direction_global(),
        )
        expected_B_distance = safe_dot_product(
            timberA_far_face_center - timberB.get_bottom_position_global(),
            timberB.get_length_direction_global(),
        )

        expected_A_end_cut = chop_timber_end_with_half_plane(timberA, TimberEnd.BOTTOM, expected_A_distance)
        expected_B_end_cut = chop_timber_end_with_half_plane(timberB, TimberEnd.BOTTOM, expected_B_distance)

        actual_A_end_cut = cutA.get_maybe_bottom_end_cut()
        actual_B_end_cut = cutB.get_maybe_bottom_end_cut()
        assert actual_A_end_cut is not None
        assert actual_B_end_cut is not None
        assert actual_A_end_cut.normal.equals(expected_A_end_cut.normal)
        assert actual_A_end_cut.offset == expected_A_end_cut.offset
        assert actual_B_end_cut.normal.equals(expected_B_end_cut.normal)
        assert actual_B_end_cut.offset == expected_B_end_cut.offset




@pytest.mark.parametrize("angle", [30, 60, 90, 120, 150])
@pytest.mark.parametrize("ends", [
    (TimberEnd.BOTTOM, TimberEnd.BOTTOM),
    (TimberEnd.TOP, TimberEnd.BOTTOM),
    (TimberEnd.BOTTOM, TimberEnd.TOP),
    (TimberEnd.TOP, TimberEnd.TOP),
])
@pytest.mark.parametrize("cut_ratio", [scalar(1, 4), scalar(1, 2), scalar(3, 4)])
def test_angled_corner_lap_trims_to_opposing_faces(angle, ends, cut_ratio):
    corner_global = create_v3(2, -3, 4)
    away_directions_global = [create_v3(0, 1, 0), create_v3(sin(degrees(angle)), cos(degrees(angle)), 0)]
    sizes = [create_v2(.12, .18), create_v2(.12, .24)]
    lengths = [scalar(2), scalar(3)]
    timbers = []
    for index, end in enumerate(ends):
        away_global = away_directions_global[index]
        timbers.append(create_timber(
            length=lengths[index], size=sizes[index],
            bottom_position=corner_global if end == TimberEnd.BOTTOM else corner_global + lengths[index] * away_global,
            length_direction=away_global if end == TimberEnd.BOTTOM else -away_global,
            width_direction=create_v3(0, 0, 1),
            ticket=TimberTicket(f"member{index}"),
        ))
    joint = cut_plain_corner_lap_joint_on_plane_aligned_timbers(CornerJointTimberArrangement(
        timber1=timbers[0], timber2=timbers[1], timber1_end=ends[0], timber2_end=ends[1],
        front_face_on_timber1=TimberLongFace.RIGHT,
    ), cut_ratio=cut_ratio)

    for index, key in enumerate(("timberA", "timberB")):
        timber, other = timbers[index], timbers[1 - index]
        cutting = joint.cuttings[key]
        solid = _render_cutting(cutting)
        # The far side is perpendicular to the other member, pointing out of this corner.
        other_away_global = away_directions_global[1 - index]
        outward_global = cross_product(create_v3(0, 0, 1), other_away_global)
        if safe_dot_product(outward_global, away_directions_global[index]) > 0:
            outward_global = -outward_global
        plane_point_global = corner_global + outward_global * other.size[1] / 2
        direction_global = timber.get_length_direction_global()
        # Sample the half of each lap that remains, at three positions across its width.
        split_x = timber.size[0] * (scalar(1, 2) - cut_ratio)
        retained_x = (-timber.size[0] / 2 + split_x) / 2 if index == 0 else (split_x + timber.size[0] / 2) / 2
        for y in (-timber.size[1] * .4, scalar(0), timber.size[1] * .4):
            edge_point_global = timber.transform.local_to_global(create_v3(retained_x, y, 0))
            station = safe_dot_product(outward_global, plane_point_global - edge_point_global) / safe_dot_product(outward_global, direction_global)
            boundary_local = create_v3(retained_x, y, station)
            inward_local = create_v3(0, 0, .001 if ends[index] == TimberEnd.BOTTOM else -.001)
            assert solid.is_point_on_boundary(boundary_local)
            assert solid.contains_point(boundary_local + inward_local)
            assert not solid.contains_point(boundary_local - inward_local)

        extension = (other.size[1] + abs(cos(degrees(angle))) * timber.size[1]) / (2 * sin(degrees(angle)))
        if ends[index] == TimberEnd.BOTTOM:
            assert cutting.maybe_bottom_end_cut_distance_from_bottom == pytest.approx(-extension)
            assert cutting.maybe_top_end_cut_distance_from_bottom is None
        else:
            assert cutting.maybe_top_end_cut_distance_from_bottom == pytest.approx(timber.length + extension)
            assert cutting.maybe_bottom_end_cut_distance_from_bottom is None
        assert cutting.assembly_freedom is not None
