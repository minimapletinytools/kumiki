"""
Tests for Japanese joint construction functions.
"""

import pytest
from sympy import Matrix, Rational, Integer, simplify, pi, Abs
from kumiki import *
from kumiki.rule import inches, degrees, are_vectors_parallel, safe_dot_product, normalize_vector
from kumiki.ticket import TimberTicket
from kumiki.cutcsg import Difference, SolidUnion, ConvexPolygonExtrusion
from kumiki.example_shavings import (
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
)
from kumiki.joints.japanese_joints import cut_mitered_and_keyed_lap_joint, cut_housed_dovetail_butt_joint
from tests.testing_shavings import (
    create_standard_horizontal_timber,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_right_angle_arrangement(front_face=TimberLongFace.RIGHT, position=None):
    """Create a right-angle corner arrangement with renamed timbers."""
    from dataclasses import replace as dc_replace
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)
    timberA = dc_replace(arrangement.timber1, ticket=TimberTicket("timberA"))
    timberB = dc_replace(arrangement.timber2, ticket=TimberTicket("timberB"))
    return dc_replace(
        arrangement,
        timber1=timberA,
        timber2=timberB,
        front_face_on_timber1=front_face,
    )


def _make_angled_arrangement(angle_deg, front_face=TimberLongFace.RIGHT, position=None):
    """Create a corner arrangement at the given angle (degrees) with renamed timbers."""
    from dataclasses import replace as dc_replace
    arrangement = create_canonical_example_corner_joint_timbers(
        corner_angle=degrees(Integer(angle_deg)), position=position
    )
    timberA = dc_replace(arrangement.timber1, ticket=TimberTicket("timberA"))
    timberB = dc_replace(arrangement.timber2, ticket=TimberTicket("timberB"))
    return dc_replace(
        arrangement,
        timber1=timberA,
        timber2=timberB,
        front_face_on_timber1=front_face,
    )


def _assert_joint_structure(joint, num_keys, num_laps):
    """Validate basic joint structure: two cut timbers, expected accessories."""
    assert joint is not None
    assert len(joint.cut_timbers) == 2
    assert "timberA" in joint.cut_timbers
    assert "timberB" in joint.cut_timbers

    # Each timber should have exactly one cutting
    assert len(joint.cut_timbers["timberA"].cuts) == 1
    assert len(joint.cut_timbers["timberB"].cuts) == 1
    assert isinstance(joint.cut_timbers["timberA"].cuts[0], Cutting)
    assert isinstance(joint.cut_timbers["timberB"].cuts[0], Cutting)

    # Keys = num_laps - 1
    expected_keys = num_laps - 1
    assert len(joint.jointAccessories) == expected_keys, (
        f"Expected {expected_keys} key accessories for {num_laps} laps, "
        f"got {len(joint.jointAccessories)}"
    )
    for i in range(expected_keys):
        assert f"key_{i}" in joint.jointAccessories
        assert isinstance(joint.jointAccessories[f"key_{i}"], Wedge)


def _assert_end_cuts_match_arrangement(joint, arrangement):
    """Verify that end cuts are on the correct ends per the arrangement."""
    cutA = joint.cut_timbers["timberA"].cuts[0]
    cutB = joint.cut_timbers["timberB"].cuts[0]

    if arrangement.timber1_end == TimberReferenceEnd.TOP:
        assert cutA.maybe_top_end_cut is not None
        assert cutA.maybe_bottom_end_cut is None
    else:
        assert cutA.maybe_bottom_end_cut is not None
        assert cutA.maybe_top_end_cut is None

    if arrangement.timber2_end == TimberReferenceEnd.TOP:
        assert cutB.maybe_top_end_cut is not None
        assert cutB.maybe_bottom_end_cut is None
    else:
        assert cutB.maybe_bottom_end_cut is not None
        assert cutB.maybe_top_end_cut is None


def _assert_miter_boundary_point(joint, timberA, timberB, point_global):
    """Assert a point on the miter boundary is on the boundary of both rendered timbers."""
    csgA = joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local()
    csgB = joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local()
    ptA = timberA.transform.global_to_local(point_global)
    ptB = timberB.transform.global_to_local(point_global)
    assert csgA.is_point_on_boundary(ptA), (
        f"Expected point {point_global.T} to be on timberA boundary"
    )
    assert csgB.is_point_on_boundary(ptB), (
        f"Expected point {point_global.T} to be on timberB boundary"
    )


# ============================================================================
# Tests for cut_mitered_and_keyed_lap_joint
# ============================================================================

class TestMiteredAndKeyedLapJoint:
    """Test cut_mitered_and_keyed_lap_joint function."""

    def test_basic_right_angle_joint(self):
        """Test basic joint at 90 degrees — structure, end cuts, accessories, miter separation."""
        arrangement = _make_right_angle_arrangement()
        timberA = arrangement.timber1
        timberB = arrangement.timber2
        num_laps = 3

        joint = cut_mitered_and_keyed_lap_joint(
            arrangement=arrangement,
            num_laps=num_laps,
            lap_thickness=inches(Rational(3, 4)),
            lap_start_distance_from_reference_miter_face=inches(Rational(1, 2)),
            distance_between_lap_and_outside=inches(Rational(1, 2)),
        )

        _assert_joint_structure(joint, num_keys=num_laps - 1, num_laps=num_laps)
        _assert_end_cuts_match_arrangement(joint, arrangement)

        # Both timbers should be renderable without error
        csgA = joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local()
        csgB = joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local()
        assert csgA is not None
        assert csgB is not None

        
        # Each key wedge accessory has a transform; its position center should
        # be in the void (not contained in either timber).
        for key_name, accessory in joint.jointAccessories.items():
            assert isinstance(accessory, Wedge)
            key_center_global = accessory.transform.position
            ptA = timberA.transform.global_to_local(key_center_global)
            ptB = timberB.transform.global_to_local(key_center_global)
            assert not csgA.contains_point(ptA), (
                f"{key_name} center should not be inside timberA (key void)"
            )
            assert not csgB.contains_point(ptB), (
                f"{key_name} center should not be inside timberB (key void)"
            )

        # TODO test finger locations and keys


    def test_multiple_angles(self):
        """Test that the joint is constructable at several valid angles."""
        for angle_deg in [60, 75, 90, 110, 130]:
            arrangement = _make_angled_arrangement(angle_deg)
            joint = cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=2,
            )
            _assert_joint_structure(joint, num_keys=1, num_laps=2)
            _assert_end_cuts_match_arrangement(joint, arrangement)

            # Ensure renderable
            csgA = joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local()
            csgB = joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local()
            assert csgA is not None
            assert csgB is not None
        
        # TODO test finger locations and keys

    # ------------------------------------------------------------------
    # Parameter variation tests
    # ------------------------------------------------------------------

    def test_num_laps_2_produces_one_key(self):
        """Minimum valid num_laps=2 should produce exactly 1 key."""
        arrangement = _make_right_angle_arrangement()
        joint = cut_mitered_and_keyed_lap_joint(
            arrangement=arrangement,
            num_laps=2,
        )
        _assert_joint_structure(joint, num_keys=1, num_laps=2)

    def test_num_laps_4_produces_three_keys(self):
        """num_laps=4 should produce exactly 3 keys."""
        arrangement = _make_right_angle_arrangement()
        joint = cut_mitered_and_keyed_lap_joint(
            arrangement=arrangement,
            num_laps=4,
        )
        _assert_joint_structure(joint, num_keys=3, num_laps=4)

    # ------------------------------------------------------------------
    # Error / validation tests
    # ------------------------------------------------------------------


    # 🐪
    def test_num_laps_below_2_raises(self):
        """num_laps < 2 should raise ValueError."""
        arrangement = _make_right_angle_arrangement()
        with pytest.raises(ValueError, match="num_laps must be at least 2"):
            cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=1,
            )

    # 🐪
    def test_angle_too_shallow_raises(self):
        """Angles below 45 degrees should raise ValueError."""
        arrangement = _make_angled_arrangement(30)
        with pytest.raises(ValueError, match="Angle between timbers"):
            cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=2,
            )

    # 🐪
    def test_parallel_timbers_raises(self):
        """Parallel timbers (angle ~0 or ~180) should raise."""
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(4, 5), position=(0, 0, 0), ticket="timberA")
        timberB = create_standard_horizontal_timber(direction='x', length=100, size=(4, 5), position=(0, 0, 0), ticket="timberB")

        arrangement = CornerJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.RIGHT,
        )
        with pytest.raises((ValueError, AssertionError)):
            cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=2,
            )


# ============================================================================
# Tests for cut_housed_dovetail_butt_joint
# ============================================================================


def _make_butt_arrangement(front_face=TimberLongFace.RIGHT):
    """Create a canonical butt joint arrangement with the given front face."""
    from dataclasses import replace as dc_replace
    return dc_replace(
        create_canonical_example_butt_joint_timbers(),
        front_face_on_butt_timber=front_face,
    )


def _make_simple_butt_arrangement():
    """
    Create a butt joint arrangement with simple integer coordinates (no unit conversion).

    - Receiving timber (post): vertical along +Z, height 100, size (8, 8), at origin.
      Cross-section: x ∈ [-4, 4], y ∈ [-4, 4].
    - Dovetail timber (beam): horizontal along +X, length 100, size (8, 8),
      bottom at (-100, 0, 50). Cross-section: y ∈ [-4, 4], z ∈ [46, 54].
    - butt_timber_end = TOP (x=0)
    - front_face_on_butt_timber = RIGHT (+Y, perpendicular to post length +Z)
    """
    from tests.testing_shavings import create_standard_vertical_timber
    post = create_standard_vertical_timber(height=100, size=(8, 8), position=(0, 0, 0), ticket="receiving_timber")
    beam = create_standard_horizontal_timber(
        direction='x', length=100, size=(8, 8), position=(-100, 0, 50), ticket="butt_timber",
    )
    return ButtJointTimberArrangement(
        butt_timber=beam,
        receiving_timber=post,
        butt_timber_end=TimberReferenceEnd.TOP,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )


class TestHousedDovetailButtJoint:
    """Test cut_housed_dovetail_butt_joint function."""

    def test_general_housed_dovetail_butt_joint(self):
        """
        General test: create the joint with normal parameters, validate structure
        (cut counts, CSG types, end cuts), then walk key points through the geometry.

        Simple arrangement (no unit conversion):
        - receiving_timber (post): +Z, size 8×8, at origin
        - butt_timber (beam): +X, size 8×8, bottom at (-100, 0, 50), TOP end at x=0
        - front_face_on_butt_timber = RIGHT (+Y)

        Post LEFT face at x=-4.  shoulder_distance_from_end = 4 - 1 = 3.
        Shoulder in global: x = 0 - 3 = -3.
        dovetail_depth = 8/2 = 4 (from RIGHT face y=+4 inward to y=0).
        Dovetail profile: narrow (small_width=2) at shoulder x=-3,
        widening (large_width=4) toward x=1 (past end, clipped by timber body at x=0).
        At x=-1: profile width ≈ 3, Z ∈ [48.5, 51.5], Y ∈ [0, 4].
        """
        arrangement = _make_simple_butt_arrangement()
        dovetail_timber = arrangement.butt_timber
        receiving_timber = arrangement.receiving_timber

        joint = cut_housed_dovetail_butt_joint(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=Rational(1),
            dovetail_length=Rational(4),
            dovetail_small_width=Rational(2),
            dovetail_large_width=Rational(4),
        )

        # ---- structure ----
        assert len(joint.cut_timbers) == 2
        assert dovetail_timber.ticket.name in joint.cut_timbers
        assert receiving_timber.ticket.name in joint.cut_timbers
        assert joint.ticket is not None
        assert joint.ticket.joint_type == "housed_dovetail_butt"
        assert len(joint.jointAccessories) == 0

        dt_cut = joint.cut_timbers[dovetail_timber.ticket.name]
        recv_cut = joint.cut_timbers[receiving_timber.ticket.name]

        # Dovetail timber: 1 cut, end cut at TOP, negative CSG = Difference(housing, profile)
        assert len(dt_cut.cuts) == 1
        assert isinstance(dt_cut.cuts[0], Cutting)
        assert dt_cut.cuts[0].maybe_top_end_cut is not None
        assert dt_cut.cuts[0].maybe_bottom_end_cut is None
        assert isinstance(dt_cut.cuts[0].negative_csg, Difference)

        # Receiving timber: 1 cut, no end cuts, with inset > 0 → SolidUnion(notch, socket)
        assert len(recv_cut.cuts) == 1
        assert isinstance(recv_cut.cuts[0], Cutting)
        assert recv_cut.cuts[0].maybe_top_end_cut is None
        assert recv_cut.cuts[0].maybe_bottom_end_cut is None
        assert isinstance(recv_cut.cuts[0].negative_csg, SolidUnion)

        # ---- render both timbers ----
        dt_csg = dt_cut.render_timber_with_cuts_csg_local()
        recv_csg = recv_cut.render_timber_with_cuts_csg_local()

        def in_dt(pt):
            return dt_csg.contains_point(dovetail_timber.transform.global_to_local(pt))

        def in_recv(pt):
            return recv_csg.contains_point(receiving_timber.transform.global_to_local(pt))

        # TODO use formula based on dovetail joint sizing parameters rather than hardcoded numbers
        # ---- walk a line along the dovetail timber centerline ----

        # Well inside the beam body (far from joint, x=-50)
        assert in_dt(create_v3(Rational(-50), 0, Rational(50)))
        # Past the dovetail end (x=5, well beyond TOP at x=0)
        assert not in_dt(create_v3(Rational(5), 0, Rational(50)))

        # ---- walk a line perpendicular to the dovetail face at x=-1 ----
        # At x=-1 (in the housing region between shoulder x=-3 and end x=0):
        #   profile width ≈ 3, Z ∈ [48.5, 51.5], Y depth ∈ [0, 4]

        # Inside the dovetail tenon: y=1 ∈ [0,4], z=50 ∈ [48.5,51.5]
        tenon_pt = create_v3(Rational(-1), Rational(1), Rational(50))
        assert in_dt(tenon_pt), "Point inside dovetail tenon should be in dovetail timber"
        assert not in_recv(tenon_pt), "Point inside dovetail socket should not be in receiving timber"

        # On the opposite side of the dovetail depth: y=-1 ∉ [0,4]
        void_pt = create_v3(Rational(-1), Rational(-1), Rational(50))
        assert not in_dt(void_pt), "Point in housing void should not be in dovetail timber"
        assert in_recv(void_pt), "Point outside socket should still be in receiving timber"

        # Outside the dovetail width: z=53 ∉ [48.5,51.5]
        outside_width_pt = create_v3(Rational(-1), Rational(1), Rational(53))
        assert not in_dt(outside_width_pt), "Point outside dovetail width should not be in dovetail timber"
        assert in_recv(outside_width_pt), "Point outside socket width should be in receiving timber"

        # ---- receiving timber body far from the joint ----
        assert in_recv(create_v3(0, 0, Rational(10)))
        assert not in_dt(create_v3(0, 0, Rational(10)))

        # ---- before shoulder, full cross-section is intact ----
        body_near_shoulder = create_v3(Rational(-5), Rational(-1), Rational(50))
        assert in_dt(body_near_shoulder), "Full cross-section before shoulder should be intact"

    def test_multiple_orientations(self):
        """Test that the joint is constructable in several timber orientation combos."""
        test_cases = [
            # (butt_dir, recv_dir, butt_end, front_face)
            ('y', 'x', TimberReferenceEnd.BOTTOM, TimberLongFace.FRONT),
            ('-y', 'x', TimberReferenceEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', 'y', TimberReferenceEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', '-y', TimberReferenceEnd.TOP, TimberLongFace.FRONT),
        ]

        for butt_dir, recv_dir, butt_end, front_face in test_cases:
            butt = create_standard_horizontal_timber(
                direction=butt_dir, length=100, size=(6, 6),
                position=(0, 0, 0), ticket="butt_timber",
            )
            recv = create_standard_horizontal_timber(
                direction=recv_dir, length=100, size=(6, 6),
                position=(0, 0, 0), ticket="receiving_timber",
            )

            arrangement = ButtJointTimberArrangement(
                butt_timber=butt,
                receiving_timber=recv,
                butt_timber_end=butt_end,
                front_face_on_butt_timber=front_face,
            )

            joint = cut_housed_dovetail_butt_joint(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=Rational(1),
                dovetail_length=Rational(3),
                dovetail_small_width=Rational(3, 2),
                dovetail_large_width=Rational(3),
            )

            assert len(joint.cut_timbers) == 2
            # Both timbers should be renderable
            joint.cut_timbers["butt_timber"].render_timber_with_cuts_csg_local()
            joint.cut_timbers["receiving_timber"].render_timber_with_cuts_csg_local()

    def test_zero_shoulder_inset(self):
        """With shoulder_inset=0 receiving timber has no shoulder notch (no SolidUnion)."""
        arrangement = _make_butt_arrangement()

        joint = cut_housed_dovetail_butt_joint(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=Rational(0),
            dovetail_length=Rational(3),
            dovetail_small_width=Rational(3, 2),
            dovetail_large_width=Rational(3),
        )

        recv_neg_csg = joint.cut_timbers[arrangement.receiving_timber.ticket.name].cuts[0].negative_csg
        assert not isinstance(recv_neg_csg, SolidUnion), \
            "With zero inset, receiving negative CSG should be the socket alone (no SolidUnion)"

    # 🐪
    def test_validation_errors(self):
        """Test that invalid parameters raise ValueErrors."""
        arrangement = _make_butt_arrangement()

        with pytest.raises(ValueError, match="dovetail_length must be positive"):
            cut_housed_dovetail_butt_joint(
                arrangement=arrangement, receiving_timber_shoulder_inset=Rational(1, 2),
                dovetail_length=Rational(0), dovetail_small_width=Rational(3, 2), dovetail_large_width=Rational(3),
            )

        with pytest.raises(ValueError, match="dovetail_small_width must be positive"):
            cut_housed_dovetail_butt_joint(
                arrangement=arrangement, receiving_timber_shoulder_inset=Rational(1, 2),
                dovetail_length=Rational(3), dovetail_small_width=Rational(-1), dovetail_large_width=Rational(3),
            )

        with pytest.raises(ValueError, match="dovetail_large_width.*must be greater"):
            cut_housed_dovetail_butt_joint(
                arrangement=arrangement, receiving_timber_shoulder_inset=Rational(1, 2),
                dovetail_length=Rational(3), dovetail_small_width=Rational(3, 2), dovetail_large_width=Rational(1),
            )

        with pytest.raises(ValueError, match="receiving_timber_shoulder_inset must be non-negative"):
            cut_housed_dovetail_butt_joint(
                arrangement=arrangement, receiving_timber_shoulder_inset=Rational(-1),
                dovetail_length=Rational(3), dovetail_small_width=Rational(3, 2), dovetail_large_width=Rational(3),
            )

        with pytest.raises(ValueError, match="dovetail_depth must be positive"):
            cut_housed_dovetail_butt_joint(
                arrangement=arrangement, receiving_timber_shoulder_inset=Rational(1, 2),
                dovetail_length=Rational(3), dovetail_small_width=Rational(3, 2), dovetail_large_width=Rational(3),
                dovetail_depth=Rational(0),
            )

    def test_parallel_face_raises(self):
        """Front face parallel to receiving length direction should raise ValueError."""
        butt = create_standard_horizontal_timber(
            direction='y', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="butt_timber",
        )
        recv = create_standard_horizontal_timber(
            direction='x', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="receiving_timber",
        )
        # For butt 'y': RIGHT face is +X, which is parallel to recv length +X
        arrangement = ButtJointTimberArrangement(
            butt_timber=butt,
            receiving_timber=recv,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        )
        with pytest.raises(ValueError, match="perpendicular to receiving timber length"):
            cut_housed_dovetail_butt_joint(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=Rational(1),
                dovetail_length=Rational(3),
                dovetail_small_width=Rational(3, 2),
                dovetail_large_width=Rational(3),
            )
