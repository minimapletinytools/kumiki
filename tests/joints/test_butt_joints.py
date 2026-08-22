"""
Tests for Kumiki timber framing system
"""

import pytest
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber
)


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()

from kumiki.rule import inches, degrees, are_vectors_parallel, safe_dot_product, safe_normalize_vector
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

class TestButtJoint:
    """Test cut_plain_butt_joint_on_face_aligned_timbers function."""

    # 🐪
    def test_basic_butt_joint_on_face_aligned_timbers(self):
        """Test butt joint between two perpendicular timbers."""
        # Create two perpendicular timbers meeting at the origin
        # timberA extends along +X (bottom at origin, top at x=100)
        # timberB extends along +Y (bottom at origin, top at y=100)
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, 0, 0))

        # Create butt joint - timberB butts into timberA at timberB's BOTTOM end
        arrangement = ButtJointTimberArrangement(
            butt_timber=timberB,
            receiving_timber=timberA,
            butt_timber_end=TimberEnd.BOTTOM
        )
        joint = cut_plain_butt_joint_on_face_aligned_timbers(arrangement)

        # Verify joint structure
        assert joint is not None
        assert len(joint.cuttings) == 2
        assert joint.cuttings["receiving_timber"].timber == timberA
        assert joint.cuttings["butt_timber"].timber == timberB

        # In strict mode each member has one Cutting; receiving member is a no-op cut.
        receiving_cut = joint.cuttings["receiving_timber"]
        assert receiving_cut.negative_csg is None, "Receiving timber should carry a no-op cut"
        assert receiving_cut.get_maybe_top_end_cut() is None
        assert receiving_cut.get_maybe_bottom_end_cut() is None

        # The butt timber (timberB) has the actual end-cutting.
        assert isinstance(joint.cuttings["butt_timber"], Cutting)
        assert joint.cuttings["butt_timber"].get_maybe_bottom_end_cut() is not None

        # Verify the cut is a Cut object
        assert isinstance(joint.cuttings["butt_timber"], Cutting)

        # Verify that the cut normal in global space is parallel or anti-parallel to timberB's length direction
        # For an end cut (butt joint), the cut plane is perpendicular to the timber's length axis,
        # so the normal is parallel/anti-parallel to the length direction
        cut_csg_local = joint.cuttings["butt_timber"].get_negative_csg_local()
        assert isinstance(cut_csg_local, HalfSpace), "Expected cut to be a HalfSpace"
        cut_normal_local = cut_csg_local.normal
        cut_normal_global = timberB.orientation.matrix * cut_normal_local
        
        dot_with_length = (cut_normal_global.T * timberB.get_length_direction_global())[0, 0]
        assert simplify(Abs(dot_with_length)) == 1, \
            "Cut normal should be parallel or anti-parallel to butt timber's length direction"
        
        # Verify the cut creates a valid CSG geometry
        # (this is a basic sanity check that the cut can be rendered)
        try:
            csg = _render_cutting(joint.cuttings["butt_timber"])
            assert csg is not None, "Should be able to render the cut timber"
        except Exception as e:
            pytest.fail(f"Failed to render cut timber: {e}")

        # pick a point that's on the boundary of the butt joint
        joint_point_global = create_v3(scalar(0), scalar(3), scalar(0))

        assert _render_cutting(joint.cuttings["receiving_timber"]).is_point_on_boundary(timberA.transform.global_to_local(joint_point_global))
        assert _render_cutting(joint.cuttings["butt_timber"]).is_point_on_boundary(timberB.transform.global_to_local(joint_point_global))
        



    # 🐪
    def test_basic_butt_joint_on_parallel_timbers(self):
        """Test that creating butt joint between parallel timbers raises an error.
        
        The cut_plain_butt_joint_on_face_aligned_timbers function validates that timbers
        are not parallel, as butt joints require timbers at an angle.
        """
        # Create three timbers: two parallel (+X) and one anti-parallel (-X)
        timberA = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberB = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        timberC = create_standard_horizontal_timber(direction='-x', length=100, size=(6, 6), position=(0, 0, 0))
        
        # Attempting to create a butt joint between parallel timbers should raise an AssertionError
        # because the function requires perpendicular timbers
        with pytest.raises(AssertionError, match="parallel"):
            arrangement = ButtJointTimberArrangement(
                butt_timber=timberB,
                receiving_timber=timberA,
                butt_timber_end=TimberEnd.BOTTOM
            )
            cut_plain_butt_joint_on_face_aligned_timbers(arrangement)
        
        # Test with anti-parallel timbers as well
        with pytest.raises(AssertionError, match="parallel"):
            arrangement = ButtJointTimberArrangement(
                butt_timber=timberC,
                receiving_timber=timberA,
                butt_timber_end=TimberEnd.BOTTOM
            )
            cut_plain_butt_joint_on_face_aligned_timbers(arrangement)

    # 🐪
    def test_butt_joint_aabb_matches_rough_cut_length(self):
        """Test that AABB bounding box length matches the rough cut length of the butt timber.
        
        Creates a butt joint with a random-length timber, renders the CSG,
        gets its AABB bounding box, extracts the length dimension, and verifies
        it matches the rough cut length of the butting timber.

        This is really to test various length computation means are consistent, and not so much to test this particular joint.
        """
        import random
        
        # Create a random timber length between 50 and 150 units
        random_length = scalar(random.randint(50, 150))
        
        # Create two perpendicular timbers
        # timberA (receiving) extends along +X
        timberA = create_standard_horizontal_timber(
            direction='x', 
            length=int(random_length) + 20,  # Slightly longer to receive the joint
            size=(6, 6), 
            position=(0, 0, 0)
        )
        
        # timberB (butt timber) extends along +Y with our random length
        timberB = create_standard_horizontal_timber(
            direction='y', 
            length=int(random_length), 
            size=(6, 6), 
            position=(0, 0, 0)
        )
        
        # Create butt joint - timberB butts into timberA at timberB's BOTTOM end
        arrangement = ButtJointTimberArrangement(
            butt_timber=timberB,
            receiving_timber=timberA,
            butt_timber_end=TimberEnd.BOTTOM
        )
        joint = cut_plain_butt_joint_on_face_aligned_timbers(arrangement)
        
        # Get the cut butt timber
        cut_butt_timber = joint.cuttings["butt_timber"]
        
        # Use the analytical finite bounding prism for dimensional checks.
        # render_timber_with_cuts_csg_local() starts from an intentionally
        # extended (possibly infinite) base CSG when end-cuts are present.
        bbox_prism = CutTimber(cut_butt_timber.timber, cuts=[cut_butt_timber]).get_perfect_timber_within_bounding_box_prism()
        bbox = bbox_prism.get_aabb()
        
        # Verify bbox is valid (not unbounded)
        assert bbox.min_x is not None, "AABB should be bounded in X"
        assert bbox.min_y is not None, "AABB should be bounded in Y"
        assert bbox.min_z is not None, "AABB should be bounded in Z"
        assert bbox.max_x is not None, "AABB should be bounded in X"
        assert bbox.max_y is not None, "AABB should be bounded in Y"
        assert bbox.max_z is not None, "AABB should be bounded in Z"
        
        assert bbox_prism.start_distance is not None
        assert bbox_prism.end_distance is not None

        # Get length from the finite local z-extents.
        aabb_length = bbox_prism.end_distance - bbox_prism.start_distance
        
        # Get the rough cut length from the cutting
        # For a BOTTOM end cut, get the distance from bottom to cut plane
        cutting = cut_butt_timber
        bottom_end_cut = cutting.get_maybe_bottom_end_cut()
        
        assert bottom_end_cut is not None, "Butt joint should have a bottom end cut"
        
        # For a BOTTOM cut at distance d, remaining local z-range is [d, length],
        # so rough-cut length is length - d.
        rough_cut_distance = -bottom_end_cut.offset
        expected_rough_cut_length = cut_butt_timber.timber.length - rough_cut_distance

        assert bbox_prism.start_distance == rough_cut_distance, \
            f"Bounding prism start {bbox_prism.start_distance} should match bottom cut distance {rough_cut_distance}"
        assert aabb_length == expected_rough_cut_length, \
            f"AABB length {aabb_length} should equal rough cut length {expected_rough_cut_length}"



class TestTongueAndForkButtJoint:
    def test_tongue_and_fork_butt_joint_structure_and_no_tongue_end_cut(self):
        """
        Verify the butt variant produces the right structure:
        - Fork timber (butt timber) gets a slot and an end cut.
        - Tongue timber (receiving timber) gets cheek removal and NO end cut.
        """
        fork_butt_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        tongue_rec_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, -50, 0))

        arrangement = ButtJointTimberArrangement(
            butt_timber=fork_butt_timber,
            receiving_timber=tongue_rec_timber,
            butt_timber_end=TimberEnd.TOP,
        )
        joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(arrangement)

        assert len(joint.cuttings) == 2
        assert "tongue_timber" in joint.cuttings
        assert "fork_timber" in joint.cuttings

        tongue_cut = joint.cuttings["tongue_timber"]
        fork_cut = joint.cuttings["fork_timber"]

        # Fork timber (butt timber) has slot and end cut
        assert fork_cut.negative_csg is not None
        assert fork_cut.get_maybe_top_end_cut() is not None

        # Tongue timber (receiving timber) has cheek removal but NO end cut
        assert tongue_cut.negative_csg is not None
        assert tongue_cut.get_maybe_top_end_cut() is None
        assert tongue_cut.get_maybe_bottom_end_cut() is None

        # Verify cuts produce valid CSG
        tongue_csg = _render_cutting(joint.cuttings["tongue_timber"])
        fork_csg = _render_cutting(joint.cuttings["fork_timber"])
        assert tongue_csg is not None
        assert fork_csg is not None

    def test_tongue_and_fork_butt_joint_angled_end_cut_extends_to_furthest_tip(self):
        """
        Verify that for an angled joint, the end cut distance extends further out than
        the centerline intersection distance to encompass the full angled cut.
        """
        from patterns.butt_joints_patterns import make_tongue_and_fork_butt_joint_angled_example
        cut_timbers = make_tongue_and_fork_butt_joint_angled_example(create_v3(0, 0, 0))
        fork_cut_timber = [ct for ct in cut_timbers if "butt" in str(ct.timber.ticket)][0]
        fork_cut = fork_cut_timber.cuts[0]

        assert fork_cut.maybe_bottom_end_cut_distance_from_bottom is not None
        # At 138 degrees, the furthest tip distance is strictly less (further into joint / further out from top)
        # than the centerline intersection distance
        assert safe_compare(fork_cut.maybe_bottom_end_cut_distance_from_bottom, 0, Comparison.LT)

    def test_tongue_and_fork_butt_joint_shoulder_inset(self):
        """
        Verify that shoulder_inset recesses the shoulder plane into the receiving timber,
        housing the fork timber's stem and forming the tongue deeper inside.
        """
        fork_butt_timber = create_standard_horizontal_timber(direction='x', length=100, size=(6, 6), position=(0, 0, 0))
        tongue_rec_timber = create_standard_horizontal_timber(direction='y', length=100, size=(6, 6), position=(0, -50, 0))

        arrangement = ButtJointTimberArrangement(
            butt_timber=fork_butt_timber,
            receiving_timber=tongue_rec_timber,
            butt_timber_end=TimberEnd.TOP,
        )
        joint = cut_tongue_and_fork_butt_joint_on_plane_aligned_timbers(
            arrangement=arrangement,
            shoulder_inset=inches(1),
        )

        assert len(joint.cuttings) == 2
        tongue_cut = joint.cuttings["tongue_timber"]
        fork_cut = joint.cuttings["fork_timber"]

        assert tongue_cut.negative_csg is not None
        assert fork_cut.negative_csg is not None

        tongue_csg = _render_cutting(tongue_cut)
        fork_csg = _render_cutting(fork_cut)
        assert tongue_csg is not None
        assert fork_csg is not None




# NOTE: mortise-and-tenon joint tests (TestMortiseAndTenonGeometry, TestMortiseAndTenonRelativeTenonSizing,
# TestPegStuff, TestMortiseAndTenonCSGHierarchy, TestWedgedHalfDovetailMortiseAndTenonJoint) live in
# test_mortise_and_tenon_joints.py now.
# ============================================================================
# Helpers for TestHousedDovetailButtJoint
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
    - Dovetail timber (beam): horizontal along +X, length 100, size (8, 8),
      bottom at (-100, 0, 50).
    """
    from tests.testing_shavings import create_standard_vertical_timber, create_standard_horizontal_timber
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


class TestHousedDovetailButtJoint:
    """Test cut_dropin_dovetail_butt_joint_on_face_aligned_timbers function."""

    def test_general_dropin_dovetail_butt_joint(self):
        """
        General test: create the joint with normal parameters, validate structure
        (cut counts, CSG types, end cuts), then walk key points through the geometry.

        Simple arrangement (no unit conversion):
        - receiving_timber (post): +Z, size 8×8, at origin
        - butt_timber (beam): +X, size 8×8, bottom at (-100, 0, 50), TOP end at x=0
        - front_face_on_butt_timber = RIGHT (+Y)

        Post LEFT face at x=-4.  shoulder_distance_from_end = 4 - 1 = 3.
        Shoulder in global: x = 0 - 3 = -3.
        dovetail_depth = 8/2 = 4 (from RIGHT face y=+4 inward to y=0).
        Dovetail profile: narrow (small_width=2) at shoulder x=-3,
        widening (large_width=4) toward x=1 (past end, clipped by timber body at x=0).
        At x=-1: profile width ≈ 3, Z ∈ [48.5, 51.5], Y ∈ [0, 4].
        """
        arrangement = _make_simple_butt_arrangement()
        dovetail_timber = arrangement.butt_timber
        receiving_timber = arrangement.receiving_timber

        joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=scalar(1),
            dovetail_length=scalar(4),
            dovetail_small_width=scalar(2),
            dovetail_large_width=scalar(4),
        )

        # ---- structure ----
        assert len(joint.cuttings) == 2
        assert dovetail_timber.ticket.path in joint.cuttings
        assert receiving_timber.ticket.path in joint.cuttings
        assert joint.ticket is not None
        assert joint.ticket.joint_type == "housed_dovetail_butt"
        assert len(joint.jointAccessories) == 0

        dt_cut = joint.cuttings[dovetail_timber.ticket.path]
        recv_cut = joint.cuttings[receiving_timber.ticket.path]

        # Dovetail timber: 1 cut, end cut at TOP, negative CSG = Difference(housing, profile)
        assert isinstance(dt_cut, Cutting)
        assert dt_cut.get_maybe_top_end_cut() is not None
        assert dt_cut.get_maybe_bottom_end_cut() is None
        assert isinstance(dt_cut.negative_csg, Difference)

        # Receiving timber: 1 cut, no end cuts, with inset > 0 → SolidUnion(notch, socket)
        assert isinstance(recv_cut, Cutting)
        assert recv_cut.get_maybe_top_end_cut() is None
        assert recv_cut.get_maybe_bottom_end_cut() is None
        assert isinstance(recv_cut.negative_csg, SolidUnion)

        # ---- render both timbers ----
        dt_csg = _render_cutting(dt_cut)
        recv_csg = _render_cutting(recv_cut)

        def in_dt(pt):
            return dt_csg.contains_point(dovetail_timber.transform.global_to_local(pt))

        def in_recv(pt):
            return recv_csg.contains_point(receiving_timber.transform.global_to_local(pt))

        # TODO use formula based on dovetail joint sizing parameters rather than hardcoded numbers
        # ---- walk a line along the dovetail timber centerline ----

        # Well inside the beam body (far from joint, x=-50)
        assert in_dt(create_v3(scalar(-50), 0, scalar(50)))
        # Past the dovetail end (x=5, well beyond TOP at x=0)
        assert not in_dt(create_v3(scalar(5), 0, scalar(50)))

        # ---- walk a line perpendicular to the dovetail face at x=-1 ----
        # At x=-1 (in the housing region between shoulder x=-3 and end x=0):
        #   profile width ≈ 3, Z ∈ [48.5, 51.5], Y depth ∈ [0, 4]

        # Inside the dovetail tenon: y=1 ∈ [0,4], z=50 ∈ [48.5,51.5]
        tenon_pt = create_v3(scalar(-1), scalar(1), scalar(50))
        assert in_dt(tenon_pt), "Point inside dovetail tenon should be in dovetail timber"
        assert not in_recv(tenon_pt), "Point inside dovetail socket should not be in receiving timber"

        # On the opposite side of the dovetail depth: y=-1 ∉ [0,4]
        void_pt = create_v3(scalar(-1), scalar(-1), scalar(50))
        assert not in_dt(void_pt), "Point in housing void should not be in dovetail timber"
        assert in_recv(void_pt), "Point outside socket should still be in receiving timber"

        # Outside the dovetail width: z=53 ∉ [48.5,51.5]
        outside_width_pt = create_v3(scalar(-1), scalar(1), scalar(53))
        assert not in_dt(outside_width_pt), "Point outside dovetail width should not be in dovetail timber"
        assert in_recv(outside_width_pt), "Point outside socket width should be in receiving timber"

        # ---- receiving timber body far from the joint ----
        assert in_recv(create_v3(0, 0, scalar(10)))
        assert not in_dt(create_v3(0, 0, scalar(10)))

        # ---- before shoulder, full cross-section is intact ----
        body_near_shoulder = create_v3(scalar(-5), scalar(-1), scalar(50))
        assert in_dt(body_near_shoulder), "Full cross-section before shoulder should be intact"

    def test_multiple_orientations(self):
        """Test that the joint is constructable in several timber orientation combos."""
        test_cases = [
            # (butt_dir, recv_dir, butt_end, front_face)
            ('y', 'x', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('-y', 'x', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', 'y', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', '-y', TimberEnd.TOP, TimberLongFace.FRONT),
        ]

        for butt_dir, recv_dir, butt_end, front_face in test_cases:
            butt = create_standard_horizontal_timber(
                direction=butt_dir, length=100, size=(6, 6),
                position=(0, 0, 0), ticket="butt_timber",
            )
            recv = create_standard_horizontal_timber(
                direction=recv_dir, length=100, size=(6, 6),
                position=(0, 0, 0), ticket="receiving_timber",
            )

            arrangement = ButtJointTimberArrangement(
                butt_timber=butt,
                receiving_timber=recv,
                butt_timber_end=butt_end,
                front_face_on_butt_timber=front_face,
            )

            joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=scalar(1),
                dovetail_length=scalar(3),
                dovetail_small_width=scalar(3, 2),
                dovetail_large_width=scalar(3),
            )

            assert len(joint.cuttings) == 2
            # Both timbers should be renderable
            _render_cutting(joint.cuttings["butt_timber"])
            _render_cutting(joint.cuttings["receiving_timber"])

    def test_zero_shoulder_inset(self):
        """With shoulder_inset=0 receiving timber has no shoulder notch (no SolidUnion)."""
        arrangement = _make_butt_arrangement()

        joint = cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=scalar(0),
            dovetail_length=scalar(3),
            dovetail_small_width=scalar(3, 2),
            dovetail_large_width=scalar(3),
        )

        recv_neg_csg = joint.cuttings[arrangement.receiving_timber.ticket.path].negative_csg
        assert not isinstance(recv_neg_csg, SolidUnion), \
            "With zero inset, receiving negative CSG should be the socket alone (no SolidUnion)"

    # 🐪
    def test_validation_errors(self):
        """Test that invalid parameters raise ValueErrors."""
        arrangement = _make_butt_arrangement()

        with pytest.raises(ValueError, match="dovetail_length must be positive"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(0), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(3),
            )

        with pytest.raises(ValueError, match="dovetail_small_width must be positive"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(3), dovetail_small_width=scalar(-1), dovetail_large_width=scalar(3),
            )

        with pytest.raises(ValueError, match="dovetail_large_width.*must be greater"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(3), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(1),
            )

        with pytest.raises(ValueError, match="receiving_timber_shoulder_inset must be non-negative"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(-1),
                dovetail_length=scalar(3), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(3),
            )

        with pytest.raises(ValueError, match="dovetail_depth must be positive"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1, 2),
                dovetail_length=scalar(3), dovetail_small_width=scalar(3, 2), dovetail_large_width=scalar(3),
                dovetail_depth=scalar(0),
            )

    def test_parallel_face_raises(self):
        """Front face parallel to receiving length direction should raise ValueError."""
        butt = create_standard_horizontal_timber(
            direction='y', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="butt_timber",
        )
        recv = create_standard_horizontal_timber(
            direction='x', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="receiving_timber",
        )
        # For butt 'y': RIGHT face is +X, which is parallel to recv length +X
        arrangement = ButtJointTimberArrangement(
            butt_timber=butt,
            receiving_timber=recv,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=TimberLongFace.RIGHT,
        )
        with pytest.raises(ValueError, match="perpendicular to receiving timber length"):
            cut_dropin_dovetail_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=scalar(1),
                dovetail_length=scalar(3),
                dovetail_small_width=scalar(3, 2),
                dovetail_large_width=scalar(3),
            )


class TestHousedButtJoint:
    """Test cut_dropin_housed_butt_joint_on_face_aligned_timbers function."""

    def test_general_dropin_housed_butt_joint(self):
        """
        General test: create the joint with normal parameters, validate structure,
        and verify point membership.
        """
        arrangement = _make_simple_butt_arrangement()
        housed_timber = arrangement.butt_timber
        receiving_timber = arrangement.receiving_timber

        joint = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            receiving_timber_shoulder_inset=scalar(1),
            housing_length=scalar(4),
            housing_width=scalar(3),
            housing_depth=scalar(3),
        )

        # ---- structure ----
        assert len(joint.cuttings) == 2
        assert housed_timber.ticket.path in joint.cuttings
        assert receiving_timber.ticket.path in joint.cuttings
        assert joint.ticket is not None
        assert joint.ticket.joint_type == "housed_butt"

        housed_cut = joint.cuttings[housed_timber.ticket.path]
        recv_cut = joint.cuttings[receiving_timber.ticket.path]

        assert isinstance(housed_cut, Cutting)
        assert housed_cut.get_maybe_top_end_cut() is not None
        assert isinstance(housed_cut.negative_csg, Difference)

        assert isinstance(recv_cut, Cutting)
        assert isinstance(recv_cut.negative_csg, SolidUnion)

        # Render cuts
        housed_csg = _render_cutting(housed_cut)
        recv_csg = _render_cutting(recv_cut)

        def in_housed(pt):
            return housed_csg.contains_point(housed_timber.transform.global_to_local(pt))

        def in_recv(pt):
            return recv_csg.contains_point(receiving_timber.transform.global_to_local(pt))

        # Far from joint
        assert in_housed(create_v3(scalar(-50), 0, scalar(50)))
        # Past the end
        assert not in_housed(create_v3(scalar(5), 0, scalar(50)))

    def test_multiple_orientations(self):
        """Test that the joint is constructable in several timber orientation combos."""
        test_cases = [
            ('y', 'x', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('-y', 'x', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', 'y', TimberEnd.BOTTOM, TimberLongFace.FRONT),
            ('x', '-y', TimberEnd.TOP, TimberLongFace.FRONT),
        ]

        for butt_dir, recv_dir, butt_end, front_face in test_cases:
            butt = create_standard_horizontal_timber(
                direction=butt_dir, length=100, size=(6, 6),
                position=(0, 0, 0), ticket="butt_timber",
            )
            recv = create_standard_horizontal_timber(
                direction=recv_dir, length=100, size=(6, 6),
                position=(0, 0, 0), ticket="receiving_timber",
            )

            arrangement = ButtJointTimberArrangement(
                butt_timber=butt,
                receiving_timber=recv,
                butt_timber_end=butt_end,
                front_face_on_butt_timber=front_face,
            )

            joint = cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement,
                receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(4),
                housing_width=scalar(3),
                housing_depth=scalar(3),
            )
            assert len(joint.cuttings) == 2

    def test_validation_errors(self):
        """Verify parameter range checks."""
        arrangement = _make_simple_butt_arrangement()

        with pytest.raises(ValueError, match="housing_length must be positive"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(0), housing_width=scalar(3),
            )

        with pytest.raises(ValueError, match="housing_width must be positive"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(4), housing_width=scalar(0),
            )

        with pytest.raises(ValueError, match="receiving_timber_shoulder_inset must be non-negative"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(-1),
                housing_length=scalar(4), housing_width=scalar(3),
            )

        with pytest.raises(ValueError, match="housing_depth must be positive"):
            cut_dropin_housed_butt_joint_on_face_aligned_timbers(
                arrangement=arrangement, receiving_timber_shoulder_inset=scalar(1),
                housing_length=scalar(4), housing_width=scalar(3),
                housing_depth=scalar(0),
            )

    def test_basic_dropin_housed_butt_joint(self):
        """Test the cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers convenience wrapper."""
        butt = create_standard_horizontal_timber(
            direction='y', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="butt_timber",
        )
        recv = create_standard_horizontal_timber(
            direction='x', length=100, size=(6, 6),
            position=(0, 0, 0), ticket="receiving_timber",
        )
        joint = cut_basic_dropin_housed_butt_joint_on_face_aligned_timbers(
            housed_timber=butt,
            receiving_timber=recv,
            housed_timber_end=TimberEnd.BOTTOM,
            housed_timber_face=TimberLongFace.FRONT,
        )
        assert len(joint.cuttings) == 2
        assert joint.ticket.joint_type == "housed_butt"



