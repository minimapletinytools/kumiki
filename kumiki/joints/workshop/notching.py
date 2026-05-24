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
from kumiki.timber_shavings import are_timbers_plane_aligned


def does_shoulder_plane_need_notching(
    arrangement: ButtJointTimberArrangement,
    mortise_shoulder_distance_from_centerline: Numeric,
    check_against_nominal_size: bool = True,
) -> bool:
    """
    Determines whether a shoulder notch is needed on the mortise timber.

    For plane-aligned timbers, checks whether the shoulder is inset from the
    mortise face surface. For non-plane-aligned timbers, always returns True.

    Args:
        arrangement: Butt joint arrangement (receiving_timber = mortise, butt_timber = tenon).
        mortise_shoulder_distance_from_centerline: Distance from the mortise centerline
            to the shoulder plane, measured toward the tenon.
        check_against_nominal_size: If True (default), compare against the mortise timber's
            nominal half-size on the entry face (using ``get_half_nominal_size_in_face_normal_axis``).
            If False, compare against the perfect-timber half-size (``get_size_in_face_normal_axis / 2``).
    """
    mortise_timber = arrangement.receiving_timber
    tenon_timber = arrangement.butt_timber
    tenon_end = arrangement.butt_timber_end

    # we could check if the shoulder plane intersects the timber here, but then you'd have an unsupported tenon shoulder which is likely unintentional and certainly rare.
    # so just assume it does intersect and a notch is required
    if not are_timbers_plane_aligned(mortise_timber, tenon_timber):
        return True

    tenon_end_direction = tenon_timber.get_face_direction_global(
        TimberFace.TOP if tenon_end == TimberReferenceEnd.TOP else TimberFace.BOTTOM
    )
    mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    if check_against_nominal_size:
        face_half_size = mortise_timber.get_half_nominal_size_in_face_normal_axis(mortise_face)
    else:
        face_half_size = mortise_timber.get_size_in_face_normal_axis(mortise_face) / Integer(2)
    return (
        mortise_shoulder_distance_from_centerline < face_half_size
        and not zero_test(face_half_size - mortise_shoulder_distance_from_centerline)
    )


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

    max_size = Max(
        notch_timber.get_nominal_size_in_face_normal_axis(TimberFace.RIGHT),
        notch_timber.get_nominal_size_in_face_normal_axis(TimberFace.FRONT),
    )
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

    # Use nominal half-sizes so asymmetric timbers (where the centerline isn't
    # at the geometric center of the nominal bounding box) place the notch at
    # the correct face plane.
    half_face_offset = timber.get_half_nominal_size_in_face_normal_axis(notch_face)

    if notch_face == TimberFace.FRONT:
        cross_span = timber.get_nominal_size_in_face_normal_axis(TimberFace.RIGHT)
        position = create_v3(Integer(0), half_face_offset - notch_depth, distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(0), Integer(1), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            Integer(0),
            half_face_offset - notch_depth,
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            Integer(0),
            half_face_offset - notch_depth,
            distance_along_timber - notch_width / Rational(2),
        )
    elif notch_face == TimberFace.BACK:
        cross_span = timber.get_nominal_size_in_face_normal_axis(TimberFace.RIGHT)
        position = create_v3(Integer(0), -half_face_offset + notch_depth, distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(0), Integer(-1), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            Integer(0),
            -half_face_offset + notch_depth,
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            Integer(0),
            -half_face_offset + notch_depth,
            distance_along_timber - notch_width / Rational(2),
        )
    elif notch_face == TimberFace.RIGHT:
        cross_span = timber.get_nominal_size_in_face_normal_axis(TimberFace.FRONT)
        position = create_v3(half_face_offset - notch_depth, Integer(0), distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(1), Integer(0), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            half_face_offset - notch_depth,
            Integer(0),
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            half_face_offset - notch_depth,
            Integer(0),
            distance_along_timber - notch_width / Rational(2),
        )
    else:
        cross_span = timber.get_nominal_size_in_face_normal_axis(TimberFace.FRONT)
        position = create_v3(-half_face_offset + notch_depth, Integer(0), distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(Integer(-1), Integer(0), Integer(0)),
            create_v3(Integer(0), Integer(0), Integer(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            -half_face_offset + notch_depth,
            Integer(0),
            distance_along_timber + notch_width / Rational(2),
        )
        corner_point_2 = create_v3(
            -half_face_offset + notch_depth,
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



@dataclass(frozen=True)
class ShoulderNotchCSGGeometry():
    receiving_timber_notch_negative_CSG: Union[RectangularPrism, SolidUnion]
    butting_timber_relief_negative_CSG: Union[RectangularPrism, SolidUnion] | None

chop_notch_for_butt_joint_arrangement(
    arrangement: ButtJointTimberArrangement,
    mortise_shoulder_distance_from_centerline: Numeric,
    # the min is taken between this parameter and the angle the butt timber approaches the shoulder plane at
    notch_wall_min_relief_cut_angle: Numeric = Integer(0),
    use_receiving_timber_nominal_size_for_butting_timber_relief_depth = True,
) -> ShoulderNotchCSGGeometry | None:

    # determine the butt timber approach angle
    # copmute the notch relief angle
    # cut the notch using chop_shoulder_notch_on_timber_face

    # next cut the relief on the butting timber
    # 1. first determine how far the receiving timber extends in the direction of the butt timber approach (based on its nominal or perfect size depending on the use_receiving_timber_nominal_size_for_butting_timber_relief_depth flag)
    # 2. create a half space parallel to the shoulder plane at this distance pointing away from the joint
    # 3. next create a prism matching the perfect timber size of the butting timber, it should extend from the half space to the shoulder plane (you can go beyond this too if convenient)
    # 4. take the notch geometery returned by chop_shoulder_notch_on_timber_face and the difference it with the half space and prism from 2./3. to get the relief cut geometry
    
    # return the results
    pass