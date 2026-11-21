from dataclasses import replace
from math import atan

import pytest

from kumiki import (CornerJointTimberArrangement, Frame, Joint, KumikiArrangementError, Orientation, TimberEnd, TimberLongFace,
                    Transform, create_v2, create_v3, cut_box_corner_joint, cut_uniform_finger_corner_joint,
                    cut_uniform_finger_splice_joint, degrees, mm)
from kumiki.example_shavings import (create_canonical_example_right_angle_corner_joint_timbers,
                                    create_canonical_example_splice_joint_timbers)


def _ownership(joint: Joint):
    cuts = Frame.from_joints([joint]).cut_timbers
    assert len(cuts) == 2 and not joint.jointAccessories
    solids = [(cut.timber.transform, cut.render_timber_with_cuts_csg_local()) for cut in cuts]

    def at(point_global):
        return tuple(solid.contains_point(transform.global_to_local(point_global)) for transform, solid in solids)
    return at


def _reverse_stock(timber):
    top = timber.transform.local_to_global(create_v3(0, 0, timber.length))
    axes = Orientation.from_z_and_y(-timber.get_length_direction_global(), timber.get_height_direction_global())
    return replace(timber, transform=Transform(top, axes))


@pytest.mark.parametrize("count,reverse", [(2, False), (5, False), (6, True)])
def test_box_corner_fills_alternate_bands_and_trims_each_end_to_the_other_stock(count, reverse):
    corner_global = create_v3(mm(44), mm(-60), mm(190))
    a = create_canonical_example_right_angle_corner_joint_timbers(corner_global,
                                                                 timber_size=create_v2(mm(60), mm(18)))
    # The row spans the same 60 mm on both pieces, with different material thicknesses.
    a = replace(a, timber2=replace(a.timber2, size=create_v2(mm(60), mm(30))))
    if reverse:
        a = replace(a, timber1=_reverse_stock(a.timber1), timber1_end=TimberEnd.TOP,
                    front_face_on_timber1=TimberLongFace.LEFT)
    assert cut_box_corner_joint is cut_uniform_finger_corner_joint
    joint = cut_box_corner_joint(a, count)
    at = _ownership(joint)
    for i in range(count):
        z = mm(30 - (i + .5) * 60 / count)
        for x in (-8, 8):
            for y in (-14, 14):
                assert at(corner_global + create_v3(mm(x), mm(y), z)) == (i % 2 == 0, i % 2 == 1)
        assert at(corner_global + create_v3(0, mm(16), z)) == (True, False)
        assert at(corner_global + create_v3(mm(10), 0, z)) == (False, True)
        assert at(corner_global + create_v3(mm(-10), mm(-16), z)) == (False, False)
    assert joint.cuttings["timber2"].maybe_bottom_end_cut_distance_from_bottom == pytest.approx(mm(-9))
    first = joint.cuttings["timber1"]
    if reverse:
        assert first.maybe_top_end_cut_distance_from_bottom == pytest.approx(first.timber.length + mm(15))
        assert first.maybe_bottom_end_cut_distance_from_bottom is None
    else:
        assert first.maybe_bottom_end_cut_distance_from_bottom == pytest.approx(mm(-15))
        assert first.maybe_top_end_cut_distance_from_bottom is None


@pytest.mark.parametrize("slope,reverse", [(0, False), (.125, False), (.2, True)])
def test_splice_owns_both_sides_of_each_flank_from_root_to_tip(slope, reverse):
    a = create_canonical_example_splice_joint_timbers(timber_size=create_v2(mm(50), mm(20)), timber_length=mm(100))
    if reverse:
        a = replace(a, timber2=_reverse_stock(a.timber2), timber2_end=TimberEnd.TOP)
    # An off-axis marking point projects to x = 7 mm.
    joint = cut_uniform_finger_splice_joint(a, mm(20), 5, taper_angle=atan(slope), splice_point=create_v3(mm(7), mm(91), 0))
    at = _ownership(joint)
    for x in (-2, 7, 16):
        for boundary in range(1, 5):
            sign = 1 if boundary % 2 else -1
            z = 25 - boundary * 10 + sign * (x - 7) * slope
            for y in (-9, 9):
                assert at(create_v3(mm(x), mm(y), mm(z + .1))) == (sign == 1, sign == -1)
                assert at(create_v3(mm(x), mm(y), mm(z - .1))) == (sign == -1, sign == 1)
    for z in (-24, 24, 0):
        assert at(create_v3(mm(-4), 0, mm(z))) == (True, False)
        assert at(create_v3(mm(18), 0, mm(z))) == (False, True)
    assert joint.cuttings["timber1"].maybe_top_end_cut_distance_from_bottom == pytest.approx(mm(117))
    freedom = joint.cuttings["timber1"].assembly_freedom
    assert freedom is not None and freedom.translations[0].freed_after == pytest.approx(mm(20))


def test_default_splice_centers_the_overlap_between_the_selected_ends():
    a = create_canonical_example_splice_joint_timbers(timber_size=create_v2(mm(50), mm(20)), timber_length=mm(100))
    a = replace(a, timber2=replace(a.timber2, transform=replace(a.timber2.transform, position=create_v3(mm(10), 0, 0))),
                front_face_on_timber1=None)
    joint = cut_uniform_finger_splice_joint(a, mm(20))
    assert joint.cuttings["timber1"].maybe_top_end_cut_distance_from_bottom == pytest.approx(mm(115))
    assert joint.cuttings["timber2"].maybe_bottom_end_cut_distance_from_bottom == pytest.approx(mm(-15))


def test_unsupported_layouts_are_rejected():
    a = create_canonical_example_splice_joint_timbers(timber_size=create_v2(mm(50), mm(20)), timber_length=mm(100))
    with pytest.raises(KumikiArrangementError, match="opposite"):
        cut_uniform_finger_splice_joint(replace(a, timber2_end=TimberEnd.TOP), mm(20))
    with pytest.raises(KumikiArrangementError, match="flush"):
        cut_uniform_finger_splice_joint(replace(a, timber2=replace(a.timber2, size=create_v2(mm(50), mm(24)))), mm(20))
    with pytest.raises(ValueError, match="no finger tip"):
        cut_uniform_finger_splice_joint(a, mm(20), taper_angle=degrees(45))
    with pytest.raises(ValueError, match="positive"):
        cut_uniform_finger_splice_joint(a, 0)
    with pytest.raises(ValueError, match="opposite end"):
        cut_uniform_finger_splice_joint(a, mm(20), splice_point=create_v3(mm(180), 0, 0))
    corner = create_canonical_example_right_angle_corner_joint_timbers()
    with pytest.raises(ValueError, match="at least 2"):
        cut_uniform_finger_corner_joint(corner, 1)


@pytest.mark.parametrize("corner", [True, False], ids=["box", "splice"])
def test_rotated_joint_meshes_have_the_expected_combined_volume(corner):
    from kumiki.csg.triangles import triangulate_cutcsg

    make = create_canonical_example_right_angle_corner_joint_timbers if corner else create_canonical_example_splice_joint_timbers
    a = make(timber_size=create_v2(mm(60), mm(18)), timber_length=mm(100))
    pose = Transform(create_v3(.3, -.15, .44), Orientation.from_angle_axis(degrees(33), create_v3(1, 2, -3)))
    a = replace(a, timber1=replace(a.timber1, transform=pose * a.timber1.transform),
                timber2=replace(a.timber2, transform=pose * a.timber2.transform), front_face_on_timber1=None)
    joint = cut_uniform_finger_corner_joint(a) if isinstance(a, CornerJointTimberArrangement) else cut_uniform_finger_splice_joint(a, mm(20))
    total_volume = 0.0
    for cut in Frame.from_joints([joint]).cut_timbers:
        mesh = triangulate_cutcsg(cut.render_timber_with_cuts_csg_local()).mesh
        assert mesh.is_watertight and mesh.body_count == 1
        total_volume += mesh.volume
    # The canonical arms meet at their end centers; the strips divide their shared overlap.
    assert total_volume == pytest.approx(2 * mm(100) * mm(60) * mm(18))


@pytest.fixture(params=["corner", "splice"])
def cut_row(request):
    def cut(width_mm, face=TimberLongFace.RIGHT, **layout):
        stock = create_v2(mm(width_mm), mm(20))
        if request.param == "corner":
            a = create_canonical_example_right_angle_corner_joint_timbers(timber_size=stock)
            return cut_uniform_finger_corner_joint(replace(a, front_face_on_timber1=face), **layout)
        a = create_canonical_example_splice_joint_timbers(timber_size=stock)
        return cut_uniform_finger_splice_joint(replace(a, front_face_on_timber1=face), mm(20), **layout)
    return cut


@pytest.mark.parametrize("face,sign", [(TimberLongFace.RIGHT, 1), (TimberLongFace.LEFT, -1)])
def test_fixed_width_starts_at_the_arrangement_front(cut_row, face, sign):
    at = _ownership(cut_row(50, face, finger_width=mm(12)))
    for i, (left, right) in enumerate([(0, 12), (12, 24), (24, 36), (36, 48), (48, 50)]):
        for distance in (left + .1, right - .1):
            assert at(create_v3(0, 0, sign * mm(25 - distance))) == (i % 2 == 0, i % 2 == 1)


def test_exact_width_multiple_and_default_count(cut_row):
    # 33 mm / 11 mm rounds just above three in floating point.
    fixed = _ownership(cut_row(33, finger_width=mm(11)))
    default = _ownership(cut_row(33))
    for i, distance in enumerate((5, 15, 28)):
        assert fixed(create_v3(0, 0, mm(16.5 - distance))) == (i % 2 == 0, i % 2 == 1)
    for i in range(5):
        assert default(create_v3(0, 0, mm(16.5 - (i + .5) * 6.6))) == (i % 2 == 0, i % 2 == 1)


def test_reject_invalid_finger_width_or_both_layout_modes(cut_row):
    with pytest.raises(ValueError, match="mutually exclusive"):
        cut_row(50, finger_count=5, finger_width=mm(10))
    for width in (0, mm(-1), mm(50), mm(51), float("inf"), float("nan"), True):
        with pytest.raises(ValueError, match="finger_width"):
            cut_row(50, finger_width=width)


def test_taper_must_leave_a_tip_on_the_partial_last_finger():
    a = create_canonical_example_splice_joint_timbers(timber_size=create_v2(mm(49), mm(20)))
    with pytest.raises(ValueError, match="no finger tip"):
        cut_uniform_finger_splice_joint(a, mm(20), finger_width=mm(12))
