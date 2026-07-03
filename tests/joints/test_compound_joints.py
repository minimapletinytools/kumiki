"""Tests for compound joints."""

import pytest
from sympy import Matrix
from kumiki import *


def _render_for_timber(joint: Joint, timber) -> object:
    """Collect all cuttings in a compound joint that belong to *timber* and render them."""
    cuts = [c for c in joint.cuttings.values() if c.timber is timber]
    return CutTimber(timber, cuts=cuts).render_timber_with_cuts_csg_local()


def _contains(rendered, timber, global_point: V3) -> bool:
    """Return True if *global_point* is inside *rendered* (which is in timber-local space)."""
    return rendered.contains_point(timber.transform.global_to_local(global_point))


class TestMultiCrossLapJoint:
    """Tests for cut_multi_cross_lap_joint."""

    # Board geometry used throughout:
    #
    #   W=6  : board width  = stacking span along global +Z (local X = +Z)
    #   L=20 : board length
    #   T=4  : board thickness
    #   width_direction = +Z  →  LOCAL X = global +Z, so LEFT face = global -Z
    #   starting_face  = LEFT →  axis_direction = +Z
    #
    # board_0 runs along +X, centered at (0, 0, 3) in global:
    #   position = (-10, 0, 3),  global Z ∈ [0, 6],  global Y ∈ [-2, 2]
    #
    # board_1 runs along +Y, centered at (0, 0, 3) in global:
    #   position = (0, -10, 3),  global Z ∈ [0, 6],  global X ∈ [-2, 2]
    #
    # board_2 runs along +X at global Y=3:
    #   position = (-10, 3, 3),  global Z ∈ [0, 6],  global Y ∈ [1, 5]
    #   (Y overlap with board_0 in Y ∈ [1, 2]; crosses board_1 at X=0, Y ∈ [1,5])
    #
    # 2-board stacking axis boundaries: P[0] = 3  (Z midpoint)
    # 3-board stacking axis boundaries: P[0] = 2,  P[1] = 4

    def _width_dir(self):
        return create_v3(scalar(0), scalar(0), scalar(1))

    def _make_x_boards(self):
        """Two boards in an X shape (board_0 along +X, board_1 along +Y)."""
        W, L, T = scalar(6), scalar(20), scalar(4)
        wd = self._width_dir()
        board_0 = timber_from_directions(
            length=L,
            size=Matrix([W, T]),
            bottom_position=create_v3(scalar(-10), scalar(0), scalar(3)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=wd,
            ticket="board_0",
        )
        board_1 = timber_from_directions(
            length=L,
            size=Matrix([W, T]),
            bottom_position=create_v3(scalar(0), scalar(-10), scalar(3)),
            length_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            width_direction=wd,
            ticket="board_1",
        )
        return board_0, board_1

    def _make_three_boards(self):
        """
        Three boards: board_0 along +X at Y=0, board_1 along +Y, board_2 along +X at Y=3.
        board_0 and board_2 both span Y values in [1, 2] so they physically overlap in XY,
        making fill-cuts necessary.
        """
        W, L, T = scalar(6), scalar(20), scalar(4)
        wd = self._width_dir()
        board_0 = timber_from_directions(
            length=L,
            size=Matrix([W, T]),
            bottom_position=create_v3(scalar(-10), scalar(0), scalar(3)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=wd,
            ticket="board_0",
        )
        board_1 = timber_from_directions(
            length=L,
            size=Matrix([W, T]),
            bottom_position=create_v3(scalar(0), scalar(-10), scalar(3)),
            length_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            width_direction=wd,
            ticket="board_1",
        )
        board_2 = timber_from_directions(
            length=L,
            size=Matrix([W, T]),
            bottom_position=create_v3(scalar(-10), scalar(3), scalar(3)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=wd,
            ticket="board_2",
        )
        return board_0, board_1, board_2

    def test_two_board_x_stacking_zones_are_exclusive(self, symbolic_mode):
        """
        2-board X cross-lap: at the crossing, each Z zone belongs to exactly one board.
        Below the cut boundary (Z<3): board_0 present, board_1 absent.
        Above the cut boundary (Z>3): board_1 present, board_0 absent.
        """
        board_0, board_1 = self._make_x_boards()
        joint = cut_multi_cross_lap_joint(
            [board_0, board_1],
            starting_face_on_first_timber=TimberFace.LEFT,
        )
        r0 = _render_for_timber(joint, board_0)
        r1 = _render_for_timber(joint, board_1)

        # lower zone (Z=1 < P[0]=3): only board_0
        lower = create_v3(scalar(0), scalar(0), scalar(1))
        assert _contains(r0, board_0, lower), "board_0 must be present in the lower zone"
        assert not _contains(r1, board_1, lower), "board_1 must be cut away in the lower zone"

        # upper zone (Z=5 > P[0]=3): only board_1
        upper = create_v3(scalar(0), scalar(0), scalar(5))
        assert not _contains(r0, board_0, upper), "board_0 must be cut away in the upper zone"
        assert _contains(r1, board_1, upper), "board_1 must be present in the upper zone"

    def test_three_board_stacking_zones_are_exclusive(self, symbolic_mode):
        """
        3-board star: the three Z zones (Z<2, 2<Z<4, Z>4) each contain exactly one
        board at the relevant intersection point.
        """
        board_0, board_1, board_2 = self._make_three_boards()
        joint = cut_multi_cross_lap_joint(
            [board_0, board_1, board_2],
            starting_face_on_first_timber=TimberFace.LEFT,
        )
        r0 = _render_for_timber(joint, board_0)
        r1 = _render_for_timber(joint, board_1)
        r2 = _render_for_timber(joint, board_2)

        # --- board_0 / board_1 intersection at (0, 0) ---
        # lower zone (Z=1 < P[0]=2): only board_0
        p_low = create_v3(scalar(0), scalar(0), scalar(1))
        assert _contains(r0, board_0, p_low), "board_0 must be present in the lower zone"
        assert not _contains(r1, board_1, p_low), "board_1 must be cut away in the lower zone"

        # middle zone (Z=3, P[0]=2 < Z < P[1]=4): only board_1
        p_mid = create_v3(scalar(0), scalar(0), scalar(3))
        assert not _contains(r0, board_0, p_mid), "board_0 must be cut away in the middle zone"
        assert _contains(r1, board_1, p_mid), "board_1 must be present in the middle zone"

        # --- board_1 / board_2 intersection at (0, 3) ---
        # middle zone (Z=3): only board_1
        p_mid_12 = create_v3(scalar(0), scalar(3), scalar(3))
        assert _contains(r1, board_1, p_mid_12), "board_1 must be present in the middle zone"
        assert not _contains(r2, board_2, p_mid_12), "board_2 must be cut away in the middle zone"

        # upper zone (Z=5 > P[1]=4): only board_2
        p_hi = create_v3(scalar(0), scalar(3), scalar(5))
        assert not _contains(r1, board_1, p_hi), "board_1 must be cut away in the upper zone"
        assert _contains(r2, board_2, p_hi), "board_2 must be present in the upper zone"

    def test_fill_cuts_prevent_non_adjacent_board_overlap(self, symbolic_mode):
        """
        3-board star: board_0 and board_2 are non-adjacent and physically overlap at
        X=5 (far outside the board_1 joint region), Y=1.5 (inside both boards' Y cross-sections).

        Forward fill-cut: board_2 must not intrude into board_0's owned zone (Z < P[0]=2).
        Backward fill-cut: board_0 must not intrude into board_2's owned zone (Z > P[1]=4).
        """
        board_0, board_1, board_2 = self._make_three_boards()
        joint = cut_multi_cross_lap_joint(
            [board_0, board_1, board_2],
            starting_face_on_first_timber=TimberFace.LEFT,
        )
        r0 = _render_for_timber(joint, board_0)
        r2 = _render_for_timber(joint, board_2)

        # X=5 is outside board_1's X span ([-2, 2]); Y=3/2 is in board_0 (Y∈[-2,2]) and board_2 (Y∈[1,5])
        # Forward fill-cut: board_0 owns Z < P[0]=2; board_2 must be absent
        p_fwd = create_v3(scalar(5), scalar(3, 2), scalar(1))
        assert _contains(r0, board_0, p_fwd), "board_0 must be present below P[0] outside the joint region"
        assert not _contains(r2, board_2, p_fwd), "board_2 must be cut by forward fill-cut below P[0]"

        # Backward fill-cut: board_2 owns Z > P[1]=4; board_0 must be absent
        p_bwd = create_v3(scalar(5), scalar(3, 2), scalar(5))
        assert not _contains(r0, board_0, p_bwd), "board_0 must be cut by backward fill-cut above P[1]"
        assert _contains(r2, board_2, p_bwd), "board_2 must be present above P[1] outside the joint region"

