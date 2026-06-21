"""Tests for board joint functions."""

import pytest
from sympy import Integer, Matrix, Rational

from kumiki.joints.workshop.board_joints import cut_tongue_and_groove_joint
from kumiki.ticket import BoardTicket
from kumiki.timber import Board, Orientation, Transform, create_v3
from kumiki.cutcsg import RectangularPrism, SolidUnion


def _make_boards(
    *,
    board_width=Rational(20),
    board_thickness=Rational(10),
    board_length=Rational(100),
    overlap=Rational(2),
    y_offset=Rational(0),
    groove_on_left=False,
):
    """Build a (tongue_board, groove_board) pair offset along X to overlap."""
    tongue_board = Board(
        length=board_length,
        size=Matrix([board_width, board_thickness]),
        transform=Transform.identity(),
        ticket=BoardTicket(name="tongue_board"),
    )
    center_offset_x = board_width - overlap
    if groove_on_left:
        center_offset_x = -center_offset_x
    groove_board = Board(
        length=board_length,
        size=Matrix([board_width, board_thickness]),
        transform=Transform(
            position=create_v3(center_offset_x, y_offset, Integer(0)),
            orientation=Orientation.identity(),
        ),
        ticket=BoardTicket(name="groove_board"),
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
            tongue_depth=Rational(2),
            tongue_width=Rational(4),
        )

        assert joint.ticket.joint_type == "tongue_and_groove"
        assert len(joint.cuttings) == 2
        assert tongue_board.ticket.name in joint.cuttings
        assert groove_board.ticket.name in joint.cuttings

        tongue_cut = joint.cuttings[tongue_board.ticket.name]
        groove_cut = joint.cuttings[groove_board.ticket.name]
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
        assert groove_prism.size[0] == Rational(2)  # tongue_depth
        assert groove_prism.size[1] == Rational(4)  # tongue_width
        trim_prism = groove_union.children[1]
        assert isinstance(trim_prism, RectangularPrism)
        # Trim spans the full board thickness.
        assert trim_prism.size[1] == groove_board.size[1]

    def test_groove_on_left_flips_side(self):
        tongue_board, groove_board = _make_boards(groove_on_left=True)

        joint = cut_tongue_and_groove_joint(
            tongue_board=tongue_board,
            groove_board=groove_board,
            tongue_depth=Rational(2),
            tongue_width=Rational(4),
        )

        # Groove prism's X center should sit on the LEFT side of tongue board
        # (negative X) because the groove board is on the left.
        tongue_cut = joint.cuttings[tongue_board.ticket.name]
        tongue_union = tongue_cut.negative_csg
        assert isinstance(tongue_union, SolidUnion)
        first_remove = tongue_union.children[0]
        assert isinstance(first_remove, RectangularPrism)
        assert first_remove.transform.position[0] < 0

        # And the groove cavity sits on the RIGHT face of the groove board.
        groove_cut = joint.cuttings[groove_board.ticket.name]
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
            tongue_depth=Rational(2),
            tongue_width=Rational(4),
            tongue_center_offset=Rational(1),
        )

        groove_cut = joint.cuttings[groove_board.ticket.name]
        groove_union = groove_cut.negative_csg
        assert isinstance(groove_union, SolidUnion)
        groove_prism = groove_union.children[0]
        assert isinstance(groove_prism, RectangularPrism)
        # Groove Y center should follow the tongue's Y center (offset by 1)
        # in the groove board's local frame (boards share Y origin here).
        assert groove_prism.transform.position[1] == Rational(1)

    def test_tongue_and_groove_with_extra_depth(self, tongue_groove_boards):
        tongue_board, groove_board = tongue_groove_boards

        joint = cut_tongue_and_groove_joint(
            tongue_board=tongue_board,
            groove_board=groove_board,
            tongue_depth=Rational(2),
            tongue_width=Rational(4),
            groove_extra_depth=Rational(1),
        )

        groove_cut = joint.cuttings[groove_board.ticket.name]
        groove_union = groove_cut.negative_csg
        assert isinstance(groove_union, SolidUnion)
        groove_prism = groove_union.children[0]
        assert isinstance(groove_prism, RectangularPrism)
        # Groove X-size grows by groove_extra_depth.
        assert groove_prism.size[0] == Rational(3)  # tongue_depth + extra

    def test_insufficient_overlap_warns(self):
        # Boards only overlap by 1 but tongue_depth is 3 → warning expected.
        tongue_board, groove_board = _make_boards(overlap=Rational(1))
        with pytest.warns(UserWarning, match="does not overlap tongue board enough"):
            cut_tongue_and_groove_joint(
                tongue_board=tongue_board,
                groove_board=groove_board,
                tongue_depth=Rational(3),
                tongue_width=Rational(4),
            )

    def test_no_thickness_overlap_raises(self):
        # Shift groove board far enough in Y that boards don't overlap in thickness at all.
        tongue_board, groove_board = _make_boards(y_offset=Rational(20))
        with pytest.raises(AssertionError, match="does not overlap tongue board at all"):
            cut_tongue_and_groove_joint(
                tongue_board=tongue_board,
                groove_board=groove_board,
                tongue_depth=Rational(2),
                tongue_width=Rational(4),
            )

    def test_misoriented_board_warns(self):
        # Thicker than wide → warning.
        tongue_board = Board(
            length=Rational(100),
            size=Matrix([Rational(5), Rational(10)]),  # width 5 < thickness 10
            transform=Transform.identity(),
            ticket=BoardTicket(name="tongue_board"),
        )
        groove_board = Board(
            length=Rational(100),
            size=Matrix([Rational(5), Rational(10)]),
            transform=Transform(
                position=create_v3(Rational(3), Integer(0), Integer(0)),
                orientation=Orientation.identity(),
            ),
            ticket=BoardTicket(name="groove_board"),
        )
        with pytest.warns(UserWarning, match="thicker than it is wide"):
            cut_tongue_and_groove_joint(
                tongue_board=tongue_board,
                groove_board=groove_board,
                tongue_depth=Rational(1),
                tongue_width=Rational(2),
            )
