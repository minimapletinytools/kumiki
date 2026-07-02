"""
Construction Examples - Testing join_face_aligned_on_face_aligned_timbers
with different reference features
"""

from kumiki import *
from kumiki.patternbook import Pattern

def inches(value):
    """Convert inches to meters using exact rational arithmetic."""
    # 1 inch = 0.0254 meters exactly
    # So value inches = value * 0.0254 = value * 254/10000 = value * 127/5000
    return scalar(value) * scalar(254, 10000)

def make_join_face_aligned_on_face_aligned_timbers_example():
    """
    Create two 4"x4"x4' vertical posts 4' apart, joined by a beam at centerline.
    
    This uses the default centerline reference (feature_to_mark_on_joining_timber=None).
    """
    post_size = create_v2(inches(4), inches(4))
    post_height = feet(4) 
    beam_size = create_v2(inches(4), inches(4))
    
    # Create left post at origin
    post_left = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post_Left"
    )
    
    # Create right post 4' away in X direction
    post_right = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(feet(4), 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post_Right"
    )
    
    # Join at mid-height (48" up) with centerline reference
    beam_centerline = join_face_aligned_on_face_aligned_timbers(
        timber1=post_left,
        timber2=post_right,
        location_on_timber1=feet(2),  # Middle of 4' post
        stickout=Stickout.nostickout(),
        lateral_offset_from_timber1=feet(0),
        size=beam_size,
        feature_to_mark_on_joining_timber=TimberFeature.CENTERLINE,  # Default: centerline
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Beam_Centerline"
    )
    
    return Frame(
        cut_timbers=[
            CutTimber(post_left),
            CutTimber(post_right),
            CutTimber(beam_centerline)
        ],
        accessories=[]
    )

def make_attach_face_aligned_timber_example():
    """
    Create a 4"x4" vertical post with a 4"x6" beam attached to its RIGHT face.

    The beam points out of the post's RIGHT face, extends 48" out from the post centerline
    (and 2" the other way, into/through the post), and is positioned 48" up from the bottom
    of the post. It is left flush with the post's FRONT face laterally.
    """
    post_size = create_v2(inches(4), inches(4))
    post_height = inches(96)
    beam_size = create_v2(inches(4), inches(6))

    post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post",
    )

    beam = attach_face_aligned_timber(
        original_timber=post,
        size=beam_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=feet(4),
        attached_timber_stickout=Stickout(feet(2)),
        # position 48" up from the bottom, measured to the beam centerline
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=feet(2),
        # keep the beam's BACK face flush with the post's FRONT face laterally
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.FRONT,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.BACK,
        lateral_position_measurement=feet(0),
        ticket="Attached_Beam",
    )

    return Frame(
        cut_timbers=[
            CutTimber(post),
            CutTimber(beam),
        ],
        accessories=[]
    )

def make_attach_face_aligned_timber_stickout_example(reference: StickoutReference, stickout_length = feet(0)):
    """
    Two 4"x4" vertical posts 3' apart; a 4"x4" timber attached out of the first post's RIGHT
    face at mid-height and extended to the second (target) post, using the same
    StickoutReference on both ends (stickout values 0):

    - CENTER_LINE: runs from the first post's centerline to the target's centerline
    - INSIDE: spans just between the two posts (flush with the first post's RIGHT face,
      touching the near boundary of the target's silhouette)
    - OUTSIDE: passes through both posts (flush with the first post's LEFT face, touching the
      far boundary of the target's silhouette)

    The target post sits in the plane the attached timber extends into, but is rotated 45
    degrees about its own vertical axis: its INSIDE/OUTSIDE references are therefore the
    projected corner edges of its silhouette, which the attached timber's centerline just
    touches.
    """
    post_size = create_v2(inches(4), inches(4))
    post_height = feet(4)
    attached_size = create_v2(inches(4), inches(4))
    span = feet(3)

    post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post",
    )

    target_post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(span, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        # rotated 45 degrees about its own axis
        width_direction=normalize_vector(create_v3(scalar(1), scalar(1), scalar(0))),
        ticket="Target_Post",
    )

    attached = attach_face_aligned_timber(
        original_timber=post,
        size=attached_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=target_post,
        attached_timber_stickout=Stickout.symmetric(stickout_length, reference),
        # attach at mid-height
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=feet(2),
        ticket=f"Attached_{reference.name}",
    )

    return Frame(
        cut_timbers=[
            CutTimber(post),
            CutTimber(target_post),
            CutTimber(attached),
        ],
        accessories=[]
    )

def make_attach_face_aligned_timber_target_projection_example():
    """
    this example demonstrates how `attached_timber_length_or_target` parameter functions when target is not in the same plane as the attached timber.
    The target timber is projected on the attached timber's plane to determine the length of the attached timber.
    """
    post_size = create_v2(inches(4), inches(4))
    post_height = feet(4)
    attached_size = create_v2(inches(4), inches(4))
    span = feet(3)

    post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post",
    )

    target_post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(span, inches(8), 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        # rotated 45 degrees about its own axis
        width_direction=normalize_vector(create_v3(scalar(1), scalar(1), scalar(0))),
        ticket="Target_Post",
    )

    attached = attach_face_aligned_timber(
        original_timber=post,
        size=attached_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=target_post,
        attached_timber_stickout=Stickout.nostickout(),
        # attach at mid-height
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=feet(2),
        ticket="Attached_Timber",
    )

    return Frame(
        cut_timbers=[
            CutTimber(post),
            CutTimber(target_post),
            CutTimber(attached),
        ],
        accessories=[]
    )

def make_attach_face_aligned_timber_flush_example():
    """
    A 5"x5" vertical post with a 5"x7" timber attached to its RIGHT face.

    - Lateral: the attached timber's centerline is offset 1" from the post's (non-centerline)
      FRONT face.
    - Length: the attached timber's RIGHT face is measured 0" from the post's TOP end, so the
      end of the post is flush with that face of the attached timber.
    """
    post_size = create_v2(inches(5), inches(5))
    post_height = feet(8)
    attached_size = create_v2(inches(5), inches(7))

    post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post",
    )

    attached = attach_face_aligned_timber(
        original_timber=post,
        size=attached_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=feet(3),
        # length: the attached timber's RIGHT face is flush (0") with the post's TOP end
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.RIGHT,
        length_position_measurement=inches(0),
        # lateral: 1" from the post's FRONT face (measured to the attached timber's centerline)
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.FRONT,
        lateral_position_measurement=inches(1),
        ticket="Attached_Timber",
    )

    return Frame(
        cut_timbers=[
            CutTimber(post),
            CutTimber(attached),
        ],
        accessories=[]
    )

def make_attach_plane_aligned_timber_brace_example():
    """
    A 4"x4" vertical post with a 4"x4" brace attached to its RIGHT face at 45 degrees.

    The brace points up-and-out of the post's RIGHT face (45 degrees from the post's length axis),
    with its lower end positioned 24" up from the bottom of the post.
    """
    post_size = create_v2(inches(4), inches(4))
    post_height = feet(8)
    brace_size = create_v2(inches(4), inches(4))

    post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post",
    )

    brace = attach_plane_aligned_timber(
        original_timber=post,
        size=brace_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_angle=pi / 4,  # 45 degrees up-and-out
        attached_timber_length_or_target=feet(3),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=inches(24),
        ticket="Brace",
    )

    return Frame(
        cut_timbers=[
            CutTimber(post),
            CutTimber(brace),
        ],
        accessories=[]
    )

def make_attach_timber_example():
    """
    A 4"x4" vertical post with a 4"x4" timber attached pointing in an arbitrary direction.

    Unlike the face/plane-aligned variants, attach_timber takes a raw direction vector and is not
    aligned to the post's faces: the timber points along (2, 1, 1), with its near end 24" up the
    post centerline and offset 6" laterally.
    """
    post_size = create_v2(inches(4), inches(4))
    post_height = feet(8)
    attached_size = create_v2(inches(4), inches(4))

    post = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(0, 0, 0),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),  # Vertical
        width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
        ticket="Post",
    )

    attached = attach_timber(
        original_timber=post,
        size=attached_size,
        attached_timber_direction=create_v3(scalar(2), scalar(1), scalar(1)),  # arbitrary
        attached_timber_length=feet(3),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=inches(24),
        lateral_offset=inches(6),
        ticket="Attached",
    )

    return Frame(
        cut_timbers=[
            CutTimber(post),
            CutTimber(attached),
        ],
        accessories=[]
    )

def _square_footprint(origin_x, origin_y, side):
    """A square footprint with its near corner at (origin_x, origin_y)."""
    return Footprint([
        create_v2(origin_x, origin_y),
        create_v2(origin_x + side, origin_y),
        create_v2(origin_x + side, origin_y + side),
        create_v2(origin_x, origin_y + side),
    ])


def make_footprint_vertical_example():
    """
    inside / outside / center placement of 5 posts on a 2' square footprint: one 4"x4" post on each
    of the 4 corners plus one in the middle. The three placements are shown side by side.
    """
    side = feet(2)
    post_size = create_v2(inches(4), inches(4))
    post_height = feet(2)
    spacing = feet(4)

    footprints = []
    cut_timbers = []
    for i, location in enumerate([FootprintLocation.INSIDE, FootprintLocation.OUTSIDE, FootprintLocation.CENTER]):
        origin_x = spacing * i
        footprint = _square_footprint(origin_x, scalar(0), side)
        footprints.append(footprint)
        # a post on each of the 4 corners, placed inside / outside / on-center of the corner
        for corner in range(4):
            cut_timbers.append(CutTimber(create_vertical_timber_on_footprint_corner(
                footprint, corner, post_height, location, post_size,
                ticket=f"Post_{location.name}_corner{corner}")))
        # a post at the midpoint of side 0, demonstrating non-corner footprint side placement
        mid_post = create_vertical_timber_on_footprint_side(
            footprint, 0, side / 2, post_height, location, post_size,
            ticket=f"Post_{location.name}_side_mid")
        cut_timbers.append(CutTimber(mid_post))

    return Frame(cut_timbers=cut_timbers, accessories=[], footprints=footprints)


def make_footprint_horizontal_example():
    """
    inside / outside / center placement of 4 mudsills on a 2' square footprint (one 4"x4" mudsill
    per side). The three placements are shown side by side.
    """
    side = feet(2)
    mudsill_size = create_v2(inches(4), inches(4))
    spacing = feet(4)

    footprints = []
    cut_timbers = []
    for i, location in enumerate([FootprintLocation.INSIDE, FootprintLocation.OUTSIDE, FootprintLocation.CENTER]):
        origin_x = spacing * i
        footprint = _square_footprint(origin_x, scalar(0), side)
        footprints.append(footprint)
        # a mudsill on each of the 4 sides
        for side_index in range(4):
            cut_timbers.append(CutTimber(create_horizontal_timber_on_footprint(
                footprint, side_index, location, mudsill_size,
                ticket=f"Mudsill_{location.name}_side{side_index}")))

    return Frame(cut_timbers=cut_timbers, accessories=[], footprints=footprints)

patterns = [
    Pattern(path="construction/join_face_aligned_on_face_aligned_timbers", lambda_=lambda center: make_join_face_aligned_on_face_aligned_timbers_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber", lambda_=lambda center: make_attach_face_aligned_timber_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber_flush", lambda_=lambda center: make_attach_face_aligned_timber_flush_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber/stickout/inside", lambda_=lambda center: make_attach_face_aligned_timber_stickout_example(StickoutReference.INSIDE), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber/stickout/outside", lambda_=lambda center: make_attach_face_aligned_timber_stickout_example(StickoutReference.OUTSIDE), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber/stickout/centerline", lambda_=lambda center: make_attach_face_aligned_timber_stickout_example(StickoutReference.CENTER_LINE), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber/stickout/centerline_with_stickout", lambda_=lambda center: make_attach_face_aligned_timber_stickout_example(StickoutReference.CENTER_LINE, stickout_length=feet(1)), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber/make_attach_face_aligned_timber_target_projection_example", lambda_=lambda center: make_attach_face_aligned_timber_target_projection_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_plane_aligned_timber_brace", lambda_=lambda center: make_attach_plane_aligned_timber_brace_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_timber", lambda_=lambda center: make_attach_timber_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/footprint/vertical", lambda_=lambda center: make_footprint_vertical_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/footprint/horizontal", lambda_=lambda center: make_footprint_horizontal_example(), pattern_type='frame', tags=['main']),
]
