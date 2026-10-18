"""A timber's rough body carrying the perfect timber within's long faces and centerplanes."""

import pytest

from kumiki import *
from kumiki.csg.carriers import CarrierRef, Midplane
from kumiki.csg.cutcsg import FeatureCategory, FeatureGroup, RectangularPrism, prism_face_key


def _timber(rough_half_sizes=None):
    """PTW 4x6, 100 long; with rough half-sizes, rough stock around it."""
    return Timber(length=scalar(100), size=create_v2(scalar(4), scalar(6)),
                  transform=Transform.identity(), rough_half_sizes=rough_half_sizes)


def _oversawn():
    """RIGHT and BACK oversawn, LEFT and FRONT true: the rough prism sits off the perfect one's axis."""
    return _timber(rough_half_sizes=(create_v2(scalar(3), scalar(2)),    # right, left
                                     create_v2(scalar(3), scalar(4))))   # front, back


def _features(csg):
    return {feature.name: feature for feature in csg.get_declared_features()}


def _same_plane(one, other):
    """Same plane, facing the same way."""
    normal = [float(v) for v in one.normal]
    gap = [float(a) - float(b) for a, b in zip(one.point, other.point)]
    return (all(abs(float(a) - float(b)) < 1e-9 for a, b in zip(one.normal, other.normal))
            and abs(sum(n * g for n, g in zip(normal, gap))) < 1e-9)


class TestWhichAreAdded:

    def test_only_the_faces_off_the_rough_body_and_the_centerplanes(self):
        added = {name for name in _features(_oversawn().get_extended_rough_csg_with_perfect_features_local())
                 if name.startswith("ptw.")}

        # LEFT and FRONT lie on rough faces, which are rptw.left and rptw.front already.
        assert added == {"ptw.right", "ptw.back", "ptw.centerplane_left_right", "ptw.centerplane_front_back"}

    def test_a_timber_with_no_rough_allowance_gets_only_its_centerplanes(self):
        names = _features(_timber().get_extended_rough_csg_with_perfect_features_local())

        assert {name for name in names if name.startswith("ptw.")} == {
            "ptw.centerplane_left_right", "ptw.centerplane_front_back"}
        assert "rptw.right" in names

    def test_the_rough_body_is_unchanged(self):
        timber = _oversawn()
        rough = timber.get_extended_actual_csg_local(True, False)
        carrying = timber.get_extended_rough_csg_with_perfect_features_local(extend_bot=True)

        assert isinstance(carrying, RectangularPrism)
        assert (carrying.size, carrying.transform, carrying.start_distance, carrying.end_distance) == (
            rough.size, rough.transform, rough.start_distance, rough.end_distance)


class TestWhereTheyAre:

    @pytest.mark.parametrize("name", ["ptw.right", "ptw.back", "ptw.centerplane_left_right",
                                      "ptw.centerplane_front_back"])
    def test_on_the_perfect_timber_within_not_the_rough_body(self, name):
        timber = _oversawn()
        carrying = timber.get_extended_rough_csg_with_perfect_features_local()
        perfect = timber.get_perfect_timber_within_csg_local()

        located = _features(carrying)[name].locate_simple_unbounded(carrying)
        expected = _features(perfect)[name].locate_simple_unbounded(perfect)

        assert _same_plane(located, expected)

    def test_a_point_on_one_is_on_it(self):
        carrying = _oversawn().get_extended_rough_csg_with_perfect_features_local()
        feature = _features(carrying)["ptw.right"]

        # The perfect RIGHT face is x = 2, wherever the rough prism sits.
        assert feature.test_point_unbounded(carrying, create_v3(scalar(2), scalar(1), scalar(50)))
        assert not feature.test_point_unbounded(carrying, create_v3(scalar(3), scalar(1), scalar(50)))

    def test_its_extent_spans_the_rough_body(self):
        carrying = _oversawn().get_extended_rough_csg_with_perfect_features_local()
        region = _features(carrying)["ptw.centerplane_front_back"].get_extent(carrying).region

        # y = 0, across the rough width (-2..3) and the length.
        xs = sorted({float(corner[0]) for corner in region.boundary})
        assert {float(corner[1]) for corner in region.boundary} == {0.0}
        assert xs == [-2.0, 3.0]
        assert sorted({float(corner[2]) for corner in region.boundary}) == [0.0, 100.0]


class TestWhatTheyAre:

    def test_non_real(self):
        carrying = _oversawn().get_extended_rough_csg_with_perfect_features_local()

        assert all(not feature.real for name, feature in _features(carrying).items() if name.startswith("ptw."))

    def test_all_of_them_are_perfect_references(self):
        # Inside the material, so cropped to the cut timber -- unlike a bore's axis, in a void.
        from kumiki.csg.cutcsg import FeatureNature

        features = _features(_oversawn().get_extended_rough_csg_with_perfect_features_local())
        added = [feature for name, feature in features.items() if name.startswith("ptw.")]

        assert len(added) == 4
        assert all(feature.nature is FeatureNature.PERFECT_REFERENCE and not feature.real for feature in added)

    def test_faces_are_perfect_and_centerplanes_pair_with_nothing(self):
        # As on the perfect timber within itself.
        features = _features(_oversawn().get_extended_rough_csg_with_perfect_features_local())

        assert features["ptw.right"].group is FeatureGroup.PERFECT
        assert features["ptw.centerplane_left_right"].group is FeatureGroup.NONE


class TestHowTheyAreSolved:
    """A perfect face off the rough body is an unknown of its own; one on it is the rough face's."""

    def test_a_face_off_the_rough_body_is_its_own_carrier_at_the_perfect_plane(self):
        timber = _oversawn()
        carrying = timber.get_extended_rough_csg_with_perfect_features_local()
        right = _features(carrying)["ptw.right"]
        perfect = timber.get_perfect_timber_within_csg_local()

        (ref,) = right.solve_recipe(carrying)
        assert isinstance(ref, CarrierRef) and ref.local[0] is FeatureCategory.EXTRA
        assert _same_plane(carrying.carriers()[ref.local].plane,
                           _features(perfect)["ptw.right"].locate_simple_unbounded(perfect))

    def test_a_face_on_the_rough_body_is_the_rough_face(self):
        carrying = _oversawn().get_extended_rough_csg_with_perfect_features_local()

        assert _features(carrying)["rptw.left"].solve_recipe(carrying) == (
            CarrierRef(carrying, prism_face_key(PrismFace.LEFT)),)

    def test_a_centerplane_is_the_midplane_of_the_two_perfect_planes(self):
        carrying = _oversawn().get_extended_rough_csg_with_perfect_features_local()
        features = _features(carrying)

        (midplane,) = features["ptw.centerplane_left_right"].solve_recipe(carrying)
        assert midplane == Midplane(front=features["ptw.right"].solve_recipe(carrying)[0],
                                    back=features["rptw.left"].solve_recipe(carrying)[0])


class TestRoughFacesAreNotMeasured:
    def test_a_rough_face_serves_rough_face_and_a_perfect_one_does_not(self):
        from kumiki.csg.cutcsg import FeaturePurpose

        features = _features(_oversawn().get_extended_actual_csg_local(extend_bot=False, extend_top=False))
        rough = [f for name, f in features.items() if name.startswith("rough.")]
        perfect = [f for name, f in features.items() if name.startswith("rptw.")]

        assert rough and perfect
        assert all(f.properties.purpose is FeaturePurpose.ROUGH_FACE for f in rough)
        assert all(f.properties.purpose is not FeaturePurpose.ROUGH_FACE for f in perfect)

    def test_only_rough_stock_is_left_unmeasured_by_default(self):
        from kumiki.csg.cutcsg import FeaturePurpose, measured_by_default

        unmeasured = {purpose for purpose in FeaturePurpose if not measured_by_default(purpose)}

        assert unmeasured == {FeaturePurpose.ROUGH_FACE, FeaturePurpose.ROUGH_RELIEF}
