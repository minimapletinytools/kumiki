"""Measuring: which kinds a pair of features can be measured as, where a dimension between them
attaches, and its value.

Parts are mirrored in kigumi/webview/measurements.js, checked by a test. Wire values (lists from
JSON) are converted at the edge; see VectorLike. Viewports and Drawing are in drawing.py.
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
    """Whether a measurement is taken projected onto a viewport or in 3D."""
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
    """What a feature acts as, after any projection, for measuring."""

    POINT = "point"
    LINE = "line"
    #: 3D only. A face, before projection.
    PLANE = "plane"
    #: Projected only. A face seen at an angle, which cannot be dimensioned.
    AREA = "area"


@dataclass(frozen=True)
class MeasurementKind:
    """What a dimension measures: operation, space and (for a distance) direction."""

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
        """Return the composed name, e.g. `projected_horizontal_distance`."""
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
        """Parse a kind from its composed name."""
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

#: Below this distance, in world units, a pair has nothing to dimension and is refused at the pick.
DEGENERATE_SEPARATION = 1e-6

#: Directions within this of parallel are treated as parallel. `kinds_for` applies it to a cosine
#: (about 8.1 degrees: no angle is offered); placing a corner applies it to a sine (about 0.57
#: degrees). The second must stay narrower; a test checks it.
PARALLEL_EPSILON = 1e-2


#: The camera frame a measurement is judged against when none is given.
DEFAULT_LOOK = create_v3(0, 0, -1)
DEFAULT_RIGHT = create_v3(1, 0, 0)
DEFAULT_UP = create_v3(0, 0, 1)


#: A V3, or a list or tuple from the wire.
VectorLike = Union[V3, Sequence[float]]


def _v3(vector: VectorLike) -> V3:
    """Return a wire vector (list, tuple or V3) as a V3."""
    return vector if isinstance(vector, Matrix) else create_v3(*(float(p) for p in vector))


def _unit(vector: VectorLike) -> V3:
    """Return `vector` normalized, or zero if it has no length."""
    found = _v3(vector)
    size = safe_norm(found)
    return found / size if size else create_v3(0, 0, 0)


def _dot(a: VectorLike, b: VectorLike) -> float:
    return safe_dot_product(_v3(a), _v3(b))


#: A feature's unbounded geometry in world space. The wire form is converted in kigumi/runner.py.
Geometry = Union[Point, Line, Plane]


def _anchor_of(geometry: Optional[Geometry]) -> Optional[V3]:
    """Return a point on the feature (its position, or the point a line or plane carries)."""
    if isinstance(geometry, Point):
        return geometry.position
    if isinstance(geometry, (Line, Plane)):
        return geometry.point
    return None


def project_geometry_for_measuring(
    geometry: Optional[Geometry], normal: VectorLike,
) -> Optional[Geometry]:
    """Return the feature as seen on a sheet facing `normal`, or None if it projects to an area.

    A point stays a point; an edge becomes a line (or a point end-on); a face seen edge-on becomes a line.
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
    """Return whether a feature is a point, line or plane, unprojected (as in the 3D view)."""
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
    """Return whether two features are parallel (a line and a plane: the line square to the normal), or None if either has no direction."""
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
    """Return the unnormalized cross product."""
    return cross_product(_v3(a), _v3(b))


def _cross(a: VectorLike, b: VectorLike) -> V3:
    """Return the cross product normalized. Use _raw_cross to test its length."""
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
        """Return the unit direction."""
        return _unit(self.direction)

    def ends_global(self) -> Tuple[V3, ...]:
        """Return the two endpoints."""
        return tuple(self.at + self.along * station for station in (self.interval or (0.0, 0.0)))


@dataclass(frozen=True)
class PlaneSpan:
    """A plane being measured to, through `at` with `normal` (3D only). `region` is the face's polygons, if known."""

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
        """Return the unit normal."""
        return _unit(self.normal)

    def ends_global(self) -> Tuple[V3, ...]:
        return (self.at,)


#: What a feature is, where a measurement is being taken.
MeasureSpan = Union[PointSpan, LineSpan, PlaneSpan]


def _stations_global(span: MeasureSpan, along: VectorLike) -> Tuple[float, float]:
    """Return how far a span reaches along `along`, as stations from the world origin."""
    reach = [_dot(end, along) for end in span.ends_global()]
    return (min(reach), max(reach))


def _at_station(span: Union[PointSpan, LineSpan], along: VectorLike, station: float) -> V3:
    """Return the point on a span at a station along `along`."""
    if isinstance(span, PointSpan):
        return span.at
    unit = span.along
    rate = _dot(unit, along)
    if abs(rate) < 1e-12:
        return span.at
    step = (station - _dot(span.at, along)) / rate
    return span.at + unit * step


def _foot_on(span: LineSpan, point: VectorLike) -> V3:
    """Return the foot of the perpendicular from `point` on a span, clamped to the span."""
    at, unit = span.at, span.along
    station = _dot(_v3(point) - at, unit)
    low, high = span.interval or (station, station)
    # Clamped: a dimension whose end floats off the end of a short edge points
    # at nothing, and the nearest place on the feature is the honest answer.
    station = max(low, min(high, station))
    return at + unit * station


def _representative_point(span: MeasureSpan) -> V3:
    """Return a point standing for a span: a point itself, or the middle of a line's extent."""
    if not isinstance(span, LineSpan):
        return span.at
    low, high = span.interval or (0.0, 0.0)
    unit = span.along
    middle = (low + high) / 2
    return span.at + unit * middle


def _foot_on_plane(span: PlaneSpan, point: VectorLike) -> V3:
    """Return the foot of the perpendicular from `point` on a plane (not clamped to the face)."""
    point, unit = _v3(point), span.facing
    gap = _dot(point - span.at, unit)
    return point - unit * gap


def _closest_on_line(point: VectorLike, at: VectorLike, direction: VectorLike) -> V3:
    """Return the point on a line nearest `point`."""
    at, unit = _v3(at), _unit(direction)
    step = _dot(_v3(point) - at, unit)
    return at + unit * step


def _plane_crossing(first: PlaneSpan, second: PlaneSpan) -> Optional[Line]:
    """Return the line two planes share, or None if they are near parallel."""
    # Both unit, so the raw cross's length is the sine between the planes.
    one, other = first.facing, second.facing
    # Squared length, so safe_zero_test_sq.
    along = _raw_cross(one, other)
    if safe_zero_test_sq(_dot(along, along), eps=PARALLEL_EPSILON):
        return None

    crossing = intersect_planes(Plane(normal=one, point=first.at),
                                Plane(normal=other, point=second.at))
    if crossing is None:
        return None
    return Line(point=crossing.point, direction=_unit(crossing.direction))


def _ray_toward(
    ray: VectorLike, vertex: VectorLike, span: MeasureSpan,
    other: Optional[MeasureSpan] = None,
) -> Optional[V3]:
    """Return a unit ray from `vertex` along `direction`, flipped to point toward the feature."""
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
    """A camera frame: look direction, and the sheet's right and up (used only by horizontal and vertical distances)."""

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
        """Return a ViewAxes from its wire form (or one already built)."""
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
    """Return the distance between two features, from the features alone; None for an angle or a pair with no distance."""
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
    """Return whether the pair has nothing between them to dimension (e.g. an arris lying on a face)."""
    gap = pair_separation(one, other, kind, view)
    return gap is not None and gap < DEGENERATE_SEPARATION


@dataclass(frozen=True)
class AngleRays:
    """Where an angle is drawn: a vertex, two unit rays and their plane's normal, in world space.

    The angle's value is read from the rays. `phantoms` are dashed segments extending each feature
    to the vertex.
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
    """Return where an angle between two features is drawn, or None if they make no corner.

    - Two faces: the vertex is on their planes' crossing line, in the middle of where both reach
      along it (or of the gap between them).
    - A line and a face, or two lines: where they meet. Skew lines are measured at the first's
      nearest approach, with the second carried over.
    - Each ray points toward the larger part of its feature (a face's area, a line's length).
    - `flip` reverses the second ray, measuring the supplement.
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
    # The plane both rays lie in. Raw cross, so near-parallel rays are refused.
    upright = _raw_cross(ray_from, ray_to)
    if not any(abs(part) > 1e-9 for part in upright):
        return None
    return AngleRays(vertex=_v3(vertex), opens_from=ray_from, opens_to=ray_to,
                     normal=_unit(upright), phantoms=tuple(phantoms))


#: Closer than this, in world units, two lines meet; and a corner is on a feature.
CORNER_TOLERANCE = 1e-6


def _corner_on(crossing: Line, first: 'PlaneSpan', second: 'PlaneSpan') -> V3:
    """Return the angle's vertex on `crossing`, the line where two faces' planes meet.

    It is the midpoint of the stretch of the line both faces' regions cover, or of the gap between
    them if they don't overlap. A face without a region falls back to the point on the line nearest
    the midpoint of the two anchors."""
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
    """Return the `(min, max)` station of a region's corners along a line, or None if empty."""
    stations = [_dot(corner - _v3(through), along) for polygon in region for corner in polygon]
    return (min(stations), max(stations)) if stations else None


def _face_ray(direction: VectorLike, vertex: VectorLike, plane: 'PlaneSpan') -> Optional[V3]:
    """Return `direction` as a unit ray from `vertex`, flipped to point toward the larger part of
    the face, or None if `direction` is zero."""
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
    """Return a planar region's area `(ahead, behind)` of the line through `vertex` square to
    `direction`."""
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
    """Return the part of a 2D polygon where x >= 0."""
    kept = []
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        if x0 >= 0:
            kept.append((x0, y0))
        if (x0 >= 0) != (x1 >= 0):
            share = x0 / (x0 - x1)
            kept.append((0.0, y0 + (y1 - y0) * share))
    return kept


def _lines_meet(first: 'LineSpan', second: 'LineSpan') -> Optional[Tuple[V3, Optional[Tuple[V3, V3]]]]:
    """Return `(vertex, carried)` for two lines, or None if parallel.

    `vertex` is the point on `first` nearest `second` (where they cross, if they do). `carried` is
    None when they cross; for skew lines it is the segment from `second`'s nearest point to `vertex`."""
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
    """Return dashed segments extending `span` to `vertex`, or none if the vertex is on it."""
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
    """Return dashed segments, in the face's plane, linking the face to the angle's vertex.

    `ray` is the face's angle ray from `vertex`; the corner line runs through `vertex` square to it.
    A face short of the corner line gets lines from its two outermost corners across to the line,
    plus the stretch of the line out to the vertex. A face touching the line gets only that stretch,
    and nothing if the vertex is already within the face."""
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
    """Return where a line crosses a plane, or None if parallel.

    With `keep_on_line`, the crossing is clamped to the line's interval.
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
    """Return the component of `direction` in the plane with normal `normal`."""
    unit, up = _unit(direction), _unit(normal)
    flat = unit - up * _dot(unit, up)
    if not any(abs(part) > 1e-9 for part in flat):
        return None
    return _unit(flat)


def angle_between(rays: Optional[AngleRays]) -> Optional[float]:
    """Return the angle between the rays in degrees."""
    if rays is None:
        return None
    facing = max(-1.0, min(1.0, _dot(_unit(rays.opens_from), _unit(rays.opens_to))))
    return math.degrees(math.acos(facing))


def slide_axis(line: LineSpan) -> V3:
    """Return the direction a dimension between two lines slides along, signed so its first non-zero component is positive."""
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
    """Return the two points where a distance between the features attaches.

    - Perpendicular, two parallel lines: both at one station along them, the middle of their
      overlap (or the end of the first nearest the second), shifted by `along`.
    - Perpendicular, otherwise: the end on the feature with less freedom (point, then line, then
      plane) stays, and the other is its foot on the other feature. Two points are themselves.
    - Horizontal or vertical: the first end stays and the second is projected onto the axis through it.

    TODO I think you can improve the logic a bit here in some cases but it's fine for now.
    """
    named = kind.name if hasattr(kind, "name") else str(kind)

    if named in ("projected_horizontal_distance", "projected_vertical_distance"):
        view = ViewAxes.from_wire(view)
        axis = _unit(view.right if named.endswith("horizontal_distance") else view.up)
        at = first.at
        offset = _dot(second.at - at, axis)
        return (first.at, at + axis * offset)

    # To a plane (3D only): anchor on the feature with less freedom, dropped square onto the other.
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
    """Return the kinds the pair admits when projected along `look`, best first."""
    return _kinds_admitted(project_geometry_for_measuring(one, look),
                           project_geometry_for_measuring(other, look),
                           MeasurementSpace.PROJECTED)


def three_d_kinds(
    one: Optional[Geometry], other: Optional[Geometry],
) -> Tuple[MeasurementKind, ...]:
    """Return the kinds the pair admits in 3D, best first."""
    return _kinds_admitted(one, other, MeasurementSpace.THREE_D)


def _kinds_admitted(
    one: Optional[Geometry], other: Optional[Geometry], space: MeasurementSpace,
) -> Tuple[MeasurementKind, ...]:
    """Return the kinds a pair already in the asked space admits."""
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
    """Return the kinds a pair admits, best first. Projected-space features must already be projected."""
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
    # Point to line, or two parallel lines.
    return (perpendicular,)


@dataclass(frozen=True)
class MeasurementPlane:
    """The plane a measurement is taken and drawn on. In a drawing viewport it should match the viewport's plane."""

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
        """Return a plane from its wire form; absent means FROM_VIEWPORT."""
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
    """Take the plane from the viewport the measurement is drawn in.

    Valid only in drawing viewports (locked camera); the runner refuses it in 3D.
    """

    def as_wire(self) -> None:
        """Return None (absent on the wire)."""
        return None


#: The one instance there needs to be: it carries nothing.
FROM_VIEWPORT = FromViewport()

#: What a measurement's plane can be. Never None -- "the viewport's" is a case
#: with a name rather than a hole.
MeasurementPlaneSpec = Union[MeasurementPlane, FromViewport]


@dataclass(frozen=True)
class MeasurementPlacement:
    """Where a dimension is drawn: `offset` from the features, `along` them, and `flip` for an angle's supplement."""

    #: How far the dimension line sits from the features, in world units, square to the run.
    #: None uses the viewport's default (in pixels).
    offset: Optional[float] = None
    #: How far the anchors are slid along slide_axis from their default, in world units. Only for a
    #: distance between two lines; None is the default.
    along: Optional[float] = None
    #: An angle measured the other way round its second feature: the supplement of the one it
    #: opens by default (angle_rays). Only an angle has one.
    flip: bool = False

    @classmethod
    def from_wire(cls, value) -> Optional['MeasurementPlacement']:
        """Return a placement from {"offset", "along", "flip"}, each optional."""
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
    """A dimension between two features in one viewport.

    Identity is the two anchors, the kind, and `measure_id` (for the same pair measured more than
    once). Changing a kind changes identity.
    """

    anchor_a: 'FeatureHandle'
    anchor_b: 'FeatureHandle'
    #: The kind, or None for the default. Parse a file's form with MeasurementKind.from_wire.
    kind: Optional[MeasurementKind] = None
    # the measurementId which allows multiple measurements with the same anchors and kind
    measure_id: Optional[MeasurementId] = None
    #: Where the dimension sits. Deliberately not part of identity: moving a
    #: dimension line is not measuring something else.
    placement: Optional[MeasurementPlacement] = None

    #: The plane it is taken and drawn on; FROM_VIEWPORT by default. Not part of identity.
    plane: MeasurementPlaneSpec = FROM_VIEWPORT

    def wire_anchors(
        self, frame: 'Frame',
    ) -> Optional[Tuple[FeaturePath, FeaturePath, Optional[MeasurementPlacement]]]:
        """Return both anchors as wire paths in sorted order, with the placement to match (offset negated if
        swapped), or None if either isn't in `frame`.

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
        if kind is None:
            return ()
        wire = kind.as_wire()
        return (wire["operation"], wire["space"], wire["direction"])

    def pair_identity(self, frame: 'Frame') -> Optional[Tuple[Tuple, Tuple]]:
        """Return the two anchors' identities in wire order, or None if either isn't in `frame`."""
        anchors = self.wire_anchors(frame)
        if anchors is None:
            return None
        return (anchors[0].identity(), anchors[1].identity())

    def identity(self, frame: 'Frame') -> Optional[Tuple[Tuple, Tuple, Tuple, str]]:
        """Return (pair, kind, measure_id), or None if either anchor isn't in `frame`."""
        pair = self.pair_identity(frame)
        if pair is None:
            return None
        return (*pair, self.kind_identity(self.kind), str(self.measure_id or ""))


class MeasurementSource(Enum):
    """Where a measurement came from; later tiers replace earlier ones."""

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
    """Return whether `candidate` replaces `existing`.

    Only a higher tier replaces. A FILE_OVERRIDE matches on everything including the kind; other
    tiers match on the two features alone.
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
    """does_override, for identities rather than Measures (the viewer reads plain dicts)."""
    if _SOURCE_RANK[candidate_source] <= _SOURCE_RANK[existing_source]:
        return False
    if candidate_source is MeasurementSource.FILE_OVERRIDE:
        return candidate_identity == existing_identity
    return candidate_pair == existing_pair
