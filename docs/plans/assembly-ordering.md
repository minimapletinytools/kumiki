# Assembly Ordering Redesign: per-member `Ordering`, `with_order`, joint-authored freedoms

## Context

The first assembly implementation (already merged into the working tree) required users to call `joint.with_assembly(order, freedoms)` after cutting — annoying, and conceptually wrong in two ways the user identified:

1. **Assembly order is a frame-level construct** — the joint can't know it at cut time. But **freedoms are joint-level** — the cut function knows the escape geometry precisely (tenon axis, mortise depth), so it should author them itself.
2. Some joints need **intra-joint sequencing** (pegs/keys/wedges come out before the joint slides apart), which one per-joint order can't express.

New model (user-specified):
- `Ordering(order: int = 0, suborder: int = 0)`, compared lexicographically. Smaller = extracted earlier.
- Every cutting/accessory carries an `assembly_ordering` (default `Ordering(0, 0)`) and cut functions set `assembly_freedom` + suborders at cut time.
- `Joint.with_assembly` is **removed**. New `Joint.with_order`:
  - `with_order(n)` — sets `order=n` on ALL members (cuttings + accessories), **preserving suborders**.
  - `with_order({member: n, ...})` — per-member: named members get `Ordering(n, 0)`; unnamed members keep their current ordering; raises `ValueError` if the resulting orderings break the joint's original strict precedence (∀ a,b: old(a) < old(b) ⟹ new(a) < new(b)). Members referenced by cutting/accessory string key OR by timber/accessory object (identity via `joint.cuttings`).
- Solver steps become distinct `Ordering` values. Default result: a frame with no `with_order` calls disassembles in two steps — (0,0) accessories pop, (0,1) timbers separate — an instant exploded-view preview.
- Zero-engagement joints (plain butt, miter, splice butt): freed_after = **nominal distance** (receiving timber's size along the escape direction), documented as a preview aid (user-confirmed).

Everything below reworks code written earlier this session, so file/line context is current.

---

## 1. kumiki/assembly.py — `Ordering` + per-member graph

```python
@dataclass(frozen=True, order=True)
class Ordering:
    """Extraction position: compared lexicographically; smaller = out earlier.
    suborder expresses required sequencing WITHIN a joint (peg before slide);
    order is the frame-level plan set via Joint.with_order."""
    order: int = 0
    suborder: int = 0

@dataclass(frozen=True)
class JointMemberSpec:
    freedom: Optional[AssemblyFreedom] = None
    ordering: Ordering = Ordering()

@dataclass(frozen=True)
class AssemblyJoint:
    name: str
    members: Mapping[int, JointMemberSpec]   # replaces order + freedoms
```

Solver (`solve_assembly(members, joints)`) rework:
- Steps = sorted distinct `Ordering`s over members that have a freedom with translations. Gate: return `None` only when NO member has any freedom.
- Per step s: candidates = members m with freedom in some joint J where `J.members[m].ordering == s`; extraction/ranking/propagation logic otherwise unchanged (the `shared` ranking term and freedom lookups read `J.members[key].freedom`).
- Drop the joint-level release check (`joint.order < o`); the `removed` set already covers extracted members (per-member orderings make joint-level release meaningless).
- `own_order` warning becomes `own_ordering` (min `Ordering` over joints granting the member a freedom); warning text reports e.g. `order 1.0 dragged member 'wedge' whose own ordering is 2.0`.
- `AssemblyStep` gains `ordering: Ordering` (replaces `order: int`); `AssemblyFailure.order` becomes `ordering`.

## 2. kumiki/timber.py — fields, `with_order`, adapter

- `Cutting.assembly_ordering: Ordering = Ordering()` and `JointAccessory.assembly_ordering: Ordering = field(default=Ordering(), kw_only=True)` (next to the existing `assembly_freedom` fields at :1390 / :1901).
- **Delete** `Joint.assembly_order` and `Joint.with_assembly` (:2146-2196). Add:

```python
def with_order(self, order: Union[int, Mapping[Union[str, PerfectTimberWithin, JointAccessory], int]]) -> "Joint":
```
  - int: rebuild every cutting/accessory via `replace(member, assembly_ordering=Ordering(order, member.assembly_ordering.suborder))`.
  - Mapping: resolve each key (str → cuttings/jointAccessories key; object → identity scan over `cutting.timber` / accessory values; ValueError naming unknown references). Named → `Ordering(n, 0)`; unnamed unchanged. Then assert precedence preservation across ALL member pairs (old strict `<` must remain strict `<` in the result) — ValueError explaining which pair breaks (e.g. "peg_0 must be extracted before 'Right Side' (suborder 0 < 1) but new orders place it at 3 vs 1").
- `solve_frame_assembly` adapter: build `JointMemberSpec(freedom=cutting.assembly_freedom, ordering=cutting.assembly_ordering)` per member; duplicate timber across cutting keys (compound joints) → `AssemblyFreedom.combine` the freedoms and take the **min** ordering. Gate: `None` when no member has a freedom (was: no joint has assembly_order).

## 3. Joint functions author their own freedoms + suborders

Conventions: escape freedoms on **both** sides of an interface (each cutting gets the direction that moves *it* out; opposite signs), so `with_order` works on whichever member the user schedules. Suborders only where the joint requires sequencing: locking accessories (pegs/keys/wedges) get `Ordering(0, 0)` and the timber cuttings they lock get `Ordering(0, 1)`; joints without locking accessories leave everything at the default `Ordering(0, 0)`.

Per the survey (all directions/depths verified in scope at `Joint(...)` construction):

| Builder (file) | Escape freedom | freed_after | Suborders |
|---|---|---|---|
| `cut_mortise_and_tenon_joint` (butt_joints.py:535, **choke point** for the 4 straight variants at :946/:1025/:1081/:1116 + basic wrappers) | tenon cutting: −`tenon_length_direction_global` (:835); mortise cutting: inverse | `tenon_length` | pegs (`peg_i`, :904-914): freedom along `peg_result.orientation_global` −Z, freed_after = peg depth + stickout; peg `(0,0)`, timbers `(0,1)` |
| `cut_plain_butt_joint` (+`_on_face_aligned`) butt_joints.py:109/:198 | butt cutting: −`butt_direction`; receiving: inverse | **nominal**: receiving timber size along escape (`get_size_in_direction_3d`) | — |
| `cut_tongue_and_fork_butt_joint` :267 | tongue along its length axis out of fork; fork inverse | fork/tenon engagement depth (in scope :441-444) | — |
| `cut_wedged_half_dovetail_mortise_and_tenon_joint` :1173 | tenon along `shoulder_result.butt_direction` inverse | `tenon_depth` | wedge (`"wedge"`, :1307): drive axis from `geo.wedge_accessory_csg.transform`; wedge `(0,0)`, timbers `(0,1)` |
| `cut_dropin_dovetail_butt_joint` :1325 | **unidirectional** single axis (drop-in direction; NOT bidirectional) | drop depth | — |
| `cut_plain_miter_joint` (+aligned) corner_joints.py:80/:301 | each timber along its own length axis (outward) | nominal | — |
| `cut_tongue_and_fork_corner_joint` :325 | tongue along length axis | engagement depth | — |
| `cut_plain_corner_lap_joint` :587 | lift along lap-plane normal (both sides, opposite) | lap depth | — |
| `cut_mitered_and_keyed_lap_joint` :699 | halves separate along `miter_normal` (:1212) | finger depth | keys (`key_i`, :1322): along `diagonal_direction` (:1124); keys `(0,0)`, timbers `(0,1)` |
| `cut_plain_cross_lap_joint` / `_house_joint` cross_joints.py:75/:381 | lift along `cutting_plane_normal_normalized` (:248), opposite per side | lap depth | — |
| `cut_plain_butt_splice_joint_on_aligned_timbers` splice_joints.py:43 | each half along shared length axis (outward) | nominal | — |
| `cut_plain_splice_lap_joint_on_aligned_timbers` :163 | lift perpendicular to lap plane | lap depth | — |
| `cut_tongue_and_groove_joint` board_joints.py:24 | separation along mating axis + slide along board length (two DOFs) | groove/tongue depth; board length for slide | — |
| `cut_splined_opposing_double_butt_joint` multi_butt_joints.py:37 | each butt timber outward along its length axis; spline along `slot_direction_global` | engagement depths | pegs `(0,0)` (dir `peg_entry_direction_global` :289), butts+spline `(0,1)` |

**Left rigid (no freedoms; code comment explaining why):** `cut_lapped_gooseneck_joint` (lift-then-slide — needs future sequenced/R6 freedom), `cut_board_in_grooved_rectangular_frame_joint` (captured panel), `cut_multi_cross_lap_joint` (woven, over-constrained; also flows through `make_compound_joint`), `cut_free_house_joint` (escape direction not derivable from arbitrary CSG). `basic_joints.py` wrappers and `decorative_joints.py` need nothing.

## 4. Serialization + viewer

- runner.py `_build_assembly_payload`: step payload becomes `{"order": s.ordering.order, "suborder": s.ordering.suborder, "movements": [...]}`; failure carries order+suborder.
- assembly-timeline.js: `normalizeAssemblyPayload` accepts/validates `suborder` (default 0); `getTimelineMarks` labels a mark `"{order}"` when suborder is 0, `"{order}.{suborder}"` otherwise. Everything else (offset math, scrub semantics) unchanged — steps are already an ordered list.
- viewer-app.js: no structural change (it consumes normalized steps).

## 5. Tests, demo, fixture updates

- **tests/test_assembly.py**: rewrite graph fixtures to `AssemblyJoint(name, members={key: JointMemberSpec(...)})`; existing scenarios keep their intent; new cases: suborder sequencing (peg-style member at `(0,0)` extracted in a step before its joint's timbers at `(0,1)`), `Ordering` comparison, steps keyed by (order, suborder), gate change (freedoms-anywhere).
- **tests/test_timber.py `TestJointAssembly`**: replace `with_assembly` tests with `with_order` — uniform int (suborders preserved, accessories included), mapping by string key and by timber object, unknown reference ValueError, precedence-violation ValueError (peg ordered after its timber), partial map keeps unnamed orderings, `solve_frame_assembly` end-to-end using a REAL `cut_mortise_and_tenon_joint_on_face_aligned_timbers` (now auto-freedoms: assert pegs pop at (n,0) before timbers at (n,1)).
- **Per-joint freedom tests**: one parametrized test sweeping the updated builders — assert each annotated cutting's freedom direction is parallel to the expected global axis, freed_after > 0, and suborder conventions for peg/wedge/key joints. Lean per the joint-testing guide (`# 🐪` tests untouched).
- **patterns/structures/assembly_preview_demo.py**: collapses beautifully — cut joints, then `.with_order(1)` / `.with_order(2)` / `.with_order(3)`; freedoms + peg suborders come from the cut functions. Keep one per-member `with_order({...})` usage to demo the overload.
- **kigumi/test-fixtures/assembly_frame.py**: raw `Joint` with manual `Cutting(assembly_freedom=..., assembly_ordering=...)` + `with_order(1)` (fields still exist; only `with_assembly` is gone). Extension drive test unchanged.
- **kigumi/__tests__/assembly-timeline.test.js**: suborder normalization + mark labels ("1" vs "1.1").
- Runner smoke: re-run the demo through `serialize_layers` and eyeball steps/warnings.

## 6. Step order & risk

1. assembly.py: `Ordering`, `JointMemberSpec`, `AssemblyJoint.members`, solver step rework + test_assembly.py rewrite (M-L — riskiest: step iteration & release-logic change; pure fixtures keep it cheap)
2. timber.py: fields, delete `with_assembly`/`assembly_order`, `with_order` + precedence assertion, adapter update + tests (M)
3. Joint builders: choke-point M&T first (incl. peg suborders), then the table top-to-bottom; per-joint tests as each lands (L — geometric care per joint; nominal-distance convention for zero-engagement)
4. runner.py + assembly-timeline.js/jest + demo + fixture updates (S-M)
5. Full verification (below)

## Verification

```bash
source .venv/bin/activate && python3 -m pytest tests/ -v
uv run ty check
cd kigumi && npx jest && npm run test:ext:initial
cd kigumi && npm run test:ext:complex:grep -- "assembly"
```

Manual: open `patterns/structures/assembly_preview_demo.py` in kigumi → timeline shows marks 1, 1.1, 2, 2.1, 3 (pegs pop before their joints separate) → an un-ordered frame (e.g. my_cute_frame) now shows a default two-step exploded preview (0 accessories / 0.1 timbers) → scrub, multiplier, warnings badge as before.

---

## Addendum: package-time feature flag (assemblyPreview)

After the ordering redesign shipped, the assembly preview was gated behind a package-time feature flag while still under development:

- `kigumi/webview/feature-flags.js` — a single frozen `FEATURE_FLAGS` registry, loaded both as a Node module (`require`, used by `frame-view-session.js`) and as a plain `<script>` in the webview (`window.FEATURE_FLAGS`), same UMD pattern as `assembly-timeline.js`/`selection-store.js`. This is the general mechanism for future in-development features — add a key, then gate both sides (see below).
- `applyFeatureFlagsToLayersPayload` (exported from `feature-flags.js`): strips the `assembly` key from the layers-tree payload before it reaches the webview when `assemblyPreview` is off. Called at both forwarding sites in `frame-view-session.js`.
- `viewer-app.js`: reads `window.FEATURE_FLAGS`; when `assemblyPreview` is off, the options-panel controls are omitted entirely (not just default-off), the timeline never renders, incoming layers data is never normalized into `assemblyData`, and persisted `kigumi-settings.json` values for `showAssemblyTimeline`/`disassemblyMultiplier` are ignored on load.
- This is distinct from the `kigumi.viewer.*` VS Code settings (`package.json` → `contributes.configuration`): those are user-facing, toggleable by anyone who installs the extension. Feature flags are developer-only — flipped in committed source before packaging/publishing, never exposed as a setting.
- Tests: `kigumi/__tests__/feature-flags.test.js` (flag defaults, frozen registry, payload-stripping behavior).

To ship the assembly preview: flip `assemblyPreview: false` → `true` in `kigumi/webview/feature-flags.js`.
