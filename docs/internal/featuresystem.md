# Introduction
This doc describes the kumiki geometry feature system.

kumiki implements its own CSG (constructive solid geometry) system to generate all timber and joint geometry. 

# Files

- csg/cutcsg.py: the main csg classes live here
- csg/pathcsg.py: adds PathExtrusion csg class
- csg/cropcsg.py, csg/planar_region.py: cropping lines and planes against a csg, and which faces are on its surface
- csg/carriers.py: the planes, lines and points features lie on, for the solver
- csg/feature_paths.py: FeatureHandle, and feature references on the wire
- csg/triangles.py: meshing and raycasting a csg
- geometry.py: contains shared geometry feature classes like Plane Line Vertex etc
- drawings/drawing.py: contains all code relate to generating measurements from CSG features
- drawings/: also the layout of a sheet and the feature solver (solve_recipe, dof_solver, feature_solving, required_features)

# Overview

## How kumiki CSGs are created 

`Timber`s produce a `RectangularPrism` CSG representing its volume. It actually produces 2 CSGs, one for its rough volume and one for its "perfect timber within" (PTW). The PTW prism's features are named `ptw.*`. The rough prism's are named `rough.*`, except a face that lies on the PTW -- and an arris or corner all of whose faces do -- which is named `rptw.*` and grouped `PERFECT`: it is the rough body's own face, but measuring from it is measuring from the PTW. A timber with no rough allowance is `rptw.*` throughout. Note that its ends may be extended to infinity if any Joint on it declares itself to be an end joint.

`Joint`s on a timber produce a `negative_csg` that is cut of the timber's prism to produce the joint.

Since a timber may contain many joints, `Joint`s are assembled into `CutTimber`s which combine all joints on a timber. The final CSG is the timber's CSG with each joint's `negative_csg` removed from it. 
Again, whether either of the timber's ends are extended to infinity depend if any of the joint's are "end joints" on that end. Whether the PTW or rough prism is used depends on what the renderer wants. Note that the same `negative_csg` is used for both PTW and rough timber prisms, thus all joints must declare their `negative_csg` as if they were cutting out of the rough timber always.

## How CSGs are rendered

`triangles.py` contains logic to convert CSGs into meshes. The raw geometry is passed as a blob and rendered kigumi or written to stl `blueprint.py`. `blueprint.py` also contains logic to directly render the CSG into a step file.

# The CSG System

The CSG system declares is hierarchical, with various primitives as its leaf nodes and a handful of compositing nodes. Which nodes and their features/limitations are documented in a table below

## Capabilities

The CSG feature tree can answer the following questions

TODO  document limitations of each of these functions

- contains_point: answers whether a point is contained in the CSG
- is_point_on_boundary: answers whether a point is on the boundary of the CSG
- get_outward_normal: returns the outward normal of a boundary point on the CSG


## The CSG Nodes

| Node Name | Node Type (primitive/composite) | contains_curves | File | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `EmptyCSG` | Primitive | No | `cutcsg.py` | Empty solid containing no points; returns `False` for point containment/boundary tests and yields an empty AABB. |
| `HalfSpace` | Primitive | No | `cutcsg.py` | Infinite half-space defined by a normal vector and signed offset (`P · normal >= offset`). Boundary is a single unbounded planar face. |
| `RectangularPrism` | Primitive | No | `cutcsg.py` | Box primitive with rectangular cross-section `(width, height)` along local Z; can be finite or semi-infinite/infinite on either end. Declares planar face, arris (edge), and corner vertex features. |
| `Cylinder` | Primitive | Yes | `cutcsg.py` | Extrusion with circular cross-section defined by axis, radius, and optional infinite ends. Lateral surface is a curved face (`CURVED_FACE`); end caps are planar. Also declares an internal axis feature (`LINE`, non-real). |
| `ConvexPolygonExtrusion` | Primitive | No | `cutcsg.py` | Extrusion of a 2D convex polygon along local Z with optional infinite ends. All side faces and end caps are planar. |
| `ConvexPolygonSimpleLoft` | Primitive | No | `cutcsg.py` | Straight-line loft between two 2D convex polygons in parallel planes. Requires planar non-twisted side faces (`_sides_are_planar`) and finite length; no curved surfaces. |
| `PathExtrusion` | Primitive | Yes (if path has `ArcSegment`s) | `pathcsg.py` | Extrusion of a closed 2D `FancyPath` along local Z. Supports non-convex profiles; straight segments yield planar faces (`FlatSide`), while arc segments yield curved lateral surfaces (`CurvedSide`, `CURVED_FACE`). |
| `SolidUnion` | Composite | Dependent on children | `cutcsg.py` | Boolean union combining multiple child nodes. Point is in union if inside any child; cancels internal boundary faces where children meet. |
| `Intersection` | Composite | Dependent on children | `cutcsg.py` | Boolean intersection of two child nodes (`left` and `right`). Point is inside if contained in both children. |
| `Difference` | Composite | Dependent on children | `cutcsg.py` | Boolean difference subtracting a list of `subtract` child nodes from a `base` node (`base - subtract[0] - subtract[1] ...`). Outward normals along cut cavities are inverted. | 

## The CSG Feature System

Each CSG leaf node declares a set of `default_features`: every face, arris and corner of that primitive, each at a `FeatureKey` (a `FeatureCategory` and an index, printed as `side.0`, `arris.5`, `cap.1`) and named after that key until someone names it otherwise.

An instance adds to these in two separate ways:

- `feature_overrides`: `FeatureOverride(key, name, properties)` renames a default and/or replaces its `FeatureProperties` (everything in `FeatureProperties`, including `real`, can change). It carries no geometry, so an override can never move or reshape what it names. Keys come from helpers: `prism_face_key`, `prism_arris_key`, `prism_corner_key`, `side_key`, `START_CAP` / `END_CAP`, `HALF_SPACE_PLANE`, `CYLINDER_BARREL`.
- `extra_features`: features with geometry of their own that no default names, e.g. `CylinderAxisFeature` or a `ProgrammableEdgeFeature`. An extra must not report a `FeatureKey`; one that does is naming a default and belongs in `feature_overrides`.

Both are checked when the primitive is constructed. Overriding a key the primitive doesn't have, overriding a key twice, a keyed extra, or two features with the same name raise `ValueError`. `PathExtrusion` has no defaults yet, so its named sides are extras.

Features themselves are bounded geometric primitives

```
class CSGFeatureType(Enum):
    FACE = 1
    EDGE = 2
    POINT = 3
    CURVED_FACE = 4
```

and represented in the `CSGFeature` class. However the `CSGFeature` may not have all the required information to know the feature geometry so many of its methods require passing in the owning CSG object.

Declared features on a CSG can be queried at a point using `collect_feature_hits` and `find_all_features` will also return derived features (see below)

### derived features

Flat face and straight edge features can be assigned a "FeatureGroup" which determines which features in a CutTimber can combine to produce derived features. That is, 2 faces producing an edge, or a face and an edge producing a point.

Note that the feature derivation system currently does NOT support the following:

- derived point features produced from 2 edges
- derived features produced from curved features
- derived features produced from derived features


## Interacting with the CSG System 

### selecting features (technically a kigumi thing)


#### feature priority

Several features can be under the pointer at once -- `_sort_feature_hits` in `cutcsg.py` orders them and clicking on fetaures takes the first one by defalut.

- **Non-real before real.** A centre axis or a centerplane is a deliberate snap, so the surface it happens to lie on does not steal the click.
- **The more specific kind.** Point, then edge, then face (flat or curved). An edge beats the two faces that formed it, and a corner beats its edges.
- **Declared before derived.** A feature something declared beats one derived from a pair of faces.
- **Group rank** (`FeatureGroup`, lower is better): `SHOULDER_PLANE`, `PERFECT`, `ROUGH`, `TENON`, `CROSSING`, then `NONE`. A derived feature takes the better rank of its two parents.
- **Author-set priority** (`FeatureProperties.priority`, lower wins). Default features carry a high value, so anything a joint names beats the prism's anonymous defaults.
- **Name**, alphabetically.
- **Gathering order**, as the last tie-break.

In Kigumi, while the pointer is over a feature:

- **Tab** steps to the next feature under the pointer, wrapping round. The highlight shows what a click would now take. Moving the pointer forgets the choice.
- **Right-click** (without dragging) lists every feature under the pointer, best first, with its kind; choosing a row selects that feature. With only one feature there, right-click opens the member menu instead.

## Limitations

The CSG system has the following limitations

- boundary point comuptations may break in certain cases, in particular if we have `Difference` B C being removed from A, and B and C share a point on faces with opposite normals, and that point is contained in A, that point will be reported as on the boundary of the final difference when it should not be. (this should be fixable)
- an edge cut in half by a another CSG is still reported as a single edge feature spanning the gap. e.g. ---☐--- It is still able to compute its segments for rendering the edge though.
- curved surfaces do not form derived features
- edge edge intersections to not form derived features

# The Measurement/Drawing System 

The complex feature system above is primarily intended for supporting the drawing system.

A drawing is a "page" that contains a set of views. Each view contains a camera and a set of measurements.

A view can be 2d, in which case its camera is orthographic.

There is a special 3d drawing that allows you to add visible measurements to the main 3d view, which is not intended for generating drawings a swell.

Measurements are references to 2 measurable features together with the a "view" from which that measurement is meant to be seen and some cosmetic properties

A drawing can contain one or more timbers. Typically a drawing will be one of the following:

- Blueprint: A blueprint is typically a drawing of a single timber measuring every joint feature so that it can be cut
- Plan: A plan is typically a "slice" of the frame containing multiple timbers and only the main dimensions of the timbers are measured.

## Automatically Generating Drawings

kumiki ships with a drawing generator. Pass a list of timbers you want to generate drawings for, and it will:

- find all features that need to be "measured" in the drawing
- create measurements such that each of those features can be "known" through the drawing
- and do so in a "nice" way so that the drawing looks good both semantically and syntatically


# The Feature Picking System

Feature picking differes if we are in the 3d view or if we are in a 2d orthographic drawing view. 

## 3D:

TODO

## 2D:

Everything below runs on each hover and click in a drawing's view. The runner calls it from
`_handle_find_csg_at_point` and gets back an ordered candidate list, split into visible and
hidden. Plan and history: `.claude/plans/drawing-view-picking.md`; the exact visibility test
began in PR #82.

### 0. What comes in (viewer → runner)

`_pickContext()` (`viewer-app.js`) goes with every hover and click:
- `space`: `'projected'` in a drawing, `'3d'` otherwise;
- `drawnMembers`: in a drawing, the members it draws.

With the click point, the pointer's ray and the pick tolerances, the runner then has: the hit
point and the ray (in the clicked timber's local space), the edge tolerance (a few pixels' worth
in metres), and the drawn members.

When `space` is `'projected'` and there is a ray, steps 1–3 run. Otherwise it is the 3D view's
single-point lookup, `features_at_point`.

### 1. Collect the candidates: `candidates_under_pointer` (`kumiki/picking.py`)

Returns `Candidate(hit, place, depth, group)`: each feature, where along the ray it is, how deep
that is, and its depth group.

1. **At the hit point:** `root.find_all_features(local_pt)`, the features where the ray first hit
   a surface.
2. **Along the rest of the ray:** `real_features_along_ray`. For each declared real feature in
   the tree it finds a place on the ray:
   - a face: `_ray_meets_plane`, where the ray crosses its plane;
   - an edge: `ray_nears_segment`, the point of the segment nearest the ray, if within the edge
     tolerance;
   - a corner: the corner itself, if within the edge tolerance of the ray.

   It keeps only places on the solid's surface (`is_point_on_boundary`) and takes
   `find_all_features` there, which brings in derived edges and points. A feature's depth is the
   smallest at which it was found.
3. **Features in voids:** `merge_ray_hits` adds non-real ones, like a bore's axis, at their
   nearest approach to the ray.
4. **Exact places for edges and corners:** `_nearest_on`. A corner is placed at itself; an edge at
   the point of its line nearest the pointer's ray. Step 2 may have found an edge where the ray
   crossed a face, up to a pixel off it, and testing visibility from there gets it wrong.
5. **Drop what the view can't measure:** `measurable_in_view`. Edges, points and curved faces
   stay. A flat face goes if:
   - it is seen at an angle (|normal · view| > `EDGE_ON`), so it is an area; or
   - it is seen edge-on but a straight-edge candidate lies in its plane (square to the normal,
     within the edge tolerance of it). That edge lands on the same line and measures the same.

   A cylinder's cap has no straight edge in its plane, so it stays.
6. **Order:** `order_along_ray`, nearest first. `_depth_groups` walks the candidates by depth and
   starts a new group whenever one is more than the edge tolerance past the start of the current
   group. The sort key is the group, then the library's ranking (`feature_hit_sort_key`:
   non-real; point, edge, face; declared before derived; ...). So a face and the edges on it are
   one depth and the edge still leads, while anything a few millimetres further back comes after.

### 2. Split into visible and hidden: `split_hidden`

In order, building a visible and a hidden list:
- Non-real candidates (axes) are always visible: snap targets in empty space.
- A candidate is hidden if either:
  - **stacked**: an already-visible candidate in an earlier depth group covers it on the sheet
    (`_covers`); or
  - **behind material**: `blocked(candidate.place)`.
- Otherwise it is visible.

Only earlier *visible* candidates count for stacking, so a hidden one hides nothing.

**Stacked: `_sheet_shape` and `_covers`.** `_sheet_shape` flattens a feature onto the sheet,
removing its component along the view:
- a corner is a point;
- an edge is a line, or a point if it runs straight along the view;
- a face seen edge-on is a line whose run is normal × view;
- anything else is nothing, and neither covers nor is covered.

`_covers(front, behind)`:
- a line in front of a line covers it when their sheet directions are parallel (both are under
  the pointer, so parallel is the same line);
- a point in front of a point, when within the tolerance on the sheet;
- a line in front of a point, when the point is within the tolerance of the line;
- a point in front of a line, never: the line shows on both sides of it.

This settles edges stacked exactly along the view from the candidates alone, without asking
whether a grazing line of sight blocks.

**Behind material: `blocked`,** built by the runner's `_sight_blocker`. It asks
`sight_is_blocked` of the clicked timber, then of each other drawn member in the slot's mesh
cache: those in `drawnMembers`, or every member when none are sent. The place and the direction
to the camera are converted into each timber's own space first. A drawing's faded context is not
in `drawnMembers`, so it hides nothing.

**`sight_is_blocked(root, place, toward_camera)`** (`kumiki/drawings/visibility.py`):
1. Crop the line through `place`, in the camera's direction, to the solid
   (`crop_line_to_segments_on_csg`, exact): the stretches of it that lie on the solid.
2. Of each stretch, keep the part toward the camera beyond `NUDGE` (10 µm), so the surface the
   place sits on does not count.
3. Blocked only if the middle of that part is *inside* the solid (`contains_point` and not
   `is_point_on_boundary`). A line of sight along an edge-on face only grazes the surface, so a
   peg's cap seen edge-on, or the front edge of a flank, stays visible.
4. A tree that cannot be cropped (`None`: curved primitives other than cylinders) is "not
   blocked". Unsure means visible.

### 3. The runner uses the result (`_handle_find_csg_at_point`)

- Candidates: visible first, then hidden, each in order; `visible_count` is how many are visible.
- Default choice: while measuring, `_best_matching_candidate` considers only the visible ones.
  Otherwise in a drawing, a plain click with no index takes candidate 0, the first visible one.
  With nothing visible it falls back to the tree walk.
- Returned: each candidate with `hidden: index >= visible_count` and its `path`, and
  `candidateCount = visible_count`, which is what Tab cycles through.

### 4. The viewer

The right-click menu lists every candidate. Hidden rows are `disabled` (greyed) and marked
"hidden" beside their type and path. Tab cycles through `candidateCount` only, so it never
reaches them.

### Cost

One candidate list per hover (a pass over the tree's declared features), plus one
`sight_is_blocked` crop per candidate place for each drawn member. About 60 ms a hover on the
dovetailed sawhorse, against 13 ms for the 3D view's single hit point. Skipping timbers whose
bounding box the line of sight misses would be the first speed-up.
