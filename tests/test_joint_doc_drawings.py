import pytest

from kumiki import TimberLongFace, create_v2, mm
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers, create_canonical_example_right_angle_corner_joint_timbers
from kumiki.joints.workshop.corner import cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers
from kumiki.joints.workshop.mixed import cut_mortise_and_tenon_joint
from tools.render_joint_docs import mortise_and_tenon, tongue_and_fork


def test_tenon_dimensions_measure_their_own_argument_even_when_all_four_differ():
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
    drawing = mortise_and_tenon(joint)
    captions = {node.text for node in drawing.iter('text')}
    assert {'tenon_size[0] = 24mm', 'tenon_size[1] = 73mm',
            'tenon_length = 49mm', 'mortise_depth = 61mm'} <= captions


def test_fork_formula_rejects_an_offset_tongue():
    joint = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
        create_canonical_example_right_angle_corner_joint_timbers(),
        tongue_thickness=mm(22), tongue_position=mm(8),
    )
    with pytest.raises(ValueError, match="centered fork slot"):
        tongue_and_fork(joint)
