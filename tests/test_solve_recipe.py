"""Solve recipes: features built from their primitive's carriers, and measurements turned into rows."""

import math

import numpy as np
import pytest

from kumiki.dof_solver import remaining
from kumiki.cutcsg import (
    EdgeFeature, FaceFeature, hit_of_kind,
    CYLINDER_AXIS, CYLINDER_BARREL, HALF_SPACE_PLANE, ConvexPolygonExtrusion, Cylinder, CylinderAxisFeature, DerivedEdgeFeature,
    DerivedPointFeature, Difference, HalfSpace, OwnedFeatureHit, PrismFace, RectangularPrism,
    SolidUnion, prism_arris_key, prism_corner_key, prism_face_key, carrier_map,
)
from kumiki.geometry import Line, Plane, Point, lines_are_coincident, planes_are_coincident
from kumiki.rule import Orientation, Transform, create_v2, create_v3, scalar
from tests.testing_shavings import present
from kumiki.solve_recipe import (
    Anchor, BarrelCoord, CarrierRef, DistanceMeasurement, PlaneCoord, feature_dof_rows, locate_recipe,
    direction_motion, measurement_row, motion_along, moved_by, perturbed,
)


def _v(x, y, z):
    return create_v3(scalar(x), scalar(y), scalar(z))


def _np(vector):
    return np.array([float(vector[i, 0]) for i in range(3)])


def _box(size=(1.0, 2.0), start=0.0, end=4.0, position=(0.0, 0.0, 0.0), turn=0.0):
    orientation = Orientation.from_axis_angle(_v(0, 0, 1), scalar(turn)) if turn else Transform.identity().orientation
    return RectangularPrism(
        size=create_v2(scalar(size[0]), scalar(size[1])),
        transform=Transform(position=_v(*position), orientation=orientation),
        start_distance=None if start is None else scalar(start),
        end_distance=None if end is None else scalar(end),
    )


def _feature(owner, key):
    return next(f for f in owner.get_declared_features() if f.feature_key() == key)


def _hit(feature, owner, kind):
    """A hit typed by its feature's kind."""
    return present(hit_of_kind(OwnedFeatureHit(feature=feature, owner=owner), kind), kind.__name__)


def _recipe(owner, key):
    recipe = _feature(owner, key).solve_recipe(owner)
    assert recipe is not None
    return recipe


def _point(recipe):
    located = locate_recipe(recipe)
    assert isinstance(located, Point)
    return located.position


def _line(geometry):
    assert isinstance(geometry, Line)
    return geometry


def _plane(geometry):
    assert isinstance(geometry, Plane)
    return geometry


def _closest(geometry, at):
    """The point of `geometry` nearest `at`."""
    x = _np(at)
    if isinstance(geometry, Point):
        return _np(geometry.position)
    if isinstance(geometry, Line):
        direction = _np(geometry.direction) / np.linalg.norm(_np(geometry.direction))
        start = _np(geometry.point)
        return start + direction * float((x - start) @ direction)
    normal = _np(geometry.normal)
    return x - normal * float((x - _np(geometry.point)) @ normal) / float(normal @ normal)


def _finite_difference_row(carriers, anchors, along, step=1e-6):
    """What `motion_along` should give, by moving each unknown and re-locating.

    `anchors` is a list of (recipe, at, sign), summed.
    """
    u = _np(along)
    row = {}
    for solving in carriers.solving_carriers():
        for coord in type(carriers.carrier(solving)).COORDS:
            moved = perturbed(carriers.carrier(solving), coord, step)

            def carrier_of(ref, solving=solving, moved=moved):
                return moved if carriers.canonical(ref) == solving else carriers.carrier(ref)

            change = 0.0
            for recipe, at, sign in anchors:
                geometry = locate_recipe(recipe, carrier_of)
                change += sign * float(u @ (_closest(geometry, at) - _np(at))) / step
            if abs(change) > 1e-6:
                row[(solving, coord)] = change
    return row


def _assert_rows_match(actual, expected, tolerance=1e-4):
    for key in set(actual) | set(expected):
        assert actual.get(key, 0.0) == pytest.approx(expected.get(key, 0.0), abs=tolerance), key


def _measure(carriers, anchors, along):
    """One anchor's motion, or the measurement from the -1 anchor to the +1 anchor."""
    if len(anchors) == 1:
        recipe, at, _ = anchors[0]
        return motion_along(recipe, carriers, at, along)
    (end, end_at, _), (start, start_at, _) = sorted(anchors, key=lambda anchor: -anchor[2])
    return measurement_row(DistanceMeasurement(Anchor(start, start_at), Anchor(end, end_at), along), carriers)


class TestRecipesLocateLikeTheirFeatures:

    @pytest.mark.parametrize("owner", [
        _box(),
        _box(turn=0.4, position=(1, 2, 3)),
        HalfSpace(normal=_v(1, 1, 0), offset=scalar(2)),
        Cylinder(axis_direction=_v(0, 1, 1), radius=scalar(0.5), position=_v(1, 0, 0),
                 start_distance=scalar(-1), end_distance=scalar(2),
                 extra_features=(CylinderAxisFeature(name="axis"),)),
        ConvexPolygonExtrusion(points=[create_v2(0, 0), create_v2(2, 0), create_v2(1, 1)],
                               start_distance=scalar(0), end_distance=scalar(3)),
    ])
    def test_every_recipe_builds_the_features_geometry(self, owner):
        checked = 0
        for feature in owner.get_declared_features():
            recipe = feature.solve_recipe(owner)
            expected = feature.locate_simple_unbounded(owner)
            if recipe is None or expected is None:
                continue
            located = locate_recipe(recipe)
            if isinstance(expected, Plane):
                assert planes_are_coincident(_plane(located), expected), feature.name
            elif isinstance(expected, Line):
                assert lines_are_coincident(_line(located), expected), feature.name
            else:
                assert isinstance(located, Point)
                assert np.allclose(_np(located.position), _np(expected.position)), feature.name
            checked += 1
        assert checked > 0

    def test_a_finite_prism_has_a_recipe_for_every_default(self):
        box = _box()
        assert all(f.solve_recipe(box) is not None for f in box.get_declared_features())

    def test_an_infinite_end_has_no_cap_so_its_arrises_and_corners_have_no_recipe(self):
        box = _box(end=None)
        assert _feature(box, prism_face_key(PrismFace.TOP)).solve_recipe(box) is None
        assert _feature(box, prism_arris_key(PrismFace.TOP, PrismFace.RIGHT)).solve_recipe(box) is None
        assert _feature(box, prism_corner_key(PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT)).solve_recipe(box) is None
        assert _feature(box, prism_arris_key(PrismFace.FRONT, PrismFace.RIGHT)).solve_recipe(box) is not None

    def test_a_cylinder_axis_is_the_axis_of_its_barrel(self):
        cylinder = Cylinder(axis_direction=_v(0, 0, 1), radius=scalar(1),
                            extra_features=(CylinderAxisFeature(name="axis"),))
        axis = next(f for f in cylinder.get_declared_features() if f.name == "axis")
        recipe = axis.solve_recipe(cylinder)
        assert recipe == (CarrierRef(cylinder, CYLINDER_AXIS),)


class TestPointToPoint:
    """p1.x - p2.x between corners of two boxes."""

    corner = prism_corner_key(PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT)
    other_corner = prism_corner_key(PrismFace.BOTTOM, PrismFace.LEFT, PrismFace.BACK)

    def test_axis_aligned_corners_touch_only_the_planes_that_fix_x(self):
        a, b = _box(), _box(position=(3, 0, 0))
        carriers = carrier_map(SolidUnion([a, b]))
        p1, p2 = _recipe(a, self.corner), _recipe(b, self.other_corner)
        at1, at2 = _point(p1), _point(p2)

        row = _measure(carriers, [(p1, at1, 1.0), (p2, at2, -1.0)], _v(1, 0, 0))

        right = carriers.canonical(CarrierRef(a, prism_face_key(PrismFace.RIGHT)))
        left = carriers.canonical(CarrierRef(b, prism_face_key(PrismFace.LEFT)))
        assert {ref for ref, _ in row} == {right, left}
        # p1 is on x = 0.5 (normal +x), p2 on x = 2.5 (normal -x, offset -2.5): x1 - x2 = d_right + d_left.
        assert row[(right, PlaneCoord.OFFSET)] == pytest.approx(1.0)
        assert row[(left, PlaneCoord.OFFSET)] == pytest.approx(1.0)
        # Tilt terms: -w (p . e) with e the plane's perpendicular_axes, here y and +-z.
        assert row[(right, PlaneCoord.TILT_1)] == pytest.approx(-float(at1[1, 0]))
        assert row[(right, PlaneCoord.TILT_2)] == pytest.approx(-float(at1[2, 0]))

    def test_matches_finite_differences(self):
        a, b = _box(), _box(position=(3, 0, 0))
        carriers = carrier_map(SolidUnion([a, b]))
        anchors = [(_recipe(a, self.corner), _point(_recipe(a, self.corner)), 1.0),
                   (_recipe(b, self.other_corner), _point(_recipe(b, self.other_corner)), -1.0)]
        _assert_rows_match(_measure(carriers, anchors, _v(1, 0, 0)),
                           _finite_difference_row(carriers, anchors, _v(1, 0, 0)))

    def test_turned_boxes_spread_over_more_planes_and_still_match(self):
        a, b = _box(turn=0.3), _box(position=(3, 1, 0), turn=-0.5)
        carriers = carrier_map(SolidUnion([a, b]))
        anchors = [(_recipe(a, self.corner), _point(_recipe(a, self.corner)), 1.0),
                   (_recipe(b, self.other_corner), _point(_recipe(b, self.other_corner)), -1.0)]
        row = _measure(carriers, anchors, _v(1, 0, 0))
        assert len({ref for ref, _ in row}) == 4
        _assert_rows_match(row, _finite_difference_row(carriers, anchors, _v(1, 0, 0)))

    def test_two_points_on_one_face_measured_along_its_normal_only_check_its_tilt(self):
        a = _box()
        carriers = carrier_map(a)
        top_front = prism_corner_key(PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT)
        bottom_back = prism_corner_key(PrismFace.BOTTOM, PrismFace.BACK, PrismFace.RIGHT)
        anchors = [(_recipe(a, top_front), _point(_recipe(a, top_front)), 1.0),
                   (_recipe(a, bottom_back), _point(_recipe(a, bottom_back)), -1.0)]
        row = _measure(carriers, anchors, _v(1, 0, 0))
        right = CarrierRef(a, prism_face_key(PrismFace.RIGHT))
        assert (right, PlaneCoord.OFFSET) not in row
        assert (right, PlaneCoord.TILT_1) in row and (right, PlaneCoord.TILT_2) in row
        _assert_rows_match(row, _finite_difference_row(carriers, anchors, _v(1, 0, 0)))


class TestEdges:

    def test_an_arris_measured_to_a_parallel_face_touches_its_two_planes_and_that_face(self):
        a = _box(turn=0.3)
        b = _box(position=(4, 0, 0), turn=0.3)
        carriers = carrier_map(SolidUnion([a, b]))
        arris = _recipe(a, prism_arris_key(PrismFace.FRONT, PrismFace.RIGHT))
        face = _recipe(b, prism_face_key(PrismFace.LEFT))
        at = _np(_line(locate_recipe(arris)).point)
        normal = _np(_plane(locate_recipe(face)).normal)
        foot = _closest(locate_recipe(face), create_v3(*at))
        along = create_v3(*normal)
        anchors = [(arris, create_v3(*at), -1.0), (face, create_v3(*foot), 1.0)]

        row = _measure(carriers, anchors, along)
        assert {ref.local for ref, _ in row} <= {prism_face_key(PrismFace.FRONT), prism_face_key(PrismFace.RIGHT),
                                                 prism_face_key(PrismFace.LEFT)}
        _assert_rows_match(row, _finite_difference_row(carriers, anchors, along))

    def test_a_point_to_a_skew_edge(self):
        a = _box()
        b = _box(position=(3, 2, 1), turn=0.7)
        carriers = carrier_map(SolidUnion([a, b]))
        corner = _recipe(a, prism_corner_key(PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT))
        edge = _recipe(b, prism_arris_key(PrismFace.BOTTOM, PrismFace.LEFT))
        at = _point(corner)
        foot = _closest(locate_recipe(edge), at)
        gap = foot - _np(at)
        along = create_v3(*(gap / np.linalg.norm(gap)))
        anchors = [(edge, create_v3(*foot), 1.0), (corner, at, -1.0)]
        _assert_rows_match(_measure(carriers, anchors, along),
                           _finite_difference_row(carriers, anchors, along))


class TestMergedPlanes:
    """The tenon back face sits on the shoulder plane, facing the other way."""

    def _tenon(self):
        shoulder = HalfSpace(normal=_v(0, 0, 1), offset=scalar(0))
        tenon = _box(size=(1, 1), start=0.0, end=3.0)
        return shoulder, tenon, Difference(base=shoulder, subtract=[tenon])

    def test_a_merged_face_has_the_rows_of_the_plane_it_merged_into(self):
        shoulder, tenon, root = self._tenon()
        carriers = carrier_map(root)
        back = CarrierRef(tenon, prism_face_key(PrismFace.BOTTOM))

        assert carriers.carrier_rows(back) == carriers.carrier_rows(CarrierRef(shoulder, HALF_SPACE_PLANE))

    def test_the_tree_s_unknowns_count_merged_planes_once(self):
        _, _, root = self._tenon()
        carriers = carrier_map(root)

        # The shoulder plane and the tenon's six planes, less the back face merged into the shoulder.
        assert len(carriers.unknowns()) == 3 * 6
        assert len({column for row in carriers.unknowns() for column in row}) == 3 * 6

    def test_the_back_face_merges_with_the_shoulder(self):
        shoulder, tenon, root = self._tenon()
        carriers = carrier_map(root)
        back = CarrierRef(tenon, prism_face_key(PrismFace.BOTTOM))
        assert carriers.canonical(back) == carriers.canonical(CarrierRef(shoulder, HALF_SPACE_PLANE))

    def test_a_back_face_corner_measures_the_shoulder(self):
        shoulder, tenon, root = self._tenon()
        carriers = carrier_map(root)
        corner = _recipe(tenon, prism_corner_key(PrismFace.BOTTOM, PrismFace.RIGHT, PrismFace.FRONT))
        tip = _recipe(tenon, prism_face_key(PrismFace.TOP))
        at = _point(corner)
        anchors = [(corner, at, -1.0), (tip, _v(float(at[0, 0]), float(at[1, 0]), 3.0), 1.0)]
        along = _v(0, 0, 1)

        row = _measure(carriers, anchors, along)
        shoulder_ref = carriers.canonical(CarrierRef(tenon, prism_face_key(PrismFace.BOTTOM)))
        assert shoulder_ref.owner is shoulder
        assert (shoulder_ref, PlaneCoord.OFFSET) in row
        _assert_rows_match(row, _finite_difference_row(carriers, anchors, along))


class TestCylinders:

    def _peg(self):
        return Cylinder(axis_direction=_v(0, 1, 0), radius=scalar(0.25), position=_v(0, 0, 2),
                        start_distance=scalar(-2), end_distance=scalar(2),
                        extra_features=(CylinderAxisFeature(name="axis"),))

    def test_a_corner_to_the_peg_axis(self):
        box, peg = _box(), self._peg()
        carriers = carrier_map(Difference(base=box, subtract=[peg]))
        corner = _recipe(box, prism_corner_key(PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT))
        axis = next(f for f in peg.get_declared_features() if f.name == "axis").solve_recipe(peg)
        at = _point(corner)
        foot = _closest(locate_recipe(axis), at)
        gap = _np(at) - foot
        along = create_v3(*(gap / np.linalg.norm(gap)))
        anchors = [(corner, at, 1.0), (axis, create_v3(*foot), -1.0)]
        _assert_rows_match(_measure(carriers, anchors, along),
                           _finite_difference_row(carriers, anchors, along))

    def test_the_barrel_moves_with_its_radius(self):
        peg = self._peg()
        carriers = carrier_map(peg)
        barrel = (CarrierRef(peg, CYLINDER_BARREL),)
        row = motion_along(barrel, carriers, _v(0.25, 1, 2), _v(1, 0, 0))
        assert row[(CarrierRef(peg, CYLINDER_BARREL), BarrelCoord.RADIUS)] == pytest.approx(1.0)
        assert any(ref == CarrierRef(peg, CYLINDER_AXIS) for ref, _ in row)


class TestDerivedFeatures:

    def test_a_derived_edge_is_where_its_two_parent_faces_meet(self):
        shoulder = HalfSpace(normal=_v(0, 0, 1), offset=scalar(1))
        box = _box(turn=0.2)
        root = Difference(base=box, subtract=[shoulder])
        carriers = carrier_map(root)
        edge = DerivedEdgeFeature(
            name="shoulder x right",
            a=_hit(_feature(shoulder, HALF_SPACE_PLANE), shoulder, FaceFeature),
            b=_hit(_feature(box, prism_face_key(PrismFace.RIGHT)), box, FaceFeature))
        recipe = edge.solve_recipe(root)
        assert recipe is not None and len(recipe) == 2
        assert lines_are_coincident(_line(locate_recipe(recipe)), _line(edge.locate_simple_unbounded(root)))

        at = _line(locate_recipe(recipe)).point
        along = _v(math.cos(0.2), math.sin(0.2), 0)
        _assert_rows_match(_measure(carriers, [(recipe, at, 1.0)], along),
                           _finite_difference_row(carriers, [(recipe, at, 1.0)], along))

    def test_a_derived_point_where_the_peg_axis_crosses_a_face(self):
        box = _box()
        peg = TestCylinders()._peg()
        root = Difference(base=box, subtract=[peg])
        carriers = carrier_map(root)
        axis = next(f for f in peg.get_declared_features() if f.name == "axis")
        point = DerivedPointFeature(
            name="axis x front",
            edge=_hit(axis, peg, EdgeFeature),
            face=_hit(_feature(box, prism_face_key(PrismFace.FRONT)), box, FaceFeature))
        recipe = point.solve_recipe(root)
        assert recipe is not None and len(recipe) == 2
        at = _point(recipe)
        located = point.locate_simple_unbounded(root)
        assert isinstance(located, Point)
        assert np.allclose(_np(at), _np(located.position))

        for along in (_v(1, 0, 0), _v(0, 1, 0), _v(0, 0, 1)):
            _assert_rows_match(_measure(carriers, [(recipe, at, 1.0)], along),
                               _finite_difference_row(carriers, [(recipe, at, 1.0)], along))

    def test_a_derived_point_from_a_declared_arris_flattens_to_three_planes(self):
        box = _box()
        shoulder = HalfSpace(normal=_v(0, 0, 1), offset=scalar(1))
        root = Difference(base=box, subtract=[shoulder])
        carriers = carrier_map(root)
        point = DerivedPointFeature(
            name="arris x shoulder",
            edge=_hit(_feature(box, prism_arris_key(PrismFace.FRONT, PrismFace.RIGHT)), box, EdgeFeature),
            face=_hit(_feature(shoulder, HALF_SPACE_PLANE), shoulder, FaceFeature))
        recipe = point.solve_recipe(root)
        assert recipe is not None and len(recipe) == 3
        at = _point(recipe)
        along = _v(0, 0, 1)
        _assert_rows_match(_measure(carriers, [(recipe, at, 1.0)], along),
                           _finite_difference_row(carriers, [(recipe, at, 1.0)], along))


class TestSolvingAFace:
    """Marking the x of the right face's corners from the known left face."""

    right_corners = [
        prism_corner_key(PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT),
        prism_corner_key(PrismFace.BOTTOM, PrismFace.BACK, PrismFace.RIGHT),
        prism_corner_key(PrismFace.TOP, PrismFace.BACK, PrismFace.RIGHT),
        prism_corner_key(PrismFace.BOTTOM, PrismFace.RIGHT, PrismFace.FRONT),
    ]

    def _solve(self, box, corners, target_key=prism_face_key(PrismFace.RIGHT)):
        return self._remaining(box, corners, target_key).count

    def _remaining(self, box, corners, target_key=prism_face_key(PrismFace.RIGHT)):
        carriers = carrier_map(box)
        left = _recipe(box, prism_face_key(PrismFace.LEFT))
        along = _plane(locate_recipe(_recipe(box, prism_face_key(PrismFace.RIGHT)))).normal
        known = feature_dof_rows(left, carriers)
        for key in corners:
            corner = _recipe(box, key)
            at = _point(corner)
            foot = create_v3(*_closest(locate_recipe(left), at))
            known.append(measurement_row(DistanceMeasurement(Anchor(left, foot), Anchor(corner, at), along), carriers))
        return remaining(known, feature_dof_rows(_recipe(box, target_key), carriers))

    @pytest.mark.parametrize("box", [_box(), _box(turn=0.6, position=(1, -2, 0))])
    def test_four_corners_solve_the_face_with_one_to_spare(self, box):
        assert self._solve(box, self.right_corners) == 0
        assert self._solve(box, self.right_corners[:3]) == 0

    def test_two_corners_leave_a_rotation_about_the_line_through_them(self):
        box = _box()
        result = self._remaining(box, self.right_corners[:2])
        assert result.count == 1
        (motion,) = result.free_motions

        right = CarrierRef(box, prism_face_key(PrismFace.RIGHT))
        assert {ref for ref, _ in motion} == {right}
        step = 1e-6
        moved = moved_by(right.carrier(), {coord: step * amount for (_, coord), amount in motion.items()})

        def x_change(key):
            recipe = _recipe(box, key)
            before = _point(recipe)
            after = locate_recipe(recipe, lambda ref: moved if ref == right else ref.carrier())
            assert isinstance(after, Point)
            return (float(after.position[0, 0]) - float(before[0, 0])) / step

        measured, unmeasured = self.right_corners[:2], self.right_corners[2:]
        assert all(x_change(key) == pytest.approx(0.0, abs=1e-4) for key in measured)
        assert all(abs(x_change(key)) > 1e-2 for key in unmeasured)

    def test_fewer_corners_leave_tilts(self):
        box = _box()
        assert self._solve(box, []) == 3
        assert self._solve(box, self.right_corners[:1]) == 2
        assert self._solve(box, self.right_corners[:2]) == 1

    def test_one_corner_solves_only_its_x(self):
        box = _box()
        corner = self.right_corners[0]
        # The corner's y and z belong to the front and top faces, which nothing measured.
        assert self._solve(box, [corner], target_key=corner) == 2

    def test_an_arris_is_solved_by_its_two_faces(self):
        box = _box(turn=0.3)
        carriers = carrier_map(box)
        arris = _recipe(box, prism_arris_key(PrismFace.FRONT, PrismFace.RIGHT))
        faces = [_recipe(box, prism_face_key(face)) for face in (PrismFace.FRONT, PrismFace.RIGHT)]
        assert remaining([], feature_dof_rows(arris, carriers)).count == 4
        assert remaining(feature_dof_rows(faces[0], carriers), feature_dof_rows(arris, carriers)).count == 2
        assert remaining(sum((feature_dof_rows(f, carriers) for f in faces), []), feature_dof_rows(arris, carriers)).count == 0


class TestDirectionMotion:
    """How a feature's direction moves: a face's normal, an edge's direction."""

    @pytest.mark.parametrize("key", [prism_face_key(PrismFace.RIGHT),
                                     prism_arris_key(PrismFace.FRONT, PrismFace.RIGHT)])
    def test_matches_finite_differences(self, key):
        box = _box(turn=0.4, position=(1, 2, 3))
        carriers = carrier_map(box)
        recipe = _recipe(box, key)
        direction, change = direction_motion(recipe, carriers)

        def located_direction(carrier_of):
            located = locate_recipe(recipe, carrier_of)
            raw = located.normal if isinstance(located, Plane) else _line(located).direction
            return _np(raw) / np.linalg.norm(_np(raw))

        assert np.allclose(located_direction(CarrierRef.carrier), direction)
        step = 1e-6
        for solving in carriers.solving_carriers():
            for coord in type(carriers.carrier(solving)).COORDS:
                moved = perturbed(carriers.carrier(solving), coord, step)
                after = located_direction(lambda ref: moved if carriers.canonical(ref) == solving else carriers.carrier(ref))
                expected = (after - direction) / step
                actual = [component.get((solving, coord), 0.0) for component in change]
                assert np.allclose(actual, expected, atol=1e-4), (solving.local, coord)

    def test_a_point_has_none(self):
        box = _box()
        with pytest.raises(ValueError):
            direction_motion(_recipe(box, prism_corner_key(PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT)),
                             carrier_map(box))
