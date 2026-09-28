"""Solve recipes: each feature built from its primitive's independent geometry.

A primitive names its independent pieces as `SolveEntity`s (`CutCSG.solve_entities`),
and each feature says how it is built from them (`CSGFeature.solve_recipe`). A
measurement to any feature then becomes a row over the entities' unknowns, via
`motion_along`. See docs/internal/featuresolving-plan.md, Part 2 B.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Optional, Tuple, Union

import numpy as np

from .geometry import Line, Plane, Point, intersect_line_plane, intersect_planes, perpendicular_axes, planes_are_coincident
from .rule import Matrix, Numeric, V3

if TYPE_CHECKING:
    from .cutcsg import CutCSG, FeatureKey


@dataclass(frozen=True)
class PlaneEntity:
    """A plane. Unknowns: offset, then tilts about its perpendicular_axes."""
    plane: Plane

    COORDS = ("offset", "tilt_1", "tilt_2")


@dataclass(frozen=True)
class LineEntity:
    """A line. Unknowns: shifts along its perpendicular_axes, then turns toward them about `line.point`."""
    line: Line

    COORDS = ("shift_1", "shift_2", "turn_1", "turn_2")


@dataclass(frozen=True)
class PointEntity:
    """A point. Unknowns: x, y, z."""
    point: V3

    COORDS = ("x", "y", "z")


@dataclass(frozen=True)
class CylinderEntity:
    """A cylinder's barrel. Unknowns: its axis as a LineEntity, then its radius."""
    axis: Line
    radius: Numeric

    COORDS = LineEntity.COORDS + ("radius",)


SolveEntity = Union[PlaneEntity, LineEntity, PointEntity, CylinderEntity]


@dataclass(frozen=True, eq=False)
class EntityRef:
    """One entity of one primitive: the primitive, compared by identity, and the entity's key."""
    owner: 'CutCSG'
    local: 'FeatureKey'

    def entity(self) -> SolveEntity:
        return self.owner.solve_entities()[self.local]

    def __eq__(self, other) -> bool:
        return isinstance(other, EntityRef) and self.owner is other.owner and self.local == other.local

    def __hash__(self) -> int:
        return hash((id(self.owner), self.local))


@dataclass(frozen=True)
class Is:
    """The feature is this entity."""
    entity: EntityRef


@dataclass(frozen=True)
class AxisOf:
    """The feature is the axis of this cylinder entity."""
    cylinder: EntityRef


@dataclass(frozen=True)
class Meet:
    """The feature is where all of these meet: two planes in a line, three in a point, a line and a plane in a point."""
    parts: Tuple['Recipe', ...]


Recipe = Union[Is, AxisOf, Meet]

# One unknown: a solving entity and the index of one of its COORDS.
Column = Tuple[EntityRef, int]
Row = Dict[Column, float]


def entity_refs(recipe: Recipe) -> List[EntityRef]:
    """Every entity the recipe is built from."""
    if isinstance(recipe, Is):
        return [recipe.entity]
    if isinstance(recipe, AxisOf):
        return [recipe.cylinder]
    return [ref for part in recipe.parts for ref in entity_refs(part)]


class EntityMap:
    """Every primitive entity mapped to the solving entity whose columns it uses.

    Coincident planes, facing either way, share the first one's columns.
    """

    def __init__(self, owned: Iterable[Tuple['CutCSG', Dict['FeatureKey', SolveEntity]]]):
        self._canonical: Dict[EntityRef, EntityRef] = {}
        self._entities: Dict[EntityRef, SolveEntity] = {}
        planes: List[Tuple[EntityRef, Plane]] = []
        for owner, entities in owned:
            for local, entity in entities.items():
                ref = EntityRef(owner, local)
                self._entities[ref] = entity
                canonical = ref
                if isinstance(entity, PlaneEntity):
                    canonical = next(
                        (other for other, plane in planes if planes_are_coincident(plane, entity.plane)),
                        ref)
                    if canonical is ref:
                        planes.append((ref, entity.plane))
                self._canonical[ref] = canonical

    def canonical(self, ref: EntityRef) -> EntityRef:
        return self._canonical[ref]

    def entity(self, ref: EntityRef) -> SolveEntity:
        """The solving entity's geometry, which is what the columns are measured against."""
        return self._entities[self._canonical[ref]]

    def solving_entities(self) -> List[EntityRef]:
        return list(dict.fromkeys(self._canonical.values()))

    def __contains__(self, ref: EntityRef) -> bool:
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


def _line_constraints(column: EntityRef, line: Line, at: np.ndarray) -> List[Constraint]:
    direction = _unit(_np(line.direction))
    first, second = _axes(direction)
    along = float((at - _np(line.point)) @ direction)
    return [
        (first, {(column, 0): 1.0, (column, 2): along}),
        (second, {(column, 1): 1.0, (column, 3): along}),
    ]


def _constraints(recipe: Recipe, entities: EntityMap, at: np.ndarray) -> List[Constraint]:
    if isinstance(recipe, Meet):
        return [c for part in recipe.parts for c in _constraints(part, entities, at)]

    ref = recipe.cylinder if isinstance(recipe, AxisOf) else recipe.entity
    column = entities.canonical(ref)
    entity = entities.entity(ref)

    if isinstance(recipe, AxisOf):
        if not isinstance(entity, CylinderEntity):
            raise ValueError(f"{ref} is not a cylinder, so it has no axis")
        return _line_constraints(column, entity.axis, at)

    if isinstance(entity, PlaneEntity):
        normal = _unit(_np(entity.plane.normal))
        first, second = _axes(normal)
        return [(normal, {(column, 0): 1.0, (column, 1): -float(at @ first), (column, 2): -float(at @ second)})]

    if isinstance(entity, LineEntity):
        return _line_constraints(column, entity.line, at)

    if isinstance(entity, PointEntity):
        return [(np.eye(3)[k], {(column, k): 1.0}) for k in range(3)]

    # The barrel moves radially: with its axis, plus its radius.
    direction = _unit(_np(entity.axis.direction))
    offset = at - _np(entity.axis.point)
    radial = offset - direction * float(offset @ direction)
    if np.linalg.norm(radial) < 1e-12:
        raise ValueError("a point on the axis is not on the barrel")
    radial = _unit(radial)
    row: Row = {(column, 4): 1.0}
    for normal, form in _line_constraints(column, entity.axis, at):
        for key, value in form.items():
            row[key] = row.get(key, 0.0) + value * float(radial @ normal)
    return [(radial, row)]


def motion_along(recipe: Recipe, entities: EntityMap, at: V3, along: V3) -> Row:
    """The first-order motion of the feature at `at`, read along `along`, as a row over solving entity unknowns.

    The motion is the smallest one that keeps `at` on the moved feature, so sliding along
    the feature doesn't count.
    """
    constraints = _constraints(recipe, entities, _np(at))
    normals = np.array([normal for normal, _ in constraints])
    gram = normals @ normals.T
    if abs(np.linalg.det(gram)) < 1e-12:
        raise ValueError("the recipe's parts don't meet in a single line or point")
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


def locate_recipe(
    recipe: Recipe,
    entity_of: Callable[[EntityRef], SolveEntity] = EntityRef.entity,
) -> Optional[Union[Plane, Line, Point]]:
    """The geometry the recipe builds."""
    if isinstance(recipe, AxisOf):
        entity = entity_of(recipe.cylinder)
        return entity.axis if isinstance(entity, CylinderEntity) else None
    if isinstance(recipe, Is):
        entity = entity_of(recipe.entity)
        if isinstance(entity, PlaneEntity):
            return entity.plane
        if isinstance(entity, LineEntity):
            return entity.line
        if isinstance(entity, PointEntity):
            return Point(position=entity.point)
        return None

    located = [locate_recipe(part, entity_of) for part in recipe.parts]
    planes = [g for g in located if isinstance(g, Plane)]
    lines = [g for g in located if isinstance(g, Line)]
    if len(planes) == 2 and not lines:
        return intersect_planes(planes[0], planes[1])
    if len(planes) == 3 and not lines:
        return intersect_line_plane(intersect_planes(planes[0], planes[1]), planes[2])
    if len(planes) == 1 and len(lines) == 1:
        return intersect_line_plane(lines[0], planes[0])
    return None


def perturbed(entity: SolveEntity, coord: int, step: float) -> SolveEntity:
    """The entity with one unknown moved by `step`, for finite-difference checks."""
    if isinstance(entity, PlaneEntity):
        normal = _unit(_np(entity.plane.normal))
        offset = float(normal @ _np(entity.plane.point))
        first, second = _axes(normal)
        moved = normal + step * (first if coord == 1 else second if coord == 2 else 0.0)
        if coord == 0:
            offset += step
        return PlaneEntity(Plane(normal=Matrix(moved), point=Matrix(moved * offset / float(moved @ moved))))

    if isinstance(entity, PointEntity):
        return PointEntity(Matrix(_np(entity.point) + step * np.eye(3)[coord]))

    line = entity.axis if isinstance(entity, CylinderEntity) else entity.line
    if isinstance(entity, CylinderEntity) and coord == 4:
        return CylinderEntity(axis=line, radius=float(entity.radius) + step)
    direction = _unit(_np(line.direction))
    first, second = _axes(direction)
    point, moved = _np(line.point), direction
    shift = first if coord in (0, 2) else second
    if coord in (0, 1):
        point = point + step * shift
    else:
        moved = direction + step * shift
    new_line = Line(direction=Matrix(moved), point=Matrix(point))
    if isinstance(entity, CylinderEntity):
        return CylinderEntity(axis=new_line, radius=entity.radius)
    return LineEntity(new_line)
