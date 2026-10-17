"""kigumi's runner: one slot's load must not leave another slot holding replaced classes.

Loading a file purges and re-imports the project's modules (kumiki, in a dev checkout) so
edits take effect. A slot built before a purge holds objects of the replaced classes, and new
code fails on them -- a pick in one view broke for good once another view was opened.
"""

import importlib.util
import sys
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SAWHORSE = REPO / "patterns" / "structures" / "dovetailed_sawhorse.py"
DOVETAILS = REPO / "patterns" / "free" / "free_dovetail_joint_patterns.py"


@pytest.fixture
def runner(monkeypatch):
    # These purge kumiki for real; the rest of the session keeps the modules it imported.
    saved_modules = dict(sys.modules)
    spec = importlib.util.spec_from_file_location("kigumi_runner_reload", REPO / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_reload"] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_project_root", REPO)
    yield module
    sys.modules.clear()
    sys.modules.update(saved_modules)


def _pick(runner, state, slot):
    key = next(k for k in slot.mesh_cache if k.startswith("beam"))
    return runner._handle_find_csg_at_point(state, {
        "memberKey": key, "point": [0.29729, 0.0127, 0.762], "currentPath": [], "ctrlClick": False,
    }, slot)


@pytest.fixture
def sawhorse(runner):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        slot = runner.load_slot_state(str(SAWHORSE))
        state = runner.RunnerState(slots={"main": slot}, active_slot="main")
        runner.build_real_geometry(state, slot)
    return state, slot


def test_loading_another_file_with_nothing_changed_keeps_the_modules(runner, sawhorse):
    state, slot = sawhorse
    generation = runner._project_generation
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        runner.load_slot_state(str(DOVETAILS))

        assert runner._project_generation == generation
        assert runner._resolve_slot(state, {"slot": "main"}) is slot
        assert _pick(runner, state, slot)["featureLabel"]


def test_after_a_module_changes_another_slot_is_rebuilt_before_its_next_use(runner, sawhorse):
    state, slot = sawhorse
    # As though geometry.py were saved after it was imported.
    runner._project_module_loaded_at["kumiki.geometry"] = 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        runner.load_slot_state(str(DOVETAILS))
        assert slot.generation != runner._project_generation

        rebuilt = runner._resolve_slot(state, {"slot": "main"})

        assert rebuilt is not slot and rebuilt.generation == runner._project_generation
        assert _pick(runner, state, rebuilt)["featureLabel"]


def test_a_rebuilt_slot_keeps_its_parameter_values(runner, sawhorse):
    state, slot = sawhorse
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        group = slot.kiwari_groups[0]
        state.slots["main"] = slot = runner.load_slot_state(
            str(SAWHORSE), kiwari_values={group.id: {"sawhorse_height": 0.7}}, previous_groups=slot.kiwari_groups)
        runner._project_module_loaded_at["kumiki.geometry"] = 0.0
        runner.load_slot_state(str(DOVETAILS))

        rebuilt = runner._resolve_slot(state, {"slot": "main"})

        assert rebuilt.kiwari_groups[0].kiwari.length("sawhorse_height") == pytest.approx(0.7)
