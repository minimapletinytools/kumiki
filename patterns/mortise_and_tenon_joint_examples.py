"""
Example usage of mortise and tenon joint functions
"""

from sympy import Matrix, Rational, Integer
from kumiki.rule import inches, Transform
from kumiki.timber import (
    Timber, TimberReferenceEnd, TimberFace, TimberLongFace, Peg, Wedge,
    PegShape, timber_from_directions,
    create_v3, V2, CutTimber, Frame
)
from kumiki.joints.mortise_and_tenon_joint import *

from kumiki.construction import (
    ButtJointTimberArrangement,
    Stickout,
    create_axis_aligned_timber,
    join_plane_aligned_on_place_aligned_timbers,
)
from kumiki.example_shavings import (
    create_canonical_example_brace_joint_timbers,
    create_canonical_example_butt_joint_timbers,
)
from kumiki.joints.basic_joints import cut_basic_miter_joint
from kumiki.construction import CornerJointTimberArrangement
from kumiki.patternbook import PatternBook, PatternMetadata, make_pattern_from_joint, make_pattern_from_frame
from kumiki.ticket import TimberTicket


def example_basic_mortise_and_tenon(position=None):
    """
    Create a basic mortise and tenon joint using canonical butt joint timbers (4"x5"x4').
    Tenon on butt timber (Y), mortise in receiving timber (X).
    
    Args:
        position: Optional offset position (V3) to translate the joint
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(position)
    tenon_size = Matrix([inches(2), inches(2)])
    tenon_length = inches(3)  # 3" long tenon
    mortise_depth = inches(7, 2)  # 3.5" deep mortise (slightly deeper than tenon)

    joint = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
    )
    return joint


def example_basic_mortise_and_tenon_on_FAT(position=None):
    """
    Basic blind mortise and tenon using cut_mortise_and_tenon_joint_on_FAT.
    Canonical 4"x5"x4' butt joint timbers, 2"x2" tenon, 3" long, 3.5" deep mortise.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(position)
    return cut_mortise_and_tenon_joint_on_FAT(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(3),
        mortise_depth=inches(7, 2),
    )


def example_basic_mortise_and_tenon_on_FAT_with_wedge(position=None):
    # TODO: wedge support not yet implemented
    pass


def example_basic_mortise_and_tenon_on_FAT_with_through_tenon(position=None):
    """
    Through tenon with 3" stickout past the mortise timber, and the tenon offset
    so that one side of the tenon lines up with the edge of the butt timber.

    Canonical timbers: butt is 4"x5" along +Y, receiving is 4"x5" along +X.
    The butt timber TOP end faces the receiving timber. The tenon enters the
    receiving timber's height face (5" dimension). Through mortise means
    mortise_depth=None.

    tenon_length = half the receiving timber entry dimension + 3" stickout
                 = 5/2 + 3 = 5.5"
    tenon_position X offset = butt_timber half-width - tenon half-width
                            = 4/2 - 2/2 = 1"
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(position)
    return cut_mortise_and_tenon_joint_on_FAT(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(11, 2),
        mortise_depth=None,
        tenon_position=Matrix([inches(0), inches(1)]),
    )


def example_basic_mortise_and_tenon_on_FAT_with_inset_mortise_shoulder(position=None):
    """
    Mortise and tenon with a 0.5" shoulder inset from the mortise entry face.
    This pushes the shoulder plane 0.5" into the mortise timber from the face,
    so the tenon shoulder sits slightly recessed.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(position)
    return cut_mortise_and_tenon_joint_on_FAT(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(3),
        mortise_depth=inches(7, 2),
        mortise_shoulder_inset=inches(1, 2),
    )


def example_basic_mortise_and_tenon_on_FAT_with_wedge(position=None):
    # TODO: wedge support not yet implemented
    pass


# TODO
def example_angled_mortise_and_tenon_on_PAT(position=None):
    pass

def example_brace_joint(position=None):
    """
    Create a brace joint with mortise and tenon connections.
    
    Configuration:
    - Creates a canonical brace joint arrangement (two 90-degree corner timbers + brace)
    - Plain miter joint between timber1 and timber2 at the corner
    - The brace timber connects the midpoints of the two corner timbers
    - Mortise and tenon joints connect the brace to both corner timbers
    
    Args:
        position: Optional offset position (V3) to translate the joint
    """
    if position is None:
        position = create_v3(0, 0, 0)
    
    # Create the brace joint timber arrangement
    brace_arrangement = create_canonical_example_brace_joint_timbers(position)
    timber1 = brace_arrangement.timber1
    timber2 = brace_arrangement.timber2
    brace_timber = join_plane_aligned_on_place_aligned_timbers(
        timber1=timber1,
        timber2=timber2,
        location_on_timber1=timber1.length / Integer(2),
        location_on_timber2=timber2.length / Integer(2),
        stickout=Stickout.nostickout(),
        size=timber1.size,
        orientation_long_face_on_timber1=TimberLongFace.RIGHT,
        orientation_long_face_on_timber2=TimberLongFace.RIGHT,
        ticket="brace_timber",
    )
    
    # Plain miter joint between the two corner timbers
    miter_joint = cut_basic_miter_joint(
        CornerJointTimberArrangement(
            timber1=timber1,
            timber2=timber2,
            timber1_end=brace_arrangement.timber1_end,
            timber2_end=brace_arrangement.timber2_end,
        )
    )
    
    # Define tenon dimensions (smaller than full timber size)
    tenon_size = Matrix([inches(2), inches(2)])  # 2" x 2" tenon
    tenon_length = inches(5) 
    mortise_depth = inches(2) 

        
    # Define peg parameters
    # Two pegs through the FRONT face, offset from the centerline
    # - First peg: 1" from shoulder, -0.5" from centerline
    # - Second peg: 2" from shoulder, +0.5" from centerline
    peg_params = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[
            (inches(1), inches(0)),  # 1" from shoulder, -0.5" from centerline
        ],
        #depth=inches(4),  # 4" deep into mortise timber
        size=inches(1, 2),  # 0.5" peg diameter/side length
        peg_orientation = (PegPositionSpace.MORTISE, Rational(0))
    )
    
    
    # Create mortise and tenon joint between brace (tenon) and timber1 (mortise)
    # The brace connects to timber1 at its midpoint
    arrangement1 = ButtJointTimberArrangement(
        butt_timber=brace_timber,
        receiving_timber=timber1,
        butt_timber_end=TimberReferenceEnd.BOTTOM,  # Tenon on the end of brace that connects to timber1
        front_face_on_butt_timber=TimberLongFace.RIGHT,  # matches peg_parameters.tenon_face
    )
    joint1 = cut_mortise_and_tenon_joint_on_PAT(
        arrangement=arrangement1,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params,
        mortise_shoulder_inset=inches(1, 2),
        crop_tenon_to_mortise_orientation_on_angled_joints=True,
    )

    # Create mortise and tenon joint between brace (tenon) and timber2 (mortise)
    # The brace connects to timber2 at its midpoint
    arrangement2 = ButtJointTimberArrangement(
        butt_timber=brace_timber,
        receiving_timber=timber2,
        butt_timber_end=TimberReferenceEnd.TOP,  # Tenon on the end of brace that connects to timber2
        front_face_on_butt_timber=TimberLongFace.RIGHT,  # matches peg_parameters.tenon_face
    )
    joint2 = cut_mortise_and_tenon_joint_on_PAT(
        arrangement=arrangement2,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params,
        mortise_shoulder_inset=inches(1, 2),
        crop_tenon_to_mortise_orientation_on_angled_joints=True,
    )
    
    # Combine miter + both mortise-and-tenon joints into a single Frame
    # Frame.from_joints will handle merging cuts on timbers that appear in multiple joints
    return Frame.from_joints([miter_joint, joint1, joint2], name="Brace Joint with Mortise and Tenon")

def example_double_angled_mortise_and_tenon(position=None):
    """
    Mortise and tenon with timbers meeting at two non-orthogonal angles.

    Takes the brace arrangement (timber1 in +Y, brace at 45 deg in XY plane),
    then rotates timber1 by 45 degrees around the Z axis so the mortise timber
    is no longer axis-aligned. The brace enters the rotated timber1 at a
    compound angle -- non-orthogonal in both the horizontal and vertical planes.
    """
    from sympy import Integer, pi
    from dataclasses import replace
    from kumiki.rule import Orientation, radians
    from kumiki.ticket import Ticket

    if position is None:
        position = create_v3(0, 0, 0)

    brace_arrangement = create_canonical_example_brace_joint_timbers(position)
    timber1 = brace_arrangement.timber1
    brace_timber = brace_arrangement.brace_timber

    local_z = create_v3(Integer(0), Integer(0), Integer(1))
    rotation = Orientation.from_angle_axis(radians(pi / Integer(6)), local_z)
    rotated_orientation = timber1.orientation * rotation
    rotated_transform = Transform(position=timber1.transform.position, orientation=rotated_orientation)
    mortise_timber = replace(timber1, transform=rotated_transform, ticket=TimberTicket("rotated_mortise"))

    peg_params = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(inches(1), Rational(0))],
        size=inches(1, 2)
    )

    arrangement = ButtJointTimberArrangement(
        butt_timber=brace_timber,
        receiving_timber=mortise_timber,
        butt_timber_end=TimberReferenceEnd.BOTTOM,
        #front_face_on_butt_timber=TimberLongFace.RIGHT,
        # use this example, fix bug on peg length
        front_face_on_butt_timber=TimberLongFace.FRONT,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(5),
        mortise_depth=inches(3),
        mortise_shoulder_distance_from_centerline=inches(2),
        peg_parameters=peg_params,
        crop_tenon_to_mortise_orientation_on_angled_joints=True,
    )



def create_mortise_and_tenon_patternbook() -> PatternBook:
    """
    Create a PatternBook with all mortise and tenon joint patterns.
    
    Each pattern has groups: ["mortise_tenon", "{variant}"]
    For example: ["mortise_tenon", "basic"] or ["mortise_tenon", "with_pegs"]
    
    Returns:
        PatternBook: PatternBook containing all mortise and tenon joint patterns
    """
    patterns = [
        (PatternMetadata("basic_4x4", ["mortise_tenon", "basic"], "frame"),
         make_pattern_from_joint(example_basic_mortise_and_tenon)),

        (PatternMetadata("basic_FAT", ["mortise_tenon", "basic_fat"], "frame"),
         make_pattern_from_joint(example_basic_mortise_and_tenon_on_FAT)),

        (PatternMetadata("through_tenon_FAT", ["mortise_tenon", "through_fat"], "frame"),
         make_pattern_from_joint(example_basic_mortise_and_tenon_on_FAT_with_through_tenon)),

        (PatternMetadata("inset_shoulder_FAT", ["mortise_tenon", "inset_shoulder_fat"], "frame"),
         make_pattern_from_joint(example_basic_mortise_and_tenon_on_FAT_with_inset_mortise_shoulder)),

        (PatternMetadata("brace_joint", ["mortise_tenon", "brace"], "frame"),
         make_pattern_from_frame(example_brace_joint)),

        (PatternMetadata("double_angled", ["mortise_tenon", "double_angled"], "frame"),
         make_pattern_from_joint(example_double_angled_mortise_and_tenon)),
    ]
    
    return PatternBook(patterns=patterns)


patternbook = create_mortise_and_tenon_patternbook()


def create_all_mortise_and_tenon_examples():
    """
    Create mortise and tenon joint examples with automatic spacing.
    
    This now uses the PatternBook to raise all patterns in the "mortise_tenon" group.
    
    Returns:
        Frame: Frame object containing all cut timbers and accessories for the examples
    """
    book = create_mortise_and_tenon_patternbook()
    
    # Raise all patterns in the "mortise_tenon" group with 6 feet spacing
    frame = book.raise_pattern_group("mortise_tenon", separation_distance=inches(72))
    
    return frame


example = create_all_mortise_and_tenon_examples


if __name__ == "__main__":
    # Run all examples
    examples = [
        ("Basic 4x4 Mortise and Tenon", example_basic_mortise_and_tenon),
        ("Basic FAT Mortise and Tenon", example_basic_mortise_and_tenon_on_FAT),
        ("Through Tenon FAT", example_basic_mortise_and_tenon_on_FAT_with_through_tenon),
        ("Inset Shoulder FAT", example_basic_mortise_and_tenon_on_FAT_with_inset_mortise_shoulder),
        ("Brace Joint with Mortise and Tenon", example_brace_joint),
        ("Double Angled Mortise and Tenon", example_double_angled_mortise_and_tenon),
    ]
    
    for example_name, example_func in examples:
        print(f"\n{'='*60}")
        print(f"Creating {example_name}...")
        print('='*60)
        
        joint = example_func()
        print(f"✅ Created joint with {len(joint.cut_timbers)} timbers")
        
        # Display timber details
        for i, cut_timber in enumerate(joint.cut_timbers.values()):
            timber = cut_timber.timber
            print(f"\n  Timber {i+1}: {timber.ticket.name}")
            print(f"    Position: ({float(timber.get_bottom_position_global()[0]):.1f}, {float(timber.get_bottom_position_global()[1]):.1f}, {float(timber.get_bottom_position_global()[2]):.1f})")
            print(f"    Length: {float(timber.length):.1f} inches")
            print(f"    Size: {float(timber.size[0]):.1f} x {float(timber.size[1]):.1f} inches")
            print(f"    Cuts: {len(cut_timber.cuts)}")
    
    print(f"\n{'='*60}")
    print("✅ All examples completed successfully!")
    print('='*60)

