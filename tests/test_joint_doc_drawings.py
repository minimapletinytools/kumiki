import pytest

from kumiki import Measure, TimberLongFace, create_v2, mm
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers, create_canonical_example_right_angle_corner_joint_timbers
from kumiki.joints.workshop.corner import cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers
from kumiki.joints.workshop.mixed import cut_mortise_and_tenon_joint
from patterns.basic_joints_patterns import example_basic_tongue_and_fork_joint
from tools.render_joint_docs import mortise_and_tenon, tongue_and_fork


def test_tenon_dimensions_measure_their_own_argument_even_when_all_four_differ(monkeypatch):
    arrangement = create_canonical_example_butt_joint_timbers()
    face = TimberLongFace.FRONT
    joint = cut_mortise_and_tenon_joint(
        arrangement,
        set_mortise_shoulder_parallel_to_face=face,
        mortise_shoulder_distance_from_centerline_or_centerplane=arrangement.receiving_timber.get_size_in_face_normal_axis(face) / 2,
        tenon_size=create_v2(mm(24), mm(73)),
        tenon_length=mm(49),
        mortise_depth=mm(61),
    )
    values = {}
    format_label = Measure.format_label

    def capture(measure, value):
        values[measure.label] = value
        return format_label(measure, value)

    monkeypatch.setattr(Measure, 'format_label', capture)
    tenon, mortise = mortise_and_tenon(joint).findall('svg')
    assert values == {'tenon_size[0]': '24mm', 'tenon_size[1]': '73mm',
                      'tenon_length': '49mm', 'mortise_depth': '61mm'}
    assert {node.text for view in (tenon, mortise) for node in view.iter('text')} == set(values)
    assert tenon.find(".//g[@class='xray-edges']") is None
    assert mortise.find(".//g[@class='xray-edges']/path[@data-feature='mortise_front']") is not None


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
