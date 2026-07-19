"""Assembly constraints and the assembly (disassembly) solver.

Each member (timber or accessory) in each joint may declare an AssemblyFreedom:
the set of degrees of freedom in which it can move to escape that joint, each
with a "freed after" amount — the travel after which the joint no longer
constrains the member. Each member additionally carries an Ordering
(order, suborder), compared lexicographically; smaller = extracted EARLIER
during disassembly (i.e. installed later during assembly). The suborder
expresses sequencing REQUIRED within a joint (a peg must come out before the
tenon slides) and is authored by the joint cut functions; the order is the
frame-level plan, assigned afterwards via Joint.with_order. Everything
defaults to Ordering(0, 0), so an un-ordered frame disassembles as one big
exploded-view step (with locking accessories popping first).

The solver is deliberately timber-agnostic: it operates on an abstract graph of
AssemblyMember / AssemblyJoint records so it can be tested without constructing
any timbers, and so this module only depends on kumiki.rule (timber.py imports
from here, never the reverse). ``solve_frame_assembly`` in timber.py adapts a
Frame into this graph.

The solver is kinematic/topological, not geometric: it trusts the declared
freedoms and does no collision checking. A "solved" disassembly is a preview
aid, not a proof of physical validity.

Rotational freedoms are declared (RotationDof) but not solved yet; the solver
raises NotImplementedError when it encounters one. Richer R6 freedom shapes
(e.g. sequenced twist-then-move) should be introduced as new Dof types or
composite freedoms on AssemblyFreedom.
"""

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import sympy as sp

from kumiki.rule import (
    Direction3D,
    Numeric,
    V3,
    create_v3,
    giraffe_evalf,
    safe_normalize_vector,
)


# Two unit directions are considered the same DOF when their dot product is at
# least 1 - _PARALLEL_DOT_TOLERANCE.
_PARALLEL_DOT_TOLERANCE = 1e-6
# Distances/vector magnitudes below this are treated as zero.
_ZERO_EPSILON = 1e-9
# How many times a member's movement record may CHANGE within one order step
# (see _propagate) before the constraint is declared unsolvable.
_MAX_LOOP_ITERATIONS = 6


# ============================================================================
# Freedom classes
# ============================================================================


@dataclass(frozen=True)
class TranslationDof:
    """One half-interval translational DOF, in GLOBAL space.

    The member may travel from 0 along ``direction``; after ``freed_after`` of
    travel the joint no longer constrains it. Full (bidirectional) intervals
    are expressed as two opposite half DOFs.
    """

    direction: Direction3D
    freed_after: Numeric


@dataclass(frozen=True)
class RotationDof:
    """One half-interval rotational DOF, in GLOBAL space. Solver support is
    NotImplemented for now; the type exists so freedoms can already be
    declared and so future R6 shapes have a home."""

    axis_position: V3
    axis_direction: Direction3D
    freed_after_angle: Numeric


@dataclass(frozen=True)
class AssemblyFreedom:
    """The freedom shape for ONE member within ONE joint.

    Currently a set of independent half/full intervals from 0 in R6. Future
    richer shapes (e.g. requires twisting while moving, or move-then-twist
    sequences) should extend this class rather than being encoded by callers.
    """

    translations: Tuple[TranslationDof, ...] = ()
    rotations: Tuple[RotationDof, ...] = ()

    @staticmethod
    def translation(direction: Direction3D, freed_after: Numeric) -> "AssemblyFreedom":
        """A single half-interval translational freedom along ``direction``."""
        return AssemblyFreedom(
            translations=(TranslationDof(direction=safe_normalize_vector(direction), freed_after=freed_after),),
        )

    @staticmethod
    def bidirectional_translation(direction: Direction3D, freed_after: Numeric) -> "AssemblyFreedom":
        """A full-interval translational freedom: two opposite half DOFs."""
        unit = safe_normalize_vector(direction)
        return AssemblyFreedom(
            translations=(
                TranslationDof(direction=unit, freed_after=freed_after),
                TranslationDof(direction=-unit, freed_after=freed_after),
            ),
        )

    @staticmethod
    def combine(f1: "AssemblyFreedom", f2: "AssemblyFreedom") -> "AssemblyFreedom":
        """Union of the DOFs of two freedoms (a member that can escape either way)."""
        return AssemblyFreedom(
            translations=f1.translations + f2.translations,
            rotations=f1.rotations + f2.rotations,
        )


# ============================================================================
# Ordering
# ============================================================================


@dataclass(frozen=True, order=True)
class Ordering:
    """Extraction position: compared lexicographically; smaller = out earlier.

    ``suborder`` expresses sequencing required WITHIN a joint (peg before
    slide) and is authored by the joint cut functions; ``order`` is the
    frame-level plan set via Joint.with_order.
    """

    order: int = 0
    suborder: int = 0

    def label(self) -> str:
        """Human-readable form: "2" or "2.1" when a suborder is present."""
        return str(self.order) if self.suborder == 0 else f"{self.order}.{self.suborder}"


# ============================================================================
# Solver input graph (timber-agnostic)
# ============================================================================


@dataclass(frozen=True)
class AssemblyMember:
    """One movable body in the assembly graph (a timber or an accessory)."""

    # Opaque handle used to reference this member from joints and movements.
    # The Frame adapter uses ticket.kumiki_id.
    key: int
    # Human-readable name for warnings/diagnostics (the adapter uses ticket path).
    name: str
    # Reference point used only by the direction-ranking heuristics
    # (the adapter uses the timber centroid).
    position: V3


@dataclass(frozen=True)
class JointMemberSpec:
    """One member's participation in one joint.

    A None freedom means "unspecified" and the connection is treated as rigid
    (the member is dragged along whenever the joint moves).
    """

    freedom: Optional[AssemblyFreedom] = None
    ordering: Ordering = Ordering()


@dataclass(frozen=True)
class AssemblyJoint:
    """One joint in the assembly graph.

    ``members`` must contain an entry for EVERY member participating in the
    joint.
    """

    name: str
    members: Mapping[int, JointMemberSpec]


# ============================================================================
# Solver output
# ============================================================================


@dataclass(frozen=True)
class MemberMovement:
    """Net movement of one member within one step.

    ``distance`` is the BASE amount (derived from freed_after); consumers apply
    their own disassembly multiplier on top. ``dragged`` is True when the
    member moved only because it was rigidly pulled along, not because it was
    being extracted itself.
    """

    member_key: int
    direction: Direction3D
    distance: Numeric
    dragged: bool


@dataclass(frozen=True)
class AssemblyStep:
    ordering: Ordering
    movements: Tuple[MemberMovement, ...]


@dataclass(frozen=True)
class AssemblyFailure:
    """Why (and where) solving stopped. Earlier steps remain valid/scrubbable."""

    ordering: Ordering
    message: str
    diagnostics: Tuple[str, ...]


@dataclass(frozen=True)
class AssemblySolution:
    steps: Tuple[AssemblyStep, ...]
    warnings: Tuple[str, ...]
    failure: Optional[AssemblyFailure] = None


# ============================================================================
# Float helpers (heuristics and propagation run in plain Python floats)
# ============================================================================


_Float3 = Tuple[float, float, float]


def _float3(vec) -> _Float3:
    return (
        float(giraffe_evalf(vec[0, 0])),
        float(giraffe_evalf(vec[1, 0])),
        float(giraffe_evalf(vec[2, 0])),
    )


def _dot3(a: _Float3, b: _Float3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub3(a: _Float3, b: _Float3) -> _Float3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add3(a: _Float3, b: _Float3) -> _Float3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale3(a: _Float3, s: float) -> _Float3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _neg3(a: _Float3) -> _Float3:
    return (-a[0], -a[1], -a[2])


def _norm3(a: _Float3) -> float:
    return _dot3(a, a) ** 0.5


def _unit3(a: _Float3) -> Optional[_Float3]:
    magnitude = _norm3(a)
    if magnitude < _ZERO_EPSILON:
        return None
    return _scale3(a, 1.0 / magnitude)


def _cross3(a: _Float3, b: _Float3) -> _Float3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _are_parallel(a: _Float3, b: _Float3) -> bool:
    """Both inputs must be unit vectors."""
    return _dot3(a, b) >= 1.0 - _PARALLEL_DOT_TOLERANCE


def _freedom_allows(freedom: Optional[AssemblyFreedom], direction: _Float3) -> Optional[TranslationDof]:
    """Return the freedom's TranslationDof parallel to ``direction`` (unit), if any."""
    if freedom is None:
        return None
    for dof in freedom.translations:
        dof_unit = _unit3(_float3(dof.direction))
        if dof_unit is not None and _are_parallel(dof_unit, direction):
            return dof
    return None


def _dominant_plane_normal(points: Sequence[_Float3]) -> Optional[_Float3]:
    """Heuristic normal of the plane the points roughly span.

    Uses the largest cross product among pairs of centered points as the plane
    normal. Returns None for fewer than 3 points or (near-)collinear layouts.
    """
    if len(points) < 3:
        return None
    centroid = (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
        sum(p[2] for p in points) / len(points),
    )
    centered = [_sub3(p, centroid) for p in points]
    best_cross: Optional[_Float3] = None
    best_magnitude = 0.0
    for i in range(len(centered)):
        for j in range(i + 1, len(centered)):
            cross = _cross3(centered[i], centered[j])
            magnitude = _norm3(cross)
            if magnitude > best_magnitude:
                best_magnitude = magnitude
                best_cross = cross
    if best_cross is None or best_magnitude < _ZERO_EPSILON:
        return None
    return _unit3(best_cross)


# ============================================================================
# Solver
# ============================================================================


class _LoopDetected(Exception):
    """Internal: a member's movement kept changing past the loop cap."""

    def __init__(self, member_key: int, chain: Tuple[Tuple[int, str, int], ...]):
        super().__init__("assembly propagation loop")
        self.member_key = member_key
        self.chain = chain


def _spec_has_translations(spec: JointMemberSpec) -> bool:
    return spec.freedom is not None and bool(spec.freedom.translations)


def solve_assembly(
    members: Sequence[AssemblyMember],
    joints: Sequence[AssemblyJoint],
) -> Optional[AssemblySolution]:
    """Solve the disassembly sequence for an abstract assembly graph.

    Iterates the distinct member Orderings from small to large. At each step,
    every member holding a freedom at that ordering in some joint is extracted
    along one of its DOFs (ranked by _rank_dofs); moving a member recursively
    drags every member it is rigidly connected to (see _propagate).

    Returns None when no member has any freedom (nothing can move). When some
    step cannot be solved, solving stops there and the partial steps plus an
    AssemblyFailure are returned (it never raises for unsolvability), so
    callers can still preview the steps that did solve.

    Raises NotImplementedError for rotational freedoms and ValueError for
    joints referencing unknown member keys.
    """
    member_by_key: Dict[int, AssemblyMember] = {member.key: member for member in members}

    joints_by_member: Dict[int, List[AssemblyJoint]] = {}
    for joint in joints:
        for key, spec in joint.members.items():
            if key not in member_by_key:
                raise ValueError(
                    f"Joint '{joint.name}' references unknown assembly member key {key}"
                )
            if spec.freedom is not None and spec.freedom.rotations:
                raise NotImplementedError(
                    f"Joint '{joint.name}': rotational assembly freedoms are not supported yet"
                )
            joints_by_member.setdefault(key, []).append(joint)

    step_orderings = sorted({
        spec.ordering
        for joint in joints
        for spec in joint.members.values()
        if _spec_has_translations(spec)
    })
    if not step_orderings:
        return None

    # A member's own extraction step: the smallest ordering at which some
    # joint gives it a usable freedom. Used for the dragged-too-early warning.
    own_ordering: Dict[int, Ordering] = {}
    for joint in joints:
        for key, spec in joint.members.items():
            if _spec_has_translations(spec):
                existing = own_ordering.get(key)
                if existing is None or spec.ordering < existing:
                    own_ordering[key] = spec.ordering

    positions: Dict[int, _Float3] = {member.key: _float3(member.position) for member in members}

    removed: set = set()
    warnings: List[str] = []
    steps: List[AssemblyStep] = []
    # Cumulative committed displacement per member, used to decide whether a
    # joint has ALREADY separated (relative motion along an escape DOF beyond
    # its freed_after) so the joint's other member need not also extract.
    total_displacement: Dict[int, _Float3] = {}

    for step_ordering in step_orderings:
        step_joints = [
            joint for joint in joints
            if any(
                spec.ordering == step_ordering and _spec_has_translations(spec)
                for spec in joint.members.values()
            )
        ]
        outcome = _solve_step(
            step_ordering=step_ordering,
            step_joints=step_joints,
            joints_by_member=joints_by_member,
            member_by_key=member_by_key,
            positions=positions,
            own_ordering=own_ordering,
            removed=removed,
            total_displacement=total_displacement,
            warnings=warnings,
        )
        if isinstance(outcome, AssemblyFailure):
            return AssemblySolution(steps=tuple(steps), warnings=tuple(warnings), failure=outcome)
        movements, primary_movers, step_records = outcome
        removed |= primary_movers
        for key, contributions in step_records.items():
            net = total_displacement.get(key, (0.0, 0.0, 0.0))
            for direction, distance in contributions:
                net = _add3(net, _scale3(direction, distance))
            total_displacement[key] = net
        if movements:
            steps.append(AssemblyStep(ordering=step_ordering, movements=tuple(movements)))

    return AssemblySolution(steps=tuple(steps), warnings=tuple(warnings), failure=None)


def _solve_step(
    step_ordering: Ordering,
    step_joints: List[AssemblyJoint],
    joints_by_member: Dict[int, List[AssemblyJoint]],
    member_by_key: Dict[int, AssemblyMember],
    positions: Dict[int, _Float3],
    own_ordering: Dict[int, Ordering],
    removed: set,
    total_displacement: Dict[int, _Float3],
    warnings: List[str],
):
    """Extract the members scheduled at one (order, suborder) step.

    Cut functions author escape freedoms on BOTH sides of each interface, so
    every member of a scheduled joint is a candidate — but a joint only needs
    ONE member to depart. Candidates are processed cheapest-drag-first, and a
    candidate is skipped when all joints scheduling it have already separated
    (see _is_joint_separated), so the second side of an interface stays put.

    Returns (movements, primary_movers, step_records) on success, or an
    AssemblyFailure. Mutates ``warnings``; ``removed`` and
    ``total_displacement`` are only read (the caller commits them).
    """
    # Which members get extracted at this step, and along which candidate DOFs.
    candidates: Dict[int, List[TranslationDof]] = {}
    for joint in step_joints:
        for key, spec in joint.members.items():
            if key in removed or spec.ordering != step_ordering:
                continue
            if spec.freedom is None or not spec.freedom.translations:
                continue
            candidates.setdefault(key, []).extend(spec.freedom.translations)

    ranked_dofs_by_key = {
        key: _rank_dofs(
            key=key,
            dofs=candidates[key],
            step_ordering=step_ordering,
            step_joints=step_joints,
            positions=positions,
            own_ordering=own_ordering,
            removed=removed,
        )
        for key in candidates
    }

    # Step-local movement records: member key -> list of (unit direction, distance)
    # contributions. Committed trial by trial.
    step_records: Dict[int, List[Tuple[_Float3, float]]] = {}
    loop_counts: Dict[int, int] = {}
    primary_movers: set = set()

    def estimated_drag_cost(key: int) -> float:
        """How many members the candidate's best DOF would move (on a clean
        slate). Cheapest-first processing lets the least-entangled member of
        an interface depart, so its partner can be skipped as separated."""
        for dof in ranked_dofs_by_key[key]:
            direction = _unit3(_float3(dof.direction))
            distance = float(giraffe_evalf(dof.freed_after))
            if direction is None or distance < _ZERO_EPSILON:
                continue
            probe_records: Dict[int, List[Tuple[_Float3, float]]] = {}
            try:
                _propagate(
                    start_key=key,
                    direction=direction,
                    distance=distance,
                    step_ordering=step_ordering,
                    joints_by_member=joints_by_member,
                    member_by_key=member_by_key,
                    own_ordering=own_ordering,
                    removed=removed,
                    records=probe_records,
                    loop_counts={},
                )
            except _LoopDetected:
                return float("inf")
            return float(len(probe_records))
        return float("inf")

    sorted_candidate_keys = sorted(
        candidates,
        key=lambda key: (estimated_drag_cost(key), member_by_key[key].name, key),
    )
    for key in sorted_candidate_keys:
        scheduling_joints = [
            joint for joint in step_joints
            if key in joint.members
            and joint.members[key].ordering == step_ordering
            and _spec_has_translations(joint.members[key])
        ]
        if scheduling_joints and all(
            _is_joint_separated(key, joint, removed, step_records, total_displacement)
            for joint in scheduling_joints
        ):
            continue  # every joint scheduling this member has already come apart

        ranked_dofs = ranked_dofs_by_key[key]
        failure_diagnostics: List[str] = []
        succeeded = False
        for dof in ranked_dofs:
            direction = _unit3(_float3(dof.direction))
            distance = float(giraffe_evalf(dof.freed_after))
            if direction is None or distance < _ZERO_EPSILON:
                continue
            # Trial: propagate into copies, commit only on success so a failed
            # DOF leaves no residue for the next attempt.
            trial_records = {record_key: list(entries) for record_key, entries in step_records.items()}
            trial_loops = dict(loop_counts)
            try:
                trial_warnings = _propagate(
                    start_key=key,
                    direction=direction,
                    distance=distance,
                    step_ordering=step_ordering,
                    joints_by_member=joints_by_member,
                    member_by_key=member_by_key,
                    own_ordering=own_ordering,
                    removed=removed,
                    records=trial_records,
                    loop_counts=trial_loops,
                )
            except _LoopDetected as loop:
                failure_diagnostics.append(
                    _describe_loop(loop, dof_direction=direction, member_by_key=member_by_key)
                )
                continue
            step_records = trial_records
            loop_counts = trial_loops
            warnings.extend(trial_warnings)
            primary_movers.add(key)
            succeeded = True
            break
        if not succeeded:
            member_name = member_by_key[key].name
            return AssemblyFailure(
                ordering=step_ordering,
                message=(
                    f"Cannot disassemble step {step_ordering.label()}: member '{member_name}' has no "
                    f"workable DOF; every direction keeps re-dragging other members past the loop "
                    f"limit ({_MAX_LOOP_ITERATIONS})"
                ),
                diagnostics=tuple(failure_diagnostics),
            )

    movements = _merge_movements(
        step_ordering=step_ordering,
        step_records=step_records,
        primary_movers=primary_movers,
        member_by_key=member_by_key,
        warnings=warnings,
    )
    return movements, primary_movers, step_records


def _member_displacement(
    key: int,
    step_records: Dict[int, List[Tuple[_Float3, float]]],
    total_displacement: Dict[int, _Float3],
) -> _Float3:
    """Cumulative displacement of a member: committed steps + current step."""
    net = total_displacement.get(key, (0.0, 0.0, 0.0))
    for direction, distance in step_records.get(key, []):
        net = _add3(net, _scale3(direction, distance))
    return net


def _dof_travel_reached(freedom: Optional[AssemblyFreedom], unit_direction: _Float3, magnitude: float) -> bool:
    """Whether traveling ``magnitude`` along ``unit_direction`` satisfies one of
    the freedom's DOFs (parallel direction, at least freed_after of travel)."""
    if freedom is None:
        return False
    for dof in freedom.translations:
        dof_unit = _unit3(_float3(dof.direction))
        if dof_unit is None or not _are_parallel(dof_unit, unit_direction):
            continue
        if magnitude >= float(giraffe_evalf(dof.freed_after)) - _ZERO_EPSILON:
            return True
    return False


def _is_joint_separated(
    member_key: int,
    joint: AssemblyJoint,
    removed: set,
    step_records: Dict[int, List[Tuple[_Float3, float]]],
    total_displacement: Dict[int, _Float3],
) -> bool:
    """Whether ``member_key`` no longer needs to extract from ``joint``: every
    other member has already moved RELATIVE to it along an escape DOF by at
    least that DOF's freed_after.

    Relative motion is what matters: a member dragged along with its partner
    (zero relative displacement) is still attached even though the partner was
    "removed", while a peg that popped out earlier no longer blocks the skip.
    """
    my_displacement = _member_displacement(member_key, step_records, total_displacement)
    for other_key, other_spec in joint.members.items():
        if other_key == member_key:
            continue
        delta = _sub3(_member_displacement(other_key, step_records, total_displacement), my_displacement)
        magnitude = _norm3(delta)
        if magnitude < _ZERO_EPSILON:
            return False
        unit_delta = _scale3(delta, 1.0 / magnitude)
        if _dof_travel_reached(other_spec.freedom, unit_delta, magnitude):
            continue  # the other member escaped this joint relative to us
        my_spec = joint.members.get(member_key)
        my_freedom = my_spec.freedom if my_spec is not None else None
        if _dof_travel_reached(my_freedom, _neg3(unit_delta), magnitude):
            continue  # we already escaped relative to the other member
        return False
    return True


def _rank_dofs(
    key: int,
    dofs: List[TranslationDof],
    step_ordering: Ordering,
    step_joints: List[AssemblyJoint],
    positions: Dict[int, _Float3],
    own_ordering: Dict[int, Ordering],
    removed: set,
) -> List[TranslationDof]:
    """Rank candidate escape DOFs, best first.

    Preference (see score weights): directions every same-step joint of this
    member already frees (no dragging of same-step partners), then away from
    the other members of this step, then away from later-extracted members,
    then roughly planar with this step's members.
    """
    step_member_keys = {
        member_key
        for joint in step_joints
        for member_key in joint.members
        if member_key not in removed
    }
    peers = [member_key for member_key in step_member_keys if member_key != key]

    later_keys = {
        member_key
        for member_key, member_ordering in own_ordering.items()
        if member_ordering > step_ordering and member_key not in removed and member_key != key
    }

    plane_normal = _dominant_plane_normal([positions[member_key] for member_key in sorted(step_member_keys)])

    my_position = positions[key]
    my_step_joints = [
        joint for joint in step_joints
        if key in joint.members
        and joint.members[key].ordering == step_ordering
        and _spec_has_translations(joint.members[key])
    ]

    def away_score(direction: _Float3, other_keys) -> float:
        score = 0.0
        count = 0
        for other_key in other_keys:
            toward_me = _unit3(_sub3(my_position, positions[other_key]))
            if toward_me is None:
                continue
            score += _dot3(direction, toward_me)
            count += 1
        return score / count if count else 0.0

    def score(dof: TranslationDof) -> float:
        direction = _unit3(_float3(dof.direction))
        if direction is None:
            return float("-inf")
        shared = 1.0 if all(
            _freedom_allows(joint.members[key].freedom, direction) is not None
            for joint in my_step_joints
        ) else 0.0
        away_same = away_score(direction, peers)
        away_later = away_score(direction, later_keys)
        planarity = (1.0 - abs(_dot3(direction, plane_normal))) if plane_normal is not None else 0.0
        return 8.0 * shared + 4.0 * away_same + 2.0 * away_later + 1.0 * planarity

    return sorted(dofs, key=score, reverse=True)


def _propagate(
    start_key: int,
    direction: _Float3,
    distance: float,
    step_ordering: Ordering,
    joints_by_member: Dict[int, List[AssemblyJoint]],
    member_by_key: Dict[int, AssemblyMember],
    own_ordering: Dict[int, Ordering],
    removed: set,
    records: Dict[int, List[Tuple[_Float3, float]]],
    loop_counts: Dict[int, int],
) -> List[str]:
    """The recursive "attempt to move" from the design notes, as a worklist.

    Moving a member by (direction, distance) checks each of its joints: if the
    joint's freedom for the mover allows the direction, the joint lets it slide
    and its other members stay; otherwise every other member is rigidly dragged
    by the same vector (unless its own freedom in that joint allows the
    opposite relative motion), recursively.

    Loop cap semantics (an interpretation of the "up to 6 loops" note): a
    member's movement record CHANGING after it already has one — a new
    non-parallel direction, or a strictly larger distance — counts as one loop
    iteration for that member. Re-visits that converge (same direction, same or
    smaller distance) are free, so ordinary cycles like A→B→A settle in one
    lap; the counter only climbs when multiple movers keep re-disturbing the
    same member, which is the genuinely over-constrained case.
    """
    trial_warnings: List[str] = []
    queue = deque([(start_key, ())])

    while queue:
        key, chain = queue.popleft()
        record = records.setdefault(key, [])

        converged = any(
            _are_parallel(recorded_direction, direction) and recorded_distance >= distance - _ZERO_EPSILON
            for recorded_direction, recorded_distance in record
        )
        if converged:
            continue

        if record:
            loop_counts[key] = loop_counts.get(key, 0) + 1
            if loop_counts[key] > _MAX_LOOP_ITERATIONS:
                raise _LoopDetected(member_key=key, chain=chain)

        merged = False
        for index, (recorded_direction, recorded_distance) in enumerate(record):
            if _are_parallel(recorded_direction, direction):
                record[index] = (recorded_direction, max(recorded_distance, distance))
                merged = True
                break
        if not merged:
            record.append((direction, distance))

        if key != start_key:
            member_own_ordering = own_ordering.get(key)
            if member_own_ordering is not None and member_own_ordering > step_ordering:
                trial_warnings.append(
                    f"Disassembling step {step_ordering.label()} dragged member "
                    f"'{member_by_key[key].name}' whose own ordering is {member_own_ordering.label()}"
                )

        # Members extracted at earlier steps are in `removed`, which also
        # releases their joints' grip (no joint-level release check needed).
        for joint in joints_by_member.get(key, []):
            my_spec = joint.members.get(key)
            if my_spec is not None and _freedom_allows(my_spec.freedom, direction) is not None:
                continue  # the joint lets this member slide in `direction`; nothing to drag
            for other_key, other_spec in joint.members.items():
                if other_key == key or other_key in removed:
                    continue
                if _freedom_allows(other_spec.freedom, _neg3(direction)) is not None:
                    continue  # relative motion allowed from the other member's side
                queue.append((other_key, chain + ((key, joint.name, other_key),)))

    return trial_warnings


def _merge_movements(
    step_ordering: Ordering,
    step_records: Dict[int, List[Tuple[_Float3, float]]],
    primary_movers: set,
    member_by_key: Dict[int, AssemblyMember],
    warnings: List[str],
) -> List[MemberMovement]:
    """Collapse each member's contributions into one net movement (numeric)."""
    movements: List[MemberMovement] = []
    for key in sorted(step_records, key=lambda record_key: (member_by_key[record_key].name, record_key)):
        net: _Float3 = (0.0, 0.0, 0.0)
        for direction, distance in step_records[key]:
            net = _add3(net, _scale3(direction, distance))
        magnitude = _norm3(net)
        if magnitude < _ZERO_EPSILON:
            warnings.append(
                f"Drag directions for member '{member_by_key[key].name}' cancelled out at "
                f"step {step_ordering.label()}; it does not move"
            )
            continue
        unit = _scale3(net, 1.0 / magnitude)
        movements.append(
            MemberMovement(
                member_key=key,
                direction=create_v3(sp.Float(unit[0]), sp.Float(unit[1]), sp.Float(unit[2])),
                distance=sp.Float(magnitude),
                dragged=key not in primary_movers,
            )
        )
    return movements


def _describe_loop(
    loop: _LoopDetected,
    dof_direction: _Float3,
    member_by_key: Dict[int, AssemblyMember],
) -> str:
    """Human-readable diagnostic for one failed DOF attempt."""
    direction_text = f"({dof_direction[0]:.3f}, {dof_direction[1]:.3f}, {dof_direction[2]:.3f})"
    member_name = member_by_key[loop.member_key].name
    if loop.chain:
        chain_text = member_by_key[loop.chain[0][0]].name
        for from_key, joint_name, to_key in loop.chain:
            chain_text += f" --[{joint_name}]--> {member_by_key[to_key].name}"
    else:
        chain_text = member_name
    return (
        f"DOF direction {direction_text}: member '{member_name}' kept being re-dragged "
        f"(more than {_MAX_LOOP_ITERATIONS} movement changes); drag chain: {chain_text}"
    )
