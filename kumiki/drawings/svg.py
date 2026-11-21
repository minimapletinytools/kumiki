"""Orthographic SVG viewports of finished CSG solids and their drawing references."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import math
from xml.etree import ElementTree as ET

import numpy as np

from ..csg.cross_sections import (PolygonRegions, cross_section_outline, cross_section_polygons,
                                  face_cross_section, subtract)
from ..csg.curves import CylindricalPatch, EllipseArc, angular_roots, cylindrical_patches
from ..csg.cutcsg import (ConvexPolygonSimpleLoft, CutCSG, ExtrusionCap, FaceFeature,
                          walk_csg_with_parity)
from ..csg.feature_extent import extents_of
from ..csg.meshcsg import TriangleSolid
from ..csg.pathcsg import ArcSegment, PathExtrusion
from ..geometry import Plane
from ..measuring import locate_face
from ..rule import Transform, as_ndarray, create_v3
from ..timber import PerfectTimberWithin
from ..timber_features import TimberFeature, TimberLongFace
from ..viewer.picking import perfect_reference_outlines
from .reference_lines import timber_reference_lines


@dataclass
class DrawingPlane:
    owner: CutCSG
    name: str
    point: np.ndarray
    normal: np.ndarray


@dataclass
class Rim:
    owner: CutCSG
    name: str
    arc: EllipseArc
    start: float
    stop: float


def _planes(owner: CutCSG):
    features = owner.get_declared_features()
    if isinstance(owner, PathExtrusion):
        # Paths may carry only the face names the author supplied.
        keys = [ExtrusionCap.TOP, ExtrusionCap.BOTTOM, *(owner.side(i) for i in range(len(owner.path.segments)))]
        known = {getattr(feature, "key", None) for feature in features}
        features += [owner.feature(str(key), key) for key in keys if key not in known]
    for face in features:
        if isinstance(face, FaceFeature) and face.real:
            plane = face.locate_simple_unbounded(owner)
            if isinstance(plane, Plane):
                yield face, DrawingPlane(owner, face.name, as_ndarray(plane.point), as_ndarray(plane.normal))


class DrawingSolid:
    """One drawable member's geometry in local metres, shared by every viewport on a sheet."""

    def __init__(self, root: CutCSG, placement: Transform, timber: PerfectTimberWithin | None = None):
        self.root = root
        self.placement = placement
        self.timber = timber
        self.lines: list[tuple[str, np.ndarray, np.ndarray]] = []
        self.patches: list[tuple[CutCSG, CylindricalPatch]] = []
        self.corner_angles: dict[CylindricalPatch, list[float]] = {}
        self.planes: list[DrawingPlane] = []
        self.rims: list[Rim] = []
        self.polygons: list[tuple[DrawingPlane, np.ndarray]] = []
        self.rotation = np.asarray(placement.orientation.matrix.tolist(), dtype=float)
        self.origin = as_ndarray(placement.position)
        bounds = root.get_aabb()
        low = [bounds.min_x, bounds.min_y, bounds.min_z]
        high = [bounds.max_x, bounds.max_y, bounds.max_z]
        mesh = None
        if None in low or None in high:
            from ..csg.triangles import triangulate_cutcsg
            mesh = triangulate_cutcsg(root).mesh
            if len(mesh.faces):
                low, high = mesh.bounds
            else:
                low = high = [0., 0., 0.]
        self.middle = (np.array(low) + np.array(high)) / 2
        self.reach = max(.001, float(np.linalg.norm(np.asarray(high, dtype=float) - np.asarray(low, dtype=float))))
        outlines = []
        unsupported = False
        for owner, _ in walk_csg_with_parity(root):
            patches = list(cylindrical_patches(owner))
            self.patches.extend((owner, patch) for patch in patches)
            if isinstance(owner, PathExtrusion):
                self.corner_angles.update(zip(patches, _profile_corners(owner), strict=True))
            if isinstance(owner, TriangleSolid) or (isinstance(owner, ConvexPolygonSimpleLoft)
                                                     and not owner.is_exactly_convex_hull()):
                unsupported = True
            for feature, plane in _planes(owner):
                self.planes.append(plane)
                if timber is None:
                    section = face_cross_section(feature, owner, root, create_v3(*self.middle), self.reach)
                else:
                    extent = extents_of(root, timber).of(feature, owner)
                    section = extent.cross_section if extent is not None else None
                if section is None:
                    continue
                self.polygons.extend((plane, np.array(poly)) for poly in cross_section_polygons(section))
                outlines.extend((plane, a, b) for a, b in cross_section_outline(section))
        self._add_creases(outlines)
        for owner, patch in self.patches:
            self._add_rims(owner, patch)

        if unsupported or self.patches:
            # Curved walls and imported mesh faces also occlude the projected strokes.
            from ..csg.triangles import triangulate_cutcsg
            if mesh is None:
                mesh = triangulate_cutcsg(root).mesh
            self.triangles = np.array(mesh.triangles)
            if unsupported:
                for pair in mesh.face_adjacency_edges[mesh.face_adjacency_angles > math.radians(1)]:
                    a, b = mesh.vertices[pair]
                    self.lines.append(('surface', a, b))
        else:
            self.triangles = np.asarray([tri for _, polygon in self.polygons
                                         for tri in _fan(polygon)]).reshape(-1, 3, 3)

    def _add_creases(self, outlines):
        """Keep finished face boundaries shared by two distinct planar surfaces."""
        seen = set()
        normals = np.array([p.normal for p in self.planes])
        offsets = np.array([p.normal @ p.point for p in self.planes])
        for plane, a, b in outlines:
            if np.linalg.norm(b - a) < 1e-8:
                continue
            if self.patches:
                on_other = ((np.abs(normals @ a - offsets) < 1e-7) & (np.abs(normals @ b - offsets) < 1e-7)
                            & (np.abs(normals @ plane.normal) < 1 - 1e-8))
                if not np.any(on_other):
                    continue
            key = tuple(sorted((tuple(a.round(9)), tuple(b.round(9)))))
            if key not in seen:
                self.lines.append((plane.name, a, b))
                seen.add(key)

    def _on_both(self, point, first, second):
        at = create_v3(*point)
        return (first.is_point_on_boundary(at, eps=1e-8) and second.is_point_on_boundary(at, eps=1e-8)
                and self.root.is_point_on_boundary(at, eps=1e-8))

    def _add_rims(self, owner: CutCSG, patch: CylindricalPatch):
        seen = set()
        for plane in self.planes:
            arc = patch.section(plane.point, plane.normal)
            if arc is None:
                continue
            key = tuple(np.concatenate((arc.center, arc.u, arc.v)).round(9))
            angles = {arc.start, arc.stop}
            for other in self.planes:
                angles.update(arc.plane_crossings(other.point, other.normal))
            for _, other_patch in self.patches:
                if other_patch is not patch:
                    angles.update(_barrel_crossings(arc, other_patch))
            bounds = sorted(angles, reverse=arc.stop < arc.start)
            for low, high in zip(bounds, bounds[1:]):
                interval = (key, round(low, 10), round(high, 10))
                if interval in seen or abs(high - low) < 1e-10:
                    continue
                if self._on_both(arc.point((low + high) / 2), owner, plane.owner):
                    self.rims.append(Rim(owner, plane.name, arc, low, high))
                    seen.add(interval)

    def generators(self, toward_eye: np.ndarray):
        """Yield exposed barrel tangents and the ends of partial circular profiles in local space."""
        for owner, patch in self.patches:
            rim = patch.rim
            a, b = float(toward_eye @ rim.u), float(toward_eye @ rim.v)
            angles = [(angle, owner) for angle in self.corner_angles.get(patch, [])]
            if math.hypot(a, b) > 1e-12:
                phase = math.atan2(b, a)
                for station in (phase + math.pi / 2, phase - math.pi / 2):
                    low, high = sorted((rim.start, rim.stop))
                    angle = low + (station - low) % math.tau
                    if angle <= high:
                        angles.append((angle, owner))
            # A plane parallel to the barrel cuts two axial lines instead of an ellipse.
            for plane in self.planes:
                if abs(plane.normal @ patch.axis) < 1e-10 and plane.owner is not owner:
                    for angle in angular_roots(float(plane.normal @ rim.u), float(plane.normal @ rim.v),
                                               float(plane.normal @ (rim.center - plane.point)),
                                               rim.start - 1e-10, rim.stop + 1e-10):
                        angles.append((angle, plane.owner))
            for other, barrel in self.patches:
                if other is not owner and abs(patch.axis @ barrel.axis) > 1 - 1e-10:
                    angles.extend((angle, other) for angle in _barrel_crossings(rim, barrel))
            for angle, cutting_owner in angles:
                origin = rim.point(angle)
                middle = float((self.middle - origin) @ patch.axis)
                low, high = middle - self.reach, middle + self.reach
                if patch.bottom is not None:
                    low = max(low, patch.bottom)
                if patch.top is not None:
                    high = min(high, patch.top)
                if high <= low:
                    continue
                stops = {low, high}
                for plane in self.planes:
                    slope = float(plane.normal @ patch.axis)
                    if abs(slope) > 1e-10:
                        distance = float((plane.point - origin) @ plane.normal) / slope
                        if low < distance < high:
                            stops.add(distance)
                for _, other in self.patches:
                    if abs(other.axis @ patch.axis) < 1 - 1e-10:
                        delta = origin - other.rim.center
                        radial = delta - other.axis * (delta @ other.axis)
                        direction = patch.axis - other.axis * (patch.axis @ other.axis)
                        roots = np.roots([direction @ direction, 2 * radial @ direction,
                                          radial @ radial - other.rim.u @ other.rim.u])
                        stops.update(float(t.real) for t in roots if abs(t.imag) < 1e-9 and low < t.real < high)
                bounds = sorted(stops)
                for start, stop in zip(bounds, bounds[1:]):
                    point = create_v3(*(origin + patch.axis * ((start + stop) / 2)))
                    if cutting_owner.is_point_on_boundary(point, eps=1e-8) and self.root.is_point_on_boundary(point, eps=1e-8):
                        yield 'barrel', origin + start * patch.axis, origin + stop * patch.axis


def _profile_corners(owner: PathExtrusion):
    """Yield the end angles of each arc that join another segment at a sharp corner."""
    segments = owner.path.segments
    for i, segment in enumerate(segments):
        if isinstance(segment, ArcSegment):
            corners = []
            for point, neighbor, angle in [(segment.start, segments[i - 1], segment.start_angle),
                                           (segment.end, segments[(i + 1) % len(segments)], segment.end_angle)]:
                first = segment.outward_local_normal(point)
                second = neighbor.outward_local_normal(point)
                if float(first.dot(second)) < 1 - 1e-9:
                    corners.append(float(angle))
            yield corners


def _barrel_crossings(arc, patch):
    """Return arc angles on another barrel by solving its radial equation in tan(t/2)."""
    def perpendicular(vector):
        return vector - patch.axis * (vector @ patch.axis)

    offset = perpendicular(arc.center - patch.rim.center)
    u, v = perpendicular(arc.u), perpendicular(arc.v)
    radius = np.linalg.norm(patch.rim.u)
    a, b, c = offset + u, 2 * v, offset - u
    coefficients = np.array([a @ a - radius**2, 2 * a @ b,
                             b @ b + 2 * a @ c - 2 * radius**2, 2 * b @ c, c @ c - radius**2])
    scale = max(radius**2, u @ u, v @ v, offset @ offset)
    coefficients[np.abs(coefficients) < scale * 1e-12] = 0
    if not np.any(coefficients):
        return []
    angles = [2 * math.atan(root.real) for root in np.polynomial.polynomial.polyroots(coefficients)
              if abs(root.imag) < 1e-8]
    if coefficients[-1] == 0:
        angles.append(math.pi)
    low, high = sorted((arc.start, arc.stop))
    turns = [low + (angle - low) % math.tau for angle in angles]
    return [angle for angle in turns if low < angle < high]


def _fan(polygon):
    """Triangulate a convex polygon about its first vertex."""
    for i in range(1, len(polygon) - 1):
        yield polygon[[0, i, i + 1]]


# Distance in metres within which a stroke belongs to the surface it touches.
SURFACE_TOLERANCE = 1e-7


def remaining_intervals(blocked: list[tuple[float, float]]) -> Iterator[tuple[float, float]]:
    """Yield the parts of [0, 1] outside the given intervals."""
    start = 0.
    for low, high in sorted(blocked):
        if low > start:
            yield start, low
        start = max(start, high)
    if start < 1:
        yield start, 1.


class ProjectedFaces:
    """Occluding triangles and their member IDs in projected coordinates.

    Coordinates are sheet x, sheet y and depth toward the eye, in metres.
    A triangle hides points inside its three projected edges and behind its face.
    """

    def __init__(self, triangles: np.ndarray, members: np.ndarray):
        edges = np.roll(triangles, -1, axis=1) - triangles
        normals = np.cross(edges[:, 0], -edges[:, 2])
        keep = np.abs(normals[:, 2]) > 1e-15
        triangles, edges, normals = triangles[keep], edges[keep], normals[keep]
        self.members = members[keep]
        self.triangles = triangles
        self.low = triangles[:, :, :2].min(axis=1)
        self.high = triangles[:, :, :2].max(axis=1)
        self.normals = np.zeros((len(triangles), 4, 3))
        # Inward normals of the projected sides, then the half space behind the surface.
        self.normals[:, :3, 0] = -edges[:, :, 1] * np.sign(normals[:, 2, None])
        self.normals[:, :3, 1] = edges[:, :, 0] * np.sign(normals[:, 2, None])
        self.normals[:, 3] = -normals / normals[:, 2, None]
        self.offset = np.empty((len(triangles), 4))
        self.offset[:, :3] = (self.normals[:, :3] * triangles).sum(axis=2)
        self.offset[:, 3] = (self.normals[:, 3] * triangles[:, 0]).sum(axis=1) + SURFACE_TOLERANCE

    def nearby(self, low, high, ignore: int = -1) -> np.ndarray:
        return np.flatnonzero(((self.high >= low) & (self.low <= high)).all(axis=1) & (self.members != ignore))

    def line(self, a, b, ignore: int = -1) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        indices = self.nearby(np.minimum(a[:2], b[:2]), np.maximum(a[:2], b[:2]), ignore)
        values = self.normals[indices] @ a - self.offset[indices]
        slopes = self.normals[indices] @ (b - a)
        crossing = np.divide(-values, slopes, out=np.zeros_like(values), where=slopes != 0)
        low = np.maximum(0., np.where(slopes > 0, crossing, -np.inf).max(axis=1))
        high = np.minimum(1., np.where(slopes < 0, crossing, np.inf).min(axis=1))
        inside = ((slopes != 0) | (values >= 0)).all(axis=1) & (low < high)
        for start, stop in remaining_intervals(list(zip(low[inside], high[inside]))):
            yield a + start * (b - a), a + stop * (b - a)

    def arc_breaks(self, arc: EllipseArc, ignore: int = -1) -> list[float]:
        """Return angles where the arc enters or leaves a projected occluder."""
        radius = np.hypot(arc.u[:2], arc.v[:2])
        indices = self.nearby(arc.center[:2] - radius, arc.center[:2] + radius, ignore)
        angles = {arc.start, arc.stop}
        for i in indices:
            for normal, offset in zip(self.normals[i], self.offset[i]):
                angles.update(angular_roots(float(normal @ arc.u), float(normal @ arc.v),
                                            float(normal @ arc.center - offset), arc.start, arc.stop))
        return sorted(angles, reverse=arc.stop < arc.start)

    def hides(self, point, ignore: int = -1) -> bool:
        indices = self.nearby(point[:2], point[:2], ignore)
        return bool(((self.normals[indices] @ point - self.offset[indices]) >= 0).all(axis=1).any())

    def visible_region(self, polygon: np.ndarray) -> PolygonRegions:
        """Return the visible XY parts of a convex planar polygon."""
        normal = np.cross(polygon[1] - polygon[0], polygon[2] - polygon[0])
        if abs(normal[2]) < 1e-15:
            return []
        region = [[tuple(p) for p in polygon[:, :2]]]
        low, high = polygon[:, :2].min(axis=0), polygon[:, :2].max(axis=0)
        for tri in self.triangles[self.nearby(low, high)]:
            # Clip the occluder at the colored face's own depth before subtracting its footprint.
            depth = (tri - polygon[0]) @ normal / normal[2] - SURFACE_TOLERANCE
            clipped = []
            for i, end in enumerate(tri):
                d, e = depth[i - 1], depth[i]
                if (d > 0) != (e > 0):
                    start = tri[i - 1]
                    clipped.append(tuple((start + d / (d - e) * (end - start))[:2]))
                if e > 0:
                    clipped.append(tuple(end[:2]))
            if len(clipped) >= 3:
                region = subtract(region, [clipped])
            if not region:
                break
        return region


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
