import pytest

from kumiki import Measure, PegShape, SimplePegParameters, TimberLongFace, create_v2, mm
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers, create_canonical_example_right_angle_corner_joint_timbers
from kumiki.joints.workshop.corner import cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers
from kumiki.joints.workshop.mixed import cut_mortise_and_tenon_joint
from patterns.basic_joints_patterns import example_basic_mortise_and_tenon_joint, example_basic_tongue_and_fork_joint
from tools.render_joint_docs import mortise_and_tenon, tongue_and_fork


def test_tenon_and_peg_dimensions_measure_their_own_arguments(monkeypatch):
    arrangement = create_canonical_example_butt_joint_timbers()
    face = TimberLongFace.FRONT
    joint = cut_mortise_and_tenon_joint(
        arrangement,
        set_mortise_shoulder_parallel_to_face=face,
        mortise_shoulder_distance_from_centerline_or_centerplane=arrangement.receiving_timber.get_size_in_face_normal_axis(face) / 2,
        tenon_size=create_v2(mm(24), mm(73)),
        tenon_length=mm(49),
        mortise_depth=mm(61),
        tenon_position=create_v2(mm(-17), mm(11)),
        peg_parameters=SimplePegParameters(shape=PegShape.ROUND, size=mm(6),
                                           peg_positions=[(mm(25), mm(-8))], tenon_hole_offset=mm(2)),
    )
    values = {}
    format_label = Measure.format_label

    def capture(measure, value):
        values[measure.label] = value
        return format_label(measure, value)

    monkeypatch.setattr(Measure, 'format_label', capture)
    tenon, mortise, end, plan = mortise_and_tenon(joint).findall('svg')
    assert values == {'tenon_size[0]': '24mm', 'tenon_size[1]': '73mm',
                      'tenon_length': '49mm', 'mortise_depth': '61mm', 'mortise_depth − tenon_length': '12mm',
                      'tenon_position[0]': '17mm', 'tenon_position[1]': '11mm',
                      'peg_positions[0][0]': '25mm', 'peg_positions[0][1]': '8mm'}
    assert {node.text for view in (tenon, mortise, end, plan)
            for node in view.findall('g/text')} == set(values)
    assert end.find(".//g[@class='xray-edges']") is None
    assert plan.find(".//g[@class='xray-edges']") is not None
    assert tenon.find(".//g[@class='xray-edges']") is None
    assert mortise.find(".//g[@class='xray-edges']/path[@data-feature='mortise_front']") is not None


def test_centered_basic_pattern_omits_zero_offsets_clearance_and_absent_peg():
    root = mortise_and_tenon(example_basic_mortise_and_tenon_joint())
    assert {node.text for view in root.findall('svg') for node in view.findall('g/text')} == {
        'tenon_size[0]', 'tenon_size[1]', 'tenon_length', 'mortise_depth',
    }


def test_corner_keeps_both_members_opaque_and_labels_only():
    drawing = tongue_and_fork(example_basic_tongue_and_fork_joint())
    assert drawing.find(".//g[@class='xray-edges']") is None
    assert {node.text for view in drawing.findall('svg') for node in view.iter('text')} == {
        'tongue_thickness', '(stock thickness − tongue_thickness) / 2',
    }


def test_fork_formula_rejects_an_offset_tongue():
    joint = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
        create_canonical_example_right_angle_corner_joint_timbers(),
        tongue_thickness=mm(22), tongue_position=mm(8),
    )
    with pytest.raises(ValueError, match="centered fork slot"):
        tongue_and_fork(joint)
