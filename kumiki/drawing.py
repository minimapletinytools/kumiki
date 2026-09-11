"""What a frame asks to have drawn.

A drawing names itself and the timbers it is of, and never a layout: where the
views go on the page, which way their cameras face and at what scale are worked
out from the timbers themselves. So a frame says what it wants drawn and never
how to draw it, and the same drawing is as right on a small sheet as on a large
one.

Measurements hang off the viewport they are drawn in, because a drawing is a
projection and a dimension only means anything in the plane it is projected
onto. The same two features measured in the front elevation and in the plan view
are two dimensions with two numbers, and either may be meaningless while the
other is fine.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union

from .identity import (DrawingId, FeaturePath, MeasurementId, TimberPath,
                       ViewportId, identity_order)
from .rule import Numeric


class MeasurementSpace(Enum):
    """Whether a measurement is taken on the sheet or in the solid.

    A drawing is a projection, so a dimension on one measures what the viewport
    shows. The same two features also have a relationship in three dimensions,
    which is a different number and sometimes a different question entirely --
    two faces at an angle have an angle between them in the solid, and cover
    each other on the sheet.
    """

    PROJECTED = "projected"
    THREE_D = "3d"


class MeasurementOperation(Enum):
    """What is being computed. RADIUS and ARC_LENGTH belong here when they come."""

    DISTANCE = "distance"
    ANGLE = "angle"


class MeasurementDirection(Enum):
    """Which direction a distance is taken along.

    PERPENDICULAR is the shortest distance and means something in either space.
    HORIZONTAL and VERTICAL are directions *of the sheet*, so they exist only
    when projected -- the solid has no up. The three-dimensional counterpart is
    a distance along a named direction, which does not exist yet.
    """

    PERPENDICULAR = "perpendicular"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class MeasurementFeature(Enum):
    """What a feature behaves as, for the purpose of measuring it.

    Four members, but two of them belong to one space each. A face is a PLANE
    in the solid and becomes either a LINE or an AREA once projected, depending
    on whether it is seen edge-on. AREA is the projected dead end: a face seen
    at an angle covers the view, and there is no distance between two things
    that each cover the view.

    That one distinction is the whole of the difference between the two spaces.
    Face to face angle and perpendicular distance are perfectly good questions
    in the solid, where both are planes, and meaningless on the sheet, where
    both are areas.
    """

    POINT = "point"
    LINE = "line"
    #: Solid only. A face, before projection.
    PLANE = "plane"
    #: Projected only. A face seen at an angle, which cannot be dimensioned.
    AREA = "area"


#: What a feature can project to. A point stays a point; an edge seen end-on
#: becomes one; a face is a line edge-on and an area otherwise. Which of the two
#: it is depends on the viewing direction, so only the viewport can say -- this
#: says what the possibilities are.
PROJECTS_TO: Mapping[MeasurementFeature, Tuple[MeasurementFeature, ...]] = {
    MeasurementFeature.POINT: (MeasurementFeature.POINT,),
    MeasurementFeature.LINE: (MeasurementFeature.POINT, MeasurementFeature.LINE),
    MeasurementFeature.PLANE: (MeasurementFeature.LINE, MeasurementFeature.AREA),
}


@dataclass(frozen=True)
class MeasurementKind:
    """What a dimension is measuring.

    A structured value rather than one name per combination. The combinations
    multiply -- every operation needs a projected form and a solid one, and a
    distance needs a direction -- so spelling each out by hand means a name to
    invent and keep in sync for each, and the list doubles again when RADIUS or
    a distance along a named direction arrives.

    The name is composed from the parts instead, which is why there is no
    mapping to maintain: `projected_horizontal_distance` is exactly its three
    fields, read out.
    """

    operation: MeasurementOperation
    space: MeasurementSpace
    #: Only meaningful for a DISTANCE. An angle has no direction to take.
    direction: MeasurementDirection = MeasurementDirection.PERPENDICULAR

    def __post_init__(self):
        for field_name, kind in (("operation", MeasurementOperation),
                                 ("space", MeasurementSpace),
                                 ("direction", MeasurementDirection)):
            value = getattr(self, field_name)
            if isinstance(value, str):
                object.__setattr__(self, field_name, kind(value))
        if (self.space is MeasurementSpace.THREE_D
                and self.direction is not MeasurementDirection.PERPENDICULAR):
            raise ValueError(
                f"{self.direction.value} is a direction of the sheet, so it only exists "
                "projected. The solid has no up."
            )

    @property
    def name(self) -> str:
        """The composed name, e.g. `projected_horizontal_distance`."""
        parts = []
        if self.space is MeasurementSpace.PROJECTED:
            parts.append("projected")
        if self.operation is MeasurementOperation.DISTANCE:
            parts.append(self.direction.value)
        parts.append(self.operation.value)
        return "_".join(parts)

    def __str__(self) -> str:
        return self.name

    def as_wire(self) -> dict:
        """The form a file holds, which says each part rather than naming the whole.

        Not the composed name, because one name is ambiguous: `angle` is what
        this calls a solid angle, and is also what every measurement written
        before spaces existed calls a projected one. Saying the space outright
        costs a few characters and cannot be misread.
        """
        return {
            "operation": self.operation.value,
            "space": self.space.value,
            "direction": self.direction.value,
        }

    @classmethod
    def from_wire(cls, value) -> Optional['MeasurementKind']:
        """A kind as read from a file: the structured form, or an older name."""
        if value is None:
            return None
        if isinstance(value, Mapping):
            return cls(
                MeasurementOperation(value.get("operation", "distance")),
                MeasurementSpace(value.get("space", "projected")),
                MeasurementDirection(value.get("direction", "perpendicular")),
            )
        return cls.parse(str(value))

    @classmethod
    def parse(cls, text: str) -> 'MeasurementKind':
        """Read a kind back from its name, or from one of the older names.

        The old names were all projected, and `aligned` and `perpendicular` both
        become a perpendicular distance: between two points the shortest
        distance IS the distance, which is why the two collapsed into one.

        Where an old name and a new one collide -- `angle`, which now composes
        for a SOLID angle -- the old reading wins, because every file that
        contains the word was written meaning the old one. Solid kinds are
        written structured (see as_wire), so nothing needs the ambiguous form.
        """
        legacy = _LEGACY_KIND_NAMES.get(str(text))
        if legacy is not None:
            return legacy
        parts = str(text).split("_")
        space = MeasurementSpace.PROJECTED if parts[:1] == ["projected"] else MeasurementSpace.THREE_D
        if space is MeasurementSpace.PROJECTED:
            parts = parts[1:]
        if parts == ["angle"]:
            return cls(MeasurementOperation.ANGLE, space)
        if len(parts) == 2 and parts[1] == "distance":
            return cls(MeasurementOperation.DISTANCE, space, MeasurementDirection(parts[0]))
        raise ValueError(f"not a measurement kind: {text!r}")


def _projected(operation, direction=MeasurementDirection.PERPENDICULAR) -> MeasurementKind:
    return MeasurementKind(operation, MeasurementSpace.PROJECTED, direction)


def _solid(operation) -> MeasurementKind:
    return MeasurementKind(operation, MeasurementSpace.THREE_D)


#: The names measurements were written with before kinds had structure.
_LEGACY_KIND_NAMES: Mapping[str, MeasurementKind] = {
    # Between two points, the direct distance and the perpendicular distance
    # are the same number, so these two are now one kind.
    "aligned": _projected(MeasurementOperation.DISTANCE),
    "perpendicular": _projected(MeasurementOperation.DISTANCE),
    "horizontal": _projected(MeasurementOperation.DISTANCE, MeasurementDirection.HORIZONTAL),
    "vertical": _projected(MeasurementOperation.DISTANCE, MeasurementDirection.VERTICAL),
    "angle": _projected(MeasurementOperation.ANGLE),
}


def kinds_for(
    feature_a: MeasurementFeature,
    feature_b: MeasurementFeature,
    space: MeasurementSpace,
    parallel: Optional[bool] = None,
) -> Tuple[MeasurementKind, ...]:
    """Which kinds a pair admits, best first. Empty when it admits none.

    *feature_a* and *feature_b* are what the two features behave as in this
    space -- already projected, if the space is projected. *parallel* says
    whether two directions line up, and is only consulted when both are lines
    or planes, since that is the only pair whose answer depends on it.

    The rules are here rather than in the viewer because they are the same rules
    in both, and two copies of a table is how a table drifts. What the viewer
    keeps is the projection itself, which needs a camera to work out.
    """
    pair = {feature_a, feature_b}

    if MeasurementFeature.AREA in pair:
        # A face seen at an angle covers the view: nothing to measure to, and
        # its middle is a point about nothing.
        return ()
    if MeasurementFeature.PLANE in pair and space is MeasurementSpace.PROJECTED:
        raise ValueError("a plane is a solid-space feature; project it first")
    if MeasurementFeature.AREA in pair and space is MeasurementSpace.THREE_D:
        raise ValueError("an area is a projected feature; it has no solid counterpart")

    flat = {MeasurementFeature.LINE, MeasurementFeature.PLANE}
    both_flat = feature_a in flat and feature_b in flat
    if both_flat and parallel is False:
        return (_projected(MeasurementOperation.ANGLE) if space is MeasurementSpace.PROJECTED
                else _solid(MeasurementOperation.ANGLE),)

    if space is MeasurementSpace.THREE_D:
        return (_solid(MeasurementOperation.DISTANCE),)

    perpendicular = _projected(MeasurementOperation.DISTANCE)
    if pair == {MeasurementFeature.POINT}:
        # Both points: the sheet's own directions are as good a question as the
        # distance itself, and often the one wanted.
        return (
            perpendicular,
            _projected(MeasurementOperation.DISTANCE, MeasurementDirection.HORIZONTAL),
            _projected(MeasurementOperation.DISTANCE, MeasurementDirection.VERTICAL),
        )
    # Point to line, or two parallel lines. A horizontal or vertical component
    # is technically available here too and is not offered: it is not what
    # anyone means by the distance to a line.
    return (perpendicular,)


@dataclass(frozen=True)
class MeasurementPlacement:
    """Where a dimension sits, as distinct from what it measures.

    Its own object rather than a bare number because placement grows: which
    side of the feature the line sits on, where the text goes when it will not
    fit between the arrows, whether a witness line is drawn. `offset` is the
    only one of those that exists yet.

    None throughout means "wherever the viewport puts it", which is what every
    measurement written before placement existed means.
    """

    #: How far the dimension line sits from the features, in page units.
    #: None asks the viewport for its own default.
    offset: Optional[float] = None

    @classmethod
    def from_wire(cls, value) -> Optional['MeasurementPlacement']:
        """A placement as read from a file: the mapping form, or one already built.

        The same shape as MeasurementKind.from_wire, and for the same reason:
        the field holds a MeasurementPlacement, and saying so is only true if
        the conversion from what a file holds happens somewhere that takes the
        file's form as its argument type.
        """
        if value is None or isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            offset = value.get("offset")
            return cls(offset=None if offset is None else float(offset))
        raise TypeError(f"Expected a placement or a mapping, got {type(value).__name__}")


@dataclass(frozen=True)
class Measure:
    """A dimension between two features, drawn in one viewport.

    TODO identity should include kind as well
    TODO should we enforce canonical ordering on anchor_a / anchor_b, we can create a new class CanonicalFeaturePathPair or something
    Identity is the anchors, plus `measure_id` when the same pair is measured
    more than once in the same viewport -- deliberately not a position in a
    list, so that a measurement generated by an algorithm keeps whatever the
    drawings file has said about it when the algorithm next runs and emits a
    different number of them. It is scoped to the viewport, since that is where
    a measurement lives.
    """

    anchor_a: FeaturePath
    anchor_b: FeaturePath
    #: The kind to use, or None for the default. A file's form -- a name, or
    #: the structured mapping -- goes through MeasurementKind.from_wire first:
    #: parsing is its own step, and doing it here as well left the declared
    #: type unable to say which of the two this is.
    kind: Optional[MeasurementKind] = None
    # the measurementId which allows multiple measurements with the same anchors and kind
    measure_id: Optional[MeasurementId] = None
    #: Where the dimension sits. Deliberately not part of identity: moving a
    #: dimension line is not measuring something else.
    placement: Optional[MeasurementPlacement] = None

    def __post_init__(self):
        self._canonicalise_anchors()

    def _canonicalise_anchors(self) -> None:
        """Put the two anchors in one order, so a pair cannot be written twice.

        Measuring A to B and measuring B to A are the same measurement, and
        without this they are two: two entries in a viewport, two dimensions
        drawn on top of each other, and a file override that matches neither.
        Sorting at creation means there is only ever one way to write it down.

        Swapping is safe because every kind there is today is symmetric -- each
        computes an absolute value or a length, so the number does not depend on
        which anchor came first. The one thing that does is which SIDE the
        dimension line sits on, since it is offset perpendicular to the run
        between the anchors, and reversing the run reverses the perpendicular.
        The offset is signed, so negating it puts the line back where it was.

        WHEN AN ASYMMETRIC KIND ARRIVES -- one where A to B and B to A are
        genuinely different measurements, rather than the same one drawn from
        the other end -- this has to stop being unconditional and start asking
        the kind. It is written here rather than left to be discovered because
        by then the ordering will look like something nothing depends on.
        """
        if self.anchor_a is None or self.anchor_b is None:
            return
        first, second = self.anchor_a, self.anchor_b
        if identity_order(first.identity()) <= identity_order(second.identity()):
            return
        object.__setattr__(self, 'anchor_a', second)
        object.__setattr__(self, 'anchor_b', first)
        if self.placement is not None and self.placement.offset is not None:
            object.__setattr__(
                self, 'placement',
                replace(self.placement, offset=-self.placement.offset))

    @staticmethod
    def kind_identity(kind: Optional['MeasurementKind']) -> Tuple:
        """A kind in a comparable form, or an empty one for "whichever is natural".

        The parts rather than the name, because a name can arrive as an older
        one -- `angle` and `projected_angle` are the same kind written years
        apart, and must not read as two different measurements.
        """
        if kind is None:
            return ()
        wire = kind.as_wire()
        return (wire["operation"], wire["space"], wire["direction"])

    def pair_identity(self) -> Tuple[Tuple, Tuple]:
        """Just the two features, without saying what is measured between them."""
        return (self.anchor_a.identity(), self.anchor_b.identity())

    def identity(self) -> Tuple[Tuple, Tuple, Tuple, str]:
        """What makes this measurement itself, within its viewport.

        The anchors come already in one order (see _canonicalise_anchors), so
        measuring A to B and measuring B to A are one measurement.

        The kind is part of it, because two kinds between one pair are two
        dimensions and both should show: the horizontal and the vertical
        between the same two points is an ordinary thing to want. The
        alternative was making the author mint a measure_id to tell them apart,
        which is a chore for the common case.

        The cost, which the editing flow has to know about: changing a
        measurement's kind changes its identity. So an override cannot edit a
        code measurement's kind in place -- it is a different measurement now.
        Say it as suppressing the original and adding the new one, which is
        what those two mechanisms are already for.
        """
        return (
            self.anchor_a.identity(),
            self.anchor_b.identity(),
            self.kind_identity(self.kind),
            str(self.measure_id or ""),
        )


class MeasurementSource(Enum):
    """Where a measurement came from, which decides what it may replace.

    Three tiers, each able to replace the ones below it and nothing else. An
    algorithm proposes, a person writing code decides, and the drawings file --
    which is to say the viewer -- has the last word.
    """

    #: An algorithm produced it. Replaceable by anything.
    PYTHON_GENERATED = "python_generated"
    #: Somebody wrote it in the frame's code.
    PYTHON_CODED = "python_coded"
    #: The drawings file, written by the viewer or by hand.
    FILE_OVERRIDE = "file_override"


_SOURCE_RANK = {
    MeasurementSource.PYTHON_GENERATED: 0,
    MeasurementSource.PYTHON_CODED: 1,
    MeasurementSource.FILE_OVERRIDE: 2,
}


def does_override(
    candidate: Measure,
    existing: Measure,
    candidate_source: MeasurementSource,
    existing_source: MeasurementSource,
) -> bool:
    """Whether *candidate* replaces *existing*, rather than sitting beside it.

    A tier only replaces one below it: two measurements from the same tier are
    two measurements, however alike, and a lower tier never displaces a higher.

    What counts as the same measurement depends on which tier is asking, and
    the difference is the kind:

    - A FILE_OVERRIDE matches on everything, kind included. It was written
      against a particular measurement -- the horizontal one, say -- and the
      vertical between the same two features is a different dimension it was
      never about. Changing a kind is therefore not an edit but a different
      measurement, said as suppressing one and adding another.

    - Anything else matches on the two features alone. A person writing a
      measurement in code is overruling what an algorithm proposed for that
      pair, and would have to guess the generated kind to say so otherwise --
      which is exactly the sort of thing that stops working when the algorithm
      is next changed.
    """
    return does_override_identities(
        candidate.identity(), candidate.pair_identity(), candidate_source,
        existing.identity(), existing.pair_identity(), existing_source,
    )


def does_override_identities(
    candidate_identity: Tuple,
    candidate_pair: Tuple,
    candidate_source: MeasurementSource,
    existing_identity: Tuple,
    existing_pair: Tuple,
    existing_source: MeasurementSource,
) -> bool:
    """does_override, for a caller holding identities rather than Measures.

    The viewer reads measurements out of a file as plain dictionaries and never
    builds a Measure from them, so the rule lives here where both can reach it.
    """
    if _SOURCE_RANK[candidate_source] <= _SOURCE_RANK[existing_source]:
        return False
    if candidate_source is MeasurementSource.FILE_OVERRIDE:
        return candidate_identity == existing_identity
    return candidate_pair == existing_pair


# ============================================================================
# Viewports: what a drawing shows, and how it divides the sheet
# ============================================================================


class SplitDirection(Enum):
    """Which way a subdivision divides, and so which way its portions run."""

    #: Portions stacked top to bottom, each the full width.
    ROWS = "rows"
    #: Portions side by side left to right, each the full height.
    COLUMNS = "columns"


@dataclass(frozen=True)
class Share:
    """A share of whatever the fixed-size siblings leave over.

    Two shares of 1 split what is left in half; a 2 and a 1 split it two to
    one. What a drawing means by "these four rows are equal", without caring
    how tall the sheet is.
    """

    value: Numeric = 1

    def __post_init__(self):
        if not (self.value > 0):
            raise ValueError(f"A share is positive, got {self.value}")


@dataclass(frozen=True)
class Length:
    """A size in page units. What a title block wants: 40mm, whatever the sheet.

    Wrapped rather than left as a bare number so that it cannot be mistaken for
    a Share. `Portion(view, 0.5)` reading as half a metre when half the room was
    meant is the kind of thing a unit only catches once it is on paper.
    """

    value: Numeric

    def __post_init__(self):
        if not (self.value > 0):
            raise ValueError(f"A length is positive, got {self.value}")


#: How much of a subdivision one portion takes.
Size = Union[Share, Length]

#: Where a floating viewport sits, as [x, y, width, height], each a fraction of
#: the page, origin top left. The form the viewer has always taken.
Rect = Tuple[float, float, float, float]


@dataclass(frozen=True)
class Page:
    """The sheet, in real units. What a Length is measured against."""

    width: Numeric
    height: Numeric

    def __post_init__(self):
        if not (self.width > 0 and self.height > 0):
            raise ValueError(f"A page has a positive size, got {self.width} x {self.height}")


@dataclass(frozen=True)
class Portion:
    """One child of a subdivision, and how much of the cell it takes.

    The size lives here rather than on the Viewport because it is a fact about
    the ARRANGEMENT, not about the view. "Half of this row" means nothing until
    there is a row, and a viewport does not know it is in one -- see Viewport.
    Keeping it here is also what lets a viewport be moved without carrying a
    proportion that belonged somewhere else.

    Held as its own type rather than a second tuple of sizes beside the
    children: two lists that must stay the same length and the same order are
    two lists that come apart, and at four children you are counting positions
    across both to see which size goes with which view.
    """

    viewport: 'Viewport'
    size: Size = field(default_factory=Share)


@dataclass(frozen=True)
class Subdivision:
    """How one viewport divides itself between the viewports inside it.

    Rows run top to bottom and columns left to right, which is both the order
    the portions are written in and the order their ids are numbered in.
    """

    direction: SplitDirection
    portions: Sequence[Portion]
    #: Space between portions, in page units. Not before the first or after the
    #: last -- that is what a viewport's own padding is for, and the two
    #: compose.
    gap: Numeric = 0

    def __post_init__(self):
        object.__setattr__(self, 'portions', tuple(self.portions))
        if not self.portions:
            raise ValueError("A subdivision divides a cell between portions, and has none")

    def taking(self, size: 'Size') -> 'Portion':
        """This subdivision, in a viewport of its own, as a portion of that size.

        The counterpart of Viewport.taking, so that a nested division can say
        how much room it takes without the wrapper having to be written out:
        `columns(rows(a, b).taking(Share(2)), c)`.
        """
        return Portion(viewport=Viewport(subdivision=self), size=size)


@dataclass(frozen=True, eq=False)
class Viewport:
    """One view on a sheet, and the views inside it.

    Knows what it is called, how much room it leaves inside itself, and what it
    contains. Does NOT know where it sits: not its rect, not its id, not its
    parent. Those are facts about the tree rather than about the viewport, and
    they are the drawing's to answer -- see Drawing.walk and Drawing.id_of.

    `subdivision` is None for a leaf, which is the only kind that gets a camera
    and becomes a viewport on screen; one with portions is a container, and the
    views inside it fill its cell. The three things a division needs --
    direction, portions, gap -- are grouped into Subdivision rather than sitting
    here as three optionals, so that "a direction but nothing to divide" cannot
    be written down.

    `rect` and `z` place a FLOATING viewport on the page and are meaningless on
    one inside a subdivision, which is placed by its portion's size instead.
    Which of the two this is, is again not something a viewport knows, so
    Drawing checks it.

    COMPARED BY IDENTITY, not by value. Two viewports with the same label are
    different viewports -- the whole point of ids being positional is that what
    a view IS, to a drawing, is the cell it occupies. Value equality would make
    id_of ambiguous between them, and comparing viewports by value is not a
    thing anyone wants: it would be asking whether two cells of a sheet happen
    to be described alike.
    """

    label: Optional[str] = None
    #: Blank space inside this viewport's own cell, in page units, on every
    #: side. On the Viewport rather than the Portion because it is true of the
    #: viewport alone -- "leave a margin inside me" needs no siblings to mean
    #: something.
    padding: Numeric = 0
    subdivision: Optional[Subdivision] = None
    #: The dimensions drawn in this viewport. On the viewport rather than
    #: keyed by id somewhere else, so that writing one takes no counting: a
    #: measurement belongs to the view it is drawn in, and here it can say so
    #: by being there. Only a leaf renders, so only a leaf's are drawn.
    measurements: Sequence['Measure'] = ()
    #: Floating placement. Roots have these; the views inside a subdivision
    #: must not.
    rect: Optional[Rect] = None
    #: Which is in front where two floating viewports overlap. Higher is nearer
    #: the reader.
    z: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'measurements', tuple(self.measurements))
        if self.rect is not None:
            rect = tuple(float(value) for value in self.rect)
            if len(rect) != 4:
                raise ValueError(f"A rect is [x, y, width, height], got {self.rect!r}")
            x, y, width, height = rect
            if width <= 0 or height <= 0:
                raise ValueError(f"A floating viewport has a positive size, got {width} x {height}")
            # Checked rather than clamped. The viewer clamps a rect into [0, 1]
            # without a word, so one placed half off the sheet quietly became a
            # different rect; saying so here is the difference between a layout
            # being wrong and being wrong in silence.
            if x < 0 or y < 0 or x + width > 1 or y + height > 1:
                raise ValueError(
                    f"A floating viewport sits on the page: {rect} runs off it. A rect is "
                    f"fractions of the page, [x, y, width, height] from the top left."
                )
            object.__setattr__(self, 'rect', rect)

    @property
    def is_leaf(self) -> bool:
        """True if this is a view rather than a container: it gets a camera."""
        return self.subdivision is None

    @property
    def children(self) -> Tuple['Viewport', ...]:
        """The viewports inside this one, in order. Empty for a leaf."""
        if self.subdivision is None:
            return ()
        return tuple(portion.viewport for portion in self.subdivision.portions)

    def taking(self, size: Size) -> Portion:
        """This viewport, as a portion of that size. `plan.taking(Share(2))`.

        Sugar for Portion(self, size). It stores nothing here -- a viewport
        still does not know how big it is in an arrangement it is not aware of
        -- it is a shorter way to write the pair down.
        """
        return Portion(viewport=self, size=size)


def rows(*children: Union[Viewport, 'Subdivision', Portion], gap: Numeric = 0) -> Subdivision:
    """A subdivision stacking its children top to bottom.

    A bare Viewport takes an equal share, which is the common case and should
    read as one; a Portion says how much it takes instead.
    """
    return Subdivision(direction=SplitDirection.ROWS, gap=gap,
                       portions=tuple(_as_portion(child) for child in children))


def columns(*children: Union[Viewport, 'Subdivision', Portion], gap: Numeric = 0) -> Subdivision:
    """A subdivision setting its children side by side, left to right."""
    return Subdivision(direction=SplitDirection.COLUMNS, gap=gap,
                       portions=tuple(_as_portion(child) for child in children))


def _as_portion(child: Union[Viewport, 'Subdivision', Portion]) -> Portion:
    """Whatever was written in a row or column, as the portion it means.

    A Subdivision is wrapped in a Viewport of its own, so that `columns(rows(a,
    b), c)` reads like the shape it makes. That wrapper is a real node with a
    real id -- a container is a viewport that happens to hold others -- it just
    has nothing to say about itself, so it carries no label.
    """
    if isinstance(child, Portion):
        return child
    if isinstance(child, Subdivision):
        return Portion(viewport=Viewport(subdivision=child))
    return Portion(viewport=child)


def covering_page(subdivision_or_viewport: Union[Viewport, Subdivision],
                  **options) -> Viewport:
    """A floating viewport over the whole sheet. The common case by far."""
    if isinstance(subdivision_or_viewport, Subdivision):
        return Viewport(rect=(0.0, 0.0, 1.0, 1.0), subdivision=subdivision_or_viewport,
                        **options)
    return replace(subdivision_or_viewport, rect=(0.0, 0.0, 1.0, 1.0), **options)


# ---------------------------------------------------------------------------
# The layouts a drawing gets when it does not name one
# ---------------------------------------------------------------------------
#
# Here rather than in kigumi/runner.py because they are what a DRAWING is,
# not what a viewer does with one -- and because Drawing reaches for them
# itself when it is given no viewports of its own.
#
# The ids are spelled out beside each. They are positional, so they follow
# from the shape and nothing else; writing them down is what lets code find a
# view by what it is for without reading a label, and what makes a change to
# either shape fail a test rather than move someone's measurements in silence.


def shop_drawing_viewports() -> Tuple[Viewport, ...]:
    """One piece's four long faces down the left, a preview beside them.

    How a piece is drawn for the shop: every long side rolled out, square on,
    with a live view of the whole thing to read them against.
    """
    return (covering_page(columns(
        rows(Viewport(label="Front"), Viewport(label="Right"),
             Viewport(label="Back"), Viewport(label="Left")),
        Viewport(label="Preview"),
    )),)


SHOP_DRAWING_IDS: Mapping[str, ViewportId] = {
    "front": ViewportId("0.0.0"),
    "right": ViewportId("0.0.1"),
    "back": ViewportId("0.0.2"),
    "left": ViewportId("0.0.3"),
    "preview": ViewportId("0.1"),
}


def elevation_viewports() -> Tuple[Viewport, ...]:
    """Three world elevations and a preview, a quadrant each.

    For several pieces at once, which have no single piece whose faces the
    sheet could be about. Two rows of two columns rather than four rects: the
    rows are what make the elevations line up across the sheet.
    """
    return (covering_page(rows(
        columns(Viewport(label="Front"), Viewport(label="Top")),
        columns(Viewport(label="Right"), Viewport(label="Preview")),
    )),)


ELEVATION_IDS: Mapping[str, ViewportId] = {
    "front": ViewportId("0.0.0"),
    "top": ViewportId("0.0.1"),
    "right": ViewportId("0.1.0"),
    "preview": ViewportId("0.1.1"),
}


def default_viewports_for(timber_count: int) -> Tuple[Viewport, ...]:
    """The viewports a drawing gets when it names timbers and no layout.

    One piece is drawn as a shop drawing of that piece. Several have no single
    piece whose faces the sheet could be about, so they get world elevations.
    """
    return shop_drawing_viewports() if timber_count == 1 else elevation_viewports()


@dataclass(frozen=True)
class Drawing:
    """A drawing the frame asks for: a name, and which timbers it is of.

    Timbers are named by path, the same name they carry everywhere else, and by
    path alone -- which of two timbers sharing a path is not a question a name
    can answer, and a drawing of "the front left post" should not have to know
    whether one was made twice. A path naming no timber is not an error either:
    a drawing of a timber a later edit removed is worth keeping and showing as
    empty, rather than failing to raise the frame it belongs to.

    `drawing_id` is what an override in the drawings file names, so it has to
    survive editing the code around it. It defaults to the name, which is stable
    as long as the name is.
    """

    name: str
    #: Held as a tuple; any sequence may be given. The ELEMENTS are exact --
    #: a TimberPath, not a string that looks like one. Wrapping a path is what
    #: stops it being passed where a drawing's name was meant, and taking a
    #: bare string here would give that away at the one moment it helps.
    timber_paths: Sequence[TimberPath] = ()
    drawing_id: Optional[DrawingId] = None
    #: The floating viewports of this sheet, in the order they were written.
    #: That order is what numbers them -- see walk -- so it is part of what the
    #: drawing means. It is not the drawing order; z is.
    viewports: Sequence[Viewport] = ()
    #: The sheet these sit on. A Length anywhere in the tree is measured
    #: against it.
    page: Optional[Page] = None
    #: Dimensions named by the id of the view they are drawn in -- a position,
    #: "0.0.1" being the second row of the first column of the first floating
    #: viewport.
    #:
    #: For a drawing that took the default layout: it has viewports like any
    #: other, but they were made for it, so there is no object in hand to put a
    #: measurement on and an id is the only way to say which view is meant.
    #: A drawing that writes its own viewports should put the measurement on
    #: the viewport instead, where no counting is involved and moving the view
    #: takes the dimension with it.
    #:
    #: Either way the runner reads measurements_by_viewport(), which is the two
    #: together.
    measurements: Mapping[ViewportId, Sequence[Measure]] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, 'timber_paths', tuple(
            TimberPath(path) if isinstance(path, str) else path
            for path in (self.timber_paths or ())
        ))
        if not self.drawing_id:
            object.__setattr__(self, 'drawing_id', DrawingId(self.name))
        elif isinstance(self.drawing_id, str):
            object.__setattr__(self, 'drawing_id', DrawingId(self.drawing_id))
        object.__setattr__(self, 'measurements', {
            viewport: tuple(measures)
            for viewport, measures in dict(self.measurements or {}).items()
        })
        # A drawing always has viewports. One that names only its timbers gets
        # the default layout for what it draws, made here and held like any
        # other -- so there is no second kind of drawing whose views exist only
        # once something else has laid it out.
        viewports = tuple(self.viewports) or default_viewports_for(len(self.timber_paths))
        object.__setattr__(self, 'viewports', viewports)
        self._check_placement()
        self._check_each_viewport_appears_once()

    # ---------------------------------------------------------------- the tree

    def walk(self) -> Iterator[Tuple[ViewportId, 'Viewport']]:
        """Every viewport of this drawing, with the id its position gives it.

        Depth first and in written order, so a parent comes before the views
        inside it. An id is the index of its floating viewport, then the index
        of each portion stepped through to reach it, joined with dots: the
        second row of the first column of the first floating viewport is
        "0.0.1", and an undivided floating viewport is just "2".

        Containers are included. A caller wanting only the views that get a
        camera wants `leaves`.
        """
        def descend(viewport: 'Viewport', path: Tuple[int, ...]):
            yield (ViewportId(".".join(str(step) for step in path)), viewport)
            for index, child in enumerate(viewport.children):
                yield from descend(child, path + (index,))

        for index, root in enumerate(self.viewports):
            yield from descend(root, (index,))

    def measurements_by_viewport(self) -> Dict[str, Tuple[Measure, ...]]:
        """Every dimension of this drawing, under the id of the view it is in.

        The two ways of saying it, merged: the ones written on a viewport, and
        the ones keyed by id for viewports the drawing did not build. A viewport
        that has both gets both, its own first.
        """
        collected: Dict[str, Tuple[Measure, ...]] = {}
        for viewport_id, viewport in self.walk():
            if viewport.measurements:
                collected[str(viewport_id)] = tuple(viewport.measurements)
        for viewport_id, measures in self.measurements.items():
            key = str(viewport_id)
            collected[key] = collected.get(key, ()) + tuple(measures)
        return collected

    def leaves(self) -> Iterator[Tuple[ViewportId, 'Viewport']]:
        """Every viewport that gets a camera, with its id. What renders."""
        return ((id, viewport) for id, viewport in self.walk() if viewport.is_leaf)

    def id_of(self, viewport: 'Viewport') -> ViewportId:
        """Where this viewport sits, which is what identifies it.

        By identity rather than by value -- see the note on Viewport -- so the
        viewport asked about must be one of THIS drawing's, not one that merely
        looks like it.
        """
        for found, candidate in self.walk():
            if candidate is viewport:
                return found
        raise KeyError(f"{viewport!r} is not a viewport of drawing {self.drawing_id}")

    def viewport_at(self, viewport_id: ViewportId) -> Optional['Viewport']:
        """The viewport at an id, or None. The other direction from id_of."""
        wanted = str(viewport_id)
        for found, viewport in self.walk():
            if str(found) == wanted:
                return viewport
        return None

    # ------------------------------------------------------------- the checks

    def _check_placement(self) -> None:
        """A root floats; a view inside a subdivision does not.

        Checked here because a viewport cannot check it: which of the two it is
        depends on where it sits, and not knowing that is the whole design.
        """
        for index, root in enumerate(self.viewports):
            if root.rect is None:
                raise ValueError(
                    f"Viewport {index} of drawing {self.drawing_id} floats on the page "
                    f"and needs a rect. Only the views inside a subdivision are placed "
                    f"by their portion's size."
                )
        for viewport_id, viewport in self.walk():
            if "." in str(viewport_id) and viewport.rect is not None:
                raise ValueError(
                    f"Viewport {viewport_id} of drawing {self.drawing_id} is inside a "
                    f"subdivision, so its cell comes from its portion's size. A rect "
                    f"here would say two different things about where it goes."
                )

    def _check_each_viewport_appears_once(self) -> None:
        """No viewport twice in one drawing.

        A viewport is identified by where it is, so one object in two places has
        two ids and id_of could only guess. Reusing an object is the easy way to
        write that by accident -- `v = Viewport(...)` then `rows(v, v)` -- so it
        is refused rather than resolved arbitrarily.
        """
        seen = {}
        for viewport_id, viewport in self.walk():
            if id(viewport) in seen:
                raise ValueError(
                    f"The same viewport is at {seen[id(viewport)]} and {viewport_id} of "
                    f"drawing {self.drawing_id}. Viewports are told apart by where they "
                    f"are, so each position needs its own."
                )
            seen[id(viewport)] = viewport_id
