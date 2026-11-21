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


def test_reversed_ends_keep_the_real_stock_extension():
    board = Board(mm(100), create_v2(mm(12), mm(16)), Transform.identity(), TimberTicket("board"))
    view = FauxTimber(board, top=TimberFace.BOTTOM, front=TimberFace.RIGHT)
    cut = Cutting(view, maybe_top_end_cut_distance_from_bottom=mm(110))
    joint = view.restore_joint(Joint({"board": cut}, JointTicket("trim")))
    assert joint.cuttings["board"].timber is board
    assert joint.cuttings["board"].maybe_bottom_end_cut_distance_from_bottom == pytest.approx(-.010)
    assert joint.cuttings["board"].maybe_top_end_cut_distance_from_bottom is None


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
