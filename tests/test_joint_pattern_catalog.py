"""Check the public joint recipes and their discoverable pattern catalog."""

import ast
import importlib.util
from pathlib import Path

import pytest

from kumiki.frame_decorators import module_patterns

ROOT = Path(__file__).resolve().parents[1]
JOINTS = ROOT / "kumiki/joints/workshop"
PATTERNS = ROOT / "patterns"
CATEGORIES = {"board", "butt", "corner", "cross", "decorative", "free", "mixed", "splice"}


def test_basic_recipes_have_source_examples():
    calls = set()
    for source in PATTERNS.glob("basic*_patterns.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)
    for node in ast.parse((JOINTS / "basic_joints.py").read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("cut_basic_"):
            if node.name == "cut_basic_practice_board_in_dado_joint_on_plane_aligned_timbers":
                continue
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


def test_multi_cross_lap_controls_move_material_between_three_members():
    from dataclasses import replace
    from kumiki import CutTimber, create_v3, inches
    from patterns.cross.multi_cross_lap_joint_patterns import CHAIN, multi_cross_lap

    for values, expected in [({}, ["first", "middle", "last"]),
                             ({"first_boundary": 0.2, "second_boundary": 0.8},
                              ["middle", "middle", "middle"])]:
        joint = multi_cross_lap(replace(CHAIN, values=values))
        timbers = {cut.timber.ticket.path: cut.timber for cut in joint.cuttings.values()}
        assert len(timbers) == 3
        bodies = {
            name: CutTimber(timber, cuts=[cut for cut in joint.cuttings.values()
                                         if cut.timber is timber]).render_timber_with_cuts_csg_local()
            for name, timber in timbers.items()
        }
        for height, owner in zip([1.5, 3, 4.5], expected):
            point = create_v3(0, inches(1.5), inches(height))
            occupants = [name for name, timber in timbers.items()
                         if bodies[name].contains_point(timber.transform.global_to_local(point))]
            assert occupants == [owner]


@pytest.mark.parametrize("notched,round_stock,pegged", [
    (False, False, True), (True, False, False), (True, True, True),
])
def test_compound_pattern_relief_and_peg_controls(notched, round_stock, pegged):
    from dataclasses import replace
    from kumiki import PegShape
    from patterns.mixed.mortise_and_tenon_joints_patterns import (
        ANGLED_TENON, example_double_angled_mortise_and_tenon,
    )

    joint = example_double_angled_mortise_and_tenon(replace(ANGLED_TENON, values={
        "notched": notched, "round_timbers": round_stock,
        "pegged": pegged, "peg_shape": PegShape.ROUND,
    }))
    assert len(joint.cuttings) == 2
    assert bool(joint.jointAccessories) == pegged


@pytest.mark.parametrize("top_entry", [False, True])
def test_tusked_pattern_accepts_rough_reference_and_inset(top_entry):
    from dataclasses import replace
    from kumiki import MeasureOppositeShoulderFrom, inches
    from patterns.mixed.mortise_and_tenon_joints_patterns import TUSKED, tusked_front, tusked_top

    build = tusked_top if top_entry else tusked_front
    joint = build(replace(TUSKED, values={
        "rough_stock": True, "measure_from": MeasureOppositeShoulderFrom.Rough,
        "opposite_inset": inches(1),
    }))
    assert len(joint.cuttings) == 2
    assert joint.jointAccessories
