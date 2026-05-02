"""
Kumiki - Japanese Joint Construction Functions
Contains traditional Japanese timber joint implementations
"""
import warnings

from kumiki.timber import *
from kumiki.construction import *
from .joint_shavings import *
from kumiki.measuring import locate_top_center_position, locate_centerline, mark_distance_from_end_along_centerline
from kumiki.rule import *
from kumiki.cutcsg import *

# Aliases for backwards compatibility
CSGUnion = SolidUnion


# ============================================================================
# Japanese Joint Construction Functions
# ============================================================================


# see diagram below
def draw_gooseneck_polygon_NONCONVEX(length: Numeric, small_width: Numeric, large_width: Numeric, head_length: Numeric) -> List[V2]:
    """
    Returns the non-convex gooseneck profile as a single polygon (for reference/visualization).

    The gooseneck shape has a narrow neck that widens into a trapezoidal head. This polygon
    is non-convex and cannot be used directly with chop_profile_on_timber_face. Use
    draw_gooseneck_polygon_CONVEX (aliased as draw_gooseneck_polygon) for actual cutting.

    Args:
        length: Total length of the gooseneck shape along the profile Y-axis.
        small_width: Width of the neck (the narrow portion).
        large_width: Width of the head (the wide trapezoid base; must be > small_width).
        head_length: Length of the trapezoidal head portion.

    Returns:
        List of 2D points forming the non-convex gooseneck polygon (counter-clockwise).
    """
    return [
            Matrix([small_width/2, 0]),
            Matrix([small_width/2, length-head_length]),
            Matrix([large_width/2, length-head_length]),
            Matrix([small_width/2, length]),
            Matrix([-small_width/2, length]),
            Matrix([-large_width/2, length-head_length]),
            Matrix([-small_width/2, length-head_length]),
            Matrix([-small_width/2, 0]),
        ]

# see diagram below
def draw_gooseneck_polygon_CONVEX(length: Numeric, small_width: Numeric, large_width: Numeric, head_length: Numeric) -> List[List[V2]]:
    """
    Returns the gooseneck profile decomposed into convex polygons for use with chop_profile_on_timber_face.

    The non-convex gooseneck shape is split into two convex polygons — a neck rectangle and
    a head trapezoid — whose union gives the full gooseneck. This is the format required by
    chop_profile_on_timber_face (List[List[V2]]).

    Args:
        length: Total length of the gooseneck shape along the profile Y-axis.
        small_width: Width of the neck (the narrow portion).
        large_width: Width of the head (the wide trapezoid base; must be > small_width).
        head_length: Length of the trapezoidal head portion.

    Returns:
        List of two convex polygon point lists: [neck_rectangle, head_trapezoid].
    """
    # Decompose the gooseneck into 2 convex polygons
    # Center rectangle and head trapezoid
    
    # Center neck rectangle
    center_rect = [
        Matrix([small_width/2, 0]),
        Matrix([small_width/2, length-head_length]),
        Matrix([-small_width/2, length-head_length]),
        Matrix([-small_width/2, 0]),
    ]
    
    # Head trapezoid (single shape)
    head_trap = [
        Matrix([-large_width/2, length-head_length]),
        Matrix([large_width/2, length-head_length]),
        Matrix([small_width/2, length]),
        Matrix([-small_width/2, length]),
    ]
    
    return [center_rect, head_trap]

# Alias for convenience
draw_gooseneck_polygon = draw_gooseneck_polygon_CONVEX


r'''

 ___     ___
    |   |                                     T  
    |   |                                     |
  __|   |__                                   |
  \       /        T                          | gooseneck_length
  .\     /.        | gooseneck_head_length    |
  . \___/ .        ⊥                          ⊥
  . .   . .
  . .   . .
  . |---| .        gooseneck_small_width
  .       .
  |-------|        gooseneck_large_width 


          lap length 
             |-|
__________________________
   |__|______|_              | <- goosneck_depth
_______________|__________
               ^
               end of receiving timber
'''
def cut_lapped_gooseneck_joint(
    arrangement: SpliceJointTimberArrangement,
    gooseneck_length: Numeric,
    gooseneck_small_width: Numeric,
    gooseneck_large_width: Numeric,
    gooseneck_head_length: Numeric,
    lap_length: Numeric = Rational(0), # 0 just means no lap
    gooseneck_lateral_offset: Numeric = Rational(0),
    gooseneck_depth: Optional[Numeric] = None
) -> Joint:
    """
    Creates a lapped gooseneck joint (腰掛鎌継ぎ / Koshikake Kama Tsugi) between two timbers.
    
    This is a traditional Japanese timber joint that combines a lap joint with a gooseneck-shaped
    profile. The gooseneck profile provides mechanical interlock while the lap provides additional
    bearing surface.
    
    Args:
        arrangement: Splice arrangement where timber1 is the gooseneck timber,
            timber2 is the receiving timber, timber1_end/timber2_end are the joined
            ends, and front_face_on_timber1 is the face on timber1 where the
            gooseneck profile is visible.
        gooseneck_length: Length of the gooseneck shape (does not include lap length)
        gooseneck_small_width: Width of the narrow end of the gooseneck taper
        gooseneck_large_width: Width of the wide end of the gooseneck taper
        gooseneck_head_length: Length of the head portion of the gooseneck
        lap_length: Length of the lap portion of the joint
        gooseneck_depth: Optional depth of the gooseneck cut. If None, defaults to half the timber dimension
                        perpendicular to arrangement.front_face_on_timber1
    
    Returns:
        Joint object containing the two CutTimbers with the gooseneck cuts applied
    
    Raises:
        ValueError: If the parameters are invalid or the timbers are not properly positioned
        
    Notes:
        - The gooseneck profile creates a mechanical interlock that resists pulling apart
        - The lap provides additional bearing surface for compression loads
        - This joint is traditionally used for connecting beams end-to-end
    """
    require_check(arrangement.check_face_aligned_and_parallel_axis())
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the gooseneck face"
    )
    gooseneck_timber = arrangement.timber1
    receiving_timber = arrangement.timber2
    gooseneck_timber_end = arrangement.timber1_end
    receiving_timber_end = arrangement.timber2_end
    gooseneck_timber_face = arrangement.front_face_on_timber1

    # ========================================================================
    # Parameter validation
    # ========================================================================
    
    # Validate positive dimensions
    if gooseneck_length <= 0:
        raise ValueError(f"gooseneck_length must be positive, got {gooseneck_length}")
    if gooseneck_small_width <= 0:
        raise ValueError(f"gooseneck_small_width must be positive, got {gooseneck_small_width}")
    if gooseneck_large_width <= 0:
        raise ValueError(f"gooseneck_large_width must be positive, got {gooseneck_large_width}")
    if gooseneck_head_length <= 0:
        raise ValueError(f"gooseneck_head_length must be positive, got {gooseneck_head_length}")
    
    # Validate that large_width > small_width (gooseneck taper requirement)
    if gooseneck_large_width <= gooseneck_small_width:
        raise ValueError(
            f"gooseneck_large_width ({gooseneck_large_width}) must be greater than "
            f"gooseneck_small_width ({gooseneck_small_width})"
        )
    
    # Validate gooseneck_depth if provided
    if gooseneck_depth is not None and gooseneck_depth <= 0:
        raise ValueError(f"gooseneck_depth must be positive if provided, got {gooseneck_depth}")

    # TODO why is this going off in our example
    # Check that the timbers overlap in a sensible way for a splice joint:
    #             |==================| <- gooseneck timber / end
    # receiving_timber_end -> |==================| <- receiving timber
    overlap_error = check_timber_overlap_for_splice_joint_is_sensible(
        gooseneck_timber, receiving_timber, gooseneck_timber_end, receiving_timber_end
    )
    if overlap_error:
        warnings.warn(f"Gooseneck joint configuration may not be sensible: {overlap_error}")

    # compute the starting position for the gooseneck shape in global space
    gooseneck_direction_global = -receiving_timber.get_face_direction_global(receiving_timber_end)
    gooseneck_lateral_offset_direction_global = receiving_timber.get_face_direction_global(gooseneck_timber_face.rotate_right())

    # Get the receiving timber end position
    if receiving_timber_end == TimberReferenceEnd.TOP:
        receiving_timber_end_position_global = locate_top_center_position(receiving_timber).position
    else:  # BOTTOM
        receiving_timber_end_position_global = receiving_timber.get_bottom_position_global()
    
    # Move from the receiving timber end by gooseneck_length (inward) to get the gooseneck starting position
    gooseneck_starting_position_on_receiving_timber_centerline_with_lateral_offset_global = receiving_timber_end_position_global + gooseneck_direction_global * lap_length + gooseneck_lateral_offset_direction_global * gooseneck_lateral_offset

    # project gooseneck_starting_position_on_receiving_timber_centerline_with_lateral_offset_global onto the gooseneck_timber_face
    gooseneck_starting_position_global = receiving_timber.project_global_point_onto_timber_face_global(gooseneck_starting_position_on_receiving_timber_centerline_with_lateral_offset_global, gooseneck_timber_face)
    gooseneck_drawing_normal_global = gooseneck_timber.get_face_direction_global(gooseneck_timber_face)

    # now cut the gooseneck shape into the gooseneck_timber
    gooseneck_shape = draw_gooseneck_polygon(gooseneck_length, gooseneck_small_width, gooseneck_large_width, gooseneck_head_length)

    # ========================================================================
    # Determine gooseneck depth default
    # ========================================================================
    
    if gooseneck_depth is None:
        # Default to half the dimension perpendicular to the specified face
        gooseneck_depth = gooseneck_timber.get_size_in_face_normal_axis(
            gooseneck_timber_face.to.face()
        ) / Rational(2)

    # ========================================================================
    # Calculate lap positions and depths
    # ========================================================================
    
    # Extract the length component from gooseneck_starting_position_on_receiving_timber_centerline_with_lateral_offset_global
    # This gives us the distance from the receiving timber's bottom position along its length axis
    gooseneck_starting_position_on_receiving_timber = (
        (gooseneck_starting_position_on_receiving_timber_centerline_with_lateral_offset_global - receiving_timber.get_bottom_position_global()).T 
        * receiving_timber.get_length_direction_global()
    )[0, 0]
    
    # Compute lap end position: move by lap_length in the direction away from receiving timber end
    # (opposite of gooseneck_direction_global, which points inward from the end)
    lap_direction = -gooseneck_direction_global
    lap_end_position_on_receiving_timber = gooseneck_starting_position_on_receiving_timber + lap_length
    
    # Compute gooseneck depth relative to the opposing face on the receiving timber
    # This accounts for any offset or rotation between the timbers
    # Create a plane at gooseneck_depth from the gooseneck timber's face
    gooseneck_cutting_plane = locate_into_face(gooseneck_depth, gooseneck_timber_face, gooseneck_timber)
    # Find the opposing face on the receiving timber
    gooseneck_face_direction = gooseneck_timber.get_face_direction_global(gooseneck_timber_face)
    receiving_face_direction = -gooseneck_face_direction
    receiving_face = receiving_timber.get_closest_oriented_face_from_global_direction(receiving_face_direction)
    # Measure from the receiving face to the cutting plane
    marking = mark_distance_from_face_in_normal_direction(gooseneck_cutting_plane, receiving_timber, receiving_face)
    receiving_timber_lap_depth = Abs(marking.distance)
    
    # ========================================================================
    # Cut laps on both timbers
    # ========================================================================
    
    # Calculate shoulder position for receiving timber (distance from end to shoulder)
    if receiving_timber_end == TimberReferenceEnd.TOP:
        receiving_timber_shoulder_from_end = receiving_timber.length - gooseneck_starting_position_on_receiving_timber
    else:  # BOTTOM
        receiving_timber_shoulder_from_end = gooseneck_starting_position_on_receiving_timber
    
    # Get the receiving timber face that opposes the gooseneck face
    receiving_timber_lap_face_direction = -gooseneck_timber.get_face_direction_global(gooseneck_timber_face)
    receiving_timber_lap_face = receiving_timber.get_closest_oriented_face_from_global_direction(receiving_timber_lap_face_direction)
    
    # Cut lap on receiving timber (only when lap_length > 0; a zero-length lap would
    # produce a degenerate RectangularPrism that breaks triangulation).
    if lap_length > 0:
        receiving_timber_lap_prism, receiving_timber_end_cut = chop_lap_on_timber_end(
            lap_timber=receiving_timber,
            lap_timber_end=receiving_timber_end,
            lap_timber_face=receiving_timber_lap_face,
            lap_length=lap_length,
            lap_shoulder_position_from_lap_timber_end=receiving_timber_shoulder_from_end,
            lap_depth=receiving_timber_lap_depth
        )
    else:
        receiving_timber_end_cut = None
    
    # Calculate shoulder position for gooseneck timber
    # The gooseneck timber's lap starts at the point where it meets the receiving timber's lap end
    # and extends by lap_length in the direction of the gooseneck timber end
    gooseneck_lap_start_global = receiving_timber_end_position_global 
    
    # Project onto gooseneck timber's length axis
    gooseneck_lap_start_on_gooseneck_timber = (
        (gooseneck_lap_start_global - gooseneck_timber.get_bottom_position_global()).T 
        * gooseneck_timber.get_length_direction_global()
    )[0, 0]
    
    if gooseneck_timber_end == TimberReferenceEnd.TOP:
        gooseneck_timber_lap_shoulder_from_end = gooseneck_timber.length - gooseneck_lap_start_on_gooseneck_timber
    else:  # BOTTOM
        gooseneck_timber_lap_shoulder_from_end = gooseneck_lap_start_on_gooseneck_timber

    # Cut lap on gooseneck timber
    gooseneck_timber_lap_prism, gooseneck_timber_lap_end_cut = chop_lap_on_timber_end(
        lap_timber=gooseneck_timber,
        lap_timber_end=gooseneck_timber_end,
        lap_timber_face=TimberFace(gooseneck_timber_face.value),
        lap_length=lap_length+gooseneck_length,
        lap_shoulder_position_from_lap_timber_end=gooseneck_timber_lap_shoulder_from_end,
        lap_depth=gooseneck_depth
    )
    
    # ========================================================================
    # Cut gooseneck shape into gooseneck timber
    # ========================================================================
    
    # Translate the gooseneck profile to the correct position
    # The profile coordinate system has Y-axis pointing into the timber from the end
    # Y=0 is at the timber end, Y increases going into the timber
    # draw_gooseneck_polygon creates profiles with base at Y=0 and head at Y=gooseneck_length
    #
    # The lap shoulder is at gooseneck_timber_lap_shoulder_from_end from the end
    # The gooseneck profile should start lap_length inward from the shoulder
    # So: gooseneck base position = shoulder + lap_length
    gooseneck_profile_y_position = gooseneck_timber_lap_shoulder_from_end + lap_length
    
    # Create the gooseneck profile CSG cut using chop_profile_on_timber_face
    # This creates a CSG that removes the gooseneck shape from the timber
    gooseneck_profile_csg = chop_profile_on_timber_face(
        timber=gooseneck_timber,
        end=gooseneck_timber_end,
        face=gooseneck_timber_face.to.face(),
        profile=gooseneck_shape,
        depth=gooseneck_depth,
        profile_y_offset_from_end=-gooseneck_profile_y_position
    )

    # Use chop_timber_end_with_prism to create the end-side volume for the profile cut.
    # NOTE:
    # The prism boundary and gooseneck profile offset both use gooseneck_profile_y_position.
    # This creates coplanar overlap in Difference(prism - profile), which can cause the
    # manifold boolean engine to emit nano-thickness shoulder flaps. These are removed
    # as degenerate geometry during rendering (see triangles._remove_tiny_disconnected_components).
    # I'm not sure why this doesn't happen in more places, maybe connected nano-thickness flaps get removed but not disconnected ones?
    gooseneck_profile_prism = chop_timber_end_with_prism(
        timber=gooseneck_timber,
        end=gooseneck_timber_end,
        distance_from_end_to_cut=-(gooseneck_profile_y_position)
    )

    # difference the gooseneck profile prism with the gooseneck profile csg
    gooseneck_profile_difference_csg = Difference(gooseneck_profile_prism, [gooseneck_profile_csg])
    
    # Union the gooseneck profile cut with the lap cut
    # Both cuts need to be applied to the gooseneck timber
    gooseneck_timber_combined_csg = CSGUnion([gooseneck_timber_lap_prism, gooseneck_profile_difference_csg])

    # Create a redundant end cut for the gooseneck timber
    # The gooseneck extends beyond the receiving timber end by (lap_length + gooseneck_length)
    # Position the end cut at: receiving_timber_end + lap_length + gooseneck_length
    gooseneck_extension_from_receiving_end = lap_length + gooseneck_length
    
    # Calculate where the gooseneck end is in gooseneck timber local coordinates
    # gooseneck_timber_lap_shoulder_from_end is where the lap starts
    # The gooseneck extends from there by gooseneck_extension_from_receiving_end
    # TODO this seems to be wrong?
    gooseneck_end_position_from_timber_end = gooseneck_timber_lap_shoulder_from_end - gooseneck_extension_from_receiving_end
    
    if gooseneck_timber_end == TimberReferenceEnd.TOP:
        # End cut at distance from top
        gooseneck_end_cut_local_z = gooseneck_timber.length - gooseneck_end_position_from_timber_end
        gooseneck_timber_end_cut = HalfSpace(normal=create_v3(0, 0, 1), offset=gooseneck_end_cut_local_z)
    else:  # BOTTOM
        # End cut at distance from bottom
        # TODO this case seems to be broken?
        gooseneck_end_cut_local_z = gooseneck_end_position_from_timber_end
        gooseneck_timber_end_cut = HalfSpace(normal=create_v3(0, 0, -1), offset=-gooseneck_end_cut_local_z)

    # Transform the gooseneck profile CSG from gooseneck_timber coordinates to receiving_timber coordinates
    # Use the generic adopt_csg function to handle all CSG types (SolidUnion, Difference, RectangularPrism, etc.)
    gooseneck_csg_on_receiving_timber = adopt_csg(gooseneck_timber.transform, receiving_timber.transform, gooseneck_profile_csg)

    if lap_length > 0:
        receiving_timber_negative_csg: CutCSG = CSGUnion([receiving_timber_lap_prism, gooseneck_csg_on_receiving_timber])
    else:
        receiving_timber_negative_csg = gooseneck_csg_on_receiving_timber

    # Create Cut objects for each timber
    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        maybe_top_end_cut=receiving_timber_end_cut if receiving_timber_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=receiving_timber_end_cut if receiving_timber_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=receiving_timber_negative_csg
    )
    gooseneck_timber_cut_obj = Cutting(
        timber=gooseneck_timber,
        maybe_top_end_cut=gooseneck_timber_end_cut if gooseneck_timber_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=gooseneck_timber_end_cut if gooseneck_timber_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=gooseneck_timber_combined_csg
    )
    
    # Create CutTimber objects with the cuts
    receiving_timber_cut = CutTimber(
        timber=receiving_timber,
        cuts=[receiving_timber_cut_obj]
    )
    
    gooseneck_timber_cut = CutTimber(
        timber=gooseneck_timber,
        cuts=[gooseneck_timber_cut_obj]
    )
    
    return Joint(
        cut_timbers={
            receiving_timber.ticket.name: receiving_timber_cut,
            gooseneck_timber.ticket.name: gooseneck_timber_cut
        },
        ticket=JointTicket(joint_type="lapped_gooseneck"),
        jointAccessories={},
    )

def cut_housed_dovetail_butt_joint(
    arrangement: ButtJointTimberArrangement,
    receiving_timber_shoulder_inset: Numeric,
    dovetail_length: Numeric,
    dovetail_small_width: Numeric,
    dovetail_large_width: Numeric,
    dovetail_lateral_offset: Numeric = Rational(0),
    dovetail_depth: Optional[Numeric] = None
) -> Joint:
    """
    Creates a dovetail butt joint (蟻継ぎ / Ari Tsugi) between two orthogonal timbers.
    
    This is a traditional Japanese timber joint where a dovetail-shaped tenon on one timber
    fits into a matching dovetail socket on another timber. The dovetail shape provides
    mechanical resistance to pulling apart.
    
    Args:
        arrangement: Butt joint arrangement where butt_timber is the dovetail timber,
            receiving_timber receives the dovetail socket, butt_timber_end is the cut end,
            and front_face_on_butt_timber is the face where the dovetail profile is visible.
        receiving_timber_shoulder_inset: Distance to inset the shoulder notch on the receiving timber
        dovetail_length: Length of the dovetail tenon
        dovetail_small_width: Width of the narrow end of the dovetail (at the tip)
        dovetail_large_width: Width of the wide end of the dovetail (at the base)
        dovetail_lateral_offset: Lateral offset of the dovetail from center (default 0)
        dovetail_depth: Depth of the dovetail cut. If None, defaults to half the timber dimension
    
    Returns:
        Joint object containing the two CutTimbers with the dovetail cuts applied
    
    Raises:
        ValueError: If the parameters are invalid or the timbers are not orthogonal
    
    Notes:
        - The dovetail provides mechanical resistance to pulling apart
        - Timbers must be orthogonal (at 90 degrees) for this joint
        - No lap is used in this joint (unlike the lapped gooseneck joint)
    """
    
    require_check(arrangement.check_face_aligned_and_orthogonal())
    assert arrangement.front_face_on_butt_timber is not None, (
        "arrangement.front_face_on_butt_timber must be set to determine the dovetail face"
    )
    dovetail_timber = arrangement.butt_timber
    receiving_timber = arrangement.receiving_timber
    dovetail_timber_end = arrangement.butt_timber_end
    dovetail_timber_face = arrangement.front_face_on_butt_timber

    # ========================================================================
    # Parameter validation
    # ========================================================================
    
    # Validate positive dimensions
    if dovetail_length <= 0:
        raise ValueError(f"dovetail_length must be positive, got {dovetail_length}")
    if dovetail_small_width <= 0:
        raise ValueError(f"dovetail_small_width must be positive, got {dovetail_small_width}")
    if dovetail_large_width <= 0:
        raise ValueError(f"dovetail_large_width must be positive, got {dovetail_large_width}")
    if receiving_timber_shoulder_inset < 0:
        raise ValueError(f"receiving_timber_shoulder_inset must be non-negative, got {receiving_timber_shoulder_inset}")
    
    # Validate that large_width > small_width (dovetail taper requirement)
    if dovetail_large_width <= dovetail_small_width:
        raise ValueError(
            f"dovetail_large_width ({dovetail_large_width}) must be greater than "
            f"dovetail_small_width ({dovetail_small_width})"
        )
    
    # Validate dovetail_depth if provided
    if dovetail_depth is not None and dovetail_depth <= 0:
        raise ValueError(f"dovetail_depth must be positive if provided, got {dovetail_depth}")
    
    # assert that dovetail_timber_face is perpendicular to receiving_timber.get_length_direction_global()
    if are_vectors_parallel(dovetail_timber.get_face_direction_global(dovetail_timber_face), receiving_timber.get_length_direction_global()):
        raise ValueError(
            "Dovetail timber face must be perpendicular to receiving timber length direction for dovetail butt joint. "
            "The face should be oriented such that the dovetail profile is visible when looking along the receiving timber. "
            "Try rotating the dovetail face by 90 degrees. "
            f"Got dovetail_timber_face direction: {dovetail_timber.get_face_direction_global(dovetail_timber_face).T}, "
            f"receiving_timber length_direction: {receiving_timber.get_length_direction_global().T}"
        )
    
    # ========================================================================
    # Calculate default depth if not provided
    # ========================================================================
    
    if dovetail_depth is None:
        # Default: half the timber dimension perpendicular to the dovetail face
        dovetail_depth = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.to.face()) / Rational(2)
    
    # ========================================================================
    # Create the dovetail profile (simple trapezoid)
    # TODO move into separate function
    # ========================================================================
    
    # Dovetail profile in 2D (X = lateral, Y = along timber length from end)
    # Y=0 is at the timber end, Y increases going into the timber
    # Small width at Y=0 (tip), large width at Y=dovetail_length (base)
    
    dovetail_profile = [
        # Tip (narrow end at the timber end)
        Matrix([-dovetail_small_width / Rational(2) + dovetail_lateral_offset, 0]),
        Matrix([dovetail_small_width / Rational(2) + dovetail_lateral_offset, 0]),
        # Base (wide end)
        Matrix([dovetail_large_width / Rational(2) + dovetail_lateral_offset, dovetail_length]),
        Matrix([-dovetail_large_width / Rational(2) + dovetail_lateral_offset, dovetail_length]),
    ]


    # ========================================================================
    # create the marking transform
    # it is on the centerline of the dovetail face where it intersects the inset shoulder of the mortise timber
    # ========================================================================

    receiving_timber_shoulder_face = receiving_timber.get_closest_oriented_face_from_global_direction(-dovetail_timber.get_face_direction_global(dovetail_timber_end.to.face()))
    face_plane = scribe_face_plane_onto_centerline(
        face=receiving_timber_shoulder_face,
        face_timber=receiving_timber
    )
    marking = mark_distance_from_end_along_centerline(face_plane, dovetail_timber, dovetail_timber_end)
    shoulder_distance_from_end = marking.distance - receiving_timber_shoulder_inset

    offset_to_dovetail_face = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face) / Rational(2) * dovetail_timber.get_face_direction_global(dovetail_timber_face)
    
    marking_transform_position = dovetail_timber.get_bottom_position_global() + shoulder_distance_from_end * dovetail_timber.get_length_direction_global() + offset_to_dovetail_face
    marking_transform_orientation = orientation_pointing_towards_face_sitting_on_face(towards_face=dovetail_timber_end.to.face(), sitting_face=dovetail_timber_face.to.face())
    dovetail_timber_marking_transform = Transform(position=marking_transform_position, orientation=marking_transform_orientation)


    # ========================================================================
    # Cut dovetail shape into dovetail timber
    # ========================================================================
    
    # Create the dovetail profile CSG using chop_profile_on_timber_face
    # This creates the profile extrusion
    dovetail_profile_csg = chop_profile_on_timber_face(
        timber=dovetail_timber,
        end=dovetail_timber_end,
        face=dovetail_timber_face.to.face(),
        profile=dovetail_profile,
        depth=dovetail_depth,
        profile_y_offset_from_end=shoulder_distance_from_end
    )

    # dovetail housing prism
    dovetail_housing_prism = chop_timber_end_with_prism(
        timber=dovetail_timber,
        end=dovetail_timber_end,
        distance_from_end_to_cut=shoulder_distance_from_end
    )
    
    # ========================================================================
    # Cut shoulder notch on receiving timber
    # ========================================================================
    
    # Calculate where along the receiving timber the shoulder should be
    dovetail_centerline = scribe_centerline_onto_centerline(dovetail_timber)
    marking_receiving = mark_distance_from_end_along_centerline(dovetail_centerline, receiving_timber)
    receiving_timber_notch_center = marking_receiving.distance
    
    # Create shoulder notch if inset is specified
    if receiving_timber_shoulder_inset > 0:
        # Notch dimensions match the dovetail timber's cross-section at the housing
        # Width is the length of the housing (shoulder_distance_from_end on dovetail timber)
        notch_width = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_face.rotate_right().to.face())
        
        # Depth is the amount of inset
        notch_depth = receiving_timber_shoulder_inset
        
        receiving_timber_shoulder_notch = chop_shoulder_notch_on_timber_face(
            timber=receiving_timber,
            notch_face=receiving_timber_shoulder_face,
            distance_along_timber=receiving_timber_notch_center,
            notch_width=notch_width,
            notch_depth=notch_depth
        )
    
    # ========================================================================
    # Adopt the dovetail socket CSG to the receiving timber
    # ========================================================================
    
    # Transform the dovetail profile CSG from dovetail_timber coordinates to receiving_timber coordinates
    dovetail_socket_csg = adopt_csg(dovetail_timber.transform, receiving_timber.transform, dovetail_profile_csg)
    
    # ========================================================================
    # Create Cut objects for each timber
    # ========================================================================
    
    # Create a redundant end cut for the dovetail timber
    # The end cut should be at the end of the dovetail profile
    # The dovetail extends from the shoulder (at shoulder_distance_from_end) toward the end for dovetail_length
    
    if dovetail_timber_end == TimberReferenceEnd.TOP:
        # For TOP end: shoulder is at (timber.length - shoulder_distance_from_end)
        # Dovetail extends toward +Z for dovetail_length
        dovetail_end_local_z = dovetail_timber.length - shoulder_distance_from_end + dovetail_length
        dovetail_timber_end_cut = HalfSpace(normal=create_v3(0, 0, 1), offset=dovetail_end_local_z)
    else:  # BOTTOM
        # For BOTTOM end: shoulder is at shoulder_distance_from_end
        # Dovetail extends toward -Z for dovetail_length
        dovetail_end_local_z = shoulder_distance_from_end - dovetail_length
        dovetail_timber_end_cut = HalfSpace(normal=create_v3(0, 0, -1), offset=-dovetail_end_local_z)
    
    dovetail_timber_cut_obj = Cutting(
        timber=dovetail_timber,
        maybe_top_end_cut=dovetail_timber_end_cut if dovetail_timber_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=dovetail_timber_end_cut if dovetail_timber_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=Difference(dovetail_housing_prism, [dovetail_profile_csg])
    )
    
    # Combine shoulder notch and dovetail socket if shoulder inset is specified
    if receiving_timber_shoulder_inset > 0:
        receiving_timber_negative_csg = CSGUnion([receiving_timber_shoulder_notch, dovetail_socket_csg])
    else:
        receiving_timber_negative_csg = dovetail_socket_csg
    
    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        maybe_top_end_cut=None,
        maybe_bottom_end_cut=None,
        negative_csg=receiving_timber_negative_csg
    )
    
    # Create CutTimber objects
    dovetail_timber_cut = CutTimber(
        timber=dovetail_timber,
        cuts=[dovetail_timber_cut_obj]
    )
    
    receiving_timber_cut = CutTimber(
        timber=receiving_timber,
        cuts=[receiving_timber_cut_obj]
    )
    
    return Joint(
        cut_timbers={
            dovetail_timber.ticket.name: dovetail_timber_cut,
            receiving_timber.ticket.name: receiving_timber_cut
        },
        ticket=JointTicket(joint_type="housed_dovetail_butt"),
        jointAccessories={},
    )


# rename lap_start_distance_from_reference_miter_face -> first_lap_distance_from_reference_miter_face
def cut_mitered_and_keyed_lap_joint(arrangement: CornerJointTimberArrangement, lap_thickness: Optional[Numeric] = None, lap_start_distance_from_reference_miter_face: Optional[Numeric] = None, distance_between_lap_and_outside: Optional[Numeric] = None, num_laps: int = 2, key_width: Optional[Numeric] = None, key_thickness: Optional[Numeric] = None) -> Joint:
    """
    Creates a mitered and keyed lap joint (箱相欠き車知栓仕口 / Hako Aikaki Shachi Sen Shikuchi)
    between two timbers.
    
    This is a traditional Japanese timber joint that combines a miter joint with interlocking
    finger laps on the inside of the miter for additional mechanical strength.
    
    Args:
        arrangement: Corner joint arrangement where timber1 and timber2 are the joined
            timbers, timber1_end and timber2_end are the joined ends, and
            front_face_on_timber1 defines the reference miter face on timber1.
        lap_thickness: Thickness of each lap/finger (optional, auto-calculated if None)
        lap_start_distance_from_reference_miter_face: Distance from miter face to first lap (optional)
        distance_between_lap_and_outside: Inset distance from outer face (optional)
        num_laps: Number of interlocking laps/fingers (minimum 2)
        key_width: Width of each key measured along the diagonal direction. If None,
            defaults to lap_thickness.
        key_thickness: Thickness of each key (the narrow dimension). If None,
            defaults to lap_thickness / 3.
    
    Returns:
        Joint object containing the two CutTimbers with miter and finger cuts applied
    
    Raises:
        ValueError: If parameters are invalid or timbers are not properly positioned
    """
    require_check(arrangement.check_plane_aligned())
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the reference miter face"
    )
    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberA_reference_miter_face = arrangement.front_face_on_timber1
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end
    from sympy import acos, pi
    
    # ========================================================================
    # Step 1: Parameter validation and find matching miter faces
    # ========================================================================
    
    # Validate num_laps
    if num_laps < 2:
        raise ValueError(f"num_laps must be at least 2, got {num_laps}")
    
    # Find matching miter face on timberB
    timberA_miter_face_normal = timberA.get_face_direction_global(timberA_reference_miter_face)
    timberB_reference_miter_face_enum = timberB.get_closest_oriented_face_from_global_direction(
        timberA_miter_face_normal
    )
    
    # Convert to TimberLongFace if it's a long face
    if timberB_reference_miter_face_enum == TimberFace.RIGHT:
        timberB_reference_miter_face = TimberLongFace.RIGHT
    elif timberB_reference_miter_face_enum == TimberFace.LEFT:
        timberB_reference_miter_face = TimberLongFace.LEFT
    elif timberB_reference_miter_face_enum == TimberFace.FRONT:
        timberB_reference_miter_face = TimberLongFace.FRONT
    elif timberB_reference_miter_face_enum == TimberFace.BACK:
        timberB_reference_miter_face = TimberLongFace.BACK
    else:
        raise ValueError(
            f"timberB matching face must be a long face (not TOP or BOTTOM), got {timberB_reference_miter_face_enum}"
        )
    
    # Verify the normals are parallel
    timberB_miter_face_normal = timberB.get_face_direction_global(timberB_reference_miter_face)
    if not are_vectors_parallel(timberA_miter_face_normal, timberB_miter_face_normal):
        raise ValueError(
            f"Miter face normals must be parallel. "
            f"timberA face normal: {timberA_miter_face_normal.T}, "
            f"timberB face normal: {timberB_miter_face_normal.T}"
        )
    
    
    # ========================================================================
    # Step 2: Calculate and validate angle between timbers
    # ========================================================================
    
    # Get end directions (pointing outward from timber)
    if timberA_end == TimberReferenceEnd.TOP:
        directionA = timberA.get_length_direction_global()
    else:  # BOTTOM
        directionA = -timberA.get_length_direction_global()
    
    if timberB_end == TimberReferenceEnd.TOP:
        directionB = timberB.get_length_direction_global()
    else:  # BOTTOM
        directionB = -timberB.get_length_direction_global()
    
    # Calculate angle between timbers using dot product
    # angle = acos(directionA · directionB)
    dot_product = safe_dot_product(normalize_vector(directionA), normalize_vector(directionB))
    
    # Clamp to [-1, 1] to avoid numerical issues with acos
    from sympy import Max, Min
    dot_product_clamped = Max(Rational(-1), Min(Rational(1), dot_product))
    angle = acos(dot_product_clamped)
    
    # Validate angle is between 45 and 135 degrees
    min_angle = radians(pi / Integer(4))  # 45 degrees
    max_angle = radians(Rational(3) * pi / Integer(4))  # 135 degrees
    
    if angle < min_angle or angle > max_angle:
        raise ValueError(
            f"Angle between timbers must be between 45° and 135°, "
            f"got {float(angle * 180 / pi):.1f}°"
        )
    
    # ========================================================================
    # Step 3: Calculate dimensions and default values
    # ========================================================================
    
    # Get miter face dimensions
    miter_face_depth = timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.to.face())
    miter_face_width = timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.rotate_right().to.face())
    
    # Calculate lap_thickness and lap_start_distance defaults
    lap_thickness_final: Numeric
    lap_start_distance_final: Numeric
    
    if lap_thickness is None and lap_start_distance_from_reference_miter_face is None:
        # Both None: distribute evenly
        # Total space for laps plus margins: miter_face_depth
        # We want: margin + num_laps * thickness + margin = miter_face_depth
        # With equal margins: 2*margin + num_laps*thickness = miter_face_depth
        # Let's use: margin = thickness, so: (num_laps + 2)*thickness = miter_face_depth
        lap_thickness_final = miter_face_depth / (num_laps + Integer(2))
        lap_start_distance_final = lap_thickness_final
        
    elif lap_thickness is None:
        # Only start distance given, calculate thickness
        assert lap_start_distance_from_reference_miter_face is not None  # Type narrowing
        remaining_depth: Numeric = miter_face_depth - lap_start_distance_from_reference_miter_face
        lap_thickness_final = remaining_depth / Integer(num_laps+1)
        lap_start_distance_final = lap_start_distance_from_reference_miter_face
    elif lap_start_distance_from_reference_miter_face is None:
        # Only thickness given, calculate start distance
        total_lap_depth: Numeric = lap_thickness * num_laps
        lap_start_distance_final = (miter_face_depth - total_lap_depth) / Rational(2)
        lap_thickness_final = lap_thickness
    else:
        # Both provided
        lap_thickness_final = lap_thickness
        lap_start_distance_final = lap_start_distance_from_reference_miter_face
    
    # Default distance_between_lap_and_outside
    if distance_between_lap_and_outside is None:
        distance_between_lap_and_outside = miter_face_width * Rational(1, 5)


    # ========================================================================
    # Step 4: Validate fit
    # ========================================================================
    
    # Check laps fit in depth
    total_lap_depth = lap_start_distance_final + lap_thickness_final * num_laps
    if total_lap_depth >= miter_face_depth:
        raise ValueError(
            f"Laps do not fit in timber depth. "
            f"Total lap depth: {float(total_lap_depth):.3f}, "
            f"Miter face depth: {float(miter_face_depth):.3f}"
        )
    
    # Check laps fit on timberB 
    # TODO fix, you need to mark the lap start/end positions and measure on timberB to see that they are both within the timberB miter face depth
    timberB_miter_face_depth = timberB.get_size_in_face_normal_axis(timberB_reference_miter_face.to.face())
    if total_lap_depth >= timberB_miter_face_depth:
        raise ValueError(
            f"Laps do not fit on timberB. "
            f"Total lap depth: {float(total_lap_depth):.3f}, "
            f"TimberB miter face depth: {float(timberB_miter_face_depth):.3f}"
        )
    
    # ========================================================================
    # Step 5: Find inner face normals and inner shoulder direction
    # ========================================================================
    
    # Determine which faces are on the "inside" of the corner
    # The inside faces are perpendicular to the miter face and point toward each other
    
    # For a corner joint, we need to find the faces that face toward the other timber
    # Use cross product of miter normal and length direction to find the perpendicular faces
    
    # Calculate the diagonal direction (bisector between timberA and timberB)
    # This is the average of the two end directions
    diagonal_direction = normalize_vector(directionA + directionB)
    
    # Find inner faces by looking for the closest oriented face to the negative diagonal direction
    # The negative diagonal points toward the inside of the corner
    negative_diagonal = -diagonal_direction
    timberA_inner_face_enum = timberA.get_closest_oriented_long_face_from_global_direction(negative_diagonal).to.face()
    timberB_inner_face_enum = timberB.get_closest_oriented_long_face_from_global_direction(negative_diagonal).to.face()
    
    # Get the inner face normals
    timberA_inner_face_normal = timberA.get_face_direction_global(timberA_inner_face_enum)
    timberB_inner_face_normal = timberB.get_face_direction_global(timberB_inner_face_enum)
    
    # The inner shoulder axis is the intersection line of the two inner face planes
    # Direction of intersection line = cross product of the two normals
    inner_shoulder_direction = cross_product(timberA_inner_face_normal, timberB_inner_face_normal)
    inner_shoulder_direction = normalize_vector(inner_shoulder_direction)

    # validate that the timber size in the inner_face axis direction is the same on both timbers
    timberA_inner_face_size = timberA.get_size_in_face_normal_axis(timberA_inner_face_enum)
    timberB_inner_face_size = timberB.get_size_in_face_normal_axis(timberB_inner_face_enum)
    if not zero_test(timberA_inner_face_size - timberB_inner_face_size):
        raise ValueError(
            f"Timber widths in the miter plane are not the same. "
            f"TimberA size: {float(timberA_inner_face_size):.3f}, "
            f"TimberB size: {float(timberB_inner_face_size):.3f}"
        )
    
    # ========================================================================
    # Step 6: Create marking transform on timberA
    # ========================================================================
    

    # Find where timberB's centerline intersects timberA's centerline
    timberB_centerline = locate_centerline(timberB)
    centerline_marking = mark_distance_from_end_along_centerline(timberB_centerline, timberA, end=TimberReferenceEnd.BOTTOM)

    marking_position = timberA.get_bottom_position_global()
    marking_position = marking_position + timberA.get_length_direction_global() * centerline_marking.distance
    
    marking_position_on_centerline = marking_position + timberA_miter_face_normal * (-timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.to.face()) / Rational(2))
    
    # Compute the angle between the two timbers to get the correct scale factor
    # The half-angle is the angle between the diagonal and either timber's length direction
    from sympy import acos, sin, sqrt
    cos_angle = safe_dot_product(directionA, directionB)
    timber_angle = acos(cos_angle)  # Angle between the two timbers
    half_angle = timber_angle / Rational(2)  # Angle between diagonal and timber length
    
    # Scale factor for moving along diagonal to achieve perpendicular offset
    # For 90° joint: half_angle = 45°, scale = 1/sin(45°) = sqrt(2)
    # For 180° joint: half_angle = 90°, scale = 1/sin(90°) = 1
    # For 135° joint: half_angle = 67.5°, scale = 1/sin(67.5°)
    diagonal_scale_factor = Rational(1) / sin(half_angle)
    
    # Move to the inner shoulder edge along the diagonal direction
    inner_edge_offset = timberA.get_size_in_face_normal_axis(timberA_inner_face_enum) / Rational(2)
    diagonal_offset = inner_edge_offset * diagonal_scale_factor
    marking_position = marking_position_on_centerline - diagonal_direction * diagonal_offset
    
    # Create orientation for the marking transform
    # Z-axis points toward the end (along timber length direction or opposite)
    if timberA_end == TimberReferenceEnd.TOP:
        marking_z = timberA.get_length_direction_global()
    else:
        marking_z = -timberA.get_length_direction_global()
    
    # X-axis aligns with the inner shoulder direction
    marking_x = inner_shoulder_direction
    
    # Ensure correct orientation (might need to flip based on handedness)
    # Y-axis from cross product
    marking_y = cross_product(marking_z, marking_x)
    marking_y = normalize_vector(marking_y)
    
    # Re-orthogonalize X to be perpendicular to Z
    marking_x = cross_product(marking_y, marking_z)
    marking_x = normalize_vector(marking_x)
    
    # ========================================================================
    # Step 7: Generate finger prisms
    # ========================================================================
    
    # Calculate finger dimensions
    finger_length = lap_thickness_final
    
    # Finger size: X = miter_face_width, Y = miter_face_width * tan(half_angle)
    from sympy import pi, tan
    finger_size_x = miter_face_width
    finger_size_y = miter_face_width * tan(half_angle)
    finger_size = create_v2(finger_size_x, finger_size_y)
    
    # Create all fingers in global space
    all_fingers_global = []
    
    for i in range(num_laps):
        # Determine if this lap belongs to timber A or B
        # Even indices (0, 2, 4, ...) = timber A, odd indices (1, 3, 5, ...) = timber B
        is_timber_a = (i % 2 == 0)
        
        # Calculate Z position along timber length for this lap
        z_offset = lap_start_distance_final + i * lap_thickness_final
        
        # Start from marking_position (at centerline intersection, on miter face surface)
        finger_position = marking_position_on_centerline
        
        # Move along miter face normal (into timber) by z_offset
        finger_position = finger_position + timberA_miter_face_normal * z_offset
        
        # Create finger orientation with Z-axis pointing along miter face normal
        # Z-axis: points along miter face normal (into timber)
        finger_z = timberA_miter_face_normal
        
        # X-axis: along the inner face normal direction based on which timber this lap belongs to
        if is_timber_a:
            finger_x = timberA_inner_face_normal
        else:
            finger_x = timberB_inner_face_normal
        
        # Y-axis: perpendicular to both (computed via cross product)
        finger_y = cross_product(finger_z, finger_x)
        finger_y = normalize_vector(finger_y)
        
        finger_orientation = Orientation(Matrix([
            [finger_x[0], finger_y[0], finger_z[0]],
            [finger_x[1], finger_y[1], finger_z[1]],
            [finger_x[2], finger_y[2], finger_z[2]]
        ]))
        
        # Rotate the finger transform around the inner shoulder edge axis
        finger_transform_global = Transform(position=finger_position, orientation=finger_orientation)
        
        # Create finger prism in global space
        finger_prism_global = RectangularPrism(
            size=finger_size,
            transform=finger_transform_global,
            start_distance=Integer(0),
            end_distance=finger_length
        )
        
        all_fingers_global.append((finger_prism_global, is_timber_a))
    
    # Separate fingers by which timber they belong to (even = A, odd = B)
    A_finger_indices = [i for i in range(num_laps) if i % 2 == 0]
    B_finger_indices = [i for i in range(num_laps) if i % 2 == 1]
    
    # Helper function to convert finger from global to local and apply crop
    def convert_finger_to_local(finger_global: RectangularPrism, target_timber: TimberLike, is_timber_a_finger: bool) -> CutCSG:
        """Convert finger from global to local coordinates and apply crop using opposing timber's inner face."""
        # Determine opposing timber from finger type
        if is_timber_a_finger:
            # Crop A fingers using timberB's inner face
            opposing_timber = timberB
            opposing_inner_face_enum = timberB_inner_face_enum
        else:
            # Crop B fingers using timberA's inner face
            opposing_timber = timberA
            opposing_inner_face_enum = timberA_inner_face_enum
        
        # Convert to local space
        finger_transform_local = finger_global.transform.to_local_transform(target_timber.transform)
        finger_local = replace(finger_global, transform=finger_transform_local)
        
        # Apply crop using the opposing timber's inner face
        from kumiki.measuring import locate_into_face
        from kumiki.rule import safe_transform_vector
        
        # Measure into opposing timber's inner face to create a cutting plane (in global space)
        crop_distance = miter_face_width - distance_between_lap_and_outside
        crop_plane = locate_into_face(crop_distance, opposing_inner_face_enum, opposing_timber)
        
        # Convert crop plane to local space of target timber
        # Convert UnsignedPlane point and normal to local coordinates
        crop_point_local = target_timber.transform.global_to_local(crop_plane.point)
        crop_normal_local = safe_transform_vector(target_timber.orientation.matrix.T, crop_plane.normal)
        
        # Convert to HalfSpace in local coordinates
        crop_offset_local = safe_dot_product(crop_point_local, crop_normal_local)
        # Use negative normal to represent the "too far into opposing timber" side
        crop_halfspace_local = HalfSpace(normal=-crop_normal_local, offset=-crop_offset_local)
        
        # Crop the finger by subtracting everything beyond the half space
        finger_local = Difference(base=finger_local, subtract=[crop_halfspace_local])
        
        return finger_local
    
    # A fingers in timberA local space (for subtracting from timberA)
    A_fingers_in_timberA = []
    for idx in A_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberA, is_timber_a_finger)
        A_fingers_in_timberA.append(finger_local)
    
    # B fingers in timberA local space (for adding voids to timberA)
    B_fingers_in_timberA = []
    for idx in B_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberA, is_timber_a_finger)
        B_fingers_in_timberA.append(finger_local)
    
    # A fingers in timberB local space (for adding voids to timberB)
    A_fingers_in_timberB = []
    for idx in A_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberB, is_timber_a_finger)
        A_fingers_in_timberB.append(finger_local)
    
    # B fingers in timberB local space (for subtracting from timberB)
    B_fingers_in_timberB = []
    for idx in B_finger_indices:
        finger_global, is_timber_a_finger = all_fingers_global[idx]
        finger_local = convert_finger_to_local(finger_global, timberB, is_timber_a_finger)
        B_fingers_in_timberB.append(finger_local)
    
    # ========================================================================
    # Step 7.5: Create Keys
    # ========================================================================

    # Set default key dimensions if not provided
    if key_width is None:
        key_width = lap_thickness_final
    if key_thickness is None:
        key_thickness = lap_thickness_final / Rational(3) 


    key_depth = miter_face_width/sin(half_angle)-distance_between_lap_and_outside/sin(half_angle)    
    
    keys_in_timberA = []
    keys_in_timberB = []
    key_wedges = []
    
    num_keys = num_laps - 1
    for i in range(num_keys):
        key_position = marking_position
        z_offset = lap_start_distance_final + (i+1) * lap_thickness_final
        key_position = key_position + timberA_miter_face_normal * z_offset
        
        # set key_orientation, it should point in the diagonal direction with y axis in the -timberA_miter_face_normal direction
        key_orientation_before_rotation = Orientation.from_z_and_y(
            z_direction=diagonal_direction,
            y_direction=-timberA_miter_face_normal
        )

        # Rotate it around the diagonal direction (X-axis) by the same rotation angle as the fingers
        # This aligns the key with the finger geometry
        from sympy import atan2
        key_rotation_sign = -1 if i % 2 == 0 else 1
        key_rotation_angle = key_rotation_sign * atan2(key_thickness, key_width)
        rotation_for_key = Orientation.from_axis_angle(diagonal_direction, radians(key_rotation_angle))
        key_orientation = rotation_for_key * key_orientation_before_rotation
        key_transform_global = Transform(position=key_position, orientation=key_orientation)
        
        # Create key prism in global space
        # Size: key_width (X) x key_thickness (Y), depth (Z) in start/end_distance
        key_size = create_v2(key_width, key_thickness)
        key_prism_global = RectangularPrism(
            size=key_size,
            transform=key_transform_global,
            start_distance=-key_depth,
            end_distance=key_depth
        )
        
        # Convert to timberA's local space using replace
        key_transform_local_A = key_transform_global.to_local_transform(timberA.transform)
        key_prism_in_timberA = replace(key_prism_global, transform=key_transform_local_A)
        keys_in_timberA.append(key_prism_in_timberA)
        
        # Convert to timberB's local space using replace
        key_transform_local_B = key_transform_global.to_local_transform(timberB.transform)
        key_prism_in_timberB = replace(key_prism_global, transform=key_transform_local_B)
        keys_in_timberB.append(key_prism_in_timberB)
        
        # Create Wedge accessory matching the key prism
        # The wedge has the same transform as the key prism (in global space)
        # base_width and tip_width are the same (key_width) since it's a rectangular shape
        # height is key_thickness, length is 2 * key_depth (from -key_depth to +key_depth)
        key_wedge = Wedge(
            transform=key_transform_global,
            base_width=key_width,
            tip_width=key_width,  # Same as base_width for rectangular shape
            height=key_thickness,
            length=key_depth,
            stickout_length=key_depth*Rational(1,4)
        )
        key_wedges.append(key_wedge)
        
    # ========================================================================
    # Step 8: Create rough end cuts and miter half plane cuts
    # ========================================================================
    
    # Create rough end cuts perpendicular to timbers
    # These cross the corner of the miter
    
    
    if timberA_end == TimberReferenceEnd.TOP:
        # Cut the top: position is outward from marking, normal points up (to cut away top)
        rough_cut_position_A = marking_position + timberA.get_length_direction_global() * finger_size_y
        rough_cut_normal_A_global = timberA.get_length_direction_global()
    else:  # BOTTOM
        # Cut the bottom: position is outward from marking, normal points down (to cut away bottom)
        rough_cut_position_A = marking_position - timberA.get_length_direction_global() * finger_size_y
        rough_cut_normal_A_global = -timberA.get_length_direction_global()
    
    local_normal_A_rough = safe_transform_vector(timberA.orientation.matrix.T, rough_cut_normal_A_global)
    local_offset_A_rough = safe_dot_product(rough_cut_position_A, rough_cut_normal_A_global) - safe_dot_product(rough_cut_normal_A_global, timberA.get_bottom_position_global())
    rough_end_cut_A = HalfSpace(normal=local_normal_A_rough, offset=local_offset_A_rough)
    
    if timberB_end == TimberReferenceEnd.TOP:
        rough_cut_position_B = marking_position + timberB.get_length_direction_global() * finger_size_y
        rough_cut_normal_B_global = timberB.get_length_direction_global()
    else:  # BOTTOM
        rough_cut_position_B = marking_position - timberB.get_length_direction_global() * finger_size_y
        rough_cut_normal_B_global = -timberB.get_length_direction_global()
    
    local_normal_B_rough = safe_transform_vector(timberB.orientation.matrix.T, rough_cut_normal_B_global)
    local_offset_B_rough = safe_dot_product(rough_cut_position_B, rough_cut_normal_B_global) - safe_dot_product(rough_cut_normal_B_global, timberB.get_bottom_position_global())
    rough_end_cut_B = HalfSpace(normal=local_normal_B_rough, offset=local_offset_B_rough)
    
    # Create miter half plane cuts (for negative_csg)
    intersection_point = marking_position
    
    # Create miter plane normal
    normA = normalize_vector(directionA)
    normB = normalize_vector(directionB)
    bisector = normalize_vector(normA + normB)
    plane_normal = cross_product(normA, normB)
    miter_normal = normalize_vector(cross_product(bisector, plane_normal))
    
    # Create HalfSpace cuts for miter planes
    dot_A = safe_dot_product(normA, miter_normal)
    if safe_compare(dot_A, 0, Comparison.GT):
        normalA = miter_normal
    else:
        normalA = -miter_normal
    
    local_normalA = safe_transform_vector(timberA.orientation.matrix.T, normalA)
    local_offsetA = safe_dot_product(intersection_point, normalA) - safe_dot_product(normalA, timberA.get_bottom_position_global())
    
    dot_B = safe_dot_product(normB, miter_normal)
    if safe_compare(dot_B, 0, Comparison.GT):
        normalB = miter_normal
    else:
        normalB = -miter_normal
    
    local_normalB = safe_transform_vector(timberB.orientation.matrix.T, normalB)
    local_offsetB = safe_dot_product(intersection_point, normalB) - safe_dot_product(normalB, timberB.get_bottom_position_global())
    
    miter_half_plane_A = HalfSpace(normal=local_normalA, offset=local_offsetA)
    miter_half_plane_B = HalfSpace(normal=local_normalB, offset=local_offsetB)
    
    # ========================================================================
    # Step 9: Combine cuts and return Joint
    # ========================================================================
    
    # For A fingers: SUBTRACT from timberA's half plane, ADD to timberB's half plane
    # For B fingers: SUBTRACT from timberB's half plane, ADD to timberA's half plane
    
    # TimberA negative_csg:
    # - Start with miter_half_plane_A
    # - Subtract A fingers (they protrude, so remove them from the half plane cut)
    # - Add B fingers (they create voids)
    # - Add keys (they create voids)
    if A_fingers_in_timberA:
        # A fingers subtract from half plane
        miter_cut_A_with_fingers = Difference(miter_half_plane_A, A_fingers_in_timberA)
    else:
        miter_cut_A_with_fingers = miter_half_plane_A
    
    # Collect all voids for timberA: B fingers and keys
    voids_in_A = []
    if B_fingers_in_timberA:
        voids_in_A.extend(B_fingers_in_timberA)
    if keys_in_timberA:
        voids_in_A.extend(keys_in_timberA)
    
    if voids_in_A:
        negative_csg_A = CSGUnion([miter_cut_A_with_fingers] + voids_in_A)
    else:
        negative_csg_A = miter_cut_A_with_fingers
    
    # TimberB negative_csg:
    # - Start with miter_half_plane_B
    # - Subtract B fingers (they protrude)
    # - Add A fingers (they create voids)
    # - Add keys (they create voids)
    if B_fingers_in_timberB:
        # B fingers subtract from half plane
        miter_cut_B_with_fingers = Difference(miter_half_plane_B, B_fingers_in_timberB)
    else:
        miter_cut_B_with_fingers = miter_half_plane_B
    
    # Collect all voids for timberB: A fingers and keys
    voids_in_B = []
    if A_fingers_in_timberB:
        voids_in_B.extend(A_fingers_in_timberB)
    if keys_in_timberB:
        voids_in_B.extend(keys_in_timberB)
    
    if voids_in_B:
        negative_csg_B = CSGUnion([miter_cut_B_with_fingers] + voids_in_B)
    else:
        negative_csg_B = miter_cut_B_with_fingers
    
    # Create Cutting objects
    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut=rough_end_cut_A if timberA_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=rough_end_cut_A if timberA_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=negative_csg_A
    )
    
    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut=rough_end_cut_B if timberB_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut=rough_end_cut_B if timberB_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=negative_csg_B
    )
    
    # Create CutTimber objects
    cut_timberA = CutTimber(timberA, cuts=[cutA])
    cut_timberB = CutTimber(timberB, cuts=[cutB])


    # Create jointAccessories dict with key wedges
    joint_accessories = {}
    for i, wedge in enumerate(key_wedges):
        joint_accessories[f"key_{i}"] = wedge
    
    # Return Joint
    return Joint(
        cut_timbers={
            timberA.ticket.name: cut_timberA,
            timberB.ticket.name: cut_timberB
        },
        ticket=JointTicket(joint_type="mitered_and_keyed_lap"),
        jointAccessories=joint_accessories,
    )


# ============================================================================
# Aliases for Japanese joint functions
# ============================================================================

cut_腰掛鎌継ぎ = cut_lapped_gooseneck_joint
cut_koshikake_kama_tsugi = cut_lapped_gooseneck_joint

cut_蟻仕口 = cut_housed_dovetail_butt_joint
cut_ari_shiguchi = cut_housed_dovetail_butt_joint

cut_箱相欠き車知栓仕口 = cut_mitered_and_keyed_lap_joint
cut_hako_aikaki_shachi_sen_shikuchi = cut_mitered_and_keyed_lap_joint