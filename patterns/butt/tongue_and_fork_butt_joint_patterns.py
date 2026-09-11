"""
Tongue and Fork Butt Joint Patterns
"""

from typing import Union, List, Optional

from kumiki import *
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_butt_joint_timbers,
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


def _maybe_round_timber(timber, use_round_timbers: bool):
    if not use_round_timbers:
        return timber
    return RoundTimber(
        length=timber.length,
        size=timber.size,
        transform=timber.transform,
        ticket=timber.ticket,
        diameter=max(timber.size[0], timber.size[1]) * sqrt(2),
    )


def _make_frame_pattern(pattern_func, name: str):
    return lambda center, use_round_timbers=False: Frame(
        cut_timbers=pattern_func(center, use_round_timbers=use_round_timbers),
        name=name,
    )


def make_tongue_and_fork_butt_joint_90_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a tongue-and-fork butt joint at 90 degrees using canonical butt joint timbers.
    """
    arrangement = create_canonical_example_butt_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement, shoulder_inset = inches(1))
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_tongue_and_fork_butt_joint_angled_inset_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a tongue-and-fork butt joint at 138 degrees.
    The butt (tongue) timber approaches the receiving (fork) timber at an angle.
    """
    angle = degrees(138)
    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))

    receiving_bottom = position + create_v3(-TIMBER_LENGTH / scalar(2), scalar(0), scalar(0))
    receiving_timber = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=receiving_bottom,
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="receiving_timber",
    ), use_round_timbers)

    butt_length_direction = create_v3(sin(angle), cos(angle), scalar(0))
    butt_timber = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=butt_length_direction,
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="butt_timber",
    ), use_round_timbers)

    arrangement = ButtJointTimberArrangement(
        butt_timber=butt_timber,
        receiving_timber=receiving_timber,
        butt_timber_end=TimberEnd.BOTTOM,
    )
    joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement, shoulder_inset = inches(1))
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_tongue_and_fork_butt_joint_angled_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a tongue-and-fork butt joint at 138 degrees, shoulder flush with the receiving
    (fork) timber's entry face (no inset).
    """
    angle = degrees(138)
    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))

    receiving_bottom = position + create_v3(-TIMBER_LENGTH / scalar(2), scalar(0), scalar(0))
    receiving_timber = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=receiving_bottom,
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="receiving_timber",
    ), use_round_timbers)

    butt_length_direction = create_v3(sin(angle), cos(angle), scalar(0))
    butt_timber = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=butt_length_direction,
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="butt_timber",
    ), use_round_timbers)

    arrangement = ButtJointTimberArrangement(
        butt_timber=butt_timber,
        receiving_timber=receiving_timber,
        butt_timber_end=TimberEnd.BOTTOM,
    )
    joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement)
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


patterns = [
    Pattern(path="butt_joints/tongue_and_fork/tongue_and_fork_butt_joint_90", lambda_=_make_frame_pattern(make_tongue_and_fork_butt_joint_90_example, "Tongue and Fork Butt Joint 90°"), pattern_type='frame', tags=['main']),
    Pattern(path="butt_joints/tongue_and_fork/tongue_and_fork_butt_joint_angled", lambda_=_make_frame_pattern(make_tongue_and_fork_butt_joint_angled_example, "Tongue and Fork Butt Joint (Angled)"), pattern_type='frame'),
    Pattern(path="butt_joints/tongue_and_fork/tongue_and_fork_butt_joint_angled_inset", lambda_=_make_frame_pattern(make_tongue_and_fork_butt_joint_angled_inset_example, "Tongue and Fork Butt Joint (Angled + Inset)"), pattern_type='frame'),
]
