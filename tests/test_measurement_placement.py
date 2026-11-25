"""Where a code drawing's dimensions go: Auto, Offset and Beside, worked out as offsets on the sheet."""

import numpy as np
import pytest

from kumiki import (Auto, Beside, CutTimber, DimensionSide, Drawing, Frame, Measure, Offset, create_timber, create_v2,
                    create_v3, mm, shop_drawing_viewports, SHOP_DRAWING_IDS)
from kumiki.csg.feature_paths import find_feature
from kumiki.drawings.auto_drawings import BASE_MM, PITCH_MM, _dim, sheet_views, with_placed_dimensions

FRONT = SHOP_DRAWING_IDS["front"]


@pytest.fixture(scope="module")
def beam():
    timber = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(150)),
                           length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 1, 0), ticket="beam")
    cut = CutTimber(timber, cuts=[])
    return Frame(cut_timbers=[cut], name="beam"), cut


def _face(cut, name):
    found = find_feature(cut, [], name)
    assert found is not None
    return found


def _placed(beam, *placements):
    frame, cut = beam
    ends = _face(cut, "rptw.bottom"), _face(cut, "rptw.top")
    drawing = Drawing(name="beam", timbers=[cut.timber], viewports=shop_drawing_viewports(),
                      measurements={FRONT: [Measure(*ends, placement=placement) for placement in placements]})
    placed = with_placed_dimensions(drawing, frame)
    front = placed.viewport_name(FRONT)
    return list(placed.measurements_by_viewport()[front]), sheet_views(placed, [cut])[front]


def _offset(measure):
    assert isinstance(measure.placement, Offset) and measure.placement.offset is not None
    return float(measure.placement.offset)


def test_a_measure_is_placed_automatically_by_default(beam):
    frame, cut = beam
    assert Measure(_face(cut, "rptw.bottom"), _face(cut, "rptw.top")).placement == Auto()
    (measure,), _ = _placed(beam, Auto())
    assert isinstance(measure.placement, Offset) and measure.placement.offset


def test_an_offset_is_kept_as_written(beam):
    (measure,), _ = _placed(beam, Offset(0.25))
    assert measure.placement == Offset(0.25)


def test_lanes_beside_the_work_are_a_pitch_apart_on_the_side_asked_for(beam):
    measures, view = _placed(beam, Beside(DimensionSide.ABOVE, 1), Beside(DimensionSide.ABOVE, 2),
                             Beside(DimensionSide.BELOW, 1))
    first, second, below = (_offset(measure) * view.mm_per_world for measure in measures)
    assert abs(second) - abs(first) == pytest.approx(PITCH_MM, abs=0.5)
    assert np.sign(first) == np.sign(second) == -np.sign(below)


def test_lane_one_sits_a_base_gap_past_the_work(beam):
    frame, cut = beam
    (measure,), view = _placed(beam, Beside(DimensionSide.ABOVE, 1))
    found = _dim(0, measure, view, frame)
    assert found is not None
    dim, swapped = found
    offset = _offset(measure) * view.mm_per_world * (-1 if swapped else 1)
    line = dim.a + dim.away * offset
    corners = [cut.timber.transform.local_to_global(create_v3(x, y, z)) for x in (mm(-50), mm(50))
               for y in (mm(-75), mm(75)) for z in (0, mm(1000))]
    top = view.to_sheet(np.array([[float(v) for v in corner] for corner in corners]))[:, 1].min()
    assert top - line[1] == pytest.approx(BASE_MM, abs=0.6)


def test_a_side_the_dimension_runs_across_is_warned_about_and_placed_automatically(beam):
    with pytest.warns(UserWarning, match="can't go left of the work"):
        (measure,), _ = _placed(beam, Beside(DimensionSide.LEFT))
    assert isinstance(measure.placement, Offset)


def test_lanes_count_from_one():
    with pytest.raises(ValueError, match="count from 1"):
        Beside(DimensionSide.ABOVE, 0)
