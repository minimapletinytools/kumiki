"""Editing a drawing's layout in the viewer (kigumi/runner.py set_drawing_layout).

The viewer sends the whole viewport tree back; the drawings file keeps it over the code's, by
viewport name, so a moved view keeps its measurements and a copy is drawn as its original.
"""

import copy

import pytest

from kumiki.drawings.drawing import Drawing, Viewport, columns, covering_page
from kumiki.drawings.layout import layout_from_wire, layout_to_wire, resolve_viewports, wire_leaf_nodes
from kumiki.drawings.drawing import Page, shop_drawing_viewports
from tests.test_kigumi_drawings_file import _frame, _plan_frame, _write_file, runner


PAGE = Page(0.42, 0.297)


@pytest.fixture
def example(tmp_path):
    return tmp_path / "shed.py"


def _plan(frame, example, pending=()):
    return next(d for d in runner.collect_drawings(frame, example, list(pending)) if d["id"] == "plan")


def _views(scene):
    return {view["id"]: view for view in scene["viewports"]}


def _leaf_node(layout, name):
    return next(node for node in wire_leaf_nodes(layout) if node["leaf"] == name)


def _floating(layout, name, rect):
    """`layout` with the view `name` taken out of its grid and floated at `rect`."""
    edited = copy.deepcopy(layout)

    def drop(node):
        split = node.get("split")
        if not split:
            return
        split["portions"] = [p for p in split["portions"] if p["node"].get("leaf") != name]
        for portion in split["portions"]:
            drop(portion["node"])

    for root in edited["roots"]:
        drop(root)
    edited["roots"].append({"rect": rect, "z": 1, "leaf": name})
    return edited


def test_the_wire_form_lays_out_the_same_rects():
    viewports = shop_drawing_viewports()
    leaves = {str(view.id): view.viewport for view in resolve_viewports(viewports, PAGE)}
    again = layout_from_wire(layout_to_wire(viewports), leaves)
    assert ([(str(v.id), v.rect) for v in resolve_viewports(again, PAGE)]
            == [(str(v.id), v.rect) for v in resolve_viewports(viewports, PAGE)])


def test_a_split_left_holding_one_view_becomes_that_view():
    wire = layout_to_wire((covering_page(columns(Viewport(label="A"), Viewport(label="B"))),))
    leaves = {"A": Viewport(label="A")}
    tree = layout_from_wire(wire, leaves)
    assert len(tree) == 1 and tree[0].is_leaf and tree[0].id == "A" and tree[0].rect == (0.0, 0.0, 1.0, 1.0)


def test_a_code_drawing_carries_its_layout_and_which_views_the_code_has(example):
    scene = _plan(_plan_frame(), example)
    assert not scene["layoutEdited"]
    assert sorted(scene["layout"]["codeLeaves"]) == sorted(_views(scene))
    assert {node["leaf"] for node in wire_leaf_nodes(scene["layout"])} == set(_views(scene))


def test_a_moved_view_floats_where_it_was_put_and_saves_in_the_override(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    preview_rect = _views(scene)["Preview"]["rect"]
    runner.set_drawing_layout(frame, example, pending, "plan",
                              _floating(scene["layout"], "Preview", [0.6, 0.6, 0.3, 0.3]))
    moved = _plan(frame, example, pending)
    assert moved["layoutEdited"] and moved["dirty"] and moved["origin"] == runner.ORIGIN_OVERRIDDEN
    assert _views(moved)["Preview"]["rect"] == pytest.approx([0.6, 0.6, 0.3, 0.3])
    assert _views(moved)["Preview"]["rect"] != preview_rect

    runner.write_drawings_file(example, runner.collect_drawings(frame, example, pending))
    saved = _plan(frame, example)
    assert saved["layoutEdited"] and not saved["dirty"]
    assert _views(saved)["Preview"]["rect"] == pytest.approx([0.6, 0.6, 0.3, 0.3])


def test_putting_the_layout_back_shows_the_codes(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    runner.set_drawing_layout(frame, example, pending, "plan",
                              _floating(scene["layout"], "Preview", [0.6, 0.6, 0.3, 0.3]))
    runner.set_drawing_layout(frame, example, pending, "plan", None)
    back = _plan(frame, example, pending)
    assert not back["layoutEdited"]
    assert _views(back)["Preview"]["rect"] == _views(scene)["Preview"]["rect"]


def test_a_deleted_view_is_not_drawn_and_its_measurements_are_kept(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    name = next(n for n in _views(scene) if n != "Preview")
    edited = _floating(scene["layout"], name, [0.1, 0.1, 0.2, 0.2])
    edited["roots"] = [root for root in edited["roots"] if root.get("leaf") != name]
    runner.set_drawing_layout(frame, example, pending, "plan", edited)
    assert name not in _views(_plan(frame, example, pending))


def test_a_copy_is_drawn_as_its_original(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    original = next(n for n in _views(scene) if n != "Preview")
    edited = copy.deepcopy(scene["layout"])
    node = _leaf_node(edited, original)
    leaf = dict(node)
    node.clear()
    node["split"] = {"direction": "columns", "gap": 0.0, "portions": [
        {"share": 1.0, "node": leaf},
        {"share": 1.0, "node": {"leaf": f"{original} 2", "copyOf": original}},
    ]}
    runner.set_drawing_layout(frame, example, pending, "plan", edited)
    views = _views(_plan(frame, example, pending))
    was, kept, made = _views(scene)[original], views[original], views[f"{original} 2"]
    assert made["camera"]["look"] == kept["camera"]["look"]
    assert made["rect"][2] == pytest.approx(was["rect"][2] / 2)
    assert _leaf_node(_plan(frame, example, pending)["layout"], f"{original} 2")["copyOf"] == original


def test_a_view_the_code_gains_after_the_layout_was_saved_floats_in(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    edited = copy.deepcopy(scene["layout"])
    edited["codeLeaves"] = [name for name in edited["codeLeaves"] if name != "Preview"]
    runner.set_drawing_layout(frame, example, pending, "plan", edited)
    assert "Preview" in _views(_plan(frame, example, pending))
    edited = _floating(scene["layout"], "Preview", [0.6, 0.6, 0.3, 0.3])
    edited["roots"] = [root for root in edited["roots"] if root.get("leaf") != "Preview"]
    runner.set_drawing_layout(frame, example, pending, "plan", edited)
    assert "Preview" not in _views(_plan(frame, example, pending))


def test_laying_out_keeps_the_overrides_saved_measurements(example):
    frame = _plan_frame()
    saved_viewports = [{"id": "Front", "measurements": [{"a": {"timber": "post"}, "b": {"timber": "post"}}]}]
    _write_file(example, [{"id": "plan-measurements", runner.OVERRIDES_KEY: "plan", "viewports": saved_viewports}])
    pending = []
    scene = _plan(frame, example)
    runner.set_drawing_layout(frame, example, pending, "plan",
                              _floating(scene["layout"], "Preview", [0.6, 0.6, 0.3, 0.3]))
    held = next(entry for entry in pending if entry["id"] == "plan-measurements")
    assert held["viewports"] == saved_viewports and "layout" in held


def test_a_drawing_of_the_files_own_keeps_its_copies_as_viewports(example):
    frame = _frame(paths=("posts/fl",))
    pending = []
    drawing = runner.create_drawing_from_selection(frame, ["posts/fl"])
    drawing.update(id="mine", name="mine", origin=runner.ORIGIN_FILE)
    pending.append(drawing)
    scene = next(d for d in runner.collect_drawings(frame, example, pending) if d["id"] == "mine")
    original = next(n for n in _views(scene) if n != "Preview")
    edited = copy.deepcopy(scene["layout"])
    edited["roots"].append({"rect": [0.7, 0.7, 0.2, 0.2], "z": 1, "leaf": "copy", "copyOf": original})
    runner.set_drawing_layout(frame, example, pending, "mine", edited)
    views = _views(next(d for d in runner.collect_drawings(frame, example, pending) if d["id"] == "mine"))
    assert views["copy"]["rect"] == pytest.approx([0.7, 0.7, 0.2, 0.2])
    assert views["copy"]["camera"]["look"] == views[original]["camera"]["look"]


def test_a_layout_with_no_views_is_refused(example):
    with pytest.raises(ValueError):
        runner.set_drawing_layout(_plan_frame(), example, [], "plan", {"roots": []})


def test_a_measurement_added_in_a_new_session_keeps_the_saved_ones(example):
    from tests.test_kigumi_drawings_file import _ref

    frame = _plan_frame()

    def ref(feature):
        return _ref(feature, timber="post", csg_path=())

    pending = []
    runner.add_measurement(frame, example, pending, "plan", "Front", {"a": ref("front"), "b": ref("back")})
    runner.write_drawings_file(example, runner.collect_drawings(frame, example, pending))
    pending = []
    runner.add_measurement(frame, example, pending, "plan", "Front", {"a": ref("left"), "b": ref("right")})
    measured = [(m["a"]["feature"], m["b"]["feature"]) for m in _views(_plan(frame, example, pending))["Front"]["measurements"]]
    assert sorted(measured) == [("front", "back"), ("left", "right")]


def _aimed(layout, name, camera):
    edited = copy.deepcopy(layout)
    _leaf_node(edited, name)["camera"] = camera
    return edited


def test_a_view_given_a_camera_looks_along_it_fitted_to_what_it_draws(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    name = next(n for n in _views(scene) if n != "Preview")
    runner.set_drawing_layout(frame, example, pending, "plan",
                              _aimed(scene["layout"], name, {"look": [0, 0, -1], "up": [0, 1, 0]}))
    aimed = _plan(frame, example, pending)
    camera = _views(aimed)[name]["camera"]
    assert camera["look"] == pytest.approx([0, 0, -1]) and camera["up"] == pytest.approx([0, 1, 0])
    assert camera["extent"] > 0
    assert _leaf_node(aimed["layout"], name)["camera"] == {"look": [0, 0, -1], "up": [0, 1, 0]}


def test_a_zoomed_view_keeps_where_it_was_put(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    name = next(n for n in _views(scene) if n != "Preview")
    look = _views(scene)[name]["camera"]["look"]
    up = _views(scene)[name]["camera"]["up"]
    runner.set_drawing_layout(frame, example, pending, "plan", _aimed(
        scene["layout"], name, {"look": look, "up": up, "target": [1.0, 2.0, 3.0], "extent": 0.25}))
    camera = _views(_plan(frame, example, pending))[name]["camera"]
    assert camera["target"] == [1.0, 2.0, 3.0] and camera["extent"] == 0.25


def test_the_preview_turned_to_a_preset_is_drawn_square_on(example):
    frame = _plan_frame()
    pending = []
    scene = _plan(frame, example)
    runner.set_drawing_layout(frame, example, pending, "plan", _aimed(
        scene["layout"], "Preview", {"look": [0, 1, 0], "up": [0, 0, 1], "projection": "orthographic"}))
    preview = _views(_plan(frame, example, pending))["Preview"]
    assert preview["projection"] == "orthographic" and preview["locked"] and "orbit" not in preview


def test_a_drawing_of_the_files_own_keeps_its_views_cameras(example):
    frame = _frame(paths=("posts/fl",))
    pending = []
    drawing = runner.create_drawing_from_selection(frame, ["posts/fl"])
    drawing.update(id="mine", name="mine", origin=runner.ORIGIN_FILE)
    pending.append(drawing)
    mine = lambda: next(d for d in runner.collect_drawings(frame, example, pending) if d["id"] == "mine")
    scene = mine()
    name = next(n for n in _views(scene) if n != "Preview")
    runner.set_drawing_layout(frame, example, pending, "mine",
                              _aimed(scene["layout"], name, {"look": [1, 0, 0], "up": [0, 0, 1]}))
    again = mine()
    assert _views(again)[name]["camera"]["look"] == pytest.approx([1, 0, 0])
    assert _leaf_node(again["layout"], name)["camera"]["look"] == [1, 0, 0]


def test_a_turned_view_keeps_its_measurements_on_the_plane_they_were_made_in(example):
    frame = _plan_frame()
    scene = _plan(frame, example)
    name = next(n for n in _views(scene) if n != "Preview")
    look = _views(scene)[name]["camera"]["look"]
    turned_to = [0, 0, -1] if abs(look[2]) < 0.9 else [0, 1, 0]
    turned = copy.deepcopy(scene)
    turned["layout"] = _aimed(scene["layout"], name, {"look": turned_to, "up": [0, 1, 0] if turned_to[2] else [0, 0, 1]})
    zoomed = copy.deepcopy(scene)
    zoomed["layout"] = _aimed(scene["layout"], name, {"look": look, "up": _views(scene)[name]["camera"]["up"]})

    was = runner._aim_viewports(turned, frame)
    assert runner._aim_viewports(zoomed, frame) == {}
    assert was[name]["look"] == look
    # Without a plane of its own: given the one it was made in, which the turned view no longer shows.
    resolved = runner._resolve_in_view(frame, turned, name, {"a": None, "b": None}, was[name])
    assert resolved["plane"]["normal"] == look

    # Turned round to look from behind: the same plane, but measured from the other side.
    behind = copy.deepcopy(scene)
    behind["layout"] = _aimed(scene["layout"], name, {"look": [-v for v in look], "up": _views(scene)[name]["camera"]["up"]})
    assert name in runner._aim_viewports(behind, frame)
    assert "plane" not in runner._resolve_in_view(frame, zoomed, name, {"a": None, "b": None}, None)


def test_a_measurement_made_in_the_viewer_is_behind_a_view_that_looks_at_its_back():
    made = {"plane": {"at": [0, 0, 0], "normal": [0, 1, 0]}, "origin": runner.ORIGIN_FILE}
    assert not runner._seen_from_behind(made, [0, 1, 0], None)
    assert runner._seen_from_behind(made, [0, -1, 0], None)
    # Turned back to the way it was made: in front again, whatever the code's camera is.
    assert not runner._seen_from_behind(made, [0, 1, 0], {"look": [0, -1, 0]})
    # A plane from code faces either way: behind only once the view is turned round.
    coded = {**made, "origin": runner.ORIGIN_CODE}
    assert not runner._seen_from_behind(coded, [0, -1, 0], None)
    assert runner._seen_from_behind(coded, [0, -1, 0], {"look": [0, 1, 0]})
