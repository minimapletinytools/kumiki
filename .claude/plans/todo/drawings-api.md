<!-- 🤖🤖🤖🤖🤖🤖 -->
# Drawings API: hand-placed measurements and viewports

Goal: make it practical to write and adjust drawings in Python (by a person or the agent), not only
generate them with `with_auto_drawings`. The viewport UI (select, resize, split, floating views) comes
after; this plan only settles the API it will sit on.

Status: design agreed on 2026-11-24 and 2026-11-25. Built on branch feat/drawings-api (placement, feature lookup,
viewport names, View, with_drawings, describe, docs); the viewport layout model (§3 E2) waits for the UI work.

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
5. **Features come from joint objects** (2026-11-25): `joint.feature(MT.SHOULDER)` searches that joint's
   cuts by name, raises if missing or ambiguous, and takes an index for repeats. A handle from the joint
   passed to the frame resolves on the final cut timber (checked: all 252 features on the cute frame's
   joints). One taken before a step that rebuilds the joint's cuts (`FauxTimber.restore_joint`) does
   not. `joint.feature` always returns a handle; it is checked when the drawing resolves it against the
   cut timber, and one that doesn't resolve is warned about and its measurement skipped (today it is
   dropped silently).
10. **A view is a direction and a scale** (2026-11-25), plus an up direction (default: the timber's
    length or world Z) and a centre (default: fit the drawing's timbers), built with helpers
    (`View.of_face(...)`, `View.world(...)`); the label is only text.
11. **Derived edges and corners get one-call constructors** (2026-11-25): `cut_timber.edge(a, b)`,
    `cut_timber.corner(a, b, c)`. Measuring them already works (the viewer, the drawings file,
    `DerivedEdgeFeature.derive` + `shared_ancestor`); this only adds the convenience.
6. **Layering on generated drawings** (2026-11-25): supported as one pattern, e.g.
   `with_drawings(frame, fn, fixed_path=...)`; the exact shape is open to whatever builds cleanly.
7. **View names** (2026-11-25): the label by default, an optional separate `id`; old position-keyed
   files are read, names written on the next save.
8. **Constants roll out** mortise and tenon first, then per family as touched (2026-11-25).
9. **`describe`** names timbers and joints by ticket path; `describe_frame` stays as an alias for now
   (2026-11-25).

## 3. Still to decide

Each has my recommendation; none is settled.

**B. Placement in sheet terms.**
Replace signed world offsets, for authors, with a side and a lane. `side` is an enum (`LEFT`, `RIGHT`,
`ABOVE`, `BELOW`) read against the view the measurement is in: which side of the work, as seen on that
sheet, the dimension line goes. `lane` is which row out from the work (1 is nearest; each lane a fixed
paper distance further, 7 mm as the auto-placer uses), so dimensions on one side stack. Both optional;
unplaced measurements go through the auto-placer. Explained again on 2026-11-25; awaiting confirmation.
*Recommend: yes, keeping `MeasurementPlacement(offset, along)` as the stored form.*
- Sub-question: lanes only, or also explicit paper millimetres?

**E2. Viewport layout model (for the UI work).**
The UI notes want one grid (split rows/columns, at least one cell) plus ordered floating views. Today
every root floats and the grid is a subdivision inside a page-covering root.
*Recommend: `Drawing(grid=..., floating=[...])`, with today's form still accepted.*
- What a view carries: camera, scale (explicit like 1:5, or fit), focus (a feature or box to frame, for
  details), which timbers, X-ray mode. Which of these are in the first cut?
- `"Front"` meaning two things (timber face vs world): make the camera explicit
  (`look=TimberFace.FRONT` vs `look=World.FRONT`) and keep the label as text only?

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
