"""
Butt Joints Patterns
"""

from sympy import Matrix, sqrt, sin, cos, pi
from typing import Union, List, Optional
from dataclasses import replace

from kumiki import *
from kumiki.joints.workshop.shavings.build_a_butt import (
    DovetailTenonWedgeAccessoryParameters,
)
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_splice_joint_timbers,
    create_canonical_example_brace_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import Pattern, make_pattern_from_joint, make_pattern_from_frame

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



def make_tongue_and_fork_butt_joint_90_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a tongue-and-fork butt joint at 90 degrees using canonical butt joint timbers.
    """
    arrangement = create_canonical_example_butt_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement)
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_tongue_and_fork_butt_joint_angled_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Create a tongue-and-fork butt joint at 138 degrees.
    The butt (tongue) timber approaches the receiving (fork) timber at an angle.
    """
    from sympy import sin, cos, Integer
    angle = degrees(138)
    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))

    receiving_bottom = position + create_v3(-TIMBER_LENGTH / scalar(2), scalar(0), scalar(0))
    receiving_timber = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=receiving_bottom,
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="receiving_timber",
    ), use_round_timbers)

    butt_length_direction = create_v3(sin(angle), cos(angle), scalar(0))
    butt_timber = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=butt_length_direction,
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="butt_timber",
    ), use_round_timbers)

    arrangement = ButtJointTimberArrangement(
        butt_timber=butt_timber,
        receiving_timber=receiving_timber,
        butt_timber_end=TimberEnd.BOTTOM,
    )
    joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement)
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_butt_joint_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
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
    arrangement = create_canonical_example_butt_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    # Rename timbers for clarity
    receiving_timber = replace(arrangement.receiving_timber, ticket=TimberTicket("ButtJoint_Receiving"))
    butt_timber = replace(arrangement.butt_timber, ticket=TimberTicket("ButtJoint_Butt"))

    butt_arrangement = ButtJointTimberArrangement(
        receiving_timber=receiving_timber,
        butt_timber=butt_timber,
        butt_timber_end=arrangement.butt_timber_end
    )
    joint = cut_plain_butt_joint_on_face_aligned_timbers(butt_arrangement)

    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_butt_joint_3d_angles_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
    """
    Butt joint with the butt timber approaching at an oblique 3D angle, meeting
    the receiving timber at mid-height.

    Receiving timber: vertical post along Z.
    Butt timber: direction (-2, 1, 1)/sqrt(6) — has significant X, Y, and Z components.
    The TOP end is positioned to meet the receiving post's right (+X) face at mid-height.
    """
    from sympy import sqrt

    sqrt6 = sqrt(6)
    sqrt5 = sqrt(5)

    # Receiving timber: vertical post along Z
    receiving = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=position,
        length_direction=Matrix([scalar(0), scalar(0), scalar(1)]),
        width_direction=Matrix([scalar(1), scalar(0), scalar(0)]),
        ticket=TimberTicket("ButtWeird_Receiving"),
    ), use_round_timbers)

    # Butt direction (-2, 1, 1)/sqrt(6): travels in -X, +Y, +Z — all three axes.
    # The perpendicular width (1, 2, 0)/sqrt(5) satisfies: (-2)(1)+(1)(2)+(1)(0) = 0.
    dirB = Matrix([scalar(-2), scalar(1), scalar(1)]) / sqrt6
    widthB = Matrix([scalar(1), scalar(2), scalar(0)]) / sqrt5

    # Place the butt timber so its TOP lands exactly at the receiving post's right
    # face (+X) center at mid-height: position + (TIMBER_WIDTH/2, 0, TIMBER_LENGTH/2).
    right_face_mid = position + Matrix([TIMBER_WIDTH / 2, scalar(0), TIMBER_LENGTH / 2])
    butt_bottom = right_face_mid - TIMBER_LENGTH * dirB

    butt = _maybe_round_timber(create_timber(
        length=TIMBER_LENGTH,
        size=TIMBER_SIZE_2D,
        bottom_position=butt_bottom,
        length_direction=dirB,
        width_direction=widthB,
        ticket=TimberTicket("ButtWeird_Butt"),
    ), use_round_timbers)

    joint = cut_plain_butt_joint(ButtJointTimberArrangement(
        receiving_timber=receiving,
        butt_timber=butt,
        butt_timber_end=TimberEnd.TOP,
    ))
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


"""
Example usage of mortise and tenon joint functions
"""

from sympy import Matrix
from kumiki.rule import inches, Transform, degrees
from kumiki.timber import (
    Timber, TimberEnd, TimberFace, TimberLongFace, Peg, Wedge,
    PegShape, create_timber,
    create_v3, V2, CutTimber, Frame
)

from kumiki.construction import (
    ButtJointTimberArrangement,
    Stickout,
    create_axis_aligned_timber,
    join_plane_aligned_on_plane_aligned_timbers,
)
from kumiki.example_shavings import (
    create_canonical_example_brace_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    RoundTimberConfig,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.construction import CornerJointTimberArrangement
from kumiki.patternbook import Pattern, make_pattern_from_joint, make_pattern_from_frame
from kumiki.ticket import TimberTicket


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[1],_CANONICAL_EXAMPLE_TIMBER_SIZE[0])*sqrt(2))


# TODO delete me
def example_basic_mortise_and_tenon(position=None, use_round_timbers=False):
    """
    Create a basic mortise and tenon joint using canonical butt joint timbers (4"x5"x4').
    Tenon on butt timber (Y), mortise in receiving timber (X).
    
    Args:
        position: Optional offset position (V3) to translate the joint
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    tenon_size = Matrix([inches(2), inches(2)])
    tenon_length = inches(3)  # 3" long tenon
    mortise_depth = inches(7, 2)  # 3.5" deep mortise (slightly deeper than tenon)

    joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
    )
    return joint

# TODO make a main patterns and all the _mortise_and_tenon_on_face_aligned ones below should become its childre
def example_basic_mortise_and_tenon_on_face_aligned_timbers(position=None, use_round_timbers=False):
    """
    Basic blind mortise and tenon using cut_mortise_and_tenon_joint_on_face_aligned_timbers.
    Canonical 4"x5"x4' butt joint timbers, 2"x2" tenon, 3" long, 3.5" deep mortise.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(3),
        mortise_depth=inches(7, 2),
    )

# TODO rename to example_mortise_and_tenon_with_round_tenon_on_face_aligned_timbers
def example_round_mortise_and_tenon_on_face_aligned_timbers(position=None, use_round_timbers=False):
    """
    Round (cylindrical) mortise and tenon using cut_round_mortise_and_tenon_joint.
    Canonical 4"x5"x4' butt joint timbers, 1.5" diameter round tenon, 3" long, 3.5" deep mortise.
    Shoulder is flush with the mortise entry face (0 inset).
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    
    # Get mortise face and compute shoulder distance
    tenon_end_direction = arrangement.butt_timber.get_face_direction_global(arrangement.butt_timber_end)
    mortise_face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    
    mortise_shoulder_distance = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=scalar(0),
        mortise_face=mortise_face,
        receiving_timber=arrangement.receiving_timber,
    )
    
    return cut_round_mortise_and_tenon_joint(
        arrangement=arrangement,
        diameter=inches(3, 2),
        tenon_length=inches(3),
        mortise_depth=inches(3.25),
        mortise_shoulder_distance_from_centerline_or_centerplane=mortise_shoulder_distance,
    )

# TODO  rename example_mortise_and_tenon_with_round_timbers
def example_basic_mortise_and_tenon_on_face_aligned_timbers_two_round_timbers(position=None, use_round_timbers=True):
    """
    Basic blind mortise and tenon on the canonical butt-joint layout,
    but with both timbers represented as RoundTimber.

    Uses 4" diameter round timbers in the same +X receiving / +Y butt
    arrangement as the standard canonical example.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    round_arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=round_arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(3),
        mortise_depth=inches(7, 2),
    )

def example_basic_mortise_and_tenon_on_face_aligned_timbers_with_wedge(position=None, use_round_timbers=False):
    # TODO: wedge support not yet implemented
    pass


def example_basic_mortise_and_tenon_on_face_aligned_timbers_with_through_tenon(position=None, use_round_timbers=False):
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

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(11, 2),
        mortise_depth=None,
        tenon_position=Matrix([inches(0), inches(1)]),
    )

def example_basic_mortise_and_tenon_on_face_aligned_timbers_with_inset_mortise_shoulder(position=None, use_round_timbers=False):
    """
    Mortise and tenon with a 0.5" shoulder inset from the mortise entry face.
    This pushes the shoulder plane 0.5" into the mortise timber from the face,
    so the tenon shoulder sits slightly recessed.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(3),
        mortise_depth=inches(7, 2),
        mortise_shoulder_inset=inches(1, 2),
    )

def example_double_angled_mortise_and_tenon(position=None, use_round_timbers=False):
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

    brace_arrangement = create_canonical_example_brace_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    timber1 = brace_arrangement.timber1
    brace_timber = brace_arrangement.brace_timber

    local_z = create_v3(scalar(0), scalar(0), scalar(1))
    rotation = Orientation.from_angle_axis(radians(pi / scalar(6)), local_z)
    rotated_orientation = timber1.orientation * rotation
    rotated_transform = Transform(position=timber1.transform.position, orientation=rotated_orientation)
    mortise_timber = replace(timber1, transform=rotated_transform, ticket=TimberTicket("rotated_mortise"))

    peg_params = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(inches(1), scalar(0))],
        size=inches(1, 2)
    )

    arrangement = ButtJointTimberArrangement(
        butt_timber=brace_timber,
        receiving_timber=mortise_timber,
        butt_timber_end=TimberEnd.BOTTOM,
        #front_face_on_butt_timber=TimberLongFace.RIGHT,
        # use this example, fix bug on peg length
        front_face_on_butt_timber=TimberLongFace.FRONT,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(5),
        mortise_depth=inches(3),
        mortise_shoulder_distance_from_centerline_or_centerplane=inches(2),
        peg_parameters=peg_params,
        bore_mortise_perpendicular_to_face=True,
    )


def example_brace_joint(position=None, use_round_timbers=False):
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
    brace_arrangement = create_canonical_example_brace_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    timber1 = brace_arrangement.timber1
    timber2 = brace_arrangement.timber2
    brace_timber = join_plane_aligned_on_plane_aligned_timbers(
        timber1=timber1,
        timber2=timber2,
        location_on_timber1=timber1.length / scalar(2),
        location_on_timber2=timber2.length / scalar(2),
        stickout=Stickout.nostickout(),
        size=timber1.size,
        orientation_long_face_on_timber1=TimberLongFace.RIGHT,
        orientation_long_face_on_timber2=TimberLongFace.RIGHT,
        ticket="brace_timber",
    )
    
    # Plain miter joint between the two corner timbers
    miter_joint = cut_basic_plain_miter_joint(
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
        peg_orientation = (PegPositionSpace.MORTISE, scalar(0))
    )
    
    
    # Create mortise and tenon joint between brace (tenon) and timber1 (mortise)
    # The brace connects to timber1 at its midpoint
    arrangement1 = ButtJointTimberArrangement(
        butt_timber=brace_timber,
        receiving_timber=timber1,
        butt_timber_end=TimberEnd.BOTTOM,  # Tenon on the end of brace that connects to timber1
        front_face_on_butt_timber=TimberLongFace.RIGHT,  # matches peg_parameters.tenon_face
    )
    joint1 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement1,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params,
        mortise_shoulder_inset=inches(1, 2),
        bore_mortise_perpendicular_to_face=True,
    )

    # Create mortise and tenon joint between brace (tenon) and timber2 (mortise)
    # The brace connects to timber2 at its midpoint
    arrangement2 = ButtJointTimberArrangement(
        butt_timber=brace_timber,
        receiving_timber=timber2,
        butt_timber_end=TimberEnd.TOP,  # Tenon on the end of brace that connects to timber2
        front_face_on_butt_timber=TimberLongFace.RIGHT,  # matches peg_parameters.tenon_face
    )
    joint2 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement2,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params,
        mortise_shoulder_inset=inches(1, 2),
        bore_mortise_perpendicular_to_face=True,
    )
    
    # Combine miter + both mortise-and-tenon joints into a single Frame
    # Frame.from_joints will handle merging cuts on timbers that appear in multiple joints
    return Frame.from_joints([miter_joint, joint1, joint2], name="Brace Joint with Mortise and Tenon")




def example_wedged_half_dovetail_mortise_and_tenon(position=None, use_round_timbers=False):
    """
    Wedged half-dovetail mortise and tenon joint on the canonical 4"x5"x4'
    butt joint timbers. The dovetail's flat (top) side sits on the FRONT face
    of the butt timber, which aligns with the receiving timber's length axis.
    A wedge accessory is included to lock the tenon.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    return cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        dovetail_top_side_on_butt_timber=TimberLongFace.FRONT,
        tenon_size=Matrix([inches(2), inches(4)]),
        tenon_depth=inches(4),
        dovetail_depth=inches(1, 2),
        mortise_shoulder_inset = inches(1, 2),
        receiving_timber_mortise_extra_depth=inches(1, 2),
        
        wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
            wedge_angle=degrees(8),
            wedge_tip_extra_length=inches(1),
            wedge_base_extra_length=inches(1),
        ),
    )


def example_wedged_half_dovetail_mortise_and_tenon_no_wedge(position=None, use_round_timbers=False):
    """
    Half-dovetail mortise and tenon (no wedge accessory) on the canonical
    4"x5"x4' butt joint timbers. The dovetail's flat (top) side sits on the
    FRONT face of the butt timber (along the receiving timber's length axis).
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    return cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        dovetail_top_side_on_butt_timber=TimberLongFace.FRONT,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_depth=inches(5),
        dovetail_depth=inches(1, 2),
        wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
            wedge_angle=degrees(8),
        ),
        receiving_timber_mortise_extra_depth=inches(1, 2),
        mortise_shoulder_inset = inches(1, 2),
    )


if __name__ == "__main__":
    # Run all examples
    examples = [
        ("Basic 4x4 Mortise and Tenon", example_basic_mortise_and_tenon),
        ("Basic Face-Aligned Mortise and Tenon", example_basic_mortise_and_tenon_on_face_aligned_timbers),
        ("Through Tenon Face-Aligned", example_basic_mortise_and_tenon_on_face_aligned_timbers_with_through_tenon),
        ("Inset Shoulder Face-Aligned", example_basic_mortise_and_tenon_on_face_aligned_timbers_with_inset_mortise_shoulder),
        ("Brace Joint with Mortise and Tenon", example_brace_joint),
        ("Double Angled Mortise and Tenon", example_double_angled_mortise_and_tenon),
    ]
    
    for example_name, example_func in examples:
        print(f"\n{'='*60}")
        print(f"Creating {example_name}...")
        print('='*60)
        
        joint = example_func()
        print(f"✅ Created joint with {len(joint.cuttings)} timbers")
        
        # Display timber details
        for i, cutting in enumerate(joint.cuttings.values()):
            timber = cutting.timber
            print(f"\n  Timber {i+1}: {timber.ticket.path}")
            print(f"    Position: ({float(timber.get_bottom_position_global()[0]):.1f}, {float(timber.get_bottom_position_global()[1]):.1f}, {float(timber.get_bottom_position_global()[2]):.1f})")
            print(f"    Length: {float(timber.length):.1f} inches")
            print(f"    Size: {float(timber.size[0]):.1f} x {float(timber.size[1]):.1f} inches")
            print("    Cuts: 1")
    
    print(f"\n{'='*60}")
    print("✅ All examples completed successfully!")
    print('='*60)

def create_dovetail_butt_joint_example(position: Optional[V3] = None, use_round_timbers=False):
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

    arrangement = create_canonical_example_butt_joint_timbers(
        position=position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    dovetail_timber = replace(arrangement.butt_timber, ticket=TimberTicket("dovetail_timber"))
    arrangement = replace(
        arrangement,
        butt_timber=dovetail_timber,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )

    joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        receiving_timber_shoulder_inset=inches(scalar(1, 2)),  # 0.5" shoulder inset
        dovetail_length=inches(4),                                # 4" long dovetail tenon
        dovetail_small_width=inches(scalar(3, 2)),             # 1.5" narrow end
        dovetail_large_width=inches(3),                          # 3" wide end
        dovetail_lateral_offset=scalar(0),                     # Centered
        dovetail_depth=inches(scalar(5, 2))                    # 2.5" deep cut
    )
    
    # Create a frame from the joint
    frame = Frame.from_joints(
        [joint],
        name="Dovetail Butt Joint Example (蟻仕口 / Ari Shiguchi)"
    )
    
    return frame


def create_dropin_housed_butt_joint_example(position: Optional[V3] = None):
    """
    Create a drop-in housed butt joint using canonical 4"x5"x4' timbers.

    Configuration:
        - Uses canonical butt joint timbers (receiving along X, housed/butt along Y)

    Args:
        position: Center position of the joint (V3). Defaults to origin.
    """
    from dataclasses import replace

    arrangement = create_canonical_example_butt_joint_timbers(position=position)
    housed_timber = replace(arrangement.butt_timber, ticket=TimberTicket("housed_timber"))
    arrangement = replace(
        arrangement,
        butt_timber=housed_timber,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )

    joint = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        receiving_timber_shoulder_inset=inches(scalar(1, 2)),  # 0.5" shoulder inset
        housing_length=inches(4),                               # 4" long housing tenon
        housing_width=inches(3),                                # 3" wide housing pocket
        housing_lateral_offset=scalar(0),                       # Centered
        housing_depth=inches(scalar(5, 2))                      # 2.5" deep cut
    )
    
    # Create a frame from the joint
    frame = Frame.from_joints(
        [joint],
        name="Drop-in Housed Butt Joint Example (大入れ仕口 / Oire Shiguchi)"
    )
    
    return frame


def example_compound_angle_offset_parallel_shoulder(position=None, use_round_timbers=False):
    """
    Mortise and tenon joint with compound angle (45 degrees in both axes),
    1 inch lateral centerline offset, and shoulder parallel to the FRONT face.
    """
    from sympy import pi
    from dataclasses import replace
    from kumiki.rule import Orientation, degrees
    from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
    
    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))
        
    arrangement = create_canonical_example_butt_joint_timbers(position)
    receiving_timber = arrangement.receiving_timber
    receiving_timber = replace(receiving_timber, size=create_v2(inches(10), inches(5)))
    butt_timber = arrangement.butt_timber
    
    # 1. Rotate the butt timber by 45 degrees in both local width and height axes (compound angle)
    # Width axis is local X, height axis is local Y
    local_x = create_v3(scalar(1), scalar(0), scalar(0))
    local_y = create_v3(scalar(0), scalar(1), scalar(0))
    
    pivot_local = create_v3(scalar(0), scalar(0), butt_timber.length / scalar(2))
    pivot_global = butt_timber.transform.position + butt_timber.transform.orientation.matrix * pivot_local
    
    # Rotate 45 degrees about local X
    rot_x = Orientation.from_angle_axis(degrees(45), local_x)
    orient_x = butt_timber.transform.orientation * rot_x
    
    # Rotate 45 degrees about local Y
    rot_y = Orientation.from_angle_axis(degrees(45), local_y)
    new_orientation = orient_x * rot_y
    
    new_bottom = pivot_global - new_orientation.matrix * pivot_local
    butt_timber = replace(butt_timber, transform=Transform(position=new_bottom, orientation=new_orientation))
    
    # 2. Add 1 inch lateral offset along receiving timber's width direction
    width_dir = receiving_timber.get_width_direction_global()
    butt_timber = replace(
        butt_timber,
        transform=Transform(
            position=butt_timber.transform.position + width_dir * inches(1),
            orientation=butt_timber.transform.orientation
        )
    )
    
    rotated_arrangement = ButtJointTimberArrangement(
        butt_timber=butt_timber,
        receiving_timber=receiving_timber,
        butt_timber_end=arrangement.butt_timber_end,
        front_face_on_butt_timber=arrangement.front_face_on_butt_timber,
    )
    
    return cut_mortise_and_tenon_joint(
        arrangement=rotated_arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(5),
        mortise_depth=inches(3),
        mortise_shoulder_distance_from_centerline_or_centerplane=scalar(0),
        set_mortise_shoulder_parallel_to_face=TimberLongFace.BACK,
    )


def example_inset_shoulder_notch_angled(position=None, use_round_timbers=False):
    """
    Mortise and tenon with an inset shoulder using the NOTCH style.

    The tenon timber approaches the mortise at ~30 degrees (angled in the XY
    plane) so the housing notch in the mortise timber is clearly visible.
    The shoulder is inset 1" from the mortise timber's centerline.
    The notch walls are angled (relieved) to follow the tenon rake.
    """
    from sympy import sqrt
    from kumiki.rule import Orientation, degrees, radians
    from kumiki.ticket import TimberTicket

    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))

    timber_size = create_v2(inches(4), inches(5))
    timber_length = inches(48)

    # Receiving (mortise) timber: runs along +X, centered at position
    mortise_timber = create_timber(
        length=timber_length,
        size=timber_size,
        bottom_position=position + create_v3(-timber_length / scalar(2), scalar(0), scalar(0)),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="mortise",
    )

    # Tenon timber: approaches from below at 30 degrees from the Y axis in the XY plane.
    # Direction: (sin30, cos30, 0) = (0.5, sqrt(3)/2, 0)
    from sympy import sin, cos, pi, Rational
    angle = pi / scalar(6)  # 30 degrees
    tenon_dir = normalize_vector(create_v3(sin(angle), cos(angle), scalar(0)))
    tenon_width_dir = normalize_vector(create_v3(cos(angle), -sin(angle), scalar(0)))

    # Place bottom of tenon timber centered so its top meets the mortise
    tenon_bottom = position - tenon_dir * timber_length
    tenon_timber = create_timber(
        length=timber_length,
        size=timber_size,
        bottom_position=tenon_bottom,
        length_direction=tenon_dir,
        width_direction=tenon_width_dir,
        ticket="tenon",
    )

    mortise_timber = _maybe_round_timber(mortise_timber, use_round_timbers)
    tenon_timber = _maybe_round_timber(tenon_timber, use_round_timbers)

    arrangement = ButtJointTimberArrangement(
        butt_timber=tenon_timber,
        receiving_timber=mortise_timber,
        butt_timber_end=TimberEnd.TOP,
        front_face_on_butt_timber=TimberLongFace.FRONT,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(4),
        mortise_depth=inches(3),
        mortise_shoulder_distance_from_centerline_or_centerplane=inches(1),
        inset_notching_style=InsetShoulderNotchingStyle.NOTCH,
        use_round_tenon=use_round_timbers,
    )


def example_inset_shoulder_scribe_angled(position=None, use_round_timbers=False):
    """
    Mortise and tenon with an inset shoulder using the SCRIBE style.

    The tenon timber approaches the mortise at a compound angle (angled in
    both the XY and XZ planes) so the scribe cut in the mortise timber is
    clearly non-rectangular. The shoulder is inset 1" from the mortise
    timber's centerline. With SCRIBE style, the mortise timber receives a
    Difference(tenon_prism, shoulder_half_space) cut — the exact 3-D shadow
    of the tenon — rather than a rectangular housing notch.
    """
    from sympy import sin, cos, pi, sqrt
    from kumiki.rule import Orientation, degrees, radians
    from kumiki.ticket import TimberTicket

    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))

    timber_size = create_v2(inches(4), inches(5))
    timber_length = inches(48)

    # Receiving (mortise) timber: runs along +X, centered at position.
    # Widen to 10" so the compound-angle tenon shoulder fits fully inside.
    mortise_size = create_v2(inches(10), inches(5))
    mortise_timber = create_timber(
        length=timber_length,
        size=mortise_size,
        bottom_position=position + create_v3(-timber_length / scalar(2), scalar(0), scalar(0)),
        length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
        ticket="mortise",
    )

    # Tenon timber: compound angle — 30 degrees in XY plane AND 20 degrees
    # toward +Z — so its cross-section trace on the mortise face is an
    # obvious oblique ellipse (very different from the rectangular NOTCH).
    angle_xy = pi / scalar(6)   # 30 deg in XY
    angle_z  = pi / scalar(9)   # 20 deg toward Z
    # length direction: rotate (0,1,0) by angle_xy around Z, then tilt by angle_z toward Z
    tenon_dir = normalize_vector(create_v3(
        sin(angle_xy) * cos(angle_z),
        cos(angle_xy) * cos(angle_z),
        sin(angle_z),
    ))
    # width direction: perpendicular to tenon_dir, mostly in XY plane
    tenon_width_dir = normalize_vector(create_v3(cos(angle_xy), -sin(angle_xy), scalar(0)))

    # Place bottom of tenon timber centered so its top meets the mortise
    tenon_bottom = position - tenon_dir * timber_length
    tenon_timber = create_timber(
        length=timber_length,
        size=timber_size,
        bottom_position=tenon_bottom,
        length_direction=tenon_dir,
        width_direction=tenon_width_dir,
        ticket="tenon",
    )

    mortise_timber = _maybe_round_timber(mortise_timber, use_round_timbers)
    tenon_timber = _maybe_round_timber(tenon_timber, use_round_timbers)

    arrangement = ButtJointTimberArrangement(
        butt_timber=tenon_timber,
        receiving_timber=mortise_timber,
        butt_timber_end=TimberEnd.TOP,
        front_face_on_butt_timber=TimberLongFace.FRONT,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([inches(2), inches(2)]),
        tenon_length=inches(4),
        mortise_depth=inches(3),
        mortise_shoulder_distance_from_centerline_or_centerplane=inches(1),
        inset_notching_style=InsetShoulderNotchingStyle.SCRIBE,
        use_round_tenon=use_round_timbers,
    )


def create_all_butt_joint_patterns(use_round_timbers=False) -> Frame:
    origin = create_v3(scalar(0), scalar(0), scalar(0))
    step = inches(24)
    all_timbers = []
    all_timbers += make_tongue_and_fork_butt_joint_90_example(origin, use_round_timbers)
    all_timbers += make_tongue_and_fork_butt_joint_angled_example(origin + create_v3(step, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_butt_joint_example(origin + create_v3(step * 2, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_butt_joint_3d_angles_example(origin + create_v3(step * 3, scalar(0), scalar(0)), use_round_timbers)
    return Frame(cut_timbers=all_timbers, name="Butt Joint Patterns")


patterns = [
    Pattern(path="butt_joints/tongue_and_fork/tongue_and_fork_butt_joint_90", lambda_=_make_frame_pattern(make_tongue_and_fork_butt_joint_90_example, "Tongue and Fork Butt Joint 90°"), pattern_type='frame', tags=['main']),
    Pattern(path="butt_joints/tongue_and_fork/tongue_and_fork_butt_joint_angled", lambda_=_make_frame_pattern(make_tongue_and_fork_butt_joint_angled_example, "Tongue and Fork Butt Joint (Angled)"), pattern_type='frame'),
    Pattern(path="butt_joints/plain_butt_joint/plain_butt_joint", lambda_=_make_frame_pattern(make_butt_joint_example, "Plain Butt Joint"), pattern_type='frame'),
    Pattern(path="butt_joints/plain_butt_joint/plain_butt_joint_3d", lambda_=_make_frame_pattern(make_butt_joint_3d_angles_example, "Plain Butt Joint (3D)"), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_basic", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_basic_face_aligned", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_on_face_aligned_timbers), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_round_face_aligned", lambda_=make_pattern_from_joint(example_round_mortise_and_tenon_on_face_aligned_timbers), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_basic_face_aligned_round_timbers", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_on_face_aligned_timbers_two_round_timbers), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_through_tenon", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_on_face_aligned_timbers_with_through_tenon), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_inset_shoulder", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_on_face_aligned_timbers_with_inset_mortise_shoulder), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_double_angled", lambda_=make_pattern_from_joint(example_double_angled_mortise_and_tenon), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_compound_offset_parallel_shoulder", lambda_=make_pattern_from_joint(example_compound_angle_offset_parallel_shoulder), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/brace_joint_mortise_and_tenon", lambda_=make_pattern_from_frame(example_brace_joint), pattern_type='frame'),
    Pattern(path="butt_joints/wedged_half_dovetail_mortise_and_tenon", lambda_=make_pattern_from_joint(example_wedged_half_dovetail_mortise_and_tenon), pattern_type='frame'),
    Pattern(path="butt_joints/half_dovetail_mortise_and_tenon_no_wedge", lambda_=make_pattern_from_joint(example_wedged_half_dovetail_mortise_and_tenon_no_wedge), pattern_type='frame'),
    Pattern(path="butt_joints/cut_dropin_dovetail_butt_joint_on_face_aligned_timbers", lambda_=make_pattern_from_frame(create_dovetail_butt_joint_example), pattern_type='frame'),
    Pattern(path="butt_joints/cut_dropin_housed_butt_joint_on_face_aligned_timbers", lambda_=make_pattern_from_frame(create_dropin_housed_butt_joint_example), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_inset_shoulder_notch_angled", lambda_=make_pattern_from_joint(example_inset_shoulder_notch_angled), pattern_type='frame'),
    Pattern(path="butt_joints/mortise_and_tenon/mortise_and_tenon_inset_shoulder_scribe_angled", lambda_=make_pattern_from_joint(example_inset_shoulder_scribe_angled), pattern_type='frame'),
]
