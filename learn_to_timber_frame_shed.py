"""
Timber Frame Shed - Base, Floor Joists, and Mudsill Joints
"""

from kumiki import *
from kumiki.timber import Frame, CutTimber, PegShape
from kumiki.construction import attach_face_aligned_timber, create_horizontal_timber_on_footprint, ButtJointTimberArrangement
from kumiki.footprint import Footprint, FootprintLocation
from kumiki.ticket import TimberTicket
from kumiki.joints.workshop.shavings import SimplePegParameters
from kumiki.joints.workshop.butt_joints import (
    cut_mortise_and_tenon_joint_on_face_aligned_timbers,
    cut_dropin_housed_butt_joint
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
    footprint = Footprint(footprint_corners)

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
        joint_east = cut_dropin_housed_butt_joint(
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
        joint_west = cut_dropin_housed_butt_joint(
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

    # Compile the frame from all mudsill corner joints and joist joints
    mudsill_joints = [joint_sw, joint_se, joint_ne, joint_nw]
    frame = Frame.from_joints(
        joints=mudsill_joints + joist_joints,
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
        print(f"  - Peg at {acc.transform.position}")
