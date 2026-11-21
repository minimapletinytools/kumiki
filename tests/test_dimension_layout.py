"""Tests for kumiki.drawings.dimension_layout."""

import numpy as np

from kumiki.drawings.dimension_layout import place_dimensions

PAGE = {"width": 0.4, "height": 0.3}
# A plate 0.8 wide and 0.2 tall at the origin, seen square on.
PLATE = (np.array([[-0.4, -0.1, 0], [0.4, -0.1, 0], [0.4, 0.1, 0], [-0.4, 0.1, 0]], float),
         np.array([[0, 1, 2], [0, 2, 3]]))


def _measure(a, b, origin="code", **extra):
    length = float(np.linalg.norm(np.subtract(b, a)))
    return {"a": {"at": list(a)}, "b": {"at": list(b)}, "origin": origin,
            "settled": {"value": {"unit": "length", "value": length}}, **extra}


def _viewport(*measures, projection="orthographic"):
    return {"camera": {"right": [1, 0, 0], "up": [0, 1, 0], "look": [0, 0, -1], "target": [0, 0, 0],
                       "extent": 0.5},
            "rect": [0, 0, 1, 1], "projection": projection, "measurements": list(measures)}


def test_a_dimension_along_the_top_edge_goes_above_the_work():
    placed = place_dimensions(_viewport(_measure((-0.4, 0.1, 0), (0.4, 0.1, 0))), PAGE, [PLATE])
    # Positive offset is sheet-down (into the plate) for this run; above it is negative.
    assert placed[0]["offset"] < 0


def test_dimensions_at_the_same_place_take_different_lanes():
    top = _measure((-0.4, 0.1, 0), (0.4, 0.1, 0))
    part = _measure((-0.4, 0.1, 0), (0.0, 0.1, 0))
    placed = place_dimensions(_viewport(top, part), PAGE, [PLATE])
    assert set(placed) == {0, 1}
    assert abs(placed[0]["offset"] - placed[1]["offset"]) > 1e-3


def test_only_unplaced_code_lengths_are_placed():
    edge = ((-0.4, 0.1, 0), (0.4, 0.1, 0))
    viewport = _viewport(_measure(*edge, origin="file"), _measure(*edge, placement={"offset": 0.05}),
                         _measure(*edge))
    assert set(place_dimensions(viewport, PAGE, [PLATE])) == {2}


def test_a_perspective_viewport_is_left_alone():
    viewport = _viewport(_measure((-0.4, 0.1, 0), (0.4, 0.1, 0)), projection="perspective")
    assert place_dimensions(viewport, PAGE, [PLATE]) == {}
