"""What a feature is on a sheet: how a point, line or plane draws, looking along a view.

A point is a point. A line seen end-on is a point, and otherwise a line, flattened onto the sheet.
A plane seen edge-on is a line along itself, and otherwise an area -- None: nothing to draw as a
line or to measure to. One tolerance, SQUARE_TO_VIEW, decides end-on, edge-on and parallel alike.

How far apart two marks are on the sheet is `sheet_gap`: what lines up, what is drawn over what,
and the length of a dimension between them all start there.

The viewer's dotted lines ask another question -- whether a plane is seen face-on, where its
outline would only retrace the faces around it -- and keep their own rule (drawing-overlays.js,
FACE_ON_DOT).
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
    """Drawn as a point. `at` is a point of the feature, not flattened."""
    at: np.ndarray


@dataclass(frozen=True, eq=False)
class SheetLine:
    """Drawn as a line through `at` (a point of the feature, not flattened), running along unit `run`,
    which lies in the sheet."""
    at: np.ndarray
    run: np.ndarray


SheetShape = Union[SheetPoint, SheetLine]


def sheet_shape(located: Optional[Union[Point, Line, Plane]], look) -> Optional[SheetShape]:
    """What `located` draws as looking along `look` (both in one frame); None for an area, or for
    something not located (a curved face)."""
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
    """How far apart two marks are across the sheet, looking along `look`: two points, their
    distance; a point and a line, the point's from the line; two lines, the distance between them
    where they are parallel, and None where they cross."""
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
