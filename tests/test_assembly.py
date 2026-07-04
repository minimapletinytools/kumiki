"""Tests for the assembly solver (kumiki/assembly.py).

The solver is timber-agnostic, so these tests build tiny abstract graphs of
AssemblyMember / AssemblyJoint records directly — no timbers involved.
"""

import pytest

from kumiki.assembly import (
    AssemblyFreedom,
    AssemblyJoint,
    AssemblyMember,
    RotationDof,
    solve_assembly,
)
from kumiki.rule import create_v3, giraffe_evalf


X = create_v3(1, 0, 0)
Y = create_v3(0, 1, 0)
Z = create_v3(0, 0, 1)


def member(key, name, x=0, y=0, z=0):
    return AssemblyMember(key=key, name=name, position=create_v3(x, y, z))


def direction_floats(movement):
    return (
        float(giraffe_evalf(movement.direction[0, 0])),
        float(giraffe_evalf(movement.direction[1, 0])),
        float(giraffe_evalf(movement.direction[2, 0])),
    )


def movements_by_key(step):
    return {movement.member_key: movement for movement in step.movements}


def assert_direction(movement, expected, tolerance=1e-6):
    actual = direction_floats(movement)
    for actual_component, expected_component in zip(actual, expected):
        assert actual_component == pytest.approx(expected_component, abs=tolerance)


class TestAssemblyFreedom:
    def test_translation_normalizes_direction(self):
        freedom = AssemblyFreedom.translation(create_v3(0, 0, 2), freed_after=3)

        assert len(freedom.translations) == 1
        dof = freedom.translations[0]
        assert float(giraffe_evalf(dof.direction[2, 0])) == pytest.approx(1.0)
        assert dof.freed_after == 3

    def test_bidirectional_translation_has_two_opposite_dofs(self):
        freedom = AssemblyFreedom.bidirectional_translation(X, freed_after=2)

        assert len(freedom.translations) == 2
        first, second = freedom.translations
        assert float(giraffe_evalf(first.direction[0, 0])) == pytest.approx(1.0)
        assert float(giraffe_evalf(second.direction[0, 0])) == pytest.approx(-1.0)

    def test_combine_unions_dofs(self):
        combined = AssemblyFreedom.combine(
            AssemblyFreedom.translation(X, freed_after=1),
            AssemblyFreedom.translation(Z, freed_after=2),
        )

        assert len(combined.translations) == 2


class TestSolveAssemblyBasics:
    def test_no_orders_returns_none(self):
        members = [member(1, "a"), member(2, "b")]
        joints = [AssemblyJoint(name="j", order=None, freedoms={1: None, 2: None})]

        assert solve_assembly(members, joints) is None

    def test_unknown_member_key_raises(self):
        members = [member(1, "a")]
        joints = [AssemblyJoint(name="j", order=1, freedoms={1: None, 99: None})]

        with pytest.raises(ValueError, match="unknown assembly member key 99"):
            solve_assembly(members, joints)

    def test_rotational_freedom_not_implemented(self):
        rotation = RotationDof(axis_position=create_v3(0, 0, 0), axis_direction=Z, freed_after_angle=1)
        freedom = AssemblyFreedom(rotations=(rotation,))
        members = [member(1, "a"), member(2, "b")]
        joints = [AssemblyJoint(name="j", order=1, freedoms={1: freedom, 2: None})]

        with pytest.raises(NotImplementedError, match="rotational"):
            solve_assembly(members, joints)

    def test_single_joint_extraction(self):
        members = [member(1, "post"), member(2, "beam", z=10)]
        joints = [
            AssemblyJoint(
                name="tenon",
                order=1,
                freedoms={1: None, 2: AssemblyFreedom.translation(Z, freed_after=3)},
            )
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None
        assert solution.failure is None
        assert len(solution.steps) == 1
        step = solution.steps[0]
        assert step.order == 1
        moved = movements_by_key(step)
        assert set(moved) == {2}
        assert_direction(moved[2], (0, 0, 1))
        assert float(giraffe_evalf(moved[2].distance)) == pytest.approx(3.0)
        assert moved[2].dragged is False

    def test_order_with_no_freedoms_warns(self):
        members = [member(1, "a"), member(2, "b")]
        joints = [AssemblyJoint(name="mystery", order=1, freedoms={1: None, 2: None})]

        solution = solve_assembly(members, joints)
        assert solution is not None
        assert solution.steps == ()
        assert any("mystery" in warning and "no assembly freedoms" in warning for warning in solution.warnings)


class TestDofRanking:
    def test_prefers_direction_away_from_peer(self):
        # The beam can slide either way along X; its joint partner sits on the
        # +X side, so extraction should pick -X.
        members = [member(1, "beam", x=0), member(2, "post", x=10)]
        joints = [
            AssemblyJoint(
                name="lap",
                order=1,
                freedoms={1: AssemblyFreedom.bidirectional_translation(X, freed_after=2), 2: None},
            )
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        moved = movements_by_key(solution.steps[0])
        assert_direction(moved[1], (-1, 0, 0))


class TestDragPropagation:
    def test_drag_through_rigid_joints(self):
        # beam is extracted; brace hangs off it through an unannotated (rigid)
        # joint, and shelf hangs off the brace: both get dragged with the beam.
        members = [
            member(1, "beam"),
            member(2, "post", x=10),
            member(3, "brace", x=3),
            member(4, "shelf", x=6),
        ]
        joints = [
            AssemblyJoint(
                name="tenon",
                order=1,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=2), 2: None},
            ),
            AssemblyJoint(name="brace_joint", order=None, freedoms={1: None, 3: None}),
            AssemblyJoint(name="shelf_joint", order=None, freedoms={3: None, 4: None}),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        moved = movements_by_key(solution.steps[0])
        assert set(moved) == {1, 3, 4}
        assert moved[1].dragged is False
        for dragged_key in (3, 4):
            assert moved[dragged_key].dragged is True
            assert_direction(moved[dragged_key], (0, 0, 1))
            assert float(giraffe_evalf(moved[dragged_key].distance)) == pytest.approx(2.0)

    def test_shared_dof_on_mover_side_omits_drag(self):
        # The side joint's freedom FOR THE MOVER allows the extraction
        # direction, so the side joint's other member stays put.
        members = [member(1, "beam"), member(2, "post", x=10), member(3, "rail", x=3)]
        joints = [
            AssemblyJoint(
                name="tenon",
                order=1,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=2), 2: None},
            ),
            AssemblyJoint(
                name="slide",
                order=None,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=1), 3: None},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        moved = movements_by_key(solution.steps[0])
        assert set(moved) == {1}

    def test_shared_dof_on_other_side_omits_drag(self):
        # The side joint's freedom for the OTHER member allows the opposite
        # relative motion, which also means the connection separates freely.
        members = [member(1, "beam"), member(2, "post", x=10), member(3, "rail", x=3)]
        joints = [
            AssemblyJoint(
                name="tenon",
                order=1,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=2), 2: None},
            ),
            AssemblyJoint(
                name="slide",
                order=None,
                freedoms={1: None, 3: AssemblyFreedom.translation(-Z, freed_after=1)},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        moved = movements_by_key(solution.steps[0])
        assert set(moved) == {1}

    def test_accessory_rides_along_dragged_subassembly_but_not_freed_joint(self):
        # peg_a sits in the extracting joint, which frees the beam: it stays.
        # peg_b sits in a joint of the dragged brace: it rides along.
        members = [
            member(1, "beam"),
            member(2, "post", x=10),
            member(3, "brace", x=3),
            member(4, "peg_a", x=1),
            member(5, "peg_b", x=4),
        ]
        joints = [
            AssemblyJoint(
                name="tenon",
                order=1,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=2), 2: None, 4: None},
            ),
            AssemblyJoint(name="brace_joint", order=None, freedoms={1: None, 3: None}),
            AssemblyJoint(name="peg_joint", order=None, freedoms={3: None, 5: None}),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        moved = movements_by_key(solution.steps[0])
        assert set(moved) == {1, 3, 5}
        assert moved[5].dragged is True

    def test_net_zero_drag_warns_and_emits_no_movement(self):
        # The board is rigidly linked to two members extracted in opposite
        # directions with equal travel; its drags cancel exactly.
        members = [
            member(1, "left_key", x=-5),
            member(2, "left_seat", x=-6),
            member(3, "right_key", x=5),
            member(4, "right_seat", x=6),
            member(5, "board"),
        ]
        joints = [
            AssemblyJoint(
                name="left_pocket",
                order=1,
                freedoms={1: AssemblyFreedom.translation(X, freed_after=2), 2: None},
            ),
            AssemblyJoint(
                name="right_pocket",
                order=1,
                freedoms={3: AssemblyFreedom.translation(-X, freed_after=2), 4: None},
            ),
            AssemblyJoint(name="left_link", order=None, freedoms={1: None, 5: None}),
            AssemblyJoint(name="right_link", order=None, freedoms={3: None, 5: None}),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        assert any("board" in warning and "cancelled out" in warning for warning in solution.warnings)
        for step in solution.steps:
            assert 5 not in movements_by_key(step)


class TestOrdersAndWarnings:
    def build_two_order_graph(self):
        # Order 1 extracts the key, which rigidly drags the wedge; the wedge's
        # own extraction is order 2, so order 1 should warn about the drag.
        members = [member(1, "key"), member(2, "seat", x=10), member(3, "wedge", x=3), member(4, "block", x=13)]
        joints = [
            AssemblyJoint(
                name="key_joint",
                order=1,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=2), 2: None},
            ),
            AssemblyJoint(name="key_wedge_link", order=None, freedoms={1: None, 3: None}),
            AssemblyJoint(
                name="wedge_joint",
                order=2,
                freedoms={3: AssemblyFreedom.translation(X, freed_after=1), 4: None},
            ),
        ]
        return members, joints

    def test_dragging_higher_order_member_warns(self):
        members, joints = self.build_two_order_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert any(
            "wedge" in warning and "order 1" in warning and "own assembly order is 2" in warning
            for warning in solution.warnings
        )

    def test_member_moved_in_multiple_steps(self):
        # The wedge is dragged at order 1 and extracted at order 2: it appears
        # in both steps (cross-step accumulation is the consumer's job).
        members, joints = self.build_two_order_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert [step.order for step in solution.steps] == [1, 2]
        step_one = movements_by_key(solution.steps[0])
        step_two = movements_by_key(solution.steps[1])
        assert step_one[3].dragged is True
        assert_direction(step_one[3], (0, 0, 1))
        assert step_two[3].dragged is False
        assert_direction(step_two[3], (1, 0, 0))

    def test_removed_members_and_released_joints_do_not_propagate(self):
        # After order 1 extracts the key, the key is out of the frame: order 2
        # extracting the wedge must not drag it through their shared joints.
        members, joints = self.build_two_order_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        step_two = movements_by_key(solution.steps[1])
        assert set(step_two) == {3}

    def test_extraction_through_lower_order_joint_is_released(self):
        # The bar sits in an order-1 joint (already disassembled) and an
        # order-2 joint. Extracting it at order 2 must not drag the order-1
        # joint's partner: that joint no longer constrains anything.
        members = [member(1, "cap"), member(2, "bar", x=5), member(3, "base", x=10)]
        joints = [
            AssemblyJoint(
                name="cap_joint",
                order=1,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=1), 2: None},
            ),
            AssemblyJoint(
                name="bar_joint",
                order=2,
                freedoms={2: AssemblyFreedom.translation(X, freed_after=2), 3: None},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        step_two = movements_by_key(solution.steps[1])
        assert set(step_two) == {2}

    def test_deterministic(self):
        members, joints = self.build_two_order_graph()

        first = solve_assembly(members, joints)
        second = solve_assembly(members, joints)

        assert first == second


class TestUnsolvable:
    def test_loop_cap_yields_partial_steps_and_failure(self):
        # Order 1 solves fine. At order 2, ten spokes are each extracted from
        # their own seat in a different direction while all being RIGIDLY
        # linked to a shared hub: every extraction re-drags the hub (and,
        # through it, every other spoke) in a new direction, so the movement
        # records keep changing past the loop cap. Order 2 fails but order 1's
        # step is preserved.
        spoke_directions = [
            create_v3(1, 0, 0),
            create_v3(-1, 0, 0),
            create_v3(0, 1, 0),
            create_v3(0, -1, 0),
            create_v3(0, 0, 1),
            create_v3(0, 0, -1),
            create_v3(1, 1, 0),
            create_v3(1, -1, 0),
            create_v3(1, 0, 1),
            create_v3(0, 1, 1),
        ]
        members = [member(1, "lid", z=20), member(2, "lid_seat", z=25), member(100, "hub")]
        joints = [
            AssemblyJoint(
                name="lid_joint",
                order=1,
                freedoms={1: AssemblyFreedom.translation(Z, freed_after=1), 2: None},
            ),
        ]
        for index, direction in enumerate(spoke_directions):
            spoke_key = 10 + index
            seat_key = 30 + index
            members.append(member(spoke_key, f"spoke_{index:02d}", x=index))
            members.append(member(seat_key, f"seat_{index:02d}", x=index, y=5))
            joints.append(
                AssemblyJoint(
                    name=f"seat_joint_{index:02d}",
                    order=2,
                    freedoms={spoke_key: AssemblyFreedom.translation(direction, freed_after=1), seat_key: None},
                )
            )
            joints.append(
                AssemblyJoint(
                    name=f"hub_link_{index:02d}",
                    order=None,
                    freedoms={spoke_key: None, 100: None},
                )
            )

        solution = solve_assembly(members, joints)
        assert solution is not None
        assert [step.order for step in solution.steps] == [1]
        assert solution.failure is not None
        assert solution.failure.order == 2
        assert "no workable DOF" in solution.failure.message
        assert len(solution.failure.diagnostics) > 0
        assert any("drag chain" in diagnostic for diagnostic in solution.failure.diagnostics)
