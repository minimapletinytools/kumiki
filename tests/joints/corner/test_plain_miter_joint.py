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

class TestMiterJoint:
    """Test cut_plain_miter_joint function."""

    @staticmethod
    def assert_miter_joint_normals_are_opposite(joint, timberA, timberB):
        """
        Helper function to assert that miter joint cut normals are opposite in global space.
        
        Args:
            joint: The joint result from cut_plain_miter_joint_on_face_aligned_timbers
            timberA: First timber in the joint
            timberB: Second timber in the joint
        """
        # Get the local normals from the cuts
        cut_A_csg = joint.cuttings["timberA"].negative_csg
        cut_B_csg = joint.cuttings["timberB"].negative_csg
        assert isinstance(cut_A_csg, HalfSpace)
        assert isinstance(cut_B_csg, HalfSpace)
        normal_A_local = cut_A_csg.normal
        normal_B_local = cut_B_csg.normal
        
        # Convert to global coordinates
        normal_A_global = timberA.orientation.matrix * normal_A_local
        normal_B_global = timberB.orientation.matrix * normal_B_local
        
        # For a miter joint, the normals should be opposite in global space
        assert normal_A_global.equals(-normal_B_global), "Normals should be opposite in global space"
    
    @staticmethod
    def assert_miter_joint_end_positions_on_boundaries(joint, timberA, timberB):
        """
        Helper function to assert that the end positions of both cut timbers are on the 
        boundaries of both half planes.
        
        For a miter joint, the end position where timber A is cut should lie on the boundary
        of both timber A's cut plane and timber B's cut plane (and vice versa).
        
        Args:
            joint: The joint result from cut_plain_miter_joint_on_face_aligned_timbers
            timberA: First timber in the joint
            timberB: Second timber in the joint
        """
        # Get the end position of the cut on timberA (in global coordinates)
        end_position_A_global = locate_position_on_centerline_from_bottom(timberA, -3).position
        
        # Get the end position of the cut on timberB (in global coordinates)
        end_position_B_global = locate_position_on_centerline_from_bottom(timberB, -3).position
        
        # see that end_position_A_global is NOT in cut timberA but is in cut timberB
        assert not _render_cutting(joint.cuttings["timberA"]).contains_point(timberA.transform.global_to_local(end_position_A_global))
        assert _render_cutting(joint.cuttings["timberB"]).contains_point(timberB.transform.global_to_local(end_position_A_global))
        # see that end_position_B_global is NOT in cut timberB but is in cut timberA
        assert not _render_cutting(joint.cuttings["timberB"]).contains_point(timberB.transform.global_to_local(end_position_B_global))
        assert _render_cutting(joint.cuttings["timberA"]).contains_point(timberA.transform.global_to_local(end_position_B_global))


    @staticmethod
    def get_timber_bottom_position_after_cutting_local(timber: CutTimber) -> V3:
        prism = timber._extended_timber_without_cuts_csg_local()
        assert isinstance(prism, RectangularPrism)
        return prism.get_bottom_position()


    # 🐪
    def test_basic_miter_joint_on_orthoganal_timbers(self):
        """Test basic miter joint on face-aligned timbers."""
        # Create two orthognal timbers meeting at the origin
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        
        # Create miter joint
        arrangement = CornerJointTimberArrangement(
            timber1=timberA, timber2=timberB,
            timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
        )
        joint = cut_plain_miter_joint_on_face_aligned_timbers(arrangement)

        # check very basic stuff
        assert joint is not None
        assert len(joint.cuttings) == 2
        assert joint.cuttings["timberA"].timber == timberA
        assert joint.cuttings["timberA"].get_maybe_bottom_end_cut() is not None
        assert joint.cuttings["timberB"].timber == timberB
        assert joint.cuttings["timberB"].get_maybe_bottom_end_cut() is not None

        # check that the two cuts are Cut objects
        assert isinstance(joint.cuttings["timberA"], Cutting)
        assert isinstance(joint.cuttings["timberB"], Cutting)

        # Convert normals to global space and check if they are opposite
        self.assert_miter_joint_normals_are_opposite(joint, timberA, timberB)

        # Check that the end positions of both cut timbers are on the boundaries of both half planes
        self.assert_miter_joint_end_positions_on_boundaries(joint, timberA, timberB)

        # check that the "corner" point of the miter is contained on the boundary of both half plane
        corner_point_global = create_v3(scalar(-3), scalar(-3), scalar(0))
        corner_point_local_A = timberA.transform.global_to_local(corner_point_global)
        corner_point_local_B = timberB.transform.global_to_local(corner_point_global)
        assert joint.cuttings["timberA"].negative_csg is not None
        assert joint.cuttings["timberB"].negative_csg is not None
        assert joint.cuttings["timberA"].negative_csg.is_point_on_boundary(corner_point_local_A)
        assert joint.cuttings["timberB"].negative_csg.is_point_on_boundary(corner_point_local_B)

        # check that the "bottom" point of timberA (after cutting) is contained in timberB but not timber A
        # This point is at (0, -3, 0) in global coordinates, which is:
        # - On the "cut away" side of timber A (should NOT be contained)
        # - On the "kept" side of timber B (should be contained)
        bottom_point_A_after_cutting_global = create_v3(scalar(0), scalar(-3), scalar(0))
        bottom_point_A_after_cutting_local_A = timberA.transform.global_to_local(bottom_point_A_after_cutting_global)
        bottom_point_A_after_cutting_local_B = timberB.transform.global_to_local(bottom_point_A_after_cutting_global)
        assert joint.cuttings["timberA"].negative_csg is not None
        assert joint.cuttings["timberB"].negative_csg is not None
        assert not joint.cuttings["timberA"].negative_csg.contains_point(bottom_point_A_after_cutting_local_A)
        assert joint.cuttings["timberB"].negative_csg.contains_point(bottom_point_A_after_cutting_local_B)

    # 🐪
    def test_basic_miter_joint_on_various_angles(self): 
        """Test miter joints with timbers at 90-degree angle in various orientations."""
        # Note: cut_plain_miter_joint_on_face_aligned_timbers requires perpendicular timbers (90-degree angle)
        # We test various orientations of perpendicular timber pairs
        
        test_cases = [
            # (timberA_direction, timberB_direction, description)
            ('x', 'y', 'X and Y perpendicular'),
            ('x', '-y', 'X and -Y perpendicular'),
            ('-x', 'y', '-X and Y perpendicular'),
            ('-x', '-y', '-X and -Y perpendicular'),
        ]
        
        for dirA, dirB, description in test_cases:
            # Create timberA and timberB in perpendicular directions
            timberA = create_standard_horizontal_timber(direction=dirA, length=100, size=(6, 6), position=(0, 0, 0))
            timberB = create_standard_horizontal_timber(direction=dirB, length=100, size=(6, 6), position=(0, 0, 0))
            
            # Create miter joint
            arrangement = CornerJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
            )
            joint = cut_plain_miter_joint_on_face_aligned_timbers(arrangement)
            
            # Verify the joint was created
            assert joint is not None, f"Failed to create joint for {description}"
            assert len(joint.cuttings) == 2
            
            # Verify the cuts are Cut objects
            assert isinstance(joint.cuttings["timberA"], Cutting)
            assert isinstance(joint.cuttings["timberB"], Cutting)
            
            # Verify normals are opposite in global space
            self.assert_miter_joint_normals_are_opposite(joint, timberA, timberB)
            
            # Verify end positions are on boundaries of both half planes
            self.assert_miter_joint_end_positions_on_boundaries(joint, timberA, timberB)

    # 🐪
    def test_basic_miter_joint_on_parallel_timbers(self):
        """Test that creating miter joint between parallel timbers raises an error."""
        # Create three timbers: two parallel (+X) and one anti-parallel (-X)
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberC = create_standard_horizontal_timber(direction='-x', length=100, size=(6, 6), position=(0, 0, 0))
        
        # Attempting to create a miter joint between parallel timbers should raise an AssertionError
        # because the function requires perpendicular timbers
        with pytest.raises(AssertionError, match="perpendicular"):
            arrangement = CornerJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
            )
            cut_plain_miter_joint_on_face_aligned_timbers(arrangement)
        
        # Test with anti-parallel timbers as well
        with pytest.raises(AssertionError, match="perpendicular"):
            arrangement = CornerJointTimberArrangement(
                timber1=timberA, timber2=timberC,
                timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
            )
            cut_plain_miter_joint_on_face_aligned_timbers(arrangement)

    # 🐪
    def test_miter_joint_on_parallel_timbers_produces_perpendicular_cuts(self):
        """cut_plain_miter_joint (base function) accepts parallel timbers and produces end cuts perpendicular to the timber axis."""
        timberA = create_timber(
            length=scalar(100),
            size=Matrix([scalar(6), scalar(6)]),
            bottom_position=Matrix([scalar(0), scalar(0), scalar(0)]),
            length_direction=Matrix([scalar(1), scalar(0), scalar(0)]),
            width_direction=Matrix([scalar(0), scalar(1), scalar(0)]),
        )
        timberB = create_timber(
            length=scalar(100),
            size=Matrix([scalar(6), scalar(6)]),
            bottom_position=Matrix([scalar(0), scalar(0), scalar(10)]),
            length_direction=Matrix([scalar(1), scalar(0), scalar(0)]),
            width_direction=Matrix([scalar(0), scalar(1), scalar(0)]),
        )

        arrangement = CornerJointTimberArrangement(
            timber1=timberA, timber2=timberB,
            timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM,
        )
        joint = cut_plain_miter_joint(arrangement)

        assert joint is not None
        assert len(joint.cuttings) == 2

        for key, timber in [("timberA", timberA), ("timberB", timberB)]:
            cut = joint.cuttings[key]
            end_cut = cut.get_maybe_bottom_end_cut()
            assert end_cut is not None, f"{key} should have a bottom end cut"
            global_normal = timber.orientation.matrix * end_cut.normal
            length_dir = timber.get_length_direction_global()
            dot = simplify(Abs((global_normal.T * length_dir)[0, 0]))
            assert dot == 1, f"{key} end cut should be perpendicular to timber axis, got |dot|={dot}"



