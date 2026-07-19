"""Tests for the assembly solver (kumiki/assembly.py).

The solver is timber-agnostic, so these tests build tiny abstract graphs of
AssemblyMember / AssemblyJoint records directly — no timbers involved. See
docs/plans/assembly-solver-v2.md for the phase vocabulary used in the class
names below (closure, ring escape, centering, compaction, clear-out).
"""

import pytest
from sympy import Float

from kumiki.assembly import (
    AssemblyFreedom,
    AssemblyJoint,
    AssemblyMember,
    BoundingBox,
    JointMemberSpec,
    Ordering,
    RotationDof,
    solve_assembly,
)
from kumiki.rule import create_v3, giraffe_evalf


X = create_v3(1, 0, 0)
Y = create_v3(0, 1, 0)
Z = create_v3(0, 0, 1)


def member(key, name, x=0, y=0, z=0, bbox=None):
    return AssemblyMember(key=key, name=name, position=create_v3(Float(x), Float(y), Float(z)), bbox=bbox)


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


def displacement_of(movement):
    direction = direction_floats(movement)
    distance = float(giraffe_evalf(movement.distance))
    return tuple(component * distance for component in direction)


def total_displacements(solution):
    """Cumulative displacement per member across all steps."""
    totals = {}
    for step in solution.steps:
        for movement in step.movements:
            dx, dy, dz = displacement_of(movement)
            px, py, pz = totals.get(movement.member_key, (0.0, 0.0, 0.0))
            totals[movement.member_key] = (px + dx, py + dy, pz + dz)
    return totals


def relative_displacement(solution, key_a, key_b):
    totals = total_displacements(solution)
    a = totals.get(key_a, (0.0, 0.0, 0.0))
    b = totals.get(key_b, (0.0, 0.0, 0.0))
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


class TestOrdering:
    def test_lexicographic_comparison(self):
        assert Ordering(0, -1) < Ordering(0, 0)
        assert Ordering(0, 0) < Ordering(0, 1)
        assert Ordering(0, 5) < Ordering(1, 0)
        assert Ordering(1, 0) < Ordering(1, 1)
        assert Ordering(2, 3) == Ordering(2, 3)
        assert not Ordering(1, 1) < Ordering(1, 1)

    def test_label(self):
        assert Ordering(2, 0).label() == "2"
        assert Ordering(2, 1).label() == "2.1"
        assert Ordering(0, -1).label() == "0.-1"
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
        assert step.substep == 1
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
        # but a joint only needs ONE member to depart: exactly one micro-step
        # separates the pair. With every member scheduled at the same ordering
        # (no stationary complement), Phase 2 centering splits the motion, so
        # BOTH sides appear to move — verify the relative separation instead.
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

        assert solution.failure is None
        assert len(solution.steps) == 1
        relative = relative_displacement(solution, 1, 2)
        assert relative[0] == pytest.approx(-2.0)
        assert relative[1] == pytest.approx(0.0)
        assert relative[2] == pytest.approx(0.0)


class TestCentering:
    def test_no_stationary_complement_centers_the_motion(self):
        # Both members are scheduled at the ordering, so the scene has no
        # stationary complement: the separation is split between the halves.
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
        assert set(moved) == {1, 2}
        left = displacement_of(moved[1])
        right = displacement_of(moved[2])
        assert left[0] == pytest.approx(-1.0)
        assert right[0] == pytest.approx(1.0)

    def test_stationary_complement_stays_anchored(self):
        # The post is scheduled at order 2, so at order 1 it is a stationary
        # complement: the beam alone moves and the post stays at zero.
        members = [member(1, "post"), member(2, "beam", z=10), member(3, "cap", z=20)]
        joints = [
            AssemblyJoint(
                name="tenon",
                members={1: spec(), 2: spec(AssemblyFreedom.translation(Z, freed_after=3), order=1)},
            ),
            AssemblyJoint(
                name="cap_joint",
                members={1: spec(), 3: spec(AssemblyFreedom.translation(Z, freed_after=1), order=2)},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        step_one = movements_by_key(solution.steps[0])
        assert set(step_one) == {2}
        assert_direction(step_one[2], (0, 0, 1))


class TestDofRanking:
    def test_prefers_direction_away_from_complement(self):
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

    def test_shared_dof_on_other_side_omits_drag_and_warns_incidental(self):
        # The side joint's freedom for the OTHER member allows the opposite
        # relative motion: the rail is not dragged, and the beam's departure
        # separates the slide joint before the rail's own step 2 (which then
        # has nothing to do). The early separation is reported as a warning.
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
        assert any("slide" in warning and "incidentally" in warning for warning in solution.warnings)

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

    def test_opposed_extractions_resolve_sequentially_with_zero_net_drag(self):
        # Two keys extracted in opposite directions, both rigidly linked to a
        # shared board. The v1 solver summed the drags to a net-zero movement
        # and warned; v2 emits two sequential micro-steps whose drags cancel
        # exactly across steps, with no warnings and full separation.
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
        assert solution.warnings == ()
        board_total = total_displacements(solution).get(5, (0.0, 0.0, 0.0))
        assert board_total[0] == pytest.approx(0.0, abs=1e-9)
        # Both pockets actually separated (relative travel reached freed_after).
        left = relative_displacement(solution, 1, 2)
        right = relative_displacement(solution, 3, 4)
        assert left[0] >= 2.0 - 1e-9
        assert right[0] <= -2.0 + 1e-9


class TestSuborders:
    def build_pegged_joint_graph(self, order=1):
        # A pegged tenon: the peg (suborder -1) must pop before the tenon
        # timber slides (suborder 0) — the authored joint convention.
        members = [member(1, "post"), member(2, "beam", z=10), member(3, "peg", y=3)]
        joints = [
            AssemblyJoint(
                name="pegged_tenon",
                members={
                    1: spec(),
                    2: spec(AssemblyFreedom.translation(Z, freed_after=3), order=order, suborder=0),
                    3: spec(AssemblyFreedom.translation(Y, freed_after=1), order=order, suborder=-1),
                },
            )
        ]
        return members, joints

    def test_peg_pops_before_timber_slides(self):
        members, joints = self.build_pegged_joint_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert [step.ordering for step in solution.steps] == [Ordering(1, -1), Ordering(1, 0)]
        assert set(movements_by_key(solution.steps[0])) == {3}
        assert set(movements_by_key(solution.steps[1])) == {2}

    def test_timber_is_not_extracted_at_the_pegs_suborder(self):
        # The peg's step must move the peg — never pull the timber off the peg
        # via the same interface (ray ownership).
        members, joints = self.build_pegged_joint_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        peg_step = solution.steps[0]
        assert peg_step.ordering == Ordering(1, -1)
        moved = movements_by_key(peg_step)
        assert 2 not in moved

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
            Ordering(2, -1),
            Ordering(2, 0),
        ]


class TestCompaction:
    def test_independent_pegs_pop_in_one_substep(self):
        # Four pegs in four unrelated joints, all at the same ordering: their
        # micro-steps merge into ONE animated substep.
        members = []
        joints = []
        for index in range(4):
            timber_key = 10 + index
            peg_key = 20 + index
            members.append(member(timber_key, f"timber_{index}", x=index * 10))
            members.append(member(peg_key, f"peg_{index}", x=index * 10, y=2))
            joints.append(
                AssemblyJoint(
                    name=f"pegged_{index}",
                    members={
                        timber_key: spec(),
                        peg_key: spec(AssemblyFreedom.translation(Y, freed_after=1), suborder=-1),
                    },
                )
            )

        solution = solve_assembly(members, joints)
        assert solution is not None

        peg_steps = [step for step in solution.steps if step.ordering == Ordering(0, -1)]
        assert len(peg_steps) == 1
        assert set(movements_by_key(peg_steps[0])) == {20, 21, 22, 23}

    def test_sequentially_dependent_motions_stay_separate_substeps(self):
        # B frees A upward, then B itself slides out of C sideways: the two
        # micro-steps share no members but ARE sequentially linked through the
        # (A, B) joint, so they must not merge into one substep.
        members = [member(1, "a", z=10), member(2, "b", z=5), member(3, "c", z=0)]
        joints = [
            AssemblyJoint(
                name="lift",
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=1), order=1), 2: spec()},
            ),
            AssemblyJoint(
                name="slide",
                members={2: spec(AssemblyFreedom.translation(X, freed_after=2), order=1), 3: spec()},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        assert len(solution.steps) == 2
        assert [step.substep for step in solution.steps] == [1, 2]
        assert [step.ordering for step in solution.steps] == [Ordering(1, 0), Ordering(1, 0)]


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

    def test_rigidly_linked_extracted_member_still_rides_along(self):
        # After order 1, the key's ray-bearing joint is separated — but its
        # rigid link to the wedge is permanent: extracting the wedge at order
        # 2 correctly drags the key along (they are one physical body).
        members, joints = self.build_two_order_graph()

        solution = solve_assembly(members, joints)
        assert solution is not None

        step_two = movements_by_key(solution.steps[1])
        assert set(step_two) == {3, 1}
        assert step_two[1].dragged is True
        assert_direction(step_two[1], (1, 0, 0))

    def test_deterministic(self):
        members, joints = self.build_two_order_graph()

        first = solve_assembly(members, joints)
        second = solve_assembly(members, joints)

        assert first == second


class TestKeepOut:
    def test_motion_toward_parked_member_drags_it_along(self):
        # The cap pops +Z at order 1 with no overshoot margin. At order 2 the
        # bar must also move +Z; the relative motion would re-insert the cap
        # joint, so the parked cap is dragged along instead (keep-out).
        members = [member(1, "cap", z=10), member(2, "bar", z=5), member(3, "base", z=0)]
        joints = [
            AssemblyJoint(
                name="cap_joint",
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=1), order=1), 2: spec()},
            ),
            AssemblyJoint(
                name="bar_joint",
                members={2: spec(AssemblyFreedom.translation(Z, freed_after=2), order=2), 3: spec()},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        step_two = movements_by_key(solution.steps[1])
        assert set(step_two) == {2, 1}
        assert step_two[1].dragged is True
        assert_direction(step_two[1], (0, 0, 1))
        # The cap joint never re-enters: relative displacement stays >= freed.
        cap_relative = relative_displacement(solution, 1, 2)
        assert cap_relative[2] >= 1.0 - 1e-9

    def test_extraction_through_earlier_step_joint_does_not_drag_removed(self):
        # The bar sits in a step-1 joint (whose partner already left) and a
        # step-2 joint. Extracting it at step 2 along X moves it AWAY from the
        # departed cap, so the cap stays parked.
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


class TestRingEscape:
    def test_skewed_three_ring_needs_simultaneous_motion(self):
        # A 3-cycle whose escape rays (+X, +Y, and the diagonal) cannot be
        # decomposed into rigid group moves: only a simultaneous multi-velocity
        # assignment separates it (Phase 1b).
        diagonal = create_v3(-1, -1, 0)
        members = [member(1, "a", x=0, y=0), member(2, "b", x=10, y=0), member(3, "c", x=5, y=8)]
        joints = [
            # ray: a moves +X relative to b
            AssemblyJoint(
                name="ab",
                members={1: spec(AssemblyFreedom.translation(X, freed_after=1)), 2: spec()},
            ),
            # ray: b moves +Y relative to c
            AssemblyJoint(
                name="bc",
                members={2: spec(AssemblyFreedom.translation(Y, freed_after=1)), 3: spec()},
            ),
            # ray: c moves along (-1,-1) relative to a
            AssemblyJoint(
                name="ca",
                members={3: spec(AssemblyFreedom.translation(diagonal, freed_after=1)), 1: spec()},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        # Every pair separated along its authored axis by at least freed_after.
        ab = relative_displacement(solution, 1, 2)
        assert ab[0] >= 1.0 - 1e-6
        bc = relative_displacement(solution, 2, 3)
        assert bc[1] >= 1.0 - 1e-6
        ca = relative_displacement(solution, 3, 1)
        diagonal_component = (-ca[0] - ca[1]) / (2 ** 0.5)
        assert diagonal_component >= 1.0 - 1e-6

    def test_ring_members_may_travel_at_different_speeds(self):
        # The skewed ring's solution is inherently asymmetric: member travel
        # distances differ within the single simultaneous step.
        diagonal = create_v3(-1, -1, 0)
        members = [member(1, "a"), member(2, "b", x=10), member(3, "c", x=5, y=8)]
        joints = [
            AssemblyJoint(
                name="ab",
                members={1: spec(AssemblyFreedom.translation(X, freed_after=1)), 2: spec()},
            ),
            AssemblyJoint(
                name="bc",
                members={2: spec(AssemblyFreedom.translation(Y, freed_after=1)), 3: spec()},
            ),
            AssemblyJoint(
                name="ca",
                members={3: spec(AssemblyFreedom.translation(diagonal, freed_after=1)), 1: spec()},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None
        assert solution.failure is None

        distances = sorted(
            float(giraffe_evalf(movement.distance))
            for step in solution.steps
            for movement in step.movements
        )
        assert len(distances) >= 2
        assert distances[-1] > distances[0] + 1e-9


class TestNullspaceRobustness:
    def test_float_cancellation_noise_does_not_cost_a_dimension(self):
        # Regression for the odd-n stool bug: a truly dependent constraint
        # row carrying ~1e-13 float cancellation noise must not be counted
        # as an extra rank (the lost nullspace dimension was exactly the one
        # holding the stool's simultaneous solution).
        import math as pymath
        import random

        from kumiki.assembly import _nullspace_basis

        random.seed(1)
        row_a = [pymath.cos(2 * pymath.pi * k / 7) for k in range(6)]
        row_b = [pymath.sin(2 * pymath.pi * k / 7) for k in range(6)]
        noisy_sum = [a + b + random.uniform(-1e-13, 1e-13) for a, b in zip(row_a, row_b)]

        basis = _nullspace_basis([row_a, row_b, noisy_sum], 6)

        assert len(basis) == 4  # rank must be 2, not 3
        for vector in basis:
            assert abs(sum(a * x for a, x in zip(row_a, vector))) < 1e-8
            assert abs(sum(b * x for b, x in zip(row_b, vector))) < 1e-8

    def test_empty_rows_yield_standard_basis(self):
        from kumiki.assembly import _nullspace_basis

        basis = _nullspace_basis([], 3)

        assert len(basis) == 3


class TestLpBackstop:
    def test_lp_finds_a_measure_zero_feasible_ray(self):
        # The feasible cone here is a single ray (b must equal a exactly), so
        # sampling/projection heuristics can miss it; the exact LP must not.
        from kumiki.assembly import _lp_sign_feasible_null_vector, _orthonormalize

        basis = _orthonormalize([[3.0, 1.0, -1.0], [1.0, -1.0, 1.0]])
        result = _lp_sign_feasible_null_vector(basis, half_line={0, 1, 2}, scheduled={0})

        assert result is not None
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(0.0, abs=1e-9)
        assert result[2] == pytest.approx(0.0, abs=1e-9)

    def test_lp_reports_infeasible_as_none(self):
        from kumiki.assembly import _lp_sign_feasible_null_vector, _orthonormalize

        basis = _orthonormalize([[1.0, -1.0]])
        result = _lp_sign_feasible_null_vector(basis, half_line={0, 1}, scheduled={0, 1})

        assert result is None


class TestSplayedRadialStructures:
    def build_stool_graph(self, leg_count):
        # Abstract model of the n-legged stool: a seat, n legs whose tenons
        # enter the seat along their own splayed axes, and a ring of
        # stretchers tenoned between adjacent legs along the chords. No
        # rigid group move exists; disassembly needs the whole-component
        # simultaneous motion (seat still, legs splaying down-and-out,
        # stretchers riding between).
        import math as pymath

        splay = pymath.radians(30)
        members = [member(1, "seat", z=10)]
        joints = []
        for index in range(leg_count):
            theta = 2 * pymath.pi * index / leg_count
            leg_key = 10 + index
            members.append(member(leg_key, f"leg_{index}",
                                  x=5 * pymath.cos(theta), y=5 * pymath.sin(theta)))
            leg_axis = create_v3(
                Float(-pymath.sin(splay) * pymath.cos(theta)),
                Float(-pymath.sin(splay) * pymath.sin(theta)),
                Float(pymath.cos(splay)),
            )
            joints.append(AssemblyJoint(
                name=f"seat_leg_{index}",
                members={
                    1: spec(AssemblyFreedom.translation(leg_axis, freed_after=1)),
                    leg_key: spec(AssemblyFreedom.translation(-leg_axis, freed_after=1)),
                },
            ))
        for index in range(leg_count):
            next_index = (index + 1) % leg_count
            theta = 2 * pymath.pi * index / leg_count
            next_theta = 2 * pymath.pi * next_index / leg_count
            chord = (pymath.cos(next_theta) - pymath.cos(theta),
                     pymath.sin(next_theta) - pymath.sin(theta))
            chord_norm = pymath.hypot(*chord)
            chord_direction = create_v3(Float(chord[0] / chord_norm), Float(chord[1] / chord_norm), Float(0))
            stretcher_key = 30 + index
            members.append(member(stretcher_key, f"stretcher_{index}",
                                  x=2.5 * (pymath.cos(theta) + pymath.cos(next_theta)),
                                  y=2.5 * (pymath.sin(theta) + pymath.sin(next_theta)),
                                  z=3))
            # Bottom tenon into leg index: the stretcher withdraws along the
            # chord toward the next leg; top tenon into the next leg
            # withdraws the opposite way.
            joints.append(AssemblyJoint(
                name=f"stretcher_{index}_bottom",
                members={
                    10 + index: spec(),
                    stretcher_key: spec(AssemblyFreedom.translation(chord_direction, freed_after=Float(0.5))),
                },
            ))
            joints.append(AssemblyJoint(
                name=f"stretcher_{index}_top",
                members={
                    10 + next_index: spec(),
                    stretcher_key: spec(AssemblyFreedom.translation(-chord_direction, freed_after=Float(0.5))),
                },
            ))
        return members, joints

    @pytest.mark.parametrize("leg_count", [3, 4, 5])
    def test_stool_disassembles_for_any_leg_count(self, leg_count):
        # The odd counts regress the nullspace rank bug: the feasible
        # simultaneous motion lived in the dimension the old RREF dropped.
        members, joints = self.build_stool_graph(leg_count)

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is None
        # Every seat-leg joint fully separated along its splay axis.
        import math as pymath
        splay = pymath.radians(30)
        totals = total_displacements(solution)
        for index in range(leg_count):
            theta = 2 * pymath.pi * index / leg_count
            axis = (-pymath.sin(splay) * pymath.cos(theta),
                    -pymath.sin(splay) * pymath.sin(theta),
                    pymath.cos(splay))
            seat = totals.get(1, (0.0, 0.0, 0.0))
            leg = totals.get(10 + index, (0.0, 0.0, 0.0))
            relative = tuple(s - l for s, l in zip(seat, leg))
            travel = sum(r * a for r, a in zip(relative, axis))
            assert travel >= 1.0 - 1e-6, f"leg_{index} not separated (travel={travel})"


class TestUnsolvable:
    def test_rigidly_locked_pair_fails_with_chain_diagnostic(self):
        # A escapes B along +X per their joint, but a second freedom-less
        # joint welds A to B: the closure absorbs the very partner A was
        # escaping. Fails with the rigid chain in the diagnostics.
        members = [member(1, "a"), member(2, "b", x=10)]
        joints = [
            AssemblyJoint(
                name="slide",
                members={1: spec(AssemblyFreedom.translation(X, freed_after=1)), 2: spec()},
            ),
            AssemblyJoint(name="weld", members={1: spec(), 2: spec()}),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert solution.failure is not None
        assert solution.failure.ordering == Ordering(0, 0)
        assert "no valid extraction" in solution.failure.message
        assert any("absorbs its partner" in diagnostic for diagnostic in solution.failure.diagnostics)
        assert any("weld" in diagnostic for diagnostic in solution.failure.diagnostics)

    def test_partial_steps_survive_a_later_failure(self):
        # Step 1 solves; step 2 is the welded pair above. The step-1 result
        # must remain in the solution alongside the failure.
        members = [member(1, "lid", z=20), member(2, "lid_seat", z=25), member(3, "a"), member(4, "b", x=10)]
        joints = [
            AssemblyJoint(
                name="lid_joint",
                members={1: spec(AssemblyFreedom.translation(Z, freed_after=1), order=1), 2: spec()},
            ),
            AssemblyJoint(
                name="slide",
                members={3: spec(AssemblyFreedom.translation(X, freed_after=1), order=2), 4: spec()},
            ),
            AssemblyJoint(name="weld", members={3: spec(), 4: spec()}),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        assert [step.ordering for step in solution.steps] == [Ordering(1, 0)]
        assert solution.failure is not None
        assert solution.failure.ordering == Ordering(2, 0)


class TestClearOut:
    def test_parked_member_in_swept_path_is_pushed_clear(self):
        # The peg pops +Y and parks right in the beam's +Y escape path; when
        # the beam slides at order 2 the parked peg is pushed ahead of it.
        peg_bbox = BoundingBox(min_x=-0.1, max_x=0.1, min_y=1.0, max_y=1.2, min_z=-0.1, max_z=0.1)
        beam_bbox = BoundingBox(min_x=-0.5, max_x=0.5, min_y=-1.0, max_y=0.0, min_z=-0.5, max_z=0.5)
        seat_bbox = BoundingBox(min_x=-0.5, max_x=0.5, min_y=-3.0, max_y=-1.5, min_z=-0.5, max_z=0.5)
        members = [
            member(1, "peg", y=1, bbox=peg_bbox),
            member(2, "beam", bbox=beam_bbox),
            member(3, "seat", y=-2, bbox=seat_bbox),
        ]
        joints = [
            AssemblyJoint(
                name="peg_joint",
                members={2: spec(), 1: spec(AssemblyFreedom.translation(Y, freed_after=1), order=1)},
            ),
            AssemblyJoint(
                name="beam_joint",
                members={2: spec(AssemblyFreedom.translation(Y, freed_after=3), order=2), 3: spec()},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None
        assert solution.failure is None

        step_two = movements_by_key(solution.steps[1])
        assert 1 in step_two, "parked peg should be pushed out of the beam's swept path"
        assert step_two[1].dragged is True
        assert_direction(step_two[1], (0, 1, 0))
        # After the push, the peg sits clear ahead of the beam's swept end.
        totals = total_displacements(solution)
        peg_min_after = 1.0 + totals[1][1]
        beam_swept_max = 0.0 + totals[2][1]
        assert peg_min_after > beam_swept_max

    def test_members_behind_the_motion_are_not_pushed(self):
        # The seat is behind the beam's motion: it must not be disturbed.
        peg_bbox = BoundingBox(min_x=-0.1, max_x=0.1, min_y=1.0, max_y=1.2, min_z=-0.1, max_z=0.1)
        beam_bbox = BoundingBox(min_x=-0.5, max_x=0.5, min_y=-1.0, max_y=0.0, min_z=-0.5, max_z=0.5)
        seat_bbox = BoundingBox(min_x=-0.5, max_x=0.5, min_y=-3.0, max_y=-1.5, min_z=-0.5, max_z=0.5)
        members = [
            member(1, "peg", y=1, bbox=peg_bbox),
            member(2, "beam", bbox=beam_bbox),
            member(3, "seat", y=-2, bbox=seat_bbox),
        ]
        joints = [
            AssemblyJoint(
                name="peg_joint",
                members={2: spec(), 1: spec(AssemblyFreedom.translation(Y, freed_after=1), order=1)},
            ),
            AssemblyJoint(
                name="beam_joint",
                members={2: spec(AssemblyFreedom.translation(Y, freed_after=3), order=2), 3: spec()},
            ),
        ]

        solution = solve_assembly(members, joints)
        assert solution is not None

        for step in solution.steps:
            moved = movements_by_key(step)
            assert 3 not in moved
