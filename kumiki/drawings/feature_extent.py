"""Where a feature is on its cut timber: its extent, cropped once, by its nature.

Every question about where a feature is -- where a dimension hangs on it, what outline lights it,
how far it reaches on a sheet, whether a view can see it -- starts from the same answer, and this
is it. Worked out in the timber's local space, from the cut timber's tree (`root`), by the
feature's nature (FeatureNature):

- REAL, on the surface: a face is the part of it on the finished surface; a line, the pieces of it
  where there is timber.
- PERFECT_REFERENCE, inside the material: a plane is the plane cut to the solid; a line, likewise.
- AUXILIARY, in a void (a bore's axis): its own extent, which the solid has nothing to bound with.

A point is where it is. FeatureExtents keeps them, one per cut timber's tree.
"""

import weakref
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from ..csg.cutcsg import CSGFeature, CutCSG, FaceFeature, FeatureNature
from ..csg.planar_region import (Section, face_section, plane_section, section_centroid, section_outline,
                                 section_polygons)
from ..geometry import Line, Plane, Point
from ..rule import as_ndarray, create_v3, exact_scalar
from ..timber import PerfectTimberWithin
from .feature_span import Interval, declared_line_span, line_pieces

Segment3 = Tuple[np.ndarray, np.ndarray]


@dataclass(frozen=True)
class FeatureExtent:
    """A feature's extent on its cut timber, in the timber's local space.

    `located` is the feature's unbounded place; `pieces`, for a line, are intervals along its
    direction from its point; `section`, for a plane, is the region it covers, in the plane's frame.
    """
    located: Union[Point, Line, Plane]
    pieces: Tuple[Interval, ...] = ()
    section: Optional[Section] = None

    @property
    def is_empty(self) -> bool:
        if isinstance(self.located, Point):
            return False
        if isinstance(self.located, Line):
            return not self.pieces
        return self.section is None or not self.section[1]

    def anchor(self) -> Optional[np.ndarray]:
        """Where a dimension hangs on it: a point itself, the middle of a line's longest piece (the
        one a reader points at, when a cut leaves several), the centroid of a plane's region."""
        if isinstance(self.located, Point):
            return as_ndarray(self.located.position)
        if isinstance(self.located, Line):
            if not self.pieces:
                return None
            low, high = max(self.pieces, key=lambda piece: piece[1] - piece[0])
            return self._on_line((low + high) / 2)
        return None if self.section is None else section_centroid(self.section)

    def outline(self) -> List[Segment3]:
        """What lights or draws it: a line's pieces, a plane region's boundary (seams between its
        convex pieces removed)."""
        if isinstance(self.located, Line):
            return [(self._on_line(low), self._on_line(high)) for low, high in self.pieces]
        if isinstance(self.located, Plane) and self.section is not None:
            return section_outline(self.section)
        return []

    def polygons(self) -> List[List[np.ndarray]]:
        """A plane's region as convex polygons of points; nothing for a line or a point."""
        return [] if self.section is None else section_polygons(self.section)

    def _on_line(self, station: float) -> np.ndarray:
        line = self.located
        assert isinstance(line, Line)
        return as_ndarray(line.point + line.direction * exact_scalar(station))


class FeatureExtents:
    """Every feature's extent on one cut timber, each worked out the first time it is asked for."""

    def __init__(self, root: Optional[CutCSG], timber: PerfectTimberWithin):
        self.root = root
        self.timber = timber
        length = float(timber.length)
        # Everything that matters is within reach of the timber's middle.
        self.near = create_v3(0, 0, length / 2)
        self.reach = 4 * (length + float(max(timber.size[0], timber.size[1])))
        self._kept: Dict[Tuple[int, str], Optional[FeatureExtent]] = {}

    def of(self, feature: CSGFeature, owner: CutCSG) -> Optional[FeatureExtent]:
        """The extent of `feature`, declared on `owner` (a node of this timber's tree); None where it
        cannot be placed -- a curved face, or a tree that cannot be cut by its plane."""
        key = (id(owner), feature.name)
        if key not in self._kept:
            self._kept[key] = self._work_out(feature, owner)
        return self._kept[key]

    def _work_out(self, feature: CSGFeature, owner: CutCSG) -> Optional[FeatureExtent]:
        located = feature.locate_simple_unbounded(owner)
        auxiliary = feature.nature is FeatureNature.AUXILIARY
        if isinstance(located, Point):
            return FeatureExtent(located)
        if isinstance(located, Line):
            solids: Sequence[Optional[CutCSG]] = [] if auxiliary or self.root is None else [self.root]
            pieces = line_pieces(located, solids, self.reach, self.near,
                                 declared=declared_line_span(feature, owner, located))
            return FeatureExtent(located, pieces=tuple(pieces))
        if isinstance(located, Plane):
            if feature.nature is FeatureNature.PERFECT_REFERENCE and self.root is not None:
                section = plane_section(located, self.root, self.near, self.reach)
            elif isinstance(feature, FaceFeature):
                section = face_section(feature, owner, None if auxiliary else self.root, self.near, self.reach)
            else:
                return None
            return None if section is None else FeatureExtent(located, section=section)
        return None


# One FeatureExtents per tree, for as long as the tree lives. Keyed by identity -- a tree is not
# hashable -- and dropped when the tree is.
_by_root: Dict[int, FeatureExtents] = {}


def extents_of(root: CutCSG, timber: PerfectTimberWithin) -> FeatureExtents:
    """The FeatureExtents of a cut timber's tree, kept for as long as the tree is."""
    extents = _by_root.get(id(root))
    if extents is None or extents.root is not root:
        extents = FeatureExtents(root, timber)
        _by_root[id(root)] = extents
        weakref.finalize(root, _by_root.pop, id(root), None)
    return extents
