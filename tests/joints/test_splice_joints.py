"""
Tests for Kumiki timber framing system
"""

import pytest
from sympy import Matrix, sqrt, simplify, Abs, pi, atan2, sin, cos
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber
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



class TestSpliceLapJoint:
    """Test cut_plain_splice_lap_joint_on_aligned_timbers function."""
    
    def test_splice_lap_joint_geometry(self, symbolic_mode):
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


class TestHalfBlindTenonedDadoedRabbetedScarfJoint:
    """Test cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers."""

    def test_basic_construction_and_stub_tenon_interlock(self, float_mode):
        """The joint builds two end-cut cuttings with an interlocking stub
        tenon (each timber retains its own peg and has a matching pocket for
        the other's), a Kusabi wedge peg accessory, and an assembly freedom
        that slides the two timbers apart along the corner->p4 oblique face
        by dado_depth, in opposite directions."""
        timber_size = create_v2(inches(4), inches(6))
        timber_length = inches(20)
        overlap = inches(8)

        # The raw timbers must physically overlap near the joint center —
        # the profile only carves shape within material that's already
        # there, it doesn't extend either timber.
        timber1 = create_timber(
            length=timber_length, size=timber_size,
            bottom_position=create_v3(-timber_length + overlap, scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="timber1",
        )
        timber2 = create_timber(
            length=timber_length, size=timber_size,
            bottom_position=create_v3(-overlap, scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="timber2",
        )
        arrangement = SpliceJointTimberArrangement(
            timber1=timber1, timber2=timber2,
            timber1_end=TimberEnd.TOP, timber2_end=TimberEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.RIGHT,
        )
        front_face_on_timber1 = arrangement.front_face_on_timber1
        assert front_face_on_timber1 is not None

        SL, DD, DH, SSD, STW = inches(10), inches(1), inches(1.5), inches(1), inches(1.5)
        joint = cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(
            arrangement=arrangement,
            stepped_shoulder_depth=SSD, scarf_length=SL, dado_depth=DD, dado_height=DH,
            stub_tenon_width=STW, joint_center_relative_to_timber1_end=overlap,
        )

        assert len(joint.cuttings) == 2
        cut1 = joint.cuttings[timber1.ticket.path]
        cut2 = joint.cuttings[timber2.ticket.path]
        # timber1's joint end is TOP: the far-side truncation is a top end cut.
        assert cut1.get_maybe_top_end_cut() is not None
        assert cut1.get_maybe_bottom_end_cut() is None
        # timber2's joint end is BOTTOM.
        assert cut2.get_maybe_bottom_end_cut() is not None
        assert cut2.get_maybe_top_end_cut() is None

        # Assembly freedom: slide along the corner->p4 oblique face, freed
        # after dado_depth, in opposite directions for the two timbers.
        u_dir = -timber1.get_face_direction_global(arrangement.timber1_end)
        v_face = front_face_on_timber1.rotate_right()
        v_dir = timber1.get_face_direction_global(v_face)
        # corner->p4 is NOT the naive (-(SL+SSD)/2, -SSD/2) chord -- the joint
        # computes p4 via the actual scarf angle (atan2(SSD/2, sqrt((SL/2)^2 -
        # (SSD/2)^2))), which only reduces to that straight-line approximation
        # in the limit SSD << SL. Recompute it the same way the joint does
        # (stepped_shoulder_length defaults to SSD here, as in the call above).
        some_var_x = sqrt((SL / scalar(2)) ** 2 - (SSD / scalar(2)) ** 2)
        scarf_hypotneuse = some_var_x + SSD / scalar(2)
        scarf_angle = atan2(SSD / scalar(2), some_var_x)
        corner_to_p4_u = -cos(scarf_angle) * scarf_hypotneuse
        corner_to_p4_v = -sin(scarf_angle) * scarf_hypotneuse
        expected_direction = safe_normalize_vector(u_dir * corner_to_p4_u + v_dir * corner_to_p4_v)

        freedom1 = cut1.assembly_freedom
        freedom2 = cut2.assembly_freedom
        assert freedom1 is not None
        assert freedom2 is not None
        dof1 = freedom1.translations[0]
        dof2 = freedom2.translations[0]
        assert dof1.freed_after == DD
        assert dof2.freed_after == DD
        assert safe_magnitude(dof1.direction + expected_direction) < scalar(1e-9)
        assert safe_magnitude(dof2.direction - expected_direction) < scalar(1e-9)

        # A Kusabi wedge peg accessory fills the peg hole.
        assert "peg" in joint.jointAccessories
        peg = joint.jointAccessories["peg"]
        assert isinstance(peg, Peg)
        assert peg.shape == PegShape.SQUARE

        # Each timber retains its own stub tenon peg (solid) and has a
        # pocket cut for the other timber's peg, so the two interlock.
        csg1 = _render_cutting(cut1)
        csg2 = _render_cutting(cut2)
        depth_dir = timber1.get_face_direction_global(front_face_on_timber1)
        H = timber1.get_size_in_face_normal_axis(v_face)
        joint_center = locate_top_center_position(timber1).position + u_dir * overlap

        def uv_point(u, v, depth, timber):
            global_point = joint_center + u_dir * u + v_dir * v + depth_dir * depth
            return timber.transform.global_to_local(global_point)

        # timber1's own peg sits at u in [-SL/2, -SL/2 + DD], v in [-H/2, -DD].
        timber1_peg_u = -SL / scalar(2) + DD / scalar(2)
        timber1_peg_v = -H / scalar(2) + (H / scalar(2) - DD) / scalar(2)

        p1 = uv_point(timber1_peg_u, timber1_peg_v, scalar(0), timber1)
        assert csg1.contains_point(p1), "timber1 should retain its own stub tenon peg"
        p1_as_timber2 = uv_point(timber1_peg_u, timber1_peg_v, scalar(0), timber2)
        assert not csg2.contains_point(p1_as_timber2), "timber2 should have a pocket for timber1's peg"

        # timber2's own peg is the point-reflection of timber1's through the joint center.
        timber2_peg_u = -timber1_peg_u
        timber2_peg_v = -timber1_peg_v

        p2 = uv_point(timber2_peg_u, timber2_peg_v, scalar(0), timber2)
        assert csg2.contains_point(p2), "timber2 should retain its own stub tenon peg"
        p2_as_timber1 = uv_point(timber2_peg_u, timber2_peg_v, scalar(0), timber1)
        assert not csg1.contains_point(p2_as_timber1), "timber1 should have a pocket for timber2's peg"


