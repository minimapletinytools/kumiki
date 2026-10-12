"""Experiment: generate a planning drawing for my_cute_frame with the feature solver.

The Left Side timber is fixed (its six faces are known). Everything else that a planning drawing
solves for -- each timber's perfect-timber-within faces, its centerplanes, and its joints' shoulder
planes -- is solved by auto dimensioning (kumiki.drawings.auto_dimensioning) in two world
elevations, top and front. Square and sheet-axis assumptions start known, so only positions are
left to dimension.

Run directly to print what it picked; load in Kigumi to see the drawing.
"""

import importlib.util as importlib_util
from dataclasses import replace
from pathlib import Path as FilePath
from typing import Dict, List, Sequence, Tuple

from kumiki import *
from kumiki.csg.cutcsg import OwnedFeatureHit, PrismCenterplaneFeature
from kumiki.csg.carriers import Row
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.drawings.assumptions import sheet_axis_assumptions, square_assumptions
from kumiki.drawings.auto_dimensioning import (DEFAULT_POLICY, Policy, auto_dimension, is_reference,
                                              plane_pair_candidates)
from kumiki.drawings.drawing import ELEVATION_IDS, Drawing, ViewAxes, elevation_viewports
from kumiki.drawings.feature_solving import carrier_map_of, feature_handle_dof_rows
from kumiki.drawings.required_features import planning_features


def _load_cute_frame():
    path = FilePath(__file__).resolve().parent / "my_cute_frame.py"
    spec = importlib_util.spec_from_file_location("my_cute_frame_for_drawing_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
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
    body = fixed.get_extended_perfect_csg_local()
    known = [FeatureHandle(timber=fixed.timber, hit=OwnedFeatureHit(feature=feature, owner=body))
             for feature in body.get_declared_features()
             if feature.feature_type().name == "FACE" and not isinstance(feature, PrismCenterplaneFeature)]

    targets = [required.handle for cut in cut_timbers for required in planning_features(cut)]
    # The fixed timber's faces are targets too; each feature once.
    directed = list({(id(handle.owner), handle.feature.name): handle for handle in targets + known}.values())
    assumptions = square_assumptions(directed, carriers)
    for view in VIEWS:
        assumptions += sheet_axis_assumptions(directed, carriers, _sheet(view)[1])
    known_rows = _rows(known, carriers) + [row for assumption in assumptions for row in assumption.rows]

    # Centerplanes can't be referenced by a drawing yet, so they're solved for but never dimensioned to.
    anchors = [handle for handle in directed if not isinstance(handle.feature, PrismCenterplaneFeature)]
    candidates = plane_pair_candidates(anchors, carriers, {view: _sheet(view)[0] for view in VIEWS})
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


def _drawable(handle: FeatureHandle, frame: Frame) -> FeatureHandle:
    """The same face on the rough body, which is what a drawing can reference today.

    The cute frame's timbers have no rough allowance, so the rough body's face is rptw.X, on ptw.X's plane.
    """
    if not handle.feature.name.startswith("ptw."):
        return handle
    cut = frame.cut_timber_of(handle.timber)
    assert cut is not None
    rendered = cut.render_timber_with_cuts_csg_local()
    rough_body = rendered.base if isinstance(rendered, Difference) else rendered
    wanted = "rptw." + handle.feature.name.removeprefix("ptw.")
    feature = next(f for f in rough_body.get_declared_features() if f.name == wanted)
    return FeatureHandle(timber=handle.timber, hit=OwnedFeatureHit(feature=feature, owner=rough_body))


def build_frame_with_drawing() -> Frame:
    frame, result, _ = solve_cute_frame()
    measurements: Dict = {ELEVATION_IDS["top"]: [], ELEVATION_IDS["front"]: []}
    for pick in result.picks:
        candidate = pick.candidate
        measure = replace(candidate.measure, anchor_a=_drawable(candidate.measure.anchor_a, frame),
                          anchor_b=_drawable(candidate.measure.anchor_b, frame))
        measurements[ELEVATION_IDS[candidate.view]].append(measure)
    drawing = Drawing(name="Cute frame plan (generated)", timbers=[cut.timber for cut in frame.cut_timbers],
                      viewports=elevation_viewports(), measurements=measurements)
    return replace(frame, drawings=[*frame.drawings, drawing])


example = build_frame_with_drawing


if __name__ == "__main__":
    import time
    started = time.time()
    _, _, lines = solve_cute_frame()
    print("\n".join(lines))
    print(f"took {time.time() - started:.1f}s")
