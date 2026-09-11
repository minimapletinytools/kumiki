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
    - Dovetail timber (beam): horizontal along +X, length 100, size (8, 8),
      bottom at (-100, 0, 50).
    """
    from tests.testing_shavings import create_standard_vertical_timber, create_standard_horizontal_timber
    post = create_standard_vertical_timber(height=100, size=(8, 8), position=(0, 0, 0), ticket="receiving_timber")
    beam = create_standard_horizontal_timber(
        direction='x', length=100, size=(8, 8), position=(-100, 0, 50), ticket="butt_timber",
    )
    return ButtJointTimberArrangement(
        butt_timber=beam,
        receiving_timber=post,
        butt_timber_end=TimberEnd.TOP,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )



class TestHousedDovetailButtJoint:
    """Test cut_dropin_dovetail_butt_joint_on_face_aligned_timbers function."""

    def test_general_dropin_dovetail_butt_joint(self):
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

        joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=scalar(1),
            dovetail_length=scalar(4),
            dovetail_small_width=scalar(2),
            dovetail_large_width=scalar(4),
        )

        # ---- structure ----
        assert len(joint.cuttings) == 2
        assert dovetail_timber.ticket.path in joint.cuttings
        assert receiving_timber.ticket.path in joint.cuttings
        assert joint.ticket is not None
        assert joint.ticket.joint_type == "housed_dovetail_butt"
        assert len(joint.jointAccessories) == 0

        dt_cut = joint.cuttings[dovetail_timber.ticket.path]
        recv_cut = joint.cuttings[receiving_timber.ticket.path]

        # Dovetail timber: 1 cut, end cut at TOP, negative CSG = Difference(housing, profile)
        assert isinstance(dt_cut, Cutting)
        assert dt_cut.get_maybe_top_end_cut() is not None
        assert dt_cut.get_maybe_bottom_end_cut() is None
        assert isinstance(dt_cut.negative_csg, Difference)

        # Receiving timber: 1 cut, no end cuts, with inset > 0 → SolidUnion(notch, socket)
        assert isinstance(recv_cut, Cutting)
        assert recv_cut.get_maybe_top_end_cut() is None
        assert recv_cut.get_maybe_bottom_end_cut() is None
        assert isinstance(recv_cut.negative_csg, SolidUnion)

        # ---- render both timbers ----
        dt_csg = _render_cutting(dt_cut)
        recv_csg = _render_cutting(recv_cut)

        def in_dt(pt):
            return dt_csg.contains_point(dovetail_timber.transform.global_to_local(pt))

        def in_recv(pt):
            return recv_csg.contains_point(receiving_timber.transform.global_to_local(pt))

        # TODO use formula based on dovetail joint sizing parameters rather than hardcoded numbers
        # ---- walk a line along the dovetail timber centerline ----

        # Well inside the beam body (far from joint, x=-50)
        assert in_dt(create_v3(scalar(-50), 0, scalar(50)))
        # Past the dovetail end (x=5, well beyond TOP at x=0)
        assert not in_dt(create_v3(scalar(5), 0, scalar(50)))

        # ---- walk a line perpendicular to the dovetail face at x=-1 ----
        # At x=-1 (in the housing region between shoulder x=-3 and end x=0):
        #   profile width ≈ 3, Z ∈ [48.5, 51.5], Y depth ∈ [0, 4]

        # Inside the dovetail tenon: y=1 ∈ [0,4], z=50 ∈ [48.5,51.5]
        tenon_pt = create_v3(scalar(-1), scalar(1), scalar(50))
        assert in_dt(tenon_pt), "Point inside dovetail tenon should be in dovetail timber"
        assert not in_recv(tenon_pt), "Point inside dovetail socket should not be in receiving timber"

        # On the opposite side of the dovetail depth: y=-1 ∉ [0,4]
        void_pt = create_v3(scalar(-1), scalar(-1), scalar(50))
        assert not in_dt(void_pt), "Point in housing void should not be in dovetail timber"
        assert in_recv(void_pt), "Point outside socket should still be in receiving timber"

        # Outside the dovetail width: z=53 ∉ [48.5,51.5]
        outside_width_pt = create_v3(scalar(-1), scalar(1), scalar(53))
        assert not in_dt(outside_width_pt), "Point outside dovetail width should not be in dovetail timber"
        assert in_recv(outside_width_pt), "Point outside socket width should be in receiving timber"

        # ---- receiving timber body far from the joint ----
        assert in_recv(create_v3(0, 0, scalar(10)))
        assert not in_dt(create_v3(0, 0, scalar(10)))

        # ---- before shoulder, full cross-section is intact ----
        body_near_shoulder = create_v3(scalar(-5), scalar(-1), scalar(50))
        assert in_dt(body_near_shoulder), "Full cross-section before shoulder should be intact"

    def test_multiple_orientations(self):
        """Test that the joint is constructable in several timber orientation combos."""
        test_cases = [
            # (butt_dir, recv_dir, butt_end, front_face)
            ('y', 'x', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('-y', 'x', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', 'y', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', '-y', TimberEnd.TOP, TimberLongFace.FRONT),
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

            joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=scalar(1),
                dovetail_length=scalar(3),
                dovetail_small_width=scalar(3, 2),
                dovetail_large_width=scalar(3),
            )

            assert len(joint.cuttings) == 2
            # Both timbers should be renderable
            _render_cutting(joint.cuttings["butt_timber"])
            _render_cutting(joint.cuttings["receiving_timber"])

    def test_zero_shoulder_inset(self):
        """With shoulder_inset=0 receiving timber has no shoulder notch (no SolidUnion)."""
        arrangement = _make_butt_arrangement()

        joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=scalar(0),
            dovetail_length=scalar(3),
            dovetail_small_width=scalar(3, 2),
            dovetail_large_width=scalar(3),
        )

        recv_neg_csg = joint.cuttings[arrangement.receiving_timber.ticket.path].negative_csg
        assert not isinstance(recv_neg_csg, SolidUnion), \
            "With zero inset, receiving negative CSG should be the socket alone (no SolidUnion)"

    # 🐪
    def test_validation_errors(self):
        """Test that invalid parameters raise ValueErrors."""
        arrangement = _make_butt_arrangement()

        with pytest.raises(ValueError, match="dovetail_length must be positive"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(0), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(3),
            )

        with pytest.raises(ValueError, match="dovetail_small_width must be positive"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(3), dovetail_small_width=scalar(-1), dovetail_large_width=scalar(3),
            )

        with pytest.raises(ValueError, match="dovetail_large_width.*must be greater"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(3), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(1),
            )

        with pytest.raises(ValueError, match="receiving_timber_shoulder_inset must be non-negative"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(-1),
                dovetail_length=scalar(3), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(3),
            )

        with pytest.raises(ValueError, match="dovetail_depth must be positive"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(3), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(3),
                dovetail_depth=scalar(0),
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
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        )
        with pytest.raises(ValueError, match="perpendicular to receiving timber length"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=scalar(1),
                dovetail_length=scalar(3),
                dovetail_small_width=scalar(3, 2),
                dovetail_large_width=scalar(3),
            )


