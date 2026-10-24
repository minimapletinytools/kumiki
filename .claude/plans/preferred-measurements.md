# Preferred measurements

Features say what they want to be measured against, and which features make good datums.
Two separate mechanisms: **pairs** (a link between two features) and **datums** (a property of one).

## Pairs: "measure me against that"

- Symmetric: tenon cheeks (`tenon_left ↔ tenon_right`, `tenon_front ↔ tenon_back`), opposite mortise walls.
- One-way: tenon tip → shoulder (`tenon_top`/`tenon_bot → shoulder`).

Declared per feature with the existing (until now unread) `FeatureMarkingSpec.mark_relative_to`,
which names the feature to dimension it from: two features naming each other are a symmetric pair,
one naming the other is one-way. The name resolves to the nearest feature of that name in the
timber's CSG tree, so each tenon's tip finds its own shoulder:

```python
FeatureOverride(prism_face_key(PrismFace.LEFT), "tenon_left", _against(_TENON_FACE, "tenon_right")),
FeatureOverride(prism_face_key(PrismFace.TOP), tenon_tip_name, _against(_TENON_FACE, "shoulder", Datum.AVOID)),
```

Pairs are **preferred, not required**: every pair sits at the same "preferred" level and is picked
only when the solver wants a measurement there anyway. A redundant pair (e.g. tenon thickness once
both cheeks are located) is not forced in.

Solver: a fixed criterion `declared_pairs` ranks a candidate first when its two ends are a declared
pair. It goes after `angles_first`, `angles_from_the_timber` and before `edges_over_faces`
(`faces_to_edges` still moves the result onto edges afterwards).

## Datums: "measure from me"

A new `FeatureProperties` field, separate from `priority` (which is a picking priority):

```python
class Datum(Enum):
    PREFERRED = 0   # shoulder planes
    NEUTRAL = 1     # default
    AVOID = 2       # tenon tips
```

- `shoulder_override` sets `PREFERRED`; tenon tips get `AVOID`.
- Criterion `preferred_datum` ranks candidates by their two ends' datums, **only between candidates
  on the same member** for now, so a shoulder doesn't pull measurements from across the frame.
- The enum may grow later for finer control.

One-way needs no picking state: once `tip ↔ shoulder` is picked the tip's DOF is solved, so nothing
else is measured *to* it; `AVOID` stops it being used as a reference for others (which
`from_solved` would otherwise encourage). One-way = pair + `AVOID` on the dependent end.

## Coincident shoulders

The shoulder is never removed as a feature (`_drop_duplicate_derived` drops derived duplicates
only), but `merge_coincident_planes` lets a coincident timber face share its carrier, and the first
one seen becomes canonical.

- Make `merge_coincident_planes` pick the highest-datum plane as canonical, so the shoulder is the
  representative and the name drawn on the measurement.
- Match pairs through the canonical carrier, so a face coincident with the shoulder counts as the
  shoulder. (Datums need no matching: `preferred_datum` already favours the shoulder's own handle.)

## Status

Done (first PR): shoulder as canonical carrier; `Datum` and `preferred_datum`; `declared_pairs`, with
mortise and tenon declaring its cheeks, tip and mortise walls. The patterns' `_end_datum` skips `AVOID`
faces, so a piece's length isn't measured from a tenon's tip.

Next: declare pairs on the other joints (tongue and fork, dovetails, scarfs, ...).
