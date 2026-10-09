"""@frame and @tool: marking a file's frames and tools, and admitting them by their signature."""

import types
from typing import Optional

import pytest

from kumiki import *
from kumiki.frame_decorators import module_entries, module_parameters, overlay_frames


def _module(**members) -> types.ModuleType:
    """A module holding `members`, each function made to belong to it as a file's would."""
    module = types.ModuleType("a_frame_file")
    for name, value in members.items():
        if callable(value) and hasattr(value, "__module__"):
            value.__module__ = module.__name__
        setattr(module, name, value)
    return module


def _post(name: str, x: float) -> CutTimber:
    timber = create_timber(bottom_position=create_v3(x, 0, 0), length=mm(1000), size=create_v2(mm(100), mm(100)),
                           length_direction=create_v3(0, 0, 1), width_direction=create_v3(1, 0, 0), ticket=name)
    return CutTimber(timber, cuts=[])


class TestDecorators:

    def test_they_leave_the_function_callable(self):
        @frame
        def posts(k: Kiwari) -> Frame:
            return Frame(cut_timbers=[_post("a", 0)])

        assert len(posts(kiwari()).cut_timbers) == 1


class TestAdmission:

    def test_well_typed_frames_and_tools_are_admitted_in_order(self):
        @frame
        def first(k: Kiwari) -> Frame:
            return Frame(cut_timbers=[])

        @frame
        def second(k: Optional[Kiwari]) -> Frame:
            return Frame(cut_timbers=[])

        @tool
        def report(frame: Frame, k: Kiwari) -> str:
            return ""

        entries = module_entries(_module(first=first, second=second, report=report))

        assert [entry.name for entry in entries.frames] == ["first", "second"]
        assert [entry.name for entry in entries.tools] == ["report"]
        assert entries.rejected == ()

    @pytest.mark.parametrize("source, reason", [
        ("@frame\ndef f(k) -> Frame: ...", "parameter 'k'"),
        ("@frame\ndef f(k: Kiwari): ...", "return"),
        ("@frame\ndef f(k: Kiwari, extra: int) -> Frame: ...", "1 parameter"),
        ("@frame\ndef f(*k: Kiwari) -> Frame: ...", "no *args"),
        ("@tool\ndef f(frame: Frame, k: Kiwari) -> int: ...", "return"),
        ("@tool\ndef f(k: Kiwari, frame: Frame) -> str: ...", "parameter 'k'"),
        ("@tool\ndef f(frame: Frame) -> str: ...", "2 parameter"),
        ("@frame\ndef f(k: 'NoSuchType') -> Frame: ...", "could not be read"),
    ])
    def test_a_wrong_signature_is_rejected_with_why(self, source, reason):
        namespace = dict(vars(__import__("kumiki")))
        namespace["__name__"] = "a_frame_file"
        exec(source, namespace)
        module = types.ModuleType("a_frame_file")
        module.__dict__.update(namespace)

        entries = module_entries(module)

        assert entries.frames == () and entries.tools == ()
        (rejected,) = entries.rejected
        assert reason in rejected.reason

    def test_string_annotations_are_resolved(self):
        namespace = dict(vars(__import__("kumiki")))
        namespace["__name__"] = "a_frame_file"
        exec("from __future__ import annotations\n@frame\ndef f(k: Kiwari) -> Frame: ...", namespace)
        module = types.ModuleType("a_frame_file")
        module.__dict__.update(namespace)

        assert [entry.name for entry in module_entries(module).frames] == ["f"]

    def test_functions_imported_from_elsewhere_are_not_this_file_s(self):
        @frame
        def borrowed(k: Kiwari) -> Frame:
            return Frame(cut_timbers=[])

        module = types.ModuleType("a_frame_file")
        setattr(module, "borrowed", borrowed)  # still belongs to this test module

        assert module_entries(module).frames == ()


class TestParameters:

    def test_the_one_module_level_kiwari(self):
        params = kiwari(posts=kiwari.count(2))

        assert module_parameters(_module(params=params)) is params

    def test_none_means_empty_parameters(self):
        assert dict(module_parameters(_module()).values) == {}

    def test_more_than_one_is_an_error(self):
        with pytest.raises(TypeError, match="one set of parameters"):
            module_parameters(_module(a=kiwari(x=kiwari.count(1)), b=kiwari(y=kiwari.count(2))))

    def test_a_file_that_marks_nothing_is_not_held_to_one(self):
        module = _module(a=kiwari(x=kiwari.count(1)), b=kiwari(y=kiwari.count(2)))

        assert module_entries(module).frames == ()


class TestOverlay:

    def test_every_frame_shown_together_with_the_shared_parameters(self):
        params = kiwari(posts=kiwari.count(2))
        left = Frame(cut_timbers=[_post("a", 0), _post("b", 1)], name="left")
        right = Frame(cut_timbers=[_post("c", 5)], name="right")

        shown = overlay_frames([left, right], "both", params)

        assert [cut.timber.ticket.path for cut in shown.cut_timbers] == ["a", "b", "c"]
        assert shown.name == "both" and shown.kiwari is params

    def test_one_frame_is_itself_with_the_parameters(self):
        params = kiwari(posts=kiwari.count(2))
        only = Frame(cut_timbers=[_post("a", 0)], name="only")

        shown = overlay_frames([only], None, params)

        assert shown.cut_timbers == only.cut_timbers and shown.name == "only" and shown.kiwari is params


class TestPatterns:

    def _patterns(self, source):
        namespace = dict(vars(__import__("kumiki")))
        namespace["__name__"] = "a_pattern_file"
        exec(source, namespace)
        module = types.ModuleType("a_pattern_file")
        module.__dict__.update(namespace)
        from kumiki.frame_decorators import module_patterns
        return module_patterns(module)

    def test_each_marked_function_is_a_pattern_in_source_order(self):
        patterns, rejected = self._patterns(
            "SIZES = kiwari(posts=kiwari.count(2))\n"
            "@pattern('group/second', tags=['main'], kiwari=SIZES)\n"
            "def b(k: Kiwari) -> Frame:\n"
            "    return Frame(cut_timbers=[], name=f\"{k.count('posts')} posts\")\n"
            "@pattern('group/first')\n"
            "def a(position=None) -> Frame:\n"
            "    return Frame(cut_timbers=[], name='a')\n")

        assert rejected == ()
        assert [(p.path, p.tags, p.kiwari is not None) for p in patterns] == [
            ("group/second", ["main"], True), ("group/first", [], False)]
        assert patterns[0].raise_at(kiwari={"posts": 3}).name == "3 posts"
        assert patterns[1].raise_at().name == "a"

    def test_the_return_annotation_decides_the_kind(self):
        patterns, _ = self._patterns(
            "@pattern('g/csg')\n"
            "def shape() -> CutCSG:\n"
            "    return HalfSpace(normal=create_v3(0, 0, 1))\n"
            "@pattern('g/frame')\n"
            "def whole() -> Frame:\n"
            "    return Frame(cut_timbers=[])\n")

        assert [p.pattern_type for p in patterns] == ["csg", "frame"]

    @pytest.mark.parametrize("source, reason", [
        ("@pattern('g/a')\ndef a(k: Kiwari) -> Frame: ...", "() -> Frame"),
        ("@pattern('g/a', kiwari=kiwari(x=kiwari.count(1)))\ndef a() -> Frame: ...", "1 parameter"),
        ("@pattern('g/a')\ndef a() -> str: ...", "return"),
        ("@pattern('g/a')\ndef a(position) -> Frame: ...", "need defaults"),
    ])
    def test_a_wrong_signature_is_rejected_with_why(self, source, reason):
        patterns, rejected = self._patterns(source)

        assert patterns == []
        assert reason in rejected[0].reason

    def test_an_alias_is_one_pattern(self):
        patterns, _ = self._patterns(
            "@pattern('g/a')\ndef a() -> Frame:\n    return Frame(cut_timbers=[])\nalso_a = a\n")

        assert [p.path for p in patterns] == ["g/a"]

    def test_a_path_is_required(self):
        with pytest.raises(TypeError, match="needs a path"):
            pattern("")
