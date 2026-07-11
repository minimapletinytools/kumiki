"""
Kigumi-at-home: headless PNG rendering for agentic workflows.

Renders a Frame to a PNG without the Kigumi VS Code viewer, so an agent
running in a plain Python process can "see" what a pattern produced.

Rendering is done with trimesh's built-in scene viewer, which is backed by
pyglet (an optional dependency -- install with ``pip install kumiki[render]``).
Two real constraints fall out of that choice and are not fixable from here:

- Trimesh's viewer only supports ``pyglet<2``; the pyglet 2.x rewrite (which
  added a proper headless/EGL backend) is not supported by trimesh yet. On
  Linux this means a real X server is required -- ``Xvfb`` is the usual
  stand-in for CI/agent sandboxes with no physical display. On macOS/Windows
  a normal desktop session is enough.
- ``trimesh.Scene.save_image()`` opens a real (visible) window by default;
  passing ``visible=False`` avoids the on-screen flash but trimesh's own
  docs warn many platforms return a blank image for hidden windows. This
  module defaults to ``visible=True`` because it is the setting that
  actually works, at the cost of a brief window appearing on screen.

There is no true orthographic camera in trimesh's viewer (its ``Camera``
only models focal length / field of view). ``ProjectionType.ORTHOGRAPHIC``
is approximated by using a very small FOV at a proportionally large
distance, which converges to an orthographic projection as FOV -> 0.

IMPORTANT -- one render per process (macOS): the first call to
render_frame_to_png() in a process reliably works. On macOS, a pyglet<2 /
Cocoa windowing bug corrupts the NSApplication delegate state as the first
window closes, and every subsequent call in that *same* process raises
(``PygletDelegate has no attribute initWithAttributes_`` or similar) when it
tries to open its own window. If you need multiple renders, invoke this
function from a fresh ``python3`` subprocess each time rather than calling it
repeatedly in one long-lived process.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Union

import numpy as np
import trimesh
from trimesh.path.entities import Line
from trimesh.path.path import Path3D

from .cutcsg import adopt_csg
from .rule import Transform
from .timber import Accessory, CutTimber, Frame

try:
    importlib.import_module("pyglet")
    _PYGLET_AVAILABLE = True
except ImportError:
    _PYGLET_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public enums
# ---------------------------------------------------------------------------


class RenderMode(Enum):
    """What geometry to use for each timber."""

    FULL_CUTS = "full_cuts"
    BOUNDING_BOX = "bounding_box"


class CameraAngle(Enum):
    """Fixed camera directions. The camera always auto-fits distance/target
    to the bounding box of the geometry in focus."""

    FRONT = "front"
    BACK = "back"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    ISO_FRONT_LEFT = "iso_front_left"
    ISO_FRONT_RIGHT = "iso_front_right"
    ISO_BACK_LEFT = "iso_back_left"
    ISO_BACK_RIGHT = "iso_back_right"


class ProjectionType(Enum):
    PERSPECTIVE = "perspective"
    ORTHOGRAPHIC = "orthographic"


class GeometryStyle(Enum):
    """Global style applied to all in-focus geometry."""

    SOLID = "solid"
    TRANSPARENT = "transparent"
    NONE = "none"


class UnfocusedStyle(Enum):
    """How timbers outside the focus set are rendered."""

    HIDDEN = "hidden"
    GHOSTED = "ghosted"


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

_TIMBER_COLOR = (222, 184, 135, 255)  # burlywood
_ACCESSORY_COLOR = (110, 110, 116, 255)  # steel gray
_TRANSPARENT_ALPHA = 90
_GHOSTED_ALPHA = 40
_EDGE_COLOR = (40, 30, 20, 255)
_EDGE_ANGLE_THRESHOLD_DEGREES = 15.0
_ACCESSORY_FOCUS_TOLERANCE = 0.02  # metres of slack around a timber's bbox

# Camera direction (unit vector from the focused target towards the camera)
# and up vector, keyed by CameraAngle. World is Z-up (see docs/concepts.md).
_CAMERA_DIRECTIONS: dict[CameraAngle, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    CameraAngle.FRONT: ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    CameraAngle.BACK: ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    CameraAngle.LEFT: ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    CameraAngle.RIGHT: ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    CameraAngle.TOP: ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    CameraAngle.BOTTOM: ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    CameraAngle.ISO_FRONT_LEFT: ((-1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
    CameraAngle.ISO_FRONT_RIGHT: ((1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
    CameraAngle.ISO_BACK_LEFT: ((-1.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
    CameraAngle.ISO_BACK_RIGHT: ((1.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
}


# ---------------------------------------------------------------------------
# CutTimber / Accessory -> trimesh
# ---------------------------------------------------------------------------


def _cut_timber_to_trimesh(cut_timber: CutTimber, mode: RenderMode) -> "trimesh.Trimesh":
    """Return a global-coordinates trimesh for one CutTimber."""
    from .triangles import triangulate_cutcsg

    if mode is RenderMode.FULL_CUTS:
        local_csg = cut_timber.render_timber_with_cuts_csg_local()
    else:
        # get_perfect_timber_within_bounding_box_prism() already returns the
        # prism in global coordinates, so no adopt_csg step is needed.
        return triangulate_cutcsg(cut_timber.get_perfect_timber_within_bounding_box_prism()).mesh

    global_csg = adopt_csg(cut_timber.timber.transform, Transform.identity(), local_csg)
    return triangulate_cutcsg(global_csg).mesh


def _accessory_to_trimesh(accessory: Accessory) -> "trimesh.Trimesh":
    """Return a global-coordinates trimesh for one Accessory."""
    from .triangles import triangulate_cutcsg

    transform = getattr(accessory, "transform", None)
    if transform is None:
        raise ValueError(f"Accessory '{accessory.ticket.path}' does not define a global transform")
    local_csg = accessory.get_csg_local()
    global_csg = adopt_csg(transform, Transform.identity(), local_csg)
    return triangulate_cutcsg(global_csg).mesh


# ---------------------------------------------------------------------------
# Focus-set resolution
# ---------------------------------------------------------------------------


def _resolve_focus_timbers(
    frame: Frame, focus_timbers: Optional[Sequence[Union[CutTimber, int]]]
) -> List[CutTimber]:
    if not focus_timbers:
        return list(frame.cut_timbers)

    by_id = {id(ct): ct for ct in frame.cut_timbers}
    by_kumiki_id = {ct.timber.ticket.kumiki_id: ct for ct in frame.cut_timbers}

    resolved: List[CutTimber] = []
    for ref in focus_timbers:
        if isinstance(ref, CutTimber):
            if id(ref) not in by_id:
                raise ValueError(f"focus_timbers CutTimber '{ref.name}' is not part of this frame")
            resolved.append(ref)
        else:
            ct = by_kumiki_id.get(int(ref))
            if ct is None:
                raise ValueError(f"focus_timbers kumiki_id {ref} does not match any timber in this frame")
            resolved.append(ct)
    return resolved


# ---------------------------------------------------------------------------
# Bounding box / camera framing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BoundingBox:
    min_corner: np.ndarray
    max_corner: np.ndarray

    @property
    def center(self) -> np.ndarray:
        return (self.min_corner + self.max_corner) / 2.0

    @property
    def radius(self) -> float:
        """Half-diagonal -- radius of the bounding sphere around this box."""
        return float(np.linalg.norm(self.max_corner - self.min_corner) / 2.0)

    def contains_point(self, point: np.ndarray, tolerance: float) -> bool:
        return bool(
            np.all(point >= self.min_corner - tolerance) and np.all(point <= self.max_corner + tolerance)
        )


def _combined_bounds(meshes: Sequence["trimesh.Trimesh"]) -> _BoundingBox:
    mins = np.array([m.bounds[0] for m in meshes])
    maxs = np.array([m.bounds[1] for m in meshes])
    return _BoundingBox(min_corner=mins.min(axis=0), max_corner=maxs.max(axis=0))


def _look_at_matrix(eye: np.ndarray, target: np.ndarray, world_up: np.ndarray) -> np.ndarray:
    """Build a camera-to-world 4x4 transform (camera looks down local -Z, +Y up)."""
    z_axis = eye - target
    z_axis /= np.linalg.norm(z_axis)
    if abs(np.dot(z_axis, world_up)) > 0.999:
        # Looking straight along world_up (TOP/BOTTOM already pick a different
        # up vector, but guard against degenerate input regardless).
        world_up = np.array([1.0, 0.0, 0.0])
    x_axis = np.cross(world_up, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)

    matrix = np.eye(4)
    matrix[:3, 0] = x_axis
    matrix[:3, 1] = y_axis
    matrix[:3, 2] = z_axis
    matrix[:3, 3] = eye
    return matrix


def _build_camera(
    scene: "trimesh.Scene",
    bbox: _BoundingBox,
    camera_angle: CameraAngle,
    projection: ProjectionType,
    resolution: tuple[int, int],
) -> None:
    direction, up = _CAMERA_DIRECTIONS[camera_angle]
    direction_arr = np.array(direction, dtype=float)
    up_arr = np.array(up, dtype=float)

    radius = max(bbox.radius, 1e-3)  # guard against a zero-size focus set
    margin = 1.35

    if projection is ProjectionType.PERSPECTIVE:
        fov_degrees = 50.0
        distance = radius / math.sin(math.radians(fov_degrees / 2.0)) * margin
    else:
        # Orthographic approximation: a very small FOV at a large distance
        # converges to a parallel projection.
        fov_degrees = 0.5
        distance = radius / math.tan(math.radians(fov_degrees / 2.0)) * margin

    eye = bbox.center + direction_arr * distance
    # Assign the Camera (which registers its node in the scene graph) before
    # setting camera_transform -- camera_transform looks up the transform for
    # whatever camera node currently exists.
    scene.camera = trimesh.scene.cameras.Camera(
        resolution=resolution,
        fov=(fov_degrees, fov_degrees),
        z_near=max(0.01, distance - radius * 3.0),
        z_far=distance + radius * 3.0,
    )
    scene.camera_transform = _look_at_matrix(eye, bbox.center, up_arr)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def _feature_edges_path(mesh: "trimesh.Trimesh") -> Optional[Path3D]:
    """Sharp (dihedral-angle) edges plus open-boundary edges, as a Path3D.

    Deliberately not "every triangulation edge" -- a fully triangulated CSG
    mesh has a diagonal on every coplanar quad, which would make the wireframe
    unreadable. Only edges where two faces meet at a real angle count.
    """
    segments = []

    if len(mesh.face_adjacency_angles) > 0:
        threshold = math.radians(_EDGE_ANGLE_THRESHOLD_DEGREES)
        sharp = mesh.face_adjacency_angles > threshold
        sharp_edges = mesh.face_adjacency_edges[sharp]
        if len(sharp_edges) > 0:
            segments.append(mesh.vertices[sharp_edges])

    open_edges = trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1)
    if len(open_edges) > 0:
        boundary_edges = mesh.edges_sorted[open_edges]
        segments.append(mesh.vertices[boundary_edges])

    if not segments:
        return None
    all_segments = np.concatenate(segments, axis=0)  # (n, 2, 3)
    vertices = all_segments.reshape(-1, 3)
    entities = [Line(points=[2 * i, 2 * i + 1]) for i in range(len(all_segments))]
    # process=False: skip vertex-merging/graph traversal (needs scipy) -- not
    # needed since these lines are only ever drawn, never queried/simplified.
    return Path3D(entities=entities, vertices=vertices, process=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _render_scene_to_png_bytes(
    scene: "trimesh.Scene", resolution: tuple[int, int], visible: bool, background_color: tuple[int, int, int, int]
) -> bytes:
    """Equivalent to trimesh.Scene.save_image(), except window.close() is
    guarded against a known pyglet<2 macOS/Cocoa bug: SceneViewer is created
    with start_loop=False (never runs pyglet.app.run()), and on some pyglet
    1.5.x + macOS combinations that leaves CocoaAlternateEventLoop without a
    'platform_event_loop' attribute, which close()'s on_window_close handler
    then crashes on. The PNG bytes are already captured before close() runs,
    so the crash would otherwise discard a perfectly good render.
    """
    import pyglet
    from trimesh.util import BytesIO
    from trimesh.viewer.windowed import SceneViewer

    window = SceneViewer(
        scene,
        start_loop=False,
        visible=visible,
        resolution=resolution,
        background=background_color,
    )
    render = b""
    for save in (False, False, True):
        pyglet.clock.tick()
        window.switch_to()
        window.dispatch_events()
        window.dispatch_event("on_draw")
        window.flip()
        if save:
            file_obj = BytesIO()
            window.save_image(file_obj)
            file_obj.seek(0)
            render = file_obj.read()
    try:
        window.close()
    except AttributeError as exc:
        if "platform_event_loop" not in str(exc):
            raise
    return render


def render_frame_to_png(
    frame: Frame,
    output_path: Union[str, Path],
    *,
    render_mode: RenderMode = RenderMode.FULL_CUTS,
    focus_timbers: Optional[Sequence[Union[CutTimber, int]]] = None,
    unfocused_style: UnfocusedStyle = UnfocusedStyle.HIDDEN,
    camera_angle: CameraAngle = CameraAngle.ISO_FRONT_RIGHT,
    projection: ProjectionType = ProjectionType.PERSPECTIVE,
    geometry_style: GeometryStyle = GeometryStyle.SOLID,
    show_edges: bool = True,
    include_accessories: bool = True,
    resolution: tuple[int, int] = (1024, 768),
    background_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    visible: bool = True,
) -> Path:
    """Render a Frame to a PNG file, headlessly (see module docstring for caveats).

    Args:
        frame: The frame to render.
        output_path: Destination PNG path. Parent directories are created if needed.
        render_mode: FULL_CUTS renders each timber with all its cuts applied.
            BOUNDING_BOX renders each timber's get_perfect_timber_within_bounding_box_prism()
            instead (fast, no CSG triangulation).
        focus_timbers: CutTimber objects (or their .timber.ticket.kumiki_id ints), from
            this frame, to focus on. The camera frames only these timbers' combined
            bounding box. None (default) focuses the entire frame.
        unfocused_style: How timbers outside the focus set are shown. HIDDEN omits them
            entirely; GHOSTED renders them at low opacity for spatial context. Ignored
            when focus_timbers is None (everything is in focus).
        camera_angle: Fixed viewing direction; distance/target always auto-fit to the
            focused bounding box.
        projection: PERSPECTIVE or an ORTHOGRAPHIC approximation (see module docstring).
        geometry_style: SOLID, TRANSPARENT, or NONE (no faces -- combine with
            show_edges=True for a pure wireframe render) for all in-focus geometry.
        show_edges: Draw sharp/boundary edge lines over in-focus geometry.
        include_accessories: Include pegs/wedges/etc. Each accessory is treated as
            "in focus" if its position falls within (a small tolerance of) a focused
            timber's bounding box -- there is no direct accessory-to-timber link in
            the data model, so this is a geometric heuristic, not an exact mapping.
        resolution: Output image size in pixels (width, height).
        background_color: RGBA background color.
        visible: Passed through to trimesh's viewer. True (default) actually renders
            on most platforms but briefly shows a real window; False avoids the
            window but trimesh warns it can return a blank image on some platforms.

    Returns:
        The path written (same as output_path, as a Path).

    Raises:
        ImportError: If pyglet (the optional 'render' extra) is not installed.
        ValueError: If focus_timbers references a timber not in this frame, or the
            frame/focus set is empty.
    """
    if not _PYGLET_AVAILABLE:
        raise ImportError(
            "Headless PNG rendering requires pyglet. Install it with: pip install kumiki[render]"
        )

    focus_set = _resolve_focus_timbers(frame, focus_timbers)
    if not focus_set:
        raise ValueError("No timbers to render: frame has no cut_timbers")
    focus_ids = {id(ct) for ct in focus_set}
    everything_in_focus = not focus_timbers

    non_focus_set: List[CutTimber] = []
    if not everything_in_focus and unfocused_style is UnfocusedStyle.GHOSTED:
        non_focus_set = [ct for ct in frame.cut_timbers if id(ct) not in focus_ids]

    focus_meshes = [_cut_timber_to_trimesh(ct, render_mode) for ct in focus_set]
    focus_bbox = _combined_bounds(focus_meshes)

    scene = trimesh.Scene()

    def _set_face_color(mesh: "trimesh.Trimesh", rgba: tuple[int, int, int, int]) -> None:
        # trimesh's own type stubs don't model face_colors as settable with an
        # (n, 4) array, but this is exactly what trimesh's runtime expects.
        mesh.visual.face_colors = np.tile(np.array(rgba, dtype=np.uint8), (len(mesh.faces), 1))  # type: ignore[invalid-assignment]

    def _add_mesh(mesh: "trimesh.Trimesh", base_color: tuple[int, int, int, int], in_focus: bool) -> None:
        if in_focus:
            if geometry_style is not GeometryStyle.NONE:
                colored = mesh.copy()
                alpha = _TRANSPARENT_ALPHA if geometry_style is GeometryStyle.TRANSPARENT else base_color[3]
                _set_face_color(colored, (*base_color[:3], alpha))
                scene.add_geometry(colored)
            if show_edges:
                edges = _feature_edges_path(mesh)
                if edges is not None:
                    edges.colors = np.tile(_EDGE_COLOR, (len(edges.entities), 1))
                    scene.add_geometry(edges)
        else:
            if unfocused_style is UnfocusedStyle.GHOSTED:
                ghosted = mesh.copy()
                _set_face_color(ghosted, (*base_color[:3], _GHOSTED_ALPHA))
                scene.add_geometry(ghosted)
            # UnfocusedStyle.HIDDEN: nothing added.

    for mesh in focus_meshes:
        _add_mesh(mesh, _TIMBER_COLOR, in_focus=True)
    for ct in non_focus_set:
        _add_mesh(_cut_timber_to_trimesh(ct, render_mode), _TIMBER_COLOR, in_focus=False)

    if include_accessories:
        for accessory in frame.accessories:
            transform = getattr(accessory, "transform", None)
            position = np.array(transform.position, dtype=float).reshape(3) if transform is not None else None
            accessory_in_focus = everything_in_focus or (
                position is not None and focus_bbox.contains_point(position, _ACCESSORY_FOCUS_TOLERANCE)
            )
            if not accessory_in_focus and unfocused_style is UnfocusedStyle.HIDDEN:
                continue
            _add_mesh(_accessory_to_trimesh(accessory), _ACCESSORY_COLOR, in_focus=accessory_in_focus)

    _build_camera(scene, focus_bbox, camera_angle, projection, resolution)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    png_bytes = _render_scene_to_png_bytes(scene, resolution, visible, background_color)
    output_path.write_bytes(png_bytes)
    return output_path
