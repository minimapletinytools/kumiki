"""
Drop-in Dovetail Butt Joint Patterns (蟻仕口 / Ari Shiguchi)
"""

from typing import Optional
from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_butt_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import Pattern, make_pattern_from_frame


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


def create_dovetail_butt_joint_example(position: Optional[V3] = None, use_round_timbers=False):
    """
    Create a dovetail butt joint (蟻仕口 / Ari Shiguchi) using canonical 4"x5"x4' timbers.
    """
    arrangement = create_canonical_example_butt_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    dovetail_timber = replace(arrangement.butt_timber, ticket=TimberTicket("dovetail_timber"))
    arrangement = replace(
        arrangement,
        butt_timber=dovetail_timber,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )

    joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        receiving_timber_shoulder_inset=inches(scalar(1, 2)),  # 0.5" shoulder inset
        dovetail_length=inches(4),                                # 4" long dovetail tenon
        dovetail_small_width=inches(scalar(3, 2)),             # 1.5" narrow end
        dovetail_large_width=inches(3),                          # 3" wide end
        dovetail_lateral_offset=scalar(0),                     # Centered
        dovetail_depth=inches(scalar(5, 2))                    # 2.5" deep cut
    )
    
    frame = Frame.from_joints(
        [joint],
        name="Dovetail Butt Joint Example (蟻仕口 / Ari Shiguchi)"
    )
    
    return frame


patterns = [
    Pattern(path="butt_joints/cut_dropin_dovetail_butt_joint_on_face_aligned_timbers", lambda_=make_pattern_from_frame(create_dovetail_butt_joint_example), pattern_type='frame'),
]
