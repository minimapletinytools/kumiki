"""Auto dimensioning: pick measurements one at a time until the target features are solved.

Every pick is one measurement, so it removes one unknown at most and the count can't choose
between candidates. A Policy does: ordered preferences, compared one after another, and rules
that are kept unless nothing would be left to pick.

Temporary, and expected to be renamed.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..csg.carriers import CarrierMap, Row
from ..csg.feature_paths import FeatureHandle
from ..geometry import Plane
from ..timber_features import TimberFeature
from .dof_solver import remaining
from .drawing import Measure, MeasurementKind, ViewAxes
from .feature_solving import feature_handle_dof_rows, measure_row

PERPENDICULAR = MeasurementKind.parse("projected_perpendicular_distance")


@dataclass(frozen=True)
class Candidate:
    """A measurement that could be added, in the view named `view`, with its row and length."""
    view: str
    measure: Measure
    row: Row
    length: float


@dataclass(frozen=True)
class PickContext:
    """What a criterion may ask about while choosing."""
    solved: Callable[[FeatureHandle], bool]
    picks: Sequence['Pick']


#: Scores a candidate; lower is better.
Criterion = Callable[[Candidate, PickContext], float]


def is_reference(handle: FeatureHandle) -> bool:
    """Whether the feature is one of its timber's reference features, or a face of a reference edge."""
    name = handle.feature.name.split(".", 1)[-1]
    for reference in getattr(handle.timber.ticket, "reference_features", ()) or ():
        if name in {face.name.lower() for face in reference.long_faces_it_rests_on()}:
            return True
        if name == _CENTERPLANE_NAMES.get(reference):
            return True
    return False


_CENTERPLANE_NAMES = {
    TimberFeature.RIGHT_LEFT_CENTER_PLANE: "centerplane_left_right",
    TimberFeature.FRONT_BACK_CENTER_PLANE: "centerplane_front_back",
}


def _ends(candidate: Candidate) -> Tuple[FeatureHandle, FeatureHandle]:
    return candidate.measure.anchor_a, candidate.measure.anchor_b


def from_reference(candidate: Candidate, context: PickContext) -> float:
    """Measured from a reference feature of its own timber."""
    return 0.0 if any(is_reference(end) for end in _ends(candidate)) else 1.0


def from_solved(candidate: Candidate, context: PickContext) -> float:
    """Measured from something already solved, so dimensions chain."""
    return 0.0 if any(context.solved(end) for end in _ends(candidate)) else 1.0


def perfect_over_rough(candidate: Candidate, context: PickContext) -> float:
    """How many ends are rough faces."""
    return float(sum(end.feature.name.startswith("rough.") for end in _ends(candidate)))


def shortest(candidate: Candidate, context: PickContext) -> float:
    return candidate.length


@dataclass(frozen=True)
class Policy:
    """How to choose among the measurements that would help.

    `prefer` is compared in order: the first criterion that tells two candidates apart decides.
    `rules` must score 0 to be picked, unless no helpful candidate would pass them, in which case
    that one pick ignores them and says so.
    """
    prefer: Sequence[Criterion] = (from_reference, perfect_over_rough, from_solved, shortest)
    rules: Sequence[Criterion] = ()


DEFAULT_POLICY = Policy()


@dataclass(frozen=True)
class Pick:
    candidate: Candidate
    score: Tuple[float, ...]
    broke_rules: bool = False


@dataclass(frozen=True)
class AutoDimensioning:
    picks: List[Pick]
    unsolved: List[FeatureHandle]
    #: Unknowns before any pick, and left after the last.
    left_before: int
    left_after: int


def _matrix(rows: Sequence[Row], columns: list) -> np.ndarray:
    index = {column: i for i, column in enumerate(columns)}
    out = np.zeros((len(rows), len(columns)))
    for r, row in enumerate(rows):
        for column, value in row.items():
            out[r, index[column]] = value
    return out


def _key(handle: FeatureHandle) -> Tuple[int, str]:
    return id(handle.owner), handle.feature.name


def auto_dimension(
    candidates: Sequence[Candidate],
    targets: Sequence[FeatureHandle],
    known_rows: Sequence[Row],
    carriers: CarrierMap,
    policy: Policy = DEFAULT_POLICY,
) -> AutoDimensioning:
    """Pick from `candidates` until `targets` are solved or nothing more helps.

    `known_rows` is what is already known: fixed features' rows, assumptions.
    """
    target_rows = [row for handle in targets for row in feature_handle_dof_rows(handle, carriers)]
    columns = list(dict.fromkeys(column for row in (*known_rows, *target_rows, *(c.row for c in candidates))
                                 for column in row))
    known_matrix, target_matrix = _matrix(known_rows, columns), _matrix(target_rows, columns)
    candidate_matrix = _matrix([candidate.row for candidate in candidates], columns)
    tolerance = 1e-9 * max(float(np.linalg.norm(np.vstack([known_matrix, target_matrix]), 2)), 1.0)

    # Everything works on rows with what is known projected out; a pick removes its direction
    # from every matrix (incremental Gram-Schmidt).
    target_left, candidate_left = target_matrix, candidate_matrix
    if len(known_rows):
        _, values, basis = np.linalg.svd(known_matrix, full_matrices=False)
        basis = basis[values > tolerance]
        target_left = target_matrix - target_matrix @ basis.T @ basis
        candidate_left = candidate_matrix - candidate_matrix @ basis.T @ basis

    spans: Dict[Tuple[int, str], slice] = {}
    start = 0
    for handle in targets:
        count = len(feature_handle_dof_rows(handle, carriers))
        spans[_key(handle)] = slice(start, start + count)
        start += count

    def solved(handle: FeatureHandle) -> bool:
        span = spans.get(_key(handle))
        return span is None or float(np.linalg.norm(target_left[span])) < tolerance

    def unsolved_basis() -> np.ndarray:
        _, values, directions = np.linalg.svd(target_left, full_matrices=False)
        return directions[values > tolerance]

    picks: List[Pick] = []
    context = PickContext(solved=solved, picks=picks)
    available = list(range(len(candidates)))
    left_before = len(unsolved_basis())
    while True:
        unsolved = unsolved_basis()
        if not len(unsolved):
            break
        helpful: List[Tuple[int, np.ndarray]] = []
        for index in available:
            residual = candidate_left[index]
            size = float(np.linalg.norm(residual))
            if size < tolerance:
                continue
            direction = residual / size
            # It helps exactly when what it adds to the known rows lies in what is still unsolved.
            if float(np.linalg.norm(direction - unsolved.T @ (unsolved @ direction))) <= 1e-6:
                helpful.append((index, direction))
        if not helpful:
            break
        passing = [(i, d) for i, d in helpful
                   if all(rule(candidates[i], context) == 0 for rule in policy.rules)]
        pool = passing or helpful
        index, direction = min(
            pool, key=lambda item: tuple(criterion(candidates[item[0]], context) for criterion in policy.prefer))
        score = tuple(criterion(candidates[index], context) for criterion in policy.prefer)
        target_left = target_left - np.outer(target_left @ direction, direction)
        candidate_left = candidate_left - np.outer(candidate_left @ direction, direction)
        available.remove(index)
        picks.append(Pick(candidates[index], score, broke_rules=not passing))

    left_after = remaining([*known_rows, *(pick.candidate.row for pick in picks)], target_rows).count
    return AutoDimensioning(picks=picks, unsolved=[handle for handle in targets if not solved(handle)],
                            left_before=left_before, left_after=left_after)


def _plane_in_world(handle: FeatureHandle) -> Optional[Tuple[np.ndarray, float]]:
    """(unit normal, offset along it) of a planar feature, in world space."""
    plane = handle.feature.locate_simple_unbounded(handle.owner)
    if not isinstance(plane, Plane):
        return None
    transform = handle.timber.transform
    normal = np.array([float(v) for v in transform.local_to_global_direction(plane.normal)])
    normal /= np.linalg.norm(normal)
    point = np.array([float(v) for v in transform.local_to_global(plane.point)])
    return normal, float(normal @ point)


def plane_pair_candidates(
    anchors: Sequence[FeatureHandle], carriers: CarrierMap, views: Mapping[str, ViewAxes],
) -> List[Candidate]:
    """Every perpendicular dimension between two parallel planes seen edge-on, in each view."""
    candidates = []
    planes = [(handle, _plane_in_world(handle)) for handle in anchors]
    planes = [(handle, plane) for handle, plane in planes if plane is not None]
    for view, axes in views.items():
        look = np.array([float(v) for v in axes.look])
        edge_on = [(handle, plane) for handle, plane in planes if abs(float(plane[0] @ look)) < 1e-9]
        for i, (a, (normal_a, offset_a)) in enumerate(edge_on):
            for b, (normal_b, offset_b) in edge_on[i + 1:]:
                if abs(abs(float(normal_a @ normal_b)) - 1) > 1e-9:
                    continue
                length = abs(offset_a - float(normal_a @ normal_b) * offset_b)
                if length < 1e-9:
                    continue
                measure = Measure(a, b, kind=PERPENDICULAR)
                try:
                    row = measure_row(measure, carriers, axes)
                except ValueError:
                    continue
                candidates.append(Candidate(view, measure, row, length))
    return candidates
