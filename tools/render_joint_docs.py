"""Render the pilot joint reference figures. Run with python -m tools.render_joint_docs."""

from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from kumiki import CutTimber, Frame, Measure, PegShape, create_v2, mm
from kumiki.csg.cutcsg import OwnedFeatureHit, SolidUnion, adopt_csg
from kumiki.csg.feature_paths import FeatureHandle, find_csg_by_labels, find_feature
from kumiki.drawings.kigumi_measuring_helpers import world_geometry
from kumiki.drawings.svg import DrawingSolid, render_svg_view
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.geometry import Line, Plane, Point, intersect_line_plane, intersect_planes
from kumiki.joints.workshop.basic_joints import _basic_peg, _basic_tenon_dimensions
from kumiki.joints.workshop.mixed import cut_mortise_and_tenon_joint
from kumiki.rule import as_ndarray, format_angle, format_length
from patterns.basic_joints_patterns import (
    example_basic_dropin_dovetail_butt_joint,
    example_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint,
    example_basic_lapped_gooseneck_joint,
    example_basic_tongue_and_fork_joint,
)


OUT = Path(__file__).resolve().parents[1] / "docs/assets/joint-drawings"
# All basic patterns use the canonical 4 × 5 × 48 inch timbers.
WIDTH, HEIGHT = 560, 380
FIELD_WIDTH = 0.34
SPLICE_OVERVIEW_WIDTH = 0.60
BACK_RIGHT = (1, 1, 1)
FRONT_LEFT = (-1, -1, 1)
TENON_END = (0, 1, 0)
PLAN = (0, 0, 1)
SIDE = (0, -1, 0)
INK = "#174e8c"
WITNESS = {"stroke": "#2677bc", "stroke-dasharray": "1 3", "stroke-linecap": "round", "stroke-width": "1.45"}
STOCK = ("timber (rough, extended)",)


def feature(cut, path, name):
    """Return the named feature on this pattern's cut timber."""
    handle = find_feature(cut, path, name)
    if handle is None:
        raise ValueError(f"{cut.timber.ticket.path}: missing {path}/{name}")
    return handle


def face_stations(measure):
    """Return the common world normal and the two distances along it, in metres."""
    first, second = (world_geometry(anchor) for anchor in (measure.anchor_a, measure.anchor_b))
    if not isinstance(first, Plane) or not isinstance(second, Plane):
        raise ValueError(f"{measure.label} requires two planes")
    normal = as_ndarray(first.normal)
    if not np.isclose(abs(normal @ as_ndarray(second.normal)), 1):
        raise ValueError(f"{measure.label} requires parallel planes")
    stations = sorted(normal @ as_ndarray(p.point) for p in (first, second))
    return normal, stations


def dimension_edge(solid, measure, toward):
    """Find the nearest finished edge running squarely between the two named faces."""
    normal, stations = face_stations(measure)
    candidates = []
    for _, a, b in solid.lines:
        ends = np.array([a, b]) @ solid.rotation.T + solid.origin
        length = np.linalg.norm(ends[1] - ends[0])
        if (np.allclose(sorted(ends @ normal), stations, atol=1e-7, rtol=0)
                and np.isclose(length, stations[1] - stations[0], atol=1e-7, rtol=0)):
            candidates.append(ends)
    if not candidates:
        raise ValueError(f"No edge spans the faces for {measure.label}")
    return max(candidates, key=lambda ends: ends.mean(axis=0) @ toward)


def line(parent, p, q, style=None):
    ET.SubElement(parent, 'line', attrib=style or {}, x1=f'{p[0]:.2f}', y1=f'{p[1]:.2f}',
                  x2=f'{q[0]:.2f}', y2=f'{q[1]:.2f}')


def annotate(view, measure, ends, project, offset, caption_at=None):
    """Draw the true edge length with witness lines offset in sheet pixels."""
    a, b = sorted((project(end) for end in ends), key=lambda pt: (round(pt[0], 4), -pt[1]))
    run = b - a
    if np.linalg.norm(run) < 1e-6:
        return
    along = run / np.linalg.norm(run)
    normal = np.array([along[1], -along[0]])
    group = ET.SubElement(view, 'g', fill=INK, stroke=INK, attrib={'class': 'dimension', 'stroke-width': '1.3'})

    for p in (a, b):
        line(group, p + np.sign(offset) * 4 * normal, p + (offset + np.sign(offset) * 4) * normal, WITNESS)
        tick = 3 * (along + normal)
        line(group, p + offset * normal - tick, p + offset * normal + tick)
    line(group, a + offset * normal, b + offset * normal)
    angle = np.degrees(np.arctan2(run[1], run[0]))
    x, y = (a + b) / 2 + (offset + 5) * normal
    if caption_at is not None:
        x, y = caption_at
        angle = 0
        bar_center = (a + b) / 2 + offset * normal
        line(group, bar_center, np.array([x, y + 5 if y < bar_center[1] else y - 15]), WITNESS)
    text = ET.SubElement(group, 'text', transform=f'translate({x:.2f} {y:.2f}) rotate({angle:.2f})',
                         attrib={'text-anchor': 'middle', 'font-size': '15', 'stroke': 'white',
                                 'stroke-width': '4', 'paint-order': 'stroke', 'stroke-linejoin': 'round'})
    text.text = measure.format_label(format_length(float(np.linalg.norm(ends[1] - ends[0]))))


def panel(sheet, slot, title, cut: CutTimber, preset, center, dimensions, *, xray=False, up_hint=(0, 0, 1), field_width=FIELD_WIDTH):
    """Draw a cut member at a preset angle with optional X-ray edges."""
    transform = cut.timber.transform
    root = cut.render_timber_with_cuts_csg_local()
    solid = DrawingSolid(root, transform)
    toward = np.array(preset) / np.linalg.norm(preset)
    right = np.cross(up_hint, toward)
    right /= np.linalg.norm(right)
    up = np.cross(toward, right)
    camera = dict(center=center, right=right, up=up, width=field_width, height=field_width * HEIGHT / WIDTH)
    appearance = dict(surface='#f0dfbf', edge='#5d4b36', opacity=0.28 if xray else 1, edgeOpacity=1, width=1.5)
    view = render_svg_view({title: solid}, set(), camera, WIDTH, HEIGHT, appearances={title: appearance},
                           edge_mode='xray' if xray else 'noOverlay')
    row, column = divmod(slot, 2)
    top = row * (HEIGHT + 48)
    view.attrib.update(x=str(column * WIDTH), y=str(top + 47), width=str(WIDTH), height=str(HEIGHT), overflow='hidden')
    sheet.append(view)

    def project(point):
        return np.array([WIDTH / 2, HEIGHT / 2]) + (point - center) @ np.stack([right, -up], axis=1) * WIDTH / field_width

    for measure, offset, caption_at in dimensions:
        annotate(view, measure, dimension_edge(solid, measure, toward), project, offset, caption_at)
    ET.SubElement(sheet, 'text', x=str(column * WIDTH + 19), y=str(top + 31), fill='#463a2c',
                  attrib={'font-size': '20', 'font-weight': '600'}).text = title
    return view, project


def sheet(title, description, rows=1):
    root = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', viewBox=f'0 0 {2*WIDTH} {rows*(HEIGHT+48)}',
                      attrib={'font-family': 'system-ui, sans-serif', 'role': 'img'})
    ET.SubElement(root, 'title').text = title
    ET.SubElement(root, 'desc').text = description
    ET.SubElement(root, 'rect', width='100%', height='100%', fill='white')
    return root


def save(root, name):
    height = int(root.get('viewBox').split()[-1])
    rules = []
    for y in range(0, height, HEIGHT + 48):
        if y:
            rules.append(f'M0 {y}H{2*WIDTH}')
        rules.append(f'M0 {y+46}H{2*WIDTH}')
    rules.append(f'M{WIDTH} 0v{height}')
    ET.SubElement(root, 'path', d=' '.join(rules), stroke='#d1c8b8')
    ET.indent(root)
    ET.ElementTree(root).write(OUT / name, encoding='utf-8', xml_declaration=True)


def pegged_example():
    """Offset the basic pattern's tenon and peg, leaving clearance behind the tip."""
    arrangement = create_canonical_example_butt_joint_timbers()
    size, length, entry_face = _basic_tenon_dimensions(arrangement)
    arrangement, peg = _basic_peg(arrangement, size, length)
    peg = replace(peg, shape=PegShape.ROUND, size=mm(9), peg_positions=[(peg.peg_positions[0][0], mm(26))])
    return cut_mortise_and_tenon_joint(
        arrangement, tenon_size=size, tenon_length=length, tenon_position=create_v2(mm(20), mm(10)),
        mortise_depth=length + mm(16), peg_parameters=peg, set_mortise_shoulder_parallel_to_face=entry_face,
        mortise_shoulder_distance_from_centerline_or_centerplane=arrangement.receiving_timber.get_size_in_face_normal_axis(entry_face) / 2,
    )


def plane_of(handle):
    """Return a named feature's world plane."""
    plane = world_geometry(handle)
    if not isinstance(plane, Plane):
        raise ValueError(f"{handle.feature.name} must locate a plane")
    return plane


def crossing(axis, plane):
    """Return the world point where a layout axis pierces a face."""
    point = intersect_line_plane(axis, plane)
    if point is None:
        raise ValueError("The layout axis must cross the face")
    return as_ndarray(point.position)


def guide(view, project, a, b, color):
    """Draw a dash-dot construction line through two points on the model."""
    p, q = project(a), project(b)
    ET.SubElement(view, 'line', x1=f'{p[0]:.2f}', y1=f'{p[1]:.2f}', x2=f'{q[0]:.2f}', y2=f'{q[1]:.2f}',
                  stroke=color, attrib={'stroke-dasharray': '8 3 2 3', 'stroke-width': '1.4'})


def mortise_and_tenon(joint):
    """Draw the square-shouldered pilot with a round peg in tenon position space."""
    frame = Frame.from_joints([joint])
    cuts = {ct.timber.ticket.path: ct for ct in frame.cut_timbers}
    tenon, socket = cuts['butt_timber'], cuts['receiving_timber']

    pegged = 'peg_0' in joint.jointAccessories
    waste = ('tenon_cut', 'tenon_waste') if pegged else ('tenon_waste',)
    mortise = ('mortise_cut', 'mortise_hole') if pegged else ('mortise_hole',)

    def cheek(name):
        return feature(tenon, (*waste, 'tenon'), 'tenon_' + name)

    tip = cheek('top')
    shoulder = feature(tenon, (*waste, 'shoulder'), 'shoulder')
    floor = feature(socket, mortise, 'mortise_bottom')
    sizes = [Measure(cheek(a), cheek(b), label=f'tenon_size[{i}]')
             for i, (a, b) in enumerate((('right', 'left'), ('front', 'back')))]
    tenon_size = [np.ptp(face_stations(size)[1]) for size in sizes]
    root = sheet('Stopped mortise and tenon', 'End and plan views locate the tenon relative to the stock and show the assembled tip inside the mortise.', rows=2)
    panel(root, 0, 'Tenon', tenon, BACK_RIGHT, (0, -0.025, 0), [
        (Measure(tip, shoulder, label='tenon_length'), 56, None),
        (sizes[0], 26, (196, 338)),
        (sizes[1], -76, None),
    ])
    panel(root, 1, 'Mortise · X-ray', socket, FRONT_LEFT, (0.015, -0.01, 0), [
        (Measure(shoulder, floor, label='mortise_depth'), 34, None),
    ], xray=True)

    names = ('centerplane_left_right', 'centerplane_front_back')
    stock_planes = [feature(tenon, STOCK, 'ptw.' + n) for n in names]
    tenon_planes = [cheek(n) for n in names]
    stock_axis = intersect_planes(*(plane_of(h) for h in stock_planes))
    tenon_axis = intersect_planes(*(plane_of(h) for h in tenon_planes))
    stock_center = crossing(stock_axis, plane_of(tip))
    tenon_center = crossing(tenon_axis, plane_of(tip))
    local_x, local_y = (as_ndarray(plane_of(h).normal) for h in tenon_planes)
    view, project = panel(root, 2, 'Tenon position · end view', tenon, TENON_END, stock_center, [], up_hint=local_y)
    for x, color, label in ((120, '#756a5a', 'Stock center'), (295, '#346979', 'Tenon center')):
        ET.SubElement(view, 'line', x1=str(x), x2=str(x + 30), y1='343', y2='343', stroke=color,
                      attrib={'stroke-dasharray': '8 3 2 3', 'stroke-width': '1.4'})
        ET.SubElement(view, 'text', x=str(x + 36), y='348', fill=color, attrib={'font-size': '15'}).text = label
    for i, direction in enumerate((local_x, local_y)):
        for point, span, color in ((stock_center, tenon.timber.size, '#756a5a'),
                                   (tenon_center, tenon_size, '#346979')):
            radius = float(span[i]) / 2 + 0.008
            guide(view, project, point - radius * direction, point + radius * direction, color)
        foot = tenon_center - direction * ((tenon_center - stock_center) @ direction)
        annotate(view, Measure(stock_planes[i], tenon_planes[i], label=f'tenon_position[{i}]'),
                 [foot, tenon_center], project, (119, -90)[i], ((298, 30), (462, 230))[i])

    title = 'Peg and tip clearance · mortise plan' if pegged else 'Tip clearance · mortise plan'
    view, project = panel(root, 3, title, socket, PLAN, (0, 0, 0), [], xray=True, up_hint=(0, 1, 0))
    mouth_point = crossing(tenon_axis, plane_of(shoulder))
    tip_point = crossing(tenon_axis, plane_of(tip))
    floor_point = crossing(tenon_axis, plane_of(floor))
    half_width = tenon_size[1] / 2
    guide(view, project, tip_point - local_y * half_width, tip_point + local_y * half_width, '#346979')
    guide(view, project, mouth_point, floor_point, '#346979')
    tip_left = project(tip_point - local_y * half_width)
    ET.SubElement(view, 'text', x=f'{tip_left[0] - 8:.2f}', y=f'{tip_left[1] + 5:.2f}', fill='#346979',
                  attrib={'text-anchor': 'end', 'font-size': '15'}).text = 'Tenon tip'
    annotate(view, Measure(tip, floor, label='mortise_depth − tenon_length'), [tip_point, floor_point],
             project, -108, (415, 50))

    if not pegged:
        return root
    bore = feature(socket, ('mortise_cut', 'peg_hole_0'), 'peg_hole_axis')
    bore_axis = world_geometry(bore)
    if not isinstance(bore_axis, Line):
        raise ValueError("The peg layout requires a round bore")
    peg_point = crossing(bore_axis, plane_of(tenon_planes[0]))
    lateral_offset = local_y * ((peg_point - mouth_point) @ local_y)
    annotate(view, Measure(shoulder, bore, label='peg_positions[0][0]'),
             [mouth_point + lateral_offset, peg_point], project, 163, (141, 345))
    annotate(view, Measure(tenon_planes[1], bore, label='peg_positions[0][1]'),
             [peg_point - lateral_offset, peg_point], project, -68, (348, 345))
    return root


def tongue_and_fork(joint):
    frame = Frame.from_joints([joint])
    cuts = {ct.timber.ticket.path: ct for ct in frame.cut_timbers}
    tongue, fork = cuts['timber1'], cuts['timber2']

    def cheek(name):
        return feature(tongue, ('tongue_waste', 'tongue'), 'tongue_' + name)

    upper = Measure(feature(fork, ('fork_slot',), 'side.3'), feature(fork, STOCK, 'rptw.right'),
                    label='(stock thickness − tongue_thickness) / 2')
    lower = Measure(feature(fork, ('fork_slot',), 'side.1'), feature(fork, STOCK, 'rptw.left'))
    if not np.isclose(np.ptp(face_stations(upper)[1]), np.ptp(face_stations(lower)[1])):
        raise ValueError("The half-thickness formula requires a centered fork slot")

    root = sheet('Tongue-and-fork corner', 'Centered tongue and mating fork. The cheeks divide the remaining stock equally.')
    panel(root, 0, 'Tongue', tongue, FRONT_LEFT, (0, 0.012, 0), [
        (Measure(cheek('front'), cheek('back'), label='tongue_thickness'), 32, (200, 350)),
    ])
    panel(root, 1, 'Fork · centered tongue', fork, FRONT_LEFT, (0.012, 0, 0), [
        (upper, -28, (270, 356)),
    ])
    return root


def point_of(handle):
    """Return the world position of a named corner."""
    point = world_geometry(handle)
    if not isinstance(point, Point):
        raise ValueError(f"{handle.feature.name} must locate a point")
    return as_ndarray(point.position)


def corner_span(view, project, start, end, label, offset, caption=None):
    """Dimension a straight span between two profile corners."""
    annotate(view, Measure(start, end, label=label), [point_of(start), point_of(end)], project, offset, caption)


def primitive_features(cut, primitive):
    """Index a timber-local primitive's declared features by name."""
    return {f.name: FeatureHandle(cut.timber, OwnedFeatureHit(f, primitive)) for f in primitive.get_declared_features()}


def foot_on_plane(point, plane):
    """Project a world point squarely onto a plane with a unit normal."""
    n = as_ndarray(plane.normal)
    return point - n * ((point - as_ndarray(plane.point)) @ n)


def gooseneck(joint):
    """Draw the gooseneck profile and its matching socket."""
    cuts = {ct.timber.ticket.path: ct for ct in Frame.from_joints([joint]).cut_timbers}
    tail, socket = cuts['timber2'], cuts['timber1']

    def profile_parts(cut, path):
        profile = find_csg_by_labels(cut.cuts[0].negative_csg, path)
        if not isinstance(profile, SolidUnion) or len(profile.children) != 2:
            raise ValueError("Expected the gooseneck neck rectangle and head trapezoid")
        return [primitive_features(cut, prism) for prism in profile.children]

    neck, head = profile_parts(tail, ('gooseneck_waste', 'gooseneck'))
    socket_neck, _ = profile_parts(socket, ('gooseneck',))
    center = (point_of(neck['corner.4']) + point_of(head['corner.7'])) / 2
    root = sheet('Lapped gooseneck splice', 'Plan of the projecting head and neck alongside the open socket.')
    view, project = panel(root, 0, 'Gooseneck · plan', tail, PLAN, center, [], up_hint=(0, 1, 0))
    corner_span(view, project, neck['corner.4'], head['corner.6'], 'gooseneck_length', 62)
    corner_span(view, project, neck['corner.6'], head['corner.7'], 'gooseneck_head_length', -75, (150, 342))
    corner_span(view, project, head['corner.4'], head['corner.5'], 'gooseneck_large_width', 134)
    socket_center = (point_of(socket_neck['corner.4']) + center) / 2
    view, project = panel(root, 1, 'Receiving socket', socket, BACK_RIGHT, socket_center, [])
    corner_span(view, project, socket_neck['corner.3'], socket_neck['corner.7'], 'gooseneck_depth', 45, (84, 311))
    corner_span(view, project, socket_neck['corner.4'], socket_neck['corner.7'], 'gooseneck_small_width', 50, (226, 85))
    return root


def scarf(joint):
    """Draw the full Kanawa-tsugi profile and the dado at its stub tenon."""
    cuts = {ct.timber.ticket.path: ct for ct in Frame.from_joints([joint]).cut_timbers}
    first, second = cuts['timber1'], cuts['timber2']
    stub = ('scarf_waste', 'stub_tenon')
    ends = [feature(cut, stub, 'stub_tenon_back') for cut in (first, second)]
    # Each stub ends at a dado corner on the scarf midline, half a scarf length from the key.
    front = plane_of(feature(first, STOCK, 'rptw.front'))
    profile_front = intersect_planes(front,
                                     plane_of(feature(first, STOCK, 'ptw.centerplane_left_right')))
    stations = [crossing(profile_front, plane_of(end)) for end in ends]
    center = np.mean(stations, axis=0)
    root = sheet('Kanawa-tsugi scarf', 'Side elevation of the oblique scarf with a detail of the stub tenon and dado.')
    view, project = panel(root, 0, 'Scarf profile', first, SIDE, center, [], field_width=SPLICE_OVERVIEW_WIDTH)
    annotate(view, Measure(*ends, label='scarf_length'), stations, project, -99)
    # The square key seats against the short step between the two oblique lands.
    key = joint.jointAccessories['peg']
    key_faces = primitive_features(first, adopt_csg(key.transform, first.timber.transform, key.get_csg_local()))
    step = intersect_planes(front, plane_of(key_faces['side.2']))
    rebate = Measure(key_faces['side.1'], key_faces['side.3'], label='rebated_shoulder_depth')
    annotate(view, rebate, [crossing(step, plane_of(h)) for h in (rebate.anchor_a, rebate.anchor_b)],
             project, -42, (207, 104))
    detail_center = as_ndarray(plane_of(ends[0]).point)
    panel(root, 1, 'Dado and stub tenon', first, BACK_RIGHT, detail_center, [
        (Measure(feature(first, stub, 'stub_tenon_right'), feature(first, stub, 'stub_tenon_left'),
                 label='stub_tenon_width'), 44, (324, 76)),
        (Measure(ends[0], feature(first, stub, 'side.1'), label='dado_depth'), -41, (179, 321)),
    ])
    return root


def annotate_plan_angle(view, measure, vertex, reference, flank, caption):
    """Draw a plan angle from a reference ray to a flank on the same face."""
    run, side = reference - vertex, flank - vertex
    a, b = run / np.linalg.norm(run), side / np.linalg.norm(side)
    turn = np.arctan2(a[0] * b[1] - a[1] * b[0], a @ b)
    if np.isclose(turn, 0):
        return
    radius = 0.78 * min(np.linalg.norm(run), np.linalg.norm(side))
    start, stop = vertex + radius * a, vertex + radius * b
    arc = (f'M{start[0]:.2f} {start[1]:.2f} A{radius:.2f} {radius:.2f} '
           f'0 0 {int(turn > 0)} {stop[0]:.2f} {stop[1]:.2f}')
    group = ET.SubElement(view, 'g', attrib={'class': 'dimension', 'fill': INK})
    line(group, vertex, reference, WITNESS)
    ET.SubElement(group, 'path', d=arc, fill='none', stroke=INK, attrib={'stroke-width': '1.8'})
    line(group, (start + stop) / 2, (caption[0], caption[1] + 6), WITNESS)
    ET.SubElement(group, 'text', x=str(caption[0]), y=str(caption[1]),
                  attrib={'text-anchor': 'middle', 'font-size': '15'}).text = measure.format_label(format_angle(abs(turn)))


def dovetail(joint):
    """Draw a drop-in dovetail in plan and its open housing in isometric view."""
    cuts = {ct.timber.ticket.path: ct for ct in Frame.from_joints([joint]).cut_timbers}
    tail, socket = cuts['butt_timber'], cuts['receiving_timber']
    profile = ('dovetail_waste', 'dovetail')
    corners = [feature(tail, profile, f'corner.{i}') for i in range(4, 8)]
    root = sheet('Drop-in dovetail', 'Plan of the neck and flared tail beside the recessed housing and socket floor.')
    view, project = panel(root, 0, 'Dovetail · plan', tail, PLAN, (0, 0, 0), [], up_hint=(0, 1, 0))
    corner_span(view, project, corners[0], corners[1], 'dovetail_small_width', -46, (268, 337))
    shoulder, tip = (feature(tail, profile, f) for f in ('side.0', 'dovetail_front'))
    neck = point_of(corners[1])
    square_tip = foot_on_plane(neck, plane_of(tip))
    annotate(view, Measure(shoulder, tip, label='dovetail_length'), [neck, square_tip], project, -82, (446, 308))

    angle = Measure(feature(tail, profile, 'dovetail_right'), feature(tail, STOCK, 'ptw.centerplane_front_back'),
                    label='dovetail_angle')
    annotate_plan_angle(view, angle, project(neck), project(square_tip), project(point_of(corners[2])), (377, 53))

    view, project = panel(root, 1, 'Housing and socket', socket, FRONT_LEFT, (0, -0.025, 0), [
        (Measure(feature(socket, STOCK, 'rptw.right'), feature(socket, ('dovetail',), 'cap.0'),
                 label='dovetail_depth'), -36, (411, 315)),
    ])
    outside = feature(socket, STOCK, 'rptw.front')
    notch = find_feature(socket, ('shoulder_notch_relief',), 'corner.1')
    if notch is not None:
        inner = point_of(notch)
        annotate(view, Measure(outside, notch, label='receiving_timber_shoulder_inset'),
                 [foot_on_plane(inner, plane_of(outside)), inner], project, -36, (150, 285))
    return root


if __name__ == '__main__':
    save(mortise_and_tenon(pegged_example()), 'mortise-and-tenon.svg')
    save(tongue_and_fork(example_basic_tongue_and_fork_joint()), 'tongue-and-fork.svg')
    save(gooseneck(example_basic_lapped_gooseneck_joint()), 'lapped-gooseneck.svg')
    save(scarf(example_basic_half_blind_tenoned_dadoed_rabbeted_scarf_joint()), 'kanawa-tsugi.svg')
    save(dovetail(example_basic_dropin_dovetail_butt_joint()), 'drop-in-dovetail.svg')
