from dataclasses import replace

import pytest

from kumiki import (
    CutTimber, Orientation, TimberEnd, Transform, TriCornerArrangement,
    create_timber, create_v2, create_v3, cut_basic_mitsudomoe_joint, cut_mitsudomoe_joint,
    cut_rock_paper_scissor_joint_on_face_aligned_timbers, degrees, inches,
)
from kumiki.example_shavings import create_canonical_example_tri_corner_timbers


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("edge_position, expected_edge", [(None, 6), (4, 4)])
def test_cyclic_miters_tenons_and_mortises(mirrored, edge_position, expected_edge):
    placement = Transform(create_v3(7, -3, 2), Orientation.from_axis_angle(create_v3(1, 2, 3), degrees(37)))
    axes = [create_v3(1, 0, 0), create_v3(0, 1, 0), create_v3(0, 0, -1 if mirrored else 1)]
    ends = [TimberEnd.BOTTOM, TimberEnd.TOP, TimberEnd.BOTTOM]
    timbers = []
    for i, end in enumerate(ends):
        width, height = axes[(i + 1) % 3], axes[(i + 2) % 3]
        # Use unequal stock and move the rough ends away from the finished corner.
        size = create_v2(10 - 2*i, 8 + 2*i)
        bottom = width * (size[0]/2) + height * (size[1]/2) + axes[i] * (13 if end == TimberEnd.TOP else -2)
        timber = create_timber(15, size, bottom,
                               -axes[i] if end == TimberEnd.TOP else axes[i], width, f"member{i}")
        timbers.append(replace(timber, transform=placement * timber.transform))

    arrangement = TriCornerArrangement(*timbers, *ends)
    assert arrangement.locate_outside_corner_global().equals(placement.position)
    assert cut_mitsudomoe_joint is cut_rock_paper_scissor_joint_on_face_aligned_timbers
    joint = cut_mitsudomoe_joint(
        arrangement, tenon_position_from_outer_face=0.75, tenon_width=1.25, tenon_height=1,
        tenon_length=1, mortise_extra_depth=0.5, tenon_position_from_outer_edge=edge_position,
    )
    assert set(joint.cuttings) == {"timber1", "timber2", "timber3"}
    assert not joint.jointAccessories
    solids = []
    for i, (timber, end) in enumerate(arrangement.members):
        cutting = joint.cuttings[f"timber{i + 1}"]
        assert cutting.timber is timber
        if end == TimberEnd.TOP:
            assert cutting.maybe_top_end_cut_distance_from_bottom == pytest.approx(13)
            assert cutting.maybe_bottom_end_cut_distance_from_bottom is None
        else:
            assert cutting.maybe_bottom_end_cut_distance_from_bottom == pytest.approx(2)
            assert cutting.maybe_top_end_cut_distance_from_bottom is None
        solids.append(CutTimber(timber, cuts=[cutting]).render_timber_with_cuts_csg_local())

    for i in range(3):
        receiver, third = (i + 1) % 3, (i + 2) % 3
        middle = expected_edge - 0.5
        # Coordinates run along donor grain, receiver grain, then inward from their shared face.
        for x, y, z, owners in [
            (middle + 0.2, middle, 1, [i]),          # donor behind the miter
            (middle - 0.9, middle, 1, [i]),          # tenon near its tip
            (middle - 1.1, middle, 1, []),           # clearance beyond the tip
            (middle - 1.6, middle, 1, [receiver]),   # wood beyond the mortise floor
            (middle - 1, middle - 0.6, 1, [receiver]),  # beyond the tenon height
            (middle - 0.2, middle + 0.6, 1, [receiver]),  # past the edge position
            (middle - 0.9, middle, 0.7, [receiver]),  # wood toward the shared outer face
            (middle - 0.9, middle, 1.95, [i]),        # inside the far side of the tenon
            (middle - 0.9, middle, 2.05, [receiver]), # wood beyond the tenon width
            (1, middle, middle + 1, [third]),         # across the second miter
            (-0.1, 0.5, 0.2, []),                    # beyond the shared end
        ]:
            point = placement.local_to_global(axes[i]*x + axes[receiver]*y + axes[third]*z)
            assert [j for j, solid in enumerate(solids)
                    if solid.contains_point(timbers[j].transform.global_to_local(point))] == owners

    assert len(cut_basic_mitsudomoe_joint(arrangement).cuttings) == 3


def test_requires_three_perpendicular_face_aligned_timbers_with_coincident_outside_edges():
    arrangement = create_canonical_example_tri_corner_timbers()
    with pytest.raises(AssertionError, match="perpendicular"):
        cut_basic_mitsudomoe_joint(replace(arrangement, timber3=arrangement.timber1))

    timber = arrangement.timber3
    rotated = timber.transform * Transform(create_v3(0, 0, 0),
                                            Orientation.from_axis_angle(create_v3(0, 0, 1), degrees(15)))
    with pytest.raises(AssertionError, match="face-aligned"):
        cut_basic_mitsudomoe_joint(replace(arrangement, timber3=replace(timber, transform=rotated)))

    shifted = replace(timber.transform, position=timber.transform.position + create_v3(inches(1), 0, 0))
    with pytest.raises(AssertionError, match="Outside long edges"):
        cut_basic_mitsudomoe_joint(replace(arrangement, timber3=replace(timber, transform=shifted)))


@pytest.mark.parametrize("position", [inches(3), inches(3.25)])
def test_tenon_width_must_leave_wood_beyond_outer_face_offset(position):
    arrangement = create_canonical_example_tri_corner_timbers()
    with pytest.raises(AssertionError, match="greater than tenon_position_from_outer_face"):
        cut_mitsudomoe_joint(arrangement, position, inches(1), inches(0.5), inches(1), 0)


@pytest.mark.parametrize("extra_depth", [0, inches(1, 8)])
def test_each_finished_timber_mesh_is_one_solid(extra_depth):
    from kumiki.csg.triangles import triangulate_cutcsg

    joint = cut_mitsudomoe_joint(create_canonical_example_tri_corner_timbers(),
                                inches(2), inches(1), inches(1), inches(1), extra_depth)
    for cutting in joint.cuttings.values():
        cut = CutTimber(cutting.timber, cuts=[cutting])
        mesh = triangulate_cutcsg(cut.render_timber_with_cuts_csg_local()).mesh
        assert mesh.is_volume
        assert len(mesh.split(only_watertight=False)) == 1
        # The miter owns a third of the shared cube. Only the mortise clearance costs volume.
        side = inches(4)
        expected = side**2 * (inches(12) - side) + side**3 / 3 - inches(1)**2 * extra_depth
        assert mesh.volume == pytest.approx(expected)
