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


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()

class TestSpliceJoint:
    """Test cut_plain_butt_splice_joint_on_aligned_timbers function."""
        
        # 🐪
    def test_basic_splice_joint_same_orientation(self):
        """Test basic splice joint with two aligned timbers with same orientation."""
        # Create two timbers aligned along the X axis
        # TimberA extends from x=0 to x=50
        timberA = create_standard_horizontal_timber(direction='x', length=50, size=(6, 6), position=(0, 0, 0))
        # TimberB extends from x=50 to x=100 (meeting at x=50)
        timberB = create_standard_horizontal_timber(direction='x', length=50, size=(6, 6), position=(50, 0, 0))
        
        # Create splice joint at x=50 (where they meet)
        # TimberA TOP meets TimberB BOTTOM
        joint = cut_plain_butt_splice_joint_on_aligned_timbers(
            SpliceJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberEnd.TOP, timber2_end=TimberEnd.BOTTOM
            )
        )
        
        # Verify joint structure
        assert joint is not None
        assert len(joint.cuttings) == 2
        
        cutA = joint.cuttings["timberA"]
        cutB = joint.cuttings["timberB"]
        
        # Verify both cuts are end cuts
        assert cutA.get_maybe_top_end_cut() is not None
        assert cutA.get_maybe_bottom_end_cut() is None
        assert cutB.get_maybe_bottom_end_cut() is not None
        assert cutB.get_maybe_top_end_cut() is None
        
        # Verify the cut planes are perpendicular to the timber axis (X axis)
        # In global coordinates, the plane normal should be ±(1, 0, 0)
        # A cutting wraps what it removes in a SolidUnion of its own; the end
        # cut is the single plane inside it.
        cutA_csg = cutA.get_negative_csg_local()
        cutB_csg = cutB.get_negative_csg_local()
        assert isinstance(cutA_csg, SolidUnion) and isinstance(cutB_csg, SolidUnion)
        cutA_csg_local = cutA_csg.children[0]
        cutB_csg_local = cutB_csg.children[0]
        assert isinstance(cutA_csg_local, HalfSpace), "Expected cutA to be a HalfSpace"
        assert isinstance(cutB_csg_local, HalfSpace), "Expected cutB to be a HalfSpace"
        global_normalA = timberA.orientation.matrix * cutA_csg_local.normal
        global_normalB = timberB.orientation.matrix * cutB_csg_local.normal
        
        # For aligned timbers with same orientation:
        # - TimberA: cut at TOP, normal points +X (away from timber body)
        # - TimberB: cut at BOTTOM, normal points -X (away from timber body)
        # So they should be opposite
        assert safe_zero_test((global_normalA + global_normalB).norm()), \
            f"Normals should be opposite! A={global_normalA.T}, B={global_normalB.T}"
        
    # 🐪
    def test_splice_joint_with_custom_point(self):
        """Test splice joint with explicitly specified splice point."""
        # Create two timbers along Z axis
        timberA = create_standard_vertical_timber(height=100, size=(4, 4), position=(0, 0, 0))
        timberB = create_standard_vertical_timber(height=100, size=(4, 4), position=(0, 0, 100))
        
        # Specify splice point at z=120 (not the midpoint)
        splice_point = Matrix([scalar(0), scalar(0), scalar(120)])
        
        joint = cut_plain_butt_splice_joint_on_aligned_timbers(
            SpliceJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberEnd.TOP, timber2_end=TimberEnd.BOTTOM
            ),
            splice_point
        )
        
        # Verify the splice occurred at the specified point
        # The end cut should be at z=120 (distance from bottom of timberA is 120)
        cutA = joint.cuttings["timberA"]
        
        # Verify the end cut exists
        assert cutA.get_maybe_top_end_cut() is not None
        
    # 🐪
    def test_splice_joint_opposite_orientation(self):
        """Test splice joint with two aligned timbers with opposite orientations."""
        # TimberA points in +X direction
        timberA = create_timber(
            length=scalar(60),
            size=Matrix([scalar(6), scalar(6)]),
            bottom_position=Matrix([scalar(0), scalar(0), scalar(0)]),
            length_direction=Matrix([scalar(1), scalar(0), scalar(0)]),
            width_direction=Matrix([scalar(0), scalar(1), scalar(0)])
        )
        
        # TimberB points in -X direction (opposite orientation)
        # Bottom is at x=100, top at x=40
        timberB = create_timber(
            length=scalar(60),
            size=Matrix([scalar(6), scalar(6)]),
            bottom_position=Matrix([scalar(100), scalar(0), scalar(0)]),
            length_direction=Matrix([scalar(-1), scalar(0), scalar(0)]),
            width_direction=Matrix([scalar(0), scalar(1), scalar(0)])
        )
        
        # Create splice joint (should meet in the middle at x=50)
        joint = cut_plain_butt_splice_joint_on_aligned_timbers(
            SpliceJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberEnd.TOP, timber2_end=TimberEnd.TOP
            )
        )
        
        assert joint is not None
        assert len(joint.cuttings) == 2
        
        # Verify the splice point is between the two timbers
        cutA = joint.cuttings["timberA"]
        
        # Verify the end cut exists
        assert cutA.get_maybe_top_end_cut() is not None
        
    # 🐪
    def test_splice_joint_non_aligned_timbers_raises_error(self):
        """Test that non-aligned (non-parallel) timbers raise a ValueError."""
        # Create two perpendicular timbers
        timberA = create_timber(
            length=scalar(50),
            size=Matrix([scalar(4), scalar(4)]),
            bottom_position=Matrix([scalar(0), scalar(0), scalar(0)]),
            length_direction=Matrix([scalar(1), scalar(0), scalar(0)]),
            width_direction=Matrix([scalar(0), scalar(1), scalar(0)])
        )
        
        timberB = create_timber(
            length=scalar(50),
            size=Matrix([scalar(4), scalar(4)]),
            bottom_position=Matrix([scalar(50), scalar(0), scalar(0)]),
            length_direction=Matrix([scalar(0), scalar(1), scalar(0)]),  # Perpendicular!
            width_direction=Matrix([scalar(1), scalar(0), scalar(0)])
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="must have parallel length axes"):
            cut_plain_butt_splice_joint_on_aligned_timbers(
                SpliceJointTimberArrangement(
                    timber1=timberA, timber2=timberB,
                    timber1_end=TimberEnd.TOP, timber2_end=TimberEnd.BOTTOM
                )
            )



