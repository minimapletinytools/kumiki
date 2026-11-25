import pytest

from kumiki import (Board, Cutting, FauxTimber, Frame, Joint, JointTicket, TimberCorner, TimberFace, TimberFeature,
                    TimberTicket, Transform, create_v2, create_v3, mm)
from kumiki.drawings.auto_drawings import solve_piece
from kumiki.drawings.reference_lines import timber_reference_lines
from patterns.mixed.mortise_and_tenon_joints_patterns import example_board_edge_tenon


def test_rotated_off_center_edge_tenon_and_matching_blind_mortise():
    joint = example_board_edge_tenon()
    board, rail = Frame.from_joints([joint]).cut_timbers
    board_solid = board.render_timber_with_cuts_csg_local()
    mortise = joint.cuttings["rail"].get_negative_csg_local()
    assert mortise is not None
    for x, y, z, in_board, in_mortise in [
        (50, 0, 115, True, True), (50, 7, 115, False, False),
        (50, 0, 185, False, False), (35, 0, 185, True, False),
        (61, 0, 115, False, True), (63, 0, 115, False, False),
    ]:
        p = create_v3(mm(x), mm(y), mm(z))
        world = board.timber.transform.local_to_global(p)
        assert board_solid.contains_point(p) == in_board
        assert mortise.contains_point(rail.timber.transform.global_to_local(world)) == in_mortise
    assert joint.cuttings["board"].timber is board.timber
    assert joint.cuttings["board"].get_maybe_top_end_cut() is None
    ref, = timber_reference_lines(board.timber, board_solid)
    assert ref["name"] == TimberFeature.FRONT_LEFT_EDGE.name.lower()
    assert ref["edgePositions"] == pytest.approx([0, -.06, .02, .3, -.06, .02])
    for pick in solve_piece(board).picks:
        dimension = pick.candidate
        anchors = (dimension.measure.anchor_a, dimension.measure.anchor_b)
        assert all(anchor.timber is board.timber for anchor in anchors)
        if {anchor.feature.name for anchor in anchors} == {"rptw.front_left", "shoulder×rptw.front"}:
            assert dimension.length == pytest.approx(.100)
            break
    else:
        pytest.fail("Expected a shoulder dimension from the board's reference edge")


@pytest.mark.parametrize("orientation,faux_bottom,faux_top,real_bottom,real_top", [
    (TimberFace.TOP, None, 83, None, 83),
    (TimberFace.TOP, 7, None, 7, None),
    (TimberFace.TOP, -4, 110, -4, 110),
    (TimberFace.TOP, 7, 83, 7, 83),
    (TimberFace.BOTTOM, None, 110, -10, None),
    (TimberFace.BOTTOM, -4, None, None, 104),
    (TimberFace.BOTTOM, 7, 83, 17, 93),
])
def test_end_trims_restore_real_end_distances_and_finished_length(
        orientation, faux_bottom, faux_top, real_bottom, real_top):
    board = Board(mm(100), create_v2(mm(12), mm(16)), Transform.identity(), TimberTicket("board"))
    view = FauxTimber(board, top=orientation, front=TimberFace.RIGHT)
    cut = Cutting(view,
                  maybe_bottom_end_cut_distance_from_bottom=mm(faux_bottom) if faux_bottom is not None else None,
                  maybe_top_end_cut_distance_from_bottom=mm(faux_top) if faux_top is not None else None)
    joint = view.restore_joint(Joint({"board": cut}, JointTicket("trim")))
    restored = joint.cuttings["board"]
    assert restored.timber is board
    for distance, expected in [(restored.maybe_bottom_end_cut_distance_from_bottom, real_bottom),
                               (restored.maybe_top_end_cut_distance_from_bottom, real_top)]:
        if expected is None:
            assert distance is None
        else:
            assert distance == pytest.approx(mm(expected))

    solid = Frame.from_joints([joint]).cut_timbers[0].render_timber_with_cuts_csg_local()
    low = real_bottom if real_bottom is not None else 0
    high = real_top if real_top is not None else 100
    for z, wood in [(low - 1, False), (low + 1, True), (high - 1, True), (high + 1, False)]:
        assert solid.contains_point(create_v3(0, 0, mm(z))) == wood


@pytest.mark.parametrize("side,axis,low,high", [
    (TimberFace.RIGHT, 0, -24, 19), (TimberFace.LEFT, 0, -19, 24),
    (TimberFace.FRONT, 1, -14, 9), (TimberFace.BACK, 1, -9, 14),
])
def test_both_faux_end_cuts_on_a_side_trim_only_the_cross_section(side, axis, low, high):
    transform = example_board_edge_tenon().cuttings["board"].timber.transform
    board = Board(mm(100), create_v2(mm(60), mm(40)), transform, TimberTicket("board"))
    view = FauxTimber(board, top=side, front=TimberFace.TOP)
    cut = Cutting(view, maybe_bottom_end_cut_distance_from_bottom=mm(6),
                  maybe_top_end_cut_distance_from_bottom=view.length - mm(11))
    joint = view.restore_joint(Joint({"board": cut}, JointTicket("side")))
    restored = joint.cuttings["board"]
    assert restored.timber is board
    assert restored.get_maybe_bottom_end_cut() is None
    assert restored.get_maybe_top_end_cut() is None
    solid = Frame.from_joints([joint]).cut_timbers[0].render_timber_with_cuts_csg_local()
    for z in (1, 50, 99):
        for across, wood in [(low - 1, False), (low + 1, True), (high - 1, True), (high + 1, False)]:
            x, y = (across, 0) if axis == 0 else (0, across)
            assert solid.contains_point(create_v3(mm(x), mm(y), mm(z))) == wood
    for z in (-1, 101):
        assert not solid.contains_point(create_v3(0, 0, mm(z)))


def test_side_stock_must_reach_the_cut_and_faces_must_be_perpendicular():
    board = Board(mm(100), create_v2(mm(12), mm(16)), Transform.identity())
    with pytest.raises(ValueError, match="perpendicular"):
        FauxTimber(board, top=TimberFace.RIGHT, front=TimberFace.LEFT)
    view = FauxTimber(board, top=TimberFace.LEFT, front=TimberFace.FRONT)
    for cut in (Cutting(view, maybe_top_end_cut_distance_from_bottom=mm(16)),
                Cutting(view, maybe_bottom_end_cut_distance_from_bottom=mm(-4))):
        with pytest.raises(ValueError, match="4 mm more stock"):
            view.restore_joint(Joint({"board": cut}, JointTicket("side")))

@pytest.mark.parametrize("top,front", [(a, b) for a in TimberFace for b in TimberFace if a.is_perpendicular(b)])
def test_each_face_pair_describes_the_same_stock(top, front):
    board = example_board_edge_tenon().cuttings["board"].timber
    assert isinstance(board, Board)
    view = FauxTimber(board, top=top, front=front)

    def corners(timber):
        return {tuple(round(float(x), 8) for x in timber.get_corner_position_global(corner)) for corner in TimberCorner}
    assert corners(view) == corners(board)
    assert view.get_face_direction_global(TimberFace.TOP) == board.get_face_direction_global(top)
    assert view.get_face_direction_global(TimberFace.FRONT) == board.get_face_direction_global(front)
    assert view.can_be_extended_for_joints() == (top in (TimberFace.TOP, TimberFace.BOTTOM))


def test_xray_sides_are_restored_to_the_original_faces():
    from kumiki import RectangularPrism
    from kumiki.csg.cutcsg import walk_csg_with_parity, with_xray_from

    board = Board(mm(100), create_v2(mm(12), mm(16)), Transform.identity(), TimberTicket("board"))
    view = FauxTimber(board, top=TimberFace.RIGHT, front=TimberFace.TOP)
    hole = RectangularPrism(size=create_v2(mm(4), mm(4)), transform=Transform.identity(),
                            start_distance=mm(2), end_distance=mm(6))
    untagged = Cutting(view, negative_csg=hole)
    tagged = Cutting(view, negative_csg=with_xray_from(hole, TimberFace.FRONT, TimberFace.TOP))

    def sides(cut):
        restored = view.restore_joint(Joint({"board": cut}, JointTicket("hole"))).cuttings["board"]
        return {feature.properties.xray_from_faces for owner, _ in walk_csg_with_parity(restored.negative_csg)
                for feature in owner.get_declared_features()}

    assert sides(untagged) == {frozenset()}
    assert sides(tagged) == {frozenset([TimberFace.TOP, TimberFace.RIGHT])}
