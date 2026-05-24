"""
Kumiki - Notching helpers

Shared helper functions for shoulder-plane calculations and notch CSG generation.
"""

from __future__ import annotations

from typing import Union

from sympy import Abs, Rational

from kumiki.construction import ButtJointTimberArrangement
from kumiki.cutcsg import RectangularPrism, SolidUnion
from kumiki.measuring import Plane, locate_centerline, locate_plane_from_edge_in_direction
from kumiki.rule import *
from kumiki.timber import TimberCenterline, TimberFace, TimberLike, TimberReferenceEnd


def chop_shoulder_notch_aligned_with_timber(
    notch_timber: TimberLike,
    butting_timber: TimberLike,
    butting_timber_end: TimberReferenceEnd,
    distance_from_centerline: Numeric,
    notch_wall_relief_cut_angle_radians: Numeric = Integer(0),
) -> Union[RectangularPrism, SolidUnion]:
    """
    Create a shoulder notch on notch_timber at a given distance from its centerline,
    oriented by the butting_timber's approach direction.

    Unlike chop_shoulder_notch_on_timber_face which is aligned to a specific face,
    this notch is aligned to the shoulder plane derived from the butting timber's
    approach direction (projected perpendicular to the notch timber's length axis).

    The notch bottom (shoulder plane) is distance_from_centerline away from the
    notch_timber's centerline. The notch opens outward from the centerline.
    The notch width is along the notch_timber's length axis. Both the width and
    span dimensions are oversized (max(size) * sqrt(2)) to guarantee full
    coverage regardless of the cross-section rotation.
    """
    from sympy import Max, cos, sqrt

    notch_length_dir_global = notch_timber.get_length_direction_global()

    if butting_timber_end == TimberReferenceEnd.TOP:
        raw_approach = -butting_timber.get_length_direction_global()
    else:
        raw_approach = butting_timber.get_length_direction_global()

    projected = raw_approach - notch_length_dir_global * safe_dot_product(
        raw_approach, notch_length_dir_global
    )
    approach_direction_global = normalize_vector(projected)

    shoulder_plane = locate_plane_from_edge_in_direction(
        notch_timber,
        TimberCenterline.CENTERLINE,
        approach_direction_global,
        distance_from_centerline,
    )
    butting_centerline = locate_centerline(butting_timber)
    denom = safe_dot_product(shoulder_plane.normal, butting_centerline.direction)
    assert not zero_test(denom), "Butting timber centerline is parallel to the shoulder plane"
    t = safe_dot_product(
        shoulder_plane.normal,
        shoulder_plane.point - butting_centerline.point,
    ) / denom
    intersection_global = butting_centerline.point + butting_centerline.direction * t

    max_size = Max(notch_timber.size[0], notch_timber.size[1])
    notch_span = max_size * sqrt(Integer(2))
    notch_depth = max_size * sqrt(Integer(2)) / Integer(2)

    w_dir = butting_timber.get_width_direction_global()
    h_dir = butting_timber.get_height_direction_global()

    cross_section_span_on_notch_length = (
        Abs(safe_dot_product(w_dir, notch_length_dir_global)) * butting_timber.size[0]
        + Abs(safe_dot_product(h_dir, notch_length_dir_global)) * butting_timber.size[1]
    )

    approach_dot_depth = safe_dot_product(raw_approach, approach_direction_global)
    approach_dot_length = safe_dot_product(raw_approach, notch_length_dir_global)

    if not zero_test(approach_dot_depth):
        shift_along_length = notch_depth * Abs(approach_dot_length / approach_dot_depth)
    else:
        shift_along_length = Integer(0)

    notch_width = cross_section_span_on_notch_length + shift_along_length

    approach_direction_local = safe_transform_vector(
        notch_timber.orientation.matrix.T,
        approach_direction_global,
    )
    notch_length_dir_local = create_v3(Integer(0), Integer(0), Integer(1))

    prism_orientation = Orientation.from_z_and_x(approach_direction_local, notch_length_dir_local)
    prism_position_local = notch_timber.transform.global_to_local(intersection_global)

    notch_prism = RectangularPrism(
        size=create_v2(notch_width, notch_span),
        transform=Transform(position=prism_position_local, orientation=prism_orientation),
        start_distance=Integer(0),
        end_distance=notch_depth,
    )

    if notch_wall_relief_cut_angle_radians == 0:
        return notch_prism

    angle_rad = notch_wall_relief_cut_angle_radians
    span_direction_local = cross_product(approach_direction_local, notch_length_dir_local)
    span_direction_local = normalize_vector(span_direction_local)

    corner_point_1 = prism_position_local + notch_length_dir_local * (notch_width / Rational(2))
    corner_point_2 = prism_position_local - notch_length_dir_local * (notch_width / Rational(2))

    axis_1 = Axis(position=corner_point_1, direction=span_direction_local)
    axis_2 = Axis(position=corner_point_2, direction=span_direction_local)

    extended_end_distance = notch_depth / cos(angle_rad)

    left_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=notch_prism.transform.rotate_around_axis(axis_1, angle_rad),
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance,
    )
    right_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=notch_prism.transform.rotate_around_axis(axis_2, -angle_rad),
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance,
    )

    return SolidUnion([notch_prism, left_wall_prism, right_wall_prism])


def chop_shoulder_notch_on_timber_face(
    timber: TimberLike,
    notch_face: TimberFace,
    distance_along_timber: Numeric,
    notch_width: Numeric,
    notch_depth: Numeric,
    notch_wall_relief_cut_angle: Numeric = Integer(0),
) -> Union[RectangularPrism, SolidUnion]:
    """
    Create a rectangular shoulder notch on a timber face with optional angled walls.
    """
    from sympy import Rational, cos

    if notch_face == TimberFace.TOP or notch_face == TimberFace.BOTTOM:
        raise ValueError("Cannot cut shoulder notch on end faces (TOP or BOTTOM)")
    if notch_width <= 0:
        raise ValueError(f"notch_width must be positive, got {notch_width}")
    if notch_depth <= 0:
        raise ValueError(f"notch_depth must be positive, got {notch_depth}")
    if distance_along_timber < 0 or distance_along_timber > timber.length:
        raise ValueError(
            f"distance_along_timber must be between 0 and timber.length ({timber.length}), "
            f"got {distance_along_timber}"
        )
    if notch_wall_relief_cut_angle < 0 or notch_wall_relief_cut_angle >= 90:
        raise ValueError(
            f"notch_wall_relief_cut_angle must be between 0 and 90 degrees, got {notch_wall_relief_cut_angle}"
        )

    if notch_face == TimberFace.FRONT:
        position = create_v3(Integer(0), timber.size[1] / Rational(2) - notch_depth, distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(0), Integer(1), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, timber.size[0])
        corner_point_1 = create_v3(
            Integer(0),
            timber.size[1] / Rational(2) - notch_depth,
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            Integer(0),
            timber.size[1] / Rational(2) - notch_depth,
            distance_along_timber - notch_width / Rational(2),
        )
    elif notch_face == TimberFace.BACK:
        position = create_v3(Integer(0), -timber.size[1] / Rational(2) + notch_depth, distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(0), Integer(-1), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, timber.size[0])
        corner_point_1 = create_v3(
            Integer(0),
            -timber.size[1] / Rational(2) + notch_depth,
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            Integer(0),
            -timber.size[1] / Rational(2) + notch_depth,
            distance_along_timber - notch_width / Rational(2),
        )
    elif notch_face == TimberFace.RIGHT:
        position = create_v3(timber.size[0] / Rational(2) - notch_depth, Integer(0), distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(1), Integer(0), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, timber.size[1])
        corner_point_1 = create_v3(
            timber.size[0] / Rational(2) - notch_depth,
            Integer(0),
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            timber.size[0] / Rational(2) - notch_depth,
            Integer(0),
            distance_along_timber - notch_width / Rational(2),
        )
    else:
        position = create_v3(-timber.size[0] / Rational(2) + notch_depth, Integer(0), distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(-1), Integer(0), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, timber.size[1])
        corner_point_1 = create_v3(
            -timber.size[0] / Rational(2) + notch_depth,
            Integer(0),
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            -timber.size[0] / Rational(2) + notch_depth,
            Integer(0),
            distance_along_timber - notch_width / Rational(2),
        )

    notch_additional_depth = timber.get_half_nominal_size_in_face_normal_axis(notch_face)

    notch_prism = RectangularPrism(
        size=prism_size,
        transform=Transform(position=position, orientation=orientation),
        start_distance=Integer(0),
        end_distance=notch_depth + notch_additional_depth,
    )

    if notch_wall_relief_cut_angle == 0:
        return notch_prism

    angle_rad = degrees(notch_wall_relief_cut_angle)

    if notch_face == TimberFace.FRONT or notch_face == TimberFace.BACK:
        axis_direction = create_v3(Integer(1), Integer(0), Integer(0))
    else:
        axis_direction = create_v3(Integer(0), Integer(1), Integer(0))

    axis_1 = Axis(position=corner_point_1, direction=axis_direction)
    axis_2 = Axis(position=corner_point_2, direction=axis_direction)

    extended_end_distance = (notch_depth + notch_additional_depth) / cos(angle_rad)

    left_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=notch_prism.transform.rotate_around_axis(axis_1, radians(angle_rad)),
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance,
    )
    right_wall_prism = RectangularPrism(
        size=notch_prism.size,
        transform=notch_prism.transform.rotate_around_axis(axis_2, radians(-angle_rad)),
        start_distance=notch_prism.start_distance,
        end_distance=extended_end_distance,
    )

    return SolidUnion([notch_prism, left_wall_prism, right_wall_prism])
