"""A file with several @frame functions and @tool functions, as the kigumi runner loads it."""

import json

import pytest

from tests.test_kigumi_kiwari_protocol import _put_kumiki_back, runner, workspace  # noqa: F401 (fixtures)

SOURCE = '''
from kumiki import *

params = kiwari(posts=kiwari.count(2, minimum=1, maximum=8))


def _posts(k, x0, prefix):
    return [
        CutTimber(create_timber(
            bottom_position=create_v3(x0 + i, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
            length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket=f"{prefix} {i}"),
            cuts=[])
        for i in range(k.count("posts"))
    ]


@frame
def west(k: Kiwari) -> Frame:
    return Frame(cut_timbers=_posts(k, 0, "west"), name="west")


@frame
def east(k: Kiwari) -> Frame:
    return Frame(cut_timbers=_posts(k, 10, "east"), name="east")


@tool
def count_posts(frame: Frame, k: Kiwari) -> str:
    return f"{len(frame.cut_timbers)} posts, {k.count('posts')} per side"


@tool
def mistyped(frame: Frame) -> str:
    return "never admitted"


@tool
def not_text(frame: Frame, k: Kiwari) -> str:
    return 42
'''


@pytest.fixture
def frames_file(workspace):  # noqa: F811
    path = workspace / "two_frames.py"
    path.write_text(SOURCE)
    return path


def test_every_frame_is_shown_together(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    assert sorted(cut.timber.ticket.path for cut in slot.frame.cut_timbers) == ["east 0", "east 1", "west 0", "west 1"]
    assert slot.frame.name == "west + east"


def test_the_shared_parameters_build_every_frame(frames_file):
    first = runner.load_slot_state(str(frames_file))
    again = runner.load_slot_state(str(frames_file), kiwari_values={"posts": 3}, previous_kiwari=first.kiwari)

    assert len(again.frame.cut_timbers) == 6
    payload = runner._serialize_kiwari_for_slot(again)
    assert [entry["key"] for entry in payload["schema"]] == ["posts"]
    assert payload["changed"] == ["posts"]


def test_tools_and_rejections_reach_the_viewer(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    listed = runner._serialize_tools(slot)

    assert [tool["name"] for tool in listed["tools"]] == ["count_posts", "not_text"]
    (rejected,) = listed["rejectedEntries"]
    assert rejected["name"] == "mistyped" and rejected["kind"] == "tool" and "2 parameter" in rejected["reason"]
    json.dumps(listed)


def test_a_tool_runs_on_the_shown_frame_with_the_bound_parameters(frames_file):
    first = runner.load_slot_state(str(frames_file))
    slot = runner.load_slot_state(str(frames_file), kiwari_values={"posts": 3}, previous_kiwari=first.kiwari)

    assert runner.run_tool(slot, "count_posts") == {"name": "count_posts", "output": "6 posts, 3 per side"}


def test_a_tool_must_return_text(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    with pytest.raises(TypeError, match="expected str"):
        runner.run_tool(slot, "not_text")


def test_an_unknown_tool_says_what_there_is(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    with pytest.raises(ValueError, match="count_posts"):
        runner.run_tool(slot, "nope")


@pytest.mark.parametrize("name", ["build_frame", "example"])
def test_a_frame_found_by_name_still_loads_but_warns(workspace, capsys, name):  # noqa: F811
    path = workspace / "old.py"
    path.write_text(f"from kumiki import *\n\ndef {name}():\n    return Frame(cut_timbers=[], name='old')\n")

    slot = runner.load_slot_state(str(path))

    assert slot.frame.name == "old"
    warning = capsys.readouterr().err
    assert f"'{name}' is deprecated" in warning and "@frame" in warning


def test_a_decorated_file_does_not_warn(frames_file, capsys):
    runner.load_slot_state(str(frames_file))

    assert "deprecated" not in capsys.readouterr().err


def test_a_file_without_parameters_shows_none(workspace):  # noqa: F811
    path = workspace / "plain_frames.py"
    path.write_text("from kumiki import *\n\n@frame\ndef empty(k: Kiwari) -> Frame:\n"
                    "    return Frame(cut_timbers=[], name='empty')\n")

    slot = runner.load_slot_state(str(path))

    assert slot.frame.name == "empty" and slot.kiwari is None
    assert runner._serialize_kiwari_for_slot(slot) is None


def test_a_kumiki_without_frame_decorators_still_loads_legacy_files(workspace, monkeypatch):  # noqa: F811
    # kigumi 0.8.x also runs against kumiki 0.8.0, which has no kumiki.frame_decorators.
    monkeypatch.setattr(runner, "_frame_decorators", lambda: None)
    path = workspace / "old.py"
    path.write_text("from kumiki import *\n\ndef build_frame():\n    return Frame(cut_timbers=[], name='old')\n")

    slot = runner.load_slot_state(str(path))

    assert slot.frame.name == "old"
    assert runner._serialize_tools(slot) == {"tools": [], "rejectedEntries": []}
