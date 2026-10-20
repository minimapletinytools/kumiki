# Finding duplicate, rotated and mirrored timbers

Status: research and a plan, nothing built (2026-10-20).

A routine the user calls before solving drawings: which cut timbers are the same piece, so one solve
(and one shop drawing, "×N") covers them all. It also says when two timbers are the same piece
rotated, or mirrored, and leaves it to the caller whether to solve those again.

## What a prototype found

A throwaway, geometry-only check: each cut timber's mesh in its own local frame, its vertices
rounded to 10 µm, compared with every other timber of the same size under each symmetry of its box
(below).

| Frame | Timbers | Distinct pieces | Identical | Reflections | Rotations |
|---|---|---|---|---|---|
| `cat_corner_cot` | 100 | 30 | 70 | 0 | 0 |
| `tinyhouse120` | 75 | 29 | 32 | 14 (studs, left vs right) | 0 |
| `oscarshed` | 25 | 17 | 8 | 0 | 0 |
| `my_cute_frame_drawing_test` | 4 | 4 | 0 | 0 | 0 |

- Every matched pair also had the same CSG tree shape and the same node labels.
- Every matched pair had the same ticket reference features, the same tags, and the same feature
  names and properties.
- Cost: 0.1–0.5 s, nearly all of it triangulating; the comparing was 0.01–0.06 s.

So on the cot, 100 member solves would become 30: most of the ~3.8 s it now takes to open.

## Why rotations are rare

A timber's tree is in its own local frame, which moves with it. So the same piece installed turned
over, or end for end, is already **identical**: nothing about it is rotated in its own frame. A
rotation match means the same piece was *authored* in a different local frame (built with its
length running the other way, or turned about its length).

## The symmetries

A timber's box is `[-w/2, w/2] × [-h/2, h/2] × [0, L]` in its local frame. The isometries that map
it to itself:

- flip width (x → −x), flip height (y → −y), flip end for end (z → L − z): 8 combinations;
- with a square section, also swap width and height: 16.

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

1. **Bucket cheaply**: by (sorted section size, length, tree shape). The tree shape is node types
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
4. **Report differences** that the geometry doesn't settle, without refusing the match:
   - ticket reference features (mapped through the symmetry: a reflection turns `left` into
     `right`);
   - feature names and properties (marking overrides, purposes), node labels;
   - tags.

The mesh fingerprint from the prototype could stay as a cross-check in tests: it doesn't care
about tree shape, so it catches a comparator that wrongly refuses a match.

## Things to decide

1. **Reflections and names.** A mirrored piece whose reference features have the same names is
   measured from the opposite physical face. Should a reflection only count as a match when its
   reference features map onto each other (left reference on one is the right reference on the
   other)? And in the shop a mirrored piece is a different, "handed" piece: is a drawing of one
   with "mirror of" good enough, or does it get its own?
2. **What has to be equal.** Tree shape, as you said. Labels and feature properties differed in no
   pair here, but they could. Report them as differences (the plan above), or refuse to match?
3. **Where it's used.** In the patterns' generators (`cat_corner_cot._with_auto_drawings`) first:
   solve each group's representative, and give its drawing the group's count. Later, maybe, in
   `Frame` itself, so a cut list and the shop drawings agree on what is "the same piece".
4. **Measures for the other members.** Reusing the representative's drawing is enough for a shop
   drawing. Anything that needs the duplicate's own measurements (a frame drawing that dimensions
   both) has to map each feature handle through the match: the node by its path, the feature by
   its name, mapped through the symmetry.
