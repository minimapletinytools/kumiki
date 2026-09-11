"""Where the views of a drawing go on the page.

A layout is a tree, and the page is what it is measured against.

At the top are floating panes: a rect somewhere on the sheet, with a z saying
which is in front when two overlap. A floating pane holds one pane, and a pane
is either a View -- a leaf, which becomes a viewport with a camera -- or a
Split, which divides its area into rows or columns and holds more panes. So the
common shop drawing is one floating pane covering the sheet, split into two
columns, the left column split again into four rows.

Sizes are shares or lengths in page units, never pixels, so a layout describes
the same drawing on any sheet the page can be printed at.


HOW A VIEWPORT IS IDENTIFIED

By WHERE IT IS, and by nothing else. A viewport's id is its position: the index
of its floating pane, then the index of each child stepped through to reach it,
joined with dots. The second row of the first column of the first floating pane
is "0.0.1", and an undivided floating pane is just "2".

`name` is a label. It is drawn on the sheet and shown in lists, it is chosen to
be read, and NOTHING looks a viewport up by it. Two views may share a name, or
have none.

That is the opposite of how a timber or a feature is identified -- see
identity.py, where a name is the stable thing and position is the fallback --
and it is a deliberate difference. A drawing's views have no names of their own
worth trusting: "front" is a description of an angle, and a sheet may hold two
front elevations at different scales. What a view IS, to a drawing, is the cell
it occupies.

The cost is the honest one, and worth stating plainly: inserting a pane
renumbers every pane after it at that level, and anything holding an id -- a
measurement, in particular, which hangs off the viewport it is drawn in -- then
points at the pane that moved into the old position. Editing a layout moves
measurements. Adding at the end does not.
"""

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple, Union

from .identity import ViewportId
from .rule import Numeric

#: A rect on the page as [x, y, width, height], each a fraction of the page,
#: origin top-left. The form the viewer has always taken.
Rect = Tuple[float, float, float, float]


@dataclass(frozen=True)
class Page:
    """The sheet, in real units. What a length in a layout is measured against."""

    width: Numeric
    height: Numeric

    def __post_init__(self):
        if not (self.width > 0 and self.height > 0):
            raise ValueError(f"A page has a positive size, got {self.width} x {self.height}")


class SplitDirection(Enum):
    """Which way a split divides, and so which way its children run."""

    #: Children stacked top to bottom. Each takes the full width.
    ROWS = "rows"
    #: Children side by side, left to right. Each takes the full height.
    COLUMNS = "columns"


@dataclass(frozen=True)
class Share:
    """A share of whatever the fixed-size siblings leave over.

    Two shares of 1 split what is left in half; a 2 and a 1 split it two to one.
    The unit of a drawing that says "these four rows are equal" without caring
    how tall the sheet is.
    """

    value: Numeric = 1

    def __post_init__(self):
        if not (self.value > 0):
            raise ValueError(f"A share is positive, got {self.value}")


#: How big a pane is within its parent split: a Share of what is left, or a
#: length in page units. A length is what a title block wants -- "40mm tall" is
#: a real requirement, and no share can say it.
Size = Union[Share, Numeric]


@dataclass(frozen=True)
class Pane(ABC):
    """Something that occupies a rect: either a View or a Split."""

    #: How much of the parent split this takes. Ignored by a floating pane,
    #: which is placed by its rect instead.
    size: Size = field(default_factory=Share, kw_only=True)
    #: What to call it on a sheet. A LABEL -- see the module docstring. Nothing
    #: identifies a viewport by this.
    name: Optional[str] = field(default=None, kw_only=True)
    #: Blank space inside this pane's cell, in page units, on every side. What
    #: keeps two elevations from touching.
    padding: Numeric = field(default=0, kw_only=True)


@dataclass(frozen=True)
class View(Pane):
    """A leaf. The only kind of pane that becomes a viewport.

    `role` is how the code building the cameras recognises which view this is --
    'front', 'preview' -- in its own vocabulary. It is not an identity either;
    two views may share a role, and resolving a layout never reads it.
    """

    role: Optional[str] = None


@dataclass(frozen=True)
class Split(Pane):
    """Divides its cell into rows or columns, in order.

    Rows run top to bottom and columns left to right, which is the order the
    children are written in and the order their ids are numbered in.
    """

    direction: SplitDirection = field(kw_only=True)
    children: Tuple[Pane, ...] = field(kw_only=True)
    #: Space between children, in page units. Not before the first or after the
    #: last -- that is what padding is for, and the two compose.
    gap: Numeric = field(default=0, kw_only=True)

    def __post_init__(self):
        object.__setattr__(self, 'children', tuple(self.children))
        if not self.children:
            raise ValueError("A split divides its cell between children, and has none")


@dataclass(frozen=True)
class FloatingPane:
    """A rect on the page, holding a tree, with a z for when two overlap.

    Undivided, this is what a person would call a floating viewport: one rect,
    one camera. It is named for the pane rather than the viewport because once
    its content is a Split it is not a viewport at all -- the leaves below it
    are.
    """

    rect: Rect
    content: Pane
    #: Which is in front where two overlap. Higher is nearer the reader.
    z: int = 0

    def __post_init__(self):
        rect = tuple(float(value) for value in self.rect)
        if len(rect) != 4:
            raise ValueError(f"A rect is [x, y, width, height], got {self.rect!r}")
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            raise ValueError(f"A floating pane has a positive size, got {width} x {height}")
        # Checked rather than clamped. The viewer clamps a rect into [0, 1]
        # without a word, so a pane placed half off the sheet quietly became a
        # different pane; saying so here is the difference between a layout
        # being wrong and a layout being wrong in silence.
        if x < 0 or y < 0 or x + width > 1 or y + height > 1:
            raise ValueError(
                f"A floating pane sits on the page: {rect} runs off it. Rects are "
                f"fractions of the page, [x, y, width, height] from the top left."
            )
        object.__setattr__(self, 'rect', rect)


@dataclass(frozen=True)
class Layout:
    """Every floating pane of one drawing, in the order they were written.

    The order is what numbers them, so it is part of what the layout means --
    see the module docstring. It is not the drawing order; z is.
    """

    panes: Tuple[FloatingPane, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'panes', tuple(self.panes))


@dataclass(frozen=True)
class PlacedView:
    """One View, once the layout has said where it goes.

    What a drawing turns into a viewport: an id, a rect on the page, and the
    View that asked for it.
    """

    id: ViewportId
    view: View
    rect: Rect
    z: int

    @property
    def name(self) -> Optional[str]:
        return self.view.name

    @property
    def role(self) -> Optional[str]:
        return self.view.role


def _inset(rect: Rect, padding: Numeric, page: Page) -> Rect:
    """A rect shrunk by `padding` page units on every side."""
    if not padding:
        return rect
    x, y, width, height = rect
    horizontal = float(padding) / float(page.width)
    vertical = float(padding) / float(page.height)
    inset = (x + horizontal, y + vertical, width - 2 * horizontal, height - 2 * vertical)
    if inset[2] <= 0 or inset[3] <= 0:
        raise ValueError(
            f"Padding of {padding} leaves nothing of a pane {width} x {height} of the page"
        )
    return inset


def _divide(split: Split, rect: Rect, page: Page) -> List[Rect]:
    """Each child's rect, in order along the split's direction.

    Fixed sizes are taken out first and the shares divide what is left, which
    is the only order that lets "40mm and then the rest" mean what it says.
    """
    x, y, width, height = rect
    along_columns = split.direction is SplitDirection.COLUMNS
    # Lengths are given in page units and rects are fractions of the page, so
    # everything crosses through the page's size on the axis being divided.
    page_extent = float(page.width if along_columns else page.height)
    span = width if along_columns else height

    gap = float(split.gap) / page_extent
    free = span - gap * (len(split.children) - 1)

    fixed = {
        index: float(child.size) / page_extent
        for index, child in enumerate(split.children)
        if not isinstance(child.size, Share)
    }
    shares = {
        index: float(child.size.value)
        for index, child in enumerate(split.children)
        if isinstance(child.size, Share)
    }

    left_over = free - sum(fixed.values())
    if left_over < 0:
        raise ValueError(
            f"A {split.direction.value} split asks for more fixed size than its cell has: "
            f"{sum(fixed.values()) * page_extent:.4g} of {free * page_extent:.4g} page units"
        )
    total_shares = sum(shares.values())

    rects: List[Rect] = []
    offset = x if along_columns else y
    for index in range(len(split.children)):
        if index in fixed:
            length = fixed[index]
        else:
            length = left_over * shares[index] / total_shares if total_shares else 0.0
        rects.append((offset, y, length, height) if along_columns
                     else (x, offset, width, length))
        offset += length + gap
    return rects


def _place(pane: Pane, rect: Rect, path: Tuple[int, ...], z: int, page: Page,
           into: List[PlacedView]) -> None:
    """Walk one pane, adding every View beneath it to *into*."""
    cell = _inset(rect, pane.padding, page)
    if isinstance(pane, View):
        into.append(PlacedView(
            id=ViewportId(".".join(str(step) for step in path)),
            view=pane, rect=cell, z=z,
        ))
        return
    # Asked for outright rather than taken as "not a View". A third kind of pane
    # would otherwise arrive here and be walked as though it had children.
    if not isinstance(pane, Split):
        raise TypeError(f"A pane is a View or a Split, got {type(pane).__name__}")
    for index, (child, child_rect) in enumerate(zip(pane.children, _divide(pane, cell, page))):
        _place(child, child_rect, path + (index,), z, page, into)


def resolve_layout(layout: Layout, page: Page) -> Tuple[PlacedView, ...]:
    """Every View of a layout, with the rect it lands on, back to front.

    Ordered by z and then by position, which is the order the viewer draws in
    and the reverse of the order it picks in -- so a pane with a higher z is
    drawn over its neighbours and is the one a click finds.

    The rects come out as fractions of the page, which is the form the viewer
    has always taken, so resolving a layout is the whole of the difference
    between a tree and what goes on the wire.
    """
    placed: List[PlacedView] = []
    for index, pane in enumerate(layout.panes):
        _place(pane.content, pane.rect, (index,), pane.z, page, placed)
    # Sorted on z alone, with Python's stable sort keeping written order within
    # a z. Sorting on the id as well would order "0.10" before "0.2".
    return tuple(sorted(placed, key=lambda view: view.z))


def rows(*children: Pane, **options) -> Split:
    """A split stacking its children top to bottom."""
    return Split(direction=SplitDirection.ROWS, children=children, **options)


def columns(*children: Pane, **options) -> Split:
    """A split setting its children side by side, left to right."""
    return Split(direction=SplitDirection.COLUMNS, children=children, **options)


def covering_page(content: Pane, **options) -> Layout:
    """A layout of one floating pane over the whole sheet. The common case."""
    return Layout((FloatingPane(rect=(0.0, 0.0, 1.0, 1.0), content=content, **options),))
