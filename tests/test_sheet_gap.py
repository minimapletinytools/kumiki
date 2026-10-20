"""sheet_gap: how far apart two marks are on the sheet, looking down -z."""

import numpy as np
import pytest

from kumiki.drawings.sheet_shape import SheetLine, SheetPoint, sheet_gap

LOOK = np.array([0.0, 0.0, -1.0])


def test_two_points_at_different_depths_are_their_distance_on_the_sheet():
    assert sheet_gap(SheetPoint(np.array([0.0, 0.0, 5.0])), SheetPoint(np.array([3.0, 4.0, -2.0])), LOOK) == pytest.approx(5)


def test_a_point_and_a_line_either_way_round():
    line = SheetLine(np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    point = SheetPoint(np.array([7.0, 3.0, 9.0]))
    assert sheet_gap(point, line, LOOK) == pytest.approx(2)
    assert sheet_gap(line, point, LOOK) == pytest.approx(2)


def test_parallel_lines_are_apart_and_crossing_ones_are_not():
    one = SheetLine(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    assert sheet_gap(one, SheetLine(np.array([5.0, -3.0, 1.0]), np.array([-1.0, 0.0, 0.0])), LOOK) == pytest.approx(3)
    assert sheet_gap(one, SheetLine(np.array([0.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])), LOOK) is None
