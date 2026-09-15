# Measuring: the states, and every transition

What the viewer does while a measurement is being made, after the change
described in `selection-states.md` §7. That document is the investigation and
the plan; this one is the target, and the code should be readable against it.

`measurement-spec.md` says what a measurement IS. This says how one gets made.

## The shape of it

> Select a feature. Hover a second one and **the measurement you would get is
> drawn**. Click and it is written.

There is no pending measurement and no confirm step. What you are looking at
before the click is the same thing you get after it.

## States

Two, and the second is the whole flow.

| State | Meaning | What is on screen |
| --- | --- | --- |
| `IDLE` | Nothing being measured. Ordinary selection. | whatever is selected |
| `HOLDING` | A first end is held. | the held end, drawn as held; a preview whenever the pointer is over a candidate that works |

The held end is **held, not selected**. Hovering and clicking elsewhere moves
the selection; the held end has to survive that, and is drawn in its own colour
so the difference is visible.

## The verdict

Every question about a candidate is answered by one object, computed by the
runner and returned with the hover and with the click.

| Field | Meaning |
| --- | --- |
| `kinds` | what the pair admits, best first. `[]` = nothing from here |
| `plane` | the plane the measurement would be taken on |
| `anchors` | where it would attach, at both ends |
| `reason` | why there is nothing, when `kinds` is empty |

The whole object is `null` when no measurement is being made — which is
different from `kinds: []`, and both are read:

- **`null`** — an ordinary hover. Nothing is held; nothing is being judged.
- **`[]`** — this pair cannot be measured from here. Drawn red; a click is
  refused.

**One verdict, three readers.** The highlight colour, the preview, and whether
the click is taken all read this object and nothing else. They cannot disagree,
which is the property the old code did not have.

## Reaching a feature

Unchanged in `IDLE`, and it forks by view:

| View | A click on a timber |
| --- | --- |
| 3D | selects it; a second click drills in |
| Drawing | drills straight in |

**While `HOLDING`, the fork closes**: both views drill straight to the feature.
Otherwise a feature on an unselected timber could not be previewed without first
clicking to select its timber, and measuring between two timbers is the ordinary
case.

## Transitions

| From | Input | To | Effect |
| --- | --- | --- | --- |
| `IDLE` | "Measure from" a focused feature | `HOLDING` | held end drawn; undo suspended |
| `IDLE` | anything else | `IDLE` | ordinary selection |
| `HOLDING` | hover a candidate the verdict allows | `HOLDING` | **preview drawn**, at the anchors and on the plane it will be written with |
| `HOLDING` | hover a candidate the verdict refuses | `HOLDING` | lit **red**; no preview |
| `HOLDING` | hover the held end, or nothing | `HOLDING` | no preview |
| `HOLDING` | **click a candidate the verdict allows** | `IDLE` | **written**; feature selection cleared; the new measurement selected; undo resumed; one entry pushed |
| `HOLDING` | click a candidate the verdict refuses | `HOLDING` | refusal reported; nothing changes |
| `HOLDING` | Escape | `IDLE` | held end cleared; undo resumed |
| `HOLDING` | Tab | `HOLDING` | cycles which feature under the pointer is meant; verdict and preview follow |
| `HOLDING` | right-click | `HOLDING` | menu of the features under the pointer; choosing one is the same as Tab |
| any | scene change, reload | `IDLE` | held end cleared; undo resumed (and purged, on reload) |

### Refusals

A click is refused, with a reason said rather than silently ignored, when:

| Reason | Meaning |
| --- | --- |
| `same-feature` | the end already held — a measurement from a thing to itself |
| `no-reference` | a feature nobody declared, so a dimension to it could not be saved |
| `not-measurable` | no plane or line of its own: a cylinder's barrel, a lofted side |
| `no-kind` | the pair admits nothing in this space, from here |

A refusal leaves `HOLDING` exactly as it was. The first end is not lost because
the second was wrong.

## Rules that outlive any one state

- **Every path out of `HOLDING` resumes undo.** Writing, Escape, a scene change,
  a reload. A path that forgets leaves undo silently dead, which is not visible
  until someone presses ctrl-Z much later.
- **Undo is suspended while holding.** There is no half-made measurement on the
  stack, so undo would reach past the thing you are looking at.
- **The preview is drawn from the verdict, never from a second calculation.**
  If the preview and the written measurement can be computed by different code,
  they will eventually differ, and that difference is invisible until someone
  clicks.
- **Hover must ask what the click will ask.** Same candidate rule, same verdict.
  A hover that lights what a click refuses is the same bug in a different coat.
- **The held end survives everything but leaving.** Selection changes, camera
  moves, panel clicks.
- **A written measurement carries its own plane**, fixed at creation. In the 3D
  view that plane comes partly from where the camera was; the value must not
  drift when the reader orbits afterwards.
- **An angle is a corner, placed where the corner is.** The runner works out a
  vertex on the line the two features share and two rays from it, and the viewer
  draws that — it decides nothing. The value is read off the same two rays, so
  the number and the arc cannot disagree; normals alone give the same absolute
  dot for 45° and 135°, which is why the side has to be settled where the corner
  is. Which side: where each feature actually reaches, and for an edge that
  straddles the vertex, the OTHER feature's outward normal — an edge's own
  normal is square to it and cannot choose a direction along it.
- **A distance to a face is square to the face.** In the solid a face is a
  plane, not the line a face draws as when seen edge-on from a sheet, so the
  anchor is chosen on whichever end has less freedom — a point has none, a line
  one direction, a plane two — and dropped onto the other perpendicular to it.
  Treating a face as a line there shared a station along one direction only, and
  left a dimension to a parallel edge leaning by the offset in the other.

## What the panel says

| State | Action button |
| --- | --- |
| `IDLE`, a measurable feature focused | **Measure from** |
| `IDLE`, otherwise | absent |
| `HOLDING` | **Cancel** — the same as Escape |

There is no Confirm button. The click on the second feature is the confirmation,
and the preview under the pointer is what it confirms.

## What this removed

Recorded because the absence is the point:

- the `PENDING` state, and every bug that lived in it
- replacing the second end, and the question of what a third click means
- the two-level Escape, where one key did a small thing or a large one
  depending on state you could not see
- the Confirm button, and the pending measurement it acted on
- `_pendingKinds`, and the second copy of the kind that went with it
