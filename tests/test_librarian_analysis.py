"""Tests for the pure-AST kumiki librarian analyzer."""

from kumiki.librarian_analysis import analyze_source


def test_typed_frame_assignment_detected():
    src = """
from kumiki import Frame
my_thing: Frame = Frame.from_joints([])
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["my_thing"]
    assert info.frames[0].kind == "var"


def test_frame_constructor_call_detected_without_annotation():
    src = """
from kumiki import Frame
giraffe = Frame.from_joints([])
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["giraffe"]


def test_aliased_frame_import_detected():
    src = """
from kumiki import Frame as F
structure = F()
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["structure"]


def test_return_annotation_detected_for_function():
    src = """
from kumiki import Frame
def build_anything() -> Frame:
    return Frame.from_joints([])
"""
    info = analyze_source(src, "f.py")
    assert [(e.name, e.kind) for e in info.frames] == [("build_anything", "function")]


def test_dotted_kumiki_frame_attribute_detected():
    src = """
import kumiki
example: kumiki.Frame = kumiki.Frame.from_joints([])
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["example"]


def test_methods_and_nested_defs_not_counted():
    src = """
from kumiki import Frame
class C:
    def m(self) -> Frame:
        ...

def outer():
    def inner() -> Frame:
        ...
    return inner
"""
    info = analyze_source(src, "f.py")
    assert info.frames == []


def test_multiple_frames_chosen_is_last_and_flag_set():
    src = """
from kumiki import Frame
a: Frame = Frame()
b: Frame = Frame()
def c() -> Frame: ...
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["a", "b", "c"]
    assert info.chosen_frame is not None and info.chosen_frame.name == "c"
    assert info.multiple_frames is True


def test_non_kumiki_frame_ignored():
    src = """
from somewhere_else import Frame
thing: Frame = Frame()
"""
    info = analyze_source(src, "f.py")
    assert info.frames == []


def test_string_form_annotation():
    src = """
from kumiki import Frame
thing: "Frame" = Frame()
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["thing"]


def test_empty_or_unrelated_file():
    info = analyze_source("x = 1\nprint('hi')\n", "f.py")
    assert info.has_anything is False


def test_star_import_from_kumiki_recognizes_frame():
    src = """
from kumiki import *

def build_frame() -> Frame:
    return Frame.from_joints([])
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["build_frame"]
