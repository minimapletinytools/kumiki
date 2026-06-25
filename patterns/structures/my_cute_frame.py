"""Starter Kigumi frame: a simple H-shaped frame made of four 90x90mm timbers.

Two side timbers run in the +Y direction. Two cross timbers join them with
mortise-and-tenon joints (with 15mm draw-bore pegs), inset from the ends so
the mortises sit safely away from the timber ends.
"""

from kumiki import *


# --- Dimensions -------------------------------------------------------------

timber_size = Matrix([mm(90), mm(90)])  # 90x90mm cross section

side_length = mm(600)            # length of each side timber (along Y)
side_spacing = mm(500)           # center-to-center spacing of side timbers (along X)
end_inset = mm(100)              # cross-timber inset from the side-timber ends

# Tenon cross-section is (width_axis, height_axis) in the cross-timber local frame.
# Cross timbers run in +X with width_direction=FRONT, so local height axis = global Z.
# 80mm in global Y, 40mm in global Z (the shorter dimension).
tenon_size = Matrix([mm(80), mm(40)])
tenon_length = mm(75)
mortise_depth = tenon_length + mm(6)

# 15mm round draw-bore peg, slightly offset so the joint draws tight.
peg_diameter = mm(15)
peg_draw_bore_offset = mm(2)


def build_frame() -> Frame:
    # Side timbers run in +Y, at x = +/- side_spacing/2.
    left_side = create_axis_aligned_timber(
        bottom_position=create_v3(-side_spacing / 2, -side_length / 2, Rational(0)),
        length=side_length,
        size=timber_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket="Left Side",
    )
    right_side = create_axis_aligned_timber(
        bottom_position=create_v3(side_spacing / 2, -side_length / 2, Rational(0)),
        length=side_length,
        size=timber_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket="Right Side",
    )

    # Cross timbers run in +X, inset from the ends of the side timbers.
    # Their length spans center-to-center so the tenons land inside the sides.
    cross_length = side_spacing
    cross_y_front = side_length / 2 - end_inset
    cross_y_back = -cross_y_front

    back_cross = create_axis_aligned_timber(
        bottom_position=create_v3(-cross_length / 2, cross_y_back, Rational(0)),
        length=cross_length,
        size=timber_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Back Cross",
    )
    front_cross = create_axis_aligned_timber(
        bottom_position=create_v3(-cross_length / 2, cross_y_front, Rational(0)),
        length=cross_length,
        size=timber_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket="Front Cross",
    )

    # Round draw-bore peg, one per joint, centered on the tenon.
    # Peg axis is perpendicular to the cross timber's FRONT face (i.e. through
    # the side timber from the front, in global +Y on the back cross and -Y on the front cross).
    peg_params = SimplePegParameters(
        shape=PegShape.ROUND,
        peg_positions=[(tenon_length / 2, Rational(0))],
        size=peg_diameter,
        depth=None,                                # through peg
        tenon_hole_offset=peg_draw_bore_offset,    # draw-bore offset pulls the joint tight
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
        mortise_into_side(back_cross, TimberReferenceEnd.BOTTOM, left_side),
        mortise_into_side(back_cross, TimberReferenceEnd.TOP, right_side),
        mortise_into_side(front_cross, TimberReferenceEnd.BOTTOM, left_side),
        mortise_into_side(front_cross, TimberReferenceEnd.TOP, right_side),
    ]

    return Frame.from_joints(joints, name="My Cute Frame")


example = build_frame
