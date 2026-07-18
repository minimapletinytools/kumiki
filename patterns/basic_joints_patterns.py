"""
Example usage of basic joint construction functions
Uses canonical timber configurations from construction.py
"""

from sympy import Matrix, sqrt
from kumiki.rule import inches, Transform, scalar, create_v2
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
)
from kumiki.example_shavings import (
    RoundTimberConfig,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_splice_joint_timbers,
    create_canonical_example_cross_joint_timbers,
    create_canonical_example_opposing_double_butt_joint_timbers,
    _CANONICAL_EXAMPLE_TIMBER_LENGTH,
    _CANONICAL_EXAMPLE_TIMBER_SIZE,
)
from kumiki.patternbook import Pattern, make_pattern_from_joint


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


def example_basic_miter_joint(position=None):
    """
    Create a basic miter joint using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
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


def example_basic_butt_joint(position=None, use_round_timbers=False):
    """
    Create a basic butt joint using canonical butt joint timbers.
    """
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


def example_basic_mortise_and_tenon_joint(position=None, use_round_timbers=False):
    """
    Create a basic mortise and tenon joint using canonical butt joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position, timber_config=_maybe_round_timber_config(use_round_timbers)
    )
    joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=arrangement.butt_timber,
        mortise_timber=arrangement.receiving_timber,
        tenon_end=arrangement.butt_timber_end,
        use_peg=False
    )

    return joint


def example_basic_mortise_and_tenon_joint_with_peg(position=None, use_round_timbers=False):
    """
    Create a basic mortise and tenon joint with peg using canonical butt joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position, timber_config=_maybe_round_timber_config(use_round_timbers)
    )
    joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=arrangement.butt_timber,
        mortise_timber=arrangement.receiving_timber,
        tenon_end=arrangement.butt_timber_end,
        use_peg=True
    )

    return joint


def example_basic_wedged_half_dovetail_mortise_and_tenon_joint(position=None, use_round_timbers=True, use_wedge=False):
    """
    Create a basic wedged half-dovetail mortise and tenon joint using canonical butt joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_butt_joint_timbers(
        position, timber_config=_maybe_round_timber_config(use_round_timbers)
    )
    joint = cut_basic_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=arrangement.butt_timber,
        mortise_timber=arrangement.receiving_timber,
        tenon_end=arrangement.butt_timber_end,
        use_wedge=use_wedge,
    )

    return joint


def example_basic_wedged_half_dovetail_mortise_and_tenon_joint_with_wedge(position=None, use_round_timbers=True):
    """
    Create a basic wedged half-dovetail mortise and tenon joint (with the wedge accessory)
    using canonical butt joint timbers.
    """
    return example_basic_wedged_half_dovetail_mortise_and_tenon_joint(
        position, use_round_timbers=use_round_timbers, use_wedge=True
    )


def example_basic_mortise_and_tenon_joint_imperfect_timber(position=None):
    """
    Create a basic mortise and tenon joint using imperfect 4x4 timbers.

    The timbers are nominally 4x4 (that nominal size drives the joint layout math)
    but their actual stock is 5x5: the RIGHT and BACK faces stay flush with the
    nominal 4x4 reference, while the LEFT and FRONT faces are oversized, extending
    an extra 1" beyond the reference. Timber.from_perfect_timber_within is used to
    attach this asymmetric actual geometry to the perfect timbers produced by the
    canonical butt joint arrangement. The canonical arrangement's tenon enters the
    mortise timber through its FRONT face, so the tenon enters through an imperfect
    (oversized) face.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    nominal_size = create_v2(inches(4), inches(4))
    arrangement = create_canonical_example_butt_joint_timbers(position, timber_size=nominal_size)

    reference_half = inches(4) / scalar(2)
    extended_half = reference_half + inches(1)
    imperfect_half_sizes = (
        create_v2(reference_half, extended_half),  # right (flush), left (extended +1")
        create_v2(extended_half, reference_half),  # front (extended +1"), back (flush)
    )

    tenon_timber = Timber.from_perfect_timber_within(arrangement.butt_timber, nominal_half_sizes=imperfect_half_sizes)
    mortise_timber = Timber.from_perfect_timber_within(arrangement.receiving_timber, nominal_half_sizes=imperfect_half_sizes)

    joint = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
        tenon_timber=tenon_timber,
        mortise_timber=mortise_timber,
        tenon_end=arrangement.butt_timber_end,
        use_peg=False
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
    from sympy import Integer

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


patterns = [
    Pattern(path="basic_joints/basic_miter_joint", lambda_=make_pattern_from_joint(example_basic_miter_joint), pattern_type='frame', tags=['main']),
    Pattern(path="basic_joints/basic_miter_joint_face_aligned", lambda_=make_pattern_from_joint(example_basic_miter_joint_face_aligned), pattern_type='frame'),
    Pattern(path="basic_joints/basic_tongue_and_fork_corner_joint", lambda_=make_pattern_from_joint(example_basic_tongue_and_fork_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_butt_joint", lambda_=make_pattern_from_joint(example_basic_butt_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_butt_splice_joint", lambda_=make_pattern_from_joint(example_basic_butt_splice_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_cross_lap_joint", lambda_=make_pattern_from_joint(example_basic_cross_lap_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_house_joint", lambda_=make_pattern_from_joint(example_basic_house_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_splined_opposing_double_butt_joint", lambda_=make_pattern_from_joint(example_basic_splined_opposing_double_butt_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_splice_lap_joint", lambda_=make_pattern_from_joint(example_basic_splice_lap_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_mortise_and_tenon", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_joint), pattern_type='frame', tags=['main']),
    Pattern(path="basic_joints/basic_mortise_and_tenon/with_peg", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_joint_with_peg), pattern_type='frame'),
    Pattern(path="basic_joints/basic_mortise_and_tenon/imperfect_timber", lambda_=make_pattern_from_joint(example_basic_mortise_and_tenon_joint_imperfect_timber), pattern_type='frame'),
    Pattern(path="basic_joints/basic_lapped_gooseneck_joint", lambda_=make_pattern_from_joint(example_basic_lapped_gooseneck_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_dropin_dovetail_butt_joint", lambda_=make_pattern_from_joint(example_basic_dropin_dovetail_butt_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_dropin_housed_butt_joint", lambda_=make_pattern_from_joint(example_basic_dropin_housed_butt_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_mitered_and_keyed_lap_joint", lambda_=make_pattern_from_joint(example_basic_mitered_and_keyed_lap_joint), pattern_type='frame'),
    Pattern(path="basic_joints/basic_wedged_half_dovetail_mortise_and_tenon", lambda_=make_pattern_from_joint(example_basic_wedged_half_dovetail_mortise_and_tenon_joint), pattern_type='frame', tags=['main']),
    Pattern(path="basic_joints/basic_wedged_half_dovetail_mortise_and_tenon/with_wedge", lambda_=make_pattern_from_joint(example_basic_wedged_half_dovetail_mortise_and_tenon_joint_with_wedge), pattern_type='frame'),
]
