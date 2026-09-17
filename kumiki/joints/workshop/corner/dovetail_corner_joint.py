"""
Kumiki - Dovetail corner joint construction function
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from kumiki.construction import CornerJointTimberArrangement
from kumiki.cutcsg import (
    CutCSG,
    CutCSGLabel,
    Difference,
    SolidUnion,
    adopt_csg,
)
from kumiki.measuring import (
    get_center_point_on_face_global,
    mark_distance_from_end_along_centerline,
)
from kumiki.rule import (
    Comparison,
    Numeric,
    create_v2,
    cross_product,
    pi,
    safe_compare,
    safe_dot_product,
    safe_equality_test,
    scalar,
    tan,
)
from kumiki.timber import (
    AssemblyFreedom,
    Cutting,
    Joint,
    JointTicket,
    TimberEnd,
    require_check,
)
from ..shavings.shavings import (
    chop_profile_on_timber_face,
    chop_timber_end_with_half_plane,
    scribe_face_plane_onto_centerline,
)
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


@dataclass(frozen=True)
class SingleDovetailSizeParameter:
    """
        ______
    ____\\   /_______ }depth
          ^ small_width

    angle: flare of the dovetail walls, 0 is perpendicular (a straight finger)
    small_width: width at the shoulder, where the dovetail is narrowest
    depth: how far the dovetail reaches into timber2. None goes all the way
        through; less than that makes a half blind dovetail. Full blind
        dovetails are done with another joint.
    """
    angle: Numeric
    small_width: Numeric
    depth: Optional[Numeric] = None


# dovetail measurement starts from front_face_on_timber1
# distances are measured from the CENTERs of the dovetails, starting from front_face_on_timber1 and then from the center of one dovetail to the next
# dovetails positives are cut into timber1, negatives are cut into timber2
def cut_dovetail_corner_joint(arrangement: CornerJointTimberArrangement, distances: List[Numeric], dovetails: List[SingleDovetailSizeParameter]) -> Joint:
    """
    Creates a dovetail corner joint: a row of interlocking dovetails across a corner.

    timber1 keeps the dovetails and timber2 receives the matching sockets, so the two
    interlock through the corner the way a drawer front interlocks with a drawer side.
    Each dovetail starts at the shoulder -- the near face of timber2 -- and widens as it
    reaches `depth` into timber2, which locks timber1 against being drawn away from the
    corner. A dovetail whose depth is timber2's full thickness is a through dovetail and
    shows on timber2's outside face; a shallower one is half blind. Dovetails span
    timber1's whole thickness through the corner, so the joint assembles by sliding
    timber1 along timber2's length axis and nothing else.

    Dovetails are laid out across timber1's outside face along the axis normal to
    `front_face_on_timber1`, measured into the timber from that face.

    Both timbers are end cut to the far face of the other, so the corner reads flush on
    both outside faces.

    Args:
        arrangement: Corner arrangement. timber1 carries the dovetails and timber2 the
            sockets; the timbers must be face aligned, orthogonal, and flush across the
            `front_face_on_timber1` axis. `front_face_on_timber1` must be set -- the
            dovetail layout is measured from it.
        distances: Distance to the center of each dovetail, the first measured from
            `front_face_on_timber1` and each one after from the previous center.
        dovetails: Size of each dovetail, one entry per entry in `distances`.

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        KumikiArrangementError: If the timbers are not face aligned and orthogonal, or
            `front_face_on_timber1` does not point along the corner plane normal.
        AssertionError: If the dovetail parameters do not fit the timbers, overlap each
            other, or run past either face of the layout axis.
    """
    require_check(arrangement.check_face_aligned_and_orthogonal())
    require_check(arrangement.check_plane_aligned())

    warn_if_arrangement_timbers_imperfect(arrangement)

    front_face_on_dovetail_timber = arrangement.front_face_on_timber1
    assert front_face_on_dovetail_timber is not None, (
        "arrangement.front_face_on_timber1 must be set, the dovetail layout is measured from it"
    )
    assert len(dovetails) > 0, "at least one dovetail is required"
    assert len(distances) == len(dovetails), (
        f"distances and dovetails must be the same length, got {len(distances)} and {len(dovetails)}"
    )

    dovetail_timber = arrangement.timber1
    socket_timber = arrangement.timber2
    dovetail_timber_end = arrangement.timber1_end
    socket_timber_end = arrangement.timber2_end

    dovetail_end_direction_global = dovetail_timber.get_face_direction_global(dovetail_timber_end)
    socket_end_direction_global = socket_timber.get_face_direction_global(socket_timber_end)

    # The face on timber2 the dovetails enter through bounds how deep they can go.
    socket_entry_face = socket_timber.get_closest_oriented_long_face_from_global_direction(-dovetail_end_direction_global)
    socket_timber_thickness = socket_timber.get_size_in_face_normal_axis(socket_entry_face)

    sized_dovetails: List[Tuple[SingleDovetailSizeParameter, Numeric]] = []
    for index, dovetail in enumerate(dovetails):
        depth = socket_timber_thickness if dovetail.depth is None else dovetail.depth
        assert safe_compare(depth, 0, Comparison.GT), (
            f"dovetail {index} depth must be greater than 0, got {depth}"
        )
        assert safe_compare(socket_timber_thickness - depth, 0, Comparison.GE), (
            f"dovetail {index} depth ({depth}) must be <= the timber2 thickness it cuts into ({socket_timber_thickness})"
        )
        assert safe_compare(dovetail.small_width, 0, Comparison.GT), (
            f"dovetail {index} small_width must be greater than 0, got {dovetail.small_width}"
        )
        assert safe_compare(dovetail.angle, 0, Comparison.GE), (
            f"dovetail {index} angle must be non-negative, got {dovetail.angle}"
        )
        assert safe_compare(dovetail.angle - pi / scalar(2), 0, Comparison.LT), (
            f"dovetail {index} angle must be less than 90 degrees, got {dovetail.angle}"
        )
        sized_dovetails.append((dovetail, depth))

    # -------------------------------------------------------------------------
    # Marking space: timber1's outside corner face, laid out from its front face
    # -------------------------------------------------------------------------
    dovetail_timber_inside_face = dovetail_timber.get_closest_oriented_long_face_from_global_direction(-socket_end_direction_global)
    dovetail_timber_outside_face = dovetail_timber_inside_face.to.face().get_opposite_face().to.long_face()
    dovetail_timber_thickness = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_outside_face)

    front_face_direction_global = dovetail_timber.get_face_direction_global(front_face_on_dovetail_timber)
    layout_dimension = dovetail_timber.get_size_in_face_normal_axis(front_face_on_dovetail_timber)
    half_layout_dimension = layout_dimension / scalar(2)

    socket_timber_front_face = socket_timber.get_closest_oriented_long_face_from_global_direction(front_face_direction_global)
    assert safe_equality_test(
        socket_timber.get_size_in_face_normal_axis(socket_timber_front_face), layout_dimension
    ) and safe_equality_test(
        safe_dot_product(get_center_point_on_face_global(socket_timber_front_face, socket_timber), front_face_direction_global),
        safe_dot_product(get_center_point_on_face_global(front_face_on_dovetail_timber, dovetail_timber), front_face_direction_global),
    ), "timber1 and timber2 must be flush across the front_face_on_timber1 axis for a dovetail corner joint"

    # Profile x runs across the outside face, see chop_profile_on_timber_face.
    layout_direction_global = cross_product(
        dovetail_end_direction_global,
        dovetail_timber.get_face_direction_global(dovetail_timber_outside_face),
    )
    front_face_sits_at_negative_profile_x = safe_compare(
        safe_dot_product(front_face_direction_global, layout_direction_global), 0, Comparison.LT
    )

    def profile_x_of(distance_from_front_face: Numeric) -> Numeric:
        """Profile x of a distance measured into timber1 from front_face_on_timber1."""
        if front_face_sits_at_negative_profile_x:
            return -half_layout_dimension + distance_from_front_face
        return half_layout_dimension - distance_from_front_face

    # The shoulder is timber2's near face: where the dovetails leave timber1's body.
    socket_entry_plane = scribe_face_plane_onto_centerline(
        face=socket_entry_face.to.face(),
        face_timber=socket_timber,
    )
    shoulder_distance_from_end = mark_distance_from_end_along_centerline(
        socket_entry_plane, dovetail_timber, dovetail_timber_end
    ).distance
    assert safe_compare(shoulder_distance_from_end, 0, Comparison.GT), (
        "timber1 must reach past timber2's near face to be dovetailed into it"
    )

    # -------------------------------------------------------------------------
    # Dovetail profiles, narrow at the shoulder and flaring into timber2
    # -------------------------------------------------------------------------
    dovetail_csgs: List[CutCSG] = []
    distance_from_front_face = scalar(0)
    previous_dovetail_edge = scalar(0)
    for index, ((dovetail, depth), distance) in enumerate(zip(sized_dovetails, distances)):
        distance_from_front_face = distance_from_front_face + distance
        half_small_width = dovetail.small_width / scalar(2)
        half_large_width = half_small_width + depth * tan(dovetail.angle)

        assert safe_compare(distance_from_front_face - half_large_width - previous_dovetail_edge, 0, Comparison.GE), (
            "dovetail 0 crosses front_face_on_timber1"
            if index == 0
            else f"dovetail {index} overlaps dovetail {index - 1}"
        )
        previous_dovetail_edge = distance_from_front_face + half_large_width
        assert safe_compare(layout_dimension - previous_dovetail_edge, 0, Comparison.GE), (
            f"dovetail {index} runs past the face opposite front_face_on_timber1"
        )

        center_x = profile_x_of(distance_from_front_face)
        profile = [
            create_v2(center_x - half_small_width, scalar(0)),
            create_v2(center_x + half_small_width, scalar(0)),
            create_v2(center_x + half_large_width, depth),
            create_v2(center_x - half_large_width, depth),
        ]

        dovetail_csgs.append(chop_profile_on_timber_face(
            timber=dovetail_timber,
            end=dovetail_timber_end,
            face=dovetail_timber_outside_face.to.face(),
            profile=profile,
            depth=dovetail_timber_thickness,
            profile_y_offset_from_end=shoulder_distance_from_end,
            label=CutCSGLabel.NoLabel(),
        ))

    dovetails_csg = SolidUnion(dovetail_csgs, label=CutCSGLabel("dovetails"))
    sockets_csg = SolidUnion(
        [adopt_csg(dovetail_timber.transform, socket_timber.transform, csg) for csg in dovetail_csgs],
        label=CutCSGLabel("dovetail_sockets"),
    )

    # Everything past the shoulder comes away from timber1 except the dovetails. A half
    # space rather than a prism, so material outside the perfect timber within goes too.
    shoulder_half_space = chop_timber_end_with_half_plane(
        timber=dovetail_timber,
        end=dovetail_timber_end,
        distance_from_end_to_cut=shoulder_distance_from_end,
        label=CutCSGLabel("shoulder"),
    )
    dovetail_timber_negative_csg = Difference(
        shoulder_half_space, [dovetails_csg], label=CutCSGLabel("dovetail_waste"),
    )

    # -------------------------------------------------------------------------
    # End cuts: each timber is cut to the far face of the other
    # note that techincally timber1 could have a shorter maybe end cut if all the tenons are half blind but we don't bother with that. please preserve this comment
    # -------------------------------------------------------------------------
    socket_timber_far_face_point_global = get_center_point_on_face_global(
        socket_entry_face.to.face().get_opposite_face(), socket_timber
    )
    dovetail_timber_end_cut_distance_from_bottom = safe_dot_product(
        socket_timber_far_face_point_global - dovetail_timber.get_bottom_position_global(),
        dovetail_timber.get_length_direction_global(),
    )

    dovetail_timber_outside_face_point_global = get_center_point_on_face_global(
        dovetail_timber_outside_face, dovetail_timber
    )
    socket_timber_end_cut_distance_from_bottom = safe_dot_product(
        dovetail_timber_outside_face_point_global - socket_timber.get_bottom_position_global(),
        socket_timber.get_length_direction_global(),
    )

    # The dovetails only leave their sockets out through timber2's end face.
    dovetail_withdraw_direction_global = dovetail_timber.get_face_direction_global(dovetail_timber_outside_face)

    dovetail_timber_cutting = Cutting(
        timber=dovetail_timber,
        maybe_top_end_cut_distance_from_bottom=dovetail_timber_end_cut_distance_from_bottom if dovetail_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=dovetail_timber_end_cut_distance_from_bottom if dovetail_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=dovetail_timber_negative_csg,
        label=CutCSGLabel("dovetail_cut"),
        assembly_freedom=AssemblyFreedom.translation(
            dovetail_withdraw_direction_global, freed_after=dovetail_timber_thickness
        ),
    )

    socket_timber_cutting = Cutting(
        timber=socket_timber,
        maybe_top_end_cut_distance_from_bottom=socket_timber_end_cut_distance_from_bottom if socket_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=socket_timber_end_cut_distance_from_bottom if socket_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=sockets_csg,
        label=CutCSGLabel("dovetail_socket_cut"),
        assembly_freedom=AssemblyFreedom.translation(
            -dovetail_withdraw_direction_global, freed_after=dovetail_timber_thickness
        ),
    )

    return Joint(
        cuttings={
            "dovetail_timber": dovetail_timber_cutting,
            "socket_timber": socket_timber_cutting,
        },
        ticket=JointTicket(joint_type="dovetail_corner"),
        jointAccessories={},
    )
