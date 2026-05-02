"""
Japanese Joints Examples

This module demonstrates traditional Japanese timber joints:
- Lapped Gooseneck Joint (腰掛鎌継ぎ / Koshikake Kama Tsugi) - for splicing beams end-to-end
- Dovetail Butt Joint (蟻仕口 / Ari Shiguchi) - for connecting timbers at right angles
- Mitered and Keyed Lap Joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi) - for corner joints

Each function creates and returns a Frame object with the joint example.
"""

from typing import Optional
import sys
sys.path.append('..')

from sympy import Rational, Integer
from kumiki import *
from kumiki.ticket import TimberTicket
from kumiki.patternbook import PatternBook, PatternMetadata
from kumiki.example_shavings import (
    create_canonical_example_splice_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
)
from kumiki.rule import inches, degrees


def create_japanese_joints_patternbook() -> PatternBook:
    """
    Create a PatternBook with Japanese joint patterns.
    
    Each pattern has groups: ["japanese_joints", "{joint_type}"]
    
    Returns:
        PatternBook: PatternBook containing Japanese joint patterns
    """
    patterns = [
        (PatternMetadata("gooseneck_simple", ["japanese_joints", "gooseneck"], "frame"),
         lambda center: create_simple_gooseneck_example(position=center)),
        
        (PatternMetadata("dovetail_butt", ["japanese_joints", "dovetail"], "frame"),
         lambda center: create_dovetail_butt_joint_example(position=center)),
        
        (PatternMetadata("mitered_keyed_lap", ["japanese_joints", "miter"], "frame"),
         lambda center: create_mitered_and_keyed_lap_joint_example(position=center)),
        
        (PatternMetadata("mitered_keyed_lap_130deg", ["japanese_joints", "miter"], "frame"),
         lambda center: create_mitered_and_keyed_lap_joint_130deg_example(position=center)),
    ]
    
    return PatternBook(patterns=patterns)


patternbook = create_japanese_joints_patternbook()



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


def create_dovetail_butt_joint_example(position: Optional[V3] = None):
    """
    Create a dovetail butt joint (蟻仕口 / Ari Shiguchi) using canonical 4"x5"x4' timbers.
    
    This is a traditional Japanese joint where a dovetail-shaped tenon on one timber
    fits into a matching dovetail socket on another timber. The dovetail shape provides
    mechanical resistance to pulling apart.
    
    Configuration:
        - Uses canonical butt joint timbers (receiving along X, dovetail/butt along Y)
    
    Args:
        position: Center position of the joint (V3). Defaults to origin.
    """
    from dataclasses import replace

    arrangement = create_canonical_example_butt_joint_timbers(position=position)
    dovetail_timber = replace(arrangement.butt_timber, ticket=TimberTicket("dovetail_timber"))
    arrangement = replace(
        arrangement,
        butt_timber=dovetail_timber,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )

    joint = cut_housed_dovetail_butt_joint(
        arrangement=arrangement,
        receiving_timber_shoulder_inset=inches(Rational(1, 2)),  # 0.5" shoulder inset
        dovetail_length=inches(4),                                # 4" long dovetail tenon
        dovetail_small_width=inches(Rational(3, 2)),             # 1.5" narrow end
        dovetail_large_width=inches(3),                          # 3" wide end
        dovetail_lateral_offset=Rational(0),                     # Centered
        dovetail_depth=inches(Rational(5, 2))                    # 2.5" deep cut
    )
    
    # Create a frame from the joint
    frame = Frame.from_joints(
        [joint],
        name="Dovetail Butt Joint Example (蟻仕口 / Ari Shiguchi)"
    )
    
    return frame


def create_mitered_and_keyed_lap_joint_example(position: Optional[V3] = None):
    """
    Create a mitered and keyed lap joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)
    using canonical 4"x5"x4' timbers.
    
    This is a traditional Japanese corner joint that combines a miter joint with interlocking
    finger laps on the inside of the miter for additional mechanical strength. The fingers
    create a strong mechanical connection that resists both tension and shear forces.
    
    Configuration:
        - Creates a 90-degree corner joint
        - Uses interlocking finger laps inside the miter
        - Timbers meet at their bottom ends
    
    Args:
        position: Center position of the joint (V3). Defaults to origin.
    """
    # Create right-angle corner joint arrangement using canonical function
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)
    
    # Rename timbers for clarity in this joint context
    from dataclasses import replace
    timberA = replace(arrangement.timber1, ticket=TimberTicket("timber_A"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("timber_B"))
    arrangement = replace(
        arrangement,
        timber1=timberA,
        timber2=timberB,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )
    
    # Create the mitered and keyed lap joint
    # The reference miter face is the face that defines the miter plane (the face that will be visible after cutting)
    # For a 90-degree corner, both timbers have their RIGHT face pointing in the +Z direction
    joint = cut_mitered_and_keyed_lap_joint(
        arrangement=arrangement,
        num_laps=3,                                          # 3 interlocking fingers
        lap_thickness=inches(Rational(3, 4)),               # 0.75" thick fingers
        lap_start_distance_from_reference_miter_face=inches(Rational(1, 2)),  # Start 0.5" from miter face
        distance_between_lap_and_outside=inches(Rational(1, 2))  # 0.5" inset from outer edge
    )
    
    # Create a frame from the joint
    frame = Frame.from_joints(
        [joint],
        name="Mitered and Keyed Lap Joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)"
    )
    
    return frame


def create_mitered_and_keyed_lap_joint_130deg_example(position: Optional[V3] = None):
    """
    Create a mitered and keyed lap joint at 130 degrees using canonical 4"x5"x4' timbers.
    
    This demonstrates the same joint type as create_mitered_and_keyed_lap_joint_example,
    but at a 130-degree angle instead of 90 degrees. The interlocking finger laps work
    at any angle, providing mechanical strength for obtuse corner joints.
    
    Configuration:
        - Creates a 130-degree corner joint
        - Uses interlocking finger laps inside the miter
        - Timbers meet at their bottom ends
    
    Args:
        position: Center position of the joint (V3). Defaults to origin.
    """
    # Create corner joint arrangement with 130-degree angle (convert to radians)
    angle_130_rad = degrees(Integer(130))
    arrangement = create_canonical_example_corner_joint_timbers(corner_angle=angle_130_rad, position=position)
    
    # Rename timbers for clarity in this joint context
    from dataclasses import replace
    timberA = replace(arrangement.timber1, ticket=TimberTicket("timber_A"))
    timberB = replace(arrangement.timber2, ticket=TimberTicket("timber_B"))
    arrangement = replace(
        arrangement,
        timber1=timberA,
        timber2=timberB,
        front_face_on_timber1=TimberLongFace.RIGHT,
    )
    
    # Create the mitered and keyed lap joint
    # The reference miter face is the face that defines the miter plane
    # For a 130-degree corner, both timbers still have their RIGHT face pointing in the +Z direction
    joint = cut_mitered_and_keyed_lap_joint(
        arrangement=arrangement,
        num_laps=3,                                          # 3 interlocking fingers
        lap_thickness=inches(Rational(3, 4)),               # 0.75" thick fingers
        lap_start_distance_from_reference_miter_face=inches(Rational(1, 2)),  # Start 0.5" from miter face
        distance_between_lap_and_outside=inches(Rational(1, 2)), 
    )
    
    # Create a frame from the joint
    frame = Frame.from_joints(
        [joint],
        name="Mitered and Keyed Lap Joint - 130° (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)"
    )
    
    return frame


if __name__ == "__main__":
    print("Creating Japanese Joint Examples...")
    print("=" * 70)
    
    frames = []
    
    # TODO: Implement create_lapped_gooseneck_splice_example
    # print("\n1. Creating 4\"x4\" x 3' timber splice with lapped gooseneck joint...")
    # frame1 = create_lapped_gooseneck_splice_example()
    # frames.append(frame1)
    # print(f"   Frame created: {frame1.name}")
    # print(f"   Number of timbers: {len(frame1.cut_timbers)}")
    # for timber in frame1.cut_timbers:
    #     print(f"   - {timber.ticket.name}: {len(timber.cuts)} cut(s)")
    
    print("\n2. Creating simplified vertical post splice example...")
    frame2 = create_simple_gooseneck_example()
    frames.append(frame2)
    print(f"   Frame created: {frame2.name}")
    print(f"   Number of timbers: {len(frame2.cut_timbers)}")
    for cut_timber in frame2.cut_timbers:
        print(f"   - {cut_timber.timber.ticket.name}: {len(cut_timber.cuts)} cut(s)")
    
    print("\n3. Creating dovetail butt joint (T-joint) example...")
    frame3 = create_dovetail_butt_joint_example()
    frames.append(frame3)
    print(f"   Frame created: {frame3.name}")
    print(f"   Number of timbers: {len(frame3.cut_timbers)}")
    for cut_timber in frame3.cut_timbers:
        print(f"   - {cut_timber.timber.ticket.name}: {len(cut_timber.cuts)} cut(s)")
    
    print("\n4. Creating mitered and keyed lap joint (corner joint) example...")
    frame4 = create_mitered_and_keyed_lap_joint_example()
    frames.append(frame4)
    print(f"   Frame created: {frame4.name}")
    print(f"   Number of timbers: {len(frame4.cut_timbers)}")
    for cut_timber in frame4.cut_timbers:
        print(f"   - {cut_timber.timber.ticket.name}: {len(cut_timber.cuts)} cut(s)")
    
    print("\n5. Creating mitered and keyed lap joint (130-degree corner) example...")
    frame5 = create_mitered_and_keyed_lap_joint_130deg_example()
    frames.append(frame5)
    print(f"   Frame created: {frame5.name}")
    print(f"   Number of timbers: {len(frame5.cut_timbers)}")
    for cut_timber in frame5.cut_timbers:
        print(f"   - {cut_timber.timber.ticket.name}: {len(cut_timber.cuts)} cut(s)")
    
    print("\n" + "=" * 70)
    print("All examples created successfully!")
    print("\nTraditional Japanese Timber Joints:")
    print("  • Lapped Gooseneck Joint (腰掛鎌継ぎ / Koshikake Kama Tsugi)")
    print("    - Splices beams end-to-end")
    print("    - Gooseneck profile resists tension")
    print("    - Lap provides compression bearing")
    print("")
    print("  • Dovetail Butt Joint (蟻仕口 / Ari Shiguchi)")
    print("    - Connects timbers at right angles")
    print("    - Dovetail shape resists pulling apart")
    print("    - Used for T-joints and corner connections")
    print("")
    print("  • Mitered and Keyed Lap Joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)")
    print("    - Reinforced corner joint")
    print("    - Miter cut with interlocking finger laps")
    print("    - Resists tension, shear, and compression")
    print("")
    print(f"Total frames created: {len(frames)}")
