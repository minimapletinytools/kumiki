"""Where a drawing's code dimensions go on the sheet.

Works on the drawing wire the viewer draws (a viewport's camera and rect, the page, each
measurement's resolved ends) and the drawn members' world meshes. Layout is in sheet millimetres
(y down); `place_dimensions` returns each placement in world metres.

Each dimension, shortest first, is tried at a few lanes out on both sides, with its witness lines
either where its ends are or slid to where its two features stop. The cheapest try wins: a label or
line over the work costs most, then landing on what is already placed, leaving the viewport, and
distance from the work.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

#: A label on the sheet: cap height, and width per character, in millimetres.
TEXT_MM = 4.8
CHAR_MM = 2.8
#: The first lane's distance from the features, and lane to lane, in sheet millimetres.
BASE_MM = 5.0
PITCH_MM = 7.0
LANES = 8
#: The material grid's cell, in sheet millimetres.
CELL_MM = 0.5

#: A mesh: world vertices (n, 3) and triangle indices (m, 3).
Mesh = Tuple[np.ndarray, np.ndarray]


@dataclass
class SheetView:
    """A viewport's orthographic camera on the page: world metres to sheet millimetres, y down."""

    right: np.ndarray
    up: np.ndarray
    target: np.ndarray
    extent: float
    rect: Tuple[float, float, float, float]
    page_mm: Tuple[float, float]

    @classmethod
    def of(cls, viewport: Mapping[str, Any], page: Optional[Mapping[str, Any]]) -> Optional['SheetView']:
        """Return the view of a wire viewport, or None without a camera or page."""
        camera = viewport.get("camera")
        if not camera or not page or not viewport.get("rect"):
            return None
        return cls(np.array(camera["right"], float), np.array(camera["up"], float),
                   np.array(camera["target"], float), float(camera["extent"]),
                   tuple(viewport["rect"]), (page["width"] * 1000, page["height"] * 1000))

    @property
    def mm_per_world(self) -> float:
        return self.rect[3] * self.page_mm[1] / (2 * self.extent)

    def to_sheet(self, points) -> np.ndarray:
        """Return world points as sheet points, (n, 2)."""
        p = np.atleast_2d(np.asarray(points, float)) - self.target
        scale = self.mm_per_world
        cx = (self.rect[0] + self.rect[2] / 2) * self.page_mm[0]
        cy = (self.rect[1] + self.rect[3] / 2) * self.page_mm[1]
        return np.stack([cx + (p @ self.right) * scale, cy - (p @ self.up) * scale], axis=1)

    def direction_to_sheet(self, vector) -> np.ndarray:
        """Return a world direction on the sheet, unscaled."""
        v = np.asarray(vector, float)
        return np.array([v @ self.right, -(v @ self.up)])

    def rect_mm(self) -> Tuple[float, float, float, float]:
        """Return the viewport's left, top, right and bottom on the sheet."""
        x, y, w, h = self.rect
        return x * self.page_mm[0], y * self.page_mm[1], (x + w) * self.page_mm[0], (y + h) * self.page_mm[1]


class MaterialGrid:
    """Which sheet cells around a viewport have a drawn member on them."""

    def __init__(self, view: SheetView, meshes: Sequence[Mesh]):
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
        """Mark the cells whose centres a triangle (in cells) covers."""
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
        """Return the fraction of sheet `points` that sit on material."""
        cells = np.floor((np.atleast_2d(points) - self.origin) / CELL_MM).astype(int)
        ok = (cells[:, 0] >= 0) & (cells[:, 1] >= 0) & (cells[:, 0] < self.shape[1]) & (cells[:, 1] < self.shape[0])
        hits = np.zeros(len(cells), dtype=bool)
        hits[ok] = self.cells[cells[ok, 1], cells[ok, 0]]
        return float(hits.mean()) if len(hits) else 0.0


@dataclass
class Box:
    """A label's box on the sheet: `along` is its unit reading direction, `half` its half length and height."""

    center: np.ndarray
    along: np.ndarray
    half: Tuple[float, float]

    @property
    def across(self) -> np.ndarray:
        return np.array([-self.along[1], self.along[0]])

    def corners(self) -> np.ndarray:
        a, b = self.half
        return np.array([self.center + self.along * sa * a + self.across * sb * b
                         for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))])

    def samples(self) -> np.ndarray:
        a, b = self.half
        return np.array([self.center + self.along * u * a + self.across * v * b
                         for u in np.linspace(-1, 1, 7) for v in np.linspace(-1, 1, 3)])

    def overlaps(self, other: 'Box') -> bool:
        mine, theirs = self.corners(), other.corners()
        for axis in (self.along, self.across, other.along, other.across):
            p, q = mine @ axis, theirs @ axis
            if p.max() <= q.min() or q.max() <= p.min():
                return False
        return True

    def hits_segment(self, start: np.ndarray, end: np.ndarray) -> bool:
        d = start + np.outer(_SEGMENT_T, end - start) - self.center
        return bool(((np.abs(d @ self.along) <= self.half[0]) & (np.abs(d @ self.across) <= self.half[1])).any())


_SEGMENT_T = np.linspace(0, 1, 24)


def text_up(run: np.ndarray) -> np.ndarray:
    """Return which way a label stands on the sheet: the viewer reads it along `run`, within 90
    degrees of upright, set on the line's upper side."""
    angle = np.degrees(np.arctan2(run[1], run[0]))
    # As the viewer turns it (measurements.js dimensionLayout).
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
    """A dimension to place. `a` and `b` are its ends on the sheet; `stretch` is where along `slide`
    (world) its two features overlap, and `t0` where its ends are now along it."""

    index: int
    a: np.ndarray
    b: np.ndarray
    text: str
    slide: Optional[np.ndarray]
    stretch: Optional[Tuple[float, float]]
    t0: float = 0.0

    @property
    def span(self) -> float:
        return float(np.linalg.norm(self.b - self.a))

    @property
    def run(self) -> np.ndarray:
        return (self.b - self.a) / max(self.span, 1e-9)

    @property
    def away(self) -> np.ndarray:
        """The sheet direction a positive offset moves the line, as the viewer draws it."""
        r = self.run
        return np.array([-r[1], r[0]])


@dataclass
class Placed:
    """A tried placement: `along` in world metres (None leaves the ends), `offset` in sheet mm."""

    dim: Dim
    along: Optional[float]
    offset: float
    a: np.ndarray
    b: np.ndarray
    line: Tuple[np.ndarray, np.ndarray]
    label: Box
    cost: float


def _label_text(measure: Mapping[str, Any]) -> Optional[str]:
    """Return about the text a length's label takes, or None for anything else."""
    value = (measure.get("settled") or {}).get("value") or {}
    if value.get("unit") != "length" or value.get("value") is None:
        return None
    return f"{float(value['value']) * 1000:.0f}mm"


def _dims(viewport: Mapping[str, Any], view: SheetView) -> List[Dim]:
    """Return the viewport's code lengths that have no placement yet."""
    out = []
    for index, measure in enumerate(viewport.get("measurements") or []):
        a, b = (measure.get("a") or {}).get("at"), (measure.get("b") or {}).get("at")
        text = _label_text(measure)
        if a is None or b is None or text is None or measure.get("origin") not in (None, "code"):
            continue
        if (measure.get("placement") or {}).get("offset") is not None:
            continue
        slide, extents = measure.get("slide"), measure.get("extents") or {}
        stretch, t0, slide_world = None, 0.0, None
        if slide is not None and extents.get("a") and extents.get("b"):
            slide_world = np.array(slide, float)
            ta = [float(np.dot(p, slide_world)) for p in extents["a"]]
            tb = [float(np.dot(p, slide_world)) for p in extents["b"]]
            low, high = max(min(ta), min(tb)), min(max(ta), max(tb))
            if high > low:
                stretch, t0 = (low, high), float(np.dot(a, slide_world))
        sa, sb = view.to_sheet([a, b])
        dim = Dim(index, sa, sb, text, slide_world, stretch, t0)
        if dim.span > 0.3:
            out.append(dim)
    return out


def _candidates(dim: Dim, view: SheetView) -> List[Tuple[Optional[float], float, np.ndarray, np.ndarray]]:
    """Return the (along, offset, a, b) to try."""
    out = []
    lanes = [BASE_MM + lane * PITCH_MM for lane in range(LANES)]
    if dim.slide is not None and dim.stretch is not None:
        slide_sheet = view.direction_to_sheet(dim.slide)
        facing = float(slide_sheet @ dim.away)
        for side in (1.0, -1.0):
            # The ends slid to the end of the stretch on this side.
            along = (dim.stretch[1] if facing * side > 0 else dim.stretch[0]) - dim.t0
            shift = slide_sheet * along * view.mm_per_world
            out += [(along, side * lane, dim.a + shift, dim.b + shift) for lane in lanes]
    for side in (1.0, -1.0):
        out += [(None, side * lane, dim.a, dim.b) for lane in lanes]
    return out


def _try(dim: Dim, along, offset, a, b, grid: MaterialGrid, placed: List[Placed], rect) -> Placed:
    """Return the placement and its cost."""
    away = dim.away
    la, lb = a + away * offset, b + away * offset
    text_len = len(dim.text) * CHAR_MM + 1.5
    label = Box((la + lb) / 2 + text_up(dim.run) * (TEXT_MM / 2 + 0.3), dim.run,
                (text_len / 2 + 1.0, TEXT_MM / 2 + 0.6))
    line_pts = np.array([la + (lb - la) * t for t in np.linspace(0.05, 0.95, 16)])
    witness = np.array([p + away * offset * t for p in (a, b) for t in np.linspace(0.15, 1.0, 8)])
    cost = (120 * grid.fraction(label.samples())
            + 30 * grid.fraction(line_pts)
            + 8 * grid.fraction(witness)
            + 1000 * sum(label.overlaps(other.label) for other in placed)
            + 60 * sum(label.hits_segment(*other.line) for other in placed)
            + 60 * sum(other.label.hits_segment(la, lb) for other in placed)
            + 6 * sum(_segments_cross(la, lb, p, q) for other in placed
                      for p, q in (other.line, (other.a, other.line[0]), (other.b, other.line[1])))
            + 0.4 * abs(offset))
    x0, y0, x1, y1 = rect
    corners = label.corners()
    outside = (np.clip(x0 - corners[:, 0], 0, None).sum() + np.clip(corners[:, 0] - x1, 0, None).sum()
               + np.clip(y0 - corners[:, 1], 0, None).sum() + np.clip(corners[:, 1] - y1, 0, None).sum())
    if outside > 0:
        cost += 400 + 40 * float(outside)
    return Placed(dim, along, offset, a, b, (la, lb), label, cost)


def place_dimensions(viewport: Mapping[str, Any], page: Optional[Mapping[str, Any]],
                     meshes: Sequence[Mesh]) -> Dict[int, Dict[str, float]]:
    """Return a wire placement (`offset`, and `along` if the ends slide) for each code length in an
    orthographic `viewport` with none, by its index in the viewport's measurements."""
    view = SheetView.of(viewport, page)
    if view is None or viewport.get("projection") not in (None, "orthographic"):
        return {}
    dims = _dims(viewport, view)
    if not dims:
        return {}
    grid = MaterialGrid(view, meshes)
    rect = view.rect_mm()
    placed: List[Placed] = []
    for dim in sorted(dims, key=lambda d: d.span):
        placed.append(min((_try(dim, along, offset, a, b, grid, placed, rect)
                           for along, offset, a, b in _candidates(dim, view)), key=lambda p: p.cost))
    out = {}
    for one in placed:
        wire = {"offset": one.offset / view.mm_per_world}
        if one.along is not None:
            wire["along"] = one.along
        out[one.dim.index] = wire
    return out
