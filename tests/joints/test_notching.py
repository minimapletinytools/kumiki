"""
Tests for shoulder notching helpers in kumiki.joints.workshop.notching.
"""

from dataclasses import replace
from sympy import Rational

from kumiki.cutcsg import Difference, Intersection
from kumiki.construction import ButtJointTimberArrangement
from kumiki.joints.workshop.notching import (
    ShoulderNotchCSGGeometry,
    chop_notch_for_butt_joint_arrangement,
    chop_scribe_notch,
    does_shoulder_plane_need_notching,
)
from kumiki.rule import create_v2, safe_normalize_vector as normalize_vector
from kumiki.timber import (
    TimberFace,
    TimberReferenceEnd,
    create_v3,
    timber_from_directions,
)
from kumiki.timber_shavings import are_timbers_plane_aligned
from tests.testing_shavings import (
    create_centered_horizontal_timber,
    create_standard_horizontal_timber,
    create_standard_vertical_timber,
)


# ============================================================================
# Test Fixtures
# ============================================================================


import pytest


@pytest.fixture
def simple_T_configuration():
    """Simple T: vertical 4x4 tenon timber + horizontal 6x6 mortise timber."""
    tenon_timber = create_standard_vertical_timber(
        height=100, size=(4, 4), position=(0, 0, 0), ticket="tenon_timber"
    )
    mortise_timber = create_centered_horizontal_timber(
        direction='x', length=100, size=(6, 6), name="mortise_timber"
    )
    return (tenon_timber, mortise_timber)


# ============================================================================
# Tests
# ============================================================================


class TestShoulderNotchingDecision:
    """Tests for does_shoulder_plane_need_notching."""

    def test_does_shoulder_plane_need_notching(self, simple_T_configuration):
        """Uses face/plane-aligned logic when aligned, and always True when not plane-aligned."""
        tenon_timber, mortise_timber = simple_T_configuration

        aligned_arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
        )
        assert are_timbers_plane_aligned(mortise_timber, tenon_timber)

        tenon_end_direction = tenon_timber.get_face_direction_global(TimberReferenceEnd.BOTTOM)
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        face_half_size = mortise_timber.get_size_in_face_normal_axis(mortise_face) / Rational(2)

        assert does_shoulder_plane_need_notching(aligned_arrangement, face_half_size - Rational(1))
        assert not does_shoulder_plane_need_notching(aligned_arrangement, face_half_size)

        non_plane_mortise = timber_from_directions(
            length=Rational(100),
            size=create_v2(Rational(6), Rational(6)),
            bottom_position=create_v3(-Rational(50), Rational(0), Rational(0)),
            length_direction=create_v3(Rational(1), Rational(0), Rational(0)),
            width_direction=create_v3(Rational(0), Rational(0), Rational(1)),
            ticket="non_plane_mortise",
        )
        non_plane_tenon = timber_from_directions(
            length=Rational(100),
            size=create_v2(Rational(4), Rational(4)),
            bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
            length_direction=create_v3(Rational(0), Rational(1), Rational(0)),
            width_direction=normalize_vector(create_v3(Rational(1), Rational(0), Rational(1))),
            ticket="non_plane_tenon",
        )
        non_plane_arrangement = ButtJointTimberArrangement(
            receiving_timber=non_plane_mortise,
            butt_timber=non_plane_tenon,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
        )

        assert not are_timbers_plane_aligned(non_plane_mortise, non_plane_tenon)
        assert does_shoulder_plane_need_notching(non_plane_arrangement, Rational(100))


class TestChopNotchForButtJointArrangement:
    """Tests for chop_notch_for_butt_joint_arrangement."""

    def test_returns_geometry_for_inset_shoulder(self, simple_T_configuration):
        """
        For a simple T-arrangement with the shoulder inset from the entry face,
        the helper returns geometry for BOTH the receiving timber notch and the
        butting timber relief cut. When the shoulder is at or past the entry
        face, the helper returns None.
        """
        from kumiki.cutcsg import Difference, RectangularPrism, SolidUnion

        tenon_timber, mortise_timber = simple_T_configuration
        arrangement = ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberReferenceEnd.BOTTOM,
        )

        # Mortise is 6x6, so nominal entry face half-size = 3.
        # An inset shoulder at distance 2 from the centerline (< 3) requires notching.
        inset_distance = Rational(2)
        geom = chop_notch_for_butt_joint_arrangement(
            arrangement, inset_distance
        )
        assert geom is not None
        assert isinstance(geom, ShoulderNotchCSGGeometry)
        # The receiving timber notch should be a prism or union of prisms.
        assert isinstance(
            geom.receiving_timber_notch_negative_CSG, (RectangularPrism, SolidUnion)
        )
        # The butting timber relief CSG is built via Difference for any non-trivial joint.
        assert geom.butting_timber_relief_negative_CSG is not None
        assert isinstance(geom.butting_timber_relief_negative_CSG, Difference)

        # A flush shoulder (distance equal to nominal half-size) needs no notch.
        tenon_end_direction = tenon_timber.get_face_direction_global(
            TimberFace.BOTTOM
        )
        entry_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        face_half_size = mortise_timber.get_half_nominal_size_in_face_normal_axis(
            entry_face
        )
        assert (
            chop_notch_for_butt_joint_arrangement(arrangement, face_half_size)
            is None
        )


class TestChopScribeNotch:
    def test_returns_pair_in_cut_timber_local_space(self):
        timber_to_be_cut = create_standard_vertical_timber(
            height=Rational(20),
            size=(Rational(4), Rational(6)),
            position=(Rational(0), Rational(0), Rational(0)),
            ticket="timber_to_be_cut",
        )
        timber_to_be_scribed = replace(
            timber_from_directions(
                length=Rational(20),
                size=create_v2(Rational(4), Rational(4)),
                bottom_position=create_v3(Rational(0), Rational(0), Rational(0)),
                length_direction=create_v3(Rational(0), Rational(0), Rational(1)),
                width_direction=create_v3(Rational(1), Rational(0), Rational(0)),
                ticket="timber_to_be_scribed",
            ),
            nominal_half_sizes=(
                create_v2(Rational(3), Rational(3)),
                create_v2(Rational(4), Rational(4)),
            ),
        )

        scribed_overlap_csg_local, scribe_notch_csg_local = chop_scribe_notch(
            timber_to_be_scribed=timber_to_be_scribed,
            timber_to_be_cut=timber_to_be_cut,
        )

        assert isinstance(scribed_overlap_csg_local, Intersection)
        assert isinstance(scribe_notch_csg_local, Difference)
        assert scribed_overlap_csg_local.contains_point(create_v3(Rational(1), Rational(5, 2), Rational(10)))
        assert scribe_notch_csg_local.contains_point(create_v3(Rational(5, 2), Rational(0), Rational(10)))
