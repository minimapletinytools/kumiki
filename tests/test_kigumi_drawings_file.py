"""Tests for where drawings come from (kigumi/runner.py).

A drawing is asked for in code, or written in the drawings file, or both -- and
which of those it is decides what the tree shows and what a save writes out. The
merge is small and the cases are easy to get subtly wrong, so they are pinned
here rather than found in the viewer.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.timber import Drawing, Frame


def _load_runner():
    """Import kigumi/runner.py by path -- kigumi is not an installed package."""
    runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
    spec = importlib.util.spec_from_file_location("kigumi_runner_drawings", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_drawings"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def _post(path):
    return create_timber(
        bottom_position=create_v3(mm(0), mm(0), mm(0)),
        length=mm(1000),
        size=create_v2(mm(100), mm(100)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket=path,
    )


def _frame(drawings=(), paths=("posts/fl", "posts/fr")):
    built = Frame.from_joints(
        joints=[], additional_unjointed_timbers=[_post(path) for path in paths]
    )
    return Frame(cut_timbers=built.cut_timbers, drawings=list(drawings))


def _write_file(example, drawings):
    path = runner._drawings_file_path(example)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"drawings": drawings}), encoding="utf-8")
    return path


def _ref(feature, timber="posts/fl", csg_path=("cut",), kind="FACE"):
    """A feature reference as it travels on the wire."""
    return {"timber": timber, "csgPath": list(csg_path), "feature": feature, "type": kind}


def _feature_names(measures):
    """The pair each measurement is between, for readable assertions."""
    return [(m["a"]["feature"], m["b"]["feature"]) for m in measures]


def _path(feature, timber="posts/fl", csg_path=("cut",), kind="FACE"):
    """The kumiki form of the same thing."""
    from kumiki.timber import FeaturePath

    return FeaturePath(timber=timber, csg_path=csg_path, feature=feature, feature_type=kind)


def _sheet(drawing_id, name=None, viewports=None):
    """A drawing of the file's own: it lays itself out."""
    return {
        "id": drawing_id,
        "name": name or drawing_id,
        "page": {"width": 0.42, "height": 0.297},
        "viewports": viewports if viewports is not None else [],
    }


def _override(drawing_id, target, viewports=None):
    """A file drawing that says which python drawing it is overriding."""
    return {
        "id": drawing_id,
        runner.OVERRIDES_KEY: target,
        "viewports": viewports or [],
    }


@pytest.fixture
def example(tmp_path):
    return tmp_path / "shed.py"


class TestCollectDrawings:
    def test_a_frame_with_no_drawings_has_none(self, example):
        assert runner.collect_drawings(_frame(), example) == []

    def test_the_code_says_what_to_draw_and_the_runner_works_out_how(self, example):
        # A frame names a drawing and its timbers; the page, viewports and
        # cameras are none of its business.
        frame = _frame([Drawing(name="front left post", timber_paths=["posts/fl"])])

        drawing = runner.collect_drawings(frame, example)[0]

        assert drawing["origin"] == runner.ORIGIN_CODE
        assert drawing["name"] == "front left post"
        assert drawing["members"] == ["posts/fl#0"]
        assert drawing["page"]["width"] > 0
        assert len(drawing["viewports"]) > 0

    def test_the_file_overrides_a_drawing_the_code_asked_for(self, example):
        # By naming it, not by sharing its id.
        frame = _frame([Drawing(name="post", timber_paths=["posts/fl"])])
        _write_file(example, [_override("my post sheet", "post")])

        drawings = runner.collect_drawings(frame, example)

        assert len(drawings) == 1, "the override is not a second drawing"
        assert drawings[0]["origin"] == runner.ORIGIN_OVERRIDDEN
        # The layout is still the code's; an override contributes measurements.
        assert len(drawings[0]["viewports"]) > 1

    def test_an_override_naming_nothing_the_code_declares_is_dangling(self, example):
        # The point of naming the target: deleting a python drawing leaves an
        # entry that is plainly a dangling override, not one that has quietly
        # become a drawing of its own.
        _write_file(example, [_override("my post sheet", "a drawing that went away")])

        drawing = runner.collect_drawings(_frame(), example)[0]

        assert drawing["dangling"] is True
        assert drawing["origin"] == runner.ORIGIN_FILE

    def test_the_file_may_introduce_drawings_of_its_own(self, example):
        _write_file(example, [_sheet("test sheet")])

        drawings = runner.collect_drawings(_frame(), example)

        assert [d["origin"] for d in drawings] == [runner.ORIGIN_FILE]

    def test_code_drawings_come_first_and_keep_their_order(self, example):
        frame = _frame([
            Drawing(name="a", timber_paths=["posts/fl"]),
            Drawing(name="b", timber_paths=["posts/fr"]),
        ])
        _write_file(example, [_sheet("z")])

        assert [d["id"] for d in runner.collect_drawings(frame, example)] == ["a", "b", "z"]

    def test_a_file_drawing_that_overrides_nothing_is_its_own(self, example):
        _write_file(example, [_sheet("a sheet of my own")])

        drawings = runner.collect_drawings(_frame(), example)

        assert len(drawings) == 1
        assert drawings[0]["origin"] == runner.ORIGIN_FILE
        assert "dangling" not in drawings[0]

    def test_a_drawing_of_a_timber_that_is_gone_is_still_a_drawing(self, example):
        # Raising the frame must not fail because a path stopped matching.
        frame = _frame([Drawing(name="ghost", timber_paths=["posts/never"])])

        drawing = runner.collect_drawings(frame, example)[0]

        assert drawing["members"] == []

    def test_an_id_keeps_an_override_attached_across_a_rename(self, example):
        # drawing_id is what the override names, so the name can change.
        frame = _frame([Drawing(name="new name", drawing_id="stable", timber_paths=["posts/fl"])])
        _write_file(example, [_override("sheet", "stable")])

        drawing = runner.collect_drawings(frame, example)[0]

        assert drawing["origin"] == runner.ORIGIN_OVERRIDDEN

    def test_a_broken_file_is_reported_rather_than_fatal(self, example):
        # It is meant to be hand-edited, so a stray comma should not cost you
        # the viewer.
        path = runner._drawings_file_path(example)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        frame = _frame([Drawing(name="post", timber_paths=["posts/fl"])])

        drawings = runner.collect_drawings(frame, example)

        assert [d["origin"] for d in drawings] == [runner.ORIGIN_CODE]

    def test_entries_without_an_id_are_skipped(self, example):
        _write_file(example, [{"name": "nameless"}, _sheet("fine")])

        assert [d["id"] for d in runner.collect_drawings(_frame(), example)] == ["fine"]


class TestSaveDrawings:
    def test_it_writes_what_the_file_is_responsible_for(self, example):
        written = runner.write_drawings_file(example, [
            dict(_sheet("from code"), origin=runner.ORIGIN_CODE),
            dict(_sheet("overridden"), origin=runner.ORIGIN_OVERRIDDEN),
            dict(_sheet("from file"), origin=runner.ORIGIN_FILE),
        ])

        saved = json.loads(Path(written).read_text())
        assert [d["id"] for d in saved["drawings"]] == ["overridden", "from file"]

    def test_an_untouched_code_drawing_is_not_frozen_into_the_file(self, example):
        # Writing it out would stop it following the code that asked for it.
        runner.write_drawings_file(example, [dict(_sheet("a"), origin=runner.ORIGIN_CODE)])

        saved = json.loads(runner._drawings_file_path(example).read_text())
        assert saved["drawings"] == []

    def test_origin_is_not_written_out(self, example):
        # It is worked out on the way in; storing it would let it go stale.
        runner.write_drawings_file(example, [dict(_sheet("a"), origin=runner.ORIGIN_FILE)])

        saved = json.loads(runner._drawings_file_path(example).read_text())
        assert "origin" not in saved["drawings"][0]

    def test_what_is_saved_comes_back_the_same_way(self, example):
        runner.write_drawings_file(example, [dict(_sheet("kept"), origin=runner.ORIGIN_FILE)])

        drawings = runner.collect_drawings(_frame(), example)

        assert [d["id"] for d in drawings] == ["kept"]
        assert drawings[0]["origin"] == runner.ORIGIN_FILE

    def test_it_makes_the_directory_it_needs(self, example):
        runner.write_drawings_file(example, [dict(_sheet("a"), origin=runner.ORIGIN_FILE)])

        assert runner._drawings_file_path(example).exists()

    def test_it_lives_under_kigumi_where_writes_do_not_wake_the_watcher(self, example):
        assert ".kigumi" in runner._drawings_file_path(example).parts


class TestMergeMeasurements:
    """Two tiers: from the file, and not, with the file overriding."""

    def _code(self, a, b, **rest):
        return {"a": _ref(a), "b": _ref(b),
                "measureId": rest.get("measureId"), "origin": runner.ORIGIN_CODE}

    def test_code_measurements_come_through_untouched(self):
        merged = runner.merge_measurements([self._code("x", "y")], [])

        assert [m["origin"] for m in merged] == [runner.ORIGIN_CODE]

    def test_the_file_overrides_the_one_beneath_it(self):
        merged = runner.merge_measurements(
            [self._code("x", "y")], [{"a": _ref("x"), "b": _ref("y"), "placement": 12}],
        )

        assert len(merged) == 1
        assert merged[0]["origin"] == runner.ORIGIN_OVERRIDDEN
        # What the file says wins over what the code said.
        assert merged[0]["placement"] == 12

    def test_measuring_a_to_b_is_measuring_b_to_a(self):
        merged = runner.merge_measurements(
            [self._code("x", "y")], [{"a": _ref("y"), "b": _ref("x"), "placement": 3}],
        )

        assert len(merged) == 1
        assert merged[0]["origin"] == runner.ORIGIN_OVERRIDDEN

    def test_an_override_stays_attached_when_it_is_read_back(self):
        # What the identity rule is for: the file's entry finds the same code
        # measurement again, however many the algorithm emitted around it.
        code = [self._code("x", "y")]
        once = runner.merge_measurements(code, [{"a": _ref("x"), "b": _ref("y"), "placement": 7}])
        twice = runner.merge_measurements(code, once)

        assert len(twice) == 1
        assert twice[0]["placement"] == 7

    def test_an_id_tells_two_of_the_same_pair_apart(self):
        merged = runner.merge_measurements(
            [self._code("x", "y"), self._code("x", "y", measureId="second")],
            [{"a": _ref("x"), "b": _ref("y"), "measureId": "second", "placement": 1}],
        )

        origins = [m["origin"] for m in merged]
        assert origins == [runner.ORIGIN_CODE, runner.ORIGIN_OVERRIDDEN]

    def test_the_file_may_add_measurements_of_its_own(self):
        merged = runner.merge_measurements([], [{"a": _ref("p"), "b": _ref("q")}])

        assert [m["origin"] for m in merged] == [runner.ORIGIN_FILE]

    def test_the_file_may_suppress_one_the_algorithm_produced(self):
        # Without this, the only way to be rid of a generated measurement is to
        # change the algorithm.
        merged = runner.merge_measurements(
            [self._code("x", "y")], [{"a": _ref("x"), "b": _ref("y"), "suppressed": True}],
        )

        assert merged == []

    def test_suppressing_something_that_is_not_there_adds_nothing(self):
        merged = runner.merge_measurements([], [{"a": _ref("x"), "b": _ref("y"), "suppressed": True}])

        assert merged == []

    def test_a_repeated_identity_lets_the_later_one_win(self):
        # A mistake rather than a case to resolve, and not worth refusing the
        # whole file over.
        merged = runner.merge_measurements([], [
            {"a": _ref("x"), "b": _ref("y"), "placement": 1},
            {"a": _ref("x"), "b": _ref("y"), "placement": 2},
        ])

        assert len(merged) == 1
        assert merged[0]["placement"] == 2

    def test_code_order_is_kept_and_the_file_follows(self):
        merged = runner.merge_measurements(
            [self._code("a", "b"), self._code("c", "d")], [{"a": _ref("e"), "b": _ref("f")}],
        )

        assert _feature_names(merged) == [("a", "b"), ("c", "d"), ("e", "f")]


class TestMeasurementsThroughADrawing:
    def _front(self, drawing):
        return next(v for v in drawing["viewports"] if v["id"] == "front")["measurements"]

    def test_a_measurement_rides_on_the_viewport_it_is_drawn_in(self, example):
        from kumiki.timber import Measure

        frame = _frame([Drawing(
            name="post", timber_paths=["posts/fl"],
            measurements={"front": [Measure(anchor_a=_path("x"), anchor_b=_path("y"))]},
        )])

        drawing = runner.collect_drawings(frame, example)[0]

        assert [m["origin"] for m in self._front(drawing)] == [runner.ORIGIN_CODE]
        # And nowhere else: the same anchors elsewhere would be another dimension.
        for viewport in drawing["viewports"]:
            if viewport["id"] != "front":
                assert viewport["measurements"] == []

    def test_the_same_pair_in_two_viewports_are_two_measurements(self, example):
        # Neither overrides the other; they have different numbers.
        from kumiki.timber import Measure

        frame = _frame([Drawing(
            name="post", timber_paths=["posts/fl"],
            measurements={
                "front": [Measure(anchor_a=_path("x"), anchor_b=_path("y"))],
                "right": [Measure(anchor_a=_path("x"), anchor_b=_path("y"))],
            },
        )])

        drawing = runner.collect_drawings(frame, example)[0]
        by_id = {v["id"]: v["measurements"] for v in drawing["viewports"]}

        assert len(by_id["front"]) == 1
        assert len(by_id["right"]) == 1

    def test_an_override_only_reaches_its_own_viewport(self, example):
        from kumiki.timber import Measure

        frame = _frame([Drawing(
            name="post", timber_paths=["posts/fl"],
            measurements={
                "front": [Measure(anchor_a=_path("x"), anchor_b=_path("y"))],
                "right": [Measure(anchor_a=_path("x"), anchor_b=_path("y"))],
            },
        )])
        _write_file(example, [_override("sheet", "post", [
            {"id": "front", "measurements": [{"a": _ref("x"), "b": _ref("y")}]},
        ])])

        drawing = runner.collect_drawings(frame, example)[0]
        by_id = {v["id"]: v["measurements"] for v in drawing["viewports"]}

        assert by_id["front"][0]["origin"] == runner.ORIGIN_OVERRIDDEN
        assert by_id["right"][0]["origin"] == runner.ORIGIN_CODE

    def test_adding_a_measurement_does_not_freeze_the_drawing(self, example):
        # The reason measurements merge where everything else replaces: an
        # override of the whole drawing would take its layout with it.
        from kumiki.timber import Measure

        frame = _frame([Drawing(
            name="post", timber_paths=["posts/fl"],
            measurements={"front": [Measure(anchor_a=_path("x"), anchor_b=_path("y"))]},
        )])
        _write_file(example, [_override("sheet", "post", [
            {"id": "front", "measurements": [{"a": _ref("p"), "b": _ref("q")}]},
        ])])

        drawing = runner.collect_drawings(frame, example)[0]

        assert [m["origin"] for m in self._front(drawing)] == [
            runner.ORIGIN_CODE, runner.ORIGIN_FILE,
        ]
        assert len(drawing["viewports"]) > 1, "the code's layout survived"

    def test_a_measurement_for_a_viewport_that_is_gone_is_not_shown(self, example):
        # An override naming a viewport the code's layout does not produce.
        frame = _frame([Drawing(name="post", timber_paths=["posts/fl"])])
        _write_file(example, [_override("sheet", "post", [
            {"id": "nowhere", "measurements": [{"a": _ref("x"), "b": _ref("y")}]},
        ])])

        drawing = runner.collect_drawings(frame, example)[0]

        assert all(v["measurements"] == [] for v in drawing["viewports"])
        assert "nowhere" in drawing["unplaceableMeasurements"]

    def test_a_measurement_that_cannot_be_placed_is_not_lost(self, example):
        # The viewport may come back when the code changes, and a save that
        # dropped it would have deleted it from the file for good.
        written = runner.write_drawings_file(example, [{
            "id": "sheet", runner.OVERRIDES_KEY: "post", "origin": runner.ORIGIN_OVERRIDDEN,
            "viewports": [],
            "unplaceableMeasurements": {
                "nowhere": [{"a": _ref("x"), "b": _ref("y"), "origin": runner.ORIGIN_FILE}],
            },
        }])

        saved = json.loads(Path(written).read_text())["drawings"][0]
        assert saved["viewports"][0]["id"] == "nowhere"
        assert _feature_names(saved["viewports"][0]["measurements"]) == [("x", "y")]

    def test_saving_leaves_the_algorithms_measurements_out(self, example):
        # They would stop following the algorithm the moment the frame changed.
        runner.write_drawings_file(example, [{
            "id": "sheet", runner.OVERRIDES_KEY: "post", "origin": runner.ORIGIN_OVERRIDDEN,
            "viewports": [{"id": "front", "measurements": [
                {"a": _ref("x"), "b": _ref("y"), "origin": runner.ORIGIN_CODE},
                {"a": _ref("p"), "b": _ref("q"), "origin": runner.ORIGIN_FILE},
            ]}],
        }])

        saved = json.loads(runner._drawings_file_path(example).read_text())["drawings"][0]
        kept = saved["viewports"][0]["measurements"]
        assert _feature_names(kept) == [("p", "q")]

    def test_an_override_saves_viewport_ids_and_nothing_else(self, example):
        # The layout is the code's; writing it out would freeze it.
        runner.write_drawings_file(example, [{
            "id": "sheet", runner.OVERRIDES_KEY: "post", "origin": runner.ORIGIN_OVERRIDDEN,
            "viewports": [{
                "id": "front", "rect": [0, 0, 1, 1], "camera": {"extent": 2},
                "measurements": [{"a": _ref("p"), "b": _ref("q"), "origin": runner.ORIGIN_FILE}],
            }],
        }])

        saved = json.loads(runner._drawings_file_path(example).read_text())["drawings"][0]
        assert sorted(saved["viewports"][0]) == ["id", "measurements"]

    def test_a_drawing_of_its_own_saves_its_whole_layout(self, example):
        runner.write_drawings_file(example, [{
            "id": "sheet", "origin": runner.ORIGIN_FILE,
            "page": {"width": 0.42, "height": 0.297},
            "viewports": [
                {"id": "front", "rect": [0, 0, 1, 1],
                 "measurements": [{"a": _ref("x"), "b": _ref("y"), "origin": runner.ORIGIN_FILE}]},
                {"id": "right", "rect": [0, 0, 1, 1],
                 "measurements": [{"a": _ref("p"), "b": _ref("q"), "origin": runner.ORIGIN_FILE}]},
            ],
        }])

        saved = json.loads(runner._drawings_file_path(example).read_text())["drawings"][0]

        assert [v["id"] for v in saved["viewports"]] == ["front", "right"]
        assert saved["viewports"][0]["rect"] == [0, 0, 1, 1]
        assert "origin" not in saved["viewports"][0]["measurements"][0]

    def test_what_is_saved_comes_back_where_it_was(self, example):
        runner.write_drawings_file(example, [{
            "id": "sheet", "name": "sheet", "origin": runner.ORIGIN_FILE,
            "page": {"width": 0.42, "height": 0.297},
            "viewports": [{"id": "front", "rect": [0, 0, 1, 1],
                           "measurements": [{"a": _ref("x"), "b": _ref("y"), "origin": runner.ORIGIN_FILE}]}],
        }])

        drawing = runner.collect_drawings(_frame(), example)[0]
        front = next(v for v in drawing["viewports"] if v["id"] == "front")

        assert _feature_names(front["measurements"]) == [("x", "y")]

    def test_a_drawing_of_its_own_lays_itself_out(self, example):
        # How a drawing is set up to test with: it is not an override at all.
        _write_file(example, [_sheet("test sheet", viewports=[{"id": "only", "rect": [0, 0, 1, 1]}])])

        drawing = runner.collect_drawings(_frame(), example)[0]

        assert [v["id"] for v in drawing["viewports"]] == ["only"]
        assert drawing["origin"] == runner.ORIGIN_FILE


class TestFeaturePath:
    """A reference to a feature: instructions for finding it again."""

    def test_it_addresses_by_name_and_never_by_position(self):
        # The property the whole thing rests on. A position stops meaning what
        # it meant the moment a joint is added above it.
        from kumiki.timber import FeaturePath

        reference = FeaturePath(
            timber="posts/fl", csg_path=["tenon_cut"], feature="tenon_front", feature_type="FACE",
        )

        assert reference.identity() == ("posts/fl", ("tenon_cut",), "tenon_front", "FACE")

    def test_a_list_of_steps_becomes_a_tuple(self):
        from kumiki.timber import FeaturePath

        assert isinstance(FeaturePath("t", ["a", "b"]).csg_path, tuple)

    def test_the_same_label_on_a_face_and_an_edge_are_different_features(self):
        # One label can name both, and measuring to the wrong one does not look
        # wrong on screen.
        assert _path("x", kind="FACE").identity() != _path("x", kind="EDGE").identity()

    def test_two_timbers_of_one_ticket_path_are_told_apart(self):
        assert _path("x", timber="posts/fl#0").identity() != _path("x", timber="posts/fl#1").identity()

    def test_a_separator_in_a_ticket_path_cannot_collapse_two_references(self):
        # Why identity is a tuple and not a joined string: ticket paths contain
        # slashes themselves.
        from kumiki.timber import FeaturePath

        one = FeaturePath(timber="posts/fl", csg_path=["cut"])
        other = FeaturePath(timber="posts", csg_path=["fl", "cut"])

        assert one.identity() != other.identity()

    def test_it_describes_itself_as_a_trail(self):
        assert _path("tenon_front", csg_path=("tenon_cut",)).describe() == (
            "posts/fl > tenon_cut > tenon_front"
        )

    def test_a_reference_to_a_whole_node_needs_no_feature(self):
        from kumiki.timber import FeaturePath

        assert FeaturePath(timber="posts/fl", csg_path=["tenon_cut"]).describe() == (
            "posts/fl > tenon_cut"
        )

    def test_the_wire_form_round_trips_into_the_same_identity(self):
        from kumiki.timber import FeaturePath

        reference = FeaturePath("posts/fl", ("cut",), "x", "FACE")
        on_the_wire = runner.serialize_feature_path(reference)

        assert runner._feature_path_identity(on_the_wire) == reference.identity()

    def test_a_measurement_is_the_same_measured_either_way_round(self):
        from kumiki.timber import Measure

        there = Measure(anchor_a=_path("x"), anchor_b=_path("y"))
        back = Measure(anchor_a=_path("y"), anchor_b=_path("x"))

        assert there.identity() == back.identity()

    def test_an_id_still_separates_two_of_the_same_pair(self):
        from kumiki.timber import Measure

        assert (Measure(anchor_a=_path("x"), anchor_b=_path("y")).identity()
                != Measure(anchor_a=_path("x"), anchor_b=_path("y"), measure_id="2").identity())
