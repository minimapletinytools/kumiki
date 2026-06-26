"""Tongue-and-groove board joint example using PatternBook."""

from sympy import Matrix

from kumiki.joints.workshop.board_joints import (
    cut_board_in_grooved_rectangular_frame_joint,
    cut_tongue_and_groove_joint,
)
from kumiki.joints.workshop.corner_joints import cut_plain_miter_joint_on_face_aligned_timbers
from kumiki.construction import CornerJointTimberArrangement
from kumiki.patternbook import PatternBook, PatternMetadata, Pattern, make_pattern_from_joint
from kumiki.rule import feet, inches
from kumiki.ticket import BoardTicket, TimberTicket
from kumiki.timber import Board, Orientation, Timber, TimberReferenceEnd, Transform, create_v3


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


# TODO rewrite this so that the boards are positioned in the frame rather than the other way around, that's a more likely pattern
def example_board_in_grooved_frame(position=None):
    """Three boards fitted into a four-timber grooved rectangular frame.

    The boards run vertically (local Z = global Z).  Left/right stiles share
    that orientation; top/bottom rails run in the global X direction.
    """
    if position is None:
        position = create_v3(inches(0), inches(0), inches(0))

    board_width     = inches(6.5)  # Widened to 6.5" so boards groove into left/right stiles
    board_thickness = inches(3, 4)
    board_length    = inches(40)
    n_boards        = 4
    groove_depth    = inches(3, 8)   # how deep the groove bites into the rail/stile
    groove_extra    = inches(1, 16)  # clearance around board thickness

    rail_width    = inches(2)
    rail_thick    = inches(2)
    stile_width   = inches(2)
    stile_thick   = inches(2)

    # Panel total X span
    panel_width = board_width * n_boards

    # Boards: stacked in X, all with identity orientation.
    boards = [
        Board(
            length=board_length,
            size=Matrix([board_width, board_thickness]),
            transform=Transform(
                position=position + create_v3(
                    board_width / 2 + board_width * i,
                    inches(0),
                    inches(0),
                ),
                orientation=Orientation.identity(),
            ),
            ticket=BoardTicket(name=f"board_{i + 1}"),
        )
        for i in range(n_boards)
    ]

    # Left and right stiles run in Z (same orientation as the boards).
    # They are positioned just outside the panel edges, overlapping in Z.
    stile_orient = Orientation.identity()

    left_stile = Timber(
        length=board_length,
        size=Matrix([stile_width, stile_thick]),
        transform=Transform(
            position=position + create_v3(-stile_width / 2 + groove_depth, inches(0), inches(0)),
            orientation=stile_orient,
        ),
        ticket=TimberTicket(name="left_stile"),
    )
    right_stile = Timber(
        length=board_length,
        size=Matrix([stile_width, stile_thick]),
        transform=Transform(
            position=position + create_v3(panel_width + stile_width / 2 - groove_depth, inches(0), inches(0)),
            orientation=stile_orient,
        ),
        ticket=TimberTicket(name="right_stile"),
    )

    # Top and bottom rails run in X (local Z = global X).
    # Orientation: local Z = [1,0,0], local X = [0,0,1] → local Y = [0,-1,0]
    rail_orient = Orientation.from_z_and_x(
        Matrix([1, 0, 0]), Matrix([0, 0, 1])
    )
    # Rail length exceeds panel width so the rail visually extends past the stiles.
    rail_length = panel_width + stile_width * 5

    # Rail transform.position is the bottom center of the rail cross-section
    # (local Z = 0, i.e. the starting X end of the rail).
    rail_start_x = position[0] - stile_width / 2

    bot_rail = Timber(
        length=rail_length,
        size=Matrix([rail_width, rail_thick]),
        transform=Transform(
            position=create_v3(rail_start_x, position[1], position[2]),
            orientation=rail_orient,
        ),
        ticket=TimberTicket(name="bottom_rail"),
    )
    top_rail = Timber(
        length=rail_length,
        size=Matrix([rail_width, rail_thick]),
        transform=Transform(
            position=create_v3(rail_start_x, position[1], position[2] + board_length),
            orientation=rail_orient,
        ),
        ticket=TimberTicket(name="top_rail"),
    )

    # Create the main board-in-groove joint
    board_joint = cut_board_in_grooved_rectangular_frame_joint(
        boards=boards,
        board_top_end_timbers=[top_rail],
        board_bottom_end_timbers=[bot_rail],
        board_left_side_timbers=[left_stile],
        board_right_side_timbers=[right_stile],
        groove_extra_space=groove_extra,
    )

    # Create miter joints at the four frame corners to align timbers
    miter_bl = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=bot_rail,
            timber2=left_stile,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.BOTTOM,
        )
    )
    miter_br = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=bot_rail,
            timber2=right_stile,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.BOTTOM,
        )
    )
    miter_tl = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=top_rail,
            timber2=left_stile,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.TOP,
        )
    )
    miter_tr = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=top_rail,
            timber2=right_stile,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.TOP,
        )
    )

    # Return a Frame combining all joints (board-in-groove plus four miter joints)
    from kumiki.timber import Frame
    return Frame.from_joints([board_joint, miter_bl, miter_br, miter_tl, miter_tr], name="Board in Grooved Frame")


patterns = [
    Pattern(path="board_joints/tongue_and_groove", lambda_=make_pattern_from_joint(example_tongue_and_groove), pattern_type='frame', tags=['main']),
    Pattern(path="board_joints/board_in_grooved_frame", lambda_=example_board_in_grooved_frame, pattern_type='frame', tags=['main']),
]


if __name__ == "__main__":
    frame = create_all_board_joint_patterns()
    print(f"Frame: {frame.name}")
    print(f"Cut timbers: {len(frame.cut_timbers)}")
