"""
Drop-in Housed Butt Joint Patterns (大入れ仕口 / Oire Shiguchi)
"""

from typing import Optional
from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.patternbook import Pattern, make_pattern_from_frame


def create_dropin_housed_butt_joint_example(position: Optional[V3] = None):
    """
    Create a drop-in housed butt joint using canonical 4"x5"x4' timbers.
    """
    arrangement = create_canonical_example_butt_joint_timbers(position=position)
    housed_timber = replace(arrangement.butt_timber, ticket=TimberTicket("housed_timber"))
    arrangement = replace(
        arrangement,
        butt_timber=housed_timber,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )

    joint = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        receiving_timber_shoulder_inset=inches(scalar(1, 2)),  # 0.5" shoulder inset
        housing_length=inches(4),                               # 4" long housing tenon
        housing_width=inches(3),                                # 3" wide housing pocket
        housing_lateral_offset=scalar(0),                       # Centered
        housing_depth=inches(scalar(5, 2))                      # 2.5" deep cut
    )
    
    frame = Frame.from_joints(
        [joint],
        name="Drop-in Housed Butt Joint Example (大入れ仕口 / Oire Shiguchi)"
    )
    
    return frame


patterns = [
    Pattern(path="butt_joints/cut_dropin_housed_butt_joint_on_face_aligned_timbers", lambda_=make_pattern_from_frame(create_dropin_housed_butt_joint_example), pattern_type='frame'),
]
