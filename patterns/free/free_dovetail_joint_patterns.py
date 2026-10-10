"""
Free Dovetail Joint Patterns

A post standing on a beam, held by a sliding dovetail across the post's width: the beam
gets the socket, the post the tongue.
"""

from kumiki import *


def _post_on_beam_with_dovetail(position, taper_angle):
    if position is None:
        position = create_v3(0, 0, 0)
    # The beam runs along x with its top face at z=50mm; the post stands on it from z=0.
    beam = create_timber(bottom_position=position + create_v3(mm(-500), 0, 0), length=mm(1000),
                         size=create_v2(mm(100), mm(100)), length_direction=create_v3(1, 0, 0),
                         width_direction=create_v3(0, 1, 0), ticket="beam")
    post = create_timber(bottom_position=position, length=mm(600), size=create_v2(mm(100), mm(100)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="post")
    # Slides along x, across the post's width. The neck is 40mm wide at the beam's top face and the
    # tongue flares at 15 degrees down into the beam for 30mm, so the post cannot lift out.
    dovetail = FreeDovetailShape(
        origin=Transform(position=position + create_v3(0, 0, mm(50)),
                         orientation=Orientation.from_x_and_y(create_v3(1, 0, 0), create_v3(0, 0, -1))),
        width=mm(40), depth=mm(30), dovetail_angle=degrees(15),
        forward_length=mm(50), backward_length=mm(50), taper_angle=taper_angle,
    )
    return cut_free_dovetail_joint(post, beam, dovetail)


@pattern("free_joints/free_dovetail_joint/sliding", tags=["main"])
def example_free_sliding_dovetail(position=None) -> Joint:
    """A straight sliding dovetail."""
    return _post_on_beam_with_dovetail(position, scalar(0))


@pattern("free_joints/free_dovetail_joint/tapered")
def example_free_tapered_dovetail(position=None) -> Joint:
    """The same, tapering toward its forward end, so it tightens as it slides home."""
    return _post_on_beam_with_dovetail(position, degrees(5))


# --- Sawhorse: four splayed 1x6 legs, each a tapered sliding dovetail let into the beam's arris ---------------

BEAM_SIZE = inches(7, 2)          # a 4x4, actual 3.5" x 3.5"
BEAM_LENGTH = inches(36)
LEG_SIZE = create_v2(inches(11, 2), inches(3, 4))  # a 1x6, actual 5.5" x 0.75"
LEG_LENGTH = inches(30)
LEG_INSET = inches(6)             # each leg's top, centred this far in from its end of the beam
LEG_SPLAY = degrees(10)           # along the beam, toward its end
DOVETAIL_TAPER = degrees(10)      # narrowing toward the top: point end up
DOVETAIL_FLARE = atan(scalar(1) / scalar(6))


def _sawhorse_leg(beam, end, side, position):
    """One leg and its dovetail.

    `end` is +1/-1 for the beam's +x/-x end, `side` +1/-1 for its +y/-y side. Seen along the beam,
    the leg leans out just so its outer face runs through the beam's top arris and its inner face
    through the bottom one. The dovetail is the leg's whole thickness between those faces.
    """
    # Seen along the beam, the faces through both arrises are a thickness apart: sin = thickness / height.
    lean_sin = LEG_SIZE[1] / BEAM_SIZE
    lean_cos = sqrt(1 - lean_sin * lean_sin)
    up = safe_normalize_vector(create_v3(-end * tan(LEG_SPLAY), -side * lean_sin / lean_cos, 1))
    outward = create_v3(0, side * lean_cos, lean_sin)  # the leg's face normal, square to the beam
    along_beam = create_v3(1, 0, 0)
    width = safe_normalize_vector(along_beam - up * safe_dot_product(along_beam, up))


    # TODO replace side * BEAM_SIZE / 2 + mm(1) with proper trig
    # Where the leg's centre crosses the beam's top arris on its side.
    arris = position + create_v3(end * (BEAM_LENGTH / 2 - LEG_INSET), side * BEAM_SIZE / 2 + side*mm(1), BEAM_SIZE)
    # The leg's centreline at the top, half its thickness in from the outer face, and an inch past the
    # top so the level trim has something to take off.
    top = arris - outward * (LEG_SIZE[1] / 2) + up * inches(1)
    leg = create_timber(bottom_position=top - up * (LEG_LENGTH + inches(1)), length=LEG_LENGTH + inches(1),
                        size=LEG_SIZE, length_direction=up, width_direction=width,
                        ticket=f"leg {'+x' if end > 0 else '-x'} {'+y' if side > 0 else '-y'}")

    # The dovetail: its width square to the beam, its neck on the leg's outer face with its top edge
    # on the top arris, its wide face on the leg's inner face. It runs down to the bottom arris.
    across, into_beam = create_v3(-side, 0, 0), -outward
    slide = cross_product(across, into_beam)
    length = BEAM_SIZE * lean_cos
    # There the neck is exactly as wide as the leg is along the beam, and centred on it.
    at_bottom = arris + up * (-length / safe_dot_product(slide, up))
    width_at_bottom = LEG_SIZE[0] / sqrt(1 - up[0] * up[0])
    dovetail = FreeDovetailShape(
        origin=Transform(position=create_v3(at_bottom[0], arris[1], arris[2]),
                         orientation=Orientation.from_x_and_y(across, into_beam)),
        width=width_at_bottom - cos(DOVETAIL_TAPER)*LEG_SIZE[1] - 2 * length * tan(DOVETAIL_TAPER), depth=LEG_SIZE[1],
        dovetail_angle=DOVETAIL_FLARE,
        # Up past the beam's top for good -- above it is only the leg, trimmed level. The taper
        # needs finite ends, so "for good" is the beam's height.
        forward_length=BEAM_SIZE, backward_length=LEG_LENGTH, taper_angle=DOVETAIL_TAPER,
    )
    joint = cut_free_dovetail_joint(leg, beam, dovetail)
    level_top = adopt_csg(None, leg.transform, HalfSpace(
        normal=create_v3(0, 0, 1), offset=safe_dot_product(create_v3(0, 0, 1), arris), label=CutCSGLabel("level_top")))
    cut_leg = CutTimber(leg, cuts=[joint.cuttings["dovetail_timber"],
                                   Cutting(timber=leg, negative_csg=level_top, label=CutCSGLabel("level_top"))])
    return cut_leg, joint.cuttings["receiving_timber"]


@pattern("free_joints/free_dovetail_joint/angled_tapered", tags=["main"])
def example_sawhorse_angled_tapered_dovetails(position=None) -> Frame:
    """A 4x4 sawhorse beam with four 1x6 legs splayed both ways, each let into the beam's arris
    as a sliding dovetail tapered 10 degrees, point up."""
    if position is None:
        position = create_v3(0, 0, 0)
    beam = create_timber(bottom_position=position + create_v3(-BEAM_LENGTH / 2, 0, BEAM_SIZE / 2),
                         length=BEAM_LENGTH, size=create_v2(BEAM_SIZE, BEAM_SIZE),
                         length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 1, 0), ticket="beam")
    legs, sockets = [], []
    for end in (1, -1):
        for side in (1, -1):
            leg, socket = _sawhorse_leg(beam, end, side, position)
            legs.append(leg)
            sockets.append(socket)
    # Each leg is let in by its thickness: the beam is housed to the leg's finished shape.
    housing = cut_free_house_joint(beam, legs).cuttings["housing_timber"]
    return Frame(cut_timbers=[CutTimber(beam, cuts=[*sockets, housing]), *legs],
                 name="Sawhorse with angled tapered dovetails")
