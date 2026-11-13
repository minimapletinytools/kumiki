"""Check automatically sized joint geometry and compatibility entry points."""

from dataclasses import replace

import pytest

from kumiki import *
from kumiki.example_shavings import (
    create_canonical_example_cross_joint_timbers,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_board_butt_joint_boards_side_to_face,
    create_canonical_example_board_butt_joint_boards_end_to_face,
)


def _butt(direction=create_v3(1, 0, 0), width=mm(120), offset=scalar(0)):
    receiving = create_timber(length=m(1), size=create_v2(mm(200), mm(100)),
        bottom_position=create_v3(0, 0, -m(1, 2)), length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0), ticket="receiver")
    direction = safe_normalize_vector(direction)
    butt = create_timber(length=m(1, 2), size=create_v2(width, mm(160)),
        bottom_position=create_v3(0, offset, 0) - direction * m(1, 2),
        length_direction=direction, width_direction=create_v3(0, 1, 0), ticket="butt")
    return ButtJointTimberArrangement(butt, receiving, TimberEnd.TOP)


def _removed(joint, timber, point):
    cut = joint.cuttings[timber.ticket.path]
    assert cut.negative_csg is not None
    return cut.negative_csg.contains_point(timber.transform.global_to_local(point))


@pytest.mark.parametrize("builder", [cut_basic_mortise_and_tenon_joint, cut_basic_round_mortise_and_tenon_joint])
def test_basic_tenon_stops_three_quarters_through_receiver(builder):
    arrangement = _butt()
    joint = builder(arrangement)
    assert _removed(joint, arrangement.receiving_timber, create_v3(mm(40), 0, 0))
    assert not _removed(joint, arrangement.receiving_timber, create_v3(mm(80), 0, 0))
    assert not _removed(joint, arrangement.butt_timber, create_v3(mm(40), 0, 0))
    assert _removed(joint, arrangement.butt_timber, create_v3(mm(80), 0, 0))


@pytest.mark.parametrize("direction", [create_v3(1, 0, 1), create_v3(1, scalar(1, 3), scalar(1, 2)), create_v3(-1, 0, 1)])
@pytest.mark.parametrize("width,offset", [(mm(120), scalar(0)), (mm(300), mm(30))])
@pytest.mark.parametrize("builder", [cut_basic_mortise_and_tenon_joint, cut_basic_round_mortise_and_tenon_joint])
def test_angled_tenons_leave_receiving_walls_intact(direction, width, offset, builder):
    arrangement = _butt(direction, width, offset)
    joint = builder(arrangement)
    receiving = arrangement.receiving_timber
    # Probe the receiver's opposite long faces and declared ends.
    inward = 1 if float(direction[0]) > 0 else -1
    for y in (-mm(49), scalar(0), mm(49)):
        for z in (-mm(490), -mm(200), scalar(0), mm(200), mm(490)):
            assert not _removed(joint, receiving, create_v3(inward * mm(99), y, z))
    assert Frame.from_joints([joint]).cut_timbers


def test_basic_tenon_peg_is_optional_and_scales_with_small_stock():
    arrangement = _butt(width=mm(18))
    plain = cut_basic_mortise_and_tenon_joint(arrangement)
    pegged = cut_basic_mortise_and_tenon_joint(arrangement, use_peg=True)
    assert not plain.jointAccessories
    assert pegged.jointAccessories


@pytest.mark.parametrize("half_blind", [False, True])
@pytest.mark.parametrize("span", [mm(40), mm(200), mm(500)])
def test_dovetail_tail_count_scales_and_tails_fit(span, half_blind):
    from unittest.mock import patch
    from kumiki.joints.workshop.corner.dovetail_corner_joint import cut_dovetail_corner_joint
    arrangement = create_canonical_example_right_angle_corner_joint_timbers()
    face = arrangement.front_face_on_timber1
    assert face is not None
    timbers = []
    for timber in (arrangement.timber1, arrangement.timber2):
        own_face = timber.get_closest_oriented_long_face_from_global_direction(arrangement.timber1.get_face_direction_global(face))
        own_index = timber.get_size_index_in_long_face_normal_axis(own_face)
        sizes = [timber.size[0], timber.size[1]]
        sizes[own_index] = span
        timbers.append(replace(timber, size=create_v2(*sizes)))
    arrangement = replace(arrangement, timber1=timbers[0], timber2=timbers[1])
    with patch('kumiki.joints.workshop.corner.dovetail_corner_joint.cut_dovetail_corner_joint', wraps=cut_dovetail_corner_joint) as cutter:
        joint = cut_basic_dovetail_corner_joint(arrangement, half_blind=half_blind)
    tails = cutter.call_args.kwargs['dovetails']
    assert (len(tails) > 1) == (span == mm(500))
    assert all((tail.depth is not None) == half_blind for tail in tails)
    assert len(joint.cuttings) == 2


def test_tongue_fits_offset_boards_with_small_overlap():
    tongue = Board(length=m(1), size=create_v2(mm(100), mm(24)), transform=Transform.identity(), ticket=BoardTicket(path="tongue"))
    groove = Board(length=m(1), size=create_v2(mm(100), mm(12)),
        transform=Transform(create_v3(mm(98), mm(6), 0), Orientation.identity()), ticket=BoardTicket(path="groove"))
    joint = cut_basic_tongue_and_groove_joint(tongue, groove)
    assert _removed(joint, groove, create_v3(mm(49), mm(6), m(1, 2)))
    assert not _removed(joint, groove, create_v3(mm(49), mm(11), m(1, 2)))


@pytest.mark.parametrize("build", [create_canonical_example_board_butt_joint_boards_side_to_face,
                                   create_canonical_example_board_butt_joint_boards_end_to_face])
def test_sliding_dovetail_defaults_fit_both_board_arrangements(build):
    joint = cut_basic_practice_sliding_dovetail_joint_on_orthogonal_boards(build())
    assert len(joint.cuttings) == 2
    assert all(cut.assembly_freedom is not None for cut in joint.cuttings.values())


@pytest.mark.parametrize("old,new", [
    ("cut_basic_plain_cross_lap_joint_on_face_aligned_timbers", cut_basic_plain_cross_lap_joint),
    ("cut_basic_plain_house_joint_on_face_aligned_timbers", cut_basic_plain_cross_lap_house_joint),
])
def test_deprecated_cross_basics_forward_without_geometry_changes(old, new):
    arrangement = create_canonical_example_cross_joint_timbers()
    from kumiki.joints.workshop import basic_joints
    with pytest.warns(DeprecationWarning):
        legacy = getattr(basic_joints, old)(arrangement)
    current = new(arrangement)
    for name in legacy.cuttings:
        assert repr(legacy.cuttings[name].negative_csg) == repr(current.cuttings[name].negative_csg)


@pytest.mark.parametrize("angle", [60, 90, 120])
@pytest.mark.parametrize("use_peg", [False, True])
def test_corner_tenon_accepts_angled_members_and_optional_pegs(angle, use_peg):
    joint = cut_basic_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(
        create_canonical_example_corner_joint_timbers(corner_angle=degrees(angle)), use_peg=use_peg)
    assert len(joint.cuttings) == 2
    assert bool(joint.jointAccessories) == use_peg


def test_existing_face_aligned_tenon_uses_the_same_stopped_recipe():
    arrangement = _butt()
    legacy = cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement.butt_timber, arrangement.receiving_timber, arrangement.butt_timber_end)
    current = cut_basic_mortise_and_tenon_joint(arrangement)
    for name in legacy.cuttings:
        assert repr(legacy.cuttings[name].negative_csg) == repr(current.cuttings[name].negative_csg)
