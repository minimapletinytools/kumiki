"""A timber's two centerplanes: declared on the perfect timber within, solved as midplanes of its faces."""

import pytest

from kumiki.construction import create_timber
from kumiki.csg.cutcsg import OwnedFeatureHit
from kumiki.csg.feature_paths import FeatureHandle
from kumiki.drawings.drawing import Measure
from kumiki.drawings.dof_solver import remaining
from kumiki.drawings.feature_solving import carrier_map_of, feature_handle_dof_rows, measure_row
from kumiki.drawings.required_features import Reason, required_features
from kumiki.rule import create_v2, create_v3, mm
from kumiki.timber import CutTimber


@pytest.fixture(scope="module")
def timber():
    """An uncut timber along z, 100 wide along x and 150 high along y, with handles to its body by name."""
    made = create_timber(bottom_position=create_v3(0, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(150)),
                         length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket="t")
    cut_timber = CutTimber(made, cuts=[])
    body = cut_timber.get_extended_perfect_csg_local()
    handles = {feature.name.removeprefix("ptw."): FeatureHandle(
        timber=made, hit=OwnedFeatureHit(feature=feature, owner=body)) for feature in body.get_declared_features()}
    return cut_timber, handles


def _left(cut_timber, known, measures, target):
    carriers = carrier_map_of(cut_timber)
    rows = [row for handle in known for row in feature_handle_dof_rows(handle, carriers)]
    rows += [measure_row(measure, carriers) for measure in measures]
    return remaining(rows, [row for handle in target for row in feature_handle_dof_rows(handle, carriers)]).count


class TestDeclared:

    def test_both_sit_on_the_timber_s_centerline(self, timber):
        _, handles = timber
        across_width = handles["centerplane_left_right"]
        across_height = handles["centerplane_front_back"]

        width_plane = across_width.feature.locate_simple_unbounded(across_width.owner)
        height_plane = across_height.feature.locate_simple_unbounded(across_height.owner)

        assert width_plane is not None and height_plane is not None
        assert [float(width_plane.point[0, 0]), abs(float(width_plane.normal[0, 0]))] == [0.0, 1.0]
        assert [float(height_plane.point[1, 0]), abs(float(height_plane.normal[1, 0]))] == [0.0, 1.0]

    def test_they_are_required_as_non_real(self, timber):
        cut_timber, _ = timber

        reasons = {required.handle.feature.name: required.reason for required in required_features(cut_timber)}

        assert reasons["ptw.centerplane_left_right"] is Reason.NON_REAL
        assert reasons["ptw.centerplane_front_back"] is Reason.NON_REAL


class TestSolving:

    def test_its_two_faces_solve_it(self, timber):
        cut_timber, handles = timber

        assert _left(cut_timber, [], [], [handles["centerplane_left_right"]]) == 3
        assert _left(cut_timber, [handles["right"], handles["left"]], [], [handles["centerplane_left_right"]]) == 0

    def test_it_and_one_face_solve_the_other(self, timber):
        cut_timber, handles = timber

        assert _left(cut_timber, [handles["centerplane_left_right"], handles["right"]], [], [handles["left"]]) == 0

    def test_on_its_own_it_takes_three_of_its_faces_six(self, timber):
        cut_timber, handles = timber

        assert _left(cut_timber, [handles["centerplane_left_right"]], [], [handles["right"], handles["left"]]) == 3

    def test_a_measurement_from_it_fixes_a_face_s_offset(self, timber):
        cut_timber, handles = timber
        center, right = handles["centerplane_left_right"], handles["right"]

        assert _left(cut_timber, [center], [], [right]) == 3
        assert _left(cut_timber, [center], [Measure(center, right)], [right]) == 2

    def test_the_other_centerplane_tells_it_nothing(self, timber):
        cut_timber, handles = timber

        assert _left(cut_timber, [handles["centerplane_front_back"]], [], [handles["centerplane_left_right"]]) == 3
