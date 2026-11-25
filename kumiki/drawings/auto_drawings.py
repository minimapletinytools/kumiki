"""Generated drawings: a frame's plan and a shop drawing per distinct piece, dimensioned by auto_dimensioning.

The plan is solved in the world's front and top elevations from a fixed timber's reference features
and bottom end; each piece on its own four long faces, plus any extra views asked for, from its
reference features and bottom end. Matching pieces (match_timbers) share one shop drawing.

Dimension placement (`with_placed_dimensions`): each view is framed as the viewer frames it
(kigumi_drawing_view_helpers) and laid out in sheet millimetres, y down. Each dimension, shortest
first, is tried at a few lanes out on both sides, with its witness lines either where its ends are or
slid to where its two features stop. The cheapest try wins: a label or line over the drawn timbers
costs most, then landing on what is already placed, leaving the viewport, and distance from the work.
"""

from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..csg.assumptions import sheet_axis_assumptions, square_assumptions
from ..csg.carriers import Row
from ..csg.cutcsg import Datum, MidplaneFeature, OwnedFeatureHit, measured_by_default
from ..csg.feature_paths import FeatureHandle, hit_identity
from ..csg.required_features import planning_features, required_features
from ..csg.symmetry import SymmetricTimberGroup, SymmetryKind, match_timbers
from ..geometry import Plane
from ..identity import DrawingId, ViewportId
from ..rule import Orientation, Transform, create_v3
from ..finishing import Finishing
from ..timber import CutTimber, Frame, PerfectTimberWithin
from .auto_dimensioning import (DEFAULT_POLICY, AutoDimensioning, Criterion, DimensionCandidate, PickContext, Policy,
                                auto_dimension, coincidence_assumptions, derived_edge_anchors, faces_to_edges, fixed,
                                is_reference, measurable_targets, sheet_candidates, without_edges_on_faces)
from .drawing import ELEVATION_IDS, Drawing, Page, Viewport, columns, covering_page, elevation_viewports, rows
from .measure import (Auto, Beside, DimensionSide, FromViewport, Measure, MeasurementOperation, Offset, Placement,
                      ViewAxes)
from ..user_warnings import warn_user
from .measure_solving import DrawingSolve
from .visibility import visible_by_view
from .xray import xray_sides

#: World elevations for the plan: name -> (right, up, look).
PLAN_VIEWS = {
    "top": ((1, 0, 0), (0, 1, 0), (0, 0, -1)),
    "front": ((1, 0, 0), (0, 0, 1), (0, 1, 0)),
}

#: A shop drawing's long-face views: name -> (timber axis the face looks along, its sign).
SHOP_VIEWS = {"front": ("height", 1), "right": ("width", 1), "back": ("height", -1), "left": ("width", -1)}

#: Extra views for one piece's shop drawing, by label, given its cut timber.
ExtraViews = Callable[[CutTimber], Mapping[str, ViewAxes]]

Sheet = Tuple[ViewAxes, Transform]


def _feature_key(handle: FeatureHandle) -> Tuple:
    return hit_identity(handle.feature, handle.owner)


def _sheet(axes: ViewAxes) -> Sheet:
    """Return `axes` and the sheet they draw on."""
    return axes, Transform(position=create_v3(0, 0, 0), orientation=Orientation.from_x_and_y(axes.right, axes.up))


def _plan_sheets() -> Dict[str, Sheet]:
    return {view: _sheet(ViewAxes(look=create_v3(*look), right=create_v3(*right), up=create_v3(*up)))
            for view, (right, up, look) in PLAN_VIEWS.items()}


def shop_sheets(timber: PerfectTimberWithin) -> Dict[str, Sheet]:
    """Return one sheet per long face, square on, the length across the sheet."""
    along = timber.get_length_direction_global()
    axes = {"width": timber.get_width_direction_global(), "height": timber.get_height_direction_global()}
    sheets = {}
    for view, (axis, sign) in SHOP_VIEWS.items():
        normal = axes[axis] * sign
        sheets[view] = _sheet(ViewAxes(look=-normal, right=along, up=normal.cross(along)))
    return sheets


def _end_datum(targets: Sequence[FeatureHandle], timber: PerfectTimberWithin) -> FeatureHandle:
    """Return the face nearest the bottom end that a piece's length is measured from.

    A face square to the length if there is one, else one cut across it at a slant (within 60
    degrees of square); never one marked to avoid measuring from.
    """
    along = [float(v) for v in timber.get_length_direction_global()]
    square, slanted = [], []
    for handle in targets:
        plane = handle.feature.locate_simple_unbounded(handle.owner)
        if not isinstance(plane, Plane) or handle.feature.properties.datum is Datum.AVOID:
            continue
        normal = [float(v) for v in timber.transform.local_to_global_direction(plane.normal)]
        across = abs(sum(a * b for a, b in zip(normal, along)))
        if across < 0.5:
            continue
        point = [float(v) for v in timber.transform.local_to_global(plane.point)]
        end = (sum(a * b for a, b in zip(point, along)), handle)
        (square if abs(across - 1) <= 1e-9 else slanted).append(end)
    return min(square or slanted, key=lambda end: end[0])[1]


def _rows(handles: Sequence[FeatureHandle], solve: DrawingSolve) -> List[Row]:
    return [row for handle in handles for row in solve.dof_rows(handle)]


def _dimension(cut_timbers: Sequence[CutTimber], targets: Sequence[FeatureHandle], known: Sequence[FeatureHandle],
               sheets: Mapping[str, Sheet], solve: DrawingSolve, policy: Policy, onto_edges: bool = True) -> AutoDimensioning:
    """Return dimensions in `sheets` solving `targets`, starting from `known`; with `onto_edges`, picked
    faces are moved onto their nearest edges."""
    carriers = solve.carriers
    directed = list({_feature_key(handle): handle for handle in [*targets, *known]}.values())
    assumptions = square_assumptions(directed, carriers)
    for _, sheet in sheets.values():
        assumptions += sheet_axis_assumptions(directed, carriers, sheet)

    views = {view: axes for view, (axes, _) in sheets.items()}
    anchors = [handle for handle in directed if not isinstance(handle.feature, MidplaneFeature)]
    # Edges where faces meet (a shoulder against a face) draw as points, which a slanted face needs.
    anchors += [edge for cut in cut_timbers for edge in derived_edge_anchors(
        cut, [handle for handle in directed if handle.timber is cut.timber], views)]
    # Edges lying on a face seen edge-on are measured through that face, and moved onto after solving.
    visible = without_edges_on_faces(visible_by_view(anchors, views, cut_timbers), views)
    measurable, visible = measurable_targets(targets, visible, views, cut_timbers, directed, carriers)
    assumptions += coincidence_assumptions(visible, views, solve)

    known_rows = _rows(known, solve) + [row for assumption in assumptions for row in assumption.rows]
    revealed = set()
    for view, handles in visible.items():
        tagged = [handle for handle in handles if xray_sides(handle.hit)]
        if tagged:
            ordinary = visible_by_view(tagged, {view: views[view]}, cut_timbers, allow_xray=False)[view]
            revealed.update((view, handle) for handle in set(tagged).difference(ordinary))
    if revealed:
        @fixed
        def needs_xray(candidate: DimensionCandidate, context: PickContext) -> float:
            return float(any((candidate.view, end) in revealed
                             for end in (candidate.measure.anchor_a, candidate.measure.anchor_b)))
        policy = replace(policy, prefer=(*policy.prefer, needs_xray))
    result = auto_dimension(sheet_candidates(visible, views, solve), measurable, known_rows, solve, policy)
    return faces_to_edges(result, cut_timbers, directed, views, carriers) if onto_edges else result


def solve_plan(cut_timbers: Sequence[CutTimber], fixed_path: str, dimensioned: Optional[Sequence[CutTimber]] = None,
               policy: Policy = DEFAULT_POLICY, onto_edges: bool = True) -> AutoDimensioning:
    """Return the plan's dimensions in the world's top and front elevations, from the timber at `fixed_path`:
    its reference faces and bottom end. `dimensioned` is which members are solved (all by default)."""
    solve = DrawingSolve(cut_timbers)
    fixed = next(cut for cut in cut_timbers if cut.timber.ticket.path == fixed_path)
    body = fixed.get_extended_rough_csg_with_perfect_features_local()
    faces = [FeatureHandle(timber=fixed.timber, hit=OwnedFeatureHit(feature=feature, owner=body))
             for feature in body.get_declared_features()
             if feature.feature_type().name == "FACE" and not isinstance(feature, MidplaneFeature)
             and measured_by_default(feature.properties.purpose)]
    known = [handle for handle in faces if is_reference(handle)] + [_end_datum(faces, fixed.timber)]
    targets = [required.handle for cut in (dimensioned or cut_timbers) for required in planning_features(cut)]
    # The fixed timber's own faces are solved too.
    targets = list({_feature_key(handle): handle for handle in targets + faces}.values())
    return _dimension(cut_timbers, targets, known, _plan_sheets(), solve, policy, onto_edges)


def plan_drawing(cut_timbers: Sequence[CutTimber], fixed_path: str, name: str,
                 dimensioned: Optional[Sequence[CutTimber]] = None, policy: Policy = DEFAULT_POLICY) -> Drawing:
    """Return the whole frame in world elevations, dimensioned by solve_plan; every timber is drawn."""
    result = solve_plan(cut_timbers, fixed_path, dimensioned, policy)
    measurements: Dict = {ELEVATION_IDS[view]: [] for view in PLAN_VIEWS}
    for pick in result.picks:
        measurements[ELEVATION_IDS[pick.candidate.view]].append(pick.candidate.measure)
    return Drawing(name=name, timbers=[cut.timber for cut in cut_timbers],
                   viewports=elevation_viewports(), measurements=measurements)


def in_views(views: Sequence[str]) -> Criterion:
    """Return a criterion preferring a dimension drawn in one of `views`."""
    @fixed
    def criterion(candidate: DimensionCandidate, context: PickContext) -> float:
        return 0.0 if candidate.view in views else 1.0
    return criterion


def solve_piece(cut: CutTimber, extra_views: Mapping[str, ViewAxes] = {}, policy: Policy = DEFAULT_POLICY,
                onto_edges: bool = True) -> AutoDimensioning:
    """Return one piece's dimensions on its four long faces and any `extra_views`, solving every required
    feature from its reference faces and bottom end."""
    solve = DrawingSolve([cut])
    targets = list({_feature_key(required.handle): required.handle for required in required_features(cut)}.values())
    known = [handle for handle in targets if is_reference(handle)] + [_end_datum(targets, cut.timber)]
    sheets = {**shop_sheets(cut.timber), **{label: _sheet(axes) for label, axes in extra_views.items()}}
    if extra_views:
        policy = replace(policy, prefer=(in_views(list(extra_views)), *policy.prefer))
    return _dimension([cut], targets, known, sheets, solve, policy, onto_edges)


def piece_drawing(group: SymmetricTimberGroup, extra_views: Mapping[str, ViewAxes] = {},
                  policy: Policy = DEFAULT_POLICY) -> Drawing:
    """Return one shop drawing for a group of matching pieces, dimensioned on its representative.

    `extra_views` are more views, by label, in world space; they sit under the preview, and what can
    be dimensioned in them is. The drawing is named with how many to make; its id stays the
    representative's path.
    """
    cut = group.representative
    result = solve_piece(cut, extra_views, policy)
    labels = {view: view.capitalize() for view in SHOP_VIEWS}
    labels.update({label: label for label in extra_views})

    viewports = (covering_page(columns(
        rows(*(Viewport(label=labels[view]) for view in SHOP_VIEWS)),
        rows(Viewport(label="Preview"), *(Viewport(label=label, camera=axes) for label, axes in extra_views.items())),
    )),)
    ids = _ids_by_label(viewports)
    measurements: Dict[ViewportId, List] = {ids[labels[view]]: [] for view in labels}
    for pick in result.picks:
        measurements[ids[labels[pick.candidate.view]]].append(pick.candidate.measure)
    path = cut.timber.ticket.path
    return Drawing(name=f"{path}{_count(group)} (generated)", drawing_id=DrawingId(f"{path} (generated)"),
                   timbers=[cut.timber], viewports=viewports, measurements=measurements)


def _ids_by_label(viewports: Sequence[Viewport]) -> Dict[str, ViewportId]:
    """Return each labelled leaf's id in `viewports`."""
    return {viewport.label: viewport_id for viewport_id, viewport in Drawing(name="", viewports=viewports).walk()
            if viewport.is_leaf and viewport.label}


def _count(group: SymmetricTimberGroup) -> str:
    """Return " ×N" for a group of N > 1, with ", M mirrored" when M of them are reflections."""
    if not group.matches:
        return ""
    mirrored = sum(1 for match in group.matches if match.kind is SymmetryKind.REFLECTION)
    return f" ×{1 + len(group.matches)}" + (f", {mirrored} mirrored" if mirrored else "")


def with_auto_drawings(frame: Frame, fixed_path: str, extra_views: Optional[ExtraViews] = None,
                       dimensioned: Optional[Callable[[CutTimber], bool]] = None) -> Frame:
    """Return `frame` with a finishing routine adding a generated plan and a shop drawing per distinct piece,
    their dimensions placed clear of the work (with_placed_dimensions).

    `fixed_path` names the timber the plan is measured from. `extra_views` adds views to a piece's
    shop drawing; `dimensioned` picks which members the plan dimensions (all by default).
    """
    cut_timbers = list(frame.cut_timbers)
    members = [cut for cut in cut_timbers if dimensioned(cut)] if dimensioned else None

    def generate(finishing: Finishing) -> None:
        groups = match_timbers(cut_timbers)
        finishing.progress(0, 1 + len(groups), "plan")
        plan = plan_drawing(cut_timbers, fixed_path, f"{frame.name} plan (generated)", members)
        finishing.add_drawing(with_placed_dimensions(plan, frame))
        for done, group in enumerate(groups, start=1):
            finishing.progress(done, 1 + len(groups), group.representative.timber.ticket.path)
            piece = piece_drawing(group, extra_views(group.representative) if extra_views else {})
            finishing.add_drawing(with_placed_dimensions(piece, frame))

    return frame.with_finishing(generate)


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

    def material(self) -> np.ndarray:
        """Return the centres of the cells with material on them, in sheet mm, (n, 2)."""
        if not hasattr(self, "_material"):
            rows, cols = np.nonzero(self.cells)
            self._material = self.origin + (np.stack([cols, rows], axis=1) + 0.5) * CELL_MM
        return self._material

    def beyond(self, a: np.ndarray, b: np.ndarray, toward: np.ndarray, gap: float) -> float:
        """Return how far to move the line from `a` to `b` along unit `toward` (sheet) so it lies `gap` mm
        past the work's outline in that direction, over the stretch between the two ends."""
        run = b - a
        run = run / max(float(np.linalg.norm(run)), 1e-9)
        low, high = sorted((float(a @ run), float(b @ run)))
        points = self.material()
        along = points @ run
        near = points[(along >= low - CELL_MM) & (along <= high + CELL_MM)]
        edge = max([float(a @ toward), float(b @ toward)] + ([float((near @ toward).max())] if len(near) else []))
        return max(edge + gap - float(a @ toward), edge + gap - float(b @ toward))

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


def _lane_gap(lane: int) -> float:
    """Return how far lane `lane` (from 1) sits past the work's outline, in sheet mm."""
    return BASE_MM + (lane - 1) * PITCH_MM


def _candidates(dim: Dim, view: SheetView, grid: MaterialGrid) -> List[Tuple[Optional[float], float, np.ndarray, np.ndarray]]:
    """Return the (along, offset, a, b) to try: each lane past the work's outline, on either side."""
    out = []
    ends = [(None, dim.a, dim.b)]
    if dim.slide is not None and dim.stretch is not None:
        slide_sheet = view.direction_to_sheet(dim.slide)
        facing = float(slide_sheet @ dim.away)
        for side in (1.0, -1.0):
            # The ends slid to the end of the stretch on this side.
            along = (dim.stretch[1] if facing * side > 0 else dim.stretch[0]) - dim.t0
            shift = slide_sheet * along * view.mm_per_world
            ends.append((along, dim.a + shift, dim.b + shift))
    for along, a, b in ends:
        for side in (1.0, -1.0):
            out += [(along, side * grid.beyond(a, b, side * dim.away, _lane_gap(lane)), a, b)
                    for lane in range(1, LANES + 1)]
    return out


#: Each side as a sheet direction (y down).
_SIDE_DIRECTIONS = {DimensionSide.LEFT: (-1.0, 0.0), DimensionSide.RIGHT: (1.0, 0.0),
                    DimensionSide.ABOVE: (0.0, -1.0), DimensionSide.BELOW: (0.0, 1.0)}


def _beside(dim: Dim, beside: Beside, grid: MaterialGrid) -> Optional[float]:
    """Return the offset (sheet mm, along `dim.away`) putting `dim` in `beside`'s lane, or None if its line
    can't lie on that side (the dimension runs across it)."""
    toward = np.array(_SIDE_DIRECTIONS[beside.side])
    facing = float(dim.away @ toward)
    if abs(facing) < 0.5:
        return None
    return float(np.sign(facing)) * grid.beyond(dim.a, dim.b, toward, _lane_gap(beside.lane)) / abs(facing)


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


def place(dims: Sequence[Dim], view: SheetView, meshes: Sequence[Mesh], beside: Mapping[int, Beside] = {},
          grid: Optional[MaterialGrid] = None) -> Dict[int, Offset]:
    """Return a placement for each of `dims`, by its index, with the offset as the viewer reads it
    for the ends in the order given (positive along `Dim.away`).

    A dim whose index is in `beside` goes in that lane, if it can lie on that side; the rest are placed
    clear of the work and of each other.
    """
    if not dims:
        return {}
    grid = grid or MaterialGrid(view, meshes)
    rect = view.rect_mm()
    placed: List[Placed] = []
    free = []
    for dim in dims:
        wanted = beside.get(dim.index)
        offset = _beside(dim, wanted, grid) if wanted is not None else None
        if wanted is not None and offset is None:
            warn_user(f"A dimension ({dim.text}) can't go {wanted.side.value} of the work: it runs across "
                      "that side, so it is placed automatically.")
        if offset is None:
            free.append(dim)
        else:
            placed.append(_try(dim, None, offset, dim.a, dim.b, grid, placed, rect))
    for dim in sorted(free, key=lambda d: d.span):
        placed.append(min((_try(dim, along, offset, a, b, grid, placed, rect)
                           for along, offset, a, b in _candidates(dim, view, grid)), key=lambda p: p.cost))
    return {one.dim.index: Offset(offset=one.offset / view.mm_per_world, along=one.along)
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


def _without_measurements(viewport: Viewport) -> Viewport:
    """Return `viewport` and everything inside it with no measurements of their own."""
    subdivision = viewport.subdivision
    if subdivision is not None:
        subdivision = replace(subdivision, portions=[replace(portion, viewport=_without_measurements(portion.viewport))
                                                     for portion in subdivision.portions])
    return replace(viewport, measurements=(), subdivision=subdivision)


def needs_placing(drawing: Drawing) -> bool:
    """Return whether any of `drawing`'s measurements has a placement still to be worked out."""
    return any(not isinstance(measure.placement, Offset)
               for measures in drawing.measurements_by_viewport().values() for measure in measures)


def with_placed_dimensions(drawing: Drawing, frame: 'Frame', page: Page = SHEET) -> Drawing:
    """Return `drawing` with each length's `Auto` or `Beside` placement worked out as an `Offset`, in the
    orthographic views the viewer frames on `page`. Its measurements all end up in `Drawing.measurements`.

    A placement that can't be worked out (an angle, a 3D measurement, a view with no camera) stays as it is.
    """
    by_viewport = drawing.measurements_by_viewport()
    if not needs_placing(drawing):
        return drawing
    cuts = [cut for cut in (frame.cut_timber_of(timber) for timber in drawing.timbers) if cut is not None]
    views = sheet_views(drawing, cuts, page)
    meshes = [mesh for mesh in (_world_mesh(cut) for cut in cuts) if mesh is not None]
    measurements = {}
    for viewport_id, measures in by_viewport.items():
        measures = list(measures)
        view = views.get(str(viewport_id))
        if view is None:
            measurements[ViewportId(viewport_id)] = measures
            continue
        found = {}
        for index, measure in enumerate(measures):
            one = None if isinstance(measure.placement, Offset) else _dim(index, measure, view, frame)
            if one is not None:
                found[index] = one
        beside = {index: measures[index].placement for index in found
                  if isinstance(measures[index].placement, Beside)}
        for index, placement in place([dim for dim, _ in found.values()], view, meshes, beside).items():
            if found[index][1] and placement.offset is not None:
                # The measure's own order runs the other way: wire_anchors negates it back.
                placement = replace(placement, offset=-placement.offset)
            measures[index] = replace(measures[index], placement=placement)
        measurements[ViewportId(viewport_id)] = measures
    return replace(drawing, viewports=[_without_measurements(root) for root in drawing.roots],
                   measurements=measurements)
