# Feature solving: implementation plan

Implementation plan for the design in `featuresolving.md`. Two parts:

1. **Required feature set:** which features of a cut timber must be solved.
2. **Solver:** given the measurements, how many DOFs each required feature has left, reported in a form a drawing generator can act on.

All numerics are floats (`rule.py` is numpy/float), with explicit tolerances.

**Status:** Part 2 A (`dof_solver.py`), B and C (`solve_recipe.py`, recipes on the CSG classes) and a first D (`feature_solving.py`: 3D distances, and horizontal/vertical sheet distances between points) are in. Not yet: angle rows, measurements between timbers, projected perpendicular distances, `Own` recipes, `PathExtrusion` carriers, Part 1, and the generator.

# Part 1: the required feature set

## What exists

- A cut timber's CSG is `Difference(timber_prism, [joint negative CSGs])` (`CutTimber.render_timber_with_cuts_csg_local`), and `walk_csg_with_parity` yields every primitive with its parity.
- Each primitive's declared features are its defaults + `feature_overrides` + `extra_features` (`get_declared_features`).
- `real=False` features (cylinder axis, reference planes) name no surface, so they are never hidden.
- `FeatureMarkingStatus` (`OPTIONAL` / `ALWAYS_MARK` / `NEVER_MARK`) exists as declared intent that nothing reads yet.
- `cropcsg.py` crops lines exactly (`crop_line_to_boundary_segments_on_csg`) and planes only approximately (`approximately_crop_plane_to_area_on_csg`, which ignores subtractions).

## Which features get which test

Every declared feature falls in one of four classes. The class comes from the feature's recipe (Part 2 B), so it is decided per primitive, not guessed.

| Class | Examples | Test |
| :--- | :--- | :--- |
| Face, flat or curved | prism sides, caps, a half space's plane, a cylinder barrel, path extrusion sides | two-sided section (flat) or generator lines (curved), below |
| Face-bound edge or point: the intersection of faces of its own primitive | prism arrises and corners, extrusion arrises and corners; derived edges and points | none. One on the final surface lies on faces that are also on it, so solving those faces solves it |
| Free real edge or point: not the intersection of its primitive's faces | a real `ProgrammableCSGFeature` edge or point, a real extra line | edge: exact line crop, required iff some boundary segment has positive length (`crop_line_to_boundary_segments_on_csg`). Point: required iff `is_point_on_boundary` |
| Non-real edge or point | a cylinder axis, a peg centreline extra, a reference line or point | the hidden test doesn't apply: it names no surface. Required by default |

On top of the table:

- Anything marked `NEVER_MARK` is dropped.
- Anything marked `ALWAYS_MARK` is required even if hidden.

A cylinder's barrel carrier moves with its axis carrier (Part 2 B), so when the barrel is required the axis is solved with it, not separately.

## Flat faces: two-sided sections

For a plane Π, compute two regions in Π:

- **below:** where the solid has material immediately on the −n side
- **above:** where it has material immediately on the +n side

Up to measure zero, the boundary of the solid within Π is exactly `above XOR below`. Both come out of one tree walk:

| Node | above / below |
| :--- | :--- |
| Convex primitive, Π cuts through its interior | section polygon on both sides |
| Convex primitive, Π is one of its face planes | face polygon on the side the solid is on, empty on the other |
| Convex primitive, Π only touches it | empty (line or point contact) |
| `SolidUnion` | union of each side |
| `Intersection` | intersection of each side |
| `Difference` | `base − ∪ subtract` for each side |

A face F is **required iff `area(F's own polygon ∩ (above XOR below)) > ε`**. F's own polygon is its primitive's two-sided section on its own plane. This is the exact rule (a patch with area, not just a touching point), so grazing contact comes out right for free.

Side effects worth having:

- The documented `Difference` limitation goes away for this query: where two cutters share a face, there is material on neither side, so it is not boundary.
- The surviving region is the output, which gives `approximately_crop_plane_to_area_on_csg` an exact replacement (anchors stop landing on removed material).

### Per primitive

The walk only needs each primitive as a union of convex half-space sets:

| Primitive | Source |
| :--- | :--- |
| `HalfSpace`, `RectangularPrism`, `ConvexPolygonExtrusion` | exactly their half spaces (`solid_bounds`) |
| `ConvexPolygonSimpleLoft`, flat sides | exactly its half spaces (`_loft_sides_are_planar`) |
| `ConvexPolygonSimpleLoft`, twisted sides | `solid_bounds` fallback, flagged approximate |
| `PathExtrusion` | `decompose_path_into_convex_pieces`, arcs polygonized. Not `solid_bounds`, which gives the hull and is wrong for concave paths |
| `Cylinder` | caps are half spaces; the barrel's section (an ellipse, or a strip when Π is parallel to the axis) is polygonized finely. Only near-tangent cases can be misjudged |

### Planes and tolerance

- Candidate faces are grouped by coincident plane first, so each distinct plane is walked once (roughly 40 per timber). The group is also the merged-plane identity the solver uses.
- Coincidence tolerance around 1e-7 m: looser than `_IN_PLANE_EPS` (1e-9), because coplanar faces of different primitives are computed along different float paths.
- Seed each plane's region from the timber's finite bounds. The timber prism can be semi-infinite before cuts, but the final solid is finite.
- Sliver filter: drop pieces whose area is below ε·L² (L = timber section size).

## Curved faces

A cylinder barrel or an arc side of a `PathExtrusion` is ruled. Sample generator lines around it (e.g. 32) and run the existing exact `crop_line_to_boundary_segments_on_csg` on each. The face is required iff any line has a boundary segment of positive length.

This is approximate only for slivers narrower than the sampling. Documented, not blocking. Later option: unroll the surface into (θ, z) and reuse the region kernel.

## Deliverables

1. **`kumiki/planar_region.py`:** a region as a list of disjoint convex polygons in a plane frame. Union, intersect, subtract (convex − convex splits into at most k convex pieces), area, sliver filter. Unit tested on its own.
2. **`two_sided_section(csg, plane)`** in `cropcsg.py`, with a per-primitive convex half-space provider (the table above).
3. **`required_features(cut_timber) -> RequiredSet`:** every declared feature with
   - its class (table above)
   - its reason: buried / in air / swallowed / on surface / face-bound / non-real / waived / marked
   - its surviving region (faces) or segments (free edges)
   - its solving carrier (Part 2 B)
4. **Kigumi debug overlay** colouring faces required or hidden. It's the fastest way to check correctness across the pattern book.
5. **Tests**, from the cases in `featuresolving.md`:
   - tenon back face buried, and exactly on the shoulder
   - mortise cutter top face in the air
   - relief cutter swallowed by a union
   - lap cutter side flush with the timber face (required, merged with the datum)
   - peg hole: through (caps hidden) and blind (bottom cap required)
   - cutter plane grazing a timber arris (hidden)
   - concave dovetail `PathExtrusion`
   - two cutters sharing a face
   - peg hole axis: required by default, dropped when marked `NEVER_MARK`
   - a free real edge extra, partly on the surface and fully buried

# Part 2: the solver

Five pieces. A is pure linear algebra. B and C are where kinds of feature and primitive live. D connects them to the drawing, and E generates measurements.

## A. Core: `kumiki/dof_solver.py`

Pure numpy, no kumiki imports.

- **Columns:** named unknown blocks, one per carrier.
- **Rows:** sparse, each labelled with its source (datum / convention / measurement id), so a report can say which measurement solved what.
- **`KnownSpace`:** an incrementally maintained orthonormal basis of R's row space (Gram–Schmidt with re-orthogonalisation), with a relative rank tolerance.
- **Column scaling** by a characteristic length, so angle unknowns and length unknowns mix sanely in the rank tolerance.
- **`remaining(target_rows)`:** project the target's rows onto the complement of R's row space and take the SVD. Returns:
  - the **count** of remaining DOFs
  - the **free combinations in the target's own coordinates** (left singular vectors with nonzero σ). For a plane with coordinates (offset, tilt₁, tilt₂), `[1, 0, 0]` means "offset is free". This is what makes the result interpretable.
- **`total_remaining(targets)`:** the same over all required features stacked.
- **`gain(candidate_rows, targets)`:** how much adding a candidate lowers the total, for the generator.

Tests on hand-built matrices:

- the tenon's 6 offsets solved by 6 measurements, with 1 remaining when the length is left out
- 4 corners of a face are redundant (rank, not count)
- a singular layout of collinear distances
- "parallel" entered as an angle of 0 solves nothing; entered as an explicit constraint it solves 2

## B. Feature recipes on the CSG classes

Measurements are written against declared features: defaults (`side.0`, `arris.5`, `corner.3`), overrides and extras, and derived edges and points. The solving is done on carriers: merged planes, cylinders, free lines and points. So every feature needs a fixed statement of how it is built from its primitive's independent geometry. That statement is a fact about the primitive, the same kind of fact as `locate_simple_unbounded`, so it lives on the CSG classes.

**Per primitive, `carriers()`:** the primitive's independent geometric pieces, each with a local id.

| Primitive | Carriers |
| :--- | :--- |
| `HalfSpace` | 1 plane |
| `RectangularPrism` | 4 side planes + each finite cap plane |
| `ConvexPolygonExtrusion` | n side planes + each finite cap plane |
| `ConvexPolygonSimpleLoft` | n side planes (flat sides only) + 2 cap planes |
| `Cylinder` | 1 cylinder (axis + radius) + each finite cap plane |
| `PathExtrusion` | a plane per straight segment, a cylinder per arc segment (axis parallel to the extrusion) + each finite cap plane |

**Per feature, `solve_recipe(owner)`:** a `Recipe`, the list of references to the carriers producing the feature, which is the carrier itself for non-derived features.

| Recipe | Used by |
| :--- | :--- |
| `(carrier,)` | every face; a cylinder axis |
| `(c1, c2)` | prism and extrusion arrises, derived edges |
| `(c1, c2, c3)` | prism and extrusion corners, derived points (an edge's recipe followed by a face's) |
| `(own carrier,)` (not yet) | a feature tied to nothing else: a free extra line or point, a `ProgrammableCSGFeature`. It brings its own carrier |
| `None` | a feature that can't be measured yet (a twisted loft side). Measurements to it are reported, not silently dropped |

The prism edge and vertex features already know their `PrismFace`s, and derived features already carry their two parents, so most recipes are a few lines. The recipe also gives Part 1 its classes: several carriers is face-bound, its own carrier is free.

**Carrier map:** every primitive carrier in the timber's tree, hidden or not, maps to one solving carrier:

- coincident planes (Part 1's grouping) map to one merged plane
- everything else maps to itself

Columns are every solving carrier. Only required features are targets. So a measurement to a hidden feature still resolves: a corner of the tenon's back face that sits on the shoulder is `(back, cheek₁, cheek₂)`, and since the back face is merged with the shoulder, its rows land on the shoulder's and cheeks' columns. A measurement whose rows touch only non-target columns is legal, and worth a warning ("measures something not on the piece").

The map carries a sign: merged planes can face opposite ways, and a plane written as (−n, −d) is the same plane, so its coefficients are flipped on the way into the merged columns.

**Worked example: a point-to-point measurement.** A horizontal distance between corners p1 and p2 measures `u·(p1 − p2)`, with u the view's right axis. Neither point has unknowns of its own. Say p1's recipe is `(A, B, C)`.

A plane has unknowns offset δd and tilts α1, α2 (δn = α1 e1 + α2 e2). Moving the planes moves the corner by δp, where each plane still passes through it:

```
(n_i + δn_i)·(p + δp) = d_i + δd_i   →   n_i·δp = δd_i − p·δn_i   (first order)
```

Stacking the three planes as the rows of N gives `N δp = r`, so

```
u·δp1 = wᵀ r,   where Nᵀ w = u
```

That is the row: coefficient `w_i` on plane i's offset, and `−w_i (p1·e_i1)`, `−w_i (p1·e_i2)` on its tilts. p2 is the same with its own planes and a minus sign, and the two are added together.

For an axis-aligned corner (A: x = a, B: y = b, C: z = c) N is the identity, so w = (1, 0, 0) and the row touches plane A only:

| Column | Coefficient |
| :--- | :--- |
| δd_A | 1 |
| α_A1 (e = ŷ) | −p1.y |
| α_A2 (e = ẑ) | −p1.z |

In words: the x of the corner depends only on the plane that fixes x. The tilt terms say that if A might tilt, where along A the corner sits matters. If A's normal is known (square convention), those columns are already in R, and the measurement is effectively `δd_A − δd_D` for p2's x-plane D.

Then the carrier map puts each coefficient in its solving carrier's column. If A is the tenon's back face merged with the shoulder, the 1 lands on the shoulder's offset. If A and D map to the same carrier (two points on one plane), the offsets cancel and only tilt terms remain: measuring two points on one face along its normal is a check on that face's tilt, which is the right answer.

For a sloped face, N isn't the identity and w spreads over all three planes. The recipe and the formula don't change. A derived point (edge × face) flattens to the edge's two planes plus the face, and goes through the same formula.

**Tests:**

- for every default feature of every primitive, the geometry its recipe builds equals `locate_simple_unbounded` (plane, line or point)
- every declared key has a recipe
- derived edges and points: recipe of the pair equals the pair's located geometry
- the tenon back-face corner above resolves to shoulder and cheek columns

## C. Carrier model: the part that depends on the kind of feature

One small class per carrier kind, holding pure geometry. Each provides:

- **own rows:** its coordinates, which are what "solved" means for it
- **displacement along u at x:** the row for the first-order motion of the feature at point x, measured along direction u (used by distance measurements)
- **direction rows:** the row for the motion of its normal or direction (used by angle measurements)
- **needs:** turning a free combination into what kind of measurement would fix it

| Carrier | Own rows | Displacement along u at x | Direction rows | Free combination → need |
| :--- | :--- | :--- | :--- | :--- |
| Plane (n, d; tilt basis e1, e2) | offset, 2 tilts | `(δd − x·δn) / (n·u)` | normal | offset → a distance along n; tilt about eᵢ → an angle, or a second distance at a spread anchor |
| Line | 2 shifts, 2 turns | its perpendicular motion at x | direction | shift → distances in the 2 perpendicular directions; turn → an angle |
| Point | 3 | `u·δp` | — | a distance along the free direction |
| Cylinder | axis (4) + radius | radial motion at x (radius only enters through a radius/diameter measurement) | axis | radius → a diameter; axis → as Line |
| Line from 2 planes | none of its own | chain rule: solve the 2×2 parent-plane system for its perpendicular motion | from parents | pushed back to the parent planes |
| Point from 3 planes | none of its own | chain rule: `N δp = (δdᵢ − p·δnᵢ)` | — | pushed back to the parent planes |

The last column is why the output is feature dependent. A DOF count is generic. But turning "this combination is free" into "measure this" depends on the carrier: an offset wants a distance along the normal, a tilt wants an angle or a spread second distance, and a radius accepts only a diameter.

## D. Interface layer: `kumiki/feature_solving.py`

Features and `Measure`s in, a per-feature report out.

**Columns and targets** come from B and Part 1: the carrier map gives the columns, the `RequiredSet` the targets. A target's rows are its recipe's rows (identity for `Is` and `Own`, chain rule for `Meet`).

**Measure → rows.** Resolve each anchor (`FeaturePath`) to a feature and owner, take its recipe, and map through the carrier map. Then reuse `drawing.py`, so the rows describe what is actually drawn:

1. `distance_anchors` gives the two anchor points. u is the dimension direction: the view axis for horizontal/vertical, otherwise the unit vector between the anchors (square to the features, so sliding along them doesn't matter).
2. Row = `u·δ_b(anchor_b) − u·δ_a(anchor_a)`, with each δ from the anchor's recipe (C). For projected kinds u already lies in the sheet, so motion along the look direction drops out.
3. Angles go through `angle_rays`, and the row is the derivative of the angle between the two rays.

**Finite-difference tests:** perturb each carrier, recompute the value with `pair_separation` / `angle_between`, and compare to the row. This pins the linearisation to the real measuring code.

**Seeding R:**

- **Datum policy:** which timber faces start fully known (see decisions).
- **Square convention:** any plane whose design normal is parallel to a datum normal gets its normal rows.
- **Merges** need no rows: merged planes already share columns through the carrier map.

**`SolveReport`:**

- per required feature: remaining count and its needs (e.g. "tenon tip: offset along +z unsolved")
- the timber's total
- which rows solved what, by label
- measurements that resolved to nothing, or only to non-target columns

The Part 1 debug overlay also colours features by remaining DOFs.

## E. Generator

Once A–D agree on real joints.

- **Candidates:** pairs of (unsolved feature, known feature), with measurement kinds from `kinds_for`, in viewports whose look direction is square to the needed direction u.
- **Pruning:** keep only candidates whose u has a component along a need.
- **Selection:** greedy by `gain`, ties broken toward conventional measurements (from a reference face, perpendicular).
- **Output:** each choice becomes a `Measure` with `MeasurementSource.PYTHON_GENERATED`, so the existing override rules (code and file overrides replace generated) apply unchanged.

# Order

1. **Part 2 A**, the core solver. Isolated, quick, de-risks the maths.
2. **Part 2 B**, recipes on the CSG classes, with the recipe-vs-locate tests. Needed before anything maps a measurement, and gives Part 1 its feature classes. Can proceed in parallel with 1.
3. **`planar_region.py`** and **`two_sided_section`**.
4. **`required_features`**, the carrier map, and the debug overlay.
5. **Carrier model** and **interface layer**, with the finite-difference tests.
6. **Generator.**

# Decisions needed

1. **Datum:** do the 4 long perfect-timber-within faces plus one chosen end start known, with the timber's length as a measurement? Or all 6 faces? PTW or rough?
2. **Marking:** reuse `FeatureMarkingStatus` (`NEVER_MARK` = waive, `ALWAYS_MARK` = required even if hidden), or add a separate solve flag?
3. **Curved faces:** is sampling barrels with generator lines acceptable for now?
