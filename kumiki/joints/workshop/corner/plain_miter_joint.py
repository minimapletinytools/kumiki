"""
Kumiki - Plain miter joint construction functions
"""

import warnings
from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import locate_top_center_position, locate_bottom_center_position
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


def cut_plain_miter_joint(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two timbers, cutting each end at half the angle between them.

    Both ends are cut by the same bisecting plane so they meet flush at the corner.
    Works for any angle including parallel timbers (parallel produces a perpendicular end cut).

    Args:
        arrangement: Corner joint arrangement with timber1, timber2, timber1_end, timber2_end.

    Returns:
        Joint object containing the two CutTimbers.
    """
    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end

    warn_if_arrangement_timbers_imperfect(arrangement)

    # Get the end directions for each timber (pointing outward from the timber)
    if timberA_end == TimberEnd.TOP:
        directionA = timberA.get_length_direction_global()
        endA_position = locate_top_center_position(timberA).position
    else:  # BOTTOM
        directionA = -timberA.get_length_direction_global()
        endA_position = locate_bottom_center_position(timberA).position

    if timberB_end == TimberEnd.TOP:
        directionB = timberB.get_length_direction_global()
        endB_position = locate_top_center_position(timberB).position
    else:  # BOTTOM
        directionB = -timberB.get_length_direction_global()
        endB_position = locate_bottom_center_position(timberB).position

    # Find the intersection point (or closest point) between the two timber centerlines
    w0 = prune(endA_position - endB_position)
    a = safe_dot_product(directionA, directionA)
    b = safe_dot_product(directionA, directionB)
    c = safe_dot_product(directionB, directionB)
    d = safe_dot_product(directionA, w0)
    e = safe_dot_product(directionB, w0)

    denom = prune(a * c - b * b)
    if safe_zero_test(denom):
        # Parallel timbers: lines don't converge; bisect between the two end positions
        intersection_point = prune((endA_position + endB_position) / 2)
    else:
        # Parameters for closest points on each line
        t = prune((b * e - c * d) / denom)
        s = prune((a * e - b * d) / denom)

        # Get the closest points on each centerline
        pointA = prune(endA_position + directionA * t)
        pointB = prune(endB_position + directionB * s)

        # The intersection point is the midpoint between the two closest points
        intersection_point = prune((pointA + pointB) / 2)

    # Create the miter plane normal
    normA = safe_normalize_vector(directionA)
    normB = safe_normalize_vector(directionB)

    # The bisecting direction is the normalized sum of the two directions
    bisector = safe_normalize_vector(normA + normB)

    # The plane formed by the two timber directions has normal:
    plane_normal = cross_product(normA, normB)

    plane_normal_sq = safe_dot_product(plane_normal, plane_normal)
    if safe_zero_test_sq(plane_normal_sq):
        miter_normal = normA
    else:
        miter_normal = safe_normalize_vector(cross_product(bisector, plane_normal))

    # For timberA: check if miter_normal points away from or towards the timber
    dot_A = safe_dot_product(normA, miter_normal)
    if safe_compare(dot_A, 0, Comparison.GT):
        normalA = miter_normal
    else:
        normalA = -miter_normal

    local_normalA = safe_transform_vector(timberA.orientation.matrix.T, normalA)

    # For timberB: check if miter_normal points away from or towards the timber
    dot_B = safe_dot_product(normB, miter_normal)
    if safe_compare(dot_B, 0, Comparison.GT):
        normalB = miter_normal
    else:
        normalB = -miter_normal

    local_normalB = safe_transform_vector(timberB.orientation.matrix.T, normalB)

    # Calculate offset for each timber's miter cut
    cos_angle = safe_dot_product(normA, normB)
    cos_angle_clamped = max(prune(scalar(-1)), min(prune(scalar(1)), cos_angle))
    sin_half_angle_sq = (scalar(1) - cos_angle_clamped) / scalar(2)
    sin_half_angle = sqrt(sin_half_angle_sq) if safe_compare(sin_half_angle_sq, 0, Comparison.GT) else scalar(1)

    half_width_A = timberA.size[0] / scalar(2)
    half_height_A = timberA.size[1] / scalar(2)
    outer_corner_dist_A = sqrt(half_width_A ** scalar(2) + half_height_A ** scalar(2))

    half_width_B = timberB.size[0] / scalar(2)
    half_height_B = timberB.size[1] / scalar(2)
    outer_corner_dist_B = sqrt(half_width_B ** scalar(2) + half_height_B ** scalar(2))

    if not safe_zero_test(sin_half_angle):
        offset_dist_A = outer_corner_dist_A / sin_half_angle
        offset_dist_B = outer_corner_dist_B / sin_half_angle
    else:
        offset_dist_A = outer_corner_dist_A * scalar(100)
        offset_dist_B = outer_corner_dist_B * scalar(100)

    miter_cut_point_A = prune(intersection_point + bisector * offset_dist_A)
    miter_cut_point_B = prune(intersection_point + bisector * offset_dist_B)

    local_offsetA = safe_dot_product(miter_cut_point_A, normalA) - safe_dot_product(normalA, timberA.get_bottom_position_global())
    local_offsetB = safe_dot_product(miter_cut_point_B, normalB) - safe_dot_product(normalB, timberB.get_bottom_position_global())

    end_cut_A = HalfSpace(normal=local_normalA, offset=local_offsetA)
    end_cut_B = HalfSpace(normal=local_normalB, offset=local_offsetB)

    end_cut_A_distance_from_bottom = safe_dot_product(
        miter_cut_point_A - timberA.get_bottom_position_global(),
        timberA.get_length_direction_global(),
    )
    end_cut_B_distance_from_bottom = safe_dot_product(
        miter_cut_point_B - timberB.get_bottom_position_global(),
        timberB.get_length_direction_global(),
    )

    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=end_cut_A_distance_from_bottom if timberA_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=end_cut_A_distance_from_bottom if timberA_end == TimberEnd.BOTTOM else None,
        negative_csg=end_cut_A,
        assembly_freedom=AssemblyFreedom.translation(-directionA, freed_after=scalar(0)),
        label=CutCSGLabel("miter_cut"),
    )

    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=end_cut_B_distance_from_bottom if timberB_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=end_cut_B_distance_from_bottom if timberB_end == TimberEnd.BOTTOM else None,
        negative_csg=end_cut_B,
        assembly_freedom=AssemblyFreedom.translation(-directionB, freed_after=scalar(0)),
        label=CutCSGLabel("miter_cut"),
    )

    return Joint(
        cuttings={"timberA": cutA, "timberB": cutB},
        ticket=JointTicket(joint_type="plain_miter"),
        jointAccessories={},
    )


def cut_plain_miter_joint_on_face_aligned_timbers(arrangement: CornerJointTimberArrangement) -> Joint:
    """
    Creates a miter joint between two face-aligned timbers meeting at a 90-degree corner.

    Like `cut_plain_miter_joint`, but requires the timbers to be orthogonal (perpendicular
    length axes). This is the common case for timber-frame corners.

    Args:
        arrangement: Corner joint arrangement with timber1, timber2, timber1_end, timber2_end.
                     Timbers must be face-aligned and orthogonal.

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        AssertionError: If the timbers are not face-aligned or not orthogonal.
    """
    assert are_timbers_face_aligned(arrangement.timber1, arrangement.timber2), (
        "Timbers must be face-aligned (orientations related by 90-degree rotations) for this joint type"
    )
    assert are_timbers_orthogonal(arrangement.timber1, arrangement.timber2), (
        "Timbers must have perpendicular length axes (90-degree angle) for this joint type"
    )

    return cut_plain_miter_joint(arrangement)
