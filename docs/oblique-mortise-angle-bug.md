# Oblique mortise-and-tenon: `1/sin` where `1/cos` was meant

Status: **open**, not fixed. Found 2026-09-01 while chasing an unrelated
drawing-mode anchor problem. Written down to be dealt with later.

## Summary

`kumiki/joints/workshop/mortise_and_tenon_joints.py` sizes an obliquely-entered
mortise hole with `1/sin_angle` where the geometry calls for `1/cos_angle`. The
two are equal at 45 degrees and diverge everywhere else, so a raking joint gets
a hole that is **too short for its tenon**.

Nothing in the repo catches it because every brace pattern is 45 degrees.

## Why the variables read backwards

At line ~304:

```python
mortise_face_normal = shoulder_plane.normal
cos_angle = safe_dot_product(normalize(mortise_face_normal), normalize(tenon_end_direction))
```

The angle is measured **from the face normal**, not from the face. So

- `cos_angle` = cos(angle from normal) = sin(angle from the face plane)
- `sin_angle` = sin(angle from normal) = cos(angle from the face plane)

A footprint elongation is expected to blow up as the tenon approaches
*parallel* to the face (grazing entry). In these variables that quantity is
`1/cos_angle`. `1/sin_angle` instead blows up at *perpendicular*, i.e. at a
square joint, which is where the least elongation is needed. The names invite
exactly this mistake.

## The geometry

Work in the plane spanned by the face normal `n` and the mortise end direction
`e`. Let `t` be the tenon axis, `c = dot(n, t)`, `s = dot(e, t)`.

The tenon is a strip of width `w` perpendicular to `t`: points `λt + μp` with
`p = (-s, c)` and `|μ| <= w/2`. Intersect with the face plane `n·x = 0`:

    λc - μs = 0            =>  λ = μs/c
    e-component = λs + μc  =  μ(s² + c²)/c  =  μ/c

so the footprint spans `w/c` along the face. **Required elongation is
`w/cos_angle`.**

## Evidence

Built an asymmetric brace (the canonical one joins midpoints of two equal
timbers, hence always 45 degrees) and compared the emitted `mortise_hole`
prism against the tenon:

| brace | entry angle from normal | code's hole/tenon | required |
|-------|------------------------|-------------------|----------|
| midpoint / midpoint | 45.0 deg | 1.4142 | 1.4142 (agrees, cannot distinguish) |
| 0.5 / 0.25          | 63.4 deg | 1.1180 | 2.2361 |
| 0.25 / 0.5          | 26.6 deg | 2.2361 | 1.1180 |

The two off-45 cases are exactly swapped.

Consequences:

- **Raking entry** (tenon near the face): hole too short, tenon does not fit.
- **Steep entry** (tenon near the normal): hole up to 2x too long. Sloppy, but
  it still assembles, which is part of why this went unseen.

## The three uses, and how bad each is

All three divide by `sin_angle`. They are not equally wrong.

| line | expression | verdict |
|------|-----------|---------|
| ~450 | `mortise_hole_size = tenon_size[axis] / sin_angle` | **wrong**, sets real cut geometry. Should be `/ cos_angle` (use `Abs`). |
| ~383 | `end_crop_distance = tenon_size[axis] / sin_angle / 2` | **likely wrong**, same swap, same block. Verify separately: it positions a crop half-space rather than sizing the hole. |
| ~333 | `back_extension = max(tenon_size) / sin_angle` | **wrong shape but harmless.** See below. |

### back_extension

This extends the tenon prism *backwards* behind the shoulder
(`start_distance=-back_extension`) so the prism does not fall short where the
tilted shoulder plane dips behind axial zero. The reach actually needed is
about `w * tan(angle from normal)` = `w * sin_angle / cos_angle`, which goes to
zero at square. `w / sin_angle` goes to infinity there instead.

It is harmless in practice because the shoulder half-space is subtracted
(`subtract=[shoulder_half_space_global]`, line ~579), so any over-reach is
trimmed and the finished joint is identical. It only became visible when
drawing mode asked a face of that prism where it was and got an answer
hundreds of metres away.

Note `w/sin` does fall *below* the needed `w*tan` past roughly 65 degrees from
the normal, so a very raking joint may be under-extended as well. Unverified.

## Already done (do not redo)

- `back_extension` is now `0` on a square joint. It used to divide by a
  guard-against-zero of `1e-4`, producing a 952 m cutter exactly where none
  was wanted. Commits `674f494`, `62cf02d`.
- `is_square` is a single named test shared by `back_extension` and the
  `do_lengthwise_cropping` gate; they used different tolerances before and
  disagreed over `|sin|` in `1e-8 .. 1e-4`.
- `tests/test_csgconvexhull.py::TestObliqueJointStillBuilds` covers the oblique
  path at all (it had none). Mutation-tested against all three divisions.

## Fix plan

1. Rename to match the convention: `cos_angle` -> `cos_from_normal`, or better,
   introduce `sin_from_face = Abs(cos_angle)` and use that for the footprints.
   The rename is most of the fix, since the bug is a reading error.
2. Change `mortise_hole_size` (~450) to divide by `Abs(cos_angle)`.
3. Work out `end_crop_distance` (~383) from the geometry independently. Do not
   assume it takes the same correction just because it sits in the same block.
4. Decide on `back_extension` (~333) separately. `w * sin_angle / cos_angle` is
   the derived value; leaving it as an over-estimate is defensible since it is
   trimmed, but then it wants a comment saying so and a cap so it cannot run
   away near square.
5. Guard the new divisor: `cos_angle -> 0` is grazing entry, a degenerate joint
   that should `require_check` rather than divide.

## Test plan

The gap that hid this is that every brace in the repo is 45 degrees, where
`sin == cos`. **Any test must use an off-45 joint.**

1. Parameterised test over entry angles, at minimum 26.6, 45 and 63.4 degrees
   (from `location_on_timber2` fractions 0.25, 0.5 and, with the fractions
   swapped, 0.25 again). Assert `mortise_hole` extent along the mortise end
   direction equals `tenon_width / cos_angle` within tolerance.
2. Assembly interference check at the raking angle: the tenon must fit inside
   the mortise hole. This is the test that would have caught it as a defect
   rather than a discrepancy, and it was never run here.
3. Keep a square joint in the set so the `is_square` branch stays covered.
4. Re-run the mutation check afterwards: break each divisor in turn and confirm
   a test fails. Line ~450 sits in the non-round branch of `use_round_tenon`,
   so a round-tenon fixture will not reach it.

## Repro

```python
# asymmetric brace; the canonical one is always 45 degrees
arr = create_canonical_example_brace_joint_timbers(create_v3(0, 0, 0))
brace = join_plane_aligned_on_plane_aligned_timbers(
    timber1=arr.timber1, timber2=arr.timber2,
    location_on_timber1=arr.timber1.length * scalar(0.5),
    location_on_timber2=arr.timber2.length * scalar(0.25),   # 0.25 != 0.5 is the point
    stickout=Stickout.nostickout(), size=arr.timber1.size,
    orientation_long_face_on_timber1=TimberLongFace.RIGHT,
    orientation_long_face_on_timber2=TimberLongFace.RIGHT,
    ticket="brace",
)
joint = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement=ButtJointTimberArrangement(
        butt_timber=brace, receiving_timber=arr.timber1,
        butt_timber_end=TimberEnd.BOTTOM, front_face_on_butt_timber=TimberLongFace.RIGHT,
    ),
    tenon_width_relative_to_joint=inches(3), tenon_height_relative_to_joint=inches(1),
    tenon_length=inches(5), mortise_depth=inches(3),
    bore_mortise_perpendicular_to_face=True,   # required, or the cropping never runs
)
# walk the negative CSGs for labels "tenon" and "mortise_hole", compare .size
```
