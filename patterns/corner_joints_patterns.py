"""
Corner Joints Patterns
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
from kumiki.patternbook import PatternBook, PatternMetadata, Pattern, make_pattern_from_frame

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



def make_miter_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a basic miter joint example with non-axis-aligned timbers.
    Two timbers meet at their ends with a miter cut, at 67 degrees apart.
    This demonstrates the general miter joint (non-face-aligned case).

    Args:
        position: Bottom position where the two timbers meet (V3)

    Returns:
        List of CutTimber objects representing the joint
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
    Similar to basic miter but specifically for face-aligned configurations.
    Uses canonical corner joint arrangement (timber1 in +Y, timber2 in +X).

    Args:
        position: Center position of the joint (V3)

    Returns:
        List of CutTimber objects representing the joint
    """
    # Get canonical corner joint timbers at position
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    # Rename timbers for clarity (timber2 is +X, timber1 is +Y)
    timberA = replace(arrangement.timber2, ticket=TimberTicket("MiterFaceAligned_TimberA"))  # +X direction
    timberB = replace(arrangement.timber1, ticket=TimberTicket("MiterFaceAligned_TimberB"))  # +Y direction

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

    TimberA runs at ~37° elevation in the XZ plane: direction (4, 0, 3)/5.
    TimberB runs with components in all three axes: direction (2, 4, 3)/sqrt(29).
    Neither timber is axis-aligned, demonstrating the general 3D case.
    """
    from sympy import sqrt

    sqrt29 = sqrt(29)
    sqrt5 = sqrt(5)

    # (4,0,3)/5 is a unit vector, elevation ~37° from horizontal in XZ plane
    dirA = Matrix([scalar(4), scalar(0), scalar(3)]) / 5
    widthA = Matrix([scalar(0), scalar(1), scalar(0)])  # perp to dirA since dirA has no Y component

    # (2,4,3)/sqrt(29) — has components in all 3 axes
    dirB = Matrix([scalar(2), scalar(4), scalar(3)]) / sqrt29
    # (-4,2,0)/sqrt(20) = (-2,1,0)/sqrt(5) is perpendicular to dirB: 2*(-2)+4*1+3*0 = 0
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


def make_corner_lap_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a corner lap joint where each corner timber gets a lap plus an end cut.
    """
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    joint = cut_plain_corner_lap_joint_on_plane_aligned_timbers(
        CornerJointTimberArrangement(
            timber1=arrangement.timber1,
            timber2=arrangement.timber2,
            timber1_end=arrangement.timber1_end,
            timber2_end=arrangement.timber2_end,
            front_face_on_timber1=None,
        ),
        cut_ratio=scalar(1, 2),
    )
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


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
    joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        num_laps=3,                                          # 3 interlocking fingers
        lap_thickness=inches(scalar(3, 4)),               # 0.75" thick fingers
        lap_start_distance_from_reference_miter_face=inches(scalar(1, 2)),  # Start 0.5" from miter face
        distance_between_lap_and_outside=inches(scalar(1, 2))  # 0.5" inset from outer edge
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
    angle_130_rad = degrees(scalar(130))
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
    joint = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        num_laps=3,                                          # 3 interlocking fingers
        lap_thickness=inches(scalar(3, 4)),               # 0.75" thick fingers
        lap_start_distance_from_reference_miter_face=inches(scalar(1, 2)),  # Start 0.5" from miter face
        distance_between_lap_and_outside=inches(scalar(1, 2)), 
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
    # print(f"   Number of timbers: {len(frame1.cuttings)}")
    # for timber in frame1.cuttings:
    #     print(f"   - {timber.ticket.path}: {len(timber.cuts)} cut(s)")
    
    print("\n2. Creating simplified vertical post splice example...")
    frame2 = create_simple_gooseneck_example()
    frames.append(frame2)
    print(f"   Frame created: {frame2.name}")
    print(f"   Number of timbers: {len(frame2.cuttings)}")
    for cut_timber in frame2.cuttings:
        print(f"   - {cut_timber.timber.ticket.path}: {len(cut_timber.cuts)} cut(s)")
    
    print("\n3. Creating dovetail butt joint (T-joint) example...")
    frame3 = create_dovetail_butt_joint_example()
    frames.append(frame3)
    print(f"   Frame created: {frame3.name}")
    print(f"   Number of timbers: {len(frame3.cuttings)}")
    for cut_timber in frame3.cuttings:
        print(f"   - {cut_timber.timber.ticket.path}: {len(cut_timber.cuts)} cut(s)")
    
    print("\n4. Creating mitered and keyed lap joint (corner joint) example...")
    frame4 = create_mitered_and_keyed_lap_joint_example()
    frames.append(frame4)
    print(f"   Frame created: {frame4.name}")
    print(f"   Number of timbers: {len(frame4.cuttings)}")
    for cut_timber in frame4.cuttings:
        print(f"   - {cut_timber.timber.ticket.path}: {len(cut_timber.cuts)} cut(s)")
    
    print("\n5. Creating mitered and keyed lap joint (130-degree corner) example...")
    frame5 = create_mitered_and_keyed_lap_joint_130deg_example()
    frames.append(frame5)
    print(f"   Frame created: {frame5.name}")
    print(f"   Number of timbers: {len(frame5.cuttings)}")
    for cut_timber in frame5.cuttings:
        print(f"   - {cut_timber.timber.ticket.path}: {len(cut_timber.cuts)} cut(s)")
    
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


def create_all_corner_joint_patterns(use_round_timbers=False) -> Frame:
    origin = create_v3(scalar(0), scalar(0), scalar(0))
    step = inches(24)
    all_timbers = []
    all_timbers += make_miter_joint_example(origin, use_round_timbers)
    all_timbers += make_miter_joint_face_aligned_example(origin + create_v3(step, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_miter_joint_3d_angles_example(origin + create_v3(step * 2, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_tongue_and_fork_corner_joint_90_example(origin + create_v3(step * 3, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_tongue_and_fork_corner_joint_135_example(origin + create_v3(step * 4, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_corner_lap_joint_example(origin + create_v3(step * 5, scalar(0), scalar(0)), use_round_timbers)
    return Frame(cut_timbers=all_timbers, name="Corner Joint Patterns")


patterns = [
    Pattern(path="corner_joints/plain_miter_joint/cut_plain_miter_joint", lambda_=lambda center: Frame(cut_timbers=make_miter_joint_example(center), name="Plain Miter Joint"), pattern_type='frame', tags=['main']),
    Pattern(path="corner_joints/plain_miter_joint/cut_plain_miter_joint_face_aligned", lambda_=lambda center: Frame(cut_timbers=make_miter_joint_face_aligned_example(center), name="Plain Miter Joint (Face Aligned)"), pattern_type='frame'),
    Pattern(path="corner_joints/plain_miter_joint/cut_plain_miter_joint_3d", lambda_=lambda center: Frame(cut_timbers=make_miter_joint_3d_angles_example(center), name="Plain Miter Joint (3D)"), pattern_type='frame'),
    Pattern(path="corner_joints/tongue_and_fork_corner_joint/cut_tongue_and_fork_corner_joint_90", lambda_=lambda center: Frame(cut_timbers=make_tongue_and_fork_corner_joint_90_example(center), name="Tongue and Fork Corner Joint 90°"), pattern_type='frame'),
    Pattern(path="corner_joints/tongue_and_fork_corner_joint/cut_tongue_and_fork_corner_joint_135", lambda_=lambda center: Frame(cut_timbers=make_tongue_and_fork_corner_joint_135_example(center), name="Tongue and Fork Corner Joint 135°"), pattern_type='frame'),
    Pattern(path="corner_joints/cut_plain_corner_lap_joint_on_plane_aligned_timbers", lambda_=lambda center: Frame(cut_timbers=make_corner_lap_joint_example(center), name="Plain Corner Lap Joint"), pattern_type='frame'),
    Pattern(path="corner_joints/mitered_and_keyed_lap_joint/cut_mitered_and_keyed_lap_joint_90", lambda_=make_pattern_from_frame(create_mitered_and_keyed_lap_joint_example), pattern_type='frame'),
    Pattern(path="corner_joints/mitered_and_keyed_lap_joint/cut_mitered_and_keyed_lap_joint_130", lambda_=make_pattern_from_frame(create_mitered_and_keyed_lap_joint_130deg_example), pattern_type='frame'),
]
