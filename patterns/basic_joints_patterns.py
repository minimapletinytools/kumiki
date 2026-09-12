"""
Example usage of basic joint construction functions
Uses canonical timber configurations from construction.py
"""

from kumiki.kiwari import kiwari
from kumiki.rule import inches, Transform, scalar, create_v2, degrees, Matrix, sqrt
from kumiki.timber import (
    Timber, TimberEnd, TimberFace, TimberLongFace, Peg, Wedge,
    PegShape, create_timber,
    create_v3, V2, CutTimber, Frame
)
from kumiki.ticket import Ticket
from kumiki.joints.workshop.basic_joints import (
    cut_basic_plain_miter_joint,
    cut_basic_plain_miter_joint_on_face_aligned_timbers,
    cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers,
    cut_basic_plain_butt_joint_on_face_aligned_timbers,
    cut_basic_plain_butt_splice_joint_on_aligned_timbers,
    cut_basic_plain_cross_lap_joint_on_face_aligned_timbers,
    cut_basic_plain_house_joint_on_face_aligned_timbers,
    cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers,
    cut_basic_plain_splice_lap_joint_on_aligned_timbers,
    cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_basic_lapped_gooseneck_joint_on_aligned_timbers,
    cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers,
    cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers,
    cut_basic_mitered_and_keyed_lap_joint_on_plane_aligned_timbers,
    cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers,
    cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers,
)
from kumiki.example_shavings import (
    ROUND_STOCK,
    RoundTimberConfig,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_splice_joint_timbers,
    create_canonical_example_cross_joint_timbers,
    create_canonical_example_opposing_double_butt_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_LENGTH,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import Pattern, make_pattern_from_joint


# These two ask the round-stock question plus one of their own, so they
# declare it rather than sharing ROUND_STOCK -- same key name either way.
MORTISE_AND_TENON_OPTIONS = kiwari(
    round_timbers=kiwari.flag(False, about="Cut the joint on round stock instead of square"),
    pegged=kiwari.flag(False, about="Drive a peg through the tenon"),
)

# No `wedged` switch: cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_
# on_face_aligned_timbers takes a use_wedge argument and never reads it, so the
# joint always has its wedge. The old UI toggle did nothing either. A control
# that changes nothing is worse than no control, so this waits on the library.
WEDGED_DOVETAIL_OPTIONS = kiwari(
    round_timbers=kiwari.flag(False, about="Cut the joint on round stock instead of square"),
)


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


def example_basic_miter_joint(position=None):
    """
    Create a basic miter joint using canonical corner joint timbers at a 120-degree angle.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_corner_joint_timbers(
        corner_angle=degrees(120),
        position=position,
    )
    joint = cut_basic_plain_miter_joint(arrangement)

    return joint


def example_basic_miter_joint_face_aligned(position=None):
    """
    Create a basic miter joint on face-aligned timbers using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_plain_miter_joint_on_face_aligned_timbers(arrangement)

    return joint


def example_basic_tongue_and_fork_joint(position=None):
    """
    Create a basic tongue-and-fork corner joint using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers(arrangement)

    return joint


def example_basic_butt_joint(k=None, *, position=None):
    """
    Create a basic butt joint using canonical butt joint timbers.
    """
    use_round_timbers = ROUND_STOCK.resolve(k).flag("round_timbers")
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position, timber_config=_maybe_round_timber_config(use_round_timbers)
    )
    joint = cut_basic_plain_butt_joint_on_face_aligned_timbers(arrangement)

    return joint


def example_basic_butt_splice_joint(position=None):
    """
    Create a basic butt splice joint using canonical splice joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_plain_butt_splice_joint_on_aligned_timbers(arrangement)

    return joint


def example_basic_cross_lap_joint(position=None):
    """
    Create a basic cross lap joint using canonical cross joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_cross_joint_timbers(position=position)
    joint = cut_basic_plain_cross_lap_joint_on_face_aligned_timbers(arrangement)

    return joint


def example_basic_house_joint(position=None):
    """
    Create a basic house joint using canonical cross joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    # TODO offset
    arrangement = create_canonical_example_cross_joint_timbers(position=position, lateral_offset=inches(2))
    joint = cut_basic_plain_house_joint_on_face_aligned_timbers(arrangement)

    return joint


def example_basic_splined_opposing_double_butt_joint(position=None):
    """
    Create a basic splined opposing double butt joint using canonical timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_opposing_double_butt_joint_timbers(position)
    joint = cut_basic_splined_opposing_double_butt_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        slot_facing_end_on_receiving_timber=TimberEnd.TOP,
    )

    return joint


def example_basic_splice_lap_joint(position=None):
    """
    Create a basic splice lap joint using canonical splice joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    from kumiki.construction import SpliceJointTimberArrangement
    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_plain_splice_lap_joint_on_aligned_timbers(
        SpliceJointTimberArrangement(
            timber1=arrangement.timber1,
            timber2=arrangement.timber2,
            timber1_end=arrangement.timber1_end,
            timber2_end=arrangement.timber2_end,
            front_face_on_timber1=TimberLongFace.FRONT,
        )
    )
    return joint


def example_basic_mortise_and_tenon_joint(k=None, *, position=None):
    """
    Create a basic mortise and tenon joint using canonical butt joint timbers.
    """
    k = MORTISE_AND_TENON_OPTIONS.resolve(k)
    use_round_timber = k.flag("round_timbers")
    use_peg = k.flag("pegged")
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position, timber_config=_maybe_round_timber_config(use_round_timber)
    )
    joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=arrangement.butt_timber,
        mortise_timber=arrangement.receiving_timber,
        tenon_end=arrangement.butt_timber_end,
        use_peg=use_peg,
    )

    return joint


def example_basic_wedged_half_dovetail_mortise_and_tenon_joint(k=None, *, position=None):
    """
    Create a basic wedged half-dovetail mortise and tenon joint using canonical butt joint timbers.
    """
    k = WEDGED_DOVETAIL_OPTIONS.resolve(k)
    use_round_timbers = k.flag("round_timbers")
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position, timber_config=_maybe_round_timber_config(use_round_timbers)
    )
    joint = cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=arrangement.butt_timber,
        mortise_timber=arrangement.receiving_timber,
        tenon_end=arrangement.butt_timber_end,
    )

    return joint


def example_basic_lapped_gooseneck_joint(position=None):
    """
    Create a basic lapped gooseneck joint.
    Uses canonical splice joint timbers (parallel timbers meeting at position).

    No round-timber toggle: cut_basic_lapped_gooseneck_joint_on_aligned_timbers
    requires a rectangular Timber (it derives gooseneck proportions from the
    timber's size), so it asserts against RoundTimber.
    """
    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_lapped_gooseneck_joint_on_aligned_timbers(
        gooseneck_timber=arrangement.timber2,
        receiving_timber=arrangement.timber1,
        receiving_timber_end=arrangement.timber1_end,
        gooseneck_timber_face=TimberLongFace.RIGHT,
    )
    return joint


def example_basic_dropin_dovetail_butt_joint(position=None):
    """
    Create a basic housed dovetail butt joint.
    Uses canonical butt joint timbers (receiving along X, butt/dovetail along Y).
    """
    arrangement = create_canonical_example_butt_joint_timbers(position)
    # Face perpendicular to receiving timber length (X): use RIGHT (normal +Z) on butt timber
    dovetail_timber_face = TimberLongFace.RIGHT
    width = arrangement.butt_timber.get_size_in_face_normal_axis(dovetail_timber_face.rotate_right())
    dovetail_length = width / scalar(2)
    dovetail_small_width = width * scalar(1, 2)
    dovetail_large_width = width * scalar(2, 3)
    receiving_timber_shoulder_inset = inches(1)  # 1 inch inset

    joint = cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers(
        dovetail_timber=arrangement.butt_timber,
        receiving_timber=arrangement.receiving_timber,
        dovetail_timber_end=arrangement.butt_timber_end,
        dovetail_timber_face=dovetail_timber_face,
        receiving_timber_shoulder_inset=receiving_timber_shoulder_inset,
        dovetail_length=dovetail_length,
        dovetail_small_width=dovetail_small_width,
        dovetail_large_width=dovetail_large_width
    )
    return joint


def example_basic_dropin_housed_butt_joint(position=None):
    """
    Create a basic housed drop-in butt joint.
    Uses canonical butt joint timbers (receiving along X, butt/housed along Y).
    """
    arrangement = create_canonical_example_butt_joint_timbers(position)
    # Face perpendicular to receiving timber length (X): use RIGHT (normal +Z) on butt timber
    housed_timber_face = TimberLongFace.RIGHT
    receiving_timber_shoulder_inset = inches(1)  # 1 inch inset

    joint = cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers(
        housed_timber=arrangement.butt_timber,
        receiving_timber=arrangement.receiving_timber,
        housed_timber_end=arrangement.butt_timber_end,
        housed_timber_face=housed_timber_face,
        receiving_timber_shoulder_inset=receiving_timber_shoulder_inset,
    )
    return joint


def example_basic_mitered_and_keyed_lap_joint(position=None):
    """
    Create a basic mitered and keyed lap joint using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
        arrangement=arrangement
    )
    
    return joint


def example_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint(position=None):
    """
    Create a basic half-blind tenoned, dadoed, rabbeted scarf joint (金輪継ぎ / Kanawa Tsugi)
    using canonical splice joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    from kumiki.construction import SpliceJointTimberArrangement
    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(
        SpliceJointTimberArrangement(
            timber1=arrangement.timber1,
            timber2=arrangement.timber2,
            timber1_end=arrangement.timber1_end,
            timber2_end=arrangement.timber2_end,
            front_face_on_timber1=TimberLongFace.FRONT,
        )
    )
    return joint


def example_basic_tusked_mortise_and_tenon_joint(position=None):
    """
    Create a basic tusked through mortise-and-tenon joint using canonical butt joint timbers.
    All sizing (tenon dimensions, stickout, and tusk shape) is derived automatically from the
    arrangement.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(position)
    joint = cut_basic_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement
    )
    return joint


patterns = [
    Pattern(path="basic_joints/basic_miter_joint", lambda_=make_pattern_from_joint(example_basic_miter_joint), pattern_type='frame', tags=['main']),
    Pattern(path="basic_joints/basic_miter_joint_face_aligned", lambda_=make_pattern_from_joint(example_basic_miter_joint_face_aligned), pattern_type='frame'),
    Pattern(path="basic_joints/basic_tongue_and_fork_corner_joint", lambda_=make_pattern_from_joint(example_basic_tongue_and_fork_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_butt_joint", lambda_=make_pattern_from_joint(example_basic_butt_joint), kiwari=ROUND_STOCK, pattern_type='frame'),
    Pattern(path="basic_joints/basic_butt_splice_joint", lambda_=make_pattern_from_joint(example_basic_butt_splice_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_cross_lap_joint", lambda_=make_pattern_from_joint(example_basic_cross_lap_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_house_joint", lambda_=make_pattern_from_joint(example_basic_house_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_splined_opposing_double_butt_joint", lambda_=make_pattern_from_joint(example_basic_splined_opposing_double_butt_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_splice_lap_joint", lambda_=make_pattern_from_joint(example_basic_splice_lap_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint", lambda_=make_pattern_from_joint(example_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_mortise_and_tenon", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_joint), kiwari=MORTISE_AND_TENON_OPTIONS, pattern_type='frame', tags=['main']),
    Pattern(path="basic_joints/basic_lapped_gooseneck_joint", lambda_=make_pattern_from_joint(example_basic_lapped_gooseneck_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_dropin_dovetail_butt_joint", lambda_=make_pattern_from_joint(example_basic_dropin_dovetail_butt_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_dropin_housed_butt_joint", lambda_=make_pattern_from_joint(example_basic_dropin_housed_butt_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_mitered_and_keyed_lap_joint", lambda_=make_pattern_from_joint(example_basic_mitered_and_keyed_lap_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_wedged_half_dovetail_mortise_and_tenon", lambda_=make_pattern_from_joint(example_basic_wedged_half_dovetail_mortise_and_tenon_joint), kiwari=WEDGED_DOVETAIL_OPTIONS, pattern_type='frame', tags=['main']),
    Pattern(path="basic_joints/basic_tusked_mortise_and_tenon", lambda_=make_pattern_from_joint(example_basic_tusked_mortise_and_tenon_joint), pattern_type='frame'),
]
