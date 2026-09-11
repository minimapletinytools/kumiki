"""
Lapped Gooseneck Joint Patterns (腰掛鎌継ぎ / Koshikake Kama Tsugi)
"""

from typing import Optional
from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import create_canonical_example_splice_joint_timbers
from kumiki.patternbook import Pattern, make_pattern_from_frame


def create_simple_gooseneck_example(position: Optional[V3] = None):
    """
    Create a gooseneck splice joint example using canonical 4"x5"x4' timbers.
    """
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
        gooseneck_length=inches(6),
        gooseneck_small_width=inches(1),
        gooseneck_large_width=inches(3),
        gooseneck_head_length=inches(2),
        lap_length=inches(3),
        gooseneck_depth=inches(2),
    )
    
    frame = Frame.from_joints(
        [joint],
        name="Lapped Gooseneck Splice Joint"
    )
    
    return frame


patterns = [
    Pattern(path="splice_joints/lapped_gooseneck_splice_joint", lambda_=make_pattern_from_frame(create_simple_gooseneck_example), pattern_type='frame'),
]
