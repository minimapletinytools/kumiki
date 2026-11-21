"""Finished faces, creases, and cylindrical rims used by orthographic drawings."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..csg.cross_sections import cross_section_outline, cross_section_polygons, face_cross_section
from ..csg.curves import CylindricalPatch, EllipseArc, angular_roots, cylindrical_patches
from ..csg.cutcsg import (ConvexPolygonSimpleLoft, CutCSG, ExtrusionCap, FaceFeature,
                          walk_csg_with_parity)
from ..csg.feature_extent import extents_of
from ..csg.meshcsg import TriangleSolid
from ..csg.pathcsg import ArcSegment, PathExtrusion
from ..geometry import Plane
from ..rule import Transform, as_ndarray, create_v3
from ..timber import PerfectTimberWithin


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
