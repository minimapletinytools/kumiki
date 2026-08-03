"""Tests for decorative joints."""

import math

import pytest
from sympy import Matrix

from kumiki.joints.workshop.decorative_joints import (
    cut_practice_roundover_decoration,
    cut_practice_rafter_tail_scallop_decoration,
)
from kumiki.ticket import TimberTicket
from kumiki.rule import scalar, Transform
from kumiki.timber import Timber, TimberEdge, TimberEnd, TimberLongFace
from kumiki.cutcsg import Difference, Cylinder
from kumiki.triangles import triangulate_cutcsg

WIDTH = scalar(4)
HEIGHT = scalar(6)
LENGTH = scalar(12)
RADIUS = scalar(1)
# Cross-sectional area removed per unit length by a single edge's fillet: a
# radius x radius square minus a quarter circle of that radius.
SQUARE_MINUS_QUARTER_CIRCLE = float(RADIUS) ** 2 * (1 - math.pi / 4)


def _make_timber():
    return Timber(
        length=LENGTH,
        size=Matrix([WIDTH, HEIGHT]),
        transform=Transform.identity(),
        ticket=TimberTicket(path="timber"),
    )


def _removed_volume(edges, radius=RADIUS):
    """Cuts the roundover, triangulates the result, and returns (removed_volume, result_csg)."""
    timber = _make_timber()
    joint = cut_practice_roundover_decoration(timber, edges, radius)
    cutting = joint.cuttings["timber"]
    assert cutting.negative_csg is not None
    full_prism = timber.get_perfect_timber_within_csg_local()
    result_csg = Difference(base=full_prism, subtract=[cutting.negative_csg])
    mesh = triangulate_cutcsg(result_csg).mesh
    assert mesh.is_watertight
    original_volume = float(WIDTH) * float(HEIGHT) * float(LENGTH)
    return original_volume - mesh.volume, result_csg


class TestRoundoverDecoration:
    """Tests for cut_practice_roundover_decoration."""

    def test_joint_structure(self):
        timber = _make_timber()
        joint = cut_practice_roundover_decoration(timber, [TimberEdge.RIGHT_FRONT], RADIUS)

        assert joint.ticket.joint_type == "roundover_decoration"
        assert joint.is_decorative()
        assert set(joint.cuttings.keys()) == {"timber"}
        cutting = joint.cuttings["timber"]
        assert cutting.label == "roundover_decoration"
        assert cutting.negative_csg is not None

    def test_no_edges_is_a_no_op(self):
        timber = _make_timber()
        joint = cut_practice_roundover_decoration(timber, [], RADIUS)

        assert joint.cuttings["timber"].negative_csg is None

    def test_single_long_edge_removes_expected_volume(self):
        # Cylinder CSGs triangulate as a 32-sided polygon (not a true circle),
        # so allow a few percent of discretization error against the ideal
        # "square minus quarter circle" formula.
        removed, _ = _removed_volume([TimberEdge.RIGHT_FRONT])
        expected = SQUARE_MINUS_QUARTER_CIRCLE * float(LENGTH)
        assert removed == pytest.approx(expected, rel=0.03)

    def test_single_short_edge_removes_expected_volume(self):
        # BOTTOM_RIGHT runs along the HEIGHT axis (back to front).
        removed, _ = _removed_volume([TimberEdge.BOTTOM_RIGHT])
        expected = SQUARE_MINUS_QUARTER_CIRCLE * float(HEIGHT)
        assert removed == pytest.approx(expected, rel=0.03)

    def test_non_adjacent_edges_do_not_interact(self):
        # RIGHT_FRONT and LEFT_BACK share no corner, so their removed volumes
        # should simply add.
        removed, _ = _removed_volume([TimberEdge.RIGHT_FRONT, TimberEdge.LEFT_BACK])
        expected = 2 * SQUARE_MINUS_QUARTER_CIRCLE * float(LENGTH)
        assert removed == pytest.approx(expected, rel=0.03)

    def test_edges_sharing_a_corner_overlap_but_stay_watertight(self):
        # RIGHT_FRONT and BOTTOM_RIGHT share corner BOT_RIGHT_FRONT, so their
        # fillets overlap there. cut_practice_roundover_decoration doesn't
        # check for this (see its docstring), but the union must still merge
        # the overlap correctly rather than double-removing it.
        removed, _ = _removed_volume([TimberEdge.RIGHT_FRONT, TimberEdge.BOTTOM_RIGHT])
        naive_sum = SQUARE_MINUS_QUARTER_CIRCLE * (float(LENGTH) + float(HEIGHT))
        assert removed < naive_sum

    def test_all_edges_produce_a_watertight_result(self):
        removed, _ = _removed_volume(list(TimberEdge))
        assert removed > 0
        assert removed < float(WIDTH) * float(HEIGHT) * float(LENGTH)

    def test_rounds_off_the_sharp_corner_but_keeps_the_center(self):
        _, result_csg = _removed_volume([TimberEdge.RIGHT_FRONT])
        sharp_corner = Matrix([float(WIDTH) / 2, float(HEIGHT) / 2, float(LENGTH) / 2])
        center = Matrix([0.0, 0.0, float(LENGTH) / 2])
        face_tangent_point = Matrix([float(WIDTH) / 2, float(HEIGHT) / 2 - float(RADIUS), float(LENGTH) / 2])

        assert not result_csg.contains_point(sharp_corner)
        assert result_csg.contains_point(center)
        assert result_csg.contains_point(face_tangent_point)

    def test_radius_too_large_raises(self):
        timber = _make_timber()
        with pytest.raises(AssertionError, match="too large"):
            cut_practice_roundover_decoration(timber, [TimberEdge.RIGHT_FRONT], WIDTH)


class TestRafterTailScallopDecoration:
    """Tests for cut_practice_rafter_tail_scallop_decoration."""

    def test_scallop_cut_is_watertight_and_removes_expected_material(self):
        # end_side=TOP, cut_side=BACK: scallop cut into the BACK face near the
        # TOP end, extruded across the full WIDTH (the axis perpendicular to
        # both BACK and TOP).
        scallop_height = scalar(2)
        scallop_length = scalar(4)
        radius = (scallop_length ** 2 + scallop_height ** 2) / (2 * scallop_height)

        timber = _make_timber()
        joint = cut_practice_rafter_tail_scallop_decoration(
            timber,
            end_side=TimberEnd.TOP,
            cut_side=TimberLongFace.BACK,
            scallop_height=scallop_height,
            scallop_length=scallop_length,
        )

        assert joint.ticket.joint_type == "rafter_tail_scallop_decoration"
        assert joint.is_decorative()
        cutting = joint.cuttings["timber"]
        assert cutting.negative_csg is not None

        # The circle must be perpendicular (not tangent) to end_side at point
        # A: its center lies exactly ON end_side's plane (local x=0, i.e. the
        # same Z as the end), offset only along cut_side's axis (Y here).
        # Verify by construction: the center must be equidistant (= radius)
        # from both A=(0,-3,12) [on cut_side, scallop_length in from the end]
        # and A itself, and the circle's radius must match the closed-form
        # tangent-perpendicular-at-A solution.
        cylinder = cutting.negative_csg
        assert isinstance(cylinder, Cylinder)
        expected_center = Matrix([0.0, -float(HEIGHT) / 2 - (float(radius) - float(scallop_height)), float(LENGTH)])
        for i in range(3):
            assert cylinder.position[i] == pytest.approx(float(expected_center[i]))
        assert cylinder.radius == pytest.approx(float(radius))

        full_prism = timber.get_perfect_timber_within_csg_local()
        result_csg = Difference(base=full_prism, subtract=[cutting.negative_csg])
        mesh = triangulate_cutcsg(result_csg).mesh
        assert mesh.is_watertight

        original_volume = float(WIDTH) * float(HEIGHT) * float(LENGTH)
        removed = original_volume - mesh.volume
        # The removed shape is the raw circle (radius computed above), clipped
        # by the timber's actual boundaries, so it's positive but strictly
        # less than the full circle's own cross-sectional area extruded
        # across the width.
        assert 0 < removed < math.pi * float(radius) ** 2 * float(WIDTH)

        # A point in the middle of the scalloped-out region (between the end
        # and where the curve meets cut_side) should be removed...
        mid_scallop = Matrix([0.0, -float(HEIGHT) / 2, float(LENGTH) - 2.0])
        assert cutting.negative_csg.contains_point(mid_scallop)
        # ...while the flat run of cut_side well before the scallop begins,
        # and the FRONT half of the cross-section at the very end, are both
        # untouched.
        far_flat_region = Matrix([0.0, -float(HEIGHT) / 2, 2.0])
        assert not cutting.negative_csg.contains_point(far_flat_region)
        front_half_at_end = Matrix([0.0, 2.0, float(LENGTH)])
        assert not cutting.negative_csg.contains_point(front_half_at_end)
