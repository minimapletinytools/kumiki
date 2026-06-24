from sympy import Rational
from kumiki import *


# Footprint: 3' wide (X) x 4' deep (Y)
base_width = feet(3)
base_depth = feet(4)

# 4x4 post: nominal 4x4, actual 3.5" x 3.5"
post_size = create_v2(inches(Rational(7, 2)), inches(Rational(7, 2)))
post_height = feet(8)

# 4x6 member: actual 3.5" x 5.5", 5.5" in vertical axis
# size[0] = 5.5" (vertical/Z), size[1] = 3.5" (horizontal/depth)
member_size = create_v2(inches(Rational(11, 2)), inches(Rational(7, 2)))
beam_floor_gap = inches(3)  # gap from floor to bottom of beam
beam_center_height = beam_floor_gap + member_size[0] / 2  # 3" + 2.75" = 5.75" from floor

# Top plates: front sits at post top, back is 3" lower for a slanted roof
plate_stickout = Stickout.symmetric(inches(3))
top_plate_front_height = post_height              # centered at top of post
top_plate_back_height = post_height - inches(3)   # 3" lower for roof slope

# Side girts: 1" below the bottom face of the back top plate so they clear it
# bottom of back plate = top_plate_back_height - member_size[0]/2
# top of side girt    = bottom of back plate - 1"
# center of side girt = top of side girt - member_size[0]/2
side_girt_height = top_plate_back_height - member_size[0] - inches(1)


def example() -> Frame:
    footprint_corners = [
        create_v2(Rational(0), Rational(0)),    # Corner 0: front-left
        create_v2(base_width, Rational(0)),      # Corner 1: front-right
        create_v2(base_width, base_depth),       # Corner 2: back-right
        create_v2(Rational(0), base_depth),      # Corner 3: back-left
    ]
    footprint = Footprint(footprint_corners)

    post_front_left = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=0, length=post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Front Left Post",
    )
    post_front_right = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=1, length=post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Front Right Post",
    )
    post_back_right = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=2, length=post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Back Right Post",
    )
    post_back_left = create_vertical_timber_on_footprint_corner(
        footprint, corner_index=3, length=post_height,
        location_type=FootprintLocation.INSIDE, size=post_size,
        ticket="Back Left Post",
    )

    # Floor beams span center-to-center between posts at beam_center_height.
    # join_timbers defaults to using the post's length direction (Z) as the
    # width reference, so size[0]=5.5" naturally lands on the vertical axis.
    beam_front = join_timbers(
        timber1=post_front_left, timber2=post_front_right,
        location_on_timber1=beam_center_height,
        location_on_timber2=beam_center_height,
        size=member_size,
        ticket="Front Floor Beam",
    )
    beam_back = join_timbers(
        timber1=post_back_left, timber2=post_back_right,
        location_on_timber1=beam_center_height,
        location_on_timber2=beam_center_height,
        size=member_size,
        ticket="Back Floor Beam",
    )
    beam_left = join_timbers(
        timber1=post_front_left, timber2=post_back_left,
        location_on_timber1=beam_center_height,
        location_on_timber2=beam_center_height,
        size=member_size,
        ticket="Left Floor Beam",
    )
    beam_right = join_timbers(
        timber1=post_front_right, timber2=post_back_right,
        location_on_timber1=beam_center_height,
        location_on_timber2=beam_center_height,
        size=member_size,
        ticket="Right Floor Beam",
    )

    # Top plates sit at the top of the posts with 3" stickout on each side.
    # The back plate is 3" lower than the front to create a slanted roof pitch.
    top_plate_front = join_timbers(
        timber1=post_front_left, timber2=post_front_right,
        location_on_timber1=top_plate_front_height,
        location_on_timber2=top_plate_front_height,
        stickout=plate_stickout,
        size=member_size,
        ticket="Front Top Plate",
    )
    top_plate_back = join_timbers(
        timber1=post_back_left, timber2=post_back_right,
        location_on_timber1=top_plate_back_height,
        location_on_timber2=top_plate_back_height,
        stickout=plate_stickout,
        size=member_size,
        ticket="Back Top Plate",
    )

    # Side girts connect the 3' sides (left and right walls), sitting 1" below
    # the bottom face of the back top plate so they clear it with no intersection.
    side_girt_left = join_timbers(
        timber1=post_front_left, timber2=post_back_left,
        location_on_timber1=side_girt_height,
        location_on_timber2=side_girt_height,
        size=member_size,
        ticket="Left Side Girt",
    )
    side_girt_right = join_timbers(
        timber1=post_front_right, timber2=post_back_right,
        location_on_timber1=side_girt_height,
        location_on_timber2=side_girt_height,
        size=member_size,
        ticket="Right Side Girt",
    )

    # ── All mortise-and-tenon joints ──────────────────────────────────────────
    # Uniform spec across the whole structure:
    #   tenon  2" in Z × 1" in horizontal depth  (tenon_size[0] = Z for all horizontal members)
    #   peg    5/8" square, 1" from shoulder, draw-bore offset 1/16"
    joint_tenon_size    = Matrix([inches(2), inches(1)])
    joint_tenon_length  = inches(2)
    joint_mortise_depth = inches(Rational(5, 2))

    peg_params = SimplePegParameters(
        shape=PegShape.SQUARE,
        peg_positions=[(inches(1), Rational(0))],  # 1" from shoulder, centered
        size=inches(Rational(5, 8)),                # 5/8" square
        depth=None,                                 # through peg
        tenon_hole_offset=inches(Rational(1, 16)),  # draw-bore
    )

    # Tenon position from bottom of beam (floor beams only):
    #   beam half-height = 2.75", tenon half-height = 1"
    #   default center = -1.75" (-7/4") from beam centerline
    #   offset  center = +0.25" (+1/4") – prevents adjacent tenons from crossing inside the post
    tenon_pos_default = Matrix([inches(Rational(-7, 4)), Rational(0)])
    tenon_pos_offset  = Matrix([inches(Rational( 1, 4)), Rational(0)])

    def fat_joint(receiving, butt, end, face, tenon_pos=None):
        return cut_mortise_and_tenon_joint_on_FAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=receiving,
                butt_timber=butt,
                butt_timber_end=end,
                front_face_on_butt_timber=face,
            ),
            tenon_size=joint_tenon_size,
            tenon_length=joint_tenon_length,
            mortise_depth=joint_mortise_depth,
            tenon_position=tenon_pos,
            peg_parameters=peg_params,
        )

    # Floor beams → posts
    # FRONT on each beam maps to a horizontal axis perpendicular to its span:
    #   beam_front / beam_back (span +X): FRONT = global −Y  (peg front-to-back)
    #   beam_left  / beam_right (span +Y): FRONT = global +X  (peg side-to-side)
    j_front_fl = fat_joint(post_front_left,  beam_front, TimberReferenceEnd.BOTTOM, TimberLongFace.FRONT, tenon_pos_default)
    j_front_fr = fat_joint(post_front_right, beam_front, TimberReferenceEnd.TOP,    TimberLongFace.FRONT, tenon_pos_default)
    j_back_bl  = fat_joint(post_back_left,   beam_back,  TimberReferenceEnd.BOTTOM, TimberLongFace.BACK, tenon_pos_default)
    j_back_br  = fat_joint(post_back_right,  beam_back,  TimberReferenceEnd.TOP,    TimberLongFace.BACK, tenon_pos_default)
    j_left_fl  = fat_joint(post_front_left,  beam_left,  TimberReferenceEnd.BOTTOM, TimberLongFace.BACK, tenon_pos_offset)
    j_left_bl  = fat_joint(post_back_left,   beam_left,  TimberReferenceEnd.TOP,    TimberLongFace.BACK, tenon_pos_offset)
    j_right_fr = fat_joint(post_front_right, beam_right, TimberReferenceEnd.BOTTOM, TimberLongFace.FRONT, tenon_pos_offset)
    j_right_br = fat_joint(post_back_right,  beam_right, TimberReferenceEnd.TOP,    TimberLongFace.FRONT, tenon_pos_offset)

    # Side girts → posts  (FRONT = global +X, peg across the wall)
    j_sg_left_fl  = fat_joint(post_front_left,  side_girt_left,  TimberReferenceEnd.BOTTOM, TimberLongFace.FRONT)
    j_sg_left_bl  = fat_joint(post_back_left,   side_girt_left,  TimberReferenceEnd.TOP,    TimberLongFace.FRONT)
    j_sg_right_fr = fat_joint(post_front_right, side_girt_right, TimberReferenceEnd.BOTTOM, TimberLongFace.FRONT)
    j_sg_right_br = fat_joint(post_back_right,  side_girt_right, TimberReferenceEnd.TOP,    TimberLongFace.FRONT)

    # Top plates ← posts  (post tenon goes up; face chosen so peg drills in global +Y)
    #   post_fl.FRONT = +Y, post_fr.RIGHT = +Y, post_bl.LEFT = +Y, post_br.BACK = +Y
    j_tp_front_fl = fat_joint(top_plate_front, post_front_left,  TimberReferenceEnd.TOP, TimberLongFace.FRONT)
    j_tp_front_fr = fat_joint(top_plate_front, post_front_right, TimberReferenceEnd.TOP, TimberLongFace.RIGHT)
    j_tp_back_bl  = fat_joint(top_plate_back,  post_back_left,   TimberReferenceEnd.TOP, TimberLongFace.LEFT)
    j_tp_back_br  = fat_joint(top_plate_back,  post_back_right,  TimberReferenceEnd.TOP, TimberLongFace.BACK)

    all_joints = [
        j_front_fl, j_front_fr, j_back_bl,  j_back_br,
        j_left_fl,  j_left_bl,  j_right_fr, j_right_br,
        j_sg_left_fl, j_sg_left_bl, j_sg_right_fr, j_sg_right_br,
        j_tp_front_fl, j_tp_front_fr, j_tp_back_bl, j_tp_back_br,
    ]

    # ── Door: 4 pieces of 1×4 (actual 3/4" × 3.5") ───────────────────────────
    # The door sits 1" inset from the outer face of the structure (Y=0 plane).
    # All 4 pieces share the same size vector; for vertical pieces size[0]=3.5"
    # runs in X, for horizontal rails size[0]=3.5" runs in Z (join_timbers picks
    # up left_vert's length direction +Z as the rail's width direction).
    door_stock = create_v2(inches(Rational(7, 2)), inches(Rational(3, 4)))  # 3.5" wide, 3/4" thick
    door_y = inches(1) + inches(Rational(3, 4)) / 2                         # center: 1" inset + 3/8"

    beam_top_z  = beam_floor_gap + member_size[0]               # top of front floor beam = 8.5"
    plate_bot_z = top_plate_front_height - member_size[0] / 2   # bottom of front top plate = 93.25"

    # Left vertical: floor-beam top → top-plate bottom, 1/2" gap from left post's inner face
    left_vert_x = post_size[0] + inches(Rational(1, 2)) + door_stock[0] / 2  # 3.5 + 0.5 + 1.75 = 5.75"
    door_left_vert = create_axis_aligned_timber(
        bottom_position=create_v3(left_vert_x, door_y, beam_top_z),
        length=plate_bot_z - beam_top_z,
        size=door_stock,
        length_direction=TimberFace.TOP,
        width_direction=TimberFace.RIGHT,
        ticket="Door Left Vertical",
    )

    # Right vertical: starts 2" above the floor beam, 58" long,
    # 1/2" gap from the right post's inner face (symmetric placement)
    right_vert_x     = base_width - post_size[0] - inches(Rational(1, 2)) - door_stock[0] / 2
    right_vert_bot_z = beam_top_z + inches(2)
    right_vert_len   = inches(58)
    door_right_vert = create_axis_aligned_timber(
        bottom_position=create_v3(right_vert_x, door_y, right_vert_bot_z),
        length=right_vert_len,
        size=door_stock,
        length_direction=TimberFace.TOP,
        width_direction=TimberFace.RIGHT,
        ticket="Door Right Vertical",
    )

    # Horizontal rails connect the ends of the right vertical to the left vertical.
    # Rail center in Z = bottom/top end of right piece ± half rail height (1.75").
    rail_bot_z = right_vert_bot_z + door_stock[0] / 2                # 10.5 + 1.75 = 12.25"
    rail_top_z = right_vert_bot_z + right_vert_len - door_stock[0] / 2  # 68.5 - 1.75 = 66.75"

    door_rail_bot = join_timbers(
        timber1=door_left_vert, timber2=door_right_vert,
        location_on_timber1=rail_bot_z - beam_top_z,       # 3.75" from left vert bottom
        location_on_timber2=rail_bot_z - right_vert_bot_z, # 1.75" from right vert bottom
        size=door_stock,
        ticket="Door Bottom Rail",
    )
    door_rail_top = join_timbers(
        timber1=door_left_vert, timber2=door_right_vert,
        location_on_timber1=rail_top_z - beam_top_z,       # 58.25" from left vert bottom
        location_on_timber2=rail_top_z - right_vert_bot_z, # 56.25" from right vert bottom
        size=door_stock,
        ticket="Door Top Rail",
    )

    door_pieces = [door_left_vert, door_right_vert, door_rail_bot, door_rail_top]

    return Frame.from_joints(all_joints, name="Oscar's Outdoor Shower",
                             additional_unjointed_timbers=door_pieces)


if __name__ == "__main__":
    frame = example()
    print(f"Timbers: {len(frame.cut_timbers)}")
    for ct in frame.cut_timbers:
        print(f"  - {ct.timber.ticket.name}")
