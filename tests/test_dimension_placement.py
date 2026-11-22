"""Tests for dimension placement in kumiki.drawings.auto_drawings."""

import numpy as np

from kumiki.drawings.auto_drawings import Dim, SheetView, place

# Square on to the z = 0 plane, on a 400 x 300 mm sheet, 300 sheet mm to the world metre.
VIEW = SheetView(np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.zeros(3), 0.5, (0, 0, 1, 1), (400.0, 300.0))
# A plate 0.8 wide and 0.2 tall at the origin.
PLATE = (np.array([[-0.4, -0.1, 0], [0.4, -0.1, 0], [0.4, 0.1, 0], [-0.4, 0.1, 0]], float),
         np.array([[0, 1, 2], [0, 2, 3]]))


def _dim(index, a, b):
    sa, sb = VIEW.to_sheet([a, b])
    return Dim(index, sa, sb, f"{np.linalg.norm(np.subtract(b, a)) * 1000:.0f}mm", None, None)


def test_a_dimension_along_the_top_edge_goes_above_the_work():
    placed = place([_dim(0, (-0.4, 0.1, 0), (0.4, 0.1, 0))], VIEW, [PLATE])
    # Positive offset is sheet-down (into the plate) for this run; above it is negative.
    offset = placed[0].offset
    assert offset is not None and offset < 0


def test_dimensions_at_the_same_place_take_different_lanes():
    placed = place([_dim(0, (-0.4, 0.1, 0), (0.4, 0.1, 0)), _dim(1, (-0.4, 0.1, 0), (0.0, 0.1, 0))], VIEW, [PLATE])
    first, second = placed[0].offset, placed[1].offset
    assert first is not None and second is not None and abs(first - second) > 1e-3


def test_a_dimension_running_the_other_way_is_offset_the_other_way():
    forward = place([_dim(0, (-0.4, 0.1, 0), (0.4, 0.1, 0))], VIEW, [PLATE])[0].offset
    backward = place([_dim(0, (0.4, 0.1, 0), (-0.4, 0.1, 0))], VIEW, [PLATE])[0].offset
    assert forward is not None and backward is not None and forward == -backward
