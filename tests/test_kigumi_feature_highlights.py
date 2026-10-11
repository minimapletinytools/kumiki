"""What the runner sends to light features nobody is pointing at: reference features and measurement ends."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from kumiki import CutTimber, Cutting, Frame, HalfSpace, TimberFeature, create_timber, create_v2, create_v3, m, mm
from kumiki.ticket import TimberTicket


def _load_runner():
    runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
    spec = importlib.util.spec_from_file_location("kigumi_runner_highlights", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_highlights"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def _post(*references):
    """1m tall, 100 wide (x) by 200 deep (y), standing at the origin."""
    return create_timber(bottom_position=create_v3(0, 0, 0), length=m(1), size=create_v2(mm(100), mm(200)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0),
                         ticket=TimberTicket(path="post", reference_features=references))


def _segments(feature):
    values = feature["edgePositions"]
    return [[round(v, 6) for v in values[i:i + 6]] for i in range(0, len(values), 6)]


class TestReferenceFeatures:

    def test_none_declared_sends_none(self):
        assert runner._reference_features_payload(_post()) == []

    def test_an_arris_runs_the_timber_s_length(self):
        (edge,) = runner._reference_features_payload(_post(TimberFeature.RIGHT_FRONT_EDGE))

        assert edge["name"] == "right_front_edge" and edge["primary"] is True
        assert _segments(edge) == [[0.05, 0.1, 0.0, 0.05, 0.1, 1.0]]

    def test_a_face_is_its_outline(self):
        (face,) = runner._reference_features_payload(_post(TimberFeature.BACK_FACE))

        corners = {tuple(segment[:3]) for segment in _segments(face)}
        assert corners == {(0.05, -0.1, 0.0), (-0.05, -0.1, 0.0), (-0.05, -0.1, 1.0), (0.05, -0.1, 1.0)}

    def test_the_first_is_the_primary(self):
        found = runner._reference_features_payload(_post(TimberFeature.CENTERLINE, TimberFeature.FRONT_FACE))

        assert [(f["name"], f["primary"]) for f in found] == [("centerline", True), ("front_face", False)]
        assert _segments(found[0]) == [[0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]

    def test_they_are_cropped_to_what_the_cuts_left(self):
        # The top 400mm cut away: the arris stops where the wood does, as a selected edge would.
        timber = _post(TimberFeature.RIGHT_FRONT_EDGE, TimberFeature.CENTERLINE)
        above = HalfSpace(normal=create_v3(0, 0, 1), offset=mm(600))
        root = CutTimber(timber, cuts=[Cutting(timber=timber, negative_csg=above)]).render_timber_with_cuts_csg_local()

        edge, axis = runner._reference_features_payload(timber, root)

        assert _segments(edge) == [[0.05, 0.1, 0.0, 0.05, 0.1, 0.6]]
        # The axis runs through the wood rather than on its surface, and is cropped to the wood.
        assert _segments(axis) == [[0.0, 0.0, 0.0, 0.0, 0.0, 0.6]]

    def test_they_reach_the_layers_payload(self):
        frame = Frame(cut_timbers=[CutTimber(_post(TimberFeature.RIGHT_FRONT_EDGE), cuts=[])])

        (timber,) = runner.serialize_layers(frame)["timbers"]
        assert [f["name"] for f in timber["referenceFeatures"]] == ["right_front_edge"]


class TestFeatureHighlights:

    def _slot(self):
        frame = Frame(cut_timbers=[CutTimber(_post(), cuts=[])])
        return SimpleNamespace(frame=frame, mesh_cache={})

    def _member_key(self, slot):
        (entry,), _ = runner._assign_member_keys(slot.frame)
        return entry["memberKey"]

    def test_an_edge_end_is_its_line(self):
        slot = self._slot()
        reference = {"timber": self._member_key(slot), "csgPath": [], "feature": "rptw.front_right", "type": "EDGE"}

        (lit,) = runner.feature_highlights(slot, [reference])

        assert lit["featureType"] == "EDGE" and lit["highlightEdgeSegments"]

    def test_a_point_end_is_where_it_is(self):
        slot = self._slot()
        reference = {"timber": self._member_key(slot), "csgPath": [], "feature": "rptw.top_right_front", "type": "POINT"}

        (lit,) = runner.feature_highlights(slot, [reference])

        assert lit["featureType"] == "POINT" and len(lit["at"]) == 3

    def test_an_end_that_is_gone_lights_nothing(self):
        slot = self._slot()
        reference = {"timber": self._member_key(slot), "csgPath": [], "feature": "no.such", "type": "FACE"}

        assert runner.feature_highlights(slot, [reference]) == [{"highlightMesh": {"vertices": [], "indices": []}}]


class TestAnEndHiddenInTheView:
    """A drawing's orthographic view measures only what it shows."""

    def _scene(self):
        def post(x, y, name):
            return CutTimber(create_timber(
                bottom_position=create_v3(x, y, 0), length=m(1), size=create_v2(mm(100), mm(100)),
                length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket=name), cuts=[])
        front, behind = post(0, 0, "front"), post(0.02, 0.5, "behind")
        frame = Frame(cut_timbers=[front, behind])
        keys = {entry["timber"].ticket.path: entry["memberKey"] for entry in runner._assign_member_keys(frame)[0]}
        return SimpleNamespace(frame=frame, mesh_cache={}), keys

    def _pick(self, slot, path, name):
        cut = next(c for c in slot.frame.cut_timbers if c.timber.ticket.path == path)
        root = cut.render_timber_with_cuts_csg_local()
        feature = next(f for f in root.get_declared_features() if f.name == name)
        return (feature, root, feature.locate_simple_unbounded(root)), cut.timber

    def _payload(self, keys, held, orthographic=True):
        return {"orthographic": orthographic, "members": list(keys.values()), "look": [0, 1, 0],
                "heldReference": {"timber": keys[held[0]], "csgPath": [], "feature": held[1], "type": "EDGE"}}

    def test_an_end_behind_another_member_is_hidden(self):
        slot, keys = self._scene()
        located, timber = self._pick(slot, "behind", "rptw.back_left")

        assert runner._an_end_is_hidden(located, timber, self._payload(keys, ("front", "rptw.back_right")), slot)

    def test_two_ends_in_sight_are_not(self):
        slot, keys = self._scene()
        located, timber = self._pick(slot, "behind", "rptw.back_right")

        assert not runner._an_end_is_hidden(located, timber, self._payload(keys, ("front", "rptw.back_right")), slot)

    def test_the_held_end_counts_too(self):
        # Held in another view, hidden in this one.
        slot, keys = self._scene()
        located, timber = self._pick(slot, "front", "rptw.back_right")

        assert runner._an_end_is_hidden(located, timber, self._payload(keys, ("behind", "rptw.back_left")), slot)

    def test_a_view_that_is_not_orthographic_hides_nothing(self):
        slot, keys = self._scene()
        located, timber = self._pick(slot, "behind", "rptw.back_left")

        payload = self._payload(keys, ("front", "rptw.back_right"), orthographic=False)
        assert not runner._an_end_is_hidden(located, timber, payload, slot)
