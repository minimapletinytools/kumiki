import math

import numpy as np
import pytest

from kumiki import CutTimber, Timber, TimberFeature, TimberTicket, Transform, create_v2, create_v3
from kumiki.csg.cutcsg import Cylinder, Difference, RectangularPrism
from kumiki.csg.pathcsg import ArcSegment, FancyPath, PathExtrusion, StraightSegment
from kumiki.drawings.drawing_solid import DrawingSolid
from kumiki.drawings.svg import DrawingStyles, render_svg_view
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


def test_reference_arris_centerline_ptw_and_two_independently_colored_faces():
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
    tinted = _view(members, right, (0, 0, 1), DrawingStyles(reference_faces=True))
    fills = tinted.findall(".//{*}g[@class='face-fills']/{*}path")
    assert {p.get('data-feature') for p in fills} == {face.name for face in edge.long_faces_it_rests_on()}
    assert len({p.get('fill') for p in fills}) == 2
