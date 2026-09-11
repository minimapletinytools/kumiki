"""
Kumiki - Decorative joint construction functions
"""

import warnings
from typing import Dict, List, Optional, Tuple, Union

from kumiki.timber import BlockLike, TimberEdge, TimberEnd, TimberFace, TimberLongFace, TimberShortEdge, Cutting, Joint, JointTicket
from kumiki.rule import Numeric, Comparison, safe_compare, safe_zero_test, scalar, create_v2, Transform, Orientation, Abs, Matrix, degrees, safe_normalize_vector, safe_dot_product, cos, sin
from kumiki.cutcsg import RectangularPrism, Cylinder, Difference, SolidUnion, adopt_csg, CutCSGLabel, HalfSpace
from kumiki.pathcsg import PathSegment, StraightSegment, Path, PathExtrusion
from kumiki.measuring import get_center_point_on_face_global


_EDGE_ADJACENT_FACES: Dict[TimberEdge, Tuple[TimberFace, TimberFace]] = {
    TimberEdge.RIGHT_FRONT: (TimberFace.RIGHT, TimberFace.FRONT),
    TimberEdge.FRONT_LEFT:  (TimberFace.FRONT, TimberFace.LEFT),
    TimberEdge.LEFT_BACK:   (TimberFace.LEFT,  TimberFace.BACK),
    TimberEdge.BACK_RIGHT:  (TimberFace.BACK,  TimberFace.RIGHT),

    TimberEdge.BOTTOM_RIGHT: (TimberFace.BOTTOM, TimberFace.RIGHT),
    TimberEdge.BOTTOM_FRONT: (TimberFace.BOTTOM, TimberFace.FRONT),
    TimberEdge.BOTTOM_LEFT:  (TimberFace.BOTTOM, TimberFace.LEFT),
    TimberEdge.BOTTOM_BACK:  (TimberFace.BOTTOM, TimberFace.BACK),

    TimberEdge.TOP_RIGHT: (TimberFace.TOP, TimberFace.RIGHT),
    TimberEdge.TOP_FRONT: (TimberFace.TOP, TimberFace.FRONT),
    TimberEdge.TOP_LEFT:  (TimberFace.TOP, TimberFace.LEFT),
    TimberEdge.TOP_BACK:  (TimberFace.TOP, TimberFace.BACK),
}


def _available_extent_in_face_normal_axis(timber: BlockLike, face: TimberFace) -> Numeric:
    """Distance from the timber's centerline out to `face` -- or, for
    TOP/BOTTOM, the timber's declared length. This doubles as the maximum
    radius that can be carved from that face before passing the centerline
    (or the opposite declared end).
    """
    if face in (TimberFace.TOP, TimberFace.BOTTOM):
        return timber.length
    return timber.get_size_in_face_normal_axis(face) / scalar(2)


def _rough_excess_in_face_normal_axis(timber: BlockLike, face: TimberFace) -> Numeric:
    """Extra distance the rough-stock boundary extends beyond the
    perfect timber's boundary in the direction of `face`.

    Always 0 for TOP/BOTTOM: edges on the timber's ends are pinned to the
    declared length rather than any not-yet-known maybe_end_cut extension
    (see cut_practice_roundover_decoration).
    """
    if face in (TimberFace.TOP, TimberFace.BOTTOM):
        return scalar(0)
    return timber.get_half_rough_size_in_face_normal_axis(face) - _available_extent_in_face_normal_axis(timber, face)


def _roundover_cut_for_edge(timber: BlockLike, edge: TimberEdge, radius: Numeric) -> Difference:
    """Build the negative CSG (in GLOBAL coordinates) that rounds over one
    edge of `timber` with the given radius.

    Starts from the edge's perfect (finished-dimension) corner, builds a
    cylinder of `radius` tangent to both adjacent faces running the length of
    the edge, and a square prism spanning from that cylinder out to the
    rough-stock corner -- so any imperfect excess material beyond
    the perfect corner is also removed -- then subtracts the cylinder from
    the prism to leave a quarter-round fillet-shaped negative volume.
    """
    face_a, face_b = _EDGE_ADJACENT_FACES[edge]
    start_corner, direction_face = edge.canonical_line_from_corner()

    for face in (face_a, face_b):
        available = _available_extent_in_face_normal_axis(timber, face)
        assert safe_compare(available - radius, 0, Comparison.GE), (
            f"radius {radius} is too large for edge {edge.name} "
            f"(only {available} of material available toward {face.name})"
        )

    dir_a = timber.get_face_direction_global(face_a)
    dir_b = timber.get_face_direction_global(face_b)
    edge_dir = timber.get_face_direction_global(direction_face)

    perfect_corner_start = timber.get_corner_position_global(start_corner)

    start_distance = None
    end_distance = None

    cylinder = Cylinder(
        axis_direction=edge_dir,
        radius=radius,
        position=perfect_corner_start - dir_a * radius - dir_b * radius,
        start_distance=start_distance,
        end_distance=end_distance,
        label=CutCSGLabel("roundover_fillet"),
    )

    excess_a = _rough_excess_in_face_normal_axis(timber, face_a)
    excess_b = _rough_excess_in_face_normal_axis(timber, face_b)

    profile_orientation = Orientation(Matrix([
        [dir_a[0], dir_b[0], edge_dir[0]],
        [dir_a[1], dir_b[1], edge_dir[1]],
        [dir_a[2], dir_b[2], edge_dir[2]],
    ]))
    prism = RectangularPrism(
        size=Matrix([excess_a + radius, excess_b + radius]),
        transform=Transform(
            position=(
                perfect_corner_start
                + dir_a * ((excess_a - radius) / scalar(2))
                + dir_b * ((excess_b - radius) / scalar(2))
            ),
            orientation=profile_orientation,
        ),
        start_distance=start_distance,
        end_distance=end_distance,
        label=CutCSGLabel("roundover_corner_waste"),
    )

    return Difference(base=prism, subtract=[cylinder], label=CutCSGLabel(f"roundover_{edge.name.lower()}"))


def cut_practice_roundover_decoration(timber: BlockLike, edges: List[TimberEdge], radius: Numeric) -> Joint:
    """
    Cuts a roundover of radius `radius` along edges of timber.
    Short edges (edges on the timber ends) are at the declared length of the timber rather than the maybe_end_cut length (which is not known here).
    Note, this does not check if round radii overlap.
    """
    assert edges, "cut_practice_roundover_decoration needs at least one edge to round over"

    edge_cuts_global = [_roundover_cut_for_edge(timber, edge, radius) for edge in edges]

    negative_csg = adopt_csg(
        None,
        timber.transform,
        SolidUnion(children=edge_cuts_global, label=CutCSGLabel("roundover_decoration")),
    )

    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label=CutCSGLabel("roundover_decoration"),
    )
    return Joint(
        cuttings={timber.ticket.path: cutting},
        ticket=JointTicket(joint_type="roundover_decoration"),
    )


def cut_practice_rounded_end_decoration(
    timber: BlockLike,
    rounded_face: TimberFace,
    rounded_end: TimberFace,
    radius: Numeric,
    distance_from_end: Numeric,
    lateral_offset: Numeric = 0,
) -> Joint:
    """
    Rounds off `rounded_end` of `timber` with a single large-radius arc spanning
    the full width perpendicular to both `rounded_face` and `rounded_end` -- a
    gentle bowed/bullnose end profile, visible as a curved outline when looking
    straight at `rounded_face` (the arc's plane is perpendicular to
    `rounded_face`'s normal, i.e. that normal is the cylinder's own axis).
    """
    if safe_compare(distance_from_end, radius, Comparison.LT):
        warnings.warn(
            f"cut_practice_rounded_end_decoration: distance_from_end ({distance_from_end}) is less than "
            f"radius ({radius}) on {timber.ticket.path}'s {rounded_end.name} -- the lateral center will "
            f"stay flat/unrounded and only the corners will be filleted, rather than a single continuous "
            f"arc across the whole width.",
            stacklevel=2,
        )

    span_face = rounded_end.rotate_about(rounded_face)

    axis_dir = timber.get_face_direction_global(rounded_face)
    end_dir = timber.get_face_direction_global(rounded_end)
    span_dir = timber.get_face_direction_global(span_face)

    half_span_reach = _available_extent_in_face_normal_axis(timber, span_face)
    assert safe_compare(radius - (half_span_reach + Abs(lateral_offset)), 0, Comparison.GE), (
        f"radius {radius} is too small to span {rounded_end.name}'s full width from a lateral offset of "
        f"{lateral_offset} (needs at least {half_span_reach + Abs(lateral_offset)})"
    )

    end_reference = get_center_point_on_face_global(rounded_end, timber) + span_dir * lateral_offset
    cylinder_center = end_reference - end_dir * distance_from_end

    cylinder = Cylinder(
        axis_direction=axis_dir,
        radius=radius,
        position=cylinder_center,
        start_distance=-timber.get_half_rough_size_in_face_normal_axis(rounded_face.get_opposite_face()),
        end_distance=timber.get_half_rough_size_in_face_normal_axis(rounded_face),
        label=CutCSGLabel("rounded_end_arc"),
    )

    prism_orientation = Orientation(Matrix([
        [span_dir[0], axis_dir[0], end_dir[0]],
        [span_dir[1], axis_dir[1], end_dir[1]],
        [span_dir[2], axis_dir[2], end_dir[2]],
    ]))
    prism_span_size = scalar(2) * (half_span_reach + Abs(lateral_offset) + radius)
    prism_axis_size = (
        timber.get_half_rough_size_in_face_normal_axis(rounded_face)
        + timber.get_half_rough_size_in_face_normal_axis(rounded_face.get_opposite_face())
    )
    prism = RectangularPrism(
        size=Matrix([prism_span_size, prism_axis_size]),
        transform=Transform(position=end_reference, orientation=prism_orientation),
        start_distance=-distance_from_end,
        end_distance=radius,
        label=CutCSGLabel("rounded_end_waste"),
    )

    negative_csg = adopt_csg(
        None,
        timber.transform,
        Difference(base=prism, subtract=[cylinder], label=CutCSGLabel("rounded_end_decoration")),
    )
    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label=CutCSGLabel("rounded_end_decoration"),
    )
    return Joint(
        cuttings={timber.ticket.path: cutting},
        ticket=JointTicket(joint_type="rounded_end_decoration"),
    )


def cut_practice_rafter_tail_scallop_corner_end_decoration(
    timber: BlockLike,
    short_edge: Union[TimberShortEdge],
    scallop_height: Numeric,
    scallop_length: Numeric,
) -> Joint:
    """
    _______________
                   |
    ______________◜  ←scallop_height
                ↑
                scallop_width
    """
    assert safe_compare(scallop_length, 0, Comparison.GT), "scallop_length must be positive"
    assert safe_compare(scallop_height, 0, Comparison.GT), "scallop_height must be positive"

    end_side = short_edge.end
    cut_side = short_edge.long_face

    end_face = end_side.to.face()
    cut_face = cut_side.to.face()

    end_direction = timber.get_face_direction_global(end_face)
    cut_direction = timber.get_face_direction_global(cut_face)
    origin = (
        get_center_point_on_face_global(end_face, timber)
        + cut_direction * (timber.get_size_in_face_normal_axis(cut_face) / scalar(2))
    )

    radius = (scallop_length * scallop_length + scallop_height * scallop_height) / (scalar(2) * scallop_height)
    center = origin - cut_direction * (scallop_height - radius)

    perp_face = cut_face.rotate_about(end_face)
    perp_face_opposite = perp_face.get_opposite_face()
    cylinder = Cylinder(
        axis_direction=timber.get_face_direction_global(perp_face),
        radius=radius,
        position=center,
        start_distance=-timber.get_half_rough_size_in_face_normal_axis(perp_face_opposite),
        end_distance=timber.get_half_rough_size_in_face_normal_axis(perp_face),
        label=CutCSGLabel("scallop_arc"),
    )

    negative_csg = adopt_csg(None, timber.transform, cylinder)
    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label=CutCSGLabel("rafter_tail_scallop_decoration"),
    )
    return Joint(
        cuttings={timber.ticket.path: cutting},
        ticket=JointTicket(joint_type="rafter_tail_scallop_decoration"),
    )


def _line_if_nondegenerate(a: Matrix, b: Matrix) -> Optional[StraightSegment]:
    if safe_zero_test(a[0] - b[0]) and safe_zero_test(a[1] - b[1]):
        return None
    return StraightSegment(a, b)


def cut_practice_path_extrusion_corner_end_decoration(
    timber: BlockLike,
    cut_corner: TimberShortEdge,
    cut_path: List[PathSegment],
) -> Joint:
    """
    path coordinates is based on cut_corner

    +y
    |
    |________
    |________|__ +x
    ^
    cut_corner
    """
    assert len(cut_path) > 0, "cut_path must have at least one segment"

    end_side = cut_corner.end
    cut_side = cut_corner.long_face
    end_face = end_side.to.face()
    cut_face = cut_side.to.face()

    end_direction = timber.get_face_direction_global(end_face)
    cut_direction = timber.get_face_direction_global(cut_face)
    origin = (
        get_center_point_on_face_global(end_face, timber)
        + cut_direction * (timber.get_size_in_face_normal_axis(cut_face) / scalar(2))
    )
    local_x_dir = -end_direction
    local_y_dir = -cut_direction

    perp_face = cut_face.rotate_about(end_face)
    perp_face_opposite = perp_face.get_opposite_face()
    extrusion_dir = timber.get_face_direction_global(perp_face)

    orientation = Orientation(Matrix([
        [local_x_dir[0], local_y_dir[0], extrusion_dir[0]],
        [local_x_dir[1], local_y_dir[1], extrusion_dir[1]],
        [local_x_dir[2], local_y_dir[2], extrusion_dir[2]],
    ]))

    path_start = cut_path[0].start
    path_end = cut_path[-1].end
    y_rough = -_rough_excess_in_face_normal_axis(timber, cut_face)

    loop_start = create_v2(scalar(0), path_start[1])
    rough_near_end = create_v2(scalar(0), y_rough)
    rough_near_path_end = create_v2(path_end[0], y_rough)

    segments: List[PathSegment] = []
    start_connector = _line_if_nondegenerate(loop_start, path_start)
    if start_connector is not None:
        segments.append(start_connector)
    segments.extend(cut_path)
    for a, b in ((path_end, rough_near_path_end), (rough_near_path_end, rough_near_end), (rough_near_end, loop_start)):
        closing_segment = _line_if_nondegenerate(a, b)
        if closing_segment is not None:
            segments.append(closing_segment)

    loop = Path(segments)
    if safe_compare(loop.signed_area(), 0, Comparison.LT):
        loop = loop.reversed()
    assert loop.is_valid(), (
        f"cut_practice_path_extrusion_corner_end_decoration: constructed cut path for "
        f"{cut_corner.name} is not a valid simple loop -- check cut_path connectivity"
    )

    extrusion = PathExtrusion(
        path=loop,
        transform=Transform(position=origin, orientation=orientation),
        start_distance=-timber.get_half_rough_size_in_face_normal_axis(perp_face_opposite),
        end_distance=timber.get_half_rough_size_in_face_normal_axis(perp_face),
        label=CutCSGLabel("path_extrusion_decoration"),
    )

    negative_csg = adopt_csg(None, timber.transform, extrusion)
    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label=CutCSGLabel("path_extrusion_corner_end_decoration"),
    )
    return Joint(
        cuttings={timber.ticket.path: cutting},
        ticket=JointTicket(joint_type="path_extrusion_corner_end_decoration"),
    )


def cut_practice_straight_angled_end_cut_decoration(
    timber: BlockLike,
    front_face: TimberFace,
    position_from_end: Numeric,
    angle: Numeric = degrees(0),
    angle_towards_face: Optional[TimberFace] = None,
    timber_end: Union[TimberEnd, TimberFace] = TimberEnd.TOP,
) -> Joint:
    """
    Cuts a straight angled cut on `timber_end` of `timber`.

    Looking straight at `front_face` (the face from which the angled cut outline
    is visible), the cut is angled by `angle` (0 is perpendicular to the length axis)
    and passes through `timber`'s centerline at distance `position_from_end` from `timber_end`.

    ____________
    front_face  \\      <-timber_end
    _____________\\
    """
    timber_end_face = timber_end.to.face()
    assert timber_end_face in (TimberFace.TOP, TimberFace.BOTTOM), (
        f"timber_end must be TOP or BOTTOM, got {timber_end}"
    )

    front_face_val = front_face.to.face()
    assert front_face_val in (TimberFace.RIGHT, TimberFace.FRONT, TimberFace.LEFT, TimberFace.BACK), (
        f"front_face must be a long face (RIGHT, FRONT, LEFT, BACK), got {front_face}"
    )

    span_face = timber_end_face.rotate_about(front_face_val)
    if angle_towards_face is None:
        towards_face = span_face
    else:
        towards_face = angle_towards_face.to.face()
        assert towards_face in (span_face, span_face.get_opposite_face()), (
            f"angle_towards_face must be one of the faces perpendicular to front_face and length axis "
            f"({span_face.name} or {span_face.get_opposite_face().name}), got {towards_face.name}"
        )

    assert safe_compare(Abs(angle), degrees(90), Comparison.LT), (
        f"angle ({angle}) must be strictly between -90 and +90 degrees"
    )
    assert safe_compare(position_from_end, 0, Comparison.GE), (
        f"position_from_end ({position_from_end}) must be non-negative"
    )
    assert safe_compare(position_from_end, timber.length, Comparison.LE), (
        f"position_from_end ({position_from_end}) cannot exceed timber length ({timber.length})"
    )

    end_dir = timber.get_face_direction_global(timber_end_face)
    towards_dir = timber.get_face_direction_global(towards_face)
    end_center_global = get_center_point_on_face_global(timber_end_face, timber)
    pivot_global = end_center_global - end_dir * position_from_end

    cut_normal_global = safe_normalize_vector(cos(angle) * end_dir + sin(angle) * towards_dir)
    offset_global = safe_dot_product(pivot_global, cut_normal_global)

    half_space_global = HalfSpace(
        normal=cut_normal_global,
        offset=offset_global,
        label=CutCSGLabel("straight_angled_end_cut"),
    )

    negative_csg = adopt_csg(None, timber.transform, half_space_global)
    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label=CutCSGLabel("straight_angled_end_cut_decoration"),
    )
    return Joint(
        cuttings={timber.ticket.path: cutting},
        ticket=JointTicket(joint_type="straight_angled_end_cut_decoration"),
    )
