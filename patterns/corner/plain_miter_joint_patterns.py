"""
Plain Miter Joint Patterns
"""

from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
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


def make_miter_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a basic miter joint example with non-axis-aligned timbers.
    Two timbers meet at their ends with a miter cut, at 67 degrees apart.
    """
    arrangement = create_canonical_example_corner_joint_timbers(
        corner_angle=degrees(67),
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    timberA = replace(arrangement.timber1, ticket=TimberTicket("MiterJoint_TimberA"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("MiterJoint_TimberB"))
    miter_arrangement = CornerJointTimberArrangement(
        timber1=timberA,
        timber2=timberB,
        timber1_end=arrangement.timber1_end,
        timber2_end=arrangement.timber2_end
    )
    joint = cut_plain_miter_joint(miter_arrangement)
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_miter_joint_face_aligned_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a miter joint for face-aligned timbers.
    """
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    timberA = replace(arrangement.timber2, ticket=TimberTicket("MiterFaceAligned_TimberA"))
    timberB = replace(arrangement.timber1, ticket=TimberTicket("MiterFaceAligned_TimberB"))

    miter_arrangement = CornerJointTimberArrangement(
        timber1=timberA,
        timber2=timberB,
        timber1_end=TimberEnd.BOTTOM,
        timber2_end=TimberEnd.BOTTOM
    )
    joint = cut_plain_miter_joint_on_face_aligned_timbers(miter_arrangement)

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_miter_joint_3d_angles_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Miter joint with timbers at oblique 3D angles.
    """
    sqrt29 = sqrt(29)
    sqrt5 = sqrt(5)

    dirA = Matrix([scalar(4), scalar(0), scalar(3)]) / 5
    widthA = Matrix([scalar(0), scalar(1), scalar(0)])

    dirB = Matrix([scalar(2), scalar(4), scalar(3)]) / sqrt29
    widthB = Matrix([scalar(-2), scalar(1), scalar(0)]) / sqrt5

    timberA = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=dirA,
        width_direction=widthA,
        ticket=TimberTicket("MiterWeird_TimberA"),
    ), use_round_timbers)
    timberB = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=dirB,
        width_direction=widthB,
        ticket=TimberTicket("MiterWeird_TimberB"),
    ), use_round_timbers)

    arrangement = CornerJointTimberArrangement(
        timber1=timberA,
        timber2=timberB,
        timber1_end=TimberEnd.BOTTOM,
        timber2_end=TimberEnd.BOTTOM,
    )
    joint = cut_plain_miter_joint(arrangement)
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


patterns = [
    Pattern(path="corner_joints/plain_miter_joint/cut_plain_miter_joint", lambda_=lambda center: Frame(cut_timbers=make_miter_joint_example(center), name="Plain Miter Joint"), pattern_type='frame', tags=['main']),
    Pattern(path="corner_joints/plain_miter_joint/cut_plain_miter_joint_face_aligned", lambda_=lambda center: Frame(cut_timbers=make_miter_joint_face_aligned_example(center), name="Plain Miter Joint (Face Aligned)"), pattern_type='frame'),
    Pattern(path="corner_joints/plain_miter_joint/cut_plain_miter_joint_3d", lambda_=lambda center: Frame(cut_timbers=make_miter_joint_3d_angles_example(center), name="Plain Miter Joint (3D)"), pattern_type='frame'),
]
