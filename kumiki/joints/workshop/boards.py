
import warnings
from typing import List, Tuple

from sympy import Matrix

from kumiki.timber import Board, TimberLike, Cutting, Joint, JointTicket
from kumiki.rule import (
    Numeric,
    Rational,
    Integer,
    Comparison,
    safe_compare,
    equality_test,
)
from kumiki.cutcsg import RectangularPrism, SolidUnion
from kumiki.construction import Transform, Orientation


def cut_tongue_and_groove_joint(
    tongue_board: Board,
    groove_board: Board,
    tongue_depth: Numeric,
    tongue_width: Numeric,
    tongue_center_offset: Numeric = Rational(0),
    groove_extra_depth: Numeric = Rational(0),
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

    tongue_half_width = tongue_board.size[0] / Integer(2)
    tongue_half_thickness = tongue_board.size[1] / Integer(2)
    groove_half_width = groove_board.size[0] / Integer(2)
    groove_half_thickness = groove_board.size[1] / Integer(2)

    # side_sign = -1 if groove board is to the LEFT of tongue board (tongue on LEFT face),
    # side_sign = +1 if groove board is to the RIGHT (tongue on RIGHT face).
    if safe_compare(groove_x_in_tongue_local, 0, Comparison.LT):
        side_sign = Integer(-1)
        x_overlap = (groove_x_in_tongue_local + groove_half_width) - (-tongue_half_width)
    else:
        side_sign = Integer(1)
        x_overlap = tongue_half_width - (groove_x_in_tongue_local - groove_half_width)

    if not safe_compare(x_overlap - tongue_depth, 0, Comparison.GE):
        warnings.warn(
            "groove board does not overlap tongue board enough to cut the groove"
        )

    # --- Thickness (Y) overlap checks ---
    tongue_y_low = tongue_center_offset - tongue_width / Integer(2)
    tongue_y_high = tongue_center_offset + tongue_width / Integer(2)

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
    ref_x_center = (face_x + inside_x) / Integer(2)
    ref_x_size = tongue_depth

    # Top negative cut: covers the region above the tongue, up to the board's top face.
    top_neg_y_low = tongue_y_high
    top_neg_y_high = tongue_board_y_high
    top_neg_y_size = top_neg_y_high - top_neg_y_low
    top_neg_y_center = (top_neg_y_low + top_neg_y_high) / Integer(2)

    top_neg_prism = RectangularPrism(
        size=Matrix([ref_x_size, top_neg_y_size]),
        transform=Transform(
            position=Matrix([ref_x_center, top_neg_y_center, Integer(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=Integer(0),
        end_distance=tongue_board.length,
        label="tongue_top_remove",
    )

    # Bottom negative cut: mirror of top.
    bot_neg_y_low = tongue_board_y_low
    bot_neg_y_high = tongue_y_low
    bot_neg_y_size = bot_neg_y_high - bot_neg_y_low
    bot_neg_y_center = (bot_neg_y_low + bot_neg_y_high) / Integer(2)

    bot_neg_prism = RectangularPrism(
        size=Matrix([ref_x_size, bot_neg_y_size]),
        transform=Transform(
            position=Matrix([ref_x_center, bot_neg_y_center, Integer(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=Integer(0),
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
        [ref_x_center, tongue_center_offset, Integer(0)]
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
        + side_sign * groove_extra_depth / Integer(2)
    )
    groove_y_center = tongue_prism_center_groove_local[1]
    groove_y_size = tongue_width

    groove_prism = RectangularPrism(
        size=Matrix([groove_x_size, groove_y_size]),
        transform=Transform(
            position=Matrix([groove_x_center, groove_y_center, Integer(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=Integer(0),
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
        - side_sign * tongue_depth / Integer(2)
    )
    trim_x_center = (groove_outer_face_x + groove_mouth_x) / Integer(2)
    trim_x_size = side_sign * (groove_mouth_x - groove_outer_face_x)

    trim_prism = RectangularPrism(
        size=Matrix([trim_x_size, groove_board.size[1]]),
        transform=Transform(
            position=Matrix([trim_x_center, Integer(0), Integer(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=Integer(0),
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

    return Joint(
        cuttings={
            tongue_board.ticket.name: tongue_cutting,
            groove_board.ticket.name: groove_cutting,
        },
        ticket=JointTicket(joint_type="tongue_and_groove"),
    )

#def cut_board_in_groove_joint

#def cut_hazo_mizo_joint = cut_board_in_groove_joint

def cut_ita_kura_compound_joint(boards : List[Board], top_end_timbers : List[TimberLike], bottom_end_timbers : List[TimberLike], left_end_timbers : List[TimberLike], right_end_timbers : List[TimberLike], groove_depths : Tuple[Numeric, Numeric, Numeric, Numeric]):
    """
    fits boards in between the timbers using the board_in_groove_joint

    All boards must be coplanar, only the first board in the list is used to determine the size and position of the grooves
    
    The boards position are cut to the first timber in each list, and the groove is then extended into the other timbers in the list.
    """
    pass

