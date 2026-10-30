"""
Kumiki - Mitered and keyed lap joint (Hako Aikaki Shachi Sen Shikuchi) construction functions
"""

from dataclasses import replace
from typing import Optional, List

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import (
    locate_centerline,
    mark_distance_from_end_along_centerline,
    locate_into_face,
)
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


def cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
    lap_thickness: Optional[Numeric] = None,
    lap_start_distance_from_reference_miter_face: Optional[Numeric] = None,
    distance_between_lap_and_outside: Optional[Numeric] = None,
    num_laps: int = 2,
    key_width: Optional[Numeric] = None,
    key_thickness: Optional[Numeric] = None,
) -> Joint:
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
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the reference miter face"
    )
    timberA = arrangement.timber1
    timberA_end = arrangement.timber1_end
    timberA_reference_miter_face = arrangement.front_face_on_timber1
    timberB = arrangement.timber2
    timberB_end = arrangement.timber2_end

    # Step 1: Parameter validation and find matching miter faces
    if num_laps < 2:
        raise ValueError(f"num_laps must be at least 2, got {num_laps}")

    timberA_miter_face_normal = timberA.get_face_direction_global(timberA_reference_miter_face)
    timberB_reference_miter_face_enum = timberB.get_closest_oriented_face_from_global_direction(
        timberA_miter_face_normal
    )

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

    timberB_miter_face_normal = timberB.get_face_direction_global(timberB_reference_miter_face)
    if not are_vectors_parallel(timberA_miter_face_normal, timberB_miter_face_normal):
        raise ValueError(
            f"Miter face normals must be parallel. "
            f"timberA face normal: {timberA_miter_face_normal.T}, "
            f"timberB face normal: {timberB_miter_face_normal.T}"
        )

    # Step 2: Calculate and validate angle between timbers
    if timberA_end == TimberEnd.TOP:
        directionA = timberA.get_length_direction_global()
    else:
        directionA = -timberA.get_length_direction_global()

    if timberB_end == TimberEnd.TOP:
        directionB = timberB.get_length_direction_global()
    else:
        directionB = -timberB.get_length_direction_global()

    dot_product = safe_dot_product(safe_normalize_vector(directionA), safe_normalize_vector(directionB))
    dot_product_clamped = Max(scalar(-1), Min(scalar(1), dot_product))
    angle = acos(dot_product_clamped)

    min_angle = radians(pi / scalar(4))  # 45 degrees
    max_angle = radians(scalar(3) * pi / scalar(4))  # 135 degrees

    if angle < min_angle or angle > max_angle:
        raise ValueError(
            f"Angle between timbers must be between 45° and 135°, "
            f"got {float(angle * 180 / pi):.1f}°"
        )

    # Step 3: Calculate dimensions and default values
    miter_face_depth = timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.to.face())
    miter_face_width = timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.rotate_right().to.face())

    if lap_thickness is None and lap_start_distance_from_reference_miter_face is None:
        lap_thickness_final = miter_face_depth / (num_laps + scalar(2))
        lap_start_distance_final = lap_thickness_final
    elif lap_thickness is None:
        assert lap_start_distance_from_reference_miter_face is not None
        remaining_depth: Numeric = miter_face_depth - lap_start_distance_from_reference_miter_face
        lap_thickness_final = remaining_depth / scalar(num_laps + 1)
        lap_start_distance_final = lap_start_distance_from_reference_miter_face
    elif lap_start_distance_from_reference_miter_face is None:
        total_lap_depth: Numeric = lap_thickness * num_laps
        lap_start_distance_final = (miter_face_depth - total_lap_depth) / scalar(2)
        lap_thickness_final = lap_thickness
    else:
        lap_thickness_final = lap_thickness
        lap_start_distance_final = lap_start_distance_from_reference_miter_face

    if distance_between_lap_and_outside is None:
        distance_between_lap_and_outside = miter_face_width * scalar(1, 5)

    # Step 4: Validate fit
    total_lap_depth = lap_start_distance_final + lap_thickness_final * num_laps
    if total_lap_depth >= miter_face_depth:
        raise ValueError(
            f"Laps do not fit in timber depth. "
            f"Total lap depth: {float(total_lap_depth):.3f}, "
            f"Miter face depth: {float(miter_face_depth):.3f}"
        )

    timberB_miter_face_depth = timberB.get_size_in_face_normal_axis(timberB_reference_miter_face.to.face())
    if total_lap_depth >= timberB_miter_face_depth:
        raise ValueError(
            f"Laps do not fit on timberB. "
            f"Total lap depth: {float(total_lap_depth):.3f}, "
            f"TimberB miter face depth: {float(timberB_miter_face_depth):.3f}"
        )

    # Step 5: Find inner face normals and inner shoulder direction
    diagonal_direction = safe_normalize_vector(directionA + directionB)
    negative_diagonal = -diagonal_direction
    timberA_inner_face_enum = timberA.get_closest_oriented_long_face_from_global_direction(negative_diagonal).to.face()
    timberB_inner_face_enum = timberB.get_closest_oriented_long_face_from_global_direction(negative_diagonal).to.face()

    timberA_inner_face_normal = timberA.get_face_direction_global(timberA_inner_face_enum)
    timberB_inner_face_normal = timberB.get_face_direction_global(timberB_inner_face_enum)

    inner_shoulder_direction = cross_product(timberA_inner_face_normal, timberB_inner_face_normal)
    inner_shoulder_direction = safe_normalize_vector(inner_shoulder_direction)

    timberA_inner_face_size = timberA.get_size_in_face_normal_axis(timberA_inner_face_enum)
    timberB_inner_face_size = timberB.get_size_in_face_normal_axis(timberB_inner_face_enum)
    if not safe_zero_test(timberA_inner_face_size - timberB_inner_face_size):
        raise ValueError(
            f"Timber widths in the miter plane are not the same. "
            f"TimberA size: {float(timberA_inner_face_size):.3f}, "
            f"TimberB size: {float(timberB_inner_face_size):.3f}"
        )

    # Step 6: Create marking transform on timberA
    timberB_centerline = locate_centerline(timberB)
    centerline_marking = mark_distance_from_end_along_centerline(timberB_centerline, timberA, end=TimberEnd.BOTTOM)

    marking_position = timberA.get_bottom_position_global()
    marking_position = marking_position + timberA.get_length_direction_global() * centerline_marking.distance
    marking_position_on_centerline = marking_position + timberA_miter_face_normal * (
        -timberA.get_size_in_face_normal_axis(timberA_reference_miter_face.to.face()) / scalar(2)
    )

    cos_angle = safe_dot_product(directionA, directionB)
    timber_angle = acos(cos_angle)
    half_angle = timber_angle / scalar(2)
    diagonal_scale_factor = scalar(1) / sin(half_angle)

    inner_edge_offset = timberA.get_size_in_face_normal_axis(timberA_inner_face_enum) / scalar(2)
    diagonal_offset = inner_edge_offset * diagonal_scale_factor
    marking_position = marking_position_on_centerline - diagonal_direction * diagonal_offset

    if timberA_end == TimberEnd.TOP:
        marking_z = timberA.get_length_direction_global()
    else:
        marking_z = -timberA.get_length_direction_global()

    marking_x = inner_shoulder_direction
    marking_y = cross_product(marking_z, marking_x)
    marking_y = safe_normalize_vector(marking_y)
    marking_x = cross_product(marking_y, marking_z)
    marking_x = safe_normalize_vector(marking_x)

    # Step 7: Generate finger prisms
    finger_length = lap_thickness_final
    finger_size_x = miter_face_width
    finger_size_y = miter_face_width * tan(half_angle)
    finger_size = create_v2(finger_size_x, finger_size_y)

    all_fingers_global = []

    for i in range(num_laps):
        is_timber_a = (i % 2 == 0)
        z_offset = lap_start_distance_final + i * lap_thickness_final
        finger_position = marking_position_on_centerline + timberA_miter_face_normal * z_offset

        finger_z = timberA_miter_face_normal
        finger_x = timberA_inner_face_normal if is_timber_a else timberB_inner_face_normal
        finger_y = cross_product(finger_z, finger_x)
        finger_y = safe_normalize_vector(finger_y)

        finger_orientation = Orientation(Matrix([
            [finger_x[0], finger_y[0], finger_z[0]],
            [finger_x[1], finger_y[1], finger_z[1]],
            [finger_x[2], finger_y[2], finger_z[2]],
        ]))

        finger_transform_global = Transform(position=finger_position, orientation=finger_orientation)
        finger_prism_global = RectangularPrism(
            size=finger_size,
            transform=finger_transform_global,
            start_distance=scalar(0),
            end_distance=finger_length,
            label=CutCSGLabel("lap_finger"),
        )
        all_fingers_global.append((finger_prism_global, is_timber_a))

    A_finger_indices = [i for i in range(num_laps) if i % 2 == 0]
    B_finger_indices = [i for i in range(num_laps) if i % 2 == 1]

    def convert_finger_to_local(finger_global: RectangularPrism, target_timber: TimberLike, is_timber_a_finger: bool) -> CutCSG:
        if is_timber_a_finger:
            opposing_timber = timberB
            opposing_inner_face_enum = timberB_inner_face_enum
        else:
            opposing_timber = timberA
            opposing_inner_face_enum = timberA_inner_face_enum

        finger_transform_local = finger_global.transform.to_local_transform(target_timber.transform)
        finger_local = replace(finger_global, transform=finger_transform_local)

        crop_distance = miter_face_width - distance_between_lap_and_outside
        crop_plane = locate_into_face(crop_distance, opposing_inner_face_enum, opposing_timber)

        crop_point_local = target_timber.transform.global_to_local(crop_plane.point)
        crop_normal_local = safe_transform_vector(target_timber.orientation.matrix.T, crop_plane.normal)
        crop_offset_local = safe_dot_product(crop_point_local, crop_normal_local)

        crop_halfspace_local = HalfSpace(
            normal=-crop_normal_local,
            offset=-crop_offset_local,
            label=CutCSGLabel("finger_crop"),
        )

        return Difference(
            base=finger_local,
            subtract=[crop_halfspace_local],
            label=CutCSGLabel("lap_finger_cropped"),
        )

    A_fingers_in_timberA = [
        convert_finger_to_local(all_fingers_global[idx][0], timberA, all_fingers_global[idx][1])
        for idx in A_finger_indices
    ]
    B_fingers_in_timberA = [
        convert_finger_to_local(all_fingers_global[idx][0], timberA, all_fingers_global[idx][1])
        for idx in B_finger_indices
    ]
    A_fingers_in_timberB = [
        convert_finger_to_local(all_fingers_global[idx][0], timberB, all_fingers_global[idx][1])
        for idx in A_finger_indices
    ]
    B_fingers_in_timberB = [
        convert_finger_to_local(all_fingers_global[idx][0], timberB, all_fingers_global[idx][1])
        for idx in B_finger_indices
    ]

    # Step 7.5: Create Keys
    if key_width is None:
        key_width = lap_thickness_final
    if key_thickness is None:
        key_thickness = lap_thickness_final / scalar(3)

    key_depth = miter_face_width / sin(half_angle) - distance_between_lap_and_outside / sin(half_angle)

    keys_in_timberA = []
    keys_in_timberB = []
    key_wedges = []

    num_keys = num_laps - 1
    for i in range(num_keys):
        key_position = marking_position
        z_offset = lap_start_distance_final + (i + 1) * lap_thickness_final
        key_position = key_position + timberA_miter_face_normal * z_offset

        key_orientation_before_rotation = Orientation.from_z_and_y(
            z_direction=diagonal_direction,
            y_direction=-timberA_miter_face_normal,
        )

        key_rotation_sign = -1 if i % 2 == 0 else 1
        key_rotation_angle = key_rotation_sign * atan2(key_thickness, key_width)
        rotation_for_key = Orientation.from_axis_angle(diagonal_direction, radians(key_rotation_angle))
        key_orientation = rotation_for_key * key_orientation_before_rotation
        key_transform_global = Transform(position=key_position, orientation=key_orientation)

        key_size = create_v2(key_width, key_thickness)
        key_prism_global = RectangularPrism(
            size=key_size,
            transform=key_transform_global,
            start_distance=-key_depth,
            end_distance=key_depth,
            label=CutCSGLabel("key_slot"),
        )

        key_transform_local_A = key_transform_global.to_local_transform(timberA.transform)
        key_prism_in_timberA = replace(key_prism_global, transform=key_transform_local_A)
        keys_in_timberA.append(key_prism_in_timberA)

        key_transform_local_B = key_transform_global.to_local_transform(timberB.transform)
        key_prism_in_timberB = replace(key_prism_global, transform=key_transform_local_B)
        keys_in_timberB.append(key_prism_in_timberB)

        key_wedge = Wedge(
            transform=key_transform_global,
            base_width=key_width,
            tip_width=key_width,
            height=key_thickness,
            length=key_depth,
            stickout_length=key_depth * scalar(1, 4),
            assembly_freedom=AssemblyFreedom.translation(-diagonal_direction, freed_after=key_depth * scalar(2)),
            assembly_ordering=Ordering(0, -1),
        )
        key_wedges.append(key_wedge)

    # Step 8: Create rough end cuts and miter half plane cuts
    if timberA_end == TimberEnd.TOP:
        rough_cut_position_A = marking_position + timberA.get_length_direction_global() * finger_size_y
        rough_cut_normal_A_global = timberA.get_length_direction_global()
    else:
        rough_cut_position_A = marking_position - timberA.get_length_direction_global() * finger_size_y
        rough_cut_normal_A_global = -timberA.get_length_direction_global()

    local_normal_A_rough = safe_transform_vector(timberA.orientation.matrix.T, rough_cut_normal_A_global)
    local_offset_A_rough = safe_dot_product(rough_cut_position_A, rough_cut_normal_A_global) - safe_dot_product(
        rough_cut_normal_A_global, timberA.get_bottom_position_global()
    )
    rough_end_cut_A = HalfSpace(normal=local_normal_A_rough, offset=local_offset_A_rough)

    if timberB_end == TimberEnd.TOP:
        rough_cut_position_B = marking_position + timberB.get_length_direction_global() * finger_size_y
        rough_cut_normal_B_global = timberB.get_length_direction_global()
    else:
        rough_cut_position_B = marking_position - timberB.get_length_direction_global() * finger_size_y
        rough_cut_normal_B_global = -timberB.get_length_direction_global()

    local_normal_B_rough = safe_transform_vector(timberB.orientation.matrix.T, rough_cut_normal_B_global)
    local_offset_B_rough = safe_dot_product(rough_cut_position_B, rough_cut_normal_B_global) - safe_dot_product(
        rough_cut_normal_B_global, timberB.get_bottom_position_global()
    )
    rough_end_cut_B = HalfSpace(normal=local_normal_B_rough, offset=local_offset_B_rough)

    intersection_point = marking_position
    normA = safe_normalize_vector(directionA)
    normB = safe_normalize_vector(directionB)
    bisector = safe_normalize_vector(normA + normB)
    plane_normal = cross_product(normA, normB)
    miter_normal = safe_normalize_vector(cross_product(bisector, plane_normal))

    dot_A = safe_dot_product(normA, miter_normal)
    normalA = miter_normal if safe_compare(dot_A, 0, Comparison.GT) else -miter_normal
    local_normalA = safe_transform_vector(timberA.orientation.matrix.T, normalA)
    local_offsetA = safe_dot_product(intersection_point, normalA) - safe_dot_product(
        normalA, timberA.get_bottom_position_global()
    )

    dot_B = safe_dot_product(normB, miter_normal)
    normalB = miter_normal if safe_compare(dot_B, 0, Comparison.GT) else -miter_normal
    local_normalB = safe_transform_vector(timberB.orientation.matrix.T, normalB)
    local_offsetB = safe_dot_product(intersection_point, normalB) - safe_dot_product(
        normalB, timberB.get_bottom_position_global()
    )

    miter_half_plane_A = HalfSpace(normal=local_normalA, offset=local_offsetA, label=CutCSGLabel("miter_plane"))
    miter_half_plane_B = HalfSpace(normal=local_normalB, offset=local_offsetB, label=CutCSGLabel("miter_plane"))

    # Step 9: Combine cuts and return Joint
    if A_fingers_in_timberA:
        miter_cut_A_with_fingers = Difference(
            miter_half_plane_A, A_fingers_in_timberA, label=CutCSGLabel("miter_waste")
        )
    else:
        miter_cut_A_with_fingers = miter_half_plane_A

    voids_in_A = []
    if B_fingers_in_timberA:
        voids_in_A.extend(B_fingers_in_timberA)
    if keys_in_timberA:
        voids_in_A.extend(keys_in_timberA)

    if voids_in_A:
        negative_csg_A = CSGUnion([miter_cut_A_with_fingers] + voids_in_A)
    else:
        negative_csg_A = miter_cut_A_with_fingers

    if B_fingers_in_timberB:
        miter_cut_B_with_fingers = Difference(
            miter_half_plane_B, B_fingers_in_timberB, label=CutCSGLabel("miter_waste")
        )
    else:
        miter_cut_B_with_fingers = miter_half_plane_B

    voids_in_B = []
    if A_fingers_in_timberB:
        voids_in_B.extend(A_fingers_in_timberB)
    if keys_in_timberB:
        voids_in_B.extend(keys_in_timberB)

    if voids_in_B:
        negative_csg_B = CSGUnion([miter_cut_B_with_fingers] + voids_in_B)
    else:
        negative_csg_B = miter_cut_B_with_fingers

    rough_end_cut_A_z = (
        rough_end_cut_A.offset if timberA_end == TimberEnd.TOP else -rough_end_cut_A.offset
    )
    rough_end_cut_B_z = (
        rough_end_cut_B.offset if timberB_end == TimberEnd.TOP else -rough_end_cut_B.offset
    )

    cutA = Cutting(
        timber=timberA,
        maybe_top_end_cut_distance_from_bottom=rough_end_cut_A_z if timberA_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=rough_end_cut_A_z if timberA_end == TimberEnd.BOTTOM else None,
        negative_csg=negative_csg_A,
        label=CutCSGLabel("mitered_lap_cut"),
        assembly_freedom=AssemblyFreedom.translation(
            -directionA, freed_after=timberB.get_size_in_direction_3d(directionA)
        ),
        assembly_ordering=Ordering(0, 0),
    )

    cutB = Cutting(
        timber=timberB,
        maybe_top_end_cut_distance_from_bottom=rough_end_cut_B_z if timberB_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=rough_end_cut_B_z if timberB_end == TimberEnd.BOTTOM else None,
        negative_csg=negative_csg_B,
        label=CutCSGLabel("mitered_lap_cut"),
        assembly_freedom=AssemblyFreedom.translation(
            -directionB, freed_after=timberA.get_size_in_direction_3d(directionB)
        ),
        assembly_ordering=Ordering(0, 0),
    )

    joint_accessories = {}
    for i, wedge in enumerate(key_wedges):
        joint_accessories[f"key_{i}"] = wedge

    return Joint(
        cuttings={
            timberA.ticket.path: cutA,
            timberB.ticket.path: cutB,
        },
        ticket=JointTicket(joint_type="mitered_and_keyed_lap"),
        jointAccessories=joint_accessories,
    )


# Aliases for Japanese joint functions
cut_箱相欠き車知栓仕口 = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers
cut_hako_aikaki_shachi_sen_shikuchi = cut_mitered_and_keyed_lap_joint_on_plane_aligned_timbers
