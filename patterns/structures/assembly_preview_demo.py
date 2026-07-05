"""Assembly preview demo: an H-frame with a disassembly sequence.

Joint cut functions author their own assembly freedoms (escape directions and
travel) and suborders (pegs pop before their joint slides), so the assembly
plan is just an order per joint via `with_order`:

- Order 1: pegs pop (1.0), then the right side slides +X off both cross-timber
  tenons (1.1). The brace is rigidly butt-jointed to it, so it gets dragged
  along — and because the brace's own extraction is order 3, this also demos
  the "dragged a later-ordered member" warning badge.
- Order 2: the front-left peg pops (2.0), then the front cross slides out of
  the left side's mortise (2.1).
- Order 3: the (already dragged) brace pulls off the right side.
- Order 4: the last peg pops (4.0), then the back cross and left side separate
  (4.1).

Scrub the timeline at the bottom of the kigumi viewer to step through the
sequence; the disassembly spacing multiplier lives in the viewer options.
"""

from kumiki import *


# --- Dimensions (same H-frame as my_cute_frame) ------------------------------

timber_size = Matrix([mm(90), mm(90)])

side_length = mm(600)
side_spacing = mm(500)
end_inset = mm(100)

tenon_size = Matrix([mm(80), mm(40)])
tenon_length = mm(75)
mortise_depth = tenon_length + mm(6)

peg_diameter = mm(15)
peg_draw_bore_offset = mm(2)

brace_length = mm(250)


def build_frame() -> Frame:
    left_side = create_axis_aligned_timber(
        bottom_position=create_v3(-side_spacing / 2, -side_length / 2, scalar(0)),
        length=side_length,
        size=timber_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket="Left Side",
    )
    right_side = create_axis_aligned_timber(
        bottom_position=create_v3(side_spacing / 2, -side_length / 2, scalar(0)),
        length=side_length,
        size=timber_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket="Right Side",
    )

    cross_length = side_spacing
    cross_y_front = side_length / 2 - end_inset
    cross_y_back = -cross_y_front

    back_cross = create_axis_aligned_timber(
        bottom_position=create_v3(-cross_length / 2, cross_y_back, scalar(0)),
        length=cross_length,
        size=timber_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Back Cross",
    )
    front_cross = create_axis_aligned_timber(
        bottom_position=create_v3(-cross_length / 2, cross_y_front, scalar(0)),
        length=cross_length,
        size=timber_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Front Cross",
    )

    # A short brace butted rigidly onto the outside of the right side; it rides
    # along when the right side is extracted, then pulls off at order 3.
    brace = create_axis_aligned_timber(
        bottom_position=create_v3(side_spacing / 2, scalar(0), scalar(0)),
        length=brace_length,
        size=timber_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Brace",
    )

    peg_params = SimplePegParameters(
        shape=PegShape.ROUND,
        peg_positions=[(tenon_length / 2, scalar(0))],
        size=peg_diameter,
        depth=None,
        tenon_hole_offset=peg_draw_bore_offset,
    )

    def mortise_into_side(cross, cross_end, side):
        return cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=side,
                butt_timber=cross,
                butt_timber_end=cross_end,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
            tenon_size=tenon_size,
            tenon_length=tenon_length,
            mortise_depth=mortise_depth,
            peg_parameters=peg_params,
        )

    joints = [
        mortise_into_side(back_cross, TimberEnd.TOP, right_side).with_order(1),
        mortise_into_side(front_cross, TimberEnd.TOP, right_side).with_order(1),
        mortise_into_side(front_cross, TimberEnd.BOTTOM, left_side).with_order(2),
        cut_plain_butt_joint_on_face_aligned_timbers(
            arrangement=ButtJointTimberArrangement(
                receiving_timber=right_side,
                butt_timber=brace,
                butt_timber_end=TimberEnd.BOTTOM,
                front_face_on_butt_timber=TimberLongFace.FRONT,
            ),
        ).with_order(3),
        mortise_into_side(back_cross, TimberEnd.BOTTOM, left_side).with_order(4),
    ]
    return Frame.from_joints(joints, name="Assembly Preview Demo")


example = build_frame
