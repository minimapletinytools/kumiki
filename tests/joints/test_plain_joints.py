"""
Tests for Kumiki timber framing system
"""

import pytest
from sympy import Matrix, sqrt, simplify, Abs, Float, Rational, pi
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber
)



# ============================================================================
# Tests for plain_joints.py - Joint Construction Functions
# ============================================================================

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
        normal_A_local = joint.cut_timbers["timberA"].cuts[0].get_negative_csg_local().normal
        normal_B_local = joint.cut_timbers["timberB"].cuts[0].get_negative_csg_local().normal
        
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
        assert not joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local().contains_point(timberA.transform.global_to_local(end_position_A_global))
        assert joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local().contains_point(timberB.transform.global_to_local(end_position_A_global))
        # see that end_position_B_global is NOT in cut timberB but is in cut timberA
        assert not joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local().contains_point(timberB.transform.global_to_local(end_position_B_global))
        assert joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local().contains_point(timberA.transform.global_to_local(end_position_B_global))


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
            timber1_end=TimberReferenceEnd.BOTTOM, timber2_end=TimberReferenceEnd.BOTTOM
        )
        joint = cut_plain_miter_joint_on_face_aligned_timbers(arrangement)

        # check very basic stuff
        assert joint is not None
        assert len(joint.cut_timbers) == 2
        assert joint.cut_timbers["timberA"].timber == timberA
        assert joint.cut_timbers["timberA"].cuts[0].maybe_bottom_end_cut is not None
        assert joint.cut_timbers["timberA"].cuts[0].maybe_top_end_cut is None
        assert joint.cut_timbers["timberB"].timber == timberB
        assert joint.cut_timbers["timberB"].cuts[0].maybe_bottom_end_cut is not None
        assert joint.cut_timbers["timberB"].cuts[0].maybe_top_end_cut is None

        # check that the two cuts are Cut objects
        assert isinstance(joint.cut_timbers["timberA"].cuts[0], Cutting)
        assert isinstance(joint.cut_timbers["timberB"].cuts[0], Cutting)

        # Convert normals to global space and check if they are opposite
        self.assert_miter_joint_normals_are_opposite(joint, timberA, timberB)

        # Check that the end positions of both cut timbers are on the boundaries of both half planes
        self.assert_miter_joint_end_positions_on_boundaries(joint, timberA, timberB)

        # check that the "corner" point of the miter is contained on the boundary of both half plane
        corner_point_global = create_v3(Rational(-3), Rational(-3), Rational(0))
        corner_point_local_A = timberA.transform.global_to_local(corner_point_global)
        corner_point_local_B = timberB.transform.global_to_local(corner_point_global)
        assert joint.cut_timbers["timberA"].cuts[0].get_negative_csg_local().is_point_on_boundary(corner_point_local_A)
        assert joint.cut_timbers["timberB"].cuts[0].get_negative_csg_local().is_point_on_boundary(corner_point_local_B)

        # check that the "bottom" point of timberA (after cutting) is contained in timberB but not timber A
        # This point is at (0, -3, 0) in global coordinates, which is:
        # - On the "cut away" side of timber A (should NOT be contained)
        # - On the "kept" side of timber B (should be contained)
        bottom_point_A_after_cutting_global = create_v3(Rational(0), Rational(-3), Rational(0))
        bottom_point_A_after_cutting_local_A = timberA.transform.global_to_local(bottom_point_A_after_cutting_global)
        bottom_point_A_after_cutting_local_B = timberB.transform.global_to_local(bottom_point_A_after_cutting_global)
        assert not joint.cut_timbers["timberA"].cuts[0].get_negative_csg_local().contains_point(bottom_point_A_after_cutting_local_A)
        assert joint.cut_timbers["timberB"].cuts[0].get_negative_csg_local().contains_point(bottom_point_A_after_cutting_local_B)

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
                timber1_end=TimberReferenceEnd.BOTTOM, timber2_end=TimberReferenceEnd.BOTTOM
            )
            joint = cut_plain_miter_joint_on_face_aligned_timbers(arrangement)
            
            # Verify the joint was created
            assert joint is not None, f"Failed to create joint for {description}"
            assert len(joint.cut_timbers) == 2
            
            # Verify the cuts are Cut objects
            assert isinstance(joint.cut_timbers["timberA"].cuts[0], Cutting)
            assert isinstance(joint.cut_timbers["timberB"].cuts[0], Cutting)
            
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
                timber1_end=TimberReferenceEnd.BOTTOM, timber2_end=TimberReferenceEnd.BOTTOM
            )
            cut_plain_miter_joint_on_face_aligned_timbers(arrangement)
        
        # Test with anti-parallel timbers as well
        with pytest.raises(AssertionError, match="perpendicular"):
            arrangement = CornerJointTimberArrangement(
                timber1=timberA, timber2=timberC,
                timber1_end=TimberReferenceEnd.BOTTOM, timber2_end=TimberReferenceEnd.BOTTOM
            )
            cut_plain_miter_joint_on_face_aligned_timbers(arrangement)


        

class TestButtJoint:
    """Test cut_plain_butt_joint_on_face_aligned_timbers function."""

    # 🐪
    def test_basic_butt_joint_on_face_aligned_timbers(self, symbolic_mode):
        """Test butt joint between two perpendicular timbers."""
        # Create two perpendicular timbers meeting at the origin
        # timberA extends along +X (bottom at origin, top at x=100)
        # timberB extends along +Y (bottom at origin, top at y=100)
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))

        # Create butt joint - timberB butts into timberA at timberB's BOTTOM end
        arrangement = ButtJointTimberArrangement(
            butt_timber=timberB,
            receiving_timber=timberA,
            butt_timber_end=TimberReferenceEnd.BOTTOM
        )
        joint = cut_plain_butt_joint_on_face_aligned_timbers(arrangement)

        # Verify joint structure
        assert joint is not None
        assert len(joint.cut_timbers) == 2
        assert joint.cut_timbers["receiving_timber"].timber == timberA
        assert joint.cut_timbers["butt_timber"].timber == timberB

        # In a butt joint, the receiving timber (timberA) should have no cuts
        assert len(joint.cut_timbers["receiving_timber"].cuts) == 0, "Receiving timber should have no cuts"

        # The butt timber (timberB) should have exactly one cut at the specified end
        assert len(joint.cut_timbers["butt_timber"].cuts) == 1, "Butt timber should have one cut"
        assert joint.cut_timbers["butt_timber"].cuts[0].maybe_bottom_end_cut is not None
        assert joint.cut_timbers["butt_timber"].cuts[0].maybe_top_end_cut is None

        # Verify the cut is a Cut object
        assert isinstance(joint.cut_timbers["butt_timber"].cuts[0], Cutting)

        # Verify that the cut normal in global space is parallel or anti-parallel to timberB's length direction
        # For an end cut (butt joint), the cut plane is perpendicular to the timber's length axis,
        # so the normal is parallel/anti-parallel to the length direction
        cut_csg_local = joint.cut_timbers["butt_timber"].cuts[0].get_negative_csg_local()
        assert isinstance(cut_csg_local, HalfSpace), "Expected cut to be a HalfSpace"
        cut_normal_local = cut_csg_local.normal
        cut_normal_global = timberB.orientation.matrix * cut_normal_local
        
        dot_with_length = (cut_normal_global.T * timberB.get_length_direction_global())[0, 0]
        from sympy import simplify, Abs
        assert simplify(Abs(dot_with_length)) == 1, \
            "Cut normal should be parallel or anti-parallel to butt timber's length direction"
        
        # Verify the cut creates a valid CSG geometry
        # (this is a basic sanity check that the cut can be rendered)
        try:
            csg = joint.cut_timbers["butt_timber"].render_timber_with_cuts_csg_local()
            assert csg is not None, "Should be able to render the cut timber"
        except Exception as e:
            pytest.fail(f"Failed to render cut timber: {e}")

        # pick a point that's on the boundary of the butt joint
        joint_point_global = create_v3(Rational(0), Rational(3), Rational(0))

        assert joint.cut_timbers["receiving_timber"].render_timber_with_cuts_csg_local().is_point_on_boundary(timberA.transform.global_to_local(joint_point_global))
        assert joint.cut_timbers["butt_timber"].render_timber_with_cuts_csg_local().is_point_on_boundary(timberB.transform.global_to_local(joint_point_global))
        



    # 🐪
    def test_basic_butt_joint_on_parallel_timbers(self):
        """Test that creating butt joint between parallel timbers raises an error.
        
        The cut_plain_butt_joint_on_face_aligned_timbers function validates that timbers
        are not parallel, as butt joints require timbers at an angle.
        """
        # Create three timbers: two parallel (+X) and one anti-parallel (-X)
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberC = create_standard_horizontal_timber(direction='-x', length=100, size=(6, 6), position=(0, 0, 0))
        
        # Attempting to create a butt joint between parallel timbers should raise an AssertionError
        # because the function requires perpendicular timbers
        with pytest.raises(AssertionError, match="parallel"):
            arrangement = ButtJointTimberArrangement(
                butt_timber=timberB,
                receiving_timber=timberA,
                butt_timber_end=TimberReferenceEnd.BOTTOM
            )
            cut_plain_butt_joint_on_face_aligned_timbers(arrangement)
        
        # Test with anti-parallel timbers as well
        with pytest.raises(AssertionError, match="parallel"):
            arrangement = ButtJointTimberArrangement(
                butt_timber=timberC,
                receiving_timber=timberA,
                butt_timber_end=TimberReferenceEnd.BOTTOM
            )
            cut_plain_butt_joint_on_face_aligned_timbers(arrangement)


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
                timber1_end=TimberReferenceEnd.TOP, timber2_end=TimberReferenceEnd.BOTTOM
            )
        )
        
        # Verify joint structure
        assert joint is not None
        assert len(joint.cut_timbers) == 2
        
        cutA = joint.cut_timbers["timberA"].cuts[0]
        cutB = joint.cut_timbers["timberB"].cuts[0]
        
        # Verify both cuts are end cuts
        assert cutA.maybe_top_end_cut is not None
        assert cutA.maybe_bottom_end_cut is None
        assert cutB.maybe_bottom_end_cut is not None
        assert cutB.maybe_top_end_cut is None
        
        # Verify the cut planes are perpendicular to the timber axis (X axis)
        # In global coordinates, the plane normal should be ±(1, 0, 0)
        cutA_csg_local = cutA.get_negative_csg_local()
        cutB_csg_local = cutB.get_negative_csg_local()
        assert isinstance(cutA_csg_local, HalfSpace), "Expected cutA to be a HalfSpace"
        assert isinstance(cutB_csg_local, HalfSpace), "Expected cutB to be a HalfSpace"
        global_normalA = timberA.orientation.matrix * cutA_csg_local.normal
        global_normalB = timberB.orientation.matrix * cutB_csg_local.normal
        
        # For aligned timbers with same orientation:
        # - TimberA: cut at TOP, normal points +X (away from timber body)
        # - TimberB: cut at BOTTOM, normal points -X (away from timber body)
        # So they should be opposite
        assert simplify(global_normalA + global_normalB).norm() == 0, \
            f"Normals should be opposite! A={global_normalA.T}, B={global_normalB.T}"
        
    # 🐪
    def test_splice_joint_with_custom_point(self):
        """Test splice joint with explicitly specified splice point."""
        # Create two timbers along Z axis
        timberA = create_standard_vertical_timber(height=100, size=(4, 4), position=(0, 0, 0))
        timberB = create_standard_vertical_timber(height=100, size=(4, 4), position=(0, 0, 100))
        
        # Specify splice point at z=120 (not the midpoint)
        splice_point = Matrix([Rational(0), Rational(0), Rational(120)])
        
        joint = cut_plain_butt_splice_joint_on_aligned_timbers(
            SpliceJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberReferenceEnd.TOP, timber2_end=TimberReferenceEnd.BOTTOM
            ),
            splice_point
        )
        
        # Verify the splice occurred at the specified point
        # The end cut should be at z=120 (distance from bottom of timberA is 120)
        cutA = joint.cut_timbers["timberA"].cuts[0]
        
        # Verify the end cut exists
        assert cutA.maybe_top_end_cut is not None
        
    # 🐪
    def test_splice_joint_opposite_orientation(self):
        """Test splice joint with two aligned timbers with opposite orientations."""
        # TimberA points in +X direction
        timberA = timber_from_directions(
            length=Rational(60),
            size=Matrix([Rational(6), Rational(6)]),
            bottom_position=Matrix([Rational(0), Rational(0), Rational(0)]),
            length_direction=Matrix([Rational(1), Rational(0), Rational(0)]),
            width_direction=Matrix([Rational(0), Rational(1), Rational(0)])
        )
        
        # TimberB points in -X direction (opposite orientation)
        # Bottom is at x=100, top at x=40
        timberB = timber_from_directions(
            length=Rational(60),
            size=Matrix([Rational(6), Rational(6)]),
            bottom_position=Matrix([Rational(100), Rational(0), Rational(0)]),
            length_direction=Matrix([Rational(-1), Rational(0), Rational(0)]),
            width_direction=Matrix([Rational(0), Rational(1), Rational(0)])
        )
        
        # Create splice joint (should meet in the middle at x=50)
        joint = cut_plain_butt_splice_joint_on_aligned_timbers(
            SpliceJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberReferenceEnd.TOP, timber2_end=TimberReferenceEnd.TOP
            )
        )
        
        assert joint is not None
        assert len(joint.cut_timbers) == 2
        
        # Verify the splice point is between the two timbers
        cutA = joint.cut_timbers["timberA"].cuts[0]
        
        # Verify the end cut exists
        assert cutA.maybe_top_end_cut is not None
        
    # 🐪
    def test_splice_joint_non_aligned_timbers_raises_error(self):
        """Test that non-aligned (non-parallel) timbers raise a ValueError."""
        # Create two perpendicular timbers
        timberA = timber_from_directions(
            length=Rational(50),
            size=Matrix([Rational(4), Rational(4)]),
            bottom_position=Matrix([Rational(0), Rational(0), Rational(0)]),
            length_direction=Matrix([Rational(1), Rational(0), Rational(0)]),
            width_direction=Matrix([Rational(0), Rational(1), Rational(0)])
        )
        
        timberB = timber_from_directions(
            length=Rational(50),
            size=Matrix([Rational(4), Rational(4)]),
            bottom_position=Matrix([Rational(50), Rational(0), Rational(0)]),
            length_direction=Matrix([Rational(0), Rational(1), Rational(0)]),  # Perpendicular!
            width_direction=Matrix([Rational(1), Rational(0), Rational(0)])
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="must have parallel length axes"):
            cut_plain_butt_splice_joint_on_aligned_timbers(
                SpliceJointTimberArrangement(
                    timber1=timberA, timber2=timberB,
                    timber1_end=TimberReferenceEnd.TOP, timber2_end=TimberReferenceEnd.BOTTOM
                )
            )


class TestHouseJoint:
    """Test cut_plain_house_joint function."""
    
    # 🐪
    def test_basic_house_joint_perpendicular_timbers(self):
        """Test that a house joint between two perpendicular timbers is created correctly."""


        # create 2 timbers in an X shape
        housing_timber = create_centered_horizontal_timber(direction='x', length=100, size=(10, 10), zoffset=1)
        housed_timber = create_centered_horizontal_timber(direction='y', length=100, size=(10, 10), zoffset=-1)

        arrangement = CrossJointTimberArrangement(timber1=housing_timber, timber2=housed_timber)
        joint = cut_plain_house_joint(arrangement)
        assert joint is not None
        assert len(joint.cut_timbers) == 2
        assert joint.cut_timbers["timberA"].timber == housing_timber
        assert joint.cut_timbers["timberB"].timber == housed_timber

        assert len(joint.cut_timbers["timberA"].cuts) == 1
        assert len(joint.cut_timbers["timberB"].cuts) == 0
        
        assert joint.cut_timbers["timberA"].cuts[0].maybe_top_end_cut is None
        assert joint.cut_timbers["timberA"].cuts[0].maybe_bottom_end_cut is None

        # test that the origin point lies in the housed timber but not the housing timber
        origin = create_v3(Rational(0), Rational(0), Rational(0))
        assert not joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local().contains_point(housing_timber.transform.global_to_local(origin))
        assert joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local().contains_point(housed_timber.transform.global_to_local(origin))
        

    def test_house_joint_prism_matches_housed_timber_global_space(self, symbolic_mode):
        """
        Test that the prism being cut from the housing timber matches the housed timber
        when both are compared in global coordinates.
        """
        from kumiki.cutcsg import RectangularPrism
        
        # Create housing timber (vertical post)
        housing_timber = create_standard_vertical_timber(height=200, size=(10, 10), position=(0, 0, 0))
        
        # Create housed timber (horizontal beam intersecting the post)
        housed_timber = timber_from_directions(
            length=Rational(80),
            size=Matrix([Rational(6), Rational(6)]),  # 6 x 6 beam
            bottom_position=Matrix([Rational(-20), Rational(0), Rational(100)]),
            length_direction=Matrix([Rational(1), Rational(0), Rational(0)]),  # Horizontal
            width_direction=Matrix([Rational(0), Rational(1), Rational(0)])
        )
        
        # Create the housed joint
        # Explicitly specify the housing timber cut face: FRONT (+Y)
        # The housed timber cut face is automatically computed as the opposite
        arrangement = CrossJointTimberArrangement(
            timber1=housing_timber,
            timber2=housed_timber,
            front_face_on_timber1=TimberLongFace.FRONT
        )
        joint = cut_plain_house_joint(arrangement)
        
        # Get the housing timber with its cut
        housing_cut_timber = joint.cut_timbers["timberA"]
        cut = housing_cut_timber.cuts[0]
        
        assert isinstance(cut, Cutting), "Cut should be a Cutting object"
        
        # Get the negative CSG (the prism being cut away)
        # This is in the housing timber's LOCAL coordinate system
        # Note: The new implementation uses a Difference(RectangularPrism, HalfSpace) for the cross lap joint
        from kumiki.cutcsg import Difference
        cut_csg_local = cut.negative_csg
        assert isinstance(cut_csg_local, Difference), "Negative CSG should be a Difference (cross lap implementation)"
        
        # Extract the base prism from the Difference
        cut_prism_local = cut_csg_local.base
        assert isinstance(cut_prism_local, RectangularPrism), "Base of Difference should be a RectangularPrism"
        
        # ===================================================================
        # Compare the cut prism with the housed timber in GLOBAL space
        # ===================================================================
        
        # 1. The prism's size should match the housed timber's size
        assert cut_prism_local.size[0] == housed_timber.size[0], \
            f"Cut prism width should match housed timber width: {cut_prism_local.size[0]} vs {housed_timber.size[0]}"
        assert cut_prism_local.size[1] == housed_timber.size[1], \
            f"Cut prism height should match housed timber height: {cut_prism_local.size[1]} vs {housed_timber.size[1]}"
        
        # 2. Check the prism's orientation in global space
        # cut_prism_local.transform.orientation is relative to housing timber's local frame
        # Global orientation = housing_orientation * local_orientation
        cut_prism_global_orientation = housing_timber.orientation.multiply(cut_prism_local.transform.orientation)
        
        # The prism's orientation should match the housed timber's orientation
        # (they should be aligned in the same direction)
        orientation_diff = cut_prism_global_orientation.matrix - housed_timber.orientation.matrix
        orientation_diff_norm = simplify(orientation_diff.norm())
        
        assert orientation_diff_norm == 0, \
            f"Cut prism orientation should exactly match housed timber orientation in global space. Difference: {orientation_diff_norm}"
        
        # 3. Check that the prism extends along the housed timber's length direction
        # The prism's length direction (in housing timber's local coords) should match
        # the housed timber's length direction (also in housing timber's local coords)
        
        housed_length_dir_in_housing_local = housing_timber.orientation.matrix.T * housed_timber.get_length_direction_global()
        prism_length_dir_in_housing_local = cut_prism_local.transform.orientation.matrix[:, 2]  # Z-axis of prism
        
        # These should be parallel (same or opposite direction)
        dot = simplify((housed_length_dir_in_housing_local.T * prism_length_dir_in_housing_local)[0, 0])
        assert abs(dot) == 1, \
            f"Cut prism length direction should be exactly parallel to housed timber length direction. Dot product: {dot}"
    


class TestCrossLapJoint:
    # 🐪
    def test_basic_cross_lap_joint_perpendicular_timbers(self):
        """Test that a cross lap joint between two perpendicular timbers is created correctly."""


        # create 2 timbers in an X shape
        timberA = create_centered_horizontal_timber(direction='x', length=100, size=(10, 10), zoffset=1)
        timberB = create_centered_horizontal_timber(direction='y', length=100, size=(10, 10), zoffset=-1)

        arrangement = CrossJointTimberArrangement(timber1=timberA, timber2=timberB)
        joint = cut_plain_cross_lap_joint(arrangement)

        assert joint is not None
        assert len(joint.cut_timbers) == 2
        assert joint.cut_timbers["timberA"].timber == timberA
        assert joint.cut_timbers["timberB"].timber == timberB
        assert len(joint.cut_timbers["timberA"].cuts) == 1
        assert len(joint.cut_timbers["timberB"].cuts) == 1
        assert joint.cut_timbers["timberA"].cuts[0].maybe_top_end_cut is None
        assert joint.cut_timbers["timberA"].cuts[0].maybe_bottom_end_cut is None
        assert joint.cut_timbers["timberB"].cuts[0].maybe_top_end_cut is None
        assert joint.cut_timbers["timberB"].cuts[0].maybe_bottom_end_cut is None

        # test that the origin point lies on the boundary of both timbers
        origin = create_v3(Rational(0), Rational(0), Rational(0))
        assert joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local().contains_point(timberA.transform.global_to_local(origin))
        assert joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local().contains_point(timberB.transform.global_to_local(origin))

        assert joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local().is_point_on_boundary(timberA.transform.global_to_local(origin))
        assert joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local().is_point_on_boundary(timberB.transform.global_to_local(origin))

        # above origin
        origin = create_v3(Rational(0), Rational(0), Rational(1))
        assert joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local().contains_point(timberA.transform.global_to_local(origin))
        assert not joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local().contains_point(timberB.transform.global_to_local(origin))

        # below origin
        origin = create_v3(Rational(0), Rational(0), Rational(-1))
        assert not joint.cut_timbers["timberA"].render_timber_with_cuts_csg_local().contains_point(timberA.transform.global_to_local(origin))
        assert joint.cut_timbers["timberB"].render_timber_with_cuts_csg_local().contains_point(timberB.transform.global_to_local(origin))


class TestSpliceLapJoint:
    """Test cut_plain_splice_lap_joint_on_aligned_timbers function."""
    
    def test_splice_lap_joint_geometry(self, symbolic_mode):
        """
        Test splice lap joint creates correct geometry with proper containment.
        
        Tests:
        1. Points outside the ends on centerline are not contained
        2. Points along a line perpendicular to the lap face show correct containment
        """
        from sympy import Rational
        
        # Create two aligned timbers meeting end-to-end
        timber_length = 20
        timber_size = create_v2(4, 4)
        
        # TimberA extends from x=0 to x=20
        timberA = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timberA'
        )
        
        # TimberB extends from x=20 to x=40
        timberB = timber_from_directions(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(20, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timberB'
        )
        
        # Create splice lap joint
        lap_length = 6
        shoulder_distance = 2
        
        joint = cut_plain_splice_lap_joint_on_aligned_timbers(
            arrangement=SpliceJointTimberArrangement(
                timber1=timberA,
                timber2=timberB,
                timber1_end=TimberReferenceEnd.TOP,
                timber2_end=TimberReferenceEnd.BOTTOM,
                front_face_on_timber1=TimberLongFace.BACK
            ),
            lap_length=lap_length,
            top_lap_shoulder_position_from_top_lap_shoulder_timber_end=shoulder_distance,
            lap_depth=None  # Use default
        )
        
        # Verify joint was created
        assert joint is not None
        assert len(joint.cut_timbers) == 2
        
        # Get the cut timbers
        cut_timberA = joint.cut_timbers['top_lap_timber']
        cut_timberB = joint.cut_timbers['bottom_lap_timber']
        
        # Verify each has exactly one cut
        assert len(cut_timberA.cuts) == 1
        assert len(cut_timberB.cuts) == 1
        
        # Render the CSGs
        csg_A = cut_timberA.render_timber_with_cuts_csg_local()
        csg_B = cut_timberB.render_timber_with_cuts_csg_local()
        
        # Test 1: Points outside the ends on centerline should not be contained
        point_before_A = create_v3(-5, 0, 0)
        point_before_A_local = timberA.transform.global_to_local(point_before_A)
        assert not csg_A.contains_point(point_before_A_local), \
            "Point before timberA should not be contained"
        
        point_after_B = create_v3(45, 0, 0)
        point_after_B_local = timberB.transform.global_to_local(point_after_B)
        assert not csg_B.contains_point(point_after_B_local), \
            "Point after timberB should not be contained"
        
        # Test 2: Points in the middle of each timber (before lap region) should be contained
        point_middle_A = create_v3(10, 0, 0)  # Well before lap at x=18
        point_middle_A_local = timberA.transform.global_to_local(point_middle_A)
        assert csg_A.contains_point(point_middle_A_local), \
            "Point in middle of timberA (before lap) should be contained"
        
        point_middle_B = create_v3(30, 0, 0)  # After lap region (lap ends at x=24)
        point_middle_B_local = timberB.transform.global_to_local(point_middle_B)
        assert csg_B.contains_point(point_middle_B_local), \
            "Point in middle of timberB (after lap) should be contained"
        
        # Test 3: Walk perpendicular to top lap face checking containment at different depths
        # Pick a point in the lap region on the cut face of timberA
        # The lap_depth defaults to half of timberA's height: 4/2 = 2
        lap_depth = Rational(4) / 2  # 2
        
        # Choose x_in_lap to be in the overlap region where both timbers have laps
        # TimberA lap: x=18-shoulder_distance to x=18, then lap extends beyond
        # Let's pick x=19 which is definitely in the lap region
        x_in_lap = 19
        
        # NEW LOGIC: With top_lap_timber_face=BACK:
        # - BACK face is at z=-2 (timber is 4x4 centered at y=0, z=0)
        # - lap_depth=2 means we KEEP 2" on the BACK side (z=-2 to z=0)
        # - We REMOVE material from the FRONT side (z=0 to z=+2)
        # - TimberA remains at global Z in [-2, 0]
        #
        # For timberB (opposing lap):
        # - Opposing face is FRONT (opposite of BACK)
        # - TimberB keeps material on FRONT side (z=0 to z=+2)
        # - TimberB removes material from BACK side (z=-2 to z=0)
        # - TimberB remains at global Z in [0, +2]
        
        # At z=-epsilon: Just inside timberA's kept region (BACK side), should be in timberA but not in timberB
        epsilon = Rational(1, 10)  # Small offset
        point_in_A = create_v3(x_in_lap, 0, -epsilon)  # Just below Z=0 (in timberA's kept region)
        point_in_A_local = timberA.transform.global_to_local(point_in_A)
        point_in_A_as_B_local = timberB.transform.global_to_local(point_in_A)
        
        assert csg_A.contains_point(point_in_A_local), \
            "Point in timberA's kept region (z=-epsilon) should be contained in timberA"
        assert not csg_B.contains_point(point_in_A_as_B_local), \
            "Point in timberA's kept region (z=-epsilon) should NOT be contained in timberB"
        
        # At z=0: on the boundary where the two timbers meet
        point_at_boundary = create_v3(x_in_lap, 0, 0)
        point_at_boundary_A_local = timberA.transform.global_to_local(point_at_boundary)
        point_at_boundary_B_local = timberB.transform.global_to_local(point_at_boundary)
        
        # At the boundary, the point should be contained in both (on their surfaces)
        assert csg_A.contains_point(point_at_boundary_A_local), \
            "Point at boundary (z=0) should be on boundary of timberA"
        assert csg_B.contains_point(point_at_boundary_B_local), \
            "Point at boundary (z=0) should be on boundary of timberB"
        
        # At z=+epsilon: Just inside timberB's kept region (FRONT side), should be in timberB but not in timberA
        point_in_B = create_v3(x_in_lap, 0, epsilon)  # Just above Z=0 (in timberB's kept region)
        point_in_B_as_A_local = timberA.transform.global_to_local(point_in_B)
        point_in_B_local = timberB.transform.global_to_local(point_in_B)
        
        assert not csg_A.contains_point(point_in_B_as_A_local), \
            "Point in timberB's kept region (z=+epsilon) should NOT be contained in timberA"
        assert csg_B.contains_point(point_in_B_local), \
            "Point in timberB's kept region (z=+epsilon) should be contained in timberB"
        
        # A little further into timberB (beyond the lap boundary): should be in timberB only, not in timberA
        point_deeper_in_B = create_v3(x_in_lap, 0, lap_depth - epsilon)  # z = 2 - 0.1 = 1.9 (deep into timberB)
        point_deeper_in_B_as_A_local = timberA.transform.global_to_local(point_deeper_in_B)
        point_deeper_in_B_local = timberB.transform.global_to_local(point_deeper_in_B)
        
        assert not csg_A.contains_point(point_deeper_in_B_as_A_local), \
            "Point deep in timberB should NOT be contained in timberA"
        assert csg_B.contains_point(point_deeper_in_B_local), \
            "Point deep in timberB should be contained in timberB"


class TestTongueAndForkJoint:
    @staticmethod
    def _face_center(timber: Timber, face: TimberFace) -> V3:
        if face == TimberFace.TOP:
            return locate_top_center_position(timber).position
        if face == TimberFace.BOTTOM:
            return locate_bottom_center_position(timber).position

        center = timber.get_bottom_position_global() + timber.get_length_direction_global() * (timber.length / Rational(2))
        if face == TimberFace.RIGHT:
            return center + timber.get_width_direction_global() * (timber.size[0] / Rational(2))
        if face == TimberFace.LEFT:
            return center - timber.get_width_direction_global() * (timber.size[0] / Rational(2))
        if face == TimberFace.FRONT:
            return center + timber.get_height_direction_global() * (timber.size[1] / Rational(2))
        return center - timber.get_height_direction_global() * (timber.size[1] / Rational(2))

    def test_tongue_and_fork_joint_structure_and_opposing_face_end_cuts(self):
        tongue_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))

        arrangement = CornerJointTimberArrangement(
            timber1=tongue_timber,
            timber2=fork_timber,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.BOTTOM,
        )
        joint = cut_tongue_and_fork_corner_joint(arrangement)

        assert len(joint.cut_timbers) == 2
        assert "tongue_timber" in joint.cut_timbers
        assert "fork_timber" in joint.cut_timbers

        tongue_cut = joint.cut_timbers["tongue_timber"].cuts[0]
        fork_cut = joint.cut_timbers["fork_timber"].cuts[0]
        assert tongue_cut.negative_csg is not None
        assert fork_cut.negative_csg is not None
        assert tongue_cut.maybe_bottom_end_cut is not None
        assert fork_cut.maybe_bottom_end_cut is not None

        tongue_end_direction = -tongue_timber.get_length_direction_global()
        fork_entry_face = fork_timber.get_closest_oriented_face_from_global_direction(-tongue_end_direction)
        fork_opposite_face_center = self._face_center(fork_timber, fork_entry_face.get_opposite_face())

        fork_end_direction = -fork_timber.get_length_direction_global()
        tongue_entry_face = tongue_timber.get_closest_oriented_face_from_global_direction(-fork_end_direction)
        tongue_opposite_face_center = self._face_center(tongue_timber, tongue_entry_face.get_opposite_face())

        tongue_distance_from_bottom = safe_dot_product(
            fork_opposite_face_center - tongue_timber.get_bottom_position_global(),
            tongue_timber.get_length_direction_global(),
        )
        expected_tongue_end_cut = Cutting.make_end_cut(
            tongue_timber,
            TimberReferenceEnd.BOTTOM,
            tongue_distance_from_bottom,
        )
        actual_tongue_end_cut = tongue_cut.maybe_bottom_end_cut
        assert actual_tongue_end_cut is not None
        assert actual_tongue_end_cut.normal.equals(expected_tongue_end_cut.normal)
        assert actual_tongue_end_cut.offset == expected_tongue_end_cut.offset

        fork_distance_from_bottom = safe_dot_product(
            tongue_opposite_face_center - fork_timber.get_bottom_position_global(),
            fork_timber.get_length_direction_global(),
        )
        expected_fork_end_cut = Cutting.make_end_cut(
            fork_timber,
            TimberReferenceEnd.BOTTOM,
            fork_distance_from_bottom,
        )
        actual_fork_end_cut = fork_cut.maybe_bottom_end_cut
        assert actual_fork_end_cut is not None
        assert actual_fork_end_cut.normal.equals(expected_fork_end_cut.normal)
        assert actual_fork_end_cut.offset == expected_fork_end_cut.offset

    def test_tongue_position_changes_kept_tongue_region(self):
        tongue_timber_a = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber_a = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        arrangement_a = CornerJointTimberArrangement(
            timber1=tongue_timber_a,
            timber2=fork_timber_a,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.BOTTOM,
        )

        joint_centered = cut_tongue_and_fork_corner_joint(arrangement_a)

        tongue_timber_b = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber_b = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        arrangement_b = CornerJointTimberArrangement(
            timber1=tongue_timber_b,
            timber2=fork_timber_b,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.BOTTOM,
        )
        joint_shifted = cut_tongue_and_fork_corner_joint(
            arrangement_b,
            tongue_thickness=Rational(2),
            tongue_position=Rational(2),
        )

        plane_normal = arrangement_a.compute_normalized_timber_cross_product()
        tongue_face = tongue_timber_a.get_closest_oriented_long_face_from_global_direction(plane_normal)
        tongue_normal = tongue_timber_a.get_face_direction_global(tongue_face)

        sample_point_global = (
            tongue_timber_a.get_bottom_position_global()
            + tongue_timber_a.get_length_direction_global() * Rational(1)
            + tongue_normal * Rational(0)
        )

        centered_render = joint_centered.cut_timbers["tongue_timber"].render_timber_with_cuts_csg_local()
        shifted_render = joint_shifted.cut_timbers["tongue_timber"].render_timber_with_cuts_csg_local()

        assert centered_render.contains_point(tongue_timber_a.transform.global_to_local(sample_point_global))
        assert not shifted_render.contains_point(tongue_timber_b.transform.global_to_local(sample_point_global))

    def test_tongue_and_fork_joint_assertions(self):
        tongue_parallel = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_parallel = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))

        with pytest.raises(AssertionError, match="parallel"):
            cut_tongue_and_fork_corner_joint(
                CornerJointTimberArrangement(
                    timber1=tongue_parallel,
                    timber2=fork_parallel,
                    timber1_end=TimberReferenceEnd.BOTTOM,
                    timber2_end=TimberReferenceEnd.BOTTOM,
                )
            )

        tongue_non_plane = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_non_plane = timber_from_directions(
            length=Rational(100),
            size=create_v2(6, 6),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 1, 1),
            width_direction=create_v3(1, -1, 0),
        )

        with pytest.raises(AssertionError, match="plane-aligned"):
            cut_tongue_and_fork_corner_joint(
                CornerJointTimberArrangement(
                    timber1=tongue_non_plane,
                    timber2=fork_non_plane,
                    timber1_end=TimberReferenceEnd.BOTTOM,
                    timber2_end=TimberReferenceEnd.BOTTOM,
                )
            )


class TestTongueAndForkButtJoint:
    def test_tongue_and_fork_butt_joint_structure_and_no_fork_end_cut(self):
        """
        Verify the butt variant produces the right structure: tongue timber
        gets an end cut and cheek removal, fork timber gets a slot but NO end cut.
        """
        tongue_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))

        arrangement = ButtJointTimberArrangement(
            butt_timber=tongue_timber,
            receiving_timber=fork_timber,
            butt_timber_end=TimberReferenceEnd.TOP,
        )
        joint = cut_tongue_and_fork_butt_joint(arrangement)

        assert len(joint.cut_timbers) == 2
        assert "tongue_timber" in joint.cut_timbers
        assert "fork_timber" in joint.cut_timbers

        tongue_cut = joint.cut_timbers["tongue_timber"].cuts[0]
        fork_cut = joint.cut_timbers["fork_timber"].cuts[0]

        # Tongue timber has cheek removal and an end cut
        assert tongue_cut.negative_csg is not None
        assert tongue_cut.maybe_top_end_cut is not None

        # Fork timber has a slot but NO end cut
        assert fork_cut.negative_csg is not None
        assert fork_cut.maybe_top_end_cut is None
        assert fork_cut.maybe_bottom_end_cut is None

        # Verify cuts produce valid CSG
        tongue_csg = joint.cut_timbers["tongue_timber"].render_timber_with_cuts_csg_local()
        fork_csg = joint.cut_timbers["fork_timber"].render_timber_with_cuts_csg_local()
        assert tongue_csg is not None
        assert fork_csg is not None
        