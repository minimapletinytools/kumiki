"""
Kumiki - Decorative joint construction functions
"""

from typing import Dict, List, Tuple

from sympy import Matrix

from kumiki.timber import BlockLike, TimberEdge, TimberEnd, TimberFace, TimberLongFace, Cutting, Joint, JointTicket
from kumiki.rule import Numeric, Comparison, safe_compare, scalar, Transform, Orientation
from kumiki.cutcsg import RectangularPrism, Cylinder, Difference, SolidUnion, adopt_csg
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
    #warn if distance_from_end is less than radius
    assert "not implemneted"
#_______________
#               |
#______________◜  ←scallop_height
#      ↑       ↑
#      |       scallop_width
#    cut_side

def cut_practice_rafter_tail_scallop_decoration(
    timber: BlockLike,
    end_side: TimberEnd,
    cut_side: TimberLongFace,
    scallop_height: Numeric,
    scallop_length: Numeric,
) -> Joint:
    """
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
        timber:
        end_side:
        cut_side:
        scallop_height:
        scallop_length:

    Returns:
    """
    assert safe_compare(scallop_length, 0, Comparison.GT), "scallop_length must be positive"
    assert safe_compare(scallop_height, 0, Comparison.GT), "scallop_height must be positive"

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