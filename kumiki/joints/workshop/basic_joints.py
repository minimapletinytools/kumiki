"""
Kumiki - Basic joint construction functions

Convenience wrappers (cut_basic_* and cut_basic_plain_*) that call the underlying
joint functions with sensible default sizing. Use these for quick prototyping; for
full control over dimensions and parameters, call the underlying cut_plain_*,
cut_mortise_and_tenon_*, or cut_lapped_* functions directly.
"""

from kumiki.construction import arrangement_error
import warnings
from dataclasses import replace
from typing import Optional, List, Tuple, Union, cast
from typing_extensions import deprecated
from kumiki.timber import *
from kumiki.rule import *
from .corner import (
    cut_plain_miter_joint,
    cut_plain_miter_joint_on_face_aligned_timbers,
    cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers,
    cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers,
)
from .butt import (
    cut_plain_butt_joint,
    cut_plain_butt_joint_on_face_aligned_timbers,
    cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers,
    cut_dropin_dovetail_butt_joint_on_face_aligned_timbers,
    cut_dropin_housed_butt_joint_on_face_aligned_timbers,
    cut_wedged_half_dovetail_joint_on_face_aligned_timbers as cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_splined_opposing_double_butt_joint_on_face_aligned_timbers,
)
from .mixed import (
    cut_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers,
    TuskParameters,
)
from .splice import (
    cut_plain_butt_splice_joint_on_aligned_timbers,
    cut_plain_splice_lap_joint_on_aligned_timbers,
    cut_lapped_gooseneck_joint_on_aligned_timbers,
    cut_rebated_oblique_and_dadoed_scarf_joint_on_aligned_timbers,
    cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers,
)
from .cross import (
    cut_plain_cross_lap_joint,
    cut_plain_cross_lap_house_joint,
)
from kumiki.construction import (
    ButtJointTimberArrangement,
    SpliceJointTimberArrangement,
    CornerJointTimberArrangement,
    CrossJointTimberArrangement,
    DoubleButtJointTimberArrangement,
)
from .shavings.build_a_butt import SimplePegParameters, DovetailTenonWedgeAccessoryParameters

from kumiki.construction import ButtJointBoardArrangement

# ============================================================================
# Plain Joint Wrappers
# ============================================================================

def cut_basic_plain_miter_joint(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two timbers, cutting each end at half the angle between them.

    Convenience wrapper with no additional sizing logic. See `cut_plain_miter_joint` for details.

    Args:
        arrangement: Corner joint arrangement specifying the two timbers and their ends.

    Returns:
        Joint object containing the two CutTimbers.
    """
    return cut_plain_miter_joint(arrangement)


def cut_basic_plain_miter_joint_on_face_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint:
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


def cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = scalar(0),
) -> Joint:
    """
    Creates a tongue-and-fork corner joint (corner bridle style).

    Convenience wrapper around `cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers`. Timbers must be plane-aligned
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
    return cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
    )


def cut_basic_tongue_and_fork_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = scalar(0),
) -> Joint:
    """Compatibility alias for `cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers`."""
    return cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
    )


def cut_basic_tongue_and_fork_butt_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tongue_thickness: Optional[Numeric] = None,
    tongue_position: Numeric = scalar(0),
    shoulder_inset: Numeric = scalar(0),
) -> Joint:
    """
    Creates a tongue-and-fork butt joint.

    Convenience wrapper around `cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers`. Timbers must be
    plane-aligned and non-parallel. The receiving (tongue) timber is not end-cut.

    Args:
        arrangement: Butt arrangement where butt_timber is fork and receiving_timber is tongue.
        tongue_thickness: Tongue thickness along shared plane normal. None defaults to 1/3
            of tongue timber dimension in that axis.
        tongue_position: Offset of tongue center from centerline in shared plane normal axis.
        shoulder_inset: Distance from receiving timber entry face to shoulder plane.

    Returns:
        Joint object containing both cut timbers.
    """
    error = arrangement.check_plane_aligned()
    assert error is None, error
    return cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tongue_thickness=tongue_thickness,
        tongue_position=tongue_position,
        shoulder_inset=shoulder_inset,
    )


def cut_basic_plain_butt_joint(arrangement: ButtJointTimberArrangement) -> Joint:
    """
    Creates a butt joint where the butt timber is cut flush with the receiving timber's face.

    The butt timber's end is cut along the plane of the best-matching long face of the
    receiving timber. Works at any non-parallel angle. The receiving timber is not cut.
    Convenience wrapper; see `cut_plain_butt_joint` for details.

    Args:
        arrangement: Butt joint arrangement with butt_timber, receiving_timber, butt_timber_end.

    Returns:
        Joint object containing the cut butt timber and uncut receiving timber.
    """
    return cut_plain_butt_joint(arrangement)


def cut_basic_plain_butt_joint_on_face_aligned_timbers(arrangement: ButtJointTimberArrangement) -> Joint:
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


def cut_basic_plain_butt_splice_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement) -> Joint:
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


@deprecated("Use cut_basic_plain_cross_lap_joint instead")
def cut_basic_plain_cross_lap_joint_on_face_aligned_timbers(arrangement: CrossJointTimberArrangement) -> Joint:
    """Forward to the general basic cross lap."""
    return cut_basic_plain_cross_lap_joint(arrangement)


@deprecated("Use cut_basic_plain_cross_lap_house_joint instead")
def cut_basic_plain_house_joint_on_face_aligned_timbers(arrangement: CrossJointTimberArrangement) -> Joint:
    """Forward to the general basic housing."""
    return cut_basic_plain_cross_lap_house_joint(arrangement)


def cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers(
    arrangement: DoubleButtJointTimberArrangement,
    slot_facing_end_on_receiving_timber: TimberEnd,
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
        joint_plane_normal = safe_normalize_vector(cross_product(butt_1_len, receiving_len))
        peg_face = arrangement.butt_timber_1.get_closest_oriented_long_face_from_global_direction(
            joint_plane_normal
        )
        arrangement_with_peg_face = replace(
            arrangement,
            front_face_on_butt_timber_1=peg_face,
        )

    default_peg_parameters = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(mm(30), scalar(0))],
        size=mm(15),
    )

    butt_timber_1 = arrangement_with_peg_face.butt_timber_1
    receiving_timber = arrangement_with_peg_face.receiving_timber

    butt_length_direction_global = butt_timber_1.get_length_direction_global()
    receiving_length_direction_global = receiving_timber.get_length_direction_global()
    slot_direction_global = receiving_timber.get_face_direction_global(
        slot_facing_end_on_receiving_timber
    )
    joint_plane_normal_global = safe_normalize_vector(
        cross_product(butt_length_direction_global, receiving_length_direction_global)
    )

    slot_face_on_butt_1 = butt_timber_1.get_closest_oriented_long_face_from_global_direction(
        slot_direction_global
    )

    slot_thickness = receiving_timber.get_size_in_direction_3d(
        joint_plane_normal_global
    ) / scalar(3)
    slot_depth = butt_timber_1.get_size_in_face_normal_axis(slot_face_on_butt_1) / scalar(2)
    spline_length = receiving_timber.get_size_in_direction_3d(
        butt_length_direction_global
    ) * scalar(4)

    return cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
        arrangement=arrangement_with_peg_face,
        slot_thickness=slot_thickness,
        slot_depth=slot_depth,
        spline_length=spline_length,
        slot_facing_end_on_receiving_timber=slot_facing_end_on_receiving_timber,
        spline_extra_depth=None,
        slot_symmetric_extra_length=mm(3),
        shoulder_symmetric_inset=scalar(0),
        slot_lateral_offset=scalar(0),
        peg_parameters=default_peg_parameters,
    )


def cut_basic_plain_splice_lap_joint_on_aligned_timbers(
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


def cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
) -> Joint:
    """
    Creates a half-blind tenoned, dadoed, rabbeted scarf joint (金輪継ぎ / Kanawa Tsugi)
    with default proportions.

    Timber width is timber1's dimension normal to front_face_on_timber1.rotate_right().
    Rebated shoulder depth, dado depth and height, and stub tenon width are 1/5 of
    that width. Scarf length is 4 times that width. An unset front face defaults
    to FRONT.

    Args:
        arrangement: Splice joint timber arrangement. Timbers must be face-aligned with parallel axes.

    Returns:
        Joint object containing the two CutTimbers.
    """
    error = arrangement.check_face_aligned_and_parallel_axis()
    assert error is None, error

    front_face = (
        arrangement.front_face_on_timber1
        if arrangement.front_face_on_timber1 is not None
        else TimberLongFace.FRONT
    )
    if arrangement.front_face_on_timber1 is None:
        arrangement = replace(arrangement, front_face_on_timber1=front_face)

    timber_width = arrangement.timber1.get_size_in_face_normal_axis(front_face.rotate_right())
    rebated_shoulder_depth = timber_width * scalar(1, 5)
    scarf_length = timber_width * scalar(4)
    dado_depth = timber_width * scalar(1, 5)
    dado_height = timber_width * scalar(1, 5)
    stub_tenon_width = timber_width * scalar(1, 5)

    return cut_rebated_oblique_and_dadoed_scarf_joint_on_aligned_timbers(
        arrangement=arrangement,
        rebated_shoulder_depth=rebated_shoulder_depth,
        scarf_length=scarf_length,
        dado_depth=dado_depth,
        dado_height=dado_height,
        stub_tenon_width=stub_tenon_width,
    )


cut_basic_rebated_oblique_and_dadoed_scarf_joint_on_aligned_timbers = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers
cut_basic_kanawa_tsugi_joint_on_aligned_timbers = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers
cut_basic_kanawa_tsugi = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers
cut_basic_金輪継ぎ_joint_on_aligned_timbers = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers
cut_basic_金輪継ぎ = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers
cut_basic_かなわつぎ_joint_on_aligned_timbers = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers
cut_basic_かなわつぎ = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers


# ============================================================================
# Mortise and Tenon Joint Wrappers
# ============================================================================

def cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
    tenon_timber: TimberLike, mortise_timber: TimberLike, tenon_end: TimberEnd,
    use_peg: bool = False,
) -> Joint:
    """Cut the basic stopped tenon using individual face-aligned timbers."""
    arrangement = ButtJointTimberArrangement(tenon_timber, mortise_timber, tenon_end)
    error = arrangement.check_face_aligned_and_orthogonal()
    assert error is None, error
    return cut_basic_mortise_and_tenon_joint(arrangement, use_peg=use_peg)


def cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
    tenon_timber: TimberLike,
    mortise_timber: TimberLike,
    tenon_end: TimberEnd,
) -> Joint:
    """
    Creates a half-dovetail mortise-and-tenon joint between two face-aligned orthogonal
    timbers, with automatic sizing and a wedge.

    Tenon dimensions are derived automatically: full size of the tenon timber along the axis
    parallel to the mortise timber's length (this is also the dovetail's slope axis -- the
    flat dovetail "top" must run along the receiving timber's length axis for its pull-out
    resistance to sit along the joint's load axis), and 1/3 of the mortise timber's size
    along the perpendicular axis. The tenon is a through-tenon (tenon_depth = the mortise
    timber's full size along the entry axis), and dovetail_depth is 1/4 of the tenon's size
    in the dovetail (length) axis. The wedge's taper angle matches the dovetail's own
    slope and its narrow end (wedge_small_height) is 1/8 of the tenon's size in the
    dovetail axis. For a joint without one, or for full control over sizing, use
    `cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers` directly.

    Args:
        tenon_timber: The timber that will receive the dovetail tenon cut.
        mortise_timber: The timber that will receive the dovetail mortise.
        tenon_end: Which end of the tenon timber gets the tenon (TOP or BOTTOM).

    Returns:
        Joint object containing the two CutTimbers and a "wedge" accessory on the
        dovetail's flat side, tapered to match the dovetail's own slope angle.
    """

    assert isinstance(tenon_end, TimberEnd), f"expected TimberEnd, got {type(tenon_end).__name__}"
    assert isinstance(tenon_timber, TimberLike), f"expected TimberLike, got {type(tenon_timber).__name__}"
    assert isinstance(mortise_timber, TimberLike), f"expected TimberLike, got {type(mortise_timber).__name__}"

    # Same "side of the joint" / "length axis" derivation as cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers.
    joint_side_mortise_timber_face = mortise_timber.get_closest_oriented_face_from_global_direction(cross_product(mortise_timber.get_length_direction_global(), tenon_timber.get_face_direction_global(tenon_end.to.face())))
    joint_side_tenon_timber_face = tenon_timber.get_closest_oriented_face_from_global_direction(mortise_timber.get_face_direction_global(joint_side_mortise_timber_face))
    mortise_length_on_tenon_timber_face = tenon_timber.get_closest_oriented_face_from_global_direction(mortise_timber.get_length_direction_global())

    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end.to.face())
    mortise_entry_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(-tenon_end_direction).to.face()

    # Dovetail's flat "top" (and its slope) must run along the axis parallel to the
    # receiving timber's length -- that's a hard requirement of dovetail_tenon_geometry.
    tenon_dovetail_axis_full_size = tenon_timber.get_size_in_face_normal_axis(mortise_length_on_tenon_timber_face)
    tenon_dovetail_axis_dovetail_depth = tenon_dovetail_axis_full_size * scalar(1, 4)
    tenon_dovetail_axis_size = tenon_dovetail_axis_full_size - tenon_dovetail_axis_dovetail_depth
    tenon_other_axis_size = mortise_timber.get_size_in_face_normal_axis(joint_side_mortise_timber_face)*scalar(1, 3)

    if mortise_length_on_tenon_timber_face == TimberLongFace.FRONT or mortise_length_on_tenon_timber_face == TimberLongFace.BACK:
        tenon_size = Matrix([tenon_dovetail_axis_size, tenon_other_axis_size])
    else:
        tenon_size = Matrix([tenon_other_axis_size, tenon_dovetail_axis_size])

    tenon_depth = mortise_timber.get_size_in_face_normal_axis(mortise_entry_face)

    wedge_accessory_parameters = DovetailTenonWedgeAccessoryParameters(
        wedge_angle=atan(tenon_dovetail_axis_dovetail_depth / tenon_depth),
        wedge_extra_height=0
    )

    arrangement = ButtJointTimberArrangement(
        receiving_timber=cast(Timber, mortise_timber),
        butt_timber=cast(Timber, tenon_timber),
        butt_timber_end=tenon_end,
        top_face_on_butt_timber=mortise_length_on_tenon_timber_face.to.long_face(),
    )
    return cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_depth=tenon_depth,
        dovetail_depth=tenon_dovetail_axis_dovetail_depth,
        wedge_accessory_parameters=wedge_accessory_parameters,
    )


# ============================================================================
# Japanese Joint Wrappers
# ============================================================================

def cut_basic_lapped_gooseneck_joint_on_aligned_timbers(
    gooseneck_timber: TimberLike,
    receiving_timber: TimberLike,
    receiving_timber_end: TimberEnd,
    gooseneck_timber_face: TimberLongFace,
) -> Joint:
    """
    Creates a lapped gooseneck splice joint (腰掛鎌継ぎ / Koshikake Kama Tsugi) with default proportions.

    Gooseneck dimensions scale with the timber width: length = 2×width, small_width = 1/4×width,
    large_width = 1/2×width, head_length = 1/2×width. For full control, use
    `cut_lapped_gooseneck_joint_on_aligned_timbers` directly.

    Args:
        gooseneck_timber: The timber with the gooseneck feature cut into it.
        receiving_timber: The timber that receives the gooseneck.
        receiving_timber_end: Which end of the receiving timber is joined.
        gooseneck_timber_face: The face on the gooseneck timber where the profile is visible.

    Returns:
        Joint object containing the two CutTimbers with gooseneck cuts.
    """
    assert isinstance(receiving_timber_end, TimberEnd), f"expected TimberEnd, got {type(receiving_timber_end).__name__}"
    assert isinstance(gooseneck_timber_face, TimberLongFace), f"expected TimberLongFace, got {type(gooseneck_timber_face).__name__}"
    assert isinstance(gooseneck_timber, Timber), f"expected Timber, got {type(gooseneck_timber).__name__}"
    assert isinstance(receiving_timber, Timber), f"expected Timber, got {type(receiving_timber).__name__}"
    width = gooseneck_timber.get_size_in_face_normal_axis(gooseneck_timber_face.rotate_right())
    gooseneck_length = width*scalar(2)
    gooseneck_small_width = width*scalar(1, 4)
    gooseneck_large_width = width*scalar(1, 2)
    gooseneck_head_length = width*scalar(1, 2)
    gooseneck_timber_end = TimberEnd.BOTTOM if receiving_timber_end == TimberEnd.TOP else TimberEnd.TOP

    return cut_lapped_gooseneck_joint_on_aligned_timbers(
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


def cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement, *, receiving_timber_shoulder_inset: Numeric = scalar(0),
) -> Joint:
    """Cut a housed dovetail with length and neck width each half the butt timber's profile width."""
    face = arrangement.front_face_on_butt_timber
    assert face is not None, "Set front_face_on_butt_timber to select the drop-in direction"
    width = arrangement.butt_timber.get_size_in_face_normal_axis(face.rotate_right())
    return cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
        arrangement, receiving_timber_shoulder_inset=receiving_timber_shoulder_inset,
        dovetail_length=width / 2, dovetail_small_width=width / 2, dovetail_angle=atan(scalar(1, 6)))


def cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers(
    housed_timber: TimberLike,
    receiving_timber: TimberLike,
    housed_timber_end: TimberEnd,
    housed_timber_face: TimberLongFace,
    receiving_timber_shoulder_inset: Numeric = scalar(0),
) -> Joint:
    """
    Creates a drop-in housed butt joint (大入れ仕口 / Oire Shiguchi) with default proportions.

    All housing dimensions (housing_length and housing_width) are auto-calculated from the
    housed timber's size. For full control, use `cut_dropin_housed_butt_joint_on_face_aligned_timbers` directly.

    Args:
        housed_timber: The timber with the housed end.
        receiving_timber: The timber that receives the housing pocket.
        housed_timber_end: Which end of the housed timber is cut.
        housed_timber_face: The face on the housed timber where the pocket profile is open (top face).
        receiving_timber_shoulder_inset: Distance to inset the shoulder notch. Default 0.

    Returns:
        Joint object containing the two CutTimbers with housing cuts.
    """
    assert isinstance(housed_timber_end, TimberEnd), f"expected TimberEnd, got {type(housed_timber_end).__name__}"
    assert isinstance(housed_timber_face, TimberLongFace), f"expected TimberLongFace, got {type(housed_timber_face).__name__}"
    assert isinstance(housed_timber, TimberLike), f"expected TimberLike, got {type(housed_timber).__name__}"
    assert isinstance(receiving_timber, TimberLike), f"expected TimberLike, got {type(receiving_timber).__name__}"

    width = housed_timber.get_size_in_face_normal_axis(housed_timber_face.rotate_right())
    housing_length = width / scalar(2)
    housing_width = width

    return cut_dropin_housed_butt_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=receiving_timber,
            butt_timber=housed_timber,
            butt_timber_end=housed_timber_end,
            front_face_on_butt_timber=housed_timber_face,
        ),
        receiving_timber_shoulder_inset=receiving_timber_shoulder_inset,
        housing_length=housing_length,
        housing_width=housing_width,
    )


def cut_basic_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
) -> Joint:
    """
    Creates a mitered and keyed lap joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi) with default proportions.

    Combines a miter cut with interlocking finger laps on the inside of the corner for
    mechanical strength. All lap and key dimensions are auto-calculated. For full control,
    use `cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers` directly.

    Args:
        arrangement: Corner joint arrangement. Timbers must be plane-aligned and
            `front_face_on_timber1` must specify the reference miter face on timber1.

    Returns:
        Joint object containing the two CutTimbers with miter and finger cuts.
    """
    error = arrangement.check_plane_aligned()
    assert error is None, error
    if arrangement.front_face_on_timber1 is None:
        raise arrangement_error("arrangement.front_face_on_timber1 must be set to determine the reference miter face", arrangement)
    return cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
        arrangement=arrangement
    )


def cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
) -> Joint:
    """
    Creates a tusked through mortise-and-tenon joint with automatic sizing.

    front_face_on_butt_timber/top_face_on_butt_timber are auto-derived when not already set
    on the arrangement: front_face is the butt timber's long face parallel to the joint
    alignment plane, and top_face is 90 degrees from it (the tusk enters from this face, since
    TuskParameters.entry_face defaults to Front). Tenon dimensions are derived automatically:
    1/3 of the butt timber's size along the front-face axis, and 4/5 of its size along the
    top-face axis. For full control over sizing, use
    `cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers` directly.

    Args:
        arrangement: Butt joint arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must be plane-aligned.

    Returns:
        Joint object with cuts on both timbers and a "tusk" accessory.
    """
    error = arrangement.check_plane_aligned()
    assert error is None, error

    front_face = arrangement.front_face_on_butt_timber
    if front_face is None:
        front_face = arrangement.butt_timber.get_closest_oriented_long_face_from_global_direction(arrangement.compute_normalized_timber_cross_product())
        arrangement = replace(arrangement, front_face_on_butt_timber=front_face)
    top_face = arrangement.top_face_on_butt_timber
    if top_face is None:
        top_face = front_face.rotate_right()
        arrangement = replace(arrangement, top_face_on_butt_timber=top_face)

    # The front face is parallel to the joint plane, so its axis is the tenon's height relative to the joint.
    front_face_size = arrangement.butt_timber.get_size_in_face_normal_axis(front_face) / scalar(3)
    top_face_size = arrangement.butt_timber.get_size_in_face_normal_axis(top_face) * scalar(4/5)

    mortise_insertion_face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(-arrangement.butt_timber.get_face_direction_global(arrangement.butt_timber_end))
    # center to center
    mortise_length = arrangement.receiving_timber.get_size_in_face_normal_axis(mortise_insertion_face)
    acute_angle = arrangement.compute_arrangement_acute_angle()
    # center to tip
    mortise_length_tip = mortise_length + top_face_size * cos(acute_angle) / 2
    tenon_length_past_opposite_shoulder = max(mortise_length_tip, front_face_size*2)

    tusk = TuskParameters(
        tusk_thickness = top_face_size * scalar(2/5),
        tusk_small_width = min(tenon_length_past_opposite_shoulder/scalar(2), min(front_face_size, top_face_size))
    )

    return cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=top_face_size,
        tenon_height_relative_to_joint=front_face_size,
        tenon_length_past_opposite_shoulder=tenon_length_past_opposite_shoulder,
        tusk_parameters=tusk,
    )



def cut_basic_plain_corner_lap_joint_on_plane_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint:
    """Cut a half-depth corner lap on plane-aligned timbers."""
    from .corner.plain_corner_lap_joint import cut_plain_corner_lap_joint_on_plane_aligned_timbers
    return cut_plain_corner_lap_joint_on_plane_aligned_timbers(arrangement)


def cut_basic_plain_cross_lap_joint(arrangement: CrossJointTimberArrangement) -> Joint:
    """Cut an equal cross lap with the default scribe relief."""
    return cut_plain_cross_lap_joint(arrangement)


def cut_basic_plain_cross_lap_house_joint(arrangement: CrossJointTimberArrangement) -> Joint:
    """Cut a housing in the first timber for the second timber."""
    return cut_plain_cross_lap_house_joint(arrangement)


def cut_basic_multi_cross_lap_joint_on_plane_aligned_timbers(
    timbers: List[TimberLike], starting_face_on_first_timber: TimberFace,
) -> Joint:
    """Cut a chain of cross laps with uniformly spaced cut boundaries."""
    from .cross.multi_cross_lap_joint import cut_multi_cross_lap_joint_on_plane_aligned_timbers
    return cut_multi_cross_lap_joint_on_plane_aligned_timbers(timbers, starting_face_on_first_timber)


def _basic_tenon_dimensions(arrangement: ButtJointTimberArrangement, round_tenon: bool = False, receiving_end: Optional[TimberEnd] = None):
    """Return local tenon size, insertion length, and receiving entry face.

    Reserve a quarter of the available insertion depth beyond the tenon's tip.
    The butt centerline must enter a long face. Corner joints extend the receiving
    end to meet the butt's outside face; other joints stay within its declared ends.
    """
    butt, receiving = arrangement.butt_timber, arrangement.receiving_timber
    direction = butt.get_face_direction_global(arrangement.butt_timber_end)
    origin = receiving.transform.global_to_local(butt.get_bottom_position_global())
    rotation = receiving.orientation.matrix.T
    direction_local = rotation * direction
    bounds = [(-receiving.size[0] / 2, receiving.size[0] / 2),
              (-receiving.size[1] / 2, receiving.size[1] / 2), (scalar(0), receiving.length)]
    intervals = []
    for axis, (low, high) in enumerate(bounds):
        if axis == 2 and receiving_end is not None:
            continue
        velocity = direction_local[axis]
        if safe_zero_test(velocity):
            assert low < origin[axis] < high, "Tenon centerline must intersect the receiving timber"
            continue
        ends = sorted(((low - origin[axis]) / velocity, (high - origin[axis]) / velocity))
        intervals.append((ends[0], ends[1], axis))
    entry, _, entry_axis = max(intervals, key=lambda interval: interval[0])
    exit_distance = min(interval[1] for interval in intervals)
    assert entry < exit_distance and entry_axis != 2, "Tenon must enter a receiving long face"
    entry_face = ((TimberLongFace.LEFT, TimberLongFace.RIGHT),
                  (TimberLongFace.BACK, TimberLongFace.FRONT))[entry_axis][direction_local[entry_axis] < 0]
    center = origin + direction_local * entry
    axes = [rotation * butt.get_width_direction_global(), rotation * butt.get_height_direction_global()]
    normal = arrangement.compute_normalized_timber_cross_product()
    thickness_axis = max(range(2), key=lambda i: Abs(safe_dot_product(
        normal, butt.get_width_direction_global() if i == 0 else butt.get_height_direction_global())))
    sizes = [butt.size[i] * (scalar(1, 3) if i == thickness_axis else scalar(3, 4)) for i in range(2)]
    sizes[thickness_axis] = min(butt.size[thickness_axis], receiving.get_size_in_direction_3d(normal)) / 3
    if round_tenon:
        sizes = [min(min(butt.size), min(receiving.size)) / 3] * 2
    # Project the tenon outline onto the entry face and fit it inside that face.
    projected = [axis - direction_local * axis[entry_axis] / direction_local[entry_axis] for axis in axes]
    scale = scalar(1)
    for i, (low, high) in enumerate(bounds):
        if i == entry_axis or (i == 2 and receiving_end is not None):
            continue
        half_span = sum(Abs(axis[i]) * size / 2 for axis, size in zip(projected, sizes))
        if not safe_zero_test(half_span):
            scale = min(scale, scalar(3, 4) * min(center[i] - low, high - center[i]) / half_span)
    assert scale > 0, "Tenon centerline must lie inside the receiving face"
    sizes = [size * scale for size in sizes]
    earliest_exit = exit_distance - entry
    latest_entry = scalar(0)
    for sign_x in (-1, 1):
        for sign_y in (-1, 1):
            offset = axes[0] * sizes[0] * sign_x / 2 + axes[1] * sizes[1] * sign_y / 2
            for i, (low, high) in enumerate(bounds):
                if i == 2 and receiving_end is not None:
                    continue
                velocity = direction_local[i]
                if safe_zero_test(velocity):
                    continue
                near, far = sorted(((low - center[i] - offset[i]) / velocity,
                                    (high - center[i] - offset[i]) / velocity))
                latest_entry = max(latest_entry, near)
                earliest_exit = min(earliest_exit, far)
    assert earliest_exit > latest_entry, "No depth remains for a stopped tenon"
    length = latest_entry + (earliest_exit - latest_entry) * scalar(3, 4)
    return create_v2(*sizes), length, entry_face


def _basic_peg(arrangement: ButtJointTimberArrangement, size: V2, length: Numeric):
    """Return the arrangement with a peg face and one proportionally sized square peg."""
    if arrangement.front_face_on_butt_timber is None:
        face = arrangement.butt_timber.get_closest_oriented_long_face_from_global_direction(
            arrangement.compute_normalized_timber_cross_product())
        arrangement = replace(arrangement, front_face_on_butt_timber=face)
    from .shavings.build_a_butt import locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face, locate_tenon_origin_on_shoulder
    direction = arrangement.butt_timber.get_face_direction_global(arrangement.butt_timber_end)
    receiving = arrangement.receiving_timber
    face = receiving.get_closest_oriented_long_face_from_global_direction(-direction)
    plane = locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face(
        arrangement, receiving.get_size_in_face_normal_axis(face) / 2, face)
    origin = locate_tenon_origin_on_shoulder(plane, arrangement.butt_timber,
                                           arrangement.butt_timber_end, create_v2(0, 0))
    peg_size = min(min(size), length) / 6
    low, high = peg_size, length - peg_size
    # Keep the peg inside the declared receiving ends, including at a corner.
    along = receiving.get_length_direction_global()
    velocity = safe_dot_product(direction, along)
    station = safe_dot_product(origin - receiving.get_bottom_position_global(), along)
    if not safe_zero_test(velocity):
        start, stop = sorted(((peg_size - station) / velocity,
                              (receiving.length - peg_size - station) / velocity))
        low, high = max(low, start), min(high, stop)
    assert low <= high, "No room for a peg inside the receiving timber's declared ends"
    distance = max(low, min(length / 3, high))
    peg = SimplePegParameters(shape=PegShape.SQUARE, peg_positions=[(distance, scalar(0))],
                              size=peg_size, tenon_hole_offset=scalar(0))
    return arrangement, peg


def cut_basic_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement, *, use_peg: bool = False,
) -> Joint:
    """Cut a centered rectangular tenon with a quarter-depth reserve in the receiver.

    Start with 3/4 of the butt's in-plane size and 1/3 of the smaller transverse
    timber dimension; reduce both to fit the receiving face. The shoulder follows that entry face.
    """
    from .mixed import cut_mortise_and_tenon_joint
    size, length, face = _basic_tenon_dimensions(arrangement)
    peg = None
    if use_peg:
        arrangement, peg = _basic_peg(arrangement, size, length)
    return cut_mortise_and_tenon_joint(
        arrangement, tenon_size=size, tenon_length=length, mortise_depth=length,
        set_mortise_shoulder_parallel_to_face=face,
        mortise_shoulder_distance_from_centerline_or_centerplane=arrangement.receiving_timber.get_size_in_face_normal_axis(face) / 2,
        peg_parameters=peg)


def cut_basic_round_mortise_and_tenon_joint(arrangement: ButtJointTimberArrangement) -> Joint:
    """Cut a centered round tenon with a quarter-depth reserve in the receiver.

    Start with a third of the smallest cross-section dimension of either timber
    and reduce it to fit the entry face.
    """
    from .mixed import cut_round_mortise_and_tenon_joint
    size, length, face = _basic_tenon_dimensions(arrangement, round_tenon=True)
    return cut_round_mortise_and_tenon_joint(
        arrangement, diameter=size[0], tenon_length=length, mortise_depth=length,
        set_mortise_shoulder_parallel_to_face=face,
        mortise_shoulder_distance_from_centerline_or_centerplane=arrangement.receiving_timber.get_size_in_face_normal_axis(face) / 2)


def cut_basic_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement, *, use_peg: bool = False,
) -> Joint:
    """Cut a centered stopped corner tenon with shoulders on both sides."""
    from .mixed import cut_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers
    butt = ButtJointTimberArrangement(arrangement.timber1, arrangement.timber2,
                                     arrangement.timber1_end, front_face_on_butt_timber=arrangement.front_face_on_timber1)
    size, length, _ = _basic_tenon_dimensions(butt, receiving_end=arrangement.timber2_end)
    normal = arrangement.compute_normalized_timber_cross_product()
    height_face = arrangement.timber1.get_closest_oriented_long_face_from_global_direction(normal)
    height_index = arrangement.timber1.get_size_index_in_long_face_normal_axis(height_face)
    width_index = 1 - height_index
    peg = None
    if use_peg:
        butt, peg = _basic_peg(butt, size, length)
        arrangement = replace(arrangement, front_face_on_timber1=butt.front_face_on_butt_timber)
    return cut_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(
        arrangement, tenon_width_relative_to_joint=size[width_index],
        tenon_height_relative_to_joint=size[height_index], tenon_length=length, mortise_depth=length,
        tenon_distance_from_end=(arrangement.timber1.size[width_index] - size[width_index]) / 2,
        peg_parameters=peg)


def cut_basic_tongue_and_groove_joint(tongue_board: Board, groove_board: Board) -> Joint:
    """Cut a tongue within the shared thickness and overlap of two boards."""
    from .board import cut_tongue_and_groove_joint
    other = tongue_board.transform.global_to_local(groove_board.transform.position)
    low = max(-tongue_board.size[1] / 2, other[1] - groove_board.size[1] / 2)
    high = min(tongue_board.size[1] / 2, other[1] + groove_board.size[1] / 2)
    overlap = (tongue_board.size[0] + groove_board.size[0]) / 2 - Abs(other[0])
    assert high > low and overlap > 0, "Boards must overlap in width and thickness"
    return cut_tongue_and_groove_joint(
        tongue_board, groove_board, tongue_depth=min(min(tongue_board.size[1], groove_board.size[1]) / 3, overlap),
        tongue_width=(high - low) / 3, tongue_center_offset=(low + high) / 2)


def cut_basic_practice_sliding_dovetail_joint_on_orthogonal_boards(arrangement: ButtJointBoardArrangement) -> Joint:
    """Cut a centered, untapered sliding dovetail with a 1:6 flare."""
    from .board.board_joints import cut_practice_sliding_dovetail_joint_on_orthogonal_boards, _lateral_positive_dovetail_face
    from kumiki.measuring import locate_face
    butt, receiving = arrangement.butt_timber, arrangement.receiving_timber
    front = arrangement.front_face_on_butt_timber
    assert front is not None, "The sliding direction requires front_face_on_butt_timber"
    direction = butt.get_face_direction_global(arrangement.butt_timber_face)
    entry = receiving.get_closest_oriented_face_from_global_direction(-direction)
    lateral = _lateral_positive_dovetail_face(arrangement.butt_timber_face, front)
    width = butt.get_size_in_face_normal_axis(lateral)
    overlap = safe_dot_product(locate_face(butt, arrangement.butt_timber_face).point - locate_face(receiving, entry).point, direction)
    depth = min(receiving.get_size_in_face_normal_axis(entry) / 3, overlap, width / 2)
    assert depth > 0, "Butt board must overlap the receiving board"
    # The underlying cutter measures flare with cosine rather than tangent.
    return cut_practice_sliding_dovetail_joint_on_orthogonal_boards(
        arrangement, dovetail_depth=depth, dovetail_small_width=width / 2,
        dovetail_angle=acos(scalar(1, 6)))


def cut_basic_dovetail_corner_joint(
    arrangement: CornerJointTimberArrangement, *, half_blind: bool = False,
) -> Joint:
    """Cut evenly spaced dovetails, deriving their count and sizes from the timbers.

    Use a 1:6 flare, reduced when a narrow layout cannot accommodate that slope.
    """
    from .corner.dovetail_corner_joint import cut_dovetail_corner_joint, SingleDovetailSizeParameter
    if arrangement.front_face_on_timber1 is None:
        face = arrangement.timber1.get_closest_oriented_long_face_from_global_direction(
            arrangement.compute_normalized_timber_cross_product())
        arrangement = replace(arrangement, front_face_on_timber1=face)
    face = arrangement.front_face_on_timber1
    assert face is not None
    span = arrangement.timber1.get_size_in_face_normal_axis(face)
    entry = arrangement.timber2.get_closest_oriented_long_face_from_global_direction(
        -arrangement.timber1.get_face_direction_global(arrangement.timber1_end))
    thickness = arrangement.timber2.get_size_in_face_normal_axis(entry)
    depth = thickness * (scalar(2, 3) if half_blind else scalar(1))
    slope = min(scalar(1, 6), span / (8 * depth))
    flare = 2 * depth * slope
    count = max(1, int(span / max(thickness * 2, flare * 2) + scalar(1, 2)))
    pitch = span / count
    small_width = (pitch - flare) / 2
    return cut_dovetail_corner_joint(arrangement,
        distances=[pitch / 2] + [pitch] * (count - 1),
        dovetails=[SingleDovetailSizeParameter(angle=atan(slope), small_width=small_width,
                                             depth=depth if half_blind else None)] * count)


def cut_basic_practice_roundover_decoration(timber: BlockLike, edges: List[TimberEdge]) -> Joint:
    """Round selected edges with a radius one quarter of their smallest adjacent dimension."""
    from .decorative.decorative_joints import cut_practice_roundover_decoration, _EDGE_ADJACENT_FACES
    assert edges, "Select at least one edge"
    dimensions = [timber.get_size_in_face_normal_axis(face) for edge in edges for face in _EDGE_ADJACENT_FACES[edge]]
    return cut_practice_roundover_decoration(timber, edges, min(dimensions) / 4)


def cut_basic_practice_rounded_end_decoration(
    timber: BlockLike, rounded_face: TimberFace, rounded_end: TimberFace,
) -> Joint:
    """Cut a centered semicircular end spanning the selected profile."""
    from .decorative.decorative_joints import cut_practice_rounded_end_decoration
    span_face = rounded_end.rotate_about(rounded_face)
    radius = max(timber.get_half_rough_size_in_face_normal_axis(span_face),
                 timber.get_half_rough_size_in_face_normal_axis(span_face.get_opposite_face()))
    return cut_practice_rounded_end_decoration(timber, rounded_face, rounded_end, radius, radius)


def cut_basic_practice_rafter_tail_scallop_corner_end_decoration(
    timber: BlockLike, short_edge: TimberShortEdge,
) -> Joint:
    """Cut a quarter-depth scallop extending one profile depth along the timber."""
    from .decorative.decorative_joints import cut_practice_rafter_tail_scallop_corner_end_decoration
    depth = timber.get_size_in_face_normal_axis(short_edge.long_face)
    return cut_practice_rafter_tail_scallop_corner_end_decoration(
        timber, short_edge, scallop_height=depth / 4, scallop_length=min(depth, timber.length))
