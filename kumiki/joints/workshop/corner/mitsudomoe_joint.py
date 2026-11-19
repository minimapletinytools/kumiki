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
    tenon_position_from_outer_face: Numeric,
    tenon_width: Numeric,
    tenon_height: Numeric,
    tenon_length: Numeric,
    mortise_extra_depth: Numeric,
    tenon_position_from_outer_edge: Numeric | None = None,
) -> Joint:
    """Cut three 45° miters and fit each timber's tenon into the next timber in order.

    Start on the outside seam where the donor and receiver meet. The distance from
    the common corner to this mark, projected along the receiver's grain, is
    `tenon_position_from_outer_edge`. None uses the smallest cross-section dimension
    of the three timbers. Lay out height from the mark back toward the corner.
    Inset the tenon by `tenon_position_from_outer_face` from the pair's shared outside
    face and measure width farther inward.
    Measure length from the miter along the donor's grain toward its joint end.
    The mortise extends another `mortise_extra_depth` in that direction.
    """
    corner_global = arrangement.locate_outside_corner_global()
    warn_if_arrangement_timbers_imperfect(arrangement)
    members = arrangement.members
    axes_global = [-timber.get_face_direction_global(end) for timber, end in members]
    smallest_side = min(min(timber.size) for timber, _ in members)
    edge = smallest_side if tenon_position_from_outer_edge is None else tenon_position_from_outer_edge
    near = edge - tenon_height
    face_start = tenon_position_from_outer_face
    face_end = face_start + tenon_width
    assert tenon_width > 0 and tenon_height > 0 and tenon_length > 0, "Tenon dimensions must be positive"
    assert mortise_extra_depth >= 0, "Mortise extra depth must be nonnegative"
    assert face_start >= 0, "Tenon position from outer face must be nonnegative"
    assert safe_compare(face_end, smallest_side, Comparison.LT), (
        "Each timber dimension must be greater than tenon_position_from_outer_face + tenon_width"
    )
    assert safe_compare(edge, smallest_side, Comparison.LE), "Tenon position from outer edge must fit all mating faces"
    assert safe_compare(face_end, near, Comparison.LE), "Tenon width and height must fit on the donor-receiver miter"
    assert safe_compare(tenon_length, near, Comparison.LE), "Tenon length must fit before the outside face"

    def tongue_profile(donor: int, stock: TimberLike, depth: Numeric, label: str) -> ConvexPolygonExtrusion:
        """Extrude the tongue profile across its width in stock-local space."""
        along_global = axes_global[donor]
        across_global = axes_global[(donor + 1) % 3]
        normal_global = cross_product(along_global, across_global)
        inward_sign = safe_dot_product(normal_global, axes_global[(donor + 2) % 3])
        caps = (inward_sign * face_start, inward_sign * face_end)
        profile_global = Transform(corner_global, compute_timber_orientation(normal_global, along_global))
        return ConvexPolygonExtrusion(
            # Carry the root behind the miter to the cross-section at the far edge.
            points=[create_v2(edge, near), create_v2(edge, edge),
                    create_v2(edge - depth, edge), create_v2(near - depth, near)],
            transform=profile_global.to_local_transform(stock.transform),
            start_distance=min(caps), end_distance=max(caps),
            label=CutCSGLabel(label),
        )

    cuttings = {}
    for i, (timber, end) in enumerate(members):
        following = (i + 1) % 3
        previous = (i - 1) % 3
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
