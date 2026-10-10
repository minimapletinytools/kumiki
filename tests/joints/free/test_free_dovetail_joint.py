"""cut_free_dovetail_joint: a dovetail of any shape, the socket in one timber and the tongue on the other."""

import pytest

from kumiki import *
from kumiki.csg.cutcsg import FeaturePurpose
from kumiki.drawings.required_features import planning_features


def _beam():
    """Along world x, 100x100, top face at z=50."""
    return create_timber(bottom_position=create_v3(mm(-500), 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 1, 0), ticket="beam")


def _post():
    """Standing on the beam from z=0, 100x100."""
    return create_timber(bottom_position=create_v3(0, 0, 0), length=mm(600), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")


def _dovetail(taper=0, forward=mm(50), backward=mm(50)):
    """Slides along world x across the post: the neck (40 wide) at the beam's top face, flaring down 30 to z=20."""
    origin = Transform(position=create_v3(0, 0, mm(50)),
                       orientation=Orientation.from_x_and_y(create_v3(0, 1, 0), create_v3(0, 0, -1)))
    return FreeDovetailShape(origin=origin, width=mm(40), depth=mm(30), dovetail_angle=degrees(15),
                             forward_length=forward, backward_length=backward, taper_angle=degrees(taper))


def _cut(taper=0):
    beam, post = _beam(), _post()
    joint = cut_free_dovetail_joint(post, beam, _dovetail(taper))
    return (CutTimber(post, cuts=[joint.cuttings["dovetail_timber"]]),
            CutTimber(beam, cuts=[joint.cuttings["receiving_timber"]]))


def _has(cut_timber, x, y, z):
    """Whether the cut timber has material at a world point given in mm."""
    local = cut_timber.timber.transform.global_to_local(create_v3(mm(x), mm(y), mm(z)))
    return cut_timber.render_timber_with_cuts_csg_local().contains_point(local)


class TestFreeDovetailJoint:

    def test_the_tongue_is_the_post_s_and_the_socket_is_cut_from_the_beam(self):
        post, beam = _cut()

        assert _has(post, 0, 0, 35) and not _has(beam, 0, 0, 35)

    def test_beside_and_below_the_tongue_the_post_is_cut_away_and_the_beam_kept(self):
        post, beam = _cut()

        for point in ((0, 40, 35), (0, -40, 35), (0, 0, 10)):
            assert not _has(post, *point), point
            assert _has(beam, *point), point

    def test_above_the_shoulder_the_post_is_whole(self):
        post, _ = _cut()

        assert _has(post, 0, 0, 100) and _has(post, 0, 40, 100)

    def test_the_socket_stops_at_the_dovetail_s_ends(self):
        _, beam = _cut()

        assert _has(beam, 200, 0, 35)

    def test_the_tongue_widens_from_its_neck_so_it_cannot_pull_out(self):
        # 24mm out: outside the 20mm half width at the neck, inside it near the tip.
        post, beam = _cut()

        assert _has(beam, 0, 24, 49) and not _has(post, 0, 24, 49)
        assert not _has(beam, 0, 24, 21) and _has(post, 0, 24, 21)

    def test_a_taper_narrows_it_toward_its_forward_end(self):
        # The dovetail's +z runs along world -x. 18mm out, just below the neck: inside the tapered
        # half width near the backward end (world +x), outside it near the forward end (world -x).
        _, beam = _cut(taper=5)

        assert not _has(beam, 45, 18, 49)
        assert _has(beam, -45, 18, 49)

    def test_the_wide_face_is_the_post_s_shoulder(self):
        post, _ = _cut()

        shoulders = [required.handle.feature.name for required in planning_features(post)
                     if required.handle.feature.properties.purpose is FeaturePurpose.SHOULDER]

        assert shoulders == ["shoulder"]

    def test_a_taper_needs_both_ends(self):
        with pytest.raises(AssertionError, match="finite"):
            _dovetail(taper=5, forward=None)

    def test_the_dovetail_angle_must_be_positive(self):
        origin = _dovetail().origin
        for angle in (0, -15):
            with pytest.raises(AssertionError, match="positive"):
                FreeDovetailShape(origin=origin, width=mm(40), depth=mm(30), dovetail_angle=degrees(angle))

    def test_it_builds_into_a_frame(self):
        frame = Frame.from_joints([cut_free_dovetail_joint(_post(), _beam(), _dovetail())])

        assert len(frame.cut_timbers) == 2
