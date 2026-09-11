"""
Plain Corner Lap Joint Patterns
"""

from kumiki import *
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_right_angle_corner_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import Pattern


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


def make_corner_lap_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a corner lap joint where each corner timber gets a lap plus an end cut.
    """
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    joint = cut_plain_corner_lap_joint_on_plane_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=arrangement.timber1,
            timber2=arrangement.timber2,
            timber1_end=arrangement.timber1_end,
            timber2_end=arrangement.timber2_end,
            front_face_on_timber1=None,
        ),
        cut_ratio=scalar(1, 2),
    )
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


patterns = [
    Pattern(path="corner_joints/cut_plain_corner_lap_joint_on_plane_aligned_timbers", lambda_=lambda center: Frame(cut_timbers=make_corner_lap_joint_example(center), name="Plain Corner Lap Joint"), pattern_type='frame'),
]
