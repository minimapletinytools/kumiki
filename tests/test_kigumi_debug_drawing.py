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
        # A frame far wider than it is tall. The extent is a half-*height* and
        # the viewer widens the frustum by the viewport's aspect, so what has to
        # hold is that the model fits once that widening is applied -- asserting
        # the height alone covers the width would demand a view 1.4x too tall.
        drawing = _drawing(
            _post(create_v3(mm(0), mm(0), mm(0))),
            _post(create_v3(mm(4000), mm(0), mm(0))),
        )
        page = drawing["page"]

        # The model's half-extents: x spans -50..4050mm, y -50..50, z 0..1000.
        half = (2.05, 0.05, 0.5)

        def reaches(axis):
            """How far the model reaches along a screen axis."""
            return sum(abs(axis[i]) * half[i] for i in range(3))

        for viewport in _orthographic_viewports(drawing):
            camera = viewport["camera"]
            aspect = (viewport["rect"][2] * page["width"]) / (viewport["rect"][3] * page["height"])
            # Whatever the model reaches across the screen must fit the width,
            # and what it reaches up the screen must fit the height. The third
            # axis is depth and does not have to fit anything.
            assert camera["extent"] * aspect >= reaches(camera["right"])
            assert camera["extent"] >= reaches(camera["up"])

    def test_a_wide_model_is_not_framed_as_if_it_were_tall(self):
        # The bug the aspect fixes: a 4m-wide, 1m-tall frame in a landscape
        # viewport needs no more height than the model has.
        drawing = _drawing(
            _post(create_v3(mm(0), mm(0), mm(0))),
            _post(create_v3(mm(4000), mm(0), mm(0))),
        )
        front = next(v for v in _orthographic_viewports(drawing) if v["id"] == "front")

        assert front["camera"]["extent"] < 2.0

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


def _beam(bottom_position, length=mm(2400), size=create_v2(mm(100), mm(200))):
    """A timber lying along +X, so its own axes differ from the world's."""
    return create_timber(
        bottom_position=bottom_position,
        length=length,
        size=size,
        length_direction=create_v3(1, 0, 0),
        width_direction=create_v3(0, 1, 0),
        ticket="beam",
    )


def _selection(timbers, keys):
    return runner.create_drawing_from_selection(_frame(*timbers), keys)


class TestDrawingFromSelection:
    def test_one_timber_gets_its_four_long_faces_and_a_preview(self):
        # The shop drawing for a single piece: every long side, rolled out.
        drawing = _selection([_beam(create_v3(mm(0), mm(0), mm(0)))], ["beam#0"])

        assert [v["id"] for v in drawing["viewports"]] == ["front", "right", "back", "left", "preview"]

    def test_the_four_faces_look_at_four_different_sides(self):
        drawing = _selection([_beam(create_v3(mm(0), mm(0), mm(0)))], ["beam#0"])

        looks = [tuple(v["camera"]["look"]) for v in _orthographic_viewports(drawing)]
        assert len(set(looks)) == 4
        # Opposite faces, so the four directions cancel out.
        for axis in range(3):
            assert abs(sum(look[axis] for look in looks)) < 1e-9

    def test_each_face_view_runs_the_length_across_the_page(self):
        # A piece is drawn lying down, not standing up: its length is the
        # screen's horizontal, whatever the timber's orientation in the world.
        beam = _beam(create_v3(mm(0), mm(0), mm(0)))
        drawing = _selection([beam], ["beam#0"])

        for viewport in _orthographic_viewports(drawing):
            assert viewport["camera"]["right"] == [1.0, 0.0, 0.0]

    def test_the_face_views_are_square_on_to_their_face(self):
        # Looking along the face normal, so the face is drawn true and not
        # foreshortened -- otherwise a measurement off it means nothing.
        drawing = _selection([_beam(create_v3(mm(0), mm(0), mm(0)))], ["beam#0"])

        for viewport in _orthographic_viewports(drawing):
            camera = viewport["camera"]
            assert abs(_dot(camera["look"], camera["right"])) < 1e-9
            expected = [-component for component in camera["look"]]
            assert all(
                abs(a - b) < 1e-9
                for a, b in zip(_cross(camera["right"], camera["up"]), expected)
            )

    def test_a_long_piece_is_framed_by_its_length_not_squashed(self):
        # The strips are much wider than they are tall, so the extent has to
        # come from the length divided by that aspect. Ignoring the aspect
        # frames a 2.4m beam as though it needed 2.4m of height.
        beam = _beam(create_v3(mm(0), mm(0), mm(0)))
        drawing = _selection([beam], ["beam#0"])
        page = drawing["page"]

        for viewport in _orthographic_viewports(drawing):
            rect = viewport["rect"]
            aspect = (rect[2] * page["width"]) / (rect[3] * page["height"])
            half_width = viewport["camera"]["extent"] * aspect
            assert half_width >= 1.2, "the beam's half length must fit across"
            assert viewport["camera"]["extent"] < 0.5, "and not be framed as if it were tall"

    def test_several_members_are_drawn_as_world_elevations(self):
        # No single piece for the sheet to be about, so it falls back to the
        # views that describe an assembly.
        timbers = [_beam(create_v3(mm(0), mm(0), mm(0))), _post(create_v3(mm(0), mm(0), mm(0)))]
        drawing = _selection(timbers, ["beam#0", "post#0"])

        assert [v["id"] for v in drawing["viewports"]] == ["front", "top", "right", "preview"]

    def test_the_drawing_names_the_members_it_is_about(self):
        timbers = [_beam(create_v3(mm(0), mm(0), mm(0))), _post(create_v3(mm(0), mm(0), mm(0)))]
        drawing = _selection(timbers, ["post#0"])

        for viewport in _orthographic_viewports(drawing):
            assert viewport["members"] == ["post#0"]
            assert viewport["ghostOthers"] is True

    def test_it_frames_only_the_selection_not_the_whole_frame(self):
        # The far timber must not drag the view out to include it.
        near = _post(create_v3(mm(0), mm(0), mm(0)))
        far = _post(create_v3(mm(20000), mm(0), mm(0)))
        drawing = _selection([near, far], ["post#0"])

        for viewport in _orthographic_viewports(drawing):
            assert viewport["camera"]["target"][0] < 1.0

    def test_an_unknown_member_key_is_ignored_rather_than_fatal(self):
        drawing = _selection([_post(create_v3(mm(0), mm(0), mm(0)))], ["post#0", "ghost#7"])

        assert [v["members"] for v in _orthographic_viewports(drawing)][0] == ["post#0"]

    def test_no_selection_draws_the_whole_frame(self):
        # Asking for a drawing before selecting anything gives something.
        drawing = _selection([_post(create_v3(mm(0), mm(0), mm(0)))], [])

        assert len(_orthographic_viewports(drawing)) == 3
        assert _orthographic_viewports(drawing)[0]["members"] is None

    def test_it_is_laid_out_on_a_sheet_with_a_free_preview(self):
        drawing = _selection([_post(create_v3(mm(0), mm(0), mm(0)))], ["post#0"])
        preview = drawing["viewports"][-1]

        assert drawing["page"]["width"] > 0
        assert preview["id"] == "preview"
        assert preview["locked"] is False
        assert preview["projection"] == "perspective"

    def test_a_drawing_shows_no_camera_gizmos(self):
        assert _selection([_post(create_v3(mm(0), mm(0), mm(0)))], ["post#0"])["cameraControls"] == []

    def test_it_frames_the_finished_piece_not_the_stock(self):
        # A timber with an end joint is not cut to length first, so centring a
        # view on its stock leaves the piece off centre by whatever the joint
        # took off. The assembly fixture's post is 1000mm of stock cut at 900.
        import importlib.util as _ilu

        spec = _ilu.spec_from_file_location(
            "assembly_fixture",
            Path(__file__).resolve().parent.parent / "kigumi" / "test-fixtures" / "assembly_frame.py",
        )
        module = _ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        frame = module.build_frame()

        drawing = runner.create_drawing_from_selection(frame, ["A#0"])

        # The post runs 0..900mm in z once cut, so the views centre on 450mm.
        for viewport in _orthographic_viewports(drawing):
            assert abs(viewport["camera"]["target"][2] - 0.45) < 1e-6


class TestPreviewCamera:
    """The 3D preview beside the elevations, and how far it may be turned."""

    def _preview(self, drawing):
        return next(v for v in drawing["viewports"] if v["id"] == "preview")

    def _off_axis_degrees(self, look, axis):
        import math

        dotted = abs(sum(look[i] * axis[i] for i in range(3)))
        return math.degrees(math.acos(min(1.0, dotted)))

    def test_it_does_not_look_down_the_length_of_the_piece(self):
        # An end-on view fills the viewport better than any other and shows
        # nothing at all, so "fit the most in" cannot mean fitting by area.
        beam = _beam(create_v3(mm(0), mm(0), mm(0)))
        preview = self._preview(_selection([beam], ["beam#0"]))

        assert self._off_axis_degrees(preview["camera"]["look"], [1.0, 0.0, 0.0]) > 25

    def test_it_looks_down_on_the_piece_rather_than_up_at_it(self):
        preview = self._preview(_selection([_beam(create_v3(mm(0), mm(0), mm(0)))], ["beam#0"]))

        assert preview["camera"]["look"][2] < 0

    def test_the_angle_follows_the_piece(self):
        # Two timbers lying along different world axes are not best seen from
        # the same place, so a fixed three-quarter view cannot be right for both.
        along_x = _beam(create_v3(mm(0), mm(0), mm(0)))
        along_y = create_timber(
            bottom_position=create_v3(mm(0), mm(0), mm(0)),
            length=mm(2400),
            size=create_v2(mm(100), mm(200)),
            length_direction=create_v3(0, 1, 0),
            width_direction=create_v3(1, 0, 0),
            ticket="beam",
        )

        looks = [
            tuple(self._preview(_selection([timber], ["beam#0"]))["camera"]["look"])
            for timber in (along_x, along_y)
        ]
        assert looks[0] != looks[1]

    def test_the_view_is_sized_to_the_angle_it_chose(self):
        # Framing on the bounding sphere instead ignores the angle entirely, so
        # choosing one would change nothing you could see.
        beam = _beam(create_v3(mm(0), mm(0), mm(0)))
        preview = self._preview(_selection([beam], ["beam#0"]))
        radius = ((1.2 ** 2) + (0.05 ** 2) + (0.1 ** 2)) ** 0.5

        assert preview["camera"]["extent"] < radius * 1.6

    def test_one_piece_turns_about_its_own_length(self):
        # Every side of the timber reachable, and no way to tumble it out of
        # the attitude it is drawn in.
        post = _post(create_v3(mm(0), mm(0), mm(0)))
        preview = self._preview(_selection([post], ["post#0"]))

        assert preview["orbit"]["mode"] == "axis"
        assert preview["orbit"]["axis"] == [0.0, 0.0, 1.0]

    def test_the_axis_is_the_timbers_own_not_the_worlds(self):
        beam = _beam(create_v3(mm(0), mm(0), mm(0)))
        preview = self._preview(_selection([beam], ["beam#0"]))

        assert preview["orbit"]["axis"] == [1.0, 0.0, 0.0]

    def test_several_pieces_orbit_freely(self):
        # No single length to turn about once there is more than one piece.
        timbers = [_beam(create_v3(mm(0), mm(0), mm(0))), _post(create_v3(mm(0), mm(0), mm(0)))]
        preview = self._preview(_selection(timbers, ["beam#0", "post#0"]))

        assert preview["orbit"]["mode"] == "free"

    def test_the_preview_is_still_free_to_be_moved(self):
        # The orbit is constrained, not the viewport: it is still a live view.
        preview = self._preview(_selection([_post(create_v3(mm(0), mm(0), mm(0)))], ["post#0"]))

        assert preview["locked"] is False
        assert preview["projection"] == "perspective"
