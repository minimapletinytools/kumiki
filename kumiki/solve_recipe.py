"""Solve recipes: each feature as the carriers it lies on.

A primitive names the planes, lines and surfaces its faces and axes lie on as carriers
(`CutCSG.carriers`), and each feature names the carriers that produce it
(`CSGFeature.solve_recipe`). A measurement to any feature then becomes a row over the
carriers' unknowns, via `measurement_row`. See docs/internal/featuresolving-plan.md, Part 2 B.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, ClassVar, Dict, List, Optional, Tuple, Type, Union

import numpy as np

from .geometry import Line, Plane, Point, intersect_line_plane, intersect_planes, perpendicular_axes, planes_are_coincident
from .rule import Matrix, Numeric, V3

if TYPE_CHECKING:
    from .cutcsg import CutCSG, FeatureKey


class PlaneCoord(Enum):
    """A plane's unknowns: its offset, and tilts toward its perpendicular_axes."""
    OFFSET = 0
    TILT_1 = 1
    TILT_2 = 2


class LineCoord(Enum):
    """A line's unknowns: shifts along its perpendicular_axes, and turns toward them about `line.point`."""
    SHIFT_1 = 0
    SHIFT_2 = 1
    TURN_1 = 2
    TURN_2 = 3


class PointCoord(Enum):
    X = 0
    Y = 1
    Z = 2


class BarrelCoord(Enum):
    RADIUS = 0


Coord = Union[PlaneCoord, LineCoord, PointCoord, BarrelCoord]


@dataclass(frozen=True)
class CarrierPlane:
    plane: Plane

    COORDS: ClassVar[Type[PlaneCoord]] = PlaneCoord


@dataclass(frozen=True)
class CarrierLine:
    line: Line

    COORDS: ClassVar[Type[LineCoord]] = LineCoord


@dataclass(frozen=True)
class CarrierPoint:
    point: V3

    COORDS: ClassVar[Type[PointCoord]] = PointCoord


@dataclass(frozen=True)
class CarrierBarrel:
    """A cylinder's barrel around the CarrierLine at `axis` on the same primitive."""
    axis: 'FeatureKey'
    radius: Numeric

    COORDS: ClassVar[Type[BarrelCoord]] = BarrelCoord


Carrier = Union[CarrierPlane, CarrierLine, CarrierPoint, CarrierBarrel]


@dataclass(frozen=True, eq=False)
class CarrierRef:
    """One carrier of one primitive: the primitive, compared by identity, and the carrier's key."""
    owner: 'CutCSG'
    local: 'FeatureKey'

    def carrier(self) -> Carrier:
        return self.owner.carriers()[self.local]

    def __eq__(self, other) -> bool:
        return isinstance(other, CarrierRef) and self.owner is other.owner and self.local == other.local

    def __hash__(self) -> int:
        return hash((id(self.owner), self.local))


# List of references to the carriers producing the feature in question, which is the carrier
# itself for non-derived features.
Recipe = Tuple[CarrierRef, ...]

# One unknown: a solving carrier and one of its COORDS.
Column = Tuple[CarrierRef, Coord]
Row = Dict[Column, float]


def merge_coincident_planes(carriers: Dict[CarrierRef, Carrier]) -> Dict[CarrierRef, CarrierRef]:
    """Each carrier's solving carrier: coincident planes, facing either way, share the first one; anything else is its own."""
    canonical: Dict[CarrierRef, CarrierRef] = {}
    planes: List[Tuple[CarrierRef, Plane]] = []
    for ref, carrier in carriers.items():
        canonical[ref] = ref
        if not isinstance(carrier, CarrierPlane):
            continue
        same = next((other for other, plane in planes if planes_are_coincident(plane, carrier.plane)), None)
        if same is None:
            planes.append((ref, carrier.plane))
        else:
            canonical[ref] = same
    return canonical


class CarrierMap:
    """Every primitive carrier mapped to the solving carrier whose columns it uses."""

    def __init__(self, carriers: Dict[CarrierRef, Carrier], canonical: Dict[CarrierRef, CarrierRef]):
        self._carriers = carriers
        self._canonical = canonical

    def canonical(self, ref: CarrierRef) -> CarrierRef:
        return self._canonical[ref]

    def carrier(self, ref: CarrierRef) -> Carrier:
        """The solving carrier's geometry, which is what the columns are measured against."""
        return self._carriers[self._canonical[ref]]

    def solving_carriers(self) -> List[CarrierRef]:
        return list(dict.fromkeys(self._canonical.values()))

    def carrier_rows(self, ref: CarrierRef) -> List[Row]:
        """One row per unknown of the solving carrier `ref` maps to."""
        column = self.canonical(ref)
        coords: List[Coord] = list(type(self.carrier(ref)).COORDS)
        return [{(column, coord): 1.0} for coord in coords]

    def unknowns(self) -> List[Row]:
        """One row per unknown of every solving carrier."""
        return [row for ref in self.solving_carriers() for row in self.carrier_rows(ref)]

    def __contains__(self, ref: CarrierRef) -> bool:
        return ref in self._canonical


def _np(vector: V3) -> np.ndarray:
    return np.array([float(vector[i, 0]) for i in range(3)])


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _axes(direction: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    first, second = perpendicular_axes(Matrix(direction))
    return _np(first), _np(second)


# One first-order constraint on how a point x of the feature moves: normal . dx = form.
Constraint = Tuple[np.ndarray, Row]


def _line_constraints(column: CarrierRef, line: Line, at: np.ndarray) -> List[Constraint]:
    direction = _unit(_np(line.direction))
    first, second = _axes(direction)
    along = float((at - _np(line.point)) @ direction)
    return [
        (first, {(column, LineCoord.SHIFT_1): 1.0, (column, LineCoord.TURN_1): along}),
        (second, {(column, LineCoord.SHIFT_2): 1.0, (column, LineCoord.TURN_2): along}),
    ]


def _carrier_constraints(ref: CarrierRef, carriers: CarrierMap, at: np.ndarray) -> List[Constraint]:
    column = carriers.canonical(ref)
    carrier = carriers.carrier(ref)

    if isinstance(carrier, CarrierPlane):
        normal = _unit(_np(carrier.plane.normal))
        first, second = _axes(normal)
        return [(normal, {(column, PlaneCoord.OFFSET): 1.0,
                          (column, PlaneCoord.TILT_1): -float(at @ first),
                          (column, PlaneCoord.TILT_2): -float(at @ second)})]

    if isinstance(carrier, CarrierLine):
        return _line_constraints(column, carrier.line, at)

    if isinstance(carrier, CarrierPoint):
        return [(np.eye(3)[coord.value], {(column, coord): 1.0}) for coord in PointCoord]

    # The barrel moves radially: with its axis, plus its radius.
    axis_ref = CarrierRef(ref.owner, carrier.axis)
    axis = carriers.carrier(axis_ref)
    assert isinstance(axis, CarrierLine)
    direction = _unit(_np(axis.line.direction))
    offset = at - _np(axis.line.point)
    radial = offset - direction * float(offset @ direction)
    if np.linalg.norm(radial) < 1e-12:
        raise ValueError("a point on the axis is not on the barrel")
    radial = _unit(radial)
    row: Row = {(column, BarrelCoord.RADIUS): 1.0}
    for normal, form in _line_constraints(carriers.canonical(axis_ref), axis.line, at):
        for key, value in form.items():
            row[key] = row.get(key, 0.0) + value * float(radial @ normal)
    return [(radial, row)]


def motion_along(recipe: Recipe, carriers: CarrierMap, at: V3, along: V3) -> Row:
    """The first-order motion of the feature at `at`, read along `along`, as a row over solving carrier unknowns.

    The motion is the smallest one that keeps `at` on the moved feature, so sliding along
    the feature doesn't count.
    """
    constraints = [c for ref in recipe for c in _carrier_constraints(ref, carriers, _np(at))]
    normals = np.array([normal for normal, _ in constraints])
    gram = normals @ normals.T
    if abs(np.linalg.det(gram)) < 1e-12:
        raise ValueError("the recipe's carriers don't meet in a single line or point")
    weights = np.linalg.solve(gram, normals @ _np(along))
    row: Row = {}
    for weight, (_, form) in zip(weights, constraints):
        for key, value in form.items():
            row[key] = row.get(key, 0.0) + float(weight) * value
    return {key: value for key, value in row.items() if abs(value) > 1e-12}


def combine(first: Row, second: Row, sign: float = 1.0) -> Row:
    """`first + sign * second`."""
    row = dict(first)
    for key, value in second.items():
        row[key] = row.get(key, 0.0) + sign * value
    return {key: value for key, value in row.items() if abs(value) > 1e-12}


@dataclass(frozen=True)
class Anchor:
    """Where a measurement attaches to a feature."""
    recipe: Recipe
    at: V3


@dataclass(frozen=True)
class DistanceMeasurement:
    """The distance from `start` to `end`, read along `along`."""
    start: Anchor
    end: Anchor
    along: V3


def measurement_row(measurement: DistanceMeasurement, carriers: CarrierMap) -> Row:
    """How the measured distance changes with the solving carriers' unknowns."""
    end = motion_along(measurement.end.recipe, carriers, measurement.end.at, measurement.along)
    start = motion_along(measurement.start.recipe, carriers, measurement.start.at, measurement.along)
    return combine(end, start, -1.0)


def feature_dof_rows(recipe: Recipe, carriers: CarrierMap) -> List[Row]:
    """The feature's own DOFs as rows over the solving carriers' unknowns.

    A single carrier's DOFs are its unknowns. A point's are its motion along x, y and z; a line's
    its motion across it at two points.
    """
    if len(recipe) == 1:
        (ref,) = recipe
        rows = carriers.carrier_rows(ref)
        carrier = carriers.carrier(ref)
        if isinstance(carrier, CarrierBarrel):
            rows += carriers.carrier_rows(CarrierRef(ref.owner, carrier.axis))
        return rows

    located = locate_recipe(recipe, carriers.carrier)
    if isinstance(located, Point):
        return [motion_along(recipe, carriers, located.position, Matrix(axis)) for axis in np.eye(3)]
    if isinstance(located, Line):
        direction = _unit(_np(located.direction))
        ends = (_np(located.point), _np(located.point) + direction)
        return [motion_along(recipe, carriers, Matrix(end), Matrix(axis))
                for end in ends for axis in _axes(direction)]
    raise ValueError("the recipe's carriers don't meet in a single line or point")


def _carrier_geometry(carrier: Carrier) -> Optional[Union[Plane, Line, Point]]:
    if isinstance(carrier, CarrierPlane):
        return carrier.plane
    if isinstance(carrier, CarrierLine):
        return carrier.line
    if isinstance(carrier, CarrierPoint):
        return Point(position=carrier.point)
    return None


def locate_recipe(
    recipe: Recipe,
    carrier_of: Callable[[CarrierRef], Carrier] = CarrierRef.carrier,
) -> Optional[Union[Plane, Line, Point]]:
    """The geometry the recipe builds: its one carrier, or where its carriers meet."""
    located = [_carrier_geometry(carrier_of(ref)) for ref in recipe]
    if len(located) == 1:
        return located[0]
    planes = [g for g in located if isinstance(g, Plane)]
    lines = [g for g in located if isinstance(g, Line)]
    if len(planes) == 2 and not lines:
        return intersect_planes(planes[0], planes[1])
    if len(planes) == 3 and not lines:
        return intersect_line_plane(intersect_planes(planes[0], planes[1]), planes[2])
    if len(planes) == 1 and len(lines) == 1:
        return intersect_line_plane(lines[0], planes[0])
    return None


def perturbed(carrier: Carrier, coord: Coord, step: float) -> Carrier:
    """The carrier with one unknown moved by `step`, for finite-difference checks."""
    if isinstance(carrier, CarrierPlane):
        normal = _unit(_np(carrier.plane.normal))
        offset = float(normal @ _np(carrier.plane.point))
        first, second = _axes(normal)
        moved = normal + step * (first if coord is PlaneCoord.TILT_1 else second if coord is PlaneCoord.TILT_2 else 0.0)
        if coord is PlaneCoord.OFFSET:
            offset += step
        return CarrierPlane(Plane(normal=Matrix(moved), point=Matrix(moved * offset / float(moved @ moved))))

    if isinstance(carrier, CarrierPoint):
        return CarrierPoint(Matrix(_np(carrier.point) + step * np.eye(3)[coord.value]))

    if isinstance(carrier, CarrierBarrel):
        return CarrierBarrel(axis=carrier.axis, radius=float(carrier.radius) + step)

    line = carrier.line
    direction = _unit(_np(line.direction))
    first, second = _axes(direction)
    point, moved = _np(line.point), direction
    shift = first if coord in (LineCoord.SHIFT_1, LineCoord.TURN_1) else second
    if coord in (LineCoord.SHIFT_1, LineCoord.SHIFT_2):
        point = point + step * shift
    else:
        moved = direction + step * shift
    return CarrierLine(Line(direction=Matrix(moved), point=Matrix(point)))
