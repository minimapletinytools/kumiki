# From a feature to a drawing

How a feature on a cut timber becomes something picked, measured, solved and drawn. Each step
links to the module that owns it; what a feature *is* is in `featuresystem.md`, how a pointer picks
one in `picking.md`.

```
feature (csg/cutcsg.py)
  -> FeatureHandle: which timber, which node, which feature (csg/feature_paths.py)
  -> FeatureExtent: where it is on the cut timber (csg/feature_extent.py)
       -> sheet_shape: what it draws as in a view (drawings/sheet_shape.py)
       -> pick       (viewer/picking.py)        what is under the pointer, and which is wanted
       -> visibility (drawings/visibility.py)   whether a view can see it
       -> span       (drawings/feature_span.py) what a measurement attaches to
       -> measuring  (drawings/measuring.py)    the plane, the kinds, the anchors, the value
       -> solving    (csg/feature_solving.py)   what the measurements leave unsolved
  -> drawing: auto-dimensioning picks measurements (drawings/auto_dimensioning.py)
```

## 1. The feature, and the tree it is on

A timber's CSG is the rough body carrying every perfect feature, with each joint's cut subtracted:
`CutTimber.render_timber_with_cuts_csg_local()`, the **drawn tree**. Everything below works on it
-- picking, measuring, the solver and the generator alike. A feature is named by a
`FeatureHandle` (the timber, the node that declares it, the feature), and its nature
(`FeatureNature`) says what kind of place it is: REAL (on the surface), PERFECT_REFERENCE (inside
the material: a centerplane, a perfect face in rough stock) or AUXILIARY (in a void: a bore's axis).

## 2. Where it is: FeatureExtent

`extents_of(root, timber).of(feature, owner)` crops the feature once, by its nature, and keeps the
answer for as long as the tree lives:

- a REAL face: the part on the finished surface (`face_cross_section`, front XOR back);
- a PERFECT_REFERENCE plane: the plane cut to the solid (`plane_cross_section`, front ∪ back);
- a line: the pieces of it on the solid, within its own declared span -- or, AUXILIARY, that span;
- a point: where it is.

From the extent: `anchor()` (where a dimension hangs), `outline()` (what a highlight or a dotted
line draws), `polygons()`. Everything that asks where a feature is reads this, so the anchor, the
span, the highlight and the visibility of one feature cannot disagree. `required_features` asks it
too, whether a face reaches the surface.

## 3. What it is on a sheet: sheet_shape

Looking along a view, a point is a point; a line is a point seen end-on, otherwise a line; a plane
is a line seen edge-on, otherwise an area (nothing to draw as a line or measure to). One
tolerance, `SQUARE_TO_VIEW`. Picking, projection for measuring, spans, auto-dimensioning and
visibility all ask it.

## 4. Picking

The runner decodes a pointer request and runs `picking.py`'s three steps: `navigate` (the tree
walk, Ctrl-drilling in 3D), `find_candidates` (in a drawing, everything along the ray, hidden ones
last), `choose` (the caller's index, the measuring preference, the first in a drawing, then
fallbacks) -> a `Pick`. The reply -- highlight mesh, edge segments, the feature's reference,
geometry and anchor, and a measuring verdict -- is built from the Pick. Details in `picking.md`.

## 5. Visibility

`visibility.py` holds the rules once, for two questions: per place, for a pointer (`hidden_at`,
`drawn_over`); per feature, for a view (`nearest_visible_depth`, `visible_by_view`). Not real is
never hidden; only a solid's inside hides; unsure means seen. Only the pointer hides a feature
drawn over by a nearer one.

## 6. Measuring

A measurement (`drawing.Measure`) names two features and a kind. To place it:

- each end's **span** (`feature_span`): the extent, as what the measurement attaches to in world
  space -- a point, a line, or in 3D a plane; on a sheet a face edge-on is a line along itself;
- the **plane** it is taken on (`measuring.measurement_plane`): containing any measured point,
  square to any face, along any edge, otherwise facing the camera;
- the **kinds** the pair admits (`kinds_for_pair`), and `place_pair`: anchors for a distance, a
  corner for an angle, and what it comes to (`settle` -> `Settled`, with a reason when nothing).

A pick's preview (`pick_verdict`, then `place_pair`) and a written measurement go through the same
`place_pair`, so the preview is where the measurement lands. The runner only decodes and encodes.

## 7. Solving

`csg/feature_solving.py` turns measurements into rows over the features' carriers
(`csg/carriers.py`) and says what they leave unsolved. It takes only what it needs --
`SolveDistance` (two features, where on each, along what) or `SolveAngle` -- which
`drawings/measure_solving.py` makes from a drawing's `Measure` and its spans. One solve's working
(carriers, DOF rows, spans, rows) is held by a `Solve` / `DrawingSolve`.

## 8. The drawing

The generator (`patterns/structures/my_cute_frame_drawing_test.py` is the worked example) finds
what must be solved (`required_features`), what each view can see (`visible_by_view`), every
dimension a view could draw between those (`sheet_candidates`), and picks until everything is
solved (`auto_dimension`). The runner resolves each written measurement through step 6 and sends
the viewer its anchors and value; cameras for the views come from `drawings/cameras.py`.
