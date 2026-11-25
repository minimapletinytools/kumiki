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

A frame also offers tools: functions the viewer can run on demand, each returning text to show.
A tool can take parameters of its own, declared as a kiwari, set in the viewer before it runs.
Tools are experimental: their shape may change in a patch release::

    frame = replace(frame, tools=[Tool("leg report", "How many legs there are",
                                       lambda: f"{k.count('legs')} legs")])

    EXPORT = kiwari(scale=kiwari.number(1000, about="Model units to the file's"))
    Tool("export", "Write the frame to an STL", lambda t: export(frame, t.number("scale")), kiwari=EXPORT)

A tool that takes a keyword-only `kigumi` argument can show extra accessories in the viewer, such as
a preview of what it exports. They last until the frame is rebuilt and are never saved::

    def export(t, *, kigumi):
        kigumi.remove_all_extra_accessories()
        kigumi.add_extra_accessory(CSGAccessory(Transform.identity(), jig), name="jig")
        ...
"""

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterable, List, Mapping, Optional, Tuple

if TYPE_CHECKING:
    from .drawings.drawing import Drawing
    from .kiwari import Kiwari
    from .timber import Accessory

__all__ = ["Finishing", "FinishingCancelled", "Kigumi", "Tool"]


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


class Kigumi:
    """What a tool is handed as `kigumi`: the extra accessories the viewer shows. Experimental; may change.

    Extra accessories are shown in their own section of the viewer's tree and can be deleted there.
    They are not part of the frame: they are cleared when it is rebuilt and never saved. Outside
    Kigumi the calls are only recorded, in `extra_accessories`.
    """

    def __init__(self, extra_accessories: Iterable[Tuple[str, "Accessory"]] = ()) -> None:
        #: The (name, accessory) pairs to show, in order.
        self.extra_accessories: List[Tuple[str, "Accessory"]] = list(extra_accessories)

    def add_extra_accessory(self, accessory: "Accessory", name: Optional[str] = None) -> None:
        """Show `accessory` in the viewer, listed as `name` (its ticket's name, or its type, by default)."""
        if name is None:
            ticket_name = getattr(getattr(accessory, "ticket", None), "name", None)
            name = ticket_name if ticket_name and ticket_name != "[no-name]" else type(accessory).__name__
        self.extra_accessories.append((name, accessory))

    def remove_all_extra_accessories(self) -> None:
        """Remove every extra accessory, including those added by earlier runs."""
        self.extra_accessories.clear()


def _takes_kigumi(run: Callable[..., Any]) -> bool:
    """Return whether `run` has a keyword-only parameter named `kigumi`."""
    try:
        parameter = inspect.signature(run).parameters.get("kigumi")
    except (TypeError, ValueError):
        return False
    return parameter is not None and parameter.kind is inspect.Parameter.KEYWORD_ONLY


@dataclass(frozen=True)
class Tool:
    """A tool a frame offers, returning the text the viewer shows. Experimental; may change.

    With a `kiwari`, `run` is given its resolved parameters; without one, it takes nothing. If `run`
    has a keyword-only parameter `kigumi`, it is also given a `Kigumi`.
    """
    name: str
    description: str
    run: Callable[..., str]
    kiwari: Optional["Kiwari"] = None

    def call(self, values: Optional[Mapping[str, Any]] = None, *, kigumi: Optional[Kigumi] = None) -> str:
        """Run the tool, with `values` laid over its kiwari's defaults if it has one.

        `kigumi` is passed on to a tool that takes one; a fresh `Kigumi` if None.
        """
        extra = {"kigumi": kigumi if kigumi is not None else Kigumi()} if _takes_kigumi(self.run) else {}
        if self.kiwari is None:
            return self.run(**extra)
        return self.run(self.kiwari.resolve(values), **extra)
