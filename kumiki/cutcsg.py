"""
CutCSG - Constructive Solid Geometry operations for Kumiki

This module provides CSG primitives and operations for representing timber cuts
and geometry operations. All operations use plain Python floats (see rule.py);
comparisons go through the safe_* helpers so they carry a tolerance rather than
testing for bit-exact equality.

The low-level point tests -- contains_point, is_point_on_boundary,
get_outward_normal -- take an optional ``eps`` that widens that tolerance for
the duration of the call.

The feature queries -- find_all_features, find_first_feature, and CSGFeature.
test_point_unbounded -- take a *test tolerance* instead, which is a different
wearing similar clothes. An epsilon absorbs float error; a test tolerance
absorbs the gap between a raycast hit on the triangulated mesh and the
analytic surface it stands for, and how far a click lands from an edge or a
point it cannot hit exactly. See FeatureTestTolerances.
"""

import re
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union, cast
from dataclasses import dataclass, field, replace
from abc import ABC, abstractmethod
from enum import Enum, Flag
import warnings
from .rule import *
from .geometry import (Line, Plane, Point, intersect_line_plane, intersect_planes,
                       lines_are_coincident, planes_are_coincident, planes_are_parallel,
                       points_are_coincident)


# ============================================================================
# AABB utilities
# ============================================================================

def _numeric_min(*vals):
    """Return the minimum of given SymPy numeric values using safe comparison."""
    result = vals[0]
    for v in vals[1:]:
        if safe_compare(v - result, 0, Comparison.LT):
            result = v
    return result


def _numeric_max(*vals):
    """Return the maximum of given SymPy numeric values using safe comparison."""
    result = vals[0]
    for v in vals[1:]:
        if safe_compare(v - result, 0, Comparison.GT):
            result = v
    return result


@dataclass(frozen=True)
class AxisAlignedBoundingBox:
    """
    Axis-aligned bounding box (AABB) for a CSG object.

    Each bound is Optional[Numeric] where None means unbounded in that direction.

    When is_empty is True, the CSG object contains no points at all (e.g. EmptyCSG,
    or a union/intersection that reduces to nothing). The bound fields are meaningless
    in this case (by convention all set to 0) and must not be treated as a real
    zero-size box at the origin — check is_empty first.
    """
    min_x: Optional[Numeric]
    min_y: Optional[Numeric]
    min_z: Optional[Numeric]
    max_x: Optional[Numeric]
    max_y: Optional[Numeric]
    max_z: Optional[Numeric]
    is_empty: bool = False

class FeatureCategory(Enum):
    """What kind of place on a primitive's boundary a default feature names.

    One vocabulary across every primitive for simplicity. OK to add primitive specific keys here rather than reuse.

    Some will be paired with an index, others may be one offs (index 0)
    """

    CAP = 0     # 0 = the start end, 1 = the end end
    SIDE = 1    # n = the nth side;
    ARRIS = 2   # every arris, in one run -- see below
    CORNER = 3  # every corner, in one run -- see below

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
    """The arris where a side meets one of the caps.

    One of the two places that know how the ARRIS run is laid out; see
    FeatureCategory. Reading "arris.5" back needs the side count, which nothing
    in the code has to do -- a key is matched and named, never decoded -- so
    that cost falls on a person rather than on a caller.
    """
    return (FeatureCategory.ARRIS, sides * (2 if end else 1) + side)


def corner_on_cap(vertex: int, vertices: int, end: bool) -> FeatureKey:
    """Vertex n of the start or end profile, in the one CORNER run."""
    return (FeatureCategory.CORNER, (vertices if end else 0) + vertex)


def default_feature_name(key: FeatureKey) -> str:
    """What a default feature is called when nobody has named it.

    Deterministic, so a default is referenceable -- from a drawing, a
    measurement, an override -- without anyone having authored a name for it.
    Lower case and dotted to sit alongside the authored names already in use,
    which look like "ptw.front" and "rough.back_right".
    """
    category, index = key
    return f"{category.name.lower()}.{index}"


# A prism's four sides in order around it -- +x, +y, -x, -y -- which is what
# fixes the meaning of SIDE n, and with it ARRIS n as the join between side n
# and side n+1.
#
# Not just any consistent cycle: this is timber.TimberFeature's order, so that
# side n and arris n pick out the same things RIGHT_FACE..BACK_FACE and
# RIGHT_FRONT_EDGE..TOP_BACK_EDGE do, in the same sequence. Anything mapping
# between the two vocabularies can then do it by position. Only the caps
# differ, because CAP 0 has to mean the START end -- see
# TestDefaultOrderFollowsTimberFeature, which pins all of this from the test
# side, since timber imports cutcsg and so cutcsg cannot say it here.
_PRISM_SIDE_ORDER: Tuple['PrismFace', ...] = ()  # filled in below, once PrismFace exists


class PrismFace(Enum):
    """Face of a RectangularPrism, indices match TimberFace."""
    TOP = 1
    BOTTOM = 2
    RIGHT = 3
    FRONT = 4
    LEFT = 5
    BACK = 6


_PRISM_SIDE_ORDER = (PrismFace.RIGHT, PrismFace.FRONT, PrismFace.LEFT, PrismFace.BACK)
_PRISM_CAP_KEYS = {PrismFace.BOTTOM: START_CAP, PrismFace.TOP: END_CAP}


class ExtrusionCap(Enum):
    """Which flat end of an extrusion-like primitive a feature is on."""
    TOP = 1
    BOTTOM = 2


# Key identifying one named feature on an extrusion-like primitive
# (ConvexPolygonExtrusion, pathcsg.PathExtrusion): an int n means the side face
# running from vertex n to vertex n+1 -- from points[n] to
# points[(n+1) % len(points)] for ConvexPolygonExtrusion, or from
# path.segments[n].start to path.segments[n].end for PathExtrusion. Same
# "n to n+1" meaning in both, so referencing side n means the same thing
# regardless of which of the two primitives it is.
ExtrusionFeatureKey = Union[int, ExtrusionCap]


class CylinderPart(Enum):
    """Which surface of a Cylinder a feature is on.

    BARREL is the curved lateral surface. Unlike a prism's four sides it is a
    single feature, not four -- there is no non-arbitrary way to cut it up, and
    nothing in joinery wants to reference "a quarter of a peg hole wall".
    """
    TOP = 1
    BOTTOM = 2
    BARREL = 3


class CSGFeatureType(Enum):
    """What kind of geometry a feature names.

    The cases measurement cares about: measuring between two features
    dispatches on this pair (two parallel faces measure like two parallel
    planes, a point and a face measure a projected distance, and so on).

    EDGE arrives with features derived from intersecting face pairs; POINT with
    their vertices.

    TODO consider adding DERIVED_POINT and DERIVED_FACE here
    """
    FACE = 1
    EDGE = 2
    POINT = 3
    CURVED_FACE = 4


# Default tolerances for deciding whether a point is on a feature. Units are
# model units (metres), so these are 0.5mm / 2mm / 4mm.
#
# These are tolerances rather than epsilons, and the distinction is the point
# of the name: an epsilon absorbs float error, and EPSILON_GENERIC (1e-8) is
# sized for that. These absorb something far larger -- the gap between a
# raycast hit on the triangulated mesh and the analytic surface it stands for,
# plus, for edges and points, however far a human click lands from a target it
# cannot hit exactly. Code doing exact analytic work wants
# FeatureTestTolerances.exact() instead.
FEATURE_FACE_TOLERANCE = scalar('5e-4')
FEATURE_EDGE_TOLERANCE = scalar('2e-3')
FEATURE_POINT_TOLERANCE = scalar('4e-3')


@dataclass(frozen=True)
class FeatureTestTolerances:
    """How close a point must be to count as on a feature, per feature type.

    Not epsilons: an epsilon absorbs float error, while these absorb the gap
    between meshed and analytic geometry and the imprecision of a human click.
    They are several orders of magnitude larger than EPSILON_GENERIC and are
    chosen, not derived.

    One tolerance does not fit all three, and the reason is about how features
    get selected rather than about the geometry:

    - a FACE you click directly, so the only slack needed is the gap between
      the analytic surface and the triangulated mesh a raycast actually hits;
    - an EDGE or a POINT you cannot click exactly at all. Selecting one means
      snapping to it, the way any CAD package works, so they want considerably
      more room -- and a caller driving this from a viewport usually wants to
      derive theirs from screen space, or a line is unhittable zoomed out and
      greedy zoomed in.

    This replaces the earlier pair of `eps` / `snap_eps` parameters, which
    keyed the wider tolerance off `real` instead. Type is the better key: a
    real derived edge is just as unclickable as a non-real centre axis.
    """
    face: Numeric = FEATURE_FACE_TOLERANCE
    edge: Numeric = FEATURE_EDGE_TOLERANCE
    point: Numeric = FEATURE_POINT_TOLERANCE

    def for_type(self, feature_type: 'CSGFeatureType') -> Numeric:
        """The test tolerance for a feature of *feature_type*."""
        if feature_type == CSGFeatureType.EDGE:
            return self.edge
        if feature_type == CSGFeatureType.POINT:
            return self.point
        return self.face

    def __mul__(self, factor: Numeric) -> 'FeatureTestTolerances':
        """Scale every tolerance by *factor*.

        The reason this exists is camera zoom. Selecting an edge or a point is
        a snap, and how much slack a snap needs is a screen-space question: a
        fixed 2mm is a comfortable target zoomed in and an invisible one zoomed
        out. A viewport can hold one FeatureTestTolerances describing the tolerances
        at some reference zoom and scale it by world-units-per-pixel per query.
        """
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
        """The same tolerance for every feature type."""
        return FeatureTestTolerances(face=eps, edge=eps, point=eps)

    @staticmethod
    def exact() -> 'FeatureTestTolerances':
        """Analytic tolerance, for geometry that was never triangulated."""
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
    """Which other features a feature is allowed to form an edge with.

    Deriving edges from every pair of faces in a CSG tree produces mostly
    nonsense -- a tenon cheek and the far end of the timber do not meet. Groups
    make the useful pairs declarable instead of searched for:

        A  intersects with B1 and B2
        B1 intersects with A only
        B2 intersects with A, and with itself
        C  intersects with itself only

    NONE is the exception to the scheme: it meets nothing, not even itself, and
    is how a feature says it forms no edges at all. Some geometry is worth
    naming and pointing at without every face of it turning into an arris.

    Defaults today: a timber's perfect-timber-within and rough faces are B2,
    and every named joint feature is A -- so joint geometry meets the timber
    body, and the body meets itself, the latter being the timber's own four
    long arrises, which drawing generation needs. B1 and C are defined but
    unused until something needs them.

    A consequence of the body meeting itself: relief geometry embeds the MATING
    timber's rough body to scribe against, and its faces carry the same reserved
    rough.* names (see timber.ROUGH_FACE_PREFIX). Two timbers' faces then pair
    into an edge that reads as one timber's -- rough.back x rough.back -- since
    the name says nothing about whose body it is.
    """
    A = 1
    B1 = 2
    B2 = 3
    C = 4
    #: Forms no edges with anything, including itself.
    NONE = 5


# Which groups each group forms edges with. Symmetric by construction; see
# FeatureGroup for what the letters mean.
FEATURE_GROUP_PAIRS: dict = {
    FeatureGroup.A: frozenset({FeatureGroup.B1, FeatureGroup.B2}),
    FeatureGroup.B1: frozenset({FeatureGroup.A}),
    FeatureGroup.B2: frozenset({FeatureGroup.A, FeatureGroup.B2}),
    FeatureGroup.C: frozenset({FeatureGroup.C}),
    FeatureGroup.NONE: frozenset(),
}


def feature_groups_intersect(a: FeatureGroup, b: FeatureGroup) -> bool:
    """Whether features in groups *a* and *b* may form an edge together."""
    return b in FEATURE_GROUP_PAIRS[a]



class FeatureMarkingStatus(Enum):
    """Whether a feature has to appear on a drawing.

    DECLARED INTENT, NOT YET HONOURED. Every feature carries one and nothing
    reads it: the drawing generator does not consult it when deciding what to
    mark. Kept because the vocabulary is the part worth settling early -- a
    joint that wants a face always dimensioned has somewhere to say so the day
    the generator learns to ask.
    """

    OPTIONAL = 0
    ALWAYS_MARK = 1
    NEVER_MARK = 2


@dataclass(frozen=True)
class FeatureMarkingSpec:
    """How a feature should be marked, when that differs from the default.

    mark_relative_to names the feature a dimension should be measured from,
    which is how a drawing says "38mm from the shoulder" rather than giving an
    absolute position. None leaves that to whatever generates the drawing.

    DECLARED INTENT, NOT YET HONOURED. Nothing sets marking_override and
    nothing reads it, so a joint cannot yet say how it wants to be dimensioned.
    """

    mark: FeatureMarkingStatus = FeatureMarkingStatus.OPTIONAL
    mark_relative_to: Optional[str] = None


class FeaturePurpose(Enum):
    """What purpose the feature serves.

    DECLARED INTENT, NOT YET HONOURED for ROUGH_RELIEF: it is never set and
    never tested against, so relief geometry is still indistinguishable from a
    joint's real surfaces everywhere it matters -- picking, measuring and
    drawing alike. That is the one of these with a visible cost.
    """

    NOT_SPECIFIED = 0
    ROUGH_RELIEF = 1


@dataclass(frozen=True)
class FeatureProperties:
    """Metadata every feature carries, independent of how it is identified.

    Args:
        group: which other features this one may form an edge with. NONE by
            default, so a feature pairs with nothing unless someone says it
            should. Deriving an edge is the expensive, noisy thing the feature
            system does -- every pairing is a line that has to be worth
            selecting -- so it is opted into rather than out of. Today the only
            pairing anyone wants is a shoulder plane against the timber's own
            prism.
        priority: lower wins when several features claim the same point.
        real: False for a feature that names no actual surface (a bore's centre
            axis, a reference plane). Real features can be cropped away by the
            CSG tree and so are tested against the triangulated result first;
            non-real ones are unaffected by boolean operations.
        marking_override: how to mark this feature on a drawing, when the
            default for its kind is not what is wanted. None means the default.
            Declared intent: carried, not yet read -- see FeatureMarkingSpec.
        purpose: what the feature is for, where that is worth recording --
            relief geometry is not a feature of the joint the way a tenon
            cheek is. Declared intent: carried, not yet read -- see
            FeaturePurpose.
    """

    group: FeatureGroup = FeatureGroup.NONE
    priority: int = 0
    real: bool = True
    marking_override: Optional[FeatureMarkingSpec] = None
    purpose: FeaturePurpose = FeaturePurpose.NOT_SPECIFIED


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
    """Those hits the point is actually on, each judged at its own type's tolerance."""
    return [hit for hit in hits
            if hit.feature.test_point_unbounded(
                hit.owner, point, tolerances.for_type(hit.feature.feature_type()))]


def _sort_feature_hits(hits: List['OwnedFeatureHit']) -> List['OwnedFeatureHit']:
    """Best answer first.

    Non-real beats real: selecting a centre axis is a deliberate snap, and a
    surface it happens to lie on should not steal the click. Then the more
    specific kind -- a point sits on an edge sits on a face, and the narrowest
    claimant is the better answer, so an edge beats the two faces that formed
    it.

    Specificity stays ahead of everything below it on purpose. Declaredness
    ranks above priority, but ABOVE specificity it would hand a click on an
    arris to one of the declared faces meeting there, which is the answer
    deriving edges exists to stop giving.

    Then, in order: a declared feature before a derived one; the pairing group,
    best rank first; author-set priority; the name; and, last, the order the
    features were gathered in, which sorted() preserves without a key of its
    own.
    """
    return sorted(hits, key=lambda hit: (
        hit.feature.real,
        _FEATURE_TYPE_SPECIFICITY[hit.feature.feature_type()],
        hit.feature.is_derived(),
        hit.feature.group_rank(),
        hit.feature.priority,
        hit.feature.name,
    ))


def _names_same_geometry(one: 'OwnedFeatureHit', other: 'OwnedFeatureHit') -> bool:
    """Whether two hits name the same point, line or plane.

    Different kinds are never the same geometry, and a feature that declines to
    locate never matches anything -- a cylinder's barrel is not comparable to
    another, so it is never dropped as a duplicate of one.
    """
    here, there = one.locate_simple_unbounded(), other.locate_simple_unbounded()
    if isinstance(here, Point) and isinstance(there, Point):
        return points_are_coincident(here, there)
    if isinstance(here, Line) and isinstance(there, Line):
        return lines_are_coincident(here, there)
    if isinstance(here, Plane) and isinstance(there, Plane):
        return planes_are_coincident(here, there)
    return False


def _drop_duplicate_derived(hits: List['OwnedFeatureHit']) -> List['OwnedFeatureHit']:
    """removes derived features that coincide with non derived fetarues, expects _sort_feature_hits order.
    """
    kept: List['OwnedFeatureHit'] = []
    # It is NOT true in general that declared features come first: _sort_feature_hits
    # ranks specificity above declaredness on purpose, so a derived EDGE sorts ahead
    # of the declared FACE it was made from.
    #
    # What makes this correct is narrower. _names_same_geometry only ever matches a
    # pair of the same kind -- Point to Point, Line to Line, Plane to Plane -- and
    # within one kind the specificity key ties, so declaredness is what decides.
    # A derived hit therefore always meets its declared twin already in `kept`.
    for hit in hits:
        twin = next((other for other in kept if _names_same_geometry(hit, other)), None)
        if hit.feature.is_derived() and twin is not None:
            # The precondition above, checked rather than assumed: the thing it is
            # a duplicate of must be the declared one, not another derived hit that
            # happened to sort first.
            assert not twin.feature.is_derived(), (
                f"{hit.feature.name} was dropped against {twin.feature.name}, which is "
                f"itself derived -- _sort_feature_hits no longer puts declared first "
                f"within a kind, so this dedup is picking an arbitrary winner")
            continue
        kept.append(hit)
    return kept


def shared_ancestor(
    some_common_ancestor: 'CutCSG',
    first: 'CutCSG',
    second: 'CutCSG',
) -> Optional['CutCSG']:
    """The deepest node under *some_common_ancestor* holding both *first* and *second*, or None if there is none.
    """
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
    """The chain of nodes from *node* down to *target*, or None if it is not there."""
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
    """Every edge formed by a pair of *face_hits*.

    The resultant hits are owned by the first shared ancestor of the 2 features forming the derived edge.

    Careful, O(len(face_hits)^2), expected to be bounded by the fact that `len(face_hits)` should be reasonably bounded in well behaved cases.
    """
    hits: List['OwnedFeatureHit'] = []
    for i in range(len(face_hits)):
        for j in range(i + 1, len(face_hits)):
            edge = DerivedEdgeFeature.derive(face_hits[i], face_hits[j])
            if edge is None:
                continue
            owner = shared_ancestor(some_common_ancestor, face_hits[i].owner, face_hits[j].owner)
            if owner is None:
                # Both parents came out of one gather, so both are
                # under it and this cannot happen. Said out loud rather than
                # guessed at: an edge owned by the wrong node is worse than one
                # that is missing and complained about.
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
    """Every point where one of *edge_hits* crosses one of *face_hits*. If edge lies in the face plane, nothing is returned (even if its acutally just 1 point of intersection due to line ending at the face boundary)

    The resultant hits are owned by the first shared ancestor of the 2 features forming the derived point

    An edge lies IN both faces that formed it, and those pairs cost a rejection
    each rather than needing filtering: intersect_line_plane declines a line in
    its plane.
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
    """checks if the test `point` (from `collect_feature_hits` call) is on the boundary. If it is, return all feature hits. If it's not, return only the non real ones (e.g. cylinder centerline is not on the boundary usually)

    NOTE parts of the dropped features may still be on the boundary, but we don't count those as a "hit" if the test point was off the boundary.
    """
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


def _box_around(points: Sequence[V3]) -> 'AxisAlignedBoundingBox':
    """The smallest axis-aligned box holding these points."""
    reach = [[float(point[axis, 0]) for point in points] for axis in range(3)]
    return AxisAlignedBoundingBox(
        min_x=scalar(repr(min(reach[0]))), min_y=scalar(repr(min(reach[1]))),
        min_z=scalar(repr(min(reach[2]))), max_x=scalar(repr(max(reach[0]))),
        max_y=scalar(repr(max(reach[1]))), max_z=scalar(repr(max(reach[2]))))


def _finite_midpoint(start: Optional[Numeric], end: Optional[Numeric]) -> Numeric:
    """Midpoint of a possibly-infinite extent along an axis.

    An anchor point only has to be somewhere sensible on the feature, so an
    end that runs to infinity contributes the finite one instead of NaN.
    """
    if start is None:
        return scalar(0) if end is None else end
    if end is None:
        return start
    return (start + end) / scalar(2)


# What locate() can hand back. Unbounded on purpose: measurement between two
# features works on infinite lines and planes, and bounds travel separately in
# CSGFeatureExtent.
LocatedFeatureGeometry = Union[Point, Line, Plane]


# NOTE this class is a little weird but it's fine for now I guess, maybe think of less weird way to do this
# NOTE this class is used for 2 things
# 1. as a simple broad phase test on individual nodes
# 2. to determine where the measurement anchors for 
# TODO consider getting rid of this becasue:
# 1. I don't think we cache extents + and there is no KD/oct tree so this is not really doing much for perf
# 2. measurement anchor position should have its own function
@dataclass(frozen=True)
class CSGFeatureExtent:
    """Roughly where a feature is, for placing annotations against it.

    Args:
        anchor: a representative point -- a face's centre, an edge's midpoint,
            or the point itself.
        ends: for an edge, its two endpoints.
        aabb: for a face, a rough bounding box.
    """
    anchor: V3
    ends: Optional[Tuple[V3, V3]] = None
    aabb: Optional['AxisAlignedBoundingBox'] = None


@dataclass(frozen=True)
class CSGFeature(ABC):
    """An ABC representing a feature on the CutCSG's boundary or a non-real feature of the CutCSG (e.g. the axis of a cylinder)
    
    This feature class itself need not be aware of its owner CSG or sibling features
    Instead ,this information is obtained by calling `locate` with its owner CSG to convert it into its owner's space
    """
    name: str
    properties: FeatureProperties = field(default_factory=FeatureProperties)

    def feature_key(self) -> Optional['FeatureKey']:
        """Which default slot this feature occupies, or None if it has none.

        This is what lets an authored feature REPLACE the default at the same
        place rather than sit alongside it. None is the honest answer for
        anything with no fixed place on a primitive -- a ProgrammableCSGFeature
        matching a formula, or a derived edge, which exists only as the product
        of two hits and never occupies a slot of its own.
        """
        return None

    @abstractmethod
    def feature_type(self) -> CSGFeatureType:
        """What kind of geometry this feature names.
        """
        ...

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        """The unbounded geometry this feature lies on, in the owner's space.

        A Plane for a planar face, a Line for an edge, a Point for a vertex.

        `None` when the feature names a surface that is not one of those -- a
        cylinder's barrel, a lofted side, an extrusion side that follows a
        curved path segment.
        
        The returned geometry is "global" in the space of `owner` which is likely local in some Timber's space.
        """
        return None

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        """Roughly where this feature sits, for placing annotations.

        None when the feature has no bounded extent at all (a half-space's
        plane), or when it is not worked out for this shape yet.
        """
        return None

    @property
    def group(self) -> FeatureGroup:
        return self.properties.group

    def is_derived(self) -> bool:
        """Whether this feature was derived from others rather than declared.
        """
        return False

    def group_rank(self) -> int:
        """Where this feature's collision group sits in the preference order. Used only for sorting features.

        A derived feature will override this to take the better rank of its 2 parents.
        """
        return self.group.value

    @property
    def real(self) -> bool:
        return self.properties.real

    @property
    def priority(self) -> int:
        return self.properties.priority

    @abstractmethod
    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Whether *point* lies on this feature's surface ignoring any boundaries it may or may not have.

        NOTE we still need `owner` here for its local transform. We don't use it for its boundaries.

        To convert into bounded features, use something like `collect_fetaure_hits` which gates every real feature on
        is_point_on_boundary of top node we call into.

        FOR CONSIDERATION: two more optional arguments, a surface normal and a
        line, so a caller that knows more about the point can say so. Worth revisiting if a picker ever hands back the analytic surface it hit
        rather than the triangle, since then both arguments mean what they say.
        """
        ...


@dataclass(frozen=True)
class ProgrammableCSGFeature(CSGFeature):
    """A feature identified by an arbitrary predicate rather than an enum member.

    The escape hatch for anything the simple per-primitive classes cannot name.

    Currently unused, but a sensible placeholder to limit the assumption we can make on CSGFeature i.e. ProgrammableCSGFeature must be supported
    """
    predicate: Optional[Callable[['CutCSG', V3, Optional[Numeric]], bool]] = None
    # The only class that stores its kind: a predicate can describe a face, an
    # edge or a point, so there is nothing constant to return.
    declared_type: CSGFeatureType = CSGFeatureType.FACE

    def feature_type(self) -> CSGFeatureType:
        return self.declared_type

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if self.predicate is None:
            return False
        return self.predicate(owner, point, test_tolerance)


def _as_plane(geometry: Optional['LocatedFeatureGeometry']) -> Optional[Plane]:
    """Narrow a located geometry to a Plane, or None if it is not one.

    locate() can hand back a Point or a Line as well, and a face that declines
    to locate hands back nothing. Only planes intersect into edges.
    """
    return geometry if isinstance(geometry, Plane) else None


def _point_is_near(point: V3, other: V3, tolerance: Optional[Numeric] = None) -> bool:
    """Whether two points are within *tolerance* of each other."""
    gap = point - other
    return safe_zero_test_sq(safe_dot_product(gap, gap), eps=tolerance)


def _point_is_on_line(point: V3, line: Line, tolerance: Optional[Numeric] = None) -> bool:
    """Whether *point* lies within *tolerance* of an infinite line."""
    along = safe_normalize_vector(line.direction)
    from_start = point - line.point
    across = from_start - along * safe_dot_product(from_start, along)
    return safe_zero_test_sq(safe_dot_product(across, across), eps=tolerance)


@dataclass(frozen=True)
class DerivedEdgeFeature(CSGFeature):
    """The edge where two planar FACE features meet.

    The `owner` of the edge itself is the deepest node holding both of them --
    see shared_ancestor. 
    """

    #: The two faces forming this edge
    #:
    #: TODO consider refactoring OwnedFeatureHit to be split out by types so these can be typed to faces
    a: 'OwnedFeatureHit' = field(kw_only=True)
    b: 'OwnedFeatureHit' = field(kw_only=True)

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.EDGE

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Test the point against the analytic edge itself. Testing against both
        faces alone will return bad results when the two faces are almost parallel.
        """
        line = self.locate_simple_unbounded(owner)
        if isinstance(line, Line):
            return _point_is_on_line(point, line, test_tolerance)
        # debatable if this is the right behavior. In any case, this code path
        # should never get hit since DerivedEdges are only created when there
        # is an actual line.
        return (self.a.feature.test_point_unbounded(self.a.owner, point, test_tolerance)
                and self.b.feature.test_point_unbounded(self.b.owner, point, test_tolerance))

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        # None if either parent is a surface with no plane -- a cylinder
        # barrel, a lofted side. The edge is still pickable; it just cannot be
        # measured against, the same decline locate() makes elsewhere.
        return intersect_planes(_as_plane(self.a.locate_simple_unbounded()), _as_plane(self.b.locate_simple_unbounded()))

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        """Where this edge sits, and where it ends when its parents can say.

        bounds the edge based on the boundaries of the 2 parent faces
        
        Exact when the line runs along one of a face's own directions, which is
        every arris of a box. For an oblique line across a rectangle it is the
        bounding interval rather than the true crossing: an over-estimate, never
        an under-estimate, so an edge is never reported shorter than it is.

        TODO/NOTE ^ we could make it exact, but it's not necessary right now, consider doing so in the future

        `ends` stays None when neither parent can bound it, and `anchor` is then
        the point on the INFINITE line closest to the origin, which need not be
        anywhere near the stretch that exists.
        """
        line = self.locate_simple_unbounded(owner)
        if not isinstance(line, Line):
            return None
        start, along = line.point, line.direction

        def reach_along_the_line(corners: Sequence[V3]) -> Tuple[float, float]:
            """How far along the line those corners reach, either way."""
            stations = [float(((corner - start).T * along)[0, 0]) for corner in corners]
            return (min(stations), max(stations))

        def at(station: float) -> V3:
            return start + along * scalar(repr(station))

        bounds = []
        for hit in (self.a, self.b):
            # Nothing for a face that cannot say where its corners are: one
            # running to infinity, or a shape that does not work them out yet.
            corners = getattr(hit.feature, "corners", None)
            found = corners(hit.owner) if corners is not None else None
            if found:
                bounds.append(reach_along_the_line(found))

        if bounds:
            low = max(span[0] for span in bounds)
            high = min(span[1] for span in bounds)
            if low < high:
                return CSGFeatureExtent(
                    anchor=at((low + high) / 2), ends=(at(low), at(high)))
        return CSGFeatureExtent(anchor=start)

    @staticmethod
    def derive(a: 'OwnedFeatureHit', b: 'OwnedFeatureHit') -> Optional['DerivedEdgeFeature']:
        """The edge where *a* and *b* meet, or None if they form none.

        None when: 
        - either is not a face; 
        - their groups are not allowed to meet;
        - either names a face that is not THERE (e.g. the top of an infinite prism)
        - or their planes are parallel (which includes being the same plane -- coincident faces share a whole plane, not a line).
        """
        if a.feature.feature_type() != CSGFeatureType.FACE:
            return None
        if b.feature.feature_type() != CSGFeatureType.FACE:
            return None
        if not feature_groups_intersect(a.feature.group, b.feature.group):
            return None

        # A face that is not there forms no edge. The top of a prism extended
        # to infinity is the case that turns this up -- a timber's rough stock
        # is exactly that -- and without the check the pair was accepted and
        # the edge then located to nothing, which reads downstream as "cannot
        # say" rather than "not an edge".
        for hit in (a, b):
            if (hit.feature.locate_simple_unbounded(hit.owner) is None
                    and hit.feature.get_extent(hit.owner) is None):
                return None
            
        if planes_are_parallel(_as_plane(a.locate_simple_unbounded()), _as_plane(b.locate_simple_unbounded())):
            return None

        # Deterministic order, so the same edge gets the same identity however traversal reached it.
        first, second = sorted(
            (a, b), key=lambda hit: (hit.feature.group.value, hit.feature.name))
        return DerivedEdgeFeature(
            name=f"{first.feature.name}\u00d7{second.feature.name}",
            properties=FeatureProperties(
                # An edge exists only where both its faces do.
                real=a.feature.real and b.feature.real,
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
        """The better rank of the two faces that formed it."""
        ranks = [hit.feature.group.value for hit in (self.a, self.b) if hit is not None]
        return min(ranks) if ranks else FeatureGroup.NONE.value


@dataclass(frozen=True)
class DerivedPointFeature(CSGFeature):
    """The point where an edge feature crosses a face feature.

    """
    #: The edge and the face that cross here. Required, as on DerivedEdgeFeature.
    a: 'OwnedFeatureHit' = field(kw_only=True)
    b: 'OwnedFeatureHit' = field(kw_only=True)

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.POINT

    def is_derived(self) -> bool:
        return True

    def group_rank(self) -> int:
        """The better rank of the edge and the face that formed it."""
        ranks = [hit.feature.group.value for hit in (self.a, self.b) if hit is not None]
        return min(ranks) if ranks else FeatureGroup.NONE.value

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Whether *point* is on the vertex itself, not merely on the edge and
        the face that cross there.
        """
        vertex = self.locate_simple_unbounded(owner)
        if isinstance(vertex, Point):
            return _point_is_near(point, vertex.position, test_tolerance)
        # debatable if this is the right behavior. In any case, this falls back
        # to the parents only when locate_simple_unbounded returns no vertex,
        # which should never happen.
        return (self.a.feature.test_point_unbounded(self.a.owner, point, test_tolerance)
                and self.b.feature.test_point_unbounded(self.b.owner, point, test_tolerance))

    def _line_and_plane(self) -> Tuple[Optional[Line], Optional[Plane]]:
        """The parents' geometry, sorted into which is which.

        Parents are stored in the order that names the feature deterministically
        rather than edge-then-face, so this picks them apart by what they
        located to rather than by position.
        """
        line: Optional[Line] = None
        plane: Optional[Plane] = None
        for hit in (self.a, self.b):
            if hit is None:
                continue
            located = hit.locate_simple_unbounded()
            if isinstance(located, Line) and line is None:
                line = located
            elif isinstance(located, Plane) and plane is None:
                plane = located
        return line, plane

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        line, plane = self._line_and_plane()
        return intersect_line_plane(line, plane)

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        located = self.locate_simple_unbounded(owner)
        if not isinstance(located, Point):
            return None
        return CSGFeatureExtent(anchor=located.position)

    @staticmethod
    def derive(a: 'OwnedFeatureHit', b: 'OwnedFeatureHit') -> Optional['DerivedPointFeature']:
        """The point where *a* and *b* cross, or None if they cross in none.

        None when: 
        - they are not one EDGE and one FACE; 
        - their groups may not meet; 
        - either names something that is not THERE (e.g. top end of an infinite prism); 
        - or the line does not pierce the plane in a single point -- which includes the line LYING in the plane
        """
        types = {a.feature.feature_type(), b.feature.feature_type()}
        if types != {CSGFeatureType.EDGE, CSGFeatureType.FACE}:
            return None
        if not feature_groups_intersect(a.feature.group, b.feature.group):
            return None

        for hit in (a, b):
            if (hit.feature.locate_simple_unbounded(hit.owner) is None
                    and hit.feature.get_extent(hit.owner) is None):
                return None

        edge, face = ((a, b) if a.feature.feature_type() == CSGFeatureType.EDGE else (b, a))
        located_edge, located_face = edge.locate_simple_unbounded(), face.locate_simple_unbounded()
        if not isinstance(located_edge, Line):
            return None
        if intersect_line_plane(located_edge, _as_plane(located_face)) is None:
            return None

        # Deterministic order, so the same point gets the same identity however
        # traversal reached it.
        first, second = sorted(
            (a, b), key=lambda hit: (hit.feature.group.value, hit.feature.name))
        return DerivedPointFeature(
            name=f"{first.feature.name}\u00d7{second.feature.name}",
            properties=FeatureProperties(
                # A point exists only where both its parents do.
                real=a.feature.real and b.feature.real,
                priority=max(a.feature.priority, b.feature.priority),
                # Nothing pairs points; see DerivedEdgeFeature on why this is
                # said rather than defaulted.
                group=FeatureGroup.NONE,
            ),
            a=first,
            b=second,
        )


@dataclass(frozen=True)
class HalfSpaceFeature(CSGFeature):
    """The entire boundary plane of a HalfSpace.
    """

    def feature_key(self) -> Optional[FeatureKey]:
        # Its only surface. Not a cap: a half space has no ends to be an end of.
        return (FeatureCategory.SIDE, 0)

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        if not isinstance(owner, HalfSpace):
            return None
        # The solid is dot(normal, p) >= offset, so the boundary plane is
        # dot(normal, p) == offset and the outward normal points out of it.
        normal_length_sq = safe_dot_product(owner.normal, owner.normal)
        if safe_zero_test_sq(normal_length_sq):
            return None
        closest_to_origin = owner.normal * (owner.offset / normal_length_sq)
        return Plane(normal=-owner.normal, point=closest_to_origin)

    # get_extent stays None: a half-space's plane is unbounded, so there is no
    # box to give and no midpoint that means anything.

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        return owner.is_point_on_boundary(point, eps=test_tolerance)


@dataclass(frozen=True)
class SimpleRectangularPrismFeature(CSGFeature):
    """One of the six faces of a RectangularPrism, named by PrismFace."""
    face: PrismFace = PrismFace.TOP

    def feature_key(self) -> Optional[FeatureKey]:
        if self.face in _PRISM_CAP_KEYS:
            return _PRISM_CAP_KEYS[self.face]
        return (FeatureCategory.SIDE, _PRISM_SIDE_ORDER.index(self.face))

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def _face_frame(self, owner: 'RectangularPrism') -> Optional[Tuple[Direction3D, V3]]:
        """(outward normal, centre point) of this face, in the owner's space."""
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

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
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
        """The face's two in-plane directions and half-sizes, or None if unbounded.

        A prism fully determines its own faces: two of the three local axes span
        each one, and how far it reaches along them is the size and the length.
        None when the end it would reach to runs to infinity, which is an honest
        answer rather than a guess -- an unbounded face has no corners.
        """
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
        """The face's four corners, exactly, or None when it is unbounded.
        """
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

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        if not isinstance(owner, RectangularPrism):
            return None
        frame = self._face_frame(owner)
        if frame is None:
            return None
        _, centre = frame
        corners = self.corners(owner)
        # TODO: carry the corners themselves, not a box. An aabb is axis-aligned
        # in WORLD space, so a face of a rotated prism gets a box substantially
        # larger than the face and never smaller -- which is fine for hinting
        # where to put an annotation and not good enough to measure against. An
        # edge carries its `ends` for exactly this reason; a face wants the same.
        # See docs/measurement-spec.md.
        if corners is None:
            # Unbounded in one direction, so the prism's own box is the most that can be said.
            return CSGFeatureExtent(anchor=centre, aabb=owner.get_aabb())
        return CSGFeatureExtent(anchor=centre, aabb=_box_around(corners))

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


def _canonical_arris_faces(
    first: 'PrismFace', second: 'PrismFace',
) -> Optional[Tuple['PrismFace', 'PrismFace']]:
    """The one order an arris between these two faces is named in.

    timber.py is the authority, since it names the arrises of every timber:
    a cap first, then the side (bottom_right); otherwise FRONT or BACK first,
    then RIGHT or LEFT (front_right, back_left).

    None for a pair that meets in no arris: one face twice, two caps, or two
    opposite sides.
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
class SimpleRectangularPrismEdgeFeature(CSGFeature):
    """An arris of a RectangularPrism, named by the two faces it lies between.
    """

    faces: Tuple[PrismFace, PrismFace] = (PrismFace.FRONT, PrismFace.RIGHT)

    def __post_init__(self):
        first, second = self.faces
        canonical = _canonical_arris_faces(first, second)
        if canonical is None:
            warnings.warn(
                f"{first} and {second} meet in no arris, so {self.name!r} locates "
                "to nothing")
        elif (first, second) != canonical:
            # Not cosmetic: the order decides which way round locate() runs the
            # line, since it is the cross product of the two faces' normals.
            warnings.warn(
                f"{self.name!r} names its faces {first}, {second}; the canonical "
                f"order is {canonical[0]}, {canonical[1]}")

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.EDGE

    def feature_key(self) -> Optional[FeatureKey]:
        """
        """
        first, second = self.faces
        if first in _PRISM_CAP_KEYS or second in _PRISM_CAP_KEYS:
            cap, side = ((first, second) if first in _PRISM_CAP_KEYS
                         else (second, first))
            if side in _PRISM_CAP_KEYS:
                return None  # two caps never meet
            return arris_against_cap(
                _PRISM_SIDE_ORDER.index(side), len(_PRISM_SIDE_ORDER),
                end=cap is PrismFace.TOP)
        low, high = (_PRISM_SIDE_ORDER.index(first), _PRISM_SIDE_ORDER.index(second))
        low, high = min(low, high), max(low, high)
        sides = len(_PRISM_SIDE_ORDER)
        if high - low == 1:
            return (FeatureCategory.ARRIS, low)
        if low == 0 and high == sides - 1:
            return (FeatureCategory.ARRIS, high)  # the wrap-around join
        return None  # opposite sides: parallel, no arris

    def _sides(self) -> Tuple['SimpleRectangularPrismFeature', 'SimpleRectangularPrismFeature']:
        """The two faces as features, so their geometry is worked out once, there."""
        return (
            SimpleRectangularPrismFeature(name=self.name, face=self.faces[0]),
            SimpleRectangularPrismFeature(name=self.name, face=self.faces[1]),
        )

    def test_point_unbounded(self, owner: 'CutCSG', point: V3,
                   test_tolerance: Optional[Numeric] = None) -> bool:
        first, second = self._sides()
        return (first.test_point_unbounded(owner, point, test_tolerance)
                and second.test_point_unbounded(owner, point, test_tolerance))

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        """The line the two faces meet in, or None if they never do."""
        first, second = self._sides()
        return intersect_planes(_as_plane(first.locate_simple_unbounded(owner)), _as_plane(second.locate_simple_unbounded(owner)))

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        """
        """
        line = self.locate_simple_unbounded(owner)
        if not isinstance(line, Line):
            return None
        first, second = self._sides()
        corners = first.corners(owner)
        if corners is not None:
            shared = [corner for corner in corners
                      if second.test_point_unbounded(owner, corner)]
            if len(shared) == 2:
                return CSGFeatureExtent(
                    anchor=(shared[0] + shared[1]) / scalar(2),
                    ends=(shared[0], shared[1]))
        return CSGFeatureExtent(anchor=line.point)


@dataclass(frozen=True)
class CylinderAxisFeature(CSGFeature):
    """The centre line of a Cylinder, down the middle of the void it cuts.
    """

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.EDGE

    @property
    def real(self) -> bool:
        return False

    def _cylinder(self, owner: 'CutCSG') -> Optional['Cylinder']:
        """The owner, as the Cylinder this feature is the axis of.

        None, with a warning, for anything else: an axis feature on a shape
        with no axis is a mistake in whatever named it.
        """
        if isinstance(owner, Cylinder):
            return owner
        warnings.warn(
            f"{self.name!r} is a cylinder axis, but its owner is a "
            f"{type(owner).__name__}, which has no axis")
        return None

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        cylinder = self._cylinder(owner)
        if cylinder is None:
            return None
        return Line(direction=safe_normalize_vector(cylinder.axis_direction),
                    point=cylinder.position)

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        """
        """
        cylinder = self._cylinder(owner)
        if cylinder is None:
            return None
        axis = safe_normalize_vector(cylinder.axis_direction)
        start, end = cylinder.start_distance, cylinder.end_distance
        anchor = cylinder.position + axis * _finite_midpoint(start, end)
        if start is None or end is None:
            return CSGFeatureExtent(anchor=anchor)
        return CSGFeatureExtent(
            anchor=anchor,
            ends=(cylinder.position + axis * start, cylinder.position + axis * end),
        )

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """On the axis if it is on the LINE -- the ends are not checked here
        """
        if not isinstance(owner, Cylinder):
            return False
        tolerance = DEFAULT_FEATURE_TEST_TOLERANCES.edge if test_tolerance is None else test_tolerance
        _axial, radial = owner._axial_and_radial(point)
        return safe_compare(radial, tolerance, Comparison.LE)


@dataclass(frozen=True)
class SimpleCylinderFeature(CSGFeature):
    """One surface of a Cylinder: an end cap, or the barrel."""
    part: CylinderPart = CylinderPart.BARREL

    def feature_key(self) -> Optional[FeatureKey]:
        if self.part is CylinderPart.BOTTOM:
            return START_CAP
        if self.part is CylinderPart.TOP:
            return END_CAP
        # A cylinder is an extrusion with one side, and that side is curved.
        return (FeatureCategory.SIDE, 0)

    def feature_type(self) -> CSGFeatureType:
        """A cap is planar; the barrel is not.
        """
        if self.part is CylinderPart.BARREL:
            return CSGFeatureType.CURVED_FACE
        return CSGFeatureType.FACE

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        if not isinstance(owner, Cylinder):
            return None
        # The barrel is curved: no single plane describes it, so decline rather
        # than invent one. (Its axis is a separate, non-real feature -- see D5.)
        if self.part == CylinderPart.BARREL:
            return None
        axis = safe_normalize_vector(owner.axis_direction)
        distance = owner.end_distance if self.part == CylinderPart.TOP else owner.start_distance
        if distance is None:
            return None
        sign = scalar(1) if self.part == CylinderPart.TOP else scalar(-1)
        return Plane(normal=axis * sign, point=owner.position + axis * distance)

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        if not isinstance(owner, Cylinder):
            return None
        axis = safe_normalize_vector(owner.axis_direction)
        if self.part == CylinderPart.BARREL:
            mid = _finite_midpoint(owner.start_distance, owner.end_distance)
            return CSGFeatureExtent(anchor=owner.position + axis * mid)
        distance = owner.end_distance if self.part == CylinderPart.TOP else owner.start_distance
        if distance is None:
            return None
        return CSGFeatureExtent(anchor=owner.position + axis * distance)

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, Cylinder):
            return False
        axial, radial = owner._axial_and_radial(point)
        if self.part == CylinderPart.TOP:
            return owner.end_distance is not None and safe_equality_test(axial, owner.end_distance, eps=test_tolerance)
        if self.part == CylinderPart.BOTTOM:
            return owner.start_distance is not None and safe_equality_test(axial, owner.start_distance, eps=test_tolerance)
        return safe_equality_test(radial, owner.radius, eps=test_tolerance)


@dataclass(frozen=True)
class SimpleConvexPolygonExtrusionFeature(CSGFeature):
    """One side face (points[key] -> points[key+1 mod n]) or end cap of a
    ConvexPolygonExtrusion."""
    key: ExtrusionFeatureKey = ExtrusionCap.TOP

    def feature_key(self) -> Optional[FeatureKey]:
        if self.key is ExtrusionCap.BOTTOM:
            return START_CAP
        if self.key is ExtrusionCap.TOP:
            return END_CAP
        return (FeatureCategory.SIDE, int(self.key))

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def _frame(self, owner: 'ConvexPolygonExtrusion') -> Optional[Tuple[Direction3D, V3]]:
        """(outward normal, centre point) of this face, in the owner's space."""
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

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
        if not isinstance(owner, ConvexPolygonExtrusion):
            return None
        frame = self._frame(owner)
        if frame is None:
            return None
        normal, centre = frame
        return Plane(normal=normal, point=centre)

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        if not isinstance(owner, ConvexPolygonExtrusion):
            return None
        frame = self._frame(owner)
        if frame is None:
            return None
        _, centre = frame
        return CSGFeatureExtent(anchor=centre, aabb=owner.get_aabb())

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
class SimpleLoftFeature(CSGFeature):
    """One side face or end cap of a ConvexPolygonSimpleLoft.

    Side faces are ruled surfaces and are only planar in the special case of a
    pure per-axis taper, so a named side is a surface, not necessarily a plane.
    Edge derivation (which assumes planes) has to account for that.
    """
    key: ExtrusionFeatureKey = ExtrusionCap.TOP

    def feature_key(self) -> Optional[FeatureKey]:
        if self.key is ExtrusionCap.BOTTOM:
            return START_CAP
        if self.key is ExtrusionCap.TOP:
            return END_CAP
        return (FeatureCategory.SIDE, int(self.key))

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[LocatedFeatureGeometry]:
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

        # A side, which is planar because is_valid refuses a twisted loft -- see
        # ConvexPolygonSimpleLoft._sides_are_planar. It used to decline here
        # whatever the shape, since a twist COULD make it a ruled surface, and
        # that cost every tapered cheek the ability to be measured to.
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

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        if not isinstance(owner, ConvexPolygonSimpleLoft):
            return None
        orientation = owner.transform.orientation.matrix
        if self.key in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            is_top = self.key == ExtrusionCap.TOP
            profile = owner.top_points if is_top else owner.bottom_points
            distance = owner.top_points_z_pos if is_top else owner.bottom_points_z_pos
        else:
            profile = [(b + t) / scalar(2) for b, t in zip(owner.bottom_points, owner.top_points)]
            distance = _finite_midpoint(owner.bottom_points_z_pos, owner.top_points_z_pos)
        if self.key in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            centroid_2d = sum(profile[1:], profile[0]) / scalar(len(profile))
        else:
            p1 = profile[self.key]
            p2 = profile[(self.key + 1) % len(profile)]
            centroid_2d = (p1 + p2) / scalar(2)
        local = Matrix([centroid_2d[0], centroid_2d[1], distance])
        return CSGFeatureExtent(
            anchor=owner.transform.position + safe_transform_vector(orientation, local),
            aabb=owner.get_aabb(),
        )

    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, ConvexPolygonSimpleLoft):
            return False
        x, y, z = owner._local_coords(point)
        if self.key == ExtrusionCap.TOP:
            return safe_equality_test(z, owner.top_points_z_pos, eps=test_tolerance)
        if self.key == ExtrusionCap.BOTTOM:
            return safe_equality_test(z, owner.bottom_points_z_pos, eps=test_tolerance)
        return owner._point_on_side(self.key, x, y, z, eps=test_tolerance)


class FeatureSource(Flag):
    """Which features a query is asking for.

    DEFAULTS are what a primitive names on its own, in FeatureKey slots.
    OVERRIDES are what an author handed it: a replacement for a default at the
    same key, or a feature at a slot no default occupies. BOTH is the answer to
    "what does this shape name", which is what nearly every caller wants.
    """

    DEFAULTS = 1
    OVERRIDES = 2
    BOTH = 3


#TODO this should an ABC? or is that not allowed for dual inheritance or osemtihng?
@dataclass(frozen=True)
class HasFeatures:
    """Storage for the features a primitive names on its own boundary.

    inherited Mixin for CutCSG deriving classes that name their own features
    """

    # named features overriding default features
    _features: Optional[List['CSGFeature']] = field(default=None, kw_only=True)

    # TODO should probably make this an abstract method, or... this overrides the CutCSG one or osemthing? plesae update the comment explaniing if that's the case
    def default_features(self) -> Dict['FeatureKey', 'CSGFeature']:
        """What this primitive names on its own, keyed by where it sits.

        Empty here: a shape opts in by overriding this. Whatever it returns
        must be in FeatureGroup.NONE -- see the note on default_features in
        RectangularPrism for why that matters more than it looks.
        """
        return {}

    def get_declared_features(
        self, source: 'FeatureSource' = FeatureSource.BOTH,
    ) -> List['CSGFeature']:
        """Features this node names on its own boundary, whether or not any
        point lies on them.
        """
        authored = list(self._features or ())
        if source is FeatureSource.OVERRIDES:
            return authored

        defaults = dict(self.default_features())
        if source is FeatureSource.DEFAULTS:
            return list(defaults.values())

        for feature in authored:
            key = feature.feature_key()
            if key is not None:
                defaults.pop(key, None)
        return authored + list(defaults.values())


@dataclass(frozen=True)
class OwnedFeatureHit:
    """A feature, paired with the primitive it belongs to
    """
    feature: CSGFeature
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

    def get_extent(self) -> Optional['CSGFeatureExtent']:
        return self.feature.get_extent(self.owner)


@dataclass(frozen=True)
class CutCSGLabel:
    """The name a CSG node carries, if anyone gave it one.
    """

    name: Optional[str] = None

    @staticmethod
    def NoLabel() -> 'CutCSGLabel':
        """The label of a node nobody named. The default for CutCSG.label."""
        return CutCSGLabel()

    def is_labeled(self) -> bool:
        """True if this node was given a name."""
        return self.name is not None

    def __bool__(self) -> bool:
        return self.is_labeled()

    def __repr__(self) -> str:
        return f"CutCSGLabel({self.name!r})" if self.name is not None else "NoLabel"


@dataclass(frozen=True)
class CutCSG(ABC):
    """Base class for all CSG operations."""
    label: CutCSGLabel = field(default_factory=CutCSGLabel.NoLabel, kw_only=True)

    @abstractmethod
    def __repr__(self) -> str:
        """String representation for debugging."""
        pass

    @classmethod
    def display_name(cls) -> str:
        """
        """
        return re.sub(r"(?<!^)(?=[A-Z])", " ", cls.__name__).lower()

    def get_declared_features(
        self, source: 'FeatureSource' = FeatureSource.BOTH,
    ) -> List[CSGFeature]:
        """Features this node names on its own boundary, whether or not any
        point lies on them.

        Empty by default, and it stays empty for the compound nodes: a
        SolidUnion, Difference or Intersection has no surface of its own to
        name, only the surfaces its children contribute.
        """
        return []

    def collect_feature_hits(
        self,
        point: V3,
        tolerances: FeatureTestTolerances,
    ) -> List['OwnedFeatureHit']:
        """collects every declared feature in this subtree that *point* lies on.

        Each feature is tested at the tolerance its own type calls for.

        Real and non-real features are gated differently:

        - A real feature names actual surface, so the point has to be on the
          boundary of THIS node.
        - A non-real feature (a bore's centre axis, a reference plane) names
          nothing the CSG tree ever cut, so boolean operations cannot have
          removed it and the gate does not apply.
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

    def find_all_features(
        self,
        point: V3,
        test_tolerances: Optional[FeatureTestTolerances] = None,
    ) -> List['OwnedFeatureHit']:
        """Every feature at *point*: those declared in this subtree, plus the
        edges and points they form with each other.

        
        
        Three gathers, because "near enough to count" means a different distance
        depending on what is being asked. The first collects features at the
        tolerance each one's type calls for. The second collects faces at the
        EDGE tolerance and pairs them, which is what makes an edge selectable
        from further away than either of its faces -- a face 1.5mm off cannot
        claim the point itself, but it can still form an edge that is
        selectable there, because you cannot click exactly on a line. The third
        does the same again at the POINT tolerance, which is wider still, and
        crosses the declared edges there with the faces.

        DECLARED edges only, in that last stage. A derived edge is in
        FeatureGroup.NONE and would be rejected anyway, but the reason it is not
        offered is the stronger one: a derived point is named by its two
        parents, and a parent that is itself derived has no name to be found
        again by, so the reference could never resolve.

        Derivation happens here rather than inside collect_feature_hits, and so runs
        once, at whichever node the caller asked about. Putting it in the
        recursive gather would either recurse into itself or have every nested
        compound re-derive what its parent derives.

        Derived duplicates come off at the end, once the ordering has settled
        which of them was the preferred way of naming the geometry.
        """
        tolerances = DEFAULT_FEATURE_TEST_TOLERANCES if test_tolerances is None else test_tolerances
        hits = self.collect_feature_hits(point, tolerances)

        def of_type(gathered, feature_type):
            return [hit for hit in gathered if hit.feature.feature_type() == feature_type]

        # One gather for both derivations, at the widest tolerance either of
        # them could want, since derived features are then asked directly
        # whether the point is on IT. Gathering narrower would only rule out
        # parents whose child is about to be asked a stricter question anyway.
        #
        # TODO two walks of the tree rather than one, because the gather above
        # also applies the boundary gate at `tolerances.face`, and widening the
        # tolerances here widens that with it. Separating "near the feature"
        # from "on the boundary" would let both derivations and the direct hits
        # come out of a single walk. Worth doing for the pick path, which runs
        # this per pointer move; not worth doing blind.
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

        return _drop_duplicate_derived(_sort_feature_hits(hits + derived_edges + derived_points))

    def find_first_feature(
        self,
        point: V3,
        test_tolerances: Optional[FeatureTestTolerances] = None,
    ) -> Optional['OwnedFeatureHit']:
        """The best feature at *point*, or None. Best is, in order:

        - a non-real feature before a real one;
        - the more specific kind: a point, then an edge, then a face;
        - a declared feature before a derived one;
        - the pairing group, best rank first;
        - author-set priority;
        - the name;
        - and last, the order they were gathered in.

        _sort_feature_hits holds the order and says why each step is where it
        is -- in particular why specificity sits above declaredness.
        """
        hits = self.find_all_features(point, test_tolerances=test_tolerances)
        if not hits:
            return None
        return _sort_feature_hits(hits)[0]


    @abstractmethod
    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is contained within the CSG object.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is inside or on the boundary of the CSG object, False otherwise
        """
        pass

    @abstractmethod
    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is on the boundary of the CSG object.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the CSG object, False otherwise
        """
        pass
    
    @abstractmethod
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        This method should only be called if is_point_on_boundary(point) is True.
        For points not on the boundary, behavior is undefined.
        
        Args:
            point: A point on the boundary (3x1 Matrix)
            
        Returns:
            The outward normal vector at the point, or None if cannot be determined
        """
        pass

    @abstractmethod
    def get_aabb(self) -> 'AxisAlignedBoundingBox':
        """
        Return the axis-aligned bounding box (AABB) of this CSG object.

        Each bound is Optional[Numeric] — None means unbounded in that direction.

        Primitives with infinite extent (HalfSpace, or prisms/cylinders with
        start_distance or end_distance set to None) cannot produce a finite AABB.
        They emit a UserWarning and return a AxisAlignedBoundingBox with all fields set to None.
        """
        pass


def csg_children(csg: CutCSG) -> List[CutCSG]:
    """The nodes directly beneath *csg*; empty for a primitive."""
    if isinstance(csg, SolidUnion):
        return list(csg.children)
    if isinstance(csg, Intersection):
        return [csg.left, csg.right]
    if isinstance(csg, Difference):
        return [csg.base, *csg.subtract]
    return []


class CSGParity(Enum):
    """Whether a node adds material to the finished solid or takes it away.

    ADDITIVE means growing that node grows the result; SUBTRACTIVE means
    growing it shrinks the result.
    """

    ADDITIVE = 0
    SUBTRACTIVE = 1

    def flipped(self) -> 'CSGParity':
        return CSGParity.SUBTRACTIVE if self is CSGParity.ADDITIVE else CSGParity.ADDITIVE


def csg_children_with_parity(
    csg: CutCSG,
    parity: CSGParity = CSGParity.ADDITIVE,
) -> List[Tuple[CutCSG, CSGParity]]:
    """The nodes directly beneath *csg*, each with its own parity.

    The one statement of the rule: a Difference's subtract children invert,
    and nothing else does.

    Children come back in csg_children order.
    """
    if isinstance(csg, Difference):
        flipped = parity.flipped()
        return [(csg.base, parity), *((sub, flipped) for sub in csg.subtract)]
    return [(child, parity) for child in csg_children(csg)]


def walk_csg_with_parity(
    root: CutCSG,
    parity: CSGParity = CSGParity.ADDITIVE,
) -> Iterator[Tuple[CutCSG, CSGParity]]:
    """Every node beneath *root*, including *root*, with its parity.
    """
    yield root, parity
    for child, child_parity in csg_children_with_parity(root, parity):
        yield from walk_csg_with_parity(child, child_parity)


@dataclass(frozen=True)
class EmptyCSG(CutCSG):
    """Represents an empty solid (contains no points)."""

    @classmethod
    def display_name(cls) -> str:
        return "empty"

    def __repr__(self) -> str:
        return "EmptyCSG()"

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


@dataclass(frozen=True)
class HalfSpace(HasFeatures, CutCSG):
    """
    An infinite half-plane defined by a normal vector and offset from origin.
    
    The half-plane includes all points P such that: P · normal >= offset    
    The offset represents the signed distance from the origin along the normal direction
    where the plane is located. Positive offset moves the plane in the direction of the normal.
    
    Args:
        normal: Normal vector pointing into the half-space (3x1 Matrix)
        offset: Distance from origin along normal direction where plane is located (default: 0)
    """

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Its one surface. See RectangularPrism.default_features for the group."""
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
    
    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is contained within the half-plane.
        
        A point P is in the half-plane if (P · normal) >= offset
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is in the half-plane (including boundary), False otherwise
        """
        # Compute dot product: point · normal
        dot_product = safe_dot_product(point, self.normal)
        return safe_compare(dot_product, self.offset, Comparison.GE, eps=eps)
    
    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is on the boundary of the half-plane.
        
        A point P is on the boundary if (P · normal) == offset
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary plane, False otherwise
        """
        # Compute dot product: point · normal
        dot_product = safe_dot_product(point, self.normal)
        # Use safe_zero_test to handle Float vs Integer comparison with tolerance
        return safe_zero_test(dot_product - self.offset, eps=eps)
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a HalfSpace, the outward normal is always the opposite of thenormal vector itself.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector (the HalfSpace's normal)
        """
        return -self.normal

    def get_aabb(self) -> AxisAlignedBoundingBox:
        warnings.warn(
            "get_aabb() called on HalfSpace, which has infinite extent — result is unbounded",
            UserWarning,
            stacklevel=2,
        )
        return AxisAlignedBoundingBox(None, None, None, None, None, None)

    
@dataclass(frozen=True)
class RectangularPrism(HasFeatures, CutCSG):
    """
    A prism with rectangular cross-section, optionally infinite in one or both ends.
    Note,they are parameterized similar to the Timber class which is atypical for such a primitive.
    
    The prism is defined by:
    - A transform (position and orientation in global coordinates)
    - A cross-section size (width (x-axis)) x height (y-axis)) in the local XY plane
    - Start and end distances along the local Z-axis from the position

    So the center point of the size cross section is at position and the timber extends out in -z by start_distance and +z by end_distance.
    
    Use None for start_distance or end_distance to make the prism infinite in that direction.
    
    The orientation matrix defines the local coordinate system where:
    - X-axis (first column) is the width direction (size[0])
    - Y-axis (second column) is the height direction (size[1])
    - Z-axis (third column) is the length/axis direction
    
    Args:
        size: Cross-section dimensions [width, height] (2x1 Matrix)
        transform: Transform (position and orientation) in global coordinates (default: identity)
        start_distance: Distance from position along Z-axis to start of prism (None = 
        -infinite)
        end_distance: Distance from position along Z-axis to end of prism (None = infinite)
    """

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:

        # Not static, though this one needs no instance: ConvexPolygonExtrusion
        # and ConvexPolygonSimpleLoft read their own shape to build theirs.
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

        # Through _canonical_arris_faces, so these are named the way timber.py
        # names the same arrises rather than in a second order of their own.
        sides = len(_PRISM_SIDE_ORDER)
        for index in range(sides):
            pair = _canonical_arris_faces(
                _PRISM_SIDE_ORDER[index], _PRISM_SIDE_ORDER[(index + 1) % sides])
            assert pair is not None, "consecutive sides meet in an arris"
            named((FeatureCategory.ARRIS, index),
                  lambda name, pair=pair: SimpleRectangularPrismEdgeFeature(
                      name=name, faces=pair, properties=_DEFAULT_FEATURE_PROPERTIES))
            for cap in (PrismFace.BOTTOM, PrismFace.TOP):
                ends = _canonical_arris_faces(cap, _PRISM_SIDE_ORDER[index])
                assert ends is not None, "a cap meets every side"
                named(arris_against_cap(index, sides, end=cap is PrismFace.TOP),
                      lambda name, ends=ends: SimpleRectangularPrismEdgeFeature(
                          name=name, faces=ends, properties=_DEFAULT_FEATURE_PROPERTIES))
        return features

    @classmethod
    def display_name(cls) -> str:
        return "prism"
    size: V2
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None  # starting distance of the prism in the direction of the +Z axis. None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # ending distance of the prism in the direction of the +Z axis. None means infinite in positive direction

    # Features this primitive names on its own boundary. Private: read it
    def get_bottom_position(self) -> V3:
        """
        Get the position of the bottom of the prism (at start_distance).
        Only valid for prisms with finite start_distance.
        
        Returns:
            The 3D position at the bottom of the prism
            
        Raises:
            ValueError: If start_distance is None (infinite prism)
        """
        if self.start_distance is None:
            raise ValueError("Cannot get bottom position of infinite prism (start_distance is None)")
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.start_distance]))
    
    def get_top_position(self) -> V3:
        """
        Get the position of the top of the prism (at end_distance).
        Only valid for prisms with finite end_distance.
        
        Returns:
            The 3D position at the top of the prism
            
        Raises:
            ValueError: If end_distance is None (infinite prism)
        """
        if self.end_distance is None:
            raise ValueError("Cannot get top position of infinite prism (end_distance is None)")
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.end_distance]))
    
    def __repr__(self) -> str:
        return (f"RectangularPrism(size={self.size.T}, transform={self.transform}, "
                f"start={self.start_distance}, end={self.end_distance})")
    
    def equals_prism(self, other: 'RectangularPrism') -> bool:
        """
        Check if this prism equals another prism.
        
        Uses SymPy's equals() method for numeric comparisons to handle symbolic values.
        
        Args:
            other: Another RectangularPrism to compare with
            
        Returns:
            True if all components are equal, False otherwise
        """
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
        """Return (width_dir, height_dir, length_dir) unit vectors in global coordinates."""
        m = self.transform.orientation.matrix
        width_dir = Matrix([m[0, 0], m[1, 0], m[2, 0]])
        height_dir = Matrix([m[0, 1], m[1, 1], m[2, 1]])
        length_dir = Matrix([m[0, 2], m[1, 2], m[2, 2]])
        return width_dir, height_dir, length_dir

    def _local_coords(self, point: V3) -> Tuple[Numeric, Numeric, Numeric]:
        """Project a global point onto this prism's local (width, height, length) axes."""
        local_point = point - self.transform.position
        width_dir, height_dir, length_dir = self._local_axes()
        x_coord = safe_dot_product(local_point, width_dir)
        y_coord = safe_dot_product(local_point, height_dir)
        z_coord = safe_dot_product(local_point, length_dir)
        return x_coord, y_coord, z_coord

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is contained within the prism.

        Args:
            point: Point to test (3x1 Matrix)

        Returns:
            True if the point is inside or on the boundary of the prism, False otherwise
        """
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
        """
        Check if a point is on the boundary of the prism.

        Args:
            point: Point to test (3x1 Matrix)

        Returns:
            True if the point is on the boundary of the prism, False otherwise
        """
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

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.

        Returns the normalized outward normal for the face that contains this point.
        If the point is on multiple faces (edge or corner), returns one of the normals.

        Args:
            point: A point on the boundary

        Returns:
            The outward normal vector at the point, or None if cannot be determined
        """
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
            return -length_dir  # Bottom face, normal points in -length direction (outward)
        if self.end_distance is not None and safe_equality_test(z_coord, self.end_distance, eps=eps):
            return length_dir  # Top face, normal points in +length direction (outward)

        # On width faces (right/left)
        if safe_equality_test(Abs(x_coord), half_width, eps=eps):
            if safe_compare(x_coord, 0, Comparison.GT, eps=eps):
                return width_dir  # Right face, normal points in +width direction
            else:
                return -width_dir  # Left face, normal points in -width direction

        # On height faces (front/back)
        if safe_equality_test(Abs(y_coord), half_height, eps=eps):
            if safe_compare(y_coord, 0, Comparison.GT, eps=eps):
                return height_dir  # Front face, normal points in +height direction
            else:
                return -height_dir  # Back face, normal points in -height direction

        # Should not reach here if point is actually on boundary
        return None

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


# UNUSED, but seems like a nice to have so keep it around
def make_finite_rectangular_prism_from_half_space(half_space: HalfSpace, size_of_space: Numeric, depth_of_space: Numeric) -> RectangularPrism:
    """
    Build a finite RectangularPrism that approximates ``half_space`` near its boundary.

    The returned prism:
    - has its "bottom" face (at start_distance = 0) lying on the half-space boundary plane,
    - extends ``depth_of_space`` into the half-space (in the +normal direction, i.e. the
      direction in which the half-space extends),
    - has a square cross-section of ``size_of_space`` × ``size_of_space`` centered on the
      point where the line through the origin along ``normal`` meets the boundary plane.

    The cross-section orientation perpendicular to the normal is chosen arbitrarily.
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
    """
    A cylinder with circular cross-section, optionally infinite in one or both ends.
    
    The cylinder is defined by:
    - A position (translation from origin)
    - An axis direction
    - A radius
    - Start and end distances along the axis from the position
    
    So the center point of the radius cross section is at position and the cylinder extends out in -z by start_distance and +z by end_distance.

    Use None for start_distance or end_distance to make the cylinder infinite in that direction.
    
    Args:
        axis_direction: Direction of the cylinder's axis (3x1 Matrix)
        radius: Radius of the cylinder
        position: Position of the cylinder origin in global coordinates (3x1 Matrix, default: origin)
        start_distance: Distance from position to start of cylinder (None = -infinite)
        end_distance: Distance from position to end of cylinder (None = infinite)
    """
    # TODO consider just making this a Transform object, even though we don't care about one of the DOFs
    axis_direction: Direction3D  # direction of the cylinder's axis, which is the +Z local axis
    radius: Numeric
    position: V3 = field(default_factory=lambda: Matrix([scalar(0), scalar(0), scalar(0)]))  # Position in global coordinates
    start_distance: Optional[Numeric] = None  # None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # None means infinite in positive direction

    # Features this primitive names on its own boundary. Private: read it
    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Two caps and the barrel
        """
        parts = ((START_CAP, CylinderPart.BOTTOM),
                 (END_CAP, CylinderPart.TOP),
                 ((FeatureCategory.SIDE, 0), CylinderPart.BARREL))
        return {
            key: SimpleCylinderFeature(name=default_feature_name(key), part=part,
                                       properties=_DEFAULT_FEATURE_PROPERTIES)
            for key, part in parts
        }

    def _axial_and_radial(self, point: V3) -> Tuple[Numeric, Numeric]:
        """Distance along the axis from `position`, and distance from the axis."""
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
        """
        Check if a point is contained within the cylinder.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is inside or on the boundary of the cylinder, False otherwise
        """
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
        """
        Check if a point is on the boundary of the cylinder.
        
        A point is on the boundary if it's either:
        1. On the cylindrical surface (at radius distance from axis)
        2. On one of the end caps (if finite)
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the cylinder, False otherwise
        """
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
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a cylinder, the normal depends on which surface the point is on.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector at the point
        """
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
                return radial_vector / radial_distance

        # Check if on end caps
        if self.start_distance is not None and safe_equality_test(axial_coord, self.start_distance, eps=eps):
            # Bottom cap, normal points in -axis direction (outward)
            return -axis
        if self.end_distance is not None and safe_equality_test(axial_coord, self.end_distance, eps=eps):
            # Top cap, normal points in +axis direction (outward)
            return axis

        # Should not reach here if point is on boundary
        return None

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


class SolidsAtPoint:
    """Where a point stands against a list of solids, worked out once.

    Each solid is asked twice -- does it hold the point, and is the point on
    its surface -- and every question below reads off that:

    - `any_holds`: does any of them hold the point at all?
    - `any_encloses`: does any hold it strictly inside, off its surface?
    - `any_on_surface`: does any have it on its surface?
    - `outward_normals`: which way does each of those surfaces face?
    - `average_outward_normal`: which way do they face together?
    - `close_around_it`: do they leave the point no way out?

    Every boolean node asked some of these of its children, each spelling out
    its own loop over contains_point and is_point_on_boundary.
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
        """Whether any of them has the point, on its surface or within."""
        return bool(self.holding)

    def any_encloses(self) -> bool:
        """Whether any holds the point strictly inside, off its surface."""
        return bool(self.enclosing)

    def any_on_surface(self) -> bool:
        return bool(self.on_surface)

    def outward_normals(self) -> List[Optional[Direction3D]]:
        """Each surface's outward normal at the point, in on_surface order."""
        return [solid.get_outward_normal(self.point, eps=self.eps)
                for solid in self.on_surface]

    def average_outward_normal(self, negated: bool = False) -> Optional[Direction3D]:
        """The mean of those normals, or None when they cancel or none can say.

        A mean rather than the first: this feeds the boundary tests through
        Difference, where averaging behaves better on non-convex corners.
        *negated* for the wall of a hole, whose outward faces into the material.
        """
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
        """Whether the surfaces meeting at the point leave no way out.

        A point can be on the boundary of every solid holding it and still be
        contained within what they make together: two prisms side by side share
        a face, and a point on that face is on the boundary of both solids but
        contained within the union. Asking each solid in turn never sees that.

        Analytic, not a step into space. Leaving every surface at once means a
        direction d with d . n > 0 for each outward normal n, so they close
        around the point exactly when no such direction exists. Exact for one
        surface and for two -- two close only when they face opposite ways --
        and a good-faith answer for more.

        False when any surface cannot say which way it faces: calling a real
        wall interior is the more damaging way to be wrong.
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


@dataclass(frozen=True)
class SolidUnion(CutCSG):
    """
    CSG union operation - combines multiple CSG objects.
    
    The union represents the set of all points that are in ANY of the child CSG objects.
    
    Args:
        children: List of CSG objects to union together
    """

    @classmethod
    def display_name(cls) -> str:
        return "union"
    children: List[CutCSG]

    def __repr__(self) -> str:
        return f"SolidUnion({len(self.children)} children)"
    
    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is contained within the union.
        
        A point is in the union if it's in ANY of the children.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is in any of the children, False otherwise
        """
        return any(child.contains_point(point, eps=eps) for child in self.children)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is on the boundary of the union.
        
        A point is on the boundary if it's on the boundary of at least one child
        and not in the interior of any other child.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the union, False otherwise
        """
        at = SolidsAtPoint(self.children, point, eps=eps)
        if not at.any_holds() or at.any_encloses():
            return False
        # Two children can share a face with neither holding the point inside,
        # and that face is the middle of the union rather than its surface.
        return at.any_on_surface() and not at.close_around_it()
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a union, we check all children that have the point on their boundary
        and return the average of their outward normals. The reason we do this is because this method is used to check if a point is on the boundary through Differences and using an average normal here tends to behave better on weird non-convex geometry.

        AVERAGED, so where several children meet at the point the answer
        bisects them and is perpendicular to none of them. Anything reading it
        as one surface's own normal is reading it wrong.

        Args:
            point: A point on the boundary

        Returns:
            The average outward normal vector, or None if cannot be determined
        """
        return SolidsAtPoint(self.children, point, eps=eps).average_outward_normal()

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
    """
    CSG intersection operation - keeps only points common to both child CSG objects.

    Args:
        left: First CSG object
        right: Second CSG object
    """
    left: CutCSG
    right: CutCSG

    def __repr__(self) -> str:
        return f"Intersection(left={self.left}, right={self.right})"

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        return self.left.contains_point(point, eps=eps) and self.right.contains_point(point, eps=eps)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        # Boundary of intersection = points in both solids that are on either boundary.
        if not self.contains_point(point, eps=eps):
            return False
        return self.left.is_point_on_boundary(point, eps=eps) or self.right.is_point_on_boundary(point, eps=eps)

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """The outward normal at a boundary point.

        AVERAGED where both sides meet at the point, as in SolidUnion and
        Difference: the answer then bisects them and is perpendicular to
        neither. Anything reading it as one surface's own normal is reading it
        wrong.
        """
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
    """
    CSG difference operation - subtracts multiple CSG objects from a base object.
    
    The difference represents: base - subtract[0] - subtract[1] - ...
    All points in base that are NOT in any of the subtract objects.
    
    Args:
        base: The base CSG object to subtract from
        subtract: List of CSG objects to subtract from the base
    """
    base: CutCSG
    subtract: List[CutCSG]

    def __repr__(self) -> str:
        return f"Difference(base={self.base}, subtract={len(self.subtract)} objects)"
    
    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is contained within the difference.
        
        A point is in the difference if it's in the base and NOT strictly inside any subtract object.
        Special case: if a point is on the boundary of both base and subtract, it's excluded.
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is in base but not in any subtract objects, False otherwise
        """
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
        """Whether a subtract's surface lies along the base's own, facing the
        same way, so the cut takes the very material that face was.

        True when a normal cannot be had, which excludes the point: the same
        conservative answer this has always given.
        """
        # TODO one normal from each side is not enough, and it now costs a real
        # surface. A normal at an edge or a corner is whichever face the shape
        # happened to check first, so where a cut's own corner sits on the
        # base's face both sides answer with the same prioritised face, this
        # calls the cut flush, and the face surrounding the cut is dropped --
        # see TestAFlushCutIsOnlyFlushWhereItIsFlat, which has the case waiting.
        #
        # It does not need a working normal on every shape to be worth fixing.
        # Knowing whether the point sits on a SMOOTH patch or on an edge is most
        # of the value: a point that is not smooth can refuse to claim flushness
        # and be right, whatever its normal says.
        base_normal = self.base.get_outward_normal(point, eps=eps)
        for sub_normal in removed.outward_normals():
            if base_normal is None or sub_normal is None:
                return True
            # TODO what were really wanting to chec khere is that the surfaces are the same locally which may not be the case if the normal was on an edge with this condition. To fix this you should introduce an is_on_edge function HOWEVER this also won't work in the case of stuff like cylinders, so to fix that you probably really need a surface_derivative (curvature) function...
            if safe_equality_test(safe_dot_product(base_normal, sub_normal), 1, eps=eps):
                return True
        return False

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is on the boundary of the difference.

        A point is on the boundary if it is in the difference at all and some
        surface passes through it: the base's own, or the wall of a hole.
        """
        if not self.contains_point(point, eps=eps):
            return False
        if self.base.is_point_on_boundary(point, eps=eps):
            return True
        return SolidsAtPoint(self.subtract, point, eps=eps).any_on_surface()

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a difference, if the point is on the boundary of the base CSG, return that normal.
        Otherwise, go through the subtract CSGs and return the average of their normals (negated).

        AVERAGED, so where several subtracts meet at the point the answer
        bisects them and is perpendicular to none of them. Anything reading it
        as one surface's own normal is reading it wrong.

        Args:
            point: A point on the boundary

        Returns:
            The outward normal vector, or None if cannot be determined
        """
        # If point is on base boundary, return base's normal
        if self.base.is_point_on_boundary(point, eps=eps):
            return self.base.get_outward_normal(point, eps=eps)
        
        # Otherwise, point must be on subtract boundary (creating a "hole")
        # The normal should point inward to the subtract (which is outward from the difference)
        # So we negate the subtract's outward normal
        return SolidsAtPoint(self.subtract, point, eps=eps).average_outward_normal(negated=True)

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
    """
    Translate a profile by a given translation vector.
    """
    return [point + translation for point in profile]

def translate_profiles(profiles: Profiles, translation: V2) -> Profiles:
    """
    Translate a list of profiles by a given translation vector.
    """
    return [translate_profile(profile, translation) for profile in profiles]


@dataclass(frozen=True)
class ConvexPolygonExtrusion(HasFeatures, CutCSG):
    """
    An extruded Convex Polygon shape, optionally infinite in one or both ends.
    
    The extrusion is defined by:
    - A list of ordered (x,y) points in the polygon (must be convex!)
    - A transform (position and orientation in global coordinates)
    - Start and end distances along the local Z-axis from the position
    
    The polygon is in the local XY plane at the position, and the extrusion extends
    out in -z by start_distance and +z by end_distance.
    
    Use None for start_distance or end_distance to make the extrusion infinite in that direction.
    
    Args:
        points: List of ordered (x,y) points in the polygon (last connects to first, must be convex)
        transform: Transform (position and orientation) in global coordinates (default: identity)
        start_distance: Distance from position along Z-axis to start of extrusion (None = -infinite)
        end_distance: Distance from position along Z-axis to end of extrusion (None = infinite)
    """

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Two caps and a side per edge of the profile.

        No arrises yet: SimpleRectangularPrismEdgeFeature is a prism's, and an
        extrusion needs its own before ARRIS n can be filled in here.
        """
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
        """
        Get the position of the bottom of the extrusion (at start_distance).
        Only valid for extrusions with finite start_distance.
        
        Returns:
            The 3D position at the bottom of the extrusion
            
        Raises:
            ValueError: If start_distance is None (infinite extrusion)
        """
        if self.start_distance is None:
            raise ValueError("Cannot get bottom position of infinite extrusion (start_distance is None)")
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.start_distance]))
    
    def get_top_position(self) -> V3:
        """
        Get the position of the top of the extrusion (at end_distance).
        Only valid for extrusions with finite end_distance.
        
        Returns:
            The 3D position at the top of the extrusion
            
        Raises:
            ValueError: If end_distance is None (infinite extrusion)
        """
        if self.end_distance is None:
            raise ValueError("Cannot get top position of infinite extrusion (end_distance is None)")
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.end_distance]))

    def __repr__(self) -> str:
        return (f"ConvexPolygonExtrusion({len(self.points)} points, "
                f"transform={self.transform}, start={self.start_distance}, end={self.end_distance})")
    
    def is_valid(self) -> bool:
        """
        Check if the ConvexPolygonExtrusion is valid
        
        Checks:
        1. At least 3 points
        2. Valid distance configuration (if both finite, end > start)
        3. Polygon is convex (all turns go the same direction)
        
        Returns:
            True if valid, False otherwise
        """
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

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is contained within the extruded polygon.
        
        A point is inside if:
        1. Its Z coordinate (in local space) is between start_distance and end_distance
        2. Its XY coordinates (in local space) are inside the convex polygon
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is inside or on the boundary, False otherwise
        """
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
        
        # Check if (x_coord, y_coord) is inside the convex polygon
        # For a convex polygon, a point is inside if it's on the correct side
        # of all edges
        point_2d = Matrix([x_coord, y_coord])
        
        for i in range(len(self.points)):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % len(self.points)]
            
            # Edge vector from p1 to p2
            edge = p2 - p1
            
            # Vector from p1 to test point
            to_point = point_2d - p1
            
            # Cross product in 2D: edge × to_point
            # If polygon vertices are ordered counter-clockwise, 
            # cross product should be >= 0 for point to be inside
            cross = edge[0] * to_point[1] - edge[1] * to_point[0]
            
            # Use safe_compare with tolerance to handle Float vs Integer comparisons
            if safe_compare(cross, 0, Comparison.LT, eps=eps):
                return False
        
        return True

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is on the boundary of the extruded polygon.
        
        A point is on the boundary if it's contained and either:
        1. On the top or bottom face (z = start_distance or z = end_distance, if finite)
        2. On one of the side faces (on an edge of the polygon)
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary, False otherwise
        """
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
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a convex polygon extrusion, the normal depends on which surface.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The outward normal vector at the point
        """
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
            return safe_transform_vector(self.transform.orientation.matrix, local_normal)

        # Check if on bottom face
        if self.start_distance is not None and safe_equality_test(z_coord, self.start_distance, eps=eps):
            # Bottom face, normal points in -Z direction in local coords
            local_normal = Matrix([scalar(0), scalar(0), scalar(-1)])
            return safe_transform_vector(self.transform.orientation.matrix, local_normal)

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
                    return safe_transform_vector(self.transform.orientation.matrix, local_normal)

        return None

    def _local_coords(self, point: V3) -> Tuple[Numeric, Numeric, Numeric]:
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        return local_coords[0], local_coords[1], local_coords[2]

    def _point_on_side(self, index: int, x: Numeric, y: Numeric, eps: Optional[Numeric] = None) -> bool:
        """Whether local (x, y) lies on the side face running from points[index]
        to points[(index+1) % len(points)]."""
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


#: How far out of plane a loft's side may sit before it counts as twisted, as a
#: fraction of that side's own size. Generous: it is separating a pure taper,
#: which is flat to float precision, from a rotation, which is off by tenths.
_SIDE_PLANARITY_EPSILON = scalar('1e-6')


@dataclass(frozen=True)
class ConvexPolygonSimpleLoft(HasFeatures, CutCSG):
    """
    A solid formed by straight-line lofting between two convex polygons in parallel
    planes, connected index-to-index (vertex i of bottom_points connects by a
    straight line to vertex i of top_points). Generalizes ConvexPolygonExtrusion
    to the case where the cross-section changes shape/size/offset along the length
    instead of staying constant -- ConvexPolygonExtrusion can be expressed where bottom_points == top_points (could probably be combined with this class but it doesn't relaly matter)


    bottom_points and top_points must each independently be a valid convex polygon
    (same rules as ConvexPolygonExtrusion.is_valid()) with the SAME number of points
    wound in the SAME direction.

    NO TWISTS. The correspondence between the two profiles must leave every side
    planar, which is_valid checks -- see _sides_are_planar. 

    The polygons live in the local XY plane, with bottom_points at bottom_points_z_pos
    and top_points at top_points_z_pos along the local Z-axis, matching the
    position/orientation conventions of RectangularPrism and ConvexPolygonExtrusion.
    Unlike those two, bottom_points_z_pos/top_points_z_pos must both be finite -- an
    infinite loft has no meaningful cross-section to loft towards.

    Args:
        bottom_points: convex polygon at bottom_points_z_pos (local XY plane)
        top_points: convex polygon at top_points_z_pos (local XY plane), same point
            count and winding direction as bottom_points
        bottom_points_z_pos: distance from position along Z-axis to bottom_points
        top_points_z_pos: distance from position along Z-axis to top_points
        transform: Transform (position and orientation) in global coordinates (default: identity)
    """

    def default_features(self) -> Dict[FeatureKey, CSGFeature]:
        """Two caps and a side per edge of the profile, as an extrusion has."""
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
        """Get the position of the bottom of the loft (at bottom_points_z_pos)."""
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.bottom_points_z_pos]))

    def get_top_position(self) -> V3:
        """Get the position of the top of the loft (at top_points_z_pos)."""
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.top_points_z_pos]))

    def __repr__(self) -> str:
        return (f"ConvexPolygonSimpleLoft({len(self.bottom_points)}->{len(self.top_points)} points, "
                f"transform={self.transform}, start={self.bottom_points_z_pos}, end={self.top_points_z_pos})")

    def is_valid(self) -> bool:
        """
        Check if the ConvexPolygonSimpleLoft is valid.

        Checks:
        1. bottom_points and top_points each have at least 3 points
        2. bottom_points and top_points have the same number of points
        3. top_points_z_pos > bottom_points_z_pos
        4. bottom_points and top_points are each individually convex
        5. every side comes out PLANAR -- see _sides_are_planar
        """
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
        """Whether every side comes out flat, rather than twisted into a saddle.

        A side joins bottom[i]-bottom[i+1] to top[i]-top[i+1] with straight
        lines, so it is a quadrilateral in space, and a quadrilateral is planar
        only when its four corners are coplanar.
        """
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
        """Project a global point onto this loft's local (x, y, z) axes."""
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        return local_coords[0], local_coords[1], local_coords[2]

    def _height_fraction(self, z_coord: Numeric) -> Numeric:
        """Fraction along the loft (0 at bottom_points_z_pos, 1 at top_points_z_pos) for a local Z coordinate."""
        return (z_coord - self.bottom_points_z_pos) / (self.top_points_z_pos - self.bottom_points_z_pos)

    def _cross_section_at(self, t: Numeric) -> Profile:
        """The (index-matched, linearly interpolated) polygon at height-fraction t."""
        return [bottom + (top - bottom) * t for bottom, top in zip(self.bottom_points, self.top_points)]

    def _point_on_side(self, index: int, x: Numeric, y: Numeric, z: Numeric,
                       eps: Optional[Numeric] = None) -> bool:
        """Whether local (x, y, z) lies on the ruled side face running from vertex
        *index* to vertex *index+1*.

        The side is a ruled surface, so this tests against the cross-section at
        the point's own height rather than against a fixed plane.
        """
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

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is contained within the loft.

        Args:
            point: Point to test (3x1 Matrix)

        Returns:
            True if the point is inside or on the boundary, False otherwise
        """
        x_coord, y_coord, z_coord = self._local_coords(point)

        if safe_compare(z_coord - self.bottom_points_z_pos, 0, Comparison.LT, eps=eps):
            return False
        if safe_compare(z_coord - self.top_points_z_pos, 0, Comparison.GT, eps=eps):
            return False

        cross_section = self._cross_section_at(self._height_fraction(z_coord))
        point_2d = Matrix([x_coord, y_coord])

        for i in range(len(cross_section)):
            p1 = cross_section[i]
            p2 = cross_section[(i + 1) % len(cross_section)]
            edge = p2 - p1
            to_point = point_2d - p1
            cross = edge[0] * to_point[1] - edge[1] * to_point[0]
            if safe_compare(cross, 0, Comparison.LT, eps=eps):
                return False

        return True

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is on the boundary of the loft.

        Args:
            point: Point to test (3x1 Matrix)

        Returns:
            True if the point is on the boundary, False otherwise
        """
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

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.

        Sides are checked for planar in is_valid so normals are constant across faces.

        Edges/vertices currentyl returns normals of one of its adjacent faces. NOTE we can consider making it average instead but there's no need right now.

        Args:
            point: A point on the boundary

        Returns:
            The outward normal vector at the point, or None if cannot be determined
        """
        x_coord, y_coord, z_coord = self._local_coords(point)

        if safe_zero_test(z_coord - self.top_points_z_pos, eps=eps):
            local_normal = Matrix([scalar(0), scalar(0), scalar(1)])
            return safe_transform_vector(self.transform.orientation.matrix, local_normal)

        if safe_zero_test(z_coord - self.bottom_points_z_pos, eps=eps):
            local_normal = Matrix([scalar(0), scalar(0), scalar(-1)])
            return safe_transform_vector(self.transform.orientation.matrix, local_normal)

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

            return safe_normalize_vector(safe_transform_vector(self.transform.orientation.matrix, local_normal))

        return None

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


# ============================================================================
# Polygon decomposition utility
# ============================================================================

def decompose_simple_polygon_into_convex_pieces(points: Profile) -> List[Profile]:
    """
    Decompose a simple (non-self-intersecting) polygon, given as an ordered
    list of (u, v) points, into convex quads/triangles whose union equals the
    polygon — via horizontal (constant-v) trapezoidal decomposition.

    See pathcsg.decompose_path_into_convex_pieces for the same algorithm
    generalized to a Path (lines + arcs): it sweeps directly over a Path's
    segments instead of a pre-tessellated point list, so the expensive
    exact-arithmetic part runs over the (small) segment count rather than
    however many points arc tessellation would otherwise produce. Not wired
    together with this function (would need pathcsg -> cutcsg -> pathcsg,
    which is circular) — kept as two independent implementations of the same
    sweep for now.

    Splits the polygon at every vertex's v-coordinate, and within each
    resulting v-band, finds every edge active there, sorts their u-crossings
    left to right, and pairs them up with the standard even-odd polygon-fill
    rule (1st-2nd pair is interior, 3rd-4th pair is interior, and so on).
    This handles overlapping v-ranges between edges correctly (unlike naively
    treating each edge as its own independent band), and degenerate edges
    that double back along another edge (contributing paired, zero-width
    crossings) simply cancel out.

    Args:
        points: Ordered polygon vertices (u, v), last connects back to first.
            v need not be monotonic along the boundary.

    Returns:
        List of convex pieces, each a Profile (quad or triangle) suitable for
        ConvexPolygonExtrusion.
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
    """
    Tighten a bounding box by removing the region inside ``hs``.

    Returns the AABB of the intersection of ``bbox`` with the complement of ``hs``
    (i.e., the set of points where ``hs.contains_point()`` is False).

    If any bound of ``bbox`` is None the box is returned unchanged, because
    we cannot enumerate the corners of an infinite box. An already-empty bbox
    is also returned unchanged (it has no corners to clip).
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
    """
    Return a copy of the CSG object translated by the given vector.

    Args:
        csg: The CSG object to translate
        translation: 3D translation vector (3x1 Matrix)

    Returns:
        A new CSG object with the same structure but translated by translation
    """
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
    """
    Transform a CSG object into another coordinate system.

    If orig_transform is provided, the CSG is treated as being in that transform's local
    coordinates. If orig_transform is None, the CSG is treated as being in global coordinates.
    If adopting_transform is provided, the result is expressed in that transform's local
    coordinates. If adopting_transform is None, the result is expressed in global coordinates.

    Args:
        orig_transform: The transform whose local space the CSG is in, or None for global
        adopting_transform: The transform whose local space we want the CSG in,
            or None to return the CSG in global coordinates
        csg_in_orig_space: The CSG object (in orig_transform local, or global if orig_transform is None)

    Returns:
        A new CSG object in adopting_transform's local coordinates, or in global
        coordinates if adopting_transform is None

    Example:
        >>> cut_on_b = adopt_csg(timber_a.transform, timber_b.transform, cut_csg)
        >>> csg_in_tenon_local = adopt_csg(None, tenon_timber.transform, csg_global)
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