# Last checked on kumiki 0.9.0
"""
Drop-in Dovetail Butt Joint Patterns (蟻仕口 / Ari Shiguchi)
"""

from typing import Optional
from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import (
    ROUND_STOCK,
    RoundTimberConfig,
    create_canonical_example_butt_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


OPTIONS = kiwari(
    round_timbers=kiwari.flag(False),
    receiving_timber_shoulder_inset=kiwari.length(inches(scalar(1, 2))),
    dovetail_length=kiwari.length(inches(4)),
    dovetail_small_width=kiwari.length(inches(scalar(3, 2))),
    dovetail_angle=kiwari.angle(atan(scalar(3, 16))),
    dovetail_lateral_offset=kiwari.length(scalar(0)),
    dovetail_depth=kiwari.length(inches(scalar(5, 2))),
)


@pattern('butt/cut_dropin_dovetail_butt_joint_on_face_aligned_timbers', kiwari=OPTIONS)
def create_dovetail_butt_joint_example(k: Optional[Kiwari]=None, *, position: Optional[V3]=None) -> Frame:
    """
    Create a dovetail butt joint (蟻仕口 / Ari Shiguchi) using canonical 4"x5"x4' timbers.
    """
    k = OPTIONS.resolve(k)
    use_round_timbers = k.flag("round_timbers")
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
        receiving_timber_shoulder_inset=k.length("receiving_timber_shoulder_inset"),
        dovetail_length=k.length("dovetail_length"),
        dovetail_small_width=k.length("dovetail_small_width"),
        dovetail_angle=k.angle("dovetail_angle"),
        dovetail_lateral_offset=k.length("dovetail_lateral_offset"),
        dovetail_depth=k.length("dovetail_depth")
    )

    frame = Frame.from_joints(
        [joint],
        name="Dovetail Butt Joint Example (蟻仕口 / Ari Shiguchi)"
    )

    return frame
