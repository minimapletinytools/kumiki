"""Auto dimensioning: pick measurements one at a time until the target features are solved.

Every pick is one measurement, so it removes one unknown at most and the count can't choose
between candidates. A Policy does: ordered preferences, compared one after another, and rules
that are kept unless nothing would be left to pick.

Temporary, and expected to be renamed.
"""

import warnings
from dataclasses import dataclass, field
from functools import cached_property
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..csg.carriers import CarrierMap, Row
from ..csg.feature_paths import FeatureHandle
from ..geometry import Line, Plane
from ..timber_features import TimberFeature
from .dof_solver import remaining
from .drawing import Measure, MeasurementKind, ViewAxes
from .feature_solving import feature_handle_dof_rows, measure_row

PERPENDICULAR = MeasurementKind.parse("projected_perpendicular_distance")


@dataclass(frozen=True)
class Candidate:
    """A measurement that could be added, in the view named `view`, with its length.

    Its row is worked out only when asked for: that is the dear part, and most candidates are never
    looked at closely enough to need one.
    """
    view: str
    measure: Measure
    length: float
    axes: ViewAxes = field(repr=False, compare=False)
    carriers: CarrierMap = field(repr=False, compare=False)

    @cached_property
    def row(self) -> Optional[Row]:
        """What the measurement fixes (measure_row), or None where it cannot be written as a row."""
        try:
            return measure_row(self.measure, self.carriers, self.axes)
        except ValueError:
            return None


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


class UnsolvedFeaturesWarning(UserWarning):
    """auto_dimension left features unsolved: nothing its candidates measure fixes them."""


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
    columns = list(dict.fromkeys(column for row in (*known_rows, *target_rows) for column in row))
    index = {column: i for i, column in enumerate(columns)}
    known_matrix, target_matrix = _matrix(known_rows, columns), _matrix(target_rows, columns)
    tolerance = 1e-9 * max(float(np.linalg.norm(np.vstack([known_matrix, target_matrix]), 2)), 1.0)

    # Everything works on rows with what is known projected out; a pick removes its direction
    # from every target row (incremental Gram-Schmidt). `known` is an orthonormal basis of what is
    # known and picked, which a candidate is projected off when it is looked at.
    target_left = target_matrix
    known = np.zeros((0, len(columns)))
    if len(known_rows):
        _, values, basis = np.linalg.svd(known_matrix, full_matrices=False)
        known = basis[values > tolerance]
        target_left = target_matrix - target_matrix @ known.T @ known

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

    def helpful_direction(candidate: Candidate, unsolved: np.ndarray) -> Optional[np.ndarray]:
        """The unit direction the candidate adds to what is known, if all of it is still unsolved."""
        row = candidate.row
        if row is None:
            return None
        vector, outside = np.zeros(len(columns)), 0.0
        for column, value in row.items():
            if column in index:
                vector[index[column]] = value
            else:
                outside += value * value  # an unknown no target asks about, which nothing projects off
        vector = vector - known.T @ (known @ vector)
        size = float(np.sqrt(vector @ vector + outside))
        if size < tolerance:
            return None
        direction = vector / size
        # It helps exactly when what it adds to the known rows lies in what is still unsolved.
        off = direction - unsolved.T @ (unsolved @ direction)
        return direction if float(np.sqrt(off @ off + outside / (size * size))) <= 1e-6 else None

    picks: List[Pick] = []
    context = PickContext(solved=solved, picks=picks)
    available = list(range(len(candidates)))
    left_before = len(unsolved_basis())
    while True:
        unsolved = unsolved_basis()
        if not len(unsolved):
            break
        # In the policy's order, so the first that helps (and passes the rules) is the pick: only the
        # candidates down to it need rows. Ties go to the earlier candidate.
        scored = sorted(available, key=lambda i: (
            tuple(criterion(candidates[i], context) for criterion in policy.prefer), i))
        chosen: Optional[Tuple[int, np.ndarray, bool]] = None
        first_helpful: Optional[Tuple[int, np.ndarray, bool]] = None
        for i in scored:
            direction = helpful_direction(candidates[i], unsolved)
            if direction is None:
                continue
            if all(rule(candidates[i], context) == 0 for rule in policy.rules):
                chosen = (i, direction, False)
                break
            if first_helpful is None:
                first_helpful = (i, direction, True)
        chosen = chosen or first_helpful
        if chosen is None:
            break
        index_, direction, broke_rules = chosen
        score = tuple(criterion(candidates[index_], context) for criterion in policy.prefer)
        target_left = target_left - np.outer(target_left @ direction, direction)
        known = np.vstack([known, direction])
        available.remove(index_)
        picks.append(Pick(candidates[index_], score, broke_rules=broke_rules))

    left_after = remaining([*known_rows, *(pick.candidate.row or {} for pick in picks)], target_rows).count
    unsolved_targets = [handle for handle in targets if not solved(handle)]
    if unsolved_targets:
        # Often a feature no view shows -- a blind mortise's bottom is hidden in every one -- or
        # one no measurement kind takes, such as a bore's radius.
        warnings.warn(
            f"{len(unsolved_targets)} feature(s) left unsolved: "
            + ", ".join(f"{handle.timber.ticket.path}:{handle.feature.name}" for handle in unsolved_targets),
            UnsolvedFeaturesWarning, stacklevel=2)
    return AutoDimensioning(picks=picks, unsolved=unsolved_targets, left_before=left_before, left_after=left_after)


def _on_sheet(handle: FeatureHandle, look: np.ndarray) -> Optional[Tuple]:
    """How a feature draws, looking along `look`, in world space.

    ("line", in-sheet unit normal, offset along it) for a face seen edge-on or a line lying along
    the sheet; ("point", position) for a line seen end-on; None for anything seen at an angle.
    """
    located = handle.feature.locate_simple_unbounded(handle.owner)
    transform = handle.timber.transform
    if isinstance(located, Plane):
        normal, point = located.normal, located.point
    elif isinstance(located, Line):
        normal, point = located.direction, located.point
    else:
        return None
    direction = np.array([float(v) for v in transform.local_to_global_direction(normal)])
    direction /= np.linalg.norm(direction)
    at = np.array([float(v) for v in transform.local_to_global(point)])
    along_look = float(direction @ look)
    if isinstance(located, Line):
        if abs(abs(along_look) - 1) < 1e-9:
            return ("point", at)
        if abs(along_look) > 1e-9:
            return None
        direction = np.cross(direction, look)
        direction /= np.linalg.norm(direction)
    elif abs(along_look) > 1e-9:
        return None
    return ("line", direction, float(direction @ at))


def _separation(one: Tuple, other: Tuple) -> Optional[float]:
    """Perpendicular distance on the sheet between two drawn features, or None if there is none to take."""
    if one[0] == "point" and other[0] == "point":
        return None
    if one[0] == "point":
        one, other = other, one
    if other[0] == "point":
        return abs(float(one[1] @ other[1]) - one[2])
    alignment = float(one[1] @ other[1])
    if abs(abs(alignment) - 1) > 1e-9:
        return None
    return abs(one[2] - alignment * other[2])


def sheet_candidates(
    anchors: Mapping[str, Sequence[FeatureHandle]], carriers: CarrierMap, views: Mapping[str, ViewAxes],
) -> List[Candidate]:
    """Every perpendicular dimension a view can draw between two of the anchors it can see.

    Between two parallel lines on the sheet (a face seen edge-on, a line lying along the sheet), or
    from a point (a line seen end-on) to a line. `anchors` are each view's own: what it can see of
    them (visibility.visible_by_view), so nothing is measured in a view that hides it.
    """
    candidates = []
    for view, axes in views.items():
        look = np.array([float(v) for v in axes.look])
        look /= np.linalg.norm(look)
        drawn = [(handle, _on_sheet(handle, look)) for handle in anchors.get(view, ())]
        drawn = [(handle, shape) for handle, shape in drawn if shape is not None]
        for i, (a, shape_a) in enumerate(drawn):
            for b, shape_b in drawn[i + 1:]:
                length = _separation(shape_a, shape_b)
                if length is None or length < 1e-9:
                    continue
                candidates.append(Candidate(view, Measure(a, b, kind=PERPENDICULAR), length, axes, carriers))
    return candidates
