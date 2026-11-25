<!-- 🤖🤖🤖🤖🤖🤖 -->
# Measuring, selection and drawing TODOs

A batch of TODOs, reviewed against the code. Order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8.
The drawing X-ray research in §7 updates the earlier selection and visibility notes.

## 1. Measuring fixes

- **A refused click selects anyway.** `csgSelectionResult` applies the pick as the new selection
  first and only then offers it to the measurement (`_measurePicked`), which refuses it. Fix:
  while measuring, a click the hover showed as refused does nothing but report why.
- **Faces in 2D.** Same cause. In a 2D view a face is projected first: one looking at you is an
  AREA, which admits nothing, so it is refused -- and then selected by the bug above. A face seen
  edge-on projects to a line and can be measured, so faces are not banned in 2D; the fix above
  makes the unmeasurable ones do nothing.
  - Edges outrank faces at a point, and most faces seen edge-on are also a declared or derived
    edge there, so projecting them is mostly redundant. Only a few have no line edge to stand for
    them (a cylinder's cap seen edge-on). Those should be labelled so the rest are not projected.
- **Hotkey `M`: measure from this.** Bound to the existing "start measurement from focus".

## 2. Deleting and editing code-made measurements

- Deleting a measurement the Python code made writes a "deleted" marker in the drawings file, the
  way drawings already mark an override.
- Deleting one that was edited removes the edit, putting the original back; deleting again deletes
  it. (Q1: decided.)
- A deleted one is listed greyed and not drawn; right-click "put back" restores it, as does undo.
  Deleting one already deleted does nothing.

## 3. Two selection modes

`pickMode` in selection-store.js. Decided (Q2):

- **Feature mode:** a click goes straight to the feature on the nearest timber; the selection is
  ignored.
- **Timber mode:** a click selects a timber; a click on one already selected picks the feature on
  it, wherever it is along the ray. Features light only on selected timbers.
- **In a drawing:** feature mode. Timber mode is off behind `TIMBER_MODE_IN_DRAWINGS`, and works if
  turned on (then as in 3D).
- **In 3D:** timber mode while nothing is held to measure from. Once measuring: feature mode, and
  shift held for timber mode -- a click selects a timber in place of the selection, and with shift
  still held a click on it picks its feature. Outside measuring, shift-click still adds or removes
  a timber from the selection.

## 4. Highlighting

- **The light-blue parent** of a selected feature: an option, off by default. Ctrl-click
  descending through the CSG tree stays.
- **Reference features:** timbers declare them on their ticket (`TimberTicket.reference_features`).
  Highlight them as a new `reference` role in feature-states.js: on by default in drawings, a toggle
  in 3D. Folds in render-states step 4 (locked members, measurement ends).

## 5. Hidden features in drawing views

- Walk the pointer's ray through the drawing's timbers (exact intervals from the CSG), look for
  features at every surface crossing, and mark each visible or hidden by depth.
- Visible first in pick and Tab order; the right-click list split into Visible and Hidden; hidden
  highlights dashed.
- The same test places a measurement only in a view that shows its features on the surface.

## 6. Perfect vs rough features

- Done for Q3: a rough face lying on the perfect timber within is named `rptw.*` and grouped
  PERFECT (and so is an arris or corner whose faces all are). No backwards compatibility.
- Every timber has `ptw.*` and `rough.*` faces; with no rough allowance they coincide. Picking
  ranks perfect first, but derived edges can still be named after rough faces.
- `FeatureMarkingStatus.NEVER_MARK` exists but nothing reads it yet.
- **Q3:** a rough face lying exactly on a perfect one: dropped/merged so only `ptw.front` shows, or
  renamed and kept?
- **Q4:** "PTW features added in drawing mode": show the perfect body in drawings? And "rough
  features do not measure": not measurable at all in drawings, or just never chosen automatically?

## 7. X-ray (drawing mode)

**Requested behavior.** A drawing can reveal hidden joinery from specific sides. Its lines have a
distinct appearance and can be selected, measured by hand and used by auto-dimensioning. The
reader can turn X-ray on directly or get a temporary reveal when selecting a feature on a timber.
The feature belongs to drawings. The following are proposed defaults for how it works.

### What the drawing should show

| In this viewport | On paper | Pointer and measurement behavior |
|---|---|---|
| A normally visible part of an edge | Solid stroke | Ordinary pick and dimension anchor |
| A hidden part of a tagged feature or its finished boundary, viewed from an allowed side with X-ray enabled | Lighter, short-dashed stroke | Pickable, labelled “X-ray”, eligible as an anchor |
| A hidden part outside that reveal or behind another drawn timber | Omitted | Disabled in the candidate menu and excluded from new dimensions in this view |

- **Direction.** Add `xray_from_faces` to `FeatureProperties`, using an immutable set of the
  existing six signed `TimberFace` values, empty by default. A joint author can reveal the
  mortise bottom from Front while giving the walls their own directions. Every direction is
  relative to the timber receiving that feature, even for a rotated cutter. `FRONT` means the viewer is on the local
  +Y side, looking along −Y. Compare the actual orthographic camera's unit look vector to the
  negative world-space face normal within an alignment tolerance. A custom camera qualifies on
  the same basis. An oblique view or perspective preview gets ordinary geometry. Preserve the
  meaning of the faces when restoring a `FauxTimber` cut and check mirrored piece groups.
- **Toggle and selection.** A drawing control could offer **Off / On selection / On**. Off
  suppresses temporary reveal. On selection exposes eligible features on the focused timber in the
  viewport where the feature was selected, until focus clears. On works even with nothing
  selected, so the first hidden feature is reachable. All three respect the allowed sides.
  Use a dashed sample labelled “X-ray” in the drawing legend and keep the dashes on hover and
  selection. Use a pattern distinguishable from centerlines and perfect-timber references in
  monochrome. The timber silhouette stays readable.
- **Occlusion and overlap.** Reveal only final cut boundaries through their own timber. Clip
  portions behind another drawn member. A partly exposed edge changes from solid to dashed
  exactly at the occlusion boundary. Where a dashed line lies on a visible outline, the solid
  stroke and ordinary pick take priority. Tab and the menu can reach an eligible feature at the
  same mark. Preserve existing rules for locked members, drawing context, auxiliary axes and
  perfect references.
- **Measurement.** Hover, click, Tab, the candidate menu and both measurement picks need the
  same classification at the pointer. Auto-dimensioning asks a different question about the same
  geometry: whether both anchors have a usable projection somewhere in this viewport. Prefer a
  normally visible view for an otherwise equally useful dimension. Retain the solver's existing
  purpose, projection and independence rules. Recheck the final attachment after a face is
  replaced with an edge, and place its witness line on the eligible stretch.
- **Saving and export.** Use the existing feature paths for dimensions. When a committed manual
  or generated dimension depends on X-ray, record the reveal in that viewport so reopening or
  exporting the drawing reproduces the witness geometry. Show those committed anchors on selection
  mode even after deselection. Suggested Off behavior is to suppress
  that dimension with its hidden anchors while keeping it in the measurement list. A temporary
  hover or selection should never change what prints. Screen, PNG and SVG need the same side,
  clipping, stroke priority and committed dimensions.

### Where the implementation fits

- **Authoring.** Both mortise builders in `kumiki/joints/workshop/mixed/mortise_and_tenon_joints.py`
  declare `mortise_bottom` with a `FeatureOverride`. For a rectangular mortise it is one face
  of a prism that also declares the walls. For a flared mortise it is the plane of a separate
  half-space. Set the property on the bottom feature in either representation. When a whole
  bore or socket should share directions, offer a CSG helper following `with_purpose` in
  `kumiki/csg/cutcsg.py`: apply the directions to the features of the chosen subtree at authoring
  time. Use it before composing the cutter with relief or other cuts, and add any individual
  exceptions afterward. Picking, export and the generator can all read one effective feature value.
- **Finished boundaries.** A tagged face authorizes the stretches of edges that bound it on
  the finished timber. This includes a shared crease with an untagged wall. The rest of the
  wall gets no reveal from that face. For a declared prism arris, resolve its incident face keys
  on the owning prism. For a derived intersection, use the parent feature handles. Keep this
  association on the clipped stroke or point so the same rule covers picking, bore rims and
  face-to-edge dimension placement. Repeated feature names on different cutters remain distinct.
- **Live drawing.** `kigumi/webview/drawing-overlays.js` already draws dashed geometry per
  camera and clips reference lines by member. The ordinary `EdgesGeometry` in `viewer-app.js`
  only supplies positions. A joint overlay needs feature-owned geometry. Check clipping with
  overlapping timbers as well as a single piece. Keep selection-driven reveal in the drawing
  pass. `member-states.js` deliberately isolates 3D selection opacity from drawing appearance.
- **Picking.** The earlier §5 checklist predates the current picker.
  `kumiki/viewer/picking.py:drawing_candidates` already orders hits from all drawn timbers and
  separates visible and hidden candidates. `kigumi/runner.py` reports a selectable count and a
  Boolean hidden flag. Carry the third “X-ray” state through that reply so a dashed pick can be
  enabled and identified. Re-evaluate outstanding hover or Tab choices when the view or mode changes.
- **Generator.** `kumiki/drawings/visibility.py:visible_by_view` is the entry point for anchor
  visibility. Both the initial pass in `auto_drawings.py` and the edge/corner fallbacks in
  `auto_dimensioning.py:measurable_targets` use it. Pass the same reveal policy to both and to
  `faces_to_edges`. Generate against the authored view without waiting for an interactive
  selection. A shop sheet has four long-face views by default. An end-only tag can contribute
  an X-ray dimension when a matching end view is present.
- **Export.** `kumiki/drawings/svg.py:render_svg_view` already draws an `xray` underlay through
  every member and then draws the visible edges solid. The live viewer's edge-mode list has no
  X-ray entry. Reuse the linework, including arcs, and supply the effective reveal for each
  viewport. The existing SVG mode alone would expose unrelated cuts and other members.

### First acceptance case

The `Left Side` blind mortise in `tests/test_view_visibility.py` provides a baseline. I probed
its `mortise_bottom` with `nearest_visible_depth` in the four shop views, first with the timber
occluding itself and then with its material omitted from the occluders for this anchor only.
The last column is the proposed behavior.

| Shop view | Current anchor eligible | Eligible through own material in the probe | Tagged FRONT only, X-ray on |
|---|---|---|---|
| Front | No | Yes | Dashed, pickable, dimensionable |
| Back | No | Yes | Hidden |
| Right and Left | No | No | No projected bottom-line dimension |

I also ran `solve_piece` with the visibility query altered in memory for just `mortise_bottom`
in Front. The normal run produced 13 dimensions. The probe produced 14, adding a 43.5 mm Front
dimension from the mortise bottom to `peg_hole_axis`. After the generator's usual face-to-edge
step the first anchor was `arris.9`. A reveal keyed only by the original face name would lose
that attachment. The experiment exercised the solver only. Picking, drawing and export of this
specific dimension still need implementation and an end-to-end check.

Use the front view to measure the bottom from a datum, manually and automatically. Check the
feature paths, value and final attachment after save/reload and SVG export. In the same cutting,
verify the untagged walls and relief gain no hidden strokes beyond the bottom's own boundary.
Repeat with the piece rotated, a second timber covering half the line, and two overlapping
picks. Exercise the existing blind-bore SVG fixture for arcs. Measure hover latency and drawing
generation time on a multi-member sheet before caching per-view geometry.

A related CAD precedent is showing hidden edges of a selected feature or component in an
individual drawing view. [SOLIDWORKS drawing help](https://help.solidworks.com/2019/English/SolidWorks/sldworks/c_show_hidden_edges.htm)

## 8. Auto drawing

- No generator exists yet: required features and the solver do (../archive/featuresolving-plan.md, Part 2 E
  is the missing piece).
- Greedy: add the measurement that removes the most unknowns; ties go to ones from the reference
  face/edge. Each placed in a view where its features are visible (section 5).
- Test on a single timber with joints, and on a rough timber with its perfect timber within.

## Status

- [x] 1. Measuring fixes
- [x] 2. Code-made measurement overrides
- [x] 3. Selection modes
- [x] 4. Highlighting
- [ ] 5. Hidden features
- [ ] 6. Perfect vs rough
- [ ] 7. X-ray
- [ ] 8. Auto drawing
