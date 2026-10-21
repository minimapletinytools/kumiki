"""A feature's span for measuring, cropped to where it exists. Shared by the runner and the solver."""

import math
from typing import Optional

import numpy as np

from ..csg.cutcsg import (CSGFeature, CutCSG, DerivedEdgeFeature, SimpleRectangularPrismEdgeFeature,
                          SimpleRectangularPrismFeature)
from ..csg.feature_extent import FeatureExtents
from ..csg.feature_paths import FeatureHandle
from ..geometry import Line, Plane, Point
from ..rule import as_ndarray, create_v3, unit_ndarray
from ..timber import PerfectTimberWithin
from .measure import LineSpan, MeasureSpan, PlaneSpan, PointSpan, VectorLike
from .sheet_shape import SheetLine, SheetPoint, sheet_shape

_UP = np.array([0.0, 0.0, 1.0])


def _unit_or_up(vector: np.ndarray) -> np.ndarray:
    """Return `vector` at unit length; a zero vector becomes up."""
    return unit_ndarray(vector, _UP)

def edge_outward_normal(feature: CSGFeature, owner: CutCSG, timber: PerfectTimberWithin) -> Optional[np.ndarray]:
    """Return the average of an edge's two faces' outward normals in world space, or None."""
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
    extents: Optional[FeatureExtents] = None,
    plane_normal: Optional[VectorLike] = None,
    in_three_d: bool = False,
) -> Optional[MeasureSpan]:
    """Return the feature's MeasureSpan in world space, or None if it can't be placed.

    Its extent comes from `extents` (the cut timber's, CutTimber.feature_extents); without them, or
    for an auxiliary line, the declared extent. With `plane_normal` (a sheet's view direction), a face seen edge-on is a line
    and otherwise a point, and a line seen end-on is a point. Without it, a face is a PlaneSpan.
    """
    feature, owner, timber = handle.feature, handle.owner, handle.timber
    located = feature.locate_simple_unbounded(owner)
    extents = extents if extents is not None else FeatureExtents(None, timber)

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
        if (extent is None or extent.is_empty) and extents.root is not None:
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
            region = tuple(tuple(create_v3(*world(create_v3(*as_ndarray(corner)))) for corner in polygon)
                           for polygon in extent.polygons())
            return PlaneSpan(at=create_v3(*at), normal=create_v3(*normal), region=region)
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
