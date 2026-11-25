"""The runner describing one timber for an agent: its faces, its joints, and the features they name."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("kigumi_runner_describe", ROOT / "kigumi" / "runner.py")


@pytest.fixture(scope="module")
def frame():
    return _load("cute_frame_for_describe", ROOT / "patterns" / "structures" / "my_cute_frame.py").my_cute_frame()


def test_a_timber_lists_its_faces_and_each_joint_s_named_features(frame):
    described = runner.describe_timber(frame, "Left Side")

    assert described["faces"]["front"] == "rptw.front"
    assert described["joints"] and all("Left Side" in joint["timbers"] for joint in described["joints"])
    features = [feature for joint in described["joints"] for feature in joint["features"]]
    assert {"name": "shoulder", "type": "FACE", "on": "Back Cross",
            "constant": "MortiseAndTenonFeatures.SHOULDER"} in features
    assert not any(feature["name"].startswith("arris.") for feature in features), "numbered names are left out"


def test_an_unknown_timber_lists_the_timbers_there_are(frame):
    with pytest.raises(ValueError, match="The timbers are: Back Cross, Front Cross, Left Side, Right Side"):
        runner.describe_timber(frame, "Nope")
