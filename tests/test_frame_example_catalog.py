"""Check public and hidden example discovery and the multi-frame scene's parameter groups."""

import importlib.util
import json
import warnings
from dataclasses import replace
from pathlib import Path

import pytest

from kumiki import Frame, mm
from kumiki.frame_decorators import module_entries

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "patterns" / "structures"
HIDDEN = ROOT / "hidden_structures"
FRAME_FILES = sorted([
    *EXAMPLES.glob("*.py"),
    *(path for path in HIDDEN.rglob("*.py") if path.name != "relief_example_patterns.py"),
])


@pytest.mark.parametrize("path", FRAME_FILES, ids=lambda p: p.stem)
def test_examples_have_explicit_buildable_entries_without_warnings(path):
    spec = importlib.util.spec_from_file_location("example_catalog_" + path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = module_entries(module)
    assert not entries.rejected
    assert entries.frames
    for entry in entries.frames:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            frame = entry.function()
        assert isinstance(frame, Frame)
        assert frame.cut_timbers


def test_packaged_catalog_promotes_multiple_frames_and_excludes_development_examples():
    index = json.loads((ROOT / "kumiki" / "_pattern_index.json").read_text())
    paths = index["entries"]
    assert "patterns/structures/multiple_frames.py" in paths
    assert not any("onlypoop" in path or "hidden_structures" in path for path in paths)
    entry = paths["patterns/structures/multiple_frames.py"]
    assert len(entry["frames"]) == 4


@pytest.mark.parametrize("pairs,rise", [(3, mm(500)), (5, mm(900)), (9, mm(1500))])
def test_pavilion_roof_controls_change_members_and_ridge_height(pairs, rise):
    from patterns.structures.multiple_frames import PAVILION, pavilion

    frame = pavilion(replace(PAVILION, values={"rafter_pairs": pairs, "roof_rise": rise}))
    rafters = [cut for cut in frame.cut_timbers if "_rafter_" in cut.timber.ticket.path]
    assert len(rafters) == 2 * pairs
    ridge = next(cut.timber for cut in frame.cut_timbers if cut.timber.ticket.path == "roof/ridge")
    assert float(ridge.get_bottom_position_global()[2]) == pytest.approx(2.2 + float(rise))
    assert len(frame.cut_timbers) == 11 + 2 * pairs


def test_scene_shares_model_parameters_and_keeps_pavilion_parameters_separate():
    from patterns.structures.multiple_frames import MODELS, cottage, tower, shed, pavilion

    models = [build() for build in (cottage, tower, shed)]
    assert all(frame.kiwari is not None and frame.kiwari.origin is MODELS for frame in models)
    structure = pavilion()
    assert structure.kiwari is not None and structure.kiwari.origin is not MODELS
