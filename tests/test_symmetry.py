"""csg/symmetry.py: which cut timbers are the same piece, turned, or mirrored."""

import importlib.util
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from kumiki.csg.cutcsg import Difference, RectangularPrism
from kumiki.csg.symmetry import SymmetryKind, csg_symmetries, match_timbers, timber_symmetries
from kumiki.rule import Orientation, Transform, create_v2, create_v3

STRUCTURES = Path(__file__).resolve().parent.parent / "patterns" / "structures"


def _module(name):
    spec = importlib.util.spec_from_file_location(f"symmetry_test_{name}", STRUCTURES / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def coffee_table():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {cut.timber.ticket.path: cut for cut in _module("coffee_table").build_frame().cut_timbers}


@pytest.fixture(scope="module")
def cute_frame():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        frame = _module("my_cute_frame_drawing_test")._load_cute_frame()()
    return {cut.timber.ticket.path: cut for cut in frame.cut_timbers}


def _block(notch_x: float, notch_z: float) -> Difference:
    """A 0.1 x 0.06 x 1 block along z with a 0.02 cube notch off centre in y, so the block has no
    symmetry of its own: where the notch is says how two blocks relate."""
    body = RectangularPrism(size=create_v2(0.1, 0.06), transform=Transform.identity(), start_distance=0,
                            end_distance=1)
    notch = RectangularPrism(size=create_v2(0.02, 0.02),
                             transform=Transform(position=create_v3(notch_x, 0.01, notch_z),
                                                 orientation=Orientation.identity()),
                             start_distance=-0.01, end_distance=0.01)
    return Difference(body, [notch])


def test_the_same_tree_is_identical():
    found = csg_symmetries(_block(0.04, 0.2), _block(0.04, 0.2))
    assert [symmetry.kind for symmetry in found] == [SymmetryKind.IDENTICAL]
    assert np.allclose(found[0].shift, 0)


def test_a_notch_on_the_other_side_is_a_mirror_and_at_the_other_end_a_turn():
    mirrored = csg_symmetries(_block(0.04, 0.2), _block(-0.04, 0.2))
    assert [symmetry.description for symmetry in mirrored] == ["reflection (flip width)"]
    # The notch near the other end, on the other side: the block turned end for end about y.
    turned = csg_symmetries(_block(0.04, 0.2), _block(-0.04, 0.8))
    assert [symmetry.description for symmetry in turned] == ["rotation (flip width, flip length)"]
    assert np.allclose(turned[0].shift, [0, 0, 1])


def test_different_pieces_do_not_match():
    assert csg_symmetries(_block(0.04, 0.2), _block(0.04, 0.3)) == []


def test_the_coffee_tables_fourteen_timbers_are_six_pieces(coffee_table):
    groups = match_timbers(list(coffee_table.values()))
    assert len(groups) == 6
    assert Counter(match.kind for group in groups for match in group.matches) == Counter(
        {SymmetryKind.IDENTICAL: 3, SymmetryKind.ROTATION: 3, SymmetryKind.REFLECTION: 2})


def test_two_legs_are_only_mirror_images(coffee_table):
    kinds = {symmetry.kind for symmetry in timber_symmetries(coffee_table["southwest-leg"], coffee_table["southeast-leg"])}
    assert kinds == {SymmetryKind.REFLECTION}


def test_a_stretcher_the_same_at_both_ends_is_its_own_mirror(coffee_table):
    stretcher = coffee_table["south-top-stretcher"]
    descriptions = [symmetry.description for symmetry in timber_symmetries(stretcher, stretcher)]
    assert descriptions == ["identical", "reflection (flip length)"]


def test_the_cute_frames_crosses_are_one_turned_end_for_end(cute_frame):
    # The other cross's joints are at the opposite ends of its tree's list: matched in any order.
    found = timber_symmetries(cute_frame["Back Cross"], cute_frame["Front Cross"])
    assert SymmetryKind.ROTATION in {symmetry.kind for symmetry in found}
    groups = match_timbers(list(cute_frame.values()))
    assert len(groups) == 2
    assert {match.kind for group in groups for match in group.matches} == {SymmetryKind.ROTATION}


def test_what_the_geometry_does_not_settle_is_reported(cute_frame):
    groups = match_timbers(list(cute_frame.values()))
    differences = [difference for group in groups for match in group.matches for difference in match.differences]
    assert any(difference.startswith("reference features") for difference in differences)
