"""A frame's deferred routines and tools (kumiki.deferred)."""

import pytest

from kumiki import (CutTimber, Deferred, DeferredCancelled, Drawing, Frame, ToolAd, create_timber, create_v2,
                    create_v3, mm)
from kumiki.frame_decorators import overlay_frames


def _frame(name="frame"):
    post = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")
    return Frame(cut_timbers=[CutTimber(post, cuts=[])], name=name)


def _drawing(frame, name):
    return Drawing(name=name, timbers=[frame.cut_timbers[0].timber])


def test_a_deferred_routine_does_not_run_during_the_build():
    ran = []
    frame = _frame().with_deferred(lambda deferred: ran.append(True))

    assert ran == [] and frame.drawings == []


def test_run_deferred_adds_what_the_routines_make_and_leaves_none_to_run():
    built = _frame()

    def later(deferred: Deferred) -> None:
        for name in ("a", "b"):
            deferred.add_drawing(_drawing(built, name))

    frame = built.with_deferred(later).with_deferred(lambda d: d.add_drawing(_drawing(built, "c"))).run_deferred()

    assert [drawing.name for drawing in frame.drawings] == ["a", "b", "c"]
    assert frame.deferred == ()


def test_a_drawing_of_another_frame_is_refused():
    other = _frame("other")
    frame = _frame().with_deferred(lambda deferred: deferred.add_drawing(_drawing(other, "stray")))

    with pytest.raises(ValueError, match="equal copy"):
        frame.run_deferred()


def test_once_cancelled_every_call_stops_the_routine():
    deferred = Deferred(on_drawing=lambda drawing: None, should_cancel=lambda: True)

    with pytest.raises(DeferredCancelled):
        deferred.progress(1, 2)


def test_progress_reaches_whoever_asked_for_it():
    seen = []
    Deferred(on_drawing=lambda drawing: None, on_progress=lambda *step: seen.append(step)).progress(1, 3, "plan")

    assert seen == [(1, 3, "plan")]


def test_shown_together_frames_keep_their_routines_and_tools():
    first = _frame("first").with_deferred(lambda d: None)
    second = Frame(cut_timbers=[], name="second", tools=[ToolAd("count", "Counts", lambda: "1")])

    shown = overlay_frames([first, second], "both")

    assert len(shown.deferred) == 1 and [tool.name for tool in shown.tools] == ["count"]
