# Selection and measuring: every state, and what it does

Companion to `measurement-spec.md`. That says what measurements ARE; this says
what the viewer is doing at any moment while one is being made, and what each
input does from there.

It exists because of a failure pattern. Nine of the bugs on this feature were
not wrong rules — every rule read correctly on its own — but two places
answering the same question differently, or one place answering it with an input
the other did not have. A state nobody wrote down is a state nobody checks.

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

Notes that have bitten:

- In the 3D view a feature on an *unselected* timber takes **two clicks** —
  select, then drill. `choosePickAction` does not know a measurement is being
  made. In a drawing, `inDrawing` goes straight to the feature.
- `canStartMeasurement` needs `csgFocus` **and** a reference **and** geometry. A
  cylinder's barrel is selectable and not measurable.
- Hover must ask `choosePickAction` the same question the click will, or it
  lights something the click will not take.

## 3. Second selection — choosing what to measure TO

The draft is `HOLDING`. This is where the verdict lives, and where most of the
bugs were.

| Candidate under the pointer | Verdict (`kinds`) | Hover | Click |
| --- | --- | --- | --- |
| Nothing | — | nothing lit | clears selection |
| A timber, not drilled into | — | timber outline | selects / drills |
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

## 4. Third selection and beyond

The draft is `PENDING`. A further pick **replaces the second end** and is judged
against the still-held first one. Everything in §3 applies unchanged.

This row is the one the code kept getting wrong, because `PENDING` looks like a
finished state and is not:

- The held end must still be offered to the runner (`heldEnd`), or the pick is
  judged as if nothing were held — no kinds, no pairwise anchors, no plane.
- The verdict must be recomputed, and the hover re-asked: the pointer has not
  moved, so nothing else will prompt it.

## 5. Transitions

| From | Input | To | Also |
| --- | --- | --- | --- |
| `IDLE` | "Measure from" | `HOLDING` | undo suspended; held end drawn |
| `HOLDING` | pick a valid second | `PENDING` | preview drawn from pairwise anchors |
| `HOLDING` | pick an invalid second | `HOLDING` | refusal reported; nothing changes |
| `HOLDING` | Escape | `IDLE` | undo resumed; held end cleared |
| `PENDING` | pick another | `PENDING` | second end replaced |
| `PENDING` | Escape | `HOLDING` | **one end at a time** |
| `PENDING` | Confirm | `IDLE` | written, one undo entry pushed |
| any | change scene / reload | `IDLE` | undo resumed, purged on reload |

Escape releasing one end at a time is deliberate: one press throwing away both
is the same keystroke doing a small thing and a large one depending on state you
cannot see.

**Every path out of the draft must un-suspend undo.** Confirm, escape-to-idle,
scene change and reload all do; a path that forgets leaves undo silently dead.

## 6. Where the verdict is decided — the actual problem

One question, "can these two be measured, and how", is answered in five places:

| # | Place | Input it uses |
| --- | --- | --- |
| 1 | `_best_matching_candidate` | held geometry, look, space |
| 2 | `_kinds_for_pick` | held geometry, look, space |
| 3 | hover colour (`isRefused`) | the runner's answer |
| 4 | `_measurePicked` refusal | the runner's answer |
| 5 | `measurementStatus` | the measurement's own kind and plane |

3 and 4 now read one answer, which is right. **1, 2 and 5 each derive it
again**, and every disagreement between them has been a shipped bug:

- 1 and 2 disagreeing → the offered feature is one the pick then refuses
- 2 and 5 disagreeing → the pick is accepted and nothing is ever drawn
- 2 asking without the held end → everything after the first pair is misjudged
- 5 asking in the wrong space → a measurement reports itself broken

**Recommendation.** The pick response should carry one verdict object — the
kinds, the plane, the pairwise anchors, and the reason when there are none — and
1, 3 and 4 should read exactly that. 5 is the one legitimate second
implementation, because it judges a *written* measurement that no pick is
happening for; it should be reachable from the same rule module with the
measurement's own kind and plane as input, and be tested against the runner on
the same cases, as `projected_form` and `solid_form` already are.

## 7. Known open

- **Kind sticks when the second end changes between an angle pair and a distance
  pair.** Reported against the 3D view, and seen in a drawing too.
  `_pendingKinds` is replaced on every accepted pick and the SVG overlay is
  rebuilt from scratch each frame, so neither is holding the old kind. The
  likely mechanism is §6 case "2 and 5 disagreeing": `measurementStatus`
  recomputes `available` using the **measurement's plane normal** as the look,
  while the runner computed `kinds` using the **camera's** look. Where those
  differ the viewer rejects the runner's kind as `kind-unavailable` and draws
  nothing — leaving whatever was last drawn to read as "stuck". In the 3D view
  this should now be moot, the solid rules using no look at all. **Needs
  retesting**; if it survives, the fix is §6, not another patch here.
- **Two clicks to reach a feature on an unselected timber in the 3D view**
  (§2). Works as designed; awkward mid-measurement.
- **Angle placement** is deferred: an angle uses no anchor positions, and where
  it should sit is its own question.
- **Faces carry an AABB, not corners**, so a rotated prism's face extent is
  larger than the face.
