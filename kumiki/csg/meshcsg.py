"""Closed triangle solids imported from mesh files."""

from dataclasses import dataclass, field
from functools import cached_property
import heapq
import math
from typing import NamedTuple, Optional

import numpy as np

from .cutcsg import AxisAlignedBoundingBox, CutCSG, HasFeatures, face_plane_carriers
from ..rule import Numeric, Transform, V3, create_v3


class _BoundsCandidate(NamedTuple):
    distance: float
    index: int


@dataclass(frozen=True)
class _MeshBounds:
    low: np.ndarray
    high: np.ndarray
    indices: Optional[np.ndarray] = None
    children: tuple[int, ...] = ()


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

    @cached_property
    def _bounds_tree(self) -> tuple[_MeshBounds, ...]:
        triangles = self.mesh.triangles
        lows, highs = triangles.min(axis=1), triangles.max(axis=1)
        centers = (lows + highs) / 2
        nodes: list[_MeshBounds] = []

        def build(indices):
            low, high = lows[indices].min(axis=0), highs[indices].max(axis=0)
            index = len(nodes)
            nodes.append(_MeshBounds(low, high, indices))
            if len(indices) > 32:
                axis = int(np.argmax(high - low))
                ordered = indices[np.argsort(centers[indices, axis])]
                mid = len(ordered) // 2
                children = (build(ordered[:mid]), build(ordered[mid:]))
                nodes[index] = _MeshBounds(low, high, children=children)
            return index

        build(np.arange(len(triangles)))
        return tuple(nodes)

    def _nearest(self, point: V3, max_distance: Optional[float] = None) -> tuple[float, int]:
        """Return distance and face index; index is -1 when no face lies within max_distance."""
        from trimesh.triangles import closest_point
        position = np.asarray(list(point), dtype=float)
        best = math.inf if max_distance is None else max_distance ** 2
        nearest = -1
        pending = [_BoundsCandidate(0.0, 0)]
        while pending:
            distance, index = heapq.heappop(pending)
            if distance > best:
                continue
            node = self._bounds_tree[index]
            if node.indices is not None:
                triangles = self.mesh.triangles[node.indices]
                points = closest_point(triangles, np.broadcast_to(position, (len(triangles), 3)))
                distances = np.sum((points - position) ** 2, axis=1)
                candidate = int(np.argmin(distances))
                if distances[candidate] <= best:
                    best, nearest = float(distances[candidate]), int(node.indices[candidate])
            else:
                for child_index in node.children:
                    child = self._bounds_tree[child_index]
                    delta = np.maximum(np.maximum(child.low - position, position - child.high), 0)
                    bound = float(delta @ delta)
                    if bound <= best:
                        heapq.heappush(pending, _BoundsCandidate(bound, child_index))
        return math.sqrt(best), nearest

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        return self._nearest(point, 1e-8 if eps is None else float(eps))[1] >= 0

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
        _, index = self._nearest(point, 1e-8 if eps is None else float(eps))
        return None if index < 0 else create_v3(*self.mesh.face_normals[index])

    def get_aabb(self) -> AxisAlignedBoundingBox:
        low, high = self.mesh.bounds
        return AxisAlignedBoundingBox(*low, *high)
