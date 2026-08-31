# Drawing mode — refactor plan

Status: phases 1-7 landed on `drawing-mode-refactor`. The refactor is done; what
remains is the feature work listed under Phases.

Kigumi needs to render the same frame several ways at once: a drawing is a set of
locked orthographic viewports over a subset of timbers, next to a live
perspective preview. Today the viewer is one scene, one camera, one 5,300-line
component, so this is a refactor before it is a feature.

## Terminology

- **Scene** — one view of the data. Either the default 3D scene or a drawing.
- **Viewport** — a rect within a scene, with its own camera. A scene has one or many.
- A scene declares which **camera controls** exist. The 3D scene shows the cube,
  orbit gizmo and the rest; a drawing shows none.
- A scene knows about **all** timbers. Its member list decides what is
  measurable; everything else is **ghosted by default**.
- The 3D scene is a one-viewport unlocked scene, so it runs the same path as a
  drawing rather than being a special case in the code.

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
and measurements sit on top of this and are not part of the refactor.

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

## Known, not caused by the refactor

The webview raises an unhandled rejection on every session:

```
TypeError: Cannot set properties of null (setting 'data')   at o._ (viewer-app.js)
```

It surfaced the moment boot-diagnostics.js started listening, and it is not new:
the same rejection appears six times per run without the phase 3 changes and
three times with them. Nothing downstream notices -- the viewer boots, and every
suite passes -- so it is left alone for now.

The shape (setting `.data` on a null node, from minified Lit internals) reads
like a part committing to a node that has already gone, which would make it an
update racing teardown. Worth chasing when something depends on it, or when the
panel extraction in phase 6 changes who owns those nodes.

## Risks

Phase 2 is the dangerous one. Removing the camera forwarding shim touches around
thirty call sites, and `updateCamera`, `onWindowResize`, `applySelectionOpacity`
and `updateInfo` all assume a single camera. It is early on purpose: everything
after it is easier once the camera belongs to a viewport.

"No visible change" is also hard to prove. The extension suites catch a throw,
not a subtly wrong render. Viewport count and active scene id go into the panel
snapshot, and phase 2 lands as its own commit to be looked at before anything
builds on it.
