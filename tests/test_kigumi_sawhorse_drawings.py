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
def sawhorse():
    """Return the sawhorse's loaded viewer slot, including its generated drawings."""
    saved_modules = dict(sys.modules)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        slot = runner.load_slot_state(str(ROOT / "patterns" / "structures" / "dovetailed_sawhorse.py"))
        state = runner.RunnerState(slots={"main": slot}, active_slot="main")
        runner.build_real_geometry(state, slot)
    yield slot
    restore_modules(saved_modules)


@pytest.fixture(scope="module")
def drawings(sawhorse):
    """Return the sawhorse's serialized drawings."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return runner.collect_drawings(sawhorse.frame, None)


def _leg_top(drawings):
    legs = next(drawing for drawing in drawings if drawing["name"].startswith("leg"))
    return next(viewport for viewport in legs["viewports"] if viewport["name"] == "Leg top")


def test_a_plan_and_one_drawing_per_distinct_piece(drawings):
    assert len(drawings) == 3


def test_leg_trims_use_the_end_cut_intersection_group(sawhorse):
    from kumiki.csg.cutcsg import FeatureGroup
    from kumiki.csg.feature_paths import find_feature

    for cut in sawhorse.frame.cut_timbers:
        if not cut.timber.ticket.path.startswith("leg"):
            continue
        for name in ("level_top", "level_bottom"):
            trim = find_feature(cut, [name, name], name)
            assert trim is not None
            assert trim.feature.group is FeatureGroup.END_CUT


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


@pytest.mark.parametrize("x", [-18, 0, 18], ids=["outside-left", "between-legs", "outside-right"])
@pytest.mark.parametrize("side,height,feature", [
    (1, 30, "rptw.front_right"), (-1, 30, "rptw.front_left"),
    (1, 26.25, "rptw.back_right"), (-1, 26.25, "rptw.back_left"),
])
def test_beam_edge_picks_highlight_the_segment_under_the_pointer(sawhorse, x, side, height, feature):
    import numpy as np

    edge_point = np.array([x, side, height]) * 0.0254
    surface = edge_point - np.array([0, side * 0.004, 0])
    look = np.array([0.25, -side, -1 if height == 30 else 1], dtype=float)
    look /= np.linalg.norm(look)
    payload = {"memberKey": "beam#0", "point": surface.tolist(), "space": "3d", "currentPath": [],
               "ctrlClick": False, "look": look.tolist(), "tolerances": {"edge": 0.005, "point": 0.008},
               "ray": {"origin": (surface - 2 * look).tolist(), "direction": look.tolist()}}

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        reply = runner._handle_find_csg_at_point(None, payload, sawhorse)

    assert reply["featureType"] == "EDGE"
    assert reply["featureLabel"] == feature
    segments = reply.get("highlightEdgeSegments") or []
    assert any(min(segment["start"][0], segment["end"][0]) - 1e-8 <= edge_point[0]
               <= max(segment["start"][0], segment["end"][0]) + 1e-8 for segment in segments)


@pytest.mark.parametrize("feature", ["rptw.front_right", "rptw.front_left"])
def test_beam_top_edges_have_three_highlight_segments_and_skip_the_sockets(sawhorse, feature):
    from kumiki.csg.feature_paths import find_feature
    from kumiki.viewer.picking import edge_highlight_segments

    entry = sawhorse.mesh_cache["beam#0"]
    cut, root = entry["cut_timber"], entry["local_csg"]
    handle = find_feature(cut, ["timber (rough, extended)"], feature)
    assert handle is not None
    segments, absent = edge_highlight_segments(handle.feature, handle.owner, cut.timber, root)

    assert not absent and segments is not None
    assert len(segments) == 3
    for socket in (-11 * 0.0254, 11 * 0.0254):
        assert not any(min(segment["start"][0], segment["end"][0]) < socket
                       < max(segment["start"][0], segment["end"][0]) for segment in segments)
