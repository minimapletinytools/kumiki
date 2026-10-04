"""Measurements on a cut timber, as rows over its solving carriers, and what they leave unsolved.

The interface layer of docs/internal/featuresolving-plan.md, Part 2 D: FeatureHandles and
Measures in, rows and remaining DOFs out. Works in the timber's local space, where its CSG tree is.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

from .cutcsg import carrier_map
from .dof_solver import Remaining, remaining
from .drawing import (LineSpan, Measure, MeasureSpan, MeasurementDirection, MeasurementKind, PlaneSpan, PointSpan,
                      MeasurementOperation, MeasurementSpace, ViewAxes, distance_anchors)
from .feature_paths import FeatureHandle
from .geometry import Line, Plane, Point
from .planar_region import face_reaches_surface
from .required_features import FaceTest, RequiredFeature, required_features
from .rule import V3, safe_norm
from .solve_recipe import (Anchor, CarrierMap, DistanceMeasurement, Recipe, Row, feature_dof_rows,
                           measurement_row)
from .timber import CutTimber

THREE_D_DISTANCE = MeasurementKind(MeasurementOperation.DISTANCE, MeasurementSpace.THREE_D)


def carrier_map_of(cut_timber: CutTimber) -> CarrierMap:
    """The solving carriers of a cut timber's rendered tree, the tree its handles point into."""
    return carrier_map(cut_timber.render_timber_with_cuts_csg_local())


def _recipe(handle: FeatureHandle) -> Recipe:
    recipe = handle.feature.solve_recipe(handle.owner)
    if recipe is None:
        raise ValueError(f"{handle.feature.name!r} has no solve recipe yet")
    return recipe


def _span(handle: FeatureHandle) -> MeasureSpan:
    """The feature as drawing's measuring rules see it, in the timber's local space."""
    located = handle.feature.locate_simple_unbounded(handle.owner)
    extent = handle.feature.get_extent(handle.owner)
    if isinstance(located, Point):
        return PointSpan(at=located.position)
    if isinstance(located, Line):
        ends = extent.ends if extent is not None else None
        interval = None
        if ends:
            direction = located.direction / safe_norm(located.direction)
            stations = sorted(float(((end - located.point).T * direction)[0, 0]) for end in ends)
            interval = (stations[0], stations[-1])
        return LineSpan(at=located.point, direction=located.direction, interval=interval)
    if isinstance(located, Plane):
        return PlaneSpan(at=extent.anchor if extent is not None else located.point, normal=located.normal)
    raise ValueError(f"{handle.feature.name!r} has no plane, line or point to measure to")


def feature_handle_dof_rows(handle: FeatureHandle, carriers: CarrierMap) -> List[Row]:
    """The feature's own DOFs as rows. See solve_recipe.feature_dof_rows."""
    return feature_dof_rows(_recipe(handle), carriers)


def measure_row(measure: Measure, carriers: CarrierMap, view: Optional[ViewAxes] = None) -> Row:
    """How a measurement's value changes with the solving carriers' unknowns.

    Supports 3D distances, and horizontal or vertical distances between two points on a sheet,
    with `view` in the timber's local space. Both anchors must be on one timber.
    """
    if measure.anchor_a.timber is not measure.anchor_b.timber:
        raise NotImplementedError("a measurement between two timbers")
    kind = measure.kind or THREE_D_DISTANCE
    if kind.operation is not MeasurementOperation.DISTANCE:
        raise NotImplementedError(f"rows for a {kind.name} measurement")

    first, second = _span(measure.anchor_a), _span(measure.anchor_b)
    if kind.space is MeasurementSpace.PROJECTED:
        if kind.direction is MeasurementDirection.PERPENDICULAR or not (
                isinstance(first, PointSpan) and isinstance(second, PointSpan)):
            raise NotImplementedError(f"rows for a {kind.name} measurement")
        view = view or ViewAxes()
        along: V3 = view.right if kind.direction is MeasurementDirection.HORIZONTAL else view.up
        at_a, at_b = first.at, second.at
    else:
        at_a, at_b = distance_anchors(first, second, kind, view)
        gap = at_b - at_a
        length = safe_norm(gap)
        if length < 1e-12:
            raise ValueError("the two features are in the same place, so there is no direction to measure along")
        along = gap / length

    return measurement_row(DistanceMeasurement(
        start=Anchor(_recipe(measure.anchor_a), at_a),
        end=Anchor(_recipe(measure.anchor_b), at_b),
        along=along,
    ), carriers)


def _known_rows(
    measures: Sequence[Measure], known: Sequence[FeatureHandle], carriers: CarrierMap, view: Optional[ViewAxes],
) -> List[Row]:
    rows: List[Row] = [row for handle in known for row in feature_handle_dof_rows(handle, carriers)]
    return rows + [measure_row(measure, carriers, view) for measure in measures]


def remaining_dofs(
    target: FeatureHandle,
    measures: Sequence[Measure],
    known: Sequence[FeatureHandle],
    cut_timber: CutTimber,
    view: Optional[ViewAxes] = None,
) -> Remaining:
    """What of `target` the measurements leave unsolved, given the `known` features."""
    carriers = carrier_map_of(cut_timber)
    return remaining(_known_rows(measures, known, carriers, view), feature_handle_dof_rows(target, carriers))


@dataclass(frozen=True)
class FeatureReport:
    """One required feature, and what of it is still unsolved. `remaining` is None if it has no recipe."""
    required: RequiredFeature
    remaining: Optional[Remaining]


@dataclass(frozen=True)
class SolveReport:
    """What the measurements leave unsolved on a timber: per required feature, and in total."""
    features: List[FeatureReport]
    total: Remaining


def solve_report(
    cut_timber: CutTimber,
    measures: Sequence[Measure],
    known: Sequence[FeatureHandle],
    view: Optional[ViewAxes] = None,
    face_test: FaceTest = face_reaches_surface,
) -> SolveReport:
    """Remaining DOFs of every feature `required_features` finds on `cut_timber`, given the `known` features."""
    carriers = carrier_map_of(cut_timber)
    known_rows = _known_rows(measures, known, carriers, view)
    reports: List[FeatureReport] = []
    target_rows: List[Row] = []
    for required in required_features(cut_timber, face_test):
        recipe = required.handle.feature.solve_recipe(required.handle.owner)
        if recipe is None:
            reports.append(FeatureReport(required, None))
            continue
        rows = feature_dof_rows(recipe, carriers)
        target_rows += rows
        reports.append(FeatureReport(required, remaining(known_rows, rows)))
    return SolveReport(features=reports, total=remaining(known_rows, target_rows))
