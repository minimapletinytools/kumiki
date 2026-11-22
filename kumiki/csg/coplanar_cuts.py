"""
Move cutter faces off the faces they coincide with, before a mesh difference.

The boolean engine cancels coincident faces only when they are exactly coplanar. Two faces that
lie in the same plane in the exact model can come out a few nanometres apart once meshed, and the
engine then leaves a sliver between them. Both steps here enlarge a cutter only by space that is
removed anyway, so base - cutters is the same solid:

- a cutter face lying in a face of the convex base is swept straight out past the base;
- a cutter face lying against a face of a convex cutter is swept partway into that cutter.

A plane tolerance decides which faces coincide; it never moves geometry by that amount.
Turn it off with `triangles.TRIANGLES_DETACH_COPLANAR_CUTS`.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import trimesh

# Two faces coincide when their normals agree this closely...
_SAME_DIRECTION = 1.0 - 1e-9
# ...and their planes are this close (meters): the mesher's coordinate precision.
_PLANE_GAP = 1e-8
# A sweep into a neighbouring cutter goes this share of the way it could while staying inside.
_NEIGHBOUR_DEPTH_SHARE = 0.5


def detach_coplanar_cuts(base: trimesh.Trimesh, cutters: Sequence[trimesh.Trimesh]) -> list[trimesh.Trimesh]:
    """Return cutters to subtract from `base` instead of `cutters`, with the same result.

    Leaves the cutters as they are unless `base` is convex; a cutter that is open or not convex
    is passed through unchanged.
    """
    if not _is_convex(base):
        return list(cutters)
    reach = _diagonal(base) + max((_diagonal(cutter) for cutter in cutters if len(cutter.faces)), default=0.0)
    bodies = [body for cutter in cutters for body in _bodies(cutter)]
    convex = [_is_convex(body) for body in bodies]
    # Into neighbours first: a body swept out past the base no longer fits inside its neighbours.
    bodies = _sweep_into_neighbours(bodies, convex)
    return [_sweep_out_of(base, body, reach) if is_convex else body for body, is_convex in zip(bodies, convex)]


def _bodies(cutter: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    """Return a closed cutter's separate bodies, or the cutter itself."""
    if len(cutter.faces) == 0 or not cutter.is_watertight:
        return [cutter]
    parts = cutter.split(only_watertight=False)
    if len(parts) > 1 and all(part.is_watertight for part in parts):
        return list(parts)
    return [cutter]


def _sweep_out_of(base: trimesh.Trimesh, cutter: trimesh.Trimesh, reach: float) -> trimesh.Trimesh:
    """Sweep each face of `cutter` that lies in a face of convex `base` out by `reach`."""
    base_normals, base_offsets = _planes(base)
    for _ in range(len(base.faces) + 1):
        normals, offsets = _planes(cutter)
        on_base = ((normals @ base_normals.T > _SAME_DIRECTION)
                   & (np.abs(offsets[:, None] - base_offsets[None, :]) < _PLANE_GAP)).any(axis=1)
        if not on_base.any():
            break
        face = int(np.argmax(on_base))
        cutter = _sweep(cutter, _patch(normals, offsets, face), normals[face], reach)
    return cutter


def _sweep_into_neighbours(bodies: list[trimesh.Trimesh], convex: list[bool]) -> list[trimesh.Trimesh]:
    """Sweep each face of a body lying against a convex body partway into it.

    A body that is not convex is swept only into a neighbour it touches without overlapping, so the
    swept part cannot run into the rest of it.
    """
    for i in range(len(bodies)):
        for j in range(len(bodies)):
            if i == j or not convex[j] or not bodies[i].is_watertight:
                continue
            for _ in range(len(bodies[j].faces) + 1):
                normals, offsets = _planes(bodies[i])
                other_normals, other_offsets = _planes(bodies[j])
                touching = ((normals @ other_normals.T < -_SAME_DIRECTION)
                            & (np.abs(offsets[:, None] + other_offsets[None, :]) < _PLANE_GAP)).any(axis=1)
                swept = False
                for face in np.flatnonzero(touching):
                    patch = _patch(normals, offsets, int(face))
                    points = bodies[i].vertices[np.unique(bodies[i].faces[patch])]
                    depth = _NEIGHBOUR_DEPTH_SHARE * _depth_inside(points, normals[face], bodies[j])
                    if depth > 1e3 * _PLANE_GAP and (convex[i] or not _overlap(bodies[i], bodies[j])):
                        bodies[i] = _sweep(bodies[i], patch, normals[face], depth)
                        swept = True
                        break
                if not swept:
                    break
    return bodies


def _overlap(first: trimesh.Trimesh, second: trimesh.Trimesh) -> bool:
    """Return whether two closed meshes share any volume."""
    shared = trimesh.boolean.intersection([first, second], engine="manifold")
    return len(shared.faces) > 0 and abs(shared.volume) > 1e-9 * min(first.volume, second.volume)


def _depth_inside(points: np.ndarray, direction: np.ndarray, body: trimesh.Trimesh) -> float:
    """Return how far `points` can all move along `direction` and stay in convex `body`.

    Returns 0 when a point starts outside it.
    """
    normals, offsets = _planes(body)
    outside = points @ normals.T - offsets
    if (outside > _PLANE_GAP).any():
        return 0.0
    rate = normals @ direction
    ahead = rate > 1e-12
    if not ahead.any():
        return 0.0
    return float(np.min(-outside[:, ahead] / rate[ahead]))


def _sweep(mesh: trimesh.Trimesh, patch: np.ndarray, direction: np.ndarray, distance: float) -> trimesh.Trimesh:
    """Return `mesh` with the planar faces `patch` swept along `direction` by `distance`.

    `direction` must be the patch's outward unit normal.
    """
    faces = mesh.faces[patch]
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    _, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    rim = edges[counts[inverse.ravel()] == 1]
    used = np.unique(faces)
    moved = np.full(len(mesh.vertices), -1, dtype=np.int64)
    moved[used] = len(mesh.vertices) + np.arange(len(used))
    walls = np.concatenate([
        np.stack([rim[:, 0], rim[:, 1], moved[rim[:, 1]]], axis=1),
        np.stack([rim[:, 0], moved[rim[:, 1]], moved[rim[:, 0]]], axis=1),
    ])
    kept = np.delete(mesh.faces, patch, axis=0)
    swept = trimesh.Trimesh(
        vertices=np.vstack([mesh.vertices, mesh.vertices[used] + direction * distance]),
        faces=np.concatenate([kept, walls, moved[faces]]),
        process=False,
    )
    swept.fix_normals()
    return swept


def _patch(normals: np.ndarray, offsets: np.ndarray, face: int) -> np.ndarray:
    """Return the faces in the same plane as `face`, facing the same way."""
    return np.flatnonzero((normals @ normals[face] > _SAME_DIRECTION) & (np.abs(offsets - offsets[face]) < _PLANE_GAP))


def _planes(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    """Return each face's unit normal and plane offset (normal · point)."""
    normals = mesh.face_normals
    return normals, np.einsum("ij,ij->i", normals, mesh.triangles_center)


def _is_convex(mesh: trimesh.Trimesh) -> bool:
    """Return whether a closed mesh has every vertex behind every face's plane."""
    if len(mesh.faces) == 0 or not mesh.is_watertight or mesh.volume <= 0:
        return False
    normals, offsets = _planes(mesh)
    return bool((mesh.vertices @ normals.T - offsets <= _PLANE_GAP).all())


def _diagonal(mesh: trimesh.Trimesh) -> float:
    low, high = np.asarray(mesh.bounds, dtype=float)
    return float(np.linalg.norm(high - low))
