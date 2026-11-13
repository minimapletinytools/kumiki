# Last checked on kumiki 0.9.0
"""
Rebated Oblique and Dadoed Scarf Joint Patterns (Kanawa Tsugi / 金輪継ぎ)
"""

from typing import Optional

from kumiki import *

TIMBER_WIDTH = inches(4)
TIMBER_HEIGHT = inches(5)
TIMBER_LENGTH = inches(48)
TIMBER_SIZE_2D = create_v2(TIMBER_WIDTH, TIMBER_HEIGHT)


SCARF = kiwari(
    length=kiwari.length(inches(10), minimum=inches(4)),
    shoulder_depth=kiwari.length(inches(1), minimum=inches(1, 4)),
    dado_depth=kiwari.length(inches(1), minimum=inches(1, 4)),
    dado_height=kiwari.length(inches(3, 2), minimum=inches(1, 4)),
    tenon_width=kiwari.length(inches(3, 2), minimum=inches(1, 4)),
)


@pattern('splice/rebated_oblique_and_dadoed_scarf_joint', kiwari=SCARF)
def create_rebated_oblique_and_dadoed_scarf_example(k: Optional[Kiwari] = None, *, position: Optional[V3] = None) -> Frame:
    """
    Create a rebated oblique and dadoed scarf joint (Kanawa Tsugi
    style) example using two 4"x5"x4' timbers.
    """
    k = SCARF.resolve(k)
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
        rebated_shoulder_depth=k.length("shoulder_depth"),
        scarf_length=k.length("length"),
        dado_depth=k.length("dado_depth"),
        dado_height=k.length("dado_height"),
        stub_tenon_width=k.length("tenon_width"),
        joint_center_relative_to_timber1_end=overlap,
    )

    return Frame.from_joints(
        [joint],
        name="Rebated Oblique and Dadoed Scarf Joint",
    )
