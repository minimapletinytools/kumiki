"""
Silly Shed Example - Photo-inspired small shed frame with joinery.

Joinery used:
- Mudsills: keyed miter joints at corners
- Posts to mudsills: short mortise-and-tenon joints
- Plates to posts: mortise-and-tenon joints
- Rafters to plates: house joints, with slight lift and overhang
- Rafter pair at ridge line: tongue-and-fork joint (no ridge beam)
"""

from kumiki import *

# Compatibility alias for watcher reloads that may still reference the old symbol name.
cut_basic_mitered_and_keyed_lap_joint = cut_mitered_and_keyed_lap_joint


# -----------------------------------------------------------------------------
# Dimensions
# -----------------------------------------------------------------------------

shed_length = feet(4)
shed_depth = feet(Rational(5, 2))
wall_height = feet(2)
roof_rise = inches(14)

rafter_overhang = inches(4)
rafter_lift = inches(1)

base_size = create_v2(inches(2), inches(3))
post_size = create_v2(inches(2), inches(3))
plate_size = create_v2(inches(2), inches(3))
rafter_size = create_v2(inches(2), inches(3))

post_to_mudsill_tenon_size = create_v2(inches(1), inches(1))
post_to_mudsill_tenon_length = inches(1, 2)

post_to_plate_tenon_size = create_v2(inches(1), inches(1))
post_to_plate_tenon_length = inches(1)


# -----------------------------------------------------------------------------
# Timber creation helpers
# -----------------------------------------------------------------------------

def _create_base_frame(origin: V3) -> tuple[Timber, Timber, Timber, Timber]:
    x_min = -shed_length / Rational(2)
    x_max = shed_length / Rational(2)
    y_min = -shed_depth / Rational(2)
    y_max = shed_depth / Rational(2)

    base_front = create_axis_aligned_timber(
        bottom_position=origin + create_v3(x_min, y_min, Integer(0)),
        length=shed_length,
        size=base_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="SillyShed Base Front",
    )

    base_back = create_axis_aligned_timber(
        bottom_position=origin + create_v3(x_min, y_max, Integer(0)),
        length=shed_length,
        size=base_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="SillyShed Base Back",
    )

    base_left = create_axis_aligned_timber(
        bottom_position=origin + create_v3(x_min, y_min, Integer(0)),
        length=shed_depth,
        size=base_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket="SillyShed Base Left",
    )

    base_right = create_axis_aligned_timber(
        bottom_position=origin + create_v3(x_max, y_min, Integer(0)),
        length=shed_depth,
        size=base_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket="SillyShed Base Right",
    )

    return base_front, base_back, base_left, base_right


def _create_side_posts(origin: V3) -> list[Timber]:
    x_positions = [-shed_length / Rational(2), Integer(0), shed_length / Rational(2)]
    y_positions = [-shed_depth / Rational(2), shed_depth / Rational(2)]

    posts: list[Timber] = []
    for y_pos in y_positions:
        side_name = "Front" if y_pos < 0 else "Back"
        for x_pos in x_positions:
            x_tag = "Left" if x_pos < 0 else ("Center" if x_pos == 0 else "Right")
            posts.append(
                create_axis_aligned_timber(
                    bottom_position=origin + create_v3(x_pos, y_pos, Integer(0)),
                    length=wall_height,
                    size=post_size,
                    length_direction=TimberFace.TOP,
                    width_direction=TimberFace.RIGHT,
                    ticket=f"SillyShed Post {side_name} {x_tag}",
                )
            )

    return posts


def _create_top_plates(origin: V3) -> tuple[Timber, Timber]:
    x_min = -shed_length / Rational(2)

    plate_front = create_axis_aligned_timber(
        bottom_position=origin + create_v3(x_min, -shed_depth / Rational(2), wall_height),
        length=shed_length,
        size=plate_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="SillyShed Plate Front",
    )

    plate_back = create_axis_aligned_timber(
        bottom_position=origin + create_v3(x_min, shed_depth / Rational(2), wall_height),
        length=shed_length,
        size=plate_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="SillyShed Plate Back",
    )

    return plate_front, plate_back


def _create_roof_rafters(origin: V3) -> list[Timber]:
    x_min = -shed_length / Rational(2)
    x_max = shed_length / Rational(2)
    x_positions = [x_min, Integer(0), x_max]
    x_labels = ["Left", "Center", "Right"]

    ridge_z = wall_height + roof_rise + rafter_lift
    plate_z = wall_height + rafter_lift

    rafters: list[Timber] = []
    for x_pos, x_label in zip(x_positions, x_labels):
        front_plate_point = origin + create_v3(x_pos, -shed_depth / Rational(2), plate_z)
        back_plate_point = origin + create_v3(x_pos, shed_depth / Rational(2), plate_z)
        ridge_point = origin + create_v3(x_pos, Integer(0), ridge_z)

        front_vec = ridge_point - front_plate_point
        back_vec = ridge_point - back_plate_point

        front_bottom = front_plate_point - normalize_vector(front_vec) * rafter_overhang
        back_bottom = back_plate_point - normalize_vector(back_vec) * rafter_overhang

        rafters.append(
            timber_from_directions(
                length=safe_norm(front_vec) + rafter_overhang,
                size=rafter_size,
                bottom_position=front_bottom,
                length_direction=normalize_vector(front_vec),
                width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
                ticket=f"SillyShed Front Rafter {x_label}",
            )
        )

        rafters.append(
            timber_from_directions(
                length=safe_norm(back_vec) + rafter_overhang,
                size=rafter_size,
                bottom_position=back_bottom,
                length_direction=normalize_vector(back_vec),
                width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
                ticket=f"SillyShed Back Rafter {x_label}",
            )
        )

    return rafters


# -----------------------------------------------------------------------------
# Joint helpers
# -----------------------------------------------------------------------------

def _find_post(posts: list[Timber], side: str, x_tag: str) -> Timber:
    target_name = f"SillyShed Post {side} {x_tag}"
    for post in posts:
        if post.ticket.name == target_name:
            return post
    raise ValueError(f"Post not found: {target_name}")


def _find_rafter(rafters: list[Timber], side: str, x_tag: str) -> Timber:
    target_name = f"SillyShed {side} Rafter {x_tag}"
    for rafter in rafters:
        if rafter.ticket.name == target_name:
            return rafter
    raise ValueError(f"Rafter not found: {target_name}")


def _build_joints(
    base_front: Timber,
    base_back: Timber,
    base_left: Timber,
    base_right: Timber,
    posts: list[Timber],
    plate_front: Timber,
    plate_back: Timber,
    rafters: list[Timber],
) -> list[Joint]:
    joints: list[Joint] = []

    def _make_corner_arrangement(
        timber1: Timber,
        timber2: Timber,
        timber1_end: TimberReferenceEnd,
        timber2_end: TimberReferenceEnd,
    ) -> CornerJointTimberArrangement:
        corner_plane_normal = normalize_vector(
            cross_product(
                timber1.get_length_direction_global(),
                timber2.get_length_direction_global(),
            )
        )
        front_face_on_timber1 = timber1.get_closest_oriented_long_face_from_global_direction(
            corner_plane_normal
        )
        return CornerJointTimberArrangement(
            timber1=timber1,
            timber2=timber2,
            timber1_end=timber1_end,
            timber2_end=timber2_end,
            front_face_on_timber1=front_face_on_timber1,
        )

    # Mudsills: keyed miter joints on all four corners.
    joints.append(cut_mitered_and_keyed_lap_joint(_make_corner_arrangement(base_front, base_left, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.BOTTOM)))
    joints.append(cut_mitered_and_keyed_lap_joint(_make_corner_arrangement(base_front, base_right, TimberReferenceEnd.TOP, TimberReferenceEnd.BOTTOM)))
    joints.append(cut_mitered_and_keyed_lap_joint(_make_corner_arrangement(base_back, base_left, TimberReferenceEnd.BOTTOM, TimberReferenceEnd.TOP)))
    joints.append(cut_mitered_and_keyed_lap_joint(_make_corner_arrangement(base_back, base_right, TimberReferenceEnd.TOP, TimberReferenceEnd.TOP)))

    # Posts -> mudsills: short tenons.
    for side, mudsill in [("Front", base_front), ("Back", base_back)]:
        for x_tag in ["Left", "Center", "Right"]:
            post = _find_post(posts, side, x_tag)
            joints.append(
                cut_mortise_and_tenon_joint_on_FAT(
                    arrangement=ButtJointTimberArrangement(
                        receiving_timber=mudsill,
                        butt_timber=post,
                        butt_timber_end=TimberReferenceEnd.BOTTOM,
                    ),
                    tenon_size=post_to_mudsill_tenon_size,
                    tenon_length=post_to_mudsill_tenon_length,
                    mortise_depth=post_to_mudsill_tenon_length,
                    tenon_position=create_v2(Integer(0), Integer(0)),
                )
            )

    # Plates -> posts: mortise and tenon.
    for side, plate in [("Front", plate_front), ("Back", plate_back)]:
        for x_tag in ["Left", "Center", "Right"]:
            post = _find_post(posts, side, x_tag)
            joints.append(
                cut_mortise_and_tenon_joint_on_FAT(
                    arrangement=ButtJointTimberArrangement(
                        receiving_timber=plate,
                        butt_timber=post,
                        butt_timber_end=TimberReferenceEnd.TOP,
                    ),
                    tenon_size=post_to_plate_tenon_size,
                    tenon_length=post_to_plate_tenon_length,
                    mortise_depth=post_to_plate_tenon_length,
                    tenon_position=create_v2(Integer(0), Integer(0)),
                )
            )

    # Rafters -> plates (house joints), then front/back rafter pair -> tongue-and-fork at ridge.
    for x_tag in ["Left", "Center", "Right"]:
        front_rafter = _find_rafter(rafters, "Front", x_tag)
        back_rafter = _find_rafter(rafters, "Back", x_tag)

        joints.append(cut_plain_house_joint(CrossJointTimberArrangement(timber1=front_rafter, timber2=plate_front)))
        joints.append(cut_plain_house_joint(CrossJointTimberArrangement(timber1=back_rafter, timber2=plate_back)))

        joints.append(
            cut_tongue_and_fork_corner_joint(
                CornerJointTimberArrangement(
                    timber1=front_rafter,
                    timber2=back_rafter,
                    timber1_end=TimberReferenceEnd.TOP,
                    timber2_end=TimberReferenceEnd.TOP,
                )
            )
        )

    return joints


# -----------------------------------------------------------------------------
# Main builder
# -----------------------------------------------------------------------------

def create_sillyshed_frame(origin: Optional[V3] = None) -> Frame:
    if origin is None:
        origin = create_v3(Integer(0), Integer(0), Integer(0))

    base_front, base_back, base_left, base_right = _create_base_frame(origin)
    posts = _create_side_posts(origin)
    plate_front, plate_back = _create_top_plates(origin)
    rafters = _create_roof_rafters(origin)

    joints = _build_joints(
        base_front=base_front,
        base_back=base_back,
        base_left=base_left,
        base_right=base_right,
        posts=posts,
        plate_front=plate_front,
        plate_back=plate_back,
        rafters=rafters,
    )

    return Frame.from_joints(joints=joints, name="Silly Shed Frame")


def create_all_sillyshed_examples() -> Frame:
    return create_sillyshed_frame()


example = create_all_sillyshed_examples
