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


def test_a_file_with_only_build_frame_is_told_what_to_do(workspace):  # noqa: F811
    path = workspace / "old.py"
    path.write_text("from kumiki import *\n\ndef build_frame():\n    return Frame(cut_timbers=[])\n")

    with pytest.raises(AttributeError, match="example = build_frame"):
        runner.load_slot_state(str(path))


def test_a_file_without_parameters_shows_none(workspace):  # noqa: F811
    path = workspace / "plain_frames.py"
    path.write_text("from kumiki import *\n\n@frame\ndef empty(k: Kiwari) -> Frame:\n"
                    "    return Frame(cut_timbers=[], name='empty')\n")

    slot = runner.load_slot_state(str(path))

    assert slot.frame.name == "empty" and slot.kiwari is None
    assert runner._serialize_kiwari_for_slot(slot) is None
