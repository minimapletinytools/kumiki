"""Cuts whose faces coincide with the timber's, or each other's, at an angle mesh without slivers."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

import kumiki.csg.triangles as triangles
from kumiki.frame_decorators import module_patterns

PATTERNS = Path(__file__).resolve().parents[1] / "patterns"
ANGLED = [
    ("corner/dovetail_corner_joint_patterns.py", "corner/dovetail_corner_joint/angled"),
    ("corner/plain_corner_lap_joint_patterns.py", "corner/plain_corner_lap_joint/angled"),
    ("mixed/mortise_and_tenon_joints_patterns.py", "mixed/mortise_and_tenon/joint_plane_aligned_notched_2sided"),
]


def _sliver_count(mesh) -> int:
    """Count faces with an opposite-facing face under them 1e-12 m to a micron away.

    Smaller gaps are rounding in the last digits, left where two cutters that are not convex touch.
    """
    normals, triangles_ = mesh.face_normals, mesh.triangles
    centers = triangles_.mean(axis=1)
    offsets = np.einsum("ij,ij->i", normals, centers)
    count = 0
    for i in range(len(normals)):
        gaps = np.abs(offsets + offsets[i])
        for j in np.flatnonzero((normals @ normals[i] < -0.999999) & (gaps < 1e-6) & (gaps > 1e-12)):
            a, b, c = triangles_[j]
            point = centers[i] - normals[j] * (normals[j] @ centers[i] - offsets[j])
            v0, v1, v2 = b - a, c - a, point - a
            d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
            den = d00 * d11 - d01 * d01
            if den <= 0:
                continue
            v = (d11 * (v2 @ v0) - d01 * (v2 @ v1)) / den
            w = (d00 * (v2 @ v1) - d01 * (v2 @ v0)) / den
            if v > 1e-9 and w > 1e-9 and v + w < 1 - 1e-9:
                count += 1
                break
    return count


def _meshes(source: str, path: str):
    spec = importlib.util.spec_from_file_location("coplanar_" + Path(source).stem, PATTERNS / source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patterns, _ = module_patterns(module)
    pattern = next(pattern for pattern in patterns if pattern.path == path)
    return [triangles.triangulate_cutcsg(cut.render_timber_with_cuts_csg_local()).mesh
            for cut in pattern.raise_at().cut_timbers]


@pytest.mark.parametrize("source,path", ANGLED, ids=[path for _, path in ANGLED])
def test_angled_cuts_leave_no_slivers(source, path, monkeypatch):
    detached = _meshes(source, path)
    assert all(mesh.is_watertight for mesh in detached)
    assert sum(_sliver_count(mesh) for mesh in detached) == 0

    monkeypatch.setattr(triangles, "TRIANGLES_DETACH_COPLANAR_CUTS", False)
    plain = _meshes(source, path)
    assert sum(_sliver_count(mesh) for mesh in plain) > 0
    for mesh, plain_mesh in zip(detached, plain):
        assert mesh.volume == pytest.approx(plain_mesh.volume, rel=1e-6)


def test_a_timber_open_past_its_end_cut_meshes_only_that_far(monkeypatch):
    source, path = ANGLED[0]
    spec = importlib.util.spec_from_file_location("coplanar_ends", PATTERNS / source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pattern = next(pattern for pattern in module_patterns(module)[0] if pattern.path == path)
    for cut in pattern.raise_at().cut_timbers:
        csg = cut.render_timber_with_cuts_csg_local()
        assert csg.base.start_distance is None
        base = triangles.triangulate_cutcsg(triangles._end_at_end_cuts(csg.base, csg.subtract)).mesh
        assert base.extents.max() < 2.0

    near = _meshes(source, path)
    monkeypatch.setattr(triangles, "TRIANGLES_END_OPEN_BASE_AT_END_CUTS", False)
    for mesh, far_mesh in zip(near, _meshes(source, path)):
        assert mesh.volume == pytest.approx(far_mesh.volume, rel=1e-9)
