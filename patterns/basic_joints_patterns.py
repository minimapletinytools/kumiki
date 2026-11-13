# Last checked on kumiki 0.9.0
"""
Example usage of basic joint construction functions
Uses canonical timber configurations from construction.py
"""

from dataclasses import replace
from typing import Optional
from kumiki import Frame, Joint, Kiwari, create_v3, pattern
from kumiki.construction import ButtJointTimberArrangement, CornerJointTimberArrangement
from kumiki.kiwari import kiwari
from kumiki.rule import feet, Orientation, inches, Transform, scalar, create_v2, degrees, Matrix, sqrt, atan
from kumiki.timber import (
    Board, TimberEdge, TimberShortEdge, Timber, TimberEnd, TimberFace, TimberLongFace, Peg, Wedge,
    PegShape, create_timber,
    create_v3, V2, CutTimber, Frame
)
from kumiki.ticket import BoardTicket, TimberTicket, Ticket
from kumiki.joints.workshop.basic_joints import (
    cut_basic_mortise_and_tenon_joint,
    cut_basic_round_mortise_and_tenon_joint,
    cut_basic_dovetail_corner_joint,
    cut_basic_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers,
    cut_basic_practice_roundover_decoration,
    cut_basic_practice_rounded_end_decoration,
    cut_basic_practice_rafter_tail_scallop_corner_end_decoration,
    cut_basic_tongue_and_groove_joint,
    cut_basic_practice_sliding_dovetail_joint_on_orthogonal_boards,
    cut_basic_plain_miter_joint,
    cut_basic_plain_miter_joint_on_face_aligned_timbers,
    cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers,
    cut_basic_plain_butt_joint_on_face_aligned_timbers,
    cut_basic_plain_butt_splice_joint_on_aligned_timbers,
    cut_basic_plain_cross_lap_joint,
    cut_basic_plain_cross_lap_house_joint,
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
    create_canonical_example_brace_joint_timbers,
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


# These two ask the round-stock question plus one of their own, so they
# declare it rather than sharing ROUND_STOCK -- same key name either way.
MORTISE_AND_TENON_OPTIONS = kiwari(
    round_timbers=kiwari.flag(False, about="Cut the joint on round stock instead of square"),
    pegged=kiwari.flag(False, about="Drive a peg through the tenon"),
)

WEDGED_DOVETAIL_OPTIONS = kiwari(
    round_timbers=kiwari.flag(False, about="Cut the joint on round stock instead of square"),
)


def _maybe_round_timber_config(use_round_timbers: bool):
    if not use_round_timbers:
        return None
    return RoundTimberConfig(
        diameter=max(_CANONICAL_EXAMPLE_TIMBER_SIZE[0], _CANONICAL_EXAMPLE_TIMBER_SIZE[1]) * sqrt(2)
    )


@pattern("basic_joints/basic_miter_joint", tags=["main"])
def example_basic_miter_joint(position=None) -> Joint:
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


@pattern("basic_joints/basic_miter_joint_face_aligned")
def example_basic_miter_joint_face_aligned(position=None) -> Joint:
    """
    Create a basic miter joint on face-aligned timbers using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_plain_miter_joint_on_face_aligned_timbers(arrangement)

    return joint


@pattern("basic_joints/basic_tongue_and_fork_corner_joint")
def example_basic_tongue_and_fork_joint(position=None) -> Joint:
    """
    Create a basic tongue-and-fork corner joint using canonical corner joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position)
    joint = cut_basic_tongue_and_fork_corner_joint_on_plane_aligned_timbers(arrangement)

    return joint


@pattern("basic_joints/basic_butt_joint", kiwari=ROUND_STOCK)
def example_basic_butt_joint(k: Optional[Kiwari]=None, *, position=None) -> Joint:
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


@pattern("basic_joints/basic_butt_splice_joint")
def example_basic_butt_splice_joint(position=None) -> Joint:
    """
    Create a basic butt splice joint using canonical splice joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_splice_joint_timbers(position)
    joint = cut_basic_plain_butt_splice_joint_on_aligned_timbers(arrangement)

    return joint


@pattern("basic_joints/basic_cross_lap_joint")
def example_basic_cross_lap_joint(position=None) -> Joint:
    """
    Create a basic cross lap joint using canonical cross joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    arrangement = create_canonical_example_cross_joint_timbers(position=position)
    joint = cut_basic_plain_cross_lap_joint(arrangement)

    return joint


@pattern("basic_joints/basic_house_joint")
def example_basic_house_joint(position=None) -> Joint:
    """
    Create a basic house joint using canonical cross joint timbers.
    """
    if position is None:
        position = create_v3(0, 0, 0)

    # TODO offset
    arrangement = create_canonical_example_cross_joint_timbers(position=position, lateral_offset=inches(2))
    joint = cut_basic_plain_cross_lap_house_joint(arrangement)

    return joint


@pattern("basic_joints/basic_splined_opposing_double_butt_joint")
def example_basic_splined_opposing_double_butt_joint(position=None) -> Joint:
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


@pattern("basic_joints/basic_splice_lap_joint")
def example_basic_splice_lap_joint(position=None) -> Joint:
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


@pattern("basic_joints/basic_mortise_and_tenon", tags=["main"], kiwari=MORTISE_AND_TENON_OPTIONS)
def example_basic_mortise_and_tenon_joint(k: Optional[Kiwari]=None, *, position=None) -> Joint:
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


@pattern("basic_joints/basic_wedged_half_dovetail_mortise_and_tenon", tags=["main"], kiwari=WEDGED_DOVETAIL_OPTIONS)
def example_basic_wedged_half_dovetail_mortise_and_tenon_joint(k: Optional[Kiwari]=None, *, position=None) -> Joint:
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


@pattern("basic_joints/basic_lapped_gooseneck_joint")
def example_basic_lapped_gooseneck_joint(position=None) -> Joint:
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


@pattern("basic_joints/basic_dropin_dovetail_butt_joint")
def example_basic_dropin_dovetail_butt_joint(position=None) -> Joint:
    """
    Create a basic housed dovetail butt joint.
    Uses canonical butt joint timbers (receiving along X, butt/dovetail along Y).
    """
    arrangement = create_canonical_example_butt_joint_timbers(position)
    # Face perpendicular to receiving timber length (X): use RIGHT (normal +Z) on butt timber
    dovetail_timber_face = TimberLongFace.RIGHT
    receiving_timber_shoulder_inset = inches(1)  # 1 inch inset

    joint = cut_basic_dropin_dovetail_butt_joint_on_face_aligned_timbers(
        replace(arrangement, front_face_on_butt_timber=dovetail_timber_face),
        receiving_timber_shoulder_inset=receiving_timber_shoulder_inset,
    )
    return joint


@pattern("basic_joints/basic_dropin_housed_butt_joint")
def example_basic_dropin_housed_butt_joint(position=None) -> Joint:
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


@pattern("basic_joints/basic_mitered_and_keyed_lap_joint")
def example_basic_mitered_and_keyed_lap_joint(position=None) -> Joint:
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


@pattern("basic_joints/basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint")
def example_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint(position=None) -> Joint:
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


@pattern("basic_joints/basic_tusked_mortise_and_tenon")
def example_basic_tusked_mortise_and_tenon_joint(position=None) -> Joint:
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


from kumiki.joints.workshop.basic_joints import (
    cut_basic_plain_butt_joint,
    cut_basic_tongue_and_fork_butt_joint_on_plane_aligned_timbers,
    cut_basic_plain_corner_lap_joint_on_plane_aligned_timbers,
    cut_basic_multi_cross_lap_joint_on_plane_aligned_timbers,
)


@pattern("basic_joints/plain_butt_joint/angled")
def basic_plain_butt_angled() -> Joint:
    """Cut a plain butt joint on a brace arrangement."""
    from kumiki.example_shavings import create_canonical_example_brace_joint_timbers
    from kumiki.construction import ButtJointTimberArrangement
    brace = create_canonical_example_brace_joint_timbers()
    return cut_basic_plain_butt_joint(ButtJointTimberArrangement(
        brace.brace_timber, brace.timber1, TimberEnd.BOTTOM))


@pattern("basic_joints/tongue_and_fork_butt_joint")
def basic_tongue_and_fork_butt() -> Joint:
    """Cut a tongue-and-fork butt joint with default proportions."""
    return cut_basic_tongue_and_fork_butt_joint_on_plane_aligned_timbers(
        create_canonical_example_butt_joint_timbers())


@pattern("basic_joints/plain_corner_lap_joint")
def basic_corner_lap() -> Joint:
    """Cut a half-depth corner lap."""
    return cut_basic_plain_corner_lap_joint_on_plane_aligned_timbers(
        create_canonical_example_corner_joint_timbers(corner_angle=degrees(120)))


@pattern("basic_joints/multi_cross_lap_joint")
def basic_multi_cross_lap() -> Joint:
    """Cut uniformly spaced laps in a two-member chain."""
    arrangement = create_canonical_example_cross_joint_timbers()
    return cut_basic_multi_cross_lap_joint_on_plane_aligned_timbers(
        [arrangement.timber1, arrangement.timber2], TimberFace.RIGHT)


DOVETAIL_LAYOUT = kiwari(
    span=kiwari.length(inches(8), minimum=inches(2), maximum=inches(24),
                      about="Layout width; tail count and sizes are derived automatically"),
)


def _dovetail_arrangement(k: Optional[Kiwari]) -> CornerJointTimberArrangement:
    k = DOVETAIL_LAYOUT.resolve(k)
    arrangement = create_canonical_example_right_angle_corner_joint_timbers()
    face = arrangement.front_face_on_timber1
    assert face is not None
    direction = arrangement.timber1.get_face_direction_global(face)
    timbers = []
    for timber in (arrangement.timber1, arrangement.timber2):
        own_face = timber.get_closest_oriented_long_face_from_global_direction(direction)
        index = timber.get_size_index_in_long_face_normal_axis(own_face)
        sizes = [timber.size[0], timber.size[1]]
        sizes[index] = k.length("span")
        timbers.append(replace(timber, size=create_v2(*sizes)))
    return replace(arrangement, timber1=timbers[0], timber2=timbers[1])


def _angled_butt() -> ButtJointTimberArrangement:
    brace = create_canonical_example_brace_joint_timbers()
    return ButtJointTimberArrangement(brace.brace_timber, brace.timber1, TimberEnd.BOTTOM)


@pattern("basic_joints/mortise_and_tenon/angled")
def rectangular_tenon() -> Joint:
    return cut_basic_mortise_and_tenon_joint(_angled_butt())


@pattern("basic_joints/round_mortise_and_tenon/angled")
def round_tenon() -> Joint:
    return cut_basic_round_mortise_and_tenon_joint(_angled_butt())


@pattern("basic_joints/dovetail_corner_joint/through", kiwari=DOVETAIL_LAYOUT)
def dovetail_corner(k: Optional[Kiwari] = None) -> Joint:
    return cut_basic_dovetail_corner_joint(_dovetail_arrangement(k))


@pattern("basic_joints/mortise_and_tenon_corner_joint")
def corner_tenon() -> Joint:
    return cut_basic_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(
        create_canonical_example_corner_joint_timbers(corner_angle=degrees(120)))


def _decorative_timber() -> Timber:
    return Timber(length=feet(4), size=create_v2(inches(4), inches(6)),
                  transform=Transform.identity(), ticket=TimberTicket(path="timber"))


@pattern("basic_joints/roundover")
def roundover() -> Joint:
    return cut_basic_practice_roundover_decoration(
        _decorative_timber(), list(TimberEdge))


@pattern("basic_joints/rounded_end")
def rounded_end() -> Joint:
    return cut_basic_practice_rounded_end_decoration(
        _decorative_timber(), TimberFace.RIGHT, TimberFace.TOP)


@pattern("basic_joints/rafter_tail_scallop")
def rafter_tail() -> Joint:
    return cut_basic_practice_rafter_tail_scallop_corner_end_decoration(
        _decorative_timber(), TimberShortEdge.TOP_BACK)


@pattern("basic_joints/tongue_and_groove")
def tongue_and_groove() -> Joint:
    board_size = create_v2(inches(7), inches(3, 4))
    tongue = Board(length=feet(4), size=board_size, transform=Transform.identity(),
                   ticket=BoardTicket(path="tongue"))
    groove = Board(length=feet(4), size=board_size,
                   transform=Transform(position=create_v3(inches(6), 0, 0),
                                       orientation=Orientation.identity()),
                   ticket=BoardTicket(path="groove"))
    return cut_basic_tongue_and_groove_joint(tongue, groove)


@pattern("basic_joints/sliding_dovetail/side_to_face")
def sliding_dovetail() -> Joint:
    from kumiki.example_shavings import create_canonical_example_board_butt_joint_boards_side_to_face
    return cut_basic_practice_sliding_dovetail_joint_on_orthogonal_boards(
        create_canonical_example_board_butt_joint_boards_side_to_face())


@pattern("basic_joints/dovetail_corner_joint/half_blind", kiwari=DOVETAIL_LAYOUT)
def half_blind_dovetail_corner(k: Optional[Kiwari] = None) -> Joint:
    return cut_basic_dovetail_corner_joint(_dovetail_arrangement(k), half_blind=True)
