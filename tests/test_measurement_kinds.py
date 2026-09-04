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
    MeasurementDirection,
    MeasurementFeature,
    MeasurementKind,
    MeasurementOperation,
    MeasurementSpace,
    kinds_for,
)

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
