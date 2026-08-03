"""Tongue-and-groove board joint example using PatternBook."""

from dataclasses import replace

from sympy import Matrix

from kumiki.joints.workshop.board_joints import (
    cut_practice_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers,
    cut_practice_sliding_dovetail_joint_on_orthogonal_boards,
    cut_tongue_and_groove_joint,
)
from kumiki.joints.workshop.corner_joints import cut_plain_miter_joint_on_face_aligned_timbers
from kumiki.construction import CornerJointTimberArrangement, ExtendedTimberArrangement, PanelBoardArrangement
from kumiki.example_shavings import (
    create_canonical_example_board_butt_joint_boards_side_to_face,
    create_canonical_example_board_butt_joint_boards_end_to_face,
)
from kumiki.patternbook import Pattern, make_pattern_from_joint, make_pattern_from_frame
from kumiki.rule import degrees, feet, inches
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
        board_joint = cut_practice_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
            boards=PanelBoardArrangement(boards=boards),
            frame_timbers=ExtendedTimberArrangement(timbers=[top_rail, bot_rail, left_stile, right_stile]),
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
        board_joint = cut_practice_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
            boards=PanelBoardArrangement(boards=boards),
            frame_timbers=ExtendedTimberArrangement(timbers=[right_stile, left_stile, bot_rail, top_rail]),
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


def _joint_with_ticket_prefix(joint, prefix: str):
    """Return a copy of `joint` with every timber's ticket path prefixed.

    Both canonical board butt-joint arrangements name their boards
    "butt_timber" / "receiving_timber", so combining two such joints into one
    Frame needs distinct names to avoid Frame.from_joints treating them as
    the same (differently-positioned) timber.
    """
    new_cuttings = {}
    for name, cutting in joint.cuttings.items():
        new_ticket = replace(cutting.timber.ticket, path=f"{prefix}{name}")
        new_timber = replace(cutting.timber, ticket=new_ticket)
        new_cuttings[new_ticket.path] = replace(cutting, timber=new_timber)
    return replace(joint, cuttings=new_cuttings)


def example_sliding_dovetail_boards() -> Frame:
    """Sliding dovetail joint demonstrated on both canonical board arrangements.

    side_to_face: butt_timber's RIGHT (side/edge) face dovetails into
    receiving_timber's FRONT (broad) face. Placed at the origin.

    end_to_face: butt_timber's TOP end dovetails into receiving_timber's FRONT
    face -- the classic shelf-end-into-case-side configuration. Placed
    alongside the first example (offset in X) so both render without
    overlapping.
    """
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
    Pattern(path="board_joints/board_in_grooved_frame", lambda_=make_pattern_from_frame(example_board_in_grooved_frame), pattern_type='frame', tags=['main']),
    Pattern(path="board_joints/sliding_dovetail", lambda_=make_pattern_from_frame(example_sliding_dovetail_boards), pattern_type='frame', tags=['main']),
]


if __name__ == "__main__":
    frame = example_board_in_grooved_frame()
    print(f"Frame: {frame.name}")
    print(f"Cut timbers: {len(frame.cut_timbers)}")
