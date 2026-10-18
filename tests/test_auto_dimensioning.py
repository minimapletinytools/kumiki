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
def pattern():
    with contextlib.redirect_stdout(io.StringIO()):
        return runpy.run_path(str(PATTERN))


@pytest.fixture(scope="module")
def solve(pattern):
    return pattern["solve_cute_frame"]


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


class TestTheGround:

    def test_the_fixed_timber_gives_where_it_is_and_not_how_big_so_both_views_dimension_something(self, solve):
        # Lined-up features only tie each other: something still has to say how far apart a line-up
        # is from the rest, and the fixed timber's own sizes are not given.
        _, result, _ = solve()

        assert {pick.candidate.view for pick in result.picks} == {"top", "front"}


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


class TestEachTimber:
    """A shop drawing per timber, solving every required feature from its reference faces and end."""

    def test_everything_but_the_bore_radii_and_blind_mortise_bottoms_is_dimensioned(self, pattern):
        # A bore's radius would need a diameter dimension, which no measurement kind takes yet. A
        # blind mortise's bottom is hidden in every view that draws it as a line, and a view measures
        # only what it can see; an x-ray view will let it be dimensioned.
        from kumiki.csg.cutcsg import SimpleCylinderBarrelFeature
        from kumiki.drawings.auto_dimensioning import UnsolvedFeaturesWarning

        frame = pattern["_load_cute_frame"]()()
        for cut in frame.cut_timbers:
            with pytest.warns(UnsolvedFeaturesWarning):
                result, _ = pattern["solve_timber"](cut)
            assert result.unsolved, cut.timber.ticket.path
            assert all(isinstance(h.feature, SimpleCylinderBarrelFeature) or h.feature.name == "mortise_bottom"
                       for h in result.unsolved)
            # Two mortise bottoms in one plane are one unknown between them.
            assert 0 < result.left_after <= len(result.unsolved)

    def test_a_peg_axis_is_dimensioned_seen_end_on(self, pattern):
        frame = pattern["_load_cute_frame"]()()
        result, _ = pattern["solve_timber"](frame.cut_timbers[0])
        ends = [end.feature.name for pick in result.picks
                for end in (pick.candidate.measure.anchor_a, pick.candidate.measure.anchor_b)]
        assert "peg_hole_axis" in ends

    def test_the_frame_has_a_drawing_per_timber_and_the_plan(self, pattern):
        frame = pattern["build_frame_with_drawing"]()
        names = [drawing.name for drawing in frame.drawings]
        assert "Cute frame plan (generated)" in names
        for cut in frame.cut_timbers:
            assert f"{cut.timber.ticket.path} (generated)" in names
