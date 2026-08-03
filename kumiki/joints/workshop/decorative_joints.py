"""
Kumiki - Decorative joint construction functions
"""

from typing import Dict, List, Tuple

from sympy import Matrix

from kumiki.timber import BlockLike, TimberEdge, TimberFace, Cutting, Joint, JointTicket
from kumiki.rule import Numeric, Comparison, safe_compare, scalar, Transform, Orientation
from kumiki.cutcsg import RectangularPrism, Cylinder, Difference, SolidUnion, adopt_csg


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


def _nominal_excess_in_face_normal_axis(timber: BlockLike, face: TimberFace) -> Numeric:
    """Extra distance the nominal (rough-stock) boundary extends beyond the
    perfect timber's boundary in the direction of `face`.

    Always 0 for TOP/BOTTOM: edges on the timber's ends are pinned to the
    declared length rather than any not-yet-known maybe_end_cut extension
    (see cut_practice_roundover_decoration).
    """
    if face in (TimberFace.TOP, TimberFace.BOTTOM):
        return scalar(0)
    return timber.get_half_nominal_size_in_face_normal_axis(face) - _available_extent_in_face_normal_axis(timber, face)


def _roundover_cut_for_edge(timber: BlockLike, edge: TimberEdge, radius: Numeric) -> Difference:
    """Build the negative CSG (in GLOBAL coordinates) that rounds over one
    edge of `timber` with the given radius.

    Starts from the edge's perfect (finished-dimension) corner, builds a
    cylinder of `radius` tangent to both adjacent faces running the length of
    the edge, and a square prism spanning from that cylinder out to the
    nominal (rough-stock) corner -- so any imperfect excess material beyond
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

    excess_a = _nominal_excess_in_face_normal_axis(timber, face_a)
    excess_b = _nominal_excess_in_face_normal_axis(timber, face_b)

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




#_______________
#               |
#______________◜  ←scallop_height
#      ↑       ↑
#      |       scallop_width
#    cut_side

def cut_practice_rafter_tail_scallop_decoration(timber: TimberLike, end_side: TimberEnd, cut_side: TimberLongFace, scallop_height: Numeric, scallop_length: Numeric) -> Joint:
    """
    cuts out a "scallop" shape from cut_side from scallop_height measured up from cut_side on the end_side
    to scallop_width measured inwards from the end on the cut_side
    the scallop is the circle touching the 2 points above such that the circle is peprendicular with the end_side face.
    """

    # set the marking space where the centerplane of the timber intersects cut_side face and the end_side face (there are 2 centerplanse and only one of them intersect the 2 faces)
    # the +x axis points towards end_side direction and the +y axis pointing away from the cut_side face direciton
    # from this point, go up by scallop_height to find point A and left by scallop_width to find point B
    # find that touch both point A and B and is perpendicular to the end_side face at point A, the circle is in the centerpalne of the timber (the same one we intersected)
    # create a cylinder that reaches to both sides of the actual timber (so rotate cut_face  by 90, and then find its half nominal dimensions to determine extrusion distances)

    # return the joint with the cylinder as its negative csg
    pass