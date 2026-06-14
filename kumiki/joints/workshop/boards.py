


from typing import List, Tuple
from kumiki.timber import Board, TimberLike, Cutting, Joint, JointTicket
from kumiki.rule import Numeric, Rational, Integer, safe_dot_product, normalize_vector
from kumiki.cutcsg import RectangularPrism, Difference, adopt_csg
from kumiki.construction import Transform, Orientation
from kumiki.timber import TimberReferenceEnd, TimberFace
from sympy import Matrix


def cut_tongue_and_groove_joint(
    tongue_board: Board,
    groove_board: Board,
    tongue_depth: Numeric,
    tongue_width: Numeric,
    tongue_center_offset: Numeric = Rational(0),
    groove_extra_depth: Numeric = Rational(0),
) -> Joint:
    """
    Cuts a tongue and groove joint between two boards. The tongue and groove runs length-wise on the boards with tongue_depth in the X axis and tongue_width in the Y axis. hence the tongue and grooves are always on the left/right side faces of the board.
    
    The tongue is centered on the left or right side face of tongue_board and the X axis position of the tongue is such that the tip of the tongue lines up with the left or right side face of the tongue board.

    The side is determined by the position of the groove board, so if the groove board is to the left of the tongue board, the tongue will be cut on the left face of the tongue board and the groove will be cut on the right face of the groove board, and vice versa if the groove board is to the right of the tongue board.

    The groove on the groove board is aligned to the tongue.

    Please make sure groove board overlaps the tongue board enough so that enough wood can be removed to cut the groove, in particular it must overlap by at least tongue_depth.
    
    Args:
        tongue_board: Board with the protruding tongue on its left face.
        groove_board: Board with the recessed groove to accommodate the tongue.
        tongue_depth: Depth of the tongue in the X direction (how far it extends).
        tongue_width: Width of the tongue in the Y direction.
        tongue_center_offset: Offset of the tongue center from the board Y-axis center (default 0).
        groove_extra_depth: Extra depth to cut into the groove_board beyond tongue_depth.
    
    Returns:
        Joint object containing cuts for both boards.
    """
    
    # assert that the tongue and groove board have the same orientation
    # first check that the tongue board is wider than it is tall (X dimensio greater than Y) if it not, output a warning saynig "board orientatian apperas to be thicker than it is wide, are you sure you oriented your board correctly"
    # check that the groove board overlap the tongue board by at least tongue_depth, if not output a warning saying "groove board does not overlap tongue board enough to cut the groove"
    # check that the groove board thickness overlaps the tongue region, if not output a warning saying "groove board does not overlap tongue, groove may be incomplete"
    # if the groove board does not overlap in thickness at all with the tongue board, then throw an error saying "groove board does not overlap tongue board at all, cannot cut joint"

    # determine if the groove board is to the left or right of the tonue board, check the X position of the groove board centerline in local coordinates of the tongue board, if it is negative, then the groove board is to the left and the tongue should be cut on the left face of the tongue board and the groove should be cut on the right face of the groove board, and vice versa if it is positive.

    # next we cut the tongue on the tongue board on the side determined above.
    # go to the bottom end of the tongue board and find the face that the tongue should be cut on
    # next create a rectangular prism that represents the positive tongue cut, the prism should have the same length as the tongue board, a width of tongue_width, and a depth of tongue_depth, and is positioned such that the tip of the tongue lines up with the side face of the tongue board, and is centered on the Y axis of the tongue board with an offset of tongue_center_offset
    # this prism is just for reference, move the prism up/down by 1/2 the tongue width to get teh negatiev cuts for the tongue board
    # then expand the prism by groove_extra_depth towards the groove board to get teh negative cut for the groove board.
    


    pass

#def cut_board_in_groove_joint

#def cut_hazo_mizo_joint = cut_board_in_groove_joint

def cut_ita_kura_compound_joint(boards : List[Board], top_end_timbers : List[TimberLike], bottom_end_timbers : List[TimberLike], left_end_timbers : List[TimberLike], right_end_timbers : List[TimberLike], groove_depths : Tuple[Numeric, Numeric, Numeric, Numeric]):
    """
    fits boards in between the timbers using the board_in_groove_joint

    All boards must be coplanar, only the first board in the list is used to determine the size and position of the grooves
    
    The boards position are cut to the first timber in each list, and the groove is then extended into the other timbers in the list.
    """
    pass

