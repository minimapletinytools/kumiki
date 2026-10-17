# Picking in a drawing's view: hidden features, fewer faces, equivalent measurements (2026-10-16)

What a pointer in a drawing's orthographic view can select and measure. This follows from:
- **Done (6f05e679 and the commit before it):**
  - every feature on the boundary along the pointer's ray is a candidate;
  - candidates are ordered nearest first;
  - the chosen candidate is settled once.
- **Done (9b74db91):** selection and measuring are per view.

## 1. Hidden features

**Problem.** Candidates now come from the whole ray, so features nobody can see are offered:
- the far dovetail's `dovetail_wide_face`, behind the beam;
- the back edges of a flank seen edge-on, stacked behind its front edge.

**Earlier work.** PR #82 (branch `visibility`, commits a47f93e8 and 62ffbded, 2026-10-11) built
an exact orthographic visibility test in `kumiki/viewer/visibility.py`:
- **Point:** hidden if its line of sight to the camera passes through material.
- **Line:** the plane of sight is cut by each solid in the way; that region's camera side,
  projected onto the line, is the hidden part. The result is exact stretches.
- **Face seen edge-on:** seen if any of its edges is.
- **Nudge:** each is first moved a few micrometres off its own timber, away from the camera. So
  only the front one of stacked features is seen (a box's far arris is hidden by the near one).
- **Cylinders** are exact. Any other curved primitive gives "visible, not exact".
- On that branch it was used only to refuse measuring ("hidden"), not selection.

The PR is closed unmerged: `main` has rewritten picking since. Port the core (the cropping, the
nudge, the cylinder stations) rather than merging.

**The question for selection is narrower: is the candidate visible *under the pointer*?**
- Each candidate was found at a place on the ray. It is hidden if its own line of sight, from that
  place nudged back toward the camera side, passes through material or along a surface first.
- Its own line of sight, not the pointer's ray. Candidates snap from a few pixels away, and the
  pointer's ray can pass through a socket's opening right beside a flank whose back edge is
  hidden.
- This covers faces seen at an angle too (the far socket floor), which "visible anywhere" could
  not answer.

**Behaviour:**
- Click and Tab skip hidden candidates.
- The right-click menu shows them greyed out and unselectable. Greyed rather than removed: a wrong
  call stays visible.
- Done on hover and click alike, so what is lit is what a click takes. If too slow, click only.
- The measuring check uses the same test, and the "hidden" refusal comes back.

**Occluders:**
- In a drawing: its drawn members, not its faded context.
- The perspective preview view uses the same test, since a line of sight is a line of sight.
- The 3D view is unchanged.

**Risks:**
1. **Ties and grazing.** A line of sight exactly along an edge-on face lies on the boundary, not
   in the interior; whether that blocks decides the stacked-edges case. Which way the nudge goes
   matters at outlines and corners. Wrong answers hide something pickable, so "unsure" means
   visible, and greyed, not removed.
2. **Cost.** A drawing hover is ~54 ms now. Visibility adds about one CSG crop per distinct
   candidate place per drawn member (sawhorse: ~10 places × 5 timbers). Share tests between places
   at the same position; measure before shipping hover.
3. Curved primitives other than cylinders stay "unknown" (visible).
4. Measuring what is hidden on purpose is X-ray (`measuring-and-drawing-todos.md` §7). Greyed
   candidates leave room for a toggle that makes them selectable again.

## 2. Fewer faces in a drawing's view

A 2D view measures points and lines, so a face only measures as a line, when it is seen edge-on.
- **Seen at any other angle** it is an area: it admits nothing to measure, and offering it only
  crowds the menu and the Tab cycle.
- **Seen edge-on** it nearly always projects onto the same line as one of its straight edges
  (declared, or derived where it meets a timber face), and measuring that edge is the same
  measurement (§3).

**Rule.** In a drawing's view a face is a candidate only if:
1. it is seen edge-on (its normal square to the view), and
2. no straight edge lying in its plane is a candidate on the same line under the pointer.

**What survives:**
- a cylinder's cap seen edge-on: its rim is a circle, not a straight edge, so the cap is the only
  thing naming that line;
- any face whose bounding edges are curved, or missing at that spot.

The 3D view keeps every face.

**Risks:**
- A face reference survives some edits an edge reference does not (a chamfer replaces an arris but
  keeps both faces). §3 is the remedy.
- Selecting a face just to inspect it ("copy for ai") is no longer possible in a drawing; the 3D
  view and the layers tree still offer it.

Do this before §1: it removes candidates, so it also cuts what visibility has to test.

## 3. Equivalent measurements

In a view, a distance between two features constrains one degree of freedom: the separation of
the two carriers it involves along the measuring direction. So:
- measuring two parallel faces, both perpendicular to the view, is the same measurement as
  measuring any edge of one to any edge of the other;
- measuring an edge is the same as measuring its edge-on face: the edge's other plane faces the
  view, and moving it moves the edge only along the line of sight, which a projection cannot see.

The machinery exists:
- features name their carriers (`solve_recipe`, `csg/carriers.py`);
- `drawings/auto_dimensioning.measure_row` turns a measurement into rows over the carriers'
  unknowns in a view.

So equivalence can be **derived**, not stored: two measurements in one view are equivalent when
their rows agree.

**Keep storing what was picked.** The two features are what is drawn and where its anchors sit,
and a named feature is what survives edits by name. Use the derived rows to:
- say "already measured as …" when a new measurement adds no row, offering to replace or keep;
- let auto dimensioning count a hand-made measurement as covering its DOF (it partly does already);
- later, re-anchor a measurement whose picked edge disappeared to another representative with the
  same rows.

Storing carriers instead would lose what the user picked and drew against, and tie saved files to
the solver's internal representation. Not worth it.

## Order

1. §2, face filtering (small, cuts the candidate count).
2. §1, hidden features (port from PR #82, under-pointer test, greyed in the menu, measuring
   refusal).
3. §3, "already measured" from measure_row (after using §1–2 for a while).
