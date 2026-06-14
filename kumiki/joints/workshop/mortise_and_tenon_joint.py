"""
Kumiki - Mortise and Tenon Joint Construction Functions
Contains various mortise and tenon joint implementations
"""

from __future__ import annotations  # Enable deferred annotation evaluation

import warnings
from functools import wraps

from kumiki.timber import *
from kumiki.measuring import (
    locate_top_center_position,
    locate_bottom_center_position,
    locate_position_on_centerline_from_bottom,
    locate_position_on_centerline_from_top,
    locate_into_face,
    locate_edge,
    locate_plane_from_edge_in_direction,
    mark_distance_from_end_along_centerline,
    mark_plane_from_edge_in_direction,
    get_point_on_face_global,
    Space,
)
from kumiki.construction import *
from kumiki.timber_shavings import are_timbers_plane_aligned
from kumiki.rule import *
from kumiki.rule import safe_dot_product
from kumiki.cutcsg import CutCSG, RectangularPrism, HalfSpace, Difference, SolidUnion, adopt_csg, PrismFace, Cylinder
from .notching import (
    ShoulderNotchCSGGeometry,
    chop_notch_for_butt_joint_arrangement,
    chop_shoulder_notch_aligned_with_timber,
    does_shoulder_plane_need_notching,
    warn_if_arrangement_timbers_imperfect,
)
from .build_a_butt import (
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
    PegPositionResult,
    PegPositionSpace,
    SimplePegParameters,
    compute_peg_positions,
    compute_butt_joint_shoulder,
    dovetail_tenon_geometry,
    DovetailTenonGeometeryResult,
    DovetailTenonWedgeAccessoryParameters,
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


# ============================================================================
# Helepers
# ============================================================================


@dataclass(frozen=True)
class WedgeParameters:
    """
    Parameters for wedges in mortise and tenon joints.
    
    Attributes:
        shape: Shape specification for the wedge
        depth: Depth of the wedge cut (may differ from length of wedge)
        width_axis: Wedges run along this axis. When looking perpendicular to this
                    and the length axis, you see the trapezoidal "sides" of the wedges
        positions: Positions from center of timber in the width axis
        expand_mortise: Amount to fan out bottom of mortise to fit wedges
                        - 0 means straight sides (default)
                        - X means expand both sides of mortise bottom by X (total), the shoulder of the mortise remains the original size
    """
    shape: WedgeShape
    depth: Numeric
    width_axis: Direction3D
    positions: List[Numeric]
    expand_mortise: Numeric = Rational(0)


# ============================================================================
# Helper Functions
# ============================================================================


def convert_mortise_shoulder_inset_to_centerline_distance(
    mortise_shoulder_inset: Numeric,
    mortise_face: TimberFace,
    receiving_timber: TimberLike,
) -> Numeric:
    """
    Convert user-facing mortise shoulder inset parameter to centerline-relative distance.

    Inset is measured from the mortise entry face surface toward the centerline (inward).
    This function converts it to the signed distance from centerline (measured toward the tenon).

    Args:
        mortise_shoulder_inset: Distance from mortise entry face inward. 0 = shoulder flush
            with the entry face. Positive = shoulder deeper into the timber.
        mortise_face: The face of the receiving timber where the mortise enters.
        receiving_timber: The receiving timber.

    Returns:
        Signed distance from the timber centerline to the shoulder plane, measured toward
        the tenon side. 0 = shoulder at centerline.
    """
    inset_plane = locate_into_face(mortise_shoulder_inset, mortise_face, receiving_timber)
    inset_marking = mark_plane_from_edge_in_direction(inset_plane, receiving_timber, TimberCenterline.CENTERLINE)
    return inset_marking.distance


# ============================================================================
# Mortise and Tenon Joint Construction Functions
# ============================================================================


def cut_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,

    mortise_shoulder_distance_from_centerline: Numeric = Rational(0),

    tenon_position: Optional[V2] = None,
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,

    # TODO rename this parameter, and also assert that mortise_depth is None if this is true
    crop_tenon_to_mortise_orientation_on_angled_joints: bool = False,
    use_round_tenon: bool = False,
) -> Joint:
    """
    Creates a mortise and tenon joint with full control over all parameters.

    This is the generic implementation used by all specialized variants
    (`cut_mortise_and_tenon_joint_on_PAT`, `cut_mortise_and_tenon_joint_on_FAT`).
    Prefer those variants for common cases.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length: Length of the tenon extending from the mortise entry face. For angled
            joints, set this slightly longer than expected to ensure full penetration.
        mortise_depth: Depth of the mortise (None = through mortise). Measurement differs
            depending on crop_tenon_to_mortise_orientation_on_angled_joints.
        mortise_shoulder_distance_from_centerline: Signed distance from the mortise
            centerline to the shoulder plane, measured within the mortise cross-section
            in the direction toward the tenon centerline. 0 = shoulder at the mortise
            centerline. Positive pushes the shoulder toward the tenon.
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional). Note: peg
            distance_from_shoulder is measured along the tenon axis, while
            distance_from_centerline is measured along the mortise axis — this makes
            positioning pegs on angled braces easier.
        crop_tenon_to_mortise_orientation_on_angled_joints: If True, the tenon is cropped
            so its depth along the mortise face axis equals mortise_depth and its tip is
            trimmed to the mortise hole boundary. If False, mortise depth is measured along
            the tenon axis from the shoulder.
        use_round_tenon: If True, creates a round (cylindrical) tenon and mortise instead of
            rectangular. When True, tenon_size[0] and tenon_size[1] must be equal (no ovals),
            and peg_parameters must be None. Default is False.

    Returns:
        Joint object containing the two CutTimbers and any accessories, all in global space.
    """
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    warn_if_arrangement_timbers_imperfect(arrangement)

    # Default tenon_position to centered (0, 0)
    if tenon_position is None:
        tenon_position = Matrix([Rational(0), Rational(0)])

    # Validation for round tenon mode
    if use_round_tenon:
        require_check(
            None if tenon_size[0] == tenon_size[1] else "Round tenon requires tenon_size[0] == tenon_size[1]"
        )
        require_check(
            None if peg_parameters is None else "Round tenon does not support pegs (peg_parameters must be None)"
        )

    # TODO default mortise depth if mortise_depth is None

    # -------------------------------------------------------------------------
    # Step 3: Shoulder plane from centerline toward tenon
    # -------------------------------------------------------------------------
    shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
        arrangement, mortise_shoulder_distance_from_centerline
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

    # -------------------------------------------------------------------------
    # Step 4: Define marking_space (global Space at shoulder, toward tenon end)
    # -------------------------------------------------------------------------
    tenon_orientation = compute_timber_orientation(
        normalize_vector(tenon_end_direction), tenon_timber.get_width_direction_global()
    )
    tenon_base_transform = Transform(position=marking_origin_global, orientation=tenon_orientation)
    marking_space: Space = Space(transform=tenon_base_transform)

    # -------------------------------------------------------------------------
    # Step 5: Determine the angle between the mortise entry direction and tenon
    # -------------------------------------------------------------------------
    mortise_face_normal = shoulder_plane.normal
    cos_angle = safe_dot_product(
        normalize_vector(mortise_face_normal), normalize_vector(tenon_end_direction)
    )

    # -------------------------------------------------------------------------
    # Tenon prism (origin at marking_space) and shoulder half-space
    # -------------------------------------------------------------------------
    from sympy import Abs, sqrt

    # Back-extension from shoulder so prism fully contains tenon at oblique angles
    sin_angle_sq = Integer(1) - cos_angle * cos_angle
    sin_angle_safe = Rational(1, 10000) if safe_zero_test(sin_angle_sq) else sqrt(Abs(sin_angle_sq))
    back_extension = max(tenon_size[0], tenon_size[1]) / sin_angle_safe

    tenon_tip_name = "tenon_top" if tenon_end == TimberReferenceEnd.TOP else "tenon_bot"
    
    if use_round_tenon:
        # Round tenon: use cylinder with diameter = tenon_size[0]
        tenon_radius = tenon_size[0] / Integer(2)
        axis_direction_global = normalize_vector(tenon_end_direction)
        tenon_prism_global = Cylinder(
            axis_direction=axis_direction_global,
            radius=tenon_radius,
            position=marking_space.transform.position,
            start_distance=-back_extension,
            end_distance=tenon_length,
            label="tenon",
        )
    else:
        tenon_prism_global = RectangularPrism(
            size=tenon_size,
            transform=marking_space.transform,
            start_distance=-back_extension,
            end_distance=tenon_length,
            named_features=[
                ("tenon_right", PrismFace.RIGHT),
                ("tenon_left", PrismFace.LEFT),
                ("tenon_front", PrismFace.FRONT),
                ("tenon_back", PrismFace.BACK),
                (tenon_tip_name, PrismFace.TOP),
            ],
            label="tenon",
        )

    tenon_prism_cropping_csgs: Optional[List[CutCSG]] = None
    do_cropping = crop_tenon_to_mortise_orientation_on_angled_joints and not zero_test(cos_angle)
    if do_cropping:
        # Compute mortise_face locally — cropping is only used for plane-aligned timbers
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        mortise_face_direction = mortise_timber.get_face_direction_global(mortise_face)

        mortise_oblique_end = mortise_timber.get_closest_oriented_end_face_from_global_direction(tenon_end_direction)
        joint_angle_axis_face = tenon_timber.get_closest_oriented_long_face_from_global_direction(mortise_timber.get_face_direction_global(mortise_oblique_end))
        joint_angle_axis_index = tenon_timber.get_size_index_in_long_face_normal_axis(joint_angle_axis_face)

        mortise_hole_length_oblique_direction = mortise_timber.get_face_direction_global(mortise_oblique_end)
        end_crop_distance = tenon_size[joint_angle_axis_index] / sin_angle_safe / Rational(2)

        # Crop 1: far end of prism perpendicular to mortise face
        mortise_hole_end_crop_global = HalfSpace(
            normal=mortise_hole_length_oblique_direction,
            offset=end_crop_distance + safe_dot_product(mortise_hole_length_oblique_direction, shoulder_point_global),
        )

        # Crop 2: depth of tenon — plane parallel to the mortise face surface,
        # mortise_depth measured from the face inward.
        mortise_depth_crop_global = HalfSpace(
            normal=-mortise_face_direction,
            offset=mortise_depth - safe_dot_product(mortise_face_direction, get_point_on_face_global(mortise_face, mortise_timber)),
        )

        tenon_prism_cropping_csgs = [mortise_hole_end_crop_global, mortise_depth_crop_global]

    # Shoulder half-space: plane through centerline ∩ shoulder (marking origin), normal = shoulder plane normal
    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
        label="shoulder",
    )

    tenon_prism_cropped = (
        tenon_prism_global
        if tenon_prism_cropping_csgs is None
        else Difference(base=tenon_prism_global, subtract=tenon_prism_cropping_csgs)
    )

    # Convert from global to tenon timber local (orig_timber=None => CSG is in global space)
    tenon_prism_local = adopt_csg(None, tenon_timber.transform, tenon_prism_cropped)
    shoulder_half_space_local = adopt_csg(None, tenon_timber.transform, shoulder_half_space_global)

    # -------------------------------------------------------------------------
    # mortise hole
    # -------------------------------------------------------------------------

    mortise_hole_prism_global = None

    if do_cropping:
        if use_round_tenon:
            # Round mortise hole at an angle: use cylinder
            mortise_radius = tenon_size[0] / Integer(2)
            axis_direction_global = normalize_vector(-mortise_face_normal)
            mortise_hole_prism_global = Cylinder(
                axis_direction=axis_direction_global,
                radius=mortise_radius,
                position=marking_space.transform.position,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label="mortise_hole",
            )
        else:
            mortise_hole_size = create_v2(0,0)
            mortise_hole_size[1] = tenon_size[joint_angle_axis_index] / sin_angle_safe
            opp_index = 1 if joint_angle_axis_index == 0 else 0
            mortise_hole_size[0] = tenon_size[opp_index]

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
                label="mortise_hole",
            )
    else:
        if use_round_tenon:
            # Round mortise hole: use cylinder with same diameter as tenon
            mortise_radius = tenon_size[0] / Integer(2)
            axis_direction_global = normalize_vector(-mortise_face_normal)
            mortise_hole_prism_global = Cylinder(
                axis_direction=axis_direction_global,
                radius=mortise_radius,
                position=marking_space.transform.position,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label="mortise_hole",
            )
        else:
            mortise_hole_prism_global = RectangularPrism(
                size=tenon_size,
                transform=marking_space.transform,
                start_distance=-back_extension,
                end_distance=mortise_depth,
                label="mortise_hole",
            )

    # -------------------------------------------------------------------------
    # shoulder notch on mortise timber and matching relief on tenon timber
    # (when shoulder is inset from the mortise entry face)
    # -------------------------------------------------------------------------

    from sympy import pi as _pi

    notch_geom = chop_notch_for_butt_joint_arrangement(
        arrangement,
        mortise_shoulder_distance_from_centerline,
        # pass pi/2 so the relief angle naturally follows the butt approach angle
        notch_wall_min_relief_cut_angle=_pi / Rational(2),
    )

    # -------------------------------------------------------------------------
    # make the final cut CSGs
    # -------------------------------------------------------------------------

    tenon_cut_csg = Difference(
        base=shoulder_half_space_local,
        subtract=[tenon_prism_local],
    )

    mortise_hole_prism_local = adopt_csg(None, mortise_timber.transform, mortise_hole_prism_global)

    if notch_geom is not None:
        mortise_negative_csg = CSGUnion(
            children=[mortise_hole_prism_local, notch_geom.receiving_timber_notch_negative_CSG]
        )
    else:
        mortise_negative_csg = mortise_hole_prism_local

    mortise_cut = Cutting(
        timber=mortise_timber,
        negative_csg=mortise_negative_csg,
        label="mortise_and_tenon",
    )

    tenon_length_direction_global = tenon_timber.get_face_direction_global(tenon_end)
    tip_position_global = marking_space.transform.position + tenon_length_direction_global * max(tenon_length, max(tenon_size[0], tenon_size[1])/cos_angle)
    tip_position_local = tenon_timber.transform.global_to_local(tip_position_global)
    tip_z_local = tip_position_local[2]
    
    tenon_cut = Cutting(
        timber=tenon_timber,
        maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=tenon_cut_csg,
        label="mortise_and_tenon",
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
                # Cylinder axis is the Z column of the orientation in global space.
                axis_direction_global = orientation_global.matrix * create_v3(Integer(0), Integer(0), Integer(1))
                return Cylinder(
                    axis_direction=axis_direction_global,
                    radius=peg_size / Integer(2),
                    position=center_global,
                    start_distance=Rational(0),
                    end_distance=depth,
                    label=label,
                )
            return RectangularPrism(
                size=Matrix([peg_size, peg_size]),
                transform=Transform(
                    position=center_global,
                    orientation=orientation_global,
                ),
                start_distance=Rational(0),
                end_distance=depth,
                label=label,
            )

        for peg_idx, peg_result in enumerate(peg_results):
            # Create peg hole CSG in tenon local space (using offset position for draw-bore tightening)
            peg_hole_tenon_global = _build_peg_hole_global(
                peg_result.tenon_face_position_with_offset_global,
                peg_result.orientation_global,
                peg_result.peg_depth,
                f"peg_hole_{peg_idx}",
            )
            peg_holes_in_tenon_local.append(adopt_csg(None, tenon_timber.transform, peg_hole_tenon_global))

            # Create peg hole CSG in mortise local space
            peg_hole_mortise_global = _build_peg_hole_global(
                peg_result.mortise_entry_position_global,
                peg_result.orientation_global,
                peg_result.peg_depth,
                f"peg_hole_{peg_idx}",
            )
            peg_holes_in_mortise_local.append(adopt_csg(None, mortise_timber.transform, peg_hole_mortise_global))

            # Create Peg accessory in global space (positioned at mortise entry)
            peg_accessory = Peg(
                transform=Transform(
                    position=peg_result.mortise_entry_position_global,
                    orientation=peg_result.orientation_global,
                ),
                size=peg_size,
                shape=peg_parameters.shape,
                forward_length=peg_result.peg_depth,
                stickout_length=peg_result.stickout_length,
            )
            joint_accessories[f"peg_{peg_idx}"] = peg_accessory

        if peg_holes_in_tenon_local:
            tenon_cut_with_pegs_csg = CSGUnion(children=[tenon_cut_csg] + peg_holes_in_tenon_local)
            tenon_cut = Cutting(
                timber=tenon_timber,
                maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberReferenceEnd.TOP else None,
                maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberReferenceEnd.BOTTOM else None,
                negative_csg=tenon_cut_with_pegs_csg,
                label="mortise_and_tenon",
            )
        if peg_holes_in_mortise_local:
            mortise_cut_with_pegs_csg = CSGUnion(children=[mortise_negative_csg] + peg_holes_in_mortise_local)
            mortise_cut = Cutting(
                timber=mortise_timber,
                negative_csg=mortise_cut_with_pegs_csg,
                label="mortise_and_tenon",
            )

    tenon_cut_timber = tenon_cut
    mortise_cut_timber = mortise_cut


    #joint_accessories["debug"] = CSGAccessory(
    #    transform = tenon_timber.transform,
    #    positive_csg = notch_geom.butting_timber_relief_negative_CSG if notch_geom is not None else None,
    #)



    return Joint(
        cuttings={
            tenon_timber.ticket.name: tenon_cut_timber,
            mortise_timber.ticket.name: mortise_cut_timber,
        },
        ticket=JointTicket(joint_type="mortise_and_tenon"),
        jointAccessories=joint_accessories,
    ) 


def cut_mortise_and_tenon_joint_on_PAT(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = Rational(0),
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,
    crop_tenon_to_mortise_orientation_on_angled_joints = False,
    use_round_tenon: bool = False,
) -> Joint:
    """
    Creates a mortise and tenon joint for plane-aligned timbers (PAT).

    PAT (plane-aligned timbers) means both timbers lie in the same plane. The timbers may
    meet at any angle — use `cut_mortise_and_tenon_joint_on_FAT` for the standard 90-degree
    case.

    Like the generic `cut_mortise_and_tenon_joint`, but accepts `mortise_shoulder_inset`
    measured from the mortise entry face surface (the intuitive user-facing parameter),
    converting it internally to `mortise_shoulder_distance_from_centerline`.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must satisfy arrangement.check_plane_aligned().
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length: Length of the tenon extending from the mortise entry face. For angled
            joints, set this slightly longer than expected.
        mortise_depth: Depth of the mortise (None = through mortise).
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional).
        crop_tenon_to_mortise_orientation_on_angled_joints: If True, the tenon tip is cropped
            to the mortise hole boundary. If False, mortise depth is measured along the tenon axis.

    Returns:
        Joint object containing the two CutTimbers and any accessories.

    Raises:
        CheckFailure: If the arrangement is not plane-aligned.
    """

    require_check(arrangement.check_plane_aligned())

    # -------------------------------------------------------------------------
    # Step 2: Determine which face of the mortise timber the tenon enters from
    # -------------------------------------------------------------------------
    tenon_end_direction = arrangement.butt_timber.get_face_direction_global(
        TimberFace.TOP if arrangement.butt_timber_end == TimberReferenceEnd.TOP else TimberFace.BOTTOM
    )
    mortise_face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    
    mortise_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=arrangement.receiving_timber,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline=mortise_shoulder_distance_from_centerline,
        tenon_position=tenon_position,
        wedge_parameters=wedge_parameters,
        peg_parameters=peg_parameters,
        crop_tenon_to_mortise_orientation_on_angled_joints=crop_tenon_to_mortise_orientation_on_angled_joints,
        use_round_tenon=use_round_tenon,
    )

    

def cut_mortise_and_tenon_joint_on_FAT(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = Rational(0),
    wedge_parameters: Optional[WedgeParameters] = None,
    peg_parameters: Optional[SimplePegParameters] = None,
    use_round_tenon: bool = False,
) -> Joint:
    """
    Creates a mortise and tenon joint for face-aligned orthogonal timbers (FAT).

    FAT (face-aligned and orthogonal timbers) means both timbers are face-aligned
    (orientations related by 90-degree rotations) and their length axes are perpendicular.
    This is the standard configuration for timber-frame T-joints and corners. For angled
    joints in the same plane, use `cut_mortise_and_tenon_joint_on_PAT`.

    This is a stricter variant of `cut_mortise_and_tenon_joint_on_PAT` that enforces
    perpendicularity and does not support crop_tenon_to_mortise_orientation_on_angled_joints.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must satisfy arrangement.check_face_aligned_and_orthogonal().
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length: Length of the tenon extending from the mortise entry face.
        mortise_depth: Depth of the mortise (None = through mortise).
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional).

    Returns:
        Joint object containing the two CutTimbers and any accessories.

    Raises:
        CheckFailure: If the arrangement is not face-aligned and orthogonal.
    """

    require_check(arrangement.check_face_aligned_and_orthogonal())

    return cut_mortise_and_tenon_joint_on_PAT(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        tenon_position=tenon_position,
        mortise_shoulder_inset=mortise_shoulder_inset,
        wedge_parameters=wedge_parameters,
        peg_parameters=peg_parameters,
        use_round_tenon=use_round_tenon,
    )

def cut_round_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_distance_from_centerline: Numeric = Rational(0),
) -> Joint:
    """
    Creates a simplified round mortise and tenon joint with any orientation.

    This is a convenience wrapper around `cut_mortise_and_tenon_joint` for
    common round tenon use cases with a single diameter parameter instead of V2 tenon_size.
    Allows any timber arrangement orientation.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
        diameter: Diameter of the round tenon and mortise.
        tenon_length: Length of the tenon extending from the mortise entry face.
        mortise_depth: Depth of the mortise (None = through mortise).
        mortise_shoulder_distance_from_centerline: Signed distance from the mortise centerline
            to the shoulder plane. 0 = shoulder at centerline.

    Returns:
        Joint object containing the two CutTimbers, all in global space.
    """
    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([diameter, diameter]),
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline=mortise_shoulder_distance_from_centerline,
        use_round_tenon=True,
    )


def cut_round_mortise_and_tenon_joint_on_PAT(
    arrangement: ButtJointTimberArrangement,
    diameter: Numeric,
    tenon_length: Numeric,
    mortise_depth: Optional[Numeric] = None,
    mortise_shoulder_inset: Numeric = Rational(0),
) -> Joint:
    """
    Creates a simplified round mortise and tenon joint for plane-aligned timbers (PAT).

    This is a convenience wrapper around `cut_mortise_and_tenon_joint` for
    round tenon use cases with a single diameter parameter.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
                     Must satisfy arrangement.check_plane_aligned().
        diameter: Diameter of the round tenon and mortise.
        tenon_length: Length of the tenon extending from the mortise entry face.
        mortise_depth: Depth of the mortise (None = through mortise).
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.

    Returns:
        Joint object containing the two CutTimbers, all in global space.
    """
    require_check(arrangement.check_plane_aligned())

    # -------------------------------------------------------------------------
    # Step 2: Determine which face of the mortise timber the tenon enters from
    # -------------------------------------------------------------------------
    tenon_end_direction = arrangement.butt_timber.get_face_direction_global(
        TimberFace.TOP if arrangement.butt_timber_end == TimberReferenceEnd.TOP else TimberFace.BOTTOM
    )
    mortise_face = arrangement.receiving_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    
    mortise_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=arrangement.receiving_timber,
    )

    return cut_mortise_and_tenon_joint(
        arrangement=arrangement,
        tenon_size=Matrix([diameter, diameter]),
        tenon_length=tenon_length,
        mortise_depth=mortise_depth,
        mortise_shoulder_distance_from_centerline=mortise_shoulder_distance_from_centerline,
        use_round_tenon=True,
    )


# ============================================================================
# Wedged Half-Dovetail Mortise and Tenon Joint
# ============================================================================


# TODO notching on this function works however the wedge won't fit so the wedge hole needs to be made bigger
def cut_wedged_half_dovetail_mortise_and_tenon_joint(
    arrangement: ButtJointTimberArrangement,
    dovetail_top_side_on_butt_timber: TimberLongFace,
    tenon_size: V2,
    tenon_depth: Numeric,
    dovetail_depth: Numeric,
    tenon_lateral_offset: Numeric = Rational(0),
    receiving_timber_mortise_extra_depth: Numeric = Rational(0),
    mortise_shoulder_inset: Numeric = Rational(0),
    wedge_accessory_parameters: Optional[DovetailTenonWedgeAccessoryParameters] = None,
) -> Joint:
    """
    Create a half-dovetail mortise-and-tenon joint (with an optional wedge accessory).

    Built on top of `dovetail_tenon_geometry`. The "top" of the dovetail is flush with
    `dovetail_top_side_on_butt_timber`; the opposite side slopes outward by `dovetail_depth`
    over `tenon_depth` to give the joint its mechanical pull-out resistance.

    Args:
        arrangement: Butt joint arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must be face-aligned and orthogonal.
        dovetail_top_side_on_butt_timber: Which face of the butt timber the dovetail's flat
            "top" is flush with. The opposite face is the sloped side.
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
            `dovetail_top_side_on_butt_timber` side of the tenon and a matching slot is cut
            into the receiving timber.

    Returns:
        Joint object with cuts on both timbers and (optionally) a "wedge" accessory.
    """
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    warn_if_arrangement_timbers_imperfect(arrangement)

    # Convert the user-facing `mortise_shoulder_inset` (measured inward from the mortise
    # entry face) into the signed-from-centerline distance that `compute_butt_joint_shoulder`
    # expects. This mirrors how `cut_mortise_and_tenon_joint_on_PAT/FAT` handle the inset.
    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    mortise_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=mortise_timber,
    )

    # The shoulder marking space's up_direction only orients the marking frame; the geometry
    # function derives its own frame from `dovetail_top_side_on_butt_timber`. Pick the butt
    # timber's height direction (a stable, non-parallel choice for any orthogonal arrangement).
    up_direction = tenon_timber.get_height_direction_global()

    shoulder_result = compute_butt_joint_shoulder(
        arrangement=arrangement,
        distance_from_centerline=mortise_shoulder_distance_from_centerline,
        up_direction=up_direction,
    )

    geo = dovetail_tenon_geometry(
        arrangement=arrangement,
        shoulder_result=shoulder_result,
        dovetail_top_side_on_butt_timber=dovetail_top_side_on_butt_timber,
        tenon_size=tenon_size,
        tenon_depth=tenon_depth,
        dovetail_depth=dovetail_depth,
        tenon_lateral_offset=tenon_lateral_offset,
        receiving_timber_mortise_extra_depth=receiving_timber_mortise_extra_depth,
        wedge_accessory_parameters=wedge_accessory_parameters,
    )

    # The CSGs from dovetail_tenon_geometry are in global space. Adopt them into each
    # timber's local frame for cutting.
    tenon_negative_local = adopt_csg(None, tenon_timber.transform, geo.tenon_negative_csg)
    mortise_negative_local = adopt_csg(None, mortise_timber.transform, geo.mortise_negative_csg)

    # Shoulder notch on the receiving timber (and matching relief on the butting
    # timber) when the shoulder is inset from the entry face. For face-aligned
    # orthogonal arrangements the approach angle is pi/2 (no relief walls).
    notch_geom = chop_notch_for_butt_joint_arrangement(
        arrangement,
        mortise_shoulder_distance_from_centerline,
        notch_wall_min_relief_cut_angle=degrees(45),
    )
    if notch_geom is not None:
        mortise_negative_local = CSGUnion(
            children=[
                mortise_negative_local,
                notch_geom.receiving_timber_notch_negative_CSG,
            ]
        )
        if notch_geom.butting_timber_relief_negative_CSG is not None:
            # Add the relief volume to the tenon negative CSG so the butting timber
            # gets carved away against the receiving timber's notch walls.
            tenon_negative_local = CSGUnion(
                children=[
                    tenon_negative_local,
                    notch_geom.butting_timber_relief_negative_CSG,
                ]
            )

    tenon_tip_position_global = (
        shoulder_result.marking_space.transform.position
        + shoulder_result.butt_direction * tenon_depth
    )
    tip_position_local = tenon_timber.transform.global_to_local(tenon_tip_position_global)
    tip_z_local = tip_position_local[2]

    tenon_cut = Cutting(
        timber=tenon_timber,
        maybe_top_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberReferenceEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=tip_z_local if tenon_end == TimberReferenceEnd.BOTTOM else None,
        negative_csg=tenon_negative_local,
        label="wedged_half_dovetail_mortise_and_tenon",
    )

    mortise_cut = Cutting(
        timber=mortise_timber,
        negative_csg=mortise_negative_local,
        label="wedged_half_dovetail_mortise_and_tenon",
    )

    joint_accessories = {}
    if geo.wedge_accessory_csg is not None:
        joint_accessories["wedge"] = geo.wedge_accessory_csg

    return Joint(
        cuttings={
            tenon_timber.ticket.name: tenon_cut,
            mortise_timber.ticket.name: mortise_cut,
        },
        ticket=JointTicket(joint_type="wedged_half_dovetail_mortise_and_tenon"),
        jointAccessories=joint_accessories,
    )
