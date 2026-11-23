"""
Kumiki - Dovetail corner joint construction function
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from kumiki.construction import CornerJointTimberArrangement
from kumiki.csg.cutcsg import (
    HALF_SPACE_PLANE,
    ConvexPolygonExtrusion,
    CutCSG,
    CutCSGLabel,
    Difference,
    FeatureGroup,
    FeatureOverride,
    FeatureProperties,
    HalfSpace,
    Intersection,
    SolidUnion,
    adopt_csg,
    measured_against,
    shoulder_override,
    side_key,
)
from kumiki.measuring import (
    get_center_point_on_face_global,
    mark_distance_from_end_along_centerline,
)
from kumiki.rule import (
    Abs,
    Comparison,
    Max,
    Min,
    Numeric,
    Orientation,
    Transform,
    V2,
    are_vectors_parallel,
    create_v2,
    create_v3,
    pi,
    safe_compare,
    safe_dot_product,
    safe_equality_test,
    safe_zero_test,
    scalar,
    tan,
)
from kumiki.construction import arrangement_check
from kumiki.timber import (
    AssemblyFreedom,
    Cutting,
    Joint,
    JointTicket,
    TimberEnd,
)
from ..shavings.shavings import (
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


#: A dovetail face is named and measurable, and meets the shoulder plane where
#: the dovetail leaves the timber -- that line is the tail's base arris, which is
#: nowhere else, so it has to be derived from the pair.
_DOVETAIL_FACE = FeatureProperties(group=FeatureGroup.TENON)

#: A tail's sides run profile point n to point n+1, so side 1 and side 3 are its
#: flared cheeks and side 2 is the wide leading face it is locked in by. Side 0 is
#: the base, buried in the timber the tail grows out of, and both caps lie in the
#: planes of that timber's own faces -- naming either would derive the same line
#: as the body's own edge with the shoulder plane (see _drop_duplicate_derived).
def _dovetail_face_overrides(face: FeatureProperties = _DOVETAIL_FACE):
    """Return the dovetail's face overrides; each cheek's angle is measured from the wide face."""
    return (
        FeatureOverride(side_key(1), "dovetail_right", measured_against(face, "dovetail_front")),
        FeatureOverride(side_key(2), "dovetail_front", measured_against(face, "dovetail_right", "dovetail_left")),
        FeatureOverride(side_key(3), "dovetail_left", measured_against(face, "dovetail_front")),
    )


_DOVETAIL_FACE_OVERRIDES = _dovetail_face_overrides()

#: At an angle the cheeks are seen edge-on in no view of timber1, so they are measured by the
#: lines they leave on its faces: CROSSING, like the free dovetail's, forms those edges.
_BEVELLED_DOVETAIL_FACE_OVERRIDES = _dovetail_face_overrides(FeatureProperties(group=FeatureGroup.CROSSING))


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

    The corner may be at any angle in the plane the timbers share. The dovetail walls run
    along timber2's length, square to its end, so at an angle the shoulder and the tails
    are sawn at a bevel across timber1.

    Dovetails are laid out across timber1's outside face along the axis normal to
    `front_face_on_timber1`, measured into the timber from that face. `depth`, `angle`
    and `small_width` are taken square to timber2's length, from its near face.

    Both timbers are end cut to the far face of the other, so the corner reads flush on
    both outside faces.

    [![Through dovetail corner](../../../assets/joint-drawings/through-dovetails.svg)](../../../assets/joint-drawings/through-dovetails.svg)
    [![Half-blind dovetail corner](../../../assets/joint-drawings/half-blind-dovetails.svg)](../../../assets/joint-drawings/half-blind-dovetails.svg)

    Args:
        arrangement: Corner arrangement. timber1 carries the dovetails and timber2 the
            sockets; the timbers must be plane aligned, not parallel, and flush across
            the `front_face_on_timber1` axis. `front_face_on_timber1` must be set -- the
            dovetail layout is measured from it.
        distances: Distance to the center of each dovetail, the first measured from
            `front_face_on_timber1` and each one after from the previous center.
        dovetails: Size of each dovetail, one entry per entry in `distances`.

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        KumikiArrangementError: If the timbers are not plane aligned, or
            `front_face_on_timber1` does not point along the corner plane normal.
        AssertionError: If the timbers are parallel, or the dovetail parameters do not
            fit the timbers, overlap each other, or run past either face of the layout axis.
    """
    arrangement_check(arrangement.check_plane_aligned(), arrangement)
    assert not are_vectors_parallel(
        arrangement.timber1.get_length_direction_global(), arrangement.timber2.get_length_direction_global()
    ), "timber1 and timber2 cannot be parallel for a dovetail corner joint"

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
    # Marking space: on the shoulder, x across the layout, y into timber2 square to
    # its length, z along timber2's length toward its end (the way the joint slides)
    # -------------------------------------------------------------------------
    dovetail_timber_inside_face = dovetail_timber.get_closest_oriented_long_face_from_global_direction(-socket_end_direction_global)
    dovetail_timber_outside_face = dovetail_timber_inside_face.to.face().get_opposite_face().to.long_face()
    dovetail_timber_thickness = dovetail_timber.get_size_in_face_normal_axis(dovetail_timber_outside_face)
    outside_direction_global = dovetail_timber.get_face_direction_global(dovetail_timber_outside_face)
    into_socket_direction_global = -socket_timber.get_face_direction_global(socket_entry_face)
    slide_direction_global = socket_timber.get_length_direction_global() * (
        scalar(1) if socket_timber_end == TimberEnd.TOP else scalar(-1))
    # Square corners keep the exact tails, shoulder and end cuts they always had.
    square_corner = safe_zero_test(safe_dot_product(
        dovetail_timber.get_length_direction_global(), socket_timber.get_length_direction_global()))

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

    # The shoulder is timber2's near face: where the dovetails leave timber1's body.
    socket_entry_plane = scribe_face_plane_onto_centerline(
        face=socket_entry_face.to.face(),
        face_timber=socket_timber,
    )
    shoulder_mark = mark_distance_from_end_along_centerline(socket_entry_plane, dovetail_timber, dovetail_timber_end)
    shoulder_distance_from_end = shoulder_mark.distance
    assert safe_compare(shoulder_distance_from_end, 0, Comparison.GT), (
        "timber1 must reach past timber2's near face to be dovetailed into it"
    )
    # On timber1's centerline, so profile x = 0 is the middle of the layout.
    marking_origin_global = shoulder_mark.locate().position
    marking_transform = Transform(position=marking_origin_global, orientation=Orientation.from_z_and_y(
        z_direction=slide_direction_global, y_direction=into_socket_direction_global))
    layout_direction_global = marking_transform.orientation.matrix[:, 0]
    front_face_sits_at_negative_profile_x = safe_compare(
        safe_dot_product(front_face_direction_global, layout_direction_global), 0, Comparison.LT
    )

    def profile_x_of(distance_from_front_face: Numeric) -> Numeric:
        """Profile x of a distance measured into timber1 from front_face_on_timber1."""
        if front_face_sits_at_negative_profile_x:
            return -half_layout_dimension + distance_from_front_face
        return half_layout_dimension - distance_from_front_face

    # timber1 lies between its inside and outside faces. Square to the slide, that is the
    # extrusion's length; at an angle the faces are bevelled to it, so the tails run on
    # and are cut off by them.
    half_thickness = dovetail_timber_thickness / scalar(2)
    tail_ends = (-half_thickness, half_thickness) if square_corner else (None, None)

    def between_timber1_faces(csg: CutCSG, label: CutCSGLabel) -> CutCSG:
        """`csg` cut back to timber1's inside and outside faces, at an angle; as is when square."""
        if square_corner:
            return csg
        faces = [HalfSpace(normal=-sign * outside_direction_global, offset=safe_dot_product(
                     -sign * outside_direction_global, marking_origin_global + outside_direction_global * sign * half_thickness),
                     label=CutCSGLabel("dovetail_bevel"))
                 for sign in (scalar(1), scalar(-1))]
        return Intersection(Intersection(csg, faces[0]), faces[1], label=label)

    # -------------------------------------------------------------------------
    # Dovetail profiles, narrow at the shoulder and flaring into timber2
    # -------------------------------------------------------------------------
    dovetail_profiles: List[List[V2]] = []
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
        dovetail_profiles.append([
            create_v2(center_x - half_small_width, scalar(0)),
            create_v2(center_x + half_small_width, scalar(0)),
            create_v2(center_x + half_large_width, depth),
            create_v2(center_x - half_large_width, depth),
        ])

    def dovetail_extrusion(profile: List[V2], overrides) -> CutCSG:
        return ConvexPolygonExtrusion(points=profile, transform=marking_transform, start_distance=tail_ends[0],
                                      end_distance=tail_ends[1], feature_overrides=overrides,
                                      label=CutCSGLabel.NoLabel())

    # A tail's faces belong to the timber that keeps it, so they are named on the
    # dovetail timber's copies. The sockets are cut with plain ones: the walls they
    # leave are the receiving timber's own surfaces, not the tail's.
    dovetails_csg = adopt_csg(None, dovetail_timber.transform, between_timber1_faces(SolidUnion(
        [dovetail_extrusion(profile, _DOVETAIL_FACE_OVERRIDES if square_corner else _BEVELLED_DOVETAIL_FACE_OVERRIDES)
         for profile in dovetail_profiles],
        label=CutCSGLabel("dovetails"),
    ), CutCSGLabel("bevelled_dovetails")))
    sockets_csg = adopt_csg(None, socket_timber.transform, between_timber1_faces(SolidUnion(
        [dovetail_extrusion(profile, ()) for profile in dovetail_profiles],
        label=CutCSGLabel("dovetail_sockets"),
    ), CutCSGLabel("bevelled_dovetail_sockets")))

    # Everything past the shoulder comes away from timber1 except the dovetails. A half
    # space rather than a prism, so material outside the perfect timber within goes too.
    if square_corner:
        shoulder_half_space = chop_timber_end_with_half_plane(
            timber=dovetail_timber,
            end=dovetail_timber_end,
            distance_from_end_to_cut=shoulder_distance_from_end,
            label=CutCSGLabel("shoulder"),
            is_shoulder=True,
        )
    else:
        shoulder_half_space = adopt_csg(None, dovetail_timber.transform, HalfSpace(
            normal=into_socket_direction_global,
            offset=safe_dot_product(into_socket_direction_global, marking_origin_global),
            label=CutCSGLabel("shoulder"),
            feature_overrides=[shoulder_override(HALF_SPACE_PLANE, name="shoulder", group=FeatureGroup.SHOULDER_PLANE)],
        ))
    dovetail_timber_negative_csg: CutCSG = Difference(
        shoulder_half_space, [dovetails_csg], label=CutCSGLabel("dovetail_waste"),
    )
    socket_timber_negative_csg: CutCSG = sockets_csg

    # -------------------------------------------------------------------------
    # End cuts: each timber is cut to the far face of the other
    # note that techincally timber1 could have a shorter maybe end cut if all the tenons are half blind but we don't bother with that. please preserve this comment
    # -------------------------------------------------------------------------
    socket_timber_far_face = socket_entry_face.to.face().get_opposite_face()
    dovetail_timber_end_cut_distance_from_bottom = _end_cut_distance_from_bottom(
        dovetail_timber, dovetail_timber_end,
        get_center_point_on_face_global(socket_timber_far_face, socket_timber),
        socket_timber.get_face_direction_global(socket_timber_far_face),
    )
    socket_timber_end_cut_distance_from_bottom = _end_cut_distance_from_bottom(
        socket_timber, socket_timber_end,
        get_center_point_on_face_global(dovetail_timber_outside_face, dovetail_timber), outside_direction_global,
    )
    if not square_corner:
        # The square end cuts reach the bevel's far corner; these take the rest.
        dovetail_timber_negative_csg = SolidUnion([dovetail_timber_negative_csg, _bevelled_end_cut(
            dovetail_timber, get_center_point_on_face_global(socket_timber_far_face, socket_timber),
            socket_timber.get_face_direction_global(socket_timber_far_face))], label=CutCSGLabel("dovetail_cut"))
        socket_timber_negative_csg = SolidUnion([socket_timber_negative_csg, _bevelled_end_cut(
            socket_timber, get_center_point_on_face_global(dovetail_timber_outside_face, dovetail_timber),
            outside_direction_global)], label=CutCSGLabel("dovetail_socket_cut"))

    # The dovetails only leave their sockets out through timber2's end face, sliding
    # along it for the length of timber1's faces there.
    freed_after = dovetail_timber_thickness / Abs(safe_dot_product(outside_direction_global, slide_direction_global))

    dovetail_timber_cutting = Cutting(
        timber=dovetail_timber,
        maybe_top_end_cut_distance_from_bottom=dovetail_timber_end_cut_distance_from_bottom if dovetail_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=dovetail_timber_end_cut_distance_from_bottom if dovetail_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=dovetail_timber_negative_csg,
        label=CutCSGLabel("dovetail_cut"),
        assembly_freedom=AssemblyFreedom.translation(slide_direction_global, freed_after=freed_after),
    )

    socket_timber_cutting = Cutting(
        timber=socket_timber,
        maybe_top_end_cut_distance_from_bottom=socket_timber_end_cut_distance_from_bottom if socket_timber_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=socket_timber_end_cut_distance_from_bottom if socket_timber_end == TimberEnd.BOTTOM else None,
        negative_csg=socket_timber_negative_csg,
        label=CutCSGLabel("dovetail_socket_cut"),
        assembly_freedom=AssemblyFreedom.translation(-slide_direction_global, freed_after=freed_after),
    )

    return Joint(
        cuttings={
            "dovetail_timber": dovetail_timber_cutting,
            "socket_timber": socket_timber_cutting,
        },
        ticket=JointTicket(joint_type="dovetail_corner"),
        jointAccessories={},
    )


def _end_cut_distance_from_bottom(timber, end: TimberEnd, point_global, normal_global) -> Numeric:
    """Return where to end cut `timber` (from its bottom) so it reaches the plane through `point_global`
    with `normal_global` at every arris: the plane's farthest crossing of the timber's four long arrises."""
    length_direction = timber.get_length_direction_global()
    along = safe_dot_product(normal_global, length_direction)
    crossings = []
    for x in (-timber.size[0] / scalar(2), timber.size[0] / scalar(2)):
        for y in (-timber.size[1] / scalar(2), timber.size[1] / scalar(2)):
            arris_bottom = timber.transform.local_to_global(create_v3(x, y, scalar(0)))
            crossings.append(safe_dot_product(normal_global, point_global - arris_bottom) / along)
    return Max(*crossings) if end == TimberEnd.TOP else Min(*crossings)


def _bevelled_end_cut(timber, point_global, normal_global) -> CutCSG:
    """Return what lies past the plane through `point_global` (`normal_global` pointing away from the
    timber's body), in `timber`'s local space: an end cut at a bevel."""
    return adopt_csg(None, timber.transform, HalfSpace(
        normal=normal_global, offset=safe_dot_product(normal_global, point_global), label=CutCSGLabel("bevelled_end_cut"),
        feature_overrides=[FeatureOverride(HALF_SPACE_PLANE, properties=FeatureProperties(group=FeatureGroup.END_CUT))]))
