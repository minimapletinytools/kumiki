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

class TestTongueAndForkJoint:
    @staticmethod
    def _face_center(timber: Timber, face: TimberFace) -> V3:
        if face == TimberFace.TOP:
            return locate_top_center_position(timber).position
        if face == TimberFace.BOTTOM:
            return locate_bottom_center_position(timber).position

        center = timber.get_bottom_position_global() + timber.get_length_direction_global() * (timber.length / scalar(2))
        if face == TimberFace.RIGHT:
            return center + timber.get_width_direction_global() * (timber.size[0] / scalar(2))
        if face == TimberFace.LEFT:
            return center - timber.get_width_direction_global() * (timber.size[0] / scalar(2))
        if face == TimberFace.FRONT:
            return center + timber.get_height_direction_global() * (timber.size[1] / scalar(2))
        return center - timber.get_height_direction_global() * (timber.size[1] / scalar(2))

    def test_tongue_and_fork_joint_structure_and_opposing_face_end_cuts(self):
        tongue_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))

        arrangement = CornerJointTimberArrangement(
            timber1=tongue_timber,
            timber2=fork_timber,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
        )
        joint = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(arrangement)

        assert len(joint.cuttings) == 2
        assert "tongue_timber" in joint.cuttings
        assert "fork_timber" in joint.cuttings

        tongue_cut = joint.cuttings["tongue_timber"]
        fork_cut = joint.cuttings["fork_timber"]
        assert tongue_cut.negative_csg is not None
        assert fork_cut.negative_csg is not None
        assert tongue_cut.get_maybe_bottom_end_cut() is not None
        assert fork_cut.get_maybe_bottom_end_cut() is not None

        tongue_end_direction = -tongue_timber.get_length_direction_global()
        fork_entry_face = fork_timber.get_closest_oriented_face_from_global_direction(-tongue_end_direction)
        fork_opposite_face_center = self._face_center(fork_timber, fork_entry_face.get_opposite_face())

        fork_end_direction = -fork_timber.get_length_direction_global()
        tongue_entry_face = tongue_timber.get_closest_oriented_face_from_global_direction(-fork_end_direction)
        tongue_opposite_face_center = self._face_center(tongue_timber, tongue_entry_face.get_opposite_face())

        tongue_distance_from_bottom = safe_dot_product(
            fork_opposite_face_center - tongue_timber.get_bottom_position_global(),
            tongue_timber.get_length_direction_global(),
        )
        expected_tongue_end_cut = chop_timber_end_with_half_plane(
            tongue_timber,
            TimberEnd.BOTTOM,
            tongue_distance_from_bottom,
        )
        actual_tongue_end_cut = tongue_cut.get_maybe_bottom_end_cut()
        assert actual_tongue_end_cut is not None
        assert actual_tongue_end_cut.normal.equals(expected_tongue_end_cut.normal)
        assert actual_tongue_end_cut.offset == expected_tongue_end_cut.offset

        fork_distance_from_bottom = safe_dot_product(
            tongue_opposite_face_center - fork_timber.get_bottom_position_global(),
            fork_timber.get_length_direction_global(),
        )
        expected_fork_end_cut = chop_timber_end_with_half_plane(
            fork_timber,
            TimberEnd.BOTTOM,
            fork_distance_from_bottom,
        )
        actual_fork_end_cut = fork_cut.get_maybe_bottom_end_cut()
        assert actual_fork_end_cut is not None
        assert actual_fork_end_cut.normal.equals(expected_fork_end_cut.normal)
        assert actual_fork_end_cut.offset == expected_fork_end_cut.offset

    def test_tongue_position_changes_kept_tongue_region(self):
        tongue_timber_a = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber_a = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        arrangement_a = CornerJointTimberArrangement(
            timber1=tongue_timber_a,
            timber2=fork_timber_a,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
        )

        joint_centered = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(arrangement_a)

        tongue_timber_b = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber_b = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        arrangement_b = CornerJointTimberArrangement(
            timber1=tongue_timber_b,
            timber2=fork_timber_b,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
        )
        joint_shifted = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
            arrangement_b,
            tongue_thickness=scalar(2),
            tongue_position=scalar(2),
        )

        plane_normal = arrangement_a.compute_normalized_timber_cross_product()
        tongue_face = tongue_timber_a.get_closest_oriented_long_face_from_global_direction(plane_normal)
        tongue_normal = tongue_timber_a.get_face_direction_global(tongue_face)

        sample_point_global = (
            tongue_timber_a.get_bottom_position_global()
            + tongue_timber_a.get_length_direction_global() * scalar(1)
            + tongue_normal * scalar(0)
        )

        centered_render = _render_cutting(joint_centered.cuttings["tongue_timber"])
        shifted_render = _render_cutting(joint_shifted.cuttings["tongue_timber"])

        assert centered_render.contains_point(tongue_timber_a.transform.global_to_local(sample_point_global))
        assert not shifted_render.contains_point(tongue_timber_b.transform.global_to_local(sample_point_global))

    def test_tongue_and_fork_joint_assertions(self):
        tongue_parallel = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_parallel = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))

        with pytest.raises(AssertionError, match="parallel"):
            cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
                CornerJointTimberArrangement(
                    timber1=tongue_parallel,
                    timber2=fork_parallel,
                    timber1_end=TimberEnd.BOTTOM,
                    timber2_end=TimberEnd.BOTTOM,
                )
            )

        tongue_non_plane = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_non_plane = create_timber(
            length=scalar(100),
            size=create_v2(6, 6),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 1, 1),
            width_direction=create_v3(1, -1, 0),
        )

        with pytest.raises(AssertionError, match="plane-aligned"):
            cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
                CornerJointTimberArrangement(
                    timber1=tongue_non_plane,
                    timber2=fork_non_plane,
                    timber1_end=TimberEnd.BOTTOM,
                    timber2_end=TimberEnd.BOTTOM,
                )
            )



