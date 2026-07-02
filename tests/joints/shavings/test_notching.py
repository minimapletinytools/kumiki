"""
Tests for shoulder notching helpers in kumiki.joints.workshop.notching.
"""

from dataclasses import replace

from kumiki.cutcsg import Difference, Intersection
from kumiki.construction import ArrangementNames, ButtJointTimberArrangement
from kumiki.joints.workshop.shavings.notching import (
    BraceJointScribeNotchingConfig,
    CrossCapJointScribeNotchingConfig,
    DoubleButtJointScribeNotchingConfig,
    QuadrupleButtJointScribeNotchingConfig,
    ShoulderNotchCSGGeometry,
    TripleButtJointScribeNotchingConfig,
    chop_notch_for_butt_joint_arrangement,
    chop_scribe_notch,
    does_shoulder_plane_need_notching,
)
from kumiki.rule import create_v2, safe_normalize_vector as normalize_vector, scalar
from kumiki.timber import (
    TimberFace,
    TimberEnd,
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
            butt_timber_end=TimberEnd.BOTTOM,
        )
        assert are_timbers_plane_aligned(mortise_timber, tenon_timber)

        tenon_end_direction = tenon_timber.get_face_direction_global(TimberEnd.BOTTOM)
        mortise_face = mortise_timber.get_closest_oriented_long_face_from_global_direction(
            -tenon_end_direction
        ).to.face()
        face_half_size = mortise_timber.get_size_in_face_normal_axis(mortise_face) / scalar(2)

        assert does_shoulder_plane_need_notching(aligned_arrangement, face_half_size - scalar(1))
        assert not does_shoulder_plane_need_notching(aligned_arrangement, face_half_size)

        non_plane_mortise = timber_from_directions(
            length=scalar(100),
            size=create_v2(scalar(6), scalar(6)),
            bottom_position=create_v3(-scalar(50), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="non_plane_mortise",
        )
        non_plane_tenon = timber_from_directions(
            length=scalar(100),
            size=create_v2(scalar(4), scalar(4)),
            bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(0), scalar(1), scalar(0)),
            width_direction=normalize_vector(create_v3(scalar(1), scalar(0), scalar(1))),
            ticket="non_plane_tenon",
        )
        non_plane_arrangement = ButtJointTimberArrangement(
            receiving_timber=non_plane_mortise,
            butt_timber=non_plane_tenon,
            butt_timber_end=TimberEnd.BOTTOM,
        )

        assert not are_timbers_plane_aligned(non_plane_mortise, non_plane_tenon)
        assert does_shoulder_plane_need_notching(non_plane_arrangement, scalar(100))


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
            butt_timber_end=TimberEnd.BOTTOM,
        )

        # Mortise is 6x6, so nominal entry face half-size = 3.
        # An inset shoulder at distance 2 from the centerline (< 3) requires notching.
        inset_distance = scalar(2)
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
            height=scalar(20),
            size=(scalar(4), scalar(6)),
            position=(scalar(0), scalar(0), scalar(0)),
            ticket="timber_to_be_cut",
        )
        timber_to_be_scribed = replace(
            timber_from_directions(
                length=scalar(20),
                size=create_v2(scalar(4), scalar(4)),
                bottom_position=create_v3(scalar(0), scalar(0), scalar(0)),
                length_direction=create_v3(scalar(0), scalar(0), scalar(1)),
                width_direction=create_v3(scalar(1), scalar(0), scalar(0)),
                ticket="timber_to_be_scribed",
            ),
            nominal_half_sizes=(
                create_v2(scalar(3), scalar(3)),
                create_v2(scalar(4), scalar(4)),
            ),
        )

        scribed_overlap_csg_local, scribe_notch_csg_local = chop_scribe_notch(
            timber_to_be_scribed=timber_to_be_scribed,
            timber_to_be_cut=timber_to_be_cut,
        )

        assert isinstance(scribed_overlap_csg_local, Intersection)
        assert isinstance(scribe_notch_csg_local, Difference)
        assert scribed_overlap_csg_local.contains_point(create_v3(scalar(1), scalar(5, 2), scalar(10)))
        assert scribe_notch_csg_local.contains_point(create_v3(scalar(5, 2), scalar(0), scalar(10)))


class TestMultiTimberScribeNotchingConfig:
    def test_double_butt_uses_with_order(self):
        config = DoubleButtJointScribeNotchingConfig.with_order(
            ArrangementNames.butt_timber_1,
            ArrangementNames.butt_timber_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.butt_timber_2

    def test_triple_butt_uses_with_order(self):
        config = TripleButtJointScribeNotchingConfig.with_order(
            ArrangementNames.main_butt_timber_1,
            ArrangementNames.main_butt_timber_2,
            ArrangementNames.awk_timber,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.main_butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.main_butt_timber_2
        assert config.third_timber_to_be_scribed == ArrangementNames.awk_timber

    def test_quadruple_butt_uses_with_order(self):
        config = QuadrupleButtJointScribeNotchingConfig.with_order(
            ArrangementNames.main_butt_timber_1,
            ArrangementNames.main_butt_timber_2,
            ArrangementNames.awk_1,
            ArrangementNames.awk_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.main_butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.main_butt_timber_2
        assert config.third_timber_to_be_scribed == ArrangementNames.awk_1
        assert config.fourth_timber_to_be_scribed == ArrangementNames.awk_2

    def test_cross_cap_uses_with_order(self):
        config = CrossCapJointScribeNotchingConfig.with_order(
            ArrangementNames.cross_timber_1,
            ArrangementNames.cross_timber_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.cross_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.cross_timber_2

    def test_brace_uses_with_order(self):
        config = BraceJointScribeNotchingConfig.with_order(
            ArrangementNames.timber1,
            ArrangementNames.brace_timber,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.timber1
        assert config.second_timber_to_be_scribed == ArrangementNames.brace_timber
