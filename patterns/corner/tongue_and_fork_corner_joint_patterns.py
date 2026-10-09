"""
Tongue and Fork Corner Joint Patterns
"""

from kumiki import *
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


def make_tongue_and_fork_corner_joint_90_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a tongue-and-fork corner joint at 90 degrees using canonical right-angle timbers.
    """
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    joint = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(arrangement)
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_tongue_and_fork_corner_joint_135_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a tongue-and-fork corner joint at 135 degrees.
    """
    arrangement = create_canonical_example_corner_joint_timbers(
        corner_angle=degrees(scalar(135)),
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    joint = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(arrangement)
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


@pattern("corner_joints/tongue_and_fork_corner_joint/cut_tongue_and_fork_corner_joint_90")
def cut_tongue_and_fork_corner_joint_90_pattern() -> Frame:
    return Frame(cut_timbers=make_tongue_and_fork_corner_joint_90_example(create_v3(0, 0, 0)), name='Tongue and Fork Corner Joint 90°')


@pattern("corner_joints/tongue_and_fork_corner_joint/cut_tongue_and_fork_corner_joint_135")
def cut_tongue_and_fork_corner_joint_135_pattern() -> Frame:
    return Frame(cut_timbers=make_tongue_and_fork_corner_joint_135_example(create_v3(0, 0, 0)), name='Tongue and Fork Corner Joint 135°')
