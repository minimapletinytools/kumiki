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
from kumiki.viewer.rule_at_home import Float3

REPO = Path(__file__).resolve().parent.parent
FRONT = "rptw.right×dovetail_right_flank"
BACK = "dovetail_right_flank×dovetail_wide_face"
LOOK = [0.0, -1.0, 0.0]


@pytest.fixture(scope="module")
def picked():
    spec = importlib.util.spec_from_file_location("kigumi_runner_whole_ray", REPO / "kigumi" / "runner.py")
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner_whole_ray"] = runner
    spec.loader.exec_module(runner)
    from kumiki.csg.cutcsg import DerivedEdgeFeature, OwnedFeatureHit, csg_children
    from kumiki.viewer.picking import edge_highlight_segments, node_positions

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        module_spec = importlib.util.spec_from_file_location("sawhorse", REPO / "patterns" / "structures" / "dovetailed_sawhorse.py")
        assert module_spec is not None and module_spec.loader is not None
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
    assert front is not None
    segments = edge_highlight_segments(front, root, beam.timber, root)[0]
    assert segments is not None
    segment = segments[0]
    on_line = [(a + b) / 2 for a, b in zip(segment["start"], segment["end"])]

    def pick(offset, space, **extra):
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
                "tolerances": {"face": 0.0005, "edge": 0.002, "point": 0.004}, **extra,
            }, slot)
        return result if extra else [candidate["label"] for candidate in result["candidates"]]

    setattr(pick, "ask", lambda payload: runner._handle_find_csg_at_point(None, payload, slot))
    setattr(pick, "by_path", lambda payload: runner._handle_find_csg_by_path(None, payload, slot))
    return pick


@pytest.mark.parametrize("offset", [-0.0004, 0.0004])
def test_both_edges_of_a_flank_seen_edge_on_are_candidates_whichever_side_the_click_lands(picked, offset):
    labels = picked(offset, "projected")

    assert FRONT in labels and BACK in labels


def test_the_3d_view_still_picks_the_surface_the_pointer_is_on(picked):
    # Into the socket, past the beam's face: only what is there.
    assert FRONT not in picked(0.0004, "3d")


@pytest.mark.parametrize("offset", [-0.0004, 0.0004])
def test_nearest_the_viewer_comes_first(picked, offset):
    # The front edge leads, ahead of the face it lies on (no depth between them), and the back
    # edge comes after both, however the declared-before-derived order would have had it.
    labels = picked(offset, "projected")

    assert labels[0] == FRONT
    assert labels.index(FRONT) < labels.index(BACK)


def test_whichever_candidate_is_chosen_is_the_one_answered(picked):
    # Settled once and read for everything: of two named alike (a dovetail_wide_face on each of
    # two dovetails) the first used to answer for both.
    candidates = picked(0.0004, "projected", candidateIndex=0)["candidates"]

    for index, candidate in enumerate(candidates):
        chosen = picked(0.0004, "projected", candidateIndex=index)
        if candidate["hidden"]:  # never taken, even when named
            assert chosen["candidates"][chosen["candidateIndex"]]["hidden"] is False
        else:
            assert (chosen["candidateIndex"], chosen["featureLabel"]) == (index, candidate["label"])


def test_a_drawing_offers_no_face_it_cannot_measure(picked):
    # The beam's faces and the socket floors are areas from here; the flank is edge-on, but its
    # edges lie on the same line and measure the same. A centerplane edge-on is a line of its own.
    labels = picked(0.0004, "projected")

    assert labels and all("×" in label or label.startswith("ptw.centerplane") for label in labels)


def test_the_3d_view_keeps_its_faces(picked):
    assert "dovetail_wide_face" in picked(0.0004, "3d")


def test_a_cylinder_cap_seen_edge_on_is_kept_and_a_face_beside_its_edge_is_not():
    from kumiki.viewer import picking
    from kumiki.csg.cutcsg import (CSGFeatureType, Cylinder, OwnedFeatureHit, RectangularPrism, END_CAP,
                                   PrismFace, prism_arris_key, prism_face_key)
    from kumiki.rule import create_v2, create_v3, scalar

    peg = Cylinder(axis_direction=create_v3(1, 0, 0), radius=scalar(1), start_distance=scalar(0), end_distance=scalar(5))
    cap = next(f for f in peg.get_declared_features() if f.feature_key() == END_CAP)
    box = RectangularPrism(size=create_v2(2, 2), start_distance=scalar(0), end_distance=scalar(4))
    right = next(f for f in box.get_declared_features() if f.feature_key() == prism_face_key(PrismFace.RIGHT))
    arris = next(f for f in box.get_declared_features() if f.feature_key() == prism_arris_key(PrismFace.RIGHT, PrismFace.FRONT))
    front = next(f for f in box.get_declared_features() if f.feature_key() == prism_face_key(PrismFace.FRONT))
    hits = [OwnedFeatureHit(feature=feature, owner=owner)
            for feature, owner in ((cap, peg), (right, box), (arris, box), (front, box))]
    assert cap.feature_type() is CSGFeatureType.FACE

    # Looking along y: the peg's cap (normal x) and the box's right face are edge-on, its front is not.
    kept = [hit.feature for hit in picking.measurable_in_view(hits, Float3(0.0, 1.0, 0.0), 1e-3)]

    assert cap in kept and arris in kept
    assert right not in kept  # the arris in its plane measures the same
    assert front not in kept  # an area from here


@pytest.mark.parametrize("offset", [-0.0004, 0.0004])
def test_what_is_not_seen_under_the_pointer_is_offered_but_not_taken(picked, offset):
    # The back edge is stacked exactly behind the front one along the view; the far dovetail's
    # edges are behind the beam itself. Both are listed, last and marked, and none is chosen.
    result = picked(offset, "projected", drawnMembers=["m#0"])
    hidden = {candidate["label"]: candidate["hidden"] for candidate in result["candidates"]}

    assert result["featureLabel"] == FRONT and not hidden[FRONT]
    assert hidden[BACK]
    assert hidden["rptw.left×dovetail_left_flank"]
    assert result["candidateCount"] == sum(1 for is_hidden in hidden.values() if not is_hidden)
    assert [candidate["hidden"] for candidate in result["candidates"]] == sorted(hidden.values())


def test_a_line_of_sight_along_a_surface_is_not_blocked_by_it():
    # A box seen edge-on along its top face: a place on the top's far edge looks back along the
    # face, which is surface, not material -- the stacked rule, not this one, says it is hidden.
    from kumiki.csg.cutcsg import RectangularPrism
    from kumiki.drawings.visibility import sight_is_blocked
    from kumiki.rule import create_v2, scalar

    box = RectangularPrism(size=create_v2(2, 2), start_distance=scalar(0), end_distance=scalar(4))

    from kumiki.rule import create_v3

    assert not sight_is_blocked(box, create_v3(1, 1, 4), create_v3(0, -1, 0))
    assert sight_is_blocked(box, create_v3(0, 1, 2), create_v3(0, -1, 0))


def test_where_everything_under_the_pointer_is_hidden_nothing_is_taken(picked):
    # The beam's side, face-on, just over the dovetail socket: only the socket's edges behind it.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = picked.ask({
            "memberKey": "m#0", "point": [-0.3912, 0.0254, 0.7353], "currentPath": [], "ctrlClick": False,
            "space": "projected", "ray": {"origin": [-0.3912, 1.0254, 0.7353], "direction": LOOK},
            "tolerances": {"face": 0.0005, "edge": 0.002, "point": 0.004},
        })

    assert result["candidates"] and all(candidate["hidden"] for candidate in result["candidates"])
    assert result["candidateCount"] == 0
    assert result["featureLabel"] is None and result["candidateIndex"] is None and result["path"] == []


def test_a_drawing_has_no_drilling_so_ctrl_is_a_plain_click(picked):
    # A drawing's view picks features directly, every timber alike.
    plain = picked(0.0004, "projected", ctrlClick=False)
    with_ctrl = picked(0.0004, "projected", ctrlClick=True)

    assert (with_ctrl["featureLabel"], with_ctrl["path"]) == (plain["featureLabel"], plain["path"])
    assert plain["featureLabel"] is not None


@pytest.mark.parametrize("name", ["ptw.centerplane_left_right", "ptw.centerplane_front_back"])
def test_a_centerplane_lights_its_outline_and_no_triangles(picked, name):
    # It is no surface: tested triangle by triangle it lit whichever it happened to pass through.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = picked.by_path({"memberKey": "m#0", "path": ["timber (rough, extended)"], "featureLabel": name})

    assert result["featureLabel"] == name
    assert result["highlightMesh"]["indices"] == []
    assert len(result["highlightEdgeSegments"]) == 4
