"""
Construction Examples - Testing join_face_aligned_on_face_aligned_timbers
with different reference features
"""

from sympy import Rational
from kumiki import *
from kumiki.patternbook import PatternBook, PatternMetadata

def inches(value):
    """Convert inches to meters using exact rational arithmetic."""
    # 1 inch = 0.0254 meters exactly
    # So value inches = value * 0.0254 = value * 254/10000 = value * 127/5000
    return Rational(value) * Rational(254, 10000)

def create_test_posts_with_beam_centerline():
    """
    Create two 4"x4"x8" vertical posts 8" apart, joined by a beam at centerline.
    
    This uses the default centerline reference (feature_to_mark_on_joining_timber=None).
    """
    post_size = create_v2(inches(4), inches(4))
    post_height = inches(8)  # 8 feet = 96 inches
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
    
    # Create right post 8" away in X direction
    post_right = timber_from_directions(
        length=post_height,
        size=post_size,
        bottom_position=create_v3(inches(8), 0, 0),
        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        ticket="Post_Right"
    )
    
    # Join at mid-height (48" up) with centerline reference
    beam_centerline = join_face_aligned_on_face_aligned_timbers(
        timber1=post_left,
        timber2=post_right,
        location_on_timber1=inches(4),  # Middle of 96" post
        stickout=Stickout.nostickout(),
        lateral_offset_from_timber1=inches(0),
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

def create_construction_patternbook() -> PatternBook:
    """
    Create a PatternBook with construction example patterns.
    
    Each pattern has groups: ["construction", "{feature_type}"]
    
    Returns:
        PatternBook: PatternBook containing construction example patterns
    """
    patterns = [
        (PatternMetadata("posts_with_beam_centerline", ["construction", "centerline"], "frame"),
         lambda center: create_test_posts_with_beam_centerline()),
    ]
    
    return PatternBook(patterns=patterns)


patternbook = create_construction_patternbook()


def create_all_construction_examples():
    """Create all construction examples for testing."""
    # For now, just return the centerline example
    # You can create a combined frame if needed
    return create_test_posts_with_beam_centerline()


example = create_all_construction_examples
