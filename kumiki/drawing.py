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

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Tuple

from .identity import DrawingId, FeaturePath, MeasurementId, TimberPath


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
    # the measurement kind to use or None to use the default
    kind: Optional[MeasurementKind] = None
    # the measurementId which allows multiple measurements with the same anchors and kind
    measure_id: Optional[MeasurementId] = None
    #: Where the dimension sits. Deliberately not part of identity: moving a
    #: dimension line is not measuring something else.
    placement: Optional[MeasurementPlacement] = None

    def __post_init__(self):
        if isinstance(self.measure_id, str):
            object.__setattr__(self, 'measure_id', MeasurementId(self.measure_id))
        if self.kind is not None and not isinstance(self.kind, MeasurementKind):
            # A name, or the structured form a file holds. An older name still
            # reads: see MeasurementKind.parse.
            object.__setattr__(self, 'kind', MeasurementKind.from_wire(self.kind))
        if isinstance(self.placement, dict):
            object.__setattr__(self, 'placement', MeasurementPlacement(**self.placement))

    def identity(self) -> Tuple[Tuple, Tuple, str]:
        """What makes this measurement itself, within its viewport.

        The anchors unordered, since measuring A to B is measuring B to A.
        """
        first, second = sorted((self.anchor_a.identity(), self.anchor_b.identity()))
        return (first, second, str(self.measure_id or ""))


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
    timber_paths: Tuple[TimberPath, ...] = ()
    drawing_id: Optional[DrawingId] = None
    # Dimensions the frame asks for, under the viewport each is drawn in --
    # 'front', 'top', 'left' and so on, the viewports the layout produces.
    # Written out by hand today; expected to be mostly generated by algorithm
    # later, which is what the identity rules on Measure are for.
    measurements: Mapping[str, Tuple[Measure, ...]] = field(default_factory=dict)

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
            str(viewport): tuple(measures)
            for viewport, measures in dict(self.measurements or {}).items()
        })
