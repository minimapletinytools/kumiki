"""Measures on a real cut timber, as rows and remaining DOFs (kumiki/feature_solving.py)."""

import pytest

from kumiki.cutcsg import OwnedFeatureHit, PrismFace, prism_corner_key, prism_face_key
from kumiki.drawing import Measure, MeasurementKind, ViewAxes
from kumiki.feature_paths import FeatureHandle
from kumiki.feature_solving import carrier_map_of, measure_row, remaining_dofs
from kumiki.rule import create_v3
from kumiki.solve_recipe import CarrierRef, PlaneCoord
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

    def test_an_angle_is_not_supported_yet(self, handles):
        frame, found = handles
        carriers = carrier_map_of(_cut_timber(frame, found["tenon_top"]))

        with pytest.raises(NotImplementedError):
            measure_row(Measure(found["tenon_top"], found["tenon_left"], kind=MeasurementKind.parse("angle")),
                        carriers)

    def test_a_measurement_between_two_timbers_is_not_supported_yet(self, handles):
        frame, found = handles
        carriers = carrier_map_of(_cut_timber(frame, found["tenon_top"]))

        with pytest.raises(NotImplementedError):
            measure_row(Measure(found["tenon_top"], found["mortise_bottom"]), carriers)
