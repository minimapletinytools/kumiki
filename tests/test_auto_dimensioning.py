"""Auto dimensioning on the cute frame: what a policy prefers, and what a rule does."""

import contextlib
import io
import runpy
from pathlib import Path as FilePath

import pytest

from kumiki import *
from kumiki.csg.cutcsg import OwnedFeatureHit
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.drawings.auto_dimensioning import (Policy, from_reference, from_solved, is_reference, shortest)

PATTERN = FilePath(__file__).resolve().parent.parent / "patterns" / "structures" / "my_cute_frame_drawing_test.py"


@pytest.fixture(scope="module")
def solve():
    with contextlib.redirect_stdout(io.StringIO()):
        return runpy.run_path(str(PATTERN))["solve_cute_frame"]


def _from_a_reference(pick) -> bool:
    measure = pick.candidate.measure
    return is_reference(measure.anchor_a) or is_reference(measure.anchor_b)


class TestIsReference:

    def _handle(self, name, reference_features):
        timber = create_timber(bottom_position=create_v3(0, 0, 0), length=m(1), size=create_v2(mm(90), mm(90)),
                               length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0),
                               ticket=TimberTicket("beam", reference_features=reference_features))
        body = timber.get_perfect_timber_within_csg_local()
        feature = next(f for f in body.get_declared_features() if f.name == name)
        return FeatureHandle(timber=timber, hit=OwnedFeatureHit(feature=feature, owner=body))

    def test_both_faces_of_a_reference_edge(self):
        assert is_reference(self._handle("ptw.left", (TimberFeature.LEFT_BACK_EDGE,)))
        assert is_reference(self._handle("ptw.back", (TimberFeature.LEFT_BACK_EDGE,)))
        assert not is_reference(self._handle("ptw.front", (TimberFeature.LEFT_BACK_EDGE,)))

    def test_a_reference_face_however_prefixed(self):
        assert is_reference(self._handle("ptw.front", (TimberFeature.FRONT_FACE,)))

    def test_a_reference_centerplane(self):
        assert is_reference(self._handle("ptw.centerplane_front_back", (TimberFeature.FRONT_BACK_CENTER_PLANE,)))
        assert not is_reference(self._handle("ptw.centerplane_left_right", (TimberFeature.FRONT_BACK_CENTER_PLANE,)))


class TestPolicy:

    def test_by_default_every_dimension_is_from_a_reference_and_all_is_solved(self, solve):
        _, result, _ = solve()

        assert result.left_after == 0 and not result.unsolved
        assert all(_from_a_reference(pick) for pick in result.picks)

    def test_without_the_preference_one_is_not(self, solve):
        # The old rule: chain from what is solved, then shortest. A shoulder to shoulder is picked.
        _, result, _ = solve(Policy(prefer=(from_solved, shortest)))

        assert result.left_after == 0
        assert not all(_from_a_reference(pick) for pick in result.picks)

    def test_a_rule_is_kept_where_it_can_be(self, solve):
        _, result, _ = solve(Policy(prefer=(from_solved, shortest), rules=(from_reference,)))

        assert result.left_after == 0
        assert all(_from_a_reference(pick) and not pick.broke_rules for pick in result.picks)

    def test_a_rule_nothing_passes_is_set_aside_rather_than_getting_stuck(self, solve):
        _, result, _ = solve(Policy(rules=(lambda candidate, context: 1.0,)))

        assert result.left_after == 0
        assert result.picks and all(pick.broke_rules for pick in result.picks)
