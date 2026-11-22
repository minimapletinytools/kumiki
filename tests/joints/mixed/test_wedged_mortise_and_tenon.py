from dataclasses import replace
from math import cos, sin, tan

import pytest

from kumiki import (CSGAccessory, CutTimber, Orientation, PegShape, SimplePegParameters, TimberEnd, TimberLongFace, Transform,
                    Wedge, WedgeOrientation, WedgeParameters, create_v2, create_v3,
                    cut_mortise_and_tenon_joint, cut_mortise_and_tenon_joint_on_face_aligned_timbers, degrees, mm)
from kumiki.csg.triangles import triangulate_cutcsg
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers


@pytest.fixture
def arrangement():
    return create_canonical_example_butt_joint_timbers(timber_size=create_v2(mm(60), mm(80)), timber_length=mm(200))


def _cut(arrangement, params, depth=mm(50), **options):
    return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement, tenon_length=mm(40), mortise_depth=depth, tenon_height_relative_to_joint=mm(24),
        tenon_width_relative_to_joint=mm(36), wedge_parameters=params, **options)


def _finished(joint, timber):
    return CutTimber(timber, [joint.cuttings[timber.ticket.path]]).render_timber_with_cuts_csg_local()


@pytest.mark.parametrize("length,depth,head", [(None, 40, 40), (24, 24, 40), (46, 40, 46)])
@pytest.mark.parametrize("orientation", list(WedgeOrientation))
def test_wedge_placement_and_kerf_on_an_offset_tenon(arrangement, length, depth, head, orientation):
    params = WedgeParameters(orientation, mm(4), None if length is None else mm(length), tenon_kerf_size=mm(2))
    joint = _cut(arrangement, params, tenon_position=create_v2(mm(2), mm(3)))
    tenon = arrangement.butt_timber
    # The canonical right face points up and the front face points along global X.
    center = create_v3(mm(3), mm(-40), mm(2))
    spread = tenon.get_width_direction_global() if orientation is WedgeOrientation.SPREAD_X else tenon.get_height_direction_global()
    along = tenon.get_length_direction_global()
    slot_origin = center + mm(4) * spread
    solid = _finished(joint, tenon)

    def has_stock(offset, station):
        return solid.contains_point(tenon.transform.global_to_local(slot_origin + spread * mm(offset) + along * mm(station)))

    for station in (40 - depth + .1, 39.9):
        assert not has_stock(.9, station)
        assert has_stock(1.1, station) and has_stock(-1.1, station)
    assert has_stock(0, 40 - depth - .1)
    wedge = joint.jointAccessories["wedge"]
    assert isinstance(wedge, Wedge)
    assert wedge.length == pytest.approx(mm(length or 40))
    assert wedge.base_width == pytest.approx(2 * wedge.length * tan(degrees(2.5)))
    assert (wedge.transform.position - (slot_origin + along * mm(head))).norm() == pytest.approx(0)
    tip = wedge.transform.local_to_global(create_v3(0, 0, wedge.length))
    assert (tip - (slot_origin + along * mm(40 - depth))).norm() == pytest.approx(0)
    wedge_mesh = triangulate_cutcsg(wedge.get_csg_local()).mesh
    assert wedge_mesh.is_watertight
    assert wedge_mesh.volume == pytest.approx(wedge.base_width * wedge.length * wedge.height / 2, rel=1e-5)


@pytest.mark.parametrize("depth", [mm(50), None])
@pytest.mark.parametrize("orientation", list(WedgeOrientation))
def test_flare_from_shoulder_to_blind_bottom_or_through_exit(arrangement, depth, orientation):
    angle = degrees(5)
    joint = _cut(arrangement, WedgeParameters(orientation, wedge_length=mm(24), mortise_side_angle=angle), depth)
    receiver = arrangement.receiving_timber
    solid = _finished(joint, receiver)
    spread_x = orientation is WedgeOrientation.SPREAD_X
    half_width, half_cross = (12, 18) if spread_x else (18, 12)

    def has_stock(spread, cross, station):
        x, z = (cross, spread) if spread_x else (spread, cross)
        return solid.contains_point(receiver.transform.global_to_local(create_v3(mm(x), mm(station - 40), mm(z))))

    for station in (1, 20, 39.9, 49.9 if depth else 79.9):
        boundary = half_width + station * tan(angle)
        for sign in (-1, 1):
            assert not has_stock(sign * (boundary - .03), 0, station)
            assert has_stock(sign * (boundary + .03), 0, station)
        assert has_stock(0, half_cross + .05, station)
    if depth:
        assert has_stock(0, 0, 50.1)


def test_zero_kerf_keeps_solid_wood_and_locatable_marks_on_bottom_end(arrangement):
    timber = arrangement.butt_timber
    reverse_pose = Transform(timber.transform.local_to_global(create_v3(0, 0, timber.length)),
                             Orientation.from_z_and_x(-timber.get_length_direction_global(), timber.get_width_direction_global()))
    timber = replace(timber, transform=reverse_pose)
    arrangement = replace(arrangement, butt_timber=timber, butt_timber_end=TimberEnd.BOTTOM)
    joint = _cut(arrangement, WedgeParameters(WedgeOrientation.SPREAD_Y, mm(3), mm(20)))
    solid = _finished(joint, timber)
    # Reversing the timber flips its positive Y while leaving the approaching end in place.
    point = timber.transform.global_to_local(create_v3(mm(-3), mm(-20), 0))
    assert solid.contains_point(point)
    assert {"kerf_center", "kerf_root"} <= {hit.feature.name for hit in solid.find_all_features(point)}
    receiver = arrangement.receiving_timber
    mortise = _finished(joint, receiver)
    assert mortise.contains_point(receiver.transform.global_to_local(create_v3(mm(18.1), 0, 0)))


def test_wedge_and_peg_survive_the_same_joint(arrangement):
    joint = _cut(arrangement, WedgeParameters(wedge_length=mm(10), tenon_kerf_size=mm(2)),
                 peg_parameters=SimplePegParameters(shape=PegShape.ROUND, size=mm(4), peg_positions=[(mm(8), 0)]))
    assert set(joint.jointAccessories) == {"wedge", "peg_0"}
    assert not _finished(joint, arrangement.butt_timber).contains_point(
        arrangement.butt_timber.transform.global_to_local(create_v3(0, mm(-1), 0)))


@pytest.mark.parametrize("options", [
    {"wedge_position": mm(12)}, {"wedge_length": mm(52)}, {"wedge_length": 0},
    {"tenon_kerf_size": mm(-1)}, {"wedge_angle": 0}, {"mortise_side_angle": degrees(90)},
])
def test_invalid_wedge_dimensions(arrangement, options):
    with pytest.raises(ValueError):
        _cut(arrangement, WedgeParameters(**options))


def test_round_tenons_reject_a_wedge(arrangement):
    with pytest.raises(ValueError, match="rectangular tenon"):
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement, tenon_length=mm(40), tenon_width_relative_to_joint=mm(24),
            tenon_height_relative_to_joint=mm(24), wedge_parameters=WedgeParameters(), use_round_tenon=True)


def test_oblique_mortise_walls_pivot_on_the_shoulder(arrangement):
    # Turn the receiver about its center. The tenon still enters along +Y.
    pose = Transform(create_v3(0, 0, 0), Orientation.from_angle_axis(degrees(30), create_v3(0, 0, 1)))
    receiver = replace(arrangement.receiving_timber, transform=pose * arrangement.receiving_timber.transform)
    arrangement = replace(arrangement, receiving_timber=receiver)

    joint = cut_mortise_and_tenon_joint(
        arrangement, tenon_size=create_v2(mm(24), mm(36)), tenon_length=mm(40), mortise_depth=mm(50),
        set_mortise_shoulder_parallel_to_face=TimberLongFace.FRONT,
        mortise_shoulder_distance_from_centerline_or_centerplane=mm(40),
        wedge_parameters=WedgeParameters(WedgeOrientation.SPREAD_Y, mortise_side_angle=degrees(5)),
    )
    solid = _finished(joint, receiver)
    # For each cheek, find its own intersection with the receiver's entrance plane.
    for sign in (-1, 1):
        x = sign * mm(18)
        normal = receiver.get_height_direction_global()
        entry_y = (mm(40) - normal[0] * x) / normal[1]
        for delta in (mm(1), mm(20)):
            edge = x + sign * delta * tan(degrees(5))
            for offset, wood in ((-.03, False), (.03, True)):
                p = create_v3(edge + sign * mm(offset), entry_y + delta, 0)
                assert solid.contains_point(receiver.transform.global_to_local(p)) == wood


@pytest.mark.parametrize("angle_deg", [30, -55])
@pytest.mark.parametrize("orientation", list(WedgeOrientation))
@pytest.mark.parametrize("depth_mm,flare_deg", [(20, 0), (20, 5), (58, 5)])
def test_face_bored_wedged_joint(arrangement, angle_deg, orientation, depth_mm, flare_deg):
    angle = degrees(angle_deg)
    pose = Transform(create_v3(0, 0, 0), Orientation.from_angle_axis(angle, create_v3(0, 0, 1)))
    receiver = replace(arrangement.receiving_timber, transform=pose * arrangement.receiving_timber.transform)
    arrangement = replace(arrangement, receiving_timber=receiver)
    joint = cut_mortise_and_tenon_joint(
        arrangement, tenon_size=create_v2(mm(24), mm(36)), tenon_length=mm(70), mortise_depth=mm(depth_mm),
        set_mortise_shoulder_parallel_to_face=TimberLongFace.FRONT,
        mortise_shoulder_distance_from_centerline_or_centerplane=mm(40), bore_mortise_perpendicular_to_face=True,
        wedge_parameters=WedgeParameters(orientation, wedge_position=mm(2), wedge_length=mm(10),
                                         mortise_side_angle=degrees(flare_deg), tenon_kerf_size=mm(1)),
    )
    entry = create_v3(0, -mm(40) / cos(angle), 0)
    inward = -receiver.get_height_direction_global()
    tangent = receiver.get_length_direction_global()
    up = create_v3(0, 0, 1)
    spread_vertical = orientation is WedgeOrientation.SPREAD_X
    stock = _finished(joint, receiver)

    def has_stock(p):
        return stock.contains_point(receiver.transform.global_to_local(p))

    for station in (mm(.1), mm(depth_mm / 2), mm(depth_mm - .1)):
        center = entry + inward * station
        flare = station * tan(degrees(flare_deg))
        for axis, half_width, expands in ((tangent, mm(18) / cos(angle), not spread_vertical),
                                          (up, mm(12), spread_vertical)):
            edge = half_width + (flare if expands else 0)
            for sign in (-1, 1):
                assert not has_stock(center + sign * axis * (edge - mm(.03)))
                assert has_stock(center + sign * axis * (edge + mm(.03)))
    assert has_stock(entry + inward * mm(depth_mm + .1))

    # Intersect the offset wedge axis with the end wall and floor independently.
    offset = (up if spread_vertical else create_v3(1, 0, 0)) * mm(2)
    wall_station = (mm(18) / cos(angle) - (1 if angle > 0 else -1) * tangent.dot(offset)) / abs(sin(angle))
    floor_station = (mm(depth_mm) - inward.dot(offset)) / cos(angle)
    head = entry + offset + create_v3(0, min(wall_station, floor_station, mm(70)), 0)
    wedge = joint.jointAccessories["wedge"]
    assert isinstance(wedge, CSGAccessory)
    assert (wedge.transform.position - head).norm() == pytest.approx(0)
    mesh = triangulate_cutcsg(wedge.get_csg_local()).mesh
    assert mesh.is_watertight and mesh.volume > 0
    for vertex in mesh.vertices:
        point = wedge.transform.local_to_global(create_v3(*vertex))
        depth = (point - entry).dot(inward)
        assert -mm(.001) <= depth <= mm(depth_mm + .001)
        extra = depth * tan(degrees(flare_deg))
        assert abs((point - entry).dot(tangent)) <= mm(18) / cos(angle) + (0 if spread_vertical else extra) + mm(.001)
    timber = arrangement.butt_timber
    tenon = _finished(joint, timber)
    for behind_head, intact in ((9.9, False), (10.1, True)):
        assert tenon.contains_point(timber.transform.global_to_local(head - create_v3(0, mm(behind_head), 0))) == intact
