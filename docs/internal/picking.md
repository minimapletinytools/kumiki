# The Feature Picking System

How a hover or click becomes a picked feature. The CSG feature system it picks from is in
`featuresystem.md`; where picking sits among measuring, solving and drawing, in `featureflow.md`.

Feature picking differes if we are in the 3d view or if we are in a 2d orthographic drawing view. 

## Feature priority

Several features can be under the pointer at once. `_sort_feature_hits` in `cutcsg.py` orders
them, and a click takes the first. Each rule decides only where the ones before it tie:

1. **Non-real lines and points, then real features, then non-real planes.** A bore's axis is a
   deliberate snap, so the surface it lies on does not steal the click. A non-real plane (a
   centerplane, or a perfect face inside rough stock) runs through the whole body, so it would
   take every click on its line; it comes last.
2. **The more specific kind.** Point, then edge, then face (flat or curved). An edge beats the two
   faces that formed it, and a corner beats its edges.
3. **Declared before derived.** A feature something declared beats one derived from a pair of
   faces.
4. **Group rank** (`FeatureGroup`, lower is better): `SHOULDER_PLANE`, `PERFECT`, `ROUGH`, `TENON`,
   `CROSSING`, then `NONE`. A derived feature takes the better rank of its two parents.
5. **Author-set priority** (`FeatureProperties.priority`, lower wins). Default features carry a high
   value, so anything a joint names beats the prism's anonymous defaults.
6. **Name**, alphabetically.
7. **The order they were found in**, as the last tie-break.

In a drawing's view the candidates come nearest the viewer first, and this order breaks ties at
one depth (`order_along_ray`; see 2D below).

In Kigumi, while the pointer is over a feature:

- **Tab** steps to the next feature under the pointer, wrapping round. The highlight shows what a
  click would now take. Moving the pointer forgets the choice.
- **Right-click** (without dragging) lists every feature under the pointer, best first, with its
  kind; choosing a row selects that feature. With only one feature there, right-click opens the
  member menu instead.

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

1. **At the surface:** `root.find_all_features(local_pt)`, the features where the ray first hit a
   surface. In a drawing every drawn member near the ray is asked at that one point, so a corner
   flush with it on another member is found too. Nothing deeper is offered: it is behind the
   surface. An edge on a silhouette is found from the side its own surface is on.
2. *(No longer done: the whole ray was swept for features at any depth. See the note on
   `real_features_along_ray`.)*
3. **Features in voids:** `merge_ray_hits` adds non-real ones, like a bore's axis, at their
   nearest approach to the ray.
4. **Exact places for edges and corners:** `_nearest_on`. A corner is placed at itself; an edge at
   the point of its line nearest the pointer's ray. The surface point can be a pixel off it, and
   testing visibility from there gets it wrong.
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

**Behind material: `blocked`,** `picking.sight_blocker` over occluders the runner's `_sight_blocker`
gathers: the clicked timber, then each other drawn member in the slot's mesh cache -- those in
`drawnMembers`, or every member when none are sent. It is `visibility.hidden_at` per place, which
asks `sight_is_blocked` of each, the place and the direction to the camera converted into each
timber's own space first. A drawing's faded context is not in `drawnMembers`, so it hides nothing.

**`sight_is_blocked(root, place, toward_camera)`** (`kumiki/drawings/visibility.py`):
1. Crop the line through `place`, in the camera's direction, to the solid's *inside*
   (`crop_line_to_interior_segments_on_csg`, exact): the stretches of it strictly within the solid,
   not on its surface.
2. Blocked if any of them reaches more than `NUDGE` (10 µm) toward the camera. A line of sight along
   an edge-on face only runs along the surface, so a peg's cap seen edge-on, or the front edge of a
   flank, stays visible -- and one that runs along a surface and then into material is blocked.
   (It judged each stretch by its middle before, which missed the second.)
3. A tree that cannot be cropped (`None`: curved primitives other than cylinders) is "not
   blocked". Unsure means visible.

A drawing's generator asks the same of a whole feature rather than a place: see
`nearest_visible_depth` in the same module, which decides a face seen edge-on, or a line lying
along the sheet, in the one plane holding all its lines of sight, cut exactly by each solid.

### 3. Choosing one (`picking.choose`)

`_handle_find_csg_at_point` runs three steps of `picking.py` -- `navigate`, `find_candidates`,
`choose` -- and builds its reply from the `Pick` that comes back.

- Candidates: visible first, then hidden, each in order; `visible_count` is how many are visible.
- Default choice: while measuring, `best_matching_candidate` considers only the visible ones.
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
