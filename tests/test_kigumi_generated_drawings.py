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


@pytest.fixture(autouse=True)
def _keep_modules():
    # Loading a file purges kumiki where it is installed from this checkout (as on CI); the rest
    # of the session keeps the modules it imported. See test_kigumi_slot_reload.
    saved_modules = dict(sys.modules)
    yield
    sys.modules.clear()
    sys.modules.update(saved_modules)


def test_every_generated_measurement_resolves_and_settles():
    with contextlib.redirect_stdout(io.StringIO()):
        slot = runner.load_slot_state(str(ROOT / "patterns" / "structures" / "my_cute_frame_drawing_test.py"))
    drawings = runner.collect_drawings(slot.frame, None)
    assert len(drawings) == 5
    for drawing in drawings:
        measures = [measure for viewport in drawing["viewports"] for measure in viewport.get("measurements", [])]
        assert measures, drawing["name"]
        for measure in measures:
            assert not measure.get("unresolved"), (drawing["name"], measure)
            assert measure["settled"]["reason"] is None, (drawing["name"], measure["a"], measure["b"])
