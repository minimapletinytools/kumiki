"""What a drawing's view can see (kumiki/drawings/visibility.py): a place, and a whole feature."""

import runpy
import warnings
from pathlib import Path

import numpy as np
import pytest

from kumiki.csg.cutcsg import CutCSGLabel, Difference, RectangularPrism
from kumiki.drawings.required_features import required_features
from kumiki.drawings.visibility import nearest_visible_depth, sight_is_blocked
from kumiki.rule import Transform, create_v2, create_v3, scalar

PATTERN = Path(__file__).resolve().parent.parent / "patterns" / "structures" / "my_cute_frame_drawing_test.py"


def _box(x, y, z):
    """An axis-aligned box from (low, high) along each axis."""
    return RectangularPrism(
        size=create_v2(x[1] - x[0], y[1] - y[0]),
        transform=Transform(position=create_v3((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, 0),
                            orientation=Transform.identity().orientation),
        start_distance=scalar(z[0]), end_distance=scalar(z[1]))


def test_a_line_of_sight_along_a_surface_and_then_into_material_is_blocked():
    # A slot cut into a block's left face: its floor runs from the slot out into solid block. A line
    # of sight from the floor, along it, is surface first and material after.
    # Most of the way is floor: judging by the middle of the way, as this used to, missed the block.
    block = Difference(_box((-1, 1), (-1, 1), (0, 4)), [_box((-2, -0.5), (-0.5, 0.8), (-1, 5))],
                       label=CutCSGLabel("slotted"))

    assert sight_is_blocked(block, create_v3(-0.5, 0, 2), create_v3(0, 1, 0))
    assert not sight_is_blocked(block, create_v3(-0.5, 0, 2), create_v3(-1, 0, 0))  # out of the slot's open end


@pytest.fixture(scope="module")
def left_side():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pattern = runpy.run_path(str(PATTERN))
    cut = next(c for c in pattern["_load_cute_frame"]()().cut_timbers if c.timber.ticket.path == "Left Side")
    look = np.array([float(v) for v in pattern["_shop_sheets"](cut.timber)["front"][0].look])
    root = cut.render_timber_with_cuts_csg_local()

    def depth(name, reach=3.0):
        handle = next(r.handle for r in required_features(cut) if r.handle.feature.name == name)
        return nearest_visible_depth(handle, root, look / np.linalg.norm(look), [(root, cut.timber.transform)], reach)

    return depth


@pytest.mark.parametrize("name", ["mortise_bottom", "mortise_right", "mortise_left"])
def test_a_blind_mortise_opening_on_the_side_is_hidden_from_the_front(left_side, name):
    assert left_side(name) is None


def test_the_timber_s_own_face_is_seen_and_a_bore_s_axis_always_is(left_side):
    assert left_side("rptw.left") is not None
    assert left_side("peg_hole_axis") is not None


@pytest.mark.parametrize("name", ["mortise_right", "rptw.left"])
def test_how_far_the_plane_is_cut_does_not_change_the_answer(left_side, name):
    # A clip of an edge lying all but along the cutting line used to spike to the edge of the plane,
    # so a hidden wall came out seen at some reaches.
    answers = {left_side(name, reach) is None for reach in (0.5, 2.76, 10.0)}

    assert len(answers) == 1
