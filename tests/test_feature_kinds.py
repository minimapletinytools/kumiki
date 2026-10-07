"""Feature kinds: every feature is a face, an edge, a point or a curved face, and hits are typed by it."""

from kumiki.csg.cutcsg import (HALF_SPACE_PLANE, CurvedFaceFeature, Cylinder, DerivedPointFeature, EdgeFeature, FaceFeature, FeatureGroup,
                           FeatureOverride, FeatureProperties, HalfSpace, OwnedFeatureHit, PointFeature, PrismFace,
                           RectangularPrism, hit_of_kind, prism_arris_key)
from kumiki.geometry import Line, Plane, Point
from kumiki.rule import Transform, create_v2, create_v3, scalar
from tests.testing_shavings import present


def _box(**features):
    return RectangularPrism(size=create_v2(1, 2), transform=Transform.identity(),
                            start_distance=scalar(0), end_distance=scalar(4), **features)


def test_a_prism_s_defaults_are_faces_edges_and_points():
    kinds = {type(f).__mro__[1] for f in _box().get_declared_features()}
    assert kinds == {FaceFeature, EdgeFeature, PointFeature}
    for feature in _box().get_declared_features():
        located = feature.locate_simple_unbounded(_box())
        expected = {FaceFeature: Plane, EdgeFeature: Line, PointFeature: Point}[type(feature).__mro__[1]]
        assert isinstance(located, expected)


def test_a_cylinder_has_flat_caps_and_a_curved_barrel():
    bore = Cylinder(axis_direction=create_v3(0, 0, 1), radius=scalar(1),
                    start_distance=scalar(0), end_distance=scalar(2))
    faces = [f for f in bore.get_declared_features() if isinstance(f, FaceFeature)]
    curved = [f for f in bore.get_declared_features() if isinstance(f, CurvedFaceFeature)]
    assert len(faces) == 2 and len(curved) == 1


def test_hit_of_kind_narrows_or_declines():
    box = _box()
    face = next(f for f in box.get_declared_features() if isinstance(f, FaceFeature))
    hit = OwnedFeatureHit(feature=face, owner=box)
    assert hit_of_kind(hit, FaceFeature) is hit
    assert hit_of_kind(hit, EdgeFeature) is None


def test_a_derived_point_knows_which_parent_is_the_edge():
    grouped = FeatureProperties(group=FeatureGroup.SHOULDER_PLANE)
    box = _box(feature_overrides=(FeatureOverride(prism_arris_key(PrismFace.FRONT, PrismFace.RIGHT), "arris",
                                                  grouped),))
    cut = HalfSpace(normal=create_v3(0, 0, 1), offset=scalar(1),
                    feature_overrides=(FeatureOverride(HALF_SPACE_PLANE, "cut", FeatureProperties(group=FeatureGroup.ROUGH)),))
    arris = OwnedFeatureHit(feature=next(f for f in box.get_declared_features() if f.name == "arris"), owner=box)
    plane = OwnedFeatureHit(feature=cut.get_declared_features()[0], owner=cut)

    for first, second in ((arris, plane), (plane, arris)):
        point = present(DerivedPointFeature.derive(first, second), "a point")
        assert point.edge.feature.name == "arris" and point.face.feature.name == "cut"
        assert point.parents == (point.edge, point.face)
