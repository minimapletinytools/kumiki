"""
Timber Frame Shed - Base, Floor Joists, and Mudsill Joints
"""

from kumiki import *
from kumiki.timber import Frame, CutTimber, PegShape
from kumiki.construction import (
    attach_face_aligned_timber,
    create_horizontal_timber_on_footprint,
    create_vertical_timber_on_footprint_corner,
    create_vertical_timber_on_footprint_side,
    create_axis_aligned_timber,
    ButtJointTimberArrangement,
)
from kumiki.footprint import Footprint, FootprintLocation
from kumiki.ticket import TimberTicket
from kumiki.joints.workshop.shavings import SimplePegParameters
from kumiki.joints.workshop.butt_joints import (
    cut_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_dropin_housed_butt_joint_on_face_aligned_timbers
)

# ============================================================================
# PARAMETERS - Modify these to adjust the shed base design
# ============================================================================

# Footprint dimensions: 16'x12'
# "the 12' sides are facing north/south" means:
# - North side (Y = 16') has length 12'
# - South side (Y = 0) has length 12'
# - East side (X = 12') has length 16'
# - West side (X = 0) has length 16'
base_width = feet(12)   # East-West width (12 feet)
base_length = feet(16)  # North-South length (16 feet)

# Mudsill size: 8" vertical height, 7" horizontal width
# Note: size[0] is the vertical Z-dimension, size[1] is the horizontal depth perpendicular to the footprint boundary
mudsill_height = inches(8)
mudsill_width = inches(7)
mudsill_size = create_v2(mudsill_height, mudsill_width)

# Joist size: 7" vertical height, 5" horizontal width
# Note: size[0] is the vertical Z-dimension, size[1] is the horizontal width perpendicular to joining direction
joist_height = inches(7)
joist_width = inches(5)
joist_size = create_v2(joist_height, joist_width)

# Spacing: 2'8" (which is 8/3 feet) center-to-center
joist_spacing = feet(8, 3)

# Post size: 7"x7" cross-section
# Height = mudsill top (8") + 9'4" = 8" + 112" = 120" = 10'. Posts sit at Z=0, tops at Z=10'.
post_size = create_v2(inches(7), inches(7))
post_height = feet(10)  # 10' = 8" mudsill height + 9'4" clear above mudsill top

# Top plate: 7" wide (perpendicular to wall, X direction) × 8" tall (Z direction)
# Plate top is flush with post tops (Z=10'). Plate extends 1' past each corner post end.
plate_height = inches(8)   # 8" in Z axis (vertical)
plate_width  = inches(7)   # 7" perpendicular to the wall (X direction)

# Peg parameters (stored in variables to be reused throughout the design)
peg_diameter = inches(3, 4)              # 3/4" diameter peg
peg_distance_from_shoulder = inches(3, 2) # 1.5" away from the shoulder


def build_shed_frame() -> Frame:
    """
    Build the shed floor frame including mudsills, floor joists, and mudsill joints.
    """
    # 1. Define the footprint (rectangular, counter-clockwise starting from South-West)
    # Corner 0: South-West (0, 0)
    # Corner 1: South-East (12', 0)
    # Corner 2: North-East (12', 16')
    # Corner 3: North-West (0, 16')
    footprint_corners = [
        create_v2(scalar(0), scalar(0)),       # Corner 0: South-West
        create_v2(base_width, scalar(0)),      # Corner 1: South-East
        create_v2(base_width, base_length),     # Corner 2: North-East
        create_v2(scalar(0), base_length)       # Corner 3: North-West
    ]
    footprint = Footprint(footprint_corners)  # type: ignore[arg-type]

    # 2. Place mudsills on the inside of the footprint on all 4 sides
    # Side 0 (South): Corner 0 -> Corner 1
    south_mudsill = create_horizontal_timber_on_footprint(
        footprint, 0, FootprintLocation.INSIDE, mudsill_size,
        ticket=TimberTicket(path="South Mudsill", tags=("mudsill",))
    )
    # Side 1 (East): Corner 1 -> Corner 2
    east_mudsill = create_horizontal_timber_on_footprint(
        footprint, 1, FootprintLocation.INSIDE, mudsill_size,
        ticket=TimberTicket(path="East Mudsill", tags=("mudsill",))
    )
    # Side 2 (North): Corner 2 -> Corner 3
    north_mudsill = create_horizontal_timber_on_footprint(
        footprint, 2, FootprintLocation.INSIDE, mudsill_size,
        ticket=TimberTicket(path="North Mudsill", tags=("mudsill",))
    )
    # Side 3 (West): Corner 3 -> Corner 0
    west_mudsill = create_horizontal_timber_on_footprint(
        footprint, 3, FootprintLocation.INSIDE, mudsill_size,
        ticket=TimberTicket(path="West Mudsill", tags=("mudsill",))
    )

    # 3. Connect the mudsills together at all 4 corners
    # - North and South mudsills have the tenon (butt_timber).
    # - West and East mudsills receive them (receiving_timber).
    # - Tenon orientation: Flat (1.5" vertical thickness × 5" horizontal width).
    # - Tenon length: 3"
    # - Mortise depth: 3.25" (1/4" deeper than tenon length).
    # - Relish: exactly 2" of relish from the ends of the longer West/East mudsills.
    #   Since West/East mudsills end at Y=0 / Y=16', and North/South sills are 7" wide (centerline at 3.5"),
    #   the tenon starts at 2" from the end and is 5" wide, ending at 7" (fully within the 7" mudsill width).
    #   The tenon center is at 4.5", which is offset inwards by exactly 1" from the mudsill centerline (3.5").
    #   Therefore, tenon_position Y-offset is -1" (opposite of local +Y axis).
    tenon_size = create_v2(inches(1.5), inches(5))
    tenon_length = inches(3)
    mortise_depth = inches(13, 4) # 3.25" (3" tenon + 1/4" clearance)
    
    # Offset by 1" inwards to get exactly 2" of relish at the ends of West/East mudsills
    tenon_position = create_v2(scalar(0), -inches(1))
    
    peg_params = SimplePegParameters(
        shape=PegShape.ROUND,
        peg_positions=[(peg_distance_from_shoulder, scalar(0))],
        size=peg_diameter,
        depth=None, # through peg
        stickout_length=scalar(0) # flush with entry face
    )

    # SW Corner Joint (South mudsill BOTTOM end butts into West mudsill)
    joint_sw = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=west_mudsill,
            butt_timber=south_mudsill,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        peg_parameters=peg_params,
    )

    # SE Corner Joint (South mudsill TOP end butts into East mudsill)
    joint_se = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=east_mudsill,
            butt_timber=south_mudsill,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        peg_parameters=peg_params,
    )

    # NE Corner Joint (North mudsill BOTTOM end butts into East mudsill)
    joint_ne = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=east_mudsill,
            butt_timber=north_mudsill,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        peg_parameters=peg_params,
    )

    # NW Corner Joint (North mudsill TOP end butts into West mudsill)
    joint_nw = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=west_mudsill,
            butt_timber=north_mudsill,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        ),
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        peg_parameters=peg_params,
    )

    # 4. Connect the west/east mudsills with 5x7 joists.
    # Spaced 2'8" apart from center to center.
    # West mudsill runs from Corner 3 (Y=16') to Corner 0 (Y=0) -> length direction -Y.
    # East mudsill runs from Corner 1 (Y=0) to Corner 2 (Y=16') -> length direction +Y.
    #
    # We place joists at 2'8", 5'4", 8'0", 10'8", 13'4" from the bottom of the East mudsill (Y=0).
    # Since east_mudsill runs in +Y, length_position_measurement is measured from Y=0.
    #
    # The top of the joist should be flush with the top of the mudsill.
    # Since mudsill_height = 8" and joist_height = 7", we can use attach_face_aligned_timber's
    # alignment feature to align the top of the joist (LEFT face when size[0] is vertical Z)
    # flush with the top of the mudsill (TimberFace.RIGHT).
    #
    # The joists extend 3" into the mudsills for support (attached_timber_stickout).

    joists = []
    # We want 5 joists spaced 2'8" apart:
    # 2'8", 5'4", 8'0", 10'8", 13'4"
    for i in range(1, 6):
        loc = joist_spacing * scalar(i)
        joist = attach_face_aligned_timber(
            original_timber=east_mudsill,
            size=joist_size,
            # Point from the East Mudsill (runs +Y) to the West (global -X, which is the local BACK face of East Mudsill)
            original_timber_long_face_that_attached_timber_points_to=TimberLongFace.BACK,
            # Target the West Mudsill so the joist spans across
            attached_timber_length_or_target=west_mudsill,
            # Extend joists 3" into sills on both sides for support
            attached_timber_stickout=Stickout.symmetric(inches(3), StickoutReference.INSIDE),
            # Measure location along East Mudsill starting from the bottom end (Y=0)
            original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
            length_position_measurement=loc,
            # Align the top face of the joist (LEFT face of joist) flush with the top of East Mudsill
            original_timber_face_to_measure_from_for_lateral_position=TimberFace.RIGHT,
            attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.LEFT,
            lateral_position_measurement=scalar(0),
            ticket=TimberTicket(path=f"Floor Joist {i}", tags=("joist",))
        )
        joists.append(joist)

    # 5. Join the joists to the sills
    joist_joints = []
    
    # Middle joist (Joist 3, index 2) is joined with a mortise and tenon joint
    # - Tenon: 1.5" thick (vertical/local X), 5" wide (horizontal/local Y)
    # - Position: bottom of the tenon is 4.5" below the top of the sill.
    #   Since top face is LEFT (local -X at -3.5"), the bottom of the tenon is at local X = +1.0"
    #   (which is 4.5" below -3.5").
    #   Tenon thickness is 1.5", so the tenon spans from local X = -0.5" to +1.0".
    #   Center of the tenon is at local X = +0.25" (+1/4" offset).
    joist3_tenon_size = create_v2(inches(1.5), inches(5))
    joist3_tenon_length = inches(3)
    joist3_mortise_depth = inches(13, 4) # 3.25"
    joist3_tenon_position = create_v2(inches(1, 4), scalar(0)) # +0.25" local X (depth to bottom is 4.5")

    # East end of Floor Joist 3
    joint_joist3_east = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=east_mudsill,
            butt_timber=joists[2],
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.LEFT,
        ),
        tenon_size=joist3_tenon_size,
        tenon_length=joist3_tenon_length,
        mortise_depth=joist3_mortise_depth,
        tenon_position=joist3_tenon_position,
        peg_parameters=peg_params, # Added peg!
    )
    # West end of Floor Joist 3
    joint_joist3_west = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=west_mudsill,
            butt_timber=joists[2],
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.LEFT,
        ),
        tenon_size=joist3_tenon_size,
        tenon_length=joist3_tenon_length,
        mortise_depth=joist3_mortise_depth,
        tenon_position=joist3_tenon_position,
        peg_parameters=peg_params, # Added peg!
    )
    joist_joints.extend([joint_joist3_east, joint_joist3_west])

    # Other joists (Joists 1, 2, 4, 5) are joined with the drop-in housed butt joint
    # - Joist extends 3" into sills, so housing_length = 3"
    # - Housing width = 5" (width of joist)
    # - Housing depth = 4.5" (so the pocket is 4.5" deep, and the remaining 2.5" bottom section of the 7" joist is cut away)
    for idx in [0, 1, 3, 4]:
        joist = joists[idx]
        # East end
        joint_east = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=east_mudsill,
                butt_timber=joist,
                butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.LEFT,
            ),
            receiving_timber_shoulder_inset=scalar(0),
            housing_length=inches(3),
            housing_width=inches(5),
            housing_depth=inches(9, 2), # 4.5" depth
        )
        # West end
        joint_west = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=west_mudsill,
                butt_timber=joist,
                butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.LEFT,
            ),
            receiving_timber_shoulder_inset=scalar(0),
            housing_length=inches(3),
            housing_width=inches(5),
            housing_depth=inches(9, 2), # 4.5" depth
        )
        joist_joints.extend([joint_east, joint_west])

    # 6. Place 6 posts (7"x7") on the inside of the footprint and join to mudsills.
    #
    #  Post height: 10' total (Z=0 to Z=10'). Mudsill tops are at Z=8", so posts
    #  extend 9'4" (= 112") above the mudsill top, as requested.
    #
    #  Corner posts sit in the footprint corner (INSIDE = vertex on the corner, post inward).
    #  All posts join exclusively to the east or west mudsill:
    #    SW (corner 0): local X = +X → connects to west mudsill (thickness in local X)
    #    SE (corner 1): local Y = -X → connects to east  mudsill (thickness in local Y)
    #    NE (corner 2): local X = -X → connects to east  mudsill (thickness in local X)
    #    NW (corner 3): local Y = +X → connects to west  mudsill (thickness in local Y)
    #
    #  Mid-side posts on East/West at the 8' midpoint join their respective mudsills.
    #
    #  Tenon: 1.5" thick × 6.5" wide × 3" deep (into mudsill top face)
    #  - Thickness (local Y, perpendicular to boundary) = 1.5"
    #  - Width   (local X, along mudsill length)        = 6.5"
    #  - tenon_position = (0, -1.25"):  the -1.25" local-Y offset moves the tenon
    #    center from the post centerline (3.5" from outside edge) to 2.25" from
    #    the outside edge, leaving a 1.5" gap (= 2.25" − 1.5"/2) between the
    #    tenon outer face and the mudsill outside edge.

    # Tenon parameters for posts whose local Y is perpendicular to the E/W mudsill
    # (SE, NW corner posts and both center posts): thickness in local Y, width in local X.
    post_tenon_size     = create_v2(inches(13, 2), inches(3, 2))  # 6.5" (local X, along mudsill) × 1.5" (local Y, perp to mudsill)
    post_tenon_length   = inches(3)                                # 3" deep tenon
    post_mortise_depth  = inches(13, 4)                            # 3.25" mortise (+ 0.25" clearance)
    # -1.25" in local Y: centers tenon 2.25" from the mudsill outside edge → 1.5" gap
    post_tenon_position = create_v2(scalar(0), -inches(5, 4))

    # Tenon parameters for SW and NE corner posts, which connect to the E/W mudsills
    # via their local X axis (thickness in local X, width in local Y).
    corner_ew_tenon_size     = create_v2(inches(3, 2), inches(13, 2))  # 1.5" (local X, perp to mudsill) × 6.5" (local Y, along mudsill)
    # -1.25" in local X: centers tenon 2.25" from the mudsill outside edge → 1.5" gap
    corner_ew_tenon_position = create_v2(-inches(5, 4), scalar(0))

    # --- Corner posts ---
    post_sw = create_vertical_timber_on_footprint_corner(
        footprint, 0, post_height, FootprintLocation.INSIDE, post_size,
        ticket=TimberTicket(path="southwest-corner-post", tags=("post",))
    )
    post_se = create_vertical_timber_on_footprint_corner(
        footprint, 1, post_height, FootprintLocation.INSIDE, post_size,
        ticket=TimberTicket(path="southeast-corner-post", tags=("post",))
    )
    post_ne = create_vertical_timber_on_footprint_corner(
        footprint, 2, post_height, FootprintLocation.INSIDE, post_size,
        ticket=TimberTicket(path="northeast-corner-post", tags=("post",))
    )
    post_nw = create_vertical_timber_on_footprint_corner(
        footprint, 3, post_height, FootprintLocation.INSIDE, post_size,
        ticket=TimberTicket(path="northwest-corner-post", tags=("post",))
    )

    # --- Mid-side posts: East and West sides at 8' midpoint ---
    mid_side_distance = base_length / scalar(2)  # 8' along 16' side

    post_east_center = create_vertical_timber_on_footprint_side(
        footprint, 1, mid_side_distance, post_height, FootprintLocation.INSIDE, post_size,
        ticket=TimberTicket(path="east-center-post", tags=("post",))
    )
    post_west_center = create_vertical_timber_on_footprint_side(
        footprint, 3, mid_side_distance, post_height, FootprintLocation.INSIDE, post_size,
        ticket=TimberTicket(path="west-center-post", tags=("post",))
    )

    # --- Post-to-mudsill mortise and tenon joints ---
    # Each post (butt_timber, BOTTOM end) joints into the top face of its adjacent mudsill
    # (receiving_timber). front_face_on_butt_timber=None lets the joint auto-detect orientation.

    # SW corner post → west mudsill
    # SW post: local X = +X_global (perp to west mudsill), local Y = +Y_global (along west mudsill)
    # Offset -1.25" in local X keeps tenon 1.5" from the west boundary (X=0).
    joint_post_sw = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=west_mudsill,
            butt_timber=post_sw,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=corner_ew_tenon_size,
        tenon_length=post_tenon_length,
        mortise_depth=post_mortise_depth,
        tenon_position=corner_ew_tenon_position,
    )

    # SE corner post → east mudsill
    joint_post_se = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=east_mudsill,
            butt_timber=post_se,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=post_tenon_size,
        tenon_length=post_tenon_length,
        mortise_depth=post_mortise_depth,
        tenon_position=post_tenon_position,
    )

    # NE corner post → east mudsill
    # NE post: local X = -X_global (perp to east mudsill), local Y = -Y_global (along east mudsill)
    # Offset -1.25" in local X (+1.25" in X_global) keeps tenon 1.5" from the east boundary (X=12').
    joint_post_ne = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=east_mudsill,
            butt_timber=post_ne,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=corner_ew_tenon_size,
        tenon_length=post_tenon_length,
        mortise_depth=post_mortise_depth,
        tenon_position=corner_ew_tenon_position,
    )

    # NW corner post → west mudsill
    joint_post_nw = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=west_mudsill,
            butt_timber=post_nw,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=post_tenon_size,
        tenon_length=post_tenon_length,
        mortise_depth=post_mortise_depth,
        tenon_position=post_tenon_position,
    )

    # East center post → east mudsill
    joint_post_east_center = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=east_mudsill,
            butt_timber=post_east_center,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=post_tenon_size,
        tenon_length=post_tenon_length,
        mortise_depth=post_mortise_depth,
        tenon_position=post_tenon_position,
    )

    # West center post → west mudsill
    joint_post_west_center = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=west_mudsill,
            butt_timber=post_west_center,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
        ),
        tenon_size=post_tenon_size,
        tenon_length=post_tenon_length,
        mortise_depth=post_mortise_depth,
        tenon_position=post_tenon_position,
    )

    post_joints = [
        joint_post_sw, joint_post_se, joint_post_ne, joint_post_nw,
        joint_post_east_center, joint_post_west_center,
    ]

    # 7. Top plates connecting the 3 posts on each wall.
    #
    #  Plate spec: 8" tall (Z) × 7" deep (perpendicular to wall = X direction)
    #  Running N-S (Y direction), sitting on top of the posts (plate top flush with post tops).
    #
    #  Stickout: 1' past the outer face of each corner post:
    #    - SW/SE corner posts: south face at Y=0  → plate south end at Y = -12"
    #    - NW/NE corner posts: north face at Y=16' → plate north end at Y = 16'+12" = 204"
    #    - Total plate length = 18' = 216"
    #
    #  Top plate bottom_position = center of south face:
    #    - Z center = post_height - plate_height/2  (plate top flush with post tops)
    #    - length_direction = TimberFace.FRONT (+Y_global)
    #    - width_direction  = TimberFace.TOP   (+Z_global, so size[0]=8" is the Z dimension)
    #    - size = (plate_height=8", plate_width=7")  i.e. (local X = +Z, local Y = +X)
    #
    #  Plate local axes:
    #    local Z (length) = +Y_global
    #    local X (width)  = +Z_global  (size[0] = 8" in Z)
    #    local Y          = +Y × +Z = +X_global  (size[1] = 7" across wall)

    plate_size         = create_v2(plate_height, plate_width)  # (8", 7")
    plate_length       = base_length + scalar(2) * feet(1)     # 16' + 2×1' = 18'
    plate_z_center     = post_height - plate_height / scalar(2)  # Z center of plate cross-section
    plate_y_south_end  = -feet(1)                               # 1' south of Y=0

    # West top plate (posts at X=0–7", center at X=3.5")
    plate_west = create_axis_aligned_timber(
        bottom_position=create_v3(
            plate_width / scalar(2),    # X center = 3.5"
            plate_y_south_end,          # south end (= bottom of timber in length direction)
            plate_z_center,             # Z center
        ),
        length=plate_length,
        size=plate_size,
        length_direction=TimberFace.FRONT,   # +Y_global
        width_direction=TimberFace.TOP,      # +Z_global (size[0]=8" is Z)
        ticket=TimberTicket(path="West Top Plate", tags=("plate",))
    )

    # East top plate (posts at X=12'-7"–12', center at X=12'-3.5")
    plate_east = create_axis_aligned_timber(
        bottom_position=create_v3(
            base_width - plate_width / scalar(2),  # X center = 12'-3.5"
            plate_y_south_end,
            plate_z_center,
        ),
        length=plate_length,
        size=plate_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.TOP,
        ticket=TimberTicket(path="East Top Plate", tags=("plate",))
    )

    # --- Post-to-top-plate mortise and tenon joints ---
    #
    # Each post tenon (TimberEnd.TOP) goes UP into the plate bottom face (receiving_timber).
    # Tenon: 1.5" thick (perpendicular to plate = X direction) × 6.5" wide (along plate = Y direction)
    # Depth: 4" tenon, 4.25" mortise. Round pegs (matching mudsill-to-post joints).
    #
    # Tenon size is expressed in each post's local (X, Y) space. Confirmed local axes:
    #   SW  post: localX=+X, localY=+Y  → 1.5" in localX (+X), 6.5" in localY (+Y)  → (1.5", 6.5")
    #   NW  post: localX=-Y, localY=+X  → 6.5" in localX (−Y=along plate), 1.5" in localY (+X) → (6.5", 1.5")
    #   W-c post: same as NW                                                              → (6.5", 1.5")
    #   SE  post: localX=+Y, localY=-X  → 6.5" in localX (+Y=along plate), 1.5" in localY (−X) → (6.5", 1.5")
    #   NE  post: localX=-X, localY=-Y  → 1.5" in localX (−X), 6.5" in localY (−Y=along plate) → (1.5", 6.5")
    #   E-c post: same as SE                                                              → (6.5", 1.5")

    top_plate_tenon_length  = inches(4)       # 4" deep tenon
    top_plate_mortise_depth = inches(17, 4)   # 4.25" mortise (4" + 1/4" clearance)

    # Round pegs — same spec as the mudsill-corner and post-to-sill pegs
    top_peg_params = SimplePegParameters(
        shape=PegShape.ROUND,
        peg_positions=[(peg_distance_from_shoulder, scalar(0))],
        size=peg_diameter,
        depth=None,             # through peg
        stickout_length=scalar(0)
    )

    # Posts where 1.5" is in local X and 6.5" is in local Y: SW, NE
    top_tenon_size_A = create_v2(inches(3, 2), inches(13, 2))   # (1.5" localX, 6.5" localY)
    # Posts where 6.5" is in local X and 1.5" is in local Y: NW, W-center, SE, E-center
    top_tenon_size_B = create_v2(inches(13, 2), inches(3, 2))   # (6.5" localX, 1.5" localY)

    # West side post-to-plate joints
    # The aligned-plane normal = Z_post × Y_plate = +Z × +Y = −X_global.
    # front_face_on_butt_timber must point in −X_global for all posts:
    #   SW  (localX=+X, localY=+Y):  LEFT   (= −localX = −X_global)
    #   W-c (localX=−Y, localY=+X):  BACK   (= −localY = −X_global)
    #   NW  (localX=−Y, localY=+X):  BACK   (= −localY = −X_global)
    #   SE  (localX=+Y, localY=−X):  FRONT  (= +localY = −X_global)
    #   E-c (localX=+Y, localY=−X):  FRONT  (= +localY = −X_global)
    #   NE  (localX=−X, localY=−Y):  RIGHT  (= +localX = −X_global)
    joint_top_sw = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_west,
            butt_timber=post_sw,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.LEFT,   # −localX = −X_global
        ),
        tenon_size=top_tenon_size_A,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    joint_top_west_center = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_west,
            butt_timber=post_west_center,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.BACK,   # −localY = −X_global
        ),
        tenon_size=top_tenon_size_B,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    joint_top_nw = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_west,
            butt_timber=post_nw,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.BACK,   # −localY = −X_global
        ),
        tenon_size=top_tenon_size_B,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    # East side post-to-plate joints
    joint_top_se = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_east,
            butt_timber=post_se,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,  # +localY = −X_global
        ),
        tenon_size=top_tenon_size_B,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    joint_top_east_center = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_east,
            butt_timber=post_east_center,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,  # +localY = −X_global
        ),
        tenon_size=top_tenon_size_B,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    joint_top_ne = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_east,
            butt_timber=post_ne,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.RIGHT,  # +localX = −X_global
        ),
        tenon_size=top_tenon_size_A,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    top_plate_joints = [
        joint_top_sw, joint_top_west_center, joint_top_nw,
        joint_top_se, joint_top_east_center, joint_top_ne,
    ]

    # 8. Tie beams connecting each post pair from East to West.
    #
    #  Tie beam spec: 7" wide × 8" tall (Z axis).
    #  Positioned 18" below the top of the posts (top face of tie beam is 18" below post tops).
    #  Joined with wedged half-dovetail M&T joints:
    #  - 1.5" wide (thickness across the Y axis)
    #  - 1" dovetail depth (taper over 7" tenon depth)
    #  - Through-tenons flush with post outside faces, with wedge accessories.

    from sympy import atan

    tie_beam_size = create_v2(inches(8), inches(7))  # 8" in Z axis, 7" in Y axis
    tb_tenon_depth = inches(7)      # 7" post depth through to outside face
    tb_dovetail_depth = inches(1)   # 1" dovetail depth
    # tenon_size: X = butt RIGHT axis (+Z, height = 8" - 1" dovetail = 7"), Y = butt TOP axis (Y, width = 1.5")
    tb_tenon_size = create_v2(inches(7), inches(3, 2))

    tb_wedge_params = DovetailTenonWedgeAccessoryParameters(
        wedge_angle=atan(tb_dovetail_depth / tb_tenon_depth),
        wedge_extra_height=scalar(0),
    )

    tie_beam_pairs = [
        (post_sw, post_se, "South Tie Beam"),
        (post_west_center, post_east_center, "Center Tie Beam"),
        (post_nw, post_ne, "North Tie Beam"),
    ]

    tie_beam_joints = []
    south_tie_beam = None
    north_tie_beam = None
    for w_post, e_post, name in tie_beam_pairs:
        facing_dir = e_post.get_bottom_position_global() - w_post.get_bottom_position_global()
        facing_face = w_post.get_closest_oriented_long_face_from_global_direction(facing_dir)
        tb = attach_face_aligned_timber(
            original_timber=w_post,
            size=tie_beam_size,
            original_timber_long_face_that_attached_timber_points_to=facing_face,
            attached_timber_length_or_target=e_post,
            attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.OUTSIDE),
            original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
            attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.RIGHT,
            length_position_measurement=inches(18),
            ticket=TimberTicket(path=name, tags=("beam", "tie_beam"))
        )
        if name == "South Tie Beam":
            south_tie_beam = tb
        elif name == "North Tie Beam":
            north_tie_beam = tb
        
        # West joint: wedged half dovetail mortise & tenon (BOTTOM end of tie beam meets West post)
        joint_w = cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=w_post,
                butt_timber=tb,
                butt_timber_end=TimberEnd.BOTTOM,
            ),
            dovetail_top_side_on_butt_timber=TimberLongFace.RIGHT,
            tenon_size=tb_tenon_size,
            tenon_depth=tb_tenon_depth,
            dovetail_depth=tb_dovetail_depth,
            wedge_accessory_parameters=tb_wedge_params,
        )
        # East joint: wedged half dovetail mortise & tenon (TOP end of tie beam meets East post)
        joint_e = cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=e_post,
                butt_timber=tb,
                butt_timber_end=TimberEnd.TOP,
            ),
            dovetail_top_side_on_butt_timber=TimberLongFace.RIGHT,
            tenon_size=tb_tenon_size,
            tenon_depth=tb_tenon_depth,
            dovetail_depth=tb_dovetail_depth,
            wedge_accessory_parameters=tb_wedge_params,
        )
        tie_beam_joints.extend([joint_w, joint_e])

    # 9. Wall Girts connecting corner posts to middle posts on West and East sides.
    #
    #  Girt spec: 4" wide × 5" tall (Z axis).
    #  Elevation: top of girt is 3' 4.5" (40.5") above the top of the mudsill (Z = 48.5" total).
    #  Alignment: flush with the outside face of the posts (X = 0 on West, X = 12' on East).

    mudsill_top = inches(8)
    girt_top_above_mudsill = feet(3) + inches(9, 2)  # 40.5" = 3' 4.5"
    girt_top_z = mudsill_top + girt_top_above_mudsill  # 48.5"
    girt_height = inches(5)
    girt_width = inches(4)
    girt_centerline_z = girt_top_z - girt_height / scalar(2)  # 46.0"

    girt_size = create_v2(girt_height, girt_width)

    # West South Girt (sw_post -> w_center_post)
    w_s_girt = attach_face_aligned_timber(
        original_timber=post_sw,
        size=girt_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=post_west_center,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=girt_centerline_z,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.LEFT,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.BACK,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="West South Girt", tags=("beam", "girt"))
    )

    # West North Girt (w_center_post -> nw_post)
    w_n_girt = attach_face_aligned_timber(
        original_timber=post_west_center,
        size=girt_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.LEFT,
        attached_timber_length_or_target=post_nw,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=girt_centerline_z,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.BACK,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.BACK,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="West North Girt", tags=("beam", "girt"))
    )

    # East South Girt (se_post -> e_center_post)
    e_s_girt = attach_face_aligned_timber(
        original_timber=post_se,
        size=girt_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=post_east_center,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=girt_centerline_z,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.BACK,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.FRONT,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="East South Girt", tags=("beam", "girt"))
    )

    # East North Girt (e_center_post -> ne_post)
    e_n_girt = attach_face_aligned_timber(
        original_timber=post_east_center,
        size=girt_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=post_ne,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=girt_centerline_z,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.BACK,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.FRONT,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="East North Girt", tags=("beam", "girt"))
    )

    # North Girt (nw_post -> ne_post, top of girt at 3' above mudsill top)
    north_girt_top_z = mudsill_top + feet(3)  # 36" above mudsill top = 44" Z total
    north_girt_centerline_z = north_girt_top_z - girt_height / scalar(2)  # 41.5"

    n_girt = attach_face_aligned_timber(
        original_timber=post_nw,
        size=girt_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=post_ne,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=north_girt_centerline_z,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.LEFT,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.BACK,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="North Girt", tags=("beam", "girt"))
    )

    # --- Barefaced Mortise & Tenon Joints with Round Pegs for Wall Girts ---
    #
    # Spec: 1.5" thick × 4" wide (Z axis) × 4" deep into post. Round pegs.
    # Barefaced: tenon face is flush with the inside face of the girt (shoulder on outside face).
    girt_tenon_size = create_v2(inches(4), inches(3, 2))
    girt_tenon_length = inches(4)
    girt_mortise_depth = inches(17, 4)  # 4.25" (4" + 1/4" clearance)

    # Offset to align tenon face flush with inside face of girt
    west_girt_tenon_pos = create_v2(scalar(0), inches(5, 4))   # +1.25" towards inside face (+X)
    east_girt_tenon_pos = create_v2(scalar(0), -inches(5, 4))  # -1.25" towards inside face (-X)
    north_girt_tenon_pos = create_v2(scalar(0), inches(5, 4))  # +1.25" towards inside face (-Y = FRONT)

    girt_peg_params = SimplePegParameters(
        shape=PegShape.ROUND,
        peg_positions=[(peg_distance_from_shoulder, scalar(0))],
        size=peg_diameter,
        depth=None,             # through peg
        stickout_length=scalar(0)
    )

    girt_joint_specs = [
        (w_s_girt, post_sw, TimberEnd.BOTTOM, west_girt_tenon_pos),
        (w_s_girt, post_west_center, TimberEnd.TOP, west_girt_tenon_pos),
        (w_n_girt, post_west_center, TimberEnd.BOTTOM, west_girt_tenon_pos),
        (w_n_girt, post_nw, TimberEnd.TOP, west_girt_tenon_pos),
        (e_s_girt, post_se, TimberEnd.BOTTOM, east_girt_tenon_pos),
        (e_s_girt, post_east_center, TimberEnd.TOP, east_girt_tenon_pos),
        (e_n_girt, post_east_center, TimberEnd.BOTTOM, east_girt_tenon_pos),
        (e_n_girt, post_ne, TimberEnd.TOP, east_girt_tenon_pos),
        (n_girt, post_nw, TimberEnd.BOTTOM, north_girt_tenon_pos),
        (n_girt, post_ne, TimberEnd.TOP, north_girt_tenon_pos),
    ]

    girt_joints = []
    for girt, post, end, pos in girt_joint_specs:
        j = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post,
                butt_timber=girt,
                butt_timber_end=end,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=girt_tenon_size,
            tenon_length=girt_tenon_length,
            mortise_depth=girt_mortise_depth,
            tenon_position=pos,
            peg_parameters=girt_peg_params,
        )
        girt_joints.append(j)

    # 10. South Door Posts connecting South Mudsill to South Tie Beam.
    #
    #  Door post spec: 4" deep (Y axis) × 5" wide (X axis).
    #  Alignment: flush with the outside face of the South wall (Y = 0 to Y = 4").
    #  Symmetry: centered around X = 6' (72") with a 3' 6" (42") door opening gap.
    #    - West Door Post: X = 46" to 51" (centerline X = 48.5")
    #    - East Door Post: X = 93" to 98" (centerline X = 95.5")

    door_post_size = create_v2(inches(5), inches(4))

    west_door_post = attach_face_aligned_timber(
        original_timber=south_mudsill,
        size=door_post_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=south_tie_beam,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=inches(97, 2),  # 48.5" centerline in X
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.FRONT,  # Y=0 outside face
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.FRONT,
        lateral_position_measurement=inches(4),  # offset to sit from Y=0 to Y=4"
        ticket=TimberTicket(path="West Door Post", tags=("post", "door_post"))
    )

    east_door_post = attach_face_aligned_timber(
        original_timber=south_mudsill,
        size=door_post_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=south_tie_beam,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=inches(191, 2),  # 95.5" centerline in X
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.FRONT,  # Y=0 outside face
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.FRONT,
        lateral_position_measurement=inches(4),  # offset to sit from Y=0 to Y=4"
        ticket=TimberTicket(path="East Door Post", tags=("post", "door_post"))
    )

    # Barefaced M&T joints for door posts (bottom unpegged, top pegged)
    dp_tenon_size = create_v2(inches(4), inches(3, 2))  # 4" wide in X, 1.5" thick in Y
    dp_tenon_length = inches(4)
    dp_mortise_depth = inches(17, 4)  # 4.25" depth
    dp_tenon_pos = create_v2(scalar(0), inches(5, 4))   # +1.25" in Y (flush with inside face Y=4")

    door_post_joints = [
        # West Door Post bottom (mudsill) - UNPEGGED
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=south_mudsill, butt_timber=west_door_post, butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=dp_tenon_size, tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
            tenon_position=dp_tenon_pos, peg_parameters=None,
        ),
        # West Door Post top (tie beam) - PEGGED
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=south_tie_beam, butt_timber=west_door_post, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=dp_tenon_size, tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
            tenon_position=dp_tenon_pos, peg_parameters=girt_peg_params,
        ),
        # East Door Post bottom (mudsill) - UNPEGGED
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=south_mudsill, butt_timber=east_door_post, butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=dp_tenon_size, tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
            tenon_position=dp_tenon_pos, peg_parameters=None,
        ),
        # East Door Post top (tie beam) - PEGGED
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=south_tie_beam, butt_timber=east_door_post, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=dp_tenon_size, tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
            tenon_position=dp_tenon_pos, peg_parameters=girt_peg_params,
        ),
    ]

    # 11. South Wall Girts connecting corner posts to door posts.
    #
    #  Spec: 4" wide × 5" tall (Z axis), top of girt at 3' (36") above mudsill top (Z = 44" total).
    #  Flush with outside face of South wall (Y = 0 to 4").
    #  Joints:
    #    - Barefaced M&T at corner posts (tenon face flush with inside face)
    #    - CENTERED M&T at door posts (tenon centered in 4" width)
    #    - All girt joints pegged with round pegs.

    south_girt_top_z = mudsill_top + feet(3)  # 44" Z total
    south_girt_centerline_z = south_girt_top_z - girt_height / scalar(2)  # 41.5"

    s_w_girt = attach_face_aligned_timber(
        original_timber=post_sw,
        size=girt_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=west_door_post,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=south_girt_centerline_z,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.BACK,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.FRONT,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="South West Girt", tags=("beam", "girt"))
    )

    s_e_girt = attach_face_aligned_timber(
        original_timber=post_se,
        size=girt_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=east_door_post,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=south_girt_centerline_z,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.LEFT,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.BACK,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="South East Girt", tags=("beam", "girt"))
    )

    sw_bareface_pos = create_v2(scalar(0), -inches(5, 4))  # -1.25" towards inside face (BACK = Y=4")
    se_bareface_pos = create_v2(scalar(0), inches(5, 4))   # +1.25" towards inside face (FRONT = Y=4")
    centered_pos = create_v2(scalar(0), scalar(0))

    south_girt_joints = [
        # South West Girt -> SW post (barefaced, pegged)
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post_sw, butt_timber=s_w_girt, butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=girt_tenon_size, tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
            tenon_position=sw_bareface_pos, peg_parameters=girt_peg_params,
        ),
        # South West Girt -> West Door Post (CENTERED, pegged)
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=west_door_post, butt_timber=s_w_girt, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=girt_tenon_size, tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
            tenon_position=centered_pos, peg_parameters=girt_peg_params,
        ),
        # South East Girt -> SE post (barefaced, pegged)
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post_se, butt_timber=s_e_girt, butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.BACK,
            ),
            tenon_size=girt_tenon_size, tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
            tenon_position=se_bareface_pos, peg_parameters=girt_peg_params,
        ),
        # South East Girt -> East Door Post (CENTERED, pegged)
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=east_door_post, butt_timber=s_e_girt, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.BACK,
            ),
            tenon_size=girt_tenon_size, tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
            tenon_position=centered_pos, peg_parameters=girt_peg_params,
        ),
    ]

    # 12. Perimeter 3x5 Knee Braces connecting Corner/Center Posts to Top Plates and Tie Beams.
    #
    #  Spec: 3" thick (inward) × 5" deep (wall plane). 45° angle.
    #  Layout: 18" from inside corner to outside corner of brace along post and beam legs.
    #  Alignment: Outside face of every brace is flush with the outside surface of the structure.
    #  Joints: Barefaced M&T joints with 3.5" orthogonal mortise depth and ¾" round pegs.

    from sympy import pi, sqrt

    brace_size = create_v2(inches(5), inches(3))
    plate_brace_length_pos = inches(8) + inches(18)  # 26" from post top (18" from top plate bottom)
    tie_brace_length_pos = inches(22) + inches(18)   # 40" from post top (18" from tie beam bottom)
    b_length = inches(18) * sqrt(2)  # Exact 18" layout hypotenuse (25.456")

    brace_tenon_size = create_v2(inches(7, 2), inches(3, 2))  # 3.5" wide in wall plane × 1.5" thick
    brace_tenon_length = inches(4)
    brace_mortise_depth = inches(7, 2)  # 3.5" orthogonal depth into mortise face

    pos_pos = create_v2(scalar(0), inches(3, 4))   # +0.75" offset when FRONT is inside face
    pos_neg = create_v2(scalar(0), -inches(3, 4))  # -0.75" offset when BACK is inside face

    brace_specs = [
        # West Wall (outside face at X=0)
        (post_sw, TimberLongFace.FRONT, plate_west, plate_brace_length_pos, TimberFace.LEFT, TimberLongFace.BACK, "West SW Brace", TimberLongFace.FRONT, pos_pos),
        (post_west_center, TimberLongFace.RIGHT, plate_west, plate_brace_length_pos, TimberFace.BACK, TimberLongFace.FRONT, "West Center South Brace", TimberLongFace.FRONT, pos_neg),
        (post_west_center, TimberLongFace.LEFT, plate_west, plate_brace_length_pos, TimberFace.BACK, TimberLongFace.BACK, "West Center North Brace", TimberLongFace.FRONT, pos_pos),
        (post_nw, TimberLongFace.RIGHT, plate_west, plate_brace_length_pos, TimberFace.BACK, TimberLongFace.FRONT, "West NW Brace", TimberLongFace.FRONT, pos_neg),

        # East Wall (outside face at X=12')
        (post_se, TimberLongFace.RIGHT, plate_east, plate_brace_length_pos, TimberFace.BACK, TimberLongFace.FRONT, "East SE Brace", TimberLongFace.BACK, pos_neg),
        (post_east_center, TimberLongFace.LEFT, plate_east, plate_brace_length_pos, TimberFace.BACK, TimberLongFace.BACK, "East Center South Brace", TimberLongFace.BACK, pos_pos),
        (post_east_center, TimberLongFace.RIGHT, plate_east, plate_brace_length_pos, TimberFace.BACK, TimberLongFace.FRONT, "East Center North Brace", TimberLongFace.BACK, pos_neg),
        (post_ne, TimberLongFace.FRONT, plate_east, plate_brace_length_pos, TimberFace.LEFT, TimberLongFace.BACK, "East NE Brace", TimberLongFace.BACK, pos_pos),

        # South Wall (outside face at Y=0)
        (post_sw, TimberLongFace.RIGHT, south_tie_beam, tie_brace_length_pos, TimberFace.BACK, TimberLongFace.FRONT, "South SW Brace", TimberLongFace.FRONT, pos_neg),
        (post_se, TimberLongFace.FRONT, south_tie_beam, tie_brace_length_pos, TimberFace.LEFT, TimberLongFace.BACK, "South SE Brace", TimberLongFace.FRONT, pos_pos),

        # North Wall (outside face at Y=16')
        (post_nw, TimberLongFace.FRONT, north_tie_beam, tie_brace_length_pos, TimberFace.LEFT, TimberLongFace.BACK, "North NW Brace", TimberLongFace.BACK, pos_pos),
        (post_ne, TimberLongFace.RIGHT, north_tie_beam, tie_brace_length_pos, TimberFace.BACK, TimberLongFace.FRONT, "North NE Brace", TimberLongFace.BACK, pos_neg),
    ]

    brace_joints = []
    for post, facing_face, target_beam, length_pos, orig_lat, att_lat, name, peg_face, tenon_pos in brace_specs:
        b = attach_plane_aligned_timber(
            original_timber=post,
            size=brace_size,
            original_timber_long_face_that_attached_timber_points_to=facing_face,
            attached_timber_angle=pi / 4,
            attached_timber_length_or_target=b_length,
            attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
            original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
            attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.RIGHT,
            length_position_measurement=length_pos,
            original_timber_face_to_measure_from_for_lateral_position=orig_lat,
            attached_timber_long_face_to_measure_to_for_lateral_position=att_lat,
            lateral_position_measurement=scalar(0),
            ticket=TimberTicket(path=name, tags=("beam", "brace"))
        )
        j_post = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post, butt_timber=b, butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=peg_face,
            ),
            tenon_size=brace_tenon_size, tenon_length=brace_tenon_length, mortise_depth=brace_mortise_depth,
            tenon_position=tenon_pos, peg_parameters=girt_peg_params,
            bore_mortise_perpendicular_to_face=True,
        )
        j_beam = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=target_beam, butt_timber=b, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=peg_face,
            ),
            tenon_size=brace_tenon_size, tenon_length=brace_tenon_length, mortise_depth=brace_mortise_depth,
            tenon_position=tenon_pos, peg_parameters=girt_peg_params,
            bore_mortise_perpendicular_to_face=True,
        )
        brace_joints.extend([j_post, j_beam])

    # 13. 9 Pairs of 5x5 Rafters (Pitch: 45°, Overhang: 18", 5"x5" section).
    #
    #  Geometry:
    #  - Rafter bottom face intersects West/East Top Plate outside face (X=0 / X=144") 3.5" below plate top (Z=116.5").
    #  - 45° slope (rise = 1, run = 1). Rafters meet at roof peak X = 72" (Z = 188.5").
    #  - Rafters extend 18" beyond plate outside face (to X = -18" / X = 162"). Total horizontal span = 90" (7.5').
    #  - 3D length = 90" × √2 = 127.279" (10.606 ft).
    #
    #  Joints:
    #  - Peak Joint: Tongue and fork corner joint between West Rafter and East Rafter at top ends.
    #  - Plate Housing Joint: Generic housing cut on West/East Top Plates receiving the 9 crossing rafters.

    from kumiki.rule import Orientation
    from kumiki.joints.workshop.corner_joints import (
        cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers,
        CornerJointTimberArrangement,
    )
    from kumiki.joints.workshop.free_joints import cut_free_house_joint

    rafter_size = create_v2(inches(5), inches(5))
    rafter_length = inches(90) * sqrt(2)

    spacing = (inches(189.5) - inches(2.5)) / scalar(6)  # 31.1667"
    y_centerlines = [
        -inches(12) + inches(5) / scalar(2),
        inches(2.5),
        inches(2.5) + spacing,
        inches(2.5) + scalar(2) * spacing,
        inches(2.5) + scalar(3) * spacing,
        inches(2.5) + scalar(4) * spacing,
        inches(2.5) + scalar(5) * spacing,
        inches(189.5),
        inches(204) - inches(5) / scalar(2),
    ]

    u_west = Matrix([sqrt(2) / scalar(2), scalar(0), sqrt(2) / scalar(2)])
    u_east = Matrix([-sqrt(2) / scalar(2), scalar(0), sqrt(2) / scalar(2)])
    w_dir = Matrix([scalar(0), scalar(1), scalar(0)])

    orient_west = Orientation.from_z_and_x(u_west, w_dir)
    orient_east = Orientation.from_z_and_x(u_east, w_dir)

    start_x_west = -inches(18)
    start_z_west = inches(233, 2) + (inches(5) / scalar(2)) / sqrt(2) - inches(18)

    start_x_east = feet(12) + inches(18)
    start_z_east = start_z_west

    west_rafters = []
    east_rafters = []
    rafter_peak_joints = []

    for i, y_c in enumerate(y_centerlines, start=1):
        pos_w = Matrix([start_x_west, y_c, start_z_west])
        pos_e = Matrix([start_x_east, y_c, start_z_east])

        rw = Timber(
            size=rafter_size,
            length=rafter_length,
            transform=Transform(position=pos_w, orientation=orient_west),
            ticket=TimberTicket(path=f"West Rafter {i}", tags=("beam", "rafter"))
        )
        re = Timber(
            size=rafter_size,
            length=rafter_length,
            transform=Transform(position=pos_e, orientation=orient_east),
            ticket=TimberTicket(path=f"East Rafter {i}", tags=("beam", "rafter"))
        )
        west_rafters.append(rw)
        east_rafters.append(re)

        # Tongue and Fork corner joint at the peak where West and East rafters meet
        arr_peak = CornerJointTimberArrangement(
            timber1=rw, timber1_end=TimberEnd.TOP,
            timber2=re, timber2_end=TimberEnd.TOP
        )
        j_peak = cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers(
            arrangement=arr_peak,
            tongue_thickness=inches(5) / scalar(3),  # 1/3 of rafter width (1.667")
            tongue_position=scalar(0)
        )
        rafter_peak_joints.append(j_peak)

    # Housing joints on West and East Top Plates receiving the rafters
    j_west_housing = cut_free_house_joint(
        housing_timber=plate_west,
        housed_timbers=west_rafters
    )
    j_east_housing = cut_free_house_joint(
        housing_timber=plate_east,
        housed_timbers=east_rafters
    )
    rafter_housing_joints = [j_west_housing, j_east_housing]

    # 14. 3x5 Collar Ties on Rafter Pair 2 (South) and Rafter Pair 8 (North).
    #
    #  Spec: 3" thick (in Y) × 5" high (in Z).
    #  Placement: Attached 3' (36") down from the rafter peak along the 45° rafter axis.
    #  Alignments (shifted inside rafter 5" width profile):
    #  - South Collar Tie: FRONT face at Y = 0", BACK face at Y = 3" (Y bounds 0" to 3").
    #  - North Collar Tie: FRONT face at Y = 189", BACK face at Y = 192" (Y bounds 189" to 192").
    #  Joints: Barefaced pegged M&T joints (1.5" thick × 4" high × 4" deep, ¾" round peg).
    #  - South tenons flush with FRONT face (+0.75" offset).
    #  - North tenons flush with BACK face (-0.75" offset).

    collar_size = create_v2(inches(5), inches(3))  # 5" high in Z, 3" thick in Y
    collar_length = feet(3) * sqrt(2)  # Exact horizontal span (50.912")

    rw2 = west_rafters[1]   # Rafter Pair 2 (South gable bent)
    re2 = east_rafters[1]
    rw8 = west_rafters[7]   # Rafter Pair 8 (North gable bent)
    re8 = east_rafters[7]

    collar_south = attach_plane_aligned_timber(
        original_timber=rw2, size=collar_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.BACK,
        attached_timber_angle=pi / 4, attached_timber_length_or_target=collar_length,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        attached_timber_long_face_to_measure_to_for_length_position=TimberCenterline.CENTERLINE,
        length_position_measurement=feet(3),
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.LEFT,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.FRONT,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="South Collar Tie", tags=("beam", "collar"))
    )

    collar_north = attach_plane_aligned_timber(
        original_timber=rw8, size=collar_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.BACK,
        attached_timber_angle=pi / 4, attached_timber_length_or_target=collar_length,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        attached_timber_long_face_to_measure_to_for_length_position=TimberCenterline.CENTERLINE,
        length_position_measurement=feet(3),
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.RIGHT,
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.BACK,
        lateral_position_measurement=scalar(0),
        ticket=TimberTicket(path="North Collar Tie", tags=("beam", "collar"))
    )

    collar_tenon_size = create_v2(inches(4), inches(3, 2))  # 4" high in Z × 1.5" thick in Y
    collar_tenon_length = inches(4)
    collar_mortise_depth = inches(4)

    tenon_pos_south = create_v2(scalar(0), -inches(3, 4))  # Flush with BACK face (-0.75", inside face at Y=3")
    tenon_pos_north = create_v2(scalar(0), inches(3, 4))   # Flush with FRONT face (+0.75", inside face at Y=189")

    j_collar_sw2 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=rw2, butt_timber=collar_south, butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_size=collar_tenon_size, tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
        tenon_position=tenon_pos_south, peg_parameters=girt_peg_params,
        bore_mortise_perpendicular_to_face=True,
    )
    j_collar_se2 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=re2, butt_timber=collar_south, butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_size=collar_tenon_size, tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
        tenon_position=tenon_pos_south, peg_parameters=girt_peg_params,
        bore_mortise_perpendicular_to_face=True,
    )

    j_collar_nw8 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=rw8, butt_timber=collar_north, butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size=collar_tenon_size, tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
        tenon_position=tenon_pos_north, peg_parameters=girt_peg_params,
        bore_mortise_perpendicular_to_face=True,
    )
    j_collar_ne8 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=re8, butt_timber=collar_north, butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size=collar_tenon_size, tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
        tenon_position=tenon_pos_north, peg_parameters=girt_peg_params,
        bore_mortise_perpendicular_to_face=True,
    )
    collar_joints = [j_collar_sw2, j_collar_se2, j_collar_nw8, j_collar_ne8]

    # Compile the frame from all joints
    mudsill_joints = [joint_sw, joint_se, joint_ne, joint_nw]
    frame = Frame.from_joints(
        joints=(
            mudsill_joints + joist_joints + post_joints + top_plate_joints
            + tie_beam_joints + girt_joints + door_post_joints + south_girt_joints
            + brace_joints + rafter_peak_joints + rafter_housing_joints
            + collar_joints
        ),
        additional_unjointed_timbers=[],
        name="Timber Frame Shed Base"
    )
    
    from dataclasses import replace
    return replace(frame, footprints=[footprint])


# Expose build_shed_frame as the example for Kigumi viewer
example = build_shed_frame

if __name__ == "__main__":
    frame = build_shed_frame()
    print(f"Successfully built frame with {len(frame.cut_timbers)} timbers and {len(frame.accessories)} accessories:")
    for ct in frame.cut_timbers:
        print(f"  - {ct.timber.ticket.path} (Length: {float(ct.timber.length):.2f}m / {float(ct.timber.length) * 39.3701 / 12:.2f} ft)")
    for acc in frame.accessories:
        if isinstance(acc, Peg):
            print(f"  - Peg at {acc.transform.position}")
