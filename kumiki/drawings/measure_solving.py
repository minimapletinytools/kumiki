"""Converts a drawing's Measure into a SolveMeasurement for csg/feature_solving.py: which features,
and where and along what it is read.
"""

from typing import TYPE_CHECKING, Dict, Hashable, Optional, Sequence, Union

import numpy as np

from ..csg.feature_paths import FeatureHandle, hit_identity
from ..csg.carriers import Row
from ..csg.feature_solving import Solve, SolveAngle, SolveDistance, SolveMeasurement
from ..geometry import Line, Plane
from ..rule import Matrix, as_ndarray, unit_ndarray
from .measure import (LineSpan, Measure, MeasureSpan, MeasurementDirection, MeasurementKind,
                        MeasurementOperation, MeasurementSpace, PointSpan, ViewAxes, distance_anchors)
from .feature_span import feature_span
from .sheet_shape import SheetLine, sheet_shape

if TYPE_CHECKING:
    from ..timber import CutTimber

THREE_D_DISTANCE = MeasurementKind(MeasurementOperation.DISTANCE, MeasurementSpace.THREE_D)

#: Features' spans, kept across the measurements of one solve: every candidate to a feature asks for it.
SpanMemo = Dict[Hashable, MeasureSpan]


def _measured_span(handle: FeatureHandle, cut_timbers: Sequence['CutTimber'],
                   spans_memo: Optional[SpanMemo]) -> MeasureSpan:
    """Return the feature's span in world space, cropped to its cut timber (feature_span)."""
    key = (id(handle.timber), hit_identity(handle.feature, handle.owner))
    if spans_memo is not None and key in spans_memo:
        return spans_memo[key]
    cut = next((cut for cut in cut_timbers if cut.timber is handle.timber), None)
    if cut is None:
        raise ValueError(f"{handle.feature.name!r} is on a timber not in cut_timbers")
    span = feature_span(handle, cut.feature_extents(), in_three_d=True)
    if span is None:
        raise ValueError(f"{handle.feature.name!r} has no plane, line or point to measure to")
    if spans_memo is not None:
        spans_memo[key] = span
    return span


def _projected(span: MeasureSpan, look: np.ndarray) -> MeasureSpan:
    """Return a span as seen on a sheet looking along `look` (sheet_shape), or None."""
    if isinstance(span, PointSpan):
        return span
    if isinstance(span, LineSpan):
        shape = sheet_shape(Line(direction=span.along, point=span.at), look)
        if not isinstance(shape, SheetLine):
            return PointSpan(at=span.at)
        # Lengths along the line shrink by how far it leans into the sheet.
        scale = float(as_ndarray(span.along) @ shape.run)
        interval = None if span.interval is None else (span.interval[0] * scale, span.interval[1] * scale)
        return LineSpan(at=span.at, direction=Matrix(shape.run), interval=interval)
    shape = sheet_shape(Plane(normal=span.facing, point=span.at), look)
    if not isinstance(shape, SheetLine):
        raise ValueError("a face seen at an angle covers the sheet, so nothing is measured to it")
    return LineSpan(at=span.at, direction=Matrix(shape.run))


def _on_feature(span: MeasureSpan, anchor: np.ndarray, look: np.ndarray) -> np.ndarray:
    """Return the point on the 3D feature that a sheet anchor stands for."""
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
                      spans_memo: Optional[SpanMemo] = None, across: Optional[np.ndarray] = None,
                      ) -> SolveMeasurement:
    """Return what `measure`, seen through `view`, measures, for the solver.

    Raises ValueError if it measures nothing (a face seen at an angle, two features in one place).
    `across` is the direction to read a perpendicular distance along when the features coincide.
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
        return SolveDistance(a, b, at_a, at_b, across if across is not None else _gap_direction(at_a, at_b))

    if kind.direction is not MeasurementDirection.PERPENDICULAR:
        if not (isinstance(first, PointSpan) and isinstance(second, PointSpan)):
            raise ValueError(f"a {kind.name} is only taken between two points")
        along = unit_ndarray(as_ndarray(view.right if kind.direction is MeasurementDirection.HORIZONTAL else view.up))
        return SolveDistance(a, b, as_ndarray(first.at), as_ndarray(second.at), along)

    flat_first, flat_second = _projected(first, look), _projected(second, look)
    anchor_a, anchor_b = (as_ndarray(point) for point in distance_anchors(flat_first, flat_second, kind, view))
    return SolveDistance(a, b, _on_feature(first, anchor_a, look), _on_feature(second, anchor_b, look),
                         across if across is not None else _gap_direction(anchor_a, anchor_b, look))


class DrawingSolve(Solve):
    """A Solve over a drawing's Measures, caching each feature's span and each measure's row."""

    def __init__(self, cut_timbers: Sequence['CutTimber']):
        super().__init__(cut_timbers)
        self.spans_memo: SpanMemo = {}
        # A row, or why there is none, per (measure, view).
        self.rows_memo: Dict[Hashable, Union[Row, ValueError]] = {}

    def row(self, measure: Measure, view: Optional[ViewAxes] = None, across: Optional[np.ndarray] = None) -> Row:
        """Return the row of `measure` seen through `view`. Raises ValueError if it measures nothing."""
        view = view or ViewAxes()
        key = (measure, *(float(part) for axis in (view.look, view.right, view.up) for part in axis),
               None if across is None else tuple(float(part) for part in across))
        if key not in self.rows_memo:
            try:
                self.rows_memo[key] = self.measure_row(
                    solve_measurement(measure, self.cut_timbers, view, self.spans_memo, across))
            except ValueError as refused:
                self.rows_memo[key] = refused
        found = self.rows_memo[key]
        if isinstance(found, ValueError):
            raise found
        return found
