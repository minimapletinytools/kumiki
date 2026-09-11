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

class TestTongueAndForkButtJoint:
    def test_tongue_and_fork_butt_joint_structure_and_no_tongue_end_cut(self):
        """
        Verify the butt variant produces the right structure:
        - Fork timber (butt timber) gets a slot and an end cut.
        - Tongue timber (receiving timber) gets cheek removal and NO end cut.
        """
        fork_butt_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        tongue_rec_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, -50, 0))

        arrangement = ButtJointTimberArrangement(
            butt_timber=fork_butt_timber,
            receiving_timber=tongue_rec_timber,
            butt_timber_end=TimberEnd.TOP,
        )
        joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement)

        assert len(joint.cuttings) == 2
        assert "tongue_timber" in joint.cuttings
        assert "fork_timber" in joint.cuttings

        tongue_cut = joint.cuttings["tongue_timber"]
        fork_cut = joint.cuttings["fork_timber"]

        # Fork timber (butt timber) has slot and end cut
        assert fork_cut.negative_csg is not None
        assert fork_cut.get_maybe_top_end_cut() is not None

        # Tongue timber (receiving timber) has cheek removal but NO end cut
        assert tongue_cut.negative_csg is not None
        assert tongue_cut.get_maybe_top_end_cut() is None
        assert tongue_cut.get_maybe_bottom_end_cut() is None

        # Verify cuts produce valid CSG
        tongue_csg = _render_cutting(joint.cuttings["tongue_timber"])
        fork_csg = _render_cutting(joint.cuttings["fork_timber"])
        assert tongue_csg is not None
        assert fork_csg is not None

    def test_tongue_and_fork_butt_joint_angled_end_cut_extends_to_furthest_tip(self):
        """
        Verify that for an angled joint, the end cut distance extends further out than
        the centerline intersection distance to encompass the full angled cut.
        """
        from patterns.butt.tongue_and_fork_butt_joint_patterns import make_tongue_and_fork_butt_joint_angled_example
        cut_timbers = make_tongue_and_fork_butt_joint_angled_example(create_v3(0, 0, 0))
        fork_cut_timber = [ct for ct in cut_timbers if "butt" in str(ct.timber.ticket)][0]
        fork_cut = fork_cut_timber.cuts[0]

        assert fork_cut.maybe_bottom_end_cut_distance_from_bottom is not None
        # At 138 degrees, the furthest tip distance is strictly less (further into joint / further out from top)
        # than the centerline intersection distance
        assert safe_compare(fork_cut.maybe_bottom_end_cut_distance_from_bottom, 0, Comparison.LT)

    def test_tongue_and_fork_butt_joint_shoulder_inset(self):
        """
        Verify that shoulder_inset recesses the shoulder plane into the receiving timber,
        housing the fork timber's stem and forming the tongue deeper inside.
        """
        fork_butt_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        tongue_rec_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, -50, 0))

        arrangement = ButtJointTimberArrangement(
            butt_timber=fork_butt_timber,
            receiving_timber=tongue_rec_timber,
            butt_timber_end=TimberEnd.TOP,
        )
        joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(
            arrangement=arrangement,
            shoulder_inset=inches(1),
        )

        assert len(joint.cuttings) == 2
        tongue_cut = joint.cuttings["tongue_timber"]
        fork_cut = joint.cuttings["fork_timber"]

        assert tongue_cut.negative_csg is not None
        assert fork_cut.negative_csg is not None

        tongue_csg = _render_cutting(tongue_cut)
        fork_csg = _render_cutting(fork_cut)
        assert tongue_csg is not None
        assert fork_csg is not None




# NOTE: mortise-and-tenon joint tests (TestMortiseAndTenonGeometry, TestMortiseAndTenonRelativeTenonSizing,
# TestPegStuff, TestMortiseAndTenonCSGHierarchy, TestWedgedHalfDovetailMortiseAndTenonJoint) live in
# test_mortise_and_tenon_joints.py now.
