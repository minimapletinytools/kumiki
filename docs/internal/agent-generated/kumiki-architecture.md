# Kumiki architecture and code navigation

> **AGENT-GENERATED — supplemental, not human-authored policy.** Reviewed 2026-11-13 against `b7fdf0d8`. Existing instructions and user decisions take precedence. Source may have changed since this review.

Read the [canonical concepts](../../concepts.md) and [authoring rules](../../../.github/instructions/authoring.instructions.md) first. Paths below are relative to the repository root. This guide describes the implementation, including distinctions that older prose may omit.

## From a recipe to a view

1. A builder declares and resolves Kiwari, creates members, and places them using construction helpers.
2. An arrangement describes the relationship between members. A cutter produces a `Joint` containing cuttings and any accessories.
3. A `Frame` collects members and joints. A `CutTimber` combines the stock with the applicable removed solids and end-cut metadata.
4. CSG features retain semantic names for selection, measurement, and assembly reasoning.
5. Consumers mesh the solids, export them, or derive drawings. Kigumi serializes a frame through its Python runner and requests more expensive data as needed.

Placement, cutting, meshing, and drawing are separate operations. Moving a member is not equivalent to changing a cut's local coordinate system.

## Mathematical and geometric foundations

| File | Responsibility |
| --- | --- |
| `kumiki/rule.py` | Scalars, units, angles, immutable NumPy-backed matrices, vectors, orientations, numerical helpers |
| `kumiki/geometry.py` | Points, lines, planes, spaces, bounded segments, and shared intersection operations |
| `kumiki/footprint.py` | Two-dimensional footprints used to position members and cuts |
| `kumiki/timber_features.py` | Face, end, edge, corner, and centerline vocabulary |
| `kumiki/measuring.py` | Timber-relative markings and conversions between relative and world geometry |

Current ordinary scalar math is float-backed. `Matrix` preserves the library's matrix-operation interface; do not substitute an ndarray and assume `*` has the same meaning. Use `as_ndarray` or `unit_ndarray` at boundaries that need NumPy. Older references to exact scalar geometry do not describe the current general numerical representation. Isolated exact calculations do not make the whole model symbolic.

World axes are right-handed: X east, Y north, Z up. Timber-local +Z runs from bottom toward top, +X toward RIGHT, and +Y toward FRONT. A face-relative distance is positive **into** the timber, opposite its outward normal. A cross-sectional position uses the timber centerline and local X/Y axes, even at the opposite end.

In `measuring.py`, `locate_*` takes relative markings to world geometry, `mark_*` expresses world geometry relative to timber features, and `scribe_*` converts between relative descriptions. These are distinct from drawing dimensions and from locating an unbounded CSG carrier.

## Members, placements, and cuts

`kumiki/timber.py` owns member types, the perfect timber within rough stock, cutting and joint records, accessories, cut members, and frames. `Timber`, `Board`, `RoundTimber`, and other stock forms share modeling concepts but have different boundaries. The perfect timber within is the construction reference; it is not necessarily the outer surface of the stock.

`kumiki/construction.py` owns placement helpers and arrangements such as butt, corner, cross, and splice relationships. Prefer current `attach_*` helpers for attachment; several older `join_*` alignment conveniences are deprecated. Inspect the specific signature rather than inferring a replacement from its name. `join_timbers` also serves general spanning construction and is not blanket-deprecated.

`kumiki/timber_shavings.py` supplies support distances, alignment predicates, and accessory helpers. Use these when an operation must account for rough or nonrectangular stock instead of assuming the perfect reference box is the real surface.

A cutting describes removed CSG and may carry top/bottom end-cut distances. End metadata participates in producing appropriate stock ends; it is not merely viewer metadata. `Joint` is the product of a cutter, not a mutation of the source members.

## Joint implementation map

| Location | Responsibility |
| --- | --- |
| `kumiki/joints/workshop/` | Active cutter families: butt, corner, cross, splice, mixed, board, free, decorative |
| `kumiki/joints/workshop/basic_joints.py` | Recipes deriving dimensions and counts from an arrangement |
| `kumiki/joints/workshop/shavings/` | Reusable cut construction, shoulder/peg operations, relief, and related helpers |
| `kumiki/__init__.py`, `kumiki/joints/__init__.py` | Public export chain; definitions alone do not establish public availability |
| `kumiki/example_shavings.py` | Canonical arrangements and stock configurations for examples/tests |

A typical cutter validates the arrangement, locates a shoulder or other reference, computes cut geometry in explicit spaces, adds necessary relief/accessories, and returns a joint. The build-a-butt helpers separate insertion geometry, shoulders, and pegging so related cutters can share these operations.

Basic cutters delegate to general cutters after deriving useful defaults. They retain placement or joint-style decisions that cannot be inferred. They are not a parallel geometry implementation. Not every `cut_*` needs a basic wrapper: custom shapes, already-inferred inputs, and alignment conveniences may offer no meaningful simplification. Some experimental APIs remain stubs; inspect their bodies before proposing wrappers.

Current ordinary rectangular, round, and corner tenon basic recipes use stopped tenons with a default based on three quarters of receiving depth. Tusked and wedged half-dovetail recipes require through geometry. Do not generalize one recipe's default to every tenon family.

## CSG, features, and identity

| File under `kumiki/csg/` | Responsibility |
| --- | --- |
| `cutcsg.py` | Primitive and boolean solid tree; feature labels, properties, and coordinate adoption |
| `pathcsg.py` | Closed line/arc profiles, extrusion, and their features |
| `triangles.py` | Meshing, mesh operations, and raycasting |
| `edges_on_csg.py` | Cropping lines against solids and deriving boundary/crease geometry |
| `cross_sections.py` | Sections, outlines, areas, centroids, and projected shadows |
| `feature_paths.py` | Resolve named features into runtime handles |
| `feature_extent.py` | Locate the portion of a feature on the final cut solid |
| `required_features.py` | Identify the actual features that need fabrication information |
| `symmetry.py` | Compare pieces under identical, rotated, or mirrored configurations |
| `identity_memo.py` | Identity-based memoization for repeated geometric work |

The CSG tree is the modeled solid. A triangle mesh is a derived representation and does not replace the feature tree. `adopt_csg` handles coordinate adoption; a local primitive must be transformed into its parent's space correctly before composition.

A plane carrier is unbounded. Its visible or measurable extent on a cut member may be cropped, split, or absent. Work involving placement on the actual surface should use extent/cropping helpers rather than the infinite plane alone.

`kumiki/ticket.py` carries labels and metadata. Slash-separated labels form organizational hierarchies. `kumiki/identity.py` distinguishes authored paths from resolved paths: duplicate names require occurrence-based disambiguation, which depends on order. A serialized feature path is a reference to resolve against a particular frame/CSG tree, not a guarantee that the target still exists after a rebuild.

Feature labels affect navigation and saved references. Meaningful labels belong at the level that owns the operation. Repeating the same label on nested nodes changes the path and makes it ambiguous to a reader. See the canonical label rules before changing them.

## Feature solving and drawings

The CSG layer imports nothing from `kumiki/drawings/`. Solving a feature's geometric freedom and laying out a dimension on a sheet are distinct responsibilities.

| Location | Responsibility |
| --- | --- |
| `csg/carriers.py` | Plane, line, point, and barrel unknowns |
| `csg/solve_recipe.py` | Derive constraint/motion rows from geometry |
| `csg/feature_solving.py`, `csg/dof_solver.py` | Measurement constraints, rank, and remaining degrees of freedom |
| `csg/assumptions.py` | Known relations such as squareness and sheet axes |
| `drawings/drawing.py`, `drawings/layout.py` | Drawings, viewports, subdivisions, resolved page rectangles |
| `drawings/measure.py` | Dimension kinds, anchors, projection, and placement |
| `drawings/measure_solving.py` | Adapt drawing measurements into solver inputs |
| `drawings/feature_span.py`, `drawings/sheet_shape.py` | Cropped spans and projected shapes |
| `drawings/visibility.py` | Analytical visibility/occlusion |
| `drawings/auto_dimensioning.py` | Generate/select dimensions to address unresolved features |
| `drawings/auto_drawings.py` | Plan/shop drawing generation and grouping related pieces |

Paths in this table are under `kumiki/`. Automatic dimensions can leave unresolved features; preserve and inspect warnings instead of equating a generated sheet with a completely specified part. Drawing layout, visible geometry, and solver completeness each need their own verification.

`kumiki/drawings/kigumi_measuring_helpers.py` and `kumiki/drawings/kigumi_drawing_view_helpers.py` bridge library measurements and viewer-facing placement/camera needs. Their location does not make the CSG layer dependent on a browser.

## Assembly and finishing

`kumiki/assembly.py` represents translational/rotational freedoms, ordering constraints, members, joints, and assembly results. Its disassembly solver considers allowed motion and collision. A visually plausible joint does not automatically describe a valid assembly route; authored freedoms are separate information.

`kumiki/finishing.py` supplies post-build work, progress, drawing accumulation, cancellation, and tool actions. A frame can exist before expensive finishing completes. Code adding finishing work must honor cancellation and avoid publishing results for a superseded build.

## Parameters, discovery, and examples

`kumiki/kiwari.py` declares adjustable values, validates overrides, and records resolved values/origins. Builders read typed values such as `k.length("width")`; Kiwari is not an arbitrary attribute bag. Return resolved Kiwari on the frame so the viewer can show what was actually used.

`kumiki/frame_decorators.py` defines `@frame`/`@pattern` entry behavior. `kumiki/patternbook.py` wraps pattern metadata and builders. `kumiki/librarian.py` discovers entries through source/AST inspection; listing does not execute every recipe. Building later imports and executes the selected entry. Dynamic registration can therefore work at runtime yet be invisible to discovery.

`kumiki/librarian_cli.py` is the external discovery interface. `kumiki/_pattern_index.json` is the packaged index, regenerated with `tools/build_pattern_index.py`. Discovery cache validity and Python import invalidation are different concerns.

Public structures live in `patterns/structures/`; internal fixtures live in `hidden_structures/`. Joint examples are organized by family, with basic recipes in `patterns/basic_joints_patterns.py`. Follow the canonical pattern/variant/Kiwari and frame preamble rules; update `docs/api_cheat_sheet.md` when the catalog changes.

## Export, tests, and change routing

`kumiki/blueprint.py` provides mesh exports and optional STEP support through CAD dependencies. `kumiki/kigumi_at_home.py` provides local rendering; `kumiki/viewer/` supports that viewer. Rendering and CAD dependencies have different availability constraints, so preserve optional-import boundaries.

For a new joint, trace arrangement → cutter → cutting/labels → public exports → geometry tests → pattern → cheat sheet. For a measurement problem, trace identity → resolved feature → cropped extent → projection → solver adaptation. For missing catalog entries, inspect decorators and librarian/index behavior before editing the viewer.

Use `tests/` to verify actual geometry, metadata, and relevant invariants. Joint tests should sample material and boundaries, including unequal sizes or rotated arrangements where supported. The canonical authoring rules specify full Python tests and type checking after library/test changes. Documentation-only changes need link/path and diff checks, not a claim that runtime behavior has been tested.
