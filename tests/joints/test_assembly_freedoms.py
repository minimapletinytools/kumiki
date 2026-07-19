"""Tests that the workshop joint builders author their own assembly freedoms.

Each cut function knows its escape geometry precisely (tenon axis, lap normal,
insertion depth), so it attaches assembly_freedom to the cuttings/accessories
it creates; locking accessories (pegs/keys/wedges) get suborder -1 so they pop
before the members slide (suborder 0, the default). These tests assert the
authored directions, depths, and suborders per joint family.
"""

import pytest
from dataclasses import replace

from kumiki import *
from kumiki.assembly import Ordering
from kumiki.example_shavings import (
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_cross_joint_timbers,
    create_canonical_example_opposing_double_butt_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_splice_joint_timbers,
)
from kumiki.rule import giraffe_evalf


def unit(direction):
    return tuple(float(giraffe_evalf(direction[index, 0])) for index in range(3))


def assert_authored_translation(freedom, expected_direction=None):
    """The freedom exists, its first DOF is a unit direction with positive travel."""
    assert freedom is not None, "expected the cut function to author an assembly freedom"
    assert len(freedom.translations) >= 1
    dof = freedom.translations[0]
    direction = unit(dof.direction)
    magnitude = sum(component ** 2 for component in direction) ** 0.5
    assert magnitude == pytest.approx(1.0, abs=1e-6)
    assert float(giraffe_evalf(dof.freed_after)) > 0
    if expected_direction is not None:
        for actual, expected in zip(direction, expected_direction):
            assert actual == pytest.approx(expected, abs=1e-6)


def assert_opposite_escape_pair(joint, key_a, key_b):
    """Both sides of an interface get inverse escape directions."""
    freedom_a = joint.cuttings[key_a].assembly_freedom
    freedom_b = joint.cuttings[key_b].assembly_freedom
    assert_authored_translation(freedom_a)
    assert_authored_translation(freedom_b)
    direction_a = unit(freedom_a.translations[0].direction)
    direction_b = unit(freedom_b.translations[0].direction)
    dot = sum(a * b for a, b in zip(direction_a, direction_b))
    assert dot == pytest.approx(-1.0, abs=1e-6)


class TestButtFamilyFreedoms:
    def test_plain_butt(self, float_mode):
        # Canonical: butt timber runs +Y, TOP end into the receiving timber.
        joint = cut_basic_plain_butt_joint(create_canonical_example_butt_joint_timbers())

        assert_authored_translation(joint.cuttings["butt_timber"].assembly_freedom, (0, -1, 0))
        assert_authored_translation(joint.cuttings["receiving_timber"].assembly_freedom, (0, 1, 0))
        assert_opposite_escape_pair(joint, "butt_timber", "receiving_timber")

    def test_mortise_and_tenon_with_pegs(self, float_mode):
        arrangement = create_canonical_example_butt_joint_timbers()
        joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
            tenon_timber=arrangement.butt_timber,
            mortise_timber=arrangement.receiving_timber,
            tenon_end=arrangement.butt_timber_end,
            use_peg=True,
        )

        # M&T cuttings are keyed by ticket path; tenon backs out along -Y.
        assert_authored_translation(joint.cuttings["butt_timber"].assembly_freedom, (0, -1, 0))
        assert_opposite_escape_pair(joint, "butt_timber", "receiving_timber")
        # The peg locks the joint: it pops at suborder -1 before the timbers
        # slide at suborder 0.
        assert "peg_0" in joint.jointAccessories
        peg = joint.jointAccessories["peg_0"]
        assert_authored_translation(peg.assembly_freedom)
        assert peg.assembly_ordering == Ordering(0, -1)
        assert joint.cuttings["butt_timber"].assembly_ordering == Ordering(0, 0)
        assert joint.cuttings["receiving_timber"].assembly_ordering == Ordering(0, 0)

    def test_mortise_and_tenon_without_pegs_has_no_suborder(self, float_mode):
        arrangement = create_canonical_example_butt_joint_timbers()
        joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
            tenon_timber=arrangement.butt_timber,
            mortise_timber=arrangement.receiving_timber,
            tenon_end=arrangement.butt_timber_end,
            use_peg=False,
        )

        assert joint.cuttings["butt_timber"].assembly_ordering == Ordering(0, 0)

    def test_tongue_and_fork_butt(self, float_mode):
        joint = cut_basic_tongue_and_fork_butt_joint_on_plane_aligned_timbers(create_canonical_example_butt_joint_timbers())

        assert_authored_translation(joint.cuttings["tongue_timber"].assembly_freedom, (0, -1, 0))
        assert_opposite_escape_pair(joint, "tongue_timber", "fork_timber")

    def test_dropin_dovetail_is_unidirectional(self, float_mode):
        arrangement = create_canonical_example_butt_joint_timbers()
        joint = cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers(
            dovetail_timber=arrangement.butt_timber,
            receiving_timber=arrangement.receiving_timber,
            dovetail_timber_end=arrangement.butt_timber_end,
            dovetail_timber_face=TimberLongFace.RIGHT,
            receiving_timber_shoulder_inset=scalar(0),
            dovetail_length=inches(3),
            dovetail_small_width=inches(1),
            dovetail_large_width=inches(2),
        )

        # The taper blocks axial pull: exactly one lift-out DOF along the
        # profile-face normal (RIGHT face points +Z in the canonical setup).
        dovetail_freedom = joint.cuttings["butt_timber"].assembly_freedom
        assert dovetail_freedom is not None
        assert_authored_translation(dovetail_freedom, (0, 0, 1))
        assert len(dovetail_freedom.translations) == 1
        assert_opposite_escape_pair(joint, "butt_timber", "receiving_timber")

    def test_dropin_housed_is_unidirectional(self, float_mode):
        arrangement = create_canonical_example_butt_joint_timbers()
        joint = cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers(
            housed_timber=arrangement.butt_timber,
            receiving_timber=arrangement.receiving_timber,
            housed_timber_end=arrangement.butt_timber_end,
            housed_timber_face=TimberLongFace.RIGHT,
            receiving_timber_shoulder_inset=scalar(0),
        )

        housed_freedom = joint.cuttings["butt_timber"].assembly_freedom
        assert housed_freedom is not None
        assert_authored_translation(housed_freedom, (0, 0, 1))
        assert len(housed_freedom.translations) == 1
        assert_opposite_escape_pair(joint, "butt_timber", "receiving_timber")


class TestLapAndSpliceFreedoms:
    def test_plain_cross_lap(self, float_mode):
        joint = cut_basic_plain_cross_lap_joint_on_face_aligned_timbers(create_canonical_example_cross_joint_timbers())

        assert_opposite_escape_pair(joint, "timberA", "timberB")

    def test_plain_miter(self, float_mode):
        joint = cut_basic_plain_miter_joint(create_canonical_example_right_angle_corner_joint_timbers())

        # Each timber pulls back along its own axis (timber1 runs +Y, timber2 +X;
        # the joint is at their BOTTOM ends, so escapes point away: +Y and +X).
        assert_authored_translation(joint.cuttings["timberA"].assembly_freedom)
        assert_authored_translation(joint.cuttings["timberB"].assembly_freedom)

    def test_plain_butt_splice(self, float_mode):
        joint = cut_basic_plain_butt_splice_joint_on_aligned_timbers(
            create_canonical_example_splice_joint_timbers()
        )

        assert_opposite_escape_pair(joint, "timberA", "timberB")

    def test_plain_splice_lap(self, float_mode):
        joint = cut_basic_plain_splice_lap_joint_on_aligned_timbers(
            create_canonical_example_splice_joint_timbers()
        )

        assert_opposite_escape_pair(joint, "top_lap_timber", "bottom_lap_timber")


class TestLockedJointFreedoms:
    def test_mitered_and_keyed_lap(self, float_mode):
        arrangement = create_canonical_example_right_angle_corner_joint_timbers()
        if arrangement.front_face_on_timber1 is None:
            arrangement = replace(arrangement, front_face_on_timber1=TimberLongFace.RIGHT)
        joint = cut_basic_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(arrangement)

        cutting_keys = list(joint.cuttings)
        for key in cutting_keys:
            assert_authored_translation(joint.cuttings[key].assembly_freedom)
            assert joint.cuttings[key].assembly_ordering == Ordering(0, 0)
        assert "key_0" in joint.jointAccessories
        key_wedge = joint.jointAccessories["key_0"]
        assert_authored_translation(key_wedge.assembly_freedom)
        assert key_wedge.assembly_ordering == Ordering(0, -1)

    def test_splined_opposing_double_butt(self, float_mode):
        arrangement = create_canonical_example_opposing_double_butt_joint_timbers()
        joint = cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers(
            arrangement,
            slot_facing_end_on_receiving_timber=TimberEnd.TOP,
        )

        # Butt timbers pull back along their own axes (butt 1 runs +Y, butt 2 -Y).
        assert_authored_translation(joint.cuttings["butt_timber_1"].assembly_freedom, (0, -1, 0))
        assert_authored_translation(joint.cuttings["butt_timber_2"].assembly_freedom, (0, 1, 0))
        assert joint.cuttings["butt_timber_1"].assembly_ordering == Ordering(0, 0)
        # The receiving timber has no single escape while both butts oppose it.
        assert joint.cuttings["receiving_timber"].assembly_freedom is None
        # Pegs pop first; the spline slides with the members.
        peg_keys = [key for key in joint.jointAccessories if key.startswith("peg")]
        assert peg_keys, "basic splined double butt should include default pegs"
        for peg_key in peg_keys:
            assert_authored_translation(joint.jointAccessories[peg_key].assembly_freedom)
            assert joint.jointAccessories[peg_key].assembly_ordering == Ordering(0, -1)
        spline = joint.jointAccessories["spline"]
        assert_authored_translation(spline.assembly_freedom)
        assert spline.assembly_ordering == Ordering(0, 0)

    def test_wedged_half_dovetail_mortise_and_tenon(self, float_mode):
        from sympy import Matrix, cos, sin
        arrangement = create_canonical_example_butt_joint_timbers()
        joint = cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            dovetail_top_side_on_butt_timber=TimberLongFace.FRONT,
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_depth=scalar(4),
            dovetail_depth=scalar(1),
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=degrees(10),
            ),
        )

        expected_angle = 10 * 3.141592653589793 / 180.0
        expected_tenon_direction = (sin(expected_angle), -cos(expected_angle), 0.0)
        expected_mortise_direction = (-sin(expected_angle), cos(expected_angle), 0.0)

        assert_authored_translation(joint.cuttings["butt_timber"].assembly_freedom, expected_tenon_direction)
        assert_authored_translation(joint.cuttings["receiving_timber"].assembly_freedom, expected_mortise_direction)


class TestRigidJoints:
    def test_lapped_gooseneck_stays_rigid(self, float_mode):
        arrangement = create_canonical_example_splice_joint_timbers()
        joint = cut_basic_lapped_gooseneck_joint_on_aligned_timbers(
            gooseneck_timber=arrangement.timber1,
            receiving_timber=arrangement.timber2,
            receiving_timber_end=arrangement.timber2_end,
            gooseneck_timber_face=TimberLongFace.RIGHT,
        )

        # Lift-then-slide cannot be expressed as one translation yet.
        for cutting in joint.cuttings.values():
            assert cutting.assembly_freedom is None
