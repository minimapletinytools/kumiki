"""Tongue-and-groove board joint example using PatternBook."""

from sympy import Matrix

from kumiki.joints.workshop.board_joints import (
    cut_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers,
    cut_tongue_and_groove_joint,
)
from kumiki.joints.workshop.corner_joints import cut_plain_miter_joint_on_face_aligned_timbers
from kumiki.construction import CornerJointTimberArrangement
from kumiki.patternbook import Pattern, make_pattern_from_joint, make_pattern_from_frame
from kumiki.rule import feet, inches
from kumiki.ticket import BoardTicket, TimberTicket
from kumiki.timber import Board, Frame, Orientation, Timber, TimberEnd, Transform, create_v3


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
        ticket=BoardTicket(path="tongue_board"),
    )

    groove_board = Board(
        length=board_length,
        size=Matrix([board_width, board_thickness]),
        transform=Transform(
            position=position + create_v3(center_offset_x, inches(0), inches(0)),
            orientation=Orientation.identity(),
        ),
        ticket=BoardTicket(path="groove_board"),
    )

    return cut_tongue_and_groove_joint(
        tongue_board=tongue_board,
        groove_board=groove_board,
        tongue_depth=inches(1, 4),
        tongue_width=inches(1, 4),
        tongue_center_offset=inches(0),
        groove_extra_depth=inches(0),
    )


def example_board_in_grooved_frame(
    frame_width=inches(24),
    frame_height=inches(40),
    board_orientation="vertical",
    n_boards=4,
) -> Frame:
    """Boards fitted into a grooved rectangular frame.

    The frame outer dimensions are established first; boards are then positioned
    relative to the inside of the frame so they overlap by groove_depth on all sides.

    Args:
        frame_width: Outer width of the frame (X dimension).
        frame_height: Outer height of the frame (Z dimension).
        board_orientation: "vertical" (boards run in Z, stacked in X) or
                           "horizontal" (boards run in X, stacked in Z).
        n_boards: Number of boards filling the panel.
    """
    member_size = inches(2)
    board_thickness = inches(3, 4)
    groove_depth = inches(3, 8)
    groove_extra = inches(1, 16)

    # Inner face positions (where each frame member faces inward).
    inner_x_min = member_size            # left stile inner face
    inner_x_max = frame_width - member_size   # right stile inner face
    inner_z_min = member_size            # bottom rail inner face
    inner_z_max = frame_height - member_size  # top rail inner face

    # Stiles: run in Z (full frame height), identity orientation.
    stile_orient = Orientation.identity()
    left_stile = Timber(
        length=frame_height,
        size=Matrix([member_size, member_size]),
        transform=Transform(
            position=create_v3(member_size / 2, inches(0), inches(0)),
            orientation=stile_orient,
        ),
        ticket=TimberTicket(path="left_stile"),
    )
    right_stile = Timber(
        length=frame_height,
        size=Matrix([member_size, member_size]),
        transform=Transform(
            position=create_v3(frame_width - member_size / 2, inches(0), inches(0)),
            orientation=stile_orient,
        ),
        ticket=TimberTicket(path="right_stile"),
    )

    # Rails: run in X (full frame width). local Z = global X, local X = global Z.
    rail_orient = Orientation.from_z_and_x(Matrix([1, 0, 0]), Matrix([0, 0, 1]))
    bot_rail = Timber(
        length=frame_width,
        size=Matrix([member_size, member_size]),
        transform=Transform(
            position=create_v3(inches(0), inches(0), member_size / 2),
            orientation=rail_orient,
        ),
        ticket=TimberTicket(path="bottom_rail"),
    )
    top_rail = Timber(
        length=frame_width,
        size=Matrix([member_size, member_size]),
        transform=Transform(
            position=create_v3(inches(0), inches(0), frame_height - member_size / 2),
            orientation=rail_orient,
        ),
        ticket=TimberTicket(path="top_rail"),
    )

    if board_orientation == "vertical":
        # Boards run in Z, stacked side-by-side in X.
        board_length = (inner_z_max - inner_z_min) + 2 * groove_depth
        board_width = (inner_x_max - inner_x_min + 2 * groove_depth) / n_boards
        x_start = inner_x_min - groove_depth  # left edge of leftmost board
        boards = [
            Board(
                length=board_length,
                size=Matrix([board_width, board_thickness]),
                transform=Transform(
                    position=create_v3(
                        x_start + board_width / 2 + board_width * i,
                        inches(0),
                        inner_z_min - groove_depth,
                    ),
                    orientation=Orientation.identity(),
                ),
                ticket=BoardTicket(path=f"board_{i + 1}"),
            )
            for i in range(n_boards)
        ]
        board_joint = cut_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
            boards=boards,
            board_bottom_end_timbers=[bot_rail],
            board_top_end_timbers=[top_rail],
            board_left_side_timbers=[left_stile],
            board_right_side_timbers=[right_stile],
            groove_extra_space=groove_extra,
        )
    else:
        # Boards run in X (local Z = global X), stacked in Z.
        # local X = global Z, so "left/right side" in the joint API = bottom/top rail.
        board_orient = Orientation.from_z_and_x(Matrix([1, 0, 0]), Matrix([0, 0, 1]))
        board_length = (inner_x_max - inner_x_min) + 2 * groove_depth
        board_width = (inner_z_max - inner_z_min + 2 * groove_depth) / n_boards
        z_start = inner_z_min - groove_depth  # bottom edge of lowest board
        boards = [
            Board(
                length=board_length,
                size=Matrix([board_width, board_thickness]),
                transform=Transform(
                    position=create_v3(
                        inner_x_min - groove_depth,
                        inches(0),
                        z_start + board_width / 2 + board_width * i,
                    ),
                    orientation=board_orient,
                ),
                ticket=BoardTicket(path=f"board_{i + 1}"),
            )
            for i in range(n_boards)
        ]
        board_joint = cut_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
            boards=boards,
            board_bottom_end_timbers=[left_stile],
            board_top_end_timbers=[right_stile],
            board_left_side_timbers=[bot_rail],
            board_right_side_timbers=[top_rail],
            groove_extra_space=groove_extra,
        )

    # Miter joints at the four frame corners.
    miter_bl = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=bot_rail, timber2=left_stile,
            timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM,
        )
    )
    miter_br = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=bot_rail, timber2=right_stile,
            timber1_end=TimberEnd.TOP, timber2_end=TimberEnd.BOTTOM,
        )
    )
    miter_tl = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=top_rail, timber2=left_stile,
            timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.TOP,
        )
    )
    miter_tr = cut_plain_miter_joint_on_face_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=top_rail, timber2=right_stile,
            timber1_end=TimberEnd.TOP, timber2_end=TimberEnd.TOP,
        )
    )

    return Frame.from_joints(
        [board_joint, miter_bl, miter_br, miter_tl, miter_tr],
        name="Board in Grooved Frame",
    )


patterns = [
    Pattern(path="board_joints/tongue_and_groove", lambda_=make_pattern_from_joint(example_tongue_and_groove), pattern_type='frame', tags=['main']),
    Pattern(path="board_joints/board_in_grooved_frame", lambda_=make_pattern_from_frame(example_board_in_grooved_frame), pattern_type='frame', tags=['main']),
]


if __name__ == "__main__":
    frame = example_board_in_grooved_frame()
    print(f"Frame: {frame.name}")
    print(f"Cut timbers: {len(frame.cut_timbers)}")
