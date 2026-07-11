"""Tests for kumiki.kigumi_at_home -- headless PNG rendering."""

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import numpy as np
import pytest

from kumiki.kigumi_at_home import (
    CameraAngle,
    GeometryStyle,
    ProjectionType,
    RenderMode,
    UnfocusedStyle,
    _PYGLET_AVAILABLE,
    _combined_bounds,
    _feature_edges_path,
    _look_at_matrix,
    _resolve_focus_timbers,
)
from kumiki.timber import CutTimber, Frame, Peg, PegShape, Timber, create_timber
from kumiki.rule import Transform, create_v3, create_v2, scalar


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _simple_timber(name: str = "beam", length_direction=None, bottom_position=None) -> Timber:
    return create_timber(
        bottom_position=bottom_position or create_v3(scalar(0), scalar(0), scalar(0)),
        length=scalar(2),
        size=create_v2(scalar(0.2), scalar(0.2)),
        length_direction=length_direction or create_v3(scalar(1), scalar(0), scalar(0)),
        width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
        ticket=name,
    )


def _two_timber_frame() -> tuple[Frame, CutTimber, CutTimber]:
    t1 = _simple_timber("beam", bottom_position=create_v3(scalar(-1), scalar(0), scalar(0)))
    t2 = _simple_timber(
        "post",
        bottom_position=create_v3(scalar(0), scalar(0), scalar(-1)),
        length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
    )
    ct1, ct2 = CutTimber(t1), CutTimber(t2)
    frame = Frame(cut_timbers=[ct1, ct2], name="TestFrame")
    return frame, ct1, ct2


# ---------------------------------------------------------------------------
# focus-set resolution
# ---------------------------------------------------------------------------


class TestResolveFocusTimbers:
    def test_none_returns_all(self):
        frame, ct1, ct2 = _two_timber_frame()
        assert _resolve_focus_timbers(frame, None) == [ct1, ct2]

    def test_empty_returns_all(self):
        frame, ct1, ct2 = _two_timber_frame()
        assert _resolve_focus_timbers(frame, []) == [ct1, ct2]

    def test_direct_cut_timber_reference(self):
        frame, ct1, ct2 = _two_timber_frame()
        assert _resolve_focus_timbers(frame, [ct2]) == [ct2]

    def test_kumiki_id_reference(self):
        frame, ct1, ct2 = _two_timber_frame()
        kumiki_id = ct2.timber.ticket.kumiki_id
        assert _resolve_focus_timbers(frame, [kumiki_id]) == [ct2]

    def test_cut_timber_not_in_frame_raises(self):
        frame, ct1, _ = _two_timber_frame()
        other = CutTimber(_simple_timber("other"))
        with pytest.raises(ValueError, match="not part of this frame"):
            _resolve_focus_timbers(frame, [other])

    def test_unknown_kumiki_id_raises(self):
        frame, _, _ = _two_timber_frame()
        with pytest.raises(ValueError, match="kumiki_id"):
            _resolve_focus_timbers(frame, [999_999_999])


# ---------------------------------------------------------------------------
# bounding box / camera math
# ---------------------------------------------------------------------------


class TestCombinedBounds:
    def test_matches_single_mesh_bounds(self):
        from kumiki.blueprint import _cut_timber_to_trimesh

        _, ct1, _ = _two_timber_frame()
        mesh = _cut_timber_to_trimesh(ct1)
        bbox = _combined_bounds([mesh])
        assert np.allclose(bbox.min_corner, mesh.bounds[0])
        assert np.allclose(bbox.max_corner, mesh.bounds[1])

    def test_union_of_two_disjoint_meshes(self):
        from kumiki.blueprint import _cut_timber_to_trimesh

        _, ct1, ct2 = _two_timber_frame()
        bbox = _combined_bounds([_cut_timber_to_trimesh(ct1), _cut_timber_to_trimesh(ct2)])
        # beam spans x in [-1, 1], post spans z in [-1, 1] (both centered at origin-ish)
        assert bbox.min_corner[0] < -0.9
        assert bbox.max_corner[0] > 0.9

    def test_contains_point(self):
        from kumiki.blueprint import _cut_timber_to_trimesh

        _, ct1, _ = _two_timber_frame()
        bbox = _combined_bounds([_cut_timber_to_trimesh(ct1)])
        assert bbox.contains_point(bbox.center, tolerance=0.0)
        far_point = bbox.max_corner + 100.0
        assert not bbox.contains_point(far_point, tolerance=0.0)


class TestLookAtMatrix:
    def test_camera_looks_towards_target(self):
        eye = np.array([0.0, -5.0, 0.0])
        target = np.array([0.0, 0.0, 0.0])
        up = np.array([0.0, 0.0, 1.0])
        matrix = _look_at_matrix(eye, target, up)
        assert np.allclose(matrix[:3, 3], eye)
        # camera-local -Z axis should point from eye towards target
        forward_world = -matrix[:3, 2]
        expected = (target - eye) / np.linalg.norm(target - eye)
        assert np.allclose(forward_world, expected, atol=1e-9)

    def test_columns_are_orthonormal(self):
        eye = np.array([3.0, -4.0, 2.0])
        target = np.array([0.0, 0.0, 0.0])
        up = np.array([0.0, 0.0, 1.0])
        matrix = _look_at_matrix(eye, target, up)
        rot = matrix[:3, :3]
        assert np.allclose(rot.T @ rot, np.eye(3), atol=1e-9)


# ---------------------------------------------------------------------------
# feature edges
# ---------------------------------------------------------------------------


class TestFeatureEdgesPath:
    def test_box_has_edges(self):
        from kumiki.blueprint import _cut_timber_to_trimesh

        _, ct1, _ = _two_timber_frame()
        mesh = _cut_timber_to_trimesh(ct1)
        path = _feature_edges_path(mesh)
        assert path is not None
        assert len(path.entities) > 0

    def test_diagonal_triangulation_seams_are_excluded(self):
        """A flat face triangulated into two triangles has one dihedral angle
        of ~0 (coplanar) between them -- that internal diagonal must not be
        treated as a feature edge, or 'show edges' would look noisy."""
        # Two coplanar triangles forming a unit square, connected by a diagonal.
        vertices = np.array(
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float
        )
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        import trimesh

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        path = _feature_edges_path(mesh)
        # only the 4 boundary edges should show up, not the coplanar diagonal
        assert path is not None
        assert len(path.entities) == 4


# ---------------------------------------------------------------------------
# end-to-end rendering (subprocess-isolated -- see module docstring: only the
# first render-per-process is reliable on macOS with pyglet<2)
# ---------------------------------------------------------------------------


def _run_render_script(body: str) -> Path:
    """Run a small script that calls render_frame_to_png exactly once, in its
    own subprocess, and return the output PNG path.

    Deliberately does not use `tempfile.TemporaryDirectory()` as a context
    manager here: it would delete the directory the instant this function
    returns, before the caller can inspect the file it just asked for.
    """
    td = tempfile.mkdtemp()
    out_path = Path(td) / "out.png"
    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from kumiki.timber import CutTimber, Frame, create_timber
        from kumiki.rule import create_v3, create_v2, scalar
        from kumiki.kigumi_at_home import (
            render_frame_to_png, CameraAngle, ProjectionType,
            GeometryStyle, UnfocusedStyle, RenderMode,
        )

        t1 = create_timber(
            bottom_position=create_v3(scalar(-1), scalar(0), scalar(0)),
            length=scalar(2), size=create_v2(scalar(0.2), scalar(0.2)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            ticket="beam",
        )
        t2 = create_timber(
            bottom_position=create_v3(scalar(0), scalar(0), scalar(-1)),
            length=scalar(3), size=create_v2(scalar(0.2), scalar(0.2)),
            length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            ticket="post",
        )
        ct1, ct2 = CutTimber(t1), CutTimber(t2)
        frame = Frame(cut_timbers=[ct1, ct2], name="TestFrame")
        output_path = Path({str(out_path)!r})

        {body}
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"render script failed:\n{result.stdout}\n{result.stderr}"
    return out_path


@pytest.mark.skipif(not _PYGLET_AVAILABLE, reason="pyglet (kumiki[render]) not installed")
class TestRenderFrameToPngEndToEnd:
    def test_writes_a_png_file(self):
        out_path = _run_render_script("render_frame_to_png(frame, output_path)")
        assert out_path.exists()
        assert out_path.stat().st_size > 0
        assert out_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_creates_parent_directories(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path.parent / 'sub' / 'dir' / 'out.png')"
        )
        nested = out_path.parent / "sub" / "dir" / "out.png"
        assert nested.exists()
        assert nested.stat().st_size > 0

    def test_bounding_box_mode_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, render_mode=RenderMode.BOUNDING_BOX)"
        )
        assert out_path.stat().st_size > 0

    def test_wireframe_mode_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, geometry_style=GeometryStyle.NONE, show_edges=True)"
        )
        assert out_path.stat().st_size > 0

    def test_focus_with_ghosted_unfocused_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, focus_timbers=[ct2], "
            "unfocused_style=UnfocusedStyle.GHOSTED)"
        )
        assert out_path.stat().st_size > 0

    def test_focus_by_kumiki_id_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, "
            "focus_timbers=[ct2.timber.ticket.kumiki_id])"
        )
        assert out_path.stat().st_size > 0

    def test_empty_frame_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.png"
            script = textwrap.dedent(
                f"""
                from kumiki.timber import Frame
                from kumiki.kigumi_at_home import render_frame_to_png
                frame = Frame(cut_timbers=[])
                try:
                    render_frame_to_png(frame, {str(out_path)!r})
                except ValueError as exc:
                    assert "No timbers" in str(exc)
                else:
                    raise AssertionError("expected ValueError")
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
            )
            assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    def test_focus_timber_not_in_frame_raises(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.png"
            script = textwrap.dedent(
                f"""
                from kumiki.timber import CutTimber, Frame, create_timber
                from kumiki.rule import create_v3, create_v2, scalar
                from kumiki.kigumi_at_home import render_frame_to_png

                t1 = create_timber(
                    bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
                    length=scalar(2), size=create_v2(scalar(0.2), scalar(0.2)),
                    length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
                    width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
                    ticket="beam",
                )
                other = CutTimber(t1)
                frame = Frame(cut_timbers=[CutTimber(t1)])
                try:
                    render_frame_to_png(frame, {str(out_path)!r}, focus_timbers=[other])
                except ValueError as exc:
                    assert "not part of this frame" in str(exc)
                else:
                    raise AssertionError("expected ValueError")
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
            )
            assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


class TestPygletImportGuard:
    @pytest.mark.skipif(_PYGLET_AVAILABLE, reason="pyglet IS installed")
    def test_raises_helpful_import_error(self):
        from kumiki.kigumi_at_home import render_frame_to_png

        frame, _, _ = _two_timber_frame()
        with tempfile.TemporaryDirectory() as td:
            with pytest.raises(ImportError, match="kumiki\\[render\\]"):
                render_frame_to_png(frame, Path(td) / "out.png")


# ---------------------------------------------------------------------------
# accessories
# ---------------------------------------------------------------------------


class TestAccessoryFocusHeuristic:
    @pytest.mark.skipif(not _PYGLET_AVAILABLE, reason="pyglet (kumiki[render]) not installed")
    def test_accessory_near_focus_timber_is_included(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.png"
            script = textwrap.dedent(
                f"""
                from kumiki.timber import CutTimber, Frame, Peg, PegShape, create_timber
                from kumiki.rule import Transform, create_v3, create_v2, scalar
                from kumiki.kigumi_at_home import render_frame_to_png, UnfocusedStyle

                t1 = create_timber(
                    bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
                    length=scalar(2), size=create_v2(scalar(0.2), scalar(0.2)),
                    length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
                    width_direction=create_v3(scalar(0), scalar(1), scalar(0)),
                    ticket="beam",
                )
                ct1 = CutTimber(t1)
                peg = Peg(
                    transform=Transform.identity(),
                    size=scalar(0.05), shape=PegShape.ROUND,
                    forward_length=scalar(0.2), stickout_length=scalar(0),
                )
                frame = Frame(cut_timbers=[ct1], accessories=[peg])
                render_frame_to_png(
                    frame, {str(out_path)!r},
                    focus_timbers=[ct1], unfocused_style=UnfocusedStyle.HIDDEN,
                )
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
            )
            assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
            assert out_path.stat().st_size > 0
