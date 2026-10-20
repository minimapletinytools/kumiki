"""Picking: what a point or a ray on a cut timber lands on, and what to light for it.

Navigating a timber's CSG tree to the node under a click, the features there, the edges and
features a ray passes near, and the triangles of the rendered mesh that belong to a picked
node or feature. Geometry only: kigumi's runner turns the answers into wire forms.

Moved out of kigumi/runner.py, where it was written. Points and directions are Float3
(rule_at_home.py) rather than rule.py's V3 on the hot paths, since these run on every hover.
"""

import math
import warnings
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, TypedDict

from ..csg.cutcsg import CSGFeature, CutCSG, FeatureTestTolerances, OwnedFeatureHit
from ..csg.feature_paths import candidate_segments, label_name, walk_labels
from ..csg.feature_extent import Interval
from ..geometry import Line
from ..rule import Transform, V3, scalar
from ..timber import PerfectTimberWithin
from .rule_at_home import Float3, Rows3

#: A pointer's ray in timber-local space: origin, direction.
LocalRay = Tuple[Float3, Float3]


class WorldSegment(TypedDict):
    start: Float3
    end: Float3





def build_inv_transform_float(transform: 'Transform') -> Tuple[Rows3, Float3]:
    """Pre-compute float data for global→local.  Returns (rot_rows, position).
    local = R^T * (global - pos) where rot_rows is the FORWARD rotation matrix."""
    M = transform.orientation.matrix
    rot = tuple(Float3(float(M[r, 0]), float(M[r, 1]), float(M[r, 2])) for r in range(3))
    return rot, Float3.of(transform.position)  # type: ignore[return-value]


def inv_transform_point(rot: Rows3, pos: Float3, global_pt) -> Float3:
    """Apply inverse transform: local = R^T * (global_pt - pos)."""
    return inv_transform_direction(rot, Float3.of(global_pt) - pos)


def inv_transform_direction(rot: Rows3, global_dir) -> Float3:
    """Apply inverse transform to a DIRECTION: local = R^T * d, no translation.

    A direction has no position, so the offset that inv_transform_point applies
    would tilt it. Kept beside that one so the pair is read together.
    """
    d = Float3.of(global_dir)
    return Float3(rot[0][0]*d.x + rot[1][0]*d.y + rot[2][0]*d.z,
                  rot[0][1]*d.x + rot[1][1]*d.y + rot[2][1]*d.z,
                  rot[0][2]*d.x + rot[1][2]*d.y + rot[2][2]*d.z)


def subtree_contains(root: 'CutCSG', target: 'CutCSG') -> bool:
    """Whether *target* is *root* or somewhere beneath it.

    """
    from kumiki.csg.cutcsg import csg_children

    # note this is identity comparison, not quality as 2 CutCSGs can be `==` equivalent but not the same
    if root is target:
        return True
    return any(subtree_contains(child, target) for child in csg_children(root))


def to_v3(pt) -> 'V3':
    """Wrap a plain [x, y, z] in the V3 kumiki's CSG API expects."""
    return Float3.of(pt).v3()


def csg_contains_point(csg: 'CutCSG', local_pt: Float3, eps: float = 1e-4) -> bool:
    """True if *local_pt* (timber-local floats) is inside *csg*, within *eps*."""
    return csg.contains_point(to_v3(local_pt), eps)


def csg_point_on_boundary(csg: 'CutCSG', local_pt: Float3, eps: float = 1e-4) -> bool:
    """True if *local_pt* (timber-local floats) lies on the boundary of *csg*, within *eps*.

    These two are thin adapters over kumiki's own CutCSG methods. kigumi used to
    carry a parallel float reimplementation of both, from when kumiki was
    sympy-backed and a symbolic point test was too slow to run per raycast.
    kumiki is plain floats now, so the shadow copy bought nothing but drift --
    it covered only HalfSpace, RectangularPrism and Cylinder, which silently
    made every ConvexPolygonExtrusion, PathExtrusion, ConvexPolygonSimpleLoft
    and Intersection surface unselectable (the click fell through to the timber
    body and reported a bare "face").
    """
    return csg.is_point_on_boundary(to_v3(local_pt), eps)


# Timber-local outward directions, used to name an unnamed face by whichever of
# the timber's own six faces it most points toward.
TIMBER_LOCAL_FACE_NORMALS = (
    ("right", (1.0, 0.0, 0.0)), ("left", (-1.0, 0.0, 0.0)),
    ("front", (0.0, 1.0, 0.0)), ("back", (0.0, -1.0, 0.0)),
    ("top", (0.0, 0.0, 1.0)), ("bottom", (0.0, 0.0, -1.0)),
)


def nearest_timber_local_face_name(normal: Any) -> str:
    """Name an outward *normal* (in timber-local space) by the timber face it
    most closely points along.

    A CSG primitive often lives in its own local frame, unrelated to the
    timber's length axis -- a tenon's marking_space local Z points along
    whichever way the tenon protrudes, not the timber's own top/bottom. Someone
    browsing a timber's faces only ever wants an answer relative to THAT
    timber, so the answer is always reported in the timber's own six
    directions.
    """
    n = [float(normal[0]), float(normal[1]), float(normal[2])]
    best_name, best_dot = "face", -2.0
    for name, direction in TIMBER_LOCAL_FACE_NORMALS:
        dot = n[0] * direction[0] + n[1] * direction[1] + n[2] * direction[2]
        if dot > best_dot:
            best_dot, best_name = dot, name
    return best_name


def feature_at(csg: 'CutCSG', point: Any, eps: float) -> Optional['CSGFeature']:
    """The best feature at a point, preferring one somebody named.

    Two passes over the same hit list rather than find_first_feature, because the
    ranking wanted here is not the one find_first_feature applies: it sorts by how
    specific a feature is, and an anonymous default sits at the same
    specificity as the authored feature covering the same surface. Asking for
    the authored layer first says which of those two a person would rather
    read.

    Only real features: this names the surface at a point, and a non-real one (a centerplane
    passing through) is no surface. Named instead, it lit whatever triangles it crossed.
    """
    from kumiki.csg.cutcsg import FeatureSource, FeatureTestTolerances

    hits = [hit for hit in csg.find_all_features(point, FeatureTestTolerances(face=eps)) if hit.feature.real]
    if not hits:
        return None
    # By name: authored features are rebuilt on each call, and names are unique
    # within a primitive.
    authored = {
        feature.name
        for feature in csg.get_declared_features(FeatureSource.OVERRIDES)
    }
    for hit in hits:
        if not hit.feature.is_derived() and hit.feature.name in authored:
            return hit.feature
    return hits[0].feature


def describe_leaf_csg(csg: 'CutCSG', local_pt: Float3, eps: float = 1e-4) -> str:
    """What to call the part of primitive *csg* that *local_pt* lies on.

    A leaf's own account of itself: one primitive, one point, one string, and
    no tree. _describe_pick is the other half -- it walks from the root to say
    which joint made this node and which way the surface really faces, neither
    of which a primitive can know about itself. This one runs per triangle
    during highlight extraction, so it stays a lookup.

    Whatever names the point, preferring the name someone chose. An AUTHORED
    feature wins outright -- a prism built in its own local frame (a tenon's
    marking_space, say) has a "top" that is not the timber's top, so a name
    written on purpose beats anything worked out from geometry. Failing that,
    the primitive's own default: "side.0" says where the face is on the shape
    that has it, which is a true answer even if it is not a friendly one.

    Everything after that is a fallback for a shape that names nothing, and
    warns, because there should not be one. They are kept rather than removed
    so a gap shows up as a poor label rather than as a crash.

    WHAT THE FALLBACKS KNEW THAT THE DEFAULTS DO NOT. Each of them answered in
    terms of something outside the primitive: "cut_plane" says what a half
    space is FOR, "cylindrical_surface" says what shape the surface is, and the
    timber-local direction says where the face is on the TIMBER rather than on
    the little prism that happens to carry it. A default cannot say any of
    that -- "side.0" is true, and about the wrong frame of reference.

    Which is an argument for composing, not for choosing. The name says which
    surface; the outward normal, read in the timber's frame, says which way it
    faces. "side.0 (facing timber top)" carries both, and neither the feature
    nor the primitive is the right place to work that out -- only here is the
    timber in scope. Left undone deliberately; the shape of that string is a
    decision, not a detail.
    """
    from kumiki.csg.cutcsg import Cylinder, HalfSpace
    from kumiki.rule import are_vectors_perpendicular

    point = to_v3(local_pt)

    # The raycast tolerance is a surface tolerance: it covers the gap between
    # the analytic face and the triangulated mesh the ray actually hit. Edges
    # and points keep their (wider) defaults, since hitting one is a snap
    # rather than a direct hit.
    feature = feature_at(csg, point, eps)
    if feature is not None:
        return feature.name

    # Everything past here is a fallback, and every primitive names its own
    # boundary now, so reaching one means a shape whose default_features() is
    # still empty -- PathExtrusion, today. They are kept rather than deleted
    # because a gap should show up as a poor label rather than as a crash, and
    # they warn because a poor label is otherwise invisible.
    warnings.warn(
        f"No feature named the point on {type(csg).__name__}, so its label is "
        "being guessed. Every primitive should name its own boundary through "
        "default_features(); this one does not."
    )

    if isinstance(csg, HalfSpace):
        return "cut_plane"

    normal = csg.get_outward_normal(point, eps)
    if normal is None:
        return "unknown feature"

    # A barrel is not a face, and saying so beats calling it one. Unreachable
    # for a Cylinder as things stand, since a cylinder names its own barrel --
    # it is here for the shape that gains a curved side and no defaults.
    if isinstance(csg, Cylinder) and are_vectors_perpendicular(normal, csg.axis_direction):
        return "cylindrical_surface"

    return "unknown face feature"


def node_positions(root: 'CutCSG') -> Dict[int, Tuple[int, int, List[str]]]:
    from kumiki.csg.feature_paths import node_positions
    return node_positions(root)


def derived_feature_owner(root: 'CutCSG', derived: 'CSGFeature') -> Optional[Tuple[Any, List[str]]]:
    """Which node a derived edge or point is shown under, and its path.

    A plane-plane edge belongs to two CSGs at once -- the shoulder half-space
    and the timber body, say -- and a tree can only show it in one place. The
    rule is the deeper of its two parents, with document order breaking a tie.
    A derived point is the same shape of problem, an arris and a plane rather
    than two planes, and takes the same rule.

    That is sufficient for now: the features worth marking are the ones where
    joint geometry meets a timber face, and the timber body sits at the top of
    every tree, so the joint side is always deeper and always wins. One between
    two nodes at the same depth is not something the joint library produces
    today; when it does, this is the rule to revisit.
    """
    parents = [hit for hit in getattr(derived, "parents", ())
               if hit is not None]
    if len(parents) != 2:
        return None

    positions = node_positions(root)
    ranked = []
    for hit in parents:
        position = positions.get(id(hit.owner))
        if position is None:
            return None
        depth, order, path = position
        ranked.append(((depth, order), hit.owner, path))

    _rank, owner, path = max(ranked, key=lambda entry: entry[0])
    return owner, path


def edge_tolerance() -> float:
    """How close a vertex must be to an edge to count as on it.

    The same tolerance the edge was found with -- an edge is selected by
    snapping to it, so the highlight has to be as forgiving as the pick was.
    """
    from kumiki.csg.cutcsg import FEATURE_EDGE_TOLERANCE

    return FEATURE_EDGE_TOLERANCE


#: Floating point error: how far off the cut surface a declared edge may compute.
DECLARED_EDGE_FLOAT_NOISE = 1e-6


def cropped_edge_segments(
    edge_feature: 'CSGFeature',
    line: 'Line',
    timber: 'PerfectTimberWithin',
    root_csg: 'CutCSG',
    owner: Optional['CutCSG'] = None,
) -> Tuple[Optional[List[WorldSegment]], bool]:
    """The edge's line, clipped to where the edge actually exists.

    Returns (segments, absent). Each segment is a {"start", "end"} pair in world
    space, in order along the line; there is more than one when a cut crosses
    the middle of the edge and leaves a piece either side of it.

    `absent` says the line was cropped away to nothing, which is a real answer:
    the two planes cross somewhere that is not on either face. A mortise
    floor's plane run sideways meets the timber's side a foot away from the
    mortise, and that is not an edge of anything.

    Three conditions, all necessary, so all three are intersected:

      - the SURFACE is there. Not merely the material: an arris runs along the
        face of the piece and is never buried in the middle of it, so asking
        where there is wood keeps every stretch the line is swallowed by. A
        tenon's arris is the case -- the cutter that shaped it is extended back
        past the shoulder on purpose, and the shank is solid around it there,
        so a material test drew the arris carrying on down the timber.
      - both parent faces are there. A derived edge is where two faces MEET,
        and a face is bounded by the solid that declared it. Without this the
        line runs the length of the timber, since a mortise wall's plane
        carries on long after the mortise stops. Surface alone does not cover
        it: a mortise floor's plane meets the timber's own side a foot away,
        and that line is on the surface without being an edge of anything.
      - the feature says so itself. Exact, and free -- a prism's arris is a
        pair of its own corners and a derived edge reaches as far as both its
        faces do. _measure_span has asked this all along; an edge highlight
        did not, and so had nothing to hold the ends but a tolerant clip.

    The bounds are intersected as intervals rather than written as one CSG
    Intersection, because the first condition is about the surface of ONE solid
    and an intersection's surface includes the other's. Intersecting root with
    a parent made the parent's own face count as boundary, which is the whole
    length of the arris.
    """
    from kumiki.csg.feature_extent import declared_line_span, intersected_intervals
    from kumiki.csg.edges_on_csg import crop_line_to_crease_segments_on_csg, crop_line_to_segments_on_csg
    from kumiki.geometry import Line, unit_vector

    # Normalised first, because everything below measures along it in metres:
    # stations are compared against the edge tolerance and against what the
    # feature declares, and edges_on_csg parameterises by its own unit direction. A
    # Line does not promise that its direction is one.
    line = Line(direction=unit_vector(line.direction), point=line.point)

    near = timber.get_perfect_timber_within_csg_local().transform.position
    reach = float(timber.length) * 4
    station = lambda point: float(((point - line.point).T * line.direction)[0, 0])
    spans = lambda pieces: None if pieces is None else [
        tuple(sorted((station(piece.start), station(piece.end))))
        for piece in pieces
    ]

    # A derived edge is bounded by the two solids its parent faces belong to.
    # A declared one -- a timber's own arris -- belongs to a single primitive,
    # which is the owner it was found on.
    hits = list(getattr(edge_feature, "parents", (None, None)))
    parents = [
        hit.owner for hit in hits
        if hit is not None and getattr(hit, "owner", None) is not None
    ]
    derived = bool(parents)
    if not parents:
        parents = [owner] if owner is not None else []

    declared = declared_line_span(edge_feature, owner, line) if owner is not None else None

    def clipped(tolerance: float) -> Optional[List[Interval]]:
        # Where the surface creases along it: on the surface, and not a line through a flat face.
        found = spans(crop_line_to_crease_segments_on_csg(
            line, root_csg, seed_reach=reach, near=near, tolerance=tolerance))
        if found is None:
            return None
        bounds = []
        if declared is not None:
            # Widened with everything else: a derived edge found by a tolerant
            # test has parents whose corners are that far from its line, so an
            # unwidened declared span would undo the fallback it is part of.
            bounds.append([(declared[0] - tolerance, declared[1] + tolerance)])
        for parent in parents:
            within = spans(crop_line_to_segments_on_csg(
                line, parent, seed_reach=reach, near=near, tolerance=tolerance))
            if within is None:
                return None
            bounds.append(within)
        for bound in bounds:
            found = intersected_intervals(found, bound)
        return found

    # Two questions, one number, and only one of them wants it.
    #
    # WHETHER the edge is there needs the tolerance it was found by: two faces
    # count as meeting within that distance, so a real edge's line can sit a
    # fraction outside the solids that formed it and clip away to nothing.
    #
    # HOW FAR it runs does not. Widening the bounds to answer the first question
    # also pushed both ends out by that tolerance, so every edge was drawn long
    # at each end -- a fifth again on a 19mm arris.
    #
    # So take the exact spans where there are any, and fall back to the tolerant
    # ones only for the edge that exact clipping loses entirely.
    #
    # Only a DERIVED edge, though. The tolerance belongs to how that edge was
    # found -- two faces counted as meeting because they came within it -- and a
    # declared arris was not found that way at all: its line is the primitive's
    # own corners and sits exactly where it says. Widening for one anyway
    # resurrected stretches the exact reading had correctly called absent, which
    # is how a bore's end arris came back as a 6mm stub floating off the piece.
    #
    # The declared-edge retry is for FLOATING POINT ERROR only, not tolerance: off
    # axis, an arris lying exactly on the cut surface (a cross lap's inside edge on
    # a pitched rafter) computes a few nanometres off it and clips away entirely.
    # TODO consider one clip at DECLARED_EDGE_FLOAT_NOISE for declared edges instead
    # of exact-then-retry: simpler, at the cost of padding every end by a micron.
    cropped = clipped(0.0)
    if not cropped:
        cropped = clipped(float(edge_tolerance()) if derived else DECLARED_EDGE_FLOAT_NOISE)
    if cropped is None:
        # A solid it cannot describe: no answer, rather than a wrong one.
        return (None, False)
    if not cropped:
        return (None, True)

    at = lambda reached: timber.transform.local_to_global(
        line.point + line.direction * float(reached))
    return ([
        {
            "start": Float3.of(at(low)),
            "end": Float3.of(at(high)),
        }
        for low, high in cropped
    ], False)


def edge_highlight_segments(
    edge_feature: 'CSGFeature',
    owner: 'CutCSG',
    timber: 'PerfectTimberWithin',
    root_csg: 'CutCSG',
) -> Tuple[Optional[List[WorldSegment]], bool]:
    """Where a selected edge runs, in world space, and whether it is there at all.

    An edge is a line, and a highlight built out of triangles can only ever
    approximate one -- it lights the strip beside it, which reads as a stray
    wedge rather than as the edge. The viewer draws lines instead, and this says
    where they run.

    Cropped from the CSG, because asking the edge where it is does not bound
    it: a face feature's test_point_unbounded checks the face's PLANE and nothing
    so an edge made of two of them answers yes all the way along its line --
    a metre past the joint that formed it. Picking never noticed, since a
    click is one point that is on the timber anyway.

    A list, because a cut through the middle of an edge leaves a piece either
    side of it. None when the tree holds a primitive edges_on_csg cannot
    describe, and the caller falls back to lighting triangles.

    The second return says the edge was cropped away entirely. The caller wants
    that separately: with no line to draw it would otherwise light the triangles
    beside the edge instead, and those are found by the same unbounded test.
    """
    from kumiki.geometry import Line

    line = edge_feature.locate_simple_unbounded(owner)
    if timber is None or root_csg is None or not isinstance(line, Line):
        return (None, False)
    if not edge_feature.real:
        return (non_real_highlight_segments(edge_feature, owner, timber), False)
    return cropped_edge_segments(edge_feature, line, timber, root_csg, owner)


def non_real_highlight_segments(
    feature: 'CSGFeature', owner: 'CutCSG', timber: 'PerfectTimberWithin',
) -> Optional[List[WorldSegment]]:
    """Where a non-real feature is drawn: its own extent, in world space.

    NOT cropped to the cut solid the way a real edge is. A bore's axis lies in
    the void the bore made, so clipping it to what the cuts left finds no
    boundary anywhere along it and reports the whole feature absent -- which is
    a selected peg hole axis with no line to draw.

    Its own extent is the right bound and an exact one: a cylinder's axis runs
    between the cylinder's own two ends, which are the depth that was drilled.
    The uncut body would bound it as well (see D5 in the feature-selection plan)
    and is the fallback if something ever declares a non-real feature that
    reaches past the piece; nothing does, and the clip is not free on a hover.
    """
    extent = feature.get_extent(owner)
    if extent is None or extent.ends is None:
        return None
    to_world = lambda point: Float3.of(timber.transform.local_to_global(point))
    return [{"start": to_world(extent.ends[0]), "end": to_world(extent.ends[1])}]


def features_at_point(
    root: 'CutCSG', local_pt: Float3, eps: float, tolerances: Optional['FeatureTestTolerances'] = None,
    local_ray: Optional[LocalRay] = None,
) -> List['OwnedFeatureHit']:
    """Every feature the whole tree sees at the click, best first. The whole tree, since a derived
    edge needs both its faces in scope.

    With a ray, the slack is in screen pixels across the view:
    - edges and corners are gathered from further along the face (SLANT_REACH), then kept only
      within their slack of the ray;
    - a reference plane is taken where its line across the face is within the edge slack;
    - features in a void, like a bore's axis, are found along the ray (non_real_features_along_ray).
    """
    from dataclasses import replace

    from kumiki.csg.cutcsg import FeatureTestTolerances, _sort_feature_hits

    resolved = tolerances or FeatureTestTolerances(face=eps)
    if local_ray is None:
        return _only_creases(root, root.find_all_features(to_v3(local_pt), resolved), local_pt)
    origin, direction = Float3.of(local_ray[0]), Float3.of(local_ray[1]).unit()
    if direction is None:
        return _only_creases(root, root.find_all_features(to_v3(local_pt), resolved), local_pt)
    wide = replace(resolved, edge=float(resolved.edge) * SLANT_REACH,
                   point=float(resolved.point or resolved.edge) * SLANT_REACH)
    gathered = _only_creases(root, root.find_all_features(to_v3(local_pt), wide), local_pt)
    hits = [hit for hit in gathered if _within_slack(hit, origin, direction, resolved)]
    known = {_hit_key(hit) for hit in hits}
    planes = [hit for hit in _reference_planes_near(root, Float3.of(local_pt), origin, direction, float(resolved.edge))
              if _hit_key(hit) not in known]
    hits = _sort_feature_hits(hits + planes) if planes else hits
    return merge_ray_hits(root, hits, local_ray, resolved)


#: How much further than its slack a 3D pick looks for an edge or a corner along the face it struck,
#: before keeping those within the slack across the view: a face at 70 degrees to the view.
SLANT_REACH = 3.0


def _within_slack(hit: 'OwnedFeatureHit', origin: Float3, direction: Float3,
                  tolerances: 'FeatureTestTolerances') -> bool:
    """Whether an edge or corner comes within its slack of the ray, across the view; anything else,
    and a line along the ray, is not asked."""
    from kumiki.csg.cutcsg import CSGFeatureType

    exact = _nearest_on(hit, origin, direction)
    if exact is None:
        return True
    offset = exact - origin
    across = offset - direction * offset.dot(direction)
    slack = tolerances.point if hit.feature.feature_type() is CSGFeatureType.POINT else tolerances.edge
    return math.sqrt(across.dot(across)) <= float(slack or tolerances.edge)


def _reference_planes_near(root: 'CutCSG', point: Float3, origin: Float3, direction: Float3,
                           tolerance: float) -> List['OwnedFeatureHit']:
    """The non-real planes declared in `root` whose line across the surface at `point` -- where each
    crosses the face struck there -- comes within `tolerance` of the ray, across the view."""
    from kumiki.csg.cutcsg import OwnedFeatureHit, csg_children
    from kumiki.geometry import Plane

    facing = root.get_outward_normal(point.v3())
    surface = Float3.of(facing).unit() if facing is not None else None
    found: List['OwnedFeatureHit'] = []

    def near(plane: Plane) -> bool:
        normal = Float3.of(plane.normal).unit()
        if normal is None:
            return False
        gap = normal.dot(point - Float3.of(plane.point))
        trace = normal.cross(surface).unit() if surface is not None else None
        if surface is None or trace is None:
            return abs(gap) <= tolerance  # no face to cross, or parallel to it: by distance alone
        toward = surface.cross(trace)  # in the face, square to the trace
        step = -gap / normal.dot(toward)
        if abs(step) > tolerance * SLANT_REACH:
            return False
        on_trace = point + toward * step
        across_trace = trace.dot(direction)
        if abs(across_trace) > 1 - 1e-12:
            nearest = on_trace
        else:
            to_origin = origin - on_trace
            along = (to_origin.dot(trace) - across_trace * to_origin.dot(direction)) / (1 - across_trace * across_trace)
            nearest = on_trace + trace * along
        offset = nearest - origin
        across = offset - direction * offset.dot(direction)
        return math.sqrt(across.dot(across)) <= tolerance

    def walk(node: 'CutCSG') -> None:
        for feature in node.get_declared_features():
            if feature.real:
                continue
            plane = feature.locate_simple_unbounded(node)
            if isinstance(plane, Plane) and near(plane):
                found.append(OwnedFeatureHit(feature=feature, owner=node))
        for child in csg_children(node):
            walk(child)

    walk(root)
    return found


def _only_creases(root: 'CutCSG', hits: List['OwnedFeatureHit'], point: Any) -> List['OwnedFeatureHit']:
    """`hits` without a real edge whose line, where the pointer is, only runs through a flat face:
    a line on the surface that is no edge of it (edges_on_csg.is_crease_at) -- a relief's copy of another
    timber's arris, flush in this one's face."""
    from kumiki.csg.cutcsg import CSGFeatureType
    from kumiki.csg.edges_on_csg import is_crease_at
    from kumiki.geometry import Line, unit_vector

    at = Float3.of(point)

    def keep(hit: 'OwnedFeatureHit') -> bool:
        if not hit.feature.real or hit.feature.feature_type() is not CSGFeatureType.EDGE:
            return True
        line = hit.feature.locate_simple_unbounded(hit.owner)
        if not isinstance(line, Line):
            return True
        run = Float3.of(unit_vector(line.direction))
        start = Float3.of(line.point)
        foot = start + run * (at - start).dot(run)
        return is_crease_at(line, root, foot.v3())

    return [hit for hit in hits if keep(hit)]


class PointerCandidate(NamedTuple):
    """A feature under the pointer in a drawing's view: where along the ray it was found, and
    the depth group it is in (see order_along_ray), named by the depth the group starts at."""
    hit: 'OwnedFeatureHit'
    place: Optional[Float3]
    depth: float
    group: float


def candidates_under_pointer(
    root: 'CutCSG', local_pt: Optional[Float3], tolerances: 'FeatureTestTolerances', local_ray: LocalRay,
    timber: Optional['PerfectTimberWithin'] = None,
) -> List[PointerCandidate]:
    """What is under the pointer, for a drawing's view: the features at the surface the ray meets
    (`local_pt`, None where it meets none of this solid), and those on no surface the ray passes near
    (a bore's axis) -- only what the view can measure (measurable_in_view), nearest first
    (order_along_ray).

    Nothing deeper than the surface: what is behind it is hidden, and is not offered. An edge on a
    silhouette is found from the side its own surface is on; a point on a surface flush with
    another member's is found from either, each member being asked at the one surface point. With
    `timber`, a non-real plane seen edge-on is found along the ray too, whatever surface the ray meets
    (non_real_features_along_ray)."""
    local_pt = Float3.of(local_pt) if local_pt is not None else None
    hits = _only_creases(root, root.find_all_features(local_pt.v3(), tolerances), local_pt) if local_pt is not None else []
    origin, direction = Float3.of(local_ray[0]), Float3.of(local_ray[1]).unit()
    if direction is None:
        return [PointerCandidate(hit, local_pt, 0.0, 0.0) for hit in hits]
    found: Dict[Tuple, Tuple[float, Float3]] = {}

    def found_at(at_place: List['OwnedFeatureHit'], place: Float3) -> None:
        along = _along_ray(origin, direction, place)
        for hit in at_place:
            key = _hit_key(hit)
            if key not in found or along < found[key][0]:
                found[key] = (along, place)

    if local_pt is not None:
        found_at(hits, local_pt)
    hits = merge_ray_hits(root, hits, local_ray, tolerances, timber)
    for hit in hits:
        if _hit_key(hit) not in found:
            # Non-real, in a void: as deep as its nearest approach to the ray.
            extent = hit.feature.get_extent(hit.owner)
            if extent is not None and extent.ends is not None:
                nearest = ray_nears_segment(
                    origin, direction, (Float3.of(extent.ends[0]), Float3.of(extent.ends[1])), math.inf)
                if nearest is not None:
                    found_at([hit], nearest)
            elif timber is not None:
                on_ray = _plane_on_ray(hit, root, timber, origin, direction, math.inf)
                if on_ray is not None:
                    found_at([hit], on_ray)
    # An edge or corner is placed on itself, where it comes nearest the pointer: it was found
    # where the ray crossed some face, which can be a pixel off it. And it is offered only within
    # its slack of the pointer ACROSS the view -- screen pixels, the viewer's tolerances -- however
    # near the point it was found at.
    within: List['OwnedFeatureHit'] = []
    for hit in hits:
        key = _hit_key(hit)
        if not _within_slack(hit, origin, direction, tolerances):
            continue
        exact = _nearest_on(hit, origin, direction)
        if exact is not None:
            found[key] = (_along_ray(origin, direction, exact), exact)
        within.append(hit)
    hits = within
    separation = float(tolerances.edge)
    ordered = order_along_ray(measurable_in_view(hits, direction, separation),
                              {key: along for key, (along, _place) in found.items()}, separation)
    groups = _depth_groups(ordered, {key: along for key, (along, _place) in found.items()}, separation)
    return [PointerCandidate(hit, found.get(_hit_key(hit), (math.inf, None))[1],
                      found.get(_hit_key(hit), (math.inf, None))[0], groups[_hit_key(hit)])
            for hit in ordered]


def _nearest_on(hit: 'OwnedFeatureHit', origin: Float3, direction: Float3) -> Optional[Float3]:
    """The point of an edge (its line) or corner nearest the ray; None for anything else."""
    from kumiki.geometry import Line, Point

    located = hit.feature.locate_simple_unbounded(hit.owner)
    if isinstance(located, Point):
        return Float3.of(located.position)
    if not isinstance(located, Line):
        return None
    point, run = Float3.of(located.point), Float3.of(located.direction).unit()
    if run is None:
        return None
    across = run.dot(direction)
    if abs(across) > 1 - 1e-12:
        return None  # along the ray: any point of it is as near as any other
    to_origin = origin - point
    along_line = (to_origin.dot(run) - across * to_origin.dot(direction)) / (1 - across * across)
    return point + run * along_line


def measurable_in_view(
    hits: List['OwnedFeatureHit'], direction: Float3, tolerance: float,
) -> List['OwnedFeatureHit']:
    """*hits* without the faces a drawing's view has no use for.

    A 2D view measures lines and points, so a face is only of use where it is a line -- seen
    edge-on -- and even then nearly always lies on the same line as one of its straight edges,
    declared or derived, which measures the same. So a real face stays only when it is edge-on and
    no real straight line among *hits* draws along it: a cylinder's cap, rimmed by a circle, is the
    one thing naming its line, and stays. A line seen end-on draws a point, not the line.

    A non-real face (a centerplane, a perfect-timber face) is never one of these: it names a
    reference, not the surface, and measuring to it is not measuring to the edge that happens to
    draw on it -- a peg's axis through a centerplane, a rough arris flush with a perfect face. Seen
    at any other angle a face is an area, and goes.
    """
    from kumiki.csg.cutcsg import CSGFeatureType
    from kumiki.drawings.sheet_shape import SheetLine, sheet_gap, sheet_shape
    from kumiki.geometry import Line, Plane

    look = direction.v3()
    located = [(hit, hit.feature.locate_simple_unbounded(hit.owner)) for hit in hits]
    drawn_lines = [sheet_shape(line, look) for hit, line in located if isinstance(line, Line) and hit.feature.real]
    lines = [line for line in drawn_lines if isinstance(line, SheetLine)]

    def keep(hit: 'OwnedFeatureHit', where: Any) -> bool:
        if hit.feature.feature_type() is not CSGFeatureType.FACE or not isinstance(where, Plane):
            return True
        drawn = sheet_shape(where, look)
        if drawn is None:
            return False
        if not hit.feature.real:
            return True
        gaps = (sheet_gap(drawn, line, look) for line in lines)
        return not any(gap is not None and gap <= tolerance for gap in gaps)

    return [hit for hit, where in located if keep(hit, where)]


def _hit_key(hit: 'OwnedFeatureHit') -> Tuple:
    """One feature, however many times it was found: a derived one found at two places is two
    objects, so by what it is (feature_paths.hit_identity) and not by object."""
    from kumiki.csg.feature_paths import hit_identity

    return hit_identity(hit.feature, hit.owner)


def _along_ray(origin: Float3, direction: Float3, point) -> float:
    return (Float3.of(point) - origin).dot(direction)


def order_along_ray(
    hits: List['OwnedFeatureHit'], depth_of: Dict[Tuple[str, int], float], separation: float,
) -> List['OwnedFeatureHit']:
    """Nearest the viewer first, then the library's order (_sort_feature_hits).

    Depth leads only where there is some: hits are grouped along the ray, a group starting at
    the first hit more than `separation` past the start of the last, and ranked by group. So a
    face and the edges on it, found within a few pixels' worth of each other, are still ordered
    as they always were, while an edge in front comes before one behind it.
    """
    from kumiki.csg.cutcsg import feature_hit_sort_key

    starts = _depth_groups(hits, depth_of, separation)
    return sorted(hits, key=lambda hit: (starts[_hit_key(hit)], feature_hit_sort_key(hit)))


def _depth_groups(
    hits: List['OwnedFeatureHit'], depth_of: Dict[Tuple[str, int], float], separation: float,
) -> Dict[Tuple[str, int], float]:
    """Each hit's depth group (see order_along_ray), named by the depth the group starts at."""
    depth = lambda hit: depth_of.get(_hit_key(hit), math.inf)
    starts: Dict[Tuple[str, int], float] = {}
    start: Optional[float] = None
    for hit in sorted(hits, key=depth):
        if start is None or depth(hit) - start > separation:
            start = depth(hit)
        starts[_hit_key(hit)] = start
    return starts


# NOT USED. Kept for reference. A drawing's pick swept the whole ray with this, to offer
# everything drawn under the pointer at any depth: the back edge of a flank behind the front one,
# features on members the ray never hit. Hidden features can no longer be picked, and every member
# near the ray is now asked at the ray's one surface hit (candidates_under_pointer), so the surface
# finds what can be picked. It cost ~40ms per member, against ~6ms for the surface lookup.
# To make it cheap again: test each plane crossing against the face's own primitive (or the
# member's box) before the whole-tree is_point_on_boundary and find_all_features -- most crossings
# land far from their face -- and keep the last answer per member and ray for the click that
# follows a hover.
def real_features_along_ray(
    root: 'CutCSG', local_ray: LocalRay, tolerances: 'FeatureTestTolerances',
) -> List[Tuple[List['OwnedFeatureHit'], Float3]]:
    """Every feature on the boundary anywhere under the pointer, at any depth: the features at
    each place found, and the place.

    For an orthographic view, where everything along the ray is drawn at one place on the
    sheet: there, a flank seen edge-on has its front edge and its back edge on one line, and
    which of them the ray's first hit lands nearer to is chance -- so whichever it was, the
    other was no candidate at all.

    Found where the ray meets each declared face's plane, and where it passes within the edge
    tolerance of each declared edge or corner -- kept where that is on the boundary -- and then
    everything at those places, derived features included. At the edge tolerance throughout,
    since this is a screen-space question: what is within a few pixels of the pointer.
    """
    from kumiki.csg.cutcsg import FeatureTestTolerances, csg_children
    from kumiki.geometry import Line, Plane, Point

    origin, direction = Float3.of(local_ray[0]), Float3.of(local_ray[1]).unit()
    if direction is None:
        return []
    near = float(tolerances.edge)
    places: List[Float3] = []

    def consider(feature: 'CSGFeature', owner: 'CutCSG') -> None:
        located = feature.locate_simple_unbounded(owner)
        if isinstance(located, Plane):
            at = _ray_meets_plane(origin, direction, located)
        elif isinstance(located, Line):
            extent = feature.get_extent(owner)
            at = (ray_nears_segment(origin, direction, (Float3.of(extent.ends[0]), Float3.of(extent.ends[1])), near)
                  if extent is not None and extent.ends is not None else None)
        elif isinstance(located, Point):
            position = Float3.of(located.position)
            at = position if (position - origin).across(direction).length() <= near else None
        else:
            at = None
        if at is not None:
            places.append(at)

    def walk(node: 'CutCSG') -> None:
        for feature in node.get_declared_features():
            if feature.real:
                consider(feature, node)
        for child in csg_children(node):
            walk(child)

    walk(root)
    # Many planes meet the ray at one place -- rough stock's reliefs lie on its faces -- and each
    # place costs a walk of the whole tree, so each is asked about once. Only the same place: two
    # a pixel apart can differ in whether they are on the boundary at all.
    distinct: List[Float3] = []
    for place in places:
        if all(place.dist(kept) > 1e-9 for kept in distinct):
            distinct.append(place)
    snap = FeatureTestTolerances(face=near, edge=near, point=max(near, float(tolerances.point)))
    return [(root.find_all_features(place.v3(), snap), place)
            for place in distinct if root.is_point_on_boundary(place.v3(), eps=near)]


def _ray_meets_plane(origin: Float3, direction: Float3, plane: Any) -> Optional[Float3]:
    """Where the ray crosses *plane*, or None if it runs along it or the plane is behind it."""
    normal, at = Float3.of(plane.normal), Float3.of(plane.point)
    facing = direction.dot(normal)
    if abs(facing) < 1e-9:
        return None
    along = (at - origin).dot(normal) / facing
    return None if along < 0 else origin + direction * along


def _merge_hits(hits: List['OwnedFeatureHit'], more: List['OwnedFeatureHit']) -> List['OwnedFeatureHit']:
    """*hits* and *more*, each feature once (see _hit_key), in the library's order."""
    from kumiki.csg.cutcsg import _sort_feature_hits

    seen = {_hit_key(hit) for hit in hits}
    extra = []
    for hit in more:
        key = _hit_key(hit)
        if key not in seen:
            seen.add(key)
            extra.append(hit)
    return _sort_feature_hits(hits + extra) if extra else hits


def merge_ray_hits(
    root: 'CutCSG', hits: List['OwnedFeatureHit'], local_ray: LocalRay,
    tolerances: 'FeatureTestTolerances', timber: Optional['PerfectTimberWithin'] = None,
) -> List['OwnedFeatureHit']:
    """*hits*, plus the void-dwelling features the ray passes through, re-sorted.

    Kept apart from find_all_features because it is not a geometric question
    about a point -- it is what the POINTER was aiming at, which only the picking
    layer knows. The ordering is the library's, applied once over both lots.
    """
    from kumiki.csg.cutcsg import _sort_feature_hits

    along_ray = non_real_features_along_ray(root, local_ray, tolerances, timber)
    if not along_ray:
        return hits
    already = {(id(hit.feature), id(hit.owner)) for hit in hits}
    extra = [hit for hit in along_ray if (id(hit.feature), id(hit.owner)) not in already]
    return _sort_feature_hits(hits + extra) if extra else hits


def non_real_features_along_ray(
    root: 'CutCSG', local_ray: LocalRay, tolerances: 'FeatureTestTolerances',
    timber: Optional['PerfectTimberWithin'] = None,
) -> List['OwnedFeatureHit']:
    """Non-real features the ray passes close to, in timber-local space.

    ONLY non-real ones. A real feature is on the boundary, so in the 3D view the
    ray's own hit point already found it, and sweeping the whole ray would light
    everything behind what was clicked. A drawing's view does sweep for them --
    see real_features_along_ray -- since there everything under the pointer is
    drawn in one place.

    Bounded by the feature's own extent rather than the infinite line it locates
    to: a bore's axis is an endless line, and without this a peg hole could be
    selected from a metre past the end of the timber.

    The tolerance is the edge one, which the viewer derives from what a pixel is
    worth -- so this is a screen-space snap, the way any CAD package snaps to a
    centre line.

    With `timber` (a drawing's view), a plane too: a centerplane or a perfect-timber
    face seen edge-on draws as a line, and is snapped to as one (_plane_on_ray).
    Without it the surface point is what finds one.
    """
    from kumiki.csg.cutcsg import OwnedFeatureHit, csg_children
    from kumiki.geometry import Line, Plane

    origin, direction = Float3.of(local_ray[0]), Float3.of(local_ray[1]).unit()
    if direction is None:
        return []
    tolerance = float(tolerances.edge)
    found: List['OwnedFeatureHit'] = []

    def consider(feature: 'CSGFeature', owner: 'CutCSG') -> None:
        # A non-real POINT would want a point-to-ray distance; nothing declares
        # one yet, so there is nothing here to guess at.
        located = feature.locate_simple_unbounded(owner)
        if isinstance(located, Plane) and timber is not None:
            hit = OwnedFeatureHit(feature=feature, owner=owner)
            if _plane_on_ray(hit, root, timber, origin, direction, tolerance) is not None:
                found.append(hit)
            return
        if not isinstance(located, Line):
            return
        extent = feature.get_extent(owner)
        if extent is None or extent.ends is None:
            return
        ends = (Float3.of(extent.ends[0]), Float3.of(extent.ends[1]))
        if ray_reaches_segment(origin, direction, ends, tolerance):
            found.append(OwnedFeatureHit(feature=feature, owner=owner))

    def walk(node: 'CutCSG') -> None:
        for feature in node.get_declared_features():
            if not feature.real:
                consider(feature, node)
        for child in csg_children(node):
            walk(child)

    walk(root)
    return found





def _plane_on_ray(hit: 'OwnedFeatureHit', root: 'CutCSG', timber: 'PerfectTimberWithin', origin: Float3,
                  direction: Float3, tolerance: float) -> Optional[Float3]:
    """Where the ray runs through a plane feature seen edge-on, within `tolerance` of it and across
    its extent on the cut timber (FeatureExtent); None if it does not. The place is the ray's point
    nearest the middle of that extent."""
    from kumiki.csg.feature_extent import extents_of
    from kumiki.drawings.sheet_shape import SQUARE_TO_VIEW
    from kumiki.geometry import Plane

    plane = hit.feature.locate_simple_unbounded(hit.owner)
    if not isinstance(plane, Plane):
        return None
    normal = Float3.of(plane.normal).unit()
    if normal is None or abs(normal.dot(direction)) > SQUARE_TO_VIEW:
        return None  # seen at an angle: an area, not a line
    if abs(normal.dot(origin - Float3.of(plane.point))) > tolerance:
        return None
    extent = extents_of(root, timber).of(hit.feature, hit.owner)
    if extent is None or extent.is_empty:
        return None
    # Across the sheet, in the plane: the extent has to reach the ray's line from both sides.
    across = normal.cross(direction).unit()
    if across is None:
        return None
    reach = [[across.dot(Float3.of(corner) - origin) for corner in polygon] for polygon in extent.polygons()]
    if not any(min(sides) <= tolerance and max(sides) >= -tolerance for sides in reach if sides):
        return None
    middle = extent.anchor()
    if middle is None:
        return None
    return origin + direction * direction.dot(Float3.of(middle) - origin)


def ray_reaches_segment(origin, direction, ends, tolerance: float) -> bool:
    """Whether the ray passes within *tolerance* of the segment between *ends*."""
    return ray_nears_segment(origin, direction, ends, tolerance) is not None


def ray_nears_segment(origin, direction, ends, tolerance: float) -> Optional[Float3]:
    """The point of the segment between *ends* nearest the ray, if within *tolerance* of it.

    A screen-space snap run on every hover: it decides whether something is close enough to
    click, not where anything is cut.

    The closest approach of two lines, with the segment parameter clamped to the
    segment and the ray parameter to what is in front of the origin, since
    behind it is behind the camera. Parallel lines take the segment's midpoint,
    which is all the answer that case needs.

    `direction` is expected normalised, which is what makes D.D drop out of the
    usual pair of equations and leaves a single division.
    """
    origin, direction = Float3.of(origin), Float3.of(direction)
    start, end = Float3.of(ends[0]), Float3.of(ends[1])
    segment = end - start
    segment_length_sq = segment.dot(segment)
    if segment_length_sq <= 0:
        return None

    to_origin = origin - start
    ray_dot_segment = direction.dot(segment)
    denominator = segment_length_sq - ray_dot_segment * ray_dot_segment
    if abs(denominator) < 1e-12:
        along_segment = 0.5
    else:
        along_segment = (segment.dot(to_origin) - ray_dot_segment * direction.dot(to_origin)) / denominator
        along_segment = min(1.0, max(0.0, along_segment))

    on_segment = start + segment * along_segment
    on_ray = origin + direction * max(0.0, (on_segment - origin).dot(direction))
    return on_segment if on_segment.dist(on_ray) <= tolerance else None


def resolve_derived_feature(hits: List['OwnedFeatureHit']) -> Optional['CSGFeature']:
    """The DERIVED edge or point under the click, if one is the best answer there.

    Only derived. A timber's own arris is an edge as well, and a declared
    feature -- it has a name, an owner and a place in the tree, so it is
    referred to the way any declared feature is. Only one that exists nowhere
    but as the product of two parents needs the roundabout treatment of being
    named by them.
    """
    from kumiki.csg.cutcsg import CSGFeatureType

    if not hits:
        return None
    best = hits[0]
    if best.feature.feature_type() not in (CSGFeatureType.EDGE, CSGFeatureType.POINT):
        return None
    if not best.feature.is_derived():
        return None
    return best.feature


def outward_normal_and_face(
    target: 'CutCSG',
    local_csg: 'CutCSG',
    local_pt: Float3,
    eps: float,
) -> Tuple[Optional[Float3], Optional[str]]:
    """The outward normal at the pick, and which of the timber's own six faces
    it points most nearly along.

    The tree is already in the timber's local frame, so the normal is matched
    against the six local directions directly -- going via
    get_closest_oriented_face_from_global_direction would convert to global and
    straight back.

    The primitive supplies the direction and its parity supplies the sign. A
    primitive's own normal points out of that primitive, which is not always
    out of the finished timber: a mortise prism's points out of the hole and
    into the material, so the wall you clicked faces the other way. A
    SUBTRACTIVE node bounds a void, so its surface faces the opposite way to
    the solid.

    Parity rather than the root's own normal at the point, which is what this
    used to ask. That is a local geometric answer and it assumes the point is
    on the composed boundary without rechecking: Difference returns the base's
    normal without asking whether a subtract removed that point, and SolidUnion
    averages whichever children contain it without asking whether the result is
    on the union's surface. Both answer confidently for points that are not on
    the boundary at all, and averaging at an edge gives a bisector rather than
    a normal. Parity never consults the point, so none of that applies.

    Args:
        target: the leaf primitive that was hit, for the face direction.
        local_csg: the root of the tree it sits in, for the parity.
        local_pt: the clicked point, in that tree's (timber-local) space.
        eps: surface tolerance for the normal lookup.

    Returns:
        (normal, face name) in timber-local space, or (None, None) if no normal
        is available. The normal is the exact answer and the face name is the
        nearest of six, so the display can show both rather than rounding
        silently.
    """
    from kumiki.csg.cutcsg import CSGParity, walk_csg_with_parity

    point = to_v3(local_pt)
    normal = target.get_outward_normal(point, eps)
    if normal is None:
        return None, None
    # First occurrence: parity belongs to a position, and navigation hands back
    # the node rather than the path it took, so a subtree placed twice in one
    # tree could not be told apart here anyway.
    parity = next(
        (p for node, p in walk_csg_with_parity(local_csg) if node is target),
        None,
    )
    if parity is CSGParity.SUBTRACTIVE:
        normal = -normal
    return Float3.of(normal), nearest_timber_local_face_name(normal)


def resolve_csg_at_path(csg: 'CutCSG', path: List[str]) -> 'CutCSG':
    """The node a navigation path names under *csg*, or the deepest one it leads to when a step no
    longer matches (feature_paths.walk_labels)."""
    return walk_labels(csg, path)[0]


def navigate_csg_one_level(
    node: 'CutCSG',
    local_pt: Float3,
    current_path: List[str],
    eps: float = 1e-4,
    segments: Optional[Dict[int, str]] = None,
) -> Tuple[List[str], Any, Optional[str]]:
    """Navigate one level deeper into *node* based on click point.

    Returns (new_path, target_csg_to_highlight, feature_label_or_None).

    Every step carries the occurrence numbering its label among the siblings it
    shares one with, from the same _candidate_segments the resolvers index into.
    *segments* is that scope, passed down when drilling through an unlabelled
    compound so its children stay numbered against the labelled ancestor a path
    actually names.
    """
    from kumiki.csg.cutcsg import SolidUnion, Difference

    if segments is None:
        segments = candidate_segments(node)

    def step(child: 'CutCSG') -> Tuple[List[str], Any, Optional[str]]:
        """The move onto *child*."""
        segment = segments.get(id(child))
        if segment:
            return (current_path + [segment], child, None)
        if isinstance(child, (SolidUnion, Difference)):
            return navigate_csg_one_level(child, local_pt, current_path, eps, segments)
        return (current_path, child, describe_leaf_csg(child, local_pt, eps))

    if isinstance(node, Difference):
        for sub in node.subtract:
            if csg_point_on_boundary(sub, local_pt, eps):
                return step(sub)
        # Point is on the base surface
        return step(node.base)

    if isinstance(node, SolidUnion):
        for ch in node.children:
            if csg_point_on_boundary(ch, local_pt, eps):
                return step(ch)
        # Couldn't match a specific child — report face of whole union
        return (current_path, node, "face")

    # Leaf primitive — report face
    return (current_path, node, describe_leaf_csg(node, local_pt, eps))


def navigate_csg_to_leaf(
    csg: 'CutCSG',
    local_pt: Float3,
    eps: float = 1e-4,
) -> Tuple[List[str], Any, Optional[str]]:
    """A plain click: traverse from root to deepest labeled node, then report face."""

    path: List[str] = []
    node = csg
    while True:
        new_path, target, label = navigate_csg_one_level(node, local_pt, path, eps)
        if label is not None:
            # Reached a leaf
            return (new_path, target, label)
        if new_path == path:
            # No progress — shouldn't happen but guard against infinite loop
            return (path, node, "face")
        path = new_path
        node = target


def aabb_filter(csg: 'CutCSG', eps: float) -> Optional[Callable[[Float3], bool]]:
    """A cheap "could this point be on *csg*" test, or None if it cannot help.

    None when the box says nothing useful -- a solid unbounded in every
    direction, or one whose bounds cannot be read. An empty solid rejects
    everything, which is a real answer rather than an unhelpful one.

    The bounds are the CSG's own, so points must be in the same space it is:
    timber-local, the same as the centroids the caller computes.
    """
    try:
        with warnings.catch_warnings():
            # Asking speculatively, and "unbounded" is a perfectly good answer:
            # it means the box cannot help and the walk goes ahead unfiltered.
            # The library's warning is for callers who wanted a real box.
            warnings.simplefilter("ignore")
            box = csg.get_aabb()
    except Exception:
        return None
    if box is None:
        return None
    if getattr(box, "is_empty", False):
        return lambda point: False

    bounds = [
        (box.min_x, box.max_x),
        (box.min_y, box.max_y),
        (box.min_z, box.max_z),
    ]
    limits = []
    for low, high in bounds:
        limits.append((
            None if low is None else float(low) - eps,
            None if high is None else float(high) + eps,
        ))
    if all(low is None and high is None for low, high in limits):
        return None

    def inside(point: Float3) -> bool:
        for axis, (low, high) in enumerate(limits):
            value = point[axis]
            if low is not None and value < low:
                return False
            if high is not None and value > high:
                return False
        return True

    return inside


def extract_highlight_mesh(
    mesh_vertices: List[float],
    mesh_indices: List[int],
    target_csg: 'CutCSG',
    timber_rot: Rows3,
    timber_pos: Float3,
    eps: float = 1e-4,
    root_csg: Optional['CutCSG'] = None,
    selected_path: Optional[List[str]] = None,
    selected_ref: Optional[Any] = None,
    feature_label: Optional[str] = None,
    edge_feature: Optional['CSGFeature'] = None,
    feature_type: Optional[str] = None,
) -> Tuple[List[float], List[int], int, int]:
    """Extract triangles belonging to *target_csg* from the rendered mesh.

    *mesh_vertices* / *mesh_indices* are in global coords (flat lists).
    Returns (highlight_vertices, highlight_indices, matched_tris, total_tris).
    """
    total_tris = len(mesh_indices) // 3
    out_verts: List[float] = []
    out_idx: List[int] = []
    matched = 0

    # The path to hold each triangle's owner to, or None to keep every triangle.
    # Triangles are kept only where the selected path's node is the one selected.
    if (root_csg is not None and selected_ref is not None and selected_path
            and resolve_csg_at_path(root_csg, selected_path) is not selected_ref):
        return [], [], 0, len(mesh_indices) // 3

    # Broadphase: a triangle whose centroid is outside the target's own box
    # cannot be on its boundary, and a box test is far cheaper than asking the
    # CSG. It matters because the target is usually small and the mesh is the
    # whole timber -- a mortise on a beam keeps 10 triangles out of 376, and the
    # walk drops from 2.8ms to 0.1ms.
    # An edge whose line has already been worked out has no triangles to light:
    # the line IS its highlight. Without this the walk still runs, comparing
    # every triangle against an edge's name that no face can ever answer to, and
    # spends a fifth of a second arriving at nothing.
    if feature_type in ("EDGE", "POINT") and edge_feature is None:
        return [], [], 0, len(mesh_indices) // 3

    inside_box = aabb_filter(target_csg, eps)

    # The feature we are matching against, looked up once instead of once per
    # triangle. describe_leaf_csg asks the node for EVERY feature at the point
    # and compares names; when the name is a declared feature we can ask that
    # one feature directly, which is the same answer without the search.
    #
    # test_point_unbounded alone means nothing off the boundary; the loop asks both.
    wanted_feature = None
    if feature_label is not None and edge_feature is None:
        wanted_feature = next(
            (f for f in target_csg.get_declared_features() if f.name == feature_label), None)
    if wanted_feature is not None and not wanted_feature.real:
        # No surface to shade (a centerplane, a perfect face in rough stock): its outline is drawn
        # instead. Tested triangle by triangle, it lit whichever ones it happened to pass through.
        return [], [], 0, total_tris

    for tri in range(total_tris):
        i0 = mesh_indices[tri * 3]
        i1 = mesh_indices[tri * 3 + 1]
        i2 = mesh_indices[tri * 3 + 2]
        # Centroid in global
        cx = (mesh_vertices[i0*3] + mesh_vertices[i1*3] + mesh_vertices[i2*3]) / 3.0
        cy = (mesh_vertices[i0*3+1] + mesh_vertices[i1*3+1] + mesh_vertices[i2*3+1]) / 3.0
        cz = (mesh_vertices[i0*3+2] + mesh_vertices[i1*3+2] + mesh_vertices[i2*3+2]) / 3.0
        # Convert centroid to timber-local
        local_c = inv_transform_point(timber_rot, timber_pos, [cx, cy, cz])
        if inside_box is not None and not inside_box(local_c):
            continue
        # The feature's own plane first: far cheaper than the tree's boundary, and most triangles fail it.
        if wanted_feature is not None and not wanted_feature.test_point_unbounded(target_csg, to_v3(local_c), eps):
            continue
        if csg_point_on_boundary(target_csg, local_c, eps):
            if edge_feature is not None:
                # The last fallback, and a poor one: it asks test_point_unbounded
                # vertex without the boundary check, so it lights the strip
                # along the whole line rather than along the edge. Only reached
                # when crop_line_to_segments_on_csg met a primitive it could not
                # describe as half spaces, and it should go once that is total.
                #
                # An edge is a line, and no triangle's centroid sits on one --
                # matching the way a face does would light nothing at all. The
                # mesher puts vertices on edges, so the strip along an edge is
                # the triangles with two vertices on it.
                on_edge = 0
                for corner in (i0, i1, i2):
                    corner_local = inv_transform_point(timber_rot, timber_pos, [
                        mesh_vertices[corner * 3],
                        mesh_vertices[corner * 3 + 1],
                        mesh_vertices[corner * 3 + 2],
                    ])
                    if edge_feature.test_point_unbounded(
                        target_csg, to_v3(corner_local), edge_tolerance()
                    ):
                        on_edge += 1
                if on_edge < 2:
                    continue
            elif feature_label is not None and wanted_feature is None:
                # A generic name -- "left", "cylindrical_surface" -- which no
                # declared feature answers to, so it has to be worked out.
                tri_face_label = describe_leaf_csg(target_csg, local_c, eps)
                if tri_face_label != feature_label:
                    continue
            base = len(out_verts) // 3
            out_verts.extend(mesh_vertices[i0*3 : i0*3+3])
            out_verts.extend(mesh_vertices[i1*3 : i1*3+3])
            out_verts.extend(mesh_vertices[i2*3 : i2*3+3])
            out_idx.extend([base, base+1, base+2])
            matched += 1

    return out_verts, out_idx, matched, total_tris


# --- a pick: where navigation lands, what is under the pointer, and which of it is wanted -------

#: Where navigating the tree lands: the path to the node, the node, and the feature named there
#: (None while a click is still drilling through compounds).
Navigated = Tuple[List[str], 'CutCSG', Optional[str]]


def navigate(root: 'CutCSG', local_pt: Float3, eps: float, ctrl_click: bool, current_path: List[str]) -> Navigated:
    """Where a click lands in the tree. A plain click goes straight to the feature; Ctrl holds it to
    one level per click, from `current_path` while the point is still on that node."""
    if not ctrl_click:
        return navigate_csg_to_leaf(root, local_pt, eps)
    node = root
    if current_path:
        node = resolve_csg_at_path(root, current_path)
        if not csg_point_on_boundary(node, local_pt, eps):
            node, current_path = root, []
    return navigate_csg_one_level(node, local_pt, current_path, eps)


class Candidates(NamedTuple):
    """Every feature under the pointer, visible ones first: `hits[:visible_count]` can be taken,
    the rest are listed greyed."""
    hits: List['OwnedFeatureHit']
    visible_count: int


def find_candidates(
    root: 'CutCSG', local_pt: Float3, eps: float, tolerances: 'FeatureTestTolerances',
    local_ray: Optional[LocalRay],
) -> Candidates:
    """What is under the pointer on one member: the features at the point, all of them takeable. A
    drawing's view asks every member drawn there instead (drawing_candidates)."""
    hits = features_at_point(root, local_pt, eps, tolerances, local_ray=local_ray)
    return Candidates(hits, len(hits))


def sight_blocker(transform: Transform, occluders: List[Tuple['CutCSG', Transform]],
                  direction: Float3) -> Callable[[Float3], bool]:
    """`blocked(place)`: whether an occluder's material hides a place (local to `transform`) from
    a camera looking along `direction` (also local). visibility.hidden_at, per place."""
    from kumiki.drawings.visibility import hidden_at
    from kumiki.rule import as_ndarray

    look = as_ndarray(transform.local_to_global_direction(direction.v3()))
    return lambda place: hidden_at(as_ndarray(transform.local_to_global(place.v3())), look, occluders)


def best_matching_candidate(hits: List['OwnedFeatureHit'], timber: 'PerfectTimberWithin', held: Any, look: Any,
                            space: Any) -> Optional[int]:
    """Which feature under the pointer best finishes the measurement in hand.

    The most specific feature is the right answer to "what is this thing here", and the wrong one
    while measuring: holding a face and being handed the arris beside it means most hovers refuse.
    So a candidate that admits a measurement with the held end beats one that does not, and among
    those, one of the held end's type breaks the tie (earlier, more specific, wins among equals).
    None when nothing is held, there is no camera, or no candidate admits anything.
    """
    from kumiki.csg.feature_paths import FeatureHandle

    return best_matching_handle([FeatureHandle(timber=timber, hit=hit) for hit in hits], held, look, space)


def best_matching_handle(handles: List[Any], held: Any, look: Any, space: Any) -> Optional[int]:
    """best_matching_candidate, over features that may be on different timbers (FeatureHandles)."""
    from kumiki.drawings.kigumi_measuring_helpers import kinds_for_pair, world_geometry

    if held is None or not look or not handles:
        return None
    best = None
    for index, handle in enumerate(handles):
        geometry = world_geometry(handle)
        if not geometry or not kinds_for_pair(held, geometry, look, space):
            continue
        rank = (0 if type(geometry) is type(held) else 1, index)
        if best is None or rank < best[0]:
            best = (rank, index)
    return None if best is None else best[1]


class Pick(NamedTuple):
    """What a pick chose: the node it selects (`path`, `node`), the feature named in it (`label`,
    `kind`, its feature type's name), an edge or point to draw (`edge` derived, or
    `declared_edge`), and the candidate it is (`hit`)."""
    path: List[str]
    node: 'CutCSG'
    label: Optional[str]
    kind: Optional[str] = None
    edge: Optional['CSGFeature'] = None
    declared_edge: Optional['CSGFeature'] = None
    hit: Optional['OwnedFeatureHit'] = None

    @property
    def edge_feature(self) -> Optional['CSGFeature']:
        return self.edge if self.edge is not None else self.declared_edge

    def located(self) -> Optional[Tuple['CSGFeature', 'CutCSG', Any]]:
        """The chosen feature, the node it is shown under, and what it lies on: an edge or point
        under the node navigation placed it at, anything else under its own owner."""
        if self.hit is None:
            return None
        owner = self.node if self.edge_feature is not None else self.hit.owner
        return (self.hit.feature, owner, self.hit.feature.locate_simple_unbounded(owner))


def pick_from_candidate(root: 'CutCSG', hit: 'OwnedFeatureHit') -> Optional[Pick]:
    """The pick one chosen feature makes, or None when its owner cannot be placed in the tree.

    A derived edge or point is placed by the deeper of the two parents that form it; a declared one
    belongs to whoever declared it. Trying derived first tells them apart.
    """
    from kumiki.csg.cutcsg import CSGFeatureType

    feature = hit.feature
    kind = feature.feature_type().name
    if feature.feature_type() in (CSGFeatureType.EDGE, CSGFeatureType.POINT):
        owned = derived_feature_owner(root, feature)
        if owned is not None:
            return Pick(owned[1], owned[0], feature.name, kind, edge=feature, hit=hit)
        placed = node_positions(root).get(id(hit.owner))
        return None if placed is None else Pick(placed[2], hit.owner, feature.name, kind, declared_edge=feature, hit=hit)
    placed = node_positions(root).get(id(hit.owner))
    return None if placed is None else Pick(placed[2], hit.owner, feature.name, kind, hit=hit)


def choose(root: 'CutCSG', navigated: Navigated, found: Candidates, candidate_index: Optional[int],
           preferred: Callable[[List['OwnedFeatureHit']], Optional[int]], in_drawing: bool, ctrl_click: bool) -> Pick:
    """Which of the features under the pointer is wanted, as a Pick.

    In order: the one the caller names (Tab, the menu) -- final, since the rules below only guess
    what was meant -- or else `preferred` (best_matching_candidate while measuring), or else in a
    drawing the first, the candidates being in the order a click should take them. Failing those:
    a derived edge or point under the click, then a declared one (a timber's own arris), then the
    face navigation landed on. Zero is a choice: stepping round to the first feature is the caller
    naming one.
    """
    from kumiki.csg.cutcsg import CSGFeatureType

    path, node, label = navigated
    hits, visible = found
    edge = resolve_derived_feature(hits) if label is not None else None
    if candidate_index is None:
        candidate_index = preferred(hits[:visible])
    if candidate_index is None and in_drawing and not ctrl_click and visible:
        candidate_index = 0
    if candidate_index is not None and visible:
        picked = pick_from_candidate(root, hits[int(candidate_index) % visible])  # never a hidden one
        if picked is not None:
            return picked

    pick = Pick(path, node, label, edge=edge)
    if edge is not None:
        owned = derived_feature_owner(root, edge)
        if owned is not None:
            # resolve_derived_feature's answer is the best one.
            pick = Pick(owned[1], owned[0], edge.name, edge.feature_type().name, edge=edge, hit=hits[0])
    elif label is not None and hits:
        # A declared edge or point beats the face a click lands on, as a derived one does: the more
        # specific answer there. It belongs to the node that declared it.
        best = hits[0]
        if best.feature.feature_type() in (CSGFeatureType.EDGE, CSGFeatureType.POINT):
            placed = node_positions(root).get(id(best.owner))
            if placed is not None:
                pick = Pick(placed[2], best.owner, best.feature.name, best.feature.feature_type().name,
                            declared_edge=best.feature, hit=best)
    if pick.hit is None and pick.label is not None:
        # Navigation landed on a face: the candidate is the one its node declares under that name.
        named = [hit for hit in hits if hit.feature.name == pick.label]
        hit = next((hit for hit in named if hit.owner is pick.node), named[0] if named else None)
        pick = pick._replace(hit=hit)
    return pick


class Derivation(NamedTuple):
    """For a derived feature: the path to the node owning it, and each parent's (path, name)."""
    owner_path: Optional[List[str]]
    parents: List[Tuple[List[str], str]]


def derivation(root: 'CutCSG', hits: List['OwnedFeatureHit'], feature: Optional['CSGFeature']) -> Optional[Derivation]:
    if feature is None or not feature.is_derived():
        return None
    positions = node_positions(root)

    def path_of(owner) -> Optional[List[str]]:
        placed = positions.get(id(owner))
        return placed[2] if placed is not None else None

    owner = next((hit.owner for hit in hits if hit.feature is feature), None)
    return Derivation(path_of(owner) if owner is not None else None,
                      [(path_of(parent.owner) or [], parent.feature.name)
                       for parent in getattr(feature, "parents", ()) if parent is not None])


def non_real_plane_outline(feature: 'CSGFeature', owner: 'CutCSG', timber: 'PerfectTimberWithin',
                           root: 'CutCSG') -> Optional[List[WorldSegment]]:
    """A non-real plane's outline -- a perfect face in rough stock, a centerplane -- which has no
    surface to light: its extent's outline, in world space, which a drawing shows edge-on as the
    line it draws dotted. None for anything else."""
    from kumiki.csg.feature_extent import extents_of
    from kumiki.geometry import Plane
    from kumiki.rule import create_v3

    if feature.real or not isinstance(feature.locate_simple_unbounded(owner), Plane):
        return None
    extent = extents_of(root, timber).of(feature, owner)
    if extent is None:
        return None
    to_world = lambda point: Float3.of(timber.transform.local_to_global(create_v3(*point)))
    return [{"start": to_world(start), "end": to_world(end)} for start, end in extent.outline()]


class PlaneOutline(NamedTuple):
    """A plane's outline, in world space: its normal, and its segments' ends, flat."""
    normal: List[float]
    positions: List[float]


def perfect_reference_outlines(timber: 'PerfectTimberWithin', root: 'CutCSG', centerplanes: bool) -> List[PlaneOutline]:
    """The rough body's perfect references, each outlined as cropped to the cut timber `root`, in
    world space: what a drawing draws dotted, edge-on. Its centerplanes, or its perfect faces --
    those the rough body has no face for (ptw.*); a face it has (rptw.*) is drawn as the timber
    already, and a joint's faces are not these."""
    from kumiki.csg.cutcsg import Difference, FeatureNature, MidplaneFeature, PlaneFeature
    from kumiki.csg.feature_extent import extents_of
    from kumiki.geometry import Plane
    from kumiki.rule import create_v3

    body = root.base if isinstance(root, Difference) else root
    kind = MidplaneFeature if centerplanes else PlaneFeature
    extents = extents_of(root, timber)
    to_world = lambda point: [float(v) for v in timber.transform.local_to_global(create_v3(*point))]
    outlines: List[PlaneOutline] = []
    for feature in body.get_declared_features():
        if not isinstance(feature, kind) or feature.nature is not FeatureNature.PERFECT_REFERENCE:
            continue
        plane = feature.locate_simple_unbounded(body)
        extent = extents.of(feature, body)
        if not isinstance(plane, Plane) or extent is None:
            continue
        positions = [v for start, end in extent.outline() for v in (*to_world(start), *to_world(end))]
        outlines.append(PlaneOutline([float(v) for v in timber.transform.local_to_global_direction(plane.normal)],
                                     positions))
    return outlines


# --- a drawing's pick: every member drawn under the pointer -------------------------------------

class DrawnMember(NamedTuple):
    """A member a drawing's pick may land on: its key, its cut timber's tree (local space), where it
    is, and where the pointer's ray met its surface (local), if it did."""
    key: str
    root: 'CutCSG'
    timber: 'PerfectTimberWithin'
    surface_point: Optional[Float3]


class MemberCandidate(NamedTuple):
    """A feature under the pointer, and the member it is on. `candidate` is in that member's space."""
    member: str
    timber: 'PerfectTimberWithin'
    candidate: PointerCandidate


def drawing_candidates(
    members: List[DrawnMember], world_ray: LocalRay, tolerances: 'FeatureTestTolerances',
    blocked_for: Callable[[str], Optional[Callable[[Float3], bool]]],
) -> Tuple[List[MemberCandidate], int]:
    """Everything under the pointer in a drawing's view, on every member drawn there: (candidates,
    how many are visible). Visible first, then hidden, each nearest first.

    A sheet draws every member flat, so what the pointer is near need not be on the member its ray
    meets first -- where two members meet, the corner aimed at is often the other one's, and off a
    silhouette the ray meets none at all. Each member is searched along the ray in its own space;
    depth along the ray is the same in every space, so they are ordered as one (order_along_ray),
    and what is hidden is decided across them (visibility: drawn_over, and `blocked_for` a member's
    places).
    """
    from kumiki.csg.cutcsg import feature_hit_sort_key
    from kumiki.csg.feature_paths import FeatureHandle
    from kumiki.drawings.kigumi_measuring_helpers import world_geometry
    from kumiki.drawings.visibility import drawn_over, never_hidden

    origin, direction = Float3.of(world_ray[0]), Float3.of(world_ray[1]).unit()
    if direction is None:
        return [], 0
    found: List[MemberCandidate] = []
    for member in members:
        rotation, position = build_inv_transform_float(member.timber.transform)
        local_ray = (inv_transform_point(rotation, position, origin), inv_transform_direction(rotation, direction))
        for candidate in candidates_under_pointer(member.root, member.surface_point, tolerances, local_ray,
                                                  member.timber):
            found.append(MemberCandidate(member.key, member.timber, candidate))

    # One depth order over every member: grouped as order_along_ray groups, then the library's order.
    separation = float(tolerances.edge)
    start: Optional[float] = None
    by_depth = sorted(range(len(found)), key=lambda index: found[index].candidate.depth)
    group_of = {}
    for index in by_depth:
        depth = found[index].candidate.depth
        if start is None or depth - start > separation:
            start = depth
        group_of[index] = start
    ordered = sorted(range(len(found)), key=lambda index: (group_of[index], feature_hit_sort_key(found[index].candidate.hit)))
    found = [found[index]._replace(candidate=found[index].candidate._replace(group=group_of[index])) for index in ordered]

    look = direction
    worlds: Dict[int, Any] = {}

    def world(one: MemberCandidate) -> Any:
        if id(one) not in worlds:
            worlds[id(one)] = world_geometry(FeatureHandle(timber=one.timber, hit=one.candidate.hit))
        return worlds[id(one)]

    visible: List[MemberCandidate] = []
    hidden: List[MemberCandidate] = []
    for one in found:
        hit, candidate = one.candidate.hit, one.candidate
        if never_hidden(hit.feature):
            visible.append(one)
            continue
        blocked = blocked_for(one.member)
        covered = any(other.candidate.group < candidate.group
                      and drawn_over(world(other), world(one), look, float(tolerances.edge)) for other in visible)
        if covered or (blocked is not None and candidate.place is not None and blocked(candidate.place)):
            hidden.append(one)
        else:
            visible.append(one)
    return visible + hidden, len(visible)
