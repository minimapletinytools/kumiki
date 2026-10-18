"""Where a feature is, for measuring: its span, cropped to where it exists.

One answer for the viewer (kigumi's runner) and the feature solver, so the length one draws
is the length the other solves with.
"""

import math
from typing import Optional

import numpy as np

from ..csg.cutcsg import (CSGFeature, CutCSG, DerivedEdgeFeature, SimpleRectangularPrismEdgeFeature,
                          SimpleRectangularPrismFeature)
from ..csg.feature_extent import FeatureExtents, extents_of
from ..csg.feature_paths import FeatureHandle
from ..geometry import Line, Plane, Point
from ..rule import as_ndarray, create_v3, unit_ndarray
from ..timber import PerfectTimberWithin
from .drawing import LineSpan, MeasureSpan, PlaneSpan, PointSpan, VectorLike
from .sheet_shape import SheetLine, SheetPoint, sheet_shape

_UP = np.array([0.0, 0.0, 1.0])


def _unit_or_up(vector: np.ndarray) -> np.ndarray:
    """At length one; a zero vector is taken as up, so a degenerate span still has a direction."""
    return unit_ndarray(vector, _UP)

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


def feature_span(
    handle: FeatureHandle,
    root_csg: Optional[CutCSG] = None,
    plane_normal: Optional[VectorLike] = None,
    in_three_d: bool = False,
) -> Optional[MeasureSpan]:
    """What a feature is, where the measurement is being taken, in world space.

    The extent is the feature's FeatureExtent: what it occupies once cropped to the timber
    (`root_csg`, the cut timber's tree the handle points into). With no `root_csg`, or for a line
    not on any timber (a bore's axis), it is what declared the feature.

    ON A SHEET (`plane_normal`, the view direction) a face is measurable only seen edge-on, where it
    draws as a line along itself; at an angle it falls back to a point. A line seen end-on is a point.
    IN THE SOLID nothing is projected away: a face is a PlaneSpan, an edge stays an edge.

    None when the feature cannot be placed.
    """
    feature, owner, timber = handle.feature, handle.owner, handle.timber
    located = feature.locate_simple_unbounded(owner)
    extents = extents_of(root_csg, timber) if root_csg is not None else FeatureExtents(None, timber)

    def world(point) -> np.ndarray:
        return as_ndarray(timber.transform.local_to_global(point))

    if isinstance(located, Point):
        return PointSpan(at=create_v3(*world(located.position)))

    if isinstance(located, Line):
        # Its extent: where the feature itself says it ends, and where the timber leaves it -- but
        # not for a line in a void, which lies where there is no timber.
        extent = extents.of(feature, owner)
        pieces = list(extent.pieces) if extent is not None else []
        if not pieces:
            return None
        # The longest: a cut can leave an edge in several, and the biggest is the one a reader points at.
        low, high = max(pieces, key=lambda piece: piece[1] - piece[0])
        start = world(located.point + located.direction * float(low))
        end = world(located.point + located.direction * float(high))
        direction = _unit_or_up(end - start)
        if not in_three_d and plane_normal is not None and isinstance(
                sheet_shape(Line(direction=create_v3(*direction), point=create_v3(*start)), plane_normal), SheetPoint):
            return PointSpan(at=create_v3(*(start + end) / 2))
        outward = edge_outward_normal(feature, owner, timber)
        return LineSpan(at=create_v3(*start), direction=create_v3(*direction), interval=(0.0, math.dist(start, end)),
                        outward=None if outward is None else create_v3(*outward))

    if isinstance(located, Plane):
        # Its extent on the cut timber -- or, with no cut timber or cut away entirely, all of what declared it.
        extent = extents.of(feature, owner)
        if (extent is None or extent.is_empty) and root_csg is not None:
            extent = FeatureExtents(None, timber).of(feature, owner)
        if extent is None or extent.is_empty:
            return None
        middle = extent.anchor()
        if middle is None:
            return None
        boundary = [corner for polygon in extent.polygons() for corner in polygon]
        middle = create_v3(*middle)
        at = world(middle)
        normal = _unit_or_up(as_ndarray(timber.transform.local_to_global_direction(located.normal)))
        if in_three_d:
            return PlaneSpan(at=create_v3(*at), normal=create_v3(*normal))
        if plane_normal is None:
            return PointSpan(at=create_v3(*at))
        # Edge-on, it draws as a line along the face, square to its normal and to the view.
        shape = sheet_shape(Plane(normal=create_v3(*normal), point=create_v3(*at)), plane_normal)
        if not isinstance(shape, SheetLine) or not boundary:
            return PointSpan(at=create_v3(*at))  # seen at an angle: it covers the view
        along = shape.run
        # The region is timber-local and the direction world, so the boundary is brought over.
        stations = [float(world(create_v3(*as_ndarray(corner))) @ along) for corner in boundary]
        here = float(at @ along)
        return LineSpan(at=create_v3(*at), direction=create_v3(*along), interval=(min(stations) - here, max(stations) - here))

    return None
