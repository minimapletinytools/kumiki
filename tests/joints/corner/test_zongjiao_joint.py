from dataclasses import replace
from itertools import combinations

import numpy as np
import pytest
from manifold3d import Manifold, Mesh64

from kumiki import (
    CutTimber, Frame, Orientation, TimberEnd, Transform, TriCornerArrangement,
    create_timber, create_v2, create_v3, cut_basic_practice_simplified_rice_dumping_joint,
    cut_practice_simplified_rice_dumping_joint, cut_简化粽角榫,
    degrees, inches, solve_frame_assembly,
)
from kumiki.example_shavings import create_canonical_example_tri_corner_timbers
from kumiki.kigumi_at_home import RenderMode, _cut_timber_to_trimesh


@pytest.mark.parametrize("hand", [1, -1])
def test_zongjiao_layout_on_unequal_rotated_timbers(hand):
    placement = Transform(create_v3(3, -2, 1), Orientation.from_axis_angle(create_v3(1, 2, 3), degrees(32)))
    x, y, z = create_v3(1, 0, 0), create_v3(0, hand, 0), create_v3(0, 0, 1)
    axes = [z, x, y]
    ends = [TimberEnd.TOP, TimberEnd.BOTTOM, TimberEnd.TOP]
    sizes = [(5, 4), (4.5, 4), (4.25, 5.5)]
    timbers = []
    for i, ((width, height), end) in enumerate(zip(sizes, ends)):
        across, inward = axes[(i + 1) % 3], axes[(i + 2) % 3]
        bottom = across * (width / 2) + inward * (height / 2) + axes[i] * (12 if end == TimberEnd.TOP else -1)
        timber = create_timber(13, create_v2(width, height), bottom,
                               -axes[i] if end == TimberEnd.TOP else axes[i], across, f"timber{i + 1}")
        timbers.append(replace(timber, transform=placement * timber.transform))

    arrangement = TriCornerArrangement(*timbers, *ends)
    assert cut_简化粽角榫 is cut_practice_simplified_rice_dumping_joint
    joint = cut_简化粽角榫(arrangement, 0.4, 0.7, 0.8, create_v2(1, 0.5))
    assert set(joint.cuttings) == {"timber1", "timber2", "timber3"}
    solids = []
    for i, timber in enumerate(timbers):
        cutting = joint.cuttings[f"timber{i + 1}"]
        assert cutting.timber is timber
        if ends[i] == TimberEnd.TOP:
            assert cutting.maybe_top_end_cut_distance_from_bottom == pytest.approx(12)
        else:
            assert cutting.maybe_bottom_end_cut_distance_from_bottom == pytest.approx(1)
        solids.append(CutTimber(timber, cuts=[cutting]).render_timber_with_cuts_csg_local())

    # Coordinates run along the tenoned rail, the receiving rail and the post from the outside corner.
    for px, py, pz, owner in [
        (4.9, 0.75, 0.05, 0), (4.1, 1.15, 0.05, 0),  # long tenon reaches the upper face
        (3.9, 1, 0.05, 1), (4.5, 1.25, 0.05, 1),     # wood beside both tenon dimensions
        (0.9, 3.8, 1.35, 0), (0.9, 3.8, 1.25, 1),   # short tenon meets the rail tenon
        (0.05, 3.6, 0.85, 1), (0.05, 4.4, 1.25, 1), # through tenon at the receiver's outer face
        (0.05, 3.4, 0.85, 2), (0.05, 3.6, 0.75, 2), # receiver around the opening
        (0.3, 2, 2.1, 0), (0.5, 2, 2.1, 2),         # cheek thickness at the first skirt
        (2, 0.3, 2.1, 0), (2, 0.5, 2.1, 1),         # cheek thickness at the second skirt
        (2, 0.3, 1.9, 1), (0.3, 2, 1.9, 2),         # rail side of each 45-degree miter
    ]:
        point = placement.local_to_global(x * px + y * py + z * pz)
        assert [i for i, solid in enumerate(solids) if solid.contains_point(
            timbers[i].transform.global_to_local(point))] == [owner]


@pytest.mark.parametrize("rail_depth", [inches(1), inches(2)])
def test_basic_recipe_uses_timber_widths_and_fits_a_shallow_rail(rail_depth):
    arrangement = create_canonical_example_tri_corner_timbers()
    rail = arrangement.timber2
    position = rail.transform.position + create_v3(0, 0, (rail.size[1] - rail_depth) / 2)
    rail = replace(rail, size=create_v2(rail.size[0], rail_depth), transform=replace(rail.transform, position=position))
    joint = cut_basic_practice_simplified_rice_dumping_joint(replace(arrangement, timber2=rail))
    post = arrangement.timber1
    post_solid = CutTimber(post, cuts=[joint.cuttings["timber1"]]).render_timber_with_cuts_csg_local()
    rail_solid = CutTimber(rail, cuts=[joint.cuttings["timber2"]]).render_timber_with_cuts_csg_local()

    # The four-inch post carries a one-inch-wide long tenon at the top of the rail.
    top = create_v3(inches(1) + rail_depth / 16, inches(3.1), -rail_depth / 16)
    assert post_solid.contains_point(post.transform.global_to_local(top))
    assert rail_solid.contains_point(rail.transform.global_to_local(top - create_v3(0, inches(0.2), 0)))

    # The horizontal tenon occupies the depth interval [5/16, 1/2] of the shallower rail.
    for fraction, inside in [(0.30, False), (0.32, True), (0.49, True), (0.51, False)]:
        point = create_v3(inches(3.5), inches(0.1), -rail_depth * fraction)
        assert rail_solid.contains_point(rail.transform.global_to_local(point)) == inside


def test_post_withdraws_before_rail_and_both_paths_clear():
    arrangement = create_canonical_example_tri_corner_timbers()
    frame = Frame.from_joints([cut_basic_practice_simplified_rice_dumping_joint(arrangement)])
    solution = solve_frame_assembly(frame)
    assert solution is not None and solution.failure is None
    post_step, rail_step = solution.steps
    meshes = {ct.timber.ticket.kumiki_id: _cut_timber_to_trimesh(ct, RenderMode.FULL_CUTS) for ct in frame.cut_timbers}
    assert all(mesh.is_volume and len(mesh.split(only_watertight=False)) == 1 for mesh in meshes.values())
    # Three square timbers share one four-inch cube at the corner.
    assert sum(mesh.volume for mesh in meshes.values()) == pytest.approx(448 * inches(1)**3)
    solids = {key: Manifold(Mesh64(vert_properties=np.array(mesh.vertices, dtype=np.float64, order="C"),
                                  tri_verts=np.array(mesh.faces, dtype=np.uint64, order="C"))) for key, mesh in meshes.items()}
    for a, b in combinations(solids.values(), 2):
        assert abs((a ^ b).volume()) < 1e-10
    for step, (timber, end) in zip((post_step, rail_step), arrangement.members):
        primary, = [move for move in step.movements if not move.dragged]
        assert primary.member_key == timber.ticket.kumiki_id
        assert primary.direction.equals(-timber.get_face_direction_global(end))
        for _ in range(64):
            for move in step.movements:
                delta = [v * move.distance / 64 for v in move.direction]
                solids[move.member_key] = solids[move.member_key].translate(delta)
            for a, b in combinations(solids.values(), 2):
                assert abs((a ^ b).volume()) < 1e-10


def test_rejects_misaligned_or_displaced_outside_edges():
    arrangement = create_canonical_example_tri_corner_timbers()
    with pytest.raises(AssertionError, match="perpendicular"):
        cut_basic_practice_simplified_rice_dumping_joint(replace(arrangement, timber3=arrangement.timber2))

    timber = arrangement.timber2
    roll = Transform(create_v3(0, 0, 0), Orientation.from_axis_angle(create_v3(0, 0, 1), degrees(15)))
    with pytest.raises(AssertionError, match="face-aligned"):
        cut_basic_practice_simplified_rice_dumping_joint(replace(arrangement, timber2=replace(timber, transform=timber.transform * roll)))

    shifted = replace(timber.transform, position=timber.transform.position + create_v3(inches(1), 0, 0))
    with pytest.raises(AssertionError, match="Outside long edges"):
        cut_basic_practice_simplified_rice_dumping_joint(replace(arrangement, timber2=replace(timber, transform=shifted)))
