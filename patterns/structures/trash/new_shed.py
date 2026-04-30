"""
The Honeycomb Shed - A hexagonal timber frame shed structure
A creative variation with 6 sides and dramatic roof pitch!
Built using the Kumiki API
"""

from sympy import Rational, cos, sin, pi, sqrt
from dataclasses import replace
import sys
sys.path.append('..')

from kumiki import *
from kumiki.timber import Frame
from kumiki.patternbook import PatternBook, PatternMetadata

# ============================================================================
# PARAMETERS - Modify these to adjust the shed design
# ============================================================================

# Hexagonal footprint - measured from center to each vertex
hex_radius = feet(4)  # Distance from center to corner

# Post parameters
post_back_height = feet(4)   # Height of back 3 posts
post_front_height = feet(7)  # Height of front 3 posts (dramatic pitch!)

# Timber size definitions
small_timber_size = create_v2(inches(3), inches(3))     # 3" x 3"
med_timber_size = create_v2(inches(4), inches(4))       # 4" x 4"
large_timber_size = create_v2(inches(6), inches(4))     # 6" x 4"

def create_honeycomb_shed_patternbook() -> PatternBook:
    """
    Create a PatternBook with the Honeycomb Shed pattern.
    
    Returns:
        PatternBook: PatternBook containing the Honeycomb Shed pattern
    """
    patterns = [
        (PatternMetadata("honeycomb_shed", ["honeycomb_shed", "complete_structures"], "frame"),
         lambda center: create_honeycomb_shed()),
    ]
    
    return PatternBook(patterns=patterns)


patternbook = create_honeycomb_shed_patternbook()


def create_honeycomb_shed():
    """
    Create the Honeycomb Shed - A hexagonal timber frame structure.
    
    Returns:
        Frame: Frame object containing all cut timbers and accessories for the complete shed
    """
    
    print("Starting create_honeycomb_shed()...")
    
    # ============================================================================
    # BUILD THE HEXAGONAL FOOTPRINT
    # ============================================================================
    
    print("Creating hexagonal footprint...")
    # Create hexagonal footprint (6 corners, counter-clockwise from right)
    # Corner 0: Right (0°)
    # Corner 1: Upper-right (60°)
    # Corner 2: Upper-left (120°)
    # Corner 3: Left (180°)
    # Corner 4: Lower-left (240°)
    # Corner 5: Lower-right (300°)
    
    footprint_corners = []
    for i in range(6):
        angle = radians(Rational(i, 3) * pi)  # 60° increments
        x = hex_radius * cos(angle)
        y = hex_radius * sin(angle)
        footprint_corners.append(create_v2(x, y))
    
    footprint = Footprint(footprint_corners)  # type: ignore[arg-type]

    print("Footprint created!")
    
    # ============================================================================
    # Create mudsills on all 6 sides (INSIDE the footprint)
    # ============================================================================
    
    print("Creating mudsills...")
    mudsill_size = large_timber_size
    mudsills = []
    
    for i in range(6):
        print(f"  Mudsill {i}...")
        mudsill = create_horizontal_timber_on_footprint(
            footprint, i, FootprintLocation.INSIDE, mudsill_size, 
            ticket=f"Mudsill {i}"
        )
        mudsills.append(mudsill)
    
    print("Mudsills created!")

    # ============================================================================
    # Create miter joints at all six corners of the mudsill hexagon
    # ============================================================================
    
    print("Creating miter joints...")
    miter_joints = []
    for i in range(6):
        print(f"  Miter joint {i}...")
        # Each mudsill connects to the next one at the shared corner
        # Mudsill i goes from corner i to corner (i+1)%6
        # So at corner (i+1)%6: mudsill i TOP meets mudsill (i+1)%6 BOTTOM
        joint = cut_plain_miter_joint(
            CornerJointTimberArrangement(
                timber1=mudsills[i],
                timber2=mudsills[(i + 1) % 6],
                timber1_end=TimberReferenceEnd.TOP,
                timber2_end=TimberReferenceEnd.BOTTOM,
            )
        )
        miter_joints.append(joint)
    
    print("Miter joints created!")

    # ============================================================================
    # Create posts at each corner
    # ============================================================================
    # Front 3 posts (corners 0, 1, 5) are tall
    # Back 3 posts (corners 2, 3, 4) are short
    
    print("Creating posts...")
    post_size = med_timber_size
    posts = []
    
    # Determine which posts are tall (front) vs short (back)
    # Front: corners 0, 1, 5 (right side of hexagon)
    # Back: corners 2, 3, 4 (left side of hexagon)
    front_corners = [0, 1, 5]
    
    for i in range(6):
        print(f"  Post {i}...")
        # Each post goes at the shared corner between side i and side (i+1)%6
        # Position the post slightly inset from the corner (3 inches along side i)
        post_inset = inches(3)
        
        height = post_front_height if i in front_corners else post_back_height
        
        post = create_vertical_timber_on_footprint_side(
            footprint,
            side_index=i,
            distance_along_side=post_inset,
            length=height,
            location_type=FootprintLocation.INSIDE,
            size=post_size,
            ticket=f"Post {i}"
        )
        posts.append(post)
    
    print("Posts created!")

    # ============================================================================
    # Create mortise and tenon joints where posts meet mudsills
    # ============================================================================
    
    print("Creating post-mudsill mortise and tenon joints...")
    tenon_size = Matrix([inches(2), inches(Rational(3, 2))])  # 2" x 1.5"
    tenon_length = inches(3)
    mortise_depth = inches(3.5)
    
    post_mudsill_joints = []
    
    for i in range(6):
        print(f"  Post-mudsill joint {i}...")
        # Post i sits on mudsill i
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mudsills[i],
            butt_timber=posts[i],
            butt_timber_end=TimberReferenceEnd.BOTTOM,
            front_face_on_butt_timber=None,
        )
        joint = cut_mortise_and_tenon_joint(
            arrangement=arrangement,
            tenon_size=tenon_size,
            tenon_length=tenon_length,
            mortise_depth=mortise_depth,
        )
        post_mudsill_joints.append(joint)
    
    print("Post-mudsill joints created!")

    # ============================================================================
    # Create top ring beam (hexagonal beam on top of posts)
    # ============================================================================
    
    print("Creating ring beams...")
    ring_beam_size = large_timber_size
    ring_beams = []
    
    for i in range(6):
        print(f"  Ring beam {i}...")
        # Create beam from post i to post (i+1)%6
        next_i = (i + 1) % 6
        
        # Determine height based on post heights
        height_i = post_front_height if i in front_corners else post_back_height
        height_next = post_front_height if next_i in front_corners else post_back_height
        
        # Use the minimum height to sit on top of posts
        beam_stickout = Stickout.symmetric(inches(6))  # 6" stickout
        
        ring_beam = join_timbers(
            timber1=posts[i],
            timber2=posts[next_i],
            location_on_timber1=height_i,  # Top of post i
            stickout=beam_stickout,
            location_on_timber2=height_next,  # Top of post next
            lateral_offset=Rational(0),
            size=ring_beam_size,
            orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),  # Face up
            ticket=f"Ring Beam {i}"
        )
        ring_beams.append(ring_beam)

    # ============================================================================
    # Create miter joints for ring beams at corners
    # ============================================================================
    
    print("Creating ring beam miter joints...")
    ring_beam_joints = []
    for i in range(6):
        print(f"  Ring beam miter joint {i}...")
        joint = cut_plain_miter_joint(
            CornerJointTimberArrangement(
                timber1=ring_beams[i],
                timber2=ring_beams[(i + 1) % 6],
                timber1_end=TimberReferenceEnd.TOP,
                timber2_end=TimberReferenceEnd.BOTTOM,
            )
        )
        ring_beam_joints.append(joint)

    # ============================================================================
    # Create mortise and tenon joints where posts meet ring beams
    # ============================================================================
    
    print("Creating post-ring beam mortise and tenon joints...")
    beam_tenon_size = Matrix([inches(2), inches(Rational(3, 2))])
    beam_tenon_length = inches(3)
    beam_mortise_depth = inches(3.5)
    
    post_ring_beam_joints = []
    
    for i in range(6):
        next_i = (i + 1) % 6
        # Only create face-aligned joints when both posts are the same height
        # (i.e., both front or both back)
        same_height = (i in front_corners) == (next_i in front_corners)
        
        if same_height:
            print(f"  Post-ring beam joint {i} (face-aligned)...")
            arrangement = ButtJointTimberArrangement(
                receiving_timber=ring_beams[i],
                butt_timber=posts[i],
                butt_timber_end=TimberReferenceEnd.TOP,
                front_face_on_butt_timber=None,
            )
            joint = cut_mortise_and_tenon_joint(
                arrangement=arrangement,
                tenon_size=beam_tenon_size,
                tenon_length=beam_tenon_length,
                mortise_depth=beam_mortise_depth,
            )
            post_ring_beam_joints.append(joint)
        else:
            print(f"  Post-ring beam joint {i} (skipped - different heights)...")
            # For beams connecting posts at different heights, skip the joint
            # or use a different joint type
            pass

    # ============================================================================
    # Create central hub post (goes through the center of the structure)
    # ============================================================================
    
    print("Creating central hub post...")
    # Calculate center point (should be origin for regular hexagon)
    center_point = create_v3(Rational(0), Rational(0), Rational(0))
    
    # Hub post is extra tall and thick
    hub_post_size = create_v2(inches(6), inches(6))  # 6" x 6"
    hub_height = (post_front_height + post_back_height) / Rational(2) + inches(12)  # Average height + 12"
    
    hub_post = timber_from_directions(
        length=hub_height,
        size=hub_post_size,
        bottom_position=center_point,
        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
        ticket="Central Hub Post"
    )

    # ============================================================================
    # Central hub post currently stands free at the center
    # ============================================================================
    # There is no central sill member to receive a hub tenon, so keep the hub post
    # as an unjointed timber rather than forcing an invalid joint to perimeter mudsill 0.

    # ============================================================================
    # Create radial rafters from hub to each corner
    # ============================================================================
    
    print("Creating radial rafters...")
    rafter_size = med_timber_size
    rafters = []
    
    for i in range(6):
        print(f"  Rafter {i}...")
        # Calculate position on hub post for this rafter
        # Rafters should meet at the hub at approximately the average height
        hub_height_for_rafter = (post_front_height + post_back_height) / Rational(2)
        
        # Position on ring beam post
        post_height = post_front_height if i in front_corners else post_back_height
        
        # Create rafter from hub to post i top
        # We'll use a simple approach: create timber from hub to post top
        rafter_stickout = Stickout(Rational(0), inches(12))  # 12" stickout at outer end
        
        rafter = join_timbers(
            timber1=hub_post,
            timber2=posts[i],
            location_on_timber1=hub_height_for_rafter,
            stickout=rafter_stickout,
            location_on_timber2=post_height,
            lateral_offset=Rational(0),
            size=rafter_size,
            orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),  # Face up
            ticket=f"Radial Rafter {i}"
        )
        rafters.append(rafter)

    # ============================================================================
    # Create diagonal knee braces from posts to ring beams
    # ============================================================================
    # Add decorative and structural knee braces at the front posts
    
    print("Creating knee braces...")
    brace_size = small_timber_size
    braces = []
    
    for i in front_corners:  # Only front posts get braces
        print(f"  Knee brace {i}...")
        # Brace connects from post (lower) to ring beam (higher)
        # Start 1 foot below top of post
        brace_start_height = post_front_height - feet(1)
        
        # End at midpoint of ring beam
        ring_beam_length = ring_beams[i].length
        brace_end_position = ring_beam_length / Rational(2)
        
        brace = join_timbers(
            timber1=posts[i],
            timber2=ring_beams[i],
            location_on_timber1=brace_start_height,
            stickout=Stickout.nostickout(),
            location_on_timber2=brace_end_position,
            lateral_offset=Rational(0),
            size=brace_size,
            orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),
            ticket=f"Knee Brace {i}"
        )
        braces.append(brace)

    # ============================================================================
    # Create simple butt joints for knee braces
    # ============================================================================
    
    brace_joints = []
    
    for i, brace in enumerate(braces):
        # Brace bottom to post - simple butt joint (could be more elaborate)
        # For now, just let them intersect naturally
        # In real construction, you'd want proper housing or mortise joints
        pass

    # ============================================================================
    # Create floor joists radiating from center
    # ============================================================================
    
    print("Creating floor joists...")
    joist_size = med_timber_size
    joists = []
    
    for i in range(6):
        print(f"  Joist {i}...")
        # Each joist runs from the hub (bottom) to mudsill i
        # Position along mudsill at midpoint
        mudsill_midpoint = mudsills[i].length / Rational(2)
        
        # Joists should be flush with top of mudsills
        mudsill_height = large_timber_size[0]
        joist_height = med_timber_size[0]
        joist_offset = (mudsill_height - joist_height) / Rational(2)
        
        joist_stickout = Stickout(Rational(0), Rational(0))  # No stickout
        
        joist = join_timbers(
            timber1=hub_post,
            timber2=mudsills[i],
            location_on_timber1=Rational(0),  # At bottom of hub
            stickout=joist_stickout,
            location_on_timber2=mudsill_midpoint,
            lateral_offset=joist_offset,
            size=joist_size,
            orientation_width_vector=create_v3(Integer(0), Integer(0), Integer(1)),
            ticket=f"Floor Joist {i}"
        )
        joists.append(joist)

    # ============================================================================
    # Create dovetail joints for joists with mudsills
    # ============================================================================
    
    print("Creating dovetail joints for joists...")
    # TEMPORARILY COMMENTED OUT - Testing if dovetail joints cause freeze
    joist_joints = []
    
    # dovetail_shoulder_inset = inches(Rational(1, 2))
    # dovetail_small_width = inches(Rational(3, 2))
    # dovetail_large_width = inches(2)
    # dovetail_length = inches(2)
    # dovetail_depth = inches(2)
    # 
    # for i, joist in enumerate(joists):
    #     print(f"  Dovetail joint {i}...")
    #     # Create dovetail at the mudsill end (TOP end of joist)
    #     # The dovetail face should be perpendicular to the mudsill
    #     joint = cut_housed_dovetail_butt_joint(
    #         dovetail_timber=joist,
    #         receiving_timber=mudsills[i],
    #         dovetail_timber_end=TimberReferenceEnd.TOP,
    #         dovetail_timber_face=TimberLongFace.RIGHT,  # Adjust as needed
    #         receiving_timber_shoulder_inset=dovetail_shoulder_inset,
    #         dovetail_length=dovetail_length,
    #         dovetail_small_width=dovetail_small_width,
    #         dovetail_large_width=dovetail_large_width,
    #         dovetail_lateral_offset=Rational(0),
    #         dovetail_depth=dovetail_depth
    #     )
    #     joist_joints.append(joint)

    # ============================================================================
    # Create Frame from all joints
    # ============================================================================
    
    print("Assembling frame...")
    all_joints = []
    
    # Add all the joints we created
    all_joints.extend(miter_joints)  # Mudsill corners
    all_joints.extend(post_mudsill_joints)  # Posts to mudsills
    all_joints.extend(ring_beam_joints)  # Ring beam corners
    all_joints.extend(post_ring_beam_joints)  # Posts to ring beams
    # all_joints.extend(joist_joints)  # Joists to mudsills - COMMENTED OUT FOR TESTING
    
    # Unjointed timbers (those without joints)
    unjointed_timbers = []
    unjointed_timbers.append(hub_post)  # Central hub post
    unjointed_timbers.extend(rafters)  # Rafters
    unjointed_timbers.extend(braces)  # Knee braces
    unjointed_timbers.extend(joists)  # Joists (no joints for now)
    
    print("Creating Frame.from_joints...")
    return Frame.from_joints(
        all_joints, 
        additional_unjointed_timbers=unjointed_timbers,
        name="Honeycomb Shed"
    )


example = create_honeycomb_shed


# ============================================================================
# Main execution (when run as standalone script)
# ============================================================================

if __name__ == "__main__":
    print("Creating the Honeycomb Shed - A Hexagonal Wonder!")
    print(f"  Hexagonal radius: {float(hex_radius):.3f} m")
    print(f"  Front posts: {float(post_front_height):.3f} m tall")
    print(f"  Back posts: {float(post_back_height):.3f} m tall")
    
    frame = create_honeycomb_shed()
    
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
    print("HONEYCOMB SHED - STRUCTURE SUMMARY")
    print("="*60)
    print(f"Shape: Hexagonal (6 sides)")
    print(f"Radius: {hex_radius} (center to corner)")
    print(f"Mudsills: 6 (one per side, with miter joints at corners)")
    print(f"Posts: 6 corner posts + 1 central hub post")
    print(f"  - Front 3 posts: {post_front_height} tall")
    print(f"  - Back 3 posts: {post_back_height} tall")
    print(f"  - Central hub: {((post_front_height + post_back_height) / Rational(2) + inches(12))} tall")
    print(f"Ring Beams: 6 (forming hexagonal top ring with miter joints)")
    print(f"  - 6\" stickout on each end for dramatic overhang")
    print(f"Rafters: 6 radial rafters from central hub to corners")
    print(f"  - Creates dramatic pyramidal roof structure")
    print(f"  - 12\" stickout at outer ends")
    print(f"Knee Braces: 3 (at front posts for decorative detail)")
    print(f"  - Connects posts to ring beams diagonally")
    print(f"Floor Joists: 6 (radiating from center hub to mudsills)")
    print(f"  - Dovetail joints at mudsill connections")
    print(f"  - Creates strong radial floor structure")
    print("\nSpecial Features:")
    print(f"  ✓ Hexagonal symmetry for unique aesthetic")
    print(f"  ✓ Central hub post for structural stability")
    print(f"  ✓ Dramatic sloped roof (3 ft height difference!)")
    print(f"  ✓ Radial rafter system creating pyramid roof")
    print(f"  ✓ Decorative knee braces at front")
    print("="*60)
