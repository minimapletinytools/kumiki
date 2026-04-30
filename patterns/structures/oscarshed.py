"""
Oscar's Shed - A simple timber frame shed structure
Built using the Kumiki API
"""

from sympy import Rational
from typing import Optional
import sys
sys.path.append('..')

from kumiki import *
from kumiki.timber import Frame
from kumiki.patternbook import PatternBook, PatternMetadata
from kumiki.joints.basic_joints import cut_basic_mitered_and_keyed_lap_joint


# ============================================================================
# PARAMETERS - Modify these to adjust the shed design
# ============================================================================

# Footprint dimensions (using dimensional helpers)
# the "front/back" of the shed is along the X axis (i.e. the front is wider than it is deep)
# the "sides" of the shed are along the Y axis
base_width = feet(8)      # Long dimension (X direction)
base_length = feet(4)     # Short dimension (Y direction)

# Post parameters
post_inset = inches(5)      # 3 inch inset from corners (2 inches is half the width of a 4x4 post so 2+3=5)

# erhm, look too hard about these measurements. The actual height of the posts gets determined by joints. These #s are just here for initial placement of the posts.
post_back_height = feet(4)   # Height of back posts
post_front_height = feet(5)   # Height of front posts

# Timber size definitions using dimensional helpers
# Format: (vertical dimension, horizontal depth)
small_timber_size = create_v2(inches(4), inches(Rational(5, 2)))   # 4" vertical x 2.5" depth
med_timber_size = create_v2(inches(4), inches(4))                   # 4" x 4"
big_timber_size = create_v2(inches(6), inches(4))                   # 6" vertical x 4" depth


def create_oscar_shed_patternbook() -> PatternBook:
    """
    Create a PatternBook with Oscar's Shed pattern.
    
    Returns:
        PatternBook: PatternBook containing the Oscar's Shed pattern
    """
    patterns = [
        (PatternMetadata("oscar_shed", ["oscar_shed", "complete_structures"], "frame"),
         lambda center: create_oscarshed(center=center)),
    ]
    
    return PatternBook(patterns=patterns)


patternbook = create_oscar_shed_patternbook()


def create_oscarshed(center: Optional[V3] = None):
    """
    Create Oscar's Shed structure.
    
    Args:
        center: Optional center position for the structure (default: origin)
    
    Returns:
        Frame: Frame object containing all cut timbers and accessories for the complete shed
    """
    # Note: Dimensions are already in meters from dimensional helpers
    
    # Default center to origin if not provided
    if center is None:
        center = create_v3(Rational(0), Rational(0), Rational(0))
    
    # ============================================================================
    # BUILD THE STRUCTURE
    # ============================================================================

    # Create the footprint (rectangular, counter-clockwise from bottom-left)
    # Offset by center position (only x and y components)
    footprint_corners = [
        create_v2(center[0] + Rational(0), center[1] + Rational(0)),     # Corner 0: Front-left
        create_v2(center[0] + base_width, center[1] + Rational(0)),      # Corner 1: Front-right
        create_v2(center[0] + base_width, center[1] + base_length),      # Corner 2: Back-right
        create_v2(center[0] + Rational(0), center[1] + base_length)      # Corner 3: Back-left
    ]
    footprint = Footprint(footprint_corners)  # type: ignore[arg-type]

    # ============================================================================
    # Create mudsills on all 4 sides (INSIDE the footprint)
    # ============================================================================
    
    mudsill_size = big_timber_size

    # Front mudsill (corner 0 to corner 1) - along X axis
    # Length is automatically calculated from boundary side
    mudsill_front = create_horizontal_timber_on_footprint(
        footprint, 0, FootprintLocation.INSIDE, mudsill_size, ticket="Front Mudsill"
    )

    # Right mudsill (corner 1 to corner 2) - along Y axis
    mudsill_right = create_horizontal_timber_on_footprint(
        footprint, 1, FootprintLocation.INSIDE, mudsill_size, ticket="Right Mudsill"
    )

    # Back mudsill (corner 2 to corner 3) - along X axis
    mudsill_back = create_horizontal_timber_on_footprint(
        footprint, 2, FootprintLocation.INSIDE, mudsill_size, ticket="Back Mudsill"
    )

    # Left mudsill (corner 3 to corner 0) - along Y axis
    mudsill_left = create_horizontal_timber_on_footprint(
        footprint, 3, FootprintLocation.INSIDE, mudsill_size, ticket="Left Mudsill"
    )

    # ============================================================================
    # Create miter joints at all four corners of the mudsill rectangle
    # ============================================================================
    
    # Corner 0 (front-left): Front mudsill BOTTOM meets Left mudsill TOP
    # Front mudsill goes from corner 0 to corner 1 (BOTTOM=corner 0, TOP=corner 1)
    # Left mudsill goes from corner 3 to corner 0 (BOTTOM=corner 3, TOP=corner 0)
    joint_corner_0 = cut_basic_mitered_and_keyed_lap_joint(
        arrangement=CornerJointTimberArrangement(
            timber1=mudsill_front,
            timber2=mudsill_left,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.TOP,
            front_face_on_timber1=TimberLongFace.RIGHT,
        ),
    )
    
    # Corner 1 (front-right): Front mudsill TOP meets Right mudsill BOTTOM
    # Front mudsill goes from corner 0 to corner 1 (BOTTOM=corner 0, TOP=corner 1)
    # Right mudsill goes from corner 1 to corner 2 (BOTTOM=corner 1, TOP=corner 2)
    joint_corner_1 = cut_basic_mitered_and_keyed_lap_joint(
        arrangement=CornerJointTimberArrangement(
            timber1=mudsill_front,
            timber2=mudsill_right,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.RIGHT,
        ),
    )
    
    # Corner 2 (back-right): Right mudsill TOP meets Back mudsill BOTTOM
    # Right mudsill goes from corner 1 to corner 2 (BOTTOM=corner 1, TOP=corner 2)
    # Back mudsill goes from corner 2 to corner 3 (BOTTOM=corner 2, TOP=corner 3)
    joint_corner_2 = cut_basic_mitered_and_keyed_lap_joint(
        arrangement=CornerJointTimberArrangement(
            timber1=mudsill_right,
            timber2=mudsill_back,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.RIGHT,
        ),
    )
    
    # Corner 3 (back-left): Back mudsill TOP meets Left mudsill BOTTOM
    # Back mudsill goes from corner 2 to corner 3 (BOTTOM=corner 2, TOP=corner 3)
    # Left mudsill goes from corner 3 to corner 0 (BOTTOM=corner 3, TOP=corner 0)
    joint_corner_3 = cut_basic_mitered_and_keyed_lap_joint(
        arrangement=CornerJointTimberArrangement(
            timber1=mudsill_back,
            timber2=mudsill_left,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.RIGHT,
        ),
    )

    # ============================================================================
    # Create posts at corners (inset 6 inches from corners on long side)
    # ============================================================================

    # Post size: 4" x 4" (med_timber_size)
    post_size = med_timber_size
    
    # Front-left post (on front boundary side, inset from left corner)
    # Side 0 goes from corner 0 (front-left) to corner 1 (front-right)
    post_front_left = create_vertical_timber_on_footprint_side(
        footprint, 
        side_index=0,
        distance_along_side=post_inset,
        length=post_front_height,
        location_type=FootprintLocation.INSIDE,
        size=post_size,
        ticket="Front Left Post"
    )

    # Front-right post (on front boundary side, inset from right corner)
    post_front_right = create_vertical_timber_on_footprint_side(
        footprint,
        side_index=0,
        distance_along_side=base_width - post_inset,
        length=post_front_height,
        location_type=FootprintLocation.INSIDE,
        size=post_size,
        ticket="Front Right Post"
    )

    # Back-right post (on back boundary side, inset from right corner)
    # Side 2 goes from corner 2 (back-right) to corner 3 (back-left)
    post_back_right = create_vertical_timber_on_footprint_side(
        footprint,
        side_index=2,
        distance_along_side=post_inset,
        length=post_back_height,
        location_type=FootprintLocation.INSIDE,
        size=post_size,
        ticket="Back Right Post"
    )

    # Back-left post (on back boundary side, inset from left corner)
    post_back_left = create_vertical_timber_on_footprint_side(
        footprint,
        side_index=2,
        distance_along_side=base_width - post_inset,
        length=post_back_height,
        location_type=FootprintLocation.INSIDE,
        size=post_size,
        ticket="Back Left Post"
    )

    # ============================================================================
    # Create additional back posts for uniform spacing
    # ============================================================================
    
    # Calculate positions for 2 additional back posts
    # We want 4 posts total with uniform spacing between them
    # The outer posts are at post_inset and (base_width - post_inset)
    # Space between outer posts: base_width - 2*post_inset
    # With 4 posts, there are 3 equal gaps
    
    back_post_spacing = (base_width - 2 * post_inset) / 3
    
    # Middle-right post (2nd from right)
    post_back_middle_right_position = post_inset + back_post_spacing
    
    post_back_middle_right = create_vertical_timber_on_footprint_side(
        footprint,
        side_index=2,  # Back side
        distance_along_side=post_back_middle_right_position,
        length=post_back_height,
        location_type=FootprintLocation.INSIDE,
        size=post_size,
        ticket="Back Middle-Right Post"
    )
    
    # Middle-left post (3rd from right)
    post_back_middle_left_position = post_inset + 2 * back_post_spacing
    
    post_back_middle_left = create_vertical_timber_on_footprint_side(
        footprint,
        side_index=2,  # Back side
        distance_along_side=post_back_middle_left_position,
        length=post_back_height,
        location_type=FootprintLocation.INSIDE,
        size=post_size,
        ticket="Back Middle-Left Post"
    )

    # ============================================================================
    # Create mortise and tenon joints where corner posts meet mudsills
    # ============================================================================
    # Each corner post's bottom end has a tenon that goes into the mudsill
    # Tenon size: 1x2 inches (2" along X axis, 1" along Y axis)
    # Tenon offset: 1" towards center (for clearance from miter joints)
    # Tenon length: 2 inches
    # Mortise depth: 3 inches (through mortise since mudsill is 4" deep)
    
    tenon_size = Matrix([inches(2), inches(1)])  # 2" along X (mudsill direction), 1" along Y
    tenon_length = inches(3)
    mortise_depth = inches(3.5)
    
    # Front-left post (left side, offset +1" towards center/right)
    tenon_offset_left = Matrix([inches(1), Rational(0)])  # +1" in X
    joint_post_front_left = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=mudsill_front,
            butt_timber=post_front_left,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_offset_left,
    )
    
    # Front-right post (right side, offset -1" towards center/left)
    tenon_offset_right = Matrix([inches(-1), Rational(0)])  # -1" in X
    joint_post_front_right = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=mudsill_front,
            butt_timber=post_front_right,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_offset_right,
    )
    
    # Back-right post (right side, offset -1" towards center/left)
    joint_post_back_right = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=mudsill_back,
            butt_timber=post_back_right,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_offset_left,
    )
    
    # Back-left post (left side, offset +1" towards center/right)
    joint_post_back_left = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=mudsill_back,
            butt_timber=post_back_left,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_offset_right,
    )
    
    # ============================================================================
    # Create mortise and tenon joints for middle back posts with back mudsill
    # ============================================================================
    # Middle posts get mortise and tenon joints (no offset needed since not at corners)
    # Tenon size: 2" x 1" (2" along X axis - mudsill direction, 1" along Y)
    # Tenon length: 3 inches
    # Mortise depth: 3.5 inches
    # No peg (peg_parameters=None)
    
    middle_post_tenon_size = Matrix([inches(2), inches(1)])  # 2" along X (mudsill direction), 1" along Y
    middle_post_tenon_length = inches(3)
    middle_post_mortise_depth = inches(3.5)
    
    # Back middle-right post
    joint_post_back_middle_right = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=mudsill_back,
            butt_timber=post_back_middle_right,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=middle_post_tenon_size,
        tenon_length=middle_post_tenon_length,
        mortise_depth=middle_post_mortise_depth,
    )
    
    # Back middle-left post
    joint_post_back_middle_left = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=mudsill_back,
            butt_timber=post_back_middle_left,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=middle_post_tenon_size,
        tenon_length=middle_post_tenon_length,
        mortise_depth=middle_post_mortise_depth,
    )

    # ============================================================================
    # Create side girts (running from back to front along the short dimension)
    # ============================================================================
    
    side_girt_size = med_timber_size

    # Side girt stickout: 5 inches on back side, 0 on front side
    side_girt_stickout_back = inches(5)  # 5 inches
    side_girt_stickout = Stickout(side_girt_stickout_back, Rational(0))  # Asymmetric: 5" on back, 0 on front
    
    
    # Left side girt (connects back-left post to front-left post)
    # Top of girt aligns with top of back post
    side_girt_left = join_timbers(
        timber1=post_back_left,        # Back post (timber1)
        timber2=post_front_left,       # Front post (timber2)
        location_on_timber1=post_back_height,   # At top of back post
        stickout=side_girt_stickout,   # 5" stickout on back, none on front
        location_on_timber2=post_back_height,    # Same height on front post
        lateral_offset=0,       # No lateral offset
        size=side_girt_size,
        ticket="Left Side Girt"
    )
    
    # Right side girt (connects back-right post to front-right post)
    side_girt_right = join_timbers(
        timber1=post_back_right,       # Back post (timber1)
        timber2=post_front_right,      # Front post (timber2)
        location_on_timber1=post_back_height,   # At top of back post
        stickout=side_girt_stickout,   # 5" stickout on back, none on front
        location_on_timber2=post_back_height,    # Same height on front post
        lateral_offset=0,       # No lateral offset
        size=side_girt_size,
        ticket="Right Side Girt"
    )

    # ============================================================================
    # Create mortise and tenon joints where side girts meet back corner posts
    # ============================================================================
    # Back corner posts have tenons on top that go into mortises in the side girts
    # Tenon size: 1.5" x 3" (3" dimension goes from back to front along girt length)
    # Tenon length: 4.5 inches (through mortise)
    # Mortise depth: 4.5 inches
    # No peg
    
    side_girt_back_tenon_size = Matrix([inches(Rational(3, 2)), inches(3)])  # 1.5" x 3"
    side_girt_back_tenon_length = inches(Rational(9, 2))  # 4.5 inches
    side_girt_back_mortise_depth = inches(Rational(9, 2))  # 4.5 inches (through mortise)
    
    # Back left post TOP end meets left side girt BOTTOM end
    joint_side_girt_left_back = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=side_girt_left,
            butt_timber=post_back_left,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=side_girt_back_tenon_size,
        tenon_length=side_girt_back_tenon_length,
        mortise_depth=side_girt_back_mortise_depth,
    )
    
    # Back right post TOP end meets right side girt BOTTOM end
    joint_side_girt_right_back = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=side_girt_right,
            butt_timber=post_back_right,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=side_girt_back_tenon_size,
        tenon_length=side_girt_back_tenon_length,
        mortise_depth=side_girt_back_mortise_depth,
    )

    # ============================================================================
    # Create mortise and tenon joints where side girts meet front posts
    # ============================================================================
    # Side girts have tenons on the front end (TOP end) that go into the front posts
    # Tenon size: 1" x 2" (1" horizontal, 2" vertical)
    # Tenon length: 3 inches
    # Mortise depth: 3 inches
    # Peg: 5/8" square peg, 1 inch from shoulder, centered
    
    side_girt_tenon_size = Matrix([inches(2), inches(1)])  # 1" horizontal, 2" vertical
    side_girt_tenon_length = inches(3)
    side_girt_mortise_depth = inches(3.5)
    
    # Peg parameters: 5/8" square peg, 1" from shoulder, on centerline
    side_girt_peg_params_left = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(inches(1), Rational(0))],  # 1" from shoulder, centered
        size=inches(Rational(5, 8)),  # 5/8" square
        depth=inches(Rational(7, 2)),
        tenon_hole_offset=inches(Rational(1, 16))
    )
    # Right side uses the same peg params (peg face comes from arrangement)
    side_girt_peg_params_right = side_girt_peg_params_left
    
    # Left side girt TOP end meets front left post
    joint_side_girt_left = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=post_front_left,
            butt_timber=side_girt_left,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_size=side_girt_tenon_size,
        tenon_length=side_girt_tenon_length,
        mortise_depth=side_girt_mortise_depth,
        peg_parameters=side_girt_peg_params_left,
    )
    
    # Right side girt TOP end meets front right post
    joint_side_girt_right = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=post_front_right,
            butt_timber=side_girt_right,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size=side_girt_tenon_size,
        tenon_length=side_girt_tenon_length,
        mortise_depth=side_girt_mortise_depth,
        peg_parameters=side_girt_peg_params_right,
    )
    
    # Collect joint accessories (pegs) for rendering
    # Accessories are already in global space, so just collect them
    side_girt_accessories = []
    if joint_side_girt_left.jointAccessories:
        side_girt_accessories.extend(joint_side_girt_left.jointAccessories.values())
    if joint_side_girt_right.jointAccessories:
        side_girt_accessories.extend(joint_side_girt_right.jointAccessories.values())

    # ============================================================================
    # Create front girt (running left to right along the long dimension)
    # ============================================================================
    
    front_girt_size = med_timber_size
    
    # Front girt is positioned 2 inches below the side girts
    # Side girts attach to front posts at post_back_height
    front_girt_drop = inches(2)
    front_girt_height_on_posts = post_back_height - front_girt_drop
    
    # Front girt stickout: symmetric on both ends (left and right)
    front_girt_stickout = Stickout.symmetric(inches(Rational(3, 2)))  # 1.5 inches
    
    # Front girt connects left front post to right front post
    front_girt = join_timbers(
        timber1=post_front_left,       # Left front post (timber1)
        timber2=post_front_right,      # Right front post (timber2)
        location_on_timber1=front_girt_height_on_posts,   # 2" below side girts
        stickout=front_girt_stickout,  # 1.5" stickout on both sides
        location_on_timber2=front_girt_height_on_posts,   # Same height on right post
        lateral_offset=0,       # No lateral offset
        size=front_girt_size,
        ticket="Front Girt"
    )
    
    # ============================================================================
    # Split the front girt into three pieces and rejoin with gooseneck joints
    # ============================================================================    
    # Middle section is 3 inches wide, centered
    middle_section_width = inches(3)
    
    # Calculate split positions
    # First split: left section ends where middle section begins
    first_split_distance = (front_girt.length - middle_section_width) / Rational(2)
    # Second split: middle section ends (measured from front girt start)
    second_split_distance = first_split_distance + middle_section_width
    
    # Split into three pieces
    front_girt_left_and_middle, front_girt_right = split_timber(
        front_girt, 
        second_split_distance,
        ticket1="Front Girt Left+Middle (temp)",
        ticket2="Front Girt Right"
    )
    
    front_girt_left, front_girt_middle = split_timber(
        front_girt_left_and_middle,
        first_split_distance,
        ticket1="Front Girt Left",
        ticket2="Front Girt Middle"
    )
    
    # Create gooseneck joints
    # Middle section (gooseneck timber) connects to left section (receiving timber)
    # and to right section (receiving timber)
    
    # Gooseneck parameters
    gooseneck_length = inches(3)
    gooseneck_narrow_width = inches(1)  # 1 inch
    gooseneck_wide_width = inches(Rational(3, 2))  # 1.25 inches
    gooseneck_head_length = inches(1.5)  # 1 inch
    gooseneck_depth = inches(Rational(3, 2))  # 1.5 inches (reasonable default)
    lap_length = inches(Rational(1, 2))  # 1.5 inches (reasonable default)
    
    # Left gooseneck joint: middle section BOTTOM end meets left section TOP end
    front_girt_gooseneck_joint_left = cut_lapped_gooseneck_joint(
        arrangement=SpliceJointTimberArrangement(
            timber1=front_girt_middle,
            timber2=front_girt_left,
            timber1_end=TimberReferenceEnd.BOTTOM,
            timber2_end=TimberReferenceEnd.TOP,
            front_face_on_timber1=TimberLongFace.FRONT,
        ),
        gooseneck_length=gooseneck_length,
        gooseneck_small_width=gooseneck_narrow_width,
        gooseneck_large_width=gooseneck_wide_width,
        gooseneck_head_length=gooseneck_head_length,
        lap_length=lap_length,
        gooseneck_lateral_offset=Rational(0),
        gooseneck_depth=gooseneck_depth
    )
    
    # Right gooseneck joint: middle section TOP end meets right section BOTTOM end
    front_girt_gooseneck_joint_right = cut_lapped_gooseneck_joint(
        arrangement=SpliceJointTimberArrangement(
            timber1=front_girt_middle,
            timber2=front_girt_right,
            timber1_end=TimberReferenceEnd.TOP,
            timber2_end=TimberReferenceEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.FRONT,
        ),
        gooseneck_length=gooseneck_length,
        gooseneck_small_width=gooseneck_narrow_width,
        gooseneck_large_width=gooseneck_wide_width,
        gooseneck_head_length=gooseneck_head_length,
        lap_length=lap_length,
        gooseneck_lateral_offset=Rational(0),
        gooseneck_depth=gooseneck_depth
    )
    
    # ============================================================================
    # Create mortise and tenon joints where front girt pieces meet posts
    # ============================================================================
    # Tenon size: 1" x 2" (1" horizontal, 2" vertical)
    # Tenon length: 3 inches
    # Mortise depth: 3 inches
    # Peg: 5/8" square peg, 1 inch from shoulder, centered
    
    front_girt_tenon_size = Matrix([inches(2), inches(1)])
    front_girt_tenon_length = inches(3)
    front_girt_mortise_depth = inches(3.5)
    
    # Peg parameters: 5/8" square peg, 1" from shoulder, on centerline
    front_girt_peg_params = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(inches(1), Rational(0))],  # 1" from shoulder, centered
        size=inches(Rational(5, 8)),  # 5/8" square
        depth=inches(Rational(7, 2)),
        tenon_hole_offset=inches(Rational(1, 16))
    )
    
    # Left end: Front girt left piece BOTTOM meets left front post
    joint_front_girt_left = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=post_front_left,
            butt_timber=front_girt_left,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_size=front_girt_tenon_size,
        tenon_length=front_girt_tenon_length,
        mortise_depth=front_girt_mortise_depth,
        peg_parameters=front_girt_peg_params,
    )
    
    # Right end: Front girt right piece TOP meets right front post
    joint_front_girt_right = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=post_front_right,
            butt_timber=front_girt_right,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_size=front_girt_tenon_size,
        tenon_length=front_girt_tenon_length,
        mortise_depth=front_girt_mortise_depth,
        peg_parameters=front_girt_peg_params,
    )
    
    # Collect cuts for each piece:
    # - Left piece: tenon cuts (BOTTOM end) + gooseneck joint cuts (TOP end)
    # - Middle piece: gooseneck joint cuts (BOTTOM end) + gooseneck joint cuts (TOP end)
    # - Right piece: tenon cuts (TOP end) + gooseneck joint cuts (BOTTOM end)
    
    # The left piece gets cuts from mortise & tenon joint and left gooseneck joint
    front_girt_left_cuts = []
    front_girt_left_cuts.extend(joint_front_girt_left.cut_timbers[front_girt_left.ticket.name].cuts)  # Tenon cuts
    front_girt_left_cuts.extend(front_girt_gooseneck_joint_left.cut_timbers[front_girt_left.ticket.name].cuts)  # Gooseneck cuts
    
    # The middle piece gets cuts from both gooseneck joints
    front_girt_middle_cuts = []
    # Middle piece is referenced in both joints, need to check which one has it
    if front_girt_middle.ticket.name in front_girt_gooseneck_joint_left.cut_timbers:
        front_girt_middle_cuts.extend(front_girt_gooseneck_joint_left.cut_timbers[front_girt_middle.ticket.name].cuts)
    if front_girt_middle.ticket.name in front_girt_gooseneck_joint_right.cut_timbers:
        front_girt_middle_cuts.extend(front_girt_gooseneck_joint_right.cut_timbers[front_girt_middle.ticket.name].cuts)
    
    # The right piece gets cuts from mortise & tenon joint and right gooseneck joint
    front_girt_right_cuts = []
    front_girt_right_cuts.extend(joint_front_girt_right.cut_timbers[front_girt_right.ticket.name].cuts)  # Tenon cuts
    front_girt_right_cuts.extend(front_girt_gooseneck_joint_right.cut_timbers[front_girt_right.ticket.name].cuts)  # Gooseneck cuts
    
    # Create CutTimbers for the split pieces with all their cuts
    pct_front_girt_left = CutTimber(front_girt_left, cuts=front_girt_left_cuts)
    pct_front_girt_middle = CutTimber(front_girt_middle, cuts=front_girt_middle_cuts)
    pct_front_girt_right = CutTimber(front_girt_right, cuts=front_girt_right_cuts)
    
    # Collect joint accessories (pegs) for rendering
    # Accessories are already in global space, so just collect them
    front_girt_accessories = []
    if joint_front_girt_left.jointAccessories:
        front_girt_accessories.extend(joint_front_girt_left.jointAccessories.values())
    if joint_front_girt_right.jointAccessories:
        front_girt_accessories.extend(joint_front_girt_right.jointAccessories.values())

    # ============================================================================
    # Create top plates (running left to right on top of posts)
    # ============================================================================
    
    # Top plate size: 6" x 4" (same as mudsills, 6" vertical)
    top_plate_size = big_timber_size
    
    # Top plate stickout: 1 foot on each side (symmetric)
    top_plate_stickout = Stickout.symmetric(feet(1))
    
    # Front top plate (connects left front post to right front post)
    # Sits on top of the front posts
    top_plate_front = join_timbers(
        timber1=post_front_left,       # Left front post (timber1)
        timber2=post_front_right,      # Right front post (timber2)
        location_on_timber1=post_front_height,   # At top of front post
        stickout=top_plate_stickout,   # 1 foot stickout on both sides
        location_on_timber2=post_front_height,   # Same height on right post
        lateral_offset=0,       # No lateral offset
        size=top_plate_size,
        orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),
        ticket="Front Top Plate"
    )
    
    
    top_plate_back = join_timbers(
        timber1=post_back_left,        # Left back post (timber1)
        timber2=post_back_right,       # Right back post (timber2)
        location_on_timber1=post_back_height+inches(3),    # At top of back post + 3 inches to raise the back beam 2 inches above bottom of side girts
        stickout=top_plate_stickout,   # 1 foot stickout on both sides
        location_on_timber2=post_back_height+inches(3),   
        lateral_offset=0,
        size=top_plate_size,
        orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),
        ticket="Back Top Plate"
    )

    # ============================================================================
    # Create mortise and tenon joints for middle back posts with back top plate
    # ============================================================================
    # Middle posts have tenons on top that go into the back top plate (back beam)
    # Tenon size: 2" x 1" (2" along X axis - top plate direction, 1" along Y)
    # Tenon length: 3 inches
    # Mortise depth: 3.5 inches
    # No peg
    
    # Back middle-right post TOP end meets back top plate
    joint_back_middle_right_to_top_plate = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=top_plate_back,
            butt_timber=post_back_middle_right,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=middle_post_tenon_size,
        tenon_length=middle_post_tenon_length,
        mortise_depth=middle_post_mortise_depth,
    )
    
    # Back middle-left post TOP end meets back top plate
    joint_back_middle_left_to_top_plate = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=top_plate_back,
            butt_timber=post_back_middle_left,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=middle_post_tenon_size,
        tenon_length=middle_post_tenon_length,
        mortise_depth=middle_post_mortise_depth,
    )

    # ============================================================================
    # Create mortise and tenon joints for front posts with front top plate
    # ============================================================================
    # Front posts have tenons on top that go into the front top plate
    # Use same parameters as middle posts: 2" x 1" tenon, 3" length, 3.5" depth
    
    # Front left post TOP end meets front top plate
    joint_front_left_post_to_top_plate = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=top_plate_front,
            butt_timber=post_front_left,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=middle_post_tenon_size,
        tenon_length=middle_post_tenon_length,
        mortise_depth=middle_post_mortise_depth,
    )
    
    # Front right post TOP end meets front top plate
    joint_front_right_post_to_top_plate = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=top_plate_front,
            butt_timber=post_front_right,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=middle_post_tenon_size,
        tenon_length=middle_post_tenon_length,
        mortise_depth=middle_post_mortise_depth,
    )

    # ============================================================================
    # Create housing joints between side girts and back top plate (back beam)
    # ============================================================================
    # The side girts are the housing timber (receiving the housed timber)
    # The back top plate is the housed timber (fitting into the pockets)
    
    joint_back_beam_left_housing = cut_plain_house_joint_DEPRECATED(
        housing_timber=side_girt_left,
        housed_timber=top_plate_back,
        extend_housed_timber_to_infinity=False
    )
    
    joint_back_beam_right_housing = cut_plain_house_joint_DEPRECATED(
        housing_timber=side_girt_right,
        housed_timber=top_plate_back,
        extend_housed_timber_to_infinity=False
    )

    # ============================================================================
    # Create mortise and tenon joints between back corner posts and back top plate
    # ============================================================================
    # Back corner posts have tenons at their TOP end that go into the back beam (back top plate)
    # Tenon size: 1" × 1.5" (1.5" side to side, 1" front to back)
    # Tenon length: 2.5 inches
    # Mortise depth: 2.5 inches
    # No peg
    
    corner_post_to_beam_tenon_size = Matrix([inches(Rational(3, 2)), inches(1)])  # 1" front to back, 1.5" side to side
    corner_post_to_beam_tenon_length = inches(Rational(5, 2))  # 2.5 inches
    corner_post_to_beam_mortise_depth = inches(Rational(5, 2))  # 2.5 inches
    
    # Back left corner post TOP end meets back top plate
    joint_back_left_post_to_beam = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=top_plate_back,
            butt_timber=post_back_left,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=corner_post_to_beam_tenon_size,
        tenon_length=corner_post_to_beam_tenon_length,
        mortise_depth=corner_post_to_beam_mortise_depth,
    )
    
    # Back right corner post TOP end meets back top plate
    joint_back_right_post_to_beam = cut_mortise_and_tenon_joint_on_FAT(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=top_plate_back,
            butt_timber=post_back_right,
            butt_timber_end=TimberReferenceEnd.TOP,
            front_face_on_butt_timber=None,
        ),
        tenon_size=corner_post_to_beam_tenon_size,
        tenon_length=corner_post_to_beam_tenon_length,
        mortise_depth=corner_post_to_beam_mortise_depth,
    )

    # ============================================================================
    # Create joists (running from front to back, between mudsills)
    # ============================================================================
    
    # Joist size: 4" x 4"
    joist_size = med_timber_size
    joist_width = med_timber_size[0]
    
    # Calculate spacing: 3 joists with 4 equal gaps (left side, 2 between joists, right side)
    num_joists = 3
    num_gaps = 4
    gap_spacing = (base_width - num_joists * joist_width) / Rational(num_gaps)
    
    # Joist positions along X axis (from left edge, which is where mudsills start)
    joist_positions_along_mudsill = [
        gap_spacing + joist_width / Rational(2),                      # Joist 1
        Rational(2) * gap_spacing + Rational(3, 2) * joist_width,     # Joist 2
        Rational(3) * gap_spacing + Rational(5, 2) * joist_width      # Joist 3
    ]
    
    # No stickout on joists (flush with mudsills)
    joist_stickout = Stickout.nostickout()
    
    # Calculate vertical offset to make joists flush with top of mudsills
    # Top of mudsill = mudsill_centerline + mudsill_height/2
    # Top of joist = joist_centerline + joist_height/2
    # To align tops: joist_offset = (mudsill_height - joist_height) / 2
    mudsill_height = big_timber_size[0]  # 6" vertical
    joist_height = med_timber_size[0]    # 4" vertical
    joist_vertical_offset = (mudsill_height - joist_height) / Rational(2)  # = 1"
    
    # Create the 3 joists
    joists = []
    
    for i, location_along_mudsill in enumerate(joist_positions_along_mudsill, start=1):
        # Joists connect from front mudsill to back mudsill
        # Mudsills start at X=0 and run along X axis, so the location is just the X position
        
        joist = join_timbers(
            timber1=mudsill_front,             # Front mudsill (timber1)
            timber2=mudsill_back,              # Back mudsill (timber2)
            location_on_timber1=location_along_mudsill,    # Distance along front mudsill
            stickout=joist_stickout,           # No stickout
            location_on_timber2=mudsill_back.length - location_along_mudsill,    # Reversed distance along back mudsill (measured from opposite end)
            lateral_offset=joist_vertical_offset,     # Offset upward to align tops
            size=joist_size,
            orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),  # Face up
            ticket=f"Joist {i}"
        )
        joists.append(joist)


    # ============================================================================
    # Create dovetail butt joints for joists with mudsills
    # ============================================================================
    
    # Dovetail parameters
    dovetail_shoulder_inset = inches(Rational(1, 2))  # 1/2 inch shoulder inset
    dovetail_small_width = inches(Rational(3, 2))     # 1.5 inch small width
    dovetail_large_width = inches(2)                   # 2 inch large width
    dovetail_length = inches(2)                        # 2 inch long
    dovetail_depth = inches(2)                         # 2 inch deep
    
    joist_dovetail_joints = []
    
    for i, joist in enumerate(joists, start=1):
        # Create dovetail joint with front mudsill
        # Joist runs from front (BOTTOM) to back (TOP)
        # The dovetail should be visible on the RIGHT face of the joist (facing right/positive X)
        joint_front = cut_housed_dovetail_butt_joint(
            arrangement=ButtJointTimberArrangement(
                butt_timber=joist,
                receiving_timber=mudsill_front,
                butt_timber_end=TimberReferenceEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
            receiving_timber_shoulder_inset=dovetail_shoulder_inset,
            dovetail_length=dovetail_length,
            dovetail_small_width=dovetail_small_width,
            dovetail_large_width=dovetail_large_width,
            dovetail_lateral_offset=Rational(0),
            dovetail_depth=dovetail_depth
        )
        
        # Create dovetail joint with back mudsill
        joint_back = cut_housed_dovetail_butt_joint(
            arrangement=ButtJointTimberArrangement(
                butt_timber=joist,
                receiving_timber=mudsill_back,
                butt_timber_end=TimberReferenceEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
            receiving_timber_shoulder_inset=dovetail_shoulder_inset,
            dovetail_length=dovetail_length,
            dovetail_small_width=dovetail_small_width,
            dovetail_large_width=dovetail_large_width,
            dovetail_lateral_offset=Rational(0),
            dovetail_depth=dovetail_depth
        )
        
        joist_dovetail_joints.append((joint_front, joint_back))

    # ============================================================================
    # Create rafters (running from back top plate to front top plate)
    # ============================================================================
    
    # Rafter size: 4" x 4"
    rafter_size = med_timber_size
    rafter_width = med_timber_size[0]  # Width of rafter (for spacing calculation)
    
    # Calculate positions for 5 rafters with outer faces flush with ends of top plates
    # The centerline of the first rafter is at rafter_width/2
    # The centerline of the last rafter is at (base_width - rafter_width/2)
    # Distance between outer rafter centerlines: base_width - rafter_width
    # With 5 rafters, there are 4 gaps between centerlines
    
    num_rafters = 5
    rafter_centerline_spacing = (top_plate_front.length - rafter_width) / Rational(num_rafters-1)
    
    # Rafter positions along the top plates (X axis)
    rafter_positions_along_top_plate = []
    for i in range(num_rafters):
        position = rafter_width / Rational(2) + i * rafter_centerline_spacing
        rafter_positions_along_top_plate.append(position)
    
    # Rafters have 12" stickout and are offset upwards by 3 inches from top plate centerlines
    rafter_stickout = Stickout.symmetric(inches(12))
    rafter_vertical_offset = inches(-3)
    
    # Create the 5 rafters
    rafters = []
    
    for i, location_along_top_plate in enumerate(rafter_positions_along_top_plate, start=1):
        # Rafters connect from back top plate to front top plate
        # Top plates run along X axis, so the location is the X position
        
        rafter = join_timbers(
            timber1=top_plate_back,        # Back top plate (timber1)
            timber2=top_plate_front,       # Front top plate (timber2)
            location_on_timber1=location_along_top_plate,  # Position along back top plate (reversed)
            stickout=rafter_stickout,      # 12" stickout
            location_on_timber2=location_along_top_plate,  # Same position on front top plate
            lateral_offset=rafter_vertical_offset,
            size=rafter_size,
            orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),  # Face up
            ticket=f"Rafter {i}"
        )
        rafters.append(rafter)

    # ============================================================================
    # Create house joints for rafter pockets in top plates
    # ============================================================================
    
    # Create house joints for each rafter with both the front and back top plates
    # The top plates are the "housing timber" (receiving the pockets)
    # The rafters are the "housed timber" (fitting into the pockets)
    rafter_house_joints = []
    
    for i, rafter in enumerate(rafters, start=1):
        # TODO switch to not DEPRECATED one
        # Create house joint with back top plate
        joint_back = cut_plain_house_joint_DEPRECATED(
            housing_timber=top_plate_back,
            housed_timber=rafter,
            extend_housed_timber_to_infinity=False
        )
        
        # Create house joint with front top plate
        joint_front = cut_plain_house_joint_DEPRECATED(
            housing_timber=top_plate_front,
            housed_timber=rafter,
            extend_housed_timber_to_infinity=False
        )
        
        rafter_house_joints.append((joint_back, joint_front))

    # ============================================================================
    # Create Frame from joints using the new from_joints constructor
    # ============================================================================
    # The from_joints method automatically:
    # - Extracts all cut timbers from the joints
    # - Merges cuts for timbers that appear in multiple joints
    # - Collects all accessories (pegs, wedges, etc.)
    
    # Collect all joints
    all_joints = [
        # Mudsill corner miter joints
        joint_corner_0,
        joint_corner_1,
        joint_corner_2,
        joint_corner_3,
        # Post to mudsill mortise & tenon joints
        joint_post_front_left,
        joint_post_front_right,
        joint_post_back_right,
        joint_post_back_left,
        joint_post_back_middle_right,
        joint_post_back_middle_left,
        # Side girt joints
        joint_side_girt_left_back,
        joint_side_girt_right_back,
        joint_side_girt_left,
        joint_side_girt_right,
        # Front girt joints
        front_girt_gooseneck_joint_left,
        front_girt_gooseneck_joint_right,
        joint_front_girt_left,
        joint_front_girt_right,
        # Back top plate joints
        joint_back_middle_right_to_top_plate,
        joint_back_middle_left_to_top_plate,
        joint_back_beam_left_housing,
        joint_back_beam_right_housing,
        joint_back_left_post_to_beam,
        joint_back_right_post_to_beam,
        # Front top plate joints
        joint_front_left_post_to_top_plate,
        joint_front_right_post_to_top_plate,
    ]
    
    # Flatten rafter house joints (they're stored as tuples of (back_joint, front_joint))
    for joint_back, joint_front in rafter_house_joints:
        all_joints.append(joint_back)
        all_joints.append(joint_front)
    
    # Add joist dovetail joints (stored as tuples of (front_joint, back_joint))
    for joint_front, joint_back in joist_dovetail_joints:
        all_joints.append(joint_front)
        all_joints.append(joint_back)
    
    # Joists now have dovetail joints, so no unjointed timbers
    unjointed_timbers = []
    
    return Frame.from_joints(all_joints, additional_unjointed_timbers=unjointed_timbers, name="Oscar's Shed")


example = create_oscarshed


# ============================================================================
# Main execution (when run as standalone script)
# ============================================================================

if __name__ == "__main__":
    print(f"Creating Oscar's Shed: 8 ft x 4 ft")
    print(f"  ({float(base_width):.3f} m x {float(base_length):.3f} m)")
    
    frame = create_oscarshed()
    
    print(f"\nCreated {len(frame.cut_timbers)} timbers and {len(frame.accessories)} accessories:")
    for ct in frame.cut_timbers:
        print(f"  - {ct.timber.ticket.name}")
    if frame.accessories:
        print(f"\nAccessories:")
        for acc in frame.accessories:
            print(f"  - {type(acc).__name__}")
    
    # ============================================================================
    # Summary
    # ============================================================================
    
    print("\n" + "="*60)
    print("OSCAR'S SHED - STRUCTURE SUMMARY")
    print("="*60)
    print(f"Footprint: {base_width} ft x {base_length} ft")
    print(f"Mudsills: 4 (all INSIDE footprint, with miter joints at all 4 corners)")
    print(f"Posts: 6 total")
    print(f"  - Front posts: 2 posts, {post_front_height} ft tall")
    print(f"  - Back posts: 4 posts, {post_back_height} ft tall (uniformly spaced)")
    print(f"  - Post inset: {post_inset} ft from corners (outer posts only)")
    print(f"Side Girts: 2 (running from back to front)")
    print(f"  - Stickout: 5 inches on back, 0 on front")
    print(f"Front Girt: 3 pieces (running left to right, joined with gooseneck joints)")
    print(f"  - Position: 2 inches below side girts")
    print(f"  - Stickout: 1.5 inches on both sides (symmetric)")
    print(f"  - Split into 3 parts: left, middle (3\" wide), and right")
    print(f"  - Joined with 2 lapped gooseneck joints (traditional Japanese joinery)")
    print(f"Top Plates: 2 (one front, one back)")
    print(f"  - Size: 6\" x 4\" (6\" vertical, same as mudsills)")
    print(f"  - Position: On top of posts with mortise & tenon joints")
    print(f"  - Front posts: 2\" x 1\" tenon, 3\" long, 3.5\" mortise depth")
    print(f"  - Back middle posts: same dimensions")
    print(f"  - Stickout: 1 foot on both sides (symmetric)")
    print(f"Joists: 3 (running from front to back between mudsills)")
    print(f"  - Size: 4\" x 4\"")
    print(f"  - Spacing: Evenly spaced with equal gaps")
    print(f"  - Position: Tops flush with tops of mudsills")
    print(f"  - No stickout (flush with mudsills lengthwise)")
    print(f"  - Joined with lapped dovetail butt joints (蟻仕口) at both ends")
    print(f"    - Dovetail: 1.5\" to 2\" wide, 2\" long, 2\" deep")
    print(f"    - Shoulder inset: 0.5\" on mudsills")
    print(f"Rafters: 5 (running from back to front on top plates)")
    print(f"  - Size: 4\" x 4\"")
    print(f"  - Spacing: Uniformly spaced")
    print(f"  - Position: 2 inches above top plates (offset upwards)")
    print(f"  - Outside faces of outer rafters flush with ends of top plates")
    print(f"  - Stickout: 12 inches on both ends (symmetric)")
    print(f"  - Top plates have housed joints (rafter pockets) for each rafter")
    print("="*60)

