"""The names joints give their features, to find them again with `Joint.feature`."""


class MortiseAndTenonFeatures:
    """The features a mortise and tenon declares, on the tenon timber and on the mortise timber."""

    #: The tenon timber's shoulder plane, where the tenon leaves it.
    SHOULDER = "shoulder"
    TENON_RIGHT = "tenon_right"
    TENON_LEFT = "tenon_left"
    TENON_FRONT = "tenon_front"
    TENON_BACK = "tenon_back"
    #: The tenon's end, at the tenon timber's top end.
    TENON_TOP = "tenon_top"
    #: The tenon's end, at the tenon timber's bottom end.
    TENON_BOTTOM = "tenon_bot"
    TENON_CENTERPLANE_LEFT_RIGHT = "tenon_centerplane_left_right"
    TENON_CENTERPLANE_FRONT_BACK = "tenon_centerplane_front_back"
    #: The mortise's walls, named after the tenon faces they meet.
    MORTISE_RIGHT = "mortise_right"
    MORTISE_LEFT = "mortise_left"
    MORTISE_FRONT = "mortise_front"
    MORTISE_BACK = "mortise_back"
    #: A blind mortise's floor.
    MORTISE_BOTTOM = "mortise_bottom"
    #: Where a flared (wedged) mortise starts, on the shoulder side.
    MORTISE_ENTRY = "mortise_entry"
    #: Each peg hole's axis; one per peg, so `Joint.feature` takes an index. Round pegs only.
    PEG_HOLE_AXIS = "peg_hole_axis"
    #: A square peg hole's two centre planes, which cross on its axis; one of each per peg.
    PEG_HOLE_CENTERPLANE_LEFT_RIGHT = "peg_hole_centerplane_left_right"
    PEG_HOLE_CENTERPLANE_FRONT_BACK = "peg_hole_centerplane_front_back"
