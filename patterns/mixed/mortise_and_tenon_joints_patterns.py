# Last checked on kumiki 0.9.8
"""
Mortise and Tenon Joints Patterns
"""

__title__ = {"en": "Mortise and tenon joints", "ja": "枘差し"}

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
    CornerJointTimberArrangement,
)
from kumiki.ticket import TimberTicket

pattern_folders(KUMIKI_PATTERN_FOLDERS)


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[1],_CANONICAL_EXAMPLE_TIMBER_SIZE[0])*sqrt(2))




EXAMPLE_ROUND_MORTISE_AND_TENON_ON_FACE_ALIGNED_TIMBERS_OPTIONS = kiwari(
    diameter=kiwari.length(inches(3, 2)),
    length=kiwari.length(inches(3)),
    depth=kiwari.length(inches(3.25)),
)


@pattern('mixed/mortise_and_tenon/round_face_aligned', name={"en": "Round, face-aligned", "ja": "丸枘、面を揃える"}, kiwari=EXAMPLE_ROUND_MORTISE_AND_TENON_ON_FACE_ALIGNED_TIMBERS_OPTIONS)
def example_round_mortise_and_tenon_on_face_aligned_timbers(k: Optional[Kiwari] = None, *, position=None, use_round_timbers=False) -> Joint:
    """
    Round (cylindrical) mortise and tenon using cut_round_mortise_and_tenon_joint.
    Canonical 4"x5"x4' butt joint timbers, 1.5" diameter round tenon, 3" long, 3.5" deep mortise.
    Shoulder is flush with the mortise entry face (0 inset).
    """
    k = EXAMPLE_ROUND_MORTISE_AND_TENON_ON_FACE_ALIGNED_TIMBERS_OPTIONS.resolve(k)
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
        diameter=k.length("diameter"),
        tenon_length=k.length("length"),
        mortise_depth=k.length("depth"),
        mortise_shoulder_distance_from_centerline_or_centerplane=mortise_shoulder_distance,
    )



EXAMPLE_BASIC_MORTISE_AND_TENON_ON_FACE_ALIGNED_TIMBERS_WITH_THROUGH_TENON_OPTIONS = kiwari(
    width=kiwari.length(inches(3)),
    height=kiwari.length(inches(1)),
    length=kiwari.length(inches(11, 2)),
    offset=kiwari.point2(create_v2(0, inches(1))),
)


@pattern('mixed/mortise_and_tenon/through_tenon', name={"en": "Through tenon", "ja": "通し枘"}, kiwari=EXAMPLE_BASIC_MORTISE_AND_TENON_ON_FACE_ALIGNED_TIMBERS_WITH_THROUGH_TENON_OPTIONS)
def example_basic_mortise_and_tenon_on_face_aligned_timbers_with_through_tenon(k: Optional[Kiwari] = None, *, position=None, use_round_timbers=False) -> Joint:
    """
    Through tenon with 3" stickout past the mortise timber, and the tenon offset
    so that one side of the tenon sits near the edge of the butt timber.

    Canonical timbers: butt is 4"x5" along +Y, receiving is 4"x5" along +X.
    The butt timber TOP end faces the receiving timber. The tenon enters the
    receiving timber's height face (5" dimension). Through mortise means
    mortise_depth=None.

    tenon_length = half the receiving timber entry dimension + 3" stickout
                 = 5/2 + 3 = 5.5"
    Tenon is 3" wide (relative to the joint plane) x 1" tall, offset 1" from
    centerline along the width axis.
    """
    k = EXAMPLE_BASIC_MORTISE_AND_TENON_ON_FACE_ALIGNED_TIMBERS_WITH_THROUGH_TENON_OPTIONS.resolve(k)
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=k.length("width"),
        tenon_height_relative_to_joint=k.length("height"),
        tenon_length=k.length("length"),
        mortise_depth=None,
        tenon_position=k.v2("offset"),
    )


TWIN_TENON = kiwari(
    notched=kiwari.flag(True, about="Flare the sides of the shared shoulder housing."),
)


@pattern("mixed/mortise_and_tenon/twin_tenon", name={"en": "Twin tenon", "ja": "二枚枘"}, kiwari=TWIN_TENON)
def twin_tenon(k: Optional[Kiwari] = None) -> Joint:
    """Merge two stopped tenons and cut their shared inset housing with straight or flared sides."""
    k = TWIN_TENON.resolve(k)
    arrangement = create_canonical_example_butt_joint_timbers(
        timber_size=create_v2(inches(4), inches(6)), timber_length=inches(16),
    )
    tenons = [
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement,
            tenon_position=create_v2(0, offset),
            tenon_width_relative_to_joint=inches(1),
            tenon_height_relative_to_joint=inches(5, 2),
            tenon_length=inches(2),
            mortise_depth=inches(9, 4),
            mortise_shoulder_inset=inches(1),
            relief=None,
            inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief,
        )
        for offset in (inches(-3, 2), inches(3, 2))
    ]
    return merge_mortise_and_tenon_joints(
        tenons, relief=ButtJointNotchReliefConfig() if k.flag("notched") else None,
    )


ANGLED_TENON = kiwari(
    width=kiwari.length(inches(2), minimum=inches(1, 4)),
    height=kiwari.length(inches(2), minimum=inches(1, 4)),
    length=kiwari.length(inches(3), minimum=inches(1, 4)),
    depth=kiwari.length(inches(4), minimum=inches(1, 4)),
    shoulder_distance=kiwari.length(inches(2)),
    position=kiwari.point2(create_v2(0, 0)),
    notched=kiwari.flag(False),
    round_timbers=kiwari.flag(False),
    pegged=kiwari.flag(False),
    peg_shape=kiwari.choice(PegShape, PegShape.SQUARE),
    peg_size=kiwari.length(inches(1, 2), minimum=inches(1, 8)),
)


@pattern('mixed/mortise_and_tenon/compound_angled', name={"en": "Compound angle", "ja": "二方向に傾いた枘"}, kiwari=ANGLED_TENON)
def example_double_angled_mortise_and_tenon(k: Optional[Kiwari] = None, *, position=None) -> Joint:
    """
    Mortise and tenon with timbers meeting at two non-orthogonal angles.

    Takes the brace arrangement (timber1 in +Y, brace at 45 deg in XY plane),
    then rotates timber1 by 45 degrees around the Z axis so the mortise timber
    is no longer axis-aligned. The brace enters the rotated timber1 at a
    compound angle -- non-orthogonal in both the horizontal and vertical planes.
    """
    k = ANGLED_TENON.resolve(k)
    use_round_timbers = k.flag("round_timbers")
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
        shape=k.choice("peg_shape"),
        peg_positions=[(inches(1), scalar(0))],
        size=k.length("peg_size")
    )

    arrangement = ButtJointTimberArrangement(
        butt_timber=brace_timber,
        receiving_timber=mortise_timber,
        butt_timber_end=TimberEnd.BOTTOM,
        front_face_on_butt_timber=TimberLongFace.FRONT,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=create_v2(k.length("width"), k.length("height")),
        tenon_length=k.length("length"),
        mortise_depth=k.length("depth"),
        mortise_shoulder_distance_from_centerline_or_centerplane=k.length("shoulder_distance"),
        peg_parameters=peg_params if k.flag("pegged") else None,
        tenon_position=k.v2("position"),
        relief=ButtJointNotchReliefConfig() if k.flag("notched") else ButtJointScribeReliefConfig.butt_timber(),
        inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief if k.flag("notched") else InsetShoulderReliefStyle.Rough,
    )


NOTCH_STYLE = kiwari(
    notch_from=kiwari.choice(
        NotchFrom, NotchFrom.Face,
        about="What the notch relief is anchored to: the real inset shoulder, or the mortise entry face",
    ),
)


@pattern('mixed/mortise_and_tenon/joint_plane_aligned_notched_2sided', name={"en": "Notched on two sides", "ja": "両側を欠き込んだ枘"}, kiwari=NOTCH_STYLE)
def example_mortise_and_tenon_joint_plane_aligned_notched_2sided(k: Optional[Kiwari]=None) -> Joint:
    """
    Mortise and tenon on plane-aligned timbers, tenon approaching at 45 degrees (in the
    XY plane), with both timbers being Timber (not the PerfectTimberWithin base) with ROUGH
    sizes 1" larger than their perfect-timber-within size (0.5" extra on each side,
    symmetric), and relief=ButtJointNotchReliefConfig() to demonstrate
    chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided: since the
    arrangement is plane-aligned, cut_mortise_and_tenon_joint_on_plane_aligned_timbers uses
    the 2-sided notch (2 flat walls at the timbers' own rough edges, 2 flared walls) instead
    of the fully-general 4-sided one, relieving the extra rough material on both timbers.

    Uses mortise_shoulder_inset=1" (a real inset), so the two notch_from styles are visibly
    different, and which one is shown is the pattern's `notch_from` parameter:
    - NotchFrom.Face (the default): the joint still fits at the real, inset shoulder (via
      the default scribe-based housing cut), but the notch itself is anchored to the
      mortise entry face, so it reads as starting at the timber's outer face.
    - NotchFrom.Shoulder: the notch is anchored to the real, inset shoulder instead.
    """
    notch_from = NOTCH_STYLE.resolve(k).choice("notch_from", NotchFrom)
    position = create_v3(scalar(0), scalar(0), scalar(0))

    ptw_size = create_v2(inches(4), inches(5))
    timber_length = inches(48)
    # Rough half-size = PTW half-size + 0.5" on each side -> rough size = PTW size + 1" total.
    rough_half_sizes = (
        create_v2(ptw_size[0] / scalar(2) + inches(1, 2), ptw_size[0] / scalar(2) + inches(1, 2)),
        create_v2(ptw_size[1] / scalar(2) + inches(1, 2), ptw_size[1] / scalar(2) + inches(1, 2)),
    )

    mortise_ptw_size = ptw_size + create_v2(inches(2), inches(2))
    mortise_rough_half_sizes = (
        create_v2(mortise_ptw_size[0] / scalar(2) + inches(1, 2), mortise_ptw_size[0] / scalar(2) + inches(1, 2)),
        create_v2(mortise_ptw_size[1] / scalar(2) + inches(1, 2), mortise_ptw_size[1] / scalar(2) + inches(1, 2)),
    )
    # Receiving (mortise) timber: runs along +X, centered at position
    mortise_timber = Timber(
        length=timber_length,
        size=mortise_ptw_size,
        transform=Transform(
            position=position + create_v3(-timber_length / scalar(2), scalar(0), scalar(0)),
            orientation=compute_timber_orientation(create_v3(scalar(1), scalar(0), scalar(0)), create_v3(scalar(0), scalar(0), scalar(1))),
        ),
        ticket=TimberTicket("mortise"),
        rough_half_sizes=mortise_rough_half_sizes,
    )

    # Tenon timber: approaches from below at 45 degrees from the Y axis in the XY plane.
    angle = pi / scalar(4)  # 45 degrees
    tenon_dir = safe_normalize_vector(create_v3(sin(angle), cos(angle), scalar(0)))
    tenon_width_dir = safe_normalize_vector(create_v3(cos(angle), -sin(angle), scalar(0)))
    tenon_bottom = position - tenon_dir * timber_length
    tenon_timber = Timber(
        length=timber_length,
        size=ptw_size,
        transform=Transform(
            position=tenon_bottom,
            orientation=compute_timber_orientation(tenon_dir, tenon_width_dir),
        ),
        ticket=TimberTicket("tenon"),
        rough_half_sizes=rough_half_sizes,
    )

    arrangement = ButtJointTimberArrangement(
        butt_timber=tenon_timber,
        receiving_timber=mortise_timber,
        butt_timber_end=TimberEnd.TOP,
        front_face_on_butt_timber=TimberLongFace.FRONT,
    )

    return cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=inches(3),
        tenon_height_relative_to_joint=inches(1),
        tenon_length=inches(3),
        mortise_depth=inches(4),
        mortise_shoulder_inset=inches(1),
        relief=ButtJointNotchReliefConfig(notch_from=notch_from),
    )


@pattern('mixed/mortise_and_tenon/brace_joint_mortise_and_tenon', name={"en": "Brace", "ja": "方杖の枘差し"})
def example_brace_joint(position=None, use_round_timbers=False) -> Frame:
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
    return _mortised_brace_frame(position, use_round_timbers, scalar(1, 2), scalar(1, 2),
                                 name="Brace Joint with Mortise and Tenon")


@pattern('mixed/mortise_and_tenon/steep_brace_joint_mortise_and_tenon', name={"en": "Steep brace", "ja": "急な方杖の枘差し"})
def example_steep_brace_joint(position=None, use_round_timbers=False) -> Frame:
    """
    The brace joint with an uneven brace: it meets timber1 at its middle and timber2 a quarter
    of the way along, so it enters one at 26.6 degrees and the other at 63.4.

    Both mortises are bored square to the face, so each hole is stretched along the slope to
    the tenon's footprint: longer at the shallow end, shorter at the steep one.
    """
    return _mortised_brace_frame(position, use_round_timbers, scalar(1, 2), scalar(1, 4),
                                 name="Steep Brace Joint with Mortise and Tenon")


def _mortised_brace_frame(position, use_round_timbers, share_of_timber1, share_of_timber2, name) -> Frame:
    """A corner with a brace mortised into both timbers, meeting each at that share of its length."""
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
        location_on_timber1=timber1.length * share_of_timber1,
        location_on_timber2=timber2.length * share_of_timber2,
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
    tenon_width_relative_to_joint = inches(3)  # 3" wide (parallel to the joint plane)
    tenon_height_relative_to_joint = inches(1)  # 1" tall (perpendicular to the joint plane)
    tenon_length = inches(5)
    mortise_depth = inches(3)


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
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        peg_parameters=peg_params,
        mortise_shoulder_inset=inches(1, 2),
        bore_mortise_perpendicular_to_face=True,
    )

    # Combine miter + both mortise-and-tenon joints into a single Frame
    # Frame.from_joints will handle merging cuts on timbers that appear in multiple joints
    return Frame.from_joints([miter_joint, joint1, joint2], name=name)


@pattern('mixed/mortise_and_tenon/mortise_and_tenon_corner_joint', name={"en": "Corner", "ja": "隅の枘差し"})
def example_mortise_and_tenon_corner_joint(position=None, use_round_timbers=False) -> Joint:
    """
    Corner mortise and tenon joint via cut_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers.

    Canonical right-angle corner arrangement: timber1 (tenon) points +Y, timber2
    (mortise) points +X, meeting at their BOTTOM ends, both 4"x5"x4'.

    Tenon is 3" wide (parallel to the joint plane) x 1" tall (perpendicular to the
    joint plane). tenon_distance_from_end defaults to 0, so the tenon sits flush
    with timber2's end -- a tongue-and-fork style corner joint.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(
        position,
        timber_config=_maybe_round_timber_config(use_round_timbers),
    )

    return cut_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=inches(3),
        tenon_height_relative_to_joint=inches(1),
        tenon_length=inches(3),
        mortise_depth=inches(4),
        # setting this to zero means the tenon is exposed at the end!!
        tenon_distance_from_end = inches(0),
        tenon_lateral_offset = inches(1)
    )


def _make_rough_receiving_timber_arrangement(position=None):
    """
    Canonical butt joint arrangement, but the receiving timber's BACK face -- the tenon's
    "opposite shoulder" axis -- is oversized rough stock (4" actual vs. its 2.5" perfect
    half-size), simulating as-sawn material that hasn't been dressed down to its final
    envelope yet. Shared by the rough/perfect opposite-shoulder examples below so they're
    directly comparable.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(position)
    receiving_timber = replace(
        arrangement.receiving_timber,
        rough_half_sizes=(create_v2(inches(2), inches(2)), create_v2(inches(scalar(5, 2)), inches(4))),
    )
    return replace(arrangement, receiving_timber=receiving_timber)


@pattern('mixed/mortise_and_tenon/compound_offset_parallel_shoulder', name={"en": "Offset with a parallel shoulder", "ja": "胴付きを平行にずらした枘"})
def example_compound_angle_offset_parallel_shoulder(position=None, use_round_timbers=False) -> Joint:
    """
    Mortise and tenon joint with compound angle (45 degrees in both axes),
    1 inch lateral centerline offset, and shoulder parallel to the FRONT face.
    """
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





STOPPED_MORTISE = kiwari(
    tenon_width=kiwari.length(inches(3), minimum=inches(1, 4)),
    tenon_height=kiwari.length(inches(1), minimum=inches(1, 4)),
    tenon_length=kiwari.length(inches(3), minimum=inches(1, 4)),
    mortise_depth=kiwari.length(inches(7, 2), minimum=inches(1, 4)),
    shoulder_inset=kiwari.length(scalar(0), minimum=scalar(0)),
    pegged=kiwari.flag(False),
    peg_shape=kiwari.choice(PegShape, PegShape.ROUND),
    round_timbers=kiwari.flag(False),
)


@pattern("mixed/mortise_and_tenon/stopped_face_aligned", name={"en": "Stopped, face-aligned", "ja": "止め枘、面を揃える"}, kiwari=STOPPED_MORTISE)
def stopped_face_aligned(k: Optional[Kiwari] = None) -> Joint:
    """Cut a stopped mortise with adjustable tenon, shoulder inset, and peg."""
    k = STOPPED_MORTISE.resolve(k)
    arrangement = create_canonical_example_butt_joint_timbers(
        timber_config=_maybe_round_timber_config(k.flag("round_timbers")))
    peg = SimplePegParameters(
        shape=k.choice("peg_shape"), peg_positions=[(inches(1), scalar(0))],
        size=inches(1, 2)) if k.flag("pegged") else None
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement,
        tenon_width_relative_to_joint=k.length("tenon_width"),
        tenon_height_relative_to_joint=k.length("tenon_height"),
        tenon_length=k.length("tenon_length"),
        mortise_depth=k.length("mortise_depth"),
        mortise_shoulder_inset=k.length("shoulder_inset"),
        peg_parameters=peg,
    )


ROUND_ANGLED = kiwari(
    diameter=kiwari.length(inches(1), minimum=inches(1, 4)),
    length=kiwari.length(inches(3), minimum=inches(1, 4)),
    depth=kiwari.length(inches(4), minimum=inches(1, 4)),
    inset=kiwari.length(scalar(0), minimum=scalar(0)),
)


@pattern("mixed/mortise_and_tenon/round_plane_aligned", name={"en": "Round, plane-aligned", "ja": "丸枘、同一平面"}, kiwari=ROUND_ANGLED)
def round_plane_aligned(k: Optional[Kiwari] = None) -> Joint:
    k = ROUND_ANGLED.resolve(k)
    brace = create_canonical_example_brace_joint_timbers()
    arrangement = ButtJointTimberArrangement(
        brace.brace_timber, brace.timber1, TimberEnd.BOTTOM)
    return cut_round_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement, diameter=k.length("diameter"), tenon_length=k.length("length"),
        mortise_depth=k.length("depth"), mortise_shoulder_inset=k.length("inset"))


TUSKED = kiwari(
    width=kiwari.length(inches(2), minimum=inches(1, 4)),
    height=kiwari.length(inches(2), minimum=inches(1, 4)),
    stickout=kiwari.length(inches(3), minimum=inches(2)),
    opposite_inset=kiwari.length(scalar(0), minimum=scalar(0)),
    measure_from=kiwari.choice(MeasureOppositeShoulderFrom, MeasureOppositeShoulderFrom.Perfect),
    rough_stock=kiwari.flag(False),
    tusk_thickness=kiwari.length(inches(3, 2), minimum=inches(1, 4)),
    tusk_width=kiwari.length(inches(1), minimum=inches(1, 4)),
    tusk_angle=kiwari.angle(degrees(10), minimum=degrees(1), maximum=degrees(30)),
)


def _tusked(k: Kiwari, entry: TuskEntryFace) -> Joint:
    arrangement = (_make_rough_receiving_timber_arrangement()
                   if k.flag("rough_stock") else create_canonical_example_butt_joint_timbers())
    arrangement = replace(arrangement, top_face_on_butt_timber=TimberLongFace.FRONT)
    return cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement, tenon_width_relative_to_joint=k.length("width"),
        tenon_height_relative_to_joint=k.length("height"),
        tenon_length_past_opposite_shoulder=k.length("stickout"),
        opposite_mortise_shoulder_inset=k.length("opposite_inset"),
        measure_opposite_shoulder_from=k.choice("measure_from"),
        tusk_parameters=TuskParameters(
            tusk_thickness=k.length("tusk_thickness"), tusk_small_width=k.length("tusk_width"),
            tusk_angle=k.angle("tusk_angle"), tusk_tip_stickout=inches(1),
            tusk_back_stickout=inches(1), entry_face=entry))


@pattern("mixed/tusked_mortise_and_tenon/front_entry", name={"en": "From the front", "ja": "正面から差す"}, kiwari=TUSKED)
def tusked_front(k: Optional[Kiwari] = None) -> Joint:
    return _tusked(TUSKED.resolve(k), TuskEntryFace.Front)


@pattern("mixed/tusked_mortise_and_tenon/top_entry", name={"en": "From the top", "ja": "上から差す"}, kiwari=TUSKED)
def tusked_top(k: Optional[Kiwari] = None) -> Joint:
    return _tusked(TUSKED.resolve(k), TuskEntryFace.Top)


EDGE_TENON = kiwari(
    width=kiwari.length(mm(40)),
    thickness=kiwari.length(mm(8), minimum=mm(1), maximum=mm(20)),
    length=kiwari.length(mm(20), minimum=mm(1), maximum=mm(20)),
    offset=kiwari.length(mm(35)),
)


@pattern('mixed/mortise_and_tenon/board_edge', name={"en": "Tenon on a board edge", "ja": "板の側面の枘"}, kiwari=EDGE_TENON)
def example_board_edge_tenon(k: Optional[Kiwari] = None) -> Joint:
    """Cut an off-center tenon across the grain into a rail parallel to the board."""
    k = EDGE_TENON.resolve(k)
    axes = Orientation.from_z_and_y(z_direction=create_v3(1, 0, 0), y_direction=create_v3(0, 0, 1))
    board = Board(mm(300), create_v2(mm(120), mm(20)), Transform(create_v3(0, 0, mm(10)), axes),
                  TimberTicket("board", reference_features=(TimberFeature.FRONT_LEFT_EDGE,)))
    rail = Board(board.length, create_v2(mm(50), mm(20)),
                 Transform(board.transform.local_to_global(create_v3(mm(65), 0, 0)), axes), TimberTicket("rail"))
    edge = FauxTimber(board, top=TimberFace.RIGHT, front=TimberFace.FRONT)
    return edge.restore_joint(cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        ButtJointTimberArrangement(edge, rail, TimberEnd.TOP),
        tenon_width_relative_to_joint=k.length("width"),
        tenon_height_relative_to_joint=k.length("thickness"),
        tenon_length=k.length("length"),
        mortise_depth=k.length("length") + mm(2),
        tenon_position=create_v2(k.length("offset"), 0),
        relief=None,
    ))


BLIND_WEDGE = kiwari(
    orientation=kiwari.choice(WedgeOrientation, WedgeOrientation.SPREAD_Y),
    edge_inset=kiwari.length(inches(3, 8), about="Distance from each tenon cheek to its kerf centerline"),
    kerf_size=kiwari.length(mm(2), minimum=0),
    wedge_length=kiwari.length(mm(30), optional=True), wedge_angle=kiwari.angle(degrees(8)),
    mortise_side_angle=kiwari.angle(degrees(5)),
)


@pattern("mixed/mortise_and_tenon/blind_wedged", name={"en": "Blind wedged tenon", "ja": "地獄枘"}, kiwari=BLIND_WEDGE)
def blind_wedged_tenon(k: Optional[Kiwari] = None) -> Joint:
    """Cut a 40 mm tenon and flare the blind mortise through its 10 mm of bottom clearance."""
    k = BLIND_WEDGE.resolve(k)
    arrangement = create_canonical_example_butt_joint_timbers(timber_size=create_v2(mm(54), mm(70)),
                                                              timber_length=mm(150))
    tenon_length = mm(40)
    extra_depth = mm(10)
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement, tenon_width_relative_to_joint=mm(40), tenon_height_relative_to_joint=mm(25),
        tenon_length=tenon_length, mortise_depth=tenon_length + extra_depth,
        wedge_parameters=WedgeParameters(
            wedge_orientation=k.choice("orientation"), paired_edge_inset=k.length("edge_inset"),
            wedge_angle=k.angle("wedge_angle"), wedge_length=k.length("wedge_length"), wedge_extra_length=extra_depth,
            tenon_kerf_size=k.length("kerf_size"), mortise_side_angle=k.angle("mortise_side_angle"),
        ),
    )


THROUGH_WEDGE = kiwari(
    stickout=kiwari.length(mm(6), minimum=0, maximum=mm(20)),
    wedge_length=kiwari.length(mm(35), minimum=mm(15), maximum=mm(55)),
    orientation=kiwari.choice(WedgeOrientation, WedgeOrientation.SPREAD_Y),
)


@pattern("mixed/mortise_and_tenon/through_wedged", name={"en": "Through wedged tenon", "ja": "楔締めの通し枘"}, kiwari=THROUGH_WEDGE)
def through_wedged_tenon(k: Optional[Kiwari] = None) -> Joint:
    """Seat a centered wedge in the exposed end of a through tenon."""
    k = THROUGH_WEDGE.resolve(k)
    stock_size = create_v2(mm(54), mm(70))
    arrangement = create_canonical_example_butt_joint_timbers(timber_size=stock_size, timber_length=mm(220))
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement, tenon_width_relative_to_joint=mm(40), tenon_height_relative_to_joint=mm(32),
        tenon_length=stock_size[1] + k.length("stickout"), mortise_depth=None,
        wedge_parameters=WedgeParameters(
            wedge_orientation=k.choice("orientation"), wedge_length=k.length("wedge_length"),
            wedge_angle=degrees(8), tenon_kerf_size=mm(2), mortise_side_angle=degrees(2),
        ),
    )


ANGLED_BLIND_WEDGE = kiwari(
    edge_inset=kiwari.length(inches(3, 8), about="Distance from each tenon cheek to its kerf centerline"),
    approach_angle=kiwari.angle(degrees(30), minimum=degrees(10), maximum=degrees(35),
                               about="Angle between the tenon and the receiving face normal"),
    mortise_side_angle=kiwari.angle(degrees(4), minimum=0, maximum=degrees(8)),
)


@pattern("mixed/mortise_and_tenon/angled_blind_wedged",
         name={"en": "Angled blind wedged tenon", "ja": "斜めの地獄枘"}, kiwari=ANGLED_BLIND_WEDGE)
def angled_blind_wedged_tenon(k: Optional[Kiwari] = None) -> Joint:
    """Fit an oblique tenon into a flared blind mortise bored square to the receiving face."""
    k = ANGLED_BLIND_WEDGE.resolve(k)
    arrangement = create_canonical_example_butt_joint_timbers(timber_size=create_v2(mm(60), mm(80)),
                                                              timber_length=mm(220))
    angle = k.angle("approach_angle")
    rotation = Transform(create_v3(0, 0, 0), Orientation.from_angle_axis(angle, create_v3(0, 0, 1)))
    receiver = arrangement.receiving_timber
    arrangement = replace(arrangement, receiving_timber=replace(receiver, transform=rotation * receiver.transform))
    mortise_depth = mm(45)
    extra_depth = mm(10)
    tenon_width = mm(56)
    # Start with stock reaching the far corner, then crop each cheek to the oblique pocket.
    tenon_length = mortise_depth / cos(angle) + tenon_width / 2 * tan(angle)
    return cut_mortise_and_tenon_joint(
        arrangement, tenon_size=create_v2(mm(24), tenon_width), tenon_length=tenon_length, mortise_depth=mortise_depth,
        set_mortise_shoulder_parallel_to_face=TimberLongFace.FRONT,
        mortise_shoulder_distance_from_centerline_or_centerplane=receiver.size[1] / 2,
        bore_mortise_perpendicular_to_face=True,
        wedge_parameters=WedgeParameters(
            paired_edge_inset=k.length("edge_inset"), wedge_length=mm(18), wedge_extra_length=extra_depth,
            wedge_angle=degrees(8), tenon_kerf_size=mm(2), mortise_side_angle=k.angle("mortise_side_angle"),
        ),
    )
