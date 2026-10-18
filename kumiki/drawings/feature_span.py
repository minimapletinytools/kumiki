"""Where a feature is, for measuring: its span, cropped to where it exists.

One answer for the viewer (kigumi's runner) and the feature solver, so the length one draws
is the length the other solves with.
"""

import math
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from ..csg.cropcsg import approximately_crop_plane_to_area_on_csg, crop_line_to_segments_on_csg
from ..csg.cutcsg import (CSGFeature, CutCSG, DerivedEdgeFeature, SimpleRectangularPrismEdgeFeature,
                          SimpleRectangularPrismFeature)
from ..csg.feature_paths import FeatureHandle
from ..geometry import Line, Plane, Point
from ..rule import Matrix, as_ndarray, create_v3, exact_scalar, scalar, unit_ndarray
from ..timber import PerfectTimberWithin
from .drawing import ALIGNMENT_EPSILON, LineSpan, MeasureSpan, PlaneSpan, PointSpan, VectorLike

#: Stations along a line, low then high.
Interval = Tuple[float, float]



_UP = np.array([0.0, 0.0, 1.0])


def _unit_or_up(vector: np.ndarray) -> np.ndarray:
    """At length one; a zero vector is taken as up, so a degenerate span still has a direction."""
    return unit_ndarray(vector, _UP)

def _station(located: Line, point) -> float:
    return float(((point - located.point).T * located.direction)[0, 0])


def intersected_intervals(one: Sequence[Interval], other: Sequence[Interval]) -> List[Interval]:
    """The stretches covered by both. Ones that only touch are dropped: a point is not a piece of a line."""
    return [(max(a[0], b[0]), min(a[1], b[1])) for a in one for b in other if max(a[0], b[0]) < min(a[1], b[1])]


def declared_line_span(feature: CSGFeature, owner: CutCSG, located: Line) -> Optional[Interval]:
    """Where a feature says its own line ends, as an interval along it, or None.

    Exact, and asked of the feature rather than found by clipping, so there is no inside test at a
    boundary to go wrong.
    """
    extent = feature.get_extent(owner)
    ends = getattr(extent, "ends", None) if extent is not None else None
    if not ends:
        return None
    reach = sorted(_station(located, end) for end in ends)
    return (reach[0], reach[-1])


def line_intervals(located: Line, csg: CutCSG, reach: float, near) -> Optional[List[Interval]]:
    """Where a line lies on one solid, as intervals along its own direction; None if the solid cannot say."""
    pieces = crop_line_to_segments_on_csg(located, csg, seed_reach=reach, near=near)
    if pieces is None:
        return None
    return [(min(a, b), max(a, b))
            for a, b in ((_station(located, piece.start), _station(located, piece.end)) for piece in pieces)]


def line_pieces(
    located: Line, solids: Sequence[Optional[CutCSG]], reach: float, near, declared: Optional[Interval] = None,
) -> List[Interval]:
    """Where a line lies on all of these solids, within `declared` if given, as intervals along it.

    A solid that cannot answer is skipped rather than treated as empty.
    """
    intervals: Optional[List[Interval]] = [declared] if declared is not None else None
    for solid in solids:
        if solid is None:
            continue
        found = line_intervals(located, solid, reach, near)
        if found is None:
            continue
        intervals = found if intervals is None else intersected_intervals(intervals, found)
    return intervals or []


def edge_outward_normal(feature: CSGFeature, owner: CutCSG, timber: PerfectTimberWithin) -> Optional[np.ndarray]:
    """Which way is out of the material across an edge, in world space, or None.

    The average of the two faces' outward normals. Only decides which of two supplementary angles
    is meant, so None is a fair answer.
    """
    located = []
    if isinstance(feature, DerivedEdgeFeature):
        located = [parent.locate_simple_unbounded() for parent in feature.parents if parent is not None]
    elif isinstance(feature, SimpleRectangularPrismEdgeFeature):
        located = [SimpleRectangularPrismFeature(name=feature.name, face=face).locate_simple_unbounded(owner)
                   for face in feature.faces]
    normals = [_unit_or_up(as_ndarray(timber.transform.local_to_global_direction(found.normal)))
               for found in located if isinstance(found, Plane)]
    if len(normals) != 2:
        return None
    total = normals[0] + normals[1]
    if not np.any(np.abs(total) > 1e-9):
        return None  # two faces looking opposite ways form no edge
    return _unit_or_up(total)


def projects_to_a_point(direction: Union[VectorLike, np.ndarray], plane_normal: VectorLike) -> bool:
    """Whether a line seen from this plane draws as a point, by the same threshold the viewer projects by."""
    return abs(float(_unit_or_up(as_ndarray(direction)) @ _unit_or_up(as_ndarray(plane_normal)))) > 1 - ALIGNMENT_EPSILON


def feature_span(
    handle: FeatureHandle,
    root_csg: Optional[CutCSG] = None,
    plane_normal: Optional[VectorLike] = None,
    in_three_d: bool = False,
) -> Optional[MeasureSpan]:
    """What a feature is, where the measurement is being taken, in world space.

    The extent comes from what the feature occupies once cropped to the timber (`root_csg`, the cut
    timber's tree the handle points into), not from what declared it. A line not on any timber -- a
    bore's axis, or any line when `root_csg` is None -- is bounded by its own extent.

    ON A SHEET (`plane_normal`, the view direction) a face is measurable only seen edge-on, where it
    draws as a line along itself; at an angle it falls back to a point. A line seen end-on is a point.
    IN THE SOLID nothing is projected away: a face is a PlaneSpan, an edge stays an edge.

    None when the feature cannot be placed.
    """
    feature, owner, timber = handle.feature, handle.owner, handle.timber
    located = feature.locate_simple_unbounded(owner)

    def world(point) -> np.ndarray:
        return as_ndarray(timber.transform.local_to_global(point))

    if isinstance(located, Point):
        return PointSpan(at=create_v3(*world(located.position)))

    solid = timber.get_perfect_timber_within_csg_local()
    reach = float(timber.length) * 4

    if isinstance(located, Line):
        # Where the feature itself says it ends, and where the timber leaves it -- but not for a
        # non-real line, which lies where there is no timber.
        solids = [root_csg] if root_csg is not None and feature.real else []
        pieces = line_pieces(located, solids, reach, solid.transform.position,
                             declared=declared_line_span(feature, owner, located))
        if not pieces:
            return None
        # The longest: a cut can leave an edge in several, and the biggest is the one a reader points at.
        low, high = max(pieces, key=lambda piece: piece[1] - piece[0])
        start = world(located.point + located.direction * exact_scalar(low))
        end = world(located.point + located.direction * exact_scalar(high))
        direction = _unit_or_up(end - start)
        if not in_three_d and plane_normal is not None and projects_to_a_point(direction, plane_normal):
            return PointSpan(at=create_v3(*(start + end) / 2))
        outward = edge_outward_normal(feature, owner, timber)
        return LineSpan(at=create_v3(*start), direction=create_v3(*direction), interval=(0.0, math.dist(start, end)),
                        outward=None if outward is None else create_v3(*outward))

    if isinstance(located, Plane):
        cropped = approximately_crop_plane_to_area_on_csg(
            located, [owner, solid], seed_reach=reach, near=solid.transform.position)
        if cropped is None or cropped.is_empty:
            # A face on the timber's own boundary -- a tenon's end, flush with the end of the piece --
            # crops to nothing against it. Its own primitive still bounds it.
            cropped = approximately_crop_plane_to_area_on_csg(
                located, [owner], seed_reach=reach, near=solid.transform.position)
        if cropped is None or cropped.is_empty:
            return None
        middle = cropped.centroid()
        if middle is None:
            return None
        at = world(middle)
        normal = _unit_or_up(as_ndarray(timber.transform.local_to_global_direction(located.normal)))
        if in_three_d:
            return PlaneSpan(at=create_v3(*at), normal=create_v3(*normal))
        if plane_normal is None:
            return PointSpan(at=create_v3(*at))
        # Edge-on, it draws as a line along the face, square to its normal and to the view.
        along = np.cross(normal, _unit_or_up(as_ndarray(plane_normal)))
        if not np.any(np.abs(along) > 1e-9) or not cropped.boundary:
            return PointSpan(at=create_v3(*at))  # facing the reader: it covers the view
        along = _unit_or_up(along)
        # The region is timber-local and the direction world, so the boundary is brought over.
        stations = [float(world(corner) @ along) for corner in cropped.boundary]
        here = float(at @ along)
        return LineSpan(at=create_v3(*at), direction=create_v3(*along), interval=(min(stations) - here, max(stations) - here))

    return None
