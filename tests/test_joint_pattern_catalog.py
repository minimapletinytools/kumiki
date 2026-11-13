"""Check the public joint recipes and their discoverable pattern catalog."""

import ast
import importlib.util
from pathlib import Path

import pytest

from kumiki.frame_decorators import module_patterns
from kumiki.joints.workshop import basic_joints

ROOT = Path(__file__).resolve().parents[1]
JOINTS = ROOT / "kumiki/joints/workshop"
PATTERNS = ROOT / "patterns"
CATEGORIES = {"board", "butt", "corner", "cross", "decorative", "free", "mixed", "splice"}


def test_implemented_joint_functions_have_basic_entries():
    for source in JOINTS.rglob("*.py"):
        if "shavings" in source.parts or source.name == "basic_joints.py":
            continue
        for node in ast.parse(source.read_text()).body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("cut_"):
                continue
            if node.name == "cut_practice_board_in_dado_joint_on_plane_aligned_timbers":
                continue
            assert callable(getattr(basic_joints, node.name.replace("cut_", "cut_basic_", 1), None)), node.name


def test_basic_recipes_have_source_examples():
    calls = set()
    for source in PATTERNS.glob("basic*_patterns.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)
    for node in ast.parse((JOINTS / "basic_joints.py").read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("cut_basic_"):
            if "Compatibility alias" not in (ast.get_docstring(node) or ""):
                assert node.name in calls, node.name


SOURCES = sorted(source for source in PATTERNS.rglob("*.py")
                 if source.parent.name in CATEGORIES or source.name.startswith("basic"))


@pytest.mark.parametrize("source", SOURCES, ids=lambda p: str(p.relative_to(PATTERNS)))
def test_joint_pattern_file_builds_leaf_variants(source):
    spec = importlib.util.spec_from_file_location("catalog_" + source.stem, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patterns, rejected = module_patterns(module)
    assert not rejected
    paths = [pattern.path for pattern in patterns]
    assert len(paths) == len(set(paths))
    for pattern in patterns:
        assert not any(path.startswith(pattern.path + "/") for path in paths)
        frame = pattern.raise_at()
        assert frame.cut_timbers
