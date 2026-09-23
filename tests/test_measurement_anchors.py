"""Where a distance attaches, at both ends.

A property of the PAIR and the plane rather than of either feature alone. An
anchor chosen per feature cannot know where the sensible attachment point is for
a given pair: two parallel edges each anchoring at their own midpoint gave a
dimension that leaned whenever those midpoints were offset along their length,
and a number beside it that was neither its length nor its direction.

See docs/measurement-spec.md.
"""

import math

import pytest

from kumiki.drawing import (MeasureSpan, MeasurementDirection, MeasurementKind,
                            ViewAxes,
                            MeasurementOperation, MeasurementSpace, distance_anchors)
from kumiki.rule import create_v3


def v(triple):
    """A triple as the vector a span holds. Written out so the tests need not."""
    return create_v3(*triple)


def kind(direction):
    return MeasurementKind(
        MeasurementOperation.DISTANCE, MeasurementSpace.PROJECTED, direction)


PERPENDICULAR = kind(MeasurementDirection.PERPENDICULAR)
HORIZONTAL = kind(MeasurementDirection.HORIZONTAL)
VERTICAL = kind(MeasurementDirection.VERTICAL)

#: A sheet whose across is X and whose up is Z, seen down Y.
AXES = ViewAxes(right=create_v3(1, 0, 0), up=create_v3(0, 0, 1),
                look=create_v3(0, 1, 0))


def line(at, direction, interval):
    return MeasureSpan(at=v(at), direction=v(direction), interval=interval)


def point(at):
    return MeasureSpan(at=v(at))


def face_span(at, normal):
    return MeasureSpan(at=v(at), normal=v(normal))


def placed(anchor):
    """An anchor as a plain triple. A span holds vectors; assertions read tuples."""
    return tuple(anchor)


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

        assert placed(anchors[0]) == (3, 0, 7)
        assert anchors[1] == pytest.approx((3, 0, 0))

    def test_whichever_way_round_the_pair_arrives(self):
        anchors = distance_anchors(
            line((0, 0, 0), (1, 0, 0), (0, 10)), point((3, 0, 7)), PERPENDICULAR)

        assert anchors[0] == pytest.approx((3, 0, 0))
        assert placed(anchors[1]) == (3, 0, 7)

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

        assert (placed(anchors[0]), placed(anchors[1])) == ((1, 2, 3), (4, 5, 6))


class TestAlongTheSheetsOwnDirections:
    """Horizontal and vertical: the first stays, the second comes to its axis."""

    def test_horizontal_runs_across_the_sheet(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), HORIZONTAL, AXES)

        assert placed(anchors[0]) == (0, 0, 0)
        assert anchors[1] == pytest.approx((4, 0, 0))

    def test_and_reads_the_separation_across_it(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), HORIZONTAL, AXES)
        span = run(anchors)

        assert dot(span, AXES.up) == pytest.approx(0)
        assert abs(dot(span, AXES.right)) == pytest.approx(4)

    def test_vertical_runs_up_the_sheet(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), VERTICAL, AXES)
        span = run(anchors)

        assert dot(span, AXES.right) == pytest.approx(0)
        assert abs(dot(span, AXES.up)) == pytest.approx(9)

    def test_the_depth_between_them_is_not_part_of_it(self):
        # A drawing is a projection: what separates two features along the line
        # of sight is not what the sheet shows.
        anchors = distance_anchors(point((0, 5, 0)), point((4, -5, 9)), HORIZONTAL, AXES)

        assert abs(dot(run(anchors), AXES.right)) == pytest.approx(4)


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
                    # The measurement carries the wire form, which is what
                    # goes to the viewer; the rules take the primitive, so this
                    # converts exactly as the runner does.
                    admitted = projected_kinds(
                        runner._geometry_from_wire(measure["a"].get("geometry")),
                        runner._geometry_from_wire(measure["b"].get("geometry")),
                        axes.look)
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
                askew = self._square_to(measure, end, axes.look)
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

        assert placed(anchors[0]) == (0, -0.6, 0.05)
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
                    hit.feature, hit.owner, timber, hit.feature.locate_simple_unbounded(hit.owner),
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
            name="a", faces=(PrismFace.FRONT, PrismFace.RIGHT))

        extent = arris.get_extent(self._box())

        assert extent.ends is not None
        first, second = extent.ends
        assert abs(float(second[2, 0]) - float(first[2, 0])) == pytest.approx(0.4)

    def test_and_its_anchor_is_between_them(self):
        from kumiki.cutcsg import PrismFace, SimpleRectangularPrismEdgeFeature

        extent = SimpleRectangularPrismEdgeFeature(
            name="a", faces=(PrismFace.FRONT, PrismFace.RIGHT)).get_extent(self._box())

        assert float(extent.anchor[2, 0]) == pytest.approx(0.2)

    def test_opposite_faces_form_no_arris_and_are_not_invented(self):
        from kumiki.cutcsg import PrismFace, SimpleRectangularPrismEdgeFeature

        with pytest.warns(UserWarning, match="meet in no arris"):
            arris = SimpleRectangularPrismEdgeFeature(
                name="a", faces=(PrismFace.LEFT, PrismFace.RIGHT))

        assert arris.get_extent(self._box()) is None

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
            name="a", faces=(PrismFace.FRONT, PrismFace.RIGHT))

        span = runner._declared_line_span(arris, box, arris.locate_simple_unbounded(box))

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
            name="a", faces=(PrismFace.FRONT, PrismFace.RIGHT))

        assert runner._declared_line_span(arris, endless, arris.locate_simple_unbounded(endless)) is None


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

        source = inspect.getsource(runner._pick_placement)

        assert "_resolve_anchor_placed" in source
        assert "distance_anchors" in source
        # And an angle is placed by the same rules from the same spans, rather
        # than by a second derivation in the viewer.
        assert "angle_rays" in source

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

        # `settled` rides along with the placement -- what the measurement
        # would come to, so the preview shows the number the finished one will
        # carry rather than working it out a second time in the viewer.
        nothing = {"anchors": None, "angle": None, "settled": None}
        assert runner._pick_placement(None, None, None, {}, None) == nothing
        assert runner._pick_placement(
            None, None, None, {"heldReference": {"timber": "t"}}, None) == nothing


class TestAPlacedAnchorStaysPlaced:
    """A measurement carrying its own plane does not move when the camera does.

    Its ends were decided once, against that plane. Drawing it says where those
    points land in this view and nothing more -- the viewer used to re-square
    them against the LIVE camera, which is a no-op only while the camera IS the
    plane. In the 3D view it is not, so the anchors wandered off their features
    as you orbited.
    """

    @pytest.fixture
    def resolved(self):
        import importlib.util
        import sys
        from pathlib import Path
        from tests.testing_shavings import load_module

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_stable", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_stable"] = runner
        spec.loader.exec_module(runner)
        frame = load_module(
            "stable_fixture", root / "kigumi" / "test-fixtures" / "measured_frame.py"
        ).build_frame()
        return runner, frame

    LOOKS = [[0, 1, 0], [1, 0, 0], [0.577, 0.577, 0.577], [0, -1, 0]]

    def _anchors_under_each_camera(self, runner, frame, measure):
        pinned = dict(measure)
        pinned["plane"] = {"at": [0, 0, 0], "normal": [0, 1, 0]}
        seen = []
        for look in self.LOOKS:
            out = runner._resolve_measurement(
                frame, pinned,
                {"look": look, "right": [1, 0, 0], "up": [0, 0, 1]})
            if out.get("unresolved"):
                continue
            seen.append((tuple(out["a"]["at"]), tuple(out["b"]["at"])))
        return seen

    def _measurements(self, runner, frame):
        for drawing in runner.collect_drawings(frame, None, []):
            for viewport in drawing.get("viewports") or []:
                for measure in viewport.get("measurements") or []:
                    if not measure.get("unresolved"):
                        yield measure

    def test_the_fixture_has_measurements_to_check(self, resolved):
        runner, frame = resolved

        assert list(self._measurements(runner, frame))

    def test_the_anchors_are_the_same_from_every_direction(self, resolved):
        runner, frame = resolved

        for measure in self._measurements(runner, frame):
            seen = self._anchors_under_each_camera(runner, frame, measure)

            assert len(set(seen)) == 1, (
                f"{measure['a'].get('feature')}/{measure['b'].get('feature')} moved")

    def test_and_a_measurement_with_no_plane_does_follow_the_viewport(self, resolved):
        # The other half of the rule: with nothing written, the viewport's own
        # plane is what it is entitled to mean, so it SHOULD differ by view.
        runner, frame = resolved
        measure = next(iter(self._measurements(runner, frame)))
        without = dict(measure)
        without.pop("plane", None)

        seen = []
        for look in self.LOOKS:
            out = runner._resolve_measurement(
                frame, without, {"look": look, "right": [1, 0, 0], "up": [0, 0, 1]})
            seen.append(out.get("unresolved") or tuple(out["a"]["at"]))

        assert len(set(map(str, seen))) > 1


class TestDroppingAPerpendicularOntoAFace:
    """In 3D a face is a PLANE, and a distance to one is square to it.

    On a sheet a face is only measurable seen edge-on, where it draws as a line,
    so the anchor rules had two shapes and both ends of any pair were lines. In
    the 3D view nothing is projected away: a face has two directions to be
    square to rather than one, and putting it through the two-lines rule --
    which shares a station along a single direction -- left the dimension
    between an edge and the face it runs parallel to leaning by however far the
    two were offset in the other direction.
    """

    THREE_D = None  # built in setup_method, to keep the import local

    def setup_method(self):
        from kumiki.drawing import (MeasurementKind, MeasurementOperation,
                                    MeasurementSpace)

        self.THREE_D = MeasurementKind(
            MeasurementOperation.DISTANCE, MeasurementSpace.THREE_D)

    def _anchors(self, first, second):
        from kumiki.drawing import distance_anchors

        return distance_anchors(first, second, self.THREE_D)

    def _along(self, a, b):
        return tuple(round(b[i] - a[i], 9) for i in range(3))

    def test_an_edge_parallel_to_a_face_measures_square_to_it(self):
        face = face_span((0, 0, 0), (0, 0, 1))
        # Offset in x and in y, and the y offset is the one the two-lines rule
        # could not remove: it shares a station along x only.
        edge = line((500, 300, 100), (1, 0, 0), (0.0, 200.0))

        at_face, at_edge = self._anchors(face, edge)

        assert self._along(at_face, at_edge) == (0.0, 0.0, 100.0)

    def test_and_the_same_the_other_way_round(self):
        face = face_span((0, 0, 0), (0, 0, 1))
        edge = line((500, 300, 100), (1, 0, 0), (0.0, 200.0))

        at_edge, at_face = self._anchors(edge, face)

        assert self._along(at_face, at_edge) == (0.0, 0.0, 100.0)

    def test_the_edge_anchor_is_on_the_edge(self):
        face = face_span((0, 0, 0), (0, 0, 1))
        edge = line((500, 300, 100), (1, 0, 0), (0.0, 200.0))

        _, at_edge = self._anchors(face, edge)

        # The middle of what survives of it, which is where a reader points.
        assert placed(at_edge) == (600.0, 300.0, 100.0)

    def test_a_point_and_a_face(self):
        face = face_span((0, 0, 0), (0, 0, 1))
        corner = point((120, -45, 70))

        at_point, at_face = self._anchors(corner, face)

        assert placed(at_point) == (120, -45, 70)
        assert self._along(at_face, at_point) == (0.0, 0.0, 70.0)

    def test_two_parallel_faces(self):
        near = face_span((10, 20, 0), (0, 0, 1))
        far = face_span((900, -400, 63.5), (0, 0, 1))

        at_near, at_far = self._anchors(near, far)

        assert self._along(at_near, at_far) == (0.0, 0.0, 63.5)

    def test_two_edges_still_share_a_station(self):
        # The rule that was already right is left alone: neither end is a plane,
        # so nothing above applies.
        one = line((0, 0, 0), (1, 0, 0), (0.0, 100.0))
        other = line((0, 50, 0), (1, 0, 0), (0.0, 100.0))

        at_one, at_other = self._anchors(one, other)

        assert self._along(at_one, at_other) == (0.0, 50.0, 0.0)


class TestAFaceIsOnlyAPlaneInTheSolid:
    """On a sheet it stays the line it draws as.

    `_measure_span` takes the space as an argument, and the name it first took
    was already the name of the timber's own CSG a few lines below -- so the
    check was always true, and every face came back a plane in drawings too.
    """

    def _span(self, in_three_d):
        import importlib.util
        import sys
        from pathlib import Path
        from tests.testing_shavings import load_module

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_space", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_space"] = runner
        spec.loader.exec_module(runner)
        frame = load_module(
            "space_fixture", root / "kigumi" / "test-fixtures" / "measured_frame.py"
        ).build_frame()

        measures = [measure
                    for drawing in runner.collect_drawings(frame, None, [])
                    for viewport in (drawing.get("viewports") or [])
                    for measure in (viewport.get("measurements") or [])
                    if not measure.get("unresolved")]
        assert measures, "the fixture has no measurements to take a span from"
        placed = runner._resolve_anchor_placed(
            frame, measures[0].get("a"), [0, 1, 0], in_three_d)
        assert placed is not None
        return placed[1]

    def test_on_a_sheet_a_face_is_not_a_plane(self):
        assert self._span(False).is_plane is False

    def test_in_three_d_it_is(self):
        assert self._span(True).is_plane is True


class TestWhereAnAngleSits:
    """A corner, and which of its two supplementary angles is meant.

    The arc used to be built in the viewer from each feature's own anchor and
    its own `direction` -- which for a face in 3D was its NORMAL. The
    vertex was then wherever two unrelated screen lines happened to cross, often
    touching neither feature, and the value was acos of an absolute dot, which
    cannot tell 45 degrees from 135.
    """

    def _span(self, **fields):
        from kumiki.drawing import MeasureSpan

        return MeasureSpan(**{key: v(value) if key in ('at', 'normal', 'direction')
                              else value for key, value in fields.items()})

    def _rays(self, first, second):
        from kumiki.drawing import angle_rays

        return angle_rays(first, second)

    def _corner(self, first, second):
        """The rays, insisting there are some. For the pairs that make a corner."""
        from tests.testing_shavings import present

        return present(self._rays(first, second), "rays for this pair")

    def _value(self, rays):
        from kumiki.drawing import angle_between

        return angle_between(rays)

    def test_the_vertex_sits_on_the_line_the_two_faces_share(self):
        # Both planes pass through the z axis, so the corner is the z axis.
        rays = self._corner(
            self._span(at=(-300, 0, 500), normal=(0, 1, 0)),
            self._span(at=(0, -300, 500), normal=(1, 0, 0)))

        vertex = rays.vertex
        assert abs(vertex[0]) < 1e-9 and abs(vertex[1]) < 1e-9

    def test_and_near_the_features_rather_than_anywhere_on_it(self):
        # The corner line runs the whole height of the frame; the arc belongs
        # beside the two faces, which sit at z = 500.
        rays = self._corner(
            self._span(at=(-300, 0, 500), normal=(0, 1, 0)),
            self._span(at=(0, -300, 500), normal=(1, 0, 0)))

        assert abs(rays.vertex[2] - 500) < 1e-9

    def test_each_ray_lies_in_its_own_face(self):
        first = self._span(at=(-300, 0, 500), normal=(0, 1, 0))
        second = self._span(at=(0, -300, 500), normal=(1, 0, 0))

        rays = self._corner(first, second)

        # Square to the face's normal is what "in the face" means.
        assert abs(sum(rays.opens_from[i] * first.normal[i] for i in range(3))) < 1e-9
        assert abs(sum(rays.opens_to[i] * second.normal[i] for i in range(3))) < 1e-9

    def test_which_side_the_material_is_on_decides_the_angle(self):
        """The same two planes read 45 or 135 by where the faces actually are.

        This is the whole reason the rays exist: the normals are identical in
        both cases, so anything derived from them alone gives one answer to two
        different questions.
        """
        slope = (0.7071067811865476, 0.7071067811865476, 0)

        shallow = self._rays(self._span(at=(-300, 0, 0), normal=(0, 1, 0)),
                             self._span(at=(-300, 300, 0), normal=slope))
        wide = self._rays(self._span(at=(300, 0, 0), normal=(0, 1, 0)),
                          self._span(at=(-300, 300, 0), normal=slope))

        assert round(self._value(shallow), 6) == 45.0
        assert round(self._value(wide), 6) == 135.0

    def test_two_edges_meeting_at_a_corner_open_away_from_it(self):
        along = self._span(at=(0, 0, 0), direction=(1, 0, 0), interval=(0.0, 400.0))
        up = self._span(at=(0, 0, 0), direction=(0, 1, 0), interval=(0.0, 400.0))

        rays = self._corner(along, up)

        assert [round(v, 6) for v in rays.vertex] == [0.0, 0.0, 0.0]
        # Each ray runs along its own edge, into the part that exists.
        assert [round(v, 6) for v in rays.opens_from] == [1.0, 0.0, 0.0]
        assert [round(v, 6) for v in rays.opens_to] == [0.0, 1.0, 0.0]

    def test_skew_edges_stand_between_them(self):
        # Two edges that never meet. The nearest approach is the honest place.
        along = self._span(at=(0, 0, 0), direction=(1, 0, 0), interval=(0.0, 400.0))
        over = self._span(at=(0, 0, 400), direction=(0, 1, 0), interval=(0.0, 400.0))

        rays = self._corner(along, over)

        assert [round(v, 6) for v in rays.vertex] == [0.0, 0.0, 200.0]

    def test_the_vertex_is_kept_on_the_edges(self):
        """Clamped to what survives, so the arc lands on the timber.

        Two edges can come nearest each other far past the end of both.
        """
        along = self._span(at=(0, 0, 0), direction=(1, 0, 0), interval=(0.0, 100.0))
        over = self._span(at=(900, 0, 50), direction=(0, 1, 0), interval=(0.0, 100.0))

        rays = self._corner(along, over)

        # x is clamped to the end of the first edge, not carried out to 900.
        assert rays.vertex[0] <= 900

    def test_an_edge_running_into_a_face(self):
        face = self._span(at=(0, 0, 0), normal=(0, 0, 1))
        into = self._span(at=(100, 100, 300), direction=(0, 0.7071067811865476,
                                                        -0.7071067811865476),
                          interval=(0.0, 500.0))

        rays = self._corner(face, into)

        # It crosses the face at z = 0.
        assert abs(rays.vertex[2]) < 1e-6
        assert round(self._value(rays), 4) == 45.0

    def test_parallel_faces_make_no_corner(self):
        assert self._rays(self._span(at=(0, 0, 0), normal=(0, 0, 1)),
                          self._span(at=(0, 0, 100), normal=(0, 0, 1))) is None

    def test_parallel_edges_make_no_corner(self):
        assert self._rays(
            self._span(at=(0, 0, 0), direction=(1, 0, 0), interval=(0.0, 100.0)),
            self._span(at=(0, 50, 0), direction=(1, 0, 0), interval=(0.0, 100.0))) is None

    def test_an_edge_straddling_the_vertex_asks_the_other_edge_s_normal(self):
        """Where the feature REACHES says nothing, so a normal decides instead.

        An edge crossing the corner reaches both ways. It is the OTHER edge's
        outward normal that settles it, not its own: an edge's normal is square
        to the edge and so cannot choose a direction ALONG it. What it can
        choose is which side of ITSELF the arc opens on, which is the other ray
        -- and the angle wanted is the one with both timbers in it.

        Deliberately LOPSIDED about the vertex. Symmetric, the fallback (the
        longer side) and the normal happen to agree, and the test would pass
        with this rule taken out.
        """
        # Reaches 100 one way and 300 the other, so "the longer side" says +x.
        crossing = self._span(at=(-100, 0, 0), direction=(1, 0, 0),
                              interval=(0.0, 400.0), outward=(0, -1, 0))
        # Its material lies on -x, so the arc should open that way instead.
        other = self._span(at=(0, -200, 0), direction=(0, 1, 0),
                           interval=(0.0, 400.0), outward=(1, 0, 0))

        rays = self._corner(crossing, other)

        assert [round(v, 6) for v in rays.opens_from] == [-1.0, 0.0, 0.0]

    def test_and_with_no_normal_to_ask_it_takes_the_longer_side(self):
        # Nothing said which side the material is on, so the arc goes with the
        # part of the edge there is more of, rather than refusing to draw.
        crossing = self._span(at=(-100, 0, 0), direction=(1, 0, 0),
                              interval=(0.0, 400.0))
        other = self._span(at=(0, -200, 0), direction=(0, 1, 0),
                           interval=(0.0, 400.0))

        rays = self._corner(crossing, other)

        assert [round(v, 6) for v in rays.opens_from] == [1.0, 0.0, 0.0]


class TestAFeatureOnALabelledRoot:
    """Pickable and then unresolvable, which showed as a measurement in red.

    Navigation records a label only when it steps ONTO a child, so a feature
    declared on a labelled ROOT comes back with an empty path. The resolver
    refused an empty path on a labelled node, so that feature could be picked,
    measured from, and then never found again -- the measurement was written and
    immediately broke. Every rafter in a frame has a labelled root.
    """

    def _runner_and_frame(self):
        import importlib.util
        import sys
        from pathlib import Path
        from tests.testing_shavings import load_module

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kigumi_runner_rooted", root / "kigumi" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        sys.modules["kigumi_runner_rooted"] = runner
        spec.loader.exec_module(runner)
        frame = load_module(
            "rooted_fixture", root / "kigumi" / "test-fixtures" / "measured_frame.py"
        ).build_frame()
        return runner, frame

    def _labelled_root(self, runner, frame):
        """A cut timber whose root carries a label AND declares features."""
        for cut_timber in frame.cut_timbers:
            roots, _ = runner._roots_for_path(cut_timber, ())
            for root in roots:
                if runner._label_name(root) is not None and root.get_declared_features():
                    return cut_timber, root
        return None, None

    def test_the_fixture_has_one_to_check(self):
        # Without this the tests below would pass by being about nothing.
        runner, frame = self._runner_and_frame()

        cut_timber, root = self._labelled_root(runner, frame)

        assert root is not None
        assert runner._label_name(root) is not None

    def test_an_empty_path_means_the_node_you_are_on(self):
        runner, frame = self._runner_and_frame()
        _, root = self._labelled_root(runner, frame)

        assert runner._find_csg_by_labels(root, ()) is root

    def test_so_a_feature_it_declares_can_be_found(self):
        runner, frame = self._runner_and_frame()
        cut_timber, root = self._labelled_root(runner, frame)
        name = root.get_declared_features()[0].name

        found = runner._find_declared_feature(
            cut_timber, runner.deserialize_feature_path(
                {"timber": cut_timber.name, "csgPath": [], "feature": name}).ref)

        assert found is not None
        assert found[0].name == name

    def test_and_a_measurement_to_it_resolves(self):
        # The whole point: picked, written, and still findable afterwards.
        runner, frame = self._runner_and_frame()
        cut_timber, root = self._labelled_root(runner, frame)
        name = root.get_declared_features()[0].name
        entries, _ = runner._assign_member_keys(frame)
        member = next(e["memberKey"] for e in entries
                      if e["cutTimber"] is cut_timber)

        placed = runner._resolve_anchor_placed(
            frame, {"timber": member, "csgPath": [], "feature": name}, [0, 0, 1])

        assert placed is not None


class TestAnObliqueCornerIsStillTheCorner:
    """The vertex lies on both faces, whatever angle they meet at.

    TestWhereAnAngleSits only ever uses perpendicular planes through the z axis,
    which is the one shape `_plane_crossing` got right: its closed form divides
    by the SQUARED length of the cross of the two normals, and that is 1 only
    when the two meet square. Off square, the corner came back scaled toward the
    world origin by the sine between them -- so a braced joint two metres out had
    its arc drawn a hundred millimetres off the timber.
    """

    #: Far enough from the origin that a scaled corner is plainly off the face.
    CORNER = (2000.0, 0.0, 1500.0)

    def _faces(self, degrees_apart):
        from kumiki.drawing import MeasureSpan

        # Two planes through CORNER, their normals `degrees_apart`. Each holds a
        # point along its own face rather than the corner itself, which is what
        # a cropped centroid is.
        turn = math.radians(degrees_apart)
        return (
            face_span((self.CORNER[0], 300.0, self.CORNER[2]), (0, 1, 0)),
            face_span((self.CORNER[0], -100.0, self.CORNER[2]),
                      (0, math.cos(turn), math.sin(turn))),
        )

    def _off_the_faces(self, point, first, second):
        """How far `point` sits off each plane. Zero on both means it is on the corner."""
        from kumiki.drawing import _dot, _unit

        return tuple(
            abs(_dot(_unit(span.normal),
                     [point[i] - span.at[i] for i in range(3)]))
            for span in (first, second)
        )

    @pytest.mark.parametrize("degrees_apart", [90, 60, 45, 30, 15])
    def test_the_vertex_lies_on_both_faces(self, degrees_apart):
        from kumiki.drawing import angle_rays
        from tests.testing_shavings import present

        first, second = self._faces(degrees_apart)

        rays = present(angle_rays(first, second), "rays for two faces at an angle")

        off_first, off_second = self._off_the_faces(rays.vertex, first, second)
        assert off_first == pytest.approx(0, abs=1e-6)
        assert off_second == pytest.approx(0, abs=1e-6)

    def test_and_it_sits_on_the_line_the_two_faces_share(self):
        """Not merely on both planes: on their intersection, which runs along x."""
        from kumiki.drawing import angle_rays
        from tests.testing_shavings import present

        first, second = self._faces(45)

        rays = present(angle_rays(first, second), "rays for two faces at 45 degrees")

        # Plane A is y == 300. Plane B through (2000, -100, 1500) with normal
        # (0, cos45, sin45) is y + z == 1400. So the shared line is y == 300,
        # z == 1100, running along x.
        assert rays.vertex[1] == pytest.approx(300.0, abs=1e-6)
        assert rays.vertex[2] == pytest.approx(1100.0, abs=1e-6)
        assert abs(rays.normal[0]) == pytest.approx(1.0, abs=1e-6)


class TestAPairOfferedAnAngleCanAlwaysSayWhereItIs:
    """The two readings of PARALLEL_EPSILON, and the order they have to keep.

    `kinds_for` asks it of a COSINE and so calls a pair parallel below about 8.1
    degrees: that is the drafting rule, and it decides whether an angle is
    offered. The three rules that place a corner ask it of a SINE and refuse
    below about 0.57: that is a conditioning guard, for a pair that reaches them
    anyway.

    If the guard ever refused a WIDER band than the drafting rule, a pair could
    be offered an angle and then be unable to say where its vertex is -- the
    viewer would light it, the click would take it, and nothing would draw. The
    two were within 2.4 degrees of that once, and by accident rather than by
    anyone having checked.
    """

    #: Angles either side of both thresholds, and well past them.
    APART = [0.1, 0.5, 0.6, 1, 3, 5.7, 5.8, 8, 8.2, 12, 30, 45, 89]

    def _turned(self, degrees_apart, shape):
        from kumiki.drawing import MeasureSpan

        turn = math.radians(degrees_apart)
        second = v((0, math.cos(turn), math.sin(turn)))
        if shape == "planes":
            return (MeasureSpan(at=v((100, 0, 200)), normal=v((0, 1, 0))),
                    MeasureSpan(at=v((100, -50, 200)), normal=second))
        if shape == "lines":
            return (MeasureSpan(at=v((100, 0, 200)), direction=v((0, 1, 0)),
                                interval=(0.0, 300.0)),
                    MeasureSpan(at=v((100, -50, 260)), direction=second,
                                interval=(0.0, 300.0)))
        # A line against a plane runs the other way round: it is parallel to the
        # face when it lies IN it, so the pair crosses as the line tips out.
        return (MeasureSpan(at=v((100, 0, 200)), direction=second,
                            interval=(0.0, 300.0)),
                MeasureSpan(at=v((100, -50, 200)), normal=v((0, 1, 0))))

    @pytest.mark.parametrize("shape", ["planes", "lines", "line and plane"])
    @pytest.mark.parametrize("degrees_apart", APART)
    def test_whenever_an_angle_is_admitted_the_corner_can_be_placed(
            self, shape, degrees_apart):
        from kumiki.drawing import (MeasurementOperation, angle_rays,
                                    three_d_kinds)

        first, second = self._turned(degrees_apart, shape)
        # Ask the table what this pair admits, through the same geometry the
        # spans describe.
        one = self._geometry(first)
        other = self._geometry(second)
        admits_angle = any(kind.operation is MeasurementOperation.ANGLE
                           for kind in three_d_kinds(one, other))

        if not admits_angle:
            return

        assert angle_rays(first, second) is not None, (
            f"{shape} {degrees_apart} degrees apart are offered an angle "
            f"but cannot say where its corner is")

    def _geometry(self, span):
        from kumiki.geometry import Line, Plane

        if span.is_plane:
            return Plane(point=span.at, normal=span.normal)
        return Line(point=span.at, direction=span.direction)

    def test_and_the_guard_refuses_a_narrower_band_than_the_table(self):
        """Stated as the numbers, so moving either epsilon fails here first."""
        from kumiki.drawing import PARALLEL_EPSILON

        # kinds_for asks it of a cosine; the corner guards ask it of a sine.
        drafting = math.degrees(math.acos(1 - PARALLEL_EPSILON))
        corner = math.degrees(math.asin(PARALLEL_EPSILON))

        assert corner < drafting
        assert (drafting, corner) == pytest.approx((8.110, 0.573), abs=1e-3)


class TestALineLyingFlatAlongAFaceTurnsNoCorner:
    """It never crosses the face, so there is no vertex to put an angle on.

    Nor is the pair offered one -- the table calls it parallel and admits only a
    perpendicular distance -- so refusing here agrees with what was on offer.
    """

    FLAT = MeasureSpan(at=v((100, 0, 200)), direction=v((1, 0, 0)),
                       interval=(0.0, 300.0))
    FACE = MeasureSpan(at=v((100, -50, 200)), normal=v((0, 1, 0)))

    def test_the_table_admits_no_angle(self):
        from kumiki.drawing import MeasurementOperation, three_d_kinds
        from kumiki.geometry import Line, Plane

        kinds = three_d_kinds(
            Line(point=self.FLAT.at, direction=self.FLAT.along),
            Plane(point=self.FACE.at, normal=self.FACE.facing))
        assert not any(k.operation is MeasurementOperation.ANGLE for k in kinds)

    @pytest.mark.parametrize("swapped", [False, True])
    def test_and_no_rays_are_placed_either_way_round(self, swapped):
        from kumiki.drawing import angle_rays

        pair = (self.FACE, self.FLAT) if swapped else (self.FLAT, self.FACE)
        assert angle_rays(*pair) is None


class TestAViewWithNothingSaidAboutIt:
    """ViewAxes supplies the defaults, so each one is written down once.

    They used to live at the three use sites, and one was wrong: the fallback
    for a missing `up` was the same (1, 0, 0) as for a missing `right`, so a
    vertical distance with no up axis ran along X.
    """

    def test_a_vertical_distance_runs_up_z(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), VERTICAL)

        assert placed(anchors[1]) == (0.0, 0.0, 9.0)

    def test_a_horizontal_one_runs_along_x(self):
        anchors = distance_anchors(point((0, 0, 0)), point((4, 0, 9)), HORIZONTAL)

        assert placed(anchors[1]) == (4.0, 0.0, 0.0)

    def test_every_shape_of_missing_axis_reads_the_same(self):
        from kumiki.drawing import DEFAULT_VIEW, ViewAxes

        for given in (None, {}, {"look": None, "right": None, "up": None}):
            assert ViewAxes.from_wire(given) == DEFAULT_VIEW
