"""
Kumiki - Mortise and tenon joint construction functions
Contains mortise-and-tenon joint implementations: plain (generic/plane-aligned/face-aligned/round),
corner, and tusked variants.
"""

from __future__ import annotations

import warnings
from dataclasses import replace
from enum import Enum
from typing import List, Optional, Union

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.cutcsg import (
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
    HalfSpaceFeature,
    SimpleRectangularPrismFeature,
)
from kumiki.measuring import (
    locate_top_center_position,
    locate_bottom_center_position,
    mark_distance_from_end_along_centerline,
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


@dataclass(frozen=True)
class WedgeParameters:
    """
    Parameters for wedges in mortise and tenon joints.

    Attributes:
        shape: Shape specification for the wedge
        depth: Depth of the wedge cut (may differ from length of wedge)
        width_axis: Wedges run along this axis.
        positions: Positions from center of timber in the width axis
        expand_mortise: Amount to fan out bottom of mortise to fit wedges
    """
    shape: WedgeShape
    depth: Numeric
    width_axis: Direction3D
    positions: List[Numeric]
    expand_mortise: Numeric = scalar(0)


class InsetShoulderReliefStyle(Enum):
    Rough = 0
    PerfectOnly = 1
    NoRelief = 2


_TENON_FACE = FeatureProperties(group=FeatureGroup.NONE)


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
    """
    Creates a mortise and tenon joint with full control over all parameters.
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
        require_check(
            None if tenon_size[0] == tenon_size[1] else "Round tenon requires tenon_size[0] == tenon_size[1]"
        )
        require_check(
            None if peg_parameters is None else "Round tenon does not support pegs (peg_parameters must be None)"
        )

    if bore_mortise_perpendicular_to_face:
        require_check(
            None if not use_round_tenon
            else "bore_mortise_perpendicular_to_face cannot be True for round tenons"
        )
        require_check(
            None if mortise_depth is not None
            else "mortise_depth must be provided (not None) when bore_mortise_perpendicular_to_face is True"
        )
        require_check(arrangement.check_plane_aligned())

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
    shoulder_from_tenon_end_mark = mark_distance_from_end_along_centerline(shoulder_plane, tenon_timber, tenon_end)

    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    shoulder_point_global = shoulder_from_tenon_end_mark.locate().position

    tenon_right = tenon_timber.get_face_direction_global(TimberFace.RIGHT)
    tenon_front = tenon_timber.get_face_direction_global(TimberFace.FRONT)
    marking_origin_global = (
        shoulder_point_global
        + tenon_right * tenon_position[0]
        + tenon_front * tenon_position[1]
    )

    tenon_orientation = compute_timber_orientation(
        safe_normalize_vector(tenon_end_direction), tenon_timber.get_width_direction_global()
    )
    tenon_base_transform = Transform(position=marking_origin_global, orientation=tenon_orientation)
    marking_space: Space = Space(transform=tenon_base_transform)

    mortise_face_normal = shoulder_plane.normal
    cos_angle = safe_dot_product(
        safe_normalize_vector(mortise_face_normal), safe_normalize_vector(tenon_end_direction)
    )

    sin_angle_sq = scalar(1) - cos_angle * cos_angle
    is_square = safe_zero_test(sin_angle_sq)
    sin_angle = sqrt(Abs(sin_angle_sq))
    back_extension = scalar(0) if is_square else max(tenon_size[0], tenon_size[1]) / sin_angle

    tenon_tip_name = "tenon_top" if tenon_end == TimberEnd.TOP else "tenon_bot"

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
            _features=[
                SimpleRectangularPrismFeature("tenon_right", face=PrismFace.RIGHT, properties=_TENON_FACE),
                SimpleRectangularPrismFeature("tenon_left", face=PrismFace.LEFT, properties=_TENON_FACE),
                SimpleRectangularPrismFeature("tenon_front", face=PrismFace.FRONT, properties=_TENON_FACE),
                SimpleRectangularPrismFeature("tenon_back", face=PrismFace.BACK, properties=_TENON_FACE),
                SimpleRectangularPrismFeature(tenon_tip_name, face=PrismFace.TOP, properties=_TENON_FACE),
            ],
            label=CutCSGLabel("tenon"),
        )

    tenon_prism_cropping_csgs: Optional[List[CutCSG]] = None
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
        end_crop_distance = tenon_size[joint_angle_axis_index] / sin_angle / scalar(2)

        mortise_hole_end_crop_global = HalfSpace(
            normal=mortise_hole_length_oblique_direction,
            offset=end_crop_distance + safe_dot_product(mortise_hole_length_oblique_direction, shoulder_point_global),
            label=CutCSGLabel("tenon_crop_to_mortise_length"),
        )

        mortise_depth_crop_global = HalfSpace(
            normal=-mortise_face_direction,
            offset=mortise_depth - safe_dot_product(mortise_face_direction, get_center_point_on_face_global(mortise_face, mortise_timber)),
            label=CutCSGLabel("tenon_crop_to_mortise_depth"),
        )

        tenon_prism_cropping_csgs = [mortise_hole_end_crop_global, mortise_depth_crop_global]

    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
        _features=[HalfSpaceFeature("shoulder", properties=FeatureProperties(group=FeatureGroup.A))],
        label=CutCSGLabel("shoulder"),
    )

    tenon_prism_cropped = (
        tenon_prism_global
        if tenon_prism_cropping_csgs is None
        else Difference(
            base=tenon_prism_global,
            subtract=tenon_prism_cropping_csgs,
            label=CutCSGLabel("tenon_cropped"),
        )
    )

    tenon_prism_local = adopt_csg(None, tenon_timber.transform, tenon_prism_cropped)
    shoulder_half_space_local = adopt_csg(None, tenon_timber.transform, shoulder_half_space_global)

    mortise_hole_prism_global = None

    if do_lengthwise_cropping:
        if use_round_tenon:
            mortise_radius = tenon_size[0] / scalar(2)
            axis_direction_global = safe_normalize_vector(tenon_end_direction)
            mortise_hole_prism_global = Cylinder(
                axis_direction=axis_direction_global,
                radius=mortise_radius,
                position=marking_space.transform.position,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label=CutCSGLabel("mortise_hole"),
            )
        else:
            opp_index = 1 if joint_angle_axis_index == 0 else 0
            mortise_hole_size = create_v2(
                tenon_size[opp_index],
                tenon_size[joint_angle_axis_index] / sin_angle,
            )

            mortise_hole_orientation = Orientation.from_z_and_y(
                z_direction=-mortise_face_normal,
                y_direction=mortise_hole_length_oblique_direction,
            )

            mortise_hole_transform = Transform(
                position=marking_space.transform.position,
                orientation=mortise_hole_orientation,
            )

            mortise_hole_prism_global = RectangularPrism(
                size=mortise_hole_size,
                transform=mortise_hole_transform,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                _features=[
                    SimpleRectangularPrismFeature("mortise_right", face=PrismFace.RIGHT),
                    SimpleRectangularPrismFeature("mortise_left", face=PrismFace.LEFT),
                    SimpleRectangularPrismFeature("mortise_front", face=PrismFace.FRONT),
                    SimpleRectangularPrismFeature("mortise_back", face=PrismFace.BACK),
                    SimpleRectangularPrismFeature("mortise_bottom", face=PrismFace.TOP),
                ],
                label=CutCSGLabel("mortise_hole"),
            )
    else:
        if use_round_tenon:
            mortise_radius = tenon_size[0] / scalar(2)
            axis_direction_global = safe_normalize_vector(tenon_end_direction)
            mortise_hole_prism_global = Cylinder(
                axis_direction=axis_direction_global,
                radius=mortise_radius,
                position=marking_space.transform.position,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label=CutCSGLabel("mortise_hole"),
            )
        else:
            mortise_hole_prism_global = RectangularPrism(
                size=tenon_size,
                transform=marking_space.transform,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                _features=[
                    SimpleRectangularPrismFeature("mortise_right", face=PrismFace.RIGHT),
                    SimpleRectangularPrismFeature("mortise_left", face=PrismFace.LEFT),
                    SimpleRectangularPrismFeature("mortise_front", face=PrismFace.FRONT),
                    SimpleRectangularPrismFeature("mortise_back", face=PrismFace.BACK),
                    SimpleRectangularPrismFeature("mortise_bottom", face=PrismFace.TOP),
                ],
                label=CutCSGLabel("mortise_hole"),
            )

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
        shoulder_notch_relief_geom: ShoulderReliefCSGGeometry | None = chop_butt_joint_shoulder_notch_relief_4sided(
            arrangement,
            mortise_shoulder_distance_from_centerline_or_centerplane,
        )
    elif inset_shoulder_relief_style is InsetShoulderReliefStyle.NoRelief:
        shoulder_notch_relief_geom = None
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
                    base=tenon_timber.get_extended_actual_csg_local(extend_bot=extend_bot, extend_top=extend_top),
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
                        subtract=[shoulder_half_space_global],
                    ),
                    right=mortise_ptw_global,
                    label=CutCSGLabel("shoulder_rough_relief"),
                ),
            )

        shoulder_notch_relief_geom = ShoulderReliefCSGGeometry(
            receiving_timber_notch_negative_CSG=scribe_csg_mortise_local,
            butting_timber_relief_negative_CSG=tenon_relief_local,
        )
    else:
        shoulder_notch_relief_geom = None

    tenon_cut_csg = Difference(
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
    tip_position_global = marking_space.transform.position + tenon_length_direction_global * max(tenon_length, max(tenon_size[0], tenon_size[1])/cos_angle)
    tip_position_local = tenon_timber.transform.global_to_local(tip_position_global)
    tip_z_local = tip_position_local[2]

    tenon_cut = Cutting(
        timber=tenon_timber,
        maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.BOTTOM else None,
        negative_csg=tenon_cut_csg,
        label=CutCSGLabel("mortise_and_tenon"),
    )

    joint_accessories = {}
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


def _resolve_tenon_size_relative_to_joint(
    arrangement: ButtJointTimberArrangement,
    tenon_size: Optional[V2],
    tenon_width_relative_to_joint: Optional[Numeric],
    tenon_height_relative_to_joint: Optional[Numeric],
) -> V2:
    has_relative_pair = tenon_width_relative_to_joint is not None or tenon_height_relative_to_joint is not None
    require_check(
        None if (tenon_width_relative_to_joint is None) == (tenon_height_relative_to_joint is None)
        else "tenon_width_relative_to_joint and tenon_height_relative_to_joint must be provided together"
    )
    require_check(
        None if tenon_size is None or not has_relative_pair
        else "Provide either tenon_size or (tenon_width_relative_to_joint and tenon_height_relative_to_joint), not both"
    )
    require_check(
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

    joint_plane_normal = arrangement.compute_normalized_timber_cross_product()
    height_face = arrangement.butt_timber.get_closest_oriented_long_face_from_global_direction(joint_plane_normal)
    height_index = arrangement.butt_timber.get_size_index_in_long_face_normal_axis(height_face)
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
) -> Joint:
    """
    Creates a mortise and tenon joint for plane-aligned timbers.
    """
    require_check(arrangement.check_plane_aligned())

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
            else InsetShoulderReliefStyle.Rough
        ),
    )

    if isinstance(relief, ButtJointNotchReliefConfig):
        notch_mortise_shoulder_distance_from_centerline_or_centerplane = (
            convert_mortise_shoulder_inset_to_centerline_distance(
                mortise_shoulder_inset=scalar(0),
                mortise_face=mortise_face,
                receiving_timber=arrangement.receiving_timber,
            )
            if notch_from_face
            else mortise_shoulder_distance_from_centerline_or_centerplane
        )
        geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(
            arrangement, notch_mortise_shoulder_distance_from_centerline_or_centerplane,
        )
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
) -> Joint:
    """
    Creates a mortise and tenon joint for face-aligned orthogonal timbers.
    """
    require_check(arrangement.check_face_aligned_and_orthogonal())

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
    )


def cut_round_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_distance_from_centerline_or_centerplane: Numeric = scalar(0),
    set_mortise_shoulder_parallel_to_face: Union[TimberLongFace, bool] = False,
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
        set_mortise_shoulder_parallel_to_face=set_mortise_shoulder_parallel_to_face,
    )


def cut_round_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
) -> Joint:
    """
    Creates a simplified round mortise and tenon joint for plane-aligned timbers.
    """
    require_check(arrangement.check_plane_aligned())

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

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([diameter, diameter]),
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline_or_centerplane=mortise_shoulder_distance_from_centerline_or_centerplane,
        use_round_tenon=True,
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
    require_check(arrangement.check_plane_aligned())

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
    tenon_size: V2,
    tenon_length_past_opposite_shoulder: Numeric,
    tusk_parameters: TuskParameters,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    measure_opposite_shoulder_from: MeasureOppositeShoulderFrom = MeasureOppositeShoulderFrom.Perfect,
    opposite_mortise_shoulder_inset: Numeric = scalar(0),
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Creates a through mortise-and-tenon joint locked by a tapered crosswise key (a "tusk").
    """
    arrangement.check_plane_aligned()

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
        tenon_size=tenon_size,
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
    assert entry_face_designation is not None, (
        "arrangement.front_face_on_butt_timber/top_face_on_butt_timber (per tusk_parameters.entry_face) "
        "must be set to determine which face the tusk enters from"
    )
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
