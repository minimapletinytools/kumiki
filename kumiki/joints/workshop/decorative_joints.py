"""
Kumiki - Decorative joint construction functions
"""

import warnings
from typing import Dict, List, Tuple, Union

from sympy import Abs, Matrix

from kumiki.timber import BlockLike, TimberEdge, TimberEnd, TimberFace, TimberLongFace, TimberShortEdge, Cutting, Joint, JointTicket
from kumiki.rule import Numeric, Comparison, safe_compare, scalar, Transform, Orientation
from kumiki.cutcsg import RectangularPrism, Cylinder, Difference, SolidUnion, adopt_csg
from kumiki.pathcsg import PathSegment
from kumiki.measuring import get_center_point_on_face_global



# The two faces adjacent to each edge -- literally the two faces named in the
# edge's own enum member name (e.g. RIGHT_FRONT is the edge where the RIGHT
# and FRONT faces meet). The edge itself always runs along the one remaining
# axis (e.g. RIGHT_FRONT runs along length/TOP-BOTTOM).
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
    edge_length = timber.get_size_in_face_normal_axis(direction_face)

    cylinder = Cylinder(
        axis_direction=edge_dir,
        radius=radius,
        position=perfect_corner_start - dir_a * radius - dir_b * radius,
        start_distance=scalar(0),
        end_distance=edge_length,
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
        start_distance=scalar(0),
        end_distance=edge_length,
    )

    return Difference(base=prism, subtract=[cylinder], label=f"roundover_{edge.name.lower()}")


def cut_practice_roundover_decoration(timber: BlockLike, edges: List[TimberEdge], radius: Numeric) -> Joint:
    """
    Cuts a roundover of radius `radius` along edges of timber.
    Short edges (edges on the timber ends) are at the declared length of the timber rather than the maybe_end_cut length (which is not known here).
    Note, this does not check if round radii overlap.
    """
    edge_cuts_global = [_roundover_cut_for_edge(timber, edge, radius) for edge in edges]

    negative_csg = None
    if edge_cuts_global:
        negative_csg = adopt_csg(
            None,
            timber.transform,
            SolidUnion(children=edge_cuts_global, label="roundover_decoration"),
        )

    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label="roundover_decoration",
    )
    return Joint(
        cuttings={timber.ticket.path: cutting},
        ticket=JointTicket(joint_type="roundover_decoration"),
    )



def cut_practice_rounded_end_decoration(
    timber: BlockLike,
    # so the round shape is visible on this face
    rounded_face: TimberFace,
    # and the round shape is cut towards this face
    rounded_end: TimberFace,
    radius: Numeric,
    distance_from_end: Numeric,
    lateral_offset: Numeric = 0
) -> Joint:
    """
    Rounds off `rounded_end` of `timber` with a single large-radius arc spanning
    the full width perpendicular to both `rounded_face` and `rounded_end` -- a
    gentle bowed/bullnose end profile, visible as a curved outline when looking
    straight at `rounded_face` (the arc's plane is perpendicular to
    `rounded_face`'s normal, i.e. that normal is the cylinder's own axis).

    The cylinder (of `radius`) is centered `distance_from_end` in from the
    timber's actual `rounded_end` face, offset laterally by `lateral_offset`
    (positive is toward `rounded_end.rotate_about(rounded_face)`). Only the
    material outside that cylinder is removed.

    If `distance_from_end` is less than `radius`, the cylinder's surface passes
    beyond the actual end at the lateral center, so a flat band survives there
    and only the corners get rounded off (a filleted-corner rectangle) rather
    than a single continuous arc spanning the whole width -- a warning is
    raised in that case since it may not be the intended look.
    """
    if safe_compare(distance_from_end, radius, Comparison.LT):
        warnings.warn(
            f"cut_practice_rounded_end_decoration: distance_from_end ({distance_from_end}) is less than "
            f"radius ({radius}) on {timber.ticket.path}'s {rounded_end.name} -- the lateral center will "
            f"stay flat/unrounded and only the corners will be filleted, rather than a single continuous "
            f"arc across the whole width.",
            stacklevel=2,
        )

    # The face perpendicular to both given faces -- the axis the arc spans
    # across (e.g. the board's width, for rounded_face=FRONT/rounded_end=TOP).
    span_face = rounded_end.rotate_about(rounded_face)

    axis_dir = timber.get_face_direction_global(rounded_face)
    end_dir = timber.get_face_direction_global(rounded_end)
    span_dir = timber.get_face_direction_global(span_face)

    half_span_reach = _available_extent_in_face_normal_axis(timber, span_face)
    assert safe_compare(radius - (half_span_reach + Abs(lateral_offset)), 0, Comparison.GE), (
        f"radius {radius} is too small to span {rounded_end.name}'s full width from a lateral offset of "
        f"{lateral_offset} (needs at least {half_span_reach + Abs(lateral_offset)})"
    )

    # Point on the actual end face, at the given lateral offset -- the local
    # origin (start_distance=0 equivalent) for both the prism and the cylinder.
    end_reference = get_center_point_on_face_global(rounded_end, timber) + span_dir * lateral_offset
    cylinder_center = end_reference - end_dir * distance_from_end

    cylinder = Cylinder(
        axis_direction=axis_dir,
        radius=radius,
        position=cylinder_center,
        start_distance=-timber.get_half_rough_size_in_face_normal_axis(rounded_face.get_opposite_face()),
        end_distance=timber.get_half_rough_size_in_face_normal_axis(rounded_face),
    )

    # A generously-oversized prism covering the corner region -- from exactly
    # the cylinder's center distance back to the actual end (tight, since that
    # fully brackets where the cylinder's surface can be, given the assertion
    # above), and comfortably wider than the cross-section in every other
    # direction (harmless -- nothing exists there to over-cut).
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
    )

    negative_csg = adopt_csg(
        None,
        timber.transform,
        Difference(base=prism, subtract=[cylinder], label="rounded_end_decoration"),
    )
    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label="rounded_end_decoration",
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
    

    cuts out a "scallop" shape from cut_side from scallop_height measured up from cut_side on the end_side
    to scallop_width (scallop_length) measured inwards from the end on the cut_side
    the scallop is the circle touching the 2 points above such that the circle is perpendicular with the end_side face.

    The circle crosses the end_side face AT A right angle at the point
    scallop_height above cut_side (its tangent line there runs straight
    through end_side, along its own normal -- so the circle's center lies
    exactly ON the end_side plane), and simply passes through the point
    scallop_length in from the end along cut_side (so there is a slight kink
    there, where the curve meets the flat run of cut_side).

    Args:
        timber: Timber to cut decoration on
        short_edge: The short edge defining the end face and cut face
        scallop_height: Height of scallop measured from cut_side on end_side
        scallop_length: Length of scallop measured inwards from end on cut_side

    Returns:
        Joint containing decorative cutting
    """

    assert safe_compare(scallop_length, 0, Comparison.GT), "scallop_length must be positive"
    assert safe_compare(scallop_height, 0, Comparison.GT), "scallop_height must be positive"

    end_side = short_edge.end
    cut_side = short_edge.long_face

    end_face = end_side.to.face()
    cut_face = cut_side.to.face()

    # Marking space: origin is where the relevant centerplane meets both
    # cut_side and end_side (the midpoint of the edge they share). +x points
    # out through end_side, +y points away from cut_side (back into the timber).
    end_direction = timber.get_face_direction_global(end_face)
    cut_direction = timber.get_face_direction_global(cut_face)
    origin = (
        get_center_point_on_face_global(end_face, timber)
        + cut_direction * (timber.get_size_in_face_normal_axis(cut_face) / scalar(2))
    )

    # Point A: scallop_height up from cut_side, on end_side (local x=0).
    # Point B: scallop_length in from the end, on cut_side (local y=0).
    # Circle through A and B, perpendicular to end_side (i.e. to the local
    # y-axis) at A -- so its center shares A's local x=0 (lies exactly on the
    # end_side plane), offset from A only along local y by the radius.
    radius = (scallop_length * scallop_length + scallop_height * scallop_height) / (scalar(2) * scallop_height)
    center = origin - cut_direction * (scallop_height - radius)

    # The cylinder's axis is the cross-sectional axis perpendicular to both
    # cut_side and the length axis (rotating cut_side 90 degrees about
    # end_side's own axis lands on it); it extrudes across the timber's full
    # actual (rough) width on that axis so the scallop reaches both sides.
    perp_face = cut_face.rotate_about(end_face)
    perp_face_opposite = perp_face.get_opposite_face()
    cylinder = Cylinder(
        axis_direction=timber.get_face_direction_global(perp_face),
        radius=radius,
        position=center,
        start_distance=-timber.get_half_rough_size_in_face_normal_axis(perp_face_opposite),
        end_distance=timber.get_half_rough_size_in_face_normal_axis(perp_face),
    )

    negative_csg = adopt_csg(None, timber.transform, cylinder)
    cutting = Cutting(
        timber=timber,
        negative_csg=negative_csg,
        label="rafter_tail_scallop_decoration",
    )
    return Joint(
        cuttings={timber.ticket.path: cutting},
        ticket=JointTicket(joint_type="rafter_tail_scallop_decoration"),
    )


def cut_path_extrusion_corner_end_decoration(
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

    generally speaking, path coordiantes is a line representing what you want to cut drown from the left end of the timber to the bottom face of the timber (based on the picture above)

    specifically to form the cut out:
    - the 0'th path coordinate is extended to the end of the timber (x = 0)
    - that point is extended vertically to the rough face in the -y direction (relative to the diagram above) 
    - then that point is extended to horizontally to the x coordinate of the last path coordinate
    - finally it is connected to the last path coordinate
    the 0'th path coordinate

    Arguments:
        cut_corner: the corner that is to be cut out, which determines the coordinates of the  path based on the diagram above
        cut_path: the path, which must be drawn from the left edge to the bottom edge based on the diagram above. 
    """
    assert "Not Implemented"