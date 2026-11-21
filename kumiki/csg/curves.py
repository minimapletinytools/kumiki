"""Circular and elliptic sections of cylinder barrels and extruded circular arcs."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterator

import numpy as np

from ..geometry import perpendicular_axes
from ..rule import as_ndarray, unit_ndarray
from .cutcsg import CutCSG, Cylinder
from .pathcsg import ArcSegment, PathExtrusion


@dataclass(frozen=True, eq=False)
class EllipseArc:
    """A curve in model coordinates, center + u cos(t) + v sin(t), between two angles in radians."""

    center: np.ndarray
    u: np.ndarray
    v: np.ndarray
    start: float = 0.
    stop: float = math.tau

    def point(self, angle: float) -> np.ndarray:
        return self.center + self.u * math.cos(angle) + self.v * math.sin(angle)

    def plane_crossings(self, point: np.ndarray, normal: np.ndarray) -> list[float]:
        """Return the interior parameters where the arc meets a plane, ordered along its sweep."""
        return angular_roots(float(self.u @ normal), float(self.v @ normal),
                             float((self.center - point) @ normal), self.start, self.stop)


def angular_roots(a: float, b: float, c: float, start: float, stop: float) -> list[float]:
    """Return interior roots of a cos(t) + b sin(t) + c over the directed interval."""
    radius = math.hypot(a, b)
    if radius == 0 or abs(c) > radius:
        return []
    phase = math.atan2(b, a)
    delta = math.acos(np.clip(-c / radius, -1., 1.))
    low, high = sorted((start, stop))
    roots = set()
    for base in (phase - delta, phase + delta):
        turn = math.floor((low - base) / math.tau) + 1
        while (angle := base + turn * math.tau) < high:
            roots.add(angle)
            turn += 1
    return sorted(roots, reverse=stop < start)


@dataclass(frozen=True, eq=False)
class CylindricalPatch:
    """An extrusion of a circular arc along a unit axis, in its CSG tree's coordinates."""

    rim: EllipseArc
    axis: np.ndarray
    bottom: float | None
    top: float | None

    @classmethod
    def of_cylinder(cls, cylinder: Cylinder) -> CylindricalPatch:
        u, v = perpendicular_axes(cylinder.axis_direction)
        radius = float(cylinder.radius)
        return cls(EllipseArc(as_ndarray(cylinder.position), radius * as_ndarray(u), radius * as_ndarray(v)),
                   unit_ndarray(as_ndarray(cylinder.axis_direction)), cylinder.start_distance, cylinder.end_distance)

    def section(self, point: np.ndarray, normal: np.ndarray) -> EllipseArc | None:
        """Intersect the axially unbounded patch with a plane. Return None for a parallel plane."""
        along = float(normal @ self.axis)
        if abs(along) < 1e-9:
            return None
        rim = self.rim
        def onto_plane(vector: np.ndarray) -> np.ndarray:
            return vector - self.axis * float(vector @ normal) / along
        return EllipseArc(point + onto_plane(rim.center - point), onto_plane(rim.u), onto_plane(rim.v),
                          rim.start, rim.stop)


def cylindrical_patches(owner: CutCSG) -> Iterator[CylindricalPatch]:
    """Yield the circular sides of a primitive in its tree's coordinates."""
    if isinstance(owner, Cylinder):
        yield CylindricalPatch.of_cylinder(owner)
    elif isinstance(owner, PathExtrusion):
        matrix = np.asarray(owner.transform.orientation.matrix.tolist(), dtype=float)
        for seg in owner.path.segments:
            if isinstance(seg, ArcSegment):
                center = as_ndarray(owner.transform.position) + matrix[:, :2] @ np.array(seg.center.tolist()).reshape(2)
                radius = float(seg.radius)
                yield CylindricalPatch(EllipseArc(center, matrix[:, 0] * radius, matrix[:, 1] * radius,
                                                  float(seg.start_angle), float(seg.end_angle)),
                                       matrix[:, 2], owner.start_distance, owner.end_distance)
