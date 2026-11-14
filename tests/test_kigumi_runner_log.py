"""kigumi's runner keeps its log short: one line for a warning a file repeats, or a failure many timbers share."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location("kigumi_runner_log", REPO / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_log"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("kigumi_runner_log", None)


def test_the_deprecated_frame_name_is_warned_about_once_per_file(runner, capsys):
    for _ in range(3):
        runner._warn_legacy_entry("build_frame", "/p/frame.py")
    runner._warn_legacy_entry("build_frame", "/p/other.py")

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    assert all(line.startswith("[warn] picking up the frame by the name 'build_frame'") for line in lines)


class _Unmeshable:
    def __init__(self, name):
        self.timber = SimpleNamespace(ticket=SimpleNamespace(path=name, name=name), name=name)

    def render_timber_with_cuts_csg_local(self):
        raise ModuleNotFoundError("No module named 'kumiki.viewer'")


def test_timbers_that_fail_the_same_way_share_one_error(runner, capsys):
    frame = SimpleNamespace(cut_timbers=[_Unmeshable(f"board_{i}") for i in range(7)], accessories=[], footprints=[])
    slot = SimpleNamespace(frame=frame, mesh_cache={})

    runner.build_real_geometry(SimpleNamespace(_active=slot), slot)

    errors = [line for line in capsys.readouterr().err.splitlines() if line.startswith("[error]")]
    assert errors == ["[error] skipping geometry for 7 timbers (board_0, board_1, board_2, board_3, board_4 "
                      "and 2 more): No module named 'kumiki.viewer'"]
