"""
Mitered and Keyed Lap Joint Patterns (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)
"""

from typing import Optional
from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import (
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
)
from kumiki.patternbook import Pattern, make_pattern_from_frame


def create_mitered_and_keyed_lap_joint_example(position: Optional[V3] = None):
    """
    Create a mitered and keyed lap joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)
    using canonical 4"x5"x4' timbers at 90 degrees.
    """
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)
    
    timberA = replace(arrangement.timber1, ticket=TimberTicket("timber_A"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("timber_B"))
    arrangement = replace(
        arrangement,
        timber1=timberA,
        timber2=timberB,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )
    
    joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        num_laps=3,
        lap_thickness=inches(scalar(3, 4)),
        lap_start_distance_from_reference_miter_face=inches(scalar(1, 2)),
        distance_between_lap_and_outside=inches(scalar(1, 2)),
    )
    
    frame = Frame.from_joints(
        [joint],
        name="Mitered and Keyed Lap Joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)"
    )
    
    return frame


def create_mitered_and_keyed_lap_joint_130deg_example(position: Optional[V3] = None):
    """
    Create a mitered and keyed lap joint at 130 degrees using canonical 4"x5"x4' timbers.
    """
    angle_130_rad = degrees(scalar(130))
    arrangement = create_canonical_example_corner_joint_timbers(corner_angle=angle_130_rad, position=position)
    
    timberA = replace(arrangement.timber1, ticket=TimberTicket("timber_A"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("timber_B"))
    arrangement = replace(
        arrangement,
        timber1=timberA,
        timber2=timberB,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )
    
    joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        num_laps=3,
        lap_thickness=inches(scalar(3, 4)),
        lap_start_distance_from_reference_miter_face=inches(scalar(1, 2)),
        distance_between_lap_and_outside=inches(scalar(1, 2)),
    )
    
    frame = Frame.from_joints(
        [joint],
        name="Mitered and Keyed Lap Joint - 130° (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)"
    )
    
    return frame


patterns = [
    Pattern(path="corner_joints/mitered_and_keyed_lap_joint/cut_mitered_and_keyed_lap_joint_90", lambda_=make_pattern_from_frame(create_mitered_and_keyed_lap_joint_example), pattern_type='frame'),
    Pattern(path="corner_joints/mitered_and_keyed_lap_joint/cut_mitered_and_keyed_lap_joint_130", lambda_=make_pattern_from_frame(create_mitered_and_keyed_lap_joint_130deg_example), pattern_type='frame'),
]
