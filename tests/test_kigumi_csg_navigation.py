"""
Tests for kigumi's CSG tree navigation (kigumi/runner.py).

These cover the runner's point-based CSG picking: given a point on a cut
timber's surface, it walks the CSG tree and reports which labeled node and
which named face the point belongs to.

Regression context: kigumi navigated the tree by reading ``csg.tag``, but
kumiki renamed that field to ``csg.label``. Because the reads went through
``getattr(csg, "tag", None)`` the breakage was silent -- every path came back
empty, ctrl+click drilling became a no-op, and the CSG tree panel collected
nothing. ``test_cutcsg_label_field_is_named_label`` exists so the next such
rename fails loudly here instead.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from kumiki.cutcsg import CutCSG
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.joints.workshop.mortise_and_tenon_joints import (
    cut_mortise_and_tenon_joint_on_face_aligned_timbers,
)
from kumiki.rule import create_v3, inches
from kumiki.timber import Frame
from kumiki.triangles import triangulate_cutcsg

# Generous epsilon: mesh vertices come out of a boolean op, so surface points
# are only approximately on the analytic primitives. Matches the runner's own
# raycast epsilon.
PICK_EPS = 5e-4


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


@pytest.fixture(scope="module")
def mortise_and_tenon_frame():
    """A basic blind mortise and tenon on canonical 4x5x4' butt joint timbers."""
    arrangement = create_canonical_example_butt_joint_timbers(create_v3(0, 0, 0))
    joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
        arrangement=arrangement,
        tenon_width_relative_to_joint=inches(3),
        tenon_height_relative_to_joint=inches(1),
        tenon_length=inches(3),
        mortise_depth=inches(7, 2),
    )
    return Frame.from_joints([joint])


def _cut_timber_by_name(frame, name):
    for cut_timber in frame.cut_timbers:
        if cut_timber.timber.ticket.path == name:
            return cut_timber
    raise AssertionError(f"no cut timber named {name!r} in frame")


def _navigate_every_surface_point(csg):
    """Run the runner's picker over every triangle centroid of *csg*.

    Returns {(path_tuple, face_label): triangle_count}.
    """
    found: dict = {}
    for triangle in triangulate_cutcsg(csg).mesh.triangles:
        centroid = [
            (triangle[0][i] + triangle[1][i] + triangle[2][i]) / 3.0 for i in range(3)
        ]
        path, _target, face_label = runner._navigate_csg_to_leaf(csg, centroid, PICK_EPS)
        found[(tuple(path), face_label)] = found.get((tuple(path), face_label), 0) + 1
    return found


def test_cutcsg_label_field_is_named_label():
    """kigumi navigates by CutCSG.label; fail loudly if that field is renamed.

    kigumi reads this attribute defensively (getattr with a default), so a
    rename here does not raise -- it silently degrades every CSG selection.
    """
    field_names = set(CutCSG.__dataclass_fields__)
    assert "label" in field_names, (
        "CutCSG no longer has a 'label' field. kigumi/runner.py navigates the "
        "CSG tree by reading it (_walk_labeled_csg, _resolve_csg_at_path, "
        "_navigate_csg_one_level); update those reads to match."
    )


class TestWalkLabeledCSG:
    def test_collects_labeled_nodes_with_paths(self, mortise_and_tenon_frame):
        """The tenon timber's tree exposes its joint, shoulder and tenon nodes."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        collected = []
        runner._walk_labeled_csg(
            cut_timber.render_timber_with_cuts_csg_local(), [], collected
        )

        by_label = {node["label"]: node for node in collected}
        assert "mortise_and_tenon" in by_label
        assert "tenon" in by_label
        assert by_label["mortise_and_tenon"]["path"] == ["mortise_and_tenon"]
        assert by_label["tenon"]["path"] == ["mortise_and_tenon", "tenon"]

    def test_reports_named_features_of_labeled_nodes(self, mortise_and_tenon_frame):
        """The tenon prism's named faces come through on its tree node."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        collected = []
        runner._walk_labeled_csg(
            cut_timber.render_timber_with_cuts_csg_local(), [], collected
        )

        tenon = next(node for node in collected if node["label"] == "tenon")
        assert set(tenon["features"]) >= {
            "tenon_right",
            "tenon_left",
            "tenon_front",
            "tenon_back",
        }

    def test_mortise_hole_is_reachable_on_receiving_timber(
        self, mortise_and_tenon_frame
    ):
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "receiving_timber")
        collected = []
        runner._walk_labeled_csg(
            cut_timber.render_timber_with_cuts_csg_local(), [], collected
        )

        paths = [node["path"] for node in collected]
        assert ["mortise_and_tenon", "mortise_hole"] in paths


class TestNavigateToLeaf:
    def test_tenon_faces_resolve_to_a_labeled_path(self, mortise_and_tenon_frame):
        """Points on the tenon report the tenon's path, not an empty one.

        This is the direct regression: with the tag/label mismatch every point
        returned path == [] because no child ever appeared to carry a label.
        """
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        found = _navigate_every_surface_point(
            cut_timber.render_timber_with_cuts_csg_local()
        )

        tenon_hits = {
            (path, face): count
            for (path, face), count in found.items()
            if path == ("mortise_and_tenon", "tenon")
        }
        assert tenon_hits, (
            "no surface point resolved to the tenon; paths found were "
            f"{sorted({path for path, _ in found})}"
        )
        assert {face for _, face in tenon_hits} >= {"tenon_top", "tenon_front"}

    def test_uncut_timber_faces_stay_at_the_root(self, mortise_and_tenon_frame):
        """Faces of the timber body itself report an empty path and a face name."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        found = _navigate_every_surface_point(
            cut_timber.render_timber_with_cuts_csg_local()
        )

        root_faces = {face for path, face in found if path == ()}
        assert root_faces >= {"left", "right", "front", "back"}

    def test_mortise_hole_faces_resolve_to_a_labeled_path(
        self, mortise_and_tenon_frame
    ):
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "receiving_timber")
        found = _navigate_every_surface_point(
            cut_timber.render_timber_with_cuts_csg_local()
        )

        assert any(
            path == ("mortise_and_tenon", "mortise_hole") for path, _ in found
        ), f"paths found were {sorted({path for path, _ in found})}"


class TestResolveCSGAtPath:
    def test_round_trips_a_path_produced_by_navigation(self, mortise_and_tenon_frame):
        """A path from _navigate_csg_to_leaf resolves back to a real node."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        local_csg = cut_timber.render_timber_with_cuts_csg_local()

        resolved = runner._resolve_csg_at_path(
            local_csg, ["mortise_and_tenon", "tenon"], None, PICK_EPS
        )
        assert resolved is not local_csg
        assert getattr(resolved, "label", None) == "tenon"


class TestSerializeCuttingSummary:
    def test_uses_the_cutting_label_as_display_name(self, mortise_and_tenon_frame):
        """Cuttings show their authored label rather than a generic 'cut N'."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        cuts_meta = runner._serialize_cutting_summary(cut_timber)

        assert cuts_meta, "expected at least one cutting on the tenon timber"
        assert cuts_meta[0]["label"] == "mortise_and_tenon"
        assert cuts_meta[0]["displayName"] == "mortise_and_tenon"
