"""Auto dimensioning: add measurements one at a time until the target features are solved.

Each pick removes at most one unknown, so a Policy chooses between candidates: ordered
preferences, and rules that hold unless no candidate would pass them.

Temporary, and expected to be renamed.
"""

import warnings
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..csg.assumptions import Assumption
from ..csg.carriers import CarrierMap, CarrierPlane, CarrierRef, Row
from ..csg.dof_solver import rank_svd, remaining, rows_matrix
from ..csg.cutcsg import (CutCSG, DerivedEdgeFeature, EdgeFeature, FaceFeature, OwnedFeatureHit, derive_edge_hits,
                         shared_ancestor)
from ..csg.feature_extent import extents_of
from ..csg.feature_solving import Solve
from ..csg.feature_paths import FeatureHandle, hit_identity
from ..csg.identity_memo import memo_by_identity
from ..geometry import Line, Plane
from ..timber_features import TimberFeature
from ..rule import as_ndarray, create_v3, unit_ndarray
from .measure import Measure, MeasurementKind, MeasurementOperation, ViewAxes
from .measure_solving import DrawingSolve
from .sheet_shape import SQUARE_TO_VIEW, SheetLine, SheetPoint, SheetShape, sheet_gap, sheet_shape

if TYPE_CHECKING:
    from ..timber import CutTimber

PERPENDICULAR = MeasurementKind.parse("projected_perpendicular_distance")
HORIZONTAL = MeasurementKind.parse("projected_horizontal_distance")
VERTICAL = MeasurementKind.parse("projected_vertical_distance")
ANGLE = MeasurementKind.parse("projected_angle")
#: Closer than this on the sheet, in world units, two drawn features are one on top of the other.
COINCIDENT = 1e-9


@dataclass(frozen=True)
class DimensionCandidate:
    """A measurement that could be added, in view `view`, with its length. Its row is computed lazily."""
    view: str
    measure: Measure
    length: float
    axes: ViewAxes = field(repr=False, compare=False)
    #: Shared by every candidate of one solve.
    solve: DrawingSolve = field(repr=False, compare=False)

    @property
    def row(self) -> Optional[Row]:
        """Return the measurement's row (cached by the solve), or None if it can't be written as one."""
        try:
            return self.solve.row(self.measure, self.axes)
        except ValueError:
            return None


@dataclass(frozen=True)
class PickContext:
    """What a criterion can read while choosing."""
    solved: Callable[[FeatureHandle], bool]
    picks: Sequence['Pick']


#: Scores a candidate; lower is better.
Criterion = Callable[[DimensionCandidate, PickContext], float]


def fixed(criterion: Criterion) -> Criterion:
    """Mark a criterion as independent of the context, so auto_dimension scores it once per candidate."""
    setattr(criterion, "fixed", True)
    return criterion


def is_reference(handle: FeatureHandle) -> bool:
    """Return whether the feature is one of its timber's reference features, or a face of a reference edge.

    A derived feature never is, though its name ("shoulder×rptw.left") contains a face's.
    """
    if handle.feature.is_derived():
        return False
    return handle.feature.name.split(".", 1)[-1] in _reference_names(handle.timber)


@memo_by_identity
def _reference_names(timber) -> FrozenSet[str]:
    """Return the unprefixed names of a timber's reference faces and centerplanes."""
    names = set()
    for reference in getattr(timber.ticket, "reference_features", ()) or ():
        names |= {face.name.lower() for face in reference.long_faces_it_rests_on()}
        if reference in _CENTERPLANE_NAMES:
            names.add(_CENTERPLANE_NAMES[reference])
    return frozenset(names)


_CENTERPLANE_NAMES = {
    TimberFeature.RIGHT_LEFT_CENTER_PLANE: "centerplane_left_right",
    TimberFeature.FRONT_BACK_CENTER_PLANE: "centerplane_front_back",
}


def _ends(candidate: DimensionCandidate) -> Tuple[FeatureHandle, FeatureHandle]:
    return candidate.measure.anchor_a, candidate.measure.anchor_b


@fixed
def from_reference(candidate: DimensionCandidate, context: PickContext) -> float:
    """Criterion: measured from a reference feature of its own timber."""
    return 0.0 if any(is_reference(end) for end in _ends(candidate)) else 1.0


def from_solved(candidate: DimensionCandidate, context: PickContext) -> float:
    """Criterion: measured from an already solved feature."""
    return 0.0 if any(context.solved(end) for end in _ends(candidate)) else 1.0


@fixed
def perfect_over_rough(candidate: DimensionCandidate, context: PickContext) -> float:
    """Criterion: how many ends are rough faces."""
    return float(sum(end.feature.name.startswith("rough.") for end in _ends(candidate)))


@fixed
def angles_first(candidate: DimensionCandidate, context: PickContext) -> float:
    """Criterion: a distance after an angle. A slanted face is marked out by its angle and one position,
    not by two distances."""
    kind = candidate.measure.kind
    return 0.0 if kind is not None and kind.operation is MeasurementOperation.ANGLE else 1.0


@fixed
def angles_from_the_timber(candidate: DimensionCandidate, context: PickContext) -> float:
    """Criterion: an angle measured from one of the timber's own faces (rptw., ptw., rough.), or an edge
    between two of them, before one measured from a joint's. Distances all score 0."""
    kind = candidate.measure.kind
    if kind is None or kind.operation is not MeasurementOperation.ANGLE:
        return 0.0
    return 0.0 if any(_of_the_timber(end.feature) for end in _ends(candidate)) else 1.0


#: Name prefixes of a timber's own faces.
_TIMBER_FACE_PREFIXES = ("rptw.", "ptw.", "rough.")


def _of_the_timber(feature) -> bool:
    """Return whether a feature is one of the timber's own faces, or an edge derived from two of them."""
    if feature.is_derived():
        return all(_of_the_timber(parent.feature) for parent in feature.parents)
    return feature.name.startswith(_TIMBER_FACE_PREFIXES)


@fixed
def edges_over_faces(candidate: DimensionCandidate, context: PickContext) -> float:
    """Criterion: how many ends are faces. A derived edge stands for its two faces and draws as a line,
    while a face is only seen edge-on."""
    return float(sum(isinstance(end.feature.locate_simple_unbounded(end.owner), Plane) for end in _ends(candidate)))


@fixed
def declared_over_derived(candidate: DimensionCandidate, context: PickContext) -> float:
    """Criterion: how many ends are derived features (e.g. where a shoulder meets a face)."""
    return float(sum(end.feature.is_derived() for end in _ends(candidate)))


@fixed
def shortest(candidate: DimensionCandidate, context: PickContext) -> float:
    return candidate.length


#: The default order of preference, first to last; reorder or drop lines to try another.
PREFERENCE_ORDER: Tuple[Criterion, ...] = (
    angles_first,
    angles_from_the_timber,
    edges_over_faces,
    from_reference,
    perfect_over_rough,
    declared_over_derived,
    from_solved,
    shortest,
)


@dataclass(frozen=True)
class Policy:
    """How to choose among helpful candidates.

    `prefer` criteria are compared in order until one separates two candidates. `rules` must score
    0, unless no helpful candidate passes them; then one pick ignores them and warns.
    """
    prefer: Sequence[Criterion] = PREFERENCE_ORDER
    rules: Sequence[Criterion] = ()


DEFAULT_POLICY = Policy()


@dataclass(frozen=True)
class Pick:
    candidate: DimensionCandidate
    score: Tuple[float, ...]
    broke_rules: bool = False


class UnsolvedFeaturesWarning(UserWarning):
    """auto_dimension left features unsolved: no candidate fixes them."""


@dataclass(frozen=True)
class AutoDimensioning:
    picks: List[Pick]
    unsolved: List[FeatureHandle]
    #: Unknowns before any pick, and left after the last.
    left_before: int
    left_after: int


@memo_by_identity
def _key(handle: FeatureHandle) -> Tuple:
    return hit_identity(handle.feature, handle.owner)


def auto_dimension(
    candidates: Sequence[DimensionCandidate],
    targets: Sequence[FeatureHandle],
    known_rows: Sequence[Row],
    solve: Solve,
    policy: Policy = DEFAULT_POLICY,
) -> AutoDimensioning:
    """Pick from `candidates` until `targets` are solved or nothing more helps.

    `known_rows` are rows already known (fixed features, assumptions).
    """
    target_rows = [row for handle in targets for row in solve.dof_rows(handle)]
    columns = list(dict.fromkeys(column for row in (*known_rows, *target_rows) for column in row))
    index = {column: i for i, column in enumerate(columns)}
    known_matrix, target_matrix = rows_matrix(known_rows, columns), rows_matrix(target_rows, columns)
    tolerance = 1e-9 * max(float(np.linalg.norm(np.vstack([known_matrix, target_matrix]), 2)), 1.0)

    # Everything works on rows with what is known projected out; a pick removes its direction
    # from every target row (incremental Gram-Schmidt). `known` is an orthonormal basis of what is
    # known and picked, which a candidate is projected off when it is looked at.
    target_left = target_matrix
    known = np.zeros((0, len(columns)))
    if len(known_rows):
        _, values, basis = rank_svd(known_matrix)
        known = basis[values > tolerance]
        target_left = target_matrix - target_matrix @ known.T @ known

    spans: Dict[Tuple[int, str], slice] = {}
    start = 0
    for handle in targets:
        count = len(solve.dof_rows(handle))
        spans[_key(handle)] = slice(start, start + count)
        start += count

    # Whether each target is solved, until the next pick changes it.
    solved_memo: Dict[Tuple, bool] = {}

    def solved(handle: FeatureHandle) -> bool:
        key = _key(handle)
        if key not in solved_memo:
            span = spans.get(key)
            solved_memo[key] = span is None or float(np.linalg.norm(target_left[span])) < tolerance
        return solved_memo[key]

    # Each candidate's score by the fixed criteria, worked out once.
    fixed_scores: Dict[Tuple[int, int], float] = {}

    def score(i: int) -> Tuple[float, ...]:
        parts = []
        for k, criterion in enumerate(policy.prefer):
            if getattr(criterion, "fixed", False):
                if (i, k) not in fixed_scores:
                    fixed_scores[(i, k)] = criterion(candidates[i], context)
                parts.append(fixed_scores[(i, k)])
            else:
                parts.append(criterion(candidates[i], context))
        return tuple(parts)

    def unsolved_basis() -> np.ndarray:
        _, values, directions = rank_svd(target_left)
        return directions[values > tolerance]

    def helpful_direction(candidate: DimensionCandidate, unsolved: np.ndarray) -> Optional[np.ndarray]:
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
        scored = sorted(available, key=lambda i: (score(i), i))
        chosen: Optional[Tuple[int, np.ndarray, bool]] = None
        first_helpful: Optional[Tuple[int, np.ndarray, bool]] = None
        for i in scored:
            direction = helpful_direction(candidates[i], unsolved)
            if direction is None:
                # Never helps again: what it adds beyond the known rows is either nothing, or partly
                # outside what is unsolved -- and a pick only adds to the known rows a direction
                # inside the unsolved, which leaves that outside part where it is.
                available.remove(i)
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
        picked_score = score(index_)
        target_left = target_left - np.outer(target_left @ direction, direction)
        known = np.vstack([known, direction])
        available.remove(index_)
        solved_memo.clear()
        picks.append(Pick(candidates[index_], picked_score, broke_rules=broke_rules))

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


def _on_sheet(handle: FeatureHandle, look: np.ndarray) -> Optional[SheetShape]:
    """Return how a feature draws looking along `look` (sheet_shape), or None.

    A line for an edge-on face or a line in the sheet's plane; a point for a line end-on.
    """
    located = handle.feature.locate_simple_unbounded(handle.owner)
    if not isinstance(located, (Line, Plane)):
        return None
    transform = handle.timber.transform
    look_local = unit_ndarray(as_ndarray(transform.global_to_local_direction(create_v3(*look))))
    shape = sheet_shape(located, look_local)
    if shape is None:
        return None
    at = as_ndarray(transform.local_to_global(create_v3(*shape.at)))
    if isinstance(shape, SheetPoint):
        return SheetPoint(at)
    if isinstance(located, Line):
        slant = float(unit_ndarray(as_ndarray(located.direction)) @ look_local)
        if abs(slant) > SQUARE_TO_VIEW:
            return None
    return SheetLine(at, unit_ndarray(as_ndarray(transform.local_to_global_direction(create_v3(*shape.run)))))


def _separation(one: SheetShape, other: SheetShape, look: np.ndarray) -> Optional[float]:
    """Return the perpendicular distance on the sheet between two drawn features, or None (e.g. two points)."""
    if isinstance(one, SheetPoint) and isinstance(other, SheetPoint):
        return None
    return sheet_gap(one, other, look)


def _across(line: SheetLine, look: np.ndarray) -> np.ndarray:
    """Return the in-sheet direction square to a drawn line."""
    return unit_ndarray(np.cross(line.run, look))


def derived_edge_anchors(cut_timber: 'CutTimber', faces: Sequence[FeatureHandle],
                         views: Mapping[str, ViewAxes]) -> List[FeatureHandle]:
    """Return the edges where a face of `faces` that some view draws slanted (along neither sheet axis)
    meets another of `faces` on `cut_timber`, where their groups let them form one and some of it is on
    the timber: e.g. a sloped shoulder against the timber's faces.

    For dimensioning to: seen end-on such an edge draws as a point, and a face drawn slanted has no
    parallel line to be measured from.

    The other faces' edges are left out: a face drawn along a sheet axis has parallel lines to measure
    from, and faces_to_edges moves a measurement onto its edge after solving. As anchors, each would pair
    with every other anchor in view as a candidate (about doubling the time to dimension).
    """
    root = cut_timber.render_timber_with_cuts_csg_local()
    timber = cut_timber.timber
    hits = [face.hit for face in faces if face.timber is timber and isinstance(face.feature, FaceFeature)]
    sheets = [(unit_ndarray(as_ndarray(axes.look)), unit_ndarray(as_ndarray(axes.right)),
               unit_ndarray(as_ndarray(axes.up))) for axes in views.values()]
    slanted = [hit for hit in hits if any(_drawn_slanted(FeatureHandle(timber=timber, hit=hit), *sheet)
                                          for sheet in sheets)]
    extents = extents_of(root, timber)
    edges, seen = [], set()
    for one in slanted:
        for other in hits:
            pair = frozenset((id(one), id(other)))
            if other is one or pair in seen:
                continue
            seen.add(pair)
            for hit in derive_edge_hits(root, [one, other]):
                extent = extents.of(hit.feature, hit.owner)
                if extent is not None and not extent.is_empty:
                    edges.append(FeatureHandle(timber=timber, hit=hit))
    return edges


def _meets(edge: FeatureHandle) -> List['CarrierRef']:
    """Return the carriers an edge is the meet of (two for a derived or declared meet of faces), else none."""
    recipe = edge.feature.solve_recipe(edge.owner) or ()
    return [part for part in recipe if isinstance(part, CarrierRef)] if len(recipe) == 2 else []


def _on_an_edge_on_face(handle: FeatureHandle, look: np.ndarray) -> bool:
    """Return whether an edge draws as a line lying on a face it is the meet of, seen edge-on (that face's
    drawn line), so a measurement to the face measures it too."""
    if not isinstance(_on_sheet(handle, look), SheetLine):
        return False
    local = unit_ndarray(as_ndarray(handle.timber.transform.global_to_local_direction(create_v3(*look))))
    carriers = [ref.carrier() for ref in _meets(handle)]
    return any(isinstance(carrier, CarrierPlane)
               and abs(float(unit_ndarray(as_ndarray(carrier.plane.normal)) @ local)) < 1e-9
               for carrier in carriers)


def without_edges_on_faces(visible: Mapping[str, Sequence[FeatureHandle]],
                           views: Mapping[str, ViewAxes]) -> Dict[str, List[FeatureHandle]]:
    """Return `visible` (per view) less the edges lying on a face seen edge-on there."""
    out = {}
    for view, handles in visible.items():
        look = unit_ndarray(as_ndarray(views[view].look))
        out[view] = [handle for handle in handles if not _on_an_edge_on_face(handle, look)]
    return out


def faces_to_edges(result: AutoDimensioning, cut_timbers: Sequence['CutTimber'], faces: Sequence[FeatureHandle],
                   views: Mapping[str, ViewAxes], carriers: CarrierMap) -> AutoDimensioning:
    """Return `result` with each pick's face ends, seen edge-on, moved onto an edge of the face.

    The edge is along the face region's boundary nearest the camera in the pick's view, where it meets
    another face of `faces`: a declared edge there if one is the meet of the same two faces, else the
    derived one, whatever their groups. The measurement keeps its value and, but for the tilt columns
    the sheet's assumptions fix, its row. A face with no such edge stays.
    """
    roots = {id(cut.timber): cut.render_timber_with_cuts_csg_local() for cut in cut_timbers}
    by_timber: Dict[int, List[FeatureHandle]] = {}
    for face in faces:
        if isinstance(face.feature, FaceFeature):
            by_timber.setdefault(id(face.timber), []).append(face)
    memo: Dict[Tuple, FeatureHandle] = {}

    def edge_of(end: FeatureHandle, view: str) -> FeatureHandle:
        key = (_key(end), id(end.timber), view)
        if key not in memo:
            root = roots.get(id(end.timber))
            look = unit_ndarray(as_ndarray(views[view].look))
            memo[key] = end if root is None else _nearest_edge_of(
                end, look, root, by_timber.get(id(end.timber), []), carriers)
        return memo[key]

    picks = []
    for pick in result.picks:
        candidate = pick.candidate
        old_a, old_b = _ends(candidate)
        a, b = edge_of(old_a, candidate.view), edge_of(old_b, candidate.view)
        # Both ends moved, else one; whichever the solver can still write a row for.
        for ends in ((a, b), (a, old_b), (old_a, b)):
            moved = replace(candidate, measure=replace(candidate.measure, anchor_a=ends[0], anchor_b=ends[1]))
            if ends != (old_a, old_b) and moved.row is not None:
                candidate = moved
                break
        picks.append(replace(pick, candidate=candidate))
    return replace(result, picks=picks)


#: How far a point may be off a plane and still be on it, in meters.
_ON_PLANE = 1e-7


def _nearest_edge_of(end: FeatureHandle, look: np.ndarray, root: CutCSG, faces: Sequence[FeatureHandle],
                     carriers: CarrierMap) -> FeatureHandle:
    """Return the edge of face `end` along its region's boundary nearest the camera, else `end`."""
    plane = end.feature.locate_simple_unbounded(end.owner)
    if (end.feature.is_derived() or not isinstance(end.feature, FaceFeature) or not isinstance(plane, Plane)
            or not isinstance(_on_sheet(end, look), SheetLine)):
        return end
    extent = extents_of(root, end.timber).of(end.feature, end.owner)
    if extent is None:
        return end
    local = unit_ndarray(as_ndarray(end.timber.transform.global_to_local_direction(create_v3(*look))))
    along = [(start, stop) for start, stop in extent.outline()
             if np.linalg.norm(stop - start) > _ON_PLANE
             and abs(float(unit_ndarray(stop - start) @ local)) < 1e-6]
    if not along:
        return end
    # Nearest by depth alone: another timber could hide that edge while some of the face shows, but
    # the face's nearest boundary is rarely hidden when the face isn't, so visibility isn't checked.
    start, stop = min(along, key=lambda segment: float((segment[0] + segment[1]) @ local))
    normal = unit_ndarray(as_ndarray(plane.normal))
    for other in faces:
        other_plane = other.feature.locate_simple_unbounded(other.owner)
        if not isinstance(other_plane, Plane) or other is end:
            continue
        other_normal = unit_ndarray(as_ndarray(other_plane.normal))
        if abs(abs(float(normal @ other_normal)) - 1) < 1e-9:
            continue
        if all(abs(float(other_normal @ (point - as_ndarray(other_plane.point)))) < _ON_PLANE for point in (start, stop)):
            edge = _edge_between(end, other, root, carriers)
            if edge is not None:
                return edge
    return end


def _edge_between(one: FeatureHandle, other: FeatureHandle, root: CutCSG,
                  carriers: CarrierMap) -> Optional[FeatureHandle]:
    """Return the edge where two faces meet: a declared edge of either's owner that is their meet, else
    the derived one (whatever their groups), or None."""
    faces = {_canonical(part, carriers) for face in (one, other)
             for part in (face.feature.solve_recipe(face.owner) or ()) if isinstance(part, CarrierRef)}
    for owner in {id(face.owner): face.owner for face in (one, other)}.values():
        for feature in _declared_edges(owner):
            edge = FeatureHandle(timber=one.timber, hit=OwnedFeatureHit(feature=feature, owner=owner))
            if {_canonical(ref, carriers) for ref in _meets(edge)} == faces:
                return edge
    derived = DerivedEdgeFeature.derive(one.hit, other.hit, any_groups=True)
    owner = None if derived is None else shared_ancestor(root, one.owner, other.owner)
    return None if derived is None or owner is None else FeatureHandle(
        timber=one.timber, hit=OwnedFeatureHit(feature=derived, owner=owner))


@memo_by_identity
def _declared_edges(owner: CutCSG) -> List[EdgeFeature]:
    return [feature for feature in owner.get_declared_features() if isinstance(feature, EdgeFeature)]


def _canonical(ref: 'CarrierRef', carriers: CarrierMap) -> 'CarrierRef':
    return carriers.canonical(ref) if ref in carriers else ref


def _drawn_slanted(handle: FeatureHandle, look: np.ndarray, right: np.ndarray, up: np.ndarray) -> bool:
    """Return whether a view looking along `look` draws the feature as a line along neither sheet axis."""
    shape = _on_sheet(handle, look)
    return isinstance(shape, SheetLine) and _slanted(shape, right, up)


def _slanted(line: SheetLine, right: np.ndarray, up: np.ndarray) -> bool:
    """Return whether a drawn line runs along neither of the sheet's axes."""
    return max(abs(float(line.run @ right)), abs(float(line.run @ up))) < 1 - 1e-9


def sheet_candidates(
    anchors: Mapping[str, Sequence[FeatureHandle]], views: Mapping[str, ViewAxes], solve: DrawingSolve,
) -> List[DimensionCandidate]:
    """Return the dimensions a view can draw between anchors it can see (`anchors` are per view,
    visibility.visible_by_view):

    - perpendicular distances between two parallel drawn lines, or from a drawn point to a line;
    - angles between a slanted drawn line (along neither sheet axis) and another line;
    - horizontal and vertical distances between two drawn points, one of them a derived edge seen end-on.
    """
    candidates = []
    for view, axes in views.items():
        look = as_ndarray(axes.look)
        look /= np.linalg.norm(look)
        right, up = unit_ndarray(as_ndarray(axes.right)), unit_ndarray(as_ndarray(axes.up))
        drawn = [(handle, _on_sheet(handle, look)) for handle in anchors.get(view, ())]
        drawn = [(handle, shape) for handle, shape in drawn if shape is not None]
        for i, (a, shape_a) in enumerate(drawn):
            for b, shape_b in drawn[i + 1:]:
                add = lambda kind, length: candidates.append(
                    DimensionCandidate(view, Measure(a, b, kind=kind), length, axes, solve))
                length = _separation(shape_a, shape_b, look)
                if length is not None and length >= COINCIDENT:
                    add(PERPENDICULAR, length)
                if isinstance(shape_a, SheetLine) and isinstance(shape_b, SheetLine):
                    if abs(float(shape_a.run @ shape_b.run)) < 1 - 1e-9 and (
                            _slanted(shape_a, right, up) or _slanted(shape_b, right, up)):
                        add(ANGLE, 0.0)
                elif isinstance(shape_a, SheetPoint) and isinstance(shape_b, SheetPoint) and (
                        a.feature.is_derived() or b.feature.is_derived()):
                    gap = shape_b.at - shape_a.at
                    for kind, axis in ((HORIZONTAL, right), (VERTICAL, up)):
                        if abs(float(gap @ axis)) >= COINCIDENT:
                            add(kind, abs(float(gap @ axis)))
    return candidates


def coincidence_assumptions(
    anchors: Mapping[str, Sequence[FeatureHandle]], views: Mapping[str, ViewAxes], solve: DrawingSolve,
) -> List[Assumption]:
    """Return assumptions for features a view draws on top of each other (flush faces, a point on a line).

    Their distance across the sheet is known without a dimension. Features on one line or spot are
    chained to the first.
    """
    assumptions: List[Assumption] = []

    def add(view: str, a: FeatureHandle, b: FeatureHandle, kind: MeasurementKind, across=None) -> None:
        try:
            row = solve.row(Measure(a, b, kind=kind), views[view], across)
        except ValueError:
            return
        assumptions.append(Assumption(
            f"{a.feature.name} and {b.feature.name} line up in the {view} view ({kind.name})", (row,)))

    for view, axes in views.items():
        look = unit_ndarray(as_ndarray(axes.look))
        lines: List[Tuple[SheetLine, FeatureHandle]] = []  # a line on the sheet, its first feature
        spots: List[Tuple[SheetPoint, FeatureHandle]] = []  # a spot on the sheet, its first feature

        def lined_up(shape: SheetShape, drawn: SheetShape) -> bool:
            gap = sheet_gap(shape, drawn, look)
            return gap is not None and gap < COINCIDENT

        for handle in anchors.get(view, ()):
            shape = _on_sheet(handle, look)
            if shape is None:
                continue
            if isinstance(shape, SheetLine):
                same = next((line for line in lines if lined_up(shape, line[0])), None)
                if same is None:
                    lines.append((shape, handle))
                else:
                    add(view, same[1], handle, PERPENDICULAR, _across(same[0], look))
                continue
            spot = next((spot for spot in spots if lined_up(shape, spot[0])), None)
            if spot is not None:
                add(view, spot[1], handle, HORIZONTAL)
                add(view, spot[1], handle, VERTICAL)
                continue
            spots.append((shape, handle))
        # A point on a line: one row, across the line.
        for point, handle in spots:
            on = next((line for line in lines if lined_up(point, line[0])), None)
            if on is not None:
                add(view, on[1], handle, PERPENDICULAR, _across(on[0], look))
    return assumptions
