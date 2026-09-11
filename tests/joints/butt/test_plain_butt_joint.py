"""
Tests for Kumiki timber framing system
"""

import pytest
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber,
)
from kumiki.rule import inches, degrees, are_vectors_parallel, safe_dot_product, safe_normalize_vector
from kumiki.ticket import TimberTicket
from kumiki.cutcsg import Difference, SolidUnion, ConvexPolygonExtrusion, RectangularPrism, HalfSpace
from kumiki.example_shavings import (
    create_canonical_example_butt_joint_timbers,
    create_canonical_example_corner_joint_timbers,
    create_canonical_example_right_angle_corner_joint_timbers,
)


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()

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
        # A cutting wraps what it removes in a SolidUnion of its own; the end
        # cut is the single plane inside it.
        cut_csg = joint.cuttings["butt_timber"].get_negative_csg_local()
        assert isinstance(cut_csg, SolidUnion)
        cut_csg_local = cut_csg.children[0]
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



