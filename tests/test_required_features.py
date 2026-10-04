"""Which faces are on the finished surface, and which features need solving."""

import pytest

from dataclasses import replace

from kumiki.construction import create_timber
from kumiki.csg.cutcsg import (CutCSGLabel, Cylinder, Difference, FeatureMarkingSpec, FeatureMarkingStatus, FeatureOverride,
                           FeatureProperties, HalfSpace, OwnedFeatureHit, PrismFace, RectangularPrism, SolidUnion,
                           prism_face_key)
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.csg.pathcsg import FancyPath, PathExtrusion, StraightSegment
from kumiki.csg.planar_region import face_reaches_surface
from kumiki.drawings.required_features import Reason, required_features
from kumiki.rule import Transform, create_v2, create_v3, mm, scalar
from tests.testing_shavings import mortise_and_tenon_handles

TIMBER = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                       length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="t")


def _box(x, y, z, **features):
    """An axis-aligned box from (low, high) along each axis."""
    return RectangularPrism(
        size=create_v2(x[1] - x[0], y[1] - y[0]),
        transform=Transform(position=create_v3((x[0] + x[1]) / 2, (y[0] + y[1]) / 2, 0),
                            orientation=Transform.identity().orientation),
        start_distance=scalar(z[0]), end_distance=scalar(z[1]), **features)


def _on_surface(owner, face, root):
    feature = next(f for f in owner.get_declared_features() if f.feature_key() == prism_face_key(face))
    handle = FeatureHandle(timber=TIMBER, hit=OwnedFeatureHit(feature=feature, owner=owner))
    return face_reaches_surface(handle, root, create_v3(0, 0, 2), 20.0)


ALL_FACES = list(PrismFace)
TIMBER_BOX = _box((-1, 1), (-1, 1), (0, 4))


class TestFaces:

    def test_every_face_of_a_lone_box(self):
        assert all(_on_surface(TIMBER_BOX, face, TIMBER_BOX) for face in ALL_FACES)

    def test_a_tenon(self):
        shoulder = HalfSpace(normal=create_v3(0, 0, 1), offset=scalar(3))
        tenon = _box((-0.5, 0.5), (-0.5, 0.5), (2, 3.8))
        root = Difference(TIMBER_BOX, [Difference(shoulder, [tenon])])

        assert not _on_surface(tenon, PrismFace.BOTTOM, root), "buried in the wood behind the shoulder"
        assert _on_surface(tenon, PrismFace.TOP, root)
        assert all(_on_surface(tenon, face, root)
                   for face in (PrismFace.RIGHT, PrismFace.LEFT, PrismFace.FRONT, PrismFace.BACK))
        assert _on_surface(TIMBER_BOX, PrismFace.RIGHT, root)

    def test_a_tenon_back_face_exactly_on_the_shoulder(self):
        shoulder = HalfSpace(normal=create_v3(0, 0, 1), offset=scalar(3))
        tenon = _box((-0.5, 0.5), (-0.5, 0.5), (3, 3.8))
        root = Difference(TIMBER_BOX, [Difference(shoulder, [tenon])])

        assert not _on_surface(tenon, PrismFace.BOTTOM, root)

    def test_a_mortise_cutter_started_out_in_the_air(self):
        cutter = _box((0, 2), (-0.5, 0.5), (1.5, 2.5))
        root = Difference(TIMBER_BOX, [cutter])

        assert not _on_surface(cutter, PrismFace.RIGHT, root), "outside the timber"
        assert _on_surface(cutter, PrismFace.LEFT, root), "the floor"
        assert all(_on_surface(cutter, face, root)
                   for face in (PrismFace.FRONT, PrismFace.BACK, PrismFace.TOP, PrismFace.BOTTOM))

    def test_a_face_swallowed_by_a_union(self):
        cutter = _box((0, 2), (-0.5, 0.5), (1.5, 2.5))
        inner = _box((0.4, 0.8), (-0.2, 0.2), (1.8, 2.2))
        root = Difference(TIMBER_BOX, [SolidUnion([cutter, inner])])

        assert not any(_on_surface(inner, face, root) for face in ALL_FACES)

    def test_a_cutter_face_flush_with_the_timber_face_is_the_opening(self):
        cutter = _box((0, 1), (-0.5, 0.5), (1.5, 2.5))
        root = Difference(TIMBER_BOX, [cutter])

        assert not _on_surface(cutter, PrismFace.RIGHT, root)
        assert _on_surface(TIMBER_BOX, PrismFace.RIGHT, root)

    def test_a_cutter_grazing_an_arris(self):
        cutter = _box((1, 2), (1, 2), (0, 4))
        root = Difference(TIMBER_BOX, [cutter])

        assert not any(_on_surface(cutter, face, root) for face in ALL_FACES)

    def test_a_mortise_wall_pierced_by_a_peg_hole(self):
        cutter = _box((0, 2), (-0.5, 0.5), (1.5, 2.5))
        peg = Cylinder(axis_direction=create_v3(0, 1, 0), radius=scalar(0.2), position=create_v3(0.5, 0, 2),
                       start_distance=scalar(-2), end_distance=scalar(2))
        root = Difference(TIMBER_BOX, [cutter, peg])

        assert _on_surface(cutter, PrismFace.FRONT, root)

    def test_faces_inside_a_peg_hole_are_hidden(self):
        # Planes along the peg's axis cut it in a strip; across it, in a circle.
        peg = Cylinder(axis_direction=create_v3(0, 1, 0), radius=scalar(0.2), position=create_v3(0.5, 0, 2),
                       start_distance=scalar(-2), end_distance=scalar(2))
        inner = _box((0.4, 0.6), (-0.1, 0.1), (1.9, 2.1))
        root = Difference(TIMBER_BOX, [SolidUnion([peg, inner])])

        assert not any(_on_surface(inner, face, root) for face in ALL_FACES)

    def test_a_concave_path_extrusion_cut(self):
        corners = [create_v2(*p) for p in ((0, -2), (2, -2), (2, 2), (1, 2), (1, 0), (0, 0))]
        path = FancyPath(segments=[StraightSegment(corners[i], corners[(i + 1) % len(corners)])
                                   for i in range(len(corners))])
        notch = PathExtrusion(path=path, transform=Transform.identity(),
                              start_distance=scalar(1.5), end_distance=scalar(2.5))
        inside = _box((0.2, 0.8), (-1.5, -0.5), (1.8, 2.2))
        root = Difference(TIMBER_BOX, [SolidUnion([notch, inside])])

        assert not any(_on_surface(inside, face, root) for face in ALL_FACES)
        assert _on_surface(TIMBER_BOX, PrismFace.RIGHT, root)


class TestRequiredFeatures:

    def test_a_mortise_and_tenon(self):
        frame, found = mortise_and_tenon_handles()
        names = {}
        for cut_timber in frame.cut_timbers:
            names[cut_timber.timber.ticket.path] = {r.handle.feature.name for r in required_features(cut_timber)}

        assert {"shoulder", "tenon_top", "tenon_left", "tenon_right", "tenon_front", "tenon_back"} <= names["butt_timber"]
        assert "cap.0" not in names["butt_timber"], "the tenon's back face lies on the shoulder"
        assert "rough.top" not in names["butt_timber"], "that end runs to infinity"
        assert {"mortise_left", "mortise_right", "mortise_front", "mortise_back"} <= names["receiving_timber"]
        assert "mortise_bottom" not in names["receiving_timber"], "a through mortise's bottom is the opening"

    def _cut_timber_with(self, **features):
        from kumiki.timber import CutTimber, Cutting

        peg = Cylinder(axis_direction=create_v3(0, 1, 0), radius=scalar(0.01), position=create_v3(0, 0, 0.5),
                       start_distance=scalar(-1), end_distance=scalar(1), label=CutCSGLabel("peg"), **features)
        return CutTimber(TIMBER, cuts=[Cutting(timber=TIMBER, negative_csg=peg)])

    def _reasons(self, cut_timber):
        return {r.handle.feature.name: r.reason for r in required_features(cut_timber)}

    def test_a_bore_is_required_and_so_is_its_axis(self):
        from kumiki.csg.cutcsg import CylinderAxisFeature

        reasons = self._reasons(self._cut_timber_with(extra_features=(CylinderAxisFeature(name="axis"),)))

        assert reasons["axis"] is Reason.NON_REAL
        assert reasons["side.0"] is Reason.CURVED

    def test_marking_overrides_the_surface(self):
        never = FeatureProperties(marking_override=FeatureMarkingSpec(mark=FeatureMarkingStatus.NEVER_MARK))
        always = FeatureProperties(marking_override=FeatureMarkingSpec(mark=FeatureMarkingStatus.ALWAYS_MARK))
        from kumiki.csg.cutcsg import CYLINDER_BARREL, START_CAP

        reasons = self._reasons(self._cut_timber_with(feature_overrides=(
            FeatureOverride(key=CYLINDER_BARREL, name="bore", properties=never),
            FeatureOverride(key=START_CAP, name="hidden end", properties=always),
        )))

        assert "bore" not in reasons
        assert reasons["hidden end"] is Reason.MARKED


def test_a_face_test_can_be_swapped():
    frame, _ = mortise_and_tenon_handles()
    cut_timber = frame.cut_timbers[0]

    assert required_features(cut_timber, face_test=lambda *_: False) == [
        r for r in required_features(cut_timber) if r.reason is not Reason.ON_SURFACE]
