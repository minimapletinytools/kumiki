# Last checked on kumiki 0.9.0
"""Splice lap proportions and shoulder placement."""

from typing import Optional
from kumiki import *
from kumiki.example_shavings import create_canonical_example_splice_joint_timbers

LAP = kiwari(
    length=kiwari.length(inches(12), minimum=inches(1)),
    shoulder_position=kiwari.length(inches(6)),
    depth=kiwari.length(inches(2), minimum=inches(1, 4)),
)


@pattern("splice/plain_splice_lap_joint", kiwari=LAP)
def plain_splice_lap_joint_pattern(k: Optional[Kiwari] = None) -> Joint:
    k = LAP.resolve(k)
    return cut_plain_splice_lap_joint_on_aligned_timbers(
        create_canonical_example_splice_joint_timbers(),
        lap_length=k.length("length"),
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end=k.length("shoulder_position"),
        lap_depth=k.length("depth"))
