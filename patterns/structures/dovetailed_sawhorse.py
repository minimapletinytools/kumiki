"""Dovetailed sawhorse: a beam on edge and four splayed 1x6 legs.

Each leg is let into an arris of the beam by its whole thickness, as a sliding dovetail tapered
point up, so the load wedges it tighter. Seen along the beam, a leg's outer face runs through the
beam's top arris; unless its side splay is given, it leans just so its inner face runs through the
bottom arris. The floor is at z=0.
"""

from kumiki import *


SAWHORSE = kiwari(
    leg_distance=kiwari.length(inches(25), about="Centre to centre along the beam, where the legs meet its top"),
    leg_y_splay_angle=kiwari.angle(degrees(12), about="How far the legs lean out toward the beam's ends"),
    leg_side_splay_angle=kiwari.angle(
        optional=True, about="How far the legs splay out from the beam's sides; based on beam and leg dimensions if disabled"),
    beam_size=kiwari.point2(create_v2(inches(2), inches(9, 2)), about="Across and tall"),
    leg_size=kiwari.point2(create_v2(inches(11, 2), inches(3, 4)), about="Width and thickness"),
    sawhorse_height=kiwari.length(inches(30), about="Floor to the top of the beam"),
    sawhorse_length=kiwari.length(inches(42), about="The beam's length"),
)

DOVETAIL_TAPER = degrees(10)      # narrowing toward the top: point end up
DOVETAIL_FLARE = atan(scalar(1) / scalar(6))
TRIM_ALLOWANCE = inches(1)        # each leg is cut this much long at both ends, for the level trims


def _leg(k: Kiwari, beam: Timber, end: int, side: int):
    """One leg and its dovetail: `end` is +1/-1 for the beam's +x/-x end, `side` +1/-1 for its +y/-y side."""
    beam_size, leg_size = k.v2("beam_size"), k.v2("leg_size")
    beam_width, beam_height = beam_size[0], beam_size[1]
    height = k.length("sawhorse_height")

    side_splay = k.angle("leg_side_splay_angle")
    if side_splay is None:
        # The faces through both arrises are a thickness apart: sin = thickness / beam height.
        lean_sin = leg_size[1] / beam_height
        lean_cos = sqrt(1 - lean_sin * lean_sin)
    else:
        lean_sin, lean_cos = sin(side_splay), cos(side_splay)
    up = safe_normalize_vector(create_v3(-end * tan(k.angle("leg_y_splay_angle")), -side * lean_sin / lean_cos, 1))
    outward = create_v3(0, side * lean_cos, lean_sin)  # the leg's face normal, square to the beam
    along_beam = create_v3(1, 0, 0)
    width = safe_normalize_vector(along_beam - up * safe_dot_product(along_beam, up))

    # Where the leg's centre crosses the beam's top arris on its side.
    arris = create_v3(end * k.length("leg_distance") / 2, side * beam_width / 2, height)
    # The leg's centreline at the beam's top, half its thickness in from the outer face, and how far
    # it runs from there to the floor.
    top = arris - outward * (leg_size[1] / 2)
    leg_length = top[2] / up[2]
    leg = create_timber(bottom_position=top - up * (leg_length + TRIM_ALLOWANCE),
                        length=leg_length + 2 * TRIM_ALLOWANCE,
                        size=leg_size, length_direction=up, width_direction=width,
                        ticket=f"leg {'+x' if end > 0 else '-x'} {'+y' if side > 0 else '-y'}")

    # The dovetail: its width square to the beam, its neck on the leg's outer face with its top edge
    # on the top arris, its wide face on the leg's inner face, down the whole leg.
    across, into_beam = create_v3(-side, 0, 0), -outward
    slide = cross_product(across, into_beam)
    # Where the dovetail passes the beam's bottom arris, the neck is exactly as wide as the leg is
    # along the beam, and centred on it.
    to_bottom = beam_height * lean_cos
    at_bottom = arris + up * (-to_bottom / safe_dot_product(slide, up))
    width_at_bottom = leg_size[0] / sqrt(1 - up[0] * up[0])
    dovetail = FreeDovetailShape(
        origin=Transform(position=create_v3(at_bottom[0], arris[1], arris[2]),
                         orientation=Orientation.from_x_and_y(across, into_beam)),
        width=width_at_bottom - cos(DOVETAIL_TAPER) * leg_size[1] - 2 * to_bottom * tan(DOVETAIL_TAPER),
        depth=leg_size[1], dovetail_angle=DOVETAIL_FLARE,
        # Up past the beam's top for good -- above it is only the leg, trimmed level. The taper
        # needs finite ends, so "for good" is the beam's height.
        forward_length=beam_height, backward_length=leg_length, taper_angle=DOVETAIL_TAPER,
    )
    joint = cut_free_dovetail_joint(leg, beam, dovetail)

    level_top = adopt_csg(None, leg.transform, HalfSpace(
        normal=create_v3(0, 0, 1), offset=height, label=CutCSGLabel("level_top")))
    level_bottom = adopt_csg(None, leg.transform, HalfSpace(
        normal=create_v3(0, 0, -1), offset=scalar(0), label=CutCSGLabel("level_bottom")))
    cut_leg = CutTimber(leg, cuts=[joint.cuttings["dovetail_timber"],
                                   Cutting(timber=leg, negative_csg=level_top, label=CutCSGLabel("level_top")),
                                   Cutting(timber=leg, negative_csg=level_bottom, label=CutCSGLabel("level_bottom"))],
                        joints=[joint])
    return cut_leg, joint


@frame
def dovetailed_sawhorse(k: Optional[Kiwari] = None) -> Frame:
    k = SAWHORSE.resolve(k)
    beam_size, length = k.v2("beam_size"), k.length("sawhorse_length")
    beam = create_timber(bottom_position=create_v3(-length / 2, 0, k.length("sawhorse_height") - beam_size[1] / 2),
                         length=length, size=beam_size,
                         length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 1, 0), ticket="beam")
    legs, joints = [], []
    for end in (1, -1):
        for side in (1, -1):
            leg, joint = _leg(k, beam, end, side)
            legs.append(leg)
            joints.append(joint)
    # Each leg is let in by its thickness: the beam is housed to the leg's finished shape.
    joints.append(cut_free_house_joint(beam, legs))
    # Built by hand rather than from the joints, for the legs' level trims; the joints ride along
    # so Kigumi can list them.
    beam_cuts = [cutting for joint in joints for cutting in joint.cuttings.values() if cutting.timber is beam]
    return Frame(cut_timbers=[CutTimber(beam, cuts=beam_cuts, joints=joints), *legs],
                 source_joints=joints, name="Dovetailed sawhorse", kiwari=k)
