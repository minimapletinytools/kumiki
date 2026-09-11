"""
Plain Butt Splice Joint Patterns
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


def make_splice_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a splice joint where two aligned timbers are joined end-to-end.
    Both timbers are cut at angles to create a scarf joint.
    Uses canonical splice joint arrangement.
    """
    arrangement = create_canonical_example_splice_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    timberA = replace(arrangement.timber1, ticket=TimberTicket("SpliceJoint_TimberA"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("SpliceJoint_TimberB"))

    splice_arrangement = SpliceJointTimberArrangement(
        timber1=timberA,
        timber2=timberB,
        timber1_end=arrangement.timber1_end,
        timber2_end=arrangement.timber2_end
    )
    joint = cut_plain_butt_splice_joint_on_aligned_timbers(
        splice_arrangement,
        splice_point=position
    )

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


patterns = [
    Pattern(path="splice_joints/plain_butt_splice_joint", lambda_=lambda center: Frame(cut_timbers=make_splice_joint_example(center), name="Plain Butt Splice Joint"), pattern_type='frame', tags=['main']),
]
