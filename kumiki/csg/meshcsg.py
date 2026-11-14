"""Closed triangle solids imported from mesh files."""

from dataclasses import dataclass, field
from functools import cached_property
from typing import Optional

import numpy as np

from .cutcsg import AxisAlignedBoundingBox, CutCSG, HasFeatures, face_plane_carriers
from ..rule import Numeric, Transform, V3, create_v3


@dataclass(frozen=True)
class TriangleSolid(HasFeatures, CutCSG):
    """Represent a closed mesh with vertices in `transform`'s local space."""

    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, int, int], ...]
    transform: Transform = field(default_factory=Transform.identity)

    def __repr__(self) -> str:
        return f"TriangleSolid({len(self.vertices)} vertices, {len(self.faces)} faces)"

    def carriers(self):
        return face_plane_carriers(self)

    @cached_property
    def mesh(self):
        import trimesh
        vertices = np.asarray([
            list(self.transform.local_to_global(create_v3(*point)))
            for point in self.vertices
        ])
        return trimesh.Trimesh(vertices=vertices, faces=np.asarray(self.faces), process=False)

    def _nearest(self, point: V3):
        from trimesh.proximity import closest_point_naive
        return closest_point_naive(self.mesh, [list(point)])

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        return bool(self._nearest(point)[1][0] <= (1e-8 if eps is None else float(eps)))

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        if self.is_point_on_boundary(point, eps):
            return True
        # Sum the signed solid angles; closed outward meshes enclose 4*pi steradians.
        vectors = self.mesh.triangles - np.asarray(list(point), dtype=float)
        a, b, c = vectors[:, 0], vectors[:, 1], vectors[:, 2]
        la, lb, lc = (np.linalg.norm(v, axis=1) for v in (a, b, c))
        numerator = np.einsum('ij,ij->i', a, np.cross(b, c))
        denominator = la * lb * lc + np.einsum('ij,ij->i', a, b) * lc + np.einsum('ij,ij->i', b, c) * la + np.einsum('ij,ij->i', c, a) * lb
        return bool(abs(np.sum(2 * np.arctan2(numerator, denominator))) > 2 * np.pi)

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[V3]:
        _, distance, index = self._nearest(point)
        if distance[0] > (1e-8 if eps is None else float(eps)):
            return None
        return create_v3(*self.mesh.face_normals[index[0]])

    def get_aabb(self) -> AxisAlignedBoundingBox:
        low, high = self.mesh.bounds
        return AxisAlignedBoundingBox(*low, *high)
