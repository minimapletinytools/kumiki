"""STL stock geometry and safe placement configuration edits."""
import ast
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
import trimesh

from kumiki import (Cutting, CutTimber, HalfSpace, STLPlacement, STLTimber, TriangleSolid,
                    Transform, create_stl_timber, create_timber, create_v2, create_v3)
from kumiki.csg.cutcsg import adopt_csg
from kumiki.csg.triangles import triangulate_cutcsg
from kumiki.stl import _source_call, load_stl


def reference():
    return create_timber(length=1, size=create_v2(.2, .2), bottom_position=create_v3(2, 3, 4),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0))


@pytest.fixture
def stl(tmp_path):
    path = tmp_path / 'block.stl'
    mesh = trimesh.creation.box(extents=[100, 200, 300])
    mesh.export(path)
    return path


def test_placeholder_keeps_reference_and_placed_mesh_accepts_joinery(stl):
    placeholder = create_stl_timber(reference(), stl)
    assert placeholder.needs_stl_placement
    assert triangulate_cutcsg(CutTimber(placeholder, cuts=[]).render_timber_with_cuts_csg_local()).mesh.volume == pytest.approx(.04)
    placed = create_stl_timber(reference(), stl, placement={'translation': [0, 0, .15]})
    assert not placed.needs_stl_placement
    assert not placed.can_be_extended_for_joints()
    cut = Cutting(placed, negative_csg=HalfSpace(normal=create_v3(0, 0, 1), offset=.15))
    solid = CutTimber(placed, cuts=[cut]).render_timber_with_cuts_csg_local()
    mesh = triangulate_cutcsg(solid).mesh
    assert mesh.is_volume
    assert mesh.volume == pytest.approx(.003)
    assert solid.contains_point(create_v3(0, 0, .05))
    assert not solid.contains_point(create_v3(0, 0, .25))


def test_stl_transform_units_and_world_adoption(stl):
    timber = create_stl_timber(reference(), stl, placement={'rotation': [0, 0, 90], 'scale': [2, 1, 1], 'translation': [.3, .4, .5]})
    solid = timber.get_actual_csg_local()
    bounds = triangulate_cutcsg(solid).mesh.bounds
    np.testing.assert_allclose(bounds, [[.2, .3, .35], [.4, .5, .65]], atol=1e-8)
    world = adopt_csg(timber.transform, Transform.identity(), solid)
    assert world.contains_point(create_v3(2.3, 3.4, 4.5))
    assert world.is_point_on_boundary(create_v3(2.4, 3.4, 4.5))
    assert not world.contains_point(create_v3(5, 5, 5))


@pytest.mark.parametrize('value', [{'scale': [0, 1, 1]}, {'rotation': [float('nan'), 0, 0]}, {'translation': [1, 2]}])
def test_invalid_placement_is_rejected(value):
    with pytest.raises(ValueError):
        STLPlacement(**value)


def test_open_stl_is_rejected(tmp_path):
    mesh = trimesh.creation.box()
    mesh.update_faces(np.arange(len(mesh.faces) - 1))
    path = tmp_path / 'open.stl'; mesh.export(path)
    with pytest.raises(ValueError, match='watertight'):
        load_stl(path, 'm')


def prepare_edit(*args, **kwargs):
    spec = importlib.util.spec_from_file_location('stl_placement_test', Path(__file__).parents[1] / 'kigumi/stl_placement.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.prepare_edit(*args, **kwargs)


@pytest.mark.parametrize('call', [
    'create_stl_timber(ref, "block.stl")',
    'create_stl_timber(ref, "block.stl", placement=None)',
    'create_stl_timber(ref, "block.stl",\n    # keep this note\n)',
])
def test_source_edit_preserves_other_text_and_refuses_stale_or_shared_calls(tmp_path, stl, call):
    path = tmp_path / 'example.py'
    original = '# 日本語 remains\nleg = ' + call + '\n'
    path.write_text(original)
    source = _source_call(path, 2)
    assert source is not None
    timber = replace(create_stl_timber(reference(), stl), source=source)
    edit = prepare_edit(timber, {'translation': [1, 2, 3]}, tmp_path)
    assert path.read_text() == original
    assert '# 日本語 remains' in edit['updated']
    tree = ast.parse(edit['updated'])
    created = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    value = ast.literal_eval(next(k.value for k in created.keywords if k.arg == 'placement'))
    assert value['translation'] == [1, 2, 3]
    with pytest.raises(ValueError, match='more than one'):
        prepare_edit(timber, {}, tmp_path, 2)
    path.write_text(original + '# changed\n')
    with pytest.raises(ValueError, match='changed'):
        prepare_edit(timber, {}, tmp_path)


def test_generated_cabriole_examples_build():
    from patterns.structures.cabriole_table import cabriole_table, cabriole_placement
    table = cabriole_table()
    assert len(table.cut_timbers) == 5
    assert table.source_joints is not None and len(table.source_joints) == 4
    legs = [cut for cut in table.cut_timbers if isinstance(cut.timber, STLTimber)]
    timbers = [leg.timber for leg in legs]
    assert all(isinstance(timber, STLTimber) for timber in timbers)
    sources = [getattr(timber, "source") for timber in timbers]
    assert all(source is not None for source in sources)
    assert len({source.line for source in sources}) == 4
    assert all(triangulate_cutcsg(leg.timber.get_actual_csg_local()).mesh.is_volume for leg in legs)
    for leg in legs:
        solid = leg.render_timber_with_cuts_csg_local()
        assert solid.contains_point(create_v3(0, 0, .71))
        assert not solid.contains_point(create_v3(.025, 0, .71))
        assert triangulate_cutcsg(solid).mesh.is_volume
    top = next(cut for cut in table.cut_timbers if not isinstance(cut.timber, STLTimber))
    solid = top.render_timber_with_cuts_csg_local()
    # Top local X is world Y, local Y is world Z, local Z is world X.
    assert not solid.contains_point(create_v3(-.25, -.0075, .1))
    assert solid.contains_point(create_v3(-.25, .0125, .1))
    placeholder = cabriole_placement().cut_timbers[0].timber
    assert isinstance(placeholder, STLTimber) and placeholder.needs_stl_placement


def test_runner_placement_protocol_and_placeholder_tree(tmp_path, stl, monkeypatch):
    from tests.test_kigumi_kiwari_protocol import runner
    from kumiki import Frame
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / 'kigumi'))
    source_path = tmp_path / 'frame.py'
    source_path.write_text('leg = create_stl_timber(ref, "block.stl")\n')
    timber = replace(create_stl_timber(reference(), stl), source=_source_call(source_path, 1))
    frame = Frame.from_joints([], additional_unjointed_timbers=[timber])
    slot = runner.SlotState(file_path=source_path, module=None, frame=frame)
    state = runner.RunnerState(slots={'main': slot})
    entries, _ = runner._assign_member_keys(frame)
    member_key = entries[0]['memberKey']
    monkeypatch.setattr(runner, '_project_root', tmp_path)
    request = {'id': 'stl', 'command': 'get_stl_placement', 'payload': {'slot': 'main', 'memberKey': member_key}}
    _, response, _ = runner.handle_request(state, request)
    assert response['ok']
    assert response['result']['size'] == [.2, .2, 1.0]
    assert len(response['result']['faces']) == 12
    _, response, _ = runner.handle_request(state, {**request, 'command': 'prepare_stl_placement', 'payload': {**request['payload'], 'placement': {}}})
    assert 'placement=' in response['result']['updated']
    assert 'placement=' not in source_path.read_text()


def test_source_edit_preserves_windows_line_endings_and_refuses_indirect_calls(tmp_path, stl):
    path = tmp_path / 'frame.py'
    original = 'leg = create_stl_timber(\r\n    ref, "block.stl",\r\n)\r\n'
    path.write_bytes(original.encode())
    timber = replace(create_stl_timber(reference(), stl), source=_source_call(path, 2))
    edit = prepare_edit(timber, {}, tmp_path)
    assert edit['expected'] == original
    assert edit['updated'].count('\r\n') == 3
    with pytest.raises(ValueError, match='outside'):
        prepare_edit(timber, {}, tmp_path / 'elsewhere')
    path.write_text('leg = create_stl_timber(ref, "block.stl", **options)\n')
    timber = replace(timber, source=_source_call(path, 1))
    with pytest.raises(ValueError, match='kwargs'):
        prepare_edit(timber, {}, tmp_path)
    with pytest.raises(ValueError, match='missing'):
        prepare_edit(replace(timber, source=None), {}, tmp_path)


def test_mesh_end_cuts_trim_stock_without_extending_it(stl):
    timber = create_stl_timber(reference(), stl, placement={'translation': [0, 0, .15]})
    trimmed = CutTimber(timber, cuts=[Cutting(timber, maybe_top_end_cut_distance_from_bottom=.2)])
    mesh = triangulate_cutcsg(trimmed.render_timber_with_cuts_csg_local()).mesh
    assert mesh.volume == pytest.approx(.004)
    beyond = CutTimber(timber, cuts=[Cutting(timber, maybe_top_end_cut_distance_from_bottom=2)])
    mesh = triangulate_cutcsg(beyond.render_timber_with_cuts_csg_local()).mesh
    assert mesh.volume == pytest.approx(.006)
    assert mesh.bounds[1, 2] == pytest.approx(.3)


def test_mesh_boundary_search_matches_full_triangle_search(monkeypatch):
    mesh = trimesh.creation.icosphere(subdivisions=4)
    solid = TriangleSolid(tuple(map(tuple, mesh.vertices)), tuple(map(tuple, mesh.faces)))
    points = np.vstack([mesh.triangles_center[::257], [[0, 0, 0], [2, 3, 4]]])
    expected = trimesh.proximity.closest_point_naive(mesh, points)[1]
    for point, distance in zip(points, expected):
        actual, index = solid._nearest(create_v3(*point))
        assert actual == pytest.approx(distance, abs=1e-12)
        assert index >= 0
        assert solid.is_point_on_boundary(create_v3(*point)) == (distance <= 1e-8)

    examined = 0
    closest_point = trimesh.triangles.closest_point

    def counted(triangles, points):
        nonlocal examined
        examined += len(triangles)
        return closest_point(triangles, points)

    monkeypatch.setattr(trimesh.triangles, 'closest_point', counted)
    assert solid.is_point_on_boundary(create_v3(*mesh.triangles_center[100]))
    assert examined < len(mesh.faces) // 10


def test_curved_mesh_pick_highlight_uses_local_triangle_search(monkeypatch):
    from kumiki.viewer.picking import extract_highlight_mesh
    from kumiki.viewer.rule_at_home import LocalFrame

    mesh = trimesh.creation.icosphere(subdivisions=3)
    solid = TriangleSolid(tuple(map(tuple, mesh.vertices)), tuple(map(tuple, mesh.faces)))
    examined = 0
    closest_point = trimesh.triangles.closest_point

    def counted(triangles, points):
        nonlocal examined
        examined += len(triangles)
        return closest_point(triangles, points)

    monkeypatch.setattr(trimesh.triangles, 'closest_point', counted)
    _, _, matched, total = extract_highlight_mesh(
        mesh.vertices.ravel().tolist(), mesh.faces.ravel().tolist(),
        solid, LocalFrame.of(Transform.identity()))
    assert matched == total == len(mesh.faces)
    assert examined < total * total // 10
