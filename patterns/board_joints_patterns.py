"""Tongue-and-groove board joint example using PatternBook."""

from sympy import Matrix

from kumiki.joints.workshop.board_joints import cut_tongue_and_groove_joint
from kumiki.patternbook import PatternBook, PatternMetadata, Pattern, make_pattern_from_joint
from kumiki.rule import feet, inches
from kumiki.ticket import BoardTicket
from kumiki.timber import Board, Orientation, Transform, create_v3


def example_tongue_and_groove(position=None):
    """Single tongue-and-groove pattern with one tongue board and one groove board."""
    if position is None:
        position = create_v3(inches(0), inches(0), inches(0))

    board_width = inches(7)
    board_thickness = inches(3, 4)
    board_length = feet(4)

    overlap = inches(1)
    center_offset_x = board_width - overlap

    tongue_board = Board(
        length=board_length,
        size=Matrix([board_width, board_thickness]),
        transform=Transform(position=position, orientation=Orientation.identity()),
        ticket=BoardTicket(name="tongue_board"),
    )

    groove_board = Board(
        length=board_length,
        size=Matrix([board_width, board_thickness]),
        transform=Transform(
            position=position + create_v3(center_offset_x, inches(0), inches(0)),
            orientation=Orientation.identity(),
        ),
        ticket=BoardTicket(name="groove_board"),
    )

    return cut_tongue_and_groove_joint(
        tongue_board=tongue_board,
        groove_board=groove_board,
        tongue_depth=inches(1, 4),
        tongue_width=inches(1, 4),
        tongue_center_offset=inches(0),
        groove_extra_depth=inches(0),
    )


def create_board_joints_patternbook() -> PatternBook:
    """Create PatternBook containing the single tongue-and-groove board pattern."""
    patterns = [
        (
            PatternMetadata("tongue_and_groove", ["tongue_groove", "boards"], "frame"),
            make_pattern_from_joint(example_tongue_and_groove),
        ),
    ]
    return PatternBook(patterns=patterns)


patternbook = create_board_joints_patternbook()


def create_all_board_joint_patterns():
    """Raise the tongue-and-groove group into a single frame."""
    return patternbook.raise_pattern_group("tongue_groove", separation_distance=inches(96))


example = create_all_board_joint_patterns

patterns = [
    Pattern(path="board_joints/tongue_and_groove", lambda_=make_pattern_from_joint(example_tongue_and_groove), pattern_type='frame', tags=['main']),
]


if __name__ == "__main__":
    frame = create_all_board_joint_patterns()
    print(f"Frame: {frame.name}")
    print(f"Cut timbers: {len(frame.cut_timbers)}")
