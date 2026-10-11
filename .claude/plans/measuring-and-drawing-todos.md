# Measuring, selection and drawing TODOs

A batch of TODOs, reviewed against the code. Order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8.
Sections 3, 6 and 7 wait on the open questions marked **Q**.

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

Selection stays global; measuring is per view. In a drawing's orthographic view, both ends of
a measurement have to be visible in that view, or the click is refused ("hidden"). Finishing a
measurement in another view than the end was picked in stays allowed. X-ray (7) is the way to
measure what is hidden, deliberately.

`kumiki/drawings/visibility.py`, exact for points and lines (all a 2D view can measure):
- a point: the line from it to the camera, cropped against each member's solid;
- a line: the plane of sight through it cuts each member in a region whose outline is that plane
  against every flat face plane, cropped exactly to the surface; the outline's camera side,
  projected back onto the line, is what is hidden -- a union of intervals;
- a face seen edge-on: visible if any of its edges is;
- each is first nudged off its own timber into free space, sideways to the view first, so an
  outline counts as visible;
- a curved primitive the lines of sight could reach makes it "visible, not exact" -- no sampling.

Later: place a measurement's anchor on the visible part (the stretches are returned); draw
hidden lines dashed; cache per view for auto drawing.

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

- A toggle; x-rayed timbers see-through and clearly marked; selecting a feature can x-ray its timber.
- Joints tagged `XRAY_FROM_AXIS` (face-aligned directions) for the directions worth x-raying from.
- **Q5:** are features inside an x-rayed timber pickable (builds on 5)? Is x-ray "the timber is
  see-through" or "this joint's hidden lines are drawn"?

## 8. Auto drawing

- No generator exists yet: required features and the solver do (featuresolving-plan.md, Part 2 E
  is the missing piece).
- Greedy: add the measurement that removes the most unknowns; ties go to ones from the reference
  face/edge. Each placed in a view where its features are visible (section 5).
- Test on a single timber with joints, and on a rough timber with its perfect timber within.

## Status

- [x] 1. Measuring fixes
- [x] 2. Code-made measurement overrides
- [x] 3. Selection modes
- [x] 4. Highlighting
- [x] 5. Hidden features
- [ ] 6. Perfect vs rough
- [ ] 7. X-ray
- [ ] 8. Auto drawing
