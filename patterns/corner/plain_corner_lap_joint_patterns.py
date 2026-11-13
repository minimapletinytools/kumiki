# Last checked on kumiki 0.9.0
"""Orthogonal and angled corner laps with adjustable cut proportions."""

from typing import Optional
from kumiki import *
from kumiki.example_shavings import create_canonical_example_corner_joint_timbers

LAP = kiwari(cut_ratio=kiwari.number(scalar(1, 2), minimum=0.1, maximum=0.9))


def _corner_lap(k: Kiwari, angle: Numeric) -> Joint:
    arrangement = create_canonical_example_corner_joint_timbers(corner_angle=angle)
    return cut_plain_corner_lap_joint_on_plane_aligned_timbers(arrangement, cut_ratio=k.number("cut_ratio"))


@pattern("corner/plain_corner_lap_joint/orthogonal", kiwari=LAP)
def orthogonal(k: Optional[Kiwari] = None) -> Joint:
    return _corner_lap(LAP.resolve(k), degrees(90))


@pattern("corner/plain_corner_lap_joint/angled", kiwari=LAP)
def angled(k: Optional[Kiwari] = None) -> Joint:
    return _corner_lap(LAP.resolve(k), degrees(120))
