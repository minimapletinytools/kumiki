"""Tests for where a feature actually is (kumiki/cropcsg.py).

The declared extent of a feature is the extent of the primitive it was declared
on, and primitives are deliberately not the finished piece. These pin the
cropping that turns one into the other.
"""

import pytest

from kumiki.cutcsg import HalfSpace, RectangularPrism
from kumiki.geometry import (
    ConvexPlanarRegion, Line, LineSegment, Plane, frame_for_plane,
)
from kumiki.cropcsg import (
    approximately_crop_plane_to_area_on_csg,
    BoundsKind,
    solid_bounds,
    convex_hull_2d,
    crop_line_to_segments_on_csg,
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
        faces = solid_bounds(HalfSpace(normal=_v(0, 0, 1), offset=scalar(2))).faces

        assert len(faces) == 1
        normal, point = faces[0]
        # Outward, so away from the material it keeps.
        assert _dot(normal, _v(0, 0, 1)) == pytest.approx(-1, abs=1e-9)
        assert float(point[2, 0]) == pytest.approx(2, abs=1e-9)

    def test_a_closed_prism_bounds_with_six(self):
        assert len(solid_bounds(_box()).faces) == 6

    def test_an_end_that_runs_to_infinity_bounds_nothing(self):
        # The case that started all of this: a cutter extended so the cut comes
        # out clean has no face out there to bound anything.
        assert len(solid_bounds(_box(start=None)).faces) == 5
        assert len(solid_bounds(_box(start=None, end=None)).faces) == 4

    def test_a_shape_it_cannot_describe_says_so(self):
        # None rather than an empty list: "does not bound" and "cannot say"
        # are different answers, and only the second should stop a caller.
        from kumiki.cutcsg import EmptyCSG

        assert solid_bounds(EmptyCSG()).is_empty

    def test_the_three_answers_are_told_apart(self):
        from kumiki.cutcsg import EmptyCSG

        assert solid_bounds(_box()).kind is BoundsKind.HALF_SPACES
        assert solid_bounds(EmptyCSG()).kind is BoundsKind.EMPTY
        assert solid_bounds(_undescribable()).kind is BoundsKind.UNKNOWN

    def test_ignoring_the_answer_fails_loudly_rather_than_quietly(self):
        """faces is None unless there are faces, on purpose.

        An empty list would have read as "no bounds", which is the opposite --
        everything -- so a caller that forgot to check the tag would silently
        return too much. This way it raises instead.
        """
        from kumiki.cutcsg import EmptyCSG

        for csg in (EmptyCSG(), _undescribable()):
            with pytest.raises(TypeError):
                list(solid_bounds(csg).faces)


class TestRegionInPlane:
    def test_a_plane_through_a_box_is_the_box_cross_section(self):
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5))

        region = approximately_crop_plane_to_area_on_csg(plane, [box], seed_reach=10, near=_v(0, 0, 0))

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

        region = approximately_crop_plane_to_area_on_csg(plane, [HalfSpace(normal=_v(0, 0, 1), offset=scalar(0)), timber],
                                 seed_reach=10, near=_v(0, 0, 0))

        assert len(region.boundary) == 4
        assert region.extent_along(_v(1, 0, 0))[1] == pytest.approx(0.05, abs=1e-9)

    def test_a_plane_that_misses_everything_leaves_nothing(self):
        # Which is how a feature says it is not on the finished piece at all.
        box = _box(start=0.0, end=1.0)
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 5))

        region = approximately_crop_plane_to_area_on_csg(plane, [box], seed_reach=20, near=_v(0, 0, 5))

        assert region.is_empty

    def test_it_gives_up_rather_than_returning_too_much(self):
        # A region clipped by only the solids it understood would be silently
        # larger than the truth, which is worse than no answer.
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        assert approximately_crop_plane_to_area_on_csg(
            plane, [_box(), _undescribable()], seed_reach=10, near=_v(0, 0, 0)) is None

    def test_an_empty_solid_crops_everything_away_rather_than_giving_up(self):
        # "Contains nothing" is an answer; "cannot describe" is not. The two
        # crops used to disagree about which one this was, and an empty solid
        # is not hypothetical -- a timber whose stock is already perfect puts
        # one in its own tree.
        from kumiki.cutcsg import EmptyCSG

        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        region = approximately_crop_plane_to_area_on_csg(
            plane, [_box(), EmptyCSG()], seed_reach=10, near=_v(0, 0, 0))

        assert region is not None and region.is_empty

    def test_the_centroid_lies_in_the_plane(self):
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.25))

        centre = approximately_crop_plane_to_area_on_csg(plane, [box], seed_reach=10, near=_v(0, 0, 0)).centroid()

        assert float(centre[2, 0]) == pytest.approx(0.25, abs=1e-9)

    def test_extent_along_answers_for_any_direction(self):
        # What makes orienting the region to a viewport unnecessary: ask along
        # the viewport's own axes and the answer is the bounds in that view.
        box = _box(size=(0.1, 0.2), start=0.0, end=1.0)
        region = approximately_crop_plane_to_area_on_csg(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5)),
                                 [box], seed_reach=10, near=_v(0, 0, 0))

        diagonal = _v(0.7071, 0.7071, 0)
        along = region.extent_along(diagonal)
        assert along[1] > along[0]

    def test_an_empty_region_has_no_centroid_to_offer(self):
        assert ConvexPlanarRegion(plane=Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0)),
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
        assert len(solid_bounds(self._loft(self._square(0.1), self._square(0.05))).faces) == 6

    def test_a_twisted_loft_is_bounded_loosely_rather_than_refused(self):
        # Its sides are ruled surfaces with no plane of their own, so each
        # plane is pushed out to the furthest corner. That bounds the corners'
        # hull, which contains the loft -- loose, but the right direction.
        twisted = self._loft(self._square(0.1), self._turned(0.1, 30))

        faces = solid_bounds(twisted).faces

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
            region = approximately_crop_plane_to_area_on_csg(
                Plane(normal=_v(0, 0, 1), point=_v(0, 0, height)),
                [taper], seed_reach=10, near=_v(0, 0, 0))
            low, high = region.extent_along(_v(1, 0, 0))
            assert high - low == pytest.approx(width, abs=1e-9), height


def _undescribable():
    """A solid solid_bounds cannot describe: a loft running to infinity."""
    from kumiki.cutcsg import ConvexPolygonSimpleLoft

    square = [(-0.05, -0.05), (0.05, -0.05), (0.05, 0.05), (-0.05, 0.05)]
    return ConvexPolygonSimpleLoft(
        bottom_points=square, top_points=square,
        transform=Transform(position=_v(0, 0, 0),
                            orientation=Transform.identity().orientation),
        start_distance=None, end_distance=None,
    )


def _span(segments, direction=None):
    """The one span expected, as (low, high) along the line."""
    assert len(segments) == 1, f"expected one segment, got {len(segments)}"
    return segments[0].extent_along(direction if direction is not None else _v(0, 0, 1))


class TestTheBoundedTypes:
    """LineSegment and ConvexPlanarRegion, apart from what produces them."""

    def _line(self):
        return Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

    def _piece(self, low, high):
        return LineSegment(line=self._line(), start=_v(0, 0, low), end=_v(0, 0, high))

    def test_a_piece_knows_its_own_length_and_middle(self):
        piece = self._piece(0.2, 0.8)

        assert piece.length() == pytest.approx(0.6, abs=1e-9)
        assert float(piece.midpoint()[2, 0]) == pytest.approx(0.5, abs=1e-9)

    def test_a_piece_keeps_the_line_direction_rather_than_deriving_it(self):
        # Derived from the ends, this would point the other way whenever they
        # came back in the other order. A cropped edge's direction is the parent
        # line's, and that is the one that means something.
        backwards = Line(direction=_v(0, 0, -1), point=_v(0, 0, 0))
        piece = LineSegment(line=backwards, start=_v(0, 0, 0), end=_v(0, 0, 1))

        assert float(piece.line.direction[2, 0]) == -1.0

    def test_a_convex_outline_is_accepted(self):
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        region = ConvexPlanarRegion(plane=plane, boundary=(
            _v(0, 0, 0), _v(1, 0, 0), _v(1, 1, 0), _v(0, 1, 0)))

        assert not region.is_empty

    def test_a_concave_outline_is_refused_on_the_spot(self):
        # Rather than answering confidently and wrongly later: centroid()
        # averages the corners and extent_along() reads only the corners, and
        # both of those are the centre and the bounds of a CONVEX outline.
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        with pytest.raises(ValueError, match="not convex"):
            ConvexPlanarRegion(plane=plane, boundary=(
                _v(0, 0, 0), _v(2, 0, 0), _v(1, 1, 0), _v(2, 2, 0), _v(0, 2, 0)))

    def test_a_straight_corner_is_not_a_reversal(self):
        # Three points in a row turn neither way, and clipping produces them
        # whenever a cut passes exactly through a corner.
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        ConvexPlanarRegion(plane=plane, boundary=(
            _v(0, 0, 0), _v(1, 0, 0), _v(2, 0, 0), _v(2, 1, 0), _v(0, 1, 0)))

    def test_too_few_corners_to_be_concave_is_allowed(self):
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        assert ConvexPlanarRegion(plane=plane, boundary=()).is_empty
        assert ConvexPlanarRegion(plane=plane, boundary=(_v(0, 0, 0), _v(1, 0, 0))).is_empty

    def test_the_check_does_not_care_how_big_the_region_is(self):
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        for size in (0.005, 5.0):
            ConvexPlanarRegion(plane=plane, boundary=(
                _v(0, 0, 0), _v(size, 0, 0), _v(size, size, 0), _v(0, size, 0)))

    def test_a_reversal_between_two_short_edges_is_still_a_reversal(self):
        """Why the test is per corner and relative rather than one number.

        A turn is a cross product, so it is an AREA: |e1||e2|sin(t). Compared
        against a single slack taken from the outline's longest edge, the same
        angle reads as huge between two long edges and as nothing between two
        short ones -- so this dent, which is a real reflex corner, passed as
        convex. Dividing the edge lengths back out leaves the angle itself.
        """
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))
        nick = 1e-5
        # A metre square with a 14-micron dent in the middle of its top edge.
        dented = (
            _v(0, 0, 0), _v(1, 0, 0), _v(1, 1, 0),
            _v(0.5 + nick, 1, 0), _v(0.5, 1 - nick, 0), _v(0.5 - nick, 1, 0),
            _v(0, 1, 0),
        )

        with pytest.raises(ValueError, match="not convex"):
            ConvexPlanarRegion(plane=plane, boundary=dented)

    def test_a_repeated_corner_is_not_a_turn(self):
        # No edge, so no direction to turn from. Dividing by its length would
        # divide by zero.
        plane = Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0))

        ConvexPlanarRegion(plane=plane, boundary=(
            _v(0, 0, 0), _v(1, 0, 0), _v(1, 0, 0), _v(1, 1, 0), _v(0, 1, 0)))


class TestCropLineToSegmentsOnCsg:
    """An edge, cropped by the whole tree rather than by what encloses it."""

    def test_a_line_through_a_box_is_the_box_thickness(self):
        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        segments = crop_line_to_segments_on_csg(
            line, _box(size=(0.1, 0.2), start=0.0, end=1.0), seed_reach=10, near=_v(0, 0, 0))

        low, high = _span(segments)
        assert low == pytest.approx(0.0, abs=1e-9)
        assert high == pytest.approx(1.0, abs=1e-9)

    def test_the_midpoint_is_the_middle_of_what_survives(self):
        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        cropped = crop_line_to_segments_on_csg(
            line, _box(size=(0.1, 0.2), start=0.0, end=1.0), seed_reach=10, near=_v(0, 0, 0))

        assert float(max(cropped, key=lambda s: s.length()).midpoint()[2, 0]) == pytest.approx(0.5, abs=1e-9)

    def test_an_edge_declared_far_away_still_crops_to_the_timber(self):
        # An edge declared on a cutter extended past the timber has its own
        # point out there with the cutter. Starting from that point and
        # clipping leaves nothing, so the search starts near the timber.
        far = Line(direction=_v(0, 0, 1), point=_v(0.05, 0.1, 900))

        cropped = crop_line_to_segments_on_csg(
            far, _box(size=(0.1, 0.2), start=0.0, end=1.0),
            seed_reach=10, near=_v(0, 0, 0.5))

        assert len(cropped) == 1
        assert float(max(cropped, key=lambda s: s.length()).midpoint()[2, 0]) == pytest.approx(0.5, abs=1e-6)

    def test_a_line_that_misses_everything_leaves_nothing(self):
        line = Line(direction=_v(0, 0, 1), point=_v(5, 5, 0))

        assert crop_line_to_segments_on_csg(
            line, _box(), seed_reach=10, near=_v(0, 0, 0)) == []

    def test_a_line_running_along_a_face_it_is_outside_of_keeps_nothing(self):
        # Parallel to every bounding plane it is outside: no bound to compute,
        # so the parallel case has to answer rather than skip.
        line = Line(direction=_v(0, 0, 1), point=_v(5, 0, 0))

        assert crop_line_to_segments_on_csg(
            line, _box(), seed_reach=10, near=_v(0, 0, 0.5)) == []

    def test_it_gives_up_rather_than_returning_too_much(self):
        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        assert crop_line_to_segments_on_csg(
            line, _undescribable(), seed_reach=10, near=_v(0, 0, 0)) is None

    def test_one_undescribable_solid_loses_the_whole_answer(self):
        # Not a shortened segment built from the parts it did understand: a
        # partial answer is wrong in a direction nobody can see.
        from kumiki.cutcsg import Difference

        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))
        tree = Difference(base=_box(), subtract=[_undescribable()])

        assert crop_line_to_segments_on_csg(
            line, tree, seed_reach=10, near=_v(0, 0, 0)) is None


class TestSolvingACylinderRatherThanBoundingIt:
    """The hexagon circumscribes the cylinder, so it reports chords too long."""

    def _cylinder(self, radius=1.0, start=0.0, end=10.0, axis=None):
        from kumiki.cutcsg import Cylinder

        return Cylinder(
            axis_direction=axis if axis is not None else _v(0, 0, 1),
            radius=scalar(radius),
            position=_v(0, 0, 0),
            start_distance=None if start is None else scalar(start),
            end_distance=None if end is None else scalar(end),
        )

    def _across(self, offset):
        """A line crossing the barrel, `offset` from the axis."""
        return Line(direction=_v(1, 0, 0), point=_v(0, offset, 5))

    def test_a_chord_is_the_length_the_circle_actually_gives(self):
        # 2*sqrt(r^2 - offset^2), which is what a circle is and a hexagon is not.
        import math

        for offset in (0.0, 0.5, 0.9):
            span = _span(crop_line_to_segments_on_csg(
                self._across(offset), self._cylinder(radius=1.0),
                seed_reach=50, near=_v(0, 0, 5)), _v(1, 0, 0))

            expected = 2.0 * math.sqrt(1.0 - offset * offset)
            assert span[1] - span[0] == pytest.approx(expected, abs=1e-9), offset

    def test_the_hexagon_reports_a_grazing_chord_four_times_too_long(self):
        """Pins how much the bound gave away, rather than assuming it gave any.

        Worst where it matters most: a chord close to the rim runs between two
        of the hexagon's flats and out towards a corner, so the bound keeps
        most of a corner the cylinder does not have. Away from the rim the
        two agree to about a percent, which is why this is easy to miss.
        """
        import math

        from kumiki.cropcsg import _spans_within_primitive, solid_bounds

        offset, angle = 0.99, math.radians(30)
        along = _v(math.cos(angle), math.sin(angle), 0)
        line = Line(direction=along,
                    point=_v(-math.sin(angle) * offset, math.cos(angle) * offset, 5))
        cylinder = self._cylinder(radius=1.0)

        bounded = _spans_within_primitive(
            solid_bounds(cylinder).faces, line, (-50.0, 50.0), 0.0, False)
        solved = _span(crop_line_to_segments_on_csg(
            line, cylinder, seed_reach=50, near=_v(0, 0, 5)), along)

        exact = 2.0 * math.sqrt(1.0 - offset * offset)
        assert solved[1] - solved[0] == pytest.approx(exact, abs=1e-9)
        assert (bounded[0][1] - bounded[0][0]) > 4.0 * (solved[1] - solved[0])

    def test_a_line_down_the_axis_runs_the_whole_length(self):
        span = _span(crop_line_to_segments_on_csg(
            Line(direction=_v(0, 0, 1), point=_v(0, 0, 0)),
            self._cylinder(start=0.0, end=10.0), seed_reach=50, near=_v(0, 0, 5)))

        assert span == pytest.approx((0.0, 10.0), abs=1e-9)

    def test_a_line_that_misses_the_barrel_is_not_on_it(self):
        assert crop_line_to_segments_on_csg(
            self._across(1.5), self._cylinder(radius=1.0),
            seed_reach=50, near=_v(0, 0, 5)) == []

    def test_a_tangent_line_touches_without_running_along_anything(self):
        # One point is not a segment.
        assert crop_line_to_segments_on_csg(
            self._across(1.0), self._cylinder(radius=1.0),
            seed_reach=50, near=_v(0, 0, 5)) == []

    def test_a_line_on_the_barrel_survives_the_bore_it_lies_on(self):
        """The reason the removing rule has to reach the curved surface too.

        This line runs down the wall of a bore, parallel to its axis -- the
        arris where the bore meets a face. Widening the bore to find it would
        delete it instead.
        """
        from kumiki.cutcsg import Difference

        body = _box(size=(4, 4), start=0.0, end=10.0)
        bore = self._cylinder(radius=1.0, start=-1.0, end=11.0)
        on_the_wall = Line(direction=_v(0, 0, 1), point=_v(1.0, 0, 0))

        span = _span(crop_line_to_segments_on_csg(
            on_the_wall, Difference(base=body, subtract=[bore]),
            seed_reach=50, near=_v(0, 0, 5), tolerance=1e-3))

        assert span[1] - span[0] == pytest.approx(10.0, abs=3e-3)

    def test_a_bore_shortens_a_line_that_runs_through_it(self):
        from kumiki.cutcsg import Difference

        body = _box(size=(4, 4), start=0.0, end=10.0)
        # Across the body, straight through the middle of the bore.
        through = Line(direction=_v(1, 0, 0), point=_v(0, 0, 5))

        segments = crop_line_to_segments_on_csg(
            through, Difference(base=body, subtract=[self._cylinder(radius=1.0)]),
            seed_reach=50, near=_v(0, 0, 5))

        # Two pieces, the bore's diameter apart.
        assert len(segments) == 2
        gap = (segments[1].extent_along(_v(1, 0, 0))[0]
               - segments[0].extent_along(_v(1, 0, 0))[1])
        assert gap == pytest.approx(2.0, abs=1e-9)

    def test_an_uncapped_cylinder_is_bounded_by_the_search_alone(self):
        span = _span(crop_line_to_segments_on_csg(
            Line(direction=_v(0, 0, 1), point=_v(0, 0, 0)),
            self._cylinder(start=None, end=None), seed_reach=7, near=_v(0, 0, 0)))

        assert span == pytest.approx((-7.0, 7.0), abs=1e-9)

    def test_it_solves_a_cylinder_at_any_angle(self):
        import math

        tilted = self._cylinder(radius=1.0, start=-20.0, end=20.0,
                                axis=_v(1, 1, 0))
        # Perpendicular to that axis, through its centre.
        line = Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

        span = _span(crop_line_to_segments_on_csg(
            line, tilted, seed_reach=50, near=_v(0, 0, 0)))

        assert span[1] - span[0] == pytest.approx(2.0, abs=1e-9)


class TestALineOnABoundaryIsKept:
    """The rule, both ways round.

    Added, "on the face" means on the solid. Removed, "on the wall" means on
    the surface of the void rather than inside it. Opposite comparisons, one
    outcome: the line stays. Get it backwards for the removing case and every
    arris a cut passes through the plane of disappears.
    """

    def _kept(self, line, csg, tolerance=0.0):
        segments = crop_line_to_segments_on_csg(
            line, csg, seed_reach=50, near=_v(0, 0, 5), tolerance=tolerance)
        return sum(segment.length() for segment in (segments or []))

    def _bore(self, radius=1.0, start=-1.0, end=11.0):
        from kumiki.cutcsg import Cylinder

        return Cylinder(axis_direction=_v(0, 0, 1), radius=scalar(radius),
                        position=_v(0, 0, 0), start_distance=scalar(start),
                        end_distance=scalar(end))

    def test_on_a_flat_face_being_added(self):
        assert self._kept(Line(direction=_v(0, 0, 1), point=_v(2, 0, 0)),
                          _box(size=(4, 4), start=0, end=10)) == pytest.approx(10.0)

    def test_on_a_flat_face_being_removed(self):
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(size=(8, 4), start=0, end=10),
                          subtract=[_box(size=(4, 4), start=0, end=10, position=(4, 0, 0))])

        assert self._kept(Line(direction=_v(0, 0, 1), point=_v(2, 0, 0)),
                          tree) == pytest.approx(10.0)

    def test_on_a_barrel_being_added(self):
        assert self._kept(Line(direction=_v(0, 0, 1), point=_v(1, 0, 0)),
                          self._bore(start=0.0, end=10.0)) == pytest.approx(10.0)

    def test_on_a_barrel_being_removed(self):
        # The arris down the wall of a bore. Widening the bore to find it would
        # be the one thing that deletes it.
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(size=(4, 4), start=0, end=10), subtract=[self._bore()])

        assert self._kept(Line(direction=_v(0, 0, 1), point=_v(1, 0, 0)),
                          tree) == pytest.approx(10.0)

    def test_on_a_cap_of_something_being_removed(self):
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(size=(4, 4), start=0, end=10),
                          subtract=[_box(size=(4, 4), start=5, end=20)])

        assert self._kept(Line(direction=_v(1, 0, 0), point=_v(0, 0, 5)),
                          tree) == pytest.approx(4.0)

    def test_and_still_with_a_tolerance_in_play(self):
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(size=(4, 4), start=0, end=10), subtract=[self._bore()])

        assert self._kept(Line(direction=_v(0, 0, 1), point=_v(1, 0, 0)),
                          tree, tolerance=1e-3) == pytest.approx(10.0, abs=3e-3)


class TestWhatIsSolvedAndWhatIsBounded:
    """Shapes that ARE their half spaces say so, rather than falling through.

    The fallback is for shapes nobody has solved yet. A prism reaching it read
    as one of those, when clipping a prism by its own six planes is not an
    approximation of the answer -- it is the answer.
    """

    def _line(self):
        return Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

    def _solved(self, csg):
        from kumiki.cropcsg import _exact_spans

        return _exact_spans(csg, self._line(), (-10.0, 10.0), 0.0, False) is not None

    def _loft(self, bottom, top):
        from kumiki.cutcsg import ConvexPolygonSimpleLoft

        return ConvexPolygonSimpleLoft(
            bottom_points=bottom, top_points=top,
            transform=Transform(position=_v(0, 0, 0),
                                orientation=Transform.identity().orientation),
            start_distance=scalar(0), end_distance=scalar(1))

    def test_the_shapes_that_are_their_own_half_spaces(self):
        from kumiki.cutcsg import ConvexPolygonExtrusion, HalfSpace

        square = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        assert self._solved(HalfSpace(normal=_v(0, 0, 1), offset=scalar(0)))
        assert self._solved(_box())
        assert self._solved(ConvexPolygonExtrusion(
            points=square,
            transform=Transform(position=_v(0, 0, 0),
                                orientation=Transform.identity().orientation),
            start_distance=scalar(0), end_distance=scalar(1)))

    def test_a_loft_is_solved_only_where_its_sides_come_out_flat(self):
        import math

        square = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        hexagon = [(math.cos(math.radians(60 * i)), math.sin(math.radians(60 * i)))
                   for i in range(6)]
        turn = math.radians(20)

        # Edges along the axes being scaled, so per-axis scaling keeps them flat.
        assert self._solved(self._loft(square, [(x * 0.5, y * 0.8) for x, y in square]))
        # Any profile survives a uniform scale.
        assert self._solved(self._loft(hexagon, [(x * 0.5, y * 0.5) for x, y in hexagon]))
        # A hexagon's edges do not run along the axes, so per-axis scaling bends
        # its sides -- which the old rule of thumb said it would not.
        assert not self._solved(self._loft(hexagon, [(x * 0.5, y * 0.8) for x, y in hexagon]))
        # And a twist bends them however the profile is shaped.
        assert not self._solved(self._loft(square, [
            (math.cos(turn) * x - math.sin(turn) * y,
             math.sin(turn) * x + math.cos(turn) * y) for x, y in square]))

    def test_a_path_extrusion_still_falls_through_to_the_bound(self):
        from kumiki.pathcsg import FancyPath, PathExtrusion, StraightSegment
        from kumiki.rule import create_v2

        def corner(x, y):
            return create_v2(scalar(x), scalar(y))

        path = FancyPath(segments=[
            StraightSegment(corner(0, 0), corner(1, 0)),
            StraightSegment(corner(1, 0), corner(1, 1)),
            StraightSegment(corner(1, 1), corner(0, 0)),
        ])
        extrusion = PathExtrusion(
            path=path,
            transform=Transform(position=_v(0, 0, 0),
                                orientation=Transform.identity().orientation),
            start_distance=scalar(0), end_distance=scalar(1))

        assert not self._solved(extrusion)


class TestCroppingThroughTheTree:
    """The point of walking it: what has been cut away is gone."""

    def _line(self):
        return Line(direction=_v(0, 0, 1), point=_v(0, 0, 0))

    def test_a_cut_at_one_end_shortens_the_edge(self):
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(start=0.0, end=1.0),
                          subtract=[_box(start=0.75, end=2.0)])

        low, high = _span(crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5)))

        assert low == pytest.approx(0.0, abs=1e-9)
        assert high == pytest.approx(0.75, abs=1e-9)

    def test_a_cut_through_the_middle_splits_the_edge_in_two(self):
        # The reason this returns a list at all. A mortise crossing an arris
        # leaves two pieces, and one segment spanning both would draw straight
        # through the hole.
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(start=0.0, end=1.0),
                          subtract=[_box(start=0.4, end=0.6)])

        segments = crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5))

        assert len(segments) == 2
        assert segments[0].extent_along(_v(0, 0, 1)) == pytest.approx((0.0, 0.4), abs=1e-9)
        assert segments[1].extent_along(_v(0, 0, 1)) == pytest.approx((0.6, 1.0), abs=1e-9)

    def test_two_cuts_leave_three_pieces(self):
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(start=0.0, end=1.0),
                          subtract=[_box(start=0.2, end=0.3), _box(start=0.6, end=0.7)])

        segments = crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5))

        assert len(segments) == 3

    def test_a_cut_that_removes_all_of_it_leaves_nothing(self):
        from kumiki.cutcsg import Difference

        tree = Difference(base=_box(start=0.0, end=1.0),
                          subtract=[_box(start=-1.0, end=2.0)])

        assert crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5)) == []

    def test_a_cut_flush_with_the_face_the_edge_lies_on_keeps_it(self):
        # The case that decides the sign of the tolerance. This arris runs along
        # the box's own corner, and the cut's wall is flush with the face it
        # opens onto -- so the cut touches the edge without removing any of it.
        # Widening the subtractor by the tolerance would delete the arris.
        from kumiki.cutcsg import Difference

        arris = Line(direction=_v(0, 0, 1), point=_v(0.05, 0.1, 0))
        flush = _box(size=(0.1, 0.2), start=0.0, end=1.0, position=(0.1, 0.0, 0.0))
        tree = Difference(base=_box(size=(0.1, 0.2), start=0.0, end=1.0), subtract=[flush])

        # At zero tolerance too, which is the pass that actually runs: the
        # degenerate "line lies in a face plane" test has to answer differently
        # for a solid being removed than for one being added, and at exactly
        # zero there is no slack to hide behind.
        for tolerance in (0.0, 1e-3):
            segments = crop_line_to_segments_on_csg(
                arris, tree, seed_reach=10, near=_v(0, 0, 0.5), tolerance=tolerance)

            # Whole and in one piece. Not exactly (0, 1) once there is a
            # tolerance: it widens the base box too, which is the additive half
            # of the same rule.
            low, high = _span(segments)
            assert high - low == pytest.approx(1.0, abs=3e-3), tolerance

    def test_a_cut_that_only_touches_the_line_does_not_take_it(self):
        """A cut lying against the base takes nothing from it.

        This one reaches past the corner in y, but in x it stops exactly at the
        base's own face -- so the two share a plane and nothing else, and the
        arris along that plane survives. Decided by asking the solid, not by
        reading the line: on the line alone this is indistinguishable from a
        cut that planes the arris away.
        """
        from kumiki.cutcsg import Difference

        arris = Line(direction=_v(0, 0, 1), point=_v(0.05, 0.1, 0))
        # Reaches past the corner in y, so the material inside the arris is gone.
        eats_corner = _box(size=(0.1, 0.4), start=0.3, end=0.6, position=(0.1, 0.0, 0.0))
        tree = Difference(base=_box(size=(0.1, 0.2), start=0.0, end=1.0),
                          subtract=[eats_corner])

        low, high = _span(crop_line_to_segments_on_csg(
            arris, tree, seed_reach=10, near=_v(0, 0, 0.5)))

        assert (low, high) == pytest.approx((0.0, 1.0), abs=1e-9)

    def test_a_cut_flush_with_a_face_does_take_the_arris_in_it(self):
        """The other side of the same ambiguity, and the bug it caused.

        Here the cut genuinely reaches into the base -- it is a notch, not a
        neighbour -- and its wall is flush with the face the arris lies in. The
        arris through the notch is gone, and saying otherwise drew a line
        straight across the opening. On a cross lap that was 127mm of edge
        drawn through thin air.
        """
        from kumiki.cutcsg import Difference

        arris = Line(direction=_v(0, 0, 1), point=_v(0.05, 0.1, 0))
        # Reaching past the base's front face rather than stopping on it, which
        # is how a cutter is always built -- extended, so the cut comes out
        # clean. That is what puts the arris strictly INSIDE the cutter and
        # settles the question.
        notch = _box(size=(0.06, 0.1), start=0.4, end=0.6, position=(0.03, 0.08, 0.0))
        tree = Difference(base=_box(size=(0.1, 0.2), start=0.0, end=1.0), subtract=[notch])

        segments = crop_line_to_segments_on_csg(
            arris, tree, seed_reach=10, near=_v(0, 0, 0.5))

        assert len(segments) == 2
        assert segments[0].extent_along(_v(0, 0, 1)) == pytest.approx((0.0, 0.4), abs=1e-9)
        assert segments[1].extent_along(_v(0, 0, 1)) == pytest.approx((0.6, 1.0), abs=1e-9)

    def test_a_union_joins_what_each_child_covers(self):
        from kumiki.cutcsg import SolidUnion

        tree = SolidUnion(children=[_box(start=0.0, end=0.5), _box(start=0.5, end=1.0)])

        low, high = _span(crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5)))

        assert low == pytest.approx(0.0, abs=1e-9)
        assert high == pytest.approx(1.0, abs=1e-9)

    def test_a_union_of_two_apart_leaves_two_pieces(self):
        from kumiki.cutcsg import SolidUnion

        tree = SolidUnion(children=[_box(start=0.0, end=0.3), _box(start=0.7, end=1.0)])

        assert len(crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5))) == 2

    def test_an_intersection_keeps_only_the_overlap(self):
        from kumiki.cutcsg import Intersection

        tree = Intersection(left=_box(start=0.0, end=0.8), right=_box(start=0.4, end=1.0))

        low, high = _span(crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5)))

        assert low == pytest.approx(0.4, abs=1e-9)
        assert high == pytest.approx(0.8, abs=1e-9)

    def test_an_empty_solid_contains_no_line(self):
        from kumiki.cutcsg import EmptyCSG

        assert crop_line_to_segments_on_csg(
            self._line(), EmptyCSG(), seed_reach=10, near=_v(0, 0, 0)) == []

    def test_subtracting_nothing_changes_nothing(self):
        from kumiki.cutcsg import Difference, EmptyCSG

        tree = Difference(base=_box(start=0.0, end=1.0), subtract=[EmptyCSG()])

        low, high = _span(crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5)))

        assert (low, high) == pytest.approx((0.0, 1.0), abs=1e-9)

    def test_a_bore_axis_is_not_on_the_solid_it_bored(self):
        # Ported from the sampler this replaced. A bore is a void: its axis runs
        # down the middle of a hole, so once the bore is subtracted the axis is
        # on none of what is left. The sampler said None for this; [] is the
        # same answer said properly -- "not there", not "cannot tell".
        from kumiki.cutcsg import Cylinder, Difference

        body = _box(size=(4, 6), start=0.0, end=10.0)
        bore = Cylinder(
            axis_direction=_v(0, 0, 1), radius=scalar(1), position=_v(0, 0, 0),
            start_distance=scalar(-1), end_distance=scalar(11),
        )
        axis = Line(direction=_v(0, 0, 1), point=_v(0, 0, 5))

        assert crop_line_to_segments_on_csg(
            axis, Difference(base=body, subtract=[bore]),
            seed_reach=50, near=_v(0, 0, 5)) == []

        low, high = _span(crop_line_to_segments_on_csg(
            axis, body, seed_reach=50, near=_v(0, 0, 5)))
        assert (low, high) == pytest.approx((0.0, 10.0), abs=1e-6)

    def test_a_difference_inside_a_subtraction_is_additive_again(self):
        # The subtracted solid is itself a box with its middle removed, so the
        # middle survives in the result. Gets the tolerance sign flip wrong and
        # this comes back as one span or none.
        from kumiki.cutcsg import Difference

        hollow = Difference(base=_box(start=0.2, end=0.8), subtract=[_box(start=0.4, end=0.6)])
        tree = Difference(base=_box(start=0.0, end=1.0), subtract=[hollow])

        segments = crop_line_to_segments_on_csg(
            self._line(), tree, seed_reach=10, near=_v(0, 0, 0.5))

        assert len(segments) == 3
        assert segments[1].extent_along(_v(0, 0, 1)) == pytest.approx((0.4, 0.6), abs=1e-9)


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
        assert len(solid_bounds(self._cylinder()).faces) == 8  # six sides, two ends

    def test_a_cylinder_running_to_infinity_has_no_ends(self):
        assert len(solid_bounds(self._cylinder(start=None, end=None)).faces) == 6

    def test_the_hexagon_contains_the_cylinder(self):
        # Outwards, per the rule at the top of cropcsg: one direction,
        # consistently, so that what a region excludes really is excluded.
        region = approximately_crop_plane_to_area_on_csg(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5)),
                                 [self._cylinder(radius=0.05)], seed_reach=10, near=_v(0, 0, 0))
        across = region.extent_along(_v(1, 0, 0))

        # Tangent faces, so it holds the diameter exactly across the flats,
        # and reaches past it at the corners -- never short of it.
        assert across[1] - across[0] >= 0.1 - 1e-9
        assert across[1] - across[0] < 0.125  # 2r/cos(30) at the widest

    def test_a_cylinder_sections_as_a_hexagon(self):
        region = approximately_crop_plane_to_area_on_csg(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 0.5)),
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

        assert len(solid_bounds(square).faces) == 6

    def test_its_planes_come_from_the_hull_not_the_points_as_given(self):
        # A point inside the outline contributes no face of its own.
        with_inner = self._extrusion([(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)])

        assert len(solid_bounds(with_inner).faces) == 6

    def test_an_extrusion_sections_to_its_cross_section(self):
        square = self._extrusion([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)])
        region = approximately_crop_plane_to_area_on_csg(Plane(normal=_v(0, 0, 1), point=_v(0, 0, 1)),
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
