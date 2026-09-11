"""Where a timber is measured from: TimberTicket.reference_features.

Two things are pinned here. That a reference has to be a LONG feature, because
a short one moves when the timber is cut to length. And that a reference
resting on a face the rough timber does not match warns rather than raises -- a
timber with no perfect face still has to be measured from somewhere.

The enums themselves are test_timber_features.py's; locating one in space is
test_measuring.py's.
"""

import warnings

import pytest

from kumiki import *
from kumiki.ticket import normalize_reference_features


def _timber(reference_features=(), size=(4, 6)) -> Timber:
    return Timber(
        length=scalar(100),
        size=create_v2(scalar(size[0]), scalar(size[1])),
        transform=Transform.identity(),
        ticket=TimberTicket("post", reference_features=reference_features),
    )


class TestNormalizingTheList:
    def test_a_narrow_member_widens_to_a_TimberFeature(self):
        # Code holding a TimberLongFace should not have to say `.to`. Lists are
        # AUTHORED from TimberFeature -- one vocabulary for a mixed list -- but
        # a narrow member arriving from somewhere else still lands right.
        assert normalize_reference_features((
            TimberLongFace.FRONT, TimberLongEdge.RIGHT_FRONT,
            TimberCenterplane.RIGHT_LEFT, TimberLongFaceCenterline.BACK,
        )) == (
            TimberFeature.FRONT_FACE, TimberFeature.RIGHT_FRONT_EDGE,
            TimberFeature.RIGHT_LEFT_CENTER_PLANE, TimberFeature.BACK_FACE_CENTERLINE)

    def test_the_stored_list_is_always_TimberFeature(self):
        ticket = TimberTicket("post", reference_features=(
            TimberFeature.FRONT_FACE, TimberFeature.RIGHT_FRONT_EDGE))

        assert all(isinstance(f, TimberFeature) for f in ticket.reference_features)

    def test_the_list_defaults_to_empty(self):
        assert TimberTicket("post").reference_features == ()

    def test_order_is_the_priority_and_is_kept(self):
        ticket = TimberTicket("post", reference_features=(
            TimberFeature.BACK_FACE, TimberFeature.RIGHT_FACE, TimberFeature.FRONT_FACE))

        assert [f.name for f in ticket.reference_features] == [
            "BACK_FACE", "RIGHT_FACE", "FRONT_FACE"]

    def test_a_repeat_is_dropped_at_its_later_position(self):
        # Keeping the first is what makes order mean priority: a second mention
        # cannot promote something already spoken for.
        ticket = TimberTicket("post", reference_features=(
            TimberFeature.FRONT_FACE, TimberFeature.RIGHT_FACE,
            TimberFeature.FRONT_FACE))

        assert [f.name for f in ticket.reference_features] == ["FRONT_FACE", "RIGHT_FACE"]

    def test_a_repeat_reaching_it_as_a_narrow_member_is_still_a_repeat(self):
        # Deduping happens after widening, so the same face written two ways is
        # one entry rather than two that look different.
        assert normalize_reference_features(
            (TimberFeature.FRONT_FACE, TimberLongFace.FRONT)
        ) == (TimberFeature.FRONT_FACE,)

    @pytest.mark.parametrize("short_feature", [
        TimberEnd.TOP,
        TimberFace.BOTTOM,
        TimberShortEdge.TOP_RIGHT,
        TimberFeature.BOT_RIGHT_FRONT,
    ])
    def test_a_feature_an_end_cut_moves_is_refused(self, short_feature):
        with pytest.raises(AssertionError, match="not a long feature"):
            TimberTicket("post", reference_features=(short_feature,))

    def test_the_ticket_refuses_without_needing_a_timber(self):
        # Whether a feature is long is a question about the vocabulary, so it
        # is settled here rather than waiting for geometry to exist.
        with pytest.raises(AssertionError, match="not a long feature"):
            normalize_reference_features((TimberEnd.BOTTOM,))


class TestPrimaryReferenceEdge:
    def test_the_first_arris_wins(self):
        ticket = TimberTicket("post", reference_features=(
            TimberFeature.BACK_RIGHT_EDGE, TimberFeature.RIGHT_FRONT_EDGE))

        assert ticket.primary_reference_edge() is TimberLongEdge.BACK_RIGHT

    def test_faces_and_planes_are_skipped_rather_than_turned_into_a_line(self):
        # Deliberately literal: FRONT and RIGHT do meet at an arris, and this
        # still declines to invent it. The author asked for two faces.
        ticket = TimberTicket("post", reference_features=(
            TimberFeature.FRONT_FACE, TimberFeature.RIGHT_LEFT_CENTER_PLANE,
            TimberFeature.RIGHT_FACE, TimberFeature.LEFT_BACK_EDGE))

        assert ticket.primary_reference_edge() is TimberLongEdge.LEFT_BACK

    def test_the_axis_counts_as_a_line(self):
        ticket = TimberTicket("post", reference_features=(
            TimberFeature.FRONT_BACK_CENTER_PLANE, TimberFeature.CENTERLINE))

        assert ticket.primary_reference_edge() is TimberCenterline.CENTERLINE

    def test_a_long_face_centerline_counts_as_a_line(self):
        ticket = TimberTicket("post", reference_features=(
            TimberFeature.FRONT_FACE, TimberFeature.RIGHT_FACE_CENTERLINE))

        assert ticket.primary_reference_edge() is TimberLongFaceCenterline.RIGHT

    def test_nothing_to_answer_with(self):
        assert TimberTicket("post").primary_reference_edge() is None
        assert TimberTicket("post", reference_features=(
            TimberFeature.FRONT_FACE, TimberFeature.RIGHT_LEFT_CENTER_PLANE,
        )).primary_reference_edge() is None


class TestImperfectReferencesWarn:
    """A reference the rough timber does not reach is a warning, not an error."""

    def _round_timber(self, reference_features):
        # A round timber's perfect-timber-within is inscribed in the cylinder,
        # so not one of its long faces is a face of the actual timber.
        return RoundTimber(
            length=scalar(100), size=create_v2(scalar(4), scalar(4)),
            transform=Transform.identity(), diameter=scalar(8),
            ticket=TimberTicket("log", reference_features=reference_features))

    def _half_sawn(self, reference_features):
        """PTW 4x6, with the RIGHT face oversawn and the other three true.

        Asymmetric rough half-sizes, so exactly one long face fails to match
        the perfect timber within -- which is what tells a per-face check apart
        from one that gives up on the whole timber.
        """
        return Timber(
            length=scalar(100), size=create_v2(scalar(4), scalar(6)),
            transform=Transform.identity(),
            rough_half_sizes=(create_v2(scalar(3), scalar(2)),    # right, left
                              create_v2(scalar(3), scalar(3))),   # front, back
            ticket=TimberTicket("beam", reference_features=reference_features))

    def test_a_perfect_timber_says_nothing(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _timber(reference_features=(TimberFeature.FRONT_FACE,
                                        TimberFeature.RIGHT_FRONT_EDGE))

    def test_a_face_the_rough_timber_does_not_match_warns(self):
        with pytest.warns(UserWarning, match="FRONT_FACE"):
            self._round_timber((TimberFeature.FRONT_FACE,))

    def test_a_reference_face_expects_only_its_own_face_to_match(self):
        # FRONT, LEFT and BACK are true on this timber; only RIGHT is not.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self._half_sawn((TimberFeature.FRONT_FACE, TimberFeature.LEFT_FACE,
                             TimberFeature.BACK_FACE))

        with pytest.warns(UserWarning, match="rests on RIGHT"):
            self._half_sawn((TimberFeature.RIGHT_FACE,))

    def test_an_arris_expects_both_of_its_faces_to_match(self):
        # The arris is only where it should be if both faces meeting at it are,
        # so one bad face is enough to warn -- and the message says which.
        with pytest.warns(UserWarning, match="rests on RIGHT and FRONT.*does not on RIGHT"):
            self._half_sawn((TimberFeature.RIGHT_FRONT_EDGE,))

    def test_an_arris_between_two_true_faces_says_nothing(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self._half_sawn((TimberFeature.FRONT_LEFT_EDGE,))

    def test_an_arris_with_neither_face_matching_names_both(self):
        with pytest.warns(UserWarning, match="rests on RIGHT and FRONT. .*It does not\\."):
            self._round_timber((TimberFeature.RIGHT_FRONT_EDGE,))

    def test_a_centerline_or_a_center_plane_never_warns(self):
        # Both are intrinsic to the perfect timber within, which is exactly why
        # they are somewhere to measure from when no face is.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self._round_timber((TimberFeature.CENTERLINE,
                                TimberFeature.RIGHT_LEFT_CENTER_PLANE,
                                TimberFeature.FRONT_FACE_CENTERLINE))

    def test_it_warns_rather_than_raising_so_the_timber_still_exists(self):
        with pytest.warns(UserWarning):
            timber = self._round_timber((TimberFeature.FRONT_FACE,))

        assert timber.ticket.reference_features == (TimberFeature.FRONT_FACE,)
