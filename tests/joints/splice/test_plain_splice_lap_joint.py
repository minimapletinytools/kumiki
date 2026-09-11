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

class TestSpliceLapJoint:
    """Test cut_plain_splice_lap_joint_on_aligned_timbers function."""
    
    def test_splice_lap_joint_geometry(self):
        """
        Test splice lap joint creates correct geometry with proper containment.
        
        Tests:
        1. Points outside the ends on centerline are not contained
        2. Points along a line perpendicular to the lap face show correct containment
        """
        
        # Create two aligned timbers meeting end-to-end
        timber_length = 20
        timber_size = create_v2(4, 4)
        
        # TimberA extends from x=0 to x=20
        timberA = create_timber(
            length=timber_length,
            size=timber_size,
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket='timberA'
        )
        
        # TimberB extends from x=20 to x=40
        timberB = create_timber(
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
                timber1_end=TimberEnd.TOP,
                timber2_end=TimberEnd.BOTTOM,
                front_face_on_timber1=TimberLongFace.BACK
            ),
            lap_length=lap_length,
            top_lap_shoulder_position_from_top_lap_shoulder_timber_end=shoulder_distance,
            lap_depth=None  # Use default
        )
        
        # Verify joint was created
        assert joint is not None
        assert len(joint.cuttings) == 2
        
        # Get the cut timbers
        cut_timberA = joint.cuttings['top_lap_timber']
        cut_timberB = joint.cuttings['bottom_lap_timber']
        
        # Each joint member contributes exactly one cutting
        assert isinstance(cut_timberA, Cutting)
        assert isinstance(cut_timberB, Cutting)
        
        # Render the CSGs
        csg_A = _render_cutting(cut_timberA)
        csg_B = _render_cutting(cut_timberB)
        
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
        lap_depth = scalar(4) / 2  # 2
        
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
        epsilon = scalar(1, 10)  # Small offset
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


