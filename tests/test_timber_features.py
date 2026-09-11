"""The vocabulary for pointing at part of a timber.

Enums only -- values, conversions, and what each feature is related to. What a
feature means geometrically is test_measuring.py's; what makes one usable as a
reference is test_reference_features.py's.

The values are the reason this file exists. Five narrower enums address a
TimberFeature member by its value, so a member that stops agreeing with its
counterpart is a conversion that silently lands on a different feature.
"""

import pytest

from kumiki.timber_features import (LONG_TIMBER_FEATURES, TimberCenterline,
                                    TimberCenterplane, TimberCorner,
                                    TimberEdge, TimberEnd, TimberFace,
                                    TimberFeature, TimberLongEdge,
                                    TimberLongFace, TimberLongFaceCenterline,
                                    TimberShortEdge)


class TestFeatureNumbering:
    def test_every_narrow_enum_member_agrees_with_TimberFeature(self):
        for enum in (TimberFace, TimberEnd, TimberLongFace, TimberEdge,
                     TimberLongEdge, TimberShortEdge, TimberCenterline,
                     TimberLongFaceCenterline, TimberCenterplane):
            for member in enum:
                assert TimberFeature(member.value) is member.to

    def test_seven_is_retired_and_stays_retired(self):
        # CENTERLINE moved off 7 to sit with the other centerlines. Handing 7
        # to something else would turn anything still holding the old value
        # into a different feature without a word.
        with pytest.raises(ValueError):
            TimberFeature(7)

    def test_the_centerlines_are_one_contiguous_run(self):
        values = [TimberFeature.CENTERLINE.value] + [
            member.value for member in TimberLongFaceCenterline]
        assert values == list(range(30, 35))

    def test_the_center_planes_sit_past_the_corners(self):
        # Past the original contiguous 1-27 range, which is what keeps the
        # range() guard in TimberFeature.corner() valid.
        assert [member.value for member in TimberCenterplane] == [28, 29]
        assert max(member.value for member in TimberCorner) == 27

    def test_no_new_member_name_reads_as_a_prism_side_or_arris(self):
        # TestDefaultOrderFollowsTimberFeature picks a prism's sides and
        # arrises out of TimberFeature by name suffix. A centerline ending
        # _FACE, or a center plane ending _EDGE, would join those runs and
        # break the mapping to arris.n without touching that test's file.
        for member in list(TimberCenterplane) + list(TimberLongFaceCenterline):
            assert not member.to.name.endswith("_FACE")
            assert not member.to.name.endswith("_EDGE")


class TestFeatureConverters:
    def test_a_centerline_converts_only_to_the_axis(self):
        assert TimberFeature.CENTERLINE.centerline() is TimberCenterline.CENTERLINE
        # A long face's centerline is a different enum on purpose -- half the
        # library branches on isinstance(x, TimberCenterline) meaning the axis.
        with pytest.raises(ValueError):
            TimberFeature.RIGHT_FACE_CENTERLINE.centerline()

    def test_long_face_centerlines_convert_both_ways(self):
        assert (TimberFeature.BACK_FACE_CENTERLINE.long_face_centerline()
                is TimberLongFaceCenterline.BACK)
        with pytest.raises(ValueError):
            TimberFeature.CENTERLINE.long_face_centerline()

    def test_center_planes_convert_both_ways(self):
        assert (TimberFeature.FRONT_BACK_CENTER_PLANE.center_plane()
                is TimberCenterplane.FRONT_BACK)
        with pytest.raises(ValueError):
            TimberFeature.RIGHT_FACE.center_plane()


class TestWhatAFeatureIsRelatedTo:
    def test_a_long_face_centerline_knows_its_face(self):
        for centerline in TimberLongFaceCenterline:
            assert centerline.long_face.name == centerline.name

    def test_the_centerline_to_plane_pairing_crosses_over(self):
        # The RIGHT face's centerline lies in the FRONT_BACK plane: a face's
        # centerline is where the plane it is NOT parallel to meets it.
        assert TimberLongFaceCenterline.RIGHT.center_plane is TimberCenterplane.FRONT_BACK
        assert TimberLongFaceCenterline.LEFT.center_plane is TimberCenterplane.FRONT_BACK
        assert TimberLongFaceCenterline.FRONT.center_plane is TimberCenterplane.RIGHT_LEFT
        assert TimberLongFaceCenterline.BACK.center_plane is TimberCenterplane.RIGHT_LEFT

    def test_a_center_plane_knows_the_faces_it_sits_between(self):
        assert TimberCenterplane.RIGHT_LEFT.long_faces == (
            TimberLongFace.RIGHT, TimberLongFace.LEFT)
        assert TimberCenterplane.FRONT_BACK.long_faces == (
            TimberLongFace.FRONT, TimberLongFace.BACK)

    def test_an_arris_knows_the_two_faces_it_lies_between(self):
        assert TimberLongEdge.RIGHT_FRONT.long_faces == (
            TimberLongFace.RIGHT, TimberLongFace.FRONT)
        assert TimberLongEdge.BACK_RIGHT.long_faces == (
            TimberLongFace.BACK, TimberLongFace.RIGHT)

    def test_what_each_feature_rests_on(self):
        assert TimberFeature.FRONT_FACE.long_faces_it_rests_on() == (TimberLongFace.FRONT,)
        assert TimberFeature.RIGHT_FRONT_EDGE.long_faces_it_rests_on() == (
            TimberLongFace.RIGHT, TimberLongFace.FRONT)
        # Intrinsic to the perfect timber within: no rough face to disagree.
        assert TimberFeature.CENTERLINE.long_faces_it_rests_on() == ()
        assert TimberFeature.RIGHT_FACE_CENTERLINE.long_faces_it_rests_on() == ()
        assert TimberFeature.RIGHT_LEFT_CENTER_PLANE.long_faces_it_rests_on() == ()
        # Not a long feature at all, so it rests on nothing either.
        assert TimberFeature.TOP_FACE.long_faces_it_rests_on() == ()


class TestTheLongSet:
    def test_it_is_exactly_the_features_an_end_cut_leaves_alone(self):
        assert {member.name for member in LONG_TIMBER_FEATURES} == {
            "RIGHT_FACE", "FRONT_FACE", "LEFT_FACE", "BACK_FACE",
            "RIGHT_FRONT_EDGE", "FRONT_LEFT_EDGE", "LEFT_BACK_EDGE", "BACK_RIGHT_EDGE",
            "RIGHT_LEFT_CENTER_PLANE", "FRONT_BACK_CENTER_PLANE",
            "CENTERLINE",
            "RIGHT_FACE_CENTERLINE", "FRONT_FACE_CENTERLINE",
            "LEFT_FACE_CENTERLINE", "BACK_FACE_CENTERLINE",
        }

    def test_nothing_that_moves_with_an_end_cut_is_in_it(self):
        for member in list(TimberEnd) + list(TimberShortEdge):
            assert member.to not in LONG_TIMBER_FEATURES
        for corner in TimberCorner:
            assert TimberFeature(corner.value) not in LONG_TIMBER_FEATURES
