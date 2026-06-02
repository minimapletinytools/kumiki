from __future__ import annotations

from typing import Optional

from kumiki.librarian import Param, discover_callable_render_parameters, resolve_callable_render_parameters
from kumiki.rule import V3


def test_optional_none_parameter_is_not_exposed_as_render_parameter() -> None:
    def build(center: Optional[V3] = None):
        return center

    descriptors, resolved = resolve_callable_render_parameters(build, None)

    assert descriptors == []
    assert resolved == {}


def test_declared_none_parameter_preserves_none_default() -> None:
    def build(label=Param(None, kind="string", description="Optional label")):
        return label

    descriptors = discover_callable_render_parameters(build)
    assert len(descriptors) == 1
    assert descriptors[0].name == "label"

    _, resolved = resolve_callable_render_parameters(build, None)
    assert resolved == {"label": None}