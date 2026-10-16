"""kigumi's runner: in a drawing's view, everything under the pointer is a candidate, at any depth.

From the sawhorse beam's side, the dovetail's flank is seen edge-on: its front edge (on the
beam's face) and its back edge (in the socket) are one line on the sheet. Which of them the
ray's first hit landed nearer to was chance, and the other was no candidate at all -- not even
in the right-click menu.
"""

import importlib.util
import sys
import types
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FRONT = "rptw.right×dovetail_right_flank"
BACK = "dovetail_right_flank×dovetail_wide_face"
LOOK = [0.0, -1.0, 0.0]


@pytest.fixture(scope="module")
def picked():
    spec = importlib.util.spec_from_file_location("kigumi_runner_whole_ray", REPO / "kigumi" / "runner.py")
    runner = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_whole_ray"] = runner
    spec.loader.exec_module(runner)
    from kumiki.csg.cutcsg import DerivedEdgeFeature, OwnedFeatureHit, csg_children
    from kumiki.picking import edge_highlight_segments, node_positions

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        module_spec = importlib.util.spec_from_file_location("sawhorse", REPO / "patterns" / "structures" / "dovetailed_sawhorse.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        beam = module.dovetailed_sawhorse().cut_timbers[0]
        root = beam.render_timber_with_cuts_csg_local()
        slot = types.SimpleNamespace(mesh_cache={"m#0": {
            "mesh": runner._cut_timber_to_triangle_mesh_payload(beam, root, "m#0"), "local_csg": root, "cut_timber": beam}})
    positions = node_positions(root)

    def owned(name, first_label):
        found = []
        def walk(node):
            for feature in node.get_declared_features():
                if feature.name == name and positions[id(node)][2][:1] == ([first_label] if first_label else positions[id(node)][2][:1]):
                    found.append(OwnedFeatureHit(feature=feature, owner=node))
            for child in csg_children(node):
                walk(child)
        walk(root)
        return found[0]

    front = DerivedEdgeFeature.derive(owned("rptw.right", None), owned("dovetail_right_flank", "free_dovetail"))
    segment = edge_highlight_segments(front, root, beam.timber, root)[0][0]
    on_line = [(a + b) / 2 for a, b in zip(segment["start"], segment["end"])]

    def pick(offset, space):
        # Shifted across the line, then onto the first surface the ray meets there.
        across = [on_line[0] + offset, on_line[1], on_line[2]]
        from kumiki.rule import create_v3
        point = next(
            p for p in ([across[0], across[1] + 0.05 - k * 0.0001, across[2]] for k in range(4000))
            if root.contains_point(beam.timber.transform.global_to_local(create_v3(*p))))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = runner._handle_find_csg_at_point(None, {
                "memberKey": "m#0", "point": point, "currentPath": [], "ctrlClick": False, "space": space,
                "ray": {"origin": [point[0], point[1] + 1.0, point[2]], "direction": LOOK},
                "tolerances": {"face": 0.0005, "edge": 0.002, "point": 0.004},
            }, slot)
        return [candidate["label"] for candidate in result["candidates"]]

    return pick


@pytest.mark.parametrize("offset", [-0.0004, 0.0004])
def test_both_edges_of_a_flank_seen_edge_on_are_candidates_whichever_side_the_click_lands(picked, offset):
    labels = picked(offset, "projected")

    assert FRONT in labels and BACK in labels


def test_the_3d_view_still_picks_the_surface_the_pointer_is_on(picked):
    # Into the socket, past the beam's face: only what is there.
    assert FRONT not in picked(0.0004, "3d")
