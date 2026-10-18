"""Measuring helpers for kigumi: for two features, the plane a measurement is taken on, which
kinds it can be, where it attaches and its value. The runner uses these for both a pick's preview
and a saved measurement.
"""

from dataclasses import dataclass, replace
from typing import Optional, Sequence, Tuple, Union

import numpy as np

from ..csg.feature_extent import FeatureExtents, extents_of
from ..csg.feature_paths import FeatureHandle
from ..csg.cutcsg import CutCSG
from ..geometry import Line, Plane, Point, unit_vector
from ..rule import V3, as_ndarray, create_v3
from .drawing import (DEGENERATE_SEPARATION, AngleRays, LineSpan, MeasureSpan, MeasurementDirection, MeasurementKind,
                      MeasurementOperation, MeasurementPlane, MeasurementSpace, ViewAxes, angle_between, angle_rays,
                      distance_anchors, measures_nothing, pair_separation, project_geometry_for_measuring,
                      projected_kinds, slide_axis, three_d_kinds)

Located = Union[Point, Line, Plane]


def world_geometry(handle: FeatureHandle) -> Optional[Located]:
    """A feature's unbounded geometry, carried out of its timber's frame into the world's.

    A plane keeps its normal and a line its direction, since those decide whether two features are
    parallel once projected. Plane, not whatever subclass it was located as: an UnsignedPlane is a
    fact about the cut that declared it, not about what is measured to.
    """
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
    """Where to attach a dimension to a feature, in world space: its extent's anchor, cropped to
    the cut timber `root` when given. Falls back to the declared extent where the feature cannot be
    placed (a curved primitive): somewhere approximate beats nowhere."""
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
    """What a pair admits, in the space the view is in. In 3D a face is a plane, whatever it looks
    like from here: two faces meeting at a corner admit an angle, two parallel ones a distance."""
    if space is MeasurementSpace.THREE_D:
        return three_d_kinds(one, other)
    return projected_kinds(one, other, look)


# --- the plane a measurement is taken on ------------------------------------------------------

def _unit(vector) -> np.ndarray:
    vector = as_ndarray(vector)
    length = float(np.linalg.norm(vector))
    return vector / length if length > 0 else np.array([0.0, 0.0, 1.0])


def _plane_constraints(one: Optional[Located], other: Optional[Located]) -> list:
    """Directions the plane's normal has to be square to, in the spec's priority order: square to a
    measured face's normal, to a measured edge's run, and -- only when both ends are points, since
    one point says where the plane sits and not which way it faces -- to the line between them."""
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
    """A normal square to every constraint, and otherwise as close to `look` as it can be, so the
    dimension is drawn as nearly face-on as its constraints allow.

    Two constraints can always be met (their cross product, or the one-constraint case when they
    are parallel); None only when there is no direction left to choose, the cue to fall back to the
    camera's own plane.
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
    """Where a measurement between these two features is taken and drawn.

    `look` is the camera's direction when it was made, which settles whatever the features leave
    free. Through a measured point if there is one, since the plane has to contain it; otherwise
    midway between the anchors, among what it measures. `in_view_plane` for a drawing's view: the
    view's own plane, whatever the features -- held to them, an edge running into the sheet tilted
    it, and the measurement refused the view it was made in.
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
    """What one end behaves as: "plane", "line", "point", or "area" / "none" for nothing to measure
    to. A plane carries its unit normal, a line its unit direction."""
    form: str
    normal: Optional[V3] = None
    direction: Optional[V3] = None


@dataclass(frozen=True)
class Settled:
    """What a measurement comes to, decided once and sent with it.

    `reason` is why there is nothing to draw, in the words and order the viewer uses: a row that
    says why and a dimension that is missing cannot disagree.
    """
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
    """What one end behaves as, judged on the measurement's plane."""
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
    """What a measurement comes to, against its own plane -- not the camera, so it does not change
    when the reader turns. Whether the view drawing it IS that plane is the viewer's to say."""
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
    """A measurement both of whose ends were found that still cannot be worked out: no plane to
    judge it on, or an end with no extent."""
    return Settled(kind=None, available=(), space=None, reason="no-span" if has_plane else "no-plane")


@dataclass(frozen=True)
class PairPlacement:
    """Where a measurement between two features sits, and what it comes to: anchors for a distance,
    a corner for an angle, neither when the pair admits nothing.

    `extents` are each end's line as far as the feature goes, (start, end) in world space, or None
    for a point or a plane: where an anchor or the corner is past them, the viewer draws the line
    on to it. `slide` is the direction the anchors slide in (MeasurementPlacement.along), for a
    distance between two lines; None where they cannot slide.
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
               along: Optional[float] = None) -> PairPlacement:
    """Where a measurement between two features attaches, and what it comes to.

    The two ends together: where a dimension attaches is a property of the pair and its plane, and
    two parallel edges each taking their own middle gave a dimension that leaned. Its kind is the
    one declared, or the best the pair admits from here -- placed for the measurement that will be
    drawn, since two crossing faces admit an angle and nothing else.
    """
    admitted = (three_d_kinds(one, other) if in_three_d else projected_kinds(one, other, plane))
    kind = declared or (admitted[0] if admitted else None)
    anchors, rays, slide = None, None, None
    if kind is not None and kind.operation is MeasurementOperation.DISTANCE:
        anchors = distance_anchors(one_span, other_span, kind, view, along)
        if (kind.direction is MeasurementDirection.PERPENDICULAR
                and isinstance(one_span, LineSpan) and isinstance(other_span, LineSpan)):
            slide = slide_axis(one_span)
    elif kind is not None and kind.operation is MeasurementOperation.ANGLE:
        rays = angle_rays(one_span, other_span)
    return PairPlacement(kind, tuple(admitted), anchors, rays,
                         settle(one, other, rays, declared, kind, admitted, in_three_d, plane, view),
                         extents=(_extent(one_span), _extent(other_span)), slide=slide)


@dataclass(frozen=True)
class Verdict:
    """What a measurement to a pick would be: the kinds the pair admits, best first, and the plane
    it would be taken on -- or, with no kinds, why not (`reason`)."""
    kinds: Tuple[MeasurementKind, ...]
    plane: Optional[MeasurementPlane]
    reason: Optional[str]


def pick_verdict(held: Optional[Located], picked: Optional[Located], plane: Optional[MeasurementPlane],
                 look, space: MeasurementSpace, view: ViewAxes) -> Verdict:
    """Whether a measurement from the held feature to the picked one could be made, and as what.

    `picked` is None for a pick that is not measurable (a cylinder's barrel). A kind that would come
    to nothing is not admitted, asked of the features rather than placed ends, and per kind: two
    points one above the other have a vertical distance and no horizontal one.
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
