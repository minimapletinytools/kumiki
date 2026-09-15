# Selection and measuring: every state, and what it does

Companion to `measurement-spec.md`. That says what measurements ARE; this says
what the viewer is doing at any moment while one is being made, and what each
input does from there.

It exists because of a failure pattern. Nine of the bugs on this feature were
not wrong rules — every rule read correctly on its own — but two places
answering the same question differently, or one place answering it with an input
the other did not have. A state nobody wrote down is a state nobody checks.

Sections 1–6 are **what the code does today**. Section 7 is the design being
moved to, and section 8 is how.

## 1. The state is four things, not one

They are independent, and nearly every bug has come from code that reads one and
assumes another.

| Axis | Values | Owned by |
| --- | --- | --- |
| **Space** | `projected` (a sheet) / `3d` (the solid) | the scene: a declared viewport camera means a sheet |
| **Draft** | `IDLE` / `HOLDING` / `PENDING` | `measure-draft.js` |
| **Selection** | timber set, `csgFocus`, measurement marks | `selection-store.js` |
| **Pointer** | nothing / timber / feature, and the pair's verdict | the runner, via hover |

**Space is not the camera.** A drawing shown in perspective still projects onto
its sheet. Only the 3D view has no sheet. Taking "not orthographic" to mean
"solid" is a mistake already made once and caught by a test.

**A 3D measurement still has a plane.** No sheet does not mean no plane. Every
measurement carries its own, and for one created by hand that plane is derived
partly from where the camera was standing when it was made. What the solid does
*not* need is a look vector to decide **what a pair admits** — a face is a plane
from anywhere. The plane still matters afterwards, for placement and for
drawing, and it is fixed at creation so the value cannot drift when the reader
orbits. Two separate questions; only the first is camera-free.

**The draft is not the selection.** The held first end is *held*, not selected —
picking the second end moves the focus off it, and it has to survive that.

## 2. First selection — choosing what to measure FROM

Before anything is held. Measuring is entered explicitly (the button, or the
right-click menu), never by a click meaning something different here.

| State | Click on a timber | Click on empty space | Escape | "Measure from" |
| --- | --- | --- | --- | --- |
| **3D, nothing selected** | selects the timber | — | clears selection | unavailable |
| **3D, timber selected** | drills into it (`csg`) | clears selection | drops selection | unavailable until a feature is focused |
| **3D, feature focused** | drills again / cycles | clears selection | drops the CSG focus | **available** |
| **In a drawing** | straight to the feature | clears selection | drops the focus, else nothing | **available** once focused |

`canStartMeasurement` needs `csgFocus` **and** a reference **and** geometry. A
cylinder's barrel is selectable and not measurable.

## 3. The fork: reaching a feature at all

This is a real branch in the logic and it belongs at the top, not in a footnote.
It applies to the first selection and the second alike.

| View | What a click on a timber does | Why |
| --- | --- | --- |
| **3D** | **Two clicks.** The first selects the timber; only then does a click drill into it. | A frame is a hundred timbers deep; drilling straight in would mean picking a feature on whatever happened to be nearest. |
| **Drawing** | **One click**, straight to the feature — as though every timber were already selected. | A sheet is what it is about. There is nothing to narrow down. |

`choosePickAction` decides this from `inDrawing`, and hover asks it the same
question so it lights what a click will take. **It does not know a measurement
is being made** — which §7 changes, because the new flow needs the fork to
collapse while an end is held.

## 4. Second selection — choosing what to measure TO

The draft is `HOLDING`. This is where the verdict lives, and where most of the
bugs were.

| Candidate under the pointer | Verdict (`kinds`) | Hover | Click |
| --- | --- | --- | --- |
| Nothing | — | nothing lit | clears selection |
| A timber, not drilled into (3D only, §3) | — | timber outline | selects it |
| The feature already held | — | lit | **refused** `same-feature` |
| A feature nobody declared | — | lit | **refused** `no-reference` |
| A barrel, a lofted side | — | lit | **refused** `not-measurable` |
| A pair this space admits nothing for | `[]` | **red** | **refused** `no-kind` |
| A measurable pair | `[kind, …]` | green | → `PENDING` |

**`null` and `[]` are different and both are read.** `null` means no measurement
is being made; `[]` means this pair cannot be finished from here. Collapsing
them is how a red hover became a click that was accepted and drew nothing.

**What is drawn red is what the click refuses.** The hover colour and the click
decision must come from one judgement, not two.

## 5. Third selection, and the transitions today

The draft is `PENDING`. A further pick **replaces the second end** and is judged
against the still-held first one. Everything in §4 applies unchanged.

This is the row the code kept getting wrong, because `PENDING` looks like a
finished state and is not: the held end must still be offered to the runner, and
the verdict must be recomputed and the hover re-asked, the pointer not having
moved.

| From | Input | To | Also |
| --- | --- | --- | --- |
| `IDLE` | "Measure from" | `HOLDING` | undo suspended; held end drawn |
| `HOLDING` | pick a valid second | `PENDING` | preview drawn from pairwise anchors |
| `HOLDING` | pick an invalid second | `HOLDING` | refusal reported; nothing changes |
| `HOLDING` | Escape | `IDLE` | undo resumed; held end cleared |
| `PENDING` | pick another | `PENDING` | second end replaced |
| `PENDING` | Escape | `HOLDING` | one end at a time |
| `PENDING` | Confirm | `IDLE` | written, one undo entry pushed |
| any | change scene / reload | `IDLE` | undo resumed, purged on reload |

**Every path out of the draft must un-suspend undo.** A path that forgets leaves
undo silently dead.

## 6. Where the verdict is decided — the actual problem

One question, "can these two be measured, and how", is answered in five places:

| # | Place | Input it uses |
| --- | --- | --- |
| 1 | `_best_matching_candidate` | held geometry, look, space |
| 2 | `_kinds_for_pick` | held geometry, look, space |
| 3 | hover colour (`isRefused`) | the runner's answer |
| 4 | `_measurePicked` refusal | the runner's answer |
| 5 | `measurementStatus` | the measurement's own kind and plane |

3 and 4 now read one answer. **1, 2 and 5 each derive it again**, and every
disagreement between them has been a shipped bug:

- 1 and 2 disagreeing → the offered feature is one the pick then refuses
- 2 and 5 disagreeing → the pick is accepted and nothing is ever drawn
- 2 asking without the held end → everything after the first pair is misjudged
- 5 asking in the wrong space → a measurement reports itself broken

**Agreed direction.** The pick response carries **one verdict object** — the
kinds, the plane, the pairwise anchors, and the reason when there are none — and
1, 3 and 4 read exactly that. 5 is the one legitimate second implementation,
because it judges a *written* measurement that no pick is happening for; it
should be reachable from the same rule module with the measurement's own kind
and plane as input, and be tested against the runner on the same cases, as
`projected_form` and `solid_form` already are.

## 7. Where this is going: the preview follows the pointer

**New model.** Select the first feature. As the pointer moves over a candidate
second feature, *the measurement it would make is drawn*. Clicking writes it and
clears the selection. There is no pending measurement and no confirm button.

| From | Input | To | Also |
| --- | --- | --- | --- |
| `IDLE` | "Measure from" | `HOLDING` | undo suspended; held end drawn |
| `HOLDING` | hover a measurable candidate | `HOLDING` | **the measurement is drawn, where it will land** |
| `HOLDING` | hover anything else | `HOLDING` | lit, red if refused; no preview |
| `HOLDING` | click a measurable candidate | `IDLE` | **written**; selection cleared; undo resumed; one entry pushed |
| `HOLDING` | click anything else | `HOLDING` | refusal reported |
| `HOLDING` | Escape | `IDLE` | undo resumed; held end cleared |

**Why it is better.** `PENDING` existed so you could look at a measurement
before committing to it. But looking at it is what hovering already does, so
`PENDING` was a second way to see the same thing, with its own state to keep
consistent — and that state is where nearly every remaining bug lives. Removing
it removes the state, the replace-the-second-end path, the two-level Escape, and
the confirm button.

**Why the architecture barely moves.** The hover answer *already* carries the
kinds, the plane and the pairwise anchors — `_anchors_for_pick` computes them on
every hover today, precisely so the preview would sit where the result will.
Today that answer is thrown away until a click turns it into `PENDING`. In the
new model it is simply drawn. **This is §6.** The verdict object becomes the
single input to the highlight colour, the preview and the click, which is the
consolidation and the new interaction at the same time.

**What it costs, and what to decide:**

- **The kind cannot be chosen before writing.** It is written as the first kind
  the pair admits and changed afterwards on the written measurement, which is
  already supported. Unchanged from today — the confirm button never offered a
  choice either.
- **"Clears the selection" makes the kind dropdown one click further away**,
  since that dropdown hangs off the focused measurement. The measurement panel
  still lists it. Flagged as a decision, not a blocker; the alternative is to
  leave the new measurement focused.
- **Escape becomes one level.** The spec's "one end at a time" rule goes with
  `PENDING`; `measurement-spec.md` needs that paragraph rewritten.
- **The fork in §3 must collapse while holding.** In 3D, hovering a feature on
  an unselected timber returns `select`, not `csg` — so no preview would appear
  until you clicked to select that timber. Cross-timber measurements are the
  common case, so while an end is held, 3D must drill straight to features the
  way a drawing does.
- **Preview latency** is whatever the hover settle is. It is already what
  governs the highlight, so it will feel the same.

## 8. The plan

**Phase 1 — one verdict object (§6).** The runner returns
`verdict: {kinds, plane, anchors, reason}` from both the hover and the click.
`_best_matching_candidate` and `_kinds_for_pick` derive it once, together; the
hover colour and the click refusal read it rather than re-deriving. Add the
cross-language test pinning `measurementStatus` to the runner on shared cases.
*Lands on its own, fixes the remaining §6 disagreements, no behaviour change.*

**Phase 2 — the fork collapses while measuring (§3, §7).** `choosePickAction`
takes `measuring`; while an end is held, the 3D view drills straight to
features. Extend the existing guard test that every call site passes every
argument — that exact omission has shipped once already.
*Lands on its own; makes the 3D flow usable before anything depends on it.*

**Phase 3 — preview on hover, click writes (§7).** `measure-draft.js` loses
`PENDING`: `IDLE` / `HOLDING`, and `pick()` becomes `confirm(anchor)` returning
what to write. The preview is derived from the hover verdict rather than from
draft state; `_pendingKinds` and `_pendingMeasurementForDisplay` go. The click
writes, clears the selection, resumes undo and pushes one entry. The selection
panel keeps "Measure from" and loses "Confirm".
*The behaviour change, once the two things it relies on are in.*

**Phase 4 — settle up.** Rewrite the Escape and pending paragraphs in
`measurement-spec.md`. Retest the angle/distance kind stickiness — Phase 1
should remove its cause. Then the deferred items: angle placement, and faces
carrying corners rather than an AABB.

Phases 1 and 2 are independent of each other and both independent of 3, so they
can land in either order; 3 wants both.

## 9. Known open

- **Kind sticks when the second end changes between an angle pair and a distance
  pair.** Reported against the 3D view, seen in a drawing too. `_pendingKinds` is
  replaced on every accepted pick and the SVG overlay is rebuilt each frame, so
  neither holds the old kind. The likely mechanism is §6 case "2 and 5
  disagreeing": `measurementStatus` recomputes `available` using the
  **measurement's plane normal** as the look, while the runner computed `kinds`
  using the **camera's** look. Where those differ the viewer rejects the
  runner's kind as `kind-unavailable` and draws nothing — leaving whatever was
  last drawn to read as "stuck". Phase 1 removes the cause; retest there.
- **Angle placement** is deferred: an angle uses no anchor positions, and where
  it should sit is its own question.
- **Faces carry an AABB, not corners**, so a rotated prism's face extent is
  larger than the face.
