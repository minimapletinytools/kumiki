"""Experiment: generate a planning drawing for my_cute_frame with the feature solver.

The Left Side timber is fixed (its six faces are known). Everything else that a planning drawing
solves for -- each timber's perfect-timber-within faces, its centerplanes, and its joints' shoulder
planes -- is solved by picking dimensions one at a time in two world elevations, top and front,
always taking the one that leaves the fewest unknowns. Square and sheet-axis assumptions start
known, so only positions are left to dimension.

Run directly to print what it picked; load in Kigumi to see the drawing.
"""

import importlib.util as importlib_util
from dataclasses import dataclass, replace
from pathlib import Path as FilePath
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from kumiki import *
from kumiki.csg.cutcsg import OwnedFeatureHit, PrismCenterplaneFeature
from kumiki.csg.carriers import Row
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.drawings.assumptions import sheet_axis_assumptions, square_assumptions
from kumiki.drawings.dof_solver import remaining
from kumiki.drawings.drawing import ELEVATION_IDS, Drawing, Measure, MeasurementKind, ViewAxes, elevation_viewports
from kumiki.drawings.feature_solving import carrier_map_of, feature_handle_dof_rows, measure_row
from kumiki.drawings.required_features import planning_features
from kumiki.geometry import Plane


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

PERPENDICULAR = MeasurementKind.parse("projected_perpendicular_distance")


@dataclass(frozen=True)
class Candidate:
    view: str
    measure: Measure
    row: Row
    length: float


def _np(vector) -> np.ndarray:
    return np.array([float(vector[i, 0]) for i in range(3)])


def _name(handle: FeatureHandle) -> str:
    return f"{handle.timber.ticket.path}:{handle.feature.name}"


def _plane_in_world(handle: FeatureHandle) -> Optional[Tuple[np.ndarray, float]]:
    """(unit normal, offset along it) of a planar feature, in world space."""
    plane = handle.feature.locate_simple_unbounded(handle.owner)
    if not isinstance(plane, Plane):
        return None
    transform = handle.timber.transform
    normal = _np(transform.local_to_global_direction(plane.normal))
    normal /= np.linalg.norm(normal)
    return normal, float(normal @ _np(transform.local_to_global(plane.point)))


def _sheet(view: str) -> Tuple[ViewAxes, Transform]:
    right, up, look = (create_v3(*axis) for axis in VIEWS[view])
    return (ViewAxes(look=look, right=right, up=up),
            Transform(position=create_v3(0, 0, 0), orientation=Orientation.from_x_and_y(right, up)))


def _candidates(anchors: Sequence[FeatureHandle], carriers) -> List[Candidate]:
    """Every perpendicular dimension between two parallel planes seen edge-on, in each view."""
    candidates = []
    planes = [(handle, _plane_in_world(handle)) for handle in anchors]
    planes = [(handle, plane) for handle, plane in planes if plane is not None]
    for view, (_, _, look) in VIEWS.items():
        axes, _ = _sheet(view)
        look_np = np.array(look, dtype=float)
        edge_on = [(handle, plane) for handle, plane in planes if abs(float(plane[0] @ look_np)) < 1e-9]
        for i, (a, (normal_a, offset_a)) in enumerate(edge_on):
            for b, (normal_b, offset_b) in edge_on[i + 1:]:
                if abs(abs(float(normal_a @ normal_b)) - 1) > 1e-9:
                    continue
                length = abs(offset_a - float(normal_a @ normal_b) * offset_b)
                if length < 1e-9:
                    continue
                measure = Measure(a, b, kind=PERPENDICULAR)
                try:
                    row = measure_row(measure, carriers, axes)
                except ValueError:
                    continue
                candidates.append(Candidate(view, measure, row, length))
    return candidates


def _matrix(rows: Sequence[Row], columns: list) -> np.ndarray:
    index = {column: i for i, column in enumerate(columns)}
    out = np.zeros((len(rows), len(columns)))
    for r, row in enumerate(rows):
        for column, value in row.items():
            out[r, index[column]] = value
    return out


def _rows(handles: Sequence[FeatureHandle], carriers) -> List[Row]:
    return [row for handle in handles for row in feature_handle_dof_rows(handle, carriers)]


def solve_cute_frame():
    """Pick dimensions until every planning feature is solved. Returns (frame, picks, report lines)."""
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
    target_rows = _rows(targets, carriers)

    # Centerplanes can't be referenced by a drawing yet, so they're solved for but never dimensioned to.
    anchors = [handle for handle in directed if not isinstance(handle.feature, PrismCenterplaneFeature)]
    candidates = _candidates(anchors, carriers)

    # Everything below works on rows with the known rows' span projected out, carried from pick to
    # pick: picking a row just removes its direction from every matrix (incremental Gram-Schmidt).
    columns = list(dict.fromkeys(column for row in (*known_rows, *target_rows, *(c.row for c in candidates))
                                 for column in row))
    known_matrix, target_matrix = _matrix(known_rows, columns), _matrix(target_rows, columns)
    candidate_matrix = _matrix([candidate.row for candidate in candidates], columns)
    tolerance = 1e-9 * max(float(np.linalg.norm(np.vstack([known_matrix, target_matrix]), 2)), 1.0)

    _, values, basis = np.linalg.svd(known_matrix, full_matrices=False)
    basis = basis[values > tolerance]
    target_left = target_matrix - target_matrix @ basis.T @ basis
    candidate_left = candidate_matrix - candidate_matrix @ basis.T @ basis

    # Which rows of the target matrix are each feature's.
    spans: Dict[Tuple[int, str], slice] = {}
    start = 0
    for handle in targets:
        count = len(feature_handle_dof_rows(handle, carriers))
        spans[(id(handle.owner), handle.feature.name)] = slice(start, start + count)
        start += count

    def solved(handle: FeatureHandle) -> bool:
        span = spans.get((id(handle.owner), handle.feature.name))
        return span is None or float(np.linalg.norm(target_left[span])) < tolerance

    def unsolved_basis() -> np.ndarray:
        _, values, directions = np.linalg.svd(target_left, full_matrices=False)
        return directions[values > tolerance]

    report = [f"fixed: {FIXED_TIMBER} ({len(known)} faces known), {len(assumptions)} assumptions",
              f"targets: {len(targets)} features, {len(candidates)} candidate dimensions",
              f"left before dimensioning: {len(unsolved_basis())}"]

    picks: List[Candidate] = []
    available = list(range(len(candidates)))
    while True:
        unsolved = unsolved_basis()
        if not len(unsolved):
            break
        best: Optional[Tuple[Tuple, int, np.ndarray]] = None
        for index in available:
            residual = candidate_left[index]
            size = float(np.linalg.norm(residual))
            if size < tolerance:
                continue
            direction = residual / size
            # It helps exactly when what it adds to the known rows lies in what is still unsolved.
            if float(np.linalg.norm(direction - unsolved.T @ (unsolved @ direction))) > 1e-6:
                continue
            candidate = candidates[index]
            # Measured from something already solved, then shortest.
            score = (not (solved(candidate.measure.anchor_a) or solved(candidate.measure.anchor_b)), candidate.length)
            if best is None or score < best[0]:
                best = (score, index, direction)
        if best is None:
            report.append(f"stuck with {len(unsolved)} left: no candidate dimension helps")
            break
        _, index, direction = best
        target_left = target_left - np.outer(target_left @ direction, direction)
        candidate_left = candidate_left - np.outer(candidate_left @ direction, direction)
        available.remove(index)
        pick = candidates[index]
        picks.append(pick)
        known_rows.append(pick.row)
        report.append(f"[{pick.view:5}] {_name(pick.measure.anchor_a)} -> {_name(pick.measure.anchor_b)}"
                      f"  {pick.length * 1000:.0f}mm  ({len(unsolved) - 1} left)")

    # Checked once more with the library's own rank test.
    left = remaining(known_rows, target_rows).count
    unsolved_names = [_name(handle) for handle in targets if not solved(handle)]
    report.append(f"unsolved: {unsolved_names or 'none'} (rank test: {left} left)")
    return frame, picks, report


def _drawable(handle: FeatureHandle, frame: Frame) -> FeatureHandle:
    """The same face on the rough body, which is what a drawing can reference today.

    The cute frame's timbers have no rough allowance, so ptw.X and rough.X are the same plane.
    """
    if not handle.feature.name.startswith("ptw."):
        return handle
    cut = frame.cut_timber_of(handle.timber)
    assert cut is not None
    rendered = cut.render_timber_with_cuts_csg_local()
    rough_body = rendered.base if isinstance(rendered, Difference) else rendered
    wanted = "rough." + handle.feature.name.removeprefix("ptw.")
    feature = next(f for f in rough_body.get_declared_features() if f.name == wanted)
    return FeatureHandle(timber=handle.timber, hit=OwnedFeatureHit(feature=feature, owner=rough_body))


def build_frame_with_drawing() -> Frame:
    frame, picks, _ = solve_cute_frame()
    measurements: Dict = {ELEVATION_IDS["top"]: [], ELEVATION_IDS["front"]: []}
    for pick in picks:
        measure = replace(pick.measure, anchor_a=_drawable(pick.measure.anchor_a, frame),
                          anchor_b=_drawable(pick.measure.anchor_b, frame))
        measurements[ELEVATION_IDS[pick.view]].append(measure)
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
