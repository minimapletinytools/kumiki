"""The plane a measurement is taken and drawn on.

Its own property rather than the viewport's, because the 3D view's camera
orbits: a measurement evaluated against whatever the camera happens to be doing
reads a different number from one moment to the next. See
docs/measurement-spec.md.

The rules, in priority order: the plane contains any point being measured, is
perpendicular to any face, is parallel to any edge, and of whatever is left
faces the camera as squarely as it can.
"""

import importlib.util
import math
import sys
from pathlib import Path

import pytest

from kumiki.drawing import MeasurementPlane


def _load_runner():
    runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
    spec = importlib.util.spec_from_file_location("kigumi_runner_plane", runner_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_plane"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()

# Looking along +Y, so the plane a dimension is most readable on has a Y normal.
LOOK = [0.0, 1.0, 0.0]


def face(normal, at=(0, 0, 0)):
    return {"kind": "plane", "normal": list(normal), "at": list(at)}


def edge(direction, at=(0, 0, 0)):
    return {"kind": "line", "direction": list(direction), "at": list(at)}


def point(at):
    return {"kind": "point", "at": list(at)}


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def square(normal, direction):
    """Whether a plane with this normal is square to this direction."""
    return abs(dot(normal, direction)) == pytest.approx(0, abs=1e-9)


class TestWhichWayThePlaneFaces:

    def test_two_faces_give_a_plane_perpendicular_to_both(self):
        plane = runner._measurement_plane(
            face([1, 0, 0]), face([0, 0, 1]), [0, 0, 0], [1, 0, 1], LOOK)

        assert square(plane["normal"], [1, 0, 0])
        assert square(plane["normal"], [0, 0, 1])

    def test_two_parallel_faces_leave_a_choice_and_it_faces_the_camera(self):
        # Square to the shared normal is a whole family of planes. The one
        # worth drawing on is the one most nearly face-on to the reader.
        plane = runner._measurement_plane(
            face([1, 0, 0]), face([1, 0, 0]), [0, 0, 0], [2, 0, 0], LOOK)

        assert square(plane["normal"], [1, 0, 0])
        assert plane["normal"] == pytest.approx(LOOK, abs=1e-9)

    def test_an_edge_is_contained_rather_than_crossed(self):
        plane = runner._measurement_plane(
            edge([0, 0, 1]), face([1, 0, 0]), [0, 0, 0], [1, 0, 0], LOOK)

        assert square(plane["normal"], [0, 0, 1])
        assert square(plane["normal"], [1, 0, 0])

    def test_two_skew_edges_are_satisfiable_and_not_a_fallback(self):
        # Parallel to both directions, which two directions always admit --
        # the plane need not contain either line, only run the same way.
        plane = runner._measurement_plane(
            edge([1, 0, 0]), edge([0, 0, 1]), [0, 0, 0], [1, 1, 1], LOOK)

        assert square(plane["normal"], [1, 0, 0])
        assert square(plane["normal"], [0, 0, 1])

    def test_two_points_give_a_plane_containing_the_line_between_them(self):
        plane = runner._measurement_plane(
            point([0, 0, 0]), point([1, 0, 1]), [0, 0, 0], [1, 0, 1], LOOK)

        assert square(plane["normal"], [1, 0, 1])

    def test_nothing_to_be_square_to_means_face_the_camera(self):
        plane = runner._measurement_plane(
            {"kind": None}, {"kind": None}, [0, 0, 0], [2, 0, 0], LOOK)

        assert plane["normal"] == pytest.approx(LOOK, abs=1e-9)

    def test_looking_straight_down_the_one_constraint_still_answers(self):
        # Every plane containing it is equally edge-on, so there is no best
        # one -- but there is still an answer, and returning none would lose a
        # measurement over a camera angle.
        plane = runner._measurement_plane(
            edge([0, 1, 0]), edge([0, 1, 0]), [0, 0, 0], [1, 0, 0], LOOK)

        assert square(plane["normal"], [0, 1, 0])
        assert dot(plane["normal"], plane["normal"]) == pytest.approx(1, abs=1e-9)

    def test_the_normal_is_turned_to_face_the_camera(self):
        # A plane has no front. Both answers are the same plane; the one that
        # faces the reader is the one to write down.
        plane = runner._measurement_plane(
            face([1, 0, 0]), face([0, 0, 1]), [0, 0, 0], [1, 0, 1], [0, -1, 0])

        assert dot(plane["normal"], [0, -1, 0]) > 0


class TestWhereThePlaneSits:

    def test_it_passes_through_a_measured_point(self):
        # It has to: a plane that does not contain the point cannot be the
        # plane that point is measured on.
        plane = runner._measurement_plane(
            point([3, 0, 4]), face([1, 0, 0]), [3, 0, 4], [9, 0, 9], LOOK)

        assert plane["at"] == pytest.approx([3, 0, 4])

    def test_otherwise_it_sits_midway_between_the_anchors(self):
        # Among what it measures rather than off to one side of it.
        plane = runner._measurement_plane(
            face([1, 0, 0]), face([0, 0, 1]), [0, 0, 0], [4, 0, 2], LOOK)

        assert plane["at"] == pytest.approx([2, 0, 1])


class TestTheDerivedPlaneIsOneTheModelAccepts:

    def test_it_round_trips_through_the_wire_form(self):
        derived = runner._measurement_plane(
            face([1, 0, 0]), edge([0, 0, 1]), [0, 0, 0], [1, 0, 1], LOOK)

        built = MeasurementPlane.from_wire(derived)

        assert built.at == pytest.approx(derived["at"])
        assert built.normal == pytest.approx(derived["normal"])
        assert built.as_wire() == derived

    def test_a_normal_is_always_unit_length(self):
        # Because it is compared against a viewport's by angle, and a
        # comparison against something of unknown length is not one.
        for one, other in [
            (face([2, 0, 0]), face([0, 0, 5])),
            (edge([0, 3, 0]), point([1, 1, 1])),
            ({"kind": None}, {"kind": None}),
        ]:
            plane = runner._measurement_plane(one, other, [0, 0, 0], [1, 1, 1], LOOK)
            length = math.sqrt(sum(part * part for part in plane["normal"]))

            assert length == pytest.approx(1, abs=1e-9)
