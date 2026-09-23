"""Measurement kinds: what a dimension is measuring (kumiki/drawing.py).

The rules live here and only here. They used to live in the viewer as well,
because the projection needs a camera and only the viewer has one -- and this
file ended with a test that ran the two against each other, since two copies of
a table is how a table drifts. The runner settles a measurement where it
resolves it now and sends the answer, so there is one copy and nothing to
compare it against.
"""

import json
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
from kumiki.geometry import Line, Plane, Point
from kumiki.rule import create_v3
from tests.testing_shavings import load_module, present


def geometry(wire):
    """A wire-form geometry as the primitive kumiki.drawing takes.

    The dicts in this file are the WIRE form on purpose: the same values go to
    node, as JSON, for the parity tests below. Python stopped taking that shape
    directly, so this converts it the way kigumi/runner.py does at the same
    edge.
    """
    if wire is None:
        return None
    at = create_v3(*(wire.get("at") or (0, 0, 0)))
    kind = wire.get("kind")
    if kind == "point":
        return Point(position=at)
    if kind == "line":
        return Line(point=at, direction=create_v3(*(wire.get("direction") or (0, 0, 0))))
    if kind == "plane":
        return Plane(point=at, normal=create_v3(*(wire.get("normal") or (0, 0, 0))))
    return None

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
    def test_the_sheets_directions_do_not_exist_in_the_three_d(self):
        # HORIZONTAL and VERTICAL are directions of the page. The solid has no
        # up, so a distance along one is not a question that can be asked.
        with pytest.raises(ValueError, match="direction of the sheet"):
            MeasurementKind(DISTANCE, SOLID, MeasurementDirection.HORIZONTAL)

    def test_the_wire_form_says_the_space_outright(self):
        solid = MeasurementKind(ANGLE, SOLID)

        assert MeasurementKind.from_wire(solid.as_wire()) == solid

    def test_a_bare_name_now_composes_rather_than_reading_as_history(self):
        # `angle` used to mean the projected one, because that is what every
        # file containing the word meant. It composes for 3D now.
        assert MeasurementKind.from_wire("angle") == MeasurementKind(ANGLE, SOLID)
        assert MeasurementKind.from_wire("projected_angle") == MeasurementKind(ANGLE, PROJECTED)


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


class TestWhatAFeatureLooksLikeOnTheSheet:
    """project(), which answers with geometry rather than a name and a vector.

    The three shapes going in are the three coming out, so what a caller gets
    back can be asked what it is instead of being told.
    """

    #: Looking down -Y, so X is across the sheet and Z is up it.
    GAZE = create_v3(0, -1, 0)

    def test_a_point_stays_where_it_is(self):
        from kumiki.drawing import project

        at = Point(position=create_v3(1, 2, 3))
        assert project(at, self.GAZE) is at

    def test_an_edge_seen_end_on_becomes_a_point(self):
        from kumiki.drawing import project

        end_on = Line(direction=create_v3(0, 1, 0), point=create_v3(1, 2, 3))
        seen = project(end_on, self.GAZE)
        assert isinstance(seen, Point)
        assert list(seen.position) == pytest.approx([1, 2, 3])

    def test_an_edge_seen_across_stays_a_line_flattened_onto_the_sheet(self):
        from kumiki.drawing import project

        leaning = Line(direction=create_v3(0, 1, 1), point=create_v3(0, 0, 0))
        seen = project(leaning, self.GAZE)
        assert isinstance(seen, Line)
        # The Y that ran into the sheet is gone; only the Z is left.
        assert list(seen.direction) == pytest.approx([0, 0, 1])

    def test_a_face_seen_edge_on_draws_as_a_line_along_itself(self):
        from kumiki.drawing import project

        upright = Plane(normal=create_v3(0, 0, 1), point=create_v3(0, 0, 5))
        seen = project(upright, self.GAZE)
        assert isinstance(seen, Line)
        # Square to both the face's normal and the line of sight.
        assert abs(float(seen.direction[0])) == pytest.approx(1.0)

    def test_a_face_seen_at_an_angle_covers_the_view_and_projects_to_nothing(self):
        from kumiki.drawing import project

        facing_you = Plane(normal=create_v3(0, 1, 0), point=create_v3(0, 0, 0))
        assert project(facing_you, self.GAZE) is None

    def test_a_feature_lying_on_no_plane_or_line_projects_to_nothing(self):
        """A cylinder's barrel: good to select, never located."""
        from kumiki.drawing import project

        assert project(None, self.GAZE) is None


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
        from kumiki.drawing import MeasurementFeature, form_of

        assert form_of(geometry(self.TOP)) is MeasurementFeature.PLANE

    def test_an_edge_is_a_line_even_when_it_points_at_you(self):
        from kumiki.drawing import MeasurementFeature, form_of

        assert form_of(geometry(self.UPRIGHT)) is MeasurementFeature.LINE

    def test_two_faces_meeting_at_a_corner_admit_an_angle(self):
        from kumiki.drawing import three_d_kinds

        assert [k.name for k in three_d_kinds(geometry(self.SIDE), geometry(self.TOP))] == ["angle"]

    def test_two_parallel_faces_admit_the_distance_between_them(self):
        from kumiki.drawing import three_d_kinds

        assert [k.name for k in three_d_kinds(geometry(self.SIDE), geometry(self.FAR_SIDE))] == [
            "perpendicular_distance"]

    def test_crossing_edges_admit_an_angle(self):
        from kumiki.drawing import three_d_kinds

        assert [k.name for k in three_d_kinds(geometry(self.UPRIGHT), geometry(self.ALONG))] == ["angle"]

    def test_an_edge_lying_in_a_face_is_parallel_to_it(self):
        """A normal is not a direction.

        The line runs square to the normal exactly when it lies in the plane, so
        comparing the two as though both were directions would call this a
        crossing and offer an angle of nothing.
        """
        from kumiki.drawing import three_d_kinds

        assert [k.name for k in three_d_kinds(geometry(self.UPRIGHT), geometry(self.SIDE))] == [
            "perpendicular_distance"]

    def test_an_edge_square_to_a_face_crosses_it(self):
        from kumiki.drawing import three_d_kinds

        assert [k.name for k in three_d_kinds(geometry(self.ALONG), geometry(self.SIDE))] == ["angle"]

    def test_a_feature_lying_on_nothing_admits_nothing(self):
        from kumiki.drawing import three_d_kinds

        assert three_d_kinds(geometry({"kind": "barrel"}), geometry(self.SIDE)) == ()

    def test_the_solid_never_offers_a_direction_of_the_sheet(self):
        """Horizontal and vertical are the page's, and the solid has no up."""
        from kumiki.drawing import MeasurementDirection, three_d_kinds

        for a in (self.SIDE, self.TOP, self.UPRIGHT, self.ALONG):
            for b in (self.SIDE, self.TOP, self.UPRIGHT, self.ALONG):
                for kind in three_d_kinds(geometry(a), geometry(b)):
                    assert kind.direction is MeasurementDirection.PERPENDICULAR


# `TestTheViewerAgrees` stood here, and is gone with the thing it watched.
#
# The viewer kept its own copy of these rules -- projectedForm, solidForm, the
# kinds tables, measureValue and the epsilons -- because it projects on every
# pointer move and could not ask python each time. Two copies of a rule is how
# a rule drifts, so this class ran the two against each other over a case
# matrix that deliberately straddled the epsilons.
#
# The runner settles a measurement where it resolves it now and sends the
# answer, so measurements.js has no copy left to disagree with. What the tests
# guarded is not a rule anyone still has to keep in two places; it is one
# place. The case matrix they used lives on in this file's own tests, which is
# where the rules are.
#
# See docs/drawing-rule-migration.md for how it got here.


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

        across = Measure(first, second, kind=MeasurementKind.parse("projected_horizontal_distance"))
        up = Measure(first, second, kind=MeasurementKind.parse("projected_vertical_distance"))

        assert across.identity() != up.identity()

    def test_the_same_kind_written_twice_is_one_measurement(self):
        first, second = self._pair()

        assert (Measure(first, second, kind=MeasurementKind.parse("projected_horizontal_distance")).identity()
                == Measure(second, first, kind=MeasurementKind.parse("projected_horizontal_distance")).identity())

    def test_an_older_name_matches_the_kind_it_became(self):
        # A file written before kinds had structure has to keep overriding the
        # code measurement it always overrode.
        first, second = self._pair()
        older = Measure(first, second, kind=MeasurementKind.parse("projected_angle"))
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
            first, second, kind=MeasurementKind.parse("projected_horizontal_distance")).identity()

    def test_the_viewer_and_the_library_build_the_same_identity(self):
        # A file measurement overrides a code one by matching this tuple, so
        # the two sides have to agree on what it is.
        runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
        runner = load_module("kigumi_runner_kinds", runner_path)

        first, second = self._pair()
        measure = Measure(first, second, kind=MeasurementKind.parse("projected_horizontal_distance"))
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
        across = self._measure("projected_horizontal_distance")
        up = self._measure("projected_vertical_distance")

        assert does_override(across, across, self.FILE, self.CODED)
        assert not does_override(up, across, self.FILE, self.CODED)

    def test_code_overrules_an_algorithm_whatever_kind_it_chose(self):
        # Otherwise you would have to guess the generated kind to replace it,
        # which stops working the next time the algorithm changes.
        across = self._measure("projected_horizontal_distance")
        up = self._measure("projected_vertical_distance")

        assert does_override(up, across, self.CODED, self.GENERATED)

    def test_a_different_pair_is_never_the_same_measurement(self):
        one = self._measure("projected_horizontal_distance")
        other = Measure(self._anchor("aaa"), self._anchor("mmm"), kind=MeasurementKind.parse("projected_horizontal_distance"))

        assert not does_override(other, one, self.FILE, self.CODED)
        assert not does_override(other, one, self.CODED, self.GENERATED)

    def test_two_of_the_same_tier_sit_beside_each_other(self):
        # However alike. Two coded measurements are two measurements.
        measure = self._measure("projected_horizontal_distance")

        assert not does_override(measure, measure, self.CODED, self.CODED)
        assert not does_override(measure, measure, self.FILE, self.FILE)

    def test_a_lower_tier_never_displaces_a_higher_one(self):
        measure = self._measure("projected_horizontal_distance")

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


class TestEveryKindHasANameAPersonWouldUse:
    """Each kind the rules can produce is translated, in every locale.

    The kind dropdown labels each entry `viewer.measure.kind.<name>`, and a
    missing key falls through as the key itself -- so a kind nobody translated
    shows the reader a code reference. The solid kinds arrived without entries
    and did exactly that.

    This lived in kigumi/__tests__/i18n.test.js, which generated the list by
    running the viewer's own copy of the rules. There is one copy now and it is
    here, so the test is here: the point of it is that the list is GENERATED --
    a kind nobody thought of is still checked -- and a hand-written list would
    give that up.
    """

    #: Enough geometry to reach every kind the tables can name, in both spaces.
    SHAPES = [
        {"kind": "point", "at": [0, 0, 0]},
        {"kind": "line", "at": [0, 0, 0], "direction": [1, 0, 0]},
        {"kind": "line", "at": [0, 0, 0], "direction": [0, 1, 0]},
        {"kind": "plane", "at": [0, 0, 0], "normal": [0, 0, 1]},
        {"kind": "plane", "at": [0, 0, 0], "normal": [1, 0, 0]},
        {"kind": "plane", "at": [0, 0, 0], "normal": [0, 0, -1]},
    ]
    LOOK = [0, 0, -1]

    def _every_kind(self):
        from kumiki.drawing import projected_kinds, three_d_kinds

        names = set()
        for one in self.SHAPES:
            for other in self.SHAPES:
                a, b = geometry(one), geometry(other)
                for kind in projected_kinds(a, b, self.LOOK):
                    names.add(kind.name)
                for kind in three_d_kinds(a, b):
                    names.add(kind.name)
        return sorted(names)

    def _catalogue(self, locale):
        path = (Path(__file__).resolve().parent.parent
                / "kigumi" / "i18n" / "locales" / f"{locale}.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_rules_produce_kinds_to_check_in_both_spaces(self):
        # Otherwise the two tests below check nothing at all.
        assert set(self._every_kind()) >= {
            "projected_perpendicular_distance", "projected_angle",
            "perpendicular_distance", "angle",
        }

    @pytest.mark.parametrize("locale", ["en", "ja"])
    def test_every_kind_is_named_in_this_locale(self, locale):
        catalogue = self._catalogue(locale)

        missing = [name for name in self._every_kind()
                   if not isinstance(catalogue.get(f"viewer.measure.kind.{name}"), str)]

        assert not missing, (
            f"{locale}.json has no name for {missing} -- the dropdown would show "
            f"the key itself")


class TestAnUnreadableKind:
    def test_falls_back_to_the_default_rather_than_raising(self):
        # The drawings file is hand-edited, so a name nobody can read must not
        # take the frame down.
        with pytest.warns(UserWarning):
            assert MeasurementKind.from_wire("horizontal") is None

    def test_a_composed_name_still_reads(self):
        assert (MeasurementKind.from_wire("projected_horizontal_distance")
                == MeasurementKind(DISTANCE, PROJECTED, MeasurementDirection.HORIZONTAL))
