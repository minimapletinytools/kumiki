"""Measures on a real cut timber, as rows and remaining DOFs (kumiki/drawings/feature_solving.py)."""

import numpy as np
import pytest

from kumiki.csg.cutcsg import OwnedFeatureHit, PrismFace, prism_corner_key, prism_face_key
from kumiki.drawings.drawing import Measure, MeasurementKind, ViewAxes
from kumiki.csg.feature_paths import FeatureHandle, find_feature
from kumiki.drawings.feature_solving import carrier_map_of, measure_row, remaining_dofs, solve_report
from kumiki.rule import create_v3
from kumiki.csg.carriers import CarrierRef, PlaneCoord
from tests.testing_shavings import mortise_and_tenon_handles, present


@pytest.fixture(scope="module")
def handles():
    return mortise_and_tenon_handles()


def _cut_timber(frame, handle):
    return present(frame.cut_timber_of(handle.timber), "the handle's cut timber")


def _tenon(found, *faces):
    """A default feature of the tenon prism, named by the faces that make it."""
    node = found["tenon_top"].owner
    key = prism_face_key(faces[0]) if len(faces) == 1 else prism_corner_key(*faces)
    feature = next(f for f in node.get_declared_features() if f.feature_key() == key)
    return FeatureHandle(timber=found["tenon_top"].timber, hit=OwnedFeatureHit(feature=feature, owner=node))


RIGHT_CORNERS = [
    (PrismFace.TOP, PrismFace.RIGHT, PrismFace.FRONT),
    (PrismFace.BOTTOM, PrismFace.BACK, PrismFace.RIGHT),
    (PrismFace.TOP, PrismFace.BACK, PrismFace.RIGHT),
    (PrismFace.BOTTOM, PrismFace.RIGHT, PrismFace.FRONT),
]


class TestAMeasureSolvesWhatItMeasures:

    def test_the_tenon_length_fixes_the_tip_offset_and_leaves_its_tilts(self, handles):
        frame, found = handles
        length = Measure(found["shoulder"], found["tenon_top"])
        cut_timber = _cut_timber(frame, found["shoulder"])

        assert remaining_dofs(found["tenon_top"], [], [found["shoulder"]], cut_timber).count == 3
        assert remaining_dofs(found["tenon_top"], [length], [found["shoulder"]], cut_timber).count == 2

    def test_without_the_shoulder_known_the_length_alone_solves_nothing(self, handles):
        frame, found = handles
        length = Measure(found["shoulder"], found["tenon_top"])

        assert remaining_dofs(found["tenon_top"], [length], [], _cut_timber(frame, found["shoulder"])).count == 3


class TestMarkingTheCornersOfAFace:
    """Your example, on a real tenon: the right face's corners measured from the known left face."""

    def _remaining(self, handles, corners):
        frame, found = handles
        left, right = _tenon(found, PrismFace.LEFT), _tenon(found, PrismFace.RIGHT)
        measures = [Measure(left, _tenon(found, *corner)) for corner in corners]
        return remaining_dofs(right, measures, [left], _cut_timber(frame, left)).count

    def test_four_corners_solve_the_face_with_one_to_spare(self, handles):
        assert self._remaining(handles, RIGHT_CORNERS) == 0
        assert self._remaining(handles, RIGHT_CORNERS[:3]) == 0

    def test_fewer_corners_leave_tilts(self, handles):
        assert self._remaining(handles, []) == 3
        assert self._remaining(handles, RIGHT_CORNERS[:1]) == 2
        assert self._remaining(handles, RIGHT_CORNERS[:2]) == 1


class TestRows:

    def test_a_back_face_corner_lands_on_the_shoulder(self, handles):
        # The tenon's back cap lies on the shoulder plane, so they share columns.
        frame, found = handles
        carriers = carrier_map_of(_cut_timber(frame, found["shoulder"]))
        corner = _tenon(found, PrismFace.BOTTOM, PrismFace.RIGHT, PrismFace.FRONT)

        row = measure_row(Measure(found["tenon_top"], corner), carriers)

        shoulder_key = present(found["shoulder"].feature.feature_key(), "the shoulder's key")
        shoulder = carriers.canonical(CarrierRef(found["shoulder"].owner, shoulder_key))
        assert (shoulder, PlaneCoord.OFFSET) in row

    def test_a_horizontal_distance_between_two_points_reads_along_the_view(self, handles):
        frame, found = handles
        carriers = carrier_map_of(_cut_timber(frame, found["tenon_top"]))
        a = _tenon(found, *RIGHT_CORNERS[0])
        b = _tenon(found, PrismFace.TOP, PrismFace.LEFT, PrismFace.BACK)
        view = ViewAxes(look=create_v3(0, 0, -1), right=create_v3(1, 0, 0), up=create_v3(0, 1, 0))

        across = measure_row(Measure(a, b, kind=MeasurementKind.parse("projected_horizontal_distance")),
                             carriers, view)
        up = measure_row(Measure(a, b, kind=MeasurementKind.parse("projected_vertical_distance")),
                         carriers, view)

        assert across and up and across != up

    def test_a_measurement_between_coincident_features_is_refused(self, handles):
        # The tenon's tip sits flush with the through mortise's opening.
        frame, found = handles
        carriers = carrier_map_of(*frame.cut_timbers)

        with pytest.raises(ValueError):
            measure_row(Measure(found["tenon_top"], found["mortise_bottom"]), carriers)


def _world_normal(handle):
    from kumiki.geometry import Plane

    plane = handle.feature.locate_simple_unbounded(handle.owner)
    assert isinstance(plane, Plane)
    rotation = handle.timber.transform.orientation.matrix
    return np.array([float((rotation * plane.normal)[i, 0]) for i in range(3)])


def _view(look):
    look = look / np.linalg.norm(look)
    right = np.cross(look, [0.0, 0.0, 1.0] if abs(look[2]) < 0.9 else [1.0, 0.0, 0.0])
    right = right / np.linalg.norm(right)
    return ViewAxes(look=create_v3(*look), right=create_v3(*right), up=create_v3(*np.cross(right, look)))


class TestAngles:

    def test_an_angle_fixes_one_tilt(self, handles):
        frame, found = handles
        butt = _cut_timber(frame, found["tenon_top"])
        angle = Measure(found["tenon_top"], found["tenon_left"], kind=MeasurementKind.parse("angle"))

        assert remaining_dofs(found["tenon_left"], [], [found["tenon_top"]], butt).count == 3
        assert remaining_dofs(found["tenon_left"], [angle], [found["tenon_top"]], butt).count == 2

    def test_an_angle_between_parallel_faces_fixes_nothing(self, handles):
        frame, found = handles
        butt = _cut_timber(frame, found["tenon_top"])
        angle = Measure(found["tenon_left"], found["tenon_right"], kind=MeasurementKind.parse("angle"))

        assert remaining_dofs(found["tenon_right"], [angle], [found["tenon_left"]], butt).count == 3

    def test_on_a_sheet_seeing_both_faces_edge_on_it_is_the_3d_angle(self, handles):
        frame, found = handles
        carriers = carrier_map_of(_cut_timber(frame, found["tenon_top"]))
        top, left = found["tenon_top"], found["tenon_left"]
        view = _view(np.cross(_world_normal(top), _world_normal(left)))

        solid = measure_row(Measure(top, left, kind=MeasurementKind.parse("angle")), carriers)
        sheet = measure_row(Measure(top, left, kind=MeasurementKind.parse("projected_angle")), carriers, view)

        assert solid.keys() == sheet.keys()
        assert all(solid[key] == pytest.approx(sheet[key]) for key in solid)


class TestSheetDistances:

    def test_parallel_faces_edge_on_measure_like_3d(self, handles):
        frame, found = handles
        butt = _cut_timber(frame, found["tenon_left"])
        carriers = carrier_map_of(butt)
        left, right = found["tenon_left"], found["tenon_right"]
        view = _view(np.cross(_world_normal(left), [0.3, 0.5, 0.8]))

        solid = measure_row(Measure(left, right), carriers)
        sheet = measure_row(Measure(left, right, kind=MeasurementKind.parse("projected_perpendicular_distance")),
                            carriers, view)

        assert solid.keys() == sheet.keys()
        assert all(solid[key] == pytest.approx(sheet[key]) for key in solid)
        assert remaining_dofs(right, [Measure(left, right, kind=MeasurementKind.parse(
            "projected_perpendicular_distance"))], [left], butt, view).count == 2

    def test_a_face_seen_at_an_angle_is_refused(self, handles):
        frame, found = handles
        carriers = carrier_map_of(_cut_timber(frame, found["tenon_left"]))
        left, right = found["tenon_left"], found["tenon_right"]

        with pytest.raises(ValueError):
            measure_row(Measure(left, right, kind=MeasurementKind.parse("projected_perpendicular_distance")),
                        carriers, _view(_world_normal(left)))


class TestBetweenTwoTimbers:

    def _across(self, frame, found):
        """A face of the mortised timber parallel to the butt timber's shoulder, and not on it."""
        receiving = _cut_timber(frame, found["mortise_front"])
        shoulder_normal = _world_normal(found["shoulder"])
        for name in ("front", "back", "left", "right", "top", "bottom"):
            face = present(find_feature(receiving, BODY, f"rough.{name}"), name)
            if abs(abs(float(_world_normal(face) @ shoulder_normal)) - 1) < 1e-9:
                try:
                    measure_row(Measure(face, found["shoulder"]), carrier_map_of(*frame.cut_timbers))
                    return face
                except ValueError:
                    continue
        raise AssertionError("no face of the mortised timber faces the shoulder from a distance")

    def test_a_measurement_from_the_other_timber_fixes_the_shoulder(self, handles):
        frame, found = handles
        butt = _cut_timber(frame, found["shoulder"])
        face = self._across(frame, found)
        across = Measure(face, found["shoulder"])

        assert remaining_dofs(found["shoulder"], [], [face], butt, frame=frame).count == 3
        assert remaining_dofs(found["shoulder"], [across], [face], butt, frame=frame).count == 2

    def test_the_row_spans_both_timbers(self, handles):
        frame, found = handles
        face = self._across(frame, found)
        row = measure_row(Measure(face, found["shoulder"]), carrier_map_of(*frame.cut_timbers))

        owners = {id(ref.owner) for ref, _ in row}
        assert id(face.owner) in owners and id(found["shoulder"].owner) in owners

    def test_without_the_frame_it_says_so(self, handles):
        frame, found = handles
        face = self._across(frame, found)

        with pytest.raises(ValueError, match="frame"):
            remaining_dofs(found["shoulder"], [Measure(face, found["shoulder"])], [face],
                           _cut_timber(frame, found["shoulder"]))

BODY = ("timber (rough, extended)",)


class TestSolveReport:
    """Every required feature of a timber, with its body faces known."""

    def _body(self, cut_timber, *faces):
        return [present(find_feature(cut_timber, BODY, f"rough.{face}"), face) for face in faces]

    def _butt(self, handles):
        frame, found = handles
        butt = _cut_timber(frame, found["shoulder"])
        return butt, found, self._body(butt, "front", "back", "left", "right", "bottom")

    def test_the_tenon_s_six_planes_are_what_is_left(self, handles):
        butt, _, known = self._butt(handles)

        report = solve_report(butt, [], known)
        counts = {r.required.handle.feature.name: present(r.remaining).count for r in report.features}

        assert report.total.count == 6 * 3
        assert all(counts[f"rough.{face}"] == 0 for face in ("front", "back", "left", "right", "bottom"))
        assert all(counts[name] == 3 for name in ("shoulder", "tenon_top", "tenon_left", "tenon_right"))

    def test_measurements_take_off_what_they_fix(self, handles):
        butt, found, known = self._butt(handles)
        shoulder_from_end = Measure(known[-1], found["shoulder"])
        tenon_length = Measure(found["shoulder"], found["tenon_top"])

        report = solve_report(butt, [shoulder_from_end, tenon_length], known)
        counts = {r.required.handle.feature.name: present(r.remaining).count for r in report.features}

        assert report.total.count == 6 * 3 - 2
        assert counts["shoulder"] == 2 and counts["tenon_top"] == 2

    def test_the_mortise_walls_are_what_is_left(self, handles):
        frame, found = handles
        receiving = _cut_timber(frame, found["mortise_front"])
        known = self._body(receiving, "front", "back", "left", "right", "bottom", "top")

        assert solve_report(receiving, [], known).total.count == 4 * 3

    def test_a_required_feature_with_no_recipe_reports_none(self):
        from kumiki.construction import create_timber
        from kumiki.csg.cutcsg import CutCSGLabel, ProgrammableEdgeFeature, RectangularPrism
        from kumiki.rule import Transform, create_v2, mm, scalar
        from kumiki.timber import CutTimber, Cutting

        timber = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                               length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="t")
        notch = RectangularPrism(size=create_v2(0.02, 0.02), transform=Transform.identity(),
                                 start_distance=scalar(0.4), end_distance=scalar(0.6), label=CutCSGLabel("notch"),
                                 extra_features=(ProgrammableEdgeFeature(name="mark"),))
        cut_timber = CutTimber(timber, cuts=[Cutting(timber=timber, negative_csg=notch)])

        report = solve_report(cut_timber, [], [])
        mark = next(r for r in report.features if r.required.handle.feature.name == "mark")

        assert mark.remaining is None
