"""
Tests for the shoulder-notch and relief-cut helpers in kumiki.joints.workshop.relief.
"""

from dataclasses import replace

from kumiki.cutcsg import Difference, Intersection
from kumiki.construction import ArrangementNames, ButtJointTimberArrangement
from kumiki.example_shavings import create_canonical_example_butt_joint_timbers
from kumiki.joints.workshop.shavings.relief import (
    BraceJointScribeReliefConfig,
    CrossCapJointScribeReliefConfig,
    DoubleButtJointScribeReliefConfig,
    QuadrupleButtJointScribeReliefConfig,
    ShoulderReliefCSGGeometry,
    TripleButtJointScribeReliefConfig,
    chop_relief_for_butt_joint_arrangement,
    chop_scribe_relief,
    chop_shoulder_notch_aligned_with_timber,
    does_shoulder_plane_need_notching,
)
from kumiki.rule import (
    Orientation,
    Transform,
    create_v2,
    degrees,
    inches,
    safe_normalize_vector as normalize_vector,
    scalar,
)
from kumiki.timber import (
    TimberFace,
    TimberEnd,
    create_v3,
    create_timber,
    Cutting,
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

        non_plane_mortise = create_timber(
            length=scalar(100),
            size=create_v2(scalar(6), scalar(6)),
            bottom_position=create_v3(-scalar(50), scalar(0), scalar(0)),
            length_direction=create_v3(scalar(1), scalar(0), scalar(0)),
            width_direction=create_v3(scalar(0), scalar(0), scalar(1)),
            ticket="non_plane_mortise",
        )
        non_plane_tenon = create_timber(
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


class TestChopReliefForButtJointArrangement:
    """Tests for chop_relief_for_butt_joint_arrangement."""

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
        geom = chop_relief_for_butt_joint_arrangement(
            arrangement, inset_distance
        )
        assert geom is not None
        assert isinstance(geom, ShoulderReliefCSGGeometry)
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
            chop_relief_for_butt_joint_arrangement(arrangement, face_half_size)
            is None
        )


class TestChopShoulderNotchAlignedWithTimber:
    """
    Geometry tests for chop_shoulder_notch_aligned_with_timber on the
    canonical butt arrangement (4"x5" timbers crossing at the origin,
    receiving along +X, butt along +Y, widths along +Z), with the butt
    timber optionally raked 45 degrees about its own local axes. The
    shoulder sits 2" from the receiving centerline (a 1/2" inset on the
    entry face).

    Expected notch widths were independently verified by brute-force
    slicing of the oblique butt prism's corner edge-lines with the
    shoulder plane.
    """

    DISTANCE_FROM_CENTERLINE = inches(2)

    @staticmethod
    def _rotate_about_midpoint(timber, angle, local_axis):
        pivot_local = create_v3(scalar(0), scalar(0), timber.length / scalar(2))
        pivot_global = timber.transform.position + timber.transform.orientation.matrix * pivot_local
        new_orientation = timber.transform.orientation * Orientation.from_angle_axis(angle, local_axis)
        new_bottom = pivot_global - new_orientation.matrix * pivot_local
        return replace(timber, transform=Transform(position=new_bottom, orientation=new_orientation))

    def _make_notch(self, rotate_width_axis: bool, rotate_height_axis: bool):
        arrangement = create_canonical_example_butt_joint_timbers(
            create_v3(scalar(0), scalar(0), scalar(0))
        )
        butt_timber = arrangement.butt_timber
        if rotate_width_axis:
            butt_timber = self._rotate_about_midpoint(
                butt_timber, degrees(45), create_v3(scalar(1), scalar(0), scalar(0))
            )
        if rotate_height_axis:
            butt_timber = self._rotate_about_midpoint(
                butt_timber, degrees(45), create_v3(scalar(0), scalar(1), scalar(0))
            )
        return chop_shoulder_notch_aligned_with_timber(
            notch_timber=arrangement.receiving_timber,
            butting_timber=butt_timber,
            butting_timber_end=arrangement.butt_timber_end,
            distance_from_centerline=self.DISTANCE_FROM_CENTERLINE,
        )

    @staticmethod
    def _base_prism(notch):
        from kumiki.cutcsg import SolidUnion

        return notch.children[0] if isinstance(notch, SolidUnion) else notch

    def test_perpendicular_notch_dimensions(self):
        """
        Perpendicular approach: width hugs the butt's 5" dimension exactly
        (the 5" height axis lies along the receiving's length), the span and
        depth clear the receiving's worst-case corner radius r = sqrt(2^2 +
        2.5^2), and no wall relief prisms appear (zero rake).
        """
        from kumiki.cutcsg import RectangularPrism

        notch = self._make_notch(False, False)
        assert isinstance(notch, RectangularPrism)

        corner_radius = float(inches(1)) * (2**2 + 2.5**2) ** 0.5
        assert float(notch.size[0]) == pytest.approx(float(inches(5)), rel=1e-9)
        assert float(notch.size[1]) == pytest.approx(2 * corner_radius, rel=1e-9)
        assert float(notch.end_distance) == pytest.approx(
            2 * corner_radius - float(self.DISTANCE_FROM_CENTERLINE), rel=1e-9
        )

    def test_width_axis_rake_stretches_width_and_adds_walls(self):
        """
        45-degree in-plane rake: the shoulder-plane slice of the butt prism
        stretches the 5" dimension by sec(45) = sqrt(2), and wall relief
        prisms appear automatically (floored at the rake angle) even though
        no wall angle was requested.
        """
        from kumiki.cutcsg import SolidUnion

        notch = self._make_notch(True, False)
        assert isinstance(notch, SolidUnion)
        assert len(notch.children) == 3
        assert float(self._base_prism(notch).size[0]) == pytest.approx(
            float(inches(5)) * 2**0.5, rel=1e-9
        )

    def test_height_axis_rake_reorients_shoulder_without_stretch(self):
        """
        45-degree out-of-plane tip: the shoulder plane reorients to face the
        butt square-on, so the slice is NOT stretched (width stays 5") and no
        wall relief is needed (the butt is perpendicular to ITS shoulder plane).
        """
        from kumiki.cutcsg import RectangularPrism

        notch = self._make_notch(False, True)
        assert isinstance(notch, RectangularPrism)
        assert float(notch.size[0]) == pytest.approx(float(inches(5)), rel=1e-9)

    def test_compound_rake_width_matches_brute_force(self):
        """
        Compound 45+45 rake: the slice direction shifts inside the butt's
        cross-section AND stretches; expected width 0.187470m (7.3807") was
        computed by brute-force corner-edge slicing.
        """
        from kumiki.cutcsg import SolidUnion

        notch = self._make_notch(True, True)
        assert isinstance(notch, SolidUnion)
        assert float(self._base_prism(notch).size[0]) == pytest.approx(0.187470, rel=1e-4)


class TestChopScribeRelief:
    def test_returns_pair_in_cut_timber_local_space(self):
        timber_to_be_cut = create_standard_vertical_timber(
            height=scalar(20),
            size=(scalar(4), scalar(6)),
            position=(scalar(0), scalar(0), scalar(0)),
            ticket="timber_to_be_cut",
        )
        timber_to_be_scribed = replace(
            create_timber(
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

        scribed_overlap_csg_local, scribe_relief_csg_local = chop_scribe_relief(
            timber_to_be_scribed=timber_to_be_scribed,
            timber_to_be_scribed_cutting=Cutting(timber=timber_to_be_scribed),
            timber_to_be_cut=timber_to_be_cut,
        )

        assert isinstance(scribed_overlap_csg_local, Intersection)
        assert isinstance(scribe_relief_csg_local, Difference)
        assert scribed_overlap_csg_local.contains_point(create_v3(scalar(1), scalar(5, 2), scalar(10)))
        assert scribe_relief_csg_local.contains_point(create_v3(scalar(5, 2), scalar(0), scalar(10)))


class TestMultiTimberScribeReliefConfig:
    def test_double_butt_uses_with_order(self):
        config = DoubleButtJointScribeReliefConfig.with_order(
            ArrangementNames.butt_timber_1,
            ArrangementNames.butt_timber_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.butt_timber_2

    def test_triple_butt_uses_with_order(self):
        config = TripleButtJointScribeReliefConfig.with_order(
            ArrangementNames.main_butt_timber_1,
            ArrangementNames.main_butt_timber_2,
            ArrangementNames.awk_timber,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.main_butt_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.main_butt_timber_2
        assert config.third_timber_to_be_scribed == ArrangementNames.awk_timber

    def test_quadruple_butt_uses_with_order(self):
        config = QuadrupleButtJointScribeReliefConfig.with_order(
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
        config = CrossCapJointScribeReliefConfig.with_order(
            ArrangementNames.cross_timber_1,
            ArrangementNames.cross_timber_2,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.cross_timber_1
        assert config.second_timber_to_be_scribed == ArrangementNames.cross_timber_2

    def test_brace_uses_with_order(self):
        config = BraceJointScribeReliefConfig.with_order(
            ArrangementNames.timber1,
            ArrangementNames.brace_timber,
        )

        assert config.first_timber_to_be_scribed == ArrangementNames.timber1
        assert config.second_timber_to_be_scribed == ArrangementNames.brace_timber
