"""
Kumiki - Plain cross lap joint construction functions
"""

from dataclasses import replace
from typing import Optional

from kumiki.timber import *
from kumiki.construction import *
from kumiki.rule import *
from kumiki.measuring import get_center_point_on_face_global
from ..shavings import *
from ..shavings.relief import (
    CrossJointScribeReliefConfig,
    chop_scribe_relief_and_apply,
    warn_if_arrangement_timbers_imperfect,
)


def _get_face_center_position(timber: PerfectTimberWithin, face: SomeTimberFace) -> V3:
    return get_center_point_on_face_global(face, timber)


def cut_plain_cross_lap_joint(
    arrangement: CrossJointTimberArrangement,
    cut_ratio: Numeric = scalar(1, 2),
    relief: Optional[CrossJointScribeReliefConfig] = CrossJointScribeReliefConfig.cross_timber_1(),
) -> Joint:
    """
    Creates a cross-lap joint between two intersecting timbers.

    Each timber has a portion relieved from it so they interlock at their crossing point,
    maintaining a flush outer face on both sides. By default material removal is split
    equally (half from each timber).

    Args:
        arrangement: Cross-joint arrangement with timber1 and timber2, and optional
                     front_face_on_timber1 (the cut face on timber1). If not provided,
                     front_face_on_timber1 is chosen automatically to minimize material removed.
                     The cut face on timber2 is implicitly the opposite face.
        cut_ratio: Fraction [0, 1] controlling how much is removed from each timber.
            0 = only timber2 is cut; 1 = only timber1 is cut; 0.5 = equal split (default).

    Returns:
        Joint object containing the two CutTimbers.

    Raises:
        AssertionError: If the timbers don't intersect, are parallel, or cut_ratio is out of range.
    """
    timberA = arrangement.timber1
    timberB = arrangement.timber2
    timberA_cut_face = arrangement.front_face_on_timber1

    warn_if_arrangement_timbers_imperfect(arrangement)

    assert 0 <= cut_ratio <= 1, f"cut_ratio must be in range [0, 1], got {cut_ratio}"

    dot_product = safe_dot_product(timberA.get_length_direction_global(), timberB.get_length_direction_global())
    assert abs(abs(dot_product) - 1) > scalar(1, 1000000), (
        "Timbers must not be parallel (their length directions must differ)"
    )

    d1 = timberA.get_length_direction_global()
    d2 = timberB.get_length_direction_global()
    p1 = timberA.get_bottom_position_global()
    p2 = timberB.get_bottom_position_global()
    w = p1 - p2

    a = safe_dot_product(d1, d1)
    b = safe_dot_product(d1, d2)
    c = safe_dot_product(d2, d2)
    d = safe_dot_product(d1, w)
    e = safe_dot_product(d2, w)

    denom = a * c - b * b

    if abs(denom) < scalar(1, 1000000):
        t = -safe_dot_product(d1, w) / a if a > 0 else 0
        closest_on_1 = p1 + t * d1
        distance = safe_norm(p2 - closest_on_1)
    else:
        t1 = (b * e - c * d) / denom
        t2 = (a * e - b * d) / denom

        closest_on_1 = p1 + t1 * d1
        closest_on_2 = p2 + t2 * d2

        distance = safe_norm(closest_on_1 - closest_on_2)

    max_separation = (timberA.size[0] + timberA.size[1] + timberB.size[0] + timberB.size[1]) / 2

    assert float(distance) < float(max_separation), (
        f"Timbers do not intersect (closest distance: {float(distance):.4f}m, max allowed: {float(max_separation):.4f}m)"
    )

    if timberA_cut_face is None:
        perpendicular_axis = cross_product(d1, d2)
        perpendicular_axis = safe_normalize_vector(perpendicular_axis)

        centerA = timberA.get_bottom_position_global() + timberA.get_length_direction_global() * (timberA.length / scalar(2))
        centerB = timberB.get_bottom_position_global() + timberB.get_length_direction_global() * (timberB.length / scalar(2))

        A_to_B = centerB - centerA
        projection = safe_dot_product(A_to_B, perpendicular_axis)
        direction_toward_B = perpendicular_axis if projection >= 0 else -perpendicular_axis

        faces = [TimberFace.RIGHT, TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK]
        max_dot = None
        best_face = TimberFace.RIGHT

        for face in faces:
            face_normal = timberA.get_face_direction_global(face)
            dot = safe_dot_product(face_normal, direction_toward_B)

            if max_dot is None or dot > max_dot:
                max_dot = dot
                best_face = face

        timberA_cut_face = best_face

    normalA = timberA.get_face_direction_global(timberA_cut_face)
    faces = [TimberFace.RIGHT, TimberFace.LEFT, TimberFace.FRONT, TimberFace.BACK]
    min_dot = None
    timberB_cut_face = TimberFace.RIGHT

    for face in faces:
        face_normal = timberB.get_face_direction_global(face)
        dot = safe_dot_product(face_normal, normalA)

        if min_dot is None or dot < min_dot:
            min_dot = dot
            timberB_cut_face = face

    assert timberA_cut_face is not None and timberB_cut_face is not None
    normalA = timberA.get_face_direction_global(timberA_cut_face)
    normalB = timberB.get_face_direction_global(timberB_cut_face)

    normal_dot = safe_dot_product(normalA, normalB)
    assert normal_dot < 0, (
        f"Face normals must oppose each other (dot product < 0, got {float(normal_dot):.4f})"
    )

    faceA_position = _get_face_center_position(timberA, timberA_cut_face)
    faceB_position = _get_face_center_position(timberB, timberB_cut_face)

    cutting_plane_position = faceA_position * (1 - cut_ratio) + faceB_position * cut_ratio
    cutting_plane_normal = normalA * (1 - cut_ratio) - normalB * cut_ratio
    cutting_plane_normal_normalized = cutting_plane_normal / safe_norm(cutting_plane_normal)
    cutting_plane_offset = safe_dot_product(cutting_plane_normal_normalized, cutting_plane_position)

    cuts_A = []
    cuts_B = []

    if safe_compare(cut_ratio, 0, Comparison.GT):
        relative_orientation_B_in_A = Orientation(safe_transform_vector(timberA.orientation.matrix.T, timberB.orientation.matrix))
        timberB_origin_in_A_local = safe_transform_vector(timberA.orientation.matrix.T, timberB.get_bottom_position_global() - timberA.get_bottom_position_global())

        transform_B_in_A = Transform(position=timberB_origin_in_A_local, orientation=relative_orientation_B_in_A)
        timberB_prism_in_A = RectangularPrism(
            size=timberB.size,
            transform=transform_B_in_A,
            start_distance=None,
            end_distance=None,
            label=CutCSGLabel("crossing_timber"),
        )

        cutting_plane_normal_in_A = safe_transform_vector(timberA.orientation.matrix.T, cutting_plane_normal_normalized)
        cutting_plane_position_in_A = safe_transform_vector(timberA.orientation.matrix.T, cutting_plane_position - timberA.get_bottom_position_global())
        cutting_plane_offset_in_A = safe_dot_product(cutting_plane_normal_in_A, cutting_plane_position_in_A)

        inverse_half_plane_A = HalfSpace(
            normal=-cutting_plane_normal_in_A,
            offset=-cutting_plane_offset_in_A,
            label=CutCSGLabel("lap_depth_plane"),
        )

        negative_csg_A = Difference(
            base=timberB_prism_in_A,
            subtract=[inverse_half_plane_A],
            label=CutCSGLabel("lap_waste"),
        )

        cut_A = Cutting(
            timber=timberA,
            negative_csg=negative_csg_A,
            label=CutCSGLabel("lap_cut"),
        )
        cuts_A.append(cut_A)

    if cut_ratio < 1:
        relative_orientation_A_in_B = Orientation(safe_transform_vector(timberB.orientation.matrix.T, timberA.orientation.matrix))
        timberA_origin_in_B_local = safe_transform_vector(timberB.orientation.matrix.T, timberA.get_bottom_position_global() - timberB.get_bottom_position_global())

        transform_A_in_B = Transform(position=timberA_origin_in_B_local, orientation=relative_orientation_A_in_B)
        timberA_prism_in_B = RectangularPrism(
            size=timberA.size,
            transform=transform_A_in_B,
            start_distance=None,
            end_distance=None,
            label=CutCSGLabel("crossing_timber"),
        )

        cutting_plane_normal_in_B = safe_transform_vector(timberB.orientation.matrix.T, cutting_plane_normal_normalized)
        cutting_plane_position_in_B = safe_transform_vector(timberB.orientation.matrix.T, cutting_plane_position - timberB.get_bottom_position_global())
        cutting_plane_offset_in_B = safe_dot_product(cutting_plane_normal_in_B, cutting_plane_position_in_B)

        half_plane_B = HalfSpace(
            normal=cutting_plane_normal_in_B,
            offset=cutting_plane_offset_in_B,
            label=CutCSGLabel("lap_depth_plane"),
        )

        negative_csg_B = Difference(
            base=timberA_prism_in_B,
            subtract=[half_plane_B],
            label=CutCSGLabel("lap_waste"),
        )

        cut_B = Cutting(
            timber=timberB,
            negative_csg=negative_csg_B,
            label=CutCSGLabel("lap_cut"),
        )
        cuts_B.append(cut_B)

    cut_timberA = cuts_A[0] if len(cuts_A) > 0 else Cutting(timber=timberA)
    cut_timberB = cuts_B[0] if len(cuts_B) > 0 else Cutting(timber=timberB)

    cuttings: dict[str, Cutting] = {"timberA": cut_timberA, "timberB": cut_timberB}

    if relief is not None:
        if relief.timber_to_be_scribed == ArrangementNames.cross_timber_1:
            scribed_key, cut_key = "timberA", "timberB"
        elif relief.timber_to_be_scribed == ArrangementNames.cross_timber_2:
            scribed_key, cut_key = "timberB", "timberA"
        else:
            raise AssertionError(
                f"Unsupported cross-joint relief target: {relief.timber_to_be_scribed}"
            )

        updated_cut_cutting, updated_scribed_cutting = chop_scribe_relief_and_apply(
            timber_to_be_scribed_cutting=cuttings[scribed_key],
            timber_to_be_cut_cutting=cuttings[cut_key],
        )
        cuttings[scribed_key] = updated_scribed_cutting
        cuttings[cut_key] = updated_cut_cutting

    lap_overlap = Abs(safe_dot_product(cutting_plane_normal_normalized, faceA_position - faceB_position))
    cuttings["timberA"] = replace(
        cuttings["timberA"],
        assembly_freedom=AssemblyFreedom.translation(-cutting_plane_normal_normalized, freed_after=lap_overlap),
    )
    cuttings["timberB"] = replace(
        cuttings["timberB"],
        assembly_freedom=AssemblyFreedom.translation(cutting_plane_normal_normalized, freed_after=lap_overlap),
    )

    return Joint(
        cuttings=cuttings,
        ticket=JointTicket(joint_type="plain_cross_lap"),
        jointAccessories={},
    )


def cut_plain_cross_lap_house_joint(arrangement: CrossJointTimberArrangement) -> Joint:
    """
    Creates a house (dado/housing) joint where the housing timber is relieved to receive the housed timber.

    Only the housing timber is cut (timber1); the housed timber (timber2) is not modified.
    Implemented as a cross-lap joint with cut_ratio=1.

    Note this different from cut_free_house_joint in the way it handles relief cuts on the non-ptw parts of the timbers.

    Args:
        arrangement: Cross-joint arrangement where timber1 is the housing timber (to be relieved)
                     and timber2 is the housed timber (remains uncut). front_face_on_timber1
                     specifies the relief face; if None, chosen automatically.

    Returns:
        Joint object containing both timbers.

    Raises:
        AssertionError: If the timbers don't intersect or are parallel.
    """
    return cut_plain_cross_lap_joint(arrangement, cut_ratio=scalar(1, 1))
