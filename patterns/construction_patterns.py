"""
Construction Examples - Testing join_face_aligned_on_face_aligned_timbers
with different reference features
"""

from sympy import Rational
from kumiki import *
from kumiki.patternbook import Pattern

def inches(value):
    """Convert inches to meters using exact rational arithmetic."""
    # 1 inch = 0.0254 meters exactly
    # So value inches = value * 0.0254 = value * 254/10000 = value * 127/5000
    return Rational(value) * Rational(254, 10000)

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
        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        ticket="Post_Left"
    )
    
    # Create right post 4' away in X direction
    post_right = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(feet(4), 0, 0),
        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
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
        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        ticket="Post",
    )

    beam = attach_face_aligned_timber(
        original_timber=post,
        size=beam_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length=feet(4),
        attached_timber_opposite_length=feet(2),
        # position 48" up from the bottom, measured to the beam centerline
        original_timber_end_to_measure_from_for_length_position=TimberReferenceEnd.BOTTOM,
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

patterns = [
    Pattern(path="construction/join_face_aligned_on_face_aligned_timbers", lambda_=lambda center: make_join_face_aligned_on_face_aligned_timbers_example(), pattern_type='frame', tags=['main']),
    Pattern(path="construction/attach_face_aligned_timber", lambda_=lambda center: make_attach_face_aligned_timber_example(), pattern_type='frame', tags=['main']),
]
