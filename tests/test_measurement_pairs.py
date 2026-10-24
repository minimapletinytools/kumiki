"""Joints that declare preferred measurements (FeatureMarkingSpec.mark_relative_to): each names a
feature found in its own joint, and a symmetric pair names each other."""

import pytest

from kumiki import *
from kumiki.csg.cutcsg import Datum, csg_children
from kumiki.drawings.auto_dimensioning import _nearest_named
from tests.testing_shavings import create_centered_horizontal_timber, create_standard_horizontal_timber


def _walk(node):
    yield node
    for child in csg_children(node):
        yield from _walk(child)


def _declared_pairs(joint):
    """(feature name, partner names found) for every feature marked relative to another, on every cut timber."""
    pairs = []
    for cutting in joint.cuttings.values():
        root = CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()
        for node in _walk(root):
            for feature in getattr(node, 'get_declared_features', lambda: [])():
                marking = feature.properties.marking_override
                if marking is None or marking.mark_relative_to is None:
                    continue
                partners = _nearest_named(root, id(node), marking.mark_relative_to)
                assert partners, f"{feature.name} names {marking.mark_relative_to}, which isn't in its joint"
                for partner in partners:
                    back = partner.feature.properties.marking_override
                    one_way = feature.properties.datum is Datum.AVOID
                    assert one_way or (back and back.mark_relative_to == feature.name), \
                        f"{feature.name} -> {partner.feature.name} is not returned"
                pairs.append(feature.name)
    return set(pairs)


def _tongue_and_fork_butt():
    fork = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
    tongue = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, -50, 0))
    return cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(
        ButtJointTimberArrangement(butt_timber=fork, receiving_timber=tongue, butt_timber_end=TimberEnd.TOP))


def _tongue_and_fork_corner():
    tongue = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
    fork = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
    return cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(CornerJointTimberArrangement(
        timber1=tongue, timber2=fork, timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM))


def _cross_lap():
    housing = create_centered_horizontal_timber(direction='x', length=100, size=(10, 10), zoffset=1)
    housed = create_centered_horizontal_timber(direction='y', length=100, size=(10, 10), zoffset=-1)
    return cut_plain_cross_lap_house_joint(CrossJointTimberArrangement(timber1=housing, timber2=housed))


def _scarf():
    size, length, overlap = create_v2(inches(4), inches(6)), inches(20), inches(8)
    timbers = [create_timber(length=length, size=size, bottom_position=create_v3(start, scalar(0), scalar(0)),
                             length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
                             width_direction=create_v3(scalar(0), scalar(0), scalar(1)), ticket=name)
               for name, start in (("timber1", -length + overlap), ("timber2", -overlap))]
    return cut_rebated_oblique_and_dadoed_scarf_joint_on_aligned_timbers(
        arrangement=SpliceJointTimberArrangement(timber1=timbers[0], timber2=timbers[1], timber1_end=TimberEnd.TOP,
                                                 timber2_end=TimberEnd.BOTTOM, front_face_on_timber1=TimberLongFace.RIGHT),
        rebated_shoulder_depth=inches(1), scarf_length=inches(10), dado_depth=inches(1), dado_height=inches(1.5),
        stub_tenon_width=inches(1.5), joint_center_relative_to_timber1_end=overlap)


@pytest.mark.parametrize("build, expected", [
    (_tongue_and_fork_butt, {"tongue_left", "tongue_right", "tongue_front", "tongue_back"}),
    (_tongue_and_fork_corner, {"tongue_front", "tongue_back"}),
    (_cross_lap, {"crossing_left", "crossing_right", "crossing_front", "crossing_back"}),
    (_scarf, {"stub_tenon_left", "stub_tenon_right"}),
], ids=["tongue and fork butt", "tongue and fork corner", "cross lap", "scarf stub tenon"])
def test_a_joint_s_pairs_name_each_other_within_it(build, expected):
    assert expected <= _declared_pairs(build())
