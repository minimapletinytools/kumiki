# Last checked on kumiki 0.9.0
"""Purpose
-------
Start with a small four-member frame to learn the arrange, cut, and assemble workflow.

Concepts demonstrated — overview
-------------------------------
Simple example; small structure; face-aligned, axis-oriented construction.

Concepts demonstrated — details
------------------------------
Two side members and two cross members use pegged mortise-and-tenon joints. Reference features
identify the edges used for measurements. Dimensions are source constants; there are no Kiwari
controls. Three drawings (a plan, a side and a cross) place their dimensions by hand.
Recipe notes
------------
Starter Kigumi frame: a simple H-shaped frame made of four 90x90mm timbers.

Two side timbers run in the +Y direction. Two cross timbers join them with
mortise-and-tenon joints (with 15mm draw-bore pegs), inset from the ends so
the mortises sit safely away from the timber ends.
"""

__title__ = {"en": "My cute frame", "ja": "かわいい架構"}

from dataclasses import replace

from kumiki import *


# --- Dimensions -------------------------------------------------------------

timber_size = Matrix([mm(90), mm(90)])  # 90x90mm cross section

side_length = mm(600)            # length of each side timber (along Y)
side_spacing = mm(500)           # center-to-center spacing of side timbers (along X)
end_inset = mm(100)              # cross-timber inset from the side-timber ends

# Tenon dimensions relative to joint plane (shared XY plane):
# 80mm wide parallel to joint plane (along Y), 40mm tall perpendicular to joint plane (along Z).
tenon_width_relative_to_joint = mm(80)
tenon_height_relative_to_joint = mm(40)
tenon_length = mm(75)
mortise_depth = tenon_length + mm(6)

# 15mm round draw-bore peg, slightly offset so the joint draws tight.
peg_diameter = mm(15)
peg_draw_bore_offset = mm(2)


@frame
def my_cute_frame(k: Optional[Kiwari] = None) -> Frame:
    # Side timbers run in +Y, at x = +/- side_spacing/2.
    # Each timber is measured from its bottom outside edge, its reference feature.
    left_side = create_axis_aligned_timber(
        bottom_position=create_v3(-side_spacing / 2, -side_length / 2, scalar(0)),
        length=side_length,
        size=timber_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket=TimberTicket(path="Left Side", reference_features=(TimberFeature.FRONT_LEFT_EDGE,)),
    )
    right_side = create_axis_aligned_timber(
        bottom_position=create_v3(side_spacing / 2, -side_length / 2, scalar(0)),
        length=side_length,
        size=timber_size,
        length_direction=TimberFace.FRONT,
        width_direction=TimberFace.RIGHT,
        ticket=TimberTicket(path="Right Side", reference_features=(TimberFeature.RIGHT_FRONT_EDGE,)),
    )

    # Cross timbers run in +X, inset from the ends of the side timbers.
    # Their length spans center-to-center so the tenons land inside the sides.
    cross_length = side_spacing
    cross_y_front = side_length / 2 - end_inset
    cross_y_back = -cross_y_front

    back_cross = create_axis_aligned_timber(
        bottom_position=create_v3(-cross_length / 2, cross_y_back, scalar(0)),
        length=cross_length,
        size=timber_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket=TimberTicket(path="Back Cross", reference_features=(TimberFeature.LEFT_BACK_EDGE,)),
    )
    front_cross = create_axis_aligned_timber(
        bottom_position=create_v3(-cross_length / 2, cross_y_front, scalar(0)),
        length=cross_length,
        size=timber_size,
        length_direction=TimberFace.RIGHT,
        width_direction=TimberFace.FRONT,
        ticket=TimberTicket(path="Front Cross", reference_features=(TimberFeature.BACK_RIGHT_EDGE,)),
    )

    # Round draw-bore peg, one per joint, centered on the tenon.
    # Peg axis is perpendicular to the cross timber's FRONT face (i.e. through
    # the side timber from the front, in global +Y on the back cross and -Y on the front cross).
    peg_params = SimplePegParameters(
        shape=PegShape.ROUND,
        peg_positions=[(tenon_length / 2, scalar(0))],
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
            tenon_width_relative_to_joint=tenon_width_relative_to_joint,
            tenon_height_relative_to_joint=tenon_height_relative_to_joint,
            tenon_length=tenon_length,
            mortise_depth=mortise_depth,
            peg_parameters=peg_params,
        )

    back_left = mortise_into_side(back_cross, TimberEnd.BOTTOM, left_side)
    back_right = mortise_into_side(back_cross, TimberEnd.TOP, right_side)
    front_left = mortise_into_side(front_cross, TimberEnd.BOTTOM, left_side)
    front_right = mortise_into_side(front_cross, TimberEnd.TOP, right_side)
    frame = Frame.from_joints([back_left, back_right, front_left, front_right], name="My Cute Frame")

    return replace(frame, drawings=[
        plan_drawing(frame, left_side, right_side, back_cross, front_cross),
        side_drawing(frame, left_side, back_left, front_left),
        cross_drawing(frame, back_cross, back_left, back_right),
    ])


# --- Drawings ---------------------------------------------------------------
# Each dimension is placed by hand: Beside(side, lane) puts it on that side of the
# work, lane 1 nearest. Features come from the timbers (face) and joints (feature).

MT = MortiseAndTenonFeatures


def plan_drawing(frame, left_side, right_side, back_cross, front_cross):
    """The frame seen from above: its overall size and where the cross timbers sit."""
    left, right = frame.cut_timber_of(left_side), frame.cut_timber_of(right_side)
    back, front = frame.cut_timber_of(back_cross), frame.cut_timber_of(front_cross)
    above = Viewport(label="Plan", camera=View.world("top", scale=1 / 3), measurements=[
        Measure(left.face(TimberFace.LEFT), right.face(TimberFace.RIGHT), placement=Beside(DimensionSide.ABOVE)),
        Measure(left.face(TimberFace.RIGHT), right.face(TimberFace.LEFT), placement=Beside(DimensionSide.BELOW)),
        Measure(left.face(TimberFace.BOTTOM), left.face(TimberFace.TOP), placement=Beside(DimensionSide.LEFT, 2)),
        Measure(left.face(TimberFace.BOTTOM), back.face(TimberFace.LEFT), placement=Beside(DimensionSide.LEFT)),
        Measure(back.face(TimberFace.RIGHT), front.face(TimberFace.LEFT), placement=Beside(DimensionSide.LEFT)),
    ])
    return Drawing(name="Plan", timbers=[cut.timber for cut in (left, right, back, front)],
                   viewports=[covering_page(columns(above.taking(Share(2)), Viewport(label="Preview")))])


def side_drawing(frame, side, back_joint, front_joint):
    """A side timber: where its two mortises and peg holes are, from its bottom end."""
    cut = frame.cut_timber_of(side)
    end = cut.face(TimberFace.BOTTOM)
    inside = Viewport(label="Inside face", camera=View.of_face(side, TimberFace.RIGHT, scale=1 / 3), measurements=[
        Measure(end, back_joint.feature(MT.MORTISE_LEFT), placement=Beside(DimensionSide.BELOW)),
        Measure(back_joint.feature(MT.MORTISE_LEFT), back_joint.feature(MT.MORTISE_RIGHT),
                placement=Beside(DimensionSide.BELOW)),
        Measure(end, front_joint.feature(MT.MORTISE_LEFT), placement=Beside(DimensionSide.BELOW, 2)),
        Measure(back_joint.feature(MT.MORTISE_FRONT), back_joint.feature(MT.MORTISE_BACK),
                placement=Beside(DimensionSide.LEFT)),
        # The mortise is centred: half its height either side of the timber's centerplane.
        Measure(cut.feature("ptw.centerplane_front_back"), front_joint.feature(MT.MORTISE_FRONT),
                placement=Beside(DimensionSide.RIGHT)),
    ])
    top = Viewport(label="Top face", camera=View.of_face(side, TimberFace.BACK, scale=1 / 3), measurements=[
        Measure(end, back_joint.feature(MT.PEG_HOLE_AXIS, on=side), placement=Beside(DimensionSide.ABOVE)),
        Measure(end, front_joint.feature(MT.PEG_HOLE_AXIS, on=side), placement=Beside(DimensionSide.ABOVE, 2)),
    ])
    return Drawing(name=f"{side.ticket.path} ×2", timbers=[side],
                   viewports=[covering_page(columns(rows(inside, top).taking(Share(2)), Viewport(label="Preview")))])


def cross_drawing(frame, cross, start_joint, end_joint):
    """A cross timber: its length between shoulders, and each tenon and its peg hole."""
    top = Viewport(label="Top face", camera=View.of_face(cross, TimberFace.FRONT, scale=1 / 3), measurements=[
        Measure(start_joint.feature(MT.SHOULDER), end_joint.feature(MT.SHOULDER), placement=Beside(DimensionSide.ABOVE)),
        Measure(start_joint.feature(MT.SHOULDER), start_joint.feature(MT.TENON_BOTTOM), placement=Beside(DimensionSide.BELOW)),
        Measure(start_joint.feature(MT.PEG_HOLE_AXIS, on=cross), start_joint.feature(MT.SHOULDER), placement=Beside(DimensionSide.ABOVE)),
        Measure(start_joint.feature(MT.TENON_RIGHT), start_joint.feature(MT.TENON_LEFT), placement=Beside(DimensionSide.LEFT)),
    ])
    side = Viewport(label="Side face", camera=View.of_face(cross, TimberFace.RIGHT, scale=1 / 3), measurements=[
        Measure(start_joint.feature(MT.TENON_FRONT), start_joint.feature(MT.TENON_BACK), placement=Beside(DimensionSide.LEFT)),
    ])
    return Drawing(name=f"{cross.ticket.path} ×2", timbers=[cross],
                   viewports=[covering_page(columns(rows(top, side).taking(Share(2)), Viewport(label="Preview")))])
