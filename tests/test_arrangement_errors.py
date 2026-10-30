"""Arrangement and attachment errors name the timbers they are about."""

import warnings

import pytest

from kumiki import *


def _post_and_rail():
    post = create_axis_aligned_timber(create_v3(0, 0, 0), m(1), create_v2(mm(90), mm(90)),
                                      TimberFace.TOP, TimberFace.RIGHT, ticket='post')
    rail = create_axis_aligned_timber(create_v3(-m(0.5), 0, m(1)), m(1), create_v2(mm(90), mm(90)),
                                      TimberFace.RIGHT, TimberFace.FRONT, ticket='top rail')
    return post, rail


def test_a_failed_arrangement_check_names_its_timbers():
    post, rail = _post_and_rail()
    arrangement = ButtJointTimberArrangement(butt_timber=post, receiving_timber=rail, butt_timber_end=TimberEnd.TOP,
                                             front_face_on_butt_timber=TimberLongFace.RIGHT)
    with pytest.raises(KumikiArrangementError) as raised:
        require_check(arrangement.check_plane_aligned(), about=arrangement)
    assert str(raised.value).startswith(
        "ButtJointTimberArrangement (butt_timber 'post', receiving_timber 'top rail'): front_face_on_butt_timber (RIGHT)")
    assert str(raised.value).endswith("use FRONT or BACK")


def test_an_error_about_no_arrangement_is_as_given():
    with pytest.raises(KumikiArrangementError, match="^tenon too long$"):
        require_check("tenon too long")


def test_an_attached_timber_with_no_length_says_which_and_why():
    post, _ = _post_and_rail()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with pytest.raises(KumikiArrangementError) as raised:
            attach_plane_aligned_timber(post, create_v2(mm(50), mm(50)), TimberLongFace.FRONT, pi / 2, -m(0.1), ticket='brace')
    message = str(raised.value)
    assert "the attached timber 'brace' would have no length" in message
    assert "'post's FRONT face or its opposite" in message
    assert "must be more than 0" in message
