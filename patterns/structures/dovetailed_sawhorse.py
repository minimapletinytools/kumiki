# Last checked on kumiki 0.9.0
"""Dovetailed sawhorse: a beam on edge and four splayed legs.

Each leg is let into an arris of the beam by its whole thickness, as a sliding dovetail tapered
point up, so the load wedges it tighter. Seen along the beam, a leg's outer face runs through the
beam's top arris; unless its side splay is given, it leans just so its inner face runs through the
bottom arris. The floor is at z=0.

Drawings are generated: a plan, and a shop drawing for the beam and one for the four legs. The legs'
also looks straight down on a leg's level top, where the dovetail is marked out.

Its tool "export router templates" writes router templates to kigumi_exports/dovetailed_sawhorse/, as
STLs in millimetres: one for a leg's socket in the beam, and one for its tail. The legs come in two
mirrored pairs, so there are two sets: A for legs +x +y and -x -y, B for +x -y and -x +y.
"""


import pathlib
from enum import Enum

import numpy as np

from kumiki import *
from kumiki.csg.cross_sections import CrossSection, PlaneFrame, cross_section_polygons, face_cross_section
from kumiki.csg.triangles import mesh_cutcsg
from kumiki.drawings.auto_drawings import with_auto_drawings
from kumiki.drawings.measure import ViewAxes


SAWHORSE = kiwari(
    leg_distance=kiwari.length(inches(22), about="Centre to centre along the beam, where the legs meet its top"),
    leg_y_splay_angle=kiwari.angle(
        optional=True, about="How far the legs lean out toward the beam's ends. "
                             "By default, atan of the leg's thickness over the beam's height"),
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


class TemplateSides(Enum):
    """Which of the opening's sides the template guides the router along, above the face."""
    FOUR_SIDED = "4 sided"
    TWO_SIDED_LR = "2 sided, left and right"    # the sides facing most along global -x and +x
    TWO_SIDED_TB = "2 sided, top and bottom"    # the sides facing most along global -z and +z


_ABOVE_FACE = mm(0.01)    # how far the two-sided template's open part keeps off the faces it would lie on

_SIDES_FACING = {TemplateSides.TWO_SIDED_LR: np.array([1.0, 0.0, 0.0]),
                 TemplateSides.TWO_SIDED_TB: np.array([0.0, 0.0, 1.0])}


def _two_sides(opening: List[Tuple[float, float]], facing: np.ndarray) -> List[Tuple[np.ndarray, float]]:
    """Return the opening's two sides facing most along -`facing` and +`facing` (2D), as (outward normal, offset) lines."""
    points = np.array(opening)
    edges = np.roll(points, -1, axis=0) - points
    normals = np.stack([edges[:, 1], -edges[:, 0]], axis=1) / np.linalg.norm(edges, axis=1, keepdims=True)
    along = normals @ facing
    chosen = [int(np.argmin(along)), int(np.argmax(along))]
    if np.linalg.norm(facing) < 0.3 or along[chosen[0]] > -0.5 * np.linalg.norm(facing) \
            or along[chosen[1]] < 0.5 * np.linalg.norm(facing):
        raise ValueError("the face has no two sides facing that way: it lies too nearly square to it")
    return [(normals[i], float(normals[i] @ points[i])) for i in chosen]


def _face_extrusion(face_frame, outline: List[Tuple[float, float]], start: Numeric, end: Numeric,
                    label: CutCSGLabel = CutCSGLabel.NoLabel()) -> ConvexPolygonExtrusion:
    """Return `outline`, in `face_frame`'s 2D axes, extruded from `start` to `end` along its normal."""
    # The face's 2D axes, turned if need be so they and its normal make a right-handed frame.
    u, v, normal = face_frame.u, face_frame.v, face_frame.normal
    flip = float(np.dot(np.cross(u, v), normal)) < 0
    if flip:
        v = -v
    points = [create_v2(x, -y if flip else y) for x, y in outline]
    if flip:
        points.reverse()
    return ConvexPolygonExtrusion(
        points=points,
        transform=Transform(position=create_v3(*face_frame.origin),
                            orientation=Orientation.from_x_and_y(create_v3(*u), create_v3(*v))),
        start_distance=start, end_distance=end, label=label)


def router_template(face: CrossSection, body: CutCSG, offset: Numeric, jig_top: Numeric, jig_width: Numeric,
                    jig_bottom: Numeric = 0, sides: TemplateSides = TemplateSides.FOUR_SIDED,
                    supports: int = 0, support_thickness: Numeric = mm(5)) -> CutCSG:
    """Return a router template for cutting `face`'s outline: a frame jig_width wide round an opening.

    `face` is a convex planar outline, from `face_cross_section` (a face of a CSG) or `plane_cross_section`
    (a plane through one), in the same space as `body`. The opening is the face moved out by `offset`
    (the collar's radius less the bit's; negative moves it in). The jig runs `jig_top` along the face's
    normal and `jig_bottom` against it, and `body`, the piece being cut, is taken out of it.

    With two `sides`, the part above the face guides along those two only: everything between their
    lines is open, leaving two rails, and the part below the face is the whole frame as with four.

    `supports` strips, each `support_thickness` wide, are left across the opening, evenly spaced between
    the guided sides (left and right for four) and running along them.
    """
    frame, region = face
    if len(region) != 1:
        raise ValueError(f"a router template needs one convex face outline, not {len(region)} pieces")
    opening = _offset_convex(region[0], float(offset))
    outside = _offset_convex(region[0], float(offset) + float(jig_width))
    between = None
    if sides is not TemplateSides.FOUR_SIDED:
        # Everything between the two sides' lines, kept a hair inside them (the opening's own sides guide)
        # and run past the outline, so none of its faces lies on another's.
        facing = _SIDES_FACING[sides]
        between = _offset_convex(region[0], float(offset) + float(jig_width) + float(mm(1)))
        for normal, line_offset in _two_sides(opening, np.array([facing @ frame.u, facing @ frame.v])):
            between = _clip_between(between, normal, -np.inf, line_offset - float(_ABOVE_FACE))

    # Each support's centreline splits the way between the guided sides (left and right for four) in a
    # fixed ratio, so it runs parallel to them, or between their angles where they converge.
    guided_facing = _SIDES_FACING.get(sides, _SIDES_FACING[TemplateSides.TWO_SIDED_LR])
    guided = _two_sides(opening, np.array([guided_facing @ frame.u, guided_facing @ frame.v])) if supports > 0 else []
    half = float(support_thickness) / 2
    # Each support's centreline as (unit direction, offset): direction . p < offset toward the first side.
    centrelines = []
    for i in range(supports):
        share = (i + 1) / (supports + 1)
        (normal_a, offset_a), (normal_b, offset_b) = guided
        # (1 - share) * (distance in from side a) = share * (distance in from side b)
        direction = share * normal_b - (1 - share) * normal_a
        offset = share * offset_b - (1 - share) * offset_a
        length = np.linalg.norm(direction)
        centrelines.append((direction / length, offset / length))
    # The stretches between supports, each as half-planes (direction, bound): direction . p <= bound.
    gaps = []
    for i in range(supports + 1):
        bounds = []
        if i > 0:
            direction, offset = centrelines[i - 1]
            bounds.append((-direction, -(offset + half)))
        if i < supports:
            direction, offset = centrelines[i]
            bounds.append((direction, offset - half))
        gaps.append(bounds)

    def extrusions(outline: List[Tuple[float, float]], start: Numeric, end: Numeric) -> List[ConvexPolygonExtrusion]:
        # The outline less the supports' bands, as one extrusion per piece left.
        pieces = []
        for bounds in gaps:
            piece = outline
            for direction, bound in bounds:
                piece = _clip_between(piece, direction, -np.inf, bound)
            pieces.append(piece)
        return [_face_extrusion(frame, piece, start, end) for piece in pieces if len(piece) >= 3]

    taken = [*extrusions(opening, -jig_bottom, jig_top), body]
    if between is not None:
        # From a hair above the face, so its floor meets nothing lying in the face (the beam's arris, on
        # the sawhorse), and to past the top: faces lying on others leave slivers an STL can't keep closed.
        taken += extrusions(between, _ABOVE_FACE, jig_top + mm(1))
    return Difference(_face_extrusion(frame, outside, -jig_bottom, jig_top), taken, label=CutCSGLabel("router_template"))


def tail_template(face: CrossSection, offset: Numeric, thickness: Numeric) -> CutCSG:
    """Return a router template for cutting round `face`'s outline: the face moved in by `offset`, as a solid.

    `face` is as for `router_template`. The template runs `thickness` against the face's normal, the
    side opposite `router_template`'s.
    """
    frame, region = face
    if len(region) != 1:
        raise ValueError(f"a router template needs one convex face outline, not {len(region)} pieces")
    return _face_extrusion(frame, _offset_convex(region[0], -float(offset)), -thickness, 0,
                           label=CutCSGLabel("tail_template"))


# The router templates for a leg's socket in the beam, routed with a dovetail bit through the neck's
# plane, and for its tail, routed from the leg's inner face: the export tool's parameters. Both trace
# the dovetail's wide face, where the bit is widest in the socket and narrowest round the tail.
ROUTER_TEMPLATE = kiwari(
    beam_bushing_offset=kiwari.length(inches(0), about="The guide bushing's radius less the bit's at the widest point of the cut"),
    leg_bushing_offset=kiwari.length(inches(3, 16), about="The guide bushing's radius less the bit's at the narrowest point of the cut"),
    top_depth=kiwari.length(inches(1, 2), minimum=0, about="The templates' thickness: the beam template's above the neck's plane, the leg template's behind the wide face"),
    bottom_depth=kiwari.length(inches(1), minimum=0, about="How far the beam template runs below the neck's plane, down onto the beam it sits on"),
    base_support_width=kiwari.length(inches(2), minimum=0, about="How wide the beam template is round its opening"),
    sides=kiwari.choice(TemplateSides, TemplateSides.TWO_SIDED_LR,
                        about="Which sides it guides along above the neck: the flanks are left and right"),
    supports=kiwari.count(0, minimum=0, about="How many strips to leave across the socket template's opening, as supports, "
                                                "running along the sides it guides (left and right for 4 sided)"),
    support_thickness=kiwari.length(mm(5), minimum=0, about="Each support's width"),
    clamp_width=kiwari.length(inches(1, 2), minimum=0, about="How wide each clamp slot is, to fit the clamp's jaw"),
    clamp_depth=kiwari.length(inches(3, 8), minimum=0, about="How deep each clamp slot is, into the template's router side"),
    clamp_clearance=kiwari.length(inches(1, 4), minimum=0, about="How far the socket template's clamp slots stop short of its opening"),
    tail_clamp_length=kiwari.length(inches(1), minimum=0, about="How far the tail template's clamp slot runs in from its top end"),
)

CLAMP_FLOOR = inches(1, 4)    # the least a template keeps under a clamp slot; thinner ones are thickened


def _slot(face_frame, start: np.ndarray, direction: np.ndarray, near: float, far: float, width: Numeric,
          low: Numeric, high: Numeric) -> ConvexPolygonExtrusion:
    """Return a slot `width` wide along `direction` (unit, 2D in the face), from `near` to `far` past `start`.

    It runs from `low` to `high` along the face's normal.
    """
    side = np.array([-direction[1], direction[0]]) * float(width) / 2
    ends = (start + direction * near, start + direction * far)
    corners = [ends[0] - side, ends[1] - side, ends[1] + side, ends[0] + side]
    return _face_extrusion(face_frame, [(float(x), float(y)) for x, y in corners], low, high)


def _convex_hull(points: np.ndarray) -> np.ndarray:
    """Return the convex hull of 2D `points`, counter-clockwise."""
    ordered = sorted({(round(float(x), 12), round(float(y), 12)) for x, y in points})

    def chain(run):
        kept: List[Tuple[float, float]] = []
        for point in run:
            while len(kept) >= 2 and np.cross(np.subtract(kept[-1], kept[-2]), np.subtract(point, kept[-2])) <= 0:
                kept.pop()
            kept.append(point)
        return kept[:-1]

    return np.array(chain(ordered) + chain(ordered[::-1]))


def _edge_lines(polygon: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return a convex polygon's edges as (outward unit normals, offsets): normal . p = offset on each."""
    edges = np.roll(polygon, -1, axis=0) - polygon
    normals = np.stack([edges[:, 1], -edges[:, 0]], axis=1) / np.linalg.norm(edges, axis=1, keepdims=True)
    if np.cross(polygon, np.roll(polygon, -1, axis=0)).sum() < 0:
        normals = -normals
    return normals, np.einsum("ij,ij->i", normals, polygon)


def _diagonal_slot(face_frame, opening: List[Tuple[float, float]], footprint: np.ndarray, toward: np.ndarray,
                   width: Numeric, clearance: Numeric, low: Numeric, high: Numeric) -> ConvexPolygonExtrusion:
    """Return a slot running out diagonally along `toward` (world) from beside the opening, over the beam.

    Its inner end is beside the middle of the opening's side facing `toward`'s level part, over the stretch
    of that side above `footprint` (the beam seen along the face's normal, a convex 2D polygon), and
    `clearance` clear of the opening; it runs from there to well past the template's edge.
    """
    def in_face(vector: np.ndarray) -> np.ndarray:
        flat = np.array([vector @ face_frame.u, vector @ face_frame.v])
        return flat / np.linalg.norm(flat)

    direction = in_face(toward)
    points = np.array(opening)
    normals, offsets = _edge_lines(points)
    side_index = int(np.argmax(normals @ in_face(toward * np.array([1.0, 1.0, 0.0]))))
    start, end = points[side_index], points[(side_index + 1) % len(points)]
    # The stretch of that side over the beam, as a range of t along start + (end - start) * t.
    beam_normals, beam_offsets = _edge_lines(footprint)
    low_t, high_t = 0.0, 1.0
    for normal, offset in zip(beam_normals, beam_offsets):
        rate, at_start = normal @ (end - start), normal @ start - offset
        if abs(rate) < 1e-12:
            if at_start > 0:
                raise ValueError("the opening's side has no stretch over the beam")
        elif rate > 0:
            high_t = min(high_t, -at_start / rate)
        else:
            low_t = max(low_t, -at_start / rate)
    if low_t >= high_t:
        raise ValueError("the opening's side has no stretch over the beam")
    middle = start + (end - start) * (low_t + high_t) / 2
    side = np.array([-direction[1], direction[0]]) * float(width) / 2

    def clear(distance: float) -> bool:
        tips = (middle + direction * distance + side, middle + direction * distance - side)
        return all(np.max(normals @ tip - offsets) >= float(clearance) for tip in tips)

    near, far = 0.0, float(inches(12))
    for _ in range(60):
        halfway = (near + far) / 2
        near, far = (near, halfway) if clear(halfway) else (halfway, far)
    inner_end = middle + direction * far
    if np.max(beam_normals @ inner_end - beam_offsets) > 0:
        raise ValueError("a clamp slot's inner end misses the beam")
    return _slot(face_frame, middle, direction, far, far + float(inches(12)), width, low, high)


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


def _templates(beam: Timber, socket: Cutting, t: Kiwari) -> Tuple[CutCSG, CutCSG]:
    """Return the router templates for one dovetail's socket in the beam and for its tail, in world space.

    Both trace the dovetail's wide face, seen square to it, over the stretch where the socket is in the
    beam. The beam template lies on the neck's plane, its opening the wide face moved out by the beam
    offset, with the uncut beam taken out of its underside so it sits on the beam. The leg template lies
    on the wide face, on the side away from the leg, as the wide face moved in by the leg offset. Each
    has clamp slots in its router side, the face away from the leg; the leg template is thickened to keep
    `CLAMP_FLOOR` under its slot.
    """
    body = adopt_csg(beam.transform, None, CutTimber(beam, cuts=[]).render_timber_with_cuts_csg_local())
    assert socket.negative_csg is not None, "a socket is a cut"
    dovetail = adopt_csg(beam.transform, None, socket.negative_csg)
    assert isinstance(dovetail, (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft)), "the socket is the dovetail's solid"
    faces = {feature.name: feature for feature in dovetail.get_declared_features()}
    neck_plane = faces["dovetail_neck"].locate_simple_unbounded(dovetail)
    wide_plane = faces["dovetail_wide_face"].locate_simple_unbounded(dovetail)
    assert neck_plane is not None and wide_plane is not None, "the dovetail's neck and wide face are flat"
    neck_face = face_cross_section(faces["dovetail_neck"], dovetail, None, neck_plane.point, float(beam.length))
    wide_face = face_cross_section(faces["dovetail_wide_face"], dovetail, None, wide_plane.point, float(beam.length))
    assert neck_face is not None and wide_face is not None, "the dovetail's faces can be cut by their own planes"
    frame = neck_face[0]
    (wide_corners,) = cross_section_polygons(wide_face)
    # The wide face is parallel to the neck, a leg's thickness in: its outline in the neck's 2D axes.
    wide_outline = [frame.to_2d(corner) for corner in wide_corners]
    depth = float((as_ndarray(neck_plane.point) - as_ndarray(wide_plane.point)) @ frame.normal)
    wide_frame = PlaneFrame.with_axes(frame.origin - frame.normal * depth, frame.u, frame.v, frame.normal)
    # Where the socket starts and stops along the dovetail, from the corners of the part in the beam.
    axis = np.array([float(value) for value in dovetail.transform.orientation.matrix[:, 2]])
    reach = mesh_cutcsg(Intersection(dovetail, body)).mesh.vertices @ axis - frame.origin @ axis
    along = np.array([axis @ frame.u, axis @ frame.v])
    outline = _clip_between(wide_outline, along, float(reach.min()), float(reach.max()))
    beam_offset, leg_offset = t.length("beam_bushing_offset"), t.length("leg_bushing_offset")
    top = t.length("top_depth")
    socket_template = router_template((frame, [outline]), body, beam_offset, top, t.length("base_support_width"),
                                      t.length("bottom_depth"), t.choice("sides", TemplateSides),
                                      t.count("supports"), t.length("support_thickness"))
    # Clamp slots, into each template's router side: the socket's two run diagonally out to the top left
    # and bottom right from over the beam beside the opening, the tail's down from its narrow top end.
    width, depth_of_slot = t.length("clamp_width"), t.length("clamp_depth")
    opening = _offset_convex(outline, float(beam_offset))
    beam_seen = (mesh_cutcsg(body).mesh.vertices - frame.origin) @ np.array([frame.u, frame.v]).T
    footprint = _convex_hull(beam_seen)
    socket_template = Difference(socket_template, [
        _diagonal_slot(frame, opening, footprint, np.array(toward), width, t.length("clamp_clearance"),
                       top - depth_of_slot, top + mm(1))
        for toward in ((-1.0, 0.0, 1.0), (1.0, 0.0, -1.0))], label=CutCSGLabel("socket_template"))
    tail_thickness = max(top, depth_of_slot + CLAMP_FLOOR)
    tail = tail_template((wide_frame, [outline]), leg_offset, tail_thickness)
    tail_outline = np.array(_offset_convex(outline, -float(leg_offset)))
    up = np.array([frame.u[2], frame.v[2]]) / np.linalg.norm([frame.u[2], frame.v[2]])
    # The top end: the edge facing most up, the slot from its middle along its inward normal.
    starts, ends = tail_outline, np.roll(tail_outline, -1, axis=0)
    normals = np.stack([ends[:, 1] - starts[:, 1], starts[:, 0] - ends[:, 0]], axis=1)
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    if np.cross(starts, ends).sum() < 0:
        normals = -normals
    top_edge = int(np.argmax(normals @ up))
    tip = (starts[top_edge] + ends[top_edge]) / 2
    tail = Difference(tail, [_slot(wide_frame, tip, -normals[top_edge], -float(mm(1)), float(t.length("tail_clamp_length")), width,
                                   -tail_thickness - mm(1), -tail_thickness + depth_of_slot)],
                      label=CutCSGLabel("tail_template"))
    return socket_template, tail


# The legs come in two mirrored pairs, each a half-turn of the other about the beam's middle: one
# leg of each stands for its pair.
TEMPLATE_PAIRS = {"A": "leg +x +y", "B": "leg +x -y"}


def _export_templates(beam: Timber, legs: List[CutTimber], joints: List[Joint], t: Kiwari) -> str:
    """Write the beam and leg templates for each pair of legs to STLs in millimetres, in kigumi_exports/, and say where."""
    folder = pathlib.Path.cwd() / "kigumi_exports" / "dovetailed_sawhorse"
    folder.mkdir(parents=True, exist_ok=True)
    joint_of = {leg.timber.ticket.path: joint for leg, joint in zip(legs, joints)}
    written = []
    for pair, leg in TEMPLATE_PAIRS.items():
        beam_template, leg_template = _templates(beam, joint_of[leg].cuttings["receiving_timber"], t)
        for part, template in (("beam_template", beam_template), ("leg_template", leg_template)):
            mesh = mesh_cutcsg(template).mesh.copy()
            mesh.apply_scale(1000)
            path = folder / f"{pair} {part}.stl"
            mesh.export(path)
            written.append(path.name)
    return (f"Wrote {len(written)} router templates to {folder}:\n" + "\n".join(written)
            + "\nA is for legs +x +y and -x -y, B for +x -y and -x +y.")


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
    y_splay = k.angle("leg_y_splay_angle")
    if y_splay is None:
        y_splay = atan(leg_size[1] / beam_height)
    up = safe_normalize_vector(create_v3(-end * tan(y_splay), -side * lean_sin / lean_cos, 1))
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
                                 "Write the router templates for each leg's socket in the beam and its tail to STLs, in mm",
                                 lambda t: _export_templates(beam, legs, joints, t), kiwari=ROUTER_TEMPLATE)])
    return with_auto_drawings(sawhorse, fixed_path="beam", extra_views=_leg_top_view)


def _leg_top_view(cut: CutTimber) -> Dict[str, ViewAxes]:
    """Return a leg's view straight down on its level top, square to the beam's top, the beam across."""
    if not cut.timber.ticket.path.startswith("leg"):
        return {}
    return {"Leg top": ViewAxes(look=create_v3(0, 0, -1), right=create_v3(1, 0, 0), up=create_v3(0, 1, 0))}
