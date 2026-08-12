"""
Tests for the shoulder-notch and relief-cut helpers in kumiki.joints.workshop.relief.
"""

from dataclasses import replace

from kumiki.cutcsg import ConvexPolygonSimpleLoft, Difference, Intersection
from kumiki.construction import ArrangementNames, ButtJointTimberArrangement
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.joints.workshop.shavings.relief import (
    BraceJointScribeReliefConfig,
    ButtJointNotchReliefConfig,
    CrossCapJointScribeReliefConfig,
    DoubleButtJointScribeReliefConfig,
    QuadrupleButtJointScribeReliefConfig,
    ShoulderReliefCSGGeometry,
    TripleButtJointScribeReliefConfig,
    chop_butt_joint_shoulder_notch_relief_4sided,
    chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided,
    chop_relief_for_butt_joint_arrangement,
    chop_scribe_relief,
    chop_shoulder_notch_aligned_with_timber,
    does_shoulder_plane_need_notching,
)
from kumiki.joints.workshop.mortise_and_tenon_joints import cut_mortise_and_tenon_joint
from kumiki.rule import (
    Matrix,
    Orientation,
    Transform,
    create_v2,
    degrees,
    inches,
    safe_normalize_vector as safe_normalize_vector,
    scalar,
)
from kumiki.timber import (
    TimberFace,
    TimberEnd,
    create_v3,
    create_timber,
    Cutting,
    CutTimber,
)
from kumiki.timber_shavings import are_timbers_plane_aligned
from tests.testing_shavings import (
    create_centered_horizontal_timber,
    create_standard_horizontal_timber,
    create_standard_vertical_timber,
)


# ============================================================================
# Test Fixtures
# ============================================================================


import pytest


@pytest.fixture
def simple_T_configuration():
    """Simple T: vertical 4x4 tenon timber + horizontal 6x6 mortise timber."""
    tenon_timber = create_standard_vertical_timber(
        height=100, size=(4, 4), position=(0, 0, 0), ticket="tenon_timber"
    )
    mortise_timber = create_centered_horizontal_timber(
        direction='x', length=100, size=(6, 6), name="mortise_timber"
    )
    return (tenon_timber, mortise_timber)


# ============================================================================
# Tests
# ============================================================================


class TestShoulderNotchingDecision:
    """Tests for does_shoulder_plane_need_notching."""

    def test_does_shoulder_plane_need_notching(self, simple_T_configuration):
        """Uses face/plane-aligned logic when aligned, and always True when not plane-aligned."""
        tenon_timber, mortise_timber = simple_T_configuration

        aligned_arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )
        assert are_timbers_plane_aligned(mortise_timber, tenon_timber)

        tenon_end_direction = tenon_timber.get_face_direction_global(TimberEnd.BOTTOM)
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        face_half_size = mortise_timber.get_size_in_face_normal_axis(mortise_face) / scalar(2)

        assert does_shoulder_plane_need_notching(aligned_arrangement, face_half_size - scalar(1))
        assert not does_shoulder_plane_need_notching(aligned_arrangement, face_half_size)

        non_plane_mortise = create_timber(
            length=scalar(100),
            size=create_v2(scalar(6), scalar(6)),
            bottom_position=create_v3(-scalar(50), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="non_plane_mortise",
        )
        non_plane_tenon = create_timber(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            width_direction=safe_normalize_vector(create_v3(scalar(1), scalar(0), scalar(1))),
            ticket="non_plane_tenon",
        )
        non_plane_arrangement = ButtJointTimberArrangement(
            receiving_timber=non_plane_mortise,
            butt_timber=non_plane_tenon,
            butt_timber_end=TimberEnd.BOTTOM,
        )

        assert not are_timbers_plane_aligned(non_plane_mortise, non_plane_tenon)
        assert does_shoulder_plane_need_notching(non_plane_arrangement, scalar(100))


class TestChopReliefForButtJointArrangement:
    """Tests for chop_relief_for_butt_joint_arrangement."""

    def test_returns_geometry_for_inset_shoulder(self, simple_T_configuration):
        """
        For a simple T-arrangement with the shoulder inset from the entry face,
        the helper returns geometry for BOTH the receiving timber notch and the
        butting timber relief cut. When the shoulder is at or past the entry
        face, the helper returns None.
        """
        from kumiki.cutcsg import Difference, RectangularPrism, SolidUnion

        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )

        # Mortise is 6x6, so rough entry face half-size = 3.
        # An inset shoulder at distance 2 from the centerline (< 3) requires notching.
        inset_distance = scalar(2)
        geom = chop_relief_for_butt_joint_arrangement(
            arrangement, inset_distance
        )
        assert geom is not None
        assert isinstance(geom, ShoulderReliefCSGGeometry)
        # The receiving timber notch should be a prism or union of prisms.
        assert isinstance(
            geom.receiving_timber_notch_negative_CSG, (RectangularPrism, SolidUnion)
        )
        # The butting timber relief CSG is built via Difference for any non-trivial joint.
        assert geom.butting_timber_relief_negative_CSG is not None
        assert isinstance(geom.butting_timber_relief_negative_CSG, Difference)

        # A flush shoulder (distance equal to rough half-size) needs no notch.
        tenon_end_direction = tenon_timber.get_face_direction_global(
            TimberFace.BOTTOM
        )
        entry_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        face_half_size = mortise_timber.get_half_rough_size_in_face_normal_axis(
            entry_face
        )
        assert (
            chop_relief_for_butt_joint_arrangement(arrangement, face_half_size)
            is None
        )


class TestChopButtJointShoulderNotchRelief4Sided:
    """Tests for chop_butt_joint_shoulder_notch_relief_4sided."""

    def test_returns_none_for_flush_shoulder(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )
        # Mortise is 6x6, so a shoulder at the rough half-size (3) is flush -- no notch needed.
        assert chop_butt_joint_shoulder_notch_relief_4sided(arrangement, scalar(3)) is None

    def test_notch_extends_toward_tenon_not_backward_into_solid_mortise(self, simple_T_configuration):
        """
        Anchors the notch's location in GLOBAL/absolute terms using coordinates derived
        independently of the loft's own transform (unlike the local-frame test below, whose
        query points are generated FROM loft.transform -- self-referential, so it stays
        "self-consistent" and passes even if the whole loft is built pointing backward; it
        would NOT have caught this bug). Points here are computed directly from the known
        timber geometry instead.

        Setup: mortise is 6x6 (half-size 3 in Z, its height axis), centered at the origin in
        cross-section; tenon (4x4, half-width 2) rises from Z=0 along the shared centerline.
        Shoulder is inset 2 from the mortise centerline -> shoulder plane at Z=2, entry face
        at Z=3 (toward the tenon). At depth loft_depth/2=1.5 past the shoulder (Z=3.5), the
        interpolated flare half-width is 3.5 (from 2 at the shoulder to 5 at full depth), so
        X=3 sits safely inside it. The point's mirror image reflected across the shoulder
        plane (Z=0.5, same X) lies backward, deep in the mortise's own remaining solid
        interior -- exactly where the bug misplaced the frustum -- and must never be touched.
        """
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )

        geom = chop_butt_joint_shoulder_notch_relief_4sided(arrangement, scalar(2))
        assert geom is not None
        from kumiki.cutcsg import adopt_csg
        notch_global = adopt_csg(mortise_timber.transform, Transform.identity(), geom.receiving_timber_notch_negative_CSG)

        forward_point = Matrix([scalar(3), scalar(0), scalar(7, 2)])   # X=3, Z=3.5: toward tenon, inside the flare
        backward_point = Matrix([scalar(3), scalar(0), scalar(1, 2)])  # X=3, Z=0.5: mirrored, into solid mortise

        assert notch_global.contains_point(forward_point)
        assert not notch_global.contains_point(backward_point)

    def test_perpendicular_notch_flares_symmetrically_around_the_tenon(self, simple_T_configuration):
        """
        For a straight (non-raking) T, all 4 of the tenon's long faces meet the shoulder
        plane at 90 degrees, so the loft flares outward by the same amount on every side:
        the notch (the raw frustum loft -- its straight core is also removed, redundantly
        but harmlessly, by the separately-unioned mortise hole prism) should contain points
        just past the tenon's perfect corner, contain its own straight core, and exclude
        points entirely outside the loft.
        """
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
        )

        geom = chop_butt_joint_shoulder_notch_relief_4sided(arrangement, scalar(2))
        assert geom is not None
        assert isinstance(geom, ShoulderReliefCSGGeometry)

        notch = geom.receiving_timber_notch_negative_CSG
        assert isinstance(notch, ConvexPolygonSimpleLoft)
        loft = notch

        # Tenon is 4x4 (half-width 2); the loft flares uniformly since every face meets
        # the shoulder plane perpendicular, so all 4 corners sit at the same radius.
        for point in loft.bottom_points:
            assert abs(float(point[0])) == pytest.approx(2.0)
            assert abs(float(point[1])) == pytest.approx(2.0)

        # Just past the tenon's own corner, mid-depth into the flare: inside the notch.
        flare_point = loft.transform.local_to_global(Matrix([scalar(3), scalar(3), loft.end_distance / scalar(2)]))
        assert notch.contains_point(flare_point)

        # Dead center of the tenon's own straight core: contained too (the notch is now the
        # raw loft, covering its whole cross-section from centerline outward, not just the
        # beyond-perfect shell -- the actual mortise hole is a separate, unioned prism).
        core_point = loft.transform.local_to_global(Matrix([scalar(0), scalar(0), loft.end_distance / scalar(2)]))
        assert notch.contains_point(core_point)

        # Well outside the loft entirely.
        outside_point = loft.transform.local_to_global(Matrix([scalar(20), scalar(20), loft.end_distance / scalar(2)]))
        assert not notch.contains_point(outside_point)

    def test_raking_joint_relieves_faces_independently(self):
        """
        A tenon raking along the mortise's own run (not just tilting sideways) meets its
        RIGHT/LEFT faces square-on (90 degrees, negated width_dir dotted with n_depth is 0
        either way -- unaffected by sign) but its FRONT/BACK faces at genuinely different
        SIGNED angles to the shoulder plane (negated height_dir generally gives a
        supplementary, not equal, signed dihedral) -- so unlike RIGHT/LEFT, which flare out
        identically on both sides, FRONT and BACK must flare out by DIFFERENT amounts.
        """
        mortise = create_timber(
            length=scalar(100), size=create_v2(scalar(6), scalar(6)),
            bottom_position=create_v3(-scalar(50), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="mortise",
        )
        raking_length_dir = safe_normalize_vector(create_v3(scalar(2), -scalar(3), scalar(0)))
        tenon = create_timber(
            length=scalar(50), size=create_v2(scalar(4), scalar(4)),
            bottom_position=create_v3(scalar(20), scalar(30), scalar(0)),
            length_direction=raking_length_dir,
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="raking_tenon",
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise, butt_timber=tenon, butt_timber_end=TimberEnd.BOTTOM,
        )

        geom = chop_butt_joint_shoulder_notch_relief_4sided(arrangement, scalar(1))
        assert geom is not None
        notch = geom.receiving_timber_notch_negative_CSG
        assert isinstance(notch, ConvexPolygonSimpleLoft)
        loft = notch

        bottom_half_width = float(loft.bottom_points[0][0])
        bottom_half_height = float(loft.bottom_points[0][1])

        # Bottom (at the shoulder) is the tenon's own perfect cross-section, unaffected by
        # the rake in one axis (width, perpendicular to the rake) but stretched in the other
        # (height, the oblique slice direction).
        assert bottom_half_width == pytest.approx(2.0)
        assert bottom_half_height > 2.0

        # RIGHT/LEFT (width axis, points 0/1 vs 2/3) flare out identically on both sides --
        # width_dir is exactly perpendicular to n_depth here, so the sign flip between the
        # two faces' normals doesn't change their (already zero) dot product with n_depth.
        top_half_width_right = float(loft.top_points[0][0])
        top_half_width_left = -float(loft.top_points[1][0])
        assert top_half_width_right == pytest.approx(top_half_width_left)
        assert top_half_width_right > bottom_half_width

        # FRONT/BACK (height axis) flare out by DIFFERENT amounts -- the whole point of
        # computing each wall's own SIGNED dihedral independently instead of a single
        # Abs-based value shared by both.
        top_half_height_front = float(loft.top_points[0][1])
        top_half_height_back = -float(loft.top_points[2][1])
        assert top_half_height_front > bottom_half_height
        assert top_half_height_back > bottom_half_height
        assert top_half_height_front != pytest.approx(top_half_height_back, rel=0.05)

    def test_raking_joint_produces_watertight_notch_and_correct_relief_containment(self):
        """
        Sanity-check the receiving timber's notch mesh, and the butting timber's relief
        CSG's exact containment logic, on an imperfect, raking tenon.

        The butting-timber relief CSG is built from plain (unbounded, cross-section-agnostic)
        half-spaces, so meshing IT ALONE would render as a huge box (nothing here bounds its
        footprint -- see the comment in chop_butt_joint_shoulder_notch_relief_4sided). It's
        only meaningful once intersected with the butt timber's own real solid body, which
        happens naturally wherever it's applied as a Cutting -- checked below via
        contains_point on the raw relief CSG (exact, symbolic, no meshing involved), AND via
        meshing the FULLY APPLIED cut (butt timber's actual body with the cut applied),
        which is properly bounded and should be watertight.
        """
        from dataclasses import replace as dataclasses_replace

        from kumiki.triangles import triangulate_cutcsg

        mortise = create_timber(
            length=scalar(100), size=create_v2(scalar(6), scalar(6)),
            bottom_position=create_v3(-scalar(50), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="mortise",
        )
        raking_length_dir = safe_normalize_vector(create_v3(scalar(2), -scalar(3), scalar(0)))
        tenon = create_timber(
            length=scalar(50), size=create_v2(scalar(4), scalar(4)),
            bottom_position=create_v3(scalar(20), scalar(30), scalar(0)),
            length_direction=raking_length_dir,
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="raking_tenon",
        )
        imperfect_tenon = dataclasses_replace(
            tenon, rough_half_sizes=(create_v2(scalar(3), scalar(3)), create_v2(scalar(3), scalar(3)))
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise, butt_timber=imperfect_tenon, butt_timber_end=TimberEnd.BOTTOM,
        )

        geom = chop_butt_joint_shoulder_notch_relief_4sided(arrangement, scalar(1))
        assert geom is not None
        relief_csg = geom.butting_timber_relief_negative_CSG
        assert relief_csg is not None

        notch_mesh = triangulate_cutcsg(geom.receiving_timber_notch_negative_CSG).mesh
        assert notch_mesh.is_watertight
        assert notch_mesh.volume > 0

        # Genuinely past the loft's own far end (shoulder ~= 37.26, loft depth ~= 10.82,
        # so the loft's far cap sits at ~= 48.07 in tenon-local Z; tenon length is 50),
        # deep in the tenon's own bulk: never touched.
        far_point_local = Matrix([scalar(0), scalar(0), scalar(49)])
        assert not relief_csg.contains_point(far_point_local)

        # Near the shoulder collar (behind the shoulder, where the dedicated tongue cut
        # lives): also not this function's concern.
        collar_point_local = Matrix([scalar(0), scalar(0), scalar(1, 2)])
        assert not relief_csg.contains_point(collar_point_local)

        # The FULLY APPLIED cut (imperfect_tenon's actual body with this relief unioned into
        # its shoulder cut, via cut_mortise_and_tenon_joint) must be properly bounded and
        # watertight -- confirming the unbounded standalone relief CSG above resolves
        # correctly once combined with the real timber body.
        joint = cut_mortise_and_tenon_joint(
            arrangement=arrangement,
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_length=scalar(3),
            mortise_depth=scalar(2),
            mortise_shoulder_distance_from_centerline_or_centerplane=scalar(1),
            relief=ButtJointNotchReliefConfig(),
        )
        tenon_cutting = joint.cuttings["raking_tenon"]
        cut_timber = CutTimber(timber=imperfect_tenon, cuts=[tenon_cutting])
        applied_mesh = triangulate_cutcsg(cut_timber.render_timber_with_cuts_csg_local()).mesh
        assert applied_mesh.is_watertight
        assert applied_mesh.volume > 0
        # Bounded to the timber's own real extent (length 50, rough half-size 3) -- not the
        # ~10000-unit fake-infinite half-space box the standalone relief CSG would show.
        assert applied_mesh.bounds[1][2] <= 51  # max Z comfortably within timber length


class TestChopButtJointShoulderNotchReliefOnPlaneAlignedTimbers2Sided:
    """
    Tests for chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided.

    Setup mirrors the 4-sided tests: mortise is 6x6 running along global X (its own
    cross-section spans Y and Z, centered at the origin); tenon (4x4, perfect) rises along
    global Z from the origin. This arrangement is plane-aligned (tenon's FRONT/BACK faces,
    normal +-Y, are parallel to the mortise's RIGHT/LEFT faces, also normal +-Y) with joint
    normal axis P = (0,-1,0) (Y) and flared axis Q = tenon's width axis (X).
    """

    def test_returns_none_for_flush_shoulder(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )
        assert chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(3)) is None

    def test_raises_for_non_plane_aligned_arrangement(self):
        non_plane_mortise = create_timber(
            length=scalar(100), size=create_v2(scalar(6), scalar(6)),
            bottom_position=create_v3(-scalar(50), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="non_plane_mortise",
        )
        non_plane_tenon = create_timber(
            length=scalar(100), size=create_v2(scalar(4), scalar(4)),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            width_direction=safe_normalize_vector(create_v3(scalar(1), scalar(0), scalar(1))),
            ticket="non_plane_tenon",
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=non_plane_mortise, butt_timber=non_plane_tenon, butt_timber_end=TimberEnd.BOTTOM,
        )
        with pytest.raises(AssertionError):
            chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(1))

    def test_p_axis_is_flat_across_full_depth_at_receiving_timbers_own_edge(self, simple_T_configuration):
        """
        The P-axis (joint normal axis, Y here) walls must be FLAT (constant extent) across
        the notch's ENTIRE depth, sitting at the receiving timber's own rough half-size (3,
        for the 6x6 mortise) -- not flared/tapered like the 4-sided version's walls, and not
        confined to the (smaller) 4x4 tenon's own footprint.
        """
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )
        geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(2))
        assert geom is not None
        loft = geom.receiving_timber_notch_negative_CSG
        assert isinstance(loft, ConvexPolygonSimpleLoft)

        for points in (loft.bottom_points, loft.top_points):
            for point in points:
                assert abs(float(point[0])) == pytest.approx(3.0)

    def test_q_axis_flares_like_4sided_from_perfect_tenon_size(self, simple_T_configuration):
        """The Q-axis (flared) walls behave like the 4-sided version: quad-1 sits at the
        butt timber's own PERFECT half-size, quad-2 flares outward."""
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )
        geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(2))
        assert geom is not None
        loft = geom.receiving_timber_notch_negative_CSG
        assert isinstance(loft, ConvexPolygonSimpleLoft)

        for point in loft.bottom_points:
            assert abs(float(point[1])) == pytest.approx(2.0)  # tenon's own perfect half-width
        for point in loft.top_points:
            assert abs(float(point[1])) > 2.0

    def test_q_axis_quad1_uses_ptw_at_shoulder_not_raw_half_size_for_raking_tenon(self):
        """
        For a raking (but still plane-aligned) tenon -- e.g. a 45-degree brace -- quad-1's
        Q-extent must be the tenon's PTW cross-section footprint where it actually crosses
        the shoulder plane, not the tenon's raw (un-stretched) half-size. Mirrors the
        4-sided version's equivalent per-corner shoulder-plane intersection.
        """
        mortise_timber = create_timber(
            length=scalar(100), size=create_v2(scalar(6), scalar(6)),
            bottom_position=create_v3(-scalar(50), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="mortise_timber",
        )
        raking_dir = safe_normalize_vector(create_v3(scalar(1), scalar(0), scalar(1)))
        tenon_timber = create_timber(
            length=scalar(40), size=create_v2(scalar(4), scalar(4)),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length_direction=raking_dir,
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="tenon_timber",
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )
        geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(1))
        assert geom is not None
        loft = geom.receiving_timber_notch_negative_CSG
        assert isinstance(loft, ConvexPolygonSimpleLoft)

        # Tenon's raw PTW half-size (perpendicular to the rake) is 2; raking 45 degrees in
        # the (Q, n_depth) plane stretches the shoulder-plane footprint by 1/cos(45) = sqrt(2).
        for point in loft.bottom_points:
            assert abs(float(point[1])) == pytest.approx(2.0 * (2 ** 0.5))

    def test_notch_extends_toward_tenon_not_backward_into_solid_mortise(self, simple_T_configuration):
        """Same direction regression guard as the 4-sided version's equivalent test."""
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )
        geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(2))
        assert geom is not None
        from kumiki.cutcsg import adopt_csg
        notch_global = adopt_csg(mortise_timber.transform, Transform.identity(), geom.receiving_timber_notch_negative_CSG)

        # Shoulder at global Z=2 (toward tenon), entry face at Z=3.
        forward_point = Matrix([scalar(0), scalar(0), scalar(35, 10)])   # Z=3.5: toward tenon
        backward_point = Matrix([scalar(0), scalar(0), scalar(5, 10)])   # Z=0.5: mirrored, into solid mortise
        assert notch_global.contains_point(forward_point)
        assert not notch_global.contains_point(backward_point)

    def test_p_boundary_is_the_further_of_either_timbers_rough_size_per_side(self, simple_T_configuration):
        """
        The flat P-axis walls must reach out to whichever is FURTHER, independently per
        side, between the RECEIVING timber's own rough edge and the BUTT timber's own rough
        edge on that axis -- guaranteeing a full transverse relief across the receiving
        timber's entire width, not a pocket sized to only one of the two timbers. Uses
        asymmetric rough sizes on both timbers, arranged so each side of the notch is won by
        a DIFFERENT timber, to confirm both are actually compared (not just one hard-coded).
        """
        tenon_timber, mortise_timber = simple_T_configuration
        # P axis here is the tenon's HEIGHT axis / the mortise's WIDTH axis (see class
        # docstring), with the timbers' respective +axis directions pointing OPPOSITE ways
        # along global Y (mortise +width = LEFT = -Y-ish; tenon +height = FRONT = +Y-ish) --
        # verified directly against the resulting loft below rather than assumed.
        imperfect_mortise = replace(
            mortise_timber,
            rough_half_sizes=(create_v2(scalar(5), scalar(2)), create_v2(scalar(3), scalar(3))),
        )
        imperfect_tenon = replace(
            tenon_timber,
            rough_half_sizes=(create_v2(scalar(2), scalar(2)), create_v2(scalar(3), scalar(6))),
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=imperfect_mortise, butt_timber=imperfect_tenon, butt_timber_end=TimberEnd.BOTTOM,
        )
        geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(2))
        assert geom is not None
        loft = geom.receiving_timber_notch_negative_CSG
        assert isinstance(loft, ConvexPolygonSimpleLoft)

        # One side: mortise's rough edge (5) beats the tenon's (3) -> boundary = 5.
        # Other side: tenon's rough edge (6) beats the mortise's (2) -> boundary = 6.
        p_values = sorted({round(abs(float(point[0])), 6) for point in loft.bottom_points})
        assert p_values == [5.0, 6.0]
        p_values_top = sorted({round(abs(float(point[0])), 6) for point in loft.top_points})
        assert p_values_top == [5.0, 6.0]  # flat: identical at the far end too

    def test_notch_angle_floors_depth_without_changing_reach(self, simple_T_configuration):
        """A larger notch_angle floors the wall's own relief angle away from its natural
        (shallowest-possible) bisector -- since reach = depth * tan(angle/2) is fixed at the
        target clearance, a steeper floored angle needs LESS depth to reach that same
        clearance, never more. tan(angle/2) only ever increases from its natural minimum
        (never decreases), so depth only ever decreases (or stays the same, once the floor
        is below the natural angle)."""
        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=tenon_timber, butt_timber_end=TimberEnd.BOTTOM,
        )
        from sympy import pi as _pi

        geom_default = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(2))
        geom_angled = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(
            arrangement, scalar(2), notch_angle=degrees(60),
        )
        geom_tiny_angle = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(
            arrangement, scalar(2), notch_angle=degrees(1),
        )
        assert geom_default is not None and geom_angled is not None and geom_tiny_angle is not None
        loft_default = geom_default.receiving_timber_notch_negative_CSG
        loft_angled = geom_angled.receiving_timber_notch_negative_CSG
        loft_tiny_angle = geom_tiny_angle.receiving_timber_notch_negative_CSG
        assert isinstance(loft_default, ConvexPolygonSimpleLoft)
        assert isinstance(loft_angled, ConvexPolygonSimpleLoft)
        assert isinstance(loft_tiny_angle, ConvexPolygonSimpleLoft)

        default_depth = float(loft_default.end_distance)
        angled_depth = float(loft_angled.end_distance)
        tiny_angle_depth = float(loft_tiny_angle.end_distance)

        assert angled_depth < default_depth
        assert tiny_angle_depth == pytest.approx(default_depth)  # floor (below natural), not override

        # Reach (top_points) must be unaffected by the angle either way.
        assert loft_default.top_points == loft_angled.top_points

    def test_produces_watertight_geometry_for_imperfect_tenon(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        imperfect_tenon = replace(
            tenon_timber,
            rough_half_sizes=(create_v2(scalar(3), scalar(3)), create_v2(scalar(3), scalar(3))),
        )
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber, butt_timber=imperfect_tenon, butt_timber_end=TimberEnd.BOTTOM,
        )
        geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, scalar(2))
        assert geom is not None

        from kumiki.cutcsg import adopt_csg
        from kumiki.triangles import triangulate_cutcsg
        notch_global = adopt_csg(mortise_timber.transform, Transform.identity(), geom.receiving_timber_notch_negative_CSG)
        notch_mesh = triangulate_cutcsg(notch_global).mesh
        assert notch_mesh.is_watertight
        assert notch_mesh.volume > 0

        relief_csg = geom.butting_timber_relief_negative_CSG
        assert relief_csg is not None
        far_point_local = Matrix([scalar(0), scalar(0), scalar(90)])
        assert not relief_csg.contains_point(far_point_local)
        collar_point_local = Matrix([scalar(0), scalar(0), scalar(1)])
        assert not relief_csg.contains_point(collar_point_local)


class TestChopShoulderNotchAlignedWithTimber:
    """
    Geometry tests for chop_shoulder_notch_aligned_with_timber on the
    canonical butt arrangement (4"x5" timbers crossing at the origin,
    receiving along +X, butt along +Y, widths along +Z), with the butt
    timber optionally raked 45 degrees about its own local axes. The
    shoulder sits 2" from the receiving centerline (a 1/2" inset on the
    entry face).

    Expected notch widths were independently verified by brute-force
    slicing of the oblique butt prism's corner edge-lines with the
    shoulder plane.
    """

    DISTANCE_FROM_CENTERLINE = inches(2)

    @staticmethod
    def _rotate_about_midpoint(timber, angle, local_axis):
        pivot_local = create_v3(scalar(0), scalar(0), timber.length / scalar(2))
        pivot_global = timber.transform.position + timber.transform.orientation.matrix * pivot_local
        new_orientation = timber.transform.orientation * Orientation.from_angle_axis(angle, local_axis)
        new_bottom = pivot_global - new_orientation.matrix * pivot_local
        return replace(timber, transform=Transform(position=new_bottom, orientation=new_orientation))

    def _make_notch(self, rotate_width_axis: bool, rotate_height_axis: bool):
        arrangement = create_canonical_example_butt_joint_timbers(
            create_v3(scalar(0), scalar(0), scalar(0))
        )
        butt_timber = arrangement.butt_timber
        if rotate_width_axis:
            butt_timber = self._rotate_about_midpoint(
                butt_timber, degrees(45), create_v3(scalar(1), scalar(0), scalar(0))
            )
        if rotate_height_axis:
            butt_timber = self._rotate_about_midpoint(
                butt_timber, degrees(45), create_v3(scalar(0), scalar(1), scalar(0))
            )
        return chop_shoulder_notch_aligned_with_timber(
            notch_timber=arrangement.receiving_timber,
            butting_timber=butt_timber,
            butting_timber_end=arrangement.butt_timber_end,
            distance_from_centerline=self.DISTANCE_FROM_CENTERLINE,
        )

    @staticmethod
    def _base_prism(notch):
        from kumiki.cutcsg import SolidUnion

        return notch.children[0] if isinstance(notch, SolidUnion) else notch

    def test_perpendicular_notch_dimensions(self):
        """
        Perpendicular approach: width hugs the butt's 5" dimension exactly
        (the 5" height axis lies along the receiving's length), the span and
        depth clear the receiving's worst-case corner radius r = sqrt(2^2 +
        2.5^2), and no wall relief prisms appear (zero rake).
        """
        from kumiki.cutcsg import RectangularPrism

        notch = self._make_notch(False, False)
        assert isinstance(notch, RectangularPrism)

        corner_radius = float(inches(1)) * (2**2 + 2.5**2) ** 0.5
        assert float(notch.size[0]) == pytest.approx(float(inches(5)), rel=1e-9)
        assert float(notch.size[1]) == pytest.approx(2 * corner_radius, rel=1e-9)
        assert float(notch.end_distance) == pytest.approx(
            2 * corner_radius - float(self.DISTANCE_FROM_CENTERLINE), rel=1e-9
        )

    def test_width_axis_rake_stretches_width_and_adds_walls(self):
        """
        45-degree in-plane rake: the shoulder-plane slice of the butt prism
        stretches the 5" dimension by sec(45) = sqrt(2), and wall relief
        prisms appear automatically (floored at the rake angle) even though
        no wall angle was requested.
        """
        from kumiki.cutcsg import SolidUnion

        notch = self._make_notch(True, False)
        assert isinstance(notch, SolidUnion)
        assert len(notch.children) == 3
        assert float(self._base_prism(notch).size[0]) == pytest.approx(
            float(inches(5)) * 2**0.5, rel=1e-9
        )

    def test_height_axis_rake_reorients_shoulder_without_stretch(self):
        """
        45-degree out-of-plane tip: the shoulder plane reorients to face the
        butt square-on, so the slice is NOT stretched (width stays 5") and no
        wall relief is needed (the butt is perpendicular to ITS shoulder plane).
        """
        from kumiki.cutcsg import RectangularPrism

        notch = self._make_notch(False, True)
        assert isinstance(notch, RectangularPrism)
        assert float(notch.size[0]) == pytest.approx(float(inches(5)), rel=1e-9)

    def test_compound_rake_width_matches_brute_force(self):
        """
        Compound 45+45 rake: the slice direction shifts inside the butt's
        cross-section AND stretches; expected width 0.187470m (7.3807") was
        computed by brute-force corner-edge slicing.
        """
        from kumiki.cutcsg import SolidUnion

        notch = self._make_notch(True, True)
        assert isinstance(notch, SolidUnion)
        assert float(self._base_prism(notch).size[0]) == pytest.approx(0.187470, rel=1e-4)


class TestChopScribeRelief:
    def test_returns_pair_in_cut_timber_local_space(self):
        timber_to_be_cut = create_standard_vertical_timber(
            height=scalar(20),
            size=(scalar(4), scalar(6)),
            position=(scalar(0), scalar(0), scalar(0)),
            ticket="timber_to_be_cut",
        )
        timber_to_be_scribed = replace(
            create_timber(
                length=scalar(20),
                size=create_v2(scalar(4), scalar(4)),
                bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
                length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
                width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
                ticket="timber_to_be_scribed",
            ),
            rough_half_sizes=(
                create_v2(scalar(3), scalar(3)),
                create_v2(scalar(4), scalar(4)),
            ),
        )

        scribed_overlap_csg_local, scribe_relief_csg_local = chop_scribe_relief(
            timber_to_be_scribed_cutting=Cutting(timber=timber_to_be_scribed),
            timber_to_be_cut_cutting=Cutting(timber=timber_to_be_cut),
        )

        assert isinstance(scribed_overlap_csg_local, Intersection)
        assert isinstance(scribe_relief_csg_local, Difference)
        assert scribed_overlap_csg_local.contains_point(create_v3(scalar(1), scalar(5, 2), scalar(10)))
        assert scribe_relief_csg_local.contains_point(create_v3(scalar(5, 2), scalar(0), scalar(10)))


class TestMultiTimberScribeReliefConfig:
    def test_double_butt_uses_with_order(self):
        config = DoubleButtJointScribeReliefConfig.with_order(
            ArrangementNames.butt_timber_1,
            ArrangementNames.butt_timber_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.butt_timber_2

    def test_triple_butt_uses_with_order(self):
        config = TripleButtJointScribeReliefConfig.with_order(
            ArrangementNames.main_butt_timber_1,
            ArrangementNames.main_butt_timber_2,
            ArrangementNames.awk_timber,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.main_butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.main_butt_timber_2
        assert config.third_timber_to_be_scribed == ArrangementNames.awk_timber

    def test_quadruple_butt_uses_with_order(self):
        config = QuadrupleButtJointScribeReliefConfig.with_order(
            ArrangementNames.main_butt_timber_1,
            ArrangementNames.main_butt_timber_2,
            ArrangementNames.awk_1,
            ArrangementNames.awk_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.main_butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.main_butt_timber_2
        assert config.third_timber_to_be_scribed == ArrangementNames.awk_1
        assert config.fourth_timber_to_be_scribed == ArrangementNames.awk_2

    def test_cross_cap_uses_with_order(self):
        config = CrossCapJointScribeReliefConfig.with_order(
            ArrangementNames.cross_timber_1,
            ArrangementNames.cross_timber_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.cross_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.cross_timber_2

    def test_brace_uses_with_order(self):
        config = BraceJointScribeReliefConfig.with_order(
            ArrangementNames.timber1,
            ArrangementNames.brace_timber,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.timber1
        assert config.second_timber_to_be_scribed == ArrangementNames.brace_timber
