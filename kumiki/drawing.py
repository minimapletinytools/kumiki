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

import math
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


#: How square something has to be to the view before it counts as square. An
#: edge a hair off end-on still projects to a line, just a very short one, and
#: calling it a point would refuse a dimension that is drawable.
ALIGNMENT_EPSILON = 1e-3

#: Two projected directions within this of parallel are treated as parallel: the
#: angle between them would be a number nobody wrote down deliberately, and
#: their separation is what was meant.
PARALLEL_EPSILON = 1e-2


def _unit(vector: Sequence[float]) -> Tuple[float, float, float]:
    size = math.sqrt(sum(float(part) * float(part) for part in vector))
    if size == 0:
        return (0.0, 0.0, 0.0)
    return tuple(float(part) / size for part in vector)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def projected_form(
    geometry: Optional[Mapping], look: Sequence[float],
) -> Tuple[MeasurementFeature, Optional[Tuple[float, float, float]]]:
    """What a feature behaves as once projected, and which way it runs.

    A point stays a point. An edge seen end-on becomes one, and otherwise stays
    a line. A face is a LINE seen edge-on and an AREA at any other angle -- and
    an area covers the view, which is the whole of what PROJECTS_TO means by a
    face having two answers.

    The direction comes back with it because a pair of lines admits different
    kinds depending on whether they are parallel, and the caller would otherwise
    have to work the projection out a second time to find out.

    None for `geometry` is a feature lying on no plane or line -- a cylinder's
    barrel, a lofted side -- which is good to select and cannot be measured to.

    THE VIEWER HAS A COPY OF THIS, in measurements.js, and a test runs the two
    against each other. Two copies of a rule is how a rule drifts; the reason
    for the second one is that the viewer projects on every pointer move and
    cannot ask python each time.
    """
    kind = (geometry or {}).get("kind")
    gaze = _unit(look)
    if kind == "point":
        return (MeasurementFeature.POINT, None)
    if kind == "line":
        direction = _unit(geometry.get("direction") or (0, 0, 0))
        if abs(_dot(direction, gaze)) > 1 - ALIGNMENT_EPSILON:
            return (MeasurementFeature.POINT, None)
        return (MeasurementFeature.LINE, _flatten(direction, gaze))
    if kind == "plane":
        normal = _unit(geometry.get("normal") or (0, 0, 0))
        if abs(_dot(normal, gaze)) > ALIGNMENT_EPSILON:
            # Not edge-on: it covers the view, and an area has no distance.
            return (MeasurementFeature.AREA, None)
        # Edge-on, so it draws as a line along the plane, square to its normal
        # and to the line of sight.
        return (MeasurementFeature.LINE, _cross(normal, gaze))
    return (None, None)


def _flatten(direction: Sequence[float], gaze: Sequence[float]) -> Tuple[float, float, float]:
    """The part of a direction that survives projection."""
    along = _dot(direction, gaze)
    return _unit([direction[i] - gaze[i] * along for i in range(3)])


def _cross(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float, float]:
    return _unit([
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ])


@dataclass(frozen=True)
class MeasureSpan:
    """What a feature is, where a measurement is being taken.

    Three shapes, and which ones can occur depends on the space:

    ON A SHEET, two. A point is a point; an edge is a line with an extent; and a
    FACE seen edge-on is also a line with an extent, while a face seen at any
    other angle covers the view and admits no measurement at all.

    IN THE SOLID, three. Nothing is projected away, so a face is a PLANE -- it
    is measurable from anywhere, not only edge-on, and it is not a line. Leaving
    it as a line there is what leaned a dimension between an edge and the face
    it runs parallel to: the anchors were placed by the two-lines rule, which
    shares a station along one direction, and a face has two directions to be
    square to rather than one.

    `interval` is how far it reaches along `direction`, as stations from `at`,
    taken from what the feature occupies once cropped to the timber. `normal` is
    set instead, for a plane. All three are None for a point.
    """

    at: Tuple[float, float, float]
    direction: Optional[Tuple[float, float, float]] = None
    interval: Optional[Tuple[float, float]] = None
    normal: Optional[Tuple[float, float, float]] = None
    #: For a LINE, the way out of the material across it -- an arris bisects the
    #: two faces that form it. Only used to decide which side an angle opens on,
    #: and absent whenever nothing could work it out.
    outward: Optional[Tuple[float, float, float]] = None

    @property
    def is_point(self) -> bool:
        return self.direction is None and self.normal is None

    @property
    def is_plane(self) -> bool:
        return self.normal is not None

    @property
    def is_line(self) -> bool:
        return self.direction is not None

    def ends(self) -> Tuple[Tuple[float, float, float], ...]:
        """The two extremities, or the point itself.

        A plane has no extremities along any one direction, so it answers with
        the one point it is placed at; the rules that ask this are the ones for
        lines.
        """
        if self.is_point or self.is_plane:
            return (self.at,)
        unit = _unit(self.direction)
        return tuple(
            tuple(self.at[i] + unit[i] * station for i in range(3))
            for station in (self.interval or (0.0, 0.0))
        )


def _stations(span: MeasureSpan, along: Sequence[float]) -> Tuple[float, float]:
    """How far a span reaches along a direction, as absolute stations.

    Absolute -- measured from the world origin rather than from the span's own
    point -- because two features have two different points, and overlap is a
    question about one shared ruler.
    """
    reach = [_dot(end, along) for end in span.ends()]
    return (min(reach), max(reach))


def _at_station(span: MeasureSpan, along: Sequence[float], station: float):
    """The point on a span that sits at a given station along `along`."""
    if span.is_point:
        return span.at
    unit = _unit(span.direction)
    rate = _dot(unit, along)
    if abs(rate) < 1e-12:
        return span.at
    step = (station - _dot(span.at, along)) / rate
    return tuple(span.at[i] + unit[i] * step for i in range(3))


def _foot_on(span: MeasureSpan, point: Sequence[float]):
    """Where a perpendicular from `point` meets a span, kept on the span."""
    unit = _unit(span.direction)
    station = _dot([point[i] - span.at[i] for i in range(3)], unit)
    low, high = span.interval or (station, station)
    # Clamped: a dimension whose end floats off the end of a short edge points
    # at nothing, and the nearest place on the feature is the honest answer.
    station = max(low, min(high, station))
    return tuple(span.at[i] + unit[i] * station for i in range(3))


def _representative_point(span: MeasureSpan) -> Tuple[float, float, float]:
    """The one point that stands for a span when something must be dropped onto it.

    A point is itself. A line offers the middle of its surviving extent, which is
    where a reader would put a finger on it.
    """
    if not span.is_line:
        return tuple(span.at)
    low, high = span.interval or (0.0, 0.0)
    unit = _unit(span.direction)
    middle = (low + high) / 2
    return tuple(span.at[i] + unit[i] * middle for i in range(3))


def _foot_on_plane(span: MeasureSpan, point: Sequence[float]):
    """Where a perpendicular from `point` meets a plane.

    NOT clamped to the face, unlike the foot on a line: a span carries a plane's
    normal and a point on it, not its outline, so there is nothing here to clamp
    against. For a pair that admits a distance the two features face each other,
    which is when the foot lands on the face anyway. Clamping properly wants the
    face's corners -- see the note in cutcsg about extents being an AABB.
    """
    unit = _unit(span.normal)
    gap = _dot([point[i] - span.at[i] for i in range(3)], unit)
    return tuple(point[i] - unit[i] * gap for i in range(3))


def _closest_on_line(point, at, direction):
    """Where a line comes nearest a point."""
    unit = _unit(direction)
    step = _dot([point[i] - at[i] for i in range(3)], unit)
    return tuple(at[i] + unit[i] * step for i in range(3))


def _plane_crossing(first: MeasureSpan, second: MeasureSpan):
    """The line two planes share: a point on it and its direction, or None.

    None when they are parallel, which has no corner to stand in -- and admits a
    distance rather than an angle anyway.
    """
    one, other = _unit(first.normal), _unit(second.normal)
    along = _cross(one, other)
    # The UNNORMALISED cross, because the closed form below divides by its
    # square length. Normalising first and dividing by one puts the point out by
    # a factor of the sine between the planes, which is right only when they
    # happen to meet square.
    scale = _dot(along, along)
    if scale < PARALLEL_EPSILON:
        return None
    reach_one, reach_other = _dot(one, first.at), _dot(other, second.at)
    part_one, part_other = _cross(other, along), _cross(along, one)
    point = tuple(
        (reach_one * part_one[i] + reach_other * part_other[i]) / scale
        for i in range(3))
    return point, _unit(along)


def _ray_toward(ray, vertex, span: MeasureSpan, other: Optional[MeasureSpan] = None):
    """A unit ray from `vertex`, turned to point at where the feature is.

    Which of the two supplementary angles is meant is decided here, and where
    the feature actually lies is usually what says it: a face reaches off to one
    side of the corner, and an arris runs away from it.

    An edge that STRADDLES the vertex reaches equally both ways and says
    nothing. The other feature's outward normal says it instead -- the way out
    of the material across it -- because the angle a reader means is the one
    with both timbers in it. Note it is the OTHER feature's: an edge's own
    normal is square to the edge, so it cannot choose a direction along it.
    """
    unit = _unit(ray)
    if not any(abs(part) > 1e-9 for part in unit):
        return None
    if span.is_line:
        stations = [_dot([end[i] - vertex[i] for i in range(3)], unit)
                    for end in span.ends()]
        low, high = min(stations), max(stations)
        straddles = low < -1e-9 < 1e-9 < high
        outward = other.outward if other is not None else None
        if straddles and outward is not None:
            lean = -_dot(unit, _unit(outward))
        else:
            # The longer side, which for an edge running off one way is that way.
            lean = high + low
    else:
        lean = _dot(unit, [span.at[i] - vertex[i] for i in range(3)])
    return tuple(-part for part in unit) if lean < 0 else unit


def angle_rays(first: MeasureSpan, second: MeasureSpan):
    """Where an angle between two features is, and which two ways it opens.

    A vertex and two unit rays from it, in world space, as
    `{"vertex", "from", "to"}` -- or None when the pair makes no corner.

    Worked out here rather than in the viewer for the same reason the anchors of
    a distance are: an angle drawn from one derivation and labelled from another
    will eventually disagree, and the disagreement is a picture that means
    nothing next to a number that is right.

    THE RAYS DECIDE THE VALUE. The angle a reader wants is the one the two
    features actually subtend -- the corner they make, not its supplement -- so
    it is read off the rays rather than from the features' normals, which cannot
    tell 45 degrees from 135.
    """
    if first is None or second is None:
        return None
    if first.is_plane and second.is_plane:
        crossing = _plane_crossing(first, second)
        if crossing is None:
            return None
        point, along = crossing
        middle = tuple((first.at[i] + second.at[i]) / 2 for i in range(3))
        vertex = _closest_on_line(middle, point, along)
        # Square to the shared corner, and lying in its own face.
        rays = (_ray_toward(_cross(along, _unit(first.normal)), vertex, first),
                _ray_toward(_cross(along, _unit(second.normal)), vertex, second))
    elif first.is_line and second.is_line:
        placed = _closest_between(first, second)
        if placed is None:
            return None
        vertex = placed
        rays = (_ray_toward(first.direction, vertex, first, second),
                _ray_toward(second.direction, vertex, second, first))
    elif first.is_line or second.is_line:
        line, plane = (first, second) if first.is_line else (second, first)
        vertex = _line_meets_plane(line, plane)
        if vertex is None:
            return None
        in_plane = _flatten_onto(line.direction, plane.normal)
        if in_plane is None:
            return None
        line_ray = _ray_toward(line.direction, vertex, line, plane)
        plane_ray = _ray_toward(in_plane, vertex, plane)
        rays = (line_ray, plane_ray) if first.is_line else (plane_ray, line_ray)
    else:
        return None
    if rays[0] is None or rays[1] is None:
        return None
    return {"vertex": list(vertex), "from": list(rays[0]), "to": list(rays[1])}


def _closest_between(first: MeasureSpan, second: MeasureSpan):
    """Where two lines come nearest each other, kept on both.

    Two edges in a frame are skew as often as they cross, so there is usually no
    single point on both. The midpoint of their nearest approach is the honest
    place to stand, and each station is clamped to what survives of its edge so
    the arc lands on the timber rather than out past the end of it.
    """
    one, other = _unit(first.direction), _unit(second.direction)
    facing = _dot(one, other)
    spread = 1 - facing * facing
    if spread < PARALLEL_EPSILON:
        return None
    gap = [first.at[i] - second.at[i] for i in range(3)]
    lean_one, lean_other = _dot(one, gap), _dot(other, gap)
    station_one = (facing * lean_other - lean_one) / spread
    station_other = (lean_other - facing * lean_one) / spread
    station_one = _clamp_to(station_one, first.interval)
    station_other = _clamp_to(station_other, second.interval)
    on_one = [first.at[i] + one[i] * station_one for i in range(3)]
    on_other = [second.at[i] + other[i] * station_other for i in range(3)]
    return tuple((on_one[i] + on_other[i]) / 2 for i in range(3))


def _clamp_to(station: float, interval):
    if interval is None:
        return station
    low, high = interval
    return max(low, min(high, station))


def _line_meets_plane(line: MeasureSpan, plane: MeasureSpan):
    """Where a line crosses a plane, or its nearest point when it runs flat."""
    unit, normal = _unit(line.direction), _unit(plane.normal)
    rate = _dot(unit, normal)
    if abs(rate) < PARALLEL_EPSILON:
        # Running along the face: it never crosses, so stand where the edge is
        # and drop that onto the face.
        return _foot_on_plane(plane, _representative_point(line))
    step = _dot([plane.at[i] - line.at[i] for i in range(3)], normal) / rate
    step = _clamp_to(step, line.interval)
    return tuple(line.at[i] + unit[i] * step for i in range(3))


def _flatten_onto(direction, normal):
    """The part of a direction that lies in a plane."""
    unit, up = _unit(direction), _unit(normal)
    along = _dot(unit, up)
    flat = [unit[i] - up[i] * along for i in range(3)]
    if not any(abs(part) > 1e-9 for part in flat):
        return None
    return _unit(flat)


def angle_between(rays) -> Optional[float]:
    """The angle the rays open, in degrees. The value a reader sees."""
    if not rays:
        return None
    facing = max(-1.0, min(1.0, _dot(_unit(rays["from"]), _unit(rays["to"]))))
    return math.degrees(math.acos(facing))


def distance_anchors(
    first: MeasureSpan,
    second: MeasureSpan,
    kind: MeasurementKind,
    axes: Optional[Mapping] = None,
):
    """Where a distance between these two features attaches, at both ends.

    A property of the PAIR and the plane, not of either feature alone. An anchor
    chosen per feature cannot know where the sensible attachment point is for a
    given pair -- two parallel edges each anchoring at their own midpoint gave a
    dimension that leaned if the midpoints were offset along their length.

    PERPENDICULAR, between two parallel lines: both ends sit at one station
    along the shared direction, which is what makes the line between them square
    to both. The station is the middle of the overlap of their extents, so the
    dimension lands where the two features actually face each other. Where they
    do not overlap there is no such place, so it goes to the end of the FIRST
    nearest the second, and the other end is projected across from there.

    PERPENDICULAR, a point and a line: the point does not move -- it is the
    whole of what is being measured from -- and the other end is the foot of the
    perpendicular dropped onto the line.

    PERPENDICULAR, anything and a PLANE: the same rule one step further. The
    anchor is chosen on whichever feature has less freedom -- a point has none,
    a line one direction, a plane two -- and dropped onto the other square to
    it. A face only IS a plane in the solid; on a sheet it is a line seen
    edge-on and takes the rules above.

    PERPENDICULAR, two points: themselves. With no line to be square to, the
    distance between them is the distance.

    HORIZONTAL or VERTICAL: the first end stays put and the second is projected
    onto the axis through it, so the dimension runs along the sheet's own
    direction and reads the separation in it. Offered only between two points
    today -- kinds_for lists no other pair for them -- so the two closest points
    on the two features are the two points.
    """
    named = kind.name if hasattr(kind, "name") else str(kind)

    if named in ("projected_horizontal_distance", "projected_vertical_distance"):
        axis = _unit((axes or {}).get(
            "right" if named.endswith("horizontal_distance") else "up") or (1, 0, 0))
        offset = _dot([second.at[i] - first.at[i] for i in range(3)], axis)
        return (first.at, tuple(first.at[i] + axis[i] * offset for i in range(3)))

    # A PLANE is measured to by dropping a perpendicular onto it. The anchor is
    # chosen on whichever feature has less freedom -- a point has none, a line
    # one direction, a plane two -- and carried to the other square to it. That
    # is what makes the dimension perpendicular to the face rather than merely
    # touching it: an edge and the face it runs parallel to were both treated as
    # lines and put through the shared-station rule, which shares ONE direction,
    # and the dimension leaned by however far the two were offset in the other.
    #
    # Only in the solid: on a sheet a face is a line and never gets here.
    if first.is_plane or second.is_plane:
        if first.is_plane and second.is_plane:
            # Parallel faces. Either centroid will do, and the first is the one
            # the reader chose first.
            return (first.at, _foot_on_plane(second, first.at))
        if first.is_plane:
            from_second = _representative_point(second)
            return (_foot_on_plane(first, from_second), from_second)
        from_first = _representative_point(first)
        return (from_first, _foot_on_plane(second, from_first))

    if first.is_point and second.is_point:
        return (first.at, second.at)
    if first.is_point:
        return (first.at, _foot_on(second, first.at))
    if second.is_point:
        return (_foot_on(first, second.at), second.at)

    along = _unit(first.direction)
    first_low, first_high = _stations(first, along)
    second_low, second_high = _stations(second, along)
    low, high = max(first_low, second_low), min(first_high, second_high)
    if low <= high:
        station = (low + high) / 2
    else:
        # Nothing faces anything: go to the end of the first that is nearest.
        station = first_high if first_high < second_low else first_low
    return (_at_station(first, along, station), _at_station(second, along, station))


def projected_kinds(
    one: Optional[Mapping], other: Optional[Mapping], look: Sequence[float],
) -> Tuple[MeasurementKind, ...]:
    """Which kinds this pair admits, seen from `look`. Empty when none.

    The two halves put together: project both, then ask the table. This is the
    question "could these two be measured against each other from here", which
    is what decides whether a feature is worth preferring under the pointer.
    """
    form_one, run_one = projected_form(one, look)
    form_other, run_other = projected_form(other, look)
    if form_one is None or form_other is None:
        return ()
    parallel = None
    if run_one is not None and run_other is not None:
        parallel = abs(_dot(run_one, run_other)) > 1 - PARALLEL_EPSILON
    return kinds_for(form_one, form_other, MeasurementSpace.PROJECTED, parallel=parallel)


def solid_form(
    geometry: Optional[Mapping],
) -> Tuple[Optional[MeasurementFeature], Optional[Tuple[float, float, float]]]:
    """What a feature IS, with nothing projected away.

    The 3D view's camera belongs to the reader and turns as they look around, so
    a feature there cannot be classified by how it happens to appear from where
    they are standing: a face is a plane whatever angle it is seen from. Asking
    `projected_form` there said a face was an AREA -- covering the view, nothing
    to measure -- for every face not seen exactly edge-on, which is nearly all
    of them.

    The direction that comes back is the line's own, or the plane's normal, for
    deciding whether a pair runs together.

    THE VIEWER HAS A COPY OF THIS, in measurements.js, and a test runs the two
    against each other.
    """
    kind = (geometry or {}).get("kind")
    if kind == "point":
        return (MeasurementFeature.POINT, None)
    if kind == "line":
        return (MeasurementFeature.LINE, _unit(geometry.get("direction") or (0, 0, 0)))
    if kind == "plane":
        return (MeasurementFeature.PLANE, _unit(geometry.get("normal") or (0, 0, 0)))
    return (None, None)


def _solid_parallel(
    form_one: MeasurementFeature,
    run_one: Optional[Sequence[float]],
    form_other: MeasurementFeature,
    run_other: Optional[Sequence[float]],
) -> Optional[bool]:
    """Whether two solid features run together.

    Two planes are parallel when their NORMALS align and two lines when their
    DIRECTIONS do -- but a line is parallel to a plane when it runs square to
    the normal, which is the opposite test. One of these carries a normal and
    the other a direction, so comparing them as though both were directions
    would have called a line lying in a plane a crossing.
    """
    if run_one is None or run_other is None:
        return None
    alignment = abs(_dot(run_one, run_other))
    if form_one is form_other:
        return alignment > 1 - PARALLEL_EPSILON
    return alignment < PARALLEL_EPSILON


def solid_kinds(
    one: Optional[Mapping], other: Optional[Mapping],
) -> Tuple[MeasurementKind, ...]:
    """Which kinds this pair admits in the 3D view. Empty when none.

    The counterpart of `projected_kinds` for a view that projects nothing. No
    camera comes into it: what a pair admits in the solid does not depend on
    where anyone is standing.
    """
    form_one, run_one = solid_form(one)
    form_other, run_other = solid_form(other)
    if form_one is None or form_other is None:
        return ()
    return kinds_for(
        form_one, form_other, MeasurementSpace.THREE_D,
        parallel=_solid_parallel(form_one, run_one, form_other, run_other),
    )


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
class MeasurementPlane:
    """The flat surface a measurement is taken and drawn on.

    The measurement's own property, not the viewport's. A drawing viewport is
    locked, so a measurement in one could be evaluated against the viewport and
    get a stable answer; the 3D view's camera is not, and the same two faces
    would read a different number from one moment to the next as it orbits.
    Carrying the plane makes the number the measurement's, and leaves the
    viewport deciding only how it is drawn.

    Floats rather than exact scalars, like Rect and for the same reason: this is
    where a dimension is drawn, not where a joint is cut.

    Its own dataclass rather than a bare pair because it will grow. A plane that
    tracks a feature -- so that moving the timber moves the dimension with it --
    is the obvious next form, and a pair of vectors leaves nowhere to say which
    kind of plane this is.

    None on a Measure means "derive it from the viewport", which is what every
    measurement written before this means, and all an orthographic viewport's
    measurements are entitled to mean.
    """

    #: A point on the plane, in world space.
    at: Tuple[float, float, float]
    #: The plane's normal, in world space. Not required to be unit length on the
    #: way in; compared up to sign, since a plane has no front.
    normal: Tuple[float, float, float]

    def __post_init__(self):
        for name in ("at", "normal"):
            value = tuple(float(part) for part in getattr(self, name))
            if len(value) != 3:
                raise ValueError(f"A plane's {name} is [x, y, z], got {getattr(self, name)!r}")
            object.__setattr__(self, name, value)
        if not any(self.normal):
            raise ValueError("A plane's normal cannot be zero length")

    @classmethod
    def from_wire(cls, value) -> Optional['MeasurementPlane']:
        """A plane as read from a file, or one already built.

        The same shape as MeasurementKind.from_wire and MeasurementPlacement's,
        and for the same reason: the field holds a MeasurementPlane, and saying
        so is only true if the conversion from the file's form happens somewhere
        that takes the file's form as its argument type.
        """
        if value is None or isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(at=value.get("at"), normal=value.get("normal"))
        raise TypeError(f"Expected a plane or a mapping, got {type(value).__name__}")

    def as_wire(self) -> Dict[str, list]:
        return {"at": list(self.at), "normal": list(self.normal)}


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

    #: How far the dimension line sits from the features, in WORLD units,
    #: measured along the in-plane perpendicular to the run.
    #:
    #: World rather than page or screen, so that where somebody put a dimension
    #: does not depend on how far they were zoomed in at the time, and so that
    #: it means the same thing in a drawing viewport and in the 3D view. What
    #: zoom changes is how big the drawing is, not where on it a dimension was
    #: placed. Only the drawn SIZE of things -- line weights, text -- is in
    #: pixels, so that it stays legible at any scale.
    #:
    #: None asks the viewport for its own default, which IS a pixel distance:
    #: there is nothing in the world to derive one from, and an untouched
    #: dimension sitting a readable distance away at any zoom is the better
    #: default.
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
    #: The plane this is taken and drawn on, or None to take the viewport's.
    #: Not part of identity either: the same two features measured on a
    #: different plane is the same measurement seen from elsewhere, and giving
    #: it a second identity would let a file hold both and draw them twice.
    plane: Optional[MeasurementPlane] = None

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
