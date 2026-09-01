# Drawing mode — refactor plan

Status: done and merged to main. All seven phases landed, plus the two defects
they turned up (see Fixed along the way). What remains is the feature work
listed at the end of Phases.

Kigumi needs to render the same frame several ways at once: a drawing is a set of
locked orthographic viewports over a subset of timbers, next to a live
perspective preview. Today the viewer is one scene, one camera, one 5,300-line
component, so this is a refactor before it is a feature.

## Terminology

- **Scene** — one view of the data. Either the default 3D scene or a drawing.
- **Page** — the sheet a drawing is laid out on. Viewports are rectangles on it.
  The 3D scene is a page holding one viewport that fills it.
- **Viewport** — a rect on the page, with its own camera. A scene has one or many,
  and they may overlap.
- A scene declares which **camera controls** exist. The 3D scene shows the cube,
  orbit gizmo and the rest; a drawing shows none.
- A scene knows about **all** timbers. Its member list decides what is
  measurable; everything else is **ghosted by default**.
- The 3D scene is one unlocked viewport on a page that is the canvas, so it runs
  the same path as a drawing rather than being a special case in the code.

Layouts come from python. The viewer renders what it is told.

## Data model

Normalized rects, blueprint-frame cameras. The default 3D scene:

```json
{ "id": "default-3d",
  "cameraControls": ["cube", "orbitGizmo", "projection", "focus"],
  "viewports": [
    { "id": "main", "rect": [0, 0, 1, 1], "locked": false,
      "projection": "perspective" } ] }
```

A drawing viewport adds `camera` — `right`, `up` and `look` vectors, validated
orthogonal, with `target` and `extent` — plus `locked: true`, `members`,
`ghostOthers` and `measurements`. The camera position is derived along `look`,
so the spec is purely about orientation, which is all a locked orthographic view
needs, and measurement marks can be placed against those axes directly.

Pan, zoom and drag-nudge live as viewer-local **deltas** on top of the locked
angle. They are never sent back to python.

## The page

Built. The sheet renders, viewports float on it, pan and zoom move the page
and a drag tilts a locked view within a bounded cone. What is not built yet:
line weight still works in pixels rather than scaling with the paper, and
nothing declares an overlapping viewport, so overlap is tested but unused.

A drawing is a sheet with views arranged on it, so there are four coordinate
spaces and we currently name three:

| space | what it is | owned by |
|---|---|---|
| world | the timbers, in metres | kumiki |
| view | what one viewport's camera sees: orientation, target, `extent` | the drawing |
| **page** | the sheet; viewports are rectangles on it | the drawing |
| canvas | screen pixels | the viewer |

`rect` is normalized to the *canvas* today, which fuses the last two. Separating
them is the whole change: a rect becomes a fraction of the **page**, and a
viewer-local page transform (offset and scale) maps the page onto the canvas.
Normalized fractions stay normalized, so the format is unchanged.

A page has a real size, because drawings get printed, and that size is the
drawing's to choose rather than a fixed menu of paper names:

```json
{ "page": { "width": 0.420, "height": 0.297 } }
```

Metres, the same unit as everything else on the wire; the viewer shows mm or
inches per the units setting, and kumiki can offer A3/Letter/Arch-C as presets
without the format knowing about them. `page: null` means "the canvas", which is
what the default 3D scene wants -- one viewport filling whatever window it is
given. So a scene is a page holding viewports either way, and the 3D scene stops
being a special case in the code as well as in the prose.

**Pan and zoom move the page, not a camera.** This is what makes the sheet feel
like a sheet: zooming in enlarges the whole layout while every view keeps its
drawing scale, exactly as moving your head closer to paper does not change what
1:20 means.

That falls out for free rather than needing to be arranged. An orthographic
projection depends on `extent` and aspect; a uniform page zoom preserves aspect,
so no projection matrix changes and no camera moves. Page zoom is rect
arithmetic and nothing else. A test that zooms the page and asserts every camera
is untouched is the one worth writing, because it pins that property.

### Scale is a consequence of a physical page

Once the page has a size, the scale of a view is not something to store and keep
consistent -- it is arithmetic. A viewport is `rect.height * page.height` metres
tall on paper and shows `2 * extent` metres of world, so

```
scale = 2 * extent / (rect.height * page.height)
```

which means the viewer can label an elevation "1:20" without being told, and a
drawing whose extent no longer matches its stated scale is not a state that can
exist.

It is worth having the relation run the other way too, because it matches how
the drawing is actually thought about: nobody chooses 0.609 metres of extent,
they choose 1:20 and let the view be what it is. So a viewport should be able to
declare *either*

- `extent` — fit this much of the model, whatever scale that lands on, which is
  what a preview or the debug drawing wants; or
- `scale` — draw at 1:20, and derive `extent` from the rect and the page.

Both reduce to an extent before rendering, so nothing downstream cares which was
written.

### Aspect stops depending on the window

A viewport's aspect follows from the page, not the canvas:

```
aspect = (rect.width * page.width) / (rect.height * page.height)
```

No canvas term. Resizing the window moves and scales the sheet, and changes
nothing about any camera -- so for drawings the entire class of bug that phase 2
hit, where a camera holds a stale aspect until the next resize, cannot happen.
The canvas-relative form stays for `page: null`, where the window genuinely is
the page.

A sheet also has a fixed aspect while the window does not, so the page transform
letterboxes: there is margin around the paper. That is correct, and it is what
tells you at a glance that you are looking at a sheet rather than a viewport.

### Three kinds of movement, and only one is an edit

| gesture | acts on | scope | goes back to python |
|---|---|---|---|
| pan, zoom | the page transform | whole sheet | no, viewer-local |
| drag | tilt of the viewport under the cursor | one viewport, bounded | no, ephemeral |
| reposition contents (later) | that viewport's `camera.target` | one viewport | **yes, it edits the drawing** |

The last row is the one to keep separate. The first two are looking; the third
changes what the drawing *is*, and belongs with the round-trip discipline
described under Measurement round trips -- a small command against the loaded
module, committed on release.

This revises the hard lock. Locked means the declared angle is authoritative and
that panning or zooming the page cannot disturb it, not that the camera is
immovable: a bounded tilt rides on top of the declared angle and springs back to
it. `orbitActiveViewport` refuses outright on a locked viewport today, which is
where that becomes a tilt.

### Overlap, and what a viewport draws on

Viewports may overlap, so that a detail can sit over the corner of an elevation
rather than claiming its own column. The list is ordered and later means on top.

Both halves of that already hold, by accident rather than intent:
`renderViewports` draws the list forward, so a later viewport paints over an
earlier one, and `viewportAtPoint` walks it in reverse, so the topmost is picked
first. Forward draw with reverse hit-test is exactly the convention overlap
needs. It is undocumented and untested, and the reverse loop reads as arbitrary
-- worth stating and pinning before anything relies on it.

**In a drawing a viewport draws on nothing.** It contributes its geometry and
leaves every other pixel alone, so an overlapping viewport floats over its
neighbour instead of punching a hole in it. The sheet itself -- paper colour,
and a texture, border or title block later -- is a **page-space layer drawn
beneath**, once, not something any camera renders. Same mechanism serves
annotations later, on top.

So a drawing composites in three layers: page beneath, viewports over it,
annotations above. `background` stays in a viewport's render settings and is
always none for a drawing, which leaves it meaning what it already means for the
3D scene's single viewport.

Two things make that harder than "skip the clear", and both are worth knowing
before it is attempted:

**Colour must not be cleared, but depth must.** Leaving `autoClearColor` on
erases the neighbour underneath; turning `autoClearDepth` off is worse, because
each viewport then depth-tests against the last one's buffer and geometry
vanishes behind a neighbour it has no spatial relationship to. Disjoint scissor
regions hide this today -- their depth ranges never meet -- so it is precisely
overlap that exposes it.

**`scene.background` defeats all of it.** It currently holds the theme's
gradient texture, and three.js paints a scene background as a full pass inside
the active viewport, whatever the clear flags say. Every viewport would repaint
the gradient over its neighbours. The background has to be null while drawing
viewports render, with the page layer supplying the paper instead -- which is
the right home for it anyway, and where a per-drawing paper override would go.

**Floating changes picking, too.** Where a floating viewport is empty, what you
see is the viewport beneath, so a click there belongs to it and not to the empty
rect on top. Picking should walk the viewports top-down and take the first that
actually *hits* something, falling back to the topmost rect only when nothing
does. Rect-topmost-wins is right for an opaque inset and misleading for a
floating one.

### Consequences worth remembering

**Line weight becomes a property of the paper.** `LineMaterial` works in pixels,
so edge lines currently stay a constant thickness on screen. On a sheet they
should stay constant relative to the page and thicken as it is zoomed, or the
drawing's line weights mean nothing.

**Annotations live in page space.** A measurement attaches to a model feature
but is drawn on the sheet, so its text and witness lines are page-space objects
positioned from a world-space anchor. It is not a third camera.

## Drawings, from code and from file

Agreed, not yet built.

A drawing comes from one of two places, and the difference is worth showing
rather than hiding:

- **From code.** The frame asks for it: `Frame.drawings` names a drawing and
  which timbers it is of. The layout -- page, viewports, cameras -- is not
  written there; the runner works it out from the members, the same way it does
  for a drawing made from a selection.
- **From the file.** `.kigumi/drawings/<stem>.json`, which overlays what the
  code asked for. It may override a drawing the code declares, and it may
  introduce drawings of its own, which is mainly how drawings get set up for
  testing. `.kigumi` is where writes are already proven safe -- refresh stats
  land there on every refresh without waking the watcher.

An override replaces a code drawing outright rather than patching fields of it.
A patch model needs a merge rule for every field and can be arrived at later if
it turns out to be wanted; starting there is a lot of machinery for a case
nobody has hit.

Overrides key on a drawing's id, so a code drawing needs an id that survives
editing the python -- not "the third one". When a code drawing goes away, its
override is kept and shown as a file drawing rather than dropped: an extra row
someone can delete is much better than work disappearing quietly.

### What the tree shows

One row per drawing, in a section of its own. Where a drawing comes from is a
mark, and whether it is saved is another, because those are two independent
things and crossing them into four glyphs makes a legend to memorize:

| mark | meaning |
|---|---|
| `○` | from code; nothing in the file |
| `◐` | from code, overridden by the file |
| `●` | from the file alone |
| trailing `•` | unsaved |

The fill reads as how much of the drawing comes from the file. The trailing dot
is the convention editors already use for a modified tab.

Saving is explicit and saves everything: one deliberate write is far easier to
reason about than a write per edit, and it keeps the watcher question simple.
Reverting an override -- back to what the code asked for -- belongs with it, and
is cheap once overrides exist.

## Modules

| module | owns |
|---|---|
| `scene-store` | scene specs, active scene, per-viewport camera deltas |
| `display-options-store` | the display subset only: theme, edges, shadows, reflections, footprint colour, transparencies, units |
| `camera-controls` | cube, orbit gizmo, light dial, projection toggle, focus, as one toggleable unit |
| `scene-manager` | meshes, materials, highlights, footprints, and the member-to-draw-object mapping |
| `input-controller` | pointer and keyboard intents, routed to the viewport under the cursor |

Display options are read through `resolve(scene, key)`, which returns the global
value today. Per-drawing theme overrides later fill in the override map without
touching call sites. Settings that are not display-ish — export formats, debug,
assembly timeline — stay where they are.

The render loop keeps one scene graph and one renderer, drawing N viewports via
`setViewport` / `setScissor`.

## Phases

Each lands green on its own and changes nothing you can see.

1. **`display-options-store`** and the resolve seam.
   Done when the settings payload round-trips identically.
2. **`scene-store` and the viewport abstraction**, with one full-canvas viewport.
   Includes removing the `cx/cy/cz/orbitDist` forwarding shim, since with N
   viewports "the" camera is ambiguous.
   Done when the render is identical and spec normalization, rect maths and the
   orthogonality check are unit-tested.
3. **`camera-controls`** extracted behind the scene's declaration.
4. **`scene-manager`** — meshes and materials leave the god object.
5. **`input-controller`** — routing by viewport rect, raycasting through that
   viewport's camera.
6. **Panels** out of the template, following `ViewerSettingsPanel`.
7. **Python spec and protocol.** A separate runner command,
   `get_default_drawing_for_debugging(frame)`, returning front/top/right
   orthographic viewports plus one perspective, over all timbers. Named and
   documented as scaffolding: it exists to exercise the multi-viewport path
   until real drawing sets arrive. Separate from the frame payload so a drawing
   never re-serializes geometry.
   Done when it renders four viewports and the 3D scene is untouched.

   Landed. The viewer reaches it through a "debug drawing" checkbox in the
   options panel, which asks python for the scene on first use. Verified against
   a capture: each elevation frames the model exactly where its declared camera
   says it should, to within a pixel.

Entering a drawing from a selection, the filtered layers panel, the leave button
and measurements sit on top of this and are not part of the refactor. The page
(see above) comes before them: pan and zoom belong to it, so building them
against viewport cameras first would only have to be undone.

## Seams for what we are not building yet

**Appearance classes.** From phase 4, `scene-manager` exposes
`setMemberAppearance(key, 'normal' | 'selected' | 'ghost' | 'hidden')`. It writes
per-member material properties exactly as today; later it swaps to materials
shared by class. No caller changes.

**Viewport culling.** `scene-manager.prepareViewport(spec)` runs before each
draw. Today it toggles visibility; later it can select a batch subset or a camera
layer mask.

**Batched geometry.** Merging is internal to `scene-manager`, *provided picking
never reads meshes directly*. From phase 4, hit-testing goes through
`scene-manager.memberAtRay(...)`, which returns a member key. That single rule is
what keeps batching a one-module change; without it, batching breaks picking
everywhere.

None of the three is implemented now. The design only has to leave room for them.

## Scale

The largest example frame today is 75 timbers and 42 accessories, around 350 draw
calls at one viewport. The target is timbers in the thousands, which is roughly
6,000 draw calls at one viewport and five times that across a drawing. That
ceiling exists today and multi-viewport multiplies it, which is why the three
seams above matter more than any of them individually.

The vendored three.js has `InstancedMesh` but no `BatchedMesh` and no
`mergeGeometries`, and every timber's CSG mesh is a distinct geometry, so
instancing does not apply. Batching means upgrading three or merging by hand —
a decision to make with a profile in hand.

## Measurement round trips

Editing a measurement round-trips through python. The numbers, from 311 refreshes
in a session log: `get_frame` 0.50 ms median, `get_layers_tree` 0.30 ms,
`get_geometry` 3.1 ms, `reload_example` **167 ms**. So an edit must be a small
command against the already-loaded module, never a reload. Commit on release
rather than per drag frame.

Writing the customization file must not reach the file watcher. The watcher does
not re-render — it raises the refresh-scene button — but a spurious button on
every measurement edit is still wrong, and it would be a real 167 ms reload for
anyone who turns auto-refresh on.

## Fixed along the way

Two defects the refactor surfaced rather than caused. Both predate it; neither
was visible until something started watching.

**Writing over the text Lit renders.** boot-diagnostics.js caught an unhandled
rejection on every session, six times a run:

```
TypeError: Cannot set properties of null (setting 'data')
```

That is Lit's `_commitText`, which updates a text binding by writing to the node
after the part's start marker, and reads null when the marker has left the
document. Two places wrote text into an element that held a binding, destroying
the markers Lit updates through: `setViewState` pushed the loading overlay into
the DOM by hand because `viewState` is a plain field that schedules no render,
and the member list rewrote its column headings on every option change. The
second was a live bug as well as noise -- the headings were hardcoded English,
so a Japanese reader lost the translated string the moment the table drew. Both
are bindings now. Six a run to none.

**An unfocused window stopping the viewer.** `waitForNextPaint` was awaited in a
loop while geometry is applied and again before a screenshot, and
requestAnimationFrame does not fire while the window is in the background. So
alt-tabbing away mid-run did not slow the viewer down, it stopped it: the frame
never finished loading and the capture never returned. Two tests asked for a
screenshot with no timeout and sat there until mocha gave up 120s later, which
read as a flaky suite for a long time. The wait now races the paint against a
short timer, and those tests pass a real timeout.

## Risks, and how they went

Phase 2 was called the dangerous one -- around thirty call sites, with
`updateCamera`, `onWindowResize`, `applySelectionOpacity` and `updateInfo` all
assuming a single camera -- and it was, though not where expected. The call
sites were mechanical. What broke was framing: cameras were built with a
placeholder aspect and only corrected on resize, so the first render came out
stretched. The aspect maths moved into `scene-store` and got tested there.

"No visible change" being hard to prove was the accurate worry. The extension
suites catch a throw, not a subtly wrong render, and three phases in a row
booted to a blank webview with nothing in the log to say why. That is what
boot-diagnostics.js is for; it earned itself back immediately, and every later
failure named itself in the session log instead of presenting as a timeout.

The lesson worth keeping: for anything about what is on screen, check the
numbers rather than the picture. Phase 7 was verified by predicting where each
elevation should place the model and measuring the capture against it, which is
what showed the framing was exact -- and, earlier, what showed a suspected
regression was a thresholding artifact in my own measurement.
