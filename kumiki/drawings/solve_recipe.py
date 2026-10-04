"""Solve recipes as rows: how a feature moves when its carriers do.

A measurement to any feature becomes a row over its carriers' unknowns, via `measurement_row`.
The carriers themselves are in csg/carriers.py. See docs/internal/featuresolving-plan.md, Part 2 B.
"""

from dataclasses import dataclass
from typing import Callable, List, Mapping, Optional, Tuple, Union

import numpy as np

from ..csg.carriers import (BarrelCoord, Carrier, CarrierBarrel, CarrierLine, CarrierMap, CarrierPlane,
                            CarrierPoint, CarrierRef, Coord, LineCoord, Midplane, PlaneCoord, PointCoord, Recipe,
                            RecipePart, Row)
from ..geometry import Line, Plane, Point, intersect_line_plane, intersect_planes, perpendicular_axes
from ..rule import Matrix, V3


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


def _midplane_normal(part: Midplane, carriers: CarrierMap) -> Tuple[np.ndarray, float]:
    """The midplane's unit normal and |n_front - n_back|. It is (n_front - n_back) . x = d_front - d_back."""
    normals = []
    for ref in (part.front, part.back):
        carrier = carriers.carrier(ref)
        if not isinstance(carrier, CarrierPlane):
            raise ValueError("a midplane is between two planes")
        normals.append(_unit(_np(carrier.plane.normal)))
    difference = normals[0] - normals[1]
    length = float(np.linalg.norm(difference))
    if length < 1e-12:
        raise ValueError("a midplane's two planes face the same way")
    return difference / length, length


def _part_constraints(part: RecipePart, carriers: CarrierMap, at: np.ndarray) -> List[Constraint]:
    if isinstance(part, CarrierRef):
        return _carrier_constraints(part, carriers, at)
    # d((n_f - n_b) . x - (d_f - d_b)) = 0, so (n_f - n_b) . dx is the front's form less the back's.
    normal, length = _midplane_normal(part, carriers)
    [(_, front)] = _carrier_constraints(part.front, carriers, at)
    [(_, back)] = _carrier_constraints(part.back, carriers, at)
    return [(normal, _scale_row(combine(front, back, -1.0), 1.0 / length))]


def motion_along(recipe: Recipe, carriers: CarrierMap, at: V3, along: V3) -> Row:
    """The first-order motion of the feature at `at`, read along `along`, as a row over solving carrier unknowns.

    The motion is the smallest one that keeps `at` on the moved feature, so sliding along
    the feature doesn't count.
    """
    constraints = [c for part in recipe for c in _part_constraints(part, carriers, _np(at))]
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


# A vector whose components are rows: the first-order change of a 3-vector.
VectorRow = Tuple[Row, Row, Row]


def _vector_row(direction: np.ndarray, column: CarrierRef, coord: Coord) -> VectorRow:
    x, y, z = ({(column, coord): float(component)} if abs(component) > 1e-15 else {} for component in direction)
    return (x, y, z)


def _sum_vector_rows(*vectors: VectorRow) -> VectorRow:
    out: List[Row] = [{}, {}, {}]
    for vector in vectors:
        for k in range(3):
            out[k] = combine(out[k], vector[k])
    return (out[0], out[1], out[2])


def _scale_vector_row(vector: VectorRow, factor: float) -> VectorRow:
    return (_scale_row(vector[0], factor), _scale_row(vector[1], factor), _scale_row(vector[2], factor))


def cross_vector_row(vector: VectorRow, fixed: np.ndarray) -> VectorRow:
    """`vector × fixed`, for a varying vector and a fixed one."""
    x, y, z = vector
    return (combine(_scale_row(y, fixed[2]), _scale_row(z, fixed[1]), -1.0),
            combine(_scale_row(z, fixed[0]), _scale_row(x, fixed[2]), -1.0),
            combine(_scale_row(x, fixed[1]), _scale_row(y, fixed[0]), -1.0))


def dot_vector_row(vector: VectorRow, fixed: np.ndarray) -> Row:
    """`vector · fixed`, for a varying vector and a fixed one."""
    row: Row = {}
    for k in range(3):
        row = combine(row, _scale_row(vector[k], float(fixed[k])))
    return row


def transform_vector_row(vector: VectorRow, matrix: np.ndarray) -> VectorRow:
    """`matrix @ vector`, for a fixed matrix."""
    return (dot_vector_row(vector, matrix[0]), dot_vector_row(vector, matrix[1]), dot_vector_row(vector, matrix[2]))


def _scale_row(row: Row, factor: float) -> Row:
    return {key: value * factor for key, value in row.items()}


def _carrier_direction(ref: CarrierRef, carriers: CarrierMap) -> Tuple[np.ndarray, VectorRow]:
    column, carrier = carriers.canonical(ref), carriers.carrier(ref)
    if isinstance(carrier, CarrierPlane):
        normal = _unit(_np(carrier.plane.normal))
        first, second = _axes(normal)
        return normal, _sum_vector_rows(_vector_row(first, column, PlaneCoord.TILT_1),
                                        _vector_row(second, column, PlaneCoord.TILT_2))
    if isinstance(carrier, CarrierLine):
        direction = _unit(_np(carrier.line.direction))
        first, second = _axes(direction)
        return direction, _sum_vector_rows(_vector_row(first, column, LineCoord.TURN_1),
                                           _vector_row(second, column, LineCoord.TURN_2))
    raise ValueError(f"{type(carrier).__name__} has no direction")


def _part_direction(part: RecipePart, carriers: CarrierMap) -> Tuple[np.ndarray, VectorRow]:
    if isinstance(part, CarrierRef):
        return _carrier_direction(part, carriers)
    normal, length = _midplane_normal(part, carriers)
    (_, front), (_, back) = _carrier_direction(part.front, carriers), _carrier_direction(part.back, carriers)
    across = np.eye(3) - np.outer(normal, normal)
    change = _sum_vector_rows(front, _scale_vector_row(back, -1.0))
    return normal, _scale_vector_row(transform_vector_row(change, across), 1.0 / length)


def direction_motion(recipe: Recipe, carriers: CarrierMap) -> Tuple[np.ndarray, VectorRow]:
    """The feature's unit direction (a plane's normal, a line's direction) and its first-order change.

    For a line where two planes meet, the direction is n1 × n2 normalised.
    """
    if len(recipe) == 1:
        return _part_direction(recipe[0], carriers)
    if len(recipe) == 2:
        (n1, dn1), (n2, dn2) = (_part_direction(part, carriers) for part in recipe)
        cross = np.cross(n1, n2)
        length = float(np.linalg.norm(cross))
        if length < 1e-12:
            raise ValueError("the recipe's planes are parallel, so they meet in no line")
        direction = cross / length
        # d(n1 × n2) = dn1 × n2 - dn2 × n1, then keep the part across the direction.
        change = _sum_vector_rows(cross_vector_row(dn1, n2), _scale_vector_row(cross_vector_row(dn2, n1), -1.0))
        across = np.eye(3) - np.outer(direction, direction)
        return direction, _scale_vector_row(transform_vector_row(change, across), 1.0 / length)
    raise ValueError("a point has no direction")


def feature_dof_rows(recipe: Recipe, carriers: CarrierMap) -> List[Row]:
    """The feature's own DOFs as rows over the solving carriers' unknowns.

    A single carrier's DOFs are its unknowns. A point's are its motion along x, y and z; a line's
    its motion across it at two points.
    """
    if len(recipe) == 1 and isinstance(recipe[0], Midplane):
        plane = locate_recipe(recipe, carriers.carrier)
        assert isinstance(plane, Plane)
        normal = _unit(_np(plane.normal))
        points = [_np(plane.point) + offset for offset in (np.zeros(3), *_axes(normal))]
        return [motion_along(recipe, carriers, Matrix(point), Matrix(normal)) for point in points]
    if len(recipe) == 1:
        (ref,) = recipe
        assert isinstance(ref, CarrierRef)
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


def _part_geometry(part: RecipePart,
                   carrier_of: Callable[[CarrierRef], Carrier]) -> Optional[Union[Plane, Line, Point]]:
    if isinstance(part, CarrierRef):
        return _carrier_geometry(carrier_of(part))
    planes = [carrier.plane for carrier in (carrier_of(part.front), carrier_of(part.back))
              if isinstance(carrier, CarrierPlane)]
    if len(planes) != 2:
        return None
    normals = [_unit(_np(plane.normal)) for plane in planes]
    offsets = [float(n @ _np(plane.point)) for n, plane in zip(normals, planes)]
    normal, offset = normals[0] - normals[1], offsets[0] - offsets[1]
    if float(normal @ normal) < 1e-24:
        return None
    return Plane(normal=Matrix(_unit(normal)), point=Matrix(normal * offset / float(normal @ normal)))


def locate_recipe(
    recipe: Recipe,
    carrier_of: Callable[[CarrierRef], Carrier] = CarrierRef.carrier,
) -> Optional[Union[Plane, Line, Point]]:
    """The geometry the recipe builds: its one part, or where its parts meet."""
    located = [_part_geometry(part, carrier_of) for part in recipe]
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


def moved_by(carrier: Carrier, changes: Mapping[Coord, float]) -> Carrier:
    """The carrier with each of its unknowns changed by the given amount, all in its own frame."""
    def amount(coord: Coord) -> float:
        return float(changes.get(coord, 0.0))

    if isinstance(carrier, CarrierPlane):
        normal = _unit(_np(carrier.plane.normal))
        offset = float(normal @ _np(carrier.plane.point)) + amount(PlaneCoord.OFFSET)
        first, second = _axes(normal)
        moved = normal + amount(PlaneCoord.TILT_1) * first + amount(PlaneCoord.TILT_2) * second
        return CarrierPlane(Plane(normal=Matrix(moved), point=Matrix(moved * offset / float(moved @ moved))))

    if isinstance(carrier, CarrierPoint):
        return CarrierPoint(Matrix(_np(carrier.point) + np.array([amount(coord) for coord in PointCoord])))

    if isinstance(carrier, CarrierBarrel):
        return CarrierBarrel(axis=carrier.axis, radius=float(carrier.radius) + amount(BarrelCoord.RADIUS))

    line = carrier.line
    direction = _unit(_np(line.direction))
    first, second = _axes(direction)
    point = _np(line.point) + amount(LineCoord.SHIFT_1) * first + amount(LineCoord.SHIFT_2) * second
    moved = direction + amount(LineCoord.TURN_1) * first + amount(LineCoord.TURN_2) * second
    return CarrierLine(Line(direction=Matrix(moved), point=Matrix(point)))


def perturbed(carrier: Carrier, coord: Coord, step: float) -> Carrier:
    """The carrier with one unknown moved by `step`, for finite-difference checks."""
    return moved_by(carrier, {coord: step})
