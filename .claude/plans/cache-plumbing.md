# Caches with owners: no more global memos

Status: plan, nothing done yet (2026-10-20).

## The problem

Several caches live in module-level tables, keyed by an object's identity (`memo_by_identity`,
`_extents_memo`) or switched on by a block (`point_tests_memo`). None of them write onto a frozen
object, so the frozen contract holds on paper. But they are global state:

- nothing in a function's signature says its answer is cached, or for how long;
- every one is correct only because its key never changes after it is built;
- they grow for the life of the process, kept small only by weakref finalizers;
- the point-test memo makes a point test's cost (not its answer) depend on the block it runs in.

The rule this plan applies: **a cache belongs to an owner that is passed down the call tree**, or
it is a fact about a frozen object worked out when the object is built (`_precomputed`, as agreed
for `RectangularPrism._axes_precomputed` and `CutTimber`).

## Inventory

### To convert (global, keyed by identity)

| Cache | Where | Keyed on | Callers | Owner it should have |
|---|---|---|---|---|
| `solid_bounds` | `csg/edges_on_csg.py` | primitive node | `edges_on_csg` span walks, `cross_sections._sides` | the node: `_precomputed` |
| `_declared_features` (`get_declared_features`) | `csg/cutcsg.py` | node | 16 uses: feature walks, `feature_paths`, `required_features`, picking, runner, patterns | the node: `_precomputed` |
| `_face_plane_carriers` (`carriers()`) | `csg/cutcsg.py` | node | `solve_recipe`, `carrier_map` | the node: `_precomputed` |
| `_extents_memo` (`extents_of`) | `csg/feature_extent.py` | tree root | `feature_span`, `required_features`, `visibility`, `kigumi_measuring_helpers`, `picking` | `CutTimber` (one `FeatureExtents` per cut timber), passed where a root is passed today |
| `_directed_memo` | `csg/assumptions.py` | `CarrierMap` | `square_assumptions`, `sheet_axis_assumptions` | `Solve` (holds the carriers already) |
| `_reference_names` | `drawings/auto_dimensioning.py` | timber | `is_reference`, criteria, two patterns | `Solve`, or the timber's ticket: `_precomputed` |
| `_key` | `drawings/auto_dimensioning.py` | `FeatureHandle` | `auto_dimension` | a local dict in `auto_dimension` |
| `_corners_memo`, `_placement` | `drawings/visibility.py` | solid, transform | `_blocking`, `_frame_in` | an occluder record built once in `visible_by_view`: (solid, transform, rotation, position, corners) |
| `point_tests_memo` (ContextVar + `__init_subclass__` wrapping) | `csg/cutcsg.py` | node + point | `find_all_features`, the runner's pick handler | a pick context passed to `find_all_features` and the point tests (the TODO in `cutcsg.py`) |

### Keep (not global state in the sense that matters)

- **Pure value caches**: `solve_recipe._axes_of` (a direction's perpendicular axes, bounded LRU);
  `timber.py`'s `_ptw_face_tags`, `_ptw_centerplanes`, `_rough_face_tags` (constant tuples);
  `RectangularPrism._default_features_memo` (one constant table per class). Same answer for the
  same arguments, forever.
- **Built at construction** (`_precomputed`): `RectangularPrism._axes_precomputed`; `CutTimber`'s
  rendered and extended trees; `PerfectTimberWithin`'s perfect prism and end cuts.
- **Already owned**: `FeatureExtents._extent_memo`, `Solve._dof_rows_memo`,
  `DrawingSolve.spans_memo` / `rows_memo`. These are the model.
- **The runner's process state** (`_patterns_cache`, `_project_module_loaded_at`, the mesh cache
  entries' `world_box` / `world_triangles`): owned by the runner and its slots. Out of scope.

## Steps

Each step on its own, checked the same way: the full tests, the drawings of
`my_cute_frame_drawing_test` and `cat_corner_cot` identical before and after (dump
`collect_drawings`), the pick probes identical, and load and pick times no worse.

1. **Node facts at construction.** `solid_bounds`, declared features and face carriers become
   `_precomputed` fields set in each primitive's `__post_init__`; the global functions read them.
   - Cost to watch: every node pays at construction, used or not. Measure tree build time on
     tinyhouse first. If it is too much, a node can hold a lazily filled private slot instead
     (still the node's own state, not a global table) -- decide with numbers.
   - `get_declared_features` keeps returning a fresh list; the features themselves are shared.
2. **Extents on the cut timber.** `CutTimber` holds its `FeatureExtents`. `extents_of(root, timber)`
   callers get it from the cut timber (or a passed `FeatureExtents`), and `_extents_memo` goes.
   - `feature_span`, `feature_anchor`, `visibility`, `required_features` take a `FeatureExtents` or
     a `CutTimber` where they take a bare root today.
   - Picking: the runner's mesh cache entry holds the cut timber, so the slot owns it.
3. **Solve-scoped caches on `Solve`.** `_directed_memo` and `_reference_names` move onto
   `Solve` / `DrawingSolve`; `square_assumptions` and `sheet_axis_assumptions` take the solve
   rather than the bare `CarrierMap` (keep a `CarrierMap` overload while patterns migrate).
   `_key` becomes a local dict in `auto_dimension`.
4. **Visibility's occluders.** `visible_by_view` builds an occluder record per drawn timber once
   (solid, transform, float rotation and position, box corners) and passes the records to
   `nearest_visible_depth` and `_blocking`. `hidden_at` (picking) builds them per pick.
5. **The pick context.** Replace `point_tests_memo` with an explicit context:
   `find_all_features(point, tolerances, context=None)` passes it to `collect_feature_hits`,
   `SolidsAtPoint` and the `contains_point` / `is_point_on_boundary` / `get_outward_normal` of
   `Difference`, `SolidUnion` and `Intersection`. Primitives don't need it. The runner makes one per
   pick. Remove the `__init_subclass__` wrapping and the ContextVar.
   - The biggest step: those three methods' signatures change across `cutcsg.py` and `pathcsg.py`.
   - A default of None keeps every other caller (and kumiki users) working unchanged.
6. **Delete `identity_memo.py`** once nothing imports it.

## Risks

- **Construction cost** (step 1) for code that builds many throwaway nodes. Measure first.
- **Public signatures**: `extents_of`, `square_assumptions`, `sheet_axis_assumptions` and
  `find_all_features` are used by patterns. Keep the old forms working for a release, or bump.
- **Lifetime**: today a cached result outlives a solve; owned caches die with their owner. A
  generator that rebuilds its `DrawingSolve` per drawing loses cross-drawing reuse, so check the
  cat corner cot's per-member solves don't get slower.
