"""
Kumiki - Build-a-Butt-Joint Helpers
Shared helpers for computing shoulder planes and marking spaces for butt joints.

THe general approach to building-a-butt-joint is:

1. compute the shoulder plane which is always parallel to the length axis of the receiving timber and mark where the butt timber centerline intersects the shoulder plane 
3. build positive and negative CSG components for the receiving and butt timbers (some are shared, some are separate depending on the joint) typically (but not always) relative to the shoulder plane and intersection marking
4. compute peg positions and cut peg holes
5. return the resultant CSG cut for each timber

outside of the purview of build-a-butt-joint, finish the joint:

6. (optional) make additional cuts and accessories like splines or wedges which are not supported by build-a-butt-joint
7. assembly and return the final joint
"""

from __future__ import annotations
from typing import NamedTuple

from kumiki.timber import *
from kumiki.measuring import (
    locate_centerline,
    locate_face,
    locate_plane_from_edge_in_direction,
    mark_distance_from_end_along_centerline,
    Space,
    Plane,
    Line,
)
from kumiki.construction import *
from kumiki.rule import *
from kumiki.rule import safe_dot_product, safe_transform_vector
from kumiki.cutcsg import CutCSG

# ============================================================================
# Shoulder Plane
# ============================================================================

def locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(arrangement: ButtJointTimberArrangement, distance_from_centerline: Numeric) -> Plane:
    """
    Computes the shoulder plane of the mortise timber, offset from its centerline toward the tenon.

    The shoulder plane is parallel to the mortise timber's length axis and offset from
    the mortise centerline in the mortise cross-section toward the tenon. Its reference
    point is chosen using the tenon centerline relation.

    Args:
        arrangement: Butt joint arrangement (receiving_timber = mortise, butt_timber = tenon).
        distance_from_centerline: Signed offset from the mortise centerline toward the tenon.
            0 = plane through the mortise centerline. Positive = toward tenon.

    Returns:
        Plane parallel to the mortise length axis, offset by distance_from_centerline
        from the mortise centerline toward the tenon.
    """
    mortise_timber = arrangement.receiving_timber
    tenon_timber = arrangement.butt_timber
    tenon_end = arrangement.butt_timber_end

    mortise_centerline = locate_centerline(mortise_timber)
    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)
    if tenon_end == TimberReferenceEnd.TOP:
        tenon_end_position = tenon_timber.get_bottom_position_global() + tenon_timber.get_length_direction_global() * tenon_timber.length
    else:
        tenon_end_position = tenon_timber.get_bottom_position_global()
    tenon_centerline = Line(-tenon_end_direction, tenon_end_position)
    mortise_length_dir = mortise_timber.get_length_direction_global()

    # Find M = closest point on mortise centerline to tenon centerline
    w = mortise_centerline.point - tenon_centerline.point
    a = safe_dot_product(mortise_centerline.direction, mortise_centerline.direction)
    b = safe_dot_product(mortise_centerline.direction, tenon_centerline.direction)
    c = safe_dot_product(tenon_centerline.direction, tenon_centerline.direction)
    d = safe_dot_product(w, mortise_centerline.direction)
    e = safe_dot_product(w, tenon_centerline.direction)

    denom = a * c - b * b
    denom_is_zero = safe_zero_test(denom)
    if denom_is_zero:
        M = mortise_centerline.point
    else:
        t_mortise = (b * e - c * d) / denom
        M = mortise_centerline.point + mortise_centerline.direction * t_mortise

    # Find P = intersection of tenon centerline with cross-section plane at M
    plane_dot_dir = safe_dot_product(mortise_length_dir, tenon_centerline.direction)
    plane_dot_dir_is_zero = safe_zero_test(plane_dot_dir)
    if plane_dot_dir_is_zero:
        if denom_is_zero:
            P = tenon_centerline.point
        else:
            s_tenon = (a * e - b * d) / denom
            P = tenon_centerline.point + tenon_centerline.direction * s_tenon
    else:
        s = safe_dot_product(mortise_length_dir, M - tenon_centerline.point) / plane_dot_dir
        P = tenon_centerline.point + tenon_centerline.direction * s

    tenon_dir = tenon_centerline.direction
    proj = tenon_dir - mortise_length_dir * safe_dot_product(tenon_dir, mortise_length_dir)
    proj_len_sq = safe_dot_product(proj, proj)
    if not safe_zero_test(proj_len_sq):
        direction_in_plane = normalize_vector(proj)
    else:
        MP = P - M
        mp_len_sq = safe_dot_product(MP, MP)
        if not safe_zero_test(mp_len_sq):
            direction_in_plane = normalize_vector(MP)
        else:
            direction_in_plane = mortise_timber.get_width_direction_global()

    return locate_plane_from_edge_in_direction(
        mortise_timber, TimberCenterline.CENTERLINE, direction_in_plane, distance_from_centerline
    )

@dataclass(frozen=True)
class ButtJointShoulderResult:
    """
    Result of computing a butt joint shoulder plane and its associated marking space.

    Attributes:
        shoulder_plane: The shoulder plane (normal points from mortise centerline toward tenon).
        butt_direction: Direction the butt timber is pointing into the receiving timber.
        marking_space: Located where tenon centerline intersects the shoulder plane, oriented with:
            +X = shoulder_plane.normal (from mortise centerline toward tenon)
            +Y = caller-provided up_direction (orthogonalized)
            +Z = derived via right-hand rule
    """
    shoulder_plane: Plane
    butt_direction: Direction3D
    marking_space: Space


def compute_butt_joint_shoulder(
    arrangement: ButtJointTimberArrangement,
    distance_from_centerline: Numeric,
    up_direction: Direction3D,
) -> ButtJointShoulderResult:
    """
    Compute the shoulder plane and an oriented marking space for a butt joint.

    The marking space is positioned where the tenon (butt) timber's centerline
    intersects the shoulder plane, oriented with:
        +X = shoulder_plane.normal (from mortise centerline toward tenon)
        +Y = up_direction (orthogonalized against +X)
        +Z = right-hand rule cross product

    Args:
        arrangement: Butt joint arrangement (receiving_timber = mortise, butt_timber = tenon).
        distance_from_centerline: Signed offset from the mortise centerline toward the tenon.
            0 = plane through the mortise centerline. Positive = toward tenon.
        up_direction: Direction for +Y axis of the marking space. Will be orthogonalized
            against the shoulder plane normal.

    Returns:
        ButtJointShoulderResult with the shoulder plane, intersection point, and marking space.
    """
    tenon_timber = arrangement.butt_timber
    tenon_end = arrangement.butt_timber_end

    shoulder_plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
        arrangement, distance_from_centerline
    )

    shoulder_from_tenon_end_mark = mark_distance_from_end_along_centerline(
        shoulder_plane, tenon_timber, tenon_end
    )
    shoulder_point_global = shoulder_from_tenon_end_mark.locate().position

    orientation = Orientation.from_x_and_y(
        x_direction=shoulder_plane.normal,
        y_direction=up_direction,
    )
    marking_space = Space(
        transform=Transform(position=shoulder_point_global, orientation=orientation)
    )

    butt_direction = tenon_timber.get_face_direction_global(tenon_end)

    return ButtJointShoulderResult(
        shoulder_plane=shoulder_plane,
        butt_direction=butt_direction,
        marking_space=marking_space,
    )


# ============================================================================
# Shoulder Geometry
# ============================================================================
def build_dovetail_shoulder_geometery(
    arrangement: ButtJointTimberArrangement,
    shoulder_result: ButtJointShoulderResult,
    dovetail_depth: Numeric
    ) -> CutCSG:
    """

    Creates the shoulder geometry for a dovetail shoulder. The height of the dovetail is determined by the dimensions of the receiving timber.
    The depth of the dovetail is determined by the dovetail_depth parameter.


          |   
    ______|  v    |
           \      |
            \     |
    _________\    |
          | ^     |
          | dovetail_depth


    The resulting CutCSG object is in global space. It includes part of the butt timber itself, not just the dovetail shape.
    The resulting CutCSG object includes part of the butt timber itself, not just the dovetail shape. This is useful for cutting notches into the receiving timber for non perfect receiving timbers.
    """
    from kumiki.cutcsg import ConvexPolygonExtrusion

    if safe_compare(dovetail_depth, Integer(0), Comparison.LE):
        raise ValueError(f"dovetail_depth must be positive, got {dovetail_depth}")

    receiving_timber = arrangement.receiving_timber
    butt_timber = arrangement.butt_timber

    shoulder_transform = shoulder_result.marking_space.transform
    orientation_matrix = shoulder_transform.orientation.matrix

    x_axis_global = create_v3(orientation_matrix[0, 0], orientation_matrix[1, 0], orientation_matrix[2, 0])
    y_axis_global = create_v3(orientation_matrix[0, 1], orientation_matrix[1, 1], orientation_matrix[2, 1])
    z_axis_global = create_v3(orientation_matrix[0, 2], orientation_matrix[1, 2], orientation_matrix[2, 2])

    shoulder_height = receiving_timber.get_size_in_direction_3d(y_axis_global)
    half_height = shoulder_height / Rational(2)

    shoulder_span = butt_timber.get_size_in_direction_3d(z_axis_global)
    half_span = shoulder_span / Rational(2)

    # Keep a rectangular butt-side section so this geometry includes part of the
    # butt timber itself before transitioning along the dovetail ramp.
    butt_side_thickness = butt_timber.get_size_in_direction_3d(x_axis_global) / Rational(2)

    profile_points = [
        create_v2(-butt_side_thickness, -half_height),
        create_v2(-butt_side_thickness, half_height),
        create_v2(Integer(0), half_height),
        create_v2(dovetail_depth, -half_height),
    ]

    return ConvexPolygonExtrusion(
        points=profile_points,
        transform=shoulder_transform,
        start_distance=-half_span,
        end_distance=half_span,
    )



# ============================================================================
# Butt Joint Geometry Definitions
# ============================================================================

@dataclass(frozen=True)
class ButtJointCSGParts:
    """
    Representation of the geometry components that make up a butt joint.
    They are combined by unioning the positive parts, then differencing the negative parts.
    """
    positive_receiving_csg: Optional[CutCSG] = None
    negative_receiving_csg: Optional[CutCSG] = None
    positive_butt_csg: Optional[CutCSG] = None
    negative_butt_csg: Optional[CutCSG] = None



# ============================================================================
# Butt Joint Geometry Functions
# ============================================================================

class DovetailTenonGeometeryResult(NamedTuple):
    """
    Result of computing the geometry for a dovetail tenon.

    Attributes:
        tenon_csg: CSG representing the tenon shape to be cut from the butt timber.
        mortise_csg: CSG representing the mortise shape to be cut from the receiving timber.
    """
    tenon_csg: CutCSG
    mortise_csg: CutCSG
    wedge_accessory_csg: Optional[CutCSG] = None

class DovetailTenonWedgeAccessoryParameters(NamedTuple):
    """
    Parameters for an optional wedge accessory for a dovetail tenon.

    Attributes:
        wedge_from_receiving_timber_side: If true, the wedge is designed to be cut from the receiving timber and inserted from that side. If false, the wedge is designed to be cut from the tenon timber and inserted from the tenon side. We must have tenon_depth + receiving_timber_extra_depth > the matching width on the receivingtimber for this to work
        wedge_angle: The angle of the wedge taper. 0 means a rectangular wedge, X means a wedge with an X angle taper.
        wedge_small_width: The width of the narrow end of the wedge. Measured at tenon_length if wedge_from_receiving_timber_side is False, measured from the shoulder if wedge_from_receiving_timber_side is True. If None, dovetail_depth is used.
    """
    wedge_from_receiving_timber_side: bool = False
    wedge_angle: Numeric = degrees(10)
    wedge_small_width: Optional[Numeric] = None

def dovetail_tenon_geometry(
    arrangement: ButtJointTimberArrangement,
    shoulder_result: ButtJointShoulderResult,
    dovetail_top_side_on_butt_timber: TimberLongFace,
    tenon_size: V2,
    tenon_depth: Numeric,
    dovetail_depth: Numeric,
    tenon_lateral_offset: Numeric = 0,
    # the extra depth for the mortise hole in the receiving timber
    receiving_timber_extra_depth: Numeric = 0,
    wedge_accessory_parameters: Optional[DovetailTenonWedgeAccessoryParameters] = None,
) -> DovetailTenonGeometeryResult:
    """
    Build the tenon geometry for a dovetail shoulder. The "top" of dovetail tenon is always flush with dovetail_top_side_on_butt_timber face of the butt timber, however x/y sizing still aligns with the usual width/height axis of the butt timber.
    tenon_lateral_offset is always in the perpendicular axis of the joint on the tenon timber. When 0, the tenon is laterally centered on the the butt timber.



        dovetail_top_side_on_butt_timber
           v 
    _________
             |
             |
          |\ |  < dovetail_depth
          | \|  <
    ______|
           ^^^ tenon_depth
    """ 

    if safe_compare(tenon_depth, Integer(0), Comparison.LE):
        raise ValueError(f"tenon_depth must be positive, got {tenon_depth}")
    if safe_compare(dovetail_depth, Integer(0), Comparison.LT):
        raise ValueError(f"dovetail_depth must be non-negative, got {dovetail_depth}")
    if safe_compare(receiving_timber_extra_depth, Integer(0), Comparison.LT):
        raise ValueError(
            "receiving_timber_extra_depth must be non-negative, "
            f"got {receiving_timber_extra_depth}"
        )
    if safe_compare(tenon_size[0], Integer(0), Comparison.LE) or safe_compare(tenon_size[1], Integer(0), Comparison.LE):
        raise ValueError(f"tenon_size values must be positive, got {tenon_size}")

    raise NotImplementedError("dovetail tenon geometry function is not implemented yet")

# ============================================================================
# Peg Geometry
# ============================================================================

class PegPositionSpace(Enum):
    """Which timber's coordinate space to use when interpreting peg positions and orientations."""
    TENON = 1
    MORTISE = 2


# TODO add tenon bore offset parameter, it could be none | auto | Numeric
@dataclass(frozen=True)
class SimplePegParameters:
    """
    Parameters for simple pegs in mortise and tenon joints.

    Attributes:
        shape: Shape specification for the peg (from PegShape enum)
        peg_positions: List of (distance_from_shoulder, distance_from_centerline) tuples
                       - First value: distance along length axis measured from shoulder of tenon
                       - Second value: distance in perpendicular axis measured from center
        peg_position_space: Controls which timber's coordinate system is used to interpret each
                    component of peg_positions. A tuple of (shoulder_axis_space, lateral_axis_space).
                    - shoulder_axis_space (first element): controls distance_from_shoulder direction.
                      TENON = along tenon length axis. MORTISE = along mortise length axis.
                    - lateral_axis_space (second element): controls distance_from_centerline direction.
                      TENON = perpendicular to peg face normal and tenon length axis.
                      MORTISE = along mortise length axis.
        size: Peg diameter (for round pegs) or side length (for square pegs)
        depth: Depth measured from mortise face where peg goes in (None means all the way through the mortise timber)
        tenon_hole_offset: Offset distance of the hole in the tenon towards the shoulder so that the peg tightens the joint up. You should usually set this to 1-2mm
        peg_orientation: Controls which timber's face axes the peg cross-section is aligned to, plus an
                         optional CCW rotation around the drill axis. A tuple of (space, ccw_rotation_angle).
                         - space: TENON = align peg Y axis with the tenon length axis.
                                  MORTISE = align peg Y axis with the mortise length axis.
                         - ccw_rotation_angle: counter-clockwise rotation (in radians) around the drill
                           axis applied on top of the face-aligned basis. 0 = no rotation.
    """
    shape: PegShape
    peg_positions: List[Tuple[Numeric, Numeric]]
    size: Numeric
    depth: Optional[Numeric] = None
    tenon_hole_offset: Numeric = Rational(0)
    peg_position_space: Tuple[PegPositionSpace, PegPositionSpace] = (
        PegPositionSpace.TENON,
        PegPositionSpace.TENON,
    )
    peg_orientation: Tuple[PegPositionSpace, Numeric] = (
        PegPositionSpace.TENON,
        Rational(0),
    )


@dataclass(frozen=True)
class PegPositionResult:
    """
    Computed geometry for a single peg, all positions and orientations in global space.

    Attributes:
        tenon_face_position_global: Center of the peg hole on the tenon face (no draw-bore offset).
        tenon_face_position_with_offset_global: Center of the peg hole on the tenon face,
            shifted toward the shoulder by tenon_hole_offset for draw-bore tightening.
        mortise_entry_position_global: Center of the peg hole on the mortise entry face.
        orientation_global: Orientation of the peg (Z-axis = drill direction into the timber).
        peg_depth: Depth of the peg hole (full chord through the mortise, or explicit depth).
        stickout_length: Length the peg protrudes beyond the mortise entry face.
    """
    tenon_face_position_global: V3
    tenon_face_position_with_offset_global: V3
    mortise_entry_position_global: V3
    orientation_global: Orientation
    peg_depth: Numeric
    stickout_length: Numeric


def compute_peg_positions(
    arrangement: ButtJointTimberArrangement,
    shoulder_plane: Plane,
    peg_parameters: SimplePegParameters,
    tenon_position: V2,
) -> List[PegPositionResult]:
    """
    Compute peg positions in global space for a mortise and tenon joint.

    Uses the arrangement's front_face_on_butt_timber as the peg face on the tenon.
    All computations are done in global space, using the measure/mark pattern where possible.

    Args:
        arrangement: Butt joint arrangement (butt_timber = tenon, receiving_timber = mortise).
                     Must have front_face_on_butt_timber set.
        shoulder_plane: The shoulder plane in global space (from
                        locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber).
        peg_parameters: Peg configuration (shape, positions, size, depth, offset).
        tenon_position: Offset of tenon center from timber centerline in tenon local cross-section (X, Y).

    Returns:
        List of PegPositionResult, one per peg_position entry.
    """
    tenon_timber = arrangement.butt_timber
    mortise_timber = arrangement.receiving_timber
    tenon_end = arrangement.butt_timber_end

    assert arrangement.front_face_on_butt_timber is not None, (
        "arrangement.front_face_on_butt_timber must be set to determine the peg face"
    )
    tenon_face: TimberLongFace = arrangement.front_face_on_butt_timber
    peg_face: TimberFace = tenon_face.to.face()

    shoulder_mark = mark_distance_from_end_along_centerline(
        shoulder_plane,
        tenon_timber,
        tenon_end,
    )
    shoulder_point_global = shoulder_mark.locate().position

    tenon_right = tenon_timber.get_face_direction_global(TimberFace.RIGHT)
    tenon_front = tenon_timber.get_face_direction_global(TimberFace.FRONT)
    marking_origin_global = (
        shoulder_point_global
        + tenon_right * tenon_position[0]
        + tenon_front * tenon_position[1]
    )

    tenon_end_direction = tenon_timber.get_face_direction_global(tenon_end)

    tenon_face_plane = locate_face(tenon_timber, peg_face)
    peg_face_normal_global = tenon_face_plane.normal

    tenon_centerline = locate_centerline(tenon_timber)
    mortise_centerline = locate_centerline(mortise_timber)

    peg_drill_direction = -peg_face_normal_global
    peg_ray_direction = peg_face_normal_global

    orient_space, ccw_rotation_angle = peg_parameters.peg_orientation
    if orient_space == PegPositionSpace.TENON:
        peg_y_base = tenon_centerline.direction
    else:
        mortise_len_dir = mortise_centerline.direction
        if safe_dot_product(mortise_len_dir, tenon_end_direction) < 0:
            mortise_len_dir = -mortise_len_dir
        peg_y_base = mortise_len_dir

    if zero_test(ccw_rotation_angle):
        peg_orientation_global = Orientation.from_z_and_y(
            z_direction=peg_drill_direction,
            y_direction=peg_y_base,
        )
    else:
        base_orientation = Orientation.from_z_and_y(
            z_direction=peg_drill_direction,
            y_direction=peg_y_base,
        )
        rotation_around_z = Orientation.from_angle_axis(
            ccw_rotation_angle,
            peg_drill_direction,
        )
        peg_orientation_global = Orientation(
            rotation_around_z.matrix * base_orientation.matrix
        )

    if tenon_face in [TimberLongFace.RIGHT, TimberLongFace.LEFT]:
        tenon_lateral_direction = tenon_front
    else:
        tenon_lateral_direction = tenon_right

    results: List[PegPositionResult] = []

    for distance_from_shoulder, distance_from_centerline in peg_parameters.peg_positions:
        if peg_parameters.peg_position_space[0] == PegPositionSpace.TENON:
            shoulder_axis = tenon_end_direction
        else:
            mortise_len_dir = mortise_centerline.direction
            if safe_dot_product(mortise_len_dir, tenon_end_direction) < 0:
                mortise_len_dir = -mortise_len_dir
            shoulder_axis = mortise_len_dir

        if peg_parameters.peg_position_space[1] == PegPositionSpace.TENON:
            lateral_axis = tenon_lateral_direction
        else:
            lateral_axis = mortise_centerline.direction

        peg_center_global = (
            marking_origin_global
            + shoulder_axis * distance_from_shoulder
            + lateral_axis * distance_from_centerline
        )

        dist_to_face = safe_dot_product(
            tenon_face_plane.normal,
            tenon_face_plane.point - peg_center_global,
        )
        peg_pos_on_tenon_face_global = (
            peg_center_global + tenon_face_plane.normal * dist_to_face
        )

        offset_direction = -tenon_end_direction
        peg_pos_on_tenon_face_with_offset_global = (
            peg_pos_on_tenon_face_global
            + offset_direction * peg_parameters.tenon_hole_offset
        )

        ray_origin_local = mortise_timber.transform.global_to_local(
            peg_pos_on_tenon_face_global
        )
        ray_dir_local = safe_transform_vector(
            mortise_timber.transform.orientation.matrix.T,
            peg_ray_direction,
        )

        box_mins = [
            -mortise_timber.size[0] / 2,
            -mortise_timber.size[1] / 2,
            Integer(0),
        ]
        box_maxs = [
            mortise_timber.size[0] / 2,
            mortise_timber.size[1] / 2,
            mortise_timber.length,
        ]

        t_enter_vals = []
        t_exit_vals = []
        for axis in range(3):
            d = ray_dir_local[axis]
            if zero_test(d):
                assert box_mins[axis] <= ray_origin_local[axis] <= box_maxs[axis], (
                    f"Peg ray is parallel to mortise timber axis {axis} but peg position is "
                    f"outside the mortise timber bounds on that axis"
                )
            else:
                t1 = (box_mins[axis] - ray_origin_local[axis]) / d
                t2 = (box_maxs[axis] - ray_origin_local[axis]) / d
                t_enter_vals.append(min(t1, t2))
                t_exit_vals.append(max(t1, t2))

        assert t_enter_vals and t_exit_vals, (
            "Peg ray is parallel to all three mortise timber axes"
        )
        t_enter = max(t_enter_vals)
        t_exit = min(t_exit_vals)
        assert t_exit > t_enter, (
            "Peg ray does not intersect the mortise timber; "
            "check that the peg position and direction are correct"
        )

        peg_entry_t = t_exit if t_enter < 0 else t_enter
        peg_pos_on_mortise_face_global = (
            peg_pos_on_tenon_face_global + peg_ray_direction * peg_entry_t
        )

        if peg_parameters.depth is not None:
            peg_depth = peg_parameters.depth
        else:
            peg_depth = t_exit - t_enter
        stickout_length = peg_depth * Rational(1, 2)

        results.append(PegPositionResult(
            tenon_face_position_global=peg_pos_on_tenon_face_global,
            tenon_face_position_with_offset_global=peg_pos_on_tenon_face_with_offset_global,
            mortise_entry_position_global=peg_pos_on_mortise_face_global,
            orientation_global=peg_orientation_global,
            peg_depth=peg_depth,
            stickout_length=stickout_length,
        ))

    return results
