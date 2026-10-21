"""Picking: what a point or ray on a cut timber lands on, and what to highlight for it.

Finds the node and features under a click, the features a ray passes near, and the rendered
triangles or segments to light for a picked node or feature. Geometry only; kigumi's runner builds
the wire forms. Hot paths use Float3 (rule_at_home.py) rather than V3.
"""

import math
import warnings
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, TypedDict

from ..csg.cutcsg import CSGFeature, CutCSG, FeatureTestTolerances, OwnedFeatureHit
from ..csg.feature_paths import candidate_segments, label_name, walk_labels
from ..csg.feature_extent import FeatureExtents, Interval
from ..geometry import Line
from ..rule import Transform, V3, scalar
from ..timber import PerfectTimberWithin
from .rule_at_home import Float3, LocalFrame

#: A pointer's ray in timber-local space: origin, direction.
LocalRay = Tuple[Float3, Float3]


class WorldSegment(TypedDict):
    start: Float3
    end: Float3





def subtree_contains(root: 'CutCSG', target: 'CutCSG') -> bool:
    """Return whether `target` is `root` or below it."""
    from kumiki.csg.cutcsg import csg_children

    # note this is identity comparison, not quality as 2 CutCSGs can be `==` equivalent but not the same
    if root is target:
        return True
    return any(subtree_contains(child, target) for child in csg_children(root))


def to_v3(pt) -> 'V3':
    """Return a plain [x, y, z] as a V3."""
    return Float3.of(pt).v3()


def csg_contains_point(csg: 'CutCSG', local_pt: Float3, eps: float = 1e-4) -> bool:
    """Return whether timber-local `local_pt` is inside `csg`, within `eps`."""
    return csg.contains_point(to_v3(local_pt), eps)


def csg_point_on_boundary(csg: 'CutCSG', local_pt: Float3, eps: float = 1e-4) -> bool:
    """Return whether timber-local `local_pt` is on the boundary of `csg`, within `eps`."""
    return csg.is_point_on_boundary(to_v3(local_pt), eps)


# Timber-local outward directions, used to name an unnamed face by whichever of
# the timber's own six faces it most points toward.
TIMBER_LOCAL_FACE_NORMALS = (
    ("right", (1.0, 0.0, 0.0)), ("left", (-1.0, 0.0, 0.0)),
    ("front", (0.0, 1.0, 0.0)), ("back", (0.0, -1.0, 0.0)),
    ("top", (0.0, 0.0, 1.0)), ("bottom", (0.0, 0.0, -1.0)),
)


def nearest_timber_local_face_name(normal: Any) -> str:
    """Return the name of the timber face whose direction a timber-local `normal` is nearest."""
    n = [float(normal[0]), float(normal[1]), float(normal[2])]
    best_name, best_dot = "face", -2.0
    for name, direction in TIMBER_LOCAL_FACE_NORMALS:
        dot = n[0] * direction[0] + n[1] * direction[1] + n[2] * direction[2]
        if dot > best_dot:
            best_dot, best_name = dot, name
    return best_name


def feature_at(csg: 'CutCSG', point: Any, eps: float) -> Optional['CSGFeature']:
    """Return the best real feature at a point, preferring an authored one over a default.

    Non-real features (e.g. a centerplane) are skipped: this names the surface.
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
    """Return a label for the part of primitive `csg` at `local_pt`.

    An authored feature's name, else the primitive's default name; failing those, a fallback (with a
    warning) from the shape or the timber-local facing.
    """
    from kumiki.csg.cutcsg import Cylinder, HalfSpace
    from kumiki.rule import are_vectors_perpendicular

    point = to_v3(local_pt)

    # `eps` is the face tolerance; edges and points keep their wider defaults.
    feature = feature_at(csg, point, eps)
    if feature is not None:
        return feature.name

    # Fallbacks for a shape with no default features (PathExtrusion); they warn.
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
    """Return the node a derived edge or point is shown under, and its path: the deeper parent's owner, ties broken by document order."""
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
    """Return how close a vertex must be to an edge to count as on it: the edge's pick tolerance."""
    from kumiki.csg.cutcsg import FEATURE_EDGE_TOLERANCE

    return FEATURE_EDGE_TOLERANCE


def edge_highlight_segments(
    edge_feature: 'CSGFeature',
    owner: 'CutCSG',
    extents: 'FeatureExtents',
) -> Tuple[Optional[List[WorldSegment]], bool]:
    """Return (segments, absent) to draw a selected line feature, in world space: its FeatureExtent in `extents`.

    segments is None when the extent can't be computed (the caller then lights triangles); `absent`
    says the line was cropped away entirely.
    """
    from kumiki.geometry import Line

    if not isinstance(edge_feature.locate_simple_unbounded(owner), Line):
        return (None, False)
    extent = extents.of(edge_feature, owner)
    if extent is None:
        return (None, False)
    if extent.is_empty:
        return (None, True)
    return (_world_segments(extent.outline(), extents.timber), False)


def _world_segments(segments, timber: 'PerfectTimberWithin') -> List[WorldSegment]:
    from kumiki.rule import create_v3

    to_world = lambda point: Float3.of(timber.transform.local_to_global(create_v3(*point)))  # noqa: E731
    return [{"start": to_world(start), "end": to_world(end)} for start, end in segments]


def features_at_point(
    root: 'CutCSG', local_pt: Float3, eps: float, tolerances: Optional['FeatureTestTolerances'] = None,
    local_ray: Optional[LocalRay] = None,
) -> List['OwnedFeatureHit']:
    """Return every feature at `local_pt` for a 3D pick, best first (features_near_ray, without a ray: at the point)."""
    from kumiki.csg.cutcsg import FeatureTestTolerances

    resolved = tolerances or FeatureTestTolerances(face=eps)
    if local_ray is None or Float3.of(local_ray[1]).unit() is None:
        return _only_creases(root, root.find_all_features(to_v3(local_pt), resolved), local_pt)
    return [candidate.hit for candidate in features_near_ray(root, Float3.of(local_pt), resolved, local_ray)]


def features_near_ray(
    root: 'CutCSG', local_pt: Optional[Float3], tolerances: 'FeatureTestTolerances', local_ray: LocalRay,
    extents: Optional['FeatureExtents'] = None,
) -> List['PointerCandidate']:
    """Return the features under the pointer on one tree, in the library's order, each with where it
    was found along the ray. Shared by the 3D and drawing picks; slack is in screen pixels.

    - Features at the surface point `local_pt` (None if the ray misses), gathered SLANT_REACH wider
      and kept within their slack of the ray; edges and corners are placed nearest the ray.
    - Non-real planes whose line across the face there passes near the ray, placed at the surface.
    - Non-real lines (a bore's axis) the ray passes near.
    - With `extents` (a drawing; the tree's FeatureExtents), non-real planes seen edge-on along the ray.

    `group` is left 0; order_along_ray sets it.
    """
    from dataclasses import replace

    from kumiki.csg.cutcsg import _sort_feature_hits

    origin, direction = Float3.of(local_ray[0]), Float3.of(local_ray[1]).unit()
    assert direction is not None
    gather = replace(tolerances, edge=float(tolerances.edge) * SLANT_REACH,
                     point=float(tolerances.point or tolerances.edge) * SLANT_REACH)
    hits: List['OwnedFeatureHit'] = []
    if local_pt is not None:
        gathered = _only_creases(root, root.find_all_features(local_pt.v3(), gather), local_pt)
        hits = [hit for hit in gathered if _within_slack(hit, origin, direction, tolerances)]
        known = {_hit_key(hit) for hit in hits}
        hits += [hit for hit in _reference_planes_near(root, local_pt, origin, direction, float(tolerances.edge))
                 if _hit_key(hit) not in known]
    at_surface = {_hit_key(hit) for hit in hits}
    hits += [hit for hit in non_real_features_along_ray(root, local_ray, tolerances, extents)
             if _hit_key(hit) not in at_surface]

    candidates = []
    for hit in _sort_feature_hits(hits):
        place = _nearest_on(hit, origin, direction)
        if place is None:
            place = (local_pt if _hit_key(hit) in at_surface
                     else _place_off_surface(hit, extents, origin, direction))
        depth = _along_ray(origin, direction, place) if place is not None else math.inf
        candidates.append(PointerCandidate(hit, place, depth, 0.0))
    return candidates


def _place_off_surface(hit: 'OwnedFeatureHit', extents: Optional['FeatureExtents'],
                       origin: Float3, direction: Float3) -> Optional[Float3]:
    """Return where a non-real feature sits along the ray: a line's nearest approach, or an edge-on plane's crossing."""
    ends = hit.feature.declared_ends(hit.owner)
    if ends is not None:
        return ray_nears_segment(origin, direction, (Float3.of(ends[0]), Float3.of(ends[1])), math.inf)
    if extents is not None:
        return _plane_on_ray(hit, extents, origin, direction, math.inf)
    return None


#: How much further than its slack a 3D pick looks for an edge or a corner along the face it struck,
#: before keeping those within the slack across the view: a face at 70 degrees to the view.
SLANT_REACH = 3.0


def _within_slack(hit: 'OwnedFeatureHit', origin: Float3, direction: Float3,
                  tolerances: 'FeatureTestTolerances') -> bool:
    """Return whether an edge or corner comes within its slack of the ray; other hits, and a line along the ray, pass."""
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
    """Return the non-real planes in `root` whose line across the face at `point` comes within `tolerance` of the ray."""
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
    """Return `hits` without real edges that, at the pointer, lie within one flat face (edges_on_csg.is_crease_at)."""
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
    """A feature under the pointer in a drawing view: its depth along the ray, and its depth group (order_along_ray)."""
    hit: 'OwnedFeatureHit'
    place: Optional[Float3]
    depth: float
    group: float


def candidates_under_pointer(
    root: 'CutCSG', local_pt: Optional[Float3], tolerances: 'FeatureTestTolerances', local_ray: LocalRay,
    extents: 'FeatureExtents',
) -> List[PointerCandidate]:
    """Return the features under the pointer for a drawing view (features_near_ray), filtered by
    measurable_in_view, nearest depth group first."""
    local_pt = Float3.of(local_pt) if local_pt is not None else None
    direction = Float3.of(local_ray[1]).unit()
    if direction is None:
        hits = _only_creases(root, root.find_all_features(local_pt.v3(), tolerances), local_pt) if local_pt else []
        return [PointerCandidate(hit, local_pt, 0.0, 0.0) for hit in hits]
    found = {_hit_key(candidate.hit): candidate
             for candidate in features_near_ray(root, local_pt, tolerances, local_ray, extents)}
    separation = float(tolerances.edge)
    depths = {key: candidate.depth for key, candidate in found.items()}
    ordered = order_along_ray(measurable_in_view([candidate.hit for candidate in found.values()], direction, separation),
                              depths, separation)
    groups = _depth_groups(ordered, depths, separation)
    return [found[_hit_key(hit)]._replace(group=groups[_hit_key(hit)]) for hit in ordered]


def _nearest_on(hit: 'OwnedFeatureHit', origin: Float3, direction: Float3) -> Optional[Float3]:
    """Return the point of an edge's line or corner nearest the ray, or None for other hits."""
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
    """Return `hits` without the faces a drawing view can't use.

    A real face stays only if seen edge-on and no real line in `hits` draws along it (e.g. a cylinder's
    cap). Non-real faces, and faces seen at an angle, are dropped.
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
    """Return a hashable key for a hit by what it is (feature_paths.hit_identity), not by object."""
    from kumiki.csg.feature_paths import hit_identity

    return hit_identity(hit.feature, hit.owner)


def _along_ray(origin: Float3, direction: Float3, point) -> float:
    return (Float3.of(point) - origin).dot(direction)


def order_along_ray(
    hits: List['OwnedFeatureHit'], depth_of: Dict[Tuple[str, int], float], separation: float,
) -> List['OwnedFeatureHit']:
    """Return `hits` sorted by depth group along the ray, then by the library's order. Groups start `separation` apart."""
    from kumiki.csg.cutcsg import feature_hit_sort_key

    starts = _depth_groups(hits, depth_of, separation)
    return sorted(hits, key=lambda hit: (starts[_hit_key(hit)], feature_hit_sort_key(hit)))


def _depth_groups(
    hits: List['OwnedFeatureHit'], depth_of: Dict[Tuple[str, int], float], separation: float,
) -> Dict[Tuple[str, int], float]:
    """Return each hit's depth group, named by the depth the group starts at."""
    depth = lambda hit: depth_of.get(_hit_key(hit), math.inf)
    starts: Dict[Tuple[str, int], float] = {}
    start: Optional[float] = None
    for hit in sorted(hits, key=depth):
        if start is None or depth(hit) - start > separation:
            start = depth(hit)
        starts[_hit_key(hit)] = start
    return starts


def non_real_features_along_ray(
    root: 'CutCSG', local_ray: LocalRay, tolerances: 'FeatureTestTolerances',
    extents: Optional['FeatureExtents'] = None,
) -> List['OwnedFeatureHit']:
    """Return non-real features within the edge tolerance of the ray, in timber-local space.

    Bounded by each feature's own extent. With `extents` (a drawing view), planes seen edge-on too.
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
        if isinstance(located, Plane) and extents is not None:
            hit = OwnedFeatureHit(feature=feature, owner=owner)
            if _plane_on_ray(hit, extents, origin, direction, tolerance) is not None:
                found.append(hit)
            return
        if not isinstance(located, Line):
            return
        declared = feature.declared_ends(owner)
        if declared is None:
            return
        if ray_reaches_segment(origin, direction, (Float3.of(declared[0]), Float3.of(declared[1])), tolerance):
            found.append(OwnedFeatureHit(feature=feature, owner=owner))

    def walk(node: 'CutCSG') -> None:
        for feature in node.get_declared_features():
            if not feature.real:
                consider(feature, node)
        for child in csg_children(node):
            walk(child)

    walk(root)
    return found





def _plane_on_ray(hit: 'OwnedFeatureHit', extents: 'FeatureExtents', origin: Float3,
                  direction: Float3, tolerance: float) -> Optional[Float3]:
    """Return where the ray runs through a plane feature seen edge-on, within `tolerance` and its extent, or None."""
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
    extent = extents.of(hit.feature, hit.owner)
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
    """Return whether the ray passes within `tolerance` of the segment `ends`."""
    return ray_nears_segment(origin, direction, ends, tolerance) is not None


def ray_nears_segment(origin, direction, ends, tolerance: float) -> Optional[Float3]:
    """Return the point of segment `ends` nearest the ray, if within `tolerance`, else None.

    `direction` must be unit. Only points in front of the ray origin count.
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
    """Return the derived edge or point at the click, if one is the best hit there."""
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
    """Return the outward normal at the pick and the nearest of the timber's six faces, in timber-local space.

    The normal is `target`'s, flipped if `target` is subtractive in `local_csg`. (None, None) if unknown.
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
    """Return the node `path` names under `csg`, or the deepest it reaches (feature_paths.walk_labels)."""
    return walk_labels(csg, path)[0]


def navigate_csg_one_level(
    node: 'CutCSG',
    local_pt: Float3,
    current_path: List[str],
    eps: float = 1e-4,
    segments: Optional[Dict[int, str]] = None,
) -> Tuple[List[str], Any, Optional[str]]:
    """Step one level into `node` toward the click.

    Returns (new_path, target_csg, feature_label_or_None). `segments` numbers the children when
    drilling through an unlabelled compound.
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
    """Walk from the root to the deepest labelled node at the click, and name the face there."""

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
    """Return a cheap could-this-point-be-on-`csg` test from its bounding box, or None if the box can't help."""
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
    frame: LocalFrame,
    eps: float = 1e-4,
    root_csg: Optional['CutCSG'] = None,
    selected_path: Optional[List[str]] = None,
    selected_ref: Optional[Any] = None,
    feature_label: Optional[str] = None,
    edge_feature: Optional['CSGFeature'] = None,
    feature_type: Optional[str] = None,
) -> Tuple[List[float], List[int], int, int]:
    """Return the rendered triangles belonging to `target_csg`.

    Vertices and indices are flat global-space lists. Returns (vertices, indices, matched_tris, total_tris).
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

    # Broadphase on the target's box. An edge with a known line has no triangles to light.
    if feature_type in ("EDGE", "POINT") and edge_feature is None:
        return [], [], 0, len(mesh_indices) // 3

    inside_box = aabb_filter(target_csg, eps)

    # The declared feature to match, looked up once; the loop also checks the boundary.
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
        local_c = frame.point([cx, cy, cz])
        if inside_box is not None and not inside_box(local_c):
            continue
        # The feature's own plane first: far cheaper than the tree's boundary, and most triangles fail it.
        if wanted_feature is not None and not wanted_feature.test_point_unbounded(target_csg, to_v3(local_c), eps):
            continue
        if csg_point_on_boundary(target_csg, local_c, eps):
            if edge_feature is not None:
                # Last fallback, when the edge couldn't be cropped: light triangles with two
                # vertices on the edge's (unbounded) line.
                on_edge = 0
                for corner in (i0, i1, i2):
                    corner_local = frame.point([
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
    """Return where a click lands in the tree: straight to the feature, or with Ctrl one level per click from `current_path`."""
    if not ctrl_click:
        return navigate_csg_to_leaf(root, local_pt, eps)
    node = root
    if current_path:
        node = resolve_csg_at_path(root, current_path)
        if not csg_point_on_boundary(node, local_pt, eps):
            node, current_path = root, []
    return navigate_csg_one_level(node, local_pt, current_path, eps)


class Candidates(NamedTuple):
    """Features under the pointer: `hits[:visible_count]` can be taken; the rest are hidden."""
    hits: List['OwnedFeatureHit']
    visible_count: int


def find_candidates(
    root: 'CutCSG', local_pt: Float3, eps: float, tolerances: 'FeatureTestTolerances',
    local_ray: Optional[LocalRay],
) -> Candidates:
    """Return the features at the point on one member, all takeable. Drawing views use drawing_candidates."""
    hits = features_at_point(root, local_pt, eps, tolerances, local_ray=local_ray)
    return Candidates(hits, len(hits))


def sight_blocker(transform: Transform, occluders: List[Tuple['CutCSG', Transform]],
                  direction: Float3) -> Callable[[Float3], bool]:
    """Return `blocked(place)`: whether an occluder hides a place (local to `transform`) looking along `direction`."""
    from kumiki.drawings.visibility import hidden_at
    from kumiki.rule import as_ndarray

    look = as_ndarray(transform.local_to_global_direction(direction.v3()))
    return lambda place: hidden_at(as_ndarray(transform.local_to_global(place.v3())), look, occluders)


def best_matching_candidate(hits: List['OwnedFeatureHit'], timber: 'PerfectTimberWithin', held: Any, look: Any,
                            space: Any) -> Optional[int]:
    """Return the candidate that best completes the measurement being made, or None.

    Prefers one that admits a measurement with the held feature, then one of the held feature's type.
    """
    from kumiki.csg.feature_paths import FeatureHandle

    return best_matching_handle([FeatureHandle(timber=timber, hit=hit) for hit in hits], held, look, space)


def best_matching_handle(handles: List[Any], held: Any, look: Any, space: Any) -> Optional[int]:
    """best_matching_candidate over FeatureHandles that may be on different timbers."""
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
    """What a pick chose: the node (`path`, `node`), the feature (`label`, `kind`), an edge or point to draw, and the candidate `hit`."""
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
        """Return the chosen feature, the node it is shown under, and its owner."""
        if self.hit is None:
            return None
        owner = self.node if self.edge_feature is not None else self.hit.owner
        return (self.hit.feature, owner, self.hit.feature.locate_simple_unbounded(owner))


def pick_from_candidate(root: 'CutCSG', hit: 'OwnedFeatureHit') -> Optional[Pick]:
    """Return the Pick for a chosen feature, or None if its owner isn't in the tree."""
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
    """Return which feature under the pointer is wanted, as a Pick.

    In order: the one the caller names (Tab, the menu); `preferred`; in a drawing the first
    candidate; then a derived edge or point at the click, a declared one, or the navigated face.
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
    """A derived feature's owner path and each parent's (path, name)."""
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


def non_real_plane_outline(feature: 'CSGFeature', owner: 'CutCSG',
                           extents: 'FeatureExtents') -> Optional[List[WorldSegment]]:
    """Return a non-real plane's outline in world space (its extent's outline), or None for anything else."""
    from kumiki.geometry import Plane

    if feature.real or not isinstance(feature.locate_simple_unbounded(owner), Plane):
        return None
    extent = extents.of(feature, owner)
    return None if extent is None else _world_segments(extent.outline(), extents.timber)


class PlaneOutline(NamedTuple):
    """A plane's outline in world space: its normal and flat segment ends."""
    normal: List[float]
    positions: List[float]


def perfect_reference_outlines(extents: 'FeatureExtents', centerplanes: bool) -> List[PlaneOutline]:
    """Return the rough body's perfect references cropped to the cut timber, in world space: centerplanes, and
    perfect faces the rough body has no face for (ptw.*).
    """
    from kumiki.csg.cutcsg import Difference, FeatureNature, MidplaneFeature, PlaneFeature
    from kumiki.geometry import Plane
    from kumiki.rule import create_v3

    root, timber = extents.root, extents.timber
    assert root is not None
    body = root.base if isinstance(root, Difference) else root
    kind = MidplaneFeature if centerplanes else PlaneFeature
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
    """A member a drawing pick may land on: key, its cut timber's FeatureExtents (tree and timber), and where
    the ray met its surface (local)."""
    key: str
    extents: 'FeatureExtents'
    surface_point: Optional[Float3]


class MemberCandidate(NamedTuple):
    """A feature under the pointer and the member it is on."""
    member: str
    timber: 'PerfectTimberWithin'
    candidate: PointerCandidate


def drawing_candidates(
    members: List[DrawnMember], world_ray: LocalRay, tolerances: 'FeatureTestTolerances',
    blocked_for: Callable[[str], Optional[Callable[[Float3], bool]]],
) -> Tuple[List[MemberCandidate], int]:
    """Return every feature under the pointer in a drawing view, across all members drawn there, and how many are visible.

    Each member is searched along the ray in its own space; results are ordered together by depth.
    Visible first, then hidden (drawn_over, `blocked_for`), each nearest first.
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
        timber, root = member.extents.timber, member.extents.root
        assert root is not None
        rotation = LocalFrame.of(timber.transform)
        local_ray = (rotation.point(origin), rotation.direction(direction))
        for candidate in candidates_under_pointer(root, member.surface_point, tolerances, local_ray, member.extents):
            found.append(MemberCandidate(member.key, timber, candidate))

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
