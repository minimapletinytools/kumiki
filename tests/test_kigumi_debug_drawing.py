"""Tests for the scaffolding drawing kigumi builds for the viewer (kigumi/runner.py).

The viewer trusts three things about a camera frame: the axes are orthogonal,
`look` is the direction of view, and `extent` fits the model. It normalizes away
anything malformed rather than complaining, so a broken frame here would show up
only as a viewport quietly pointing somewhere else -- hence pinning them.
"""

import importlib.util
import sys
from pathlib import Path

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.timber import Frame


def _load_runner():
    """Import kigumi/runner.py by path -- kigumi is not an installed package."""
    runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
    spec = importlib.util.spec_from_file_location("kigumi_runner", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _post(bottom_position, length=mm(1000), size=create_v2(mm(100), mm(100))):
    return create_timber(
        bottom_position=bottom_position,
        length=length,
        size=size,
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket="post",
    )


def _frame(*timbers):
    return Frame.from_joints(joints=[], additional_unjointed_timbers=list(timbers))


def _drawing(*timbers):
    return runner.build_default_drawing_for_debugging(_frame(*timbers))


def _orthographic_viewports(drawing):
    return [v for v in drawing["viewports"] if v["projection"] == "orthographic"]


class TestDefaultDebugDrawing:
    def test_it_has_three_elevations_and_one_preview(self):
        drawing = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))

        ids = [viewport["id"] for viewport in drawing["viewports"]]
        assert ids == ["front", "top", "right", "preview"]

    def test_the_elevations_are_locked_and_the_preview_is_not(self):
        drawing = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))

        by_id = {viewport["id"]: viewport for viewport in drawing["viewports"]}
        assert all(by_id[name]["locked"] for name in ("front", "top", "right"))
        assert by_id["preview"]["locked"] is False

    def test_a_drawing_asks_for_no_camera_gizmos(self):
        assert _drawing(_post(create_v3(mm(0), mm(0), mm(0))))["cameraControls"] == []

    def test_it_is_laid_out_on_a_sheet(self):
        # A page with a real size is what lets a view state its scale.
        page = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))["page"]

        assert page["width"] > 0 and page["height"] > 0
        assert page["width"] > page["height"], "expected a landscape sheet"

    def test_the_quadrants_tile_the_page(self):
        drawing = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))

        rects = sorted(tuple(viewport["rect"]) for viewport in drawing["viewports"])
        assert rects == [
            (0.0, 0.0, 0.5, 0.5),
            (0.0, 0.5, 0.5, 0.5),
            (0.5, 0.0, 0.5, 0.5),
            (0.5, 0.5, 0.5, 0.5),
        ]

    def test_every_camera_frame_is_orthonormal(self):
        drawing = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))

        for viewport in _orthographic_viewports(drawing):
            camera = viewport["camera"]
            for axis in ("right", "up", "look"):
                assert abs(_dot(camera[axis], camera[axis]) - 1.0) < 1e-9
            assert abs(_dot(camera["right"], camera["up"])) < 1e-9
            assert abs(_dot(camera["right"], camera["look"])) < 1e-9
            assert abs(_dot(camera["up"], camera["look"])) < 1e-9

    def test_every_camera_frame_is_right_handed(self):
        # right x up == -look, the frame of a camera looking down its own -Z.
        # A flipped one still passes the orthogonality check the viewer runs,
        # and renders the elevation mirrored.
        drawing = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))

        for viewport in _orthographic_viewports(drawing):
            camera = viewport["camera"]
            expected = [-component for component in camera["look"]]
            assert all(
                abs(actual - wanted) < 1e-9
                for actual, wanted in zip(_cross(camera["right"], camera["up"]), expected)
            )

    def test_the_elevations_look_along_the_world_axes(self):
        # Z up, +Y north, +X east: the front elevation looks north, the plan
        # view looks down, and the right elevation looks west from the east.
        by_id = {
            viewport["id"]: viewport["camera"]
            for viewport in _orthographic_viewports(_drawing(_post(create_v3(mm(0), mm(0), mm(0)))))
        }

        assert by_id["front"]["look"] == [0.0, 1.0, 0.0]
        assert by_id["front"]["up"] == [0.0, 0.0, 1.0]
        assert by_id["top"]["look"] == [0.0, 0.0, -1.0]
        assert by_id["right"]["look"] == [-1.0, 0.0, 0.0]

    def test_the_target_is_the_centre_of_everything(self):
        drawing = _drawing(
            _post(create_v3(mm(0), mm(0), mm(0))),
            _post(create_v3(mm(1000), mm(400), mm(0))),
        )

        # x spans -50..1050mm, y -50..450mm, z 0..1000mm.
        for viewport in _orthographic_viewports(drawing):
            target = viewport["camera"]["target"]
            assert abs(target[0] - 0.5) < 1e-9
            assert abs(target[1] - 0.2) < 1e-9
            assert abs(target[2] - 0.5) < 1e-9

    def test_the_extent_covers_the_model_on_both_screen_axes(self):
        # A frame far wider than it is tall: the plan view's extent has to come
        # from the width, or half the frame falls outside the viewport.
        drawing = _drawing(
            _post(create_v3(mm(0), mm(0), mm(0))),
            _post(create_v3(mm(4000), mm(0), mm(0))),
        )

        by_id = {viewport["id"]: viewport["camera"] for viewport in _orthographic_viewports(drawing)}
        assert by_id["top"]["extent"] >= 2.05  # half of 4100mm
        assert by_id["front"]["extent"] >= 2.05

    def test_the_extent_leaves_a_margin(self):
        drawing = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))

        # The post is 1000mm tall, so a snug front elevation would be 0.5.
        assert _orthographic_viewports(drawing)[0]["camera"]["extent"] > 0.5

    def test_an_empty_frame_still_produces_a_usable_drawing(self):
        drawing = _drawing()

        for viewport in _orthographic_viewports(drawing):
            assert viewport["camera"]["target"] == [0.0, 0.0, 0.0]
            assert viewport["camera"]["extent"] > 0.0

    def test_the_elevations_cover_every_timber(self):
        # members: None is the viewer's "all of them".
        drawing = _drawing(_post(create_v3(mm(0), mm(0), mm(0))))

        for viewport in _orthographic_viewports(drawing):
            assert viewport["members"] is None
