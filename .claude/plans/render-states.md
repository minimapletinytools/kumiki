# Render states: one object per member and per feature, then render from it

## Where rendering stands

Kigumi draws three layers, plus settings that apply to the whole scene:

1. **Member bodies** (timbers, accessories). One bundle per member in
   `scene-manager.js`: mesh, edges, reflection, round-stock silhouette.
   `_memberAppearance` (viewer-app.js) resolves each to
   `{ name, opacity, edgeOpacity, edgesVisible, reflectionOpacity }` from: the
   selection (5 states in `selection-visuals.js`, each with an opacity policy),
   hidden, drawing context, render profile, the sliders and the edge mode.
   `setMemberAppearance` writes it onto the materials.
2. **Feature overlays**, drawn over the bodies with depth testing off.
   `highlights.js` is pure: `highlightsFor` lists overlays for three sources --
   the selection (tagged node; or a feature and its parent), the hover (orange,
   red when refused) and the held measurement end (green) -- and `reconcile`
   builds, updates and drops them.
3. **Measurements**: an SVG overlay rebuilt every frame.

Layers 1 and 2 are pulled: every frame `applyDerivedVisuals` folds their inputs
into a signature and redraws only when it changes. Render mode, edge mode,
profiles, assembly transforms, footprints and debug geometry write to the scene
directly; render mode is already computed whole each frame.

## What is awkward

- **Precedence lives in `if` order.** In `_memberAppearance` hidden beats the
  selection, then the drawing context caps opacity. Adding locked, fixed or a
  measuring state means finding the right place in that chain.
- **The signature lists inputs by hand**, and a test that reads the source
  exists only to catch a forgotten one.
- **Overlays stack per source, not per feature.** A feature selected, hovered
  and held gets three translucent copies of its geometry layered by draw order,
  and there is no one answer to "what state is this feature in".
- **Features have no identity across sources**: each source keys its own string.
- **Measuring states are scattered** (green held end, red refused hover,
  `dim-pending` in the SVG).

## The plan

Two stacks, because they work differently: bodies restyle persistent meshes;
overlays are extra geometry from the runner drawn over them.

1. **`MemberState`, per member** (`member-states.js`). Describes, does not
   resolve: `{ hidden, selection: 'none'|'selected'|'drilledInto'|'dimmed',
   drawing: 'none'|'subject'|'context' }`. `memberStateFor(key, snapshot)` is
   pure; `appearanceFor(state, settings)` resolves it, with the precedence
   written as an ordered list rather than nested `if`s. Behaviour unchanged.
2. **`FeatureState`, per feature** (`feature-states.js`). The sources merged by
   one feature key: `{ key, roles: { selection, hover, held } }`, each role
   carrying the geometry its source sent. `highlightsFor` draws from these, one
   overlay per role as today. No visible change.
3. **One overlay per feature.** A feature's roles resolve to one look by
   `ROLE_PRIORITY` in feature-states.js, first match wins: a refused hover
   (red, the click would refuse it), then the held end (green), then the hover
   (orange), then the selection (blue). A selected feature's dim parent is other
   geometry, so it stays as context whichever role leads. Changing the order is
   editing that list.
4. **New roles and states**: locked/fixed members; a feature that is an end of
   an existing measurement. Each becomes a row in the tables above.

Measurements could later take a `MeasurementState` (pending / committed /
selected / refused) the same way; that is independent of the two 3D stacks.
Render mode, edge mode, profiles and assembly transforms stay as they are: they
are scene-wide settings or transforms, not per-thing styling.

## Status

- [x] 1. `MemberState` + `appearanceFor`
- [x] 2. `FeatureState`, drawn one overlay per role
- [x] 3. One overlay per feature
- [ ] 4. Locked/fixed, measurement-end roles
