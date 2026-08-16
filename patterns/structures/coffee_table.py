
from kumiki import *
from dataclasses import replace


def build_frame() -> Frame:

    base_width = inches(32.5)
    base_length = inches(17.5)

    leg_height = inches(15)
    leg_size = create_v2(inches(1.75),inches(1.75))

    top_stretcher_size = create_v2(inches(3), inches(3/4))
    top_short_stretcher_size = create_v2(inches(3 + 3/8), inches(3/4))

    bot_stretcher_size = create_v2(inches(1.5),inches(1))
    bot_stretcher_length_position = inches(4)  # length_position_measurement for all 4 bottom stretchers

    stretcher_tenon_size = inches(3/4)
    tenon_length_past_opposite_shoulder = inches(2)  # shared by all 8 top-stretcher tusked M&T joints
    tusk_size = stretcher_tenon_size / scalar(3)  # shared tusk_thickness / tusk_small_width
    # tenon_position x-offset for the top-stretcher M&T joints: positive for the
    # south/north stretchers, negative for the west/east stretchers.
    tenon_lateral_offset = inches(3/8) + inches(3/32)

    top_short_stretcher_length_position = inches(-3/8)  # length_position_measurement for west/east top stretchers

    dovetail_depth = inches(3/8)
    dovetail_small_width = inches(3/8)
    dovetail_angle = degrees(83)

    roundover_radius = inches(1/2)
    all_long_edges = [TimberEdge.RIGHT_FRONT, TimberEdge.FRONT_LEFT, TimberEdge.LEFT_BACK, TimberEdge.BACK_RIGHT]

    # Gentle "B-shape" rounded-end decoration on the table top boards. distance_from_end
    # equal to the radius puts the arc's surface exactly tangent at the lateral center of
    # the end (untouched there), receding by the sagitta (~0.5in over the 12in width, for
    # this radius) out toward the corners -- a single continuous bulge across the whole
    # width, rather than an only-the-corners fillet (distance_from_end < radius) or a
    # deeper dome that also recedes at the center (distance_from_end > radius).
    rounded_end_radius = inches(8)
    rounded_end_distance_from_end = rounded_end_radius

    table_half_width = inches(12)
    table_thickness = inches(3/4)
    table_length = inches(48)

    footprint_corners = [
        create_v2(scalar(0), scalar(0)),       # Corner 0: South-West
        create_v2(base_width, scalar(0)),      # Corner 1: South-East
        create_v2(base_width, base_length),     # Corner 2: North-East
        create_v2(scalar(0), base_length)       # Corner 3: North-West
    ]
    footprint = Footprint(footprint_corners)  # type: ignore[arg-type]

    leg_sw = create_vertical_timber_on_footprint_corner(
        footprint, 0, leg_height, FootprintLocation.INSIDE, leg_size,
        ticket=TimberTicket(path="southwest-leg", tags=("leg",))
    )
    leg_se = create_vertical_timber_on_footprint_corner(
        footprint, 1, leg_height, FootprintLocation.INSIDE, leg_size,
        ticket=TimberTicket(path="southeast-leg", tags=("leg",))
    )
    leg_ne = create_vertical_timber_on_footprint_corner(
        footprint, 2, leg_height, FootprintLocation.INSIDE, leg_size,
        ticket=TimberTicket(path="northeast-leg", tags=("leg",))
    )
    leg_nw = create_vertical_timber_on_footprint_corner(
        footprint, 3, leg_height, FootprintLocation.INSIDE, leg_size,
        ticket=TimberTicket(path="northwest-leg", tags=("leg",))
    )
    top_stretcher_s = attach_face_aligned_timber(
        original_timber=leg_sw,
        size=top_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=leg_se,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.RIGHT,
        length_position_measurement=inches(0),
        ticket=TimberTicket(path="south-top-stretcher", tags=("stretcher", "top"))
    )
    top_stretcher_n = attach_face_aligned_timber(
        original_timber=leg_nw,
        size=top_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=leg_ne,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.RIGHT,
        length_position_measurement=inches(0),
        ticket=TimberTicket(path="north-top-stretcher", tags=("stretcher", "top"))
    )

    top_stretcher_w = attach_face_aligned_timber(
        original_timber=leg_sw,
        size=top_short_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=leg_nw,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.RIGHT,
        length_position_measurement=top_short_stretcher_length_position,
        ticket=TimberTicket(path="west-top-stretcher", tags=("stretcher", "top"))
    )

    top_stretcher_e = attach_face_aligned_timber(
        original_timber=leg_se,
        size=top_short_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=leg_ne,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.RIGHT,
        length_position_measurement=top_short_stretcher_length_position,
        ticket=TimberTicket(path="east-top-stretcher", tags=("stretcher", "top"))
    )

    sw_to_s_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_sw,
            butt_timber=top_stretcher_s,
            butt_timber_end=TimberEnd.BOTTOM,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(tenon_lateral_offset, 0),
    )

    se_to_s_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_se,
            butt_timber=top_stretcher_s,
            butt_timber_end=TimberEnd.TOP,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(tenon_lateral_offset, 0),
    )

    nw_to_n_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_nw,
            butt_timber=top_stretcher_n,
            butt_timber_end=TimberEnd.BOTTOM,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(tenon_lateral_offset, 0),
    )

    ne_to_n_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_ne,
            butt_timber=top_stretcher_n,
            butt_timber_end=TimberEnd.TOP,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(tenon_lateral_offset, 0),
    )

    sw_to_w_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_sw,
            butt_timber=top_stretcher_w,
            butt_timber_end=TimberEnd.BOTTOM,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(-tenon_lateral_offset, 0),
    )
    nw_to_w_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_nw,
            butt_timber=top_stretcher_w,
            butt_timber_end=TimberEnd.TOP,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(-tenon_lateral_offset, 0),
    )

    se_to_e_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_se,
            butt_timber=top_stretcher_e,
            butt_timber_end=TimberEnd.BOTTOM,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(-tenon_lateral_offset, 0),
    )
    ne_to_e_stretcher_joint = cut_practice_tusked_mortise_and_tenon_joint_on_plane_aligned_timbers(
        arrangement = ButtJointTimberArrangement(
            receiving_timber=leg_ne,
            butt_timber=top_stretcher_e,
            butt_timber_end=TimberEnd.TOP,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
            front_face_on_butt_timber=TimberLongFace.BACK,
        ),
        tenon_size = create_v2(stretcher_tenon_size, stretcher_tenon_size),
        tenon_length_past_opposite_shoulder = tenon_length_past_opposite_shoulder,
        tusk_parameters = TuskParameters(
            tusk_thickness = tusk_size,
            tusk_small_width = tusk_size,
        ),
        tenon_position = create_v2(-tenon_lateral_offset, 0),
    )

    table_top_south = attach_face_aligned_timber(
        original_timber=leg_sw,
        size=create_v2(table_half_width, table_thickness),
        attached_timber_stickout=Stickout.symmetric((table_length-base_width)/scalar(2), StickoutReference.OUTSIDE),
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=leg_se,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        # TODO BUG aligning BACK face rather than FRONT???
        attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.FRONT,
        length_position_measurement=inches(0),
        lateral_position_measurement=inches(-1.875),
        ticket=TimberTicket(path="south-table-top", tags=("table-top",))
    )
    table_top_north = attach_face_aligned_timber(
        original_timber=leg_nw,
        size=create_v2(table_half_width, table_thickness),
        attached_timber_stickout=Stickout.symmetric((table_length-base_width)/scalar(2), StickoutReference.OUTSIDE),
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=leg_ne,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.TOP,
        # TODO BUG aligning BACK face rather than FRONT???
        attached_timber_long_face_to_measure_to_for_length_position=TimberLongFace.FRONT,
        length_position_measurement=inches(0),
        lateral_position_measurement=inches(1.875),
        ticket=TimberTicket(path="north-table-top", tags=("table-top",)),
    )

    south_table_top_round_bottom = cut_practice_rounded_end_decoration(
        timber = table_top_south,
        rounded_face = TimberFace.FRONT,
        rounded_end = TimberFace.BOTTOM,
        radius = rounded_end_radius,
        distance_from_end = rounded_end_distance_from_end,
    )
    south_table_top_round_top = cut_practice_rounded_end_decoration(
        timber = table_top_south,
        rounded_face = TimberFace.FRONT,
        rounded_end = TimberFace.TOP,
        radius = rounded_end_radius,
        distance_from_end = rounded_end_distance_from_end,
    )
    north_table_top_round_bottom = cut_practice_rounded_end_decoration(
        timber = table_top_north,
        rounded_face = TimberFace.FRONT,
        rounded_end = TimberFace.BOTTOM,
        radius = rounded_end_radius,
        distance_from_end = rounded_end_distance_from_end,
    )
    north_table_top_round_top = cut_practice_rounded_end_decoration(
        timber = table_top_north,
        rounded_face = TimberFace.FRONT,
        rounded_end = TimberFace.TOP,
        radius = rounded_end_radius,
        distance_from_end = rounded_end_distance_from_end,
    )


    ne_table_joint = cut_practice_sliding_dovetail_joint_on_orthogonal_boards(
        arrangement = ButtJointBoardArrangement(
            butt_timber = top_stretcher_e,
            receiving_timber = table_top_north,
            butt_timber_face = TimberFace.RIGHT,
            front_face_on_butt_timber = TimberFace.TOP,
        ),
        dovetail_depth = dovetail_depth,
        dovetail_small_width = dovetail_small_width,
        dovetail_angle = dovetail_angle,
    )
    se_table_joint = cut_practice_sliding_dovetail_joint_on_orthogonal_boards(
        arrangement = ButtJointBoardArrangement(
            butt_timber = top_stretcher_e,
            receiving_timber = table_top_south,
            butt_timber_face = TimberFace.RIGHT,
            front_face_on_butt_timber = TimberFace.BOTTOM,
        ),
        dovetail_depth = dovetail_depth,
        dovetail_small_width = dovetail_small_width,
        dovetail_angle = dovetail_angle,
    )
    nw_table_joint = cut_practice_sliding_dovetail_joint_on_orthogonal_boards(
        arrangement = ButtJointBoardArrangement(
            butt_timber = top_stretcher_w,
            receiving_timber = table_top_north,
            butt_timber_face = TimberFace.RIGHT,
            front_face_on_butt_timber = TimberFace.TOP,
        ),
        dovetail_depth = dovetail_depth,
        dovetail_small_width = dovetail_small_width,
        dovetail_angle = dovetail_angle,
    )
    sw_table_joint = cut_practice_sliding_dovetail_joint_on_orthogonal_boards(
        arrangement = ButtJointBoardArrangement(
            butt_timber = top_stretcher_w,
            receiving_timber = table_top_south,
            butt_timber_face = TimberFace.RIGHT,
            front_face_on_butt_timber = TimberFace.BOTTOM,
        ),
        dovetail_depth = dovetail_depth,
        dovetail_small_width = dovetail_small_width,
        dovetail_angle = dovetail_angle,
    )


    bot_stretcher_s = attach_face_aligned_timber(
        original_timber=leg_sw,
        size=bot_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=leg_se,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        attached_timber_long_face_to_measure_to_for_length_position=TimberCenterline.CENTERLINE,
        length_position_measurement=bot_stretcher_length_position,
        ticket=TimberTicket(path="south-bottom-stretcher", tags=("stretcher", "bottom"))
    )
    bot_stretcher_n = attach_face_aligned_timber(
        original_timber=leg_nw,
        size=bot_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=leg_ne,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        attached_timber_long_face_to_measure_to_for_length_position=TimberCenterline.CENTERLINE,
        length_position_measurement=bot_stretcher_length_position,
        ticket=TimberTicket(path="north-bottom-stretcher", tags=("stretcher", "bottom"))
    )

    bot_stretcher_w = attach_face_aligned_timber(
        original_timber=leg_sw,
        size=bot_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.FRONT,
        attached_timber_length_or_target=leg_nw,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        attached_timber_long_face_to_measure_to_for_length_position=TimberCenterline.CENTERLINE,
        length_position_measurement=bot_stretcher_length_position,
        ticket=TimberTicket(path="west-bottom-stretcher", tags=("stretcher", "bottom"))
    )

    bot_stretcher_e = attach_face_aligned_timber(
        original_timber=leg_se,
        size=bot_stretcher_size,
        original_timber_long_face_that_attached_timber_points_to=TimberLongFace.RIGHT,
        attached_timber_length_or_target=leg_ne,
        original_timber_end_to_measure_from_for_length_position=TimberEnd.BOTTOM,
        attached_timber_long_face_to_measure_to_for_length_position=TimberCenterline.CENTERLINE,
        length_position_measurement=bot_stretcher_length_position,
        ticket=TimberTicket(path="east-bottom-stretcher", tags=("stretcher", "bottom"))
    )

    nw_bot_joint = cut_basic_plain_miter_joint(
        arrangement = CornerJointTimberArrangement(
            timber1 = bot_stretcher_n,
            timber2 = bot_stretcher_w,
            timber1_end = TimberEnd.BOTTOM,
            timber2_end = TimberEnd.TOP
        )
    )
    sw_bot_joint = cut_basic_plain_miter_joint(
        arrangement = CornerJointTimberArrangement(
            timber1 = bot_stretcher_s,
            timber2 = bot_stretcher_w,
            timber1_end = TimberEnd.BOTTOM,
            timber2_end = TimberEnd.BOTTOM,
        )
    )
    ne_bot_joint = cut_basic_plain_miter_joint(
        arrangement = CornerJointTimberArrangement(
            timber1 = bot_stretcher_n,
            timber2 = bot_stretcher_e,
            timber1_end = TimberEnd.TOP,
            timber2_end = TimberEnd.TOP
        )
    )
    se_bot_joint = cut_basic_plain_miter_joint(
        arrangement = CornerJointTimberArrangement(
            timber1 = bot_stretcher_s,
            timber2 = bot_stretcher_e,
            timber1_end = TimberEnd.TOP,
            timber2_end = TimberEnd.BOTTOM,
        )
    )

    # TODO: disabled for now -- causes a rendering issue when included in the house
    # joints' housed bodies below. Re-enable (and pass into the CutTimber.from_joints
    # calls + the frame's joint list) once that's root-caused.
    # n_bot_roundover = cut_practice_roundover_decoration(
    #     timber = bot_stretcher_n,
    #     edges = all_long_edges,
    #     radius = roundover_radius
    # )
    # s_bot_roundover = cut_practice_roundover_decoration(
    #     timber = bot_stretcher_s,
    #     edges = all_long_edges,
    #     radius = roundover_radius
    # )
    # e_bot_roundover = cut_practice_roundover_decoration(
    #     timber = bot_stretcher_e,
    #     edges = all_long_edges,
    #     radius = roundover_radius
    # )
    # w_bot_roundover = cut_practice_roundover_decoration(
    #     timber = bot_stretcher_w,
    #     edges = all_long_edges,
    #     radius = roundover_radius
    # )

    # Each stretcher is housed using its actual body so far -- both corner miters it
    # participates in -- via CutTimber.from_joints, rather than hand-picking a
    # Joint.cuttings["timberA"/"timberB"] key (easy to pair with the wrong timber).
    # Irrelevant cuts (e.g. the miter at the timber's other, far-away end) are pruned
    # automatically by cut_free_house_joint based on whether they actually reach the
    # housing's cross section.
    sw_house_joint = cut_free_house_joint(
        housing_timber = leg_sw,
        housed_timbers = [
            CutTimber.from_joints(bot_stretcher_w, [sw_bot_joint, nw_bot_joint]),
            CutTimber.from_joints(bot_stretcher_s, [sw_bot_joint, se_bot_joint]),
        ]
    )
    nw_house_joint = cut_free_house_joint(
        housing_timber = leg_nw,
        housed_timbers = [
            CutTimber.from_joints(bot_stretcher_n, [nw_bot_joint, ne_bot_joint]),
            CutTimber.from_joints(bot_stretcher_w, [sw_bot_joint, nw_bot_joint]),
        ]
    )
    ne_house_joint = cut_free_house_joint(
        housing_timber = leg_ne,
        housed_timbers = [
            CutTimber.from_joints(bot_stretcher_n, [nw_bot_joint, ne_bot_joint]),
            CutTimber.from_joints(bot_stretcher_e, [ne_bot_joint, se_bot_joint]),
        ]
    )
    se_house_joint = cut_free_house_joint(
        housing_timber = leg_se,
        housed_timbers = [
            CutTimber.from_joints(bot_stretcher_s, [sw_bot_joint, se_bot_joint]),
            CutTimber.from_joints(bot_stretcher_e, [ne_bot_joint, se_bot_joint]),
        ]
    )

    frame = Frame.from_joints([
        sw_to_s_stretcher_joint, se_to_s_stretcher_joint,
        nw_to_n_stretcher_joint, ne_to_n_stretcher_joint,
        sw_to_w_stretcher_joint, nw_to_w_stretcher_joint,
        se_to_e_stretcher_joint, ne_to_e_stretcher_joint,
        ne_table_joint, se_table_joint, nw_table_joint, sw_table_joint,
        nw_bot_joint, ne_bot_joint, sw_bot_joint, se_bot_joint,
        sw_house_joint, nw_house_joint, ne_house_joint, se_house_joint,
        south_table_top_round_bottom, south_table_top_round_top,
        north_table_top_round_bottom, north_table_top_round_top,
    ], [], name="my coffee table")
    replace(frame, footprints=[footprint])

    return frame


example = build_frame
