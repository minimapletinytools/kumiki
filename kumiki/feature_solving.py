"""Measurements on a cut timber, as rows over its solving entities, and what they leave unsolved.

The interface layer of docs/internal/featuresolving-plan.md, Part 2 D: FeatureHandles and
Measures in, rows and remaining DOFs out. Works in the timber's local space, where its CSG tree is.
"""

from typing import List, Optional, Sequence

from .cutcsg import solve_entity_map
from .dof_solver import Remaining, remaining
from .drawing import (Measure, MeasureSpan, MeasurementDirection, MeasurementKind,
                      MeasurementOperation, MeasurementSpace, ViewAxes, distance_anchors)
from .feature_paths import FeatureHandle
from .geometry import Line, Plane, Point
from .rule import V3, safe_norm
from .solve_recipe import (Anchor, DistanceMeasurement, EntityMap, Recipe, Row, feature_rows,
                           measurement_row)
from .timber import CutTimber

THREE_D_DISTANCE = MeasurementKind(MeasurementOperation.DISTANCE, MeasurementSpace.THREE_D)


def entity_map_of(cut_timber: CutTimber) -> EntityMap:
    """The solving entities of a cut timber's rendered tree, the tree its handles point into."""
    return solve_entity_map(cut_timber.render_timber_with_cuts_csg_local())


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
        return MeasureSpan(at=located.position)
    if isinstance(located, Line):
        ends = extent.ends if extent is not None else None
        interval = None
        if ends:
            direction = located.direction / safe_norm(located.direction)
            stations = sorted(float(((end - located.point).T * direction)[0, 0]) for end in ends)
            interval = (stations[0], stations[-1])
        return MeasureSpan(at=located.point, direction=located.direction, interval=interval)
    if isinstance(located, Plane):
        return MeasureSpan(at=extent.anchor if extent is not None else located.point, normal=located.normal)
    raise ValueError(f"{handle.feature.name!r} has no plane, line or point to measure to")


def feature_handle_rows(handle: FeatureHandle, entities: EntityMap) -> List[Row]:
    """The feature's own unknowns as rows: it is solved when all of them are known."""
    return feature_rows(_recipe(handle), entities)


def measure_row(measure: Measure, entities: EntityMap, view: Optional[ViewAxes] = None) -> Row:
    """How a measurement's value changes with the solving entities' unknowns.

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
        if kind.direction is MeasurementDirection.PERPENDICULAR or not (first.is_point and second.is_point):
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
    ), entities)


def remaining_dofs(
    target: FeatureHandle,
    measures: Sequence[Measure],
    known: Sequence[FeatureHandle],
    cut_timber: CutTimber,
    view: Optional[ViewAxes] = None,
) -> Remaining:
    """What of `target` the measurements leave unsolved, given the `known` features."""
    entities = entity_map_of(cut_timber)
    rows: List[Row] = [row for handle in known for row in feature_handle_rows(handle, entities)]
    rows += [measure_row(measure, entities, view) for measure in measures]
    return remaining(rows, feature_handle_rows(target, entities))
