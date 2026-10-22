"""A feature's extent on its cut timber: the part of it that is actually there.

Computed in the timber's local space from the cut timber's tree (`root`), by FeatureNature:

- REAL: a face's part on the finished surface; a line's pieces where the surface creases along it
  (a real edge), within its parent faces' solids and its declared ends.
- PERFECT_REFERENCE: a plane or line cropped to the solid.
- AUXILIARY (e.g. a bore's axis): its own declared extent, not cropped.

A point is just itself. Used for dimension anchors, highlight outlines and visibility.
"""

import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from .edges_on_csg import crop_line_to_crease_segments_on_csg, crop_line_to_segments_on_csg
from .cross_sections import (CrossSection, cross_section_centroid, cross_section_outline, cross_section_polygons,
                             face_cross_section, plane_cross_section)
from .cutcsg import FEATURE_EDGE_TOLERANCE, CSGFeature, CutCSG, FaceFeature, FeatureNature
from .feature_paths import hit_identity
from ..geometry import Line, Plane, Point, unit_vector
from ..rule import as_ndarray, create_v3

if TYPE_CHECKING:
    from ..timber import PerfectTimberWithin

Segment3 = Tuple[np.ndarray, np.ndarray]
#: Stations along a line, low then high.
Interval = Tuple[float, float]

#: Float error: how far off the cut surface a declared edge may compute.
DECLARED_EDGE_FLOAT_NOISE = 1e-6


def timber_reach(timber: 'PerfectTimberWithin') -> float:
    """Return a distance that takes a line or plane past the whole timber from its middle."""
    return 4 * (float(timber.length) + float(max(timber.size[0], timber.size[1])))


def _station(located: Line, point) -> float:
    return float(((point - located.point).T * located.direction)[0, 0])


def intersected_intervals(one: Sequence[Interval], other: Sequence[Interval]) -> List[Interval]:
    """Return the overlaps of two interval lists, dropping ones that only touch."""
    return [(max(a[0], b[0]), min(a[1], b[1])) for a in one for b in other if max(a[0], b[0]) < min(a[1], b[1])]


def declared_line_span(feature: CSGFeature, owner: CutCSG, located: Line) -> Optional[Interval]:
    """Return the interval along `located` between the feature's declared ends, or None if it has none."""
    ends = feature.declared_ends(owner)
    if ends is None:
        return None
    reach = sorted(_station(located, end) for end in ends)
    return (reach[0], reach[-1])


def _intervals(located: Line, pieces) -> Optional[List[Interval]]:
    if pieces is None:
        return None
    return [(min(a, b), max(a, b))
            for a, b in ((_station(located, piece.start), _station(located, piece.end)) for piece in pieces)]


def cropped_intervals(located: Line, crop, solid: CutCSG, reach: float, near, retry: float) -> Optional[List[Interval]]:
    """Return the intervals along `located` that `crop` (an edges_on_csg crop function) keeps on `solid`.

    Exact, or at tolerance `retry` if exact keeps nothing. None if it can't be computed.
    """
    found = _intervals(located, crop(located, solid, seed_reach=reach, near=near, tolerance=0.0))
    if found == []:
        found = _intervals(located, crop(located, solid, seed_reach=reach, near=near, tolerance=retry))
    return found


def line_intervals(located: Line, csg: CutCSG, reach: float, near) -> Optional[List[Interval]]:
    """Return the intervals along `located` where it lies on `csg`, or None if that can't be computed."""
    return _intervals(located, crop_line_to_segments_on_csg(located, csg, seed_reach=reach, near=near))


def line_pieces(
    located: Line, solids: Sequence[Optional[CutCSG]], reach: float, near, declared: Optional[Interval] = None,
) -> List[Interval]:
    """Return the intervals along `located` where it lies on every solid (and within `declared`).

    A solid that can't be computed is skipped.
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


@dataclass(frozen=True)
class FeatureExtent:
    """A feature's extent on its cut timber, in the timber's local space.

    `located` is the feature's unbounded place; `pieces`, for a line, are intervals along its
    direction from its point; `cross_section`, for a plane, is the region it covers, in the plane's frame.
    """
    located: Union[Point, Line, Plane]
    pieces: Tuple[Interval, ...] = ()
    cross_section: Optional[CrossSection] = None

    @property
    def is_empty(self) -> bool:
        if isinstance(self.located, Point):
            return False
        if isinstance(self.located, Line):
            return not self.pieces
        return self.cross_section is None or not self.cross_section[1]

    def anchor(self) -> Optional[np.ndarray]:
        """Return where a dimension attaches: the point, the middle of a line's longest piece, or the
        centroid of a plane's region. None if empty."""
        if isinstance(self.located, Point):
            return as_ndarray(self.located.position)
        if isinstance(self.located, Line):
            if not self.pieces:
                return None
            low, high = max(self.pieces, key=lambda piece: piece[1] - piece[0])
            return self._on_line((low + high) / 2)
        return None if self.cross_section is None else cross_section_centroid(self.cross_section)

    def outline(self) -> List[Segment3]:
        """Return the segments that draw it: a line's pieces, or a plane region's outer boundary."""
        if isinstance(self.located, Line):
            return [(self._on_line(low), self._on_line(high)) for low, high in self.pieces]
        if isinstance(self.located, Plane) and self.cross_section is not None:
            return cross_section_outline(self.cross_section)
        return []

    def polygons(self) -> List[List[np.ndarray]]:
        """Return a plane's region as convex polygons; empty for a line or point."""
        return [] if self.cross_section is None else cross_section_polygons(self.cross_section)

    def _on_line(self, station: float) -> np.ndarray:
        line = self.located
        assert isinstance(line, Line)
        return as_ndarray(line.point + line.direction * float(station))


class FeatureExtents:
    """Lazily computed extents of every feature on one cut timber."""

    def __init__(self, root: Optional[CutCSG], timber: 'PerfectTimberWithin'):
        self.root = root
        self.timber = timber
        length = float(timber.length)
        # Everything that matters is within reach of the timber's middle.
        self.near = create_v3(0, 0, length / 2)
        self.reach = timber_reach(timber)
        self._extent_memo: Dict[Tuple[int, str], Optional[FeatureExtent]] = {}

    def of(self, feature: CSGFeature, owner: CutCSG) -> Optional[FeatureExtent]:
        """Return the extent of `feature` declared on `owner` (a node of this tree), or None for a
        curved face or a tree its plane can't cut."""
        key = hit_identity(feature, owner)
        if key not in self._extent_memo:
            self._extent_memo[key] = self._work_out(feature, owner)
        return self._extent_memo[key]

    def know(self, feature: CSGFeature, owner: CutCSG, extent: FeatureExtent) -> None:
        """Record an extent found some cheaper way (e.g. read off a face's outline), unless one is known."""
        self._extent_memo.setdefault(hit_identity(feature, owner), extent)

    def _work_out(self, feature: CSGFeature, owner: CutCSG) -> Optional[FeatureExtent]:
        located = feature.locate_simple_unbounded(owner)
        auxiliary = feature.nature is FeatureNature.AUXILIARY
        if isinstance(located, Point):
            return FeatureExtent(located)
        if isinstance(located, Line):
            located = Line(direction=unit_vector(located.direction), point=located.point)
            declared = declared_line_span(feature, owner, located)
            if feature.real and self.root is not None:
                edge = self._edge_pieces(feature, owner, located, declared)
                if edge is None:
                    if declared is None:
                        return None
                    edge = [declared]
                return FeatureExtent(located, pieces=tuple(edge))
            solids: Sequence[Optional[CutCSG]] = [] if auxiliary or self.root is None else [self.root]
            return FeatureExtent(located, pieces=tuple(line_pieces(located, solids, self.reach, self.near, declared)))
        if isinstance(located, Plane):
            if feature.nature is FeatureNature.PERFECT_REFERENCE and self.root is not None:
                cross_section = plane_cross_section(located, self.root, self.near, self.reach)
            elif isinstance(feature, FaceFeature):
                root = None if auxiliary else self.root
                cross_section = face_cross_section(feature, owner, root, self.near, self.reach)
            else:
                return None
            return None if cross_section is None else FeatureExtent(located, cross_section=cross_section)
        return None


    def _edge_pieces(self, feature: CSGFeature, owner: CutCSG, located: Line,
                     declared: Optional[Interval]) -> Optional[List[Interval]]:
        """Return where a real edge is: where the surface creases along it, within its parent faces'
        solids (or its owner) and its declared ends. None if a solid can't be computed.

        Exact first; if that leaves nothing, retried at the edge tolerance (derived) or float noise (declared).
        """
        root = self.root
        assert root is not None
        parents = [hit.owner for hit in getattr(feature, "parents", ()) if hit is not None] or [owner]

        def clipped(tolerance: float) -> Optional[List[Interval]]:
            found = _intervals(located, crop_line_to_crease_segments_on_csg(
                located, root, seed_reach=self.reach, near=self.near, tolerance=tolerance))
            if found is None:
                return None
            if declared is not None:
                found = intersected_intervals(found, [(declared[0] - tolerance, declared[1] + tolerance)])
            for parent in parents:
                within = _intervals(located, crop_line_to_segments_on_csg(
                    located, parent, seed_reach=self.reach, near=self.near, tolerance=tolerance))
                if within is None:
                    return None
                found = intersected_intervals(found, within)
            return found

        cropped = clipped(0.0)
        if cropped == []:
            cropped = clipped(float(FEATURE_EDGE_TOLERANCE) if feature.is_derived() else DECLARED_EDGE_FLOAT_NOISE)
        return cropped


# One FeatureExtents per live tree, keyed by id.
_extents_memo: Dict[int, FeatureExtents] = {}


def extents_of(root: CutCSG, timber: 'PerfectTimberWithin') -> FeatureExtents:
    """Return the (cached) FeatureExtents of a cut timber's tree."""
    extents = _extents_memo.get(id(root))
    if extents is None or extents.root is not root:
        extents = FeatureExtents(root, timber)
        _extents_memo[id(root)] = extents
        weakref.finalize(root, _extents_memo.pop, id(root), None)
    return extents
