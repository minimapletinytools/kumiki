# Measurements — specification

Status: agreed, not yet built. Supersedes the measurement parts of
`drawing-mode-plan.md`, which stands for everything about scenes, pages and
viewports.

This is an overhaul rather than an extension. The picking interaction on the
`measure-mode-wiring` branch is replaced: measurements now start from a feature
you have already selected, so a click in a drawing no longer means "begin a
measurement", and there is a plain selection in a drawing again.

## Terminology

- **Anchor** — one end of a measurement: a reference to a declared feature, or
  to an edge derived from two faces.
- **Plane** — the flat surface a measurement is taken and drawn on. A point and
  a normal. It is the measurement's own property, not the viewport's.
- **Pending measurement** — one that has both anchors but has not been
  confirmed. It lives in the viewer only.
- **3D drawing** — the one reserved drawing that holds the 3D view's
  measurements.

## Why the plane exists

Today a measurement belongs to a viewport and is evaluated with that viewport's
`look`. A drawing viewport is locked, so the number is stable. The 3D view's
camera is not: orbit, and the projection changes under you, so the same two
faces would read a different number from one moment to the next.

Giving each measurement a plane makes the number a property of the measurement.
The viewport stops deciding what a measurement means and only decides how it is
drawn. One evaluation path serves both views.

## Data model

`Measure` gains one field:

```python
plane: Optional[MeasurementPlane]   # point + normal, in world space
```

`MeasurementPlane` follows `MeasurementPlacement`: its own dataclass with a
`from_wire`, because it will grow — a plane that tracks a feature rather than
sitting at fixed coordinates is the obvious next thing, and a bare pair of
vectors leaves nowhere to say so.

`None` means "derive from the viewport", which is what every measurement written
before this means, and what every measurement in an orthographic viewport is
entitled to mean. Files are rewritten to the new form on the next save; there is
no migration step.

### Which side the dimension line sits on

`MeasurementPlacement.offset` is signed, and today its sign is read against the
viewport's screen axes — `dimensionLayout` takes the perpendicular of the
projected run. That cannot survive a plane that outlives any one camera.

The sign is now intrinsic: the in-plane perpendicular is `normal × run`, where
`run` goes from `anchor_a` to `anchor_b`. Anchors are already canonically
ordered by `Measure._canonicalise_anchors`, and that function already negates
the offset when it swaps them, so the convention holds without further work.

The consequence worth stating: a dimension does not flip sides when looked at
from behind. That is a change from today and it is the point of it.

### Where 3D measurements live

A reserved drawing, id `three-d-measurements`, in the same file and the same
format as every other drawing. It carries one viewport, id `main`, with no
camera: the 3D view's camera belongs to the viewer and changes constantly, so
the viewport has nothing to declare.

It is a drawing so that everything already written for drawings — the file
merge, override handling, identity, the panel, saving — applies to it without a
second implementation. It is reserved so that nothing in python declares one.

## The plane

### Deriving it

When a measurement is created, its plane is chosen to satisfy, in this priority
order:

1. It contains any **point** being measured.
2. It is perpendicular to any **plane** (face) being measured.
3. It is parallel to any **edge** being measured.
4. Of the planes left, the one closest to parallel with the current camera's
   plane — closest by the angle between normals.

Position, when no point pins it: through the midpoint of the two anchors.

**Rules 1–3 cannot actually conflict**, which is worth writing down because it
is not obvious and the fallback below otherwise looks like it does real work.
Each of them says the same thing — the plane's normal must be square to some
direction — and two anchors produce at most two such directions: a face's
normal, an edge's run, or the line between two measured points. Two directions
are always satisfiable, by their cross product; parallel ones collapse to the
single-direction case, which leaves a whole family to choose from. Two *skew*
edges are satisfiable too: the plane has to run the same way as both, not
contain either.

So the camera's plane is a genuine fallback rather than a common branch — it is
what rule 4 returns when nothing constrains the normal, and what the code
returns if the geometry arrives malformed.

In a drawing's orthographic viewport rule 4 and the viewport's own plane are the
same thing, so a measurement made there lands on the viewport's plane, which is
the invariant below.

### The invariant, and where it does not apply

**An orthographic viewport's measurements must lie on a plane parallel to that
viewport's.** Not the same plane — position along `look` cannot change an
orthographic projection — the same normal, up to sign, within epsilon.

It does **not** apply to perspective cameras. The projection logic only means
anything orthographically, so:

- the 3D view, whichever way its projection toggle is set;
- a perspective viewport inside a drawing, which is the preview.

Measurements in those are drawn through the live camera and checked against
nothing.

Enforcement is split by who is at fault:

- **Writing** — our own code computing a plane that disagrees with the
  orthographic viewport it is writing into is a bug. Assert.
- **Reading** — a file that says so is data, not a bug: hand-edited, or a
  python viewport whose camera has changed. Refuse with a reason and draw the
  row red. Never silently re-plane; that would change a number the user has
  already read.

## Validity

`measurementStatus` keeps its shape and gains one reason. In full:

| reason | means |
|---|---|
| `unresolved` | an anchor names a feature that is not there. Red. |
| `plane-mismatch` | the plane disagrees with an orthographic viewport's. Red. |
| `not-measurable` | the pair admits nothing in this plane |
| `kind-unavailable` | the written kind is not one this pair admits |
| `degenerate` | the measurement comes to zero |

Red is for a measurement that is broken wherever you look at it. The other three
are about this view, and read as ordinary refusals.

## Selection

This is the part with the most ways to go wrong, so it is written out in full.
There are now four kinds of selectable thing and six modes, and the existing
store already carries the hard-won invariant that a CSG focus means exactly one
timber is selected.

### The state

```
selectedTimbers : Set          multi-select. 3D view only.
focus           : one of       { kind: 'csg' } | { kind: 'measurement' } | null
held            : anchor|null  the first end of a measurement being made
pending         : measure|null both ends, unconfirmed, viewer-only
markedMeasures  : Set          measurements marked for deletion
```

`held` is deliberately **not** the focus. The whole point of the flow is that
picking the second feature moves the focus off the first, and the first has to
survive that. It is drawn in its own colour, which is how the user can see that
it is held rather than selected.

`markedMeasures` is separate from `focus` for the same reason focus is single:
multi-select exists only to delete. Everything else — the kind dropdown, drag,
the info panel — reads `focus` and acts on exactly one.

### By mode

| mode | timbers | features | measurements |
|---|---|---|---|
| 3D, idle | yes, multi | yes, after selecting a timber | yes, click or tree |
| 3D, holding | unchanged | yes, this is the second pick | no |
| 3D, pending | frozen | re-pick replaces the second end | no |
| Drawing, idle | **no** | yes, as if every member were selected | yes, click or panel |
| Drawing, holding | no | yes | no |
| Drawing, pending | no | re-pick replaces the second end | no |

Rules that fall out of it:

- **Entering a drawing purges the timber selection.** A drawing has no concept
  of a selected timber, and carrying one in means every panel has to ask which
  mode it is in before answering. Timbers are still selected *implicitly* when a
  feature on one is focused — that is the existing csgFocus invariant and it is
  left alone.
- **Feature selection in a drawing behaves as if all members were selected.**
  `choosePickAction` returns `csg` for any member of the drawing, rather than
  requiring a prior selection. This is what makes hover work in a drawing at
  all; today it does not, because hover only asks the runner when the click
  would drill into an already-selected timber.
- **The tree selects nothing in drawing mode.** Not timbers, not measurements.
  Measurements are selected in the drawings panel or by clicking them.
- **Measurements are clickable when the pointer is over one and no pick is in
  flight.** Not keyed to whether something is selected — in a drawing there is
  no timber selection to key off.
- **Escape** releases the second end, then the held end, then leaves drawing
  mode in the 3D view. In the drawing view there is no mode to leave, so a third
  press does nothing.
- **Delete and Backspace** delete the focused measurement, or every marked one.

## Creating a measurement

The same flow in both views, from one module. Where they differ is named.

1. **Start.** A feature is focused. "Create measurement from this feature" — a
   button, or the context menu — holds it and enters the flow. In the 3D view
   this enters drawing mode; the drawing view is always in it.
2. **The held feature** is drawn in its own colour and stays drawn while the
   focus moves away from it.
3. **Hover** shows what a click would take, coloured by whether it could finish
   the measurement from here. One verdict answers both the colour and the
   refusal, so what is drawn red is what the click refuses.
4. **The second pick** goes through ordinary feature selection — select the
   timber, then the feature on it — which unselects the first. That is fine; it
   is held, not selected.
5. **Pending.** Both ends are known. The measurement is drawn but exists only in
   the viewer. Re-picking replaces the second end. Escape releases it.
6. **Confirm** writes it, selects it, and pushes one entry onto the undo stack.

The pending measurement is **not** written to the design before confirmation.
Holding it in the viewer costs a little state and removes a class of problems:
a reload, an external edit to the drawings file, or a change of scene in the
middle of making one. Nothing outside the viewer needs to see a half-made
measurement.

### Hover picks the best matching feature

The picker today returns the most specific feature at a point — an edge beats
the two faces that form it. While holding, that is the wrong default: holding a
face and being handed an edge means most hovers refuse.

While a feature is held, the picker prefers a candidate that **yields a valid
measurement**, and among those, one of the same type as the held feature. Type
matching is the tie-break, not the rule: a candidate that matches by type and
admits nothing is worse than one that does not match and admits a distance.

Cycling past the preference stays: Tab, and now also the right-click menu.

### What a 3D measurement may be

Horizontal and vertical are directions of the sheet. The 3D view has no up, so
only perpendicular distance and angle are offered there. `MeasurementDirection`
already says as much in its docstring; this is that rule reaching the viewer.

## Undo and redo

Stacks live in the viewer. One per **(loaded frame, drawing)** — so a file with
four drawings plus the 3D drawing has five, and opening another file has its
own.

- **On the stack**: create, delete, change kind, drag.
- **Not on it**: show/hide, selection, entering or leaving a drawing.
- **Survives** saving. Saving is not an edit.
- **Purged** on reload, and on switching frames. Both are cheap to purge and
  expensive to keep honest.
- **Disabled while a measurement is pending.** There is no half-made measurement
  on the stack to undo, and allowing it would mean deciding what undo means
  mid-gesture. Confirm or cancel first.
- **No interaction with VS Code's undo.** The drawings file is data, not a
  document being edited.

## Rendering

SVG, in both views, from one path. No occlusion — dimensions draw over
everything.

The 3D view has no page, so the existing early return in `renderMeasurements`
goes: the page rect becomes the whole canvas, and world points project through
the live camera exactly as they do through a viewport's. `dimensionLayout` and
`angleLayout` are already pure and unchanged; what changes is what feeds them.

A measurement is drawn in the viewport it belongs to. In the 3D view that is the
one unlocked viewport. The 3D drawing's measurements are **not** drawn in a
drawing view, and a drawing's measurements are not drawn in the 3D view.

Dragging a selected measurement changes `placement.offset` and nothing else:
one degree of freedom, in its plane, perpendicular to the run.

## Panels

### Left rail, both views

Selection panel, then drawings panel, then tree. Today the drawings panel is
above the selection panel; it moves below.

### Selection panel

With a measurement focused it shows what the measurement is between, what it
comes to, and a dropdown of kinds when the pair admits more than one. With a
feature focused it shows what it shows now, plus the button that starts a
measurement from it.

The "draw" button reads **draw frame** with nothing selected and **draw
timber(s)** with timbers selected.

### Drawings panel

Viewports and their measurements, then members. Members lists the timbers even
when the whole frame is drawn: `members (everything)` for the whole frame,
`members (<slice name>)` otherwise, the slice name coming from python.

It keeps its save button. The one beside drawings in the tree is deleted.

### Tree

In the 3D view it gains a top-level **3D measurements** node with an eyeball
that shows and hides all of them at once. Individual measurements are selectable
there. In drawing mode the tree selects nothing.

## Runner commands

| command | for |
|---|---|
| `add_measurement` | exists; gains `plane` |
| `delete_measurement` | new — anchors plus `measureId`, scoped to a viewport |
| `update_measurement` | new — kind and placement, so a drag is not an add |

`add_measurement` currently doubles as "change the kind", because it replaces a
pair already measured in a viewport. That is fine for creation and wrong for
editing: it makes a drag indistinguishable from a create on the undo stack.

Plane derivation is python's, since it needs the features' geometry, and the
camera plane arrives in the payload.

## Deferred

- Occlusion for 3D dimensions. Not built; the SVG path cannot do it, and moving
  to scene geometry later is a contained change.
- Per-measurement visibility. The eyeball is all or nothing.
- Multi-select for anything but deletion.
- A plane that tracks a feature rather than holding fixed coordinates.

## The perspective preview

A drawing's preview viewport behaves as the 3D view does, because it is the same
thing: a perspective camera you can orbit. Measurements are created there the
same way, derive their plane from the live camera the same way, and are checked
against no invariant.

The one difference is the one the drawing view imposes anyway — no timber
selection. Features are picked as if every member of the drawing were selected,
in the preview as in the elevations.
