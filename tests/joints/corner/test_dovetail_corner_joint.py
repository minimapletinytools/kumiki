"""
Tests for Kumiki timber framing system
"""

import dataclasses

import pytest
from kumiki import *
from kumiki.rule import atan, cross_product, safe_normalize_vector
from kumiki.cutcsg import Difference, SolidUnion
from kumiki.timber import KumikiArrangementError
from tests.testing_shavings import create_standard_horizontal_timber


# All corner fixtures use square 6x6 timbers, so the layout axis and the
# thickness through the corner are both 6 and the corner square is 6x6x6.
HALF = 3.0


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()


def _dovetail(angle=atan(scalar(1, 8)), small_width=scalar(1), depth=None):
    return SingleDovetailSizeParameter(angle=angle, small_width=small_width, depth=depth)


def _make_corner_arrangement(direction1, direction2, timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM):
    """
    A 90 degree corner of two square 6x6 timbers whose arms run away from the origin.

    `direction1`/`direction2` are the directions each timber's arm extends in, so the
    corner square straddles the origin and both timbers are cut back to it. The joined
    end of each timber is the one pointing at the corner.
    """
    plane_normal = safe_normalize_vector(cross_product(direction1, direction2))

    def make(direction, end, ticket):
        length_direction = direction if end == TimberEnd.BOTTOM else -direction
        bottom_position = create_v3(0, 0, 0) if end == TimberEnd.BOTTOM else direction * scalar(60)
        return create_timber(
            length=scalar(60),
            size=create_v2(scalar(6), scalar(6)),
            bottom_position=bottom_position,
            length_direction=length_direction,
            width_direction=plane_normal,
            ticket=ticket,
        )

    timber1 = make(direction1, timber1_end, "timber1")
    timber2 = make(direction2, timber2_end, "timber2")
    return CornerJointTimberArrangement(
        timber1=timber1,
        timber2=timber2,
        timber1_end=timber1_end,
        timber2_end=timber2_end,
        front_face_on_timber1=timber1.get_closest_oriented_long_face_from_global_direction(plane_normal),
    )


def _check_corner_geometry(arrangement, distances, dovetails, joint):
    """
    Walk the corner in its own (u, v, w) frame and check both timbers against the
    dovetail layout.

    u runs along timber1's arm, v along timber2's arm, w along the layout axis (the
    corner plane normal, which front_face_on_timber1 points along). The corner square
    is |u|, |v|, |w| <= 3; the shoulder is at u = 3 and dovetails reach down towards
    u = -3, widening as they go.
    """
    timber1 = arrangement.timber1
    timber2 = arrangement.timber2
    u_axis = timber1.get_face_direction_global(arrangement.timber1_end) * scalar(-1)
    v_axis = timber2.get_face_direction_global(arrangement.timber2_end) * scalar(-1)
    w_axis = timber1.get_face_direction_global(arrangement.front_face_on_timber1)

    render1 = _render_cutting(joint.cuttings["dovetail_timber"])
    render2 = _render_cutting(joint.cuttings["socket_timber"])

    def at(u, v, w):
        point = u_axis * scalar(u) + v_axis * scalar(v) + w_axis * scalar(w)
        return (
            render1.contains_point(timber1.transform.global_to_local(point)),
            render2.contains_point(timber2.transform.global_to_local(point)),
        )

    def assert_in_dovetail_timber(u, v, w, message):
        in1, in2 = at(u, v, w)
        assert in1, f"{message}: expected material on the dovetail timber at ({u}, {v}, {w})"
        assert not in2, f"{message}: expected no material on the socket timber at ({u}, {v}, {w})"

    def assert_in_socket_timber(u, v, w, message):
        in1, in2 = at(u, v, w)
        assert not in1, f"{message}: expected no material on the dovetail timber at ({u}, {v}, {w})"
        assert in2, f"{message}: expected material on the socket timber at ({u}, {v}, {w})"

    margin = 0.05

    # Each arm, away from the corner, belongs only to its own timber.
    assert_in_dovetail_timber(20, 0, 0, "timber1 arm")
    assert_in_socket_timber(0, 20, 0, "timber2 arm")

    # Timber1 is whole up to the shoulder, and stops at timber2's far face.
    for w in (-HALF + margin, 0.0, HALF - margin):
        assert_in_dovetail_timber(HALF + 1, 0, w, "timber1 before the shoulder")
    in1, in2 = at(-HALF - margin, 0, 0)
    assert not in1 and not in2, "neither timber reaches past the far face of the other"

    # Every dovetail, sampled from the shoulder down to its tip.
    distance_from_front_face = 0.0
    for index, (distance, dovetail) in enumerate(zip(distances, dovetails)):
        distance_from_front_face += float(distance)
        center_w = HALF - distance_from_front_face
        depth = float(dovetail.depth) if dovetail.depth is not None else 2 * HALF
        flare = float(tan(dovetail.angle))
        half_small_width = float(dovetail.small_width) / 2

        for penetration in (margin, depth / 2, depth - margin):
            u = HALF - penetration
            half_width = half_small_width + penetration * flare
            assert_in_dovetail_timber(u, 0, center_w, f"dovetail {index} core")
            assert_in_dovetail_timber(u, 0, center_w + half_width - margin, f"dovetail {index} inside its edge")
            if center_w + half_width + margin < HALF:
                assert_in_socket_timber(u, 0, center_w + half_width + margin, f"dovetail {index} outside its edge")
            # The dovetail spans the whole thickness of timber1 through the corner.
            for v in (-HALF + margin, HALF - margin):
                assert_in_dovetail_timber(u, v, center_w, f"dovetail {index} through the thickness")

        # Past the tip of a half blind dovetail, timber2 is still solid.
        if depth < 2 * HALF - margin:
            assert_in_socket_timber(HALF - depth - margin, 0, center_w, f"dovetail {index} blind backing")


class TestDovetailCornerJoint:
    """Test cut_dovetail_corner_joint."""

    def test_general_dovetail_corner_joint(self):
        """
        General test: two through dovetails on a corner in the XY plane, checked
        against hand-computed points.

        - timber1: +X arm, 6x6, joined end pointing back at the origin
        - timber2: +Y arm, 6x6, joined end pointing back at the origin
        - front_face_on_timber1 points +Z, so dovetails are laid out down from z=+3

        Corner square: x, y, z all in [-3, 3]. The shoulder is timber2's near face at
        x=+3 and dovetails run through to x=-3. Centers are 1.5 and 4.5 from the front
        face, i.e. z=+1.5 and z=-1.5. With small_width=1 and a 1:8 flare, half width
        runs from 0.5 at the shoulder to 0.5 + 6/8 = 1.25 at the tip.
        """
        timber1 = create_standard_horizontal_timber(direction='x', length=60, size=(6, 6), position=(0, 0, 0), ticket="timber1")
        timber2 = create_standard_horizontal_timber(direction='y', length=60, size=(6, 6), position=(0, 0, 0), ticket="timber2")
        arrangement = CornerJointTimberArrangement(
            timber1=timber1,
            timber2=timber2,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.FRONT,
        )

        distances = [scalar(3, 2), scalar(3)]
        dovetails = [_dovetail(), _dovetail()]
        joint = cut_dovetail_corner_joint(arrangement, distances, dovetails)

        # ---- structure ----
        assert len(joint.cuttings) == 2
        assert set(joint.cuttings) == {"dovetail_timber", "socket_timber"}
        assert joint.ticket.joint_type == "dovetail_corner"
        assert len(joint.jointAccessories) == 0

        dovetail_cut = joint.cuttings["dovetail_timber"]
        socket_cut = joint.cuttings["socket_timber"]
        assert isinstance(dovetail_cut.negative_csg, Difference)
        assert isinstance(socket_cut.negative_csg, SolidUnion)
        assert len(socket_cut.negative_csg.children) == 2

        # Each timber is cut back to the far face of the other, at x=-3 and y=-3.
        assert dovetail_cut.get_maybe_top_end_cut() is None
        assert socket_cut.get_maybe_top_end_cut() is None
        assert dovetail_cut.maybe_bottom_end_cut_distance_from_bottom == scalar(-3)
        assert socket_cut.maybe_bottom_end_cut_distance_from_bottom == scalar(-3)

        # ---- geometry ----
        dovetail_csg = _render_cutting(dovetail_cut)
        socket_csg = _render_cutting(socket_cut)

        def in_dovetail_timber(point):
            return dovetail_csg.contains_point(timber1.transform.global_to_local(point))

        def in_socket_timber(point):
            return socket_csg.contains_point(timber2.transform.global_to_local(point))

        # At the shoulder (x=2.9) the upper dovetail is 1 wide about z=1.5.
        assert in_dovetail_timber(create_v3(scalar(2.9), 0, scalar(1.9)))
        assert not in_dovetail_timber(create_v3(scalar(2.9), 0, scalar(2.1)))
        assert in_socket_timber(create_v3(scalar(2.9), 0, scalar(2.1)))

        # At the tip (x=-2.9) it has flared to 2.4750 wide, so z=2.1 is now inside it.
        assert in_dovetail_timber(create_v3(scalar(-2.9), 0, scalar(2.1)))
        assert not in_socket_timber(create_v3(scalar(-2.9), 0, scalar(2.1)))
        assert not in_dovetail_timber(create_v3(scalar(-2.9), 0, scalar(2.8)))

        # The gap between the two dovetails is timber2's, all the way through.
        for x in (scalar(2.9), scalar(0), scalar(-2.9)):
            assert in_socket_timber(create_v3(x, 0, scalar(0)))
            assert not in_dovetail_timber(create_v3(x, 0, scalar(0)))

        # Dovetails span timber1's whole thickness, so timber2 has nothing beside them.
        for y in (scalar(-2.9), scalar(2.9)):
            assert in_dovetail_timber(create_v3(scalar(0), y, scalar(1.5)))
            assert not in_socket_timber(create_v3(scalar(0), y, scalar(1.5)))

        # Bodies away from the corner, and nothing past either far face.
        assert in_dovetail_timber(create_v3(scalar(20), 0, 0))
        assert in_socket_timber(create_v3(0, scalar(20), 0))
        assert not in_dovetail_timber(create_v3(scalar(-3.1), 0, scalar(1.5)))
        assert not in_socket_timber(create_v3(0, scalar(-3.1), 0))

    def test_dovetail_counts(self):
        """One dovetail, and a row of four, both cut the corner correctly."""
        for distances, dovetails in (
            ([scalar(3)], [_dovetail()]),
            (
                [scalar(3, 4), scalar(3, 2), scalar(3, 2), scalar(3, 2)],
                [_dovetail(angle=atan(scalar(1, 16)), small_width=scalar(1, 2)) for _ in range(4)],
            ),
        ):
            arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
            joint = cut_dovetail_corner_joint(arrangement, distances, dovetails)
            sockets = joint.cuttings["socket_timber"].negative_csg
            assert isinstance(sockets, SolidUnion)
            assert len(sockets.children) == len(dovetails)
            _check_corner_geometry(arrangement, distances, dovetails, joint)

    def test_multiple_orientations(self):
        """The joint cuts the same corner in every plane, and off either end."""
        cases = [
            (create_v3(1, 0, 0), create_v3(0, 1, 0), TimberEnd.BOTTOM, TimberEnd.BOTTOM),
            (create_v3(0, 1, 0), create_v3(0, 0, 1), TimberEnd.BOTTOM, TimberEnd.BOTTOM),
            (create_v3(0, 0, 1), create_v3(1, 0, 0), TimberEnd.BOTTOM, TimberEnd.BOTTOM),
            (create_v3(-1, 0, 0), create_v3(0, 0, 1), TimberEnd.TOP, TimberEnd.TOP),
            (create_v3(0, -1, 0), create_v3(1, 0, 0), TimberEnd.TOP, TimberEnd.BOTTOM),
            (create_v3(0, 0, -1), create_v3(0, -1, 0), TimberEnd.BOTTOM, TimberEnd.TOP),
        ]
        distances = [scalar(3, 2), scalar(3)]
        dovetails = [_dovetail(), _dovetail()]

        for direction1, direction2, end1, end2 in cases:
            arrangement = _make_corner_arrangement(direction1, direction2, end1, end2)
            joint = cut_dovetail_corner_joint(arrangement, distances, dovetails)

            joined_end_cut = (
                joint.cuttings["dovetail_timber"].get_maybe_top_end_cut()
                if end1 == TimberEnd.TOP
                else joint.cuttings["dovetail_timber"].get_maybe_bottom_end_cut()
            )
            assert joined_end_cut is not None, f"{direction1.T} / {direction2.T} should be end cut at its joined end"

            _check_corner_geometry(arrangement, distances, dovetails, joint)

    def test_extreme_parameters(self):
        """Zero flare, a full through depth, and a dovetail filling the layout axis."""
        # angle 0 is a straight finger: the box joint at the bottom of this joint.
        distances = [scalar(3, 2), scalar(3)]
        dovetails = [_dovetail(angle=scalar(0)), _dovetail(angle=scalar(0))]
        arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
        joint = cut_dovetail_corner_joint(arrangement, distances, dovetails)
        _check_corner_geometry(arrangement, distances, dovetails, joint)

        # An explicit depth equal to timber2's full thickness is the same through
        # dovetail that depth=None gives.
        arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
        through = cut_dovetail_corner_joint(arrangement, [scalar(3)], [_dovetail(depth=scalar(6))])
        _check_corner_geometry(arrangement, [scalar(3)], [_dovetail(depth=scalar(6))], through)

        # A shallow half blind dovetail leaves timber2 solid behind it.
        arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
        half_blind = [_dovetail(depth=scalar(1))]
        joint = cut_dovetail_corner_joint(arrangement, [scalar(3)], half_blind)
        _check_corner_geometry(arrangement, [scalar(3)], half_blind, joint)

        # One dovetail as wide as the layout axis allows: a 1:8 flare over a depth of 6
        # takes 0.75 a side, so a small width of 4.5 lands its tip exactly on both faces.
        arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
        widest = [_dovetail(small_width=scalar(9, 2))]
        joint = cut_dovetail_corner_joint(arrangement, [scalar(3)], widest)
        _check_corner_geometry(arrangement, [scalar(3)], widest, joint)

    def test_dovetail_corner_joint_parameter_validation(self):
        def cut(distances, dovetails, arrangement=None):
            if arrangement is None:
                arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
            return cut_dovetail_corner_joint(arrangement, distances, dovetails)

        with pytest.raises(AssertionError, match="same length"):
            cut([scalar(3), scalar(1)], [_dovetail()])

        with pytest.raises(AssertionError, match="at least one dovetail"):
            cut([], [])

        with pytest.raises(AssertionError, match="depth"):
            cut([scalar(3)], [_dovetail(depth=scalar(7))])

        with pytest.raises(AssertionError, match="depth"):
            cut([scalar(3)], [_dovetail(depth=scalar(0))])

        with pytest.raises(AssertionError, match="small_width"):
            cut([scalar(3)], [_dovetail(small_width=scalar(0))])

        with pytest.raises(AssertionError, match="angle"):
            cut([scalar(3)], [_dovetail(angle=scalar(-1, 10))])

        with pytest.raises(AssertionError, match="angle"):
            cut([scalar(3)], [_dovetail(angle=pi / scalar(2))])

        with pytest.raises(AssertionError, match="crosses front_face_on_timber1"):
            cut([scalar(1, 2)], [_dovetail()])

        with pytest.raises(AssertionError, match="runs past the face opposite"):
            cut([scalar(11, 2)], [_dovetail()])

        with pytest.raises(AssertionError, match="overlaps dovetail 0"):
            cut([scalar(3, 2), scalar(1, 2)], [_dovetail(), _dovetail()])

        # front_face_on_timber1 carries the layout, so it has to be there.
        arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
        with pytest.raises(AssertionError, match="front_face_on_timber1 must be set"):
            cut([scalar(3)], [_dovetail()], dataclasses.replace(arrangement, front_face_on_timber1=None))

        # ... and it has to point along the corner plane normal.
        with pytest.raises(KumikiArrangementError, match="front_face_on_timber1"):
            cut(
                [scalar(3)],
                [_dovetail()],
                dataclasses.replace(
                    arrangement,
                    front_face_on_timber1=arrangement.front_face_on_timber1.rotate_right(),
                ),
            )

        # Timbers that are not flush across the layout axis cannot interlock.
        offset_arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(0, 1, 0))
        offset_timber2 = create_timber(
            length=scalar(60),
            size=create_v2(scalar(4), scalar(6)),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(0, 1, 0),
            width_direction=create_v3(0, 0, 1),
            ticket="timber2",
        )
        with pytest.raises(AssertionError, match="flush"):
            cut([scalar(3)], [_dovetail()], dataclasses.replace(offset_arrangement, timber2=offset_timber2))

        # Non-orthogonal timbers have no corner square to interlock in.
        skew_arrangement = _make_corner_arrangement(create_v3(1, 0, 0), create_v3(1, 1, 0))
        with pytest.raises(KumikiArrangementError, match="orthogonal"):
            cut([scalar(3)], [_dovetail()], skew_arrangement)
