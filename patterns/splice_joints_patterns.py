"""
Splice Joints Patterns
"""

from sympy import Matrix, Rational, sqrt
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
from kumiki.patternbook import PatternBook, PatternMetadata

# Standard timber dimensions (4" x 5", 4' long) - matches canonical examples
TIMBER_WIDTH = inches(4)
TIMBER_HEIGHT = inches(5)
TIMBER_LENGTH = inches(48)
TIMBER_SIZE_2D = create_v2(TIMBER_WIDTH, TIMBER_HEIGHT)

from kumiki.joints.workshop.splice_joints import cut_lapped_gooseneck_joint

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



def make_splice_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a splice joint where two aligned timbers are joined end-to-end.
    Both timbers are cut at angles to create a scarf joint.
    Uses canonical splice joint arrangement.

    Args:
        position: Center position of the joint (V3)

    Returns:
        List of CutTimber objects representing the joint
    """
    # Get canonical splice joint timbers at position
    arrangement = create_canonical_example_splice_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    # Rename timbers for clarity
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
        splice_point=position  # Meet at the specified position
    )

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_splice_lap_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a splice lap joint example.
    Two timbers meet end-to-end with interlocking lap notches.

    Args:
        position: Center position of the joint (V3)

    Returns:
        List of CutTimber objects representing the joint
    """
    lap_length = TIMBER_WIDTH * 3  # Lap extends 3x the timber width

    # Use canonical splice joint arrangement
    # This creates two aligned timbers meeting at 'position'
    arrangement = create_canonical_example_splice_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    # Rename timbers for clarity
    timberA = replace(arrangement.timber1, ticket=TimberTicket("SpliceLap_TimberA"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("SpliceLap_TimberB"))

    # Update arrangement
    splice_arrangement = replace(
        arrangement,
        timber1=timberA,
        timber2=timberB
    )

    joint = cut_plain_splice_lap_joint_on_aligned_timbers(
        arrangement=splice_arrangement,
        lap_length=lap_length,
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end=lap_length/2,
        lap_depth=None  # Use default (half thickness)
    )

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def create_simple_gooseneck_example(position: Optional[V3] = None):
    """
    Create a gooseneck splice joint example using canonical 4"x5"x4' timbers.
    
    Args:
        position: Center position of the joint (V3). Defaults to origin.
    """
    # Create splice joint arrangement using canonical function
    # This creates two horizontal timbers meeting end-to-end
    arrangement = create_canonical_example_splice_joint_timbers(position=position)
    
    # Rename timbers for clarity in this joint context
    from dataclasses import replace
    gooseneck_timber = replace(arrangement.timber1, ticket=TimberTicket("gooseneck_timber"))
    receiving_timber = replace(arrangement.timber2, ticket=TimberTicket("receiving_timber"))
    arrangement = replace(
        arrangement,
        timber1=gooseneck_timber,
        timber2=receiving_timber,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )

    # Create the gooseneck joint using parameters appropriate for canonical timber size
    joint = cut_lapped_gooseneck_joint(
        arrangement=arrangement,
        gooseneck_length=inches(6),        # 6" gooseneck length
        gooseneck_small_width=inches(1),   # 1" narrow end
        gooseneck_large_width=inches(3),   # 3" wide end
        gooseneck_head_length=inches(2),   # 2" head length
        lap_length=inches(3),              # 3" lap length
        gooseneck_depth=inches(2)          # 2" depth
    )
    
    frame = Frame.from_joints(
        [joint],
        name="Lapped Gooseneck Splice Joint"
    )
    
    return frame



def create_all_splice_joint_patterns(use_round_timbers=False) -> Frame:
    origin = create_v3(Integer(0), Integer(0), Integer(0))
    step = inches(24)
    all_timbers = []
    all_timbers += make_splice_joint_example(origin, use_round_timbers)
    all_timbers += make_splice_lap_joint_example(origin + create_v3(step, Integer(0), Integer(0)), use_round_timbers)
    return Frame(cut_timbers=all_timbers, name="Splice Joint Patterns")


example = create_all_splice_joint_patterns
