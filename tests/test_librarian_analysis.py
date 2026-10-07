"""Tests for the pure-AST kumiki librarian analyzer."""

from kumiki.librarian import analyze_source


def test_decorated_frames_in_source_order():
    src = """
from kumiki import *

@frame
def stool(k: Kiwari) -> Frame: ...

@frame
def bench(k: Kiwari) -> Frame: ...
"""
    info = analyze_source(src, "f.py")
    assert [(e.name, e.kind) for e in info.frames] == [("stool", "function"), ("bench", "function")]
    assert info.multiple_frames is True
    assert info.tools == []


def test_decorated_tools_are_tools_not_frames():
    src = """
from kumiki import *

@frame
def stool(k: Kiwari) -> Frame: ...

@tool
def report(frame: Frame, k: Kiwari) -> str: ...
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["stool"]
    assert [e.name for e in info.tools] == ["report"]


def test_decorators_by_name_alias_or_attribute():
    src = """
import kumiki
from kumiki import frame as view
from kumiki.frame_entries import tool

@view
def a(k): ...

@kumiki.frame
def b(k): ...

@tool
def c(frame, k): ...
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["a", "b"]
    assert [e.name for e in info.tools] == ["c"]


def test_a_decorator_from_elsewhere_is_ignored():
    src = """
from somewhere_else import frame

@frame
def a(k): ...
"""
    info = analyze_source(src, "f.py")
    assert info.frames == []


def test_methods_and_nested_defs_not_counted():
    src = """
from kumiki import *
class C:
    @frame
    def m(self, k): ...

def outer():
    @frame
    def inner(k): ...
    return inner
"""
    info = analyze_source(src, "f.py")
    assert info.frames == []


def test_empty_or_unrelated_file():
    info = analyze_source("x = 1\nprint('hi')\n", "f.py")
    assert info.has_anything is False


def test_untyped_example_assignment_detected():
    src = """
from kumiki import Frame
example = Frame.from_joints([])
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["example"]


def test_annotated_example_assignment_detected():
    src = """
import kumiki
example: kumiki.Frame = kumiki.Frame.from_joints([])
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["example"]


def test_untyped_example_function_recognized():
    src = """
def example():
    return something()
"""
    info = analyze_source(src, "f.py")
    assert [e.name for e in info.frames] == ["example"]
    assert info.frames[0].kind == "function"


def test_build_frame_is_still_listed():
    src = """
def build_frame():
    return something()
"""
    info = analyze_source(src, "f.py")
    assert [(e.name, e.kind) for e in info.frames] == [("build_frame", "function")]


def test_forms_the_runner_never_built_are_not_listed():
    src = """
from kumiki import *
my_thing: Frame = Frame.from_joints([])
giraffe = Frame()
def build_anything() -> Frame: ...
"""
    info = analyze_source(src, "f.py")
    assert info.frames == []
