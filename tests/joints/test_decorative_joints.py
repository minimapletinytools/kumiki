"""Tests for decorative joints."""

import math

import pytest
from sympy import Matrix

from kumiki.joints.workshop.decorative_joints import cut_practice_roundover_decoration
from kumiki.ticket import TimberTicket
from kumiki.rule import scalar, Transform
from kumiki.timber import Timber, TimberEdge
from kumiki.cutcsg import Difference
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
