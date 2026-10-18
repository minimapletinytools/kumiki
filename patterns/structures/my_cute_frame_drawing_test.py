"""Experiment: generate a planning drawing for my_cute_frame with the feature solver.

The Left Side timber is fixed (its six faces are known). Everything else that a planning drawing
solves for -- each timber's perfect-timber-within faces, its centerplanes, and its joints' shoulder
planes -- is solved by auto dimensioning (kumiki.drawings.auto_dimensioning) in two world
elevations, top and front. Square and sheet-axis assumptions start known, so only positions are
left to dimension.

Each timber also gets a shop drawing of its own, solving every required feature -- joints and
peg holes too, not just its prism -- from its reference faces and its bottom end.

Run directly to print what it picked; load in Kigumi to see the drawings.
"""

import importlib.util as importlib_util
from dataclasses import replace
from pathlib import Path as FilePath
from typing import Dict, List, Sequence, Tuple

from kumiki import *
from kumiki.csg.cutcsg import MidplaneFeature, OwnedFeatureHit, measured_by_default
from kumiki.csg.carriers import Row
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.csg.assumptions import sheet_axis_assumptions, square_assumptions
from kumiki.drawings.auto_dimensioning import (DEFAULT_POLICY, Policy, auto_dimension, is_reference,
                                              sheet_candidates)
from kumiki.drawings.drawing import (ELEVATION_IDS, SHOP_DRAWING_IDS, Drawing, ViewAxes, elevation_viewports,
                                    shop_drawing_viewports)
from kumiki.geometry import Plane
from kumiki.csg.feature_solving import carrier_map_of, feature_handle_dof_rows
from kumiki.drawings.visibility import visible_by_view
from kumiki.csg.required_features import planning_features, required_features


ROUGH_ALLOWANCE = inches(1)


def _rough(timber: Timber) -> Timber:
    """*timber*, its rough stock ROUGH_ALLOWANCE larger on each long face that is not a reference face."""
    referenced = {face for feature in timber.ticket.reference_features for face in feature.long_faces_it_rests_on()}
    (right, left), (front, back) = ((half[0], half[1]) for half in timber.get_rough_half_sizes())
    grow = lambda face, half: half if face in referenced else half + ROUGH_ALLOWANCE
    return Timber.from_perfect_timber_within(timber, rough_half_sizes=(
        create_v2(grow(TimberLongFace.RIGHT, right), grow(TimberLongFace.LEFT, left)),
        create_v2(grow(TimberLongFace.FRONT, front), grow(TimberLongFace.BACK, back))))


def _load_cute_frame():
    """my_cute_frame's build_frame, every timber of it rough on its two non-reference faces.

    my_cute_frame.py is the starter project's frame and stays as it is, so the rough stock goes in
    here, where its timbers are made.
    """
    path = FilePath(__file__).resolve().parent / "my_cute_frame.py"
    spec = importlib_util.spec_from_file_location("my_cute_frame_for_drawing_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.create_axis_aligned_timber = lambda *args, **kwargs: _rough(create_axis_aligned_timber(*args, **kwargs))
    return module.build_frame


FIXED_TIMBER = "Left Side"

# The viewer's world elevations (kigumi/runner.py, _DEBUG_DRAWING_VIEWS): (right, up, look).
VIEWS = {
    "top": ((1, 0, 0), (0, 1, 0), (0, 0, -1)),
    "front": ((1, 0, 0), (0, 0, 1), (0, 1, 0)),
}

def _name(handle: FeatureHandle) -> str:
    return f"{handle.timber.ticket.path}:{handle.feature.name}"


def _sheet(view: str) -> Tuple[ViewAxes, Transform]:
    right, up, look = (create_v3(*axis) for axis in VIEWS[view])
    return (ViewAxes(look=look, right=right, up=up),
            Transform(position=create_v3(0, 0, 0), orientation=Orientation.from_x_and_y(right, up)))


def _rows(handles: Sequence[FeatureHandle], carriers) -> List[Row]:
    return [row for handle in handles for row in feature_handle_dof_rows(handle, carriers)]


def solve_cute_frame(policy: Policy = DEFAULT_POLICY):
    """Pick dimensions until every planning feature is solved. Returns (frame, AutoDimensioning, report lines)."""
    frame = _load_cute_frame()()
    cut_timbers = list(frame.cut_timbers)
    carriers = carrier_map_of(*cut_timbers)

    fixed = next(cut for cut in cut_timbers if cut.timber.ticket.path == FIXED_TIMBER)
    body = fixed.get_extended_rough_csg_with_perfect_features_local()
    known = [FeatureHandle(timber=fixed.timber, hit=OwnedFeatureHit(feature=feature, owner=body))
             for feature in body.get_declared_features()
             if feature.feature_type().name == "FACE" and not isinstance(feature, MidplaneFeature)
             and measured_by_default(feature.properties.purpose)]

    targets = [required.handle for cut in cut_timbers for required in planning_features(cut)]
    # The fixed timber's faces are targets too; each feature once.
    directed = list({(id(handle.owner), handle.feature.name): handle for handle in targets + known}.values())
    assumptions = square_assumptions(directed, carriers)
    for view in VIEWS:
        assumptions += sheet_axis_assumptions(directed, carriers, _sheet(view)[1])
    known_rows = _rows(known, carriers) + [row for assumption in assumptions for row in assumption.rows]

    # Centerplanes can't be referenced by a drawing yet, so they're solved for but never dimensioned to.
    anchors = [handle for handle in directed if not isinstance(handle.feature, MidplaneFeature)]
    views = {view: _sheet(view)[0] for view in VIEWS}
    candidates = sheet_candidates(visible_by_view(anchors, views, cut_timbers), carriers, views, cut_timbers)
    result = auto_dimension(candidates, targets, known_rows, carriers, policy)

    report = [f"fixed: {FIXED_TIMBER} ({len(known)} faces known), {len(assumptions)} assumptions",
              f"targets: {len(targets)} features, {len(candidates)} candidate dimensions",
              f"left before dimensioning: {result.left_before}"]
    for count, pick in enumerate(result.picks, start=1):
        measure = pick.candidate.measure
        marks = "".join("*" if is_reference(end) else " " for end in (measure.anchor_a, measure.anchor_b))
        report.append(f"[{pick.candidate.view:5}] {marks} {_name(measure.anchor_a)} -> {_name(measure.anchor_b)}"
                      f"  {pick.candidate.length * 1000:.0f}mm  ({result.left_before - count} left)")
    report.append(f"unsolved: {[_name(h) for h in result.unsolved] or 'none'} "
                  f"(rank test: {result.left_after} left)  * = a reference face")
    return frame, result, report


# A shop drawing's four long-face views (kigumi/runner.py, _LONG_FACE_VIEWS): face axis and sign.
SHOP_VIEWS = {"front": ("height", 1), "right": ("width", 1), "back": ("height", -1), "left": ("width", -1)}


def _shop_sheets(timber) -> Dict[str, Tuple[ViewAxes, Transform]]:
    """Each long face square on, the length across the sheet -- the cameras the viewer builds."""
    along = timber.get_length_direction_global()
    axes = {"width": timber.get_width_direction_global(), "height": timber.get_height_direction_global()}
    sheets = {}
    for view, (axis, sign) in SHOP_VIEWS.items():
        normal = axes[axis] * sign
        up = normal.cross(along)
        sheets[view] = (ViewAxes(look=-normal, right=along, up=up),
                        Transform(position=create_v3(0, 0, 0), orientation=Orientation.from_x_and_y(along, up)))
    return sheets


def _end_datum(targets: Sequence[FeatureHandle], timber) -> FeatureHandle:
    """The face nearest the bottom end square to the length: where a piece's length is measured from."""
    along = [float(v) for v in timber.get_length_direction_global()]
    ends = []
    for handle in targets:
        plane = handle.feature.locate_simple_unbounded(handle.owner)
        if not isinstance(plane, Plane):
            continue
        normal = [float(v) for v in timber.transform.local_to_global_direction(plane.normal)]
        if abs(abs(sum(a * b for a, b in zip(normal, along))) - 1) > 1e-9:
            continue
        point = [float(v) for v in timber.transform.local_to_global(plane.point)]
        ends.append((sum(a * b for a, b in zip(point, along)), handle))
    return min(ends, key=lambda end: end[0])[1]


def solve_timber(cut: CutTimber, policy: Policy = DEFAULT_POLICY):
    """Every required feature of one timber, dimensioned from its reference faces and its bottom end."""
    carriers = carrier_map_of(cut)
    targets = list({(id(r.handle.owner), r.handle.feature.name): r.handle for r in required_features(cut)}.values())
    known = [handle for handle in targets if is_reference(handle)] + [_end_datum(targets, cut.timber)]
    sheets = _shop_sheets(cut.timber)
    assumptions = square_assumptions(targets, carriers)
    for _, sheet in sheets.values():
        assumptions += sheet_axis_assumptions(targets, carriers, sheet)
    known_rows = _rows(known, carriers) + [row for assumption in assumptions for row in assumption.rows]

    anchors = [handle for handle in targets if not isinstance(handle.feature, MidplaneFeature)]
    views = {view: axes for view, (axes, _) in sheets.items()}
    candidates = sheet_candidates(visible_by_view(anchors, views, [cut]), carriers, views, [cut])
    result = auto_dimension(candidates, targets, known_rows, carriers, policy)

    report = [f"{cut.timber.ticket.path}: {len(targets)} features, from {[_name(h) for h in known]}, "
              f"{len(candidates)} candidates, {result.left_before} left before"]
    for pick in result.picks:
        measure = pick.candidate.measure
        report.append(f"  [{pick.candidate.view:5}] {_name(measure.anchor_a)} -> {_name(measure.anchor_b)}"
                      f"  {pick.candidate.length * 1000:.0f}mm")
    report.append(f"  unsolved: {[_name(h) for h in result.unsolved] or 'none'} (rank test: {result.left_after} left)")
    return result, report


def build_frame_with_drawing() -> Frame:
    frame, result, _ = solve_cute_frame()
    measurements: Dict = {ELEVATION_IDS["top"]: [], ELEVATION_IDS["front"]: []}
    for pick in result.picks:
        candidate = pick.candidate
        measurements[ELEVATION_IDS[candidate.view]].append(candidate.measure)
    drawing = Drawing(name="Cute frame plan (generated)", timbers=[cut.timber for cut in frame.cut_timbers],
                      viewports=elevation_viewports(), measurements=measurements)
    return replace(frame, drawings=[*frame.drawings, drawing, *(_timber_drawing(cut, frame) for cut in frame.cut_timbers)])


def _timber_drawing(cut: CutTimber, frame: Frame) -> Drawing:
    """One timber's shop drawing, dimensioned by solve_timber."""
    result, _ = solve_timber(cut)
    measurements: Dict = {SHOP_DRAWING_IDS[view]: [] for view in SHOP_VIEWS}
    for pick in result.picks:
        candidate = pick.candidate
        measurements[SHOP_DRAWING_IDS[candidate.view]].append(candidate.measure)
    return Drawing(name=f"{cut.timber.ticket.path} (generated)", timbers=[cut.timber],
                   viewports=shop_drawing_viewports(), measurements=measurements)


example = build_frame_with_drawing


if __name__ == "__main__":
    import time
    started = time.time()
    frame, _, lines = solve_cute_frame()
    print("\n".join(lines))
    for cut in frame.cut_timbers:
        print("\n".join(solve_timber(cut)[1]))
    print(f"took {time.time() - started:.1f}s")
