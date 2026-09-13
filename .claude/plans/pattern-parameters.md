# Putting the patterns' parameters back

## Status — proposal, nothing built (2026-09-11)

Follow-up to the kiwari refactor (PR #17, merged as `47ef2fe`). That replaced
signature reflection with declared parameters and migrated the two frames that
had them, but left the library patterns with their controls gone. This is how
they come back.

Scope is only the patterns that **had** parameters. Everything else stays as it
is.

---

## What is actually missing

Measured by running the old discovery against the pre-refactor tree, then
checking each against what the sidebar can still reach.

**34 patterns exposed controls. 15 of those settings are still reachable**,
because a sibling `Pattern` renders the other way already (`mortise_and_tenon/
basic_face_aligned` and `…_round_timbers` are two entries). Those need nothing.

What is left divides into three, and only the first two are worth doing:

### A — ten visible patterns, twelve boolean settings

| pattern | setting |
|---|---|
| `basic_joints/basic_butt_joint` | `use_round_timbers` |
| `basic_joints/basic_mortise_and_tenon` | `use_round_timber`, `use_peg` |
| `basic_joints/basic_wedged_half_dovetail_mortise_and_tenon` | `use_round_timbers`, `use_wedge` |
| `butt_joints/cut_dropin_dovetail_butt_joint_on_face_aligned_timbers` | `use_round_timbers` |
| `butt_joints/plain_butt_joint/plain_butt_joint` | `use_round_timbers` |
| `butt_joints/plain_butt_joint/plain_butt_joint_3d` | `use_round_timbers` |
| `butt_joints/tongue_and_fork/…_90`, `…_angled`, `…_angled_inset` | `use_round_timbers` |
| `butt_joints/wedged_half_dovetail_mortise_and_tenon` | `use_round_timbers` |

Ten of the twelve are the *same question asked of ten different joints*: show
this joint cut on round stock. That is the shape the answer should take.

### B — two patterns that lost real design parameters

* **`board_joints/board_in_grooved_frame`** — `frame_height` (a length),
  `board_orientation` (vertical/horizontal), `n_boards` (a count). A small
  parametric design, and the one pattern here that genuinely wants a kiwari.
* **`butt_joints/mortise_and_tenon/joint_plane_aligned_notched_2sided`** —
  `notch_from`, a two-member enum. See the bug below before touching it.

### C — seven `relief/butt_arrangement/*` patterns

All seven are tagged `'poop'`, so they never appear in the sidebar and their
toggles were unreachable from the UI before this refactor too. **Do nothing.**
If they are ever untagged, they join group A.

---

## Two things found while measuring

**The two notch patterns render the same thing.** The base function's default
is `NotchFrom.Face`, and `…_notched_2sided_from_face` passes `NotchFrom.Face`
explicitly — so both sidebar entries are identical, verified by comparing the
frames they build. The docstring claims "NotchFrom.Shoulder (default)", which
is not true of the code. `Shoulder` was only ever reachable by flipping the old
toggle, and is now reachable nowhere. Whatever else happens here, that is a bug
to fix on its own: either the base pattern defaults to `Shoulder` (making the
pair meaningful), or the second entry goes and `notch_from` becomes a `choice`.

**The old system silently ate a parameter.** `example_board_in_grooved_frame`
has no `position` argument — its first parameter is `frame_width`. The old
`_build_pattern_lambda_signature` dropped the first parameter of every pattern
function on the assumption it was the position, so `frame_width` was never
adjustable and nobody could see why. Declaring parameters makes that class of
thing impossible.

---

## The proposal

### For group A: one shared declaration and a small adapter

Round stock is not ten design decisions, it is one question. Put it in
`patternbook.py` beside the other pattern helpers:

```python
ROUND_STOCK = kiwari(
    round_timbers=kiwari.flag(False, about="Cut the joint on round stock"),
)


def on_round_stock(joint_func, make=make_pattern_from_joint) -> PatternLambda:
    """A pattern lambda for a joint function whose round-stock variant is a kwarg."""
    def pattern_lambda(center, k=None):
        on = ROUND_STOCK.resolve(k).flag("round_timbers")
        return make(lambda: joint_func(use_round_timbers=on))(center)
    return pattern_lambda
```

and each call site becomes one line longer:

```python
Pattern(
    path="butt_joints/plain_butt_joint/plain_butt_joint",
    lambda_=on_round_stock(make_butt_joint_example, make=make_pattern_from_frame),
    kiwari=ROUND_STOCK,
    pattern_type='frame',
),
```

**Why this and not a kiwari per function:** the source functions keep their
plain `use_round_timbers=` kwarg, which is how they are called from Python and
from each other, and ten near-identical declarations do not get written ten
times. The `use_peg` and `use_wedge` pair get the same treatment with their own
one-line declarations — they are the same shape, just not shared.

**The cost, stated plainly:** the declaration is named in two places per
pattern — inside the adapter and on the `Pattern`. They cannot drift silently
(a key on one and not the other warns at resolve time) but they are two places.
The alternative, a factory returning a whole `Pattern`, collapses them into one
at the price of a less obvious call site; worth trying if the double naming
grates once it is written.

### For group B: real declarations, written by hand

Two patterns, two one-off kiwari, no shared machinery — these are genuinely
different designs:

```python
BOARD_IN_FRAME = kiwari(
    frame_width=kiwari.length(inches(24)),
    frame_height=kiwari.length(inches(40)),
    board_orientation=kiwari.choice(BoardOrientation, BoardOrientation.VERTICAL),
    n_boards=kiwari.count(4, minimum=1, maximum=12),
)
```

Note `frame_width` joins them — it was always meant to be adjustable and the
old system hid it. `board_orientation` becomes a real `Enum` rather than the
string `"vertical"`, which is what `choice` wants and what the joint code
should have taken in the first place.

### What not to do

Sibling `Pattern` entries for the ten round-stock variants. It is the form the
15 survivors use and the authoring rules recommend it where seeing both at once
is the point — but here it means ten more sidebar rows showing joints that look
nearly the same, to answer a question that is identical every time. The rule
still stands for genuinely different joints; this is not that.

---

## Staging

1. **The notch bug on its own**, before any parameter work: decide whether the
   pair is two variants or one, fix the stale docstring, and land it as a
   one-line change that is easy to review.
2. **`ROUND_STOCK` and `on_round_stock`** in `patternbook.py`, with tests that a
   pattern declaring it builds differently with the flag on and off.
3. **The ten round-stock call sites**, mechanical once step 2 is in.
4. **`use_peg` and `use_wedge`**, same shape, two call sites.
5. **`board_in_grooved_frame`**, including `frame_width` and an enum for
   orientation.
6. **`notch_from`** as a `choice`, if step 1 left it wanting one.

Steps 1 and 5 are the ones with judgment in them. Steps 3 and 4 are typing.

## Tests

* A pattern that declares a kiwari builds a different frame with the flag on
  than off — the same guard the viewer fixture has, which is what caught three
  dead parameters there.
* Every `Pattern` in the tree still raises at the origin (already covered by
  the pattern-grid path, which builds all of them).
* The notch pair build *different* frames, which today they do not.
