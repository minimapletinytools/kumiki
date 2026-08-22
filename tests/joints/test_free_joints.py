"""
Tests for Kumiki timber framing system
"""

import pytest
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber
)


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()

from kumiki.cutcsg import HalfSpace

class TestFreeHouseJoint:
    """Test cut_free_house_joint function."""

    # 🐪
    def test_free_house_joint_timberlike_points_in_housed_not_in_housing(self):
        """
        A 1×1 housed timber enters halfway into a 3×3 housing timber.
        Points strictly inside the housed timber's body must not be inside
        the cut housing timber (they were removed to accommodate the relief cut).
        """
        # 3×3 vertical housing timber (local x=global X, y=global Y, z=global Z)
        housing_timber = create_standard_vertical_timber(
            height=20, size=(3, 3), position=(0, 0, 0), ticket="housing"
        )

        # 1×1 horizontal +X housed timber; bottom at (-10, 0, 10), length 20
        # Crosses the housing at global Z=10, Y ∈ [-0.5, 0.5]
        housed_timber = create_timber(
            length=scalar(20),
            size=Matrix([scalar(1), scalar(1)]),
            bottom_position=create_v3(scalar(-10), scalar(0), scalar(10)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="housed",
        )

        joint = cut_free_house_joint(housing_timber, [housed_timber])
        assert "housing_timber" in joint.cuttings
        assert "housed_timber_1" in joint.cuttings

        housing_rendered = _render_cutting(joint.cuttings["housing_timber"])
        housed_rendered = _render_cutting(joint.cuttings["housed_timber_1"])

        # Center of the housed timber — strictly interior to both timbers' prisms
        center_global = create_v3(scalar(0), scalar(0), scalar(10))
        housing_local = housing_timber.transform.global_to_local(center_global)
        housed_local = housed_timber.transform.global_to_local(center_global)

        # Relief was cut → point is no longer inside the housing timber
        assert not housing_rendered.contains_point(housing_local)
        # The housed timber itself is untouched
        assert housed_rendered.contains_point(housed_local)

        # Point well away from the relief cut must still be inside the housing timber
        away_global = create_v3(scalar(0), scalar(0), scalar(5))
        housing_local_away = housing_timber.transform.global_to_local(away_global)
        assert housing_rendered.contains_point(housing_local_away)

    # 🐪
    def test_free_house_joint_cut_timber_relief_matches_actual_body(self):
        """
        A 2×2 CutTimber with its lower-Z half removed is housed in a 3×3 timber.
        The relief must match the CutTimber's remaining body (upper Z half only),
        so the lower Z region is not removed from the housing even though the full
        prism overlaps there.
        """
        # 3×3 vertical housing timber
        housing_timber = create_standard_vertical_timber(
            height=20, size=(3, 3), position=(0, 0, 0), ticket="housing"
        )

        # 2×2 horizontal +X base timber; bottom at (-10, 0, 10), length 20
        # local x = global Y, local y = global Z, local z = global X
        housed_timber_base = create_timber(
            length=scalar(20),
            size=Matrix([scalar(2), scalar(2)]),
            bottom_position=create_v3(scalar(-10), scalar(0), scalar(10)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="housed_base",
        )

        # Remove the lower-Z half of the timber.
        # HalfSpace contains points with P·normal >= offset; normal=[0,-1,0] → local_y <= 0 → global Z <= 10.
        # Remaining body: local_y > 0 → global Z ∈ (10, 11].
        bottom_half_cut = Cutting(
            timber=housed_timber_base,
            negative_csg=HalfSpace(normal=Matrix([scalar(0), scalar(-1), scalar(0)]), offset=scalar(0)),
        )
        housed_cut_timber = CutTimber(housed_timber_base, cuts=[bottom_half_cut])
        housed_body = housed_cut_timber.render_timber_with_cuts_csg_local()

        joint = cut_free_house_joint(housing_timber, [housed_cut_timber])
        housing_rendered = _render_cutting(joint.cuttings["housing_timber"])

        # --- Point in the UPPER half (global Z = 10.5): CutTimber body ---
        # The relief must remove this region from the housing.
        upper_global = create_v3(scalar(0), scalar(0), scalar(21, 2))  # Z = 10.5
        housing_local_upper = housing_timber.transform.global_to_local(upper_global)
        housed_local_upper = housed_timber_base.transform.global_to_local(upper_global)

        assert housed_body.contains_point(housed_local_upper), \
            "Z=10.5 should be inside the CutTimber body (upper half kept)"
        assert not housing_rendered.contains_point(housing_local_upper), \
            "Z=10.5 should have been removed from the housing (relief matches CutTimber body)"

        # --- Point in the LOWER half (global Z = 9.5): was cut from CutTimber ---
        # The housing must NOT be relieved here.
        lower_global = create_v3(scalar(0), scalar(0), scalar(19, 2))  # Z = 9.5
        housing_local_lower = housing_timber.transform.global_to_local(lower_global)
        housed_local_lower = housed_timber_base.transform.global_to_local(lower_global)

        assert not housed_body.contains_point(housed_local_lower), \
            "Z=9.5 should NOT be in the CutTimber body (lower half was cut away)"
        assert housing_rendered.contains_point(housing_local_lower), \
            "Z=9.5 should still be inside the housing (relief does not reach the removed region)"

    # 🐪
    def test_free_house_joint_extends_cut_timber_for_skewed_end_cut(self):
        """
        A housed CutTimber's un-extended local Z origin sits exactly at the housing's
        centerline, but a SKEWED end cut (e.g. a miter) means the piece's true, as-cut
        tip reaches past that origin at one corner of the cross-section. The housing
        relief must reach that far too -- if the housing carve-out were computed from
        the un-extended body instead of the extended one, the sharp corner of the miter
        would get chopped off flat instead of leaving room for the full pointed tip.
        """
        # 3x3 vertical housing timber, base at origin, height 20.
        housing_timber = create_standard_vertical_timber(
            height=20, size=(3, 3), position=(0, 0, 0), ticket="housing"
        )

        # 2x2 horizontal +X timber; local x = global Y, local y = global Z, local z = global X.
        # Bottom (local z=0) sits at global X=0 -- the housing's centerline -- so any material
        # at global X<0 only exists because the bottom end was extended past local z=0.
        housed_timber_base = create_timber(
            length=scalar(20),
            size=Matrix([scalar(2), scalar(2)]),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(10)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="housed_base",
        )

        # Skewed 45-degree miter-style cut in the local x/z plane. Kept (remaining) region
        # is local_x + local_z > 0. At local_x=0.5 the kept region reaches to local_z=-0.3 --
        # past the timber's own un-extended bottom (local_z=0) -- while at local_x=-0.5 it's
        # trimmed back to local_z=0.3.
        #
        # maybe_bottom_end_cut_distance_from_bottom is separate axis-aligned bookkeeping
        # (used for length/bounding-box purposes elsewhere -- see get_maybe_bottom_end_cut)
        # that gets unioned into the real cut alongside negative_csg. Real miter joints
        # (cut_plain_miter_joint) always set it to the *outermost* corner of the skewed
        # plane, so it never removes more than the skewed cut already does. Mirror that
        # here with a very permissive value so this synthetic cut isn't inadvertently
        # double-cut by its own bookkeeping distance.
        skew_normal = safe_normalize_vector(Matrix([scalar(1), scalar(0), scalar(1)]))
        miter_cut = Cutting(
            timber=housed_timber_base,
            maybe_bottom_end_cut_distance_from_bottom=scalar(-100),
            negative_csg=HalfSpace(normal=-skew_normal, offset=scalar(0)),
        )
        housed_cut_timber = CutTimber(housed_timber_base, cuts=[miter_cut])
        housed_body = housed_cut_timber.render_timber_with_cuts_csg_local()

        joint = cut_free_house_joint(housing_timber, [housed_cut_timber])
        housing_rendered = _render_cutting(joint.cuttings["housing_timber"])

        # --- Sharp tip (global X=-0.3, Y=0.5, Z=10): past the un-extended bottom (X=0) ---
        # Kept in the housed body (local_x + local_z = 0.5 + (-0.3) > 0); the housing must
        # be relieved here even though it lies beyond the timber's own un-extended origin.
        tip_global = create_v3(scalar(-3, 10), scalar(1, 2), scalar(10))
        housing_local_tip = housing_timber.transform.global_to_local(tip_global)
        housed_local_tip = housed_timber_base.transform.global_to_local(tip_global)

        assert housed_body.contains_point(housed_local_tip), \
            "tip should be kept in the housed body (past the miter's skewed cut point)"
        assert not housing_rendered.contains_point(housing_local_tip), \
            "housing must be relieved at the tip -- this only happens if the housed " \
            "timber's body was extended past its un-extended bottom before cutting"

        # --- Trimmed-back corner (global X=0.3, Y=-0.5, Z=10): removed from the housed body ---
        # The housing must NOT be relieved here.
        trimmed_global = create_v3(scalar(3, 10), scalar(-1, 2), scalar(10))
        housing_local_trimmed = housing_timber.transform.global_to_local(trimmed_global)
        housed_local_trimmed = housed_timber_base.transform.global_to_local(trimmed_global)

        assert not housed_body.contains_point(housed_local_trimmed), \
            "trimmed-back corner should have been cut away from the housed body"
        assert housing_rendered.contains_point(housing_local_trimmed), \
            "housing must remain solid where the housed body was trimmed away"

    def test_free_house_joint_multiple_housed_timbers_relief_union(self):
        """
        Two housed timbers should produce one housing relief that removes both occupied regions.
        """
        housing_timber = create_standard_vertical_timber(
            height=20, size=(3, 3), position=(0, 0, 0), ticket="housing"
        )

        housed_timber_1 = create_timber(
            length=scalar(20),
            size=Matrix([scalar(1), scalar(1)]),
            bottom_position=create_v3(scalar(-10), scalar(0), scalar(8)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="housed_1",
        )
        housed_timber_2 = create_timber(
            length=scalar(20),
            size=Matrix([scalar(1), scalar(1)]),
            bottom_position=create_v3(scalar(-10), scalar(0), scalar(12)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="housed_2",
        )

        joint = cut_free_house_joint(housing_timber, [housed_timber_1, housed_timber_2])
        assert "housing_timber" in joint.cuttings
        assert "housed_timber_1" in joint.cuttings
        assert "housed_timber_2" in joint.cuttings

        housing_rendered = _render_cutting(joint.cuttings["housing_timber"])

        first_center_global = create_v3(scalar(0), scalar(0), scalar(8))
        second_center_global = create_v3(scalar(0), scalar(0), scalar(12))
        first_center_housing_local = housing_timber.transform.global_to_local(first_center_global)
        second_center_housing_local = housing_timber.transform.global_to_local(second_center_global)

        assert not housing_rendered.contains_point(first_center_housing_local)
        assert not housing_rendered.contains_point(second_center_housing_local)

        away_global = create_v3(scalar(0), scalar(0), scalar(5))
        away_housing_local = housing_timber.transform.global_to_local(away_global)
        assert housing_rendered.contains_point(away_housing_local)
