"""
Gateway Example - Outdoor gate with a built-in hallway.

Layout summary:
- Fence front: 5m wide with 6 evenly spaced posts.
- Hallway entrance: between the two middle fence posts.
- Rear fence supports: 2 posts aligned with outer fence posts, 0.5m toward back.
- Hallway: 8m long with 8 total posts (2 shared with the fence).
"""

from sympy import Rational
from typing import Optional

from kumiki import *


# Timber sizes (metric)
post_size = Matrix([cm(10), cm(10)])
beam_size = Matrix([cm(10), cm(15)])
plate_size = Matrix([cm(10), cm(15)])


# Overall dimensions
fence_width = m(5)
hallway_length = m(8)
rear_support_offset = cm(50)

regular_post_height = m(2)
entry_post_height = m(3)
rear_support_post_height = regular_post_height / Rational(2)


# Beam height offsets
fence_beam_bottom_z = cm(10)
fence_beam_top_z = regular_post_height - cm(10)
fence_inner_top_beam_z = fence_beam_top_z - cm(20)
outer_fence_top_plate_overhang = cm(10)

hallway_beam_bottom_z = cm(50)
hallway_beam_top_z = regular_post_height - cm(10)

entry_plate_z = entry_post_height
entry_beam_z = entry_plate_z - cm(20)
entry_top_plate_overhang = cm(50)
rear_support_top_beam_z = rear_support_post_height - cm(10)

# Entry roof (gable roof: ridge runs left-right, slopes to front/back)
roof_support_height = cm(45)
roof_side_overhang = cm(20)
roof_front_back_run = cm(90)
roof_rise = cm(40)

beam_tenon_size = Matrix([cm(4), cm(4)])
beam_tenon_length_into_post = post_size[0] / Rational(2)
post_tenon_size = Matrix([cm(4), cm(4)])
post_tenon_length_into_plate = plate_size[0] / Rational(2)


def _offset_position(x: Numeric, y: Numeric, z: Numeric, center: V3) -> V3:
    return create_v3(center[0] + x, center[1] + y, center[2] + z)


def create_gateway(center: Optional[V3] = None) -> Frame:
    if center is None:
        center = create_v3(Rational(0), Rational(0), Rational(0))

    one_meter = m(1)
    zero = Rational(0)

    # Fence front posts: x=0..5m, y=0
    front_fence_x_positions = [one_meter * Rational(i) for i in range(6)]

    # Entrance posts are the two middle fence posts (index 2 and 3)
    entry_left_x = front_fence_x_positions[2]
    entry_right_x = front_fence_x_positions[3]

    fence_posts_front = []
    for index, x_pos in enumerate(front_fence_x_positions):
        height = entry_post_height if index in (2, 3) else regular_post_height
        fence_posts_front.append(
            create_axis_aligned_timber(
                bottom_position=_offset_position(x_pos, zero, zero, center),
                length=height,
                size=post_size,
                length_direction=TimberFace.TOP,
                width_direction=TimberFace.RIGHT,
                ticket=f"Fence Front Post {index + 1}",
            )
        )

    rear_support_posts = [
        create_axis_aligned_timber(
            bottom_position=_offset_position(front_fence_x_positions[0], -rear_support_offset, zero, center),
            length=rear_support_post_height,
            size=post_size,
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Fence Rear Support Left",
        ),
        create_axis_aligned_timber(
            bottom_position=_offset_position(front_fence_x_positions[-1], -rear_support_offset, zero, center),
            length=rear_support_post_height,
            size=post_size,
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket="Fence Rear Support Right",
        ),
    ]

    # Hallway has 8 total posts; 2 are shared with the entry posts.
    # Use 4 rows (2 posts each) across y=0..-8m.
    hallway_row_count = Rational(4)
    hallway_step = hallway_length / (hallway_row_count - Rational(1))
    hallway_row_y_positions = [-(hallway_step * Rational(i)) for i in range(4)]

    hallway_left_x = entry_left_x
    hallway_right_x = entry_right_x

    # Shared front hallway posts are fence posts 3 and 4.
    hallway_shared_posts = [fence_posts_front[2], fence_posts_front[3]]

    hallway_left_posts = [fence_posts_front[2]]
    hallway_right_posts = [fence_posts_front[3]]

    hallway_additional_posts = []
    for row_index in range(1, 4):
        y_pos = hallway_row_y_positions[row_index]
        left_post = create_axis_aligned_timber(
            bottom_position=_offset_position(hallway_left_x, y_pos, zero, center),
            length=regular_post_height,
            size=post_size,
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket=f"Hallway Left Post {row_index + 1}",
        )
        right_post = create_axis_aligned_timber(
            bottom_position=_offset_position(hallway_right_x, y_pos, zero, center),
            length=regular_post_height,
            size=post_size,
            length_direction=TimberFace.TOP,
            width_direction=TimberFace.RIGHT,
            ticket=f"Hallway Right Post {row_index + 1}",
        )

        hallway_left_posts.append(left_post)
        hallway_right_posts.append(right_post)
        hallway_additional_posts.extend([left_post, right_post])

    # Fence beams segmented per bay (beam segments stop at posts).
    # Skip the middle bay (between posts 3 and 4) to keep the entry opening clear.
    fence_bottom_beam_segments = []
    fence_top_inner_beam_segments = []
    fence_top_outer_plate_segments = []
    for bay_index in range(5):
        if bay_index == 2:
            continue

        x_start = front_fence_x_positions[bay_index]
        x_end = front_fence_x_positions[bay_index + 1]
        segment_length = x_end - x_start

        fence_bottom_beam_segments.append(
            create_axis_aligned_timber(
                bottom_position=_offset_position(x_start, zero, fence_beam_bottom_z, center),
                length=segment_length,
                size=beam_size,
                length_direction=TimberFace.RIGHT,
                width_direction=TimberFace.FRONT,
                ticket=f"Fence Beam Bottom Bay {bay_index + 1}",
            )
        )

        if bay_index in (1, 3):
            fence_top_inner_beam_segments.append(
                create_axis_aligned_timber(
                    bottom_position=_offset_position(x_start, zero, fence_inner_top_beam_z, center),
                    length=segment_length,
                    size=beam_size,
                    length_direction=TimberFace.RIGHT,
                    width_direction=TimberFace.FRONT,
                    ticket=f"Fence Beam Top Inner Bay {bay_index + 1}",
                )
            )
        else:
            fence_top_outer_plate_segments.append(
                create_axis_aligned_timber(
                    bottom_position=_offset_position(x_start - outer_fence_top_plate_overhang, zero, regular_post_height, center),
                    length=segment_length + outer_fence_top_plate_overhang * Rational(2),
                    size=plate_size,
                    length_direction=TimberFace.RIGHT,
                    width_direction=TimberFace.FRONT,
                    ticket=f"Fence Top Plate Outer Bay {bay_index + 1}",
                )
            )

    # Rear support connector beams: bottom at fence bottom-beam level,
    # top at 10cm below rear support top.
    # Connect each outer front fence post to its rear support post.
    rear_support_connector_length = rear_support_offset
    rear_support_connector_beams = [
        create_axis_aligned_timber(
            bottom_position=_offset_position(front_fence_x_positions[0], zero, fence_beam_bottom_z, center),
            length=rear_support_connector_length,
            size=beam_size,
            length_direction=TimberFace.BACK,
            width_direction=TimberFace.RIGHT,
            ticket="Rear Support Connector Left Bottom",
        ),
        create_axis_aligned_timber(
            bottom_position=_offset_position(front_fence_x_positions[0], zero, rear_support_top_beam_z, center),
            length=rear_support_connector_length,
            size=beam_size,
            length_direction=TimberFace.BACK,
            width_direction=TimberFace.RIGHT,
            ticket="Rear Support Connector Left Top",
        ),
        create_axis_aligned_timber(
            bottom_position=_offset_position(front_fence_x_positions[-1], zero, fence_beam_bottom_z, center),
            length=rear_support_connector_length,
            size=beam_size,
            length_direction=TimberFace.BACK,
            width_direction=TimberFace.RIGHT,
            ticket="Rear Support Connector Right Bottom",
        ),
        create_axis_aligned_timber(
            bottom_position=_offset_position(front_fence_x_positions[-1], zero, rear_support_top_beam_z, center),
            length=rear_support_connector_length,
            size=beam_size,
            length_direction=TimberFace.BACK,
            width_direction=TimberFace.RIGHT,
            ticket="Rear Support Connector Right Top",
        ),
    ]

    # Hallway side beams segmented between each pair of hallway post rows.
    hallway_left_beam_bottom_segments = []
    hallway_left_beam_top_segments = []
    hallway_right_beam_bottom_segments = []
    hallway_right_beam_top_segments = []

    for segment_index in range(3):
        y_start = hallway_row_y_positions[segment_index]
        y_end = hallway_row_y_positions[segment_index + 1]
        segment_length = y_start - y_end

        hallway_left_beam_bottom_segments.append(
            create_axis_aligned_timber(
                bottom_position=_offset_position(hallway_left_x, y_start, hallway_beam_bottom_z, center),
                length=segment_length,
                size=beam_size,
                length_direction=TimberFace.BACK,
                width_direction=TimberFace.RIGHT,
                ticket=f"Hallway Left Beam Bottom Segment {segment_index + 1}",
            )
        )

        hallway_left_beam_top_segments.append(
            create_axis_aligned_timber(
                bottom_position=_offset_position(hallway_left_x, y_start, hallway_beam_top_z, center),
                length=segment_length,
                size=beam_size,
                length_direction=TimberFace.BACK,
                width_direction=TimberFace.RIGHT,
                ticket=f"Hallway Left Beam Top Segment {segment_index + 1}",
            )
        )

        hallway_right_beam_bottom_segments.append(
            create_axis_aligned_timber(
                bottom_position=_offset_position(hallway_right_x, y_start, hallway_beam_bottom_z, center),
                length=segment_length,
                size=beam_size,
                length_direction=TimberFace.BACK,
                width_direction=TimberFace.RIGHT,
                ticket=f"Hallway Right Beam Bottom Segment {segment_index + 1}",
            )
        )

        hallway_right_beam_top_segments.append(
            create_axis_aligned_timber(
                bottom_position=_offset_position(hallway_right_x, y_start, hallway_beam_top_z, center),
                length=segment_length,
                size=beam_size,
                length_direction=TimberFace.BACK,
                width_direction=TimberFace.RIGHT,
                ticket=f"Hallway Right Beam Top Segment {segment_index + 1}",
            )
        )

    # Entry-specific members between the two taller posts
    entry_beam = create_axis_aligned_timber(
        bottom_position=_offset_position(entry_left_x, zero, entry_beam_z, center),
        length=entry_right_x - entry_left_x,
        size=beam_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Entry Beam",
    )

    entry_top_plate = create_axis_aligned_timber(
        bottom_position=_offset_position(entry_left_x - entry_top_plate_overhang, zero, entry_plate_z, center),
        length=(entry_right_x - entry_left_x) + entry_top_plate_overhang * Rational(2),
        size=plate_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Entry Top Plate",
    )

    roof_base_z = entry_plate_z + plate_size[1]
    roof_left_x = entry_left_x - roof_side_overhang
    roof_right_x = entry_right_x + roof_side_overhang
    roof_span_x = roof_right_x - roof_left_x
    roof_front_y = roof_front_back_run
    roof_back_y = -roof_front_back_run
    roof_ridge_z = roof_base_z + roof_support_height + roof_rise
    roof_eave_z = roof_base_z + roof_support_height

    roof_support_left = create_axis_aligned_timber(
        bottom_position=_offset_position(entry_left_x, zero, roof_base_z, center),
        length=roof_support_height,
        size=post_size,
        length_direction=TimberFace.TOP,
        width_direction=TimberFace.RIGHT,
        ticket="Roof Support Left",
    )
    roof_support_right = create_axis_aligned_timber(
        bottom_position=_offset_position(entry_right_x, zero, roof_base_z, center),
        length=roof_support_height,
        size=post_size,
        length_direction=TimberFace.TOP,
        width_direction=TimberFace.RIGHT,
        ticket="Roof Support Right",
    )

    roof_ridge_beam = create_axis_aligned_timber(
        bottom_position=_offset_position(roof_left_x, zero, roof_ridge_z, center),
        length=roof_span_x,
        size=beam_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Roof Ridge Beam",
    )

    roof_front_eave_plate = create_axis_aligned_timber(
        bottom_position=_offset_position(roof_left_x, roof_front_y, roof_eave_z, center),
        length=roof_span_x,
        size=plate_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Roof Front Eave Plate",
    )
    roof_back_eave_plate = create_axis_aligned_timber(
        bottom_position=_offset_position(roof_left_x, roof_back_y, roof_eave_z, center),
        length=roof_span_x,
        size=plate_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Roof Back Eave Plate",
    )

    roof_rafter_x_positions = [roof_left_x, (entry_left_x + entry_right_x) / Rational(2), roof_right_x]
    roof_front_rafters = []
    roof_back_rafters = []
    for rafter_index, rafter_x in enumerate(roof_rafter_x_positions, start=1):
        front_vec = create_v3(Rational(0), roof_front_y, roof_eave_z - roof_ridge_z)
        back_vec = create_v3(Rational(0), roof_back_y, roof_eave_z - roof_ridge_z)

        roof_front_rafters.append(
            create_timber(
                bottom_position=_offset_position(rafter_x, zero, roof_ridge_z, center),
                length=vector_magnitude(front_vec),
                size=beam_size,
                length_direction=normalize_vector(front_vec),
                width_direction=create_v3(Rational(1), Rational(0), Rational(0)),
                ticket=f"Roof Front Rafter {rafter_index}",
            )
        )
        roof_back_rafters.append(
            create_timber(
                bottom_position=_offset_position(rafter_x, zero, roof_ridge_z, center),
                length=vector_magnitude(back_vec),
                size=beam_size,
                length_direction=normalize_vector(back_vec),
                width_direction=create_v3(Rational(1), Rational(0), Rational(0)),
                ticket=f"Roof Back Rafter {rafter_index}",
            )
        )

    roof_braces = []
    brace_specs = [
        (entry_left_x, roof_front_y, "Roof Brace Left Front"),
        (entry_left_x, roof_back_y, "Roof Brace Left Back"),
        (entry_right_x, roof_front_y, "Roof Brace Right Front"),
        (entry_right_x, roof_back_y, "Roof Brace Right Back"),
    ]
    for brace_x, brace_y, brace_name in brace_specs:
        brace_start_z = roof_base_z + roof_support_height - cm(5)
        brace_end_z = roof_eave_z + cm(5)
        brace_vec = create_v3(Rational(0), brace_y, brace_end_z - brace_start_z)
        roof_braces.append(
            create_timber(
                bottom_position=_offset_position(brace_x, zero, brace_start_z, center),
                length=vector_magnitude(brace_vec),
                size=Matrix([cm(8), cm(8)]),
                length_direction=normalize_vector(brace_vec),
                width_direction=create_v3(Rational(1), Rational(0), Rational(0)),
                ticket=brace_name,
            )
        )

    def _beam_to_post_joint(beam: Timber, beam_end: TimberReferenceEnd, post: Timber) -> Joint:
        return cut_mortise_and_tenon_joint_on_FAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=post,
                butt_timber=beam,
                butt_timber_end=beam_end,
                front_face_on_butt_timber=None,
            ),
            tenon_size=beam_tenon_size,
            tenon_length=beam_tenon_length_into_post,
            mortise_depth=beam_tenon_length_into_post,
            peg_parameters=None,
        )

    def _beam_to_plate_joint(beam: Timber, beam_end: TimberReferenceEnd, plate: Timber) -> Joint:
        return cut_mortise_and_tenon_joint_on_FAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=plate,
                butt_timber=beam,
                butt_timber_end=beam_end,
                front_face_on_butt_timber=None,
            ),
            tenon_size=beam_tenon_size,
            tenon_length=post_tenon_length_into_plate,
            mortise_depth=post_tenon_length_into_plate,
            peg_parameters=None,
        )

    def _post_to_plate_joint(post: Timber, plate: Timber) -> Joint:
        return cut_mortise_and_tenon_joint_on_FAT(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=plate,
                butt_timber=post,
                butt_timber_end=TimberReferenceEnd.TOP,
                front_face_on_butt_timber=None,
            ),
            tenon_size=post_tenon_size,
            tenon_length=post_tenon_length_into_plate,
            mortise_depth=post_tenon_length_into_plate,
            peg_parameters=None,
        )

    all_joints = []

    # Fence front beam segments (4 bays because entry bay is skipped)
    fence_front_bay_pairs = [
        (0, 1),
        (1, 2),
        (3, 4),
        (4, 5),
    ]
    for segment, (left_index, right_index) in zip(fence_bottom_beam_segments, fence_front_bay_pairs):
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.BOTTOM, fence_posts_front[left_index]))
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.TOP, fence_posts_front[right_index]))

    inner_top_bay_pairs = [
        (1, 2),
        (3, 4),
    ]
    for segment, (left_index, right_index) in zip(fence_top_inner_beam_segments, inner_top_bay_pairs):
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.BOTTOM, fence_posts_front[left_index]))
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.TOP, fence_posts_front[right_index]))

    outer_top_bay_pairs = [
        (0, 1),
        (4, 5),
    ]
    for segment, (left_index, right_index) in zip(fence_top_outer_plate_segments, outer_top_bay_pairs):
        all_joints.append(_post_to_plate_joint(fence_posts_front[left_index], segment))
        all_joints.append(_post_to_plate_joint(fence_posts_front[right_index], segment))

    # Rear support connector beams (left/right, bottom/top)
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[0], TimberReferenceEnd.BOTTOM, fence_posts_front[0]))
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[0], TimberReferenceEnd.TOP, rear_support_posts[0]))
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[1], TimberReferenceEnd.BOTTOM, fence_posts_front[0]))
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[1], TimberReferenceEnd.TOP, rear_support_posts[0]))
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[2], TimberReferenceEnd.BOTTOM, fence_posts_front[5]))
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[2], TimberReferenceEnd.TOP, rear_support_posts[1]))
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[3], TimberReferenceEnd.BOTTOM, fence_posts_front[5]))
    all_joints.append(_beam_to_post_joint(rear_support_connector_beams[3], TimberReferenceEnd.TOP, rear_support_posts[1]))

    # Hallway beam segments per row pair (left side)
    for row_index, segment in enumerate(hallway_left_beam_bottom_segments):
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.BOTTOM, hallway_left_posts[row_index]))
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.TOP, hallway_left_posts[row_index + 1]))
    for row_index, segment in enumerate(hallway_left_beam_top_segments):
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.BOTTOM, hallway_left_posts[row_index]))
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.TOP, hallway_left_posts[row_index + 1]))

    # Hallway beam segments per row pair (right side)
    for row_index, segment in enumerate(hallway_right_beam_bottom_segments):
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.BOTTOM, hallway_right_posts[row_index]))
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.TOP, hallway_right_posts[row_index + 1]))
    for row_index, segment in enumerate(hallway_right_beam_top_segments):
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.BOTTOM, hallway_right_posts[row_index]))
        all_joints.append(_beam_to_post_joint(segment, TimberReferenceEnd.TOP, hallway_right_posts[row_index + 1]))

    # Entry beam into entry posts
    all_joints.append(_beam_to_post_joint(entry_beam, TimberReferenceEnd.BOTTOM, fence_posts_front[2]))
    all_joints.append(_beam_to_post_joint(entry_beam, TimberReferenceEnd.TOP, fence_posts_front[3]))

    # Entry posts into top plate
    all_joints.append(_post_to_plate_joint(fence_posts_front[2], entry_top_plate))
    all_joints.append(_post_to_plate_joint(fence_posts_front[3], entry_top_plate))

    # Roof supports and ridge/eave members
    all_joints.append(_post_to_plate_joint(roof_support_left, entry_top_plate))
    all_joints.append(_post_to_plate_joint(roof_support_right, entry_top_plate))
    all_joints.append(_post_to_plate_joint(roof_support_left, roof_ridge_beam))
    all_joints.append(_post_to_plate_joint(roof_support_right, roof_ridge_beam))

    # Sloped rafters and braces are modeled geometrically for roof form/support.
    # Mortise-tenon joints are kept on the roof supports and ridge connections above.

    all_unjointed_timbers = [
        *fence_posts_front,
        *rear_support_posts,
        *hallway_shared_posts,
        *hallway_additional_posts,
        *fence_bottom_beam_segments,
        *fence_top_inner_beam_segments,
        *fence_top_outer_plate_segments,
        *rear_support_connector_beams,
        *hallway_left_beam_bottom_segments,
        *hallway_left_beam_top_segments,
        *hallway_right_beam_bottom_segments,
        *hallway_right_beam_top_segments,
        entry_beam,
        entry_top_plate,
        roof_support_left,
        roof_support_right,
        roof_ridge_beam,
        roof_front_eave_plate,
        roof_back_eave_plate,
        *roof_front_rafters,
        *roof_back_rafters,
        *roof_braces,
    ]

    # Deduplicate shared references (hallway_shared_posts are same objects as fence posts 3/4)
    unique_timbers_by_id = {id(timber): timber for timber in all_unjointed_timbers}

    return Frame.from_joints(
        joints=all_joints,
        additional_unjointed_timbers=list(unique_timbers_by_id.values()),
        name="Gateway",
    )


example = create_gateway


def main() -> Frame:
    frame = create_gateway()
    print(f"Created '{frame.name}' with {len(frame.cut_timbers)} timbers")
    return frame


if __name__ == "__main__":
    main()
