# Finding duplicate, rotated and mirrored timbers

Status: research and a plan, nothing built (2026-10-20). Reflections are detected and reported; what to do with them is the caller's choice.

A routine the user calls before solving drawings: which cut timbers are the same piece, so one solve
(and one shop drawing, "×N") covers them all. It also says when two timbers are the same piece
rotated, or mirrored, and leaves it to the caller whether to solve those again.

## What a prototype found

A throwaway check, geometry only: two cut timbers match under a symmetry when every triangle centre
of one, mapped through it, lies on the other's surface, and back. Run on these frames:

| Frame | Timbers | Distinct pieces | Identical | Rotations | Reflections |
|---|---|---|---|---|---|
| `coffee_table` | 14 | 6 | 3 | 3 (table tops, bottom stretchers) | 2 (legs) |
| `my_cute_frame_drawing_test` | 4 | 2 | 0 | 2 (the crosses, the sides) | 0 |
| `tinyhouse120` | 75 | 26 | 29 | 13 (studs) | 7 (bottom beams) |
| `oscarshed` | 25 | 14 | 8 | 2 | 1 (front posts) |
| `cat_corner_cot` | 100 | 30 | 70 | 0 | 0 |

Rotations and reflections are common: most frames are built symmetric.

- Every matched pair had the same CSG tree shape. Labels differed in 8 pairs, and reference
  features in 2 (both in the cute frame), so those are differences to report, not to match on.
- Cost: 0.3–4.5 s a frame, nearly all of it triangulating and point tests. Too slow to run on
  every load; the tree comparison below should be far cheaper. The prototype stays useful as a test
  oracle, since it doesn't care about tree shape or how a face was triangulated.

What it took to get right, which the real routine has to respect:

- **Symmetries about the material's box, not the timber's centreline.** Rough stock sits flush with
  the reference faces, so off centre, and ends are extended past the timber. Flipping about the
  centreline found nothing on the cute frame.
- **Not the mesh's vertices.** Mirrored pieces triangulate differently (a holed face gets different
  points added), so their vertex sets differ even when the pieces are the same.
- **Curved faces are tessellated.** A hole's flat triangles sag inside the cylinder, so their
  centres are not on the surface; only centres on the piece's own surface are sampled.
- **Surface area is only a loose filter.** Same pieces' triangulated areas differed by up to 0.05%.

## The symmetries

A cut timber's material sits in a box in its local frame (the rough stock, plus any extended ends).
The isometries that map one piece's box onto the other's, about the boxes' centres:

- each axis flipped or not: 8 combinations;
- with a square section, width and height swapped too: 16.

Each has a determinant: +1 is a **rotation**, −1 a **reflection**. The identity is **identical**.
Only those are worth trying: two pieces that match under any other isometry don't have the same
box.

## Proposed routine

```python
def match_timbers(cut_timbers, *, rotations=True, reflections=True) -> List[TimberGroup]

@dataclass(frozen=True)
class TimberMatch:
    cut: CutTimber
    kind: MatchKind          # IDENTICAL, ROTATION, REFLECTION
    symmetry: Symmetry       # the box isometry taking the representative onto this one
    differences: Tuple[str, ...]   # what differs that the geometry doesn't: see below

@dataclass(frozen=True)
class TimberGroup:
    representative: CutTimber
    matches: Tuple[TimberMatch, ...]
```

The caller decides what to do with each kind: solve once per group of identical pieces; for
rotations and reflections, solve again or not.

Steps:

1. **Bucket cheaply**: by (the material box's section, sorted, and its length; the tree shape). The tree shape is node types
   and child counts, walked in order. Only timbers in one bucket are compared.
2. **Compare trees under each symmetry**, walking both in step:
   - The same node type at every step, as you suggest. A union's children in the same order
     first; if that fails, try matching them unordered (a union of a few children only).
   - Primitives compared by their parameters after mapping the other one's through the symmetry,
     within a tolerance (1e-6 m, 1e-9 on directions):
     - prism: size, centre, axis directions as lines (sign free), start and end distances (swapped
       and negated by an end flip);
     - half space: normal and offset;
     - cylinder: axis line, radius, start and end;
     - convex extrusion and loft: the profile's points mapped and compared as a set (a reflection
       reverses their winding), the caps;
     - path extrusion: the path's segments mapped.
   - No new trees are built. `adopt_csg` can move a tree by a rotation, but a reflected prism or
     extrusion would have a left-handed frame, which nothing else expects.
3. **Group**: the first timber of a bucket is a representative; each other one joins the first
   group it matches, trying the identity first, then rotations, then reflections.
   The symmetries are about each piece's material box (its rough stock and extended ends), not its
   centreline.
4. **Report differences** that the geometry doesn't settle, without refusing the match:
   - ticket reference features (mapped through the symmetry: a reflection turns `left` into
     `right`);
   - feature names and properties (marking overrides, purposes), node labels;
   - tags.

The mesh fingerprint from the prototype could stay as a cross-check in tests: it doesn't care
about tree shape, so it catches a comparator that wrongly refuses a match.

## Things to decide

1. **Reflections: settled.** Detected and reported as REFLECTION; the caller chooses whether to
   solve them again. Worth noting on the drawing: a mirrored piece whose reference features have
   the same names is measured from the opposite physical face, and in the shop it is a "handed"
   piece.
2. **What has to be equal.** Tree shape, as you said: it held in every match found. Labels differed
   in 8 matched pairs and reference features in 2, so they are reported as differences (the plan
   above) rather than refusing the match -- unless a differing reference feature should refuse it,
   since it changes the datum a piece is dimensioned from.
3. **Where it's used.** In the patterns' generators (`cat_corner_cot._with_auto_drawings`) first:
   solve each group's representative, and give its drawing the group's count. Later, maybe, in
   `Frame` itself, so a cut list and the shop drawings agree on what is "the same piece".
4. **Measures for the other members.** Reusing the representative's drawing is enough for a shop
   drawing. Anything that needs the duplicate's own measurements (a frame drawing that dimensions
   both) has to map each feature handle through the match: the node by its path, the feature by
   its name, mapped through the symmetry.
