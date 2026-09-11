"""
Plain Butt Joint Patterns
"""

from typing import Union, List, Optional
from dataclasses import replace

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


def make_butt_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a butt joint where one timber butts into another.
    The butt timber is cut square; the receiving timber is uncut.
    Uses canonical butt joint arrangement.

    Args:
        position: Center position of the joint (V3)

    Returns:
        List of CutTimber objects representing the joint
    """
    arrangement = create_canonical_example_butt_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    receiving_timber = replace(arrangement.receiving_timber, ticket=TimberTicket("ButtJoint_Receiving"))
    butt_timber = replace(arrangement.butt_timber, ticket=TimberTicket("ButtJoint_Butt"))

    butt_arrangement = ButtJointTimberArrangement(
        receiving_timber=receiving_timber,
        butt_timber=butt_timber,
        butt_timber_end=arrangement.butt_timber_end
    )
    joint = cut_plain_butt_joint_on_face_aligned_timbers(butt_arrangement)

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_butt_joint_3d_angles_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Butt joint with the butt timber approaching at an oblique 3D angle, meeting
    the receiving timber at mid-height.

    Receiving timber: vertical post along Z.
    Butt timber: direction (-2, 1, 1)/sqrt(6) — has significant X, Y, and Z components.
    The TOP end is positioned to meet the receiving post's right (+X) face at mid-height.
    """
    sqrt6 = sqrt(6)
    sqrt5 = sqrt(5)

    receiving = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=Matrix([scalar(0), scalar(0), scalar(1)]),
        width_direction=Matrix([scalar(1), scalar(0), scalar(0)]),
        ticket=TimberTicket("ButtWeird_Receiving"),
    ), use_round_timbers)

    dirB = Matrix([scalar(-2), scalar(1), scalar(1)]) / sqrt6
    widthB = Matrix([scalar(1), scalar(2), scalar(0)]) / sqrt5

    right_face_mid = position + Matrix([TIMBER_WIDTH / 2, scalar(0), TIMBER_LENGTH / 2])
    butt_bottom = right_face_mid - TIMBER_LENGTH * dirB

    butt = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=butt_bottom,
        length_direction=dirB,
        width_direction=widthB,
        ticket=TimberTicket("ButtWeird_Butt"),
    ), use_round_timbers)

    joint = cut_plain_butt_joint(ButtJointTimberArrangement(
        receiving_timber=receiving,
        butt_timber=butt,
        butt_timber_end=TimberEnd.TOP,
    ))
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


patterns = [
    Pattern(path="butt_joints/plain_butt_joint/plain_butt_joint", lambda_=_make_frame_pattern(make_butt_joint_example, "Plain Butt Joint"), pattern_type='frame'),
    Pattern(path="butt_joints/plain_butt_joint/plain_butt_joint_3d", lambda_=_make_frame_pattern(make_butt_joint_3d_angles_example, "Plain Butt Joint (3D)"), pattern_type='frame'),
]
