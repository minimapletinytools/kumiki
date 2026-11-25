"""Finding features by name: on a joint, on a cut timber, and the edges and corners where faces meet."""

import pytest

from kumiki import ButtJointTimberArrangement, Frame, MortiseAndTenonFeatures as MT, TimberEnd, TimberFace, scalar
from kumiki.csg.cutcsg import DerivedEdgeFeature, DerivedPointFeature
from kumiki.csg.feature_paths import to_feature_path
from kumiki.joints.workshop.mixed import cut_mortise_and_tenon_joint_on_face_aligned_timbers
from tests.testing_shavings import create_centered_horizontal_timber, create_standard_vertical_timber


@pytest.fixture(scope="module")
def framed():
    post = create_standard_vertical_timber(height=100, size=(4, 4), position=(0, 0, 0), ticket="post")
    beam = create_centered_horizontal_timber(direction='x', length=100, size=(6, 6), name="beam")
    joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(receiving_timber=beam, butt_timber=post,
                                               butt_timber_end=TimberEnd.BOTTOM, front_face_on_butt_timber=None),
        tenon_width_relative_to_joint=scalar(2), tenon_height_relative_to_joint=scalar(2), tenon_length=scalar(4),
        mortise_depth=scalar(5))
    frame = Frame.from_joints([joint])
    return frame, joint, {cut.timber.ticket.path: cut for cut in frame.cut_timbers}


def test_a_joint_feature_resolves_on_the_frame_s_cut_timber(framed):
    frame, joint, _ = framed
    for name in (MT.SHOULDER, MT.MORTISE_BOTTOM, MT.TENON_LEFT):
        handle = joint.feature(name)
        assert handle.feature.name == name and to_feature_path(handle, frame) is not None


def test_a_missing_name_says_what_is_close(framed):
    _, joint, _ = framed
    with pytest.raises(KeyError, match="did you mean 'mortise_bottom'"):
        joint.feature("mortise_botom")


def test_an_index_picks_among_features_of_one_name(framed):
    _, joint, _ = framed
    assert joint.feature(MT.SHOULDER, 0).feature.name == MT.SHOULDER
    with pytest.raises(ValueError, match="out of range"):
        joint.feature(MT.SHOULDER, 3)


def test_a_cut_timber_finds_its_faces_and_the_edges_and_corners_they_make(framed):
    frame, _, cuts = framed
    post = cuts["post"]
    front, left = post.face(TimberFace.FRONT), post.face(TimberFace.LEFT)
    assert front.feature.name == "rptw.front"
    edge = post.edge(front, left)
    assert isinstance(edge.feature, DerivedEdgeFeature) and to_feature_path(edge, frame) is not None
    corner = post.corner("rptw.front_left", MT.SHOULDER)
    assert isinstance(corner.feature, DerivedPointFeature) and to_feature_path(corner, frame) is not None
    with pytest.raises(ValueError, match="derived edge"):
        post.corner(edge, post.face(TimberFace.TOP))
    assert post.edge(MT.SHOULDER, "rptw.front").feature.name.startswith("shoulder")
    with pytest.raises(ValueError, match="don't meet"):
        post.edge(front, post.face(TimberFace.BACK))
