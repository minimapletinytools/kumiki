"""Tests for decorative joints."""

import math
import warnings

import pytest
from sympy import Matrix

from kumiki.joints.workshop.decorative_joints import (
    cut_practice_roundover_decoration,
    cut_practice_rafter_tail_scallop_decoration,
    cut_practice_rounded_end_decoration,
)
from kumiki.ticket import TimberTicket
from kumiki.rule import scalar, Transform
from kumiki.timber import Timber, TimberEdge, TimberEnd, TimberFace, TimberLongFace, TimberShortEdge
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
            short_edge=TimberShortEdge.TOP_BACK,
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

    def test_scallop_cut_accepts_timber_edge(self):
        timber = _make_timber()
        joint = cut_practice_rafter_tail_scallop_decoration(
            timber,
            short_edge=TimberEdge.TOP_BACK,
            scallop_height=scalar(2),
            scallop_length=scalar(4),
        )
        assert joint.ticket.joint_type == "rafter_tail_scallop_decoration"


class TestRoundedEndDecoration:
    """Tests for cut_practice_rounded_end_decoration.

    Uses rounded_face=RIGHT, rounded_end=TOP throughout: the cylinder axis runs
    along X (WIDTH), so it doesn't matter which X the test points use, and the
    arc spans Y (HEIGHT, half-extent 3) at the TOP end (Z=LENGTH=12).
    """

    def _result(self, radius, distance_from_end, lateral_offset=scalar(0)):
        timber = _make_timber()
        joint = cut_practice_rounded_end_decoration(
            timber,
            rounded_face=TimberFace.RIGHT,
            rounded_end=TimberFace.TOP,
            radius=radius,
            distance_from_end=distance_from_end,
            lateral_offset=lateral_offset,
        )
        cutting = joint.cuttings["timber"]
        full_prism = timber.get_perfect_timber_within_csg_local()
        result_csg = Difference(base=full_prism, subtract=[cutting.negative_csg])
        return joint, cutting, result_csg

    def test_joint_structure(self):
        joint, cutting, _ = self._result(radius=scalar(5), distance_from_end=scalar(5))

        assert joint.ticket.joint_type == "rounded_end_decoration"
        assert joint.is_decorative()
        assert set(joint.cuttings.keys()) == {"timber"}
        assert cutting.label == "rounded_end_decoration"
        assert cutting.negative_csg is not None

    def test_watertight(self):
        _, _, result_csg = self._result(radius=scalar(5), distance_from_end=scalar(5))
        mesh = triangulate_cutcsg(result_csg).mesh
        assert mesh.is_watertight

    def test_tangent_at_center_recedes_toward_corners(self):
        # distance_from_end == radius: the arc is tangent to the original
        # boundary exactly at the lateral center (Y=0) and recedes by the
        # sagitta -- radius - sqrt(radius**2 - half_extent**2) = 5 - 4 = 1 --
        # at the full corner (Y=half_extent=3), i.e. the corner's new boundary
        # is at Z=11.
        _, _, result_csg = self._result(radius=scalar(5), distance_from_end=scalar(5))

        center_near_end = Matrix([0.0, 0.0, float(LENGTH) - 0.01])
        assert result_csg.contains_point(center_near_end)

        corner_at_original_end = Matrix([0.0, 3.0, float(LENGTH)])
        assert not result_csg.contains_point(corner_at_original_end)

        corner_within_recession = Matrix([0.0, 3.0, float(LENGTH) - 0.1])  # Z=11.9 > 11 -> removed
        assert not result_csg.contains_point(corner_within_recession)

        corner_past_recession = Matrix([0.0, 3.0, float(LENGTH) - 1.5])  # Z=10.5 < 11 -> kept
        assert result_csg.contains_point(corner_past_recession)

        far_from_end = Matrix([0.0, 0.0, 5.0])
        assert result_csg.contains_point(far_from_end)

    def test_flat_center_when_distance_from_end_less_than_radius(self):
        # distance_from_end=2 < radius=5: the flat band half-width
        # sqrt(radius**2 - distance_from_end**2) = sqrt(21) ~= 4.58 exceeds
        # the timber's own half-extent (3), so nothing is removed anywhere
        # across the whole width -- not even the corners.
        with pytest.warns(UserWarning, match="distance_from_end"):
            _, _, result_csg = self._result(radius=scalar(5), distance_from_end=scalar(2))

        center_at_end = Matrix([0.0, 0.0, float(LENGTH)])
        assert result_csg.contains_point(center_at_end)
        corner_at_end = Matrix([0.0, 3.0, float(LENGTH)])
        assert result_csg.contains_point(corner_at_end)

    def test_distance_from_end_equal_to_radius_does_not_warn(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self._result(radius=scalar(5), distance_from_end=scalar(5))

    def test_lateral_offset_shifts_the_bulge(self):
        # rounded_end.rotate_about(rounded_face) = TOP.rotate_about(RIGHT) = BACK,
        # whose direction is -Y, so positive lateral_offset shifts the arc's
        # center toward -Y. That makes the -Y corner recede less (it's now
        # closer to the shifted center): its new boundary moves from Z=11
        # (centered) to Z=12-(5-sqrt(25-4))~=11.58. At Z=11.3 (between those
        # two boundaries), the -Y corner point flips from removed (centered)
        # to kept (offset).
        _, _, centered = self._result(radius=scalar(5), distance_from_end=scalar(5))
        _, _, offset = self._result(radius=scalar(5), distance_from_end=scalar(5), lateral_offset=scalar(1))

        probe = Matrix([0.0, -3.0, 11.3])
        assert not centered.contains_point(probe)
        assert offset.contains_point(probe)

    def test_radius_too_small_for_width_raises(self):
        timber = _make_timber()
        with pytest.raises(AssertionError, match="too small"):
            cut_practice_rounded_end_decoration(
                timber,
                rounded_face=TimberFace.RIGHT,
                rounded_end=TimberFace.TOP,
                radius=scalar(1),  # half-extent along Y is 3 > radius
                distance_from_end=scalar(1),
            )
