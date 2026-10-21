"""Measurements on cut timbers as rows over their solving carriers, and the DOFs they leave free.

FeatureHandles and world-space measurements in, rows and remaining DOFs out. Converting a drawing's
Measure into a SolveMeasurement is in drawings/measure_solving.py.
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
    """Return the carrier map of the cut timbers' drawn trees; coincident planes merge only within a timber."""
    return CarrierMap.union([carrier_map(timber.render_timber_with_cuts_csg_local())
                             for timber in (cut_timber, *more)])


def _recipe(handle: FeatureHandle) -> Recipe:
    recipe = handle.feature.solve_recipe(handle.owner)
    if recipe is None:
        raise ValueError(f"{handle.feature.name!r} has no solve recipe yet")
    return recipe


def _distance_row(measure: SolveDistance, carriers: CarrierMap) -> Row:
    """Return the row for the distance measurement."""
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
    """Return the row for the cosine of the angle: in 3D, or between the lines drawn on a sheet."""
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
    """Return the feature's own DOFs as rows (solve_recipe.feature_dof_rows)."""
    return feature_dof_rows(_recipe(handle), carriers)


def measure_row(measure: SolveMeasurement, carriers: CarrierMap) -> Row:
    """Return the measurement's row over the unknowns; `carriers` must cover both its timbers."""
    if isinstance(measure, SolveAngle):
        return _angle_row(measure, carriers)
    return _distance_row(measure, carriers)


class Solve:
    """Carriers and cached DOF rows for one solve over some cut timbers."""

    def __init__(self, cut_timbers: Sequence['CutTimber']):
        self.cut_timbers: Tuple['CutTimber', ...] = tuple(cut_timbers)
        self.carriers = carrier_map_of(*self.cut_timbers)
        self._dof_rows_memo: Dict[FeatureHandle, List[Row]] = {}

    def dof_rows(self, handle: FeatureHandle) -> List[Row]:
        """Return the feature's own DOFs as rows, cached."""
        if handle not in self._dof_rows_memo:
            self._dof_rows_memo[handle] = feature_handle_dof_rows(handle, self.carriers)
        return self._dof_rows_memo[handle]

    def measure_row(self, measure: SolveMeasurement) -> Row:
        return measure_row(measure, self.carriers)

    def known_rows(self, measures: Sequence[SolveMeasurement], known: Sequence[FeatureHandle]) -> List[Row]:
        """Return the rows the measurements and `known` features fix."""
        return [row for handle in known for row in self.dof_rows(handle)] + [self.measure_row(m) for m in measures]

    def remaining(self, target: FeatureHandle, measures: Sequence[SolveMeasurement],
                  known: Sequence[FeatureHandle]) -> Remaining:
        """Return the DOFs of `target` left free by the measurements and `known` features."""
        return remaining(self.known_rows(measures, known), self.dof_rows(target))

    def report(self, targets: Sequence[FeatureHandle], measures: Sequence[SolveMeasurement],
               known: Sequence[FeatureHandle]) -> 'SolveReport':
        """Return the free DOFs of each target, and of all together, given the measurements and `known` features."""
        known_rows = self.known_rows(measures, known)
        reports: List[FeatureReport] = []
        target_rows: List[Row] = []
        for handle in targets:
            if handle.feature.solve_recipe(handle.owner) is None:
                reports.append(FeatureReport(handle, None))
                continue
            rows = self.dof_rows(handle)
            target_rows += rows
            reports.append(FeatureReport(handle, remaining(known_rows, rows)))
        return SolveReport(features=reports, total=remaining(known_rows, target_rows))


def _solve_for(handles: Sequence[FeatureHandle], cut_timbers: Sequence['CutTimber']) -> Solve:
    """Return a Solve over just the timbers `handles` are on, looked up in `cut_timbers`."""
    touched: List['CutTimber'] = []
    for handle in handles:
        if any(cut.timber is handle.timber for cut in touched):
            continue
        found = next((cut for cut in cut_timbers if cut.timber is handle.timber), None)
        if found is None:
            raise ValueError(f"{handle.feature.name!r} is on a timber not in cut_timbers")
        touched.append(found)
    return Solve(touched)


def _handles(measures: Sequence[SolveMeasurement], known: Sequence[FeatureHandle]) -> List[FeatureHandle]:
    return [*known, *(handle for measure in measures for handle in (measure.a, measure.b))]


def remaining_dofs(
    target: FeatureHandle,
    measures: Sequence[SolveMeasurement],
    known: Sequence[FeatureHandle],
    cut_timbers: Sequence['CutTimber'],
) -> Remaining:
    """Solve.remaining, over the timbers involved. `cut_timbers` must hold all of them."""
    return _solve_for([target, *_handles(measures, known)], cut_timbers).remaining(target, measures, known)


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
    """Solve.report, over the timbers involved. `cut_timbers` must hold all of them; a frame's will do."""
    return _solve_for([*targets, *_handles(measures, known)], cut_timbers).report(targets, measures, known)


def required_targets(cut_timber: 'CutTimber', face_test: FaceTest = on_finished_surface) -> List[FeatureHandle]:
    """Return the handles of `required_features(cut_timber)`, as targets for `solve_report`."""
    return [required.handle for required in required_features(cut_timber, face_test)]
