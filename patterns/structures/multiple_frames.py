"""Multiple frames in one file: a little yard of four structures.

Each `@frame` below builds one structure, and Kigumi shows them all together,
each where it was built. Each returns its kiwari on its Frame. The three models
are all resolved from MODELS, so they share one set of parameters; the pavilion
has PAVILION to itself. The parameters panel shows one section for each.

Three are supporting "models" -- neighbours that only need to look about right
(see `Creating supporting "Models"` in docs/agent_usage_instructions.md): one
massive vertical timber filling the footprint, slanted boards for a roof, a
plain butt joint trimming the body to each board, and doors and windows recessed
into the walls.

The fourth is an actual timber frame: four posts and a ring of beams, joined
with pegged mortise and tenons.

    cottage (0, +y)      tower (+x, +y)

    pavilion (0, 0)      shed (+x, 0)

Measured from the pavilion, so changing the spacing moves only the models.
"""

from dataclasses import replace

from kumiki import *


MODELS = kiwari(
    spacing=kiwari.length(m(7), minimum=m(5), about="Centre to centre distance between neighbouring structures"),
    height=kiwari.length(m(2.4), minimum=m(1.5), about="The cottage's wall height; the others are in proportion"),
)
PAVILION = kiwari(
    post_size=kiwari.point2(create_v2(mm(150), mm(150)), about="The posts' cross section"),
    beam_size=kiwari.point2(create_v2(mm(100), mm(150)), about="The beams' cross section, width by height"),
)

# The height every model is drawn at when MODELS's height is left alone.
_MODEL_HEIGHT = m(2.4)

roof_board_thickness = mm(100)
opening_recess = mm(150)

# Roof pitches as (run, rise, slope) triples, so the slope length is exact.
gentle_pitch = (scalar(12), scalar(5), scalar(13))
regular_pitch = (scalar(4), scalar(3), scalar(5))
steep_pitch = (scalar(3), scalar(4), scalar(5))


def _rectangle(center_x: Numeric, center_y: Numeric, width: Numeric, depth: Numeric) -> Footprint:
    """A rectangular footprint, counter-clockwise from its back left (-x, -y) corner."""
    left, right = center_x - width / 2, center_x + width / 2
    back, front = center_y - depth / 2, center_y + depth / 2
    return Footprint([
        create_v2(left, back), create_v2(right, back),
        create_v2(right, front), create_v2(left, front),
    ])


def _roof_board(eave_x: Numeric, eave_z: Numeric, center_y: Numeric, run: Numeric, pitch,
                ridge_length: Numeric, rises_towards: TimberFace, ticket: str) -> Timber:
    """A board with its underside on the roof plane, climbing `run` from the eave."""
    run_part, rise_part, slope_part = pitch
    sign = scalar(1) if rises_towards == TimberFace.RIGHT else scalar(-1)
    up_the_slope = create_v3(sign * run_part / slope_part, scalar(0), rise_part / slope_part)
    # Chosen so the board's own +Y (its thickness) faces the sky on either side.
    along_the_ridge = create_v3(scalar(0), sign, scalar(0))
    outward = create_v3(-sign * rise_part / slope_part, scalar(0), run_part / slope_part)
    return create_timber(
        length=run * slope_part / run_part,
        size=Matrix([ridge_length, roof_board_thickness]),
        bottom_position=create_v3(eave_x, center_y, eave_z) + outward * roof_board_thickness / 2,
        length_direction=up_the_slope,
        width_direction=along_the_ridge,
        ticket=ticket,
    )


def _opening(wall: TimberFace, along: Numeric, sill: Numeric, width: Numeric, height: Numeric):
    """A door or window: which wall, how far along it from its middle (towards +x
    or +y), how high its bottom edge is, and its size."""
    return (wall, along, sill, width, height)


def _door(wall: TimberFace, along: Numeric, width: Numeric = mm(900), height: Numeric = m(2)):
    return _opening(wall, along, scalar(0), width, height)


def _taller(openings, scale: Numeric):
    """The openings with their heights and sills scaled with the building."""
    return [(wall, along, sill * scale, width, height * scale) for wall, along, sill, width, height in openings]


def _opening_block(opening, center_x: Numeric, center_y: Numeric, width: Numeric, depth: Numeric) -> Timber:
    """The block an opening is cut with, straddling its wall by the recess depth."""
    wall, along, sill, opening_width, opening_height = opening
    outward = wall.get_direction()
    if wall in (TimberFace.LEFT, TimberFace.RIGHT):
        on_the_wall = create_v3(center_x, center_y + along, scalar(0)) + outward * width / 2
        across = TimberFace.FRONT
    else:
        on_the_wall = create_v3(center_x + along, center_y, scalar(0)) + outward * depth / 2
        across = TimberFace.RIGHT
    middle = on_the_wall + create_v3(scalar(0), scalar(0), sill + opening_height / 2)
    return create_axis_aligned_timber(
        bottom_position=middle - outward * opening_recess,
        length=opening_recess * 2,
        size=Matrix([opening_width, opening_height]),
        length_direction=wall,
        width_direction=across,
    )


def _model_building(name: str, center_x: Numeric, center_y: Numeric, width: Numeric, depth: Numeric,
                    wall_height: Numeric, pitch, overhang: Numeric, gabled: bool = True,
                    openings=()) -> Frame:
    """A supporting model: a solid body under a gable roof, or a single-pitch one.

    The roof plane passes through the top of the left wall (and of the right
    one, when gabled), and the body is trimmed to it with plain butt joints.
    """
    run_part, rise_part, _ = pitch
    footprint = _rectangle(center_x, center_y, width, depth)
    left_wall_x, right_wall_x = center_x - width / 2, center_x + width / 2
    ridge_length = depth + overhang * 2
    eave_z = wall_height - overhang * rise_part / run_part

    if gabled:
        run = width / 2 + overhang
        peak_z = wall_height + (width / 2) * rise_part / run_part
        boards = [
            _roof_board(left_wall_x - overhang, eave_z, center_y, run, pitch, ridge_length,
                        TimberFace.RIGHT, f"{name} Left Roof"),
            _roof_board(right_wall_x + overhang, eave_z, center_y, run, pitch, ridge_length,
                        TimberFace.LEFT, f"{name} Right Roof"),
        ]
    else:
        run = width + overhang * 2
        peak_z = wall_height + width * rise_part / run_part
        boards = [
            _roof_board(left_wall_x - overhang, eave_z, center_y, run, pitch, ridge_length,
                        TimberFace.RIGHT, f"{name} Roof"),
        ]

    body = create_axis_aligned_timber(
        bottom_position=create_v3(center_x, center_y, scalar(0)),
        length=peak_z,
        size=Matrix([width, depth]),
        length_direction=TimberFace.TOP,
        width_direction=TimberFace.RIGHT,
        ticket=f"{name} Body",
    )

    joints = [
        cut_basic_plain_butt_joint(ButtJointTimberArrangement(
            butt_timber=body, receiving_timber=board, butt_timber_end=TimberEnd.TOP))
        for board in boards
    ]
    if openings:
        # A free house joint cuts the body to fit each block; keeping only the
        # body's side of it leaves the recess and no block.
        housed = cut_free_house_joint(
            body, [_opening_block(opening, center_x, center_y, width, depth) for opening in openings])
        joints.append(replace(housed, cuttings={"housing_timber": housed.cuttings["housing_timber"]}))
    return replace(Frame.from_joints(joints, name=name), footprints=[footprint])


@frame
def cottage(k: Optional[Kiwari] = None) -> Frame:
    k = MODELS.resolve(k)
    scale = k.length("height") / _MODEL_HEIGHT
    frame = _model_building("Cottage", scalar(0), k.length("spacing"), width=m(4), depth=m(5),
                            wall_height=m(2.4) * scale, pitch=regular_pitch, overhang=mm(400), openings=_taller([
                               _door(TimberFace.BACK, mm(-900)),
                               _opening(TimberFace.BACK, mm(900), mm(900), m(1), m(1)),
                               _opening(TimberFace.BACK, scalar(0), m(2.7), mm(600), mm(600)),
                               _opening(TimberFace.RIGHT, m(-1.2), mm(900), m(1), m(1)),
                               _opening(TimberFace.RIGHT, m(1.2), mm(900), m(1), m(1)),
                               _opening(TimberFace.LEFT, mm(400), mm(1100), m(1.6), mm(700)),
                           ], scale))
    return replace(frame, kiwari=k)


@frame
def tower(k: Optional[Kiwari] = None) -> Frame:
    k = MODELS.resolve(k)
    scale = k.length("height") / _MODEL_HEIGHT
    spacing = k.length("spacing")
    frame = _model_building("Tower", spacing, spacing, width=m(2.5), depth=m(2.5),
                            wall_height=m(5) * scale, pitch=steep_pitch, overhang=mm(300), openings=_taller([
                               _door(TimberFace.LEFT, scalar(0), width=mm(800)),
                               _opening(TimberFace.LEFT, scalar(0), m(3.4), mm(600), mm(900)),
                               _opening(TimberFace.BACK, scalar(0), m(3.4), mm(600), mm(900)),
                               _opening(TimberFace.BACK, scalar(0), m(5.3), mm(500), mm(500)),
                               _opening(TimberFace.RIGHT, mm(-400), m(1.4), mm(600), mm(900)),
                               _opening(TimberFace.RIGHT, mm(400), m(3.4), mm(600), mm(900)),
                           ], scale))
    return replace(frame, kiwari=k)


@frame
def shed(k: Optional[Kiwari] = None) -> Frame:
    k = MODELS.resolve(k)
    scale = k.length("height") / _MODEL_HEIGHT
    frame = _model_building("Shed", k.length("spacing"), scalar(0), width=m(3), depth=m(2),
                            wall_height=m(1.8) * scale, pitch=gentle_pitch, overhang=mm(250), gabled=False,
                            openings=_taller([
                               _door(TimberFace.BACK, mm(700)),
                               _opening(TimberFace.BACK, mm(-800), mm(800), mm(700), mm(700)),
                               _opening(TimberFace.RIGHT, scalar(0), m(1.2), mm(800), m(1)),
                           ], scale))
    return replace(frame, kiwari=k)


@frame
def pavilion(k: Optional[Kiwari] = None) -> Frame:
    """The one real timber frame: four posts and a ring of pegged beams."""
    k = PAVILION.resolve(k)
    post_size = k.v2("post_size")
    beam_size = k.v2("beam_size")
    post_height = m(2.4)
    # The two pairs sit at different heights so their tenons pass each other in the post.
    side_beam_height = m(2.2)
    cross_beam_height = m(1.95)

    footprint = _rectangle(scalar(0), scalar(0), m(3), m(3))
    back_left, back_right, front_right, front_left = [
        create_vertical_timber_on_footprint_corner(
            footprint, corner, post_height, FootprintLocation.INSIDE, post_size,
            ticket=f"{label} Post")
        for corner, label in enumerate(["Back Left", "Back Right", "Front Right", "Front Left"])
    ]

    def beam(from_post: Timber, to_post: Timber, height: Numeric, ticket: str) -> Timber:
        return join_timbers(from_post, to_post, location_on_timber1=height, size=beam_size,
                            orientation_width_vector=create_v3(scalar(0), scalar(0), scalar(1)),
                            ticket=ticket)

    beams = [
        (beam(back_left, front_left, side_beam_height, "Left Beam"), back_left, front_left),
        (beam(back_right, front_right, side_beam_height, "Right Beam"), back_right, front_right),
        (beam(back_left, back_right, cross_beam_height, "Back Beam"), back_left, back_right),
        (beam(front_left, front_right, cross_beam_height, "Front Beam"), front_left, front_right),
    ]

    joints = []
    for spanning, bottom_post, top_post in beams:
        joints.append(cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
            spanning, bottom_post, TimberEnd.BOTTOM, use_peg=True))
        joints.append(cut_basic_mortise_and_tenon_joint_on_face_aligned_timbers(
            spanning, top_post, TimberEnd.TOP, use_peg=True))

    return replace(Frame.from_joints(joints, name="Pavilion", kiwari=k), footprints=[footprint])
