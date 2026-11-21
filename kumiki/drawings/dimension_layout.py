"""EXPERIMENT: where a drawing's dimensions go on the sheet.

Works on the wire the runner sends the viewer (a viewport's camera and rect, the page, each
measurement's resolved ends) and the drawn timbers' meshes. Everything is in sheet millimetres;
what comes out is a placement per dimension in world units: `offset` (out from the features) and
`along` (where along them the witness lines start).

For each dimension, shortest first, it tries both sides: the ends slid to where the two features
stop on that side, and lanes out from there; and the ends left where they are, a lane or two
either side (a dimension across an opening). The cheapest wins: a label or line on the work costs
most, then landing on what is already placed, leaving the viewport, and distance.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

#: A label on the sheet: cap height, and width per character, in millimetres.
TEXT_MM = 4.8
CHAR_MM = 2.8
#: The first lane's distance from the work, and lane to lane.
BASE_MM = 5.0
PITCH_MM = 7.0
LANES = 8
#: The material grid's cell, in sheet millimetres.
CELL_MM = 0.5


@dataclass
class SheetView:
    """A viewport's camera on the page: world metres to sheet millimetres, y down."""

    right: np.ndarray
    up: np.ndarray
    target: np.ndarray
    extent: float
    rect: Tuple[float, float, float, float]
    page_mm: Tuple[float, float]

    @classmethod
    def of(cls, viewport: Dict[str, Any], page: Dict[str, float]) -> Optional['SheetView']:
        camera = viewport.get("camera")
        if not camera or not page:
            return None
        return cls(np.array(camera["right"], float), np.array(camera["up"], float),
                   np.array(camera["target"], float), float(camera["extent"]),
                   tuple(viewport["rect"]), (page["width"] * 1000, page["height"] * 1000))

    @property
    def mm_per_world(self) -> float:
        return self.rect[3] * self.page_mm[1] / (2 * self.extent)

    def to_sheet(self, points) -> np.ndarray:
        p = np.atleast_2d(np.asarray(points, float)) - self.target
        scale = self.mm_per_world
        cx = (self.rect[0] + self.rect[2] / 2) * self.page_mm[0]
        cy = (self.rect[1] + self.rect[3] / 2) * self.page_mm[1]
        return np.stack([cx + (p @ self.right) * scale, cy - (p @ self.up) * scale], axis=1)

    def direction_to_sheet(self, vector) -> np.ndarray:
        v = np.asarray(vector, float)
        return np.array([v @ self.right, -(v @ self.up)])

    def rect_mm(self) -> Tuple[float, float, float, float]:
        x, y, w, h = self.rect
        return x * self.page_mm[0], y * self.page_mm[1], (x + w) * self.page_mm[0], (y + h) * self.page_mm[1]


class MaterialGrid:
    """Which sheet cells have a drawn timber on them: its triangles projected and filled."""

    def __init__(self, view: SheetView, meshes: Sequence[Tuple[np.ndarray, np.ndarray]]):
        x0, y0, x1, y1 = view.rect_mm()
        margin = 60.0
        self.origin = np.array([x0 - margin, y0 - margin])
        self.shape = (int((y1 - y0 + 2 * margin) / CELL_MM) + 1, int((x1 - x0 + 2 * margin) / CELL_MM) + 1)
        self.cells = np.zeros(self.shape, dtype=bool)
        for vertices, faces in meshes:
            sheet = (view.to_sheet(vertices) - self.origin) / CELL_MM
            for tri in faces:
                self._fill(sheet[tri])

    def _fill(self, tri: np.ndarray) -> None:
        lo = np.maximum(np.floor(tri.min(axis=0)).astype(int), 0)
        hi = np.minimum(np.ceil(tri.max(axis=0)).astype(int), [self.shape[1] - 1, self.shape[0] - 1])
        if (hi < lo).any():
            return
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0] + 1) + 0.5, np.arange(lo[1], hi[1] + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = tri
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-9:
            return
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / det
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / det
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (1 - l1 - l2 >= -1e-6)
        self.cells[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1] |= inside

    def fraction(self, points: np.ndarray) -> float:
        """How many of `points` (sheet mm) sit on material, as a fraction."""
        cells = np.floor((np.atleast_2d(points) - self.origin) / CELL_MM).astype(int)
        ok = (cells[:, 0] >= 0) & (cells[:, 1] >= 0) & (cells[:, 0] < self.shape[1]) & (cells[:, 1] < self.shape[0])
        hits = np.zeros(len(cells), dtype=bool)
        hits[ok] = self.cells[cells[ok, 1], cells[ok, 0]]
        return float(hits.mean()) if len(hits) else 0.0


@dataclass
class Box:
    """An oriented label box on the sheet."""

    center: np.ndarray
    along: np.ndarray
    half: Tuple[float, float]

    def corners(self) -> np.ndarray:
        across = np.array([-self.along[1], self.along[0]])
        a, b = self.half
        return np.array([self.center + self.along * sa * a + across * sb * b
                         for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])

    def samples(self) -> np.ndarray:
        across = np.array([-self.along[1], self.along[0]])
        a, b = self.half
        return np.array([self.center + self.along * u * a + across * v * b
                         for u in np.linspace(-1, 1, 7) for v in np.linspace(-1, 1, 3)])

    def overlaps(self, other: 'Box') -> bool:
        mine, theirs = self.corners(), other.corners()
        for axis in (self.along, np.array([-self.along[1], self.along[0]]),
                     other.along, np.array([-other.along[1], other.along[0]])):
            p, q = mine @ axis, theirs @ axis
            if p.max() <= q.min() or q.max() <= p.min():
                return False
        return True

    def hits_segment(self, start: np.ndarray, end: np.ndarray) -> bool:
        return any(self.contains(start + (end - start) * t) for t in np.linspace(0, 1, 24))

    def contains(self, point: np.ndarray) -> bool:
        d = point - self.center
        across = np.array([-self.along[1], self.along[0]])
        return abs(d @ self.along) <= self.half[0] and abs(d @ across) <= self.half[1]


def text_up(run: np.ndarray) -> np.ndarray:
    """Which way a label's text stands, on the sheet (y down): the viewer turns it to read along
    the run, kept within 90 degrees of upright, and sets it above the line (text-after-edge)."""
    angle = np.degrees(np.arctan2(run[1], run[0]))
    while angle > 90:
        angle -= 180
    while angle < -90:
        angle += 180
    a = np.radians(angle)
    return np.array([np.sin(a), -np.cos(a)])


def _segments_cross(p1, p2, q1, q2) -> bool:
    def orient(a, b, c):
        return np.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    return (orient(p1, p2, q1) * orient(p1, p2, q2) < 0) and (orient(q1, q2, p1) * orient(q1, q2, p2) < 0)


@dataclass
class Dim:
    index: int
    a: np.ndarray            # sheet mm, as resolved
    b: np.ndarray
    text: str
    slide_world: Optional[np.ndarray]
    stretch: Optional[Tuple[float, float]]   # the features' shared stretch along slide, world, from the ends
    t0: float = 0.0          # where the ends are now along slide

    @property
    def span(self) -> float:
        return float(np.linalg.norm(self.b - self.a))

    @property
    def run(self) -> np.ndarray:
        return (self.b - self.a) / max(self.span, 1e-9)

    @property
    def away(self) -> np.ndarray:
        r = self.run
        return np.array([-r[1], r[0]])


@dataclass
class Placed:
    dim: Dim
    along_world: Optional[float]
    offset_mm: float
    a: np.ndarray
    b: np.ndarray
    line: Tuple[np.ndarray, np.ndarray]
    label: Box
    cost: float = 0.0
    why: Dict[str, float] = field(default_factory=dict)


def _label_text(measure: Dict[str, Any]) -> Optional[str]:
    value = ((measure.get("settled") or {}).get("value") or {})
    if value.get("unit") != "length" or value.get("value") is None:
        return None
    return f"{float(value['value']) * 1000:.0f}mm"


def _dims(viewport: Dict[str, Any], view: SheetView) -> List[Dim]:
    out = []
    for index, measure in enumerate(viewport.get("measurements") or []):
        a, b = (measure.get("a") or {}).get("at"), (measure.get("b") or {}).get("at")
        text = _label_text(measure)
        if text is not None and measure.get("note"):
            text = f"{text} {measure['note']}"
        if a is None or b is None or text is None or measure.get("origin") not in (None, "code"):
            continue
        if measure.get("placement") and measure["placement"].get("offset") is not None:
            continue
        slide = measure.get("slide")
        stretch, t0, slide_world = None, 0.0, None
        extents = measure.get("extents") or {}
        if slide is not None and extents.get("a") and extents.get("b"):
            slide_world = np.array(slide, float)
            ta = sorted(float(np.dot(p, slide_world)) for p in extents["a"])
            tb = sorted(float(np.dot(p, slide_world)) for p in extents["b"])
            low, high = max(ta[0], tb[0]), min(ta[-1], tb[-1])
            if high > low:
                stretch = (low, high)
                t0 = float(np.dot(a, slide_world))
        sa, sb = view.to_sheet([a, b])
        dim = Dim(index, sa, sb, text, slide_world, stretch, t0)
        if dim.span > 0.3:
            out.append(dim)
    return out


def _candidates(dim: Dim, view: SheetView) -> List[Tuple[Optional[float], float, np.ndarray, np.ndarray]]:
    """(along in world, offset in sheet mm, a, b) to try."""
    out = []
    scale = view.mm_per_world
    if dim.slide_world is not None and dim.stretch is not None:
        slide_sheet = view.direction_to_sheet(dim.slide_world)
        facing = float(slide_sheet @ dim.away)
        for side in (1.0, -1.0):
            # The stretch's end on this side: the ends slid there, so witness lines start where the
            # features stop.
            end = dim.stretch[1] if facing * side > 0 else dim.stretch[0]
            along = end - dim.t0
            shift = slide_sheet * along * scale
            a, b = dim.a + shift, dim.b + shift
            for lane in range(LANES):
                out.append((along, side * (BASE_MM + lane * PITCH_MM), a, b))
    for side in (1.0, -1.0):
        for lane in range(LANES):
            out.append((None, side * (BASE_MM + lane * PITCH_MM), dim.a, dim.b))
    return out


def _try(dim: Dim, along, offset, a, b, grid: MaterialGrid, placed: List[Placed], rect, bounded: bool = True) -> Placed:
    away = dim.away
    la, lb = a + away * offset, b + away * offset
    text_len = len(dim.text) * CHAR_MM + 1.5
    label = Box((la + lb) / 2 + text_up(dim.run) * (TEXT_MM / 2 + 0.3), dim.run, (text_len / 2 + 1.0, TEXT_MM / 2 + 0.6))
    line_pts = np.array([la + (lb - la) * t for t in np.linspace(0.05, 0.95, 16)])
    # The witness line's stretch past the features: a witness over the work reads as an edge.
    wit = np.array([p + away * offset * t for p in (a, b) for t in np.linspace(0.15, 1.0, 8)])
    why = {
        "label on work": 120 * grid.fraction(label.samples()),
        "line on work": 30 * grid.fraction(line_pts),
        "witness on work": 8 * grid.fraction(wit),
        "label on labels": 1000 * sum(label.overlaps(other.label) for other in placed),
        "label on lines": 60 * sum(label.hits_segment(*other.line) for other in placed),
        "line through labels": 60 * sum(other.label.hits_segment(la, lb) for other in placed),
        "crossings": 6 * sum(_segments_cross(la, lb, p, q) for other in placed
                             for p, q in (other.line, (other.a, other.line[0]), (other.b, other.line[1]))),
        "distance": 0.4 * abs(offset),
    }
    x0, y0, x1, y1 = rect
    corners = label.corners()
    outside = np.clip(x0 - corners[:, 0], 0, None).sum() + np.clip(corners[:, 0] - x1, 0, None).sum() \
        + np.clip(y0 - corners[:, 1], 0, None).sum() + np.clip(corners[:, 1] - y1, 0, None).sum()
    why["off the viewport"] = (400 * float(outside > 0) + 40 * float(outside)) if bounded else 0.0
    return Placed(dim, along, offset, a, b, (la, lb), label, sum(why.values()), why)


def place_viewport(viewport: Dict[str, Any], page: Dict[str, float],
                   meshes: Sequence[Tuple[np.ndarray, np.ndarray]], bounded: bool = True) -> List[Placed]:
    """Return a placement for each code dimension in `viewport` that has none. Unbounded, the
    viewport's edge costs nothing: where the dimensions want to go, to size the viewport by."""
    view = SheetView.of(viewport, page)
    if view is None:
        return []
    dims = _dims(viewport, view)
    if not dims:
        return []
    grid = MaterialGrid(view, meshes)
    rect = view.rect_mm()
    placed: List[Placed] = []
    for dim in sorted(dims, key=lambda d: d.span):
        best = min((_try(dim, along, offset, a, b, grid, placed, rect, bounded)
                    for along, offset, a, b in _candidates(dim, view)), key=lambda p: p.cost)
        placed.append(best)
    return placed


def placement_wire(one: Placed, view_scale: float) -> Dict[str, Any]:
    """The wire placement: offset and along in world metres."""
    wire: Dict[str, Any] = {"offset": one.offset_mm / view_scale}
    if one.along_world is not None:
        wire["along"] = one.along_world
    return wire


#: Room kept between what is drawn and the viewport's edge, in sheet mm.
EDGE_MM = 4.0


def material_bounds(grid: MaterialGrid) -> Optional[Tuple[float, float, float, float]]:
    rows, cols = np.nonzero(grid.cells)
    if not len(rows):
        return None
    x0, y0 = grid.origin + np.array([cols.min(), rows.min()]) * CELL_MM
    x1, y1 = grid.origin + np.array([cols.max() + 1, rows.max() + 1]) * CELL_MM
    return float(x0), float(y0), float(x1), float(y1)


def bands(placed: Sequence[Placed], work: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """How far what is placed reaches past the work: left, top, right, bottom, in sheet mm."""
    points = [p for one in placed for p in (*one.label.corners(), *one.line)]
    if not points:
        return 0.0, 0.0, 0.0, 0.0
    pts = np.array(points)
    x0, y0, x1, y1 = work
    return (max(0.0, x0 - pts[:, 0].min()), max(0.0, y0 - pts[:, 1].min()),
            max(0.0, pts[:, 0].max() - x1), max(0.0, pts[:, 1].max() - y1))


def refit(viewport: Dict[str, Any], view: SheetView, work, band, scale: float) -> None:
    """Shrink the viewport's model by `scale` and centre the model and its bands in the rect."""
    camera = viewport["camera"]
    left, top, right, bottom = band
    new_extent = view.extent / scale
    mm_per_world = view.mm_per_world * scale
    # Where the work's centre is now, from the viewport's centre, in sheet mm.
    rx0, ry0, rx1, ry1 = view.rect_mm()
    cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
    wx, wy = ((work[0] + work[2]) / 2 - cx) * scale, ((work[1] + work[3]) / 2 - cy) * scale
    # Where it should be: moved off whichever side carries more.
    want_x, want_y = (left - right) / 2, (top - bottom) / 2
    dx, dy = want_x - wx, want_y - wy
    target = np.array(camera["target"], float) - view.right * dx / mm_per_world + view.up * dy / mm_per_world
    camera["target"] = target.tolist()
    camera["extent"] = new_extent


def fit_scale(view: SheetView, work, band) -> float:
    """The largest scale (<= 1) at which the work and its bands fit the rect."""
    rx0, ry0, rx1, ry1 = view.rect_mm()
    width, height = work[2] - work[0], work[3] - work[1]
    room_x = (rx1 - rx0) - 2 * EDGE_MM - band[0] - band[2]
    room_y = (ry1 - ry0) - 2 * EDGE_MM - band[1] - band[3]
    # No room at all (the bands alone overflow) shrinks only so far: past that the dimensions
    # crowd back onto the work rather than the work vanishing.
    return float(max(MIN_SCALE, min(1.0, room_x / max(width, 1e-6), room_y / max(height, 1e-6))))


MIN_SCALE = 0.6
