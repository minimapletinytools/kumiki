"""What a feature draws as on a sheet, looking along a view.

A point is a point. A line end-on is a point, otherwise a line. A plane edge-on is a line,
otherwise an area (None). SQUARE_TO_VIEW decides end-on, edge-on and parallel. The viewer's dotted
lines use their own face-on rule (drawing-overlays.js, FACE_ON_DOT).
"""

from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

from ..geometry import Line, Plane, Point
from ..rule import as_ndarray, unit_ndarray

#: The sine of the angle a line may be off end-on, or a plane off edge-on, and still count.
SQUARE_TO_VIEW = 1e-6


@dataclass(frozen=True, eq=False)
class SheetPoint:
    """Drawn as a point; `at` is a point of the feature (not flattened)."""
    at: np.ndarray


@dataclass(frozen=True, eq=False)
class SheetLine:
    """Drawn as a line through `at` (not flattened) along unit `run`, which lies in the sheet."""
    at: np.ndarray
    run: np.ndarray


SheetShape = Union[SheetPoint, SheetLine]


def sheet_shape(located: Optional[Union[Point, Line, Plane]], look) -> Optional[SheetShape]:
    """Return what `located` draws as looking along `look`, or None for an area or an unlocated feature."""
    look = unit_ndarray(as_ndarray(look))
    if isinstance(located, Point):
        return SheetPoint(as_ndarray(located.position))
    if isinstance(located, Line):
        direction = unit_ndarray(as_ndarray(located.direction))
        flat = direction - look * float(direction @ look)
        length = float(np.linalg.norm(flat))
        if length <= SQUARE_TO_VIEW:
            return SheetPoint(as_ndarray(located.point))
        return SheetLine(as_ndarray(located.point), flat / length)
    if isinstance(located, Plane):
        normal = unit_ndarray(as_ndarray(located.normal))
        if abs(float(normal @ look)) > SQUARE_TO_VIEW:
            return None
        return SheetLine(as_ndarray(located.point), unit_ndarray(np.cross(normal, look)))
    return None


def sheet_gap(one: SheetShape, other: SheetShape, look) -> Optional[float]:
    """Return the distance across the sheet between two marks, or None for two crossing lines."""
    look = unit_ndarray(as_ndarray(look))
    if isinstance(one, SheetLine) and isinstance(other, SheetLine):
        if float(np.linalg.norm(np.cross(one.run, other.run))) > SQUARE_TO_VIEW:
            return None
    elif isinstance(one, SheetLine):
        one, other = other, one
    gap = other.at - one.at
    gap = gap - look * float(gap @ look)
    if isinstance(other, SheetLine):
        gap = gap - other.run * float(gap @ other.run)
    return float(np.linalg.norm(gap))
