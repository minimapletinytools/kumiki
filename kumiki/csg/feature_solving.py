"""Measurements on cut timbers, as rows over their solving carriers, and what they leave unsolved.

The interface layer of docs/internal/featuresolving-plan.md, Part 2 D: FeatureHandles and
measurements in, rows and remaining DOFs out. A measurement here is only what the solver needs --
which features, and where and along what it is read, in world space. Turning a drawing's Measure
into one (spans, sheets, views) is drawings/measure_solving.py. Each anchor's row is taken in its
own timber's local space, where its carriers are.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .carriers import CarrierMap, Recipe, Row
from .cutcsg import carrier_map
from .dof_solver import Remaining, remaining
from .feature_paths import FeatureHandle
from .required_features import FaceTest, on_finished_surface, required_features
from .solve_recipe import (combine, direction_motion, dot_vector_row, feature_dof_rows, motion_along,
                           transform_vector_row)
from ..geometry import Plane
from ..rule import Matrix, as_ndarray

if TYPE_CHECKING:
    from ..timber import CutTimber


@dataclass(frozen=True, eq=False)
class SolveDistance:
    """The distance from `at_a` on feature `a` to `at_b` on feature `b`, read along `along`. World space."""
    a: FeatureHandle
    b: FeatureHandle
    at_a: np.ndarray
    at_b: np.ndarray
    along: np.ndarray


@dataclass(frozen=True, eq=False)
class SolveAngle:
    """The angle between features `a` and `b`: in 3D, or as drawn on a sheet looking along `look` (world space)."""
    a: FeatureHandle
    b: FeatureHandle
    look: Optional[np.ndarray] = None


SolveMeasurement = Union[SolveDistance, SolveAngle]


def carrier_map_of(cut_timber: 'CutTimber', *more: 'CutTimber') -> CarrierMap:
    """The solving carriers of cut timbers' drawn trees, the trees their handles point into.

    Coincident planes are merged within a timber, never across timbers.
    """
    return CarrierMap.union([carrier_map(timber.render_timber_with_cuts_csg_local())
                             for timber in (cut_timber, *more)])


def _recipe(handle: FeatureHandle) -> Recipe:
    recipe = handle.feature.solve_recipe(handle.owner)
    if recipe is None:
        raise ValueError(f"{handle.feature.name!r} has no solve recipe yet")
    return recipe


def _distance_row(measure: SolveDistance, carriers: CarrierMap) -> Row:
    """How the distance from `at_a` to `at_b`, read along `along`, changes."""
    rows = []
    for handle, at in ((measure.a, measure.at_a), (measure.b, measure.at_b)):
        transform = handle.timber.transform
        rows.append(motion_along(_recipe(handle), carriers, transform.global_to_local(Matrix(as_ndarray(at))),
                                 transform.global_to_local_direction(Matrix(as_ndarray(measure.along)))))
    return combine(rows[1], rows[0], -1.0)


def _direction_in_world(handle: FeatureHandle, carriers: CarrierMap) -> Tuple[np.ndarray, Tuple[Row, Row, Row]]:
    direction, change = direction_motion(_recipe(handle), carriers)
    rotation = np.array(handle.timber.transform.orientation.matrix.tolist(), dtype=float)
    return rotation @ direction, transform_vector_row(change, rotation)


def _angle_row(measure: SolveAngle, carriers: CarrierMap) -> Row:
    """How the cosine of the angle between the two features changes.

    In 3D, between their normals or directions. On a sheet, between the lines they draw as.
    """
    look = None if measure.look is None else as_ndarray(measure.look)
    sides = []
    for handle in (measure.a, measure.b):
        direction, change = _direction_in_world(handle, carriers)
        if look is not None:
            if isinstance(handle.feature.locate_simple_unbounded(handle.owner), Plane):
                # A face draws as the line its plane meets the sheet in: normal × look.
                drawn = np.cross(direction, look)
                drawn_change = tuple(dot_vector_row(change, np.cross(look, axis)) for axis in np.eye(3))
            else:
                across = np.eye(3) - np.outer(look, look)
                drawn = across @ direction
                drawn_change = transform_vector_row(change, across)
            direction, change = drawn, drawn_change
        length = float(np.linalg.norm(direction))
        if length < 1e-9:
            raise ValueError("a feature seen end-on, or a face seen square on, has no direction on the sheet")
        sides.append((direction, change, length))

    (a, change_a, length_a), (b, change_b, length_b) = sides
    cosine = float(a @ b) / (length_a * length_b)
    row = combine(dot_vector_row(change_a, b), dot_vector_row(change_b, a))
    row = {key: value / (length_a * length_b) for key, value in row.items()}
    row = combine(row, dot_vector_row(change_a, a * cosine / (length_a * length_a)), -1.0)
    return combine(row, dot_vector_row(change_b, b * cosine / (length_b * length_b)), -1.0)


def feature_handle_dof_rows(handle: FeatureHandle, carriers: CarrierMap) -> List[Row]:
    """The feature's own DOFs as rows. See solve_recipe.feature_dof_rows."""
    return feature_dof_rows(_recipe(handle), carriers)


def measure_row(measure: SolveMeasurement, carriers: CarrierMap) -> Row:
    """How a measurement's value changes with the solving carriers' unknowns.

    `carriers` must cover every timber the measurement touches.
    """
    if isinstance(measure, SolveAngle):
        return _angle_row(measure, carriers)
    return _distance_row(measure, carriers)


class Solve:
    """What one solve over some cut timbers works out once and asks for again: their carriers, and
    each feature's own DOF rows. Lasts as long as the solve; the timbers must not change under it."""

    def __init__(self, cut_timbers: Sequence['CutTimber']):
        self.cut_timbers: Tuple['CutTimber', ...] = tuple(cut_timbers)
        self.carriers = carrier_map_of(*self.cut_timbers)
        self._dof_rows_cache: Dict[FeatureHandle, List[Row]] = {}

    def dof_rows(self, handle: FeatureHandle) -> List[Row]:
        """The feature's own DOFs as rows (feature_handle_dof_rows)."""
        if handle not in self._dof_rows_cache:
            self._dof_rows_cache[handle] = feature_handle_dof_rows(handle, self.carriers)
        return self._dof_rows_cache[handle]

    def measure_row(self, measure: SolveMeasurement) -> Row:
        return measure_row(measure, self.carriers)


def _carriers_for(handles: Sequence[FeatureHandle], cut_timbers: Sequence['CutTimber']) -> CarrierMap:
    """Carriers of every timber the handles are on, each found among `cut_timbers`."""
    touched: List['CutTimber'] = []
    for handle in handles:
        if any(cut.timber is handle.timber for cut in touched):
            continue
        found = next((cut for cut in cut_timbers if cut.timber is handle.timber), None)
        if found is None:
            raise ValueError(f"{handle.feature.name!r} is on a timber not in cut_timbers")
        touched.append(found)
    return carrier_map_of(*touched)


def _known_rows(
    measures: Sequence[SolveMeasurement], known: Sequence[FeatureHandle], carriers: CarrierMap,
) -> List[Row]:
    rows: List[Row] = [row for handle in known for row in feature_handle_dof_rows(handle, carriers)]
    return rows + [measure_row(measure, carriers) for measure in measures]


def _handles(measures: Sequence[SolveMeasurement], known: Sequence[FeatureHandle]) -> List[FeatureHandle]:
    return [*known, *(handle for measure in measures for handle in (measure.a, measure.b))]


def remaining_dofs(
    target: FeatureHandle,
    measures: Sequence[SolveMeasurement],
    known: Sequence[FeatureHandle],
    cut_timbers: Sequence['CutTimber'],
) -> Remaining:
    """What of `target` the measurements leave unsolved, given the `known` features.

    `cut_timbers` must hold every timber the target, measurements and known features are on.
    """
    carriers = _carriers_for([target, *_handles(measures, known)], cut_timbers)
    return remaining(_known_rows(measures, known, carriers), feature_handle_dof_rows(target, carriers))


@dataclass(frozen=True)
class FeatureReport:
    """One target feature, and what of it is still unsolved. `remaining` is None if it has no recipe."""
    handle: FeatureHandle
    remaining: Optional[Remaining]


@dataclass(frozen=True)
class SolveReport:
    """What the measurements leave unsolved: per target feature, and in total."""
    features: List[FeatureReport]
    total: Remaining


def solve_report(
    targets: Sequence[FeatureHandle],
    measures: Sequence[SolveMeasurement],
    known: Sequence[FeatureHandle],
    cut_timbers: Sequence['CutTimber'],
) -> SolveReport:
    """Remaining DOFs of each target, and of all of them together, given the `known` features.

    Targets may be on any number of timbers. `cut_timbers` must hold every timber the targets,
    measurements and known features are on; a frame's `cut_timbers` will do.
    """
    carriers = _carriers_for([*targets, *_handles(measures, known)], cut_timbers)
    known_rows = _known_rows(measures, known, carriers)
    reports: List[FeatureReport] = []
    target_rows: List[Row] = []
    for handle in targets:
        recipe = handle.feature.solve_recipe(handle.owner)
        if recipe is None:
            reports.append(FeatureReport(handle, None))
            continue
        rows = feature_dof_rows(recipe, carriers)
        target_rows += rows
        reports.append(FeatureReport(handle, remaining(known_rows, rows)))
    return SolveReport(features=reports, total=remaining(known_rows, target_rows))


def required_targets(cut_timber: 'CutTimber', face_test: FaceTest = on_finished_surface) -> List[FeatureHandle]:
    """The features `required_features` finds on `cut_timber`, as targets for `solve_report`."""
    return [required.handle for required in required_features(cut_timber, face_test)]
