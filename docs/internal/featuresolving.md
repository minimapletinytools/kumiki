# Feature solving

Design notes and plan for deciding which features of a cut timber must be solved, and for checking whether a set of measurements solves them. This is the basis for an automatic drawing generator: keep adding measurements until every required feature is fully determined.

See `featuresystem.md` for the CSG feature system this builds on.

# Goal

Two questions:

1. **What must be solved:** which features of a cut timber actually need to be determined.
2. **What is still open:** given the measurements so far, how many degrees of freedom (DOFs) each required feature has left.

The geometry is always fixed by the design. Nothing is ever solved numerically; the only question is whether the drawing's measurements pin the geometry down. The unit of work is one timber, with all its cuts measured from that timber's reference faces.

# The model: rows and rank

Every feature and every measurement becomes rows of one matrix, and "solved" is a rank test. No dependency graph between faces, edges and vertices is needed; redundancy (4 corners solve a face, 6 faces solve all corners) falls out of the rank.

## Unknowns

Each distinct geometric entity on the timber gets a few unknowns:

| Entity | Unknowns |
| :--- | :--- |
| Plane (a face) | 3: normal (2) + offset (1) |
| Line (an edge, an axis) | 4: direction (2) + position (2) |
| Point (a corner) | 3 |
| Cylinder | axis (4) + radius (1) |
| Arc | centre, radius, sweep |

**Why a normal is 2, not 3.** A normal is a unit vector, so it lives on a sphere, which is 2 dimensional. Changing its length doesn't change the plane. Near the design, a normal can only tilt in the two directions perpendicular to itself.

**Why a line is 4.** A direction is a unit vector (2, same argument as a normal). Sliding the line along itself doesn't change it, so its position is only the 2 coordinates of where it crosses the plane perpendicular to its direction.

## Derived features

Edges and corners that are intersections of planes (a prism's own arrises, and derived features such as shoulder × arris) add no unknowns of their own. Their rows are the chain rule through their parent planes: moving a parent plane moves the edge by a known amount, so a derived edge's rows have entries only in its parents' columns.

This also covers measuring the derived feature directly. A measurement to a derived corner becomes a row over the parent planes' unknowns, so it can solve (part of) those planes. A derived feature is solved exactly when its parents' relevant unknowns are.

## Rows, known space, remaining DOFs

A feature is the set of rows that locate it: its entity's unknowns, or for a derived feature the chain-rule rows through its parents.

A measurement adds rows to the *known space* R. R starts with:

- the timber's reference faces (fully known, the datum)
- drafting conventions (see open questions)
- then every measurement on the drawing.

For a required feature f with rows J_f:

```
remaining(f) = rank([R; J_f]) - rank(R)
```

f is solved when that is 0. The same formula over all required features at once gives the total the drawing generator must bring to 0. A greedy generator then picks, from candidate measurements, the one that lowers the total most, preferring conventional ones (from a reference face, perpendicular).

**Cost.** A timber with a few joints has roughly 20–60 unknowns. Keeping R as an incrementally reduced basis makes each added measurement a small update, exact with sympy rationals to match kumiki.

**Caveat.** Rank is a sufficient test: full rank guarantees the geometry is locally pinned down. In rare singular layouts (two collinear distances to one point) it can report a freedom that isn't really there. The worst case is one redundant dimension on the drawing.

# Measurements as rows

Some measurements are not linear in the unknowns (a point to point distance has a square root in it), but only the rank matters, and the rank is taken at the fixed design geometry. So each measurement contributes its derivative at the design: a plain row of numbers.

Intuition: take a distance R from a known point p to a point q. On its own, "|q − p| = R" allows q anywhere on a sphere, which is not linear. But q's design position is fixed, and all we ask is which small motions of q the measurement forbids. At the design, the sphere is locally its tangent plane: the measurement pins q along the direction p→q and leaves the two tangent directions free. That is one linear row, `u · dq` with `u` the unit vector from p to q.

| Measurement | Rows | Row touches |
| :--- | :--- | :--- |
| Perpendicular distance, plane to parallel plane | 1 | both offsets |
| Perpendicular distance, point to plane | 1 | the point, the plane's offset and normal |
| Point to point distance (diagonals too) | 1 | both points, along the unit vector between them: `u · (dp − dq)` |
| Angle between two planes | 1 | both normals |
| Angle between an edge and a plane or edge | 1 | the edge's direction and the other normal or direction |
| Radius or diameter | 1 | the radius unknown only |
| Parallel (explicit) | 2 | both normals / directions |
| Coincident point (explicit) | 3 | both points |
| Coplanar / flush (explicit) | 3 | both planes |

**Angles.** An angle measurement is one more row, over the normals (or edge directions) it relates. It does nothing to offsets. Normals and directions are unknowns like any other, so "is this face's tilt pinned down" is the same rank question as "is its position pinned down".

**Linearization traps.** An angle of 0 (parallel) or a distance of 0 (coincident points) has a zero or undefined derivative at the design, so as a single row it solves nothing. These relations must be entered as their own explicit constraints, with the row counts in the table above, not as a measurement of 0.

**Curves are measured directly.** Only an explicit radius, diameter or arc measurement puts a row on a curve's radius or sweep. No other measurement touches those unknowns, which encodes the rule that a curved surface is solved only by measuring it.

# What must be solved

Every kumiki operation removes material from the parent timber, so the final solid is always

```
S = timber - (cut_1 ∪ cut_2 ∪ ...)
```

A feature's *relative interior* is its interior within its own dimension: a face without its edges, an edge without its endpoints; a point is its own relative interior.

**Rule.** A feature is hidden, and needs no solving, iff no point of its relative interior lies on the boundary ∂S of the final solid. Equivalently: every point of the relative interior has a small ball around it that lies entirely inside S or entirely outside S.

Boundary points of the feature don't need to be considered: if an edge or corner of a feature is still on ∂S, it lies on some other feature that is on the surface, and gets solved through that one.

**Grazing contact.** The rule is conservative. A feature whose relative interior touches ∂S only on a set of zero measure in its own dimension (a cutter face whose plane passes exactly through a timber arris without removing anything) is flagged as required even though it isn't: the arris is already solved by the two timber faces. The exact version is "required iff ∂S contains a nonempty subset of the relative interior that is open relative to the feature" (a patch with area for a face, a stretch with length for an edge). Start with the simple rule and treat grazing as a known over-report.

**Required but already known.** A feature can be required and still need no measurement, when it coincides with a plane that is already known or solved (a lap cutter's side flush with the timber's side). Planes that coincide are merged into one entity before the rank test.

## Examples

"How it enters" is the primitive's path into the timber's CSG. Two subtractions cancel, so the parity column gives the net effect, which kumiki calls `CSGParity`: additive (its inside is material) or subtractive (its inside is removed).

| Case | Example | How it enters | Parity | Why the face is or isn't on the finished surface | Required |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Buried | back face of the tenon prism | tenon prism is subtracted from the waste (shoulder half-space − tenon), and the waste is subtracted from the timber | additive | the prism runs back into the timber past the shoulder, so its back face sits inside wood that is still there | nothing |
| In the air | top face of a mortise cutter started above the timber face | cutter is subtracted from the timber | subtractive | the cutter is oversized on purpose; that face is outside the timber | nothing from that face; the cutter's walls and bottom are required |
| Swallowed by a union | a relief cutter's face lying inside the tenon waste | relief cutter is unioned with the waste, then subtracted | subtractive | inside the union, in removed space | nothing |
| Flush | a lap cutter's side coplanar with the timber's side | cutter is subtracted from the timber | subtractive | it lies on a surface that already exists | one merged plane: the timber face, already known |
| Partly hidden | a mortise wall pierced by a peg hole | mortise cutter and peg cylinder are both subtracted | subtractive | most of the wall survives; the peg hole removes a patch | the whole plane |
| Face gone, corners kept | the tenon's back face exactly on the shoulder plane | as Buried, with no extension past the shoulder | additive | its relative interior is inside the wood; its corners are on the surface but belong to the cheeks and shoulder | nothing (corners solved through cheeks × shoulder) |
| Line or point contact only | a cutter plane grazing exactly along a timber arris | cutter is subtracted from the timber | subtractive | it touches the solid along a line, with no area | nothing in truth; the simple rule over-reports it |
| Curved | a through peg hole | peg cylinder is subtracted from the timber | subtractive | the wall is on the surface; the end caps are in the air | axis and radius; the bottom cap too if the hole is blind |
| Extras | peg centrelines, layout lines, reference points | not part of the CSG | — | added by the user, not geometry | what the user marks required |
| Don't care | any feature the user waives | any | any | the user says it doesn't matter | removed, unless a required feature still depends on it |

In the solver, the required set is just the rows of the required entities, stacked. Waiving a feature removes its rows; if a still-required edge depends on the same plane, the plane's rows come back in through the edge, and the rank test handles it.

# Detecting hidden features with cutcsg

Detection is done with our own code, not manifold3d. cutcsg is not fragile at what it does today, but it answers questions about *points*, and hidden-feature detection needs questions about *regions*. The region layer half exists in `cropcsg.py`; the missing half is exact polygon booleans in a plane.

**What exists.**

- **Point queries** (`contains_point`, `is_point_on_boundary`) are exact under sympy, apart from the one documented `Difference` limitation in `featuresystem.md`.
- **Lines are done exactly.** `crop_line_to_segments_on_csg` walks the whole tree with intervals (which union, intersect and subtract exactly), and `crop_line_to_boundary_segments_on_csg` separates *on the surface* from *inside the material*. That already answers "which stretches of this edge survive on the finished piece".
- **Planes are approximate.** `approximately_crop_plane_to_area_on_csg` only intersects the solids that enclose the face and counts anything subtracted as still present. Subtracting in a plane needs polygon booleans, and the result can have holes.

**Why not sample points.** Testing sample points on each face with `is_point_on_boundary` misses thin slivers, misreads points near edges, and depends on tolerances. It should not be the basis for deciding what goes on a drawing.

**Proposed: exact face regions by convex clipping.** Every kumiki primitive is convex (a `PathExtrusion` decomposes into convex pieces with `decompose_path_into_convex_pieces`). So:

1. Represent a region in a face's plane as a list of convex polygons, exact in rationals.
2. Intersecting with a convex primitive is half-plane clipping of each piece. Subtracting one convex polygon from another yields at most as many convex pieces as it has sides, so holes never need a special representation.
3. Walk the tree the way the line crop does, keeping *on the surface* and *inside* apart, so a face buried in material, one in the air, and one flush with another surface each classify correctly.
4. A face is required when its on-surface region meets its relative interior (simple rule), or has nonzero area (exact rule; the clipped pieces make this a cheap check, so the exact rule may come for free). Edges keep using the existing exact line crop.

**Curved surfaces** stay approximate: a plane cuts a cylinder in an ellipse, which `cropcsg` already bounds outwards by a polygon. That can misjudge only near-tangent cases. Worth flagging, not blocking.

# Worked example: a tenon

A square tenon on the end of a timber needs 6 position measurements once its directions are taken as square to the timber. Planes after merging:

| Plane | Survives? | Why |
| :--- | :--- | :--- |
| 4 cheeks | yes | visible between the shoulder and the tip |
| Tip | yes | the end of the tenon |
| Tenon back face | no | its relative interior is inside the wood |
| Shoulder | yes | visible around the tenon |
| Timber faces | known | the datum |

That leaves 6 required plane offsets (4 cheeks, tip, shoulder). Directions are square to the reference faces, so under the convention in question 1 they are known.

Measurements that solve it:

1. Shoulder from the timber end: solves the shoulder (and the tenon's back corners through it).
2. Tenon thickness, and one cheek from a reference face: solves both thickness cheeks together. Neither alone solves anything; the rank sees the pair.
3. Tenon width, and one edge cheek from the other reference face: the other two cheeks.
4. Tenon length, tip to shoulder: the tip.

That is 6 rows for 6 required offsets. Leave out the length and the tip reports 1 remaining DOF, which is the generator's cue to add it.

A barefaced tenon has a cheek flush with a timber face. That cheek is required (it's on the surface) but merges with the known timber face, so it needs no measurement and the count drops to 5.

# Open questions

1. **Square by convention?** Is "square to the reference faces unless noted" assumed, so only non-square angles are drawn? If so, those directions start out known in R, which removes most angle measurements.
2. **Is coincidence free?** A cutter face flush with the timber face or the shoulder is treated as known without a dimension (merged planes). That matches how a carpenter reads it; confirm it's intended.
3. **Curved extent:** is surviving area enough to decide when a curved surface is required, or should curves use their analytic extent (a bore's depth, an arc's sweep)?
4. **Extras and waivers:** where does the user mark a feature "required" or "doesn't matter": on the joint in code, in the viewer, or both?

# Plan

1. **Exact face regions** in `cropcsg.py`: convex-piece polygon booleans, and an "on the finished surface" region query per face, tested against the mortise-and-tenon and dovetail patterns.
2. **Required set for a cut timber:** features whose relative interior reaches ∂S, planes merged where they coincide, curved surfaces, user extras.
3. **Rank solver:** unknowns per entity, rows per measurement kind (including the explicit parallel/coincident constraints), R as an incremental exact basis, remaining DOFs per feature. Reproduce the tenon example as a test.
4. **Greedy generator** on top, once 1–3 agree on real joints.
