"""Feature handles, and their wire form (kumiki/feature_paths.py)."""

import pytest

from kumiki.construction import create_timber
from kumiki.cutcsg import DerivedEdgeFeature, OwnedFeatureHit
from kumiki.feature_paths import (FeatureHandle, deserialize_feature_path, find_feature,
                                  resolve_feature_path, serialize_feature_path, to_feature_path)
from kumiki.identity import DerivedFeaturePath, ResolvedTimberPath, SingleFeaturePath
from kumiki.rule import create_v2, create_v3, mm
from kumiki.timber import Frame
from patterns.basic_joints_patterns import example_basic_mortise_and_tenon_joint
from tests.testing_shavings import present

BODY = ("timber (rough, extended)",)


@pytest.fixture
def frame():
    return Frame.from_joints(joints=[example_basic_mortise_and_tenon_joint()])


def _cut(frame, path):
    return present(frame.cut_timber_at(ResolvedTimberPath(path)), path)


def _shoulder_edge(frame):
    butt = _cut(frame, "butt_timber")
    shoulder = present(find_feature(butt, ("mortise_and_tenon", "tenon_waste", "shoulder"), "shoulder"), "shoulder")
    front = present(find_feature(butt, BODY, "rough.front"), "rough.front")
    edge = present(DerivedEdgeFeature.derive(shoulder.hit, front.hit), "an edge")
    return FeatureHandle(timber=butt.timber, hit=OwnedFeatureHit(feature=edge, owner=shoulder.owner))


class TestHandles:

    def test_a_handle_holds_the_node_in_the_rendered_tree(self, frame):
        butt = _cut(frame, "butt_timber")
        handle = present(find_feature(butt, ("mortise_and_tenon", "tenon_waste", "tenon"), "tenon_top"), "tenon_top")
        assert handle.timber is butt.timber
        assert handle.feature.name == "tenon_top"
        assert to_feature_path(handle, frame) is not None

    def test_two_lookups_of_one_feature_are_equal(self, frame):
        butt = _cut(frame, "butt_timber")
        path = ("mortise_and_tenon", "tenon_waste", "tenon")
        assert find_feature(butt, path, "tenon_top") == find_feature(butt, path, "tenon_top")
        assert find_feature(butt, path, "tenon_top") != find_feature(butt, path, "tenon_left")

    def test_a_missing_feature_has_no_handle(self, frame):
        assert find_feature(_cut(frame, "butt_timber"), ("mortise_and_tenon",), "nothing") is None


class TestRoundTrips:

    @pytest.mark.parametrize("timber, csg_path, name", [
        ("butt_timber", ("mortise_and_tenon", "tenon_waste", "tenon"), "tenon_top"),
        ("butt_timber", ("mortise_and_tenon", "tenon_waste", "shoulder"), "shoulder"),
        ("butt_timber", BODY, "rough.front"),
        ("receiving_timber", ("mortise_and_tenon", "mortise_hole"), "mortise_bottom"),
    ])
    def test_a_declared_feature(self, frame, timber, csg_path, name):
        handle = present(find_feature(_cut(frame, timber), csg_path, name), name)
        path = present(to_feature_path(handle, frame), "a path")
        assert isinstance(path, SingleFeaturePath)
        assert path.csg_path == csg_path and path.feature == name
        assert resolve_feature_path(path, frame) == handle

    def test_a_derived_edge(self, frame):
        handle = _shoulder_edge(frame)
        path = present(to_feature_path(handle, frame), "a path")
        assert isinstance(path, DerivedFeaturePath)
        resolved = present(resolve_feature_path(path, frame), "the edge")
        assert isinstance(resolved.feature, DerivedEdgeFeature)
        assert to_feature_path(resolved, frame) == path

    def test_through_the_wire_form(self, frame):
        handle = _shoulder_edge(frame)
        path = present(to_feature_path(handle, frame), "a path")
        assert deserialize_feature_path(serialize_feature_path(path)) == path

    def test_a_timber_not_in_the_frame_has_no_path(self, frame):
        other = Frame.from_joints(joints=[example_basic_mortise_and_tenon_joint()])
        handle = present(find_feature(_cut(other, "butt_timber"), BODY, "rough.front"), "rough.front")
        assert to_feature_path(handle, frame) is None


class TestFrameTimberLookup:

    def _post(self):
        return create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                             length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")

    def test_timbers_sharing_a_name_are_told_apart_by_occurrence(self):
        first, second = self._post(), self._post()
        frame = Frame.from_joints(joints=[], additional_unjointed_timbers=[first, second])
        assert frame.resolved_timber_path_of(second) == ResolvedTimberPath("post", 1)
        assert present(frame.cut_timber_at(ResolvedTimberPath("post", 1)), "post#1").timber is second
        assert frame.cut_timber_at(ResolvedTimberPath("post", 2)) is None
