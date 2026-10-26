"""Drawings: Drawing, Viewport, Subdivision and page sizes. The dimensions on a drawing are in measure.py."""

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
    """Which way a subdivision divides."""

    #: Portions stacked top to bottom, each the full width.
    ROWS = "rows"
    #: Portions side by side left to right, each the full height.
    COLUMNS = "columns"


@dataclass(frozen=True)
class Share:
    """A share of the room left by fixed-size siblings: Share(1), Share(1) split it in half."""

    value: Numeric = 1

    def __post_init__(self):
        if not (self.value > 0):
            raise ValueError(f"A share is positive, got {self.value}")


@dataclass(frozen=True)
class Length:
    """A size in page units, e.g. a 40mm title block."""

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
    """The sheet's size in real units."""

    width: Numeric
    height: Numeric

    def __post_init__(self):
        if not (self.width > 0 and self.height > 0):
            raise ValueError(f"A page has a positive size, got {self.width} x {self.height}")


@dataclass(frozen=True)
class Portion:
    """One child of a subdivision, with the size it takes."""

    viewport: 'Viewport'
    size: Size = field(default_factory=Share)


@dataclass(frozen=True)
class Subdivision:
    """How a viewport divides between its children: rows top to bottom, or columns left to right."""

    direction: SplitDirection
    portions: Sequence[Portion]
    #: Space between portions, in page units (not before the first or after the last).
    gap: Numeric = 0

    def __post_init__(self):
        object.__setattr__(self, 'portions', tuple(self.portions))
        if not self.portions:
            raise ValueError("A subdivision divides a cell between portions, and has none")

    def taking(self, size: 'Size') -> 'Portion':
        """Return this subdivision wrapped in a viewport, as a portion of `size`: `columns(rows(a, b).taking(Share(2)), c)`."""
        return Portion(viewport=Viewport(subdivision=self), size=size)


#: A drawing's floating viewports, in the order they were written -- which is
#: what numbers them, so the order is part of what the drawing means.
ViewportList = Tuple['Viewport', ...]


@dataclass(frozen=True, eq=False)
class Viewport:
    """One view on a sheet, and the views inside it.

    A leaf (no `subdivision`) gets a camera; a container's children fill its cell. `rect` and `z`
    place a floating root viewport and are ignored inside a subdivision. A viewport doesn't know its
    id or position; Drawing does. Compared by identity.
    """

    label: Optional[str] = None
    #: Margin inside this viewport's cell, in page units, on every side.
    padding: Numeric = 0
    subdivision: Optional[Subdivision] = None
    #: The dimensions drawn in this viewport. Only a leaf's are drawn.
    measurements: Sequence['Measure'] = ()
    #: Floating placement. Roots have these; the views inside a subdivision
    #: must not.
    rect: Optional[Rect] = None
    #: Which is in front where two floating viewports overlap. Higher is nearer
    #: the reader.
    z: int = 0
    #: A leaf's camera, in world space. None lets the viewer choose one from the label
    #: ("Front", "Top", "Preview", ...).
    camera: Optional[ViewAxes] = None

    def __post_init__(self):
        object.__setattr__(self, 'measurements', tuple(self.measurements))
        if self.camera is not None and self.subdivision is not None:
            raise ValueError("Only a leaf viewport has a camera; this one is subdivided")
        if self.rect is not None:
            rect = tuple(float(value) for value in self.rect)
            if len(rect) != 4:
                raise ValueError(f"A rect is [x, y, width, height], got {self.rect!r}")
            x, y, width, height = rect
            if width <= 0 or height <= 0:
                raise ValueError(f"A floating viewport has a positive size, got {width} x {height}")
            if x < 0 or y < 0 or x + width > 1 or y + height > 1:
                raise ValueError(
                    f"A floating viewport sits on the page: {rect} runs off it. A rect is "
                    f"fractions of the page, [x, y, width, height] from the top left."
                )
            object.__setattr__(self, 'rect', rect)

    @property
    def is_leaf(self) -> bool:
        """Return whether this is a view (gets a camera) rather than a container."""
        return self.subdivision is None

    @property
    def children(self) -> ViewportList:
        """Return the viewports inside this one, in order."""
        if self.subdivision is None:
            return ()
        return tuple(portion.viewport for portion in self.subdivision.portions)

    def taking(self, size: Size) -> Portion:
        """Return Portion(self, size): `plan.taking(Share(2))`."""
        return Portion(viewport=self, size=size)


def rows(*children: Union[Viewport, 'Subdivision', Portion], gap: Numeric = 0) -> Subdivision:
    """Return a subdivision stacking `children` top to bottom. A bare Viewport takes Share(1)."""
    return Subdivision(direction=SplitDirection.ROWS, gap=gap,
                       portions=tuple(_as_portion(child) for child in children))


def columns(*children: Union[Viewport, 'Subdivision', Portion], gap: Numeric = 0) -> Subdivision:
    """Return a subdivision setting `children` left to right. A bare Viewport takes Share(1)."""
    return Subdivision(direction=SplitDirection.COLUMNS, gap=gap,
                       portions=tuple(_as_portion(child) for child in children))


def _as_portion(child: Union[Viewport, 'Subdivision', Portion]) -> Portion:
    """Return a row or column entry as a Portion, wrapping a Subdivision in an unlabelled Viewport."""
    if isinstance(child, Portion):
        return child
    if isinstance(child, Subdivision):
        return Portion(viewport=Viewport(subdivision=child))
    return Portion(viewport=child)


def covering_page(subdivision_or_viewport: Union[Viewport, Subdivision],
                  **options) -> Viewport:
    """Return a floating viewport covering the whole sheet."""
    if isinstance(subdivision_or_viewport, Subdivision):
        return Viewport(rect=(0.0, 0.0, 1.0, 1.0), subdivision=subdivision_or_viewport,
                        **options)
    return replace(subdivision_or_viewport, rect=(0.0, 0.0, 1.0, 1.0), **options)


# ---------------------------------------------------------------------------
# default drawing layouts 
# ---------------------------------------------------------------------------

# aso what's th e difference between this and Sequence[Viewport]? oh I guess tuple has at least one?
def shop_drawing_viewports() -> ViewportList:
    """Return a shop drawing layout: a piece's four long faces down the left, a preview beside them."""
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
    """Return three world elevations and a preview, two rows of two."""
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
    """Return the default layout: a shop drawing for one timber, elevations for several."""
    return shop_drawing_viewports() if timber_count == 1 else elevation_viewports()


@dataclass(frozen=True)
class Drawing:
    """A drawing: a name, the timbers it draws, and its viewports."""

    name: str

    #: Which timbers this is a drawing of, one entry per timber: the frame's own
    #: timber objects, not copies. Frame checks this when it is built.
    timbers: Sequence['PerfectTimberWithin'] = ()

    #: The id the drawings file refers to it by. Defaults to DrawingId(name); never None once built.
    drawing_id: Optional[DrawingId] = None

    #: The floating viewports, in order (which numbers them; z sets draw order).
    #: None means the default layout; () means none.
    viewports: Optional[Sequence[Viewport]] = None

    #: The sheet, which Lengths are measured against. None (usual) lets the viewer choose; only
    #: layout.resolve_drawing needs one.
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

        # None gets the default layout; () is kept.
        viewports = (default_viewports_for(len(self.timbers))
                     if self.viewports is None else tuple(self.viewports))
        object.__setattr__(self, 'viewports', viewports)
        self._check_placement()
        self._check_each_viewport_appears_once()

    # ---------------------------------------------------------------- the tree

    @property
    def roots(self) -> ViewportList:
        """Return the root (floating) viewports."""
        return tuple(self.viewports or ())

    def walk(self) -> Iterator[Tuple[ViewportId, 'Viewport']]:
        """Yield every viewport with its id, depth first, parents before children."""
        def descend(viewport: 'Viewport', path: Tuple[int, ...]):
            yield (ViewportId(".".join(str(step) for step in path)), viewport)
            for index, child in enumerate(viewport.children):
                yield from descend(child, path + (index,))

        for index, root in enumerate(self.roots):
            yield from descend(root, (index,))

    def measurements_by_viewport(self) -> Dict[str, Tuple[Measure, ...]]:
        """Return the drawing's measurements, keyed by viewport id."""
        collected: Dict[str, Tuple[Measure, ...]] = {}
        for viewport_id, viewport in self.walk():
            if viewport.measurements:
                collected[str(viewport_id)] = tuple(viewport.measurements)
        for viewport_id, measures in self.measurements.items():
            key = str(viewport_id)
            collected[key] = collected.get(key, ()) + tuple(measures)
        return collected

    def leaves(self) -> Iterator[Tuple[ViewportId, 'Viewport']]:
        """Return every leaf viewport (one with a camera) with its id."""
        return ((id, viewport) for id, viewport in self.walk() if viewport.is_leaf)

    def get_viewport_id(self, viewport: 'Viewport') -> ViewportId:
        """Return the id of `viewport` (its position in the tree)."""
        for found, candidate in self.walk():
            if candidate is viewport:
                return found
        raise KeyError(f"{viewport!r} is not a viewport of drawing {self.drawing_id}")

    def viewport_at(self, viewport_id: ViewportId) -> Optional['Viewport']:
        """Return the viewport with id `viewport_id`, or None."""
        wanted = str(viewport_id)
        for found, viewport in self.walk():
            if str(found) == wanted:
                return viewport
        return None

    # ------------------------------------------------------------- the checks

    def _check_placement(self) -> None:
        """Raise unless every root has a rect and no subdivided viewport does."""
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
        """Raise if a viewport object appears twice (it would have two ids)."""
        seen = {}
        for viewport_id, viewport in self.walk():
            if id(viewport) in seen:
                raise ValueError(
                    f"The same viewport is at {seen[id(viewport)]} and {viewport_id} of "
                    f"drawing {self.drawing_id}. Viewports are told apart by where they "
                    f"are, so each position needs its own."
                )
            seen[id(viewport)] = viewport_id
