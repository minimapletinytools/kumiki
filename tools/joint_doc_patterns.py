"""Draw the remaining basic joint patterns from their cut members and layout datums."""

from dataclasses import dataclass
from functools import partial

import numpy as np

from kumiki import Frame, TimberEnd, TimberLongFace
from kumiki.csg.cutcsg import csg_children
from kumiki.measuring import get_center_point_on_face_global
from kumiki.geometry import Line, Plane, intersect_planes
from kumiki.rule import as_ndarray, create_v3
from patterns import basic_joints_patterns as basic
from patterns.board.board_joints_patterns import example_board_in_grooved_frame
from patterns.free.free_dovetail_joint_patterns import example_free_sliding_dovetail, example_free_tapered_dovetail
from tools.render_joint_docs import (
    BACK_RIGHT,
    FRONT_LEFT,
    PLAN,
    SIDE,
    STOCK,
    FIELD_WIDTH,
    HEIGHT,
    WIDTH,
    annotate,
    annotate_plan_angle,
    crossing,
    feature,
    foot_on_plane,
    panel,
    plane_of,
    point_of,
    primitive_features,
    save,
    sheet,
)

FRONT_RIGHT = (1, -1, 1)
BELOW = (1, 1, -1)
END = (1, 0, 0)
BOARD_DETAIL = 0.13
OVERVIEW = 0.60


@dataclass
class Span:
    label: str
    start: np.ndarray
    end: np.ndarray
    inline: bool = False
    offset: float = 34


def _walk(root):
    yield root
    for child in csg_children(root):
        yield from _walk(child)


def node(cut, name):
    """Find the unique cut primitive or group with the requested label."""
    matches = [
        n for c in cut.cuts if c.negative_csg is not None for n in _walk(c.negative_csg) if n.label.name == name
    ]
    if len(matches) != 1:
        raise ValueError(f"{cut.timber.ticket.path} has {len(matches)} cuts named {name}")
    return matches[0]


def corners(cut, name, *, only_child=False):
    primitive = node(cut, name)
    if only_child:
        (primitive,) = csg_children(primitive)
    return {
        int(n.split(".")[1]): point_of(h)
        for n, h in primitive_features(cut, primitive).items()
        if n.startswith("corner.")
    }


def axis_span(label, point, plane, *, offset=34):
    return Span(label, point, foot_on_plane(point, plane), offset=offset)


def stock_plane(cut, side):
    return plane_of(feature(cut, STOCK, "rptw." + side))


class Plate:
    """Place member views and model-space dimensions on a two-column sheet."""

    def __init__(self, joint, title, panels):
        self.root = sheet(title, title, rows=(panels + 1) // 2, columns=min(panels, 2))
        frame = joint if isinstance(joint, Frame) else Frame.from_joints([joint])
        self.cuts = {c.timber.ticket.path: c for c in frame.cut_timbers}
        self.accessories = {} if isinstance(joint, Frame) else joint.jointAccessories
        self.slot = 0

    def view(
        self, title, cut, preset, center, *spans, width=FIELD_WIDTH, xray=False, companions=(), mesh_outline=False
    ):
        view, project = panel(
            self.root,
            self.slot,
            title,
            cut,
            preset,
            center,
            [],
            field_width=width,
            xray=xray,
            companions=companions,
            mesh_outline=mesh_outline,
            up_hint=(0, 1, 0) if preset == PLAN else (0, 0, 1),
        )
        self.slot += 1
        # Place captions in the same order as their anchors across the sheet.
        ordered = sorted(spans, key=lambda s: project((s.start + s.end) / 2)[0])
        captions = []
        for i, span in enumerate(ordered):
            a, b = sorted((project(p) for p in (span.start, span.end)), key=lambda p: (round(p[0], 4), -p[1]))
            run = b - a
            if np.linalg.norm(run) < 1e-5:
                raise ValueError(f"{title}: {span.label} is end-on")
            if span.inline:
                annotate(view, span.label, (span.start, span.end), project, 0)
                continue
            normal = np.array([run[1], -run[0]]) / np.linalg.norm(run)
            top = (a[1] + b[1]) / 2 < HEIGHT / 2
            margin = min(WIDTH / 2, len(span.label) * 4.3 + 12)
            x = np.clip((i + 0.5) * WIDTH / len(ordered), margin, WIDTH - margin)
            caption = np.array([x, 37 if top else HEIGHT - 25])
            for prev, half_width in captions:
                if abs(x - prev[0]) < margin + half_width and abs(caption[1] - prev[1]) < 21:
                    caption[1] += 24 if top else -24
            captions.append((caption.copy(), margin))
            offset = span.offset if (caption - (a + b) / 2) @ normal > 0 else -span.offset
            annotate(view, span.label, (span.start, span.end), project, offset, caption)
        return view, project

    def assembly(self, center, preset=FRONT_LEFT, width=FIELD_WIDTH):
        cut, *others = self.cuts.values()
        bodies = [
            (c.timber.ticket.path, c.render_timber_with_cuts_csg_local(), c.timber.transform) for c in others
        ]
        bodies.extend((k, a.get_csg_local(), a.transform) for k, a in (self.accessories or {}).items())
        return self.view("Assembled joint", cut, preset, center, width=width, companions=bodies)


def plain(plate, *, brace=False, miter=False):
    cuts = list(plate.cuts.values())
    center = (0.055, 0.55, 0) if brace else (0, 0, 0)
    if miter:
        view, project = plate.assembly(center, PLAN, width=OVERVIEW)
        vertex = np.array(center)
        directions = [as_ndarray(c.timber.get_length_direction_global()) for c in cuts]
        first, second = (project(vertex + 0.12 * d) for d in directions)
        annotate_plan_angle(view, "corner_angle", project(vertex), first, second, (380, 84))
    else:
        plate.assembly(center, width=OVERVIEW)


def cross_lap(plate, *, house=False):
    first, second = plate.cuts.values()
    depth = node(first, "lap_depth_plane")
    plane = plane_of(primitive_features(first, depth)["lap_depth"])
    normal = as_ndarray(plane.normal)
    # The waste occupies the side opposite the half-space in the cutter difference.
    first_side = "right" if normal[2] > 0 else "left"
    second_side = "left" if first_side == "right" else "right"

    def notch(cut, side, name):
        floor = plane_of(primitive_features(cut, node(cut, "lap_depth_plane"))["lap_depth"])
        cutter = primitive_features(cut, node(cut, "crossing_timber"))
        left = plane_of(cutter["crossing_front"])
        right = plane_of(cutter["crossing_back"])
        front = stock_plane(cut, "front")
        outside = as_ndarray(front.normal) + as_ndarray(stock_plane(cut, side).normal)
        preset = max(
            (BACK_RIGHT, FRONT_LEFT, FRONT_RIGHT, BELOW, (-1, -1, -1), (1, -1, -1)),
            key=lambda direction: outside @ direction,
        )
        edge = intersect_planes(floor, front)
        a, b = (crossing(edge, face) for face in (left, right))
        plate.view(
            name,
            cut,
            preset,
            (a + b) / 2 - as_ndarray(stock_plane(cut, "front").normal) * float(cut.timber.size[1]) / 2,
            Span(
                "crossing timber width"
                if np.isclose(abs(as_ndarray(left.normal) @ as_ndarray(stock_plane(cut, "front").normal)), 0)
                else "notch length",
                a,
                b,
            ),
            axis_span(
                "overlap" if house else "overlap × cut_ratio" if cut is first else "overlap × (1 − cut_ratio)",
                a,
                stock_plane(cut, side),
            ),
        )

    if house:
        plate.assembly((0, 0, 0.025))
    notch(first, first_side, "Housing" if house else "First notch")
    if not house:
        notch(second, second_side, "Second notch")


def splice_lap(p):
    a, b = p.cuts.values()
    v, w = corners(a, "lap_cut"), corners(b, "lap_cut")
    p.view("First lap", a, BACK_RIGHT, (v[0] + v[4]) / 2, Span("lap_length", v[0], v[4]))
    # The removed section of the mating lap equals the retained section of the first.
    for i in (1, 3):
        edge = w[i] - w[0]
        widths = [
            abs(
                (as_ndarray(stock_plane(b, s1).point) - as_ndarray(stock_plane(b, s2).point))
                @ (edge / np.linalg.norm(edge))
            )
            for s1, s2 in [("right", "left"), ("front", "back")]
        ]
        if np.linalg.norm(edge) < max(widths) - 1e-8:
            p.view("Mating lap", b, (-1, 1, 1), (w[i] + w[4]) / 2, Span("lap_depth", w[i + 4], w[4], inline=True))
            break
    else:
        raise ValueError("The mating section must be shallower than the stock")


def housed(p):
    a, b = p.cuts.values()
    v = corners(a, "housing")
    w = corners(b, "shoulder_notch_relief")
    p.view(
        "Housed end",
        a,
        BACK_RIGHT,
        (v[4] + v[2]) / 2,
        Span("housing_width", v[6], v[7]),
        Span("housing_length", v[5], v[6]),
    )
    p.view(
        "Recessed socket",
        b,
        FRONT_LEFT,
        (0, -0.025, 0),
        Span("housing_depth", v[4], v[0]),
        axis_span("receiving_timber_shoulder_inset", w[2], stock_plane(b, "front"), offset=0),
    )


def fingers(p, *, splice=False):
    a, b = p.cuts.values()
    v = corners(a, "slot_2")
    finger = corners(b, "slot_3")
    width_label = "finger_width/finger_count\n(provide one or the other)"
    if splice:
        mid1, mid2 = (finger[0] + finger[3]) / 2, (finger[1] + finger[2]) / 2
        root, tip = v[1], v[2]
        square = tip.copy()
        square[1] = root[1]
        p.view(
            "Finger pitch at mid-length",
            a,
            PLAN,
            (0, 0, 0),
            Span(width_label, mid1, mid2, inline=True),
            Span("finger_length", root, square),
            width=BOARD_DETAIL,
        )
        view, project = p.view("Taper at the flank", b, PLAN, (0, 0, 0), width=BOARD_DETAIL)
        # The corresponding slot on the second member is the finger on the first.
        t = finger
        q = t[0].copy()
        q[0] = t[3][0]
        annotate_plan_angle(view, "taper_angle", project(t[0]), project(q), project(t[3]), (365, 60))
    else:
        p.view(
            "First board",
            a,
            FRONT_LEFT,
            (0, 0, 0),
            Span(width_label, (finger[4] + finger[7]) / 2, (finger[5] + finger[6]) / 2, inline=True),
            width=BOARD_DETAIL,
        )
        w = finger
        p.view(
            "Mating board",
            b,
            FRONT_LEFT,
            (0, 0, 0),
            Span("mating board thickness", w[5], w[1]),
            width=BOARD_DETAIL,
        )


def wedged(p):
    a, b = p.cuts.values()
    v = corners(a, "tenon")
    p.assembly((0, 0, 0), width=OVERVIEW)
    p.view(
        "Flared tenon",
        a,
        BACK_RIGHT,
        (0, 0, 0),
        Span("tenon_depth", v[2], v[1]),
        Span("tenon_size[0]", v[1], v[5]),
        Span("tenon_size[1]", v[2], v[3]),
    )
    w = corners(b, "mortise_hole")
    widened = w[3].copy()
    widened[0] = w[0][0]
    p.view("Mortise flare", b, FRONT_LEFT, (0, 0, 0), Span("dovetail_depth", w[3], widened), xray=True)
    wedge = p.accessories["wedge"]
    points = accessory_points(wedge)
    view, project = p.view(
        "Loose wedge · plan",
        wedge,
        PLAN,
        (points[0] + points[2]) / 2,
        Span("wedge tip width", points[2], points[3]),
    )
    reference = points[1] + points[3] - points[0]
    annotate_plan_angle(view, "wedge_angle", project(points[1]), project(reference), project(points[2]), (398, 87))


def tusked(p):
    a, b = p.cuts.values()
    v = corners(a, "tenon")
    p.assembly((0, 0.065, 0), width=OVERVIEW)
    p.view(
        "Projecting tenon",
        a,
        BACK_RIGHT,
        (0, 0.06, 0),
        Span("tenon_width_relative_to_joint", v[7], v[4]),
        Span("tenon_height_relative_to_joint", v[4], v[5]),
    )
    w = corners(a, "tusk_hole")
    cheek = plane_of(primitive_features(a, node(a, "tenon"))["tenon_right"])
    hole = [foot_on_plane(w[i], cheek) for i in (0, 4)]
    p.view(
        "Projection beyond receiver",
        a,
        PLAN,
        (0, 0.11, 0),
        axis_span("tenon_length_past_opposite_shoulder", v[4], stock_plane(b, "back")),
        Span("tusk_thickness", *hole),
    )
    tusk = p.accessories["tusk"]
    v = accessory_points(tusk)
    exit_cheek = plane_of(primitive_features(a, node(a, "tenon"))["tenon_left"])
    tip = axis_span("tusk_tip_stickout", v[2], exit_cheek)
    sloping_edge = Line(create_v3(*(v[1] - v[2])), create_v3(*v[2]))
    width_end = crossing(sloping_edge, exit_cheek)
    width_start = foot_on_plane(v[3], exit_cheek)
    view, project = p.view(
        "Loose tusk · side",
        tusk,
        END,
        (v[0] + v[2]) / 2,
        tip,
        Span("tusk_small_width", width_start, width_end, inline=True),
    )
    annotate_plan_angle(view, "tusk_angle", project(v[1]), project(v[1] + v[3] - v[0]), project(v[2]), (399, 87))


def rice(p):
    post, rail, receiver = p.cuts.values()
    p.assembly((0.05, 0.05, -0.05))
    u = corners(post, "long_tenon")
    short = corners(post, "short_tenon")
    p.view(
        "Post tenons",
        post,
        BACK_RIGHT,
        (0.05, 0.05, -0.04),
        Span("tenon_size[0]", u[1], u[0]),
        Span("tenon_size[1]", u[0], u[3]),
        Span("tenon_size[0]", short[0], short[3]),
        Span("tenon_size[1]", short[0], short[1]),
    )
    v = corners(rail, "rail_tenon")
    # The rail inset is measured down from the top of the joint.
    top = next(
        stock_plane(rail, s)
        for s in ("right", "left", "front", "back")
        if as_ndarray(stock_plane(rail, s).normal)[2] > 0.99
    )
    p.view(
        "Rail tenon",
        rail,
        FRONT_RIGHT,
        (0.065, 0.025, -0.05),
        axis_span("timber_2_tenon_distance_from_outer_face", v[0], top),
    )
    # In plan the post shows the outside faces used to lay out its tenons.
    outside = next(
        stock_plane(post, s)
        for s in ("right", "left", "front", "back")
        if as_ndarray(stock_plane(post, s).normal)[0] < -0.99
    )
    cheek = corners(post, "x_cheek")
    p.view(
        "Post layout · plan",
        post,
        PLAN,
        (0.05, 0.05, 0),
        axis_span("timber_1_tenon_distance_from_outer_faces", u[3], outside),
        Span("timber1_miter_thickness", cheek[0], cheek[1]),
    )


def splined(p, *, stubs=False):
    r, a, b = p.cuts.values()
    p.assembly((0, 0, 0), width=OVERVIEW)
    v = corners(a, "spline_slot")
    slot_depth = Span("slot_depth", v[0], v[3])
    if not stubs:
        # Project the slot onto the shoulder at the open end of the butt timber.
        shoulder = stock_plane(r, "front")
        slot_depth = Span("slot_depth", foot_on_plane(v[0], shoulder), foot_on_plane(v[3], shoulder), inline=True)
    p.view(
        "Spline slot in butt timber",
        a,
        BACK_RIGHT,
        (0, -0.17, 0),
        slot_depth,
        Span("slot_thickness", v[0], v[1]),
        width=OVERVIEW,
    )
    if stubs:
        t = corners(a, "stubby_tenon_0")
        p.view(
            "First stub tenon",
            a,
            BACK_RIGHT,
            (0, -0.072, 0),
            Span("length", t[0], t[4]),
            Span("size[0]", t[0], t[1]),
            Span("size[1]", t[0], t[3]),
        )
        m = corners(r, "stubby_mortise_butt_timber_1_0")
        p.view(
            "Stub mortises",
            r,
            FRONT_LEFT,
            (0, -0.05, 0),
            Span("length + mortise_extra_depth", m[3], m[7]),
            xray=True,
        )
    else:
        spline = p.accessories["spline"]
        xyz = accessory_points(spline)
        p.view(
            "Loose spline",
            spline,
            BACK_RIGHT,
            (xyz[0] + xyz[6]) / 2,
            Span("spline_length", xyz[0], xyz[4]),
            width=OVERVIEW,
        )
        # Show the receiver's actual section at its entry face.
        w = corners(r, "spline_slot")
        entry = stock_plane(r, "front")
        left, right = [foot_on_plane(w[i], entry) for i in (0, 3)]
        p.view(
            "Receiver slot section",
            r,
            FRONT_LEFT,
            (0.04, -0.05, 0),
            Span("slot_depth + spline_extra_depth", left, right),
        )


def fork_butt(p):
    a, b = p.cuts.values()
    slot = node(b, "fork_slot")
    fs = primitive_features(b, slot)
    # The two planes normal to Z bound the tongue slot through the end of the fork.
    planes = [
        plane_of(h)
        for h in fs.values()
        if h.feature.name.startswith("side.") and abs(as_ndarray(plane_of(h).normal)[2]) > 0.99
    ]
    pts = [
        foot_on_plane(np.array([float(b.timber.size[1]) / 2, -float(a.timber.size[1]) / 2, 0]), f) for f in planes
    ]
    p.view("Receiving tongue", a, FRONT_LEFT, (0, 0, 0), Span("tongue_thickness", *pts))
    p.view(
        "Mating fork",
        b,
        BACK_RIGHT,
        (0, 0, 0),
        axis_span(
            "(stock thickness − tongue_thickness) / 2", max(pts, key=lambda pt: pt[2]), stock_plane(b, "right")
        ),
    )


def angled_tenon(p, *, corner=False, round_profile=False):
    a, b = p.cuts.values()
    axis = as_ndarray(a.timber.get_face_direction_global(TimberEnd.BOTTOM))
    shoulder = plane_of(primitive_features(a, node(a, "shoulder"))["shoulder"])
    if round_profile:
        n = node(a, "tenon")
        center = as_ndarray(a.timber.transform.local_to_global(n.position))
        tip = center + axis * float(n.end_distance)
        across = as_ndarray(a.timber.get_width_direction_global()) * float(n.radius)
        profile = [Span("diameter", tip - across, tip + across)]
    else:
        v = corners(a, "tenon")
        tip = (v[4] + v[6]) / 2
        center = crossing(Line(create_v3(*axis), create_v3(*tip)), shoulder)
        if corner:
            profile = [
                Span("tenon_height_relative_to_joint", v[4], v[5]),
                Span("tenon_width_relative_to_joint", v[5], v[6]),
            ]
        else:
            # These two edges meet at the forward, upper corner of the tenon tip.
            profile = [Span("tenon_size[0]", v[4], v[5]), Span("tenon_size[1]", v[7], v[4])]
    preset = BACK_RIGHT if corner else (1, 2, 1)
    p.view(
        "Tenon and shoulder",
        a,
        FRONT_LEFT if corner else preset,
        (center + tip) / 2,
        *profile,
        Span("tenon_length", center, tip),
    )
    bore = node(b, "mortise_hole")
    if round_profile:
        floor = as_ndarray(
            b.timber.transform.local_to_global(bore.position + bore.end_distance * bore.axis_direction)
        )
    else:
        floor_plane = plane_of(primitive_features(b, bore)["mortise_bottom"])
        floor = crossing(Line(create_v3(*axis), create_v3(*center)), floor_plane)
    p.view(
        "Mortise along insertion axis",
        b,
        preset,
        (center + floor) / 2,
        Span("mortise_depth", center, floor),
        xray=True,
    )


def board_dovetails(p, *, blind=False):
    a, b = p.cuts.values()
    v = corners(a, "dovetails", only_child=True)
    w = corners(b, "dovetail_sockets", only_child=True)
    neck, tip = v[0], v[3]
    square = tip.copy()
    square[2] = neck[2]
    view, project = p.view("Tail layout", a, END, (neck + v[2]) / 2, Span("dovetails[0].small_width", v[0], v[1]))
    annotate_plan_angle(view, "dovetails[0].angle", project(neck), project(square), project(tip), (396, 55))
    spans = []
    if blind:
        socket_floor = w[7]
        end_face = socket_floor + ((w[4] + w[5]) - (w[6] + w[7])) / 2
        spans.append(Span("dovetails[0].depth", end_face, socket_floor, inline=True))
    p.view("Blind socket" if blind else "Through socket", b, FRONT_LEFT, (w[0] + w[6]) / 2, *spans)


def board_edge(p):
    a, b = p.cuts.values()
    v = corners(a, "tongue_top_remove")
    w = corners(b, "groove")
    p.view("Tongue at board end", a, (1, 1, -1), v[3], Span("tongue_depth", v[2], v[3]), width=BOARD_DETAIL)
    p.view(
        "Groove at board end",
        b,
        (-1, 1, -1),
        w[1],
        Span("tongue_width", w[0], w[3]),
        Span("tongue_depth + groove_extra_depth", w[1], w[0]),
        width=BOARD_DETAIL,
    )


def sliding(p):
    a, b = p.cuts.values()
    v = corners(a, "dovetail_tongue_profile")
    w = corners(b, "dovetail_housing")
    opening = max(
        TimberLongFace, key=lambda face: as_ndarray(b.timber.get_face_direction_global(face)) @ (w[5] - w[1])
    )
    end_face = Plane(
        b.timber.get_face_direction_global(opening), get_center_point_on_face_global(opening, b.timber)
    )
    lip = [foot_on_plane(w[i], end_face) for i in (1, 2)]
    base = (v[0] + v[3]) / 2
    tip = (v[1] + v[2]) / 2
    p.view(
        "Sliding tongue · end",
        a,
        (-1, -1, 1),
        base,
        Span("dovetail_small_width", v[0], v[3]),
        Span("dovetail_depth", base, tip),
        width=BOARD_DETAIL,
    )
    p.view(
        "Sliding housing",
        b,
        BACK_RIGHT,
        np.mean(lip, axis=0),
        Span("dovetail_small_width + 2 × dovetail_depth × cos(dovetail_angle)", *lip, offset=0),
        width=BOARD_DETAIL,
    )


def decoration(p, kind):
    (a,) = p.cuts.values()
    end = as_ndarray(
        a.timber.get_bottom_position_global() + a.timber.length * a.timber.get_length_direction_global()
    )
    if kind == "rounded-end":
        cyl = node(a, "rounded_end_arc")
        center = as_ndarray(a.timber.transform.local_to_global(cyl.position))
        center[0] += float(a.timber.size[0]) / 2
        dims = [
            Span("radius", center, center + [0, float(cyl.radius), 0]),
            Span("distance_from_end", center, center + [0, 0, end[2] - center[2]]),
        ]
    else:
        cyl = node(a, "scallop_arc")
        c = as_ndarray(a.timber.transform.local_to_global(cyl.position))
        outer = -float(a.timber.size[1]) / 2
        radius = float(cyl.radius)
        height = c[1] + radius - outer
        length = np.sqrt(radius**2 - (outer - c[1]) ** 2)
        center = np.array([float(a.timber.size[0]) / 2, outer, end[2]])
        dims = [
            Span("scallop_height", center, center + [0, height, 0]),
            Span("scallop_length", center, center - [0, 0, length]),
        ]
    p.view("Finished end", a, FRONT_RIGHT, end - [0, 0, 0.05], width=FIELD_WIDTH, mesh_outline=True)
    focus = (dims[1].end + center) / 2 if kind == "scallop" else center
    p.view("Profile", a, END, focus, *dims, mesh_outline=True)


def accessory_points(accessory):
    body = accessory.get_csg_local()
    if hasattr(body, "base"):
        body = body.base
    return {
        int(f.name[7:]): as_ndarray(accessory.transform.local_to_global(f.locate_simple_unbounded(body).position))
        for f in body.get_declared_features()
        if f.name.startswith("corner.")
    }


def free_dovetail(p, *, tapered=False):
    post, beam = p.cuts.values()
    v = corners(post, "dovetail")
    back, front = (v[0] + v[1]) / 2, (v[4] + v[5]) / 2
    post_axis = Line(post.timber.get_length_direction_global(), post.timber.get_bottom_position_global())
    neck_plane = Plane(post.timber.get_length_direction_global(), create_v3(*back))
    center = crossing(post_axis, neck_plane)
    fraction = ((center - back) @ (front - back)) / np.dot(front - back, front - back)
    mid_left, mid_right = (v[i] + fraction * (v[i + 4] - v[i]) for i in (0, 1))
    depth = (v[2] + v[3]) / 2
    view, project = p.view(
        "Tongue section", post, SIDE, center, Span("depth", back, depth), Span("width", mid_left, mid_right)
    )
    square = v[1] + (depth - back)
    annotate_plan_angle(view, "dovetail_angle", project(v[1]), project(square), project(v[2]), (394, 108))
    view, project = p.view("Dovetail socket", beam, FRONT_RIGHT, center, width=FIELD_WIDTH)
    if tapered:
        ref = v[1] + (front - back)
        annotate_plan_angle(
            view,
            "taper_angle",
            v[1][:2],
            ref[:2],
            v[5][:2],
            (414, 91),
            project=lambda xy: project(np.append(xy, v[1][2])),
        )


def grooved_frame(p):
    rail = p.cuts["bottom_rail"]
    v = corners(rail, "board_groove")
    p.assembly((v[0] + v[6]) / 2, SIDE, width=1.8)
    # A groove follows the envelope of the inserted boards.
    floor = (v[0] + v[1]) / 2
    front = (v[2] + v[3]) / 2
    inside = next(
        stock_plane(rail, s)
        for s in ("right", "left", "front", "back")
        if as_ndarray(stock_plane(rail, s).normal)[2] > 0.99
    )
    p.view(
        "Groove in bottom rail",
        rail,
        FRONT_RIGHT,
        floor,
        Span("board_thickness", foot_on_plane(floor, inside), foot_on_plane(front, inside), inline=True),
        axis_span("groove_depth", floor, inside),
        width=BOARD_DETAIL,
    )


# Each entry names the basic pattern, the plate filename and the layout used for it.
CATALOG = [
    (
        basic.example_basic_practice_simplified_rice_dumping_joint,
        "rice-dumpling",
        "Three-way mitered tenon",
        rice,
        4,
    ),
    (basic.example_basic_miter_joint, "angled-miter", "Angled miter", partial(plain, miter=True), 1),
    (
        basic.example_basic_miter_joint_face_aligned,
        "right-angle-miter",
        "Right-angle miter",
        partial(plain, miter=True),
        1,
    ),
    (basic.example_basic_butt_joint, "plain-butt", "Face-aligned butt joint", plain, 1),
    (basic.basic_plain_butt_angled, "angled-butt", "Angled butt joint", partial(plain, brace=True), 1),
    (basic.example_basic_butt_splice_joint, "butt-splice", "Butt splice", plain, 1),
    (basic.basic_finger_corner, "finger-corner", "Box corner", fingers, 2),
    (basic.basic_finger_splice, "finger-splice", "Tapered finger splice", partial(fingers, splice=True), 2),
    (basic.example_basic_cross_lap_joint, "cross-lap", "Cross lap", cross_lap, 2),
    (basic.example_basic_house_joint, "cross-lap-house", "Cross-lap housing", partial(cross_lap, house=True), 2),
    (basic.basic_corner_lap, "corner-lap", "Corner lap", cross_lap, 2),
    (basic.example_basic_splice_lap_joint, "splice-lap", "Splice lap", splice_lap, 2),
    (
        basic.example_basic_splined_opposing_double_butt_joint,
        "splined-double-butt",
        "Splined opposing double butt",
        splined,
        4,
    ),
    (
        basic.example_basic_splined_opposing_double_butt_joint_with_stubby_tenons,
        "splined-stub-tenons",
        "Splined joint with stub tenons",
        partial(splined, stubs=True),
        4,
    ),
    (
        basic.example_basic_wedged_half_dovetail_mortise_and_tenon_joint,
        "wedged-half-dovetail",
        "Wedged half-dovetail",
        wedged,
        4,
    ),
    (basic.example_basic_dropin_housed_butt_joint, "drop-in-housing", "Drop-in housed butt", housed, 2),
    (basic.example_basic_tusked_mortise_and_tenon_joint, "tusked-tenon", "Tusked through tenon", tusked, 4),
    (basic.basic_tongue_and_fork_butt, "fork-butt", "Tongue-and-fork butt", fork_butt, 2),
    (basic.rectangular_tenon, "angled-tenon", "Angled rectangular tenon", angled_tenon, 2),
    (basic.round_tenon, "angled-round-tenon", "Angled round tenon", partial(angled_tenon, round_profile=True), 2),
    (basic.corner_tenon, "corner-tenon", "Corner mortise and tenon", partial(angled_tenon, corner=True), 2),
    (basic.dovetail_corner, "through-dovetails", "Through dovetail corner", board_dovetails, 2),
    (
        basic.half_blind_dovetail_corner,
        "half-blind-dovetails",
        "Half-blind dovetail corner",
        partial(board_dovetails, blind=True),
        2,
    ),
    (basic.tongue_and_groove, "tongue-and-groove", "Tongue and groove", board_edge, 2),
    (basic.sliding_dovetail, "sliding-dovetail", "Sliding dovetail", sliding, 2),
    (basic.rounded_end, "rounded-end", "Rounded end", partial(decoration, kind="rounded-end"), 2),
    (example_free_sliding_dovetail, "free-sliding-dovetail", "Free sliding dovetail", free_dovetail, 2),
    (
        example_free_tapered_dovetail,
        "free-tapered-dovetail",
        "Free tapered dovetail",
        partial(free_dovetail, tapered=True),
        2,
    ),
    (example_board_in_grooved_frame, "grooved-frame", "Board in a grooved frame", grooved_frame, 2),
    (basic.rafter_tail, "rafter-scallop", "Rafter tail scallop", partial(decoration, kind="scallop"), 2),
]


def render_entry(entry):
    pattern, filename, title, layout, panels = entry
    plate = Plate(pattern(), title, panels)
    layout(plate)
    if plate.slot != panels:
        raise ValueError(f"{title} has an empty panel")
    save(plate.root, filename + ".svg")
