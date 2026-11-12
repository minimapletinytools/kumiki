# Multi mortise and tenon: several tenons in one joint (2026-11-11)

Status: agreed, not started.

A mortise and tenon joint with any number of tenons, each with its own size, position, length, mortise
depth and pegs, cut on one shoulder. The current single-tenon joint becomes its one-tenon case.

## Why it can't be built from single joints

Each single joint's tenon cut is "everything past the shoulder, minus my tenon". Two of them in a
compound joint each cut the other's tenon away. The multi joint needs one shoulder cut minus the union of
the tenons, so the core function changes rather than wrapping it.

## Signatures

```python
@dataclass(frozen=True)
class TenonSpec:
    """One tenon in a mortise and tenon joint, with the mortise it goes in."""
    size: V2                                   # in the tenon timber's X/Y, like tenon_size today
    position: V2 = (0, 0)                      # centre offset from the timber's centreline
    length: Optional[Numeric] = None           # None: the joint's tenon_length
    mortise_depth: Optional[Numeric] = None    # None: the joint's mortise_depth
    round: bool = False
    peg_parameters: Optional[SimplePegParameters] = None   # positions relative to this tenon


def cut_multi_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    tenons: List[TenonSpec],
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool] = False,
    mortise_shoulder_distance_from_centerline_or_centerplane: Numeric = scalar(0),
    bore_mortise_perpendicular_to_face: bool = False,
    relief: Union[None, ButtJointScribeReliefConfig, ButtJointNotchReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
    inset_shoulder_relief_style: InsetShoulderReliefStyle = InsetShoulderReliefStyle.Rough,
) -> Joint
```

`cut_mortise_and_tenon_joint` keeps its signature and calls this with one `TenonSpec`.

Relative to the joint, like `tenon_width_relative_to_joint` / `tenon_height_relative_to_joint`:

```python
@dataclass(frozen=True)
class JointRelativeTenon:
    width: Numeric                       # along the receiving timber
    height: Numeric                      # across the joint plane
    offset_along_width: Numeric = 0
    offset_along_height: Numeric = 0
    length: Optional[Numeric] = None
    mortise_depth: Optional[Numeric] = None
    peg_parameters: Optional[SimplePegParameters] = None


def cut_multi_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement, tenons: List[JointRelativeTenon], tenon_length, mortise_depth=None,
    mortise_shoulder_inset=0, bore_mortise_perpendicular_to_face=False, relief=...) -> Joint

def cut_multi_mortise_and_tenon_joint_on_face_aligned_timbers(...)   # the check, then pass through
```

A grid of identical tenons, evenly spaced and centred on the timber:

```python
def cut_tenon_grid_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement,
    tenon_count_along_width: int,
    tenon_count_along_height: int,
    tenon_width_relative_to_joint: Numeric,
    tenon_height_relative_to_joint: Numeric,
    tenon_length: Numeric,
    gap_along_width: Numeric = 0,        # between neighbouring tenons; unused when that count is 1
    gap_along_height: Numeric = 0,
    mortise_depth=None, mortise_shoulder_inset=0,
    peg_parameters: Optional[SimplePegParameters] = None,   # applied to each tenon
    relief=...) -> Joint
```

1 x 2 is a twin tenon, 2 x 1 a double tenon, 1 x 1 the plain joint. The name is open.

## What is single-tenon specific today

- **Relief: shared, unchanged.** The scribe and notch reliefs depend only on the shoulder plane and the
  two timbers' bodies, not on the tenon. Keep one shoulder per joint; per-tenon shoulders are what would
  make relief messy.
- **Feature names.** `tenon_left` ... `tenon_top`/`tenon_bot` and `mortise_left` ... `mortise_bottom`
  would repeat across tenons, and two features of one name on one timber is what
  `_drop_duplicate_derived` trips over. With more than one tenon, index them (`tenon_0_left`,
  `mortise_1_bottom`). With one, keep today's names so drawings and tests don't change.
- **End cut and assembly freedom** use the one tenon's length. Use the farthest tenon tip (on an angled
  shoulder each tenon starts at a different distance, so take the max of each tip, not of the lengths),
  and the deepest mortise for the perpendicular bore.
- **Pegs** are positioned relative to `tenon_position`, so they belong to each tenon. Peg and hole labels
  get the tenon index (`peg_0_1`). Only the grid variant has a "same pegs on every tenon" argument.
- **Checks.** Each tenon inside the timber (exists); a round tenon square and without pegs (exists, per
  tenon); tenons must not overlap: reject it.
- **Stays single:** the tusked joint (its tusk assumes one through tenon), the wedged half dovetail (own
  file), the corner variants.
- `wedge_parameters` is accepted by the single joints and never used. Leave it out of the multi
  signatures, or decide whether wedges are per tenon first.

## Angled joints

The per-tenon geometry already works for any angle: each tenon's origin is its position projected along
the tenon axis onto the shared shoulder plane (`locate_tenon_origin_on_shoulder`), its prism runs from
there, and the mortise hole is the same prism. On an angled shoulder, tenons further along the slope just
start further out. The `back_extension` behind each tenon is trimmed by the shoulder, as now.

What needs care:

1. **Fix [oblique-mortise-angle-bug](oblique-mortise-angle-bug.md) first.** With
   `bore_mortise_perpendicular_to_face`, the hole's elongation divides by `sin` where `cos` is meant, so
   off-45 joints get holes too short or too long. A grid inherits it once per tenon. (That plan names
   `joints/workshop/mortise_and_tenon_joints.py`; the file is now under `joints/workshop/mixed/`.)
2. **Overlap with the perpendicular bore** must be checked on the mortise footprints, which are
   elongated by `1/cos` along the slope, not on the tenon sizes. Tenons that clear each other can have
   holes that merge, leaving no wall between them.
3. **End cut**: the max over each tenon's tip, as above.

Tests must use an off-45 joint (the oblique bug went unseen because every brace is 45 degrees): a 2 x 2
grid on the asymmetric brace from the bug's repro, with and without the perpendicular bore, checking
that each tenon fits its hole and the holes don't touch.

## Order

1. Fix the oblique bug, with its off-45 tests.
2. Core `cut_multi_mortise_and_tenon_joint`; `cut_mortise_and_tenon_joint` calls it. The existing tests
   pass unchanged, and drawings of existing patterns don't change (same feature names).
3. Plane- and face-aligned multi variants, then the grid variant.
4. A pattern file (twin tenon into a post, and a 2 x 2 on a wide rail), a line in the cheat sheet's
   "which joint for the job", and the CHANGELOG.
