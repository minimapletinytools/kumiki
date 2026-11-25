<!-- 🤖🤖🤖🤖🤖🤖 -->
# Drawings API: hand-placed measurements and viewports

Goal: make it practical to write and adjust drawings in Python (by a person or the agent), not only
generate them with `with_auto_drawings`. The viewport UI (select, resize, split, floating views) comes
after; this plan only settles the API it will sit on.

Status: design agreed in part on 2026-11-24. Nothing built yet. Open decisions are in §3.

## 1. Where we are

A hand-written drawing today:

```python
post = frame.cut_timber_of(post_timber)
shoulder = find_feature(post, ["tenon_joint"], "shoulder")
bottom = find_feature(post, [], "rptw.bottom")
shop = Drawing(
    name="post",
    timbers=[post.timber],
    viewports=shop_drawing_viewports(),
    measurements={SHOP_DRAWING_IDS["front"]: [
        Measure(bottom, shoulder, placement=MeasurementPlacement(offset=0.03)),
    ]},
)
frame = frame.with_finishing(lambda f: f.add_drawing(shop))
```

Nothing in `patterns/` or `hidden_structures/` writes one this way. The problems:

| Area | Problem |
|---|---|
| Finding features | `find_feature` returns `None` on a miss, with no hint of valid names. A `Measure` with a missing anchor is silently dropped. |
| | A feature is found by name plus the exact chain of CSG labels above it (`mortise_and_tenon/scribe_hollow_relief_cut/mortise_cut/peg_hole_0`). That chain is internal to the joint function and changes with its options. |
| | Only declared features are reachable. Derived edges and corners (`arris.9`, `shoulder×rptw.front`), which auto-dimensioning uses, have no public constructor. |
| | Names are string literals inline in each joint function. The agent has no tool that lists them. |
| Addressing a view | Views are named by tree position (`"0.0.0"`). Changing the layout re-points every measurement and every saved override in the drawings file. |
| | Measurements live in two places (`Viewport.measurements`, `Drawing.measurements`); only the second is auto-placed. |
| Placement | `offset` / `along` are signed world metres. The sign depends on how the anchors sort, and the same offset is a different paper distance in each view. |
| | A measurement with no placement gets a viewer default, not the collision-aware placer generated drawings use. |
| Mixing with auto | `with_auto_drawings` is all-or-nothing. Changing one dimension means `piece_drawing`, `dataclasses.replace` and a finishing routine. |
| Viewports | A view is a label the viewer maps to a camera, or a bare `ViewAxes`. No scale, crop or detail target, per-view timbers, or per-view X-ray. `"Front"` means the timber's face for one timber and the world's for several. |
| Kinds | `MeasurementKind.parse("projected_horizontal_distance")`. |

## 2. Decided

1. **Viewports are addressed by name.** Position ids (`"0.0.0"`, `SHOP_DRAWING_IDS`) stay accepted as a
   temporary compatibility layer.
2. **Feature names become constants per joint family**, e.g. `MortiseAndTenonFeatures.SHOULDER`. String
   ids remain valid underneath (the drawings file needs them).
3. **The agent gets a feature listing.** `describe_frame` becomes `describe`, taking a frame, a timber or
   a joint.
4. **API before UI.** The viewport UI notes (9/6/2026) are implemented later, on top of this.

## 3. Still to decide

Each has my recommendation; none is settled.

**A. Is `joint.feature(...)` the main way to get a feature?**
Constants fix renames of the name but not the label path. Proposal: `joint.feature(MT.MORTISE_BOTTOM)`
searches that joint's cuts for the name and raises if it is missing or ambiguous; repeats take an index
(`joint.feature(MT.PEG_HOLE_AXIS, 0)`). The label-path form stays for the drawings file and odd cases.
*Recommend: yes.* Asked on 2026-11-24, not yet answered.

**B. Placement in sheet terms.**
Replace signed world offsets, for authors, with a side and a lane: `side="left", lane=2` (lanes are fixed
paper spacing, as the auto-placer already uses). Unplaced measurements go through the auto-placer.
Explained on 2026-11-24; not yet confirmed.
*Recommend: yes, keeping `MeasurementPlacement(offset, along)` as the stored form.*
- Sub-question: lanes only, or also explicit paper millimetres?

**C. How manual edits combine with generated drawings.**
Proposal: one entry point where the generated drawing is the starting point and code adds, removes or
pins measurements, using the existing generated → coded → file-override tiers (`MeasurementSource`).
*Recommend: layer on top; a fully hand-built `Drawing` stays possible.*
- Sub-question: the name. `with_drawings(frame, fn, fixed_path=...)` alongside `with_auto_drawings`, or
  a callback argument on `with_auto_drawings`?

**D. Where a view's name comes from, and renames.**
Proposal: the name is the view's label, unique within a drawing (raise on a duplicate).
- Renaming a view in code orphans its saved overrides. Accept that, or add an optional explicit `id`
  separate from the label? *Recommend: label by default, optional `id` for when the label must change.*
- Existing drawings files are keyed by position. Migrate on load and rewrite on save, or keep reading
  both forever? *Recommend: read both, write names.*

**E. Viewport model.**
The UI notes want one grid (split rows/columns, at least one cell) plus ordered floating views. Today
every root floats and the grid is a subdivision inside a page-covering root.
*Recommend: `Drawing(grid=..., floating=[...])`, with today's form still accepted.*
- What a view carries: camera, scale (explicit like 1:5, or fit), focus (a feature or box to frame, for
  details), which timbers, X-ray mode. Which of these are in the first cut?
- `"Front"` meaning two things (timber face vs world): make the camera explicit
  (`look=TimberFace.FRONT` vs `look=World.FRONT`) and keep the label as text only?

**F. Derived features.**
`edge(a, b)` and `corner(a, b, c)` as public constructors for derived anchors. Where they live: on the
joint, the cut timber, or free functions? *Recommend: on the cut timber, since the two faces can belong
to different joints.*

**G. Rolling out constants.**
Mortise and tenon first (about a dozen names), then the rest per family as they are touched; or all
families in one pass? *Recommend: mortise and tenon first.* Timber faces keep `rptw.*` / `ptw.*` with a
`TimberFace` shortcut.

**H. `describe` details.**
- Frame: what `describe_frame` returns today. Timber: faces, joints on it, feature names. Joint: members,
  each feature with its constant name and type.
- Keep `describe_frame` as an alias? *Recommend: yes, for a while.*
- How a timber or joint is named in the call: ticket path?

## 4. Sketch of the target

Illustrative; names depend on §3.

```python
def drawings(d):
    post = d.piece("post")                          # the generated shop drawing, editable
    front = post.view("front")
    tenon = post.joint("tenon_joint")
    front.measure(tenon.feature(MT.SHOULDER), post.face(TimberFace.BOTTOM), side="left", lane=1)
    front.measure(post.edge(MT.MORTISE_LEFT, "rptw.front"), tenon.feature(MT.PEG_HOLE_AXIS, 0),
                  horizontal=True)
    front.remove(post.face(TimberFace.TOP), tenon.feature(MT.SHOULDER))
    post.add_view("mortise detail", look=TimberFace.FRONT, around=MT.MORTISE_BOTTOM, scale=1/2)

frame = with_drawings(frame, drawings, fixed_path="beam")
```

## 5. Build order

Each step is its own PR.

1. **Viewport names** (§3 D): name-keyed measurements and overrides, position ids as compatibility,
   drawings-file reading of both forms. Touches `drawing.py`, the runner's override merge, the viewer's
   viewport ids.
2. **Feature constants and joint lookup** for mortise and tenon (§3 A, F, G), with errors that list the
   nearest names.
3. **Measurement API** (§3 B, C): sheet-side placement, auto-placement of unplaced measurements, the
   layered entry point. Convert `dovetailed_sawhorse` or the cute frame as the worked example.
4. **`describe`** (§3 H).
5. **Viewport model** (§3 E): grid plus floating, per-view scale / focus / timbers / X-ray.
6. Docs: `agent_usage_instructions.md` and `api_cheat_sheet.md` drawing sections (both partly
   human-written, so changes go to review).

Then the viewport UI from the 9/6/2026 notes.

## 6. Risks

- **Drawings-file compatibility.** Step 1 changes what saved overrides are keyed by. Needs a test with a
  position-keyed file from before the change.
- **Ambiguous joint lookups.** A name can appear more than once in a joint (multi-tenon, several pegs).
  The index form has to be stable across parameter changes, or overrides drift.
- **Auto-placing hand-written measurements** changes how existing coded drawings look. Acceptable since
  there are none outside tests, but worth stating in the changelog.
- **Two layout forms** (grid plus floating vs all-floating roots) living side by side for a while.
