# Frame parameters: kill reflection, declare a kiwari

## Status — step 1 done, kiwari not started (2026-09-11)

Design settled in review. **Step 1 (strip the old system) has landed** on
branch `strip-frame-parameters`; steps 2-7 are unstarted. Written against the
joints/patterns subfolder reorg (`3c433f3`), which is in.

*Kiwari* (木割) is the traditional system that sets every member's dimension
from a small set of base numbers. That is what this object is.

---

## What was there (removed in step 1)

Signature reflection, in three places:

* `kumiki/librarian.py:400-800` — `Param`, `RenderParameterDescriptor`,
  `discover_callable_render_parameters`, `resolve_callable_render_parameters`,
  kind inference, coercers, serialiser. Discovery reads `inspect.signature`,
  re-parses the source with `ast` to recover annotation *text* (because
  `Optional[V3]` can't be told from `V3` by the object alone), then **mutates
  `__defaults__`/`__kwdefaults__` in place** to unwrap `Param` wrappers so a
  plain Python call still works.
* `kumiki/patternbook.py:22-45` — `_build_pattern_lambda_signature` fabricates a
  `__signature__` on every pattern lambda. It exists *only* to feed the
  reflection above; nothing else reads it.
* `kigumi/runner.py` — `_resolve_callable_entry_with_render_parameters`,
  `_serialize_render_parameters_for_slot`, and two call sites
  (`resolve_frame_from_module`, `_raise_specific_pattern`).

Kinds: `number | boolean | string | enum | v3`. No V2. Dimensionless — every
length in kumiki is a bare `float` in metres, so nothing anywhere knows whether
a number is a length, an angle, or a count.

**In use:** two `Param(...)` declarations (`n_legged_stool.py`,
`simple_simultaneous_assembly.py`) — and **47 pattern functions** whose trailing
kwargs (`use_round_timbers=False`, `notch_from=NotchFrom.Face`) became UI
controls by accident of having a default.

All of the above is now gone (1263 lines deleted). A pattern lambda takes
exactly one argument, `center`. The two `Param` defaults became plain defaults.
The 47 kwargs are still there as ordinary Python defaults — they simply are not
UI any more, which is the decision recorded under *The 47* below.

Everything awkward above is one mismatch leaking: **a signature is not a
schema.** An explicit declaration deletes all of it, not just some of it.

---

## Decisions

### D1 — One type, named `Kiwari`

Not a values object plus a configuration object. Values are never useful without
the schema — you cannot validate, coerce, or fall back to a default without it,
so two types means every call site carries both and the "do these agree?" check
has to be written and tested.

A `Kiwari` holds declarations, and may also hold bound values. Bare, it reads
its own defaults. `with_values()` / `resolve()` return new ones. Same accessors
either way, so the mismatch error the brief wanted **cannot be constructed** —
there is only ever one schema in the room.

*Cost, stated plainly:* "declared" vs "bound" is a field, not a type, so passing
an unbound one where a bound one was meant reads defaults silently. That is also
the right behaviour for that mistake, which is why it is cheap.

### D2 — The kiwari lives on the `Frame`, declared inside the builder

No module-level `kiwari = ...` global. The declaration is made in the function
body, merged with whatever came in, and handed back out on the frame:

```python
def build_frame(k: Kiwari | None = None) -> Frame:
    k = kiwari(
        count("legs", default=4, minimum=3, about="Number of legs"),
        length("seat_height", default=mm(450)),
        choice("butt_end", TimberEnd, default=TimberEnd.TOP),
    ).resolve(k)

    n = k.count("legs")
    ...
    return Frame.from_joints(joints, name=f"{n}-Legged Stool", kiwari=k)
```

`Frame` is already `@dataclass(frozen=True)`; `kiwari: Optional[Kiwari] = None`
is an additive field. Nothing is global, nothing is mutated, the builder is a
function of its argument, and its output carries everything needed to build it
again. `build_frame()` bare still works — `resolve(None)` gives defaults.

**How the UI gets the schema.** Build once with no overrides; the schema is on
`frame.kiwari`. On an edit, the runner takes the kiwari it already holds,
`with_values({...})` it, and passes that in. `resolve()` inside the builder then
validates those values against a declaration made *fresh on this run* — which is
what makes the edit-the-file-while-open case correct: the new declaration wins,
values for surviving keys carry over, stale keys are reported.

*Cost, stated plainly:* the schema is only knowable by building, so a file that
raises before returning shows no panel. Mitigated where it matters — when a
build fails, **the runner keeps the last good `Kiwari` for the panel**, so a bad
value you just typed is always dialable back. Uncovered case: a file broken on
first open, where no panel would have helped anyway.

*Rejected:* a decorator that hides the two-line ceremony. It would have to read
the declaration off the function to work, which is the reflection system wearing
a hat.

### D3 — Patterns declare on the `Pattern`

```python
Pattern(path="butt_joints/plain_butt_joint", lambda_=..., kiwari=kiwari(...))
```

and the lambda becomes `(center: V3, k: Kiwari) -> Frame | CutCSG`. Center stays
an explicit positional — a pattern can be repositioned, and that is not a
parameter.

The asymmetry with D2 is deliberate: a `Pattern` is a catalogue entry, which is
already a declaration site, and its lambda may return a `CutCSG`, which has
nowhere to hang a kiwari. It is also strictly better here — the schema is
readable without running anything, so a pattern's panel survives a broken
pattern.

`_build_pattern_lambda_signature` deletes outright.

### D4 — Dimensions are declared, because kumiki has no unit type

`inches(4)` returns `0.1016`. A float. Whether that is a length is information
only the author has, so it goes in the declaration — which also gives the typed
accessors something to check.

| declare | accessor | value | UI |
|---|---|---|---|
| `length` | `k.length(key)` | float, metres | dimensioned text box |
| `angle` | `k.angle(key)` | float, radians | dimensioned text box (`deg`/`rad`) |
| `count` | `k.count(key)` | `int` | integer box with steppers |
| `number` | `k.number(key)` | float, dimensionless | plain number box |
| `flag` | `k.flag(key)` | `bool` | checkbox |
| `text` | `k.text(key)` | `str` | text box |
| `choice` | `k.choice(key, TimberEnd)` | enum member | type-to-search dropdown |
| `point2` / `size2` | `k.v2(key)` | `V2` | two dimensioned boxes |
| `point3` | `k.v3(key)` | `V3` | three dimensioned boxes |

The brief's "raise if the key/type/dimension doesn't match" falls out for free:
`k.length("legs")` on a `count` raises at the call site, naming the key, the
declared kind and the requested one. No separate consistency check exists.

Carried over from today because both are in use: **`optional`** (nullable
parameters, the enable-checkbox) and **`minimum`/`maximum`**.

`choice` takes a Python `Enum` class, not strings — kumiki is full of them
(`TimberEnd`, `TimberLongFace`, `NotchFrom`). `(value, label)` pairs go over the
wire; the builder gets the real member back.

### D5 — One parse grammar, two implementations, one fixture

`scalar("1 1/4")` raises today (splits on `/`, chokes on `"1 1"`), and
`scalar("10in")` raises too. Both sides need a real parser: JS to say *as you
type* that a box is bad, Python to be authoritative on load and on the companion
file. Written twice with no pin, the two quietly disagree about `2'6"`.

**Pin them with a shared fixture** — `kigumi/test-fixtures/dimension-parsing.json`,
a table of `input → metres` plus the invalid inputs and their reasons, read by
both pytest and jest. Python is authoritative: where they disagree, the refresh
response corrects the box.

Grammar — closed, no `eval`, no expressions:

```
[sign] [whole] [ws|-] [num/den] unit?
in " ft ' mm cm m yd   shaku 尺  sun 寸  bu 分     (length)
deg ° rad                                          (angle)
2'6"   1-1/4in   1 1/4"                            (compound / mixed)
```

A bare number means **the viewer's current display unit** (mm in metric, inches
in imperial) — what someone typing into a box under a `mm` label expects. The
canonical form is echoed beside the field so it is never ambiguous.

"Formulas not supported yet" holds: a fraction is a literal, not arithmetic.
Nothing user-typed reaches `eval` on the way into a build.

**Round-trip the text.** Every value crosses the wire and lands in the file as
`{"value": 0.0254, "text": "1\""}`. Without the text half, `1"` comes back as
`25mm` on the next load.

### D6 — Companion file, saved sparsely, behind an explicit button

`myframe.py` → `myframe.parameters.json`, beside the source. Checked: the file
watcher (`file-watcher.js:96`) watches only the example file's exact basename, so
a sibling `.json` does not trigger a reload loop. Beside the source rather than
under `.kigumi/` (where drawings go) because parameter choices are something you
want to commit.

```json
{
  "schema_version": 1,
  "values": {
    "seat_height": {"value": 0.5, "text": "500mm"},
    "legs": {"value": 6}
  }
}
```

**Sparse — only what differs from the code default.** If every value is written,
changing a default in `myframe.py` silently does nothing for anyone holding a
companion file, and the bug report is "my edit didn't take".

**Explicit save.** A *save parameters* button in the panel, never an autosave.
It is enabled only when the pending values differ from what is on disk, and it
reports the path it wrote.

**Gate:** hidden when the slot has a `single_pattern_name` (a pattern), and when
the file is not under the workspace root. `discover_search_roots` already labels
roots `workspace | kumiki | dep`. The runner sends `canSave`, so the button's
absence is its decision, not the webview guessing.

**Auto-load** on `load_slot_state`: file values under UI-supplied values
(explicit edits win for the session), both over code defaults.

### D7 — Highlight against the code default

Not against the saved file. If "modified" means "differs from what's saved", the
highlight goes blank the instant you save — exactly when the file starts
mattering. The companion file is shown separately: a header line saying values
were loaded from it, and a *reset to code defaults* action.

Each row therefore needs three values, not two: code default, applied, pending.
The webview tracks applied + pending + drafts today; this makes the default a
first-class thing rather than a `parameter.default` fallback read.

---

## Wire protocol

Same `{schema, applied}` envelope, new descriptor fields:

```jsonc
{
  "schema": [
    {"key": "seat_height", "kind": "length", "about": "…",
     "default": {"value": 0.45, "text": "450mm"},
     "optional": false, "minimum": 0.1, "maximum": 2.0},
    {"key": "butt_end", "kind": "choice",
     "choices": [{"value": "TOP", "label": "Top"}, …],
     "default": {"value": "TOP"}}
  ],
  "applied": {"seat_height": {"value": 0.5, "text": "500mm"}},
  "source": {"companionFile": "myframe.parameters.json",
             "canSave": true, "loadedFromFile": ["seat_height"]},
  "stale": false
}
```

Every value is `{value, text?}` rather than a bare primitive — one shape for
every kind, and the text half is where round-tripping lives. `stale: true` marks
a schema kept from the last good build after a failure (D2), so the panel can
say so.

New command: `save_parameters` (payload `{slot}`) → writes the sparse file,
returns the path.

---

## Staging

Seven steps, each landable and testable on its own.

**1 — strip the old system. DONE.** Deleted the parameter block from
`librarian.py` (and with it the now-unused `inspect`/`textwrap` imports),
`_build_pattern_lambda_signature` from `patternbook.py`, the `Param` re-export
from `kumiki/__init__.py`, `SlotState.render_parameter_schema` /
`applied_render_parameters` and every `renderParameters` field in the runner
protocol, `ViewerParameterPanel` and its app state from `viewer-app.js`, the
session's `renderParameters` plumbing and `refreshWithPanelParameters`, 30 dead
CSS rules and 4 i18n keys. The top-center refresh button survives on
`sourceHasPendingChanges` alone; its three i18n keys moved from
`viewer.frameParams.*` to `viewer.refresh.*`. `#top-controls` is a single
column now that only the settings panel sits in it.

**2 — `Kiwari` in kumiki, nothing wired.** New `kumiki/kiwari.py`: declaration
helpers (`length`, `count`, `angle`, `number`, `flag`, `text`, `choice`,
`point2`, `point3`), the frozen `Kiwari`, typed accessors, `resolve`,
`with_values`, `changed_from_defaults`, validation and error messages. Add
`kiwari: Optional[Kiwari] = None` to `Frame` and thread it through
`Frame.from_joints`. Pure kumiki, no kigumi. Full pytest coverage.

**3 — parsing and formatting.** `parse_length` / `parse_angle` / `format_length`
/ `format_angle` in `kumiki/rule.py` beside `inches`/`mm`; the JS mirror in
`kigumi/webview/dimension-text.js`; the shared fixture; both suites reading it.
(`units.js` + `units.test.js` is the pattern to follow.)

**4 — runner speaks Kiwari.** Add `kiwari=` to `Pattern` and thread it through
the pattern lambdas; teach `resolve_frame_from_module` and
`_raise_specific_pattern` to pass a bound kiwari in and read `frame.kiwari` back
out; put the new envelope on the wire; keep the last good kiwari on build
failure. Step 1 already cleared the ground, so this only adds.

**5 — panel rewrite.** `ViewerParameterPanel` per kind: dimensioned text
control, type-to-search combobox for `choice`, integer steppers for `count`,
per-field invalid state (red border + reason, refresh blocked while anything is
invalid), modified-vs-default highlighting, save button, reset action. New i18n
keys under `viewer.frameParams.*` in both `en.json` and `ja.json`. Pull the
value normalisation out of `viewer-app.js` into a framework-neutral module with
its own jest test — the frontend rules ask for exactly that, and the four
`normalize*RenderParameterValue` functions already sit at file scope waiting to
move.

**6 — companion file.** Path helper, sparse read/write, the gate, the
`save_parameters` command, auto-load merge. Python tests alongside
`test_kigumi_drawings_file.py`, the same shape of problem.

**7 — migrate the callers.** `n_legged_stool.py` and
`simple_simultaneous_assembly.py` are the two real ones, then the 47 accidental
pattern kwargs (below). Update `docs/agent_usage_instructions.md` and
`.github/instructions/authoring.instructions.md`, neither of which documents
parameters at all today.

---

## The 47 accidental parameters

`example_basic_butt_joint(position=None, use_round_timbers=False)` and 46
siblings get a UI checkbox today purely because the kwarg has a default. Killing
reflection drops all of them silently unless each is migrated.

**Decision: migrate the handful that earn a control, drop the rest.** Most are a
single `use_round_timbers` bool, and a variant is already expressible as a second
`Pattern` over a lambda passing `True` — which makes the library's UI more
honest, since a round-timber variant becomes a visible sidebar entry rather than
a hidden toggle. The genuinely useful ones (`notch_from: NotchFrom`) get a
`choice`. The alternative — 47 mechanical diffs keeping a feature nobody asked
for on library examples — answers the question once for all of them instead of
per pattern.

---

## Tests to write

* pytest — declaration, defaults, `resolve` (None / mapping / stale keys /
  dropped keys), `with_values`, every accessor's happy path and its wrong-kind
  raise, unknown-key raise, min/max, optional, enum round-trip.
* pytest — the parse table from the shared fixture, and the formatters.
* jest — the same fixture through the JS parser; the value-normalisation module;
  modified-vs-default comparison.
* pytest — companion file: sparse write, load-merge precedence, gate refuses a
  pattern, gate refuses outside the workspace, unknown key in a stale file.
* pytest — a failed build keeps the previous schema and marks it `stale`.
* `cd kigumi && npx jest && npm run test:ext:initial` per the frontend rules;
  full `test:ext:complex` before merge, since this touches the session protocol.
