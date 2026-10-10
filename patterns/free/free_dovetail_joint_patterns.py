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
                         orientation=Orientation.from_x_and_y(create_v3(0, 1, 0), create_v3(0, 0, -1))),
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


# --- Sawhorse: four splayed 1x6 legs, each in a tapered, angled sliding dovetail ---------------------------

BEAM_SIZE = inches(7, 2)          # a 4x4, actual 3.5" x 3.5"
BEAM_LENGTH = inches(36)
LEG_SIZE = create_v2(inches(11, 2), inches(3, 4))  # a 1x6, actual 5.5" x 0.75"
LEG_LENGTH = inches(30)
LEG_INSET = inches(6)             # each leg's top, centred this far in from its end of the beam
LEG_SPLAY = degrees(10)           # outward from the beam, and along it toward its end
DOVETAIL_TILT = degrees(18)       # the dovetail's slide axis, outward from vertical
DOVETAIL_TAPER = degrees(10)      # narrowing toward the top: point end up
DOVETAIL_FLARE = atan(scalar(1) / scalar(6))
DOVETAIL_WIDTH = inches(3, 2)     # at the top
DOVETAIL_DEPTH = inches(1, 2)     # into the beam


def _sawhorse_leg(beam, end, side, position):
    """One leg, let into the beam's side by its thickness, and its dovetail.

    `end` is +1/-1 for the beam's +x/-x end, `side` +1/-1 for its +y/-y side. The leg's outer face
    lies on the beam's top arris on its side, and its top is trimmed level with the beam's top.
    """
    up = safe_normalize_vector(create_v3(-end * tan(LEG_SPLAY), -side * tan(LEG_SPLAY), 1))
    along_beam = create_v3(1, 0, 0)
    width = safe_normalize_vector(along_beam - up * safe_dot_product(along_beam, up))
    outward = safe_normalize_vector(cross_product(width, up))
    if safe_compare(outward[1] * side, 0, Comparison.LT):
        outward = -outward

    # Where the leg's centre meets the beam's top arris on its side.
    arris = position + create_v3(end * (BEAM_LENGTH / 2 - LEG_INSET), side * BEAM_SIZE / 2, BEAM_SIZE)
    # The leg's centreline at the top, half its thickness in from the outer face, and an inch past the
    # top so the level trim has something to take off.
    top = arris - outward * (LEG_SIZE[1] / 2) + up * inches(1)
    leg = create_timber(bottom_position=top - up * (LEG_LENGTH + inches(1)), length=LEG_LENGTH + inches(1),
                        size=LEG_SIZE, length_direction=up, width_direction=width,
                        ticket=f"leg {'+x' if end > 0 else '-x'} {'+y' if side > 0 else '-y'}")

    # The dovetail: its width square to the beam, sliding up an axis tilted outward from vertical,
    # its +y into the beam. The tongue is cut from the leg's thickness, so the leg must stay behind
    # the neck (-y) all the way down. The axis leans more than the leg does, so the neck starts on
    # the leg's outer face at the beam's bottom and runs inward as it rises: the tongue gets
    # shallower toward the top as well as narrower.
    slide = create_v3(0, -side * sin(DOVETAIL_TILT), cos(DOVETAIL_TILT))
    across = create_v3(-side, 0, 0)
    length = BEAM_SIZE / cos(DOVETAIL_TILT)
    at_bottom = arris + create_v3(0, BEAM_SIZE * outward[2] / outward[1], -BEAM_SIZE)
    dovetail = FreeDovetailShape(
        origin=Transform(position=at_bottom + slide * length, orientation=Orientation.from_z_and_x(slide, across)),
        width=DOVETAIL_WIDTH, depth=DOVETAIL_DEPTH, dovetail_angle=DOVETAIL_FLARE,
        forward_length=scalar(0), backward_length=length, taper_angle=DOVETAIL_TAPER,
    )
    joint = cut_free_dovetail_joint(leg, beam, dovetail)
    level_top = adopt_csg(None, leg.transform, HalfSpace(
        normal=create_v3(0, 0, 1), offset=safe_dot_product(create_v3(0, 0, 1), arris), label=CutCSGLabel("level_top")))
    cut_leg = CutTimber(leg, cuts=[joint.cuttings["dovetail_timber"],
                                   Cutting(timber=leg, negative_csg=level_top, label=CutCSGLabel("level_top"))])
    return cut_leg, joint.cuttings["receiving_timber"]


@pattern("free_joints/free_dovetail_joint/angled_tapered", tags=["main"])
def example_sawhorse_angled_tapered_dovetails(position=None) -> Frame:
    """A 4x4 sawhorse beam with four 1x6 legs splayed 10 degrees both ways, each let in by its
    thickness and held by a dovetail tapered 10 degrees (point up) and tilted 18 degrees outward."""
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
