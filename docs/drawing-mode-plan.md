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

Built. Both sources, the merge, the marks, and the drawings section of the
layers panel. Not built: deleting or renaming a drawing, and reverting an
override back to what the code asks for.

A drawing comes from one of two places, and the difference is worth showing
rather than hiding:

- **From code.** The frame asks for it: `Frame.drawings` names a drawing and
  which timbers it is of. The layout -- page, viewports, cameras -- is not
  written there; the runner works it out from the members, the same way it does
  for a drawing made from a selection.
- **From the file.** `.kigumi/drawings/<stem>.json`, which mirrors the same
  shape -- drawings holding viewports holding measurements. `.kigumi` is where
  writes are already proven safe: refresh stats land there on every refresh
  without waking the watcher.

A file drawing has an id of its own and says outright which code drawing it
overrides, in `overridesPythonDrawing`, rather than overriding by sharing an id.
That is what keeps an override recognisable as one: delete the code drawing and
what remains is plainly a dangling entry to be repointed or removed on purpose,
not something that has quietly become a drawing in its own right.

So a file drawing is one of two things. Naming a code drawing, it contributes
measurements to a drawing the code still lays out. Naming none, it is a drawing
of its own and lays itself out, which is mainly how drawings get set up for
testing.

An override never brings a layout with it. If it did, adding one dimension to a
code drawing would take that drawing's page and viewports into the file and
detach it from the code it was asked for by. Wanting a different layout means
wanting a different drawing, which the file can simply declare.

`overridesPythonDrawing` names a code drawing's id, so that id needs to survive
editing the python around it -- not "the third one". A code drawing that goes
away leaves its override visible and marked as dangling, because work
disappearing quietly is much worse than a row someone can see and delete.

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

## Measurements

The model is built -- what a measurement is, how the two tiers merge, and how
its anchors are named. Nothing shows one yet, and nothing makes one: a
measurement can only arrive by being declared in python or written into the
drawings file. Drawing them and picking them are what remain.

**A measurement belongs to a viewport, and is measured in that viewport's
plane.** This is the whole design, and it dissolves what looks like the hard
part. Two parallel edges lying in different planes seem to want their true
distance in one context and their projected distance in another -- but a drawing
*is* a projection, so the projected distance is the only one that means
anything on the sheet. There is no second case to detect. True 3D distance is a
question about the model, and belongs to a measure tool in the 3D scene rather
than to a dimension on a drawing, which is where every CAD drawing environment
draws the same line.

The viewport already carries a declared `right` and `up`, so projecting is exact
and marks can be placed against those axes directly. In the four-long-faces
layout the camera comes from the timber's own frame, so horizontal on the sheet
is along the piece, and dimensions come out in the timber's axes for nothing.

### Project first, then ask what is measurable

Compatibility is decided on the projected forms, not in 3D:

| projected pair | measurement |
|---|---|
| point, point | distance |
| point, line | perpendicular distance |
| line, line, parallel | separation |
| line, line, not parallel | an angle, not a distance |
| face seen edge-on | behaves as a line |
| face seen as an area | no distance is well defined; refused |
| anything projecting to a point | degenerate; refused |

The same two features can therefore be measurable in one viewport and meaningless
in another, which is correct and is worth showing: in measurement mode only the
features that would work are worth highlighting.

Foreshortening is not a separate hazard, though it looks like one. A measurement
is between two features, never of one, so what could be foreshortened is the
segment between them -- and its projected length is the number the drawing
wants: two mortises at different depths, dimensioned on the front elevation,
should read as their separation across that face. The one case that misleads is
a pair separated purely along the view direction, where the projection collapses
to nothing, and the degenerate row above already refuses it. The question would
return only if a measurement of a single feature's own length ever arrives.

### Where the dimension line goes decides what it means

Between two projected points, the direct distance and the horizontal or vertical
component are all reasonable and none can be inferred. Drafting tools resolve
this by placement: pull the line below and it reads the horizontal component, to
the side the vertical, diagonally the aligned distance. One gesture places the
mark and chooses its meaning, which beats choosing a dimension type first.

### What a measurement holds

Two feature references, the viewport, and the placement. Never frozen numbers:
the point of referencing features is that the dimension follows the model when
the code changes.

### Naming things, and how much a name can be trusted

Three grades of stability are worth keeping apart: the same code producing the
same name on every run, an unrelated edit elsewhere leaving it alone, and
editing the thing itself leaving it alone. An authored name reaches the second
and often the third. A position reaches only the first -- insert something above
it and every reference below moves.

So identity comes from what the author wrote, and position is a fallback used
only where the author did not distinguish two things. Where it is used it gets a
field of its own rather than being folded into a string, so code and people can
both see which references are order-dependent. `kumiki_id` is not identity at
all: it is a counter, already named a runtime-only handle, and must never be
persisted.

`TimberPath` is what the author calls a timber -- a name, and nothing more,
because which of two timbers sharing a name is not a question a name can answer.
`ResolvedTimberPath` is one particular timber in one particular frame, obtained
only by resolving against a frame or by parsing the member key the viewer
already uses, since an occurrence has no meaning until there is a frame to count
within. Resolving is where a duplicated path is discovered, so that is where it
warns -- and the warning says what actually follows from it: those timbers can
now only be told apart by the order they were built in.

The weakest link is not timber names, though. A measurement anchored to a
declared feature is stable against nearly anything; one anchored to a picked but
unlabelled face is "the nth face of this node", and slides when the joint's
shape changes. Eleven of the twelve joint files declare no features, so
**declaring them is worth more to measurement stability than any naming scheme**.

An anchor is a `FeaturePath`: the timber, the labels of the CSG nodes stepped
through, and the feature on the last of them. Names the whole way down and never
a position -- not "the third cut", not "the second face" -- because a position
stops meaning what it meant the moment a joint is added above it. Rename any of
those and the reference breaks, which is the honest outcome; add or reorder
around them and it still finds what it meant.

It carries the feature's type as well as its name, since one label can name both
a face and an edge, and a measurement to the wrong one does not look wrong on
screen.

That way a measurement can attach to anything pickable rather than only to
declared features, which would block measurements behind the eleven joint files
that declare none. A reference that stops resolving leaves the measurement
**greyed out rather than deleted** -- the same rule as an orphaned drawing
override, for the same reason: work that quietly disappears is worse than a
broken row someone can see and fix.

### Measurements come from code as well as from the file

A drawing can declare measurements in python, alongside the timbers it is of.
Most of them will eventually be produced by algorithm rather than written out by
hand, and that is what shapes the rest of this:

**An identity derived from what a measurement measures, never an index.** "The
third measurement the algorithm emitted" stops meaning anything the moment a
joint is added, and every override attached to one would slide onto its
neighbour. Derived from its two anchors, an override stays attached across a
regeneration. An optional `id` disambiguates when the same pair is measured more
than once, which is the only case the anchors cannot separate on their own.

**That identity is the viewport's, not the drawing's.** A measurement lives under
the viewport it is drawn in, and its id only has to be unique there. The same
anchors in the plan view are not this measurement seen from elsewhere; they are a
different dimension with a different number, and one may be meaningless while the
other is fine. So an override reaches only within one viewport.

Moving a measurement between viewports is therefore not a move at all -- the
dimension changes when the viewport does -- which is why it is left out for now
rather than treated as a rename.

**Code measurements are never written to the file.** The same rule as an
untouched code drawing, for the same reason: freezing one would stop it
following the algorithm that produces it.

**So the file has three jobs for a code measurement** -- move it, since an
algorithm cannot know where there is room on the sheet; suppress it, when it is
not one you want; and add measurements the algorithm did not produce. Suppression
is an entry that says "not this one", and is much easier to allow for now than
to retrofit.

This narrows the rule that a file entry replaces a code drawing outright.
Measurements are the exception and merge, because adding one measurement to a
code drawing would otherwise freeze its page, its viewports and its whole layout
into the file and detach it from the code. Everything else still replaces, and
whole-drawing replacement stays available for setting up a drawing to test with.

### Two tiers, three things to show

There are only two tiers: from the file, and not. A file measurement overrides
the one beneath it with the same identity, and that is the whole rule. It still
produces the three states worth marking, the same three a drawing has: a code
measurement nothing has touched, a code measurement the file has overridden, and
one the file introduced.

Two measurements sharing an identity within the same tier is a mistake rather
than a case to resolve, so the later one wins and a warning is logged the first
time the data is parsed. Failing outright would cost someone their drawings over
a hand-edited file, which is the same trade the file parser already makes.

A measurement greys out rather than disappearing when its anchors stop
resolving -- and equally when it has been moved to a viewport where its anchors
project onto each other, since what can be measured is decided per viewport and a
move can therefore invalidate it.

### Where a feature actually is

Agreed, not yet built.

A measurement needs two things from each of its anchors: the geometry to measure
on, and somewhere to attach the drawing. `locate()` gives the first and is
reliable -- an infinite plane or line is exactly what a projected measurement
computes against.

The second is the hard one, because **a feature's declared extent is the extent
of the primitive it was declared on, and primitives are deliberately not the
finished piece**. A half space has no bounded extent at all. A cutter is extended
past the timber on purpose so the cut is clean, and the mortise-and-tenon extends
its by `max(tenon_size) / sin(angle)` -- which for a square joint divides by a
guard value and puts the mortise's front face anchor 476 metres away. The hole is
cut correctly; the anchor is meaningless.

So the extent has to come from the finished piece rather than from what declared
it. Three ways to get it, in the order they should be tried:

**From the triangles.** The mesh already exists, and a feature already knows how
to test whether a point is on it -- that is how picking works, and the docstrings
say real features are tested against the triangulated result first. So the
triangles of the finished member whose vertices lie on the feature *are* its
extent: their bounds and centroid, exactly cropped, with no new geometry code.
This is the answer for a face that survives to the surface.

It also settles a second question for free. A feature cropped away entirely has
no triangles, which is precisely the "this measurement cannot be drawn" case --
so the same pass that finds the extent says whether the feature is on the
finished piece at all.

**From the declared extent**, when there are no triangles but `get_extent()`
gives something bounded and sane. Weaker, but better than nothing for a feature
that is real and simply not on the surface.

**From the geometry and the other anchor**, when there is neither: the foot of
the perpendicular from one anchor onto the other's plane is a perfectly good
place to attach a dimension, and it is the right answer for a half space, which
has a plane and no extent by construction.

Cost is a scan of one member's triangles per anchor, against a handful of
measurements per drawing, so it belongs alongside the mesh cache the runner
already keeps rather than being computed per frame.

### The list is viewports first

Measurements hang off viewports, so the drawing's tree lists viewports and the
measurements within each. That is not only how they are stored; it is what the
reader needs, since the same pair of features measured in the front elevation
and in the plan view are two different dimensions with two different numbers.

Nothing deletes a viewport today. A measurement naming a viewport the layout does
not produce cannot be drawn, so it is not shown and the mismatch is warned about
-- but it is kept, since the viewport may come back when the code changes and
dropping it would mean the next save deleted it from the file for good.

### The drawing's own tree

While a drawing is open there is a tree for the drawing itself: its name and
where it came from, close and save, its viewports with their measurements under
them, and the members it is about -- which is where the filtered member list belongs rather than as a
separate piece of work, since a drawing can only select what it is about anyway.

Where that tree is shown is deliberately left open. It is likely a panel of its
own for drawing mode, but it may end up back in the layers rail, or both may be
shown at once with the members in one and the drawing in the other. So it is
built as content that can be mounted anywhere -- data in, events out, like the
layers panel -- and where it goes stays a one-line decision.

Chains and baselines -- a run of mortises dimensioned from one end -- are not in
this first step, but nothing should be built that a chain could not later be
placed through.

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
