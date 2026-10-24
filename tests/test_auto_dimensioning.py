"""Auto dimensioning on the cute frame: what a policy prefers, and what a rule does."""

import contextlib
import io
import runpy
import warnings
from pathlib import Path as FilePath
from typing import List

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
    # The picks as the policy made them, before faces are moved onto edges.
    return lambda *args: pattern["solve_cute_frame"](*args, onto_edges=False)


def _from_a_reference(pick) -> bool:
    measure = pick.candidate.measure
    return is_reference(measure.anchor_a) or is_reference(measure.anchor_b)


def _names(pick) -> List[str]:
    measure = pick.candidate.measure
    return sorted((measure.anchor_a.feature.name, measure.anchor_b.feature.name))


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

    def test_by_default_every_dimension_is_from_a_reference_or_a_shoulder_and_all_is_solved(self, solve):
        _, result, _ = solve()

        assert result.left_after == 0 and not result.unsolved
        assert all(_from_a_reference(pick) or _names(pick) == ["shoulder", "shoulder"] for pick in result.picks)

    def test_a_cross_is_measured_shoulder_to_shoulder(self, solve):
        _, result, _ = solve()

        assert any(_names(pick) == ["shoulder", "shoulder"] and pick.candidate.measure.anchor_a.timber
                   is pick.candidate.measure.anchor_b.timber for pick in result.picks)

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

    def test_the_frame_has_the_plan_and_a_drawing_per_distinct_piece(self, pattern):
        frame = pattern["build_frame_with_drawing"]()
        names = [drawing.name for drawing in frame.drawings]
        ids = [str(drawing.drawing_id) for drawing in frame.drawings]
        assert "Cute frame plan (generated)" in names
        # The crosses are one piece turned, and so are the sides: one drawing each, of two.
        assert "Back Cross ×2 (generated)" in names and "Left Side ×2 (generated)" in names
        assert "Back Cross (generated)" in ids and "Left Side (generated)" in ids
        assert len(frame.drawings) == 3


class TestPreferredMeasurements:
    """Features marked relative to another (a tenon's cheeks, its tip and shoulder, a mortise's walls) are
    measured against it; a tenon's tip from nothing else."""

    @pytest.fixture(scope="class")
    def picks(self, pattern):
        frame = pattern["_load_cute_frame"]()()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return {cut.timber.ticket.path: pattern["solve_timber"](cut, onto_edges=False)[0].picks
                    for cut in frame.cut_timbers}

    def test_a_tenon_is_measured_cheek_to_cheek_both_ways(self, picks):
        names = [_names(pick) for pick in picks["Back Cross"]]
        assert ["tenon_left", "tenon_right"] in names and ["tenon_back", "tenon_front"] in names

    def test_each_tenon_s_length_is_from_its_own_shoulder(self, picks):
        lengths = [pick.candidate.length for pick in picks["Back Cross"]
                   if _names(pick) in (["shoulder", "tenon_top"], ["shoulder", "tenon_bot"])]
        assert lengths and all(length == pytest.approx(lengths[0]) for length in lengths)
        assert lengths[0] < 0.1

    def test_a_tenon_s_tip_is_measured_from_nothing_but_its_shoulder(self, picks):
        for pick in picks["Back Cross"]:
            names = _names(pick)
            if "tenon_top" in names or "tenon_bot" in names:
                assert "shoulder" in names, names

    def test_a_mortise_is_measured_wall_to_wall(self, picks):
        names = [_names(pick) for pick in picks["Left Side"]]
        assert ["mortise_back", "mortise_front"] in names or ["mortise_left", "mortise_right"] in names


class TestDerivedEdges:
    """Edges where a slanted face meets the timber's faces are offered to dimension to: such a face draws
    with no point or parallel line of its own."""

    def _bevelled(self):
        from kumiki.csg.cutcsg import HALF_SPACE_PLANE, CutCSGLabel, FeatureGroup, HalfSpace, shoulder_override

        timber = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(150)),
                               length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0),
                               ticket=TimberTicket("post", reference_features=(TimberFeature.LEFT_BACK_EDGE,)))
        bevel = HalfSpace(normal=safe_normalize_vector(create_v3(1, 0, 1)), offset=mm(1020) / sqrt(2),
                          label=CutCSGLabel("bevel"),
                          feature_overrides=[shoulder_override(HALF_SPACE_PLANE, "shoulder", FeatureGroup.SHOULDER_PLANE)])
        return CutTimber(timber, cuts=[Cutting(timber=timber, negative_csg=bevel)])

    def _edges(self, pattern, cut, handles):
        from kumiki.drawings.auto_dimensioning import derived_edge_anchors

        views = {view: axes for view, (axes, _) in pattern["_shop_sheets"](cut.timber).items()}
        return derived_edge_anchors(cut, handles, views)

    def test_a_sloped_shoulder_meets_the_timber_s_faces(self, pattern):
        from kumiki.csg.required_features import required_features

        cut = self._bevelled()
        names = {edge.feature.name for edge in self._edges(pattern, cut, [r.handle for r in required_features(cut)])}
        assert {"shoulder×rptw.front", "shoulder×rptw.back"} <= names
        assert all(name.startswith("shoulder×") for name in names)

    def test_none_is_a_reference_though_named_after_one(self, pattern):
        from kumiki.csg.required_features import required_features

        cut = self._bevelled()
        handles = [r.handle for r in required_features(cut)]
        assert any(is_reference(h) and h.feature.name == "rptw.back" for h in handles)
        edges = self._edges(pattern, cut, handles)
        assert any(edge.feature.name == "shoulder×rptw.back" for edge in edges)
        assert not any(is_reference(edge) for edge in edges)

    def test_faces_no_view_draws_slanted_give_none(self, pattern):
        from kumiki.csg.required_features import required_features

        frame = pattern["_load_cute_frame"]()()
        cut = next(c for c in frame.cut_timbers if c.timber.ticket.path == "Back Cross")
        assert self._edges(pattern, cut, [r.handle for r in required_features(cut)]) == []

    def test_a_sloped_shoulder_is_set_out_by_an_angle_from_the_timber(self, pattern):
        from kumiki.drawings.measure import MeasurementOperation

        result, _ = pattern["solve_timber"](self._bevelled())
        first = result.picks[0].candidate.measure
        assert first.kind.operation is MeasurementOperation.ANGLE
        names = {first.anchor_a.feature.name, first.anchor_b.feature.name}
        # The shoulder by one of its edges, from one of the timber's faces.
        assert any(name.startswith("shoulder×") for name in names)
        assert any(name.startswith("rptw.") for name in names)
        assert not result.unsolved
