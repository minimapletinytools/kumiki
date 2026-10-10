"""Marking the frames and tools in a file for kigumi to find.

A file may declare any number of frames and tools. Each frame declares its own parameters,
resolves the values it is handed onto them, and returns them on the Frame::

    STOOL = kiwari(legs=kiwari.count(4, minimum=3))

    @frame
    def stool(k: Optional[Kiwari] = None) -> Frame:
        k = STOOL.resolve(k)
        ...
        return Frame.from_joints(joints, kiwari=k)

    @frame
    def bench(k: Optional[Kiwari] = None) -> Frame:
        k = STOOL.resolve(k)    # the same kiwari object: one set of parameters for both
        ...

    @tool
    def leg_report(frame: Frame) -> str:
        return f"{frame.kiwari.count('legs')} legs"

Kigumi builds every `@frame` and shows them together. Frames whose kiwari were resolved from
the same kiwari object share one set of parameters (see `Kiwari.origin`); each different one
gets its own section in the parameters panel. A frame is handed back the values for its own
kiwari, or None on the first build. A `@tool` runs on demand against the shown frame and its
text is displayed. The decorators only mark a function; it is still an ordinary function to
call from a script or a test.

A marked function is admitted only if its annotations say exactly that: `(k: Kiwari) -> Frame`
for a frame, `(frame: Frame) -> str` for a tool. `Optional[Kiwari]` is accepted for the
parameters.

A pattern book marks each of its patterns instead, with a path and, if it takes parameters,
its own kiwari::

    @pattern("basic_joints/basic_mortise_and_tenon", tags=["main"], kiwari=MORTISE_AND_TENON_OPTIONS)
    def basic_mortise_and_tenon(k: Optional[Kiwari] = None) -> Joint:
        ...

A pattern takes `(k: Kiwari)` if it declares a kiwari and nothing otherwise, and returns a
`Frame`, a `Joint` or a `CutCSG`. Further parameters are allowed if they have defaults.
"""

import inspect
import typing
from dataclasses import dataclass, replace
from typing import Any, Callable, List, Optional, Sequence, Tuple, TypeVar

from .kiwari import Kiwari

__all__ = ["frame", "tool", "pattern"]

_MARK = "__kumiki_entry__"
FRAME = "frame"
TOOL = "tool"
PATTERN = "pattern"
_PATTERN_DECLARATION = "__kumiki_pattern__"

F = TypeVar("F", bound=Callable[..., Any])


def frame(function: F) -> F:
    """Marks a function `(k: Kiwari) -> Frame` as one of the file's frames.

    It returns its parameters on the Frame: `Frame(..., kiwari=k)`.
    """
    setattr(function, _MARK, FRAME)
    return function


def tool(function: F) -> F:
    """Marks a function `(frame: Frame) -> str` as a tool to run on the file's frame."""
    setattr(function, _MARK, TOOL)
    return function


@dataclass(frozen=True)
class PatternDeclaration:
    path: str
    tags: Tuple[str, ...]
    kiwari: Optional[Kiwari]


def pattern(path: str, *, tags: Sequence[str] = (), kiwari: Optional[Kiwari] = None) -> Callable[[F], F]:
    """Marks a function as one of a pattern book's patterns, at `path`, with its own kiwari if it takes one.

    `path` is hierarchical ("corner_joints/plain_miter_joint"); each segment is also a tag. Of the
    tags, 'main' shows the pattern when the file is opened and 'poop' hides it from the sidebar.
    """
    if not isinstance(path, str) or not path:
        raise TypeError("@pattern needs a path, e.g. @pattern(\"corner_joints/plain_miter_joint\")")

    def mark(function: F) -> F:
        setattr(function, _MARK, PATTERN)
        setattr(function, _PATTERN_DECLARATION, PatternDeclaration(path, tuple(tags), kiwari))
        return function

    return mark


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
    """What a module marked: its admitted frames and tools, and those rejected."""
    frames: Tuple[Entry, ...]
    tools: Tuple[Entry, ...]
    rejected: Tuple[Rejected, ...]


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
    from .csg.cutcsg import CutCSG
    from .timber import Frame, Joint

    try:
        hints = typing.get_type_hints(function)
        parameters = list(inspect.signature(function).parameters.values())
    except Exception as exc:  # an annotation that does not resolve, or no signature at all
        return f"its annotations could not be read: {exc}"

    is_frame = lambda annotation: _is_class(annotation, Frame)  # noqa: E731
    if kind == FRAME:
        wanted, checks, returns_ok = "(k: Kiwari) -> Frame", [_is_kiwari], is_frame
    elif kind == TOOL:
        wanted, checks, returns_ok = "(frame: Frame) -> str", [is_frame], lambda a: a is str
    else:
        takes_kiwari = getattr(function, _PATTERN_DECLARATION).kiwari is not None
        wanted = f"({'k: Kiwari' if takes_kiwari else ''}) -> Frame | Joint | CutCSG"
        checks = [_is_kiwari] if takes_kiwari else []
        returns_ok = lambda a: is_frame(a) or _is_class(a, Joint) or _is_subclass(a, CutCSG)  # noqa: E731
        # A pattern may keep extra parameters after these, so long as they have defaults.
        extra = parameters[len(checks):]
        if any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) or p.default is p.empty for p in extra):
            return f"it should be {wanted}; any further parameters need defaults"
        parameters = parameters[:len(checks)]

    positional = [p for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if len(positional) != len(parameters):
        return f"it should be {wanted}, with no *args, **kwargs or keyword-only parameters"
    if len(positional) != len(checks):
        return f"it should take {len(checks)} parameter(s): {wanted}"
    for parameter, check in zip(positional, checks):
        if parameter.name not in hints or not check(hints[parameter.name]):
            return f"parameter {parameter.name!r} should be annotated as in {wanted}"
    if not returns_ok(hints.get("return")):
        return f"its return should be annotated as in {wanted}"
    return None


def _is_subclass(value: Any, cls: type) -> bool:
    return isinstance(value, type) and any(_is_class(base, cls) for base in value.__mro__)


def _marked(module: Any, kinds: Tuple[str, ...]) -> List[Tuple[str, Callable[..., Any]]]:
    """The module's own functions marked as one of `kinds`, in source order, each once under its first name."""
    seen: set = set()
    marked = []
    for name, value in vars(module).items():
        if (callable(value) and getattr(value, _MARK, None) in kinds and id(value) not in seen
                and getattr(value, "__module__", None) == module.__name__):
            seen.add(id(value))
            marked.append((name, value))
    return marked


def module_entries(module: Any) -> ModuleEntries:
    """The frames and tools `module` marked, in source order, each admitted or rejected."""
    marked = _marked(module, (FRAME, TOOL))
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
    return ModuleEntries(tuple(frames), tuple(tools), tuple(rejected))


# TODO merging into one Frame keeps kigumi working as is. Instead, kigumi should take several
# frames: the frame list shows the frames at the top level, each opening to its timbers and
# joints, with drawings still at the top level.
def module_patterns(module: Any) -> Tuple[List[Any], Tuple[Rejected, ...]]:
    """The patterns `module` marked with @pattern, in source order, and those rejected for their signature."""
    from .csg.cutcsg import CutCSG
    from .patternbook import Pattern, make_pattern_from_csg, make_pattern_from_frame, make_pattern_from_joint
    from .timber import Joint

    patterns: List[Any] = []
    rejected: List[Rejected] = []
    for name, function in _marked(module, (PATTERN,)):
        problem = _signature_problem(function, PATTERN)
        if problem is not None:
            rejected.append(Rejected(name, PATTERN, problem))
            continue
        declaration: PatternDeclaration = getattr(function, _PATTERN_DECLARATION)
        returns = typing.get_type_hints(function)["return"]
        if _is_subclass(returns, CutCSG):
            lambda_, pattern_type = make_pattern_from_csg(function), "csg"
        elif _is_class(returns, Joint):
            lambda_, pattern_type = make_pattern_from_joint(function), "frame"
        else:
            lambda_, pattern_type = make_pattern_from_frame(function), "frame"
        patterns.append(Pattern(path=declaration.path, lambda_=lambda_, tags=list(declaration.tags),
                                pattern_type=pattern_type, kiwari=declaration.kiwari))
    return patterns, tuple(rejected)


def overlay_frames(frames: List[Any], name: Optional[str]) -> Any:
    """Several frames shown together, each where it was built.

    The overlay carries a kiwari only when every frame was built from the same one; otherwise
    each frame's parameters are its own, and stay on it.
    """
    from .timber import Frame

    if len(frames) == 1:
        return frames[0]
    kiwaris = [getattr(built, "kiwari", None) for built in frames]
    origins = {id(k.origin) for k in kiwaris if k is not None}
    shared = kiwaris[0] if None not in kiwaris and len(origins) == 1 else None
    joints = [joint for built in frames for joint in (built.source_joints or [])]
    return Frame(
        cut_timbers=[timber for built in frames for timber in built.cut_timbers],
        accessories=[accessory for built in frames for accessory in built.accessories],
        footprints=[footprint for built in frames for footprint in built.footprints],
        drawings=[drawing for built in frames for drawing in built.drawings],
        source_joints=joints or None,
        name=name,
        kiwari=shared,
    )
