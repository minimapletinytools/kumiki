import pytest

from kumiki.ticket import (
    _MEMBER_PARENT,
    BoardTicket,
    GenericTag,
    JointTicket,
    Member,
    MemberTag,
    SliceTag,
    TimberTicket,
    as_timber_tag,
    normalize_timber_tags,
)


class TestTicket:
    def test_kumiki_id_auto_increments(self):
        ticket_a = TimberTicket(path="timber_a")
        ticket_b = JointTicket(joint_type="plain_butt")

        assert ticket_b.kumiki_id == ticket_a.kumiki_id + 1

    def test_kumiki_id_does_not_affect_equality_or_hash(self):
        ticket_a = TimberTicket(path="shared_name")
        ticket_b = TimberTicket(path="shared_name")

        assert ticket_a == ticket_b
        assert hash(ticket_a) == hash(ticket_b)
        assert ticket_a.kumiki_id != ticket_b.kumiki_id

    def test_joints_do_not_carry_tags(self):
        # Joints will get their own tagging system; a stray tags= here should
        # fail loudly rather than land somewhere nothing reads.
        with pytest.raises(TypeError):
            JointTicket(joint_type="plain_butt", tags=("bent1",))  # type: ignore[call-arg]


class TestTimberTag:
    def test_bare_string_becomes_a_generic_tag(self):
        assert as_timber_tag("gable") == GenericTag("gable")

    def test_a_tag_passes_through_unchanged(self):
        tag = SliceTag("gable")
        assert as_timber_tag(tag) is tag

    def test_a_non_tag_is_rejected(self):
        with pytest.raises(TypeError):
            as_timber_tag(3)  # type: ignore[arg-type]

    def test_member_tag_takes_the_enum_or_its_value(self):
        assert MemberTag(Member.POST) == MemberTag("post")
        assert MemberTag(Member.POST).name == "post"

    def test_member_tag_rejects_a_name_outside_the_enum(self):
        with pytest.raises(ValueError):
            MemberTag("flying_buttress")

    def test_kind_is_the_subclass_so_the_same_name_can_be_two_tags(self):
        assert SliceTag("gable") != GenericTag("gable")


class TestMemberHierarchy:
    def test_a_role_is_itself(self):
        assert Member.POST.is_a(Member.POST)

    def test_a_role_is_its_parent_and_its_grandparent(self):
        assert Member.SUMMER_BEAM.is_a(Member.BEAM)
        assert Member.SUMMER_BEAM.is_a(Member.HORIZONTAL)

    def test_a_role_is_not_its_child_or_a_sibling(self):
        assert not Member.BEAM.is_a(Member.SUMMER_BEAM)
        assert not Member.SUMMER_BEAM.is_a(Member.TIE_BEAM)
        assert not Member.POST.is_a(Member.HORIZONTAL)

    def test_is_a_takes_the_role_name_too(self):
        assert Member.CORNER_POST.is_a("vertical")

    def test_is_a_rejects_a_name_outside_the_enum(self):
        with pytest.raises(ValueError):
            Member.CORNER_POST.is_a("flying_buttress")

    def test_a_role_is_every_step_up_its_branch(self):
        assert Member.MUDSILL.is_a(Member.SILL)
        assert Member.MUDSILL.is_a(Member.HORIZONTAL)

    def test_a_root_is_only_itself(self):
        assert Member.HORIZONTAL.is_a(Member.HORIZONTAL)
        assert not Member.HORIZONTAL.is_a(Member.VERTICAL)

    def test_every_role_is_in_the_tree(self):
        # Missing roles would read as roots, so is_a would quietly answer False.
        assert set(_MEMBER_PARENT) == set(Member)

    def test_every_role_reaches_a_root(self):
        for member in Member:
            seen = set()
            current = member
            while current is not None:
                assert current not in seen, f"cycle at {current}"
                seen.add(current)
                current = _MEMBER_PARENT[current]

    def test_the_tag_answers_for_its_role(self):
        assert MemberTag(Member.KNEE_BRACE).is_a(Member.BRACE)
        assert MemberTag(Member.KNEE_BRACE).member is Member.KNEE_BRACE


class TestNormalizeTimberTags:
    def test_names_are_stripped_and_empties_dropped(self):
        assert normalize_timber_tags([" gable ", "", "   "]) == (GenericTag("gable"),)

    def test_duplicates_collapse_on_kind_and_name(self):
        tags = normalize_timber_tags(["gable", GenericTag("gable"), SliceTag("gable")])
        assert tags == (GenericTag("gable"), SliceTag("gable"))

    def test_order_is_stable_regardless_of_input_order(self):
        forwards = normalize_timber_tags([SliceTag("b"), MemberTag(Member.POST), GenericTag("a")])
        backwards = normalize_timber_tags([GenericTag("a"), MemberTag(Member.POST), SliceTag("b")])
        assert forwards == backwards == (GenericTag("a"), MemberTag("post"), SliceTag("b"))


class TestTimberTicketTags:
    def test_tags_are_normalized_on_construction(self):
        # Bare strings are coerced at runtime; the field type asks for tags.
        ticket = TimberTicket(path="posts/fl", tags=("beta", " beta ", GenericTag("alpha")))  # type: ignore[arg-type]
        assert ticket.tags == (GenericTag("alpha"), GenericTag("beta"))

    def test_with_tags_adds_without_mutating_the_original(self):
        ticket = TimberTicket(path="posts/fl", tags=(MemberTag(Member.POST),))
        tagged = ticket.with_tags(SliceTag("bent1"), "temporary")

        assert ticket.tags == (MemberTag("post"),)
        assert tagged.tags == (GenericTag("temporary"), MemberTag("post"), SliceTag("bent1"))

    def test_with_tags_keeps_the_kumiki_id(self):
        # dataclasses.replace re-runs __init__, which would otherwise mint a
        # fresh id and lose the viewer's handle on this member.
        ticket = TimberTicket(path="posts/fl")
        assert ticket.with_tags("bent1").kumiki_id == ticket.kumiki_id

    def test_two_member_roles_are_rejected(self):
        with pytest.raises(ValueError):
            TimberTicket(path="posts/fl", tags=(MemberTag(Member.POST), MemberTag(Member.BEAM)))

    def test_the_same_role_twice_is_just_the_one_role(self):
        ticket = TimberTicket(path="posts/fl", tags=(MemberTag(Member.POST), MemberTag("post")))
        assert ticket.tags == (MemberTag("post"),)

    def test_with_member_replaces_the_role_and_keeps_other_tags(self):
        ticket = TimberTicket(path="posts/fl", tags=(MemberTag(Member.POST), SliceTag("bent1")))
        assert ticket.with_member(Member.KING_POST).tags == (
            MemberTag("king_post"),
            SliceTag("bent1"),
        )

    def test_with_member_keeps_the_kumiki_id(self):
        ticket = TimberTicket(path="posts/fl")
        assert ticket.with_member(Member.STUD).kumiki_id == ticket.kumiki_id

    def test_with_tags_keeps_the_ticket_subclass(self):
        assert isinstance(BoardTicket(path="door/1").with_tags("skin"), BoardTicket)
