"""
Tests for lapped gooseneck joint (Koshikake Kama Tsugi).
"""

import pytest
from kumiki import *
from kumiki.example_shavings import create_canonical_example_splice_joint_timbers
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
)


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()


class TestLappedGooseneckJoint:
    """Test cut_lapped_gooseneck_joint_on_aligned_timbers function."""

    def test_lapped_gooseneck_basic_structure(self):
        """Test that lapped gooseneck joint creates two cut timbers with appropriate cuttings."""
        arrangement = create_canonical_example_splice_joint_timbers()
        gooseneck_timber = arrangement.timber1
        receiving_timber = arrangement.timber2
        splice_arr = SpliceJointTimberArrangement(
            timber1=gooseneck_timber,
            timber2=receiving_timber,
            timber1_end=arrangement.timber1_end,
            timber2_end=arrangement.timber2_end,
            front_face_on_timber1=TimberLongFace.RIGHT,
        )

        joint = cut_lapped_gooseneck_joint_on_aligned_timbers(
            arrangement=splice_arr,
            gooseneck_length=inches(6),
            gooseneck_small_width=inches(1),
            gooseneck_large_width=inches(3),
            gooseneck_head_length=inches(2),
            lap_length=inches(3),
            gooseneck_depth=inches(2),
        )

        assert joint is not None
        assert len(joint.cuttings) == 2
        assert gooseneck_timber.ticket.path in joint.cuttings
        assert receiving_timber.ticket.path in joint.cuttings
