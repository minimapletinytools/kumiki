# Last checked on kumiki 0.9.0
"""Three-member cross-lap chain with adjustable cut boundaries."""

from typing import Optional
from kumiki import *

CHAIN = kiwari(
    first_boundary=kiwari.number(scalar(1, 3), minimum=0.1, maximum=0.45),
    second_boundary=kiwari.number(scalar(2, 3), minimum=0.55, maximum=0.9),
    spacing=kiwari.length(inches(3), minimum=inches(1), maximum=inches(3)),
)


@pattern("cross/multi_cross_lap_joint", kiwari=CHAIN)
def multi_cross_lap(k: Optional[Kiwari] = None) -> Joint:
    k = CHAIN.resolve(k)
    timber_size = create_v2(inches(6), inches(4))
    length = inches(20)
    first = create_timber(length=length, size=timber_size,
        bottom_position=create_v3(-length / 2, 0, inches(3)),
        length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 0, 1), ticket="first")
    middle = create_timber(length=length, size=timber_size,
        bottom_position=create_v3(0, -length / 2, inches(3)),
        length_direction=create_v3(0, 1, 0), width_direction=create_v3(0, 0, 1), ticket="middle")
    last = create_timber(length=length, size=timber_size,
        bottom_position=create_v3(-length / 2, k.length("spacing"), inches(3)),
        length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 0, 1), ticket="last")
    return cut_multi_cross_lap_joint_on_plane_aligned_timbers(
        [first, middle, last], TimberFace.LEFT,
        cut_distance_ratios=[k.number("first_boundary"), k.number("second_boundary")])
