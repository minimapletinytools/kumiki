"""Lay out a wedge, saw kerf and flared mortise in the tenon's shoulder frame."""

from dataclasses import dataclass, replace
from enum import Enum
from math import isfinite

from kumiki.csg.cutcsg import (CutCSG, CutCSGLabel, FeatureOverride, FeatureProperties,
                               HalfSpace, HALF_SPACE_PLANE, Intersection, PlaneFeature,
                               RectangularPrism, measured_against)
from kumiki.rule import (Numeric, Orientation, Transform, V2, V3, cos, create_v2, create_v3,
                         degrees, pi, safe_dot_product, safe_normalize_vector, sin, tan)
from kumiki.timber import AssemblyFreedom, Ordering, Wedge


class WedgeOrientation(Enum):
    SPREAD_X = "spread_x"
    SPREAD_Y = "spread_y"


@dataclass(frozen=True)
class WedgeParameters:
    """Place one wedge from the tenon tip toward its shoulder.

    wedge_position is signed from the tenon center along the timber's X or Y axis.
    wedge_angle is the included angle in radians. mortise_side_angle is the outward
    angle per spread wall from shoulder to mortise bottom. tenon_kerf_size is the
    saw cut width. Zero leaves only the layout datums. A longer wedge projects past
    the tenon tip by its excess length.
    """
    wedge_orientation: WedgeOrientation = WedgeOrientation.SPREAD_X
    wedge_position: Numeric = 0
    wedge_length: Numeric | None = None
    wedge_angle: Numeric = degrees(5)
    mortise_side_angle: Numeric = 0
    tenon_kerf_size: Numeric = 0


@dataclass(frozen=True)
class TenonWedgeLayout:
    accessory: Wedge
    kerf_global: RectangularPrism | None
    kerf_datums: tuple[PlaneFeature, PlaneFeature]


def lay_out_tenon_wedge(params: WedgeParameters, shoulder_global: Transform, size: V2,
                        tenon_length: Numeric, mortise_depth: Numeric | None,
                        spread_global: V3) -> TenonWedgeLayout:
    """Place the wedge and kerf from the shoulder, using the timber's positive spread direction."""
    length = tenon_length if params.wedge_length is None else params.wedge_length
    kerf = params.tenon_kerf_size
    if not isinstance(params.wedge_orientation, WedgeOrientation):
        raise ValueError("wedge_orientation must be SPREAD_X or SPREAD_Y")
    if not (isfinite(length) and isfinite(tenon_length) and min(length, tenon_length) > 0):
        raise ValueError("wedge_length and tenon_length must be positive and finite")
    if not 0 < params.wedge_angle < pi or not 0 <= params.mortise_side_angle < pi / 2:
        raise ValueError("wedge_angle must be between 0 and pi and mortise_side_angle in [0, pi/2)")
    if not isfinite(kerf) or kerf < 0 or not isfinite(params.wedge_position):
        raise ValueError("tenon_kerf_size must be nonnegative and wedge_position and kerf size finite")
    if mortise_depth is not None and (not isfinite(mortise_depth) or mortise_depth < max(tenon_length, length)):
        raise ValueError("mortise_depth must accommodate the tenon and seated wedge")

    index = 0 if params.wedge_orientation is WedgeOrientation.SPREAD_X else 1
    depth = min(length, tenon_length)
    root = tenon_length - depth
    taper = tan(params.wedge_angle / 2)
    if abs(params.wedge_position) + max(kerf / 2, depth * taper) >= size[index] / 2:
        raise ValueError("The kerf and inserted wedge must fit between the tenon cheeks")

    outward = shoulder_global.local_to_global_direction(create_v3(0, 0, 1))
    origin = shoulder_global.position + params.wedge_position * spread_global
    across = size[1 - index]
    wedge = Wedge(
        transform=Transform(origin + outward * (root + length), Orientation.from_z_and_x(-outward, spread_global)),
        length=length, base_width=2 * length * taper, tip_width=0, height=across,
        assembly_freedom=AssemblyFreedom.translation(outward, depth) if mortise_depth is None else None,
        assembly_ordering=Ordering(0, -1) if mortise_depth is None else Ordering(),
    )
    slot = RectangularPrism(
        size=create_v2(kerf, across), transform=Transform(origin, Orientation.from_z_and_x(outward, spread_global)),
        start_distance=root, end_distance=tenon_length, label=CutCSGLabel("tenon_kerf"),
    ) if kerf > 0 else None
    direction = shoulder_global.global_to_local_direction(spread_global)
    return TenonWedgeLayout(wedge, slot, (
        PlaneFeature("kerf_center", normal=(direction[0], direction[1], direction[2]), offset=params.wedge_position),
        PlaneFeature("kerf_root", normal=(0, 0, 1), offset=root),
    ))


def flared_mortise(params: WedgeParameters, size: V2, shoulder_global: Transform, inward_global: V3,
                   start: Numeric, depth: Numeric | None) -> CutCSG:
    """Intersect the four mortise walls with the entry and optional blind bottom.

    Rotate each spread wall about its intersection with the shoulder plane.
    An open-ended cut continues through the receiving timber.
    """
    inward = shoulder_global.global_to_local_direction(inward_global)
    along = create_v3(0, 0, 1)

    def plane(normal: V3, point: V3, name: str, opposite: str | None = None) -> HalfSpace:
        normal_global = shoulder_global.local_to_global_direction(normal)
        props = measured_against(FeatureProperties(), opposite) if opposite else FeatureProperties()
        return HalfSpace(normal=normal_global, offset=safe_dot_product(normal_global, shoulder_global.local_to_global(point)),
                         feature_overrides=[FeatureOverride(HALF_SPACE_PLANE, name, props)])

    cut: CutCSG = plane(along, start * along, "mortise_entry")
    if depth is not None:
        cut = Intersection(cut, plane(-along, depth * along, "mortise_bottom"))
    spread = 0 if params.wedge_orientation is WedgeOrientation.SPREAD_X else 1
    for index, (axis, positive, negative) in enumerate((
        (create_v3(1, 0, 0), "mortise_right", "mortise_left"),
        (create_v3(0, 1, 0), "mortise_front", "mortise_back"),
    )):
        for sign, name, opposite in ((1, positive, negative), (-1, negative, positive)):
            normal = -sign * axis
            point = sign * size[index] / 2 * axis
            if index == spread:
                point = point - along * (safe_dot_product(inward, point) / inward[2])
                into_wall = safe_normalize_vector(inward - axis * safe_dot_product(inward, axis))
                normal = normal * cos(params.mortise_side_angle) + into_wall * sin(params.mortise_side_angle)
            cut = Intersection(cut, plane(normal, point, name, opposite))
    return replace(cut, label=CutCSGLabel("mortise_hole"))
