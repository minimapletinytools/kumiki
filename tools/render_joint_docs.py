"""Render the pilot joint reference figures. Run with python -m tools.render_joint_docs."""

from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from kumiki import CutTimber, Frame, Measure, create_v3
from kumiki.csg.cutcsg import HalfSpace, Intersection
from kumiki.csg.feature_paths import find_feature
from kumiki.drawings.kigumi_measuring_helpers import world_geometry
from kumiki.drawings.svg import DrawingSolid, render_svg_view
from kumiki.geometry import Plane
from kumiki.rule import as_ndarray, format_length
from patterns.basic_joints_patterns import example_basic_mortise_and_tenon_joint, example_basic_tongue_and_fork_joint


OUT = Path(__file__).resolve().parents[1] / "docs/assets/joint-drawings"
# Both basic patterns use the canonical 4 × 5 × 48 inch timbers. All detail windows use the same scale.
WIDTH, HEIGHT = 560, 380
FIELD_WIDTH = 0.34
BACK_RIGHT = (1, 1, 1)
FRONT_LEFT = (-1, -1, 1)
STOCK = ("timber (rough, extended)",)


def face(cut, path, name):
    """Return the named face on this pattern's cut timber."""
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


def annotate(view, measure, ends, project, offset, caption_at=None):
    """Draw the true edge length with witness lines offset in sheet pixels."""
    a, b = sorted((project(end) for end in ends), key=lambda pt: (round(pt[0], 4), -pt[1]))
    run = b - a
    along = run / np.linalg.norm(run)
    normal = np.array([along[1], -along[0]])
    group = ET.SubElement(view, 'g', fill='#244f6b', stroke='#244f6b')

    def line(p, q):
        ET.SubElement(group, 'line', x1=f'{p[0]:.2f}', y1=f'{p[1]:.2f}', x2=f'{q[0]:.2f}', y2=f'{q[1]:.2f}')

    for p in (a, b):
        line(p + np.sign(offset) * 3 * normal, p + (offset + np.sign(offset) * 4) * normal)
        tick = 3 * (along + normal)
        line(p + offset * normal - tick, p + offset * normal + tick)
    line(a + offset * normal, b + offset * normal)
    angle = np.degrees(np.arctan2(run[1], run[0]))
    x, y = (a + b) / 2 + (offset + 5) * normal
    if caption_at is not None:
        x, y = caption_at
        angle = 0
        line((a + b) / 2 + offset * normal, np.array([x, y - 15]))
    text = ET.SubElement(group, 'text', transform=f'translate({x:.2f} {y:.2f}) rotate({angle:.2f})',
                         attrib={'text-anchor': 'middle', 'font-size': '15', 'stroke': 'white',
                                 'stroke-width': '4', 'paint-order': 'stroke', 'stroke-linejoin': 'round'})
    text.text = measure.format_label(format_length(float(np.linalg.norm(ends[1] - ends[0]))))


def panel(sheet, slot, title, cut: CutTimber, preset, center, dimensions, *, section=False):
    """Draw a cut member at a preset isometric angle, optionally sectioned through world X = 0."""
    transform = cut.timber.transform
    root = cut.render_timber_with_cuts_csg_local()
    if section:
        # Keep the half beyond the center of the socket, exposing its floor and entry.
        inward = transform.global_to_local_direction(create_v3(1, 0, 0))
        on_plane = transform.global_to_local(create_v3(0, 0, 0))
        root = Intersection(root, HalfSpace(normal=inward, offset=inward.dot(on_plane)))
    solid = DrawingSolid(root, transform)
    toward = np.array(preset) / np.linalg.norm(preset)
    right = np.cross([0, 0, 1], toward)
    right /= np.linalg.norm(right)
    up = np.cross(toward, right)
    camera = dict(center=center, right=right, up=up, width=FIELD_WIDTH, height=FIELD_WIDTH * HEIGHT / WIDTH)
    appearance = dict(surface='#f0dfbf', edge='#5d4b36', opacity=1, edgeOpacity=1, width=1.5)
    view = render_svg_view({title: solid}, set(), camera, WIDTH, HEIGHT, appearances={title: appearance})
    view.attrib.update(x=str(slot * WIDTH), y='47', width=str(WIDTH), height=str(HEIGHT), overflow='hidden')
    sheet.append(view)

    def project(point):
        return np.array([WIDTH / 2, HEIGHT / 2]) + (point - center) @ np.stack([right, -up], axis=1) * WIDTH / FIELD_WIDTH

    for measure, offset, caption_at in dimensions:
        annotate(view, measure, dimension_edge(solid, measure, toward), project, offset, caption_at)
    ET.SubElement(sheet, 'text', x=str(slot * WIDTH + 19), y='31', fill='#463a2c',
                  attrib={'font-size': '20', 'font-weight': '600'}).text = title


def sheet(title, description):
    root = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', viewBox=f'0 0 {2*WIDTH} {HEIGHT+48}',
                      attrib={'font-family': 'system-ui, sans-serif', 'role': 'img'})
    ET.SubElement(root, 'title').text = title
    ET.SubElement(root, 'desc').text = description
    ET.SubElement(root, 'rect', width='100%', height='100%', fill='white')
    return root


def save(root, name):
    ET.SubElement(root, 'path', d=f'M0 46H{2*WIDTH} M{WIDTH} 0v{HEIGHT+48}', stroke='#d1c8b8')
    ET.indent(root)
    ET.ElementTree(root).write(OUT / name, encoding='utf-8', xml_declaration=True)


def mortise_and_tenon(joint):
    frame = Frame.from_joints([joint])
    cuts = {ct.timber.ticket.path: ct for ct in frame.cut_timbers}
    tenon, socket = cuts['butt_timber'], cuts['receiving_timber']
    waste = ('tenon_waste',)

    def cheek(name):
        return face(tenon, (*waste, 'tenon'), 'tenon_' + name)

    root = sheet('Stopped mortise and tenon', 'Tenon dimensions in timber-local axes and a section through the stopped mortise.')
    panel(root, 0, 'Tenon', tenon, BACK_RIGHT, (0, -0.025, 0), [
        (Measure(cheek('top'), face(tenon, (*waste, 'shoulder'), 'shoulder'), label='tenon_length = {value}'), 25, None),
        (Measure(cheek('right'), cheek('left'), label='tenon_size[0] = {value}'), 26, (196, 338)),
        (Measure(cheek('front'), cheek('back'), label='tenon_size[1] = {value}'), -76, None),
    ])
    panel(root, 1, 'Mortise · center section', socket, FRONT_LEFT, (0.015, -0.01, 0), [
        (Measure(face(socket, STOCK, 'rptw.front'), face(socket, ('mortise_hole',), 'mortise_bottom'),
                 label='mortise_depth = {value}'), 34, None),
    ], section=True)
    return root


def tongue_and_fork(joint):
    frame = Frame.from_joints([joint])
    cuts = {ct.timber.ticket.path: ct for ct in frame.cut_timbers}
    tongue, fork = cuts['timber1'], cuts['timber2']

    def cheek(name):
        return face(tongue, ('tongue_waste', 'tongue'), 'tongue_' + name)

    upper = Measure(face(fork, ('fork_slot',), 'side.3'), face(fork, STOCK, 'rptw.right'),
                    label='(stock thickness − tongue_thickness) / 2')
    lower = Measure(face(fork, ('fork_slot',), 'side.1'), face(fork, STOCK, 'rptw.left'))
    if not np.isclose(np.ptp(face_stations(upper)[1]), np.ptp(face_stations(lower)[1])):
        raise ValueError("The half-thickness formula requires a centered fork slot")

    root = sheet('Tongue-and-fork corner', 'Centered tongue and mating fork. The cheeks divide the remaining stock equally.')
    panel(root, 0, 'Tongue', tongue, FRONT_LEFT, (0, 0.012, 0), [
        (Measure(cheek('front'), cheek('back'), label='tongue_thickness = {value}'), 32, (200, 350)),
    ])
    panel(root, 1, 'Fork · centered tongue', fork, FRONT_LEFT, (0.012, 0, 0), [
        (upper, -28, (270, 356)),
    ])
    return root


if __name__ == '__main__':
    save(mortise_and_tenon(example_basic_mortise_and_tenon_joint()), 'mortise-and-tenon.svg')
    save(tongue_and_fork(example_basic_tongue_and_fork_joint()), 'tongue-and-fork.svg')
