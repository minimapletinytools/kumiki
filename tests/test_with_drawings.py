"""with_drawings: the generated plan and piece drawings, changed in code."""

import importlib.util

import pytest

from kumiki import Beside, DimensionSide, Drawing, MortiseAndTenonFeatures as MT, Offset, TimberFace
from kumiki.drawings.auto_drawings import with_drawings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cute():
    spec = importlib.util.spec_from_file_location("cute_frame_for_with_drawings",
                                                  ROOT / "patterns" / "structures" / "my_cute_frame.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.my_cute_frame()


def _between(measure):
    return {measure.anchor_a.feature.name, measure.anchor_b.feature.name}


def test_an_edit_adds_and_removes_dimensions_and_adds_drawings(cute):
    seen = {}

    def edit(drawings):
        piece = drawings.piece("Right Side")
        post = piece.cut_timbers[0]
        front = piece.view("Front")
        seen["generated"] = [_between(m) for m in front._measures]
        seen["removed"] = front.remove(post.face(TimberFace.TOP), post.face(TimberFace.BOTTOM))
        front.measure(post.face(TimberFace.BOTTOM), post.feature(MT.PEG_HOLE_AXIS, 0),
                      placement=Beside(DimensionSide.BELOW, 2))
        drawings.add(Drawing(name="just the post", timbers=[post.timber]))
        # Naming a view or piece that is not there says what is.
        with pytest.raises(KeyError, match="has no view 'Nope'; it has Front"):
            drawings.plan.view("Nope")
        with pytest.raises(KeyError, match="No piece drawing has a timber at 'nobody'"):
            drawings.piece("nobody")

    frame = with_drawings(cute, edit, fixed_path="Left Side").finish()
    by_name = {drawing.name: drawing for drawing in frame.drawings}
    assert "just the post" in by_name
    piece = next(drawing for name, drawing in by_name.items() if name.startswith("Left Side"))  # Right Side matches it
    front = piece.measurements_by_viewport()["Front"]
    assert {"rptw.bottom", MT.PEG_HOLE_AXIS} in [_between(m) for m in front]
    assert all(isinstance(m.placement, Offset) for m in front), "every dimension is placed"
    if {"rptw.top", "rptw.bottom"} in seen["generated"]:
        assert seen["removed"] and {"rptw.top", "rptw.bottom"} not in [_between(m) for m in front]
