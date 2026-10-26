"""The dovetailed sawhorse's generated drawings, as the viewer gets them, including the legs' extra view."""

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest
from tests.module_isolation import restore_modules

ROOT = Path(__file__).resolve().parent.parent


def _load_runner():
    spec = importlib.util.spec_from_file_location("kigumi_runner_sawhorse", ROOT / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_sawhorse"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


@pytest.fixture(scope="module")
def drawings():
    """The sawhorse's drawings, loaded once (see test_kigumi_generated_drawings for why once per file)."""
    saved_modules = dict(sys.modules)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        slot = runner.load_slot_state(str(ROOT / "patterns" / "structures" / "dovetailed_sawhorse.py"))
        state = runner.RunnerState(slots={"main": slot}, active_slot="main")
        runner.build_real_geometry(state, slot)
        found = runner.collect_drawings(slot.frame, None)
    yield found
    restore_modules(saved_modules)


def _leg_top(drawings):
    legs = next(drawing for drawing in drawings if drawing["name"].startswith("leg"))
    return next(viewport for viewport in legs["viewports"] if viewport["name"] == "Leg top")


def test_a_plan_and_one_drawing_per_distinct_piece(drawings):
    assert len(drawings) == 3


def test_the_legs_drawing_looks_straight_down_on_a_leg_top(drawings):
    camera = _leg_top(drawings)["camera"]

    assert camera["look"] == [0.0, 0.0, -1.0]
    assert camera["right"] == [1.0, 0.0, 0.0]


def test_the_leg_top_view_dimensions_a_dovetail_angle(drawings):
    kinds = [measure["kind"]["operation"] for measure in _leg_top(drawings)["measurements"]]

    assert "angle" in kinds


def test_every_generated_measurement_resolves(drawings):
    for drawing in drawings:
        for viewport in drawing["viewports"]:
            for measure in viewport.get("measurements", []):
                assert not measure.get("unresolved"), (drawing["name"], viewport["name"], measure)


def _names(measure):
    """Return the feature names a measurement's two ends name, derived edges by both faces."""
    def of(end):
        return [end.get("feature")] if "feature" in end else [end["a"]["feature"], end["b"]["feature"]]
    return of(measure["a"]) + of(measure["b"])


def test_the_beam_s_dovetail_sockets_are_dimensioned(drawings):
    beam = next(drawing for drawing in drawings if drawing["name"].startswith("beam"))
    named = {name for viewport in beam["viewports"] for measure in viewport.get("measurements", [])
             for name in _names(measure)}

    assert {"dovetail_left_flank", "dovetail_right_flank"} <= named


def test_both_flanks_are_angled_on_the_leg_top(drawings):
    angled = {name for measure in _leg_top(drawings)["measurements"] if measure["kind"]["operation"] == "angle"
              for name in _names(measure)}

    assert {"dovetail_left_flank", "dovetail_right_flank"} <= angled
