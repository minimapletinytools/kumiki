# Picking on a sheet: marks, occlusion and aliases

What a pointer in a drawing's view offers, stated as one rule instead of a set of special cases.
Not built yet.

## The problem

What a sheet's pointer hides grew one case at a time:

- `picking.measurable_in_view` drops a face seen edge-on when a straight edge lies in its plane.
- `visibility.drawn_over` hides a line behind a nearer line, and a point behind a nearer point or
  line, each its own case.
- An edge seen end-on is not handled. It draws as a point on its near vertex, is offered beside
  it, and is sometimes the pick.

Two questions are mixed in these:

- **Occlusion**: is what is drawn here behind something nearer? A real "hidden", decided by depth
  and by material.
- **Aliasing**: do several features draw as the same mark? An edge-on face and the edge along it
  draw one line; an end-on edge and its vertex draw one point. Neither is behind the other: they
  are two names for one drawn thing.

## The rule

On a sheet the reader picks marks (points and lines), not 3D features.

1. **Project.** Each candidate becomes what it draws as (`sheet_shape`): a point, a line, or an
   area. An area is not pickable.
2. **Group by mark.** Candidates under the pointer that draw the same point, or the same line, are
   one group.
3. **Occlusion, within a group.** The nearest depth is what is drawn there. Anything deeper on the
   same mark is hidden, and so is anything material hides (`visibility.hidden_at`).
4. **Aliasing, among the nearest.** The feature that draws as itself represents the mark: one whose
   3D dimension is the mark's. A vertex is a point, an end-on edge only collapses to one; an edge
   is a line, an edge-on face only collapses to one. The collapsed ones are aliases: not hidden,
   just not offered as picks of their own.

| Case | Under the rule |
|---|---|
| Edge-on face with an edge in its plane (today: special case) | The face collapses to the edge's line; the edge represents it |
| End-on edge on its vertex (today: not handled) | The vertex represents the point; the edge's far vertex is deeper on it, so occluded |
| Cylinder cap edge-on (its rim names no straight line) | Alone on its line: represents itself |
| Bore axis end-on | Alone on its point: represents itself |

## Decisions

- **Aliases are left out of the right-click menu.** On a sheet an edge-on face and its edge measure
  the same; listing both is noise. The menu shows what is drawn, and what is behind it greyed.
- **Material occlusion stays separate** (`hidden_at`), as it is now.
- **The generator's per-feature question stays per feature.** It keeps stacked lines on purpose:
  two timbers' tops in line are dimensioned at the one line both draw. It could use the same
  grouping to stop offering a face and its edge as two dimension candidates; that is a separate
  decision.

## Where it goes

One function in `kumiki/drawings/visibility.py` that sorts a pointer's candidates into drawn,
aliased and hidden. `measurable_in_view` and `drawn_over` fold into it, and both
`picking.split_hidden` and the multi-member drawing pick (`picking.drawing_candidates`, #125) call
it.

## Checking it

It changes what the pointer offers, so: the pick probes (full replies over a grid of drawing
picks, before and after), with every difference explained by the rule, and a pass in the app over
the cute frame's plan and shop drawings, at joints and on silhouettes.
