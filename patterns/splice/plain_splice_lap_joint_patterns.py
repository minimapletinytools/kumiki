"""
Plain Splice Lap Joint Patterns
"""

from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_splice_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import Pattern

TIMBER_WIDTH = inches(4)
TIMBER_HEIGHT = inches(5)
TIMBER_LENGTH = inches(48)
TIMBER_SIZE_2D = create_v2(TIMBER_WIDTH, TIMBER_HEIGHT)


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


def make_splice_lap_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a splice lap joint example.
    Two timbers meet end-to-end with interlocking lap relief cuts.
    """
    lap_length = TIMBER_WIDTH * 3

    arrangement = create_canonical_example_splice_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    timberA = replace(arrangement.timber1, ticket=TimberTicket("SpliceLap_TimberA"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("SpliceLap_TimberB"))

    splice_arrangement = replace(
        arrangement,
        timber1=timberA,
        timber2=timberB
    )

    joint = cut_plain_splice_lap_joint_on_aligned_timbers(
        arrangement=splice_arrangement,
        lap_length=lap_length,
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end=lap_length/2,
        lap_depth=None
    )

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


patterns = [
    Pattern(path="splice_joints/plain_splice_lap_joint", lambda_=lambda center: Frame(cut_timbers=make_splice_lap_joint_example(center), name="Plain Splice Lap Joint"), pattern_type='frame'),
]
