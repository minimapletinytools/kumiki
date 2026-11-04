"""Work a frame leaves for after it is shown, and the tools it offers.

A frame function can hand back slow work, such as generated drawings, to run once the frame is on
screen. The routine is written inside the frame function, so it uses what the build computed::

    @frame
    def shed(k: Optional[Kiwari] = None) -> Frame:
        frame = Frame.from_joints(joints, kiwari=k)
        groups = match_timbers(frame.cut_timbers)

        def later(finishing: Finishing) -> None:
            for group in groups:
                finishing.add_drawing(piece_drawing(group))

        return frame.with_finishing(later)

Kigumi runs the routine in the background after showing the frame, and shows each drawing as it
is added. `frame.finish()` runs it straight away, for scripts and tests.

A frame also offers tools: functions the viewer can run on demand, each returning text to show::

    frame = replace(frame, tools=[Tool("leg report", "How many legs there are",
                                         lambda: f"{k.count('legs')} legs")])
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from .drawings.drawing import Drawing

__all__ = ["Finishing", "FinishingCancelled", "Tool"]


class FinishingCancelled(Exception):
    """Raised inside a finishing routine when its frame has been replaced and its work is no longer wanted."""


class Finishing:
    """What a finishing routine is handed: where to put what it makes.

    Every call raises FinishingCancelled once the work is no longer wanted, so a routine stops at
    its next call without checking for itself.
    """

    def __init__(self,
                 on_drawing: Callable[["Drawing"], None],
                 on_progress: Optional[Callable[[int, Optional[int], Optional[str]], None]] = None,
                 should_cancel: Optional[Callable[[], bool]] = None) -> None:
        self._on_drawing = on_drawing
        self._on_progress = on_progress
        self._should_cancel = should_cancel

    def _stop_if_cancelled(self) -> None:
        if self._should_cancel is not None and self._should_cancel():
            raise FinishingCancelled()

    def add_drawing(self, drawing: "Drawing") -> None:
        """Add a drawing to the frame. It must be of this frame's own timbers."""
        self._stop_if_cancelled()
        self._on_drawing(drawing)

    def progress(self, done: int, total: Optional[int] = None, label: Optional[str] = None) -> None:
        """Say how far along the routine is: `done` of `total` steps, and what it is doing now."""
        self._stop_if_cancelled()
        if self._on_progress is not None:
            self._on_progress(done, total, label)


@dataclass(frozen=True)
class Tool:
    """A tool a frame offers: `run()` returns the text the viewer shows."""
    name: str
    description: str
    run: Callable[[], str]
