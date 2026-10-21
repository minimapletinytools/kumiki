"""CutCSG: CSG primitives and operations for timbers and their cuts, and the features they declare.

Values are plain floats compared through the safe_* helpers (see rule.py).

- Point tests (contains_point, is_point_on_boundary, get_outward_normal) take an optional `eps`
  for float error.
- Feature queries (find_all_features, find_first_feature, CSGFeature.test_point_unbounded) take a
  FeatureTestTolerances instead: slack for mesh-vs-analytic error and click imprecision.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import functools
import math
import re
from typing import TYPE_CHECKING, Callable, ClassVar, Dict, Generic, Iterator, List, Optional, Sequence, Tuple, Type, TypeVar, Union, cast
from dataclasses import dataclass, field, replace
from abc import ABC, abstractmethod
from enum import Enum, Flag
import warnings
from ..rule import *
from ..geometry import (Line, Plane, Point, intersect_line_plane, intersect_planes,
                       lines_are_coincident, perpendicular_axes, planes_are_coincident, planes_are_parallel,
                       points_are_coincident, unit_vector)
import numpy as np

if TYPE_CHECKING:
    from .cross_sections import Sides
    from .edges_on_csg import AngleSpans, SolidBounds, Span
from .identity_memo import memo_by_identity
from .carriers import (Carrier, CarrierBarrel, CarrierLine, CarrierMap, CarrierPlane, CarrierRef, Midplane, Recipe,
                       merge_coincident_planes)


# ============================================================================
# AABB utilities
# ============================================================================

def _numeric_min(*vals):
    """Return the minimum of `values` using safe comparison."""
    result = vals[0]
    for v in vals[1:]:
        if safe_compare(v - result, 0, Comparison.LT):
            result = v
    return result


def _numeric_max(*vals):
    """Return the maximum of `values` using safe comparison."""
    result = vals[0]
    for v in vals[1:]:
        if safe_compare(v - result, 0, Comparison.GT):
            result = v
    return result


@dataclass(frozen=True)
class AxisAlignedBoundingBox:
    """Axis-aligned bounding box of a CSG. A None bound is unbounded that way.

    When `is_empty`, the solid has no points and the bounds are meaningless; check it first.
    """
    min_x: Optional[Numeric]
    min_y: Optional[Numeric]
    min_z: Optional[Numeric]
    max_x: Optional[Numeric]
    max_y: Optional[Numeric]
    max_z: Optional[Numeric]
    is_empty: bool = False

class FeatureCategory(Enum):
    """Kind of place on a primitive's boundary a default feature names, shared by every primitive.

    Paired with an index where a primitive has several (index 0 for one-offs).
    """

    CAP = 0     # 0 = the start end, 1 = the end end
    SIDE = 1    # n = the nth side;
    ARRIS = 2   # every arris, in one run -- see below
    CORNER = 3  # every corner, in one run -- see below
    AXIS = 4    # a cylinder's axis
    EXTRA = 5   # n = the nth of a primitive's extra_features, for one that is its own carrier (PlaneFeature)

    # ARRIS and CORNER each number all of their kind together rather than
    # splitting by which end they belong to. For a shape with s sides:
    #
    #     ARRIS    0 .. s-1     side n against side n+1  -- a long arris
    #              s .. 2s-1    side n against the start cap
    #             2s .. 3s-1    side n against the end cap
    #     CORNER   0 .. s-1     vertex n of the start profile
    #              s .. 2s-1    vertex n of the end profile
    #
    # arris_against_cap and corner_on_cap below are the only things that know
    # this, so a default and the key an override matches against cannot drift.


# Where a default feature sits on a primitive: a category and an index within
# it. Deliberately not a string -- the set is finite and known per primitive,
# and a typo in a string key is a feature that silently never matches.
FeatureKey = Tuple[FeatureCategory, int]

# The two ends, named so callers do not write 0 and 1 and mean the wrong one.
START_CAP: FeatureKey = (FeatureCategory.CAP, 0)
END_CAP: FeatureKey = (FeatureCategory.CAP, 1)


# What every default carries. FeatureGroup.NONE is the important half -- see
# RectangularPrism.default_features for why a default that pairs would be a
# problem rather than a bonus.
_DEFAULT_FEATURE_PROPERTIES: 'FeatureProperties'


def arris_against_cap(side: int, sides: int, end: bool) -> FeatureKey:
    """Return the key of the arris where side `side` meets cap `cap`."""
    return (FeatureCategory.ARRIS, sides * (2 if end else 1) + side)


def corner_on_cap(vertex: int, vertices: int, end: bool) -> FeatureKey:
    """Return the key of vertex `index` of the start or end profile."""
    return (FeatureCategory.CORNER, (vertices if end else 0) + vertex)


def default_feature_name(key: FeatureKey) -> str:
    """Return the deterministic name of a default feature, e.g. "arris.5"."""
    category, index = key
    return f"{category.name.lower()}.{index}"


def side_key(index: int) -> FeatureKey:
    """Return the key of side `index` of an extrusion-like primitive."""
    return (FeatureCategory.SIDE, index)


# The one surface of a half space, and a cylinder's barrel -- its one side.
HALF_SPACE_PLANE: FeatureKey = side_key(0)
CYLINDER_BARREL: FeatureKey = side_key(0)
CYLINDER_AXIS: FeatureKey = (FeatureCategory.AXIS, 0)


# A prism's four sides in order: +x, +y, -x, -y. Side n and arris n (side n against n+1) follow
# timber.TimberFeature's order; see TestDefaultOrderFollowsTimberFeature.
_PRISM_SIDE_ORDER: Tuple['PrismFace', ...] = ()  # filled in below, once PrismFace exists


class PrismFace(Enum):
    """Face of a RectangularPrism; indices match TimberFace."""
    TOP = 1
    BOTTOM = 2
    RIGHT = 3
    FRONT = 4
    LEFT = 5
    BACK = 6


_PRISM_SIDE_ORDER = (PrismFace.RIGHT, PrismFace.FRONT, PrismFace.LEFT, PrismFace.BACK)
_PRISM_CAP_KEYS = {PrismFace.BOTTOM: START_CAP, PrismFace.TOP: END_CAP}


class ExtrusionCap(Enum):
    """Which flat end of an extrusion-like primitive."""
    TOP = 1
    BOTTOM = 2


# Key of a feature on an extrusion-like primitive: int n is the side from vertex n to vertex n+1
# (points[n] for ConvexPolygonExtrusion, path.segments[n] for PathExtrusion).
ExtrusionFeatureKey = Union[int, ExtrusionCap]


class CylinderPart(Enum):
    """Which surface of a Cylinder; BARREL is the whole curved side as one feature."""
    TOP = 1
    BOTTOM = 2
    BARREL = 3


class CSGFeatureType(Enum):
    """Kind of geometry a feature names: face, curved face, edge or point.

    Measurements dispatch on the pair of types.

    TODO consider adding DERIVED_POINT and DERIVED_FACE here
    """
    FACE = 1
    EDGE = 2
    POINT = 3
    CURVED_FACE = 4


# Default feature test tolerances in metres (0.5mm / 2mm / 4mm). See FeatureTestTolerances.
FEATURE_FACE_TOLERANCE = scalar('5e-4')
FEATURE_EDGE_TOLERANCE = scalar('2e-3')
FEATURE_POINT_TOLERANCE = scalar('4e-3')


@dataclass(frozen=True)
class FeatureTestTolerances:
    """How close a point must be to count as on a feature, per feature type.

    Faces need only the mesh-vs-analytic gap; edges and points need more, since they are snapped to.
    A viewport usually scales these by world units per pixel.
    """
    face: Numeric = FEATURE_FACE_TOLERANCE
    edge: Numeric = FEATURE_EDGE_TOLERANCE
    point: Numeric = FEATURE_POINT_TOLERANCE

    def for_type(self, feature_type: 'CSGFeatureType') -> Numeric:
        """Return the tolerance for `feature_type`."""
        if feature_type == CSGFeatureType.EDGE:
            return self.edge
        if feature_type == CSGFeatureType.POINT:
            return self.point
        return self.face

    def __mul__(self, factor: Numeric) -> 'FeatureTestTolerances':
        """Return these tolerances scaled by `factor` (e.g. world units per pixel)."""
        if safe_compare(factor, 0, Comparison.LE):
            raise ValueError(f"feature test tolerances must scale by a positive factor, got {factor}")
        return FeatureTestTolerances(
            face=self.face * factor,
            edge=self.edge * factor,
            point=self.point * factor,
        )

    def __rmul__(self, factor: Numeric) -> 'FeatureTestTolerances':
        return self.__mul__(factor)

    def __truediv__(self, divisor: Numeric) -> 'FeatureTestTolerances':
        if safe_compare(divisor, 0, Comparison.LE):
            raise ValueError(f"feature test tolerances must divide by a positive factor, got {divisor}")
        return self.__mul__(scalar(1) / divisor)

    @staticmethod
    def uniform(eps: Numeric) -> 'FeatureTestTolerances':
        """Return the same tolerance for every feature type."""
        return FeatureTestTolerances(face=eps, edge=eps, point=eps)

    @staticmethod
    def exact() -> 'FeatureTestTolerances':
        """Return analytic tolerances, for geometry that was never triangulated."""
        return FeatureTestTolerances.uniform(EPSILON_GENERIC)


DEFAULT_FEATURE_TEST_TOLERANCES = FeatureTestTolerances()


# How specific each kind of feature is, most specific first. A point sits on
# an edge which sits on a face, so when several claim the same click the
# narrowest one is the better answer.
_FEATURE_TYPE_SPECIFICITY = {
    CSGFeatureType.POINT: 0,
    CSGFeatureType.EDGE: 1,
    CSGFeatureType.FACE: 2,
    CSGFeatureType.CURVED_FACE: 2,
}


class FeatureGroup(Enum):
    """Which features a feature may derive an edge with:

        SHOULDER_PLANE with PERFECT, ROUGH and TENON
        PERFECT        with SHOULDER_PLANE and CROSSING
        ROUGH          with SHOULDER_PLANE and CROSSING
        TENON          with SHOULDER_PLANE
        CROSSING       with PERFECT and ROUGH
        NONE           with nothing

    - PERFECT: the perfect timber within's faces, arrises, corners and centerplanes, and rough faces
      lying on it (rptw.*).
    - ROUGH: the rough body's faces.
    - SHOULDER_PLANE: a joint's shoulder plane. TENON: a joint's tenon faces.
    - CROSSING: the faces a cross lap removes.

    PERFECT and ROUGH don't pair with themselves: a timber's own arrises and corners are declared.
    The order is the pick preference, best first.
    """
    SHOULDER_PLANE = 1
    PERFECT = 2
    ROUGH = 3
    TENON = 4
    CROSSING = 5
    #: Forms no edges with anything, including itself.
    NONE = 6


# Which groups each group forms edges with. Symmetric by construction; see
# FeatureGroup for what the names mean.
FEATURE_GROUP_PAIRS: dict = {
    FeatureGroup.SHOULDER_PLANE: frozenset({FeatureGroup.PERFECT, FeatureGroup.ROUGH,
                                            FeatureGroup.TENON}),
    FeatureGroup.PERFECT: frozenset({FeatureGroup.SHOULDER_PLANE, FeatureGroup.CROSSING}),
    FeatureGroup.ROUGH: frozenset({FeatureGroup.SHOULDER_PLANE, FeatureGroup.CROSSING}),
    FeatureGroup.TENON: frozenset({FeatureGroup.SHOULDER_PLANE}),
    FeatureGroup.CROSSING: frozenset({FeatureGroup.PERFECT, FeatureGroup.ROUGH}),
    FeatureGroup.NONE: frozenset(),
}


def feature_groups_intersect(a: FeatureGroup, b: FeatureGroup) -> bool:
    """Return whether features in groups `a` and `b` may form an edge."""
    return b in FEATURE_GROUP_PAIRS[a]



class FeatureMarkingStatus(Enum):
    """Whether a feature must appear on a drawing. Not yet read by the drawing generator."""

    OPTIONAL = 0
    ALWAYS_MARK = 1
    NEVER_MARK = 2


@dataclass(frozen=True)
class FeatureMarkingSpec:
    """How to mark a feature on a drawing, when not the default.

    `mark_relative_to` names the feature to dimension it from. Not yet read.
    """

    mark: FeatureMarkingStatus = FeatureMarkingStatus.OPTIONAL
    mark_relative_to: Optional[str] = None


class FeaturePurpose(Enum):
    """What a feature is for."""

    NOT_SPECIFIED = 0
    # Relief cut into rough stock (shavings/relief.py marks every feature of it).
    ROUGH_RELIEF = 1
    # The plane a joint's shoulder sits in. Planning drawings solve for these and the timber prisms only.
    SHOULDER = 2
    # A rough timber's own face, arris or corner where it is not the perfect timber within's
    # (rough.*; see timber.ROUGH_FACE_PREFIX): as sawn, so nothing is measured from it.
    ROUGH_FACE = 3


def measured_by_default(purpose: FeaturePurpose) -> bool:
    """Return whether features serving `purpose` are solved for by default (not rough stock or its relief)."""
    return purpose not in (FeaturePurpose.ROUGH_FACE, FeaturePurpose.ROUGH_RELIEF)


class FeatureNature(Enum):
    """Where a feature lives, which sets how far it reaches:

    - REAL: on the surface (a face, an arris); cropped by the cuts.
    - AUXILIARY: in a void (a bore's axis); bounded by its own extent.
    - PERFECT_REFERENCE: inside the material (the perfect timber within); cropped to the solid.
    """

    REAL = 0
    AUXILIARY = 1
    PERFECT_REFERENCE = 2


@dataclass(frozen=True)
class FeatureProperties:
    """Metadata every feature carries.

    Args:
        group: which features this one may derive edges with (FeatureGroup). NONE by default.
        priority: lower wins when several features claim a point.
        nature: FeatureNature. Only REAL features are tested against the triangulated result.
        marking_override: how to mark it on a drawing (not yet read).
        purpose: what it is for (FeaturePurpose).
    """

    group: FeatureGroup = FeatureGroup.NONE
    priority: int = 0
    nature: FeatureNature = FeatureNature.REAL
    marking_override: Optional[FeatureMarkingSpec] = None
    purpose: FeaturePurpose = FeaturePurpose.NOT_SPECIFIED

    @property
    def real(self) -> bool:
        return self.nature is FeatureNature.REAL


# An authored feature beats an anonymous default wherever both could answer.
# Set explicitly rather than left to the order the two lists happen to be
# concatenated in, since that is invisible at the point it decides something.
_DEFAULT_FEATURE_PRIORITY = 1000

_DEFAULT_FEATURE_PROPERTIES = FeatureProperties(
    group=FeatureGroup.NONE, priority=_DEFAULT_FEATURE_PRIORITY)


def _within_tolerance(
    hits: List['OwnedFeatureHit'],
    point: V3,
    tolerances: 'FeatureTestTolerances',
) -> List['OwnedFeatureHit']:
    """Return the hits `point` is on, each at its type's tolerance."""
    return [hit for hit in hits
            if hit.feature.test_point_unbounded(
                hit.owner, point, tolerances.for_type(hit.feature.feature_type()))]


def _sort_feature_hits(hits: List['OwnedFeatureHit']) -> List['OwnedFeatureHit']:
    """Return hits sorted best first (see docs/internal/picking.md), by:

    1. Non-real lines and points, then real features, then non-real planes.
    2. Point, then edge, then face.
    3. Declared before derived.
    4. Group rank.
    5. Priority, lowest first.
    6. Name.
    7. Order found.
    """
    return sorted(hits, key=feature_hit_sort_key)


def _derived_nature(one: 'CSGFeature', other: 'CSGFeature') -> FeatureNature:
    """Return a derived feature's nature: REAL if both parents are, else the non-real one's."""
    return next((parent.nature for parent in (one, other) if not parent.real), FeatureNature.REAL)


def feature_hit_sort_key(hit: 'OwnedFeatureHit') -> Tuple:
    """Return a hit's sort key (see _sort_feature_hits)."""
    face = hit.feature.feature_type() is CSGFeatureType.FACE
    return (
        1 if hit.feature.real else (2 if face else 0),
        _FEATURE_TYPE_SPECIFICITY[hit.feature.feature_type()],
        hit.feature.is_derived(),
        hit.feature.group_rank(),
        hit.feature.priority,
        hit.feature.name,
    )


def _names_same_geometry(one: 'OwnedFeatureHit', other: 'OwnedFeatureHit') -> bool:
    """Return whether two hits locate to the same point, line or plane. Unlocatable features match nothing."""
    here, there = one.locate_simple_unbounded(), other.locate_simple_unbounded()
    if isinstance(here, Point) and isinstance(there, Point):
        return points_are_coincident(here, there)
    if isinstance(here, Line) and isinstance(there, Line):
        return lines_are_coincident(here, there)
    if isinstance(here, Plane) and isinstance(there, Plane):
        return planes_are_coincident(here, there)
    return False


def owner_label_trails(root: 'CutCSG') -> Dict[int, Tuple[str, ...]]:
    """Return every node under `root`, keyed by id, with its label path (`shoulder`, `shoulder#1`, ...)."""
    trails: Dict[int, Tuple[str, ...]] = {}
    stack: List[Tuple['CutCSG', Tuple[str, ...]]] = [(root, ())]
    while stack:
        node, trail = stack.pop()
        trails[id(node)] = trail
        seen: Dict[str, int] = {}
        children = csg_children(node)
        for child in children:
            name = getattr(getattr(child, 'label', None), 'name', None)
            if name is None:
                stack.append((child, trail))
                continue
            occurrence = seen.get(name, 0)
            seen[name] = occurrence + 1
            stack.append((child, trail + (name if occurrence == 0 else f"{name}#{occurrence}",)))
    return trails


def _drop_duplicate_derived(
    hits: List['OwnedFeatureHit'],
    root: Optional['CutCSG'] = None,
) -> List['OwnedFeatureHit']:
    """Drop derived hits that locate to the same geometry as an earlier hit. Expects _sort_feature_hits order.

    Between two derived duplicates, keeps the one whose owner's label trail (then name) sorts first,
    using `root`; without it, the first. Logs duplicates.
    """
    kept: List['OwnedFeatureHit'] = []
    trails = owner_label_trails(root) if root is not None else {}
    # Duplicates are always the same kind, and within a kind declared sorts before derived.
    for hit in hits:
        twin_index = next((index for index, other in enumerate(kept)
                           if _names_same_geometry(hit, other)), None)
        if twin_index is None or not hit.feature.is_derived():
            kept.append(hit)
            continue
        twin = kept[twin_index]
        if not twin.feature.is_derived():
            continue
        # Both derived: the same geometry named twice over, from two copies of it.
        def order(candidate: 'OwnedFeatureHit'):
            return (trails.get(id(candidate.owner), ()), candidate.feature.name)
        winner, loser = sorted((twin, hit), key=order)
        if winner is hit:
            kept[twin_index] = hit
        if winner.feature.name != loser.feature.name:
            # Two different pairs meeting at one place -- an arris and a face crossing where an
            # edge leaves that face -- which is geometry, not one surface declared twice.
            continue
        warnings.warn(
            f"{loser.feature.name} at "
            f"{' > '.join(trails.get(id(loser.owner), ())) or '<unnamed>'} is the same "
            f"geometry as {winner.feature.name} at "
            f"{' > '.join(trails.get(id(winner.owner), ())) or '<unnamed>'}; keeping the "
            f"first by path. One surface declared twice derives its edge twice -- worth "
            f"fixing where the second copy is built, usually by leaving its feature "
            f"labels off.", stacklevel=2)
    return kept


def shared_ancestor(
    some_common_ancestor: 'CutCSG',
    first: 'CutCSG',
    second: 'CutCSG',
) -> Optional['CutCSG']:
    """Return the deepest node under `some_common_ancestor` containing both `first` and `second`, or None."""
    here, there = _trail_within(some_common_ancestor, first), _trail_within(some_common_ancestor, second)
    if here is None or there is None:
        return None
    deepest = None
    for one, other in zip(here, there):
        if one is not other:
            break
        deepest = one
    return deepest


def _trail_within(node: 'CutCSG', target: 'CutCSG') -> Optional[List['CutCSG']]:
    """Return the nodes from `node` down to `target`, or None if it isn't below."""
    if node is target:
        return [node]
    for child in csg_children(node):
        found = _trail_within(child, target)
        if found is not None:
            return [node] + found
    return None


def derive_edge_hits(
    some_common_ancestor: 'CutCSG',
    face_hits: List['OwnedFeatureHit'],
) -> List['OwnedFeatureHit']:
    """Return the edges formed by pairs of `face_hits`, each owned by the pair's shared ancestor.

    O(n^2) in the number of hits.
    """
    hits: List['OwnedFeatureHit'] = []
    for i in range(len(face_hits)):
        for j in range(i + 1, len(face_hits)):
            edge = DerivedEdgeFeature.derive(face_hits[i], face_hits[j])
            if edge is None:
                continue
            owner = shared_ancestor(some_common_ancestor, face_hits[i].owner, face_hits[j].owner)
            if owner is None:
                # Can't happen: both parents came from one gather.
                warnings.warn(
                    f"Skipping the derived edge {edge.name}: its parents are not "
                    f"both under the node being searched, so there is no node to "
                    f"own it.")
                continue
            hits.append(OwnedFeatureHit(feature=edge, owner=owner))
    return hits


def derive_point_hits(
    some_common_ancestor: 'CutCSG',
    edge_hits: List['OwnedFeatureHit'],
    face_hits: List['OwnedFeatureHit'],
) -> List['OwnedFeatureHit']:
    """Return the points where an edge in `edge_hits` crosses a face in `face_hits`, each owned by the pair's shared ancestor.

    An edge lying in the face's plane gives nothing.
    """
    hits: List['OwnedFeatureHit'] = []
    for edge_hit in edge_hits:
        for face_hit in face_hits:
            point = DerivedPointFeature.derive(edge_hit, face_hit)
            if point is None:
                continue
            owner = shared_ancestor(some_common_ancestor, edge_hit.owner, face_hit.owner)
            if owner is None:
                warnings.warn(
                    f"Skipping the derived point {point.name}: its parents are not "
                    f"both under the node being searched, so there is no node to "
                    f"own it.")
                continue
            hits.append(OwnedFeatureHit(feature=point, owner=owner))
    return hits


def _drop_real_hits_if_not_on_boundary(
    node: 'CutCSG',
    hits: List['OwnedFeatureHit'],
    point: V3,
    tolerances: 'FeatureTestTolerances',
) -> List['OwnedFeatureHit']:
    """Return `hits`, minus the real ones if `point` isn't on the boundary of `csg`."""
    if not hits:
        return hits

    # early exit if all fetaures are non real
    if not any(hit.feature.real for hit in hits):
        return hits

    # if the tested point is on the boundary, then all feature hits are OK
    if node.is_point_on_boundary(point, eps=tolerances.face):
        return hits

    # if the tested point is not on the boundary, return only the non real features
    return [hit for hit in hits if not hit.feature.real]


def _finite_midpoint(start: Optional[Numeric], end: Optional[Numeric]) -> Numeric:
    """Return the midpoint of an extent along an axis, using the finite end if one is infinite."""
    if start is None:
        return scalar(0) if end is None else end
    if end is None:
        return start
    return (start + end) / scalar(2)


# What locate_simple_unbounded() returns. Bounds are in feature_extent.FeatureExtents.
LocatedFeatureGeometry = Union[Point, Line, Plane]


@dataclass(frozen=True)
class CSGFeature(ABC):
    """A feature on a CutCSG's boundary, or a non-real one (e.g. a cylinder's axis).

    Doesn't know its owner; methods take the owner node to place it in the owner's space.
    """
    name: str
    properties: FeatureProperties = field(default_factory=FeatureProperties)

    def feature_key(self) -> Optional['FeatureKey']:
        """Return the default slot this feature fills (so it replaces that default), or None."""
        return None

    @abstractmethod
    def feature_type(self) -> CSGFeatureType:
        """Return the kind of geometry this feature names."""
        ...

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        """Return the feature's unbounded Plane, Line or Point in `owner`'s space.

        None for a curved surface (a barrel, a lofted side, a curved path side).
        """
        return None

    def declared_ends(self, owner: 'CutCSG') -> Optional[Tuple[V3, V3]]:
        """Return a line feature's own two ends in `owner`'s space, or None if it has none."""
        return None

    @property
    def group(self) -> FeatureGroup:
        return self.properties.group

    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        """Return the carriers of `owner` that produce this feature, or None."""
        key = self.feature_key()
        if key is not None and key in owner.carriers():
            return (CarrierRef(owner, key),)
        return None

    def is_derived(self) -> bool:
        """Return whether this feature was derived from others rather than declared."""
        return False

    def group_rank(self) -> int:
        """Return this feature's group's pick preference rank (derived features take their better parent's)."""
        return self.group.value

    @property
    def nature(self) -> FeatureNature:
        return self.properties.nature

    @property
    def real(self) -> bool:
        return self.nature is FeatureNature.REAL

    @property
    def priority(self) -> int:
        return self.properties.priority

    @abstractmethod
    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on this feature's surface, ignoring its bounds.

        `owner` places the feature. collect_feature_hits gates real features on the boundary.
        """
        ...


@dataclass(frozen=True)
class FaceFeature(CSGFeature):
    """A flat face. Locates to a Plane."""

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        return None


@dataclass(frozen=True)
class EdgeFeature(CSGFeature):
    """A straight edge or axis. Locates to a Line."""

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.EDGE

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Line]:
        return None


@dataclass(frozen=True)
class PointFeature(CSGFeature):
    """A vertex. Locates to a Point."""

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.POINT

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Point]:
        return None


@dataclass(frozen=True)
class CurvedFaceFeature(CSGFeature):
    """A curved face. Locates to nothing: no plane, line or point describes it."""

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.CURVED_FACE

    def locate_simple_unbounded(self, owner: 'CutCSG') -> None:
        return None


# A feature type, for OwnedFeatureHit and FeatureHandle to be generic over.
F_co = TypeVar("F_co", bound=CSGFeature, covariant=True)
K = TypeVar("K", bound=CSGFeature)


@dataclass(frozen=True)
class _ProgrammableFeature(CSGFeature):
    """A feature matched by an arbitrary predicate. Currently unused."""
    predicate: Optional[Callable[['CutCSG', V3, Optional[Numeric]], bool]] = None

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if self.predicate is None:
            return False
        return self.predicate(owner, point, test_tolerance)


@dataclass(frozen=True)
class ProgrammableFaceFeature(_ProgrammableFeature, FaceFeature):
    pass


@dataclass(frozen=True)
class ProgrammableEdgeFeature(_ProgrammableFeature, EdgeFeature):
    pass


@dataclass(frozen=True)
class ProgrammablePointFeature(_ProgrammableFeature, PointFeature):
    pass


def _as_plane(geometry: Optional['LocatedFeatureGeometry']) -> Optional[Plane]:
    """Return `located` if it is a Plane, else None."""
    return geometry if isinstance(geometry, Plane) else None


def _point_is_near(point: V3, other: V3, tolerance: Optional[Numeric] = None) -> bool:
    """Return whether two points are within `tolerance`."""
    gap = point - other
    return safe_zero_test_sq(safe_dot_product(gap, gap), eps=tolerance)


def _point_is_on_line(point: V3, line: Line, tolerance: Optional[Numeric] = None) -> bool:
    """Return whether `point` is within `tolerance` of an infinite line."""
    along = safe_normalize_vector(line.direction)
    from_start = point - line.point
    across = from_start - along * safe_dot_product(from_start, along)
    return safe_zero_test_sq(safe_dot_product(across, across), eps=tolerance)


def _meet_of_parents(a: 'OwnedFeatureHit', b: 'OwnedFeatureHit') -> Optional[Recipe]:
    """Return the recipe where two parent features meet, or None if either has none."""
    first, second = a.feature.solve_recipe(a.owner), b.feature.solve_recipe(b.owner)
    if first is None or second is None:
        return None
    return first + second


@dataclass(frozen=True)
class DerivedEdgeFeature(EdgeFeature):
    """The edge where two planar face features meet. Owned by their shared_ancestor."""

    #: The two faces forming this edge
    a: 'OwnedFeatureHit[FaceFeature]' = field(kw_only=True)
    b: 'OwnedFeatureHit[FaceFeature]' = field(kw_only=True)

    @property
    def parents(self) -> Tuple['OwnedFeatureHit[FaceFeature]', 'OwnedFeatureHit[FaceFeature]']:
        return (self.a, self.b)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on the edge's line (tested directly, since near-parallel faces make face tests unreliable)."""
        line = self.locate_simple_unbounded(owner)
        if isinstance(line, Line):
            return _point_is_on_line(point, line, test_tolerance)
        # debatable if this is the right behavior. In any case, this code path
        # should never get hit since DerivedEdges are only created when there
        # is an actual line.
        return (self.a.feature.test_point_unbounded(self.a.owner, point, test_tolerance)
                and self.b.feature.test_point_unbounded(self.b.owner, point, test_tolerance))

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Line]:
        return intersect_planes(self.a.feature.locate_simple_unbounded(self.a.owner),
                                self.b.feature.locate_simple_unbounded(self.b.owner))

    def declared_ends(self, owner: 'CutCSG') -> Optional[Tuple[V3, V3]]:
        """Return the edge's ends as bounded by its parent faces' corners, or None if they can't bound it.

        Exact along a face's own axes (every arris of a box); otherwise an over-estimate.

        TODO make it exact for oblique lines
        """
        line = self.locate_simple_unbounded(owner)
        if not isinstance(line, Line):
            return None
        start, along = line.point, line.direction
        bounds = []
        for hit in self.parents:
            corners = getattr(hit.feature, "corners", None)
            found = corners(hit.owner) if corners is not None else None
            if found:
                stations = [float(((corner - start).T * along)[0, 0]) for corner in found]
                bounds.append((min(stations), max(stations)))
        if not bounds:
            return None
        low, high = max(span[0] for span in bounds), min(span[1] for span in bounds)
        if low >= high:
            return None
        return start + along * scalar(repr(low)), start + along * scalar(repr(high))

    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        return _meet_of_parents(self.a, self.b)

    @staticmethod
    def derive(a: 'OwnedFeatureHit', b: 'OwnedFeatureHit') -> Optional['DerivedEdgeFeature']:
        """Return the edge where `a` and `b` meet, or None.

        None if either isn't a face, their groups can't meet, either face isn't there (e.g. an infinite
        prism's cap), or their planes are parallel.
        """
        face_a, face_b = hit_of_kind(a, FaceFeature), hit_of_kind(b, FaceFeature)
        if face_a is None or face_b is None:
            return None
        if not feature_groups_intersect(a.feature.group, b.feature.group):
            return None

        # A face that isn't there (an infinite prism's cap) forms no edge.
        if any(hit.feature.locate_simple_unbounded(hit.owner) is None for hit in (a, b)):
            return None

        if planes_are_parallel(face_a.feature.locate_simple_unbounded(face_a.owner),
                               face_b.feature.locate_simple_unbounded(face_b.owner)):
            return None

        # Deterministic order, so the same edge gets the same identity however traversal reached it.
        first, second = sorted(
            (face_a, face_b), key=lambda hit: (hit.feature.group.value, hit.feature.name))
        return DerivedEdgeFeature(
            name=f"{first.feature.name}\u00d7{second.feature.name}",
            properties=FeatureProperties(
                # An edge exists only where both its faces do.
                nature=_derived_nature(a.feature, b.feature),
                priority=max(a.feature.priority, b.feature.priority),
                # NONE, derived features do not create more derived features for now
                group=FeatureGroup.NONE,
            ),
            a=first,
            b=second,
        )

    def is_derived(self) -> bool:
        return True

    def group_rank(self) -> int:
        """Return the better rank of its two faces."""
        ranks = [hit.feature.group.value for hit in self.parents]
        return min(ranks) if ranks else FeatureGroup.NONE.value


@dataclass(frozen=True)
class DerivedPointFeature(PointFeature):
    """The point where an edge feature crosses a face feature."""
    edge: 'OwnedFeatureHit[EdgeFeature]' = field(kw_only=True)
    face: 'OwnedFeatureHit[FaceFeature]' = field(kw_only=True)

    @property
    def parents(self) -> Tuple['OwnedFeatureHit[EdgeFeature]', 'OwnedFeatureHit[FaceFeature]']:
        return (self.edge, self.face)

    def is_derived(self) -> bool:
        return True

    def group_rank(self) -> int:
        """Return the better rank of its edge and face."""
        ranks = [hit.feature.group.value for hit in self.parents]
        return min(ranks) if ranks else FeatureGroup.NONE.value

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on the vertex itself."""
        vertex = self.locate_simple_unbounded(owner)
        if isinstance(vertex, Point):
            return _point_is_near(point, vertex.position, test_tolerance)
        # debatable if this is the right behavior. In any case, this falls back
        # to the parents only when locate_simple_unbounded returns no vertex,
        # which should never happen.
        return (self.edge.feature.test_point_unbounded(self.edge.owner, point, test_tolerance)
                and self.face.feature.test_point_unbounded(self.face.owner, point, test_tolerance))

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Point]:
        return intersect_line_plane(self.edge.feature.locate_simple_unbounded(self.edge.owner),
                                    self.face.feature.locate_simple_unbounded(self.face.owner))


    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        return _meet_of_parents(self.edge, self.face)

    @staticmethod
    def derive(a: 'OwnedFeatureHit', b: 'OwnedFeatureHit') -> Optional['DerivedPointFeature']:
        """Return the point where `a` and `b` cross, or None.

        None unless they are one edge and one face whose groups can meet, both are there, and the line
        pierces the plane at one point (not lying in it).
        """
        edge = hit_of_kind(a, EdgeFeature) or hit_of_kind(b, EdgeFeature)
        face = hit_of_kind(a, FaceFeature) or hit_of_kind(b, FaceFeature)
        if edge is None or face is None:
            return None
        if not feature_groups_intersect(a.feature.group, b.feature.group):
            return None

        if any(hit.feature.locate_simple_unbounded(hit.owner) is None for hit in (a, b)):
            return None

        if intersect_line_plane(edge.feature.locate_simple_unbounded(edge.owner),
                                face.feature.locate_simple_unbounded(face.owner)) is None:
            return None

        # Deterministic order, so the same point gets the same identity however
        # traversal reached it.
        first, second = sorted(
            (a, b), key=lambda hit: (hit.feature.group.value, hit.feature.name))
        return DerivedPointFeature(
            name=f"{first.feature.name}\u00d7{second.feature.name}",
            properties=FeatureProperties(
                # A point exists only where both its parents do.
                nature=_derived_nature(a.feature, b.feature),
                priority=max(a.feature.priority, b.feature.priority),
                # Nothing pairs points; see DerivedEdgeFeature on why this is
                # said rather than defaulted.
                group=FeatureGroup.NONE,
            ),
            edge=edge,
            face=face,
        )


@dataclass(frozen=True)
class HalfSpaceFeature(FaceFeature):
    """The boundary plane of a HalfSpace."""

    def feature_key(self) -> Optional[FeatureKey]:
        # Its only surface. Not a cap: a half space has no ends to be an end of.
        return (FeatureCategory.SIDE, 0)

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        if not isinstance(owner, HalfSpace):
            return None
        # The solid is dot(normal, p) >= offset, so the boundary plane is
        # dot(normal, p) == offset and the outward normal points out of it.
        normal_length_sq = safe_dot_product(owner.normal, owner.normal)
        if safe_zero_test_sq(normal_length_sq):
            return None
        closest_to_origin = owner.normal * (owner.offset / normal_length_sq)
        return Plane(normal=-owner.normal, point=closest_to_origin)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        return owner.is_point_on_boundary(point, eps=test_tolerance)


@dataclass(frozen=True)
class SimpleRectangularPrismFeature(FaceFeature):
    """One of the six faces of a RectangularPrism, named by PrismFace."""
    face: PrismFace = PrismFace.TOP

    def feature_key(self) -> Optional[FeatureKey]:
        return prism_face_key(self.face)

    def _face_frame(self, owner: 'RectangularPrism') -> Optional[Tuple[Direction3D, V3]]:
        """Return the face's (outward normal, centre) in the owner's space."""
        width_dir, height_dir, length_dir = owner._local_axes()
        half_width = owner.size[0] / 2
        half_height = owner.size[1] / 2
        centre = owner.transform.position
        if self.face in (PrismFace.TOP, PrismFace.BOTTOM):
            distance = owner.end_distance if self.face == PrismFace.TOP else owner.start_distance
            if distance is None:
                return None  # that end runs to infinity; no face there
            sign = scalar(1) if self.face == PrismFace.TOP else scalar(-1)
            return length_dir * sign, centre + length_dir * distance
        mid_length = _finite_midpoint(owner.start_distance, owner.end_distance)
        base = centre + length_dir * mid_length
        if self.face == PrismFace.RIGHT:
            return width_dir, base + width_dir * half_width
        if self.face == PrismFace.LEFT:
            return -width_dir, base - width_dir * half_width
        if self.face == PrismFace.FRONT:
            return height_dir, base + height_dir * half_height
        if self.face == PrismFace.BACK:
            return -height_dir, base - height_dir * half_height
        return None

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        if not isinstance(owner, RectangularPrism):
            return None
        frame = self._face_frame(owner)
        if frame is None:
            return None
        normal, centre = frame
        return Plane(normal=normal, point=centre)

    def _face_axes(
        self, owner: 'RectangularPrism',
    ) -> Optional[Tuple[Tuple[Direction3D, Numeric], Tuple[Direction3D, Numeric]]]:
        """Return the face's two in-plane directions and half-sizes, or None if unbounded."""
        width_dir, height_dir, length_dir = owner._local_axes()
        half_width = owner.size[0] / 2
        half_height = owner.size[1] / 2
        if self.face in (PrismFace.TOP, PrismFace.BOTTOM):
            return ((width_dir, half_width), (height_dir, half_height))
        if owner.start_distance is None or owner.end_distance is None:
            return None
        half_length = (owner.end_distance - owner.start_distance) / 2
        if self.face in (PrismFace.RIGHT, PrismFace.LEFT):
            return ((height_dir, half_height), (length_dir, half_length))
        if self.face in (PrismFace.FRONT, PrismFace.BACK):
            return ((width_dir, half_width), (length_dir, half_length))
        return None

    def corners(self, owner: 'CutCSG') -> Optional[Tuple[V3, V3, V3, V3]]:
        """Return the face's four corners, or None if unbounded."""
        if not isinstance(owner, RectangularPrism):
            return None
        frame = self._face_frame(owner)
        axes = self._face_axes(owner)
        if frame is None or axes is None:
            return None
        _, centre = frame
        (first, first_half), (second, second_half) = axes
        return tuple(
            centre + first * (first_half * scalar(a)) + second * (second_half * scalar(b))
            for a, b in ((1, 1), (1, -1), (-1, -1), (-1, 1))
        )


    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, RectangularPrism):
            return False
        x, y, z = owner._local_coords(point)
        half_width = owner.size[0] / 2
        half_height = owner.size[1] / 2
        if self.face == PrismFace.RIGHT:
            return safe_equality_test(x, half_width, eps=test_tolerance)
        if self.face == PrismFace.LEFT:
            return safe_equality_test(x, -half_width, eps=test_tolerance)
        if self.face == PrismFace.FRONT:
            return safe_equality_test(y, half_height, eps=test_tolerance)
        if self.face == PrismFace.BACK:
            return safe_equality_test(y, -half_height, eps=test_tolerance)
        if self.face == PrismFace.TOP:
            return owner.end_distance is not None and safe_equality_test(z, owner.end_distance, eps=test_tolerance)
        if self.face == PrismFace.BOTTOM:
            return owner.start_distance is not None and safe_equality_test(z, owner.start_distance, eps=test_tolerance)
        return False



@dataclass(frozen=True)
class PlaneFeature(FaceFeature):
    """An extra plane on a primitive, with its own solver carrier. Not real by default.

    `normal` . x = `offset` in the owner's frame (before its transform).
    """
    normal: Tuple[Numeric, Numeric, Numeric] = (scalar(1), scalar(0), scalar(0))
    offset: Numeric = scalar(0)
    properties: FeatureProperties = field(default_factory=lambda: FeatureProperties(nature=FeatureNature.AUXILIARY))

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        transform = getattr(owner, "transform", None)
        normal = create_v3(*self.normal)
        point = normal * self.offset
        if transform is None:
            return Plane(normal=normal, point=point)
        return Plane(normal=safe_transform_vector(transform.orientation.matrix, normal),
                     point=transform.local_to_global(point))


    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        extras = getattr(owner, "extra_features", ())
        index = next((i for i, extra in enumerate(extras) if extra.name == self.name), None)
        return None if index is None else (CarrierRef(owner, (FeatureCategory.EXTRA, index)),)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        plane = self.locate_simple_unbounded(owner)
        return plane is not None and safe_equality_test(
            safe_dot_product(point - plane.point, plane.normal), 0, eps=test_tolerance)


@dataclass(frozen=True)
class MidplaneFeature(FaceFeature):
    """The plane midway between two parallel planes of its owner. Not real by default.

    Each of `between` is a feature name or a default FeatureKey. Solved from those two planes; locates
    to None if they aren't parallel.
    """
    between: Tuple[Union[str, FeatureKey], Union[str, FeatureKey]] = ("", "")
    properties: FeatureProperties = field(default_factory=lambda: FeatureProperties(nature=FeatureNature.AUXILIARY))

    def _sides(self, owner: 'CutCSG') -> Optional[Tuple['CSGFeature', 'CSGFeature']]:
        named = {feature.name: feature for feature in owner.get_declared_features()}
        defaults = owner.default_features() if isinstance(owner, HasFeatures) else {}
        first, second = (named.get(side) if isinstance(side, str) else defaults.get(side) for side in self.between)
        return None if first is None or second is None else (first, second)

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        sides = self._sides(owner)
        if sides is None:
            return None
        first, second = (side.locate_simple_unbounded(owner) for side in sides)
        if not isinstance(first, Plane) or not isinstance(second, Plane):
            return None
        if abs(abs(float(safe_dot_product(first.normal, second.normal))) - 1) > 1e-9:
            return None
        return Plane(normal=first.normal, point=(first.point + second.point) / 2)


    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        sides = self._sides(owner)
        if sides is None:
            return None
        first, second = (side.solve_recipe(owner) for side in sides)
        if first is None or second is None or len(first) != 1 or len(second) != 1:
            return None
        front, back = first[0], second[0]
        if not isinstance(front, CarrierRef) or not isinstance(back, CarrierRef):
            return None
        return (Midplane(front=front, back=back),)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        plane = self.locate_simple_unbounded(owner)
        return plane is not None and safe_equality_test(
            safe_dot_product(point - plane.point, plane.normal), 0, eps=test_tolerance)


def _canonical_ordering_arris_faces(
    first: 'PrismFace', second: 'PrismFace',
) -> Optional[Tuple['PrismFace', 'PrismFace']]:
    """Return two prism faces in arris-naming order (as timber.py names them), or None if they share no arris.

    A cap first, then the side; otherwise FRONT/BACK first, then RIGHT/LEFT.
    """
    if not isinstance(first, PrismFace) or not isinstance(second, PrismFace):
        return None
    if first is second:
        return None
    first_is_cap, second_is_cap = first in _PRISM_CAP_KEYS, second in _PRISM_CAP_KEYS
    if first_is_cap or second_is_cap:
        if first_is_cap and second_is_cap:
            return None
        return (first, second) if first_is_cap else (second, first)
    one, other = _PRISM_SIDE_ORDER.index(first), _PRISM_SIDE_ORDER.index(second)
    gap = (one - other) % len(_PRISM_SIDE_ORDER)
    if gap not in (1, len(_PRISM_SIDE_ORDER) - 1):
        return None  # opposite sides: parallel, no arris
    # Consecutive sides are always one odd index and one even, and the odd ones
    # are FRONT and BACK.
    return (first, second) if one % 2 else (second, first)


@dataclass(frozen=True)
class SimpleRectangularPrismEdgeFeature(EdgeFeature):
    """An arris of a RectangularPrism, named by its two faces."""

    faces: Tuple[PrismFace, PrismFace] = (PrismFace.FRONT, PrismFace.RIGHT)

    def __post_init__(self):
        first, second = self.faces
        canonical_ordering = _canonical_ordering_arris_faces(first, second)
        if canonical_ordering is None:
            raise ValueError(f"{self.name!r}: {first} and {second} meet in no arris")
        if (first, second) != canonical_ordering:
            raise ValueError(
                f"{self.name!r}: the faces must be in canonical order, "
                f"{canonical_ordering[0]}, {canonical_ordering[1]}; use SimpleRectangularPrismEdgeFeature.of")

    @classmethod
    def of(cls, name: str, first: PrismFace, second: PrismFace,
           properties: Optional[FeatureProperties] = None) -> 'SimpleRectangularPrismEdgeFeature':
        """Return the arris between two faces, given in either order."""
        ordered = _canonical_ordering_arris_faces(first, second)
        if ordered is None:
            raise ValueError(f"{name!r}: {first} and {second} meet in no arris")
        if properties is None:
            return cls(name=name, faces=ordered)
        return cls(name=name, faces=ordered, properties=properties)

    def feature_key(self) -> Optional[FeatureKey]:
        return _prism_arris_key(*self.faces)

    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        return _meet_of_prism_faces(owner, self.faces)

    def _sides(self) -> Tuple['SimpleRectangularPrismFeature', 'SimpleRectangularPrismFeature']:
        """Return the two faces as features."""
        return (
            SimpleRectangularPrismFeature(name=self.name, face=self.faces[0]),
            SimpleRectangularPrismFeature(name=self.name, face=self.faces[1]),
        )

    def test_point_unbounded(self, owner: 'CutCSG', point: V3,
                   test_tolerance: Optional[Numeric] = None) -> bool:
        first, second = self._sides()
        return (first.test_point_unbounded(owner, point, test_tolerance)
                and second.test_point_unbounded(owner, point, test_tolerance))

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Line]:
        """Return the line the two faces meet in, or None."""
        first, second = self._sides()
        return intersect_planes(_as_plane(first.locate_simple_unbounded(owner)), _as_plane(second.locate_simple_unbounded(owner)))

    def declared_ends(self, owner: 'CutCSG') -> Optional[Tuple[V3, V3]]:
        """Return the two prism corners the arris runs between, or None if the prism is unbounded there."""
        first, second = self._sides()
        corners = first.corners(owner)
        if corners is None:
            return None
        shared = [corner for corner in corners if second.test_point_unbounded(owner, corner)]
        return (shared[0], shared[1]) if len(shared) == 2 else None


def _canonical_ordering_corner_faces(
    faces: Sequence['PrismFace'],
) -> Optional[Tuple['PrismFace', 'PrismFace', 'PrismFace']]:
    """Return three prism faces in corner-naming order (as TimberCorner), or None if they share no corner."""
    if len(faces) != 3 or not all(isinstance(face, PrismFace) for face in faces):
        return None
    if len(set(faces)) != 3:
        return None
    caps = [face for face in faces if face in _PRISM_CAP_KEYS]
    sides = [face for face in faces if face not in _PRISM_CAP_KEYS]
    if len(caps) != 1:
        return None
    ordered = _canonical_ordering_arris_faces(*sides)
    if ordered is None:
        return None  # opposite sides, which meet in no arris and so in no corner
    # The arris order puts FRONT or BACK first; a corner reads the sides the way
    # they come round the prism, which is RIGHT before FRONT.
    first, second = ordered
    if (_PRISM_SIDE_ORDER.index(second) - _PRISM_SIDE_ORDER.index(first)) % len(
            _PRISM_SIDE_ORDER) != 1:
        first, second = second, first
    return (caps[0], first, second)


def _meet_of_prism_faces(owner: 'CutCSG', faces: Sequence[PrismFace]) -> Optional[Recipe]:
    """Return where these prism faces meet, or None if one isn't there."""
    carriers = owner.carriers()
    keys = [prism_face_key(face) for face in faces]
    if not all(key in carriers for key in keys):
        return None
    return tuple(CarrierRef(owner, key) for key in keys)


def prism_face_key(face: PrismFace) -> FeatureKey:
    """Return the default key of a RectangularPrism face."""
    if face in _PRISM_CAP_KEYS:
        return _PRISM_CAP_KEYS[face]
    return side_key(_PRISM_SIDE_ORDER.index(face))


def _prism_arris_key(first: PrismFace, second: PrismFace) -> Optional[FeatureKey]:
    """Return the default key of the arris between two faces in canonical order, or None."""
    if first in _PRISM_CAP_KEYS or second in _PRISM_CAP_KEYS:
        cap, side = (first, second) if first in _PRISM_CAP_KEYS else (second, first)
        if side in _PRISM_CAP_KEYS:
            return None  # two caps never meet
        return arris_against_cap(
            _PRISM_SIDE_ORDER.index(side), len(_PRISM_SIDE_ORDER), end=cap is PrismFace.TOP)
    low, high = _PRISM_SIDE_ORDER.index(first), _PRISM_SIDE_ORDER.index(second)
    low, high = min(low, high), max(low, high)
    sides = len(_PRISM_SIDE_ORDER)
    if high - low == 1:
        return (FeatureCategory.ARRIS, low)
    if low == 0 and high == sides - 1:
        return (FeatureCategory.ARRIS, high)  # the wrap-around join
    return None  # opposite sides: parallel, no arris


def _prism_corner_key(
    canonical_ordering: Optional[Tuple[PrismFace, PrismFace, PrismFace]],
) -> Optional[FeatureKey]:
    """Return the default key of a corner, given its faces in canonical order."""
    if canonical_ordering is None:
        return None
    cap, first, _ = canonical_ordering
    return corner_on_cap(_PRISM_SIDE_ORDER.index(first), len(_PRISM_SIDE_ORDER),
                         end=cap is PrismFace.TOP)


def prism_arris_key(first: PrismFace, second: PrismFace) -> FeatureKey:
    """Return the default key of the arris between two faces, in either order."""
    key = _prism_arris_key(first, second)
    if key is None:
        raise ValueError(f"{first} and {second} meet in no arris")
    return key


def prism_corner_key(*faces: PrismFace) -> FeatureKey:
    """Return the default key of the corner of three faces, in any order."""
    key = _prism_corner_key(_canonical_ordering_corner_faces(faces))
    if key is None:
        raise ValueError(f"{', '.join(face.name for face in faces)} meet at no corner")
    return key


@dataclass(frozen=True)
class SimpleRectangularPrismVertexFeature(PointFeature):
    """A corner of a RectangularPrism, named by its three faces; numbered to match TimberCorner."""

    faces: Tuple[PrismFace, PrismFace, PrismFace] = (
        PrismFace.BOTTOM, PrismFace.RIGHT, PrismFace.FRONT)

    def __post_init__(self):
        canonical_ordering = _canonical_ordering_corner_faces(self.faces)
        names = ', '.join(face.name for face in self.faces)
        if canonical_ordering is None:
            raise ValueError(f"{self.name!r}: {names} meet at no corner")
        if tuple(self.faces) != canonical_ordering:
            raise ValueError(
                f"{self.name!r}: the faces must be in canonical order, "
                f"{', '.join(f.name for f in canonical_ordering)}; use SimpleRectangularPrismVertexFeature.of")

    @classmethod
    def of(cls, name: str, *faces: PrismFace,
           properties: Optional[FeatureProperties] = None) -> 'SimpleRectangularPrismVertexFeature':
        """Return the corner of three faces, given in any order."""
        ordered = _canonical_ordering_corner_faces(faces)
        if ordered is None:
            raise ValueError(f"{name!r}: {', '.join(face.name for face in faces)} meet at no corner")
        if properties is None:
            return cls(name=name, faces=ordered)
        return cls(name=name, faces=ordered, properties=properties)

    def feature_key(self) -> Optional[FeatureKey]:
        return _prism_corner_key(self.faces)

    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        return _meet_of_prism_faces(owner, self.faces)

    def _position(self, owner: 'CutCSG') -> Optional[V3]:
        """Return the corner's position in the owner's space."""
        if not isinstance(owner, RectangularPrism):
            return None
        cap, first, second = self.faces
        width_dir, height_dir, length_dir = owner._local_axes()
        distance = owner.end_distance if cap is PrismFace.TOP else owner.start_distance
        if distance is None:
            return None  # that end runs to infinity; no corner there
        at = owner.transform.position + length_dir * distance
        reach = {PrismFace.RIGHT: width_dir * (owner.size[0] / 2),
                 PrismFace.LEFT: -width_dir * (owner.size[0] / 2),
                 PrismFace.FRONT: height_dir * (owner.size[1] / 2),
                 PrismFace.BACK: -height_dir * (owner.size[1] / 2)}
        return at + reach[first] + reach[second]

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Point]:
        at = self._position(owner)
        return None if at is None else Point(position=at)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3,
                             test_tolerance: Optional[Numeric] = None) -> bool:
        at = self._position(owner)
        return False if at is None else _point_is_near(point, at, test_tolerance)



@dataclass(frozen=True)
class CylinderAxisFeature(EdgeFeature):
    """The centre line of a Cylinder."""

    @property
    def nature(self) -> FeatureNature:
        return FeatureNature.AUXILIARY

    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        if self._cylinder(owner) is None:
            return None
        return (CarrierRef(owner, CYLINDER_AXIS),)

    def _cylinder(self, owner: 'CutCSG') -> Optional['Cylinder']:
        """Return the owner as a Cylinder, or None (with a warning) if it isn't one."""
        if isinstance(owner, Cylinder):
            return owner
        warnings.warn(
            f"{self.name!r} is a cylinder axis, but its owner is a "
            f"{type(owner).__name__}, which has no axis")
        return None

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Line]:
        cylinder = self._cylinder(owner)
        if cylinder is None:
            return None
        return Line(direction=safe_normalize_vector(cylinder.axis_direction),
                    point=cylinder.position)

    def declared_ends(self, owner: 'CutCSG') -> Optional[Tuple[V3, V3]]:
        """Return the axis's ends at the cylinder's caps, or None if either is infinite."""
        cylinder = self._cylinder(owner)
        if cylinder is None or cylinder.start_distance is None or cylinder.end_distance is None:
            return None
        axis = safe_normalize_vector(cylinder.axis_direction)
        return (cylinder.position + axis * cylinder.start_distance,
                cylinder.position + axis * cylinder.end_distance)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on the axis line (ends not checked)."""
        if not isinstance(owner, Cylinder):
            return False
        tolerance = DEFAULT_FEATURE_TEST_TOLERANCES.edge if test_tolerance is None else test_tolerance
        _axial, radial = owner._axial_and_radial(point)
        return safe_compare(radial, tolerance, Comparison.LE)


@dataclass(frozen=True)
class SimpleCylinderCapFeature(FaceFeature):
    """An end cap of a Cylinder; `part` is TOP or BOTTOM."""
    part: CylinderPart = CylinderPart.TOP

    def feature_key(self) -> Optional[FeatureKey]:
        return END_CAP if self.part is CylinderPart.TOP else START_CAP

    def _distance(self, owner: 'Cylinder') -> Optional[Numeric]:
        return owner.end_distance if self.part is CylinderPart.TOP else owner.start_distance

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        if not isinstance(owner, Cylinder):
            return None
        distance = self._distance(owner)
        if distance is None:
            return None
        axis = safe_normalize_vector(owner.axis_direction)
        sign = scalar(1) if self.part is CylinderPart.TOP else scalar(-1)
        return Plane(normal=axis * sign, point=owner.position + axis * distance)


    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, Cylinder):
            return False
        distance = self._distance(owner)
        axial, _radial = owner._axial_and_radial(point)
        return distance is not None and safe_equality_test(axial, distance, eps=test_tolerance)


@dataclass(frozen=True)
class SimpleCylinderBarrelFeature(CurvedFaceFeature):
    """The curved side of a Cylinder."""

    def feature_key(self) -> Optional[FeatureKey]:
        return (FeatureCategory.SIDE, 0)


    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, Cylinder):
            return False
        _axial, radial = owner._axial_and_radial(point)
        return safe_equality_test(radial, owner.radius, eps=test_tolerance)


@dataclass(frozen=True)
class SimpleConvexPolygonExtrusionFeature(FaceFeature):
    """A side (points[key] to points[key+1]) or end cap of a ConvexPolygonExtrusion."""
    key: ExtrusionFeatureKey = ExtrusionCap.TOP

    def feature_key(self) -> Optional[FeatureKey]:
        if self.key is ExtrusionCap.BOTTOM:
            return START_CAP
        if self.key is ExtrusionCap.TOP:
            return END_CAP
        return (FeatureCategory.SIDE, int(self.key))

    def _frame(self, owner: 'ConvexPolygonExtrusion') -> Optional[Tuple[Direction3D, V3]]:
        """Return the face's (outward normal, centre) in the owner's space."""
        orientation = owner.transform.orientation.matrix
        length_dir = safe_transform_vector(orientation, Matrix([scalar(0), scalar(0), scalar(1)]))
        if self.key in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            distance = owner.end_distance if self.key == ExtrusionCap.TOP else owner.start_distance
            if distance is None:
                return None
            sign = scalar(1) if self.key == ExtrusionCap.TOP else scalar(-1)
            return length_dir * sign, owner.transform.position + length_dir * distance
        # A straight extrusion, so every side face is planar.
        points = owner.points
        p1 = points[self.key]
        p2 = points[(self.key + 1) % len(points)]
        edge = p2 - p1
        edge_length = safe_norm(Matrix([edge[0], edge[1]]))
        if safe_zero_test(edge_length):
            return None
        # Outward normal of a CCW-wound polygon edge is (dy, -dx) negated; the
        # winding is normalised by is_valid(), so take the side away from the
        # polygon centroid to stay right either way.
        candidate = Matrix([edge[1], -edge[0]]) / edge_length
        midpoint_2d = (p1 + p2) / scalar(2)
        centroid_2d = sum(points[1:], points[0]) / scalar(len(points))
        if safe_compare(safe_dot_product(candidate, midpoint_2d - centroid_2d), 0, Comparison.LT):
            candidate = -candidate
        normal = safe_transform_vector(orientation, Matrix([candidate[0], candidate[1], scalar(0)]))
        mid_length = _finite_midpoint(owner.start_distance, owner.end_distance)
        local_mid = Matrix([midpoint_2d[0], midpoint_2d[1], mid_length])
        return normal, owner.transform.position + safe_transform_vector(orientation, local_mid)

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        if not isinstance(owner, ConvexPolygonExtrusion):
            return None
        frame = self._frame(owner)
        if frame is None:
            return None
        normal, centre = frame
        return Plane(normal=normal, point=centre)


    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, ConvexPolygonExtrusion):
            return False
        x, y, z = owner._local_coords(point)
        if self.key == ExtrusionCap.TOP:
            return owner.end_distance is not None and safe_equality_test(z, owner.end_distance, eps=test_tolerance)
        if self.key == ExtrusionCap.BOTTOM:
            return owner.start_distance is not None and safe_equality_test(z, owner.start_distance, eps=test_tolerance)
        return owner._point_on_side(self.key, x, y, eps=test_tolerance)


@dataclass(frozen=True)
class SimpleLoftFeature(FaceFeature):
    """A side or end cap of a ConvexPolygonSimpleLoft. Sides are planar only for a pure taper."""
    key: ExtrusionFeatureKey = ExtrusionCap.TOP

    def feature_key(self) -> Optional[FeatureKey]:
        if self.key is ExtrusionCap.BOTTOM:
            return START_CAP
        if self.key is ExtrusionCap.TOP:
            return END_CAP
        return (FeatureCategory.SIDE, int(self.key))

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        if not isinstance(owner, ConvexPolygonSimpleLoft):
            return None
        
        orientation = owner.transform.orientation.matrix
        length_dir = safe_transform_vector(orientation, Matrix([scalar(0), scalar(0), scalar(1)]))
        if self.key in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            is_top = self.key == ExtrusionCap.TOP
            distance = owner.top_points_z_pos if is_top else owner.bottom_points_z_pos
            sign = scalar(1) if is_top else scalar(-1)
            return Plane(normal=length_dir * sign,
                         point=owner.transform.position + length_dir * distance)

        # A side; planar, since is_valid refuses a twisted loft.
        index = int(self.key)
        count = len(owner.bottom_points)
        if index >= count:
            return None
        following = (index + 1) % count
        def placed(profile_point, z_pos):
            local = Matrix([profile_point[0], profile_point[1], z_pos])
            return owner.transform.position + safe_transform_vector(orientation, local)

        corners = [
            placed(owner.bottom_points[index], owner.bottom_points_z_pos),
            placed(owner.bottom_points[following], owner.bottom_points_z_pos),
            placed(owner.top_points[index], owner.top_points_z_pos),
        ]
        normal = cross_product(corners[1] - corners[0], corners[2] - corners[0])
        if safe_zero_test(giraffe_norm(normal)):
            # A degenerate side -- three corners in line -- lies on no one plane.
            return None
        return Plane(normal=safe_normalize_vector(normal), point=corners[0])


    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, ConvexPolygonSimpleLoft):
            return False
        x, y, z = owner._local_coords(point)
        if self.key == ExtrusionCap.TOP:
            return safe_equality_test(z, owner.top_points_z_pos, eps=test_tolerance)
        if self.key == ExtrusionCap.BOTTOM:
            return safe_equality_test(z, owner.bottom_points_z_pos, eps=test_tolerance)
        return owner._point_on_side(self.key, x, y, z, eps=test_tolerance)


def _profile_corner(owner: 'CutCSG', index: int, end: bool) -> Optional[V3]:
    """Return vertex `index` of a convex extrusion's or loft's profile at one end, in the owner's space, or None if that end is infinite."""
    if not isinstance(owner, (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft)):
        return None
    if isinstance(owner, ConvexPolygonExtrusion):
        z = owner.end_distance if end else owner.start_distance
        if z is None:
            return None
        vertex = owner.points[index]
    else:
        z = owner.top_points_z_pos if end else owner.bottom_points_z_pos
        vertex = (owner.top_points if end else owner.bottom_points)[index]
    local = Matrix([vertex[0], vertex[1], z])
    return owner.transform.position + safe_transform_vector(owner.transform.orientation.matrix, local)


@dataclass(frozen=True)
class ConvexProfileEdgeFeature(EdgeFeature):
    """An edge of a ConvexPolygonExtrusion or ConvexPolygonSimpleLoft.

    `faces` is a side and the next side (a long edge), or a side and a cap (a profile edge).
    """
    key: FeatureKey = (FeatureCategory.ARRIS, 0)
    faces: Tuple[int, ExtrusionFeatureKey] = (0, 1)

    def feature_key(self) -> Optional[FeatureKey]:
        return self.key

    def _face_features(self, owner: 'CutCSG') -> Tuple[CSGFeature, ...]:
        face_type = (SimpleConvexPolygonExtrusionFeature if isinstance(owner, ConvexPolygonExtrusion)
                     else SimpleLoftFeature)
        return tuple(face_type(name=self.name, key=face) for face in self.faces)

    def solve_recipe(self, owner: 'CutCSG') -> Optional[Recipe]:
        carriers = owner.carriers()
        keys = [face.feature_key() for face in self._face_features(owner)]
        if not all(key in carriers for key in keys):
            return None
        return tuple(CarrierRef(owner, key) for key in keys if key is not None)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft)):
            return False
        return all(face.test_point_unbounded(owner, point, test_tolerance)
                   for face in self._face_features(owner))

    def _ends(self, owner: 'CutCSG') -> Tuple[Optional[V3], Optional[V3]]:
        """Return the edge's two endpoints, None for one at an infinite end."""
        side, other = self.faces
        if isinstance(other, ExtrusionCap):
            end = other is ExtrusionCap.TOP
            count = len(owner.points) if isinstance(owner, ConvexPolygonExtrusion) else len(owner.bottom_points)  # type: ignore[attr-defined]
            return _profile_corner(owner, side, end), _profile_corner(owner, (side + 1) % count, end)
        return _profile_corner(owner, other, False), _profile_corner(owner, other, True)

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Line]:
        if not isinstance(owner, (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft)):
            return None
        start, end = self._ends(owner)
        if start is not None and end is not None:
            if safe_zero_test(giraffe_norm(end - start)):
                return None
            return Line(direction=safe_normalize_vector(end - start), point=start)
        side, other = self.faces
        if isinstance(other, ExtrusionCap) or not isinstance(owner, ConvexPolygonExtrusion):
            return None  # a profile edge at an infinite end: there is none
        # A long edge of an extrusion open at an end: through its vertex, along the extrusion.
        orientation = owner.transform.orientation.matrix
        vertex = owner.points[other]
        return Line(
            direction=safe_transform_vector(orientation, Matrix([scalar(0), scalar(0), scalar(1)])),
            point=owner.transform.position + safe_transform_vector(
                orientation, Matrix([vertex[0], vertex[1], scalar(0)])))

    def declared_ends(self, owner: 'CutCSG') -> Optional[Tuple[V3, V3]]:
        """Return the edge's two ends, or None if either is at an infinite end."""
        start, end = self._ends(owner)
        return None if start is None or end is None else (start, end)


def convex_profile_edge_features(sides: int) -> Dict[FeatureKey, CSGFeature]:
    """Return the default edges of a convex extrusion or loft with `sides` sides, in key order:
    side n against side n+1, then each side against the start cap, then the end cap.
    """
    features: Dict[FeatureKey, CSGFeature] = {}
    for side in range(sides):
        for key, faces in (
            ((FeatureCategory.ARRIS, side), (side, (side + 1) % sides)),
            (arris_against_cap(side, sides, end=False), (side, ExtrusionCap.BOTTOM)),
            (arris_against_cap(side, sides, end=True), (side, ExtrusionCap.TOP)),
        ):
            features[key] = ConvexProfileEdgeFeature(
                name=default_feature_name(key), key=key, faces=faces,
                properties=_DEFAULT_FEATURE_PROPERTIES)
    return features


class FeatureSource(Flag):
    """Which features a query wants: DEFAULTS, OVERRIDES (authored), or BOTH."""

    DEFAULTS = 1
    OVERRIDES = 2
    BOTH = 3


@dataclass(frozen=True)
class FeatureOverride:
    """Overrides the name and properties of a default feature.

    Args:
        key: the default, e.g. prism_face_key(PrismFace.RIGHT).
        name: new name; None keeps the default's.
        properties: replaces the default's properties; None keeps them.
    """
    key: FeatureKey
    name: Optional[str] = None
    properties: Optional[FeatureProperties] = None

    def apply(self, default: 'CSGFeature') -> 'CSGFeature':
        """Return the default feature at `key` with this override applied."""
        return replace(
            default,
            name=default.name if self.name is None else self.name,
            properties=default.properties if self.properties is None else self.properties,
        )


def shoulder_override(key: FeatureKey, name: Optional[str] = None,
                      group: FeatureGroup = FeatureGroup.NONE) -> FeatureOverride:
    """Return an override marking the default at `key` as a shoulder plane, in group `group`."""
    return FeatureOverride(key, name, FeatureProperties(group=group, purpose=FeaturePurpose.SHOULDER))


#TODO this should an ABC? or is that not allowed for dual inheritance or osemtihng?
@dataclass(frozen=True)
class HasFeatures:
    """Mixin for primitives that declare their own features.

    Args:
        feature_overrides: overrides of this shape's defaults, at most one per key.
        extra_features: keyless features with their own geometry (a bore's axis, a reference plane).

    Both are validated on construction.
    """

    feature_overrides: Sequence[FeatureOverride] = field(default=(), kw_only=True)
    extra_features: Sequence['CSGFeature'] = field(default=(), kw_only=True)

    def __post_init__(self):
        if self.feature_overrides or self.extra_features:
            self._check_authored_features()

    # TODO should probably make this an abstract method, or... this overrides the CutCSG one or osemthing? plesae update the comment explaniing if that's the case
    def default_features(self) -> Dict['FeatureKey', 'CSGFeature']:
        """Return this primitive's default features by key. Must all be in FeatureGroup.NONE."""
        return {}

    def _check_authored_features(self) -> None:
        """Raise for overrides of missing or repeated keys, keyed extras, or repeated names."""
        defaults = self.default_features()
        shape = type(self).__name__

        overridden: Dict['FeatureKey', FeatureOverride] = {}
        for override in self.feature_overrides:
            if override.key not in defaults:
                known = ', '.join(sorted(feature.name for feature in defaults.values())) or 'none'
                raise ValueError(
                    f"{shape} has no default feature {default_feature_name(override.key)} "
                    f"to override (as {override.name!r}); its defaults are: {known}")
            if override.key in overridden:
                raise ValueError(
                    f"{shape} overrides {default_feature_name(override.key)} twice, "
                    f"as {overridden[override.key].name!r} and {override.name!r}")
            overridden[override.key] = override

        for extra in self.extra_features:
            key = extra.feature_key()
            if key is not None:
                raise ValueError(
                    f"extra feature {extra.name!r} on {shape} names the default "
                    f"{default_feature_name(key)}; rename it with a FeatureOverride "
                    f"in feature_overrides instead")

        names = [defaults[o.key].name if o.name is None else o.name for o in overridden.values()]
        names += [extra.name for extra in self.extra_features]
        names += [feature.name for key, feature in defaults.items() if key not in overridden]
        seen: set = set()
        repeated = sorted({name for name in names if name in seen or seen.add(name)})
        if repeated:
            raise ValueError(f"{shape} names more than one feature {', '.join(map(repr, repeated))}")

    # TODO rename to get_self_declared_features or something
    def get_declared_features(
        self, source: 'FeatureSource' = FeatureSource.BOTH,
    ) -> List['CSGFeature']:
        """Return the features this node declares (defaults with overrides applied, plus extras), cached per node."""
        return list(_declared_features(self, source))

    def _work_out_declared_features(self, source: 'FeatureSource') -> List['CSGFeature']:
        defaults = self.default_features()
        if source is FeatureSource.DEFAULTS:
            return list(defaults.values())
        overridden = {override.key: override.apply(defaults[override.key])
                      for override in self.feature_overrides}
        authored = [*overridden.values(), *self.extra_features]
        if source is FeatureSource.OVERRIDES:
            return authored
        return authored + [feature for key, feature in defaults.items() if key not in overridden]


@memo_by_identity
def _declared_features(csg: 'HasFeatures', source: 'FeatureSource') -> List['CSGFeature']:
    return csg._work_out_declared_features(source)


def face_plane_carriers(csg: 'HasFeatures') -> Dict[FeatureKey, Carrier]:
    """Return a CarrierPlane per default face of `csg` with a plane, and per extra PlaneFeature, by key.

    Cached per node; the returned dict is a copy.
    """
    return dict(_face_plane_carriers(csg))


@memo_by_identity
def _face_plane_carriers(csg: 'HasFeatures') -> Dict[FeatureKey, Carrier]:
    carriers: Dict[FeatureKey, Carrier] = {}
    for key, feature in csg.default_features().items():
        if not isinstance(feature, FaceFeature):
            continue
        plane = feature.locate_simple_unbounded(cast(CutCSG, csg))
        if plane is not None:
            carriers[key] = CarrierPlane(plane)
    for index, extra in enumerate(csg.extra_features):
        if isinstance(extra, PlaneFeature):
            plane = extra.locate_simple_unbounded(cast(CutCSG, csg))
            if plane is not None:
                carriers[(FeatureCategory.EXTRA, index)] = CarrierPlane(plane)
    return carriers


# TODO consider making this typed, you could do this by adding... an optional owner field to FeatureHit and removing this class all together. Or making several OwnedFeatureHit classes is fine too I guess.
@dataclass(frozen=True)
class OwnedFeatureHit(Generic[F_co]):
    """A feature with the node that owns it."""
    feature: F_co
    owner: 'CutCSG'

    @property
    def name(self) -> str:
        return self.feature.name

    def feature_type(self) -> CSGFeatureType:
        return self.feature.feature_type()

    @property
    def properties(self) -> FeatureProperties:
        return self.feature.properties

    def locate_simple_unbounded(self) -> Optional['LocatedFeatureGeometry']:
        return self.feature.locate_simple_unbounded(self.owner)


def hit_of_kind(hit: OwnedFeatureHit[CSGFeature], kind: Type[K]) -> Optional[OwnedFeatureHit[K]]:
    """Return the hit typed as `kind`, or None if its feature isn't one."""
    return cast(OwnedFeatureHit[K], hit) if isinstance(hit.feature, kind) else None


@dataclass(frozen=True)
class CutCSGLabel:
    """A CSG node's optional name."""

    name: Optional[str] = None

    @staticmethod
    def NoLabel() -> 'CutCSGLabel':
        """Return the label of an unnamed node."""
        return CutCSGLabel()

    def is_labeled(self) -> bool:
        """Return whether the node has a name."""
        return self.name is not None

    def __bool__(self) -> bool:
        return self.is_labeled()

    def __repr__(self) -> str:
        return f"CutCSGLabel({self.name!r})" if self.name is not None else "NoLabel"


# =================================================================================================
# TODO GLOBAL STATE -- REMOVE. A stopgap for pick speed, not a design.
#
# point_tests_memo hides a memo in a ContextVar, and every CutCSG subclass's contains_point,
# is_point_on_boundary and get_outward_normal is wrapped (__init_subclass__) to read it. That is a
# global in all but name: a point test answers differently depending on what block it runs inside,
# and nothing in its signature says so.
#
# Why it exists: collect_feature_hits gates each level of a tree on is_point_on_boundary, and each
# level's test asks every node below it again, so a walk asks each node once per ancestor. Inside
# a pick, the memo makes that once per node (cute frame top-view picks 15 -> 5 ms).
#
# The refactor: pass a context object through the point tests and the feature walks
# (find_all_features, collect_feature_hits, SolidsAtPoint, the Difference / SolidUnion tests),
# owned by whoever asks -- a pick, a generator run -- and holding this memo. Then drop the
# ContextVar, the wrapping in __init_subclass__ and point_tests_memo.
# =================================================================================================
_POINT_TESTS = ("contains_point", "is_point_on_boundary", "get_outward_normal")
_point_tests_memo: ContextVar[Optional[Dict[Tuple, Tuple['CutCSG', object]]]] = ContextVar(
    "_point_tests_memo", default=None)


@contextmanager
def point_tests_memo() -> Iterator[None]:
    """Context manager caching point tests (_POINT_TESTS) until the block ends."""
    if _point_tests_memo.get() is not None:
        yield
        return
    token = _point_tests_memo.set({})
    try:
        yield
    finally:
        _point_tests_memo.reset(token)


def _memoized_point_test(test: Callable) -> Callable:
    @functools.wraps(test)
    def memoized(self: 'CutCSG', point: V3, eps: Optional[Numeric] = None):
        memo = _point_tests_memo.get()
        if memo is None:
            return test(self, point, eps)
        key = (test, id(self), float(point[0]), float(point[1]), float(point[2]), eps)
        kept = memo.get(key)
        if kept is None or kept[0] is not self:
            kept = (self, test(self, point, eps))
            memo[key] = kept
        return kept[1]
    return memoized


@dataclass(frozen=True)
class CutCSG(ABC):
    """Base class of CSG nodes."""
    label: CutCSGLabel = field(default_factory=CutCSGLabel.NoLabel, kw_only=True)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        for name in _POINT_TESTS:
            if name in cls.__dict__:
                setattr(cls, name, _memoized_point_test(cls.__dict__[name]))

    @abstractmethod
    def __repr__(self) -> str:
        pass

    @classmethod
    def display_name(cls) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", " ", cls.__name__).lower()

    # TODO rename to get_self_declared_features or something    
    def get_declared_features(
        self, source: 'FeatureSource' = FeatureSource.BOTH,
    ) -> List[CSGFeature]:
        """Return the features this node declares. Empty for compound nodes."""
        return []

    @abstractmethod
    def carriers(self) -> Dict[FeatureKey, Carrier]:
        """Return this node's solver carriers by key.

        TODO decide whether to drop NEVER_MARK features' carriers, or tag OPTIONAL ones
        """
        ...

    # does not include derived features
    # TODO rename this to be more descriptive
    def collect_feature_hits(
        self,
        point: V3,
        tolerances: FeatureTestTolerances,
    ) -> List['OwnedFeatureHit']:
        """Return every declared feature in this subtree that `point` is on, each at its type's tolerance.

        Real features also require `point` on this node's boundary; non-real ones don't.
        """
        hits: List['OwnedFeatureHit'] = [
            OwnedFeatureHit(feature=feature, owner=self)
            for feature in self.get_declared_features()
            if feature.test_point_unbounded(
                self, point, tolerances.for_type(feature.feature_type()))
        ]
        for child in csg_children(self):
            hits.extend(child.collect_feature_hits(point, tolerances))
        return _drop_real_hits_if_not_on_boundary(self, hits, point, tolerances)

    # so basically collect_feature_hits + derived features
    # TODO rename this to be more descriptive
    def find_all_features(
        self,
        point: V3,
        test_tolerances: Optional[FeatureTestTolerances] = None,
    ) -> List['OwnedFeatureHit']:
        """Return every feature at `point`, best first: declared ones in this subtree plus derived edges
        and points.

        Faces are paired into edges at the EDGE tolerance, and declared edges crossed with faces at the
        POINT tolerance, so edges and points can be picked from further away than their faces. Derived
        duplicates are dropped at the end.
        """
        with point_tests_memo():
            return self._find_all_features(point, test_tolerances)

    def _find_all_features(
        self, point: V3, test_tolerances: Optional[FeatureTestTolerances],
    ) -> List['OwnedFeatureHit']:
        tolerances = DEFAULT_FEATURE_TEST_TOLERANCES if test_tolerances is None else test_tolerances
        hits = self.collect_feature_hits(point, tolerances)

        def of_type(gathered, feature_type):
            return [hit for hit in gathered if hit.feature.feature_type() == feature_type]

        # One gather for both derivations, at the widest tolerance; derived features then test the point themselves.
        #
        # TODO two walks of the tree rather than one, because the gather above also applies the boundary
        # gate at `tolerances.face`. Separating "near the feature" from "on the boundary" would allow one walk.
        candidates = self.collect_feature_hits(
            point, FeatureTestTolerances.uniform(tolerances.point))

        # NOTE for now we don't allow derived features to produce more derived features
        derived_edges = _within_tolerance(
            derive_edge_hits(self, of_type(candidates, CSGFeatureType.FACE)),
            point, tolerances)
        derived_points = _within_tolerance(
            derive_point_hits(
                self,
                of_type(candidates, CSGFeatureType.EDGE),
                of_type(candidates, CSGFeatureType.FACE),
            ),
            point, tolerances)

        return _drop_duplicate_derived(
            _sort_feature_hits(hits + derived_edges + derived_points), root=self)

    def find_first_feature(
        self,
        point: V3,
        test_tolerances: Optional[FeatureTestTolerances] = None,
    ) -> Optional['OwnedFeatureHit']:
        """Return the best feature at `point` (see _sort_feature_hits), or None."""
        hits = self.find_all_features(point, test_tolerances=test_tolerances)
        if not hits:
            return None
        return _sort_feature_hits(hits)[0]


    @abstractmethod
    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is inside or on the boundary."""
        pass

    @abstractmethod
    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on the boundary."""
        pass
    
    @abstractmethod
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """Return the outward normal at boundary point `point`, or None. Undefined off the boundary."""
        pass

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        """Return the outward normal of every face meeting at boundary point `point` (several on an edge or corner).

        Shapes that can't tell return get_outward_normal's one.
        """
        normal = self.get_outward_normal(point, eps=eps)
        return [] if normal is None else [normal]

    @abstractmethod
    def get_aabb(self) -> 'AxisAlignedBoundingBox':
        """Return the bounding box. An infinite primitive warns and returns all-None bounds."""
        pass


    # --- geometry the CSG walkers ask of a primitive (edges_on_csg, cross_sections) -----------------
    # Defaults work from bounding_half_spaces; a primitive overrides what it answers differently.

    def bounding_half_spaces(self) -> 'SolidBounds':
        """Return the half spaces whose intersection contains this primitive (an outward approximation),
        EMPTY, or UNKNOWN. Use edges_on_csg.solid_bounds, which caches it."""
        from .edges_on_csg import UNKNOWN_BOUNDS
        return UNKNOWN_BOUNDS

    def is_exactly_its_bounds(self) -> bool:
        """Return whether bounding_half_spaces describes this primitive exactly."""
        return False

    def exact_line_spans(self, line: Line, seed: 'Span', tolerance: float, removing: bool) -> Optional[List['Span']]:
        """Return the spans of `seed` along `line` inside this primitive, exactly, or None if not solved.

        A line on the boundary is kept; `removing` flips the comparison for a subtracted solid.
        """
        from .edges_on_csg import _spans_within_primitive, solid_bounds
        if not self.is_exactly_its_bounds():
            return None
        bounds = solid_bounds(self)
        if bounds.is_unknown:
            return None
        return [] if bounds.is_empty else _spans_within_primitive(bounds.require_faces(), line, seed, tolerance, removing)

    def angles_around_line(self, at, direction, basis, tolerance: float) -> Optional['AngleSpans']:
        """Return the angles around the line through `at` this primitive occupies, or None if not solved."""
        from .edges_on_csg import _plane_angles, solid_bounds
        if not self.is_exactly_its_bounds():
            return None
        bounds = solid_bounds(self)
        if bounds.is_unknown:
            return None
        return [] if bounds.is_empty else _plane_angles(bounds.require_faces(), at, direction, basis, tolerance)

    def line_crossings(self, origin, direction) -> List[float]:
        """Return the stations along the line (numpy `origin`, unit `direction`) where it crosses this
        primitive's surfaces, so where the solid around it can change."""
        from .edges_on_csg import _plane_stations, solid_bounds
        bounds = solid_bounds(self)
        if bounds.is_unknown or bounds.is_empty:
            return []
        return _plane_stations(bounds.require_faces(), origin, direction)

    def plane_sides(self, frame, seed) -> 'Sides':
        """Return (front, back): where this primitive has material just in front of `frame`'s plane and
        just behind, within `seed`. Raises cross_sections.CannotCrossSection if it can't be cut."""
        from .cross_sections import _CannotCrossSection, _half_space_cross_section
        from .edges_on_csg import solid_bounds
        bounds = solid_bounds(self)
        if bounds.is_empty:
            return [], []
        if bounds.is_unknown:
            raise _CannotCrossSection(type(self).__name__)
        return _half_space_cross_section(bounds.require_faces(), frame, seed)


def csg_children(csg: CutCSG) -> List[CutCSG]:
    """Return the direct children of `csg`; empty for a primitive."""
    if isinstance(csg, SolidUnion):
        return list(csg.children)
    if isinstance(csg, Intersection):
        return [csg.left, csg.right]
    if isinstance(csg, Difference):
        return [csg.base, *csg.subtract]
    return []


def map_primitives(csg: CutCSG, change: Callable[['HasFeatures'], CutCSG]) -> CutCSG:
    """Return `csg` with `change` applied to every feature-declaring primitive."""
    if isinstance(csg, SolidUnion):
        return replace(csg, children=[map_primitives(child, change) for child in csg.children])
    if isinstance(csg, Intersection):
        return replace(csg, left=map_primitives(csg.left, change), right=map_primitives(csg.right, change))
    if isinstance(csg, Difference):
        return replace(csg, base=map_primitives(csg.base, change),
                       subtract=[map_primitives(child, change) for child in csg.subtract])
    if isinstance(csg, HasFeatures):
        return change(csg)
    return csg


def strip_features(csg: CutCSG) -> CutCSG:
    """Return `csg` with every override and extra feature removed, all the way down; only defaults remain.

    For copies of geometry already in another tree (e.g. a relief built from another timber).
    """
    return map_primitives(csg, lambda primitive: replace(primitive, feature_overrides=(), extra_features=())
                          if primitive.feature_overrides or primitive.extra_features else cast(CutCSG, primitive))


def with_purpose(csg: CutCSG, purpose: 'FeaturePurpose') -> CutCSG:
    """Return `csg` with every feature, all the way down, given purpose `purpose`."""
    def change(primitive: 'HasFeatures') -> CutCSG:
        authored = {override.key: override for override in primitive.feature_overrides}
        overrides = []
        for key, default in primitive.default_features().items():
            override = authored.get(key, FeatureOverride(key))
            properties = override.properties if override.properties is not None else default.properties
            overrides.append(replace(override, properties=replace(properties, purpose=purpose)))
        extras = [replace(extra, properties=replace(extra.properties, purpose=purpose))
                  for extra in primitive.extra_features]
        return cast(CutCSG, replace(primitive, feature_overrides=overrides, extra_features=extras))

    return map_primitives(csg, change)


class CSGParity(Enum):
    """Whether a node adds material to the result (ADDITIVE) or removes it (SUBTRACTIVE)."""

    ADDITIVE = 0
    SUBTRACTIVE = 1

    def flipped(self) -> 'CSGParity':
        return CSGParity.SUBTRACTIVE if self is CSGParity.ADDITIVE else CSGParity.ADDITIVE


def csg_children_with_parity(
    csg: CutCSG,
    parity: CSGParity = CSGParity.ADDITIVE,
) -> List[Tuple[CutCSG, CSGParity]]:
    """Return the children of `csg` with their parity, in csg_children order. Only a Difference's subtract children invert."""
    if isinstance(csg, Difference):
        flipped = parity.flipped()
        return [(csg.base, parity), *((sub, flipped) for sub in csg.subtract)]
    return [(child, parity) for child in csg_children(csg)]


def walk_csg_with_parity(
    root: CutCSG,
    parity: CSGParity = CSGParity.ADDITIVE,
) -> Iterator[Tuple[CutCSG, CSGParity]]:
    """Yield every node under `root`, including it, with its parity."""
    yield root, parity
    for child, child_parity in csg_children_with_parity(root, parity):
        yield from walk_csg_with_parity(child, child_parity)


def carrier_map(root: CutCSG) -> CarrierMap:
    """Return the CarrierMap of every primitive carrier in the tree, coincident planes merged."""
    def walk(node: CutCSG) -> Iterator[CutCSG]:
        yield node
        for child in csg_children(node):
            yield from walk(child)
    carriers = {CarrierRef(node, key): carrier
                for node in walk(root) for key, carrier in node.carriers().items()}
    return CarrierMap(carriers, merge_coincident_planes(carriers))


@dataclass(frozen=True)
class EmptyCSG(CutCSG):
    """A solid with no points."""

    @classmethod
    def display_name(cls) -> str:
        return "empty"

    def __repr__(self) -> str:
        return "EmptyCSG()"

    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return {}

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        return False

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        return False

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        return None

    def get_aabb(self) -> 'AxisAlignedBoundingBox':
        return AxisAlignedBoundingBox(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=0,
            max_y=0,
            max_z=0,
            is_empty=True,
        )


    def bounding_half_spaces(self) -> 'SolidBounds':
        from .edges_on_csg import EMPTY_BOUNDS
        return EMPTY_BOUNDS

    def is_exactly_its_bounds(self) -> bool:
        return True


@dataclass(frozen=True)
class HalfSpace(HasFeatures, CutCSG):
    """An infinite half space: all points P with P · normal >= offset.

    Args:
        normal: points into the half space.
        offset: the plane's signed distance from the origin along `normal`.
    """

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Return its one face."""
        key = (FeatureCategory.SIDE, 0)
        return {key: HalfSpaceFeature(name=default_feature_name(key),
                                      properties=_DEFAULT_FEATURE_PROPERTIES)}

    @classmethod
    def display_name(cls) -> str:
        return "half-space"
    normal: Direction3D
    offset: Numeric = scalar(0)
    # Features this primitive names on its own boundary. Private: read it
    def __repr__(self) -> str:
        return f"HalfSpace(normal={self.normal.T}, offset={self.offset})"
    
    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return face_plane_carriers(self)

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether P · normal >= offset."""
        # Compute dot product: point · normal
        dot_product = safe_dot_product(point, self.normal)
        return safe_compare(dot_product, self.offset, Comparison.GE, eps=eps)
    
    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether P · normal == offset."""
        # Compute dot product: point · normal
        dot_product = safe_dot_product(point, self.normal)
        # Use safe_zero_test to handle Float vs Integer comparison with tolerance
        return safe_zero_test(dot_product - self.offset, eps=eps)
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """Return -normal."""
        return -self.normal

    def get_aabb(self) -> AxisAlignedBoundingBox:
        warnings.warn(
            "get_aabb() called on HalfSpace, which has infinite extent — result is unbounded",
            UserWarning,
            stacklevel=2,
        )
        return AxisAlignedBoundingBox(None, None, None, None, None, None)


    def bounding_half_spaces(self) -> 'SolidBounds':
        from .edges_on_csg import SolidBounds
        # Inside is p . normal >= offset, so the outward normal is the other way.
        normal = unit_vector(self.normal)
        return SolidBounds.of([(-normal, normal * self.offset)])

    def is_exactly_its_bounds(self) -> bool:
        return True

    
@dataclass(frozen=True)
class RectangularPrism(HasFeatures, CutCSG):
    """A prism with rectangular cross-section, optionally infinite at either end. Parameterized like a Timber.

    The cross-section (`size` = width along local X, height along local Y) is centred at the
    transform's position; the prism runs from `start_distance` to `end_distance` along local Z.
    None for either distance makes that end infinite.
    """

    # Every prism has the same defaults (they locate against their owner), so
    # they are built once and shared.
    _default_features_memo: ClassVar[Optional[Dict[FeatureKey, CSGFeature]]] = None

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        if RectangularPrism._default_features_memo is None:
            RectangularPrism._default_features_memo = self._build_default_features()
        return dict(RectangularPrism._default_features_memo)

    def _build_default_features(self) -> Dict[FeatureKey, CSGFeature]:
        features: Dict[FeatureKey, CSGFeature] = {}

        def named(key: FeatureKey, feature_for) -> None:
            features[key] = feature_for(default_feature_name(key))

        for face, key in _PRISM_CAP_KEYS.items():
            named(key, lambda name, face=face: SimpleRectangularPrismFeature(
                name=name, face=face, properties=_DEFAULT_FEATURE_PROPERTIES))
        for index, face in enumerate(_PRISM_SIDE_ORDER):
            named((FeatureCategory.SIDE, index),
                  lambda name, face=face: SimpleRectangularPrismFeature(
                      name=name, face=face, properties=_DEFAULT_FEATURE_PROPERTIES))

        # Through .of, so these are named the way timber.py names the same
        # arrises rather than in a second order of their own.
        sides = len(_PRISM_SIDE_ORDER)
        for index in range(sides):
            side, next_side = _PRISM_SIDE_ORDER[index], _PRISM_SIDE_ORDER[(index + 1) % sides]
            named((FeatureCategory.ARRIS, index),
                  lambda name, side=side, next_side=next_side: SimpleRectangularPrismEdgeFeature.of(
                      name, side, next_side, properties=_DEFAULT_FEATURE_PROPERTIES))
            for cap in (PrismFace.BOTTOM, PrismFace.TOP):
                named(arris_against_cap(index, sides, end=cap is PrismFace.TOP),
                      lambda name, cap=cap, side=side: SimpleRectangularPrismEdgeFeature.of(
                          name, cap, side, properties=_DEFAULT_FEATURE_PROPERTIES))
                named(corner_on_cap(index, sides, end=cap is PrismFace.TOP),
                      lambda name, cap=cap, side=side, next_side=next_side: SimpleRectangularPrismVertexFeature.of(
                          name, cap, side, next_side, properties=_DEFAULT_FEATURE_PROPERTIES))
        return features

    @classmethod
    def display_name(cls) -> str:
        return "prism"
    size: V2
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None  # starting distance of the prism in the direction of the +Z axis. None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # ending distance of the prism in the direction of the +Z axis. None means infinite in positive direction
    # (width_dir, height_dir, length_dir), unit vectors in global coordinates: every point test asks.
    _axes_precomputed: Tuple[Direction3D, Direction3D, Direction3D] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        super().__post_init__()
        m = self.transform.orientation.matrix
        axes = (Matrix([m[0, 0], m[1, 0], m[2, 0]]), Matrix([m[0, 1], m[1, 1], m[2, 1]]),
                Matrix([m[0, 2], m[1, 2], m[2, 2]]))
        object.__setattr__(self, "_axes_precomputed", axes)

    # Features this primitive names on its own boundary. Private: read it
    def get_bottom_position(self) -> V3:
        """Return the centre of the start end. Raises ValueError if it is infinite."""
        if self.start_distance is None:
            raise ValueError("Cannot get bottom position of infinite prism (start_distance is None)")
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.start_distance]))
    
    def get_top_position(self) -> V3:
        """Return the centre of the far end. Raises ValueError if it is infinite."""
        if self.end_distance is None:
            raise ValueError("Cannot get top position of infinite prism (end_distance is None)")
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.end_distance]))
    
    def __repr__(self) -> str:
        return (f"RectangularPrism(size={self.size.T}, transform={self.transform}, "
                f"start={self.start_distance}, end={self.end_distance})")
    
    def equals_prism(self, other: 'RectangularPrism') -> bool:
        """Return whether every parameter equals `other`'s."""
        # Check size components
        if not safe_equality_test(self.size[0], other.size[0]) or not safe_equality_test(self.size[1], other.size[1]):
            return False

        # Check transform position
        if not (safe_equality_test(self.transform.position[0], other.transform.position[0]) and
                safe_equality_test(self.transform.position[1], other.transform.position[1]) and
                safe_equality_test(self.transform.position[2], other.transform.position[2])):
            return False

        # Check transform orientation matrix
        for i in range(3):
            for j in range(3):
                if not safe_equality_test(self.transform.orientation.matrix[i, j], other.transform.orientation.matrix[i, j]):
                    return False
        
        # Check start_distance (handle None case)
        if self.start_distance is None and other.start_distance is None:
            pass  # Both None, equal
        elif self.start_distance is None or other.start_distance is None:
            return False  # One is None, other isn't
        elif not safe_compare(self.start_distance - other.start_distance, 0, Comparison.EQ):
            return False
        
        # Check end_distance (handle None case)
        if self.end_distance is None and other.end_distance is None:
            pass  # Both None, equal
        elif self.end_distance is None or other.end_distance is None:
            return False  # One is None, other isn't
        elif not safe_compare(self.end_distance - other.end_distance, 0, Comparison.EQ):
            return False
        
        return True
    
    def _local_axes(self) -> Tuple[Direction3D, Direction3D, Direction3D]:
        """Return the (width, height, length) unit axes in global coordinates."""
        return self._axes_precomputed

    def _local_coords(self, point: V3) -> Tuple[Numeric, Numeric, Numeric]:
        """Return a global point's coordinates along the prism's (width, height, length) axes."""
        local_point = point - self.transform.position
        width_dir, height_dir, length_dir = self._local_axes()
        x_coord = safe_dot_product(local_point, width_dir)
        y_coord = safe_dot_product(local_point, height_dir)
        z_coord = safe_dot_product(local_point, length_dir)
        return x_coord, y_coord, z_coord

    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return face_plane_carriers(self)

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is inside or on the boundary."""
        x_coord, y_coord, z_coord = self._local_coords(point)

        # Check bounds in each dimension
        half_width = self.size[0] / 2
        half_height = self.size[1] / 2

        # Check width and height bounds
        if safe_compare(Abs(x_coord), half_width, Comparison.GT, eps=eps) or safe_compare(Abs(y_coord), half_height, Comparison.GT, eps=eps):
            return False

        # Check length bounds
        if self.start_distance is not None and safe_compare(z_coord, self.start_distance, Comparison.LT, eps=eps):
            return False
        if self.end_distance is not None and safe_compare(z_coord, self.end_distance, Comparison.GT, eps=eps):
            return False

        return True

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on the boundary."""
        # First check if point is contained
        if not self.contains_point(point, eps=eps):
            return False

        x_coord, y_coord, z_coord = self._local_coords(point)

        # Check if on any face
        half_width = self.size[0] / 2
        half_height = self.size[1] / 2

        # On width faces
        if safe_equality_test(Abs(x_coord), half_width, eps=eps):
            return True

        # On height faces
        if safe_equality_test(Abs(y_coord), half_height, eps=eps):
            return True

        # On length faces (if finite)
        if self.start_distance is not None and safe_equality_test(z_coord, self.start_distance, eps=eps):
            return True
        if self.end_distance is not None and safe_equality_test(z_coord, self.end_distance, eps=eps):
            return True

        return False

    def _each_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Iterator[Direction3D]:
        """Yield the outward normal of each face `point` is on: one on a face, two on an edge, three at a corner."""
        x_coord, y_coord, z_coord = self._local_coords(point)
        width_dir, height_dir, length_dir = self._local_axes()

        half_width = self.size[0] / 2
        half_height = self.size[1] / 2

        # Check which face(s) the point is on
        # For edges/corners, we'll return one of the normals
        # Prioritize: length faces (top/bottom), then width faces, then height faces
        # This prioritization makes sense for typical CSG operations where end faces are often involved

        # TODO consider checking if point is on edges/corners and return averages instead, probably not necessary for now

        # On length faces (top/bottom) - check these first
        if self.start_distance is not None and safe_equality_test(z_coord, self.start_distance, eps=eps):
            yield -length_dir  # Bottom face, normal points in -length direction (outward)
        if self.end_distance is not None and safe_equality_test(z_coord, self.end_distance, eps=eps):
            yield length_dir  # Top face, normal points in +length direction (outward)

        # On width faces (right/left)
        if safe_equality_test(Abs(x_coord), half_width, eps=eps):
            if safe_compare(x_coord, 0, Comparison.GT, eps=eps):
                yield width_dir  # Right face, normal points in +width direction
            else:
                yield -width_dir  # Left face, normal points in -width direction

        # On height faces (front/back)
        if safe_equality_test(Abs(y_coord), half_height, eps=eps):
            if safe_compare(y_coord, 0, Comparison.GT, eps=eps):
                yield height_dir  # Front face, normal points in +height direction
            else:
                yield -height_dir  # Back face, normal points in -height direction

        # Should not reach here if point is actually on boundary
        return

    # returns the first outward normal on the CSG, use get_outward_normals if that's insufficient.
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        return next(self._each_outward_normal(point, eps=eps), None)

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        return list(self._each_outward_normal(point, eps=eps))

    def get_aabb(self) -> AxisAlignedBoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite RectangularPrism — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return AxisAlignedBoundingBox(None, None, None, None, None, None)

        half_w = self.size[0] / scalar(2)
        half_h = self.size[1] / scalar(2)

        corners_global = [
            self.transform.local_to_global(Matrix([x_sign * half_w, y_sign * half_h, z]))
            for x_sign in (scalar(-1), scalar(1))
            for y_sign in (scalar(-1), scalar(1))
            for z in (self.start_distance, self.end_distance)
        ]

        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]
        return AxisAlignedBoundingBox(
            _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
            _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
        )


    def bounding_half_spaces(self) -> 'SolidBounds':
        from .edges_on_csg import SolidBounds, _extrusion_caps
        width_dir, height_dir, length_dir = self._local_axes()
        centre = self.transform.position
        half_width, half_height = self.size[0] / scalar(2), self.size[1] / scalar(2)
        return SolidBounds.of([
            (width_dir, centre + width_dir * half_width),
            (-width_dir, centre - width_dir * half_width),
            (height_dir, centre + height_dir * half_height),
            (-height_dir, centre - height_dir * half_height),
            *_extrusion_caps(length_dir, centre, self.start_distance, self.end_distance),
        ])

    def is_exactly_its_bounds(self) -> bool:
        return True


# UNUSED, but seems like a nice to have so keep it around
def make_finite_rectangular_prism_from_half_space(half_space: HalfSpace, size_of_space: Numeric, depth_of_space: Numeric) -> RectangularPrism:
    """Return a finite prism standing in for `half_space` near its boundary.

    Its start face lies on the boundary plane, it runs `depth_of_space` into the half space, and its
    square `size_of_space` cross-section is centred where the normal through the origin meets the plane.
    """
    # Unit normal pointing into the half-space (HalfSpace contains points where P·normal >= offset)
    unit_normal = safe_normalize_vector(half_space.normal)

    # Pick a reference direction not parallel to the normal to build a perpendicular x-axis.
    world_x = Matrix([scalar(1), scalar(0), scalar(0)])
    world_y = Matrix([scalar(0), scalar(1), scalar(0)])
    if safe_compare(Abs(safe_dot_product(unit_normal, world_x)) - scalar(9, 10), 0, Comparison.LT):
        reference = world_x
    else:
        reference = world_y

    # Gram-Schmidt: project reference onto plane perpendicular to unit_normal, then normalize.
    x_direction = safe_normalize_vector(
        reference - unit_normal * safe_dot_product(reference, unit_normal)
    )

    orientation = Orientation.from_z_and_x(unit_normal, x_direction)

    # A point on the boundary plane: nearest point to origin on the plane P·normal = offset.
    # For normalized normal n, plane is P·n = offset/|normal|.
    normal_magnitude = safe_norm(half_space.normal)
    point_on_plane = unit_normal * (half_space.offset / normal_magnitude)

    return RectangularPrism(
        size=Matrix([size_of_space, size_of_space]),
        transform=Transform(position=point_on_plane, orientation=orientation),
        start_distance=scalar(0),
        end_distance=depth_of_space,
    )

@dataclass(frozen=True)
class Cylinder(HasFeatures, CutCSG):
    """A cylinder, optionally infinite at either end.

    The axis runs through `position` along `axis_direction`, from `start_distance` to `end_distance`;
    None for either makes that end infinite.
    """
    # TODO consider just making this a Transform object, even though we don't care about one of the DOFs
    axis_direction: Direction3D  # direction of the cylinder's axis, which is the +Z local axis
    radius: Numeric
    position: V3 = field(default_factory=lambda: Matrix([scalar(0), scalar(0), scalar(0)]))  # Position in global coordinates
    start_distance: Optional[Numeric] = None  # None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # None means infinite in positive direction

    # Features this primitive names on its own boundary. Private: read it
    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Return its two caps and the barrel."""
        features: Dict[FeatureKey, CSGFeature] = {
            key: SimpleCylinderCapFeature(name=default_feature_name(key), part=part,
                                          properties=_DEFAULT_FEATURE_PROPERTIES)
            for key, part in ((START_CAP, CylinderPart.BOTTOM), (END_CAP, CylinderPart.TOP))
        }
        features[CYLINDER_BARREL] = SimpleCylinderBarrelFeature(
            name=default_feature_name(CYLINDER_BARREL), properties=_DEFAULT_FEATURE_PROPERTIES)
        return features

    def carriers(self) -> Dict[FeatureKey, Carrier]:
        """Return the axis, the barrel around it, and a plane for each finite cap."""
        carriers = face_plane_carriers(self)
        carriers[CYLINDER_AXIS] = CarrierLine(
            Line(direction=safe_normalize_vector(self.axis_direction), point=self.position))
        carriers[CYLINDER_BARREL] = CarrierBarrel(axis=CYLINDER_AXIS, radius=self.radius)
        return carriers

    def _axial_and_radial(self, point: V3) -> Tuple[Numeric, Numeric]:
        """Return `point`'s distance along the axis from `position`, and from the axis."""
        local_point = point - self.position
        axis = self.axis_direction / safe_norm(self.axis_direction)
        axial = safe_dot_product(local_point, axis)
        perpendicular = local_point - axis * axial
        return axial, safe_norm(perpendicular)

    def __repr__(self) -> str:
        return (f"Cylinder(axis={self.axis_direction.T}, "
                f"radius={self.radius}, "
                f"position={self.position.T}, "
                f"start={self.start_distance}, end={self.end_distance})")
    
    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is inside or on the boundary."""
        # Transform point to local coordinates
        local_point = point - self.position
        
        # Normalize axis
        axis = self.axis_direction / safe_norm(self.axis_direction)
        
        # Project onto axis to get axial coordinate
        axial_coord = safe_dot_product(local_point, axis)

        # Check axial bounds
        if self.start_distance is not None and safe_compare(axial_coord, self.start_distance, Comparison.LT, eps=eps):
            return False
        if self.end_distance is not None and safe_compare(axial_coord, self.end_distance, Comparison.GT, eps=eps):
            return False

        # Calculate radial distance from axis
        axial_projection = axis * axial_coord
        radial_vector = local_point - axial_projection
        radial_distance = safe_norm(radial_vector)

        # Check if within radius
        return safe_compare(radial_distance, self.radius, Comparison.LE, eps=eps)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on the barrel or a finite cap."""
        # First check if point is contained
        if not self.contains_point(point, eps=eps):
            return False
        
        # Transform point to local coordinates
        local_point = point - self.position
        
        # Normalize axis
        axis = self.axis_direction / safe_norm(self.axis_direction)
        
        # Project onto axis to get axial coordinate
        axial_coord = safe_dot_product(local_point, axis)
        
        # Calculate radial distance from axis
        axial_projection = axis * axial_coord
        radial_vector = local_point - axial_projection
        radial_distance = safe_norm(radial_vector)

        # On cylindrical surface
        if safe_equality_test(radial_distance, self.radius, eps=eps):
            return True

        # On end caps (if finite and at the end)
        if self.start_distance is not None and safe_equality_test(axial_coord, self.start_distance, eps=eps):
            return True
        if self.end_distance is not None and safe_equality_test(axial_coord, self.end_distance, eps=eps):
            return True

        return False
    
    def _each_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Iterator[Direction3D]:
        """Yield the outward normal of each surface `point` is on."""
        # Transform point to local coordinates
        local_point = point - self.position
        
        # Normalize axis
        axis = self.axis_direction / safe_norm(self.axis_direction)
        
        # Project onto axis to get axial coordinate
        axial_coord = safe_dot_product(local_point, axis)
        
        # Calculate radial distance from axis
        axial_projection = axis * axial_coord
        radial_vector = local_point - axial_projection
        radial_distance = safe_norm(radial_vector)

        # Check if on cylindrical surface first (most common case)
        if safe_equality_test(radial_distance, self.radius, eps=eps):
            # Normal is the radial direction (normalized)
            if safe_zero_test(radial_distance, eps=eps):
                # Point is on the axis, which shouldn't happen for the cylindrical surface
                # This might be an edge case on the cap center
                pass
            else:
                yield radial_vector / radial_distance

        # Check if on end caps
        if self.start_distance is not None and safe_equality_test(axial_coord, self.start_distance, eps=eps):
            # Bottom cap, normal points in -axis direction (outward)
            yield -axis
        if self.end_distance is not None and safe_equality_test(axial_coord, self.end_distance, eps=eps):
            # Top cap, normal points in +axis direction (outward)
            yield axis

        # Should not reach here if point is on boundary
        return

    # returns the first outward normal on the CSG, use get_outward_normals if that's insufficient.
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        return next(self._each_outward_normal(point, eps=eps), None)

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        return list(self._each_outward_normal(point, eps=eps))

    def get_aabb(self) -> AxisAlignedBoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite Cylinder — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return AxisAlignedBoundingBox(None, None, None, None, None, None)

        axis_norm = self.axis_direction / safe_norm(self.axis_direction)
        p1 = self.position + axis_norm * self.start_distance
        p2 = self.position + axis_norm * self.end_distance

        bounds = []
        for i in range(3):
            ai = axis_norm[i]
            radial_i = self.radius * sqrt(scalar(1) - ai * ai)
            lo = _numeric_min(p1[i], p2[i]) - radial_i
            hi = _numeric_max(p1[i], p2[i]) + radial_i
            bounds.append((lo, hi))

        return AxisAlignedBoundingBox(
            bounds[0][0], bounds[1][0], bounds[2][0],
            bounds[0][1], bounds[1][1], bounds[2][1],
        )


    def bounding_half_spaces(self) -> 'SolidBounds':
        """Return a circumscribing hexagon and the finite caps."""
        from .edges_on_csg import SolidBounds, _extrusion_caps
        axis = unit_vector(self.axis_direction)
        across, up = perpendicular_axes(axis)
        faces = []
        for step in range(6):
            angle = math.pi * step / 3
            normal = across * scalar(math.cos(angle)) + up * scalar(math.sin(angle))
            faces.append((normal, self.position + normal * self.radius))
        return SolidBounds.of(faces + _extrusion_caps(axis, self.position, self.start_distance, self.end_distance))

    def exact_line_spans(self, line: Line, seed: 'Span', tolerance: float, removing: bool) -> Optional[List['Span']]:
        from .edges_on_csg import _cylinder_spans
        return _cylinder_spans(self, line, seed, tolerance, removing)

    def angles_around_line(self, at, direction, basis, tolerance: float) -> Optional['AngleSpans']:
        from .edges_on_csg import _IN_PLANE_EPS, _angles_intersection, _extrusion_caps, _half_turn, _plane_angles
        axis = np.array([float(v) for v in unit_vector(self.axis_direction)])
        offset = at - np.array([float(self.position[i, 0]) for i in range(3)])
        radial = offset - axis * float(offset @ axis)
        distance = float(np.linalg.norm(radial)) - float(self.radius)
        if distance > tolerance + _IN_PLANE_EPS:
            return []
        caps = _extrusion_caps(unit_vector(self.axis_direction), self.position, self.start_distance, self.end_distance)
        angles = _plane_angles(caps, at, direction, basis, tolerance)
        if angles and distance >= -(tolerance + _IN_PLANE_EPS):
            across = radial - direction * float(radial @ direction)
            if float(np.linalg.norm(across)) > 1e-12:
                angles = _angles_intersection(angles, _half_turn(across, basis))
        return angles

    def line_crossings(self, origin, direction) -> List[float]:
        """Return where the line crosses the barrel and the finite caps."""
        from .edges_on_csg import _extrusion_caps, _plane_stations
        axis = np.array([float(v) for v in unit_vector(self.axis_direction)])
        start = origin - np.array([float(self.position[i, 0]) for i in range(3)])
        across, offset = direction - axis * float(direction @ axis), start - axis * float(start @ axis)
        a, b = float(across @ across), 2 * float(offset @ across)
        c = float(offset @ offset) - float(self.radius) ** 2
        found: List[float] = []
        if a > 1e-18 and b * b - 4 * a * c > 0:
            root = (b * b - 4 * a * c) ** 0.5
            found += [(-b - root) / (2 * a), (-b + root) / (2 * a)]
        caps = _extrusion_caps(unit_vector(self.axis_direction), self.position, self.start_distance, self.end_distance)
        return found + _plane_stations(caps, origin, direction)

    def plane_sides(self, frame, seed) -> 'Sides':
        from .cross_sections import _cylinder_cross_section
        return _cylinder_cross_section(self, frame, seed)


# TODO rename to PointOnCSGInfo
class SolidsAtPoint:
    """Caches contains_point and is_point_on_boundary of one point against several solids.

    Answers: any_holds, any_encloses, any_on_surface, outward_normals, average_outward_normal,
    close_around_it.
    """

    def __init__(
        self,
        solids: Sequence['CutCSG'],
        point: V3,
        eps: Optional[Numeric] = None,
    ) -> None:
        self.point = point
        self.eps = eps
        self.on_surface: List['CutCSG'] = []
        self.enclosing: List['CutCSG'] = []
        for solid in solids:
            if not solid.contains_point(point, eps=eps):
                continue
            if solid.is_point_on_boundary(point, eps=eps):
                self.on_surface.append(solid)
            else:
                self.enclosing.append(solid)
        self.holding = [*self.on_surface, *self.enclosing]

    def any_holds(self) -> bool:
        """Return whether any solid contains the point."""
        return bool(self.holding)

    def any_encloses(self) -> bool:
        """Return whether any solid has the point strictly inside."""
        return bool(self.enclosing)

    def any_on_surface(self) -> bool:
        return bool(self.on_surface)

    def outward_normals(self) -> List[Optional[Direction3D]]:
        """Return each on-surface solid's outward normal at the point."""
        return [solid.get_outward_normal(self.point, eps=self.eps)
                for solid in self.on_surface]

    def every_outward_normal(self) -> Optional[List[Direction3D]]:
        """Return each face normal of the single solid the point is on the surface of; None if several or none."""
        if len(self.on_surface) != 1:
            return None
        return self.on_surface[0].get_outward_normals(self.point, eps=self.eps)

    def average_outward_normal(self, negated: bool = False) -> Optional[Direction3D]:
        """Return the mean outward normal (negated if `negated`), or None if they cancel or are unknown."""
        normals = [normal for normal in self.outward_normals() if normal is not None]
        if negated:
            normals = [-normal for normal in normals]
        if not normals:
            return None
        if len(normals) == 1:
            return normals[0]
        total = sum(normals[1:], normals[0])
        size = safe_norm(total)
        if safe_zero_test(size, eps=self.eps):
            return None
        return total / size

    def close_around_it(self) -> bool:
        """Return whether the surfaces at the point enclose it, so it is inside their union.

        E.g. a point on the shared face of two touching prisms. True when no direction leaves every
        surface. Exact for one or two surfaces; False if any normal is unknown.
        """
        normals = [normal for normal in self.outward_normals() if normal is not None]
        if len(normals) < 2 or len(normals) != len(self.on_surface):
            return False

        units = [safe_normalize_vector(normal) for normal in normals]
        candidates = [sum(units[1:], units[0])]
        candidates.extend(units)
        candidates.extend(one + other
                          for index, one in enumerate(units)
                          for other in units[index + 1:])
        for candidate in candidates:
            size = safe_norm(candidate)
            if safe_zero_test(size):
                continue
            direction = candidate / size
            if all(safe_compare(safe_dot_product(direction, unit), 0, Comparison.GT)
                   for unit in units):
                return False
        return True


def assert_distinct_children(kind: str, children: Sequence[CutCSG]) -> None:
    """Raise if the same CSG object appears twice among `children`."""
    seen = set()
    for child in children:
        assert id(child) not in seen, (
            f"{kind} was given the same {type(child).__name__} object twice. The same "
            f"node reachable by two paths is not two operations -- build a copy for the "
            f"second use.")
        seen.add(id(child))


@dataclass(frozen=True)
class SolidUnion(CutCSG):
    """Union of `children`: points in any child."""

    @classmethod
    def display_name(cls) -> str:
        return "union"
    children: List[CutCSG]

    def __post_init__(self) -> None:
        assert_distinct_children("SolidUnion", self.children)

    def __repr__(self) -> str:
        return f"SolidUnion({len(self.children)} children)"
    
    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return {}

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether any child contains `point`."""
        return any(child.contains_point(point, eps=eps) for child in self.children)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on some child's boundary and not enclosed by the union."""
        at = SolidsAtPoint(self.children, point, eps=eps)
        if not at.any_holds() or at.any_encloses():
            return False
        # Two children can share a face with neither holding the point inside,
        # and that face is the middle of the union rather than its surface.
        return at.any_on_surface() and not at.close_around_it()
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """Return the average outward normal of the children `point` is on the boundary of, or None."""
        return SolidsAtPoint(self.children, point, eps=eps).average_outward_normal()

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        own = SolidsAtPoint(self.children, point, eps=eps).every_outward_normal()
        return own if own is not None else super().get_outward_normals(point, eps=eps)

    def get_aabb(self) -> AxisAlignedBoundingBox:
        # Empty children contribute no points to the union, so they're excluded
        # before combining bounds — otherwise their degenerate zero-box would
        # incorrectly pull the union's bounds toward the origin.
        bboxes = [b for b in (child.get_aabb() for child in self.children) if not b.is_empty]
        if not bboxes:
            return AxisAlignedBoundingBox(None, None, None, None, None, None, is_empty=True)

        def union_min(vals):
            if any(v is None for v in vals):
                return None
            return _numeric_min(*vals)

        def union_max(vals):
            if any(v is None for v in vals):
                return None
            return _numeric_max(*vals)

        return AxisAlignedBoundingBox(
            union_min([b.min_x for b in bboxes]),
            union_min([b.min_y for b in bboxes]),
            union_min([b.min_z for b in bboxes]),
            union_max([b.max_x for b in bboxes]),
            union_max([b.max_y for b in bboxes]),
            union_max([b.max_z for b in bboxes]),
        )


@dataclass(frozen=True)
class Intersection(CutCSG):
    """Intersection of `left` and `right`: points in both."""
    left: CutCSG
    right: CutCSG

    def __post_init__(self) -> None:
        assert_distinct_children("Intersection", (self.left, self.right))

    def __repr__(self) -> str:
        return f"Intersection(left={self.left}, right={self.right})"

    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return {}

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        return self.left.contains_point(point, eps=eps) and self.right.contains_point(point, eps=eps)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        # Boundary of intersection = points in both solids that are on either boundary.
        if not self.contains_point(point, eps=eps):
            return False
        return self.left.is_point_on_boundary(point, eps=eps) or self.right.is_point_on_boundary(point, eps=eps)

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """Return the outward normal at `point`, averaged where both sides' surfaces meet."""
        at = SolidsAtPoint([self.left, self.right], point, eps=eps)
        average = at.average_outward_normal()
        if average is not None:
            return average
        # Two surfaces facing opposite ways average to nothing. Either one
        # describes the corner as well as the other, so take the first.
        for normal in at.outward_normals():
            if normal is not None:
                return normal
        return None

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        own = SolidsAtPoint([self.left, self.right], point, eps=eps).every_outward_normal()
        return own if own is not None else super().get_outward_normals(point, eps=eps)

    def get_aabb(self) -> AxisAlignedBoundingBox:
        left_bbox = self.left.get_aabb()
        right_bbox = self.right.get_aabb()

        # If either side is empty, their intersection has no points either.
        if left_bbox.is_empty or right_bbox.is_empty:
            return AxisAlignedBoundingBox(None, None, None, None, None, None, is_empty=True)

        def intersect_min(a: Optional[Numeric], b: Optional[Numeric]) -> Optional[Numeric]:
            if a is None:
                return b
            if b is None:
                return a
            return _numeric_max(a, b)

        def intersect_max(a: Optional[Numeric], b: Optional[Numeric]) -> Optional[Numeric]:
            if a is None:
                return b
            if b is None:
                return a
            return _numeric_min(a, b)

        return AxisAlignedBoundingBox(
            intersect_min(left_bbox.min_x, right_bbox.min_x),
            intersect_min(left_bbox.min_y, right_bbox.min_y),
            intersect_min(left_bbox.min_z, right_bbox.min_z),
            intersect_max(left_bbox.max_x, right_bbox.max_x),
            intersect_max(left_bbox.max_y, right_bbox.max_y),
            intersect_max(left_bbox.max_z, right_bbox.max_z),
        )


@dataclass(frozen=True)
class Difference(CutCSG):
    """`base` minus every solid in `subtract`."""
    base: CutCSG
    subtract: List[CutCSG]

    def __post_init__(self) -> None:
        assert_distinct_children("Difference", self.subtract)

    def __repr__(self) -> str:
        return f"Difference(base={self.base}, subtract={len(self.subtract)} objects)"
    
    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return {}

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is in `base` and not strictly inside any subtracted solid (nor on a flush cut)."""
        if not self.base.contains_point(point, eps=eps):
            return False

        removed = SolidsAtPoint(self.subtract, point, eps=eps)
        if removed.any_encloses():
            return False
        # Several subtracts can close around a point none of them holds inside
        # -- two mortises meeting share a face in the middle of one cavity.
        if removed.close_around_it():
            return False
        if not removed.any_on_surface():
            return True
        if not self.base.is_point_on_boundary(point, eps=eps):
            return True
        return not self._cut_is_flush_with_the_base(removed, point, eps=eps)

    def _cut_is_flush_with_the_base(
        self, removed: 'SolidsAtPoint', point: V3, eps: Optional[Numeric] = None,
    ) -> bool:
        """Return whether a subtracted solid's surface at `point` lies along the base's, facing the same way. True if a normal is unknown."""
        # Flush only where every face the cut has at the point lies along one
        # of the base's: at the cut's edge, that needs the base to turn the same
        # corner there.
        #
        # NOTE only exact for planar surfaces, not curved surfaces.
        base_normals = self.base.get_outward_normals(point, eps=eps)
        if not base_normals:
            return True
        for solid in removed.on_surface:
            sub_normals = solid.get_outward_normals(point, eps=eps)
            if not sub_normals:
                return True
            if all(any(safe_equality_test(safe_dot_product(base_normal, sub_normal), 1, eps=eps)
                       for base_normal in base_normals)
                   for sub_normal in sub_normals):
                return True
        return False

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is in the difference and on the base's surface or a cut's wall."""
        if not self.contains_point(point, eps=eps):
            return False
        if self.base.is_point_on_boundary(point, eps=eps):
            return True
        return SolidsAtPoint(self.subtract, point, eps=eps).any_on_surface()

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """Return the base's normal at `point`, else the average negated normal of the cuts there; None if unknown."""
        # If point is on base boundary, return base's normal
        if self.base.is_point_on_boundary(point, eps=eps):
            return self.base.get_outward_normal(point, eps=eps)
        
        # Otherwise, point must be on subtract boundary (creating a "hole")
        # The normal should point inward to the subtract (which is outward from the difference)
        # So we negate the subtract's outward normal
        return SolidsAtPoint(self.subtract, point, eps=eps).average_outward_normal(negated=True)

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        """Return the base's normals at `point`, plus the negated normals of cuts through it not parallel to one."""
        if not self.base.is_point_on_boundary(point, eps=eps):
            return super().get_outward_normals(point, eps=eps)
        base_normals = list(self.base.get_outward_normals(point, eps=eps))
        normals = list(base_normals)
        for solid in SolidsAtPoint(self.subtract, point, eps=eps).on_surface:
            for normal in solid.get_outward_normals(point, eps=eps):
                along_base = any(
                    safe_equality_test(safe_dot_product(base_normal, normal), 1, eps=eps)
                    or safe_equality_test(safe_dot_product(base_normal, normal), -1, eps=eps)
                    for base_normal in base_normals)
                if not along_base:
                    normals.append(-normal)
        return normals

    def get_aabb(self) -> AxisAlignedBoundingBox:
        bbox = self.base.get_aabb()
        if bbox.is_empty:
            return bbox
        for sub in self.subtract:
            if isinstance(sub, HalfSpace):
                bbox = _clip_bbox_by_halfspace_complement(bbox, sub)
        return bbox

# TODO come up with a cuter/better name for these
Profile = List[V2]
Profiles = List[Profile]

def translate_profile(profile: Profile, translation: V2) -> Profile:
    """Return `profile` translated by `translation`."""
    return [point + translation for point in profile]

def translate_profiles(profiles: Profiles, translation: V2) -> Profiles:
    """Return each profile translated by `translation`."""
    return [translate_profile(profile, translation) for profile in profiles]


def point_in_convex_profile(points: Sequence[V2], point_2d: V2, eps: Optional[Numeric] = None) -> bool:
    """Return whether a 2D point is inside a convex profile, wound either way."""
    signed_area = 0.0
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        signed_area += (float(current[0]) * float(following[1])
                        - float(following[0]) * float(current[1]))
    inside_is_positive = signed_area >= 0

    for index, p1 in enumerate(points):
        p2 = points[(index + 1) % len(points)]
        edge = p2 - p1
        to_point = point_2d - p1
        # Divided by the edge's length, giving the point's distance from the edge.
        edge_length = safe_norm(Matrix([edge[0], edge[1]]))
        if safe_zero_test(edge_length):
            continue
        distance = (edge[0] * to_point[1] - edge[1] * to_point[0]) / edge_length
        wrong_side = Comparison.GT if not inside_is_positive else Comparison.LT
        if safe_compare(distance, 0, wrong_side, eps=eps):
            return False
    return True


@dataclass(frozen=True)
class ConvexPolygonExtrusion(HasFeatures, CutCSG):
    """A convex polygon in the local XY plane extruded along local Z, optionally infinite at either end.

    Args:
        points: the polygon's (x, y) points in order; must be convex.
        transform: the polygon's position and orientation.
        start_distance, end_distance: extent along local Z; None for infinite.
    """

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Return its two caps, a side per profile edge, and their edges."""
        features: Dict[FeatureKey, CSGFeature] = {}
        for key, cap in ((START_CAP, ExtrusionCap.BOTTOM), (END_CAP, ExtrusionCap.TOP)):
            features[key] = SimpleConvexPolygonExtrusionFeature(
                name=default_feature_name(key), key=cap,
                properties=_DEFAULT_FEATURE_PROPERTIES)
        for index in range(len(self.points)):
            key = (FeatureCategory.SIDE, index)
            features[key] = SimpleConvexPolygonExtrusionFeature(
                name=default_feature_name(key), key=index,
                properties=_DEFAULT_FEATURE_PROPERTIES)
        features.update(convex_profile_edge_features(len(self.points)))
        return features

    @classmethod
    def display_name(cls) -> str:
        return "extrusion"
    points: Profile
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None  # starting distance in the direction of the -Z axis. None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # ending distance in the direction of the +Z axis. None means infinite in positive direction

    # Features this primitive names on its own boundary. Private: read it
    def get_bottom_position(self) -> V3:
        """Return the profile origin at `start_distance`. Raises ValueError if infinite."""
        if self.start_distance is None:
            raise ValueError("Cannot get bottom position of infinite extrusion (start_distance is None)")
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.start_distance]))
    
    def get_top_position(self) -> V3:
        """Return the profile origin at `end_distance`. Raises ValueError if infinite."""
        if self.end_distance is None:
            raise ValueError("Cannot get top position of infinite extrusion (end_distance is None)")
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.end_distance]))

    def __repr__(self) -> str:
        return (f"ConvexPolygonExtrusion({len(self.points)} points, "
                f"transform={self.transform}, start={self.start_distance}, end={self.end_distance})")
    
    def is_valid(self) -> bool:
        """Return whether it has at least 3 points, a convex polygon, and end > start when both are finite."""
        if len(self.points) < 3:
            return False
        
        # Check distance configuration
        if self.start_distance is not None and self.end_distance is not None:
            if safe_compare(self.end_distance, self.start_distance, Comparison.LE):
                return False

        # Check convexity: all cross products of consecutive edges should have the same sign
        # For a convex polygon, as we traverse the vertices, we should always turn the same way
        n = len(self.points)

        # Compute 2D cross product for each triplet of consecutive points
        def cross_product(i):
            p0, p1, p2 = self.points[i], self.points[(i + 1) % n], self.points[(i + 2) % n]
            edge1, edge2 = p1 - p0, p2 - p1
            return edge1[0] * edge2[1] - edge1[1] * edge2[0]

        # Generate all cross products and filter out zeros (collinear points)
        cross_products = [cross_product(i) for i in range(n)]
        non_zero_crosses = [cp for cp in cross_products if not safe_zero_test(cp)]

        # Reject if all collinear, otherwise check all turns go the same direction
        return (len(non_zero_crosses) > 0 and
                (all(safe_compare(cp, 0, Comparison.GT) for cp in non_zero_crosses) or
                 all(safe_compare(cp, 0, Comparison.LT) for cp in non_zero_crosses)))

    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return face_plane_carriers(self)

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is inside or on the boundary."""
        # Transform point to local coordinates
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        
        x_coord = local_coords[0]
        y_coord = local_coords[1]
        z_coord = local_coords[2]
        
        # Check Z bounds (use safe_compare for tolerance with Float vs Integer)
        if self.start_distance is not None and safe_compare(z_coord - self.start_distance, 0, Comparison.LT, eps=eps):
            return False
        if self.end_distance is not None and safe_compare(z_coord - self.end_distance, 0, Comparison.GT, eps=eps):
            return False
        
        # Check if (x_coord, y_coord) is inside the convex polygon, whichever way the
        # profile is wound -- see point_in_convex_profile.
        return point_in_convex_profile(self.points, Matrix([x_coord, y_coord]), eps)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on a cap or a side."""
        # First check if point is contained
        if not self.contains_point(point, eps=eps):
            return False
        
        # Transform point to local coordinates
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        
        x_coord = local_coords[0]
        y_coord = local_coords[1]
        z_coord = local_coords[2]
        
        # Check if on top or bottom face (if finite)
        if self.start_distance is not None and safe_zero_test(z_coord - self.start_distance, eps=eps):
            return True
        if self.end_distance is not None and safe_zero_test(z_coord - self.end_distance, eps=eps):
            return True
        
        # Check if on a vertical edge (point is at a vertex XY coordinate)
        point_2d = Matrix([x_coord, y_coord])
        for vertex_2d in self.points:
            distance_sq = (point_2d[0] - vertex_2d[0])**2 + (point_2d[1] - vertex_2d[1])**2
            if safe_zero_test_sq(distance_sq, eps):
                return True  # Point is on a vertical edge
        
        # Check if on any horizontal edge of the polygon (side face at this z)
        for i in range(len(self.points)):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % len(self.points)]
            
            # Check if point is on the line segment from p1 to p2
            # Use parametric form: p = p1 + t*(p2-p1), where 0 <= t <= 1
            edge = p2 - p1
            to_point = point_2d - p1
            
            # If edge is zero-length, skip it
            edge_length_sq = edge[0]**2 + edge[1]**2
            # Degeneracy is a property of the polygon, not of how close the
            # caller clicked, so this takes no query tolerance.
            if safe_zero_test_sq(edge_length_sq):
                continue
            
            # Project to_point onto edge
            t = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq
            
            # Check if projection is on the segment [0, 1]
            t_in_range = safe_compare(t, 0, Comparison.GE, eps=eps) and safe_compare(t - scalar(1), 0, Comparison.LE, eps=eps)
            
            if t_in_range:
                closest_point = p1 + edge * t
                distance_sq = (point_2d[0] - closest_point[0])**2 + (point_2d[1] - closest_point[1])**2
                if safe_zero_test_sq(distance_sq, eps):
                    return True
        
        return False
    
    def _each_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Iterator[Direction3D]:
        """Yield the outward normal of each surface `point` is on."""
        # Transform point to local coordinates
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        
        x_coord = local_coords[0]
        y_coord = local_coords[1]
        z_coord = local_coords[2]
        
        # Check if on top face
        if self.end_distance is not None and safe_equality_test(z_coord, self.end_distance, eps=eps):
            # Top face, normal points in +Z direction in local coords
            local_normal = Matrix([scalar(0), scalar(0), scalar(1)])
            yield safe_transform_vector(self.transform.orientation.matrix, local_normal)

        # Check if on bottom face
        if self.start_distance is not None and safe_equality_test(z_coord, self.start_distance, eps=eps):
            # Bottom face, normal points in -Z direction in local coords
            local_normal = Matrix([scalar(0), scalar(0), scalar(-1)])
            yield safe_transform_vector(self.transform.orientation.matrix, local_normal)

        # Otherwise, point is on a side face (edge of polygon extruded)
        # Find which edge it's on and compute the normal
        point_2d = Matrix([x_coord, y_coord])

        for i in range(len(self.points)):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % len(self.points)]

            # Check if point is on the line segment from p1 to p2
            edge = p2 - p1
            to_point = point_2d - p1

            edge_length_sq = edge[0]**2 + edge[1]**2
            # Degeneracy is a property of the polygon, not of how close the
            # caller clicked, so this takes no query tolerance.
            if safe_zero_test_sq(edge_length_sq):
                continue

            t = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq

            if safe_compare(t, 0, Comparison.GE, eps=eps) and safe_compare(t, 1, Comparison.LE, eps=eps):
                closest_point = p1 + edge * t
                distance_sq = (point_2d[0] - closest_point[0])**2 + (point_2d[1] - closest_point[1])**2
                if safe_zero_test_sq(distance_sq, eps):
                    # Point is on this edge
                    # Normal is perpendicular to edge (in 2D), pointing outward
                    # Left perpendicular of (dx, dy) is (-dy, dx)
                    edge_normal_2d = Matrix([-edge[1], edge[0]])
                    edge_normal_2d = edge_normal_2d / sqrt(edge_normal_2d[0]**2 + edge_normal_2d[1]**2)

                    # Check if this normal points outward (away from polygon center)
                    # Calculate polygon center
                    center_x = sum(p[0] for p in self.points) / len(self.points)
                    center_y = sum(p[1] for p in self.points) / len(self.points)
                    center = Matrix([center_x, center_y])

                    # Vector from center to point on edge
                    to_edge = closest_point - center

                    # If dot product is negative, flip the normal
                    if safe_compare(edge_normal_2d[0] * to_edge[0] + edge_normal_2d[1] * to_edge[1], 0, Comparison.LT, eps=eps):
                        edge_normal_2d = -edge_normal_2d

                    # Convert to 3D local normal (no Z component for side faces)
                    local_normal = Matrix([edge_normal_2d[0], edge_normal_2d[1], 0])

                    # Transform to global coordinates
                    yield safe_transform_vector(self.transform.orientation.matrix, local_normal)

        return

    # returns the first outward normal on the CSG, use get_outward_normals if that's insufficient.
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        return next(self._each_outward_normal(point, eps=eps), None)

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        return list(self._each_outward_normal(point, eps=eps))

    def _local_coords(self, point: V3) -> Tuple[Numeric, Numeric, Numeric]:
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        return local_coords[0], local_coords[1], local_coords[2]

    def _point_on_side(self, index: int, x: Numeric, y: Numeric, eps: Optional[Numeric] = None) -> bool:
        """Return whether local (x, y) lies on side `index` (points[index] to points[index + 1])."""
        p1 = self.points[index]
        p2 = self.points[(index + 1) % len(self.points)]
        edge = p2 - p1
        to_point = Matrix([x, y]) - p1
        edge_length_sq = edge[0] ** 2 + edge[1] ** 2
        # Degeneracy is a property of the polygon, not of how close the
        # caller clicked, so this takes no query tolerance.
        if safe_zero_test_sq(edge_length_sq):
            return False
        t = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq
        if not (safe_compare(t, 0, Comparison.GE, eps=eps) and safe_compare(t, 1, Comparison.LE, eps=eps)):
            return False
        closest_point = p1 + edge * t
        distance_sq = (x - closest_point[0]) ** 2 + (y - closest_point[1]) ** 2
        return safe_zero_test_sq(distance_sq, eps)

    def get_aabb(self) -> AxisAlignedBoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite ConvexPolygonExtrusion — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return AxisAlignedBoundingBox(None, None, None, None, None, None)

        corners_global = [
            self.transform.local_to_global(Matrix([pt[0], pt[1], z]))
            for pt in self.points
            for z in (self.start_distance, self.end_distance)
        ]

        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]
        return AxisAlignedBoundingBox(
            _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
            _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
        )


    def bounding_half_spaces(self) -> 'SolidBounds':
        from .edges_on_csg import _bounds_or_unknown, _extruded_hull_half_spaces
        return _bounds_or_unknown(_extruded_hull_half_spaces(
            [(float(x), float(y)) for x, y in self.points], self.transform, self.start_distance, self.end_distance))

    def is_exactly_its_bounds(self) -> bool:
        return True


#: How far out of plane a loft's side may sit before it counts as twisted, as a
#: fraction of that side's own size. Generous: it is separating a pure taper,
#: which is flat to float precision, from a rotation, which is off by tenths.
_SIDE_PLANARITY_EPSILON = scalar('1e-6')


@dataclass(frozen=True)
class ConvexPolygonSimpleLoft(HasFeatures, CutCSG):
    """A solid lofted between two convex polygons in parallel planes, vertex i to vertex i.

    Both profiles must be convex, with the same point count and winding, and every side planar (no
    twist; see is_valid). Profiles lie in the local XY plane at `bottom_points_z_pos` and
    `top_points_z_pos` along local Z; both must be finite.
    """

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Return its two caps, a side per profile edge, and their edges."""
        features: Dict[FeatureKey, CSGFeature] = {}
        for key, cap in ((START_CAP, ExtrusionCap.BOTTOM), (END_CAP, ExtrusionCap.TOP)):
            features[key] = SimpleLoftFeature(
                name=default_feature_name(key), key=cap,
                properties=_DEFAULT_FEATURE_PROPERTIES)
        for index in range(len(self.bottom_points)):
            key = (FeatureCategory.SIDE, index)
            features[key] = SimpleLoftFeature(
                name=default_feature_name(key), key=index,
                properties=_DEFAULT_FEATURE_PROPERTIES)
        features.update(convex_profile_edge_features(len(self.bottom_points)))
        return features

    @classmethod
    def display_name(cls) -> str:
        return "loft"

    bottom_points: Profile
    top_points: Profile

    bottom_points_z_pos: Numeric
    top_points_z_pos: Numeric

    transform: Transform = field(default_factory=Transform.identity)

    # Features this primitive names on its own boundary. Private: read it
    def get_bottom_position(self) -> V3:
        """Return the profile origin at `bottom_points_z_pos`."""
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.bottom_points_z_pos]))

    def get_top_position(self) -> V3:
        """Return the profile origin at `top_points_z_pos`."""
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.top_points_z_pos]))

    def __repr__(self) -> str:
        return (f"ConvexPolygonSimpleLoft({len(self.bottom_points)}->{len(self.top_points)} points, "
                f"transform={self.transform}, start={self.bottom_points_z_pos}, end={self.top_points_z_pos})")

    def is_valid(self) -> bool:
        """Return whether both profiles are convex with 3+ matching points, top is above bottom, and every side is planar."""
        if len(self.bottom_points) < 3 or len(self.top_points) < 3:
            return False
        if len(self.bottom_points) != len(self.top_points):
            return False
        if safe_compare(self.top_points_z_pos, self.bottom_points_z_pos, Comparison.LE):
            return False

        def winding_sign(points: Profile) -> Optional[int]:
            """+1 for CCW-convex, -1 for CW-convex, None if not convex."""
            n = len(points)

            def cross_product_2d(i):
                p0, p1, p2 = points[i], points[(i + 1) % n], points[(i + 2) % n]
                edge1, edge2 = p1 - p0, p2 - p1
                return edge1[0] * edge2[1] - edge1[1] * edge2[0]

            cross_products = [cross_product_2d(i) for i in range(n)]
            non_zero_crosses = [cp for cp in cross_products if not safe_zero_test(cp)]
            if not non_zero_crosses:
                return None
            if all(safe_compare(cp, 0, Comparison.GT) for cp in non_zero_crosses):
                return 1
            if all(safe_compare(cp, 0, Comparison.LT) for cp in non_zero_crosses):
                return -1
            return None

        bottom_winding = winding_sign(self.bottom_points)
        top_winding = winding_sign(self.top_points)
        # Both must be individually convex AND wound the same direction -- the
        # index-to-index correspondence between bottom_points and top_points only
        # means what it's documented to mean (a straight-line loft) if they agree.
        if bottom_winding is None or bottom_winding != top_winding:
            return False
        return self._sides_are_planar()

    def _sides_are_planar(self) -> bool:
        """Return whether every side quad's four corners are coplanar."""
        bottom, top = self.bottom_points, self.top_points
        count = len(bottom)
        low, high = self.bottom_points_z_pos, self.top_points_z_pos
        for index in range(count):
            following = (index + 1) % count
            corners = [
                create_v3(bottom[index][0], bottom[index][1], low),
                create_v3(bottom[following][0], bottom[following][1], low),
                create_v3(top[following][0], top[following][1], high),
                create_v3(top[index][0], top[index][1], high),
            ]
            spanning = cross_product(corners[1] - corners[0], corners[3] - corners[0])
            reach = giraffe_norm(spanning)
            if safe_zero_test(reach):
                # Three of the four corners are in line, so there is no plane to
                # be off. A degenerate side, not a twisted one.
                continue
            away = safe_dot_product(spanning / reach, corners[2] - corners[0])
            size = max(giraffe_norm(corners[1] - corners[0]),
                       giraffe_norm(corners[3] - corners[0]))
            if safe_zero_test(size):
                continue
            if not safe_zero_test(away / size, eps=_SIDE_PLANARITY_EPSILON):
                return False
        return True

    def _local_coords(self, point: V3) -> Tuple[Numeric, Numeric, Numeric]:
        """Return a global point in the loft's local (x, y, z)."""
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        return local_coords[0], local_coords[1], local_coords[2]

    def _height_fraction(self, z_coord: Numeric) -> Numeric:
        """Return the fraction along the loft (0 at bottom, 1 at top) of local `z`."""
        return (z_coord - self.bottom_points_z_pos) / (self.top_points_z_pos - self.bottom_points_z_pos)

    def _cross_section_at(self, t: Numeric) -> Profile:
        """Return the interpolated profile at height fraction `t`."""
        return [bottom + (top - bottom) * t for bottom, top in zip(self.bottom_points, self.top_points)]

    def _point_on_side(self, index: int, x: Numeric, y: Numeric, z: Numeric,
                       eps: Optional[Numeric] = None) -> bool:
        """Return whether local (x, y, z) lies on side `index`, tested against the cross-section at its height."""
        cross_section = self._cross_section_at(self._height_fraction(z))
        p1 = cross_section[index]
        p2 = cross_section[(index + 1) % len(cross_section)]
        edge = p2 - p1
        to_point = Matrix([x, y]) - p1
        edge_length_sq = edge[0] ** 2 + edge[1] ** 2
        # Degeneracy is a property of the polygon, not of how close the
        # caller clicked, so this takes no query tolerance.
        if safe_zero_test_sq(edge_length_sq):
            return False
        t = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq
        if not (safe_compare(t, 0, Comparison.GE, eps=eps) and safe_compare(t, 1, Comparison.LE, eps=eps)):
            return False
        closest_point = p1 + edge * t
        distance_sq = (x - closest_point[0]) ** 2 + (y - closest_point[1]) ** 2
        return safe_zero_test_sq(distance_sq, eps)

    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return face_plane_carriers(self)

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is inside or on the boundary."""
        x_coord, y_coord, z_coord = self._local_coords(point)

        if safe_compare(z_coord - self.bottom_points_z_pos, 0, Comparison.LT, eps=eps):
            return False
        if safe_compare(z_coord - self.top_points_z_pos, 0, Comparison.GT, eps=eps):
            return False

        cross_section = self._cross_section_at(self._height_fraction(z_coord))

        return point_in_convex_profile(cross_section, Matrix([x_coord, y_coord]), eps)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """Return whether `point` is on the boundary."""
        if not self.contains_point(point, eps=eps):
            return False

        x_coord, y_coord, z_coord = self._local_coords(point)

        if safe_zero_test(z_coord - self.bottom_points_z_pos, eps=eps):
            return True
        if safe_zero_test(z_coord - self.top_points_z_pos, eps=eps):
            return True

        cross_section = self._cross_section_at(self._height_fraction(z_coord))
        point_2d = Matrix([x_coord, y_coord])

        # On a lofted vertex (the straight line connecting a bottom vertex to its
        # matching top vertex, evaluated at this height)
        for vertex_2d in cross_section:
            distance_sq = (point_2d[0] - vertex_2d[0]) ** 2 + (point_2d[1] - vertex_2d[1]) ** 2
            if safe_zero_test_sq(distance_sq, eps):
                return True

        # On a side face at this height
        for i in range(len(cross_section)):
            p1 = cross_section[i]
            p2 = cross_section[(i + 1) % len(cross_section)]
            edge = p2 - p1
            to_point = point_2d - p1

            edge_length_sq = edge[0] ** 2 + edge[1] ** 2
            # Degeneracy is a property of the polygon, not of how close the
            # caller clicked, so this takes no query tolerance.
            if safe_zero_test_sq(edge_length_sq):
                continue

            u = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq
            u_in_range = safe_compare(u, 0, Comparison.GE, eps=eps) and safe_compare(u - scalar(1), 0, Comparison.LE, eps=eps)

            if u_in_range:
                closest_point = p1 + edge * u
                distance_sq = (point_2d[0] - closest_point[0]) ** 2 + (point_2d[1] - closest_point[1]) ** 2
                if safe_zero_test_sq(distance_sq, eps):
                    return True

        return False

    def _each_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Iterator[Direction3D]:
        """Yield the outward normal of a face `point` is on (one adjacent face's at an edge or vertex)."""
        x_coord, y_coord, z_coord = self._local_coords(point)

        if safe_zero_test(z_coord - self.top_points_z_pos, eps=eps):
            local_normal = Matrix([scalar(0), scalar(0), scalar(1)])
            yield safe_transform_vector(self.transform.orientation.matrix, local_normal)

        if safe_zero_test(z_coord - self.bottom_points_z_pos, eps=eps):
            local_normal = Matrix([scalar(0), scalar(0), scalar(-1)])
            yield safe_transform_vector(self.transform.orientation.matrix, local_normal)

        t_height = self._height_fraction(z_coord)
        cross_section = self._cross_section_at(t_height)
        point_2d = Matrix([x_coord, y_coord])
        n = len(cross_section)

        for i in range(n):
            p1 = cross_section[i]
            p2 = cross_section[(i + 1) % n]
            edge = p2 - p1
            to_point = point_2d - p1

            edge_length_sq = edge[0] ** 2 + edge[1] ** 2
            # Degeneracy is a property of the polygon, not of how close the
            # caller clicked, so this takes no query tolerance.
            if safe_zero_test_sq(edge_length_sq):
                continue

            u = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_length_sq
            if not (safe_compare(u, 0, Comparison.GE, eps=eps) and safe_compare(u, 1, Comparison.LE, eps=eps)):
                continue

            closest_point = p1 + edge * u
            distance_sq = (point_2d[0] - closest_point[0]) ** 2 + (point_2d[1] - closest_point[1]) ** 2
            if not safe_zero_test_sq(distance_sq, eps):
                continue

            # Point is on the side face spanning edge i. Parametrize the face by
            # (u, t): P(u, t) = lerp(bottom_i + u*(bottom_{i+1}-bottom_i),
            #                        top_i + u*(top_{i+1}-top_i), t)
            # and take dP/du x dP/dt as the (unnormalized, not-yet-oriented) normal.
            bottom_i, bottom_i1 = self.bottom_points[i], self.bottom_points[(i + 1) % n]
            top_i, top_i1 = self.top_points[i], self.top_points[(i + 1) % n]
            length = self.top_points_z_pos - self.bottom_points_z_pos

            d_edge = (scalar(1) - t_height) * (bottom_i1 - bottom_i) + t_height * (top_i1 - top_i)
            d_height_xy = (top_i - bottom_i) + u * ((top_i1 - top_i) - (bottom_i1 - bottom_i))

            d_edge_3d = Matrix([d_edge[0], d_edge[1], scalar(0)])
            d_height_3d = Matrix([d_height_xy[0], d_height_xy[1], length])
            local_normal = cross_product(d_edge_3d, d_height_3d)

            # Orient outward: flip if it doesn't point away from this height's
            # cross-section centroid (mirrors ConvexPolygonExtrusion's approach).
            center_x = sum(p[0] for p in cross_section) / n
            center_y = sum(p[1] for p in cross_section) / n
            to_edge = closest_point - Matrix([center_x, center_y])
            outward_dot = local_normal[0] * to_edge[0] + local_normal[1] * to_edge[1]
            if safe_compare(outward_dot, 0, Comparison.LT, eps=eps):
                local_normal = -local_normal

            yield safe_normalize_vector(safe_transform_vector(self.transform.orientation.matrix, local_normal))

        return

    # returns the first outward normal on the CSG, use get_outward_normals if that's insufficient.
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        return next(self._each_outward_normal(point, eps=eps), None)

    def get_outward_normals(self, point: V3, eps: Optional[Numeric] = None) -> List[Direction3D]:
        return list(self._each_outward_normal(point, eps=eps))

    def get_aabb(self) -> AxisAlignedBoundingBox:
        corners_global = (
            [self.transform.local_to_global(Matrix([pt[0], pt[1], self.bottom_points_z_pos])) for pt in self.bottom_points] +
            [self.transform.local_to_global(Matrix([pt[0], pt[1], self.top_points_z_pos])) for pt in self.top_points]
        )

        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]
        return AxisAlignedBoundingBox(
            _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
            _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
        )


    def bounding_half_spaces(self) -> 'SolidBounds':
        from .edges_on_csg import _bounds_or_unknown, _loft_half_spaces
        return _bounds_or_unknown(_loft_half_spaces(self))

    def is_exactly_its_bounds(self) -> bool:
        from .edges_on_csg import _loft_sides_are_planar
        return _loft_sides_are_planar(self)

    def plane_sides(self, frame, seed) -> 'Sides':
        from .cross_sections import _CannotCrossSection
        if not self.is_exactly_its_bounds():
            raise _CannotCrossSection("a loft with twisted sides")
        return super().plane_sides(frame, seed)


# ============================================================================
# Polygon decomposition utility
# ============================================================================

def decompose_simple_polygon_into_convex_pieces(points: Profile) -> List[Profile]:
    """Split a simple polygon of (u, v) points into convex quads and triangles, by horizontal bands.

    Within each band between vertex v's, the active edges' crossings are paired left to right
    (even-odd). pathcsg.decompose_path_into_convex_pieces is the same sweep over a FancyPath.
    """
    n = len(points)
    edges: List[Tuple[Numeric, Numeric, Numeric, Numeric]] = []  # (v_lo, v_hi, u_at_v_lo, u_at_v_hi)
    for i in range(n):
        a = points[i]
        b = points[(i + 1) % n]
        if safe_zero_test(a[1] - b[1]):
            continue  # horizontal edge: no v-crossings, doesn't bound any band
        if safe_compare(a[1], b[1], Comparison.LT):
            edges.append((a[1], b[1], a[0], b[0]))
        else:
            edges.append((b[1], a[1], b[0], a[0]))

    breakpoints: List[Numeric] = sorted((p[1] for p in points), key=giraffe_evalf)
    deduped_breakpoints: List[Numeric] = []
    for v in breakpoints:
        if not deduped_breakpoints or not safe_zero_test(v - deduped_breakpoints[-1]):
            deduped_breakpoints.append(v)

    pieces: List[Profile] = []
    for i in range(len(deduped_breakpoints) - 1):
        v_lo, v_hi = deduped_breakpoints[i], deduped_breakpoints[i + 1]
        v_mid = (v_lo + v_hi) / scalar(2)

        crossings = []  # (u_at_v_mid, u_at_v_lo, u_at_v_hi)
        for (e_v_lo, e_v_hi, e_u_lo, e_u_hi) in edges:
            if safe_compare(e_v_lo, v_mid, Comparison.LE) and safe_compare(v_mid, e_v_hi, Comparison.LE):
                t_lo = (v_lo - e_v_lo) / (e_v_hi - e_v_lo)
                t_hi = (v_hi - e_v_lo) / (e_v_hi - e_v_lo)
                t_mid = (v_mid - e_v_lo) / (e_v_hi - e_v_lo)
                u_lo = e_u_lo + t_lo * (e_u_hi - e_u_lo)
                u_hi = e_u_lo + t_hi * (e_u_hi - e_u_lo)
                u_mid = e_u_lo + t_mid * (e_u_hi - e_u_lo)
                crossings.append((u_mid, u_lo, u_hi))
        crossings.sort(key=lambda c: giraffe_evalf(c[0]))

        if len(crossings) % 2 != 0:
            raise ValueError("profile polygon is not simple: odd number of boundary crossings in a v-band")

        for j in range(0, len(crossings) - 1, 2):
            _, u_left_lo, u_left_hi = crossings[j]
            _, u_right_lo, u_right_hi = crossings[j + 1]
            # A degenerate (zero-area, e.g. two edges retracing the same line)
            # pair — both corners coincide at both v_lo and v_hi — contributes
            # nothing and isn't a valid convex polygon; skip it.
            if safe_zero_test(u_right_lo - u_left_lo) and safe_zero_test(u_right_hi - u_left_hi):
                continue
            pieces.append([
                create_v2(u_left_lo, v_lo), create_v2(u_right_lo, v_lo),
                create_v2(u_right_hi, v_hi), create_v2(u_left_hi, v_hi),
            ])

    return pieces


# ============================================================================
# AABB clipping utility
# ============================================================================

def _clip_bbox_by_halfspace_complement(bbox: AxisAlignedBoundingBox, hs: HalfSpace) -> AxisAlignedBoundingBox:
    """Return the bounding box of `bbox` minus the half space `hs`.

    An infinite or empty `bbox` is returned unchanged.
    """
    if bbox.is_empty:
        return bbox
    if any(v is None for v in [bbox.min_x, bbox.min_y, bbox.min_z,
                                bbox.max_x, bbox.max_y, bbox.max_z]):
        return bbox

    # 8 corners of the AABB
    corners = [
        Matrix([x, y, z])
        for x in (bbox.min_x, bbox.max_x)
        for y in (bbox.min_y, bbox.max_y)
        for z in (bbox.min_z, bbox.max_z)
    ]

    # 12 edges (each edge connects two corners that differ in exactly one coordinate)
    edges = [
        # 4 edges parallel to X
        (Matrix([bbox.min_x, bbox.min_y, bbox.min_z]), Matrix([bbox.max_x, bbox.min_y, bbox.min_z])),
        (Matrix([bbox.min_x, bbox.max_y, bbox.min_z]), Matrix([bbox.max_x, bbox.max_y, bbox.min_z])),
        (Matrix([bbox.min_x, bbox.min_y, bbox.max_z]), Matrix([bbox.max_x, bbox.min_y, bbox.max_z])),
        (Matrix([bbox.min_x, bbox.max_y, bbox.max_z]), Matrix([bbox.max_x, bbox.max_y, bbox.max_z])),
        # 4 edges parallel to Y
        (Matrix([bbox.min_x, bbox.min_y, bbox.min_z]), Matrix([bbox.min_x, bbox.max_y, bbox.min_z])),
        (Matrix([bbox.max_x, bbox.min_y, bbox.min_z]), Matrix([bbox.max_x, bbox.max_y, bbox.min_z])),
        (Matrix([bbox.min_x, bbox.min_y, bbox.max_z]), Matrix([bbox.min_x, bbox.max_y, bbox.max_z])),
        (Matrix([bbox.max_x, bbox.min_y, bbox.max_z]), Matrix([bbox.max_x, bbox.max_y, bbox.max_z])),
        # 4 edges parallel to Z
        (Matrix([bbox.min_x, bbox.min_y, bbox.min_z]), Matrix([bbox.min_x, bbox.min_y, bbox.max_z])),
        (Matrix([bbox.max_x, bbox.min_y, bbox.min_z]), Matrix([bbox.max_x, bbox.min_y, bbox.max_z])),
        (Matrix([bbox.min_x, bbox.max_y, bbox.min_z]), Matrix([bbox.min_x, bbox.max_y, bbox.max_z])),
        (Matrix([bbox.max_x, bbox.max_y, bbox.min_z]), Matrix([bbox.max_x, bbox.max_y, bbox.max_z])),
    ]

    valid_points = []

    # Keep corners that lie outside (or on the boundary of) the halfspace
    for c in corners:
        if not hs.contains_point(c):
            valid_points.append(c)

    # Find intersections of each AABB edge with the halfspace boundary plane
    for a, b in edges:
        na = safe_dot_product(hs.normal, a)
        nb = safe_dot_product(hs.normal, b)
        denom = nb - na
        if safe_compare(denom, 0, Comparison.EQ):
            # Edge parallel to the plane — no intersection
            continue
        t = (hs.offset - na) / denom
        if safe_compare(t, 0, Comparison.GE) and safe_compare(t - scalar(1), 0, Comparison.LE):
            valid_points.append(a + (b - a) * t)

    if not valid_points:
        # The entire bbox is consumed by the halfspace — nothing remains
        return AxisAlignedBoundingBox(0, 0, 0, 0, 0, 0, is_empty=True)

    xs = [p[0] for p in valid_points]
    ys = [p[1] for p in valid_points]
    zs = [p[2] for p in valid_points]
    return AxisAlignedBoundingBox(
        _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
        _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
    )


# ============================================================================
# CSG Coordinate Transform Utility
# ============================================================================

def translate_csg(csg: CutCSG, translation: V3) -> CutCSG:
    """Return a copy of `csg` translated by `translation`."""
    if isinstance(csg, SolidUnion):
        return SolidUnion(children=[translate_csg(c, translation) for c in csg.children], label=csg.label)
    if isinstance(csg, Difference):
        return Difference(
            base=translate_csg(csg.base, translation),
            subtract=[translate_csg(s, translation) for s in csg.subtract],
            label=csg.label,
        )
    if isinstance(csg, Intersection):
        return Intersection(
            left=translate_csg(csg.left, translation),
            right=translate_csg(csg.right, translation),
            label=csg.label,
        )
    if isinstance(csg, HalfSpace):
        # HalfSpace: normal·P >= offset. After translating by T: normal·(P - T) >= offset => normal·P >= offset + normal·T
        new_offset = csg.offset + safe_dot_product(csg.normal, translation)
        return replace(csg, offset=new_offset)
    if isinstance(csg, RectangularPrism):
        new_position = csg.transform.position + translation
        new_transform = replace(csg.transform, position=new_position)
        return replace(csg, transform=new_transform)
    if isinstance(csg, ConvexPolygonExtrusion):
        new_position = csg.transform.position + translation
        new_transform = replace(csg.transform, position=new_position)
        return replace(csg, transform=new_transform)
    if isinstance(csg, ConvexPolygonSimpleLoft):
        new_position = csg.transform.position + translation
        new_transform = replace(csg.transform, position=new_position)
        return replace(csg, transform=new_transform)
    if isinstance(csg, Cylinder):
        return replace(csg, position=csg.position + translation)
    # Unknown CSG type: return as-is
    return csg


def adopt_csg(
    orig_transform: Optional[Transform],
    adopting_transform: Optional[Transform],
    csg_in_orig_space: CutCSG,
) -> CutCSG:
    """Return `csg_in_orig_space` re-expressed from `orig_transform`'s local space in `adopting_transform`'s.

    Either transform may be None for global space.

    Example:
        >>> cut_on_b = adopt_csg(timber_a.transform, timber_b.transform, cut_csg)
        >>> csg_in_global = adopt_csg(timber_a.transform, None, cut_csg)
    """
    # Helper: Transform from orig (or global) to adopting local, or to global
    # coordinates when adopting_transform is None.
    def transform_transform(trans: Transform) -> Transform:
        if orig_transform is not None:
            global_position = orig_transform.numeric_local_to_global(trans.position)
            global_orientation = orig_transform.orientation * trans.orientation
        else:
            global_position = trans.position
            global_orientation = trans.orientation

        if adopting_transform is None:
            return Transform(position=global_position, orientation=global_orientation)

        local_position = adopting_transform.numeric_global_to_local(global_position)
        local_orientation = adopting_transform.orientation.invert() * global_orientation
        return Transform(position=local_position, orientation=local_orientation)

    # Helper: HalfSpace from orig (or global) to adopting local, or to global
    # coordinates when adopting_transform is None.
    def transform_halfspace(hp: HalfSpace) -> HalfSpace:
        if orig_transform is not None:
            global_normal = numeric_transform_vector(orig_transform.orientation.matrix, hp.normal)
        else:
            global_normal = hp.normal

        if adopting_transform is None:
            new_normal = global_normal
        else:
            new_normal = numeric_transform_vector(
                adopting_transform.orientation.matrix.T, global_normal
            )

        normal_length_sq = numeric_dot_product(hp.normal, hp.normal)
        if safe_zero_test_sq(normal_length_sq):
            return replace(hp, normal=new_normal, offset=hp.offset)

        point_on_plane_in_orig = hp.normal * (hp.offset / normal_length_sq)
        if orig_transform is not None:
            point_on_plane_global = orig_transform.numeric_local_to_global(point_on_plane_in_orig)
        else:
            point_on_plane_global = point_on_plane_in_orig

        if adopting_transform is None:
            new_offset = numeric_dot_product(new_normal, point_on_plane_global)
        else:
            point_on_plane_new_local = adopting_transform.numeric_global_to_local(point_on_plane_global)
            new_offset = numeric_dot_product(new_normal, point_on_plane_new_local)
        return replace(hp, normal=new_normal, offset=new_offset)

    # Recursively transform based on CSG type
    if isinstance(csg_in_orig_space, SolidUnion):
        transformed_children = [
            adopt_csg(orig_transform, adopting_transform, child)
            for child in csg_in_orig_space.children
        ]
        return SolidUnion(transformed_children, label=csg_in_orig_space.label)

    elif isinstance(csg_in_orig_space, Intersection):
        transformed_left = adopt_csg(orig_transform, adopting_transform, csg_in_orig_space.left)
        transformed_right = adopt_csg(orig_transform, adopting_transform, csg_in_orig_space.right)
        return Intersection(left=transformed_left, right=transformed_right, label=csg_in_orig_space.label)

    elif isinstance(csg_in_orig_space, Difference):
        transformed_base = adopt_csg(orig_transform, adopting_transform, csg_in_orig_space.base)
        transformed_subtract = [
            adopt_csg(orig_transform, adopting_transform, sub)
            for sub in csg_in_orig_space.subtract
        ]
        return Difference(base=transformed_base, subtract=transformed_subtract, label=csg_in_orig_space.label)

    elif isinstance(csg_in_orig_space, HalfSpace):
        return transform_halfspace(csg_in_orig_space)

    elif isinstance(csg_in_orig_space, Cylinder):
        cyl = csg_in_orig_space
        if orig_transform is not None:
            global_position = orig_transform.numeric_local_to_global(cyl.position)
            global_axis = numeric_transform_vector(orig_transform.orientation.matrix, cyl.axis_direction)
        else:
            global_position = cyl.position
            global_axis = cyl.axis_direction

        if adopting_transform is None:
            return replace(cyl, position=global_position, axis_direction=global_axis)

        new_local_position = adopting_transform.numeric_global_to_local(global_position)
        new_local_axis = numeric_transform_vector(
            adopting_transform.orientation.matrix.T, global_axis
        )
        return replace(cyl, position=new_local_position, axis_direction=new_local_axis)

    elif hasattr(csg_in_orig_space, "transform"):
        new_transform = transform_transform(cast(Transform, csg_in_orig_space.transform))
        return replace(csg_in_orig_space, transform=new_transform)

    else:
        return csg_in_orig_space