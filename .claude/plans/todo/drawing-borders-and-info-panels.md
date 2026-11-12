# Borders and info panels on a drawing

## Status — notes only, nothing built (2026-09-11)

Ideas from a conversation, written down to come back to. No code, no decision
taken. The viewport tree this builds on is merged (`71bc7b7`).

---

## What we want

Borders and info panels (title blocks) on a drawing sheet. They render **over**
the viewports, always. Several border styles and several info panel styles.

The starting position was: it is the drawing author's job to define viewports
that do not overlap them, with two common tricks for doing that --

1. **For the border**, define the viewport inset from the page edge.
2. **For the info panel**, put an empty viewport where the panel goes, so
   nothing else lands there.

Trick 2 has a wart: the empty viewport shows up in the tree view, where it is
not a view of anything and reads as a mistake.

---

## The observation the wart is pointing at

A border and a title block have **no camera, project no geometry, and take no
picks**. They are not viewports. Trick 2 is reservation-by-side-effect, and the
tree-view weirdness is that type error surfacing.

Both tricks can become features, and then neither is needed.

---

## Idea 1 — the border defines the drawable area

In drafting the border **is** the edge of the drawing area, not decoration
inside it. So rather than drawing a frame and asking authors to keep clear:

```python
Drawing(border=Border(style=BorderStyle.ZONED, margin=mm(10)), viewports=[...])
```

and viewport rects resolve **within the bordered area** rather than the raw
page. `rect=(0, 0, 1, 1)` then means "all the room there is", which is inside
the border, and nobody computes an inset. Trick 1 stops existing.

**Cost, stated plainly:** `Rect` stops meaning "a fraction of the page" and
starts meaning "a fraction of the drawable area". That is a meaning change to a
documented type. For a drawing with no border the two are identical, so the
change is invisible until a border is added -- which is either the nicest or the
most surprising thing about it, depending on taste.

**Where it lands in code:** `resolve_viewports` starts each root at its rect
scaled against the page. It would start against the bordered area instead --
one inset, computed once, before the walk.

---

## Idea 2 — panels take part in the layout without being viewports

Let a `Portion` hold either a `Viewport` or a `Panel`:

```python
rows(
    plan,
    TitleBlock(style=TitleBlockStyle.STRIP).taking(Length(mm(40))),
)
```

The panel gets its rect from the same arithmetic, so it reserves its space
naturally -- but it never enters the viewport tree. No id, no camera, no row
among the views. Trick 2 stops existing, and so does the thing that bothered us
about it.

### The sub-decision that matters

**A panel must not consume a viewport id.** Indices number viewports among
viewports, so adding a title block does not renumber anything below it.

Otherwise dropping furniture into a sheet silently moves every measurement after
it -- which is the exact fragility positional ids have, and the thing the
viewport refactor was built to contain. See the note at the top of
`kumiki/drawing.py` on how a viewport is identified.

---

## Idea 3 — floating panels as well

Some furniture does not want a cell: a north arrow in a corner, a logo, a
revision table pinned bottom-right whatever the layout does.

So panels get both forms, exactly as viewports do -- a portion inside a
subdivision, or a floating `rect` + `z`.

Floating is the one place overlap stays the author's problem, and the one place
a validation warning would earn its keep: *"this panel covers 40% of viewport
0.1"*.

---

## Idea 4 — styles as closed enums with parameters beside them

Matching how `Member` and the render profiles are done.

| | |
| --- | --- |
| `BorderStyle` | `PLAIN` (single rule), `DOUBLE`, `ZONED` (A/B/C and 1/2/3 zone marks with ticks, the ISO thing) |
| | plus `margin`, line weight, and a wider binding margin on the left if wanted |
| `TitleBlockStyle` | `CORNER` (bottom right), `STRIP` (full width along the bottom), `COLUMN` (down the right edge) |

Style says shape and internal arrangement; the layout says where it sits.

---

## Idea 5 — the content should mostly be DERIVED

The idea worth arguing hardest for.

A title block's fields are drawing name, scale, sheet size, date, sheet n of m,
material, drawn-by. The drawing already knows most of them -- and **scale is
genuinely computable**, from a viewport's camera extent against its rect and the
page. That is the number a shop actually reads off a sheet, and the one most
likely to be wrong if it is typed.

```python
TitleBlock(
    fields=(Field.NAME, Field.SCALE, Field.SHEET_SIZE, Field.DATE),
    overrides={Field.DRAWN_BY: "..."},   # only what nothing can derive
)
```

A title block filled in by hand goes stale the first time someone moves a
camera. One that asks the drawing cannot.

**Related and cheap once scale is computable:** a per-viewport `1:20` label in
the corner. That also settles the "give viewports labels" TODO, and
`Viewport.label` already exists with nothing reading it.

---

## Where this renders

Already solved, and worth knowing before designing anything:

`#measurement-overlay` is an **SVG overlay in page-pixel space**, rebuilt every
frame in `renderMeasurements()` (`kigumi/webview/viewer-app.js`), drawn after
`renderViewports()`. Borders and panels are 2D page furniture, so they belong
there.

- No new rendering machinery is needed.
- "Always over the viewports" is already what happens.
- `pageScreenRect` gives the paper's pixel rect to draw against.

Layering today is: desk -> paper (`paintSheet`) -> viewports -> measurement
overlay. Furniture joins the last one. Open: whether the border goes over or
under the dimensions. Probably over, since it is the frame.

---

## Build order, if we do it

| # | | why first |
| --- | --- | --- |
| 1 | `Border` + drawable-area inset | smallest, kills the bigger trick, every drawing wants one |
| 2 | `Panel` in a `Portion`, viewport ids unaffected | kills the other trick and the tree-view wart |
| 3 | `TitleBlock` with derived fields, starting with name and scale | the thing that makes an info panel worth having |

Floating panels and the richer border styles follow; nothing above forecloses
them.

---

## Open questions

- **Is a `Panel` addressable at all?** An id the drawings file could name, the
  way it names viewports for overrides -- or purely declarative furniture the
  file never points at? Leaning: purely declarative, and add addressing when
  something actually needs to point at one.
- **Does the border go over or under the dimension overlay?**
- **Does `Rect` changing meaning (idea 1) bother us?** The alternative is a
  separate "drawable area" concept that viewports resolve against explicitly,
  which is more honest and more to say.
- **Should a page carry a standard size** (A3, A4, ANSI B) rather than raw
  width/height, so `SHEET_SIZE` in a title block has something to print and the
  border style has a convention to follow? `Page` is width/height today.
