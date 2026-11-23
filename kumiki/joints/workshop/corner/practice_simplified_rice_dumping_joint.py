"""Cut a Zongjiao corner with two mitered rails and a locking post."""

from dataclasses import replace

from kumiki.assembly import AssemblyFreedom, Ordering
from kumiki.construction import TriCornerArrangement
from kumiki.csg.cutcsg import (
    CutCSG, CutCSGLabel, Difference, HalfSpace, Intersection, RectangularPrism, SolidUnion, adopt_csg,
)
from kumiki.rule import (
    Comparison, Direction3D, Numeric, Transform, V2, create_v2, safe_compare, safe_dot_product, safe_normalize_vector,
)
from kumiki.ticket import JointTicket
from kumiki.timber import Cutting, Joint, TimberEnd, compute_timber_orientation
from ..shavings.relief import warn_if_arrangement_timbers_imperfect


def cut_practice_simplified_rice_dumping_joint(
    arrangement: TriCornerArrangement,
    timber1_miter_thickness: Numeric,
    timber_1_tenon_distance_from_outer_faces: Numeric,
    timber_2_tenon_distance_from_outer_face: Numeric,
    tenon_size: V2,
) -> Joint:
    """Fit timber 2's rail tenon into timber 3, then seat both rails on timber 1's post.

    Measure cheek thickness and the post tenon offsets straight in from the post's two
    outside faces. Each post tenon is flush with the inside face toward its rail.
    On timber 2, measure the offset from the outside face opposite the post. Its tenon
    is flush with the inside face toward timber 3. For all tenons, Y is the thickness
    normal to the face used for the offset and X is the width along that face.

    [![Three-way mitered tenon](../../../assets/joint-drawings/rice-dumpling.svg)](../../../assets/joint-drawings/rice-dumpling.svg)
    """
    corner_global = arrangement.locate_outside_corner_global()
    warn_if_arrangement_timbers_imperfect(arrangement)
    post, rail, receiver = arrangement.timber1, arrangement.timber2, arrangement.timber3
    # Corner coordinates increase away from the vertex along rail 2, rail 3 and the post.
    z, x, y = [-timber.get_face_direction_global(end) for timber, end in arrangement.members]
    post_x, post_y = post.get_size_in_direction_3d(x), post.get_size_in_direction_3d(y)
    rail_y, rail_depth = rail.get_size_in_direction_3d(y), rail.get_size_in_direction_3d(z)
    receiver_x = receiver.get_size_in_direction_3d(x)
    receiver_depth = receiver.get_size_in_direction_3d(z)
    depth = max(rail_depth, receiver_depth)

    width, thickness = tenon_size
    cheek = timber1_miter_thickness
    inset = timber_1_tenon_distance_from_outer_faces
    rail_inset = timber_2_tenon_distance_from_outer_face
    short_tip = rail_inset + thickness
    assert width > 0 and thickness > 0, "Tenon size must have positive X and Y dimensions"
    assert cheek > 0 and inset >= cheek, "The post tenons must clear the mitered outer cheeks"
    assert rail_inset > 0 and safe_compare(short_tip, min(rail_depth, receiver_depth), Comparison.LT), (
        "The rail tenon must fit below the top face and leave room for the short post tenon"
    )
    assert safe_compare(inset + thickness, min(post_x - width, post_y - width), Comparison.LE), (
        "Each post tenon must fit on its side of the rail miter"
    )
    assert safe_compare(inset + thickness, min(rail_y, receiver_x), Comparison.LE), (
        "Both post tenons must fit inside their receiving rails"
    )
    assert safe_compare(inset + thickness, rail_y - width, Comparison.LE), (
        "The horizontal rail tenon must clear the long post tenon"
    )
    assert safe_compare(short_tip, rail_y - width, Comparison.LE), (
        "The horizontal rail tenon must clear the mitered peak"
    )

    orientation = compute_timber_orientation(z, x)

    def box(x0: Numeric, x1: Numeric, y0: Numeric, y1: Numeric, z0: Numeric, z1: Numeric,
            label: str) -> RectangularPrism:
        center_global = corner_global + x * ((x0 + x1) / 2) + y * ((y0 + y1) / 2)
        return RectangularPrism(size=create_v2(x1 - x0, y1 - y0), transform=Transform(center_global, orientation),
                                start_distance=z0, end_distance=z1, label=CutCSGLabel(label))

    def plane(normal_global: Direction3D) -> HalfSpace:
        normal_global = safe_normalize_vector(normal_global)
        return HalfSpace(normal=normal_global, offset=safe_dot_product(corner_global, normal_global))

    cheeks = SolidUnion(children=[box(0, cheek, 0, post_y, 0, depth, "x_cheek"),
                                  box(0, post_x, 0, cheek, 0, depth, "y_cheek")])
    peak = Intersection(Intersection(cheeks, plane(z - x)), plane(z - y), label=CutCSGLabel("mitered_peak"))
    long_tenon = box(post_x - width, post_x, inset, inset + thickness, 0, depth, "long_tenon")
    short_tenon = box(inset, inset + thickness, post_y - width, post_y, short_tip, depth, "short_tenon")
    rail_tenon = box(0, rail_y, rail_y - width, rail_y, rail_inset, short_tip, "rail_tenon")

    # Only remove the stock actually occupied by a rail, including on unequal sections.
    rail_stock = box(0, max(post_x, receiver_x), 0, rail_y, 0, rail_depth, "rail_stock")
    receiver_stock = box(0, receiver_x, 0, max(post_y, rail_y), 0, receiver_depth, "receiver_stock")
    post_waste = Difference(SolidUnion([rail_stock, receiver_stock]), [peak, long_tenon, short_tenon])
    rail_miter = Intersection(receiver_stock, plane(y - x), label=CutCSGLabel("miter"))
    receiver_miter = Intersection(rail_stock, plane(x - y), label=CutCSGLabel("miter"))
    long_mortise = replace(long_tenon, label=CutCSGLabel("long_mortise"))
    short_mortise = replace(short_tenon, label=CutCSGLabel("short_mortise"))
    rail_waste = SolidUnion([Difference(rail_miter, [rail_tenon]), peak, long_mortise, short_mortise])
    receiver_waste = SolidUnion([receiver_miter, peak, long_mortise, short_mortise,
                                 replace(rail_tenon, label=CutCSGLabel("rail_mortise"))])

    def cut(index: int, waste_global: CutCSG, label: str, freedom: AssemblyFreedom | None,
            suborder: int = 0) -> Cutting:
        timber, end = arrangement.members[index]
        at_corner = timber.transform.global_to_local(corner_global)[2]
        return Cutting(timber=timber, negative_csg=adopt_csg(None, timber.transform, waste_global),
                       maybe_top_end_cut_distance_from_bottom=at_corner if end == TimberEnd.TOP else None,
                       maybe_bottom_end_cut_distance_from_bottom=at_corner if end == TimberEnd.BOTTOM else None,
                       assembly_freedom=freedom, assembly_ordering=Ordering(0, suborder), label=CutCSGLabel(label))

    return Joint(cuttings={
        "timber1": cut(0, post_waste, "post_shoulders", AssemblyFreedom.translation(z, depth), -1),
        "timber2": cut(1, rail_waste, "tenoned_rail", AssemblyFreedom.translation(x, rail_y)),
        "timber3": cut(2, receiver_waste, "mortised_rail", None),
    }, ticket=JointTicket(joint_type="practice_simplified_rice_dumping"))


cut_简化粽角榫 = cut_practice_simplified_rice_dumping_joint
