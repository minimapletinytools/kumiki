"""What a drawing's view can see: whether a place, or any of a feature, is hidden behind material.

Analytic, over the whole CSG, not sampled: a place's line of sight is clipped exactly to the solid
(cropcsg), and a feature drawn as a line is decided in the one plane holding all its lines of sight,
cut exactly by each solid (planar_region). Only a solid's inside hides; a line of sight along its
surface does not.
"""

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..csg.cropcsg import crop_line_to_boundary_segments_on_csg, crop_line_to_interior_segments_on_csg
from ..csg.cutcsg import CutCSG, FaceFeature
from ..csg.feature_paths import FeatureHandle
from ..csg.planar_region import (CannotSection, Region, SightFrame, area, face_on_surface, material_crossing,
                                 segments_outside, shadow, subtract)
from ..geometry import Line, Plane
from ..rule import Transform, V3, create_v3, safe_dot_product, safe_normalize_vector
from ..timber import CutTimber
from .drawing import ViewAxes

#: Material nearer the place than this is the surface it lies on, not something in front of it.
NUDGE = 1e-5
#: How far the line of sight is followed toward the camera. Only has to pass every solid.
REACH = 1e3


def sight_is_blocked(root: CutCSG, place: V3, toward_camera: V3) -> bool:
    """Whether the inside of *root* lies between *place* and the camera.

    Args:
        root: the solid that may be in the way, in its own local space.
        place: where the feature is, in that same space.
        toward_camera: the direction from *place* to the camera, in that same space.

    False when *root* cannot be clipped exactly (a curved primitive other than a cylinder).
    """
    direction = safe_normalize_vector(toward_camera)
    inside = crop_line_to_interior_segments_on_csg(Line(direction=direction, point=place), root, seed_reach=REACH,
                                                   near=place)
    return any(max(float(safe_dot_product(end - place, direction)) for end in (piece.start, piece.end)) > NUDGE
               for piece in inside or [])


# A solid that may hide what is behind it: a drawn timber's tree, in its own local space, and where it is.
Occluder = Tuple[CutCSG, Transform]


def _np(vector: V3) -> np.ndarray:
    return np.array([float(vector[i, 0]) for i in range(3)])


def _frame_in(transform: Transform, origin: np.ndarray, u: np.ndarray, v: np.ndarray,
              normal: np.ndarray) -> SightFrame:
    """A world-space plane frame, in the local space of something placed by `transform`."""
    local = lambda direction: _np(transform.global_to_local_direction(create_v3(*direction)))
    return (_np(transform.global_to_local(create_v3(*origin))), local(u), local(v), local(normal))


def nearest_visible_depth(
    handle: FeatureHandle, root: CutCSG, look: np.ndarray, occluders: Sequence[Occluder], reach: float,
) -> Optional[float]:
    """How near the camera any of `handle`'s feature can be seen, looking along unit `look`; None if
    none of it can.

    Depth is distance along `look`, in world space. `root` is the feature's own timber's tree, which
    says where the feature is on the finished surface; `occluders` are every solid that may be in
    the way, that tree included. Only a face seen edge-on or a line lying along or across the sheet
    is asked about, as only those draw as a line or a point. Not real (a bore's axis, a centerplane):
    never hidden. Unsure -- a solid that cannot be cut exactly -- means seen.

    Only the strip of the plane the feature spans across the sheet is cut: nothing beside it can
    stand between it and the camera.
    """
    transform = handle.timber.transform
    located = handle.feature.locate_simple_unbounded(handle.owner)
    if not isinstance(located, (Plane, Line)):
        return None
    point = _np(transform.local_to_global(located.point))
    if not handle.feature.real:
        return float(point @ look)
    if isinstance(located, Plane):
        normal = _np(transform.local_to_global_direction(located.normal))
    else:
        run = _np(transform.local_to_global_direction(located.direction))
        run /= np.linalg.norm(run)
        if abs(abs(float(run @ look)) - 1) < 1e-9:
            return _end_on_depth(located, root, transform, look, occluders, reach)
        normal = np.cross(run, look)
    normal /= np.linalg.norm(normal)
    if abs(float(normal @ look)) > 1e-9:
        return None  # seen at an angle: drawn as an area, not a line
    across = np.cross(look, normal)
    # One frame per plane, whichever feature asks: its point nearest the world's origin.
    offset = float(normal @ point)
    origin = normal * offset
    world = (origin, across, look, normal)
    own = _frame_in(transform, *world)
    try:
        if isinstance(located, Plane):
            region = face_on_surface(handle, root, own, reach)
            if area(region) <= 0:
                return None
            corners = [point for polygon in region for point in polygon]
            blocked = _blocking(occluders, world, reach, _span(corners))
            visible = subtract(region, _overlapping(blocked, corners))
            depths = [y for polygon in visible for _x, y in polygon]
        else:
            pieces = crop_line_to_boundary_segments_on_csg(located, root, seed_reach=reach, near=located.point)
            if pieces is None:
                return float(point @ look)
            to_2d = lambda end: tuple(float((_np(transform.local_to_global(end)) - origin) @ axis)
                                      for axis in (across, look))
            segments = [(to_2d(piece.start), to_2d(piece.end)) for piece in pieces]
            ends = [end for segment in segments for end in segment]
            if not ends:
                return None
            near = _overlapping(_blocking(occluders, world, reach, _span(ends)), ends)
            depths = [end[1] for segment in segments_outside(segments, near) for end in segment]
    except CannotSection:
        return float(point @ look)
    return min(depths) + float(origin @ look) if depths else None


def _span(points: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """How far `points` reach across the sheet (u), a little widened so an edge on its border counts."""
    return min(p[0] for p in points) - 1e-6, max(p[0] for p in points) + 1e-6


def _overlapping(region: Region, points: Sequence[Tuple[float, float]]) -> Region:
    """The pieces of `region` whose bounding box meets that of `points`: the only ones that can
    hide any of them. Most shadows in a plane are nowhere near the feature asked about."""
    if not points:
        return []
    low_x, high_x = min(p[0] for p in points), max(p[0] for p in points)
    low_y, high_y = min(p[1] for p in points), max(p[1] for p in points)
    return [polygon for polygon in region
            if min(p[0] for p in polygon) <= high_x and max(p[0] for p in polygon) >= low_x
            and min(p[1] for p in polygon) <= high_y and max(p[1] for p in polygon) >= low_y]


def _blocking(occluders: Sequence[Occluder], world: Tuple[np.ndarray, ...], reach: float,
              across: Tuple[float, float]) -> Region:
    """What the occluders hide in the world frame's plane, within the `across` strip of it: their
    material across it, swept away from the camera."""
    hidden: Region = []
    for solid, transform in occluders:
        try:
            hidden += shadow(material_crossing(solid, _frame_in(transform, *world), reach, across), 2 * reach)
        except CannotSection:
            continue  # unsure means seen
    return hidden


def _end_on_depth(line: Line, root: CutCSG, transform: Transform, look: np.ndarray,
                  occluders: Sequence[Occluder], reach: float) -> Optional[float]:
    """A line seen end-on draws as a point: seen if the sight line from its nearest end is clear."""
    pieces = crop_line_to_boundary_segments_on_csg(line, root, seed_reach=reach, near=line.point)
    if not pieces:
        return None if pieces is not None else float(_np(transform.local_to_global(line.point)) @ look)
    ends = [_np(transform.local_to_global(end)) for piece in pieces for end in (piece.start, piece.end)]
    nearest = min(ends, key=lambda end: float(end @ look))
    toward = create_v3(*(-look))
    for solid, placed in occluders:
        if sight_is_blocked(solid, placed.global_to_local(create_v3(*nearest)), placed.global_to_local_direction(toward)):
            return None
    return float(nearest @ look)


def visible_by_view(
    anchors: Sequence[FeatureHandle], views: Mapping[str, ViewAxes], drawn: Sequence[CutTimber],
) -> Dict[str, List[FeatureHandle]]:
    """For each view, the anchors it can see some of: what a measurement in it may be taken to.

    `drawn` are the timbers the views draw, every one of which may hide the others. Only material
    hides: an anchor drawn on the same line as a nearer one is still drawn there, so it is kept --
    two timbers' tops in line are dimensioned at the one line both draw.
    """
    occluders = [(cut.render_timber_with_cuts_csg_local(), cut.timber.transform) for cut in drawn]
    roots = {id(cut.timber): cut.render_timber_with_cuts_csg_local() for cut in drawn}
    reach = 4 * max((float(cut.timber.length) + float(max(cut.timber.size[0], cut.timber.size[1]))
                     for cut in drawn), default=1.0)
    visible: Dict[str, List[FeatureHandle]] = {}
    for view, axes in views.items():
        look = _np(axes.look)
        look /= np.linalg.norm(look)
        visible[view] = [handle for handle in anchors if id(handle.timber) in roots
                         and nearest_visible_depth(handle, roots[id(handle.timber)], look, occluders, reach)
                         is not None]
    return visible
