"""A flat face's extent carries its outline -- its plane and corners in order -- rather than a box."""

import math

import pytest

from kumiki.csg.cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, ExtrusionCap, PrismFace,
                               RectangularPrism, SimpleConvexPolygonExtrusionFeature, SimpleLoftFeature,
                               SimpleRectangularPrismFeature)
from kumiki.csg.pathcsg import FancyPath, FlatSide, PathExtrusion, SimplePathExtrusionFeature, StraightSegment
from kumiki.rule import Orientation, Transform, create_v2, create_v3, scalar
from tests.testing_shavings import present


def _extent(feature, owner):
    return present(feature.get_extent(owner), "an extent")


def _region(feature, owner):
    return present(_extent(feature, owner).region, "an outline")


def _points(region):
    return [tuple(round(float(p[i, 0]), 9) for i in range(3)) for p in region.boundary]


def _on_plane(region):
    normal = region.plane.normal
    return all(abs(float(((p - region.plane.point).T * normal)[0, 0])) < 1e-9 for p in region.boundary)


def _prism(turn=0.0, end=10):
    orientation = Orientation.from_axis_angle(create_v3(0, 0, 1), turn) if turn else Transform.identity().orientation
    return RectangularPrism(size=create_v2(4, 6), transform=Transform(position=create_v3(0, 0, 0), orientation=orientation),
                            start_distance=scalar(0), end_distance=None if end is None else scalar(end))


class TestPrism:

    def test_a_face_is_its_four_corners(self):
        region = _region(SimpleRectangularPrismFeature("r", face=PrismFace.RIGHT), _prism())

        assert sorted(_points(region)) == [(2, -3, 0), (2, -3, 10), (2, 3, 0), (2, 3, 10)]
        assert _on_plane(region)

    def test_a_turned_prism_s_face_is_exact_not_a_box_around_it(self):
        prism = _prism(turn=math.pi / 6)
        feature = SimpleRectangularPrismFeature("r", face=PrismFace.RIGHT)

        region = _region(feature, prism)

        assert region.boundary == feature.corners(prism)
        assert _on_plane(region)
        assert all(feature.test_point_unbounded(prism, corner, scalar(1e-9)) for corner in region.boundary)

    def test_a_side_running_to_infinity_has_no_outline_but_its_cap_does(self):
        prism = _prism(end=None)

        assert _extent(SimpleRectangularPrismFeature("r", face=PrismFace.RIGHT), prism).region is None
        assert _extent(SimpleRectangularPrismFeature("b", face=PrismFace.BOTTOM), prism).region is not None


HEXAGON = [create_v2(math.cos(k * math.pi / 3), math.sin(k * math.pi / 3)) for k in range(6)]


class TestExtrusion:

    def _hexagon(self, end=4):
        return ConvexPolygonExtrusion(points=HEXAGON, transform=Transform.identity(),
                                      start_distance=scalar(0), end_distance=None if end is None else scalar(end))

    def test_a_cap_is_the_profile(self):
        region = _region(SimpleConvexPolygonExtrusionFeature("top", key=ExtrusionCap.TOP), self._hexagon())

        assert len(region.boundary) == 6
        assert all(z == 4 for (_, _, z) in _points(region))
        assert _on_plane(region)

    def test_a_side_is_its_own_rectangle_not_the_whole_solid(self):
        region = _region(SimpleConvexPolygonExtrusionFeature("s", key=0), self._hexagon())
        a, b = HEXAGON[0], HEXAGON[1]

        assert sorted(_points(region)) == sorted(
            (round(float(p[0]), 9), round(float(p[1]), 9), z) for p in (a, b) for z in (0, 4))
        assert _on_plane(region)

    def test_a_side_running_to_infinity_has_no_outline(self):
        assert _extent(SimpleConvexPolygonExtrusionFeature("s", key=0), self._hexagon(end=None)).region is None


class TestLoft:

    def _taper(self):
        square = [create_v2(-2, -2), create_v2(2, -2), create_v2(2, 2), create_v2(-2, 2)]
        small = [create_v2(-1, -1), create_v2(1, -1), create_v2(1, 1), create_v2(-1, 1)]
        return ConvexPolygonSimpleLoft(bottom_points=square, top_points=small, bottom_points_z_pos=scalar(0),
                                       top_points_z_pos=scalar(3), transform=Transform.identity())

    def test_caps_are_their_profiles(self):
        loft = self._taper()

        top = _region(SimpleLoftFeature("top", key=ExtrusionCap.TOP), loft)
        bottom = _region(SimpleLoftFeature("bottom", key=ExtrusionCap.BOTTOM), loft)

        assert sorted(_points(top)) == [(-1, -1, 3), (-1, 1, 3), (1, -1, 3), (1, 1, 3)]
        assert sorted(_points(bottom)) == [(-2, -2, 0), (-2, 2, 0), (2, -2, 0), (2, 2, 0)]

    def test_a_sloping_side_is_its_four_corners(self):
        region = _region(SimpleLoftFeature("s", key=0), self._taper())

        assert sorted(_points(region)) == [(-2, -2, 0), (-1, -1, 3), (1, -1, 3), (2, -2, 0)]
        assert _on_plane(region)


class TestPathExtrusion:

    def _square(self):
        corners = [create_v2(0, 0), create_v2(1, 0), create_v2(1, 1), create_v2(0, 1)]
        path = FancyPath(segments=[StraightSegment(corners[i], corners[(i + 1) % 4]) for i in range(4)])
        return PathExtrusion(path=path, transform=Transform.identity(), start_distance=scalar(0),
                             end_distance=scalar(2))

    def test_a_straight_side_is_its_rectangle(self):
        region = _region(SimplePathExtrusionFeature("s", key=FlatSide(0)), self._square())

        assert sorted(_points(region)) == [(0, 0, 0), (0, 0, 2), (1, 0, 0), (1, 0, 2)]
        assert _on_plane(region)

    def test_a_cap_follows_the_path_so_gives_no_convex_outline(self):
        assert _extent(SimplePathExtrusionFeature("top", key=ExtrusionCap.TOP), self._square()).region is None
