"""
Kumiki - Basic joint construction functions

Convenience wrappers (cut_basic_*) that call the underlying joint functions with
sensible default sizing. Use these for quick prototyping; for full control over
dimensions and parameters, call the underlying cut_plain_*, cut_mortise_and_tenon_*,
or cut_lapped_* functions directly.
"""

from dataclasses import replace
from typing import Optional, List, Tuple, cast
from kumiki.timber import *
from kumiki.rule import *
from .plain_joints import (
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
from kumiki.construction import (
    ButtJointTimberArrangement,
    SpliceJointTimberArrangement,
    CornerJointTimberArrangement,
    CrossJointTimberArrangement,
    DoubleButtJointTimberArrangement,
)
from .mortise_and_tenon_joint import (
    cut_mortise_and_tenon_joint_on_FAT,
)
from .build_a_butt_joint_shavings import SimplePegParameters
from .double_butt_joints import cut_splined_opposing_double_butt_joint
from .japanese_joints import (
    cut_lapped_gooseneck_joint,
    cut_housed_dovetail_butt_joint,
    cut_mitered_and_keyed_lap_joint,
)


# ============================================================================
# Plain Joint Wrappers
# ============================================================================

def cut_basic_miter_joint(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two timbers, cutting each end at half the angle between them.

    Convenience wrapper with no additional sizing logic. See `cut_plain_miter_joint` for details.

    Args:
        arrangement: Corner joint arrangement specifying the two timbers and their ends.

    Returns:
        Joint object containing the two CutTimbers.
    """
    return cut_plain_miter_joint(arrangement)


def cut_basic_miter_joint_on_face_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two face-aligned timbers meeting at a 90-degree corner.

    Timbers must be orthogonal. Convenience wrapper; see
    `cut_plain_miter_joint_on_face_aligned_timbers` for details.

    Args:
        arrangement: Corner joint arrangement. Timbers must be face-aligned and orthogonal.

    Returns:
        Joint object containing the two CutTimbers.
    """
    error = arrangement.check_face_aligned_and_orthogonal()
    assert error is None, error
    return cut_plain_miter_joint_on_face_aligned_timbers(arrangement)


def cut_basic_tongue_and_fork_corner_joint(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = Rational(0),
) -> Joint:
    """
    Creates a tongue-and-fork corner joint (corner bridle style).

    Convenience wrapper around `cut_tongue_and_fork_corner_joint`. Timbers must be plane-aligned
    and non-parallel.

    Args:
        arrangement: Corner joint arrangement where timber1 is tongue and timber2 is fork.
        tongue_thickness: Tongue thickness along shared plane normal. None defaults to 1/3
            of tongue timber dimension in that axis.
        tongue_position: Offset of tongue center from centerline in shared plane normal axis.

    Returns:
        Joint object containing both cut timbers.
    """
    error = arrangement.check_plane_aligned()
    assert error is None, error
    return cut_tongue_and_fork_corner_joint(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
    )


def cut_basic_tongue_and_fork_joint(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = Rational(0),
) -> Joint:
    """Compatibility alias for `cut_basic_tongue_and_fork_corner_joint`."""
    return cut_basic_tongue_and_fork_corner_joint(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
    )


def cut_basic_tongue_and_fork_butt_joint(
    arrangement: ButtJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = Rational(0),
) -> Joint:
    """
    Creates a tongue-and-fork butt joint.

    Convenience wrapper around `cut_tongue_and_fork_butt_joint`. Timbers must be
    plane-aligned and non-parallel. The receiving (fork) timber is not end-cut.

    Args:
        arrangement: Butt arrangement where butt_timber is tongue and receiving_timber is fork.
        tongue_thickness: Tongue thickness along shared plane normal. None defaults to 1/3
            of tongue timber dimension in that axis.
        tongue_position: Offset of tongue center from centerline in shared plane normal axis.

    Returns:
        Joint object containing both cut timbers.
    """
    error = arrangement.check_plane_aligned()
    assert error is None, error
    return cut_tongue_and_fork_butt_joint(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
    )


def cut_basic_butt_joint_on_face_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the receiving timber's face.

    The receiving timber is not cut. Convenience wrapper; see
    `cut_plain_butt_joint_on_face_aligned_timbers` for details.

    Args:
        arrangement: Butt joint arrangement. Timbers must be face-aligned and orthogonal.

    Returns:
        Joint object containing the cut butt timber and uncut receiving timber.
    """
    error = arrangement.check_face_aligned_and_orthogonal()
    assert error is None, error
    return cut_plain_butt_joint_on_face_aligned_timbers(arrangement)


def cut_basic_butt_splice_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement) -> Joint:
    """
    Creates a plain butt splice joint between two parallel timbers cut at a shared plane.

    Convenience wrapper with no additional sizing logic. See
    `cut_plain_butt_splice_joint_on_aligned_timbers` for details.

    Args:
        arrangement: Splice joint arrangement. Timbers must be face-aligned with parallel axes.

    Returns:
        Joint object containing the two CutTimbers.
    """
    error = arrangement.check_face_aligned_and_parallel_axis()
    assert error is None, error
    return cut_plain_butt_splice_joint_on_aligned_timbers(arrangement)


def cut_basic_cross_lap_joint(arrangement: CrossJointTimberArrangement) -> Joint:
    """
    Creates a cross-lap joint between two intersecting timbers with equal material removal.

    Material is split equally (half from each timber). Convenience wrapper; see
    `cut_plain_cross_lap_joint` for full control over cut faces and split ratio.

    Args:
        arrangement: Cross joint arrangement. Timbers must be face-aligned and orthogonal.

    Returns:
        Joint object containing the two CutTimbers.
    """
    error = arrangement.check_face_aligned_and_orthogonal()
    assert error is None, error
    return cut_plain_cross_lap_joint(arrangement)


def cut_basic_house_joint(arrangement: CrossJointTimberArrangement) -> Joint:
    """
    Creates a house (dado/housing) joint where the housing timber is notched to receive the housed timber.

    Only the housing timber is cut; the housed timber is unaffected. Convenience wrapper; see
    `cut_plain_house_joint` for details.

    Args:
        arrangement: Cross joint arrangement where timber1 is the housing timber and timber2
                     is the housed timber. Timbers must be face-aligned and orthogonal.

    Returns:
        Joint object containing both timbers.
    """
    error = arrangement.check_face_aligned_and_orthogonal()
    assert error is None, error
    return cut_plain_house_joint(arrangement)


def cut_basic_splined_opposing_double_butt_joint(
    arrangement: DoubleButtJointTimberArrangement,
    slot_facing_end_on_receiving_timber: TimberReferenceEnd,
) -> Joint:
    """
    Creates a splined opposing double butt joint with default sizing and a default peg.

    This basic wrapper always enables pegs and uses a default peg recipe:
    - one square peg
    - distance from shoulder = 30 mm
    - lateral offset = 0
    - peg size = 15 mm

    Args:
        arrangement: Double butt joint arrangement with butt_timber_1, butt_timber_2,
            receiving_timber, butt_timber_1_end, butt_timber_2_end.
        slot_facing_end_on_receiving_timber: Receiving-timber end that the slot faces.

    Returns:
        Joint containing all three cut timbers and spline/peg accessories.
    """
    # Ensure peg entry direction is defined. If unset, choose the butt-1 long face whose
    # normal is closest to the joint-plane normal so drilling is perpendicular to the joint plane.
    arrangement_with_peg_face = arrangement
    if arrangement.front_face_on_butt_timber_1 is None:
        butt_1_len = arrangement.butt_timber_1.get_length_direction_global()
        receiving_len = arrangement.receiving_timber.get_length_direction_global()
        joint_plane_normal = normalize_vector(cross_product(butt_1_len, receiving_len))
        peg_face = arrangement.butt_timber_1.get_closest_oriented_long_face_from_global_direction(
            joint_plane_normal
        )
        arrangement_with_peg_face = replace(
            arrangement,
            front_face_on_butt_timber_1=peg_face,
        )

    default_peg_parameters = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(mm(30), Rational(0))],
        size=mm(15),
    )

    butt_timber_1 = arrangement_with_peg_face.butt_timber_1
    receiving_timber = arrangement_with_peg_face.receiving_timber

    butt_length_direction_global = butt_timber_1.get_length_direction_global()
    receiving_length_direction_global = receiving_timber.get_length_direction_global()
    slot_direction_global = receiving_timber.get_face_direction_global(
        slot_facing_end_on_receiving_timber
    )
    joint_plane_normal_global = normalize_vector(
        cross_product(butt_length_direction_global, receiving_length_direction_global)
    )

    slot_face_on_butt_1 = butt_timber_1.get_closest_oriented_long_face_from_global_direction(
        slot_direction_global
    )

    slot_thickness = receiving_timber.get_size_in_direction_3d(
        joint_plane_normal_global
    ) / Rational(3)
    slot_depth = butt_timber_1.get_size_in_face_normal_axis(slot_face_on_butt_1) / Rational(2)
    spline_length = receiving_timber.get_size_in_direction_3d(
        butt_length_direction_global
    ) * Integer(4)

    return cut_splined_opposing_double_butt_joint(
        arrangement=arrangement_with_peg_face,
        slot_thickness=slot_thickness,
        slot_depth=slot_depth,
        spline_length=spline_length,
        slot_facing_end_on_receiving_timber=slot_facing_end_on_receiving_timber,
        spline_extra_depth=None,
        slot_symmetric_extra_length=mm(3),
        shoulder_symmetric_inset=Rational(0),
        slot_lateral_offset=Rational(0),
        peg_parameters=default_peg_parameters,
    )


def cut_basic_splice_lap_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
) -> Joint:
    """
    Creates a splice lap joint between two parallel timbers with default half-lap sizing.

    The lap length and shoulder position are derived from the timber face dimension indicated
    by `arrangement.front_face_on_timber1` (defaults to FRONT if None).
    For full control over dimensions, use `cut_plain_splice_lap_joint_on_aligned_timbers` directly.

    Args:
        arrangement: Splice joint arrangement. Timbers must be face-aligned with parallel axes.
                     `front_face_on_timber1` specifies the lap cut face on timber1.

    Returns:
        Joint object containing the two CutTimbers with lap cuts.
    """
    error = arrangement.check_face_aligned_and_parallel_axis()
    assert error is None, error
    lap_face = arrangement.front_face_on_timber1 if arrangement.front_face_on_timber1 is not None else TimberLongFace.FRONT
    lap_length = arrangement.timber1.get_size_in_face_normal_axis(lap_face)
    return cut_plain_splice_lap_joint_on_aligned_timbers(
        arrangement,
        lap_length,
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end=lap_length
    )


# ============================================================================
# Mortise and Tenon Joint Wrappers
# ============================================================================

def cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
    tenon_timber: TimberLike,
    mortise_timber: TimberLike,
    tenon_end: TimberReferenceEnd,
    use_peg: bool = False,
) -> Joint:
    """
    Creates a mortise and tenon joint between two face-aligned orthogonal timbers, with automatic sizing.

    Tenon dimensions are derived automatically: 3/4 of the mortise timber's relevant depth for
    the height and 1/3 of its face width for the width. Tenon length equals the full width of the
    mortise timber. For full control over sizing, use `cut_mortise_and_tenon_joint_on_FAT` directly.

    Args:
        tenon_timber: The timber that will receive the tenon cut.
        mortise_timber: The timber that will receive the mortise hole.
        tenon_end: Which end of the tenon timber gets the tenon (TOP or BOTTOM).
        use_peg: If True, adds a square peg through the joint for draw-bore tightening.

    Returns:
        Joint object containing the two CutTimbers and, if use_peg=True, a Peg accessory.
    """
    assert isinstance(tenon_end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(tenon_end).__name__}"
    # this is the "side" of the joint
    joint_side_mortise_timber_face = mortise_timber.get_closest_oriented_face_from_global_direction(cross_product(mortise_timber.get_length_direction_global(), tenon_timber.get_face_direction_global(tenon_end.to.face())))
    joint_side_tenon_timber_face = tenon_timber.get_closest_oriented_face_from_global_direction(mortise_timber.get_face_direction_global(joint_side_mortise_timber_face))

    # the sizing XY depends on the orientation of the tenon timber relative to the mortise timber
    mortise_length_on_tenon_timber_face = tenon_timber.get_closest_oriented_face_from_global_direction(mortise_timber.get_length_direction_global())

    mortise_timber_entry_face = joint_side_mortise_timber_face.to.long_face().rotate_right().to.face()

    tenon_mortise_length_size = tenon_timber.get_size_in_face_normal_axis(mortise_length_on_tenon_timber_face)*Rational(3,4)
    tenon_mortise_width_size = mortise_timber.get_size_in_face_normal_axis(joint_side_mortise_timber_face)*Rational(1,3)

    if mortise_length_on_tenon_timber_face == TimberLongFace.FRONT or mortise_length_on_tenon_timber_face == TimberLongFace.BACK:
        tenon_size = Matrix([tenon_mortise_length_size, tenon_mortise_width_size])
    else:
        tenon_size = Matrix([tenon_mortise_width_size, tenon_mortise_length_size])
        

    tenon_length = mortise_timber.get_size_in_face_normal_axis(mortise_timber_entry_face)
    mortise_depth = tenon_length

    tenon_position = create_v2(Rational(0), Rational(0))
    peg_parameters = None
    front_face_on_butt_timber = None
    if use_peg:
        front_face_on_butt_timber = joint_side_tenon_timber_face.to.long_face()
        peg_parameters = SimplePegParameters(
            shape=PegShape.SQUARE,
            peg_positions=[cast(Tuple[Numeric, Numeric], (tenon_length / 3, 0))],
            size=inches(1, 2),
            depth=None,
            tenon_hole_offset=inches(Rational(1, 16))
        )

    arrangement = ButtJointTimberArrangement(
        receiving_timber=cast(Timber, mortise_timber),
        butt_timber=cast(Timber, tenon_timber),
        butt_timber_end=tenon_end,
        front_face_on_butt_timber=front_face_on_butt_timber,
    )
    return cut_mortise_and_tenon_joint_on_FAT(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        peg_parameters=peg_parameters,
    )


# ============================================================================
# Japanese Joint Wrappers
# ============================================================================

def cut_basic_lapped_gooseneck_joint(
    gooseneck_timber: TimberLike,
    receiving_timber: TimberLike,
    receiving_timber_end: TimberReferenceEnd,
    gooseneck_timber_face: TimberLongFace,
) -> Joint:
    """
    Creates a lapped gooseneck splice joint (腰掛鎌継ぎ / Koshikake Kama Tsugi) with default proportions.

    Gooseneck dimensions scale with the timber width: length = 2×width, small_width = 1/4×width,
    large_width = 1/2×width, head_length = 1/2×width. For full control, use
    `cut_lapped_gooseneck_joint` directly.

    Args:
        gooseneck_timber: The timber with the gooseneck feature cut into it.
        receiving_timber: The timber that receives the gooseneck.
        receiving_timber_end: Which end of the receiving timber is joined.
        gooseneck_timber_face: The face on the gooseneck timber where the profile is visible.

    Returns:
        Joint object containing the two CutTimbers with gooseneck cuts.
    """
    assert isinstance(receiving_timber_end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(receiving_timber_end).__name__}"
    assert isinstance(gooseneck_timber_face, TimberLongFace), f"expected TimberLongFace, got {type(gooseneck_timber_face).__name__}"
    assert isinstance(gooseneck_timber, Timber), f"expected Timber, got {type(gooseneck_timber).__name__}"
    assert isinstance(receiving_timber, Timber), f"expected Timber, got {type(receiving_timber).__name__}"
    width = gooseneck_timber.get_size_in_face_normal_axis(gooseneck_timber_face.rotate_right())
    gooseneck_length = width*Rational(2)
    gooseneck_small_width = width*Rational(1, 4)
    gooseneck_large_width = width*Rational(1, 2)
    gooseneck_head_length = width*Rational(1, 2)
    gooseneck_timber_end = TimberReferenceEnd.BOTTOM if receiving_timber_end == TimberReferenceEnd.TOP else TimberReferenceEnd.TOP

    return cut_lapped_gooseneck_joint(
        arrangement=SpliceJointTimberArrangement(
            timber1=gooseneck_timber,
            timber2=receiving_timber,
            timber1_end=gooseneck_timber_end,
            timber2_end=receiving_timber_end,
            front_face_on_timber1=gooseneck_timber_face,
        ),
        gooseneck_length=gooseneck_length,
        gooseneck_small_width=gooseneck_small_width,
        gooseneck_large_width=gooseneck_large_width,
        gooseneck_head_length=gooseneck_head_length
    )


def cut_basic_housed_dovetail_butt_joint(
    dovetail_timber: TimberLike,
    receiving_timber: TimberLike,
    dovetail_timber_end: TimberReferenceEnd,
    dovetail_timber_face: TimberLongFace,
    receiving_timber_shoulder_inset: Numeric,
    dovetail_length: Numeric,
    dovetail_small_width: Numeric,
    dovetail_large_width: Numeric,
) -> Joint:
    """
    Creates a housed dovetail butt joint (蟻継ぎ / Ari Tsugi) with default proportions.

    Dovetail dimensions scale with the timber width regardless of the values passed for
    dovetail_length, dovetail_small_width, and dovetail_large_width — those parameters are
    overridden internally (present for API compatibility). For full control, use
    `cut_housed_dovetail_butt_joint` directly.

    Args:
        dovetail_timber: The timber with the dovetail tenon.
        receiving_timber: The timber that receives the dovetail socket.
        dovetail_timber_end: Which end of the dovetail timber is cut.
        dovetail_timber_face: The face on the dovetail timber where the profile is visible.
        receiving_timber_shoulder_inset: Distance to inset the shoulder notch on the receiving timber.
        dovetail_length: Overridden internally by default proportions.
        dovetail_small_width: Overridden internally by default proportions.
        dovetail_large_width: Overridden internally by default proportions.

    Returns:
        Joint object containing the two CutTimbers with dovetail cuts.
    """
    assert isinstance(dovetail_timber_end, TimberReferenceEnd), f"expected TimberReferenceEnd, got {type(dovetail_timber_end).__name__}"
    assert isinstance(dovetail_timber_face, TimberLongFace), f"expected TimberLongFace, got {type(dovetail_timber_face).__name__}"
    assert isinstance(dovetail_timber, Timber), f"expected Timber, got {type(dovetail_timber).__name__}"
    assert isinstance(receiving_timber, Timber), f"expected Timber, got {type(receiving_timber).__name__}"
    width = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.rotate_right())
    dovetail_length = width/Integer(2)
    dovetail_small_width = width*Rational(1, 2)
    dovetail_large_width = width*Rational(2, 3)

    return cut_housed_dovetail_butt_joint(
        arrangement=ButtJointTimberArrangement(
            butt_timber=dovetail_timber,
            receiving_timber=receiving_timber,
            butt_timber_end=dovetail_timber_end,
            front_face_on_butt_timber=dovetail_timber_face,
        ),
        receiving_timber_shoulder_inset=receiving_timber_shoulder_inset,
        dovetail_length=dovetail_length,
        dovetail_small_width=dovetail_small_width,
        dovetail_large_width=dovetail_large_width
    )


def cut_basic_mitered_and_keyed_lap_joint(
    arrangement: CornerJointTimberArrangement,
) -> Joint:
    """
    Creates a mitered and keyed lap joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi) with default proportions.

    Combines a miter cut with interlocking finger laps on the inside of the corner for
    mechanical strength. All lap and key dimensions are auto-calculated. For full control,
    use `cut_mitered_and_keyed_lap_joint` directly.

    Args:
        arrangement: Corner joint arrangement. Timbers must be plane-aligned and
            `front_face_on_timber1` must specify the reference miter face on timber1.

    Returns:
        Joint object containing the two CutTimbers with miter and finger cuts.
    """
    error = arrangement.check_plane_aligned()
    assert error is None, error
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the reference miter face"
    )
    return cut_mitered_and_keyed_lap_joint(
        arrangement=arrangement
    )
