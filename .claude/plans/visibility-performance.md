# Visibility check performance (drawing generator)

Notes from profiling, 2026-10-18, to revisit. `visible_by_view` (kumiki/drawings/visibility.py)
decides, for each drawing view, which anchors the generator may measure to.

## Where it stands

Rough cute frame (`patterns/structures/my_cute_frame_drawing_test.py`), all five drawings:
**379 ms** over 400 anchor/view checks, after the strip seed (`5ff5272e`) and planar_region's
bounding-box skip (`e7c0dc38`). It was ~1.2 s when it went in (#106).

Only one kind of check costs anything:

| Anchor kind, in that view | Checks | Time |
|---|---|---|
| Face seen edge-on (drawn as a line) | 198 | 375 ms |
| Face at an angle (an area; skipped) | 90 | 1 ms |
| Not real (axes, centerplanes; never hidden) | 80 | 0 ms |
| Other (points; skipped) | 32 | 0 ms |

Steps for one edge-on face:

| Step | Calls | Time | What it does |
|---|---|---|---|
| 1. `face_on_surface` | 198 | 164 ms | Cuts the face's primitive, then its whole timber tree, by the face's plane: which part of the face is on the finished surface. |
| 2. `material_crossing` | 264 | 165 ms | Cuts every drawn timber's whole tree by the same plane, within the strip the face spans: what crosses the plane. |
| 3. `shadow` | 264 | 4 ms | Sweeps that away from the camera. |
| 4. `subtract` | 198 | 29 ms | Face minus the shadows near it. |

Steps 1 and 2 are both "cut a whole CSG tree by a plane": 87 % of the time. That cut walks every
node and, at each subtraction, clips by the cutter's section; a peg hole is a 64-sided polygon.

## Waste to remove (same answers)

1. **The same cut twice.** For the face's own timber, steps 1 and 2 cut the same tree by the same
   plane; only the seed differs (the face's region, the strip). In a shop drawing the own timber is
   the only one drawn, so every face there does it twice. Cut once over the strip, read both off it.
   About a third of the time, or more.
2. **Opposite views repeat step 1.** A face edge-on from the front is edge-on from the back, and its
   own surface region does not depend on which way you look. Keep it per face across views.
3. **Coplanar faces repeat step 2.** Faces on one plane (a timber face and a joint face flush with it)
   each cut the occluders afresh. Cache by plane, then clip to each face's strip.

Estimated together: 379 ms to roughly 100-150 ms.

## Bigger lever: the scribe reliefs

Rough stock more than doubles every timber's tree (cute frame: 52 to 124 CSG nodes, 360 to 1012
declared features) because each joint's scribe relief embeds the other timber's whole rough body
and its cuts, the rough-minus-perfect fringe, and a copy of the perfect timber. Everything that
walks or cuts the tree scales with it: this check, `face_reaches_surface`, picking's feature
search, triangulation, centerline cropping. Bounding each relief to the joint's neighbourhood (say,
intersecting it with a box around the joint) would shrink the trees and speed all of these up.

## Elsewhere in the load (rough cute frame, ~0.8 s + ~0.15 s geometry)

- `required_features` (~200 ms): nearly all `face_reaches_surface`, the same kind of plane cut.
- `auto_dimension`: every candidate's row is built anyway, because the last step finds nothing
  helps (a bore's radius, a hidden mortise bottom) and so scans them all. The span cache on the
  CarrierMap (feature_solving `_span`) is a stopgap; feature_solving should hold per-solve caches in
  a solve object instead.
- Centerline outlines (~80 ms at geometry build): `plane_section` of each timber's tree. Slicing the
  already-triangulated mesh with the plane would take a few ms and match what is drawn.
