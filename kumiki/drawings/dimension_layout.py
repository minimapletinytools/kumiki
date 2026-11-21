"""Where a drawing's dimensions go on the sheet: `with_placed_dimensions` gives each one a placement.

Each view is framed as the viewer frames it (kigumi_drawing_view_helpers) and laid out in sheet
millimetres, y down. Each dimension, shortest first, is tried at a few lanes out on both sides,
with its witness lines either where its ends are or slid to where its two features stop. The
cheapest try wins: a label or line over the drawn timbers costs most, then landing on what is
already placed, leaving the viewport, and distance from the work.
"""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .drawing import Drawing, Page
from .measure import FromViewport, Measure, MeasurementOperation, MeasurementPlacement, ViewAxes

if TYPE_CHECKING:
    from ..timber import CutTimber, Frame

#: The sheet the viewer draws code drawings on (A3 landscape), in metres.
SHEET = Page(0.420, 0.297)

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

    @property
    def axes(self) -> ViewAxes:
        return ViewAxes(right=self.right.tolist(), up=self.up.tolist(), look=np.cross(self.up, self.right).tolist())

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


def place(dims: Sequence[Dim], view: SheetView, meshes: Sequence[Mesh]) -> Dict[int, MeasurementPlacement]:
    """Return a placement for each of `dims`, by its index, with the offset as the viewer reads it
    for the ends in the order given (positive along `Dim.away`)."""
    if not dims:
        return {}
    grid = MaterialGrid(view, meshes)
    rect = view.rect_mm()
    placed: List[Placed] = []
    for dim in sorted(dims, key=lambda d: d.span):
        placed.append(min((_try(dim, along, offset, a, b, grid, placed, rect)
                           for along, offset, a, b in _candidates(dim, view)), key=lambda p: p.cost))
    return {one.dim.index: MeasurementPlacement(offset=one.offset / view.mm_per_world, along=one.along)
            for one in placed}


# --- from a drawing ---------------------------------------------------------------------------

#: A shop drawing's long faces: label -> (timber axis the face looks along, its sign), as the viewer has them.
_LONG_FACES = {"front": ("height", 1), "right": ("width", 1), "back": ("height", -1), "left": ("width", -1)}
#: World elevations: label -> (right, up), as the viewer has them.
_ELEVATIONS = {"front": ((1, 0, 0), (0, 0, 1)), "top": ((1, 0, 0), (0, 1, 0)), "right": ((0, 1, 0), (0, 0, 1))}


def sheet_views(drawing: Drawing, cuts: Sequence['CutTimber'], page: Page = SHEET) -> Dict[str, SheetView]:
    """Return each orthographic leaf's view, by viewport id, framed as the viewer frames a code drawing
    of `cuts`: one timber's long faces, several timbers' world elevations, or a leaf's own camera."""
    from .kigumi_drawing_view_helpers import camera_looking_at_face, view_extent, world_bounds
    from .layout import resolve_viewports

    def floats(vector) -> List[float]:
        return [float(v) for v in vector]

    centre, half = world_bounds(cuts)
    page_mm = (float(page.width) * 1000, float(page.height) * 1000)
    views = {}
    for placed in resolve_viewports(drawing.roots, page):
        x, y, w, h = (float(v) for v in placed.rect)
        rect = (x, y, w, h)
        label = (placed.label or "").lower()
        if placed.viewport.camera is not None:
            right = floats(placed.viewport.camera.right)
            up = floats(placed.viewport.camera.up)
            right, up = (list(np.array(v) / np.linalg.norm(v)) for v in (right, up))
        elif len(cuts) == 1 and label in _LONG_FACES:
            timber = cuts[0].timber
            axis, sign = _LONG_FACES[label]
            normal = floats(timber.get_height_direction_global() if axis == "height"
                            else timber.get_width_direction_global())
            frame = camera_looking_at_face([v * sign for v in normal], floats(timber.get_length_direction_global()))
            right, up = frame.right, frame.up
        elif len(cuts) != 1 and label in _ELEVATIONS:
            right, up = (list(map(float, v)) for v in _ELEVATIONS[label])
        else:
            continue
        aspect = rect[2] * page_mm[0] / (rect[3] * page_mm[1])
        views[str(placed.id)] = SheetView(np.array(right, float), np.array(up, float), np.array(centre, float),
                                          view_extent(half, right, up, aspect), rect, page_mm)
    return views


def _world_mesh(cut: 'CutTimber') -> Optional[Mesh]:
    """Return a cut timber's world mesh, or None if it has none."""
    from ..csg.cutcsg import adopt_csg
    from ..csg.triangles import triangulate_cutcsg
    from ..rule import Transform

    mesh = triangulate_cutcsg(adopt_csg(cut.timber.transform, Transform.identity(),
                                        cut.render_timber_with_cuts_csg_local())).mesh
    return (np.asarray(mesh.vertices, float), np.asarray(mesh.faces, int)) if len(mesh.faces) else None


def _dim(index: int, measure: Measure, view: SheetView, frame: 'Frame') -> Optional[Tuple[Dim, bool]]:
    """Return a length in a view as a Dim, its ends in the order the viewer has them, and whether
    that order is the measure's own reversed; None for anything else."""
    from .feature_span import feature_span
    from .kigumi_measuring_helpers import place_pair, world_geometry

    if not isinstance(measure.plane, FromViewport):
        return None
    from ..csg.feature_paths import to_feature_path

    path_a, path_b = to_feature_path(measure.anchor_a, frame), to_feature_path(measure.anchor_b, frame)
    if path_a is None or path_b is None:
        return None
    # The viewer runs a length from the anchor whose path sorts first (Measure.wire_anchors).
    swapped = not path_a.sort_key <= path_b.sort_key
    first, second = (measure.anchor_b, measure.anchor_a) if swapped else (measure.anchor_a, measure.anchor_b)
    axes = view.axes
    spans = []
    for handle in (first, second):
        cut = frame.cut_timber_of(handle.timber)
        if cut is None:
            return None
        spans.append(feature_span(handle, cut.render_timber_with_cuts_csg_local(), axes.look))
    if spans[0] is None or spans[1] is None:
        return None
    placement = place_pair(world_geometry(first), world_geometry(second), spans[0], spans[1], measure.kind,
                           axes.look, axes, False)
    settled = placement.settled
    if (placement.kind is None or placement.kind.operation is not MeasurementOperation.DISTANCE
            or placement.anchors is None or settled.unit != "length" or settled.value is None):
        return None
    a, b = (np.array([float(v) for v in end], float) for end in placement.anchors)
    stretch, t0, slide = None, 0.0, None
    ends = placement.extents
    if placement.slide is not None and ends[0] is not None and ends[1] is not None:
        slide = np.array([float(v) for v in placement.slide], float)
        ta = [float(np.dot([float(v) for v in p], slide)) for p in ends[0]]
        tb = [float(np.dot([float(v) for v in p], slide)) for p in ends[1]]
        low, high = max(min(ta), min(tb)), min(max(ta), max(tb))
        if high > low:
            stretch, t0 = (low, high), float(a @ slide)
    sa, sb = view.to_sheet([a, b])
    dim = Dim(index, sa, sb, f"{float(settled.value) * 1000:.0f}mm", slide, stretch, t0)
    return (dim, swapped) if dim.span > 0.3 else None


def with_placed_dimensions(drawing: Drawing, frame: 'Frame', page: Page = SHEET) -> Drawing:
    """Return `drawing` with a placement on each of its lengths (in `Drawing.measurements`) that has none,
    in the orthographic views the viewer frames on `page`."""
    cuts = [cut for cut in (frame.cut_timber_of(timber) for timber in drawing.timbers) if cut is not None]
    views = sheet_views(drawing, cuts, page)
    meshes = [mesh for mesh in (_world_mesh(cut) for cut in cuts) if mesh is not None]
    measurements = {}
    for viewport_id, measures in drawing.measurements.items():
        measures = list(measures)
        view = views.get(str(viewport_id))
        if view is None:
            measurements[viewport_id] = measures
            continue
        found = {}
        for index, measure in enumerate(measures):
            one = _dim(index, measure, view, frame) if measure.placement is None else None
            if one is not None:
                found[index] = one
        for index, placement in place([dim for dim, _ in found.values()], view, meshes).items():
            if found[index][1] and placement.offset is not None:
                # The measure's own order runs the other way: wire_anchors negates it back.
                placement = replace(placement, offset=-placement.offset)
            measures[index] = replace(measures[index], placement=placement)
        measurements[viewport_id] = measures
    return replace(drawing, measurements=measurements)
