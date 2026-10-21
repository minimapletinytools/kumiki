"""A drawing's view offers a timber's reference planes -- centerplanes, perfect-timber faces -- seen
edge-on, wherever the pointer is on the line they draw: behind another member, and with a peg's axis
drawn along the same line. On the cute frame, drawn whole."""

import contextlib
import importlib.util
import io
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from kumiki.csg.feature_extent import FeatureExtents

REPO = Path(__file__).resolve().parent.parent
TOLERANCES = {"face": 5e-4, "edge": 0.012, "point": 0.020}


@pytest.fixture(scope="module")
def frame():
    spec = importlib.util.spec_from_file_location("kigumi_runner_reference_picks", REPO / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_reference_picks"] = runner
    spec.loader.exec_module(runner)
    # Loading purges kumiki where it is installed from this checkout (as on CI); the rest of the
    # session keeps the modules it imported, as test_kigumi_generated_drawings does.
    saved_modules = dict(sys.modules)
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        slot = runner.load_slot_state(str(REPO / "patterns" / "structures" / "my_cute_frame_drawing_test.py"))
        runner.build_real_geometry(None, slot)
    yield runner, slot
    sys.modules.clear()
    sys.modules.update(saved_modules)


def _first_hit(slot, origin, look):
    """The member a ray meets first, and where: as the viewer finds it on the meshes."""
    best = (np.inf, None)
    for key, entry in slot.mesh_cache.items():
        if entry.get("cut_timber") is None:
            continue
        v = np.array(entry["mesh"]["vertices"]).reshape(-1, 3)
        f = np.array(entry["mesh"]["indices"]).reshape(-1, 3)
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        e1, e2 = b - a, c - a
        p = np.cross(look, e2)
        det = (e1 * p).sum(1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
        s = origin - a
        u = (s * p).sum(1) * inv
        q = np.cross(s, e1)
        w = (look * q).sum(1) * inv
        t = (e2 * q).sum(1) * inv
        hit = ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 0)
        if hit.any() and t[hit].min() < best[0]:
            best = (float(t[hit].min()), key)
    return best[1], origin + look * best[0]


def _anchor(frame, member, feature):
    """Where a dimension would hang on `feature` of `member`: its middle, world space."""
    from kumiki.csg.cutcsg import OwnedFeatureHit, csg_children
    from kumiki.csg.feature_paths import FeatureHandle
    from kumiki.drawings.kigumi_measuring_helpers import feature_anchor
    from kumiki.rule import as_ndarray

    _runner, slot = frame
    entry = slot.mesh_cache[member]
    nodes, index = [entry["local_csg"]], 0
    while index < len(nodes):
        nodes += csg_children(nodes[index])
        index += 1
    owner = next(node for node in nodes if any(f.name == feature for f in node.get_declared_features()))
    declared = next(f for f in owner.get_declared_features() if f.name == feature)
    handle = FeatureHandle(timber=entry["cut_timber"].timber, hit=OwnedFeatureHit(feature=declared, owner=owner))
    anchor = feature_anchor(handle, entry["cut_timber"].feature_extents())
    assert anchor is not None
    return as_ndarray(anchor)


def _offered(frame, member, feature, look):
    """Aim at `feature`'s middle on `member`, looking along `look`: the member the ray met first,
    and whether the feature is among what can be taken there."""
    runner, slot = frame
    look = np.array(look, dtype=float)
    origin = _anchor(frame, member, feature) - look * 10
    hit, point = _first_hit(slot, origin, look)
    payload = {"memberKey": hit, "point": [float(x) for x in point], "currentPath": [], "ctrlClick": False,
               "space": "projected", "tolerances": TOLERANCES, "look": list(look),
               "ray": {"origin": [float(x) for x in origin], "direction": list(look)}}
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        reply = runner._handle_find_csg_at_point(None, payload, slot)
    takeable = (reply.get("candidates") or [])[:reply.get("candidateCount") or 0]
    return hit, any(c.get("label") == feature and c.get("memberKey") == member for c in takeable)


@pytest.mark.parametrize("feature", ["ptw.centerplane_front_back", "ptw.front"])
def test_a_reference_plane_behind_another_member_is_offered(frame, feature):
    hit, offered = _offered(frame, "Back Cross#0", feature, [0, -1.0, 0])
    assert hit == "Front Cross#0", "the ray meets the front member first"
    assert offered


def test_a_centerplane_with_a_pegs_axis_drawn_along_it_is_offered(frame):
    hit, offered = _offered(frame, "Left Side#0", "ptw.centerplane_left_right", [0, 1.0, 0])
    assert hit == "Left Side#0"
    assert offered


# --- the slack is in screen pixels, either side -----------------------------------------------

PIXEL = 0.001  # what a pixel is worth, in metres, at the zoom the tolerances below stand for


def _reply(frame, origin, look, space, pixel):
    runner, slot = frame
    hit, point = _first_hit(slot, origin, look)
    payload = {"memberKey": hit, "point": [float(x) for x in point] if hit else None, "currentPath": [],
               "ctrlClick": False, "space": space, "look": list(look),
               "tolerances": {"face": 5e-4, "edge": 12 * pixel, "point": 20 * pixel},
               "ray": {"origin": [float(x) for x in origin], "direction": list(look)}}
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        reply = runner._handle_find_csg_at_point(None, payload, slot)
    # The 3D view's candidates are all the picked member's, and say so once, on the reply.
    return [{"memberKey": reply.get("memberKey"), **candidate}
            for candidate in (reply.get("candidates") or [])[:reply.get("candidateCount") or 0]]


def _box(frame, member):
    _runner, slot = frame
    vertices = np.array(slot.mesh_cache[member]["mesh"]["vertices"]).reshape(-1, 3)
    return vertices.min(0), vertices.max(0)


@pytest.mark.parametrize("pixels", [-8, 8])
def test_a_drawing_offers_an_edge_from_either_side_of_it(frame, pixels):
    low, high = _box(frame, "Left Side#0")
    look = np.array([0, 0, -1.0])
    origin = np.array([high[0] + pixels * PIXEL, low[1] + (high[1] - low[1]) * 0.63, 10.0])
    offered = _reply(frame, origin, look, "projected", PIXEL)
    assert any(c.get("type") == "EDGE" and c.get("memberKey") == "Left Side#0" for c in offered)


def test_the_3d_view_offers_a_centerplane_a_few_pixels_off_its_line(frame):
    low, high = _box(frame, "Left Side#0")
    plane = _anchor(frame, "Left Side#0", "ptw.centerplane_left_right")
    middle = np.array([plane[0], low[1] + (high[1] - low[1]) * 0.63, high[2]])
    camera = middle + 2.0 * np.array([np.cos(np.radians(30)), 0, np.sin(np.radians(30))])
    look = (middle - camera) / np.linalg.norm(middle - camera)
    per_pixel = 2 * 2.0 * np.tan(np.radians(22.5)) / 800
    across = np.cross(look, np.cross([1.0, 0, 0], look))
    aimed = look + across / np.linalg.norm(across) * (8 * per_pixel / 2.0)
    offered = _reply(frame, camera, aimed / np.linalg.norm(aimed), "3d", per_pixel)
    assert any("centerplane" in (c.get("label") or "") and c.get("memberKey") == "Left Side#0" for c in offered)


def test_a_shoulder_crossing_a_perfect_face_of_rough_stock_has_a_line_to_draw(frame):
    # Neither parent has corners to bound the edge -- a half space and a bare plane -- so it is
    # drawn where it is on the timber: across the shoulder face. Without that it was picked, and
    # nothing was lit.
    from kumiki.csg.cutcsg import DerivedEdgeFeature, FeatureGroup, OwnedFeatureHit, csg_children
    from kumiki.viewer.picking import edge_highlight_segments

    _runner, slot = frame
    cut = slot.mesh_cache["Back Cross#0"]["cut_timber"]
    root = slot.mesh_cache["Back Cross#0"]["local_csg"]
    nodes, index = [root], 0
    while index < len(nodes):
        nodes += csg_children(nodes[index])
        index += 1
    hits = [OwnedFeatureHit(feature=feature, owner=node) for node in nodes for feature in node.get_declared_features()]
    shoulder = next(hit for hit in hits if hit.feature.group is FeatureGroup.SHOULDER_PLANE)
    face = next(hit for hit in hits if hit.feature.name == "ptw.front")
    edge = DerivedEdgeFeature.derive(shoulder, face)
    assert edge is not None and not edge.real
    segments, absent = edge_highlight_segments(edge, shoulder.owner, FeatureExtents(root, cut.timber))
    assert not absent
    assert segments, "a line to draw"
    start, end = segments[0]["start"], segments[0]["end"]
    assert abs(sum((a - b) ** 2 for a, b in zip(start, end)) ** 0.5 - 0.1154) < 0.002, "across the rough stock"
