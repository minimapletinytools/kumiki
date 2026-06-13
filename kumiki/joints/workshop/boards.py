


# TODO

def cut_tongue_and_groove_joint(tongue_board : Board, groove_board : Board, tongue_depth : Numeric, tongue_width : Numeric, tongue_center_offset : Numeric = 0, groove_extra_depth : Numeric = 0):
    """
    Cuts a tongue and groove joint between two boards. The tongue and groove runs length-wise on the boards with tongue_depth in the X axis and tongue_width in the Y axis. hence the tongue and grooves are always on the left/right side faces of the board.
    
    The tongue is centered on the left side face of tongue_board and the X axis position of the tongue is such that the tip of the tongue lines up with the left side face of the tongue board.

    The groove is aligned to the tongue.

    Please make sure groove board overlaps the tongue board enough so that enough wood can be removed to cut the groove, in particular it must overlap by at least tongue_depth.
    """
    # TODO
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