"""The runner running a frame's finishing routines and its tools."""

import pytest

from tests.test_kigumi_kiwari_protocol import _put_kumiki_back, runner, workspace  # noqa: F401 (fixtures)

SOURCE = '''
from kumiki import *


@frame
def posts(k: Optional[Kiwari] = None) -> Frame:
    post = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")
    frame = Frame(cut_timbers=[CutTimber(post, cuts=[])], name="posts",
                  tools=[Tool("count", "How many timbers", lambda: f"{len(frame.cut_timbers)} timbers"),
                         Tool("not text", "Returns a number", lambda: 42)])

    def later(finishing: Finishing) -> None:
        for name in ("first", "second"):
            finishing.add_drawing(Drawing(name=name, timbers=[post]))

    return frame.with_finishing(later)
'''


class _Context:
    def __init__(self, cancel_after=None):
        self.reports = []
        self._cancel_after = cancel_after

    def should_cancel(self):
        return self._cancel_after is not None and len(self.reports) >= self._cancel_after

    def progress(self, done, total=None, label=None):
        self.report(done=done, total=total, label=label)

    def report(self, **fields):
        self.reports.append(fields)


@pytest.fixture
def slot(workspace):  # noqa: F811
    path = workspace / "posts.py"
    path.write_text(SOURCE)
    return runner.load_slot_state(str(path))


def test_drawings_come_once_the_finishing_work_runs(slot):
    assert runner.collect_drawings(slot.frame, slot.file_path) == []
    context = _Context()

    assert runner._run_finishing(slot, context) == {"drawings": ["first", "second"]}

    assert [d["name"] for d in runner.collect_drawings(slot.frame, slot.file_path)] == ["first", "second"]
    assert [report["drawing"] for report in context.reports] == ["first", "second"]


def test_cancelled_work_stops_at_its_next_drawing(slot):
    from kumiki.finishing import FinishingCancelled  # the kumiki the runner loaded

    with pytest.raises(FinishingCancelled):
        runner._run_finishing(slot, _Context(cancel_after=1))

    assert [drawing.name for drawing in slot.frame.drawings] == ["first"]


def test_a_tool_runs_and_gives_its_text(slot):
    assert runner.run_tool(slot, "count") == {"name": "count", "output": "1 timbers"}


def test_a_tool_must_give_text(slot):
    with pytest.raises(TypeError, match="expected str"):
        runner.run_tool(slot, "not text")


def test_an_unknown_tool_says_what_there_is(slot):
    with pytest.raises(ValueError, match="count"):
        runner.run_tool(slot, "nope")
