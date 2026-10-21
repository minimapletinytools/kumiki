"""Measuring: what a pair of features can be measured as, where a dimension between them attaches,
and what it comes to.

The viewer keeps a copy of some of it in kigumi/webview/measurements.js; the docstrings below say
which, and a test runs the two against each other.

Vectors here are rule.py's V3, as everywhere else in the library. The types a measurement arrives
as off the wire -- lists and tuples out of JSON -- are taken at the edge and converted once; see
VectorLike.

See .claude/plans/measurement-spec.md, and .claude/plans/archive/drawing-rule-migration.md for what is
still to do. Where a sheet's viewports sit, and the Drawing that holds them, are drawing.py.
"""

import math
import warnings
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Dict, Mapping, Optional, Sequence, Tuple, Union

from ..geometry import Line, Plane, Point, closest_stations, intersect_planes
from ..identity import FeaturePath, MeasurementId
if TYPE_CHECKING:
    from ..csg.feature_paths import FeatureHandle
    from ..timber import Frame
from ..rule import (Matrix, V3, are_vectors_parallel,
                   are_vectors_perpendicular, create_v3, cross_product,
                   safe_dot_product, safe_norm, safe_zero_test_sq)
from .sheet_shape import SheetPoint, sheet_shape


class MeasurementSpace(Enum):
    """Whether a measurement is taken in the projected viewport or in 3d space
    """
    PROJECTED = "projected"
    THREE_D = "3d"


class MeasurementOperation(Enum):
    DISTANCE = "distance"
    ANGLE = "angle"


class MeasurementDirection(Enum):
    """Which direction a distance is taken along."""

    #: Square to whichever of the pair constrains it most: along a plane's
    #: normal, across a line, and straight between two points.
    PERPENDICULAR = "perpendicular"
    #: Along the view's right axis.
    HORIZONTAL = "horizontal"
    #: Along the view's up axis.
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
        try:
            return cls.parse(str(value))
        except ValueError:
            warnings.warn(f"Ignoring an unreadable measurement kind: {value!r}")
            return None

    @classmethod
    def parse(cls, text: str) -> 'MeasurementKind':
        """Read a kind back from its composed name."""
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


# TODO refine these 3 epsilons below? alginment and parallel seem especially big?

#: Below this, in world units, two features are in the same place and there is
#: nothing between them to dimension. A measurement that comes to zero draws as
#: nothing, which reads as a measurement that failed rather than one that was
#: never worth making -- so a pair this close is refused at the pick instead.
DEGENERATE_SEPARATION = 1e-6

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


#: The camera frame a measurement is judged against when none is given.
DEFAULT_LOOK = create_v3(0, 0, -1)
DEFAULT_RIGHT = create_v3(1, 0, 0)
DEFAULT_UP = create_v3(0, 0, 1)


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


def project_geometry_for_measuring(
    geometry: Optional[Geometry], normal: VectorLike,
) -> Optional[Geometry]:
    """A feature as it is seen on the sheet that *normal* faces out of.

    A point stays a point. An edge seen end-on becomes one, and otherwise stays
    a line, flattened onto the sheet. A face is a line edge-on. The rule is
    sheet_shape's; this answers it as geometry.

    None if it does not project to a line -- a face seen at any other angle
    projects to an area -- or if it is not a recognized piece of projectable
    geometry.
    """
    if isinstance(geometry, Point):
        return geometry
    shape = sheet_shape(geometry, _v3(normal))
    if shape is None or not isinstance(geometry, (Line, Plane)):
        return None
    if isinstance(shape, SheetPoint):
        return Point(position=geometry.point)
    # A face edge-on draws as a line along itself, square to its normal and to the line of sight.
    #
    # TODO mostly redundant. Edges outrank projected faces, and most faces are fully determined by
    # declared or derived edges. Only things like a Cylinder's cap are not covered. We should label
    # these exceptional features and only project those ones.
    return Line(direction=create_v3(*shape.run), point=geometry.point)


def form_of(geometry: Optional[Geometry]) -> Optional[MeasurementFeature]:
    """Which of the three shapes a feature is, for asking the table.

    Nothing is projected away: in the 3D view the camera belongs to the reader
    and turns as they look around, so a face is a plane whatever angle it is
    seen from. Project first to ask the same question of a sheet.
    """
    if isinstance(geometry, Point):
        return MeasurementFeature.POINT
    if isinstance(geometry, Line):
        return MeasurementFeature.LINE
    if isinstance(geometry, Plane):
        return MeasurementFeature.PLANE
    return None


def _are_parallel(
    one: Optional[Geometry], other: Optional[Geometry],
) -> Optional[bool]:
    """Whether two features run together. None when either has no way to run.

    A plane is parallel to a plane when their normals are, and to a line when
    the line is SQUARE to its normal -- which is why this asks the geometry
    rather than being handed one vector per side.
    """
    if isinstance(one, Plane) and isinstance(other, Plane):
        return are_vectors_parallel(_unit(one.normal), _unit(other.normal),
                                    eps=PARALLEL_EPSILON)
    if isinstance(one, Line) and isinstance(other, Line):
        return are_vectors_parallel(_unit(one.direction), _unit(other.direction),
                                    eps=PARALLEL_EPSILON)
    line, plane = (one, other) if isinstance(one, Line) else (other, one)
    if isinstance(line, Line) and isinstance(plane, Plane):
        return are_vectors_perpendicular(_unit(line.direction), _unit(plane.normal),
                                         eps=PARALLEL_EPSILON)
    return None


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


def _as_v3(value) -> V3:
    return value if isinstance(value, Matrix) else _v3(value)


@dataclass(frozen=True)
class PointSpan:
    """A point being measured to."""

    at: V3
    #: Roughly outward from the body of the feature. Only decides which side an angle opens on.
    outward: Optional[V3] = field(default=None, kw_only=True)

    def __post_init__(self):
        object.__setattr__(self, 'at', _as_v3(self.at))
        if self.outward is not None:
            object.__setattr__(self, 'outward', _as_v3(self.outward))

    def ends_global(self) -> Tuple[V3, ...]:
        return (self.at,)


@dataclass(frozen=True)
class LineSpan:
    """A line being measured to: through `at` along `direction`, cropped to `interval` from `at`."""

    at: V3
    direction: V3
    interval: Optional[Tuple[float, float]] = None
    outward: Optional[V3] = field(default=None, kw_only=True)

    def __post_init__(self):
        object.__setattr__(self, 'at', _as_v3(self.at))
        object.__setattr__(self, 'direction', _as_v3(self.direction))
        if self.interval is not None:
            object.__setattr__(self, 'interval', tuple(float(end) for end in self.interval))
        if self.outward is not None:
            object.__setattr__(self, 'outward', _as_v3(self.outward))

    @property
    def along(self) -> V3:
        """Which way this line runs, unit length."""
        return _unit(self.direction)

    def ends_global(self) -> Tuple[V3, ...]:
        """The two extremities."""
        return tuple(self.at + self.along * station for station in (self.interval or (0.0, 0.0)))


@dataclass(frozen=True)
class PlaneSpan:
    """A plane being measured to, through `at` with `normal`. In 3D only: on a sheet a face is a line."""

    at: V3
    normal: V3
    outward: Optional[V3] = field(default=None, kw_only=True)
    #: The part of the plane the face covers on its timber, as convex polygons of world points; empty
    #: when not known. Decides where an angle's corner goes and which way it opens.
    region: Tuple[Tuple[V3, ...], ...] = field(default=(), kw_only=True)

    def __post_init__(self):
        object.__setattr__(self, 'at', _as_v3(self.at))
        object.__setattr__(self, 'normal', _as_v3(self.normal))
        if self.outward is not None:
            object.__setattr__(self, 'outward', _as_v3(self.outward))
        object.__setattr__(self, 'region', tuple(tuple(_as_v3(corner) for corner in polygon)
                                                 for polygon in self.region))

    @property
    def facing(self) -> V3:
        """Which way this plane faces, unit length."""
        return _unit(self.normal)

    def ends_global(self) -> Tuple[V3, ...]:
        return (self.at,)


#: What a feature is, where a measurement is being taken.
MeasureSpan = Union[PointSpan, LineSpan, PlaneSpan]


def _stations_global(span: MeasureSpan, along: VectorLike) -> Tuple[float, float]:
    """How far a span reaches along a direction, as absolute stations.

    Absolute -- measured from the world origin rather than from the span's own
    point -- because two features have two different points, and overlap is a
    question about one shared ruler.
    """
    reach = [_dot(end, along) for end in span.ends_global()]
    return (min(reach), max(reach))


def _at_station(span: Union[PointSpan, LineSpan], along: VectorLike, station: float) -> V3:
    """The point on a span that sits at a given station along `along`."""
    if isinstance(span, PointSpan):
        return span.at
    unit = span.along
    rate = _dot(unit, along)
    if abs(rate) < 1e-12:
        return span.at
    step = (station - _dot(span.at, along)) / rate
    return span.at + unit * step


def _foot_on(span: LineSpan, point: VectorLike) -> V3:
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
    if not isinstance(span, LineSpan):
        return span.at
    low, high = span.interval or (0.0, 0.0)
    unit = span.along
    middle = (low + high) / 2
    return span.at + unit * middle


def _foot_on_plane(span: PlaneSpan, point: VectorLike) -> V3:
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


def _plane_crossing(first: PlaneSpan, second: PlaneSpan) -> Optional[Line]:
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
    if isinstance(span, LineSpan):
        stations = [_dot(end - vertex, unit) for end in span.ends_global()]
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


@dataclass(frozen=True)
class ViewAxes:
    """Which way a sheet is seen, and which way is across it and up it.

    A camera frame. `right` and `up` are only consulted by a horizontal or
    vertical distance, so a 3D pick passes neither and gets the defaults.
    """

    # A factory, since Python 3.11+ refuses an unhashable Matrix as a default.
    look: V3 = field(default_factory=lambda: DEFAULT_LOOK)
    right: V3 = field(default_factory=lambda: DEFAULT_RIGHT)
    up: V3 = field(default_factory=lambda: DEFAULT_UP)

    def __post_init__(self):
        for name, fallback in (("look", DEFAULT_LOOK), ("right", DEFAULT_RIGHT),
                               ("up", DEFAULT_UP)):
            given = getattr(self, name)
            object.__setattr__(self, name, fallback if given is None else _v3(given))

    @classmethod
    def from_wire(cls, value) -> 'ViewAxes':
        """A camera frame as the viewer sends it, or one already built."""
        if value is None:
            return DEFAULT_VIEW
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(look=value.get("look"), right=value.get("right"),
                       up=value.get("up"))
        raise TypeError(f"Expected view axes or a mapping, got {type(value).__name__}")


#: What a measurement is judged against when no camera is given.
DEFAULT_VIEW = ViewAxes()


def pair_separation(
    one: Optional[Geometry], other: Optional[Geometry],
    kind: MeasurementKind, view: Optional[ViewAxes] = None,
) -> Optional[float]:
    """What a distance between these two comes to, FROM THE FEATURES ALONE.

    No anchors. Where a dimension anchors attaches to is a separate question.

    None when the pair measures no length -- an angle, or a pair that admits
    nothing.
    """
    if kind.operation is not MeasurementOperation.DISTANCE:
        return None
    at_one, at_other = _anchor_of(one), _anchor_of(other)
    if at_one is None or at_other is None:
        return None

    view = ViewAxes.from_wire(view)
    look = _unit(view.look)
    in_three_d = kind.space is MeasurementSpace.THREE_D

    gap = _v3(at_other) - _v3(at_one)
    if not in_three_d:
        # On a sheet, only what survives the projection counts -- of the gap,
        # and of the two features it runs between.
        gap = gap - look * _dot(gap, look)
        one = project_geometry_for_measuring(one, look)
        other = project_geometry_for_measuring(other, look)

    if kind.direction is MeasurementDirection.HORIZONTAL:
        return abs(_dot(gap, _unit(view.right)))
    if kind.direction is MeasurementDirection.VERTICAL:
        return abs(_dot(gap, _unit(view.up)))

    # Square to whichever of the two constrains it most. A plane leaves one
    # direction to measure along, a line leaves two, and two points leave the
    # distance itself.
    def constraining(shape):
        # A feature with no way to run constrains nothing, so it is passed over.
        # Squaring to a zero direction would call every such pair nothing at all.
        for geometry in (one, other):
            if not isinstance(geometry, shape):
                continue
            run = geometry.normal if shape is Plane else geometry.direction
            if any(part for part in run):
                return run
        return None

    facing = constraining(Plane)
    if facing is not None:
        return abs(_dot(gap, _unit(facing)))

    along = constraining(Line)
    if along is None:
        return safe_norm(gap)
    unit = _unit(along)
    return safe_norm(gap - unit * _dot(gap, unit))


def measures_nothing(
    one: Optional[Geometry], other: Optional[Geometry],
    kind: MeasurementKind, view: Optional[ViewAxes] = None,
) -> bool:
    """Whether this pair has nothing between them to dimension.

    From the features, not from placed ends: what a distance comes to does not
    depend on where it is drawn. An arris lying ON a face is the ordinary way
    to reach this.
    """
    gap = pair_separation(one, other, kind, view)
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
    #: Each feature drawn on to the corner where the corner is off it, as world segments, dashed:
    #: a line carried on along itself; a face, in 3D, its plane swept to the corner line.
    phantoms: Tuple[Tuple[V3, V3], ...] = ()

    def as_wire(self) -> Dict[str, list]:
        return {"vertex": list(self.vertex), "from": list(self.opens_from),
                "to": list(self.opens_to), "normal": list(self.normal),
                "phantoms": [[list(start), list(end)] for start, end in self.phantoms]}


def angle_rays(first: MeasureSpan, second: MeasureSpan, flip: bool = False) -> Optional[AngleRays]:
    """Where an angle between two features is, and which two ways it opens.

    A vertex, two unit rays from it, and the plane they span, in world space -- or None when the
    pair makes no corner.

    - Two faces: the corner is on the line their planes share, in the middle of where both faces
      reach along it (the middle of the gap between them where they don't).
    - A line and a face, or two lines: where they meet, wherever that is. Two lines that never meet
      (skew) are measured at the first's nearest approach, the second carried over to it.
    - Each ray opens toward where most of its feature is: a face's area, a line's length.
    - `flip` measures the other way round the second feature: the supplement.

    Where the corner is off a feature, `phantoms` draw the feature on to it.
    """
    if first is None or second is None:
        return None
    carried: Optional[Tuple[V3, V3]] = None
    if isinstance(first, PlaneSpan) and isinstance(second, PlaneSpan):
        crossing = _plane_crossing(first, second)
        if crossing is None:
            return None
        along = crossing.direction
        vertex = _corner_on(crossing, first, second)
        # Square to the shared corner, and lying in its own face.
        rays = (_face_ray(_cross(along, first.facing), vertex, first),
                _face_ray(_cross(along, second.facing), vertex, second))
    elif isinstance(first, LineSpan) and isinstance(second, LineSpan):
        met = _lines_meet(first, second)
        if met is None:
            return None
        vertex, carried = met
        rays = (_ray_toward(first.along, vertex, first, second),
                _ray_toward(second.along, vertex if carried is None else carried[0], second, first))
    elif isinstance(first, LineSpan) and isinstance(second, PlaneSpan) or \
            isinstance(first, PlaneSpan) and isinstance(second, LineSpan):
        line, plane = (first, second) if isinstance(first, LineSpan) else (second, first)
        assert isinstance(line, LineSpan) and isinstance(plane, PlaneSpan)
        vertex = _line_meets_plane(line, plane, keep_on_line=False)
        if vertex is None:
            return None
        in_plane = _flatten_onto(line.along, plane.facing)
        if in_plane is None:
            return None
        line_ray = _ray_toward(line.along, vertex, line, plane)
        plane_ray = _face_ray(in_plane, vertex, plane)
        rays = (line_ray, plane_ray) if isinstance(first, LineSpan) else (plane_ray, line_ray)
    else:
        return None
    ray_from, ray_to = rays
    if ray_from is None or ray_to is None:
        return None
    # Before any flip: they say where each feature is from the corner, which a flip does not move.
    phantoms = _phantoms(first, vertex, ray_from) + _phantoms(second, vertex, ray_to)
    if carried is not None:
        phantoms += ((carried[0], carried[1]),)
    if flip:
        ray_to = -ray_to
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
    upright = _raw_cross(ray_from, ray_to)
    if not any(abs(part) > 1e-9 for part in upright):
        return None
    return AngleRays(vertex=_v3(vertex), opens_from=ray_from, opens_to=ray_to,
                     normal=_unit(upright), phantoms=tuple(phantoms))


#: Closer than this, in world units, two lines meet; and a corner is on a feature.
CORNER_TOLERANCE = 1e-6


def _corner_on(crossing: Line, first: 'PlaneSpan', second: 'PlaneSpan') -> V3:
    """Where on two faces' shared line the corner goes: the middle of where both reach along it, or
    of the gap between them. Without both regions, nearest the middle of the two faces' anchors."""
    along, through = crossing.direction, crossing.point
    reach_a, reach_b = (_reach_along(span.region, through, along) for span in (first, second))
    if reach_a is None or reach_b is None:
        return _closest_on_line((first.at + second.at) / 2, through, along)
    (low_a, high_a), (low_b, high_b) = reach_a, reach_b
    low, high = max(low_a, low_b), min(high_a, high_b)
    if low > high:  # apart along the line: the middle of the gap
        low, high = min(high_a, high_b), max(low_a, low_b)
    return _v3(through) + _v3(along) * ((low + high) / 2)


def _reach_along(region, through, along) -> Optional[Tuple[float, float]]:
    """How far a region's corners reach along a line, from its point."""
    stations = [_dot(corner - _v3(through), along) for polygon in region for corner in polygon]
    return (min(stations), max(stations)) if stations else None


def _face_ray(direction: VectorLike, vertex: VectorLike, plane: 'PlaneSpan') -> Optional[V3]:
    """A ray in a face's plane from the corner, turned toward the side holding most of the face."""
    unit = _unit(direction)
    if not any(abs(part) > 1e-9 for part in unit):
        return None
    if not plane.region:
        return _ray_toward(unit, vertex, plane)
    ahead, behind = _area_either_side(plane.region, _v3(vertex), unit, plane.facing)
    if abs(ahead - behind) <= 1e-12:
        return _ray_toward(unit, vertex, plane)
    return unit if ahead >= behind else -unit


def _area_either_side(region, vertex: V3, direction: V3, normal: V3) -> Tuple[float, float]:
    """A planar region's area ahead of the line through `vertex` square to `direction` (in its plane),
    and behind it."""
    across = _unit(_cross(normal, direction))
    ahead = behind = 0.0
    for polygon in region:
        flat = [(_dot(corner - vertex, direction), _dot(corner - vertex, across)) for corner in polygon]
        whole = _polygon_area(flat)
        front = _polygon_area(_clip_ahead(flat))
        ahead += front
        behind += max(0.0, whole - front)
    return ahead, behind


def _polygon_area(points) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))) / 2


def _clip_ahead(points):
    """The part of a 2D polygon where x >= 0."""
    kept = []
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        if x0 >= 0:
            kept.append((x0, y0))
        if (x0 >= 0) != (x1 >= 0):
            share = x0 / (x0 - x1)
            kept.append((0.0, y0 + (y1 - y0) * share))
    return kept


def _lines_meet(first: 'LineSpan', second: 'LineSpan') -> Optional[Tuple[V3, Optional[Tuple[V3, V3]]]]:
    """Where two lines meet, wherever along them; for two that never do (skew), the first's point of
    nearest approach, with the stretch from the second's to it -- what carries the second over."""
    stations = closest_stations(Line(direction=first.along, point=first.at),
                                Line(direction=second.along, point=second.at), eps=PARALLEL_EPSILON)
    if stations is None:
        return None
    on_first = first.at + first.along * stations[0]
    on_second = second.at + second.along * stations[1]
    gap = on_second - on_first
    if safe_zero_test_sq(_dot(gap, gap), eps=CORNER_TOLERANCE):
        return on_first, None
    return on_first, (on_second, on_first)


def _phantoms(span: MeasureSpan, vertex: VectorLike, ray: V3) -> Tuple[Tuple[V3, V3], ...]:
    """A feature drawn on to the corner, where the corner is off it."""
    vertex = _v3(vertex)
    if isinstance(span, LineSpan) and span.interval is not None:
        low, high = sorted(_dot(end - span.at, span.along) for end in span.ends_global())
        station = _dot(vertex - span.at, span.along)
        if station < low - CORNER_TOLERANCE:
            return ((span.at + span.along * low, vertex),)
        if station > high + CORNER_TOLERANCE:
            return ((span.at + span.along * high, vertex),)
        return ()
    if isinstance(span, PlaneSpan) and span.region:
        return _face_phantoms(span, vertex, ray)
    return ()


def _face_phantoms(span: 'PlaneSpan', vertex: V3, ray: V3) -> Tuple[Tuple[V3, V3], ...]:
    """A face swept on to its corner, in its own plane: from its two ends along the corner line,
    straight across to that line, and along it as far as the corner -- the part of the plane between
    the face and the corner, outlined. Nothing where the face already reaches the corner."""
    corner_line = _unit(_cross(span.facing, ray))
    corners = [corner for polygon in span.region for corner in polygon]
    across = [_dot(corner - vertex, ray) for corner in corners]
    along = [_dot(corner - vertex, corner_line) for corner in corners]
    on_line = lambda station: vertex + corner_line * station
    segments = []
    if min(across) > CORNER_TOLERANCE:
        # The face stops short of the corner line: its two far ends, carried across to it.
        for pick in (along.index(min(along)), along.index(max(along))):
            segments.append((corners[pick], on_line(along[pick])))
        low, high = min(min(along), 0.0), max(max(along), 0.0)
    else:
        # It reaches the corner line: only where the corner is past its end along it.
        low, high = min(along), max(along)
        if low - CORNER_TOLERANCE <= 0.0 <= high + CORNER_TOLERANCE:
            return ()
        low, high = (0.0, low) if 0.0 < low else (high, 0.0)
    if high - low > CORNER_TOLERANCE:
        segments.append((on_line(low), on_line(high)))
    return tuple(segments)


def _clamp_to(station: float, interval: Optional[Tuple[float, float]]) -> float:
    if interval is None:
        return station
    low, high = interval
    return max(low, min(high, station))


def _line_meets_plane(line: LineSpan, plane: PlaneSpan, keep_on_line: bool = True) -> Optional[V3]:
    """Where a line crosses a plane: kept within the line's interval, or (not `keep_on_line`) where
    it really does.

    None when it runs flat along the face and so never crosses -- the same
    contract as geometry.intersect_line_plane.
    """
    unit, normal = line.along, plane.facing
    if are_vectors_perpendicular(unit, normal, eps=PARALLEL_EPSILON):
        return None
    at = line.at
    step = _dot(plane.at - at, normal) / _dot(unit, normal)
    if keep_on_line:
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


def slide_axis(line: LineSpan) -> V3:
    """Which way a dimension between two lines slides: along the lines, the same way whichever end
    is first -- the first of x, y, z it has any of is positive."""
    run = line.along
    for part in run:
        if abs(float(part)) > 1e-9:
            return run if float(part) > 0 else run * -1
    return run


def distance_anchors(
    first: MeasureSpan,
    second: MeasureSpan,
    kind: MeasurementKind,
    view: Optional[ViewAxes] = None,
    along: Optional[float] = None,
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
    `along` (MeasurementPlacement.along) slides that station, along slide_axis;
    past the end of a line, the viewer draws the line on to its anchor.

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
        view = ViewAxes.from_wire(view)
        axis = _unit(view.right if named.endswith("horizontal_distance") else view.up)
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
    if isinstance(first, PlaneSpan) and isinstance(second, PlaneSpan):
        # Parallel faces. Either centroid will do, and the first is the one
        # the reader chose first.
        return (first.at, _foot_on_plane(second, first.at))
    if isinstance(first, PlaneSpan):
        from_second = _representative_point(second)
        return (_foot_on_plane(first, from_second), from_second)
    if isinstance(second, PlaneSpan):
        from_first = _representative_point(first)
        return (from_first, _foot_on_plane(second, from_first))

    if isinstance(first, PointSpan) and isinstance(second, PointSpan):
        return (first.at, second.at)
    if isinstance(first, PointSpan):
        assert isinstance(second, LineSpan)
        return (first.at, _foot_on(second, first.at))
    if isinstance(second, PointSpan):
        return (_foot_on(first, second.at), second.at)

    run = first.along
    first_low, first_high = _stations_global(first, run)
    second_low, second_high = _stations_global(second, run)
    low, high = max(first_low, second_low), min(first_high, second_high)
    if low <= high:
        station = (low + high) / 2
    else:
        # Nothing faces anything: go to the end of the first that is nearest.
        station = first_high if first_high < second_low else first_low
    if along is not None:
        # Slid by whoever placed it, both ends together, so it stays square to both.
        station += along * _dot(slide_axis(first), run)
    return (_at_station(first, run, station), _at_station(second, run, station))


def projected_kinds(
    one: Optional[Geometry], other: Optional[Geometry], look: VectorLike,
) -> Tuple[MeasurementKind, ...]:
    """Which kinds this pair admits, seen from `look`. Empty when none.

    The two halves put together: project both, then ask the table. This is the
    question "could these two be measured against each other from here", which
    is what decides whether a feature is worth preferring under the pointer.
    """
    return _kinds_admitted(project_geometry_for_measuring(one, look),
                           project_geometry_for_measuring(other, look),
                           MeasurementSpace.PROJECTED)


def three_d_kinds(
    one: Optional[Geometry], other: Optional[Geometry],
) -> Tuple[MeasurementKind, ...]:
    """Which kinds this pair admits in the 3D view. Empty when none.

    Nothing is projected first, which is the whole difference: the 3D camera
    belongs to the reader, so a face there is a plane however it is being seen.
    """
    return _kinds_admitted(one, other, MeasurementSpace.THREE_D)


def _kinds_admitted(
    one: Optional[Geometry], other: Optional[Geometry], space: MeasurementSpace,
) -> Tuple[MeasurementKind, ...]:
    """The table, asked about a pair that is already in the space it is asked in."""
    form_one, form_other = form_of(one), form_of(other)
    if form_one is None or form_other is None:
        return ()
    return kinds_for(form_one, form_other, space,
                     parallel=_are_parallel(one, other))


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
    def from_wire(cls, value) -> 'MeasurementPlaneSpec':
        """A plane as read from a file, or one already built.

        The same shape as MeasurementKind.from_wire and MeasurementPlacement's,
        and for the same reason: the field holds a plane, and saying so is only
        true if the conversion from the file's form happens somewhere that takes
        the file's form as its argument type.

        Absent on the wire reads as FROM_VIEWPORT, which is what every
        measurement written without one means.
        """
        if value is None:
            return FROM_VIEWPORT
        if isinstance(value, (cls, FromViewport)):
            return value
        if isinstance(value, Mapping):
            return cls(at=value.get("at"), normal=value.get("normal"))
        raise TypeError(f"Expected a plane or a mapping, got {type(value).__name__}")

    def as_wire(self) -> Dict[str, list]:
        return {"at": list(self.at), "normal": list(self.normal)}


@dataclass(frozen=True)
class FromViewport:
    """Take the plane from the viewport this measurement is drawn in.

    The other half of what a measurement's plane can be, and a named one. It was
    None, which made the field Optional and left the reader to know that a
    missing plane means something specific rather than nothing -- a drawing
    viewport has a locked camera, and a measurement in one is entitled to be
    read against it.

    Whether a measurement should be ALLOWED to say this is a separate question.
    A drawing viewport can always answer; the 3D view cannot, because its camera
    belongs to the reader and turns. The runner refuses a measurement that
    reaches it with neither -- see `no-plane` in _unplaceable_measurement.
    """

    def as_wire(self) -> None:
        """Absent on the wire, which is what the viewer already reads as this."""
        return None


#: The one instance there needs to be: it carries nothing.
FROM_VIEWPORT = FromViewport()

#: What a measurement's plane can be. Never None -- "the viewport's" is a case
#: with a name rather than a hole.
MeasurementPlaneSpec = Union[MeasurementPlane, FromViewport]


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
    #: How far the anchors have been slid along the two features, in WORLD units, from where they
    #: sit by default (the middle of where the features overlap). Only a distance between two lines
    #: can slide -- anywhere else the anchors are fixed by the features -- and it reads along
    #: slide_axis, so it does not depend on which end is which. None is the default.
    along: Optional[float] = None
    #: An angle measured the other way round its second feature: the supplement of the one it
    #: opens by default (angle_rays). Only an angle has one.
    flip: bool = False

    @classmethod
    def from_wire(cls, value) -> Optional['MeasurementPlacement']:
        """A placement as a file or the viewer has it: {"offset", "along", "flip"}, each optional."""
        if value is None or isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            offset, along = value.get("offset"), value.get("along")
            return cls(offset=None if offset is None else float(offset),
                       along=None if along is None else float(along),
                       flip=bool(value.get("flip", False)))
        raise TypeError(f"Expected a placement or a mapping, got {type(value).__name__}")


@dataclass(frozen=True)
class Measure:
    """A dimension between two features, drawn in one viewport.

    The kind IS part of identity, so the horizontal and the vertical between one
    pair are two dimensions and both show. The cost, which the editing flow has
    to know: changing a kind changes identity, so an override cannot edit a code
    measurement's kind in place -- say it as suppressing the original and adding
    the new one.

    Identity is the anchors, plus `measure_id` when the same pair is measured
    more than once in the same viewport -- deliberately not a position in a
    list, so that a measurement generated by an algorithm keeps whatever the
    drawings file has said about it when the algorithm next runs and emits a
    different number of them. It is scoped to the viewport, since that is where
    a measurement lives.
    """

    anchor_a: 'FeatureHandle'
    anchor_b: 'FeatureHandle'
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

    #: The plane this is taken and drawn on. Never None: taking the viewport's
    #: is FROM_VIEWPORT, a case with a name, which is also the default because
    #: an author writing a measurement has no plane to hand -- the anchors are
    #: not resolved yet and the normal is the viewport's camera.
    #:
    #: Not part of identity: the same two features measured on a different plane
    #: is the same measurement seen from elsewhere, and giving it a second
    #: identity would let a file hold both and draw them twice.
    plane: MeasurementPlaneSpec = FROM_VIEWPORT

    def wire_anchors(
        self, frame: 'Frame',
    ) -> Optional[Tuple[FeaturePath, FeaturePath, Optional[MeasurementPlacement]]]:
        """Both anchors as wire paths, in one order, with the placement to match.

        Measuring A to B is measuring B to A, so the pair is sorted and the offset
        negated if that swapped them. None if either anchor isn't in `frame`.

        NOTE Some day we may support asymmetric measurements.
        """
        from ..csg.feature_paths import to_feature_path

        first, second = to_feature_path(self.anchor_a, frame), to_feature_path(self.anchor_b, frame)
        if first is None or second is None:
            return None
        if first.sort_key <= second.sort_key:
            return first, second, self.placement
        placement = self.placement
        if placement is not None and placement.offset is not None:
            placement = replace(placement, offset=-placement.offset)
        return second, first, placement

    @staticmethod
    def kind_identity(kind: Optional['MeasurementKind']) -> Tuple:
        """
        """
        if kind is None:
            return ()
        wire = kind.as_wire()
        return (wire["operation"], wire["space"], wire["direction"])

    def pair_identity(self, frame: 'Frame') -> Optional[Tuple[Tuple, Tuple]]:
        """The two anchors' identities, in wire order. None if either isn't in `frame`."""
        anchors = self.wire_anchors(frame)
        if anchors is None:
            return None
        return (anchors[0].identity(), anchors[1].identity())

    def identity(self, frame: 'Frame') -> Optional[Tuple[Tuple, Tuple, Tuple, str]]:
        """The pair, the kind and the id. None if either anchor isn't in `frame`."""
        pair = self.pair_identity(frame)
        if pair is None:
            return None
        return (*pair, self.kind_identity(self.kind), str(self.measure_id or ""))


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
    frame: 'Frame',
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
    candidate_identity, candidate_pair = candidate.identity(frame), candidate.pair_identity(frame)
    existing_identity, existing_pair = existing.identity(frame), existing.pair_identity(frame)
    if (candidate_identity is None or candidate_pair is None
            or existing_identity is None or existing_pair is None):
        return False
    return does_override_identities(
        candidate_identity, candidate_pair, candidate_source,
        existing_identity, existing_pair, existing_source,
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
