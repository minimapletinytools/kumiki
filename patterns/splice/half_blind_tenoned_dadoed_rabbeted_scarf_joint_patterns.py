"""
Rebated Oblique and Dadoed Scarf Joint Patterns (Kanawa Tsugi / 金輪継ぎ)
"""

from typing import Optional

from kumiki import *
from kumiki.patternbook import Pattern, make_pattern_from_frame

TIMBER_WIDTH = inches(4)
TIMBER_HEIGHT = inches(5)
TIMBER_LENGTH = inches(48)
TIMBER_SIZE_2D = create_v2(TIMBER_WIDTH, TIMBER_HEIGHT)


def create_rebated_oblique_and_dadoed_scarf_example(position: Optional[V3] = None):
    """
    Create a rebated oblique and dadoed scarf joint (Kanawa Tsugi
    style) example using two 4"x5"x4' timbers.
    """
    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))

    overlap = inches(8)

    timber1 = create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position + create_v3(-TIMBER_LENGTH + overlap, scalar(0), scalar(0)),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="scarf_timber1",
    )
    timber2 = create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position + create_v3(-overlap, scalar(0), scalar(0)),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="scarf_timber2",
    )

    arrangement = SpliceJointTimberArrangement(
        timber1=timber1,
        timber2=timber2,
        timber1_end=TimberEnd.TOP,
        timber2_end=TimberEnd.BOTTOM,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )

    joint = cut_rebated_oblique_and_dadoed_scarf_joint_on_aligned_timbers(
        arrangement=arrangement,
        rebated_shoulder_depth=inches(1),
        scarf_length=inches(10),
        dado_depth=inches(1),
        dado_height=inches(1.5),
        stub_tenon_width=inches(1.5),
        joint_center_relative_to_timber1_end=overlap,
    )

    return Frame.from_joints(
        [joint],
        name="Rebated Oblique and Dadoed Scarf Joint",
    )


create_half_blind_tenoned_dadoed_rabbeted_scarf_example = create_rebated_oblique_and_dadoed_scarf_example


patterns = [
    Pattern(path="splice_joints/rebated_oblique_and_dadoed_scarf_joint", lambda_=make_pattern_from_frame(create_rebated_oblique_and_dadoed_scarf_example), pattern_type='frame'),
    Pattern(path="splice_joints/half_blind_tenoned_dadoed_rabbeted_scarf_joint", lambda_=make_pattern_from_frame(create_half_blind_tenoned_dadoed_rabbeted_scarf_example), pattern_type='frame'),
]
