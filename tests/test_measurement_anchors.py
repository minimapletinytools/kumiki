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


class TestAFeatureSeenEndOn:
    """A line whose length is all depth draws as a point, and must be given as one.

    MeasureSpan is what a feature is ONCE PROJECTED, and building it in three
    dimensions ignored that: two arrises running along different axes were handed
    over as two lines, so a point-and-line pair went through the parallel-lines
    rule and both ends were slid to a station that meant nothing.
    """

    def test_a_line_along_the_view_is_a_point_to_the_rules(self):
        import importlib.util
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_endon", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_endon"] = runner
        spec.loader.exec_module(runner)

        assert runner._projects_to_a_point((0, 1, 0), (0, 1, 0)) is True
        assert runner._projects_to_a_point((0, -1, 0), (0, 1, 0)) is True
        assert runner._projects_to_a_point((1, 0, 0), (0, 1, 0)) is False

    def test_a_hair_off_end_on_is_still_a_line(self):
        # It draws as a very short line, and calling it a point would refuse a
        # dimension that is drawable.
        import importlib.util
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_endon2", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_endon2"] = runner
        spec.loader.exec_module(runner)

        assert runner._projects_to_a_point((0.05, 1, 0), (0, 1, 0)) is False

    def test_a_point_and_a_line_do_not_go_through_the_parallel_rule(self):
        # The point stays where it is and the line takes the foot. The parallel
        # rule would slide BOTH to a shared station.
        anchors = distance_anchors(
            point((0, -0.6, 0.05)),
            line((-0.064, -0.61, 0.05), (0, 1, 0), (0, 0.546)),
            PERPENDICULAR,
        )

        assert anchors[0] == (0, -0.6, 0.05)
        assert anchors[1][1] == pytest.approx(-0.6)


class TestAFeatureIsBoundedByWhatDeclaredIt:
    """An arris of a mortise hole is as long as the hole, not as the timber.

    A face was already cropped to the node that declared it as well as to the
    timber. A line was cropped to the timber alone -- and the line an arris lies
    on runs the whole length of the post, so a 25mm feature came back with a
    1295mm extent. Two such extents overlap over the whole timber, so the
    dimension landed in the middle of it, nowhere near what it measured.
    """

    @pytest.fixture
    def receiving(self):
        import importlib.util
        import sys
        from pathlib import Path

        from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
        from kumiki.joints.workshop.mixed import (
            cut_mortise_and_tenon_joint_on_face_aligned_timbers)
        from kumiki.rule import create_v3, inches
        from kumiki.timber import Frame

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_bounds", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_bounds"] = runner
        spec.loader.exec_module(runner)

        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=create_canonical_example_butt_joint_timbers(create_v3(0, 0, 0)),
            tenon_width_relative_to_joint=inches(3),
            tenon_height_relative_to_joint=inches(1),
            tenon_length=inches(3), mortise_depth=inches(7, 2))
        frame = Frame.from_joints([joint])
        entries, _ = runner._assign_member_keys(frame)
        entry = next(e for e in entries if e["memberKey"] == "receiving_timber#0")
        return runner, entry

    def _spans(self, runner, entry, look):
        from kumiki.cutcsg import CSGFeatureType, FeatureTestTolerances
        from kumiki.triangles import triangulate_cutcsg

        timber = entry["timber"]
        root = entry["cutTimber"].render_timber_with_cuts_csg_local()
        points = [
            [float(vertex[i]) for i in range(3)]
            for triangle in triangulate_cutcsg(root).mesh.triangles for vertex in triangle
        ]
        found = {}
        for point in points:
            for hit in runner._features_at_point(
                    root, runner._to_v3(point), 5e-4, FeatureTestTolerances(face=5e-4)):
                if hit.feature.feature_type() != CSGFeatureType.EDGE:
                    continue
                found.setdefault(hit.feature.name, runner._measure_span(
                    hit.feature, hit.owner, timber, hit.feature.locate(hit.owner),
                    root, look))
        return found, float(timber.length)

    def test_an_arris_of_the_hole_is_as_long_as_the_hole(self, receiving):
        runner, entry = receiving
        spans, length = self._spans(runner, entry, [1, 0, 0])

        holes = [span for name, span in spans.items()
                 if name.startswith("arris.") and span is not None and not span.is_point]
        assert holes, "the mortise hole should declare some arrises"
        for span in holes:
            low, high = span.interval
            assert high - low < length / 4

    def test_a_timber_arris_is_still_as_long_as_the_timber_allows(self, receiving):
        # The bound has to come from what declared it, not from being small: a
        # rough arris IS declared by the whole timber and must keep its length.
        runner, entry = receiving
        spans, length = self._spans(runner, entry, [0, 0, 1])

        rough = [span for name, span in spans.items()
                 if name.startswith("rough.") and span is not None and not span.is_point]
        assert rough, "the timber should declare some arrises"
        assert max(high - low for low, high in (span.interval for span in rough)) \
            > length / 2


class TestAFeatureKnowsItsOwnEnds:
    """Extents come from the shape, not from clipping it against something.

    An arris lies exactly ON the surface of whatever declared it, and asking a
    solid "is this boundary point inside you" is the one question an inside test
    cannot answer. It said no, the bound was lost, and a 51mm arris of a mortise
    hole was reported with the 1295mm extent of the whole post -- so two of them
    overlapped over the entire timber and the dimension landed in the middle of
    it.

    A prism knows where its own corners are. Nothing has to be clipped to find
    out where its faces and arrises stop.
    """

    def _box(self):
        from kumiki.cutcsg import RectangularPrism
        from kumiki.rule import create_v2, scalar

        return RectangularPrism(
            size=create_v2(scalar("0.1"), scalar("0.2")),
            start_distance=scalar("0"), end_distance=scalar("0.4"))

    def _face(self, which):
        from kumiki.cutcsg import SimpleRectangularPrismFeature

        return SimpleRectangularPrismFeature(name=str(which), face=which)

    def test_a_face_knows_its_four_corners(self):
        from kumiki.cutcsg import PrismFace

        corners = self._face(PrismFace.RIGHT).corners(self._box())

        assert len(corners) == 4
        # Half the width across, half the height up, the length along.
        for corner in corners:
            assert float(corner[0, 0]) == pytest.approx(0.05)
            assert abs(float(corner[1, 0])) == pytest.approx(0.1)
            assert float(corner[2, 0]) in (pytest.approx(0.0), pytest.approx(0.4))

    def test_an_unbounded_face_says_so_rather_than_guessing(self):
        from kumiki.cutcsg import PrismFace, RectangularPrism
        from kumiki.rule import create_v2, scalar

        endless = RectangularPrism(
            size=create_v2(scalar("0.1"), scalar("0.2")),
            start_distance=scalar("0"), end_distance=None)

        assert self._face(PrismFace.RIGHT).corners(endless) is None

    def test_an_arris_is_two_corners_of_the_faces_that_form_it(self):
        from kumiki.cutcsg import PrismFace, SimpleRectangularPrismEdgeFeature

        arris = SimpleRectangularPrismEdgeFeature(
            name="a", faces=(PrismFace.RIGHT, PrismFace.FRONT))

        extent = arris.get_extent(self._box())

        assert extent.ends is not None
        first, second = extent.ends
        assert abs(float(second[2, 0]) - float(first[2, 0])) == pytest.approx(0.4)

    def test_and_its_anchor_is_between_them(self):
        from kumiki.cutcsg import PrismFace, SimpleRectangularPrismEdgeFeature

        extent = SimpleRectangularPrismEdgeFeature(
            name="a", faces=(PrismFace.RIGHT, PrismFace.FRONT)).get_extent(self._box())

        assert float(extent.anchor[2, 0]) == pytest.approx(0.2)

    def test_opposite_faces_form_no_arris_and_are_not_invented(self):
        from kumiki.cutcsg import PrismFace, SimpleRectangularPrismEdgeFeature

        assert SimpleRectangularPrismEdgeFeature(
            name="a", faces=(PrismFace.LEFT, PrismFace.RIGHT)).get_extent(self._box()) is None

    def test_a_derived_edge_reaches_as_far_as_both_its_parents(self):
        from kumiki.cutcsg import (DerivedEdgeFeature, FeatureGroup, FeatureProperties,
                                   OwnedFeatureHit, PrismFace,
                                   SimpleRectangularPrismFeature)

        box = self._box()
        # Groups that are allowed to meet: A pairs with B2, which is what makes
        # an edge between these two derivable at all.
        face = lambda which, group: SimpleRectangularPrismFeature(
            name=str(which), face=which, properties=FeatureProperties(group=group))
        edge = DerivedEdgeFeature.derive(
            OwnedFeatureHit(feature=face(PrismFace.RIGHT, FeatureGroup.A), owner=box),
            OwnedFeatureHit(feature=face(PrismFace.FRONT, FeatureGroup.B2), owner=box))
        assert edge is not None, "adjacent faces in meeting groups form an edge"

        extent = edge.get_extent(box)

        assert extent.ends is not None
        first, second = extent.ends
        assert abs(float(second[2, 0]) - float(first[2, 0])) == pytest.approx(0.4)

    def test_the_runner_reads_those_ends_as_an_interval(self):
        import importlib.util
        import sys
        from pathlib import Path

        from kumiki.cutcsg import PrismFace, SimpleRectangularPrismEdgeFeature

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_declared", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_declared"] = runner
        spec.loader.exec_module(runner)

        box = self._box()
        arris = SimpleRectangularPrismEdgeFeature(
            name="a", faces=(PrismFace.RIGHT, PrismFace.FRONT))

        span = runner._declared_line_span(arris, box, arris.locate(box))

        assert span is not None
        assert span[1] - span[0] == pytest.approx(0.4)

    def test_a_feature_that_cannot_say_returns_nothing(self):
        # So the caller falls back to clipping rather than to a wrong number.
        import importlib.util
        import sys
        from pathlib import Path

        from kumiki.cutcsg import PrismFace, RectangularPrism
        from kumiki.cutcsg import SimpleRectangularPrismEdgeFeature
        from kumiki.rule import create_v2, scalar

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_declared2", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_declared2"] = runner
        spec.loader.exec_module(runner)

        endless = RectangularPrism(
            size=create_v2(scalar("0.1"), scalar("0.2")),
            start_distance=scalar("0"), end_distance=None)
        arris = SimpleRectangularPrismEdgeFeature(
            name="a", faces=(PrismFace.RIGHT, PrismFace.FRONT))

        assert runner._declared_line_span(arris, endless, arris.locate(endless)) is None


class TestTheHalfMadeMeasurementIsPlacedLikeTheFinishedOne:
    """A preview that sits somewhere else is a preview of nothing.

    Both go through distance_anchors now. Before, a pick carried each feature's
    own anchor and the preview was drawn between those, while the written
    measurement was placed at the middle of their overlap -- so confirming moved
    the dimension, sometimes the length of the timber.
    """

    def test_the_held_end_is_resolved_from_its_reference(self):
        # Not from geometry sent along with the request: resolving it the way a
        # written measurement resolves it is what makes the two agree, rather
        # than being a second way of working out the same answer.
        import importlib.util
        import inspect
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_preview", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_preview"] = runner
        spec.loader.exec_module(runner)

        source = inspect.getsource(runner._anchors_for_pick)

        assert "_resolve_anchor_placed" in source
        assert "distance_anchors" in source

    def test_a_pick_with_nothing_held_places_nothing(self):
        import importlib.util
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_preview2", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_preview2"] = runner
        spec.loader.exec_module(runner)

        assert runner._anchors_for_pick(None, None, None, {}, None) is None
        assert runner._anchors_for_pick(
            None, None, None, {"heldReference": {"timber": "t"}}, None) is None
