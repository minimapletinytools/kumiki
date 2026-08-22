"""
Kumiki - Board joint construction functions
Contains functions for creating joints between boards.
"""

import warnings
from dataclasses import replace
from typing import Dict, List, Tuple, Union, Optional

from kumiki.timber import AssemblyFreedom, Board, TimberFace, Cutting, Joint, JointTicket, require_check
from kumiki.rule import (
    Numeric,
    V3,
    Matrix,
    cos,
    tan,
    scalar,
    create_v2,
    Comparison,
    safe_compare,
    safe_dot_product,
    safe_normalize_vector,
    safe_equality_test,
)
from kumiki.cutcsg import (
    RectangularPrism,
    ConvexPolygonExtrusion,
    SolidUnion,
    Difference,
    Intersection,
    HalfSpace,
    adopt_csg,
)
from kumiki.construction import (
    Transform,
    Orientation,
    ButtJointBoardArrangement,
    PanelBoardArrangement,
    ExtendedTimberArrangement,
)
from kumiki.measuring import locate_face


def cut_tongue_and_groove_joint(
    tongue_board: Board,
    groove_board: Board,
    tongue_depth: Numeric,
    tongue_width: Numeric,
    tongue_center_offset: Numeric = scalar(0),
    groove_extra_depth: Numeric = scalar(0),
) -> Joint:
    """
    Cuts a tongue and groove joint between two boards. The tongue and groove run
    length-wise on the boards with tongue_depth in the X axis and tongue_width
    in the Y axis; hence the tongue and grooves are always on the left/right
    side faces of the board.

    The tongue is centered on the left or right side face of tongue_board and
    the tip of the tongue lines up with that side face.

    The side is determined by the position of the groove board: if the groove
    board is to the left of the tongue board the tongue is cut on the left face
    of the tongue board and the groove is cut on the right face of the groove
    board, and vice versa.

    The groove on the groove board is aligned to the tongue.

    The groove board must overlap the tongue board by at least tongue_depth so
    enough wood is available to cut the groove.

    Args:
        tongue_board: Board with the protruding tongue on one of its side faces.
        groove_board: Board with the recessed groove that receives the tongue.
        tongue_depth: Depth of the tongue in the X direction.
        tongue_width: Width of the tongue in the Y direction.
        tongue_center_offset: Offset of the tongue center along the board Y axis (default 0).
        groove_extra_depth: Extra depth to cut into the groove board beyond tongue_depth.

    Returns:
        Joint with one Cutting per board, both labeled "tongue_and_groove".
    """

    # --- Same orientation between boards (element-wise on the rotation matrix) ---
    for r in range(3):
        for c in range(3):
            assert safe_equality_test(
                tongue_board.transform.orientation.matrix[r, c],
                groove_board.transform.orientation.matrix[r, c],
            ), "tongue board and groove board must have the same orientation"

    # Warn if the tongue board appears thicker than wide (likely flipped).
    if not safe_compare(tongue_board.size[0] - tongue_board.size[1], 0, Comparison.GT):
        warnings.warn(
            "board orientation appears to be thicker than it is wide, "
            "are you sure you oriented your board correctly"
        )

    # --- Determine which side the groove board sits on, in tongue board local coords ---
    groove_pos_in_tongue_local = tongue_board.transform.global_to_local(
        groove_board.transform.position
    )
    groove_x_in_tongue_local = groove_pos_in_tongue_local[0]
    groove_y_in_tongue_local = groove_pos_in_tongue_local[1]

    tongue_half_width = tongue_board.size[0] / scalar(2)
    tongue_half_thickness = tongue_board.size[1] / scalar(2)
    groove_half_width = groove_board.size[0] / scalar(2)
    groove_half_thickness = groove_board.size[1] / scalar(2)

    # side_sign = -1 if groove board is to the LEFT of tongue board (tongue on LEFT face),
    # side_sign = +1 if groove board is to the RIGHT (tongue on RIGHT face).
    if safe_compare(groove_x_in_tongue_local, 0, Comparison.LT):
        side_sign = scalar(-1)
        x_overlap = (groove_x_in_tongue_local + groove_half_width) - (-tongue_half_width)
    else:
        side_sign = scalar(1)
        x_overlap = tongue_half_width - (groove_x_in_tongue_local - groove_half_width)

    if not safe_compare(x_overlap - tongue_depth, 0, Comparison.GE):
        warnings.warn(
            "groove board does not overlap tongue board enough to cut the groove"
        )

    # --- Thickness (Y) overlap checks ---
    tongue_y_low = tongue_center_offset - tongue_width / scalar(2)
    tongue_y_high = tongue_center_offset + tongue_width / scalar(2)

    groove_y_low = groove_y_in_tongue_local - groove_half_thickness
    groove_y_high = groove_y_in_tongue_local + groove_half_thickness

    tongue_board_y_low = -tongue_half_thickness
    tongue_board_y_high = tongue_half_thickness

    no_thickness_overlap = (
        safe_compare(groove_y_high - tongue_board_y_low, 0, Comparison.LE)
        or safe_compare(groove_y_low - tongue_board_y_high, 0, Comparison.GE)
    )
    assert not no_thickness_overlap, (
        "groove board does not overlap tongue board at all, cannot cut joint"
    )

    if safe_compare(groove_y_low - tongue_y_low, 0, Comparison.GT) or safe_compare(
        tongue_y_high - groove_y_high, 0, Comparison.GT
    ):
        warnings.warn(
            "groove board does not overlap tongue, groove may be incomplete"
        )

    # --- Cut tongue on the tongue board ---
    # Reference tongue prism (positive tongue volume) in tongue board local coords:
    #   X: from side face inward by tongue_depth
    #   Y: centered at tongue_center_offset with height tongue_width
    #   Z: 0 .. tongue_board.length
    face_x = side_sign * tongue_half_width
    inside_x = face_x - side_sign * tongue_depth
    ref_x_center = (face_x + inside_x) / scalar(2)
    ref_x_size = tongue_depth

    # Top negative cut: covers the region above the tongue, up to the board's top face.
    top_neg_y_low = tongue_y_high
    top_neg_y_high = tongue_board_y_high
    top_neg_y_size = top_neg_y_high - top_neg_y_low
    top_neg_y_center = (top_neg_y_low + top_neg_y_high) / scalar(2)

    top_neg_prism = RectangularPrism(
        size=Matrix([ref_x_size, top_neg_y_size]),
        transform=Transform(
            position=Matrix([ref_x_center, top_neg_y_center, scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=tongue_board.length,
        label="tongue_top_remove",
    )

    # Bottom negative cut: mirror of top.
    bot_neg_y_low = tongue_board_y_low
    bot_neg_y_high = tongue_y_low
    bot_neg_y_size = bot_neg_y_high - bot_neg_y_low
    bot_neg_y_center = (bot_neg_y_low + bot_neg_y_high) / scalar(2)

    bot_neg_prism = RectangularPrism(
        size=Matrix([ref_x_size, bot_neg_y_size]),
        transform=Transform(
            position=Matrix([ref_x_center, bot_neg_y_center, scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=tongue_board.length,
        label="tongue_bottom_remove",
    )

    tongue_neg_csg = SolidUnion(
        children=[top_neg_prism, bot_neg_prism],
        label="tongue_and_groove",
    )

    tongue_cutting = Cutting(
        timber=tongue_board,
        negative_csg=tongue_neg_csg,
        label="tongue_and_groove",
    )

    # --- Cut groove on the groove board ---
    # Convert the tongue positive prism (centered at ref_x_center,
    # tongue_center_offset in tongue board local coords) into groove board local
    # coords so the groove sits exactly where the tongue is, then extend it
    # deeper into the groove board by groove_extra_depth.
    tongue_prism_center_tongue_local = Matrix(
        [ref_x_center, tongue_center_offset, scalar(0)]
    )
    tongue_prism_center_global = tongue_board.transform.local_to_global(
        tongue_prism_center_tongue_local
    )
    tongue_prism_center_groove_local = groove_board.transform.global_to_local(
        tongue_prism_center_global
    )

    # Boards share orientation, so the X axis matches in both local frames.
    # Deeper into the groove board (away from the tongue board) is the +side_sign
    # direction in groove local X.
    groove_x_size = tongue_depth + groove_extra_depth
    groove_x_center = (
        tongue_prism_center_groove_local[0]
        + side_sign * groove_extra_depth / scalar(2)
    )
    groove_y_center = tongue_prism_center_groove_local[1]
    groove_y_size = tongue_width

    groove_prism = RectangularPrism(
        size=Matrix([groove_x_size, groove_y_size]),
        transform=Transform(
            position=Matrix([groove_x_center, groove_y_center, scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=groove_board.length,
        label="groove",
    )

    # Trim the overhanging lip of the groove board: cut full thickness and full
    # length from the outer face (the one facing the tongue board) up to where
    # the groove starts (the mouth of the cavity). This removes the material
    # that would otherwise intersect the tongue board.
    groove_outer_face_x = -side_sign * groove_half_width
    groove_mouth_x = (
        tongue_prism_center_groove_local[0]
        - side_sign * tongue_depth / scalar(2)
    )
    trim_x_center = (groove_outer_face_x + groove_mouth_x) / scalar(2)
    trim_x_size = side_sign * (groove_mouth_x - groove_outer_face_x)

    trim_prism = RectangularPrism(
        size=Matrix([trim_x_size, groove_board.size[1]]),
        transform=Transform(
            position=Matrix([trim_x_center, scalar(0), scalar(0)]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=groove_board.length,
        label="groove_excess_trim",
    )

    groove_neg_csg = SolidUnion(
        children=[groove_prism, trim_prism],
        label="tongue_and_groove",
    )

    groove_cutting = Cutting(
        timber=groove_board,
        negative_csg=groove_neg_csg,
        label="tongue_and_groove",
    )

    # Assembly: the boards part along the mating axis (tongue pulls out of the
    # groove after tongue_depth of travel) and can also slide freely along the
    # board length (free after the full board length).
    groove_local_x_global = groove_board.get_width_direction_global()
    tongue_escape_direction = groove_local_x_global * (-side_sign)
    length_direction_global = tongue_board.get_length_direction_global()
    tongue_cutting = replace(
        tongue_cutting,
        assembly_freedom=AssemblyFreedom.combine(
            AssemblyFreedom.translation(tongue_escape_direction, freed_after=tongue_depth),
            AssemblyFreedom.bidirectional_translation(length_direction_global, freed_after=tongue_board.length),
        ),
    )
    groove_cutting = replace(
        groove_cutting,
        assembly_freedom=AssemblyFreedom.combine(
            AssemblyFreedom.translation(-tongue_escape_direction, freed_after=tongue_depth),
            AssemblyFreedom.bidirectional_translation(length_direction_global, freed_after=groove_board.length),
        ),
    )

    return Joint(
        cuttings={
            tongue_board.ticket.path: tongue_cutting,
            groove_board.ticket.path: groove_cutting,
        },
        ticket=JointTicket(joint_type="tongue_and_groove"),
    )


def cut_practice_board_in_grooved_rectangular_frame_joint_on_face_aligned_timbers(
    boards: PanelBoardArrangement,
    frame_timbers: ExtendedTimberArrangement,
) -> Joint:
    """
    fits boards in between the timbers using the board_in_groove_joint

    All timbers must be face aligned and in particluar form a rectangular frame around the boards

    The groove position and depths are based on the boards so the boards are expected to be positioned and sized to where they will fit, in particular no cuts are made on the boards.

    The boards are all expected to be the same thickness and coplanar and form a "rectangle" shape.

    TODO add an optional maybe_end_cut_boards_to_groove_depth parameter. If provided the boards are extended with end cuts to fit into the grooves on the board_top/bottom_end_timbers

    Args:
        boards: Panel of boards to be fitted into the grooves.
        frame_timbers: The surrounding frame timbers (top/bottom/left/right) that will have grooves cut to receive the board panel's edges.
    """
    require_check(boards.check_parallal_coplanar_and_same_thickness())

    board_list = boards.boards
    ref = board_list[0]
    board_thickness = ref.size[1]

    require_check(
        ExtendedTimberArrangement(timbers=[ref, *frame_timbers.timbers]).check_face_aligned()
    )

    # Compute the bounding box of all boards in the reference board's local frame.
    # Board local: X = width, Y = thickness, Z = length.
    # board.transform.position is the bottom center (at Z=0 in board local).
    min_x: Numeric
    max_x: Numeric
    min_y: Numeric
    max_y: Numeric
    min_z: Numeric
    max_z: Numeric

    # Seed from the reference board (always at local origin).
    min_x = -ref.size[0] / scalar(2)
    max_x =  ref.size[0] / scalar(2)
    min_y = -board_thickness / scalar(2)
    max_y =  board_thickness / scalar(2)
    min_z =  scalar(0)
    max_z =  ref.length

    for i, b in enumerate(board_list[1:], start=1):
        # Coplanarity is already guaranteed by the PanelBoardArrangement check above.
        pos_in_ref_local = ref.transform.global_to_local(b.transform.position)
        x_lo = pos_in_ref_local[0] - b.size[0] / scalar(2)
        x_hi = pos_in_ref_local[0] + b.size[0] / scalar(2)
        z_lo = pos_in_ref_local[2]
        z_hi = pos_in_ref_local[2] + b.length
        min_x = min(min_x, x_lo)
        max_x = max(max_x, x_hi)
        min_z = min(min_z, z_lo)
        max_z = max(max_z, z_hi)

    x_center = (min_x + max_x) / scalar(2)
    y_center = (min_y + max_y) / scalar(2)  # = 0 for coplanar boards
    x_size   = max_x - min_x
    y_size   = max_y - min_y
    z_span   = max_z - min_z

    # Build the groove prism in the reference board's local coordinate frame.
    # Subtracting this volume from each frame timber cuts the groove that receives
    # the board panel edges.
    groove_prism_ref_local = RectangularPrism(
        size=Matrix([x_size, y_size]),
        transform=Transform(
            position=Matrix([x_center, y_center, min_z]),
            orientation=Orientation.identity(),
        ),
        start_distance=scalar(0),
        end_distance=z_span,
        label="board_groove",
    )

    # Re-express the groove prism in each frame timber's local coordinate frame
    # and build a Cutting for each timber.
    cuttings: Dict[str, Cutting] = {}
    for timber in frame_timbers.timbers:
        groove_in_timber_local = adopt_csg(
            ref.transform, timber.transform, groove_prism_ref_local
        )
        cuttings[timber.ticket.path] = Cutting(
            timber=timber,
            negative_csg=groove_in_timber_local,
            label="board_in_grooved_frame",
        )

    # Include boards as uncut members so the returned joint can form a complete frame.
    for board in board_list:
        cuttings[board.ticket.path] = Cutting(
            timber=board,
            negative_csg=None,
            label="board_in_grooved_frame",
        )

    # Assembly: no freedoms are set — a panel captured in a 4-sided grooved
    # frame is fully constrained once assembled (the frame must be built
    # around it); there is no single-translation escape to express. The
    # connections are treated as rigid.
    return Joint(
        cuttings=cuttings,
        ticket=JointTicket(joint_type="board_in_grooved_frame"),
    )



def cut_practice_board_in_dado_joint_on_plane_aligned_timbers(boards : PanelBoardArrangement, dado_timbers : ExtendedTimberArrangement, dado_depth : Numeric = scalar(0)):
    """
    cuts boards to fit in dados on dado_timbers. The dadoes are dado_depth deep, so the boards are cut to fit excatly in the dadosinto the grooves on the dado_timbers

    Args:
        boards: A list of boards to be fitted into the dadoes
        dado_timbers: A list of timbers that will have dadoes cut to receive the boards. Dadoes are measured from the perfect timber within of the dado timbers!
    """
    assert False, "not implemented yet"
    # TODO
    # assert boards are all coplanar and have the same thickness
    # assert everything is plane aligned
    # first assemble the boars into a "panel" and determine it's centerlines and it's orientation
    # for each dado timber, run a heuristic to determine which face to cut the dado on, it should be such that "most" of the board is away from the face and the long face is chosen such that it is perpendicular to the board plane
    # for each dado timber, determine the plane that forms the bottom of the dado, give it a normal as wel
    # assert that these planes form a convex shape (could be open, but not concave)
    # cut each of thesee planes from all of the boards that intersect it
    # construct rectangular prisms to form the dadoes, make sure the prism extend sto the acutal timber size not just teh perfect timber within
    # finis the joint and return it
    pass

def _lateral_positive_dovetail_face(butt_timber_face: TimberFace, front_face_on_butt_timber: TimberFace) -> TimberFace:
    """
    The "positive" face (RIGHT, FRONT, or TOP) of whichever axis group is NOT
    used by butt_timber_face or front_face_on_butt_timber.

    Since those two faces are perpendicular (different axis groups), exactly one
    of the three axis groups {RIGHT/LEFT, FRONT/BACK, TOP/BOTTOM} is left over --
    this is the lateral axis. lateral_offset is measured along this face's own
    (positive) direction, regardless of which specific signed face
    (butt_timber_face vs its opposite, etc.) was actually passed in.
    """
    axis_groups = (
        (TimberFace.RIGHT, TimberFace.LEFT),
        (TimberFace.FRONT, TimberFace.BACK),
        (TimberFace.TOP, TimberFace.BOTTOM),
    )
    used_faces = {
        butt_timber_face, butt_timber_face.get_opposite_face(),
        front_face_on_butt_timber, front_face_on_butt_timber.get_opposite_face(),
    }
    for positive_face, _negative_face in axis_groups:
        if positive_face not in used_faces:
            return positive_face
    raise AssertionError(
        "unreachable: butt_timber_face and front_face_on_butt_timber are perpendicular, "
        "so exactly one axis group must be left over for the lateral axis"
    )


def _dovetail_trapezoid_points(
    dovetail_small_width: Numeric,
    dovetail_depth: Numeric,
    dovetail_angle: Numeric,
    lateral_offset: Numeric,
) -> List[V3]:
    """
    The dovetail's cross-sectional trapezoid in the (lateral=u, depth=z) plane,
    narrow at z=0 (the shoulder) and flaring outward by cos(dovetail_angle) per
    unit of depth as z increases (see the ASCII diagram on
    cut_practice_sliding_dovetail_joint_on_orthogonal_boards).
    """
    half_small = dovetail_small_width / scalar(2)
    flare = cos(dovetail_angle) * dovetail_depth
    return [
        create_v2(lateral_offset - half_small, scalar(0)),
        create_v2(lateral_offset - half_small - flare, dovetail_depth),
        create_v2(lateral_offset + half_small + flare, dovetail_depth),
        create_v2(lateral_offset + half_small, scalar(0)),
    ]


#
#   ____
#___\  /___ <-dovetail_depth
#    ^
#    dovetail_small_width
def cut_practice_sliding_dovetail_joint_on_orthogonal_boards(arrangement: ButtJointBoardArrangement, dovetail_depth: Numeric, dovetail_small_width: Numeric, dovetail_angle: Numeric, lateral_offset: Numeric = scalar(0), dovetail_length: Optional[Numeric] = None, shorten_dovetail_by: Numeric = scalar(0), extend_front_dovetail_housing_by: Union[None, Numeric] = scalar(0), taper_angle: Numeric = scalar(0)) -> Joint:
    """
    cuts a sliding dovetail joint, the dovetail slides in from the front_face_on_butt_timber direction

    Args:
        arrangement:
        dovetail_depth: the depth of the dovetail, see diagram
        dovetail_small_width: the width of the smaller part of the dovetail, see diagram
        dovetail_angle: the angle the dovetail expands by from the smaller part of the dovetail
        lateral_offset: offset the dovetail from the centerline by this amount (sign based on local axis of the butting timber and not based on front_face_on_butt_timber)
        dovetail_length: the length of the dovetail on the butting timber, measurement starts from where shorten_dovetail_by defines the start of the dovetail.
        shorten_dovetail_by: shortens the dovetail from front_face_on_butt_timber by this amount
        extend_front_dovetail_housing_by: extend the front side of the dovetail housing from the end of the shortened dovetail by this amount. If `None` extends all the way through. Note that the back side is always extended to the end of the receiving timber so that the joint can be assembled.
        taper_angle: the narrower side is always pointing towards front_face_on_butt_timber

    Returns:
    """
    butt_timber = arrangement.butt_timber
    receiving_timber = arrangement.receiving_timber
    butt_timber_face = arrangement.butt_timber_face
    assert arrangement.front_face_on_butt_timber is not None, (
        "front_face_on_butt_timber is required for cut_practice_sliding_dovetail_joint_on_orthogonal_boards"
    )
    front_face_on_butt_timber = arrangement.front_face_on_butt_timber

    orthogonal_error = arrangement.check_orthogonal()
    assert orthogonal_error is None, orthogonal_error

    # Just assert that all timbers are perfect -- our algorithm doesn't actually
    # need this (every dimension query below is already correct for asymmetric
    # rough_half_sizes), but it's simpler and safer to require it for now.
    perfection_error = arrangement.check_perfection()
    assert perfection_error is None, perfection_error

    depth_dir = butt_timber.get_face_direction_global(butt_timber_face)
    slide_dir = butt_timber.get_face_direction_global(front_face_on_butt_timber)
    lateral_positive_face = _lateral_positive_dovetail_face(butt_timber_face, front_face_on_butt_timber)
    lateral_dir = butt_timber.get_face_direction_global(lateral_positive_face)

    # The entry face in the receiving timber: whichever of its faces points
    # back out toward butt_timber (opposite of the direction butt_timber_face
    # points, since that direction points FROM butt_timber INTO receiving_timber).
    entry_face = receiving_timber.get_closest_oriented_face_from_global_direction(-depth_dir)
    assert receiving_timber.is_face_perfect(entry_face), (
        "receiving_timber's entry face must be perfect"
    )

    # The joint shoulder is just the entry face of the receiving timber.
    shoulder = locate_face(receiving_timber, entry_face)
    front_face_plane = locate_face(butt_timber, front_face_on_butt_timber)

    # Marking space origin: on the centerline of front_face_on_butt_timber
    # (i.e. on that face's own plane, centered laterally) where it intersects
    # the joint shoulder. depth_dir is guaranteed non-perpendicular to
    # shoulder.normal by check_orthogonal (they're parallel), so this
    # line-plane intersection is always well-defined.
    t = safe_dot_product(shoulder.point - front_face_plane.point, shoulder.normal) / safe_dot_product(depth_dir, shoulder.normal)
    marking_origin = front_face_plane.point + depth_dir * t

    def s_coord(point: V3) -> Numeric:
        """Signed distance from marking_origin along slide_dir (the marking space's own 'y' axis)."""
        return safe_dot_product(point - marking_origin, slide_dir)

    # butt_timber's own actual face position, in the depth direction, must
    # extend at least dovetail_depth beyond the shoulder -- otherwise there
    # isn't enough of butt_timber's own material to carve the tongue into.
    butt_face_point = locate_face(butt_timber, butt_timber_face).point
    depth_extent = safe_dot_product(butt_face_point - marking_origin, depth_dir)
    assert safe_compare(depth_extent - dovetail_depth, 0, Comparison.GE), (
        "butt_timber's butting face must extend by at least dovetail_depth beyond the joint shoulder"
    )

    lateral_dimension = butt_timber.get_size_in_face_normal_axis(lateral_positive_face)

    # Slide-axis (s) reference positions, all measured from marking_origin.
    s_butt_front = s_coord(front_face_plane.point)  # == 0 by construction
    s_butt_back = s_coord(locate_face(butt_timber, front_face_on_butt_timber.get_opposite_face()).point)

    receiving_back_face = receiving_timber.get_closest_oriented_face_from_global_direction(-slide_dir)
    receiving_front_face = receiving_back_face.get_opposite_face()
    s_receiving_back = s_coord(locate_face(receiving_timber, receiving_back_face).point)
    s_receiving_front = s_coord(locate_face(receiving_timber, receiving_front_face).point)

    # The tongue itself is set back from butt_timber's own front face by
    # shorten_dovetail_by. From there it either runs all the way to
    # butt_timber's own actual end (dovetail_length=None), or is limited to
    # exactly dovetail_length -- only the tongue is shortened this way; the
    # housing on receiving_timber is untouched by dovetail_length.
    s_tongue_front = s_butt_front - shorten_dovetail_by
    if dovetail_length is None:
        s_tongue_back = s_butt_back
    else:
        s_tongue_back = s_tongue_front - dovetail_length
        assert safe_compare(s_tongue_back - s_butt_back, 0, Comparison.GE), (
            "dovetail_length exceeds the material available on butt_timber past shorten_dovetail_by"
        )

    # The housing's back side always extends to receiving_timber's own actual
    # end (so the joint can be assembled); the front side either extends past
    # the shortened tongue position by extend_front_dovetail_housing_by, or --
    # if None -- all the way through receiving_timber's own front face.
    if extend_front_dovetail_housing_by is None:
        s_housing_front = s_receiving_front
    else:
        s_housing_front = s_tongue_front + extend_front_dovetail_housing_by
    s_housing_back = s_receiving_back

    # Profile transform: local X = lateral, local Y = depth, local Z = slide
    # (the extrusion axis for both ConvexPolygonExtrusion and RectangularPrism
    # below). Matches the pseudocode's marking space convention (+z = depth =
    # butt_timber_face direction, +y = slide = front_face_on_butt_timber
    # direction), just relabeled to fit ConvexPolygonExtrusion's XY-profile /
    # Z-extrusion convention.
    profile_orientation = Orientation(Matrix([
        [lateral_dir[0], depth_dir[0], slide_dir[0]],
        [lateral_dir[1], depth_dir[1], slide_dir[1]],
        [lateral_dir[2], depth_dir[2], slide_dir[2]],
    ]))
    profile_transform = Transform(position=marking_origin, orientation=profile_orientation)

    # taper_angle tapers the ENTIRE dovetail cross-section (independent of
    # depth/z) so it narrows uniformly toward front_face_on_butt_timber,
    # implemented as two half-space clips on top of the (already-flared)
    # untapered shapes below. reduction(s) = tan(taper_angle) * (s -
    # s_receiving_back) -- anchored at s_receiving_back (the housing's
    # mandatory back extent) so the tongue and housing taper identically and
    # still mate exactly at every slide position.
    def _taper_intersection(csg):
        if safe_compare(taper_angle, 0, Comparison.EQ):
            return csg
        taper_k = tan(taper_angle)
        # Generously large so the clip is a no-op at s_receiving_back and only
        # narrows the shape further toward the front.
        clip_half_width = lateral_dimension
        for sign in (scalar(1), scalar(-1)):
            outward_normal = safe_normalize_vector(lateral_dir * sign + slide_dir * taper_k)
            point_on_boundary = marking_origin + lateral_dir * (sign * clip_half_width) + slide_dir * s_receiving_back
            inward_normal = -outward_normal
            offset = safe_dot_product(inward_normal, point_on_boundary)
            csg = Intersection(csg, HalfSpace(normal=inward_normal, offset=offset))
        return csg

    def _trapezoid_extrusion(s_start: Numeric, s_end: Numeric, label: str):
        points = _dovetail_trapezoid_points(dovetail_small_width, dovetail_depth, dovetail_angle, lateral_offset)
        extrusion = ConvexPolygonExtrusion(
            points=points,
            transform=profile_transform,
            start_distance=s_start,
            end_distance=s_end,
            label=label,
        )
        assert extrusion.is_valid(), f"dovetail trapezoid profile is not a valid convex polygon (label={label})"
        return _taper_intersection(extrusion)

    def _full_depth_box(s_start: Numeric, s_end: Numeric, label: str):
        """Plain box spanning butt_timber's own full actual depth extent
        (lateral_dimension x depth_extent), over a given slide-axis range --
        used to clear away material where no tongue exists at all."""
        transform = Transform(
            position=marking_origin + depth_dir * (depth_extent / scalar(2)),
            orientation=profile_orientation,
        )
        return RectangularPrism(
            size=Matrix([lateral_dimension, depth_extent]),
            transform=transform,
            start_distance=s_start,
            end_distance=s_end,
            label=label,
        )

    # --- butt_timber's cut: remove everything except the tongue ---
    tongue_cuts: List = []
    if safe_compare(s_tongue_back, s_tongue_front, Comparison.LT):
        # Full box (butt_timber's own actual cross-section) over the tongue's
        # slide range, minus the dovetail trapezoid -- leaves just the tongue
        # sticking out, wings removed.
        box_prism = _full_depth_box(s_tongue_back, s_tongue_front, "dovetail_wings")
        trapezoid_for_tongue = _trapezoid_extrusion(s_tongue_back, s_tongue_front, "dovetail_tongue_profile")
        tongue_cuts.append(Difference(base=box_prism, subtract=[trapezoid_for_tongue]))

    # Near-front clearance cut: for the shortened segment (butt_timber's own
    # front face back to where the tongue starts), no tongue exists at all, so
    # remove butt_timber's FULL depth-axis extent there (not just
    # dovetail_depth) -- otherwise the excess raw material beyond
    # dovetail_depth (present because the canonical/raw arrangement generously
    # overlaps, same as every other joint in this codebase) would still
    # protrude straight through receiving_timber, uncut, in this segment.
    if safe_compare(shorten_dovetail_by, 0, Comparison.GT):
        tongue_cuts.append(_full_depth_box(s_tongue_front, s_butt_front, "dovetail_shortened_clearance"))

    # Near-back clearance cut: dovetail_length can leave the tongue short of
    # butt_timber's own actual end. Only the tongue is shortened this way --
    # the housing on receiving_timber keeps its own full range -- so the same
    # full-depth clearance is needed here too, past the tongue's back end.
    if safe_compare(s_tongue_back - s_butt_back, 0, Comparison.GT):
        tongue_cuts.append(_full_depth_box(s_butt_back, s_tongue_back, "dovetail_length_clearance"))

    assert tongue_cuts, "shorten_dovetail_by/dovetail_length leaves no material for butt_timber's own actual depth extent to cut"
    butt_negative_csg = SolidUnion(children=tongue_cuts, label="sliding_dovetail") if len(tongue_cuts) > 1 else tongue_cuts[0]

    butt_cutting = Cutting(
        timber=butt_timber,
        negative_csg=adopt_csg(None, butt_timber.transform, butt_negative_csg),
        label="sliding_dovetail",
    )

    # --- receiving_timber's cut: the dovetail-shaped housing groove ---
    assert safe_compare(s_housing_back, s_housing_front, Comparison.LT), (
        "extend_front_dovetail_housing_by leaves no housing length to cut"
    )
    housing_csg = _trapezoid_extrusion(s_housing_back, s_housing_front, "dovetail_housing")
    receiving_cutting = Cutting(
        timber=receiving_timber,
        negative_csg=adopt_csg(None, receiving_timber.transform, housing_csg),
        label="sliding_dovetail",
    )

    # Assembly: the tongue slides free of the housing by withdrawing along
    # +slide_dir (the reverse of insertion) for the full housing length.
    escape_freed_after = s_housing_front - s_housing_back
    butt_cutting = replace(
        butt_cutting,
        assembly_freedom=AssemblyFreedom.translation(slide_dir, freed_after=escape_freed_after),
    )
    receiving_cutting = replace(
        receiving_cutting,
        assembly_freedom=AssemblyFreedom.translation(-slide_dir, freed_after=escape_freed_after),
    )

    return Joint(
        cuttings={
            butt_timber.ticket.path: butt_cutting,
            receiving_timber.ticket.path: receiving_cutting,
        },
        ticket=JointTicket(joint_type="sliding_dovetail"),
    )