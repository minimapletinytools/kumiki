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
    cut_dropin_housed_butt_joint_on_face_aligned_timbers
)
from kumiki.joints.workshop.mortise_and_tenon_joints import (
    cut_mortise_and_tenon_joint_on_face_aligned_timbers,
)
from kumiki.timber import Timber, TimberLongEdge, TimberLongFace, SomeTimberFace

OPPOSITE_LONG_FACE = {
    TimberLongFace.RIGHT: TimberLongFace.LEFT,
    TimberLongFace.LEFT: TimberLongFace.RIGHT,
    TimberLongFace.FRONT: TimberLongFace.BACK,
    TimberLongFace.BACK: TimberLongFace.FRONT,
}

def make_timber_imperfect_opposite_edge(
    timber: PerfectTimberWithin,
    reference_edge: Union[TimberLongEdge, Tuple[SomeTimberFace, SomeTimberFace]],
    extra_amount: Numeric = inches(1,2)
) -> Timber:
    """
    Returns a Timber whose actual cross-sectional size is enlarged by `extra_amount` (default 1/2")
    on the faces opposite to the specified `reference_edge`.

    Args:
        timber: The base PerfectTimberWithin (or Timber).
        reference_edge: The TimberLongEdge (or tuple of two adjacent faces) defining the reference edge.
        extra_amount: The additional thickness to add to the opposite faces (default 1/2").

    Returns:
        A new Timber instance with asymmetric rough_half_sizes.
    """
    w_half = timber.size[0] / scalar(2)
    h_half = timber.size[1] / scalar(2)

    right_half = w_half
    left_half = w_half
    front_half = h_half
    back_half = h_half

    if isinstance(reference_edge, TimberLongEdge):
        _edge_map = {
            TimberLongEdge.RIGHT_FRONT: (TimberLongFace.RIGHT, TimberLongFace.FRONT),
            TimberLongEdge.FRONT_LEFT:  (TimberLongFace.FRONT, TimberLongFace.LEFT),
            TimberLongEdge.LEFT_BACK:   (TimberLongFace.LEFT,  TimberLongFace.BACK),
            TimberLongEdge.BACK_RIGHT:  (TimberLongFace.BACK,  TimberLongFace.RIGHT),
        }
        ref_f1, ref_f2 = _edge_map[reference_edge]
    else:
        ref_f1, ref_f2 = reference_edge

    opp_f1 = OPPOSITE_LONG_FACE[TimberLongFace(ref_f1.value)]
    opp_f2 = OPPOSITE_LONG_FACE[TimberLongFace(ref_f2.value)]

    for opp in (opp_f1, opp_f2):
        if opp == TimberLongFace.RIGHT:
            right_half += extra_amount
        elif opp == TimberLongFace.LEFT:
            left_half += extra_amount
        elif opp == TimberLongFace.FRONT:
            front_half += extra_amount
        elif opp == TimberLongFace.BACK:
            back_half += extra_amount

    width_halves = create_v2(right_half, left_half)
    height_halves = create_v2(front_half, back_half)

    return Timber.from_perfect_timber_within(timber, rough_half_sizes=(width_halves, height_halves))

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
length_feet = 16
base_length = feet(length_feet)  # North-South length (16 feet)

# Number of floor joists spanning between the East and West mudsills.
# Evenly spaced along the mudsill length (base_length / (num_joists + 1) per gap),
# leaving one spacing gap between the first/last joist and each mudsill end so the
# joists clear the corner-post mortises there.
# The middle 1 joist (if num_joists is odd) or 2 joists (if even) use a pegged
# mortise-and-tenon joint; the rest use a drop-in housed butt joint.
num_joists = length_feet // 3

# Number of rafter pairs (each pair = one West + one East rafter meeting at the ridge).
# The outer 2 rafter pairs on each side keep their existing alignment:
#   - the outermost pair stays flush with the top-plate overhang end
#   - the 2nd pair stays aligned with the mudsill end (where the corner post /
#     collar tie sits, the "gable bent")
# The remaining pairs are evenly spaced between the two gable-bent pairs.
# Must be >= 4 (2 aligned pairs on each side).
num_rafter_pairs = length_feet // 2 + 1

# Number of mid-wall posts on the East and West walls (in addition to the 4 corner
# posts), evenly spaced between the corner posts. Each mid post gets its own tie beam
# to its opposite-wall counterpart, and knee braces leaning into both of its
# neighboring bays. 0 removes mid posts entirely (a single long bay per wall).
num_ew_mid_posts = length_feet // 9

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
    tenon_width_relative_to_joint = inches(5)
    tenon_height_relative_to_joint = inches(1.5)
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
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
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
    # Evenly space num_joists joists along the mudsill length, leaving one spacing
    # gap between the first/last joist and each mudsill end.
    joist_spacing = base_length / scalar(num_joists + 1)
    for i in range(1, num_joists + 1):
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

    # Middle joist(s) (1 if num_joists is odd, 2 if even) are joined with a mortise
    # and tenon joint; every other joist uses a drop-in housed butt joint.
    # - M&T Tenon: 1.5" thick (vertical/local X), 5" wide (horizontal/local Y)
    # - Position: bottom of the tenon is 4.5" below the top of the sill.
    #   Since top face is LEFT (local -X at -3.5"), the bottom of the tenon is at local X = +1.0"
    #   (which is 4.5" below -3.5").
    #   Tenon thickness is 1.5", so the tenon spans from local X = -0.5" to +1.0".
    #   Center of the tenon is at local X = +0.25" (+1/4" offset).
    # - Butt joint: joist extends 3" into sills, so housing_length = 3", housing_width = 5"
    #   (width of joist), housing_depth = 4.5" (pocket depth; remaining 2.5" of the 7" joist is cut away).
    joist_tenon_width_relative_to_joint = inches(5)
    joist_tenon_height_relative_to_joint = inches(1.5)
    joist_tenon_length = inches(3)
    joist_mortise_depth = inches(13, 4) # 3.25"
    joist_tenon_position = create_v2(inches(1, 4), scalar(0)) # +0.25" local X (depth to bottom is 4.5")

    if num_joists % 2 == 1:
        mortise_and_tenon_joist_indices = {num_joists // 2}
    else:
        mortise_and_tenon_joist_indices = {num_joists // 2 - 1, num_joists // 2}

    for idx, joist in enumerate(joists):
        if idx in mortise_and_tenon_joist_indices:
            joint_east = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
                arrangement=ButtJointTimberArrangement(
                    receiving_timber=east_mudsill,
                    butt_timber=joist,
                    butt_timber_end=TimberEnd.BOTTOM,
                    front_face_on_butt_timber=TimberLongFace.LEFT,
                ),
                tenon_width_relative_to_joint=joist_tenon_width_relative_to_joint,
                tenon_height_relative_to_joint=joist_tenon_height_relative_to_joint,
                tenon_length=joist_tenon_length,
                mortise_depth=joist_mortise_depth,
                tenon_position=joist_tenon_position,
                peg_parameters=peg_params,
            )
            joint_west = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
                arrangement=ButtJointTimberArrangement(
                    receiving_timber=west_mudsill,
                    butt_timber=joist,
                    butt_timber_end=TimberEnd.TOP,
                    front_face_on_butt_timber=TimberLongFace.LEFT,
                ),
                tenon_width_relative_to_joint=joist_tenon_width_relative_to_joint,
                tenon_height_relative_to_joint=joist_tenon_height_relative_to_joint,
                tenon_length=joist_tenon_length,
                mortise_depth=joist_mortise_depth,
                tenon_position=joist_tenon_position,
                peg_parameters=peg_params,
            )
        else:
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

    # Tenon parameters for post-to-mudsill joints: width=6.5" parallel to mudsill, height=1.5" perpendicular to mudsill.
    post_tenon_width_relative_to_joint  = inches(13, 2)
    post_tenon_height_relative_to_joint = inches(3, 2)
    post_tenon_length   = inches(3)                                # 3" deep tenon
    post_mortise_depth  = inches(13, 4)                            # 3.25" mortise (+ 0.25" clearance)
    # -1.25" in local Y: centers tenon 2.25" from the mudsill outside edge → 1.5" gap
    post_tenon_position = create_v2(scalar(0), -inches(5, 4))

    # Tenon parameters for SW and NE corner posts, which connect to the E/W mudsills
    # via their local X axis (thickness in local X, width in local Y).
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

    # --- Mid-wall posts: East and West sides, evenly spaced between the corner posts ---
    # num_ew_mid_posts posts per wall divide it into (num_ew_mid_posts + 1) equal bays.
    # Posts are paired south-to-north by index (west_mid_posts[i] <-> east_mid_posts[i]),
    # e.g. with 1 mid post per wall (the original design) each sits at the 8' midpoint of
    # the 16' wall.
    # create_vertical_timber_on_footprint_side measures distance_along_side from the side's
    # start corner: the East mudsill's side (index 1) runs South->North (corner 1 -> corner 2),
    # but the West mudsill's side (index 3) runs North->South (corner 3 -> corner 0) -- so the
    # same south-relative Y position requires *reversed* distance_along_side on the West side.
    def _build_mid_wall_posts(footprint_side_index, ticket_prefix, measure_from_south):
        posts = []
        for i in range(1, num_ew_mid_posts + 1):
            y_from_south = base_length * scalar(i) / scalar(num_ew_mid_posts + 1)
            distance_along_side = y_from_south if measure_from_south else (base_length - y_from_south)
            posts.append(create_vertical_timber_on_footprint_side(
                footprint, footprint_side_index, distance_along_side, post_height, FootprintLocation.INSIDE, post_size,
                ticket=TimberTicket(path=f"{ticket_prefix}-mid-post-{i}", tags=("post",))
            ))
        return posts

    east_mid_posts = _build_mid_wall_posts(1, "east", measure_from_south=True)
    west_mid_posts = _build_mid_wall_posts(3, "west", measure_from_south=False)

    # Enlarge posts by 1/2" on the faces opposite to their reference edges:
    # - Corner posts reference edge: outside corner (LEFT_BACK)
    # - West mid posts reference edge: north outside corner (LEFT_BACK)
    # - East mid posts reference edge: north outside corner (BACK_RIGHT)
    # (These are constant per post-construction method/side, independent of position along the wall.)
    post_sw = make_timber_imperfect_opposite_edge(post_sw, TimberLongEdge.LEFT_BACK)
    post_se = make_timber_imperfect_opposite_edge(post_se, TimberLongEdge.LEFT_BACK)
    post_ne = make_timber_imperfect_opposite_edge(post_ne, TimberLongEdge.LEFT_BACK)
    post_nw = make_timber_imperfect_opposite_edge(post_nw, TimberLongEdge.LEFT_BACK)
    west_mid_posts = [make_timber_imperfect_opposite_edge(p, TimberLongEdge.LEFT_BACK) for p in west_mid_posts]
    east_mid_posts = [make_timber_imperfect_opposite_edge(p, TimberLongEdge.BACK_RIGHT) for p in east_mid_posts]

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
        tenon_width_relative_to_joint=post_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=post_tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=post_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=post_tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=post_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=post_tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=post_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=post_tenon_height_relative_to_joint,
        tenon_length=post_tenon_length,
        mortise_depth=post_mortise_depth,
        tenon_position=post_tenon_position,
    )

    # Mid-wall posts → their own wall's mudsill (same tenon spec as the SE/NW corner posts,
    # regardless of position along the wall).
    mid_post_joints = []
    for post in east_mid_posts:
        mid_post_joints.append(cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=east_mudsill,
                butt_timber=post,
                butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=None,
            ),
            tenon_width_relative_to_joint=post_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=post_tenon_height_relative_to_joint,
            tenon_length=post_tenon_length,
            mortise_depth=post_mortise_depth,
            tenon_position=post_tenon_position,
        ))
    for post in west_mid_posts:
        mid_post_joints.append(cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=west_mudsill,
                butt_timber=post,
                butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=None,
            ),
            tenon_width_relative_to_joint=post_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=post_tenon_height_relative_to_joint,
            tenon_length=post_tenon_length,
            mortise_depth=post_mortise_depth,
            tenon_position=post_tenon_position,
        ))

    post_joints = [
        joint_post_sw, joint_post_se, joint_post_ne, joint_post_nw,
    ] + mid_post_joints

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

    top_tenon_width_relative_to_joint = inches(13, 2)
    top_tenon_height_relative_to_joint = inches(3, 2)

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
        tenon_width_relative_to_joint=top_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=top_tenon_height_relative_to_joint,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    # West mid posts share the NW post's local-axis convention (BACK = −X_global),
    # regardless of position along the wall.
    west_mid_top_plate_joints = [
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=plate_west,
                butt_timber=post,
                butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.BACK,   # −localY = −X_global
            ),
            tenon_width_relative_to_joint=top_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=top_tenon_height_relative_to_joint,
            tenon_length=top_plate_tenon_length,
            mortise_depth=top_plate_mortise_depth,
            peg_parameters=top_peg_params,
        )
        for post in west_mid_posts
    ]

    joint_top_nw = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_west,
            butt_timber=post_nw,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.BACK,   # −localY = −X_global
        ),
        tenon_width_relative_to_joint=top_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=top_tenon_height_relative_to_joint,
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
        tenon_width_relative_to_joint=top_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=top_tenon_height_relative_to_joint,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    # East mid posts share the SE post's local-axis convention (FRONT = −X_global),
    # regardless of position along the wall.
    east_mid_top_plate_joints = [
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=plate_east,
                butt_timber=post,
                butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,  # +localY = −X_global
            ),
            tenon_width_relative_to_joint=top_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=top_tenon_height_relative_to_joint,
            tenon_length=top_plate_tenon_length,
            mortise_depth=top_plate_mortise_depth,
            peg_parameters=top_peg_params,
        )
        for post in east_mid_posts
    ]

    joint_top_ne = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=plate_east,
            butt_timber=post_ne,
            butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.RIGHT,  # +localX = −X_global
        ),
        tenon_width_relative_to_joint=top_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=top_tenon_height_relative_to_joint,
        tenon_length=top_plate_tenon_length,
        mortise_depth=top_plate_mortise_depth,
        peg_parameters=top_peg_params,
    )

    top_plate_joints = (
        [joint_top_sw] + west_mid_top_plate_joints + [joint_top_nw]
        + [joint_top_se] + east_mid_top_plate_joints + [joint_top_ne]
    )

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

    tie_beam_pairs = (
        [(post_sw, post_se, "South Tie Beam")]
        + [
            (west_mid_posts[i], east_mid_posts[i], f"Mid Tie Beam {i + 1}")
            for i in range(num_ew_mid_posts)
        ]
        + [(post_nw, post_ne, "North Tie Beam")]
    )

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
                top_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
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
                top_face_on_butt_timber=TimberLongFace.RIGHT,
            ),
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

    # West/East wall girts: walk [south corner post, mid posts..., north corner post] and
    # place one girt per gap. The girt's local-axis convention depends only on whether its
    # origin post is the south corner post or a mid post (constant regardless of position
    # along the wall) -- confirmed by the original 1-mid-post design, where the "South Girt"
    # (origin = corner post) and "North Girt" (origin = mid post) used different conventions.
    west_girt_origin_conv = {
        "corner": dict(long_face=TimberLongFace.FRONT, lat_from=TimberFace.LEFT, lat_to=TimberLongFace.BACK),
        "mid": dict(long_face=TimberLongFace.LEFT, lat_from=TimberFace.BACK, lat_to=TimberLongFace.BACK),
    }
    east_girt_origin_conv = {
        "corner": dict(long_face=TimberLongFace.RIGHT, lat_from=TimberFace.BACK, lat_to=TimberLongFace.FRONT),
        "mid": dict(long_face=TimberLongFace.RIGHT, lat_from=TimberFace.BACK, lat_to=TimberLongFace.FRONT),
    }

    def _build_wall_girts(south_post, mid_posts, north_post, origin_conv, name_prefix):
        posts_in_order = [south_post] + list(mid_posts) + [north_post]
        girts = []
        for i in range(len(posts_in_order) - 1):
            origin_post = posts_in_order[i]
            target_post = posts_in_order[i + 1]
            conv = origin_conv["corner"] if i == 0 else origin_conv["mid"]
            girt = attach_face_aligned_timber(
                original_timber=origin_post,
                size=girt_size,
                original_timber_long_face_that_attached_timber_points_to=conv["long_face"],
                attached_timber_length_or_target=target_post,
                attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
                original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
                length_position_measurement=girt_centerline_z,
                original_timber_face_to_measure_from_for_lateral_position=conv["lat_from"],
                attached_timber_long_face_to_measure_to_for_lateral_position=conv["lat_to"],
                lateral_position_measurement=scalar(0),
                ticket=TimberTicket(path=f"{name_prefix} Girt {i + 1}", tags=("beam", "girt"))
            )
            girts.append((girt, origin_post, target_post))
        return girts

    west_girts = _build_wall_girts(post_sw, west_mid_posts, post_nw, west_girt_origin_conv, "West")
    east_girts = _build_wall_girts(post_se, east_mid_posts, post_ne, east_girt_origin_conv, "East")

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

    # Enlarge girts by 1/2" on faces opposite to upper outside reference edge relative to footprint:
    # - West girts reference edge: upper outside edge (BACK_RIGHT)
    # - East girts reference edge: upper outside edge (RIGHT_FRONT)
    # - North girt reference edge: upper outside edge (BACK_RIGHT)
    west_girts = [
        (make_timber_imperfect_opposite_edge(g, TimberLongEdge.BACK_RIGHT), origin, target)
        for g, origin, target in west_girts
    ]
    east_girts = [
        (make_timber_imperfect_opposite_edge(g, TimberLongEdge.RIGHT_FRONT), origin, target)
        for g, origin, target in east_girts
    ]
    n_girt = make_timber_imperfect_opposite_edge(n_girt, TimberLongEdge.BACK_RIGHT)

    # --- Barefaced Mortise & Tenon Joints with Round Pegs for Wall Girts ---
    #
    # Spec: 1.5" thick × 4" wide (Z axis) × 4" deep into post. Round pegs.
    # Barefaced: tenon face is flush with the inside face of the girt (shoulder on outside face).
    girt_tenon_width_relative_to_joint = inches(4)
    girt_tenon_height_relative_to_joint = inches(3, 2)
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

    girt_joint_specs = []
    for girt, origin_post, target_post in west_girts:
        girt_joint_specs.append((girt, origin_post, TimberEnd.BOTTOM, west_girt_tenon_pos))
        girt_joint_specs.append((girt, target_post, TimberEnd.TOP, west_girt_tenon_pos))
    for girt, origin_post, target_post in east_girts:
        girt_joint_specs.append((girt, origin_post, TimberEnd.BOTTOM, east_girt_tenon_pos))
        girt_joint_specs.append((girt, target_post, TimberEnd.TOP, east_girt_tenon_pos))
    girt_joint_specs.extend([
        (n_girt, post_nw, TimberEnd.BOTTOM, north_girt_tenon_pos),
        (n_girt, post_ne, TimberEnd.TOP, north_girt_tenon_pos),
    ])

    girt_joints = []
    for girt, post, end, pos in girt_joint_specs:
        j = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post,
                butt_timber=girt,
                butt_timber_end=end,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_width_relative_to_joint=girt_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=girt_tenon_height_relative_to_joint,
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
    #  Symmetry: centered around X = base_width / 2 with a 3' 6" (42") door opening gap.

    door_post_size = create_v2(inches(5), inches(4))
    door_opening_width = inches(42)  # 3'6" clear opening between door posts
    # Centerline offset from the footprint centerline to each door post's centerline:
    # half the opening plus half the post's own width (door_post_size[0]).
    door_post_centerline_offset = door_opening_width / scalar(2) + door_post_size[0] / scalar(2)
    west_door_post_x = base_width / scalar(2) - door_post_centerline_offset
    east_door_post_x = base_width / scalar(2) + door_post_centerline_offset

    west_door_post = attach_face_aligned_timber(
        original_timber=south_mudsill,
        size=door_post_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=south_tie_beam,
        attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        length_position_measurement=west_door_post_x,
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
        length_position_measurement=east_door_post_x,
        original_timber_face_to_measure_from_for_lateral_position=TimberFace.FRONT,  # Y=0 outside face
        attached_timber_long_face_to_measure_to_for_lateral_position=TimberLongFace.FRONT,
        lateral_position_measurement=inches(4),  # offset to sit from Y=0 to Y=4"
        ticket=TimberTicket(path="East Door Post", tags=("post", "door_post"))
    )

    # Barefaced M&T joints for door posts (bottom unpegged, top pegged)
    dp_tenon_width_relative_to_joint = inches(4)
    dp_tenon_height_relative_to_joint = inches(3, 2)
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
            tenon_width_relative_to_joint=dp_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=dp_tenon_height_relative_to_joint,
            tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
            tenon_position=dp_tenon_pos, peg_parameters=None,
        ),
        # West Door Post top (tie beam) - PEGGED
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=south_tie_beam, butt_timber=west_door_post, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_width_relative_to_joint=dp_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=dp_tenon_height_relative_to_joint,
            tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
            tenon_position=dp_tenon_pos, peg_parameters=girt_peg_params,
        ),
        # East Door Post bottom (mudsill) - UNPEGGED
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=south_mudsill, butt_timber=east_door_post, butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_width_relative_to_joint=dp_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=dp_tenon_height_relative_to_joint,
            tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
            tenon_position=dp_tenon_pos, peg_parameters=None,
        ),
        # East Door Post top (tie beam) - PEGGED
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=south_tie_beam, butt_timber=east_door_post, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_width_relative_to_joint=dp_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=dp_tenon_height_relative_to_joint,
            tenon_length=dp_tenon_length, mortise_depth=dp_mortise_depth,
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

    # Enlarge south girts by 1/2" on faces opposite to upper outside reference edge relative to footprint:
    # - South West girt reference edge: upper outside edge (RIGHT_FRONT)
    # - South East girt reference edge: upper outside edge (BACK_RIGHT)
    s_w_girt = make_timber_imperfect_opposite_edge(s_w_girt, TimberLongEdge.RIGHT_FRONT)
    s_e_girt = make_timber_imperfect_opposite_edge(s_e_girt, TimberLongEdge.BACK_RIGHT)

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
            tenon_width_relative_to_joint=girt_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=girt_tenon_height_relative_to_joint,
            tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
            tenon_position=sw_bareface_pos, peg_parameters=girt_peg_params,
        ),
        # South West Girt -> West Door Post (CENTERED, pegged)
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=west_door_post, butt_timber=s_w_girt, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_width_relative_to_joint=girt_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=girt_tenon_height_relative_to_joint,
            tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
            tenon_position=centered_pos, peg_parameters=girt_peg_params,
        ),
        # South East Girt -> SE post (barefaced, pegged)
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post_se, butt_timber=s_e_girt, butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.BACK,
            ),
            tenon_width_relative_to_joint=girt_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=girt_tenon_height_relative_to_joint,
            tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
            tenon_position=se_bareface_pos, peg_parameters=girt_peg_params,
        ),
        # South East Girt -> East Door Post (CENTERED, pegged)
        cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=east_door_post, butt_timber=s_e_girt, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.BACK,
            ),
            tenon_width_relative_to_joint=girt_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=girt_tenon_height_relative_to_joint,
            tenon_length=girt_tenon_length, mortise_depth=girt_mortise_depth,
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

    brace_tenon_width_relative_to_joint = inches(7, 2)
    brace_tenon_height_relative_to_joint = inches(3, 2)
    brace_tenon_length = inches(4)
    brace_mortise_depth = inches(7, 2)  # 3.5" orthogonal depth into mortise face

    pos_pos = create_v2(scalar(0), inches(3, 4))   # +0.75" offset when FRONT is inside face
    pos_neg = create_v2(scalar(0), -inches(3, 4))  # -0.75" offset when BACK is inside face

    # West/East wall knee braces: the south corner post and north corner post each get a
    # single brace leaning into their one adjacent bay; every mid post gets 2 braces (one
    # leaning into each of its neighboring bays). Which of these 4 roles a post plays
    # determines its brace's facing/lateral/peg conventions -- constant regardless of how
    # many mid posts there are or which one a given post is.
    west_south_corner_conv = dict(facing_face=TimberLongFace.FRONT, orig_lat=TimberFace.LEFT, att_lat=TimberLongFace.BACK, peg_face=TimberLongFace.FRONT, tenon_pos=pos_pos)
    west_mid_south_conv    = dict(facing_face=TimberLongFace.RIGHT, orig_lat=TimberFace.BACK, att_lat=TimberLongFace.FRONT, peg_face=TimberLongFace.FRONT, tenon_pos=pos_neg)
    west_mid_north_conv    = dict(facing_face=TimberLongFace.LEFT, orig_lat=TimberFace.BACK, att_lat=TimberLongFace.BACK, peg_face=TimberLongFace.FRONT, tenon_pos=pos_pos)
    west_north_corner_conv = dict(facing_face=TimberLongFace.RIGHT, orig_lat=TimberFace.BACK, att_lat=TimberLongFace.FRONT, peg_face=TimberLongFace.FRONT, tenon_pos=pos_neg)

    east_south_corner_conv = dict(facing_face=TimberLongFace.RIGHT, orig_lat=TimberFace.BACK, att_lat=TimberLongFace.FRONT, peg_face=TimberLongFace.BACK, tenon_pos=pos_neg)
    east_mid_south_conv    = dict(facing_face=TimberLongFace.LEFT, orig_lat=TimberFace.BACK, att_lat=TimberLongFace.BACK, peg_face=TimberLongFace.BACK, tenon_pos=pos_pos)
    east_mid_north_conv    = dict(facing_face=TimberLongFace.RIGHT, orig_lat=TimberFace.BACK, att_lat=TimberLongFace.FRONT, peg_face=TimberLongFace.BACK, tenon_pos=pos_neg)
    east_north_corner_conv = dict(facing_face=TimberLongFace.FRONT, orig_lat=TimberFace.LEFT, att_lat=TimberLongFace.BACK, peg_face=TimberLongFace.BACK, tenon_pos=pos_pos)

    def _wall_brace_specs(south_post, mid_posts, north_post, plate,
                           south_conv, mid_south_conv, mid_north_conv, north_conv,
                           wall_label, south_name, north_name):
        specs = [
            (south_post, south_conv["facing_face"], plate, plate_brace_length_pos,
             south_conv["orig_lat"], south_conv["att_lat"], south_name,
             south_conv["peg_face"], south_conv["tenon_pos"]),
        ]
        for i, post in enumerate(mid_posts, start=1):
            specs.append((post, mid_south_conv["facing_face"], plate, plate_brace_length_pos,
                          mid_south_conv["orig_lat"], mid_south_conv["att_lat"], f"{wall_label} Mid {i} South Brace",
                          mid_south_conv["peg_face"], mid_south_conv["tenon_pos"]))
            specs.append((post, mid_north_conv["facing_face"], plate, plate_brace_length_pos,
                          mid_north_conv["orig_lat"], mid_north_conv["att_lat"], f"{wall_label} Mid {i} North Brace",
                          mid_north_conv["peg_face"], mid_north_conv["tenon_pos"]))
        specs.append((north_post, north_conv["facing_face"], plate, plate_brace_length_pos,
                      north_conv["orig_lat"], north_conv["att_lat"], north_name,
                      north_conv["peg_face"], north_conv["tenon_pos"]))
        return specs

    west_brace_specs = _wall_brace_specs(
        post_sw, west_mid_posts, post_nw, plate_west,
        west_south_corner_conv, west_mid_south_conv, west_mid_north_conv, west_north_corner_conv,
        "West", "West SW Brace", "West NW Brace",
    )
    east_brace_specs = _wall_brace_specs(
        post_se, east_mid_posts, post_ne, plate_east,
        east_south_corner_conv, east_mid_south_conv, east_mid_north_conv, east_north_corner_conv,
        "East", "East SE Brace", "East NE Brace",
    )

    brace_specs = west_brace_specs + east_brace_specs + [
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
            # TODO update this to use target timber
            attached_timber_length_or_target=b_length,
            attached_timber_stickout=Stickout.symmetric(inches(0), StickoutReference.INSIDE),
            original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
            attached_timber_long_face_to_measure_to_for_length_position=TimberCenterline.CENTERLINE,
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
            tenon_width_relative_to_joint=brace_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=brace_tenon_height_relative_to_joint,
            tenon_length=brace_tenon_length, mortise_depth=brace_mortise_depth,
            tenon_position=tenon_pos, peg_parameters=girt_peg_params,
            bore_mortise_perpendicular_to_face=True,
        )
        j_beam = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=target_beam, butt_timber=b, butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=peg_face,
            ),
            tenon_width_relative_to_joint=brace_tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=brace_tenon_height_relative_to_joint,
            tenon_length=brace_tenon_length, mortise_depth=brace_mortise_depth,
            tenon_position=tenon_pos, peg_parameters=girt_peg_params,
            bore_mortise_perpendicular_to_face=True,
        )
        brace_joints.extend([j_post, j_beam])

    # 13. num_rafter_pairs Pairs of 5x5 Rafters (Pitch: 45°, Overhang: 18", 5"x5" section).
    #
    #  Geometry:
    #  - Rafter bottom face intersects West/East Top Plate outside face (X=0 / X=base_width) 3.5" below plate top (Z=116.5").
    #  - 45° slope (rise = 1, run = 1). Rafters meet at roof peak X = base_width / 2 (Z = 188.5").
    #  - Rafters extend 18" beyond plate outside face. Total horizontal span = base_width/2 + 18" per side.
    #
    #  Y-spacing (along base_length): the outer 2 pairs on each side keep their existing alignment —
    #  the outermost pair flush with the top-plate overhang end, the 2nd pair aligned with the mudsill
    #  end (the "gable bent", where the corner post / collar tie sits). The remaining pairs are evenly
    #  spaced between the two gable-bent pairs.
    #
    #  Joints:
    #  - Peak Joint: Tongue and fork corner joint between West Rafter and East Rafter at top ends.
    #  - Plate Housing Joint: Generic housing cut on West/East Top Plates receiving the crossing rafters.

    from kumiki.rule import Orientation
    from kumiki.joints.workshop.corner_joints import (
        cut_tongue_and_fork_corner_joint_on_plane_aligned_timbers,
        CornerJointTimberArrangement,
    )
    from kumiki.joints.workshop.free_joints import cut_free_house_joint

    if num_rafter_pairs < 4:
        raise ValueError("num_rafter_pairs must be >= 4 (2 aligned rafter pairs on each side)")

    rafter_size = create_v2(inches(5), inches(5))
    rafter_horizontal_half_span = base_width / scalar(2) + inches(18)
    rafter_length = rafter_horizontal_half_span * sqrt(2)

    rafter_half_width = rafter_size[1] / scalar(2)  # 2.5", half the rafter's Y-thickness
    plate_y_north_end = plate_y_south_end + plate_length
    gable_south_y = rafter_half_width               # aligned with south mudsill end
    gable_north_y = base_length - rafter_half_width  # aligned with north mudsill end
    num_middle_aligned = num_rafter_pairs - 2        # the 2 gable-bent pairs + interior pairs
    interior_spacing = (gable_north_y - gable_south_y) / scalar(num_middle_aligned - 1)
    y_centerlines = (
        [plate_y_south_end + rafter_half_width]
        + [gable_south_y + scalar(k) * interior_spacing for k in range(num_middle_aligned)]
        + [plate_y_north_end - rafter_half_width]
    )

    u_west = Matrix([sqrt(2) / scalar(2), scalar(0), sqrt(2) / scalar(2)])
    u_east = Matrix([-sqrt(2) / scalar(2), scalar(0), sqrt(2) / scalar(2)])
    w_dir = Matrix([scalar(0), scalar(1), scalar(0)])

    orient_west = Orientation.from_z_and_x(u_west, w_dir)
    orient_east = Orientation.from_z_and_x(u_east, w_dir)

    start_x_west = -inches(18)
    start_z_west = inches(233, 2) + (inches(5) / scalar(2)) / sqrt(2) - inches(18)

    start_x_east = base_width + inches(18)
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

    # 14. 3x5 Collar Ties on Rafter Pair 2 (South gable bent) and the 2nd-to-last Rafter Pair (North gable bent).
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

    rw2 = west_rafters[1]                     # Rafter Pair 2 (South gable bent)
    re2 = east_rafters[1]
    rw8 = west_rafters[num_rafter_pairs - 2]  # 2nd-to-last Rafter Pair (North gable bent)
    re8 = east_rafters[num_rafter_pairs - 2]

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

    collar_tenon_width_relative_to_joint = inches(4)
    collar_tenon_height_relative_to_joint = inches(3, 2)
    collar_tenon_length = inches(4)
    collar_mortise_depth = inches(4)

    tenon_pos_south = create_v2(scalar(0), -inches(3, 4))  # Flush with BACK face (-0.75", inside face at Y=3")
    tenon_pos_north = create_v2(scalar(0), inches(3, 4))   # Flush with FRONT face (+0.75", inside face at Y=189")

    j_collar_sw2 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=rw2, butt_timber=collar_south, butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_width_relative_to_joint=collar_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=collar_tenon_height_relative_to_joint,
        tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
        tenon_position=tenon_pos_south, peg_parameters=girt_peg_params,
        bore_mortise_perpendicular_to_face=True,
    )
    j_collar_se2 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=re2, butt_timber=collar_south, butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.FRONT,
        ),
        tenon_width_relative_to_joint=collar_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=collar_tenon_height_relative_to_joint,
        tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
        tenon_position=tenon_pos_south, peg_parameters=girt_peg_params,
        bore_mortise_perpendicular_to_face=True,
    )

    j_collar_nw8 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=rw8, butt_timber=collar_north, butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_width_relative_to_joint=collar_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=collar_tenon_height_relative_to_joint,
        tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
        tenon_position=tenon_pos_north, peg_parameters=girt_peg_params,
        bore_mortise_perpendicular_to_face=True,
    )
    j_collar_ne8 = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=ButtJointTimberArrangement(
            receiving_timber=re8, butt_timber=collar_north, butt_timber_end=TimberEnd.TOP,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_width_relative_to_joint=collar_tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=collar_tenon_height_relative_to_joint,
        tenon_length=collar_tenon_length, mortise_depth=collar_mortise_depth,
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
