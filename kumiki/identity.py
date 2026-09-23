"""How things are named, and how much a name can be trusted.

There are three grades of stability worth keeping apart:

1. the same code produces the same name on every run;
2. an unrelated edit somewhere else leaves the name alone;
3. editing the thing itself leaves the name alone.

An authored name reaches 2 and often 3. A position reaches only 1: insert
something above it and every reference below moves. That is why the types below
keep the two apart instead of blending them into one opaque string.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Tuple


@dataclass(frozen=True)
class DrawingId:
    """Which drawing. What an override in the drawings file names."""

    value: str

    def __str__(self) -> str:
        return self.value

    def __bool__(self) -> bool:
        return bool(self.value)


@dataclass(frozen=True)
class ViewportId:
    """Which viewport of a drawing -- 'front', 'top', the ones a layout produces."""

    value: str

    def __str__(self) -> str:
        return self.value

    def __bool__(self) -> bool:
        return bool(self.value)


@dataclass(frozen=True)
class MeasurementId:
    """Which of several measurements between the same two features."""

    value: str

    def __str__(self) -> str:
        return self.value

    def __bool__(self) -> bool:
        return bool(self.value)


@dataclass(frozen=True)
class TimberPath:
    """
    Timbers are named by path so that they can be stored hierarchically. The hierchy is purely for organization on the user's end.
    No mechanisms to prevent name conflicts. Use ResolvedTimberPath to refer to timbers on a frame unambiguously.
    There should not be duplicate names but we can't really trust the user not to do so.
    """

    # TODO create a PathName object that is just a wrapper around a string with some validators and helpres for extracting part sof the path
    path: str

    def __str__(self) -> str:
        return self.path


@dataclass(frozen=True)
class ResolvedTimberPath:
    """One particular timber in one particular frame. Attained by resolving a TimberPath against a frame. 
    
    Disambiguates duplicate path names using `occurrence`
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
    """Joints are named by path so that they can be stored hierarchically. The hierchy is purely for organization on the user's end.
    """

    path: str

    def __str__(self) -> str:
        return self.path


@dataclass(frozen=True)
class ResolvedJointPath:
    """One particular joint on one particular timber.
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
class FeatureRef:
    """A reference to specific feature on a CSG tree. Must be resolved against an actual CSG tree to find the feature. Does not guarantee that the feature exists.
    """

    #: Held as a tuple; any sequence may be given, which is what reading one
    #: off the wire hands over.
    csg_path: Sequence[str] = ()
    feature: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.csg_path, list):
            object.__setattr__(self, 'csg_path', tuple(self.csg_path))

    def identity(self) -> Tuple[Tuple[str, ...], str]:
        return (tuple(self.csg_path), self.feature or "")

    @property
    def sort_key(self) -> Tuple[str, ...]:
        """The path's length, then the path, then the feature."""
        return (str(len(self.csg_path)), *self.csg_path, self.feature or "")

    def describe(self) -> str:
        trail = " > ".join(self.csg_path)
        return f"{trail} > {self.feature}" if self.feature else trail


class FeaturePath(ABC):
    """A reference to something measurable on one timber.

    Semi-stable on purpose. Nothing here is a position except where it has to
    be: it is the timber, then the labels of the CSG nodes stepped through, then
    the feature on the last of them. Rename any of those and the reference
    breaks, which is the honest outcome; add or reorder around them and it still
    finds what it meant.

    `csg_path` holds labels only, which is what the viewer navigates by and what
    skips the unlabelled intermediates -- the nodes most likely to move.

    Two shapes, because a derived edge is not a feature anyone declared: it is
    the pair of faces that form it (see cutcsg.DerivedEdgeFeature). Keeping them
    apart in the type is what stops a face carrying a second parent, or an edge
    carrying none.
    """

    timber: ResolvedTimberPath

    @abstractmethod
    def identity(self) -> Tuple[Any, ...]:
        """A comparable form, for deciding whether two references are the same.

        A tuple rather than a joined string: a timber path may itself contain
        any separator that might be chosen, and two different references must
        never collapse into one.
        """
        ...

    @property
    @abstractmethod
    def sort_key(self) -> Tuple[str, ...]:
        ...

    @abstractmethod
    def describe(self) -> str:
        """For a person to read -- a log line, or a broken reference in a list."""
        ...


@dataclass(frozen=True)
class SingleFeaturePath(FeaturePath):
    """One declared feature: a face, a point, or an edge a primitive names.

    `feature_type` is kept because one label can name both a face and an edge,
    and a measurement to the wrong one does not look wrong on screen. EDGE
    belongs here as well as in DerivedFeaturePath -- a feature can declare
    itself an edge rather than being derived from two faces.
    """

    timber: ResolvedTimberPath
    ref: FeatureRef = field(default_factory=FeatureRef)
    feature_type: Optional[str] = None

    @property
    def csg_path(self) -> Tuple[str, ...]:
        return tuple(self.ref.csg_path)

    @property
    def feature(self) -> Optional[str]:
        return self.ref.feature

    def identity(self) -> Tuple[Any, ...]:
        csg_path, feature = self.ref.identity()
        return (str(self.timber), csg_path, feature, self.feature_type or "")

    @property
    def sort_key(self) -> Tuple[str, ...]:
        return ("single", str(self.timber), *self.ref.sort_key,
                self.feature_type or "")

    def describe(self) -> str:
        trail = self.ref.describe()
        return f"{self.timber} > {trail}" if trail else str(self.timber)



@dataclass(frozen=True)
class DerivedFeaturePath(FeaturePath):
    """An edge or a point, named by the two features that form it.

    A derived feature is built on demand from a pair of hits and is not among
    any node's declared features, so it cannot be looked up by name: resolving
    one means resolving both parents and deriving again. That also sidesteps
    names not being unique -- two tenons on one timber declare the same face
    names, so their edges share a name while being different edges.

    ALWAYS TWO PARENTS, whichever kind it is. An edge is two faces; a point is
    an edge and a face. Three faces also meet at a point and two edges crossing
    do too, and neither is written here: the group rules keep derivation to one
    route per piece of geometry, so a point arrives as one declared edge
    against one face and never as a set of planes. That is what lets this stay
    a pair rather than becoming a list.

    One timber, not one per parent. Both are always in the same timber's tree,
    and holding a timber on each would allow writing a pair that could never
    resolve.

    `a` and `b` are sorted at construction, because deriving sorts its parents
    too: the same feature written either way round is the same reference.
    """

    timber: ResolvedTimberPath

    # A derived feature IS owned by the parent union/difference/intersection producing the derived feature as worked out by cutcsg.shared_ancestor
    # TODO consider storing the actual owner featureref here as well, or update FeatuerRef so that it's able to support referencing derivedfeatures better so that only 1 ref is needed
    a: FeatureRef = field(default_factory=FeatureRef)
    b: FeatureRef = field(default_factory=FeatureRef)
    #: "EDGE" or "POINT". Carried rather than inferred from the parents: a
    #: reference is read back before anything is resolved, and what it names
    #: has to be known then.
    kind: str = "EDGE"

    def __post_init__(self):
        first, second = sorted((self.a, self.b), key=lambda ref: ref.identity())
        object.__setattr__(self, 'a', first)
        object.__setattr__(self, 'b', second)

    @property
    def feature_type(self) -> str:
        return self.kind

    def identity(self) -> Tuple[Any, ...]:
        return (str(self.timber), self.a.identity(), self.b.identity(), self.kind)

    @property
    def sort_key(self) -> Tuple[str, ...]:
        return ("derived", str(self.timber), self.kind,
                *self.a.sort_key, *self.b.sort_key)

    def describe(self) -> str:
        return f"{self.timber} > {self.a.describe()} x {self.b.describe()}"
