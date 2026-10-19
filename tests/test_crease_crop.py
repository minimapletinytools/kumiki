"""Where a line is an edge of a solid: on its surface, and where the surface creases along it
(cropcsg.crop_line_to_crease_segments_on_csg, is_crease_at)."""

import pytest

from kumiki.csg.cropcsg import crop_line_to_boundary_segments_on_csg, crop_line_to_crease_segments_on_csg, is_crease_at
from kumiki.csg.cutcsg import Cylinder, Difference, RectangularPrism, SolidUnion
from kumiki.geometry import Line
from kumiki.rule import Transform, create_v2, create_v3, scalar


def _box(x, y, z):
    """An axis-aligned box from (low, high) along each axis."""
    return RectangularPrism(size=create_v2(x[1] - x[0], y[1] - y[0]),
                            transform=Transform(position=create_v3((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, 0),
                                                orientation=Transform.identity().orientation),
                            start_distance=scalar(z[0]), end_distance=scalar(z[1]))


def _along_y(x, z):
    return Line(point=create_v3(x, 0, z), direction=create_v3(0, 1, 0))


def _lengths(segments):
    return [round(float((segment.end - segment.start).norm()), 6) for segment in segments or []]


# Two boxes side by side, tops flush: one flat top across x = 1.
FLUSH = SolidUnion(children=[_box((0, 1), (0, 1), (0, 1)), _box((1, 2), (0, 1), (0, 1))])


def test_a_line_through_a_flat_face_is_on_the_surface_and_no_edge():
    line = _along_y(1, 1)

    assert _lengths(crop_line_to_boundary_segments_on_csg(line, FLUSH, seed_reach=10)) == [1.0]
    assert crop_line_to_crease_segments_on_csg(line, FLUSH, seed_reach=10) == []
    assert not is_crease_at(line, FLUSH, create_v3(1, 0.5, 1))


def test_an_arris_is_an_edge():
    assert _lengths(crop_line_to_crease_segments_on_csg(_along_y(0, 1), FLUSH, seed_reach=10)) == [1.0]
    assert is_crease_at(_along_y(2, 0), FLUSH, create_v3(2, 0.5, 0))


def test_a_notch_s_inside_corner_is_an_edge():
    notched = Difference(_box((0, 2), (0, 1), (0, 1)), [_box((1, 3), (-1, 2), (0.5, 2))])

    assert _lengths(crop_line_to_crease_segments_on_csg(_along_y(1, 0.5), notched, seed_reach=10)) == [1.0]


def test_an_edge_flush_for_part_of_its_length_is_kept_only_where_it_creases():
    # The second box is only half as deep: along x = 1 at the top, flat where both are, an arris past it.
    partly = SolidUnion(children=[_box((0, 1), (0, 1), (0, 1)), _box((1, 2), (0, 0.5), (0, 1))])

    assert _lengths(crop_line_to_crease_segments_on_csg(_along_y(1, 1), partly, seed_reach=10)) == [0.5]


def test_a_cylinder_s_barrel_has_no_edge_along_it_and_its_rim_meets_the_cap():
    rod = Cylinder(axis_direction=create_v3(0, 1, 0), radius=scalar(1), position=create_v3(0, 0, 0),
                   start_distance=scalar(0), end_distance=scalar(2))
    along = Line(point=create_v3(0, 0, 1), direction=create_v3(0, 1, 0))

    assert crop_line_to_crease_segments_on_csg(along, rod, seed_reach=10) == []
    assert is_crease_at(Line(point=create_v3(0, 2, 1), direction=create_v3(1, 0, 0)), rod, create_v3(0, 2, 1))
