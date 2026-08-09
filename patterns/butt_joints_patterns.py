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
    joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement, shoulder_inset = inches(1))
    return [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]


def make_tongue_and_fork_butt_joint_angled_inset_example(position: V3, use_round_timbers=False) -> list[CutTimber]:
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
    joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement, shoulder_inset = inches(1))
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

# NOTE: mortise-and-tenon example patterns (basic, round, through-tenon, inset-shoulder,
# double-angled, 45-degree-relative-size, brace joint, corner joint, tusked, wedged
# half-dovetail, compound-angle, inset-shoulder-notch/scribe-angled) live in
# mortise_and_tenon_joints_patterns.py now.

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


def create_all_butt_joint_patterns(use_round_timbers=False) -> Frame:
    origin = create_v3(scalar(0), scalar(0), scalar(0))
    step = inches(24)
    all_timbers = []
    all_timbers += make_tongue_and_fork_butt_joint_90_example(origin, use_round_timbers)
    all_timbers += make_tongue_and_fork_butt_joint_angled_inset_example(origin + create_v3(step, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_butt_joint_example(origin + create_v3(step * 2, scalar(0), scalar(0)), use_round_timbers)
    all_timbers += make_butt_joint_3d_angles_example(origin + create_v3(step * 3, scalar(0), scalar(0)), use_round_timbers)
    return Frame(cut_timbers=all_timbers, name="Butt Joint Patterns")


patterns = [
    Pattern(path="butt_joints/tongue_and_fork/tongue_and_fork_butt_joint_90", lambda_=_make_frame_pattern(make_tongue_and_fork_butt_joint_90_example, "Tongue and Fork Butt Joint 90°"), pattern_type='frame', tags=['main']),
    Pattern(path="butt_joints/tongue_and_fork/tongue_and_fork_butt_joint_angled", lambda_=_make_frame_pattern(make_tongue_and_fork_butt_joint_angled_inset_example, "Tongue and Fork Butt Joint (Angled + Inset)"), pattern_type='frame'),
    Pattern(path="butt_joints/plain_butt_joint/plain_butt_joint", lambda_=_make_frame_pattern(make_butt_joint_example, "Plain Butt Joint"), pattern_type='frame'),
    Pattern(path="butt_joints/plain_butt_joint/plain_butt_joint_3d", lambda_=_make_frame_pattern(make_butt_joint_3d_angles_example, "Plain Butt Joint (3D)"), pattern_type='frame'),
    Pattern(path="butt_joints/cut_dropin_dovetail_butt_joint_on_face_aligned_timbers", lambda_=make_pattern_from_frame(create_dovetail_butt_joint_example), pattern_type='frame'),
    Pattern(path="butt_joints/cut_dropin_housed_butt_joint_on_face_aligned_timbers", lambda_=make_pattern_from_frame(create_dropin_housed_butt_joint_example), pattern_type='frame'),
]
