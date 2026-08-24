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

from kumiki.cutcsg import (
    ConvexPolygonExtrusion,
    CutCSG,
    Cylinder,
    Difference,
    HalfSpaceFeature,
    SimpleRectangularPrismFeature,
    PrismFace,
    RectangularPrism,
)
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.joints.workshop.mortise_and_tenon_joints import (
    cut_mortise_and_tenon_joint_on_face_aligned_timbers,
)
from kumiki.rule import Matrix, Transform, create_v3, inches, scalar
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
        """Faces of the timber body report an empty path and a reserved rough name.

        The rendered CSG is built from the timber's actual (as-sawn) body, so
        its faces are the ``rough.*`` set. The ``ptw.*`` set names the same six
        directions on the perfect-timber-within prism, which is a different
        solid -- keeping them distinct is what lets drawing generation tell a
        reference face from a rough one.
        """
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        found = _navigate_every_surface_point(
            cut_timber.render_timber_with_cuts_csg_local()
        )

        root_faces = {face for path, face in found if path == ()}
        assert root_faces >= {"rough.left", "rough.right", "rough.front", "rough.back"}
        assert not any(f.startswith("ptw.") for f in root_faces)

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


def _timber_prism(named=True):
    """A plain 4x6x100 timber body, optionally with its faces named."""
    return RectangularPrism(
        size=Matrix([scalar(4), scalar(6)]),
        transform=Transform.identity(),
        start_distance=scalar(0),
        end_distance=scalar(100),
        _features=[SimpleRectangularPrismFeature("rough.right", face=PrismFace.RIGHT)] if named else None,
    )


class TestNonPrismPrimitivesArePickable:
    """Extrusions, path extrusions and lofts used to be invisible to picking.

    kigumi carried its own float reimplementation of the point tests that only
    understood HalfSpace, RectangularPrism and Cylinder. Every other primitive
    failed the boundary test outright, so a click on (say) a dovetail cheek
    fell through to the timber body and came back labeled with a bare "face".
    The runner now calls kumiki's own CutCSG methods, which cover every
    primitive.
    """

    def test_extrusion_surface_is_on_the_boundary(self):
        """A point on a subtracted extrusion's wall registers as boundary."""
        extrusion = ConvexPolygonExtrusion(
            points=[
                Matrix([scalar(0), scalar(-1)]),
                Matrix([scalar(2), scalar(-1)]),
                Matrix([scalar(2), scalar(1)]),
                Matrix([scalar(0), scalar(1)]),
            ],
            transform=Transform.identity(),
            start_distance=scalar(10),
            end_distance=scalar(20),
            label="dovetail_housing",
        )
        # On the extrusion's x=2 wall, inside the timber body.
        point = [2.0, 0.0, 15.0]
        assert runner._csg_point_on_boundary(extrusion, point, PICK_EPS)

    def test_extrusion_cut_resolves_to_its_label_not_the_timber_body(self):
        csg = Difference(base=_timber_prism(), subtract=[
            ConvexPolygonExtrusion(
                points=[
                    Matrix([scalar(0), scalar(-1)]),
                    Matrix([scalar(2), scalar(-1)]),
                    Matrix([scalar(2), scalar(1)]),
                    Matrix([scalar(0), scalar(1)]),
                ],
                transform=Transform.identity(),
                start_distance=scalar(10),
                end_distance=scalar(20),
                label="dovetail_housing",
            ),
        ])
        path, target, _face = runner._navigate_csg_to_leaf(csg, [2.0, 0.0, 15.0], PICK_EPS)
        assert path == ["dovetail_housing"]
        assert isinstance(target, ConvexPolygonExtrusion)

    def test_cylinder_cut_resolves_to_its_label(self):
        csg = Difference(base=_timber_prism(), subtract=[
            Cylinder(
                axis_direction=create_v3(scalar(0), scalar(1), scalar(0)),
                radius=scalar(1),
                position=create_v3(scalar(0), scalar(-5), scalar(50)),
                start_distance=scalar(0),
                end_distance=scalar(10),
                label="peg_hole",
            ),
        ])
        # On the bore wall, one radius off the axis.
        path, target, face = runner._navigate_csg_to_leaf(csg, [1.0, 0.0, 50.0], PICK_EPS)
        assert path == ["peg_hole"]
        assert isinstance(target, Cylinder)
        assert face == "cylindrical_surface"


class TestDetectFaceLabel:
    def test_prefers_a_declared_named_feature(self):
        """A declared name beats the geometric guess.

        A prism built in its own local frame has a "top" that need not be the
        timber's top, so a name the author gave always wins.
        """
        prism = RectangularPrism(
            size=Matrix([scalar(4), scalar(6)]),
            transform=Transform.identity(),
            start_distance=scalar(0),
            end_distance=scalar(100),
            _features=[SimpleRectangularPrismFeature("tenon_right", face=PrismFace.RIGHT)],
        )
        assert runner._detect_face_label(prism, [2.0, 0.0, 50.0], PICK_EPS) == "tenon_right"

    def test_falls_back_to_the_timber_local_direction(self):
        """An unnamed face is named by which timber face it points along."""
        prism = _timber_prism(named=False)
        assert runner._detect_face_label(prism, [2.0, 0.0, 50.0], PICK_EPS) == "right"
        assert runner._detect_face_label(prism, [-2.0, 0.0, 50.0], PICK_EPS) == "left"
        assert runner._detect_face_label(prism, [0.0, 3.0, 50.0], PICK_EPS) == "front"
        assert runner._detect_face_label(prism, [0.0, 0.0, 100.0], PICK_EPS) == "top"

    def test_half_space_reports_a_cut_plane(self):
        from kumiki.cutcsg import HalfSpace

        plane = HalfSpace(
            normal=create_v3(scalar(0), scalar(0), scalar(1)), offset=scalar(50)
        )
        assert runner._detect_face_label(plane, [0.0, 0.0, 50.0], PICK_EPS) == "cut_plane"

    def test_half_space_named_feature_wins_over_cut_plane(self):
        from kumiki.cutcsg import HalfSpace

        plane = HalfSpace(
            normal=create_v3(scalar(0), scalar(0), scalar(1)),
            offset=scalar(50),
            _features=[HalfSpaceFeature("shoulder")],
        )
        assert runner._detect_face_label(plane, [0.0, 0.0, 50.0], PICK_EPS) == "shoulder"


class TestPickingToleranceIsPerCall:
    def test_widened_picking_does_not_affect_a_later_default_query(
        self, mortise_and_tenon_frame
    ):
        """Picking passes a wide eps; that must not leak into anything else."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        csg = cut_timber.render_timber_with_cuts_csg_local()

        # A point 1e-4 off the timber's bottom face: inside the pick tolerance,
        # outside the default one.
        near_miss = create_v3(scalar(0), scalar(0), scalar(-1e-4))
        assert csg.is_point_on_boundary(near_miss, PICK_EPS)

        runner._navigate_csg_to_leaf(csg, [0.0, 0.0, 0.0], PICK_EPS)

        assert not csg.is_point_on_boundary(near_miss)


class TestJointAttribution:
    """Which joint produced a piece of geometry.

    Derived, never stored. A Joint already owns its cuttings, so the reverse
    link is read from that rather than duplicated onto Cutting or CutCSG --
    a second copy would need keeping in sync (with_order() rebuilds cuttings
    via replace(), so it genuinely can drift), and putting a joint ticket on
    CutCSG would make a pure geometry module carry a construction concept.
    """

    @pytest.fixture
    def named_joint_frame(self):
        """The mortise-and-tenon, with a joint ticket worth reading back."""
        from dataclasses import replace

        from kumiki.ticket import JointTicket

        arrangement = create_canonical_example_butt_joint_timbers(create_v3(0, 0, 0))
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=inches(3),
            tenon_height_relative_to_joint=inches(1),
            tenon_length=inches(3),
            mortise_depth=inches(7, 2),
        )
        joint = replace(joint, ticket=JointTicket(path="joints/corner_a",
                                                  joint_type="mortise_and_tenon"))
        return Frame.from_joints([joint])

    def _leaf_at(self, csg, point):
        _path, target, label = runner._navigate_csg_to_leaf(csg, point, PICK_EPS)
        return target, label

    def test_joint_geometry_reports_its_joint(self, named_joint_frame):
        cut_timber = _cut_timber_by_name(named_joint_frame, "butt_timber")
        csg = cut_timber.render_timber_with_cuts_csg_local()

        tenon_point = None
        for triangle in triangulate_cutcsg(csg).mesh.triangles:
            centroid = [
                (triangle[0][i] + triangle[1][i] + triangle[2][i]) / 3.0 for i in range(3)
            ]
            _target, label = self._leaf_at(csg, centroid)
            if label.startswith("tenon"):
                tenon_point = centroid
                break
        assert tenon_point is not None, "no tenon face found to click on"

        target, _label = self._leaf_at(csg, tenon_point)
        assert runner._joint_name_for_node(csg, cut_timber, target) == "corner_a"

    def test_the_timber_body_belongs_to_no_joint(self, named_joint_frame):
        """A rough face is the timber itself, not something a joint cut."""
        cut_timber = _cut_timber_by_name(named_joint_frame, "butt_timber")
        csg = cut_timber.render_timber_with_cuts_csg_local()
        half_width = float(cut_timber.timber.size[0]) / 2

        target, label = self._leaf_at(csg, [half_width, 0.0, 0.3])
        assert label.startswith("rough.")
        assert runner._joint_name_for_node(csg, cut_timber, target) is None

    def test_a_hand_built_cut_timber_declines_rather_than_guesses(self):
        """Attribution comes from CutTimber.joints, which a hand-built one lacks."""
        from kumiki.timber import CutTimber

        arrangement = create_canonical_example_butt_joint_timbers(create_v3(0, 0, 0))
        joint = cut_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_width_relative_to_joint=inches(3),
            tenon_height_relative_to_joint=inches(1),
            tenon_length=inches(3),
            mortise_depth=inches(7, 2),
        )
        jointed = _cut_timber_by_name(Frame.from_joints([joint]), "butt_timber")
        by_hand = CutTimber(jointed.timber, cuts=list(jointed.cuts))

        assert by_hand.joints == []
        assert runner._joint_by_cutting_id(by_hand) == {}

        csg = by_hand.render_timber_with_cuts_csg_local()
        target, _ = self._leaf_at(csg, [0.0, 0.0, 0.0])
        assert runner._joint_name_for_node(csg, by_hand, target) is None

    def test_attribution_does_not_depend_on_the_frame(self, named_joint_frame):
        """A cut timber can name its joints on its own, with no frame in hand."""
        cut_timber = _cut_timber_by_name(named_joint_frame, "butt_timber")
        assert [j.ticket.get_name() for j in cut_timber.joints] == ["corner_a"]

    def test_nothing_is_stored_on_the_cutting_or_the_csg(self):
        """The link stays derived -- guard against reintroducing a stored copy."""
        from kumiki.cutcsg import CutCSG
        from kumiki.timber import Cutting

        assert "joint_ticket" not in Cutting.__dataclass_fields__
        assert "joint_ticket" not in CutCSG.__dataclass_fields__
