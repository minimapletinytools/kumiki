"""Scratch: what the cute frame's generated dimensions do on the sheet, and what a lane packer does with them.

Not a library module and not a test -- a probe for the dimension-layout proposal in
`.claude/plans/dimension-layout.md`. It reads the drawing the runner actually sends the
viewer (`collect_drawings`), projects each dimension's resolved anchors into page
millimetres with the viewport's own camera, and reports:

- where the anchors land, and which dimensions land on the same line,
- how many label boxes sit on the work and on each other under today's rules (one
  26px offset, one side, no lanes -- viewer-app.js `_offsetInPixels`),
- what a first-cut packer does instead: for each dimension, try both sides and a few
  lanes, and take the cheapest band by material under it, overlap with what is already
  placed, and distance from the run.

Run:  .venv/bin/python garbage/dimension_layout_probe.py
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load("kigumi_runner", REPO / "kigumi/runner.py")
test = load("probe_test", REPO / "patterns/structures/my_cute_frame_drawing_test.py")

PAGE_W_MM, PAGE_H_MM = 420.0, 297.0          # A3 landscape, the runner's _DEBUG_DRAWING_PAGE
CANVAS_PX = 1400.0                           # a typical page width on screen
MM_PER_PX = PAGE_W_MM / CANVAS_PX
DEFAULT_OFFSET_MM = 26.0 * MM_PER_PX         # MEASUREMENT_OFFSET_PX, in sheet millimetres

BASE_MM, PITCH_MM = 9.0, 8.0                 # first lane, and lane to lane
TEXT_MM, CHAR_MM = 3.6, 2.1                  # a label, on the sheet
LANES = 6


def hull(points):
    """Convex hull of page points, monotone chain."""
    pts = sorted({(round(float(x), 6), round(float(y), 6)) for x, y in points})
    if len(pts) <= 2:
        return pts

    def half(sequence):
        out = []
        for p in sequence:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out

    return half(pts)[:-1] + half(pts[::-1])[:-1]


def inside(polygon, point):
    x, y = float(point[0]), float(point[1])
    hit = False
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        if (y1 > y) != (y2 > y):
            if x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
                hit = not hit
    return hit


def corner_points(cut):
    """The eight corners of a cut timber, in world space."""
    timber = cut.timber
    origin = np.array([float(timber.get_bottom_position_global()[i, 0]) for i in range(3)])
    along = np.array([float(timber.get_length_direction_global()[i, 0]) for i in range(3)])
    across = np.array([float(timber.get_width_direction_global()[i, 0]) for i in range(3)])
    up = np.array([float(timber.get_height_direction_global()[i, 0]) for i in range(3)])
    half_w, half_h = float(timber.size[0]) / 2, float(timber.size[1]) / 2
    return [origin + along * d + across * a + up * b
            for d in (0.0, float(timber.length)) for a in (-half_w, half_w) for b in (-half_h, half_h)]


def label_box(mid, along, across, text):
    half_along = max(4.0, len(text) * CHAR_MM) / 2
    return (mid, along, across, half_along, TEXT_MM)


def box_corners(box):
    mid, along, across, half_along, half_across = box
    return [mid + along * a + across * b
            for a in (-half_along, half_along) for b in (-half_across, half_across)]


def boxes_overlap(one, other):
    def span(box, axis):
        values = [float(c @ axis) for c in box_corners(box)]
        return min(values), max(values)

    for axis in (one[1], one[2], other[1], other[2]):
        (low_a, high_a), (low_b, high_b) = span(one, axis), span(other, axis)
        if high_a <= low_b or high_b <= low_a:
            return False
    return True


def viewports_with_measurements(drawing):
    for viewport in drawing["viewports"]:
        if viewport.get("camera") and viewport.get("measurements"):
            yield viewport


def main():
    frame = test.build_frame_with_drawing()
    drawing = runner.collect_drawings(frame, None, None)[0]

    for viewport in viewports_with_measurements(drawing):
        camera = viewport["camera"]
        right = np.array(camera["right"], dtype=float)
        up = np.array(camera["up"], dtype=float)
        target = np.array(camera["target"], dtype=float)
        extent = float(camera["extent"])
        rect = viewport["rect"]
        aspect = (rect[2] * PAGE_W_MM) / (rect[3] * PAGE_H_MM)

        def on_sheet(point):
            p = np.array(point, dtype=float) - target
            x = float(p @ right) / (extent * aspect) * 0.5 + 0.5
            y = 0.5 - float(p @ up) / extent * 0.5
            return np.array([(rect[0] + x * rect[2]) * PAGE_W_MM,
                             (rect[1] + y * rect[3]) * PAGE_H_MM])

        work = [hull([on_sheet(corner) for corner in corner_points(cut)]) for cut in frame.cut_timbers]

        dims = []
        for measure in viewport["measurements"]:
            a, b = measure["a"].get("at"), measure["b"].get("at")
            if a is None or b is None:
                continue
            value = ((measure.get("settled") or {}).get("value") or {}).get("value") or 0.0
            start, end = on_sheet(a), on_sheet(b)
            run = end - start
            span = float(np.linalg.norm(run))
            if span < 1e-6:
                continue
            along = run / span
            dims.append({"a": start, "b": end, "along": along, "span": span,
                         "across": np.array([-along[1], along[0]]), "text": f"{value * 1000:.0f}"})

        def on_material(box):
            samples = box_corners(box) + [box[0], box[0] + box[1] * box[3] / 2,
                                          box[0] - box[1] * box[3] / 2]
            return sum(1 for point in samples if any(inside(poly, point) for poly in work))

        current = [label_box((dim["a"] + dim["b"]) / 2 + dim["across"] * DEFAULT_OFFSET_MM,
                             dim["along"], dim["across"], dim["text"]) for dim in dims]
        before_overlaps = sum(1 for i in range(len(current)) for j in range(i + 1, len(current))
                              if boxes_overlap(current[i], current[j]))
        before_material = sum(1 for box in current if on_material(box))

        placed, lanes = [], []
        for dim in sorted(dims, key=lambda d: -d["span"]):
            best = None
            for side in (1, -1):
                for lane in range(LANES):
                    offset = side * (BASE_MM + lane * PITCH_MM)
                    box = label_box((dim["a"] + dim["b"]) / 2 + dim["across"] * offset,
                                    dim["along"], dim["across"], dim["text"])
                    cost = (100 * on_material(box)
                            + 1000 * sum(1 for other in placed if boxes_overlap(box, other))
                            + abs(offset))
                    if best is None or cost < best[0]:
                        best = (cost, offset, box)
            assert best is not None, "SIDES and LANES both offer at least one placement"
            _, offset, box = best
            placed.append(box)
            lanes.append(offset)

        after_overlaps = sum(1 for i in range(len(placed)) for j in range(i + 1, len(placed))
                             if boxes_overlap(placed[i], placed[j]))
        after_material = sum(1 for box in placed if on_material(box))

        world_per_mm = extent * 1000 / (rect[3] * PAGE_H_MM / 2)
        print(f"\n=== viewport {viewport['id']} {viewport.get('name')!r}: {len(dims)} dimensions"
              f"  (1mm on the sheet = {world_per_mm:.2f}mm in the world)")
        print(f"    today:  {before_overlaps} label overlaps, {before_material} labels on the work")
        print(f"    packed: {after_overlaps} label overlaps, {after_material} labels on the work")
        for dim, offset in zip(sorted(dims, key=lambda d: -d["span"]), lanes):
            print(f"      {dim['text']:>5}mm  run {dim['span']:5.1f}mm sheet"
                  f"  ->  lane {offset:+5.0f}mm"
                  f"  (world offset {offset * world_per_mm:+.0f}mm)")


if __name__ == "__main__":
    main()
