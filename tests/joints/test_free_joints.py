"""
Tests for Kumiki timber framing system
"""

import pytest
from sympy import Matrix, sqrt, simplify, Abs, pi
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
    def test_free_house_joint_timberlike_points_in_housed_not_in_housing(self, symbolic_mode):
        """
        A 1×1 housed timber enters halfway into a 3×3 housing timber.
        Points strictly inside the housed timber's body must not be inside
        the cut housing timber (they were removed to accommodate the notch).
        """
        # 3×3 vertical housing timber (local x=global X, y=global Y, z=global Z)
        housing_timber = create_standard_vertical_timber(
            height=20, size=(3, 3), position=(0, 0, 0), ticket="housing"
        )

        # 1×1 horizontal +X housed timber; bottom at (-10, 0, 10), length 20
        # Crosses the housing at global Z=10, Y ∈ [-0.5, 0.5]
        housed_timber = timber_from_directions(
            length=scalar(20),
            size=Matrix([scalar(1), scalar(1)]),
            bottom_position=create_v3(scalar(-10), scalar(0), scalar(10)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="housed",
        )

        joint = cut_free_house_joint(housing_timber, housed_timber)
        assert "housing_timber" in joint.cuttings
        assert "housed_timber" in joint.cuttings

        housing_rendered = _render_cutting(joint.cuttings["housing_timber"])
        housed_rendered = _render_cutting(joint.cuttings["housed_timber"])

        # Center of the housed timber — strictly interior to both timbers' prisms
        center_global = create_v3(scalar(0), scalar(0), scalar(10))
        housing_local = housing_timber.transform.global_to_local(center_global)
        housed_local = housed_timber.transform.global_to_local(center_global)

        # Notch was cut → point is no longer inside the housing timber
        assert not housing_rendered.contains_point(housing_local)
        # The housed timber itself is untouched
        assert housed_rendered.contains_point(housed_local)

        # Point well away from the notch must still be inside the housing timber
        away_global = create_v3(scalar(0), scalar(0), scalar(5))
        housing_local_away = housing_timber.transform.global_to_local(away_global)
        assert housing_rendered.contains_point(housing_local_away)

    # 🐪
    def test_free_house_joint_cut_timber_notch_matches_actual_body(self, symbolic_mode):
        """
        A 2×2 CutTimber with its lower-Z half removed is housed in a 3×3 timber.
        The notch must match the CutTimber's remaining body (upper Z half only),
        so the lower Z region is not removed from the housing even though the full
        prism overlaps there.
        """
        # 3×3 vertical housing timber
        housing_timber = create_standard_vertical_timber(
            height=20, size=(3, 3), position=(0, 0, 0), ticket="housing"
        )

        # 2×2 horizontal +X base timber; bottom at (-10, 0, 10), length 20
        # local x = global Y, local y = global Z, local z = global X
        housed_timber_base = timber_from_directions(
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

        joint = cut_free_house_joint(housing_timber, housed_cut_timber)
        housing_rendered = _render_cutting(joint.cuttings["housing_timber"])

        # --- Point in the UPPER half (global Z = 10.5): CutTimber body ---
        # The notch must remove this region from the housing.
        upper_global = create_v3(scalar(0), scalar(0), scalar(21, 2))  # Z = 10.5
        housing_local_upper = housing_timber.transform.global_to_local(upper_global)
        housed_local_upper = housed_timber_base.transform.global_to_local(upper_global)

        assert housed_body.contains_point(housed_local_upper), \
            "Z=10.5 should be inside the CutTimber body (upper half kept)"
        assert not housing_rendered.contains_point(housing_local_upper), \
            "Z=10.5 should have been removed from the housing (notch matches CutTimber body)"

        # --- Point in the LOWER half (global Z = 9.5): was cut from CutTimber ---
        # The housing must NOT be notched here.
        lower_global = create_v3(scalar(0), scalar(0), scalar(19, 2))  # Z = 9.5
        housing_local_lower = housing_timber.transform.global_to_local(lower_global)
        housed_local_lower = housed_timber_base.transform.global_to_local(lower_global)

        assert not housed_body.contains_point(housed_local_lower), \
            "Z=9.5 should NOT be in the CutTimber body (lower half was cut away)"
        assert housing_rendered.contains_point(housing_local_lower), \
            "Z=9.5 should still be inside the housing (notch does not reach the removed region)"
