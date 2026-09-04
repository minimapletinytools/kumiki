"""Measurement kinds: what a dimension is measuring (kumiki/drawing.py).

The rules live here and in the viewer, because the projection needs a camera
and only the viewer has one. So the last test in this file checks the viewer's
copy against this one by running it -- two copies of a table is how a table
drifts.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from kumiki.drawing import (
    Measure,
    MeasurementDirection,
    MeasurementFeature,
    MeasurementKind,
    MeasurementOperation,
    MeasurementPlacement,
    MeasurementSource,
    MeasurementSpace,
    does_override,
    kinds_for,
)
from kumiki.identity import FeatureRef, ResolvedTimberPath, SingleFeaturePath

DISTANCE = MeasurementOperation.DISTANCE
ANGLE = MeasurementOperation.ANGLE
PROJECTED = MeasurementSpace.PROJECTED
SOLID = MeasurementSpace.THREE_D
POINT = MeasurementFeature.POINT
LINE = MeasurementFeature.LINE
PLANE = MeasurementFeature.PLANE
AREA = MeasurementFeature.AREA


class TestTheName:
    def test_it_is_composed_from_the_parts(self):
        # No mapping to keep in sync: the name IS the three fields read out.
        assert MeasurementKind(
            DISTANCE, PROJECTED, MeasurementDirection.HORIZONTAL,
        ).name == "projected_horizontal_distance"

    def test_a_solid_kind_says_nothing_about_projection(self):
        assert MeasurementKind(ANGLE, SOLID).name == "angle"

    def test_every_name_reads_back(self):
        for space in (PROJECTED, SOLID):
            for direction in MeasurementDirection:
                if space is SOLID and direction is not MeasurementDirection.PERPENDICULAR:
                    continue
                kind = MeasurementKind(DISTANCE, space, direction)
                assert MeasurementKind.parse(kind.name) == kind


class TestSpacesAndDirections:
    def test_the_sheets_directions_do_not_exist_in_the_solid(self):
        # HORIZONTAL and VERTICAL are directions of the page. The solid has no
        # up, so a distance along one is not a question that can be asked.
        with pytest.raises(ValueError, match="direction of the sheet"):
            MeasurementKind(DISTANCE, SOLID, MeasurementDirection.HORIZONTAL)

    def test_the_wire_form_says_the_space_outright(self):
        # `angle` is a solid angle by composition and a projected one by
        # history, so a bare name cannot carry both.
        solid = MeasurementKind(ANGLE, SOLID)

        assert MeasurementKind.from_wire(solid.as_wire()) == solid
        assert MeasurementKind.from_wire("angle") == MeasurementKind(ANGLE, PROJECTED)


class TestOlderNames:
    @pytest.mark.parametrize("older,expected", [
        ("aligned", MeasurementKind(DISTANCE, PROJECTED)),
        ("perpendicular", MeasurementKind(DISTANCE, PROJECTED)),
        ("horizontal", MeasurementKind(DISTANCE, PROJECTED, MeasurementDirection.HORIZONTAL)),
        ("vertical", MeasurementKind(DISTANCE, PROJECTED, MeasurementDirection.VERTICAL)),
        ("angle", MeasurementKind(ANGLE, PROJECTED)),
    ])
    def test_a_measurement_written_before_still_reads(self, older, expected):
        assert MeasurementKind.parse(older) == expected

    def test_aligned_and_perpendicular_became_one_kind(self):
        # Between two points the shortest distance is the distance.
        assert MeasurementKind.parse("aligned") == MeasurementKind.parse("perpendicular")


class TestWhatAPairAdmits:
    def test_two_points_admit_the_distance_and_both_components(self):
        assert [k.name for k in kinds_for(POINT, POINT, PROJECTED)] == [
            "projected_perpendicular_distance",
            "projected_horizontal_distance",
            "projected_vertical_distance",
        ]

    def test_a_point_and_a_line_admit_only_the_perpendicular(self):
        assert [k.name for k in kinds_for(POINT, LINE, PROJECTED)] == [
            "projected_perpendicular_distance"]

    def test_crossing_lines_admit_an_angle(self):
        assert [k.name for k in kinds_for(LINE, LINE, PROJECTED, parallel=False)] == [
            "projected_angle"]

    def test_parallel_lines_admit_a_separation(self):
        assert [k.name for k in kinds_for(LINE, LINE, PROJECTED, parallel=True)] == [
            "projected_perpendicular_distance"]

    def test_an_area_admits_nothing(self):
        # A face seen at an angle covers the view; there is no distance between
        # two things that each cover the view.
        assert kinds_for(AREA, POINT, PROJECTED) == ()
        assert kinds_for(AREA, LINE, PROJECTED) == ()

    def test_two_faces_admit_in_the_solid_what_they_cannot_on_the_sheet(self):
        # The whole of the difference between the two spaces: a face is a plane
        # in the solid and an area on the sheet.
        assert [k.name for k in kinds_for(PLANE, PLANE, SOLID, parallel=False)] == ["angle"]
        assert [k.name for k in kinds_for(PLANE, PLANE, SOLID, parallel=True)] == [
            "perpendicular_distance"]

    def test_a_plane_cannot_be_measured_on_a_sheet_without_projecting_it(self):
        with pytest.raises(ValueError, match="project it first"):
            kinds_for(PLANE, POINT, PROJECTED)


class TestTheViewerAgrees:
    """The viewer's copy of the table, checked against this one by running it."""

    def _viewer_rules(self):
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not available")
        script = (
            "const m = require(%s);"
            "process.stdout.write(JSON.stringify(m.PROJECTED_RULES));"
            % json.dumps(str(Path(__file__).resolve().parent.parent
                             / "kigumi" / "webview" / "measurements.js"))
        )
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    def test_the_two_tables_say_the_same_thing(self):
        expected = {
            "point-point": [k.name for k in kinds_for(POINT, POINT, PROJECTED)],
            "line-point": [k.name for k in kinds_for(POINT, LINE, PROJECTED)],
            "line-line-parallel": [k.name for k in kinds_for(LINE, LINE, PROJECTED, parallel=True)],
            "line-line-crossing": [k.name for k in kinds_for(LINE, LINE, PROJECTED, parallel=False)],
        }

        assert self._viewer_rules() == expected


class TestAnchorsAreWrittenInOneOrder:
    """Measuring A to B and measuring B to A are the same measurement."""

    def _anchor(self, name):
        return SingleFeaturePath(
            ResolvedTimberPath("post"), FeatureRef((name,), name), "FACE")

    def test_the_pair_comes_out_the_same_way_round(self):
        first, second = self._anchor("aaa"), self._anchor("zzz")

        forwards = Measure(first, second)
        backwards = Measure(second, first)

        assert forwards.anchor_a.feature == backwards.anchor_a.feature
        assert forwards == backwards

    def test_it_is_one_measurement_however_it_was_written(self):
        # Without this a pair written both ways is two entries in a viewport,
        # two dimensions drawn on top of each other, and a file override that
        # matches neither.
        first, second = self._anchor("aaa"), self._anchor("zzz")

        assert Measure(first, second).identity() == Measure(second, first).identity()

    def test_swapping_keeps_the_dimension_on_the_same_side(self):
        # The offset is perpendicular to the run between the anchors, so
        # reversing the run reverses the side. The offset is signed, so
        # negating it puts the line back.
        first, second = self._anchor("aaa"), self._anchor("zzz")

        swapped = Measure(second, first, placement=MeasurementPlacement(offset=-24.0))

        assert swapped.placement.offset == 24.0

    def test_an_order_that_is_already_canonical_is_left_alone(self):
        first, second = self._anchor("aaa"), self._anchor("zzz")

        kept = Measure(first, second, placement=MeasurementPlacement(offset=-24.0))

        assert kept.anchor_a.feature == "aaa"
        assert kept.placement.offset == -24.0

    def test_no_placement_is_fine(self):
        first, second = self._anchor("aaa"), self._anchor("zzz")

        assert Measure(second, first).placement is None


class TestKindTellsTwoMeasurementsApart:
    """Two kinds between one pair are two dimensions, and both should show."""

    def _anchor(self, name):
        return SingleFeaturePath(
            ResolvedTimberPath("post"), FeatureRef((name,), name), "FACE")

    def _pair(self):
        return self._anchor("aaa"), self._anchor("zzz")

    def test_the_horizontal_and_the_vertical_are_not_the_same_measurement(self):
        # The ordinary thing to want between two points, without having to mint
        # an id to say they are different.
        first, second = self._pair()

        across = Measure(first, second, kind="horizontal")
        up = Measure(first, second, kind="vertical")

        assert across.identity() != up.identity()

    def test_the_same_kind_written_twice_is_one_measurement(self):
        first, second = self._pair()

        assert (Measure(first, second, kind="horizontal").identity()
                == Measure(second, first, kind="horizontal").identity())

    def test_an_older_name_matches_the_kind_it_became(self):
        # A file written before kinds had structure has to keep overriding the
        # code measurement it always overrode.
        first, second = self._pair()
        older = Measure(first, second, kind="angle")
        newer = Measure(first, second,
                        kind={"operation": "angle", "space": "projected",
                              "direction": "perpendicular"})

        assert older.identity() == newer.identity()

    def test_asking_for_no_kind_is_its_own_measurement(self):
        # "Whichever is natural" is a different request from naming one, even
        # when the viewport would resolve it to the same thing.
        first, second = self._pair()

        assert Measure(first, second).identity() != Measure(
            first, second, kind="horizontal").identity()

    def test_the_viewer_and_the_library_build_the_same_identity(self):
        # A file measurement overrides a code one by matching this tuple, so
        # the two sides have to agree on what it is.
        import importlib.util
        import sys

        runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
        spec = importlib.util.spec_from_file_location("kigumi_runner_kinds", runner_path)
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_kinds"] = runner
        spec.loader.exec_module(runner)

        first, second = self._pair()
        measure = Measure(first, second, kind="horizontal")
        on_the_wire = {
            "a": runner.serialize_feature_path(measure.anchor_a),
            "b": runner.serialize_feature_path(measure.anchor_b),
            "kind": measure.kind.as_wire(),
            "measureId": None,
        }

        assert runner._measure_identity(on_the_wire) == measure.identity()


class TestWhatReplacesWhat:
    """Three tiers: an algorithm proposes, code decides, the file has the last word."""

    GENERATED = MeasurementSource.PYTHON_GENERATED
    CODED = MeasurementSource.PYTHON_CODED
    FILE = MeasurementSource.FILE_OVERRIDE

    def _anchor(self, name):
        return SingleFeaturePath(
            ResolvedTimberPath("post"), FeatureRef((name,), name), "FACE")

    def _measure(self, kind=None):
        return Measure(self._anchor("aaa"), self._anchor("zzz"), kind=kind)

    def test_a_file_override_must_match_the_kind_too(self):
        # It was written against a particular dimension. The vertical between
        # the same two features is one it was never about.
        across = self._measure("horizontal")
        up = self._measure("vertical")

        assert does_override(across, across, self.FILE, self.CODED)
        assert not does_override(up, across, self.FILE, self.CODED)

    def test_code_overrules_an_algorithm_whatever_kind_it_chose(self):
        # Otherwise you would have to guess the generated kind to replace it,
        # which stops working the next time the algorithm changes.
        across = self._measure("horizontal")
        up = self._measure("vertical")

        assert does_override(up, across, self.CODED, self.GENERATED)

    def test_a_different_pair_is_never_the_same_measurement(self):
        one = self._measure("horizontal")
        other = Measure(self._anchor("aaa"), self._anchor("mmm"), kind="horizontal")

        assert not does_override(other, one, self.FILE, self.CODED)
        assert not does_override(other, one, self.CODED, self.GENERATED)

    def test_two_of_the_same_tier_sit_beside_each_other(self):
        # However alike. Two coded measurements are two measurements.
        measure = self._measure("horizontal")

        assert not does_override(measure, measure, self.CODED, self.CODED)
        assert not does_override(measure, measure, self.FILE, self.FILE)

    def test_a_lower_tier_never_displaces_a_higher_one(self):
        measure = self._measure("horizontal")

        assert not does_override(measure, measure, self.CODED, self.FILE)
        assert not does_override(measure, measure, self.GENERATED, self.FILE)
        assert not does_override(measure, measure, self.GENERATED, self.CODED)
