# Assembly Solver v2: moving-group closure, solver-generated substeps, centering

## Context

The current solver (`kumiki/assembly.py`, design history in `docs/plans/assembly-ordering.md`)
is feature-flagged off in kigumi (`assemblyPreview: false`) because it doesn't work well.
Its per-member model (freedoms + `Ordering`) and the Frame adapter are sound and stay;
the *solving* algorithm is replaced. The three driving requirements:

1. **Orders are group boundaries, not step boundaries.** A user-assigned order says
   "this group comes apart separately," but one group may need SEVERAL distinct
   motions in sequence to come apart. The solver must discover that sequencing
   itself (TODO: "it can attempt to break it into groups by itself").
2. **Centering.** A step may move several members at once; the motion should be
   split/averaged so the scene stays centered about the arrangement's centroid
   instead of one side flying off while the rest stays pinned.
3. **Different speeds.** Members may need to travel different distances within one
   step; the animation must support per-member distances (already partially true).

## Diagnosis: what the current algorithm gets wrong

The current algorithm is per-member greedy extraction + rigid drag propagation
(`_propagate`), with all of a step's motions summed into ONE net vector per member
(`_merge_movements`), a loop counter as the failure detector, and separation detected
by checking accumulated absolute displacements for parallelism against declared DOFs
(`_is_joint_separated`). Specific defects, all traceable to that shape:

1. **One merged step per `Ordering`.** All candidates at an ordering extract
   "simultaneously" and each member's contributions collapse into a single net
   vector. There is no way to express "within order 2: first lift A, then slide B"
   — the exact thing requirement 1 needs. Suborders don't help; they are
   *authored* by cut functions, not discovered.
2. **Merged net vectors are kinematically invalid.** A member dragged +Z by one
   extraction and +X by another gets a single diagonal net movement that no joint
   in the frame ever declared as an escape direction. The viewer animates that
   diagonal linearly, sliding tenons sideways through mortise walls.
3. **Separation detection is defeated by its own output.** `_is_joint_separated`
   only recognizes relative displacement that is parallel (1e-6 dot tolerance)
   to a declared DOF. Because merging produces diagonal accumulated displacements,
   genuinely separated joints go undetected → members re-extract, overshoot, or
   drag partners that should have been skipped.
4. **The right answers happen by accident.** In
   `test_net_zero_drag_warns_and_emits_no_movement` (two keys extracted in opposite
   directions, both rigidly linked to a board), the solver extracts both keys, drags
   everything both ways, and the ±X contributions cancel: keys and board end up with
   net-zero motion and "cancelled out" warnings — including on the *primary movers* —
   while the seats drift apart. The relative outcome is coincidentally right; the
   step semantics (primary movers that don't move, warnings on success) are incoherent.
5. **Loop caps conflate oscillation with unsolvability.** `_MAX_LOOP_ITERATIONS = 6`
   is an arbitrary re-disturbance budget; failure diagnostics describe the
   oscillation, not the actual constraint contradiction.
6. **No centering at all** (requirement 2). One side of every interface stays pinned;
   the "away from peers" DOF ranking chooses directions, it never splits motion.
7. **No per-joint travel accounting.** Only per-member absolute displacement is
   tracked (`total_displacement`); partial engagement (a joint that separates over
   two steps, or after a shorter drag) can't be represented.
8. **No home for sequenced freedoms.** Lift-then-slide joints (lapped gooseneck) are
   left rigid today because a step is one vector per member; there is nowhere to
   put a two-stage escape.

## The new model

Reframe from "extract members" to **"separate joints by moving groups."** This is the
classic assembly-partitioning formulation (directional blocking graphs, Wilson &
Latombe), with declared freedoms standing in for geometric blocking tests. Three
cleanly separated phases: **plan** (which group moves, along what, how far),
**gauge/centering** (who actually moves in world space), **compaction** (which
micro-steps animate in parallel). The solver stays timber-agnostic, kinematic, and
deterministic.

### State

- **Pair engagement.** For each joint J and unordered member pair {m, p} within it:
  accumulated relative travel per escape axis, and a separated/engaged bit with the
  separation direction once freed. Replaces `total_displacement` +
  `_is_joint_separated` entirely. A pair is *separated* when accumulated travel
  along one of its escape DOFs ≥ that DOF's `freed_after`.
- Because every micro-step moves one group along ONE authored DOF direction,
  per-pair relative motion is always along ±that axis — travel bookkeeping is a
  scalar add, never a diagonal decomposition. Defects 2, 3, 7 disappear by
  construction.
- A member is *removed* when all its pairs are separated (derived, not primal).

Relative motion of m w.r.t. p along direction d is **allowed** by their joint iff
`freedom[m]` has a DOF ∥ d or `freedom[p]` has a DOF ∥ −d (same rule as today).
A separated pair is ignored by closure EXCEPT motion that would re-enter it
(negative component along its separation direction) — that re-couples the pair and
drags the partner instead. This "keep-out" rule prevents the preview from visually
re-inserting joints that already came apart (a case the current solver ignores).

### Phase 1 — plan micro-steps, per ordering

The unit of work is an **unseparated scheduled pair**: a (joint, pair) whose member
spec carries the current `Ordering` and has translations. An ordering is done when
all its scheduled pairs are separated. ("Second side skips" fall out: once a pair
separates from either side, nothing schedules more work for it.)

```
for each ordering (sorted):
    while unseparated scheduled pairs remain:
        candidates = []
        for each (target member, DOF d) of an unseparated scheduled pair:
            G, chains = closure(target, d)          # see below
            if G has a crossing scheduled pair:     # target's joint must not be absorbed
                candidates.append(scored (target, d, G))
        if no candidates: return AssemblyFailure(ordering, chains as diagnostics)
        pick best candidate
        D = max remaining_travel over CROSSING scheduled pairs of this ordering
        emit micro-step: every member of G moves D·d̂
        accumulate travel on ALL crossing pairs; mark separations (incidental
        separations of later-scheduled pairs are recorded + warned)
```

**closure(target, d)** — the old `_propagate`, but as monotone set growth
(no distance mutation, no loop counts):

```
G = {target}; frontier = [target]
while frontier:
    x = pop
    for each engaged (or keep-out-violated) pair {x, p} with p ∉ G:
        if relative motion d is allowed for the pair: continue   # it slides
        add p to G (record the chain edge x --[joint]--> p)
```

Closure grows monotonically and terminates in ≤ |members| iterations — no
`_MAX_LOOP_ITERATIONS`, no `_LoopDetected`. Unsolvability becomes exact and
explainable: *the closure absorbed the very partner the target was escaping* (or the
whole frame). Diagnostics are the real chain of rigid links that caused it, e.g.
`spoke_00 --[hub_link_00]--> hub --[hub_link_01]--> spoke_01 --...` (defect 5).

**Candidate scoring** (deterministic, tiebreak by name/key), reusing today's ranking
signals as score terms:
1. fewest dragged members whose own ordering is LATER (each also emits the existing
   warning),
2. smallest |G|,
3. direction heuristics: away from the engaged complement's centroid, away from
   later-ordered members, planar with this ordering's members
   (`_dominant_plane_normal` survives as-is).

**Termination:** every emitted micro-step separates ≥ 1 scheduled pair (D is chosen
as the max *remaining* travel over crossing scheduled pairs), so the per-ordering
loop runs at most (number of scheduled pairs) times. Complexity per micro-step is
O(candidates × E); fine at frame scale.

This phase directly delivers requirement 1: an order group that needs "lift the
cross-lap out, THEN slide the tenon" produces two micro-steps under one ordering,
discovered by the solver. It also gives the un-ordered default frame a real
auto-sequenced exploded view for free. And it creates the home for future sequenced
freedoms (defect 8): a lift-then-slide escape is just a freedom whose stages emit
consecutive micro-steps.

### Phase 1b — simultaneous ring escape (fallback when closure fails)

Closure only finds **rigid** group motions: one group, one direction, stationary
complement — a "two-handed" step. Assemblies exist that no two-handed step can
separate but a simultaneous multi-velocity motion can (Snoeyink & Stolfi 1993);
in our ray model the minimal case is a skewed ring, e.g. a 3-cycle with escapes
+X, +Y, and (−1,−1): assigning velocities A=(1,1), B=(0,1), C=0 puts every
pairwise relative motion on its allowed ray, yet every closure from every target
absorbs the whole ring.

Note that most realizable rings DO decompose under closure — a cardinal 4-ring
(+X, +Y, −X, −Y around the cycle) comes apart as {A, D} sliding +X together, then
B sliding +Y — because opposite rays pair into rigid group motions. The fallback
triggers only when an ordering has unseparated scheduled pairs and NO closure
candidate:

- Contract rigid links, then solve for per-member velocities x_i on the engaged-
  pair graph: each pair's relative velocity x_i − x_j must be zero or t_ij·r_ij
  (t_ij ≥ 0) for one of its authored rays. Around each cycle this telescopes to
  Σ t_ij·r_ij = 0 — a small enumeration over ray choices per pair (joints author
  both sides, so sign freedom is the norm), then a linear feasibility check.
- Scale the solution so every scheduled pair's relative travel reaches its
  remaining `freed_after`; overshoot on already-freed rays is harmless.
- **No output change needed**: an `AssemblyStep` already carries per-member
  direction + distance, so a ring step is simply a step with more than two
  distinct velocities; closure steps are the two-velocity special case. Members
  traveling different t_ij distances in one step is requirement 3 appearing
  naturally.
- Centering (Phase 2) applies unchanged — subtracting the weighted mean velocity
  turns a ring escape into a symmetric pinwheel explosion.
- If neither closure nor ring assignment succeeds, the `AssemblyFailure`
  diagnostics report the blocking cycle(s) alongside the closure chains.

### Phase 2 — Anchored Centering (Active Group only)

Instead of counter-translating the entire scene (which makes the stationary/unassembled frame drift), we anchor the stationary complement $C_S$ (members belonging to later orderings) to $0$ displacement. Centering is restricted to the active disassembly group $M_S$ (the members of the current `Ordering` step that are not yet fully removed).

- **Empty Stationary Complement**: If the stationary complement $C_S$ is empty (e.g., the last remaining pieces are parting from each other), we subtract the weighted average velocity $v_{\text{avg}}$ of $M_S$ from all members in $M_S$:
  ```
  v_avg = sum(w_i * v_i) / sum(w_i)  # for i in M_S
  v_i = v_i - v_avg                  # for i in M_S
  ```
  This makes the expansion symmetric about the group's centroid.
- **Non-Empty Stationary Complement**: If $C_S$ is not empty, we preserve the net escape translation of $M_S$ relative to $C_S$ (so they clear the stationary frame), but center any internal relative separation within $M_S$ (e.g., if subgroups of $M_S$ move in opposite/different directions).

Because this centering adjustment is per-member, we apply it directly to each member's movement vector. The viewer does not need to apply a global offset.

### Phase 3 — compaction (parallel animation)

Raw micro-steps are sequential, which would make N pegs pop one… at… a… time.
Within one ordering, greedily merge consecutive micro-steps into a single animated
substep when **moving groups are pairwise disjoint AND no engaged pair connects two
distinct moving groups**. (Each group was validated against a stationary complement;
with no joint between the merged groups, their mutual relative motion is
unconstrained, so the merge is sound.) All pegs pop simultaneously again;
independent corners of a frame part in parallel.

Different distances within a merged substep animate as different speeds over the
same scrub interval — requirement 3, now with per-joint travel guaranteeing each
distance is individually valid.

### Phase 4 — Clear-out Propagation (Collision Avoidance)

Previously freed members (accessories like pegs, or smaller timbers) parked at
their exploded positions may sit directly in the escape path of a later step's
motion. To prevent visual clipping where a larger timber slides through a
floating, already-freed piece, a clear-out pass adjusts parked members'
positions. Inputs: an axis-aligned `bbox` per `AssemblyMember` (the Frame
adapter computes it from timber corners; accessories get a small box around
their transform position until real accessory extents are plumbed through).

Run per emitted step (post-compaction), tracking each member's cumulative
displacement so parked bboxes are evaluated where they actually float:

1. **Sweep test.** For each moving member B in the step (direction d̂, distance
   D): form the AABB hull of B's start and end boxes. Collect every parked
   member A whose current bbox intersects that hull and whose projection
   interval along d̂ lies ahead of B's start (A is in the path, not behind it).
2. **Single-pass push, front-to-back.** Sort the collected members by their
   min-projection along d̂, ascending, and process in order: push each A along
   d̂ just far enough that its min-projection clears (a) B's end-position
   max-projection and (b) the max-projection of every already-pushed member,
   plus a clearance margin (default 25mm; solver parameter). Because
   processing follows the projection order and every push is forward along
   d̂, each parked member is pushed **at most once per step** — no recursion,
   no mutual-push leapfrogging, termination by construction. (Attempt #1
   implemented this as recursive pair-wise pushes; two boxes overlapping
   perpendicular to a diagonal d̂ leapfrogged each other unboundedly.)
3. **Emit as movements.** A push becomes an extra `MemberMovement` in that
   step (dragged=True), so the viewer animates the parked piece drifting
   clear; cumulative displacement is updated for later steps' sweep tests.

Safety and caveats: parked members are fully separated, so translating them
is always kinematically legal; pushes go forward along the step's escape
flow, which in practice increases separations (a formal keep-out check
against re-entry can be added if a model ever shows otherwise). The viewer's
disassembly multiplier scales all distances uniformly; clearances computed at
base scale stay clear for multiplier ≥ 1 (sub-1 multipliers may re-overlap —
acceptable for a preview aid).

## Output & serialization changes

```python
@dataclass(frozen=True)
class AssemblyStep:
    ordering: Ordering          # authored (order, suborder) — unchanged
    substep: int                # NEW: solver-generated sequence within the ordering
    movements: Tuple[MemberMovement, ...]   # sparse: moving group only (includes centering/clear-out adjustments)
```

`MemberMovement` is unchanged (`dragged` still distinguishes ride-alongs).
`AssemblySolution` / `AssemblyFailure` unchanged apart from steps now carrying
substeps; failures keep partial steps scrubbable.

`AssemblyMember` gains an optional `bbox` (axis-aligned, global) for Phase 4;
the Frame adapter fills it from timber corner positions (accessories: small
box at the transform position for now).

- runner.py `_build_assembly_payload`: add `substep` per step, outputting the centered/adjusted movements.
- assembly-timeline.js: scrub semantics unchanged (value k = first k steps applied,
  fraction interpolates the next). Timeline: major marks per
  ordering, minor ticks per substep; labels stay `"2"` / `"2.1"` (substeps get
  ticks, not labels).

## Migration map (old → new)

| Current | Fate |
|---|---|
| `_propagate` (worklist + distance mutation + loop counts) | → `closure` (monotone set growth, chain recording) |
| `_MAX_LOOP_ITERATIONS`, `_LoopDetected`, `_describe_loop` | deleted; absorb-failure with exact chains |
| `estimated_drag_cost` cheapest-first | → |G| term in candidate scoring |
| `_rank_dofs` heuristics | kept as direction score terms |
| `_is_joint_separated`, `total_displacement` | → per-pair travel/separation state |
| `_merge_movements`, cancellation warnings | deleted; micro-steps are single-direction by construction |
| dragged-later-ordering warning | kept (from G membership) |
| `Ordering`, freedoms, `with_order`, Frame adapter | unchanged |
| Phase 2 Centering (whole-scene) | → Anchored Centering (modifying active movements directly) |
| None | → Phase 4 Clear-out Propagation (adjusting historical displacements for collision avoidance) |

`_are_parallel`'s tight tolerance stops being a hazard: candidate directions are
always authored DOF directions, never merged diagonals, so parallel checks compare
authored axes against each other.

## Lessons from implementation attempt #1 (must-follow)

The first implementation (branch `assembly-solver-v2`, deleted 2026-07) got the
closure planner mostly right but failed on real models. Root causes, verified
against oscarshed and tinyhouse120:

1. **Never validate the SUM of a member's motion across micro-steps.** Attempt
   #1 added a post-hoc check that each member's total ordering-wide velocity be
   parallel to an authored DOF. Micro-steps are *sequential*; a member extracted
   along one DOF and later dragged along another has a diagonal sum that means
   nothing. This single check made oscarshed (and most real models) fail after
   the pegs popped. Per-substep motion is single-direction by construction;
   there is nothing to validate.
2. **Emit solved steps even when an ordering fails midway.** Attempt #1 broke
   out before step emission, discarding every solved micro-step of the failing
   ordering — the "pegs come out, everything else stuck" symptom. The contract
   is: failures keep all previously solved steps scrubbable.
3. **No sympy in inner loops.** Convert every DOF direction and freed_after to
   floats ONCE at solve start. Attempt #1 called `giraffe_evalf` inside the
   closure's allowed-check: 7.3M evalf calls ≈ 60s of tinyhouse120's 83s solve.
4. **Don't re-enumerate all candidates every micro-step.** Attempt #1 re-ran
   closure for every (pair × target × DOF) each iteration of the per-ordering
   loop (21,612 closures on tinyhouse120). Cache closures and invalidate only
   candidates whose members' pair states changed, or at minimum enumerate
   lazily best-first. Budget: tinyhouse-scale (~120 members, ~140 joints)
   must solve well under 2s.
5. **Keep-out must not deadlock the greedy sequence.** Once pairs separate in
   scattered directions, the strict rule "any opposing motion re-couples the
   pair" makes re-dragged partners (moving off their own escape rays) absorb
   the whole model, and candidates go to zero even when a valid sequence
   exists. Mitigations, in order: (a) score candidates to penalize directions
   opposing any separation direction held by members of G (avoid creating the
   conflict at all — attempt #1 happily extracted studs and top plates
   DOWNWARD, poisoning later state); (b) prefer directions that already have
   separated pairs along them (travel is monotone); (c) before declaring
   failure with pairs remaining, retry remaining pairs under relaxed scoring
   (different pick order), since the deadlock is order-of-picks, not
   infeasibility.
6. **Key pair state by joint identity, never `joint.name`.** Names are type
   strings ("mortise_and_tenon") shared by dozens of joints; two same-named
   joints between the same member pair silently share one engagement state.
   Use the joint's index in the input sequence.
7. **Intra-joint sequencing lives in the SUBORDER.** Locking accessories
   (pegs/keys/wedges) are authored `Ordering(0, -1)`; member timbers stay
   `Ordering(0, 0)`. `with_order(n)` rewrites only the order and preserves
   suborders, so peg-before-slide survives frame-level ordering. (Attempt #1
   put pegs at order −1, which `with_order` flattened away.)
8. **Serialize what you emit.** Attempt #1 added `substep` to `AssemblyStep`
   but never plumbed it through runner.py, so same-labeled timeline steps
   collided. Payload, normalization, and timeline marks must all understand
   substeps (and Phase 4's pushed movements) end to end.
9. **Compaction must check pair state as of that micro-step.** Attempt #1
   consulted the mutated end-of-ordering pair states, over-merging substeps
   that were sequentially dependent. Snapshot separation state (e.g. a
   monotone version counter per pair) and compare against the micro-step's
   timestamp.

## Tests

- Port `tests/test_assembly.py` fixtures (same graph-builder helpers). Expected
  changes: the spoke/hub loop-cap case becomes a clean absorb-failure with a chain
  diagnostic; the cancelled-drag board case becomes a POSITIVE test (seats part in
  two micro-steps, keys/board never move, no warnings).
- New: solver-generated substeps (order group requiring sequenced motions, e.g.
  lift-then-slide chain); per-pair travel across steps (joint separated by an
  earlier drag is skipped at its own step); keep-out (motion that would re-insert a
  separated joint drags the partner instead); centering invariants (unassembled frame stays anchored at 0; active moving groups center relative to each other/centroids); compaction (disjoint pegs merge into one substep; linked groups don't); clear-out propagation (previous steps' displacements adjusted to clear future steps' sweeps); determinism.
- Clear-out: parked member in a mover's swept path gets pushed with clearance;
  push chains resolve front-to-back in one pass (construct the attempt-#1
  leapfrog case — two boxes overlapping perpendicular to a diagonal d̂ — and
  assert each is pushed at most once per step); pushes appear as movements and
  compound into later steps' sweep tests.
- `tests/joints/test_assembly_freedoms.py`: already updated for the suborder
  convention (accessories `(0,-1)`, timbers `(0,0)`) — keep green.
- kigumi: timeline normalization of `substep`; offsets apply modified movements.

## Implementation order

1. `kumiki/assembly.py`: pair-engagement state + `closure` + Phase 1 planner, new
   `AssemblyStep` shape, rewrite test_assembly.py (riskiest; pure fixtures keep it cheap).
2. Phase 2 anchored centering + Phase 3 compaction + Phase 4 clear-out propagation (each is a small, separately testable pass).
3. runner.py payload + assembly-timeline.js + jest tests.
4. Update `patterns/structures/assembly_preview_demo.py` expectations; manual scrub
   in kigumi; only then consider flipping `assemblyPreview`.

## Open questions / future

- **Centering weights**: member count v1; timber volume (adapter already has sizes)
  is a drop-in refinement. Whether removed members should stop counter-moving
  (`ACTIVE_ONLY` policy) is a visual-taste call — it breaks exact centroid fixing
  and needs keep-out validation, so it's deferred.
- **Rotations**: closure extends naturally (relative screw motions instead of
  translations); still `NotImplementedError` for now.
- **Sequenced freedoms** (gooseneck): add a staged-DOF freedom type; the planner
  emits one micro-step per stage. The v2 architecture is the prerequisite.
- The solver remains topological (no collision checks); a "solved" preview is still
  a preview, not a proof.

## References

- R. H. Wilson, J.-C. Latombe — *Geometric Reasoning about Mechanical Assembly*,
  Artificial Intelligence 71(2), 1994 (non-directional blocking graphs; the
  assembly-partitioning formulation Phase 1 instantiates).
- P. Song, C.-W. Fu, D. Cohen-Or — *Recursive Interlocking Puzzles*, SIGGRAPH Asia
  2012 (disassembly sequencing of interlocking parts via blocking analysis).
- C.-W. Fu et al. — *Computational Interlocking Furniture Assembly*, SIGGRAPH 2015.
- M. Larsson et al. — *Tsugite: Interactive Design and Fabrication of Wood Joints*,
  UIST 2020 (per-joint escape-direction analysis for joinery).
