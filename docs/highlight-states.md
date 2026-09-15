# What is lit, and why: timber and feature rendering

**Status: §6 is built.** Overlays are a list now — `highlights.js` says what
should be lit and a reconciler makes the scene match, called from the frame
loop's derive pass. Sections 1–4 below describe what it was and why, because the
reasoning is what stops it growing back; §5 is still the open question.

Companion to `measuring-states.md`. That says what the viewer is *doing*; this
says what it *looks like* while doing it, and where the two can disagree.

Written because the highlight is about to grow — a measurement should light the
features it measures from — and because the last stretch produced two bugs that
were neither wrong colours nor wrong geometry, but wrong *lifetimes*: something
torn down at a moment nobody meant.

## 1. Two halves, held to different standards

| | Member appearance | Highlight overlays |
| --- | --- | --- |
| **What** | every timber's face and edge opacity | the seven meshes and lines drawn over them |
| **How** | recomputed for every member, every pass | built once when a message arrives |
| **From** | current state, via a pure function | the pick/hover response that caused it |
| **Torn down by** | nothing — the next pass overwrites it | seven scattered `clear…()` calls |
| **Drift** | impossible; it is derived | this is where every bug has been |

`applySelectionOpacity()` is the good half. It walks every member and asks
`_memberAppearance` what that member should look like *now*, given the
selection, the layers, and the drawing. It is called from eleven places, and
calling it more often costs a loop over members and is otherwise free. Nothing
accumulates, so nothing can drift.

The overlays are the other half. `handleCSGSelectionResult` removes the old
highlight and builds a new one **from the message it just received**. There is
no path from "the state is X" to "these overlays should exist" — only from
"this message arrived" to "build these". Which means every state change that
does *not* produce a message has to remember to tear the right thing down by
hand.

## 2. Member appearance, as it is derived today

In order; the first match wins.

| Condition | Class | Face opacity | Edge opacity |
| --- | --- | --- | --- |
| Member hidden in layers | `hidden` | — | — |
| In a drawing, member not in it | `ghost`, or `hidden` if ghosts are off | ≤ 0.05 | × 0.05 |
| Nothing selected | `normal` | selected-visibility slider | profile × slider |
| Timber selected, no subselection — **that timber** | `selected` | selected slider | profile × slider |
| Timber selected, no subselection — **the others** | `ghost` | unselected slider | profile × slider |
| A subselection — **the timber owning it** | `selected` | 0.62 / 0.66 / 0.72 by state | profile × slider |
| A subselection — **the others** | `ghost` | min(slider, 0.18 / 0.20 / 0.25) | profile × slider |

The three numbers are `FEATURE_SELECTED`, `TAGGED_CSG_SELECTED_WITH_SUB`,
`TAGGED_CSG_SELECTED_NO_SUB` — the deeper the selection, the more the owning
timber fades so what is *inside* it can be seen.

`computeSelectionVisualContext(selectedTimbers, csgFocus)` decides which of the
five states applies. It is pure, it takes a plain snapshot, and its comment says
it was split out "so the decision is pure and independently testable".
**It has no tests.**

## 3. The overlays, and what each one is derived from

| Overlay | Drawn when | Built from | Colour | Order | Torn down by |
| --- | --- | --- | --- | --- | --- |
| CSG feature mesh | the focus names a feature | pick `highlightMesh` | `0x0288d1` | 999 | `removeCSGHighlight` |
| CSG parent mesh | a feature inside a parent | pick `parentHighlightMesh` | `0x29b6f6` | 999 | `removeCSGHighlight` |
| CSG edge line | the pick returned edge segments | pick `highlightEdgeSegments` | `0x0288d1` | 1000 | `removeCSGHighlight` |
| Hover mesh | pointer over what a click would take | hover response | `0xffa726`, or `0xef5350` refused | 1100 | `clearHoverOutline` |
| Hover edge | as above, for edges | hover response | as above | 1101 | `clearHoverOutline` |
| Held feature mesh | draft is `HOLDING` | the anchor captured **at hold time** | `0x66bb6a` @ 0.8 | 1101 | `clearHeldFeature` |
| Held feature lines | draft is `HOLDING` | as above | as above | 1101 | `clearHeldFeature` |
| Measurement (SVG) | per measurement, `status.drawable` | the resolved measurement | CSS | overlay | overlay cleared each render |
| Preview (SVG) | `HOLDING` + the verdict allows it | the hover verdict | CSS `.dim-pending` | overlay | overlay cleared each render |

Note the two disciplines side by side. **The SVG overlay is wiped and rebuilt on
every render** — `overlay.innerHTML = ''` — which is why measurements never
drift. The three.js overlays are not.

## 4. Where drift can get in

Found by reading, not by reports — except the first two, which shipped.

- **Teardown inside a redraw.** `drawHoverHighlight` calls `clearHoverOutline`
  as its first line, to remove what it is about to replace. Anything else
  forgotten there is forgotten *mid-draw*. Two things were: the measurement
  preview (erased a statement after being drawn) and `_hoverDrawn` (left null
  after every draw, so the redraw guard compared against nothing and never once
  skipped). Both are fixed; the shape that produced them is still there.
- **A reload leaves the overlays behind.** `_frameLoaded()` purges the undo
  stacks, bumps the frame generation, drops `_lastPickAnchor` and clears the
  draft. It does **not** call `removeCSGHighlight` or `clearHover`. The meshes
  are added straight to `this.scene` and held on the app, so rebuilding the
  members does not take them with it: after an edit, a highlight can still be
  lit against geometry from the previous build.
- **Two overlays share render order 1101** — the held feature and the hover edge
  line. Which wins is undefined, and they are the two most likely to overlap:
  the hover is usually next to the thing being held.
- **The held highlight is a snapshot.** It is captured from the pick anchor when
  the end is taken and never recomputed. If the frame reloads while holding, the
  draft is cleared — so it survives only by being torn down, not by being right.
- **Five states, one shared timber.** `subselectionTimberKey` falls back to "the
  only selected timber" when the focus does not name one. With several selected
  and a focus carrying no timber key, no member matches, and every timber ghosts.

## 5. What "a measurement lights its features" needs

The wanted behaviour does not fit the current shape, and it is worth being
precise about why.

Every overlay above is built from a **pick or hover response**. A resolved
measurement carries `at` and `geometry` for each end — a point, a line, a plane,
analytically — but **no triangles**: `_anchor_payload` returns `{at, geometry}`
and nothing else. There is no mesh to light, and no message that would bring
one.

Two ways to get it:

1. **The runner returns highlight meshes with resolved measurements.** Simple,
   and it costs a mesh walk per end per measurement on every resolve — for a
   sheet with thirty dimensions, sixty walks nobody asked for.
2. **The viewer asks when a measurement is focused.** One request, for two
   features, only when something is selected. It is the same question
   `find_csg_by_path` already answers, and it matches how the rest of the
   highlight works: ask about what is selected, not about everything.

**Recommend 2**, and note that the answer wants caching by measurement key, or
focusing a measurement costs a round trip every time the selection is touched.

## 6. The change worth making first

One derivation, the way member appearance already works.

```
highlightsFor(state) -> [ { id, geometry, colour, opacity, renderOrder }, … ]
```

A pure function from a state snapshot — selection, focus, draft, hover answer,
measurement focus — to the list of overlays that *should* exist. Then a
reconciler that adds what is missing, removes what is not in the list, and
leaves the rest alone. Called wherever `applySelectionOpacity` is called.

What this buys:

- **Teardown stops being a decision.** Nothing calls `clearHoverOutline` at a
  moment it has to get right; an overlay disappears because it stopped being in
  the list. The two bugs in §4 could not have been written.
- **A reload cannot leave anything lit**, because the next pass derives the list
  from the new state and removes whatever is not in it.
- **"A measurement lights its features" is an entry in the list**, not a new
  lifetime to manage — which is the point, given how much more of this is coming.
- **Render order becomes a property of the list**, so ties like §4's are visible
  in one place rather than spread across seven build sites.

The cost is a mesh identity — an overlay needs an `id` stable across passes, so
the reconciler can tell "the same highlight, still wanted" from "a new one".
Measurements already have `measurementKey` for exactly this reason, and the CSG
overlays can key on member plus path plus feature.

**Done.** `computeSelectionVisualContext` was moved out of `viewer-app.js` — it
could not be tested there, since that file wants a browser — and has tests, as
does `layer-state-store`. `highlightsFor` is pure and tested, the reconciler
owns every overlay's lifetime, and three things fell out of the shape rather
than being fixed:

- **A resize now reaches every overlay.** Only the selection's line had its
  resolution refreshed; the hover and held lines had fields of their own and
  were missed, so they went thin until something rebuilt them.
- **Held and hover no longer share a render order.** They sat at 1101 together,
  which left which one won undefined, and they are the two most likely to
  overlap.
- **A highlight's opacity follows the selection.** It was frozen at the moment
  the message arrived, so deepening a selection faded the timber and left the
  highlight where it was.
