"""
Kumiki - Mortise and tenon joint construction functions
Contains mortise-and-tenon joint implementations: plain (generic/plane-aligned/face-aligned/round),
corner, tusked, and wedged half-dovetail variants. Split out of butt_joints.py.
"""

from __future__ import annotations  # Enable deferred annotation evaluation

import warnings
from dataclasses import replace
from functools import wraps

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from .shavings import *
from .shavings.relief import warn_if_arrangement_timbers_imperfect, chop_shoulder_notch_on_timber_face, ShoulderReliefCSGGeometry, chop_shoulder_notch_aligned_with_timber, chop_butt_joint_shoulder_notch_relief_4sided, chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided, does_shoulder_plane_need_notching, ButtJointScribeReliefConfig, ButtJointNotchReliefConfig, NotchFrom, chop_scribe_relief_and_apply_for_butt_joint_arrangement
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
    get_center_point_on_face_global,
    Space,
)
from kumiki.timber_shavings import are_timbers_plane_aligned
from kumiki.cutcsg import CutCSG, CutCSGLabel, RectangularPrism, HalfSpace, Difference, Intersection, SolidUnion, adopt_csg, PrismFace, Cylinder, HalfSpaceFeature, SimpleRectangularPrismFeature
from .shavings.build_a_butt import (
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
    locate_mortise_timber_shoulder_plane_from_centerplane_towards_long_face,
    resolve_parallel_shoulder_face,
    PegPositionResult,
    PegPositionSpace,
    SimplePegParameters,
    compute_peg_positions,
    compute_butt_joint_shoulder,
    dovetail_tenon_geometry,
    DovetailTenonGeometeryResult,
    DovetailTenonWedgeAccessoryParameters,
    tusk_tenon_geometry,
    TuskTenonGeometryResult,
)
# safe_dot_product/safe_norm/safe_transform_vector are rational-safe wrappers defined in
# butt_joints.py; convert_mortise_shoulder_inset_to_centerline_distance and
# _apply_scribe_relief_if_configured stay there too since cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers
# (a non-mortise-and-tenon joint) also depends on them -- moving them here would create a
# circular import between the two modules.
from .butt_joints import (
    safe_dot_product,
    safe_norm,
    safe_transform_vector,
    convert_mortise_shoulder_inset_to_centerline_distance,
    _apply_scribe_relief_if_configured,
)


# Everything this joint removes from one timber lives under a single node named
# for the side of the joint that timber plays. Both cuttings carry the same
# "mortise_and_tenon" label from the Cutting itself, so this is what tells the
# two apart in the tree.
TENON_CUT_LABEL = CutCSGLabel("tenon_cut")
MORTISE_CUT_LABEL = CutCSGLabel("mortise_cut")


def _union_into_cut(existing: CutCSG, additions: List[CutCSG], label: CutCSGLabel) -> SolidUnion:
    """Add more removed material to a timber's cut, as one labelled union.

    Extends the union when one is already there rather than nesting a second
    node with the same label inside it: a cutting that gains both a shoulder
    relief and peg holes should still read as one `tenon_cut`, not as
    `tenon_cut` within `tenon_cut`.
    """
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
    expand_mortise: Numeric = scalar(0)


class InsetShoulderReliefStyle(Enum):
    """
    How an inset shoulder is fitted -- the mortise timber has to give up the
    material the tenon timber's shank occupies past the shoulder plane.

    Only cuts the mortise timber where that material meets its PTW, and only cuts
    the tenon timber past the shoulder plane. `relief` covers everything outside
    that, including either timber's rough fringe at the entry face.
    """
    # Fit the tenon's ROUGH shank, so the pocket carries the rough margin.
    Rough = 0
    # Fit the tenon's PERFECT shank and take the tenon's own rough excess off the
    # tenon instead.
    PerfectOnly = 1
    # Skip the step entirely, for callers computing their own inset-shoulder relief.
    NoRelief = 2


# ============================================================================
# Mortise and Tenon Joint Construction Functions
# ============================================================================


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

    This is the generic implementation used by all specialized variants
    (`cut_mortise_and_tenon_joint_on_plane_aligned_timbers`, `cut_mortise_and_tenon_joint_on_face_aligned_timbers`).
    Prefer those variants for common cases.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length: Length of the tenon extending from the mortise entry face. For angled
            joints, set this slightly longer than expected to ensure full penetration.
        mortise_depth: Depth of the mortise (None = through mortise, only valid when
            bore_mortise_perpendicular_to_face is False).
            Measures along the tenon axis if bore_mortise_perpendicular_to_face is False; along the mortise face axis if True.
        mortise_shoulder_distance_from_centerline_or_centerplane: Signed distance from the mortise
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
        bore_mortise_perpendicular_to_face: If True, the mortise is bored straight into the
            receiving face (perpendicular to it) rather than along the tenon's own axis, and
            the tenon is cropped to fit — its depth along the mortise face axis equals
            mortise_depth (which must be provided) and its tip is trimmed to the mortise hole
            boundary. If False (default), the mortise hole and mortise_depth both follow the
            tenon's own axis from the shoulder, so the mortise face aligns with the tenon. Arrangement MUST be plane aligned.
        use_round_tenon: If True, creates a round (cylindrical) tenon and mortise instead of
            rectangular. When True, tenon_size[0] and tenon_size[1] must be equal (no ovals),
            and peg_parameters must be None. Default is False.
        relief: Relief configuration for imperfect timbers. Either:
            - ButtJointScribeReliefConfig (see `chop_scribe_relief_and_apply` in relief.py):
              scribes one timber's imperfect (beyond-perfect-within) material onto the other
              and cuts it away. Defaults to scribing the tenon (butt) timber onto the mortise
              (receiving) timber. This is separate from -- and applied on top of -- the
              inset-shoulder relief.
            - ButtJointNotchReliefConfig: does a 4 sided notch from the shoulder plane and
              IS the inset-shoulder relief, so inset_shoulder_relief_style is ignored (pass
              NoRelief, or it warns).
            - None skips relief but still applies inset_shoulder_relief_style if needed.
        inset_shoulder_relief_style: how the tenon timber's shank past the shoulder plane is
            fitted into the mortise timber. Cuts the mortise timber only where that material
            meets its PTW, and cuts the tenon timber only past the shoulder plane. Use
            `relief` for the rest.
            - Rough (default): fits the tenon timber's ROUGH shank into the mortise timber.
            - PerfectOnly: fits its PERFECT shank, and takes the tenon's own rough excess
              off the tenon so it still seats.
            - NoRelief: skip the step. Used by
              cut_mortise_and_tenon_joint_on_plane_aligned_timbers, which computes its own.

    Returns:
        Joint object containing the two CutTimbers and any accessories, all in global space.
    """
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    # Default tenon_position to centered (0, 0)
    if tenon_position is None:
        tenon_position = Matrix([scalar(0), scalar(0)])

    # Assert if the tenon dimensions after offsetting exceed the perfect timber within dimension of the tenon timber
    from kumiki.rule import safe_compare, Comparison
    
    # Check local X direction (vertical)
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
    
    # Check local Y direction (horizontal)
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

    # Validation for round tenon mode
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
        # bore_mortise_perpendicular_to_face only works on plane aligned arrangements
        require_check(arrangement.check_plane_aligned())

    # TODO default mortise depth if mortise_depth is None

    # -------------------------------------------------------------------------
    # Step 3: Shoulder plane from centerline toward tenon
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Step 4: Define marking_space (global Space at shoulder, toward tenon end)
    # -------------------------------------------------------------------------
    tenon_orientation = compute_timber_orientation(
        safe_normalize_vector(tenon_end_direction), tenon_timber.get_width_direction_global()
    )
    tenon_base_transform = Transform(position=marking_origin_global, orientation=tenon_orientation)
    marking_space: Space = Space(transform=tenon_base_transform)

    # -------------------------------------------------------------------------
    # Step 5: Determine the angle between the mortise entry direction and tenon
    # -------------------------------------------------------------------------
    mortise_face_normal = shoulder_plane.normal
    cos_angle = safe_dot_product(
        safe_normalize_vector(mortise_face_normal), safe_normalize_vector(tenon_end_direction)
    )

    # -------------------------------------------------------------------------
    # Tenon prism (origin at marking_space) and shoulder half-space
    # -------------------------------------------------------------------------

    # Back-extension from shoulder so prism fully contains tenon at oblique angles.
    #
    # None of it on a square joint. sin_angle_sq is zero exactly when the tenon
    # runs along the mortise face normal, which is to say the joint is square,
    # and there the prism meets the shoulder square-on and needs no reach behind
    # it. That case used to divide by a guard against zero instead, which gave
    # the largest extension possible where the least was wanted -- ten thousand
    # times the tenon, a cutter hundreds of metres long. It cut the same joint,
    # since the shoulder trims whatever reaches past it, so nothing looked
    # wrong until something asked one of its faces where it was.
    sin_angle_sq = scalar(1) - cos_angle * cos_angle
    back_extension = (
        scalar(0) if safe_zero_test_sq(sin_angle_sq)
        else max(tenon_size[0], tenon_size[1]) / sqrt(Abs(sin_angle_sq))
    )

    tenon_tip_name = "tenon_top" if tenon_end == TimberEnd.TOP else "tenon_bot"

    if use_round_tenon:
        # Round tenon: use cylinder with diameter = tenon_size[0]
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
                SimpleRectangularPrismFeature("tenon_right", face=PrismFace.RIGHT),
                SimpleRectangularPrismFeature("tenon_left", face=PrismFace.LEFT),
                SimpleRectangularPrismFeature("tenon_front", face=PrismFace.FRONT),
                SimpleRectangularPrismFeature("tenon_back", face=PrismFace.BACK),
                SimpleRectangularPrismFeature(tenon_tip_name, face=PrismFace.TOP),
            ],
            label=CutCSGLabel("tenon"),
        )

    tenon_prism_cropping_csgs: Optional[List[CutCSG]] = None
    # why did the agent do safe_zero_test(scalar(1) - cos_angle * cos_angle)...
    do_lengthwise_cropping = bore_mortise_perpendicular_to_face and not safe_zero_test(scalar(1) - cos_angle * cos_angle)
    if do_lengthwise_cropping:
        # do_lengthwise_cropping implies bore_mortise_perpendicular_to_face, which the
        # require_check above already guarantees means mortise_depth is not None.
        assert mortise_depth is not None
        # TODO you could support this on non plane-aligned timbers as well but you need to choose a different plane to do the cropping
        # Compute mortise_face locally — cropping is only used for plane-aligned timbers
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        mortise_face_direction = mortise_timber.get_face_direction_global(mortise_face)

        mortise_oblique_end = mortise_timber.get_closest_oriented_end_face_from_global_direction(tenon_end_direction)
        joint_angle_axis_face = tenon_timber.get_closest_oriented_long_face_from_global_direction(mortise_timber.get_face_direction_global(mortise_oblique_end))
        joint_angle_axis_index = tenon_timber.get_size_index_in_long_face_normal_axis(joint_angle_axis_face)

        mortise_hole_length_oblique_direction = mortise_timber.get_face_direction_global(mortise_oblique_end)
        end_crop_distance = tenon_size[joint_angle_axis_index] / sin_angle_safe / scalar(2)

        # Crop 1: far end of prism perpendicular to mortise face
        mortise_hole_end_crop_global = HalfSpace(
            normal=mortise_hole_length_oblique_direction,
            offset=end_crop_distance + safe_dot_product(mortise_hole_length_oblique_direction, shoulder_point_global),
            label=CutCSGLabel("tenon_crop_to_mortise_length"),
        )

        # Crop 2: depth of tenon — plane parallel to the mortise face surface,
        # mortise_depth measured from the face inward.
        mortise_depth_crop_global = HalfSpace(
            normal=-mortise_face_direction,
            offset=mortise_depth - safe_dot_product(mortise_face_direction, get_center_point_on_face_global(mortise_face, mortise_timber)),
            label=CutCSGLabel("tenon_crop_to_mortise_depth"),
        )

        tenon_prism_cropping_csgs = [mortise_hole_end_crop_global, mortise_depth_crop_global]

    # Shoulder half-space: plane through centerline ∩ shoulder (marking origin), normal = shoulder plane normal
    shoulder_half_space_global = HalfSpace(
        normal=-shoulder_plane.normal,
        offset=safe_dot_product(-shoulder_plane.normal, marking_space.transform.position),
        # Declared so the shoulder can be selected and, more to the point, so it
        # forms edges with the timber's own faces: shoulder x rough.front and
        # its three siblings are the line you knife around the timber.
        _features=[HalfSpaceFeature("shoulder")],
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

    # Convert from global to tenon timber local (orig_timber=None => CSG is in global space)
    tenon_prism_local = adopt_csg(None, tenon_timber.transform, tenon_prism_cropped)
    shoulder_half_space_local = adopt_csg(None, tenon_timber.transform, shoulder_half_space_global)

    # -------------------------------------------------------------------------
    # mortise hole
    # -------------------------------------------------------------------------

    mortise_hole_prism_global = None

    if do_lengthwise_cropping:
        if use_round_tenon:
            # Round mortise hole at an angle: use cylinder
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
                tenon_size[joint_angle_axis_index] / sin_angle_safe,
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
                # The prism's TOP is the deep end of the pocket: its floor.
                SimpleRectangularPrismFeature("mortise_bottom", face=PrismFace.TOP),
            ],
                label=CutCSGLabel("mortise_hole"),
            )
    else:
        if use_round_tenon:
            # Round mortise hole: use cylinder with same diameter as tenon
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
                # The prism's TOP is the deep end of the pocket: its floor.
                SimpleRectangularPrismFeature("mortise_bottom", face=PrismFace.TOP),
            ],
                label=CutCSGLabel("mortise_hole"),
            )

    # -------------------------------------------------------------------------
    # shoulder notch on mortise timber and matching relief on tenon timber
    # (when shoulder is inset from the mortise entry face)
    # -------------------------------------------------------------------------

    if isinstance(relief, ButtJointNotchReliefConfig):
        assert relief.notch_from == NotchFrom.Shoulder, (
            "cut_mortise_and_tenon_joint only supports "
            "ButtJointNotchReliefConfig(notch_from=NotchFrom.Shoulder) -- "
            "notch_from=NotchFrom.Face is only supported by "
            "cut_mortise_and_tenon_joint_on_plane_aligned_timbers / "
            "_on_face_aligned_timbers, which compute their own face-anchored relief "
            "on top of this function's default shoulder scribe."
        )
        if inset_shoulder_relief_style is not InsetShoulderReliefStyle.NoRelief:
            warnings.warn(
                "inset_shoulder_relief_style is ignored when relief is a "
                "ButtJointNotchReliefConfig -- the 4-sided notch is itself the "
                "inset-shoulder relief. Pass InsetShoulderReliefStyle.NoRelief.",
                stacklevel=2,
            )
        # The 4-sided notch relief IS the inset-shoulder relief (built directly from the
        # shoulder line), so the scribe-based housing cut below would be redundant --
        # skip straight to it instead.
        shoulder_notch_relief_geom: ShoulderReliefCSGGeometry | None = chop_butt_joint_shoulder_notch_relief_4sided(
            arrangement,
            mortise_shoulder_distance_from_centerline_or_centerplane,
        )
    elif inset_shoulder_relief_style is InsetShoulderReliefStyle.NoRelief:
        # The caller computes its own inset-shoulder relief and unions it in, so running
        # this step too would duplicate it rather than replace it.
        shoulder_notch_relief_geom = None
    elif does_shoulder_plane_need_notching(
        arrangement,
        mortise_shoulder_distance_from_centerline_or_centerplane,
        # PTW, not rough: this step cuts the mortise only inside its PTW, so a shoulder
        # landing in the rough fringe has nothing here to remove.
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
        # Bare prism, not get_perfect_timber_within_csg_local(): that one carries the
        # reserved ptw.* face tags, and a timber may only ever own one set of those.
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
        # Difference against the shoulder half-space keeps the tenon's shank -- the part
        # past the shoulder, which is what the mortise has to house. Cropping to the
        # mortise's PTW leaves its rough fringe for `relief`.
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
            # The pocket above is only the PERFECT shank, so the tenon's own rough excess
            # inside it has to come off the tenon for the joint to seat.
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

    # -------------------------------------------------------------------------
    # make the final cut CSGs
    # -------------------------------------------------------------------------

    tenon_cut_csg = Difference(
        base=shoulder_half_space_local,
        subtract=[tenon_prism_local],
        label=CutCSGLabel("tenon_waste"),
    )
    if shoulder_notch_relief_geom is not None and shoulder_notch_relief_geom.butting_timber_relief_negative_CSG is not None:
        # The relief CSG occupies its own depth range (from the shoulder outward, toward
        # and past the receiving timber's entry face) which is DISJOINT from
        # shoulder_half_space_local's domain (behind the shoulder) -- it's an ADDITIONAL
        # region of material to remove, not something to subtract from that half-space
        # (which would have no effect, since they don't overlap).
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
                # Cylinder axis is the Z column of the orientation in global space.
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
            # Assembly: the peg backs out along its drill axis; it locks the
            # joint, so it pops (suborder 0) before the tenon slides (suborder 1).
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
        # ButtJointNotchReliefConfig was already fully applied above (as the shoulder
        # notch/relief itself), so don't hand it to the scribe-relief mechanism too.
        relief=relief if isinstance(relief, ButtJointScribeReliefConfig) else None,
        butt_cut=tenon_cut_no_relief,
        receiving_cut=mortise_cut_no_relief,
    )

    # Assembly: the tenon backs out of the mortise along the tenon axis; the
    # mortise timber's view of the same separation is the inverse direction.
    # Locking accessories (pegs) pop first at suborder -1, so the timbers
    # slide at the default suborder 0. with_order(n) preserves suborders, so
    # the peg-before-slide sequencing survives frame-level ordering.
    tenon_freedom = AssemblyFreedom.translation(-tenon_length_direction_global, freed_after=tenon_length)
    mortise_freedom = AssemblyFreedom.translation(tenon_length_direction_global, freed_after=tenon_length)

    if bore_mortise_perpendicular_to_face:
        # The mortise hole is bored straight into the receiving face rather
        # than along the tenon's own axis, so the embedded tenon stub sits in
        # a straight-walled pocket. That gives the mortise timber a second
        # way to escape: sliding straight out along the face normal (instead
        # of along the tenon axis) clears the pocket after mortise_depth of
        # travel, since the pocket has constant cross-section along that axis.
        assert mortise_depth is not None  # enforced above: required when bore_mortise_perpendicular_to_face is True
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
    """
    Resolve a tenon's (X, Y) cross-sectional size, either from the raw local-space
    tenon_size or from the joint-relative width/height pair.

    tenon_width_relative_to_joint is the tenon dimension along the axis parallel to
    the joint plane (the plane the two arrangement timbers share); tenon_height_relative_to_joint
    is the dimension along the axis perpendicular to that plane. Exactly one of
    tenon_size or the (width, height) pair must be provided.
    """
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

    Plane-aligned timbers means both timbers lie in the same plane. The timbers may
    meet at any angle — use `cut_mortise_and_tenon_joint_on_face_aligned_timbers` for the standard 90-degree
    case.

    Like the generic `cut_mortise_and_tenon_joint`, but accepts `mortise_shoulder_inset`
    measured from the mortise entry face surface (the intuitive user-facing parameter),
    converting it internally to `mortise_shoulder_distance_from_centerline_or_centerplane`.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must satisfy arrangement.check_plane_aligned().
        tenon_length: Length of the tenon extending from the mortise entry face. For angled
            joints, set this slightly longer than expected.
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
            Deprecated in favor of tenon_width_relative_to_joint / tenon_height_relative_to_joint;
            provide this or that pair, not both.
        tenon_width_relative_to_joint: Tenon dimension along the axis parallel to the joint
            plane (the plane shared by the two arrangement timbers). Must be provided together
            with tenon_height_relative_to_joint, and only when tenon_size is not provided.
        tenon_height_relative_to_joint: Tenon dimension along the axis perpendicular to the
            joint plane. Must be provided together with tenon_width_relative_to_joint, and only
            when tenon_size is not provided.
        mortise_depth: Depth of the mortise (None = through mortise, only valid when
            bore_mortise_perpendicular_to_face is False).
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional).
        bore_mortise_perpendicular_to_face: If True, the mortise is bored straight into the
            receiving face and the tenon tip is cropped to the mortise hole boundary; mortise_depth
            must be provided. If False, mortise depth is measured along the tenon axis.
        relief: Relief configuration for imperfect timbers. Either:
            - ButtJointScribeReliefConfig (default): scribes the tenon (butt) timber onto
              the mortise (receiving) timber.
            - ButtJointNotchReliefConfig: since this arrangement is already known to be
              plane-aligned, use chop_butt_joint_shoulder_notch_relief_on_plane_aligned_timbers_2sided
              instead of the fully-general 4-sided notch cut_mortise_and_tenon_joint.
                - NotchFrom.Shoulder (default): notching starts from the possible inset shoulder
                - NotchFrom.Face: notching starts from the PTW entry face of the mortise timber
            - None: skip relief entirely

    Returns:
        Joint object containing the two CutTimbers and any accessories.

    Raises:
        CheckFailure: If the arrangement is not plane-aligned.
        KumikiArrangementError: If tenon sizing args are not provided as exactly one of
            tenon_size or (tenon_width_relative_to_joint, tenon_height_relative_to_joint).
    """

    require_check(arrangement.check_plane_aligned())

    tenon_size = _resolve_tenon_size_relative_to_joint(
        arrangement=arrangement,
        tenon_size=tenon_size,
        tenon_width_relative_to_joint=tenon_width_relative_to_joint,
        tenon_height_relative_to_joint=tenon_height_relative_to_joint,
    )

    # -------------------------------------------------------------------------
    # Step 2: Determine which face of the mortise timber the tenon enters from
    # -------------------------------------------------------------------------
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

    # notch_from=Face still fits the joint at the real (inset) shoulder via the default
    # scribe-based housing cut below (relief=None, inset_shoulder_relief_style=PerfectOnly) --
    # only the notch relief geometry itself (computed further down) is anchored to the
    # face instead of the real shoulder. PerfectOnly (not Rough) because the 2-sided notch
    # unioned in below already covers the rough-stock margin at the face; scribing the
    # housing cut with the tenon's ROUGH cross-section too would double up on that margin.
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
        # relief=None whenever ButtJointNotchReliefConfig is passed (both notch_from styles):
        # this wrapper computes its own shoulder relief below and unions it in itself, so the
        # inner call's whole-body scribe relief step must stay off either way.
        relief=None if isinstance(relief, ButtJointNotchReliefConfig) else relief,
        inset_shoulder_relief_style=(
            InsetShoulderReliefStyle.PerfectOnly if notch_from_face
            # notch_from=Shoulder: this wrapper's own 2-sided relief (below) IS the shoulder
            # relief, so skip the inner call's default shoulder scribe entirely.
            else InsetShoulderReliefStyle.NoRelief if isinstance(relief, ButtJointNotchReliefConfig)
            else InsetShoulderReliefStyle.Rough
        ),
    )

    if isinstance(relief, ButtJointNotchReliefConfig):
        # notch_from=Face anchors the notch relief itself to the mortise entry face --
        # i.e. as if mortise_shoulder_inset were 0 -- regardless of the real inset used above.
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

    Face-aligned orthogonal timbers means both timbers are face-aligned
    (orientations related by 90-degree rotations) and their length axes are perpendicular.
    This is the standard configuration for timber-frame T-joints and corners. For angled
    joints in the same plane, use `cut_mortise_and_tenon_joint_on_plane_aligned_timbers`.

    This is a stricter variant of `cut_mortise_and_tenon_joint_on_plane_aligned_timbers` that enforces
    perpendicularity and does not support bore_mortise_perpendicular_to_face.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must satisfy arrangement.check_face_aligned_and_orthogonal().
        tenon_length: Length of the tenon extending from the mortise entry face.
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
            Deprecated in favor of tenon_width_relative_to_joint / tenon_height_relative_to_joint;
            provide this or that pair, not both.
        tenon_width_relative_to_joint: Tenon dimension along the axis parallel to the joint
            plane (the plane shared by the two arrangement timbers). Must be provided together
            with tenon_height_relative_to_joint, and only when tenon_size is not provided.
        tenon_height_relative_to_joint: Tenon dimension along the axis perpendicular to the
            joint plane. Must be provided together with tenon_width_relative_to_joint, and only
            when tenon_size is not provided.
        mortise_depth: Depth of the mortise (None = through mortise).
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        wedge_parameters: Wedge configuration (not currently used).
        peg_parameters: Peg configuration for draw-bore tightening (optional).
        relief: Relief configuration for imperfect timbers -- see
            cut_mortise_and_tenon_joint_on_plane_aligned_timbers (this function just
            forwards to it, since it's a strictly narrower/stricter special case).

    Returns:
        Joint object containing the two CutTimbers and any accessories.

    Raises:
        CheckFailure: If the arrangement is not face-aligned and orthogonal.
        KumikiArrangementError: If tenon sizing args are not provided as exactly one of
            tenon_size or (tenon_width_relative_to_joint, tenon_height_relative_to_joint).
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

    This is a convenience wrapper around `cut_mortise_and_tenon_joint` for
    common round tenon use cases with a single diameter parameter instead of V2 tenon_size.
    Allows any timber arrangement orientation.

    Args:
        arrangement: Butt joint timber arrangement (butt_timber = tenon, receiving_timber = mortise).
        diameter: Diameter of the round tenon and mortise.
        tenon_length: Length of the tenon extending from the mortise entry face.
        mortise_depth: Depth of the mortise (None = through mortise).
        mortise_shoulder_distance_from_centerline_or_centerplane: Signed distance from the mortise centerline
            to the shoulder plane. 0 = shoulder at centerline.

    Returns:
        Joint object containing the two CutTimbers, all in global space.
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
    Args:
        arrangement: timber1 is the tenon timber, timber2 is the mortise timber, front_face_on_timber1 is the peg entry face
        tenon_width_relative_to_joint: the "width" of the tenon which is in the axis that's parallel to the joint plane
        tenon_height_relative_to_joint: the "height" of the tenon which is in the axis that's perpendicular to the joint plane
        tenon_length: see cut_mortise_and_tenon_joint
        tenon_distance_from_end: distance, along the axis parallel to the joint plane, from the face on
            timber1 (the tenon timber) that aligns with timber2's end face to the near edge of the
            tenon. Defaults to 0, meaning the tenon sits flush with that face -- the side of the tenon
            is exposed, i.e. a tongue and fork corner joint. Positive values inset the tenon, leaving a
            "horn" of timber2 material past the joint on that side (a blind mortise corner joint).
        tenon_lateral_offset: lateral offset of the tenon in the axis that's perpendicular to the joint plane, sign is based off the matching local axis of the tenon timber
        mortise_depth: see cut_mortise_and_tenon_joint
        mortise_shoulder_inset: see cut_mortise_and_tenon_joint
        peg_parameters: see cut_mortise_and_tenon_joint
        relief: see cut_mortise_and_tenon_joint

    Returns:

    Raises:
        KumikiArrangementError: If the arrangement is not plane-aligned.
    """
    require_check(arrangement.check_plane_aligned())

    tenon_timber = arrangement.timber1
    mortise_timber = arrangement.timber2
    tenon_end = arrangement.timber1_end
    mortise_end = arrangement.timber2_end

    # -------------------------------------------------------------------------
    # tenon_position: width-axis component (parallel to the joint plane) is
    # derived from tenon_distance_from_end, measured from the tenon timber's
    # own face that aligns with the mortise timber's end face. Height-axis
    # component (perpendicular to the joint plane) is tenon_lateral_offset directly.
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Corner end cuts: each timber's own stock is trimmed flush with the
    # opposing timber's outer (far) face, so neither timber's material
    # protrudes past the other's boundary at the corner.
    # -------------------------------------------------------------------------
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
    """
    The face the tusk enters from referring to
    ButtJointTimberArrangement.front_face_on_butt_timber
    ButtJointTimberArrangement.top_face_on_butt_timber
    """
    Front = 0
    Top = 1

@dataclass(frozen=True)
class TuskParameters():
    tusk_thickness: Numeric
    tusk_small_width: Numeric
    # defaults to 1/3 of length of the tusk that's in the tenon
    tusk_tip_stickout: Optional[Numeric] = None
    # defaults to 1/3 of length of the tusk that's in the tenon
    tusk_back_stickout: Optional[Numeric] = None
    tusk_angle: Numeric = degrees(10)
    entry_face: TuskEntryFace = TuskEntryFace.Front


def cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_length_past_opposite_shoulder: Numeric,
    # the tusk is always centered on the tenon
    tusk_parameters: TuskParameters,
    tenon_position: Optional[V2] = None,
    mortise_shoulder_inset: Numeric = scalar(0),
    measure_opposite_shoulder_from: MeasureOppositeShoulderFrom = MeasureOppositeShoulderFrom.Perfect,
    # measured inward towards the timber, allowed to be negative as if measure_opposite_shoulder_from is Rough
    opposite_mortise_shoulder_inset: Numeric = scalar(0),
    relief: Union[None, ButtJointScribeReliefConfig] = ButtJointScribeReliefConfig.butt_timber(),
) -> Joint:
    """
    Creates a through mortise-and-tenon joint locked by a tapered crosswise key (a "tusk")
    driven through the protruding tenon, bearing against the receiving timber's exit face.

    The tenon is always a through-tenon: its length is computed as the distance from the
    mortise entry shoulder to an "opposite shoulder" reference on the far side of the
    receiving timber (see measure_opposite_shoulder_from / opposite_mortise_shoulder_inset),
    plus tenon_length_past_opposite_shoulder. The tusk hole is cut through the tenon at that
    opposite-shoulder position, entering from arrangement.front_face_on_butt_timber or
    arrangement.top_face_on_butt_timber (per tusk_parameters.entry_face), centered on the
    tenon.

    Args:
        arrangement: Butt joint arrangement (butt_timber = tenon, receiving_timber = mortise).
            Must satisfy arrangement.check_plane_aligned(), and whichever of
            front_face_on_butt_timber/top_face_on_butt_timber tusk_parameters.entry_face
            selects must be set.
        tenon_size: Cross-sectional size of the tenon (X, Y) in the tenon timber's local space.
        tenon_length_past_opposite_shoulder: How far the tenon (and tusk hole) extends past
            the opposite shoulder reference.
        tusk_parameters: Tusk shape parameters.
        tenon_position: Offset of the tenon center from the timber centerline in the tenon's
            local cross-section. (0, 0) = centered on the centerline.
        mortise_shoulder_inset: Distance from the mortise entry face to the shoulder plane,
            measured perpendicular to the face inward. 0 = shoulder flush with the entry face.
        measure_opposite_shoulder_from: Whether the opposite shoulder reference is measured
            against the receiving timber's perfect or rough boundary.
        opposite_mortise_shoulder_inset: Distance the opposite shoulder reference is moved
            inward (toward the entry shoulder) from that boundary. May be negative.
        relief: Scribe-relief configuration for imperfect timbers. Defaults to scribing the
            tenon (butt) timber onto the mortise (receiving) timber. Pass None to skip.

    Returns:
        Joint object with cuts on both timbers and a "tusk" accessory.
    """

    arrangement.check_plane_aligned()
    
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    # Mirrors cut_mortise_and_tenon_joint_on_plane_aligned_timbers' own mortise-face and
    # shoulder-inset handling (duplicated here rather than threading it back out of that
    # function) because the opposite-shoulder math below needs the raw centerline distance.
    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    entry_shoulder_distance_from_centerline = convert_mortise_shoulder_inset_to_centerline_distance(
        mortise_shoulder_inset=mortise_shoulder_inset,
        mortise_face=mortise_face,
        receiving_timber=mortise_timber,
    )

    # Opposite shoulder: the reference position on the far side of the receiving timber where
    # the tenon "exits" and the tusk hole is centered. Measured from centerline in the same
    # sign convention as entry_shoulder_distance_from_centerline (positive = toward the tenon).
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

    # -------------------------------------------------------------------------
    # Tusk: crosswise locking key through the tenon, positioned at the opposite shoulder.
    # -------------------------------------------------------------------------
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

    # Recompute the entry shoulder's marking origin (mirrors cut_mortise_and_tenon_joint's own
    # marking_origin_global) to locate the opposite-shoulder reference point in 3D.
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



# ============================================================================
# Wedged Half-Dovetail Mortise and Tenon Joint
# ============================================================================

def cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
    arrangement: ButtJointTimberArrangement,
    tenon_size: V2,
    tenon_depth: Numeric,
    dovetail_depth: Numeric,
    wedge_accessory_parameters: DovetailTenonWedgeAccessoryParameters,
    tenon_lateral_offset: Numeric = scalar(0),
    receiving_timber_mortise_extra_depth: Numeric = scalar(0),

    mortise_shoulder_inset: Numeric = scalar(0),

    # TODO
    # cuts a dovetail shaped shoulder using build_dovetail_shoulder_geometery
    # the dovetail_pointy_face_on_butt_timber is the face opposite to arrangement.top_face_on_butt_timber
    #dovetail_shoulder_depth: Numeric = scalar(0),

    # TODO
    #peg_parameters: Optional[SimplePegParameters] = None,

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

    # Convert the user-facing `mortise_shoulder_inset` (measured inward from the mortise
    # entry face) into the signed-from-centerline distance that `compute_butt_joint_shoulder`
    # expects. This mirrors how `cut_mortise_and_tenon_joint_on_plane_aligned_timbers`
    # and `cut_mortise_and_tenon_joint_on_face_aligned_timbers` handle the inset.
    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
        -tenon_end_direction
    ).to.face()
    mortise_shoulder_distance_from_centerline_or_centerplane = convert_mortise_shoulder_inset_to_centerline_distance(
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

    # The CSGs from dovetail_tenon_geometry are in global space. Adopt them into each
    # timber's local frame for cutting.
    tenon_negative_local = adopt_csg(None, tenon_timber.transform, geo.tenon_negative_csg)
    mortise_negative_local = adopt_csg(None, mortise_timber.transform, geo.mortise_negative_csg)

    # Shoulder notch on the receiving timber (and matching relief on the butting
    # timber) when the shoulder is inset from the entry face. For face-aligned
    # orthogonal arrangements the approach angle is pi/2 (no relief walls).
    # This joint is face-aligned, so the arrangement is plane-aligned and the
    # 2-sided notch applies: 2 walls flare, the other 2 run straight across the
    # receiving timber's full width. notch_angle is the same minimum-flare
    # parameter the older chop_relief_for_butt_joint_arrangement called
    # notch_wall_min_relief_cut_angle.
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
            # Add the relief volume to the tenon negative CSG so the butting timber
            # gets carved away against the receiving timber's notch walls.
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

    # Assembly: the tenon backs out of the mortise along a diagonal direction
    # determined by the wedge_angle. The wedge (always present) locks it
    # and pops first, so the timbers slide at suborder 1.
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

    tenon_cut, mortise_cut = _apply_scribe_relief_if_configured(
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
