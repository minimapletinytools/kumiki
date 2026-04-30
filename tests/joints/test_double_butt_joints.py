"""
Tests for double butt joint construction functions.
"""

from dataclasses import replace
from sympy import Rational, Abs
from kumiki import *
from kumiki.example_shavings import create_canonical_example_opposing_double_butt_joint_timbers
from kumiki.joints.build_a_butt_joint_shavings import SimplePegParameters


class TestSplinedOpposingDoubleButtJoint:
    """Test cut_splined_opposing_double_butt_joint function."""

    def test_arrangement_validation(self):
        """Canonical arrangement passes the cardinal-and-opposing-butts check."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        assert arrangement.check_face_aligned_cardinal_and_opposing_butts() is None

    def test_arrangement_rejects_butt_1_front_face_not_parallel_to_joint_plane(self):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        bad_arrangement = replace(arrangement, front_face_on_butt_timber_1=TimberLongFace.FRONT)
        assert bad_arrangement.check_face_aligned_cardinal_and_opposing_butts() is not None

    def test_returns_joint_with_three_cut_timbers(self):
        """Implemented function returns all three cut timbers with one cut each."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        joint = cut_basic_splined_opposing_double_butt_joint(
            arrangement,
            TimberReferenceEnd.TOP,
        )

        assert set(joint.cut_timbers.keys()) == {"receiving_timber", "butt_timber_1", "butt_timber_2"}
        assert len(joint.cut_timbers["receiving_timber"].cuts) == 1
        assert len(joint.cut_timbers["butt_timber_1"].cuts) == 1
        assert len(joint.cut_timbers["butt_timber_2"].cuts) == 1

    def test_slot_point_removed_on_all_three_members(self):
        """A point known to lie inside the default slot should be removed from all three timbers."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        joint = cut_basic_splined_opposing_double_butt_joint(
            arrangement,
            TimberReferenceEnd.TOP,
        )

        receiving_center_global = (
            arrangement.receiving_timber.get_bottom_position_global()
            + arrangement.receiving_timber.get_length_direction_global() * arrangement.receiving_timber.length / Rational(2)
        )

        slot_direction_global = arrangement.receiving_timber.get_face_direction_global(TimberReferenceEnd.TOP)
        joint_plane_normal_global = normalize_vector(
            cross_product(
                arrangement.butt_timber_1.get_length_direction_global(),
                arrangement.receiving_timber.get_length_direction_global(),
            )
        )
        slot_face_on_butt_1 = arrangement.butt_timber_1.get_closest_oriented_long_face_from_global_direction(
            slot_direction_global
        )
        slot_depth_axis_dimension = arrangement.butt_timber_1.get_size_in_face_normal_axis(slot_face_on_butt_1)
        default_slot_depth = slot_depth_axis_dimension / Rational(2)

        # Use the slot center point implied by default parameters in the joint function.
        slot_sample_point_global = receiving_center_global + slot_direction_global * (
            slot_depth_axis_dimension / Rational(2) - default_slot_depth / Rational(2)
        ) + joint_plane_normal_global * Rational(0)

        for key in ["receiving_timber", "butt_timber_1", "butt_timber_2"]:
            cut_timber = joint.cut_timbers[key]
            rendered_csg = cut_timber.render_timber_with_cuts_csg_local()
            slot_sample_point_local = cut_timber.timber.transform.global_to_local(slot_sample_point_global)
            assert not rendered_csg.contains_point(slot_sample_point_local), (
                f"Slot sample point should be cut out of {key}"
            )

        far_point_on_receiving_global = (
            receiving_center_global
            + arrangement.receiving_timber.get_length_direction_global() * inches(12)
        )
        receiving_csg = joint.cut_timbers["receiving_timber"].render_timber_with_cuts_csg_local()
        far_point_on_receiving_local = arrangement.receiving_timber.transform.global_to_local(far_point_on_receiving_global)
        assert receiving_csg.contains_point(far_point_on_receiving_local), (
            "Receiving timber should still contain points far from the slot"
        )

    def test_shoulder_inset_moves_butt_end_cut_inward(self):
        """Increasing shoulder inset should move the butt end cut inward by that inset."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()

        joint_flush = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            shoulder_symmetric_inset=Rational(0),
        )
        joint_inset = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            shoulder_symmetric_inset=inches(1),
        )

        butt_1_flush_end_cut = joint_flush.cut_timbers["butt_timber_1"].cuts[0].maybe_top_end_cut
        butt_1_inset_end_cut = joint_inset.cut_timbers["butt_timber_1"].cuts[0].maybe_top_end_cut

        assert butt_1_flush_end_cut is not None
        assert butt_1_inset_end_cut is not None
        assert zero_test((butt_1_inset_end_cut.offset - butt_1_flush_end_cut.offset) - inches(1)), (
            "Top-end shoulder cut offset should increase by the shoulder inset (butt protrudes further)"
        )

    def test_receiving_timber_gets_shoulder_notches_when_inset_positive(self):
        """Positive shoulder inset should add receiving-side shoulder notch cuts."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()

        joint_flush = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            shoulder_symmetric_inset=Rational(0),
        )
        joint_inset = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            shoulder_symmetric_inset=inches(1),
        )

        receiving_flush_negative_csg = joint_flush.cut_timbers["receiving_timber"].cuts[0].negative_csg
        receiving_inset_negative_csg = joint_inset.cut_timbers["receiving_timber"].cuts[0].negative_csg

        assert not isinstance(receiving_flush_negative_csg, CSGUnion)
        assert isinstance(receiving_inset_negative_csg, CSGUnion)
        assert len(receiving_inset_negative_csg.children) == 3

    def test_pegs_cut_butts_and_spline_and_create_accessories(self):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        peg_parameters = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(2), Rational(0))],
            size=inches(1),
            tenon_hole_offset=Rational(0),
        )

        joint = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            peg_parameters=peg_parameters,
        )

        assert "spline" in joint.jointAccessories
        peg_keys = [key for key in joint.jointAccessories.keys() if key.startswith("peg_butt_")]
        assert len(peg_keys) == 2

        butt_1_negative_csg = joint.cut_timbers["butt_timber_1"].cuts[0].negative_csg
        butt_2_negative_csg = joint.cut_timbers["butt_timber_2"].cuts[0].negative_csg
        assert isinstance(butt_1_negative_csg, CSGUnion)
        assert isinstance(butt_2_negative_csg, CSGUnion)
        assert len(butt_1_negative_csg.children) >= 2
        assert len(butt_2_negative_csg.children) >= 2

        spline_accessory = joint.jointAccessories["spline"]
        assert isinstance(spline_accessory, CSGAccessory)
        assert isinstance(spline_accessory.positive_csg, Difference)
        assert len(spline_accessory.positive_csg.subtract) == 2

    def test_pegs_enter_perpendicular_to_joint_plane(self):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        peg_parameters = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(2), Rational(0))],
            size=inches(1),
            tenon_hole_offset=Rational(0),
        )

        joint = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            peg_parameters=peg_parameters,
        )

        receiving_len = arrangement.receiving_timber.get_length_direction_global()
        butt_1_len = arrangement.butt_timber_1.get_length_direction_global()
        joint_plane_normal = normalize_vector(cross_product(butt_1_len, receiving_len))

        peg_key = next(key for key in joint.jointAccessories if key.startswith("peg_butt_1_"))
        peg = joint.jointAccessories[peg_key]
        assert isinstance(peg, Peg)
        peg_drill_direction = create_v3(
            peg.transform.orientation.matrix[0, 2],
            peg.transform.orientation.matrix[1, 2],
            peg.transform.orientation.matrix[2, 2],
        )
        assert are_vectors_parallel(peg_drill_direction, joint_plane_normal)

    def test_tenon_hole_offset_moves_spline_hole_toward_receiving(self):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        peg_parameters_no_offset = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(2), Rational(0))],
            size=inches(1),
            tenon_hole_offset=Rational(0),
        )
        peg_parameters_offset = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(2), Rational(0))],
            size=inches(1),
            tenon_hole_offset=inches(1),
        )

        joint_no_offset = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            peg_parameters=peg_parameters_no_offset,
        )
        joint_offset = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            peg_parameters=peg_parameters_offset,
        )

        spline_no_offset = joint_no_offset.jointAccessories["spline"]
        spline_offset = joint_offset.jointAccessories["spline"]

        assert isinstance(spline_no_offset, CSGAccessory)
        assert isinstance(spline_offset, CSGAccessory)
        assert isinstance(spline_no_offset.positive_csg, Difference)
        assert isinstance(spline_offset.positive_csg, Difference)
        assert isinstance(spline_no_offset.positive_csg.subtract[0], RectangularPrism)
        assert isinstance(spline_offset.positive_csg.subtract[0], RectangularPrism)

        first_hole_local_no_offset = spline_no_offset.positive_csg.subtract[0].transform.position
        first_hole_local_offset = spline_offset.positive_csg.subtract[0].transform.position

        z_delta = first_hole_local_offset[2] - first_hole_local_no_offset[2]
        assert numeric_compare(Abs(z_delta), inches(1), Comparison.EQ)

    def test_zero_lateral_peg_position_tracks_non_extra_spline_centerline(self):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        spline_extra_depth = inches(1)
        peg_parameters = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(2), Rational(0))],
            size=inches(1),
            tenon_hole_offset=Rational(0),
        )

        joint = cut_splined_opposing_double_butt_joint(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberReferenceEnd.TOP,
            spline_extra_depth=spline_extra_depth,
            peg_parameters=peg_parameters,
        )

        peg_key = next(key for key in joint.jointAccessories if key.startswith("peg_butt_1_"))
        peg = joint.jointAccessories[peg_key]
        spline = joint.jointAccessories["spline"]

        assert isinstance(peg, Peg)
        assert isinstance(spline, CSGAccessory)

        slot_direction_global = arrangement.receiving_timber.get_face_direction_global(
            TimberReferenceEnd.TOP
        )
        non_extra_spline_center_global = (
            spline.transform.position - slot_direction_global * spline_extra_depth / Rational(2)
        )

        peg_face_on_butt_1 = arrangement.front_face_on_butt_timber_1
        assert peg_face_on_butt_1 is not None
        if peg_face_on_butt_1 in [TimberLongFace.RIGHT, TimberLongFace.LEFT]:
            lateral_axis = arrangement.butt_timber_1.get_face_direction_global(TimberFace.FRONT)
        else:
            lateral_axis = arrangement.butt_timber_1.get_face_direction_global(TimberFace.RIGHT)

        peg_lateral_position = safe_dot_product(peg.transform.position, lateral_axis)
        spline_lateral_position = safe_dot_product(non_extra_spline_center_global, lateral_axis)
        actual_spline_lateral_position = safe_dot_product(spline.transform.position, lateral_axis)

        assert zero_test(peg_lateral_position - spline_lateral_position)
        assert zero_test(Abs(actual_spline_lateral_position - spline_lateral_position) - spline_extra_depth / Rational(2))
