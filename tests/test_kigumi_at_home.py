"""Tests for kumiki.kigumi_at_home -- headless PNG rendering."""

import math
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
    RenderBackend,
    RenderMode,
    UnfocusedStyle,
    _MATPLOTLIB_AVAILABLE,
    _PYGLET_AVAILABLE,
    _combined_bounds,
    _direction_to_elev_azim,
    _feature_edge_segments,
    _look_at_matrix,
    _resolve_focus_timbers,
    render_frame_to_png,
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


class TestDirectionToElevAzim:
    def test_straight_down_is_elev_90(self):
        elev, azim = _direction_to_elev_azim(np.array([0.0, 0.0, 1.0]))
        assert elev == pytest.approx(90.0)

    def test_non_unit_iso_direction_is_not_gimbal_locked(self):
        """Regression test: _CAMERA_DIRECTIONS entries like the iso corners
        are not unit vectors (e.g. (1, -1, 1) has magnitude sqrt(3)). Failing
        to normalize before asin(z) clamps every iso direction's elev to
        exactly 90 degrees, collapsing all iso angles into a top-down view."""
        elev, azim = _direction_to_elev_azim(np.array([1.0, -1.0, 1.0]))
        assert elev < 89.0
        assert elev == pytest.approx(math.degrees(math.asin(1.0 / math.sqrt(3.0))))

    def test_front_direction_azim(self):
        # FRONT direction is (0, -1, 0): looking along +Y, elev 0, azim -90.
        elev, azim = _direction_to_elev_azim(np.array([0.0, -1.0, 0.0]))
        assert elev == pytest.approx(0.0)
        assert azim == pytest.approx(-90.0)


# ---------------------------------------------------------------------------
# feature edges
# ---------------------------------------------------------------------------


class TestFeatureEdgeSegments:
    def test_box_has_edges(self):
        from kumiki.blueprint import _cut_timber_to_trimesh

        _, ct1, _ = _two_timber_frame()
        mesh = _cut_timber_to_trimesh(ct1)
        segments = _feature_edge_segments(mesh)
        assert segments is not None
        assert segments.shape[1:] == (2, 3)
        assert len(segments) > 0

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
        segments = _feature_edge_segments(mesh)
        # only the 4 boundary edges should show up, not the coplanar diagonal
        assert segments is not None
        assert len(segments) == 4


# ---------------------------------------------------------------------------
# end-to-end rendering -- RenderBackend.MATPLOTLIB
#
# No subprocess isolation needed: unlike TRIMESH_PYGLET, this backend has no
# per-process window-state bug, so these call render_frame_to_png directly
# and can run repeatedly in the same test process.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _MATPLOTLIB_AVAILABLE, reason="matplotlib (kumiki[render-matplotlib]) not installed")
class TestRenderFrameToPngMatplotlibEndToEnd:
    def test_writes_a_png_file(self, tmp_path):
        frame, ct1, ct2 = _two_timber_frame()
        out_path = render_frame_to_png(frame, tmp_path / "out.png")
        assert out_path.exists()
        assert out_path.stat().st_size > 0
        assert out_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_creates_parent_directories(self, tmp_path):
        frame, _, _ = _two_timber_frame()
        out_path = render_frame_to_png(frame, tmp_path / "sub" / "dir" / "out.png")
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_bounding_box_mode_renders(self, tmp_path):
        frame, _, _ = _two_timber_frame()
        out_path = render_frame_to_png(frame, tmp_path / "out.png", render_mode=RenderMode.BOUNDING_BOX)
        assert out_path.stat().st_size > 0

    def test_wireframe_mode_renders(self, tmp_path):
        frame, _, _ = _two_timber_frame()
        out_path = render_frame_to_png(
            frame, tmp_path / "out.png", geometry_style=GeometryStyle.NONE, show_edges=True
        )
        assert out_path.stat().st_size > 0

    def test_orthographic_projection_renders(self, tmp_path):
        frame, _, _ = _two_timber_frame()
        out_path = render_frame_to_png(
            frame, tmp_path / "out.png", projection=ProjectionType.ORTHOGRAPHIC, camera_angle=CameraAngle.FRONT
        )
        assert out_path.stat().st_size > 0

    def test_focus_with_ghosted_unfocused_renders(self, tmp_path):
        frame, ct1, ct2 = _two_timber_frame()
        out_path = render_frame_to_png(
            frame, tmp_path / "out.png", focus_timbers=[ct2], unfocused_style=UnfocusedStyle.GHOSTED
        )
        assert out_path.stat().st_size > 0

    def test_focus_by_kumiki_id_renders(self, tmp_path):
        frame, ct1, ct2 = _two_timber_frame()
        out_path = render_frame_to_png(
            frame, tmp_path / "out.png", focus_timbers=[ct2.timber.ticket.kumiki_id]
        )
        assert out_path.stat().st_size > 0

    def test_multiple_renders_in_same_process(self, tmp_path):
        """The whole reason RenderBackend.MATPLOTLIB exists: unlike
        TRIMESH_PYGLET it must not corrupt any per-process state."""
        frame, _, _ = _two_timber_frame()
        for i in range(3):
            out_path = render_frame_to_png(frame, tmp_path / f"out_{i}.png")
            assert out_path.stat().st_size > 0

    def test_all_camera_angles_render(self, tmp_path):
        frame, _, _ = _two_timber_frame()
        for angle in CameraAngle:
            out_path = render_frame_to_png(frame, tmp_path / f"{angle.value}.png", camera_angle=angle)
            assert out_path.stat().st_size > 0

    def test_accessory_near_focus_timber_is_included(self, tmp_path):
        t1 = _simple_timber("beam")
        ct1 = CutTimber(t1)
        peg = Peg(
            transform=Transform.identity(),
            size=scalar(0.05),
            shape=PegShape.ROUND,
            forward_length=scalar(0.2),
            stickout_length=scalar(0),
        )
        frame = Frame(cut_timbers=[ct1], accessories=[peg])
        out_path = render_frame_to_png(
            frame, tmp_path / "out.png", focus_timbers=[ct1], unfocused_style=UnfocusedStyle.HIDDEN
        )
        assert out_path.stat().st_size > 0


class TestMatplotlibImportGuard:
    @pytest.mark.skipif(_MATPLOTLIB_AVAILABLE, reason="matplotlib IS installed")
    def test_raises_helpful_import_error(self, tmp_path):
        frame, _, _ = _two_timber_frame()
        with pytest.raises(ImportError, match=r"kumiki\[render-matplotlib\]"):
            render_frame_to_png(frame, tmp_path / "out.png")


# ---------------------------------------------------------------------------
# end-to-end rendering -- RenderBackend.TRIMESH_PYGLET (subprocess-isolated --
# see module docstring: only the first render-per-process is reliable on
# macOS with pyglet<2)
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
            render_frame_to_png, RenderBackend, CameraAngle, ProjectionType,
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
class TestRenderFrameToPngTrimeshPygletEndToEnd:
    def test_writes_a_png_file(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, render_backend=RenderBackend.TRIMESH_PYGLET)"
        )
        assert out_path.exists()
        assert out_path.stat().st_size > 0
        assert out_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_creates_parent_directories(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path.parent / 'sub' / 'dir' / 'out.png', "
            "render_backend=RenderBackend.TRIMESH_PYGLET)"
        )
        nested = out_path.parent / "sub" / "dir" / "out.png"
        assert nested.exists()
        assert nested.stat().st_size > 0

    def test_bounding_box_mode_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, render_backend=RenderBackend.TRIMESH_PYGLET, "
            "render_mode=RenderMode.BOUNDING_BOX)"
        )
        assert out_path.stat().st_size > 0

    def test_wireframe_mode_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, render_backend=RenderBackend.TRIMESH_PYGLET, "
            "geometry_style=GeometryStyle.NONE, show_edges=True)"
        )
        assert out_path.stat().st_size > 0

    def test_focus_with_ghosted_unfocused_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, render_backend=RenderBackend.TRIMESH_PYGLET, "
            "focus_timbers=[ct2], unfocused_style=UnfocusedStyle.GHOSTED)"
        )
        assert out_path.stat().st_size > 0

    def test_focus_by_kumiki_id_renders(self):
        out_path = _run_render_script(
            "render_frame_to_png(frame, output_path, render_backend=RenderBackend.TRIMESH_PYGLET, "
            "focus_timbers=[ct2.timber.ticket.kumiki_id])"
        )
        assert out_path.stat().st_size > 0

    def test_empty_frame_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.png"
            script = textwrap.dedent(
                f"""
                from kumiki.timber import Frame
                from kumiki.kigumi_at_home import render_frame_to_png, RenderBackend
                frame = Frame(cut_timbers=[])
                try:
                    render_frame_to_png(
                        frame, {str(out_path)!r}, render_backend=RenderBackend.TRIMESH_PYGLET
                    )
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
                from kumiki.kigumi_at_home import render_frame_to_png, RenderBackend

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
                    render_frame_to_png(
                        frame, {str(out_path)!r}, render_backend=RenderBackend.TRIMESH_PYGLET,
                        focus_timbers=[other],
                    )
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
        frame, _, _ = _two_timber_frame()
        with tempfile.TemporaryDirectory() as td:
            with pytest.raises(ImportError, match=r"kumiki\[render\]"):
                render_frame_to_png(
                    frame, Path(td) / "out.png", render_backend=RenderBackend.TRIMESH_PYGLET
                )


# ---------------------------------------------------------------------------
# accessories (trimesh backend path -- matplotlib's accessory test lives in
# TestRenderFrameToPngMatplotlibEndToEnd above)
# ---------------------------------------------------------------------------


class TestAccessoryFocusHeuristicTrimeshPyglet:
    @pytest.mark.skipif(not _PYGLET_AVAILABLE, reason="pyglet (kumiki[render]) not installed")
    def test_accessory_near_focus_timber_is_included(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "out.png"
            script = textwrap.dedent(
                f"""
                from kumiki.timber import CutTimber, Frame, Peg, PegShape, create_timber
                from kumiki.rule import Transform, create_v3, create_v2, scalar
                from kumiki.kigumi_at_home import render_frame_to_png, RenderBackend, UnfocusedStyle

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
                    frame, {str(out_path)!r}, render_backend=RenderBackend.TRIMESH_PYGLET,
                    focus_timbers=[ct1], unfocused_style=UnfocusedStyle.HIDDEN,
                )
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
            )
            assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
            assert out_path.stat().st_size > 0
