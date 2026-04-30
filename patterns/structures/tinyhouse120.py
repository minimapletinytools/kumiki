"""
Tiny House 120 sqft - A 15' x 8' timber frame tiny house
Posts are on the INSIDE of the footprint. Front is the 15' side.
"""

import sys

from sympy import Rational, Integer, sqrt
from typing import Optional

from kumiki import *
from kumiki.timber import Frame, add_milestone
from kumiki.patternbook import PatternBook, PatternMetadata

# ============================================================================
# PARAMETERS
# ============================================================================

# Footprint dimensions
# Front/back is 15' along X axis, sides are 8' along Y axis
house_width = feet(15)    # X direction (front/back)
house_depth = feet(8)     # Y direction (sides)

# Lumber sizes (nominal -> actual: 3.5" x 3.5" and 3.5" x 5.5")
size_4x4 = create_v2(inches(Rational(7, 2)), inches(Rational(7, 2)))
size_4x6 = create_v2(inches(Rational(7, 2)), inches(Rational(11, 2)))

# Post parameters
post_size = size_4x4
corner_post_height = feet(11)


# Beam parameters — all horizontal members are 4x6 with 6" (5.5") in Z
# With orientation_face=TimberFace.TOP, size[0] maps to Z axis
beam_size = create_v2(inches(Rational(11, 2)), inches(Rational(7, 2)))  # 5.5" in Z, 3.5" across
bottom_beam_height = inches(6)   # Bottom of beam at 6" above ground
mid_beam_height = feet(7)        # Mid-height perimeter beam at 7'
top_plate_height = feet(11)      # Top plates at 11'

# Non-corner posts reach the top of the mid-height beam (7' + 5.5")
non_corner_post_height = mid_beam_height + beam_size[0]

# Stud mortise-and-tenon parameters
stud_tenon_size = create_v2(inches(1), inches(Rational(5, 2)))
stud_tenon_depth = inches(Rational(5, 2))
stud_tenon_outside_offset = inches(1)



def create_tinyhouse120_patternbook() -> PatternBook:
    patterns = [
        (PatternMetadata("tinyhouse120", ["tinyhouse", "complete_structures"], "frame"),
         lambda center: create_tinyhouse120(center=center)),
    ]
    return PatternBook(patterns=patterns)


patternbook = create_tinyhouse120_patternbook()


def create_tinyhouse120(center: Optional[V3] = None):
    """
    Create a 120 sqft tiny house frame (15' x 8').
    No joints yet — just timbers placed in position.
    """
    add_milestone('begin')
    
    if center is None:
        center = create_v3(Rational(0), Rational(0), Rational(0))

    no_stickout = Stickout.nostickout()

    def _format_debug_value(value: object) -> str:
        return str(value).replace("\n", " ")

    def _describe_timber(label: str, timber: PerfectTimberWithin) -> str:
        return (
            f"{label}: ticket={timber.ticket.name}, "
            f"bottom={_format_debug_value(timber.get_bottom_position_global())}, "
            f"length={_format_debug_value(timber.length)}, "
            f"length_dir={_format_debug_value(timber.get_length_direction_global())}, "
            f"width_dir={_format_debug_value(timber.get_width_direction_global())}, "
            f"height_dir={_format_debug_value(timber.get_height_direction_global())}, "
            f"transform={_format_debug_value(timber.transform)}"
        )

    # ========================================================================
    # FOOTPRINT (counter-clockwise from front-left)
    # ========================================================================
    footprint_corners = [
        create_v2(center[0] + Rational(0), center[1] + Rational(0)),          # Corner 0: Front-left
        create_v2(center[0] + house_width, center[1] + Rational(0)),          # Corner 1: Front-right
        create_v2(center[0] + house_width, center[1] + house_depth),          # Corner 2: Back-right
        create_v2(center[0] + Rational(0), center[1] + house_depth),          # Corner 3: Back-left
    ]
    footprint = Footprint(footprint_corners)  # type: ignore[arg-type]

    # ========================================================================
    # POSTS — 4 columns (along 15' front/back) x 3 rows (along 8' sides)
    #
    # Layout (top view, Y points into screen):
    #
    #   Back (side 2):   BL ------- BM1 ------ BM2 ------- BR
    #                     |                                  |
    #   Left (side 3):  ML                                  MR  :Right (side 1)
    #                     |                                  |
    #   Front (side 0):  FL ------- FM1 ------ FM2 ------- FR
    #
    # 4 posts on 15' sides: evenly spaced (at corners + 2 intermediate)
    # 3 posts on 8' sides: at corners + 1 intermediate (middle)
    # ========================================================================

    # Spacing for 4 posts on 15' side: corners at ends, so 3 equal gaps
    front_back_spacing = house_width / Integer(3)
    # Spacing for 3 posts on 8' side: corners at ends, so 2 equal gaps
    side_spacing = house_depth / Integer(2)

    # --- Corner posts (11' tall) ---
    post_FL = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=0, length=corner_post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Front-Left Corner Post"
    )
    post_FR = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=1, length=corner_post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Front-Right Corner Post"
    )
    post_BR = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=2, length=corner_post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Back-Right Corner Post"
    )
    post_BL = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=3, length=corner_post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Back-Left Corner Post"
    )

    # --- Front intermediate posts (8' tall) ---
    # Side 0 goes from corner 0 (FL) to corner 1 (FR)
    post_FM1 = create_vertical_timber_on_footprint_side(
        footprint, side_index=0, distance_along_side=front_back_spacing,
        length=non_corner_post_height, location_type=FootprintLocation.INSIDE,
        size=post_size, ticket="Front-Middle-Left Post"
    )
    post_FM2 = create_vertical_timber_on_footprint_side(
        footprint, side_index=0, distance_along_side=Integer(2) * front_back_spacing,
        length=non_corner_post_height, location_type=FootprintLocation.INSIDE,
        size=post_size, ticket="Front-Middle-Right Post"
    )

    # --- Back intermediate posts (8' tall) ---
    # Side 2 goes from corner 2 (BR) to corner 3 (BL)
    # distance_along_side is measured from corner 2 (BR)
    post_BM1 = create_vertical_timber_on_footprint_side(
        footprint, side_index=2, distance_along_side=front_back_spacing,
        length=non_corner_post_height, location_type=FootprintLocation.INSIDE,
        size=post_size, ticket="Back-Middle-Right Post"
    )
    post_BM2 = create_vertical_timber_on_footprint_side(
        footprint, side_index=2, distance_along_side=Integer(2) * front_back_spacing,
        length=non_corner_post_height, location_type=FootprintLocation.INSIDE,
        size=post_size, ticket="Back-Middle-Left Post"
    )

    # --- Side intermediate posts (8' tall, middle of 8' sides) ---
    # Side 1 goes from corner 1 (FR) to corner 2 (BR)
    post_MR = create_vertical_timber_on_footprint_side(
        footprint, side_index=1, distance_along_side=side_spacing,
        length=non_corner_post_height, location_type=FootprintLocation.INSIDE,
        size=post_size, ticket="Right-Middle Post"
    )
    # Side 3 goes from corner 3 (BL) to corner 0 (FL)
    post_ML = create_vertical_timber_on_footprint_side(
        footprint, side_index=3, distance_along_side=side_spacing,
        length=non_corner_post_height, location_type=FootprintLocation.INSIDE,
        size=post_size, ticket="Left-Middle Post"
    )

    # Collect all posts for convenience
    all_posts = [
        post_FL, post_FM1, post_FM2, post_FR,
        post_MR,
        post_BR, post_BM1, post_BM2, post_BL,
        post_ML,
    ]
    add_milestone('posts')

    # ========================================================================
    # BOTTOM PERIMETER BEAMS — 4x6 connecting each post to its neighbor
    # around the perimeter, bottom of beam at 6" above ground.
    # 6" dimension (5.5" actual) in +Z direction.
    #
    # location_on_timber = height from post bottom where beam centerline is.
    # Beam is 5.5" tall, bottom at 6" means centerline at 6" + 5.5"/2 = 8.75"
    # ========================================================================
    beam_centerline_height = bottom_beam_height + beam_size[0] / Integer(2)

    # Front perimeter: FL -> FM1 -> FM2 -> FR
    beam_front_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FL, timber2=post_FM1,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Front Bottom Beam 1"
    )
    beam_front_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FM1, timber2=post_FM2,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Front Bottom Beam 2"
    )
    beam_front_3 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FM2, timber2=post_FR,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Front Bottom Beam 3"
    )

    # Right perimeter: FR -> MR -> BR
    beam_right_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FR, timber2=post_MR,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Right Bottom Beam 1"
    )
    beam_right_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_MR, timber2=post_BR,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Right Bottom Beam 2"
    )

    # Back perimeter: BR -> BM1 -> BM2 -> BL
    beam_back_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_BR, timber2=post_BM1,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Back Bottom Beam 1"
    )
    beam_back_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_BM1, timber2=post_BM2,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Back Bottom Beam 2"
    )
    beam_back_3 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_BM2, timber2=post_BL,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Back Bottom Beam 3"
    )

    # Left perimeter: BL -> ML -> FL
    beam_left_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_BL, timber2=post_ML,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Left Bottom Beam 1"
    )
    beam_left_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=post_ML, timber2=post_FL,
        location_on_timber1=beam_centerline_height,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Left Bottom Beam 2"
    )

    # ========================================================================
    # FLOOR JOISTS — join_timbers front-to-back, using beam segment midpoints.
    # - FM1<->FM2 zone uses beam_front_2 midpoint
    # - Also connect midpoints of beam_front_1/2/3 to corresponding back beams
    #   (back segments are reversed in X: 1<->3, 2<->2, 3<->1).
    # ========================================================================
    floor_joist_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_front_1,
        timber2=beam_back_3,
        location_on_timber1=beam_front_1.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Floor Joist 1",
    )
    floor_joist_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_front_2,
        timber2=beam_back_2,
        location_on_timber1=beam_front_2.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Floor Joist 2",
    )
    floor_joist_3 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_front_3,
        timber2=beam_back_1,
        location_on_timber1=beam_front_3.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Floor Joist 3",
    )
    floor_joist_4 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_front_2,
        timber2=beam_back_2,
        location_on_timber1=Integer(0),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Floor Joist FM1-BM",
    )
    floor_joist_5 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_front_2,
        timber2=beam_back_2,
        location_on_timber1=beam_front_2.length,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Floor Joist FM2-BM",
    )

    floor_joists = [floor_joist_1, floor_joist_2, floor_joist_3, floor_joist_4, floor_joist_5]
    add_milestone('floor joists')

    # ========================================================================
    # MID-HEIGHT PERIMETER BEAM at 7' — connects corner posts only
    # ========================================================================
    mid_beam_centerline = mid_beam_height + beam_size[0] / Integer(2)

    mid_beam_front = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FL, timber2=post_FR,
        location_on_timber1=mid_beam_centerline,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Mid-Height Front Beam"
    )
    mid_beam_right = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FR, timber2=post_BR,
        location_on_timber1=mid_beam_centerline,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Mid-Height Right Beam"
    )
    mid_beam_back = join_face_aligned_on_face_aligned_timbers(
        timber1=post_BR, timber2=post_BL,
        location_on_timber1=mid_beam_centerline,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Mid-Height Back Beam"
    )
    mid_beam_left = join_face_aligned_on_face_aligned_timbers(
        timber1=post_BL, timber2=post_FL,
        location_on_timber1=mid_beam_centerline,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Mid-Height Left Beam"
    )

    # ========================================================================
    # LOFT BEAMS — 2 beams connecting front/back mid-height beams, aligned with
    # FM1/FM2 (and corresponding BM intersections).
    # ========================================================================
    loft_beam_front_pos_1 = beam_front_1.length - inches(9)
    loft_beam_front_pos_2 = beam_front_1.length + beam_front_2.length + inches(9)

    # mid_beam_back runs in opposite X direction (BR -> BL), so mirror positions
    loft_beam_back_pos_1 = mid_beam_back.length - loft_beam_front_pos_1
    loft_beam_back_pos_2 = mid_beam_back.length - loft_beam_front_pos_2

    loft_beam_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=mid_beam_front,
        timber2=mid_beam_back,
        location_on_timber1=loft_beam_front_pos_1,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Loft Beam FM1-BM"
    )
    loft_beam_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=mid_beam_front,
        timber2=mid_beam_back,
        location_on_timber1=loft_beam_front_pos_2,
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Loft Beam FM2-BM"
    )

    

    # ========================================================================
    # TOP PLATES at 11'
    #
    # First layer: front-to-back plates connecting FL->BL and FR->BR
    #   at 11' (top of corner posts), with 6" stickout
    #   4x6 with 6" in +Z
    #
    # Second layer: left-to-right plates connecting FL->FR and BL->BR
    #   3" above the first layer (i.e. at 11' + 5.5" + 3")
    #   sitting on TOP of the first layer plates
    # ========================================================================
    top_plate_size = beam_size


    # First layer: front-to-back (along Y axis), 6" stickout on both ends
    top_plate_stickout = Stickout.symmetric(inches(6))

    top_plate_left = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FL, timber2=post_BL,
        location_on_timber1=top_plate_height,
        stickout=top_plate_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=top_plate_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Top Plate Left (Front-to-Back)"
    )
    top_plate_right = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FR, timber2=post_BR,
        location_on_timber1=top_plate_height,
        stickout=top_plate_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=top_plate_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Top Plate Right (Front-to-Back)"
    )

    # Second layer: left-to-right (along X axis)
    # Sits on top of F/B plates with 3" overlap into the F/B plates.
    # F/B plate top = top_plate_height + 5.5"/2
    # L/R plate bottom = F/B plate top - 3"
    # L/R plate centerline = L/R plate bottom + 5.5"/2
    second_plate_centerline = (top_plate_height + top_plate_size[0] / Integer(2)) - inches(3) + top_plate_size[0] / Integer(2)

    top_plate_front = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FL, timber2=post_FR,
        location_on_timber1=second_plate_centerline,
        stickout=top_plate_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=top_plate_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Top Plate Front (Left-to-Right)"
    )
    top_plate_back = join_face_aligned_on_face_aligned_timbers(
        timber1=post_BL, timber2=post_BR,
        location_on_timber1=second_plate_centerline,
        stickout=top_plate_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=top_plate_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Top Plate Back (Left-to-Right)"
    )
    add_milestone('beams and plates')

    # ========================================================================
    # ========================================================================
    # LOWER WALL STUDS — vertical 4x4 posts via join_timbers
    # from bottom beam spans up to the mid-height perimeter beams.
    # ========================================================================
    lower_stud_front_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_front_1, timber2=mid_beam_front,
        location_on_timber1=beam_front_1.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.FRONT,
        ticket="Front Lower Stud 1"
    )
    lower_stud_front_3 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_front_3, timber2=mid_beam_front,
        location_on_timber1=beam_front_3.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.FRONT,
        ticket="Front Lower Stud 3"
    )

    # Window members in FM1-FM2 bay (replace middle lower stud)
    window_member_upper = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FM1, timber2=post_FM2,
        location_on_timber1=non_corner_post_height * Rational(4, 5),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Front Window Member Upper"
    )
    window_member_lower = join_face_aligned_on_face_aligned_timbers(
        timber1=post_FM1, timber2=post_FM2,
        location_on_timber1=non_corner_post_height * Rational(2, 5),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Front Window Member Lower"
    )

    lower_stud_right_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_right_1, timber2=mid_beam_right,
        location_on_timber1=beam_right_1.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.RIGHT,
        ticket="Right Lower Stud 1"
    )
    lower_stud_right_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_right_2, timber2=mid_beam_right,
        location_on_timber1=beam_right_2.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.RIGHT,
        ticket="Right Lower Stud 2"
    )

    lower_stud_back_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_back_1, timber2=mid_beam_back,
        location_on_timber1=beam_back_1.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.FRONT,
        ticket="Back Lower Stud 1"
    )
    lower_stud_back_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_back_2, timber2=mid_beam_back,
        location_on_timber1=beam_back_2.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.FRONT,
        ticket="Back Lower Stud 2"
    )
    lower_stud_back_3 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_back_3, timber2=mid_beam_back,
        location_on_timber1=beam_back_3.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.FRONT,
        ticket="Back Lower Stud 3"
    )

    lower_stud_left_1 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_left_1, timber2=mid_beam_left,
        location_on_timber1=beam_left_1.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.RIGHT,
        ticket="Left Lower Stud 1"
    )
    lower_stud_left_2 = join_face_aligned_on_face_aligned_timbers(
        timber1=beam_left_2, timber2=mid_beam_left,
        location_on_timber1=beam_left_2.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        orientation_face_on_timber1=TimberFace.RIGHT,
        ticket="Left Lower Stud 2"
    )

    # ========================================================================
    # UPPER WALL STUDS — vertical 4x4 posts between mid-height beams
    # and top plates, evenly spaced: 4 on F/B sides, 2 on L/R sides.
    #
    # Front/back top plate (second layer) centerline = second_plate_centerline
    # Left/right top plate (first layer) centerline = top_plate_height
    # ========================================================================

    def _lerp_xy(t1, t2, frac, z):
        """Linearly interpolate XY between two posts at fraction frac, at given Z."""
        p1 = t1.get_bottom_position_global()
        p2 = t2.get_bottom_position_global()
        return create_v3(
            p1[0] + (p2[0] - p1[0]) * frac,
            p1[1] + (p2[1] - p1[1]) * frac,
            z,
        )

    # Upper studs via join_timbers.

    upper_studs_front = []
    for i in range(1, 5):
        frac = Rational(i, 5)
        stud = join_face_aligned_on_face_aligned_timbers(
            timber1=mid_beam_front,
            timber2=top_plate_front,
            location_on_timber1=mid_beam_front.length * frac,
            stickout=no_stickout,
            lateral_offset_from_timber1=Integer(0),
            size=post_size,
            orientation_face_on_timber1=TimberFace.FRONT,
            ticket=f"Front Upper Stud {i}"
        )
        upper_studs_front.append(stud)

    upper_studs_back = []
    for i in range(1, 5):
        frac = Rational(i, 5)
        stud = join_face_aligned_on_face_aligned_timbers(
            timber1=mid_beam_back,
            timber2=top_plate_back,
            location_on_timber1=mid_beam_back.length * frac,
            stickout=no_stickout,
            lateral_offset_from_timber1=Integer(0),
            size=post_size,
            orientation_face_on_timber1=TimberFace.FRONT,
            ticket=f"Back Upper Stud {i}"
        )
        upper_studs_back.append(stud)

    upper_studs_right = []
    for i in range(1, 3):
        frac = Rational(i, 3)
        stud = join_face_aligned_on_face_aligned_timbers(
            timber1=mid_beam_right,
            timber2=top_plate_right,
            location_on_timber1=mid_beam_right.length * frac,
            stickout=no_stickout,
            lateral_offset_from_timber1=Integer(0),
            size=post_size,
            orientation_face_on_timber1=TimberFace.RIGHT,
            ticket=f"Right Upper Stud {i}"
        )
        upper_studs_right.append(stud)

    upper_studs_left = []
    for i in range(1, 3):
        frac = Rational(i, 3)
        stud = join_face_aligned_on_face_aligned_timbers(
            timber1=mid_beam_left,
            timber2=top_plate_left,
            location_on_timber1=mid_beam_left.length * frac,
            stickout=no_stickout,
            lateral_offset_from_timber1=Integer(0),
            size=post_size,
            orientation_face_on_timber1=TimberFace.RIGHT,
            ticket=f"Left Upper Stud {i}"
        )
        upper_studs_left.append(stud)

    # ========================================================================
    # KING POSTS — on the side (L/R) top plates at their midpoints,
    # supporting the ridge beam at the gable ends.
    # ========================================================================
    king_post_height = feet(Rational(5, 2))
    king_post_bottom_z = top_plate_height + beam_size[0] / Integer(2)  # top of side plates

    king_post_left = create_axis_aligned_timber(
        _lerp_xy(post_FL, post_BL, Rational(1, 2), king_post_bottom_z),
        king_post_height, post_size,
        TimberFace.TOP, ticket="Left King Post"
    )
    king_post_right = create_axis_aligned_timber(
        _lerp_xy(post_FR, post_BR, Rational(1, 2), king_post_bottom_z),
        king_post_height, post_size,
        TimberFace.TOP, ticket="Right King Post"
    )

    # ========================================================================
    # RIDGE BEAM — 16' 4x6 on top of king posts, running along X (the 15' dir)
    # centered on the house with ~6" overhang each side.
    # ========================================================================
    ridge_length = feet(16)
    ridge_bottom_z = king_post_bottom_z + king_post_height  # top of king posts
    ridge_center_x = center[0] + house_width / Integer(2)
    ridge_y = center[1] + house_depth / Integer(2)
    ridge_start_x = ridge_center_x - ridge_length / Integer(2)

    ridge_beam = create_axis_aligned_timber(
        create_v3(ridge_start_x, ridge_y, ridge_bottom_z),
        ridge_length, beam_size,
        TimberFace.RIGHT,  # extends in +X
        ticket="Ridge Beam"
    )

    # ========================================================================
    # CENTER RIDGE SUPPORT
    # - One beam between the midpoints of front/back top plates
    # - One vertical king post from that beam up to the ridge beam
    # ========================================================================
    top_plate_mid_x = top_plate_front.get_bottom_position_global()[0] + top_plate_front.length / Integer(2)
    center_support_beam = join_face_aligned_on_face_aligned_timbers(
        timber1=top_plate_front,
        timber2=top_plate_back,
        location_on_timber1=top_plate_front.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=beam_size,
        orientation_face_on_timber1=TimberFace.TOP,
        ticket="Center Ridge Support Beam"
    )

    center_king_post = join_face_aligned_on_face_aligned_timbers(
        timber1=center_support_beam,
        timber2=ridge_beam,
        location_on_timber1=center_support_beam.length / Integer(2),
        stickout=no_stickout,
        lateral_offset_from_timber1=Integer(0),
        size=post_size,
        ticket="Center King Post"
    )

    # ========================================================================
    # RAFTERS — 6 sets (12 rafters), evenly spaced along the ridge beam,
    # starting from the very edge. Each set has a front rafter and a back
    # rafter sloping from the ridge down to the F/B top plates.
    # Rafters are 4x4, intersecting ridge and plate by ~1".
    # ========================================================================
    rafter_size = post_size


    # Reference surfaces
    ridge_top_z = ridge_bottom_z + beam_size[0]          # top of ridge beam
    plate_top_z = second_plate_centerline + beam_size[0] / Integer(2)  # top of F/B plates

    # Rafter anchor Z: mostly above each member, with ~1" overlap into it.
    # Since rafter depth is 3.5", centerline should be at top + (3.5"/2 - 1")
    embed_depth = inches(1)
    rafter_vertical_half = rafter_size[0] / Integer(2)
    rafter_ridge_z = ridge_top_z + rafter_vertical_half - embed_depth
    rafter_plate_z = plate_top_z + rafter_vertical_half - embed_depth

    # Extend each rafter by 1' toward the eave side (past the plate),
    # not past the ridge side.
    extra_rafter_length = feet(1)

    # Y positions of front/back plates (from corner post centers)
    front_plate_y = post_FL.get_bottom_position_global()[1]
    back_plate_y = post_BL.get_bottom_position_global()[1]

    rafter_edge_inset = rafter_size[0] / Integer(2)
    usable_rafter_span_x = ridge_length - Integer(2) * rafter_edge_inset

    rafter_stickout = Stickout(extra_rafter_length, Integer(0))

    def _rafter_from_join(
        plate: PerfectTimberWithin,
        ridge: PerfectTimberWithin,
        x: Numeric,
        plate_y: Numeric,
        ticket: str,
    ) -> PerfectTimberWithin:
        plate_location = x - plate.get_bottom_position_global()[0]
        ridge_location = x - ridge.get_bottom_position_global()[0]

        target_plate_point = create_v3(x, plate_y, rafter_plate_z)
        target_ridge_point = create_v3(x, ridge_y, rafter_ridge_z)
        target_direction = normalize_vector(target_ridge_point - target_plate_point)
        target_bottom = target_plate_point - target_direction * extra_rafter_length

        plate_centerline_point = locate_position_on_centerline_from_bottom(plate, plate_location).position
        ridge_centerline_point = locate_position_on_centerline_from_bottom(ridge, ridge_location).position
        join_direction = normalize_vector(ridge_centerline_point - plate_centerline_point)
        offset_direction = normalize_vector(cross_product(plate.get_length_direction_global(), join_direction))
        base_bottom = plate_centerline_point - join_direction * extra_rafter_length
        lateral_offset = safe_dot_product(target_bottom - base_bottom, offset_direction)*1.5

        return join_timbers(
            timber1=plate,
            timber2=ridge,
            location_on_timber1=plate_location,
            location_on_timber2=ridge_location,
            lateral_offset=lateral_offset,
            stickout=rafter_stickout,
            size=rafter_size,
            orientation_width_vector=create_v3(Integer(1), Integer(0), Integer(0)),
            ticket=ticket,
        )

    rafters = []
    rafter_pairs: List[Tuple[PerfectTimberWithin, PerfectTimberWithin]] = []
    rafter_housing_pairs: List[Tuple[PerfectTimberWithin, PerfectTimberWithin]] = []
    for i in range(6):
        x = ridge_start_x + rafter_edge_inset + i * usable_rafter_span_x / Integer(5)

        front_rafter = _rafter_from_join(
            top_plate_front,
            ridge_beam,
            x,
            front_plate_y,
            f"Front Rafter {i + 1}",
        )
        rafters.append(front_rafter)
        rafter_housing_pairs.append((ridge_beam, front_rafter))
        rafter_housing_pairs.append((top_plate_front, front_rafter))

        back_rafter = _rafter_from_join(
            top_plate_back,
            ridge_beam,
            x,
            back_plate_y,
            f"Back Rafter {i + 1}",
        )
        rafters.append(back_rafter)
        rafter_housing_pairs.append((ridge_beam, back_rafter))
        rafter_housing_pairs.append((top_plate_back, back_rafter))

        rafter_pairs.append((front_rafter, back_rafter))

    add_milestone('roof structure')

    # ========================================================================
    # COLLECT ALL TIMBERS (no joints yet)
    # ========================================================================
    all_beams = [
        # Bottom perimeter
        beam_front_1, beam_front_2, beam_front_3,
        beam_right_1, beam_right_2,
        beam_back_1, beam_back_2, beam_back_3,
        beam_left_1, beam_left_2,
        # Floor joists
        *floor_joists,
        # Mid-height perimeter
        mid_beam_front, mid_beam_right, mid_beam_back, mid_beam_left,
        # Loft beams
        loft_beam_1, loft_beam_2,
        # Window members
        window_member_upper, window_member_lower,
        # Top plates
        top_plate_left, top_plate_right,
        top_plate_front, top_plate_back,
        # Center support
        center_support_beam,
        # Ridge
        ridge_beam,
    ]

    all_studs = [
        # Lower wall studs
        lower_stud_front_1, lower_stud_front_3,
        lower_stud_right_1, lower_stud_right_2,
        lower_stud_back_1, lower_stud_back_2, lower_stud_back_3,
        lower_stud_left_1, lower_stud_left_2,
        # Upper wall studs
        *upper_studs_front, *upper_studs_back,
        *upper_studs_right, *upper_studs_left,
        # King posts
        king_post_left, king_post_right,
        center_king_post,
    ]

    horizontal_member_peg_params = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(mm(25), Rational(0))],
        size=mm(15),
    )
    add_milestone('cutting joints')

    def _is_horizontal_timber(timber: PerfectTimberWithin) -> bool:
        return zero_test(
            safe_dot_product(
                timber.get_length_direction_global(),
                create_v3(Integer(0), Integer(0), Integer(1)),
            )
        )

    def _peg_front_face_for_joint(
        butt_timber: PerfectTimberWithin,
        receiving_timber: PerfectTimberWithin,
    ) -> TimberLongFace:
        receiving_length_direction = receiving_timber.get_length_direction_global()
        candidates = [
            (TimberLongFace.RIGHT, butt_timber.get_face_direction_global(TimberFace.RIGHT)),
            (TimberLongFace.LEFT, butt_timber.get_face_direction_global(TimberFace.LEFT)),
            (TimberLongFace.FRONT, butt_timber.get_face_direction_global(TimberFace.FRONT)),
            (TimberLongFace.BACK, butt_timber.get_face_direction_global(TimberFace.BACK)),
        ]
        return min(
            candidates,
            key=lambda candidate: abs(safe_dot_product(candidate[1], receiving_length_direction)),
        )[0]

    def _fat_joint(
        butt_timber: PerfectTimberWithin,
        receiving_timber: PerfectTimberWithin,
        butt_timber_end: TimberReferenceEnd,
        *,
        tenon_size: Optional[V2] = None,
        tenon_position: Optional[V2] = None,
        label: str,
    ) -> Joint:
        try:
            actual_tenon_size = stud_tenon_size if tenon_size is None else tenon_size
            if tenon_position is None:
                butt_candidate_face = butt_timber.get_outside_face_from_footprint(footprint)
                outward_dir = butt_timber.get_face_direction_global(butt_candidate_face)
                
                receiving_outside_face = receiving_timber.get_closest_oriented_face_from_global_direction(outward_dir)
                target_plane = locate_into_face(stud_tenon_outside_offset, receiving_outside_face, receiving_timber)
                
                receiving_outward_dir = receiving_timber.get_face_direction_global(receiving_outside_face)
                butt_outside_face = butt_timber.get_closest_oriented_face_from_global_direction(receiving_outward_dir)
                
                mark = mark_distance_from_face_in_normal_direction(target_plane, butt_timber, butt_outside_face)
                dist_into_butt = mark.distance
                
                idx = butt_timber.get_size_index_in_long_face_normal_axis(butt_outside_face.to.long_face())
                timber_half_size = butt_timber.get_size_in_face_normal_axis(butt_outside_face) / Integer(2)
                thickness = actual_tenon_size[idx]
                
                offset_toward_outside = timber_half_size - (dist_into_butt + thickness / Integer(2))
                
                butt_offset = [Integer(0), Integer(0)]
                if butt_outside_face.to.long_face() in [TimberLongFace.RIGHT, TimberLongFace.FRONT]:
                    butt_offset[idx] = offset_toward_outside
                else:
                    butt_offset[idx] = -offset_toward_outside
                    
                tenon_position = create_v2(butt_offset[0], butt_offset[1])

            peg_parameters = (
                horizontal_member_peg_params
                if _is_horizontal_timber(butt_timber)
                else None
            )
            return cut_mortise_and_tenon_joint_on_FAT(
                arrangement=ButtJointTimberArrangement(
                    butt_timber=butt_timber,
                    receiving_timber=receiving_timber,
                    butt_timber_end=butt_timber_end,
                    front_face_on_butt_timber=(
                        _peg_front_face_for_joint(butt_timber, receiving_timber)
                        if peg_parameters is not None
                        else None
                    ),
                ),
                tenon_size=actual_tenon_size,
                tenon_length=stud_tenon_depth,
                mortise_depth=stud_tenon_depth,
                mortise_shoulder_inset=inches(Rational(1, 64)),
                tenon_position=tenon_position,
                peg_parameters=peg_parameters,
            )
        except Exception as err:
            print(
                f"Error creating FAT joint label={label} butt_end={butt_timber_end} face_aligned={are_timbers_face_aligned(butt_timber, receiving_timber)} plane_aligned={are_timbers_plane_aligned(butt_timber, receiving_timber)}",
                file=sys.stderr,
                flush=True,
            )
            print(_describe_timber("butt_timber", butt_timber), file=sys.stderr, flush=True)
            print(_describe_timber("receiving_timber", receiving_timber), file=sys.stderr, flush=True)
            raise AssertionError(
                f"FAT joint failed for label='{label}' butt='{butt_timber.ticket.name}' receiving='{receiving_timber.ticket.name}' end='{butt_timber_end}': {err}"
            ) from err

    def _wall_stud_joint(stud: PerfectTimberWithin, beam: PerfectTimberWithin, stud_end: TimberReferenceEnd) -> Joint:
        return _fat_joint(stud, beam, stud_end, label="wall_stud")

    wall_stud_joints: List[Joint] = []

    lower_stud_to_beams = [
        (lower_stud_front_1, beam_front_1, mid_beam_front, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_front_3, beam_front_3, mid_beam_front, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_right_1, beam_right_1, mid_beam_right, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_right_2, beam_right_2, mid_beam_right, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_back_1, beam_back_1, mid_beam_back, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_back_2, beam_back_2, mid_beam_back, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_back_3, beam_back_3, mid_beam_back, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_left_1, beam_left_1, mid_beam_left, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
        (lower_stud_left_2, beam_left_2, mid_beam_left, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP),
    ]

    for stud, bottom_beam, top_beam, bottom_end, top_end in lower_stud_to_beams:
        wall_stud_joints.append(_wall_stud_joint(stud, bottom_beam, bottom_end))
        wall_stud_joints.append(_wall_stud_joint(stud, top_beam, top_end))

    for stud in upper_studs_front:
        wall_stud_joints.append(_wall_stud_joint(stud, mid_beam_front, TimberReferenceEnd.BOTTOM))
        wall_stud_joints.append(_wall_stud_joint(stud, top_plate_front, TimberReferenceEnd.TOP))

    for stud in upper_studs_back:
        wall_stud_joints.append(_wall_stud_joint(stud, mid_beam_back, TimberReferenceEnd.BOTTOM))
        wall_stud_joints.append(_wall_stud_joint(stud, top_plate_back, TimberReferenceEnd.TOP))

    for stud in upper_studs_right:
        wall_stud_joints.append(_wall_stud_joint(stud, mid_beam_right, TimberReferenceEnd.BOTTOM))
        wall_stud_joints.append(_wall_stud_joint(stud, top_plate_right, TimberReferenceEnd.TOP))

    for stud in upper_studs_left:
        wall_stud_joints.append(_wall_stud_joint(stud, mid_beam_left, TimberReferenceEnd.BOTTOM))
        wall_stud_joints.append(_wall_stud_joint(stud, top_plate_left, TimberReferenceEnd.TOP))
    add_milestone('wall stud joints')

    def _tenon_size_with_long_axis(stud: PerfectTimberWithin, long_axis_global: V3) -> V2:
        stud_right = stud.get_face_direction_global(TimberFace.RIGHT)
        stud_front = stud.get_face_direction_global(TimberFace.FRONT)
        right_alignment = abs(safe_dot_product(stud_right, long_axis_global))
        front_alignment = abs(safe_dot_product(stud_front, long_axis_global))

        if right_alignment > front_alignment:
            return create_v2(stud_tenon_size[1], stud_tenon_size[0])
        return create_v2(stud_tenon_size[0], stud_tenon_size[1])

    def _fat_joint_aligned_to_receiver(
        butt_timber: PerfectTimberWithin,
        receiving_timber: PerfectTimberWithin,
        butt_timber_end: TimberReferenceEnd,
        *,
        label: str,
    ) -> Joint:
        return _fat_joint(
            butt_timber,
            receiving_timber,
            butt_timber_end,
            tenon_size=_tenon_size_with_long_axis(
                butt_timber,
                receiving_timber.get_length_direction_global(),
            ),
            label=label,
        )

    def _beam_corner_post_tenon_position(beam: PerfectTimberWithin) -> V2:
        tenon_size = _tenon_size_with_long_axis(
            beam,
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        centered_in_top_band = beam.size[0] / Integer(2) - tenon_size[0] / Integer(2)

        beam_length_direction = beam.get_length_direction_global()
        front_back_alignment = abs(safe_dot_product(beam_length_direction, create_v3(Integer(0), Integer(1), Integer(0))))
        left_right_alignment = abs(safe_dot_product(beam_length_direction, create_v3(Integer(1), Integer(0), Integer(0))))

        if front_back_alignment > left_right_alignment:
            return create_v2(centered_in_top_band, Integer(0))

        return create_v2(centered_in_top_band - tenon_size[0], Integer(0))

    def _beam_to_corner_post_joint(
        beam: PerfectTimberWithin,
        post: PerfectTimberWithin,
        beam_end: TimberReferenceEnd,
    ) -> Joint:
        return _fat_joint(
            beam,
            post,
            beam_end,
            tenon_size=_tenon_size_with_long_axis(
                beam,
                post.get_length_direction_global(),
            ),
            tenon_position=_beam_corner_post_tenon_position(beam),
            label="mid_beam_to_corner_post",
        )

    intermediate_post_joints: List[Joint] = []
    for post, beam in [
        (post_FM1, mid_beam_front),
        (post_FM2, mid_beam_front),
        (post_MR, mid_beam_right),
        (post_BM1, mid_beam_back),
        (post_BM2, mid_beam_back),
        (post_ML, mid_beam_left),
    ]:
        intermediate_post_joints.append(
            _fat_joint_aligned_to_receiver(post, beam, TimberReferenceEnd.TOP, label="intermediate_post_to_mid_beam")
        )

    mid_beam_corner_post_joints: List[Joint] = []
    for beam, start_post, end_post in [
        (mid_beam_front, post_FL, post_FR),
        (mid_beam_right, post_FR, post_BR),
        (mid_beam_back, post_BR, post_BL),
        (mid_beam_left, post_BL, post_FL),
    ]:
        mid_beam_corner_post_joints.append(
            _beam_to_corner_post_joint(beam, start_post, TimberReferenceEnd.BOTTOM)
        )
        mid_beam_corner_post_joints.append(
            _beam_to_corner_post_joint(beam, end_post, TimberReferenceEnd.TOP)
        )

    bottom_beam_corner_post_joints: List[Joint] = []
    # FAT joints for corner posts
    for beam, post, beam_end in [
        (beam_front_1, post_FL, TimberReferenceEnd.BOTTOM),
        (beam_front_3, post_FR, TimberReferenceEnd.TOP),
        (beam_right_1, post_FR, TimberReferenceEnd.BOTTOM),
        (beam_right_2, post_BR, TimberReferenceEnd.TOP),
        (beam_back_1, post_BR, TimberReferenceEnd.BOTTOM),
        (beam_back_3, post_BL, TimberReferenceEnd.TOP),
        (beam_left_1, post_BL, TimberReferenceEnd.BOTTOM),
        (beam_left_2, post_FL, TimberReferenceEnd.TOP),
    ]:
        bottom_beam_corner_post_joints.append(
            _beam_to_corner_post_joint(beam, post, beam_end)
        )
        
    
    # Splined double butt joints for intermediate posts (antiparallel beams)
    for beam1, beam1_end, beam2, beam2_end, post in [
        (beam_front_1, TimberReferenceEnd.TOP, beam_front_2, TimberReferenceEnd.BOTTOM, post_FM1),
        (beam_front_2, TimberReferenceEnd.TOP, beam_front_3, TimberReferenceEnd.BOTTOM, post_FM2),
        (beam_back_1, TimberReferenceEnd.TOP, beam_back_2, TimberReferenceEnd.BOTTOM, post_BM1),
        (beam_back_2, TimberReferenceEnd.TOP, beam_back_3, TimberReferenceEnd.BOTTOM, post_BM2),
        (beam_right_1, TimberReferenceEnd.TOP, beam_right_2, TimberReferenceEnd.BOTTOM, post_MR),
        (beam_left_1, TimberReferenceEnd.TOP, beam_left_2, TimberReferenceEnd.BOTTOM, post_ML),
    ]:
        bottom_beam_corner_post_joints.append(
            cut_basic_splined_opposing_double_butt_joint(
                arrangement=DoubleButtJointTimberArrangement(
                    butt_timber_1=beam1,
                    butt_timber_2=beam2,
                    receiving_timber=post,
                    butt_timber_1_end=beam1_end,
                    butt_timber_2_end=beam2_end,
                ),
                slot_facing_end_on_receiving_timber=TimberReferenceEnd.BOTTOM,
            )
        )

    window_member_joints: List[Joint] = []
    for window_member in [window_member_upper, window_member_lower]:
        window_member_joints.append(
            _fat_joint_aligned_to_receiver(window_member, post_FM1, TimberReferenceEnd.BOTTOM, label="window_member_to_post")
        )
        window_member_joints.append(
            _fat_joint_aligned_to_receiver(window_member, post_FM2, TimberReferenceEnd.TOP, label="window_member_to_post")
        )

    corner_post_to_side_plate_tenon_size = create_v2(inches(Rational(3, 2)), inches(3))
    corner_post_to_side_plate_tenon_length = inches(Rational(9, 2))
    corner_post_to_side_plate_mortise_depth = inches(Rational(9, 2))

    corner_post_to_cross_plate_tenon_size = create_v2(inches(Rational(3, 2)), inches(1))
    corner_post_to_cross_plate_tenon_length = inches(Rational(5, 2))
    corner_post_to_cross_plate_mortise_depth = inches(Rational(5, 2))

    corner_top_plate_compound_joints: List[Joint] = []

    for post, side_plate in [
        (post_FL, top_plate_left),
        (post_FR, top_plate_right),
        (post_BL, top_plate_left),
        (post_BR, top_plate_right),
    ]:
        corner_top_plate_compound_joints.append(
            cut_mortise_and_tenon_joint_on_FAT(
                arrangement=ButtJointTimberArrangement(
                    receiving_timber=side_plate,
                    butt_timber=post,
                    butt_timber_end=TimberReferenceEnd.TOP,
                    front_face_on_butt_timber=None,
                ),
                tenon_size=corner_post_to_side_plate_tenon_size,
                tenon_length=corner_post_to_side_plate_tenon_length,
                mortise_depth=corner_post_to_side_plate_mortise_depth,
            )
        )

    for post, cross_plate in [
        (post_FL, top_plate_front),
        (post_FR, top_plate_front),
        (post_BL, top_plate_back),
        (post_BR, top_plate_back),
    ]:
        corner_top_plate_compound_joints.append(
            cut_mortise_and_tenon_joint_on_FAT(
                arrangement=ButtJointTimberArrangement(
                    receiving_timber=cross_plate,
                    butt_timber=post,
                    butt_timber_end=TimberReferenceEnd.TOP,
                    front_face_on_butt_timber=None,
                ),
                tenon_size=corner_post_to_cross_plate_tenon_size,
                tenon_length=corner_post_to_cross_plate_tenon_length,
                mortise_depth=corner_post_to_cross_plate_mortise_depth,
            )
        )

    for side_plate, cross_plate in [
        (top_plate_left, top_plate_front),
        (top_plate_right, top_plate_front),
        (top_plate_left, top_plate_back),
        (top_plate_right, top_plate_back),
    ]:
        corner_top_plate_compound_joints.append(
            cut_plain_house_joint(
                CrossJointTimberArrangement(
                    timber1=side_plate,
                    timber2=cross_plate,
                )
            )
        )

    def _king_post_joint(
        stud: PerfectTimberWithin,
        beam: PerfectTimberWithin,
        stud_end: TimberReferenceEnd,
        long_axis_global: V3,
    ) -> Joint:
        try:
            return cut_mortise_and_tenon_joint_on_FAT(
                arrangement=ButtJointTimberArrangement(
                    butt_timber=stud,
                    receiving_timber=beam,
                    butt_timber_end=stud_end,
                ),
                tenon_size=_tenon_size_with_long_axis(stud, long_axis_global),
                tenon_length=stud_tenon_depth,
                mortise_depth=stud_tenon_depth,
                mortise_shoulder_inset=inches(Rational(1, 64)),
                peg_parameters=None,
            )
        except Exception as err:
            print(
                f"Error creating king-post FAT joint stud_end={stud_end} face_aligned={are_timbers_face_aligned(stud, beam)} plane_aligned={are_timbers_plane_aligned(stud, beam)}",
                file=sys.stderr,
                flush=True,
            )
            print(_describe_timber("stud", stud), file=sys.stderr, flush=True)
            print(_describe_timber("beam", beam), file=sys.stderr, flush=True)
            raise AssertionError(
                f"FAT king-post joint failed for stud='{stud.ticket.name}' beam='{beam.ticket.name}' end='{stud_end}': {err}"
            ) from err

    front_back_axis = create_v3(Integer(0), Integer(1), Integer(0))
    left_right_axis = create_v3(Integer(1), Integer(0), Integer(0))

    king_post_joints: List[Joint] = [
        # Bottom tenons: long side front-to-back.
        _king_post_joint(king_post_left, top_plate_left, TimberReferenceEnd.BOTTOM, front_back_axis),
        _king_post_joint(king_post_right, top_plate_right, TimberReferenceEnd.BOTTOM, front_back_axis),
        _king_post_joint(center_king_post, center_support_beam, TimberReferenceEnd.BOTTOM, front_back_axis),
        # Top tenons: long side left-to-right.
        _king_post_joint(king_post_left, ridge_beam, TimberReferenceEnd.TOP, left_right_axis),
        _king_post_joint(king_post_right, ridge_beam, TimberReferenceEnd.TOP, left_right_axis),
        _king_post_joint(center_king_post, ridge_beam, TimberReferenceEnd.TOP, left_right_axis),
    ]

    floor_joist_dovetail_shoulder_inset = inches(0)
    floor_joist_dovetail_small_width = inches(2)
    floor_joist_dovetail_large_width = inches(Rational(5, 2))
    floor_joist_dovetail_length = inches(Rational(3, 2))
    floor_joist_dovetail_depth = inches(2)
    

    floor_joist_intermediate_post_tenon_size = create_v2(inches(Rational(11, 4)), inches(1))
    floor_joist_intermediate_post_tenon_position = create_v2(
        floor_joist_4.size[0] / Integer(2) - floor_joist_intermediate_post_tenon_size[0] / Integer(2),
        Integer(0),
    )

    floor_joist_receivers = [
        (floor_joist_1, beam_front_1, beam_back_3),
        (floor_joist_2, beam_front_2, beam_back_2),
        (floor_joist_3, beam_front_3, beam_back_1),
    ]
    floor_joist_dovetail_joints: List[Joint] = []

    for joist, front_receiver, back_receiver in floor_joist_receivers:
        floor_joist_dovetail_joints.append(
            cut_housed_dovetail_butt_joint(
                arrangement=ButtJointTimberArrangement(
                    butt_timber=joist,
                    receiving_timber=front_receiver,
                    butt_timber_end=TimberReferenceEnd.BOTTOM,
                    front_face_on_butt_timber=TimberLongFace.RIGHT,
                ),
                receiving_timber_shoulder_inset=floor_joist_dovetail_shoulder_inset,
                dovetail_length=floor_joist_dovetail_length,
                dovetail_small_width=floor_joist_dovetail_small_width,
                dovetail_large_width=floor_joist_dovetail_large_width,
                dovetail_lateral_offset=Rational(0),
                dovetail_depth=floor_joist_dovetail_depth,
            )
        )
        floor_joist_dovetail_joints.append(
            cut_housed_dovetail_butt_joint(
                arrangement=ButtJointTimberArrangement(
                    butt_timber=joist,
                    receiving_timber=back_receiver,
                    butt_timber_end=TimberReferenceEnd.TOP,
                    front_face_on_butt_timber=TimberLongFace.RIGHT,
                ),
                receiving_timber_shoulder_inset=floor_joist_dovetail_shoulder_inset,
                dovetail_length=floor_joist_dovetail_length,
                dovetail_small_width=floor_joist_dovetail_small_width,
                dovetail_large_width=floor_joist_dovetail_large_width,
                dovetail_lateral_offset=Rational(0),
                dovetail_depth=floor_joist_dovetail_depth,
            )
        )

    floor_joist_intermediate_post_joints: List[Joint] = []
    for joist, front_post, back_post in [
        (floor_joist_4, post_FM1, post_BM2),
        (floor_joist_5, post_FM2, post_BM1),
    ]:
        floor_joist_intermediate_post_joints.append(
            _fat_joint(
                joist,
                front_post,
                TimberReferenceEnd.BOTTOM,
                tenon_size=floor_joist_intermediate_post_tenon_size,
                tenon_position=floor_joist_intermediate_post_tenon_position,
                label="floor_joist_to_intermediate_post",
            )
        )
        floor_joist_intermediate_post_joints.append(
            _fat_joint(
                joist,
                back_post,
                TimberReferenceEnd.TOP,
                tenon_size=floor_joist_intermediate_post_tenon_size,
                tenon_position=floor_joist_intermediate_post_tenon_position,
                label="floor_joist_to_intermediate_post",
            )
        )

    loft_beam_receivers = [
        (loft_beam_1, mid_beam_front, mid_beam_back),
        (loft_beam_2, mid_beam_front, mid_beam_back),
    ]
    loft_beam_dovetail_joints: List[Joint] = []

    for loft_beam, front_receiver, back_receiver in loft_beam_receivers:
        loft_beam_dovetail_joints.append(
            cut_housed_dovetail_butt_joint(
                arrangement=ButtJointTimberArrangement(
                    butt_timber=loft_beam,
                    receiving_timber=front_receiver,
                    butt_timber_end=TimberReferenceEnd.BOTTOM,
                    front_face_on_butt_timber=TimberLongFace.RIGHT,
                ),
                receiving_timber_shoulder_inset=floor_joist_dovetail_shoulder_inset,
                dovetail_length=floor_joist_dovetail_length,
                dovetail_small_width=floor_joist_dovetail_small_width,
                dovetail_large_width=floor_joist_dovetail_large_width,
                dovetail_lateral_offset=Rational(0),
                dovetail_depth=floor_joist_dovetail_depth,
            )
        )
        loft_beam_dovetail_joints.append(
            cut_housed_dovetail_butt_joint(
                arrangement=ButtJointTimberArrangement(
                    butt_timber=loft_beam,
                    receiving_timber=back_receiver,
                    butt_timber_end=TimberReferenceEnd.TOP,
                    front_face_on_butt_timber=TimberLongFace.RIGHT,
                ),
                receiving_timber_shoulder_inset=floor_joist_dovetail_shoulder_inset,
                dovetail_length=floor_joist_dovetail_length,
                dovetail_small_width=floor_joist_dovetail_small_width,
                dovetail_large_width=floor_joist_dovetail_large_width,
                dovetail_lateral_offset=Rational(0),
                dovetail_depth=floor_joist_dovetail_depth,
            )
        )

    center_support_beam_dovetail_joints: List[Joint] = [
        cut_housed_dovetail_butt_joint(
            arrangement=ButtJointTimberArrangement(
                butt_timber=center_support_beam,
                receiving_timber=top_plate_front,
                butt_timber_end=TimberReferenceEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
            receiving_timber_shoulder_inset=floor_joist_dovetail_shoulder_inset,
            dovetail_length=floor_joist_dovetail_length,
            dovetail_small_width=floor_joist_dovetail_small_width,
            dovetail_large_width=floor_joist_dovetail_large_width,
            dovetail_lateral_offset=Rational(0),
            dovetail_depth=floor_joist_dovetail_depth,
        ),
        cut_housed_dovetail_butt_joint(
            arrangement=ButtJointTimberArrangement(
                butt_timber=center_support_beam,
                receiving_timber=top_plate_back,
                butt_timber_end=TimberReferenceEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
            receiving_timber_shoulder_inset=floor_joist_dovetail_shoulder_inset,
            dovetail_length=floor_joist_dovetail_length,
            dovetail_small_width=floor_joist_dovetail_small_width,
            dovetail_large_width=floor_joist_dovetail_large_width,
            dovetail_lateral_offset=Rational(0),
            dovetail_depth=floor_joist_dovetail_depth,
        ),
    ]

    rafter_house_joints: List[Joint] = []
    for housing_timber, housed_timber in rafter_housing_pairs:
        rafter_house_joints.append(
            cut_plain_house_joint(
                CrossJointTimberArrangement(
                    timber1=housing_timber,
                    timber2=housed_timber,
                )
            )
        )

    rafter_pair_joints: List[Joint] = []
    for front_rafter, back_rafter in rafter_pairs:
        rafter_pair_joints.append(
            cut_tongue_and_fork_corner_joint(
                CornerJointTimberArrangement(
                    timber1=front_rafter,
                    timber2=back_rafter,
                    timber1_end=TimberReferenceEnd.TOP,
                    timber2_end=TimberReferenceEnd.TOP,
                )
            )
        )
    add_milestone('all joints done')

    all_timbers = all_posts + all_beams + all_studs + rafters

    jointed_timber_ids = {
        id(cut_timber.timber)
        for joint in (
            wall_stud_joints
            + intermediate_post_joints
            + mid_beam_corner_post_joints
            + bottom_beam_corner_post_joints
            + window_member_joints
            + corner_top_plate_compound_joints
            + king_post_joints
            + floor_joist_dovetail_joints
            + floor_joist_intermediate_post_joints
            + loft_beam_dovetail_joints
            + center_support_beam_dovetail_joints
            + rafter_house_joints
            + rafter_pair_joints
        )
        for cut_timber in joint.cut_timbers.values()
    }

    unjointed_timbers = [
        timber for timber in all_timbers
        if id(timber) not in jointed_timber_ids
    ]

    add_milestone('assembling frame')
    return Frame.from_joints(
        joints=(
            wall_stud_joints
            + intermediate_post_joints
            + mid_beam_corner_post_joints
            + bottom_beam_corner_post_joints
            + window_member_joints
            + corner_top_plate_compound_joints
            + king_post_joints
            + floor_joist_dovetail_joints
            + floor_joist_intermediate_post_joints
            + loft_beam_dovetail_joints
            + center_support_beam_dovetail_joints
            + rafter_house_joints
            + rafter_pair_joints
        ),
        additional_unjointed_timbers=unjointed_timbers,
        name="Tiny House 120"
    )
