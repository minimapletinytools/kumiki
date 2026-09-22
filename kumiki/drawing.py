"""Drawings: what a sheet shows, and the dimensions on it.

Two halves. The LAYOUT half -- Drawing, Viewport, Subdivision and the sizes --
is about where things sit on a page. The MEASURING half is about what a pair of
features can be measured as and what the measurement comes to, and the viewer
keeps a copy of some of it in kigumi/webview/measurements.js; the docstrings
below say which, and a test runs the two against each other.

Vectors here are rule.py's V3, as everywhere else in the library. The types a
measurement arrives as off the wire -- lists and tuples out of JSON -- are taken
at the edge and converted once; see VectorLike.

See docs/measurement-spec.md, and docs/drawing-rule-migration.md for what is
still to do.
"""

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union

from .geometry import Line, Plane, Point, intersect_planes
from .identity import (DrawingId, FeaturePath, MeasurementId, TimberPath,
                       ViewportId, identity_order)
from .rule import (Matrix, Numeric, V3, are_vectors_parallel,
                   are_vectors_perpendicular, create_v3, cross_product,
                   safe_dot_product, safe_norm, safe_zero_test_sq)


class MeasurementSpace(Enum):
    """Whether a measurement is taken in the projected viewport or in 3d space
    """
    PROJECTED = "projected"
    THREE_D = "3d"


class MeasurementOperation(Enum):
    DISTANCE = "distance"
    ANGLE = "angle"


class MeasurementDirection(Enum):
    """Which direction a distance is taken along.

    TODO clarify comments on how these are interpreted
    """

    PERPENDICULAR = "perpendicular"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class MeasurementFeature(Enum):
    """What a feature behaves as (after projection), for the purpose of measuring it.
    """

    POINT = "point"
    LINE = "line"
    #: 3D only. A face, before projection.
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
                "projected. Space itself has no up."
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
        return {
            "operation": self.operation.value,
            "space": self.space.value,
            "direction": self.direction.value,
        }

    @classmethod
    def from_wire(cls, value) -> Optional['MeasurementKind']:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return cls(
                MeasurementOperation(value.get("operation", "distance")),
                MeasurementSpace(value.get("space", "projected")),
                MeasurementDirection(value.get("direction", "perpendicular")),
            )
        return cls.parse(str(value))

    # TODO why do we need as/from_wire when we have parse and name?
    @classmethod
    def parse(cls, text: str) -> 'MeasurementKind':
        """Read a kind back from its name, or from one of the older names.

        # TODO remove these comments after removing legacy path
        The old names were all projected, and `aligned` and `perpendicular` both
        become a perpendicular distance: between two points the shortest
        distance IS the distance, which is why the two collapsed into one.

        Where an old name and a new one collide -- `angle`, which now composes
        for a 3D angle -- the old reading wins, because every file that
        contains the word was written meaning the old one. Solid kinds are
        written structured (see as_wire), so nothing needs the ambiguous form.
        """
        # TODO no need to suport legacy path, just delete it
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


def _three_d(operation) -> MeasurementKind:
    return MeasurementKind(operation, MeasurementSpace.THREE_D)


# TODO DELETE
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


# TODO refine these 3 epsilons below? alginment and parallel seem especially big?

#: How square something has to be to the view before it counts as square. An
#: edge a hair off end-on still projects to a line, just a very short one, and
#: calling it a point would refuse a dimension that is drawable.
#: Below this, in world units, two features are in the same place and there is
#: nothing between them to dimension. A measurement that comes to zero draws as
#: nothing, which reads as a measurement that failed rather than one that was
#: never worth making -- so a pair this close is refused at the pick instead.
#:
#: THE VIEWER HAS A COPY, as DEGENERATE_WORLD in measurements.js, for judging a
#: measurement already written. A test runs the two against each other.
DEGENERATE_SEPARATION = 1e-6

ALIGNMENT_EPSILON = 1e-3

#: Two projected directions within this of parallel are treated as parallel: the
#: angle between them would be a number nobody wrote down deliberately, and
#: their separation is what was meant.
#:
#: It is read two ways, and the difference matters. `kinds_for` asks it of a
#: COSINE, through are_vectors_parallel, and so calls a pair parallel below
#: about 8.1 degrees -- that is the drafting rule, and it decides whether a pair
#: is offered an angle at all. The three rules that place a corner ask it of a
#: SINE, and refuse below about 0.57 degrees -- that is a conditioning guard,
#: standing behind the first for a pair that somehow reaches them anyway.
#:
#: The order is what keeps them from arguing: the corner guards must refuse a
#: NARROWER band than the drafting rule, or a pair could be offered an angle and
#: then be unable to say where its vertex is. A test pins that.
PARALLEL_EPSILON = 1e-2


#: Anything that stands for a vector in here: a V3 already, or the lists and
#: tuples a measurement arrives as off the wire. The helpers below take this so
#: that a caller holding either does not have to say which.
VectorLike = Union[V3, Sequence[float]]


def _v3(vector: VectorLike) -> V3:
    """Whatever arrived off the wire, as a vector. Lists, tuples and V3 alike."""
    return vector if isinstance(vector, Matrix) else create_v3(*(float(p) for p in vector))


def _unit(vector: VectorLike) -> V3:
    """A unit vector, or a ZERO one where there is no direction to find.

    Zero rather than the input, which is what safe_normalize_vector gives back:
    four callers here test the result for zero to mean "no direction", and the
    viewer's `normalized` returns [0, 0, 0] too (measurements.js). Returning the
    input unchanged would make a zero direction look like a unit one.
    """
    found = _v3(vector)
    size = safe_norm(found)
    return found / size if size else create_v3(0, 0, 0)


def _dot(a: VectorLike, b: VectorLike) -> float:
    return safe_dot_product(_v3(a), _v3(b))


#: What a feature IS: unbounded, in world space, and one of three shapes. The
#: same primitives the CSG layer locates features as -- see kumiki.geometry --
#: rather than a mapping with a "kind" string, which was a sum type spelled out
#: by hand and left every function here unable to say what it took.
#:
#: The wire still carries the mapping form, because the viewer reads it; turning
#: one into the other happens once, at that edge, in kigumi/runner.py.
Geometry = Union[Point, Line, Plane]


def _anchor_of(geometry: Optional[Geometry]) -> Optional[V3]:
    """Where a feature sits.

    A point IS its position. A line and a plane pass through many points and
    carry one of them, which is as good as any for measuring the gap to
    something else: what a distance comes to is squared up to whichever of the
    pair constrains it, so which point was kept does not change the answer.
    """
    if isinstance(geometry, Point):
        return geometry.position
    if isinstance(geometry, (Line, Plane)):
        return geometry.point
    return None


# TODO rename look to normal probably
def projected_form(
    geometry: Optional[Geometry], look: VectorLike,
) -> Tuple[Optional[MeasurementFeature], Optional[V3]]:
    """What a feature behaves as once projected, and which way it runs.

    A point stays a point. An edge seen end-on becomes one, and otherwise stays
    a line. A face is a LINE seen edge-on and an AREA at any other angle -- and
    an area covers the view, which is the whole of what PROJECTS_TO means by a
    face having two answers.

    TODO what is this? it's just the normal (look) component of the un projected line, a little awkward to return it here sinec it only applies to lines.. is there a better way to do this?
    TODO update comment to simply say this is the direction of the line in the plane defined by look
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
    gaze = _unit(look)
    if isinstance(geometry, Point):
        return (MeasurementFeature.POINT, None)
    if isinstance(geometry, Line):
        direction = _unit(geometry.direction)
        if are_vectors_parallel(direction, gaze, eps=ALIGNMENT_EPSILON):
            return (MeasurementFeature.POINT, None)
        return (MeasurementFeature.LINE, _flatten(direction, gaze))
    if isinstance(geometry, Plane):
        normal = _unit(geometry.normal)
        if not are_vectors_perpendicular(normal, gaze, eps=ALIGNMENT_EPSILON):
            # Not edge-on: it covers the view, and an area has no distance.
            return (MeasurementFeature.AREA, None)
        # Edge-on, so it draws as a line along the plane, square to its normal
        # and to the line of sight.
        return (MeasurementFeature.LINE, _cross(normal, gaze))
    return (None, None)


def _flatten(direction: VectorLike, gaze: VectorLike) -> V3:
    """The part of a direction that survives projection."""
    direction, gaze = _v3(direction), _v3(gaze)
    return _unit(direction - gaze * _dot(direction, gaze))


def _raw_cross(a: VectorLike, b: VectorLike) -> V3:
    """The cross product at its own length, which is what magnitude tests want."""
    return cross_product(_v3(a), _v3(b))


def _cross(a: VectorLike, b: VectorLike) -> V3:
    """The cross product as a DIRECTION, so length is thrown away.

    Only for callers that want an axis. Anything dividing by the length, or
    testing it for degeneracy, wants _raw_cross: this one answers a unit vector
    for two barely-crossing inputs just as readily as for two square ones.
    """
    return _unit(_raw_cross(a, b))


# TODO can/should we split this into different classes for each feature type so we don't need to make as many runtime assumption checks?
@dataclass(frozen=True)
class MeasureSpan:
    """What a feature is, where a measurement is being taken.

    Three shapes, and which ones can occur depends on the space:

    ON A SHEET. point and edge only. faces projecting to areas are not measurable features.

    IN 3D. all supported.

    `interval` is measured from `at` in `direction` marking the feature cropped to its parent.
    """

    at: V3
    direction: Optional[V3] = None
    interval: Optional[Tuple[float, float]] = None
    normal: Optional[V3] = None
    # optional roughly outward direction of the body of the fetaure being measured. Only used to decide which side an angle opens on.
    outward: Optional[V3] = None

    def __post_init__(self):
        """Take a span however it is written, and hold it as vectors.

        Callers build these from whatever they have -- a tuple off the wire, a
        list from a cropped boundary -- and should not each have to convert.
        """
        for name in ("at", "direction", "normal", "outward"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Matrix):
                object.__setattr__(self, name, _v3(value))
        if self.interval is not None:
            object.__setattr__(
                self, 'interval', tuple(float(end) for end in self.interval))

    @property
    def is_point(self) -> bool:
        return self.direction is None and self.normal is None

    @property
    def is_plane(self) -> bool:
        return self.normal is not None

    @property
    def is_line(self) -> bool:
        return self.direction is not None

    @property
    def along(self) -> V3:
        """Which way this line runs, unit length. Ask only a line.

        Here so that the rules for lines can say `span.along` and mean it: the
        field is optional because a point has no direction, and every one of
        those rules has already established it is not looking at a point.
        """
        if self.direction is None:
            raise ValueError(f"{self!r} has no direction: only a line runs a way")
        return _unit(self.direction)

    @property
    def facing(self) -> V3:
        """Which way this plane faces, unit length. Ask only a plane."""
        if self.normal is None:
            raise ValueError(f"{self!r} has no normal: only a plane faces a way")
        return _unit(self.normal)

    # TODO thisis in global space right? rename to ends_global if so
    def ends(self) -> Tuple[V3, ...]:
        """The two extremities, or the point itself.

        A plane has no extremities along any one direction, so it answers with
        the one point it is placed at; the rules that ask this are the ones for
        lines.
        """
        if self.is_point or self.is_plane:
            return (self.at,)
        at, unit = self.at, self.along
        return tuple(
            at + unit * station
            for station in (self.interval or (0.0, 0.0))
        )


# TODO rename to _stations_global
def _stations(span: MeasureSpan, along: VectorLike) -> Tuple[float, float]:
    """How far a span reaches along a direction, as absolute stations.

    Absolute -- measured from the world origin rather than from the span's own
    point -- because two features have two different points, and overlap is a
    question about one shared ruler.
    """
    reach = [_dot(end, along) for end in span.ends()]
    return (min(reach), max(reach))


def _at_station(span: MeasureSpan, along: VectorLike, station: float) -> V3:
    """The point on a span that sits at a given station along `along`."""
    if span.is_point:
        return span.at
    unit = span.along
    rate = _dot(unit, along)
    if abs(rate) < 1e-12:
        return span.at
    step = (station - _dot(span.at, along)) / rate
    return span.at + unit * step


def _foot_on(span: MeasureSpan, point: VectorLike) -> V3:
    """Where a perpendicular from `point` meets a span, kept on the span."""
    at, unit = span.at, span.along
    station = _dot(_v3(point) - at, unit)
    low, high = span.interval or (station, station)
    # Clamped: a dimension whose end floats off the end of a short edge points
    # at nothing, and the nearest place on the feature is the honest answer.
    station = max(low, min(high, station))
    return at + unit * station


def _representative_point(span: MeasureSpan) -> V3:
    """The one point that stands for a span when something must be dropped onto it.

    A point is itself. A line offers the middle of its surviving extent, which is
    where a reader would put a finger on it.
    """
    if not span.is_line:
        return span.at
    low, high = span.interval or (0.0, 0.0)
    unit = span.along
    middle = (low + high) / 2
    return span.at + unit * middle


def _foot_on_plane(span: MeasureSpan, point: VectorLike) -> V3:
    """Where a perpendicular from `point` meets a plane.

    NOT clamped to the face, unlike the foot on a line: a span carries a plane's
    normal and a point on it, not its outline, so there is nothing here to clamp
    against. For a pair that admits a distance the two features face each other,
    which is when the foot lands on the face anyway. Clamping properly wants the
    face's corners -- see the note in cutcsg about extents being an AABB.
    """
    point, unit = _v3(point), span.facing
    gap = _dot(point - span.at, unit)
    return point - unit * gap


def _closest_on_line(point: VectorLike, at: VectorLike, direction: VectorLike) -> V3:
    """Where a line comes nearest a point."""
    at, unit = _v3(at), _unit(direction)
    step = _dot(_v3(point) - at, unit)
    return at + unit * step


def _plane_crossing(first: MeasureSpan, second: MeasureSpan) -> Optional[Line]:
    """The line two planes share, or None when they are too near parallel.

    Too near parallel has no corner to stand in -- and admits a distance rather
    than an angle anyway.
    """
    # BOTH UNIT, since they come from `facing`. That is what lets the length of
    # their cross stand for the sine between the two planes, which is the only
    # reason the raw cross is wanted below: nothing here is scale-dependent,
    # because nothing here has a scale.
    one, other = first.facing, second.facing
    # The cross at its own length, then. Asking _cross instead normalised it, so
    # the length was always exactly one: the refusal below could only fire on
    # two EXACTLY parallel planes, and intersect_planes divided by one rather
    # than by that sine -- putting the corner a factor of it toward the world
    # origin, which is right only where the two happen to meet square.
    #
    # safe_zero_test_sq because that length is SQUARED: it squares the tolerance
    # itself, so PARALLEL_EPSILON means here what it means everywhere else in
    # this file -- a plain sine. Compared raw it read as a tolerance on the
    # square and refused anything under 5.7 degrees instead of 0.57.
    along = _raw_cross(one, other)
    if safe_zero_test_sq(_dot(along, along), eps=PARALLEL_EPSILON):
        return None

    # The refusal above is this file's, not geometry's: how near parallel is too
    # near to stand a dimension in is a question about drafting. intersect_planes
    # refuses only what it cannot compute, at EPSILON_GENERIC, and takes no eps
    # of its own -- giving it one would put a drafting rule in the geometry
    # layer, where the next caller would inherit a tolerance meant for this one.
    crossing = intersect_planes(Plane(normal=one, point=first.at),
                                Plane(normal=other, point=second.at))
    if crossing is None:
        return None
    return Line(point=crossing.point, direction=_unit(crossing.direction))


def _ray_toward(
    ray: VectorLike, vertex: VectorLike, span: MeasureSpan,
    other: Optional[MeasureSpan] = None,
) -> Optional[V3]:
    """A unit ray from `vertex`, turned to point at where the feature is. Used for determing how to draw an angle measurement
    """
    unit = _unit(ray)
    if not any(abs(part) > 1e-9 for part in unit):
        return None
    if span.is_line:
        stations = [_dot(end - vertex, unit) for end in span.ends()]
        low, high = min(stations), max(stations)
        straddles = low < -1e-9 < 1e-9 < high
        outward = other.outward if other is not None else None
        if straddles and outward is not None:
            lean = -_dot(unit, _unit(outward))
        else:
            # The longer side, which for an edge running off one way is that way.
            lean = high + low
    else:
        lean = _dot(unit, span.at - vertex)
    return -unit if lean < 0 else unit


# TODO NEXT PASS: `axes` is the last mapping-as-object here, and wants to be a
# frozen ViewAxes(look, right, up) with a from_wire, and the parameter renamed
# -- `view`, not `frame`, which is a timber frame everywhere else. Left for its
# own pass because it is the awkward one:
#   - it crosses the wire, built in runner from payload look/right/up
#   - right and up are legitimately absent for a 3D pick, so it is Optional
#     fields inside an Optional argument -- two levels that should be one
#   - the three fallbacks ((0,0,-1), (1,0,0), (0,0,1)) live at the use sites
#     here, not in the type; moving them in is a behaviour change and wants its
#     own test
#   - ~19 call sites and ~46 dict literals across drawing, runner and tests
#   - the name is already overloaded: runner has a different `axes` for a
#     timber's width/height directions
def pair_separation(
    one: Optional[Geometry], other: Optional[Geometry],
    kind: MeasurementKind, axes: Optional[Mapping] = None,
) -> Optional[float]:
    """What a distance between these two comes to, FROM THE FEATURES ALONE.

    No anchors. Where a dimension anchors attaches to is a separate question.

    None when the pair measures no length -- an angle, or a pair that admits
    nothing.

    TODO cleanup all these comments. I think we deleted the mesaurements.js copy
    THE VIEWER HAS A COPY, as measureValue in measurements.js, because it needs
    the number on every frame and cannot ask python for it. A test runs the two
    against each other.
    """
    if kind.operation is not MeasurementOperation.DISTANCE:
        return None
    at_one, at_other = _anchor_of(one), _anchor_of(other)
    if at_one is None or at_other is None:
        return None

    look = _unit((axes or {}).get("look") or (0, 0, -1))
    in_three_d = kind.space is MeasurementSpace.THREE_D
    if in_three_d:
        form_one, run_one = three_d_form(one)
        form_other, run_other = three_d_form(other)
    else:
        form_one, run_one = projected_form(one, look)
        form_other, run_other = projected_form(other, look)
    if form_one is None or form_other is None:
        return None

    gap = _v3(at_other) - _v3(at_one)
    if not in_three_d:
        # On a sheet, only what survives the projection counts.
        gap = gap - look * _dot(gap, look)

    if kind.direction is MeasurementDirection.HORIZONTAL:
        return abs(_dot(gap, _unit((axes or {}).get("right") or (1, 0, 0))))
    if kind.direction is MeasurementDirection.VERTICAL:
        return abs(_dot(gap, _unit((axes or {}).get("up") or (0, 0, 1))))

    # Square to whichever of the two constrains it most. A plane leaves one
    # direction to measure along, a line leaves two, and two points leave the
    # distance itself.
    def constraining(form):
        # A form with no way to run constrains nothing, so it is passed over --
        # as the viewer's copy passes it over. Squaring to a zero direction
        # would call every such pair nothing at all.
        one_run = run_one if form_one is form else None
        other_run = run_other if form_other is form else None
        for run in (one_run, other_run):
            if run is not None and any(part for part in run):
                return run
        return None

    plane = constraining(MeasurementFeature.PLANE)
    if plane is not None:
        return abs(_dot(gap, _unit(plane)))

    line = constraining(MeasurementFeature.LINE)
    if line is None:
        return safe_norm(gap)
    unit = _unit(line)
    return safe_norm(gap - unit * _dot(gap, unit))


def measures_nothing(
    one: Optional[Geometry], other: Optional[Geometry],
    kind: MeasurementKind, axes: Optional[Mapping] = None,
) -> bool:
    """Whether this pair has nothing between them to dimension.

    From the features, not from placed ends: what a distance comes to does not
    depend on where it is drawn. An arris lying ON a face is the ordinary way
    to reach this.
    """
    gap = pair_separation(one, other, kind, axes)
    return gap is not None and gap < DEGENERATE_SEPARATION


@dataclass(frozen=True)
class AngleRays:
    """Where an angle is, and which two ways it opens.

    A corner, two unit rays from it, and the plane they span, in world space.
    The viewer sweeps the arc in that plane and projects it, so the arc lies on
    the work and foreshortens with it -- drawn flat on the screen instead it
    shows the PROJECTED angle and agrees with its own label from one direction
    only.

    THE RAYS DECIDE THE VALUE. The angle a reader wants is the one the two
    features actually subtend -- the corner they make, not its supplement -- so
    it is read off these rather than off the features' normals, which give the
    same absolute dot for 45 degrees and 135.
    """

    vertex: V3
    #: `from` and `to` on the wire. Spelled out here because `from` is a
    #: keyword, and a field cannot be called it.
    opens_from: V3
    opens_to: V3
    #: The plane the angle is IN: for two faces, the one both are perpendicular
    #: to, whose normal is the corner they share.
    normal: V3

    def as_wire(self) -> Dict[str, list]:
        return {"vertex": list(self.vertex), "from": list(self.opens_from),
                "to": list(self.opens_to), "normal": list(self.normal)}


def angle_rays(first: MeasureSpan, second: MeasureSpan) -> Optional[AngleRays]:
    """Where an angle between two features is, and which two ways it opens.

    A vertex, two unit rays from it, and the plane they span, in world space,
    as `{"vertex", "from", "to", "normal"}` -- or None when the pair makes no
    corner.
    """
    if first is None or second is None:
        return None
    if first.is_plane and second.is_plane:
        crossing = _plane_crossing(first, second)
        if crossing is None:
            return None
        along = crossing.direction
        middle = (first.at + second.at) / 2
        vertex = _closest_on_line(middle, crossing.point, along)
        # Square to the shared corner, and lying in its own face.
        rays = (_ray_toward(_cross(along, first.facing), vertex, first),
                _ray_toward(_cross(along, second.facing), vertex, second))
    elif first.is_line and second.is_line:
        placed = _closest_between(first, second)
        if placed is None:
            return None
        vertex = placed
        rays = (_ray_toward(first.along, vertex, first, second),
                _ray_toward(second.along, vertex, second, first))
    elif first.is_line or second.is_line:
        line, plane = (first, second) if first.is_line else (second, first)
        # No None check: _line_meets_plane always answers, falling back to the
        # nearest point when the line runs flat along the face. Whether it
        # SHOULD refuse instead is the question in its own TODO -- if it ever
        # does, this needs a guard again.
        vertex = _line_meets_plane(line, plane)
        in_plane = _flatten_onto(line.along, plane.facing)
        if in_plane is None:
            return None
        line_ray = _ray_toward(line.along, vertex, line, plane)
        plane_ray = _ray_toward(in_plane, vertex, plane)
        rays = (line_ray, plane_ray) if first.is_line else (plane_ray, line_ray)
    else:
        return None
    if rays[0] is None or rays[1] is None:
        return None
    # The plane the angle is IN: the one both rays lie in, which for two faces
    # is the plane they are each perpendicular to -- its normal is the corner
    # they share. Carried so the arc can be swept in it rather than drawn flat
    # on the screen, where it shows the projected angle and agrees with the
    # number it labels only from the one direction.
    # RAW, because what is being asked is how long it is: two rays that barely
    # cross span no plane worth sweeping an arc in. Normalising first answered a
    # unit vector made of rounding noise for exactly those, so the test below
    # could only ever catch two rays that were bit-for-bit parallel. Nothing
    # reaches it today -- every shape above refuses a near-parallel pair first,
    # the closest at 0.57 degrees -- so this is the guard behind those, doing
    # what it says rather than what it did.
    upright = _raw_cross(rays[0], rays[1])
    if not any(abs(part) > 1e-9 for part in upright):
        return None
    return AngleRays(vertex=_v3(vertex), opens_from=rays[0], opens_to=rays[1],
                     normal=_unit(upright))

# TODO measuring.py has this same closed form inside
# mark_distance_from_corner_along_edge_by_finding_closest_point_on_line, wrapped
# in timber/edge/end semantics. The shared core -- two Lines in, two stations
# out -- belongs in geometry.py beside intersect_planes; this clamps to the
# intervals and takes the midpoint, that one raises on parallel.
def _closest_between(first: MeasureSpan, second: MeasureSpan) -> Optional[V3]:
    """Where two lines come nearest each other, kept on both.
    """
    one, other = first.along, second.along
    facing = _dot(one, other)
    # The sine between the two, SQUARED, so safe_zero_test_sq -- which squares
    # the tolerance rather than the value, leaving PARALLEL_EPSILON meaning a
    # plain sine here as it does for a line against a plane just below.
    spread = 1 - facing * facing
    if safe_zero_test_sq(spread, eps=PARALLEL_EPSILON):
        return None
    gap = first.at - second.at
    lean_one, lean_other = _dot(one, gap), _dot(other, gap)
    station_one = (facing * lean_other - lean_one) / spread
    station_other = (lean_other - facing * lean_one) / spread
    station_one = _clamp_to(station_one, first.interval)
    station_other = _clamp_to(station_other, second.interval)
    on_one = first.at + one * station_one
    on_other = second.at + other * station_other
    return (on_one + on_other) / 2

def _clamp_to(station: float, interval: Optional[Tuple[float, float]]) -> float:
    if interval is None:
        return station
    low, high = interval
    return max(low, min(high, station))


def _line_meets_plane(line: MeasureSpan, plane: MeasureSpan) -> V3:
    """Where a line crosses a plane, or some nearest point if parallel
    
    # TODO why do we need to support the parallel case, could/should we just have this return None instead in the parallel cases?
    """
    unit, normal = line.along, plane.facing
    rate = _dot(unit, normal)
    if are_vectors_perpendicular(unit, normal, eps=PARALLEL_EPSILON):
        # Running along the face: it never crosses, so stand where the edge is
        # and drop that onto the face.
        return _foot_on_plane(plane, _representative_point(line))
    at = line.at
    step = _dot(plane.at - at, normal) / rate
    step = _clamp_to(step, line.interval)
    return at + unit * step


def _flatten_onto(direction: VectorLike, normal: VectorLike) -> Optional[V3]:
    """The part of a direction that lies in a plane."""
    unit, up = _unit(direction), _unit(normal)
    flat = unit - up * _dot(unit, up)
    if not any(abs(part) > 1e-9 for part in flat):
        return None
    return _unit(flat)


def angle_between(rays: Optional[AngleRays]) -> Optional[float]:
    """The angle the rays open, in degrees. The value a reader sees."""
    if rays is None:
        return None
    facing = max(-1.0, min(1.0, _dot(_unit(rays.opens_from), _unit(rays.opens_to))))
    return math.degrees(math.acos(facing))


def distance_anchors(
    first: MeasureSpan,
    second: MeasureSpan,
    kind: MeasurementKind,
    # TODO give axes a real type and a better name -- see ViewAxes in
    # docs/drawing-rule-migration.md.
    axes: Optional[Mapping] = None,
) -> Tuple[V3, V3]:
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
    it. A face only IS a plane in 3D; on a sheet it is a line seen
    edge-on and takes the rules above.

    PERPENDICULAR, two points: themselves. With no line to be square to, the
    distance between them is the distance.

    HORIZONTAL or VERTICAL: the first end stays put and the second is projected
    onto the axis through it, so the dimension runs along the sheet's own
    direction and reads the separation in it. Offered only between two points
    today -- kinds_for lists no other pair for them -- so the two closest points
    on the two features are the two points.

    TODO I think you can improve the logic a bit here in some cases but it's fine for now.
    """
    named = kind.name if hasattr(kind, "name") else str(kind)

    if named in ("projected_horizontal_distance", "projected_vertical_distance"):
        axis = _unit((axes or {}).get(
            "right" if named.endswith("horizontal_distance") else "up") or (1, 0, 0))
        at = first.at
        offset = _dot(second.at - at, axis)
        return (first.at, at + axis * offset)

    # A PLANE is measured to by dropping a perpendicular onto it. The anchor is
    # chosen on whichever feature has less freedom -- a point has none, a line
    # one direction, a plane two -- and carried to the other square to it. That
    # is what makes the dimension perpendicular to the face rather than merely
    # touching it: an edge and the face it runs parallel to were both treated as
    # lines and put through the shared-station rule, which shares ONE direction,
    # and the dimension leaned by however far the two were offset in the other.
    #
    # Only in 3D: on a sheet a face is a line and never gets here.
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

    along = first.along
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
    one: Optional[Geometry], other: Optional[Geometry], look: VectorLike,
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
        parallel = are_vectors_parallel(_v3(run_one), _v3(run_other),
                                        eps=PARALLEL_EPSILON)
    return kinds_for(form_one, form_other, MeasurementSpace.PROJECTED, parallel=parallel)


# TODO NEXT PASS: there are only two spaces and they are exclusive, so this and
# projected_form could be one `form_of(geometry, space, look=None)`, and
# three_d_kinds/projected_kinds one `kinds_admitted(one, other, space,
# look=None)`. That would also settle the complaint below -- _three_d_parallel
# takes a second argument that means a normal for a plane and a direction for a
# line, which is only tolerable because it is private and has one caller.
# Held over: it changes call sites in runner and ~27 in the tests, and should
# fail on its own if it is wrong.
def three_d_form(
    geometry: Optional[Geometry],
) -> Tuple[Optional[MeasurementFeature], Optional[V3]]:
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
    if isinstance(geometry, Point):
        return (MeasurementFeature.POINT, None)
    if isinstance(geometry, Line):
        return (MeasurementFeature.LINE, _unit(geometry.direction))
    if isinstance(geometry, Plane):
        return (MeasurementFeature.PLANE, _unit(geometry.normal))
    return (None, None)



def _three_d_parallel(
    form_one: MeasurementFeature,
    run_one: Optional[VectorLike],
    form_other: MeasurementFeature,
    run_other: Optional[VectorLike],
) -> Optional[bool]:
    """Whether two 3D features are parallel
    """
    # TODO the second argument means different things by feature type -- a
    # plane's normal, a line's direction -- which is what makes the test below
    # read oddly. Folded into `form_of` next pass; see the note above.
    if run_one is None or run_other is None:
        return None
    one, other = _v3(run_one), _v3(run_other)
    if form_one is form_other:
        return are_vectors_parallel(one, other, eps=PARALLEL_EPSILON)
    return are_vectors_perpendicular(one, other, eps=PARALLEL_EPSILON)


def three_d_kinds(
    one: Optional[Geometry], other: Optional[Geometry],
) -> Tuple[MeasurementKind, ...]:
    """Which kinds this pair admits in the 3D view. Empty when none.
    """
    form_one, run_one = three_d_form(one)
    form_other, run_other = three_d_form(other)
    if form_one is None or form_other is None:
        return ()
    return kinds_for(
        form_one, form_other, MeasurementSpace.THREE_D,
        parallel=_three_d_parallel(form_one, run_one, form_other, run_other),
    )


def kinds_for(
    feature_a: MeasurementFeature,
    feature_b: MeasurementFeature,
    space: MeasurementSpace,
    parallel: Optional[bool] = None,
) -> Tuple[MeasurementKind, ...]:
    """Which kinds a pair admits, best first. Empty when it admits none. Features are already projected if space is projected
    """
    pair = {feature_a, feature_b}

    if MeasurementFeature.AREA in pair:
        # A face seen at an angle covers the view: nothing to measure to, and
        # its middle is a point about nothing.
        return ()
    if MeasurementFeature.PLANE in pair and space is MeasurementSpace.PROJECTED:
        raise ValueError("a plane is a 3D feature; project it first")
    if MeasurementFeature.AREA in pair and space is MeasurementSpace.THREE_D:
        raise ValueError("an area is a projected feature; it has no 3D counterpart")

    flat = {MeasurementFeature.LINE, MeasurementFeature.PLANE}
    both_flat = feature_a in flat and feature_b in flat
    if both_flat and parallel is False:
        return (_projected(MeasurementOperation.ANGLE) if space is MeasurementSpace.PROJECTED
                else _three_d(MeasurementOperation.ANGLE),)

    if space is MeasurementSpace.THREE_D:
        return (_three_d(MeasurementOperation.DISTANCE),)

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

    The measurement's own property, not the viewport's. If this is a projected measurement in a 2d drawing, the plane is expected to match the drawing viewport's plane (pretty sure we assert or warn on this) 
    """

    #: A point on the plane, in world space.
    at: V3
    #: The plane's normal, in world space. Not required to be unit length on the
    #: way in; compared up to sign, since a plane has no front.
    normal: V3

    def __post_init__(self):
        for name in ("at", "normal"):
            given = getattr(self, name)
            if len(given) != 3:
                raise ValueError(f"A plane's {name} is [x, y, z], got {given!r}")
            object.__setattr__(self, name, _v3(given))
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
    """Where the measurement graphic (like the label with the #s on it betwene the 2 lines) is placed
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
        """
        """
        if value is None or isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            offset = value.get("offset")
            return cls(offset=None if offset is None else float(offset))
        raise TypeError(f"Expected a placement or a mapping, got {type(value).__name__}")


# CONTINUE HERE
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

    # TODO remove Optional
    #: The plane this is taken and drawn on, or None to take the viewport's.
    #: Not part of identity either: the same two features measured on a
    #: different plane is the same measurement seen from elsewhere, and giving
    #: it a second identity would let a file hold both and draw them twice.
    plane: Optional[MeasurementPlane] = None

    def __post_init__(self):
        self._canonicalise_anchors()

    def _canonicalise_anchors(self) -> None:
        """Put the two anchors in one order, so a pair cannot be written twice.

        Measuring A to B and measuring B to A are the same measurement up to a sign. Sorting at creation means there is only ever one way to write it down.

        NOTE Some day we may support asymmetric measurements.
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
        """
        """
        if kind is None:
            return ()
        wire = kind.as_wire()
        return (wire["operation"], wire["space"], wire["direction"])

    def pair_identity(self) -> Tuple[Tuple, Tuple]:
        """
        """
        return (self.anchor_a.identity(), self.anchor_b.identity())

    def identity(self) -> Tuple[Tuple, Tuple, Tuple, str]:
        """
        """
        return (
            self.anchor_a.identity(),
            self.anchor_b.identity(),
            self.kind_identity(self.kind),
            str(self.measure_id or ""),
        )


class MeasurementSource(Enum):
    """Where a measurement came from, ordered by what replaces what
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



# TODO move these into a viewport.py file or prefix with Viewport to make it more clear
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
# default drawing layouts 
# ---------------------------------------------------------------------------

# TODO give a type alias for Tuple[Viewport, ...] (ViewportList)
# aso what's th e difference between this and Sequence[Viewport]? oh I guess tuple has at least one?
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
    """

    name: str

    # TODO shouldn't this be ResolvedTimebrPath?
    #: Held as a tuple; any sequence may be given. The ELEMENTS are exact --
    #: a TimberPath, not a string that looks like one. Wrapping a path is what
    #: stops it being passed where a drawing's name was meant, and taking a
    #: bare string here would give that away at the one moment it helps.
    timber_paths: Sequence[TimberPath] = ()

    # used for determining override behavior, defaults to the name if not provided 
    # TODO just create a ctor for Drawing where the id is optional, and then make this non optional, this lets you clean up some of the other weird stuff you're doing in post_init
    drawing_id: Optional[DrawingId] = None

    #: The floating viewports of this sheet, in the order they were written.
    #: That order is what numbers them -- see walk -- so it is part of what the
    #: drawing means. It is not the drawing order; z is.
    viewports: Sequence[Viewport] = ()

    # TODO why is this optional?
    #: The sheet these sit on. A Length anywhere in the tree is measured
    #: against it.
    page: Optional[Page] = None

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

        # TODO in the ctor just make viewports Optional{..} and then if it's none, use default viewports
        viewports = tuple(self.viewports) or default_viewports_for(len(self.timber_paths))
        object.__setattr__(self, 'viewports', viewports)
        self._check_placement()
        self._check_each_viewport_appears_once()

    # ---------------------------------------------------------------- the tree

    def walk(self) -> Iterator[Tuple[ViewportId, 'Viewport']]:
        """Every viewport of this drawing, with the id its position gives it.

        Depth first and in written order, so a parent comes before the views
        inside it.
        """
        def descend(viewport: 'Viewport', path: Tuple[int, ...]):
            yield (ViewportId(".".join(str(step) for step in path)), viewport)
            for index, child in enumerate(viewport.children):
                yield from descend(child, path + (index,))

        for index, root in enumerate(self.viewports):
            yield from descend(root, (index,))

    def measurements_by_viewport(self) -> Dict[str, Tuple[Measure, ...]]:
        """Every dimension of this drawing, under the id of the view it is in.
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

    # TODO rename to get_viewport_id
    def id_of(self, viewport: 'Viewport') -> ViewportId:
        """Where this viewport sits, which is what identifies it.
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
