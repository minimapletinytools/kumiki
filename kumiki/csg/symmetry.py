"""Which cut timbers are the same piece: identical, turned (a rotation), or mirrored (a reflection).

For frame authors who want to solve or draw a piece once for all its copies. Nothing here decides
that; it only says which timbers match, how, and what differs between them that the geometry
doesn't settle (labels, reference features, tags).

How two timbers are compared, in their own local frames (x across the width, y across the height,
z along the length):

- Their CSG trees must have the same shape: the same node types, in the same order.
- A symmetry is one of the 16 ways of flipping the three axes and swapping width with height. For
  each, walk both trees in step, mapping the second's primitives through it:
  - what doesn't depend on where the piece sits -- directions, sizes, radii, profile shapes -- must
    agree outright;
  - where it sits gives equations linear in one unknown shift (a half space's offset, a prism's
    axis line and its ends, ...), solved together at the end.
- It fits when every equation holds. Its determinant says which kind: +1 a rotation (the piece can
  simply be turned over), -1 a reflection (a mirror image, a "handed" piece).

No mirrored trees are built: a reflected prism would have a left-handed frame, which nothing else
expects.

Trees are compared, not solids, so it never claims a match that isn't there. The other way round,
two pieces built differently -- a cutter placed otherwise inside material removed anyway -- match
only under the symmetries their trees agree on: oscarshed's side girts are identical, and come out
a reflection, because their peg-hole cutters run from opposite faces.
"""

import itertools
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

import numpy as np

from .cutcsg import (ConvexPolygonExtrusion, ConvexPolygonSimpleLoft, CutCSG, Cylinder, Difference, EmptyCSG,
                     HalfSpace, HasFeatures, Intersection, RectangularPrism, SolidUnion, csg_children)
from .edges_on_csg import convex_hull_2d
from .feature_paths import label_name
from .pathcsg import PathExtrusion, decompose_path_into_convex_pieces
from ..rule import as_ndarray

if TYPE_CHECKING:
    from ..timber import CutTimber

__all__ = ["SymmetryKind", "Symmetry", "TimberMatch", "TimberGroup", "csg_symmetries", "timber_symmetries",
           "match_timbers"]

#: How far apart, in metres, two things may be and still be the same place.
DEFAULT_TOLERANCE = 1e-6


class SymmetryKind(Enum):
    IDENTICAL = "identical"
    ROTATION = "rotation"
    REFLECTION = "reflection"


@dataclass(frozen=True, eq=False)
class Symmetry:
    """A way one piece maps onto another, in their local frames: a point `p` of the second is at
    `matrix @ p + shift` on the first."""
    matrix: np.ndarray
    shift: np.ndarray
    kind: SymmetryKind
    #: e.g. "reflection (swap width/height)", "rotation (flip width, flip length)".
    description: str


# --- the candidate symmetries ----------------------------------------------------------------

_AXIS_NAMES = ("width", "height", "length")


def _candidates() -> List[np.ndarray]:
    """The 16 axis flips and width/height swaps, the identity first, then rotations, then reflections."""
    found = []
    for swap in (False, True):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            matrix = np.diag(signs)
            if swap:
                matrix = matrix[[1, 0, 2]]
            found.append(matrix)
    found.sort(key=lambda m: (not np.array_equal(m, np.eye(3)), round(float(np.linalg.det(m))) < 0))
    return found


_CANDIDATES = _candidates()


def _kind(matrix: np.ndarray) -> SymmetryKind:
    if np.array_equal(matrix, np.eye(3)):
        return SymmetryKind.IDENTICAL
    return SymmetryKind.ROTATION if np.linalg.det(matrix) > 0 else SymmetryKind.REFLECTION


def _describe(matrix: np.ndarray) -> str:
    kind = _kind(matrix)
    if kind is SymmetryKind.IDENTICAL:
        return "identical"
    parts = ["swap width/height"] if matrix[0, 1] != 0 else []
    parts += [f"flip {_AXIS_NAMES[row]}" for row in range(3) if matrix[row].sum() < 0]
    return f"{kind.value} ({', '.join(parts)})"


# --- comparing trees under one symmetry ------------------------------------------------------

#: One equation on the shift: row . shift = value.
Equation = Tuple[np.ndarray, float]


class _Mismatch(Exception):
    """The trees differ under this symmetry, whatever the shift."""


def _unit(vector) -> np.ndarray:
    vector = np.asarray(as_ndarray(vector), dtype=float)
    return vector / np.linalg.norm(vector)


def _parallel(one: np.ndarray, other: np.ndarray, tolerance: float) -> float:
    """+1 or -1 as unit `one` runs with or against unit `other`; a mismatch if they aren't parallel."""
    if np.linalg.norm(np.cross(one, other)) > tolerance:
        raise _Mismatch
    return 1.0 if float(one @ other) > 0 else -1.0


def _same(one: float, other: float, tolerance: float) -> None:
    if abs(one - other) > tolerance:
        raise _Mismatch


def _frame(transform) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A transform's local x, y and z axes and its origin, as floats."""
    matrix = np.array(transform.orientation.matrix.tolist(), dtype=float)
    return matrix[:, 0], matrix[:, 1], matrix[:, 2], as_ndarray(transform.position)


def _extent(axis_dot_origin: float, start, end) -> Tuple[Optional[float], Optional[float]]:
    """Where a solid runs along its axis, absolutely: None for a side that runs to infinity."""
    return (None if start is None else axis_dot_origin + float(start),
            None if end is None else axis_dot_origin + float(end))


def _extent_equations(axis: np.ndarray, extent_a, extent_b, sense: float, tolerance: float) -> List[Equation]:
    """Each finite end of the first solid's extent along `axis` is the second's, carried over.

    A point q of the second is at m q + shift; along the first's axis that reads
    sense * (its own axis . q) + axis . shift. Running the other way, its ends swap.
    """
    low_b, high_b = extent_b
    mapped = ((None if low_b is None else sense * low_b), (None if high_b is None else sense * high_b))
    if sense < 0:
        mapped = (mapped[1], mapped[0])
    equations = []
    for end_a, end_b in zip(extent_a, mapped):
        if (end_a is None) != (end_b is None):
            raise _Mismatch
        if end_a is not None:
            equations.append((axis, end_a - end_b))
    return equations


def _across_equations(axis: np.ndarray, point_a: np.ndarray, mapped_b: np.ndarray) -> List[Equation]:
    """The first point is the second (already mapped by the matrix) plus the shift, across `axis`."""
    helper = np.eye(3)[int(np.argmin(np.abs(axis)))]
    first = np.cross(axis, helper)
    first /= np.linalg.norm(first)
    second = np.cross(axis, first)
    return [(direction, float(direction @ (point_a - mapped_b))) for direction in (first, second)]


def _same_profile(points_a: np.ndarray, points_b: np.ndarray, tolerance: float) -> None:
    """Two point sets the same shape and place relative to their centroids."""
    if len(points_a) != len(points_b):
        raise _Mismatch
    relative_a = points_a - points_a.mean(axis=0)
    relative_b = points_b - points_b.mean(axis=0)
    for point in relative_a:
        if np.min(np.linalg.norm(relative_b - point, axis=1)) > tolerance:
            raise _Mismatch


def _half_space(a: HalfSpace, b: HalfSpace, matrix: np.ndarray, tolerance: float) -> List[Equation]:
    # Inside is normal . p >= offset; with unit normals, the offset is a distance.
    normal_a, length_a = as_ndarray(a.normal), float(np.linalg.norm(as_ndarray(a.normal)))
    normal_b, length_b = as_ndarray(b.normal), float(np.linalg.norm(as_ndarray(b.normal)))
    unit_a, mapped = normal_a / length_a, matrix @ (normal_b / length_b)
    if np.linalg.norm(unit_a - mapped) > tolerance:
        raise _Mismatch
    return [(unit_a, float(a.offset) / length_a - float(b.offset) / length_b)]


def _prism(a: RectangularPrism, b: RectangularPrism, matrix: np.ndarray, tolerance: float) -> List[Equation]:
    width_a, height_a, length_a, origin_a = _frame(a.transform)
    width_b, height_b, length_b, origin_b = _frame(b.transform)
    sense = _parallel(length_a, matrix @ length_b, tolerance)
    sizes_a = (float(a.size[0]), float(a.size[1]))
    sizes_b = (float(b.size[0]), float(b.size[1]))
    # The section's sides as lines with lengths, either way round.
    mapped_width = matrix @ width_b
    if np.linalg.norm(np.cross(width_a, mapped_width)) <= tolerance:
        _same(sizes_a[0], sizes_b[0], tolerance)
        _same(sizes_a[1], sizes_b[1], tolerance)
    else:
        _parallel(height_a, mapped_width, tolerance)
        _same(sizes_a[1], sizes_b[0], tolerance)
        _same(sizes_a[0], sizes_b[1], tolerance)
    return (_across_equations(length_a, origin_a, matrix @ origin_b)
            + _extent_equations(length_a, _extent(float(length_a @ origin_a), a.start_distance, a.end_distance),
                                _extent(float(length_b @ origin_b), b.start_distance, b.end_distance),
                                sense, tolerance))


def _cylinder(a: Cylinder, b: Cylinder, matrix: np.ndarray, tolerance: float) -> List[Equation]:
    axis_a, axis_b = _unit(a.axis_direction), _unit(b.axis_direction)
    sense = _parallel(axis_a, matrix @ axis_b, tolerance)
    _same(float(a.radius), float(b.radius), tolerance)
    position_a, position_b = as_ndarray(a.position), as_ndarray(b.position)
    return (_across_equations(axis_a, position_a, matrix @ position_b)
            + _extent_equations(axis_a, _extent(float(axis_a @ position_a), a.start_distance, a.end_distance),
                                _extent(float(axis_b @ position_b), b.start_distance, b.end_distance),
                                sense, tolerance))


def _profile_points(transform, points: Sequence, z: float = 0.0) -> np.ndarray:
    """A profile's corners (its convex hull) lifted into the node's space at `z` along its axis."""
    across, up, axis, origin = _frame(transform)
    hull = convex_hull_2d([(float(point[0]), float(point[1])) for point in points])
    return np.array([origin + axis * z + across * x + up * y for x, y in hull])


def _extrusion(a: ConvexPolygonExtrusion, b: ConvexPolygonExtrusion, matrix: np.ndarray,
               tolerance: float) -> List[Equation]:
    _, _, axis_a, origin_a = _frame(a.transform)
    _, _, axis_b, origin_b = _frame(b.transform)
    sense = _parallel(axis_a, matrix @ axis_b, tolerance)
    profile_a = _profile_points(a.transform, a.points)
    profile_b = _profile_points(b.transform, b.points) @ matrix.T
    # Compared across the axis: where along it the profile was drawn is the extent's business.
    flatten = lambda points: points - np.outer(points @ axis_a, axis_a)
    _same_profile(flatten(profile_a), flatten(profile_b), tolerance)
    return (_across_equations(axis_a, profile_a.mean(axis=0), profile_b.mean(axis=0))
            + _extent_equations(axis_a, _extent(float(axis_a @ origin_a), a.start_distance, a.end_distance),
                                _extent(float(axis_b @ origin_b), b.start_distance, b.end_distance),
                                sense, tolerance))


def _loft(a: ConvexPolygonSimpleLoft, b: ConvexPolygonSimpleLoft, matrix: np.ndarray,
          tolerance: float) -> List[Equation]:
    ends_a = [_profile_points(a.transform, a.bottom_points, float(a.bottom_points_z_pos)),
              _profile_points(a.transform, a.top_points, float(a.top_points_z_pos))]
    ends_b = [_profile_points(b.transform, b.bottom_points, float(b.bottom_points_z_pos)) @ matrix.T,
              _profile_points(b.transform, b.top_points, float(b.top_points_z_pos)) @ matrix.T]
    for order in (ends_b, ends_b[::-1]):
        try:
            # Each end the same shape, and the same step from one end to the other.
            for one, other in zip(ends_a, order):
                _same_profile(one, other, tolerance)
            step_a = ends_a[1].mean(axis=0) - ends_a[0].mean(axis=0)
            step_b = order[1].mean(axis=0) - order[0].mean(axis=0)
            if np.linalg.norm(step_a - step_b) > tolerance:
                raise _Mismatch
        except _Mismatch:
            continue
        centre_a, centre_b = ends_a[0].mean(axis=0), order[0].mean(axis=0)
        return [(direction, float(direction @ (centre_a - centre_b))) for direction in np.eye(3)]
    raise _Mismatch


def _path_extrusion(a: PathExtrusion, b: PathExtrusion, matrix: np.ndarray, tolerance: float) -> List[Equation]:
    """As the convex extrusions it is cut into, matched in any order: a mirrored path's pieces come
    out in another order."""
    def pieces(path_extrusion: PathExtrusion) -> List[ConvexPolygonExtrusion]:
        return [ConvexPolygonExtrusion(points=piece, transform=path_extrusion.transform,
                                       start_distance=path_extrusion.start_distance,
                                       end_distance=path_extrusion.end_distance)
                for piece in decompose_path_into_convex_pieces(path_extrusion.path, tolerance=1e-4)]
    pieces_a, unused = pieces(a), pieces(b)
    if len(pieces_a) != len(unused):
        raise _Mismatch
    equations: List[Equation] = []
    for piece in pieces_a:
        for index, other in enumerate(unused):
            try:
                equations += _extrusion(piece, other, matrix, tolerance)
            except _Mismatch:
                continue
            del unused[index]
            break
        else:
            raise _Mismatch
    return equations


def _walk(a: CutCSG, b: CutCSG, matrix: np.ndarray, tolerance: float,
          known: Sequence[Equation] = ()) -> List[Equation]:
    """Both trees in step under `matrix`: every equation on the shift, or a mismatch.

    A difference's cuts and a union's children are matched in any order: turned end for end, one
    end's joint is the other end's. Each child takes the first same-shaped partner whose equations
    agree with everything matched so far (`known`).
    """
    if type(a) is not type(b):
        raise _Mismatch
    if isinstance(a, EmptyCSG):
        return []
    if isinstance(a, Difference):
        assert isinstance(b, Difference)
        base = _walk(a.base, b.base, matrix, tolerance, known)
        return base + _unordered(a.subtract, b.subtract, matrix, tolerance, [*known, *base])
    if isinstance(a, SolidUnion):
        assert isinstance(b, SolidUnion)
        return _unordered(a.children, b.children, matrix, tolerance, list(known))
    if isinstance(a, Intersection):
        assert isinstance(b, Intersection)
        return _unordered([a.left, a.right], [b.left, b.right], matrix, tolerance, list(known))
    if isinstance(a, HalfSpace) and isinstance(b, HalfSpace):
        return _half_space(a, b, matrix, tolerance)
    if isinstance(a, RectangularPrism) and isinstance(b, RectangularPrism):
        return _prism(a, b, matrix, tolerance)
    if isinstance(a, Cylinder) and isinstance(b, Cylinder):
        return _cylinder(a, b, matrix, tolerance)
    if isinstance(a, ConvexPolygonExtrusion) and isinstance(b, ConvexPolygonExtrusion):
        return _extrusion(a, b, matrix, tolerance)
    if isinstance(a, ConvexPolygonSimpleLoft) and isinstance(b, ConvexPolygonSimpleLoft):
        return _loft(a, b, matrix, tolerance)
    if isinstance(a, PathExtrusion) and isinstance(b, PathExtrusion):
        return _path_extrusion(a, b, matrix, tolerance)
    raise _Mismatch  # a primitive this module can't compare: never claim a match


def _unordered(children_a: Sequence[CutCSG], children_b: Sequence[CutCSG], matrix: np.ndarray,
               tolerance: float, known: List[Equation]) -> List[Equation]:
    """Children matched one to one in any order, each to the first that agrees with what is known."""
    if len(children_a) != len(children_b):
        raise _Mismatch
    unused = list(children_b)
    equations: List[Equation] = []
    for child in children_a:
        shape = _shape(child)
        for index, other in enumerate(unused):
            if _shape(other) != shape:
                continue
            try:
                found = _walk(child, other, matrix, tolerance, [*known, *equations])
            except _Mismatch:
                continue
            if _shift([*known, *equations, *found], tolerance) is None:
                continue
            equations += found
            del unused[index]
            break
        else:
            raise _Mismatch
    return equations


def _shift(equations: Sequence[Equation], tolerance: float) -> Optional[np.ndarray]:
    """The one shift every equation agrees on, or None. Directions nothing pins down are left at 0."""
    if not equations:
        return np.zeros(3)
    rows = np.array([row for row, _ in equations])
    values = np.array([value for _, value in equations])
    shift = np.linalg.lstsq(rows, values, rcond=None)[0]
    return shift if float(np.max(np.abs(rows @ shift - values))) <= tolerance else None


def csg_symmetries(a: CutCSG, b: CutCSG, tolerance: float = DEFAULT_TOLERANCE) -> List[Symmetry]:
    """Every way tree `b` maps onto tree `a`, each in its own local frame (x width, y height, z
    length): the identity first, then rotations, then reflections. Empty if none does."""
    found = []
    for matrix in _CANDIDATES:
        try:
            shift = _shift(_walk(a, b, matrix, tolerance), tolerance)
        except _Mismatch:
            continue
        if shift is not None:
            found.append(Symmetry(matrix=matrix, shift=shift, kind=_kind(matrix), description=_describe(matrix)))
    return found


def timber_symmetries(a: 'CutTimber', b: 'CutTimber', tolerance: float = DEFAULT_TOLERANCE) -> List[Symmetry]:
    """Every way cut timber `b` is cut timber `a`, rough stock and cuts and all. `a` with itself
    gives the piece's own symmetries (a stretcher the same at both ends is its own mirror)."""
    return csg_symmetries(a.render_timber_with_cuts_csg_local(), b.render_timber_with_cuts_csg_local(), tolerance)


# --- grouping a frame's timbers --------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class TimberMatch:
    """A timber that is its group's representative over again.

    `kind` is the best that fits: IDENTICAL if the identity does, else ROTATION if any rotation does
    (it can be turned into the representative, even when a mirror fits too), else REFLECTION (only a
    mirror fits: a handed piece). `symmetries` are all that fit. `differences` are what the geometry
    doesn't settle and the caller may care about; they never stop a match.
    """
    cut: 'CutTimber'
    kind: SymmetryKind
    symmetries: Tuple[Symmetry, ...]
    differences: Tuple[str, ...]


@dataclass(frozen=True, eq=False)
class TimberGroup:
    """One piece: the first timber found of it, and every other that matches it."""
    representative: 'CutTimber'
    matches: Tuple[TimberMatch, ...]


def _shape(node: CutCSG) -> Tuple:
    """A tree's shape: node types and children, in order."""
    return (type(node).__name__, tuple(_shape(child) for child in csg_children(node)))


def _labels(node: CutCSG) -> Tuple:
    return (label_name(node), tuple(_labels(child) for child in csg_children(node)))


def _authored_features(node: CutCSG) -> List[Tuple]:
    """What an author named or changed on the tree's nodes: overrides and extras, with properties."""
    found = []
    if isinstance(node, HasFeatures):
        found += [("override", repr(override)) for override in node.feature_overrides]
        found += [("extra", extra.name, repr(extra.properties)) for extra in node.extra_features]
    for child in csg_children(node):
        found += _authored_features(child)
    return found


def _differences(a: 'CutTimber', b: 'CutTimber') -> Tuple[str, ...]:
    tree_a, tree_b = a.render_timber_with_cuts_csg_local(), b.render_timber_with_cuts_csg_local()
    differences = []
    if _labels(tree_a) != _labels(tree_b):
        differences.append("node labels")
    if _authored_features(tree_a) != _authored_features(tree_b):
        differences.append("authored features")
    references = lambda cut: tuple(feature.name for feature in (getattr(cut.timber.ticket, "reference_features", ()) or ()))
    if references(a) != references(b):
        differences.append(f"reference features: {list(references(a))} vs {list(references(b))}")
    tags = lambda cut: sorted(tag.name for tag in cut.timber.ticket.tags)
    if tags(a) != tags(b):
        differences.append(f"tags: {tags(a)} vs {tags(b)}")
    return tuple(differences)


def match_timbers(cut_timbers: Sequence['CutTimber'], tolerance: float = DEFAULT_TOLERANCE) -> List[TimberGroup]:
    """The distinct pieces among `cut_timbers`, in the order first met.

    Each timber joins the first group whose representative it matches (timber_symmetries), else
    starts its own. Only timbers whose trees have the same shape are compared.
    """
    groups: List[Tuple['CutTimber', Tuple, List[TimberMatch]]] = []
    for cut in cut_timbers:
        shape = _shape(cut.render_timber_with_cuts_csg_local())
        for representative, representative_shape, matches in groups:
            if representative_shape != shape:
                continue
            symmetries = timber_symmetries(representative, cut, tolerance)
            if not symmetries:
                continue
            kinds = {symmetry.kind for symmetry in symmetries}
            kind = next(kind for kind in SymmetryKind if kind in kinds)
            matches.append(TimberMatch(cut=cut, kind=kind, symmetries=tuple(symmetries),
                                       differences=_differences(representative, cut)))
            break
        else:
            groups.append((cut, shape, []))
    return [TimberGroup(representative=representative, matches=tuple(matches))
            for representative, _shape_of, matches in groups]
