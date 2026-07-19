"""Tests for the assembly solver (kumiki/assembly.py).

The solver is timber-agnostic, so these tests build tiny abstract graphs of
AssemblyMember / AssemblyJoint records directly — no timbers involved.
"""

import pytest

from kumiki.assembly import (
    AssemblyFreedom,
    AssemblyJoint,
    AssemblyMember,
    JointMemberSpec,
    Ordering,
    RotationDof,
    solve_assembly,
)
from kumiki.rule import create_v3, giraffe_evalf


X = create_v3(1, 0, 0)
Y = create_v3(0, 1, 0)
Z = create_v3(0, 0, 1)


def member(key, name, x=0, y=0, z=0):
    return AssemblyMember(key=key, name=name, position=create_v3(x, y, z))


def spec(freedom=None, order=0, suborder=0):
    return JointMemberSpec(freedom=freedom, ordering=Ordering(order, suborder))


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


class TestOrdering:
    def test_lexicographic_comparison(self):
        assert Ordering(0, 0) < Ordering(0, 1)
        assert Ordering(0, 5) < Ordering(1, 0)
        assert Ordering(1, 0) < Ordering(1, 1)
        assert Ordering(2, 3) == Ordering(2, 3)
        assert not Ordering(1, 1) < Ordering(1, 1)

    def test_label(self):
        assert Ordering(2, 0).label() == "2"
        assert Ordering(2, 1).label() == "2.1"
        assert Ordering().label() == "0"


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
    def test_no_freedoms_returns_none(self):
        members = [member(1, "a"), member(2, "b")]
        joints = [AssemblyJoint(name="j", members={1: spec(), 2: spec()})]

        assert solve_assembly(members, joints) is None

    def test_unknown_member_key_raises(self):
        members = [member(1, "a")]
        joints = [AssemblyJoint(name="j", members={1: spec(), 99: spec()})]

        with pytest.raises(ValueError, match="unknown assembly member key 99"):
            solve_assembly(members, joints)

    def test_rotational_freedom_not_implemented(self):
        rotation = RotationDof(axis_position=create_v3(0, 0, 0), axis_direction=Z, freed_after_angle=1)
        freedom = AssemblyFreedom(rotations=(rotation,))
        members = [member(1, "a"), member(2, "b")]
        joints = [AssemblyJoint(name="j", members={1: spec(freedom), 2: spec()})]

        with pytest.raises(NotImplementedError, match="rotational"):
            solve_assembly(members, joints)

    def test_single_joint_extraction(self):
        members = [member(1, "post"), member(2, "beam", z=10)]
        joints = [
            AssemblyJoint(
                name="tenon",
                members={1: spec(), 2: spec(AssemblyFreedom.translation(Z, freed_after=3), order=1)},
            )
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        assert len(solution.steps) == 1
        step = solution.steps[0]
        assert step.ordering == Ordering(1, 0)
        moved = movements_by_key(step)
        assert set(moved) == {2}
        assert_direction(moved[2], (0, 0, 1))
        assert float(giraffe_evalf(moved[2].distance)) == pytest.approx(3.0)
        assert moved[2].dragged is False

    def test_default_ordering_is_single_exploded_step(self):
        members = [member(1, "post"), member(2, "beam", z=10)]
        joints = [
            AssemblyJoint(
                name="tenon",
                members={1: spec(), 2: spec(AssemblyFreedom.translation(Z, freed_after=3))},
            )
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert [step.ordering for step in solution.steps] == [Ordering(0, 0)]

    def test_second_side_skipped_once_joint_separates(self):
        # Cut functions set inverse freedoms on both sides of an interface,
        # but a joint only needs ONE member to depart: after the first side
        # extracts, the other is skipped as already separated.
        members = [member(1, "left", x=-5), member(2, "right", x=5)]
        joints = [
            AssemblyJoint(
                name="splice",
                members={
                    1: spec(AssemblyFreedom.translation(-X, freed_after=2)),
                    2: spec(AssemblyFreedom.translation(X, freed_after=2)),
                },
            )
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        moved = movements_by_key(solution.steps[0])
        assert len(moved) == 1
        mover_key, movement = next(iter(moved.items()))
        assert movement.dragged is False
        assert_direction(movement, (-1, 0, 0) if mover_key == 1 else (1, 0, 0))


class TestDofRanking:
    def test_prefers_direction_away_from_peer(self):
        # The beam can slide either way along X; its joint partner sits on the
        # +X side, so extraction should pick -X.
        members = [member(1, "beam", x=0), member(2, "post", x=10)]
        joints = [
            AssemblyJoint(
                name="lap",
                members={
                    1: spec(AssemblyFreedom.bidirectional_translation(X, freed_after=2), order=1),
                    2: spec(),
                },
            )
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        moved = movements_by_key(solution.steps[0])
        assert_direction(moved[1], (-1, 0, 0))


class TestDragPropagation:
    def test_drag_through_rigid_joints(self):
        # beam is extracted; brace hangs off it through a freedom-less (rigid)
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
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=2), order=1), 2: spec()},
            ),
            AssemblyJoint(name="brace_joint", members={1: spec(), 3: spec()}),
            AssemblyJoint(name="shelf_joint", members={3: spec(), 4: spec()}),
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
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=2), order=1), 2: spec()},
            ),
            AssemblyJoint(
                name="slide",
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=1), order=1), 3: spec()},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        moved = movements_by_key(solution.steps[0])
        assert set(moved) == {1}

    def test_shared_dof_on_other_side_omits_drag(self):
        # The side joint's freedom for the OTHER member allows the opposite
        # relative motion, which also means the connection separates freely:
        # the rail is not dragged at step 1, and by its own step 2 the beam's
        # departure has already separated the slide joint, so the rail never
        # needs to move at all.
        members = [member(1, "beam"), member(2, "post", x=10), member(3, "rail", x=3)]
        joints = [
            AssemblyJoint(
                name="tenon",
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=2), order=1), 2: spec()},
            ),
            AssemblyJoint(
                name="slide",
                members={1: spec(), 3: spec(AssemblyFreedom.translation(-Z, freed_after=1), order=2)},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert [step.ordering for step in solution.steps] == [Ordering(1, 0)]
        step_one = movements_by_key(solution.steps[0])
        assert set(step_one) == {1}

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
                members={
                    1: spec(AssemblyFreedom.translation(Z, freed_after=2), order=1),
                    2: spec(),
                    4: spec(),
                },
            ),
            AssemblyJoint(name="brace_joint", members={1: spec(), 3: spec()}),
            AssemblyJoint(name="peg_joint", members={3: spec(), 5: spec()}),
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
                members={1: spec(AssemblyFreedom.translation(X, freed_after=2), order=1), 2: spec()},
            ),
            AssemblyJoint(
                name="right_pocket",
                members={3: spec(AssemblyFreedom.translation(-X, freed_after=2), order=1), 4: spec()},
            ),
            AssemblyJoint(name="left_link", members={1: spec(), 5: spec()}),
            AssemblyJoint(name="right_link", members={3: spec(), 5: spec()}),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        assert any("board" in warning and "cancelled out" in warning for warning in solution.warnings)
        for step in solution.steps:
            assert 5 not in movements_by_key(step)


class TestSuborders:
    def build_pegged_joint_graph(self, order=1):
        # A pegged tenon: the peg (suborder 0) must pop before the tenon
        # timber slides (suborder 1).
        members = [member(1, "post"), member(2, "beam", z=10), member(3, "peg", y=3)]
        joints = [
            AssemblyJoint(
                name="pegged_tenon",
                members={
                    1: spec(),
                    2: spec(AssemblyFreedom.translation(Z, freed_after=3), order=order, suborder=1),
                    3: spec(AssemblyFreedom.translation(Y, freed_after=1), order=order, suborder=0),
                },
            )
        ]
        return members, joints

    def test_peg_pops_before_timber_slides(self):
        members, joints = self.build_pegged_joint_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert [step.ordering for step in solution.steps] == [Ordering(1, 0), Ordering(1, 1)]
        assert set(movements_by_key(solution.steps[0])) == {3}
        assert set(movements_by_key(solution.steps[1])) == {2}

    def test_suborder_steps_sort_within_and_across_orders(self):
        members_a, joints_a = self.build_pegged_joint_graph(order=2)
        members_b = [member(10, "cap", z=20), member(11, "cap_seat", z=25)]
        joints_b = [
            AssemblyJoint(
                name="cap_joint",
                members={10: spec(AssemblyFreedom.translation(Z, freed_after=1), order=1), 11: spec()},
            )
        ]

        solution = solve_assembly(members_a + members_b, joints_a + joints_b)
        assert solution is not None

        assert [step.ordering for step in solution.steps] == [
            Ordering(1, 0),
            Ordering(2, 0),
            Ordering(2, 1),
        ]


class TestOrdersAndWarnings:
    def build_two_order_graph(self):
        # Order 1 extracts the key, which rigidly drags the wedge; the wedge's
        # own extraction is order 2, so order 1 should warn about the drag.
        members = [member(1, "key"), member(2, "seat", x=10), member(3, "wedge", x=3), member(4, "block", x=13)]
        joints = [
            AssemblyJoint(
                name="key_joint",
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=2), order=1), 2: spec()},
            ),
            AssemblyJoint(name="key_wedge_link", members={1: spec(), 3: spec()}),
            AssemblyJoint(
                name="wedge_joint",
                members={3: spec(AssemblyFreedom.translation(X, freed_after=1), order=2), 4: spec()},
            ),
        ]
        return members, joints

    def test_dragging_later_ordered_member_warns(self):
        members, joints = self.build_two_order_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert any(
            "wedge" in warning and "step 1" in warning and "own ordering is 2" in warning
            for warning in solution.warnings
        )

    def test_member_moved_in_multiple_steps(self):
        # The wedge is dragged at order 1 and extracted at order 2: it appears
        # in both steps (cross-step accumulation is the consumer's job).
        members, joints = self.build_two_order_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert [step.ordering for step in solution.steps] == [Ordering(1, 0), Ordering(2, 0)]
        step_one = movements_by_key(solution.steps[0])
        step_two = movements_by_key(solution.steps[1])
        assert step_one[3].dragged is True
        assert_direction(step_one[3], (0, 0, 1))
        assert step_two[3].dragged is False
        assert_direction(step_two[3], (1, 0, 0))

    def test_removed_members_do_not_propagate(self):
        # After order 1 extracts the key, the key is out of the frame: order 2
        # extracting the wedge must not drag it through their shared joint.
        members, joints = self.build_two_order_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        step_two = movements_by_key(solution.steps[1])
        assert set(step_two) == {3}

    def test_extraction_through_earlier_step_joint_does_not_drag_removed(self):
        # The bar sits in a step-1 joint (whose partner already left) and a
        # step-2 joint. Extracting it at step 2 must not drag the departed cap.
        members = [member(1, "cap"), member(2, "bar", x=5), member(3, "base", x=10)]
        joints = [
            AssemblyJoint(
                name="cap_joint",
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=1), order=1), 2: spec()},
            ),
            AssemblyJoint(
                name="bar_joint",
                members={2: spec(AssemblyFreedom.translation(X, freed_after=2), order=2), 3: spec()},
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
        # Step 1 solves fine. At step 2, ten spokes are each extracted from
        # their own seat in a different direction while all being RIGIDLY
        # linked to a shared hub: every extraction re-drags the hub (and,
        # through it, every other spoke) in a new direction, so the movement
        # records keep changing past the loop cap. Step 2 fails but step 1's
        # result is preserved.
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
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=1), order=1), 2: spec()},
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
                    members={
                        spoke_key: spec(AssemblyFreedom.translation(direction, freed_after=1), order=2),
                        seat_key: spec(),
                    },
                )
            )
            joints.append(
                AssemblyJoint(
                    name=f"hub_link_{index:02d}",
                    members={spoke_key: spec(), 100: spec()},
                )
            )

        solution = solve_assembly(members, joints)

        assert solution is not None
        assert [step.ordering for step in solution.steps] == [Ordering(1, 0)]
        assert solution.failure is not None
        assert solution.failure.ordering == Ordering(2, 0)
        assert "no workable DOF" in solution.failure.message
        assert len(solution.failure.diagnostics) > 0
        assert any("drag chain" in diagnostic for diagnostic in solution.failure.diagnostics)
