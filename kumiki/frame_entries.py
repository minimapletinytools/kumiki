"""Marking the frames and tools in a file for kigumi to find.

A file may declare any number of frames and tools, sharing one set of parameters::

    params = kiwari(legs=kiwari.count(4, minimum=3))

    @frame
    def stool(k: Kiwari) -> Frame:
        ...

    @frame
    def bench(k: Kiwari) -> Frame:
        ...

    @tool
    def leg_report(frame: Frame, k: Kiwari) -> str:
        return f"{k.count('legs')} legs"

Kigumi builds every `@frame` with the file's one module-level `Kiwari`, bound to the values
in its parameters panel, and shows them together. A `@tool` runs on demand against the shown
frame and its text is displayed. The decorators only mark a function; it is still an ordinary
function to call from a script or a test.

A marked function is admitted only if its annotations say exactly that: `(k: Kiwari) -> Frame`
for a frame, `(frame: Frame, k: Kiwari) -> str` for a tool. `Optional[Kiwari]` is accepted
for the parameters.
"""

import inspect
import typing
from dataclasses import dataclass, replace
from typing import Any, Callable, List, Optional, Tuple, TypeVar

from .kiwari import Kiwari, kiwari as _declare_kiwari

__all__ = ["frame", "tool"]

_MARK = "__kumiki_entry__"
FRAME = "frame"
TOOL = "tool"

F = TypeVar("F", bound=Callable[..., Any])


def frame(function: F) -> F:
    """Marks a function `(k: Kiwari) -> Frame` as one of the file's frames."""
    setattr(function, _MARK, FRAME)
    return function


def tool(function: F) -> F:
    """Marks a function `(frame: Frame, k: Kiwari) -> str` as a tool to run on the file's frame."""
    setattr(function, _MARK, TOOL)
    return function


@dataclass(frozen=True)
class Entry:
    name: str
    function: Callable[..., Any]


@dataclass(frozen=True)
class Rejected:
    name: str
    kind: str
    reason: str


@dataclass(frozen=True)
class ModuleEntries:
    """What a module marked: its admitted frames and tools, those rejected, and its parameters."""
    frames: Tuple[Entry, ...]
    tools: Tuple[Entry, ...]
    rejected: Tuple[Rejected, ...]
    parameters: Kiwari


def _is_class(value: Any, cls: type) -> bool:
    # By module and name, not identity: the runner re-imports kumiki on every reload, so a
    # class from one load is a different object from the same class in another.
    return isinstance(value, type) and (value.__module__, value.__qualname__) == (cls.__module__, cls.__qualname__)


def _is_kiwari(annotation: Any) -> bool:
    if _is_class(annotation, Kiwari):
        return True
    arguments = [argument for argument in typing.get_args(annotation) if argument is not type(None)]
    return (typing.get_origin(annotation) is typing.Union and len(arguments) == 1
            and len(typing.get_args(annotation)) == 2 and _is_class(arguments[0], Kiwari))


def _signature_problem(function: Callable[..., Any], kind: str) -> Optional[str]:
    """Why `function` does not have the signature its mark requires, or None if it does."""
    from .timber import Frame

    try:
        hints = typing.get_type_hints(function)
        parameters = list(inspect.signature(function).parameters.values())
    except Exception as exc:  # an annotation that does not resolve, or no signature at all
        return f"its annotations could not be read: {exc}"

    expected = ("k: Kiwari", "-> Frame") if kind == FRAME else ("frame: Frame, k: Kiwari", "-> str")
    wanted = f"({expected[0]}) {expected[1]}"
    positional = [p for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if len(positional) != len(parameters):
        return f"it should be {wanted}, with no *args, **kwargs or keyword-only parameters"
    checks = [_is_kiwari] if kind == FRAME else [lambda annotation: _is_class(annotation, Frame), _is_kiwari]
    if len(positional) != len(checks):
        return f"it should take {len(checks)} parameter(s): {wanted}"
    for parameter, check in zip(positional, checks):
        if parameter.name not in hints or not check(hints[parameter.name]):
            return f"parameter {parameter.name!r} should be annotated as in {wanted}"
    returns = hints.get("return")
    if (kind == FRAME and not _is_class(returns, Frame)) or (kind == TOOL and returns is not str):
        return f"its return should be annotated as in {wanted}"
    return None


def module_parameters(module: Any) -> Kiwari:
    """The module's one module-level Kiwari, or empty parameters if it declares none."""
    found = [(name, value) for name, value in vars(module).items() if _is_class(type(value), Kiwari)]
    if len(found) > 1:
        names = ", ".join(name for name, _ in found)
        raise TypeError(f"a file shares one set of parameters, but this one declares several Kiwari: {names}")
    return found[0][1] if found else _declare_kiwari()


def module_entries(module: Any) -> ModuleEntries:
    """The frames and tools `module` marked, in source order, each admitted or rejected."""
    marked = [(name, value) for name, value in vars(module).items()
              if callable(value) and getattr(value, _MARK, None) in (FRAME, TOOL)
              and getattr(value, "__module__", None) == module.__name__]
    frames: List[Entry] = []
    tools: List[Entry] = []
    rejected: List[Rejected] = []
    for name, function in marked:
        kind = getattr(function, _MARK)
        problem = _signature_problem(function, kind)
        if problem is not None:
            rejected.append(Rejected(name, kind, problem))
        else:
            (frames if kind == FRAME else tools).append(Entry(name, function))
    # Only a file that marks something is held to one shared kiwari.
    parameters = module_parameters(module) if marked else _declare_kiwari()
    return ModuleEntries(tuple(frames), tuple(tools), tuple(rejected), parameters)


def overlay_frames(frames: List[Any], name: Optional[str], parameters: Optional[Kiwari]) -> Any:
    """Several frames shown together, each where it was built, carrying the shared parameters."""
    from .timber import Frame

    if len(frames) == 1:
        return replace(frames[0], kiwari=parameters)
    joints = [joint for built in frames for joint in (built.source_joints or [])]
    return Frame(
        cut_timbers=[timber for built in frames for timber in built.cut_timbers],
        accessories=[accessory for built in frames for accessory in built.accessories],
        footprints=[footprint for built in frames for footprint in built.footprints],
        drawings=[drawing for built in frames for drawing in built.drawings],
        source_joints=joints or None,
        name=name,
        kiwari=parameters,
    )
