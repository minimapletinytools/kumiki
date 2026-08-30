"""Tests for the typed tag payload kigumi ships to the viewer (kigumi/runner.py).

Tags are TimberTag objects in kumiki and {"kind", "name"} dicts on the wire.
The kind names are the viewer's vocabulary, so they are pinned here rather than
left to whatever the class happens to be called.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.ticket import (
    GenericTag,
    Member,
    MemberTag,
    SliceTag,
    TimberTag,
    TimberTicket,
)
from kumiki.timber import Frame


def _load_runner():
    """Import kigumi/runner.py by path -- kigumi is not an installed package."""
    runner_path = Path(__file__).resolve().parent.parent / "kigumi" / "runner.py"
    spec = importlib.util.spec_from_file_location("kigumi_runner", runner_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kigumi_runner"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def _timber(ticket):
    return create_timber(
        bottom_position=create_v3(mm(0), mm(0), mm(0)),
        length=mm(1000),
        size=create_v2(mm(100), mm(100)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket=ticket,
    )


class TestSerializeTimberTags:
    def test_each_kind_ships_with_its_wire_name(self):
        ticket = TimberTicket(path="A").with_tags(
            MemberTag(Member.SUMMER_BEAM), SliceTag("bent1"), "wonky"
        )
        assert runner._serialize_timber_tags(ticket) == [
            {"kind": "generic", "name": "wonky"},
            {"kind": "member", "name": "summer_beam"},
            {"kind": "slice", "name": "bent1"},
        ]

    def test_tags_are_sorted_by_kind_then_name(self):
        ticket = TimberTicket(path="A").with_tags(
            SliceTag("roof"), GenericTag("zebra"), SliceTag("bent1"), GenericTag("alpha")
        )
        assert [tag["name"] for tag in runner._serialize_timber_tags(ticket)] == [
            "alpha",
            "zebra",
            "bent1",
            "roof",
        ]

    def test_a_ticket_without_tags_ships_an_empty_list(self):
        assert runner._serialize_timber_tags(TimberTicket(path="A")) == []
        assert runner._serialize_timber_tags(None) == []

    def test_every_tag_class_has_a_wire_name(self):
        # The serializer skips tag classes it does not know, so that a new one
        # costs a missing pill rather than a timber's whole mesh. This is the
        # loud half of that bargain: add a TimberTag subclass, add it there.
        serialized = {cls for cls, _ in runner._timber_tag_kinds()}
        assert serialized == set(TimberTag.__subclasses__())

    def test_the_wire_names_are_distinct(self):
        wire_names = [wire for _, wire in runner._timber_tag_kinds()]
        assert len(set(wire_names)) == len(wire_names)


class TestFramePayloads:
    @pytest.fixture
    def frame(self):
        tagged = _timber(TimberTicket(path="A").with_tags(MemberTag(Member.POST), "wonky"))
        untagged = _timber(TimberTicket(path="B"))
        return Frame.from_joints(joints=[], additional_unjointed_timbers=[tagged, untagged])

    def test_the_layers_payload_carries_typed_timber_tags(self, frame):
        by_name = {entry["name"]: entry for entry in runner.serialize_layers(frame)["timbers"]}
        assert by_name["A"]["tags"] == [
            {"kind": "generic", "name": "wonky"},
            {"kind": "member", "name": "post"},
        ]
        assert by_name["B"]["tags"] == []

    def test_joints_carry_no_tags_at_all(self, frame):
        for joint in runner.serialize_layers(frame)["joints"]:
            assert "tags" not in joint

    def test_the_mesh_payload_carries_the_same_tags(self, frame):
        cut_timber = next(ct for ct in frame.cut_timbers if ct.timber.ticket.path == "A")
        payload = runner._cut_timber_to_triangle_mesh_payload(
            cut_timber, cut_timber.render_timber_with_cuts_csg_local(), "A#0"
        )
        assert payload["tags"] == [
            {"kind": "generic", "name": "wonky"},
            {"kind": "member", "name": "post"},
        ]
