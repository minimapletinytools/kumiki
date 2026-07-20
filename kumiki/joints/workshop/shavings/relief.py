"""
Kumiki - Relief helpers

Shared helper functions for shoulder-plane calculations and relief CSG generation.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from typing import Optional, Union

from sympy import Abs, Max, Min, acos

from kumiki.construction import ButtJointTimberArrangement, ArrangementNames
from kumiki.cutcsg import (
    CutCSG,
    Difference,
    HalfSpace,
    Intersection,
    RectangularPrism,
    SolidUnion,
    adopt_csg,
    make_finite_rectangular_prism_from_half_space,
    EmptyCSG,
)
from kumiki.measuring import Plane, locate_centerline, locate_plane_from_edge_in_direction
from kumiki.rule import *
from kumiki.timber import Cutting, TimberCenterline, TimberFace, TimberLike, TimberEnd, TimberLongFace
from kumiki.timber_shavings import (
    are_timbers_plane_aligned,
    get_perfect_support_distance_from_centerline,
)


IMPERFECT_TIMBER_WARNING = (
    "timber is imperfect (does not match perfect timber within), this joint currently does not supporting maknig relief cuts beyond the perfect timber within so the joint may not actually fit"
)


_raw_safe_dot_product = safe_dot_product
_raw_safe_norm = safe_norm
_raw_safe_transform_vector = safe_transform_vector


def safe_dot_product(*args, **kwargs):
    return prune(_raw_safe_dot_product(*args, **kwargs))


def safe_norm(*args, **kwargs):
    return prune(_raw_safe_norm(*args, **kwargs))


def safe_transform_vector(*args, **kwargs):
    return prune(_raw_safe_transform_vector(*args, **kwargs))


def warn_if_arrangement_timbers_imperfect(arrangement) -> None:
    """Warn when a joint arrangement uses any timber that is not perfect."""
    check_perfection = getattr(arrangement, "check_perfection", None)
    if not callable(check_perfection):
        return
    error = check_perfection()
    if error is not None:
        warnings.warn(IMPERFECT_TIMBER_WARNING, stacklevel=2)

@dataclass(frozen=True)
class CrossJointScribeReliefConfig:
    """
    Configuration for cross joint relief
    "Scribe" here means one timber is scribed onto the other and completely cut away
    """
    timber_to_be_scribed: ArrangementNames

    @staticmethod
    def cross_timber_1():
        return CrossJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.cross_timber_1,
        )

    @staticmethod
    def cross_timber_2():
        return CrossJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.cross_timber_2,
        )


@dataclass(frozen=True)
class ButtJointScribeReliefConfig:
    """
    Configuration for butt joint relief
    "Scribe" here means one timber is scribed onto the other and completely cut away
    """
    timber_to_be_scribed: ArrangementNames

    @staticmethod
    def butt_timber():
        return ButtJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.butt_timber,
        )

    @staticmethod
    def receiving_timber():
        return ButtJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.receiving_timber,
        )


@dataclass(frozen=True)
class SpliceJointScribeReliefConfig:
    """
    Configuration for splice joint relief
    "Scribe" here means one timber is scribed onto the other and completely cut away
    """
    timber_to_be_scribed: ArrangementNames

    @staticmethod
    def timber1():
        return SpliceJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.timber1,
        )

    @staticmethod
    def timber2():
        return SpliceJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.timber2,
        )


@dataclass(frozen=True)
class CornerJointScribeReliefConfig:
    """
    Configuration for corner joint relief
    "Scribe" here means one timber is scribed onto the other and completely cut away
    """
    timber_to_be_scribed: ArrangementNames

    @staticmethod
    def timber1():
        return CornerJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.timber1,
        )

    @staticmethod
    def timber2():
        return CornerJointScribeReliefConfig(
            timber_to_be_scribed=ArrangementNames.timber2,
        )


@dataclass(frozen=True)
class DoubleButtJointScribeReliefConfig:
    """
    Configuration for double butt joint relief.

    ``first_timber_to_be_scribed`` is scribed first, then
    ``second_timber_to_be_scribed`` is scribed onto the remaining timber.
    """
    first_timber_to_be_scribed: ArrangementNames
    second_timber_to_be_scribed: ArrangementNames

    @staticmethod
    def with_order(
        first_timber_to_be_scribed: ArrangementNames,
        second_timber_to_be_scribed: ArrangementNames,
    ):
        return DoubleButtJointScribeReliefConfig(
            first_timber_to_be_scribed=first_timber_to_be_scribed,
            second_timber_to_be_scribed=second_timber_to_be_scribed,
        )


@dataclass(frozen=True)
class TripleButtJointScribeReliefConfig:
    """
    Configuration for triple butt joint relief.

    ``first_timber_to_be_scribed`` is scribed first, then
    ``second_timber_to_be_scribed``, then ``third_timber_to_be_scribed``.
    """
    first_timber_to_be_scribed: ArrangementNames
    second_timber_to_be_scribed: ArrangementNames
    third_timber_to_be_scribed: ArrangementNames

    @staticmethod
    def with_order(
        first_timber_to_be_scribed: ArrangementNames,
        second_timber_to_be_scribed: ArrangementNames,
        third_timber_to_be_scribed: ArrangementNames,
    ):
        return TripleButtJointScribeReliefConfig(
            first_timber_to_be_scribed=first_timber_to_be_scribed,
            second_timber_to_be_scribed=second_timber_to_be_scribed,
            third_timber_to_be_scribed=third_timber_to_be_scribed,
        )


@dataclass(frozen=True)
class QuadrupleButtJointScribeReliefConfig:
    """
    Configuration for quadruple butt joint relief.

    ``first_timber_to_be_scribed`` is scribed first, then
    ``second_timber_to_be_scribed``, ``third_timber_to_be_scribed``, and
    ``fourth_timber_to_be_scribed``.
    """
    first_timber_to_be_scribed: ArrangementNames
    second_timber_to_be_scribed: ArrangementNames
    third_timber_to_be_scribed: ArrangementNames
    fourth_timber_to_be_scribed: ArrangementNames

    @staticmethod
    def with_order(
        first_timber_to_be_scribed: ArrangementNames,
        second_timber_to_be_scribed: ArrangementNames,
        third_timber_to_be_scribed: ArrangementNames,
        fourth_timber_to_be_scribed: ArrangementNames,
    ):
        return QuadrupleButtJointScribeReliefConfig(
            first_timber_to_be_scribed=first_timber_to_be_scribed,
            second_timber_to_be_scribed=second_timber_to_be_scribed,
            third_timber_to_be_scribed=third_timber_to_be_scribed,
            fourth_timber_to_be_scribed=fourth_timber_to_be_scribed,
        )


@dataclass(frozen=True)
class CrossCapJointScribeReliefConfig:
    """
    Configuration for cross-cap joint relief.

    ``first_timber_to_be_scribed`` is scribed first, then
    ``second_timber_to_be_scribed`` is scribed onto the remaining timber.
    """
    first_timber_to_be_scribed: ArrangementNames
    second_timber_to_be_scribed: ArrangementNames

    @staticmethod
    def with_order(
        first_timber_to_be_scribed: ArrangementNames,
        second_timber_to_be_scribed: ArrangementNames,
    ):
        return CrossCapJointScribeReliefConfig(
            first_timber_to_be_scribed=first_timber_to_be_scribed,
            second_timber_to_be_scribed=second_timber_to_be_scribed,
        )


@dataclass(frozen=True)
class BraceJointScribeReliefConfig:
    """
    Configuration for brace joint relief.

    The 2 braced timbers are always scribed onto the brace timber.
    """
    first_timber_to_be_scribed: ArrangementNames
    second_timber_to_be_scribed: ArrangementNames

    @staticmethod
    def with_order(
        first_timber_to_be_scribed: ArrangementNames,
        second_timber_to_be_scribed: ArrangementNames,
    ):
        return BraceJointScribeReliefConfig(
            first_timber_to_be_scribed=first_timber_to_be_scribed,
            second_timber_to_be_scribed=second_timber_to_be_scribed,
        )



@dataclass(frozen=True)
class DropinButtJointSweepScribeReliefConfig:
    """
    Configuration for drop in butt joint relief

    The butting (drop in) timber is always scribed onto the receiving timber

    Actually the butting timber and its entire swept volume in the drop-in path are scribed onto the receiving timber
    """
    pass



def _perfect_cross_section_slice_span_along_plane_direction(
    timber: TimberLike,
    slice_plane_normal_global: Direction3D,
    measure_direction_global: Direction3D,
) -> Numeric:
    """
    Full span, along ``measure_direction_global``, of the timber's perfect
    cross-section sliced by a plane with normal ``slice_plane_normal_global``.
    ``measure_direction_global`` must lie in the slice plane.

    The timber is an oblique prism: cross-section extruded along its length
    axis b. Slicing it with a plane stretches the footprint. A cross-section
    point p lands on the plane at p + t*b (t solved per point from the plane
    equation), so its coordinate along an in-plane direction d is dot(p, e)
    with

        e = d - n * (dot(b, d) / dot(b, n))        (n = plane normal)

    e is perpendicular to b by construction (dot(e, b) == 0), i.e. e lies in
    the cross-section plane, so the slice span along d is exactly the
    cross-section's support span along e -- where both the direction AND the
    magnitude of e matter (|e| grows as 1/cos of the timber's rake away from
    the plane normal, and e's direction within the cross-section shifts for
    compound rakes). Simply projecting d into the cross-section plane (what
    this function used to do) measures the cross-section's shadow instead and
    undershoots by that same secant factor.
    """
    b = timber.get_length_direction_global()
    n = slice_plane_normal_global
    d = measure_direction_global
    assert zero_test(safe_dot_product(d, n)), "measure_direction_global must lie in the slice plane"
    b_dot_n = safe_dot_product(b, n)
    assert not zero_test(b_dot_n), "Timber length axis is parallel to the slice plane"

    e_global = d - n * (safe_dot_product(b, d) / b_dot_n)
    e_local = safe_transform_vector(timber.orientation.matrix.T, e_global)
    # e is perpendicular to the length axis (local Z), so e_local[2] == 0 and
    # the 2D cross-section support captures all of it.
    e_local_2d = create_v2(e_local[0], e_local[1])
    e_length = safe_norm(e_local_2d)
    # get_perfect_support_distance_from_centerline normalizes its direction
    # argument, so the stretch magnitude |e| is applied here. The perfect
    # cross-section is symmetric about the centerline, hence span = 2*support.
    return scalar(2) * e_length * get_perfect_support_distance_from_centerline(timber, e_local_2d)


def does_shoulder_plane_need_notching(
    arrangement: ButtJointTimberArrangement,
    mortise_shoulder_distance_from_centerline_or_centerplane: Numeric,
    check_against_nominal_size: bool = True,
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool] = False,
) -> bool:
    """
    Determines whether a shoulder notch is needed on the mortise timber.

    For plane-aligned timbers, checks whether the shoulder is inset from the
    mortise face surface. For non-plane-aligned timbers, always returns True.

    Args:
        arrangement: Butt joint arrangement (receiving_timber = mortise, butt_timber = tenon).
        mortise_shoulder_distance_from_centerline_or_centerplane: Distance from the mortise centerline
            to the shoulder plane, measured toward the tenon.
        check_against_nominal_size: If True (default), compare against the mortise timber's
            nominal half-size on the entry face (using ``get_half_nominal_size_in_face_normal_axis``).
            If False, compare against the perfect-timber half-size (``get_size_in_face_normal_axis / 2``).
        set_mortise_shoulder_parallel_to_face: If set to a face, then force the mortise shoulder to be parallel to that face.
    """
    mortise_timber = arrangement.receiving_timber
    tenon_timber = arrangement.butt_timber
    tenon_end = arrangement.butt_timber_end

    # we could check if the shoulder plane intersects the timber here, but then you'd have an unsupported tenon shoulder which is likely unintentional and certainly rare.
    # so just assume it does intersect and a notch is required
    if not are_timbers_plane_aligned(mortise_timber, tenon_timber):
        return True

    tenon_end_direction = tenon_timber.get_face_direction_global(
        TimberFace.TOP if tenon_end == TimberEnd.TOP else TimberFace.BOTTOM
    )
    if set_mortise_shoulder_parallel_to_face is not False:
        if set_mortise_shoulder_parallel_to_face is True:
            x_axis = mortise_timber.get_width_direction_global()
            y_axis = mortise_timber.get_height_direction_global()
            dot_x = abs(safe_dot_product(tenon_end_direction, x_axis))
            dot_y = abs(safe_dot_product(tenon_end_direction, y_axis))
            proj = tenon_end_direction - mortise_timber.get_length_direction_global() * safe_dot_product(tenon_end_direction, mortise_timber.get_length_direction_global())
            if dot_x < dot_y:
                if safe_dot_product(x_axis, proj) > 0:
                    mortise_face = TimberFace.RIGHT
                else:
                    mortise_face = TimberFace.LEFT
            else:
                if safe_dot_product(y_axis, proj) > 0:
                    mortise_face = TimberFace.FRONT
                else:
                    mortise_face = TimberFace.BACK
        else:
            mortise_face = set_mortise_shoulder_parallel_to_face.to.face()
    else:
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()

    if check_against_nominal_size:
        face_half_size = mortise_timber.get_half_nominal_size_in_face_normal_axis(mortise_face)
    else:
        face_half_size = mortise_timber.get_size_in_face_normal_axis(mortise_face) / scalar(2)
    return (
        mortise_shoulder_distance_from_centerline_or_centerplane < face_half_size
        and not zero_test(face_half_size - mortise_shoulder_distance_from_centerline_or_centerplane)
    )


def chop_shoulder_notch_aligned_with_timber(
    notch_timber: TimberLike,
    butting_timber: TimberLike,
    butting_timber_end: TimberEnd,
    distance_from_centerline: Numeric,
    notch_wall_relief_cut_angle_radians: Numeric = scalar(0),
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool] = False,
) -> Union[RectangularPrism, SolidUnion]:
    """
    Create a shoulder notch on notch_timber at a given distance from its centerline,
    oriented by the butting_timber's approach direction.

    Unlike chop_shoulder_notch_on_timber_face which is aligned to a specific face,
    this notch is aligned to the shoulder plane derived from the butting timber's
    approach direction (projected perpendicular to the notch timber's length axis if set_mortise_shoulder_parallel_to_face is not False).

    The notch bottom (shoulder plane) is distance_from_centerline away from the
    notch_timber's centerline. The notch opens outward from the centerline.
    The notch width is along the notch_timber's length axis and hugs the
    butting timber's shoulder-plane slice exactly (its perfect cross-section;
    imperfect material beyond that is scribe relief's job, not the housing's).
    The span and depth clear the notch timber's entire nominal cross-section
    via a worst-case corner-radius bound -- overshoot is free in both of those
    directions (the span channel exits the timber's sides, the depth exits its
    outer face) so neither needs to be exact.

    notch_wall_relief_cut_angle_radians is a MINIMUM: the walls are always
    relieved by at least the butting timber's rake away from the shoulder-plane
    normal, since anything less would leave housing walls colliding with the
    raking butting timber above the shoulder plane.
    """
    from sympy import Max, cos, sqrt

    notch_length_dir_global = notch_timber.get_length_direction_global()

    if butting_timber_end == TimberEnd.TOP:
        raw_approach = -butting_timber.get_length_direction_global()
    else:
        raw_approach = butting_timber.get_length_direction_global()

    projected = raw_approach - notch_length_dir_global * safe_dot_product(
        raw_approach, notch_length_dir_global
    )

    # the approach direction projected onto the plane perpendicular to the notch timber's length axis
    perpendicular_approach_direction_global = normalize_vector(projected)

    arrangement = ButtJointTimberArrangement(
        butt_timber=butting_timber,
        receiving_timber=notch_timber,
        butt_timber_end=butting_timber_end,
    )

    if set_mortise_shoulder_parallel_to_face:
        from kumiki.joints.workshop.shavings.build_a_butt import (
            locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face,
            resolve_parallel_shoulder_face,
        )
        resolved_face = resolve_parallel_shoulder_face(arrangement, set_mortise_shoulder_parallel_to_face)
        shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face(
            arrangement,
            distance_from_centerline,
            resolved_face,
        )
    else:
        from kumiki.joints.workshop.shavings.build_a_butt import locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber
        shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement,
            distance_from_centerline,
        )

    shoulder_plane_normal = shoulder_plane.normal
    butting_centerline = locate_centerline(butting_timber)
    denom = safe_dot_product(shoulder_plane.normal, butting_centerline.direction)
    assert not zero_test(denom), "Butting timber centerline is parallel to the shoulder plane"
    t = safe_dot_product(
        shoulder_plane.normal,
        shoulder_plane.point - butting_centerline.point,
    ) / denom
    intersection_global = butting_centerline.point + butting_centerline.direction * t

    # ------------------------------------------------------------------
    # Notch prism dimensions. The three prism axes (all mutually
    # perpendicular): depth extrudes along the approach direction outward
    # from the shoulder plane, width runs along the notch timber's length
    # axis, span runs across the notch timber's cross-section.
    # ------------------------------------------------------------------

    # Span and depth must clear the notch timber's entire nominal
    # (imperfect-bounding) cross-section regardless of how that cross-section
    # is rotated about the length axis, and overshoot in both directions is
    # free (span exits the timber's sides, depth exits its outer face), so
    # both are sized from the worst-case corner radius -- the farthest any
    # nominal-corner can be from the centerline under any rotation -- rather
    # than computed exactly for the specific directions.
    notch_timber_width_halves, notch_timber_height_halves = notch_timber.get_nominal_half_sizes()
    max_corner_radius = sqrt(
        Max(notch_timber_width_halves[0], notch_timber_width_halves[1]) ** 2
        + Max(notch_timber_height_halves[0], notch_timber_height_halves[1]) ** 2
    )
    # The prism is centered on intersection_global, which carries no offset
    # along the span direction as long as the two centerlines intersect: the
    # span direction is perpendicular to the plane spanned by both length
    # axes, and the intersection only ever moves within that plane.
    notch_span = scalar(2) * max_corner_radius
    # Depth is measured outward from the shoulder plane (start_distance=0 on
    # the prism below), so the material to clear is at most
    # max_corner_radius - distance_from_centerline; the Max keeps the prism
    # comfortably non-degenerate when the shoulder sits near the surface.
    notch_depth = Max(scalar(2) * max_corner_radius - distance_from_centerline, max_corner_radius)

    # Width must hug the butting timber exactly -- unlike span/depth,
    # overshoot here is NOT free: it would widen the housing and cut away
    # seat material. This is the true footprint of the butting timber's
    # (perfect) cross-section sliced by the shoulder plane.
    #
    # The notch width axis is the projection of the butting timber's length
    # axis onto the shoulder plane. For the centerline-derived shoulder plane
    # this coincides with notch_length_dir_global (no change). For
    # face-parallel shoulder planes (compound angles) the tenon may rake in
    # both the length and span directions of the receiving timber, so we use
    # the actual projected tenon direction as the notch width axis to keep
    # the notch tight against the tenon on both walls.
    b_global = butting_centerline.direction
    n_global = shoulder_plane.normal
    b_in_plane = b_global - n_global * safe_dot_product(b_global, n_global)
    b_in_plane_len_sq = safe_dot_product(b_in_plane, b_in_plane)
    if not zero_test(b_in_plane_len_sq):
        notch_width_axis_global = normalize_vector(b_in_plane)
    else:
        notch_width_axis_global = notch_length_dir_global

    notch_width = _perfect_cross_section_slice_span_along_plane_direction(
        butting_timber,
        shoulder_plane.normal,
        notch_width_axis_global,
    )

    approach_direction_local = safe_transform_vector(
        notch_timber.orientation.matrix.T,
        shoulder_plane_normal,
    )
    notch_width_axis_local = normalize_vector(
        safe_transform_vector(notch_timber.orientation.matrix.T, notch_width_axis_global)
    )

    prism_orientation = Orientation.from_z_and_x(approach_direction_local, notch_width_axis_local)
    prism_position_local = notch_timber.transform.global_to_local(intersection_global)

    # this prism is the "main" part of the notch
    notch_prism = RectangularPrism(
        size=create_v2(notch_width, notch_span),
        transform=Transform(position=prism_position_local, orientation=prism_orientation),
        start_distance=scalar(0),
        end_distance=notch_depth,
    )

    # The requested wall relief angle is a floor, not the final value: the
    # walls must be relieved by at least the butting timber's rake away from
    # the shoulder-plane normal, otherwise the housing walls would collide
    # with the raking butting timber above the shoulder plane.
    cos_butt_from_shoulder_normal = Abs(safe_dot_product(raw_approach, shoulder_plane.normal))
    butt_rake_from_shoulder_normal_radians = acos(Min(cos_butt_from_shoulder_normal, scalar(1)))
    wall_relief_angle_radians = Max(notch_wall_relief_cut_angle_radians, butt_rake_from_shoulder_normal_radians)

    if zero_test(wall_relief_angle_radians):
        return notch_prism

    angle_rad = wall_relief_angle_radians
    span_direction_local = cross_product(approach_direction_local, notch_width_axis_local)
    span_direction_local = normalize_vector(span_direction_local)

    corner_point_1 = prism_position_local + notch_width_axis_local * (notch_width / scalar(2))
    corner_point_2 = prism_position_local - notch_width_axis_local * (notch_width / scalar(2))

    axis_1 = Axis(position=corner_point_1, direction=span_direction_local)
    axis_2 = Axis(position=corner_point_2, direction=span_direction_local)

    extended_end_distance = notch_depth / cos(angle_rad)

    # these 2 prisms are the "relief" parts of the notch
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
    # TODO TimberLongFace
    notch_face: TimberFace,
    distance_along_timber: Numeric,
    notch_width: Numeric,
    notch_depth: Numeric,
    notch_wall_relief_cut_angle: Numeric = scalar(0),
) -> Union[RectangularPrism, SolidUnion]:
    """
    Create a rectangular shoulder notch on a timber face with optional angled walls.
    """
    from sympy import cos

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
        position = create_v3(scalar(0), half_face_offset - notch_depth, distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(scalar(0), scalar(1), scalar(0)),
            create_v3(scalar(0), scalar(0), scalar(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            scalar(0),
            half_face_offset - notch_depth,
            distance_along_timber + notch_width / scalar(2),
        )
        corner_point_2 = create_v3(
            scalar(0),
            half_face_offset - notch_depth,
            distance_along_timber - notch_width / scalar(2),
        )
    elif notch_face == TimberFace.BACK:
        cross_span = timber.get_nominal_size_in_face_normal_axis(TimberFace.RIGHT)
        position = create_v3(scalar(0), -half_face_offset + notch_depth, distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(scalar(0), scalar(-1), scalar(0)),
            create_v3(scalar(0), scalar(0), scalar(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            scalar(0),
            -half_face_offset + notch_depth,
            distance_along_timber + notch_width / scalar(2),
        )
        corner_point_2 = create_v3(
            scalar(0),
            -half_face_offset + notch_depth,
            distance_along_timber - notch_width / scalar(2),
        )
    elif notch_face == TimberFace.RIGHT:
        cross_span = timber.get_nominal_size_in_face_normal_axis(TimberFace.FRONT)
        position = create_v3(half_face_offset - notch_depth, scalar(0), distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(scalar(1), scalar(0), scalar(0)),
            create_v3(scalar(0), scalar(0), scalar(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            half_face_offset - notch_depth,
            scalar(0),
            distance_along_timber + notch_width / scalar(2),
        )
        corner_point_2 = create_v3(
            half_face_offset - notch_depth,
            scalar(0),
            distance_along_timber - notch_width / scalar(2),
        )
    else:
        cross_span = timber.get_nominal_size_in_face_normal_axis(TimberFace.FRONT)
        position = create_v3(-half_face_offset + notch_depth, scalar(0), distance_along_timber)
        orientation = Orientation.from_z_and_x(
            create_v3(scalar(-1), scalar(0), scalar(0)),
            create_v3(scalar(0), scalar(0), scalar(1)),
        )
        prism_size = create_v2(notch_width, cross_span)
        corner_point_1 = create_v3(
            -half_face_offset + notch_depth,
            scalar(0),
            distance_along_timber + notch_width / scalar(2),
        )
        corner_point_2 = create_v3(
            -half_face_offset + notch_depth,
            scalar(0),
            distance_along_timber - notch_width / scalar(2),
        )

    notch_additional_depth = timber.get_half_nominal_size_in_face_normal_axis(notch_face)

    notch_prism = RectangularPrism(
        size=prism_size,
        transform=Transform(position=position, orientation=orientation),
        start_distance=scalar(0),
        end_distance=notch_depth + notch_additional_depth,
    )

    if notch_wall_relief_cut_angle == 0:
        return notch_prism

    angle_rad = degrees(notch_wall_relief_cut_angle)

    if notch_face == TimberFace.FRONT or notch_face == TimberFace.BACK:
        axis_direction = create_v3(scalar(1), scalar(0), scalar(0))
    else:
        axis_direction = create_v3(scalar(0), scalar(1), scalar(0))

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
class ShoulderReliefCSGGeometry:
    """
    CSG geometry produced by ``chop_relief_for_butt_joint_arrangement``.

    - ``receiving_timber_notch_negative_CSG``: cut applied to the receiving
      (mortise) timber, expressed in that timber's local frame.
    - ``butting_timber_relief_negative_CSG``: cut applied to the butting
      (tenon) timber, expressed in that timber's local frame. ``None`` only
      when no relief geometry is necessary (currently always populated).
    """
    receiving_timber_notch_negative_CSG: CutCSG
    butting_timber_relief_negative_CSG: CutCSG | None


def chop_relief_for_butt_joint_arrangement(
    arrangement: ButtJointTimberArrangement,
    mortise_shoulder_distance_from_centerline_or_centerplane: Numeric,
    # the min is taken between this parameter and the angle the butt timber
    # approaches the shoulder plane at (both in radians)
    notch_wall_min_relief_cut_angle: Numeric = scalar(0),
    use_receiving_timber_nominal_size_for_butting_timber_relief_depth: bool = True,
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool] = False,
) -> ShoulderReliefCSGGeometry | None:
    """
    Compute the shoulder notch on the receiving timber AND the matching
    relief cut on the butting timber for a butt-joint arrangement.

    Returns ``None`` when no notch is required (shoulder sits at or past the
    receiving timber's nominal entry face).
    """
    from sympy import sqrt

    if not does_shoulder_plane_need_notching(
        arrangement,
        mortise_shoulder_distance_from_centerline_or_centerplane,
        check_against_nominal_size=True,
        set_mortise_shoulder_parallel_to_face=set_mortise_shoulder_parallel_to_face,
    ):
        return None

    receiving_timber = arrangement.receiving_timber
    butt_timber = arrangement.butt_timber
    butt_timber_end = arrangement.butt_timber_end

    # Direction from butt body out the joining end (= into receiving timber).
    butt_end_face = (
        TimberFace.TOP if butt_timber_end == TimberEnd.TOP else TimberFace.BOTTOM
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
    if set_mortise_shoulder_parallel_to_face:
        from kumiki.joints.workshop.shavings.build_a_butt import (
            locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face,
            resolve_parallel_shoulder_face,
        )
        resolved_face = resolve_parallel_shoulder_face(arrangement, set_mortise_shoulder_parallel_to_face)
        shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face(
            arrangement,
            mortise_shoulder_distance_from_centerline_or_centerplane,
            resolved_face,
        )
    else:
        from kumiki.joints.workshop.shavings.build_a_butt import locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber
        shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement,
            mortise_shoulder_distance_from_centerline_or_centerplane,
        )
    # The normal of the shoulder plane used in relief logic points away from the tenon.
    # The helper functions return normal pointing towards the tenon.
    shoulder_plane = Plane(normal=-shoulder_plane.normal, point=shoulder_plane.point)
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
        distance_from_centerline=mortise_shoulder_distance_from_centerline_or_centerplane,
        notch_wall_relief_cut_angle_radians=relief_angle_radians,
        set_mortise_shoulder_parallel_to_face=set_mortise_shoulder_parallel_to_face,
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
        far_face_half_size = receiving_timber.get_size_in_face_normal_axis(far_face) / scalar(2)
    receiving_extent_in_approach = (
        mortise_shoulder_distance_from_centerline_or_centerplane + far_face_half_size
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
            position=create_v3(scalar(0), scalar(0), joint_center_butt_z),
            orientation=Orientation.from_z_and_x(
                create_v3(scalar(0), scalar(0), scalar(1)),
                create_v3(scalar(1), scalar(0), scalar(0)),
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

    return ShoulderReliefCSGGeometry(
        receiving_timber_notch_negative_CSG=receiving_timber_notch_local,
        butting_timber_relief_negative_CSG=relief_in_butt_local,
    )


def chop_scribe_relief(
    timber_to_be_scribed: TimberLike,
    timber_to_be_scribed_cutting: Cutting,
    timber_to_be_cut: TimberLike,
) -> tuple[CutCSG, CutCSG]:
    """
    scribes timber_to_be_scribed onto timber_to_be_cut such that the entirety of timber_to_be_scribed is cut out of timber_to_be_cut excluding the perfect timber within portion of timber_to_be_cut

    timber_to_be_scribed_cutting is the cutting already computed for timber_to_be_scribed
    elsewhere in the current joint (e.g. the tenon's shoulder cut, plus any end cut) --
    material already removed there is excluded from what gets scribed onto timber_to_be_cut,
    otherwise the relief would be based on timber_to_be_scribed's full, uncut extent (its
    entire length) rather than just the part of it that actually survives near the joint.

    returns a pair of CSG geometries, the first to be removed from timber_to_be_scribed and the second to be removed from timber_to_be_cut, both expressed in their respective local frames
    """
    timber_to_be_scribed_actual_csg_global = adopt_csg(
        timber_to_be_scribed.transform,
        None,
        timber_to_be_scribed.get_extended_actual_csg_local(extend_bot=False, extend_top=False),
    )

    timber_to_be_scribed_perfect_csg_global = adopt_csg(
        timber_to_be_scribed.transform,
        None,
        timber_to_be_scribed.get_perfect_timber_within_csg_local(),
    )

    timber_to_be_scribed_own_cuts_global = adopt_csg(
        timber_to_be_scribed.transform,
        None,
        timber_to_be_scribed_cutting.get_negative_csg_local(),
    )

    timber_to_be_cut_perfect_csg_global = adopt_csg(
        timber_to_be_cut.transform,
        None,
        timber_to_be_cut.get_perfect_timber_within_csg_local(),
    )

    # seems to create triangulation artifacts when used on circular timbers with trimesh right now :(
    scribed_relief_global = Intersection(
        left=Difference(
            timber_to_be_scribed_actual_csg_global,
            subtract=[timber_to_be_scribed_perfect_csg_global],
        ),
        right=timber_to_be_cut_perfect_csg_global,
    )

    # What actually remains of timber_to_be_scribed's full extent (perfect core
    # AND imperfect fringe alike) near the joint, after its own cuts (shoulder,
    # end cut, etc.) are accounted for -- per this function's contract, the
    # ENTIRETY of timber_to_be_scribed needs a matching hollow in
    # timber_to_be_cut (excluding timber_to_be_cut's own perfect-within, which
    # is handled by the subtraction below). Using only the imperfect fringe
    # here would leave timber_to_be_cut's imperfect material un-cut wherever it
    # overlaps timber_to_be_scribed's perfect-within region.
    timber_to_be_scribed_actual_after_own_cuts_global = Difference(
        base=timber_to_be_scribed_actual_csg_global,
        subtract=[timber_to_be_scribed_own_cuts_global],
    )

    cut_relief_global = Difference(
        base=timber_to_be_scribed_actual_after_own_cuts_global,
        subtract=[timber_to_be_cut_perfect_csg_global],
    )


    scribed_relief_in_scribed_local = adopt_csg(
        None, timber_to_be_scribed.transform, scribed_relief_global
    )
    cut_relief_in_cut_local = adopt_csg(
        None, timber_to_be_cut.transform, cut_relief_global
    )

    return scribed_relief_in_scribed_local, cut_relief_in_cut_local


def chop_scribe_relief_and_apply(
    timber_to_be_scribed: TimberLike,
    timber_to_be_scribed_cutting: Cutting,
    timber_to_be_cut: TimberLike,
    timber_to_be_cut_cutting: Cutting,
) -> tuple[Cutting, Cutting]:
    """
    Apply scribe relief cuts from ``chop_scribe_relief`` to the given cuttings, unioning the
    new relief CSGs into each cutting's existing ``negative_csg``.

    Returns ``(updated_cut_cutting, updated_scribed_cutting)`` (matching the order of
    the early-return path when both timbers are perfect).
    """
    if timber_to_be_scribed.is_perfect_timber() and timber_to_be_cut.is_perfect_timber():
        return timber_to_be_cut_cutting, timber_to_be_scribed_cutting

    scribed_relief_csg_local, cut_relief_csg_local = chop_scribe_relief(
        timber_to_be_scribed=timber_to_be_scribed,
        timber_to_be_scribed_cutting=timber_to_be_scribed_cutting,
        timber_to_be_cut=timber_to_be_cut,
    )

    def _union_into(existing: Optional[CutCSG], new: CutCSG) -> CutCSG:
        if existing is None:
            return new
        return SolidUnion([existing, new])

    updated_scribed_cutting = replace(
        timber_to_be_scribed_cutting,
        negative_csg=_union_into(
            timber_to_be_scribed_cutting.negative_csg, scribed_relief_csg_local
        ),
    )
    updated_cut_cutting = replace(
        timber_to_be_cut_cutting,
        negative_csg=_union_into(
            timber_to_be_cut_cutting.negative_csg, cut_relief_csg_local
        ),
    )

    return updated_cut_cutting, updated_scribed_cutting


def chop_scribe_relief_and_apply_for_butt_joint_arrangement(
    arrangement: ButtJointTimberArrangement,
    relief: ButtJointScribeReliefConfig,
    butt_cut: Cutting,
    receiving_cut: Cutting,
) -> tuple[Cutting, Cutting]:
    """
    Helper shared by the butt-joint cutting functions: apply scribe relief
    between the butt and receiving timbers of ``arrangement``, honoring
    ``relief.timber_to_be_scribed`` to decide which timber is scribed onto the
    other.

    ``relief`` is required here -- callers are responsible for skipping this
    call entirely when relief isn't configured (e.g. it's None).
    """
    butt_timber = arrangement.butt_timber
    receiving_timber = arrangement.receiving_timber

    if relief.timber_to_be_scribed == ArrangementNames.butt_timber:
        scribed_timber, cut_timber_for_relief = butt_timber, receiving_timber
        scribed_cutting, cut_cutting = butt_cut, receiving_cut
    elif relief.timber_to_be_scribed == ArrangementNames.receiving_timber:
        scribed_timber, cut_timber_for_relief = receiving_timber, butt_timber
        scribed_cutting, cut_cutting = receiving_cut, butt_cut
    else:
        raise AssertionError(
            f"Unsupported butt-joint relief target: {relief.timber_to_be_scribed}"
        )

    updated_cut_cutting, updated_scribed_cutting = chop_scribe_relief_and_apply(
        timber_to_be_scribed=scribed_timber,
        timber_to_be_scribed_cutting=scribed_cutting,
        timber_to_be_cut=cut_timber_for_relief,
        timber_to_be_cut_cutting=cut_cutting,
    )

    if relief.timber_to_be_scribed == ArrangementNames.butt_timber:
        return updated_scribed_cutting, updated_cut_cutting
    else:
        return updated_cut_cutting, updated_scribed_cutting
