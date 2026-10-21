"""Path-based CSG: FancyPath, a closed 2D boundary of straight and arc segments, and PathExtrusion,
which extrudes one along its local Z.

Unlike ConvexPolygonExtrusion the boundary may be concave. Curved sides carry no plane, so they
are never measurable.
"""

import math
import warnings
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from ..rule import sqrt as sym_sqrt

from ..rule import *
from ..geometry import Plane
from .cutcsg import (
    ConvexPolygonExtrusion,
    AxisAlignedBoundingBox,
    CSGFeature,
    CSGFeatureType,
    CurvedFaceFeature,
    CutCSG,
    FaceFeature,
    FeatureKey,
    HasFeatures,
    LocatedFeatureGeometry,
    _finite_midpoint,
    ExtrusionCap,
    ExtrusionFeatureKey,
    OwnedFeatureHit,
    Profile,
)
from .carriers import Carrier

if TYPE_CHECKING:
    from .cross_sections import Sides
    from .edges_on_csg import SolidBounds


# ============================================================================
# PathSegment
# ============================================================================

@dataclass(frozen=True)
class PathSegment(ABC):
    """One segment of a closed FancyPath, in the path's local 2D plane."""

    @property
    @abstractmethod
    def start(self) -> V2: ...

    @property
    @abstractmethod
    def end(self) -> V2: ...

    @abstractmethod
    def is_planar(self) -> bool:
        """Return whether extruding this segment gives a flat side."""

    @abstractmethod
    def ray_crossings(self, y: Numeric, inclusive: bool = False, eps: Optional[Numeric] = None) -> List[Numeric]:
        """Return the x values where this segment crosses height y.

        `inclusive=False` counts each crossing at a shared vertex once (for parity tests);
        `inclusive=True` includes the segment's own endpoints (for convex decomposition).
        """

    @abstractmethod
    def v_extrema(self) -> List[Numeric]:
        """Return the y values strictly between the endpoints where x(y) turns (e.g. an arc's pole)."""

    @abstractmethod
    def closest_point(self, point: V2, eps: Optional[Numeric] = None) -> V2:
        """Return the nearest point on this segment to `point`."""

    @abstractmethod
    def outward_local_normal(self, point: V2, eps: Optional[Numeric] = None) -> V2:
        """Return the 2D outward normal at `point` on this segment, assuming a CCW path."""

    @abstractmethod
    def bounds(self) -> Tuple[V2, V2]:
        """Return this segment's (min_corner, max_corner)."""

    @abstractmethod
    def signed_area_contribution(self) -> Numeric:
        """Return this segment's term in FancyPath.signed_area."""

    @abstractmethod
    def tessellate(self, tolerance: float) -> List[V2]:
        """Return points approximating this segment for meshing, excluding `start` and including `end`."""

    @abstractmethod
    def tessellate_with_extra_breaks(self, other_breaks: List[Numeric], tolerance: float) -> List[V2]:
        """Like tessellate(), plus a vertex at each y in `other_breaks` within this segment's y range.

        Keeps the wall mesh's vertices matching the cap pieces' seams.
        """

    @abstractmethod
    def sample_interior(self, point_lo: V2, point_hi: V2, tolerance: float) -> List[V2]:
        """Return mesh points strictly between `point_lo` and `point_hi` on this segment, in that order.

        Uses the same sample grid as tessellate() so cap and wall meshes share vertices. Empty for a
        straight segment.
        """

    @abstractmethod
    def reverse(self) -> 'PathSegment':
        """Return this segment traversed from `end` to `start`."""


def _right_perpendicular(v: V2) -> V2:
    """Return a 2D vector rotated 90 degrees clockwise: the outward normal of a CCW tangent."""
    return create_v2(v[1], -v[0])


# ============================================================================
# StraightSegment
# ============================================================================

@dataclass(frozen=True)
class StraightSegment(PathSegment):
    """A straight segment of a path, between two 2D points."""

    line_start: V2
    line_end: V2

    @property
    def start(self) -> V2:
        return self.line_start

    @property
    def end(self) -> V2:
        return self.line_end

    def is_planar(self) -> bool:
        return True

    def ray_crossings(self, y: Numeric, inclusive: bool = False, eps: Optional[Numeric] = None) -> List[Numeric]:
        y0, y1 = self.line_start[1], self.line_end[1]
        if safe_zero_test(y1 - y0, eps=eps):
            return []  # horizontal segment: no crossings, doesn't bound any band

        if inclusive:
            lo, hi = (y0, y1) if safe_compare(y0, y1, Comparison.LE, eps=eps) else (y1, y0)
            hit = safe_compare(lo, y, Comparison.LE, eps=eps) and safe_compare(y, hi, Comparison.LE, eps=eps)
        else:
            hit = (
                (safe_compare(y0, y, Comparison.LE, eps=eps) and safe_compare(y, y1, Comparison.LT, eps=eps))
                or (safe_compare(y1, y, Comparison.LE, eps=eps) and safe_compare(y, y0, Comparison.LT, eps=eps))
            )
        if not hit:
            return []

        t = (y - y0) / (y1 - y0)
        x = self.line_start[0] + t * (self.line_end[0] - self.line_start[0])
        return [x]

    def v_extrema(self) -> List[Numeric]:
        return []

    def closest_point(self, point: V2, eps: Optional[Numeric] = None) -> V2:
        edge = self.line_end - self.line_start
        edge_len_sq = edge[0] ** 2 + edge[1] ** 2
        # Degeneracy is a property of the path, not of how close the caller
        # clicked, so this takes no query tolerance.
        if safe_zero_test_sq(edge_len_sq):
            return self.line_start

        to_point = point - self.line_start
        t = (to_point[0] * edge[0] + to_point[1] * edge[1]) / edge_len_sq
        if safe_compare(t, 0, Comparison.LT, eps=eps):
            t = scalar(0)
        elif safe_compare(t, 1, Comparison.GT, eps=eps):
            t = scalar(1)
        return self.line_start + edge * t

    def outward_local_normal(self, point: V2, eps: Optional[Numeric] = None) -> V2:
        edge = self.line_end - self.line_start
        return safe_normalize_vector(_right_perpendicular(edge))

    def bounds(self) -> Tuple[V2, V2]:
        x0, y0 = self.line_start[0], self.line_start[1]
        x1, y1 = self.line_end[0], self.line_end[1]
        min_x = x0 if safe_compare(x0, x1, Comparison.LE) else x1
        max_x = x1 if safe_compare(x0, x1, Comparison.LE) else x0
        min_y = y0 if safe_compare(y0, y1, Comparison.LE) else y1
        max_y = y1 if safe_compare(y0, y1, Comparison.LE) else y0
        return create_v2(min_x, min_y), create_v2(max_x, max_y)

    def signed_area_contribution(self) -> Numeric:
        x0, y0 = self.line_start[0], self.line_start[1]
        x1, y1 = self.line_end[0], self.line_end[1]
        return (x0 * y1 - x1 * y0) / scalar(2)

    def tessellate(self, tolerance: float) -> List[V2]:
        return [self.line_end]

    def tessellate_with_extra_breaks(self, other_breaks: List[Numeric], tolerance: float) -> List[V2]:
        y0, y1 = self.line_start[1], self.line_end[1]
        if safe_zero_test(y1 - y0):
            return [self.line_end]  # horizontal: no y ever falls strictly inside its range
        lo, hi = (y0, y1) if safe_compare(y0, y1, Comparison.LE) else (y1, y0)

        inserts = []  # (t, point), t in (0, 1)
        for y in other_breaks:
            if safe_compare(y, lo, Comparison.GT) and safe_compare(y, hi, Comparison.LT):
                t = (y - y0) / (y1 - y0)
                x = self.line_start[0] + t * (self.line_end[0] - self.line_start[0])
                inserts.append((t, create_v2(x, y)))
        inserts.sort(key=lambda item: giraffe_evalf(item[0]))
        return [pt for _, pt in inserts] + [self.line_end]

    def sample_interior(self, point_lo: V2, point_hi: V2, tolerance: float) -> List[V2]:
        return []

    def reverse(self) -> 'StraightSegment':
        return StraightSegment(self.line_end, self.line_start)


# ============================================================================
# ArcSegment
# ============================================================================

def _normalize_angle_to_range(angle: float, lo: float, hi: float) -> float:
    """Return `angle` shifted by whole turns into [lo, hi]."""
    while angle < lo - 1e-9:
        angle += 2.0 * math.pi
    while angle > hi + 1e-9:
        angle -= 2.0 * math.pi
    return angle


@dataclass(frozen=True)
class ArcSegment(PathSegment):
    """A circular arc from `start_angle`, sweeping `sweep_angle`: CCW if positive, CW if negative.

    abs(sweep_angle) is in (0, 2*pi]. The sign picks which of the two arcs between the endpoints.
    """
    center: V2
    radius: Numeric
    start_angle: Numeric
    sweep_angle: Numeric

    @property
    def end_angle(self) -> Numeric:
        return self.start_angle + self.sweep_angle

    @property
    def start(self) -> V2:
        return create_v2(self.center[0] + self.radius * cos(self.start_angle),
                          self.center[1] + self.radius * sin(self.start_angle))

    @property
    def end(self) -> V2:
        return create_v2(self.center[0] + self.radius * cos(self.end_angle),
                          self.center[1] + self.radius * sin(self.end_angle))

    def is_planar(self) -> bool:
        return False

    def _monotonic_subranges(self, eps: Optional[Numeric] = None) -> List[Tuple[Numeric, Numeric, int]]:
        """Split the arc at its poles into pieces where y(theta) is monotonic.

        Returns (angle_a, angle_b, cos_sign) per piece in traversal order; cos_sign is the sign of cos(theta).
        """
        clockwise = safe_compare(self.sweep_angle, 0, Comparison.LT, eps=eps)
        angle_lo = self.end_angle if clockwise else self.start_angle
        angle_hi = self.start_angle if clockwise else self.end_angle

        # For each candidate pole base, there's at most one representative
        # (mod 2*pi) inside (angle_lo, angle_hi), since that window is never
        # wider than 2*pi: push the base up past angle_lo, then down past
        # angle_hi (both directions are needed -- angle_lo/angle_hi can be
        # any real numbers, including both negative, e.g. a CW arc whose
        # start/end angles are already below zero) and see if what's left
        # still clears angle_lo.
        poles: List[Numeric] = []
        for pole_base in (pi / 2, scalar(3) * pi / 2):
            pole = pole_base
            while safe_compare(pole, angle_lo, Comparison.LE, eps=eps):
                pole += 2 * pi
            while safe_compare(pole, angle_hi, Comparison.GE, eps=eps):
                pole -= 2 * pi
            if safe_compare(pole, angle_lo, Comparison.GT, eps=eps):
                poles.append(pole)

        poles = sorted(set(poles), key=giraffe_evalf)  # ascending; de-dupes exact repeats
        if clockwise:
            bounds = [self.start_angle] + list(reversed(poles)) + [self.end_angle]
        else:
            bounds = [self.start_angle] + poles + [self.end_angle]

        pieces = []
        for i in range(len(bounds) - 1):
            a, b = bounds[i], bounds[i + 1]
            mid = (a + b) / scalar(2)
            cos_sign = 1 if safe_compare(cos(mid), 0, Comparison.GE, eps=eps) else -1
            pieces.append((a, b, cos_sign))
        return pieces

    def ray_crossings(self, y: Numeric, inclusive: bool = False, eps: Optional[Numeric] = None) -> List[Numeric]:
        results: List[Numeric] = []
        for angle_lo, angle_hi, cos_sign in self._monotonic_subranges(eps=eps):
            y_lo = self.center[1] + self.radius * sin(angle_lo)
            y_hi = self.center[1] + self.radius * sin(angle_hi)
            if inclusive:
                lo, hi = (y_lo, y_hi) if safe_compare(y_lo, y_hi, Comparison.LE, eps=eps) else (y_hi, y_lo)
                hit = safe_compare(lo, y, Comparison.LE, eps=eps) and safe_compare(y, hi, Comparison.LE, eps=eps)
            else:
                hit = (
                    (safe_compare(y_lo, y, Comparison.LE, eps=eps) and safe_compare(y, y_hi, Comparison.LT, eps=eps))
                    or (safe_compare(y_hi, y, Comparison.LE, eps=eps) and safe_compare(y, y_lo, Comparison.LT, eps=eps))
                )
            if not hit:
                continue
            sin_theta = (y - self.center[1]) / self.radius
            # The hit test above accepts y within the comparison tolerance of
            # this subrange's endpoints, so at the extremes sin_theta can land
            # a hair outside [-1, 1] -- far enough outside to blow past sqrt's
            # own small-negative guard once the tolerance is widened for
            # picking. The gate has already established y lies on this
            # subrange, so clamp instead of failing on the noise.
            sin_theta = min(scalar(1), max(scalar(-1), sin_theta))
            cos_theta = cos_sign * sym_sqrt(scalar(1) - sin_theta ** 2)
            results.append(self.center[0] + self.radius * cos_theta)
        return results

    def v_extrema(self) -> List[Numeric]:
        extrema = []
        for angle_lo, angle_hi, _ in self._monotonic_subranges()[:-1]:
            # angle_hi of each piece but the last is an interior pole
            extrema.append(self.center[1] + self.radius * sin(angle_hi))
        return extrema

    def _angle_extent_float(self) -> Tuple[float, float]:
        """Return the arc's (lo, hi) angles as floats, lo <= hi."""
        start_a, end_a = float(self.start_angle), float(self.end_angle)
        return (start_a, end_a) if start_a <= end_a else (end_a, start_a)

    def _angle_for_point(self, point: V2) -> float:
        dx = float(point[0] - self.center[0])
        dy = float(point[1] - self.center[1])
        angle = math.atan2(dy, dx)
        lo, hi = self._angle_extent_float()
        return _normalize_angle_to_range(angle, lo, hi)

    def closest_point(self, point: V2, eps: Optional[Numeric] = None) -> V2:
        angle = self._angle_for_point(point)
        lo, hi = self._angle_extent_float()
        if lo - 1e-9 <= angle <= hi + 1e-9:
            return self._point_at_angle(angle)
        # off the arc's own span -- nearer endpoint wins
        start_pt, end_pt = self.start, self.end
        d_start = (point[0] - start_pt[0]) ** 2 + (point[1] - start_pt[1]) ** 2
        d_end = (point[0] - end_pt[0]) ** 2 + (point[1] - end_pt[1]) ** 2
        return start_pt if safe_compare(d_start, d_end, Comparison.LE, eps=eps) else end_pt

    def outward_local_normal(self, point: V2, eps: Optional[Numeric] = None) -> V2:
        # For CCW (positive sweep) travel, outward is +radial (away from
        # center) -- e.g. the rim of a convex bulge. For CW (negative sweep,
        # a concave bite), it's -radial (toward center, into the void the
        # bite carves out). See the class docstring: this sign is exactly
        # what makes a concave arc possible at all for a fixed start/end.
        radial = point - self.center
        if safe_compare(self.sweep_angle, 0, Comparison.LT, eps=eps):
            radial = -radial
        return safe_normalize_vector(radial)

    def bounds(self) -> Tuple[V2, V2]:
        xs = [self.start[0], self.end[0]]
        ys = [self.start[1], self.end[1]]
        angle_lo = self.start_angle if safe_compare(self.start_angle, self.end_angle, Comparison.LE) else self.end_angle
        angle_hi = self.end_angle if safe_compare(self.start_angle, self.end_angle, Comparison.LE) else self.start_angle
        for cardinal in (scalar(0), pi / 2, pi, scalar(3) * pi / 2):
            angle = cardinal
            while safe_compare(angle, angle_lo, Comparison.LT):
                angle += 2 * pi
            if safe_compare(angle, angle_lo, Comparison.GE) and \
               safe_compare(angle, angle_hi, Comparison.LE):
                xs.append(self.center[0] + self.radius * cos(angle))
                ys.append(self.center[1] + self.radius * sin(angle))
        min_x = xs[0]; max_x = xs[0]; min_y = ys[0]; max_y = ys[0]
        for x in xs[1:]:
            if safe_compare(x, min_x, Comparison.LT): min_x = x
            if safe_compare(x, max_x, Comparison.GT): max_x = x
        for y in ys[1:]:
            if safe_compare(y, min_y, Comparison.LT): min_y = y
            if safe_compare(y, max_y, Comparison.GT): max_y = y
        return create_v2(min_x, min_y), create_v2(max_x, max_y)

    def signed_area_contribution(self) -> Numeric:
        start_pt, end_pt = self.start, self.end
        chord_term = (start_pt[0] * end_pt[1] - end_pt[0] * start_pt[1]) / scalar(2)
        # Standard chord+bulge area identity: adding a CCW arc of sweep angle
        # `t` in place of its own chord adds a signed r^2*(t - sin(t))/2 term
        # -- valid for any t in (0, 2*pi], reflex sweeps included.
        arc_term = (self.radius ** 2) * (self.sweep_angle - sin(self.sweep_angle)) / scalar(2)
        return chord_term + arc_term

    def _angle_grid(self, tolerance: float) -> List[float]:
        """Return sample angles strictly inside the arc, stepped from `start_angle` for chord sagitta `tolerance`.

        Anchored at `start_angle` so tessellate() and sample_interior() land on the same points.
        """
        radius = float(self.radius)
        sweep = float(self.sweep_angle)
        start = float(self.start_angle)
        if radius <= 0 or sweep == 0:
            return []
        max_step = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - float(tolerance) / radius)))
        if max_step <= 1e-9:
            max_step = abs(sweep)
        steps = max(1, math.ceil(abs(sweep) / max_step))
        return [start + sweep * k / steps for k in range(1, steps)]

    def _point_at_angle(self, angle: float) -> V2:
        cx, cy = float(self.center[0]), float(self.center[1])
        radius = float(self.radius)
        return create_v2(Float(cx + radius * math.cos(angle)), Float(cy + radius * math.sin(angle)))

    def tessellate(self, tolerance: float) -> List[V2]:
        points = [self._point_at_angle(a) for a in self._angle_grid(tolerance)]
        points.append(self.end)
        return points

    def tessellate_with_extra_breaks(self, other_breaks: List[Numeric], tolerance: float) -> List[V2]:
        angles = list(self._angle_grid(tolerance))
        for y in other_breaks:
            for x in self.ray_crossings(y, inclusive=True):
                angle = self._angle_for_point(create_v2(x, y))
                lo, hi = self._angle_extent_float()
                if lo + 1e-9 < angle < hi - 1e-9:  # strictly interior -- not one of this segment's own endpoints
                    angles.append(angle)
        clockwise = safe_compare(self.sweep_angle, 0, Comparison.LT)
        angles.sort(reverse=bool(clockwise))
        deduped: List[float] = []
        for a in angles:
            if not deduped or abs(a - deduped[-1]) > 1e-9:
                deduped.append(a)
        points = [self._point_at_angle(a) for a in deduped]
        points.append(self.end)
        return points

    def sample_interior(self, point_lo: V2, point_hi: V2, tolerance: float) -> List[V2]:
        angle_lo = self._angle_for_point(point_lo)
        angle_hi = self._angle_for_point(point_hi)
        reverse = angle_lo > angle_hi
        angle_a, angle_b = (angle_hi, angle_lo) if reverse else (angle_lo, angle_hi)
        grid = self._angle_grid(tolerance)
        # _angle_grid's own order runs start_angle -> end_angle (ascending for
        # a CCW/positive sweep, descending for CW/negative) -- sort ascending
        # first so the reverse-if-needed below reliably lands on point_lo ->
        # point_hi order regardless of which direction the grid itself runs.
        interior = sorted(a for a in grid if angle_a + 1e-9 < a < angle_b - 1e-9)
        if reverse:
            interior.reverse()
        return [self._point_at_angle(a) for a in interior]

    def reverse(self) -> 'ArcSegment':
        # Same circle, same points, traversed the other way: starting where
        # this one ended, sweeping by the same magnitude in the opposite
        # (CCW<->CW) direction.
        return ArcSegment(center=self.center, radius=self.radius,
                           start_angle=self.end_angle, sweep_angle=-self.sweep_angle)


# ============================================================================
# FancyPath
# ============================================================================

@dataclass(frozen=True)
class FancyPath:
    """A closed loop of segments, each ending where the next starts.

    Not validated on construction; call is_valid().
    """
    segments: List[PathSegment]

    def is_valid(self) -> bool:
        """Return whether the loop has a segment, closes, and winds CCW.

        Self-intersection isn't checked; a self-intersecting path is undefined behaviour.
        """
        if not self.segments:
            return False
        n = len(self.segments)
        for i in range(n):
            a = self.segments[i]
            b = self.segments[(i + 1) % n]
            end_pt, start_pt = a.end, b.start
            if not (safe_zero_test(end_pt[0] - start_pt[0]) and safe_zero_test(end_pt[1] - start_pt[1])):
                return False
        return safe_compare(self.signed_area(), 0, Comparison.GT)

    def signed_area(self) -> Numeric:
        total = scalar(0)
        for seg in self.segments:
            total += seg.signed_area_contribution()
        return total

    def reversed(self) -> 'FancyPath':
        """Return this loop traversed the other way (flips CW and CCW)."""
        return FancyPath([seg.reverse() for seg in reversed(self.segments)])

    def bounds(self) -> Tuple[V2, V2]:
        mins, maxs = self.segments[0].bounds()
        min_x, min_y = mins[0], mins[1]
        max_x, max_y = maxs[0], maxs[1]
        for seg in self.segments[1:]:
            lo, hi = seg.bounds()
            if safe_compare(lo[0], min_x, Comparison.LT): min_x = lo[0]
            if safe_compare(lo[1], min_y, Comparison.LT): min_y = lo[1]
            if safe_compare(hi[0], max_x, Comparison.GT): max_x = hi[0]
            if safe_compare(hi[1], max_y, Comparison.GT): max_y = hi[1]
        return create_v2(min_x, min_y), create_v2(max_x, max_y)

    def locate_boundary_segment(self, point: V2, eps: Optional[Numeric] = None) -> Optional[Tuple[int, PathSegment]]:
        """Return the first segment `point` lies on, or None if it isn't on the boundary."""
        for index, seg in enumerate(self.segments):
            closest = seg.closest_point(point, eps=eps)
            if safe_zero_test_sq((closest[0] - point[0]) ** 2 + (closest[1] - point[1]) ** 2, eps):
                return index, seg
        return None

    def is_point_on_boundary_2d(self, point: V2, eps: Optional[Numeric] = None) -> bool:
        return self.locate_boundary_segment(point, eps=eps) is not None

    def contains_point_2d(self, point: V2, eps: Optional[Numeric] = None) -> bool:
        if self.is_point_on_boundary_2d(point, eps=eps):
            return True
        x, y = point[0], point[1]
        count = 0
        for seg in self.segments:
            for cross_x in seg.ray_crossings(y, eps=eps):
                if safe_compare(cross_x, x, Comparison.GT, eps=eps):
                    count += 1
        return count % 2 == 1

    def tessellate(self, tolerance: float) -> Profile:
        """Return the path as a point list, for an outline. Use tessellate_for_mesh for a PathExtrusion's wall."""
        points: List[V2] = []
        for seg in self.segments:
            points.extend(seg.tessellate(tolerance))
        return points

    def tessellate_for_mesh(self, tolerance: float) -> Profile:
        """Return the path as a point list with a vertex at every seam decompose_path_into_convex_pieces makes."""
        breakpoints = _path_breakpoints(self)
        points: List[V2] = []
        for seg in self.segments:
            # Passing every breakpoint (including this segment's own start/end)
            # is fine: tessellate_with_extra_breaks only ever inserts ones that
            # land strictly inside its own y-range, so its own endpoints are a
            # no-op here regardless.
            points.extend(seg.tessellate_with_extra_breaks(breakpoints, tolerance))
        return points


# Alias for backwards compatibility
Path = FancyPath


def _path_breakpoints(path: FancyPath) -> List[Numeric]:
    """Return the sorted y values decompose_path_into_convex_pieces cuts bands at: segment start y's and v_extrema."""
    breakpoints: List[Numeric] = []
    for seg in path.segments:
        breakpoints.append(seg.start[1])
        breakpoints.extend(seg.v_extrema())
    breakpoints.sort(key=giraffe_evalf)
    deduped: List[Numeric] = []
    for v in breakpoints:
        if not deduped or not safe_zero_test(v - deduped[-1]):
            deduped.append(v)
    return deduped


# ============================================================================
# decompose_path_into_convex_pieces
# ============================================================================

def decompose_path_into_convex_pieces(path: FancyPath, tolerance: float) -> List[Profile]:
    """Split a FancyPath into convex polygons (point lists), sweeping horizontal bands over its segments.

    Band corners are exact; curved band edges are sampled at `tolerance`.
    """
    deduped = _path_breakpoints(path)

    # Full crossing set at each breakpoint LEVEL (every segment, not just
    # ones "mid-band active" in some particular band) -- needed because a
    # pole can sit exactly on a band boundary and only affect the band on
    # ONE side of it (the arc is only mid-band active above its own pole,
    # say), yet the piece on the OTHER side still shares that exact boundary
    # line and must place a vertex at the same spot, or the two pieces
    # subdivide their shared edge differently -- a T-junction between two
    # cap pieces, not a wall/cap one this time, but the same failure mode.
    level_crossings = {v: sorted(set(
        x for seg in path.segments for x in seg.ray_crossings(v, inclusive=True)
    ), key=giraffe_evalf) for v in deduped}

    pieces: List[Profile] = []
    for i in range(len(deduped) - 1):
        v_lo, v_hi = deduped[i], deduped[i + 1]
        v_mid = (v_lo + v_hi) / scalar(2)

        crossings = []  # (u_mid, u_lo, u_hi, segment)
        for seg in path.segments:
            # A single segment can contribute more than one crossing to the
            # same band -- e.g. one ArcSegment spanning an entire semicircle
            # crosses a horizontal line through its interior twice (once on
            # each side), even though the band-splitting above already
            # guarantees no *individual* monotonic branch needs further
            # splitting. Each of a segment's monotonic branches spans the
            # full band whenever it's active in it, so ray_crossings returns
            # its hits in the same (angle-ascending) branch order regardless
            # of which of v_lo/v_mid/v_hi it's asked about -- sort each by x
            # and zip by position to pair them correctly.
            mid_hits = sorted(seg.ray_crossings(v_mid), key=giraffe_evalf)
            if not mid_hits:
                continue
            lo_hits = sorted(seg.ray_crossings(v_lo, inclusive=True), key=giraffe_evalf)
            hi_hits = sorted(seg.ray_crossings(v_hi, inclusive=True), key=giraffe_evalf)
            if len(lo_hits) != len(mid_hits) or len(hi_hits) != len(mid_hits):
                raise ValueError(
                    "FancyPath is not simple: a segment's crossing count changed within a "
                    "single decomposition band (band boundaries should prevent this)"
                )
            for k in range(len(mid_hits)):
                crossings.append((mid_hits[k], lo_hits[k], hi_hits[k], seg))
        crossings.sort(key=lambda c: giraffe_evalf(c[0]))

        if len(crossings) % 2 != 0:
            raise ValueError("FancyPath is not simple: odd number of boundary crossings in a v-band")

        for j in range(0, len(crossings) - 1, 2):
            _, u_left_lo, u_left_hi, seg_left = crossings[j]
            _, u_right_lo, u_right_hi, seg_right = crossings[j + 1]
            # NOTE: unlike the straight-only decompose_simple_polygon_into_convex_pieces,
            # there is no "both ends coincide -> zero-area, skip" shortcut here:
            # a piece pinched to a point at BOTH v_lo and v_hi can still have
            # real width strictly between them once a curved edge is involved
            # (e.g. a half-disk -- straight diameter on one side, arc on the
            # other -- is pinched at both its top and bottom vertices, but is
            # not remotely zero-area). A genuinely zero-width piece (left and
            # right edges coincide throughout) just produces zero-area fan
            # triangles below, which is harmless, unlike incorrectly dropping
            # real geometry would be.

            bl = create_v2(u_left_lo, v_lo)
            br = create_v2(u_right_lo, v_lo)
            tr = create_v2(u_right_hi, v_hi)
            tl = create_v2(u_left_hi, v_hi)
            # A band that starts or ends exactly at a pole (e.g. the top/bottom
            # of a circular arc) has its left/right corner pair coincide at a
            # single point there -- emitting both would add a zero-area
            # triangle at that pole, which breaks manifoldness (a self-loop
            # edge, plus an over-shared edge next to it) rather than just
            # being a harmless sliver.
            lo_degenerate = safe_zero_test(u_right_lo - u_left_lo)
            hi_degenerate = safe_zero_test(u_right_hi - u_left_hi)

            # Seam points other segments' poles land at this exact level,
            # strictly inside this piece's bl-br / tr-tl span -- see
            # level_crossings above. Ascending order matches bl->br;
            # reversed matches tr->tl (descending, since tr's x > tl's x).
            extra_lo = [x for x in level_crossings[v_lo]
                        if safe_compare(x, u_left_lo, Comparison.GT) and safe_compare(x, u_right_lo, Comparison.LT)]
            extra_hi = [x for x in level_crossings[v_hi]
                        if safe_compare(x, u_left_hi, Comparison.GT) and safe_compare(x, u_right_hi, Comparison.LT)]

            piece: Profile = [bl] if lo_degenerate else [bl] + [create_v2(x, v_lo) for x in extra_lo] + [br]
            piece.extend(seg_right.sample_interior(br, tr, tolerance))
            piece.append(tr)
            if not hi_degenerate:
                piece.extend(create_v2(x, v_hi) for x in reversed(extra_hi))
                piece.append(tl)
            piece.extend(seg_left.sample_interior(tl, bl, tolerance))
            pieces.append(piece)

    return pieces


# ============================================================================
# PathExtrusion
# ============================================================================

@dataclass(frozen=True)
class FlatSide:
    """Key of the side extruded from a straight segment."""

    index: int


@dataclass(frozen=True)
class CurvedSide:
    """Key of the side extruded from an arc. Has no plane, so is never measurable."""

    index: int


#: Key of a PathExtrusion feature: a cap, or a side marked flat or curved.
PathExtrusionFeatureKey = Union[ExtrusionCap, FlatSide, CurvedSide]


def is_cap(key: PathExtrusionFeatureKey) -> bool:
    """Return whether a key names an end cap rather than a side."""
    return isinstance(key, ExtrusionCap)


def side_index(key: PathExtrusionFeatureKey) -> int:
    """Return the segment index a side key names. Raises for a cap."""
    if isinstance(key, (FlatSide, CurvedSide)):
        return key.index
    raise ValueError(f"{key!r} names a cap, not a side, so it indexes no segment")


@dataclass(frozen=True)
class _PathExtrusionFeature(CSGFeature):
    """Shared base of PathExtrusion's flat and curved features."""
    key: PathExtrusionFeatureKey = ExtrusionCap.TOP

    def _midpoint_2d(self, owner: 'PathExtrusion') -> Optional[V2]:
        """Return the centre of this face's footprint in the path's 2D plane."""
        if self.key in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            low, high = owner.path.bounds()
            return (low + high) / scalar(2)
        segment = owner.path.segments[side_index(self.key)]
        return (segment.start + segment.end) / scalar(2)

    def locate_simple_unbounded(self, owner: 'CutCSG') -> Optional[Plane]:
        if not isinstance(owner, PathExtrusion):
            return None
        orientation = owner.transform.orientation.matrix
        length_dir = safe_transform_vector(orientation, Matrix([scalar(0), scalar(0), scalar(1)]))
        if self.key in (ExtrusionCap.TOP, ExtrusionCap.BOTTOM):
            distance = owner.end_distance if self.key == ExtrusionCap.TOP else owner.start_distance
            if distance is None:
                return None
            sign = scalar(1) if self.key == ExtrusionCap.TOP else scalar(-1)
            return Plane(normal=length_dir * sign, point=owner.transform.position + length_dir * distance)
        # A side is planar only if its path segment is straight. An arc's wall
        # is curved, so there is no plane to give -- the same graceful decline
        # test_point_unbounded already makes for curved segments.
        segment = owner.path.segments[side_index(self.key)]
        if not segment.is_planar():
            return None
        midpoint_2d = self._midpoint_2d(owner)
        if midpoint_2d is None:
            return None
        normal_2d = segment.outward_local_normal(midpoint_2d)
        normal = safe_transform_vector(orientation, Matrix([normal_2d[0], normal_2d[1], scalar(0)]))
        mid_length = _finite_midpoint(owner.start_distance, owner.end_distance)
        local = Matrix([midpoint_2d[0], midpoint_2d[1], mid_length])
        return Plane(normal=normal, point=owner.transform.position + safe_transform_vector(orientation, local))


    def test_point_unbounded(self, owner: 'CutCSG', point: V3, test_tolerance: Optional[Numeric] = None) -> bool:
        if not isinstance(owner, PathExtrusion):
            return False
        x, y, z = owner._local_coords(point)
        if self.key == ExtrusionCap.TOP:
            return owner.end_distance is not None and safe_equality_test(z, owner.end_distance, eps=test_tolerance)
        if self.key == ExtrusionCap.BOTTOM:
            return owner.start_distance is not None and safe_equality_test(z, owner.start_distance, eps=test_tolerance)
        index = side_index(self.key)
        if not owner.path.segments[index].is_planar():
            return False
        located = owner.path.locate_boundary_segment(create_v2(x, y), eps=test_tolerance)
        return located is not None and located[0] == index


@dataclass(frozen=True)
class SimplePathExtrusionFeature(_PathExtrusionFeature, FaceFeature):
    """A flat side (FlatSide key) or an end cap of a PathExtrusion."""

    def __post_init__(self):
        if isinstance(self.key, CurvedSide):
            raise ValueError(f"{self.name!r}: {self.key!r} is curved; use SimplePathExtrusionCurvedFeature")


@dataclass(frozen=True)
class SimplePathExtrusionCurvedFeature(_PathExtrusionFeature, CurvedFaceFeature):
    """A curved side of a PathExtrusion. Has no plane."""

    def __post_init__(self):
        if not isinstance(self.key, CurvedSide):
            raise ValueError(f"{self.name!r}: {self.key!r} is not a curved side; use SimplePathExtrusionFeature")

    def locate_simple_unbounded(self, owner: 'CutCSG') -> None:
        return None


@dataclass(frozen=True)
class PathExtrusion(HasFeatures, CutCSG):
    """Extrusion of a closed FancyPath (may be concave) along local Z.

    The path is in the local XY plane at `transform`; it extends -z by `start_distance` and +z by
    `end_distance`, as ConvexPolygonExtrusion.
    """
    path: FancyPath
    transform: Transform = field(default_factory=Transform.identity)
    start_distance: Optional[Numeric] = None
    end_distance: Optional[Numeric] = None

    # Features this primitive names on its own boundary. Private: read it
    def __repr__(self) -> str:
        return (f"PathExtrusion({len(self.path.segments)} segments, "
                f"transform={self.transform}, start={self.start_distance}, end={self.end_distance})")

    def side(self, index: int) -> PathExtrusionFeatureKey:
        """Return the key for side `index`: FlatSide or CurvedSide as the segment is."""
        segment = self.path.segments[index]
        return FlatSide(index) if segment.is_planar() else CurvedSide(index)

    def feature(self, name: str, key: PathExtrusionFeatureKey,
                **rest) -> '_PathExtrusionFeature':
        """Return a feature of this extrusion; pass `extrusion.side(n)` for a side."""
        if isinstance(key, CurvedSide):
            return SimplePathExtrusionCurvedFeature(name, key=key, **rest)
        return SimplePathExtrusionFeature(name, key=key, **rest)

    def _local_coords(self, point: V3) -> Tuple[Numeric, Numeric, Numeric]:
        local_point = point - self.transform.position
        local_coords = safe_transform_vector(self.transform.orientation.invert().matrix, local_point)
        return local_coords[0], local_coords[1], local_coords[2]

    def carriers(self) -> Dict[FeatureKey, Carrier]:
        return {}

    def contains_point(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        x, y, z = self._local_coords(point)
        if self.start_distance is not None and safe_compare(z, self.start_distance, Comparison.LT, eps=eps):
            return False
        if self.end_distance is not None and safe_compare(z, self.end_distance, Comparison.GT, eps=eps):
            return False
        return self.path.contains_point_2d(create_v2(x, y), eps=eps)

    def is_point_on_boundary(self, point: V3, eps: Optional[Numeric] = None) -> bool:
        if not self.contains_point(point, eps=eps):
            return False
        x, y, z = self._local_coords(point)
        if self.start_distance is not None and safe_zero_test(z - self.start_distance, eps=eps):
            return True
        if self.end_distance is not None and safe_zero_test(z - self.end_distance, eps=eps):
            return True
        return self.path.is_point_on_boundary_2d(create_v2(x, y), eps=eps)

    def get_outward_normal(self, point: V3, eps: Optional[Numeric] = None) -> Optional[Direction3D]:
        x, y, z = self._local_coords(point)
        if self.end_distance is not None and safe_equality_test(z, self.end_distance, eps=eps):
            return safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), scalar(1)]))
        if self.start_distance is not None and safe_equality_test(z, self.start_distance, eps=eps):
            return safe_transform_vector(self.transform.orientation.matrix, Matrix([scalar(0), scalar(0), scalar(-1)]))

        located = self.path.locate_boundary_segment(create_v2(x, y), eps=eps)
        if located is None:
            return None
        _, seg = located
        n2 = seg.outward_local_normal(create_v2(x, y), eps=eps)
        local_normal = Matrix([n2[0], n2[1], scalar(0)])
        return safe_transform_vector(self.transform.orientation.matrix, local_normal)

    def get_aabb(self) -> AxisAlignedBoundingBox:
        if self.start_distance is None or self.end_distance is None:
            warnings.warn(
                "get_aabb() called on an infinite PathExtrusion — result is unbounded",
                UserWarning,
                stacklevel=2,
            )
            return AxisAlignedBoundingBox(None, None, None, None, None, None)

        mins, maxs = self.path.bounds()
        corners_global = [
            self.transform.local_to_global(Matrix([x, y, z]))
            for x in (mins[0], maxs[0])
            for y in (mins[1], maxs[1])
            for z in (self.start_distance, self.end_distance)
        ]
        xs = [p[0] for p in corners_global]
        ys = [p[1] for p in corners_global]
        zs = [p[2] for p in corners_global]

        def _min(*vals):
            result = vals[0]
            for v in vals[1:]:
                if safe_compare(v, result, Comparison.LT):
                    result = v
            return result

        def _max(*vals):
            result = vals[0]
            for v in vals[1:]:
                if safe_compare(v, result, Comparison.GT):
                    result = v
            return result

        return AxisAlignedBoundingBox(_min(*xs), _min(*ys), _min(*zs), _max(*xs), _max(*ys), _max(*zs))


    def bounding_half_spaces(self) -> 'SolidBounds':
        """Return the hull of the path's segment start points.

        KNOWN BUG: an arc bulging outward lies outside this hull, so the bound is too small.
        """
        from .edges_on_csg import _bounds_or_unknown, _extruded_hull_half_spaces
        points = [seg.start for seg in self.path.segments]
        return _bounds_or_unknown(_extruded_hull_half_spaces(
            [(float(point[0, 0]), float(point[1, 0])) for point in points],
            self.transform, self.start_distance, self.end_distance))

    def plane_sides(self, frame, seed) -> 'Sides':
        """Return the union of its convex pieces' sides."""
        from .cross_sections import _union
        front: list = []
        back: list = []
        for piece in decompose_path_into_convex_pieces(self.path, tolerance=1e-4):
            convex = ConvexPolygonExtrusion(points=piece, transform=self.transform,
                                            start_distance=self.start_distance, end_distance=self.end_distance)
            piece_front, piece_back = convex.plane_sides(frame, seed)
            front, back = _union(front, piece_front), _union(back, piece_back)
        return front, back
