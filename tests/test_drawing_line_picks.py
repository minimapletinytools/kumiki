"""A drawing's view: a click beside a drawn line takes that line, from either side of it.

The cute frame, each piece drawn alone and looked at from all six sides. For every line the mesh
draws (a crease, seen across), a click on it that takes an edge is matched by clicks a pixel or two
to either side, unless another drawn line is nearer the pointer there.
"""

import contextlib
import importlib.util
import io
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from tests.module_isolation import restore_modules

REPO = Path(__file__).resolve().parent.parent
PIXEL = 0.001  # metres a pixel is worth at the zoom these tolerances stand for
TOLERANCES = {"face": 5e-4, "edge": 6 * PIXEL, "point": 10 * PIXEL}
LOOKS = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]


@pytest.fixture(scope="module")
def frame():
    spec = importlib.util.spec_from_file_location("kigumi_runner_line_picks", REPO / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_line_picks"] = runner
    spec.loader.exec_module(runner)
    saved_modules = dict(sys.modules)
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        slot = runner.load_slot_state(str(REPO / "patterns" / "structures" / "my_cute_frame.py"))
        runner.build_real_geometry(None, slot)
    yield runner, slot
    restore_modules(saved_modules)


def _click(frame, member, origin, look):
    """What a click takes along the ray from `origin`, with only `member` drawn: the runner's reply."""
    runner, slot = frame
    a, b, c = runner._world_triangles(slot.mesh_cache[member])
    e1, e2 = b - a, c - a
    p = np.cross(look, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
    s = origin - a
    u, q = (s * p).sum(1) * inv, np.cross(s, e1)
    w, t = (look * q).sum(1) * inv, (e2 * q).sum(1) * inv
    struck = ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 0)
    payload = {"currentPath": [], "ctrlClick": False, "space": "projected", "tolerances": TOLERANCES,
               "look": [float(x) for x in look], "drawnMembers": [member],
               "ray": {"origin": [float(x) for x in origin], "direction": [float(x) for x in look]}}
    if struck.any():
        payload.update(memberKey=member, point=[float(x) for x in origin + look * t[struck].min()])
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return runner._handle_find_csg_at_point(None, payload, slot)


def _across(points, origin, look):
    """Each point's distance from the ray, across the view."""
    offset = points - origin
    return np.linalg.norm(offset - np.outer(offset @ look, look), axis=-1)


def _on_line(reply, start, run, look):
    """Whether the click took an edge drawn on the same sheet line as the segment (start, run)."""
    geometry = reply.get("geometry") or {}
    if reply.get("featureType") != "EDGE" or geometry.get("kind") != "line":
        return False
    point, direction = np.array(geometry["at"], float), np.array(geometry["direction"], float)
    flat = lambda v: v - look * (v @ look)
    if abs(abs(flat(direction) @ flat(run)) / (np.linalg.norm(flat(direction)) * np.linalg.norm(flat(run))) - 1) > 1e-6:
        return False
    gap = flat(point - start)
    side = flat(run) / np.linalg.norm(flat(run))
    return bool(np.linalg.norm(gap - side * (gap @ side)) < 1e-5)


def _nearest_line(starts, runs, origin, look):
    """How far the nearest drawn segment passes from the ray, across the view."""
    flat_starts = (starts - origin) - np.outer((starts - origin) @ look, look)
    flat_runs = runs - np.outer(runs @ look, look)
    lengths = (flat_runs * flat_runs).sum(1)
    t = np.clip(-(flat_starts * flat_runs).sum(1) / np.where(lengths > 1e-24, lengths, 1), 0, 1)
    return np.linalg.norm(flat_starts + flat_runs * t[:, None], axis=1)


def test_the_mortise_mouth_is_taken_from_either_side(frame):
    # Looking at Left Side's inner face: the mouth's top edge, from the face above it and from
    # inside the mortise below it, where the ray strikes the mortise's back.
    look = np.array([-1.0, 0, 0])
    for dz in (-2 * PIXEL, 2 * PIXEL):
        reply = _click(frame, "Left Side#0", np.array([0.5, 0.2, 0.02 + dz]), look)
        assert reply.get("featureLabel") == "arris.7", dz


@pytest.mark.parametrize("member", ["Left Side#0", "Back Cross#0"])
def test_a_click_beside_a_drawn_line_takes_it(frame, member):
    runner, slot = frame
    starts, runs = runner._world_creases(slot.mesh_cache[member])
    misses = []
    for look in (np.array(one, float) for one in LOOKS):
        tested = set()
        for start, run in zip(starts, runs):
            length = float(np.linalg.norm(run))
            if length < 0.01 or abs(run @ look) / length > 0.01:
                continue  # too short to aim at the middle of, or seen end-on
            middle = start + run / 2
            # The same stretch of sheet, drawn again deeper: one click there tells for both.
            sheet = tuple(np.round(np.concatenate([middle - look * (middle @ look), np.abs(run) / length]), 4))
            if sheet in tested:
                continue
            if not _on_line(_click(frame, member, middle - look * 5, look), start, run, look):
                continue  # hidden, or a corner or a face takes it: not a line a click takes here
            tested.add(sheet)
            across = np.cross(look, run / length)
            for pixels in (-2, 2):
                origin = middle + across * pixels * PIXEL - look * 5
                if _nearest_line(starts, runs, origin, look).min() < _nearest_line(start[None], run[None], origin, look)[0] - 1e-6:
                    continue  # another drawn line is nearer the pointer
                if not _on_line(_click(frame, member, origin, look), start, run, look):
                    misses.append((tuple(look), tuple(np.round(middle, 3)), pixels))
    assert not misses


def test_a_faces_triangulation_is_no_drawn_line(frame):
    # Looking straight at a face, at the middle of a diagonal its triangles meet along, clear of its
    # edges: the diagonal is not drawn, so the pointer is near no line.
    runner, slot = frame
    from kumiki.viewer.rule_at_home import Float3

    entry = slot.mesh_cache["Left Side#0"]
    starts, runs = runner._world_creases(entry)
    a, b, c = runner._world_triangles(entry)
    reach = 6 * PIXEL
    aimed = 0
    for corners in zip(a, b, c):
        normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
        look = -normal / np.linalg.norm(normal)
        for one, other in ((0, 1), (1, 2), (2, 0)):
            middle = (corners[one] + corners[other]) / 2
            origin = middle - look * 5
            if _nearest_line(starts, runs, origin, look).min() < 3 * reach:
                continue  # an edge of the face, or near one
            assert runner._mesh_point_near_ray(entry, Float3.of(origin), Float3.of(look), reach) is None
            aimed += 1
    assert aimed
