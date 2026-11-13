# Last checked on kumiki 0.9.0
"""Basic joint recipes with explicit shape inputs and default optional settings."""

from kumiki import *
from kumiki.example_shavings import (
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_brace_joint_timbers,
)


def _angled_butt() -> ButtJointTimberArrangement:
    brace = create_canonical_example_brace_joint_timbers()
    return ButtJointTimberArrangement(brace.brace_timber, brace.timber1, TimberEnd.BOTTOM)


@pattern("basic_joints/mortise_and_tenon/angled")
def rectangular_tenon() -> Joint:
    return cut_basic_mortise_and_tenon_joint(_angled_butt())


@pattern("basic_joints/mortise_and_tenon/plane_aligned")
def plane_aligned_tenon() -> Joint:
    return cut_basic_mortise_and_tenon_joint_on_plane_aligned_timbers(_angled_butt())


@pattern("basic_joints/round_mortise_and_tenon/angled")
def round_tenon() -> Joint:
    return cut_basic_round_mortise_and_tenon_joint(_angled_butt())


@pattern("basic_joints/round_mortise_and_tenon/plane_aligned")
def plane_aligned_round_tenon() -> Joint:
    return cut_basic_round_mortise_and_tenon_joint_on_plane_aligned_timbers(_angled_butt())


@pattern("basic_joints/dovetail_corner_joint")
def dovetail_corner() -> Joint:
    arrangement = create_canonical_example_right_angle_corner_joint_timbers()
    return cut_basic_dovetail_corner_joint(
        arrangement, distances=[inches(1), inches(2)],
        dovetails=[SingleDovetailSizeParameter(
            angle=atan(scalar(1, 8)), small_width=inches(1, 2)) for _ in range(2)])


@pattern("basic_joints/mortise_and_tenon_corner_joint")
def corner_tenon() -> Joint:
    return cut_basic_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(
        create_canonical_example_right_angle_corner_joint_timbers(),
        tenon_width_relative_to_joint=inches(1),
        tenon_height_relative_to_joint=inches(2), tenon_length=inches(3))


def _decorative_timber() -> Timber:
    return Timber(length=feet(4), size=create_v2(inches(4), inches(6)),
                  transform=Transform.identity(), ticket=TimberTicket(path="timber"))


@pattern("basic_joints/roundover")
def roundover() -> Joint:
    return cut_basic_practice_roundover_decoration(
        _decorative_timber(), list(TimberEdge), inches(1, 2))


@pattern("basic_joints/rounded_end")
def rounded_end() -> Joint:
    return cut_basic_practice_rounded_end_decoration(
        _decorative_timber(), TimberFace.RIGHT, TimberFace.TOP, inches(5), inches(5))


@pattern("basic_joints/rafter_tail_scallop")
def rafter_tail() -> Joint:
    return cut_basic_practice_rafter_tail_scallop_corner_end_decoration(
        _decorative_timber(), TimberShortEdge.TOP_BACK, inches(2), inches(4))


@pattern("basic_joints/path_extrusion_corner_end")
def path_extrusion() -> Joint:
    from kumiki.csg.pathcsg import StraightSegment
    return cut_basic_practice_path_extrusion_corner_end_decoration(
        _decorative_timber(), TimberShortEdge.BOTTOM_RIGHT,
        [StraightSegment(create_v2(0, inches(2)), create_v2(inches(2), 0))])


@pattern("basic_joints/straight_end_cut")
def straight_end() -> Joint:
    return cut_basic_practice_straight_angled_end_cut_decoration(
        _decorative_timber(), TimberFace.FRONT, inches(3))


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


def _post_on_beam_with_dovetail(position, taper_angle):
    if position is None:
        position = create_v3(0, 0, 0)
    # The beam runs along x with its top face at z=50mm; the post stands on it from z=0.
    beam = create_timber(bottom_position=position + create_v3(mm(-500), 0, 0), length=mm(1000),
                         size=create_v2(mm(100), mm(100)), length_direction=create_v3(1, 0, 0),
                         width_direction=create_v3(0, 1, 0), ticket="beam")
    post = create_timber(bottom_position=position, length=mm(600), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")
    # Slides along x, across the post's width. The neck is 40mm wide at the beam's top face and the
    # tongue flares at 15 degrees down into the beam for 30mm, so the post cannot lift out.
    dovetail = FreeDovetailShape(
        origin=Transform(position=position + create_v3(0, 0, mm(50)),
                         orientation=Orientation.from_x_and_y(create_v3(1, 0, 0), create_v3(0, 0, -1))),
        width=mm(40), depth=mm(30), dovetail_angle=degrees(15),
        forward_length=mm(50), backward_length=mm(50), taper_angle=taper_angle,
    )
    return cut_basic_free_dovetail_joint(post, beam, dovetail)


@pattern("basic_joints/free_dovetail")
def free_dovetail() -> Joint:
    return _post_on_beam_with_dovetail(None, scalar(0))


@pattern("basic_joints/sliding_dovetail/side_to_face")
def sliding_dovetail() -> Joint:
    from kumiki.example_shavings import create_canonical_example_board_butt_joint_boards_side_to_face
    return cut_basic_practice_sliding_dovetail_joint_on_orthogonal_boards(
        create_canonical_example_board_butt_joint_boards_side_to_face(),
        inches(1, 4), inches(1, 2), degrees(80))


@pattern("basic_joints/board_in_grooved_frame")
def board_in_grooved_frame() -> Joint:
    board = Board(length=inches(20), size=create_v2(inches(10), inches(3, 4)),
                  transform=Transform.identity(), ticket=BoardTicket(path="panel"))
    rail_size = create_v2(inches(2), inches(2))
    left = create_timber(length=inches(24), size=rail_size,
        bottom_position=create_v3(inches(-5), 0, inches(-2)),
        length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="left")
    right = create_timber(length=inches(24), size=rail_size,
        bottom_position=create_v3(inches(5), 0, inches(-2)),
        length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="right")
    bottom = create_timber(length=inches(12), size=rail_size,
        bottom_position=create_v3(inches(-6), 0, 0),
        length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 0, 1), ticket="bottom")
    top = create_timber(length=inches(12), size=rail_size,
        bottom_position=create_v3(inches(-6), 0, inches(20)),
        length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 0, 1), ticket="top")
    return cut_basic_practice_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
        PanelBoardArrangement(boards=[board]),
        ExtendedTimberArrangement(timbers=[left, right, bottom, top]))
