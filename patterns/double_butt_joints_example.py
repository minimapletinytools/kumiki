"""
Double Butt Joints Examples - Demonstration of double butt joint types in Kumiki

This file contains one example function for each double butt joint type.
Each joint is created from 4"x5" timbers that are 4' long.
"""

from sympy import Rational
from typing import Union

from kumiki.rule import V3, create_v3
from kumiki.timber import *
from kumiki.joints.double_butt_joints import cut_splined_opposing_double_butt_joint
from kumiki.joints.build_a_butt_joint_shavings import SimplePegParameters
from kumiki.example_shavings import create_canonical_example_opposing_double_butt_joint_timbers
from kumiki.patternbook import PatternBook, PatternMetadata


def make_splined_opposing_double_butt_joint_example(position: V3) -> Frame:
    """
    Create a splined opposing double butt joint example.

    Two butt timbers approach a receiving timber (post) from opposite directions.
    Returns a Frame containing all three cut timbers and the spline accessory.

    Args:
        position: Center position of the joint (V3)
    """
    arrangement = create_canonical_example_opposing_double_butt_joint_timbers(position=position)
    joint = cut_splined_opposing_double_butt_joint(arrangement = arrangement,
        slot_facing_end_on_receiving_timber = TimberReferenceEnd.TOP,
        # thickness is in the axis perpendicular to the joint plane
        slot_thickness=inches(1),
        # depth is in the axis of the receiving timber, measured from the face of the butt timber that alines with slot_facing_end_on_receiving_timber
        slot_depth=inches(2),
        # length is in the axis parallel to the butt timbers
        spline_length=inches(12),
        # the spline has this much extra depth beyond the slot depth
        spline_extra_depth=inches(1/2),
        # the slot extends this much beyond the spline on each end so that there is clearance 
        slot_symmetric_extra_length=inches(1/4),
        # inset the shoulder plane on both sides by this amount, flush with faces of receiving timber if 0
        shoulder_symmetric_inset=inches(1),
        # offset the solt by this much, measured relative to receiving timber centerline and in the axis perpendicular to the joint plane and 
        slot_lateral_offset=inches(0),
        # one 15 mm square peg, 30 mm from shoulder
        peg_parameters=SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[(mm(30), Rational(0))],
            size=mm(15),
        ),
    )
    return Frame.from_joints([joint], name="Splined Opposing Double Butt Joint")


def create_double_butt_joints_patternbook() -> PatternBook:
    """
    Create a PatternBook with all double butt joint patterns.

    Returns:
        PatternBook containing all double butt joint patterns
    """
    patterns = [
        (PatternMetadata("splined_opposing_double_butt_joint", ["double_butt_joints", "splined_opposing"], "frame"),
         lambda center: make_splined_opposing_double_butt_joint_example(center)),
    ]

    return PatternBook(patterns=patterns)


patternbook = create_double_butt_joints_patternbook()


def create_all_double_butt_joint_examples() -> Union[Frame]:
    """
    Create double butt joint examples with automatic spacing starting from the origin.

    Returns:
        Frame object containing all cut timbers
    """
    book = create_double_butt_joints_patternbook()
    frame = book.raise_pattern_group("double_butt_joints", separation_distance=Rational(2))
    return frame


example = create_all_double_butt_joint_examples
