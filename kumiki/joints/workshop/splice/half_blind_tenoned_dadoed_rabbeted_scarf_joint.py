"""
Kumiki - Half-blind tenoned dadoed rabbeted scarf joint (Kanawa Tsugi) construction functions
"""

from typing import Optional, Tuple

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import locate_top_center_position
from ..shavings import decompose_simple_polygon_into_convex_pieces
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


def cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers(
    arrangement: SpliceJointTimberArrangement,
    stepped_shoulder_depth: Numeric,
    scarf_length: Numeric,
    dado_depth: Numeric,
    dado_height: Numeric,
    stub_tenon_width: Numeric,
    stepped_shoulder_length: Optional[Numeric] = None,
    joint_center_relative_to_timber1_end: Numeric = scalar(0),
    lateral_offset_from_midline: Numeric = scalar(0),
) -> Joint:
    """
    Creates a half-blind tenoned dadoed rabbeted scarf joint (金輪継ぎ / Kanawa Tsugi).

    arrangement.front_face_on_timber1 determines the face which scarf cut profile is visible on.

    Args:
        arrangement: Splice arrangement with timber1, timber2, timber1_end, timber2_end,
            and front_face_on_timber1.
        stepped_shoulder_depth: (Tsuki-tsuke (突付)) determines the depth of the stepped shoulder cut in the scarf joint, the 2 stepped shoulders form the pin hole for the square peg forming the Kusabi-ana (楔穴)
        scarf_length: determines the length of the scarf cut on each timber, it is measured from the corner that lies on the midline of the scarf joint of the opposite dadoes of the joint when fully assembled
        dado_depth: the "depth" of both dadoes (measured in the length axis of the timbers)
        dado_height: the "height" of both dadoes (measured in the long face axis of the long face adjacent front_face_on_timber1), the dado width is always the entire size of the timber in the front_face_on_timber1 axis
        stub_tenon_width: the "width" of the stub tenon (measured in the long face axis of the long face adjacent front_face_on_timber1), the stub tenon depth is always the distance from the surface to the dado wall.
        stepped_shoulder_length: determines the length of the stepped shoulder cut in the scarf joint, if None, defaults to stepped_shoulder_depth (forming a rectangular peg hole). Note this measures the width of the rectangular hole that gets created by the stepped shoulder, rather than the width from corner to corner of the rectangular hole which is how you might draw this joint by hand.
        joint_center_relative_to_timber1_end: determines the "center" of the joint (right in the middle of the rectangular peg hole) measured inward from the joint end of timber1. (positive means the joint center is further into timber1)
        lateral_offset_from_midline: determines the lateral offset of the joint profiles centerline from the midline of front_face_on_timber1

    Returns:
        Joint object containing both cut timbers and the peg accessory.

    Notes:
        the oblique scarf face angle (Sogi-michi (斜面)) is determined by the stepped_shoulder_depth and the scarf_half_length
        all measurements are done relative to timber1, timber2 is expected to share the same axis and be the same size as timber1.
    """
    require_check(arrangement.check_face_aligned_and_parallel_axis())
    warn_if_arrangement_timbers_imperfect(arrangement)
    assert arrangement.front_face_on_timber1 is not None, (
        "arrangement.front_face_on_timber1 must be set to determine the joint orientation"
    )

    timber1 = arrangement.timber1
    timber2 = arrangement.timber2
    timber1_end = arrangement.timber1_end
    timber2_end = arrangement.timber2_end
    front_face = arrangement.front_face_on_timber1
    v_face = front_face.rotate_right()

    if stepped_shoulder_length is None:
        stepped_shoulder_length = stepped_shoulder_depth

    SL = scarf_length
    DD = dado_depth
    DH = dado_height
    SSD = stepped_shoulder_depth
    SSL = stepped_shoulder_length
    STW = stub_tenon_width

    require_check(
        None if SSL == SSD
        else "stepped_shoulder_length must equal stepped_shoulder_depth: the Kusabi peg accessory "
             "(kumiki.timber.Peg) only supports a square or round cross-section, so a non-square "
             "peg hole can't yet be represented by an accessory"
    )
    require_check(None if SL >= SSD else "stepped_shoulder_depth must be less than scarf_length")
    require_check(None if DD > 0 else "dado_depth must be positive")
    require_check(None if DH > 0 else "dado_height must be positive")
    require_check(None if SSD > 0 else "stepped_shoulder_depth must be positive")
    require_check(None if SL > 0 else "scarf_length must be positive")
    require_check(None if STW > 0 else "stub_tenon_width must be positive")

    some_var_x = sqrt((SL / scalar(2)) ** 2 - (SSD / scalar(2)) ** 2)
    scarf_hypotneuse = some_var_x + SSL / scalar(2)
    scarf_angle = atan2(SSD / scalar(2), some_var_x)
    sin_scarf_angle = sin(scarf_angle)
    cos_scarf_angle = cos(scarf_angle)

    H = timber1.get_size_in_face_normal_axis(v_face)
    depth_size = timber1.get_size_in_face_normal_axis(front_face)

    require_check(None if STW < depth_size else "stub_tenon_width must be less than the timber's dimension in the front_face_on_timber1 normal axis")
    require_check(None if DH < H / scalar(2) else "dado_height must be less than half the timber's dimension in the front_face_on_timber1-adjacent axis")
    require_check(None if DD < (SL - SSD) / scalar(2) else "dado_depth must be less than (scarf_length - stepped_shoulder_depth) / 2")
    require_check(None if DH >= SSD else "dado_height must be at least stepped_shoulder_depth")

    u_dir = -timber1.get_face_direction_global(timber1_end)
    v_dir = timber1.get_face_direction_global(v_face)
    lateral_dir = arrangement.timber1.get_face_direction_global(front_face)

    if timber1_end == TimberEnd.TOP:
        timber1_end_position_global = locate_top_center_position(timber1).position
    else:
        timber1_end_position_global = timber1.get_bottom_position_global()

    scarf_joint_center_global = timber1_end_position_global + u_dir * joint_center_relative_to_timber1_end + lateral_dir * lateral_offset_from_midline

    corner = (SL / scalar(2), scalar(0))
    p1 = (corner[0], DH)
    p2 = (p1[0] - DD, DH)
    p3 = (p2[0], H / scalar(2))

    p4 = (corner[0] - cos_scarf_angle * scarf_hypotneuse, corner[1] - (sin_scarf_angle * scarf_hypotneuse))
    p5 = (p4[0] - sin_scarf_angle * SSD, p4[1] + cos_scarf_angle * SSD)

    p6 = (-SL / scalar(2), 0)
    p7 = (p6[0], p6[1] - DH)
    p8 = (p7[0] + DD, p7[1])
    p9 = (p8[0], -H / scalar(2))

    left_boundary_u = -SL / scalar(2)
    p10 = (left_boundary_u, p3[1])
    p11 = (left_boundary_u, p9[1])
    profile_points = [p3, p2, p1, corner, p4, p5, p6, p7, p8, p9, p11, p10]

    depth_dir = timber1.get_face_direction_global(front_face)
    profile_orientation = Orientation(Matrix([
        [u_dir[0], v_dir[0], depth_dir[0]],
        [u_dir[1], v_dir[1], depth_dir[1]],
        [u_dir[2], v_dir[2], depth_dir[2]],
    ]))
    profile_transform = Transform(position=scarf_joint_center_global, orientation=profile_orientation)

    convex_pieces = [
        ConvexPolygonExtrusion(
            points=quad,
            transform=profile_transform,
            start_distance=-depth_size,
            end_distance=depth_size,
        )
        for quad in decompose_simple_polygon_into_convex_pieces(
            [create_v2(u, v) for (u, v) in profile_points]
        )
    ]

    timber1_profile_csg_global = SolidUnion(convex_pieces, label=CutCSGLabel("scarf_profile"))

    def reflect(p: Tuple[Numeric, Numeric]) -> Tuple[Numeric, Numeric]:
        return (-p[0], -p[1])

    corner2 = reflect(corner)
    p1_2 = reflect(p1)
    p2_2 = reflect(p2)
    p3_2 = reflect(p3)
    p4_2 = reflect(p4)
    p5_2 = reflect(p5)
    p6_2 = reflect(p6)
    p7_2 = reflect(p7)
    p8_2 = reflect(p8)
    p9_2 = reflect(p9)

    right_boundary_u = -left_boundary_u
    p10_2 = (right_boundary_u, p9_2[1])
    p11_2 = (right_boundary_u, p3_2[1])
    profile_points_2 = [p3_2, p2_2, p1_2, corner2, p4_2, p5_2, p6_2, p7_2, p8_2, p9_2, p10_2, p11_2]

    convex_pieces_2 = [
        ConvexPolygonExtrusion(
            points=quad,
            transform=profile_transform,
            start_distance=-depth_size,
            end_distance=depth_size,
        )
        for quad in decompose_simple_polygon_into_convex_pieces(
            [create_v2(u, v) for (u, v) in profile_points_2]
        )
    ]

    timber2_profile_csg_global = SolidUnion(convex_pieces_2, label=CutCSGLabel("scarf_profile"))

    v_face_size = timber1.get_size_in_face_normal_axis(v_face)
    timber1_stub_tenon_middle_surface_outer_edge_point = scarf_joint_center_global - scarf_length / scalar(2) * u_dir - v_dir * v_face_size / scalar(2)
    timber1_stub_tenon_middle_surface_inner_edge_point = timber1_stub_tenon_middle_surface_outer_edge_point + u_dir * dado_depth
    timber1_stub_tenon_start = (timber1_stub_tenon_middle_surface_outer_edge_point + timber1_stub_tenon_middle_surface_inner_edge_point) / scalar(2)
    timber1_stub_tenon_prism = RectangularPrism(
        transform=Transform(position=timber1_stub_tenon_start, orientation=Orientation.from_z_and_y(v_dir, u_dir)),
        start_distance=0,
        end_distance=v_face_size / scalar(2) - dado_depth,
        size=create_v2(stub_tenon_width, dado_depth),
        label=CutCSGLabel("stub_tenon"),
    )

    def reflect_about_joint_center(point: V3):
        relative = point - scarf_joint_center_global
        reflected = -relative
        return reflected + scarf_joint_center_global

    timber2_stub_tenon_prism = RectangularPrism(
        transform=Transform(position=reflect_about_joint_center(timber1_stub_tenon_start), orientation=Orientation.from_z_and_y(-v_dir, -u_dir)),
        start_distance=0,
        end_distance=v_face_size / scalar(2) - dado_depth,
        size=create_v2(stub_tenon_width, dado_depth),
        label=CutCSGLabel("stub_tenon"),
    )

    timber1_with_stubs_global = SolidUnion([
        Difference(
            timber1_profile_csg_global, [timber1_stub_tenon_prism],
            label=CutCSGLabel("scarf_waste"),
        ),
        timber2_stub_tenon_prism,
    ])
    timber1_negative_csg_local = adopt_csg(None, timber1.transform, timber1_with_stubs_global)

    timber2_with_stubs_global = SolidUnion([
        Difference(
            timber2_profile_csg_global, [timber2_stub_tenon_prism],
            label=CutCSGLabel("scarf_waste"),
        ),
        timber1_stub_tenon_prism,
    ])
    timber2_negative_csg_local = adopt_csg(None, timber2.transform, timber2_with_stubs_global)

    left_boundary_global = scarf_joint_center_global + u_dir * left_boundary_u
    left_boundary_distance_from_bottom = safe_dot_product(
        left_boundary_global - timber1.get_bottom_position_global(),
        timber1.get_length_direction_global(),
    )

    right_boundary_global = scarf_joint_center_global + u_dir * right_boundary_u
    right_boundary_distance_from_bottom = safe_dot_product(
        right_boundary_global - timber2.get_bottom_position_global(),
        timber2.get_length_direction_global(),
    )

    disassembly_direction = u_dir * (p4[0] - corner[0]) + v_dir * (p4[1] - corner[1])
    timber1_freedom = AssemblyFreedom.translation(-disassembly_direction, freed_after=DD)
    timber2_freedom = AssemblyFreedom.translation(disassembly_direction, freed_after=DD)

    timber1_cut = Cutting(
        timber=timber1,
        maybe_top_end_cut_distance_from_bottom=left_boundary_distance_from_bottom if timber1_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=left_boundary_distance_from_bottom if timber1_end == TimberEnd.BOTTOM else None,
        negative_csg=timber1_negative_csg_local,
        label=CutCSGLabel("scarf_cut"),
        assembly_freedom=timber1_freedom,
    )

    timber2_cut = Cutting(
        timber=timber2,
        maybe_top_end_cut_distance_from_bottom=right_boundary_distance_from_bottom if timber2_end == TimberEnd.TOP else None,
        maybe_bottom_end_cut_distance_from_bottom=right_boundary_distance_from_bottom if timber2_end == TimberEnd.BOTTOM else None,
        negative_csg=timber2_negative_csg_local,
        label=CutCSGLabel("scarf_cut"),
        assembly_freedom=timber2_freedom,
    )
    front_face_dir = arrangement.timber1.get_face_direction_global(arrangement.front_face_on_timber1)

    peg_orientation = Orientation.from_z_and_y(front_face_dir, v_dir)
    peg_orientation = Orientation.from_angle_axis(scarf_angle, front_face_dir) * peg_orientation
    peg = Peg(
        transform=Transform(position=scarf_joint_center_global, orientation=peg_orientation),
        size=stepped_shoulder_depth,
        shape=PegShape.SQUARE,
        forward_length=depth_size * scalar(3 / 5),
        stickout_length=depth_size * scalar(3 / 5),
    )

    return Joint(
        cuttings={
            timber1.ticket.path: timber1_cut,
            timber2.ticket.path: timber2_cut,
        },
        ticket=JointTicket(joint_type="half_blind_tenoned_dadoed_rabbeted_scarf"),
        jointAccessories={"peg": peg},
    )


# Aliases for Japanese joint functions
cut_kanawa_tsugi_joint_on_aligned_timbers = cut_half_blind_tenoned_dadoed_rabbeted_scarf_joint_on_aligned_timbers
