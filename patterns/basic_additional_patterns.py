# Last checked on kumiki 0.9.0
"""Build automatically sized joint and decoration recipes."""

from dataclasses import replace
from typing import Optional

from kumiki import *
from kumiki.example_shavings import (
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_brace_joint_timbers,
)


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
