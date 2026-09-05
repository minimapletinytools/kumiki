"""
CutCSG - Constructive Solid Geometry operations for Kumiki

This module provides CSG primitives and operations for representing timber cuts
and geometry operations. All operations use plain Python floats (see rule.py);
comparisons go through the safe_* helpers so they carry a tolerance rather than
testing for bit-exact equality.

The low-level point tests -- contains_point, is_point_on_boundary,
get_outward_normal -- take an optional ``eps`` that widens that tolerance for
the duration of the call.

The feature queries -- get_all_features, find_feature, and CSGFeature.
test_point -- take a *test tolerance* instead, which is a different thing
wearing similar clothes. An epsilon absorbs float error; a test tolerance
absorbs the gap between a raycast hit on the triangulated mesh and the
analytic surface it stands for, and how far a click lands from an edge or a
point it cannot hit exactly. See FeatureTestTolerances.
"""

import re
from typing import Callable, Iterator, List, Optional, Tuple, Union, cast
from dataclasses import dataclass, field, replace
from abc import ABC, abstractmethod
from enum import Enum
import warnings
from .rule import *
from .geometry import Line, Plane, Point, intersect_planes, planes_are_parallel


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


# TODO rename to AxisAlignedBoundingBox
@dataclass(frozen=True)
class BoundingBox:
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

class PrismFace(Enum):
    """Face of a RectangularPrism, indices match TimberFace."""
    TOP = 1
    BOTTOM = 2
    RIGHT = 3
    FRONT = 4
    LEFT = 5
    BACK = 6


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

    The three cases measurement cares about: measuring between two features
    dispatches on this pair (two parallel faces measure like two parallel
    planes, a point and a face measure a projected distance, and so on).

    Everything nameable on a primitive today is a FACE. EDGE arrives with
    features derived from intersecting face pairs; POINT with their vertices.
    """
    FACE = 1
    EDGE = 2
    POINT = 3


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
    """Whether a feature has to appear on a drawing."""

    OPTIONAL = 0
    ALWAYS_MARK = 1
    NEVER_MARK = 2


@dataclass(frozen=True)
class FeatureMarkingSpec:
    """How a feature should be marked, when that differs from the default.

    mark_relative_to names the feature a dimension should be measured from,
    which is how a drawing says "38mm from the shoulder" rather than giving an
    absolute position. None leaves that to whatever generates the drawing.
    """

    mark: FeatureMarkingStatus = FeatureMarkingStatus.OPTIONAL
    mark_relative_to: Optional[str] = None


class FeaturePurpose(Enum):
    """What purpose the feature serves."""

    NOT_SPECIFIED = 0
    ROUGH_RELIEF = 1


@dataclass(frozen=True)
class FeatureProperties:
    """Metadata every feature carries, independent of how it is identified.

    Args:
        group: which other features this one may form an edge with.
        priority: lower wins when several features claim the same point.
        real: False for a feature that names no actual surface (a bore's centre
            axis, a reference plane). Real features can be cropped away by the
            CSG tree and so are tested against the triangulated result first;
            non-real ones are unaffected by boolean operations.
        marking_override: how to mark this feature on a drawing, when the
            default for its kind is not what is wanted. None means the default.
        purpose: what the feature is for, where that is worth recording --
            relief geometry is not a feature of the joint the way a tenon
            cheek is.
    """

    group: FeatureGroup = FeatureGroup.A
    priority: int = 0
    real: bool = True
    marking_override: Optional[FeatureMarkingSpec] = None
    purpose: FeaturePurpose = FeaturePurpose.NOT_SPECIFIED


def _sort_feature_hits(hits: List['OwnedFeatureHit']) -> List['OwnedFeatureHit']:
    """Best answer first.

    Non-real beats real: selecting a centre axis is a deliberate snap, and a
    surface it happens to lie on should not steal the click. Then the more
    specific kind -- a point sits on an edge sits on a face, and the narrowest
    claimant is the better answer, so an edge beats the two faces that formed
    it. Then author-set priority.
    """
    return sorted(hits, key=lambda hit: (
        hit.feature.real,
        _FEATURE_TYPE_SPECIFICITY[hit.feature.feature_type()],
        hit.feature.priority,
    ))


def derive_edge_hits(
    owner: 'CutCSG',
    face_hits: List['OwnedFeatureHit'],
) -> List['OwnedFeatureHit']:
    """Every edge formed by a pair of *face_hits*, owned by *owner*.

    The pairs come from a scan run at the edge tolerance, so if two faces both
    turned up there, the conjunction that defines their edge holds at that
    tolerance by construction -- no further point testing needed. That is what
    makes this O(k^2) over the few faces near the point rather than over
    everything the subtree declares.

    Not deduplicated: derivation runs once, at whichever node the caller
    queried, so nothing arrives here twice. Names are not unique enough to
    dedupe by anyway -- two tenons on one timber legitimately declare the same
    face names, which makes their edges share a name while being genuinely
    different edges.
    """
    hits: List['OwnedFeatureHit'] = []
    for i in range(len(face_hits)):
        for j in range(i + 1, len(face_hits)):
            edge = DerivedEdgeFeature.derive(face_hits[i], face_hits[j])
            if edge is not None:
                hits.append(OwnedFeatureHit(feature=edge, owner=owner))
    return hits


def _drop_real_hits_off_boundary(
    node: 'CutCSG',
    hits: List['OwnedFeatureHit'],
    point: V3,
    test_tolerances: Optional['FeatureTestTolerances'],
) -> List['OwnedFeatureHit']:
    """Keep only what can legitimately be claimed at *point* on *node*.

    A child's real feature can name surface that this node's boolean removed --
    a base prism face inside a subtracted pocket, say -- so real hits survive
    only where the combined solid actually has boundary.

    Non-real features are exempt: they name nothing the boolean ever cut (a
    bore's centre axis lies in the void the bore made), so gating them on the
    combined boundary would make them unselectable, which is the opposite of
    what `real=False` is for.
    """
    if not hits:
        return hits
    if not any(hit.feature.real for hit in hits):
        return hits
    tolerances = DEFAULT_FEATURE_TEST_TOLERANCES if test_tolerances is None else test_tolerances
    if node.is_point_on_boundary(point, eps=tolerances.face):
        return hits
    return [hit for hit in hits if not hit.feature.real]


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
LocatedGeometry = Union[Point, Line, Plane]


@dataclass(frozen=True)
class CSGFeatureExtent:
    """Roughly where a feature is, for placing annotations against it.

    Separate from locate(): that gives the unbounded geometry a measurement is
    computed on, this says where to actually draw the thing. Approximate is
    fine -- a dimension line only needs somewhere sensible to attach.

    Args:
        anchor: a representative point -- a face's centre, an edge's midpoint,
            or the point itself.
        ends: for an edge, its two endpoints.
        aabb: for a face, a rough bounding box.
    """
    anchor: V3
    ends: Optional[Tuple[V3, V3]] = None
    aabb: Optional['BoundingBox'] = None


@dataclass(frozen=True)
class CSGFeature(ABC):
    """A named region of a CutCSG's boundary -- a face today, edges and points later.

    A feature is stored on the primitive it belongs to and does NOT hold a
    reference back to it: the owner is passed in to every method that needs
    geometry. That keeps a feature constructible before its owner exists (which
    it must be, to be passed to the owner's constructor) and means there is one
    feature type rather than a stored declaration plus a resolved copy.

    Because a feature alone does not know where it lives, queries hand back a
    OwnedFeatureHit pairing it with the primitive that matched.

    Subclasses say how the feature is identified: by an enum member for the
    simple per-primitive cases, or by an arbitrary predicate for
    ProgrammableCSGFeature.
    """
    name: str
    properties: FeatureProperties = field(default_factory=FeatureProperties)

    @abstractmethod
    def feature_type(self) -> CSGFeatureType:
        """What kind of geometry this feature names.

        A method rather than a field so it cannot be set to something the
        feature is not: a face feature has no way to claim it is an edge.
        Subclasses that name one kind by construction return a constant; only
        a feature whose kind genuinely varies stores one.

        Kept off FeatureProperties deliberately -- this says what the feature
        *is*, while properties say how it should be treated.
        """
        ...

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
        """The unbounded geometry this feature lies on, in the owner's space.

        A Plane for a planar face, a Line for an edge, a Point for a vertex.

        None when the feature names a surface that is not one of those -- a
        cylinder's barrel, a lofted side, an extrusion side that follows a
        curved path segment. Those are perfectly good features to select and
        highlight; there is just no single plane to measure against, so
        measurement has to decline rather than invent one.

        Note the space: the CSG tree is timber-local, so this is too. Anything
        comparing features across timbers has to lift both through the timber
        transform first.
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

    @property
    def real(self) -> bool:
        return self.properties.real

    @property
    def priority(self) -> int:
        return self.properties.priority

    @abstractmethod
    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        """Whether *point* lies on this feature of *owner*.

        Primitive level, and deliberately so: no root node is involved, so this
        cannot know what the rest of the tree did to *owner*. A face feature
        answers for the face's whole PLANE -- the bounding comes from the layer
        above.

        Which means this is half a test, and callers reach it through
        owner.get_all_features(), which has already established that the point
        is on the owner's boundary at all. Used on its own it says yes a long
        way from the feature: an edge built from two of these answers yes all
        the way along its line.
        """
        ...


@dataclass(frozen=True)
class ProgrammableCSGFeature(CSGFeature):
    """A feature identified by an arbitrary predicate rather than an enum member.

    The escape hatch for anything the simple per-primitive classes cannot name:
    a formula-defined region, half of a face, an edge derived from two other
    features. Works on any primitive, since the owner is just an argument.

    The predicate is called only for points already known to be on the owner's
    boundary, and receives the same eps the query was made with.
    """
    predicate: Optional[Callable[['CutCSG', V3, Optional[Numeric]], bool]] = None
    # The only class that stores its kind: a predicate can describe a face, an
    # edge or a point, so there is nothing constant to return.
    declared_type: CSGFeatureType = CSGFeatureType.FACE

    def feature_type(self) -> CSGFeatureType:
        return self.declared_type

    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if self.predicate is None:
            return False
        return self.predicate(owner, point, test_tolerance)


def _as_plane(geometry: Optional['LocatedGeometry']) -> Optional[Plane]:
    """Narrow a located geometry to a Plane, or None if it is not one.

    locate() can hand back a Point or a Line as well, and a face that declines
    to locate hands back nothing. Only planes intersect into edges.
    """
    return geometry if isinstance(geometry, Plane) else None


@dataclass(frozen=True)
class DerivedEdgeFeature(CSGFeature):
    """The edge where two face features meet.

    Built rather than authored: joints declare faces, and the edges between
    them fall out of which faces are allowed to meet (see FeatureGroup). Use
    `derive()` rather than constructing directly -- it applies the group rules,
    rejects pairs that form no edge, and names the result deterministically.

    The two parents generally live on different primitives (a tenon cheek and
    the timber body, say), so each is carried with its own owner. The `owner`
    passed to this feature's own methods is the compound node that contains
    both, and is unused here -- the geometry comes from the parents.
    """
    a: Optional['OwnedFeatureHit'] = None
    b: Optional['OwnedFeatureHit'] = None

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.EDGE

    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if self.a is None or self.b is None:
            return False
        return (self.a.feature.test_point(self.a.owner, point, test_tolerance)
                and self.b.feature.test_point(self.b.owner, point, test_tolerance))

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
        if self.a is None or self.b is None:
            return None
        # None if either parent is a surface with no plane -- a cylinder
        # barrel, a lofted side. The edge is still pickable; it just cannot be
        # measured against, the same decline locate() makes elsewhere.
        return intersect_planes(_as_plane(self.a.locate()), _as_plane(self.b.locate()))

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        """Where this edge sits -- only approximately, and deliberately so.

        `ends` is None and `anchor` is the point on the INFINITE line closest to
        the origin, which need not be anywhere near the stretch of edge that
        actually exists. Harmless for picking, which only calls test_point, and
        not good enough to hang a dimension line off.

        Measurement does the cropping instead, a level up where the enclosing
        timber is known -- this feature cannot see it, since its owner is
        whichever node derived it. See csgconvexhull.segment_on_line, called
        from the runner's _feature_anchor.
        """
        if self.a is None or self.b is None:
            return None
        line = self.locate(owner)
        if not isinstance(line, Line):
            return None
        return CSGFeatureExtent(anchor=line.point)

    @staticmethod
    def derive(a: 'OwnedFeatureHit', b: 'OwnedFeatureHit') -> Optional['DerivedEdgeFeature']:
        """The edge where *a* and *b* meet, or None if they form none.

        None when: either is not a face; their groups are not allowed to meet;
        or their planes are parallel (which includes being the same plane --
        coincident faces share a whole plane, not a line).
        """
        if a.feature.feature_type() != CSGFeatureType.FACE:
            return None
        if b.feature.feature_type() != CSGFeatureType.FACE:
            return None
        if not feature_groups_intersect(a.feature.group, b.feature.group):
            return None
        if planes_are_parallel(_as_plane(a.locate()), _as_plane(b.locate())):
            return None

        # Deterministic order, so the same edge gets the same identity however
        # traversal reached it.
        first, second = sorted(
            (a, b), key=lambda hit: (hit.feature.group.value, hit.feature.name))
        return DerivedEdgeFeature(
            name=f"{first.feature.name}\u00d7{second.feature.name}",
            properties=FeatureProperties(
                # An edge exists only where both its faces do.
                real=a.feature.real and b.feature.real,
                priority=max(a.feature.priority, b.feature.priority),
                # Groups govern which faces meet; nothing pairs edges yet, so
                # this is not meaningful for a derived edge and stays default.
            ),
            a=first,
            b=second,
        )


@dataclass(frozen=True)
class HalfSpaceFeature(CSGFeature):
    """The entire boundary plane of a HalfSpace.

    A half-space has exactly one face, so this needs no key to say which.
    """

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
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

    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        return owner.is_point_on_boundary(point, eps=test_tolerance)


@dataclass(frozen=True)
class SimpleRectangularPrismFeature(CSGFeature):
    """One of the six faces of a RectangularPrism, named by PrismFace."""
    face: PrismFace = PrismFace.TOP

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

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
        if not isinstance(owner, RectangularPrism):
            return None
        frame = self._face_frame(owner)
        if frame is None:
            return None
        normal, centre = frame
        return Plane(normal=normal, point=centre)

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        if not isinstance(owner, RectangularPrism):
            return None
        frame = self._face_frame(owner)
        if frame is None:
            return None
        _, centre = frame
        return CSGFeatureExtent(anchor=centre, aabb=owner.get_aabb())

    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
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
class SimpleRectangularPrismEdgeFeature(CSGFeature):
    """An arris of a RectangularPrism, named by the two faces it lies between.

    Declared rather than derived, which is the difference that matters. A
    derived edge exists only as the product of two face hits at a query point,
    so it cannot be referred to afterwards by name and its identity depends on
    both parents surviving. An arris a timber simply HAS is a thing to name
    once, and then to measure to for as long as the timber has it.

    The two faces must actually meet: opposite faces are parallel and share no
    line, and asking for that pair gets None from locate() rather than an
    invented answer.
    """

    faces: Tuple[PrismFace, PrismFace] = (PrismFace.FRONT, PrismFace.RIGHT)

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.EDGE

    def _sides(self) -> Tuple['SimpleRectangularPrismFeature', 'SimpleRectangularPrismFeature']:
        """The two faces as features, so their geometry is worked out once, there."""
        return (
            SimpleRectangularPrismFeature(name=self.name, face=self.faces[0]),
            SimpleRectangularPrismFeature(name=self.name, face=self.faces[1]),
        )

    def test_point(self, owner: 'CutCSG', point: V3,
                   test_tolerance: Optional[Numeric] = None) -> bool:
        first, second = self._sides()
        return (first.test_point(owner, point, test_tolerance)
                and second.test_point(owner, point, test_tolerance))

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
        """The line the two faces meet in, or None if they never do."""
        first, second = self._sides()
        return intersect_planes(_as_plane(first.locate(owner)), _as_plane(second.locate(owner)))

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        """Where the arris sits -- only approximately, as for a derived edge.

        `ends` is None and `anchor` is the point on the INFINITE line closest to
        the origin. Cropping it to the timber is measurement's job, a level up
        where the enclosing solid is known; see csgconvexhull.segment_on_line.
        """
        line = self.locate(owner)
        if not isinstance(line, Line):
            return None
        return CSGFeatureExtent(anchor=line.point)


@dataclass(frozen=True)
class SimpleCylinderFeature(CSGFeature):
    """One surface of a Cylinder: an end cap, or the barrel."""
    part: CylinderPart = CylinderPart.BARREL

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
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

    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
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

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
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

    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
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

    def feature_type(self) -> CSGFeatureType:
        return CSGFeatureType.FACE

    def locate(self, owner: 'CutCSG') -> Optional[LocatedGeometry]:
        if not isinstance(owner, ConvexPolygonSimpleLoft):
            return None
        # Only the caps are reliably planar. A side is a ruled surface, planar
        # only in the special case of a pure per-axis taper -- so decline
        # rather than return a plane that is right for some lofts and wrong
        # for others. Refining this to detect the planar case is worth doing
        # when something actually needs to measure from a tapered side.
        if self.key not in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            return None
        orientation = owner.transform.orientation.matrix
        length_dir = safe_transform_vector(orientation, Matrix([scalar(0), scalar(0), scalar(1)]))
        is_top = self.key == ExtrusionCap.TOP
        distance = owner.end_distance if is_top else owner.start_distance
        sign = scalar(1) if is_top else scalar(-1)
        return Plane(normal=length_dir * sign, point=owner.transform.position + length_dir * distance)

    def get_extent(self, owner: 'CutCSG') -> Optional[CSGFeatureExtent]:
        if not isinstance(owner, ConvexPolygonSimpleLoft):
            return None
        orientation = owner.transform.orientation.matrix
        if self.key in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            is_top = self.key == ExtrusionCap.TOP
            profile = owner.top_points if is_top else owner.bottom_points
            distance = owner.end_distance if is_top else owner.start_distance
        else:
            profile = [(b + t) / scalar(2) for b, t in zip(owner.bottom_points, owner.top_points)]
            distance = _finite_midpoint(owner.start_distance, owner.end_distance)
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

    def test_point(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, ConvexPolygonSimpleLoft):
            return False
        x, y, z = owner._local_coords(point)
        if self.key == ExtrusionCap.TOP:
            return safe_equality_test(z, owner.end_distance, eps=test_tolerance)
        if self.key == ExtrusionCap.BOTTOM:
            return safe_equality_test(z, owner.start_distance, eps=test_tolerance)
        return owner._point_on_side(self.key, x, y, z, eps=test_tolerance)


@dataclass(frozen=True)
class OwnedFeatureHit:
    """A feature, paired with the primitive it belongs to.

    A CSGFeature holds no reference to its owner, so anything handing one
    around carries both. That covers two jobs with the same shape: what a query
    hands back, and how a DerivedEdgeFeature refers to the two parents it was
    built from -- which generally live on different primitives.

    Anything needing the feature's geometry -- its plane, its extent -- needs
    the owner too, so `locate` and `get_extent` are forwarded here.
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

    def locate(self) -> Optional['LocatedGeometry']:
        return self.feature.locate(self.owner)

    def get_extent(self) -> Optional['CSGFeatureExtent']:
        return self.feature.get_extent(self.owner)


@dataclass(frozen=True)
class CutCSGLabel:
    """The name a CSG node carries, if anyone gave it one.

    A wrapper rather than a bare Optional[str] so that what a label carries can
    grow -- provenance, namespacing, whatever naming turns out to need -- without
    revisiting every node that constructs one.

    An unnamed node gets NoLabel() rather than None, so `csg.label` is always a
    CutCSGLabel and reading it never needs a None check first. Test for a name
    with the label's truthiness or is_labeled(); read it with `.name`.
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
        """What this kind of CSG is called where a person reads it.

        Derived from the class name -- "path extrusion" -- so a new CSG type
        names itself; subclasses override where a shorter word is the one
        people actually use ("union", not "solid union").

        Distinct from the class name, which stays the machine-readable kind:
        the viewer keys structural decisions off that and must not follow
        wording changes.
        """
        return re.sub(r"(?<!^)(?=[A-Z])", " ", cls.__name__).lower()

    def get_declared_features(self) -> List[CSGFeature]:
        """Features this node names on its own boundary, whether or not any
        point lies on them.

        Empty by default, and it stays empty for the compound nodes: a
        SolidUnion, Difference or Intersection has no surface of its own to
        name, only the surfaces its children contribute. Each primitive
        declares a private `_features` and overrides this to expose it.
        """
        return []

    def collect_hits(
        self,
        point: V3,
        tolerances: FeatureTestTolerances,
    ) -> List['OwnedFeatureHit']:
        """Every declared feature in this subtree that *point* lies on.

        Each feature is tested at the tolerance its own type calls for, right
        here -- a face at the face tolerance, a declared edge at the edge one.
        Compound nodes extend this over their children; they declare nothing
        themselves.

        Real and non-real features are gated differently, which is the whole
        reason `real` exists:

        - A real feature names actual surface, so the point has to be on the
          boundary of the primitive declaring it. That gate is a surface
          question, hence the face tolerance whatever the feature's own type.
        - A non-real feature (a bore's centre axis, a reference plane) names
          nothing the CSG tree ever cut, so boolean operations cannot have
          removed it and the gate does not apply.

        Takes a concrete FeatureTestTolerances, not an optional one: the
        defaulting happens once, at the public entry point, so nothing on the
        recursive path can quietly re-default.
        """
        declared = self.get_declared_features()
        if not declared:
            return []
        on_boundary: Optional[bool] = None  # computed at most once, only if needed
        hits: List['OwnedFeatureHit'] = []
        for feature in declared:
            if not feature.test_point(
                self, point, tolerances.for_type(feature.feature_type())
            ):
                continue
            if feature.real:
                if on_boundary is None:
                    on_boundary = self.is_point_on_boundary(point, eps=tolerances.face)
                if not on_boundary:
                    continue
            hits.append(OwnedFeatureHit(feature=feature, owner=self))
        return hits

    def get_all_features(
        self,
        point: V3,
        test_tolerances: Optional[FeatureTestTolerances] = None,
    ) -> List['OwnedFeatureHit']:
        """Every feature at *point*: those declared in this subtree, plus the
        edges they form with each other.

        TODO rename to find_all_features: this is a query at a point, not a
        listing, and the "get" reads like get_declared_features -- which is the
        one that does NOT include derived edges. The two get confused.

        Two gathers, because "near enough to count" means a different distance
        depending on what is being asked. The first collects features at the
        tolerance each one's type calls for. The second collects faces at the
        EDGE tolerance and pairs them, which is what makes an edge selectable
        from further away than either of its faces -- a face 1.5mm off cannot
        claim the point itself, but it can still form an edge that is
        selectable there, because you cannot click exactly on a line.

        Derivation happens here rather than inside collect_hits, and so runs
        once, at whichever node the caller asked about. Putting it in the
        recursive gather would either recurse into itself or have every nested
        compound re-derive what its parent derives.
        """
        tolerances = DEFAULT_FEATURE_TEST_TOLERANCES if test_tolerances is None else test_tolerances
        hits = self.collect_hits(point, tolerances)
        at_edge_tolerance = self.collect_hits(
            point, FeatureTestTolerances.uniform(tolerances.edge))
        faces = [
            hit for hit in at_edge_tolerance
            if hit.feature.feature_type() == CSGFeatureType.FACE
        ]
        return _sort_feature_hits(hits + derive_edge_hits(self, faces))

    def find_feature(
        self,
        point: V3,
        test_tolerances: Optional[FeatureTestTolerances] = None,
    ) -> Optional['OwnedFeatureHit']:
        """The best feature at *point*, or None.

        Non-real features win outright over real ones. They are lines and
        points inside or alongside the solid, so anything selecting one has
        deliberately snapped to it, and a surface it happens to sit on should
        not steal the click. Priority breaks ties within each of the two.
        """
        hits = self.get_all_features(point, test_tolerances=test_tolerances)
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
    def get_aabb(self) -> 'BoundingBox':
        """
        Return the axis-aligned bounding box (AABB) of this CSG object.

        Each bound is Optional[Numeric] — None means unbounded in that direction.

        Primitives with infinite extent (HalfSpace, or prisms/cylinders with
        start_distance or end_distance set to None) cannot produce a finite AABB.
        They emit a UserWarning and return a BoundingBox with all fields set to None.
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
    and nothing else does. A union's children are each monotone-increasing in
    the union, an intersection's operands in the intersection, and a
    Difference's base in the difference -- so those all inherit.

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

    Parity belongs to a node's POSITION, not to the node: a node has no parent
    pointer and cannot answer on its own, and the same subtree placed twice in
    one tree can have a different answer each time. So this yields one entry
    per occurrence and always starts from a root -- there is no way to ask a
    node about itself.

    Two subtract edges cancel: in ``A - (B - C)`` the C is ADDITIVE, and
    indeed C restores material that B removed.
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

    def get_aabb(self) -> 'BoundingBox':
        return BoundingBox(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=0,
            max_y=0,
            max_z=0,
            is_empty=True,
        )


@dataclass(frozen=True)
class HalfSpace(CutCSG):
    """
    An infinite half-plane defined by a normal vector and offset from origin.
    
    The half-plane includes all points P such that: P · normal >= offset    
    The offset represents the signed distance from the origin along the normal direction
    where the plane is located. Positive offset moves the plane in the direction of the normal.
    
    Args:
        normal: Normal vector pointing into the half-space (3x1 Matrix)
        offset: Distance from origin along normal direction where plane is located (default: 0)
    """

    @classmethod
    def display_name(cls) -> str:
        return "half-space"
    normal: Direction3D
    offset: Numeric = scalar(0)
    # Features this primitive names on its own boundary. Private: read it
    # through get_declared_features(), query it through get_all_features().
    _features: Optional[List[CSGFeature]] = field(default=None, kw_only=True)

    def get_declared_features(self) -> List[CSGFeature]:
        return list(self._features or ())

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

    def get_aabb(self) -> BoundingBox:
        warnings.warn(
            "get_aabb() called on HalfSpace, which has infinite extent — result is unbounded",
            UserWarning,
            stacklevel=2,
        )
        return BoundingBox(None, None, None, None, None, None)
@dataclass(frozen=True)
class RectangularPrism(CutCSG):
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

    @classmethod
    def display_name(cls) -> str:
        return "prism"
    size: V2
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None  # starting distance of the prism in the direction of the +Z axis. None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # ending distance of the prism in the direction of the +Z axis. None means infinite in positive direction

    # Features this primitive names on its own boundary. Private: read it
    # through get_declared_features(), query it through get_all_features().
    _features: Optional[List[CSGFeature]] = field(default=None, kw_only=True)

    def get_declared_features(self) -> List[CSGFeature]:
        return list(self._features or ())

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

        # TODO you should check if point is on edges and return averages instead

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

    def get_aabb(self) -> BoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite RectangularPrism — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return BoundingBox(None, None, None, None, None, None)

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
        return BoundingBox(
            _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
            _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
        )


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
class Cylinder(CutCSG):
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
    # through get_declared_features(), query it through get_all_features().
    _features: Optional[List[CSGFeature]] = field(default=None, kw_only=True)

    def get_declared_features(self) -> List[CSGFeature]:
        return list(self._features or ())

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

    def get_aabb(self) -> BoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite Cylinder — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return BoundingBox(None, None, None, None, None, None)

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

        return BoundingBox(
            bounds[0][0], bounds[1][0], bounds[2][0],
            bounds[0][1], bounds[1][1], bounds[2][1],
        )


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
        # Point must be contained in the union
        if not self.contains_point(point, eps=eps):
            return False
        
        # Check if on boundary of any child and not strictly inside all others
        on_any_boundary = False
        for child in self.children:
            if child.contains_point(point, eps=eps):
                if child.is_point_on_boundary(point, eps=eps):
                    on_any_boundary = True
                else:
                    # Point is strictly inside this child, so not on union boundary
                    return False
        
        return on_any_boundary
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a union, we check all children that have the point on their boundary
        and return the average of their outward normals. The reason we do this is because this method is used to check if a point is on the boundary through Differences and using an average normal here tends to behave better on weird non-convex geometry.
        
        Args:
            point: A point on the boundary
            
        Returns:
            The average outward normal vector, or None if cannot be determined
        """
        normals = []
        
        for child in self.children:
            if child.is_point_on_boundary(point, eps=eps):
                normal = child.get_outward_normal(point, eps=eps)
                if normal is not None:
                    normals.append(normal)
        
        if len(normals) == 0:
            return None
        elif len(normals) == 1:
            return normals[0]
        else:
            # Average the normals
            avg_normal = normals[0]
            for n in normals[1:]:
                avg_normal = avg_normal + n
            # Normalize
            norm = safe_norm(avg_normal)
            if safe_zero_test(norm, eps=eps):
                return None
            return avg_normal / norm

    def collect_hits(self, point: V3, tolerances: FeatureTestTolerances) -> List['OwnedFeatureHit']:
        hits = super().collect_hits(point, tolerances)
        for child in self.children:
            hits.extend(child.collect_hits(point, tolerances))
        # A child's face can be buried inside a sibling, which is surface the
        # union does not have. is_point_on_boundary rejects exactly that case.
        return _drop_real_hits_off_boundary(self, hits, point, tolerances)

    def get_aabb(self) -> BoundingBox:
        # Empty children contribute no points to the union, so they're excluded
        # before combining bounds — otherwise their degenerate zero-box would
        # incorrectly pull the union's bounds toward the origin.
        bboxes = [b for b in (child.get_aabb() for child in self.children) if not b.is_empty]
        if not bboxes:
            return BoundingBox(None, None, None, None, None, None, is_empty=True)

        def union_min(vals):
            if any(v is None for v in vals):
                return None
            return _numeric_min(*vals)

        def union_max(vals):
            if any(v is None for v in vals):
                return None
            return _numeric_max(*vals)

        return BoundingBox(
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
        left_on_boundary = self.left.is_point_on_boundary(point, eps=eps)
        right_on_boundary = self.right.is_point_on_boundary(point, eps=eps)

        if left_on_boundary and not right_on_boundary:
            return self.left.get_outward_normal(point, eps=eps)
        if right_on_boundary and not left_on_boundary:
            return self.right.get_outward_normal(point, eps=eps)

        if left_on_boundary and right_on_boundary:
            left_normal = self.left.get_outward_normal(point, eps=eps)
            right_normal = self.right.get_outward_normal(point, eps=eps)
            if left_normal is None:
                return right_normal
            if right_normal is None:
                return left_normal
            avg_normal = left_normal + right_normal
            norm = safe_norm(avg_normal)
            if safe_zero_test(norm, eps=eps):
                return left_normal
            return avg_normal / norm

        return None

    def collect_hits(self, point: V3, tolerances: FeatureTestTolerances) -> List['OwnedFeatureHit']:
        hits = super().collect_hits(point, tolerances)
        hits.extend(self.left.collect_hits(point, tolerances))
        hits.extend(self.right.collect_hits(point, tolerances))
        return _drop_real_hits_off_boundary(self, hits, point, tolerances)

    def get_aabb(self) -> BoundingBox:
        left_bbox = self.left.get_aabb()
        right_bbox = self.right.get_aabb()

        # If either side is empty, their intersection has no points either.
        if left_bbox.is_empty or right_bbox.is_empty:
            return BoundingBox(None, None, None, None, None, None, is_empty=True)

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

        return BoundingBox(
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
        # Point must be in base
        if not self.base.contains_point(point, eps=eps):
            return False
        
        # Check if on base boundary
        on_base_boundary = self.base.is_point_on_boundary(point, eps=eps)
        
        # Point must not be strictly inside any subtract object
        # If point is on boundary of both base and subtract, check normals
        for sub in self.subtract:
            if sub.contains_point(point, eps=eps):
                if not sub.is_point_on_boundary(point, eps=eps):
                    # Point is strictly inside a subtract object
                    return False
                elif on_base_boundary:
                    # Point is on boundary of both base and subtract
                    # Check the outward normals
                    base_normal = self.base.get_outward_normal(point, eps=eps)
                    sub_normal = sub.get_outward_normal(point, eps=eps)
                    
                    if base_normal is not None and sub_normal is not None:
                        # Compute dot product of normals
                        dot_product = safe_dot_product(base_normal, sub_normal)
                        
                        # If dot product == 1, surfaces overlap, exclude the point
                        # TODO what were really wanting to chec khere is that the surfaces are the same locally which may not be the case if the normal was on an edge with this condition. To fix this you should introduce an is_on_edge function HOWEVER this also won't work in the case of stuff like cylinders, so to fix that you probably really need a surface_derivative (curvature) function...
                        if safe_equality_test(dot_product, 1, eps=eps):
                            return False
                    else:
                        # Cannot determine normals, use conservative approach: exclude
                        return False
        
        return True

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        """
        Check if a point is on the boundary of the difference.
        
        A point is on the boundary if:
        1. It's contained in the difference (base - subtract), AND
        2. Either:
           a. It's on the boundary of the base, OR
           b. It's strictly inside the base but on the boundary of at least one subtract object
        
        Note: For case 2b, the point creates a new boundary surface (the "hole" surface).
        The point must be on the subtract boundary but NOT inside the subtract (i.e., on the
        surface of the hole facing the remaining material).
        
        Args:
            point: Point to test (3x1 Matrix)
            
        Returns:
            True if the point is on the boundary of the difference, False otherwise
        """
        # Point must be contained in base
        if not self.base.contains_point(point, eps=eps):
            return False
        
        # Check if point is in any subtract region (strictly inside, not just boundary)
        in_subtract_interior = False
        on_subtract_boundary = False
        
        for sub in self.subtract:
            if sub.contains_point(point, eps=eps):
                if sub.is_point_on_boundary(point, eps=eps):
                    on_subtract_boundary = True
                else:
                    # Point is strictly inside a subtract object
                    in_subtract_interior = True
                    break
        
        # If point is strictly inside any subtract, it's not on the difference boundary
        if in_subtract_interior:
            return False
        
        # If point is on subtract boundary, it's on the difference boundary
        if on_subtract_boundary:
            return True
        
        # Otherwise, check if it's on the base boundary
        return self.base.is_point_on_boundary(point, eps=eps)
    
    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        """
        Get the outward normal vector at a boundary point.
        
        For a difference, if the point is on the boundary of the base CSG, return that normal.
        Otherwise, go through the subtract CSGs and return the average of their normals (negated).
        
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
        normals = []
        for sub in self.subtract:
            if sub.is_point_on_boundary(point, eps=eps):
                normal = sub.get_outward_normal(point, eps=eps)
                if normal is not None:
                    # Negate because we want the normal pointing into the remaining material
                    normals.append(-normal)
        
        if len(normals) == 0:
            return None
        elif len(normals) == 1:
            return normals[0]
        else:
            # Average the normals
            avg_normal = normals[0]
            for n in normals[1:]:
                avg_normal = avg_normal + n
            # Normalize
            norm = safe_norm(avg_normal)
            if safe_zero_test(norm, eps=eps):
                return None
            return avg_normal / norm

    def collect_hits(self, point: V3, tolerances: FeatureTestTolerances) -> List['OwnedFeatureHit']:
        hits = super().collect_hits(point, tolerances)
        hits.extend(self.base.collect_hits(point, tolerances))
        for sub_csg in self.subtract:
            hits.extend(sub_csg.collect_hits(point, tolerances))
        return _drop_real_hits_off_boundary(self, hits, point, tolerances)

    def get_aabb(self) -> BoundingBox:
        bbox = self.base.get_aabb()
        if bbox.is_empty:
            return bbox
        for sub in self.subtract:
            if isinstance(sub, HalfSpace):
                bbox = _clip_bbox_by_halfspace_complement(bbox, sub)
        return bbox

# TODO come upw ith a cuter/better name for these
Profile = List[V2]
Profiles = List[Profile]

def crop_line_to_csg(
    line: Line,
    solid: CutCSG,
    search_extent: Numeric,
    samples: int = 256,
    eps: Optional[Numeric] = None,
) -> Optional[Tuple[V3, V3]]:
    """Clip an infinite *line* to the span of it that lies inside *solid*.

    Non-real features are unbounded by construction -- a bore's centre axis is
    an infinite line -- but drawing one has to stop somewhere, and the sensible
    somewhere is where it enters and leaves the timber. Note that this is the
    timber's UNCUT body: a bore is a void, so clipping the axis to the cut
    result would return nothing at all.

    Returns (entry, exit) in the same space as *line* and *solid*, or None if
    the line misses the solid entirely.

    Deliberately a free function rather than a method on the feature: the
    relevant solid is the enclosing timber, which a feature's owner (the bore
    primitive) knows nothing about. The caller supplies it.

    The span is found by sampling *samples* points across +/-*search_extent*
    about the line's origin and bisecting the two crossings. That is enough for
    the convex, axis-aligned cases this exists for; a line that enters and
    leaves a concave solid more than once reports only the outermost span.

    SUPERSEDED, flagged for removal. csgconvexhull.segment_on_line does this
    exactly, by half-space clipping rather than sampling: it takes several
    solids at once, starts near the timber instead of near the line's origin
    (which may be nowhere close), cannot step over an edge shorter than a
    sample spacing, and says None rather than guessing when a solid is one it
    cannot describe. Nothing in the library calls this any more -- only tests.

    The one thing it still does that segment_on_line cannot is handle a
    non-convex solid, since contains_point sees through a Difference where
    half-space clipping ignores subtractions. Remove this once segment_on_line
    accounts for those (see the note at the top of csgconvexhull).
    """
    direction = safe_normalize_vector(line.direction)

    def at(t: Numeric) -> V3:
        return line.point + direction * t

    step = (search_extent * scalar(2)) / scalar(samples)
    inside_ts = []
    for i in range(samples + 1):
        t = -search_extent + step * scalar(i)
        if solid.contains_point(at(t), eps=eps):
            inside_ts.append(t)
    if not inside_ts:
        return None

    def refine(outside: Numeric, inside: Numeric) -> Numeric:
        """Bisect toward the boundary between a known outside and inside t."""
        for _ in range(40):
            middle = (outside + inside) / scalar(2)
            if solid.contains_point(at(middle), eps=eps):
                inside = middle
            else:
                outside = middle
        return inside

    first, last = inside_ts[0], inside_ts[-1]
    entry_t = first if safe_compare(first, -search_extent, Comparison.LE) else refine(first - step, first)
    exit_t = last if safe_compare(last, search_extent, Comparison.GE) else refine(last + step, last)
    return at(entry_t), at(exit_t)


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
class ConvexPolygonExtrusion(CutCSG):
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

    @classmethod
    def display_name(cls) -> str:
        return "extrusion"
    points: Profile
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None  # starting distance in the direction of the -Z axis. None means infinite in negative direction
    end_distance: Optional[Numeric] = None    # ending distance in the direction of the +Z axis. None means infinite in positive direction

    # Features this primitive names on its own boundary. Private: read it
    # through get_declared_features(), query it through get_all_features().
    _features: Optional[List[CSGFeature]] = field(default=None, kw_only=True)

    def get_declared_features(self) -> List[CSGFeature]:
        return list(self._features or ())

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

    def get_aabb(self) -> BoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite ConvexPolygonExtrusion — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return BoundingBox(None, None, None, None, None, None)

        corners_global = [
            self.transform.local_to_global(Matrix([pt[0], pt[1], z]))
            for pt in self.points
            for z in (self.start_distance, self.end_distance)
        ]

        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]
        return BoundingBox(
            _numeric_min(*xs), _numeric_min(*ys), _numeric_min(*zs),
            _numeric_max(*xs), _numeric_max(*ys), _numeric_max(*zs),
        )


@dataclass(frozen=True)
class ConvexPolygonSimpleLoft(CutCSG):
    """
    A solid formed by straight-line lofting between two convex polygons in parallel
    planes, connected index-to-index (vertex i of bottom_points connects by a
    straight line to vertex i of top_points). Generalizes ConvexPolygonExtrusion
    to the case where the cross-section changes shape/size/offset along the length
    instead of staying constant -- ConvexPolygonExtrusion is the degenerate case
    where bottom_points == top_points.

    bottom_points and top_points must each independently be a valid convex polygon
    (same rules as ConvexPolygonExtrusion.is_valid()) with the SAME number of points
    wound in the SAME direction. Intermediate (lofted) cross-sections are NOT
    checked for convexity or simplicity -- if the correspondence between the two
    profiles is "twisted" enough (e.g. a profile rotated relative to the other),
    an intermediate cross-section can become non-convex or self-intersecting, which
    is undefined behavior for this primitive. This is safe for tapers/relief pockets
    where each vertex moves along a roughly-monotonic path (the common case for
    joinery), but this is NOT a general-purpose polygon morph.

    Side faces are ruled surfaces and are only planar in the special case where the
    taper is a pure independent per-axis scale from one profile to the other (e.g.
    a rectangle-to-rectangle taper on the same axes); get_outward_normal accounts
    for this and is not necessarily constant across a side face.

    The polygons live in the local XY plane, with bottom_points at start_distance
    and top_points at end_distance along the local Z-axis, matching the
    position/orientation conventions of RectangularPrism and ConvexPolygonExtrusion.
    Unlike those two, start_distance/end_distance must both be finite -- an
    infinite loft has no meaningful cross-section to loft towards.

    Args:
        bottom_points: convex polygon at start_distance (local XY plane)
        top_points: convex polygon at end_distance (local XY plane), same point
            count and winding direction as bottom_points
        start_distance: distance from position along Z-axis to bottom_points
        end_distance: distance from position along Z-axis to top_points
        transform: Transform (position and orientation) in global coordinates (default: identity)
    """

    @classmethod
    def display_name(cls) -> str:
        return "loft"
    bottom_points: Profile
    top_points: Profile
    start_distance: Numeric
    end_distance: Numeric
    transform: Transform = field(default_factory=Transform.identity)

    # Features this primitive names on its own boundary. Private: read it
    # through get_declared_features(), query it through get_all_features().
    _features: Optional[List[CSGFeature]] = field(default=None, kw_only=True)

    def get_declared_features(self) -> List[CSGFeature]:
        return list(self._features or ())

    def get_bottom_position(self) -> V3:
        """Get the position of the bottom of the loft (at start_distance)."""
        return self.transform.position - safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.start_distance]))

    def get_top_position(self) -> V3:
        """Get the position of the top of the loft (at end_distance)."""
        return self.transform.position + safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), self.end_distance]))

    def __repr__(self) -> str:
        return (f"ConvexPolygonSimpleLoft({len(self.bottom_points)}->{len(self.top_points)} points, "
                f"transform={self.transform}, start={self.start_distance}, end={self.end_distance})")

    def is_valid(self) -> bool:
        """
        Check if the ConvexPolygonSimpleLoft is valid.

        Checks:
        1. bottom_points and top_points each have at least 3 points
        2. bottom_points and top_points have the same number of points
        3. end_distance > start_distance
        4. bottom_points and top_points are each individually convex

        Does NOT check that intermediate (lofted) cross-sections stay convex or
        simple -- see class docstring.
        """
        if len(self.bottom_points) < 3 or len(self.top_points) < 3:
            return False
        if len(self.bottom_points) != len(self.top_points):
            return False
        if safe_compare(self.end_distance, self.start_distance, Comparison.LE):
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
        return bottom_winding is not None and bottom_winding == top_winding

    def _local_coords(self, point: V3) -> Tuple[Numeric, Numeric, Numeric]:
        """Project a global point onto this loft's local (x, y, z) axes."""
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        return local_coords[0], local_coords[1], local_coords[2]

    def _height_fraction(self, z_coord: Numeric) -> Numeric:
        """Fraction along the loft (0 at start_distance, 1 at end_distance) for a local Z coordinate."""
        return (z_coord - self.start_distance) / (self.end_distance - self.start_distance)

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

        if safe_compare(z_coord - self.start_distance, 0, Comparison.LT, eps=eps):
            return False
        if safe_compare(z_coord - self.end_distance, 0, Comparison.GT, eps=eps):
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

        if safe_zero_test(z_coord - self.start_distance, eps=eps):
            return True
        if safe_zero_test(z_coord - self.end_distance, eps=eps):
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

        For the top/bottom caps this is the (constant) local ±Z axis. For a side
        face, the face is in general a ruled (non-planar) surface, so the normal
        is computed from the face's parametric partial derivatives at this point
        rather than being constant across the face.

        Args:
            point: A point on the boundary

        Returns:
            The outward normal vector at the point, or None if cannot be determined
        """
        x_coord, y_coord, z_coord = self._local_coords(point)

        if safe_zero_test(z_coord - self.end_distance, eps=eps):
            local_normal = Matrix([scalar(0), scalar(0), scalar(1)])
            return safe_transform_vector(self.transform.orientation.matrix, local_normal)

        if safe_zero_test(z_coord - self.start_distance, eps=eps):
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
            length = self.end_distance - self.start_distance

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

    def get_aabb(self) -> BoundingBox:
        corners_global = (
            [self.transform.local_to_global(Matrix([pt[0], pt[1], self.start_distance])) for pt in self.bottom_points] +
            [self.transform.local_to_global(Matrix([pt[0], pt[1], self.end_distance])) for pt in self.top_points]
        )

        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]
        return BoundingBox(
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

def _clip_bbox_by_halfspace_complement(bbox: BoundingBox, hs: HalfSpace) -> BoundingBox:
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
        return BoundingBox(0, 0, 0, 0, 0, 0, is_empty=True)

    xs = [p[0] for p in valid_points]
    ys = [p[1] for p in valid_points]
    zs = [p[2] for p in valid_points]
    return BoundingBox(
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