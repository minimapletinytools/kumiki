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
    EmptyCSG,
    CutCSG,
    CutCSGLabel,
    Cylinder,
    Difference,
    HalfSpace,
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

# Where the tenon sits in a mortise-and-tenon tree: the joint's node, the waste
# removed around the tenon, then the tenon prism subtracted back out of it.
# The joint segment carries its occurrence, which is what tells two identical
# joints on one timber apart. One joint here, so #0.
TENON_PATH = ["mortise_and_tenon#0", "tenon_waste", "tenon"]


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


def test_cutcsg_label_name_is_reachable_as_name():
    """The name lives at ``csg.label.name``, and kigumi reads it through a
    getattr chain -- so renaming it degrades silently too, exactly like
    renaming the field itself."""
    labeled = HalfSpace(normal=create_v3(0, 0, 1), label=CutCSGLabel("shoulder"))
    assert labeled.label.name == "shoulder"
    assert runner._label_name(labeled) == "shoulder"


def test_an_unlabeled_csg_reports_no_name():
    """NoLabel() is not None, so a naive truth test on csg.label would call
    every node labelled. kigumi must see None here."""
    unlabeled = HalfSpace(normal=create_v3(0, 0, 1))
    assert unlabeled.label == CutCSGLabel.NoLabel()
    assert runner._label_name(unlabeled) is None


class TestCSGTreeSerialization:
    """The CSG tree the viewer renders for debugging.

    It serializes the timber's *rendered* CSG -- the tree picking actually runs
    against -- rather than one cutting's negative CSG, and it keeps every node
    including untagged intermediates, since the shape of the tree is exactly
    what you need to see when the shape is what has gone wrong.
    """

    def _tree(self, frame, name):
        return runner.serialize_cut_csg_tree(_cut_timber_by_name(frame, name))["tree"]

    def _walk(self, node):
        yield node
        for child in node["children"]:
            yield from self._walk(child)

    def _by_label(self, node):
        return {n["label"]: n for n in self._walk(node) if n["label"]}

    def test_the_root_is_the_rendered_difference(self, mortise_and_tenon_frame):
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        assert tree["kind"] == "Difference"
        assert tree["role"] is None
        roles = [child["role"] for child in tree["children"]]
        assert roles[0] == "base" and set(roles[1:]) == {"subtract"}

    def test_untagged_intermediates_are_kept(self, mortise_and_tenon_frame):
        """The old walker collected only labelled nodes, hiding the shape."""
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        assert any(node["label"] is None for node in self._walk(tree))

    def test_labelled_nodes_carry_their_navigable_path(self, mortise_and_tenon_frame):
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        labelled = self._by_label(tree)
        # The label people read stays bare; only the path is numbered.
        assert labelled["mortise_and_tenon"]["path"] == ["mortise_and_tenon#0"]
        assert labelled["tenon_waste"]["path"] == ["mortise_and_tenon#0", "tenon_waste"]
        assert labelled["tenon"]["path"] == TENON_PATH

    def test_features_carry_their_metadata(self, mortise_and_tenon_frame):
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        tenon = self._by_label(tree)["tenon"]
        by_name = {f["name"]: f for f in tenon["features"]}
        assert {"tenon_right", "tenon_left", "tenon_front", "tenon_back"} <= set(by_name)
        assert by_name["tenon_right"]["type"] == "FACE"
        assert by_name["tenon_right"]["real"] is True
        assert by_name["tenon_right"]["group"] == "A"

    def test_the_timber_body_carries_its_reserved_face_names(self, mortise_and_tenon_frame):
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        base = tree["children"][0]
        names = {f["name"] for f in base["features"]}
        assert {"rough.right", "rough.left", "rough.top"} <= names
        assert all(f["group"] == "B2" for f in base["features"])

    def test_joint_attribution_flows_down_the_cut(self, mortise_and_tenon_frame):
        """The body belongs to no joint; everything under a cut belongs to one."""
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        assert tree["children"][0]["jointName"] is None  # the timber body
        cut = tree["children"][1]
        assert cut["jointName"] is not None
        assert all(node["jointName"] == cut["jointName"] for node in self._walk(cut))

    def test_cut_index_and_joint_id_flow_down_the_cut(self, mortise_and_tenon_frame):
        """The viewer joins the joint list against these, so they travel with
        jointName rather than being re-derived per node."""
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")

        body = tree["children"][0]
        assert body["cutIndex"] is None and body["jointId"] is None

        cuts = [child for child in tree["children"] if child["role"] == "subtract"]
        for expected_index, cut in enumerate(cuts):
            assert cut["cutIndex"] == expected_index
            assert cut["jointId"] is not None
            # A joint id is only useful if it matches the one the layers
            # payload publishes for the same joint.
            assert all(
                node["cutIndex"] == expected_index and node["jointId"] == cut["jointId"]
                for node in self._walk(cut)
            )

    def test_joint_ids_match_the_layers_payload(self, mortise_and_tenon_frame):
        layers = runner.serialize_layers(mortise_and_tenon_frame)
        published = {str(joint["kumikiEphemeralId"]) for joint in layers["joints"]}
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        from_tree = {
            node["jointId"] for node in self._walk(tree) if node["jointId"] is not None
        }
        assert from_tree and from_tree <= published

    def test_a_cut_without_a_joint_still_gets_an_index(self, mortise_and_tenon_frame):
        """Attribution degrades one field at a time: a hand-built CutTimber has
        no joints to name, but its cuts are still indexable."""
        from kumiki.timber import CutTimber

        jointed = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        by_hand = CutTimber(jointed.timber, cuts=list(jointed.cuts))

        tree = runner.serialize_cut_csg_tree(by_hand)["tree"]
        cuts = [child for child in tree["children"] if child["role"] == "subtract"]
        assert cuts, "the hand-built timber should still have its cuts"
        for expected_index, cut in enumerate(cuts):
            assert cut["cutIndex"] == expected_index
            assert cut["jointId"] is None and cut["jointName"] is None

    def test_the_mortise_shows_up_on_the_receiving_timber(self, mortise_and_tenon_frame):
        tree = self._tree(mortise_and_tenon_frame, "receiving_timber")
        assert "mortise_hole" in self._by_label(tree)


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
            if path == tuple(TENON_PATH)
        }
        assert tenon_hits, (
            "no surface point resolved to the tenon; paths found were "
            f"{sorted({path for path, _ in found})}"
        )
        assert {face for _, face in tenon_hits} >= {"tenon_top", "tenon_front"}

    def test_uncut_timber_faces_resolve_to_the_body(self, mortise_and_tenon_frame):
        """Faces of the timber body report the body's path and a rough name.

        The body names itself after the timber type it came from, so a pick on
        it resolves there rather than to an empty path -- which is what makes
        the body addressable in the tree alongside the cuts.

        The rendered CSG is built from the timber's actual (as-sawn) body, so
        its faces are the ``rough.*`` set. The ``ptw.*`` set names the same six
        directions on the perfect-timber-within prism, which is a different
        solid -- keeping them distinct is what lets drawing generation tell a
        reference face from a rough one.
        """
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        body_path = (type(cut_timber.timber).csg_label("rough", "extended").name,)
        assert body_path == ("timber (rough, extended)",)

        found = _navigate_every_surface_point(
            cut_timber.render_timber_with_cuts_csg_local()
        )

        body_faces = {face for path, face in found if path == body_path}
        assert body_faces >= {"rough.left", "rough.right", "rough.front", "rough.back"}
        assert not any(f.startswith("ptw.") for f in body_faces)

    def test_mortise_hole_faces_resolve_to_a_labeled_path(
        self, mortise_and_tenon_frame
    ):
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "receiving_timber")
        found = _navigate_every_surface_point(
            cut_timber.render_timber_with_cuts_csg_local()
        )

        assert any(
            path == ("mortise_and_tenon#0", "mortise_hole") for path, _ in found
        ), f"paths found were {sorted({path for path, _ in found})}"


class TestResolveCSGAtPath:
    def test_round_trips_a_path_produced_by_navigation(self, mortise_and_tenon_frame):
        """A path from _navigate_csg_to_leaf resolves back to a real node."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        local_csg = cut_timber.render_timber_with_cuts_csg_local()

        resolved = runner._resolve_csg_at_path(
            local_csg, TENON_PATH, None, PICK_EPS
        )
        assert resolved is not local_csg
        assert resolved.label.name == "tenon"


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
            label=CutCSGLabel("dovetail_housing"),
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
                label=CutCSGLabel("dovetail_housing"),
            ),
        ])
        path, target, _face = runner._navigate_csg_to_leaf(csg, [2.0, 0.0, 15.0], PICK_EPS)
        assert path == ["dovetail_housing#0"]
        assert isinstance(target, ConvexPolygonExtrusion)

    def test_cylinder_cut_resolves_to_its_label(self):
        csg = Difference(base=_timber_prism(), subtract=[
            Cylinder(
                axis_direction=create_v3(scalar(0), scalar(1), scalar(0)),
                radius=scalar(1),
                position=create_v3(scalar(0), scalar(-5), scalar(50)),
                start_distance=scalar(0),
                end_distance=scalar(10),
                label=CutCSGLabel("peg_hole"),
            ),
        ])
        # On the bore wall, one radius off the axis.
        path, target, face = runner._navigate_csg_to_leaf(csg, [1.0, 0.0, 50.0], PICK_EPS)
        assert path == ["peg_hole#0"]
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


class TestEdgePicking:
    """Clicking a derived edge.

    An edge comes from a face on each of two primitives, so it exists only
    where both are in scope. Navigation lands on one leaf, and a leaf can never
    see the pair -- which is why edges were unselectable while derivation
    itself worked. The pick asks the root for them instead.
    """

    def _slot(self, frame, name):
        import types

        cut_timber = _cut_timber_by_name(frame, name)
        local_csg = cut_timber.render_timber_with_cuts_csg_local()
        mesh = runner._cut_timber_to_triangle_mesh_payload(cut_timber, local_csg, "m#0")
        slot = types.SimpleNamespace(mesh_cache={"m#0": {
            "mesh": mesh, "local_csg": local_csg, "cut_timber": cut_timber,
        }})
        return slot, cut_timber, local_csg

    def _to_global(self, cut_timber, local_point):
        transform = cut_timber.timber.transform
        moved = transform.position + transform.orientation.matrix * runner._to_v3(local_point)
        return [float(coordinate) for coordinate in moved]

    def _point_where(self, local_csg, predicate):
        """A surface point the whole tree resolves to a feature matching *predicate*."""
        from kumiki.cutcsg import CSGFeatureType

        for triangle in triangulate_cutcsg(local_csg).mesh.triangles:
            candidates = [
                [(triangle[a][i] + triangle[b][i]) / 2 for i in range(3)]
                for a, b in ((0, 1), (1, 2), (2, 0))
            ]
            candidates.append([sum(v[i] for v in triangle) / 3 for i in range(3)])
            for point in candidates:
                hit = local_csg.find_feature(runner._to_v3(point))
                if hit is not None and predicate(hit.feature):
                    return point
        raise AssertionError("no matching point found")

    def _pick(self, slot, cut_timber, point, ctrl_click=False, path=None):
        return runner._handle_find_csg_at_point(None, {
            "memberKey": "m#0",
            "point": self._to_global(cut_timber, point),
            "currentPath": path or [],
            "ctrlClick": ctrl_click,
        }, slot)

    def test_a_click_on_the_shoulder_line_selects_the_edge(self, mortise_and_tenon_frame):
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        result = self._pick(slot, cut_timber, point)
        assert result["featureType"] == "EDGE"
        assert "shoulder" in result["featureLabel"]
        assert "\u00d7" in result["featureLabel"]   # the name of a pair

    def test_the_edge_comes_back_as_a_line_to_draw(self, mortise_and_tenon_frame):
        """The viewer draws a selected edge rather than shading triangles beside
        it, so the pick returns the span the line should cover."""
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        result = self._pick(slot, cut_timber, point)
        segment = result["highlightEdge"]
        assert len(segment["start"]) == 3 and len(segment["end"]) == 3
        assert segment["start"] != segment["end"]

    def test_the_clicked_point_lies_on_the_drawn_line(self, mortise_and_tenon_frame):
        """A line somewhere else on the timber would look like a stray mark."""
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))
        clicked = self._to_global(cut_timber, point)

        segment = self._pick(slot, cut_timber, point)["highlightEdge"]
        start, end = segment["start"], segment["end"]
        span = [end[i] - start[i] for i in range(3)]
        length_sq = sum(component * component for component in span)
        # Distance from the clicked point to the segment's line.
        offset = [clicked[i] - start[i] for i in range(3)]
        along = sum(offset[i] * span[i] for i in range(3)) / length_sq
        closest = [start[i] + span[i] * along for i in range(3)]
        distance_sq = sum((clicked[i] - closest[i]) ** 2 for i in range(3))
        assert distance_sq < (2e-3) ** 2
        assert -0.001 <= along <= 1.001   # and within the span, not off its end

    def test_an_edge_pick_does_not_shade_triangles(self, mortise_and_tenon_frame):
        """The strip beside the edge was what read as a stray wedge; the line
        replaces it rather than joining it."""
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        result = self._pick(slot, cut_timber, point)
        assert result["stats"]["trianglesMatched"] == 0

    def test_a_face_pick_draws_no_line(self, mortise_and_tenon_frame):
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.FACE and f.name == "shoulder"))

        result = self._pick(slot, cut_timber, point)
        assert "highlightEdge" not in result
        assert result["stats"]["trianglesMatched"] > 0

    def test_the_edge_shows_up_as_something(self, mortise_and_tenon_frame):
        """A selection that shows nothing looks exactly like a click that did
        not land, which is how this looked before: the feature resolved and the
        mesh filter then matched no triangle at all, because no triangle's
        centroid sits on a line. A line is the answer, with the triangle strip
        left as the fallback when no span can be measured."""
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        result = self._pick(slot, cut_timber, point)
        assert result.get("highlightEdge") or result["stats"]["trianglesMatched"] > 0

    def test_the_middle_of_a_face_still_selects_the_face(self, mortise_and_tenon_frame):
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.FACE and f.name == "shoulder"))

        result = self._pick(slot, cut_timber, point)
        assert result["featureType"] == "FACE"
        assert result["featureLabel"] == "shoulder"

    def test_the_edge_is_shown_under_the_deeper_of_its_two_parents(self, mortise_and_tenon_frame):
        """The shoulder sits inside the joint; the timber body is a child of
        the root. The rule puts the edge with the shoulder."""
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        result = self._pick(slot, cut_timber, point)
        assert result["path"][-1] == "shoulder"
        assert result["nodeLabel"] == "shoulder"

    def test_ctrl_holds_the_click_to_one_level(self, mortise_and_tenon_frame):
        """Ctrl is the way down through the compounds, which are selectable in
        their own right -- so the first one stops above the edge."""
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        first = self._pick(slot, cut_timber, point, ctrl_click=True)
        assert first["featureLabel"] is None
        assert first["path"] == ["mortise_and_tenon"]

    def test_ctrl_clicking_down_reaches_the_edge_once_it_is_deep_enough(self, mortise_and_tenon_frame):
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        path: list = []
        for _step in range(6):
            result = self._pick(slot, cut_timber, point, ctrl_click=True, path=path)
            if result["featureType"] == "EDGE":
                return
            path = result["path"]
        raise AssertionError("ctrl-clicking down never reached the edge")

    def test_a_plain_click_needs_no_drilling(self, mortise_and_tenon_frame):
        """The whole point of the swap: one click on the line selects it."""
        from kumiki.cutcsg import CSGFeatureType

        slot, cut_timber, local_csg = self._slot(mortise_and_tenon_frame, "butt_timber")
        point = self._point_where(local_csg, lambda f: (
            f.feature_type() == CSGFeatureType.EDGE and "shoulder" in f.name))

        result = self._pick(slot, cut_timber, point, ctrl_click=False)
        assert result["featureType"] == "EDGE"


class TestPickDescription:
    """What the selection display gets from one click.

    featureLabel / featureType / jointName / facesToward, computed once per
    pick -- unlike _detect_face_label, which runs per triangle during highlight
    extraction and stays a cheap string lookup.
    """

    def _describe(self, frame, name, point):
        cut_timber = _cut_timber_by_name(frame, name)
        csg = cut_timber.render_timber_with_cuts_csg_local()
        _path, target, label = runner._navigate_csg_to_leaf(csg, point, PICK_EPS)
        return runner._describe_pick(target, csg, cut_timber, point, PICK_EPS, label)

    def _point_on(self, frame, name, predicate):
        """A surface point whose feature label satisfies *predicate*."""
        cut_timber = _cut_timber_by_name(frame, name)
        csg = cut_timber.render_timber_with_cuts_csg_local()
        for triangle in triangulate_cutcsg(csg).mesh.triangles:
            centroid = [
                (triangle[0][i] + triangle[1][i] + triangle[2][i]) / 3.0 for i in range(3)
            ]
            _p, _t, label = runner._navigate_csg_to_leaf(csg, centroid, PICK_EPS)
            if predicate(label):
                return centroid
        raise AssertionError("no matching surface point found")

    def test_a_whole_node_names_itself_rather_than_a_face_inside_it(
        self, mortise_and_tenon_frame,
    ):
        """An ordinary click descends one level at a time, so it selects
        compounds on the way down. Those must not report a feature: the
        highlight lights the whole node, and naming a descendant's face made
        the display contradict it."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        csg = cut_timber.render_timber_with_cuts_csg_local()
        point = self._point_on(mortise_and_tenon_frame, "butt_timber",
                               lambda label: label is not None and label.startswith("tenon_"))

        # What the first click on that point selects.
        path, target, label = runner._navigate_csg_one_level(csg, point, [], PICK_EPS)
        assert path == ["mortise_and_tenon"] and label is None
        described = runner._describe_pick(target, csg, cut_timber, point, PICK_EPS, label)

        assert described["featureLabel"] is None
        assert described["featureType"] is None
        assert described["facesToward"] is None
        # It says what it is instead.
        assert described["nodeKind"] == "SolidUnion"
        assert described["nodeDisplayName"] == "union"
        assert described["nodeLabel"] == "mortise_and_tenon"

    def test_a_node_identifies_itself_even_when_a_feature_is_selected(
        self, mortise_and_tenon_frame,
    ):
        point = self._point_on(mortise_and_tenon_frame, "butt_timber",
                               lambda label: label == "rough.right")
        described = self._describe(mortise_and_tenon_frame, "butt_timber", point)
        assert described["nodeKind"] == "RectangularPrism"
        assert described["nodeLabel"] == "timber (rough, extended)"

    def test_a_timber_face_describes_itself(self, mortise_and_tenon_frame):
        point = self._point_on(mortise_and_tenon_frame, "butt_timber",
                               lambda label: label == "rough.right")
        described = self._describe(mortise_and_tenon_frame, "butt_timber", point)
        assert described["featureLabel"] == "rough.right"
        assert described["featureType"] == "FACE"
        assert described["jointName"] is None
        assert described["facesToward"] == "right"

    def test_a_tenon_cheek_faces_the_way_the_tenon_does(self, mortise_and_tenon_frame):
        """A tenon is inside a cutting but is not a hole.

        The cut is ``body - Union(Difference(shoulder, tenon), ...)``, so the
        tenon prism is subtracted from something that is itself subtracted, and
        ends up net additive: its cheeks face the way the prism does. Any rule
        along the lines of "inside a cutting means flip" reports every cheek as
        the opposite face of the timber.
        """
        point = self._point_on(mortise_and_tenon_frame, "butt_timber",
                               lambda label: label == "tenon_right")
        described = self._describe(mortise_and_tenon_frame, "butt_timber", point)
        assert described["featureLabel"] == "tenon_right"
        assert described["jointName"] is not None
        assert described["facesToward"] == "right"

    def test_a_mortise_wall_faces_into_the_timber(self, mortise_and_tenon_frame):
        """A hole's wall faces the opposite way to the prism that cut it.

        The mortise prism's own outward normal points out of the hole and into
        the material; the surface someone clicked is the wall of the hole. The
        composed solid is what settles the sign.
        """
        # The mortise declares its walls now, so a pick reports the declared
        # mortise_back rather than the geometric guess "back" it fell back to
        # before. Those names are not interchangeable -- a declared name is in
        # the prism's own frame and the guess is in the timber's -- so the sign
        # is asserted against the geometry rather than a fixed direction.
        from kumiki.rule import safe_dot_product

        point = self._point_on(mortise_and_tenon_frame, "receiving_timber",
                               lambda label: label == "mortise_back")
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "receiving_timber")
        csg = cut_timber.render_timber_with_cuts_csg_local()
        _path, target, _label = runner._navigate_csg_to_leaf(csg, point, PICK_EPS)

        prism_normal = target.get_outward_normal(runner._to_v3(point), PICK_EPS)
        composed_normal = csg.get_outward_normal(runner._to_v3(point), PICK_EPS)
        # The prism's own normal points out of the hole and into the material;
        # the wall someone clicked faces the other way.
        assert safe_dot_product(prism_normal, composed_normal) < 0

        described = self._describe(mortise_and_tenon_frame, "receiving_timber", point)
        assert described["facesToward"] == runner._nearest_timber_local_face_name(composed_normal)

    def test_it_agrees_with_the_composed_solid_everywhere(self, mortise_and_tenon_frame):
        """The reported direction always matches the finished timber's own normal.

        This is the property the whole thing rests on, so it is checked over
        every surface point rather than a few chosen ones.

        Two independent routes to the same answer, which is the point: the code
        under test signs the leaf's normal by its structural parity and never
        looks at the composed solid, while this asks the composed solid
        directly. They agree here because the parity rule is right, not because
        one is derived from the other.
        """
        from kumiki.rule import safe_dot_product

        for name in ("butt_timber", "receiving_timber"):
            cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, name)
            csg = cut_timber.render_timber_with_cuts_csg_local()
            for triangle in triangulate_cutcsg(csg).mesh.triangles:
                centroid = [
                    (triangle[0][i] + triangle[1][i] + triangle[2][i]) / 3.0
                    for i in range(3)
                ]
                composed = csg.get_outward_normal(runner._to_v3(centroid), PICK_EPS)
                if composed is None:
                    continue
                expected = runner._nearest_timber_local_face_name(composed)
                _p, target, _l = runner._navigate_csg_to_leaf(csg, centroid, PICK_EPS)
                normal, faces_toward = runner._outward_normal_and_face(
                    target, csg, centroid, PICK_EPS)
                assert faces_toward == expected
                # The exact normal is reported alongside the nearest-of-six
                # name, so the display can show both rather than rounding
                # silently.
                assert normal is not None and len(normal) == 3
                assert runner._nearest_timber_local_face_name(normal) == expected


class TestSerializedParity:
    """Every node in the payload says whether it adds material or removes it.

    role says which edge a node sits on; parity says what that means for the
    finished solid, and they differ -- two subtract edges cancel.
    """

    def _tree(self, frame, name):
        return runner.serialize_cut_csg_tree(_cut_timber_by_name(frame, name))["tree"]

    def _walk(self, node):
        yield node
        for child in node["children"]:
            yield from self._walk(child)

    def test_the_timber_body_adds_and_its_cuts_remove(self, mortise_and_tenon_frame):
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        assert tree["parity"] == "ADDITIVE"
        body, cut = tree["children"][0], tree["children"][1]
        assert body["parity"] == "ADDITIVE"
        assert cut["parity"] == "SUBTRACTIVE"

    def test_the_tenon_is_additive_though_it_sits_inside_a_cut(self, mortise_and_tenon_frame):
        """The case role alone gets wrong: the tenon is two subtract edges
        down, so the material it describes is left standing."""
        tree = self._tree(mortise_and_tenon_frame, "butt_timber")
        tenon = next(n for n in self._walk(tree) if n["label"] == "tenon")
        assert tenon["role"] == "cut" or tenon["role"] == "subtract"
        assert tenon["parity"] == "ADDITIVE"

    def test_the_payload_agrees_with_kumikis_own_rule(self, mortise_and_tenon_frame):
        """The guard against the two drifting apart: the serializer threads
        parity as it recurses, so it must still match the walk."""
        from kumiki.cutcsg import walk_csg_with_parity

        for name in ("butt_timber", "receiving_timber"):
            cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, name)
            expected = [p.name for _n, p in
                        walk_csg_with_parity(cut_timber.render_timber_with_cuts_csg_local())]
            serialized = [n["parity"] for n in self._walk(self._tree(mortise_and_tenon_frame, name))]
            assert serialized == expected

    def test_parity_matches_which_way_the_surface_actually_faces(self, mortise_and_tenon_frame):
        """Ground truth: a SUBTRACTIVE leaf's own normal opposes the finished
        solid's, an ADDITIVE one agrees. Checked at every surface point."""
        from kumiki.cutcsg import walk_csg_with_parity
        from kumiki.rule import safe_dot_product

        for name in ("butt_timber", "receiving_timber"):
            cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, name)
            csg = cut_timber.render_timber_with_cuts_csg_local()
            parity_by_id = {id(n): p for n, p in walk_csg_with_parity(csg)}
            checked = 0
            for triangle in triangulate_cutcsg(csg).mesh.triangles:
                centroid = [
                    (triangle[0][i] + triangle[1][i] + triangle[2][i]) / 3.0 for i in range(3)
                ]
                _p, target, _l = runner._navigate_csg_to_leaf(csg, centroid, PICK_EPS)
                point = runner._to_v3(centroid)
                own = target.get_outward_normal(point, PICK_EPS)
                composed = csg.get_outward_normal(point, PICK_EPS)
                if own is None or composed is None:
                    continue
                opposed = safe_dot_product(own, composed) < 0
                assert opposed == (parity_by_id[id(target)].name == "SUBTRACTIVE")
                checked += 1
            assert checked > 0


class TestJointDisplayName:
    """How a joint is named, wherever a joint is named.

    Name, then type, then id. The name its ticket was given says WHICH joint;
    the joint_type says what KIND it is, which is a weaker answer but a far
    better one than an id, since almost every joint in the library sets a type
    and almost none set a path. A joint with neither falls back to its kumiki
    id rather than a shared placeholder: several unnamed joints can touch one
    timber, and "which of these did I just click?" is the question the display
    exists to answer.
    """

    def _joint(self, ticket=None):
        from kumiki.ticket import JointTicket
        from kumiki.timber import Cutting, Joint

        timber = create_canonical_example_butt_joint_timbers(create_v3(0, 0, 0)).butt_timber
        return Joint(
            cuttings={"a": Cutting(timber=timber, negative_csg=EmptyCSG())},
            ticket=ticket if ticket is not None else JointTicket(),
            jointAccessories={},
        )

    def test_a_named_joint_shows_its_name(self):
        from kumiki.ticket import JointTicket

        joint = self._joint(JointTicket(path="joints/corner_a"))
        assert runner._joint_display_name(joint) == "corner_a"

    def test_an_unnamed_joint_falls_back_to_its_kumiki_id(self):
        joint = self._joint()
        name = runner._joint_display_name(joint)
        assert name == f"<unnamed joint - {joint.ticket.kumiki_id}>"

    def test_two_unnamed_joints_are_distinguishable(self):
        """The whole point of using the id rather than a fixed placeholder."""
        first, second = self._joint(), self._joint()
        assert runner._joint_display_name(first) != runner._joint_display_name(second)

    def test_the_joint_type_stands_in_when_there_is_no_name(self):
        """Weaker than a name -- it says what kind, not which one -- but the
        library sets a type on nearly every joint and a path on nearly none."""
        from kumiki.ticket import JointTicket

        joint = self._joint(JointTicket(joint_type="mortise_and_tenon"))
        assert runner._joint_display_name(joint) == "mortise_and_tenon"

    def test_an_authored_name_outranks_the_type(self):
        from kumiki.ticket import JointTicket

        joint = self._joint(JointTicket(path="joints/corner_a", joint_type="plain_butt"))
        assert runner._joint_display_name(joint) == "corner_a"

    def test_the_joint_list_and_the_csg_tree_agree(self, mortise_and_tenon_frame):
        """The divergence this rule exists to prevent: the layers payload used
        to fall back to joint_type while the tree fell back to the id, so one
        joint read two different ways depending on where you looked."""
        listed = {
            entry["kumikiEphemeralId"]: entry["name"]
            for entry in runner.serialize_layers(mortise_and_tenon_frame)["joints"]
        }
        assert listed
        for joint in mortise_and_tenon_frame.source_joints:
            assert listed[joint.ticket.kumiki_id] == runner._joint_display_name(joint)

    def test_a_joint_with_no_ticket_at_all_has_no_id_to_show(self):
        class TicketlessJoint:
            ticket = None

        assert runner._joint_display_name(TicketlessJoint()) == "<unnamed joint>"

    def test_it_reaches_the_pick_result(self, mortise_and_tenon_frame):
        """The fixture's joint has a type but no name, so a picked cut shows
        the type."""
        cut_timber = _cut_timber_by_name(mortise_and_tenon_frame, "butt_timber")
        csg = cut_timber.render_timber_with_cuts_csg_local()
        for triangle in triangulate_cutcsg(csg).mesh.triangles:
            centroid = [
                (triangle[0][i] + triangle[1][i] + triangle[2][i]) / 3.0 for i in range(3)
            ]
            _p, target, label = runner._navigate_csg_to_leaf(csg, centroid, PICK_EPS)
            if label.startswith("tenon"):
                name = runner._joint_name_for_node(csg, cut_timber, target)
                assert name == "mortise_and_tenon"
                return
        raise AssertionError("no tenon face found to click on")
