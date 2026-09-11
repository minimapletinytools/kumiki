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
from kumiki.cutcsg import Difference, SolidUnion, ConvexPolygonExtrusion, RectangularPrism, HalfSpace
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




