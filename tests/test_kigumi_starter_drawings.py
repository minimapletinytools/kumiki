"""The starter frame's hand-placed drawings, as the viewer gets them: every dimension resolves, placed."""

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

from tests.module_isolation import restore_modules

ROOT = Path(__file__).resolve().parent.parent
STARTER = ROOT / "patterns" / "structures" / "my_cute_frame.py"


def _runner():
    spec = importlib.util.spec_from_file_location("kigumi_runner_starter", ROOT / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_starter"] = module
    spec.loader.exec_module(module)
    return module


def test_the_starter_s_drawings_measure_what_its_dimensions_say():
    # Loading purges kumiki where it is installed from this checkout (as on CI); put it back after.
    saved_modules = dict(sys.modules)
    try:
        runner = _runner()
        with contextlib.redirect_stdout(io.StringIO()):
            slot = runner.load_slot_state(str(STARTER))
        drawings = runner.collect_drawings(slot.frame, STARTER)
    finally:
        restore_modules(saved_modules)
    values = {}
    for drawing in drawings:
        for viewport in drawing["viewports"]:
            for measure in viewport.get("measurements", []):
                assert not measure.get("unresolved"), (drawing["name"], measure)
                assert measure["settled"]["reason"] is None, (drawing["name"], measure["a"], measure["b"])
                assert (measure.get("placement") or {}).get("offset") is not None, "placed"
                values.setdefault(drawing["name"], []).append(round(measure["settled"]["value"]["value"] * 1000, 1))

    assert sorted(values["Plan"]) == [55.0, 310.0, 410.0, 590.0, 600.0]
    assert sorted(values["Left Side ×2"]) == [40.0, 60.0, 80.0, 100.0, 460.0, 500.0]
    assert sorted(values["Back Cross ×2"]) == [35.5, 40.0, 75.0, 80.0, 410.0]
