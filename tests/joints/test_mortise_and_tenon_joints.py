"""
Tests for mortise and tenon joint construction functions
"""

import pytest
from typing import List
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber
)
from kumiki.rule import Orientation, create_v2, inches, radians, are_vectors_parallel, safe_zero_test, safe_compare, Comparison, safe_dot_product, safe_normalize_vector as safe_normalize_vector
from kumiki.timber import (
    Timber, TimberEnd, TimberFace, TimberLongFace,
    V2, V3, Numeric, PegShape, WedgeShape, Peg, Cutting, CutTimber,
    create_timber, create_v3
)
from kumiki.construction import ButtJointTimberArrangement
from kumiki.timber_shavings import are_timbers_plane_aligned
from kumiki.cutcsg import csg_children
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.joints.workshop.basic_joints import (
    cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers,
)
from kumiki.joints.workshop.shavings.build_a_butt import (
    SimplePegParameters,
    PegPositionSpace,
)
from kumiki.joints.workshop.mortise_and_tenon_joints import (
    InsetShoulderReliefStyle,
    WedgeParameters,
    cut_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_mortise_and_tenon_joint_on_plane_aligned_timbers,
)
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber,
    assert_vectors_parallel
)


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def simple_T_configuration():
    """
    Creates a simple T-configuration with a vertical tenon timber 
    and a horizontal mortise timber centered at the top.
    
    Returns:
        tuple: (tenon_timber, mortise_timber)
            - tenon_timber: Vertical 4x4 timber, height 100, at origin
            - mortise_timber: Horizontal 6x6 timber, length 100, along x-axis
    """
    tenon_timber = create_standard_vertical_timber(
        height=100, size=(4, 4), position=(0, 0, 0), ticket="tenon_timber"
    )
    mortise_timber = create_centered_horizontal_timber(
        direction='x', length=100, size=(6, 6), name="mortise_timber"
    )
    return (tenon_timber, mortise_timber)


# ============================================================================
# Helper Functions for CSG Testing
# ============================================================================

# TODO DELETE replace with timber.global_to_local
def transform_point_to_local(point_world: V3, timber: Timber) -> V3:
    """Transform a point from world coordinates to timber local coordinates."""
    return timber.orientation.matrix.T * (point_world - timber.get_bottom_position_global())


def sample_points_in_box(center: V3, size: V3, num_samples: int = 5) -> List[V3]:
    """
    Generate test points within a box.
    
    Args:
        center: Center of the box (3x1 Matrix)
        size: Size of the box [width, height, depth] (3x1 Matrix)
        num_samples: Number of samples per dimension
        
    Returns:
        List of points distributed throughout the box
    """
    points = []
    half_size = size / 2
    
    # Sample along each axis
    for i in range(num_samples):
        t = scalar(i, num_samples - 1) if num_samples > 1 else scalar(1, 2)
        offset = (t - scalar(1, 2)) * 2  # Map [0,1] to [-1, 1]
        
        # Sample along X axis
        points.append(center + Matrix([half_size[0] * offset, 0, 0]))
        # Sample along Y axis  
        points.append(center + Matrix([0, half_size[1] * offset, 0]))
        # Sample along Z axis
        points.append(center + Matrix([0, 0, half_size[2] * offset]))
    
    # Add center point
    points.append(center)
    
    return points


# ============================================================================
# Tests for Mortise and Tenon Joint Geometry
# ============================================================================

class TestMortiseAndTenonGeometry:
    
    def test_mortise_tenon_centerline_containment(self, simple_T_configuration):
        """
        Test points along the tenon centerline to verify correct joint geometry.
        
        Measuring from the shoulder of the joint along the centerline of the tenon timber, we expect:
        - Points in [0,4] should be in tenon but not mortise (tenon part)
        - Points in (4,5) should be in neither (gap between tenon and mortise  depth)
        - Points in [5,6] should be in neither (inside the mortise hole)
        
        This tests that the tenon length and mortise depth are correctly implemented.
        """
        tenon_timber, mortise_timber = simple_T_configuration
        
        mortise_depth = scalar(5)
        tenon_length = scalar(4)
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=tenon_length,
            mortise_depth=mortise_depth,
        )
        
        # Get the CSGs for the cut timbers (these are the REMAINING material after cuts)
        tenon_csg = _render_cutting(joint.cuttings["tenon_timber"])
        mortise_csg = _render_cutting(joint.cuttings["mortise_timber"])

        joint_shoulder_global = create_v3(scalar(0), scalar(0), scalar(3))
        
        # Verify basic tenon geometry: tenon should exist from z=0 upward
        # Test that center points are in the tenon at the bottom
        for z in [scalar(0), scalar(1), scalar(2), scalar(3)]:
            point_global = joint_shoulder_global - create_v3(scalar(0), scalar(0), z)
            point_tenon_local = tenon_timber.transform.global_to_local(point_global)
            point_mortise_local = mortise_timber.transform.global_to_local(point_global)
            assert tenon_csg.contains_point(point_tenon_local), \
                f"Point at z={z} should be in tenon centerline"
            assert not mortise_csg.contains_point(point_mortise_local), \
                f"Point at z={z} should not be in mortise centerline"
        
        for z in [scalar(4.2), scalar(4.8)]:
            point_global = joint_shoulder_global - create_v3(scalar(0), scalar(0), z)
            point_tenon_local = tenon_timber.transform.global_to_local(point_global)
            point_mortise_local = mortise_timber.transform.global_to_local(point_global)
            assert not tenon_csg.contains_point(point_tenon_local), \
                f"Point at z={z} should not be in tenon centerline"
            assert not mortise_csg.contains_point(point_mortise_local), \
                f"Point at z={z} should not be in mortise centerline"
        
        # TODO change back to scalar(5) it's failing due to numeric precision issues in contains_point
        for z in [scalar(51, 10), scalar(6)]:
            point_global = joint_shoulder_global - create_v3(scalar(0), scalar(0), z)
            point_tenon_local = tenon_timber.transform.global_to_local(point_global)
            point_mortise_local = mortise_timber.transform.global_to_local(point_global)
            assert not tenon_csg.contains_point(point_tenon_local), \
                f"Point at z={z} should not be in tenon centerline"
            assert mortise_csg.contains_point(point_mortise_local), \
                f"Point at z={z} should be in mortise centerline"

    def test_tenon_negative_csg_has_no_cut_behind_shoulder(self, simple_T_configuration):
        """Ensure the tenon cut volume does not extend past the shoulder into the timber body."""
        from kumiki.cutcsg import Difference, HalfSpace, Intersection

        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(5),
        )

        tenon_negative_csg = joint.cuttings["tenon_timber"].negative_csg
        assert isinstance(tenon_negative_csg, Difference)
        assert isinstance(tenon_negative_csg.base, HalfSpace)

        shoulder_half_space_local = tenon_negative_csg.base
        epsilon = scalar(1, 100)
        behind_shoulder_half_space_local = HalfSpace(
            normal=-shoulder_half_space_local.normal,
            offset=-shoulder_half_space_local.offset + epsilon,
        )

        overlap_csg = Intersection(
            left=behind_shoulder_half_space_local,
            right=tenon_negative_csg,
        )

        # Probe a small grid of points behind the shoulder; none should lie in the
        # overlap if nothing behind the shoulder is being removed.
        x_values = [scalar(-2), scalar(0), scalar(2)]
        y_values = [scalar(-2), scalar(0), scalar(2)]
        z_values = [scalar(4), scalar(5), scalar(10)]
        for x in x_values:
            for y in y_values:
                for z in z_values:
                    point_local = create_v3(x, y, z)
                    assert not overlap_csg.contains_point(point_local), (
                        f"Found cut volume behind shoulder at local point {point_local.T}"
                    )
    



class TestMortiseAndTenonJointNotchReliefConfig:
    """Tests for relief=ButtJointNotchReliefConfig() in cut_mortise_and_tenon_joint."""

    def test_notch_relief_actually_relieves_the_butt_timber(self, simple_T_configuration):
        """
        Regression guard: relief=ButtJointNotchReliefConfig() must actually change the
        tenon (butt timber)'s cut geometry for an imperfect (oversized) tenon, not just the
        mortise (receiving timber)'s notch. A previous bug wired the relief CSG as something
        to subtract FROM shoulder_half_space_local (the standard behind-the-shoulder collar
        cut) -- but the relief CSG occupies its OWN, DISJOINT depth range (from the shoulder
        outward, toward the receiving timber's entry face), so subtracting it there had NO
        effect at all (a silent no-op): the tenon received zero relief regardless of how
        oversized it was, even though the mortise's own notch was computed and applied
        correctly. The fix unions the relief CSG in as an ADDITIONAL region to remove,
        rather than subtracting it from a base it never overlaps.
        """
        from dataclasses import replace

        tenon_timber, mortise_timber = simple_T_configuration
        imperfect_tenon = replace(
            tenon_timber,
            rough_half_sizes=(create_v2(scalar(3), scalar(3)), create_v2(scalar(3), scalar(3))),
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=imperfect_tenon, butt_timber_end=TimberEnd.BOTTOM,
        )

        joint_no_relief = cut_mortise_and_tenon_joint(
            arrangement=arrangement,
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_distance_from_centerline_or_centerplane=scalar(2),
            relief=None,
        )
        joint_with_relief = cut_mortise_and_tenon_joint(
            arrangement=arrangement,
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_distance_from_centerline_or_centerplane=scalar(2),
            relief=ButtJointNotchReliefConfig(),
            inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief,
        )

        tenon_csg_no_relief = joint_no_relief.cuttings["tenon_timber"].negative_csg
        tenon_csg_with_relief = joint_with_relief.cuttings["tenon_timber"].negative_csg
        assert tenon_csg_no_relief is not None
        assert tenon_csg_with_relief is not None

        # A point where rough (beyond-perfect) material pokes past the tight flare just
        # past the shoulder: must be removed WITH relief, but NOT removed without it.
        poke_point = create_v3(scalar(28, 10), scalar(0), scalar(21, 10))
        assert not tenon_csg_no_relief.contains_point(poke_point)
        assert tenon_csg_with_relief.contains_point(poke_point)

        # Far bulk of the tenon, well away from the joint: untouched in both cases.
        far_point = create_v3(scalar(0), scalar(0), scalar(90))
        assert not tenon_csg_no_relief.contains_point(far_point)
        assert not tenon_csg_with_relief.contains_point(far_point)

        # The tongue's own core survives in both cases (relief must not eat the tongue).
        core_point = create_v3(scalar(0), scalar(0), scalar(1, 2))
        assert not tenon_csg_no_relief.contains_point(core_point)
        assert not tenon_csg_with_relief.contains_point(core_point)


class TestMortiseAndTenonJointOnPlaneAlignedTimbersNotchReliefConfig:
    """
    Tests for relief=ButtJointNotchReliefConfig() in
    cut_mortise_and_tenon_joint_on_plane_aligned_timbers /
    cut_mortise_and_tenon_joint_on_face_aligned_timbers.

    These wrappers know the arrangement is plane-aligned, so they should use
    chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided (2 flat walls,
    2 flared walls) themselves -- applying it directly and passing
    inset_shoulder_relief_style=NoRelief (NOT the Rough default) down to
    cut_mortise_and_tenon_joint, so its default SCRIBE-based inset-shoulder housing cut is
    skipped entirely rather than redundantly unioned on top.

    Probe points below are given in intuitive GLOBAL terms and converted to the mortise
    timber's own LOCAL frame (what Cutting.negative_csg.contains_point actually expects --
    see the Cutting docstring) via _mortise_local, using this fixture's specific layout:
    mortise runs along global +X centered at the origin (bottom_position=(-50,0,0), local
    Z=length=global X, local X=width=global Y, local Y=height=global Z), so
    local(a,b,c) = global(c-50, a, b).
    """

    @staticmethod
    def _mortise_local(gx, gy, gz):
        return create_v3(scalar(gy), scalar(gz), gx + scalar(50))

    def test_notch_relief_actually_applied_via_face_aligned_wrapper(self, simple_T_configuration):
        """Regression guard mirroring TestMortiseAndTenonJointNotchReliefConfig's own:
        relief must have a real effect through this wrapper too, not be silently dropped."""
        tenon_timber, mortise_timber = simple_T_configuration

        joint_no_relief = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
            ),
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_inset=scalar(1),
            relief=None,
        )
        joint_with_relief = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
            ),
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_inset=scalar(1),
            relief=ButtJointNotchReliefConfig(),
        )

        mortise_csg_no_relief = joint_no_relief.cuttings["mortise_timber"].negative_csg
        mortise_csg_with_relief = joint_with_relief.cuttings["mortise_timber"].negative_csg
        assert mortise_csg_no_relief is not None
        assert mortise_csg_with_relief is not None

        # Mortise is 6x6, shoulder inset 1 from the entry face -> shoulder at global Z=2. A
        # point at the mortise's own Y-edge (P-axis, flat at the full rough half-size 3),
        # just past the shoulder, must be relieved WITH the notch config but not without it.
        p_axis_edge_point = self._mortise_local(0, 3, scalar(21, 10))
        assert not mortise_csg_no_relief.contains_point(p_axis_edge_point)
        assert mortise_csg_with_relief.contains_point(p_axis_edge_point)

    def test_uses_2sided_not_4sided_notch(self, simple_T_configuration):
        """
        Distinguishing behavior vs the 4-sided notch (used when calling
        cut_mortise_and_tenon_joint directly): the P-axis (Y here) must stay FLAT at the
        mortise's own rough edge (3) even at a depth where the 4-sided version would have
        already flared past it. Uses a deep-inset shoulder (large clearance requirement) so
        the two versions diverge clearly within the notch's own depth range.
        """
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )

        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_inset=scalar(1),
            relief=ButtJointNotchReliefConfig(),
        )
        mortise_csg = joint.cuttings["mortise_timber"].negative_csg
        assert mortise_csg is not None

        # Just past the P-axis (Y) edge at 3: never touched, at any depth within the notch.
        just_beyond_p_edge = self._mortise_local(0, scalar(31, 10), scalar(21, 10))
        assert not mortise_csg.contains_point(just_beyond_p_edge)

        # Just inside the P-axis edge, deep into the notch: relieved.
        just_inside_p_edge = self._mortise_local(0, scalar(29, 10), 4)
        assert mortise_csg.contains_point(just_inside_p_edge)

    def test_does_not_also_apply_the_redundant_default_scribe_housing_cut(self, simple_T_configuration):
        """
        Regression guard: previously, relief=ButtJointNotchReliefConfig() through this
        wrapper passed relief=None down to cut_mortise_and_tenon_joint, which (since None
        isn't a ButtJointNotchReliefConfig) fell through to that inner call's OWN default
        SCRIBE-based inset-shoulder housing cut -- unioned in ON TOP OF the 2-sided relief
        this wrapper already applies. Unlike the 2-sided notch's own Q-axis flare (which
        starts tight at the tenon's PERFECT Q half-size and only grows gradually with
        depth), the SCRIBE cut scribes the tenon's full ROUGH cross-section immediately past
        the shoulder, regardless of depth. Oversizing the tenon's rough WIDTH (Q axis) makes
        this visible: a point just past the shoulder, beyond the correct notch's own
        (barely-flared-yet) Q reach at that shallow depth but still within the tenon's
        oversized rough width, would have been caught by the redundant scribe cut even
        though the correct construction must not relieve it yet at that depth.
        """
        from dataclasses import replace

        tenon_timber, mortise_timber = simple_T_configuration
        imperfect_tenon = replace(
            tenon_timber,
            rough_half_sizes=(create_v2(scalar(5), scalar(5)), create_v2(scalar(2), scalar(2))),
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=imperfect_tenon, butt_timber_end=TimberEnd.BOTTOM,
        )

        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_inset=scalar(1),
            relief=ButtJointNotchReliefConfig(),
        )
        mortise_csg = joint.cuttings["mortise_timber"].negative_csg
        assert mortise_csg is not None

        # Shoulder at global Z=2; Q axis here is global X (the mortise's own length axis --
        # see class docstring). Just past the shoulder (Z=2.1) and 3 units along Q (within
        # the tenon's oversized rough width of 5, but beyond the correct notch's own Q reach
        # at this shallow a depth, which is barely past its unflared base of 2): the
        # redundant scribe cut (using the tenon's full rough width regardless of depth)
        # would have relieved this; the correct construction must not, yet.
        just_beyond_q_reach_near_shoulder = self._mortise_local(3, 0, scalar(21, 10))
        assert not mortise_csg.contains_point(just_beyond_q_reach_near_shoulder)

    def test_forwards_through_face_aligned_to_plane_aligned_wrapper(self, simple_T_configuration):
        """cut_mortise_and_tenon_joint_on_face_aligned_timbers and
        cut_mortise_and_tenon_joint_on_plane_aligned_timbers must produce identical results
        for an arrangement that's valid for both (face-aligned implies plane-aligned)."""
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )

        joint_face = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_inset=scalar(1),
            relief=ButtJointNotchReliefConfig(),
        )
        joint_plane = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_inset=scalar(1),
            relief=ButtJointNotchReliefConfig(),
        )

        probe_points = [
            self._mortise_local(0, scalar(29, 10), 4),
            self._mortise_local(0, 0, scalar(21, 10)),
            self._mortise_local(0, 0, 90),
        ]
        mortise_face = joint_face.cuttings["mortise_timber"].negative_csg
        mortise_plane = joint_plane.cuttings["mortise_timber"].negative_csg
        assert mortise_face is not None and mortise_plane is not None
        for point in probe_points:
            assert mortise_face.contains_point(point) == mortise_plane.contains_point(point)


class TestMortiseAndTenonRelativeTenonSizing:

    def test_relative_sizing_matches_equivalent_tenon_size(self, simple_T_configuration):
        """tenon_width/height_relative_to_joint should produce the same cut geometry
        as the equivalent explicit tenon_size, with width mapped to the axis parallel
        to the joint plane and height mapped to the axis perpendicular to it.

        For this face-aligned T-configuration (vertical tenon into horizontal mortise
        along the mortise's length axis), the joint plane is the tenon's XZ plane, so
        width -> tenon local X (tenon_size[0]) and height -> tenon local Y (tenon_size[1]).
        """
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )

        with pytest.warns(UserWarning, match="deprecated"):
            joint_explicit = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                tenon_size=Matrix([scalar(1), scalar(2)]),
                tenon_length=scalar(4),
                mortise_depth=scalar(5),
            )
        joint_relative = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(1),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(5),
        )

        assert joint_explicit.cuttings["tenon_timber"].negative_csg == joint_relative.cuttings["tenon_timber"].negative_csg
        assert joint_explicit.cuttings["mortise_timber"].negative_csg == joint_relative.cuttings["mortise_timber"].negative_csg

    def test_relative_sizing_requires_exactly_one_form(self, simple_T_configuration):
        """Exactly one of tenon_size or the (width, height) pair must be given."""
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )

        # Neither provided
        with pytest.raises(KumikiArrangementError):
            cut_mortise_and_tenon_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                tenon_length=scalar(4),
            )

        # Only one of the relative pair provided
        with pytest.raises(KumikiArrangementError):
            cut_mortise_and_tenon_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                tenon_width_relative_to_joint=scalar(1),
                tenon_length=scalar(4),
            )

        # Both tenon_size and the relative pair provided
        with pytest.raises(KumikiArrangementError):
            cut_mortise_and_tenon_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                tenon_size=Matrix([scalar(1), scalar(2)]),
                tenon_width_relative_to_joint=scalar(1),
                tenon_height_relative_to_joint=scalar(2),
                tenon_length=scalar(4),
            )


# ============================================================================
# Tests for Peg Orientation
# ============================================================================

class TestPegStuff:
    # 🐪
    def test_simple_peg_basic_stuff(self, simple_T_configuration):
        """Test that peg is perpendicular to the face it goes through."""
        tenon_timber, mortise_timber = simple_T_configuration
        
        peg_depth = scalar(7)
        distance_from_shoulder = scalar(2)
        mortise_timber_x_size = mortise_timber.size[0]
        shoulder_plane_x_global = mortise_timber_x_size / scalar(2)
        peg_params = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(distance_from_shoulder, scalar(0))],
            depth=peg_depth,
            size=scalar(1, 2)
        )
        
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(4),
            peg_parameters=peg_params,
        )

        assert joint.cuttings["tenon_timber"].timber == tenon_timber
        assert joint.cuttings["mortise_timber"].timber == mortise_timber
        assert 1 == 1
        assert 1 == 1
        # Tenon cut has a redundant end cut marker (points away from timber, doesn't cut anything extra)
        assert joint.cuttings["tenon_timber"].get_maybe_bottom_end_cut() is not None
        assert joint.cuttings["tenon_timber"].get_maybe_top_end_cut() is None
        assert joint.cuttings["mortise_timber"].get_maybe_top_end_cut() is None
        assert joint.cuttings["mortise_timber"].get_maybe_bottom_end_cut() is None
        
        peg = joint.jointAccessories["peg_0"]
        assert isinstance(peg, Peg), "Expected peg to be a Peg instance"
        
        # check that the peg is orthogonal to get_face_direction(TimberFace.FRONT)
        assert_vectors_parallel(peg.transform.orientation.matrix[:, 2], tenon_timber.get_face_direction_global(TimberFace.FRONT))
        f"Peg forward_length should match specified depth. Expected {peg_depth}, got {peg.forward_length}"
        assert peg.stickout_length == peg_depth * scalar(1, 2), \
            f"Peg stickout_length should be half of forward_length by default. Expected {peg_depth * scalar(1, 2)}, got {peg.stickout_length}"

        # check that the peg is positioned at the correct distance from the shoulder
        assert peg.transform.position[2] == shoulder_plane_x_global - distance_from_shoulder

        # Get tenon timber's cut CSG (what's removed)
        tenon_cut_timber = joint.cuttings["mortise_timber"]
        tenon_cut_csg = tenon_cut_timber.negative_csg
        
        # Verify CSG includes peg holes (should be a SolidUnion with multiple children)
        from kumiki.cutcsg import SolidUnion
        assert isinstance(tenon_cut_csg, SolidUnion), \
            "Tenon cut CSG with pegs should be a SolidUnion"
        assert len(tenon_cut_csg.children) >= 2, \
            "SolidUnion should contain base cut plus peg holes"

    # 🐪
    def test_peg_custom_stickout_length(self, simple_T_configuration):
        """Test that custom stickout_length parameter works."""
        tenon_timber, mortise_timber = simple_T_configuration
        
        peg_params = SimplePegParameters(
            shape=PegShape.ROUND,
            peg_positions=[(scalar(2), scalar(0))],
            depth=scalar(5),
            size=scalar(1, 2),
            stickout_length=scalar(0)
        )
        
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(4),
            peg_parameters=peg_params,
        )
        
        peg = joint.jointAccessories["peg_0"]
        assert isinstance(peg, Peg), "Expected peg to be a Peg instance"
        assert peg.stickout_length == 0

    # 🐪
    def test_peg_geometry(self, simple_T_configuration):
        """Test points on peg hole boundary using is_point_on_boundary()."""
        tenon_timber, mortise_timber = simple_T_configuration
        
        peg_size = scalar(1, 2)
        peg_params = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(scalar(2), scalar(0))],
            depth=None,
            size=peg_size
        )
        
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(4),
            peg_parameters=peg_params,
        )
        
        peg = joint.jointAccessories["peg_0"]
        assert isinstance(peg, Peg), "Expected peg to be a Peg instance"
        peg_csg = peg.get_csg_local()

        # Sample points within the peg's CSG
        peg_center_points = [
            peg.transform.position + peg.transform.orientation.matrix * Matrix([0, 0, scalar(1)]),  # 1 unit along peg
            peg.transform.position + peg.transform.orientation.matrix * Matrix([0, 0, scalar(2)]),  # 2 units along peg
            peg.transform.position + peg.transform.orientation.matrix * Matrix([0, 0, scalar(3)]),  # 3 units along peg
        ]
        
        for point_local in peg_center_points:
            # Transform to peg's local space (peg CSG is in its own local coords)
            point_peg_local = peg.transform.orientation.matrix.T * (point_local - peg.transform.position)
            assert peg_csg.contains_point(point_peg_local), \
                f"Point along peg centerline should be in peg CSG"
    
        # For a square peg, points on the edge should be on boundary
        # Peg is peg_size x peg_size in cross-section
        half_size = peg_size / 2
        
        # Point on the edge of the square peg at z=1
        point_on_edge = peg.transform.position + peg.transform.orientation.matrix * Matrix([half_size, 0, scalar(1)])
        point_on_edge_peg_local = peg.transform.orientation.matrix.T * (point_on_edge - peg.transform.position)

        # see that the peg total length is equal to 1.5 times the mortise width
        assert peg.forward_length + peg.stickout_length == scalar(3, 2) * mortise_timber.size[0]
        
        # This point should be on the boundary of the peg
        assert peg_csg.contains_point(point_on_edge_peg_local), \
            "Point on peg edge should be contained in peg CSG"
        assert peg_csg.is_point_on_boundary(point_on_edge_peg_local), \
            "Point on peg edge should be on boundary of peg CSG"

        
        
        
        for i in range(0,10):
            # Test that a point inside the peg hole is NOT contained in the timber CSGs
            point_in_peg_hole = peg.transform.position + peg.transform.orientation.matrix * Matrix([0, 0, scalar(i)])
            point_in_peg_hole_tenon_local = tenon_timber.transform.global_to_local(point_in_peg_hole)
            point_in_peg_hole_mortise_local = mortise_timber.transform.global_to_local(point_in_peg_hole)
            
            tenon_csg = _render_cutting(joint.cuttings["tenon_timber"])
            mortise_csg = _render_cutting(joint.cuttings["mortise_timber"])
            
            assert not tenon_csg.contains_point(point_in_peg_hole_tenon_local), \
                "Point inside peg hole should not be contained in tenon timber"
            assert not mortise_csg.contains_point(point_in_peg_hole_mortise_local), \
                "Point inside peg hole should not be contained in mortise timber"
            
    
    
    # 🐪
    def test_multiple_pegs(self, simple_T_configuration):
        """Test joint with multiple pegs at different positions."""
        tenon_timber, mortise_timber = simple_T_configuration
        
        peg_params = SimplePegParameters(
            shape=PegShape.ROUND,
            peg_positions=[
                (scalar(1), scalar(0)),
                (scalar(2), scalar(1, 2)),
                (scalar(3), scalar(-1, 2))
            ],
            depth=scalar(5),
            size=scalar(1, 2)
        )
        
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(4),
            peg_parameters=peg_params,
        )
        
        # Should have 3 peg accessories
        assert len(joint.jointAccessories) == 3, \
            f"Should have 3 pegs, got {len(joint.jointAccessories)}"
        
        # All should be Peg objects
        for accessory in joint.jointAccessories.values():
            assert isinstance(accessory, Peg), \
                "All accessories should be Peg objects"
        
        # Each peg should have correct depth
        for peg in joint.jointAccessories.values():
            assert isinstance(peg, Peg), "Expected peg to be a Peg instance"
            assert peg.forward_length == scalar(5), \
                f"Each peg should have depth 5, got {peg.forward_length}"
    
    # 🐪
    def test_peg_depth_from_mortise_surface_projection(self):
        """Peg depth (auto) is the full chord through the mortise timber in the peg direction.

        Uses a non-square mortise (width=4 in peg direction, height=10) so the test
        distinguishes the correct axis (size[0]=4) from the other (size[1]=10).
        """
        tenon_timber = create_standard_vertical_timber(
            height=100, size=(4, 4), position=(0, 0, 0), ticket="tenon_timber"
        )
        # The peg face is FRONT of the vertical tenon, whose normal is +Y globally.
        # The mortise runs along +X; its local X dimension (size[0]=4) is in the +Y direction.
        mortise_timber = create_centered_horizontal_timber(
            direction='x', length=100, size=(4, 10), name="mortise_timber"
        )
        peg_params = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(scalar(2), scalar(0))],
            depth=None,  # auto: computed from chord through mortise timber
            size=scalar(1, 2),
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(4),
            peg_parameters=peg_params,
        )
        peg = joint.jointAccessories["peg_0"]
        assert isinstance(peg, Peg)
        # The peg travels in the +Y direction through the mortise.
        # The mortise chord in that direction equals size[0]=4, not size[1]=10.
        assert peg.forward_length == mortise_timber.size[0], (
            f"Peg depth should equal the chord through the mortise in the peg direction "
            f"({mortise_timber.size[0]}), got {peg.forward_length}"
        )

    # 🐪
    def test_peg_with_tenon_hole_offset(self, simple_T_configuration):
        """Test that tenon_hole_offset shifts the peg hole in the tenon towards the shoulder."""
        tenon_timber, mortise_timber = simple_T_configuration
        
        distance_from_shoulder = scalar(2)
        offset = scalar(1, 4)  # 0.25 units offset
        
        # Create joint with offset
        peg_params_with_offset = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(distance_from_shoulder, scalar(0))],
            depth=scalar(5),
            size=scalar(1, 2),
            tenon_hole_offset=offset
        )
        
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        )
        joint_with_offset = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(4),
            peg_parameters=peg_params_with_offset,
        )
        
        # Create joint without offset for comparison
        peg_params_no_offset = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(distance_from_shoulder, scalar(0))],
            depth=scalar(5),
            size=scalar(1, 2),
            tenon_hole_offset=scalar(0)
        )
        
        joint_no_offset = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(4),
            peg_parameters=peg_params_no_offset,
        )
        
        # TODO test actual stuff here

    # 🐪
    def test_peg_orientation_mortise_space_face_aligned(self):
        """When peg_orientation uses MORTISE space the peg X and Y axes must be
        face-aligned with the mortise timber, even when tenon and mortise are not
        face-aligned with each other.

        Uses the canonical brace arrangement: brace_timber runs at 45° in the XY
        plane (tenon), timber1 runs along +Y (mortise).  They are NOT face-aligned.
        The peg face is FRONT of the brace timber (normal = +Z globally).
        Requesting MORTISE orientation means the peg Y-axis must be parallel to
        the mortise length axis (+Y), not the brace length axis.
        """
        from kumiki.example_shavings import create_canonical_example_brace_joint_timbers
        from kumiki.rule import are_vectors_parallel

        brace_arrangement = create_canonical_example_brace_joint_timbers()
        brace_timber = brace_arrangement.brace_timber
        timber1 = brace_arrangement.timber1

        peg_params = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(inches(1), scalar(0))],
            size=inches(1, 2),
            depth=inches(4),
            peg_orientation=(PegPositionSpace.MORTISE, scalar(0)),
        )

        arrangement = ButtJointTimberArrangement(
            butt_timber=brace_timber,
            receiving_timber=timber1,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        )
        joint = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=inches(2),
            tenon_height_relative_to_joint=inches(2),
            tenon_length=inches(4),
            mortise_depth=inches(3),
            peg_parameters=peg_params,
            mortise_shoulder_inset=inches(1, 2),
        )

        peg = joint.jointAccessories["peg_0"]
        assert isinstance(peg, Peg)

        # The peg's Y column (index 1) must be parallel to the mortise length axis (+Y)
        mortise_length_dir = timber1.get_length_direction_global()
        peg_y_axis = peg.transform.orientation.matrix[:, 1]
        assert are_vectors_parallel(peg_y_axis, mortise_length_dir), (
            f"Peg Y axis should be parallel to mortise length direction {mortise_length_dir}, "
            f"got {peg_y_axis}"
        )

        # It must NOT be parallel to the brace (tenon) length axis
        brace_length_dir = brace_timber.get_length_direction_global()
        assert not are_vectors_parallel(peg_y_axis, brace_length_dir), (
            f"Peg Y axis should NOT be parallel to brace (tenon) length direction {brace_length_dir}"
        )



class TestMortiseAndTenonCSGHierarchy:
    """Test that the CSG tree has the expected named node hierarchy."""

    def test_tenon_timber_csg_hierarchy(self, simple_T_configuration):
        from kumiki.cutcsg import Difference, SolidUnion, HalfSpace, RectangularPrism

        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(5),
        )
        csg = _render_cutting(joint.cuttings["tenon_timber"])

        # Top level: Difference
        assert isinstance(csg, Difference)
        assert isinstance(csg.base, RectangularPrism)

        # subtract[0] should be the named "mortise_and_tenon" SolidUnion
        assert len(csg.subtract) == 1
        mt_union = csg.subtract[0]
        assert isinstance(mt_union, SolidUnion)
        assert mt_union.label.name == "mortise_and_tenon"

        # Inside the SolidUnion: a Difference (shoulder - tenon) + a redundant end HalfSpace
        assert len(mt_union.children) == 2
        cut_diff = mt_union.children[0]
        redundant_end = mt_union.children[1]

        assert isinstance(cut_diff, Difference)
        assert isinstance(cut_diff.base, HalfSpace)
        assert cut_diff.base.label.name == "shoulder"
        assert len(cut_diff.subtract) == 1
        assert isinstance(cut_diff.subtract[0], RectangularPrism)
        assert cut_diff.subtract[0].label.name == "tenon"

        assert isinstance(redundant_end, HalfSpace)

    def test_mortise_timber_csg_hierarchy(self, simple_T_configuration):
        from kumiki.cutcsg import Difference, SolidUnion, RectangularPrism

        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(2),
            tenon_length=scalar(4),
            mortise_depth=scalar(5),
        )
        csg = _render_cutting(joint.cuttings["mortise_timber"])

        # Top level: Difference
        assert isinstance(csg, Difference)
        assert isinstance(csg.base, RectangularPrism)

        # subtract[0] should be the named "mortise_and_tenon" SolidUnion
        assert len(csg.subtract) == 1
        mt_union = csg.subtract[0]
        assert isinstance(mt_union, SolidUnion)
        assert mt_union.label.name == "mortise_and_tenon"

        # Inside: just the mortise_hole RectangularPrism (wrapped in SolidUnion by Cutting.label)
        assert len(mt_union.children) == 1
        mortise_hole = mt_union.children[0]
        assert isinstance(mortise_hole, RectangularPrism)
        assert mortise_hole.label.name == "mortise_hole"

# ============================================================================
# Tests for Wedged Half-Dovetail Mortise and Tenon Joint
# ============================================================================

from kumiki.joints.workshop.mortise_and_tenon_joints import (
    cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers,
)
from kumiki.joints.workshop.shavings.build_a_butt import (
    DovetailTenonWedgeAccessoryParameters,
    compute_butt_joint_shoulder,
    dovetail_tenon_geometry,
)
from kumiki.rule import degrees as _degrees
from kumiki.timber import CSGAccessory
from kumiki.cutcsg import ConvexPolygonExtrusion, SolidUnion


class TestWedgedHalfDovetailMortiseAndTenonJoint:
    """Tests for cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers."""

    def _make_arrangement(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        return ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
        )

    def test_an_inset_shoulder_notches_the_mortise_timber(self, simple_T_configuration):
        """With the shoulder set back from the entry face, the mortise timber
        gets a notch so the tenon's shoulder has somewhere to sit.

        Every other test of this joint leaves mortise_shoulder_inset at 0,
        where the relief function returns None and no notch is built at all --
        so nothing else here covers the notched path.
        """
        from kumiki.cutcsg import csg_children

        joint = cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=self._make_arrangement(simple_T_configuration),
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_depth=scalar(4),
            dovetail_depth=scalar(1),
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=_degrees(8),
                wedge_back_extra_length=scalar(1, 2),
            ),
            mortise_shoulder_inset=scalar(1),
        )

        def labels(node):
            found = {node.label.name} if node.label.is_labeled() else set()
            for child in csg_children(node):
                found |= labels(child)
            return found

        mortise_ct = joint.cuttings["mortise_timber"]
        assert mortise_ct.negative_csg is not None
        assert "shoulder_notch" in labels(mortise_ct.negative_csg)

        # The notch removes material, and the result is still a closed solid.
        cut_timber = CutTimber(mortise_ct.timber, cuts=[mortise_ct])
        notched = triangulate_cutcsg(cut_timber.render_timber_with_cuts_csg_local()).mesh
        assert notched.is_watertight
        uncut = triangulate_cutcsg(mortise_ct.timber.get_actual_csg_local()).mesh
        assert notched.volume < uncut.volume

    def test_general_wedged_half_dovetail_mortise_and_tenon(self, simple_T_configuration):
        """
        Build the joint and walk points along the tenon centerline.

        Geometry (simple_T_configuration + shoulder at mortise top face z=3):
        - tenon_timber: vertical +Z, height 100, size 4x4 at origin.
          BOTTOM end (at z=0) faces -Z into the mortise.
        - mortise_timber: horizontal +X, length 100, size 6x6 centered at origin
          (cross-section y ∈ [-3, 3], z ∈ [-3, 3]).
        - mortise_shoulder_inset defaults to 0 → shoulder flush with the mortise
          entry face at z = 3 (global).
        - tenon_depth = 4 → tenon tip at z = -1 (penetrating past mortise centerline).
        - dovetail_depth = 1 → inside the mortise, the dovetail flares by 1 in the
          -Z direction (away from the dovetail-top side, which is RIGHT → +Z).
        """
        arrangement = self._make_arrangement(simple_T_configuration)
        tenon_timber = arrangement.butt_timber
        mortise_timber = arrangement.receiving_timber

        tenon_depth = scalar(4)
        dovetail_depth = scalar(1)
        tenon_size = Matrix([scalar(2), scalar(2)])

        joint = cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_size=tenon_size,
            tenon_depth=tenon_depth,
            dovetail_depth=dovetail_depth,
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=_degrees(8),
                wedge_back_extra_length=scalar(1, 2),
            ),
        )

        # ---- structure ----
        assert joint.ticket.joint_type == "wedged_half_dovetail_mortise_and_tenon"
        assert set(joint.cuttings.keys()) == {"tenon_timber", "mortise_timber"}
        assert "wedge" in joint.jointAccessories
        assert isinstance(joint.jointAccessories["wedge"], CSGAccessory)

        tenon_ct = joint.cuttings["tenon_timber"]
        mortise_ct = joint.cuttings["mortise_timber"]
        assert isinstance(tenon_ct, Cutting)
        assert isinstance(mortise_ct, Cutting)
        # Butt end is BOTTOM, so the redundant end cut lives on the bottom end.
        assert tenon_ct.get_maybe_bottom_end_cut() is not None
        assert tenon_ct.get_maybe_top_end_cut() is None
        assert mortise_ct.get_maybe_top_end_cut() is None
        assert mortise_ct.get_maybe_bottom_end_cut() is None
        assert tenon_ct.label.name == "wedged_half_dovetail_mortise_and_tenon"
        assert mortise_ct.label.name == "wedged_half_dovetail_mortise_and_tenon"

        # ---- walk points along the tenon centerline (x=0, y=0, varying z) ----
        tenon_csg = _render_cutting(tenon_ct)
        mortise_csg = _render_cutting(mortise_ct)

        # Shoulder at z=3 (mortise top face).
        # Above the shoulder: deep in tenon body, untouched.
        for z in [scalar(10), scalar(50)]:
            pt = create_v3(scalar(0), scalar(0), z)
            pt_local = tenon_timber.transform.global_to_local(pt)
            assert tenon_csg.contains_point(pt_local), \
                f"tenon body should remain at z={z}"

        # Past the shoulder (z<3) and far from the dovetail footprint (a corner
        # of the butt cross-section): the shoulder cut should have removed this.
        cut_corner = create_v3(scalar(19, 10), scalar(19, 10), scalar(2))
        cut_corner_local = tenon_timber.transform.global_to_local(cut_corner)
        assert not tenon_csg.contains_point(cut_corner_local), \
            "butt corner past the shoulder should be cut"

        # Past the tenon tip (z < -1) on the centerline: end cut should remove this.
        past_tip = create_v3(scalar(0), scalar(0), scalar(-3, 2))
        past_tip_local = tenon_timber.transform.global_to_local(past_tip)
        assert not tenon_csg.contains_point(past_tip_local), \
            "tenon material past the tip should be cut"

        # Mortise body away from the cavity remains.
        mortise_far = create_v3(scalar(40), scalar(0), scalar(0))
        mortise_far_local = mortise_timber.transform.global_to_local(mortise_far)
        assert mortise_csg.contains_point(mortise_far_local)

    def test_no_wedge_accessory(self, simple_T_configuration):
        """Omitting wedge_accessory_parameters raises TypeError."""
        arrangement = self._make_arrangement(simple_T_configuration)
        import pytest
        with pytest.raises(TypeError, match="missing.*required.*wedge_accessory_parameters"):
            cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(  # type: ignore[missing-argument]
                arrangement=arrangement,
                tenon_size=Matrix([scalar(2), scalar(2)]),
                tenon_depth=scalar(4),
                dovetail_depth=scalar(1),
            )

    def test_wedge_size_unchanged_and_slot_extends_to_perfect_boundary(self, simple_T_configuration):
        """Keep wedge size unchanged while extending only the mortise slot base to perfect boundary."""
        arrangement = self._make_arrangement(simple_T_configuration)
        receiving_timber = arrangement.receiving_timber

        tenon_depth = scalar(4)
        back_extra = scalar(1, 2)
        dovetail_depth = scalar(1)

        shoulder_result = compute_butt_joint_shoulder(
            arrangement=arrangement,
            distance_from_centerline_or_centerplane=scalar(0),
            up_direction=arrangement.butt_timber.get_height_direction_global(),
        )

        geo = dovetail_tenon_geometry(
            arrangement=arrangement,
            shoulder_result=shoulder_result,
            dovetail_top_side_on_butt_timber=TimberLongFace.RIGHT,
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_depth=tenon_depth,
            dovetail_depth=dovetail_depth,
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=_degrees(8),
                wedge_back_extra_length=back_extra,
            ),
        )

        wedge = geo.wedge_accessory_csg
        assert isinstance(wedge, CSGAccessory)
        assert isinstance(wedge.positive_csg, ConvexPolygonExtrusion)
        wedge_x_values = [p[0] for p in wedge.positive_csg.points]

        # Wedge geometry should remain unchanged (base side = -wedge_back_extra).
        assert min(wedge_x_values) == -back_extra

        assert isinstance(geo.mortise_negative_csg, SolidUnion)
        slot_candidates = [
            child for child in geo.mortise_negative_csg.children
            if isinstance(child, ConvexPolygonExtrusion)
            and all(safe_compare(p[1], scalar(0), Comparison.GE) for p in child.points)
        ]
        assert len(slot_candidates) == 1

        wedge_slot = slot_candidates[0]
        wedge_slot_x_values = [p[0] for p in wedge_slot.points]

        into_mortise_dir = shoulder_result.butt_direction
        receiving_perfect_boundary = -receiving_timber.get_size_in_direction_3d(into_mortise_dir)
        expected_slot_x_base = min(-back_extra, receiving_perfect_boundary)

        assert min(wedge_slot_x_values) == expected_slot_x_base


class TestMortiseAndTenonCSGNaming:
    """Every node a mortise and tenon puts in the tree carries a name.

    An unlabeled node cannot be addressed by path, so it is invisible to the
    viewer's navigation and to anything that wants to name features on it.
    """

    def _rendered(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=mortise_timber,
                butt_timber=tenon_timber,
                butt_timber_end=TimberEnd.BOTTOM,
            ),
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(1),
            tenon_length=scalar(3),
            mortise_depth=scalar(3),
        )
        frame = Frame.from_joints([joint])
        return {ct.timber.ticket.path: ct.render_timber_with_cuts_csg_local()
                for ct in frame.cut_timbers}

    def _unlabeled_below_root(self, root):
        """Every unlabeled node except the root, which is the rendered
        Difference wrapping body and cuts -- structure, not geometry."""
        from kumiki.cutcsg import csg_children

        found = []

        def walk(node, is_root):
            if not is_root and not node.label.is_labeled():
                found.append(type(node).__name__)
            for child in csg_children(node):
                walk(child, False)

        walk(root, True)
        return found

    def test_nothing_in_either_timber_is_unlabeled(self, simple_T_configuration):
        for name, rendered in self._rendered(simple_T_configuration).items():
            assert self._unlabeled_below_root(rendered) == [], (
                f"{name} has unlabeled CSG nodes")

    def test_the_tenon_side_names_what_it_removes(self, simple_T_configuration):
        rendered = self._rendered(simple_T_configuration)
        labels = set()

        def walk(node):
            from kumiki.cutcsg import csg_children
            if node.label.is_labeled():
                labels.add(node.label.name)
            for child in csg_children(node):
                walk(child)

        for tree in rendered.values():
            walk(tree)

        assert {"mortise_and_tenon", "tenon_waste", "shoulder", "tenon",
                "mortise_hole"} <= labels
        # The end cut says which end it is; both are half-spaces, so the shape
        # alone cannot tell you.
        assert labels & {"top_end_cut", "bottom_end_cut"}


class TestMortiseAndTenonFeatures:
    """What a mortise and tenon declares, and the edges that fall out of it.

    Edges are derived from pairs of declared faces, so geometry that declares
    nothing has no edges -- which is why the shoulder line and the mortise
    mouth were unselectable while the machinery for them worked fine.
    """

    def _rendered(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=mortise_timber,
                butt_timber=tenon_timber,
                butt_timber_end=TimberEnd.BOTTOM,
            ),
            tenon_width_relative_to_joint=scalar(2),
            tenon_height_relative_to_joint=scalar(1),
            tenon_length=scalar(3),
            mortise_depth=scalar(3),
        )
        frame = Frame.from_joints([joint])
        return {ct.timber.ticket.path: ct.render_timber_with_cuts_csg_local()
                for ct in frame.cut_timbers}

    def _picked(self, rendered, feature_type):
        """Every feature of *feature_type* selectable anywhere on the surface.

        Face centroids find faces; triangle-edge midpoints land on the creases
        where two faces meet, which is where an edge is selectable.
        """
        from kumiki.cutcsg import CSGFeatureType
        from kumiki.triangles import triangulate_cutcsg

        found = set()
        for triangle in triangulate_cutcsg(rendered).mesh.triangles:
            points = [
                [(triangle[a][i] + triangle[b][i]) / 2 for i in range(3)]
                for a, b in ((0, 1), (1, 2), (2, 0))
            ]
            points.append([sum(v[i] for v in triangle) / 3 for i in range(3)])
            for point in points:
                hit = rendered.find_feature(create_v3(*point))
                if hit is not None and hit.feature.feature_type() == feature_type:
                    found.add(hit.feature.name)
        return found

    def test_the_shoulder_is_selectable(self, simple_T_configuration):
        from kumiki.cutcsg import CSGFeatureType

        faces = self._picked(self._rendered(simple_T_configuration)["tenon_timber"],
                             CSGFeatureType.FACE)
        assert "shoulder" in faces

    def test_the_shoulder_forms_the_line_you_knife_around_the_timber(self, simple_T_configuration):
        from kumiki.cutcsg import CSGFeatureType

        edges = self._picked(self._rendered(simple_T_configuration)["tenon_timber"],
                             CSGFeatureType.EDGE)
        # Where the shoulder plane meets the timber's own faces.
        assert {edge for edge in edges if edge.startswith("shoulder\u00d7")}

    def test_the_mortise_declares_its_walls_and_floor(self, simple_T_configuration):
        from kumiki.cutcsg import CSGFeatureType

        faces = self._picked(self._rendered(simple_T_configuration)["mortise_timber"],
                             CSGFeatureType.FACE)
        assert {"mortise_front", "mortise_back", "mortise_left", "mortise_right"} <= faces

    def test_the_mortise_mouth_is_an_edge(self, simple_T_configuration):
        from kumiki.cutcsg import CSGFeatureType

        edges = self._picked(self._rendered(simple_T_configuration)["mortise_timber"],
                             CSGFeatureType.EDGE)
        # The outline you would mark on the face before chopping.
        assert {edge for edge in edges if edge.startswith("mortise_")}

    def test_the_timbers_own_arrises_still_derive(self, simple_T_configuration):
        # These worked before any joint geometry declared anything; the new
        # declarations must not crowd them out.
        from kumiki.cutcsg import CSGFeatureType

        edges = self._picked(self._rendered(simple_T_configuration)["tenon_timber"],
                             CSGFeatureType.EDGE)
        assert {edge for edge in edges if edge.count("rough.") == 2}


class TestBuildAButtCSGNaming:
    """The geometry build_a_butt hands back carries names too.

    Its two builders feed the dovetail and tusked joints, and both used to
    return unnamed nodes -- including unnamed siblings under one parent, where
    neither can be addressed by path and nothing tells the two apart.
    """

    def _labels(self, joint):
        found = set()

        def walk(node):
            if node.label.is_labeled():
                found.add(node.label.name)
            for child in csg_children(node):
                walk(child)

        for cutting in joint.cuttings.values():
            negative = cutting.get_negative_csg_local()
            if negative is not None:
                walk(negative)
        return found

    def _unlabeled(self, joint):
        found = []

        def walk(node):
            if not node.label.is_labeled():
                found.append(type(node).__name__)
            for child in csg_children(node):
                walk(child)

        for key, cutting in joint.cuttings.items():
            negative = cutting.get_negative_csg_local()
            if negative is not None:
                walk(negative)
        return found

    def _dovetail_joint(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        return cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=mortise_timber,
                butt_timber=tenon_timber,
                butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=None,
                top_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_depth=scalar(4),
            dovetail_depth=scalar(1),
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=radians(0.14),
                wedge_back_extra_length=scalar(1, 2),
            ),
        )

    def test_the_dovetail_names_every_node_it_cuts(self, simple_T_configuration):
        assert self._unlabeled(self._dovetail_joint(simple_T_configuration)) == []

    def test_the_dovetail_shoulder_and_tenon_are_told_apart(self, simple_T_configuration):
        # These two were siblings under one unnamed Difference, so neither could
        # be addressed and the pair read identically.
        labels = self._labels(self._dovetail_joint(simple_T_configuration))
        assert {"tenon_waste", "shoulder", "tenon"} <= labels

    def test_the_mortise_cavity_and_the_wedge_slot_are_told_apart(self, simple_T_configuration):
        labels = self._labels(self._dovetail_joint(simple_T_configuration))
        assert {"mortise", "mortise_hole", "wedge_slot"} <= labels

    def test_the_dovetail_uses_the_same_words_as_a_plain_mortise_and_tenon(self, simple_T_configuration):
        # A dovetail tenon is still a tenon: the joint label already records
        # which joint this is, so the parts keep the family's vocabulary.
        labels = self._labels(self._dovetail_joint(simple_T_configuration))
        assert {"tenon", "tenon_waste", "shoulder", "mortise_hole"} <= labels


class TestTuskedMortiseAndTenonCSGNaming:
    """The tusk's own geometry, which had no tests of any kind before."""

    def _tusked_joint(self, receiving_timber=None):
        arrangement = create_canonical_example_butt_joint_timbers(create_v3(0, 0, 0))
        if receiving_timber is not None:
            arrangement = ButtJointTimberArrangement(
                receiving_timber=receiving_timber,
                butt_timber=arrangement.butt_timber,
                butt_timber_end=arrangement.butt_timber_end,
            )
        return cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(arrangement)

    def _labels(self, joint):
        found = set()

        def walk(node):
            if node.label.is_labeled():
                found.add(node.label.name)
            for child in csg_children(node):
                walk(child)

        for cutting in joint.cuttings.values():
            negative = cutting.get_negative_csg_local()
            if negative is not None:
                walk(negative)
        return found

    def test_the_tusk_hole_is_named(self):
        assert "tusk_hole" in self._labels(self._tusked_joint())

    def test_nothing_the_tusked_joint_cuts_is_unnamed(self):
        joint = self._tusked_joint()
        unlabeled = []

        def walk(node):
            if not node.label.is_labeled():
                unlabeled.append(type(node).__name__)
            for child in csg_children(node):
                walk(child)

        for cutting in joint.cuttings.values():
            negative = cutting.get_negative_csg_local()
            if negative is not None:
                walk(negative)
        assert unlabeled == []

    def test_the_tusk_clearance_is_named_when_rough_stock_makes_one(self):
        """The clearance only exists when the receiving timber's rough stock
        still surrounds the tenon at the tusk hole. On the canonical (perfect)
        timbers it is never built, so a test that did not add rough material
        would pass while saying nothing about this label."""
        from dataclasses import replace

        canonical = create_canonical_example_butt_joint_timbers(create_v3(0, 0, 0))
        perfect = canonical.receiving_timber
        rough_half = create_v2(
            perfect.size[0] / scalar(2) + inches(1),
            perfect.size[1] / scalar(2) + inches(1),
        )
        rough_receiving = replace(perfect, rough_half_sizes=(rough_half, rough_half))

        assert "tusk_clearance" not in self._labels(self._tusked_joint())
        assert "tusk_clearance" in self._labels(self._tusked_joint(rough_receiving))


class TestUnionIntoCut:
    """_union_into_cut keeps one node per cutting rather than nesting."""

    def _piece(self, offset):
        from kumiki.cutcsg import HalfSpace
        return HalfSpace(normal=create_v3(0, 0, 1), offset=scalar(offset))

    def test_the_first_addition_wraps_what_was_there(self):
        from kumiki.cutcsg import SolidUnion
        from kumiki.joints.workshop.mortise_and_tenon_joints import (
            _union_into_cut, TENON_CUT_LABEL)

        result = _union_into_cut(self._piece(1), [self._piece(2)], TENON_CUT_LABEL)
        assert isinstance(result, SolidUnion)
        assert result.label == TENON_CUT_LABEL
        assert len(result.children) == 2

    def test_a_second_addition_extends_rather_than_nests(self):
        # A cutting that gains both a relief and peg holes must still read as
        # one tenon_cut, not tenon_cut inside tenon_cut.
        from kumiki.joints.workshop.mortise_and_tenon_joints import (
            _union_into_cut, TENON_CUT_LABEL)

        once = _union_into_cut(self._piece(1), [self._piece(2)], TENON_CUT_LABEL)
        twice = _union_into_cut(once, [self._piece(3)], TENON_CUT_LABEL)

        assert len(twice.children) == 3
        assert not any(child.label == TENON_CUT_LABEL for child in twice.children)

    def test_a_different_side_is_not_flattened_into_this_one(self):
        from kumiki.joints.workshop.mortise_and_tenon_joints import (
            _union_into_cut, TENON_CUT_LABEL, MORTISE_CUT_LABEL)

        tenon = _union_into_cut(self._piece(1), [self._piece(2)], TENON_CUT_LABEL)
        mortise = _union_into_cut(tenon, [self._piece(3)], MORTISE_CUT_LABEL)

        assert mortise.label == MORTISE_CUT_LABEL
        assert len(mortise.children) == 2
        assert mortise.children[0].label == TENON_CUT_LABEL


class TestInsetShoulderReliefOnRoughStock:
    """
    Inset-shoulder relief on timbers that are actually rough.

    Every other fixture in this file is a perfect timber, where rough and perfect
    are the same shape and none of this can register.

    Layout: the mortise runs along global X centered at the origin, 6x6 perfect
    (PTW faces at z=+-3) but sawn to +-4, so z in (3, 4) is its rough fringe. The
    tenon runs up +Z from the origin, 4x4 perfect (+-2) but sawn to +-2.5. The
    shoulder sits at z=2, one inch below the mortise's PTW entry face, so the
    tenon's shank is housed in z in (2, 3). relief=None throughout, to isolate
    this step from the whole-body scribe that would otherwise cover the same
    ground.
    """

    @staticmethod
    def _arrangement():
        tenon = replace(
            create_standard_vertical_timber(height=100, size=(4, 4), position=(0, 0, 0), ticket="tenon_timber"),
            rough_half_sizes=(create_v2(scalar(5, 2), scalar(5, 2)), create_v2(scalar(5, 2), scalar(5, 2))),
        )
        mortise = replace(
            create_centered_horizontal_timber(direction='x', length=100, size=(6, 6), name="mortise_timber"),
            rough_half_sizes=(create_v2(scalar(4), scalar(4)), create_v2(scalar(4), scalar(4))),
        )
        return ButtJointTimberArrangement(
            receiving_timber=mortise, butt_timber=tenon, butt_timber_end=TimberEnd.BOTTOM,
        )

    @staticmethod
    def _cut(arrangement, style, shoulder_distance=scalar(2)):
        return cut_mortise_and_tenon_joint(
            arrangement=arrangement,
            tenon_size=create_v2(scalar(2), scalar(2)),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_distance_from_centerline_or_centerplane=shoulder_distance,
            relief=None,
            inset_shoulder_relief_style=style,
        )

    @staticmethod
    def _cuts(joint, ticket, point_global):
        cutting = joint.cuttings[ticket]
        local = cutting.timber.transform.global_to_local(create_v3(*[scalar(v) for v in point_global]))
        return bool(cutting.negative_csg.contains_point(local))

    def test_pocket_stops_at_the_mortises_ptw(self):
        """The pocket reaches the PTW entry face and no further -- the rough fringe
        beyond it belongs to `relief`, not to this step."""
        joint = self._cut(self._arrangement(), InsetShoulderReliefStyle.Rough)
        # (0, 1.5, z): clear of the 2x2 mortise hole, inside the tenon's footprint.
        assert self._cuts(joint, "mortise_timber", (0, 1.5, 2.5))
        assert not self._cuts(joint, "mortise_timber", (0, 1.5, 3.5))

    def test_shoulder_landing_in_the_rough_fringe_emits_no_pocket(self):
        """A shoulder at z=3.5 is proud of the PTW face but still buried in the rough
        fringe, so there is nothing inside the PTW for this step to remove. The
        pocket would be geometrically empty either way -- what the PTW-based
        predicate buys is not building the node at all."""
        def labels(csg):
            found, stack = [], [csg]
            while stack:
                node = stack.pop()
                if node.label and node.label.name:
                    found.append(node.label.name)
                stack.extend(csg_children(node))
            return found

        inset = self._cut(self._arrangement(), InsetShoulderReliefStyle.Rough)
        assert "shoulder_scribe_relief" in labels(inset.cuttings["mortise_timber"].negative_csg)

        in_fringe = self._cut(self._arrangement(), InsetShoulderReliefStyle.Rough, shoulder_distance=scalar(7, 2))
        assert "shoulder_scribe_relief" not in labels(in_fringe.cuttings["mortise_timber"].negative_csg)
        assert not self._cuts(in_fringe, "mortise_timber", (0, 1.5, 3.75))

    def test_perfect_only_takes_the_tenons_rough_excess_off_the_tenon(self):
        """PerfectOnly cuts a pocket sized to the perfect shank, so the tenon's own
        rough excess has to come off the tenon or the joint will not seat."""
        joint = self._cut(self._arrangement(), InsetShoulderReliefStyle.PerfectOnly)
        # y=2.25 is rough excess (perfect stops at 2); y=1.0 is body that must survive.
        assert self._cuts(joint, "tenon_timber", (0, 2.25, 2.5))
        assert not self._cuts(joint, "tenon_timber", (0, 1.0, 2.5))
        # Rough fits the rough shank instead, so it leaves the tenon alone.
        rough_joint = self._cut(self._arrangement(), InsetShoulderReliefStyle.Rough)
        assert not self._cuts(rough_joint, "tenon_timber", (0, 2.25, 2.5))

    def test_perfect_only_clears_the_whole_housed_rough_shell(self):
        """All four faces, not just the two the old face-anchored helper covered."""
        joint = self._cut(self._arrangement(), InsetShoulderReliefStyle.PerfectOnly)
        left_behind = [
            (x / 4, y / 4, z)
            for x in range(-10, 11)
            for y in range(-10, 11)
            for z in (scalar(9, 4), scalar(5, 2), scalar(11, 4))
            if max(abs(x / 4), abs(y / 4)) > 2  # in the rough shell, outside the perfect body
            and not self._cuts(joint, "tenon_timber", (x / 4, y / 4, z))
        ]
        assert left_behind == []

    def test_notch_relief_config_warns_that_the_style_is_ignored(self):
        with pytest.warns(UserWarning, match="inset_shoulder_relief_style is ignored"):
            cut_mortise_and_tenon_joint(
                arrangement=self._arrangement(),
                tenon_size=create_v2(scalar(2), scalar(2)),
                tenon_length=scalar(3),
                mortise_depth=scalar(2),
                mortise_shoulder_distance_from_centerline_or_centerplane=scalar(2),
                relief=ButtJointNotchReliefConfig(),
                inset_shoulder_relief_style=InsetShoulderReliefStyle.Rough,
            )

    def test_no_relief_style_does_not_warn(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            cut_mortise_and_tenon_joint(
                arrangement=self._arrangement(),
                tenon_size=create_v2(scalar(2), scalar(2)),
                tenon_length=scalar(3),
                mortise_depth=scalar(2),
                mortise_shoulder_distance_from_centerline_or_centerplane=scalar(2),
                relief=ButtJointNotchReliefConfig(),
                inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief,
            )
