"""Six-way cross lap arrangement: a round post capped by three crossing 2x8 boards.

A single round post (10" diameter, 4' tall) stands at the origin. Three 2x8
boards, each 4' long, pass over the top of the post so their centerlines all
meet above the post's centerline, spaced 60 degrees apart in plan (a "six-way
cross" / asterisk pattern). Each board stands on edge (7.25" dimension
vertical, 1.5" dimension horizontal) with its top face flush with the top of
the post.

The three boards are woven together with `cut_multi_cross_lap_joint_on_plane_aligned_timbers`, starting
from each board's LEFT face (the global-bottom face shared by all three boards
regardless of their plan rotation), split half-and-half at the midpoint.
"""

from sympy import cos, sin

from kumiki import *
from kumiki.ticket import BoardTicket

# --- Dimensions --------------------------------------------------------

post_diameter = inches(10)
post_height = feet(4)

board_width = inches(scalar(29, 4))   # 7.25" actual width of a 2x8 (stands vertical)
board_thickness = inches(scalar(3, 2))  # 1.5" actual thickness of a 2x8 (lies horizontal)
board_length = feet(4)

num_boards = 3
angle_step = degrees(180) / num_boards  # 60 degrees between each board's axis


def example() -> Frame:
    # Round post, standing at the origin.
    post = RoundTimber(
        length=post_height,
        size=create_v2(post_diameter, post_diameter),
        diameter=post_diameter,
        transform=Transform(
            position=create_v3(scalar(0), scalar(0), scalar(0)),
            orientation=Orientation.identity(),
        ),
        ticket=TimberTicket(path="post"),
    )

    # Three boards crossing above the post, 60 degrees apart in plan, each
    # centered over the post's centerline with their top face flush with the
    # post's top. Width (local X) is mapped to global Z, so the centerline
    # sits half a board-width below the post's top face.
    boards = []
    for i in range(num_boards):
        angle = angle_step * i
        length_direction = create_v3(cos(angle), sin(angle), scalar(0))
        width_direction = create_v3(scalar(0), scalar(0), scalar(1))
        centerline_z = post_height - board_width / 2

        board = Board(
            length=board_length,
            size=create_v2(board_width, board_thickness),
            transform=Transform(
                position=create_v3(scalar(0), scalar(0), scalar(0)) - length_direction * (board_length / 2)
                + create_v3(scalar(0), scalar(0), centerline_z),
                orientation=Orientation.from_z_and_x(length_direction, width_direction),
            ),
            ticket=BoardTicket(path=f"board_{i + 1}"),
        )
        boards.append(board)

    joint = cut_multi_cross_lap_joint_on_plane_aligned_timbers(
        boards,
        starting_face_on_first_timber=TimberFace.LEFT,
        cut_distance_ratios=[scalar(1, 2)],
    )

    post_housing_joint = cut_free_house_joint(
        housing_timber=post,
        housed_timbers=boards,
    )

    return Frame.from_joints(
        [joint, post_housing_joint],
        name="multi_cross_lap_post_arrangement",
    )
