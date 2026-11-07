# Last checked on kumiki 0.9.0
"""Dovetailed sawhorse: a beam on edge and four splayed legs.

Each leg is let into an arris of the beam by its whole thickness, as a sliding dovetail tapered
point up, so the load wedges it tighter. Seen along the beam, a leg's outer face runs through the
beam's top arris; unless its side splay is given, it leans just so its inner face runs through the
bottom arris. The floor is at z=0.

Drawings are generated: a plan, and a shop drawing for the beam and one for the four legs. The legs'
also looks straight down on a leg's level top, where the dovetail is marked out.

Its tool "export router templates" writes a router template for each leg's socket in the beam to
kigumi_exports/dovetailed_sawhorse/, as an STL in millimetres.
"""


import pathlib

import numpy as np

from kumiki import *
from kumiki.csg.cross_sections import CrossSection, face_cross_section
from kumiki.csg.triangles import mesh_cutcsg
from kumiki.drawings.auto_drawings import with_auto_drawings
from kumiki.drawings.measure import ViewAxes


SAWHORSE = kiwari(
    leg_distance=kiwari.length(inches(22), about="Centre to centre along the beam, where the legs meet its top"),
    leg_y_splay_angle=kiwari.angle(degrees(12), about="How far the legs lean out toward the beam's ends"),
    leg_side_splay=kiwari.ratio(
        optional=True, parts=("rise", "run"), minimum=1,
        about="How far the legs splay out to the side; the slope is determined by the rise and run, at least 1:1. "
              "By default, the board thickness and beam height are used to determine this"),
    beam_size=kiwari.point2(create_v2(inches(2), inches(15, 4)), about="Across and tall"),
    leg_size=kiwari.point2(create_v2(inches(13, 2), inches(3, 4)), about="Width and thickness"),
    sawhorse_height=kiwari.length(inches(30), about="Floor to the top of the beam"),
    sawhorse_length=kiwari.length(inches(42), about="The beam's length"),
)

DOVETAIL_TAPER = degrees(13)      # narrowing toward the top: point end up
DOVETAIL_FLARE = degrees(14)
TRIM_ALLOWANCE = inches(1)

# The router template for a leg's socket in the beam, routed with a dovetail bit through the neck's plane.
JIG_OFFSET = inches(1, 16)    # the guide bushing's radius less the bit's: a 5/8" bushing round a 1/2" bit
JIG_TOP = inches(1, 2)        # the template's thickness above the neck's plane
JIG_BOTTOM = inches(1)        # how far it runs below that plane, down onto the beam it sits on
JIG_WIDTH = inches(2)         # how wide the template is round its opening
BEAM_REFERENCE = TimberFeature.RIGHT_FRONT_EDGE   # the beam's top meets its +y side
LEG_REFERENCE = TimberFeature.RIGHT_FRONT_EDGE    # a leg's outer face meets its +width edge        # each leg is cut this much long at both ends, for the level trims


def _offset_convex(polygon: List[Tuple[float, float]], distance: float) -> List[Tuple[float, float]]:
    """Return a convex polygon with each edge moved `distance` outward (inward if negative), corners kept sharp."""
    points = np.array(polygon, dtype=float)
    if len(points) < 3:
        raise ValueError("a face outline needs at least 3 corners")
    edge_area = np.cross(points, np.roll(points, -1, axis=0)).sum() / 2
    if edge_area < 0:
        points = points[::-1]  # counter-clockwise, so an edge's outward normal is on its right
    starts, ends = points, np.roll(points, -1, axis=0)
    directions = ends - starts
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    normals = np.stack([directions[:, 1], -directions[:, 0]], axis=1)
    shifted = starts + normals * distance
    corners = []
    for i in range(len(points)):
        # Edge i-1 and edge i, each a moved line, meet at corner i.
        a_point, a_dir, b_point, b_dir = shifted[i - 1], directions[i - 1], shifted[i], directions[i]
        turn = np.cross(a_dir, b_dir)
        if abs(turn) < 1e-12:
            continue  # a straight corner
        t = np.cross(b_point - a_point, b_dir) / turn
        corners.append(tuple(a_point + a_dir * t))
    moved = np.array(corners)
    moved_directions = np.roll(moved, -1, axis=0) - moved
    if (np.cross(moved, np.roll(moved, -1, axis=0)).sum() <= 0
            or np.any(np.cross(moved_directions, np.roll(moved_directions, -1, axis=0)) <= 0)):
        raise ValueError(f"insetting the face by {-distance} closes it up")
    return [(float(x), float(y)) for x, y in moved]


def router_template(face: CrossSection, body: CutCSG, offset: Numeric, jig_top: Numeric, jig_width: Numeric,
                    jig_bottom: Numeric = 0) -> CutCSG:
    """Return a router template for cutting `face`'s outline: a frame jig_width wide round an opening.

    `face` is a convex planar outline, from `face_cross_section` (a face of a CSG) or `plane_cross_section`
    (a plane through one), in the same space as `body`. The opening is the face moved out by `offset`
    (the collar's radius less the bit's; negative moves it in). The jig runs `jig_top` along the face's
    normal and `jig_bottom` against it, and `body`, the piece being cut, is taken out of it.
    """
    frame, region = face
    if len(region) != 1:
        raise ValueError(f"a router template needs one convex face outline, not {len(region)} pieces")
    opening = _offset_convex(region[0], float(offset))
    outside = _offset_convex(region[0], float(offset) + float(jig_width))
    # The face's 2D axes, turned if need be so they and its normal make a right-handed frame.
    u, v, normal = frame.u, frame.v, frame.normal
    flip = float(np.dot(np.cross(u, v), normal)) < 0
    if flip:
        v = -v

    def extrusion(outline: List[Tuple[float, float]]) -> ConvexPolygonExtrusion:
        points = [create_v2(x, -y if flip else y) for x, y in outline]
        if flip:
            points.reverse()
        return ConvexPolygonExtrusion(
            points=points,
            transform=Transform(position=create_v3(*frame.origin),
                                orientation=Orientation.from_x_and_y(create_v3(*u), create_v3(*v))),
            start_distance=-jig_bottom, end_distance=jig_top)

    return Difference(extrusion(outside), [extrusion(opening), body], label=CutCSGLabel("router_template"))


def _clip_between(polygon: List[Tuple[float, float]], along: np.ndarray, low: float, high: float) -> List[Tuple[float, float]]:
    """Return the part of a convex polygon where `along` . point lies between `low` and `high`."""
    points = [np.array(point, dtype=float) for point in polygon]
    for sign, bound in ((1, high), (-1, -low)):
        kept = []
        for here, there in zip(points, points[1:] + points[:1]):
            here_in, there_in = sign * (along @ here) <= bound, sign * (along @ there) <= bound
            if here_in:
                kept.append(here)
            if here_in != there_in:
                t = (bound - sign * (along @ here)) / (sign * (along @ (there - here)))
                kept.append(here + (there - here) * t)
        points = kept
    return [(float(x), float(y)) for x, y in points]


def _socket_template(beam: Timber, socket: Cutting) -> CutCSG:
    """Return the router template for one dovetail socket in the beam, in world space.

    Its opening is the dovetail's neck, over the stretch of it where the socket is in the beam; the
    uncut beam is taken out of its underside, so it sits on the beam.
    """
    body = adopt_csg(beam.transform, None, CutTimber(beam, cuts=[]).render_timber_with_cuts_csg_local())
    assert socket.negative_csg is not None, "a socket is a cut"
    dovetail = adopt_csg(beam.transform, None, socket.negative_csg)
    assert isinstance(dovetail, (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft)), "the socket is the dovetail's solid"
    neck = next(feature for feature in dovetail.get_declared_features() if feature.name == "dovetail_neck")
    plane = neck.locate_simple_unbounded(dovetail)
    assert plane is not None, "the dovetail's neck is a flat face"
    neck_face = face_cross_section(neck, dovetail, None, plane.point, float(beam.length))
    assert neck_face is not None, "the dovetail's neck can be cut by its own plane"
    frame, (outline,) = neck_face
    # Where the socket starts and stops along the dovetail, from the corners of the part in the beam.
    axis = np.array([float(value) for value in dovetail.transform.orientation.matrix[:, 2]])
    reach = mesh_cutcsg(Intersection(dovetail, body)).mesh.vertices @ axis - frame.origin @ axis
    along = np.array([axis @ frame.u, axis @ frame.v])
    opening = _clip_between(outline, along, float(reach.min()), float(reach.max()))
    return router_template((frame, [opening]), body, JIG_OFFSET, JIG_TOP, JIG_WIDTH, JIG_BOTTOM)


def _export_socket_templates(beam: Timber, legs: List[CutTimber], joints: List[Joint]) -> str:
    """Write each leg's socket template to an STL in millimetres, in kigumi_exports/, and say where."""
    folder = pathlib.Path.cwd() / "kigumi_exports" / "dovetailed_sawhorse"
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for leg, joint in zip(legs, joints):
        mesh = mesh_cutcsg(_socket_template(beam, joint.cuttings["receiving_timber"])).mesh.copy()
        mesh.apply_scale(1000)
        path = folder / f"router template {leg.timber.ticket.path}.stl"
        mesh.export(path)
        written.append(path.name)
    return f"Wrote {len(written)} router templates to {folder}:\n" + "\n".join(written)


def _leg_end(name: str) -> FeatureOverride:
    """Return the override naming a level trim's face, in the END_CUT group."""
    return FeatureOverride(HALF_SPACE_PLANE, name, FeatureProperties(group=FeatureGroup.END_CUT))


def _leg(k: Kiwari, beam: Timber, end: int, side: int):
    """One leg and its dovetail: `end` is +1/-1 for the beam's +x/-x end, `side` +1/-1 for its +y/-y side."""
    beam_size, leg_size = k.v2("beam_size"), k.v2("leg_size")
    beam_width, beam_height = beam_size[0], beam_size[1]
    height = k.length("sawhorse_height")

    slope = k.ratio("leg_side_splay")
    if slope is None:
        # The faces through both arrises are a thickness apart: sin = thickness / beam height.
        lean_sin = leg_size[1] / beam_height
        lean_cos = sqrt(1 - lean_sin * lean_sin)
    else:
        # Seen along the beam, the leg rises `slope` for each unit it runs out: atan(slope) from the floor.
        lean_sin = 1 / sqrt(1 + slope * slope)
        lean_cos = slope * lean_sin
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
                        ticket=TimberTicket(path=f"leg {'+x' if end > 0 else '-x'} {'+y' if side > 0 else '-y'}",
                                            reference_features=(LEG_REFERENCE,)))

    # The dovetail: its width square to the beam, its neck on the leg's outer face with its top edge
    # on the top arris, its wide face on the leg's inner face, down the whole leg.
    across, into_beam = create_v3(-side, 0, 0), -outward
    slide = cross_product(across, into_beam)
    # Where the dovetail passes the beam's bottom arris, the neck is exactly as wide as the leg is
    # along the beam, and centred on it.
    to_bottom = beam_height * lean_cos
    at_bottom = arris + up * (-to_bottom / safe_dot_product(slide, up))
    width_at_bottom = leg_size[0] / sqrt(1 - up[0] * up[0])
    # Turned in the leg's face, about the centre at the bottom arris, so the inner flank stands
    # plumb seen from the side; the neck stays in the face, its line on the beam top along the beam.
    turn = end * side * DOVETAIL_TAPER
    turned_across = across * cos(turn) - slide * sin(turn)
    turned_slide = across * sin(turn) + slide * cos(turn)
    dovetail = FreeDovetailShape(
        origin=Transform(position=at_bottom + turned_slide * to_bottom,
                         orientation=Orientation.from_x_and_y(turned_across, into_beam)),
        width=width_at_bottom - cos(DOVETAIL_TAPER) * leg_size[1] - 2 * to_bottom * tan(DOVETAIL_TAPER),
        depth=leg_size[1], dovetail_angle=DOVETAIL_FLARE, taper_angle=DOVETAIL_TAPER,
    )
    joint = cut_free_dovetail_joint(leg, beam, dovetail)

    # The level trims meet the dovetail's CROSSING faces in derived edges.
    level_top = adopt_csg(None, leg.transform, HalfSpace(
        normal=create_v3(0, 0, 1), offset=height, label=CutCSGLabel("level_top"),
        feature_overrides=[_leg_end("level_top")]))
    level_bottom = adopt_csg(None, leg.transform, HalfSpace(
        normal=create_v3(0, 0, -1), offset=scalar(0), label=CutCSGLabel("level_bottom"),
        feature_overrides=[_leg_end("level_bottom")]))
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
                         length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 1, 0),
                         ticket=TimberTicket(path="beam", reference_features=(BEAM_REFERENCE,)))
    legs, joints = [], []
    for end in (1, -1):
        for side in (1, -1):
            leg, joint = _leg(k, beam, end, side)
            legs.append(leg)
            joints.append(joint)
    # Built by hand rather than from the joints, for the legs' level trims; the joints ride along
    # so Kigumi can list them.
    beam_cuts = [cutting for joint in joints for cutting in joint.cuttings.values() if cutting.timber is beam]
    sawhorse = Frame(cut_timbers=[CutTimber(beam, cuts=beam_cuts, joints=joints), *legs],
                     source_joints=joints, name="Dovetailed sawhorse", kiwari=k,
                     tools=[Tool("export router templates",
                                 "Write the router template for each leg's socket in the beam to an STL, in mm",
                                 lambda: _export_socket_templates(beam, legs, joints))])
    return with_auto_drawings(sawhorse, fixed_path="beam", extra_views=_leg_top_view)


def _leg_top_view(cut: CutTimber) -> Dict[str, ViewAxes]:
    """Return a leg's view straight down on its level top, square to the beam's top, the beam across."""
    if not cut.timber.ticket.path.startswith("leg"):
        return {}
    return {"Leg top": ViewAxes(look=create_v3(0, 0, -1), right=create_v3(1, 0, 0), up=create_v3(0, 1, 0))}
