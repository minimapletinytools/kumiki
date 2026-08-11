"""
Kumiki - Splice joint construction functions
Contains butt splice, splice lap, and lapped gooseneck joint implementations.
"""

import warnings

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *
from .shavings.shavings import draw_gooseneck_polygon
from .shavings.relief import warn_if_arrangement_timbers_imperfect
from kumiki.measuring import locate_top_center_position, locate_bottom_center_position, mark_distance_from_end_along_centerline, mark_distance_from_face_in_normal_direction


# Aliases for backwards compatibility
CSGUnion = SolidUnion


# ============================================================================
# Splice Joint Construction Functions
# ============================================================================


def cut_plain_butt_splice_joint_on_aligned_timbers(arrangement: SpliceJointTimberArrangement, splice_point: Optional[V3] = None) -> Joint:
    """
    Creates a plain butt splice joint between two parallel timbers cut at a shared plane.

    Both timbers are cut at the splice plane, creating a flush end-to-end connection.

    Args:
        arrangement: Splice joint arrangement with timber1, timber2, timber1_end, timber2_end.
                     Timbers must have parallel length axes.
        splice_point: Point where the splice occurs. If not provided, the midpoint between
            the two timber ends is used. If provided but off the centerline, it is projected
            onto timber1's centerline.

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        ValueError: If the timbers do not have parallel length axes.
    """
    from kumiki.construction import _are_directions_parallel

    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end

    # Assert that the length axes are parallel
    if not _are_directions_parallel(timberA.get_length_direction_global(), timberB.get_length_direction_global()):
        raise ValueError("Timbers must have parallel length axes for a splice joint")

    # Get the end positions for each timber
    if timberA_end == TimberEnd.TOP:
        endA_position = locate_top_center_position(timberA).position
        directionA = timberA.get_length_direction_global()
    else:  # BOTTOM
        endA_position = locate_bottom_center_position(timberA).position
        directionA = -timberA.get_length_direction_global()

    if timberB_end == TimberEnd.TOP:
        endB_position = locate_top_center_position(timberB).position
        directionB = timberB.get_length_direction_global()
    else:  # BOTTOM
        endB_position = locate_bottom_center_position(timberB).position
        directionB = -timberB.get_length_direction_global()

    # Normalize length direction for later use
    length_dir_norm = normalize_vector(timberA.get_length_direction_global())

    # Calculate or validate the splice point
    if splice_point is None:
        # Calculate as the midpoint between the two timber ends
        splice_point = (endA_position + endB_position) / 2
    else:
        # Project the splice point onto timberA's centerline if it's not already on it
        # Vector from timberA's bottom to the splice point
        to_splice = splice_point - timberA.get_bottom_position_global()

        # Project onto the centerline
        distance_along_centerline = safe_dot_product(to_splice, length_dir_norm)
        projected_point = timberA.get_bottom_position_global() + length_dir_norm * distance_along_centerline

        # Check if the point needed projection (warn if not on centerline)
        distance_from_centerline = vector_magnitude(splice_point - projected_point)
        if not zero_test(distance_from_centerline):
            warnings.warn(f"Splice point was not on timberA's centerline (distance: {float(distance_from_centerline)}). Projecting onto centerline.")
            splice_point = projected_point

    # Check if timber cross sections overlap (approximate check using bounding boxes)
    # Project both timber cross-sections onto a plane perpendicular to the length direction
    # For simplicity, we'll warn if the centerlines are far apart
    centerline_distance = vector_magnitude(
        (splice_point - timberA.get_bottom_position_global()) -
        length_dir_norm * safe_dot_product(splice_point - timberA.get_bottom_position_global(), length_dir_norm) -
        ((splice_point - timberB.get_bottom_position_global()) -
         length_dir_norm * safe_dot_product(splice_point - timberB.get_bottom_position_global(), length_dir_norm))
    )

    # Approximate overlap check: centerlines should be close
    max_dimension = max(timberA.size[0], timberA.size[1], timberB.size[0], timberB.size[1])
    if centerline_distance > max_dimension / scalar(2):
        warnings.warn(f"Timber cross sections may not overlap (centerline distance: {float(centerline_distance)}). Check joint geometry.")

    # Calculate distance from each timber end to the splice point
    distance_A_from_bottom = safe_dot_product(splice_point - timberA.get_bottom_position_global(), timberA.get_length_direction_global())
    distance_A_from_end = timberA.length - distance_A_from_bottom if timberA_end == TimberEnd.TOP else distance_A_from_bottom

    distance_B_from_bottom = safe_dot_product(splice_point - timberB.get_bottom_position_global(), timberB.get_length_direction_global())
    distance_B_from_end = timberB.length - distance_B_from_bottom if timberB_end == TimberEnd.TOP else distance_B_from_bottom

    # Assembly: a plain butt splice has no engagement — each half pulls back
    # along its own axis and is free after 0 travel. Disassembly code adds its
    # own visual-separation padding on top of freed_after, so no nominal
    # travel is needed here.
    endA_direction = timberA.get_face_direction_global(timberA_end)
    endB_direction = timberB.get_face_direction_global(timberB_end)

    # Create the Cuts
    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=distance_A_from_bottom if timberA_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=distance_A_from_bottom if timberA_end == TimberEnd.BOTTOM else None,
        negative_csg=None,
        assembly_freedom=AssemblyFreedom.translation(-endA_direction, freed_after=scalar(0)),
    )

    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=distance_B_from_bottom if timberB_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=distance_B_from_bottom if timberB_end == TimberEnd.BOTTOM else None,
        negative_csg=None,
        assembly_freedom=AssemblyFreedom.translation(-endB_direction, freed_after=scalar(0)),
    )

    # Create CutTimbers with cuts passed at construction
    cut_timberA = cutA
    cut_timberB = cutB

    # Create and return the Joint with all data at construction
    joint = Joint(
        cuttings={"timberA": cut_timberA, "timberB": cut_timberB},
        ticket=JointTicket(joint_type="plain_butt_splice"),
        jointAccessories={},
    )

    return joint


def cut_plain_splice_lap_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
    lap_length: Numeric,
    # TODO rename to top_lap_shoulder_position_from_timber1_end
    top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Numeric,
    lap_depth: Optional[Numeric] = None
) -> Joint:
    """
    Creates a splice lap joint between two parallel timber ends with interlocking relief cuts.

    One timber has material removed from the specified face; the other has material
    removed from the opposite face. Timbers must be parallel and face-aligned.

        arrangement.front_face_on_timber1
        v           |--------| lap_length
    ╔════════════════════════╗╔══════╗  -
    ║timber1                 ║║      ║  | lap_depth
    ║               ╔════════╝║      ║  -
    ║               ║╔════════╝      ║
    ║               ║║ timber2       ║
    ╚═══════════════╝╚═══════════════╝
                    ^ top_lap_shoulder_position_from_top_lap_shoulder_timber_end

    Args:
        arrangement: Splice joint arrangement with timber1, timber2, timber1_end, timber2_end,
                     and optionally front_face_on_timber1 (the lap cut face on timber1).
                     If front_face_on_timber1 is None, defaults to FRONT face.
                     Timbers must be parallel and face-aligned.
        lap_length: Length of the lap region along the timber length.
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Distance from the
            timber1 end to the shoulder, measured inward along the timber.
        lap_depth: Depth of material to remove perpendicular to the face. If None,
            defaults to half the timber thickness in the face normal axis.

    Returns:
        Joint object containing the two CutTimbers with lap cuts.
    """
    # Extract arrangement fields
    top_lap_timber = arrangement.timber1
    top_lap_timber_end = arrangement.timber1_end
    bottom_lap_timber = arrangement.timber2
    bottom_lap_timber_end = arrangement.timber2_end
    top_lap_timber_face = arrangement.front_face_on_timber1 if arrangement.front_face_on_timber1 is not None else TimberLongFace.FRONT


    # Calculate default lap_depth if not provided
    if lap_depth is None:
        # Use half the thickness in the axis perpendicular to top_lap_timber_face
        if top_lap_timber_face == TimberLongFace.LEFT or top_lap_timber_face == TimberLongFace.RIGHT:
            # Face is on Y-axis, so thickness is in Y direction (height)
            lap_depth = top_lap_timber.size[1] / scalar(2)
        else:  # TOP or BOTTOM
            # Face is on Z-axis (end face), use the smaller of width/height
            lap_depth = min(top_lap_timber.size[0], top_lap_timber.size[1]) / scalar(2)

    # Create the CSG cuts using the helper function
    # Returns tuples of (lap_prism, end_cut) for each timber
    (top_lap_prism, top_end_cut), (bottom_lap_prism, bottom_end_cut) = chop_lap_on_timber_ends(
        top_lap_timber=top_lap_timber,
        top_lap_timber_end=top_lap_timber_end,
        bottom_lap_timber=bottom_lap_timber,
        bottom_lap_timber_end=bottom_lap_timber_end,
        top_lap_timber_face=top_lap_timber_face,
        lap_length=lap_length,
        lap_depth=lap_depth,
        top_lap_shoulder_position_from_top_lap_shoulder_timber_end=top_lap_shoulder_position_from_top_lap_shoulder_timber_end
    )

    # Create Cuts for both timbers with separated lap and end cuts
    top_end_cut_distance_from_bottom = (
        top_end_cut.offset
        if top_lap_timber_end == TimberEnd.TOP
        else -top_end_cut.offset
    )
    bottom_end_cut_distance_from_bottom = (
        bottom_end_cut.offset
        if bottom_lap_timber_end == TimberEnd.TOP
        else -bottom_end_cut.offset
    )

    # Assembly: the laps separate perpendicular to the lap plane — the top-lap
    # timber lifts along the lap face normal, the bottom-lap timber the other
    # way. Either member is free after traveling the full thickness.
    lap_face_normal_global = top_lap_timber.get_face_direction_global(top_lap_timber_face.to.face())
    lap_thickness = top_lap_timber.get_size_in_face_normal_axis(top_lap_timber_face)

    cut_top = Cutting(
        timber=top_lap_timber,
        maybe_top_end_cut_distance_from_bottom=top_end_cut_distance_from_bottom if top_lap_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=top_end_cut_distance_from_bottom if top_lap_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=top_lap_prism,
        assembly_freedom=AssemblyFreedom.translation(lap_face_normal_global, freed_after=lap_thickness),
    )

    cut_bottom = Cutting(
        timber=bottom_lap_timber,
        maybe_top_end_cut_distance_from_bottom=bottom_end_cut_distance_from_bottom if bottom_lap_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=bottom_end_cut_distance_from_bottom if bottom_lap_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=bottom_lap_prism,
        assembly_freedom=AssemblyFreedom.translation(-lap_face_normal_global, freed_after=lap_thickness),
    )

    # Create CutTimbers
    cut_top_timber = cut_top
    cut_bottom_timber = cut_bottom

    # Create and return the Joint
    joint = Joint(
        cuttings={"top_lap_timber": cut_top_timber, "bottom_lap_timber": cut_bottom_timber},
        ticket=JointTicket(joint_type="plain_splice_lap"),
        jointAccessories={},
    )

    return joint


# ============================================================================
# Japanese splice joints (moved from japanese_joints.py)
# ============================================================================


# TODO comment where the start of the gooseneck is determined
# TODO add a shoulder_position_from_timberx_end parameter to specify the position (should be right where the gooseneck shape starts in one direction and the lap starts in the other direction)
def cut_lapped_gooseneck_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
    gooseneck_length: Numeric,
    gooseneck_small_width: Numeric,
    gooseneck_large_width: Numeric,
    gooseneck_head_length: Numeric,
    lap_length: Numeric = scalar(0), # 0 just means no lap
    gooseneck_lateral_offset: Numeric = scalar(0),
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
    warn_if_arrangement_timbers_imperfect(arrangement)
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
    if receiving_timber_end == TimberEnd.TOP:
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
        ) / scalar(2)

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
    if receiving_timber_end == TimberEnd.TOP:
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

    if gooseneck_timber_end == TimberEnd.TOP:
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

    if gooseneck_timber_end == TimberEnd.TOP:
        # End cut at distance from top
        gooseneck_end_cut_local_z = gooseneck_timber.length - gooseneck_end_position_from_timber_end
        gooseneck_timber_end_cut = HalfSpace(normal=create_v3(0, 0, 1), offset=gooseneck_end_cut_local_z)
    else:  # BOTTOM
        # End cut at distance from bottom
        # TODO this case seems to be broken?
        gooseneck_end_cut_local_z = gooseneck_end_position_from_timber_end
        gooseneck_timber_end_cut = HalfSpace(normal=create_v3(0, 0, -1), offset=-gooseneck_end_cut_local_z)

    receiving_end_cut_local_z = None
    if receiving_timber_end_cut is not None:
        receiving_end_cut_local_z = (
            receiving_timber_end_cut.offset
            if receiving_timber_end == TimberEnd.TOP
            else -receiving_timber_end_cut.offset
        )

    # Transform the gooseneck profile CSG from gooseneck_timber coordinates to receiving_timber coordinates
    # Use the generic adopt_csg function to handle all CSG types (SolidUnion, Difference, RectangularPrism, etc.)
    gooseneck_csg_on_receiving_timber = adopt_csg(gooseneck_timber.transform, receiving_timber.transform, gooseneck_profile_csg)

    if lap_length > 0:
        receiving_timber_negative_csg: CutCSG = CSGUnion([receiving_timber_lap_prism, gooseneck_csg_on_receiving_timber])
    else:
        receiving_timber_negative_csg = gooseneck_csg_on_receiving_timber

    # Assembly: the real extraction is lifting the head out of the socket and
    # THEN sliding along the run (a sequenced motion), which cannot be
    # expressed as a single half-interval translation yet. As an approximation
    # until richer R6 freedom shapes exist, treat it as a straight lift along
    # front_face_on_timber1, freed after gooseneck_depth of travel.
    gooseneck_timber_freedom = AssemblyFreedom.translation(gooseneck_face_direction, freed_after=gooseneck_depth)
    receiving_timber_freedom = AssemblyFreedom.translation(-gooseneck_face_direction, freed_after=gooseneck_depth)

    # Create Cut objects for each timber
    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        maybe_top_end_cut_distance_from_bottom=receiving_end_cut_local_z if receiving_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=receiving_end_cut_local_z if receiving_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=receiving_timber_negative_csg,
        assembly_freedom=receiving_timber_freedom,
    )
    gooseneck_timber_cut_obj = Cutting(
        timber=gooseneck_timber,
        maybe_top_end_cut_distance_from_bottom=gooseneck_end_cut_local_z if gooseneck_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=gooseneck_end_cut_local_z if gooseneck_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=gooseneck_timber_combined_csg,
        assembly_freedom=gooseneck_timber_freedom,
    )

    return Joint(
        cuttings={
            receiving_timber.ticket.path: receiving_timber_cut_obj,
            gooseneck_timber.ticket.path: gooseneck_timber_cut_obj
        },
        ticket=JointTicket(joint_type="lapped_gooseneck"),
        jointAccessories={},
    )



def cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(
        arrangement: SpliceJointTimberArrangement,
        stepped_shoulder_depth: Numeric,
        scarf_length: Numeric,
        dado_depth: Numeric,
        dado_height: Numeric, 
        # TODO add support to handle stub_tenon_width = 0 without generating extra dud geometry, also set this to 0 by defalut I guess?
        stub_tenon_width: Numeric,
        stepped_shoulder_length: Optional[Numeric] = None,
        joint_center_relative_to_timber1_end: Numeric = scalar(0),
        lateral_offset_from_midline: Numeric = scalar(0)) -> Joint:
    """
    arrangement.front_face_on_timber1 determines the face which scarf cut profile is visible on.

    Args:
        arrangement:
        stepped_shoulder_depth: (Tsuki-tsuke (突付)) determines the depth of the stepped shoulder cut in the scarf joint, the 2 stepped shoulders form the pin hole for the square peg forming the Kusabi-ana (楔穴)
        scarf_length: determines the length of the scarf cut on ecah timber, it is meansured the corner that lies on the midline of the scarf joint of the opposite dadoes of the joint when fully assembled
        dado_depth: the "depth" of both dadoes (measured in the length axis of the timbers)
        dado_height: the "height" of both dadoes (measured in the long face axis of the long face adjacent front_face_on_timber1), the dado width is always the entire size of the timber in the front_face_on_timber1 axis
        stub_tenon_width: the "width" of the stub tenon (measured in the long face axis of the long face adjacent front_face_on_timber1), the stub tenon depth is always the distance from the surface to the dado wall.
        stepped_shoulder_length: determines the length of the stepped shoulder cut in the scarf joint, if None, defaults to stepped_shoulder_depth (forming a rectangular peg hole)
        joint_center_relative_to_timber1_end: determines the "center" of the joint (right in the middle of the rectangular peg hole) measured inward from the joint end of timber1. (positive means the joint center is further into timber1)
        lateral_offset_from_midline: determines the lateral offset of the joint profiles centerline from the midline of front_face_on_timber1

    Returns:

    Notes:
        the oblique scarf face angle (Sogi-michi (斜面)) is determined by the stepped_shoulder_depth and the scarf_half_length
        all measurements are done relative to timber1, timber2 is expected to share the same axis and be the same size as timber1.
    """
    require_check(arrangement.check_face_aligned_and_parallel_axis())
    # TODO assert timber2 is same size as timber1
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the joint orientation"
    )

    timber1 = arrangement.timber1
    timber2 = arrangement.timber2
    timber1_end = arrangement.timber1_end
    timber2_end = arrangement.timber2_end
    front_face = arrangement.front_face_on_timber1
    v_face = front_face.rotate_right()
    

    if stepped_shoulder_length is None:
        stepped_shoulder_length = stepped_shoulder_depth

    SL = scarf_length
    DD = dado_depth
    DH = dado_height
    SSD = stepped_shoulder_depth
    SSL = stepped_shoulder_length
    STW = stub_tenon_width

    require_check(
        None if SSL == SSD
        else "stepped_shoulder_length must equal stepped_shoulder_depth: the Kusabi peg accessory "
             "(kumiki.timber.Peg) only supports a square or round cross-section, so a non-square "
             "peg hole can't yet be represented by an accessory"
    )
    require_check(None if DD > 0 else "dado_depth must be positive")
    require_check(None if DH > 0 else "dado_height must be positive")
    require_check(None if SSD > 0 else "stepped_shoulder_depth must be positive")
    require_check(None if SL > 0 else "scarf_length must be positive")
    require_check(None if STW > 0 else "stub_tenon_width must be positive")

    H = timber1.get_size_in_face_normal_axis(v_face)
    depth_size = timber1.get_size_in_face_normal_axis(front_face)

    require_check(None if STW < depth_size else "stub_tenon_width must be less than the timber's dimension in the front_face_on_timber1 normal axis")
    require_check(None if DH < H / scalar(2) else "dado_height must be less than half the timber's dimension in the front_face_on_timber1-adjacent axis")
    require_check(None if DD < (SL - SSD) / scalar(2) else "dado_depth must be less than (scarf_length - stepped_shoulder_depth) / 2")
    require_check(None if DH >= SSD else "dado_height must be at least stepped_shoulder_depth")


    # determine the scarf joint center is global space:
    # it is in the plane of front_face_on_timber1
    # from the appropriat end of timber1 translate by  joint_center_relative_to_timber1_end in the appropritae direction
    # then translate laterally by lateral_offset_from_midline in the local axis perpendicular to the length axis and front_face_on_timber1 axis (TODO make sure sign convention is consistent, should this be relative to timber as it is in the comment right now or relative to the joint arrangment? I forget!)

    # u_dir: +u = "towards timber1" = further into timber1's body, away from the joint end.
    # (get_face_direction_global(timber1_end) is the OUTWARD normal at that end, i.e.
    # pointing away from the body, so its negation points into the body.)
    u_dir = -timber1.get_face_direction_global(timber1_end)
    v_dir = timber1.get_face_direction_global(v_face)

    # TODO is this the sign we want?
    lateral_dir = arrangement.timber1.get_face_direction_global(front_face)

    if timber1_end == TimberEnd.TOP:
        timber1_end_position_global = locate_top_center_position(timber1).position
    else:
        timber1_end_position_global = timber1.get_bottom_position_global()

    scarf_joint_center_global = timber1_end_position_global + u_dir * joint_center_relative_to_timber1_end + lateral_dir * lateral_offset_from_midline


    # -------------------------------------------------------------------------
    # Profile points (see the docstring diagram / step comments below for the
    # derivation). All in the shared (u, v) marking frame.
    #
    #   "right"/+u = towards timber1, "up"/+v = towards +v_dir.
    #   first find the "corner of the dado" by going right by scarf_length / 2
    #   1. from the corner of the dado go up by dado_height
    #   2. then go left by dado_depth
    #   3. then go up to the face of timber1 ("stub_tenon_face")
    #   starting back at the corner of the dado, the other side of the profile:
    #   4. go left by (scarf_length + stepped_shoulder_length)/2 and down by
    #      stepped_shoulder_depth/2 (the lower oblique scarf face)
    #   5. then go up by stepped_shoulder_depth (the peg-hole wall)
    #   6. go to the opposite corner of the dado: left by
    #      (scarf_length - stepped_shoulder_length)/2 and up by stepped_shoulder_depth/2
    #      (the upper oblique scarf face)
    #   7. go down by dado_height
    #   8. go right by dado_depth
    #   9. go down to the face of timber1
    #
    # NOTE: steps 4 and 6 use stepped_shoulder_length (not stepped_shoulder_depth)
    # for their horizontal component — the pseudocode this was transcribed from
    # only ever wrote stepped_shoulder_depth there, which left stepped_shoulder_length
    # unused. Substituting it here is what gives that parameter any effect, and it
    # reproduces the literal pseudocode exactly whenever stepped_shoulder_length
    # defaults to stepped_shoulder_depth (the "rectangular peg hole" case) — the
    # oblique-angle claim in the docstring is about that default case.
    # -------------------------------------------------------------------------
    corner = (SL / scalar(2), scalar(0))
    p1 = (corner[0], DH)
    p2 = (p1[0] - DD, DH)
    p3 = (p2[0], H / scalar(2))
    p4 = (corner[0] - (SL + SSL) / scalar(2), -SSD / scalar(2))
    p5 = (p4[0], SSD / scalar(2))
    p6 = (p5[0] - (SL - SSL) / scalar(2), 0)
    p7 = (p6[0], p6[1] - DH)
    p8 = (p7[0] + DD, p7[1])
    p9 = (p8[0], -H / scalar(2))

    # so the complete profile is now
    # profile_points = [p3, p2, p1, corner, p4, p5, p6, p7, p8, p9]

    # Close the profile: mark a plane orthogonal to the length axis scarf_length/2
    # left of the center point (u = -scarf_length/2, the same u as p6/p7), extend
    # p3 and p9 out to it (p10, p11), and connect them with a vertical line. This
    # closing edge runs along the timber's own top/bottom faces (p10-p3 at
    # v = H/2, p9-p11 at v = -H/2) and the left wall (p11-p10 at u = -SL/2), so it
    # doesn't cut anything by itself — it just closes the boundary into a proper
    # simple polygon.
    left_boundary_u = -SL / scalar(2)
    p10 = (left_boundary_u, p3[1])
    p11 = (left_boundary_u, p9[1])
    profile_points = [p3, p2, p1, corner, p4, p5, p6, p7, p8, p9, p11, p10]

    # -------------------------------------------------------------------------
    # TEST-ONLY: decompose the profile into convex pieces and cut it out of
    # timber1 alone, extruded generously through the front_face_on_timber1 axis
    # in both directions, just to check the profile shape by itself before
    # building out timber2, the stub tenon, and assembly freedoms.
    #
    # ConvexPolygonExtrusion requires convex polygons; profile_points as a whole
    # is not convex — and worse, v is not monotonic along the boundary (e.g. it
    # descends corner -> p4 then climbs back up p4 -> p5 -> p6), so a naive
    # "one convex piece per edge, from that edge out to the left wall" pass is
    # WRONG wherever v-ranges from different edges overlap: e.g. p1-corner
    # (v in [0, DH], reaching out to u=corner) and p4-p5 (v in [-SSD/2, SSD/2],
    # only reaching to u=p4) both cover v in [0, SSD/2] — the true boundary
    # there is the peg-hole wall at p4, not corner, since the peg-hole is a
    # notch cut INTO the region p1-corner would otherwise claim. Decomposing
    # per edge misses that the two interact.
    #
    # decompose_simple_polygon_into_convex_pieces handles this generally via
    # horizontal (constant-v) trapezoidal decomposition: split at every
    # vertex's v, and within each band pick up ALL edges active there, pairing
    # up their u-crossings left-to-right by the even-odd rule (matching
    # standard polygon-fill semantics) rather than assuming one edge per band.
    # -------------------------------------------------------------------------
    depth_dir = timber1.get_face_direction_global(front_face)
    profile_orientation = Orientation(Matrix([
        [u_dir[0], v_dir[0], depth_dir[0]],
        [u_dir[1], v_dir[1], depth_dir[1]],
        [u_dir[2], v_dir[2], depth_dir[2]],
    ]))
    profile_transform = Transform(position=scarf_joint_center_global, orientation=profile_orientation)

    convex_pieces = [
        ConvexPolygonExtrusion(
            points=quad,
            transform=profile_transform,
            # TODO instead of extruding depth_size, find the distance from the center to the actual faces of the timber so we're only cutting a minimal amount.
            start_distance=-depth_size,
            end_distance=depth_size,
        )
        for quad in decompose_simple_polygon_into_convex_pieces(
            [create_v2(u, v) for (u, v) in profile_points]
        )
    ]

    timber1_profile_csg_global = SolidUnion(convex_pieces)

    
    def reflect(p: Tuple[Numeric, Numeric]) -> Tuple[Numeric, Numeric]:
        return (-p[0], -p[1])

    corner2 = reflect(corner)
    p1_2 = reflect(p1)
    p2_2 = reflect(p2)
    p3_2 = reflect(p3)
    p4_2 = reflect(p4)
    p5_2 = reflect(p5)
    p6_2 = reflect(p6)
    p7_2 = reflect(p7)
    p8_2 = reflect(p8)
    p9_2 = reflect(p9)

    right_boundary_u = -left_boundary_u
    p10_2 = (right_boundary_u, p9_2[1])
    p11_2 = (right_boundary_u, p3_2[1])
    profile_points_2 = [p3_2, p2_2, p1_2, corner2, p4_2, p5_2, p6_2, p7_2, p8_2, p9_2, p10_2, p11_2]

    convex_pieces_2 = [
        ConvexPolygonExtrusion(
            points=quad,
            transform=profile_transform,
            start_distance=-depth_size,
            end_distance=depth_size,
        )
        for quad in decompose_simple_polygon_into_convex_pieces(
            [create_v2(u, v) for (u, v) in profile_points_2]
        )
    ]

    timber2_profile_csg_global = SolidUnion(convex_pieces_2)



    # now lets make the stub tenons
    v_face_size = timber1.get_size_in_face_normal_axis(v_face)
    timber1_stub_tenon_middle_surface_outer_edge_point = scarf_joint_center_global - scarf_length / scalar(2) * u_dir - v_dir * v_face_size / scalar(2)
    timber1_stub_tenon_middle_surface_inner_edge_point = timber1_stub_tenon_middle_surface_outer_edge_point + u_dir * dado_depth
    timber1_stub_tenon_start = (timber1_stub_tenon_middle_surface_outer_edge_point + timber1_stub_tenon_middle_surface_inner_edge_point) / scalar(2)
    timber1_stub_tenon_prism = RectangularPrism(
        transform=Transform(position=timber1_stub_tenon_start, orientation=Orientation.from_z_and_y(v_dir, u_dir)),
        start_distance = 0,
        end_distance = v_face_size / scalar(2) - dado_depth,
        size = create_v2(stub_tenon_width, dado_depth),
    )

    def reflect_about_joint_center(point : V3):
        relative = point - scarf_joint_center_global
        reflected = -relative
        return reflected + scarf_joint_center_global

    timber2_stub_tenon_prism = RectangularPrism(
        transform=Transform(position=reflect_about_joint_center(timber1_stub_tenon_start), orientation=Orientation.from_z_and_y(-v_dir, -u_dir)),
        start_distance = 0,
        end_distance = v_face_size / scalar(2) - dado_depth,
        size = create_v2(stub_tenon_width, dado_depth),
    )


    timber1_with_stubs_global = SolidUnion([Difference(timber1_profile_csg_global, [timber1_stub_tenon_prism]), timber2_stub_tenon_prism])
    timber1_negative_csg_local = adopt_csg(None, timber1.transform, timber1_with_stubs_global)

    timber2_with_stubs_global = SolidUnion([Difference(timber2_profile_csg_global, [timber2_stub_tenon_prism]), timber1_stub_tenon_prism])
    timber2_negative_csg_local = adopt_csg(None, timber2.transform, timber2_with_stubs_global)

    left_boundary_global = scarf_joint_center_global + u_dir * left_boundary_u
    left_boundary_distance_from_bottom = safe_dot_product(
        left_boundary_global - timber1.get_bottom_position_global(),
        timber1.get_length_direction_global(),
    )

    right_boundary_global = scarf_joint_center_global + u_dir * right_boundary_u
    right_boundary_distance_from_bottom = safe_dot_product(
        right_boundary_global - timber2.get_bottom_position_global(),
        timber2.get_length_direction_global(),
    )

    # Assembly: the first disassembly motion is sliding along the lower
    # oblique scarf face, i.e. the line from "corner" to p4 (see step 4
    # above), freed after dado_depth of travel. timber1 slides in the
    # corner->p4 direction, timber2 slides the opposite way (the same
    # pattern used for the gooseneck joint above). Fully separating the
    # joint actually requires a SECOND, follow-up step sliding along
    # front_face_on_timber1's normal (to clear the half-blind stub tenon) —
    # that sequenced (slide-then-lift) motion isn't expressible as a single
    # translation yet.
    disassembly_direction = u_dir * (p4[0] - corner[0]) + v_dir * (p4[1] - corner[1])
    timber1_freedom = AssemblyFreedom.translation(-disassembly_direction, freed_after=DD)
    timber2_freedom = AssemblyFreedom.translation(disassembly_direction, freed_after=DD)

    timber1_test_cut = Cutting(
        timber=timber1,
        maybe_top_end_cut_distance_from_bottom=left_boundary_distance_from_bottom if timber1_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=left_boundary_distance_from_bottom if timber1_end == TimberEnd.BOTTOM else None,
        negative_csg=timber1_negative_csg_local,
        label="half_blind_tenoned_dadoed_rabbeted_scarf_TEST_PROFILE_ONLY",
        assembly_freedom=timber1_freedom,
    )

    timber2_test_cut = Cutting(
        timber=timber2,
        maybe_top_end_cut_distance_from_bottom=right_boundary_distance_from_bottom if timber2_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=right_boundary_distance_from_bottom if timber2_end == TimberEnd.BOTTOM else None,
        negative_csg=timber2_negative_csg_local,
        label="half_blind_tenoned_dadoed_rabbeted_scarf_TEST_PROFILE_ONLY",
        assembly_freedom=timber2_freedom,
    )
    front_face_dir = arrangement.timber1.get_face_direction_global(arrangement.front_face_on_timber1)

    # TODO don't use a peg, use a wedge
    peg = Peg(
            transform = Transform(position = scarf_joint_center_global, orientation=Orientation.from_z_and_y(front_face_dir, v_dir)),
            size = stepped_shoulder_depth,
            shape = PegShape.SQUARE,
            forward_length = depth_size * scalar(3/5),
            stickout_length = depth_size * scalar(3/5),

    )

    return Joint(
        cuttings={
            timber1.ticket.path: timber1_test_cut,
            timber2.ticket.path: timber2_test_cut,
        },
        ticket=JointTicket(joint_type="half_blind_tenoned_dadoed_rabbeted_scarf"),
        jointAccessories={"peg": peg},
    )


# ============================================================================
# Aliases for Japanese joint functions
# ============================================================================

cut_腰掛鎌継ぎ_joint_on_aligned_timbers = cut_lapped_gooseneck_joint_on_aligned_timbers
cut_koshikake_kama_tsugi_joint_on_aligned_timbers = cut_lapped_gooseneck_joint_on_aligned_timbers
cut_kanawa_tsugi_joint_on_aligned_timbers = cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers