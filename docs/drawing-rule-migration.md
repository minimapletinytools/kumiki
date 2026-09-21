# Moving `drawing.py` onto `rule.py`

`kumiki/drawing.py` defines its own 3-vector math -- `_unit`, `_dot`, `_cross`,
and about 120 lines of `for i in range(3)` -- instead of using the `Matrix`/`V3`
types and helpers in `rule.py`, which every other file in the library uses. This
is the plan for moving it over.

Status: **Stages 0-4 are done, and step A of the seam change.** Step B of the
seam change is the only piece left, and it is waiting on a decision. Baseline
recorded below.

## Why it is the way it is

Not an import cycle and not an oversight. `drawing.py` already does
`from .rule import Numeric`, and `geometry.py` -- which uses rule.py properly --
sits below it in the import graph with no cycle.

The measuring half of the file is a **line-for-line mirror of
`kigumi/webview/measurements.js`**:

| `kumiki/drawing.py` | `kigumi/webview/measurements.js` |
| --- | --- |
| `_unit` (191) | `normalized` (84) |
| `_dot` (198) | `dot` |
| `_cross` (256) | `cross` (76) |
| `_flatten` (249) | `flatten` (67) |
| `projected_form` (206) | `projectedForm` (37) |

Five docstrings say so outright ("THE VIEWER HAS A COPY... a test runs the two
against each other"). The math was written as index loops so the two files can
be diffed by eye. Reinforcing it, the data is JSON at both ends: geometry
arrives as a `Mapping` off the wire and anchors go back out as `list`.

That explains it; it does not justify it. `AGENTS.md` and
`.github/instructions/authoring.instructions.md` both say "use math types in
`rule.py`", and nothing stops rule.py types living in the middle with conversion
only at the wire -- which is what `kigumi/runner.py` already does at the timber
boundary (`_vector3_to_floats`).

See [the seam question](#appendix-why-two-copies-at-all) for whether the mirror
needs to be as wide as it is.

## What is actually duplicated

Sixteen private helpers, all with a rule.py or geometry.py equivalent:

| `drawing.py` | replacement |
| --- | --- |
| `_unit` 191 | `safe_normalize_vector` / `geometry.unit_vector` |
| `_dot` 198 | `safe_dot_product` or `Matrix.dot` |
| `_cross` 256 | `cross_product` / `Matrix.cross` (**note: not equivalent, see below**) |
| `math.sqrt(_dot(g,g))` 516, 520 | `safe_norm` / `Matrix.norm()` |
| `_plane_crossing` 393 | **`geometry.intersect_planes`** |
| `_line_meets_plane` 635 | **`geometry.intersect_line_plane`** + the flat-line fallback |
| `_flatten` 249, `_flatten_onto` 648 | one shared `v - n * dot(v, n)` |
| `_stations`, `_at_station`, `_foot_on`, `_foot_on_plane`, `_closest_on_line`, `_representative_point`, `_closest_between`, `_ray_toward`, `_clamp_to` | keep as domain logic, written in `Matrix` ops |

Plus 28 `for i in range(3)` loops, and tuple-typed fields on `MeasureSpan` and
`MeasurementPlane`.

### Explicitly out of scope

The layout half of the file -- `Share`, `Length`, `Page`, `Portion`,
`Subdivision`, `Viewport`, `Drawing`, `rows`, `columns`, `covering_page` and the
default-viewport helpers -- is **already correct**. It uses `Numeric` from
rule.py and holds no vectors. Do not touch it.

`Rect` stays `Tuple[float, float, float, float]`. It is four fractions of a
page, not a world vector; `V3` would be a category error and `Matrix` buys
nothing. Same reasoning as the note on `MeasurementPlane` about floats rather
than exact scalars: this is where a dimension is drawn, not where a joint is
cut.

## What the investigation turned up

Five things were measured rather than assumed. Two de-risk the work, one raises
its priority, two are constraints on how it is done and how it is judged.

### 1. One live bug and one dead guard, same root cause: `_cross` normalises

`_cross` (256) ends in `return _unit([...])`. Two of its six call sites assume
it does not. **1a is live and reaches the product. 1b is not reachable** -- it
is a guard that cannot fire, which is worth correcting but is not a bug anyone
has hit.

#### 1a. `_plane_crossing` puts the corner in the wrong place

The docstring at 401-404 says it outright -- "The UNNORMALISED cross, because
the closed form below divides by its square length. Normalising first and
dividing by one puts the point out by a factor of the sine between the planes"
-- and then calls `_cross`. The right comment was written against the wrong
helper.

Consequences:

- `scale = _dot(along, along)` is always exactly `1.0`, never `sin²θ`.
- The returned point is `sin(θ) x` the true point, so it is off both planes by
  `(1 - sin θ)` times the distance from the world origin to the shared corner.
- `if scale < PARALLEL_EPSILON` can only fire when the cross is exactly zero.
  The near-parallel guard is dead code.

Measured, with the corner at x=2000, z=1500 (mm):

| faces meet at | vertex off face A | off face B |
| --- | --- | --- |
| 90° | 0.000 | 0.000 |
| 60° | exact | exact |
| 45° | 87.9 mm | 289.9 mm |
| 30° | 150.0 mm | 331.7 mm |

Exact at 90°, and exact whenever the shared line passes through the world
origin. **That is why every test passes**: `TestWhereAnAngleSits` uses two
perpendicular planes through the z axis, which is the one case the bug cannot
reach. Square framing never shows it; oblique joinery does.

Severity: **the labelled number is wrong too, not just the picture.** Four
structured cases all reported the right angle, which suggested only the vertex
moved; over 20,000 random plane pairs the reported angle changes in **1441** of
them. `_ray_toward` uses the vertex to decide which of the two supplementary
angles is meant, so a displaced vertex can pick the wrong side.

That the corrected one is right, rather than merely different, was checked on
those 1441: the old vertex sits up to **3100 units** off the two faces, the new
one **2.7e-12**, and every new ray lies in its own face.

The dead near-parallel guard has no live effect today, because `kinds_for`
refuses near-parallel planes upstream at ~8.11° before `angle_rays` is reached.
Defence in depth is gone, not correctness. Reviving it makes `angle_rays` refuse
plane pairs within ~5.74° of parallel when called directly -- 134 of the same
20,000 -- and never the reverse, which is the guard doing what it says.

`geometry.intersect_planes` computes this correctly: verified over 20,000 random
plane pairs, max distance off either plane **3.6e-12** against drawing.py's
**638**. So this migration *fixes* the bug rather than merely tidying around it.

The viewer is not implicated: `angleArcPoints` and `angleLabelPoint`
(measurements.js 521-540) consume `rays.vertex` as python sends it and derive
only a screen-space vertex from projected points. The fix is python-only and
does not touch the parity tests.

#### 1b. `angle_rays`' degeneracy guard cannot fire

`angle_rays` 593 builds the plane an angle is swept in:

```python
upright = _cross(rays[0], rays[1])
if not any(abs(part) > 1e-9 for part in upright):
    return None
```

Because `_cross` normalises, `upright` is unit length or exactly zero -- never
small. Measured, for rays 1e-8° apart the raw cross has magnitude 1.7e-10 and
`_cross` returns a **unit** vector, so the guard passes:

| rays apart | raw \|cross\| | after `_cross` | guard fires? |
| --- | --- | --- | --- |
| 1° | 1.7e-02 | 1.000000 | no |
| 1e-4° | 1.7e-06 | 1.000000 | no |
| 1e-8° | 1.7e-10 | 1.000000 | no |

So two near-parallel rays would yield an angle plane built from rounding noise
instead of being refused. `geometry.py`'s `unit_vector` docstring warns about
precisely this -- "dividing by anything merely above zero ... turns the cross
product of two nearly parallel edges into a direction made of rounding noise" --
which is why `safe_normalize_vector` has a floor and `_unit` does not.

**But nothing reaches it.** Driving `angle_rays` with 30,000 random spans across
all three shapes, the smallest raw `|cross(rays)|` ever seen at this guard was
**9.5e-5** -- five orders of magnitude above the 1e-9 threshold. Every shape is
refused upstream at a much wider angle first:

| shape | upstream guard | fires at |
| --- | --- | --- |
| plane-plane | `_plane_crossing`, normals parallel | -- |
| line-line | `_closest_between`, `spread < 1e-2` | 5.74° |
| line-plane | `_line_meets_plane`, `\|rate\| < 1e-2` | 0.57° |
| any | `kinds_for` calls the pair parallel | 8.11° |

So 1b is a guard that cannot fire, not a defect in output. Correct it while
fixing 1a -- the two share a cause and it is one line -- but do not write a
Stage 0 test for it: the case is unreachable through the public API, and a test
that constructs it would be testing a private helper's internals.

The other four `_cross` call sites (244, 564, 565) are well-conditioned by
construction -- the two operands are perpendicular there -- so they are safe.

### 2. No float drift from the swap

`safe_normalize_vector`, `safe_dot_product`, `cross_product` and `safe_norm` are
**bit-identical** to the tuple versions over 200,000 random vectors spanning
1e-6 to 1e6 in magnitude: max abs difference `0.0` for all four.

This matters because the node parity tests compare python against JS at
`abs=1e-9`. The swap cannot break them numerically. It is the single biggest
de-risking fact for Stage 1.

### 3. Performance is a non-issue

`Matrix` is 2.7x slower than tuple math for 3-vectors (3.8x including
construction): 1.05 µs -> 2.83 µs for a normalise-and-dot pair.

It does not matter. There are exactly two call sites into this math, both
measured:

- `_kinds_for_pair` in the hover path, over candidate features. `projected_kinds`
  is 5.5 µs now, so ~16 µs after; at 20 candidates that is 0.22 ms added to a
  request whose mesh walk is already milliseconds.
- `_resolve_measurement`, once per written measurement.

Neither is O(n²) and there is no bulk path. Do not optimise for this.

### 4. `drawing.py` is the only unclean module in the repo

All 70 `ty` diagnostics come from `drawing.py` and its three test files.
`rule.py`, `geometry.py`, `runner.py`, `timber.py` and everything else are
clean:

| file | count | what they are |
| --- | --- | --- |
| `kumiki/drawing.py` | **22** | 14 bad args to `_unit`, 4 bad returns, 4 `Mapping\|None.get` |
| `tests/test_measurement_anchors.py` | 39 | `importlib.module_from_spec(spec)` on a `ModuleSpec\|None` |
| `tests/test_measurement_plane.py` | 6 | ditto, plus `MeasurementPlane\|None` attribute access |
| `tests/test_measurement_end_to_end.py` | 3 | ditto |

Two things follow. First, `geometry.py` uses `Matrix` throughout and has **zero**
diagnostics, so ty handles these types fine and the migration will not trade one
set of errors for another. Second, **do not expect ty to reach zero**: the 48 in
the test files are an unrelated `importlib` pattern that this work does not
touch. Stage 1 should take 70 to about 48, and no further.

### 5. `--cov` cannot be used on this suite

`pytest --cov` makes `test_measurement_anchors.py` fail and
`test_measurement_end_to_end.py` error (20 errors), and crashes outright on some
combinations -- those tests re-exec `kigumi/runner.py` through `importlib`, which
coverage interferes with. The plain run is green.

One figure was obtained before it broke: **94% of `drawing.py`** (38 of 605
statements missed). Do not expect to measure coverage of the refactor; lean on
the parity tests instead.

## Gotchas

1. **`rule.degrees()` converts degrees to radians** -- the opposite of
   `math.degrees`. `angle_between` (663) needs radians to degrees and must keep
   `math.degrees`. rule.py has no equivalent; `format_angle` is for display.

2. **`giraffe_normalize_vector` returns the input unchanged** when the norm is
   below `EPSILON_GENERIC`; `_unit` returns `(0, 0, 0)`. Four call sites depend
   on the zero -- `_ray_toward` 430, `_flatten_onto` 653, `angle_rays` 588,
   `projected_form` on a zero direction -- and the JS mirror returns `[0,0,0]`
   too (measurements.js:86). Keep a thin `unit_or_zero` wrapper, or use
   `geometry._unit_or_none` and handle `None`.

3. **`_cross` normalises and `cross_product` does not.** Six call sites, and
   they do not want the same thing:

   | site | wants | today |
   | --- | --- | --- |
   | `projected_form` 244 | unit | fine (operands perpendicular) |
   | `_plane_crossing` 400, 409 | **raw** | **bug 1a** |
   | `angle_rays` 564, 565 | unit | fine (operands perpendicular) |
   | `angle_rays` 593 | **raw**, to test magnitude | **bug 1b** |

   Do not swap `_cross` for `cross_product` globally. Introduce both a raw and
   a unit form and pick per site. This helper is the root cause of finding 1.

4. **Three places compare a squared quantity against the linear
   `PARALLEL_EPSILON`** -- `_plane_crossing` 407 (dead, see above),
   `_closest_between` 612 (`spread` is sin²), against `_solid_parallel` and
   `projected_kinds` which compare `|dot|` linearly. rule.py has
   `safe_zero_test_sq` precisely for this. The squared tests fire at ~5.74° and
   the linear ones at ~8.11°, so the ordering is safe today by accident. Fix
   deliberately with a test, not silently.

5. **The three epsilons stay in `drawing.py`.** `DEGENERATE_SEPARATION`,
   `ALIGNMENT_EPSILON` and `PARALLEL_EPSILON` are mirrored in measurements.js
   and pinned by parity tests. `EPSILON_GENERIC` (1e-8) is float-noise
   tolerance and is not a substitute for a domain tolerance.

6. **`Matrix` is unhashable** -- it defines `__eq__` without `__hash__`. That
   makes any frozen dataclass holding one unhashable too. Nothing currently
   hashes `MeasureSpan`, `MeasurementPlane` or `Measure` (checked), and
   `Measure.identity()` returns tuples of strings, so this is safe -- but it is
   a door closing, and worth a comment so it is not rediscovered.

7. **`json.dumps` will not serialise a `Matrix`.** Every path from drawing.py
   output to the wire must go through `as_wire()`, `list()` or `tuple()`.
   `MeasurementPlane.as_wire` and `angle_rays` already do. Audit this in
   Stage 2.

## The plan

Each stage lands as its own commit and is independently green, so the sequence
can stop after any of them.

### Stage 0 -- pin the bug

Before changing anything, add a test for 1a that fails today. It is what proves
Stage 1 fixed something rather than merely moved it.

Two faces meeting at 45° with the corner away from the world origin; assert the
angle's vertex lies on both planes. Today it is ~88 mm and ~290 mm off. Note why
the existing `TestWhereAnAngleSits` misses it: its planes are perpendicular and
pass through the z axis, the one case the bug cannot reach.

No Stage 0 test for 1b -- the guard it fixes is unreachable through the public
API (see finding 1b).

### Stage 1 -- internal math only, no API change

Replace the sixteen helpers' bodies with rule.py calls. Every public signature
keeps taking and returning tuples and `Mapping`s; convert at the top of each
public function and back at the `return`.

- Import `Matrix`, `V3`, `create_v3`, `safe_dot_product`,
  `safe_normalize_vector`, `safe_norm`, `cross_product`, `are_vectors_parallel`,
  `are_vectors_perpendicular`, `safe_zero_test_sq`.
- Add `_v3(seq) -> V3` and `_unit(v) -> V3` (the zero-returning one, gotcha 2).
- Split `_cross` into a raw and a unit form (gotcha 3).
- `_plane_crossing` -> keep the `PARALLEL_EPSILON` guard on a *correctly*
  computed `sin²` (that refusal is drawing's own rule, not geometry's), then
  delegate to `geometry.intersect_planes`. Stage 0's test goes green here.
- `_line_meets_plane` -> `geometry.intersect_line_plane`, keeping the
  runs-flat fallback.
- Rewrite `abs(_dot(a,b)) > 1 - ALIGNMENT_EPSILON` as
  `are_vectors_parallel(a, b, eps=ALIGNMENT_EPSILON)` and
  `abs(_dot(n,g)) > ALIGNMENT_EPSILON` as
  `not are_vectors_perpendicular(n, g, eps=ALIGNMENT_EPSILON)`. Both are exactly
  equivalent, including at the `normal=[0,1,0.0005]` case the parity test
  deliberately straddles.
- Leave the remaining squared/linear epsilon mix alone, with a one-line note
  pointing at `safe_zero_test_sq`. That is Stage 4.

Nothing outside `drawing.py` changes. Every test but Stage 0's must pass
untouched -- that is the proof the stage is behaviour-preserving.

Expected: `ty` diagnostics drop from 70 to about 48 -- `drawing.py`'s 22 go, and
the 48 `importlib` ones in the test files stay (finding 4). Fix the four
`invalid-return-type` errors while here: `projected_form` and `solid_form` are
annotated `-> Tuple[MeasurementFeature, ...]` and both can return
`(None, None)`, so the annotation wants `Optional[MeasurementFeature]`.

### Stage 2 -- `MeasureSpan` and `MeasurementPlane` hold `V3`

`at`, `direction`, `normal`, `outward` become `V3`. `interval` stays
`Tuple[float, float]` -- those are scalar stations, not vectors. `__post_init__`
accepts any sequence and coerces.

Blast radius, counted:

- **`kigumi/runner.py`**: six `MeasureSpan(...)` constructions in `_measure_span`
  (2795-2875), and the `distance_anchors` unpack at 2132.
- **Tests**: ~30 assertions of the form
  `assert at_edge == (600.0, 300.0, 100.0)` in `test_measurement_anchors.py`,
  plus `test_measurement_plane.py:150-151`. `Matrix.__eq__` returns
  `NotImplemented` against a tuple, so these fail loudly rather than silently --
  each needs `tuple(...)` on the left.
- **Serialisation**: audit every path to `json.dumps` (gotcha 7).

`as_wire()` needs no change: `list(Matrix)` already yields `[x, y, z]`.

**Done.** `MeasureSpan` and `MeasurementPlane` hold `V3`, coerced in
`__post_init__` so callers may still write a triple -- which `runner.py` does in
six places, unchanged. Two narrowing accessors, `span.along` and `span.facing`,
give the rules for lines and planes a non-optional vector to work with and are
what took `drawing.py` to **zero ty diagnostics**; `interval` stayed a pair of
floats, being stations rather than a place. The anchors `distance_anchors`
returns and the points `ends()` yields are vectors now too, so nothing converts
back and forth mid-rule.

The 17 span constructions in `test_measurement_anchors.py` went through three
helpers (`point`, `line`, `face_span`) rather than being rewritten one by one,
which is why only four `MeasureSpan(` calls are left in that file.

Checked against the Stage 1 file imported side by side: `distance_anchors`
(120,000 components) and `angle_rays` (158,520 components) over 20,000 random
span pairs are **bit-identical**. Nothing reaches `json.dumps` as a raw
`Matrix`: both fixtures' `collect_drawings` output serialises cleanly.

### Stage 3 -- real types for geometry

`projected_form`, `solid_form`, `pair_separation`, `measures_nothing`,
`projected_kinds` and `solid_kinds` take `Optional[Mapping]` with a `"kind"`
discriminator. That is a hand-rolled sum type over exactly
`geometry.Point | Line | Plane`, which already exist and already use `V3`.

Change those six to take the primitives and dispatch on `isinstance`.
`_located_geometry_payload` (runner.py:3192) becomes the single seam: it keeps
producing the dict **for the wire to JS**, and gains a sibling handing python the
primitive. The runner is already holding the `Point`/`Line`/`Plane` there -- it
converts down to dicts and drawing.py reads them back up.

This resolves the "use a real type for geometry" TODO. Hold it separate: it
touches the runner's payload layer, not just `drawing.py`. Stages 1 and 2 are
worth doing whether or not this happens.

**Done.** The six functions take `Point | Line | Plane` and dispatch on
`isinstance`. `runner.py` grew three functions at the edge:
`_located_geometry` (a feature's geometry in world space, as a primitive),
`_geometry_payload` (that, in the mapping the viewer reads) and
`_geometry_from_wire` (the way back, for the held end the viewer sends). The
old `_located_geometry_payload` is now the first two composed.

`_anchor_of` was needed because the three primitives name their point
differently -- `Point.position`, `Line.point`, `Plane.point` -- which the
mapping form had flattened to one `"at"` key.

Two behaviours moved with it. `_best_matching_candidate` broke its tie on
`geometry.get("kind") == held_kind`; it now asks `type(geometry) is type(held)`.
`_measure_span` read `["normal"]` off a payload it built only to read one field,
and takes it from the primitive.

The dicts in `test_measurement_kinds.py` stayed dicts -- the same values go to
node as JSON for the parity tests -- with one `geometry()` converter in the
test file doing what the runner does at the same edge. The end-to-end tests
build the primitives directly, which reads better than the mappings did.

Checked against the Stage 2 file imported side by side, each fed the form it
takes: form directions (90 components), the kind tables (288 pairs) and
`pair_separation` (188 values) are **bit-identical**.

### Stage 4 -- optional, deliberate epsilon cleanup

With the math in rule.py terms, make the remaining squared comparison use
`safe_zero_test_sq` and state each threshold as an angle in the comment. Needs
its own test pinning the ~5.74°/~8.11° ordering, which is currently load-bearing
and accidental. Do not fold into Stage 1.

**Done**, and there were two squared comparisons left, not one --
`_plane_crossing`'s stopped being dead once Stage 1 gave it a raw cross. Both
now use `safe_zero_test_sq`, which squares the tolerance rather than the value,
so `PARALLEL_EPSILON` means a plain sine in all three corner rules:
`_line_meets_plane` already read it that way, and the other two now agree at
0.573° instead of 5.739°.

The two readings of the one epsilon are now written down where it is defined.
`kinds_for` asks it of a COSINE and calls a pair parallel below 8.110° -- the
drafting rule, deciding whether an angle is offered at all. The three corner
rules ask it of a SINE and refuse below 0.573° -- a conditioning guard standing
behind the first. **The order is the invariant**: the guard must refuse a
narrower band than the table, or a pair could be offered an angle and then be
unable to say where its vertex is.

`TestAPairOfferedAnAngleCanAlwaysSayWhereItIs` pins that behaviourally across
all three shapes at thirteen angles either side of both thresholds. It was
checked for teeth: widening the corner guard to ~12° fails it at 8.2° and 12°,
which are exactly the angles the table admits and the guard would refuse.

No live behaviour change. The band that moved, 0.58°-5.73°, is unreachable:
`kinds_for` admits no angle below 8.110°, so nothing gets that far.

### Sequencing, across both tracks

The seam change in the appendix is a separate track. Recommended order:

| # | Work | Why here |
| --- | --- | --- |
| 1 | Stage 0 + Stage 1 | Fixes a live bug and a dead guard; behaviour-preserving otherwise, and the parity tests prove it |
| 2 | Seam change, step A (appendix) | Makes python the one place the number is worked out |
| 3 | Stage 2, Stage 3 | Much cheaper once little has to stay bit-compatible with JS |
| 4 | Stage 4 | Cosmetic-ish; needs its own test |

Stage 0+1 is worth doing first regardless of whether the seam change ever
happens.

## Open questions

Decisions not made here, and one thing not yet proven:

- **Does bug 1a get fixed now, on its own?** It is live and the fix is small
  (correct `_plane_crossing`, add a raw cross, use it at 593 too). Coupling it
  to Stage 1 is tidier; landing it first is faster and independently reviewable.
  Not decided.
- **Not yet reproduced end-to-end.** Bugs 1a and 1b were found by calling
  `_plane_crossing` and `angle_rays` directly with valid `MeasureSpan` inputs.
  They are reachable by construction -- `_measure_span` (runner.py 2845-2860)
  builds plane spans from a cropped centroid in world coordinates, typically
  metres from the origin, so a braced joint gives exactly the failing shape --
  but no oblique frame has been driven through the runner to watch the arc land
  off the corner. Worth doing before the fix, so there is a picture of it.
- **Effort is not estimated** for any stage.

## Preserving the review comments

**All fourteen review notes added in `a244924` stay verbatim**, including ones
this work does not touch: `clarify comments on how these are interpreted`,
`why do we need as/from_wire`, `no need to suport legacy path`, `TODO DELETE`,
`rename look to normal probably`, `CONTINUE HERE`, and both `what is this?`
notes on `projected_form`.

Only three are earned by this work, and only in the stage that resolves them:

| Note | Delete when |
| --- | --- |
| module docstring `TODO change this class to use rule.py type...` | end of Stage 2 |
| `# TODO these all get replaced by rule.py` x2 (247, 254) | Stage 1, with those functions |
| `# TODO use a real type for geometry. Why does this file have no types omg` (204) | Stage 3 only |

The long explanatory docstrings -- the "THE VIEWER HAS A COPY" notes, the
`distance_anchors` rules, the `_canonicalise_anchors` note -- are load-bearing
and stay. Stage 1 should not reword one, so the diff reads as pure mechanism.

One exception: the `_plane_crossing` comment at 401-404 describes behaviour the
code does not have (finding 1). It gets corrected, not preserved.

## Verification

```bash
source .venv/bin/activate && python3 -m pytest tests/ -v   # per AGENTS.md
uv run ty check                                            # 70 -> ~48 after Stage 1
cd kigumi && npx jest && npm run test:ext:initial
```

The node parity tests in `test_measurement_kinds.py` (`TestTheViewerAgrees`) are
the real gate: they run `projected_form`, `solid_form`, `measureValue` and the
kind tables against the JS across a case matrix that deliberately straddles the
epsilons. Green through Stage 1 means the swap was exact.

Baseline, recorded 2026-09-20 on `main` at `a244924`:

- `tests/test_measurement_{anchors,kinds,plane,end_to_end}.py` + `test_layout.py`:
  **191 passed**
- `uv run ty check`: **70 diagnostics**, 22 in `drawing.py`
- `kigumi/__tests__/measurements.test.js`: 115 tests

After Stage 0 + Stage 1:

- full `pytest tests/`: **1927 passed, 5 skipped**
- `npx jest`: **1257 passed**; `test:ext:initial` 5 passing; `test:ext:complex`
  10 passing
- `uv run ty check`: **62 diagnostics**, 14 in `drawing.py`

The 14 that remain in `drawing.py` are all one thing, and it is not vector
typing: `MeasureSpan.direction` and `.normal` are `Optional` by design -- a
point has neither -- and the helpers are called under an `is_line`/`is_plane`
guard that ty cannot see through. The Stage 1 prediction of "70 -> 48" was
wrong because it assumed all 22 were vector typing; only 8 were. Fixing the
remaining 14 wants narrowing accessors on `MeasureSpan`, which belongs with
Stage 2.

Behaviour was also checked directly against the pre-migration file, imported
side by side: `projected_form`/`solid_form` (90 direction components),
the kind tables and `pair_separation` (188 values), and `distance_anchors`
(120,000 components over 20,000 random span pairs) are **bit-identical**. The
only thing that changed is `angle_rays` on plane-plane pairs, which is the bug.

## Appendix: why two copies at all

The duplication between `drawing.py` and `measurements.js` is historical, not
principled. Two of the three tiers are drawn correctly:

| Tier | Lives in | Why |
| --- | --- | --- |
| Needs the **CSG** -- `distance_anchors`, `angle_rays`, `MeasureSpan` and helpers | Python only | The viewer has a mesh, not the solid. |
| Needs the **page** -- `dimensionLayout`, `angleArcPoints`, `offsetForPointer` | JS only | Screen pixels and SVG. |
| Classify and evaluate -- `projected_form`, `solid_form`, `solidKinds`, the kinds table, `measureValue`, the degenerate check, the three epsilons | **Both** | the ~9 functions in question |

The stated reason is that the viewer projects every frame and cannot ask python
each time. The per-frame part is true: `renderMeasurements()` (viewer-app.js:6724)
is called from `renderViewports()` (2109), inside the `requestAnimationFrame`
loop (1908).

But `measurementStatus` (measurements.js:666) does this:

```js
const look = plane && plane.normal ? plane.normal : axes.look;
```

It prefers the measurement's own plane normal over the live camera, so for any
measurement carrying a plane the number is **camera-independent**. The codebase
says so twice -- viewer-app.js:6779 ("the number does not move when the camera
does, only the picture of it") and `measuring-states.md`. The 60fps pipeline
recomputes a constant. The only genuinely camera-dependent part is
`planeMatchesView` -- one dot product.

The dates:

```
2026-09-01  ae7c183  Decide what a pair of features can be measured as   <- the JS copy
2026-09-12  daf8e4a  Give a measurement the plane it is taken on         <- value becomes camera-independent
2026-09-14  d6a831d  One verdict, and a click that reaches the feature   <- python answers per hover
```

The copy predates both of the changes that undercut it, by 11 and 13 days.
`_pick_verdict` already returns `kinds`, `plane`, `anchors` and `angle` per
hover, and the viewer stores them wholesale (viewer-app.js:3819) -- then
recomputes the value beside them. `measuring-states.md` already states the rule
this breaks: "The preview is drawn from the verdict, never from a second
calculation."

### Step A -- done

`_resolve_measurement` now sends a `settled` block with every measurement:
the kind it settled on, what it comes to, the kinds it admits, the space, the
reason there is nothing to draw, and the two forms. `_pick_placement` sends the
same block with the verdict, so the preview reads it too. `measurementStatus`
asks its one camera question -- `planeMatchesView` -- and then returns what it
was given.

So the number the viewer draws is now the number python computed, for every
measurement that gets drawn and for the preview. That closes the rule
`measuring-states.md` already states and only half had: "the preview is drawn
from the verdict, never from a second calculation" was true of the picture and
not of the number beside it.

Verified on the fixture: python's `settled` and the viewer's own derivation
agree on value, kind and reason for all four measurements, and the kinds the
change-kind menu offers are identical either way.

### Step B -- not done

**Nothing was deleted from measurements.js.** The evaluation path is still
there, reached whenever a measurement arrives without a `settled` block, and
that is a real case rather than mere caution: `settled` is set inside the
`placeable` branch, so a measurement with no plane to be taken on -- no written
one and no viewport camera -- has no answer python could compute, because
classifying the ends needs a direction to look along.

So the *correctness* win is banked (one derivation, not two) and the
*maintenance* win is not (the second copy still exists). Retiring it needs that
last case answered, one way or the other:

- have the viewer refuse an un-placeable measurement outright rather than
  evaluating it, which is arguably what "it could not be placed" already means; or
- have python answer it, which means deciding what a measurement with no plane
  comes to -- possibly "nothing", which is the same thing said in the other place.

Only once that is settled can `projectedForm`, `solidForm`, `availableKinds`,
`solidKinds`, `solidParallel`, `measureValue`, `projectedSeparation` and the
three epsilons come out of measurements.js, along with the ~8 `describe` blocks
covering them.

This is **not** a performance problem -- a few dot products per measurement per
frame is nothing. The cost is maintenance, and it is why `drawing.py` is written
in tuples at all. Shrinking the mirror drops the functions that must stay
bit-compatible with JS from nine to about one, which makes Stages 2 and 3
markedly cheaper.

Cost to weigh: `kigumi/__tests__/measurements.test.js` has 115 tests across 22
`describe` blocks, and roughly eight of those blocks cover the mirrored
functions. Shrinking the JS surface retires them.
