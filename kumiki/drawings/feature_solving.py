"""Measurements on cut timbers, as rows over their solving carriers, and what they leave unsolved.

The interface layer of docs/internal/featuresolving-plan.md, Part 2 D: FeatureHandles and
Measures in, rows and remaining DOFs out. Measurements are placed in world space; each anchor's
row is taken in its own timber's local space, where its carriers are.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ..csg.cutcsg import carrier_map
from .dof_solver import Remaining, remaining
from .drawing import (LineSpan, Measure, MeasureSpan, MeasurementDirection, MeasurementKind, MeasurementOperation,
                      MeasurementSpace, PlaneSpan, PointSpan, ViewAxes, distance_anchors)
from ..csg.feature_paths import FeatureHandle
from ..geometry import Line, Plane, Point
from ..csg.planar_region import face_reaches_surface
from .required_features import FaceTest, required_features
from ..rule import Matrix, V3
from ..csg.carriers import CarrierMap, Recipe, Row
from .solve_recipe import (combine, direction_motion, dot_vector_row, feature_dof_rows, motion_along,
                           transform_vector_row)
from ..timber import CutTimber

THREE_D_DISTANCE = MeasurementKind(MeasurementOperation.DISTANCE, MeasurementSpace.THREE_D)


def carrier_map_of(cut_timber: CutTimber, *more: CutTimber) -> CarrierMap:
    """The solving carriers of cut timbers' perfect-timber-within trees, the trees their handles point into.

    Coincident planes are merged within a timber, never across timbers.
    """
    return CarrierMap.union([carrier_map(timber.render_perfect_timber_within_with_cuts_csg_local())
                             for timber in (cut_timber, *more)])


def _np(vector: V3) -> np.ndarray:
    return np.array([float(vector[i, 0]) for i in range(3)])


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _recipe(handle: FeatureHandle) -> Recipe:
    recipe = handle.feature.solve_recipe(handle.owner)
    if recipe is None:
        raise ValueError(f"{handle.feature.name!r} has no solve recipe yet")
    return recipe


def _span(handle: FeatureHandle) -> MeasureSpan:
    """The feature as drawing's measuring rules see it, in world space."""
    transform = handle.timber.transform
    located = handle.feature.locate_simple_unbounded(handle.owner)
    extent = handle.feature.get_extent(handle.owner)
    if isinstance(located, Point):
        return PointSpan(at=transform.local_to_global(located.position))
    if isinstance(located, Line):
        direction = _unit(_np(located.direction))
        ends = extent.ends if extent is not None else None
        interval = None
        if ends:
            stations = sorted(float((_np(end) - _np(located.point)) @ direction) for end in ends)
            interval = (stations[0], stations[-1])
        return LineSpan(at=transform.local_to_global(located.point),
                        direction=transform.local_to_global_direction(located.direction), interval=interval)
    if isinstance(located, Plane):
        at = extent.anchor if extent is not None else located.point
        return PlaneSpan(at=transform.local_to_global(at), normal=transform.local_to_global_direction(located.normal))
    raise ValueError(f"{handle.feature.name!r} has no plane, line or point to measure to")


def _projected(span: MeasureSpan, look: np.ndarray) -> MeasureSpan:
    """A span as it is seen on a sheet looking along `look`: a point stays a point, an edge-on face is a line."""
    if isinstance(span, PointSpan):
        return span
    if isinstance(span, LineSpan):
        flat = _np(span.along) - look * float(_np(span.along) @ look)
        if np.linalg.norm(flat) < 1e-9:
            return PointSpan(at=span.at)
        scale = float(np.linalg.norm(flat))
        interval = None if span.interval is None else (span.interval[0] * scale, span.interval[1] * scale)
        return LineSpan(at=span.at, direction=Matrix(flat / scale), interval=interval)
    edge = np.cross(_np(span.facing), look)
    if np.linalg.norm(edge) < 1e-9 or abs(float(_np(span.facing) @ look)) > 1e-6:
        raise ValueError("a face seen at an angle covers the sheet, so nothing is measured to it")
    return LineSpan(at=span.at, direction=Matrix(_unit(edge)))


def _on_feature(span: MeasureSpan, anchor: np.ndarray, look: np.ndarray) -> np.ndarray:
    """The point of the 3D feature that a sheet anchor stands for."""
    if isinstance(span, LineSpan):
        direction = _np(span.along)
        flat = direction - look * float(direction @ look)
        if float(flat @ flat) > 1e-18:
            return _np(span.at) + direction * float((anchor - _np(span.at)) @ flat) / float(flat @ flat)
    return anchor


def _distance_row(measure: Measure, at_a: np.ndarray, at_b: np.ndarray, along: np.ndarray,
                  carriers: CarrierMap) -> Row:
    """How the distance from `at_a` to `at_b`, read along `along`, changes. Points and direction in world space."""
    rows = []
    for handle, at in ((measure.anchor_a, at_a), (measure.anchor_b, at_b)):
        transform = handle.timber.transform
        rows.append(motion_along(_recipe(handle), carriers, transform.global_to_local(Matrix(at)),
                                 transform.global_to_local_direction(Matrix(along))))
    return combine(rows[1], rows[0], -1.0)


def _gap_direction(at_a: np.ndarray, at_b: np.ndarray, look: Optional[np.ndarray] = None) -> np.ndarray:
    gap = at_b - at_a
    if look is not None:
        gap = gap - look * float(gap @ look)
    length = float(np.linalg.norm(gap))
    if length < 1e-12:
        raise ValueError("the two features are in the same place, so there is no direction to measure along")
    return gap / length


def _direction_in_world(handle: FeatureHandle, carriers: CarrierMap) -> Tuple[np.ndarray, Tuple[Row, Row, Row]]:
    direction, change = direction_motion(_recipe(handle), carriers)
    rotation = np.array(handle.timber.transform.orientation.matrix.tolist(), dtype=float)
    return rotation @ direction, transform_vector_row(change, rotation)


def _angle_row(measure: Measure, carriers: CarrierMap, look: Optional[np.ndarray]) -> Row:
    """How the cosine of the angle between the two features changes.

    In 3D, between their normals or directions. On a sheet, between the lines they draw as.
    """
    sides = []
    for handle in (measure.anchor_a, measure.anchor_b):
        direction, change = _direction_in_world(handle, carriers)
        if look is not None:
            if isinstance(handle.feature.locate_simple_unbounded(handle.owner), Plane):
                # A face draws as the line its plane meets the sheet in: normal × look.
                drawn = np.cross(direction, look)
                drawn_change = tuple(dot_vector_row(change, np.cross(look, axis)) for axis in np.eye(3))
            else:
                across = np.eye(3) - np.outer(look, look)
                drawn = across @ direction
                drawn_change = transform_vector_row(change, across)
            direction, change = drawn, drawn_change
        length = float(np.linalg.norm(direction))
        if length < 1e-9:
            raise ValueError("a feature seen end-on, or a face seen square on, has no direction on the sheet")
        sides.append((direction, change, length))

    (a, change_a, length_a), (b, change_b, length_b) = sides
    cosine = float(a @ b) / (length_a * length_b)
    row = combine(dot_vector_row(change_a, b), dot_vector_row(change_b, a))
    row = {key: value / (length_a * length_b) for key, value in row.items()}
    row = combine(row, dot_vector_row(change_a, a * cosine / (length_a * length_a)), -1.0)
    return combine(row, dot_vector_row(change_b, b * cosine / (length_b * length_b)), -1.0)


def feature_handle_dof_rows(handle: FeatureHandle, carriers: CarrierMap) -> List[Row]:
    """The feature's own DOFs as rows. See solve_recipe.feature_dof_rows."""
    return feature_dof_rows(_recipe(handle), carriers)


def measure_row(measure: Measure, carriers: CarrierMap, view: Optional[ViewAxes] = None) -> Row:
    """How a measurement's value changes with the solving carriers' unknowns.

    Distances and angles, in 3D or on a sheet seen through `view` (world space), between features
    on one timber or two. `carriers` must cover every timber the measurement touches.
    """
    kind = measure.kind or THREE_D_DISTANCE
    view = view or ViewAxes()
    look = _unit(_np(view.look)) if kind.space is MeasurementSpace.PROJECTED else None

    if kind.operation is MeasurementOperation.ANGLE:
        return _angle_row(measure, carriers, look)

    first, second = _span(measure.anchor_a), _span(measure.anchor_b)
    if look is None:
        at_a, at_b = (_np(point) for point in distance_anchors(first, second, kind, view))
        return _distance_row(measure, at_a, at_b, _gap_direction(at_a, at_b), carriers)

    if kind.direction is not MeasurementDirection.PERPENDICULAR:
        if not (isinstance(first, PointSpan) and isinstance(second, PointSpan)):
            raise ValueError(f"a {kind.name} is only taken between two points")
        along = _unit(_np(view.right if kind.direction is MeasurementDirection.HORIZONTAL else view.up))
        return _distance_row(measure, _np(first.at), _np(second.at), along, carriers)

    flat_first, flat_second = _projected(first, look), _projected(second, look)
    anchor_a, anchor_b = (_np(point) for point in distance_anchors(flat_first, flat_second, kind, view))
    along = _gap_direction(anchor_a, anchor_b, look)
    return _distance_row(measure, _on_feature(first, anchor_a, look), _on_feature(second, anchor_b, look),
                         along, carriers)


def _carriers_for(handles: Sequence[FeatureHandle], cut_timbers: Sequence[CutTimber]) -> CarrierMap:
    """Carriers of every timber the handles are on, each found among `cut_timbers`."""
    touched: List[CutTimber] = []
    for handle in handles:
        if any(cut.timber is handle.timber for cut in touched):
            continue
        found = next((cut for cut in cut_timbers if cut.timber is handle.timber), None)
        if found is None:
            raise ValueError(f"{handle.feature.name!r} is on a timber not in cut_timbers")
        touched.append(found)
    return CarrierMap.union([carrier_map(cut.render_timber_with_cuts_csg_local()) for cut in touched])


def _known_rows(
    measures: Sequence[Measure], known: Sequence[FeatureHandle], carriers: CarrierMap, view: Optional[ViewAxes],
) -> List[Row]:
    rows: List[Row] = [row for handle in known for row in feature_handle_dof_rows(handle, carriers)]
    return rows + [measure_row(measure, carriers, view) for measure in measures]


def _handles(measures: Sequence[Measure], known: Sequence[FeatureHandle]) -> List[FeatureHandle]:
    return [*known, *(handle for measure in measures for handle in (measure.anchor_a, measure.anchor_b))]


def remaining_dofs(
    target: FeatureHandle,
    measures: Sequence[Measure],
    known: Sequence[FeatureHandle],
    cut_timbers: Sequence[CutTimber],
    view: Optional[ViewAxes] = None,
) -> Remaining:
    """What of `target` the measurements leave unsolved, given the `known` features.

    `cut_timbers` must hold every timber the target, measurements and known features are on.
    """
    carriers = _carriers_for([target, *_handles(measures, known)], cut_timbers)
    return remaining(_known_rows(measures, known, carriers, view), feature_handle_dof_rows(target, carriers))


@dataclass(frozen=True)
class FeatureReport:
    """One target feature, and what of it is still unsolved. `remaining` is None if it has no recipe."""
    handle: FeatureHandle
    remaining: Optional[Remaining]


@dataclass(frozen=True)
class SolveReport:
    """What the measurements leave unsolved: per target feature, and in total."""
    features: List[FeatureReport]
    total: Remaining


def solve_report(
    targets: Sequence[FeatureHandle],
    measures: Sequence[Measure],
    known: Sequence[FeatureHandle],
    cut_timbers: Sequence[CutTimber],
    view: Optional[ViewAxes] = None,
) -> SolveReport:
    """Remaining DOFs of each target, and of all of them together, given the `known` features.

    Targets may be on any number of timbers. `cut_timbers` must hold every timber the targets,
    measurements and known features are on; a frame's `cut_timbers` will do.
    """
    carriers = _carriers_for([*targets, *_handles(measures, known)], cut_timbers)
    known_rows = _known_rows(measures, known, carriers, view)
    reports: List[FeatureReport] = []
    target_rows: List[Row] = []
    for handle in targets:
        recipe = handle.feature.solve_recipe(handle.owner)
        if recipe is None:
            reports.append(FeatureReport(handle, None))
            continue
        rows = feature_dof_rows(recipe, carriers)
        target_rows += rows
        reports.append(FeatureReport(handle, remaining(known_rows, rows)))
    return SolveReport(features=reports, total=remaining(known_rows, target_rows))


def required_targets(cut_timber: CutTimber, face_test: FaceTest = face_reaches_surface) -> List[FeatureHandle]:
    """The features `required_features` finds on `cut_timber`, as targets for `solve_report`."""
    return [required.handle for required in required_features(cut_timber, face_test)]
