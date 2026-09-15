# Where the state machine is error-prone, and what to do about it

A review of the viewer with one question in mind: **which state can drift, and
why**. Written before `highlightsFor`, because most of what would make that
change work is worth doing anyway, and some of it should come first.

## The finding that settles the argument

The approach already exists in this codebase, twice, and the two differ in
exactly one way.

| | `renderMeasurements()` | `applySelectionOpacity()` |
| --- | --- | --- |
| What it does | wipes the SVG overlay and rebuilds every dimension | recomputes every member's appearance from current state |
| Called by | **the animation loop, every frame** | eleven setters, each of which must remember |
| Has it ever drifted? | **no** | no |
| Can it? | no | **yes — by nobody calling it** |

`renderMeasurements` throws away the entire overlay and rebuilds it about sixty
times a second, and it is the one visual in the viewer that has never gone
stale. So the cost of "re-derive often" is already being paid, happily, by the
most intricate thing on screen. That is the answer to whether it is affordable
here: it is, and it is already happening.

The difference is only **who calls it**. Appearance is derived just as purely,
but it is reached from `firstUpdated`, `onLayerStateChanged`, `onLayerStateSync`,
four slider setters, `setEdgeMode`, `applyRenderProfilesToScene`, `updateDebug`,
`setActiveScene` and `setDrawingGhostsVisible`. Add an input that affects
appearance — a selected measurement, say — and it is correct only in the eleven
places somebody remembers.

That is the same shape as every bug this branch produced: the `space` field
dropped from a field-by-field payload rebuild, the preview cleared inside a
redraw, `_hoverDrawn` nulled by a teardown. Not wrong logic. Logic nobody
reached.

## What can drift today

### 1. Overlays are event-driven; appearance is derived

Covered in `highlight-states.md`. The seven three.js overlays are built from
whichever pick or hover response caused them and torn down by seven scattered
calls; there is no path from "the state is X" to "these overlays should exist".

### 2. Eleven setters must remember to re-derive

Above. The cure is one reaction point, not a twelfth caller.

### 3. Five drag lifecycles, four of them ad-hoc

`pointerDrag` is a module with a shape — armed, moved, ended. The gizmo, the
light dial, the rail resize and the measurement drag each roll their own: a
field on the app, a pair of window listeners added and removed by hand, and
their own notion of "has it moved far enough to be a gesture yet".

Twelve `removeEventListener` calls are kept paired with their adds by hand. A
missed one is a listener that fires after the thing it belongs to is gone.

### 4. The hover machine has two homes

`hover-state.js` owns the timing — when to ask, which answer is still wanted.
The app owns `_hoverDrawn`, `_hoverBroken`, `_hoverClient`, `_candidateIndex`
and `_lastClientX/Y`. **Both hover bugs lived exactly on that seam.**

### 5. The protocol is a convention, not a declaration

26 message types are posted from the webview; 21 are handled by the extension;
17 come back. Nothing relates the three lists, so:

- `requestExportStl` and `requestExportStep` are **handled and never sent** —
  dead branches nobody can see are dead.
- A field added to a request and not to the extension's field-by-field rebuild
  is dropped in silence. That has happened four times.

### 6. Half the stores are observable

| Observable | Not |
| --- | --- |
| `selection-store`, `scene-store`, `layer-state-store` | `hover-state`, `measure-draft`, `undo-stacks`, `context-menu` |

So half of the state announces changes and half must be polled or remembered by
whoever mutates it. A subscriber has to know which kind it is dealing with.
`layer-state-store` is observable and has **no tests**.

### 7. `viewer-app.js` is 7,383 lines and 138 fields

Not a defect on its own, and not worth splitting for its own sake. It is
*why* the above is hard to see: the eleven callers, the five drags and the two
halves of the hover machine are all in one file, none of them named as a thing.

## What to do, in order

**0. Tests for what is already pure.** `computeSelectionVisualContext` has five
states and a fallback, was split out with a comment saying it is "independently
testable", and has no tests. `layer-state-store` has none either. Free, and it
makes the next step safe.

**1. One derive pass.** A single `applyDerivedVisuals()` — member appearance and
the overlays together — reached from the frame loop beside `renderMeasurements`,
and the eleven manual calls deleted.

Per-frame recomputation over every member is more than the SVG rebuild costs, so
gate it on a **signature**: a cheap value over the inputs that decide appearance
(selection, focus, layers, scene, the sliders). Compare it each frame and
re-derive when it differs. That keeps "cannot drift" without paying for a walk
over every member sixty times a second — and, unlike the eleven callers, adding
a new input means adding it to the signature, in one place, where forgetting is
visible rather than silent.

**2. `highlightsFor(state)`.** What this review was for. Once step 1 exists, the
overlays become a list the pass reconciles rather than seven lifetimes, and a
measurement lighting its features is an entry in that list.

**3. Give the hover machine one home.** Move `_hoverDrawn`, `_candidateIndex`
and `_hoverClient` into `hover-state.js`. The seam goes, and with it the class
of bug that has twice grown on it.

**4. One drag concept.** Fold the four ad-hoc drags into `PointerDrag`'s shape,
with the listener lifetime owned by the module rather than by four pairs of
hand-matched calls.

**5. Declare the protocol.** One list of message types shared by both sides,
with a test that every posted type is handled and every handled type is posted.
It deletes the two dead handlers and closes the silent-drop class for good —
the existing `pick-payload-wiring` test does this for one message's fields, and
this is the same idea for the whole surface.

## What I would not do

- **Split `viewer-app.js` for its own sake.** The size is a symptom. Steps 1–4
  take real machinery out of it; splitting first would just move the seams.
- **Make every store observable.** Tempting for consistency, but `measure-draft`
  and `undo-stacks` are asked questions rather than watched, and step 1 removes
  the reason a subscriber would need to watch them.
- **Touch the runner's state.** It is request/response and stateless between
  calls apart from the slot cache; none of the drift here is on that side.
