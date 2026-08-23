"""
Tests for pathcsg.py: Path/LineSegment/ArcSegment and the PathExtrusion CutCSG
primitive, including decompose_path_into_convex_pieces.
"""

import pytest

from kumiki.rule import create_v2, create_v3, Transform, scalar, pi
from kumiki.cutcsg import ExtrusionCap
from kumiki.geometry import Plane
from kumiki.pathcsg import (
    ArcSegment, LineSegment, FancyPath, Path, PathExtrusion,
    SimplePathExtrusionFeature,
)
from kumiki.triangles import mesh_cutcsg


class TestPathCSG:

    # ------------------------------------------------------------------
    # A plain circle (two semicircular ArcSegments) -- the simplest curved,
    # convex case. Regression coverage for two real bugs found while
    # building this: the pole-search only ever walking angles *upward*
    # (silently missing poles on an entirely-negative angle range), and a
    # single ArcSegment contributing more than one crossing to the same
    # decomposition band (the old algorithm assumed at most one).
    # ------------------------------------------------------------------
    def test_circle_extrusion_contains_and_meshes_correctly(self):
        radius = scalar(1, 20)
        height = scalar(1, 10)
        center = create_v2(scalar(0), scalar(0))
        path = FancyPath(segments=[
            ArcSegment(center=center, radius=radius, start_angle=scalar(0), sweep_angle=pi),
            ArcSegment(center=center, radius=radius, start_angle=pi, sweep_angle=pi),
        ])
        assert path.is_valid()

        import math
        assert float(path.signed_area()) == pytest.approx(math.pi * float(radius) ** 2)

        extrusion = PathExtrusion(
            path=path, transform=Transform.identity(),
            start_distance=scalar(0), end_distance=height,
        )
        assert extrusion.contains_point(create_v3(scalar(0), scalar(0), height / 2))
        assert not extrusion.contains_point(create_v3(radius * 2, scalar(0), height / 2))
        on_boundary = create_v3(radius, scalar(0), height / 2)
        assert extrusion.is_point_on_boundary(on_boundary)
        normal = extrusion.get_outward_normal(on_boundary)
        assert normal is not None
        assert [float(n) for n in normal] == pytest.approx([1.0, 0.0, 0.0])

        mesh = mesh_cutcsg(extrusion).mesh
        assert mesh.is_watertight
        # Chord tessellation always slightly undershoots a true circle's area.
        expected_volume = math.pi * float(radius) ** 2 * float(height)
        assert mesh.volume == pytest.approx(expected_volume, rel=0.02)

    def test_path_alias(self):
        assert Path is FancyPath

    # ------------------------------------------------------------------
    # A square with a concave semicircular bite taken out of the top edge.
    # This is the shape the whole curved-extrusion effort is for (a
    # simplified ankle tuck): it requires a CW (negative sweep_angle) arc,
    # and it's the case that first exposed the wall/cap and cap/cap
    # T-junction bugs (a straight wall edge split by a foreign extremum, and
    # two cap pieces meeting at a pole disagreeing on the seam).
    # ------------------------------------------------------------------
    def test_concave_notch_excludes_void_and_meshes_watertight(self):
        r = scalar(1, 50)
        notch_center = create_v2(scalar(1, 20), scalar(1, 10))
        p_bl = create_v2(scalar(0), scalar(0))
        p_br = create_v2(scalar(1, 10), scalar(0))
        p_tr = create_v2(scalar(1, 10), scalar(1, 10))
        notch_start = create_v2(scalar(1, 20) + r, scalar(1, 10))
        notch_end = create_v2(scalar(1, 20) - r, scalar(1, 10))
        p_tl = create_v2(scalar(0), scalar(1, 10))
        notch_arc = ArcSegment(center=notch_center, radius=r, start_angle=scalar(0), sweep_angle=-pi)

        path = FancyPath([
            LineSegment(p_bl, p_br),
            LineSegment(p_br, p_tr),
            LineSegment(p_tr, notch_start),
            notch_arc,
            LineSegment(notch_end, p_tl),
            LineSegment(p_tl, p_bl),
        ])
        assert path.is_valid()

        import math
        expected_area = 0.1 * 0.1 - 0.5 * math.pi * float(r) ** 2
        assert float(path.signed_area()) == pytest.approx(expected_area)

        # Directly under the notch (in the bitten-out void) is NOT material...
        assert not path.contains_point_2d(create_v2(scalar(1, 20), scalar(1, 10) - r / 2))
        # ...but the rest of the square body still is.
        assert path.contains_point_2d(create_v2(scalar(1, 20), scalar(1, 50)))

        height = scalar(1, 50)
        extrusion = PathExtrusion(path=path, transform=Transform.identity(),
                                   start_distance=scalar(0), end_distance=height)
        mesh = mesh_cutcsg(extrusion).mesh
        assert mesh.is_watertight
        assert mesh.volume == pytest.approx(expected_area * float(height), rel=0.02)

    # ------------------------------------------------------------------
    # A stylized cabriole-leg-like cross-section: three arcs (a convex
    # "knee" bulge, a concave "ankle" tuck, and a convex "foot" bulge)
    # chained together with four straight lines, deliberately non-convex.
    # This is the shape decompose_path_into_convex_pieces exists for --
    # a single convex-only piece could never represent it.
    # ------------------------------------------------------------------
    def _leg_profile_path(self) -> FancyPath:
        p0 = create_v2(scalar(0), scalar(0))
        p1 = create_v2(scalar(3, 100), scalar(0))
        line_foot = LineSegment(p0, p1)

        knee = ArcSegment(center=create_v2(scalar(3, 100), scalar(5, 100)),
                           radius=scalar(5, 100), start_angle=-pi / 2, sweep_angle=pi / 2)
        ankle = ArcSegment(center=create_v2(scalar(8, 100), scalar(9, 100)),
                            radius=scalar(4, 100), start_angle=-pi / 2, sweep_angle=-pi / 2)
        foot_bulge = ArcSegment(center=create_v2(scalar(4, 100), scalar(11, 100)),
                                 radius=scalar(2, 100), start_angle=-pi / 2, sweep_angle=pi / 2)

        p5 = create_v2(scalar(2, 100), scalar(15, 100))
        p6 = create_v2(scalar(0), scalar(15, 100))
        line_shin = LineSegment(foot_bulge.end, p5)
        line_top = LineSegment(p5, p6)
        line_back = LineSegment(p6, p0)

        return FancyPath([line_foot, knee, ankle, foot_bulge, line_shin, line_top, line_back])

    def test_leg_profile_is_valid_and_non_convex(self):
        path = self._leg_profile_path()
        assert path.is_valid()

        min_corner, max_corner = path.bounds()
        bbox_area = float((max_corner[0] - min_corner[0]) * (max_corner[1] - min_corner[1]))
        area = float(path.signed_area())
        # Non-degenerate, and strictly less than its own bounding box (true
        # for any non-trivial concave-or-convex shape, just a sanity bound).
        assert 0 < area < bbox_area

        # The point at the middle of the straight chord the concave "ankle"
        # arc replaces sits outside the material -- proof the shape is
        # actually concave there, not just a rounded-corner convex blob.
        chord_mid = create_v2(scalar(6, 100), scalar(7, 100))
        assert not path.contains_point_2d(chord_mid)

        # Deep inside the "knee" bulge, and against the flat back, are both material.
        assert path.contains_point_2d(create_v2(scalar(3, 100), scalar(3, 100)))
        assert path.contains_point_2d(create_v2(scalar(1, 100), scalar(1, 10)))

        # Far outside the whole silhouette is not.
        assert not path.contains_point_2d(create_v2(scalar(15, 100), scalar(7, 100)))

    def test_leg_profile_extrusion_meshes_watertight_and_matches_analytic_area(self):
        path = self._leg_profile_path()
        height = scalar(1, 25)
        extrusion = PathExtrusion(path=path, transform=Transform.identity(),
                                   start_distance=scalar(0), end_distance=height)

        mesh = mesh_cutcsg(extrusion).mesh
        assert mesh.is_watertight
        # Cross-checks the analytic Path.signed_area() against the meshed
        # volume from an entirely different code path (decompose + tessellate
        # + trimesh) -- both must agree since the cross-section is constant.
        expected_volume = float(path.signed_area()) * float(height)
        assert mesh.volume == pytest.approx(expected_volume, rel=0.02)

    def test_leg_profile_named_features(self):
        """A named feature on a straight segment or cap resolves; one on a
        curved segment is gracefully skipped -- never raises, just absent."""
        path = self._leg_profile_path()
        extrusion = PathExtrusion(
            path=path, transform=Transform.identity(),
            start_distance=scalar(0), end_distance=scalar(1, 25),
            _features=[
                SimplePathExtrusionFeature("foot", key=0),        # line_foot: planar, should resolve
                SimplePathExtrusionFeature("knee_bulge", key=1),  # knee: curved (ArcSegment), never matches
                SimplePathExtrusionFeature("top", key=ExtrusionCap.TOP),
            ],
        )

        on_foot = create_v3(scalar(1, 100), scalar(0), scalar(1, 50))
        assert [f.name for f in extrusion.get_all_features(on_foot)] == ["foot"]

        knee_mid_local = path.segments[1].closest_point(create_v2(scalar(6, 100), scalar(2, 100)))
        on_knee = create_v3(knee_mid_local[0], knee_mid_local[1], scalar(1, 50))
        assert extrusion.get_all_features(on_knee) == []

        on_top = create_v3(scalar(1, 100), scalar(15, 100), scalar(1, 25))
        assert [f.name for f in extrusion.get_all_features(on_top)] == ["top"]


class TestPathExtrusionTolerance:
    """PathExtrusion must hand its eps all the way down.

    This is the primitive that motivated threading the tolerance explicitly
    rather than scoping it globally. PathExtrusion does almost none of its own
    comparing: containment and boundary tests delegate to FancyPath, which
    delegates to each PathSegment's ray_crossings / closest_point. A tolerance
    that stopped at PathExtrusion's own methods would be useless here -- and
    silently so, since the answer would just be "not on the boundary".
    """

    def _circle(self, radius):
        center = create_v2(scalar(0), scalar(0))
        return FancyPath(segments=[
            ArcSegment(center=center, radius=radius, start_angle=scalar(0), sweep_angle=pi),
            ArcSegment(center=center, radius=radius, start_angle=pi, sweep_angle=pi),
        ])

    def _square(self):
        a = create_v2(scalar(0), scalar(0))
        b = create_v2(scalar(1, 10), scalar(0))
        c = create_v2(scalar(1, 10), scalar(1, 10))
        d = create_v2(scalar(0), scalar(1, 10))
        return FancyPath([LineSegment(a, b), LineSegment(b, c),
                          LineSegment(c, d), LineSegment(d, a)])

    def test_eps_reaches_a_line_segment_boundary(self):
        """Through FancyPath.locate_boundary_segment into LineSegment."""
        extrusion = PathExtrusion(
            path=self._square(), transform=Transform.identity(),
            start_distance=scalar(0), end_distance=scalar(1, 10),
        )
        # A hair outside the x = 0.1 wall.
        near_miss = create_v3(scalar(1, 10) + 1e-4, scalar(5, 100), scalar(5, 100))
        assert not extrusion.is_point_on_boundary(near_miss)
        assert extrusion.is_point_on_boundary(near_miss, 5e-4)

    def test_eps_reaches_an_arc_segment_boundary(self):
        """Through FancyPath into ArcSegment.closest_point / ray_crossings."""
        radius = scalar(1, 20)
        extrusion = PathExtrusion(
            path=self._circle(radius), transform=Transform.identity(),
            start_distance=scalar(0), end_distance=scalar(1, 10),
        )
        # A hair outside the barrel, on the +x side.
        near_miss = create_v3(radius + 1e-4, scalar(0), scalar(5, 100))
        assert not extrusion.is_point_on_boundary(near_miss)
        assert extrusion.is_point_on_boundary(near_miss, 5e-4)

    def test_widened_eps_does_not_raise_on_an_arc(self):
        """Regression: ArcSegment.ray_crossings' sqrt(1 - sin^2).

        The hit gate accepts y within the comparison tolerance of a monotonic
        subrange's endpoints, so at a widened tolerance sin_theta can land
        outside [-1, 1] -- far enough to blow past rule.sqrt's own
        small-negative guard and raise "math domain error". sin_theta is
        clamped now.
        """
        radius = scalar(1, 20)
        extrusion = PathExtrusion(
            path=self._circle(radius), transform=Transform.identity(),
            start_distance=scalar(0), end_distance=scalar(1, 10),
        )
        # Level with the circle's top pole, where the subrange endpoints meet.
        at_pole = create_v3(scalar(0), radius, scalar(5, 100))
        assert extrusion.contains_point(at_pole, 5e-4) in (True, False)
        assert extrusion.is_point_on_boundary(at_pole, 5e-4)

    def test_eps_does_not_persist_into_later_calls(self):
        extrusion = PathExtrusion(
            path=self._square(), transform=Transform.identity(),
            start_distance=scalar(0), end_distance=scalar(1, 10),
        )
        near_miss = create_v3(scalar(1, 10) + 1e-4, scalar(5, 100), scalar(5, 100))
        assert extrusion.is_point_on_boundary(near_miss, 5e-4)
        assert not extrusion.is_point_on_boundary(near_miss)


class TestPathExtrusionLocate:
    """locate() on a path extrusion, where planarity depends on the segment."""

    def _square(self):
        a = create_v2(scalar(0), scalar(0))
        b = create_v2(scalar(1, 10), scalar(0))
        c = create_v2(scalar(1, 10), scalar(1, 10))
        d = create_v2(scalar(0), scalar(1, 10))
        return FancyPath([LineSegment(a, b), LineSegment(b, c),
                          LineSegment(c, d), LineSegment(d, a)])

    def _extrusion(self, path):
        return PathExtrusion(path=path, transform=Transform.identity(),
                             start_distance=scalar(0), end_distance=scalar(1, 10))

    def test_a_straight_side_locates_as_an_outward_plane(self):
        extrusion = self._extrusion(self._square())
        # segment 1 runs (0.1, 0) -> (0.1, 0.1), so it faces +X
        plane = SimplePathExtrusionFeature("east", key=1).locate(extrusion)
        assert isinstance(plane, Plane)
        assert float(plane.normal[0]) == pytest.approx(1.0)
        assert float(plane.point[0]) == pytest.approx(0.1)

    def test_a_cap_locates_along_the_extrusion_axis(self):
        extrusion = self._extrusion(self._square())
        plane = SimplePathExtrusionFeature("top", key=ExtrusionCap.TOP).locate(extrusion)
        assert isinstance(plane, Plane)
        assert float(plane.normal[2]) == pytest.approx(1.0)
        assert float(plane.point[2]) == pytest.approx(0.1)

    def test_a_curved_side_declines(self):
        """An arc wall has no plane, the same way test_point never matches it."""
        radius = scalar(1, 20)
        centre = create_v2(scalar(0), scalar(0))
        circle = FancyPath(segments=[
            ArcSegment(center=centre, radius=radius, start_angle=scalar(0), sweep_angle=pi),
            ArcSegment(center=centre, radius=radius, start_angle=pi, sweep_angle=pi),
        ])
        assert SimplePathExtrusionFeature("wall", key=0).locate(self._extrusion(circle)) is None

    def test_extent_anchors_on_the_face(self):
        extrusion = self._extrusion(self._square())
        extent = SimplePathExtrusionFeature("east", key=1).get_extent(extrusion)
        assert extent is not None
        assert float(extent.anchor[0]) == pytest.approx(0.1)
        assert float(extent.anchor[2]) == pytest.approx(0.05)
