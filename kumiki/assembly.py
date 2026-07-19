"""Assembly constraints and the assembly (disassembly) solver.

Each member (timber or accessory) in each joint may declare an AssemblyFreedom:
the set of degrees of freedom in which it can move to escape that joint, each
with a "freed after" amount — the travel after which the joint no longer
constrains the member. Each member additionally carries an Ordering
(order, suborder), compared lexicographically; smaller = extracted EARLIER
during disassembly (i.e. installed later during assembly). The suborder
expresses sequencing REQUIRED within a joint (locking accessories are authored
at suborder -1 so they pop before the members slide at suborder 0); the order
is the frame-level plan, assigned afterwards via Joint.with_order.

The solver follows docs/plans/assembly-solver-v2.md: it separates JOINTS by
moving GROUPS.

- Phase 1: per ordering, repeatedly pick a (target member, escape direction),
  grow the minimal rigid moving group via monotone closure, and emit a
  micro-step that separates at least one scheduled joint pair. Per-pair
  relative-displacement state replaces any notion of merged member motion.
- Phase 1b: when no closure candidate exists, attempt a simultaneous
  multi-velocity motion: per connected component of the engaged-pair graph,
  solve for one velocity per rigid cluster such that every pair's relative
  velocity lies on an authored ray (cycle constraints telescope to zero).
  Handles interlocked rings and radial structures that no two-handed move can
  separate; members naturally travel at different speeds.
- Phase 2: anchored centering — when every active member belongs to the
  current ordering (no stationary complement), each substep's motion is
  recentred about the group so the scene expands symmetrically.
- Phase 3: compaction — consecutive micro-steps with disjoint groups and no
  engaged pair between them animate as one substep (pegs pop together).
- Phase 4: clear-out — parked (fully separated) members sitting in a later
  step's swept path are pushed clear, front-to-back in a single pass.

The solver is deliberately timber-agnostic: it operates on an abstract graph
of AssemblyMember / AssemblyJoint records so it can be tested without
constructing any timbers, and so this module only depends on kumiki.rule
(timber.py imports from here, never the reverse). ``solve_frame_assembly`` in
timber.py adapts a Frame into this graph.

The solver is kinematic/topological, not geometric: it trusts the declared
freedoms and does no collision checking (Phase 4's bbox pass is a visual aid,
not a proof). A "solved" disassembly is a preview aid.

Rotational freedoms are declared (RotationDof) but not solved yet; the solver
raises NotImplementedError when it encounters one.
"""

import math
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple

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
# Phase 4: minimum gap kept between a mover's swept path and parked members.
_DEFAULT_CLEAROUT_CLEARANCE = 0.025


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

    ``suborder`` expresses sequencing required WITHIN a joint (locking
    accessories at -1 pop before members at 0) and is authored by the joint
    cut functions; ``order`` is the frame-level plan set via Joint.with_order.
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
class BoundingBox:
    """Axis-aligned box in GLOBAL space; used only by the Phase 4 clear-out."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float


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
    # Optional global-space bounds for the Phase 4 clear-out pass.
    bbox: Optional[BoundingBox] = None


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
    member moved only because it was rigidly pulled along (or pushed clear),
    not because it was being extracted itself.
    """

    member_key: int
    direction: Direction3D
    distance: Numeric
    dragged: bool


@dataclass(frozen=True)
class AssemblyStep:
    """One animated substep. ``ordering`` is the authored (order, suborder);
    ``substep`` (1-based) sequences the solver-generated motions within it."""

    ordering: Ordering
    movements: Tuple[MemberMovement, ...]
    substep: int = 1


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
# Float helpers (the whole solver runs in plain Python floats; sympy values
# are converted exactly once while building the internal graph)
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


def _axis_key(axis: _Float3) -> Tuple[float, float, float]:
    return (round(axis[0], 9), round(axis[1], 9), round(axis[2], 9))


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
# Internal pair-engagement state
# ============================================================================


class _Ray:
    """One allowed escape axis for a pair, expressed as the relative motion of
    the pair's ``m`` member with respect to its ``p`` member.

    ``owners`` records which member(s) authored the axis and at which
    Ordering; a member may only be a PRIMARY extraction target along rays it
    authored, at its own ordering (a peg's escape axis must not schedule the
    timber it locks).
    """

    __slots__ = ("axis", "freed_after", "owners")

    def __init__(self, axis: _Float3, freed_after: float,
                 owners: List[Tuple[int, Ordering]]):
        self.axis = axis
        self.freed_after = freed_after
        self.owners = owners


class _Pair:
    """Engagement state of one member pair within one joint.

    Keyed by joint INDEX (never by joint name — names are type strings shared
    by many joints). ``relative_displacement`` is the cumulative motion of m
    relative to p; separation latches when its projection on some ray reaches
    that ray's freed_after, and the keep-out margin is the overshoot past it.
    """

    __slots__ = (
        "index", "joint_index", "joint_name", "m", "p", "rays",
        "scheduled_orderings", "relative_displacement",
        "separated", "separation_axis", "separation_freed", "separated_at_seq",
    )

    def __init__(self, index: int, joint_index: int, joint_name: str,
                 m: int, p: int, rays: List[_Ray],
                 scheduled_orderings: Set[Ordering]):
        self.index = index
        self.joint_index = joint_index
        self.joint_name = joint_name
        self.m = m
        self.p = p
        self.rays = rays
        self.scheduled_orderings = scheduled_orderings
        self.relative_displacement: _Float3 = (0.0, 0.0, 0.0)
        self.separated = False
        self.separation_axis: Optional[_Float3] = None
        self.separation_freed = 0.0
        self.separated_at_seq = -1

    def other(self, key: int) -> int:
        return self.p if key == self.m else self.m

    def ray_for(self, relative_direction: _Float3) -> Optional[_Ray]:
        for ray in self.rays:
            if _dot3(ray.axis, relative_direction) >= 1.0 - _PARALLEL_DOT_TOLERANCE:
                return ray
        return None

    def remaining_travel(self, ray: _Ray) -> float:
        return max(0.0, ray.freed_after - _dot3(self.relative_displacement, ray.axis))

    def keepout_margin(self) -> float:
        """Overshoot past freed_after along the separation axis (>= 0)."""
        if not self.separated or self.separation_axis is None:
            return 0.0
        return _dot3(self.relative_displacement, self.separation_axis) - self.separation_freed

    def apply_relative_delta(self, delta: _Float3, seq: int) -> bool:
        """Accumulate relative motion; returns True when this call separated the pair."""
        self.relative_displacement = _add3(self.relative_displacement, delta)
        if self.separated:
            return False
        for ray in self.rays:
            if _dot3(self.relative_displacement, ray.axis) >= ray.freed_after - _ZERO_EPSILON:
                self.separated = True
                self.separation_axis = ray.axis
                self.separation_freed = ray.freed_after
                self.separated_at_seq = seq
                return True
        return False


def _spec_has_translations(spec: JointMemberSpec) -> bool:
    return spec.freedom is not None and bool(spec.freedom.translations)


def _build_pairs(
    joints: Sequence[AssemblyJoint],
) -> Tuple[List[_Pair], Dict[int, List[_Pair]]]:
    """Build per-pair engagement records (floats only) from the input joints."""
    pairs: List[_Pair] = []
    pairs_by_member: Dict[int, List[_Pair]] = {}

    def freedom_rays(member_key: int, spec: JointMemberSpec, sign: float) -> List[_Ray]:
        rays: List[_Ray] = []
        if spec.freedom is None:
            return rays
        for dof in spec.freedom.translations:
            axis = _unit3(_float3(dof.direction))
            if axis is None:
                continue
            rays.append(_Ray(_scale3(axis, sign), float(giraffe_evalf(dof.freed_after)),
                             [(member_key, spec.ordering)]))
        return rays

    for joint_index, joint in enumerate(joints):
        keys = sorted(joint.members.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                m, p = keys[i], keys[j]
                spec_m = joint.members[m]
                spec_p = joint.members[p]
                rays: List[_Ray] = []
                for candidate in freedom_rays(m, spec_m, 1.0) + freedom_rays(p, spec_p, -1.0):
                    merged = False
                    for existing in rays:
                        if _are_parallel(existing.axis, candidate.axis):
                            existing.freed_after = min(existing.freed_after, candidate.freed_after)
                            existing.owners = existing.owners + candidate.owners
                            merged = True
                            break
                    if not merged:
                        rays.append(candidate)
                scheduled: Set[Ordering] = set()
                if _spec_has_translations(spec_m):
                    scheduled.add(spec_m.ordering)
                if _spec_has_translations(spec_p):
                    scheduled.add(spec_p.ordering)
                pair = _Pair(len(pairs), joint_index, joint.name, m, p, rays, scheduled)
                pairs.append(pair)
                pairs_by_member.setdefault(m, []).append(pair)
                pairs_by_member.setdefault(p, []).append(pair)
    return pairs, pairs_by_member


# ============================================================================
# Phase 1 — closure
# ============================================================================


def _closure(
    target: int,
    direction: _Float3,
    pairs_by_member: Dict[int, List[_Pair]],
    forced_drag: Optional[Set[int]] = None,
) -> Tuple[Set[int], Dict[int, Tuple[int, str]]]:
    """Minimal set of members that must move rigidly together along ``direction``.

    Monotone set growth: an engaged pair whose relative motion is not on an
    allowed ray drags the partner in; a separated pair drags the partner only
    when the motion would re-enter it AND there is no keep-out margin left
    (margin-limited re-entry is permitted here and capped later via the step
    distance). ``forced_drag`` pairs re-couple regardless of margin — the
    candidate evaluation adds pairs whose margin cap would block the needed
    travel and re-runs the closure. Returns (group, parent) where parent maps
    each dragged member to (from_member, joint_name) for chain diagnostics.
    """
    group: Set[int] = {target}
    frontier = deque([target])
    parent: Dict[int, Tuple[int, str]] = {}

    while frontier:
        x = frontier.popleft()
        for pair in pairs_by_member.get(x, []):
            other = pair.other(x)
            if other in group:
                continue
            relative = direction if x == pair.m else _neg3(direction)
            if pair.separated:
                axis = pair.separation_axis
                if axis is not None and _dot3(relative, axis) < -_ZERO_EPSILON \
                        and (pair.keepout_margin() <= _ZERO_EPSILON
                             or (forced_drag is not None and pair.index in forced_drag)):
                    group.add(other)
                    parent[other] = (x, pair.joint_name)
                    frontier.append(other)
                continue
            if pair.ray_for(relative) is None:
                group.add(other)
                parent[other] = (x, pair.joint_name)
                frontier.append(other)
    return group, parent


class _Candidate:
    __slots__ = ("target", "direction", "group", "parent", "distance",
                 "crossing", "separating_count", "score")

    def __init__(self, target, direction, group, parent, distance, crossing,
                 separating_count, score):
        self.target = target
        self.direction = direction
        self.group = group
        self.parent = parent
        self.distance = distance
        # crossing: list of (pair, ray, relative_direction) for every engaged
        # pair with exactly one end in the group.
        self.crossing = crossing
        self.separating_count = separating_count
        self.score = score


def _evaluate_candidate(
    target: int,
    direction: _Float3,
    ordering: "Ordering",
    pairs_by_member: Dict[int, List[_Pair]],
    member_by_key: Dict[int, AssemblyMember],
    member_min_ordering: Dict[int, Ordering],
    positions: Dict[int, _Float3],
    active_members: Set[int],
    plane_normal: Optional[_Float3],
) -> Optional[_Candidate]:
    """Run closure for one (target, direction) and score it; None if invalid.

    When a separated pair's keep-out margin would cap the travel below what is
    needed to separate even the easiest scheduled crossing pair, that pair is
    re-coupled (its parked partner dragged along) and the closure re-runs —
    disturbing parked members is preferred over deadlocking, and the scoring
    penalizes it so undisturbing candidates still win when they exist.
    """
    forced: Set[int] = set()
    while True:
        group, parent = _closure(target, direction, pairs_by_member, forced)

        crossing: List[Tuple[_Pair, _Ray, _Float3]] = []
        keepout_caps: List[Tuple[float, int]] = []
        seen_pairs: Set[int] = set()
        for member in group:
            for pair in pairs_by_member.get(member, []):
                if pair.index in seen_pairs:
                    continue
                seen_pairs.add(pair.index)
                if (pair.m in group) == (pair.p in group):
                    continue  # internal, or neither end moves
                relative = direction if pair.m in group else _neg3(direction)
                if pair.separated:
                    axis = pair.separation_axis
                    if axis is not None:
                        rate = -_dot3(relative, axis)
                        if rate > _ZERO_EPSILON:
                            keepout_caps.append((pair.keepout_margin() / rate, pair.index))
                    continue
                ray = pair.ray_for(relative)
                if ray is None:
                    return None  # closure invariant violated (should not happen)
                crossing.append((pair, ray, relative))

        scheduled_remaining = [
            pair.remaining_travel(ray)
            for pair, ray, _ in crossing
            if ordering in pair.scheduled_orderings
        ]
        if not scheduled_remaining:
            return None  # separates nothing scheduled (e.g. group absorbed the frame)

        easiest = min(scheduled_remaining)
        blocking = {index for cap, index in keepout_caps if cap < easiest - _ZERO_EPSILON}
        if blocking - forced:
            forced |= blocking
            continue  # re-run closure with the parked partners dragged along

        distance = max(scheduled_remaining)
        if keepout_caps:
            distance = min(distance, min(cap for cap, _ in keepout_caps))
        if distance < easiest - _ZERO_EPSILON or distance <= _ZERO_EPSILON:
            return None
        break

    separating_count = sum(
        1 for pair, ray, _ in crossing
        if ordering in pair.scheduled_orderings
        and pair.remaining_travel(ray) <= distance + _ZERO_EPSILON
    )

    later_drag_count = sum(
        1 for member in group
        if member != target
        and member in member_min_ordering
        and member_min_ordering[member] > ordering
    )

    # Direction heuristics: away from the active complement's centroid, away
    # from later-extracted members, roughly planar with the layout.
    complement = [m for m in active_members if m not in group]
    away = 0.0
    if complement:
        cx = sum(positions[m][0] for m in complement) / len(complement)
        cy = sum(positions[m][1] for m in complement) / len(complement)
        cz = sum(positions[m][2] for m in complement) / len(complement)
        toward_me = _unit3(_sub3(positions[target], (cx, cy, cz)))
        if toward_me is not None:
            away = _dot3(direction, toward_me)
    later_members = [m for m in active_members
                     if m in member_min_ordering and member_min_ordering[m] > ordering]
    away_later = 0.0
    if later_members:
        count = 0
        for m in later_members:
            toward_me = _unit3(_sub3(positions[target], positions[m]))
            if toward_me is None:
                continue
            away_later += _dot3(direction, toward_me)
            count += 1
        away_later = away_later / count if count else 0.0
    planarity = (1.0 - abs(_dot3(direction, plane_normal))) if plane_normal is not None else 0.0
    direction_score = 4.0 * away + 2.0 * away_later + 1.0 * planarity

    score = (
        later_drag_count,
        len(forced),
        len(group) / separating_count,
        len(keepout_caps),
        -direction_score,
        member_by_key[target].name,
        target,
        _axis_key(direction),
    )
    return _Candidate(target, direction, group, parent, distance, crossing,
                      separating_count, score)


def _chain_text(target: int, absorbed: int, parent: Dict[int, Tuple[int, str]],
                member_by_key: Dict[int, AssemblyMember]) -> str:
    """"target --[joint]--> ... --> absorbed" from closure parent pointers."""
    hops: List[Tuple[int, str]] = []
    current = absorbed
    while current != target and current in parent:
        from_member, joint_name = parent[current]
        hops.append((current, joint_name))
        current = from_member
    text = member_by_key[target].name
    for member, joint_name in reversed(hops):
        text += f" --[{joint_name}]--> {member_by_key[member].name}"
    return text


# ============================================================================
# Phase 1b — simultaneous multi-velocity escape
# ============================================================================


# Relative-velocity directions from the numeric solve carry small drift, so
# ray validation for simultaneous steps uses this slightly relaxed tolerance.
_SIMULTANEOUS_PARALLEL_TOLERANCE = 1e-5
# Relative speeds below this fraction of the fastest member are treated as
# "these members do not separate in this step".
_SIMULTANEOUS_SPEED_EPSILON = 1e-6
# Cap on ray-choice combinations for edges with multiple non-collinear rays.
_SIMULTANEOUS_COMBO_CAP = 64


def _orthonormalize(vectors: List[List[float]]) -> List[List[float]]:
    """Gram-Schmidt with a drop tolerance RELATIVE to each vector's original
    norm. Rank decisions here must never hinge on an absolute threshold:
    float cancellation noise in a dependent row once got counted as an extra
    rank, which cost the nullspace the exact dimension carrying the odd-n
    stool's simultaneous solution."""
    basis: List[List[float]] = []
    for vector in vectors:
        original_norm = math.sqrt(sum(a * a for a in vector))
        if original_norm < 1e-300:
            continue
        working = list(vector)
        for existing in basis:
            projection = sum(a * b for a, b in zip(working, existing))
            working = [a - projection * b for a, b in zip(working, existing)]
        norm = math.sqrt(sum(a * a for a in working))
        if norm >= 1e-9 * original_norm:
            basis.append([a / norm for a in working])
    return basis


def _nullspace_basis(rows: List[List[float]], columns: int) -> List[List[float]]:
    """ORTHONORMAL nullspace basis via the row-space complement.

    The row space is orthonormalized with a relative drop tolerance (that is
    where the rank decision happens); each standard basis vector is then
    projected onto the orthogonal complement and orthonormalized. An empty
    ``rows`` yields the standard basis. This construction is robust against
    the float cancellation noise that made the previous RREF implementation
    overestimate rank (see _orthonormalize).
    """
    row_basis = _orthonormalize(rows) if rows else []
    basis: List[List[float]] = []
    for index in range(columns):
        working = [0.0] * columns
        working[index] = 1.0
        for existing in row_basis:
            projection = sum(a * b for a, b in zip(working, existing))
            working = [a - projection * b for a, b in zip(working, existing)]
        for existing in basis:
            projection = sum(a * b for a, b in zip(working, existing))
            working = [a - projection * b for a, b in zip(working, existing)]
        norm = math.sqrt(sum(a * a for a in working))
        if norm >= 1e-9:  # relative to |e_index| = 1
            basis.append([a / norm for a in working])
    return basis


def _sign_feasible_null_vector(
    null_basis: List[List[float]],
    half_line: Set[int],
    scheduled: Set[int],
) -> Optional[List[float]]:
    """A vector in span(null_basis), normalized to max |x| = 1, with x_e >= 0
    on half-line coordinates and |x_e| > 0 on some scheduled coordinate.

    Tries the basis vectors and their sum directly (which covers symmetric
    structures, whose solution IS the symmetric nullspace direction), then
    alternating projection between the nullspace and the sign orthant. The
    result is approximate; the caller re-validates reconstructed velocities.
    """
    if not null_basis:
        return None
    dimension = len(null_basis[0])

    def project(x: List[float]) -> List[float]:
        out = [0.0] * dimension
        for basis_vector in null_basis:
            dot = sum(a * b for a, b in zip(x, basis_vector))
            for i in range(dimension):
                out[i] += dot * basis_vector[i]
        return out

    def normalize_feasible(x: List[float]) -> Optional[List[float]]:
        largest = max(abs(a) for a in x)
        if largest < 1e-9:
            return None
        x = [a / largest for a in x]
        if any(x[i] < -1e-6 for i in half_line):
            if all(-x[i] >= -1e-6 for i in half_line):
                x = [-a for a in x]
            else:
                return None
        if not any(abs(x[i]) > 1e-6 for i in scheduled):
            return None
        return [0.0 if (i in half_line and a < 0.0) else a for i, a in enumerate(x)]

    candidates = [list(b) for b in null_basis]
    if len(null_basis) > 1:
        candidates.append([sum(components) for components in zip(*null_basis)])
    for candidate in candidates:
        result = normalize_feasible(candidate)
        if result is not None:
            return result

    seeds = [[1.0] * dimension]
    for index in sorted(scheduled):
        seed = [0.0] * dimension
        seed[index] = 1.0
        seeds.append(seed)
    for seed in seeds:
        x = seed
        for _ in range(300):
            x = project(x)
            x = [0.0 if (i in half_line and a < 0.0) else a for i, a in enumerate(x)]
        x = project(x)
        result = normalize_feasible(x)
        if result is not None:
            return result

    return _lp_sign_feasible_null_vector(null_basis, half_line, scheduled)


# Guardrails for the exact-arithmetic LP backstop: beyond these sizes the
# rational simplex could get slow, and the heuristics-only answer stands.
_LP_MAX_NULLSPACE_DIM = 24
_LP_MAX_CONSTRAINTS = 96


def _lp_sign_feasible_null_vector(
    null_basis: List[List[float]],
    half_line: Set[int],
    scheduled: Set[int],
) -> Optional[List[float]]:
    """Exact backstop for the heuristic search (which can miss thin feasible
    cones): maximize the total motion on scheduled coordinates over the
    nullspace, subject to the half-line signs, with box-bounded coefficients.
    A positive optimum IS a valid simultaneous motion; zero means none exists
    for this ray combo. Uses sympy's rational simplex — exact, deterministic,
    and cheap at Phase 1b's component sizes.
    """
    if not null_basis or not scheduled:
        return None
    dimension = len(null_basis[0])
    coefficients = len(null_basis)
    if coefficients > _LP_MAX_NULLSPACE_DIM or len(half_line) > _LP_MAX_CONSTRAINTS:
        return None
    try:
        from sympy.solvers.simplex import linprog as simplex_linprog
    except ImportError:
        return None

    rational_basis = [[sp.Rational(component) for component in vector] for vector in null_basis]
    # Minimize the negated scheduled-motion sum; constrain -(B·λ)_e <= 0 on
    # half-line coordinates; box λ so the LP is bounded.
    objective = [-sum(vector[e] for e in scheduled) for vector in rational_basis]
    constraint_rows = [
        [-vector[e] for vector in rational_basis]
        for e in sorted(half_line)
    ]
    constraint_bounds = [sp.Integer(0)] * len(constraint_rows)
    try:
        optimum, point = simplex_linprog(
            objective,
            A=constraint_rows,
            b=constraint_bounds,
            bounds=[(-1, 1)] * coefficients,
        )
    except Exception:  # noqa: BLE001 — the LP must never break solving
        return None
    if float(-optimum) <= 1e-9:
        return None

    coefficients_solution = [float(value) for value in point]
    x = [
        sum(coefficients_solution[j] * null_basis[j][e] for j in range(coefficients))
        for e in range(dimension)
    ]
    largest = max(abs(value) for value in x)
    if largest < 1e-9:
        return None
    x = [value / largest for value in x]
    if not any(abs(x[e]) > 1e-9 for e in scheduled):
        return None
    return [0.0 if (e in half_line and value < 0.0) else value for e, value in enumerate(x)]


def _attempt_simultaneous_step(
    ordering: Ordering,
    pairs: List[_Pair],
) -> Optional[Dict[int, _Float3]]:
    """Phase 1b: a simultaneous multi-velocity motion when no rigid group
    works (interlocked rings, splayed radial structures).

    Contracts rigid pairs into clusters and treats each connected component of
    the engaged-pair graph as one linear system: every edge's relative
    velocity must be x_e times its ray axis (x_e >= 0 for half-line edges,
    free for bidirectional ones), and every independent cycle must telescope
    to zero. A sign-feasible nullspace vector of the cycle constraints gives
    per-cluster velocities via the spanning tree; validation re-checks every
    engaged pair and keep-out picks the stationary anchor. Returns member
    displacements scaled so every separating pair fully separates, or None.
    """
    engaged = [pair for pair in pairs if not pair.separated]
    if not engaged:
        return None

    cluster_parent: Dict[int, int] = {}

    def find(key: int) -> int:
        root = key
        while cluster_parent.get(root, root) != root:
            root = cluster_parent[root]
        while cluster_parent.get(key, key) != key:
            cluster_parent[key], key = root, cluster_parent[key]
        return root

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            cluster_parent[max(root_a, root_b)] = min(root_a, root_b)

    members_involved: Set[int] = set()
    for pair in engaged:
        members_involved.add(pair.m)
        members_involved.add(pair.p)
        if not pair.rays:
            union(pair.m, pair.p)

    cluster_members: Dict[int, List[int]] = {}
    for member in members_involved:
        cluster_members.setdefault(find(member), []).append(member)

    edge_pairs: List[_Pair] = []
    adjacency: Dict[int, List[Tuple[int, int]]] = {}
    for pair in engaged:
        if not pair.rays:
            continue
        cluster_m, cluster_p = find(pair.m), find(pair.p)
        if cluster_m == cluster_p:
            continue
        edge_index = len(edge_pairs)
        edge_pairs.append(pair)
        adjacency.setdefault(cluster_m, []).append((edge_index, cluster_p))
        adjacency.setdefault(cluster_p, []).append((edge_index, cluster_m))
    if not edge_pairs:
        return None

    # Per-edge axis options, oriented as: relative velocity of the pair's
    # m-side cluster minus its p-side cluster equals x_e * axis. A ray and its
    # exact opposite collapse into one free-sign option; non-collinear
    # alternatives stay separate options (combos capped).
    edge_options: List[List[Tuple[_Float3, bool]]] = []
    for pair in edge_pairs:
        options: List[Tuple[_Float3, bool]] = []
        consumed: Set[int] = set()
        for i, ray in enumerate(pair.rays):
            if i in consumed:
                continue
            free = False
            for j in range(i + 1, len(pair.rays)):
                if j in consumed:
                    continue
                if _dot3(pair.rays[j].axis, ray.axis) <= -(1.0 - _PARALLEL_DOT_TOLERANCE):
                    consumed.add(j)
                    free = True
                    break
            consumed.add(i)
            options.append((ray.axis, free))
        edge_options.append(options)

    seen_clusters: Set[int] = set()
    for start in sorted(adjacency.keys()):
        if start in seen_clusters:
            continue
        component: Set[int] = {start}
        frontier = deque([start])
        while frontier:
            cluster = frontier.popleft()
            for _, neighbor in adjacency.get(cluster, []):
                if neighbor not in component:
                    component.add(neighbor)
                    frontier.append(neighbor)
        seen_clusters |= component

        component_edges = [
            index for index, pair in enumerate(edge_pairs) if find(pair.m) in component
        ]
        if not any(
            ordering in edge_pairs[index].scheduled_orderings for index in component_edges
        ):
            continue
        result = _solve_simultaneous_component(
            ordering=ordering,
            component=component,
            component_edges=component_edges,
            edge_pairs=edge_pairs,
            edge_options=edge_options,
            adjacency=adjacency,
            cluster_members=cluster_members,
            find=find,
            pairs=pairs,
        )
        if result is not None:
            return result
    return None


def _solve_simultaneous_component(
    ordering: Ordering,
    component: Set[int],
    component_edges: List[int],
    edge_pairs: List[_Pair],
    edge_options: List[List[Tuple[_Float3, bool]]],
    adjacency: Dict[int, List[Tuple[int, int]]],
    cluster_members: Dict[int, List[int]],
    find,
    pairs: List[_Pair],
) -> Optional[Dict[int, _Float3]]:
    local_of_edge = {edge_index: k for k, edge_index in enumerate(component_edges)}
    edge_count = len(component_edges)

    # Spanning tree (BFS) and per-cluster tree paths as (local edge, sign)
    # where sign is +1 when walking from the p-side to the m-side.
    root = min(component)
    tree_path: Dict[int, List[Tuple[int, float]]] = {root: []}
    tree_edges: Set[int] = set()
    frontier = deque([root])
    while frontier:
        cluster = frontier.popleft()
        for edge_index, neighbor in sorted(adjacency.get(cluster, [])):
            if neighbor in tree_path:
                continue
            pair = edge_pairs[edge_index]
            sign = 1.0 if find(pair.m) == neighbor else -1.0
            tree_path[neighbor] = tree_path[cluster] + [(local_of_edge[edge_index], sign)]
            tree_edges.add(edge_index)
            frontier.append(neighbor)
    non_tree = [index for index in component_edges if index not in tree_edges]

    choice_edges = [index for index in component_edges if len(edge_options[index]) > 1]

    def option_combos():
        if not choice_edges:
            yield {}
            return
        budget = _SIMULTANEOUS_COMBO_CAP
        counters = [0] * len(choice_edges)
        while budget > 0:
            budget -= 1
            yield {edge: counters[k] for k, edge in enumerate(choice_edges)}
            position = len(choice_edges) - 1
            while position >= 0:
                counters[position] += 1
                if counters[position] < len(edge_options[choice_edges[position]]):
                    break
                counters[position] = 0
                position -= 1
            if position < 0:
                return

    for combo in option_combos():
        axes: List[_Float3] = []
        half_line: Set[int] = set()
        for edge_index in component_edges:
            option = edge_options[edge_index][combo.get(edge_index, 0)]
            axes.append(option[0])
            if not option[1]:
                half_line.add(local_of_edge[edge_index])

        # Cycle constraints: for each non-tree edge f between clusters a
        # (m-side) and b (p-side): (v_a - v_b) - x_f * axis_f = 0, with v
        # expressed through tree-path coefficients.
        rows: List[List[float]] = []
        for edge_index in non_tree:
            pair = edge_pairs[edge_index]
            side_m, side_p = find(pair.m), find(pair.p)
            for axis_component in range(3):
                row = [0.0] * edge_count
                for local, sign in tree_path[side_m]:
                    row[local] += sign * axes[local][axis_component]
                for local, sign in tree_path[side_p]:
                    row[local] -= sign * axes[local][axis_component]
                row[local_of_edge[edge_index]] -= axes[local_of_edge[edge_index]][axis_component]
                rows.append(row)

        scheduled_locals = {
            local_of_edge[index] for index in component_edges
            if ordering in edge_pairs[index].scheduled_orderings
        }
        null_basis = _nullspace_basis(rows, edge_count)  # already orthonormal
        x = _sign_feasible_null_vector(null_basis, half_line, scheduled_locals)
        if x is None:
            continue

        # Reconstruct cluster velocities from the tree.
        velocity: Dict[int, _Float3] = {}
        for cluster in component:
            total = (0.0, 0.0, 0.0)
            for local, sign in tree_path[cluster]:
                total = _add3(total, _scale3(axes[local], sign * x[local]))
            velocity[cluster] = total

        member_velocity: Dict[int, _Float3] = {}
        for cluster in component:
            for member in cluster_members.get(cluster, []):
                member_velocity[member] = velocity[cluster]

        speed_reference = max(_norm3(vector) for vector in velocity.values())
        if speed_reference < 1e-9:
            continue
        stationary_threshold = _SIMULTANEOUS_SPEED_EPSILON * speed_reference

        # Validate every engaged pair of the component against its rays
        # (relative velocities are anchor-independent).
        feasible = True
        active_pairs: List[Tuple[_Pair, float, _Ray]] = []
        for pair in pairs:
            if pair.separated:
                continue
            if pair.m not in member_velocity and pair.p not in member_velocity:
                continue
            difference = _sub3(member_velocity.get(pair.m, (0.0, 0.0, 0.0)),
                               member_velocity.get(pair.p, (0.0, 0.0, 0.0)))
            magnitude = _norm3(difference)
            if magnitude <= stationary_threshold:
                continue
            unit = _scale3(difference, 1.0 / magnitude)
            matched: Optional[_Ray] = None
            for ray in pair.rays:
                if _dot3(ray.axis, unit) >= 1.0 - _SIMULTANEOUS_PARALLEL_TOLERANCE:
                    matched = ray
                    break
            if matched is None:
                feasible = False
                break
            active_pairs.append((pair, magnitude, matched))
        if not feasible or not active_pairs:
            continue
        if not any(ordering in pair.scheduled_orderings for pair, _, _ in active_pairs):
            continue

        # One shared scale so every active pair fully separates.
        scale = 0.0
        for pair, magnitude, ray in active_pairs:
            scale = max(scale, pair.remaining_travel(ray) / magnitude)
        if scale <= _ZERO_EPSILON:
            continue

        # Keep-out decides the anchor: uniform shifts change no relative
        # velocity, so try anchoring each cluster (largest first) until
        # separated pairs to stationary members stop re-entering.
        anchors = sorted(
            component,
            key=lambda cluster: (-len(cluster_members.get(cluster, [])), cluster),
        )
        for anchor in anchors:
            shift = velocity[anchor]
            shifted = {
                member: _sub3(vector, shift)
                for member, vector in member_velocity.items()
            }
            violated = False
            for pair in pairs:
                if not pair.separated or pair.separation_axis is None:
                    continue
                difference = _sub3(shifted.get(pair.m, (0.0, 0.0, 0.0)),
                                   shifted.get(pair.p, (0.0, 0.0, 0.0)))
                if _norm3(difference) < _ZERO_EPSILON:
                    continue
                projected = _dot3(
                    _add3(pair.relative_displacement, _scale3(difference, scale)),
                    pair.separation_axis,
                )
                if projected < pair.separation_freed - _ZERO_EPSILON:
                    violated = True
                    break
            if violated:
                continue
            return {member: _scale3(vector, scale)
                    for member, vector in shifted.items()
                    if _norm3(vector) > stationary_threshold * scale}
    return None


# ============================================================================
# Solver
# ============================================================================


def solve_assembly(
    members: Sequence[AssemblyMember],
    joints: Sequence[AssemblyJoint],
    clearout_clearance: float = _DEFAULT_CLEAROUT_CLEARANCE,
) -> Optional[AssemblySolution]:
    """Solve the disassembly sequence for an abstract assembly graph.

    Returns None when no member has any translational freedom. On an
    unsolvable ordering the already-solved steps (including the failing
    ordering's earlier substeps) are returned with an AssemblyFailure — it
    never raises for unsolvability.

    Raises NotImplementedError for rotational freedoms and ValueError for
    joints referencing unknown member keys.
    """
    member_by_key: Dict[int, AssemblyMember] = {member.key: member for member in members}
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

    step_orderings = sorted({
        spec.ordering
        for joint in joints
        for spec in joint.members.values()
        if _spec_has_translations(spec)
    })
    if not step_orderings:
        return None

    member_orderings: Dict[int, Set[Ordering]] = {}
    for joint in joints:
        for key, spec in joint.members.items():
            if _spec_has_translations(spec):
                member_orderings.setdefault(key, set()).add(spec.ordering)
    member_min_ordering = {key: min(values) for key, values in member_orderings.items()}

    positions: Dict[int, _Float3] = {member.key: _float3(member.position) for member in members}
    pairs, pairs_by_member = _build_pairs(joints)

    engaged_count: Dict[int, int] = {member.key: 0 for member in members}
    for pair in pairs:
        engaged_count[pair.m] += 1
        engaged_count[pair.p] += 1
    removed: Set[int] = {key for key, count in engaged_count.items() if count == 0}

    warnings: List[str] = []
    warned: Set[Tuple[int, Ordering]] = set()
    steps: List[AssemblyStep] = []
    removed_before_step: List[Set[int]] = []
    failure: Optional[AssemblyFailure] = None
    sequence = 0  # micro-step counter; pairs record the seq they separated at

    def note_separation(pair: _Pair, ordering: Ordering) -> None:
        engaged_count[pair.m] -= 1
        engaged_count[pair.p] -= 1
        for key in (pair.m, pair.p):
            if engaged_count[key] == 0:
                removed.add(key)
        if pair.scheduled_orderings and all(o > ordering for o in pair.scheduled_orderings):
            warnings.append(
                f"Joint '{pair.joint_name}' separated incidentally during step {ordering.label()}"
            )

    def warn_dragged(group: Set[int], primaries: Set[int], ordering: Ordering) -> None:
        for key in sorted(group):
            if key in primaries:
                continue
            own = member_min_ordering.get(key)
            if own is not None and own > ordering and (key, ordering) not in warned:
                warned.add((key, ordering))
                warnings.append(
                    f"Disassembling step {ordering.label()} dragged member "
                    f"'{member_by_key[key].name}' whose own ordering is {own.label()}"
                )

    for ordering in step_orderings:
        removed_at_ordering_start = set(removed)
        active_members = {key for key in member_by_key if key not in removed_at_ordering_start}
        ms_members = {key for key in active_members
                      if ordering in member_orderings.get(key, ())}
        cs_members = active_members - ms_members
        plane_normal = _dominant_plane_normal(
            [positions[key] for key in sorted(ms_members)]
        ) if ms_members else None

        # Substep accumulator (Phase 3): list of (movement map, primaries,
        # start sequence). A micro-step merges into the open substep when its
        # group is disjoint AND every pair between them was separated before
        # the substep began.
        ordering_substeps: List[Tuple[Dict[int, _Float3], Set[int], int]] = []

        def emit_micro(movements: Dict[int, _Float3], primaries: Set[int],
                       mergeable: bool) -> None:
            if mergeable and ordering_substeps:
                current_map, current_primaries, start_seq = ordering_substeps[-1]
                if not (set(movements) & set(current_map)):
                    blocked = False
                    for key in movements:
                        for pair in pairs_by_member.get(key, []):
                            if pair.other(key) not in current_map:
                                continue
                            if not pair.separated or pair.separated_at_seq >= start_seq:
                                blocked = True
                                break
                        if blocked:
                            break
                    if not blocked:
                        current_map.update(movements)
                        current_primaries.update(primaries)
                        return
            ordering_substeps.append((dict(movements), set(primaries), sequence))

        while failure is None:
            scheduled_pairs = [
                pair for pair in pairs
                if not pair.separated and ordering in pair.scheduled_orderings
            ]
            if not scheduled_pairs:
                break

            # A ray only makes its AUTHOR a primary target, at the author's
            # own ordering: at a peg's suborder step the peg pops — the timber
            # it locks must not be extracted early via the same interface.
            candidate_inputs: Dict[Tuple[int, Tuple[float, float, float]], Tuple[int, _Float3]] = {}
            for pair in scheduled_pairs:
                for ray in pair.rays:
                    for owner_key, owner_ordering in ray.owners:
                        if owner_ordering != ordering:
                            continue
                        direction = ray.axis if owner_key == pair.m else _neg3(ray.axis)
                        candidate_inputs.setdefault((owner_key, _axis_key(direction)), (owner_key, direction))

            best: Optional[_Candidate] = None
            for target, direction in sorted(
                candidate_inputs.values(),
                key=lambda item: (member_by_key[item[0]].name, item[0], _axis_key(item[1])),
            ):
                candidate = _evaluate_candidate(
                    target, direction, ordering, pairs_by_member, member_by_key,
                    member_min_ordering, positions, active_members, plane_normal,
                )
                if candidate is None:
                    continue
                if best is None or candidate.score < best.score:
                    best = candidate

            if best is None:
                ring = _attempt_simultaneous_step(ordering, pairs)
                if ring is not None:
                    sequence += 1
                    primaries: Set[int] = set()
                    for pair in scheduled_pairs:
                        delta = _sub3(ring.get(pair.m, (0.0, 0.0, 0.0)),
                                      ring.get(pair.p, (0.0, 0.0, 0.0)))
                        if _norm3(delta) > _ZERO_EPSILON:
                            primaries.add(pair.m)
                            primaries.add(pair.p)
                    for pair in pairs:
                        delta = _sub3(ring.get(pair.m, (0.0, 0.0, 0.0)),
                                      ring.get(pair.p, (0.0, 0.0, 0.0)))
                        if _norm3(delta) < _ZERO_EPSILON:
                            continue
                        was_separated = pair.separated
                        pair.apply_relative_delta(delta, sequence)
                        if not was_separated and pair.separated:
                            note_separation(pair, ordering)
                    warn_dragged(set(ring), primaries, ordering)
                    emit_micro(ring, primaries & set(ring), mergeable=False)
                    continue

                diagnostics: List[str] = []
                for pair in scheduled_pairs[:8]:
                    for target in (pair.m, pair.p):
                        partner = pair.other(target)
                        for ray in pair.rays:
                            direction = ray.axis if target == pair.m else _neg3(ray.axis)
                            group, parent = _closure(target, direction, pairs_by_member)
                            if partner in group:
                                diagnostics.append(
                                    f"moving '{member_by_key[target].name}' along "
                                    f"({direction[0]:.3f}, {direction[1]:.3f}, {direction[2]:.3f}) "
                                    f"absorbs its partner: "
                                    f"{_chain_text(target, partner, parent, member_by_key)}"
                                )
                first = scheduled_pairs[0]
                failure = AssemblyFailure(
                    ordering=ordering,
                    message=(
                        f"Cannot disassemble step {ordering.label()}: no valid extraction "
                        f"found for {len(scheduled_pairs)} remaining joint pair(s), e.g. "
                        f"'{member_by_key[first.m].name}' / '{member_by_key[first.p].name}' "
                        f"in joint '{first.joint_name}'"
                    ),
                    diagnostics=tuple(diagnostics[:12]),
                )
                break

            # Execute the winning micro-step: the group translates rigidly, so
            # only crossing pairs accumulate relative motion (engaged crossing
            # pairs were validated by closure; separated crossing pairs track
            # their keep-out margin).
            sequence += 1
            for pair, ray, relative in best.crossing:
                was_separated = pair.separated
                pair.apply_relative_delta(_scale3(relative, best.distance), sequence)
                if not was_separated and pair.separated:
                    note_separation(pair, ordering)
            updated = {pair.index for pair, _, _ in best.crossing}
            for member in best.group:
                for pair in pairs_by_member.get(member, []):
                    if pair.index in updated:
                        continue
                    if (pair.m in best.group) == (pair.p in best.group):
                        continue
                    updated.add(pair.index)
                    relative = best.direction if pair.m in best.group else _neg3(best.direction)
                    pair.relative_displacement = _add3(
                        pair.relative_displacement,
                        _scale3(relative, best.distance),
                    )
            warn_dragged(best.group, {best.target}, ordering)
            emit_micro(
                {member: _scale3(best.direction, best.distance) for member in best.group},
                {best.target},
                mergeable=True,
            )

        # Phase 2 (anchored centering) + emission of this ordering's substeps.
        for substep_index, (movement_map, primaries, _) in enumerate(ordering_substeps):
            final_map = dict(movement_map)
            if ms_members and not cs_members:
                total = (0.0, 0.0, 0.0)
                for key in ms_members:
                    total = _add3(total, final_map.get(key, (0.0, 0.0, 0.0)))
                average = _scale3(total, 1.0 / len(ms_members))
                if _norm3(average) > _ZERO_EPSILON:
                    for key in ms_members:
                        final_map[key] = _sub3(final_map.get(key, (0.0, 0.0, 0.0)), average)
            movements: List[MemberMovement] = []
            for key in sorted(final_map, key=lambda k: (member_by_key[k].name, k)):
                vector = final_map[key]
                magnitude = _norm3(vector)
                if magnitude < _ZERO_EPSILON:
                    continue
                unit = _scale3(vector, 1.0 / magnitude)
                movements.append(MemberMovement(
                    member_key=key,
                    direction=create_v3(sp.Float(unit[0]), sp.Float(unit[1]), sp.Float(unit[2])),
                    distance=sp.Float(magnitude),
                    dragged=key not in primaries,
                ))
            if movements:
                steps.append(AssemblyStep(ordering=ordering, movements=tuple(movements),
                                          substep=substep_index + 1))
                removed_before_step.append(removed_at_ordering_start)

        if failure is not None:
            break

    _clear_out(steps, removed_before_step, member_by_key, clearout_clearance)

    return AssemblySolution(steps=tuple(steps), warnings=tuple(warnings), failure=failure)


# ============================================================================
# Phase 4 — clear-out (parked members pushed out of swept paths)
# ============================================================================


def _bbox_at(bbox: BoundingBox, offset: _Float3) -> Tuple[float, float, float, float, float, float]:
    return (bbox.min_x + offset[0], bbox.max_x + offset[0],
            bbox.min_y + offset[1], bbox.max_y + offset[1],
            bbox.min_z + offset[2], bbox.max_z + offset[2])


def _boxes_intersect(a, b) -> bool:
    return (a[0] <= b[1] and b[0] <= a[1]
            and a[2] <= b[3] and b[2] <= a[3]
            and a[4] <= b[5] and b[4] <= a[5])


def _project_box(box, direction: _Float3) -> Tuple[float, float]:
    """(min, max) projection of an AABB onto a direction."""
    low_total = 0.0
    high_total = 0.0
    for axis in range(3):
        component = direction[axis]
        low, high = box[axis * 2], box[axis * 2 + 1]
        if component >= 0.0:
            low_total += component * low
            high_total += component * high
        else:
            low_total += component * high
            high_total += component * low
    return low_total, high_total


def _clear_out(
    steps: List[AssemblyStep],
    removed_before_step: List[Set[int]],
    member_by_key: Dict[int, AssemblyMember],
    clearance: float,
) -> None:
    """Push parked (already fully separated) members out of movers' swept
    paths. Parked members are processed front-to-back along the mover's
    direction in a single pass, so each is pushed at most once per mover and
    pushes only ever go forward — no recursion, no leapfrogging. Mutates
    ``steps`` in place; pushes appear as dragged movements."""
    cumulative: Dict[int, _Float3] = {}

    for step_index, step in enumerate(steps):
        movers: Dict[int, _Float3] = {}
        for movement in step.movements:
            direction = _float3(movement.direction)
            distance = float(giraffe_evalf(movement.distance))
            movers[movement.member_key] = _scale3(direction, distance)

        parked = [key for key in removed_before_step[step_index]
                  if key not in movers and member_by_key[key].bbox is not None]
        pushes: Dict[int, _Float3] = {}

        for mover_key in sorted(movers, key=lambda k: (member_by_key[k].name, k)):
            vector = movers[mover_key]
            magnitude = _norm3(vector)
            mover_bbox = member_by_key[mover_key].bbox
            if magnitude < _ZERO_EPSILON or mover_bbox is None:
                continue
            direction = _scale3(vector, 1.0 / magnitude)
            start_offset = cumulative.get(mover_key, (0.0, 0.0, 0.0))
            start_box = _bbox_at(mover_bbox, start_offset)
            end_box = _bbox_at(mover_bbox, _add3(start_offset, vector))
            hull = tuple(
                min(start_box[i], end_box[i]) if i % 2 == 0 else max(start_box[i], end_box[i])
                for i in range(6)
            )
            start_min, _ = _project_box(start_box, direction)
            _, end_max = _project_box(end_box, direction)

            in_path: List[Tuple[float, float, int]] = []
            for parked_key in parked:
                parked_bbox = member_by_key[parked_key].bbox
                if parked_bbox is None:
                    continue
                parked_box = _bbox_at(
                    parked_bbox,
                    _add3(cumulative.get(parked_key, (0.0, 0.0, 0.0)),
                          pushes.get(parked_key, (0.0, 0.0, 0.0))),
                )
                if not _boxes_intersect(hull, parked_box):
                    continue
                parked_min, parked_max = _project_box(parked_box, direction)
                if parked_min < start_min - _ZERO_EPSILON:
                    continue  # behind the mover's start: not in the path
                in_path.append((parked_min, parked_max, parked_key))

            floor = end_max + clearance
            for parked_min, parked_max, parked_key in sorted(in_path):
                if parked_min < floor - _ZERO_EPSILON:
                    push_distance = floor - parked_min
                    pushes[parked_key] = _add3(
                        pushes.get(parked_key, (0.0, 0.0, 0.0)),
                        _scale3(direction, push_distance),
                    )
                    floor = parked_max + push_distance + clearance

        if pushes:
            extra: List[MemberMovement] = []
            for key in sorted(pushes, key=lambda k: (member_by_key[k].name, k)):
                vector = pushes[key]
                magnitude = _norm3(vector)
                if magnitude < _ZERO_EPSILON:
                    continue
                unit = _scale3(vector, 1.0 / magnitude)
                extra.append(MemberMovement(
                    member_key=key,
                    direction=create_v3(sp.Float(unit[0]), sp.Float(unit[1]), sp.Float(unit[2])),
                    distance=sp.Float(magnitude),
                    dragged=True,
                ))
                cumulative[key] = _add3(cumulative.get(key, (0.0, 0.0, 0.0)), vector)
            steps[step_index] = AssemblyStep(
                ordering=step.ordering,
                movements=tuple(list(step.movements) + extra),
                substep=step.substep,
            )

        for key, vector in movers.items():
            cumulative[key] = _add3(cumulative.get(key, (0.0, 0.0, 0.0)), vector)
