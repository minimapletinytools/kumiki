# Where a generated drawing's dimensions go, and what it measures

Proposal, 2026-10-05. Nothing here is built except the probe under `garbage/`.
Follows `patterns/structures/my_cute_frame_drawing_test.py` (the solver) and
`.claude/plans/featuresolving-plan.md` Part 2 E (the generator).

The drawing that comes out of the cute frame test solves the frame correctly and
reads badly. This is about the two halves of that: **where a dimension sits on
the sheet** (placement), and **which dimensions are asked for at all**
(selection). They are separable, and the second is the one that makes the bigger
difference to how the sheet reads.

---

## The diagnosis, with numbers

Ran the real path -- `build_frame_with_drawing()` then
`runner.collect_drawings()` -- and projected every resolved anchor into page
millimetres with the viewport's own camera. Script:
`garbage/dimension_layout_probe.py`. Front viewport (6 dimensions), top
viewport (12):

| | front | top |
| :--- | ---: | ---: |
| dimensions | 6 | 12 |
| distinct values | **1** (90mm six times) | 55, 90, 410 |
| distinct runs (where they are drawn) | **3** | 11, one shared by two |
| labels sitting on the work | **6 of 6** | **12 of 12** |
| labels on top of each other | 1 pair | 0 pairs (but a 410 and a 90 share a midpoint) |

1. **Every dimension takes the same default.** `Measure.placement` is None on all
   18, so `_offsetInPixels` falls to `MEASUREMENT_OFFSET_PX = 26` px
   (viewer-app.js:191, 3757-3767) and `dimensionLayout` offsets along
   `[-run.y, run.x]` -- one side, chosen by the run's direction alone
   (measurements.js:413-451). Nothing knows about anything else on the sheet.
2. **Runs coincide, so dimensions stack.** The front elevation's six 90mm
   dimensions are six different timbers' own thickness -- each a genuinely
   separate unknown, so the solver is right to ask -- and they occupy three
   stations in the run, one of them three times over and one of them twice.
3. **Which side a dimension lands on is an accident.** `dimensionLayout` puts it
   left of the run or right of it purely by which way the run is written, and the
   run's direction comes from the anchor sort order (`Measure.wire_anchors`,
   drawing.py:1106-1126). So the six coincident 90s scatter to *both* sides: two
   land exactly on top of each other and the rest sit 15.6mm apart in pairs,
   which is the 90/90 twin labels in the screenshot and which no reading of the
   drawing explains.
4. **The labels sit on the work.** All 18 label boxes have material under them:
   a member's thickness is dimensioned inside the member, and the frame's clear
   span (410) inside the frame.
5. **Nothing reserves room for them.** `_view_extent` (runner.py:1043-1061) pads
   the model by 1.15 and knows nothing about dimensions. And the overlay is not
   clipped to a viewport (`renderMeasurements`, no clip path anywhere), so a band
   that runs past the rect spills over its neighbour and the page.
6. **There is no lane machinery to build on.** Nothing in the viewer or the
   library does collision, staggering or keep-clear (grep: no `lane`, no
   collision, no text metrics). The one placement freedom a measurement has is
   the single signed offset the drag writes (`measurement-spec.md`:315).
7. **The selection is a cover, not a drawing.** Greedy scores each candidate by
   `(neither anchor solved, shortest length)` (the test, `solve_cute_frame`), so
   it prefers short member-to-member gaps and reaches the overall dimensions
   last, if at all: 590, 600 and 90 (the group's own size) never appear, and the
   shop numbers that matter for this frame -- tenon 80 wide by 75 long, mortise
   81 deep, peg 15 with a 2mm draw-bore offset -- are not reachable, see 8.
8. **The target set is 8 of the 24 required features.** `planning_features`
   (kumiki/drawings/required_features.py:79-84) keeps the perfect-timber-within
   prism's faces plus the joints' shoulder planes. On the Back Cross that is 4
   PTW faces, 2 centerplanes and 2 shoulders; the joint's own faces
   (`tenon_front`, `tenon_back`, `tenon_bot`), the peg hole's axis and its
   curved sides are all *required* by `required_features` and all excluded from
   the drawing. So the only numbers a generator can produce are face-to-face
   distances between prisms and shoulders -- which is exactly the 55/90/410 set
   above.
9. **The pair labels read as nonsense.** `Back Cross:shoulder ->
   Back Cross:shoulder 410mm` is the cross's shoulder-to-shoulder length
   (500 - 90), a real dimension, drawn with two identical feature names.

---

## Part 1: placing a dimension

### What a placer has to decide

`dimensionLayout` gives a dimension exactly one degree of freedom: a signed
distance along the in-plane perpendicular of its run. Side and distance are the
same number. So a placer's whole output, per dimension, is **one scalar** -- and
that scalar already exists on the wire (`placement.offset`, world units), already
survives a save, and is deliberately not part of a measurement's identity
(drawing.py:1092-1094). No wire change is needed for any of Part 1.

The scale that turns sheet millimetres into world millimetres is known in python:
the camera's half-height `extent` maps onto half the viewport's height on the
page, so

```
world_per_sheet_mm = extent / (rect.height * page.height / 2)
```

For the cute frame's top view: 345mm half-height over 74.25mm half-sheet, so
4.65 world mm per sheet mm. A lane pitch of 8mm on the sheet is 37mm in the
world. That is why the placer can work in sheet millimetres -- the page is the
truth for a printed drawing -- and emit world offsets.

A world offset stays the sheet distance it was computed as, because a drawing's
orthographic views do not zoom: the camera's `orbitDist` comes from the wire's
`extent` (viewer-app.js:177-187, 6737-6747), the wheel zooms the page rather than
any viewport (1778-1790), and page zoom scales the page rect the offsets are
measured against along with the geometry. The one thing that is not in sheet
units is text: labels are 11px in CSS (`viewer.css`:356-364) and nothing anywhere
measures a string, so a python placer has to carry a text size of its own
(say 3.6mm cap height) to size a label box. That is the only number in Part 1
that is a guess, and it is a constant to tune rather than a design decision.

### Step 1: bands and lanes (deterministic, python, no schema change)

1. **Project.** For a viewport, project each drawn timber's oriented box corners
   to sheet millimetres with the viewport's own axes and extent. The union of
   their hulls is *the work*; the viewport rect less a margin is *the drawing
   area*. (The corner code already exists: runner.py:1000-1022, 1267.)
2. **Runs.** Each dimension's drawn segment is the two resolved anchors
   projected. The runner resolves them already (`_resolve_measurement`); a placer
   in python reads the same pair, so what is measured and what is placed cannot
   disagree.
3. **Families.** Group dimensions by run direction (mod 180 degrees). Everything
   after this is per family: a family shares an axis, so lanes and label
   collisions are one-dimensional within it.
4. **Candidate bands.** For side in `{+1, -1}` and lane in `0..k`: offset =
   `side * (base + lane * pitch)`. The band is the run segment offset by that,
   with the label box at its midpoint.
5. **Cost.** Material under the dimension line and the label (a coarse grid over
   the work, or sampling); overlap with labels already placed; crossings with
   other dimension lines; distance from the run; leaving the drawing area. The
   first term is what puts dimensions *outside the outline* when the interior is
   busy, and *in the opening* when it is not -- a 410 between two members wants
   the opening, a member's thickness wants the outside.
6. **Order.** Longest run first, so the overall dimensions claim the outer lanes
   and the short ones fill in beside them -- which is also the drafting
   convention (the smallest dimension nearest the work, the largest outside it).
7. **Output.** One `MeasurementPlacement(offset=...)` per dimension, in world
   units, plus the sheet-millimetre band the view now needs (step 2).

What the probe's rough packer does on the real runs, with a fixed 9mm base and
8mm pitch:

| | labels on the work | labels on each other |
| :--- | :--- | :--- |
| front, today | 6 of 6 | 1 pair |
| front, packed | 3 of 6 | 0 |
| top, today | 12 of 12 | 0 |
| top, packed | 3 of 12 | 0 |

The three left in each view are member-thickness dimensions whose every
candidate band still touches the member: to get those off the work the band has
to clear the whole part, and there has to be room outside it -- which is step 2,
and the probe has neither. It is a probe, not a library: label boxes only, coarse
material sampling, fixed pitch.

### Step 2: reserve the room, in the camera fit

A band outside the outline eats the 15% padding and then spills, unclipped, into
the next viewport. So the fit has to know about the band. `extent` is computed at
three places (`_world_elevation_viewports`:1501, `_long_face_viewports`:1475,
`build_default_drawing_for_debugging`:1119) and each is a pure function of the
model's half-size, the axes and the viewport aspect.

The band is wanted in sheet millimetres, and a sheet millimetre is itself a
function of `extent`, so the two are a fixed point -- which has a closed form:

```
extent = needed * padding / (1 - band_mm / (rect.height * page.height * 1000 / 2))
```

Two passes would do as well and is obviously convergent. Either way the order
becomes: frame the model, place the dimensions, grow the extent by the band (and
re-place, since the scale moved a little). A viewport whose band does not fit at
all should say so rather than quietly overlap its neighbour.

### Step 3: what to do about coincident runs

Two dimensions on the same line are a placement problem (stack them) and a
selection problem (why are there two?). Placement can only stack; Part 2 is where
they stop being asked for. Until then, a placer should treat exactly coincident
runs as one lane and let the labels overlap only if it must.

### Should `MeasurementPlacement` grow `lane` and `side`?

Not yet. World offsets work today, need no wire or viewer change, and are
testable offline -- the probe is the proof. The case for a lane index instead is
page zoom (the wheel's, not a viewport's, which cannot zoom at all): zooming the
page out shrinks the drawing in pixels while the label text stays 11px, so lanes
that were 8mm apart on the sheet thin out until the text touches. That is already
true of a dimension the reader has dragged, so it is a known property rather than
a new problem, and the fallback pass below is the cheaper place to answer it.

If it does become one, the extension points are: `MeasurementPlacement`
(drawing.py:1032-1062) plus `from_wire`; `Measure.wire_anchors` must flip a side,
the way it already negates an offset when it swaps the anchors (drawing.py:1121-1126);
`_serialize_code_measure` is the single code-tier wire point (runner.py:2122);
`placement` sub-keys pass through `frame-view-session.js` untouched, so only
`tests/test_kigumi_drawings_file.py`, `tests/test_measurement_kinds.py:320-341`
and `tests/test_measurement_anchors.py:611` need care.

### A viewer-side fallback, for everything the generator did not place

A reader's own dimensions, and any drawing the generator has not touched, still
land on the default. A small pass in `renderMeasurements` -- group a viewport's
dimensions by direction, and push apart any two whose label boxes overlap -- would
catch those. It is a fallback, not the mechanism: python's offset wins when it
is there, and the viewer stays a renderer of decisions rather than a maker of
them. The place is the loop that walks one viewport's measurements
(viewer-app.js:6790-6793), which already rebuilds the whole overlay every frame
(6779); `dimensionLayout` has exactly one production caller (7001), so a lane
resolved there needs no new plumbing. The one thing the viewer has that python
does not is real text metrics -- the label is a plain 11px `<text>` and nothing
measures it today, so a pass there could size boxes exactly where a python
placer has to assume them.

---

## Part 2: what gets measured

### The idea

Today the picked dimensions *are* the solving steps, chosen one at a time for
what they add to the known rows. That is why the sheet reads like a debug dump.
Split it:

- **Solve**: the greedy already covers every required feature's degrees of
  freedom (`remaining(...) == 0` is the test), and that is its job.
- **Voice**: then decide how to *say* it, which is free to be conventional --
  overall dimensions, datums, chains, notes -- as long as the result still covers
  the same degrees of freedom. The rank test already exists to check that
  (`kumiki/drawings/dof_solver.remaining`), so a voicing pass can rewrite a set
  and refuse its own output if it stopped solving anything.

### Step 1: voicing, with what is drawable today

1. **Anchor the sheet with the group's overall dimensions**, one per axis,
   outermost lane: 590 wide, 600 long, 90 thick for this frame. They are the
   first thing read and the last thing picked today.
2. **Dimension from a datum, not to the neighbour.** A timber's reference face or
   end is what a maker measures from; member-to-member gaps leave the reader
   adding up. The model already has the notion and nothing reads it:
   `TimberTicket.reference_features` is an ordered, author-declared list of what
   the timber is measured from, with `primary_reference_edge()` picking the first
   line in it (ticket.py:293-336; zero consumers, and empty on the cute frame
   because it uses bare string tickets).
3. **Collapse coincident runs.** Six 90mm thicknesses on one line are one drawn
   dimension plus a note -- the model keeps all six (they are six unknowns), the
   sheet says it once. That needs a note: a text at a place on a viewport, which
   drawings do not have yet (see `.claude/plans/drawing-borders-and-info-panels.md`
   for the panel side of the same gap).
4. **Never print the same feature name twice.** `shoulder -> shoulder` should read
   by owner ("Back Cross shoulder to Left Side shoulder"), or better, pick the
   reference face of the other member so it is a datum dimension.
5. **Prefer anchors that are visible in the view they are drawn in** -- on the
   projected outline, with a real extent -- so the witness lines land on a drawn
   line rather than on a plane hidden behind another member. Slivers (a chamfer,
   a peg hole's edge) should never win a lane.
6. **Rewrite each family into a chain or a baseline** where that says the same
   thing: consecutive planes in a stack, or every plane from the datum. Check the
   rewrite with `remaining`, and fall back to the original pick where the rewrite
   would leave a degree of freedom unsolved.
7. **Spread the families over the views.** The right elevation is empty, and the
   front and top carry everything. A direction family belongs in the elevation
   that is edge-on to it and least crowded -- which is a placement input, so this
   belongs with Part 1.

### Step 2: richer targets, once drawings can reference the perfect tree

The numbers a shop drawing of this frame is actually about are the joint's:
tenon 80 wide, 75 long, mortise 81 deep, peg 15, draw-bore 2. Every one of them
is on a feature `required_features` already finds (`tenon_front`, `tenon_back`,
`tenon_bot`, `peg_hole_axis`, the mortise walls) and `planning_features` throws
away. Two things have to happen first:

- **Drawings and measuring move to the perfect tree.** `find_feature` and
  `timber_body_csg` still look up the rough body, which is why the test file has
  the `_drawable` ptw-to-rough mapping at all. This is already the last item on
  `featuresolving-plan.md`'s Left list.
- **`planning_features` keeps joint features**, not just the prism and the
  shoulders -- and probably wants a reason to keep *some* of them and not others
  (a rough relief is not a surface, which `FeaturePurpose.ROUGH_RELIEF` already
  says and nothing reads).

Then the long game: **let the joint say what is worth dimensioning.** A joint
knows that its tenon's width and length are the numbers a maker wants; the
planner is guessing. The hooks are already in the model, unset:

- `FeatureMarkingSpec.mark_relative_to` is documented as "names the feature a
  dimension should be measured from, which is how a drawing says '38mm from the
  shoulder' rather than giving an absolute position" (cutcsg.py:402-415). Nothing
  sets it, nothing reads it: it is the datum dimension, declared once, in the
  code that knows.
- `FeatureMarkingStatus.ALWAYS_MARK` / `NEVER_MARK` is carried on every feature
  and *is* read (`required_features`, Reason.MARKED), but only tests ever set it.
- `FeaturePurpose` has three members, one of them (`ROUGH_RELIEF`) never set, and
  only six joint modules set `SHOULDER` at all -- so a picker that insists on a
  purpose finds nothing on any other joint.
- `required_features` never yields a declared arris or any derived feature, so
  `shoulder×ptw.right` -- literally the shoulder's visible outline on the timber
  face, and the thing a witness line wants to land on -- cannot be a target
  today. That is an extension there, not a new mechanism.

Between them these are the "declare it where it is known" path, which beats a
scorer guessing from names.

### Step 3: more kinds of dimension

`kinds_for` already offers horizontal and vertical distances between two points
and angles between features; the generator only ever builds projected
perpendicular distances between parallel planes (`_candidates` in the test).
Peg centres, mortise offsets from an arris, and a shoulder's angle off square all
want the other kinds, and point and line anchors are what the wire carries
anyway.

---

## Where the code would go

- **`kumiki/drawings/dimension_layout.py`** (new): sheet-space packing. Page,
  rect, runs, work outlines in, placements and required margins out. Same split
  as `layout.py` -- it decides where things go and knows nothing about timbers.
- **`kumiki/drawings/generator.py`** (new, the test's solver pulled out and
  grown): candidates from `kinds_for`, coverage by `remaining`, voicing, and the
  view assignment per family. `featuresolving-plan.md` Part 2 E is the plan for
  this already.
- **The runner** calls the layout where the viewports are built, because that is
  where `extent` is known and where the band has to be reserved
  (`_world_elevation_viewports`, `_long_face_viewports`); `_attach_measurements`
  is the place that has both the scene cameras and the resolved measurements, if
  the layout would rather run after the fact.

## Tests

- `dimension_layout`: two parallel dimensions 4mm apart get different lanes; a
  dimension whose run is inside an opening stays there; one whose only free band
  is outside lands outside; the same input gives the same output.
- voicing: the cute frame's six thickness dimensions collapse to one drawn
  dimension plus a note, and the rewritten set still leaves `remaining == 0`.
- `runner`: the extent grows by the band the layout asks for
  (`tests/test_kigumi_debug_drawing.py` pins the camera today).
- a golden table of the cute frame's per-viewport lanes, so the sheet's look is
  pinned the way `tests/test_layout.py` pins rects.
- nothing above needs a wire change, so the anchors, kinds and drawings-file
  suites should not move.

## Open questions

- **Notes.** Collapsing repeated dimensions needs somewhere for "×6" or "TYP" to
  live. A small note type on a viewport, or a suppressed dimension that keeps a
  label? The borders plan wants panels on the same sheet, so this is worth
  deciding once.
- **How far may a dimension move** before it reads as belonging to the
  neighbouring view? A hard rule (inside the rect) is easy; a taste rule is not.
- **May a dimension line cross the work?** Witness lines may cross other
  witness lines, and standard practice allows a dimension line to cross the
  outline when it must. The packer's cost needs a decision, not a default.
