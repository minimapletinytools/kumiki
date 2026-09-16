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
from kumiki.identity import (DerivedFeaturePath, FeatureRef, MeasurementId,
                             ResolvedTimberPath,
                             SingleFeaturePath)
from tests.testing_shavings import load_module, present

def _feature_of(anchor) -> str:
    """The feature an anchor names.

    Measure holds FeaturePath, which is abstract on purpose -- a derived edge
    has two parents and no single feature. These tests build the other kind, so
    this says so rather than reaching for an attribute the declared type has
    not got.
    """
    assert isinstance(anchor, SingleFeaturePath), f"expected a single feature, got {anchor!r}"
    return anchor.feature or ""


def _offset_of(measure) -> float:
    """Where a measurement's dimension line sits.

    Both the placement and its offset are optional -- "wherever the viewport
    puts it" -- and these tests are about the ones that say.
    """
    return present(present(measure.placement, "a placement").offset, "an offset")


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


class TestWhatTheSolidAdmits:
    """The 3D view classifies features as they ARE, projecting nothing.

    Its camera belongs to the reader and turns as they look around, so asking
    what a face looks like from here called nearly every face an AREA -- nothing
    to measure -- and refused it.
    """

    SIDE = {"kind": "plane", "normal": [1, 0, 0]}
    FAR_SIDE = {"kind": "plane", "normal": [-1, 0, 0]}
    TOP = {"kind": "plane", "normal": [0, 0, 1]}
    UPRIGHT = {"kind": "line", "direction": [0, 0, 1]}
    ALONG = {"kind": "line", "direction": [1, 0, 0]}

    def test_a_face_is_a_plane_from_wherever_it_is_seen(self):
        from kumiki.drawing import MeasurementFeature, solid_form

        assert solid_form(self.TOP)[0] is MeasurementFeature.PLANE

    def test_an_edge_is_a_line_even_when_it_points_at_you(self):
        from kumiki.drawing import MeasurementFeature, solid_form

        assert solid_form(self.UPRIGHT)[0] is MeasurementFeature.LINE

    def test_two_faces_meeting_at_a_corner_admit_an_angle(self):
        from kumiki.drawing import solid_kinds

        assert [k.name for k in solid_kinds(self.SIDE, self.TOP)] == ["angle"]

    def test_two_parallel_faces_admit_the_distance_between_them(self):
        from kumiki.drawing import solid_kinds

        assert [k.name for k in solid_kinds(self.SIDE, self.FAR_SIDE)] == [
            "perpendicular_distance"]

    def test_crossing_edges_admit_an_angle(self):
        from kumiki.drawing import solid_kinds

        assert [k.name for k in solid_kinds(self.UPRIGHT, self.ALONG)] == ["angle"]

    def test_an_edge_lying_in_a_face_is_parallel_to_it(self):
        """A normal is not a direction.

        The line runs square to the normal exactly when it lies in the plane, so
        comparing the two as though both were directions would call this a
        crossing and offer an angle of nothing.
        """
        from kumiki.drawing import solid_kinds

        assert [k.name for k in solid_kinds(self.UPRIGHT, self.SIDE)] == [
            "perpendicular_distance"]

    def test_an_edge_square_to_a_face_crosses_it(self):
        from kumiki.drawing import solid_kinds

        assert [k.name for k in solid_kinds(self.ALONG, self.SIDE)] == ["angle"]

    def test_a_feature_lying_on_nothing_admits_nothing(self):
        from kumiki.drawing import solid_kinds

        assert solid_kinds({"kind": "barrel"}, self.SIDE) == ()

    def test_the_solid_never_offers_a_direction_of_the_sheet(self):
        """Horizontal and vertical are the page's, and the solid has no up."""
        from kumiki.drawing import MeasurementDirection, solid_kinds

        for a in (self.SIDE, self.TOP, self.UPRIGHT, self.ALONG):
            for b in (self.SIDE, self.TOP, self.UPRIGHT, self.ALONG):
                for kind in solid_kinds(a, b):
                    assert kind.direction is MeasurementDirection.PERPENDICULAR


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
        out = subprocess.run([present(node, "node on PATH"), "-e", script], capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    #: Geometry to project, spanning every answer projected_form can give.
    CASES = [
        {"kind": "point", "at": [0, 0, 0]},
        {"kind": "line", "direction": [1, 0, 0]},
        {"kind": "line", "direction": [0, 1, 0]},          # end-on: a point
        {"kind": "line", "direction": [0, 0.9995, 0.03]},  # a hair off end-on
        # Straddling ALIGNMENT_EPSILON, so the two sides disagree the moment
        # either moves its threshold. Without a case in the gap this comparison
        # passes whatever the epsilons are, which is a test of nothing.
        {"kind": "line", "direction": [0.0999, 0.995, 0]},
        {"kind": "plane", "normal": [1, 0.005, 0]},
        {"kind": "line", "direction": [1, 1, 0]},          # oblique
        {"kind": "plane", "normal": [0, 0, 1]},            # edge-on: a line
        {"kind": "plane", "normal": [0, 1, 0]},            # facing: an area
        {"kind": "plane", "normal": [0, 1, 0.0005]},       # barely off facing
        {"kind": "plane", "normal": [1, 1, 0]},            # oblique
        None,                                              # nothing to measure
    ]
    LOOKS = [[0, 1, 0], [0, -1, 0], [1, 0, 0], [0.577, 0.577, 0.577]]

    def _viewer_forms(self):
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not available")
        script = (
            "const m = require(%s);"
            "const cases = %s, looks = %s;"
            "const out = [];"
            "for (const look of looks) { for (const g of cases) {"
            "  const f = m.projectedForm(g, look);"
            "  out.push([f.form, f.direction || null]); } }"
            "process.stdout.write(JSON.stringify(out));"
            % (json.dumps(str(Path(__file__).resolve().parent.parent
                              / "kigumi" / "webview" / "measurements.js")),
               json.dumps(self.CASES), json.dumps(self.LOOKS))
        )
        out = subprocess.run([present(node, "node on PATH"), "-e", script],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    def _viewer_solid(self):
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not available")
        script = (
            "const m = require(%s);"
            "const cases = %s;"
            "const out = [];"
            "for (const a of cases) { for (const b of cases) {"
            "  out.push(m.solidKinds(m.solidForm(a), m.solidForm(b))); } }"
            "process.stdout.write(JSON.stringify(out));"
            % (json.dumps(str(Path(__file__).resolve().parent.parent
                              / "kigumi" / "webview" / "measurements.js")),
               json.dumps(self.CASES))
        )
        out = subprocess.run([present(node, "node on PATH"), "-e", script],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    def test_the_two_solid_tables_say_the_same_thing(self):
        """The 3D view's rule, in python and in the viewer's copy of it.

        The same reason the projected pair are checked against each other: two
        copies of a table is how a table drifts.
        """
        from kumiki.drawing import solid_kinds

        theirs = self._viewer_solid()
        mine = [[kind.name for kind in solid_kinds(a, b)]
                for a in self.CASES for b in self.CASES]

        assert theirs == mine

    def test_the_two_projections_say_the_same_thing(self):
        """The rule the runner prefers features by, and the one the viewer draws by.

        The viewer keeps a copy because it projects on every pointer move and
        cannot ask python each time. Two copies of a rule is how a rule drifts,
        so they are run against each other here.
        """
        from kumiki.drawing import projected_form

        mine = []
        for look in self.LOOKS:
            for geometry in self.CASES:
                form, direction = projected_form(geometry, look)
                mine.append([
                    form.value if form is not None else "none",
                    list(direction) if direction is not None else None,
                ])

        theirs = self._viewer_forms()
        assert len(theirs) == len(mine)
        for (form, direction), (their_form, their_direction) in zip(mine, theirs):
            assert form == their_form
            if direction is None or their_direction is None:
                assert direction is None and their_direction is None
            else:
                assert direction == pytest.approx(their_direction, abs=1e-9)

    def _viewer_status_kinds(self):
        """What measurementStatus says a WRITTEN measurement admits."""
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not available")
        script = (
            "const m = require(%s);"
            "const cases = %s, look = %s;"
            "const out = [];"
            "for (const a of cases) { for (const b of cases) {"
            "  for (const space of ['projected', '3d']) {"
            "    const status = m.measurementStatus("
            "      { a: { at: [0,0,0], geometry: a }, b: { at: [137,91,53], geometry: b } },"
            "      { look, right: [1,0,0], up: [0,0,1] },"
            "      { orthographic: space === 'projected', space });"
            "    out.push(status.available || []); } } }"
            "process.stdout.write(JSON.stringify(out));"
            % (json.dumps(str(Path(__file__).resolve().parent.parent
                              / "kigumi" / "webview" / "measurements.js")),
               json.dumps(self.CASES), json.dumps(self.LOOKS[0]))
        )
        out = subprocess.run([present(node, "node on PATH"), "-e", script],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    A_AT = [0.0, 0.0, 0.0]
    B_AT = [137.0, 91.0, 53.0]

    def _viewer_values(self):
        """What measureValue makes of every pair, in both spaces."""
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not available")
        script = (
            "const m = require(%s);"
            "const cases = %s, look = %s, a = %s, b = %s;"
            "const axes = { look, right: [1,0,0], up: [0,0,1] };"
            "const out = [];"
            "for (const ca of cases) { for (const cb of cases) {"
            "  for (const space of ['projected', '3d']) {"
            "    const solid = space === '3d';"
            "    const fa = solid ? m.solidForm(ca) : m.projectedForm(ca, look);"
            "    const fb = solid ? m.solidForm(cb) : m.projectedForm(cb, look);"
            "    const kinds = solid ? m.solidKinds(fa, fb)"
            "                        : m.availableKinds(fa, fb);"
            "    const row = [];"
            "    for (const kind of kinds) {"
            "      const v = m.measureValue(kind, a, b, fa, fb,"
            "        Object.assign({}, axes, { space }));"
            "      row.push(v.unit === 'length' ? v.value : null); }"
            "    out.push(row); } } }"
            "process.stdout.write(JSON.stringify(out));"
            % (json.dumps(str(Path(__file__).resolve().parent.parent
                              / "kigumi" / "webview" / "measurements.js")),
               json.dumps(self.CASES), json.dumps(self.LOOKS[0]),
               json.dumps(self.A_AT), json.dumps(self.B_AT))
        )
        out = subprocess.run([present(node, "node on PATH"), "-e", script],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    def test_the_two_agree_on_what_a_pair_comes_to(self):
        """`pair_separation` against the viewer's `measureValue`, pair by pair.

        Python had no way to say what a measurement came to -- only the viewer
        computed that -- so the rule that refuses a pair with nothing between
        them was first written against PLACED ANCHORS, which made what a
        measurement IS depend on where it happened to be drawn. Python can
        answer it from the geometries now, and this is what stops that answer
        drifting from the one the viewer draws with.

        None on both sides for an angle: it measures no length, so the rule
        leaves it alone.
        """
        from kumiki.drawing import pair_separation, projected_kinds, solid_kinds

        axes = {"look": self.LOOKS[0], "right": [1, 0, 0], "up": [0, 0, 1]}
        mine = []
        for one in self.CASES:
            for other in self.CASES:
                for space in ("projected", "3d"):
                    # A None case is "nothing to measure", and stays None.
                    a = None if one is None else dict(one, at=self.A_AT)
                    b = None if other is None else dict(other, at=self.B_AT)
                    admitted = (solid_kinds(a, b) if space == "3d"
                                else projected_kinds(a, b, self.LOOKS[0]))
                    mine.append([pair_separation(a, b, kind, axes)
                                 for kind in admitted])

        theirs = self._viewer_values()
        assert len(theirs) == len(mine), "the two walked different pairs"
        assert any(any(value for value in row) for row in mine), "no lengths compared"
        for row, their_row in zip(mine, theirs):
            assert len(row) == len(their_row)
            for value, their_value in zip(row, their_row):
                if value is None or their_value is None:
                    assert value is None and their_value is None
                else:
                    assert value == pytest.approx(their_value, abs=1e-9)

    def test_the_two_agree_on_what_counts_as_no_distance(self):
        """One epsilon, two files.

        The runner refuses a PICK the two features have nothing between; the
        viewer refuses to draw a WRITTEN measurement that comes to nothing.
        Different moments, same rule, and two numbers that drifted apart would
        mean a pick allowed and then never drawn -- which is the thing being
        fixed.
        """
        from kumiki.drawing import DEGENERATE_SEPARATION

        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not available")
        script = (
            "const m = require(%s);"
            "process.stdout.write(String(m.DEGENERATE_WORLD));"
            % json.dumps(str(Path(__file__).resolve().parent.parent
                             / "kigumi" / "webview" / "measurements.js"))
        )
        out = subprocess.run([present(node, "node on PATH"), "-e", script],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr

        assert float(out.stdout) == DEGENERATE_SEPARATION

    def test_a_written_measurement_is_judged_the_way_a_pick_is(self):
        """The fifth place the verdict is decided, against the rules it must match.

        The two anchors are deliberately off every axis: a pair whose ends come
        to zero is refused as degenerate before its kinds are reported, which
        says nothing about whether the two sides agree.

        The runner answers what a PICK admits; measurementStatus answers what a
        measurement already written admits, which no pick is happening for. That
        second answer is legitimate and it is also where three shipped bugs
        came from -- it judged in the wrong space, it upgraded a solid kind's
        name to the projected one, and it compared a structured kind against a
        list of names. Nothing pinned it to the rules until here.
        """
        from kumiki.drawing import projected_kinds, solid_kinds

        mine = []
        for one in self.CASES:
            for other in self.CASES:
                for space in ("projected", "3d"):
                    admitted = (solid_kinds(one, other) if space == "3d"
                                else projected_kinds(one, other, self.LOOKS[0]))
                    mine.append([kind.name for kind in admitted])

        assert self._viewer_status_kinds() == mine

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

        assert _feature_of(forwards.anchor_a) == _feature_of(backwards.anchor_a)
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

        assert _offset_of(swapped) == 24.0

    def test_an_order_that_is_already_canonical_is_left_alone(self):
        first, second = self._anchor("aaa"), self._anchor("zzz")

        kept = Measure(first, second, placement=MeasurementPlacement(offset=-24.0))

        assert _feature_of(kept.anchor_a) == "aaa"
        assert _offset_of(kept) == -24.0

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

        across = Measure(first, second, kind=MeasurementKind.parse("horizontal"))
        up = Measure(first, second, kind=MeasurementKind.parse("vertical"))

        assert across.identity() != up.identity()

    def test_the_same_kind_written_twice_is_one_measurement(self):
        first, second = self._pair()

        assert (Measure(first, second, kind=MeasurementKind.parse("horizontal")).identity()
                == Measure(second, first, kind=MeasurementKind.parse("horizontal")).identity())

    def test_an_older_name_matches_the_kind_it_became(self):
        # A file written before kinds had structure has to keep overriding the
        # code measurement it always overrode.
        first, second = self._pair()
        older = Measure(first, second, kind=MeasurementKind.parse("angle"))
        newer = Measure(first, second,
                        kind=MeasurementKind.from_wire(
                            {"operation": "angle", "space": "projected",
                             "direction": "perpendicular"}))

        assert older.identity() == newer.identity()

    def test_asking_for_no_kind_is_its_own_measurement(self):
        # "Whichever is natural" is a different request from naming one, even
        # when the viewport would resolve it to the same thing.
        first, second = self._pair()

        assert Measure(first, second).identity() != Measure(
            first, second, kind=MeasurementKind.parse("horizontal")).identity()

    def test_the_viewer_and_the_library_build_the_same_identity(self):
        # A file measurement overrides a code one by matching this tuple, so
        # the two sides have to agree on what it is.
        runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
        runner = load_module("kigumi_runner_kinds", runner_path)

        first, second = self._pair()
        measure = Measure(first, second, kind=MeasurementKind.parse("horizontal"))
        on_the_wire = {
            "a": runner.serialize_feature_path(measure.anchor_a),
            "b": runner.serialize_feature_path(measure.anchor_b),
            "kind": present(measure.kind, "a kind").as_wire(),
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
        """A measurement of the named kind. The name is parsed, not passed --
        Measure takes a MeasurementKind, and turning a name into one is
        MeasurementKind.parse's job rather than the constructor's."""
        return Measure(self._anchor("aaa"), self._anchor("zzz"),
                       kind=None if kind is None else MeasurementKind.parse(kind))

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
        other = Measure(self._anchor("aaa"), self._anchor("mmm"), kind=MeasurementKind.parse("horizontal"))

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


class TestMeasuringAFaceToAnEdge:
    """The pair whose two identities are different shapes."""

    def _face(self):
        return SingleFeaturePath(
            ResolvedTimberPath("post"), FeatureRef(("cut",), "tenon_left"), "FACE")

    def _edge(self):
        return DerivedFeaturePath(
            ResolvedTimberPath("post"),
            FeatureRef(("cut",), "tenon_left"), FeatureRef(("body",), "rough.front"))

    def test_it_can_be_measured_at_all(self):
        # A face's identity has a name where an edge's has a whole parent
        # reference, and python will not order a string against a tuple. So
        # this raised rather than measuring -- on the ordinary case of
        # dimensioning a face to an arris.
        measure = Measure(self._face(), self._edge())

        assert measure.identity() is not None

    def test_it_is_one_measurement_whichever_way_round(self):
        assert Measure(self._face(), self._edge()).identity() == Measure(
            self._edge(), self._face()).identity()

    def test_the_order_is_stable(self):
        # Nothing reads the order; it exists so a pair comes out the same way
        # round every time.
        one = Measure(self._face(), self._edge())
        other = Measure(self._face(), self._edge())

        assert one.anchor_a.identity() == other.anchor_a.identity()
