"""A drawing's Measure as the feature solver takes it (csg/feature_solving.py).

The solver only wants which features, and where and along what the measurement is read. Working
that out is drawing's: each feature's span, what it draws as on the sheet, and where a dimension
between the two attaches (distance_anchors).
"""

from typing import TYPE_CHECKING, Dict, Hashable, Optional, Sequence

import numpy as np

from ..csg.feature_paths import FeatureHandle
from ..csg.carriers import Row
from ..csg.feature_solving import Solve, SolveAngle, SolveDistance, SolveMeasurement
from ..rule import Matrix, as_ndarray, unit_ndarray
from .drawing import (LineSpan, Measure, MeasureSpan, MeasurementDirection, MeasurementKind, MeasurementOperation,
                      MeasurementSpace, PointSpan, ViewAxes, distance_anchors)
from .feature_span import feature_span

if TYPE_CHECKING:
    from ..timber import CutTimber

THREE_D_DISTANCE = MeasurementKind(MeasurementOperation.DISTANCE, MeasurementSpace.THREE_D)

#: Features' spans, kept across the measurements of one solve: every candidate to a feature asks for it.
SpanMemo = Dict[Hashable, MeasureSpan]


def _measured_span(handle: FeatureHandle, cut_timbers: Sequence['CutTimber'],
                   spans_memo: Optional[SpanMemo]) -> MeasureSpan:
    """The feature in world space, on its cut timber, as the viewer measures it (feature_span)."""
    key = (id(handle.owner), handle.feature.name, id(handle.timber))
    if spans_memo is not None and key in spans_memo:
        return spans_memo[key]
    cut = next((cut for cut in cut_timbers if cut.timber is handle.timber), None)
    if cut is None:
        raise ValueError(f"{handle.feature.name!r} is on a timber not in cut_timbers")
    span = feature_span(handle, cut.render_timber_with_cuts_csg_local(), in_three_d=True)
    if span is None:
        raise ValueError(f"{handle.feature.name!r} has no plane, line or point to measure to")
    if spans_memo is not None:
        spans_memo[key] = span
    return span


def _projected(span: MeasureSpan, look: np.ndarray) -> MeasureSpan:
    """A span as it is seen on a sheet looking along `look`: a point stays a point, an edge-on face is a line."""
    if isinstance(span, PointSpan):
        return span
    if isinstance(span, LineSpan):
        flat = as_ndarray(span.along) - look * float(as_ndarray(span.along) @ look)
        if np.linalg.norm(flat) < 1e-9:
            return PointSpan(at=span.at)
        scale = float(np.linalg.norm(flat))
        interval = None if span.interval is None else (span.interval[0] * scale, span.interval[1] * scale)
        return LineSpan(at=span.at, direction=Matrix(flat / scale), interval=interval)
    edge = np.cross(as_ndarray(span.facing), look)
    if np.linalg.norm(edge) < 1e-9 or abs(float(as_ndarray(span.facing) @ look)) > 1e-6:
        raise ValueError("a face seen at an angle covers the sheet, so nothing is measured to it")
    return LineSpan(at=span.at, direction=Matrix(unit_ndarray(edge)))


def _on_feature(span: MeasureSpan, anchor: np.ndarray, look: np.ndarray) -> np.ndarray:
    """The point of the 3D feature that a sheet anchor stands for."""
    if isinstance(span, LineSpan):
        direction = as_ndarray(span.along)
        flat = direction - look * float(direction @ look)
        if float(flat @ flat) > 1e-18:
            return as_ndarray(span.at) + direction * float((anchor - as_ndarray(span.at)) @ flat) / float(flat @ flat)
    return anchor


def _gap_direction(at_a: np.ndarray, at_b: np.ndarray, look: Optional[np.ndarray] = None) -> np.ndarray:
    gap = at_b - at_a
    if look is not None:
        gap = gap - look * float(gap @ look)
    length = float(np.linalg.norm(gap))
    if length < 1e-12:
        raise ValueError("the two features are in the same place, so there is no direction to measure along")
    return gap / length


def solve_measurement(measure: Measure, cut_timbers: Sequence['CutTimber'], view: Optional[ViewAxes] = None,
                      spans_memo: Optional[SpanMemo] = None) -> SolveMeasurement:
    """What `measure`, seen through `view` (world space), measures, for the solver.

    Each feature is measured where it is on its cut timber, found among `cut_timbers` -- as the
    viewer measures it.

    Distances and angles, in 3D or on a sheet, between features on one timber or two. Raises
    ValueError for one that measures nothing: a face seen at an angle, two features in one place.
    """
    kind = measure.kind or THREE_D_DISTANCE
    view = view or ViewAxes()
    a, b = measure.anchor_a, measure.anchor_b
    look = unit_ndarray(as_ndarray(view.look)) if kind.space is MeasurementSpace.PROJECTED else None

    if kind.operation is MeasurementOperation.ANGLE:
        return SolveAngle(a, b, look)

    first, second = _measured_span(a, cut_timbers, spans_memo), _measured_span(b, cut_timbers, spans_memo)
    if look is None:
        at_a, at_b = (as_ndarray(point) for point in distance_anchors(first, second, kind, view))
        return SolveDistance(a, b, at_a, at_b, _gap_direction(at_a, at_b))

    if kind.direction is not MeasurementDirection.PERPENDICULAR:
        if not (isinstance(first, PointSpan) and isinstance(second, PointSpan)):
            raise ValueError(f"a {kind.name} is only taken between two points")
        along = unit_ndarray(as_ndarray(view.right if kind.direction is MeasurementDirection.HORIZONTAL else view.up))
        return SolveDistance(a, b, as_ndarray(first.at), as_ndarray(second.at), along)

    flat_first, flat_second = _projected(first, look), _projected(second, look)
    anchor_a, anchor_b = (as_ndarray(point) for point in distance_anchors(flat_first, flat_second, kind, view))
    return SolveDistance(a, b, _on_feature(first, anchor_a, look), _on_feature(second, anchor_b, look),
                         _gap_direction(anchor_a, anchor_b, look))


class DrawingSolve(Solve):
    """A Solve that takes a drawing's Measures, keeping each feature's span for the solve."""

    def __init__(self, cut_timbers: Sequence['CutTimber']):
        super().__init__(cut_timbers)
        self.spans_memo: SpanMemo = {}

    def row(self, measure: Measure, view: Optional[ViewAxes] = None) -> Row:
        """How `measure`, seen through `view`, changes with the carriers' unknowns. Raises ValueError
        for one that measures nothing (solve_measurement)."""
        return self.measure_row(solve_measurement(measure, self.cut_timbers, view, self.spans_memo))
