# Last checked on kumiki 0.9.0
"""
Lapped Gooseneck Joint Patterns (腰掛鎌継ぎ / Koshikake Kama Tsugi)
"""

from typing import Optional
from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import create_canonical_example_splice_joint_timbers


OPTIONS = kiwari(
    gooseneck_length=kiwari.length(inches(6)),
    gooseneck_small_width=kiwari.length(inches(1)),
    gooseneck_large_width=kiwari.length(inches(3)),
    gooseneck_head_length=kiwari.length(inches(2)),
    lap_length=kiwari.length(inches(3)),
    gooseneck_depth=kiwari.length(inches(2)),
)


@pattern('splice/lapped_gooseneck_splice_joint', kiwari=OPTIONS)
def create_simple_gooseneck_example(k: Optional[Kiwari] = None, *, position: Optional[V3]=None) -> Frame:
    """
    Create a gooseneck splice joint example using canonical 4"x5"x4' timbers.
    """
    k = OPTIONS.resolve(k)
    arrangement = create_canonical_example_splice_joint_timbers(position=position)

    gooseneck_timber = replace(arrangement.timber1, ticket=TimberTicket("gooseneck_timber"))
    receiving_timber = replace(arrangement.timber2, ticket=TimberTicket("receiving_timber"))
    arrangement = replace(
        arrangement,
        timber1=gooseneck_timber,
        timber2=receiving_timber,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )

    joint = cut_lapped_gooseneck_joint_on_aligned_timbers(
        arrangement=arrangement,
        gooseneck_length=k.length("gooseneck_length"),
        gooseneck_small_width=k.length("gooseneck_small_width"),
        gooseneck_large_width=k.length("gooseneck_large_width"),
        gooseneck_head_length=k.length("gooseneck_head_length"),
        lap_length=k.length("lap_length"),
        gooseneck_depth=k.length("gooseneck_depth"),
    )

    frame = Frame.from_joints(
        [joint],
        name="Lapped Gooseneck Splice Joint"
    )

    return frame
