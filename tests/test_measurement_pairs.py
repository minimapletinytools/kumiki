"""Joints that declare preferred measurements (FeatureMarkingSpec.mark_relative_to): each names
features found in its own joint, and a symmetric pair names each other."""

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
    """The names of every feature marked relative to others, on every cut timber of a joint or frame."""
    pairs = []
    cuts = joint.cut_timbers if isinstance(joint, Frame) else \
        [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]
    for cut in cuts:
        root = cut.render_timber_with_cuts_csg_local()
        for node in _walk(root):
            for feature in getattr(node, 'get_declared_features', lambda: [])():
                marking = feature.properties.marking_override
                if marking is None or not marking.mark_relative_to:
                    continue
                for name in marking.mark_relative_to:
                    partners = _nearest_named(root, id(node), name)
                    assert partners, f"{feature.name} names {name}, which isn't in its joint"
                    for partner in partners:
                        back = partner.feature.properties.marking_override
                        one_way = feature.properties.datum is Datum.AVOID
                        assert one_way or (back and feature.name in back.mark_relative_to), \
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


def _corner_dovetail():
    from patterns.corner.dovetail_corner_joint_patterns import through
    return through()


def _dropin_dovetail():
    from patterns.butt.dropin_dovetail_butt_joint_patterns import create_dovetail_butt_joint_example
    return create_dovetail_butt_joint_example()


def _free_dovetail():
    from patterns.free.free_dovetail_joint_patterns import example_free_tapered_dovetail
    return example_free_tapered_dovetail()


def _board_dovetail():
    from patterns.board.board_joints_patterns import sliding_dovetail_side_to_face
    return sliding_dovetail_side_to_face()


_FLANKS = {"dovetail_left", "dovetail_right", "dovetail_front"}
_FREE_FLANKS = {"dovetail_left_flank", "dovetail_right_flank", "dovetail_wide_face"}


@pytest.mark.parametrize("build, expected", [
    (_tongue_and_fork_butt, {"tongue_left", "tongue_right", "tongue_front", "tongue_back"}),
    (_tongue_and_fork_corner, {"tongue_front", "tongue_back"}),
    (_cross_lap, {"crossing_left", "crossing_right", "crossing_front", "crossing_back"}),
    (_scarf, {"stub_tenon_left", "stub_tenon_right"}),
    (_corner_dovetail, _FLANKS),
    (_dropin_dovetail, _FLANKS | {"socket_left", "socket_right", "socket_front"}),
    (_free_dovetail, _FREE_FLANKS | {f"{name}×dovetail_forward_end" for name in _FREE_FLANKS}),
    (_board_dovetail, _FREE_FLANKS),
], ids=["tongue and fork butt", "tongue and fork corner", "cross lap", "scarf stub tenon",
        "corner dovetail", "drop-in dovetail", "free dovetail", "sliding board dovetail"])
def test_a_joint_s_pairs_name_each_other_within_it(build, expected):
    assert expected <= _declared_pairs(build())


def _angled_pairs(joint):
    """The feature names at the two ends of every generated angle, a derived edge by its joint's face."""
    from kumiki.drawings.auto_drawings import solve_piece
    from kumiki.drawings.measure import MeasurementOperation

    def name(end):
        if not end.feature.is_derived():
            return end.feature.name
        return next(parent.feature.name for parent in end.feature.parents if parent.feature.name.startswith(
            ("dovetail", "socket")))

    cuts = joint.cut_timbers if isinstance(joint, Frame) else \
        [CutTimber(cutting.timber, cuts=[cutting]) for cutting in joint.cuttings.values()]
    return {frozenset((name(pick.candidate.measure.anchor_a), name(pick.candidate.measure.anchor_b)))
            for cut in cuts for pick in solve_piece(cut, onto_edges=False).picks
            if (kind := pick.candidate.measure.kind) is not None and kind.operation is MeasurementOperation.ANGLE}


@pytest.mark.parametrize("build, wide, flanks", [
    (_corner_dovetail, "dovetail_front", ("dovetail_left", "dovetail_right")),
    (_dropin_dovetail, "dovetail_front", ("dovetail_left", "dovetail_right")),
    (_dropin_dovetail, "socket_front", ("socket_left", "socket_right")),
    (_free_dovetail, "dovetail_wide_face",
     ("dovetail_left_flank×dovetail_forward_end", "dovetail_right_flank×dovetail_forward_end")),
    (_board_dovetail, "dovetail_wide_face", ("dovetail_left_flank", "dovetail_right_flank")),
], ids=["corner dovetail", "drop-in tail", "drop-in socket", "tapered free dovetail", "sliding board dovetail"])
# A lone joint's timbers have no reference faces, so their own faces are left unsolved.
@pytest.mark.filterwarnings("ignore::kumiki.drawings.auto_dimensioning.UnsolvedFeaturesWarning")
@pytest.mark.filterwarnings("ignore::kumiki.drawings.auto_dimensioning.UnmeasurableFeaturesWarning")
def test_a_dovetail_s_flank_angles_are_taken_from_its_wide_face(build, wide, flanks):
    assert {frozenset((flank, wide)) for flank in flanks} <= _angled_pairs(build())
