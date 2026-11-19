"""Cut a three-way miter with cyclic tenons."""

from kumiki.construction import TriCornerArrangement
from kumiki.csg.cutcsg import ConvexPolygonExtrusion, CutCSGLabel, Difference, HalfSpace, SolidUnion
from kumiki.rule import (
    Comparison, Direction3D, Numeric, Transform, create_v2, cross_product,
    safe_compare, safe_dot_product, safe_normalize_vector,
)
from kumiki.ticket import JointTicket
from kumiki.timber import Cutting, Joint, TimberEnd, TimberLike, compute_timber_orientation
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


def cut_rock_paper_scissor_joint_on_face_aligned_timbers(
    arrangement: TriCornerArrangement,
    tenon_position_from_outside: Numeric,
    tenon_width: Numeric,
    tenon_height: Numeric,
    tenon_length: Numeric,
    mortise_extra_depth: Numeric,
) -> Joint:
    """Cut three 45° miters and fit each timber's tenon into the next timber in order.

    Measure position and width from the donor's outside long edge along the receiving
    timber's axis, away from the corner. Measure height inward from their common outside
    face. Measure length from the miter along the donor's grain toward its joint end.
    The mortise extends another `mortise_extra_depth` in that direction.
    """
    corner_global = arrangement.locate_outside_corner_global()
    warn_if_arrangement_timbers_imperfect(arrangement)
    members = arrangement.members
    axes_global = [-timber.get_face_direction_global(end) for timber, end in members]
    near = tenon_position_from_outside
    far = near + tenon_width
    assert tenon_width > 0 and tenon_height > 0 and tenon_length > 0, "Tenon dimensions must be positive"
    assert mortise_extra_depth >= 0, "Mortise extra depth must be nonnegative"
    assert safe_compare(tenon_height, near, Comparison.LE), "Tenon height must fit on the donor-receiver miter"
    assert safe_compare(tenon_length, near, Comparison.LE), "Tenon length must fit before the outside face"

    def tongue_profile(donor: int, stock: TimberLike, depth: Numeric, label: str) -> ConvexPolygonExtrusion:
        """Extrude the tongue profile through the tenon height in stock-local space."""
        along_global = axes_global[donor]
        across_global = axes_global[(donor + 1) % 3]
        normal_global = cross_product(along_global, across_global)
        height = tenon_height * safe_dot_product(normal_global, axes_global[(donor + 2) % 3])
        profile_global = Transform(corner_global, compute_timber_orientation(normal_global, along_global))
        return ConvexPolygonExtrusion(
            # Carry the root behind the miter to the cross-section at the far edge.
            points=[create_v2(far, near), create_v2(far, far),
                    create_v2(far - depth, far), create_v2(near - depth, near)],
            transform=profile_global.to_local_transform(stock.transform),
            start_distance=min(0, height), end_distance=max(0, height),
            label=CutCSGLabel(label),
        )

    cuttings = {}
    for i, (timber, end) in enumerate(members):
        following = (i + 1) % 3
        previous = (i - 1) % 3
        receiver = members[following][0]
        miter_width = min(timber.get_size_in_direction_3d(axes_global[following]),
                          receiver.get_size_in_direction_3d(axes_global[i]))
        assert safe_compare(far, miter_width, Comparison.LE), "Tenon width and position must fit the mating faces"

        corner_local = timber.transform.global_to_local(corner_global)

        def miter_plane(neighbor_global: Direction3D, label: str) -> HalfSpace:
            normal_global = safe_normalize_vector(neighbor_global - axes_global[i])
            normal_local = timber.transform.global_to_local_direction(normal_global)
            return HalfSpace(normal=normal_local, offset=safe_dot_product(corner_local, normal_local),
                             label=CutCSGLabel(label))

        tenon = tongue_profile(i, timber, tenon_length, "tenon")
        mortise = tongue_profile(previous, timber, tenon_length + mortise_extra_depth, "mortise")
        waste = SolidUnion(children=[miter_plane(axes_global[following], "outgoing_miter"),
                                     miter_plane(axes_global[previous], "incoming_miter"), mortise])
        cuttings[f"timber{i + 1}"] = Cutting(
            timber=timber,
            negative_csg=Difference(base=waste, subtract=[tenon], label=CutCSGLabel("miter_waste")),
            maybe_top_end_cut_distance_from_bottom=corner_local[2] if end == TimberEnd.TOP else None,
            maybe_bottom_end_cut_distance_from_bottom=corner_local[2] if end == TimberEnd.BOTTOM else None,
            label=CutCSGLabel("miter_and_mortise"),
        )
    return Joint(cuttings=cuttings, ticket=JointTicket(joint_type="mitsudomoe"))


cut_mitsudomoe_joint = cut_rock_paper_scissor_joint_on_face_aligned_timbers
