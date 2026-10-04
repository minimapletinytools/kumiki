"""Rows taken as known without drawing them (kumiki/drawings/assumptions.py)."""

import math

from kumiki.construction import create_timber
from kumiki.csg.carriers import PlaneCoord
from kumiki.csg.cutcsg import CutCSGLabel, HalfSpace
from kumiki.drawings.assumptions import sheet_axis_assumptions, square_assumptions
from kumiki.drawings.dof_solver import remaining
from kumiki.drawings.feature_solving import carrier_map_of, feature_handle_dof_rows
from kumiki.drawings.required_features import Reason, required_features
from kumiki.rule import Orientation, Transform, create_v2, create_v3, mm, safe_normalize_vector, sqrt
from kumiki.timber import CutTimber, Cutting


def _plain():
    """An uncut timber along z, its width along x, and its six faces."""
    timber = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(150)),
                           length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="t")
    cut_timber = CutTimber(timber, cuts=[])
    # Keyed without the "rough." or "ptw." prefix; only the six faces, not any non-real features.
    faces = {required.handle.feature.name.split(".")[-1]: required.handle for required in required_features(cut_timber)
             if required.reason is Reason.ON_SURFACE}
    return cut_timber, faces


def _solve(faces, carriers, known_names, assumptions):
    known = [row for name in known_names for row in feature_handle_dof_rows(faces[name], carriers)]
    known += [row for assumption in assumptions for row in assumption.rows]
    target = [row for handle in faces.values() for row in feature_handle_dof_rows(handle, carriers)]
    return remaining(known, target)


class TestSquare:

    def test_a_prism_is_one_aligned_set(self):
        cut_timber, faces = _plain()
        carriers = carrier_map_of(cut_timber)

        assumptions = square_assumptions(list(faces.values()), carriers)

        # 3 axes: one parallel link along each (2 rows), and 3 square pairs (1 row).
        assert len(assumptions) == 6
        assert sum(len(assumption.rows) for assumption in assumptions) == 3 * 2 + 3

    def test_with_one_face_known_only_offsets_and_a_spin_are_left(self):
        cut_timber, faces = _plain()
        carriers = carrier_map_of(cut_timber)

        without = _solve(faces, carriers, ["top"], [])
        with_square = _solve(faces, carriers, ["top"], square_assumptions(list(faces.values()), carriers))

        assert without.count == 6 * 3 - 3
        # The five other offsets, and the prism spinning about the known face's normal.
        assert with_square.count == 5 + 1

    def test_a_plane_at_an_angle_gets_nothing(self):
        timber = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(150)),
                               length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="t")
        bevel = HalfSpace(normal=safe_normalize_vector(create_v3(1, 0, 1)), offset=mm(1020) / sqrt(2),
                          label=CutCSGLabel("bevel"))
        cut_timber = CutTimber(timber, cuts=[Cutting(timber=timber, negative_csg=bevel)])
        handles = [required.handle for required in required_features(cut_timber) if required.reason is Reason.ON_SURFACE]
        carriers = carrier_map_of(cut_timber)

        assumptions = square_assumptions(handles, carriers)
        bevel_face = next(handle.feature.name for handle in handles if handle.owner is bevel)

        assert not any(bevel_face in assumption.reason for assumption in assumptions)
        assert len(assumptions) == 6


class TestSheetAxes:

    def test_faces_along_the_sheet_axes_keep_their_direction(self):
        cut_timber, faces = _plain()
        carriers = carrier_map_of(cut_timber)

        assumptions = sheet_axis_assumptions(list(faces.values()), carriers, Transform.identity())

        # right/left face x (the sheet's right), front/back face y (its up); top/bottom face the viewer.
        assert sorted(assumption.reason.split(" ")[0].split(".")[-1] for assumption in assumptions) == \
            ["back", "front", "left", "right"]
        assert all(len(assumption.rows) == 2 for assumption in assumptions)

    def test_with_square_and_the_sheet_only_offsets_are_left(self):
        cut_timber, faces = _plain()
        carriers = carrier_map_of(cut_timber)
        handles = list(faces.values())
        assumptions = square_assumptions(handles, carriers) + sheet_axis_assumptions(
            handles, carriers, Transform.identity())

        left = _solve(faces, carriers, ["top"], assumptions)

        assert left.count == 5
        assert all(column[1] is PlaneCoord.OFFSET for quantity in left.free_quantities for column in quantity)

    def test_a_turned_sheet_lines_up_with_nothing(self):
        cut_timber, faces = _plain()
        carriers = carrier_map_of(cut_timber)
        turned = Transform(position=create_v3(0, 0, 0),
                           orientation=Orientation.from_axis_angle(create_v3(0, 0, 1), math.pi / 5))

        assert sheet_axis_assumptions(list(faces.values()), carriers, turned) == []
