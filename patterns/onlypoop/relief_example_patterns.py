"""
Relief algorithm test patterns (DEVELOPMENT ONLY)

These patterns exist to exercise the relief-cut algorithm (chop_scribe_relief /
chop_relief_for_butt_joint_arrangement) across a range of butt-timber approach
angles. All tagged 'poop' -- hidden from the sidebar, not curated examples.
"""

from dataclasses import replace

from kumiki import *
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.joints.workshop.butt_joints import (
    cut_mortise_and_tenon_joint,
    convert_mortise_shoulder_inset_to_centerline_distance,
)
from kumiki.patternbook import Pattern, make_pattern_from_joint

_SHOULDER_INSET = inches(1, 2)

# Canonical (4"x5") timber joint dimensions.
_TENON_SIZE = Matrix([inches(2), inches(2)])
_TENON_LENGTH = inches(3)
_MORTISE_DEPTH = inches(7, 2)

# 1.5"x4" timber joint dimensions -- scaled down so the mortise still fits
# comfortably within the thinner cross-section.
_SMALL_TIMBER_SIZE = create_v2(inches(3, 2), inches(4))
_SMALL_TENON_SIZE = Matrix([inches(1), inches(1)])
_SMALL_TENON_LENGTH = inches(2)
_SMALL_MORTISE_DEPTH = inches(1)

# The butt timber's own local width/height axes (perpendicular to its length
# axis, local Z). Rotating around either tilts the approach angle; rotating
# around length (local Z) would just roll the cross-section and not change
# the angle at all, so those are the only two axes worth varying.
_LOCAL_WIDTH_AXIS = create_v3(scalar(1), scalar(0), scalar(0))
_LOCAL_HEIGHT_AXIS = create_v3(scalar(0), scalar(1), scalar(0))


def _rotate_butt_timber_about_joint(butt_timber, angle_radians, local_axis):
    """
    Rotate butt_timber's orientation by angle_radians around one of its own
    LOCAL axes, while keeping its centerline MIDPOINT fixed in global space.

    create_canonical_example_butt_joint_timbers positions both timbers with
    their length-midpoint at the shared "position" -- that's where the two
    centerlines actually cross and where the shoulder/tenon geometry forms,
    NOT at the butt timber's raw end 24" away. (An earlier version of this
    pivoted around the raw TOP tip instead, which swung the joint itself by
    up to half the timber's length -- the mispositioning seen in the viewer.)
    """
    pivot_local = create_v3(scalar(0), scalar(0), butt_timber.length / scalar(2))
    pivot_global = butt_timber.transform.position + butt_timber.transform.orientation.matrix * pivot_local

    rotation = Orientation.from_angle_axis(angle_radians, local_axis)
    new_orientation = butt_timber.transform.orientation * rotation

    new_bottom_global = pivot_global - new_orientation.matrix * pivot_local

    return replace(butt_timber, transform=Transform(position=new_bottom_global, orientation=new_orientation))


def _build_relief_example(
    rotate_width_axis: bool,
    rotate_height_axis: bool,
    use_small_timbers: bool,
    use_round_timbers: bool,
    position=None,
) -> Joint:
    """Canonical mortise-and-tenon joint (1/2" inset shoulder) with the butt
    timber optionally rotated 45 degrees around its width and/or height axis,
    and optionally converted to round timbers."""
    if position is None:
        position = create_v3(scalar(0), scalar(0), scalar(0))

    if use_small_timbers:
        timber_size = _SMALL_TIMBER_SIZE
        tenon_size, tenon_length, mortise_depth = _SMALL_TENON_SIZE, _SMALL_TENON_LENGTH, _SMALL_MORTISE_DEPTH
    else:
        timber_size = None
        tenon_size, tenon_length, mortise_depth = _TENON_SIZE, _TENON_LENGTH, _MORTISE_DEPTH

    arrangement = create_canonical_example_butt_joint_timbers(position, timber_size=timber_size)
    butt_timber = arrangement.butt_timber
    receiving_timber = arrangement.receiving_timber

    if rotate_width_axis:
        butt_timber = _rotate_butt_timber_about_joint(butt_timber, degrees(45), _LOCAL_WIDTH_AXIS)
    if rotate_height_axis:
        butt_timber = _rotate_butt_timber_about_joint(butt_timber, degrees(45), _LOCAL_HEIGHT_AXIS)

    if use_round_timbers:
        butt_timber = RoundTimber.from_perfect_timber_within(butt_timber)
        receiving_timber = RoundTimber.from_perfect_timber_within(receiving_timber)

    rotated_arrangement = ButtJointTimberArrangement(
        butt_timber=butt_timber,
        receiving_timber=receiving_timber,
        butt_timber_end=arrangement.butt_timber_end,
        front_face_on_butt_timber=arrangement.front_face_on_butt_timber,
    )

    mortise_face = receiving_timber.get_closest_oriented_long_face_from_global_direction(
        -butt_timber.get_length_direction_global()
    ).to.face()
    mortise_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=_SHOULDER_INSET,
        mortise_face=mortise_face,
        receiving_timber=receiving_timber,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=rotated_arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline=mortise_shoulder_distance_from_centerline,
        bore_mortise_perpendicular_to_face=True,
    )


def example_rotate_width_axis(position=None, use_round_timbers=False) -> Joint:
    """Butt timber rotated 45 deg around its width axis (in-plane raking angle)."""
    return _build_relief_example(True, False, False, use_round_timbers, position)


def example_rotate_height_axis(position=None, use_round_timbers=False) -> Joint:
    """Butt timber rotated 45 deg around its height axis (out-of-plane raking angle)."""
    return _build_relief_example(False, True, False, use_round_timbers, position)


def example_rotate_width_and_height_axis(position=None, use_round_timbers=False) -> Joint:
    """Butt timber rotated 45 deg around both its width and height axes (compound angle)."""
    return _build_relief_example(True, True, False, use_round_timbers, position)


def example_rotate_width_axis_small_timbers(position=None, use_round_timbers=False) -> Joint:
    """Same as example_rotate_width_axis but with 1.5"x4" timbers."""
    return _build_relief_example(True, False, True, use_round_timbers, position)


def example_rotate_height_axis_small_timbers(position=None, use_round_timbers=False) -> Joint:
    """Same as example_rotate_height_axis but with 1.5"x4" timbers."""
    return _build_relief_example(False, True, True, use_round_timbers, position)


def example_rotate_width_and_height_axis_small_timbers(position=None, use_round_timbers=False) -> Joint:
    """Same as example_rotate_width_and_height_axis but with 1.5"x4" timbers."""
    return _build_relief_example(True, True, True, use_round_timbers, position)


patterns = [
    Pattern(path="relief/butt_arrangement/rotate_width_axis", lambda_=make_pattern_from_joint(example_rotate_width_axis), pattern_type='frame', tags=['poop']),
    Pattern(path="relief/butt_arrangement/rotate_height_axis", lambda_=make_pattern_from_joint(example_rotate_height_axis), pattern_type='frame', tags=['poop']),
    Pattern(path="relief/butt_arrangement/rotate_width_and_height_axis", lambda_=make_pattern_from_joint(example_rotate_width_and_height_axis), pattern_type='frame', tags=['poop']),
    Pattern(path="relief/butt_arrangement/rotate_width_axis_small_timbers", lambda_=make_pattern_from_joint(example_rotate_width_axis_small_timbers), pattern_type='frame', tags=['poop']),
    Pattern(path="relief/butt_arrangement/rotate_height_axis_small_timbers", lambda_=make_pattern_from_joint(example_rotate_height_axis_small_timbers), pattern_type='frame', tags=['poop']),
    Pattern(path="relief/butt_arrangement/rotate_width_and_height_axis_small_timbers", lambda_=make_pattern_from_joint(example_rotate_width_and_height_axis_small_timbers), pattern_type='frame', tags=['poop']),
]
