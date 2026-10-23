# Feature picking

How a hover or a click becomes a picked feature. The features themselves are described in
`featuresystem.md`; where picking sits among measuring, solving and drawing, in `featureflow.md`.

There are two ways to pick:

- **3D view**: the pointer picks on the one timber it is over.
- **Drawing view** (orthographic sheet): the pointer picks from every timber drawn under it, and
  what is hidden behind material is listed but can't be taken.

One rule holds for both: **the slack is in screen pixels**. An edge is picked within 6 px of it on
screen, a corner within 10 px, on either side, whatever the zoom or the angle.

## The words used below

- **Ray**: the line from the camera through the pointer.
- **Hit point**: where the ray first meets a timber's mesh.
- **Slack**: how close the pointer must be to a feature on screen. The viewer turns pixels into a
  world distance at the hit point and sends it as `tolerances` (`face`, `edge`, `point`).
- **Real / non-real**: a real feature is on the timber's surface (a face, an arris). A non-real one
  is a reference that isn't surface: a centerplane, a perfect-timber (PTW) face, a bore's axis.
- **Candidates**: every feature under the pointer, best first. A click takes the first one; Tab
  steps through them; right-click lists them.

## What the viewer sends (`webview/viewer-picking.js`)

On a click, and on a hover once the pointer has settled:

- Raycast the meshes for the hit point and the member it is on (`memberKey`). In a drawing, a ray
  that hits nothing still sends a pick.
- Work out the slack: pixels (`pick-tolerances.js`: 6 to an edge, 10 to a corner) times the world
  size of one pixel at the hit point.
- Send `findCSGAtPoint` with the hit point, the ray, the slack, `space` (`'projected'` in a
  drawing, `'3d'` otherwise), the drawn members, the current CSG path, Ctrl, the end of a
  measurement in hand (if any), and the candidate the hover settled on (if any).

## Entry point: `_handle_find_csg_at_point` (runner)

Click and hover both come here, so a hover always shows what a click would take.

- Turn on the point-test memo for this pick (`point_tests_memo`).
- Read the request once (`_PickAsk`). A missing `space` means 3D.
- In a drawing, with a ray: do a **drawing pick** (`_pick_in_drawing`).
- Otherwise: do a **3D pick** (`_pick_on_member`) on the member that was hit.

## 3D pick: `_pick_on_member`

- Move the hit point and the ray into the timber's own space.
- **Navigate** the CSG tree to the node under the point (`picking.navigate`):
  - a plain click goes straight to the deepest labelled node under the point;
  - Ctrl+click goes one level deeper than the current path per click.
- **Find the candidates** (`find_candidates` → `features_at_point` → `features_near_ray`, shared with
  the drawing pick):
  - Ask the whole tree for features near the hit point (`find_all_features`, below). Edges and
    corners are gathered from 3× further along the face than their slack (`SLANT_REACH`), because
    a face seen at a slant puts a pixel on screen further away along the face.
  - Keep an edge or a corner only if it comes within its slack of the ray, measured across the
    view.
  - Add a non-real plane (centerplane, PTW face) if the line where it crosses the struck face comes
    within the edge slack of the ray.
  - Add non-real lines (a bore's axis) the ray passes within the edge slack of, inside their
    extent (`non_real_features_along_ray`).
  - Drop an edge whose line is not really an edge of the surface there: a flush copy of another
    timber's arris (`_only_creases`).
- **Choose** one (`choose`, below).
- **Highlight** it (`_pick_highlights`, below) and build the reply: the feature, its path, its
  geometry and anchor, the candidate list, and a measurement verdict if a measurement is in hand.

## Drawing pick: `_pick_in_drawing`

- **Gather every member near the ray** (`_drawing_candidates`):
  - Skip a member whose box the ray doesn't come within the slack of.
  - The member that was hit, and any member the ray passes through, is asked at the hit point.
  - A member the ray just misses is asked at the point of its mesh nearest the ray, so an edge is
    picked from outside its silhouette as well as from inside.
- **Find each member's candidates** (`candidates_under_pointer` → `features_near_ray`), in that
  member's own space:
  - The 3D pick's steps, at its point (`find_all_features`, `SLANT_REACH`, plane traces).
  - Non-real lines and non-real planes along the ray (`non_real_features_along_ray`). A plane
    counts when it is seen edge-on, the ray is within the edge slack of it, and the ray crosses the
    part of the plane that lies in the timber (its `FeatureExtent`).
  - Keep an edge or corner only within its slack of the ray, across the view; place it at its own
    point nearest the ray.
  - Drop what the sheet can't measure (`measurable_in_view`): a face seen at an angle is an area,
    not a line. A real face seen edge-on is also dropped when a real edge draws the same line,
    since the edge measures the same. Non-real faces always stay.
- **Order them, nearest the camera first** (`drawing_candidates`): group by depth (a new group
  whenever one is more than the edge slack deeper), and within a group use the feature priority.
- **Split visible from hidden**, in order:
  - a non-real feature is never hidden;
  - a feature is hidden when a nearer visible one draws over it on the sheet
    (`visibility.drawn_over`);
  - or when material lies between it and the camera (`visibility.hidden_at`, below).
- If nothing is visible, take nothing but still list the hidden ones (greyed in the menu).
- **Choose**: the candidate the request names (Tab, a menu row), else the one that best finishes
  the measurement in hand, else the first visible one.
- Do the rest as a 3D pick on the chosen candidate's member, then reply with the whole list.

## Is a place hidden? `visibility.hidden_at`

- For each drawn member, in its own space:
  - Cut the line from the place toward the camera to the inside of the solid
    (`crop_line_to_interior_segments_on_csg`, exact).
  - The place is hidden if any piece of that reaches more than 10 µm toward the camera. A line of
    sight that only runs along a surface is not blocked.
- A solid that can't be cut exactly counts as not blocking: unsure means visible.

## Finding features at a point: `CutCSG.find_all_features` (library)

- Walk the tree and collect every declared feature the point is on, each at its own tolerance
  (`collect_feature_hits`).
- At each node, drop the real ones if the point is not on that node's boundary. Non-real ones
  skip this check.
- Gather faces again at the corner slack, and make **derived edges** from pairs of them and
  **derived points** from edges crossing faces; keep those the point is near.
- Sort by feature priority, and drop derived duplicates of the same geometry.

## Choosing one: `picking.choose`

In order:

- the candidate the request names (Tab, a menu row), wrapping round the visible ones;
- else, while measuring, the visible one that can be measured against the held end, preferring
  the same kind (face to face, edge to edge);
- else, in a drawing, the first visible one;
- else (3D): a derived edge or point under the click, then a declared edge or point, then the face
  navigation landed on.

## Feature priority (`_sort_feature_hits`)

When several features tie on depth, each rule decides only where the ones before it tie:

1. Non-real lines and points first, then real features, then non-real planes. An axis is a
   deliberate snap; a centerplane runs through the whole body, so it comes last.
2. More specific first: point, then edge, then face.
3. Declared before derived.
4. Group rank (`FeatureGroup`): `SHOULDER_PLANE`, `PERFECT`, `ROUGH`, `TENON`, `CROSSING`, then
   `NONE`. A derived feature takes the better rank of its two parents.
5. Author-set priority, lower first.
6. Name, alphabetically.
7. The order they were found in.

## Lighting the pick: `_pick_highlights`

- An edge or axis: its `FeatureExtent` outline (`edge_highlight_segments`). A real edge is cut to
  where the surface creases along it, inside its parent faces' solids and its declared ends; an
  axis in a void keeps its declared ends.
- A non-real plane: its outline on the timber (`non_real_plane_outline`).
- A face: the mesh triangles on it (`extract_highlight_mesh`):
  - skip triangles outside the node's box;
  - keep a triangle whose centre is on the feature's plane and on the node's boundary.
- The selected node's own triangles too, drawn dimmer.

## Entry point: `_handle_find_csg_by_path` (runner)

Lights a node named by a path (the tree panel, a saved selection), with no point involved.

- Walk the path down the tree (`resolve_csg_at_path`): each step is a label, `label#n` for the
  n-th sibling with that label.
- Light the node's triangles, or the named feature's.

## Speed

A drawing pick is around 5–15 ms on the cute frame and tinyhouse. What keeps it there:

- the point-test memo: each node answers each point question once per pick;
- members are skipped by box before anything else;
- feature extents, solid bounds and declared features are worked out once per tree and kept.
