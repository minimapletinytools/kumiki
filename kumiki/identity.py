"""How things are named, and how much a name can be trusted.

Identity here comes from what the author wrote. Position -- "the third cut",
"the second post" -- is a fallback used only where the author did not
distinguish two things, and where it is used it is a field of its own rather
than something folded into a string, so that code and people can both see which
references are order-dependent and which are not.

There are three grades of stability worth keeping apart:

1. the same code produces the same name on every run;
2. an unrelated edit somewhere else leaves the name alone;
3. editing the thing itself leaves the name alone.

An authored name reaches 2 and often 3. A position reaches only 1: insert
something above it and every reference below moves. That is why the types below
keep the two apart instead of blending them into one opaque string.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Identifier:
    """A name someone chose, wrapped so it cannot be confused with another kind.

    A string today. The wrapper is what lets it grow later without every caller
    changing, and what stops a drawing's name being passed where a viewport's
    was meant -- both are strings, and nothing but a type says they are not
    interchangeable.
    """

    value: str

    def __str__(self) -> str:
        return self.value

    def __bool__(self) -> bool:
        return bool(self.value)


@dataclass(frozen=True)
class DrawingId(Identifier):
    """Which drawing. What an override in the drawings file names."""


@dataclass(frozen=True)
class ViewportId(Identifier):
    """Which viewport of a drawing -- 'front', 'top', the ones a layout produces."""


@dataclass(frozen=True)
class MeasurementId(Identifier):
    """Which of several measurements between the same two features."""


@dataclass(frozen=True)
class TimberPath:
    """What the author calls a timber, before there is a frame to look in.

    A name and nothing more. It cannot say *which* timber when a frame holds two
    of them, because that is not a question a name can answer on its own -- ask
    a frame, with Frame.resolve_timber_path, and get back the ones it matched.
    """

    path: str

    def __str__(self) -> str:
        return self.path


@dataclass(frozen=True)
class ResolvedTimberPath:
    """One particular timber in one particular frame.

    Only obtainable by resolving a TimberPath against a frame, or by parsing the
    form the viewer already uses, because `occurrence` has no meaning until
    there is a frame to count within.

    `occurrence` is the fallback, and the only order-dependent thing here: it
    says which of the timbers sharing a path this is, in the order the frame
    built them. A frame whose timber paths are all distinct never has an
    ambiguous one, which is why a duplicated path is worth warning about -- it
    is the moment a stable reference turns into an order-dependent one.
    """

    path: str
    occurrence: int = 0

    @property
    def timber_path(self) -> TimberPath:
        """The name, without the frame-dependent part."""
        return TimberPath(self.path)

    def __str__(self) -> str:
        """The form the viewer has always used as a member key."""
        return f"{self.path}#{self.occurrence}"

    @classmethod
    def parse(cls, text: str) -> 'ResolvedTimberPath':
        """Read one back from the viewer's member key.

        A path may itself contain anything except the final '#n', so the split
        is from the right.
        """
        name, separator, occurrence = str(text).rpartition("#")
        if separator and occurrence.isdigit():
            return cls(path=name, occurrence=int(occurrence))
        return cls(path=str(text))


@dataclass(frozen=True)
class JointPath:
    """What a joint is called, before there is a timber to look in.

    The same split as TimberPath, for the same reason: a joint cannot say which
    of two identical joints it is, because it does not know the order it was cut
    in -- only the timber holding the cuts does. Ask one, with
    CutTimber.resolve_joint_path.
    """

    path: str

    def __str__(self) -> str:
        return self.path


@dataclass(frozen=True)
class ResolvedJointPath:
    """One particular joint on one particular timber.

    `occurrence` says which of the same-named joints on that timber this is, in
    the order the timber's cuts were applied. Scoped to the timber rather than
    the frame, so a joint added on another timber renumbers nothing here.

    As with a timber, this is the fallback and the only order-dependent thing:
    a timber whose joints are all named differently never has an ambiguous one.
    Two identical joints on one timber -- both ends of a brace, say -- are the
    case it exists for.
    """

    path: str
    occurrence: int = 0

    @property
    def joint_path(self) -> JointPath:
        """The name, without the timber-dependent part."""
        return JointPath(self.path)

    def __str__(self) -> str:
        return f"{self.path}#{self.occurrence}"

    @classmethod
    def parse(cls, text: str) -> 'ResolvedJointPath':
        """Read one back from a stored path segment.

        No '#n' means occurrence 0, so a reference written before joints were
        told apart still points where it always did.
        """
        name, separator, occurrence = str(text).rpartition("#")
        if separator and occurrence.isdigit():
            return cls(path=name, occurrence=int(occurrence))
        return cls(path=str(text))


@dataclass(frozen=True)
class FeaturePath:
    """Where a feature is, as instructions for finding it again.

    Semi-stable on purpose. Nothing here is a position except where it has to
    be: it is the timber, then the labels of the CSG nodes stepped through, then
    the feature on the last of them. Rename any of those and the reference
    breaks, which is the honest outcome; add or reorder around them and it still
    finds what it meant.

    `csg_path` holds labels only, which is what the viewer navigates by and
    what skips the unlabelled intermediates -- the nodes most likely to move.
    `feature` names the declared feature on the node arrived at, and
    `feature_type` is FACE, EDGE or POINT, kept because one label can name both
    a face and an edge and a measurement to the wrong one does not look wrong on
    screen.
    """

    timber: ResolvedTimberPath
    csg_path: Tuple[str, ...] = ()
    feature: Optional[str] = None
    feature_type: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.csg_path, list):
            object.__setattr__(self, 'csg_path', tuple(self.csg_path))
        if isinstance(self.timber, str):
            object.__setattr__(self, 'timber', ResolvedTimberPath.parse(self.timber))

    def identity(self) -> Tuple[str, Tuple[str, ...], str, str]:
        """A comparable form, for deciding whether two references are the same.

        A tuple rather than a joined string: a timber path may itself contain
        any separator that might be chosen, and two different references must
        never collapse into one.
        """
        return (str(self.timber), self.csg_path, self.feature or "", self.feature_type or "")

    def describe(self) -> str:
        """For a person to read -- a log line, or a broken reference in a list."""
        trail = " > ".join((str(self.timber),) + self.csg_path)
        return f"{trail} > {self.feature}" if self.feature else trail
