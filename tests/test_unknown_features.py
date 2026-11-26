"""unknown_features: what a hand-dimensioned shop drawing leaves unknown, on the cute frame's side timber."""

import importlib.util
import warnings
from dataclasses import replace
from pathlib import Path

import pytest

from kumiki import Beside, DimensionSide, Measure, MortiseAndTenonFeatures as MT, TimberFace
from kumiki.drawings.auto_drawings import unknown_features

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def frame():
    spec = importlib.util.spec_from_file_location("cute_frame_unknowns", REPO / "patterns" / "structures" / "my_cute_frame.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec.loader.exec_module(module)
        return module.my_cute_frame()


def _side(frame):
    return next(drawing for drawing in frame.drawings if drawing.name.startswith("Left Side"))


def _names(frame, drawing):
    return [gap.handle.feature.name for gap in unknown_features(frame, drawing)]


def test_what_the_drawing_leaves_out_is_unknown_and_what_it_gives_is_not(frame):
    names = _names(frame, _side(frame))
    # Its overall length isn't dimensioned, nor how deep the mortises go.
    assert "rptw.top" in names
    assert MT.MORTISE_BOTTOM in names
    # Its long faces come to size from the cut list.
    assert "rptw.right" not in names


def test_dimensioning_a_feature_makes_it_known(frame):
    drawing = _side(frame)
    cut = frame.cut_timber_of(drawing.timbers[0])
    length = Measure(cut.face(TimberFace.BOTTOM), cut.face(TimberFace.TOP), placement=Beside(DimensionSide.ABOVE))
    given = replace(drawing, measurements={"Inside face": [length]})
    assert "rptw.top" not in _names(frame, given)


def test_only_a_drawing_of_one_piece_is_checked(frame):
    plan = next(drawing for drawing in frame.drawings if len(drawing.timbers) > 1)
    with pytest.raises(ValueError):
        unknown_features(frame, plan)
