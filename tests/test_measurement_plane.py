"""The plane a measurement is taken and drawn on.

Its own property rather than the viewport's, because the 3D view's camera
orbits: a measurement evaluated against whatever the camera happens to be doing
reads a different number from one moment to the next. See
.claude/plans/measurement-spec.md.

The rules, in priority order: the plane contains any point being measured, is
perpendicular to any face, is parallel to any edge, and of whatever is left
faces the camera as squarely as it can.
"""

import math
from pathlib import Path

import pytest

from tests.testing_shavings import load_module

from kumiki.drawings import kigumi_measuring_helpers as measuring
from kumiki.drawings.measure import MeasurementPlane
from kumiki.geometry import Line, Plane, Point
from kumiki.rule import create_v3


def _load_runner():
    runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
    module = load_module("kigumi_runner_plane", runner_path)
    return module


runner = _load_runner()

# Looking along +Y, so the plane a dimension is most readable on has a Y normal.
LOOK = [0.0, 1.0, 0.0]


def face(normal, at=(0, 0, 0)):
    return Plane(normal=create_v3(*normal), point=create_v3(*at))


def edge(direction, at=(0, 0, 0)):
    return Line(direction=create_v3(*direction), point=create_v3(*at))


def point(at):
    return Point(position=create_v3(*at))


def measurement_plane(*args, **kwargs):
    """measuring.measurement_plane, in the form a file or the wire holds it."""
    return measuring.measurement_plane(*args, **kwargs).as_wire()


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def square(normal, direction):
    """Whether a plane with this normal is square to this direction."""
    return abs(dot(normal, direction)) == pytest.approx(0, abs=1e-9)


class TestWhichWayThePlaneFaces:

    def test_two_faces_give_a_plane_perpendicular_to_both(self):
        plane = measurement_plane(
            face([1, 0, 0]), face([0, 0, 1]), [0, 0, 0], [1, 0, 1], LOOK)

        assert square(plane["normal"], [1, 0, 0])
        assert square(plane["normal"], [0, 0, 1])

    def test_two_parallel_faces_leave_a_choice_and_it_faces_the_camera(self):
        # Square to the shared normal is a whole family of planes. The one
        # worth drawing on is the one most nearly face-on to the reader.
        plane = measurement_plane(
            face([1, 0, 0]), face([1, 0, 0]), [0, 0, 0], [2, 0, 0], LOOK)

        assert square(plane["normal"], [1, 0, 0])
        assert plane["normal"] == pytest.approx(LOOK, abs=1e-9)

    def test_an_edge_is_contained_rather_than_crossed(self):
        plane = measurement_plane(
            edge([0, 0, 1]), face([1, 0, 0]), [0, 0, 0], [1, 0, 0], LOOK)

        assert square(plane["normal"], [0, 0, 1])
        assert square(plane["normal"], [1, 0, 0])

    def test_two_skew_edges_are_satisfiable_and_not_a_fallback(self):
        # Parallel to both directions, which two directions always admit --
        # the plane need not contain either line, only run the same way.
        plane = measurement_plane(
            edge([1, 0, 0]), edge([0, 0, 1]), [0, 0, 0], [1, 1, 1], LOOK)

        assert square(plane["normal"], [1, 0, 0])
        assert square(plane["normal"], [0, 0, 1])

    def test_two_points_give_a_plane_containing_the_line_between_them(self):
        plane = measurement_plane(
            point([0, 0, 0]), point([1, 0, 1]), [0, 0, 0], [1, 0, 1], LOOK)

        assert square(plane["normal"], [1, 0, 1])

    def test_in_a_drawing_s_view_the_plane_is_the_view_s_whatever_is_measured(self):
        # The features are projected onto the sheet: an edge running into it must not tilt the
        # plane, or the measurement refuses the very view it was made in.
        tilted = [0, 0.17, 0.98]
        plane = measurement_plane(
            edge(tilted), edge([1, 0, 0.2]), [0, 0, 0], [1, 0, 1], LOOK, in_view_plane=True)

        assert plane["normal"] == pytest.approx(LOOK, abs=1e-9)

    def test_nothing_to_be_square_to_means_face_the_camera(self):
        plane = measurement_plane(
            None, None, [0, 0, 0], [2, 0, 0], LOOK)

        assert plane["normal"] == pytest.approx(LOOK, abs=1e-9)

    def test_looking_straight_down_the_one_constraint_still_answers(self):
        # Every plane containing it is equally edge-on, so there is no best
        # one -- but there is still an answer, and returning none would lose a
        # measurement over a camera angle.
        plane = measurement_plane(
            edge([0, 1, 0]), edge([0, 1, 0]), [0, 0, 0], [1, 0, 0], LOOK)

        assert square(plane["normal"], [0, 1, 0])
        assert dot(plane["normal"], plane["normal"]) == pytest.approx(1, abs=1e-9)

    def test_the_normal_is_turned_to_face_the_camera(self):
        # A plane has no front. Both answers are the same plane; the one that
        # faces the reader is the one to write down.
        plane = measurement_plane(
            face([1, 0, 0]), face([0, 0, 1]), [0, 0, 0], [1, 0, 1], [0, -1, 0])

        assert dot(plane["normal"], [0, -1, 0]) > 0


class TestWhereThePlaneSits:

    def test_it_passes_through_a_measured_point(self):
        # It has to: a plane that does not contain the point cannot be the
        # plane that point is measured on.
        plane = measurement_plane(
            point([3, 0, 4]), face([1, 0, 0]), [3, 0, 4], [9, 0, 9], LOOK)

        assert plane["at"] == pytest.approx([3, 0, 4])

    def test_otherwise_it_sits_midway_between_the_anchors(self):
        # Among what it measures rather than off to one side of it.
        plane = measurement_plane(
            face([1, 0, 0]), face([0, 0, 1]), [0, 0, 0], [4, 0, 2], LOOK)

        assert plane["at"] == pytest.approx([2, 0, 1])


class TestTheDerivedPlaneIsOneTheModelAccepts:

    def test_it_round_trips_through_the_wire_form(self):
        derived = measurement_plane(
            face([1, 0, 0]), edge([0, 0, 1]), [0, 0, 0], [1, 0, 1], LOOK)

        built = MeasurementPlane.from_wire(derived)
        assert isinstance(built, MeasurementPlane)

        assert built.at == pytest.approx(derived["at"])
        assert built.normal == pytest.approx(derived["normal"])
        assert built.as_wire() == derived

    def test_a_normal_is_always_unit_length(self):
        # Because it is compared against a viewport's by angle, and a
        # comparison against something of unknown length is not one.
        for one, other in [
            (face([2, 0, 0]), face([0, 0, 5])),
            (edge([0, 3, 0]), point([1, 1, 1])),
            (None, None),
        ]:
            plane = measurement_plane(one, other, [0, 0, 0], [1, 1, 1], LOOK)
            length = math.sqrt(sum(part * part for part in plane["normal"]))

            assert length == pytest.approx(1, abs=1e-9)


class TestAMeasurementLiesOnItsViewsPlane:
    SCENES = [{"id": "beam", "viewports": [
        {"id": "front", "projection": "orthographic", "camera": {"look": [0.0, -1.0, 0.0]}},
        {"id": "preview", "projection": "perspective", "camera": {"look": [0.0, -1.0, 0.0]}},
    ]}]

    def test_one_on_the_view_s_plane_is_written(self):
        runner._check_plane_matches_view(self.SCENES, "beam", "front", {"normal": [0.0, 1.0, 0.0]})

    def test_one_tilted_off_it_is_refused(self):
        with pytest.raises(ValueError, match="view's plane"):
            runner._check_plane_matches_view(self.SCENES, "beam", "front", {"normal": [0.0, -0.986, -0.167]})

    def test_a_perspective_view_checks_nothing(self):
        runner._check_plane_matches_view(self.SCENES, "beam", "preview", {"normal": [0.0, -0.986, -0.167]})
