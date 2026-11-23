from dataclasses import replace
from math import radians

import pytest

from kumiki import Measure, TimberLongFace, create_v2, mm
from kumiki.example_shavings import (
    create_canonical_example_butt_joint_timbers, create_canonical_example_right_angle_corner_joint_timbers,
    create_canonical_example_splice_joint_timbers,
)
from kumiki.joints.workshop.butt import cut_dropin_dovetail_butt_joint_on_face_aligned_timbers
from kumiki.joints.workshop.splice import (
    cut_lapped_gooseneck_joint_on_aligned_timbers, cut_rebated_oblique_and_dadoed_scarf_joint_on_aligned_timbers,
)
from kumiki.joints.workshop.corner import cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers
from kumiki.joints.workshop.mixed import cut_mortise_and_tenon_joint
from patterns.basic_joints_patterns import example_basic_mortise_and_tenon_joint, example_basic_tongue_and_fork_joint
from tools.render_joint_docs import dovetail, gooseneck, mortise_and_tenon, scarf, tongue_and_fork


@pytest.fixture
def values(monkeypatch):
    values = {}
    format_label = Measure.format_label

    def capture(measure, value):
        values[measure.label] = value
        return format_label(measure, value)

    monkeypatch.setattr(Measure, 'format_label', capture)
    return values


def test_tenon_dimensions_measure_their_own_arguments(values):
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
    )
    tenon, mortise, end, plan = mortise_and_tenon(joint).findall('svg')
    assert values == {'tenon_size[0]': '24mm', 'tenon_size[1]': '73mm',
                      'tenon_length': '49mm', 'mortise_depth': '61mm', 'mortise_depth − tenon_length': '12mm',
                      'tenon_position[0]': '17mm', 'tenon_position[1]': '11mm',
                      'mortise_shoulder_distance_from_centerline_or_centerplane': '63.5mm'}
    assert {node.text for view in (tenon, mortise, end, plan)
            for node in view.findall('g/text')} == set(values)
    assert end.find(".//g[@class='xray-edges']") is None
    assert plan.find(".//g[@class='xray-edges']") is not None
    assert tenon.find(".//g[@class='xray-edges']") is None
    assert mortise.find(".//g[@class='xray-edges']/path[@data-feature='mortise_front']") is not None


def test_centered_basic_pattern_omits_zero_offsets_clearance_and_absent_peg():
    root = mortise_and_tenon(example_basic_mortise_and_tenon_joint())
    assert {node.text for view in root.findall('svg') for node in view.findall('g/text')} == {
        'tenon_size[0]', 'tenon_size[1]', 'tenon_length', 'mortise_depth', 'mortise_shoulder_distance_from_centerline_or_centerplane',
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


def test_dovetail_dimensions_measure_the_flare_and_the_housed_shoulder(values):
    joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
        create_canonical_example_butt_joint_timbers(), dovetail_length=mm(49), dovetail_small_width=mm(59),
        dovetail_angle=radians(12), dovetail_depth=mm(33), receiving_timber_shoulder_inset=mm(15),
    )
    root = dovetail(joint)
    assert values == {'dovetail_length': '49mm', 'dovetail_small_width': '59mm', 'dovetail_angle': '12deg',
                      'dovetail_depth': '33mm', 'receiving_timber_shoulder_inset': '15mm'}
    assert {t.text for view in root.findall('svg') for t in view.findall("g[@class='dimension']/text")} == set(values)
    assert root.find(".//g[@class='xray-edges']") is None


def test_gooseneck_dimensions_distinguish_neck_head_and_socket(values):
    arr = create_canonical_example_splice_joint_timbers()
    joint = cut_lapped_gooseneck_joint_on_aligned_timbers(
        replace(arr, timber1=arr.timber2, timber2=arr.timber1, timber1_end=arr.timber2_end, timber2_end=arr.timber1_end),
        gooseneck_length=mm(211), gooseneck_small_width=mm(27), gooseneck_large_width=mm(62),
        gooseneck_head_length=mm(54), gooseneck_depth=mm(41),
    )
    gooseneck(joint)
    assert values == {'gooseneck_length': '211mm', 'gooseneck_small_width': '27mm', 'gooseneck_large_width': '62mm',
                      'gooseneck_head_length': '54mm', 'gooseneck_depth': '41mm'}


def test_scarf_dimensions_distinguish_the_rebate_dado_and_stub(values):
    arr = create_canonical_example_splice_joint_timbers()
    joint = cut_rebated_oblique_and_dadoed_scarf_joint_on_aligned_timbers(
        replace(arr, front_face_on_timber1=TimberLongFace.FRONT), scarf_length=mm(330), rebated_shoulder_depth=mm(14),
        dado_depth=mm(22), dado_height=mm(27), stub_tenon_width=mm(35),
    )
    scarf(joint)
    assert values == {'scarf_length': '330mm', 'rebated_shoulder_depth': '14mm',
                      'dado_depth': '22mm', 'dado_height': '27mm', 'stub_tenon_width': '35mm'}


def test_published_drawings_cover_every_basic_pattern():
    import ast
    from pathlib import Path
    from xml.etree import ElementTree
    from patterns import basic_joints_patterns
    from tools.joint_doc_patterns import CATALOG
    from tools.render_joint_docs import OUT

    pilots = {
        'example_basic_mortise_and_tenon_joint': 'mortise-and-tenon',
        'example_basic_tongue_and_fork_joint': 'tongue-and-fork',
        'example_basic_lapped_gooseneck_joint': 'lapped-gooseneck',
        'example_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint': 'kanawa-tsugi',
        'example_basic_dropin_dovetail_butt_joint': 'drop-in-dovetail',
    }
    definitions = ast.parse(Path(basic_joints_patterns.__file__).read_text())
    basic = {fn.name for fn in definitions.body if isinstance(fn, ast.FunctionDef)
             and any(isinstance(d, ast.Call) and ast.unparse(d.func) == 'pattern' for d in fn.decorator_list)}
    assert basic == set(pilots) | {fn.__name__ for fn, *_ in CATALOG if fn.__module__ == basic_joints_patterns.__name__}
    assets = {file.stem for file in OUT.glob('*.svg')}
    assert assets == set(pilots.values()) | {slug for _, slug, *_ in CATALOG}
    ns = {'s': 'http://www.w3.org/2000/svg'}
    for _, slug, _, _, rows in CATALOG:
        root = ElementTree.parse(OUT / f'{slug}.svg')
        assert len(root.findall('s:svg', ns)) == 2 * rows, slug
        assert root.findall(".//s:g[@class='dimension']/s:text", ns), slug
    assert 'peg' not in (OUT / 'mortise-and-tenon.svg').read_text().lower()


@pytest.fixture
def measured_spans(monkeypatch):
    import numpy as np
    from tools import joint_doc_patterns

    lengths = {}
    def record(view, label, ends, *args):
        lengths[label] = np.linalg.norm(ends[1] - ends[0]) * 1000
    monkeypatch.setattr(joint_doc_patterns, 'annotate', record)
    return lengths


def test_housing_dimensions_follow_independent_arguments(measured_spans):
    from kumiki.joints.workshop.butt import cut_dropin_housed_butt_joint_on_face_aligned_timbers
    from tools.joint_doc_patterns import Plate, housed

    joint = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
        create_canonical_example_butt_joint_timbers(), receiving_timber_shoulder_inset=mm(18),
        housing_length=mm(54), housing_width=mm(62), housing_depth=mm(32), housing_lateral_offset=mm(7))
    housed(Plate(joint, 'Housing', 1))
    assert measured_spans == pytest.approx(dict(receiving_timber_shoulder_inset=18, housing_length=54,
                                               housing_width=62, housing_depth=32))


def test_tusk_dimensions_follow_the_exit_face(measured_spans):
    from kumiki.joints.workshop.mixed.mortise_and_tenon_joints import (
        TuskParameters, cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers,
    )
    from tools.joint_doc_patterns import Plate, tusked

    joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        create_canonical_example_butt_joint_timbers(), tenon_length_past_opposite_shoulder=mm(91),
        tenon_width_relative_to_joint=mm(65), tenon_height_relative_to_joint=mm(37),
        tusk_parameters=TuskParameters(tusk_thickness=mm(23), tusk_small_width=mm(29),
                                      tusk_back_stickout=mm(12), tusk_tip_stickout=mm(19)))
    tusked(Plate(joint, 'Tusk', 2))
    assert measured_spans == pytest.approx(dict(tenon_length_past_opposite_shoulder=91,
        tenon_width_relative_to_joint=65, tenon_height_relative_to_joint=37,
        tusk_thickness=23, tusk_small_width=29, tusk_tip_stickout=19))


def test_splice_lap_dimensions_follow_the_removed_depth(measured_spans):
    from kumiki.joints.workshop.splice import cut_plain_splice_lap_joint_on_aligned_timbers
    from tools.joint_doc_patterns import Plate, splice_lap

    joint = cut_plain_splice_lap_joint_on_aligned_timbers(create_canonical_example_splice_joint_timbers(),
        lap_length=mm(145), lap_depth=mm(31), top_lap_shoulder_position_from_top_lap_shoulder_timber_end=mm(72))
    splice_lap(Plate(joint, 'Splice', 1))
    assert measured_spans == pytest.approx(dict(lap_length=145, lap_depth=31))


def test_cross_lap_ratio_measures_the_removed_side_of_each_member(measured_spans):
    from kumiki.example_shavings import create_canonical_example_cross_joint_timbers
    from kumiki.joints.workshop.cross import cut_plain_cross_lap_joint
    from tools.joint_doc_patterns import Plate, cross_lap

    joint = cut_plain_cross_lap_joint(create_canonical_example_cross_joint_timbers(), cut_ratio=0.25)
    cross_lap(Plate(joint, 'Cross lap', 1))
    assert measured_spans['overlap × cut_ratio'] == pytest.approx(25.4)
    assert measured_spans['overlap × (1 − cut_ratio)'] == pytest.approx(76.2)
