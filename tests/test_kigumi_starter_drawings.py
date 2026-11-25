"""The starter frame's hand-placed drawings, as the viewer gets them: every dimension resolves, placed."""

import importlib.util
import sys
from pathlib import Path

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
    runner = _runner()
    slot = runner.load_slot_state(str(STARTER))
    values = {}
    for drawing in runner.collect_drawings(slot.frame, STARTER):
        for viewport in drawing["viewports"]:
            for measure in viewport.get("measurements", []):
                assert not measure.get("unresolved"), (drawing["name"], measure)
                assert measure["settled"]["reason"] is None, (drawing["name"], measure["a"], measure["b"])
                assert (measure.get("placement") or {}).get("offset") is not None, "placed"
                values.setdefault(drawing["name"], []).append(round(measure["settled"]["value"]["value"] * 1000, 1))

    assert sorted(values["Plan"]) == [55.0, 310.0, 410.0, 590.0, 600.0]
    assert sorted(values["Left Side ×2"]) == [40.0, 60.0, 80.0, 100.0, 460.0, 500.0]
    assert sorted(values["Back Cross ×2"]) == [35.5, 40.0, 75.0, 80.0, 410.0]
