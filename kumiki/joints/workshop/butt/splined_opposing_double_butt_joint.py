"""
Kumiki - Splined opposing double butt joint construction function
"""

from kumiki.construction import arrangement_error
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import (
    get_center_point_on_face_global,
    locate_top_center_position,
    mark_distance_from_end_along_centerline,
)
from ..shavings import *
from ..shavings.build_a_butt import (
    SimplePegParameters,
    locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber,
    locate_tenon_origin_on_shoulder,
)
from ..shavings.relief import (
    chop_shoulder_notch_aligned_with_timber,
    warn_if_arrangement_timbers_imperfect,
)

@dataclass(frozen=True)
class StubbyMiniTenon:
    """A short tenon left on a butt timber's end, beside the spline, in a mortise in the receiving timber.

    `position` and `size` are as cut_mortise_and_tenon_joint's `tenon_position` and `tenon_size`: the
    tenon's centre, offset from the butt timber's centerline, and its size, both in that timber's
    local X and Y. `length` is how far it reaches past the shoulder. `mortise_extra_depth` is how much
    deeper than `length` its mortise goes; None for a quarter of `length`.
    """
    position: V2
    size: V2
    length: Numeric
    mortise_extra_depth: Optional[Numeric] = None

    def reflect_for_other_side(self, from_timber: TimberLike, to_timber: TimberLike) -> 'StubbyMiniTenon':
        """Return this tenon of `from_timber` as one on `to_timber`, the opposing butt timber, lined up with
        it across the receiving timber: the same place in the world, in `to_timber`'s local X and Y."""
        length_direction = from_timber.get_length_direction_global()
        between = from_timber.get_bottom_position_global() - to_timber.get_bottom_position_global()
        between = between - length_direction * safe_dot_product(between, length_direction)
        offset = (between
                  + from_timber.get_face_direction_global(TimberFace.RIGHT) * self.position[0]
                  + from_timber.get_face_direction_global(TimberFace.FRONT) * self.position[1])
        to_right = to_timber.get_face_direction_global(TimberFace.RIGHT)
        to_front = to_timber.get_face_direction_global(TimberFace.FRONT)
        # The timbers' X and Y may be turned a quarter from each other; the size turns with them.
        same_axes = are_vectors_parallel(to_right, from_timber.get_face_direction_global(TimberFace.RIGHT))
        return replace(
            self,
            position=create_v2(safe_dot_product(offset, to_right), safe_dot_product(offset, to_front)),
            size=self.size if same_axes else create_v2(self.size[1], self.size[0]),
        )

def cut_splined_opposing_double_butt_joint_on_face_aligned_timbers(
    arrangement: DoubleButtJointTimberArrangement,
    # thickness is in the axis perpendicular to the joint plane
    slot_thickness: Numeric,
    # depth is in the axis of the receiving timber, measured from the face of the butt timber that aligns with slot_facing_end_on_receiving_timber
    slot_depth: Numeric,
    # length is in the axis parallel to the butt timbers
    spline_length: Numeric,
    # REQUIRED: the slot faces this end of the receiving timber
    slot_facing_end_on_receiving_timber: TimberEnd,
    # the spline has this much extra depth beyond the slot depth; defaults to 1/4 of slot_depth
    spline_extra_depth=None,
    # the slot extends this much beyond the spline on each end for clearance
    slot_symmetric_extra_length=mm(3),
    # inset the shoulder plane on both sides by this amount, flush with faces of receiving timber if 0
    shoulder_symmetric_inset=scalar(0),
    # offset the slot by this much, measured relative to receiving timber centerline in the axis perpendicular to the joint plane
    slot_lateral_offset=scalar(0),
    # optional peg setup; pegs will be drilled through each butt timber and the spline
    peg_parameters: Optional[SimplePegParameters] = None,

    # stubby mini tenons on butt_timber_1, each in a mortise in the receiving timber
    timber1_stubby_mini_tenons: Optional[List[StubbyMiniTenon]] = None,
    # those on butt_timber_2; None for timber1's, reflected across to line up with them
    timber2_stubby_mini_tenons: Optional[List[StubbyMiniTenon]] = None,

) -> Joint:
    """
    Creates a splined opposing double butt joint.

    Two butt timbers approach the receiving timber from opposite cardinal directions.
    All three timbers must be face-aligned, each butt timber must be perpendicular to the
    receiving timber, and the two butt timbers must be antiparallel.

    [![Splined opposing double butt](../../../assets/joint-drawings/splined-double-butt.svg)](../../../assets/joint-drawings/splined-double-butt.svg)
    [![Splined joint with stub tenons](../../../assets/joint-drawings/splined-stub-tenons.svg)](../../../assets/joint-drawings/splined-stub-tenons.svg)

    Args:
        arrangement: Double butt joint arrangement with butt_timber_1, butt_timber_2,
            receiving_timber, butt_timber_1_end, butt_timber_2_end.

    Returns:
        Joint containing all three cut timbers.

    Raises:
        AssertionError: If the arrangement fails the cardinal-and-opposing-butts check.
    """
    error = arrangement.check_face_aligned_cardinal_and_opposing_butts()
    assert error is None, error
    warn_if_arrangement_timbers_imperfect(arrangement)

    assert isinstance(slot_facing_end_on_receiving_timber, TimberEnd), (
        f"slot_facing_end_on_receiving_timber must be TimberEnd, got "
        f"{type(slot_facing_end_on_receiving_timber).__name__}"
    )

    butt_timber_1 = arrangement.butt_timber_1
    butt_timber_2 = arrangement.butt_timber_2
    receiving_timber = arrangement.receiving_timber

    butt_length_direction_global = butt_timber_1.get_length_direction_global()
    receiving_length_direction_global = receiving_timber.get_length_direction_global()
    slot_direction_global = receiving_timber.get_face_direction_global(slot_facing_end_on_receiving_timber)
    joint_plane_normal_global = safe_normalize_vector(
        cross_product(butt_length_direction_global, receiving_length_direction_global)
    )

    slot_face_on_butt_1 = butt_timber_1.get_closest_oriented_long_face_from_global_direction(slot_direction_global)
    slot_face_on_butt_2 = butt_timber_2.get_closest_oriented_long_face_from_global_direction(slot_direction_global)

    slot_face_direction_1 = butt_timber_1.get_face_direction_global(slot_face_on_butt_1)
    slot_face_direction_2 = butt_timber_2.get_face_direction_global(slot_face_on_butt_2)

    assert are_vectors_parallel(slot_face_direction_1, slot_direction_global), (
        "slot-facing face on butt_timber_1 must align with slot_direction"
    )
    assert are_vectors_parallel(slot_face_direction_2, slot_direction_global), (
        "slot-facing face on butt_timber_2 must align with slot_direction"
    )

    slot_depth_axis_dimension = butt_timber_1.get_size_in_face_normal_axis(slot_face_on_butt_1)
    slot_thickness_axis_dimension = butt_timber_1.get_size_in_direction_3d(joint_plane_normal_global)

    if spline_extra_depth is None:
        spline_extra_depth = slot_depth / scalar(4)

    assert safe_compare(slot_thickness, 0, Comparison.GT), "slot_thickness must be > 0"
    assert safe_compare(slot_depth, 0, Comparison.GT), "slot_depth must be > 0"
    assert safe_compare(slot_depth_axis_dimension - slot_depth, 0, Comparison.GE), (
        "slot_depth must be <= butt timber thickness along slot depth axis"
    )
    assert safe_compare(spline_length, 0, Comparison.GT), "spline_length must be > 0"
    effective_slot_depth = slot_depth + spline_extra_depth
    assert safe_compare(slot_thickness_axis_dimension - slot_thickness, 0, Comparison.GE), (
        "slot_thickness must be <= butt timber thickness along joint-plane-normal axis"
    )
    assert safe_compare(spline_extra_depth, 0, Comparison.GE), "spline_extra_depth must be >= 0"
    assert safe_compare(slot_symmetric_extra_length, 0, Comparison.GE), "slot_symmetric_extra_length must be >= 0"

    slot_length = spline_length + scalar(2) * slot_symmetric_extra_length
    assert safe_compare(slot_length, 0, Comparison.GT), "slot_length must be > 0"

    def _locate_butt_end_center_global(timber: TimberLike, end: TimberEnd) -> V3:
        if end == TimberEnd.TOP:
            return locate_top_center_position(timber).position
        return timber.get_bottom_position_global()

    butt_end_center_1_global = _locate_butt_end_center_global(butt_timber_1, arrangement.butt_timber_1_end)
    butt_end_center_2_global = _locate_butt_end_center_global(butt_timber_2, arrangement.butt_timber_2_end)

    entry_face_point_1_global = (
        butt_end_center_1_global
        + slot_face_direction_1 * (butt_timber_1.get_size_in_face_normal_axis(slot_face_on_butt_1) / scalar(2))
    )
    entry_face_point_2_global = (
        butt_end_center_2_global
        + slot_face_direction_2 * (butt_timber_2.get_size_in_face_normal_axis(slot_face_on_butt_2) / scalar(2))
    )

    slot_center_from_butt_1_global = entry_face_point_1_global - slot_direction_global * (slot_depth / scalar(2))
    slot_center_from_butt_2_global = entry_face_point_2_global - slot_direction_global * (slot_depth / scalar(2))
    slot_center_global = (
        slot_center_from_butt_1_global + slot_center_from_butt_2_global
    ) / scalar(2) + joint_plane_normal_global * slot_lateral_offset

    slot_marking_orientation_global = Orientation.from_z_and_y(
        z_direction=butt_length_direction_global,
        y_direction=slot_direction_global,
    )
    slot_marking_transform_global = Transform(
        position=slot_center_global,
        orientation=slot_marking_orientation_global,
    )

    slot_negative_csg_global = RectangularPrism(
        size=create_v2(slot_thickness, slot_depth),
        transform=slot_marking_transform_global,
        start_distance=-(slot_length / scalar(2)),
        end_distance=slot_length / scalar(2),
        label=CutCSGLabel("spline_slot"),
    )

    extended_slot_negative_csg_global = RectangularPrism(
        size=create_v2(slot_thickness, effective_slot_depth),
        transform=Transform(
            position=slot_marking_transform_global.position + slot_direction_global * (effective_slot_depth - slot_depth) / 2,
            orientation=slot_marking_transform_global.orientation,
        ),
        start_distance=-(slot_length / scalar(2)),
        end_distance=slot_length / scalar(2),
        label=CutCSGLabel("spline_slot"),
    )

    def _make_shoulder_end_cut(timber: TimberLike, timber_end: TimberEnd) -> HalfSpace:
        butt_end_direction_global = timber.get_face_direction_global(timber_end)
        receiving_face = receiving_timber.get_closest_oriented_face_from_global_direction(-butt_end_direction_global)
        receiving_face_center_global = get_center_point_on_face_global(receiving_face, receiving_timber)

        distance_from_bottom = safe_dot_product(
            receiving_face_center_global - timber.get_bottom_position_global(),
            timber.get_length_direction_global(),
        )
        if timber_end == TimberEnd.TOP:
            distance_from_end = timber.length - distance_from_bottom
        else:
            distance_from_end = distance_from_bottom

        distance_from_end = distance_from_end - shoulder_symmetric_inset
        assert safe_compare(distance_from_end, 0, Comparison.GE), "shoulder cut distance must be >= 0"
        assert safe_compare(timber.length - distance_from_end, 0, Comparison.GE), (
            "shoulder cut distance from end exceeds timber length"
        )
        return chop_timber_end_with_half_plane(timber, timber_end, distance_from_end)

    butt_1_shoulder_end_cut = _make_shoulder_end_cut(butt_timber_1, arrangement.butt_timber_1_end)
    butt_2_shoulder_end_cut = _make_shoulder_end_cut(butt_timber_2, arrangement.butt_timber_2_end)
    butt_1_shoulder_distance_from_bottom = (
        butt_1_shoulder_end_cut.offset
        if arrangement.butt_timber_1_end == TimberEnd.TOP
        else -butt_1_shoulder_end_cut.offset
    )
    butt_2_shoulder_distance_from_bottom = (
        butt_2_shoulder_end_cut.offset
        if arrangement.butt_timber_2_end == TimberEnd.TOP
        else -butt_2_shoulder_end_cut.offset
    )

    receiving_slot_negative_csg_local = adopt_csg(None, receiving_timber.transform, extended_slot_negative_csg_global)
    butt_1_slot_negative_csg_local = adopt_csg(None, butt_timber_1.transform, slot_negative_csg_global)
    butt_2_slot_negative_csg_local = adopt_csg(None, butt_timber_2.transform, slot_negative_csg_global)

    receiving_negative_csg_parts = [receiving_slot_negative_csg_local]

    stubby_tenons_1 = list(timber1_stubby_mini_tenons or [])
    stubby_tenons_2 = (
        list(timber2_stubby_mini_tenons) if timber2_stubby_mini_tenons is not None
        else [tenon.reflect_for_other_side(butt_timber_1, butt_timber_2) for tenon in stubby_tenons_1]
    )

    def _stubby_tenon_cuts(
        butt_timber: TimberLike, butt_end: TimberEnd, tenons: List[StubbyMiniTenon], name: str,
    ) -> Tuple[List[CutCSG], List[CutCSG], Numeric]:
        """Return the butt timber's waste past its shoulder around its stubby tenons, local to it; their
        mortises, local to the receiving timber; and the longest tenon's length."""
        if not tenons:
            return [], [], scalar(0)
        for tenon in tenons:
            for axis in (0, 1):
                half = butt_timber.size[axis] / scalar(2)
                assert safe_compare(tenon.position[axis] - tenon.size[axis] / scalar(2), -half, Comparison.GE) and \
                    safe_compare(tenon.position[axis] + tenon.size[axis] / scalar(2), half, Comparison.LE), (
                        f"a stubby tenon on {name} reaches outside the timber in its local {'XY'[axis]}"
                    )
            assert safe_compare(tenon.length, 0, Comparison.GT), "a stubby tenon's length must be > 0"
        receiving_face_towards_butt = receiving_timber.get_closest_oriented_long_face_from_global_direction(
            butt_timber.get_face_direction_global(butt_end)
        )
        shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            ButtJointTimberArrangement(butt_timber=butt_timber, receiving_timber=receiving_timber, butt_timber_end=butt_end),
            receiving_timber.get_size_in_face_normal_axis(receiving_face_towards_butt) / scalar(2) - shoulder_symmetric_inset,
        )
        tenon_orientation = compute_timber_orientation(
            safe_normalize_vector(butt_timber.get_face_direction_global(butt_end)), butt_timber.get_width_direction_global()
        )
        tenons_local: List[CutCSG] = []
        mortises_local: List[CutCSG] = []
        for index, tenon in enumerate(tenons):
            transform = Transform(
                position=locate_tenon_origin_on_shoulder(shoulder_plane, butt_timber, butt_end, tenon.position),
                orientation=tenon_orientation,
            )
            extra = tenon.mortise_extra_depth if tenon.mortise_extra_depth is not None else tenon.length / scalar(4)
            assert safe_compare(extra, 0, Comparison.GE), "a stubby tenon's mortise_extra_depth must be >= 0"
            tenons_local.append(adopt_csg(None, butt_timber.transform, RectangularPrism(
                size=tenon.size, transform=transform, start_distance=scalar(0), end_distance=tenon.length,
                label=CutCSGLabel(f"stubby_tenon_{index}"),
            )))
            mortises_local.append(adopt_csg(None, receiving_timber.transform, RectangularPrism(
                size=tenon.size, transform=transform, start_distance=scalar(0), end_distance=tenon.length + extra,
                label=CutCSGLabel(f"stubby_mortise_{name}_{index}"),
            )))
        # Everything past the shoulder goes, but the tenons.
        shoulder_waste_global = HalfSpace(
            normal=-shoulder_plane.normal,
            offset=safe_dot_product(-shoulder_plane.normal, shoulder_plane.point),
            label=CutCSGLabel("stubby_tenon_shoulder"),
        )
        waste_local = Difference(
            base=adopt_csg(None, butt_timber.transform, shoulder_waste_global),
            subtract=tenons_local,
            label=CutCSGLabel("stubby_tenon_waste"),
        )
        return [waste_local], mortises_local, max(tenon.length for tenon in tenons)

    butt_1_stubby_waste, stubby_mortises_1, longest_stubby_1 = _stubby_tenon_cuts(
        butt_timber_1, arrangement.butt_timber_1_end, stubby_tenons_1, "butt_timber_1")
    butt_2_stubby_waste, stubby_mortises_2, longest_stubby_2 = _stubby_tenon_cuts(
        butt_timber_2, arrangement.butt_timber_2_end, stubby_tenons_2, "butt_timber_2")
    receiving_negative_csg_parts.extend(stubby_mortises_1 + stubby_mortises_2)
    # A butt timber with stubby tenons ends at their tips; the waste around them is cut back to the shoulder.
    butt_1_end_cut_from_bottom = butt_1_shoulder_distance_from_bottom + (
        longest_stubby_1 if arrangement.butt_timber_1_end == TimberEnd.TOP else -longest_stubby_1)
    butt_2_end_cut_from_bottom = butt_2_shoulder_distance_from_bottom + (
        longest_stubby_2 if arrangement.butt_timber_2_end == TimberEnd.TOP else -longest_stubby_2)

    if safe_compare(shoulder_symmetric_inset, 0, Comparison.GT):
        def _make_receiving_shoulder_notch_local(
            butting_timber: TimberLike,
            butting_timber_end: TimberEnd,
        ) -> CutCSG:
            butt_end_direction_global = butting_timber.get_face_direction_global(butting_timber_end)
            receiving_face = receiving_timber.get_closest_oriented_long_face_from_global_direction(
                -butt_end_direction_global
            )
            receiving_face_half_size = receiving_timber.get_size_in_face_normal_axis(receiving_face) / scalar(2)
            shoulder_distance_from_centerline = receiving_face_half_size - shoulder_symmetric_inset

            assert safe_compare(shoulder_distance_from_centerline, 0, Comparison.GE), (
                "shoulder_symmetric_inset is too large for receiving timber half size"
            )

            return chop_shoulder_notch_aligned_with_timber(
                notch_timber=receiving_timber,
                butting_timber=butting_timber,
                butting_timber_end=butting_timber_end,
                distance_from_centerline=shoulder_distance_from_centerline,
            )

        receiving_negative_csg_parts.append(
            _make_receiving_shoulder_notch_local(butt_timber_1, arrangement.butt_timber_1_end)
        )
        receiving_negative_csg_parts.append(
            _make_receiving_shoulder_notch_local(butt_timber_2, arrangement.butt_timber_2_end)
        )

    receiving_negative_csg_local = (
        receiving_negative_csg_parts[0]
        if len(receiving_negative_csg_parts) == 1
        else CSGUnion(children=receiving_negative_csg_parts)
    )

    receiving_cut = Cutting(
        timber=receiving_timber,
        negative_csg=receiving_negative_csg_local,
        label=CutCSGLabel("spline_socket_cut"),
    )
    spline_transform = Transform(
        position=slot_marking_transform_global.position + slot_direction_global * (effective_slot_depth-slot_depth)/2,
        orientation=slot_marking_orientation_global,
    )

    peg_holes_in_spline_local: List[CutCSG] = []
    joint_accessories: Dict[str, Accessory] = {}
    butt_1_negative_parts: List[CutCSG] = [butt_1_slot_negative_csg_local, *butt_1_stubby_waste]
    butt_2_negative_parts: List[CutCSG] = [butt_2_slot_negative_csg_local, *butt_2_stubby_waste]

    # peg logic slightly different so we don't use compute_peg_positions
    if peg_parameters is not None:
        peg_size = peg_parameters.size

        if arrangement.front_face_on_butt_timber_1 is None:

            raise arrangement_error("front_face_on_butt_timber_1 must be provided when peg_parameters are set", arrangement)

        peg_entry_direction_global = butt_timber_1.get_face_direction_global(
            arrangement.front_face_on_butt_timber_1
        )

        peg_face_on_butt_1 = arrangement.front_face_on_butt_timber_1
        peg_face_on_butt_2 = butt_timber_2.get_closest_oriented_long_face_from_global_direction(
            peg_entry_direction_global
        )

        def _append_pegs_for_butt(
            butt_timber: TimberLike,
            butt_end: TimberEnd,
            peg_face_on_butt: TimberLongFace,
            butt_negative_parts: List[CutCSG],
            accessory_prefix: str,
        ) -> None:
            # Peg geometry: enters from peg_face, drills perpendicular to the joint plane.
            peg_face: TimberFace = peg_face_on_butt.to.face()
            peg_face_normal_global = butt_timber.get_face_direction_global(peg_face_on_butt)
            peg_drill_direction = -peg_face_normal_global
            peg_face_plane = locate_face(butt_timber, peg_face)

            # Peg depth = full width of the butt timber in the drill direction.
            # The peg goes from the entry face, through the timber, to the exit face.
            peg_depth = butt_timber.get_size_in_face_normal_axis(peg_face_on_butt)
            actual_depth = peg_parameters.depth if peg_parameters.depth is not None else peg_depth
            stickout = actual_depth * scalar(1, 2)

            # Away-from-joint axis: from the shoulder toward the main butt body.
            butt_end_direction = butt_timber.get_face_direction_global(butt_end)
            away_from_joint_axis = -butt_end_direction

            # Lateral axis in the peg face plane, matching compute_peg_positions convention.
            if peg_face_on_butt in [TimberLongFace.RIGHT, TimberLongFace.LEFT]:
                lateral_axis = butt_timber.get_face_direction_global(TimberFace.FRONT)
            else:
                lateral_axis = butt_timber.get_face_direction_global(TimberFace.RIGHT)

            # Peg orientation: drill direction is Z, butt length direction is Y.
            butt_length_dir = butt_timber.get_length_direction_global()
            peg_orientation_global = Orientation.from_z_and_y(
                z_direction=peg_drill_direction,
                y_direction=butt_length_dir,
            )

            # Shoulder reference: the external face of the receiving timber that the butt enters.
            # Using the existing shoulder-plane helper with a ButtJointTimberArrangement.
            butt_arrangement = ButtJointTimberArrangement(
                butt_timber=butt_timber,
                receiving_timber=receiving_timber,
                butt_timber_end=butt_end,
                front_face_on_butt_timber=peg_face_on_butt,
            )
            receiving_face_towards_butt = receiving_timber.get_closest_oriented_long_face_from_global_direction(
                butt_timber.get_face_direction_global(butt_end)
            )
            shoulder_distance_from_centerline = (
                receiving_timber.get_size_in_face_normal_axis(receiving_face_towards_butt) / scalar(2)
            ) - shoulder_symmetric_inset
            assert safe_compare(shoulder_distance_from_centerline, 0, Comparison.GE), (
                "shoulder_symmetric_inset is too large for peg shoulder reference"
            )
            shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
                butt_arrangement,
                shoulder_distance_from_centerline,
            )
            shoulder_mark = mark_distance_from_end_along_centerline(
                shoulder_plane, butt_timber, butt_end
            )
            shoulder_point_global = shoulder_mark.locate().position

            # Lateral peg positions are referenced from the centerline of the non-extra
            # spline body, not from the butt timber centerline at the shoulder.
            non_extra_spline_center_lateral_offset = safe_dot_product(
                slot_center_global - shoulder_point_global,
                lateral_axis,
            )
            spline_lateral_reference_global = (
                shoulder_point_global
                + lateral_axis * non_extra_spline_center_lateral_offset
            )

            for peg_idx, (dist_from_shoulder, dist_from_center) in enumerate(peg_parameters.peg_positions):
                # Place peg away from the receiving-timber shoulder, into the butt body.
                peg_center_global = (
                    spline_lateral_reference_global
                    + away_from_joint_axis * dist_from_shoulder
                    + lateral_axis * dist_from_center
                )

                # Project peg center onto the peg entry face plane.
                dist_to_face = safe_dot_product(
                    peg_face_plane.normal,
                    peg_face_plane.point - peg_center_global,
                )
                peg_face_pos_global = peg_center_global + peg_face_plane.normal * dist_to_face

                # tenon_hole_offset shifts the spline hole in the same away-from-joint direction.
                peg_face_pos_with_offset_global = (
                    peg_face_pos_global
                    + away_from_joint_axis * peg_parameters.tenon_hole_offset
                )

                peg_hole_in_butt_global = RectangularPrism(
                    size=create_v2(peg_size, peg_size),
                    transform=Transform(
                        position=peg_face_pos_global,
                        orientation=peg_orientation_global,
                    ),
                    start_distance=scalar(0),
                    end_distance=actual_depth,
                    label=CutCSGLabel("peg_hole"),
                )
                butt_negative_parts.append(
                    adopt_csg(None, butt_timber.transform, peg_hole_in_butt_global)
                )

                # For splined double butt joints, tenon_hole_offset shifts the spline hole
                # in the away-from-joint direction (toward the butt body).
                peg_hole_in_spline_global = RectangularPrism(
                    size=create_v2(peg_size, peg_size),
                    transform=Transform(
                        position=peg_face_pos_with_offset_global,
                        orientation=peg_orientation_global,
                    ),
                    start_distance=scalar(0),
                    end_distance=actual_depth,
                    label=CutCSGLabel("peg_hole"),
                )
                peg_holes_in_spline_local.append(
                    adopt_csg(None, spline_transform, peg_hole_in_spline_global)
                )

                # Assembly: the peg backs out of its entry face; it locks the
                # joint, so it pops (suborder 0) before the members slide.
                joint_accessories[f"{accessory_prefix}_{peg_idx}"] = Peg(
                    transform=Transform(
                        position=peg_face_pos_global,
                        orientation=peg_orientation_global,
                    ),
                    size=peg_size,
                    shape=peg_parameters.shape,
                    forward_length=actual_depth,
                    stickout_length=stickout,
                    assembly_freedom=AssemblyFreedom.translation(
                        peg_face_normal_global, freed_after=actual_depth + stickout
                    ),
                    assembly_ordering=Ordering(0, -1),
                )

        _append_pegs_for_butt(
            butt_timber_1,
            arrangement.butt_timber_1_end,
            peg_face_on_butt_1,
            butt_1_negative_parts,
            "peg_butt_1",
        )
        _append_pegs_for_butt(
            butt_timber_2,
            arrangement.butt_timber_2_end,
            peg_face_on_butt_2,
            butt_2_negative_parts,
            "peg_butt_2",
        )

    def _butt_cut(timber: TimberLike, end: TimberEnd, end_cut_from_bottom: Numeric, parts: List[CutCSG]) -> Cutting:
        return Cutting(
            timber=timber,
            maybe_top_end_cut_distance_from_bottom=end_cut_from_bottom if end == TimberEnd.TOP else None,
            maybe_bottom_end_cut_distance_from_bottom=end_cut_from_bottom if end == TimberEnd.BOTTOM else None,
            negative_csg=parts[0] if len(parts) == 1 else CSGUnion(children=parts),
            # Without pegs or stubby tenons the cut is the slot alone, named as such.
            label=CutCSGLabel("spline_slot_cut") if len(parts) == 1 else CutCSGLabel.NoLabel(),
        )

    butt_1_cut = _butt_cut(butt_timber_1, arrangement.butt_timber_1_end, butt_1_end_cut_from_bottom, butt_1_negative_parts)
    butt_2_cut = _butt_cut(butt_timber_2, arrangement.butt_timber_2_end, butt_2_end_cut_from_bottom, butt_2_negative_parts)

    # Accessory geometry is local-space and centered at origin; transform places it globally.
    spline_positive_csg = RectangularPrism(
        size=create_v2(slot_thickness, effective_slot_depth),
        transform=Transform.identity(),
        start_distance=-(spline_length / scalar(2)),
        end_distance=spline_length / scalar(2),
        label=CutCSGLabel("spline"),
    )

    if peg_holes_in_spline_local:
        spline_positive_csg = Difference(
            base=spline_positive_csg,
            subtract=peg_holes_in_spline_local,
            label=CutCSGLabel("spline_drilled"),
        )

    # Assembly: each butt timber pulls back along its own axis, sliding off
    # the spline (free after clearing the spline's reach into it); the spline
    # backs out of its slot. When pegs lock the joint they pop first
    # (suborder 0), so the sliding members go at suborder 1.
    member_suborder = 1 if peg_parameters is not None else 0
    butt_1_escape_direction = -butt_timber_1.get_face_direction_global(arrangement.butt_timber_1_end)
    butt_2_escape_direction = -butt_timber_2.get_face_direction_global(arrangement.butt_timber_2_end)
    butt_1_cut = replace(
        butt_1_cut,
        assembly_freedom=AssemblyFreedom.translation(butt_1_escape_direction, freed_after=max(spline_length / scalar(2), longest_stubby_1)),
        assembly_ordering=Ordering(0, 0),
    )
    butt_2_cut = replace(
        butt_2_cut,
        assembly_freedom=AssemblyFreedom.translation(butt_2_escape_direction, freed_after=max(spline_length / scalar(2), longest_stubby_2)),
        assembly_ordering=Ordering(0, 0),
    )

    spline = CSGAccessory(
        transform=spline_transform,
        positive_csg=spline_positive_csg,
        assembly_freedom=AssemblyFreedom.translation(-slot_direction_global, freed_after=effective_slot_depth),
        assembly_ordering=Ordering(0, 0),
    )
    joint_accessories["spline"] = spline

    return Joint(
        cuttings={
            "receiving_timber": receiving_cut,
            "butt_timber_1": butt_1_cut,
            "butt_timber_2": butt_2_cut,
        },
        ticket=JointTicket(joint_type="splined_opposing_double_butt"),
        jointAccessories=joint_accessories,
    )
