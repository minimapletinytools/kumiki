"""Scratch: exactly which faces of which labelled primitive carry the finished surface.

Samples a grid ON each bounded face of each labelled primitive -- built from the face's
own corners, not from a plane test -- and asks the finished solid whether that point is
on its boundary. What comes back is the set of faces a FeatureOverride on that primitive
could ever be picked on.

Run:  .venv/bin/python garbage/exposed_faces.py <pattern-substring> <label-substring>
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from kumiki.csg.cutcsg import (  # noqa: E402
    csg_children, HasFeatures, RectangularPrism, ConvexPolygonExtrusion,
    SimpleRectangularPrismFeature, SimpleConvexPolygonExtrusionFeature,
    ExtrusionCap,
)
from kumiki.rule import create_v2, create_v3, scalar  # noqa: E402
from kumiki.patternbook import Pattern  # noqa: E402

PATTERNS_DIR = REPO / "patterns"
ORIGIN = create_v3(scalar(0), scalar(0), scalar(0))
STEPS = 5
INSET = 0.02


def walk(node, depth=0, seen=None):
    seen = set() if seen is None else seen
    if node is None or id(node) in seen:
        return
    seen.add(id(node))
    yield node, depth
    for child in csg_children(node):
        yield from walk(child, depth + 1, seen)


def lerp(a, b, t):
    return a + (b - a) * t


def face_samples(node, feature):
    """A grid of local-frame points on one face of a prism or extrusion."""
    if isinstance(node, RectangularPrism) and isinstance(feature, SimpleRectangularPrismFeature):
        corners = feature.corners(node)
        if corners is None:
            return []
        first, second = corners[0], corners[1]  # adjacent corners span one direction
        return [lerp(lerp(corners[0], corners[1], t), lerp(corners[3], corners[2], t), s)
                for t in _steps() for s in _steps()]
    if isinstance(node, ConvexPolygonExtrusion) and isinstance(
            feature, SimpleConvexPolygonExtrusionFeature):
        points = node.points
        if feature.key in (ExtrusionCap.BOTTOM, ExtrusionCap.TOP):
            z = node.start_distance if feature.key is ExtrusionCap.BOTTOM else node.end_distance
            if z is None:
                return []
            centre = create_v2(
                sum(float(p[0]) for p in points) / len(points),
                sum(float(p[1]) for p in points) / len(points),
            )
            samples = []
            for index, point in enumerate(points):
                nxt = points[(index + 1) % len(points)]
                for t in _steps():
                    inner = lerp(point, nxt, t)
                    for s in _steps():
                        samples.append(lerp(inner, centre, s * 0.9))
            return [_lift(node, x, y, z) for x, y in samples]
        index = feature.key
        start, end = node.start_distance, node.end_distance
        if start is None or end is None:
            return []
        first, second = points[index], points[(index + 1) % len(points)]
        samples = []
        for along in _steps():
            edge_point = lerp(first, second, along)
            for across in _steps():
                samples.append(_lift(node, edge_point[0], edge_point[1],
                                     lerp(scalar(start), scalar(end), across)))
        return samples
    return []


def _steps():
    return [scalar(INSET) + scalar(1 - 2 * INSET) * scalar(i, STEPS - 1) for i in range(STEPS)]


def _lift(node, x, y, z):
    """A local (x, y, z) point of an extrusion, in its parent's frame."""
    matrix = node.transform.orientation.matrix
    position = node.transform.position
    return create_v3(
        position[0] + matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2] * z,
        position[1] + matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2] * z,
        position[2] + matrix[2, 0] * x + matrix[2, 1] * y + matrix[2, 2] * z,
    )


def main() -> int:
    wanted, label_filter = sys.argv[1], sys.argv[2]
    for index, path in enumerate(sorted(PATTERNS_DIR.rglob("*.py"))):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        name = f"exposed_{index}_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        for pattern in getattr(module, "patterns", None) or []:
            if not isinstance(pattern, Pattern) or pattern.pattern_type != "frame":
                continue
            if wanted not in pattern.path:
                continue
            frame = pattern.raise_at(ORIGIN)
            print(f"\n=== {pattern.path}")
            for cut in frame.cut_timbers:
                rendered = cut.render_timber_with_cuts_csg_local()
                nodes = [(node, depth) for node, depth in walk(rendered)
                         if isinstance(node, HasFeatures)
                         and label_filter in str(getattr(node, "label", ""))]
                if not nodes:
                    continue
                print(f"  -- {cut.timber.ticket.path}")
                for node, depth in nodes:
                    kind = "subtracted" if depth >= 4 else "positive"
                    print(f"     id={id(node)} depth={depth} ({kind})"
                          f" start={getattr(node, 'start_distance', None)}"
                          f" end={getattr(node, 'end_distance', None)}"
                          f" size={getattr(node, 'size', None)}")
                    for key, feature in sorted(node.default_features().items(), key=lambda kv: str(kv[0])):
                        if feature.feature_type().name != "FACE":
                            continue
                        samples = face_samples(node, feature)
                        on_surface = sum(1 for point in samples
                                         if rendered.is_point_on_boundary(point))
                        total = len(samples)
                        verdict = "EXPOSED" if on_surface else "buried"
                        if total and 0 < on_surface < total:
                            verdict = f"partly ({on_surface}/{total})"
                        print(f"        {feature.name:10} {str(key):24} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
