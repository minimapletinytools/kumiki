"""The rank test over hand-built rows."""

import pytest

from kumiki.drawings.dof_solver import remaining


def _unit(*names):
    return [{name: 1.0} for name in names]


def test_nothing_known_leaves_every_target_row_free():
    assert remaining([], _unit("a", "b", "c")).count == 3


def test_a_known_row_removes_its_direction():
    result = remaining([{"a": 1.0}], _unit("a", "b"))
    assert result.count == 1
    (free,) = result.free
    assert abs(free[0]) == pytest.approx(0.0, abs=1e-12)
    assert abs(free[1]) == pytest.approx(1.0)


def test_redundant_measurements_count_by_rank_not_by_number():
    # Four measurements of a plane's offset and two tilts, one of them redundant.
    rows = [{"d": 1.0, "t1": -y, "t2": -z} for y, z in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
    assert remaining(rows, _unit("d", "t1", "t2")).count == 0
    assert remaining(rows[:2], _unit("d", "t1", "t2")).count == 1


def test_a_zero_row_solves_nothing():
    # An angle of 0 has no derivative, so as a row it's empty.
    assert remaining([{"n": 0.0}], _unit("n")).count == 1


class TestTenon:
    """Six offsets: shoulder, four cheeks, tip. The timber's end and two reference faces are known."""

    known = _unit("end", "ref_a", "ref_b")
    measurements = [
        {"shoulder": 1.0, "end": -1.0},      # shoulder from the end
        {"cheek_1": 1.0, "ref_a": -1.0},     # one cheek from a reference face
        {"cheek_2": 1.0, "cheek_1": -1.0},   # thickness
        {"cheek_3": 1.0, "ref_b": -1.0},
        {"cheek_4": 1.0, "cheek_3": -1.0},   # width
        {"tip": 1.0, "shoulder": -1.0},      # length
    ]
    offsets = ("shoulder", "cheek_1", "cheek_2", "cheek_3", "cheek_4", "tip")

    def test_six_measurements_solve_six_offsets(self):
        assert remaining(self.known + self.measurements, _unit(*self.offsets)).count == 0

    def test_leaving_out_the_length_leaves_the_tip(self):
        known = self.known + self.measurements[:-1]
        assert remaining(known, _unit("tip")).count == 1
        assert remaining(known, _unit(*self.offsets[:-1])).count == 0

    def test_thickness_alone_solves_neither_cheek(self):
        known = self.known + [self.measurements[2]]
        assert remaining(known, _unit("cheek_1")).count == 1
        assert remaining(known, _unit("cheek_1", "cheek_2")).count == 1


def test_a_free_dof_reads_back_as_a_quantity_and_a_motion():
    # a - b is known; a is not. The unknown quantity is a; the motion moves a and b together.
    result = remaining([{"a": 1.0, "b": -1.0}], _unit("a"))
    assert result.count == 1
    (quantity,) = result.free_quantities
    (motion,) = result.free_motions
    assert set(quantity) == {"a"}
    assert motion["a"] == pytest.approx(motion["b"])
    assert abs(motion["a"]) == pytest.approx(2 ** -0.5)


def test_nothing_free_reads_back_as_nothing():
    result = remaining(_unit("a", "b"), _unit("a"))
    assert result.count == 0 and result.free_quantities == () and result.free_motions == ()
