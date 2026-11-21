"""Shared marking and end cuts for complementary rows of fingers."""

from math import ceil, isfinite

from kumiki.construction import CornerJointTimberArrangement, SpliceJointTimberArrangement, arrangement_error
from kumiki.csg.cutcsg import ConvexPolygonExtrusion, CutCSG, CutCSGLabel, SolidUnion, adopt_csg
from kumiki.measuring import get_center_point_on_face_global
from kumiki.rule import (Comparison, Numeric, Orientation, Transform, V3, create_v2, pi, safe_compare,
                         safe_dot_product, safe_equality_test, tan)
from kumiki.timber import AssemblyFreedom, Board, Cutting, Timber, TimberEnd, TimberLike, TimberLongFace


def matched_span(arrangement: CornerJointTimberArrangement | SpliceJointTimberArrangement,
                 face: TimberLongFace) -> Numeric:
    """Return the span between the two shared face planes normal to timber1's given face."""
    first, second = arrangement.timber1, arrangement.timber2
    if not all(isinstance(member, (Board, Timber)) and member.is_perfect_timber() for member in (first, second)):
        raise arrangement_error("Finger joints require perfect rectangular stock", arrangement)
    normal = first.get_face_direction_global(face)
    other = second.get_closest_oriented_long_face_from_global_direction(normal)
    width = first.get_size_in_face_normal_axis(face)
    offset = get_center_point_on_face_global(other, second) - get_center_point_on_face_global(face, first)
    if not (safe_equality_test(safe_dot_product(normal, second.get_face_direction_global(other)), 1)
            and safe_equality_test(safe_dot_product(offset, normal), 0)
            and safe_equality_test(width, second.get_size_in_face_normal_axis(other))):
        raise arrangement_error(f"The timbers must be flush across timber1's {face.name} axis", arrangement)
    return width


def finger_slots(shoulder_global: V3, front_global: V3, along_global: V3, width: Numeric,
                 depth: Numeric, thickness: Numeric, finger_count: int | None, finger_width: Numeric | None,
                 taper_angle: Numeric) -> tuple[CutCSG, CutCSG]:
    """Return each member's slot waste in world space, starting with a finger on timber1.

    The profile runs inward from the front face and along timber1 from its shoulder to its tip.
    Thickness spans the third axis, centered on the shoulder point.
    """
    if finger_width is None:
        count = 5 if finger_count is None else finger_count
        if isinstance(count, bool) or not isinstance(count, int) or count < 2:
            raise ValueError("finger_count must be an integer of at least 2")
        pitch = width / count
    else:
        if finger_count is not None:
            raise ValueError("finger_count and finger_width are mutually exclusive")
        if isinstance(finger_width, bool) or not isfinite(finger_width) or safe_compare(finger_width, 0, Comparison.LE):
            raise ValueError("finger_width must be positive and finite")
        if safe_compare(finger_width, width, Comparison.GE):
            raise ValueError("finger_width must be smaller than the shared width")
        pitch = finger_width
        count = ceil(width / pitch)
        # A rounded exact multiple can otherwise leave a zero-width last finger.
        if safe_equality_test((count - 1) * pitch, width):
            count -= 1
    if not isfinite(depth) or depth <= 0:
        raise ValueError("finger_length must be positive and finite")
    if not 0 <= taper_angle < pi / 2:
        raise ValueError("taper_angle must satisfy 0 <= angle < pi/2")
    shift = depth * tan(taper_angle) / 2
    transform = Transform(position=shoulder_global + front_global * (width / 2),
                          orientation=Orientation.from_x_and_y(-front_global, along_global))
    # Each shared flank has one station at the root and one at the tip.
    stations = [(0.0, 0.0)]
    for i in range(1, count):
        delta = shift if i % 2 else -shift
        stations.append((i * pitch + delta, i * pitch - delta))
    stations.append((width, width))

    waste: tuple[list[CutCSG], list[CutCSG]] = ([], [])
    for i, ((root_left, tip_left), (root_right, tip_right)) in enumerate(zip(stations, stations[1:])):
        if safe_compare(root_right, root_left, Comparison.LE) or safe_compare(tip_right, tip_left, Comparison.LE):
            raise ValueError("The taper leaves no finger tip. Reduce the taper or change the finger spacing.")
        profile = [create_v2(root_left, 0), create_v2(root_right, 0),
                   create_v2(tip_right, depth), create_v2(tip_left, depth)]
        waste[(i + 1) % 2].append(ConvexPolygonExtrusion(
            points=profile, transform=transform, start_distance=-thickness / 2, end_distance=thickness / 2,
            label=CutCSGLabel(f"slot_{i + 1}"),
        ))
    return SolidUnion(waste[0]), SolidUnion(waste[1])


def finger_cutting(timber: TimberLike, end: TimberEnd, tip_global: V3, finger_length: Numeric, slots_global: CutCSG,
                   freedom: AssemblyFreedom) -> Cutting:
    """Trim the selected end to the tip plane and remove its finger slots."""
    tip = timber.transform.global_to_local(tip_global)[2]
    remaining = tip if end == TimberEnd.TOP else timber.length - tip
    if safe_compare(remaining, finger_length, Comparison.LE):
        raise ValueError("Finger joint shoulder must lie inside the opposite end of the timber")
    return Cutting(timber=timber, negative_csg=adopt_csg(None, timber.transform, slots_global),
                   maybe_top_end_cut_distance_from_bottom=tip if end == TimberEnd.TOP else None,
                   maybe_bottom_end_cut_distance_from_bottom=tip if end == TimberEnd.BOTTOM else None,
                   assembly_freedom=freedom, label=CutCSGLabel("finger_slots"))
