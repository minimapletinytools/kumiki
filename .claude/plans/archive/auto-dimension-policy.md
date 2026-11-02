# Auto dimensioning: a policy for picking the next measurement

**Status:** built, simplified, in `kumiki/drawings/auto_dimensioning.py`: `auto_dimension`, `Policy`
(`prefer`, `rules` with fallback), criteria `from_reference`, `perfect_over_rough`, `from_solved`,
`shortest`, and `plane_pair_candidates`. Default is reference-first, as a preference, and a
timber's own references only. Not yet: `baseline`, the view criteria, `visible_in_view`, a policy on
`Drawing`. The proposal as written follows.

## What exists today

The picking loop lives in the experiment pattern `patterns/structures/my_cute_frame_drawing_test.py`,
not in kumiki. The solver (`kumiki/drawings/feature_solving.py`, `dof_solver.py`) only reports what is
still unknown; it never chooses.

- Candidates: every perpendicular dimension between two parallel faces seen edge-on, in the top and
  front views.
- Eligible: a candidate whose new information lies entirely in what is still unsolved.
- Choice: one hard-coded line, `score = (not anchored_on_something_solved, length)` -- prefer a
  dimension from a face already solved, then the shortest.
- Reference features play no part, which is why it doesn't pick from reference faces.

Each candidate is one measurement, so each pick removes exactly one unknown. "Fewest unknowns left"
always ties; the ordering is what decides. So the ordering is where a policy belongs.

## Proposal

### 1. Move the loop into kumiki

`kumiki/drawings/auto_dimension.py`:

```python
picks, report = pick_dimensions(candidates, targets, known, carriers, policy=DEFAULT_POLICY)
```

The loop keeps the linear algebra (eligibility, projecting out what's solved after each pick). The
policy only orders and filters what's eligible. The pattern becomes a caller, unchanged in behaviour
with today's rule as its policy.

### 2. A policy is hard rules plus ordered preferences

```python
Policy(
    rules=[visible_in_view],                                             # never broken
    prefer=[from_reference, perfect_over_rough, from_solved, shortest],  # first difference wins
    fallback=True,
)
```

- Each preference scores a candidate given context (what's solved, what's a reference, which views
  are used). Lower is better; compared criterion by criterion, so an earlier preference always beats
  a later one.
- Strict ordering rather than weights: predictable, and every pick can say why it won ("from
  reference ptw.front, then shortest"). That goes in the report, later in the drawing panel.
- "Always" vs "strongly prefer" is the same criterion in `rules` or in `prefer`. A rule can leave
  nothing eligible (a shoulder-to-shoulder distance may not be reachable from a reference face);
  with `fallback=True` the loop relaxes the rule for that one pick and records that it did.

### 3. Criteria to start with

| criterion | prefers |
|---|---|
| `from_reference` | an end that is a reference feature of its timber: a reference face, or either face of a reference edge |
| `from_solved` | an end already solved (today's rule; chains dimensions) |
| `baseline` | an end already used as a starting point by an earlier pick (one datum, not a chain) |
| `perfect_over_rough` | `ptw.*`/`rptw.*` over `rough.*` (the "rough features aren't measured" item) |
| `shortest` / `longest` | dimension length |
| `same_view` / `spread_views` | fewer views, or balance across them |
| `visible_in_view` | both ends visible in the candidate's view (after PR #82; best as a rule) |

Default: `prefer=[from_reference, perfect_over_rough, from_solved, shortest]` -- strongly prefer
references. Move `from_reference` into `rules` for "always".

### 4. Where a policy is set

Per call to begin with. Later on `Drawing` (e.g. `Drawing(auto_dimension=Policy(...))`), so a drawing
written in code says how it wants to be dimensioned.

## Decisions needed

1. Reference faces: hard rule or preference? Suggest preference, or rule with fallback.
2. Whose reference: only the timber's own (a shoulder measured from its own timber's reference face,
   as in square-rule layout -- suggested), or any reference face in the frame?
3. After reference: baseline or chain? Baseline (everything from the reference face) is what a layout
   sheet usually wants, and pairs naturally with reference-first.

## Work, in three PRs

1. Move the loop into kumiki, no change in behaviour.
2. Reference, baseline and perfect-over-rough criteria; rule fallback; the new default.
3. Test on the cute frame that picks start from reference faces where they can.
