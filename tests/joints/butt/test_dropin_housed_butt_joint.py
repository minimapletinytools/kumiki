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



class TestHousedButtJoint:
    """Test cut_dropin_housed_butt_joint_on_face_aligned_timbers function."""

    def test_general_dropin_housed_butt_joint(self):
        """
        General test: create the joint with normal parameters, validate structure,
        and verify point membership.
        """
        arrangement = _make_simple_butt_arrangement()
        housed_timber = arrangement.butt_timber
        receiving_timber = arrangement.receiving_timber

        joint = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=scalar(1),
            housing_length=scalar(4),
            housing_width=scalar(3),
            housing_depth=scalar(3),
        )

        # ---- structure ----
        assert len(joint.cuttings) == 2
        assert housed_timber.ticket.path in joint.cuttings
        assert receiving_timber.ticket.path in joint.cuttings
        assert joint.ticket is not None
        assert joint.ticket.joint_type == "housed_butt"

        housed_cut = joint.cuttings[housed_timber.ticket.path]
        recv_cut = joint.cuttings[receiving_timber.ticket.path]

        assert isinstance(housed_cut, Cutting)
        assert housed_cut.get_maybe_top_end_cut() is not None
        assert isinstance(housed_cut.negative_csg, Difference)

        assert isinstance(recv_cut, Cutting)
        assert isinstance(recv_cut.negative_csg, SolidUnion)

        # Render cuts
        housed_csg = _render_cutting(housed_cut)
        recv_csg = _render_cutting(recv_cut)

        def in_housed(pt):
            return housed_csg.contains_point(housed_timber.transform.global_to_local(pt))

        def in_recv(pt):
            return recv_csg.contains_point(receiving_timber.transform.global_to_local(pt))

        # Far from joint
        assert in_housed(create_v3(scalar(-50), 0, scalar(50)))
        # Past the end
        assert not in_housed(create_v3(scalar(5), 0, scalar(50)))

    def test_multiple_orientations(self):
        """Test that the joint is constructable in several timber orientation combos."""
        test_cases = [
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

            joint = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(4),
                housing_width=scalar(3),
                housing_depth=scalar(3),
            )
            assert len(joint.cuttings) == 2

    def test_validation_errors(self):
        """Verify parameter range checks."""
        arrangement = _make_simple_butt_arrangement()

        with pytest.raises(ValueError, match="housing_length must be positive"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(0), housing_width=scalar(3),
            )

        with pytest.raises(ValueError, match="housing_width must be positive"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(4), housing_width=scalar(0),
            )

        with pytest.raises(ValueError, match="receiving_timber_shoulder_inset must be non-negative"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(-1),
                housing_length=scalar(4), housing_width=scalar(3),
            )

        with pytest.raises(ValueError, match="housing_depth must be positive"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(4), housing_width=scalar(3),
                housing_depth=scalar(0),
            )

    def test_basic_dropin_housed_butt_joint(self):
        """Test the cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers convenience wrapper."""
        butt = create_standard_horizontal_timber(
            direction='y', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="butt_timber",
        )
        recv = create_standard_horizontal_timber(
            direction='x', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="receiving_timber",
        )
        joint = cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers(
            housed_timber=butt,
            receiving_timber=recv,
            housed_timber_end=TimberEnd.BOTTOM,
            housed_timber_face=TimberLongFace.FRONT,
        )
        assert len(joint.cuttings) == 2
        assert joint.ticket.joint_type == "housed_butt"



