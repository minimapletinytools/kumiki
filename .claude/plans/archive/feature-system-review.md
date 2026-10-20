# Review: features, picking, measuring and solving

An end-to-end read, 2026-10-18, of the code behind selecting features, measuring them and solving
drawings: `kumiki/csg` (features, `planar_region`, `cropcsg`, `carriers`), `kumiki/drawings`
(`feature_span`, `feature_solving`, `solve_recipe`, `required_features`, `auto_dimensioning`,
`visibility`), `kumiki/viewer/picking.py`, the picking and measuring half of `kigumi/runner.py`, and
the drawing overlays in `viewer-app.js`. About 30k lines between them; `runner.py` (6.8k) and
`viewer-app.js` (7.7k) are the bulk.

The short version: each new capability was added where the bug that asked for it showed up, so
one concept -- *where a feature is* -- is now worked out in five places, three of them different.
Most of the simplification is giving a few concepts one home each.

## Status

| Item | State | Where |
|---|---|---|
| 1. FeatureExtent | Done | #112; the solver too, and the approximate plane crop removed, #113 |
| 2. sheet_shape | Done | #115 |
| 3. Domain logic out of the runner | Done | #117: `drawings/measuring.py`, `drawings/cameras.py`, picking into `viewer/picking.py` |
| 4. The Pick split | Done | #117: `navigate`, `find_candidates`, `choose` -> `Pick` |
| 5. Caches with a home | Done, but one part | #114: per-tree extents in `csg`, `Solve` / `DrawingSolve`, no `__dict__` stashing. The per-timber `TimberFeatures` index of declared features was skipped: `get_declared_features` is about 1% of the generator's time |
| 6. Visibility written once | Done | #116 |
| 7. Vector helpers | Done | #111 (`as_ndarray`, `unit_ndarray` in `rule.py`); `exact_scalar` deleted, #118 |
| 8. Smaller things | Done, but one part | Names, the duplicate centerplane class, the overlays module (#110); the perfect tree's one use documented (#119); one flow page, `docs/internal/featureflow.md` (#120). `picking.py` kept one file, by choice. `feature_at` / `extract_highlight_mesh` left as they are: each is one `feature.real` check, which `FeatureExtent` does not replace, since the highlight walks the rendered mesh |

Also: the feature solver moved to `kumiki/csg` with its own measurement types; `planar_region` is
`cross_sections`. Generator time on the rough cute frame: 725 ms before #113, about 550 ms after.
What is left for speed is in `visibility-performance.md`.

## 1. "Where a feature is" is computed five ways

The single biggest source of complication. Given a feature on a cut timber, the code needs: its
extent cropped to the timber; a point to hang a dimension on; what it is on a sheet; an outline to
highlight or draw; whether a view can see it. Today:

| Where | For | How it crops a plane | How it crops a line |
|---|---|---|---|
| `runner._feature_anchor` | dimension anchors | approximate (`approximately_crop_plane_to_area_on_csg`, cannot subtract cuts) -- or exact `plane_section` for a perfect reference | `line_pieces` |
| `drawings.feature_span.feature_span` | what the solver and measurements measure to | approximate, bounded by the *perfect* prism | `line_pieces` |
| `picking.cropped_edge_segments`, `plane_outline_segments`; `runner._perfect_reference_outline`, `_cropped_reference_segments` | highlights, dotted lines, reference edges | exact `plane_section` / uncropped rectangle | boundary crop, own clipping |
| `drawings.visibility` | the generator's hidden check | exact `face_on_surface` | boundary crop |
| `required_features` | what needs solving | exact `face_reaches_surface` (yes/no) | -- |

Consequences: the anchor and the span for one feature can disagree (a perfect reference anchors on
its exact section but measures on an approximate one bounded by the perfect prism); a fix in one is
missed in the others; and the same exact section is recomputed by each.

**Proposal: one `FeatureExtent` per feature, per cut timber.** A function
`feature_extent(handle, root) -> FeatureExtent` that crops once, by the feature's nature:

- REAL plane: the part on the finished surface (`face_on_surface`'s region).
- PERFECT_REFERENCE plane: the plane cropped to the solid (`plane_section`).
- AUXILIARY: its own extent, uncropped.
- Lines: boundary pieces (real) or own extent (auxiliary).

holding the cropped region or segments in the timber's frame, and answering everything else from
them: `anchor()` (centroid / middle of the longest piece), `outline()`, `span(view)`. Anchors,
spans, highlights, dotted lines and visibility then all read the same extent; the approximate plane
crop goes away. Cached per cut timber (see 5).

## 2. "What a feature is on the sheet" is computed six ways

Classifying a feature against a view direction -- edge-on line, end-on point, or an area to skip --
lives in `picking._sheet_shape`, `auto_dimensioning._on_sheet`, `feature_span` (its `plane_normal`
branch), `picking.measurable_in_view`, `visibility.nearest_visible_depth`'s own classification, and
the viewer's face-on test. Each has its own tolerance (1e-9, 1e-6 `EDGE_ON`, 1e-3 in the viewer).

**Proposal:** one `sheet_shape(feature, owner, transform, look) -> Line | Point | None` in
`kumiki/drawings`, with one named tolerance, used by all the Python; the viewer's rule documented
against it.

## 3. Domain logic lives in the runner

`runner.py` was meant to be the protocol between the viewer and kumiki; it now holds a good part
of the measuring model, untyped against kumiki and only testable by loading the runner:

- measuring: `_plane_constraints`, `_plane_normal`, `_measurement_plane`, `_kinds_for_pair`,
  `_pick_verdict`, `_pick_placement`, `_feature_anchor`, `_measure_span` (a wrapper of
  `feature_span`), `_resolve_measurement`, `_settled_measurement`;
- picking: `_best_matching_candidate`, `_pick_from_candidate`, `_sight_blocker`,
  `_non_real_plane_outline`, `_perfect_reference_*`, `_centerplane_outlines`, `_perfect_face_outlines`;
- cameras: the preview orientation strategies (`orient_by_search`, `OrientedBox`, ...).

**Proposal:** move them into kumiki (`kumiki/drawings/measuring.py`, `kumiki/viewer/pick.py`,
`kumiki/drawings/cameras.py`), leaving the runner to decode a request, call one function, and encode
the reply. They become importable, typed and unit-testable without the runner's module purge (which
has already cost a CI incident and a test fixture contortion).

## 4. The pick handler does four jobs with seven loose variables

`_handle_find_csg_at_point` (295 lines) walks the tree, gathers candidates (a 3D path and a drawing
path), chooses one (a named index, the measuring heuristic, "first visible", then three fallbacks:
a derived edge, a declared edge, the navigated face), and builds the reply. The choice is carried in
`new_path`, `target_csg`, `feature_label`, `feature_type`, `edge`, `declared_edge` and `chosen_hit`,
set differently by each branch; in a drawing the tree walk's answer is computed and then usually
thrown away.

**Proposal:** a `Pick` value (hit, owner, path, label, kind, edge) and three steps:
`candidates(mode) -> [Candidate]` (3D: features at the point; drawing: whole ray, split hidden),
`choose(candidates, request) -> Pick` (one place for index / heuristic / default / fallbacks), and
`reply(pick) -> PickResultWire`. Navigation (Ctrl-drilling) becomes its own small path, used in 3D only.

## 5. Caches stashed on whatever was to hand

To make things fast, results were hung on objects that happen to live long enough:
`RectangularPrism.__dict__["_axes"]`, the cut tree's `__dict__["_perfect_reference_outlines"]`,
`CarrierMap.__dict__["_spans"]` (with a TODO), and `HasFeatures.get_declared_features()` rebuilding
override features on every call (relief primitives now carry an override per default).

**Proposal:** two explicit homes.
- **Per cut timber**, built once with `CutTimber`: a `TimberFeatures` index holding declared
  features per node, node positions, and the `FeatureExtent`s of 1 (lazily). Picking, highlights,
  dotted lines, anchors, visibility and `required_features` read it.
- **Per solve**: a `Solve` object for `feature_solving` / `auto_dimension` (carriers, spans, rows),
  as the TODO on `_span` asks, instead of a `CarrierMap` side effect.

Frozen-dataclass `__dict__` stashing then goes; the prism axes can simply be computed in
`__post_init__` like the timber's perfect prism already is.

## 6. Visibility is implemented twice

The viewer's picking decides hidden per *place* (`split_hidden`: stacked lines plus
`sight_is_blocked` per candidate); the generator decides it per *feature* and analytically
(`visible_by_view`). They agree in spirit but not in rules (picking hides stacked lines; the
generator deliberately keeps them) and share no code past `sight_is_blocked`.

**Proposal:** keep both questions, but write the rules once in `drawings/visibility.py` with the
difference named (per-place for a pointer, per-feature for a view), and have `split_hidden` call it.
Longer term the member id pass (`member-id-buffer.js`) could answer the pointer's question on the GPU.

## 7. Three vector types, and the helpers re-written per module

`V3` (rule's Matrix), numpy arrays and `Float3` are all in use; `_np`, `_unit`, `_floats`, `_exact`,
`_v3` are re-defined in `feature_span`, `feature_solving`, `solve_recipe`, `planar_region`,
`visibility` and `picking`.

**Proposal:** numpy for the numeric drawing code with one small conversions module
(`kumiki/drawings/vec.py`: to/from `V3`), `Float3` kept to `kumiki/viewer` as decided, and `V3` at the
library's edges. Delete the per-module copies.

## 8. Smaller things

- **Name clashes:** two `Candidate` classes (`picking`, `auto_dimensioning`); two `_span`s
  (`visibility`'s strip, `feature_solving`'s measure span); `Segment` / `SegmentWire` / `Segment2D`;
  "extent" meaning three things. Rename to say what each is.
- **Two centerplane classes:** `PrismCenterplaneFeature` survives only on the perfect prism
  (`timber._ptw_centerplanes`); `MidplaneFeature` does the same job generally. Use `MidplaneFeature`
  there too and delete the other.
- **The perfect tree:** since the solver moved to the drawn tree, `render_perfect_timber_within_with_cuts_csg_local`
  is used only for the non-rectangular preview mesh. Keep it there, but say so; `feature_span` still
  bounds by the perfect prism, which 1 fixes.
- **`feature_at` and `extract_highlight_mesh`** each special-case non-real features after the fact;
  with 1, a non-real feature simply has no surface triangles to match.
- **`picking.py` (1350 lines)** is four modules: tree navigation, highlight mesh extraction, ray
  feature search, and drawing candidates. Split along those lines when doing 4.
- **`viewer-app.js`:** the drawing overlays (dotted lines, their materials, the id pass) belong in
  a module beside `highlights.js` and `member-id-buffer.js`.
- **Docs:** `picking.md` and `featuresystem.md` each cover a piece; there is no one page for the flow
  feature -> extent -> pick / measure / solve -> drawing. Write it once 1-5 settle, and keep each
  module's docstring to what it owns.

## Suggested order

1. `FeatureExtent` and `sheet_shape` (1, 2), with the per-cut-timber index (5) as their cache --
   the largest simplification, and it makes 6 and the perf notes cheap.
2. The `Pick` split (4), moving the picking logic out of the runner (3, picking half).
3. The measuring half of 3, onto `FeatureExtent`.
4. The `Solve` object (5), vectors (7), names and dead classes (8).

Each step should keep behaviour identical, checked as the performance work was: the generator's
picks diffed before and after, the full kumiki and kigumi suites, and the app smoke test.
