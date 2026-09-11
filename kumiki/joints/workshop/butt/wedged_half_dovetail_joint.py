"""
Kumiki - Wedged half-dovetail mortise and tenon joint construction functions
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional, Union

from kumiki.timber import (
    AssemblyFreedom,
    Cutting,
    Joint,
    JointTicket,
    Ordering,
    TimberEnd,
)
from kumiki.construction import ButtJointTimberArrangement
from kumiki.rule import (
    Numeric,
    V2,
    Matrix,
    degrees,
    scalar,
    cos,
    sin,
)
from kumiki.cutcsg import (
    CutCSG,
    CutCSGLabel,
    SolidUnion,
    adopt_csg,
)
from ..shavings.relief import (
    chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided,
    ButtJointScribeReliefConfig,
    apply_scribe_relief_if_configured,
)
from ..shavings.build_a_butt import (
    convert_mortise_shoulder_inset_to_centerline_distance,
    compute_butt_joint_shoulder,
    dovetail_tenon_geometry,
    DovetailTenonWedgeAccessoryParameters,
)

TENON_CUT_LABEL = CutCSGLabel("tenon_cut")
MORTISE_CUT_LABEL = CutCSGLabel("mortise_cut")


def _union_into_cut(existing: CutCSG, additions: list[CutCSG], label: CutCSGLabel) -> SolidUnion:
    """Add more removed material to a timber's cut, as one labelled union."""
    if isinstance(existing, SolidUnion) and existing.label == label:
        return SolidUnion(children=list(existing.children) + list(additions), label=label)
    return SolidUnion(children=[existing] + list(additions), label=label)


def cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_depth: Numeric,
    dovetail_depth: Numeric,
    wedge_accessory_parameters: DovetailTenonWedgeAccessoryParameters,
    tenon_lateral_offset: Numeric = scalar(0),
    receiving_timber_mortise_extra_depth: Numeric = scalar(0),
    mortise_shoulder_inset: Numeric = scalar(0),
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Create a half-dovetail mortise-and-tenon joint (with an optional wedge accessory).

    Built on top of `dovetail_tenon_geometry`. The "top" of the dovetail is flush with
    `arrangement.top_face_on_butt_timber`; the opposite side slopes outward by `dovetail_depth`
    over `tenon_depth` to give the joint its mechanical pull-out resistance.

    Args:
        arrangement: Butt joint arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must be face-aligned and orthogonal, with top_face_on_butt_timber set to the
            face the dovetail's flat "top" is flush with (the opposite face is the sloped side).
        tenon_size: Cross-section of the tenon (X = butt RIGHT axis, Y = butt TOP axis).
        tenon_depth: Depth of the tenon into the receiving timber, measured from the shoulder.
        dovetail_depth: How far the sloped side of the dovetail kicks out over `tenon_depth`.
        tenon_lateral_offset: Offset of the tenon along the lateral direction (perpendicular
            to both length and top-to-bottom). 0 = centered on the butt timber.
        receiving_timber_mortise_extra_depth: Extra mortise depth in the receiving timber past
            the tenon tip.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the entry face inward. 0 = shoulder flush with the
            entry face (the default). Positive pushes the shoulder deeper into the receiving
            timber.
        wedge_accessory_parameters: If provided, a wedge accessory is added on the
            `arrangement.top_face_on_butt_timber` side of the tenon and a matching slot is cut
            into the receiving timber.
        relief: Scribe-relief configuration for imperfect timbers. Defaults to scribing the
            tenon (butt) timber onto the mortise (receiving) timber. Pass None to skip.

    Returns:
        Joint object with cuts on both timbers and (optionally) a "wedge" accessory.
    """
    assert arrangement.top_face_on_butt_timber is not None, (
        "arrangement.top_face_on_butt_timber must be set to determine the dovetail's flat side"
    )
    dovetail_top_side_on_butt_timber = arrangement.top_face_on_butt_timber
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    mortise_shoulder_distance_from_centerline_or_centerplane = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=mortise_timber,
    )

    up_direction = tenon_timber.get_height_direction_global()

    shoulder_result = compute_butt_joint_shoulder(
        arrangement=arrangement,
        distance_from_centerline_or_centerplane=mortise_shoulder_distance_from_centerline_or_centerplane,
        up_direction=up_direction,
    )

    geo = dovetail_tenon_geometry(
        arrangement=arrangement,
        shoulder_result=shoulder_result,
        dovetail_top_side_on_butt_timber=dovetail_top_side_on_butt_timber,
        tenon_size=tenon_size,
        tenon_depth=tenon_depth,
        dovetail_depth=dovetail_depth,
        wedge_accessory_parameters=wedge_accessory_parameters,
        tenon_lateral_offset=tenon_lateral_offset,
        receiving_timber_mortise_extra_depth=receiving_timber_mortise_extra_depth,
    )

    tenon_negative_local = adopt_csg(None, tenon_timber.transform, geo.tenon_negative_csg)
    mortise_negative_local = adopt_csg(None, mortise_timber.transform, geo.mortise_negative_csg)

    relief_geom = chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided(
        arrangement,
        mortise_shoulder_distance_from_centerline_or_centerplane,
        notch_angle=degrees(45),
    )
    if relief_geom is not None:
        mortise_negative_local = _union_into_cut(
            mortise_negative_local,
            [relief_geom.receiving_timber_notch_negative_CSG],
            MORTISE_CUT_LABEL,
        )
        if relief_geom.butting_timber_relief_negative_CSG is not None:
            tenon_negative_local = _union_into_cut(
                tenon_negative_local,
                [relief_geom.butting_timber_relief_negative_CSG],
                TENON_CUT_LABEL,
            )

    tenon_tip_position_global = (
        shoulder_result.marking_space.transform.position
        + shoulder_result.butt_direction * tenon_depth
    )
    tip_position_local = tenon_timber.transform.global_to_local(tenon_tip_position_global)
    tip_z_local = tip_position_local[2]

    wedge_angle = wedge_accessory_parameters.wedge_angle
    cos_angle = cos(wedge_angle)
    sin_angle = sin(wedge_angle)

    top_face_dir = tenon_timber.get_face_direction_global(
        dovetail_top_side_on_butt_timber.to.face()
    )

    tenon_disassembly_dir = -cos_angle * shoulder_result.butt_direction + sin_angle * top_face_dir
    mortise_disassembly_dir = cos_angle * shoulder_result.butt_direction - sin_angle * top_face_dir
    freed_dist = tenon_depth / cos_angle

    timber_suborder = 1 if geo.wedge_accessory_csg is not None else 0
    tenon_cut_no_relief = Cutting(
        timber=tenon_timber,
        maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberEnd.BOTTOM else None,
        negative_csg=tenon_negative_local,
        label=CutCSGLabel("wedged_half_dovetail_mortise_and_tenon"),
        assembly_freedom=AssemblyFreedom.translation(tenon_disassembly_dir, freed_after=freed_dist),
        assembly_ordering=Ordering(0, timber_suborder),
    )

    mortise_cut_no_relief = Cutting(
        timber=mortise_timber,
        negative_csg=mortise_negative_local,
        label=CutCSGLabel("wedged_half_dovetail_mortise_and_tenon"),
        assembly_freedom=AssemblyFreedom.translation(mortise_disassembly_dir, freed_after=freed_dist),
        assembly_ordering=Ordering(0, timber_suborder),
    )

    tenon_cut, mortise_cut = apply_scribe_relief_if_configured(
        relief=relief,
        butt_cut=tenon_cut_no_relief,
        receiving_cut=mortise_cut_no_relief,
    )

    joint_accessories = {}
    if geo.wedge_accessory_csg is not None:
        joint_accessories["wedge"] = geo.wedge_accessory_csg

    return Joint(
        cuttings={
            tenon_timber.ticket.path: tenon_cut,
            mortise_timber.ticket.path: mortise_cut,
        },
        ticket=JointTicket(joint_type="wedged_half_dovetail_mortise_and_tenon"),
        jointAccessories=joint_accessories,
    )


# Short alias
cut_wedged_half_dovetail_joint_on_face_aligned_timbers = (
    cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers
)
