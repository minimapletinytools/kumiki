"""
Kumiki - Board joint construction functions
Contains functions for creating joints between boards.
"""

import warnings
from dataclasses import replace
from typing import Dict, List, Tuple

from sympy import Matrix

from kumiki.timber import AssemblyFreedom, Board, TimberLike, Cutting, Joint, JointTicket
from kumiki.rule import (
    Numeric,
    scalar,
    Comparison,
    safe_compare,
    equality_test,
)
from kumiki.cutcsg import RectangularPrism, SolidUnion, adopt_csg
from kumiki.construction import Transform, Orientation
from kumiki.timber_shavings import are_timbers_face_aligned


def cut_tongue_and_groove_joint(
    tongue_board: Board,
    groove_board: Board,
    tongue_depth: Numeric,
    tongue_width: Numeric,
    tongue_center_offset: Numeric = scalar(0),
    groove_extra_depth: Numeric = scalar(0),
) -> Joint:
    """
    Cuts a tongue and groove joint between two boards. The tongue and groove run
    length-wise on the boards with tongue_depth in the X axis and tongue_width
    in the Y axis; hence the tongue and grooves are always on the left/right
    side faces of the board.

    The tongue is centered on the left or right side face of tongue_board and
    the tip of the tongue lines up with that side face.

    The side is determined by the position of the groove board: if the groove
    board is to the left of the tongue board the tongue is cut on the left face
    of the tongue board and the groove is cut on the right face of the groove
    board, and vice versa.

    The groove on the groove board is aligned to the tongue.

    The groove board must overlap the tongue board by at least tongue_depth so
    enough wood is available to cut the groove.

    Args:
        tongue_board: Board with the protruding tongue on one of its side faces.
        groove_board: Board with the recessed groove that receives the tongue.
        tongue_depth: Depth of the tongue in the X direction.
        tongue_width: Width of the tongue in the Y direction.
        tongue_center_offset: Offset of the tongue center along the board Y axis (default 0).
        groove_extra_depth: Extra depth to cut into the groove board beyond tongue_depth.

    Returns:
        Joint with one Cutting per board, both labeled "tongue_and_groove".
    """

    # --- Same orientation between boards (element-wise on the rotation matrix) ---
    for r in range(3):
        for c in range(3):
            assert equality_test(
                tongue_board.transform.orientation.matrix[r, c],
                groove_board.transform.orientation.matrix[r, c],
            ), "tongue board and groove board must have the same orientation"

    # Warn if the tongue board appears thicker than wide (likely flipped).
    if not safe_compare(tongue_board.size[0] - tongue_board.size[1], 0, Comparison.GT):
        warnings.warn(
            "board orientation appears to be thicker than it is wide, "
            "are you sure you oriented your board correctly"
        )

    # --- Determine which side the groove board sits on, in tongue board local coords ---
    groove_pos_in_tongue_local = tongue_board.transform.global_to_local(
        groove_board.transform.position
    )
    groove_x_in_tongue_local = groove_pos_in_tongue_local[0]
    groove_y_in_tongue_local = groove_pos_in_tongue_local[1]

    tongue_half_width = tongue_board.size[0] / scalar(2)
    tongue_half_thickness = tongue_board.size[1] / scalar(2)
    groove_half_width = groove_board.size[0] / scalar(2)
    groove_half_thickness = groove_board.size[1] / scalar(2)

    # side_sign = -1 if groove board is to the LEFT of tongue board (tongue on LEFT face),
    # side_sign = +1 if groove board is to the RIGHT (tongue on RIGHT face).
    if safe_compare(groove_x_in_tongue_local, 0, Comparison.LT):
        side_sign = scalar(-1)
        x_overlap = (groove_x_in_tongue_local + groove_half_width) - (-tongue_half_width)
    else:
        side_sign = scalar(1)
        x_overlap = tongue_half_width - (groove_x_in_tongue_local - groove_half_width)

    if not safe_compare(x_overlap - tongue_depth, 0, Comparison.GE):
        warnings.warn(
            "groove board does not overlap tongue board enough to cut the groove"
        )

    # --- Thickness (Y) overlap checks ---
    tongue_y_low = tongue_center_offset - tongue_width / scalar(2)
    tongue_y_high = tongue_center_offset + tongue_width / scalar(2)

    groove_y_low = groove_y_in_tongue_local - groove_half_thickness
    groove_y_high = groove_y_in_tongue_local + groove_half_thickness

    tongue_board_y_low = -tongue_half_thickness
    tongue_board_y_high = tongue_half_thickness

    no_thickness_overlap = (
        safe_compare(groove_y_high - tongue_board_y_low, 0, Comparison.LE)
        or safe_compare(groove_y_low - tongue_board_y_high, 0, Comparison.GE)
    )
    assert not no_thickness_overlap, (
        "groove board does not overlap tongue board at all, cannot cut joint"
    )

    if safe_compare(groove_y_low - tongue_y_low, 0, Comparison.GT) or safe_compare(
        tongue_y_high - groove_y_high, 0, Comparison.GT
    ):
        warnings.warn(
            "groove board does not overlap tongue, groove may be incomplete"
        )

    # --- Cut tongue on the tongue board ---
    # Reference tongue prism (positive tongue volume) in tongue board local coords:
    #   X: from side face inward by tongue_depth
    #   Y: centered at tongue_center_offset with height tongue_width
    #   Z: 0 .. tongue_board.length
    face_x = side_sign * tongue_half_width
    inside_x = face_x - side_sign * tongue_depth
    ref_x_center = (face_x + inside_x) / scalar(2)
    ref_x_size = tongue_depth

    # Top negative cut: covers the region above the tongue, up to the board's top face.
    top_neg_y_low = tongue_y_high
    top_neg_y_high = tongue_board_y_high
    top_neg_y_size = top_neg_y_high - top_neg_y_low
    top_neg_y_center = (top_neg_y_low + top_neg_y_high) / scalar(2)

    top_neg_prism = RectangularPrism(
        size=Matrix([ref_x_size, top_neg_y_size]),
        transform=Transform(
            position=Matrix([ref_x_center, top_neg_y_center, scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=tongue_board.length,
        label="tongue_top_remove",
    )

    # Bottom negative cut: mirror of top.
    bot_neg_y_low = tongue_board_y_low
    bot_neg_y_high = tongue_y_low
    bot_neg_y_size = bot_neg_y_high - bot_neg_y_low
    bot_neg_y_center = (bot_neg_y_low + bot_neg_y_high) / scalar(2)

    bot_neg_prism = RectangularPrism(
        size=Matrix([ref_x_size, bot_neg_y_size]),
        transform=Transform(
            position=Matrix([ref_x_center, bot_neg_y_center, scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=tongue_board.length,
        label="tongue_bottom_remove",
    )

    tongue_neg_csg = SolidUnion(
        children=[top_neg_prism, bot_neg_prism],
        label="tongue_and_groove",
    )

    tongue_cutting = Cutting(
        timber=tongue_board,
        negative_csg=tongue_neg_csg,
        label="tongue_and_groove",
    )

    # --- Cut groove on the groove board ---
    # Convert the tongue positive prism (centered at ref_x_center,
    # tongue_center_offset in tongue board local coords) into groove board local
    # coords so the groove sits exactly where the tongue is, then extend it
    # deeper into the groove board by groove_extra_depth.
    tongue_prism_center_tongue_local = Matrix(
        [ref_x_center, tongue_center_offset, scalar(0)]
    )
    tongue_prism_center_global = tongue_board.transform.local_to_global(
        tongue_prism_center_tongue_local
    )
    tongue_prism_center_groove_local = groove_board.transform.global_to_local(
        tongue_prism_center_global
    )

    # Boards share orientation, so the X axis matches in both local frames.
    # Deeper into the groove board (away from the tongue board) is the +side_sign
    # direction in groove local X.
    groove_x_size = tongue_depth + groove_extra_depth
    groove_x_center = (
        tongue_prism_center_groove_local[0]
        + side_sign * groove_extra_depth / scalar(2)
    )
    groove_y_center = tongue_prism_center_groove_local[1]
    groove_y_size = tongue_width

    groove_prism = RectangularPrism(
        size=Matrix([groove_x_size, groove_y_size]),
        transform=Transform(
            position=Matrix([groove_x_center, groove_y_center, scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=groove_board.length,
        label="groove",
    )

    # Trim the overhanging lip of the groove board: cut full thickness and full
    # length from the outer face (the one facing the tongue board) up to where
    # the groove starts (the mouth of the cavity). This removes the material
    # that would otherwise intersect the tongue board.
    groove_outer_face_x = -side_sign * groove_half_width
    groove_mouth_x = (
        tongue_prism_center_groove_local[0]
        - side_sign * tongue_depth / scalar(2)
    )
    trim_x_center = (groove_outer_face_x + groove_mouth_x) / scalar(2)
    trim_x_size = side_sign * (groove_mouth_x - groove_outer_face_x)

    trim_prism = RectangularPrism(
        size=Matrix([trim_x_size, groove_board.size[1]]),
        transform=Transform(
            position=Matrix([trim_x_center, scalar(0), scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=groove_board.length,
        label="groove_excess_trim",
    )

    groove_neg_csg = SolidUnion(
        children=[groove_prism, trim_prism],
        label="tongue_and_groove",
    )

    groove_cutting = Cutting(
        timber=groove_board,
        negative_csg=groove_neg_csg,
        label="tongue_and_groove",
    )

    # Assembly: the boards part along the mating axis (tongue pulls out of the
    # groove after tongue_depth of travel) and can also slide freely along the
    # board length (free after the full board length).
    groove_local_x_global = groove_board.get_width_direction_global()
    tongue_escape_direction = groove_local_x_global * (-side_sign)
    length_direction_global = tongue_board.get_length_direction_global()
    tongue_cutting = replace(
        tongue_cutting,
        assembly_freedom=AssemblyFreedom.combine(
            AssemblyFreedom.translation(tongue_escape_direction, freed_after=tongue_depth),
            AssemblyFreedom.bidirectional_translation(length_direction_global, freed_after=tongue_board.length),
        ),
    )
    groove_cutting = replace(
        groove_cutting,
        assembly_freedom=AssemblyFreedom.combine(
            AssemblyFreedom.translation(-tongue_escape_direction, freed_after=tongue_depth),
            AssemblyFreedom.bidirectional_translation(length_direction_global, freed_after=groove_board.length),
        ),
    )

    return Joint(
        cuttings={
            tongue_board.ticket.path: tongue_cutting,
            groove_board.ticket.path: groove_cutting,
        },
        ticket=JointTicket(joint_type="tongue_and_groove"),
    )


def cut_board_in_grooved_rectangular_frame_joint(boards: List[Board], board_top_end_timbers: List[TimberLike], board_bottom_end_timbers: List[TimberLike], board_left_side_timbers: List[TimberLike], board_right_side_timbers: List[TimberLike], groove_extra_space: Numeric = scalar(0)):
    """
    fits boards in between the timbers using the board_in_groove_joint

    All timbers must be face aligned and in particluar form a rectangular frame around the boards

    The groove position and depths are based on the boards so the boards are expected to be positioned and sized to where they will fit, in particular no cuts are made on the boards.

    The boards are all expected to be the same thickness and coplanar and form a "rectangle" shape.

    TODO add an optional maybe_end_cut_boards_to_groove_depth parameter. If provided the boards are extended with end cuts to fit into the grooves on the board_top/bottom_end_timbers

    Args:
        boards: A list of boards to be fitted into the grooves
        board_top_end_timbers: A list of timbers that will have grooves cut to receive the "top" end of the boards
        board_bottom_end_timbers: A list of timbers that will have grooves cut to receive the "bottom" end of the boards
        board_left_side_timbers: A list of timbers that will have grooves cut to receive the "left" side of the boards
        board_right_side_timbers: A list of timbers that will have grooves cut to receive the "right" side of the boards
        groove_extra_space: Extra space to add to the groove depth beyond the board thickness, to allow for easier fitting of the boards into the grooves
    """
     
    assert boards, "boards must not be empty"

    ref = boards[0]
    board_thickness = ref.size[1]

    # Assert all boards have the same orientation matrix and thickness.
    for i, b in enumerate(boards[1:], start=1):
        for r in range(3):
            for c in range(3):
                assert equality_test(
                    b.transform.orientation.matrix[r, c],
                    ref.transform.orientation.matrix[r, c],
                ), (
                    f"all boards must have the same orientation "
                    f"(board {i} differs from board 0 at [{r},{c}])"
                )
        assert equality_test(b.size[1], board_thickness), (
            f"all boards must have the same thickness "
            f"(board {i} has {b.size[1]}, board 0 has {board_thickness})"
        )

    # Assert all frame timbers are face-aligned with the boards.
    all_frame_timbers: List[TimberLike] = (
        board_top_end_timbers
        + board_bottom_end_timbers
        + board_left_side_timbers
        + board_right_side_timbers
    )
    for t in all_frame_timbers:
        assert are_timbers_face_aligned(t, ref), (
            f"all frame timbers must be face-aligned with the boards, "
            f"but timber '{t.ticket.path}' is not"
        )

    # Compute the bounding box of all boards in the reference board's local frame.
    # Board local: X = width, Y = thickness, Z = length.
    # board.transform.position is the bottom center (at Z=0 in board local).
    min_x: Numeric
    max_x: Numeric
    min_y: Numeric
    max_y: Numeric
    min_z: Numeric
    max_z: Numeric

    # Seed from the reference board (always at local origin).
    min_x = -ref.size[0] / scalar(2)
    max_x =  ref.size[0] / scalar(2)
    min_y = -board_thickness / scalar(2)
    max_y =  board_thickness / scalar(2)
    min_z =  scalar(0)
    max_z =  ref.length

    for i, b in enumerate(boards[1:], start=1):
        pos_in_ref_local = ref.transform.global_to_local(b.transform.position)
        # Coplanar assertion: Y offset of board bottom in ref local frame must be zero.
        assert equality_test(pos_in_ref_local[1], scalar(0)), (
            f"board {i} is not coplanar with board 0 "
            f"(Y offset = {pos_in_ref_local[1]} in ref local frame)"
        )
        x_lo = pos_in_ref_local[0] - b.size[0] / scalar(2)
        x_hi = pos_in_ref_local[0] + b.size[0] / scalar(2)
        z_lo = pos_in_ref_local[2]
        z_hi = pos_in_ref_local[2] + b.length
        min_x = min(min_x, x_lo)
        max_x = max(max_x, x_hi)
        min_z = min(min_z, z_lo)
        max_z = max(max_z, z_hi)

    x_center = (min_x + max_x) / scalar(2)
    y_center = (min_y + max_y) / scalar(2)  # = 0 for coplanar boards
    x_size   = max_x - min_x
    y_size   = (max_y - min_y) + groove_extra_space
    z_span   = max_z - min_z

    # Build the groove prism in the reference board's local coordinate frame.
    # Subtracting this volume from each frame timber cuts the groove that receives
    # the board panel edges.
    groove_prism_ref_local = RectangularPrism(
        size=Matrix([x_size, y_size]),
        transform=Transform(
            position=Matrix([x_center, y_center, min_z]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=z_span,
        label="board_groove",
    )

    # Re-express the groove prism in each frame timber's local coordinate frame
    # and build a Cutting for each timber.
    cuttings: Dict[str, Cutting] = {}
    for timber in all_frame_timbers:
        groove_in_timber_local = adopt_csg(
            ref.transform, timber.transform, groove_prism_ref_local
        )
        cuttings[timber.ticket.path] = Cutting(
            timber=timber,
            negative_csg=groove_in_timber_local,
            label="board_in_grooved_frame",
        )

    # Include boards as uncut members so the returned joint can form a complete frame.
    for board in boards:
        cuttings[board.ticket.path] = Cutting(
            timber=board,
            negative_csg=None,
            label="board_in_grooved_frame",
        )

    # Assembly: no freedoms are set — a panel captured in a 4-sided grooved
    # frame is fully constrained once assembled (the frame must be built
    # around it); there is no single-translation escape to express. The
    # connections are treated as rigid.
    return Joint(
        cuttings=cuttings,
        ticket=JointTicket(joint_type="board_in_grooved_frame"),
    )
