"""Tests for where a feature actually is (kumiki/csgconvexhull.py).

The declared extent of a feature is the extent of the primitive it was declared
on, and primitives are deliberately not the finished piece. These pin the
cropping that turns one into the other.
"""

import pytest

from kumiki.cutcsg import HalfSpace, RectangularPrism
from kumiki.geometry import Line, Plane
from kumiki.csgconvexhull import (
    FeatureRegion,
    FeatureSegment,
    bounding_half_spaces,
    convex_hull_2d,
    frame_for_plane,
    region_in_plane,
    segment_on_line,
)
from kumiki.rule import Matrix, Transform, create_v2, create_v3, mm, scalar


def _v(x, y, z):
    return create_v3(scalar(x), scalar(y), scalar(z))


def _box(size=(0.1, 0.2), start=0.0, end=1.0, position=(0.0, 0.0, 0.0)):
    return RectangularPrism(
        size=create_v2(scalar(size[0]), scalar(size[1])),
        transform=Transform(position=_v(*position), orientation=Transform.identity().orientation),
        start_distance=None if start is None else scalar(start),
        end_distance=None if end is None else scalar(end),
    )


def _dot(a, b):
    return float((a.T * b)[0, 0])


class TestPlaneFrame:
    def test_the_axes_are_perpendicular_to_the_normal_and_each_other(self):
        for normal in (_v(0, 0, 1), _v(1, 0, 0), _v(0.3, -0.5, 0.81)):
            frame = frame_for_plane(Plane(normal=normal, point=_v(0, 0, 0)))

            assert _dot(frame.u, normal) == pytest.approx(0, abs=1e-9)
            assert _dot(frame.v, normal) == pytest.approx(0, abs=1e-9)
            assert _dot(frame.u, frame.v) == pytest.approx(0, abs=1e-9)

    def test_a_point_survives_the_round_trip(self):
        frame = frame_for_plane(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 5)))

        assert frame.to_2d(frame.to_3d(2.0, -3.0)) == pytest.approx((2.0, -3.0), abs=1e-9)

    def test_the_origin_can_be_put_near_something(self):
        # A plane's own point may be nowhere near the material: an extended
        # cutter's face plane holds a point out where the cutter ends. Starting
        # there and clipping to the timber leaves nothing.
        far = Plane(normal=_v(0, 0, 1), point=_v(0, 500, 0))

        frame = frame_for_plane(far, near=_v(0, 0, 0))

        assert frame.to_2d(_v(0, 0, 0)) == pytest.approx((0.0, 0.0), abs=1e-9)


class TestBoundingHalfSpaces:
    def test_a_half_space_bounds_with_one_plane(self):
        faces = bounding_half_spaces(HalfSpace(normal=_v(0, 0, 1), offset=scalar(2)))

        assert len(faces) == 1
        normal, point = faces[0]
        # Outward, so away from the material it keeps.
        assert _dot(normal, _v(0, 0, 1)) == pytest.approx(-1, abs=1e-9)
        assert float(point[2, 0]) == pytest.approx(2, abs=1e-9)

    def test_a_closed_prism_bounds_with_six(self):
        assert len(bounding_half_spaces(_box())) == 6

    def test_an_end_that_runs_to_infinity_bounds_nothing(self):
        # The case that started all of this: a cutter extended so the cut comes
        # out clean has no face out there to bound anything.
        assert len(bounding_half_spaces(_box(start=None))) == 5
        assert len(bounding_half_spaces(_box(start=None, end=None))) == 4

    def test_a_shape_it_cannot_describe_says_so(self):
        # None rather than an empty list: "does not bound" and "cannot say"
        # are different answers, and only the second should stop a caller.
        from kumiki.cutcsg import EmptyCSG

        assert bounding_half_spaces(EmptyCSG()) is None


class TestRegionInPlane:
    def test_a_plane_through_a_box_is_the_box_cross_section(self):
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5))

        region = region_in_plane(plane, [box], seed_reach=10, near=_v(0, 0, 0))

        assert len(region.boundary) == 4
        width = region.extent_along(_v(1, 0, 0))
        height = region.extent_along(_v(0, 1, 0))
        assert width[1] - width[0] == pytest.approx(0.1, abs=1e-9)
        assert height[1] - height[0] == pytest.approx(0.2, abs=1e-9)

    def test_an_unbounded_solid_is_cropped_by_a_bounded_one(self):
        # The whole point: a half space has no extent of its own, and gets one
        # from whatever encloses it.
        timber = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5))

        region = region_in_plane(plane, [HalfSpace(normal=_v(0, 0, 1), offset=scalar(0)), timber],
                                 seed_reach=10, near=_v(0, 0, 0))

        assert len(region.boundary) == 4
        assert region.extent_along(_v(1, 0, 0))[1] == pytest.approx(0.05, abs=1e-9)

    def test_a_plane_that_misses_everything_leaves_nothing(self):
        # Which is how a feature says it is not on the finished piece at all.
        box = _box(start=0.0, end=1.0)
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 5))

        region = region_in_plane(plane, [box], seed_reach=20, near=_v(0, 0, 5))

        assert region.is_empty

    def test_it_gives_up_rather_than_returning_too_much(self):
        # A region clipped by only the solids it understood would be silently
        # larger than the truth, which is worse than no answer.
        from kumiki.cutcsg import EmptyCSG

        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        assert region_in_plane(plane, [_box(), EmptyCSG()], seed_reach=10, near=_v(0, 0, 0)) is None

    def test_the_centroid_lies_in_the_plane(self):
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.25))

        centre = region_in_plane(plane, [box], seed_reach=10, near=_v(0, 0, 0)).centroid()

        assert float(centre[2, 0]) == pytest.approx(0.25, abs=1e-9)

    def test_extent_along_answers_for_any_direction(self):
        # What makes orienting the region to a viewport unnecessary: ask along
        # the viewport's own axes and the answer is the bounds in that view.
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        region = region_in_plane(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5)),
                                 [box], seed_reach=10, near=_v(0, 0, 0))

        diagonal = _v(0.7071, 0.7071, 0)
        along = region.extent_along(diagonal)
        assert along[1] > along[0]

    def test_an_empty_region_has_no_centroid_to_offer(self):
        assert FeatureRegion(plane=Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0)),
                             boundary=()).centroid() is None


class TestLoftedSolids:
    """A loft's sides are planar only when the taper is a pure per-axis scale."""

    def _square(self, half):
        return [create_v2(scalar(-half), scalar(-half)), create_v2(scalar(half), scalar(-half)),
                create_v2(scalar(half), scalar(half)), create_v2(scalar(-half), scalar(half))]

    def _turned(self, half, degrees):
        import math

        angle = math.radians(degrees)
        corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
        return [
            create_v2(scalar(x * math.cos(angle) - y * math.sin(angle)),
                      scalar(x * math.sin(angle) + y * math.cos(angle)))
            for x, y in corners
        ]

    def _loft(self, bottom, top):
        from kumiki.cutcsg import ConvexPolygonSimpleLoft

        return ConvexPolygonSimpleLoft(
            bottom_points=bottom, top_points=top,
            transform=Transform(position=_v(0, 0, 0),
                                orientation=Transform.identity().orientation),
            start_distance=scalar(0), end_distance=scalar(1),
        )

    def test_a_taper_is_bounded_by_four_sides_and_two_ends(self):
        assert len(bounding_half_spaces(self._loft(self._square(0.1), self._square(0.05)))) == 6

    def test_a_twisted_loft_is_bounded_loosely_rather_than_refused(self):
        # Its sides are ruled surfaces with no plane of their own, so each
        # plane is pushed out to the furthest corner. That bounds the corners'
        # hull, which contains the loft -- loose, but the right direction.
        twisted = self._loft(self._square(0.1), self._turned(0.1, 30))

        faces = bounding_half_spaces(twisted)

        assert faces is not None and len(faces) == 6
        # Every corner of both profiles inside every face.
        for normal, point in faces:
            for height, profile in ((0.0, twisted.bottom_points), (1.0, twisted.top_points)):
                for corner in profile:
                    at = _v(float(corner[0]), float(corner[1]), height)
                    assert float(((at - point).T * normal)[0, 0]) <= 1e-9

    def test_the_section_narrows_the_way_the_taper_does(self):
        taper = self._loft(self._square(0.1), self._square(0.05))

        for height, width in ((0.0, 0.2), (0.5, 0.15), (1.0, 0.1)):
            region = region_in_plane(
                Plane(normal=_v(0, 0, 1), point=_v(0, 0, height)),
                [taper], seed_reach=10, near=_v(0, 0, 0))
            low, high = region.extent_along(_v(1, 0, 0))
            assert high - low == pytest.approx(width, abs=1e-9), height


class TestSegmentOnLine:
    """An edge, cropped the same way a face is."""

    def test_a_line_through_a_box_is_the_box_thickness(self):
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        segment = segment_on_line(line, [box], seed_reach=10, near=_v(0, 0, 0))

        low, high = segment.extent_along(_v(0, 0, 1))
        assert low == pytest.approx(0.0, abs=1e-9)
        assert high == pytest.approx(1.0, abs=1e-9)

    def test_the_midpoint_is_the_middle_of_what_survives(self):
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        middle = segment_on_line(line, [box], seed_reach=10, near=_v(0, 0, 0)).midpoint()

        assert float(middle[2, 0]) == pytest.approx(0.5, abs=1e-9)

    def test_an_edge_declared_far_away_still_crops_to_the_timber(self):
        # The whole point, and the same failure a face had: an edge declared on
        # a cutter extended past the timber has its own point out there with the
        # cutter. Starting from that point and clipping leaves nothing.
        timber = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        far = Line(direction=_v(0, 0, 1), point=_v(0.05, 0.1, 900))

        segment = segment_on_line(far, [timber], seed_reach=10, near=_v(0, 0, 0.5))

        assert not segment.is_empty
        assert float(segment.midpoint()[2, 0]) == pytest.approx(0.5, abs=1e-6)

    def test_an_unbounded_solid_is_cropped_by_a_bounded_one(self):
        timber = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        segment = segment_on_line(
            line, [HalfSpace(normal=_v(0, 0, 1), offset=scalar(0.25)), timber],
            seed_reach=10, near=_v(0, 0, 0))

        low, high = segment.extent_along(_v(0, 0, 1))
        assert low == pytest.approx(0.25, abs=1e-9)
        assert high == pytest.approx(1.0, abs=1e-9)

    def test_a_line_that_misses_everything_leaves_nothing(self):
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        line = Line(direction=_v(0, 0, 1), point=_v(5, 5, 0))

        assert segment_on_line(line, [box], seed_reach=10, near=_v(0, 0, 0)).is_empty

    def test_a_line_running_along_a_face_it_is_outside_of_keeps_nothing(self):
        # Parallel to every bounding plane it is outside: no bound to compute,
        # so the parallel case has to answer rather than skip.
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        line = Line(direction=_v(0, 0, 1), point=_v(5, 0, 0))

        assert segment_on_line(line, [box], seed_reach=10, near=_v(0, 0, 0.5)).is_empty

    def test_it_gives_up_rather_than_returning_too_much(self):
        from kumiki.cutcsg import EmptyCSG

        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        assert segment_on_line(line, [_box(), EmptyCSG()], seed_reach=10, near=_v(0, 0, 0)) is None

    def test_an_empty_segment_has_no_midpoint_to_offer(self):
        assert FeatureSegment(line=Line(direction=_v(0, 0, 1), point=_v(0, 0, 0)),
                              ends=()).midpoint() is None


class TestConvexHull:
    def test_it_drops_a_point_inside_the_outline(self):
        hull = convex_hull_2d([(0, 0), (2, 0), (2, 2), (0, 2), (1, 1)])

        assert (1, 1) not in hull
        assert len(hull) == 4

    def test_it_drops_a_point_along_an_edge(self):
        assert len(convex_hull_2d([(0, 0), (1, 0), (2, 0), (2, 2), (0, 2)])) == 4

    def test_too_few_points_to_enclose_anything(self):
        assert len(convex_hull_2d([(0, 0), (1, 1)])) == 2


class TestCurvedAndPointyPrimitives:
    """The primitives that are described by points or curves rather than planes."""

    def _cylinder(self, start=0.0, end=1.0, radius=0.05):
        from kumiki.cutcsg import Cylinder

        return Cylinder(
            axis_direction=_v(0, 0, 1), radius=scalar(radius), position=_v(0, 0, 0),
            start_distance=None if start is None else scalar(start),
            end_distance=None if end is None else scalar(end),
        )

    def test_a_cylinder_becomes_a_hexagonal_prism(self):
        assert len(bounding_half_spaces(self._cylinder())) == 8  # six sides, two ends

    def test_a_cylinder_running_to_infinity_has_no_ends(self):
        assert len(bounding_half_spaces(self._cylinder(start=None, end=None))) == 6

    def test_the_hexagon_contains_the_cylinder(self):
        # Outwards, per the rule at the top of csgconvexhull: one direction,
        # consistently, so that what a region excludes really is excluded.
        region = region_in_plane(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5)),
                                 [self._cylinder(radius=0.05)], seed_reach=10, near=_v(0, 0, 0))
        across = region.extent_along(_v(1, 0, 0))

        # Tangent faces, so it holds the diameter exactly across the flats,
        # and reaches past it at the corners -- never short of it.
        assert across[1] - across[0] >= 0.1 - 1e-9
        assert across[1] - across[0] < 0.125  # 2r/cos(30) at the widest

    def test_a_cylinder_sections_as_a_hexagon(self):
        region = region_in_plane(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5)),
                                 [self._cylinder()], seed_reach=10, near=_v(0, 0, 0))

        assert len(region.boundary) == 6

    def _extrusion(self, points, start=0.0, end=2.0):
        from kumiki.cutcsg import ConvexPolygonExtrusion

        return ConvexPolygonExtrusion(
            points=[(scalar(x), scalar(y)) for x, y in points],
            transform=Transform.identity(),
            start_distance=None if start is None else scalar(start),
            end_distance=None if end is None else scalar(end),
        )

    def test_an_extrusion_bounds_with_a_plane_per_edge_and_its_ends(self):
        square = self._extrusion([(0, 0), (1, 0), (1, 1), (0, 1)])

        assert len(bounding_half_spaces(square)) == 6

    def test_its_planes_come_from_the_hull_not_the_points_as_given(self):
        # A point inside the outline contributes no face of its own.
        with_inner = self._extrusion([(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)])

        assert len(bounding_half_spaces(with_inner)) == 6

    def test_an_extrusion_sections_to_its_cross_section(self):
        square = self._extrusion([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)])
        region = region_in_plane(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 1)),
                                 [square], seed_reach=10, near=_v(0, 0, 0))
        across = region.extent_along(_v(1, 0, 0))

        assert across[1] - across[0] == pytest.approx(1.0, abs=1e-9)


class TestSquareJointNeedsNoBackExtension:
    """A square mortise and tenon should not build a cutter hundreds of metres long."""

    def _prisms(self):
        import sys
        from pathlib import Path as _Path

        sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
        from kumiki.cutcsg import csg_children
        from kumiki.timber import Frame
        from patterns.basic_joints_patterns import example_basic_mortise_and_tenon_joint

        frame = Frame.from_joints(joints=[example_basic_mortise_and_tenon_joint()])
        found = {}

        def walk(csg):
            label = getattr(getattr(csg, "label", None), "name", None)
            if label in ("tenon", "mortise_hole"):
                found[label] = csg
            for child in csg_children(csg):
                walk(child)

        for cut_timber in frame.cut_timbers:
            for cut in cut_timber.cuts:
                if getattr(cut, "negative_csg", None) is not None:
                    walk(cut.negative_csg)
        return found

    def test_the_prisms_stay_the_size_of_the_timber(self):
        # The reach behind the shoulder is for oblique entry. A square joint
        # meets the shoulder square-on, and dividing by the guard against zero
        # gave it the largest extension possible where the least was wanted.
        for name, prism in self._prisms().items():
            assert abs(float(prism.start_distance)) < 1.0, name
            assert abs(float(prism.end_distance)) < 1.0, name


class TestObliqueJointStillBuilds:
    """The oblique path, which nothing else in the suite reaches.

    Squareness decides both the back extension and whether the lengthwise
    cropping runs, and the cropping divides by the same sine. Nothing here
    covered that until a change to the one broke the other and the whole suite
    stayed green.
    """

    def _frame(self):
        import sys
        from pathlib import Path as _Path

        sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
        from patterns.mortise_and_tenon_joints_patterns import example_brace_joint

        # A brace: oblique, and plane-aligned enough to be bored perpendicular
        # to the face, which is what turns the lengthwise cropping on.
        return example_brace_joint()

    def test_a_braced_joint_builds_and_stays_bounded(self):
        from kumiki.cutcsg import csg_children

        prisms = {}

        def walk(csg):
            label = getattr(getattr(csg, "label", None), "name", None)
            if label in ("tenon", "mortise_hole"):
                prisms[label] = csg
            for child in csg_children(csg):
                walk(child)

        frame = self._frame()
        for cut_timber in frame.cut_timbers:
            for cut in cut_timber.cuts:
                if getattr(cut, "negative_csg", None) is not None:
                    walk(cut.negative_csg)

        assert prisms, "no tenon or mortise_hole built"
        # The reach behind the shoulder is a small multiple of the tenon
        # rather than a number that ran away.
        for name, prism in prisms.items():
            assert abs(float(prism.start_distance)) < 100.0, name
            assert abs(float(prism.end_distance)) < 100.0, name
