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
from .shavings.notching import warn_if_arrangement_timbers_imperfect
from kumiki.measuring import locate_top_center_position, locate_bottom_center_position, mark_distance_from_end_along_centerline, mark_distance_from_face_in_normal_direction


_raw_safe_dot_product = safe_dot_product
_raw_safe_norm = safe_norm
_raw_safe_transform_vector = safe_transform_vector


def safe_dot_product(*args, **kwargs):
    return prune(_raw_safe_dot_product(*args, **kwargs))


def safe_norm(*args, **kwargs):
    return prune(_raw_safe_norm(*args, **kwargs))


def safe_transform_vector(*args, **kwargs):
    return prune(_raw_safe_transform_vector(*args, **kwargs))


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
        from kumiki.rule import safe_dot_product
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
    from kumiki.rule import safe_dot_product
    centerline_distance = vector_magnitude(
        (splice_point - timberA.get_bottom_position_global()) -
        length_dir_norm * safe_dot_product(splice_point - timberA.get_bottom_position_global(), length_dir_norm) -
        ((splice_point - timberB.get_bottom_position_global()) -
         length_dir_norm * safe_dot_product(splice_point - timberB.get_bottom_position_global(), length_dir_norm))
    )

    # Approximate overlap check: centerlines should be close
    max_dimension = max(timberA.size[0], timberA.size[1], timberB.size[0], timberB.size[1])
    from sympy import Rational
    if centerline_distance > max_dimension / Rational(2):
        warnings.warn(f"Timber cross sections may not overlap (centerline distance: {float(centerline_distance)}). Check joint geometry.")

    # Calculate distance from each timber end to the splice point
    distance_A_from_bottom = safe_dot_product(splice_point - timberA.get_bottom_position_global(), timberA.get_length_direction_global())
    distance_A_from_end = timberA.length - distance_A_from_bottom if timberA_end == TimberEnd.TOP else distance_A_from_bottom

    distance_B_from_bottom = safe_dot_product(splice_point - timberB.get_bottom_position_global(), timberB.get_length_direction_global())
    distance_B_from_end = timberB.length - distance_B_from_bottom if timberB_end == TimberEnd.TOP else distance_B_from_bottom

    # Create the Cuts
    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=distance_A_from_bottom if timberA_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=distance_A_from_bottom if timberA_end == TimberEnd.BOTTOM else None,
        negative_csg=None
    )

    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=distance_B_from_bottom if timberB_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=distance_B_from_bottom if timberB_end == TimberEnd.BOTTOM else None,
        negative_csg=None
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
    top_lap_shoulder_position_from_top_lap_shoulder_timber_end: Numeric,
    lap_depth: Optional[Numeric] = None
) -> Joint:
    """
    Creates a splice lap joint between two parallel timber ends with interlocking notches.

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

    from sympy import Rational

    # Calculate default lap_depth if not provided
    if lap_depth is None:
        # Use half the thickness in the axis perpendicular to top_lap_timber_face
        if top_lap_timber_face == TimberLongFace.LEFT or top_lap_timber_face == TimberLongFace.RIGHT:
            # Face is on Y-axis, so thickness is in Y direction (height)
            lap_depth = top_lap_timber.size[1] / Rational(2)
        else:  # TOP or BOTTOM
            # Face is on Z-axis (end face), use the smaller of width/height
            lap_depth = min(top_lap_timber.size[0], top_lap_timber.size[1]) / Rational(2)

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

    cut_top = Cutting(
        timber=top_lap_timber,
        maybe_top_end_cut_distance_from_bottom=top_end_cut_distance_from_bottom if top_lap_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=top_end_cut_distance_from_bottom if top_lap_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=top_lap_prism
    )

    cut_bottom = Cutting(
        timber=bottom_lap_timber,
        maybe_top_end_cut_distance_from_bottom=bottom_end_cut_distance_from_bottom if bottom_lap_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=bottom_end_cut_distance_from_bottom if bottom_lap_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=bottom_lap_prism
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

    # Create Cut objects for each timber
    receiving_timber_cut_obj = Cutting(
        timber=receiving_timber,
        maybe_top_end_cut_distance_from_bottom=receiving_end_cut_local_z if receiving_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=receiving_end_cut_local_z if receiving_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=receiving_timber_negative_csg
    )
    gooseneck_timber_cut_obj = Cutting(
        timber=gooseneck_timber,
        maybe_top_end_cut_distance_from_bottom=gooseneck_end_cut_local_z if gooseneck_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=gooseneck_end_cut_local_z if gooseneck_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=gooseneck_timber_combined_csg
    )

    return Joint(
        cuttings={
            receiving_timber.ticket.name: receiving_timber_cut_obj,
            gooseneck_timber.ticket.name: gooseneck_timber_cut_obj
        },
        ticket=JointTicket(joint_type="lapped_gooseneck"),
        jointAccessories={},
    )


# ============================================================================
# Aliases for Japanese joint functions
# ============================================================================

cut_腰掛鎌継ぎ = cut_lapped_gooseneck_joint
cut_koshikake_kama_tsugi = cut_lapped_gooseneck_joint
