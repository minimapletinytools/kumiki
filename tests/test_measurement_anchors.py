"""Where a distance attaches, at both ends.

A property of the PAIR and the plane rather than of either feature alone. An
anchor chosen per feature cannot know where the sensible attachment point is for
a given pair: two parallel edges each anchoring at their own midpoint gave a
dimension that leaned whenever those midpoints were offset along their length,
and a number beside it that was neither its length nor its direction.

See docs/measurement-spec.md.
"""

import pytest

from kumiki.drawing import (MeasureSpan, MeasurementDirection, MeasurementKind,
                            MeasurementOperation, MeasurementSpace, distance_anchors)


def kind(direction):
    return MeasurementKind(
        MeasurementOperation.DISTANCE, MeasurementSpace.PROJECTED, direction)


PERPENDICULAR = kind(MeasurementDirection.PERPENDICULAR)
HORIZONTAL = kind(MeasurementDirection.HORIZONTAL)
VERTICAL = kind(MeasurementDirection.VERTICAL)

#: A sheet whose across is X and whose up is Z, seen down Y.
AXES = {"right": (1, 0, 0), "up": (0, 0, 1), "look": (0, 1, 0)}


def line(at, direction, interval):
    return MeasureSpan(at=at, direction=direction, interval=interval)


def point(at):
    return MeasureSpan(at=at)


def run(anchors):
    one, other = anchors
    return tuple(other[i] - one[i] for i in range(3))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class TestTwoParallelLines:
    """Both ends at one station, which is what makes the line square to both."""

    def test_the_dimension_is_square_to_the_features(self):
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 10)),
            line((0, 0, 4), (1, 0, 0), (6, 20)),
            PERPENDICULAR,
        )

        assert dot(run(anchors), (1, 0, 0)) == pytest.approx(0)

    def test_and_its_length_is_the_distance_between_them(self):
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 10)),
            line((0, 0, 4), (1, 0, 0), (6, 20)),
            PERPENDICULAR,
        )

        assert abs(run(anchors)[2]) == pytest.approx(4)

    def test_it_lands_in_the_middle_of_where_they_face_each_other(self):
        # Extents 0..10 and 6..20 overlap over 6..10, so the middle is 8.
        # Anywhere in the overlap would be square; the middle is where the two
        # features are most obviously about each other.
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 10)),
            line((0, 0, 4), (1, 0, 0), (6, 20)),
            PERPENDICULAR,
        )

        assert anchors[0][0] == pytest.approx(8)
        assert anchors[1][0] == pytest.approx(8)

    def test_touching_at_one_end_counts_as_overlapping(self):
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 10)),
            line((0, 0, 4), (1, 0, 0), (10, 20)),
            PERPENDICULAR,
        )

        assert anchors[0][0] == pytest.approx(10)

    def test_where_they_do_not_overlap_it_goes_to_the_end_of_the_first(self):
        # There is no station where both are present, so there is no square
        # place between them. The end of the first nearest the second is the
        # closest thing to one.
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 5)),
            line((0, 0, 4), (1, 0, 0), (10, 20)),
            PERPENDICULAR,
        )

        assert anchors[0][0] == pytest.approx(5)
        assert anchors[1][0] == pytest.approx(5)

    def test_and_to_the_other_end_when_the_second_is_behind_it(self):
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (10, 20)),
            line((0, 0, 4), (1, 0, 0), (0, 5)),
            PERPENDICULAR,
        )

        assert anchors[0][0] == pytest.approx(10)

    def test_it_is_still_square_when_they_do_not_overlap(self):
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 5)),
            line((0, 0, 4), (1, 0, 0), (10, 20)),
            PERPENDICULAR,
        )

        assert dot(run(anchors), (1, 0, 0)) == pytest.approx(0)

    def test_a_feature_pointing_the_other_way_is_the_same_feature(self):
        # A line's direction has no preferred sense, so the pair can arrive
        # antiparallel. Reading the extents off the ends rather than off the
        # interval is what keeps that from mattering.
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 10)),
            line((0, 0, 4), (-1, 0, 0), (-20, -6)),
            PERPENDICULAR,
        )

        assert dot(run(anchors), (1, 0, 0)) == pytest.approx(0)
        assert anchors[0][0] == pytest.approx(8)


class TestAPointAndALine:
    """The point does not move: it is the whole of what is measured from."""

    def test_the_other_end_is_the_foot_of_the_perpendicular(self):
        anchors = distance_anchors(
            point((3, 0, 7)), line((0, 0, 0), (1, 0, 0), (0, 10)), PERPENDICULAR)

        assert anchors[0] == (3, 0, 7)
        assert anchors[1] == pytest.approx((3, 0, 0))

    def test_whichever_way_round_the_pair_arrives(self):
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 10)), point((3, 0, 7)), PERPENDICULAR)

        assert anchors[0] == pytest.approx((3, 0, 0))
        assert anchors[1] == (3, 0, 7)

    def test_a_foot_past_the_end_is_brought_back_onto_the_feature(self):
        # A dimension whose end floats off the end of a short edge points at
        # nothing. The nearest place on the feature is the honest answer.
        anchors = distance_anchors(
            point((99, 0, 7)), line((0, 0, 0), (1, 0, 0), (0, 10)), PERPENDICULAR)

        assert anchors[1] == pytest.approx((10, 0, 0))

    def test_and_at_the_other_end_too(self):
        anchors = distance_anchors(
            point((-99, 0, 7)), line((0, 0, 0), (1, 0, 0), (4, 10)), PERPENDICULAR)

        assert anchors[1] == pytest.approx((4, 0, 0))


class TestTwoPoints:

    def test_they_are_their_own_anchors(self):
        # With no line to be square to, the distance between them is the
        # distance, and there is nowhere else for the ends to be.
        anchors = distance_anchors(point((1, 2, 3)), point((4, 5, 6)), PERPENDICULAR)

        assert anchors == ((1, 2, 3), (4, 5, 6))


class TestAlongTheSheetsOwnDirections:
    """Horizontal and vertical: the first stays, the second comes to its axis."""

    def test_horizontal_runs_across_the_sheet(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), HORIZONTAL, AXES)

        assert anchors[0] == (0, 0, 0)
        assert anchors[1] == pytest.approx((4, 0, 0))

    def test_and_reads_the_separation_across_it(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), HORIZONTAL, AXES)
        span = run(anchors)

        assert dot(span, AXES["up"]) == pytest.approx(0)
        assert abs(dot(span, AXES["right"])) == pytest.approx(4)

    def test_vertical_runs_up_the_sheet(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), VERTICAL, AXES)
        span = run(anchors)

        assert dot(span, AXES["right"]) == pytest.approx(0)
        assert abs(dot(span, AXES["up"])) == pytest.approx(9)

    def test_the_depth_between_them_is_not_part_of_it(self):
        # A drawing is a projection: what separates two features along the line
        # of sight is not what the sheet shows.
        anchors = distance_anchors(point((0, 5, 0)), point((4, -5, 9)), HORIZONTAL, AXES)

        assert abs(dot(run(anchors), AXES["right"])) == pytest.approx(4)


class TestOnARealFrame:
    """The rules reaching a measurement through collect_drawings."""

    @pytest.fixture
    def drawings(self):
        import importlib.util
        import sys
        from pathlib import Path
        from tests.testing_shavings import load_module

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_anchors", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_anchors"] = runner
        spec.loader.exec_module(runner)
        frame = load_module(
            "anchors_fixture", root / "kigumi" / "test-fixtures" / "measured_frame.py"
        ).build_frame()
        return runner, runner.collect_drawings(frame, None, [])

    def _measurements(self, runner, drawings):
        from kumiki.drawing import projected_kinds

        for drawing in drawings:
            for viewport in drawing.get("viewports") or []:
                axes = runner._viewport_axes(drawing, viewport["id"])
                for measure in viewport.get("measurements") or []:
                    if measure.get("unresolved") or not axes:
                        continue
                    admitted = projected_kinds(
                        measure["a"].get("geometry"), measure["b"].get("geometry"),
                        axes["look"])
                    yield measure, axes, admitted

    def _square_to(self, measure, end, look):
        """How far from square the dimension is to one edge-on face."""
        geometry = measure[end].get("geometry") or {}
        if geometry.get("kind") != "plane":
            return None
        normal, run = geometry["normal"], [
            measure["b"]["at"][i] - measure["a"]["at"][i] for i in range(3)]
        across = (normal[1] * look[2] - normal[2] * look[1],
                  normal[2] * look[0] - normal[0] * look[2],
                  normal[0] * look[1] - normal[1] * look[0])
        size = sum(part * part for part in across) ** 0.5
        if size < 1e-9:
            # Facing the reader rather than edge-on: no line to be square to.
            return None
        return dot(run, tuple(part / size for part in across)) / max(
            1e-12, sum(part * part for part in run) ** 0.5)

    def test_the_fixture_offers_both_a_distance_and_an_angle(self, drawings):
        # Otherwise the two assertions below are not being exercised.
        runner, collected = drawings
        names = {
            kind.name
            for _measure, _axes, admitted in self._measurements(runner, collected)
            for kind in admitted
        }

        assert "projected_perpendicular_distance" in names
        assert "projected_angle" in names

    def test_every_distance_is_drawn_square_to_what_it_measures(self, drawings):
        runner, collected = drawings
        checked = 0
        for measure, axes, admitted in self._measurements(runner, collected):
            if not admitted or admitted[0].name != "projected_perpendicular_distance":
                continue
            for end in ("a", "b"):
                askew = self._square_to(measure, end, axes["look"])
                if askew is None:
                    continue
                checked += 1
                assert askew == pytest.approx(0, abs=1e-9)

        assert checked > 0

    def test_an_angle_keeps_the_anchors_its_features_gave_it(self, drawings):
        # The distance rules would place a crossing pair square to one of them
        # and not the other. An angle uses no anchor positions, and where it
        # should sit is its own question.
        runner, collected = drawings
        crossing = [
            measure for measure, _axes, admitted in self._measurements(runner, collected)
            if admitted and admitted[0].name == "projected_angle"
        ]

        assert crossing, "the fixture should offer an angle"
        for measure in crossing:
            assert measure["a"]["at"] is not None
            assert measure["b"]["at"] is not None
