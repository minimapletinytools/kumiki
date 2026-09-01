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
