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

class TestMiteredAndKeyedLapJoint:
    """Test cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers function."""


# ============================================================================
# Helpers for TestMiteredAndKeyedLapJoint
# ============================================================================

def _make_right_angle_arrangement(front_face=TimberLongFace.RIGHT, position=None):
    from dataclasses import replace as dc_replace
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)
    timberA = dc_replace(arrangement.timber1, ticket=TimberTicket("timberA"))
    timberB = dc_replace(arrangement.timber2, ticket=TimberTicket("timberB"))
    return dc_replace(arrangement, timber1=timberA, timber2=timberB, front_face_on_timber1=front_face)


def _make_angled_arrangement(angle_deg, front_face=TimberLongFace.RIGHT, position=None):
    from dataclasses import replace as dc_replace
    arrangement = create_canonical_example_corner_joint_timbers(
        corner_angle=degrees(scalar(angle_deg)), position=position
    )
    timberA = dc_replace(arrangement.timber1, ticket=TimberTicket("timberA"))
    timberB = dc_replace(arrangement.timber2, ticket=TimberTicket("timberB"))
    return dc_replace(arrangement, timber1=timberA, timber2=timberB, front_face_on_timber1=front_face)


def _assert_joint_structure(joint, num_keys, num_laps):
    assert joint is not None
    assert len(joint.cuttings) == 2
    assert "timberA" in joint.cuttings
    assert "timberB" in joint.cuttings
    assert isinstance(joint.cuttings["timberA"], Cutting)
    assert isinstance(joint.cuttings["timberB"], Cutting)
    expected_keys = num_laps - 1
    assert len(joint.jointAccessories) == expected_keys, (
        f"Expected {expected_keys} key accessories for {num_laps} laps, "
        f"got {len(joint.jointAccessories)}"
    )
    for i in range(expected_keys):
        assert f"key_{i}" in joint.jointAccessories
        assert isinstance(joint.jointAccessories[f"key_{i}"], Wedge)


def _assert_end_cuts_match_arrangement(joint, arrangement):
    cutA = joint.cuttings["timberA"]
    cutB = joint.cuttings["timberB"]
    if arrangement.timber1_end == TimberEnd.TOP:
        assert cutA.get_maybe_top_end_cut() is not None
        assert cutA.get_maybe_bottom_end_cut() is None
    else:
        assert cutA.get_maybe_bottom_end_cut() is not None
        assert cutA.get_maybe_top_end_cut() is None
    if arrangement.timber2_end == TimberEnd.TOP:
        assert cutB.get_maybe_top_end_cut() is not None
        assert cutB.get_maybe_bottom_end_cut() is None
    else:
        assert cutB.get_maybe_bottom_end_cut() is not None
        assert cutB.get_maybe_top_end_cut() is None


def _assert_miter_boundary_point(joint, timberA, timberB, point_global):
    def _render_cutting(cutting):
        return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()
    csgA = _render_cutting(joint.cuttings["timberA"])
    csgB = _render_cutting(joint.cuttings["timberB"])
    ptA = timberA.transform.global_to_local(point_global)
    ptB = timberB.transform.global_to_local(point_global)
    assert csgA.is_point_on_boundary(ptA)
    assert csgB.is_point_on_boundary(ptB)



    def test_basic_right_angle_joint(self):
        """Test basic joint at 90 degrees — structure, end cuts, accessories, miter separation."""
        arrangement = _make_right_angle_arrangement()
        timberA = arrangement.timber1
        timberB = arrangement.timber2
        num_laps = 3

        joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
            arrangement=arrangement,
            num_laps=num_laps,
            lap_thickness=inches(scalar(3, 4)),
            lap_start_distance_from_reference_miter_face=inches(scalar(1, 2)),
            distance_between_lap_and_outside=inches(scalar(1, 2)),
        )

        _assert_joint_structure(joint, num_keys=num_laps - 1, num_laps=num_laps)
        _assert_end_cuts_match_arrangement(joint, arrangement)

        # Both timbers should be renderable without error
        csgA = _render_cutting(joint.cuttings["timberA"])
        csgB = _render_cutting(joint.cuttings["timberB"])
        assert csgA is not None
        assert csgB is not None

        
        # Each key wedge accessory has a transform; its position center should
        # be in the void (not contained in either timber).
        for key_name, accessory in joint.jointAccessories.items():
            assert isinstance(accessory, Wedge)
            key_center_global = accessory.transform.position
            ptA = timberA.transform.global_to_local(key_center_global)
            ptB = timberB.transform.global_to_local(key_center_global)
            assert not csgA.contains_point(ptA), (
                f"{key_name} center should not be inside timberA (key void)"
            )
            assert not csgB.contains_point(ptB), (
                f"{key_name} center should not be inside timberB (key void)"
            )

        # TODO test finger locations and keys


    def test_multiple_angles(self):
        """Test that the joint is constructable at several valid angles."""
        for angle_deg in [60, 75, 90, 110, 130]:
            arrangement = _make_angled_arrangement(angle_deg)
            joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
                arrangement=arrangement,
                num_laps=2,
            )
            _assert_joint_structure(joint, num_keys=1, num_laps=2)
            _assert_end_cuts_match_arrangement(joint, arrangement)

            # Ensure renderable
            csgA = _render_cutting(joint.cuttings["timberA"])
            csgB = _render_cutting(joint.cuttings["timberB"])
            assert csgA is not None
            assert csgB is not None
        
        # TODO test finger locations and keys

    # ------------------------------------------------------------------
    # Parameter variation tests
    # ------------------------------------------------------------------

    def test_num_laps_2_produces_one_key(self):
        """Minimum valid num_laps=2 should produce exactly 1 key."""
        arrangement = _make_right_angle_arrangement()
        joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
            arrangement=arrangement,
            num_laps=2,
        )
        _assert_joint_structure(joint, num_keys=1, num_laps=2)

    def test_num_laps_4_produces_three_keys(self):
        """num_laps=4 should produce exactly 3 keys."""
        arrangement = _make_right_angle_arrangement()
        joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
            arrangement=arrangement,
            num_laps=4,
        )
        _assert_joint_structure(joint, num_keys=3, num_laps=4)

    # ------------------------------------------------------------------
    # Error / validation tests
    # ------------------------------------------------------------------


    # 🐪
    def test_num_laps_below_2_raises(self):
        """num_laps < 2 should raise ValueError."""
        arrangement = _make_right_angle_arrangement()
        with pytest.raises(ValueError, match="num_laps must be at least 2"):
            cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
                arrangement=arrangement,
                num_laps=1,
            )

    # 🐪
    def test_angle_too_shallow_raises(self):
        """Angles below 45 degrees should raise ValueError."""
        arrangement = _make_angled_arrangement(30)
        with pytest.raises(ValueError, match="Angle between timbers"):
            cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
                arrangement=arrangement,
                num_laps=2,
            )

    # 🐪
    def test_parallel_timbers_raises(self):
        """Parallel timbers (angle ~0 or ~180) should raise."""
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(4, 5), position=(0, 0, 0), ticket="timberA")
        timberB = create_standard_horizontal_timber(direction='x', length=100, size=(4, 5), position=(0, 0, 0), ticket="timberB")

        arrangement = CornerJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.RIGHT,
        )
        with pytest.raises((ValueError, AssertionError)):
            cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
                arrangement=arrangement,
                num_laps=2,
            )


# ============================================================================
# Tests for cut_dropin_dovetail_butt_joint_on_face_aligned_timbers
# ============================================================================


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
      Cross-section: x ∈ [-4, 4], y ∈ [-4, 4].
    - Dovetail timber (beam): horizontal along +X, length 100, size (8, 8),
      bottom at (-100, 0, 50). Cross-section: y ∈ [-4, 4], z ∈ [46, 54].
    - butt_timber_end = TOP (x=0)
    - front_face_on_butt_timber = RIGHT (+Y, perpendicular to post length +Z)
    """
    from tests.testing_shavings import create_standard_vertical_timber
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


