"""
Tests for Wedged Half-Dovetail Mortise and Tenon Joint
"""

import pytest
from kumiki import *
from tests.testing_shavings import (
    create_standard_vertical_timber,
    create_standard_horizontal_timber,
    create_centered_horizontal_timber,
)
from kumiki.joints.workshop.butt import (
    cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers,
)
from kumiki.joints.workshop.shavings.build_a_butt import (
    DovetailTenonWedgeAccessoryParameters,
    compute_butt_joint_shoulder,
    dovetail_tenon_geometry,
)
from kumiki.rule import degrees as _degrees
from kumiki.timber import CSGAccessory
from kumiki.cutcsg import ConvexPolygonExtrusion, SolidUnion


def _render_cutting(cutting: Cutting):
    return CutTimber(cutting.timber, cuts=[cutting]).render_timber_with_cuts_csg_local()


@pytest.fixture
def simple_T_configuration():
    tenon_timber = create_standard_vertical_timber(
        height=100, size=(4, 4), position=(0, 0, 0), ticket="tenon_timber"
    )
    mortise_timber = create_centered_horizontal_timber(
        direction="x", length=100, size=(6, 6), name="mortise_timber"
    )
    return (tenon_timber, mortise_timber)

class TestWedgedHalfDovetailMortiseAndTenonJoint:
    """Tests for cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers."""

    def _make_arrangement(self, simple_T_configuration):
        tenon_timber, mortise_timber = simple_T_configuration
        return ButtJointTimberArrangement(
            receiving_timber=mortise_timber,
            butt_timber=tenon_timber,
            butt_timber_end=TimberEnd.BOTTOM,
            front_face_on_butt_timber=None,
            top_face_on_butt_timber=TimberLongFace.RIGHT,
        )

    def test_an_inset_shoulder_notches_the_mortise_timber(self, simple_T_configuration):
        """With the shoulder set back from the entry face, the mortise timber
        gets a notch so the tenon's shoulder has somewhere to sit.

        Every other test of this joint leaves mortise_shoulder_inset at 0,
        where the relief function returns None and no notch is built at all --
        so nothing else here covers the notched path.
        """
        from kumiki.cutcsg import csg_children

        joint = cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=self._make_arrangement(simple_T_configuration),
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_depth=scalar(4),
            dovetail_depth=scalar(1),
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=_degrees(8),
                wedge_back_extra_length=scalar(1, 2),
            ),
            mortise_shoulder_inset=scalar(1),
        )

        def labels(node):
            found = {node.label.name} if node.label.is_labeled() else set()
            for child in csg_children(node):
                found |= labels(child)
            return found

        mortise_ct = joint.cuttings["mortise_timber"]
        assert mortise_ct.negative_csg is not None
        assert "shoulder_notch_relief" in labels(mortise_ct.negative_csg)

        # The notch removes material, and the result is still a closed solid.
        cut_timber = CutTimber(mortise_ct.timber, cuts=[mortise_ct])
        notched = triangulate_cutcsg(cut_timber.render_timber_with_cuts_csg_local()).mesh
        assert notched.is_watertight
        uncut = triangulate_cutcsg(mortise_ct.timber.get_actual_csg_local()).mesh
        assert notched.volume < uncut.volume

    def test_general_wedged_half_dovetail_mortise_and_tenon(self, simple_T_configuration):
        """
        Build the joint and walk points along the tenon centerline.

        Geometry (simple_T_configuration + shoulder at mortise top face z=3):
        - tenon_timber: vertical +Z, height 100, size 4x4 at origin.
          BOTTOM end (at z=0) faces -Z into the mortise.
        - mortise_timber: horizontal +X, length 100, size 6x6 centered at origin
          (cross-section y ∈ [-3, 3], z ∈ [-3, 3]).
        - mortise_shoulder_inset defaults to 0 → shoulder flush with the mortise
          entry face at z = 3 (global).
        - tenon_depth = 4 → tenon tip at z = -1 (penetrating past mortise centerline).
        - dovetail_depth = 1 → inside the mortise, the dovetail flares by 1 in the
          -Z direction (away from the dovetail-top side, which is RIGHT → +Z).
        """
        arrangement = self._make_arrangement(simple_T_configuration)
        tenon_timber = arrangement.butt_timber
        mortise_timber = arrangement.receiving_timber

        tenon_depth = scalar(4)
        dovetail_depth = scalar(1)
        tenon_size = Matrix([scalar(2), scalar(2)])

        joint = cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(
            arrangement=arrangement,
            tenon_size=tenon_size,
            tenon_depth=tenon_depth,
            dovetail_depth=dovetail_depth,
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=_degrees(8),
                wedge_back_extra_length=scalar(1, 2),
            ),
        )

        # ---- structure ----
        assert joint.ticket.joint_type == "wedged_half_dovetail_mortise_and_tenon"
        assert set(joint.cuttings.keys()) == {"tenon_timber", "mortise_timber"}
        assert "wedge" in joint.jointAccessories
        assert isinstance(joint.jointAccessories["wedge"], CSGAccessory)

        tenon_ct = joint.cuttings["tenon_timber"]
        mortise_ct = joint.cuttings["mortise_timber"]
        assert isinstance(tenon_ct, Cutting)
        assert isinstance(mortise_ct, Cutting)
        # Butt end is BOTTOM, so the redundant end cut lives on the bottom end.
        assert tenon_ct.get_maybe_bottom_end_cut() is not None
        assert tenon_ct.get_maybe_top_end_cut() is None
        assert mortise_ct.get_maybe_top_end_cut() is None
        assert mortise_ct.get_maybe_bottom_end_cut() is None
        assert tenon_ct.label.name == "wedged_half_dovetail_mortise_and_tenon"
        assert mortise_ct.label.name == "wedged_half_dovetail_mortise_and_tenon"

        # ---- walk points along the tenon centerline (x=0, y=0, varying z) ----
        tenon_csg = _render_cutting(tenon_ct)
        mortise_csg = _render_cutting(mortise_ct)

        # Shoulder at z=3 (mortise top face).
        # Above the shoulder: deep in tenon body, untouched.
        for z in [scalar(10), scalar(50)]:
            pt = create_v3(scalar(0), scalar(0), z)
            pt_local = tenon_timber.transform.global_to_local(pt)
            assert tenon_csg.contains_point(pt_local), \
                f"tenon body should remain at z={z}"

        # Past the shoulder (z<3) and far from the dovetail footprint (a corner
        # of the butt cross-section): the shoulder cut should have removed this.
        cut_corner = create_v3(scalar(19, 10), scalar(19, 10), scalar(2))
        cut_corner_local = tenon_timber.transform.global_to_local(cut_corner)
        assert not tenon_csg.contains_point(cut_corner_local), \
            "butt corner past the shoulder should be cut"

        # Past the tenon tip (z < -1) on the centerline: end cut should remove this.
        past_tip = create_v3(scalar(0), scalar(0), scalar(-3, 2))
        past_tip_local = tenon_timber.transform.global_to_local(past_tip)
        assert not tenon_csg.contains_point(past_tip_local), \
            "tenon material past the tip should be cut"

        # Mortise body away from the cavity remains.
        mortise_far = create_v3(scalar(40), scalar(0), scalar(0))
        mortise_far_local = mortise_timber.transform.global_to_local(mortise_far)
        assert mortise_csg.contains_point(mortise_far_local)

    def test_no_wedge_accessory(self, simple_T_configuration):
        """Omitting wedge_accessory_parameters raises TypeError."""
        arrangement = self._make_arrangement(simple_T_configuration)
        import pytest
        with pytest.raises(TypeError, match="missing.*required.*wedge_accessory_parameters"):
            cut_wedged_half_dovetail_mortise_and_tenon_joint_on_face_aligned_timbers(  # type: ignore[missing-argument]
                arrangement=arrangement,
                tenon_size=Matrix([scalar(2), scalar(2)]),
                tenon_depth=scalar(4),
                dovetail_depth=scalar(1),
            )

    def test_wedge_size_unchanged_and_slot_extends_to_perfect_boundary(self, simple_T_configuration):
        """Keep wedge size unchanged while extending only the mortise slot base to perfect boundary."""
        arrangement = self._make_arrangement(simple_T_configuration)
        receiving_timber = arrangement.receiving_timber

        tenon_depth = scalar(4)
        back_extra = scalar(1, 2)
        dovetail_depth = scalar(1)

        shoulder_result = compute_butt_joint_shoulder(
            arrangement=arrangement,
            distance_from_centerline_or_centerplane=scalar(0),
            up_direction=arrangement.butt_timber.get_height_direction_global(),
        )

        geo = dovetail_tenon_geometry(
            arrangement=arrangement,
            shoulder_result=shoulder_result,
            dovetail_top_side_on_butt_timber=TimberLongFace.RIGHT,
            tenon_size=Matrix([scalar(2), scalar(2)]),
            tenon_depth=tenon_depth,
            dovetail_depth=dovetail_depth,
            wedge_accessory_parameters=DovetailTenonWedgeAccessoryParameters(
                wedge_angle=_degrees(8),
                wedge_back_extra_length=back_extra,
            ),
        )

        wedge = geo.wedge_accessory_csg
        assert isinstance(wedge, CSGAccessory)
        assert isinstance(wedge.positive_csg, ConvexPolygonExtrusion)
        wedge_x_values = [p[0] for p in wedge.positive_csg.points]

        # Wedge geometry should remain unchanged (base side = -wedge_back_extra).
        assert min(wedge_x_values) == -back_extra

        assert isinstance(geo.mortise_negative_csg, SolidUnion)
        slot_candidates = [
            child for child in geo.mortise_negative_csg.children
            if isinstance(child, ConvexPolygonExtrusion)
            and all(safe_compare(p[1], scalar(0), Comparison.GE) for p in child.points)
        ]
        assert len(slot_candidates) == 1

        wedge_slot = slot_candidates[0]
        wedge_slot_x_values = [p[0] for p in wedge_slot.points]

        into_mortise_dir = shoulder_result.butt_direction
        receiving_perfect_boundary = -receiving_timber.get_size_in_direction_3d(into_mortise_dir)
        expected_slot_x_base = min(-back_extra, receiving_perfect_boundary)

        assert min(wedge_slot_x_values) == expected_slot_x_base


