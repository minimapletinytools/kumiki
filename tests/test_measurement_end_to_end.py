"""Making a measurement, the way the viewer makes one.

Every other test here checks a rule, a span or a payload on its own. These drive
the whole chain the runner owns -- pick a feature, hold it, pick a second, read
the verdict, write it, resolve it -- because that is where the parts have gone
wrong together: a feature that picked and then would not resolve, a verdict
judged in the wrong space, anchors placed by the rule for a sheet in the solid.

The viewer's half cannot run here (it wants a browser), so this stops at what
the runner answers. That is the half where the geometry lives.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.testing_shavings import load_module


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


class TestAMeasurementMadeInTheThreeDView:
    """Two faces, in the solid, through the reserved drawing."""

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
        # Structured, and in the SOLID -- a bare name could not say which of the
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

    def test_a_sheet_and_the_solid_disagree_about_the_same_pair(self, viewer):
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
