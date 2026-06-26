from __future__ import annotations

from pathlib import Path
from typing import Optional

from kumiki.librarian import (
    Param,
    _should_skip_dir,
    discover_callable_render_parameters,
    resolve_callable_render_parameters,
)
from kumiki.rule import V3, create_v3
from sympy import Rational


def test_untyped_none_parameter_is_not_exposed_as_render_parameter() -> None:
    def build(center=None):
        return center

    descriptors, resolved = resolve_callable_render_parameters(build, None)

    assert descriptors == []
    assert resolved == {}


def test_optional_v3_parameter_is_exposed_and_coerced() -> None:
    def build(center: Optional[V3] = None):
        return center

    descriptors = discover_callable_render_parameters(build)
    assert len(descriptors) == 1
    assert descriptors[0].name == "center"
    assert descriptors[0].kind == "v3"
    assert descriptors[0].optional is True

    _, default_resolved = resolve_callable_render_parameters(build, None)
    assert default_resolved == {"center": None}

    _, resolved = resolve_callable_render_parameters(build, {
        "center": {"x": "1/2", "y": "2", "z": "3"},
    })
    center = resolved["center"]
    assert center == create_v3(Rational(1, 2), Rational(2), Rational(3))


def test_declared_none_parameter_preserves_none_default() -> None:
    def build(label=Param(None, kind="string", description="Optional label")):
        return label

    descriptors = discover_callable_render_parameters(build)
    assert len(descriptors) == 1
    assert descriptors[0].name == "label"
    assert descriptors[0].optional is True

    _, resolved = resolve_callable_render_parameters(build, None)
    assert resolved == {"label": None}


def test_explicit_optional_v3_param_round_trips_default() -> None:
    default = create_v3(Rational(1), Rational(2), Rational(3))

    def build(center=Param(default, kind="v3", optional=True)):
        return center

    descriptors = discover_callable_render_parameters(build)
    assert len(descriptors) == 1
    assert descriptors[0].kind == "v3"
    assert descriptors[0].optional is True

    _, resolved = resolve_callable_render_parameters(build, None)
    assert resolved["center"] == default


def test_default_skip_dirs_include_test_fixtures() -> None:
    assert _should_skip_dir("test-fixtures", Path("/tmp/workspace/test-fixtures")) is True
    assert _should_skip_dir("test_fixtures", Path("/tmp/workspace/test_fixtures")) is True