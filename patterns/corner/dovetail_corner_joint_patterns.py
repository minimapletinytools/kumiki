# Last checked on kumiki 0.9.0
"""Through and half-blind dovetail corners."""

from typing import Optional
from kumiki import *
from kumiki.example_shavings import create_canonical_example_right_angle_corner_joint_timbers

DOVETAIL = kiwari(
    small_width=kiwari.length(inches(1, 2), minimum=inches(1, 8)),
    angle=kiwari.angle(atan(scalar(1, 8))),
    first_distance=kiwari.length(inches(1)),
    spacing=kiwari.length(inches(2)),
)
HALF_BLIND = kiwari(**dict(DOVETAIL.declarations), depth=kiwari.length(inches(5, 2)))


def _dovetail(k: Kiwari, depth: Optional[Numeric]) -> Joint:
    return cut_dovetail_corner_joint(
        create_canonical_example_right_angle_corner_joint_timbers(),
        distances=[k.length("first_distance"), k.length("spacing")],
        dovetails=[SingleDovetailSizeParameter(
            angle=k.angle("angle"), small_width=k.length("small_width"), depth=depth)
            for _ in range(2)])


@pattern("corner/dovetail_corner_joint/through", kiwari=DOVETAIL)
def through(k: Optional[Kiwari] = None) -> Joint:
    return _dovetail(DOVETAIL.resolve(k), None)


@pattern("corner/dovetail_corner_joint/half_blind", kiwari=HALF_BLIND)
def half_blind(k: Optional[Kiwari] = None) -> Joint:
    k = HALF_BLIND.resolve(k)
    return _dovetail(k, k.length("depth"))
