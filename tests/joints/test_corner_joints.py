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

from kumiki.rule import inches, degrees, are_vectors_parallel, safe_dot_product, normalize_vector
from kumiki.ticket import TimberTicket
from kumiki.cutcsg import Difference, SolidUnion, ConvexPolygonExtrusion
from kumiki.example_shavings import (
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
)
from tests.testing_shavings import (
    create_standard_horizontal_timber,
)

class TestMiterJoint:
    """Test cut_plain_miter_joint function."""

    @staticmethod
    def assert_miter_joint_normals_are_opposite(joint, timberA, timberB):
        """
        Helper function to assert that miter joint cut normals are opposite in global space.
        
        Args:
            joint: The joint result from cut_plain_miter_joint_on_face_aligned_timbers
            timberA: First timber in the joint
            timberB: Second timber in the joint
        """
        # Get the local normals from the cuts
        cut_A_csg = joint.cuttings["timberA"].negative_csg
        cut_B_csg = joint.cuttings["timberB"].negative_csg
        assert isinstance(cut_A_csg, HalfSpace)
        assert isinstance(cut_B_csg, HalfSpace)
        normal_A_local = cut_A_csg.normal
        normal_B_local = cut_B_csg.normal
        
        # Convert to global coordinates
        normal_A_global = timberA.orientation.matrix * normal_A_local
        normal_B_global = timberB.orientation.matrix * normal_B_local
        
        # For a miter joint, the normals should be opposite in global space
        assert normal_A_global.equals(-normal_B_global), "Normals should be opposite in global space"
    
    @staticmethod
    def assert_miter_joint_end_positions_on_boundaries(joint, timberA, timberB):
        """
        Helper function to assert that the end positions of both cut timbers are on the 
        boundaries of both half planes.
        
        For a miter joint, the end position where timber A is cut should lie on the boundary
        of both timber A's cut plane and timber B's cut plane (and vice versa).
        
        Args:
            joint: The joint result from cut_plain_miter_joint_on_face_aligned_timbers
            timberA: First timber in the joint
            timberB: Second timber in the joint
        """
        # Get the end position of the cut on timberA (in global coordinates)
        end_position_A_global = locate_position_on_centerline_from_bottom(timberA, -3).position
        
        # Get the end position of the cut on timberB (in global coordinates)
        end_position_B_global = locate_position_on_centerline_from_bottom(timberB, -3).position
        
        # see that end_position_A_global is NOT in cut timberA but is in cut timberB
        assert not _render_cutting(joint.cuttings["timberA"]).contains_point(timberA.transform.global_to_local(end_position_A_global))
        assert _render_cutting(joint.cuttings["timberB"]).contains_point(timberB.transform.global_to_local(end_position_A_global))
        # see that end_position_B_global is NOT in cut timberB but is in cut timberA
        assert not _render_cutting(joint.cuttings["timberB"]).contains_point(timberB.transform.global_to_local(end_position_B_global))
        assert _render_cutting(joint.cuttings["timberA"]).contains_point(timberA.transform.global_to_local(end_position_B_global))


    @staticmethod
    def get_timber_bottom_position_after_cutting_local(timber: CutTimber) -> V3:
        prism = timber._extended_timber_without_cuts_csg_local()
        assert isinstance(prism, RectangularPrism)
        return prism.get_bottom_position()


    # 🐪
    def test_basic_miter_joint_on_orthoganal_timbers(self):
        """Test basic miter joint on face-aligned timbers."""
        # Create two orthognal timbers meeting at the origin
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        
        # Create miter joint
        arrangement = CornerJointTimberArrangement(
            timber1=timberA, timber2=timberB,
            timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
        )
        joint = cut_plain_miter_joint_on_face_aligned_timbers(arrangement)

        # check very basic stuff
        assert joint is not None
        assert len(joint.cuttings) == 2
        assert joint.cuttings["timberA"].timber == timberA
        assert joint.cuttings["timberA"].get_maybe_bottom_end_cut() is not None
        assert joint.cuttings["timberB"].timber == timberB
        assert joint.cuttings["timberB"].get_maybe_bottom_end_cut() is not None

        # check that the two cuts are Cut objects
        assert isinstance(joint.cuttings["timberA"], Cutting)
        assert isinstance(joint.cuttings["timberB"], Cutting)

        # Convert normals to global space and check if they are opposite
        self.assert_miter_joint_normals_are_opposite(joint, timberA, timberB)

        # Check that the end positions of both cut timbers are on the boundaries of both half planes
        self.assert_miter_joint_end_positions_on_boundaries(joint, timberA, timberB)

        # check that the "corner" point of the miter is contained on the boundary of both half plane
        corner_point_global = create_v3(Rational(-3), Rational(-3), Rational(0))
        corner_point_local_A = timberA.transform.global_to_local(corner_point_global)
        corner_point_local_B = timberB.transform.global_to_local(corner_point_global)
        assert joint.cuttings["timberA"].negative_csg is not None
        assert joint.cuttings["timberB"].negative_csg is not None
        assert joint.cuttings["timberA"].negative_csg.is_point_on_boundary(corner_point_local_A)
        assert joint.cuttings["timberB"].negative_csg.is_point_on_boundary(corner_point_local_B)

        # check that the "bottom" point of timberA (after cutting) is contained in timberB but not timber A
        # This point is at (0, -3, 0) in global coordinates, which is:
        # - On the "cut away" side of timber A (should NOT be contained)
        # - On the "kept" side of timber B (should be contained)
        bottom_point_A_after_cutting_global = create_v3(Rational(0), Rational(-3), Rational(0))
        bottom_point_A_after_cutting_local_A = timberA.transform.global_to_local(bottom_point_A_after_cutting_global)
        bottom_point_A_after_cutting_local_B = timberB.transform.global_to_local(bottom_point_A_after_cutting_global)
        assert joint.cuttings["timberA"].negative_csg is not None
        assert joint.cuttings["timberB"].negative_csg is not None
        assert not joint.cuttings["timberA"].negative_csg.contains_point(bottom_point_A_after_cutting_local_A)
        assert joint.cuttings["timberB"].negative_csg.contains_point(bottom_point_A_after_cutting_local_B)

    # 🐪
    def test_basic_miter_joint_on_various_angles(self): 
        """Test miter joints with timbers at 90-degree angle in various orientations."""
        # Note: cut_plain_miter_joint_on_face_aligned_timbers requires perpendicular timbers (90-degree angle)
        # We test various orientations of perpendicular timber pairs
        
        test_cases = [
            # (timberA_direction, timberB_direction, description)
            ('x', 'y', 'X and Y perpendicular'),
            ('x', '-y', 'X and -Y perpendicular'),
            ('-x', 'y', '-X and Y perpendicular'),
            ('-x', '-y', '-X and -Y perpendicular'),
        ]
        
        for dirA, dirB, description in test_cases:
            # Create timberA and timberB in perpendicular directions
            timberA = create_standard_horizontal_timber(direction=dirA, length=100, size=(6, 6), position=(0, 0, 0))
            timberB = create_standard_horizontal_timber(direction=dirB, length=100, size=(6, 6), position=(0, 0, 0))
            
            # Create miter joint
            arrangement = CornerJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
            )
            joint = cut_plain_miter_joint_on_face_aligned_timbers(arrangement)
            
            # Verify the joint was created
            assert joint is not None, f"Failed to create joint for {description}"
            assert len(joint.cuttings) == 2
            
            # Verify the cuts are Cut objects
            assert isinstance(joint.cuttings["timberA"], Cutting)
            assert isinstance(joint.cuttings["timberB"], Cutting)
            
            # Verify normals are opposite in global space
            self.assert_miter_joint_normals_are_opposite(joint, timberA, timberB)
            
            # Verify end positions are on boundaries of both half planes
            self.assert_miter_joint_end_positions_on_boundaries(joint, timberA, timberB)

    # 🐪
    def test_basic_miter_joint_on_parallel_timbers(self):
        """Test that creating miter joint between parallel timbers raises an error."""
        # Create three timbers: two parallel (+X) and one anti-parallel (-X)
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberC = create_standard_horizontal_timber(direction='-x', length=100, size=(6, 6), position=(0, 0, 0))
        
        # Attempting to create a miter joint between parallel timbers should raise an AssertionError
        # because the function requires perpendicular timbers
        with pytest.raises(AssertionError, match="perpendicular"):
            arrangement = CornerJointTimberArrangement(
                timber1=timberA, timber2=timberB,
                timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
            )
            cut_plain_miter_joint_on_face_aligned_timbers(arrangement)
        
        # Test with anti-parallel timbers as well
        with pytest.raises(AssertionError, match="perpendicular"):
            arrangement = CornerJointTimberArrangement(
                timber1=timberA, timber2=timberC,
                timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM
            )
            cut_plain_miter_joint_on_face_aligned_timbers(arrangement)

    # 🐪
    def test_miter_joint_on_parallel_timbers_produces_perpendicular_cuts(self):
        """cut_plain_miter_joint (base function) accepts parallel timbers and produces end cuts perpendicular to the timber axis."""
        timberA = timber_from_directions(
            length=Rational(100),
            size=Matrix([Rational(6), Rational(6)]),
            bottom_position=Matrix([Rational(0), Rational(0), Rational(0)]),
            length_direction=Matrix([Rational(1), Rational(0), Rational(0)]),
            width_direction=Matrix([Rational(0), Rational(1), Rational(0)]),
        )
        timberB = timber_from_directions(
            length=Rational(100),
            size=Matrix([Rational(6), Rational(6)]),
            bottom_position=Matrix([Rational(0), Rational(0), Rational(10)]),
            length_direction=Matrix([Rational(1), Rational(0), Rational(0)]),
            width_direction=Matrix([Rational(0), Rational(1), Rational(0)]),
        )

        arrangement = CornerJointTimberArrangement(
            timber1=timberA, timber2=timberB,
            timber1_end=TimberEnd.BOTTOM, timber2_end=TimberEnd.BOTTOM,
        )
        joint = cut_plain_miter_joint(arrangement)

        assert joint is not None
        assert len(joint.cuttings) == 2

        for key, timber in [("timberA", timberA), ("timberB", timberB)]:
            cut = joint.cuttings[key]
            end_cut = cut.get_maybe_bottom_end_cut()
            assert end_cut is not None, f"{key} should have a bottom end cut"
            global_normal = timber.orientation.matrix * end_cut.normal
            length_dir = timber.get_length_direction_global()
            dot = simplify(Abs((global_normal.T * length_dir)[0, 0]))
            assert dot == 1, f"{key} end cut should be perpendicular to timber axis, got |dot|={dot}"



class TestTongueAndForkJoint:
    @staticmethod
    def _face_center(timber: Timber, face: TimberFace) -> V3:
        if face == TimberFace.TOP:
            return locate_top_center_position(timber).position
        if face == TimberFace.BOTTOM:
            return locate_bottom_center_position(timber).position

        center = timber.get_bottom_position_global() + timber.get_length_direction_global() * (timber.length / Rational(2))
        if face == TimberFace.RIGHT:
            return center + timber.get_width_direction_global() * (timber.size[0] / Rational(2))
        if face == TimberFace.LEFT:
            return center - timber.get_width_direction_global() * (timber.size[0] / Rational(2))
        if face == TimberFace.FRONT:
            return center + timber.get_height_direction_global() * (timber.size[1] / Rational(2))
        return center - timber.get_height_direction_global() * (timber.size[1] / Rational(2))

    def test_tongue_and_fork_joint_structure_and_opposing_face_end_cuts(self):
        tongue_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))

        arrangement = CornerJointTimberArrangement(
            timber1=tongue_timber,
            timber2=fork_timber,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
        )
        joint = cut_tongue_and_fork_corner_joint(arrangement)

        assert len(joint.cuttings) == 2
        assert "tongue_timber" in joint.cuttings
        assert "fork_timber" in joint.cuttings

        tongue_cut = joint.cuttings["tongue_timber"]
        fork_cut = joint.cuttings["fork_timber"]
        assert tongue_cut.negative_csg is not None
        assert fork_cut.negative_csg is not None
        assert tongue_cut.get_maybe_bottom_end_cut() is not None
        assert fork_cut.get_maybe_bottom_end_cut() is not None

        tongue_end_direction = -tongue_timber.get_length_direction_global()
        fork_entry_face = fork_timber.get_closest_oriented_face_from_global_direction(-tongue_end_direction)
        fork_opposite_face_center = self._face_center(fork_timber, fork_entry_face.get_opposite_face())

        fork_end_direction = -fork_timber.get_length_direction_global()
        tongue_entry_face = tongue_timber.get_closest_oriented_face_from_global_direction(-fork_end_direction)
        tongue_opposite_face_center = self._face_center(tongue_timber, tongue_entry_face.get_opposite_face())

        tongue_distance_from_bottom = safe_dot_product(
            fork_opposite_face_center - tongue_timber.get_bottom_position_global(),
            tongue_timber.get_length_direction_global(),
        )
        expected_tongue_end_cut = Cutting.make_end_cut(
            tongue_timber,
            TimberEnd.BOTTOM,
            tongue_distance_from_bottom,
        )
        actual_tongue_end_cut = tongue_cut.get_maybe_bottom_end_cut()
        assert actual_tongue_end_cut is not None
        assert actual_tongue_end_cut.normal.equals(expected_tongue_end_cut.normal)
        assert actual_tongue_end_cut.offset == expected_tongue_end_cut.offset

        fork_distance_from_bottom = safe_dot_product(
            tongue_opposite_face_center - fork_timber.get_bottom_position_global(),
            fork_timber.get_length_direction_global(),
        )
        expected_fork_end_cut = Cutting.make_end_cut(
            fork_timber,
            TimberEnd.BOTTOM,
            fork_distance_from_bottom,
        )
        actual_fork_end_cut = fork_cut.get_maybe_bottom_end_cut()
        assert actual_fork_end_cut is not None
        assert actual_fork_end_cut.normal.equals(expected_fork_end_cut.normal)
        assert actual_fork_end_cut.offset == expected_fork_end_cut.offset

    def test_tongue_position_changes_kept_tongue_region(self):
        tongue_timber_a = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber_a = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        arrangement_a = CornerJointTimberArrangement(
            timber1=tongue_timber_a,
            timber2=fork_timber_a,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
        )

        joint_centered = cut_tongue_and_fork_corner_joint(arrangement_a)

        tongue_timber_b = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_timber_b = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))
        arrangement_b = CornerJointTimberArrangement(
            timber1=tongue_timber_b,
            timber2=fork_timber_b,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
        )
        joint_shifted = cut_tongue_and_fork_corner_joint(
            arrangement_b,
            tongue_thickness=Rational(2),
            tongue_position=Rational(2),
        )

        plane_normal = arrangement_a.compute_normalized_timber_cross_product()
        tongue_face = tongue_timber_a.get_closest_oriented_long_face_from_global_direction(plane_normal)
        tongue_normal = tongue_timber_a.get_face_direction_global(tongue_face)

        sample_point_global = (
            tongue_timber_a.get_bottom_position_global()
            + tongue_timber_a.get_length_direction_global() * Rational(1)
            + tongue_normal * Rational(0)
        )

        centered_render = _render_cutting(joint_centered.cuttings["tongue_timber"])
        shifted_render = _render_cutting(joint_shifted.cuttings["tongue_timber"])

        assert centered_render.contains_point(tongue_timber_a.transform.global_to_local(sample_point_global))
        assert not shifted_render.contains_point(tongue_timber_b.transform.global_to_local(sample_point_global))

    def test_tongue_and_fork_joint_assertions(self):
        tongue_parallel = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_parallel = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))

        with pytest.raises(AssertionError, match="parallel"):
            cut_tongue_and_fork_corner_joint(
                CornerJointTimberArrangement(
                    timber1=tongue_parallel,
                    timber2=fork_parallel,
                    timber1_end=TimberEnd.BOTTOM,
                    timber2_end=TimberEnd.BOTTOM,
                )
            )

        tongue_non_plane = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        fork_non_plane = timber_from_directions(
            length=Rational(100),
            size=create_v2(6, 6),
            bottom_position=create_v3(0, 0, 0),
            length_direction=create_v3(1, 1, 1),
            width_direction=create_v3(1, -1, 0),
        )

        with pytest.raises(AssertionError, match="plane-aligned"):
            cut_tongue_and_fork_corner_joint(
                CornerJointTimberArrangement(
                    timber1=tongue_non_plane,
                    timber2=fork_non_plane,
                    timber1_end=TimberEnd.BOTTOM,
                    timber2_end=TimberEnd.BOTTOM,
                )
            )



class TestCornerLapJoint:
    def test_corner_lap_joint_has_two_end_cuts_aligned_to_opposing_faces(self):
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))

        arrangement = CornerJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.FRONT,
        )

        joint = cut_plain_corner_lap_joint(arrangement)

        assert len(joint.cuttings) == 2
        cutA = joint.cuttings["timberA"]
        cutB = joint.cuttings["timberB"]
        assert cutA.get_maybe_bottom_end_cut() is not None
        assert cutB.get_maybe_bottom_end_cut() is not None

        timberA_end_direction = -timberA.get_length_direction_global()
        timberB_entry_face = timberB.get_closest_oriented_face_from_global_direction(-timberA_end_direction)
        timberB_far_face_center = get_point_on_face_global(timberB_entry_face.get_opposite_face(), timberB)

        timberB_end_direction = -timberB.get_length_direction_global()
        timberA_entry_face = timberA.get_closest_oriented_face_from_global_direction(-timberB_end_direction)
        timberA_far_face_center = get_point_on_face_global(timberA_entry_face.get_opposite_face(), timberA)

        expected_A_distance = safe_dot_product(
            timberB_far_face_center - timberA.get_bottom_position_global(),
            timberA.get_length_direction_global(),
        )
        expected_B_distance = safe_dot_product(
            timberA_far_face_center - timberB.get_bottom_position_global(),
            timberB.get_length_direction_global(),
        )

        expected_A_end_cut = Cutting.make_end_cut(timberA, TimberEnd.BOTTOM, expected_A_distance)
        expected_B_end_cut = Cutting.make_end_cut(timberB, TimberEnd.BOTTOM, expected_B_distance)

        actual_A_end_cut = cutA.get_maybe_bottom_end_cut()
        actual_B_end_cut = cutB.get_maybe_bottom_end_cut()
        assert actual_A_end_cut is not None
        assert actual_B_end_cut is not None
        assert actual_A_end_cut.normal.equals(expected_A_end_cut.normal)
        assert actual_A_end_cut.offset == expected_A_end_cut.offset
        assert actual_B_end_cut.normal.equals(expected_B_end_cut.normal)
        assert actual_B_end_cut.offset == expected_B_end_cut.offset




# ============================================================================
# Helpers for TestMiteredAndKeyedLapJoint
# ============================================================================

def _make_right_angle_arrangement(front_face=TimberLongFace.RIGHT, position=None):
    from dataclasses import replace as dc_replace
    arrangement = create_canonical_example_right_angle_corner_joint_timbers(position=position)
    timberA = dc_replace(arrangement.timber1, ticket=TimberTicket("timberA"))
    timberB = dc_replace(arrangement.timber2, ticket=TimberTicket("timberB"))
    return dc_replace(arrangement, timber1=timberA, timber2=timberB, front_face_on_timber1=front_face)


def _make_angled_arrangement(angle_deg, front_face=TimberLongFace.RIGHT, position=None):
    from dataclasses import replace as dc_replace
    arrangement = create_canonical_example_corner_joint_timbers(
        corner_angle=degrees(Integer(angle_deg)), position=position
    )
    timberA = dc_replace(arrangement.timber1, ticket=TimberTicket("timberA"))
    timberB = dc_replace(arrangement.timber2, ticket=TimberTicket("timberB"))
    return dc_replace(arrangement, timber1=timberA, timber2=timberB, front_face_on_timber1=front_face)


def _assert_joint_structure(joint, num_keys, num_laps):
    assert joint is not None
    assert len(joint.cuttings) == 2
    assert "timberA" in joint.cuttings
    assert "timberB" in joint.cuttings
    assert isinstance(joint.cuttings["timberA"], Cutting)
    assert isinstance(joint.cuttings["timberB"], Cutting)
    expected_keys = num_laps - 1
    assert len(joint.jointAccessories) == expected_keys, (
        f"Expected {expected_keys} key accessories for {num_laps} laps, "
        f"got {len(joint.jointAccessories)}"
    )
    for i in range(expected_keys):
        assert f"key_{i}" in joint.jointAccessories
        assert isinstance(joint.jointAccessories[f"key_{i}"], Wedge)


def _assert_end_cuts_match_arrangement(joint, arrangement):
    cutA = joint.cuttings["timberA"]
    cutB = joint.cuttings["timberB"]
    if arrangement.timber1_end == TimberEnd.TOP:
        assert cutA.get_maybe_top_end_cut() is not None
        assert cutA.get_maybe_bottom_end_cut() is None
    else:
        assert cutA.get_maybe_bottom_end_cut() is not None
        assert cutA.get_maybe_top_end_cut() is None
    if arrangement.timber2_end == TimberEnd.TOP:
        assert cutB.get_maybe_top_end_cut() is not None
        assert cutB.get_maybe_bottom_end_cut() is None
    else:
        assert cutB.get_maybe_bottom_end_cut() is not None
        assert cutB.get_maybe_top_end_cut() is None


def _assert_miter_boundary_point(joint, timberA, timberB, point_global):
    def _render_cutting(cutting):
        return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()
    csgA = _render_cutting(joint.cuttings["timberA"])
    csgB = _render_cutting(joint.cuttings["timberB"])
    ptA = timberA.transform.global_to_local(point_global)
    ptB = timberB.transform.global_to_local(point_global)
    assert csgA.is_point_on_boundary(ptA)
    assert csgB.is_point_on_boundary(ptB)


class TestMiteredAndKeyedLapJoint:
    """Test cut_mitered_and_keyed_lap_joint function."""

    def test_basic_right_angle_joint(self):
        """Test basic joint at 90 degrees — structure, end cuts, accessories, miter separation."""
        arrangement = _make_right_angle_arrangement()
        timberA = arrangement.timber1
        timberB = arrangement.timber2
        num_laps = 3

        joint = cut_mitered_and_keyed_lap_joint(
            arrangement=arrangement,
            num_laps=num_laps,
            lap_thickness=inches(Rational(3, 4)),
            lap_start_distance_from_reference_miter_face=inches(Rational(1, 2)),
            distance_between_lap_and_outside=inches(Rational(1, 2)),
        )

        _assert_joint_structure(joint, num_keys=num_laps - 1, num_laps=num_laps)
        _assert_end_cuts_match_arrangement(joint, arrangement)

        # Both timbers should be renderable without error
        csgA = _render_cutting(joint.cuttings["timberA"])
        csgB = _render_cutting(joint.cuttings["timberB"])
        assert csgA is not None
        assert csgB is not None

        
        # Each key wedge accessory has a transform; its position center should
        # be in the void (not contained in either timber).
        for key_name, accessory in joint.jointAccessories.items():
            assert isinstance(accessory, Wedge)
            key_center_global = accessory.transform.position
            ptA = timberA.transform.global_to_local(key_center_global)
            ptB = timberB.transform.global_to_local(key_center_global)
            assert not csgA.contains_point(ptA), (
                f"{key_name} center should not be inside timberA (key void)"
            )
            assert not csgB.contains_point(ptB), (
                f"{key_name} center should not be inside timberB (key void)"
            )

        # TODO test finger locations and keys


    def test_multiple_angles(self):
        """Test that the joint is constructable at several valid angles."""
        for angle_deg in [60, 75, 90, 110, 130]:
            arrangement = _make_angled_arrangement(angle_deg)
            joint = cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=2,
            )
            _assert_joint_structure(joint, num_keys=1, num_laps=2)
            _assert_end_cuts_match_arrangement(joint, arrangement)

            # Ensure renderable
            csgA = _render_cutting(joint.cuttings["timberA"])
            csgB = _render_cutting(joint.cuttings["timberB"])
            assert csgA is not None
            assert csgB is not None
        
        # TODO test finger locations and keys

    # ------------------------------------------------------------------
    # Parameter variation tests
    # ------------------------------------------------------------------

    def test_num_laps_2_produces_one_key(self):
        """Minimum valid num_laps=2 should produce exactly 1 key."""
        arrangement = _make_right_angle_arrangement()
        joint = cut_mitered_and_keyed_lap_joint(
            arrangement=arrangement,
            num_laps=2,
        )
        _assert_joint_structure(joint, num_keys=1, num_laps=2)

    def test_num_laps_4_produces_three_keys(self):
        """num_laps=4 should produce exactly 3 keys."""
        arrangement = _make_right_angle_arrangement()
        joint = cut_mitered_and_keyed_lap_joint(
            arrangement=arrangement,
            num_laps=4,
        )
        _assert_joint_structure(joint, num_keys=3, num_laps=4)

    # ------------------------------------------------------------------
    # Error / validation tests
    # ------------------------------------------------------------------


    # 🐪
    def test_num_laps_below_2_raises(self):
        """num_laps < 2 should raise ValueError."""
        arrangement = _make_right_angle_arrangement()
        with pytest.raises(ValueError, match="num_laps must be at least 2"):
            cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=1,
            )

    # 🐪
    def test_angle_too_shallow_raises(self):
        """Angles below 45 degrees should raise ValueError."""
        arrangement = _make_angled_arrangement(30)
        with pytest.raises(ValueError, match="Angle between timbers"):
            cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=2,
            )

    # 🐪
    def test_parallel_timbers_raises(self):
        """Parallel timbers (angle ~0 or ~180) should raise."""
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(4, 5), position=(0, 0, 0), ticket="timberA")
        timberB = create_standard_horizontal_timber(direction='x', length=100, size=(4, 5), position=(0, 0, 0), ticket="timberB")

        arrangement = CornerJointTimberArrangement(
            timber1=timberA,
            timber2=timberB,
            timber1_end=TimberEnd.BOTTOM,
            timber2_end=TimberEnd.BOTTOM,
            front_face_on_timber1=TimberLongFace.RIGHT,
        )
        with pytest.raises((ValueError, AssertionError)):
            cut_mitered_and_keyed_lap_joint(
                arrangement=arrangement,
                num_laps=2,
            )


# ============================================================================
# Tests for cut_dropin_dovetail_butt_joint
# ============================================================================


def _make_butt_arrangement(front_face=TimberLongFace.RIGHT):
    """Create a canonical butt joint arrangement with the given front face."""
    from dataclasses import replace as dc_replace
    return dc_replace(
        create_canonical_example_butt_joint_timbers(),
        front_face_on_butt_timber=front_face,
    )


def _make_simple_butt_arrangement():
    """
    Create a butt joint arrangement with simple integer coordinates (no unit conversion).

    - Receiving timber (post): vertical along +Z, height 100, size (8, 8), at origin.
      Cross-section: x ∈ [-4, 4], y ∈ [-4, 4].
    - Dovetail timber (beam): horizontal along +X, length 100, size (8, 8),
      bottom at (-100, 0, 50). Cross-section: y ∈ [-4, 4], z ∈ [46, 54].
    - butt_timber_end = TOP (x=0)
    - front_face_on_butt_timber = RIGHT (+Y, perpendicular to post length +Z)
    """
    from tests.testing_shavings import create_standard_vertical_timber
    post = create_standard_vertical_timber(height=100, size=(8, 8), position=(0, 0, 0), ticket="receiving_timber")
    beam = create_standard_horizontal_timber(
        direction='x', length=100, size=(8, 8), position=(-100, 0, 50), ticket="butt_timber",
    )
    return ButtJointTimberArrangement(
        butt_timber=beam,
        receiving_timber=post,
        butt_timber_end=TimberEnd.TOP,
        front_face_on_butt_timber=TimberLongFace.RIGHT,
    )


