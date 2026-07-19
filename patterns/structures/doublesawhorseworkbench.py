"""Double sawhorse workbench.

Footprint is 2' (Y) x 4' (X). Two 4x6 feet (tall dimension in Z) run along the
inside of the 2' sides. Each foot carries a pair of vertical 4x6 posts (thin
dimension in X, matching the feet) with a 3" gap between them, centered on the
foot. Two 4x8 top beams (thin dimension in Z) span across the posts in X and
overhang the outside face of the posts on each side.

All timber cross-sections are true (dressed) dimensions, not nominal:
4x6 = 3.5" x 5.5", 4x8 = 3.5" x 7.5", 2x12 = 1.5" x 11.5".

Posts are joined to the feet with mortise and tenon joints (through mortises
in the feet), and to the top beams with stopped mortise and tenon joints so
nothing shows on the work surface. A 2x12 stretcher laid flat below the work
surface is cross-lapped into all four posts, and its top face carries a
1"-deep tray recess between the posts with a 3/4" border all around.
"""

from kumiki import *

# --- Dimensions -------------------------------------------------------------

footprint_x = feet(4)            # long dimension (X)
footprint_y = inches(24)            # short dimension (Y); the feet run along this

foot_size = Matrix([inches(7, 2), inches(11, 2)])   # true 4x6: 3.5" in X, 5.5" in Z
foot_length = footprint_y                           # feet span the full 2' sides

post_size = Matrix([inches(7, 2), inches(11, 2)])   # true 4x6: 3.5" in X (matches feet), 5.5" in Y
post_height = inches(22)   # not specified by user; work surface lands at
                           # 31" (5.5" foot + 22" post + 3.5" beam)
post_gap = inches(3)       # clear gap between the two posts on each foot

top_beam_size = Matrix([inches(15, 2), inches(7, 2)])  # true 4x8: 7.5" in Y, 3.5" in Z
top_beam_overhang = inches(11)  # beyond the outside face of the posts, each side

# Post-to-foot mortise and tenon: tenon is 4/3" in X (about a third of the
# foot's 3.5" width) and 5" in Y, just under the post's 5.5" depth.
post_tenon_size = Matrix([inches(4, 3), inches(5)])
post_tenon_length = inches(5)

# Square draw-bore pegs on the post-to-foot joints: 1" square, centered on the
# tenon 1.5" below the shoulder, driven through the foot. The 1/16" hole
# offset in the tenon pulls the shoulder tight when the peg is driven.
post_peg_parameters = SimplePegParameters(
    shape=PegShape.SQUARE,
    peg_positions=[(inches(3, 2), Rational(0))],
    size=inches(1),
    depth=None,  # through peg
    tenon_hole_offset=inches(1, 16),
)

# Post-to-beam mortise and tenon: stopped mortise (tenon must not protrude
# through the 3.5" beam). Tenon is deliberately rotated from the usual
# convention: 1.5" in the beam's length axis (X), 4" in the perpendicular (Y).
beam_tenon_size = Matrix([inches(3, 2), inches(4)])
beam_tenon_length = inches(3)
beam_mortise_depth = beam_tenon_length + inches(1, 4)  # stops 1/4" below the top

# Stretcher: 2x12 laid flat (11.5" in Y so it reaches both post rows, 1.5" in
# Z), spanning between the post pairs and cross-lapped into all four posts.
stretcher_size = Matrix([inches(23, 2), inches(3, 2)])
stretcher_stickout = inches(3.5)   # past the outer post faces, each end
stretcher_center_z = inches(15)  # height not specified by user; mid-post

# Tray recess in the stretcher's top face: 1" deep, with a 3/4" border off the
# stretcher's long edges and off the posts' inside faces, so the tray sits
# only between the post pairs.
tray_border = inches(3, 4)
tray_depth = inches(1)

# Feet sit on the inside of the 2' sides: outer face flush with the footprint
# edge, body extending inward. Timber cross-sections are centered on their
# centerline, so the foot centerline sits half its width in from the edge.
foot_center_x = footprint_x / 2 - foot_size[0] / 2

# Post centerlines in Y: half the gap plus half the post depth off center.
post_center_y = post_gap / 2 + post_size[1] / 2

footprint = Footprint(corners=(
    create_v2(-footprint_x / 2, -footprint_y / 2),
    create_v2( footprint_x / 2, -footprint_y / 2),
    create_v2( footprint_x / 2,  footprint_y / 2),
    create_v2(-footprint_x / 2,  footprint_y / 2),
))


def build_double_sawhorse_workbench() -> Frame:
    # Feet run in +Y along the 2' sides, resting on the ground. The centerline
    # is raised half the foot height so the bottom face sits at Z=0. Each
    # foot's local RIGHT face points outward (west foot: -X, east foot: +X) so
    # the peg joinery mirrors instead of repeating across the bench.
    def make_foot(center_x, width_direction, ticket):
        return create_axis_aligned_timber(
            bottom_position=create_v3(center_x, -foot_length / 2, foot_size[1] / 2),
            length=foot_length,
            size=foot_size,
            length_direction=TimberFace.FRONT,  # +Y
            width_direction=width_direction,    # thin dimension, +/-X
            ticket=ticket,
        )

    west_foot = make_foot(-foot_center_x, TimberFace.LEFT, "West Foot")
    east_foot = make_foot(foot_center_x, TimberFace.RIGHT, "East Foot")

    # Two posts per foot, rising from the top of the foot, with a 3" gap
    # between the pair, centered on the foot.
    def make_post(center_x, center_y, ticket):
        return create_axis_aligned_timber(
            bottom_position=create_v3(center_x, center_y, foot_size[1]),
            length=post_height,
            size=post_size,
            length_direction=TimberFace.TOP,    # +Z
            width_direction=TimberFace.RIGHT,   # +X (thin dimension)
            ticket=ticket,
        )

    west_south_post = create_axis_aligned_timber(
        bottom_position=create_v3(-foot_center_x, -post_center_y, foot_size[1]),
        length=post_height,
        size=Matrix([inches(7, 2), inches(15, 2)]),  # true 4x8
        length_direction=TimberFace.TOP,    # +Z
        width_direction=TimberFace.RIGHT,   # +X (thin dimension)
        ticket="West South Post",
    )
    west_north_post = make_post(-foot_center_x, post_center_y, "West North Post")
    east_south_post = make_post(foot_center_x, -post_center_y, "East South Post")
    east_north_post = make_post(foot_center_x, post_center_y, "East North Post")

    # Top beams span in X between each pair of posts, sitting on the post tops
    # (centerline half the beam depth above them). Stickout is measured from
    # the post centerlines: half the post width plus the overhang.
    top_beam_stickout = Stickout.symmetric(post_size[0] / 2 + top_beam_overhang)
    top_beam_centerline_location = post_height + top_beam_size[1] / 2

    def make_top_beam(west_post, east_post, ticket):
        return join_timbers(
            west_post, east_post,
            location_on_timber1=top_beam_centerline_location,
            location_on_timber2=top_beam_centerline_location,
            stickout=top_beam_stickout,
            size=top_beam_size,
            orientation_width_vector=create_v3(scalar(0), scalar(1), scalar(0)),  # wide in Y, thin in Z
            ticket=ticket,
        )

    south_top_beam = make_top_beam(west_south_post, east_south_post, "South Top Beam")
    north_top_beam = make_top_beam(west_north_post, east_north_post, "North Top Beam")

    # Stretcher runs in +X, centered on the bench so its width overlaps both
    # post rows, ends sticking out past the outer post faces.
    stretcher = create_axis_aligned_timber(
        bottom_position=create_v3(-footprint_x / 2 - stretcher_stickout,
                                  Rational(0), stretcher_center_z),
        length=footprint_x + 2 * stretcher_stickout,
        size=stretcher_size,
        length_direction=TimberFace.RIGHT,  # +X
        width_direction=TimberFace.FRONT,   # +Y (wide dimension)
        ticket="Stretcher",
    )

    # Post bottoms tenon into the feet: through mortise, pegged through the
    # foot's X faces. The peg face comes from front_face_on_butt_timber (a
    # face on the post), so the west side uses LEFT and the east side RIGHT
    # to mirror the pegs across the bench instead of repeating them.
    def cut_post_to_foot_joint(post, foot, peg_face_on_post):
        return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=foot,
                butt_timber=post,
                butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=peg_face_on_post,
            ),
            tenon_size=post_tenon_size,
            tenon_length=post_tenon_length,
            mortise_depth=None,  # through mortise
            peg_parameters=post_peg_parameters,
        )

    post_foot_joints = [
        cut_post_to_foot_joint(west_south_post, west_foot, TimberLongFace.LEFT),
        cut_post_to_foot_joint(west_north_post, west_foot, TimberLongFace.LEFT),
        cut_post_to_foot_joint(east_south_post, east_foot, TimberLongFace.RIGHT),
        cut_post_to_foot_joint(east_north_post, east_foot, TimberLongFace.RIGHT),
    ]

    # Post tops tenon into the beams: stopped mortise, 3" tenon. Unpegged --
    # the beams sit above the posts, so gravity holds the joint.
    def cut_post_to_beam_joint(post, beam):
        return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=beam,
                butt_timber=post,
                butt_timber_end=TimberEnd.TOP,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=beam_tenon_size,
            tenon_length=beam_tenon_length,
            mortise_depth=beam_mortise_depth,
        )

    post_beam_joints = [
        cut_post_to_beam_joint(west_south_post, south_top_beam),
        cut_post_to_beam_joint(east_south_post, south_top_beam),
        cut_post_to_beam_joint(west_north_post, north_top_beam),
        cut_post_to_beam_joint(east_north_post, north_top_beam),
    ]

    # Cross laps bind the stretcher to all four posts, splitting the material
    # removal equally between stretcher and post at each crossing.
    stretcher_joints = [
        cut_basic_plain_cross_lap_joint_on_face_aligned_timbers(
            CrossJointTimberArrangement(timber1=stretcher, timber2=post),
        )
        for post in (west_south_post, west_north_post,
                     east_south_post, east_north_post)
    ]

    # Tray recess pocketed into the stretcher's top face (local FRONT = +Z).
    # The profile is drawn on the top face anchored at the stretcher's -X end:
    # profile x runs across the width (global +Y) and profile y runs toward
    # that end (global -X), so wall distances from the end enter negated.
    stretcher_half_length = footprint_x / 2 + stretcher_stickout
    post_inner_x = foot_center_x - post_size[0] / 2
    tray_near_wall = stretcher_half_length - post_inner_x + tray_border
    tray_far_wall = stretcher_half_length + post_inner_x - tray_border
    tray_half_width = stretcher_size[0] / 2 - tray_border
    tray_csg = chop_profile_on_timber_face(
        timber=stretcher,
        end=TimberEnd.BOTTOM,  # the -X end
        face=TimberFace.FRONT,          # top face of the flat stretcher
        profile=[
            create_v2(-tray_half_width, -tray_near_wall),
            create_v2(tray_half_width, -tray_near_wall),
            create_v2(tray_half_width, -tray_far_wall),
            create_v2(-tray_half_width, -tray_far_wall),
        ],
        depth=tray_depth,
    )
    tray_joint = Joint(
        cuttings={"stretcher_tray": Cutting(timber=stretcher, negative_csg=tray_csg)},
        ticket=JointTicket(joint_type="tray_recess"),
        jointAccessories={},
    )

    return Frame.from_joints(
        post_foot_joints + post_beam_joints + stretcher_joints + [tray_joint],
        name="Double Sawhorse Workbench",
    )


example = build_double_sawhorse_workbench


if __name__ == "__main__":
    from kumiki.timber import TimberCorner

    frame = build_double_sawhorse_workbench()
    print(f"Created '{frame.name}' with {len(frame.cut_timbers)} timbers:")

    def extents(timber):
        corners = [timber.get_corner_position_global(c) for c in TimberCorner]
        return [(min(p[i] for p in corners), max(p[i] for p in corners)) for i in range(3)]

    fmt = lambda v: f"{float(v) / 0.0254:7.2f}\""
    by_name = {}
    cuts_by_name = {}
    for cut_timber in frame.cut_timbers:
        timber = cut_timber.timber
        (x0, x1), (y0, y1), (z0, z1) = extents(timber)
        by_name[timber.ticket.path] = ((x0, x1), (y0, y1), (z0, z1))
        cuts_by_name[timber.ticket.path] = len(cut_timber.cuts)
        print(f"  {timber.ticket.path:16s} x[{fmt(x0)},{fmt(x1)}] "
              f"y[{fmt(y0)},{fmt(y1)}] z[{fmt(z0)},{fmt(z1)}] "
              f"cuts={len(cut_timber.cuts)}")

    # Sanity-check the spec.
    for name in ("West Foot", "East Foot"):
        assert by_name[name][2] == (scalar(0), foot_size[1]), f"{name} not resting on ground"
    post_names = [n for n in by_name if "Post" in n]
    for name in post_names:
        assert by_name[name][2] == (foot_size[1], foot_size[1] + post_height), f"{name} not on foot top"
    assert by_name["West North Post"][1][0] == post_gap / 2, "post gap is not 3 inches"
    for name in ("South Top Beam", "North Top Beam"):
        assert by_name[name][2][0] == foot_size[1] + post_height, f"{name} not resting on post tops"
        assert by_name[name][0] == (-footprint_x / 2 - top_beam_overhang,
                                    footprint_x / 2 + top_beam_overhang), f"{name} overhang wrong"
    for name in ("West Foot", "East Foot"):
        assert cuts_by_name[name] == 2, f"{name} should have 2 mortise cuts"
    for name in post_names:
        assert cuts_by_name[name] == 3, f"{name} should have 2 tenons + 1 lap relief"
    for name in ("South Top Beam", "North Top Beam"):
        assert cuts_by_name[name] == 2, f"{name} should have 2 mortise cuts"
    assert by_name["Stretcher"] == ((-footprint_x / 2 - stretcher_stickout,
                                     footprint_x / 2 + stretcher_stickout),
                                    (-stretcher_size[0] / 2, stretcher_size[0] / 2),
                                    (stretcher_center_z - stretcher_size[1] / 2,
                                     stretcher_center_z + stretcher_size[1] / 2)), \
        "stretcher extents wrong"
    assert cuts_by_name["Stretcher"] == 5, "stretcher should have 4 lap relief cuts + tray"
    assert len(frame.accessories) == 4, "expected one peg per post-to-foot joint"
    print(f"All layout checks passed. {len(frame.accessories)} pegs. "
          f"Work surface height: {fmt(by_name['South Top Beam'][2][1])}")
