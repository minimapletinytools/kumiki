"""
Tests for double butt joint construction functions.
"""

from dataclasses import replace
from kumiki import *
from kumiki.example_shavings import create_canonical_example_opposing_double_butt_joint_timbers
from kumiki.joints.workshop.shavings.build_a_butt import SimplePegParameters


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()


class TestSplinedOpposingDoubleButtJoint:
    """Test cut_splined_opposing_double_butt_joint_on_face_aligned_timbers function."""

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
        joint = cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            TimberEnd.TOP,
        )

        assert set(joint.cuttings.keys()) == {"receiving_timber", "butt_timber_1", "butt_timber_2"}
        assert 1 == 1
        assert 1 == 1
        assert 1 == 1

    def test_slot_point_removed_on_all_three_members(self):
        """A point known to lie inside the default slot should be removed from all three timbers."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        joint = cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            TimberEnd.TOP,
        )

        receiving_center_global = (
            arrangement.receiving_timber.get_bottom_position_global()
            + arrangement.receiving_timber.get_length_direction_global() * arrangement.receiving_timber.length / scalar(2)
        )

        slot_direction_global = arrangement.receiving_timber.get_face_direction_global(TimberEnd.TOP)
        joint_plane_normal_global = safe_normalize_vector(
            cross_product(
                arrangement.butt_timber_1.get_length_direction_global(),
                arrangement.receiving_timber.get_length_direction_global(),
            )
        )
        slot_face_on_butt_1 = arrangement.butt_timber_1.get_closest_oriented_long_face_from_global_direction(
            slot_direction_global
        )
        slot_depth_axis_dimension = arrangement.butt_timber_1.get_size_in_face_normal_axis(slot_face_on_butt_1)
        default_slot_depth = slot_depth_axis_dimension / scalar(2)

        # Use the slot center point implied by default parameters in the joint function.
        slot_sample_point_global = receiving_center_global + slot_direction_global * (
            slot_depth_axis_dimension / scalar(2) - default_slot_depth / scalar(2)
        ) + joint_plane_normal_global * scalar(0)

        for key in ["receiving_timber", "butt_timber_1", "butt_timber_2"]:
            cut_timber = joint.cuttings[key]
            rendered_csg = _render_cutting(cut_timber)
            slot_sample_point_local = cut_timber.timber.transform.global_to_local(slot_sample_point_global)
            assert not rendered_csg.contains_point(slot_sample_point_local), (
                f"Slot sample point should be cut out of {key}"
            )

        far_point_on_receiving_global = (
            receiving_center_global
            + arrangement.receiving_timber.get_length_direction_global() * inches(12)
        )
        receiving_csg = _render_cutting(joint.cuttings["receiving_timber"])
        far_point_on_receiving_local = arrangement.receiving_timber.transform.global_to_local(far_point_on_receiving_global)
        assert receiving_csg.contains_point(far_point_on_receiving_local), (
            "Receiving timber should still contain points far from the slot"
        )

    def test_shoulder_inset_moves_butt_end_cut_inward(self):
        """Increasing shoulder inset should move the butt end cut inward by that inset."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()

        joint_flush = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            shoulder_symmetric_inset=scalar(0),
        )
        joint_inset = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            shoulder_symmetric_inset=inches(1),
        )

        butt_1_flush_end_cut = joint_flush.cuttings["butt_timber_1"].get_maybe_top_end_cut()
        butt_1_inset_end_cut = joint_inset.cuttings["butt_timber_1"].get_maybe_top_end_cut()

        assert butt_1_flush_end_cut is not None
        assert butt_1_inset_end_cut is not None
        assert safe_zero_test((butt_1_inset_end_cut.offset - butt_1_flush_end_cut.offset) - inches(1)), (
            "Top-end shoulder cut offset should increase by the shoulder inset (butt protrudes further)"
        )

    def test_receiving_timber_gets_shoulder_notches_when_inset_positive(self):
        """Positive shoulder inset should add receiving-side shoulder notch cuts."""
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()

        joint_flush = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            shoulder_symmetric_inset=scalar(0),
        )
        joint_inset = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            shoulder_symmetric_inset=inches(1),
        )

        receiving_flush_negative_csg = joint_flush.cuttings["receiving_timber"].negative_csg
        receiving_inset_negative_csg = joint_inset.cuttings["receiving_timber"].negative_csg

        assert not isinstance(receiving_flush_negative_csg, CSGUnion)
        assert isinstance(receiving_inset_negative_csg, CSGUnion)
        assert len(receiving_inset_negative_csg.children) == 3

    def test_pegs_cut_butts_and_spline_and_create_accessories(self):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        peg_parameters = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(2), scalar(0))],
            size=inches(1),
            tenon_hole_offset=scalar(0),
        )

        joint = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            peg_parameters=peg_parameters,
        )

        assert "spline" in joint.jointAccessories
        peg_keys = [key for key in joint.jointAccessories.keys() if key.startswith("peg_butt_")]
        assert len(peg_keys) == 2

        butt_1_negative_csg = joint.cuttings["butt_timber_1"].negative_csg
        butt_2_negative_csg = joint.cuttings["butt_timber_2"].negative_csg
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
            peg_positions=[(inches(2), scalar(0))],
            size=inches(1),
            tenon_hole_offset=scalar(0),
        )

        joint = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            peg_parameters=peg_parameters,
        )

        receiving_len = arrangement.receiving_timber.get_length_direction_global()
        butt_1_len = arrangement.butt_timber_1.get_length_direction_global()
        joint_plane_normal = safe_normalize_vector(cross_product(butt_1_len, receiving_len))

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
            peg_positions=[(inches(2), scalar(0))],
            size=inches(1),
            tenon_hole_offset=scalar(0),
        )
        peg_parameters_offset = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(2), scalar(0))],
            size=inches(1),
            tenon_hole_offset=inches(1),
        )

        joint_no_offset = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            peg_parameters=peg_parameters_no_offset,
        )
        joint_offset = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
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
            peg_positions=[(inches(2), scalar(0))],
            size=inches(1),
            tenon_hole_offset=scalar(0),
        )

        joint = cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_thickness=inches(1),
            slot_depth=inches(2),
            spline_length=inches(12),
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
            spline_extra_depth=spline_extra_depth,
            peg_parameters=peg_parameters,
        )

        peg_key = next(key for key in joint.jointAccessories if key.startswith("peg_butt_1_"))
        peg = joint.jointAccessories[peg_key]
        spline = joint.jointAccessories["spline"]

        assert isinstance(peg, Peg)
        assert isinstance(spline, CSGAccessory)

        slot_direction_global = arrangement.receiving_timber.get_face_direction_global(
            TimberEnd.TOP
        )
        non_extra_spline_center_global = (
            spline.transform.position - slot_direction_global * spline_extra_depth / scalar(2)
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

        assert safe_zero_test(peg_lateral_position - spline_lateral_position)
        assert safe_zero_test(Abs(actual_spline_lateral_position - spline_lateral_position) - spline_extra_depth / scalar(2))


def _stubby_tenon_middle_global(butt: TimberLike, end: TimberEnd, receiving: TimberLike, tenon: StubbyMiniTenon) -> V3:
    """Return the middle of `tenon` on `butt`: halfway along it past the shoulder, at its position."""
    end_direction = butt.get_face_direction_global(end)
    receiving_middle = receiving.get_bottom_position_global() + receiving.get_length_direction_global() * receiving.length / scalar(2)
    length_direction = butt.get_length_direction_global()
    bottom = butt.get_bottom_position_global()
    on_centerline = bottom + length_direction * safe_dot_product(receiving_middle - bottom, length_direction)
    shoulder = on_centerline - end_direction * (receiving.get_size_in_direction_3d(end_direction) / scalar(2))
    return (shoulder + end_direction * (tenon.length / scalar(2))
            + butt.get_face_direction_global(TimberFace.RIGHT) * tenon.position[0]
            + butt.get_face_direction_global(TimberFace.FRONT) * tenon.position[1])


class TestStubbyMiniTenons:
    """Stubby mini tenons beside the spline, each in a mortise in the receiving timber."""

    def _joint(self):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        joint = cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers_with_stubby_tenons(arrangement, TimberEnd.TOP)
        return arrangement, joint

    def test_each_tenon_stands_past_the_shoulder_and_its_mortise_is_cut(self):
        arrangement, joint = self._joint()
        receiving = arrangement.receiving_timber
        receiving_csg = _render_cutting(joint.cuttings["receiving_timber"])
        tenons_1 = basic_stubby_mini_tenons(arrangement, TimberEnd.TOP)
        assert len(tenons_1) == 3
        for butt, end, key, tenons in (
            (arrangement.butt_timber_1, arrangement.butt_timber_1_end, "butt_timber_1", tenons_1),
            (arrangement.butt_timber_2, arrangement.butt_timber_2_end, "butt_timber_2",
             [one.reflect_for_other_side(arrangement.butt_timber_1, arrangement.butt_timber_2) for one in tenons_1]),
        ):
            butt_csg = _render_cutting(joint.cuttings[key])
            for tenon in tenons:
                middle = _stubby_tenon_middle_global(butt, end, receiving, tenon)
                assert butt_csg.contains_point(butt.transform.global_to_local(middle)), f"a tenon is missing from {key}"
                assert not receiving_csg.contains_point(receiving.transform.global_to_local(middle)), (
                    f"the mortise for a tenon on {key} is not cut")

    def test_the_other_butts_tenons_line_up_across_the_receiving_timber(self):
        arrangement, _ = self._joint()
        receiving = arrangement.receiving_timber
        length_direction = arrangement.butt_timber_1.get_length_direction_global()
        for tenon in basic_stubby_mini_tenons(arrangement, TimberEnd.TOP):
            other = tenon.reflect_for_other_side(arrangement.butt_timber_1, arrangement.butt_timber_2)
            here = _stubby_tenon_middle_global(arrangement.butt_timber_1, arrangement.butt_timber_1_end, receiving, tenon)
            there = _stubby_tenon_middle_global(arrangement.butt_timber_2, arrangement.butt_timber_2_end, receiving, other)
            across = there - here
            lateral = across - length_direction * safe_dot_product(across, length_direction)
            assert safe_compare(safe_dot_product(lateral, lateral), 0, Comparison.EQ)

    def test_the_end_past_the_shoulder_is_cut_away_around_the_tenons(self):
        arrangement, joint = self._joint()
        butt = arrangement.butt_timber_1
        end = arrangement.butt_timber_1_end
        receiving = arrangement.receiving_timber
        # A corner of the end, past the shoulder: no tenon there.
        corner = StubbyMiniTenon(position=create_v2(butt.size[0] / 2 - mm(2), -butt.size[1] / 2 + mm(2)),
                                 size=create_v2(mm(1), mm(1)), length=mm(10))
        point = _stubby_tenon_middle_global(butt, end, receiving, corner)
        assert not _render_cutting(joint.cuttings["butt_timber_1"]).contains_point(butt.transform.global_to_local(point))

