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


def _sheet(drawing_id, name=None):
    return {
        "id": drawing_id,
        "name": name or drawing_id,
        "page": {"width": 0.42, "height": 0.297},
        "viewports": [],
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
        frame = _frame([Drawing(name="post", timber_paths=["posts/fl"])])
        _write_file(example, [_sheet("post")])

        drawing = runner.collect_drawings(frame, example)[0]

        assert drawing["origin"] == runner.ORIGIN_OVERRIDDEN
        # Replaced outright, not patched: the file's viewports are what is used.
        assert drawing["viewports"] == []

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

    def test_an_override_outlives_the_drawing_it_overrode(self, example):
        # The code used to declare this and no longer does. Dropping it would
        # throw away whatever was set up in the file without saying so.
        _write_file(example, [_sheet("a drawing the code forgot")])

        drawings = runner.collect_drawings(_frame(), example)

        assert len(drawings) == 1
        assert drawings[0]["origin"] == runner.ORIGIN_FILE

    def test_a_drawing_of_a_timber_that_is_gone_is_still_a_drawing(self, example):
        # Raising the frame must not fail because a path stopped matching.
        frame = _frame([Drawing(name="ghost", timber_paths=["posts/never"])])

        drawing = runner.collect_drawings(frame, example)[0]

        assert drawing["members"] == []

    def test_an_id_keeps_an_override_attached_across_a_rename(self, example):
        # drawing_id is what the override keys on, so the name can change.
        frame = _frame([Drawing(name="new name", drawing_id="stable", timber_paths=["posts/fl"])])
        _write_file(example, [_sheet("stable", name="old name")])

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
        return {"a": a, "b": b, "measureId": rest.get("measureId"),
                "origin": runner.ORIGIN_CODE}

    def test_code_measurements_come_through_untouched(self):
        merged = runner.merge_measurements([self._code("x", "y")], [])

        assert [m["origin"] for m in merged] == [runner.ORIGIN_CODE]

    def test_the_file_overrides_the_one_beneath_it(self):
        merged = runner.merge_measurements(
            [self._code("x", "y")], [{"a": "x", "b": "y", "placement": 12}],
        )

        assert len(merged) == 1
        assert merged[0]["origin"] == runner.ORIGIN_OVERRIDDEN
        # What the file says wins over what the code said.
        assert merged[0]["placement"] == 12

    def test_measuring_a_to_b_is_measuring_b_to_a(self):
        merged = runner.merge_measurements(
            [self._code("x", "y")], [{"a": "y", "b": "x", "placement": 3}],
        )

        assert len(merged) == 1
        assert merged[0]["origin"] == runner.ORIGIN_OVERRIDDEN

    def test_an_override_stays_attached_when_it_is_read_back(self):
        # What the identity rule is for: the file's entry finds the same code
        # measurement again, however many the algorithm emitted around it.
        code = [self._code("x", "y")]
        once = runner.merge_measurements(code, [{"a": "x", "b": "y", "placement": 7}])
        twice = runner.merge_measurements(code, once)

        assert len(twice) == 1
        assert twice[0]["placement"] == 7

    def test_an_id_tells_two_of_the_same_pair_apart(self):
        merged = runner.merge_measurements(
            [self._code("x", "y"), self._code("x", "y", measureId="second")],
            [{"a": "x", "b": "y", "measureId": "second", "placement": 1}],
        )

        origins = [m["origin"] for m in merged]
        assert origins == [runner.ORIGIN_CODE, runner.ORIGIN_OVERRIDDEN]

    def test_the_file_may_add_measurements_of_its_own(self):
        merged = runner.merge_measurements([], [{"a": "p", "b": "q"}])

        assert [m["origin"] for m in merged] == [runner.ORIGIN_FILE]

    def test_the_file_may_suppress_one_the_algorithm_produced(self):
        # Without this, the only way to be rid of a generated measurement is to
        # change the algorithm.
        merged = runner.merge_measurements(
            [self._code("x", "y")], [{"a": "x", "b": "y", "suppressed": True}],
        )

        assert merged == []

    def test_suppressing_something_that_is_not_there_adds_nothing(self):
        merged = runner.merge_measurements([], [{"a": "x", "b": "y", "suppressed": True}])

        assert merged == []

    def test_a_repeated_identity_lets_the_later_one_win(self):
        # A mistake rather than a case to resolve, and not worth refusing the
        # whole file over.
        merged = runner.merge_measurements([], [
            {"a": "x", "b": "y", "placement": 1},
            {"a": "x", "b": "y", "placement": 2},
        ])

        assert len(merged) == 1
        assert merged[0]["placement"] == 2

    def test_code_order_is_kept_and_the_file_follows(self):
        merged = runner.merge_measurements(
            [self._code("a", "b"), self._code("c", "d")], [{"a": "e", "b": "f"}],
        )

        assert [(m["a"], m["b"]) for m in merged] == [("a", "b"), ("c", "d"), ("e", "f")]


class TestMeasurementsThroughADrawing:
    def _front(self, drawing):
        return next(v for v in drawing["viewports"] if v["id"] == "front")["measurements"]

    def test_a_measurement_rides_on_the_viewport_it_is_drawn_in(self, example):
        from kumiki.timber import Measure

        frame = _frame([Drawing(
            name="post", timber_paths=["posts/fl"],
            measurements={"front": [Measure(anchor_a="x", anchor_b="y")]},
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
                "front": [Measure(anchor_a="x", anchor_b="y")],
                "right": [Measure(anchor_a="x", anchor_b="y")],
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
                "front": [Measure(anchor_a="x", anchor_b="y")],
                "right": [Measure(anchor_a="x", anchor_b="y")],
            },
        )])
        _write_file(example, [{"id": "post", "measurements": {"front": [{"a": "x", "b": "y"}]}}])

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
            measurements={"front": [Measure(anchor_a="x", anchor_b="y")]},
        )])
        _write_file(example, [{"id": "post", "measurements": {"front": [{"a": "p", "b": "q"}]}}])

        drawing = runner.collect_drawings(frame, example)[0]

        assert [m["origin"] for m in self._front(drawing)] == [
            runner.ORIGIN_CODE, runner.ORIGIN_FILE,
        ]

    def test_a_measurement_for_a_viewport_that_is_gone_is_kept_as_broken(self, example):
        # Written against a viewport this layout does not produce. Dropping it
        # would lose the work without saying so.
        _write_file(example, [{
            "id": "post", "name": "post",
            "page": {"width": 0.42, "height": 0.297},
            "viewports": [{"id": "front", "rect": [0, 0, 1, 1]}],
            "measurements": {"nowhere": [{"a": "x", "b": "y"}]},
        }])

        drawing = runner.collect_drawings(_frame(), example)[0]

        assert "nowhere" in drawing["orphanedMeasurements"]

    def test_saving_leaves_the_algorithms_measurements_out(self, example):
        # They would stop following the algorithm the moment the frame changed.
        runner.write_drawings_file(example, [{
            "id": "post", "origin": runner.ORIGIN_OVERRIDDEN,
            "viewports": [{"id": "front", "measurements": [
                {"a": "x", "b": "y", "origin": runner.ORIGIN_CODE},
                {"a": "p", "b": "q", "origin": runner.ORIGIN_FILE},
            ]}],
        }])

        saved = json.loads(runner._drawings_file_path(example).read_text())
        kept = saved["drawings"][0]["measurements"]["front"]
        assert [(m["a"], m["b"]) for m in kept] == [("p", "q")]

    def test_saving_gathers_them_back_under_their_viewports(self, example):
        runner.write_drawings_file(example, [{
            "id": "post", "origin": runner.ORIGIN_FILE,
            "viewports": [
                {"id": "front", "measurements": [{"a": "x", "b": "y", "origin": runner.ORIGIN_FILE}]},
                {"id": "right", "measurements": [{"a": "p", "b": "q", "origin": runner.ORIGIN_FILE}]},
            ],
        }])

        saved = json.loads(runner._drawings_file_path(example).read_text())["drawings"][0]

        assert sorted(saved["measurements"]) == ["front", "right"]
        assert "origin" not in saved["measurements"]["front"][0]

    def test_what_is_saved_comes_back_where_it_was(self, example):
        runner.write_drawings_file(example, [{
            "id": "sheet", "name": "sheet", "origin": runner.ORIGIN_FILE,
            "page": {"width": 0.42, "height": 0.297},
            "viewports": [{"id": "front", "rect": [0, 0, 1, 1],
                           "measurements": [{"a": "x", "b": "y", "origin": runner.ORIGIN_FILE}]}],
        }])

        drawing = runner.collect_drawings(_frame(), example)[0]
        front = next(v for v in drawing["viewports"] if v["id"] == "front")

        assert [(m["a"], m["b"]) for m in front["measurements"]] == [("x", "y")]

    def test_a_file_entry_with_a_layout_stands_in_for_the_drawing(self, example):
        # How a drawing is set up to test with: the file's layout is the one used.
        frame = _frame([Drawing(name="post", timber_paths=["posts/fl"])])
        _write_file(example, [dict(_sheet("post"), viewports=[{"id": "only", "rect": [0, 0, 1, 1]}])])

        drawing = runner.collect_drawings(frame, example)[0]

        assert [v["id"] for v in drawing["viewports"]] == ["only"]
        assert drawing["origin"] == runner.ORIGIN_OVERRIDDEN

    def test_a_file_entry_with_only_measurements_keeps_the_code_layout(self, example):
        # Adding a dimension must not take the drawing's page and viewports with
        # it -- that is the whole reason measurements merge.
        frame = _frame([Drawing(name="post", timber_paths=["posts/fl"])])
        _write_file(example, [{"id": "post", "measurements": {"front": [{"a": "x", "b": "y"}]}}])

        drawing = runner.collect_drawings(frame, example)[0]

        assert len(drawing["viewports"]) > 1, "the code layout survived"
        assert drawing["page"]["width"] > 0
        # Still marked as touched by the file, so it can be reverted.
        assert drawing["origin"] == runner.ORIGIN_OVERRIDDEN
