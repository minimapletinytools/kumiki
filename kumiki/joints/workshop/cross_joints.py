"""
Kumiki - Cross joint construction functions
Contains cross-lap and house joint implementations.
"""

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *
from .shavings.relief import CrossJointScribeReliefConfig, chop_scribe_relief_and_apply, warn_if_arrangement_timbers_imperfect
from kumiki.measuring import locate_top_center_position, locate_bottom_center_position


_raw_safe_dot_product = safe_dot_product
_raw_safe_norm = safe_norm
_raw_safe_transform_vector = safe_transform_vector


def safe_dot_product(*args, **kwargs):
    return prune(_raw_safe_dot_product(*args, **kwargs))


def safe_norm(*args, **kwargs):
    return prune(_raw_safe_norm(*args, **kwargs))


def safe_transform_vector(*args, **kwargs):
    return prune(_raw_safe_transform_vector(*args, **kwargs))


# ============================================================================
# Helper functions
# ============================================================================


def _get_face_center_position(timber: PerfectTimberWithin, face: SomeTimberFace) -> V3:
    """
    Helper function to calculate the center position of a timber face.

    Args:
        timber: The timber object
        face: The face to get the center position for

    Returns:
        3D position vector at the center of the specified face
    """
    face = face.to.face()

    if face == TimberFace.TOP:
        return locate_top_center_position(timber).position
    elif face == TimberFace.BOTTOM:
        return locate_bottom_center_position(timber).position
    else:
        # For long faces (LEFT, RIGHT, FRONT, BACK), center is at mid-length
        face_center = timber.get_bottom_position_global() + (timber.length / scalar(2)) * timber.get_length_direction_global()

        # Offset to the face surface
        if face == TimberFace.RIGHT:
            face_center = face_center + (timber.size[0] / scalar(2)) * timber.get_width_direction_global()
        elif face == TimberFace.LEFT:
            face_center = face_center - (timber.size[0] / scalar(2)) * timber.get_width_direction_global()
        elif face == TimberFace.FRONT:
            face_center = face_center + (timber.size[1] / scalar(2)) * timber.get_height_direction_global()
        else:  # BACK
            face_center = face_center - (timber.size[1] / scalar(2)) * timber.get_height_direction_global()

        return face_center


# ============================================================================
# Cross Joint Construction Functions
# ============================================================================


def cut_plain_cross_lap_joint(
    arrangement: CrossJointTimberArrangement,
    cut_ratio: Numeric = scalar(1, 2),
    relief: Optional[CrossJointScribeReliefConfig] = CrossJointScribeReliefConfig.cross_timber_1(),
) -> Joint:
    """
    Creates a cross-lap joint between two intersecting timbers.

    Each timber has a portion relieved from it so they interlock at their crossing point,
    maintaining a flush outer face on both sides. By default material removal is split
    equally (half from each timber).

    Args:
        arrangement: Cross-joint arrangement with timber1 and timber2, and optional
                     front_face_on_timber1 (the cut face on timber1). If not provided,
                     front_face_on_timber1 is chosen automatically to minimize material removed.
                     The cut face on timber2 is implicitly the opposite face.
        cut_ratio: Fraction [0, 1] controlling how much is removed from each timber.
            0 = only timber2 is cut; 1 = only timber1 is cut; 0.5 = equal split (default).

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        AssertionError: If the timbers don't intersect, are parallel, or cut_ratio is out of range.
    """
    from kumiki.cutcsg import Difference, RectangularPrism, HalfSpace
    from kumiki.rule import safe_dot_product, safe_transform_vector, safe_norm

    timberA = arrangement.timber1
    timberB = arrangement.timber2
    timberA_cut_face = arrangement.front_face_on_timber1

    warn_if_arrangement_timbers_imperfect(arrangement)

    # Verify that cut_ratio is in valid range [0, 1]
    assert 0 <= cut_ratio <= 1, f"cut_ratio must be in range [0, 1], got {cut_ratio}"

    # Verify that the timbers are not parallel (their length directions must differ)
    dot_product = safe_dot_product(timberA.get_length_direction_global(), timberB.get_length_direction_global())
    assert abs(abs(dot_product) - 1) > scalar(1, 1000000), \
        "Timbers must not be parallel (their length directions must differ)"

    # Check that the timbers intersect when extended infinitely
    # Calculate closest points between two lines in 3D
    d1 = timberA.get_length_direction_global()
    d2 = timberB.get_length_direction_global()
    p1 = timberA.get_bottom_position_global()
    p2 = timberB.get_bottom_position_global()
    w = p1 - p2

    a = safe_dot_product(d1, d1)
    b = safe_dot_product(d1, d2)
    c = safe_dot_product(d2, d2)
    d = safe_dot_product(d1, w)
    e = safe_dot_product(d2, w)

    denom = a * c - b * b

    if abs(denom) < scalar(1, 1000000):
        # Lines are parallel (already checked above)
        t = -safe_dot_product(d1, w) / a if a > 0 else 0
        closest_on_1 = p1 + t * d1
        distance = safe_norm(p2 - closest_on_1)
    else:
        t1 = (b * e - c * d) / denom
        t2 = (a * e - b * d) / denom

        closest_on_1 = p1 + t1 * d1
        closest_on_2 = p2 + t2 * d2

        distance = safe_norm(closest_on_1 - closest_on_2)

    # Check if timbers are close enough to intersect
    max_separation = (timberA.size[0] + timberA.size[1] +
                     timberB.size[0] + timberB.size[1]) / 2

    assert float(distance) < float(max_separation), \
        f"Timbers do not intersect (closest distance: {float(distance):.4f}m, max allowed: {float(max_separation):.4f}m)"


    # Auto-select cut faces if not provided
    # Find the axis perpendicular to the length axis of both timbers
    # Choose the face on that axis on timberA that's closest to timberB
    # Then pick the opposite face on timberB
    if timberA_cut_face is None:
        from kumiki.rule import cross_product, safe_normalize_vector as normalize_vector, safe_norm

        # Get length directions of both timbers
        d1 = timberA.get_length_direction_global()
        d2 = timberB.get_length_direction_global()

        # Find axis perpendicular to both length directions (cross product)
        perpendicular_axis = cross_product(d1, d2)
        perpendicular_axis = normalize_vector(perpendicular_axis)

        # Get center positions of both timbers
        centerA = timberA.get_bottom_position_global() + timberA.get_length_direction_global() * (timberA.length / scalar(2))
        centerB = timberB.get_bottom_position_global() + timberB.get_length_direction_global() * (timberB.length / scalar(2))

        # Vector from timberA center to timberB center
        A_to_B = centerB - centerA

        # Project A_to_B onto the perpendicular axis to get direction
        projection = safe_dot_product(A_to_B, perpendicular_axis)

        # Direction along perpendicular axis (toward timberB from timberA)
        direction_toward_B = perpendicular_axis if projection >= 0 else -perpendicular_axis

        # Find face on timberA whose normal is closest to direction_toward_B
        faces = [TimberFace.RIGHT, TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK]
        max_dot = None
        best_face = TimberFace.RIGHT  # Default

        for face in faces:
            face_normal = timberA.get_face_direction_global(face)
            dot = safe_dot_product(face_normal, direction_toward_B)

            if max_dot is None or dot > max_dot:
                max_dot = dot
                best_face = face

        timberA_cut_face = best_face

    # timberB_cut_face is computed as the opposite of timberA_cut_face
    normalA = timberA.get_face_direction_global(timberA_cut_face)
    faces = [TimberFace.RIGHT, TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK]
    min_dot = None
    timberB_cut_face = TimberFace.RIGHT  # Default

    for face in faces:
        face_normal = timberB.get_face_direction_global(face)
        dot = safe_dot_product(face_normal, normalA)

        # We want the face with the most negative dot product (most opposing)
        if min_dot is None or dot < min_dot:
            min_dot = dot
            timberB_cut_face = face

    # Both cut faces are now set (narrow type for type checker)
    assert timberA_cut_face is not None and timberB_cut_face is not None
    # Get face normals (pointing outward from the timber) in GLOBAL space
    # get_face_direction returns the direction vector in world coordinates
    normalA = timberA.get_face_direction_global(timberA_cut_face)
    normalB = timberB.get_face_direction_global(timberB_cut_face)

    # Verify that the face normals oppose each other (point toward each other)
    # For a valid cross lap joint, the normals must strictly oppose (dot product < 0)
    # This ensures the cutting plane can properly separate the two timber volumes
    normal_dot = safe_dot_product(normalA, normalB)

    # The faces must be opposing (normals pointing toward each other)
    # Perpendicular faces (dot product = 0) are NOT valid for cross lap joints
    assert normal_dot < 0, \
        f"Face normals must oppose each other (dot product < 0, got {float(normal_dot):.4f})"

    # Create the cutting plane by lerping between the two faces
    # Get the position of each face (center point on the face)
    # Calculate face center positions
    faceA_position = _get_face_center_position(timberA, timberA_cut_face)
    faceB_position = _get_face_center_position(timberB, timberB_cut_face)

    # The cutting plane position is interpolated based on cut_ratio
    # cut_ratio = 0: plane at faceA (timberB is cut entirely)
    # cut_ratio = 0.5: plane halfway between faces
    # cut_ratio = 1: plane at faceB (timberA is cut entirely)
    cutting_plane_position = faceA_position * (1 - cut_ratio) + faceB_position * cut_ratio

    # The cutting plane normal should be interpolated between the two face normals
    # cut_ratio = 0: normal is normalA (pointing from faceA)
    # cut_ratio = 1: normal is -normalB (pointing toward faceB from the opposite direction)
    # Since normalA and normalB oppose each other (normalA · normalB < 0), we interpolate:
    cutting_plane_normal = normalA * (1 - cut_ratio) - normalB * cut_ratio
    cutting_plane_normal_normalized = cutting_plane_normal / safe_norm(cutting_plane_normal)

    # Calculate the offset for the cutting plane
    # offset = normal · point_on_plane
    cutting_plane_offset = safe_dot_product(cutting_plane_normal_normalized, cutting_plane_position)

    # Create cuts for both timbers
    cuts_A = []
    cuts_B = []

    # TimberA: Cut by (timberB prism) intersected with (region on the timberB side of cutting plane)
    # The HalfSpace keeps points where normal·P >= offset
    # We want to keep the region on the timberB side (positive normal direction from A)
    # So we use the cutting plane as-is

    if safe_compare(cut_ratio, 0, Comparison.GT):  # Only cut timberA if cut_ratio > 0
        # Transform timberB prism to timberA's local coordinates
        relative_orientation_B_in_A = Orientation(safe_transform_vector(timberA.orientation.matrix.T, timberB.orientation.matrix))
        timberB_origin_in_A_local = safe_transform_vector(timberA.orientation.matrix.T, timberB.get_bottom_position_global() - timberA.get_bottom_position_global())

        # Create timberB prism in timberA's local coordinates (infinite extent)
        transform_B_in_A = Transform(position=timberB_origin_in_A_local, orientation=relative_orientation_B_in_A)
        timberB_prism_in_A = RectangularPrism(
            size=timberB.size,
            transform=transform_B_in_A,
            start_distance=None,  # Infinite
            end_distance=None     # Infinite
        )

        # Transform cutting plane to timberA's local coordinates
        cutting_plane_normal_in_A = safe_transform_vector(timberA.orientation.matrix.T, cutting_plane_normal_normalized)
        cutting_plane_position_in_A = safe_transform_vector(timberA.orientation.matrix.T, cutting_plane_position - timberA.get_bottom_position_global())
        cutting_plane_offset_in_A = safe_dot_product(cutting_plane_normal_in_A, cutting_plane_position_in_A)

        # Create HalfSpace that keeps the region on the positive side of the plane
        # (toward timberB from the cutting plane)
        half_plane_A = HalfSpace(
            normal=cutting_plane_normal_in_A,
            offset=cutting_plane_offset_in_A
        )

        inverse_half_plane_A = HalfSpace(
            normal=-cutting_plane_normal_in_A,
            offset=-cutting_plane_offset_in_A
        )

        # Subtract the portion of timberB that's on the positive side of cutting plane
        negative_csg_A = Difference(
            base=timberB_prism_in_A,
            subtract=[inverse_half_plane_A]  # Remove the negative side, keeping positive side
        )

        cut_A = Cutting(
            timber=timberA,
            negative_csg=negative_csg_A
        )
        cuts_A.append(cut_A)

    # TimberB: Cut by (timberA prism) intersected with (region on the timberA side of cutting plane)
    if cut_ratio < 1:  # Only cut timberB if cut_ratio < 1
        # Transform timberA prism to timberB's local coordinates
        relative_orientation_A_in_B = Orientation(safe_transform_vector(timberB.orientation.matrix.T, timberA.orientation.matrix))
        timberA_origin_in_B_local = safe_transform_vector(timberB.orientation.matrix.T, timberA.get_bottom_position_global() - timberB.get_bottom_position_global())

        # Create timberA prism in timberB's local coordinates (infinite extent)
        transform_A_in_B = Transform(position=timberA_origin_in_B_local, orientation=relative_orientation_A_in_B)
        timberA_prism_in_B = RectangularPrism(
            size=timberA.size,
            transform=transform_A_in_B,
            start_distance=None,  # Infinite
            end_distance=None     # Infinite
        )

        # Transform cutting plane to timberB's local coordinates
        cutting_plane_normal_in_B = safe_transform_vector(timberB.orientation.matrix.T, cutting_plane_normal_normalized)
        cutting_plane_position_in_B = safe_transform_vector(timberB.orientation.matrix.T, cutting_plane_position - timberB.get_bottom_position_global())
        cutting_plane_offset_in_B = safe_dot_product(cutting_plane_normal_in_B, cutting_plane_position_in_B)

        # For timberB, we want to subtract the region on the negative side (timberA side) of the plane
        # So we use the inverse half plane (keeps normal·P <= offset, the negative side)
        half_plane_B = HalfSpace(
            normal=cutting_plane_normal_in_B,
            offset=cutting_plane_offset_in_B
        )

        # Subtract the portion of timberA that's on the negative side of cutting plane
        negative_csg_B = Difference(
            base=timberA_prism_in_B,
            subtract=[half_plane_B]  # Remove the positive side, keeping negative side
        )

        cut_B = Cutting(
            timber=timberB,
            negative_csg=negative_csg_B
        )
        cuts_B.append(cut_B)

    cut_timberA = cuts_A[0] if len(cuts_A) > 0 else Cutting(timber=timberA)
    cut_timberB = cuts_B[0] if len(cuts_B) > 0 else Cutting(timber=timberB)

    cuttings: dict[str, Cutting] = {"timberA": cut_timberA, "timberB": cut_timberB}

    if relief is not None:
        if relief.timber_to_be_scribed == ArrangementNames.cross_timber_1:
            scribed_key, cut_key = "timberA", "timberB"
            scribed_timber, cut_timber = timberA, timberB
        elif relief.timber_to_be_scribed == ArrangementNames.cross_timber_2:
            scribed_key, cut_key = "timberB", "timberA"
            scribed_timber, cut_timber = timberB, timberA
        else:
            raise AssertionError(
                f"Unsupported cross-joint relief target: {relief.timber_to_be_scribed}"
            )

        updated_cut_cutting, updated_scribed_cutting = chop_scribe_relief_and_apply(
            timber_to_be_scribed=scribed_timber,
            timber_to_be_scribed_cutting=cuttings[scribed_key],
            timber_to_be_cut=cut_timber,
            timber_to_be_cut_cutting=cuttings[cut_key],
        )
        cuttings[scribed_key] = updated_scribed_cutting
        cuttings[cut_key] = updated_cut_cutting

    # Create and return the Joint
    joint = Joint(
        cuttings=cuttings,
        ticket=JointTicket(joint_type="plain_cross_lap"),
        jointAccessories={},
    )

    return joint


def cut_plain_cross_lap_house_joint(arrangement: CrossJointTimberArrangement) -> Joint:
    """
    Creates a house (dado/housing) joint where the housing timber is relieved to receive the housed timber.

    Only the housing timber is cut (timber1); the housed timber (timber2) is not modified.
    Implemented as a cross-lap joint with cut_ratio=1.

    Note this different from cut_free_house_joint in the way it handles relief cuts on the non-ptw parts of the timbers.

    Args:
        arrangement: Cross-joint arrangement where timber1 is the housing timber (to be relieved)
                     and timber2 is the housed timber (remains uncut). front_face_on_timber1
                     specifies the relief face; if None, chosen automatically.

    Returns:
        Joint object containing both timbers.

    Raises:
        AssertionError: If the timbers don't intersect or are parallel.
    """
    # Use cross lap joint with cut_ratio=1 (only cut timber1, not timber2)
    return cut_plain_cross_lap_joint(arrangement, cut_ratio=scalar(1, 1))
