"""The cute frame's generated drawings, as the viewer gets them: every measurement drawable.

Covers the runner placing a bore's axis (a non-real line, in the bore where there is no timber) and
a tenon's end face (flush with the end of the piece, on the timber's own boundary).
"""

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_runner():
    spec = importlib.util.spec_from_file_location("kigumi_runner_generated", ROOT / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_generated"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


@pytest.fixture(scope="module")
def loaded():
    """The cute frame, loaded once: loading purges kumiki where it is installed from this checkout
    (as on CI), and the rest of the session keeps the modules it imported (see
    test_kigumi_slot_reload) -- once per file, since a second purge would re-import numpy's C
    extensions, which cannot be loaded twice."""
    saved_modules = dict(sys.modules)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        slot = runner.load_slot_state(str(ROOT / "patterns" / "structures" / "my_cute_frame_drawing_test.py"))
        state = runner.RunnerState(slots={"main": slot}, active_slot="main")
        runner.build_real_geometry(state, slot)
    yield slot, state
    sys.modules.clear()
    sys.modules.update(saved_modules)


def test_every_generated_measurement_resolves_and_settles(loaded):
    slot, _ = loaded
    drawings = runner.collect_drawings(slot.frame, None)
    assert len(drawings) == 5
    for drawing in drawings:
        measures = [measure for viewport in drawing["viewports"] for measure in viewport.get("measurements", [])]
        assert measures, drawing["name"]
        for measure in measures:
            assert not measure.get("unresolved"), (drawing["name"], measure)
            assert measure["settled"]["reason"] is None, (drawing["name"], measure["a"], measure["b"])


def test_a_perfect_reference_is_cropped_to_the_cut_timber(loaded):
    # Back Cross is tenoned at both ends, its shoulders 45 mm in from each end of its 500 mm. Its
    # perfect faces are inside the rough stock, so they end at the shoulders; a centerplane runs on
    # through the middle of each tenon.
    slot, state = loaded
    key = next(k for k in slot.mesh_cache if k.startswith("Back Cross"))
    transform = slot.mesh_cache[key]["cut_timber"].timber.transform
    from kumiki.rule import create_v3

    def along(name):
        result = runner._handle_find_csg_by_path(
            state, {"memberKey": key, "path": ["timber (rough, extended)"], "featureLabel": name}, slot)
        ends = [float(transform.global_to_local(create_v3(*end))[2])
                for segment in result["highlightEdgeSegments"] for end in (segment["start"], segment["end"])]
        return min(ends), max(ends)

    low, high = along("ptw.right")
    assert (round(low, 4), round(high, 4)) == (0.045, 0.455)
    # And a dimension to it attaches at the middle of what is left of it.
    root = slot.mesh_cache[key]["local_csg"]
    body = root.base
    right = next(f for f in body.get_declared_features() if f.name == "ptw.right")
    at = runner._feature_anchor(right, body, slot.mesh_cache[key]["cut_timber"].timber,
                                right.locate_simple_unbounded(body), root)
    assert round(float(transform.global_to_local(create_v3(*at))[2]), 4) == 0.25
    low, high = along("ptw.centerplane_left_right")
    assert low < 0 and high > 0.5
