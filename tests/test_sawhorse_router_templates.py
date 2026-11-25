"""The dovetailed sawhorse's router templates: the leg template's square wide end, its runouts, and the
switch that shows them in the viewer."""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from kumiki import Kigumi, TimberFace
from kumiki.csg.triangles import mesh_cutcsg

PATTERN = Path(__file__).resolve().parent.parent / "patterns" / "structures" / "dovetailed_sawhorse.py"


@pytest.fixture(scope="module")
def sawhorse():
    spec = importlib.util.spec_from_file_location("sawhorse_for_templates", PATTERN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sawhorse_for_templates"] = module
    spec.loader.exec_module(module)
    frame = module.dovetailed_sawhorse()
    leg = next(cut for cut in frame.cut_timbers if cut.timber.ticket.path == "leg +x +y")
    joint = next(j for j in frame.source_joints if j.cuttings["dovetail_timber"].timber is leg.timber)
    return module, frame, leg.timber, joint


def _leg_template(sawhorse, wide_mm=None, narrow_mm=None):
    module, frame, leg, joint = sawhorse
    values = {}
    if wide_mm is not None:
        values["leg_template_wide_runout"] = {"value": wide_mm / 1000}
    if narrow_mm is not None:
        values["leg_template_narrow_runout"] = {"value": narrow_mm / 1000}
    beam = frame.cut_timbers[0].timber
    _, tail = module._templates(beam, leg, joint.cuttings["receiving_timber"], module.ROUTER_TEMPLATE.resolve(values))
    return mesh_cutcsg(tail).mesh


def _along_leg(sawhorse, mesh):
    up = np.array([float(v) for v in sawhorse[2].get_length_direction_global()])
    along = mesh.vertices @ up
    return float(along.min()), float(along.max())


def test_the_leg_template_s_wide_end_is_square_to_the_leg(sawhorse):
    mesh = _leg_template(sawhorse)
    leg = sawhorse[2]
    up = np.array([float(v) for v in leg.get_length_direction_global()])
    across = np.array([float(v) for v in leg.get_face_direction_global(TimberFace.FRONT)])
    # The faces through the template's thickness, by how far each turns from the leg's length.
    sides = [normal for normal in mesh.face_normals if abs(normal @ across) < 1e-6]
    angles = {round(math.degrees(math.acos(min(1.0, abs(float(normal @ up))))), 2) for normal in sides}
    assert 0.0 in angles, f"no end square to the leg among {sorted(angles)}"


def test_each_runout_carries_its_end_that_far_along_the_leg(sawhorse):
    low, high = _along_leg(sawhorse, _leg_template(sawhorse, 0, 0))
    wide_low, wide_high = _along_leg(sawhorse, _leg_template(sawhorse, 50, 0))
    narrow_low, narrow_high = _along_leg(sawhorse, _leg_template(sawhorse, 0, 50))
    assert (low - wide_low, wide_high - high) == pytest.approx((0.05, 0.0), abs=1e-4)
    assert narrow_low == pytest.approx(low, abs=1e-4)
    # The narrow end isn't square to the leg, so it moves up the leg a hair less than at its corner.
    assert narrow_high - high == pytest.approx(0.05, abs=1e-3)


def test_the_templates_are_shown_only_when_asked(sawhorse, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tool = sawhorse[1].tools[0]
    for show, count in ((True, 4), (False, 0)):
        kigumi = Kigumi()
        tool.call({"add_jigs_and_accessories": {"value": show}}, kigumi=kigumi)
        assert len(kigumi.extra_accessories) == count
    assert len(list((tmp_path / "kigumi_exports" / "dovetailed_sawhorse").glob("*.stl"))) == 4
