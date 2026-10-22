# Feature solving

How kumiki decides which features of a timber must be dimensioned, whether a set of
measurements pins them down, and how it picks dimensions automatically until they are.

See `featuresystem.md` for the features themselves, and `.claude/plans/featuresolving-plan.md` for the plan and
the decisions made along the way.

## The idea in one paragraph

The geometry is already known exactly; nothing is solved numerically. The question is only whether
the drawing *says* enough to build it. So every surface gets a few unknowns ("how much could this
face move or tilt"), every feature and every measurement becomes rows over those unknowns, and
"solved" is a rank test: a feature is solved when its rows add nothing to what the measurements
already pin down.

## The words used below

- **Carrier**: the plane, line, point or cylinder barrel a feature lies on. Features share carriers:
  an arris lies on two face planes.
- **Unknowns**: small changes a carrier could make. A plane: offset and two tilts (3). A line: two
  shifts and two turns (4). A point: x, y, z (3). A barrel: its radius, plus its axis line.
- **Row**: how one quantity (a feature's position, a measurement's value) changes with the
  unknowns, at the design. A plain list of numbers.
- **Known rows**: what is pinned down: the fixed datum, assumptions, and every measurement.
- **Remaining DOFs** of a feature: how many independent ways it could still move without changing
  anything known.

## Entry point: `required_features(cut_timber)` (`csg/required_features.py`)

Which features of one timber need solving, each with a reason.

- Walk every node of the drawn tree (the rough body with its perfect planes, plus the cuts).
- For each declared feature:
  - skip rough-stock features (not measured by default) unless asked to include them;
  - skip one marked `NEVER_MARK`; take one marked `ALWAYS_MARK`;
  - take every non-real feature (an axis, a centerplane);
  - take a flat face if some of it, with area, is on the finished surface (its `FeatureExtent` is
    not empty);
  - take every curved face;
  - take an edge or point only if it is an extra the author added. A primitive's own edges and
    corners are solved through its faces.

`planning_features` narrows this for a plan drawing: the perfect timber's own faces and the joints'
shoulder planes.

**Why a face can be skipped.** The finished piece is `timber − cuts`. A face needs no dimension when
none of it is on that finished surface: a tenon's back face buried in the wood, a mortise cutter's
top face out in the air, a relief cutter's face swallowed by a union.

## Entry point: `carrier_map(tree)` / `Solve(cut_timbers)` (`csg/feature_solving.py`)

The unknowns for a solve.

- Collect every primitive's carriers in each timber's drawn tree.
- Merge planes that coincide (facing either way) within a timber into one carrier, so a face flush
  with another face needs no dimension of its own. Never merge across timbers.
- `Solve` keeps the merged carriers and each feature's rows for the length of one solve.

## Entry point: `feature_dof_rows(recipe, carriers)` (`csg/solve_recipe.py`)

A feature's own rows: what would move it.

- Each feature has a **recipe**: the carriers it is made from (`CSGFeature.solve_recipe`).
- A feature on one carrier: that carrier's unknowns, one row each.
- A centerplane (a midplane between two faces): its motion at three points of it.
- A derived edge (two planes meeting): how its line moves across itself at two points, from how
  its parent planes move. A derived corner (three planes): its motion along x, y and z.

So a derived feature adds no unknowns. Measuring to it is measuring its parents.

## Entry point: `measure_row(measurement, carriers)` (`csg/feature_solving.py`)

A measurement's row: how its value would change.

- **A distance** (`SolveDistance`: two features, a point on each, and the direction it is read
  along):
  - For each end, the smallest motion that keeps its point on its moved feature, read along the
    direction (`motion_along`).
  - The row is the far end's motion minus the near end's.
- **An angle** (`SolveAngle`):
  - Each feature's direction (a plane's normal, a line's direction) and how it turns.
  - On a sheet, each one as the line it draws on the sheet.
  - The row is how the cosine of the angle between them changes.

Because only the rank matters, each measurement is linearised at the design: a distance from a
known point pins the other point along the line between them and leaves it free across it.

## Entry point: `solve_measurement(measure, cut_timbers, view)` (`drawings/measure_solving.py`)

Turns a drawing's `Measure` into the solver's `SolveDistance` / `SolveAngle`.

- An angle: the two features, and the view's look direction if it is on a sheet.
- A distance:
  - Find each feature's span on its cut timber (`feature_span`).
  - On a sheet, flatten each to what it draws as (a face seen edge-on is a line, a line seen end-on
    is a point).
  - Find where the dimension attaches at each end (`distance_anchors`), and carry those points back
    onto the 3D features.
  - Read it along the gap between them, or along the sheet's right or up for a horizontal or
    vertical dimension.
- `DrawingSolve.row` keeps each measurement's row (or the reason it has none) for the solve.

## Entry point: `remaining(known, target)` (`csg/dof_solver.py`)

The rank test everything else uses.

- Stack the known rows into a matrix and find the directions they span (an SVD).
- Take those directions out of the target's rows.
- Whatever is left, above a small relative tolerance, is the target's remaining DOFs: how many,
  and which motions are still free.

`remaining_dofs` and `solve_report` (`csg/feature_solving.py`) run this per target and for all
targets at once.

## Entry points: assumptions (`csg/assumptions.py`, `drawings/auto_dimensioning.py`)

What a drawing says without a dimension. Each assumption is rows added to the known rows, with a
reason.

- **`square_assumptions`**: what is square stays square.
  - Group the features' directions into sets of three square axes.
  - Within a set, chain the features along each axis as parallel, and hold one feature per axis
    square to one per other axis.
- **`sheet_axis_assumptions`**: a feature drawn along the sheet's right or up keeps that direction.
  Where it sits along the axis stays unknown.
- **`coincidence_assumptions`**: what a view shows lined up is known.
  - In each view, find features that draw on one line, a point on a line, or two points on one
    spot.
  - Each such pair adds the row a zero-length dimension would.
  - Only features the view can see count.

## Entry point: `visible_by_view(anchors, views, drawn)` (`drawings/visibility.py`)

Which features each view can see some of, so nothing is dimensioned in a view that hides it.

- Only a face seen edge-on, or a line, is asked about; a face seen at an angle is an area.
- Non-real features are never hidden.
- For the rest, cut the plane holding the feature's lines of sight by every drawn solid, exactly,
  and see if any of the feature is left uncovered.

## Entry point: `sheet_candidates(visible, views, solve)` (`drawings/auto_dimensioning.py`)

Every dimension a view could draw.

- For each view, take the features it can see that draw as a line lying in the sheet (not slanting
  into it, which would be foreshortened) or as a point.
- For each pair of them: two parallel lines, or a point and a line, give a perpendicular
  dimension with that length.
- Skip pairs drawn on top of each other: that's a coincidence assumption, not a dimension.
- A candidate's row is worked out only when the picker asks for it.

## Entry point: `auto_dimension(candidates, targets, known_rows, solve, policy)`

Picks dimensions one at a time until every target is solved.

- Take the targets' rows, with everything already known projected out.
- Repeat while any target is unsolved:
  - Sort the remaining candidates by the policy's preferences, compared one after another (by
    default `PREFERENCE_ORDER`: angles first, angles from the timber, fewer face ends, from a reference
    face, perfect faces over rough ones, declared over derived, from something already solved, then
    shortest).
  - Walk down that order and take the first candidate that **helps**: its row adds something new,
    and all of what it adds is still unsolved. It must also pass the policy's rules; if no helpful
    candidate passes them, take the first helpful one anyway and say so.
  - Remove its direction from every target's rows, and add it to what is known.
- Stop when nothing is unsolved, or no candidate helps. Warn about any target left unsolved (often
  a feature no view shows, like a blind mortise's bottom).

## Entry point: `faces_to_edges(result, cut_timbers, faces, views, carriers)` (`drawings/auto_dimensioning.py`)

After picking, moves each face end of a dimension onto one of the face's edges, since a viewer sees
edges as drawn lines and a face only edge-on. Solving works with faces; only what is drawn changes.

- Before solving, `without_edges_on_faces` drops, per view, each edge that lies on one of the faces it
  meets, where that face is seen edge-on: the face's line is the edge's, so measuring the face measures
  it. Edges seen end-on draw as points and stay (a slanted face needs one to be measured from).
- For each face end, seen edge-on in the dimension's view:
  - take the boundary segment of the face's region that runs along its drawn line, nearest the camera;
  - find another face of `faces` whose region has a boundary along the same stretch (they meet at a
    crease there; a face whose plane only passes through is a seam, and is skipped), trying the best
    group first;
  - use the declared edge that is the meet of the two faces (e.g. `rptw.front_left`), else derive it,
    whatever their groups;
  - record the shared stretch as the edge's extent, so it is never cropped for.
- The dimension keeps its value. Its row is the same but for the tilt columns, which the sheet's
  assumptions fix, so the solve is unchanged. A move the solver can't write a row for isn't made.
- Not checked: whether another timber hides the chosen edge while some of the face shows.

## The whole pipeline (as in `patterns/structures/my_cute_frame_drawing_test.py`)

- Set up a `DrawingSolve` over the frame's cut timbers.
- **Datum**: fix one timber's reference faces and its bottom end, as known rows.
- **Targets**: the planning features of every timber.
- **Assumptions**: square, along the sheet axes, and lined up in each view.
- **Anchors**: the targets, and the edges of faces some view draws slanted (`derived_edge_anchors`).
- **Visible**: what each view can see of the anchors, less edges lying on a face seen edge-on.
- **Candidates**: every dimension the views could draw.
- **Pick**: `auto_dimension`.
- **Onto edges**: `faces_to_edges`, then put the picks on the drawing, view by view.

## Worked example: a tenon

A square tenon on the end of a timber, with its directions square to the timber:

- Planes left after merging: 4 cheeks, the tip, the shoulder (the back face is buried in the wood;
  the timber faces are the datum). That is 6 offsets to solve.
- Dimensions that solve it:
  - shoulder from the timber end: the shoulder;
  - tenon thickness, plus one cheek from a reference face: both thickness cheeks. Neither alone
    solves anything; the rank sees the pair;
  - tenon width, plus one edge cheek from the other reference face: the other two cheeks;
  - tenon length from the shoulder: the tip.
- Leave out the length and the tip reports 1 remaining DOF: the picker's cue to add it.
- A barefaced tenon has a cheek flush with a timber face. That cheek merges with the known face,
  so it needs no dimension, and the count drops to 5.

## Known limits

- **Grazing contact**: a face that touches the finished surface only along a line (a cutter plane
  along an arris) may be reported as required. Worst case, one redundant dimension.
- **Singular layouts**: the rank test can report a freedom that isn't really there (two collinear
  distances to one point). Worst case, one redundant dimension.
- **Zero-valued relations**: "parallel" or "coincident" can't be measured as 0; they come in as
  assumptions instead.
- **Curved surfaces** are solved only by measuring them directly (a radius, a diameter).
- **Centerplanes** are solved for but not yet dimensioned to on a drawing.
