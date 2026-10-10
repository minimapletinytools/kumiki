"""A file with several @frame functions and @tool functions, as the kigumi runner loads it."""

import json

import pytest

from tests.test_kigumi_kiwari_protocol import _put_kumiki_back, runner, workspace  # noqa: F401 (fixtures)

SOURCE = '''
from kumiki import *

SIDES = kiwari(posts=kiwari.count(2, minimum=1, maximum=8))
NORTH = kiwari(posts=kiwari.count(1, minimum=1, maximum=8))


def _posts(k, x0, prefix):
    return [
        CutTimber(create_timber(
            bottom_position=create_v3(x0 + i, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
            length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket=f"{prefix} {i}"),
            cuts=[])
        for i in range(k.count("posts"))
    ]


@frame
def west(k: Optional[Kiwari] = None) -> Frame:
    k = SIDES.resolve(k)
    return Frame(cut_timbers=_posts(k, 0, "west"), name="west", kiwari=k)


@frame
def north(k: Optional[Kiwari] = None) -> Frame:
    k = NORTH.resolve(k)
    return Frame(cut_timbers=_posts(k, 5, "north"), name="north", kiwari=k)


@frame
def east(k: Optional[Kiwari] = None) -> Frame:
    k = SIDES.resolve(k)
    return Frame(cut_timbers=_posts(k, 10, "east"), name="east", kiwari=k)


@tool
def count_posts(frame: Frame) -> str:
    return f"{len(frame.cut_timbers)} posts"


@tool
def mistyped(frame: Frame, k: Kiwari) -> str:
    return "never admitted"


@tool
def not_text(frame: Frame) -> str:
    return 42
'''


@pytest.fixture
def frames_file(workspace):  # noqa: F811
    path = workspace / "two_frames.py"
    path.write_text(SOURCE)
    return path


def _posts_of(slot, prefix):
    return sum(1 for cut in slot.frame.cut_timbers if cut.timber.ticket.path.startswith(prefix))


def test_every_frame_is_shown_together(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    assert sorted(cut.timber.ticket.path for cut in slot.frame.cut_timbers) == [
        "east 0", "east 1", "north 0", "west 0", "west 1"]
    assert slot.frame.name == "west + north + east"


def test_frames_from_one_kiwari_share_it_and_the_rest_have_their_own(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    assert [group.frames for group in slot.kiwari_groups] == [("west", "east"), ("north",)]
    sections = runner._serialize_kiwari_for_slot(slot)
    assert [(section["id"], section["frames"]) for section in sections] == [
        ("west,east", ["west", "east"]), ("north", ["north"])]
    json.dumps(sections)


def test_values_for_a_shared_kiwari_build_every_frame_from_it(frames_file):
    first = runner.load_slot_state(str(frames_file))
    again = runner.load_slot_state(str(frames_file), kiwari_values={"west,east": {"posts": 3}},
                                   previous_groups=first.kiwari_groups)

    assert (_posts_of(again, "west"), _posts_of(again, "east"), _posts_of(again, "north")) == (3, 3, 1)
    shared, own = runner._serialize_kiwari_for_slot(again)
    assert shared["changed"] == ["posts"] and own["changed"] == []


def test_values_for_one_kiwari_leave_the_others_alone(frames_file):
    first = runner.load_slot_state(str(frames_file))
    again = runner.load_slot_state(str(frames_file), kiwari_values={"north": {"posts": 4}},
                                   previous_groups=first.kiwari_groups)

    assert (_posts_of(again, "west"), _posts_of(again, "east"), _posts_of(again, "north")) == (2, 2, 4)


def test_tools_and_rejections_reach_the_viewer(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    listed = runner._serialize_tools(slot)

    assert [tool["name"] for tool in listed["tools"]] == ["count_posts", "not_text"]
    (rejected,) = listed["rejectedEntries"]
    assert rejected["name"] == "mistyped" and rejected["kind"] == "tool" and "1 parameter" in rejected["reason"]
    json.dumps(listed)


def test_a_tool_runs_on_the_shown_frame(frames_file):
    first = runner.load_slot_state(str(frames_file))
    slot = runner.load_slot_state(str(frames_file), kiwari_values={"west,east": {"posts": 3}},
                                  previous_groups=first.kiwari_groups)

    assert runner.run_tool(slot, "count_posts") == {"name": "count_posts", "output": "7 posts"}


def test_a_tool_must_return_text(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    with pytest.raises(TypeError, match="expected str"):
        runner.run_tool(slot, "not_text")


def test_an_unknown_tool_says_what_there_is(frames_file):
    slot = runner.load_slot_state(str(frames_file))

    with pytest.raises(ValueError, match="count_posts"):
        runner.run_tool(slot, "nope")


def test_saved_values_go_back_to_the_frames_they_were_saved_for(frames_file):
    first = runner.load_slot_state(str(frames_file))
    runner._write_parameters_file(runner.load_slot_state(
        str(frames_file), kiwari_values={"north": {"posts": 4}}, previous_groups=first.kiwari_groups))

    saved = json.loads((frames_file.parent / "two_frames.parameters.json").read_text())
    assert saved["groups"] == [{"frames": ["north"], "values": {"posts": {"value": 4}}}]
    reloaded = runner.load_slot_state(str(frames_file))
    assert (_posts_of(reloaded, "west"), _posts_of(reloaded, "north")) == (2, 4)


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

    assert slot.frame.name == "empty" and slot.kiwari_groups == ()
    assert runner._serialize_kiwari_for_slot(slot) is None


def test_a_kumiki_without_frame_decorators_still_loads_legacy_files(workspace, monkeypatch):  # noqa: F811
    # kigumi 0.8.x also runs against kumiki 0.8.0, which has no kumiki.frame_decorators.
    monkeypatch.setattr(runner, "_frame_decorators", lambda: None)
    path = workspace / "old.py"
    path.write_text("from kumiki import *\n\ndef build_frame():\n    return Frame(cut_timbers=[], name='old')\n")

    slot = runner.load_slot_state(str(path))

    assert slot.frame.name == "old"
    assert runner._serialize_tools(slot) == {"tools": [], "rejectedEntries": []}


def test_a_pattern_book_ignores_its_frames(workspace, capsys):  # noqa: F811
    path = workspace / "book.py"
    path.write_text("from kumiki import *\n\n"
                    "@pattern('g/a', tags=['main'])\ndef a() -> Frame:\n    return Frame(cut_timbers=[], name='a')\n\n"
                    "@frame\ndef f(k: Kiwari) -> Frame:\n    return Frame(cut_timbers=[], name='f')\n")

    slot = runner.load_slot_state(str(path))

    assert slot.frame.name == "a"
    assert "@frame functions are not shown: f" in capsys.readouterr().err


def test_a_patterns_list_is_no_longer_read(workspace):  # noqa: F811
    path = workspace / "old_book.py"
    path.write_text("from kumiki import *\nfrom kumiki.patternbook import Pattern, make_pattern_from_frame\n\n"
                    "def a():\n    return Frame(cut_timbers=[])\n\n"
                    "patterns = [Pattern(path='g/a', lambda_=make_pattern_from_frame(a))]\n")

    with pytest.raises(AttributeError, match="@pattern or @frame"):
        runner.load_slot_state(str(path))


def test_the_layers_say_which_timbers_are_each_frame_s(frames_file):
    slot = runner.load_slot_state(str(frames_file))
    layers = runner.serialize_layers(slot.frame, slot.frame_parts)

    names = {timber["kumikiEphemeralId"]: timber["name"] for timber in layers["timbers"]}
    assert [(part["name"], sorted(names[i] for i in part["timberKumikiEphemeralIds"])) for part in layers["frames"]] == [
        ("west", ["west 0", "west 1"]), ("north", ["north 0"]), ("east", ["east 0", "east 1"])]
    json.dumps(layers)


def test_one_frame_has_no_frames_in_its_layers(workspace):  # noqa: F811
    path = workspace / "one.py"
    path.write_text("from kumiki import *\n\n@frame\ndef only(k: Kiwari) -> Frame:\n"
                    "    return Frame(cut_timbers=[], name='only')\n")
    slot = runner.load_slot_state(str(path))

    assert slot.frame_parts == () and runner.serialize_layers(slot.frame, slot.frame_parts)["frames"] is None
