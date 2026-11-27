import math

import numpy as np
import pytest

from kumiki import CutTimber, Timber, TimberFeature, TimberTicket, Transform, create_v2, create_v3
from kumiki.csg.cutcsg import Cylinder, Difference, RectangularPrism, SolidUnion
from kumiki.csg.pathcsg import ArcSegment, FancyPath, PathExtrusion, StraightSegment
from kumiki.drawings.svg import DrawingSolid, DrawingStyles, render_svg_view
from kumiki.measuring import locate_face
from kumiki.rule import as_ndarray


def _box(width=4, height=4, bottom=0, top=1, x=0, y=0):
    placement = Transform(position=create_v3(x, y, 0), orientation=Transform.identity().orientation)
    return RectangularPrism(size=create_v2(width, height), transform=placement, start_distance=bottom, end_distance=top)


def _view(members, right=(1, 0, 0), up=(0, 1, 0), styles=DrawingStyles(), ghosts=()):
    camera = dict(center=[0, 0, 0], right=right, up=up, width=10, height=10)
    return render_svg_view(members, set(ghosts), camera, 100, 100, styles)


def _arcs(view, key):
    return [p.get('d', '') for p in view.findall(f'.//{{*}}g[@data-member="{key}"]/{{*}}path') if ' A' in p.get('d', '')]


def test_bore_keeps_true_arcs_only_on_open_side_and_stops_at_foreground():
    bore = Cylinder(axis_direction=create_v3(0, 0, 1), radius=1, start_distance=.5, end_distance=2)
    members = {'beam': DrawingSolid(Difference(_box(), [bore]), Transform.identity())}
    assert _arcs(_view(members), 'beam')
    assert not _arcs(_view(members, right=(-1, 0, 0)), 'beam')
    members['cover'] = DrawingSolid(_box(width=2, bottom=2, top=3, x=-1), Transform.identity())
    half = _arcs(_view(members), 'beam')
    assert half
    for path in half:
        for arc in path.split(' A')[1:]:
            x = float(arc.split()[5])
            assert x >= 50 - 1e-6
    assert _arcs(_view(members, ghosts=['cover']), 'beam') != half


def test_notch_trims_original_rim_at_the_cut_plane():
    bore = Cylinder(axis_direction=create_v3(0, 0, 1), radius=1, start_distance=.5, end_distance=2)
    notch = _box(width=4, height=2, bottom=.25, top=2, y=1.5)
    solid = DrawingSolid(Difference(_box(), [bore, notch]), Transform.identity())
    opening = [rim for rim in solid.rims if abs(rim.arc.center[2] - 1) < 1e-7]
    assert sum(abs(rim.stop - rim.start) for rim in opening) == pytest.approx(4 * math.pi / 3)
    assert all(rim.arc.point((rim.start + rim.stop) / 2)[1] < .5 for rim in opening)


def test_one_bore_removes_the_overlapping_part_of_another_bores_rim():
    bores = [Cylinder(axis_direction=create_v3(0, 0, 1), position=create_v3(x, 0, 0),
                      radius=1, start_distance=.4, end_distance=2) for x in (0, 1)]
    solid = DrawingSolid(Difference(_box(), bores), Transform.identity())
    for bore in bores:
        rims = [rim for rim in solid.rims if rim.owner is bore and abs(rim.arc.center[2] - 1) < 1e-7]
        assert sum(abs(rim.stop - rim.start) for rim in rims) == pytest.approx(4 * math.pi / 3)


def test_extruded_arc_has_smooth_outline_and_two_corners_at_its_flat_side():
    profile = FancyPath([ArcSegment(create_v2(0, 0), 1, 0, math.pi),
                         StraightSegment(create_v2(-1, 0), create_v2(1, 0))])
    solid = DrawingSolid(PathExtrusion(profile, start_distance=0, end_distance=1), Transform.identity())
    assert _arcs(_view({'moulding': solid}), 'moulding')
    corners = list(solid.generators(np.array([0., 0., 1.])))
    assert {tuple(np.round(edge[1][:2], 6)) for edge in corners} == {(-1., 0.), (1., 0.)}


def test_partially_flush_faces_only_draw_the_exposed_crease():
    long = _box(width=1, height=1, x=.5, y=.5)
    short = _box(width=1, height=.5, x=1.5, y=.25)
    member = DrawingSolid(SolidUnion(children=[long, short]), Transform.identity())
    along_y = [(min(a[1], b[1]), max(a[1], b[1])) for _, a, b in member.lines
               if np.allclose([a[0], b[0], a[2], b[2]], 1)]
    assert np.asarray(along_y) == pytest.approx(np.array([[.5, 1.]]))


def test_reference_arris_centerline_ptw_and_both_faces_tinted_light_blue():
    edge = TimberFeature.RIGHT_FRONT_EDGE
    timber = Timber(length=4, size=create_v2(2, 2), transform=Transform.identity(),
                    rough_half_sizes=(create_v2(1, 1.2), create_v2(1, 1.2)),
                    ticket=TimberTicket('beam', reference_features=(edge,)))
    members = {'beam': DrawingSolid(CutTimber(timber).render_timber_with_cuts_csg_local(), timber.transform, timber)}
    normals = [as_ndarray(locate_face(timber, face).normal) for face in edge.long_faces_it_rests_on()]
    toward = (normals[0] + normals[1]) / math.sqrt(2)
    right = np.cross([0., 0., 1.], toward)
    plain = _view(members, right, (0, 0, 1))
    assert len(plain.findall(".//{*}g[@class='face-fills']/{*}path")) == 0
    for kind in ('centerline', 'perfect-face', 'right_front_edge'):
        assert plain.findall(f".//{{*}}g[@class='{kind}']/{{*}}path")
    assert plain.find(".//{*}g[@class='right_front_edge']").attrib['stroke'] == '#2458ab'
    tinted = _view(members, right, (0, 0, 1), DrawingStyles(reference_faces=True))
    fills = tinted.findall(".//{*}g[@class='face-fills']/{*}path")
    assert {p.get('data-feature') for p in fills} == {face.name for face in edge.long_faces_it_rests_on()}
    assert {p.get('fill') for p in fills} == {'#cfdfec'}


def test_centerline_dashes_align_across_centerplane_outlines_and_foreground_clipping():
    timber = Timber(length=4, size=create_v2(2, 2), transform=Transform.identity(),
                    ticket=TimberTicket('beam', reference_features=(TimberFeature.CENTERLINE,)))
    members = {'beam': DrawingSolid(CutTimber(timber).render_timber_with_cuts_csg_local(), timber.transform, timber),
               'cover': DrawingSolid(_box(bottom=1.2, top=2.7, x=-5), Transform.identity())}
    for show_centers in (False, True):
        view = _view(members, right=(0, 0, 1), up=(0, 1, 0), styles=DrawingStyles(centerlines=show_centers))
        if not show_centers:
            assert not view.findall(".//{*}g[@class='centerline']")
            continue
        axis, = view.findall(".//{*}g[@class='centerline']")
        planes = view.findall(".//{*}g[@class='centerplane']")
        assert bool(planes) == show_centers
        for group in [axis, *planes]:
            assert group.get('stroke') == '#dc7777'
            assert group.get('stroke-dasharray') == '6 10'
            strokes = {(p.get('d'), p.get('stroke-dashoffset')) for p in group}
            assert strokes == {('M50 50 L62 50', '50'), ('M77 50 L90 50', '77')}


@pytest.mark.parametrize('edge', [TimberFeature.RIGHT_FRONT_EDGE, TimberFeature.FRONT_LEFT_EDGE,
                                  TimberFeature.LEFT_BACK_EDGE, TimberFeature.BACK_RIGHT_EDGE])
def test_reference_arris_is_highlighted_only_from_its_two_adjoining_faces(edge):
    timber = Timber(length=4, size=create_v2(2, 2), transform=Transform.identity(),
                    ticket=TimberTicket('beam', reference_features=(edge,)))
    members = {'beam': DrawingSolid(CutTimber(timber).render_timber_with_cuts_csg_local(), timber.transform, timber)}
    up = np.array([0., 0., 1.])
    for face in edge.long_faces_it_rests_on():
        normal = as_ndarray(locate_face(timber, face).normal)
        for side in (1, -1):
            right = np.cross(up, side * normal)
            view = _view(members, right, up)
            strokes = view.findall(f".//{{*}}g[@class='{edge.name.lower()}']/{{*}}path")
            assert bool(strokes) == (side == 1)


def test_nearer_ordinary_arris_hides_the_overlapping_part_of_a_blue_arris():
    timber = Timber(length=4, size=create_v2(2, 2), transform=Transform.identity(),
                    ticket=TimberTicket('beam', reference_features=(TimberFeature.RIGHT_FRONT_EDGE,)))
    members = {'beam': DrawingSolid(CutTimber(timber).render_timber_with_cuts_csg_local(), timber.transform, timber),
               'cover': DrawingSolid(_box(width=2, height=2, bottom=1, top=3, x=4, y=-1e-10), Transform.identity())}
    view = _view(members, right=(0, 1, 0), up=(0, 0, 1))
    path, = view.findall(".//{*}g[@class='right_front_edge']/{*}path")
    segments = path.attrib['d'].replace('M', '').replace('L', '').split()
    assert list(map(float, segments)) == pytest.approx([60, 50, 60, 40, 60, 20, 60, 10], abs=1e-5)

@pytest.mark.parametrize('mode', ['none', 'noOverlay', 'overlay', 'xray'])
def test_inherit_viewer_materials_and_edge_mode_on_a_blind_bore(mode):
    bore = Cylinder(axis_direction=create_v3(0, 0, 1), radius=1, start_distance=.5, end_distance=2)
    members = {'beam': DrawingSolid(Difference(_box(), [bore]), Transform.identity())}
    camera = dict(center=[0, 0, 0], right=[-1, 0, 0], up=[0, 1, 0], width=10, height=10)
    materials = {'beam': dict(edge='#335588', edgeOpacity=.4, width=2, surface='#ccaa88', opacity=.65)}
    view = render_svg_view(members, set(), camera, 100, 100, appearances=materials, edge_mode=mode)
    surface, = view.findall(".//{*}g[@class='member-fills']/{*}path")
    assert surface.get('fill') == '#ccaa88' and surface.get('fill-opacity') == '0.65'
    edges, = view.findall(".//{*}g[@class='edges']/{*}g")
    assert edges.get('stroke') == '#335588' and edges.get('stroke-width') == '2'
    assert edges.get('stroke-opacity') == '0.4'
    assert bool(edges.findall('{*}path')) == (mode != 'none')
    assert bool(_arcs(view, 'beam')) == (mode == 'overlay')
    hidden = edges.find("{*}g[@class='xray-edges']")
    assert (hidden is not None) == (mode == 'xray')
    if hidden is not None:
        assert hidden.get('stroke-dasharray')
        assert any(' A' in p.attrib['d'] for p in hidden.findall('{*}path'))


def test_directional_xray_through_own_stock_clips_at_another_member():
    from kumiki.csg.cutcsg import START_CAP, FeatureOverride, FeatureProperties
    from kumiki.timber_features import TimberFace

    timber = Timber(length=4, size=create_v2(4, 4), transform=Transform.identity(), ticket=TimberTicket('beam'))
    cutter = RectangularPrism(size=create_v2(2, 2), start_distance=1, end_distance=5,
                              feature_overrides=[FeatureOverride(START_CAP, 'floor', FeatureProperties(
                                  xray_from_faces=frozenset([TimberFace.FRONT])))])
    root = Difference(_box(top=4), [cutter])
    members = {'beam': DrawingSolid(root, timber.transform, timber),
               'cover': DrawingSolid(_box(width=2, height=1, bottom=0, top=2, x=-1, y=3), Transform.identity())}
    for side in [1, -1]:
        view = _view(members, right=(-side, 0, 0), up=(0, 0, 1))
        paths = view.findall(".//{*}g[@class='feature-xray']/{*}path")
        assert bool(paths) == (side == 1)
        for path in paths:
            coords = list(map(float, path.get('d').replace('M', '').replace('L', '').split()))
            assert max(coords[0], coords[2]) <= 50.00001
            assert coords[1] == pytest.approx(40)


def test_centerlines_where_measured_draw_only_those_a_dimension_goes_to():
    timber = Timber(length=4, size=create_v2(2, 2), transform=Transform.identity(), ticket=TimberTicket('beam'))
    members = {'beam': DrawingSolid(CutTimber(timber).render_timber_with_cuts_csg_local(), timber.transform, timber)}
    camera = dict(center=[0, 0, 0], right=(0, 0, 1), up=(0, 1, 0), width=10, height=10)

    def drawn(measured):
        view = render_svg_view(members, set(), camera, 100, 100, DrawingStyles(centerlines='measured'),
                               measured=measured)
        return len(view.findall(".//{*}g[@class='centerplane']")), len(view.findall(".//{*}g[@class='centerline']"))

    assert drawn(set()) == (0, 0)
    # Looking along x, the front-back centerplane is the one seen edge-on; measuring it draws it and the axis.
    assert drawn({'beam|ptw.centerplane_front_back'}) == (1, 1)
    assert drawn({'other|ptw.centerplane_front_back'}) == (0, 0), "another member's is not this one's"
