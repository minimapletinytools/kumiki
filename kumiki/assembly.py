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
class BoundingBox:
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float

    def translate(self, dx: float, dy: float, dz: float) -> "BoundingBox":
        return BoundingBox(
            min_x=self.min_x + dx,
            max_x=self.max_x + dx,
            min_y=self.min_y + dy,
            max_y=self.max_y + dy,
            min_z=self.min_z + dz,
            max_z=self.max_z + dz,
        )


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
    # Optional bounding box in global coordinates.
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
    substep: int
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
# Pair Engagement State & Solver
# ============================================================================


class PairState:
    def __init__(self, m: int, p: int, joint: AssemblyJoint):
        self.m = m
        self.p = p
        self.joint = joint
        self.separated = False
        self.separation_direction = None  # unit relative vector m w.r.t p
        self.travels: Dict[_Float3, float] = {}  # dof_unit -> accumulated_travel


def _get_allowed_dof(joint: AssemblyJoint, m: int, p: int, direction: _Float3) -> Optional[TranslationDof]:
    """Return the TranslationDof for m or p that allows relative motion of m w.r.t p along direction."""
    spec_m = joint.members.get(m)
    if spec_m is not None:
        dof_m = _freedom_allows(spec_m.freedom, direction)
        if dof_m is not None:
            return dof_m
    spec_p = joint.members.get(p)
    if spec_p is not None:
        dof_p = _freedom_allows(spec_p.freedom, _neg3(direction))
        if dof_p is not None:
            return dof_p
    return None


def _closure(
    target: int,
    d: _Float3,
    pair_states: Dict[Tuple[str, int, int], PairState],
    removed: set,
    joints_by_member: Dict[int, List[AssemblyJoint]]
) -> Tuple[set, Dict[int, Tuple[int, str, int]]]:
    """Grow group monotonically using monotone set growth."""
    G = {target}
    frontier = [target]
    chains: Dict[int, Tuple[int, str, int]] = {}

    while frontier:
        x = frontier.pop(0)
        for joint in joints_by_member.get(x, []):
            for other in joint.members:
                if other == x or other in removed or other in G:
                    continue

                p_key = (joint.name, min(x, other), max(x, other))
                p_state = pair_states[p_key]

                if p_state.separated:
                    # Keep-out violation check:
                    # rel_dir is the relative direction of m w.r.t p when x moves d and other is stationary.
                    rel_dir = d if x == p_state.m else _neg3(d)
                    if _dot3(rel_dir, p_state.separation_direction) < -_ZERO_EPSILON:
                        G.add(other)
                        frontier.append(other)
                        chains[other] = (x, joint.name, other)
                    else:
                        continue
                else:
                    # Engaged pair check
                    dof = _get_allowed_dof(joint, x, other, d)
                    if dof is not None:
                        continue
                    else:
                        G.add(other)
                        frontier.append(other)
                        chains[other] = (x, joint.name, other)

    return G, chains


def _reconstruct_chain(target: int, blocked_key: int, chains: Dict[int, Tuple[int, str, int]]) -> Tuple[Tuple[int, str, int], ...]:
    path = []
    curr = blocked_key
    while curr != target and curr in chains:
        edge = chains[curr]
        path.append(edge)
        curr = edge[0]
    return tuple(reversed(path))


def _score_candidate(
    t: int,
    d: _Float3,
    G: set,
    own_ordering: Dict[int, Set[Ordering]],
    step_ordering: Ordering,
    positions: Dict[int, _Float3],
    step_member_keys: set,
    plane_normal: Optional[_Float3]
) -> Tuple[int, int, float]:
    later_dragged_count = sum(1 for x in G if any(step > step_ordering for step in own_ordering.get(x, {step_ordering})))
    g_size = len(G)

    peers = [member_key for member_key in step_member_keys if member_key != t]
    later_keys = {
        member_key
        for member_key, steps in own_ordering.items()
        if any(step > step_ordering for step in steps) and member_key != t
    }

    my_position = positions[t]

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

    away_same = away_score(d, peers)
    away_later = away_score(d, later_keys)
    planarity = (1.0 - abs(_dot3(d, plane_normal))) if plane_normal is not None else 0.0

    dir_score = 4.0 * away_same + 2.0 * away_later + 1.0 * planarity
    return (later_dragged_count, g_size, -dir_score)


def _can_merge(
    G1: set,
    G2: set,
    pair_states: Dict[Tuple[str, int, int], PairState],
    joints_by_member: Dict[int, List[AssemblyJoint]]
) -> bool:
    if not G1.isdisjoint(G2):
        return False
    for x in G1:
        for joint in joints_by_member.get(x, []):
            for other in joint.members:
                if other in G2:
                    p_key = (joint.name, min(x, other), max(x, other))
                    if not pair_states[p_key].separated:
                        return False
    return True


def _project_bbox_min(bbox: BoundingBox, d: _Float3) -> float:
    corners = [
        (bbox.min_x, bbox.min_y, bbox.min_z),
        (bbox.min_x, bbox.min_y, bbox.max_z),
        (bbox.min_x, bbox.max_y, bbox.min_z),
        (bbox.min_x, bbox.max_y, bbox.max_z),
        (bbox.max_x, bbox.min_y, bbox.min_z),
        (bbox.max_x, bbox.min_y, bbox.max_z),
        (bbox.max_x, bbox.max_y, bbox.min_z),
        (bbox.max_x, bbox.max_y, bbox.max_z),
    ]
    return min(_dot3(c, d) for c in corners)


def _project_bbox_max(bbox: BoundingBox, d: _Float3) -> float:
    corners = [
        (bbox.min_x, bbox.min_y, bbox.min_z),
        (bbox.min_x, bbox.min_y, bbox.max_z),
        (bbox.min_x, bbox.max_y, bbox.min_z),
        (bbox.min_x, bbox.max_y, bbox.max_z),
        (bbox.max_x, bbox.min_y, bbox.min_z),
        (bbox.max_x, bbox.min_y, bbox.max_z),
        (bbox.max_x, bbox.max_y, bbox.min_z),
        (bbox.max_x, bbox.max_y, bbox.max_z),
    ]
    return max(_dot3(c, d) for c in corners)


def _push_member(
    step_index: int,
    member_key: int,
    push_vector: _Float3,
    push_distance: float,
    step_movements: Dict[int, Tuple[_Float3, float, bool]],
    cum_displacements: Dict[int, _Float3],
    member_by_key: Dict[int, AssemblyMember],
    freed_before_step: set
):
    current_mov = step_movements.get(member_key)
    if current_mov is not None:
        d_curr, dist_curr, dragged = current_mov
        net_v = _add3(_scale3(d_curr, dist_curr), _scale3(push_vector, push_distance))
        mag = _norm3(net_v)
        if mag > _ZERO_EPSILON:
            step_movements[member_key] = (_scale3(net_v, 1.0 / mag), mag, dragged)
        else:
            step_movements.pop(member_key, None)
    else:
        step_movements[member_key] = (push_vector, push_distance, True)

    new_cum = _add3(cum_displacements[member_key], _scale3(push_vector, push_distance))
    cum_displacements[member_key] = new_cum

    my_bbox = member_by_key[member_key].bbox
    if my_bbox is None:
        return

    my_active_bbox = my_bbox.translate(*new_cum)

    for other_key in freed_before_step:
        if other_key == member_key:
            continue
        other_bbox = member_by_key[other_key].bbox
        if other_bbox is None:
            continue

        other_active_bbox = other_bbox.translate(*cum_displacements[other_key])

        if (max(my_active_bbox.min_x, other_active_bbox.min_x) <= min(my_active_bbox.max_x, other_active_bbox.max_x) and
            max(my_active_bbox.min_y, other_active_bbox.min_y) <= min(my_active_bbox.max_y, other_active_bbox.max_y) and
            max(my_active_bbox.min_z, other_active_bbox.min_z) <= min(my_active_bbox.max_z, other_active_bbox.max_z)):

            p_my_max = _project_bbox_max(my_active_bbox, push_vector)
            p_other_min = _project_bbox_min(other_active_bbox, push_vector)

            clearance = 0.0254  # 1 inch
            if p_other_min < p_my_max + clearance:
                cascade_push = (p_my_max + clearance) - p_other_min
                _push_member(step_index, other_key, push_vector, cascade_push, step_movements, cum_displacements, member_by_key, freed_before_step)


def _spec_has_translations(spec: JointMemberSpec) -> bool:
    return spec.freedom is not None and bool(spec.freedom.translations)


def solve_assembly(
    members: Sequence[AssemblyMember],
    joints: Sequence[AssemblyJoint],
) -> Optional[AssemblySolution]:
    """Solve the disassembly sequence for an abstract assembly graph using the v2 design."""
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

    own_ordering: Dict[int, Set[Ordering]] = {}
    for joint in joints:
        for key, spec in joint.members.items():
            if _spec_has_translations(spec):
                own_ordering.setdefault(key, set()).add(spec.ordering)

    positions: Dict[int, _Float3] = {member.key: _float3(member.position) for member in members}

    pair_states: Dict[Tuple[str, int, int], PairState] = {}
    for joint in joints:
        keys = sorted(joint.members.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                m, p = keys[i], keys[j]
                pair_states[(joint.name, m, p)] = PairState(m, p, joint)

    removed = set()
    warnings: List[str] = []
    steps: List[AssemblyStep] = []
    failure = None

    for step_ordering in step_orderings:
        removed_at_start = set(removed)

        scheduled_pairs = []
        for joint in joints:
            keys = sorted(joint.members.keys())
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    m, p = keys[i], keys[j]
                    p_state = pair_states[(joint.name, m, p)]
                    if p_state.separated:
                        continue
                    spec_m = joint.members[m]
                    spec_p = joint.members[p]
                    cond = (spec_m.ordering == step_ordering and _spec_has_translations(spec_m)) or \
                           (spec_p.ordering == step_ordering and _spec_has_translations(spec_p))
                    if cond:
                        scheduled_pairs.append(p_state)

        micro_steps: List[Tuple[int, set, _Float3, float, List[PairState], dict]] = []
        
        step_member_keys = {
            member_key
            for joint in joints
            for member_key in joint.members
            if member_key not in removed and any(
                (joint.members[k].ordering == step_ordering and _spec_has_translations(joint.members[k]))
                for k in joint.members
            )
        }
        plane_normal = _dominant_plane_normal([positions[member_key] for member_key in sorted(step_member_keys)])

        failure = None
        primary_movers = set()

        while True:
            active_scheduled_pairs = [p for p in scheduled_pairs if not p.separated and p.m not in removed and p.p not in removed]
            if not active_scheduled_pairs:
                break

            candidates = []
            for p_state in active_scheduled_pairs:
                for target in (p_state.m, p_state.p):
                    if target in removed:
                        continue
                    other = p_state.p if target == p_state.m else p_state.m
                    
                    target_dirs = []
                    spec_target = p_state.joint.members[target]
                    if spec_target.freedom is not None:
                        for dof in spec_target.freedom.translations:
                            d = _unit3(_float3(dof.direction))
                            if d is not None:
                                target_dirs.append(d)
                    spec_other = p_state.joint.members[other]
                    if spec_other.freedom is not None:
                        for dof in spec_other.freedom.translations:
                            d = _unit3(_float3(dof.direction))
                            if d is not None:
                                target_dirs.append(_neg3(d))
                                
                    for d in target_dirs:
                        G, chains = _closure(target, d, pair_states, removed_at_start, joints_by_member)
                        crossing_pairs = []
                        for p in active_scheduled_pairs:
                            if (p.m in G) != (p.p in G):
                                crossing_pairs.append(p)
                                
                        if crossing_pairs:
                            candidates.append((target, d, G, crossing_pairs, chains))

            if not candidates:
                diagnostics = []
                for p_state in active_scheduled_pairs:
                    for target in (p_state.m, p_state.p):
                        if target in removed or target not in own_ordering:
                            continue
                        other = p_state.p if target == p_state.m else p_state.m
                        
                        target_dirs = []
                        spec_target = p_state.joint.members[target]
                        if spec_target.freedom is not None:
                            for dof in spec_target.freedom.translations:
                                d = _unit3(_float3(dof.direction))
                                if d is not None:
                                    target_dirs.append(d)
                        spec_other = p_state.joint.members[other]
                        if spec_other.freedom is not None:
                            for dof in spec_other.freedom.translations:
                                d = _unit3(_float3(dof.direction))
                                if d is not None:
                                    target_dirs.append(_neg3(d))
                                    
                        for d in target_dirs:
                            G, chains = _closure(target, d, pair_states, removed_at_start, joints_by_member)
                            partner = p_state.p if target == p_state.m else p_state.m
                            if partner in G:
                                path = _reconstruct_chain(target, partner, chains)
                                chain_text = member_by_key[target].name
                                for from_k, j_name, to_k in path:
                                    chain_text += f" --[{j_name}]--> {member_by_key[to_k].name}"
                                diagnostics.append(
                                    f"DOF direction ({d[0]:.3f}, {d[1]:.3f}, {d[2]:.3f}): member '{member_by_key[target].name}' kept being re-dragged (more than 6 movement changes); drag chain: {chain_text}"
                                )
                
                if not diagnostics:
                    diagnostics = [f"No candidates found for step {step_ordering.label()}"]
                msg = (
                    f"Cannot disassemble step {step_ordering.label()}: member '{member_by_key[active_scheduled_pairs[0].m].name}' has no "
                    f"workable DOF; every direction keeps re-dragging other members past the loop limit (6)"
                )
                failure = AssemblyFailure(ordering=step_ordering, message=msg, diagnostics=tuple(diagnostics))
                break

            candidates.sort(key=lambda c: (
                not (c[0] in own_ordering),
                _score_candidate(c[0], c[1], c[2], own_ordering, step_ordering, positions, step_member_keys, plane_normal),
                member_by_key[c[0]].name,
                c[0],
                c[1]
            ))
            target, d, G, crossing_pairs, chains = candidates[0]

            D = 0.0
            for p_state in crossing_pairs:
                if p_state.separated:
                    continue
                x = p_state.m if p_state.m in G else p_state.p
                other = p_state.p if x == p_state.m else p_state.m
                rel_dir = d if x == p_state.m else _neg3(d)
                dof = _get_allowed_dof(p_state.joint, p_state.m, p_state.p, rel_dir)
                assert dof is not None
                dof_unit = _unit3(_float3(dof.direction))
                travel = p_state.travels.get(dof_unit, 0.0)
                remaining = max(0.0, float(giraffe_evalf(dof.freed_after)) - travel)
                if remaining > D:
                    D = remaining

            if D < _ZERO_EPSILON:
                D = _ZERO_EPSILON

            micro_steps.append((target, G, d, D, crossing_pairs, chains))
            primary_movers.add(target)

            for x in G:
                if x != target:
                    member_own_ordering = own_ordering.get(x)
                    if member_own_ordering is not None and any(step > step_ordering for step in member_own_ordering):
                        orderings_label = ", ".join(step.label() for step in sorted(member_own_ordering))
                        warnings.append(
                            f"Disassembling step {step_ordering.label()} dragged member "
                            f"'{member_by_key[x].name}' whose own ordering is {orderings_label}"
                        )

            for p_state in pair_states.values():
                if p_state.separated:
                    continue
                if (p_state.m in G) != (p_state.p in G):
                    x = p_state.m if p_state.m in G else p_state.p
                    other = p_state.p if x == p_state.m else p_state.m
                    rel_dir = d if x == p_state.m else _neg3(d)
                    dof = _get_allowed_dof(p_state.joint, p_state.m, p_state.p, rel_dir)
                    if dof is not None:
                        dof_unit = _unit3(_float3(dof.direction))
                        current_travel = p_state.travels.get(dof_unit, 0.0)
                        new_travel = current_travel + D
                        p_state.travels[dof_unit] = new_travel
                        
                        freed_dist = float(giraffe_evalf(dof.freed_after))
                        if new_travel >= freed_dist - _ZERO_EPSILON:
                            p_state.separated = True
                            p_state.separation_direction = rel_dir
                            
                            spec_m = p_state.joint.members[p_state.m]
                            spec_p = p_state.joint.members[p_state.p]
                            is_later = False
                            if spec_m.ordering > step_ordering and _spec_has_translations(spec_m):
                                is_later = True
                            if spec_p.ordering > step_ordering and _spec_has_translations(spec_p):
                                is_later = True
                            if is_later:
                                warnings.append(
                                    f"Joint '{p_state.joint.name}' separated incidentally during step {step_ordering.label()}"
                                )

            removed.update(primary_movers)

            for key in list(member_by_key.keys()):
                if key in removed:
                    continue
                my_joints = joints_by_member.get(key, [])
                if not my_joints:
                    removed.add(key)
                    continue
                all_separated = True
                for joint in my_joints:
                    for other in joint.members:
                        if other == key or other in removed:
                            continue
                        p_key = (joint.name, min(key, other), max(key, other))
                        if not pair_states[p_key].separated:
                            all_separated = False
                            break
                    if not all_separated:
                        break
                if all_separated:
                    removed.add(key)

            # Detached components check
            active_members = {m.key for m in members if m.key not in removed}
            adj = {u: set() for u in active_members}
            for p_state in pair_states.values():
                if not p_state.separated:
                    if p_state.m in active_members and p_state.p in active_members:
                        adj[p_state.m].add(p_state.p)
                        adj[p_state.p].add(p_state.m)
            
            visited = set()
            for u in active_members:
                if u not in visited:
                    comp = []
                    queue = [u]
                    visited.add(u)
                    while queue:
                        curr = queue.pop(0)
                        comp.append(curr)
                        for nxt in adj[curr]:
                            if nxt not in visited:
                                visited.add(nxt)
                                queue.append(nxt)
                    has_active_internal_joints = False
                    for p_state in active_scheduled_pairs:
                        if p_state.m in comp and p_state.p in comp:
                            has_active_internal_joints = True
                            break
                    if not has_active_internal_joints:
                        if all(own_ordering.get(x) is not None and all(step <= step_ordering for step in own_ordering[x]) for x in comp):
                            removed.update(comp)

        if failure is not None:
            break

        M_S = {key for key in own_ordering if step_ordering in own_ordering[key] and key not in removed_at_start}
        C_S = {key for key in member_by_key if key not in M_S and key not in removed_at_start}

        allowed_target_dirs = {}
        for p_state in scheduled_pairs:
            for target in (p_state.m, p_state.p):
                if target in removed_at_start or target not in own_ordering:
                    continue
                other = p_state.p if target == p_state.m else p_state.m
                
                target_dirs = []
                spec_target = p_state.joint.members[target]
                if spec_target.freedom is not None:
                    for dof in spec_target.freedom.translations:
                        d = _unit3(_float3(dof.direction))
                        if d is not None:
                            target_dirs.append(d)
                spec_other = p_state.joint.members[other]
                if spec_other.freedom is not None:
                    for dof in spec_other.freedom.translations:
                        d = _unit3(_float3(dof.direction))
                        if d is not None:
                            target_dirs.append(_neg3(d))
                
                allowed_target_dirs.setdefault(target, []).extend(target_dirs)

        # Validate target movements using total step velocities
        total_velocities: Dict[int, _Float3] = {}
        for _, G, d, D, _, _ in micro_steps:
            for key in G:
                prev_v = total_velocities.get(key, (0.0, 0.0, 0.0))
                total_velocities[key] = _add3(prev_v, _scale3(d, D))

        for key, v in total_velocities.items():
            if key in allowed_target_dirs:
                mag = _norm3(v)
                if mag > _ZERO_EPSILON:
                    unit = _scale3(v, 1.0 / mag)
                    is_allowed = False
                    for d in allowed_target_dirs[key]:
                        if _are_parallel(d, unit):
                            is_allowed = True
                            break
                    if not is_allowed:
                        msg = (
                            f"Cannot disassemble step {step_ordering.label()}: member '{member_by_key[key].name}' moved in a non-allowed direction "
                            f"({unit[0]:.3f}, {unit[1]:.3f}, {unit[2]:.3f}) due to rigid linking."
                        )
                        diagnostics = []
                        for target_m, G_m, d_m, _, _, chains_m in micro_steps:
                            if key in G_m:
                                path = _reconstruct_chain(target_m, key, chains_m)
                                chain_text = member_by_key[target_m].name
                                for from_k, j_name, to_k in path:
                                    chain_text += f" --[{j_name}]--> {member_by_key[to_k].name}"
                                diagnostics.append(
                                    f"DOF direction ({d_m[0]:.3f}, {d_m[1]:.3f}, {d_m[2]:.3f}): member '{member_by_key[key].name}' kept being re-dragged (more than 6 movement changes); drag chain: {chain_text}"
                                )
                        if not diagnostics:
                            diagnostics = [f"No candidates found for step {step_ordering.label()}"]
                        failure = AssemblyFailure(ordering=step_ordering, message=msg, diagnostics=tuple(diagnostics))
                        break
        if failure is not None:
            break

        compacted_substeps: List[List[Tuple[set, _Float3, float, dict]]] = []
        for _, G, d, D, _, chains in micro_steps:
            if compacted_substeps and all(_can_merge(G, other[0], pair_states, joints_by_member) for other in compacted_substeps[-1]):
                compacted_substeps[-1].append((G, d, D, chains))
            else:
                compacted_substeps.append([(G, d, D, chains)])

        for substep_idx, comp_list in enumerate(compacted_substeps):
            raw_velocities: Dict[int, _Float3] = {}
            for G, d, D, _ in comp_list:
                for key in G:
                    prev_v = raw_velocities.get(key, (0.0, 0.0, 0.0))
                    raw_velocities[key] = _add3(prev_v, _scale3(d, D))
            
            if not C_S and M_S:
                sum_v = (0.0, 0.0, 0.0)
                for key in M_S:
                    sum_v = _add3(sum_v, raw_velocities.get(key, (0.0, 0.0, 0.0)))
                v_avg = _scale3(sum_v, 1.0 / len(M_S))
                
                for key in M_S:
                    v_raw = raw_velocities.get(key, (0.0, 0.0, 0.0))
                    raw_velocities[key] = _sub3(v_raw, v_avg)

            movements = []
            for key in sorted(raw_velocities.keys(), key=lambda k: (member_by_key[k].name, k)):
                v = raw_velocities[key]
                mag = _norm3(v)
                if mag < _ZERO_EPSILON:
                    sum_abs = 0.0
                    for G, d, D, _ in comp_list:
                        if key in G:
                            sum_abs += D
                    if sum_abs > _ZERO_EPSILON:
                        warnings.append(
                            f"Drag directions for member '{member_by_key[key].name}' cancelled out at "
                            f"step {step_ordering.label()}; it does not move"
                        )
                    continue
                unit = _scale3(v, 1.0 / mag)
                is_target = key in primary_movers
                
                movements.append(
                    MemberMovement(
                        member_key=key,
                        direction=create_v3(sp.Float(unit[0]), sp.Float(unit[1]), sp.Float(unit[2])),
                        distance=sp.Float(mag),
                        dragged=not is_target,
                    )
                )

            steps.append(AssemblyStep(ordering=step_ordering, substep=substep_idx + 1, movements=tuple(movements)))

        if failure is not None:
            break

    # Phase 4 Clear-out pass
    cum_displacements: Dict[int, _Float3] = {m.key: (0.0, 0.0, 0.0) for m in members}
    freed_before_step = set()
    
    for step_idx, step in enumerate(steps):
        step_movements = {mov.member_key: (_float3(mov.direction), float(giraffe_evalf(mov.distance)), mov.dragged) for mov in step.movements}
        moving_keys = list(step_movements.keys())
        
        for B in moving_keys:
            B_dir, B_dist, B_dragged = step_movements[B]
            B_bbox = member_by_key[B].bbox
            if B_bbox is None:
                continue
            
            B_active_start = B_bbox.translate(*cum_displacements[B])
            B_active_end = B_bbox.translate(*_add3(cum_displacements[B], _scale3(B_dir, B_dist)))
            
            B_swept = BoundingBox(
                min_x=min(B_active_start.min_x, B_active_end.min_x),
                max_x=max(B_active_start.max_x, B_active_end.max_x),
                min_y=min(B_active_start.min_y, B_active_end.min_y),
                max_y=max(B_active_start.max_y, B_active_end.max_y),
                min_z=min(B_active_start.min_z, B_active_end.min_z),
                max_z=max(B_active_start.max_z, B_active_end.max_z),
            )
            
            for A in list(freed_before_step):
                A_bbox = member_by_key[A].bbox
                if A_bbox is None:
                    continue
                
                A_active = A_bbox.translate(*cum_displacements[A])
                
                if (max(B_swept.min_x, A_active.min_x) <= min(B_swept.max_x, A_active.max_x) and
                    max(B_swept.min_y, A_active.min_y) <= min(B_swept.max_y, A_active.max_y) and
                    max(B_swept.min_z, A_active.min_z) <= min(B_swept.max_z, A_active.max_z)):
                    
                    p_B_max = _project_bbox_max(B_active_start, B_dir)
                    p_A_min = _project_bbox_min(A_active, B_dir)
                    
                    if p_A_min >= p_B_max - _ZERO_EPSILON:
                        clearance = 0.0254 # 1 inch
                        if p_A_min < p_B_max + B_dist + clearance:
                            push_dist = (p_B_max + B_dist + clearance) - p_A_min
                            _push_member(step_idx, A, B_dir, push_dist, step_movements, cum_displacements, member_by_key, freed_before_step)
        
        # Commit displacements
        for key, (d_vec, dist, _) in step_movements.items():
            cum_displacements[key] = _add3(cum_displacements[key], _scale3(d_vec, dist))
            freed_before_step.add(key)
            
        new_movements = []
        for key in sorted(step_movements.keys(), key=lambda k: (member_by_key[k].name, k)):
            d_vec, dist, dragged = step_movements[key]
            new_movements.append(
                MemberMovement(
                    member_key=key,
                    direction=create_v3(sp.Float(d_vec[0]), sp.Float(d_vec[1]), sp.Float(d_vec[2])),
                    distance=sp.Float(dist),
                    dragged=dragged
                )
            )
        steps[step_idx] = AssemblyStep(ordering=step.ordering, substep=step.substep, movements=tuple(new_movements))

    return AssemblySolution(steps=tuple(steps), warnings=tuple(warnings), failure=failure)
