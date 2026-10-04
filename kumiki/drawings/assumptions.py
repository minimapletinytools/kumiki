"""Rows a drawing takes as known without drawing them: square features, and features along the sheet's axes.

Add these to the known rows before solving. Each comes with a reason, so a report can say why
something counts as solved.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..csg.carriers import CarrierMap, Row
from ..csg.feature_paths import FeatureHandle
from ..rule import Transform
from .solve_recipe import VectorRow, combine, direction_motion, dot_vector_row, transform_vector_row

# How close |cos| must be to 1 for two directions to count as parallel, or to 0 for square.
ALIGNED = 1e-9


@dataclass(frozen=True)
class Assumption:
    """Rows taken as known, and why."""
    reason: str
    rows: Tuple[Row, ...]


@dataclass(frozen=True)
class _Directed:
    handle: FeatureHandle
    direction: np.ndarray
    change: VectorRow


def _directed(handles: Sequence[FeatureHandle], carriers: CarrierMap) -> List[_Directed]:
    """The handles that have a direction (a plane's normal, a line's direction), in world space."""
    directed = []
    for handle in handles:
        recipe = handle.feature.solve_recipe(handle.owner)
        if recipe is None:
            continue
        try:
            direction, change = direction_motion(recipe, carriers)
        except ValueError:
            continue
        rotation = np.array(handle.timber.transform.orientation.matrix.tolist(), dtype=float)
        directed.append(_Directed(handle, rotation @ direction, transform_vector_row(change, rotation)))
    return directed


def _across(direction: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Two unit vectors square to `direction` and to each other."""
    seed = np.eye(3)[int(np.argmin(np.abs(direction)))]
    first = np.cross(direction, seed)
    first /= np.linalg.norm(first)
    return first, np.cross(direction, first)


def _parallel_rows(a: _Directed, b: _Directed) -> Tuple[Row, ...]:
    """`b` stays parallel to `a`: b's change across a matches a's, up to their sign."""
    sign = 1.0 if float(a.direction @ b.direction) > 0 else -1.0
    return tuple(combine(dot_vector_row(b.change, axis), dot_vector_row(a.change, axis), -sign)
                 for axis in _across(a.direction))


def _square_row(a: _Directed, b: _Directed) -> Row:
    """`a` stays square to `b`: d(a · b) = 0."""
    return combine(dot_vector_row(a.change, b.direction), dot_vector_row(b.change, a.direction))


def _name(item: _Directed) -> str:
    return item.handle.feature.name


def square_assumptions(handles: Sequence[FeatureHandle], carriers: CarrierMap) -> List[Assumption]:
    """Features that are parallel or square (perpendicular) to each other stay that way.

    The handles' planes and lines are grouped, in the order given, into aligned sets: features
    whose directions all lie along one set of three square axes. Within a set, the features along
    each axis are chained by parallel rows, and one feature per axis is held square to one per
    other axis. That covers every relative angle in the set without pairing every feature.
    """
    sets: List[List[List[_Directed]]] = []  # set -> axis -> features along it
    for item in _directed(handles, carriers):
        placed = False
        for axes in sets:
            cosines = [abs(float(item.direction @ along[0].direction)) for along in axes]
            parallel = next((i for i, cosine in enumerate(cosines) if cosine > 1 - ALIGNED), None)
            if parallel is not None:
                axes[parallel].append(item)
                placed = True
            elif len(axes) < 3 and all(cosine < ALIGNED for cosine in cosines):
                axes.append([item])
                placed = True
            if placed:
                break
        if not placed:
            sets.append([[item]])

    assumptions = []
    for axes in sets:
        for along in axes:
            for a, b in zip(along, along[1:]):
                assumptions.append(Assumption(f"{_name(b)} parallel to {_name(a)}", _parallel_rows(a, b)))
        for i, first in enumerate(axes):
            for second in axes[i + 1:]:
                a, b = first[0], second[0]
                assumptions.append(Assumption(f"{_name(a)} square to {_name(b)}", (_square_row(a, b),)))
    return assumptions


def sheet_axis_assumptions(handles: Sequence[FeatureHandle], carriers: CarrierMap,
                           sheet: Transform) -> List[Assumption]:
    """Features along the sheet's right or up axis stay along it.

    `sheet`'s local x and y axes are the sheet's right and up, in world space. A plane whose normal,
    or a line whose direction, lies along one of them gets its direction fixed; where it sits
    along that axis stays unknown.
    """
    orientation = np.array(sheet.orientation.matrix.tolist(), dtype=float)
    assumptions = []
    for item in _directed(handles, carriers):
        axis: Optional[Tuple[str, np.ndarray]] = None
        for label, column in (("right", orientation[:, 0]), ("up", orientation[:, 1])):
            if abs(float(item.direction @ column)) > 1 - ALIGNED:
                axis = (label, column)
        if axis is None:
            continue
        label, column = axis
        rows = tuple(dot_vector_row(item.change, across) for across in _across(column))
        assumptions.append(Assumption(f"{_name(item)} along the sheet's {label}", rows))
    return assumptions
