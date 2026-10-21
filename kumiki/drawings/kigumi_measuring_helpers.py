"""Measuring helpers for the kigumi runner: for two features, the plane a measurement is taken on,
its possible kinds, where it attaches and its value. Used for pick previews and saved measurements.
"""

from dataclasses import dataclass, replace
from typing import Optional, Sequence, Tuple, Union

import numpy as np

from ..csg.feature_extent import FeatureExtents, extents_of
from ..csg.feature_paths import FeatureHandle
from ..csg.cutcsg import CutCSG
from ..geometry import Line, Plane, Point, unit_vector
from ..rule import V3, as_ndarray, create_v3
from .measure import (DEGENERATE_SEPARATION, AngleRays, LineSpan, MeasureSpan, MeasurementDirection,
                        MeasurementKind, MeasurementOperation, MeasurementPlane, MeasurementSpace, ViewAxes,
                        angle_between, angle_rays, distance_anchors, measures_nothing, pair_separation,
                        project_geometry_for_measuring, projected_kinds, slide_axis, three_d_kinds)

Located = Union[Point, Line, Plane]


def world_geometry(handle: FeatureHandle) -> Optional[Located]:
    """Return a feature's unbounded geometry in world space (a plain Plane, Line or Point)."""
    located = handle.feature.locate_simple_unbounded(handle.owner)
    transform = handle.timber.transform
    if isinstance(located, Point):
        return Point(position=transform.local_to_global(located.position))
    if isinstance(located, Line):
        return Line(point=transform.local_to_global(located.point),
                    direction=transform.local_to_global_direction(located.direction))
    if isinstance(located, Plane):
        return Plane(point=transform.local_to_global(located.point),
                     normal=transform.local_to_global_direction(located.normal))
    return None


def feature_anchor(handle: FeatureHandle, root: Optional[CutCSG] = None) -> Optional[V3]:
    """Return where a dimension attaches to a feature, in world space: its extent's anchor on `root`, else its declared extent's."""
    timber = handle.timber
    extents = extents_of(root, timber) if root is not None else FeatureExtents(None, timber)
    extent = extents.of(handle.feature, handle.owner)
    anchor = None if extent is None else extent.anchor()
    if anchor is not None:
        return timber.transform.local_to_global(create_v3(*anchor))
    declared = handle.feature.get_extent(handle.owner)
    return None if declared is None else timber.transform.local_to_global(declared.anchor)


def kinds_for_pair(one: Optional[Located], other: Optional[Located], look, space: MeasurementSpace,
                   ) -> Tuple[MeasurementKind, ...]:
    """Return the kinds a pair admits in the view's space (in 3D a face is a plane)."""
    if space is MeasurementSpace.THREE_D:
        return three_d_kinds(one, other)
    return projected_kinds(one, other, look)


# --- the plane a measurement is taken on ------------------------------------------------------

def _unit(vector) -> np.ndarray:
    vector = as_ndarray(vector)
    length = float(np.linalg.norm(vector))
    return vector / length if length > 0 else np.array([0.0, 0.0, 1.0])


def _plane_constraints(one: Optional[Located], other: Optional[Located]) -> list:
    """Return directions the measurement plane's normal must be square to, in priority order:
    a measured face's normal, a measured edge's direction, and (only for two points) the line between them.
    """
    constraints = []
    for geometry in (one, other):
        if isinstance(geometry, Plane):
            constraints.append(as_ndarray(geometry.normal))
        elif isinstance(geometry, Line):
            constraints.append(as_ndarray(geometry.direction))
    if isinstance(one, Point) and isinstance(other, Point):
        constraints.append(as_ndarray(other.position) - as_ndarray(one.position))
    return [constraint for constraint in constraints if np.any(constraint)]


def _plane_normal(constraints: list, look) -> Optional[np.ndarray]:
    """Return a normal square to every constraint and otherwise closest to `look`, or None if
    the constraints leave no direction (use the camera's plane).
    """
    gaze = _unit(look)
    distinct: list = []
    for constraint in constraints:
        unit = _unit(constraint)
        if not any(abs(abs(float(unit @ seen)) - 1.0) < 1e-9 for seen in distinct):
            distinct.append(unit)
    if not distinct:
        return gaze  # nothing to be square to: face the camera
    if len(distinct) >= 2:
        normal = np.cross(distinct[0], distinct[1])
        if not np.any(np.abs(normal) > 1e-12):
            return None
        normal = _unit(normal)
        # A plane has no front, so whichever way round faces the camera.
        return normal if float(normal @ gaze) >= 0 else -normal
    # One constraint: the member of the family of planes containing it nearest to facing the camera.
    only = distinct[0]
    flattened = gaze - only * float(gaze @ only)
    if not np.any(np.abs(flattened) > 1e-9):
        # Looking straight down it: every member is equally edge-on, and any will do.
        fallback = np.array([1.0, 0.0, 0.0]) if abs(only[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        return _unit(np.cross(only, fallback))
    return _unit(flattened)


def measurement_plane(one: Optional[Located], other: Optional[Located], at_one, at_other, look,
                      in_view_plane: bool = False) -> MeasurementPlane:
    """Return the plane a measurement between two features is taken on.

    `look` settles what the features leave free. Through a measured point if there is one, else
    midway between the anchors. With `in_view_plane`, the view's own plane.
    """
    normal = None if in_view_plane else _plane_normal(_plane_constraints(one, other), look)
    if normal is None:
        normal = _unit(look)
    at = next((as_ndarray(geometry.position) for geometry in (one, other) if isinstance(geometry, Point)), None)
    if at is None and at_one is not None and at_other is not None:
        at = (as_ndarray(at_one) + as_ndarray(at_other)) / 2
    at = at if at is not None else np.zeros(3)
    return MeasurementPlane(at=create_v3(*(float(part) for part in at)),
                            normal=create_v3(*(float(part) for part in normal)))


# --- what a measurement comes to --------------------------------------------------------------

@dataclass(frozen=True)
class EndForm:
    """What one end acts as: "plane", "line", "point", or "area" / "none". Planes carry a unit normal, lines a unit direction."""
    form: str
    normal: Optional[V3] = None
    direction: Optional[V3] = None


@dataclass(frozen=True)
class Settled:
    """A measurement's value, or `reason` (in the viewer's words) why there is nothing to draw."""
    kind: Optional[MeasurementKind]
    available: Tuple[str, ...]
    space: Optional[str]
    #: "length" or "angle", with `value`; both None when there is no number.
    unit: Optional[str] = None
    value: Optional[float] = None
    reason: Optional[str] = None
    a: Optional[EndForm] = None
    b: Optional[EndForm] = None


def end_form(geometry: Optional[Located], in_three_d: bool, plane) -> EndForm:
    """Return what one end acts as on the measurement's plane."""
    if not in_three_d:
        seen = project_geometry_for_measuring(geometry, plane)
        if seen is None:
            return EndForm("area" if isinstance(geometry, Plane) else "none")
        geometry = seen
    if isinstance(geometry, Plane):
        return EndForm("plane", normal=unit_vector(geometry.normal))
    if isinstance(geometry, Line):
        return EndForm("line", direction=unit_vector(geometry.direction))
    if isinstance(geometry, Point):
        return EndForm("point")
    return EndForm("none")


def settle(one: Optional[Located], other: Optional[Located], rays: Optional[AngleRays],
           declared: Optional[MeasurementKind], kind: Optional[MeasurementKind],
           admitted: Sequence[MeasurementKind], in_three_d: bool, plane, view: Optional[ViewAxes]) -> Settled:
    """Return a measurement's value judged on its own plane (not the camera's)."""
    names = tuple(one_kind.name for one_kind in admitted)
    settled = Settled(kind=kind, available=names, space="3d" if in_three_d else "projected",
                      a=end_form(one, in_three_d, plane), b=end_form(other, in_three_d, plane))
    if not admitted:
        return replace(settled, reason="not-measurable")
    if declared is not None and declared.name not in names:
        return replace(settled, reason="kind-unavailable")
    if kind is None:
        return replace(settled, reason="not-measurable")
    if kind.operation is MeasurementOperation.ANGLE:
        # Off the rays, which are the two ways the corner opens: normals alone give the same
        # absolute dot for 45 degrees and 135.
        value = angle_between(rays)
        return replace(settled, unit="angle", value=0.0 if value is None else value)
    length = pair_separation(one, other, kind, replace(ViewAxes.from_wire(view), look=create_v3(*plane)))
    if length is None:
        return replace(settled, reason="not-measurable")
    return replace(settled, unit="length", value=length,
                   reason="degenerate" if length < DEGENERATE_SEPARATION else None)


def unplaceable(has_plane: bool) -> Settled:
    """Return a Settled for a measurement whose ends exist but can't be worked out (no plane, or an end with no extent)."""
    return Settled(kind=None, available=(), space=None, reason="no-span" if has_plane else "no-plane")


@dataclass(frozen=True)
class PairPlacement:
    """Where a measurement between two features is drawn, and its value: anchors for a distance, a corner
    for an angle, neither if the pair admits nothing.

    `extents` are each end's line segment (or None), so the viewer can extend a line to an anchor past
    it. `slide` is the direction a distance between two lines slides in, else None.
    """
    kind: Optional[MeasurementKind]
    admitted: Tuple[MeasurementKind, ...]
    anchors: Optional[Tuple[V3, V3]]
    rays: Optional[AngleRays]
    settled: Settled
    extents: Tuple[Optional[Tuple[V3, V3]], Optional[Tuple[V3, V3]]] = (None, None)
    slide: Optional[V3] = None


def _extent(span: MeasureSpan) -> Optional[Tuple[V3, V3]]:
    if isinstance(span, LineSpan) and span.interval is not None:
        start, end = span.ends_global()
        return (start, end)
    return None


def place_pair(one: Optional[Located], other: Optional[Located], one_span: MeasureSpan, other_span: MeasureSpan,
               declared: Optional[MeasurementKind], plane, view: Optional[ViewAxes], in_three_d: bool,
               along: Optional[float] = None, flip: bool = False) -> PairPlacement:
    """Return where a measurement between two features attaches and its value, using the declared kind or the best the pair admits."""
    admitted = (three_d_kinds(one, other) if in_three_d else projected_kinds(one, other, plane))
    kind = declared or (admitted[0] if admitted else None)
    anchors, rays, slide, extents = None, None, None, (None, None)
    if kind is not None and kind.operation is MeasurementOperation.DISTANCE:
        anchors = distance_anchors(one_span, other_span, kind, view, along)
        extents = (_extent(one_span), _extent(other_span))
        if (kind.direction is MeasurementDirection.PERPENDICULAR
                and isinstance(one_span, LineSpan) and isinstance(other_span, LineSpan)):
            slide = slide_axis(one_span)
    elif kind is not None and kind.operation is MeasurementOperation.ANGLE:
        rays = angle_rays(one_span, other_span, flip)
    return PairPlacement(kind, tuple(admitted), anchors, rays,
                         settle(one, other, rays, declared, kind, admitted, in_three_d, plane, view),
                         extents=extents, slide=slide)


@dataclass(frozen=True)
class Verdict:
    """Whether a measurement to a pick could be made: its kinds best first and its plane, or `reason` why not."""
    kinds: Tuple[MeasurementKind, ...]
    plane: Optional[MeasurementPlane]
    reason: Optional[str]


def pick_verdict(held: Optional[Located], picked: Optional[Located], plane: Optional[MeasurementPlane],
                 look, space: MeasurementSpace, view: ViewAxes) -> Verdict:
    """Return whether a measurement from the held feature to `picked` could be made, and as what.

    `picked` is None for an unmeasurable pick (a cylinder's barrel). Kinds that would measure zero
    are excluded per kind.
    """
    if picked is None:
        return Verdict((), None, "not-measurable")
    admitted = kinds_for_pair(held, picked, look, space)
    if not admitted:
        return Verdict((), plane, "no-kind")
    kinds = tuple(kind for kind in admitted if not measures_nothing(held, picked, kind, view))
    if not kinds:
        return Verdict((), plane, "degenerate")
    return Verdict(kinds, plane, None)
