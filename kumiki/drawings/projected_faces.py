"""Occlusion of vector strokes and planar face regions in an orthographic view.

Coordinates are (sheet x, sheet y, depth toward the eye), in metres. A projected triangle
hides the points inside its three side planes and behind its face plane.
"""

from collections.abc import Iterator

import numpy as np

from ..csg.cross_sections import PolygonRegions, subtract
from ..csg.curves import EllipseArc, angular_roots


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
    """Front and back surfaces that can hide a stroke, with the member owning each one."""

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
