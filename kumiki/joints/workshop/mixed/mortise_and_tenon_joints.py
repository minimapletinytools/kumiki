"""
Kumiki - Mortise and tenon joint construction functions
Contains mortise-and-tenon joint implementations: plain (generic/plane-aligned/face-aligned/round),
corner, and tusked variants.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from math import isfinite
from enum import Enum
from typing import List, Optional, Sequence, Union

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.csg.cutcsg import (
    CutCSG,
    CutCSGLabel,
    RectangularPrism,
    HalfSpace,
    Difference,
    Intersection,
    SolidUnion,
    adopt_csg,
    PrismFace,
    Cylinder,
    CylinderAxisFeature,
    Datum,
    PlaneFeature,
    FeatureOverride,
    FeatureProperties,
    measured_against,
    prism_face_key,
    HALF_SPACE_PLANE,
    shoulder_override,
)
from kumiki.measuring import (
    locate_top_center_position,
    locate_bottom_center_position,
    mark_distance_from_end_along_centerline,
    mark_plane_from_edge_in_direction,
    get_center_point_on_face_global,
    Space,
)
from ..shavings import *
from ..shavings.relief import (
    warn_if_arrangement_timbers_imperfect,
    chop_shoulder_notch_on_timber_face,
    ShoulderReliefCSGGeometry,
    chop_shoulder_notch_aligned_with_timber,
    chop_butt_joint_shoulder_notch_relief_4sided,
    chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided,
    does_shoulder_plane_need_notching,
    ButtJointScribeReliefConfig,
    ButtJointNotchReliefConfig,
    NotchFrom,
    chop_scribe_relief_and_apply_for_butt_joint_arrangement,
    _apply_scribe_relief_if_configured,
)
from ..shavings.build_a_butt import (
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
    locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face,
    resolve_parallel_shoulder_face,
    PegPositionResult,
    PegPositionSpace,
    SimplePegParameters,
    compute_peg_positions,
    locate_tenon_origin_on_shoulder,
    compute_butt_joint_shoulder,
    tusk_tenon_geometry,
    TuskTenonGeometryResult,
    convert_mortise_shoulder_inset_to_centerline_distance,
)

TENON_CUT_LABEL = CutCSGLabel("tenon_cut")
MORTISE_CUT_LABEL = CutCSGLabel("mortise_cut")


def _union_into_cut(existing: CutCSG, additions: List[CutCSG], label: CutCSGLabel) -> SolidUnion:
    if isinstance(existing, SolidUnion) and existing.label == label:
        return SolidUnion(children=list(existing.children) + list(additions), label=label)
    return SolidUnion(children=[existing] + list(additions), label=label)


class WedgeOrientation(Enum):
    SPREAD_X = "spread_x"
    SPREAD_Y = "spread_y"


@dataclass(frozen=True)
class WedgeParameters:
    """Place one wedge or a symmetric pair from the tenon tip toward its shoulder.

    The default spread axis is the tenon's X or Y axis closest to the receiving
    timber's length. Spreading along its grain reduces the risk of splitting it.
    wedge_position is signed from the tenon center along the spread axis.
    paired_edge_inset places two kerf centerlines that far inside opposite cheeks.
    A pair uses a common spread axis and requires wedge_position to be zero.
    wedge_angle is the included angle in radians. mortise_side_angle is the outward
    angle per spread wall from shoulder to mortise bottom. tenon_kerf_size is the
    saw cut width. Zero leaves only the layout datums. wedge_length sets the kerf
    depth, capped at the tenon length available on the wedge centerline.
    wedge_extra_length sets how far the broad end projects past the trimmed tenon
    along its axis. If omitted, only excess wedge_length projects.
    """
    wedge_orientation: WedgeOrientation | None = None
    wedge_position: Numeric = 0
    wedge_length: Numeric | None = None
    wedge_angle: Numeric = degrees(5)
    mortise_side_angle: Numeric = 0
    tenon_kerf_size: Numeric = 0
    wedge_extra_length: Numeric | None = None
    paired_edge_inset: Numeric | None = None


@dataclass(frozen=True)
class _TenonWedgeLayout:
    accessory: Wedge
    kerf_global: RectangularPrism | None
    kerf_datums: tuple[PlaneFeature, PlaneFeature]


def _lay_out_tenon_wedge(params: WedgeParameters, shoulder_global: Transform, size: V2,
                        tenon_length: Numeric, mortise_depth: Numeric | None,
                        spread_global: V3, crop_planes: list[HalfSpace], inward_global: V3, suffix: str) -> _TenonWedgeLayout:
    """Lay out the wedge along the kerf centerline between the shoulder and the trimmed tip."""
    kerf = params.tenon_kerf_size
    if not isinstance(params.wedge_orientation, WedgeOrientation):
        raise ValueError("wedge_orientation must be SPREAD_X or SPREAD_Y")
    if not 0 < params.wedge_angle < pi or not 0 <= params.mortise_side_angle < pi / 2:
        raise ValueError("wedge_angle must be between 0 and pi and mortise_side_angle in [0, pi/2)")
    if not isfinite(kerf) or kerf < 0 or not isfinite(params.wedge_position):
        raise ValueError("tenon_kerf_size must be nonnegative and wedge_position and kerf size finite")
    extra = params.wedge_extra_length
    if extra is not None and (not isfinite(extra) or extra < 0):
        raise ValueError("wedge_extra_length must be finite and nonnegative")

    outward = shoulder_global.local_to_global_direction(create_v3(0, 0, 1))
    offset = params.wedge_position * spread_global
    origin = shoulder_global.position + offset
    tip = tenon_length
    start = 0
    if crop_planes:
        start = -safe_dot_product(inward_global, offset) / safe_dot_product(inward_global, outward)
        for plane in crop_planes:
            advance = safe_dot_product(plane.normal, outward)
            if advance > 0:
                tip = min(tip, (plane.offset - safe_dot_product(plane.normal, origin)) / advance)
    available = tip - start
    nominal_length = available if params.wedge_length is None else params.wedge_length
    if not (isfinite(nominal_length) and isfinite(available) and min(nominal_length, available) > 0):
        raise ValueError("The wedge and tenon at its position must have positive finite length")
    index = 0 if params.wedge_orientation is WedgeOrientation.SPREAD_X else 1
    depth = min(nominal_length, available)
    root = tip - depth
    projection = nominal_length - depth if extra is None else extra
    length = depth + projection
    head = tip + projection
    if mortise_depth is not None and (not isfinite(mortise_depth) or
                                      (not crop_planes and not safe_compare(head, mortise_depth, Comparison.LE))):
        raise ValueError("mortise_depth must accommodate the tenon and seated wedge")
    taper = tan(params.wedge_angle / 2)
    if abs(params.wedge_position) + max(kerf / 2, depth * taper) >= size[index] / 2:
        raise ValueError("The kerf and inserted wedge must fit between the tenon cheeks")

    across = size[1 - index]
    wedge = Wedge(
        transform=Transform(origin + outward * head, Orientation.from_z_and_x(-outward, spread_global)),
        length=length, base_width=2 * length * taper, tip_width=0, height=across,
        assembly_freedom=AssemblyFreedom.translation(outward, depth) if mortise_depth is None else None,
        assembly_ordering=Ordering(0, -1) if mortise_depth is None else Ordering(),
    )
    slot = RectangularPrism(
        size=create_v2(kerf, across), transform=Transform(origin, Orientation.from_z_and_x(outward, spread_global)),
        start_distance=root, end_distance=tenon_length, label=CutCSGLabel(f"tenon_kerf{suffix}"),
    ) if kerf > 0 else None
    direction = shoulder_global.global_to_local_direction(spread_global)
    return _TenonWedgeLayout(wedge, slot, (
        PlaneFeature(f"kerf_center{suffix}", normal=(direction[0], direction[1], direction[2]), offset=params.wedge_position),
        PlaneFeature(f"kerf_root{suffix}", normal=(0, 0, 1), offset=root),
    ))


def _flared_mortise(side_angle: Numeric, spread: int, size: V2, shoulder_global: Transform, inward_global: V3,
                   start: Numeric, depth: Numeric | None) -> CutCSG:
    """Intersect the four mortise walls with the entry and optional blind bottom.

    Rotate each spread wall about its intersection with the shoulder plane.
    An open-ended cut continues through the receiving timber.
    """
    inward = shoulder_global.global_to_local_direction(inward_global)
    along = create_v3(0, 0, 1)

    def plane(normal: V3, point: V3, name: str, opposite: str | None = None) -> HalfSpace:
        normal_global = shoulder_global.local_to_global_direction(normal)
        props = measured_against(FeatureProperties(), opposite) if opposite else FeatureProperties()
        return HalfSpace(normal=normal_global, offset=safe_dot_product(normal_global, shoulder_global.local_to_global(point)),
                         feature_overrides=[FeatureOverride(HALF_SPACE_PLANE, name, props)])

    cut: CutCSG = plane(along, start * along, "mortise_entry")
    if depth is not None:
        cut = Intersection(cut, plane(-along, depth * along, "mortise_bottom"))
    for index, (axis, positive, negative) in enumerate((
        (create_v3(1, 0, 0), "mortise_right", "mortise_left"),
        (create_v3(0, 1, 0), "mortise_front", "mortise_back"),
    )):
        for sign, name, opposite in ((1, positive, negative), (-1, negative, positive)):
            normal = -sign * axis
            point = sign * size[index] / 2 * axis
            if index == spread:
                point = point - along * (safe_dot_product(inward, point) / inward[2])
                into_wall = safe_normalize_vector(inward - axis * safe_dot_product(inward, axis))
                normal = normal * cos(side_angle) + into_wall * sin(side_angle)
            cut = Intersection(cut, plane(normal, point, name, opposite))
    return replace(cut, label=CutCSGLabel("mortise_hole"))


class InsetShoulderReliefStyle(Enum):
    Rough = 0
    PerfectOnly = 1
    NoRelief = 2


#: A tenon face is named and measurable, and meets exactly one other feature: the
#: shoulder plane, at the tenon's base. It does not meet the mating timber's body
#: (an edge nobody asked for), and its own arrises are the prism's defaults, so a
#: derived pair of cheeks would name those twice.
_TENON_FACE = FeatureProperties(group=FeatureGroup.TENON)


def _mortise_walls() -> List[FeatureOverride]:
    """The mortise hole's walls, each measured against the opposite one, and its bottom."""
    wall = FeatureProperties()
    return [
        FeatureOverride(prism_face_key(PrismFace.RIGHT), "mortise_right", measured_against(wall, "mortise_left")),
        FeatureOverride(prism_face_key(PrismFace.LEFT), "mortise_left", measured_against(wall, "mortise_right")),
        FeatureOverride(prism_face_key(PrismFace.FRONT), "mortise_front", measured_against(wall, "mortise_back")),
        FeatureOverride(prism_face_key(PrismFace.BACK), "mortise_back", measured_against(wall, "mortise_front")),
        FeatureOverride(prism_face_key(PrismFace.TOP), "mortise_bottom"),
    ]


def _plane_aligned_shoulder_notch(
    arrangement: ButtJointTimberArrangement, notch_from: NotchFrom, shoulder_distance: Numeric,
) -> ShoulderReliefCSGGeometry | None:
    """Build the two-sided notch from the inset shoulder or the receiver's entry face."""
    if notch_from is NotchFrom.Face:
        direction = arrangement.butt_timber.get_face_direction_global(arrangement.butt_timber_end)
        face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(-direction).to.face()
        shoulder_distance = convert_mortise_shoulder_inset_to_centerline_distance(
            scalar(0), face, arrangement.receiving_timber)
    return chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(arrangement, shoulder_distance)


def _inset_shoulder_relief(
    arrangement: ButtJointTimberArrangement,
    shoulder_plane: Plane,
    shoulder_half_space_global: HalfSpace,
    mortise_shoulder_distance_from_centerline_or_centerplane: Numeric,
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool],
    relief: None | ButtJointScribeReliefConfig | ButtJointNotchReliefConfig,
    inset_shoulder_relief_style: InsetShoulderReliefStyle,
) -> ShoulderReliefCSGGeometry | None:
    """Build the housing and matching shank relief at the shared shoulder."""
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end
    shoulder_relief_bound_global = replace(shoulder_half_space_global, feature_overrides=[])
    if isinstance(relief, ButtJointNotchReliefConfig):
        assert relief.notch_from == NotchFrom.Shoulder, (
            "cut_mortise_and_tenon_joint only supports "
            "ButtJointNotchReliefConfig(notch_from=NotchFrom.Shoulder)"
        )
        if inset_shoulder_relief_style is not InsetShoulderReliefStyle.NoRelief:
            warnings.warn(
                "inset_shoulder_relief_style is ignored when relief is a "
                "ButtJointNotchReliefConfig -- the 4-sided notch is itself the "
                "inset-shoulder relief. Pass InsetShoulderReliefStyle.NoRelief.",
                stacklevel=2,
            )
        return chop_butt_joint_shoulder_notch_relief_4sided(
            arrangement,
            mortise_shoulder_distance_from_centerline_or_centerplane,
            shoulder_plane=shoulder_plane,
        )
    elif inset_shoulder_relief_style is InsetShoulderReliefStyle.NoRelief:
        return None
    elif does_shoulder_plane_need_notching(
        arrangement,
        mortise_shoulder_distance_from_centerline_or_centerplane,
        check_against_rough_size=False,
        set_mortise_shoulder_parallel_to_face=set_mortise_shoulder_parallel_to_face,
    ):
        extend_bot = tenon_end == TimberEnd.BOTTOM
        extend_top = tenon_end == TimberEnd.TOP
        fit_rough_shank = inset_shoulder_relief_style is InsetShoulderReliefStyle.Rough
        tenon_timber_scribe_csg_local = (
            tenon_timber.get_extended_actual_csg_local(extend_bot=extend_bot, extend_top=extend_top)
            if fit_rough_shank
            else tenon_timber.get_extended_perfect_csg_local(extend_bot=extend_bot, extend_top=extend_top)
        )
        tenon_timber_csg_global = adopt_csg(
            tenon_timber.transform,
            None,
            tenon_timber_scribe_csg_local,
        )
        mortise_ptw_global = adopt_csg(
            mortise_timber.transform,
            None,
            RectangularPrism(
                size=mortise_timber.size,
                start_distance=scalar(0),
                end_distance=mortise_timber.length,
                label=CutCSGLabel("mortise_ptw_bounds"),
            ),
        )
        scribe_csg_global = Intersection(
            left=Difference(
                base=tenon_timber_csg_global,
                subtract=[shoulder_half_space_global],
            ),
            right=mortise_ptw_global,
            label=CutCSGLabel("shoulder_scribe_relief"),
        )
        scribe_csg_mortise_local = adopt_csg(None, mortise_timber.transform, scribe_csg_global)

        if fit_rough_shank or tenon_timber.is_perfect_timber():
            tenon_relief_local = None
        else:
            tenon_imperfect_global = adopt_csg(
                tenon_timber.transform,
                None,
                Difference(
                    # The timber's own rough body without its labels: that body is already
                    # in this timber's tree, and one surface declared twice puts two
                    # features of one name on one plane (see the shoulder bound above).
                    base=tenon_timber.get_extended_actual_csg_local(
                        extend_bot=extend_bot, extend_top=extend_top, with_feature_labels=False),
                    subtract=[tenon_timber.get_extended_perfect_csg_local(extend_bot=extend_bot, extend_top=extend_top)],
                    label=CutCSGLabel("rough_fringe"),
                ),
            )
            tenon_relief_local = adopt_csg(
                None,
                tenon_timber.transform,
                Intersection(
                    left=Difference(
                        base=tenon_imperfect_global,
                        subtract=[shoulder_relief_bound_global],
                    ),
                    right=mortise_ptw_global,
                    label=CutCSGLabel("shoulder_rough_relief"),
                ),
            )

        return ShoulderReliefCSGGeometry(
            receiving_timber_notch_negative_CSG=scribe_csg_mortise_local,
            butting_timber_relief_negative_CSG=tenon_relief_local,
        )
    return None


def cut_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool] = False,
    mortise_shoulder_distance_from_centerline_or_centerplane: Numeric = scalar(0),
    tenon_position: Optional[V2] = None,
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,
    bore_mortise_perpendicular_to_face: bool = False,
    use_round_tenon: bool = False,
    relief: Union[None, ButtJointScribeReliefConfig, ButtJointNotchReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
    inset_shoulder_relief_style: InsetShoulderReliefStyle = InsetShoulderReliefStyle.Rough,
) -> Joint:
    """Cut a mortise and tenon with optional pegs and end-driven wedges.

    wedge_parameters sizes the wedge and saw kerf on a rectangular tenon.
    Flared walls run from the shoulder to mortise_depth, or through the receiver
    when depth is omitted.

    The basic pattern uses 4 × 5 in stock. The tenon is dimensioned along its local axes.
    The X-ray view shows the floor through the intact receiving timber.

    [![Tenon length and cross section, with an X-ray view showing mortise depth](../../../assets/joint-drawings/mortise-and-tenon.svg)](../../../assets/joint-drawings/mortise-and-tenon.svg)
    """
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    if tenon_position is None:
        tenon_position = Matrix([scalar(0), scalar(0)])

    tenon_min_x = tenon_position[0] - tenon_size[0] / scalar(2)
    tenon_max_x = tenon_position[0] + tenon_size[0] / scalar(2)
    timber_half_width_x = tenon_timber.size[0] / scalar(2)

    assert safe_compare(tenon_min_x, -timber_half_width_x, Comparison.GE), (
        f"Tenon X boundary extends outside of the timber: "
        f"minimum tenon X ({tenon_min_x}) is less than timber boundary ({-timber_half_width_x})"
    )
    assert safe_compare(tenon_max_x, timber_half_width_x, Comparison.LE), (
        f"Tenon X boundary extends outside of the timber: "
        f"maximum tenon X ({tenon_max_x}) exceeds timber boundary ({timber_half_width_x})"
    )

    tenon_min_y = tenon_position[1] - tenon_size[1] / scalar(2)
    tenon_max_y = tenon_position[1] + tenon_size[1] / scalar(2)
    timber_half_width_y = tenon_timber.size[1] / scalar(2)

    assert safe_compare(tenon_min_y, -timber_half_width_y, Comparison.GE), (
        f"Tenon Y boundary extends outside of the timber: "
        f"minimum tenon Y ({tenon_min_y}) is less than timber boundary ({-timber_half_width_y})"
    )
    assert safe_compare(tenon_max_y, timber_half_width_y, Comparison.LE), (
        f"Tenon Y boundary extends outside of the timber: "
        f"maximum tenon Y ({tenon_max_y}) exceeds timber boundary ({timber_half_width_y})"
    )

    if use_round_tenon:
        arrangement_check(
            None if tenon_size[0] == tenon_size[1] else "Round tenon requires tenon_size[0] == tenon_size[1]"
        )
        arrangement_check(
            None if peg_parameters is None else "Round tenon does not support pegs (peg_parameters must be None)"
        )

    if bore_mortise_perpendicular_to_face:
        arrangement_check(
            None if not use_round_tenon
            else "bore_mortise_perpendicular_to_face cannot be True for round tenons"
        )
        arrangement_check(
            None if mortise_depth is not None
            else "mortise_depth must be provided (not None) when bore_mortise_perpendicular_to_face is True"
        )
        arrangement_check(arrangement.check_plane_aligned(), arrangement)

    if set_mortise_shoulder_parallel_to_face:
        resolved_face = resolve_parallel_shoulder_face(arrangement, set_mortise_shoulder_parallel_to_face)
        shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face(
            arrangement,
            mortise_shoulder_distance_from_centerline_or_centerplane,
            resolved_face,
        )
    else:
        shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement,
            mortise_shoulder_distance_from_centerline_or_centerplane,
        )
    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    marking_origin_global = locate_tenon_origin_on_shoulder(shoulder_plane, tenon_timber, tenon_end, tenon_position)

    tenon_orientation = compute_timber_orientation(
        safe_normalize_vector(tenon_end_direction), tenon_timber.get_width_direction_global()
    )
    tenon_base_transform = Transform(position=marking_origin_global, orientation=tenon_orientation)
    marking_space: Space = Space(transform=tenon_base_transform)

    mortise_face_normal = shoulder_plane.normal
    # The tenon's angle is measured from the face's normal, so its cosine is the sine of the angle to
    # the face itself: how steeply the tenon enters. A tenon of width w covers w / sin_from_face of the face.
    cos_from_normal = safe_dot_product(
        safe_normalize_vector(mortise_face_normal), safe_normalize_vector(tenon_end_direction)
    )
    sin_from_face = Abs(cos_from_normal)
    arrangement_check(
        None if not safe_zero_test(sin_from_face)
        else "The tenon runs along the mortise face instead of into it"
    )

    sin_from_normal_sq = scalar(1) - cos_from_normal * cos_from_normal
    is_square = safe_zero_test(sin_from_normal_sq)
    sin_from_normal = sqrt(Abs(sin_from_normal_sq))
    # How far the slanted shoulder dips behind the tenon's base: (size / 2) * tan(angle from the
    # normal), doubled for margin. The shoulder trims whatever reaches further.
    back_extension = (
        scalar(0) if is_square
        else max(tenon_size[0], tenon_size[1]) * sin_from_normal / sin_from_face
    )

    mortise_transform = tenon_base_transform
    mortise_size = tenon_size
    if wedge_parameters is not None and wedge_parameters.wedge_orientation is None:
        face = tenon_timber.get_closest_oriented_long_face_from_global_direction(
            mortise_timber.get_length_direction_global())
        axis = tenon_timber.get_size_index_in_long_face_normal_axis(face)
        orientation = WedgeOrientation.SPREAD_X if axis == 0 else WedgeOrientation.SPREAD_Y
        wedge_parameters = replace(wedge_parameters, wedge_orientation=orientation)
    spread_index = int(wedge_parameters is not None and wedge_parameters.wedge_orientation is WedgeOrientation.SPREAD_Y)
    tenon_crop_planes: list[HalfSpace] = []
    do_lengthwise_cropping = bore_mortise_perpendicular_to_face and not is_square
    if do_lengthwise_cropping:
        assert mortise_depth is not None
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        mortise_face_direction = mortise_timber.get_face_direction_global(mortise_face)

        mortise_oblique_end = mortise_timber.get_closest_oriented_end_face_from_global_direction(tenon_end_direction)
        joint_angle_axis_face = tenon_timber.get_closest_oriented_long_face_from_global_direction(mortise_timber.get_face_direction_global(mortise_oblique_end))
        joint_angle_axis_index = tenon_timber.get_size_index_in_long_face_normal_axis(joint_angle_axis_face)

        mortise_hole_length_oblique_direction = mortise_timber.get_face_direction_global(mortise_oblique_end)
        end_crop_distance = tenon_size[joint_angle_axis_index] / sin_from_face / scalar(2)

        mortise_hole_end_crop_global = HalfSpace(
            normal=mortise_hole_length_oblique_direction,
            offset=end_crop_distance + safe_dot_product(mortise_hole_length_oblique_direction, marking_origin_global),
            label=CutCSGLabel("tenon_crop_to_mortise_length"),
        )

        mortise_depth_crop_global = HalfSpace(
            normal=-mortise_face_direction,
            offset=mortise_depth - safe_dot_product(mortise_face_direction, get_center_point_on_face_global(mortise_face, mortise_timber)),
            label=CutCSGLabel("tenon_crop_to_mortise_depth"),
        )

        tenon_crop_planes = [mortise_hole_end_crop_global, mortise_depth_crop_global]
        if wedge_parameters is not None and wedge_parameters.paired_edge_inset is not None and wedge_parameters.wedge_extra_length:
            # Leave axial clearance to the pocket floor and the approached end wall.
            projection = wedge_parameters.wedge_extra_length
            if spread_index == joint_angle_axis_index:
                angle = wedge_parameters.mortise_side_angle
                wall_normal = cos(angle) * mortise_hole_length_oblique_direction + sin(angle) * mortise_face_direction
                tenon_crop_planes[0] = replace(mortise_hole_end_crop_global, normal=wall_normal,
                                               offset=end_crop_distance * cos(angle) + wall_normal.dot(marking_origin_global))
            tenon_crop_planes = [replace(plane, offset=plane.offset - projection * max(0, plane.normal.dot(tenon_end_direction)))
                                 for plane in tenon_crop_planes]

        mortise_transform = Transform(marking_origin_global, Orientation.from_z_and_y(
            z_direction=-mortise_face_normal, y_direction=mortise_hole_length_oblique_direction))
        mortise_size = create_v2(tenon_size[1 - joint_angle_axis_index],
                                 tenon_size[joint_angle_axis_index] / sin_from_face)
        # Bore Y lies along the receiver, the axis stretched by the oblique entrance.
        spread_index = 1 if spread_index == joint_angle_axis_index else 0

    tenon_tip_name = "tenon_top" if tenon_end == TimberEnd.TOP else "tenon_bot"

    wedge_layouts: dict[str, _TenonWedgeLayout] = {}
    if wedge_parameters is not None:
        if use_round_tenon:
            raise ValueError("Wedging requires a rectangular tenon")
        spread_global = (tenon_timber.get_width_direction_global()
                         if wedge_parameters.wedge_orientation is WedgeOrientation.SPREAD_X
                         else tenon_timber.get_height_direction_global())
        inset = wedge_parameters.paired_edge_inset
        positions = {"": wedge_parameters.wedge_position}
        if inset is not None:
            half_width = tenon_size[0 if wedge_parameters.wedge_orientation is WedgeOrientation.SPREAD_X else 1] / 2
            if wedge_parameters.wedge_position != 0 or not 0 < inset < half_width:
                raise ValueError("paired_edge_inset must be inside each cheek and requires wedge_position=0")
            positions = {"_0": inset - half_width, "_1": half_width - inset}
        for suffix, position in positions.items():
            wedge_layouts[suffix] = _lay_out_tenon_wedge(
                replace(wedge_parameters, wedge_position=position), tenon_base_transform, tenon_size,
                tenon_length, mortise_depth, spread_global, tenon_crop_planes, -shoulder_plane.normal, suffix)
        if inset is not None:
            occupied = sum(max(layout.accessory.base_width, wedge_parameters.tenon_kerf_size) / 2
                           for layout in wedge_layouts.values())
            if positions["_1"] - positions["_0"] <= occupied:
                raise ValueError("The paired wedges and kerfs must be separated by wood")

    if use_round_tenon:
        tenon_radius = tenon_size[0] / scalar(2)
        axis_direction_global = safe_normalize_vector(tenon_end_direction)
        tenon_prism_global = Cylinder(
            axis_direction=axis_direction_global,
            radius=tenon_radius,
            position=marking_space.transform.position,
            start_distance=-back_extension,
            end_distance=tenon_length,
            label=CutCSGLabel("tenon"),
        )
    else:
        tenon_prism_global = RectangularPrism(
            size=tenon_size,
            transform=marking_space.transform,
            start_distance=-back_extension,
            end_distance=tenon_length,
            extra_features=tuple(datum for layout in wedge_layouts.values() for datum in layout.kerf_datums),
            feature_overrides=[
                # Cheek to cheek is the tenon's thickness; tip to shoulder its length, and the tip
                # is measured from nothing else.
                FeatureOverride(prism_face_key(PrismFace.RIGHT), "tenon_right", measured_against(_TENON_FACE, "tenon_left")),
                FeatureOverride(prism_face_key(PrismFace.LEFT), "tenon_left", measured_against(_TENON_FACE, "tenon_right")),
                FeatureOverride(prism_face_key(PrismFace.FRONT), "tenon_front", measured_against(_TENON_FACE, "tenon_back")),
                FeatureOverride(prism_face_key(PrismFace.BACK), "tenon_back", measured_against(_TENON_FACE, "tenon_front")),
                FeatureOverride(prism_face_key(PrismFace.TOP), tenon_tip_name,
                                measured_against(_TENON_FACE, "shoulder", datum=Datum.AVOID)),
            ],
            label=CutCSGLabel("tenon"),
        )

    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
        feature_overrides=[shoulder_override(HALF_SPACE_PLANE, name="shoulder", group=FeatureGroup.SHOULDER_PLANE)],
        label=CutCSGLabel("shoulder"),
    )

    # The tenon-side relief below is bounded by the same plane, but with a copy that
    # carries no shoulder feature. Using the one above put a second "shoulder" on the
    # tenon timber -- the joint's own cutter plus the relief's -- and two features on
    # one plane derive the same edge twice, which is what _drop_duplicate_derived
    # trips over. The relief wants the plane, not the name. The scribe relief on the
    # receiving timber keeps the named one, since it is that timber's only shoulder.
    shoulder_relief_bound_global = replace(shoulder_half_space_global, feature_overrides=[])

    tenon_prism_cropped = (
        tenon_prism_global
        if not tenon_crop_planes
        else Difference(
            base=tenon_prism_global,
            subtract=list(tenon_crop_planes),
            label=CutCSGLabel("tenon_cropped"),
        )
    )

    tenon_prism_local = adopt_csg(None, tenon_timber.transform, tenon_prism_cropped)
    shoulder_half_space_local = adopt_csg(None, tenon_timber.transform, shoulder_half_space_global)

    mortise_hole_prism_global: CutCSG
    if use_round_tenon:
        mortise_hole_prism_global = Cylinder(
            axis_direction=tenon_end_direction, radius=tenon_size[0] / 2, position=marking_origin_global,
            start_distance=-back_extension, end_distance=mortise_depth, label=CutCSGLabel("mortise_hole"),
        )
    elif wedge_parameters is not None and wedge_parameters.mortise_side_angle > 0:
        mortise_hole_prism_global = _flared_mortise(
            wedge_parameters.mortise_side_angle, spread_index, mortise_size, mortise_transform,
            -shoulder_plane.normal, -back_extension, mortise_depth)
    else:
        mortise_hole_prism_global = RectangularPrism(
            size=mortise_size, transform=mortise_transform, start_distance=-back_extension, end_distance=mortise_depth,
            feature_overrides=_mortise_walls(), label=CutCSGLabel("mortise_hole"),
        )

    shoulder_notch_relief_geom = _inset_shoulder_relief(
        arrangement, shoulder_plane, shoulder_half_space_global,
        mortise_shoulder_distance_from_centerline_or_centerplane, set_mortise_shoulder_parallel_to_face,
        relief, inset_shoulder_relief_style,
    )

    tenon_cut_csg: CutCSG = Difference(
        base=shoulder_half_space_local,
        subtract=[tenon_prism_local],
        label=CutCSGLabel("tenon_waste"),
    )
    if shoulder_notch_relief_geom is not None and shoulder_notch_relief_geom.butting_timber_relief_negative_CSG is not None:
        tenon_cut_csg = _union_into_cut(
            tenon_cut_csg,
            [shoulder_notch_relief_geom.butting_timber_relief_negative_CSG],
            TENON_CUT_LABEL,
        )

    slots: list[CutCSG] = []
    for layout in wedge_layouts.values():
        if layout.kerf_global is not None:
            slot: CutCSG = layout.kerf_global
            if not is_square:
                slot = Intersection(slot, shoulder_relief_bound_global)
            slots.append(adopt_csg(None, tenon_timber.transform, slot))
    if slots:
        tenon_cut_csg = _union_into_cut(tenon_cut_csg, slots, TENON_CUT_LABEL)

    mortise_hole_prism_local = adopt_csg(None, mortise_timber.transform, mortise_hole_prism_global)

    if shoulder_notch_relief_geom is not None:
        mortise_negative_csg = _union_into_cut(
            mortise_hole_prism_local,
            [shoulder_notch_relief_geom.receiving_timber_notch_negative_CSG],
            MORTISE_CUT_LABEL,
        )
    else:
        mortise_negative_csg = mortise_hole_prism_local

    mortise_cut = Cutting(
        timber=mortise_timber,
        negative_csg=mortise_negative_csg,
        label=CutCSGLabel("mortise_and_tenon"),
    )

    tenon_length_direction_global = tenon_timber.get_face_direction_global(tenon_end)
    tip_position_global = marking_space.transform.position + tenon_length_direction_global * max(tenon_length, max(tenon_size[0], tenon_size[1])/cos_from_normal)
    tip_position_local = tenon_timber.transform.global_to_local(tip_position_global)
    tip_z_local = tip_position_local[2]

    tenon_cut = Cutting(
        timber=tenon_timber,
        maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.BOTTOM else None,
        negative_csg=tenon_cut_csg,
        label=CutCSGLabel("mortise_and_tenon"),
    )

    joint_accessories: dict[str, Accessory] = {}
    for suffix, layout in wedge_layouts.items():
        wedge = layout.accessory
        if do_lengthwise_cropping:
            if not mortise_hole_prism_global.contains_point(wedge.transform.position):
                raise ValueError("The seated wedge head extends beyond the face-bored mortise")
            # Bevel the wedge edges to the bore walls and floor, keeping its drive axis along the tenon.
            pocket = Intersection(mortise_hole_prism_global, shoulder_relief_bound_global)
            bore_local = adopt_csg(None, wedge.transform, pocket)
            joint_accessories[f"wedge{suffix}"] = CSGAccessory(
                ticket=wedge.ticket, transform=wedge.transform,
                positive_csg=Intersection(wedge.get_csg_local(), bore_local))
        else:
            joint_accessories[f"wedge{suffix}"] = wedge
    if peg_parameters is not None:
        peg_results = compute_peg_positions(
            arrangement=arrangement,
            shoulder_plane=shoulder_plane,
            peg_parameters=peg_parameters,
            tenon_position=tenon_position,
        )

        peg_size = peg_parameters.size
        peg_holes_in_tenon_local = []
        peg_holes_in_mortise_local = []

        def _build_peg_hole_global(center_global: V3, orientation_global: Orientation, depth: Numeric, label: str) -> CutCSG:
            if peg_parameters.shape == PegShape.ROUND:
                axis_direction_global = orientation_global.matrix * create_v3(scalar(0), scalar(0), scalar(1))
                return Cylinder(
                    axis_direction=axis_direction_global,
                    radius=peg_size / scalar(2),
                    position=center_global,
                    start_distance=scalar(0),
                    end_distance=depth,
                    # The line the drill follows. Named because it is what a peg
                    # hole is dimensioned from -- a bore is located by its centre,
                    # not by a tangent to its wall -- and the barrel declines to
                    # locate, being curved, so without this the hole has nothing
                    # measurable on it at all.
                    extra_features=[CylinderAxisFeature("peg_hole_axis")],
                    label=CutCSGLabel(label),
                )
            return RectangularPrism(
                size=Matrix([peg_size, peg_size]),
                transform=Transform(
                    position=center_global,
                    orientation=orientation_global,
                ),
                start_distance=scalar(0),
                end_distance=depth,
                label=CutCSGLabel(label),
            )

        for peg_idx, peg_result in enumerate(peg_results):
            peg_hole_tenon_global = _build_peg_hole_global(
                peg_result.tenon_face_position_with_offset_global,
                peg_result.orientation_global,
                peg_result.peg_depth,
                f"peg_hole_{peg_idx}",
            )
            peg_holes_in_tenon_local.append(adopt_csg(None, tenon_timber.transform, peg_hole_tenon_global))

            peg_hole_mortise_global = _build_peg_hole_global(
                peg_result.mortise_entry_position_global,
                peg_result.orientation_global,
                peg_result.peg_depth,
                f"peg_hole_{peg_idx}",
            )
            peg_holes_in_mortise_local.append(adopt_csg(None, mortise_timber.transform, peg_hole_mortise_global))

            peg_drill_direction_global = peg_result.orientation_global.matrix * create_v3(scalar(0), scalar(0), scalar(1))
            peg_accessory = Peg(
                transform=Transform(
                    position=peg_result.mortise_entry_position_global,
                    orientation=peg_result.orientation_global,
                ),
                size=peg_size,
                shape=peg_parameters.shape,
                forward_length=peg_result.peg_depth,
                stickout_length=peg_result.stickout_length,
                assembly_freedom=AssemblyFreedom.translation(
                    -peg_drill_direction_global,
                    freed_after=peg_result.peg_depth + peg_result.stickout_length,
                ),
                assembly_ordering=Ordering(0, -1),
            )
            joint_accessories[f"peg_{peg_idx}"] = peg_accessory

        if peg_holes_in_tenon_local:
            tenon_cut_with_pegs_csg = _union_into_cut(
                tenon_cut_csg, peg_holes_in_tenon_local, TENON_CUT_LABEL)
            tenon_cut = Cutting(
                timber=tenon_timber,
                maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.TOP else None,
                maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.BOTTOM else None,
                negative_csg=tenon_cut_with_pegs_csg,
                label=CutCSGLabel("mortise_and_tenon"),
            )
        if peg_holes_in_mortise_local:
            mortise_cut_with_pegs_csg = _union_into_cut(
                mortise_negative_csg, peg_holes_in_mortise_local, MORTISE_CUT_LABEL)
            mortise_cut = Cutting(
                timber=mortise_timber,
                negative_csg=mortise_cut_with_pegs_csg,
                label=CutCSGLabel("mortise_and_tenon"),
            )

    tenon_cut_no_relief, mortise_cut_no_relief = tenon_cut, mortise_cut
    tenon_cut, mortise_cut = _apply_scribe_relief_if_configured(
        relief=relief if isinstance(relief, ButtJointScribeReliefConfig) else None,
        butt_cut=tenon_cut_no_relief,
        receiving_cut=mortise_cut_no_relief,
    )

    tenon_freedom = AssemblyFreedom.translation(-tenon_length_direction_global, freed_after=tenon_length)
    mortise_freedom = AssemblyFreedom.translation(tenon_length_direction_global, freed_after=tenon_length)

    if bore_mortise_perpendicular_to_face:
        assert mortise_depth is not None
        tenon_freedom = AssemblyFreedom.combine(
            tenon_freedom,
            AssemblyFreedom.translation(-mortise_face_normal, freed_after=mortise_depth),
        )
        mortise_freedom = AssemblyFreedom.combine(
            mortise_freedom,
            AssemblyFreedom.translation(mortise_face_normal, freed_after=mortise_depth),
        )

    tenon_cut_timber = replace(
        tenon_cut,
        assembly_freedom=tenon_freedom,
        assembly_ordering=Ordering(0, 0),
    )
    mortise_cut_timber = replace(
        mortise_cut,
        assembly_freedom=mortise_freedom,
        assembly_ordering=Ordering(0, 0),
    )

    return Joint(
        cuttings={
            tenon_timber.ticket.path: tenon_cut_timber,
            mortise_timber.ticket.path: mortise_cut_timber,
        },
        ticket=JointTicket(joint_type="mortise_and_tenon"),
        jointAccessories=joint_accessories,
    )


def _same_direction(first: V3, second: V3) -> bool:
    """Compare unit directions, including their sign."""
    delta = first - second
    return safe_zero_test_sq(safe_dot_product(delta, delta))


def _common_withdrawal(cuttings: Sequence[Cutting]) -> AssemblyFreedom:
    """Keep withdrawal directions shared by every cut, through the farthest release distance."""
    freedoms = [cut.assembly_freedom for cut in cuttings]
    assert all(freedom is not None for freedom in freedoms)
    directions = [freedom.translations for freedom in freedoms if freedom is not None]
    translations = []
    for first in directions[0]:
        if any(_same_direction(first.direction, dof.direction) for dof in translations):
            continue
        distances = [[dof.freed_after for dof in group if _same_direction(first.direction, dof.direction)]
                     for group in directions]
        if all(distances):
            translations.append(replace(first, freed_after=max(max(group) for group in distances)))
    return AssemblyFreedom(translations=tuple(translations))


def _unrelieved_tenon_parts(joint: Joint) -> tuple[Cutting, Cutting, HalfSpace, CutCSG, list[CutCSG]]:
    """Return the tenon and mortise cuttings, local shoulder, retained tenon and independent tenon cuts."""
    assert joint.ticket.joint_type == "mortise_and_tenon" and len(joint.cuttings) == 2, (
        "Expected a single butt mortise and tenon joint"
    )
    tenon, mortise = joint.cuttings.values()
    if tenon.get_maybe_top_end_cut() is None and tenon.get_maybe_bottom_end_cut() is None:
        tenon, mortise = mortise, tenon
    assert (tenon.get_maybe_top_end_cut() is None) != (tenon.get_maybe_bottom_end_cut() is None), "Expected one tenon end"
    assert mortise.get_maybe_top_end_cut() is None and mortise.get_maybe_bottom_end_cut() is None, "Expected a butt joint"

    hole = mortise.negative_csg
    assert hole is not None
    bores = hole.children if isinstance(hole, SolidUnion) and hole.label == MORTISE_CUT_LABEL else [hole]
    relief_error = (
        "Expected one mortise hole and optional peg holes. Inputs that already have shoulder or scribe relief "
        "must be cut with relief=None and inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief"
    )
    mortises = [bore for bore in bores if not (bore.label.name or "").startswith("peg_hole_")]
    assert len(mortises) == 1 and mortises[0].label.name == "mortise_hole", relief_error
    cut = tenon.negative_csg
    assert cut is not None
    cuts = cut.children if isinstance(cut, SolidUnion) and cut.label == TENON_CUT_LABEL else [cut]
    wastes = [node for node in cuts if isinstance(node, Difference) and node.label.name == "tenon_waste"]
    assert len(wastes) == 1, "Expected one tenon on one shoulder"
    waste = wastes[0]
    assert isinstance(waste.base, HalfSpace) and len(waste.subtract) == 1, "Expected one tenon on one shoulder"
    independent_cuts = [node for node in cuts if node is not waste]
    for node in independent_cuts:
        # An oblique wedge kerf is clipped to the shoulder.
        tool = node.left if isinstance(node, Intersection) else node
        assert (tool.label.name or "").startswith(("peg_hole_", "tenon_kerf")), relief_error
    return tenon, mortise, waste.base, waste.subtract[0], independent_cuts


def merge_mortise_and_tenon_joints(
    joints: Sequence[Joint],
    *,
    relief: None | ButtJointScribeReliefConfig | ButtJointNotchReliefConfig = ButtJointScribeReliefConfig.butt_timber(),
    inset_shoulder_relief_style: InsetShoulderReliefStyle | None = None,
) -> Joint:
    """Merge tenons on one timber end that share a mortise timber and an oriented shoulder plane.

    Supply single joints without relief. To suppress both scribing and inset housing on
    the inputs, pass relief=None and inset_shoulder_relief_style=InsetShoulderReliefStyle.NoRelief.
    A plane-aligned notch flares on two sides. A general shoulder notch flares on four.
    A face-referenced notch retains the housing at the inset shoulder.
    The caller sets the spacing between mortises.
    """
    assert len(joints) >= 2, "Supply at least two mortise and tenon joints"
    tenon_cuts: list[Cutting] = []
    mortise_cuts: list[Cutting] = []
    shoulders: list[HalfSpace] = []
    tenons: list[CutCSG] = []
    remaining_cuts: list[CutCSG] = []
    for joint in joints:
        tenon_cut, mortise_cut, local_plane, solid, extra_cuts = _unrelieved_tenon_parts(joint)
        tenon_cuts.append(tenon_cut)
        mortise_cuts.append(mortise_cut)
        shoulders.append(local_plane)
        tenons.append(solid)
        remaining_cuts.extend(extra_cuts)

    assert len({id(solid) for solid in tenons}) == len(tenons), "A tenon was supplied more than once"
    tenon_timber, mortise_timber = tenon_cuts[0].timber, mortise_cuts[0].timber
    assert isinstance(tenon_timber, TimberLike) and isinstance(mortise_timber, TimberLike)
    assert all(cut.timber is mortise_timber for cut in mortise_cuts), "Expected the same mortise timber"
    top_end = tenon_cuts[0].get_maybe_top_end_cut() is not None
    assert all(cut.timber is tenon_timber and (cut.get_maybe_top_end_cut() is not None) == top_end
               for cut in tenon_cuts), "Expected all tenons on the same tenon timber end"
    shoulder_local = shoulders[0]
    assert all(_same_direction(other.normal, shoulder_local.normal) and safe_zero_test(other.offset - shoulder_local.offset)
               for other in shoulders[1:]), "Expected the same oriented shoulder plane"
    for cuts in (tenon_cuts, mortise_cuts):
        assert all(cut.assembly_ordering == cuts[0].assembly_ordering for cut in cuts), (
            "Cuttings on a shared timber must agree on assembly ordering"
        )

    arrangement = ButtJointTimberArrangement(tenon_timber, mortise_timber, TimberEnd.TOP if top_end else TimberEnd.BOTTOM)
    shoulder_global = adopt_csg(tenon_timber.transform, None, shoulder_local)
    assert isinstance(shoulder_global, HalfSpace)
    shoulder = Plane(normal=-shoulder_global.normal, point=shoulder_global.normal * shoulder_global.offset)
    shoulder_distance = mark_plane_from_edge_in_direction(shoulder, mortise_timber, TimberCenterline.CENTERLINE).distance
    kept_tenons = [replace(solid, label=CutCSGLabel(f"tenon_{i}")) for i, solid in enumerate(tenons)]
    shoulder_waste = Difference(shoulder_local, kept_tenons, label=CutCSGLabel("tenon_waste"))
    holes = [replace(cut.negative_csg, label=CutCSGLabel(f"mortise_{i}"))
             for i, cut in enumerate(mortise_cuts) if cut.negative_csg is not None]

    inset_style = inset_shoulder_relief_style or InsetShoulderReliefStyle.Rough
    notch = None
    if isinstance(relief, ButtJointNotchReliefConfig):
        located = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement, shoulder_distance)
        plane_aligned = (arrangement.check_plane_aligned() is None
                         and _same_direction(located.normal, shoulder.normal))
        from_face = relief.notch_from is NotchFrom.Face
        assert plane_aligned or not from_face, "A face-referenced notch requires a plane-aligned shoulder"
        if plane_aligned:
            notch = _plane_aligned_shoulder_notch(arrangement, relief.notch_from, shoulder_distance)
        else:
            notch = chop_butt_joint_shoulder_notch_relief_4sided(
                arrangement, shoulder_distance, shoulder_plane=shoulder)
        inset_style = InsetShoulderReliefStyle.PerfectOnly if from_face else InsetShoulderReliefStyle.NoRelief
        if inset_shoulder_relief_style is not None and inset_shoulder_relief_style is not inset_style:
            raise ValueError(f"A {relief.notch_from.name}-referenced notch requires inset housing style {inset_style.name}")

    shoulder_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(shoulder.normal)
    housing = _inset_shoulder_relief(arrangement, shoulder, shoulder_global, shoulder_distance,
                                     shoulder_face, None, inset_style)
    for geometry in (housing, notch):
        if geometry is not None:
            holes.append(geometry.receiving_timber_notch_negative_CSG)
            if geometry.butting_timber_relief_negative_CSG is not None:
                remaining_cuts.append(geometry.butting_timber_relief_negative_CSG)

    top_ends = [cut.maybe_top_end_cut_distance_from_bottom for cut in tenon_cuts
                if cut.maybe_top_end_cut_distance_from_bottom is not None]
    bottom_ends = [cut.maybe_bottom_end_cut_distance_from_bottom for cut in tenon_cuts
                   if cut.maybe_bottom_end_cut_distance_from_bottom is not None]
    tenon = replace(
        tenon_cuts[0],
        negative_csg=_union_into_cut(shoulder_waste, remaining_cuts, TENON_CUT_LABEL) if remaining_cuts else shoulder_waste,
        maybe_top_end_cut_distance_from_bottom=max(top_ends, default=None),
        maybe_bottom_end_cut_distance_from_bottom=min(bottom_ends, default=None),
        assembly_freedom=_common_withdrawal(tenon_cuts),
    )
    mortise = replace(mortise_cuts[0], negative_csg=SolidUnion(holes, label=MORTISE_CUT_LABEL),
                      assembly_freedom=_common_withdrawal(mortise_cuts))
    tenon, mortise = _apply_scribe_relief_if_configured(
        relief if isinstance(relief, ButtJointScribeReliefConfig) else None, tenon, mortise)
    accessories = {f"{key}_tenon_{i}": accessory for i, joint in enumerate(joints)
                   for key, accessory in joint.jointAccessories.items()}
    return Joint({tenon_timber.ticket.path: tenon, mortise_timber.ticket.path: mortise}, JointTicket(joint_type="mortise_and_tenon"), accessories)


def _tenon_height_index(arrangement: ButtJointTimberArrangement) -> int:
    """Return which of the butt timber's size axes (0: its X, 1: its Y) is the tenon's height relative
    to the joint: the axis normal to the joint plane."""
    joint_plane_normal = arrangement.compute_normalized_timber_cross_product()
    height_face = arrangement.butt_timber.get_closest_oriented_long_face_from_global_direction(joint_plane_normal)
    return arrangement.butt_timber.get_size_index_in_long_face_normal_axis(height_face)


def _resolve_tenon_size_relative_to_joint(
    arrangement: ButtJointTimberArrangement,
    tenon_size: Optional[V2],
    tenon_width_relative_to_joint: Optional[Numeric],
    tenon_height_relative_to_joint: Optional[Numeric],
) -> V2:
    has_relative_pair = tenon_width_relative_to_joint is not None or tenon_height_relative_to_joint is not None
    arrangement_check(
        None if (tenon_width_relative_to_joint is None) == (tenon_height_relative_to_joint is None)
        else "tenon_width_relative_to_joint and tenon_height_relative_to_joint must be provided together"
    )
    arrangement_check(
        None if tenon_size is None or not has_relative_pair
        else "Provide either tenon_size or (tenon_width_relative_to_joint and tenon_height_relative_to_joint), not both"
    )
    arrangement_check(
        None if tenon_size is not None or has_relative_pair
        else "Must provide either tenon_size or (tenon_width_relative_to_joint and tenon_height_relative_to_joint)"
    )

    if tenon_size is not None:
        warnings.warn(
            "tenon_size is deprecated in favor of tenon_width_relative_to_joint and "
            "tenon_height_relative_to_joint, which size the tenon relative to the joint "
            "plane instead of the tenon timber's local X/Y axes.",
            stacklevel=3,
        )
        return tenon_size

    height_index = _tenon_height_index(arrangement)
    width_index = 1 - height_index

    resolved_size: List[Optional[Numeric]] = [None, None]
    resolved_size[height_index] = tenon_height_relative_to_joint
    resolved_size[width_index] = tenon_width_relative_to_joint
    return Matrix(resolved_size)


def cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_length: Numeric,
    tenon_size: Optional[V2] = None,
    tenon_width_relative_to_joint: Optional[Numeric] = None,
    tenon_height_relative_to_joint: Optional[Numeric] = None,
    mortise_depth: Optional[Numeric] = None,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,
    bore_mortise_perpendicular_to_face: bool = False,
    use_round_tenon: bool = False,
    relief: Union[None, ButtJointScribeReliefConfig, ButtJointNotchReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
    inset_shoulder_relief_style: Optional[InsetShoulderReliefStyle] = None,
) -> Joint:
    """
    Creates a mortise and tenon joint for plane-aligned timbers.
    """
    arrangement_check(arrangement.check_plane_aligned(), arrangement)

    tenon_size = _resolve_tenon_size_relative_to_joint(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
    )

    tenon_end_direction = arrangement.butt_timber.get_face_direction_global(
        TimberFace.TOP if arrangement.butt_timber_end == TimberEnd.TOP else TimberFace.BOTTOM
    )
    mortise_face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()

    mortise_shoulder_distance_from_centerline_or_centerplane = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=arrangement.receiving_timber,
    )

    notch_from_face = isinstance(relief, ButtJointNotchReliefConfig) and relief.notch_from == NotchFrom.Face

    joint = cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline_or_centerplane=mortise_shoulder_distance_from_centerline_or_centerplane,
        tenon_position=tenon_position,
        wedge_parameters=wedge_parameters,
        peg_parameters=peg_parameters,
        bore_mortise_perpendicular_to_face=bore_mortise_perpendicular_to_face,
        use_round_tenon=use_round_tenon,
        relief=None if isinstance(relief, ButtJointNotchReliefConfig) else relief,
        inset_shoulder_relief_style=(
            InsetShoulderReliefStyle.PerfectOnly if notch_from_face
            else InsetShoulderReliefStyle.NoRelief if isinstance(relief, ButtJointNotchReliefConfig)
            else inset_shoulder_relief_style or InsetShoulderReliefStyle.Rough
        ),
    )

    if isinstance(relief, ButtJointNotchReliefConfig):
        geom = _plane_aligned_shoulder_notch(
            arrangement, relief.notch_from, mortise_shoulder_distance_from_centerline_or_centerplane)
        if geom is not None:
            tenon_key = arrangement.butt_timber.ticket.path
            mortise_key = arrangement.receiving_timber.ticket.path
            mortise_cutting = joint.cuttings[mortise_key]
            tenon_cutting = joint.cuttings[tenon_key]
            assert mortise_cutting.negative_csg is not None
            assert tenon_cutting.negative_csg is not None
            updated_cuttings = dict(joint.cuttings)
            updated_cuttings[mortise_key] = replace(
                mortise_cutting,
                negative_csg=_union_into_cut(
                    mortise_cutting.negative_csg,
                    [geom.receiving_timber_notch_negative_CSG],
                    MORTISE_CUT_LABEL,
                ),
            )
            if geom.butting_timber_relief_negative_CSG is not None:
                updated_cuttings[tenon_key] = replace(
                    tenon_cutting,
                    negative_csg=_union_into_cut(
                        tenon_cutting.negative_csg,
                        [geom.butting_timber_relief_negative_CSG],
                        TENON_CUT_LABEL,
                    ),
                )
            joint = replace(joint, cuttings=updated_cuttings)

    return joint


def cut_mortise_and_tenon_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_length: Numeric,
    tenon_size: Optional[V2] = None,
    tenon_width_relative_to_joint: Optional[Numeric] = None,
    tenon_height_relative_to_joint: Optional[Numeric] = None,
    mortise_depth: Optional[Numeric] = None,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,
    use_round_tenon: bool = False,
    relief: Union[None, ButtJointScribeReliefConfig, ButtJointNotchReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
    inset_shoulder_relief_style: Optional[InsetShoulderReliefStyle] = None,
) -> Joint:
    """
    Creates a mortise and tenon joint for face-aligned orthogonal timbers.
    """
    arrangement_check(arrangement.check_face_aligned_and_orthogonal(), arrangement)

    return cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        mortise_shoulder_inset=mortise_shoulder_inset,
        wedge_parameters=wedge_parameters,
        peg_parameters=peg_parameters,
        use_round_tenon=use_round_tenon,
        relief=relief,
        inset_shoulder_relief_style=inset_shoulder_relief_style,
    )


def cut_round_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_distance_from_centerline_or_centerplane: Numeric = scalar(0),
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool] = False,
    *,
    relief: None | ButtJointScribeReliefConfig | ButtJointNotchReliefConfig = ButtJointScribeReliefConfig.butt_timber(),
    inset_shoulder_relief_style: InsetShoulderReliefStyle = InsetShoulderReliefStyle.Rough,
) -> Joint:
    """
    Creates a simplified round mortise and tenon joint with any orientation.
    """
    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([diameter, diameter]),
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline_or_centerplane=mortise_shoulder_distance_from_centerline_or_centerplane,
        use_round_tenon=True,
        relief=relief,
        inset_shoulder_relief_style=inset_shoulder_relief_style,
        set_mortise_shoulder_parallel_to_face=set_mortise_shoulder_parallel_to_face,
    )


def cut_round_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    *,
    relief: None | ButtJointScribeReliefConfig | ButtJointNotchReliefConfig = ButtJointScribeReliefConfig.butt_timber(),
    inset_shoulder_relief_style: InsetShoulderReliefStyle = InsetShoulderReliefStyle.Rough,
) -> Joint:
    """
    Creates a simplified round mortise and tenon joint for plane-aligned timbers.
    """
    return cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=diameter,
        tenon_height_relative_to_joint=diameter,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_inset=mortise_shoulder_inset,
        use_round_tenon=True,
        relief=relief,
        inset_shoulder_relief_style=inset_shoulder_relief_style,
    )


def cut_practice_mortise_and_tenon_corner_joint_on_plane_aligned_timbers(
    arrangement: CornerJointTimberArrangement,
    tenon_width_relative_to_joint: Numeric,
    tenon_height_relative_to_joint: Numeric,
    tenon_length: Numeric,
    tenon_distance_from_end: Numeric = 0,
    tenon_lateral_offset: Numeric = 0,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    peg_parameters: Optional[SimplePegParameters] = None,
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Creates a mortise and tenon corner joint on plane-aligned timbers.
    """
    arrangement_check(arrangement.check_plane_aligned(), arrangement)

    tenon_timber = arrangement.timber1
    mortise_timber = arrangement.timber2
    tenon_end = arrangement.timber1_end
    mortise_end = arrangement.timber2_end

    joint_plane_normal = arrangement.compute_normalized_timber_cross_product()
    height_face = tenon_timber.get_closest_oriented_long_face_from_global_direction(joint_plane_normal)
    height_index = tenon_timber.get_size_index_in_long_face_normal_axis(height_face)
    width_index = 1 - height_index

    mortise_end_direction = mortise_timber.get_face_direction_global(mortise_end)
    width_axis_positive_direction = (
        tenon_timber.get_width_direction_global() if width_index == 0 else tenon_timber.get_height_direction_global()
    )
    width_sign = scalar(1) if safe_dot_product(mortise_end_direction, width_axis_positive_direction) > 0 else scalar(-1)

    half_tenon_timber_width = tenon_timber.size[width_index] / scalar(2)
    tenon_width_position = width_sign * (
        half_tenon_timber_width - tenon_distance_from_end - tenon_width_relative_to_joint / scalar(2)
    )

    tenon_position_components: List[Optional[Numeric]] = [None, None]
    tenon_position_components[width_index] = tenon_width_position
    tenon_position_components[height_index] = tenon_lateral_offset
    tenon_position = Matrix(tenon_position_components)

    butt_arrangement = ButtJointTimberArrangement(
        butt_timber=tenon_timber,
        receiving_timber=mortise_timber,
        butt_timber_end=tenon_end,
        front_face_on_butt_timber=arrangement.front_face_on_timber1,
    )

    joint = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=butt_arrangement,
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
        tenon_length=tenon_length,
        tenon_position=tenon_position,
        mortise_depth=mortise_depth,
        mortise_shoulder_inset=mortise_shoulder_inset,
        peg_parameters=peg_parameters,
        relief=relief,
    )

    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    mortise_entry_long_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(-tenon_end_direction)
    mortise_far_face = mortise_entry_long_face.to.face().get_opposite_face()
    mortise_far_face_point_global = get_center_point_on_face_global(mortise_far_face, mortise_timber)

    tenon_end_cut_distance_from_bottom = safe_dot_product(
        mortise_far_face_point_global - tenon_timber.get_bottom_position_global(),
        tenon_timber.get_length_direction_global(),
    )

    tenon_entry_long_face = tenon_timber.get_closest_oriented_long_face_from_global_direction(-mortise_end_direction)
    tenon_far_face = tenon_entry_long_face.to.face().get_opposite_face()
    tenon_far_face_point_global = get_center_point_on_face_global(tenon_far_face, tenon_timber)

    mortise_end_cut_distance_from_bottom = safe_dot_product(
        tenon_far_face_point_global - mortise_timber.get_bottom_position_global(),
        mortise_timber.get_length_direction_global(),
    )

    tenon_cutting = replace(
        joint.cuttings[tenon_timber.ticket.path],
        maybe_top_end_cut_distance_from_bottom=tenon_end_cut_distance_from_bottom if tenon_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tenon_end_cut_distance_from_bottom if tenon_end == TimberEnd.BOTTOM else None,
    )
    mortise_cutting = replace(
        joint.cuttings[mortise_timber.ticket.path],
        maybe_top_end_cut_distance_from_bottom=mortise_end_cut_distance_from_bottom if mortise_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=mortise_end_cut_distance_from_bottom if mortise_end == TimberEnd.BOTTOM else None,
    )

    return replace(
        joint,
        cuttings={
            tenon_timber.ticket.path: tenon_cutting,
            mortise_timber.ticket.path: mortise_cutting,
        },
        ticket=JointTicket(joint_type="mortise_and_tenon_corner"),
    )


class MeasureOppositeShoulderFrom(Enum):
    Perfect = 0
    Rough = 1


class TuskEntryFace(Enum):
    Front = 0
    Top = 1


@dataclass(frozen=True)
class TuskParameters:
    tusk_thickness: Numeric
    tusk_small_width: Numeric
    tusk_tip_stickout: Optional[Numeric] = None
    tusk_back_stickout: Optional[Numeric] = None
    tusk_angle: Numeric = degrees(10)
    entry_face: TuskEntryFace = TuskEntryFace.Front


def cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_length_past_opposite_shoulder: Numeric,
    tusk_parameters: TuskParameters,
    tenon_size: Optional[V2] = None,
    tenon_width_relative_to_joint: Optional[Numeric] = None,
    tenon_height_relative_to_joint: Optional[Numeric] = None,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    measure_opposite_shoulder_from: MeasureOppositeShoulderFrom = MeasureOppositeShoulderFrom.Perfect,
    opposite_mortise_shoulder_inset: Numeric = scalar(0),
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Creates a through mortise-and-tenon joint locked by a tapered crosswise key (a "tusk").

    The tenon is sized as in cut_mortise_and_tenon_joint_on_plane_aligned_timbers: by
    tenon_width_relative_to_joint and tenon_height_relative_to_joint, or by the deprecated tenon_size.
    """
    arrangement_check(arrangement.check_plane_aligned(), arrangement)
    tenon_size = _resolve_tenon_size_relative_to_joint(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
    )
    height_index = _tenon_height_index(arrangement)

    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    entry_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=mortise_timber,
    )

    opposite_face = mortise_face.get_opposite_face()
    if measure_opposite_shoulder_from == MeasureOppositeShoulderFrom.Perfect:
        opposite_shoulder_distance_from_centerline = -convert_mortise_shoulder_inset_to_centerline_distance(
            mortise_shoulder_inset=opposite_mortise_shoulder_inset,
            mortise_face=opposite_face,
            receiving_timber=mortise_timber,
        )
    else:
        opposite_shoulder_distance_from_centerline = (
            -mortise_timber.get_half_rough_size_in_face_normal_axis(opposite_face)
            + opposite_mortise_shoulder_inset
        )

    distance_between_shoulders = entry_shoulder_distance_from_centerline - opposite_shoulder_distance_from_centerline
    tenon_length = distance_between_shoulders + tenon_length_past_opposite_shoulder

    base_joint = cut_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=tenon_size[1 - height_index],
        tenon_height_relative_to_joint=tenon_size[height_index],
        tenon_length=tenon_length,
        mortise_depth=None,
        tenon_position=tenon_position,
        mortise_shoulder_inset=mortise_shoulder_inset,
        relief=relief,
    )

    entry_face_designation = (
        arrangement.front_face_on_butt_timber
        if tusk_parameters.entry_face == TuskEntryFace.Front
        else arrangement.top_face_on_butt_timber
    )
    if entry_face_designation is None:
        raise arrangement_error(
            "arrangement.front_face_on_butt_timber/top_face_on_butt_timber (per tusk_parameters.entry_face) "
            "must be set to determine which face the tusk enters from", arrangement)
    entry_axis_extent = (
        tenon_size[0] if entry_face_designation in (TimberLongFace.RIGHT, TimberLongFace.LEFT) else tenon_size[1]
    )

    up_direction = tenon_timber.get_height_direction_global()
    shoulder_result = compute_butt_joint_shoulder(
        arrangement=arrangement,
        distance_from_centerline_or_centerplane=entry_shoulder_distance_from_centerline,
        up_direction=up_direction,
    )
    resolved_tenon_position = tenon_position if tenon_position is not None else Matrix([scalar(0), scalar(0)])
    tenon_right = tenon_timber.get_face_direction_global(TimberFace.RIGHT)
    tenon_front = tenon_timber.get_face_direction_global(TimberFace.FRONT)
    entry_marking_origin_global = (
        shoulder_result.marking_space.transform.position
        + tenon_right * resolved_tenon_position[0]
        + tenon_front * resolved_tenon_position[1]
    )
    opposite_shoulder_position_global = (
        entry_marking_origin_global + shoulder_result.butt_direction * distance_between_shoulders
    )

    rough_half_extent = mortise_timber.get_half_rough_size_in_face_normal_axis(opposite_face)
    rough_half_extent_past_opposite_shoulder = rough_half_extent + opposite_shoulder_distance_from_centerline

    tusk_geo = tusk_tenon_geometry(
        arrangement=arrangement,
        opposite_shoulder_position_global=opposite_shoulder_position_global,
        tenon_length_direction=shoulder_result.butt_direction,
        entry_face_designation=entry_face_designation,
        entry_axis_extent=entry_axis_extent,
        tusk_parameters=tusk_parameters,
        rough_half_extent_past_opposite_shoulder=rough_half_extent_past_opposite_shoulder,
    )

    tenon_hole_local = adopt_csg(None, tenon_timber.transform, tusk_geo.tenon_hole_negative_csg)

    tenon_cut = base_joint.cuttings[tenon_timber.ticket.path]
    mortise_cut = base_joint.cuttings[mortise_timber.ticket.path]
    assert tenon_cut.negative_csg is not None and mortise_cut.negative_csg is not None

    tenon_cut = replace(
        tenon_cut,
        negative_csg=_union_into_cut(
            tenon_cut.negative_csg, [tenon_hole_local], TENON_CUT_LABEL),
    )
    if tusk_geo.mortise_clearance_negative_csg is not None:
        mortise_clearance_local = adopt_csg(None, mortise_timber.transform, tusk_geo.mortise_clearance_negative_csg)
        mortise_cut = replace(
            mortise_cut,
            negative_csg=_union_into_cut(
                mortise_cut.negative_csg, [mortise_clearance_local], MORTISE_CUT_LABEL),
        )

    joint_accessories = dict(base_joint.jointAccessories)
    joint_accessories["tusk"] = tusk_geo.tusk_accessory_csg

    return Joint(
        cuttings={
            tenon_timber.ticket.path: tenon_cut,
            mortise_timber.ticket.path: mortise_cut,
        },
        ticket=JointTicket(joint_type="tusked_mortise_and_tenon"),
        jointAccessories=joint_accessories,
    )
