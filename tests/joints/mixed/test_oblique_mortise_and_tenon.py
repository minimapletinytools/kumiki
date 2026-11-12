"""
A brace's mortise bored square to the post's face: the hole must fit the tenon at every angle.

Every brace in the patterns is at 45 degrees, where sine and cosine agree, so these use braces at
26.6 and 63.4 degrees too (see .claude/plans/archive/oblique-mortise-angle-bug.md).
"""

import math

import pytest

from kumiki import *
from kumiki.rule import inches
from kumiki.csg.cutcsg import csg_children
from kumiki.timber import CutTimber
from kumiki.example_shavings import create_canonical_example_brace_joint_timbers
from kumiki.joints.workshop.mixed import cut_mortise_and_tenon_joint_on_plane_aligned_timbers

TENON_WIDTH = inches(3)    # along the post: the size the angle stretches
TENON_HEIGHT = inches(1)
TENON_LENGTH = inches(5)
MORTISE_DEPTH = inches(3)

# Where the brace meets each timber, as a share of its length, and the angle that makes.
BRACES = {
    "45 degrees": (0.5, 0.5),
    "26.6 degrees": (0.5, 0.25),
    "63.4 degrees": (0.25, 0.5),
}


def _brace_joint(f1, f2, bore_mortise_perpendicular_to_face=True, mortise_depth=MORTISE_DEPTH):
    arr = create_canonical_example_brace_joint_timbers(create_v3(0, 0, 0))
    with pytest.warns(DeprecationWarning):
        brace = join_plane_aligned_on_plane_aligned_timbers(
            timber1=arr.timber1, timber2=arr.timber2,
            location_on_timber1=arr.timber1.length * scalar(f1),
            location_on_timber2=arr.timber2.length * scalar(f2),
            stickout=Stickout.nostickout(), size=arr.timber1.size,
            orientation_long_face_on_timber1=TimberLongFace.RIGHT,
            orientation_long_face_on_timber2=TimberLongFace.RIGHT,
            ticket="brace",
        )
    arrangement = ButtJointTimberArrangement(
        butt_timber=brace, receiving_timber=arr.timber1,
        butt_timber_end=TimberEnd.BOTTOM, front_face_on_butt_timber=TimberLongFace.RIGHT,
    )
    joint = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=TENON_WIDTH, tenon_height_relative_to_joint=TENON_HEIGHT,
        tenon_length=TENON_LENGTH, mortise_depth=mortise_depth,
        bore_mortise_perpendicular_to_face=bore_mortise_perpendicular_to_face,
    )
    return arrangement, joint


def _labelled(joint, name):
    found = []

    def walk(csg):
        if getattr(getattr(csg, "label", None), "name", None) == name:
            found.append(csg)
        for child in csg_children(csg):
            walk(child)

    for cutting in joint.cuttings.values():
        walk(cutting.negative_csg)
    assert len(found) == 1, f"expected one {name}, found {len(found)}"
    return found[0]


def _sin_from_face(arrangement):
    """sin of the angle between the brace and the post: how steeply the tenon enters the face."""
    along_brace = arrangement.butt_timber.get_length_direction_global()
    along_post = arrangement.receiving_timber.get_length_direction_global()
    cos_between = abs(float(sum(along_brace[i] * along_post[i] for i in range(3))))
    return math.sqrt(1 - cos_between ** 2)


@pytest.mark.parametrize("f1,f2", BRACES.values(), ids=BRACES.keys())
def test_the_hole_is_as_long_as_the_tenons_footprint_on_the_face(f1, f2):
    # A tenon of width w entering at angle a to the face covers w / sin(a) of it.
    arrangement, joint = _brace_joint(f1, f2)
    hole = _labelled(joint, "mortise_hole")
    expected = float(TENON_WIDTH) / _sin_from_face(arrangement)
    assert float(hole.size[1]) == pytest.approx(expected, rel=1e-6)
    assert float(hole.size[0]) == pytest.approx(float(TENON_HEIGHT), rel=1e-6)


def _overlap(arrangement, joint, steps=9, depth_steps=41):
    """Points inside both finished timbers, sampled through the tenon's end of the brace."""
    brace, post = arrangement.butt_timber, arrangement.receiving_timber
    brace_left = CutTimber(brace, cuts=[joint.cuttings[brace.ticket.path]]).render_timber_with_cuts_csg_local()
    post_left = CutTimber(post, cuts=[joint.cuttings[post.ticket.path]]).render_timber_with_cuts_csg_local()
    # Across the brace, just inside its tenon; along it, from past the tip to above the shoulder.
    half_x, half_y = 0.48 * float(TENON_HEIGHT), 0.48 * float(TENON_WIDTH)
    reach = float(post.size[0]) * 2
    tenon_points = clashes = 0
    for i in range(steps):
        for k in range(steps):
            for d in range(depth_steps):
                local = create_v3(
                    -half_x + 2 * half_x * i / (steps - 1),
                    -half_y + 2 * half_y * k / (steps - 1),
                    -reach + 2 * reach * d / (depth_steps - 1),
                )
                if not brace_left.contains_point(local):
                    continue
                world = brace.transform.local_to_global(local)
                if not post.transform.global_to_local(world)[0] ** 2 <= (float(post.size[0]) / 2) ** 2:
                    continue
                tenon_points += 1
                if post_left.contains_point(post.transform.global_to_local(world)):
                    clashes += 1
    return tenon_points, clashes


@pytest.mark.parametrize("f1,f2", BRACES.values(), ids=BRACES.keys())
def test_the_tenon_fits_its_hole(f1, f2):
    arrangement, joint = _brace_joint(f1, f2)
    tenon_points, clashes = _overlap(arrangement, joint)
    assert tenon_points > 50, "sampled too little of the tenon to tell"
    assert clashes == 0, f"{clashes} of {tenon_points} tenon points are still inside the post"


@pytest.mark.parametrize("f1,f2", BRACES.values(), ids=BRACES.keys())
def test_without_the_square_bore_the_tenon_fits_too(f1, f2):
    # The hole follows the tenon instead, at any angle; kept here so a fix to the bored hole
    # can't break this one. Its depth runs along the tenon, and nothing crops the tenon to it.
    arrangement, joint = _brace_joint(f1, f2, bore_mortise_perpendicular_to_face=False,
                                      mortise_depth=TENON_LENGTH + inches(1, 4))
    tenon_points, clashes = _overlap(arrangement, joint)
    assert tenon_points > 50
    assert clashes == 0


@pytest.mark.parametrize("f1,f2", BRACES.values(), ids=BRACES.keys())
def test_the_reach_behind_the_shoulder_stays_small(f1, f2):
    # It only has to cover where the slanted shoulder dips behind the tenon's base, which is
    # (size / 2) * tan(angle from the face's normal); anything more is trimmed off, but
    # drawings ask the prism where its faces are.
    arrangement, joint = _brace_joint(f1, f2)
    tenon = _labelled(joint, "tenon")
    sin_face = _sin_from_face(arrangement)
    needed = float(TENON_WIDTH) / 2 * math.sqrt(1 - sin_face ** 2) / sin_face
    assert float(-tenon.start_distance) >= needed - 1e-9
    assert float(-tenon.start_distance) <= 2 * needed + float(TENON_WIDTH)
