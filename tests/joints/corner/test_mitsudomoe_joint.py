from dataclasses import replace

import pytest

from kumiki import (
    CutTimber, Orientation, TimberEnd, Transform, TriCornerArrangement,
    create_timber, create_v2, create_v3, cut_basic_mitsudomoe_joint, cut_mitsudomoe_joint,
    cut_rock_paper_scissor_joint_on_face_aligned_timbers, degrees, inches,
)
from kumiki.example_shavings import create_canonical_example_tri_corner_timbers


@pytest.mark.parametrize("mirrored", [False, True])
def test_cyclic_miters_tenons_and_mortises(mirrored):
    placement = Transform(create_v3(7, -3, 2), Orientation.from_axis_angle(create_v3(1, 2, 3), degrees(37)))
    axes = [create_v3(1, 0, 0), create_v3(0, 1, 0), create_v3(0, 0, -1 if mirrored else 1)]
    ends = [TimberEnd.BOTTOM, TimberEnd.TOP, TimberEnd.BOTTOM]
    timbers = []
    for i, end in enumerate(ends):
        width, height = axes[(i + 1) % 3], axes[(i + 2) % 3]
        # Use unequal stock and move the rough ends away from the finished corner.
        bottom = width * (3 + i) + height * (4 + i) + axes[i] * (13 if end == TimberEnd.TOP else -2)
        timber = create_timber(15, create_v2(6 + 2*i, 8 + 2*i), bottom,
                               -axes[i] if end == TimberEnd.TOP else axes[i], width, f"member{i}")
        timbers.append(replace(timber, transform=placement * timber.transform))

    arrangement = TriCornerArrangement(*timbers, *ends)
    assert arrangement.locate_outside_corner_global().equals(placement.position)
    assert cut_mitsudomoe_joint is cut_rock_paper_scissor_joint_on_face_aligned_timbers
    joint = cut_mitsudomoe_joint(arrangement, tenon_position_from_outside=2, tenon_width=1,
                                tenon_height=1, tenon_length=1, mortise_extra_depth=0.5)
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
        # Coordinates are along donor grain, receiver grain, then inward from the outside face.
        for x, y, z, owners in [
            (2.7, 2.5, 0.4, [i]),         # donor behind the miter
            (1.6, 2.5, 0.4, [i]),         # tenon near its tip
            (1.4, 2.5, 0.4, []),          # clearance beyond the tip
            (0.9, 2.5, 0.4, [receiver]),  # wood beyond the mortise floor
            (1.5, 1.9, 0.4, [receiver]),  # outside the near side
            (2.5, 3.1, 0.4, [receiver]),  # outside the far side
            (1.7, 2.5, 1.1, [receiver]),  # below the tenon
            (1.7, 2.5, 3.2, [third]),     # across the second miter
            (-0.1, 0.5, 0.2, []),        # beyond the shared end
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
