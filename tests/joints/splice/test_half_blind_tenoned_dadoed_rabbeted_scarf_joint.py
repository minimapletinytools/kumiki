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

class TestHalfBlindTenonedDadoedRabbetedScarfJoint:
    """Test cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers."""

    def test_basic_construction_and_stub_tenon_interlock(self):
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


