"""How a kiwari reaches the viewer and comes back, including the saved file."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest



def _load_runner():
    """Import kigumi/runner.py by path -- kigumi is not an installed package."""
    runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
    spec = importlib.util.spec_from_file_location("kigumi_runner_kiwari", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_kiwari"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


FRAME_SOURCE = '''
from kumiki import *
from kumiki.ticket import TimberTicket


def build_frame(k=None):
    k = kiwari(
        posts=kiwari.count(2, minimum=1, maximum=8, about="How many posts"),
        post_height=kiwari.length(mm(2400)),
        capped=kiwari.flag(False),
        end=kiwari.choice(TimberEnd, TimberEnd.TOP),
    ).resolve(k)
    timbers = [
        create_timber(
            bottom_position=create_v3(inches(24) * scalar(i), scalar(0), scalar(0)),
            length=k.length("post_height"),
            size=create_v2(inches(6), inches(6)),
            length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            ticket=TimberTicket(path=f"Post {i + 1}"),
        )
        for i in range(k.count("posts"))
    ]
    return Frame(
        cut_timbers=[CutTimber(timber=t, cuts=[]) for t in timbers],
        name=f"{k.count('posts')} posts",
        kiwari=k,
    )
'''

PLAIN_SOURCE = '''
from kumiki import *


def build_frame():
    return Frame(cut_timbers=[], name="no parameters")
'''


@pytest.fixture(autouse=True)
def _put_kumiki_back():
    """Undo the runner's module purge once each test is done.

    load_slot_state purges kumiki out of sys.modules so that editing a source
    file actually takes effect. Left purged, every later test in this session
    would import fresh classes that the ones it captured at import time no
    longer match -- which shows up as unrelated failures a long way from here.
    """
    before = {name: module for name, module in sys.modules.items() if name.startswith("kumiki")}
    yield
    for name in [name for name in sys.modules if name.startswith("kumiki")]:
        del sys.modules[name]
    sys.modules.update(before)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("KIGUMI_WORKSPACE_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def frame_file(workspace):
    path = workspace / "myframe.py"
    path.write_text(FRAME_SOURCE)
    return path


def test_a_frame_that_takes_no_parameters_sends_no_kiwari(workspace):
    path = workspace / "plain.py"
    path.write_text(PLAIN_SOURCE)
    slot = runner.load_slot_state(str(path))
    assert slot.kiwari is None
    assert runner._serialize_kiwari_for_slot(slot) is None


def test_the_schema_reaches_the_viewer_off_the_frame_that_was_built(frame_file):
    payload = runner._serialize_kiwari_for_slot(runner.load_slot_state(str(frame_file)))
    kinds = {entry["key"]: entry["kind"] for entry in payload["schema"]}
    assert kinds == {"posts": "count", "post_height": "length", "capped": "flag", "end": "choice"}
    posts = next(e for e in payload["schema"] if e["key"] == "posts")
    assert posts["about"] == "How many posts" and posts["minimum"] == 1 and posts["maximum"] == 8
    assert payload["applied"]["post_height"] == {"value": 2.4, "text": "2400mm"}
    assert payload["changed"] == []
    json.dumps(payload)


def test_values_from_the_viewer_build_a_different_frame(frame_file):
    first = runner.load_slot_state(str(frame_file))
    again = runner.load_slot_state(
        str(frame_file),
        kiwari_values={"posts": 5, "post_height": "10ft"},
        previous_kiwari=first.kiwari,
    )
    assert again.frame.name == "5 posts"
    assert len(again.frame.cut_timbers) == 5
    assert again.kiwari.length("post_height") == pytest.approx(3.048)
    assert set(again.kiwari.changed_from_defaults()) == {"posts", "post_height"}


def test_a_value_the_frame_refuses_is_reported_not_swallowed(frame_file):
    first = runner.load_slot_state(str(frame_file))
    with pytest.raises(ValueError, match="at most 8"):
        runner.load_slot_state(str(frame_file), kiwari_values={"posts": 99},
                               previous_kiwari=first.kiwari)


def test_a_builder_that_takes_no_argument_is_told_what_to_add(workspace):
    path = workspace / "plain.py"
    path.write_text(PLAIN_SOURCE)
    from kumiki.kiwari import kiwari
    with pytest.raises(TypeError, match="takes no argument to receive them"):
        runner.load_slot_state(str(path), kiwari_values={"posts": 3},
                               previous_kiwari=kiwari(posts=kiwari.count(2)))


# --- the file beside the source ---------------------------------------------


def test_saving_writes_only_what_differs_from_the_code(frame_file):
    first = runner.load_slot_state(str(frame_file))
    changed = runner.load_slot_state(
        str(frame_file),
        kiwari_values={"posts": 5, "post_height": {"value": 3.048, "text": "10ft"}},
        previous_kiwari=first.kiwari,
    )
    written = Path(runner._write_parameters_file(changed))
    assert written.name == "myframe.parameters.json"
    saved = json.loads(written.read_text())
    assert saved["schema_version"] == 1
    # capped and end were never touched, so they are not in the file.
    assert set(saved["values"]) == {"posts", "post_height"}
    assert saved["values"]["post_height"]["text"] == "10ft"


def test_a_saved_file_is_loaded_without_the_viewer_asking(frame_file):
    first = runner.load_slot_state(str(frame_file))
    runner._write_parameters_file(runner.load_slot_state(
        str(frame_file), kiwari_values={"posts": 5}, previous_kiwari=first.kiwari))

    fresh = runner.load_slot_state(str(frame_file))
    assert fresh.frame.name == "5 posts"
    assert fresh.kiwari.changed_from_defaults() == ("posts",)


def test_what_the_viewer_says_beats_what_the_file_says(frame_file):
    first = runner.load_slot_state(str(frame_file))
    runner._write_parameters_file(runner.load_slot_state(
        str(frame_file), kiwari_values={"posts": 5}, previous_kiwari=first.kiwari))

    fresh = runner.load_slot_state(str(frame_file), kiwari_values={"posts": 3},
                                   previous_kiwari=first.kiwari)
    assert fresh.frame.name == "3 posts"


def test_putting_everything_back_to_default_removes_the_file(frame_file):
    first = runner.load_slot_state(str(frame_file))
    changed = runner.load_slot_state(str(frame_file), kiwari_values={"posts": 5},
                                     previous_kiwari=first.kiwari)
    written = Path(runner._write_parameters_file(changed))
    assert written.exists()

    back = runner.load_slot_state(str(frame_file), kiwari_values={"posts": 2},
                                  previous_kiwari=changed.kiwari)
    runner._write_parameters_file(back)
    assert not written.exists()


def test_a_saved_value_for_a_key_the_code_dropped_is_ignored_with_a_warning(frame_file):
    path = runner._parameters_file_path(frame_file)
    path.write_text(json.dumps({"schema_version": 1, "values": {"rails": {"value": 3}}}))
    with pytest.warns(UserWarning, match="rails"):
        slot = runner.load_slot_state(str(frame_file))
    assert slot.frame.name == "2 posts"


def test_a_parameters_file_that_is_not_json_is_ignored(frame_file):
    runner._parameters_file_path(frame_file).write_text("{ not json")
    assert runner.load_slot_state(str(frame_file)).frame.name == "2 posts"


def test_a_pattern_may_not_write_to_the_library_it_came_from(frame_file):
    slot = runner.load_slot_state(str(frame_file))
    slot.single_pattern_name = "butt_joints/something"
    assert runner._can_save_parameters(slot) is False
    assert runner._serialize_kiwari_for_slot(slot)["canSave"] is False
    with pytest.raises(ValueError, match="not for a library pattern|library pattern"):
        runner._write_parameters_file(slot)


def test_a_frame_outside_the_workspace_may_not_be_saved_beside(frame_file, tmp_path, monkeypatch):
    slot = runner.load_slot_state(str(frame_file))
    monkeypatch.setenv("KIGUMI_WORKSPACE_ROOT", str(tmp_path / "somewhere else"))
    assert runner._can_save_parameters(slot) is False


def test_a_frame_with_no_parameters_has_nothing_to_save(workspace):
    path = workspace / "plain.py"
    path.write_text(PLAIN_SOURCE)
    with pytest.raises(ValueError, match="nothing to save"):
        runner._write_parameters_file(runner.load_slot_state(str(path)))


# --- patterns ----------------------------------------------------------------


PATTERN_SOURCE = '''
from kumiki import *
from kumiki.patternbook import Pattern
from kumiki.ticket import TimberTicket


def a_post(k):
    return Frame(cut_timbers=[CutTimber(timber=create_timber(
        bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
        length=k.length("height"),
        size=create_v2(inches(4), inches(4)),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket=TimberTicket(path="Post"),
    ), cuts=[])], name="post")


def a_plain_post():
    return a_post(kiwari(height=kiwari.length(mm(1000))))


patterns = [
    Pattern(path="probe/tall", lambda_=make_pattern_from_frame(a_post),
            kiwari=kiwari(height=kiwari.length(mm(1000), minimum=mm(100)))),
    Pattern(path="probe/plain", lambda_=make_pattern_from_frame(a_plain_post)),
]
'''


def test_a_pattern_declares_its_kiwari_and_is_built_with_it(workspace):
    path = workspace / "probe_patterns.py"
    path.write_text(PATTERN_SOURCE)

    slot, result = runner._raise_specific_pattern(str(path), "probe/tall")
    assert result["kiwari"]["applied"]["height"] == {"value": 1.0, "text": "1000mm"}
    assert result["kiwari"]["canSave"] is False

    taller, _ = runner._raise_specific_pattern(str(path), "probe/tall",
                                               kiwari_values={"height": "3m"})
    assert taller.kiwari.length("height") == pytest.approx(3.0)
    assert taller.frame.cut_timbers[0].timber.length == pytest.approx(3.0)


def test_a_pattern_that_declares_nothing_is_called_exactly_as_before(workspace):
    path = workspace / "probe_patterns.py"
    path.write_text(PATTERN_SOURCE)
    slot, result = runner._raise_specific_pattern(str(path), "probe/plain")
    assert result["kiwari"] is None
    assert len(slot.frame.cut_timbers) == 1


# --- the fixture the viewer is driven with -----------------------------------

FIXTURE = Path(__file__).resolve().parent.parent / "kigumi" / "test-fixtures" / "kiwari_frame.py"


def _frame_signature(frame):
    """Enough of a frame to tell whether a parameter did anything."""
    return tuple(
        tuple(round(float(v), 9) for v in (
            cut.timber.get_bottom_position_global()[0],
            cut.timber.get_bottom_position_global()[1],
            cut.timber.get_bottom_position_global()[2],
            cut.timber.get_length_direction_global()[0],
            cut.timber.get_length_direction_global()[2],
            cut.timber.length, cut.timber.size[0], cut.timber.size[1],
        ))
        for cut in frame.cut_timbers
    )


@pytest.mark.parametrize("key,value,also", [
    ("posts", 4, {}),
    ("post_height", "2m", {}),
    ("spacing", "500mm", {}),
    ("size", {"x": "50mm", "y": "150mm"}, {}),
    ("lean", "40deg", {}),
    ("alternating", True, {"lean": "40deg"}),
    ("cap", "40mm", {}),
    ("cap_end", "BOTTOM", {"cap": "40mm"}),
])
def test_every_parameter_the_viewer_fixture_offers_changes_the_frame(key, value, also):
    """A control that does nothing is worse than no control.

    The fixture exists to demonstrate the panel, so a parameter it declares and
    then ignores would make the panel look broken to anyone trying it out.
    """
    module = runner.load_module_from_path(FIXTURE)
    baseline = module.build_frame()

    moved = module.build_frame(baseline.kiwari.resolve({key: value, **also}))
    if also:
        # Compare against the other value being set too, so the change measured
        # is this parameter's own and not its companion's.
        baseline = module.build_frame(baseline.kiwari.resolve(also))

    assert _frame_signature(moved) != _frame_signature(baseline), (
        f"{key!r} is declared by the fixture but changes nothing when set to {value!r}"
    )


def test_the_fixtures_optional_parameter_is_nothing_until_it_is_asked_for():
    module = runner.load_module_from_path(FIXTURE)
    without = module.build_frame()
    assert without.kiwari.length("cap") is None
    with_cap = module.build_frame(without.kiwari.resolve({"cap": "40mm"}))
    assert with_cap.kiwari.length("cap") == pytest.approx(0.04)
    assert len(with_cap.cut_timbers) == len(without.cut_timbers) + 1
    assert without.kiwari.changed_from_defaults() == ()
    assert with_cap.kiwari.changed_from_defaults() == ("cap",)
