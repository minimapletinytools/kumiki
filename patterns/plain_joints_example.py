"""
Plain Joints Examples - Demonstration of all plain joint types in Kumiki

This file contains one example function for each plain joint type.
Each joint is created from 4"x5" timbers that are 4' long,
axis-aligned with one timber going in +Y and another in +X direction.
"""

from sympy import Matrix, Rational
from typing import Union, List
from dataclasses import replace

from kumiki.rule import inches, degrees, create_v2, create_v3, V3
from kumiki.ticket import TimberTicket
from kumiki.construction import (
    CornerJointTimberArrangement,
    ButtJointTimberArrangement,
    SpliceJointTimberArrangement,
    CrossJointTimberArrangement,
)
from kumiki.timber import (
    TimberReferenceEnd,
    TimberFace,
    TimberLongFace,
    timber_from_directions,
    CutTimber,
    Frame,
)
from kumiki.joints.plain_joints import (
    cut_plain_miter_joint,
    cut_plain_miter_joint_on_face_aligned_timbers,
    cut_plain_butt_joint_on_face_aligned_timbers,
    cut_tongue_and_fork_corner_joint,
    cut_tongue_and_fork_butt_joint,
    cut_plain_butt_splice_joint_on_aligned_timbers,
    cut_plain_cross_lap_joint,
    cut_plain_house_joint,
    cut_plain_splice_lap_joint_on_aligned_timbers,
)
from kumiki.example_shavings import (
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_splice_joint_timbers,
)
from kumiki.patternbook import PatternBook, PatternMetadata

# Standard timber dimensions (4" x 5", 4' long) - matches canonical examples
TIMBER_WIDTH = inches(4)   # 4"
TIMBER_HEIGHT = inches(5)  # 5"
TIMBER_LENGTH = inches(48)  # 4 feet = 48"
TIMBER_SIZE_2D = create_v2(TIMBER_WIDTH, TIMBER_HEIGHT)


def make_miter_joint_example(position: V3) -> list[CutTimber]:
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
    return list(joint.cut_timbers.values())


def make_miter_joint_face_aligned_example(position: V3) -> list[CutTimber]:
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
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)

    # Rename timbers for clarity (timber2 is +X, timber1 is +Y)
    timberA = replace(arrangement.timber2, ticket=TimberTicket("MiterFaceAligned_TimberA"))  # +X direction
    timberB = replace(arrangement.timber1, ticket=TimberTicket("MiterFaceAligned_TimberB"))  # +Y direction

    miter_arrangement = CornerJointTimberArrangement(
        timber1=timberA,
        timber2=timberB,
        timber1_end=TimberReferenceEnd.BOTTOM,
        timber2_end=TimberReferenceEnd.BOTTOM
    )
    joint = cut_plain_miter_joint_on_face_aligned_timbers(miter_arrangement)

    return list(joint.cut_timbers.values())


def make_tongue_and_fork_corner_joint_90_example(position: V3) -> list[CutTimber]:
    """
    Create a tongue-and-fork corner joint at 90 degrees using canonical right-angle timbers.
    """
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)
    joint = cut_tongue_and_fork_corner_joint(arrangement)
    return list(joint.cut_timbers.values())


def make_tongue_and_fork_corner_joint_135_example(position: V3) -> list[CutTimber]:
    """
    Create a tongue-and-fork corner joint at 135 degrees for shoulder-plane validation.
    """
    arrangement = create_canonical_example_corner_joint_timbers(
        # TODO change to 135...
        corner_angle=degrees(138),
        position=position,
    )
    joint = cut_tongue_and_fork_corner_joint(arrangement)
    return list(joint.cut_timbers.values())


def make_tongue_and_fork_butt_joint_90_example(position: V3) -> list[CutTimber]:
    """
    Create a tongue-and-fork butt joint at 90 degrees using canonical butt joint timbers.
    """
    arrangement = create_canonical_example_butt_joint_timbers(position=position)
    joint = cut_tongue_and_fork_butt_joint(arrangement)
    return list(joint.cut_timbers.values())


def make_tongue_and_fork_butt_joint_angled_example(position: V3) -> list[CutTimber]:
    """
    Create a tongue-and-fork butt joint at 138 degrees.
    The butt (tongue) timber approaches the receiving (fork) timber at an angle.
    """
    from sympy import sin, cos, Integer
    angle = degrees(138)
    if position is None:
        position = create_v3(Integer(0), Integer(0), Integer(0))

    receiving_bottom = position + create_v3(-TIMBER_LENGTH / Rational(2), Integer(0), Integer(0))
    receiving_timber = timber_from_directions(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=receiving_bottom,
        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),
        ticket="receiving_timber",
    )

    butt_length_direction = create_v3(sin(angle), cos(angle), Integer(0))
    butt_timber = timber_from_directions(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=butt_length_direction,
        width_direction=create_v3(Integer(0), Integer(0), Integer(1)),
        ticket="butt_timber",
    )

    arrangement = ButtJointTimberArrangement(
        butt_timber=butt_timber,
        receiving_timber=receiving_timber,
        butt_timber_end=TimberReferenceEnd.BOTTOM,
    )
    joint = cut_tongue_and_fork_butt_joint(arrangement)
    return list(joint.cut_timbers.values())


def make_butt_joint_example(position: V3) -> list[CutTimber]:
    """
    Create a butt joint where one timber butts into another.
    The butt timber is cut square; the receiving timber is uncut.
    Uses canonical butt joint arrangement.

    Args:
        position: Center position of the joint (V3)

    Returns:
        List of CutTimber objects representing the joint
    """
    # Get canonical butt joint timbers at position
    arrangement = create_canonical_example_butt_joint_timbers(position=position)

    # Rename timbers for clarity
    receiving_timber = replace(arrangement.receiving_timber, ticket=TimberTicket("ButtJoint_Receiving"))
    butt_timber = replace(arrangement.butt_timber, ticket=TimberTicket("ButtJoint_Butt"))

    butt_arrangement = ButtJointTimberArrangement(
        receiving_timber=receiving_timber,
        butt_timber=butt_timber,
        butt_timber_end=arrangement.butt_timber_end
    )
    joint = cut_plain_butt_joint_on_face_aligned_timbers(butt_arrangement)

    return list(joint.cut_timbers.values())


def make_splice_joint_example(position: V3) -> list[CutTimber]:
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
    arrangement = create_canonical_example_splice_joint_timbers(position=position)

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

    return list(joint.cut_timbers.values())


def make_house_joint_example(position: V3) -> list[CutTimber]:
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
    housing_timber = timber_from_directions(
        ticket="HouseJoint_Housing",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([half_length, 0, 0]) + Matrix([0, 0, offset]),
        length_direction=Matrix([1, 0, 0]),
        width_direction=Matrix([0, 1, 0])
    )

    # Housed timber (shelf) extends in +Y direction, crossing through the housing timber
    # This timber fits into the groove and remains uncut
    # Offset vertically so they intersect properly
    housed_timber = timber_from_directions(
        ticket="HouseJoint_Housed",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([0, half_length, 0]) - Matrix([0, 0, offset]),
        length_direction=Matrix([0, 1, 0]),
        width_direction=Matrix([-1, 0, 0])
    )

    # Create house joint
    house_arrangement = CrossJointTimberArrangement(
        timber1=housing_timber,
        timber2=housed_timber
    )
    joint = cut_plain_house_joint(house_arrangement)

    return list(joint.cut_timbers.values())


def make_cross_lap_joint_example(position: V3) -> list[CutTimber]:
    """
    Create a cross lap joint where two timbers cross each other.
    Each timber is notched halfway through (cut_ratio=0.5) so they fit together flush.
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
    timberA = timber_from_directions(
        ticket="CrossLap_TimberA",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([half_length, 0, 0]),
        length_direction=Matrix([1, 0, 0]),
        width_direction=Matrix([0, 1, 0])  # Height direction becomes +Z
    )

    # TimberB extends in +Y direction, bottom at Z=half_height (relative to position)
    # This creates an overlap from Z=half_height to Z=TIMBER_HEIGHT
    # Height direction is +Z, so top face is at Z=half_height+TIMBER_HEIGHT
    timberB = timber_from_directions(
        ticket="CrossLap_TimberB",
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position - Matrix([0, half_length, 0]) + Matrix([0, 0, half_height]),
        length_direction=Matrix([0, 1, 0]),
        width_direction=Matrix([-1, 0, 0])  # Height direction becomes +Z
    )

    # Create cross lap joint with cut_ratio=0.5 (each timber cut halfway)
    joint = cut_plain_cross_lap_joint(
        CrossJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            front_face_on_timber1=TimberLongFace.FRONT,
        ),
        cut_ratio=Rational(1, 2),
    )

    return list(joint.cut_timbers.values())


def make_splice_lap_joint_example(position: V3) -> list[CutTimber]:
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
    arrangement = create_canonical_example_splice_joint_timbers(position=position)

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

    return list(joint.cut_timbers.values())


def create_plain_joints_patternbook() -> PatternBook:
    """
    Create a PatternBook with all plain joint patterns.

    Each pattern has groups: ["plain_joints", "{joint_type}"]
    For example: ["plain_joints", "miter"] or ["plain_joints", "butt"]

    Returns:
        PatternBook: PatternBook containing all plain joint patterns
    """
    patterns = [
        (PatternMetadata("miter_joint", ["plain_joints", "miter"], "frame"),
         lambda center: Frame(cut_timbers=make_miter_joint_example(center), name="Miter Joint (67°)")),

        (PatternMetadata("miter_joint_face_aligned", ["plain_joints", "miter"], "frame"),
         lambda center: Frame(cut_timbers=make_miter_joint_face_aligned_example(center), name="Miter Joint (Face Aligned)")),

        (PatternMetadata("butt_joint", ["plain_joints", "butt"], "frame"),
         lambda center: Frame(cut_timbers=make_butt_joint_example(center), name="Butt Joint")),

        (PatternMetadata("tongue_and_fork_corner_joint_90", ["plain_joints", "tongue_and_fork"], "frame"),
         lambda center: Frame(cut_timbers=make_tongue_and_fork_corner_joint_90_example(center), name="Tongue and Fork Corner (90°)")),

        (PatternMetadata("tongue_and_fork_corner_joint_135", ["plain_joints", "tongue_and_fork"], "frame"),
         lambda center: Frame(cut_timbers=make_tongue_and_fork_corner_joint_135_example(center), name="Tongue and Fork Corner (135°)")),

        (PatternMetadata("tongue_and_fork_butt_joint_90", ["plain_joints", "tongue_and_fork"], "frame"),
         lambda center: Frame(cut_timbers=make_tongue_and_fork_butt_joint_90_example(center), name="Tongue and Fork Butt (90°)")),

        (PatternMetadata("tongue_and_fork_butt_joint_138", ["plain_joints", "tongue_and_fork"], "frame"),
         lambda center: Frame(cut_timbers=make_tongue_and_fork_butt_joint_angled_example(center), name="Tongue and Fork Butt (138°)")),

        (PatternMetadata("splice_joint", ["plain_joints", "splice"], "frame"),
         lambda center: Frame(cut_timbers=make_splice_joint_example(center), name="Splice Joint")),

        (PatternMetadata("splice_lap_joint", ["plain_joints", "splice_lap"], "frame"),
         lambda center: Frame(cut_timbers=make_splice_lap_joint_example(center), name="Splice Lap Joint")),

        (PatternMetadata("house_joint", ["plain_joints", "house"], "frame"),
         lambda center: Frame(cut_timbers=make_house_joint_example(center), name="House Joint")),

        (PatternMetadata("cross_lap_joint", ["plain_joints", "cross_lap"], "frame"),
         lambda center: Frame(cut_timbers=make_cross_lap_joint_example(center), name="Cross Lap Joint")),
    ]

    return PatternBook(patterns=patterns)


patternbook = create_plain_joints_patternbook()


def create_all_joint_examples() -> Union[Frame, List]:
    """
    Create joint examples with automatic spacing starting from the origin.

    This now uses the PatternBook to raise all patterns in the "plain_joints" group.

    Returns:
        Frame or List[CutCSG]: Frame object containing all cut timbers for the enabled joints, or list of CSG objects
    """
    book = create_plain_joints_patternbook()

    # Raise all patterns in the "plain_joints" group with 2m spacing
    frame = book.raise_pattern_group("plain_joints", separation_distance=Rational(2))

    return frame


example = create_all_joint_examples


# ============================================================================
# Main execution
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("Kumiki - Plain Joints Examples")
    print("="*70)
    # Convert from meters back to inches for display (1m = 39.3701 inches)
    width_inches = float(TIMBER_WIDTH / inches(1))
    height_inches = float(TIMBER_HEIGHT / inches(1))
    length_inches = float(TIMBER_LENGTH / inches(1))
    print(f"Timber dimensions: {width_inches:.0f}\" x {height_inches:.0f}\"")
    print(f"Timber length: {length_inches:.0f}\" ({length_inches/12:.1f}ft)")
    print()

    # Create all examples
    frame = create_all_joint_examples()

    print()
    print("="*70)
    print(f"Total timbers created: {len(frame.cut_timbers)}")
    print("="*70)

    # Print summary of each timber
    for i, cut_timber in enumerate(frame.cut_timbers):
        timber = cut_timber.timber
        num_cuts = len(cut_timber.cuts)
        print(f"{i+1:2d}. {timber.ticket.name:30s} | Cuts: {num_cuts} | Length: {float(timber.length):.2f}m")
