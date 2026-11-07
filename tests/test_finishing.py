"""A frame's finishing routines and tools (kumiki.finishing)."""

import pytest

from kumiki import (CutTimber, Finishing, FinishingCancelled, Drawing, Frame, Tool, create_timber, create_v2,
                    create_v3, kiwari, mm)
from kumiki.frame_decorators import overlay_frames


def _frame(name="frame"):
    post = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")
    return Frame(cut_timbers=[CutTimber(post, cuts=[])], name=name)


def _drawing(frame, name):
    return Drawing(name=name, timbers=[frame.cut_timbers[0].timber])


def test_a_finishing_routine_does_not_run_during_the_build():
    ran = []
    frame = _frame().with_finishing(lambda finishing: ran.append(True))

    assert ran == [] and frame.drawings == []


def test_finish_adds_what_the_routines_make_and_leaves_none_to_run():
    built = _frame()

    def later(finishing: Finishing) -> None:
        for name in ("a", "b"):
            finishing.add_drawing(_drawing(built, name))

    frame = built.with_finishing(later).with_finishing(lambda d: d.add_drawing(_drawing(built, "c"))).finish()

    assert [drawing.name for drawing in frame.drawings] == ["a", "b", "c"]
    assert frame.finishing == ()


def test_a_drawing_of_another_frame_is_refused():
    other = _frame("other")
    frame = _frame().with_finishing(lambda finishing: finishing.add_drawing(_drawing(other, "stray")))

    with pytest.raises(ValueError, match="equal copy"):
        frame.finish()


def test_once_cancelled_every_call_stops_the_routine():
    finishing = Finishing(on_drawing=lambda drawing: None, should_cancel=lambda: True)

    with pytest.raises(FinishingCancelled):
        finishing.progress(1, 2)


def test_progress_reaches_whoever_asked_for_it():
    seen = []
    Finishing(on_drawing=lambda drawing: None, on_progress=lambda *step: seen.append(step)).progress(1, 3, "plan")

    assert seen == [(1, 3, "plan")]


def test_shown_together_frames_keep_their_routines_and_tools():
    first = _frame("first").with_finishing(lambda d: None)
    second = Frame(cut_timbers=[], name="second", tools=[Tool("count", "Counts", lambda: "1")])

    shown = overlay_frames([first, second], "both")

    assert len(shown.finishing) == 1 and [tool.name for tool in shown.tools] == ["count"]


def test_a_tool_without_parameters_is_run_with_nothing():
    assert Tool("count", "Counts", lambda: "1").call() == "1"


def test_a_tool_with_parameters_is_given_them_over_its_defaults():
    tool = Tool("scale", "Says its scale and name", lambda t: f"{t.number('scale')} {t.text('name')}",
                kiwari=kiwari(scale=kiwari.number(2, minimum=0), name=kiwari.text("jig")))

    assert tool.call() == "2.0 jig"
    assert tool.call({"scale": {"value": 5}}) == "5.0 jig"
    with pytest.raises(ValueError, match="at least 0"):
        tool.call({"scale": {"value": -1}})
