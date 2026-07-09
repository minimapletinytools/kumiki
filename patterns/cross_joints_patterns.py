"""
Cross Joints Patterns
"""

from sympy import Matrix, sqrt
from typing import Union, List, Optional
from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_splice_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import PatternBook, PatternMetadata, Pattern

# Standard timber dimensions (4" x 5", 4' long) - matches canonical examples
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



def make_house_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a housed joint (also called housing joint or dado joint).
    One timber (housing timber) gets a rectangular groove cut into it,
    and the other timber (housed timber) fits into that groove.

    This is commonly used for shelves fitting into uprights.

    Args:
        position: Center position of the joint (V3)

    Returns:
        List of CutTimber objects representing the joint
    """
    half_length = TIMBER_LENGTH / 2
    offset = TIMBER_HEIGHT / 2  # Offset by half the timber height

    # Housing timber (beam) extends in +X direction
    # This is the timber that gets the groove cut into it
    housing_timber = _maybe_round_timber(create_timber(
        ticket="HouseJoint_Housing",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([half_length, 0, 0]) + Matrix([0, 0, offset]),
        length_direction=Matrix([1, 0, 0]),
        width_direction=Matrix([0, 1, 0])
    ), use_round_timbers)

    # Housed timber (shelf) extends in +Y direction, crossing through the housing timber
    # This timber fits into the groove and remains uncut
    # Offset vertically so they intersect properly
    housed_timber = _maybe_round_timber(create_timber(
        ticket="HouseJoint_Housed",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([0, half_length, 0]) - Matrix([0, 0, offset]),
        length_direction=Matrix([0, 1, 0]),
        width_direction=Matrix([-1, 0, 0])
    ), use_round_timbers)

    # Create house joint
    house_arrangement = CrossJointTimberArrangement(
        timber1=housing_timber,
        timber2=housed_timber
    )
    joint = cut_plain_cross_lap_house_joint(house_arrangement)

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_cross_lap_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a cross lap joint where two timbers cross each other.
    Each timber has a relief cut halfway through (cut_ratio=0.5) so they fit together flush.
    TimberA is positioned lower, TimberB is positioned higher, and they overlap in the middle.

    Args:
        position: Center position of the joint (V3)

    Returns:
        List of CutTimber objects representing the joint
    """
    half_length = TIMBER_LENGTH / 2
    half_height = TIMBER_HEIGHT / 2

    # TimberA extends in +X direction, bottom at Z=0 (relative to position)
    # Height direction is +Z, so top face is at Z=TIMBER_HEIGHT
    timberA = _maybe_round_timber(create_timber(
        ticket="CrossLap_TimberA",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([half_length, 0, 0]),
        length_direction=Matrix([1, 0, 0]),
        width_direction=Matrix([0, 1, 0])  # Height direction becomes +Z
    ), use_round_timbers)

    # TimberB extends in +Y direction, bottom at Z=half_height (relative to position)
    # This creates an overlap from Z=half_height to Z=TIMBER_HEIGHT
    # Height direction is +Z, so top face is at Z=half_height+TIMBER_HEIGHT
    timberB = _maybe_round_timber(create_timber(
        ticket="CrossLap_TimberB",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([0, half_length, 0]) + Matrix([0, 0, half_height]),
        length_direction=Matrix([0, 1, 0]),
        width_direction=Matrix([-1, 0, 0])  # Height direction becomes +Z
    ), use_round_timbers)

    # Create cross lap joint with cut_ratio=0.5 (each timber cut halfway)
    joint = cut_plain_cross_lap_joint(
        CrossJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            front_face_on_timber1=TimberLongFace.FRONT,
        ),
        cut_ratio=scalar(1, 2),
    )

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]



def create_all_cross_joint_patterns(use_round_timbers=False) -> Frame:
    origin = create_v3(scalar(0), scalar(0), scalar(0))
    step = inches(24)
    all_timbers = []
    all_timbers += make_house_joint_example(origin, use_round_timbers)
    all_timbers += make_cross_lap_joint_example(origin + create_v3(step, scalar(0), scalar(0)), use_round_timbers)
    return Frame(cut_timbers=all_timbers, name="Cross Joint Patterns")


patterns = [
    Pattern(path="cross_joints/cut_plain_cross_lap_house_joint", lambda_=lambda center: Frame(cut_timbers=make_house_joint_example(center), name="Plain Cross Lap House Joint"), pattern_type='frame', tags=['main']),
    Pattern(path="cross_joints/cut_plain_cross_lap_joint", lambda_=lambda center: Frame(cut_timbers=make_cross_lap_joint_example(center), name="Plain Cross Lap Joint"), pattern_type='frame'),
]
