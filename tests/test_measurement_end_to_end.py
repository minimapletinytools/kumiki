"""Making a measurement, the way the viewer makes one.

Every other test here checks a rule, a span or a payload on its own. These drive
the whole chain the runner owns -- pick a feature, hold it, pick a second, read
the verdict, write it, resolve it -- because that is where the parts have gone
wrong together: a feature that picked and then would not resolve, a verdict
judged in the wrong space, anchors placed by the rule for a sheet in 3D.

The viewer's half cannot run here (it wants a browser), so this stops at what
the runner answers. That is the half where the geometry lives.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.testing_shavings import load_module


from kumiki.geometry import Line, Plane, Point
from kumiki.rule import create_v3


def at(position):
    """A point feature, where the tests used to write a `point` mapping."""
    return Point(position=create_v3(*position))


def edge(through, direction):
    return Line(point=create_v3(*through), direction=create_v3(*direction))


def plane(through, normal):
    return Plane(point=create_v3(*through), normal=create_v3(*normal))



def _load_runner():
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "kigumi_runner_end_to_end", root / "kigumi" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_end_to_end"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


class Viewer:
    """As much of the viewer as the runner can see: a mesh cache and a pointer."""

    def __init__(self, frame):
        from kumiki.triangles import triangulate_cutcsg

        self.frame = frame
        entries, _ = runner._assign_member_keys(frame)
        self.members = [entry["memberKey"] for entry in entries]
        self._points = {}
        cache = {}
        for entry in entries:
            cut_timber, key = entry["cutTimber"], entry["memberKey"]
            local = cut_timber.render_timber_with_cuts_csg_local()
            points = []
            for triangle in triangulate_cutcsg(local).mesh.triangles:
                corners = [[float(triangle[k][i]) for i in range(3)] for k in range(3)]
                middle = [sum(corner[i] for corner in corners) / 3 for i in range(3)]
                for local_point in corners + [middle]:
                    world = cut_timber.timber.transform.local_to_global(
                        runner._to_v3(local_point))
                    points.append([float(world[i, 0]) for i in range(3)])
            flat = [value for point in points for value in point]
            cache[key] = {
                "local_csg": local,
                "cut_timber": cut_timber,
                "mesh": {"vertices": flat, "indices": list(range(len(flat) // 3))},
            }
            self._points[key] = points

        frame_ref = frame

        class Slot:
            mesh_cache = cache
            frame = frame_ref

        class State:
            _active = Slot()

        self._state, self._slot = State(), Slot()
        self.pending = []

    def pick(self, member, feature, held=None):
        """Click every point on a member until one resolves to `feature`."""
        payload = dict(held or {})
        for point in self._points[member]:
            answer = runner._handle_find_csg_at_point(
                self._state,
                {"memberKey": member, "point": point, "currentPath": [],
                 "ctrlClick": False, **payload},
                self._slot)
            if answer.get("featureLabel") == feature and answer.get("geometry"):
                return answer
        raise AssertionError(f"no point on {member} resolved to {feature}")

    def holding(self, first, look, space):
        """What the viewer sends once an end is held."""
        return {
            "heldGeometry": first["geometry"],
            "heldAt": first["at"],
            "heldReference": first["reference"],
            "look": look,
            "right": [1, 0, 0],
            "up": [0, 0, 1],
            "space": space,
        }

    def write(self, drawing_id, viewport_id, first, second, verdict):
        runner.add_measurement(
            self.frame, None, self.pending, drawing_id, viewport_id,
            {
                "a": first["reference"],
                "b": second["reference"],
                "kind": verdict["kinds"][0],
                "measureId": None,
                "plane": verdict.get("plane"),
                "placement": None,
            },
        )

    def measurements(self, drawing_id, viewport_id):
        """What is on a viewport, or nothing if there is no such viewport yet.

        The 3D drawing is made when the first measurement is put in it, so
        before that it does not exist -- which is "no measurements", not an
        error.
        """
        for drawing in runner.collect_drawings(self.frame, None, self.pending):
            if drawing.get("id") != drawing_id:
                continue
            for viewport in drawing.get("viewports") or []:
                if viewport.get("id") == viewport_id:
                    return viewport.get("measurements") or []
        return []

    def has_drawing(self, drawing_id):
        return any(drawing.get("id") == drawing_id
                   for drawing in runner.collect_drawings(self.frame, None, self.pending))


@pytest.fixture
def viewer():
    root = Path(__file__).resolve().parent.parent
    return Viewer(load_module(
        "end_to_end_fixture",
        root / "kigumi" / "test-fixtures" / "measured_frame.py").build_frame())


THREE_D = runner.THREE_D_MEASUREMENTS_ID
THREE_D_VIEWPORT = "main"
LOOK = [-0.577, -0.577, -0.577]


def _three_d_distance():
    from kumiki.drawing import MeasurementKind, MeasurementOperation, MeasurementSpace

    return MeasurementKind(MeasurementOperation.DISTANCE, MeasurementSpace.THREE_D)


THREE_D_DISTANCE = _three_d_distance()


class TestAMeasurementMadeInTheThreeDView:
    """Two faces, in 3D, through the reserved drawing."""

    def test_two_parallel_faces_admit_a_distance(self, viewer):
        member = viewer.members[0]
        first = viewer.pick(member, "rough.front")
        second = viewer.pick(member, "rough.back",
                             viewer.holding(first, LOOK, "3d"))

        verdict = second["verdict"]
        assert [kind["operation"] for kind in verdict["kinds"]] == ["distance"]
        assert verdict["kinds"][0]["space"] == "3d"

    def test_and_it_says_where_both_ends_attach(self, viewer):
        member = viewer.members[0]
        first = viewer.pick(member, "rough.front")
        second = viewer.pick(member, "rough.back",
                             viewer.holding(first, LOOK, "3d"))

        anchors = second["verdict"]["anchors"]
        assert anchors is not None
        assert len(anchors["a"]) == 3 and len(anchors["b"]) == 3

    def test_two_faces_that_meet_admit_an_angle(self, viewer):
        one, other = viewer.members
        first = viewer.pick(one, "rough.front")
        second = viewer.pick(other, "rough.front",
                             viewer.holding(first, LOOK, "3d"))

        verdict = second["verdict"]
        assert [kind["operation"] for kind in verdict["kinds"]] == ["angle"]

    def test_an_angle_comes_with_the_corner_to_draw_it_in(self, viewer):
        # A vertex, two rays, and the plane they span -- so the arc is placed
        # from the features rather than from wherever two screen lines cross.
        one, other = viewer.members
        first = viewer.pick(one, "rough.front")
        second = viewer.pick(other, "rough.front",
                             viewer.holding(first, LOOK, "3d"))

        angle = second["verdict"]["angle"]
        assert angle is not None
        for key in ("vertex", "from", "to", "normal"):
            assert len(angle[key]) == 3, key

    def test_a_distance_gets_no_corner_and_an_angle_no_anchors(self, viewer):
        # Neither gets the other's placement: they are placed by different
        # rules and carrying both would mean one of them is never right.
        one, other = viewer.members
        held = viewer.pick(one, "rough.front")
        distance = viewer.pick(one, "rough.back", viewer.holding(held, LOOK, "3d"))
        angle = viewer.pick(other, "rough.front", viewer.holding(held, LOOK, "3d"))

        assert distance["verdict"]["angle"] is None
        assert angle["verdict"]["anchors"] is None

    def test_the_reserved_drawing_does_not_exist_until_it_holds_something(self, viewer):
        # It is made when the first 3D measurement is put in it, so a file with
        # none has no such drawing to show in the tree.
        member = viewer.members[0]
        assert viewer.has_drawing(THREE_D) is False

        first = viewer.pick(member, "rough.front")
        second = viewer.pick(member, "rough.back", viewer.holding(first, LOOK, "3d"))
        viewer.write(THREE_D, THREE_D_VIEWPORT, first, second, second["verdict"])

        assert viewer.has_drawing(THREE_D) is True

    def test_writing_one_makes_it_appear_where_it_was_asked_for(self, viewer):
        member = viewer.members[0]
        first = viewer.pick(member, "rough.front")
        second = viewer.pick(member, "rough.back", viewer.holding(first, LOOK, "3d"))

        before = len(viewer.measurements(THREE_D, THREE_D_VIEWPORT))
        viewer.write(THREE_D, THREE_D_VIEWPORT, first, second, second["verdict"])

        assert len(viewer.measurements(THREE_D, THREE_D_VIEWPORT)) == before + 1

    def test_and_it_still_resolves_once_written(self, viewer):
        """The whole point. A feature that picks and then cannot be found again
        is a measurement that appears and is immediately broken -- which is what
        every timber with a labelled root used to do."""
        member = viewer.members[0]
        first = viewer.pick(member, "rough.front")
        second = viewer.pick(member, "rough.back", viewer.holding(first, LOOK, "3d"))
        viewer.write(THREE_D, THREE_D_VIEWPORT, first, second, second["verdict"])

        written = viewer.measurements(THREE_D, THREE_D_VIEWPORT)[-1]

        assert not written.get("unresolved"), written.get("unresolved")
        assert written["a"]["at"] and written["b"]["at"]
        assert written["a"]["geometry"] and written["b"]["geometry"]

    def test_the_written_kind_is_the_one_the_pick_offered(self, viewer):
        # Structured, and in 3D -- a bare name could not say which of the
        # two angles it meant, and the space decides what the pair admits.
        member = viewer.members[0]
        first = viewer.pick(member, "rough.front")
        second = viewer.pick(member, "rough.back", viewer.holding(first, LOOK, "3d"))
        viewer.write(THREE_D, THREE_D_VIEWPORT, first, second, second["verdict"])

        written = viewer.measurements(THREE_D, THREE_D_VIEWPORT)[-1]

        assert written["kind"] == second["verdict"]["kinds"][0]
        assert written["kind"]["space"] == "3d"

    def test_a_written_distance_ends_square_to_the_face_it_measures(self, viewer):
        """The separation is along the normal, with nothing across it.

        NOT a test that the pair is placed together rather than per feature:
        this fixture is a symmetric prism, so the two answers coincide and it
        could not tell them apart. The discriminating case is synthetic and
        lives in test_measurement_anchors -- an edge offset from a face, where
        placing each end on its own leans the dimension.
        """
        member = viewer.members[0]
        first = viewer.pick(member, "rough.front")
        second = viewer.pick(member, "rough.back", viewer.holding(first, LOOK, "3d"))
        viewer.write(THREE_D, THREE_D_VIEWPORT, first, second, second["verdict"])

        written = viewer.measurements(THREE_D, THREE_D_VIEWPORT)[-1]
        gap = [written["b"]["at"][i] - written["a"]["at"][i] for i in range(3)]
        normal = written["a"]["geometry"]["normal"]

        # Square to the face it is measured from: the parts across the normal
        # are zero, so the whole separation is along it.
        along = sum(gap[i] * normal[i] for i in range(3))
        across = sum((gap[i] - normal[i] * along) ** 2 for i in range(3))
        assert across == pytest.approx(0.0, abs=1e-9)


class TestAPairWithNothingBetweenThem:
    """Two features in the same place measure nothing, and are refused.

    An arris lying ON a face is the ordinary way to reach this -- a tenon cheek
    and the edge that runs along it -- and there are a dozen such pairs on one
    tenoned timber. They admitted a distance, which came to zero, and drew as
    nothing: indistinguishable from a measurement that failed.
    """

    def _degenerate_pair(self, viewer):
        """An arris and the face it lies on, found rather than assumed."""
        import math

        member = viewer.members[0]
        for edge, face in (("arris.0", "tenon_front"), ("arris.1", "tenon_left"),
                           ("arris.2", "tenon_back")):
            try:
                held = viewer.pick(member, edge)
                viewer.pick(member, face, viewer.holding(held, LOOK, "3d"))
            except AssertionError:
                continue
            return member, edge, face
        raise AssertionError("the fixture has no arris lying on a face")

    def test_the_fixture_has_such_a_pair(self, viewer):
        # Without one, everything below passes by never reaching the rule.
        member, edge, face = self._degenerate_pair(viewer)

        assert edge and face and member

    def test_it_is_refused_and_says_why(self, viewer):
        member, edge, face = self._degenerate_pair(viewer)
        held = viewer.pick(member, edge)

        verdict = viewer.pick(member, face, viewer.holding(held, LOOK, "3d"))["verdict"]

        assert verdict["kinds"] == []
        assert verdict["reason"] == "degenerate"

    def test_so_the_hover_paints_it_red_and_the_click_refuses(self, viewer):
        # Both follow from the verdict without either knowing this rule: empty
        # kinds is what the hover draws red and what the click turns away.
        member, edge, face = self._degenerate_pair(viewer)
        held = viewer.pick(member, edge)

        verdict = viewer.pick(member, face, viewer.holding(held, LOOK, "3d"))["verdict"]

        assert verdict is not None, "not an ordinary hover: a measurement IS being made"
        assert verdict["kinds"] == [], "empty, which is what paints it red"

    def test_and_nothing_is_offered_to_place(self, viewer):
        # Neither anchors nor a corner: there is no measurement to place.
        member, edge, face = self._degenerate_pair(viewer)
        held = viewer.pick(member, edge)

        verdict = viewer.pick(member, face, viewer.holding(held, LOOK, "3d"))["verdict"]

        assert verdict["anchors"] is None
        assert verdict["angle"] is None

    def test_a_pair_with_something_between_them_is_untouched(self, viewer):
        # The rule must not reach past the case it is for.
        member = viewer.members[0]
        held = viewer.pick(member, "rough.front")

        verdict = viewer.pick(member, "rough.back",
                              viewer.holding(held, LOOK, "3d"))["verdict"]

        assert [kind["operation"] for kind in verdict["kinds"]] == ["distance"]
        assert verdict["reason"] is None

    def test_what_counts_as_nothing_between_them(self):
        from kumiki.drawing import DEGENERATE_SEPARATION, measures_nothing

        face = plane([0, 0, 0], [0, 0, 1])
        touching = at([5, 7, 0])
        barely = at([5, 7, DEGENERATE_SEPARATION / 10])
        clear = at([5, 7, 50])

        assert measures_nothing(face, touching, THREE_D_DISTANCE) is True
        assert measures_nothing(face, barely, THREE_D_DISTANCE) is True
        assert measures_nothing(face, clear, THREE_D_DISTANCE) is False

    def test_the_features_decide_and_no_anchor_is_computed(self):
        """What a distance comes to is a property of the two geometries.

        A perpendicular distance is the same wherever along the pair you stand,
        so it can be had from the features and the space alone. Asking placed
        ends instead would make a rule about what a measurement IS depend on
        where it happens to be drawn.
        """
        from kumiki.drawing import measures_nothing, pair_separation

        face = plane([0, 0, 0], [0, 0, 1])
        # An arris lying IN that face, running off to one side. Its own point is
        # nowhere near the face's, and the separation is still nothing.
        lying_in_it = edge([900, -40, 0], [1, 0, 0])

        assert pair_separation(face, lying_in_it, THREE_D_DISTANCE) == 0.0
        assert measures_nothing(face, lying_in_it, THREE_D_DISTANCE) is True

    def test_an_angle_measures_no_length_so_the_rule_leaves_it_alone(self):
        from kumiki.drawing import MeasurementKind, MeasurementOperation, MeasurementSpace
        from kumiki.drawing import measures_nothing, pair_separation

        angle = MeasurementKind(MeasurementOperation.ANGLE, MeasurementSpace.THREE_D)
        face = plane([0, 0, 0], [0, 0, 1])
        lying_in_it = edge([900, -40, 0], [1, 0, 0])

        assert pair_separation(face, lying_in_it, angle) is None
        assert measures_nothing(face, lying_in_it, angle) is False

    def test_kinds_do_not_fail_together(self):
        """Two points one above the other: a vertical worth having, no horizontal."""
        from kumiki.drawing import MeasurementDirection as D
        from kumiki.drawing import MeasurementKind, MeasurementOperation, MeasurementSpace
        from kumiki.drawing import measures_nothing

        axes = {"look": (0, -1, 0), "right": (1, 0, 0), "up": (0, 0, 1)}
        below = at([0, 0, 0])
        above = at([0, 0, 50])

        def kind(direction):
            return MeasurementKind(MeasurementOperation.DISTANCE,
                                   MeasurementSpace.PROJECTED, direction)

        assert measures_nothing(below, above, kind(D.HORIZONTAL), axes) is True
        assert measures_nothing(below, above, kind(D.VERTICAL), axes) is False


class TestAMeasurementMadeOnASheet:
    """The same chain in a drawing, where a face is a line seen edge-on."""

    DRAWING = "tenon"
    VIEWPORT = "0.0.0"

    def _look(self, viewer):
        for drawing in runner.collect_drawings(viewer.frame, None, viewer.pending):
            if drawing.get("id") != self.DRAWING:
                continue
            for viewport in drawing.get("viewports") or []:
                if viewport.get("id") == self.VIEWPORT:
                    return viewport["camera"]["look"]
        raise AssertionError("the fixture has no such viewport")

    def test_the_fixture_gives_the_viewport_a_camera(self, viewer):
        # Everything below is judged against it, so without one the tests would
        # be about a sheet nobody is looking at.
        assert len(self._look(viewer)) == 3

    def test_a_pair_is_judged_in_the_sheet_s_space(self, viewer):
        # Two arrises. A FACE is measurable on a sheet only when seen edge-on,
        # and this viewport does not see these ones that way -- which is the
        # rule working, not a shortcoming of the fixture.
        member = viewer.members[0]
        look = self._look(viewer)
        first = viewer.pick(member, "arris.0")
        second = viewer.pick(member, "arris.1",
                             viewer.holding(first, look, "projected"))

        kinds = second["verdict"]["kinds"]
        assert kinds, "two parallel faces seen edge-on should admit something"
        for kind in kinds:
            assert kind["space"] == "projected"

    def test_writing_one_puts_it_on_that_viewport(self, viewer):
        member = viewer.members[0]
        look = self._look(viewer)
        first = viewer.pick(member, "arris.0")
        second = viewer.pick(member, "arris.1",
                             viewer.holding(first, look, "projected"))

        before = len(viewer.measurements(self.DRAWING, self.VIEWPORT))
        viewer.write(self.DRAWING, self.VIEWPORT, first, second, second["verdict"])

        after = viewer.measurements(self.DRAWING, self.VIEWPORT)
        assert len(after) == before + 1
        assert not after[-1].get("unresolved")

    def test_and_it_carries_the_plane_it_was_taken_on(self, viewer):
        # Fixed at creation, so the value cannot drift when the reader moves.
        member = viewer.members[0]
        look = self._look(viewer)
        first = viewer.pick(member, "arris.0")
        second = viewer.pick(member, "arris.1",
                             viewer.holding(first, look, "projected"))
        viewer.write(self.DRAWING, self.VIEWPORT, first, second, second["verdict"])

        written = viewer.measurements(self.DRAWING, self.VIEWPORT)[-1]

        assert written["plane"] is not None
        assert len(written["plane"]["normal"]) == 3

    def test_a_sheet_and_three_d_disagree_about_the_same_pair(self, viewer):
        """The two spaces are not the same question, and this is the proof.

        The same two features, asked about twice. Which space decides what a
        pair admits, and judging one by the other's rule is what made every face
        in the 3D view unmeasurable.
        """
        member = viewer.members[0]
        first = viewer.pick(member, "arris.0")
        sheet = viewer.pick(member, "arris.1",
                            viewer.holding(first, self._look(viewer), "projected"))
        solid = viewer.pick(member, "arris.1",
                            viewer.holding(first, LOOK, "3d"))

        assert sheet["verdict"]["kinds"][0]["space"] == "projected"
        assert solid["verdict"]["kinds"][0]["space"] == "3d"


class TestWhatTheRunnerSettles:
    """The answer sent with a measurement, which the viewer now only reports.

    These rules were the viewer's until it stopped deriving them: what a pair
    admits here, which kind is drawn when none was written, what the thing
    comes to and in what unit, and why there is nothing to draw. They are
    checked here because this is where they live.
    """

    def _runner(self):
        from pathlib import Path
        from tests.testing_shavings import load_module

        root = Path(__file__).resolve().parent.parent
        return load_module("kigumi_runner_settled", root / "kigumi" / "runner.py")

    #: A sheet seen down -y, its across x and its up z.
    AXES = {"look": [0, -1, 0], "right": [1, 0, 0], "up": [0, 0, 1]}

    def _settle(self, one, other, written=None, solid=False, axes=None):
        """What the runner would send for a pair, through its own code."""
        from kumiki.drawing import (MeasurementKind, projected_kinds,
                                    three_d_kinds)

        runner = self._runner()
        axes = self.AXES if axes is None else axes
        look = axes["look"]
        declared = MeasurementKind.from_wire(written)
        admitted = (three_d_kinds(one, other) if solid
                    else projected_kinds(one, other, look))
        kind = declared or (admitted[0] if admitted else None)
        return runner._settled_measurement(
            {"a": {"geometry": one}, "b": {"geometry": other}, "angle": None},
            declared, kind, admitted, solid, look, axes)

    def test_two_points_admit_three_so_there_is_a_choice_to_offer(self):
        settled = self._settle(at([0, 0, 0]), at([1, 0, 1]))

        assert len(settled["available"]) == 3

    def test_the_kind_drawn_is_the_first_when_none_was_written(self):
        settled = self._settle(at([0, 0, 0]), at([1, 0, 1]))

        from kumiki.drawing import MeasurementKind
        from tests.testing_shavings import present

        settled_kind = present(MeasurementKind.from_wire(settled["kind"]), "a settled kind")
        assert settled_kind.name == settled["available"][0]

    def test_a_written_kind_is_what_is_drawn_instead(self):
        settled = self._settle(at([0, 0, 0]), at([1, 0, 1]),
                               written="projected_vertical_distance")

        from kumiki.drawing import MeasurementKind
        from tests.testing_shavings import present

        settled_kind = present(MeasurementKind.from_wire(settled["kind"]), "a settled kind")
        assert settled_kind.name == "projected_vertical_distance"

    def test_a_pair_in_line_is_degenerate_and_still_offers_the_others(self):
        # Refused under the default kind, while horizontal or vertical between
        # the same two points is a real number -- which is the point of
        # carrying the available kinds on a refusal at all.
        settled = self._settle(at([0, 0, 0]), at([0, 5, 0]))

        assert settled["reason"] == "degenerate"
        assert len(settled["available"]) == 3

    def test_a_distance_calls_itself_a_length(self):
        settled = self._settle(at([0, 0, 0]), at([1, 0, 1]))

        assert settled["value"]["unit"] == "length"

    def test_and_an_angle_calls_itself_an_angle(self):
        # Two crossing faces, which admit an angle and nothing else.
        settled = self._settle(plane([0, 0, 0], [0, 0, 1]),
                               plane([0, 0, 0], [1, 0, 0]), solid=True)

        assert settled["available"] == ["angle"]
        assert settled["value"]["unit"] == "angle"

    def test_a_corner_reads_its_angle_rather_than_a_length(self):
        from kumiki.drawing import MeasureSpan, angle_rays

        runner = self._runner()
        first = plane([0, 0, 0], [0, 0, 1])
        second = plane([0, 0, 0], [1, 0, 0])
        from kumiki.drawing import projected_kinds, three_d_kinds
        admitted = three_d_kinds(first, second)
        rays = angle_rays(MeasureSpan(at=first.point, normal=first.normal),
                          MeasureSpan(at=second.point, normal=second.normal))
        settled = runner._settled_measurement(
            {"a": {"geometry": first}, "b": {"geometry": second}, "angle": rays},
            None, admitted[0], admitted, True, self.AXES["look"], self.AXES)

        assert settled["value"] == {"unit": "angle", "value": pytest.approx(90.0)}

    #: An oblique camera, which is what the 3D view always is: no face is seen
    #: exactly edge-on from here.
    OBLIQUE = {"look": [-0.577, -0.577, -0.577], "right": [1, 0, 0], "up": [0, 0, 1]}

    def test_in_the_solid_a_slab_reads_its_whole_thickness(self):
        # Not the part of it that survives a projection: in the solid nothing
        # is projected away.
        settled = self._settle(plane([0, 0, 0], [1, 0, 0]),
                               plane([150, 0, 0], [-1, 0, 0]),
                               solid=True, axes=self.OBLIQUE)

        assert settled["value"] == {"unit": "length", "value": pytest.approx(150.0)}

    def test_and_the_same_pair_judged_as_a_sheet_is_not_measurable(self):
        # Which is what the 3D view used to do, and why a face went red: seen
        # from anywhere oblique, a face is an AREA and covers the view.
        settled = self._settle(plane([0, 0, 0], [1, 0, 0]),
                               plane([0, 0, 0], [0, 0, 1]), axes=self.OBLIQUE)

        assert settled["reason"] == "not-measurable"

    def test_a_kind_this_view_cannot_draw_says_so(self):
        settled = self._settle(at([0, 0, 0]), at([1, 0, 1]), written="projected_angle")

        assert settled["reason"] == "kind-unavailable"


class TestAMeasurementTheRunnerCannotWorkOut:
    """Refused with a reason, and warned about, rather than left to the viewer.

    The viewer used to work an unsettled measurement out for itself, and could
    only judge it against whatever camera was showing: for one carrying no
    plane the same two points then read as their separation from one angle and
    their diagonal from another. That drift is what a measurement's own plane
    exists to prevent, so there is nothing honest to draw and the runner says
    so.

    None of these should happen -- nothing written since planes existed lacks
    one -- which is why each is warned about rather than quietly skipped.
    """

    def _runner(self):
        from pathlib import Path
        from tests.testing_shavings import load_module

        root = Path(__file__).resolve().parent.parent
        return load_module("kigumi_runner_unplaceable", root / "kigumi" / "runner.py")

    def _frame(self):
        from pathlib import Path
        from tests.testing_shavings import load_module

        root = Path(__file__).resolve().parent.parent
        return load_module(
            "unplaceable_fixture",
            root / "kigumi" / "test-fixtures" / "measured_frame.py").build_frame()

    def _a_resolvable_pair(self, runner, frame):
        """Two ends known to resolve, stripped back to their references."""
        for drawing in runner.collect_drawings(frame, None, []):
            for viewport in drawing.get("viewports") or []:
                for measure in viewport.get("measurements") or []:
                    if measure.get("unresolved"):
                        continue
                    if (measure.get("settled") or {}).get("value") is None:
                        continue
                    return {
                        key: {name: value
                              for name, value in (measure.get(key) or {}).items()
                              if name not in ("at", "geometry")}
                        for key in ("a", "b")
                    }
        raise AssertionError("the fixture has no resolvable measurement")

    def _resolve_without_a_plane(self):
        import contextlib
        import io

        runner = self._runner()
        frame = self._frame()
        # No plane of its own, and no viewport camera to borrow one from --
        # which is what a measurement in the reserved 3D drawing written before
        # planes existed looks like.
        bare = self._a_resolvable_pair(runner, frame)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            resolved = runner._resolve_measurement(frame, bare, None)
        return resolved, stderr.getvalue()

    def test_both_ends_resolve_so_this_is_not_the_unresolved_case(self):
        resolved, _ = self._resolve_without_a_plane()

        assert resolved.get("unresolved") is None

    def test_and_yet_it_is_refused_with_a_reason(self):
        resolved, _ = self._resolve_without_a_plane()

        assert resolved["settled"]["reason"] == "no-plane"
        assert resolved["settled"]["value"] is None

    def test_the_runner_warns_about_it(self):
        _, warned = self._resolve_without_a_plane()

        assert "Warning" in warned
        assert "no plane" in warned

    def test_and_names_the_two_ends_so_it_can_be_found(self):
        resolved, warned = self._resolve_without_a_plane()

        for key in ("a", "b"):
            named = (resolved.get(key) or {}).get("feature")
            if named:
                assert named in warned

    def test_a_measurement_it_can_place_is_not_warned_about(self):
        import contextlib
        import io

        runner = self._runner()
        frame = self._frame()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            runner.collect_drawings(frame, None, [])

        assert "not drawing the measurement" not in stderr.getvalue()
