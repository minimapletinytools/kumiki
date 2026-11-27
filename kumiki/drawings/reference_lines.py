"""Drawing reference lines cropped to the finished timber."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, TypedDict

from ..csg.cutcsg import CutCSG
from ..timber import PerfectTimberWithin
from ..timber_features import TimberFeature, TimberLongFace


REFERENCE_FACE_TINT = '#cfdfec'


def reference_face_colors(timber: PerfectTimberWithin) -> dict[TimberLongFace, str]:
    """Return the tint of each long face adjoining a ticket reference arris: one light blue for all."""
    colors = {}
    for feature in timber.ticket.reference_features:
        adjacent = feature.long_faces_it_rests_on()
        if len(adjacent) == 2:
            for face in adjacent:
                colors[face] = REFERENCE_FACE_TINT
    return colors


class ReferenceLineWire(TypedDict):
    name: str
    primary: bool
    edgePositions: List[float]


def timber_reference_lines(timber: 'PerfectTimberWithin', root_csg: Optional['CutCSG'] = None,
                           features: Optional[Sequence[TimberFeature]] = None) -> List[ReferenceLineWire]:
    """Return a timber's reference features as world-space segments to highlight, primary first.

    Lines run the perfect timber's length; faces and centerplanes are outlines. With `root_csg`, each
    is cropped to the cut timber.
    """
    from kumiki.measuring import (locate_center_plane, locate_edge, locate_face,
                                  locate_long_face_centerline)

    references = timber.ticket.reference_features if features is None else features
    if not references:
        return []
    vector = lambda v: [float(v[i]) for i in range(3)]  # noqa: E731
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))  # noqa: E731
    plus = lambda a, b, k=1.0: [x + k * y for x, y in zip(a, b)]  # noqa: E731
    origin = vector(timber.get_bottom_position_global())
    along = vector(timber.get_length_direction_global())
    length = float(timber.length)
    axes = [vector(timber.orientation.matrix[:, column]) for column in (0, 1)]
    sizes = [float(timber.size[0]), float(timber.size[1])]

    def run(point: List[float]) -> tuple[List[float], List[float]]:
        """The line through *point* along the timber, from its bottom end to its top."""
        start = plus(point, along, dot(plus(origin, point, -1.0), along))
        return start, plus(start, along, length)

    found = []
    for index, feature in enumerate(references):
        name = feature.name
        if name.endswith("_FACE") or name.endswith("_CENTER_PLANE"):
            plane = (locate_face(timber, feature.long_face()) if name.endswith("_FACE")
                     else locate_center_plane(timber, feature.center_plane()))
            normal = vector(plane.normal)
            across = [normal[1] * along[2] - normal[2] * along[1],
                      normal[2] * along[0] - normal[0] * along[2],
                      normal[0] * along[1] - normal[1] * along[0]]
            half = 0.5 * sum(abs(dot(across, axis)) * size for axis, size in zip(axes, sizes))
            bottom, top = run(vector(plane.point))
            corners = [plus(bottom, across, -half), plus(bottom, across, half),
                       plus(top, across, half), plus(top, across, -half)]
            segments = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        else:
            line = (locate_long_face_centerline(timber, feature.long_face_centerline())
                    if name.endswith("_FACE_CENTERLINE")
                    else locate_edge(timber, feature.centerline() if name == "CENTERLINE" else feature.edge()))
            segments = [run(vector(line.point))]
        if root_csg is not None:
            # The axis runs through the wood; everything else lies on its surface.
            segments = _cropped_reference_segments(
                timber, root_csg, segments, through_material=name == "CENTERLINE")
        found.append({
            "name": name.lower(),
            "primary": index == 0,
            "edgePositions": [value for segment in segments for end in segment for value in end],
        })
    return found


def _cropped_reference_segments(
    timber: 'PerfectTimberWithin', root_csg: 'CutCSG', segments: List[Any], through_material: bool,
) -> List[Any]:
    """Return `segments` (world space) cropped to the cut timber's surface, or with `through_material` its inside. Exact, then at float noise."""
    from kumiki.csg.edges_on_csg import crop_line_to_boundary_segments_on_csg, crop_line_to_segments_on_csg
    from kumiki.csg.feature_extent import DECLARED_EDGE_FLOAT_NOISE, cropped_intervals
    from kumiki.geometry import Line, unit_vector
    from kumiki.rule import create_v3

    crop = crop_line_to_segments_on_csg if through_material else crop_line_to_boundary_segments_on_csg
    near = timber.get_perfect_timber_within_csg_local().transform.position
    reach = float(timber.length) * 4
    kept = []
    for start, end in segments:
        a = timber.transform.global_to_local(create_v3(*start))
        b = timber.transform.global_to_local(create_v3(*end))
        span = float(((b - a).T * (b - a))[0, 0]) ** 0.5
        if span <= 0:
            continue
        line = Line(direction=unit_vector(b - a), point=a)
        for low, high in cropped_intervals(line, crop, root_csg, reach, near, DECLARED_EDGE_FLOAT_NOISE) or []:
            low, high = max(low, 0.0), min(high, span)
            if high - low <= 1e-9:
                continue
            at = lambda distance: [float(v) for v in timber.transform.local_to_global(  # noqa: E731
                a + line.direction * distance)]
            kept.append((at(low), at(high)))
    return kept
