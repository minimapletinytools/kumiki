"""Generated drawings: a frame's plan and a shop drawing per distinct piece, dimensioned by auto_dimensioning.

The plan is solved in the world's front and top elevations from a fixed timber's reference features
and bottom end; each piece on its own four long faces, plus any extra views asked for, from its
reference features and bottom end. Matching pieces (match_timbers) share one shop drawing.
"""

from dataclasses import replace
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..csg.assumptions import sheet_axis_assumptions, square_assumptions
from ..csg.carriers import Row
from ..csg.cutcsg import Datum, MidplaneFeature, OwnedFeatureHit, measured_by_default
from ..csg.feature_paths import FeatureHandle, hit_identity
from ..csg.required_features import planning_features, required_features
from ..csg.symmetry import SymmetricTimberGroup, SymmetryKind, match_timbers
from ..geometry import Plane
from ..identity import DrawingId, ViewportId
from ..rule import Orientation, Transform, create_v3
from ..timber import CutTimber, Frame, PerfectTimberWithin
from .auto_dimensioning import (DEFAULT_POLICY, AutoDimensioning, Criterion, DimensionCandidate, PickContext, Policy,
                                auto_dimension, coincidence_assumptions, derived_edge_anchors, faces_to_edges, fixed,
                                is_reference, measurable_targets, sheet_candidates, without_edges_on_faces)
from .drawing import ELEVATION_IDS, Drawing, Viewport, columns, covering_page, elevation_viewports, rows
from .measure import ViewAxes
from .measure_solving import DrawingSolve
from .visibility import visible_by_view

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


def _shop_sheets(timber: PerfectTimberWithin) -> Dict[str, Sheet]:
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
               sheets: Mapping[str, Sheet], solve: DrawingSolve, policy: Policy) -> AutoDimensioning:
    """Return dimensions in `sheets` solving `targets`, starting from `known`."""
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
    result = auto_dimension(sheet_candidates(visible, views, solve), measurable, known_rows, solve, policy)
    return faces_to_edges(result, cut_timbers, directed, views, carriers)


def plan_drawing(cut_timbers: Sequence[CutTimber], fixed_path: str, name: str,
                 dimensioned: Optional[Sequence[CutTimber]] = None, policy: Policy = DEFAULT_POLICY) -> Drawing:
    """Return the whole frame in world elevations, dimensioned from the timber at `fixed_path`.

    `dimensioned` is which members the plan dimensions (all of them by default); every timber is drawn.
    """
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

    result = _dimension(cut_timbers, targets, known, _plan_sheets(), solve, policy)
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


def piece_drawing(group: SymmetricTimberGroup, extra_views: Mapping[str, ViewAxes] = {},
                  policy: Policy = DEFAULT_POLICY) -> Drawing:
    """Return one shop drawing for a group of matching pieces, dimensioned on its representative.

    `extra_views` are more views, by label, in world space; they sit under the preview, and what can
    be dimensioned in them is. The drawing is named with how many to make; its id stays the
    representative's path.
    """
    cut = group.representative
    solve = DrawingSolve([cut])
    targets = list({_feature_key(required.handle): required.handle for required in required_features(cut)}.values())
    known = [handle for handle in targets if is_reference(handle)] + [_end_datum(targets, cut.timber)]
    labels = {view: view.capitalize() for view in SHOP_VIEWS}
    labels.update({label: label for label in extra_views})
    sheets = {**_shop_sheets(cut.timber), **{label: _sheet(axes) for label, axes in extra_views.items()}}
    if extra_views:
        policy = replace(policy, prefer=(in_views(list(extra_views)), *policy.prefer))
    result = _dimension([cut], targets, known, sheets, solve, policy)

    viewports = (covering_page(columns(
        rows(*(Viewport(label=labels[view]) for view in SHOP_VIEWS)),
        rows(Viewport(label="Preview"), *(Viewport(label=label, camera=axes) for label, axes in extra_views.items())),
    )),)
    ids = _ids_by_label(viewports)
    measurements: Dict[ViewportId, List] = {ids[labels[view]]: [] for view in sheets}
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
    """Return `frame` plus a generated plan and a shop drawing per distinct piece.

    `fixed_path` names the timber the plan is measured from. `extra_views` adds views to a piece's
    shop drawing; `dimensioned` picks which members the plan dimensions (all by default).
    """
    cut_timbers = list(frame.cut_timbers)
    members = [cut for cut in cut_timbers if dimensioned(cut)] if dimensioned else None
    return replace(frame, drawings=[
        *frame.drawings,
        plan_drawing(cut_timbers, fixed_path, f"{frame.name} plan (generated)", members),
        *(piece_drawing(group, extra_views(group.representative) if extra_views else {})
          for group in match_timbers(cut_timbers)),
    ])
