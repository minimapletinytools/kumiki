"""What a drawing's 2D view can see, computed analytically.

- `hidden_at` / `drawn_over`: is what is under the pointer hidden (picking.drawing_candidates)?
- `nearest_visible_depth` / `visible_by_view`: can any of a feature be seen in a view?

Non-real features are never hidden. Only a solid's inside hides; a sight line along its surface
doesn't. A solid that can't be cut exactly counts as not hiding. Under the pointer, a feature drawn
over by a nearer one is also hidden; in a view it is kept.
"""

import warnings
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from ..csg.edges_on_csg import crop_line_to_interior_segments_on_csg
from ..csg.cutcsg import CSGFeature, CutCSG
from ..csg.feature_paths import FeatureHandle
from ..csg.identity_memo import memo_by_identity
from ..csg.cross_sections import (CannotCrossSection, PolygonRegions, PlaneFrame, area, material_crossing,
                                  segments_outside, shadow, subtract)
from ..geometry import Line, Plane, Point
from ..rule import Transform, V3, as_ndarray, create_v3, safe_dot_product, safe_normalize_vector
from ..timber import CutTimber
from .measure import ViewAxes
from .sheet_shape import SheetLine, SheetPoint, sheet_gap, sheet_shape

Geometry = Union[Point, Line, Plane]
from ..csg.feature_extent import FeatureExtent, extents_of, timber_reach

# TODO probably should make these relative to timber size if it's not alerady, i.e. epsilon per meter kinda deal
#: Material nearer the place than this is the surface it lies on, not something in front of it.
NUDGE = 1e-5
#: How far the line of sight is followed toward the camera. Only has to pass every solid.
REACH = 1e3


def sight_is_blocked(root: CutCSG, place: V3, toward_camera: V3) -> bool:
    """Return whether the inside of `root` lies between `place` and the camera, all in `root`'s local space.

    False if `root` can't be clipped exactly.
    """
    direction = safe_normalize_vector(toward_camera)
    inside = crop_line_to_interior_segments_on_csg(Line(direction=direction, point=place), root, seed_reach=REACH,
                                                   near=place)
    return any(max(float(safe_dot_product(end - place, direction)) for end in (piece.start, piece.end)) > NUDGE
               for piece in inside or [])


# A solid that may hide what is behind it: a drawn timber's tree, in its own local space, and where it is.
Occluder = Tuple[CutCSG, Transform]


def never_hidden(feature: CSGFeature) -> bool:
    """Return whether `feature` can't be hidden (it isn't real)."""
    return not feature.real


def hidden_at(place: np.ndarray, look: np.ndarray, occluders: Sequence[Occluder]) -> bool:
    """Return whether any occluder's material is between world `place` and the camera along `look`."""
    toward = create_v3(*(-np.asarray(look, dtype=float)))
    at = create_v3(*place)
    return any(sight_is_blocked(solid, placed.global_to_local(at), placed.global_to_local_direction(toward))
               for solid, placed in occluders)


def drawn_over(front: Optional[Geometry], behind: Optional[Geometry], look, tolerance: float) -> bool:
    """Return whether `front` is drawn where `behind` is, under one pointer (sheet_shape).

    Two lines: parallel. Two points: within `tolerance`. A point over a line: within `tolerance` of it.
    A line behind a point is still seen.
    """
    near, far = sheet_shape(front, look), sheet_shape(behind, look)
    if near is None or far is None or (isinstance(near, SheetPoint) and isinstance(far, SheetLine)):
        return False
    gap = sheet_gap(near, far, look)
    if isinstance(near, SheetLine) and isinstance(far, SheetLine):
        return gap is not None
    return gap is not None and gap <= tolerance


def _frame_in(transform: Transform, origin: np.ndarray, u: np.ndarray, v: np.ndarray,
              normal: np.ndarray) -> PlaneFrame:
    """Return a world plane frame in the local space of `transform`."""
    rotation, position = _placement(transform)
    return PlaneFrame.with_axes((origin - position) @ rotation, u @ rotation, v @ rotation, normal @ rotation)


@memo_by_identity
def _placement(transform: Transform) -> Tuple[np.ndarray, np.ndarray]:
    """Return a transform's rotation and position as float arrays."""
    return np.array(transform.orientation.matrix.tolist(), dtype=float), as_ndarray(transform.position)


def nearest_visible_depth(
    handle: FeatureHandle, root: CutCSG, look: np.ndarray, occluders: Sequence[Occluder], reach: float,
) -> Optional[float]:
    """Return the depth along `look` of the nearest visible part of the feature, or None if none of it is.

    `root` is the feature's own timber's tree; `occluders` include it. Only features drawn as a line
    or point are asked about. Non-real features are never hidden.
    """
    transform = handle.timber.transform
    located = handle.feature.locate_simple_unbounded(handle.owner)
    if not isinstance(located, (Plane, Line)):
        return None
    point = as_ndarray(transform.local_to_global(located.point))
    if never_hidden(handle.feature):
        return float(point @ look)
    shape = sheet_shape(located, as_ndarray(transform.global_to_local_direction(create_v3(*look))))
    if shape is None:
        return None  # a face seen at an angle: drawn as an area, not a line
    extent = extents_of(root, handle.timber).of(handle.feature, handle.owner)
    if extent is None:
        return float(point @ look)
    if isinstance(shape, SheetPoint):
        return _end_on_depth(extent, transform, look, occluders)
    if isinstance(located, Plane):
        normal = as_ndarray(transform.local_to_global_direction(located.normal))
    else:
        normal = np.cross(as_ndarray(transform.local_to_global_direction(located.direction)), look)
    normal /= np.linalg.norm(normal)
    across = np.cross(look, normal)
    # One frame per plane, whichever feature asks: its point nearest the world's origin.
    offset = float(normal @ point)
    origin = normal * offset
    world = (origin, across, look, normal)
    own = _frame_in(transform, *world)
    try:
        if isinstance(located, Plane):
            # The face's region on the finished surface, brought into this sight plane's frame.
            region = [[own.to_2d(corner) for corner in polygon] for polygon in extent.polygons()]
            if area(region) <= 0:
                return None
            corners = [point for polygon in region for point in polygon]
            blocked = _blocking(occluders, world, reach, _across_sheet(corners))
            visible = subtract(region, _overlapping(blocked, corners))
            depths = [y for polygon in visible for _x, y in polygon]
        else:
            to_2d = lambda end: tuple(float((as_ndarray(transform.local_to_global(create_v3(*end))) - origin) @ axis)
                                      for axis in (across, look))
            segments = [(to_2d(start), to_2d(end)) for start, end in extent.outline()]
            ends = [end for segment in segments for end in segment]
            if not ends:
                return None
            near = _overlapping(_blocking(occluders, world, reach, _across_sheet(ends)), ends)
            depths = [end[1] for segment in segments_outside(segments, near) for end in segment]
    except CannotCrossSection:
        return float(point @ look)
    return min(depths) + float(origin @ look) if depths else None


def _across_sheet(points: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """Return the (low, high) u range of `points`, slightly widened."""
    return min(p[0] for p in points) - 1e-6, max(p[0] for p in points) + 1e-6


def _overlapping(region: PolygonRegions, points: Sequence[Tuple[float, float]]) -> PolygonRegions:
    """Return the pieces of `region` whose bounding box overlaps that of `points`."""
    if not points:
        return []
    low_x, high_x = min(p[0] for p in points), max(p[0] for p in points)
    low_y, high_y = min(p[1] for p in points), max(p[1] for p in points)
    return [polygon for polygon in region
            if min(p[0] for p in polygon) <= high_x and max(p[0] for p in polygon) >= low_x
            and min(p[1] for p in polygon) <= high_y and max(p[1] for p in polygon) >= low_y]


def _blocking(occluders: Sequence[Occluder], world: Tuple[np.ndarray, ...], reach: float,
              across: Tuple[float, float]) -> PolygonRegions:
    """Return what the occluders hide in the frame's plane within the `across` strip: their material swept away from the camera."""
    origin, u, _v, normal = world
    hidden: PolygonRegions = []
    for solid, transform in occluders:
        corners = _world_corners(solid, transform)
        if corners is not None:
            # Its box clear of the plane, or of the strip: nothing of it can be in the way.
            side = (corners - origin) @ normal
            spread = (corners - origin) @ u
            if (side.min() > _CLEAR or side.max() < -_CLEAR
                    or spread.max() < across[0] - _CLEAR or spread.min() > across[1] + _CLEAR):
                continue
        try:
            hidden += shadow(material_crossing(solid, _frame_in(transform, *world), reach, across), 2 * reach)
        except CannotCrossSection:
            continue  # unsure means seen
    return hidden


#: How far clear of a plane a box must be to be skipped, so one merely touching it is still cut.
_CLEAR = 1e-6


def _world_corners(solid: CutCSG, transform: Transform) -> Optional[np.ndarray]:
    """Return the eight world corners of `solid`'s bounding box, or None if infinite. Cached."""
    memo = _corners_memo(solid)
    if id(transform) not in memo:
        memo[id(transform)] = (transform, _work_out_corners(solid, transform))
    return memo[id(transform)][1]


@memo_by_identity
def _corners_memo(solid: CutCSG) -> Dict[int, Tuple[Transform, Optional[np.ndarray]]]:
    return {}


def _work_out_corners(solid: CutCSG, transform: Transform) -> Optional[np.ndarray]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        box = solid.get_aabb()
    ends = [box.min_x, box.min_y, box.min_z, box.max_x, box.max_y, box.max_z]
    if box.is_empty:
        return None
    floats = [float(end) for end in ends if end is not None]
    if len(floats) != 6:
        return None
    low, high = floats[:3], floats[3:]
    rotation, position = _placement(transform)
    local = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    return local @ rotation.T + position


def _end_on_depth(extent: FeatureExtent, transform: Transform, look: np.ndarray,
                  occluders: Sequence[Occluder]) -> Optional[float]:
    """Return the depth of a line seen end-on, if the sight line from its nearest end is clear."""
    ends = [as_ndarray(transform.local_to_global(create_v3(*end))) for piece in extent.outline() for end in piece]
    if not ends:
        return None
    nearest = min(ends, key=lambda end: float(end @ look))
    return None if hidden_at(nearest, look, occluders) else float(nearest @ look)


def visible_by_view(
    anchors: Sequence[FeatureHandle], views: Mapping[str, ViewAxes], drawn: Sequence[CutTimber],
) -> Dict[str, List[FeatureHandle]]:
    """Return, per view, the anchors it can see some of.

    Every timber in `drawn` may hide the others. An anchor drawn on the same line as a nearer one is kept.
    """
    occluders = [(cut.render_timber_with_cuts_csg_local(), cut.timber.transform) for cut in drawn]
    roots = {id(cut.timber): cut.render_timber_with_cuts_csg_local() for cut in drawn}
    reach = max((timber_reach(cut.timber) for cut in drawn), default=4.0)
    visible: Dict[str, List[FeatureHandle]] = {}
    for view, axes in views.items():
        look = as_ndarray(axes.look)
        look /= np.linalg.norm(look)
        visible[view] = [handle for handle in anchors if id(handle.timber) in roots
                         and nearest_visible_depth(handle, roots[id(handle.timber)], look, occluders, reach)
                         is not None]
    return visible
