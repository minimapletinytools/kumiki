"""Whether a feature shows in an orthographic view: exact for points and lines, else visible."""

from kumiki import (Cutting, CutTimber, Cylinder, Frame, Transform, create_timber, create_v2, create_v3, m, mm)
from kumiki.csg.cutcsg import OwnedFeatureHit
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.drawings.visibility import feature_visibility, line_visibility

import numpy as np
from pytest import approx

# The camera is at -y, looking along +y. A post's "front" faces +y, away from it.
LOOK = create_v3(0, 1, 0)


def _post(x, y, name, cuts=(), z=0):
    timber = create_timber(bottom_position=create_v3(x, y, z), length=m(1), size=create_v2(mm(100), mm(100)),
                           length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket=name)
    return CutTimber(timber, cuts=[cut(timber) for cut in cuts])


def _feature(cut_timber, name):
    root = cut_timber.render_timber_with_cuts_csg_local()
    feature = next(f for f in root.get_declared_features() if f.name == name)
    return FeatureHandle(timber=cut_timber.timber, hit=OwnedFeatureHit(feature=feature, owner=root))


def _seen(cut_timber, name, everyone):
    return feature_visibility(_feature(cut_timber, name), cut_timber, LOOK, everyone)


class TestOneTimber:

    def test_its_near_arrises_are_seen(self):
        post = _post(0, 0, "post")
        assert _seen(post, "rptw.back_right", [post]).visible

    def test_its_far_arrises_are_hidden_behind_the_near_ones(self):
        # On its outline the far arris lies on the same line as the near one, which is in
        # front of it: only the frontmost is seen.
        post = _post(0, 0, "post")
        assert not _seen(post, "rptw.front_right", [post]).visible
        assert not _seen(post, "rptw.front_left", [post]).visible
        assert _seen(post, "rptw.back_left", [post]).visible

    def test_a_face_seen_edge_on_is_seen(self):
        post = _post(0, 0, "post")
        result = _seen(post, "rptw.right", [post])
        assert result.visible and result.exact


class TestBehindAnother:

    def test_what_falls_inside_the_one_in_front_is_hidden(self):
        front, behind = _post(0, 0, "front"), _post(0.02, 0.5, "behind")
        # The one behind is 20mm to the right: its left arrises fall inside the front post.
        assert not _seen(behind, "rptw.back_left", [front, behind]).visible
        assert _seen(behind, "rptw.back_right", [front, behind]).visible

    def test_only_what_hides_it_counts(self):
        front, behind = _post(0, 0, "front"), _post(0.02, 0.5, "behind")
        assert _seen(behind, "rptw.back_left", [behind]).visible

    def test_a_point_behind_is_hidden(self):
        # Raised, so its bottom corner is behind the middle of the front post, not on its outline.
        front, behind = _post(0, 0, "front"), _post(0.02, 0.5, "behind", z=0.2)
        assert not _seen(behind, "rptw.bot_left_back", [front, behind]).visible


class TestPartlyHidden:

    def test_a_beam_across_the_middle_leaves_two_stretches(self):
        # A vertical line behind a horizontal beam crossing it from z 0.4 to 0.6.
        beam = CutTimber(create_timber(
            bottom_position=create_v3(-0.5, -0.5, 0.5), length=m(1), size=create_v2(mm(200), mm(200)),
            length_direction=create_v3(1, 0, 0), width_direction=create_v3(0, 0, 1), ticket="beam"), cuts=[])
        result = line_visibility(np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]),
                                 np.array([0.0, -1.0, 0.0]), [beam])
        lows_highs = sorted((round(a[2], 6), round(b[2], 6)) for a, b in result.stretches)
        assert result.visible and lows_highs == [(0.0, 0.4), (0.6, 1.0)]


class TestThroughABore:

    def test_it_is_seen_exactly_through_a_bore_in_the_way(self):
        # A bore through the front post, right where the line of sight to the one behind passes
        # (its left arrises are at x = -30mm).
        bore = lambda timber: Cutting(timber=timber, negative_csg=Cylinder(  # noqa: E731
            axis_direction=create_v3(0, 1, 0), radius=mm(10), position=create_v3(mm(-30), 0, mm(500)),
            start_distance=mm(-100), end_distance=mm(100)))
        front, behind = _post(0, 0, "front", cuts=[bore]), _post(0.02, 0.5, "behind")
        result = _seen(behind, "rptw.back_left", [front, behind])
        assert result.visible and result.exact
        [(start, end)] = result.stretches
        assert sorted((float(start[2]), float(end[2]))) == [approx(0.49, abs=1e-4), approx(0.51, abs=1e-4)]

    def test_a_curved_primitive_out_of_the_way_does_not(self):
        bore = lambda timber: Cutting(timber=timber, negative_csg=Cylinder(  # noqa: E731
            axis_direction=create_v3(0, 1, 0), radius=mm(10), position=create_v3(mm(30), 0, mm(500)),
            start_distance=mm(-100), end_distance=mm(100)))
        front, behind = _post(0, 0, "front", cuts=[bore]), _post(0.02, 0.5, "behind")
        result = _seen(behind, "rptw.back_left", [front, behind])
        assert not result.visible and result.exact


class TestAPeggedTenon:
    """The starter frame's tenons have a peg hole through them, which the edge-on face meets."""

    def test_two_of_its_four_long_arrises_show_from_each_side_exactly(self):
        import runpy
        from pathlib import Path

        from kumiki.csg.cutcsg import csg_children

        pattern = Path(__file__).resolve().parent.parent / "patterns" / "structures" / "my_cute_frame.py"
        frame = runpy.run_path(str(pattern))["build_frame"]()
        cross = next(c for c in frame.cut_timbers if c.timber.ticket.path == "Back Cross")

        def tenons(node):
            if "'tenon'" in repr(getattr(node, "label", None)):
                yield node
            for child in csg_children(node):
                yield from tenons(child)

        tenon = next(tenons(cross.render_timber_with_cuts_csg_local()))
        for look in (create_v3(0, 1, 0), create_v3(0, -1, 0), create_v3(0, 0, 1), create_v3(0, 0, -1)):
            results = []
            for name in ("arris.0", "arris.1", "arris.2", "arris.3"):
                feature = next(f for f in tenon.get_declared_features() if f.name == name)
                handle = FeatureHandle(timber=cross.timber, hit=OwnedFeatureHit(feature=feature, owner=tenon))
                results.append(feature_visibility(handle, cross, look, [cross]))
            assert all(r.exact for r in results), look
            assert sum(r.visible for r in results) == 2, (look, [r.visible for r in results])
