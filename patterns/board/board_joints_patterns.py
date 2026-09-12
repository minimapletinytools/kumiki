"""Tongue-and-groove board joint example using PatternBook."""

from dataclasses import replace
from enum import Enum
from typing import Optional

from kumiki import *
from kumiki.construction import CornerJointTimberArrangement, ExtendedTimberArrangement, PanelBoardArrangement
from kumiki.example_shavings import (
    create_canonical_example_board_butt_joint_boards_side_to_face,
    create_canonical_example_board_butt_joint_boards_end_to_face,
)
from kumiki.patternbook import Pattern, make_pattern_from_joint, make_pattern_from_frame
from kumiki.rule import degrees, feet, inches, Matrix
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


class BoardOrientation(Enum):
    """Which way the boards run inside the frame."""
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


GROOVED_FRAME = kiwari(
    frame_width=kiwari.length(inches(24), minimum=inches(6), about="Outside width of the frame"),
    frame_height=kiwari.length(inches(40), minimum=inches(6), about="Outside height of the frame"),
    board_orientation=kiwari.choice(BoardOrientation, BoardOrientation.VERTICAL),
    n_boards=kiwari.count(4, minimum=1, maximum=20, about="How many boards fill the opening"),
)


def example_board_in_grooved_frame(k: Optional[Kiwari] = None) -> Frame:
    """Boards fitted into a grooved rectangular frame."""
    k = GROOVED_FRAME.resolve(k)
    frame_width = k.length("frame_width")
    frame_height = k.length("frame_height")
    board_orientation = k.choice("board_orientation", BoardOrientation)
    n_boards = k.count("n_boards")
    member_size = inches(2)
    board_thickness = inches(3, 4)
    groove_depth = inches(3, 8)

    inner_x_min = member_size
    inner_x_max = frame_width - member_size
    inner_z_min = member_size
    inner_z_max = frame_height - member_size

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

    if board_orientation is BoardOrientation.VERTICAL:
        board_length = (inner_z_max - inner_z_min) + 2 * groove_depth
        board_width = (inner_x_max - inner_x_min + 2 * groove_depth) / n_boards
        x_start = inner_x_min - groove_depth
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
        board_joint = cut_practice_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
            boards=PanelBoardArrangement(boards=boards),
            frame_timbers=ExtendedTimberArrangement(timbers=[top_rail, bot_rail, left_stile, right_stile]),
        )
    else:
        board_orient = Orientation.from_z_and_x(Matrix([1, 0, 0]), Matrix([0, 0, 1]))
        board_length = (inner_x_max - inner_x_min) + 2 * groove_depth
        board_width = (inner_z_max - inner_z_min + 2 * groove_depth) / n_boards
        z_start = inner_z_min - groove_depth
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
        board_joint = cut_practice_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
            boards=PanelBoardArrangement(boards=boards),
            frame_timbers=ExtendedTimberArrangement(timbers=[right_stile, left_stile, bot_rail, top_rail]),
        )

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


def _joint_with_ticket_prefix(joint, prefix: str):
    new_cuttings = {}
    for name, cutting in joint.cuttings.items():
        new_ticket = replace(cutting.timber.ticket, path=f"{prefix}{name}")
        new_timber = replace(cutting.timber, ticket=new_ticket)
        new_cuttings[new_ticket.path] = replace(cutting, timber=new_timber)
    return replace(joint, cuttings=new_cuttings)


def example_sliding_dovetail_boards() -> Frame:
    dovetail_depth = inches(1, 4)
    dovetail_small_width = inches(1, 2)
    dovetail_angle = degrees(80)

    side_to_face_arrangement = create_canonical_example_board_butt_joint_boards_side_to_face(
        position=create_v3(inches(0), inches(0), inches(0)),
    )
    side_to_face_joint = cut_practice_sliding_dovetail_joint_on_orthogonal_boards(
        side_to_face_arrangement,
        dovetail_depth=dovetail_depth,
        dovetail_small_width=dovetail_small_width,
        dovetail_angle=dovetail_angle,
    )

    end_to_face_arrangement = create_canonical_example_board_butt_joint_boards_end_to_face(
        position=create_v3(inches(24), inches(0), inches(0)),
    )
    end_to_face_joint = cut_practice_sliding_dovetail_joint_on_orthogonal_boards(
        end_to_face_arrangement,
        dovetail_depth=dovetail_depth,
        dovetail_small_width=dovetail_small_width,
        dovetail_angle=dovetail_angle,
        dovetail_length=inches(3),
        shorten_dovetail_by=inches(1),
        extend_front_dovetail_housing_by=inches(1, 2),
    )

    return Frame.from_joints(
        [
            _joint_with_ticket_prefix(side_to_face_joint, "side_to_face_"),
            _joint_with_ticket_prefix(end_to_face_joint, "end_to_face_"),
        ],
        name="Sliding Dovetail Boards",
    )


patterns = [
    Pattern(path="board_joints/tongue_and_groove", lambda_=make_pattern_from_joint(example_tongue_and_groove), pattern_type='frame', tags=['main']),
    Pattern(path="board_joints/board_in_grooved_frame", lambda_=make_pattern_from_frame(example_board_in_grooved_frame), kiwari=GROOVED_FRAME, pattern_type='frame', tags=['main']),
    Pattern(path="board_joints/sliding_dovetail", lambda_=make_pattern_from_frame(example_sliding_dovetail_boards), pattern_type='frame', tags=['main']),
]
