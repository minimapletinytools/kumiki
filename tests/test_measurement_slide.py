"""Sliding a dimension along the two lines it measures (MeasurementPlacement.along), and the extents
the viewer draws a feature on to its anchor from."""

import pytest

from kumiki.drawings.drawing import (LineSpan, MeasurementKind, MeasurementPlacement, PointSpan, distance_anchors,
                                     slide_axis)
from kumiki.drawings.kigumi_measuring_helpers import place_pair
from kumiki.geometry import Line, Point
from kumiki.rule import create_v3

PERPENDICULAR = MeasurementKind.parse("projected_perpendicular_distance")


def _line(at, direction, interval):
    return LineSpan(at=create_v3(*at), direction=create_v3(*direction), interval=interval)


def _floats(vector):
    return [float(part) for part in vector]


# Two parallel lines along x, one above the other, overlapping between x = 1 and x = 3.
LOW = _line((0, 0, 0), (1, 0, 0), (0.0, 3.0))
HIGH = _line((1, 0, 2), (1, 0, 0), (0.0, 4.0))


def test_by_default_the_anchors_sit_in_the_middle_of_the_overlap():
    a, b = distance_anchors(LOW, HIGH, PERPENDICULAR)

    assert _floats(a) == pytest.approx([2, 0, 0])
    assert _floats(b) == pytest.approx([2, 0, 2])


def test_along_slides_both_anchors_together_so_it_stays_square():
    a, b = distance_anchors(LOW, HIGH, PERPENDICULAR, along=1.5)

    assert _floats(a) == pytest.approx([3.5, 0, 0])
    assert _floats(b) == pytest.approx([3.5, 0, 2])


def test_it_slides_past_the_end_of_a_line_rather_than_stopping():
    # The viewer draws LOW on to its anchor from its end at x = 3.
    a, _b = distance_anchors(LOW, HIGH, PERPENDICULAR, along=5.0)

    assert _floats(a) == pytest.approx([7, 0, 0])


def test_the_slide_reads_the_same_way_whichever_end_is_first():
    reversed_low = _line((3, 0, 0), (-1, 0, 0), (0.0, 3.0))

    one = distance_anchors(LOW, HIGH, PERPENDICULAR, along=1.0)[0]
    other = distance_anchors(reversed_low, HIGH, PERPENDICULAR, along=1.0)[0]

    assert _floats(slide_axis(reversed_low)) == pytest.approx([1, 0, 0])
    assert _floats(one) == pytest.approx(_floats(other))


def test_a_placement_reads_along_from_the_wire():
    assert MeasurementPlacement.from_wire({"offset": 0.1, "along": -0.25}) == MeasurementPlacement(0.1, -0.25)
    without = MeasurementPlacement.from_wire({"offset": 0.1})
    assert without is not None and without.along is None


def test_place_pair_says_which_way_it_slides_and_how_far_each_line_goes():
    one = Line(point=create_v3(0, 0, 0), direction=create_v3(1, 0, 0))
    other = Line(point=create_v3(1, 0, 2), direction=create_v3(1, 0, 0))

    placed = place_pair(one, other, LOW, HIGH, PERPENDICULAR, create_v3(0, 1, 0), None, False, along=0.5)

    low, high = placed.extents
    assert placed.slide is not None and _floats(placed.slide) == pytest.approx([1, 0, 0])
    assert low is not None and high is not None and placed.anchors is not None
    assert _floats(low[0]) + _floats(low[1]) == pytest.approx([0, 0, 0, 3, 0, 0])
    assert _floats(high[0]) + _floats(high[1]) == pytest.approx([1, 0, 2, 5, 0, 2])
    assert _floats(placed.anchors[0]) == pytest.approx([2.5, 0, 0])


def test_a_point_has_no_line_to_extend_and_a_point_to_line_distance_does_not_slide():
    point = PointSpan(at=create_v3(2, 0, 5))

    placed = place_pair(Point(position=create_v3(2, 0, 5)), Line(point=create_v3(0, 0, 0), direction=create_v3(1, 0, 0)),
                        point, LOW, PERPENDICULAR, create_v3(0, 1, 0), None, False)

    assert placed.slide is None
    assert placed.extents[0] is None and placed.extents[1] is not None
