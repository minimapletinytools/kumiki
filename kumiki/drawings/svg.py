"""Orthographic SVG viewports of finished CSG solids and their drawing references."""

from __future__ import annotations

from dataclasses import dataclass
import math
from xml.etree import ElementTree as ET

import numpy as np

from ..csg.curves import EllipseArc, angular_roots
from ..measuring import locate_face
from ..rule import as_ndarray
from ..timber_features import TimberFeature, TimberLongFace
from ..viewer.picking import perfect_reference_outlines
from .drawing_solid import DrawingSolid
from .projected_faces import ProjectedFaces
from .reference_lines import timber_reference_lines


@dataclass(frozen=True)
class DrawingStyles:
    centerlines: bool = True
    perfect_faces: bool = True
    references: bool = True
    reference_faces: bool = False


def _xy(point):
    return f'{point[0]:.8g} {point[1]:.8g}'


class _Viewport:
    def __init__(self, camera, width, height):
        right, up = np.array(camera['right']), np.array(camera['up'])
        self.axes = np.stack((right, -up, np.cross(right, up)), axis=1)
        self.center = np.array(camera['center'])
        self.scale = np.array([width / camera['width'], height / camera['height']])
        self.origin = np.array([width, height]) / 2

    def world(self, points):
        return (points - self.center) @ self.axes

    def paper(self, point):
        return self.origin + point[:2] * self.scale


def _arc_path(view, arc, start, stop):
    axes = np.column_stack((arc.u[:2], arc.v[:2])) * view.scale[:, None]
    directions, radii, _ = np.linalg.svd(axes)
    rotation = math.degrees(math.atan2(directions[1, 0], directions[0, 0]))
    sweep = int(np.linalg.det(axes) * (stop - start) > 0)
    path = 'M' + _xy(view.paper(arc.point(start)))
    if radii[1] < 1e-7:
        component = int(np.argmax(np.hypot(arc.u[:2], arc.v[:2])))
        turns = angular_roots(arc.v[component], -arc.u[component], 0, start, stop)
        return path + ''.join(' L' + _xy(view.paper(arc.point(t))) for t in [*turns, stop])
    # Two arcs also describe a full circle, whose endpoints coincide.
    n = max(1, math.ceil(abs(stop - start) / math.pi))
    for i in range(1, n + 1):
        end = view.paper(arc.point(start + (stop - start) * i / n))
        path += f' A{_xy(radii)} {rotation:.8g} 0 {sweep} {_xy(end)}'
    return path


def _visible_angles(arc, occlusion):
    stops = occlusion.arc_breaks(arc)
    start = None
    for a, b in zip(stops, stops[1:]):
        if abs(b - a) < 1e-12:
            continue
        if occlusion.hides(arc.point((a + b) / 2)):
            if start is not None:
                yield start, a
                start = None
        elif start is None:
            start = a
    if start is not None:
        yield start, arc.stop


def _fill_reference_faces(fills, key, solid, timber, view, faces):
    colored = {}
    for ref in timber.ticket.reference_features:
        adjacent = ref.long_faces_it_rests_on()
        if len(adjacent) == 2:
            for face in adjacent:
                colored[face] = '#f4d6c4' if face in (TimberLongFace.RIGHT, TimberLongFace.LEFT) else '#cfdfec'
    for face, color in colored.items():
        plane = locate_face(timber, face)
        normal = as_ndarray(plane.normal)
        if normal @ view.axes[:, 2] <= 1e-8:
            continue
        paths = []
        for _, polygon in solid.polygons:
            world = polygon @ solid.rotation.T + solid.origin
            if np.max(np.abs((world - as_ndarray(plane.point)) @ normal)) > 1e-7:
                continue
            for region in faces.visible_region(view.world(world)):
                paths.append('M' + ' L'.join(_xy(view.paper(p)) for p in region) + ' Z')
        if paths:
            ET.SubElement(fills, 'path', {'data-member': key, 'data-feature': face.name,
                                           'fill': color, 'd': ' '.join(paths)})


def _reference_overlays(timber, solid, styles, view):
    for center, enabled in [(False, styles.perfect_faces), (True, styles.centerlines)]:
        if enabled:
            for outline in perfect_reference_outlines(timber, solid.root, center):
                if abs(np.dot(outline.normal, view.axes[:, 2])) < 1 - 1e-3:
                    yield ('centerplane' if center else 'perfect-face', '#d0582f' if center else '#2f6fd0',
                            outline.positions, True, True)
    if styles.centerlines:
        axis = timber_reference_lines(timber, solid.root, [TimberFeature.CENTERLINE])[0]
        yield 'centerline', '#d0582f', axis['edgePositions'], True, True
    if styles.references:
        for refline in timber_reference_lines(timber, solid.root):
            yield (refline['name'], '#c0392b' if refline['primary'] else '#e57373',
                    refline['edgePositions'], False, refline['name'] == 'centerline')


def render_svg_view(members: dict[str, DrawingSolid], ghosts: set[str], camera: dict,
                    width: float, height: float, styles: DrawingStyles = DrawingStyles()) -> ET.Element:
    """Return SVG content for one orthographic viewport, with its live camera dimensions in metres."""
    view = _Viewport(camera, width, height)
    svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg', 'viewBox': f'0 0 {width} {height}'})
    fills = ET.SubElement(svg, 'g', {'class': 'face-fills'})
    segments = ET.SubElement(svg, 'g', {'class': 'edges', 'fill': 'none', 'stroke-linejoin': 'round'})
    overlays = ET.SubElement(svg, 'g', {'class': 'references', 'fill': 'none'})
    triangles, ids = [], []
    for index, (key, solid) in enumerate(members.items()):
        if key not in ghosts:
            triangles.extend(view.world(solid.triangles @ solid.rotation.T + solid.origin))
            ids.extend([index] * len(solid.triangles))
    faces = ProjectedFaces(np.asarray(triangles).reshape(-1, 3, 3), np.asarray(ids))
    for index, (key, solid) in enumerate(members.items()):
        ghost = key in ghosts
        basis = solid.rotation.T @ view.axes
        origin = view.world(solid.origin)
        def project(p):
            return p @ basis + origin

        group = ET.SubElement(segments, 'g', {'data-member': key, 'stroke': '#b6bdc4' if ghost else '#252a30'})
        occlusion = faces
        if ghost:
            own = project(solid.triangles)
            occlusion = ProjectedFaces(np.concatenate([faces.triangles, own]),
                                       np.concatenate([faces.members, np.full(len(own), index)]))
        def stroke(parent, name, a, b, ignore=-1):
            parts = ['M' + _xy(view.paper(p)) + ' L' + _xy(view.paper(q))
                     for p, q in occlusion.line(a, b, ignore) if np.linalg.norm(view.paper(q) - view.paper(p)) > .001]
            if parts:
                ET.SubElement(parent, 'path', {'data-feature': name, 'd': ' '.join(parts)})

        for name, a, b in solid.lines:
            stroke(group, name, project(a), project(b))
        for name, a, b in solid.generators(basis[:, 2]):
            stroke(group, name, project(a), project(b))
        drawn_arcs = set()
        for rim in solid.rims:
            arc = EllipseArc(project(rim.arc.center), rim.arc.u @ basis, rim.arc.v @ basis, rim.start, rim.stop)
            paths = []
            for a, b in _visible_angles(arc, occlusion):
                path = _arc_path(view, arc, a, b)
                if path not in drawn_arcs:
                    paths.append(path)
                    drawn_arcs.add(path)
            if paths:
                attrs = {'data-feature': rim.name, 'd': ' '.join(paths)}
                if rim.owner.label.name:
                    attrs['data-source'] = rim.owner.label.name
                ET.SubElement(group, 'path', attrs)
        timber = solid.timber
        if timber is None or ghost:
            continue
        if styles.reference_faces:
            _fill_reference_faces(fills, key, solid, timber, view, faces)
        for name, color, positions, dashed, through in _reference_overlays(timber, solid, styles, view):
            lines = ET.SubElement(overlays, 'g', {'data-member': key, 'class': name, 'stroke': color,
                                                  'stroke-width': '1.5'})
            if dashed:
                lines.set('stroke-dasharray', '5 3')
            for a, b in np.array(positions).reshape(-1, 2, 3):
                stroke(lines, name, view.world(a), view.world(b), index if through else -1)
    return svg


def render_svg_sheet(members: dict[str, DrawingSolid], sheet: dict) -> str:
    """Compose the fitted sheet in physical millimetres from the viewer's printable snapshot."""
    page, paper = sheet['page'], sheet['paper']
    w, h = page['width'], page['height']
    root = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg', 'width': f"{1000 * paper['width']:.8g}mm",
                              'height': f"{1000 * paper['height']:.8g}mm", 'viewBox': f'0 0 {w} {h}'})
    ET.SubElement(root, 'rect', width='100%', height='100%', fill='white')
    styles = DrawingStyles(**sheet['styles'])
    for pane in sheet['views']:
        x, y, width, height = pane['rect']
        rect = dict(x=str(x * w), y=str(y * h), width=str(width * w), height=str(height * h))
        if 'image' in pane:
            if not pane['image'].startswith('data:image/png;base64,'):
                raise ValueError('A perspective preview must be an embedded PNG')
            element = ET.SubElement(root, 'image', href=pane['image'], preserveAspectRatio='none')
        else:
            element = render_svg_view(members, set(sheet['ghosts']), pane['camera'], width * w, height * h, styles)
            root.append(element)
        element.attrib.update(rect)
        element.set('data-viewport', str(pane['id']))
    overlay = ET.fromstring(sheet['dimensions'])
    # Only printable geometry and text from the live measurement overlay belong in the exported page.
    for node in overlay.iter():
        node.tag = node.tag.rsplit('}', 1)[-1]
        if node.tag not in {'svg', 'g', 'line', 'text', 'path'}:
            raise ValueError('Unexpected element in measurement overlay')
        node.attrib = {key: val for key, val in node.attrib.items() if key in {
            'viewBox', 'x', 'y', 'width', 'height', 'x1', 'x2', 'y1', 'y2', 'transform', 'd',
            'class', 'style', 'fill', 'stroke'} and 'url(' not in val.lower()}
    overlay.set('x', str(-page['x']))
    overlay.set('y', str(-page['y']))
    overlay.set('id', 'measurements')
    root.append(overlay)
    return ET.tostring(root, encoding='unicode')
