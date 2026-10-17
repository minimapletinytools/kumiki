# The Feature Picking System

How a hover or click becomes a picked feature. The CSG feature system it picks from is in
`featuresystem.md`.

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

### 1. Collect the candidates: `candidates_under_pointer` (`kumiki/viewer/picking.py`)

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

**`sight_is_blocked(root, place, toward_camera)`** (`kumiki/viewer/visibility.py`):
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
  With nothing visible, nothing is taken: the answer is empty but for the (hidden) candidates.
- A named index (Tab, a menu row) wraps round the visible candidates only, so it is never a
  hidden one.
- Returned: each candidate with `hidden: index >= visible_count` and its `path`, and
  `candidateCount = visible_count`, which is what Tab cycles through.

### 4. The viewer

The right-click menu lists every candidate. Hidden rows are `disabled`, greyed, and marked
"hidden" beside their type and path; hovering one does not preview it. Tab cycles through
`candidateCount` only, so it never reaches them.

### Cost

One candidate list per hover (a pass over the tree's declared features), plus one
`sight_is_blocked` crop per candidate place for each drawn member. About 60 ms a hover on the
dovetailed sawhorse, against 13 ms for the 3D view's single hit point. Skipping timbers whose
bounding box the line of sight misses would be the first speed-up.
