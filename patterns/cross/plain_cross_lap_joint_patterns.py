"""
Plain Cross Lap Joint Patterns
"""

from kumiki import *
from kumiki.patternbook import Pattern

TIMBER_WIDTH = inches(4)
TIMBER_HEIGHT = inches(5)
TIMBER_LENGTH = inches(48)
TIMBER_SIZE_2D = create_v2(TIMBER_WIDTH, TIMBER_HEIGHT)


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


def make_house_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a housed joint (housing / dado joint).
    One timber (housing timber) gets a rectangular groove cut into it,
    and the other timber (housed timber) fits into that groove.
    """
    half_length = TIMBER_LENGTH / 2
    offset = TIMBER_HEIGHT / 2

    housing_timber = _maybe_round_timber(create_timber(
        ticket="HouseJoint_Housing",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([half_length, 0, 0]) + Matrix([0, 0, offset]),
        length_direction=Matrix([1, 0, 0]),
        width_direction=Matrix([0, 1, 0])
    ), use_round_timbers)

    housed_timber = _maybe_round_timber(create_timber(
        ticket="HouseJoint_Housed",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([0, half_length, 0]) - Matrix([0, 0, offset]),
        length_direction=Matrix([0, 1, 0]),
        width_direction=Matrix([-1, 0, 0])
    ), use_round_timbers)

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
    """
    half_length = TIMBER_LENGTH / 2
    half_height = TIMBER_HEIGHT / 2

    timberA = _maybe_round_timber(create_timber(
        ticket="CrossLap_TimberA",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([half_length, 0, 0]),
        length_direction=Matrix([1, 0, 0]),
        width_direction=Matrix([0, 1, 0])
    ), use_round_timbers)

    timberB = _maybe_round_timber(create_timber(
        ticket="CrossLap_TimberB",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([0, half_length, 0]) + Matrix([0, 0, half_height]),
        length_direction=Matrix([0, 1, 0]),
        width_direction=Matrix([-1, 0, 0])
    ), use_round_timbers)

    joint = cut_plain_cross_lap_joint(
        CrossJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            front_face_on_timber1=TimberLongFace.FRONT,
        ),
        cut_ratio=scalar(1, 2),
    )

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


patterns = [
    Pattern(path="cross_joints/cut_plain_cross_lap_house_joint", lambda_=lambda center: Frame(cut_timbers=make_house_joint_example(center), name="Plain Cross Lap House Joint"), pattern_type='frame', tags=['main']),
    Pattern(path="cross_joints/cut_plain_cross_lap_joint", lambda_=lambda center: Frame(cut_timbers=make_cross_lap_joint_example(center), name="Plain Cross Lap Joint"), pattern_type='frame'),
]
