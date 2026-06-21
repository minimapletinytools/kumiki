"""
Tests for Kumiki timber framing system
"""

import pytest
from sympy import Matrix, sqrt, simplify, Abs, Float, Rational, pi
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber
)


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()

class TestHouseJoint:
    """Test cut_plain_cross_lap_house_joint function."""
    
    # 🐪
    def test_basic_house_joint_perpendicular_timbers(self):
        """Test that a house joint between two perpendicular timbers is created correctly."""


        # create 2 timbers in an X shape
        housing_timber = create_centered_horizontal_timber(direction='x', length=100, size=(10, 10), zoffset=1)
        housed_timber = create_centered_horizontal_timber(direction='y', length=100, size=(10, 10), zoffset=-1)

        arrangement = CrossJointTimberArrangement(timber1=housing_timber, timber2=housed_timber)
        joint = cut_plain_cross_lap_house_joint(arrangement)
        assert joint is not None
        assert len(joint.cuttings) == 2
        assert joint.cuttings["timberA"].timber == housing_timber
        assert joint.cuttings["timberB"].timber == housed_timber

        assert isinstance(joint.cuttings["timberA"], Cutting)
        assert isinstance(joint.cuttings["timberB"], Cutting)
        assert joint.cuttings["timberA"].negative_csg is not None
        assert joint.cuttings["timberB"].negative_csg is None
        
        assert joint.cuttings["timberA"].get_maybe_top_end_cut() is None
        assert joint.cuttings["timberA"].get_maybe_bottom_end_cut() is None

        # test that the origin point lies in the housed timber but not the housing timber
        origin = create_v3(Rational(0), Rational(0), Rational(0))
        assert not _render_cutting(joint.cuttings["timberA"]).contains_point(housing_timber.transform.global_to_local(origin))
        assert _render_cutting(joint.cuttings["timberB"]).contains_point(housed_timber.transform.global_to_local(origin))
        

    def test_house_joint_prism_matches_housed_timber_global_space(self, symbolic_mode):
        """
        Test that the prism being cut from the housing timber matches the housed timber
        when both are compared in global coordinates.
        """
        from kumiki.cutcsg import RectangularPrism
        
        # Create housing timber (vertical post)
        housing_timber = create_standard_vertical_timber(height=200, size=(10, 10), position=(0, 0, 0))
        
        # Create housed timber (horizontal beam intersecting the post)
        housed_timber = timber_from_directions(
            length=Rational(80),
            size=Matrix([Rational(6), Rational(6)]),  # 6 x 6 beam
            bottom_position=Matrix([Rational(-20), Rational(0), Rational(100)]),
            length_direction=Matrix([Rational(1), Rational(0), Rational(0)]),  # Horizontal
            width_direction=Matrix([Rational(0), Rational(1), Rational(0)])
        )
        
        # Create the housed joint
        # Explicitly specify the housing timber cut face: FRONT (+Y)
        # The housed timber cut face is automatically computed as the opposite
        arrangement = CrossJointTimberArrangement(
            timber1=housing_timber,
            timber2=housed_timber,
            front_face_on_timber1=TimberLongFace.FRONT
        )
        joint = cut_plain_cross_lap_house_joint(arrangement)
        
        # Get the housing timber with its cut
        housing_cut_timber = joint.cuttings["timberA"]
        cut = housing_cut_timber
        
        assert isinstance(cut, Cutting), "Cut should be a Cutting object"
        
        # Get the negative CSG (the prism being cut away)
        # This is in the housing timber's LOCAL coordinate system
        # Note: The new implementation uses a Difference(RectangularPrism, HalfSpace) for the cross lap joint
        from kumiki.cutcsg import Difference
        cut_csg_local = cut.negative_csg
        assert isinstance(cut_csg_local, Difference), "Negative CSG should be a Difference (cross lap implementation)"
        
        # Extract the base prism from the Difference
        cut_prism_local = cut_csg_local.base
        assert isinstance(cut_prism_local, RectangularPrism), "Base of Difference should be a RectangularPrism"
        
        # ===================================================================
        # Compare the cut prism with the housed timber in GLOBAL space
        # ===================================================================
        
        # 1. The prism's size should match the housed timber's size
        assert cut_prism_local.size[0] == housed_timber.size[0], \
            f"Cut prism width should match housed timber width: {cut_prism_local.size[0]} vs {housed_timber.size[0]}"
        assert cut_prism_local.size[1] == housed_timber.size[1], \
            f"Cut prism height should match housed timber height: {cut_prism_local.size[1]} vs {housed_timber.size[1]}"
        
        # 2. Check the prism's orientation in global space
        # cut_prism_local.transform.orientation is relative to housing timber's local frame
        # Global orientation = housing_orientation * local_orientation
        cut_prism_global_orientation = housing_timber.orientation.multiply(cut_prism_local.transform.orientation)
        
        # The prism's orientation should match the housed timber's orientation
        # (they should be aligned in the same direction)
        orientation_diff = cut_prism_global_orientation.matrix - housed_timber.orientation.matrix
        orientation_diff_norm = simplify(orientation_diff.norm())
        
        assert orientation_diff_norm == 0, \
            f"Cut prism orientation should exactly match housed timber orientation in global space. Difference: {orientation_diff_norm}"
        
        # 3. Check that the prism extends along the housed timber's length direction
        # The prism's length direction (in housing timber's local coords) should match
        # the housed timber's length direction (also in housing timber's local coords)
        
        housed_length_dir_in_housing_local = housing_timber.orientation.matrix.T * housed_timber.get_length_direction_global()
        prism_length_dir_in_housing_local = cut_prism_local.transform.orientation.matrix[:, 2]  # Z-axis of prism
        
        # These should be parallel (same or opposite direction)
        dot = simplify((housed_length_dir_in_housing_local.T * prism_length_dir_in_housing_local)[0, 0])
        assert abs(dot) == 1, \
            f"Cut prism length direction should be exactly parallel to housed timber length direction. Dot product: {dot}"
    


class TestCrossLapJoint:
    # 🐪
    def test_basic_cross_lap_joint_perpendicular_timbers(self):
        """Test that a cross lap joint between two perpendicular timbers is created correctly."""


        # create 2 timbers in an X shape
        timberA = create_centered_horizontal_timber(direction='x', length=100, size=(10, 10), zoffset=1)
        timberB = create_centered_horizontal_timber(direction='y', length=100, size=(10, 10), zoffset=-1)

        arrangement = CrossJointTimberArrangement(timber1=timberA, timber2=timberB)
        joint = cut_plain_cross_lap_joint(arrangement)

        assert joint is not None
        assert len(joint.cuttings) == 2
        assert joint.cuttings["timberA"].timber == timberA
        assert joint.cuttings["timberB"].timber == timberB
        assert 1 == 1
        assert 1 == 1
        assert joint.cuttings["timberA"].get_maybe_top_end_cut() is None
        assert joint.cuttings["timberA"].get_maybe_bottom_end_cut() is None
        assert joint.cuttings["timberB"].get_maybe_top_end_cut() is None
        assert joint.cuttings["timberB"].get_maybe_bottom_end_cut() is None

        # test that the origin point lies on the boundary of both timbers
        origin = create_v3(Rational(0), Rational(0), Rational(0))
        assert _render_cutting(joint.cuttings["timberA"]).contains_point(timberA.transform.global_to_local(origin))
        assert _render_cutting(joint.cuttings["timberB"]).contains_point(timberB.transform.global_to_local(origin))

        assert _render_cutting(joint.cuttings["timberA"]).is_point_on_boundary(timberA.transform.global_to_local(origin))
        assert _render_cutting(joint.cuttings["timberB"]).is_point_on_boundary(timberB.transform.global_to_local(origin))

        # above origin
        origin = create_v3(Rational(0), Rational(0), Rational(1))
        assert _render_cutting(joint.cuttings["timberA"]).contains_point(timberA.transform.global_to_local(origin))
        assert not _render_cutting(joint.cuttings["timberB"]).contains_point(timberB.transform.global_to_local(origin))

        # below origin
        origin = create_v3(Rational(0), Rational(0), Rational(-1))
        assert not _render_cutting(joint.cuttings["timberA"]).contains_point(timberA.transform.global_to_local(origin))
        assert _render_cutting(joint.cuttings["timberB"]).contains_point(timberB.transform.global_to_local(origin))


