"""
Kumiki - Notching helpers

Shared helper functions for shoulder-plane calculations and notch CSG generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from sympy import Abs, Max, Min, Rational, acos

from kumiki.construction import ButtJointTimberArrangement, ArrangementNames
from kumiki.cutcsg import (
    CutCSG,
    Difference,
    HalfSpace,
    RectangularPrism,
    SolidUnion,
    adopt_csg,
    make_finite_rectangular_prism_from_half_space,
)
from kumiki.measuring import Plane, locate_centerline, locate_plane_from_edge_in_direction
from kumiki.rule import *
from kumiki.timber import TimberCenterline, TimberFace, TimberLike, TimberReferenceEnd
from kumiki.timber_shavings import (
    are_timbers_plane_aligned,
    get_perfect_support_distance_from_centerline,
)

@dataclass(frozen=True)
class CrossJointNotchingConfig:
    """
    Configuration for cross joint notching
    """
    timber_to_be_notched: ArrangementNames


def _projected_perfect_cross_section_span_along_global_direction(
    timber: TimberLike,
    direction_global: V3,
) -> Numeric:
    """Projected full cross-section span of a timber along a global direction."""
    direction_local = safe_transform_vector(timber.orientation.matrix.T, direction_global)
    direction_local_2d = create_v2(direction_local[0], direction_local[1])
    return Integer(2) * get_perfect_support_distance_from_centerline(timber, direction_local_2d)


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

    cross_section_span_on_notch_length = _projected_perfect_cross_section_span_along_global_direction(
        butting_timber,
        notch_length_dir_global,
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
class ShoulderNotchCSGGeometry:
    """
    CSG geometry produced by ``chop_notch_for_butt_joint_arrangement``.

    - ``receiving_timber_notch_negative_CSG``: cut applied to the receiving
      (mortise) timber, expressed in that timber's local frame.
    - ``butting_timber_relief_negative_CSG``: cut applied to the butting
      (tenon) timber, expressed in that timber's local frame. ``None`` only
      when no relief geometry is necessary (currently always populated).
    """
    receiving_timber_notch_negative_CSG: Union[RectangularPrism, SolidUnion]
    butting_timber_relief_negative_CSG: CutCSG | None


def chop_notch_for_butt_joint_arrangement(
    arrangement: ButtJointTimberArrangement,
    mortise_shoulder_distance_from_centerline: Numeric,
    # the min is taken between this parameter and the angle the butt timber
    # approaches the shoulder plane at (both in radians)
    notch_wall_min_relief_cut_angle: Numeric = Integer(0),
    use_receiving_timber_nominal_size_for_butting_timber_relief_depth: bool = True,
) -> ShoulderNotchCSGGeometry | None:
    """
    Compute the shoulder notch on the receiving timber AND the matching
    relief cut on the butting timber for a butt-joint arrangement.

    Returns ``None`` when no notch is required (shoulder sits at or past the
    receiving timber's nominal entry face).
    """
    from sympy import sqrt

    if not does_shoulder_plane_need_notching(
        arrangement,
        mortise_shoulder_distance_from_centerline,
        check_against_nominal_size=True,
    ):
        return None

    receiving_timber = arrangement.receiving_timber
    butt_timber = arrangement.butt_timber
    butt_timber_end = arrangement.butt_timber_end

    # Direction from butt body out the joining end (= into receiving timber).
    butt_end_face = (
        TimberFace.TOP if butt_timber_end == TimberReferenceEnd.TOP else TimberFace.BOTTOM
    )
    butt_end_direction_global = butt_timber.get_face_direction_global(butt_end_face)

    # Approach direction projected perpendicular to receiving timber's length axis.
    receiving_length_dir = receiving_timber.get_length_direction_global()
    projected = butt_end_direction_global - receiving_length_dir * safe_dot_product(
        butt_end_direction_global, receiving_length_dir
    )
    approach_into_receiving = normalize_vector(projected)

    # Angle the butt timber makes with the shoulder-plane normal (0 when perpendicular).
    cos_butt_dev = safe_dot_product(butt_end_direction_global, approach_into_receiving)
    butt_approach_angle_radians = acos(Abs(cos_butt_dev))

    # Notch wall relief angle: min(user cap, actual butt approach angle).
    relief_angle_radians = Min(notch_wall_min_relief_cut_angle, butt_approach_angle_radians)

    # Shoulder plane and joint-center intersection (butt centerline meets shoulder plane).
    shoulder_plane = locate_plane_from_edge_in_direction(
        receiving_timber,
        TimberCenterline.CENTERLINE,
        -approach_into_receiving,
        mortise_shoulder_distance_from_centerline,
    )
    butt_centerline = locate_centerline(butt_timber)
    denom = safe_dot_product(shoulder_plane.normal, butt_centerline.direction)
    assert not zero_test(denom), "Butt centerline is parallel to the shoulder plane"
    t = safe_dot_product(
        shoulder_plane.normal, shoulder_plane.point - butt_centerline.point
    ) / denom
    joint_center_global = butt_centerline.point + butt_centerline.direction * t

    # Distance along the receiving timber to the joint center.
    joint_center_in_receiver_local = receiving_timber.transform.global_to_local(
        joint_center_global
    )
    distance_along_receiver = joint_center_in_receiver_local[2]

    # Receiving timber notch: keep the original alignment-based shoulder notch
    # behavior so the notch is oriented by the butt approach direction rather
    # than locked to a single face.
    receiving_timber_notch_local = chop_shoulder_notch_aligned_with_timber(
        notch_timber=receiving_timber,
        butting_timber=butt_timber,
        butting_timber_end=butt_timber_end,
        distance_from_centerline=mortise_shoulder_distance_from_centerline,
        notch_wall_relief_cut_angle_radians=relief_angle_radians,
    )

    # ------------------------------------------------------------------
    # Butting timber relief
    # ------------------------------------------------------------------
    # 1. Receiving extent in approach direction (shoulder plane -> far face).
    far_face = receiving_timber.get_closest_oriented_long_face_from_global_direction(
        butt_end_direction_global
    ).to.face()
    if use_receiving_timber_nominal_size_for_butting_timber_relief_depth:
        far_face_half_size = receiving_timber.get_half_nominal_size_in_face_normal_axis(far_face)
    else:
        far_face_half_size = receiving_timber.get_size_in_face_normal_axis(far_face) / Integer(2)
    receiving_extent_in_approach = (
        mortise_shoulder_distance_from_centerline + far_face_half_size
    )

    # TODO this is not required, only if yo uwant the -|_|- kinda shape which is useful if the relief angle is close to zero
    # for relief angles closer to 45 better not to have this at all, but in order for that to work, you need to modify the relief cut prisms to extend out far enough to cut off the non-perfect sides of the butting timber
    # 2. Half space at the far face of the receiving timber, pointing TOWARDS
    #    the joint (so it covers the region on the butt side, including the
    #    notch and the butt-prism region inside the receiving timber).
    far_face_point_global = (
        shoulder_plane.point + approach_into_receiving * receiving_extent_in_approach
    )

    halfspace_global = HalfSpace(
        normal=approach_into_receiving,
        offset=safe_dot_product(-approach_into_receiving, far_face_point_global),
    )

    # 3. Prism matching the butt timber's perfect cross-section, extending
    #    along the butt centerline from past the shoulder plane to past the
    #    far face of the receiving timber.
    if zero_test(cos_butt_dev):
        butt_extent_along_centerline = receiving_extent_in_approach
    else:
        butt_extent_along_centerline = receiving_extent_in_approach / Abs(cos_butt_dev)
    joint_center_in_butt_local = butt_timber.transform.global_to_local(joint_center_global)
    joint_center_butt_z = joint_center_in_butt_local[2]
    extra = Max(butt_timber.size[0], butt_timber.size[1])
    butt_prism_in_butt_local = RectangularPrism(
        size=butt_timber.size,
        transform=Transform(
            position=create_v3(Integer(0), Integer(0), joint_center_butt_z),
            orientation=Orientation.from_z_and_x(
                create_v3(Integer(0), Integer(0), Integer(1)),
                create_v3(Integer(1), Integer(0), Integer(0)),
            ),
        ),
        start_distance=-butt_extent_along_centerline - extra,
        end_distance=butt_extent_along_centerline + extra,
    )

    # 4. Difference: take the half-space and remove the notch and the butt
    #    prism from it, in the butt timber's local frame, to produce the
    #    relief cut.
    notch_in_butt_local = adopt_csg(
        receiving_timber.transform, butt_timber.transform, receiving_timber_notch_local
    )
    halfspace_in_butt_local = adopt_csg(None, butt_timber.transform, halfspace_global)
    relief_in_butt_local = Difference(
        base=halfspace_in_butt_local,
        subtract=[notch_in_butt_local, butt_prism_in_butt_local],
    )

    return ShoulderNotchCSGGeometry(
        receiving_timber_notch_negative_CSG=receiving_timber_notch_local,
        butting_timber_relief_negative_CSG=relief_in_butt_local,
    )


# TODO this is wrong
# we need to remove the timber_to_be_cut's perfect timber within portion from the timber_to_be_scribed's (actual timber - perfect timber within) portion
# TODO rename the 2 variables and return a pair of CutCSGs
def chop_scribe_notch(
    timber_to_be_scribed: TimberLike,
    timber_to_be_cut: TimberLike,
) -> CutCSG:
    """
    scribes timber_to_be_scribed onto timber_to_be_cut such that the entirety of timber_to_be_scribed is cut out of timber_to_be_cut excluding the perfect timber within portion of timber_to_be_cut

    returns the CSG geometery in timber_to_be_cut's local space!
    """
    timber_to_be_scribed_actual_csg_local = timber_to_be_scribed.get_extended_actual_csg_local(
        extend_bot=False,
        extend_top=False,
    )
    timber_to_be_scribed_actual_csg_in_timber_to_be_cut_local = adopt_csg(
        timber_to_be_scribed.transform,
        timber_to_be_cut.transform,
        timber_to_be_scribed_actual_csg_local,
    )
    timber_to_be_cut_perfect_csg_local = timber_to_be_cut.get_perfect_timber_within_CSG_local()
    scribe_notch_csg_local = Difference(
        base=timber_to_be_scribed_actual_csg_in_timber_to_be_cut_local,
        subtract=[timber_to_be_cut_perfect_csg_local],
    )
    return scribe_notch_csg_local