"""What a drawing's view can see: whether a place, or any of a feature, is hidden behind material.

Two questions, one set of rules:

- PER PLACE, for a pointer: is what is under it hidden? `hidden_at` a place, and a feature
  `drawn_over` by a nearer one there (picking.split_hidden).
- PER FEATURE, for a view: can any of it be seen? `nearest_visible_depth` (visible_by_view).

The rules both keep: a feature that is not real (a bore's axis, a centerplane) is `never_hidden`;
only a solid's inside hides, and a line of sight along its surface does not; unsure -- a solid that
cannot be cut exactly -- means seen. The one difference: under a pointer, a feature drawn over by a
nearer one is hidden too, so a click takes what is on top; a view keeps it, since two timbers' tops
in line are dimensioned at the one line both draw.

Analytic, over the whole CSG, not sampled: a place's line of sight is clipped exactly to the solid
(cropcsg), and a feature drawn as a line is decided in the one plane holding all its lines of sight,
cut exactly by each solid (cross_sections).
"""

from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from ..csg.cropcsg import crop_line_to_boundary_segments_on_csg, crop_line_to_interior_segments_on_csg
from ..csg.cutcsg import CSGFeature, CutCSG
from ..csg.feature_paths import FeatureHandle
from ..csg.cross_sections import (CannotCrossSection, PolygonRegions, SightFrame, area, material_crossing,
                                  segments_outside, shadow, subtract)
from ..geometry import Line, Plane, Point
from ..rule import Transform, V3, as_ndarray, create_v3, safe_dot_product, safe_normalize_vector
from ..timber import CutTimber
from .drawing import ViewAxes
from .sheet_shape import SQUARE_TO_VIEW, SheetLine, SheetPoint, sheet_shape

Geometry = Union[Point, Line, Plane]
from ..csg.feature_extent import extents_of

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


def never_hidden(feature: CSGFeature) -> bool:
    """Whether nothing can hide `feature`: one that is not real names no material, so it is drawn
    wherever it is."""
    return not feature.real


def hidden_at(place: np.ndarray, look: np.ndarray, occluders: Sequence[Occluder]) -> bool:
    """Whether any occluder's material lies between `place` and the camera, looking along `look`
    (both world space)."""
    toward = create_v3(*(-np.asarray(look, dtype=float)))
    at = create_v3(*place)
    return any(sight_is_blocked(solid, placed.global_to_local(at), placed.global_to_local_direction(toward))
               for solid, placed in occluders)


def drawn_over(front: Optional[Geometry], behind: Optional[Geometry], look, tolerance: float) -> bool:
    """Whether `front` is drawn where `behind` is on the sheet, both under one pointer (sheet_shape).

    Two lines under one pointer cross it, so parallel is on top of each other; two points, within
    `tolerance`; a point under a line, within `tolerance` of it. A line behind a point is seen
    either side of it. All in one frame.
    """
    look = as_ndarray(look)
    look = look / np.linalg.norm(look)
    near, far = sheet_shape(front, look), sheet_shape(behind, look)
    if near is None or far is None:
        return False

    def across(vector: np.ndarray, axis: np.ndarray) -> np.ndarray:
        return vector - axis * float(vector @ axis)

    if isinstance(near, SheetLine) and isinstance(far, SheetLine):
        return float(np.linalg.norm(np.cross(near.run, far.run))) <= SQUARE_TO_VIEW
    if isinstance(far, SheetPoint) and isinstance(near, SheetPoint):
        return float(np.linalg.norm(across(far.at - near.at, look))) <= tolerance
    if isinstance(far, SheetPoint) and isinstance(near, SheetLine):
        return float(np.linalg.norm(across(across(far.at - near.at, look), near.run))) <= tolerance
    return False


def _frame_in(transform: Transform, origin: np.ndarray, u: np.ndarray, v: np.ndarray,
              normal: np.ndarray) -> SightFrame:
    """A world-space plane frame, in the local space of something placed by `transform`."""
    local = lambda direction: as_ndarray(transform.global_to_local_direction(create_v3(*direction)))
    return (as_ndarray(transform.global_to_local(create_v3(*origin))), local(u), local(v), local(normal))


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
    point = as_ndarray(transform.local_to_global(located.point))
    if never_hidden(handle.feature):
        return float(point @ look)
    shape = sheet_shape(located, as_ndarray(transform.global_to_local_direction(create_v3(*look))))
    if shape is None:
        return None  # a face seen at an angle: drawn as an area, not a line
    if isinstance(shape, SheetPoint):
        return _end_on_depth(located, root, transform, look, occluders, reach)
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
            # The face's region on the finished surface: its extent, kept for the tree and so shared
            # by every view that asks, brought into this sight plane's frame.
            extent = extents_of(root, handle.timber).of(handle.feature, handle.owner)
            if extent is None:
                return float(point @ look)
            frame_origin, frame_u, frame_v = own[0], own[1], own[2]
            region = [[(float((corner - frame_origin) @ frame_u), float((corner - frame_origin) @ frame_v))
                       for corner in polygon] for polygon in extent.polygons()]
            if area(region) <= 0:
                return None
            corners = [point for polygon in region for point in polygon]
            blocked = _blocking(occluders, world, reach, _across_sheet(corners))
            visible = subtract(region, _overlapping(blocked, corners))
            depths = [y for polygon in visible for _x, y in polygon]
        else:
            pieces = crop_line_to_boundary_segments_on_csg(located, root, seed_reach=reach, near=located.point)
            if pieces is None:
                return float(point @ look)
            to_2d = lambda end: tuple(float((as_ndarray(transform.local_to_global(end)) - origin) @ axis)
                                      for axis in (across, look))
            segments = [(to_2d(piece.start), to_2d(piece.end)) for piece in pieces]
            ends = [end for segment in segments for end in segment]
            if not ends:
                return None
            near = _overlapping(_blocking(occluders, world, reach, _across_sheet(ends)), ends)
            depths = [end[1] for segment in segments_outside(segments, near) for end in segment]
    except CannotCrossSection:
        return float(point @ look)
    return min(depths) + float(origin @ look) if depths else None


def _across_sheet(points: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """How far `points` reach across the sheet (u), a little widened so an edge on its border counts."""
    return min(p[0] for p in points) - 1e-6, max(p[0] for p in points) + 1e-6


def _overlapping(region: PolygonRegions, points: Sequence[Tuple[float, float]]) -> PolygonRegions:
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
              across: Tuple[float, float]) -> PolygonRegions:
    """What the occluders hide in the world frame's plane, within the `across` strip of it: their
    material across it, swept away from the camera."""
    hidden: PolygonRegions = []
    for solid, transform in occluders:
        try:
            hidden += shadow(material_crossing(solid, _frame_in(transform, *world), reach, across), 2 * reach)
        except CannotCrossSection:
            continue  # unsure means seen
    return hidden


def _end_on_depth(line: Line, root: CutCSG, transform: Transform, look: np.ndarray,
                  occluders: Sequence[Occluder], reach: float) -> Optional[float]:
    """A line seen end-on draws as a point: seen if the sight line from its nearest end is clear."""
    pieces = crop_line_to_boundary_segments_on_csg(line, root, seed_reach=reach, near=line.point)
    if not pieces:
        return None if pieces is not None else float(as_ndarray(transform.local_to_global(line.point)) @ look)
    ends = [as_ndarray(transform.local_to_global(end)) for piece in pieces for end in (piece.start, piece.end)]
    nearest = min(ends, key=lambda end: float(end @ look))
    return None if hidden_at(nearest, look, occluders) else float(nearest @ look)


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
        look = as_ndarray(axes.look)
        look /= np.linalg.norm(look)
        visible[view] = [handle for handle in anchors if id(handle.timber) in roots
                         and nearest_visible_depth(handle, roots[id(handle.timber)], look, occluders, reach)
                         is not None]
    return visible
