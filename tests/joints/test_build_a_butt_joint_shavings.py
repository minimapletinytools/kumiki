"""
Tests for build-a-butt-joint shoulder helpers
"""

import pytest
from sympy import Rational, cos, sin, pi
from kumiki.rule import create_v2, inches, radians, are_vectors_parallel, zero_test, safe_dot_product, safe_normalize_vector as normalize_vector, safe_compare, Comparison
from kumiki.timber import (
    TimberReferenceEnd,
    timber_from_directions, create_v3
)
from kumiki.construction import ButtJointTimberArrangement
from kumiki.joints.build_a_butt_joint_shavings import locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber


class TestMeasureMortiseShoulderPlane:
    """Tests for locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber"""

    def test_perpendicular_intersecting_centerlines(self):
        """90-degree butt joint where centerlines intersect at origin.

        Receiving (mortise) timber along +X, butt (tenon) timber along +Y.
        Both timbers are 4"x5"x48" centered at origin.
        Direction from mortise centerline toward tenon = +Y.

        With distance_from_centerline = 0, the plane passes through the
        mortise centerline. With distance = 1, the plane is 1" toward the tenon.
        """
        from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
        arrangement = create_canonical_example_butt_joint_timbers()

        plane_at_center = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement, Rational(0)
        )
        # The plane normal points AWAY from the tenon (into the mortise interior).
        # Tenon runs in +Y, so normal is -Y.
        assert are_vectors_parallel(plane_at_center.normal, create_v3(0, -1, 0)), \
            f"Plane normal should point away from tenon (-Y), got {plane_at_center.normal}"
        mortise_length_dir = arrangement.receiving_timber.get_length_direction_global()
        mortise_center = arrangement.receiving_timber.get_bottom_position_global() + mortise_length_dir * arrangement.receiving_timber.length / 2
        assert plane_at_center.point.equals(mortise_center), \
            f"At distance 0, plane point should be the mortise centerline midpoint, got {plane_at_center.point} vs {mortise_center}"

        # Positive distance moves the plane TOWARD the tenon (+Y),
        # but the direction_in_plane is -Y, so the point moves in -Y.
        # The shoulder conceptually moves toward the tenon, so positive distance
        # means the plane point goes away from centerline toward tenon face.
        plane_offset = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement, Rational(1)
        )
        expected_offset_point = mortise_center + create_v3(0, -1, 0)
        assert plane_offset.point.equals(expected_offset_point), \
            f"At distance 1, plane point should be offset 1 in -Y (normal dir), got {plane_offset.point} vs {expected_offset_point}"

    def test_angled_non_intersecting_centerlines(self, symbolic_mode):
        """40-degree butt joint where centerlines do NOT intersect.

        Mortise timber along +X at origin, tenon timber at 40 degrees in the
        XY plane offset 3" in +Z so the centerlines are skew (non-intersecting).
        """
        from sympy import Integer
        angle_rad = radians(Rational(2, 9) * pi)  # 40 degrees

        mortise_timber = timber_from_directions(
            length=inches(48), size=create_v2(inches(4), inches(5)),
            bottom_position=create_v3(-inches(24), Integer(0), Integer(0)),
            length_direction=create_v3(Integer(1), Integer(0), Integer(0)),
            width_direction=create_v3(Integer(0), Integer(0), Integer(1)),
            ticket="mortise"
        )
        tenon_length_dir = create_v3(cos(angle_rad), sin(angle_rad), Integer(0))
        tenon_timber = timber_from_directions(
            length=inches(48), size=create_v2(inches(4), inches(5)),
            bottom_position=create_v3(-inches(24) * cos(angle_rad), -inches(24) * sin(angle_rad), inches(3)),
            length_direction=tenon_length_dir,
            width_direction=create_v3(Integer(0), Integer(0), Integer(1)),
            ticket="tenon"
        )
        arrangement = ButtJointTimberArrangement(
            butt_timber=tenon_timber,
            receiving_timber=mortise_timber,
            butt_timber_end=TimberReferenceEnd.TOP,
        )

        plane = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement, Rational(0)
        )
        # The plane normal should be in the mortise cross-section, pointing
        # toward the tenon (which is offset at +Z=3").
        mortise_length_dir = mortise_timber.get_length_direction_global()
        assert zero_test(safe_dot_product(plane.normal, mortise_length_dir)), \
            "Plane normal should be perpendicular to the mortise length direction"
        dot_z = safe_dot_product(plane.normal, create_v3(Integer(0), Integer(0), Integer(1)))
        assert safe_compare(dot_z, 0, Comparison.GE), \
            "Plane normal should have a non-negative Z component (toward the tenon which is at +Z=3)"

        plane_positive = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement, inches(1)
        )
        plane_negative = locate_mortise_timber_shoulder_plane_from_centerline_towards_tenon_timber(
            arrangement, -inches(1)
        )
        direction_to_tenon = plane_positive.point - plane.point
        dot_to_tenon = safe_dot_product(direction_to_tenon, create_v3(Integer(0), Integer(0), Integer(1)))
        assert safe_compare(dot_to_tenon, 0, Comparison.GE), \
            "Positive distance should offset toward the tenon (which is at +Z)"
        direction_away = plane_negative.point - plane.point
        dot_away = safe_dot_product(direction_away, create_v3(Integer(0), Integer(0), Integer(1)))
        assert safe_compare(dot_away, 0, Comparison.LE), \
            "Negative distance should offset away from the tenon"
