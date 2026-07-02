"""Tests for board joint functions."""

import pytest
from sympy import Matrix

from kumiki.joints.workshop.board_joints import (
    cut_board_in_grooved_rectangular_frame_joint,
    cut_tongue_and_groove_joint,
)
from kumiki.ticket import BoardTicket, TimberTicket
from kumiki.rule import equality_test, scalar
from kumiki.timber import Board, Orientation, Timber, Transform, create_v3
from kumiki.cutcsg import RectangularPrism, SolidUnion


def _make_boards(
    *,
    board_width=scalar(20),
    board_thickness=scalar(10),
    board_length=scalar(100),
    overlap=scalar(2),
    y_offset=scalar(0),
    groove_on_left=False,
):
    """Build a (tongue_board, groove_board) pair offset along X to overlap."""
    tongue_board = Board(
        length=board_length,
        size=Matrix([board_width, board_thickness]),
        transform=Transform.identity(),
        ticket=BoardTicket(path="tongue_board"),
    )
    center_offset_x = board_width - overlap
    if groove_on_left:
        center_offset_x = -center_offset_x
    groove_board = Board(
        length=board_length,
        size=Matrix([board_width, board_thickness]),
        transform=Transform(
            position=create_v3(center_offset_x, y_offset, scalar(0)),
            orientation=Orientation.identity(),
        ),
        ticket=BoardTicket(path="groove_board"),
    )
    return tongue_board, groove_board


@pytest.fixture
def tongue_groove_boards():
    """Default boards: 20x10x100 with a 2-unit overlap (groove board to the right)."""
    return _make_boards()


class TestTongueAndGrooveJoint:
    """Tests for cut_tongue_and_groove_joint."""

    def test_basic_tongue_and_groove_joint(self, tongue_groove_boards):
        tongue_board, groove_board = tongue_groove_boards

        joint = cut_tongue_and_groove_joint(
            tongue_board=tongue_board,
            groove_board=groove_board,
            tongue_depth=scalar(2),
            tongue_width=scalar(4),
        )

        assert joint.ticket.joint_type == "tongue_and_groove"
        assert len(joint.cuttings) == 2
        assert tongue_board.ticket.path in joint.cuttings
        assert groove_board.ticket.path in joint.cuttings

        tongue_cut = joint.cuttings[tongue_board.ticket.path]
        groove_cut = joint.cuttings[groove_board.ticket.path]
        assert tongue_cut.label == "tongue_and_groove"
        assert groove_cut.label == "tongue_and_groove"

        # Tongue side has two prism subtractions (top/bottom remove).
        assert isinstance(tongue_cut.negative_csg, SolidUnion)
        assert len(tongue_cut.negative_csg.children) == 2

        # Groove side has the groove cavity plus an excess-trim prism.
        groove_union = groove_cut.negative_csg
        assert isinstance(groove_union, SolidUnion)
        assert len(groove_union.children) == 2
        groove_prism = groove_union.children[0]
        assert isinstance(groove_prism, RectangularPrism)
        assert groove_prism.size[0] == scalar(2)  # tongue_depth
        assert groove_prism.size[1] == scalar(4)  # tongue_width
        trim_prism = groove_union.children[1]
        assert isinstance(trim_prism, RectangularPrism)
        # Trim spans the full board thickness.
        assert trim_prism.size[1] == groove_board.size[1]

    def test_groove_on_left_flips_side(self):
        tongue_board, groove_board = _make_boards(groove_on_left=True)

        joint = cut_tongue_and_groove_joint(
            tongue_board=tongue_board,
            groove_board=groove_board,
            tongue_depth=scalar(2),
            tongue_width=scalar(4),
        )

        # Groove prism's X center should sit on the LEFT side of tongue board
        # (negative X) because the groove board is on the left.
        tongue_cut = joint.cuttings[tongue_board.ticket.path]
        tongue_union = tongue_cut.negative_csg
        assert isinstance(tongue_union, SolidUnion)
        first_remove = tongue_union.children[0]
        assert isinstance(first_remove, RectangularPrism)
        assert first_remove.transform.position[0] < 0

        # And the groove cavity sits on the RIGHT face of the groove board.
        groove_cut = joint.cuttings[groove_board.ticket.path]
        groove_union = groove_cut.negative_csg
        assert isinstance(groove_union, SolidUnion)
        groove_prism = groove_union.children[0]
        assert isinstance(groove_prism, RectangularPrism)
        assert groove_prism.transform.position[0] > 0

    def test_tongue_and_groove_with_offset(self, tongue_groove_boards):
        tongue_board, groove_board = tongue_groove_boards

        joint = cut_tongue_and_groove_joint(
            tongue_board=tongue_board,
            groove_board=groove_board,
            tongue_depth=scalar(2),
            tongue_width=scalar(4),
            tongue_center_offset=scalar(1),
        )

        groove_cut = joint.cuttings[groove_board.ticket.path]
        groove_union = groove_cut.negative_csg
        assert isinstance(groove_union, SolidUnion)
        groove_prism = groove_union.children[0]
        assert isinstance(groove_prism, RectangularPrism)
        # Groove Y center should follow the tongue's Y center (offset by 1)
        # in the groove board's local frame (boards share Y origin here).
        assert groove_prism.transform.position[1] == scalar(1)

    def test_tongue_and_groove_with_extra_depth(self, tongue_groove_boards):
        tongue_board, groove_board = tongue_groove_boards

        joint = cut_tongue_and_groove_joint(
            tongue_board=tongue_board,
            groove_board=groove_board,
            tongue_depth=scalar(2),
            tongue_width=scalar(4),
            groove_extra_depth=scalar(1),
        )

        groove_cut = joint.cuttings[groove_board.ticket.path]
        groove_union = groove_cut.negative_csg
        assert isinstance(groove_union, SolidUnion)
        groove_prism = groove_union.children[0]
        assert isinstance(groove_prism, RectangularPrism)
        # Groove X-size grows by groove_extra_depth.
        assert groove_prism.size[0] == scalar(3)  # tongue_depth + extra

    def test_insufficient_overlap_warns(self):
        # Boards only overlap by 1 but tongue_depth is 3 → warning expected.
        tongue_board, groove_board = _make_boards(overlap=scalar(1))
        with pytest.warns(UserWarning, match="does not overlap tongue board enough"):
            cut_tongue_and_groove_joint(
                tongue_board=tongue_board,
                groove_board=groove_board,
                tongue_depth=scalar(3),
                tongue_width=scalar(4),
            )

    def test_no_thickness_overlap_raises(self):
        # Shift groove board far enough in Y that boards don't overlap in thickness at all.
        tongue_board, groove_board = _make_boards(y_offset=scalar(20))
        with pytest.raises(AssertionError, match="does not overlap tongue board at all"):
            cut_tongue_and_groove_joint(
                tongue_board=tongue_board,
                groove_board=groove_board,
                tongue_depth=scalar(2),
                tongue_width=scalar(4),
            )

    def test_misoriented_board_warns(self):
        # Thicker than wide → warning.
        tongue_board = Board(
            length=scalar(100),
            size=Matrix([scalar(5), scalar(10)]),  # width 5 < thickness 10
            transform=Transform.identity(),
            ticket=BoardTicket(path="tongue_board"),
        )
        groove_board = Board(
            length=scalar(100),
            size=Matrix([scalar(5), scalar(10)]),
            transform=Transform(
                position=create_v3(scalar(3), scalar(0), scalar(0)),
                orientation=Orientation.identity(),
            ),
            ticket=BoardTicket(path="groove_board"),
        )
        with pytest.warns(UserWarning, match="thicker than it is wide"):
            cut_tongue_and_groove_joint(
                tongue_board=tongue_board,
                groove_board=groove_board,
                tongue_depth=scalar(1),
                tongue_width=scalar(2),
            )


class TestBoardInGroovedRectangularFrameJoint:
    """Tests for cut_board_in_grooved_rectangular_frame_joint."""

    def _make_frame(self, *, n_boards=2, groove_extra_space=scalar(0)):
        """
        Build a panel of *n_boards* side-by-side boards and four surrounding
        frame timbers, all with identity orientation for simplicity.

        Board dimensions: width=10, thickness=2, length=20.
        Frame timbers: 3×3 cross-section.
        """
        board_width     = scalar(10)
        board_thickness = scalar(2)
        board_length    = scalar(20)
        timber_size     = Matrix([scalar(3), scalar(3)])

        boards = [
            Board(
                length=board_length,
                size=Matrix([board_width, board_thickness]),
                transform=Transform(
                    position=create_v3(board_width * scalar(i), scalar(0), scalar(0)),
                    orientation=Orientation.identity(),
                ),
                ticket=BoardTicket(path=f"board_{i}"),
            )
            for i in range(n_boards)
        ]

        panel_half_w = board_width * n_boards / scalar(2)

        top_timber = Timber(
            length=scalar(5),
            size=timber_size,
            transform=Transform(
                position=create_v3(scalar(0), scalar(0), board_length),
                orientation=Orientation.identity(),
            ),
            ticket=TimberTicket(path="top"),
        )
        bot_timber = Timber(
            length=scalar(5),
            size=timber_size,
            transform=Transform.identity(),
            ticket=TimberTicket(path="bottom"),
        )
        left_timber = Timber(
            length=board_length,
            size=timber_size,
            transform=Transform(
                position=create_v3(-panel_half_w, scalar(0), scalar(0)),
                orientation=Orientation.identity(),
            ),
            ticket=TimberTicket(path="left"),
        )
        right_timber = Timber(
            length=board_length,
            size=timber_size,
            transform=Transform(
                position=create_v3(panel_half_w, scalar(0), scalar(0)),
                orientation=Orientation.identity(),
            ),
            ticket=TimberTicket(path="right"),
        )

        joint = cut_board_in_grooved_rectangular_frame_joint(
            boards=boards,
            board_top_end_timbers=[top_timber],
            board_bottom_end_timbers=[bot_timber],
            board_left_side_timbers=[left_timber],
            board_right_side_timbers=[right_timber],
            groove_extra_space=groove_extra_space,
        )
        return joint, boards, [top_timber, bot_timber, left_timber, right_timber]

    def test_joint_structure(self):
        """Returns frame-timber cuttings plus uncut board members."""
        joint, boards, _ = self._make_frame()

        assert joint.ticket.joint_type == "board_in_grooved_frame"
        expected_frame_keys = {"top", "bottom", "left", "right"}
        expected_board_keys = {b.ticket.path for b in boards}
        assert set(joint.cuttings.keys()) == expected_frame_keys | expected_board_keys

        for key in expected_frame_keys:
            cutting = joint.cuttings[key]
            assert cutting.label == "board_in_grooved_frame"
            assert isinstance(cutting.negative_csg, RectangularPrism)

        for key in expected_board_keys:
            cutting = joint.cuttings[key]
            assert cutting.label == "board_in_grooved_frame"
            assert cutting.negative_csg is None

    def test_groove_thickness_matches_board(self):
        """Groove Y-size equals board thickness when groove_extra_space=0.

        Side timbers share the reference board's orientation so the prism
        size is not permuted by adopt_csg; we can check size[1] directly.
        """
        board_thickness = scalar(2)
        joint, _, _ = self._make_frame(groove_extra_space=scalar(0))

        left_prism = joint.cuttings["left"].negative_csg
        assert isinstance(left_prism, RectangularPrism)
        assert equality_test(left_prism.size[1], board_thickness)

    def test_groove_extra_space_widens_groove(self):
        """Groove Y-size grows by groove_extra_space."""
        board_thickness = scalar(2)
        extra           = scalar(1, 4)
        joint, _, _ = self._make_frame(groove_extra_space=extra)

        left_prism = joint.cuttings["left"].negative_csg
        assert isinstance(left_prism, RectangularPrism)
        assert equality_test(left_prism.size[1], board_thickness + extra)

    def test_groove_width_spans_full_panel(self):
        """Groove X-size equals total panel width (n_boards × board_width)."""
        n   = 3
        bw  = scalar(10)
        joint, _, _ = self._make_frame(n_boards=n)

        left_prism = joint.cuttings["left"].negative_csg
        assert isinstance(left_prism, RectangularPrism)
        assert equality_test(left_prism.size[0], bw * scalar(n))
