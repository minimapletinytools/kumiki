"""Drawings: what a sheet shows -- Drawing, Viewport, Subdivision and the sizes, about where things
sit on a page. The dimensions on it are measure.py.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union

from ..identity import DrawingId, ViewportId
if TYPE_CHECKING:
    from ..timber import PerfectTimberWithin
from ..rule import Numeric

# Measuring lived here; its names are still importable from this module.
from .measure import (  # noqa: F401
    MeasurementSpace,
    MeasurementOperation,
    MeasurementDirection,
    MeasurementFeature,
    MeasurementKind,
    DEGENERATE_SEPARATION,
    PARALLEL_EPSILON,
    DEFAULT_LOOK,
    DEFAULT_RIGHT,
    DEFAULT_UP,
    VectorLike,
    Geometry,
    project_geometry_for_measuring,
    form_of,
    PointSpan,
    LineSpan,
    PlaneSpan,
    MeasureSpan,
    ViewAxes,
    DEFAULT_VIEW,
    pair_separation,
    measures_nothing,
    AngleRays,
    angle_rays,
    angle_between,
    slide_axis,
    distance_anchors,
    projected_kinds,
    three_d_kinds,
    kinds_for,
    MeasurementPlane,
    FromViewport,
    FROM_VIEWPORT,
    MeasurementPlaneSpec,
    MeasurementPlacement,
    Measure,
    MeasurementSource,
    does_override,
    does_override_identities,
)


# TODO move these into a viewport.py file or prefix with Viewport to make it more clear
# ============================================================================
# Viewports: what a drawing shows, and how it divides the sheet
# ============================================================================


class SplitDirection(Enum):
    """Which way a subdivision divides, and so which way its portions run."""

    #: Portions stacked top to bottom, each the full width.
    ROWS = "rows"
    #: Portions side by side left to right, each the full height.
    COLUMNS = "columns"


@dataclass(frozen=True)
class Share:
    """A share of whatever the fixed-size siblings leave over.

    Two shares of 1 split what is left in half; a 2 and a 1 split it two to
    one. What a drawing means by "these four rows are equal", without caring
    how tall the sheet is.
    """

    value: Numeric = 1

    def __post_init__(self):
        if not (self.value > 0):
            raise ValueError(f"A share is positive, got {self.value}")


@dataclass(frozen=True)
class Length:
    """A size in page units. What a title block wants: 40mm, whatever the sheet.

    Wrapped rather than left as a bare number so that it cannot be mistaken for
    a Share. `Portion(view, 0.5)` reading as half a metre when half the room was
    meant is the kind of thing a unit only catches once it is on paper.
    """

    value: Numeric

    def __post_init__(self):
        if not (self.value > 0):
            raise ValueError(f"A length is positive, got {self.value}")


#: How much of a subdivision one portion takes.
Size = Union[Share, Length]

#: Where a floating viewport sits, as [x, y, width, height], each a fraction of
#: the page, origin top left. The form the viewer has always taken.
Rect = Tuple[float, float, float, float]


@dataclass(frozen=True)
class Page:
    """The sheet, in real units. What a Length is measured against."""

    width: Numeric
    height: Numeric

    def __post_init__(self):
        if not (self.width > 0 and self.height > 0):
            raise ValueError(f"A page has a positive size, got {self.width} x {self.height}")


@dataclass(frozen=True)
class Portion:
    """One child of a subdivision, and how much of the cell it takes.

    The size lives here rather than on the Viewport because it is a fact about
    the ARRANGEMENT, not about the view. "Half of this row" means nothing until
    there is a row, and a viewport does not know it is in one -- see Viewport.
    Keeping it here is also what lets a viewport be moved without carrying a
    proportion that belonged somewhere else.

    Held as its own type rather than a second tuple of sizes beside the
    children: two lists that must stay the same length and the same order are
    two lists that come apart, and at four children you are counting positions
    across both to see which size goes with which view.
    """

    viewport: 'Viewport'
    size: Size = field(default_factory=Share)


@dataclass(frozen=True)
class Subdivision:
    """How one viewport divides itself between the viewports inside it.

    Rows run top to bottom and columns left to right, which is both the order
    the portions are written in and the order their ids are numbered in.
    """

    direction: SplitDirection
    portions: Sequence[Portion]
    #: Space between portions, in page units. Not before the first or after the
    #: last -- that is what a viewport's own padding is for, and the two
    #: compose.
    gap: Numeric = 0

    def __post_init__(self):
        object.__setattr__(self, 'portions', tuple(self.portions))
        if not self.portions:
            raise ValueError("A subdivision divides a cell between portions, and has none")

    def taking(self, size: 'Size') -> 'Portion':
        """This subdivision, in a viewport of its own, as a portion of that size.

        The counterpart of Viewport.taking, so that a nested division can say
        how much room it takes without the wrapper having to be written out:
        `columns(rows(a, b).taking(Share(2)), c)`.
        """
        return Portion(viewport=Viewport(subdivision=self), size=size)


#: A drawing's floating viewports, in the order they were written -- which is
#: what numbers them, so the order is part of what the drawing means.
ViewportList = Tuple['Viewport', ...]


@dataclass(frozen=True, eq=False)
class Viewport:
    """One view on a sheet, and the views inside it.

    Knows what it is called, how much room it leaves inside itself, and what it
    contains. Does NOT know where it sits: not its rect, not its id, not its
    parent. Those are facts about the tree rather than about the viewport, and
    they are the drawing's to answer -- see Drawing.walk and Drawing.get_viewport_id.

    `subdivision` is None for a leaf, which is the only kind that gets a camera
    and becomes a viewport on screen; one with portions is a container, and the
    views inside it fill its cell. The three things a division needs --
    direction, portions, gap -- are grouped into Subdivision rather than sitting
    here as three optionals, so that "a direction but nothing to divide" cannot
    be written down.

    `rect` and `z` place a FLOATING viewport on the page and are meaningless on
    one inside a subdivision, which is placed by its portion's size instead.
    Which of the two this is, is again not something a viewport knows, so
    Drawing checks it.

    COMPARED BY IDENTITY, not by value. Two viewports with the same label are
    different viewports -- the whole point of ids being positional is that what
    a view IS, to a drawing, is the cell it occupies. Value equality would make
    get_viewport_id ambiguous between them, and comparing viewports by value is not a
    thing anyone wants: it would be asking whether two cells of a sheet happen
    to be described alike.
    """

    label: Optional[str] = None
    #: Blank space inside this viewport's own cell, in page units, on every
    #: side. On the Viewport rather than the Portion because it is true of the
    #: viewport alone -- "leave a margin inside me" needs no siblings to mean
    #: something.
    padding: Numeric = 0
    subdivision: Optional[Subdivision] = None
    #: The dimensions drawn in this viewport. On the viewport rather than
    #: keyed by id somewhere else, so that writing one takes no counting: a
    #: measurement belongs to the view it is drawn in, and here it can say so
    #: by being there. Only a leaf renders, so only a leaf's are drawn.
    measurements: Sequence['Measure'] = ()
    #: Floating placement. Roots have these; the views inside a subdivision
    #: must not.
    rect: Optional[Rect] = None
    #: Which is in front where two floating viewports overlap. Higher is nearer
    #: the reader.
    z: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'measurements', tuple(self.measurements))
        if self.rect is not None:
            rect = tuple(float(value) for value in self.rect)
            if len(rect) != 4:
                raise ValueError(f"A rect is [x, y, width, height], got {self.rect!r}")
            x, y, width, height = rect
            if width <= 0 or height <= 0:
                raise ValueError(f"A floating viewport has a positive size, got {width} x {height}")
            # Checked rather than clamped. The viewer clamps a rect into [0, 1]
            # without a word, so one placed half off the sheet quietly became a
            # different rect; saying so here is the difference between a layout
            # being wrong and being wrong in silence.
            if x < 0 or y < 0 or x + width > 1 or y + height > 1:
                raise ValueError(
                    f"A floating viewport sits on the page: {rect} runs off it. A rect is "
                    f"fractions of the page, [x, y, width, height] from the top left."
                )
            object.__setattr__(self, 'rect', rect)

    @property
    def is_leaf(self) -> bool:
        """True if this is a view rather than a container: it gets a camera."""
        return self.subdivision is None

    @property
    def children(self) -> ViewportList:
        """The viewports inside this one, in order. Empty for a leaf."""
        if self.subdivision is None:
            return ()
        return tuple(portion.viewport for portion in self.subdivision.portions)

    def taking(self, size: Size) -> Portion:
        """This viewport, as a portion of that size. `plan.taking(Share(2))`.

        Sugar for Portion(self, size). It stores nothing here -- a viewport
        still does not know how big it is in an arrangement it is not aware of
        -- it is a shorter way to write the pair down.
        """
        return Portion(viewport=self, size=size)


def rows(*children: Union[Viewport, 'Subdivision', Portion], gap: Numeric = 0) -> Subdivision:
    """A subdivision stacking its children top to bottom.

    A bare Viewport takes an equal share, which is the common case and should
    read as one; a Portion says how much it takes instead.
    """
    return Subdivision(direction=SplitDirection.ROWS, gap=gap,
                       portions=tuple(_as_portion(child) for child in children))


def columns(*children: Union[Viewport, 'Subdivision', Portion], gap: Numeric = 0) -> Subdivision:
    """A subdivision setting its children side by side, left to right."""
    return Subdivision(direction=SplitDirection.COLUMNS, gap=gap,
                       portions=tuple(_as_portion(child) for child in children))


def _as_portion(child: Union[Viewport, 'Subdivision', Portion]) -> Portion:
    """Whatever was written in a row or column, as the portion it means.

    A Subdivision is wrapped in a Viewport of its own, so that `columns(rows(a,
    b), c)` reads like the shape it makes. That wrapper is a real node with a
    real id -- a container is a viewport that happens to hold others -- it just
    has nothing to say about itself, so it carries no label.
    """
    if isinstance(child, Portion):
        return child
    if isinstance(child, Subdivision):
        return Portion(viewport=Viewport(subdivision=child))
    return Portion(viewport=child)


def covering_page(subdivision_or_viewport: Union[Viewport, Subdivision],
                  **options) -> Viewport:
    """A floating viewport over the whole sheet. The common case by far."""
    if isinstance(subdivision_or_viewport, Subdivision):
        return Viewport(rect=(0.0, 0.0, 1.0, 1.0), subdivision=subdivision_or_viewport,
                        **options)
    return replace(subdivision_or_viewport, rect=(0.0, 0.0, 1.0, 1.0), **options)


# ---------------------------------------------------------------------------
# default drawing layouts 
# ---------------------------------------------------------------------------

# aso what's th e difference between this and Sequence[Viewport]? oh I guess tuple has at least one?
def shop_drawing_viewports() -> ViewportList:
    """One piece's four long faces down the left, a preview beside them.

    How a piece is drawn for the shop: every long side rolled out, square on,
    with a live view of the whole thing to read them against.
    """
    return (covering_page(columns(
        rows(Viewport(label="Front"), Viewport(label="Right"),
             Viewport(label="Back"), Viewport(label="Left")),
        Viewport(label="Preview"),
    )),)


SHOP_DRAWING_IDS: Mapping[str, ViewportId] = {
    "front": ViewportId("0.0.0"),
    "right": ViewportId("0.0.1"),
    "back": ViewportId("0.0.2"),
    "left": ViewportId("0.0.3"),
    "preview": ViewportId("0.1"),
}


def elevation_viewports() -> ViewportList:
    """Three world elevations and a preview, a quadrant each.

    For several pieces at once, which have no single piece whose faces the
    sheet could be about. Two rows of two columns rather than four rects: the
    rows are what make the elevations line up across the sheet.
    """
    return (covering_page(rows(
        columns(Viewport(label="Front"), Viewport(label="Top")),
        columns(Viewport(label="Right"), Viewport(label="Preview")),
    )),)


ELEVATION_IDS: Mapping[str, ViewportId] = {
    "front": ViewportId("0.0.0"),
    "top": ViewportId("0.0.1"),
    "right": ViewportId("0.1.0"),
    "preview": ViewportId("0.1.1"),
}


def default_viewports_for(timber_count: int) -> ViewportList:
    """The viewports a drawing gets when it names timbers and no layout.

    One piece is drawn as a shop drawing of that piece. Several have no single
    piece whose faces the sheet could be about, so they get world elevations.
    """
    return shop_drawing_viewports() if timber_count == 1 else elevation_viewports()


@dataclass(frozen=True)
class Drawing:
    """A drawing the frame asks for: a name, and which timbers it is of.
    """

    name: str

    #: Which timbers this is a drawing of, one entry per timber: the frame's own
    #: timber objects, not copies. Frame checks this when it is built.
    timbers: Sequence['PerfectTimberWithin'] = ()

    #: What an override in the drawings file names, so it has to survive editing
    #: the code around it. Optional only at CONSTRUCTION: leave it out and it
    #: becomes DrawingId(name), which is stable as long as the name is, and it
    #: is never None on a built Drawing.
    #:
    #: A classmethod taking the optional id would let this field be declared
    #: non-optional, which is what the note asked for. Not done: it costs all 49
    #: Drawing(...) sites a rename to buy one annotation, and the coercion below
    #: would still have to exist for the string form.
    drawing_id: Optional[DrawingId] = None

    #: The floating viewports of this sheet, in the order they were written.
    #: That order is what numbers them -- see walk -- so it is part of what the
    #: drawing means. It is not the drawing order; z is.
    #:
    #: None asks for the default layout for what this draws. It was (), which
    #: could not tell "I did not say" from "I said none": an explicitly empty
    #: tuple was silently replaced by the defaults.
    viewports: Optional[Sequence[Viewport]] = None

    #: The sheet these sit on, when this drawing lays itself out. A Length
    #: anywhere in the tree is measured against it.
    #:
    #: None is the common case -- 31 of the drawings built in this repo -- and
    #: means the sheet is not this drawing's to choose: the viewer lays it out
    #: and supplies its own page. Only kumiki.drawings.layout.resolve_drawing needs one,
    #: and it says so rather than inventing a size.
    page: Optional[Page] = None

    measurements: Mapping[ViewportId, Sequence[Measure]] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, 'timbers', tuple(self.timbers or ()))
        if not self.drawing_id:
            object.__setattr__(self, 'drawing_id', DrawingId(self.name))
        elif isinstance(self.drawing_id, str):
            object.__setattr__(self, 'drawing_id', DrawingId(self.drawing_id))
        object.__setattr__(self, 'measurements', {
            viewport: tuple(measures)
            for viewport, measures in dict(self.measurements or {}).items()
        })

        # A drawing always ends up with viewports. One that says nothing gets
        # the default layout for what it draws, made here and held like any
        # other -- so there is no second kind of drawing whose views exist only
        # once something else has laid it out. Saying () means none, and is
        # kept.
        viewports = (default_viewports_for(len(self.timbers))
                     if self.viewports is None else tuple(self.viewports))
        object.__setattr__(self, 'viewports', viewports)
        self._check_placement()
        self._check_each_viewport_appears_once()

    # ---------------------------------------------------------------- the tree

    @property
    def roots(self) -> ViewportList:
        """The floating viewports, settled. Never None.

        `viewports` is Optional because the CONSTRUCTOR takes None to mean "give
        me the default layout for what this draws"; __post_init__ resolves that
        and always leaves a tuple. This is that guarantee, said once, so the
        rules below do not each carry an optionality that cannot happen.
        """
        return tuple(self.viewports or ())

    def walk(self) -> Iterator[Tuple[ViewportId, 'Viewport']]:
        """Every viewport of this drawing, with the id its position gives it.

        Depth first and in written order, so a parent comes before the views
        inside it.
        """
        def descend(viewport: 'Viewport', path: Tuple[int, ...]):
            yield (ViewportId(".".join(str(step) for step in path)), viewport)
            for index, child in enumerate(viewport.children):
                yield from descend(child, path + (index,))

        for index, root in enumerate(self.roots):
            yield from descend(root, (index,))

    def measurements_by_viewport(self) -> Dict[str, Tuple[Measure, ...]]:
        """Every dimension of this drawing, under the id of the view it is in.
        """
        collected: Dict[str, Tuple[Measure, ...]] = {}
        for viewport_id, viewport in self.walk():
            if viewport.measurements:
                collected[str(viewport_id)] = tuple(viewport.measurements)
        for viewport_id, measures in self.measurements.items():
            key = str(viewport_id)
            collected[key] = collected.get(key, ()) + tuple(measures)
        return collected

    def leaves(self) -> Iterator[Tuple[ViewportId, 'Viewport']]:
        """Every viewport that gets a camera, with its id. What renders."""
        return ((id, viewport) for id, viewport in self.walk() if viewport.is_leaf)

    def get_viewport_id(self, viewport: 'Viewport') -> ViewportId:
        """Where this viewport sits, which is what identifies it.
        """
        for found, candidate in self.walk():
            if candidate is viewport:
                return found
        raise KeyError(f"{viewport!r} is not a viewport of drawing {self.drawing_id}")

    def viewport_at(self, viewport_id: ViewportId) -> Optional['Viewport']:
        """The viewport at an id, or None. The other direction from get_viewport_id."""
        wanted = str(viewport_id)
        for found, viewport in self.walk():
            if str(found) == wanted:
                return viewport
        return None

    # ------------------------------------------------------------- the checks

    def _check_placement(self) -> None:
        """A root floats; a view inside a subdivision does not.

        Checked here because a viewport cannot check it: which of the two it is
        depends on where it sits, and not knowing that is the whole design.
        """
        for index, root in enumerate(self.roots):
            if root.rect is None:
                raise ValueError(
                    f"Viewport {index} of drawing {self.drawing_id} floats on the page "
                    f"and needs a rect. Only the views inside a subdivision are placed "
                    f"by their portion's size."
                )
        for viewport_id, viewport in self.walk():
            if "." in str(viewport_id) and viewport.rect is not None:
                raise ValueError(
                    f"Viewport {viewport_id} of drawing {self.drawing_id} is inside a "
                    f"subdivision, so its cell comes from its portion's size. A rect "
                    f"here would say two different things about where it goes."
                )

    def _check_each_viewport_appears_once(self) -> None:
        """No viewport twice in one drawing.

        A viewport is identified by where it is, so one object in two places has
        two ids and get_viewport_id could only guess. Reusing an object is the easy way to
        write that by accident -- `v = Viewport(...)` then `rows(v, v)` -- so it
        is refused rather than resolved arbitrarily.
        """
        seen = {}
        for viewport_id, viewport in self.walk():
            if id(viewport) in seen:
                raise ValueError(
                    f"The same viewport is at {seen[id(viewport)]} and {viewport_id} of "
                    f"drawing {self.drawing_id}. Viewports are told apart by where they "
                    f"are, so each position needs its own."
                )
            seen[id(viewport)] = viewport_id
