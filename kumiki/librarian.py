"""
Librarian: discovery and loading of kumiki frame examples and pattern books.

This module owns the full librarian stack: AST-driven discovery, scanning,
pattern index files, and layered search roots. The JS bridge never reads any
of this directly — it always goes through the librarian CLI
(:mod:`kumiki.librarian_cli`).

Frame and pattern-list detection rules (see ``analyze_source``)
------------------------------------------------------------------

Detection never imports the file — it's pure ``ast`` inspection. A module-level
statement is recognized as a **frame** entry if either of these holds:

* **Type-based** (the primary path): the statement's *type* resolves to
  kumiki's canonical ``Frame`` (through aliases like ``from kumiki import
  Frame as F``, dotted forms like ``kumiki.timber.Frame``, or string
  annotations):

  - ``name: Frame = ...`` — annotation is ``Frame``
  - ``name = Frame(...)`` / ``name = Frame.from_joints(...)`` — RHS call
    constructs a ``Frame`` (checked even when the annotation, if any, isn't
    ``Frame``)
  - ``def foo(...) -> Frame:`` — return annotation is ``Frame``

* **Name-based fallback** (unconditional, ignores types entirely): a target
  or function literally named ``example`` or ``build_frame`` is *always*
  treated as a frame entry, whether or not it's annotated ``-> Frame``. This
  is why ``docs/agent_usage_instructions.md`` can say "just call it
  ``example``" as the simple convention, while the type-based rule is what
  actually backs it.

A module-level statement is recognized as a **pattern list** entry only by
name: ``patterns = [...]`` or ``patterns: ... = [...]``, list literal or
call, no content type-checking at this stage (that happens after import, in
``_resolve_pattern_list``).

When a file has multiple frame entries, ``ModuleStaticInfo.chosen_frame`` is
the **last** one in source order — that's what downstream consumers render.

Two-phase scan (see ``_scan_single_file``)
-------------------------------------------

1. Static AST analysis always runs first and is cheap (no import).
2. A file is only actually imported (``exec_module``) if its static info has
   a ``patterns = [...]`` candidate (``needs_import = bool(static_info.pattern_lists)``).
   **Frame-only files are never imported during a scan** — only their static
   info (names/kinds/line numbers) is captured. Building the real ``Frame``
   object (calling ``example()``/``build_frame()``) is deferred entirely to
   the runner, on demand, when a specific file is opened/rendered.

Pattern index files: the caching path
--------------------------------------

``build_pattern_index`` / ``refresh_pattern_index`` / ``read_pattern_index`` /
``write_pattern_index`` maintain a JSON cache (keyed by per-file sha256) of
the same scan results above, so unchanged files don't need to be re-scanned
or re-imported:

* ``build_pattern_index(root, prior_index=...)`` — for each file, reuses the
  prior entry verbatim if its sha256 still matches; only changed/new files
  get a real scan. Returns both a per-file ``entries`` dict (each entry has
  its own ``frames``/``chosen_frame_name``/``patternbook``) and a flattened,
  path-sorted ``frame_examples`` summary list, mirroring what
  ``build_scan_index`` returns for a live scan.
* ``refresh_pattern_index(root, index_path)`` — reads the index already on
  disk at *index_path* as ``prior_index``, rebuilds against *root*, writes
  the result back to *index_path*. This is **how to keep an index file up to
  date**: call it (or ``python -m kumiki.librarian_cli refresh-index <root>
  <index_path>``) whenever the source tree may have changed, instead of
  hand-editing or blowing away the cache.
* ``load_or_build_pattern_index_for_root`` (used by ``scan_all_roots``) is
  the actual "check for an index file first" behavior: for the ``kumiki`` /
  dependency search roots it trusts a bundled ``_pattern_index.json`` as-is
  with **no** sha-diffing at all (installed packages are assumed immutable —
  that file is what ``tools/build_pattern_index.py`` generates at release
  time and ships in the wheel). Workspace roots always get a fresh
  ``build_pattern_index`` call instead.

Caveat: as of this writing the live kigumi extension bridge
(``kigumi/frame-scanner.js``) only ever calls the CLI's ``scan-workspace``
action (→ ``scan_workspace_index`` → ``scan_library_folder``), which does a
full live AST (+ import-if-needed) scan every time and does **not** consult
any pattern index file. The index/cache machinery above is real and tested,
but currently only exercised for the bundled ``kumiki``/dependency roots via
``scan_all_roots`` — not (yet) for the workspace's own live-edited files.

Layered search roots
---------------------

``discover_search_roots`` returns, in order: the workspace, the installed
``kumiki`` package directory, and any explicitly declared kumiki-aware
dependencies. A dependency is only included if it's both declared in
``.kigumi/config.json`` (``kumiki_dependencies``) *and* its installed
metadata's ``Requires-Dist`` actually lists ``kumiki``.
"""

from __future__ import annotations

import ast
import contextlib
from dataclasses import dataclass, field, replace
import inspect
import importlib.metadata
import importlib.util
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sys
import textwrap
import traceback
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Tuple, get_args, get_origin

from sympy import Float, Rational

from .rule import scalar
from .patternbook import Pattern


_DYNAMIC_MODULE_PREFIX = "giraffe_librarian_dynamic"

_PARAM_KIND_VALUES: Tuple[str, ...] = ("number", "boolean", "string", "enum", "v3")


# ---------------------------------------------------------------------------
# AST-driven static analysis (no imports)
# ---------------------------------------------------------------------------
#
# Identifies module-level entries that produce a ``Frame`` or ``PatternBook``
# — either by typed annotation, by known constructor call, or by function
# return annotation. Detection is done without importing the file.
# Recognition is **type-based, not name-based**: the local identifier is
# irrelevant.
#
# The analyzer resolves identifiers through the file's ``import`` statements
# so aliased imports (``from kumiki import Frame as F``) are handled
# correctly.
#
# Frames and patternbooks are only detected when they refer to kumiki's
# canonical ``Frame``/``PatternBook`` symbols. We accept any kumiki submodule
# path (``kumiki``, ``kumiki.timber``, ``kumiki.patternbook``, etc.) as a
# valid provider — kumiki re-exports both at the top level.

# Canonical type names we recognize.  Module-of-origin checks are restricted to
# kumiki and its submodules; any other origin is ignored.
_FRAME_NAME = "Frame"


@dataclass(frozen=True)
class StaticEntry:
    """A single module-level frame or patternbook entry."""
    name: str
    kind: str  # "var" | "function" | "factory"
    lineno: int


@dataclass
class ModuleStaticInfo:
    """Result of statically analyzing a single source file."""
    file_path: str
    frames: List[StaticEntry] = field(default_factory=list)
    pattern_lists: List[StaticEntry] = field(default_factory=list)
    parse_error: Optional[str] = None

    @property
    def has_anything(self) -> bool:
        return bool(self.frames) or bool(self.pattern_lists)

    @property
    def chosen_frame(self) -> Optional[StaticEntry]:
        return self.frames[-1] if self.frames else None

    @property
    def multiple_frames(self) -> bool:
        return len(self.frames) > 1


def _is_kumiki_module(module_name: Optional[str]) -> bool:
    if not module_name:
        return False
    return module_name == "kumiki" or module_name.startswith("kumiki.")


def _collect_kumiki_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local identifier -> canonical kumiki symbol name.

    Only module-level ``import`` / ``from ... import`` statements are inspected.
    The mapping contains entries like ``{"F": "Frame", "PB": "PatternBook"}``.
    Symbols not from kumiki, and kumiki names other than ``Frame``/``PatternBook``,
    are ignored.

    ``from kumiki[...] import *`` is treated as bringing ``Frame`` and
    ``PatternBook`` into scope under their canonical names — kumiki re-exports
    both at the top level via star imports in its package ``__init__``.
    """
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if not _is_kumiki_module(node.module):
                continue
            for alias in node.names:
                if alias.name == "*":
                    aliases[_FRAME_NAME] = _FRAME_NAME
                    continue
                if alias.name == _FRAME_NAME:
                    local = alias.asname or alias.name
                    aliases[local] = alias.name
    return aliases


def _annotation_target(annotation: Optional[ast.expr], aliases: dict[str, str]) -> Optional[str]:
    """If ``annotation`` ultimately references a kumiki ``Frame``,
    return the canonical name; else ``None``.

    Handles bare names (``Frame``), attribute access (``kumiki.Frame``,
    ``kumiki.timber.Frame``), and string-form annotations (``"Frame"``).
    Stripping of ``Optional[...]`` / ``list[...]`` / etc. is intentionally not
    done — entries are only counted when the value *is* a Frame,
    not a container of them.
    """
    if annotation is None:
        return None
    # PEP 563 string-form: "Frame"
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        text = annotation.value.strip()
        if text in aliases:
            return aliases[text]
        if text == _FRAME_NAME:
            return text
        # accept dotted forms like "kumiki.Frame"
        tail = text.rsplit(".", 1)[-1]
        if tail == _FRAME_NAME:
            return tail
        return None
    if isinstance(annotation, ast.Name):
        return aliases.get(annotation.id)
    if isinstance(annotation, ast.Attribute):
        # Walk attribute chain, ensure root is "kumiki"
        attr = annotation
        parts: List[str] = []
        while isinstance(attr, ast.Attribute):
            parts.append(attr.attr)
            attr = attr.value
        if isinstance(attr, ast.Name) and attr.id == "kumiki":
            if parts and parts[0] == _FRAME_NAME:
                return parts[0]
    return None


def _call_target(call: ast.Call, aliases: dict[str, str]) -> Optional[str]:
    """If ``call`` is a constructor or classmethod of ``Frame``,
    return the canonical name; else ``None``.

    Recognizes ``Frame(...)``, ``Frame.from_joints(...)``, ``kumiki.Frame(...)``,
    ``kumiki.timber.Frame.from_joints(...)``, and the aliased equivalents.
    """
    func = call.func
    # Direct: Frame(...) or alias F(...)
    if isinstance(func, ast.Name):
        canonical = aliases.get(func.id)
        if canonical == _FRAME_NAME:
            return canonical
        return None
    # Attribute: X.method(...) or kumiki[.sub].Frame(...)
    if isinstance(func, ast.Attribute):
        # Case A: <Frame-or-alias>.classmethod(...)
        if isinstance(func.value, ast.Name):
            canonical = aliases.get(func.value.id)
            if canonical == _FRAME_NAME:
                return canonical
        # Case B: kumiki[.sub].Frame(...) — last attr is Frame, root is "kumiki"
        parts: List[str] = []
        node: ast.expr = func
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name) and node.id == "kumiki":
            for candidate in parts:
                if candidate == _FRAME_NAME:
                    return candidate
    return None


def _is_pattern_list_assignment(node: ast.Assign) -> bool:
    """True if this is a module-level `patterns = [...]` assignment."""
    if not isinstance(node.value, (ast.List, ast.Call)):
        return False
    for target in node.targets:
        for name in _record_target_names(target):
            if name == "patterns":
                return True
    return False


def _is_pattern_list_ann_assign(node: ast.AnnAssign) -> bool:
    """True if this is a module-level `patterns: ... = [...]` annotation."""
    return (
        isinstance(node.target, ast.Name)
        and node.target.id == "patterns"
    )


def _record_target_names(target: ast.expr) -> List[str]:
    """Extract simple identifier targets from an assignment LHS."""
    names: List[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.extend(_record_target_names(elt))
    return names


def analyze_source(source: str, file_path: str) -> ModuleStaticInfo:
    """Analyze raw source text and return its static info."""
    info = ModuleStaticInfo(file_path=file_path)
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as exc:
        info.parse_error = f"SyntaxError: {exc}"
        return info

    aliases = _collect_kumiki_aliases(tree)

    for node in tree.body:
        # Typed assignment: name: Frame = ...
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            canonical = _annotation_target(node.annotation, aliases)
            if canonical == _FRAME_NAME:
                info.frames.append(StaticEntry(node.target.id, "var", node.lineno))
                continue
            # Also accept call-on-rhs even when annotated to something else
            if isinstance(node.value, ast.Call):
                rhs = _call_target(node.value, aliases)
                if rhs == _FRAME_NAME:
                    info.frames.append(StaticEntry(node.target.id, "var", node.lineno))
            # patterns: List[Pattern] = [...] annotated assignment
            if _is_pattern_list_ann_assign(node):
                info.pattern_lists.append(StaticEntry("patterns", "var", node.lineno))
            continue

        # Untyped assignment: name = Frame(...) / Frame.from_joints(...)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            canonical = _call_target(node.value, aliases)
            if canonical == _FRAME_NAME:
                for target in node.targets:
                    for name in _record_target_names(target):
                        info.frames.append(StaticEntry(name, "var", node.lineno))
                continue
            # Check for patterns = [...] (new pattern list system)
            if _is_pattern_list_assignment(node):
                info.pattern_lists.append(StaticEntry("patterns", "var", node.lineno))
            continue

        # patterns = [...] list literal assignment
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            if _is_pattern_list_assignment(node):
                info.pattern_lists.append(StaticEntry("patterns", "var", node.lineno))
            continue

        # Recognize example/build_frame assignments even if the RHS isn't a Frame() call
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for name in _record_target_names(target):
                    if name == "example" or name == "build_frame":
                        info.frames.append(StaticEntry(name, "var", node.lineno))
            continue

        # def name(...) -> Frame: ...
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            canonical = _annotation_target(node.returns, aliases)
            if canonical == _FRAME_NAME:
                info.frames.append(StaticEntry(node.name, "function", node.lineno))
            # Also recognize build_frame() even without explicit Frame annotation
            elif node.name == "build_frame":
                info.frames.append(StaticEntry(node.name, "function", node.lineno))
            # Also recognize example() even without explicit Frame annotation
            elif node.name == "example":
                info.frames.append(StaticEntry(node.name, "function", node.lineno))

    return info


def analyze_file(file_path: str) -> ModuleStaticInfo:
    """Read and analyze a single source file."""
    info = ModuleStaticInfo(file_path=file_path)
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        info.parse_error = f"OSError: {exc}"
        return info
    return analyze_source(source, file_path)


# ---------------------------------------------------------------------------
# Author-facing render parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Param:
    """Author-facing parameter declaration helper.

    Use as a callable default value, e.g.:

        def build_frame(width=Param(scalar(2), description="Timber width")):
            ...
    """

    default: Any
    description: str = ""
    kind: Optional[Literal["number", "boolean", "string", "enum", "v3"]] = None
    options: Optional[Tuple[str, ...]] = None
    minimum: Optional[Any] = None
    maximum: Optional[Any] = None
    optional: Optional[bool] = None


@dataclass(frozen=True)
class RenderParameterDescriptor:
    name: str
    default_value: Any
    kind: Literal["number", "boolean", "string", "enum", "v3"]
    description: str = ""
    options: Tuple[str, ...] = ()
    minimum: Optional[Any] = None
    maximum: Optional[Any] = None
    optional: bool = False

    def to_protocol_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "default": serialize_render_parameter_value(self.default_value),
        }
        if self.options:
            payload["options"] = [str(option) for option in self.options]
        if self.minimum is not None:
            payload["minimum"] = serialize_render_parameter_value(self.minimum)
        if self.maximum is not None:
            payload["maximum"] = serialize_render_parameter_value(self.maximum)
        if self.optional:
            payload["optional"] = True
        return payload


def _looks_like_sympy_number(value: Any) -> bool:
    return hasattr(value, "is_real") and hasattr(value, "evalf")


def _looks_like_v3_value(value: Any) -> bool:
    shape = getattr(value, "shape", None)
    return shape in ((3, 1), (1, 3))


def _infer_parameter_kind_from_annotation(annotation: Any, annotation_text: Optional[str]) -> Optional[Literal["number", "boolean", "string", "enum", "v3"]]:
    text = (annotation_text or "").replace(" ", "")
    if "V3" in text:
        return "v3"
    if annotation is bool:
        return "boolean"
    if annotation is str:
        return "string"
    if annotation in (int, float, Rational, Float):
        return "number"
    return None


def _infer_parameter_kind(default_value: Any, annotation: Any = None, annotation_text: Optional[str] = None) -> Literal["number", "boolean", "string", "enum", "v3"]:
    annotation_kind = _infer_parameter_kind_from_annotation(annotation, annotation_text)
    if annotation_kind is not None:
        return annotation_kind
    if isinstance(default_value, bool):
        return "boolean"
    if isinstance(default_value, str):
        return "string"
    if _looks_like_v3_value(default_value):
        return "v3"
    if isinstance(default_value, (int, float, Rational, Float)):
        return "number"
    if _looks_like_sympy_number(default_value):
        return "number"
    return "string"


def _normalize_param_options(options: Optional[Iterable[Any]]) -> Tuple[str, ...]:
    if options is None:
        return ()
    return tuple(str(option) for option in options)


def _strip_optional_annotation_text(annotation_text: Optional[str]) -> Optional[str]:
    if annotation_text is None:
        return None
    stripped = annotation_text.strip()
    compact = stripped.replace(" ", "")
    if compact.startswith("Optional[") and compact.endswith("]"):
        return stripped[stripped.find("[") + 1:-1].strip()
    return stripped


def _unwrap_optional_annotation(annotation: Any, annotation_text: Optional[str]) -> Tuple[Any, bool, Optional[str]]:
    optional = False
    inner_annotation = annotation
    inner_text = annotation_text

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None and args:
        non_none_args = tuple(arg for arg in args if arg is not type(None))
        if len(non_none_args) == len(args) - 1:
            optional = True
            inner_annotation = non_none_args[0]

    compact = (annotation_text or "").replace(" ", "")
    if "Optional[" in compact or "|None" in compact or "None|" in compact:
        optional = True
        inner_text = _strip_optional_annotation_text(annotation_text)

    return inner_annotation, optional, inner_text


def _extract_parameter_annotation_texts(callable_obj: Any) -> Dict[str, str]:
    try:
        source = textwrap.dedent(inspect.getsource(callable_obj))
    except (OSError, TypeError):
        return {}

    try:
        module = ast.parse(source)
    except SyntaxError:
        return {}

    target_name = getattr(callable_obj, "__name__", None)
    if not target_name:
        return {}

    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_name:
            parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            result: Dict[str, str] = {}
            for param in parameters:
                if param.annotation is not None:
                    result[param.arg] = ast.unparse(param.annotation)
            return result
    return {}


def _descriptor_from_signature_parameter(
    parameter: inspect.Parameter,
    annotation_text: Optional[str] = None,
) -> Optional[RenderParameterDescriptor]:
    if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
        return None

    if parameter.default is inspect.Parameter.empty:
        # Only optional/defaulted parameters are currently exposed in the UI.
        return None

    annotation = parameter.annotation if parameter.annotation is not inspect.Parameter.empty else None
    inner_annotation, annotation_is_optional, inner_annotation_text = _unwrap_optional_annotation(annotation, annotation_text)

    if parameter.default is None and not annotation_is_optional:
        return None

    if isinstance(parameter.default, Param):
        declared = parameter.default
        default_value = declared.default
        declared_kind = declared.kind
        if declared_kind is None:
            kind = _infer_parameter_kind(default_value, inner_annotation, inner_annotation_text)
        else:
            kind = str(declared_kind)
            if kind not in _PARAM_KIND_VALUES:
                raise ValueError(
                    f"Parameter '{parameter.name}' has invalid kind '{declared_kind}'. "
                    f"Expected one of: {_PARAM_KIND_VALUES}"
                )
        options = _normalize_param_options(declared.options)
        if kind == "enum" and not options:
            raise ValueError(
                f"Parameter '{parameter.name}' declared as enum must provide options"
            )
        optional = declared.optional if declared.optional is not None else (default_value is None or annotation_is_optional)
        return RenderParameterDescriptor(
            name=parameter.name,
            default_value=default_value,
            kind=kind,  # type: ignore[arg-type]
            description=declared.description,
            options=options,
            minimum=declared.minimum,
            maximum=declared.maximum,
            optional=optional,
        )

    if parameter.default is None:
        kind = _infer_parameter_kind_from_annotation(inner_annotation, inner_annotation_text)
        if kind is None:
            return None
        return RenderParameterDescriptor(
            name=parameter.name,
            default_value=None,
            kind=kind,
            description="",
            options=(),
            minimum=None,
            maximum=None,
            optional=True,
        )

    inferred_kind = _infer_parameter_kind(parameter.default, inner_annotation, inner_annotation_text)
    return RenderParameterDescriptor(
        name=parameter.name,
        default_value=parameter.default,
        kind=inferred_kind,
        description="",
        options=(),
        minimum=None,
        maximum=None,
        optional=annotation_is_optional,
    )


def discover_callable_render_parameters(
    callable_obj: Any,
    *,
    skip_first_parameter: bool = False,
) -> List[RenderParameterDescriptor]:
    """Inspect a callable signature and return render-parameter descriptors."""
    signature = inspect.signature(callable_obj)
    annotation_texts = _extract_parameter_annotation_texts(callable_obj)
    discovered: List[RenderParameterDescriptor] = []
    parameters = list(signature.parameters.values())

    if skip_first_parameter and parameters:
        parameters = parameters[1:]

    for parameter in parameters:
        descriptor = _descriptor_from_signature_parameter(
            parameter,
            annotation_text=annotation_texts.get(parameter.name),
        )
        if descriptor is not None:
            discovered.append(descriptor)
    return discovered


def _coerce_bool(value: Any, param_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"Parameter '{param_name}' expects a boolean value")


def _coerce_number(value: Any, param_name: str) -> Any:
    if isinstance(value, bool):
        return scalar(1 if value else 0)
    if isinstance(value, int):
        return scalar(value)
    if isinstance(value, float):
        return scalar(str(value))
    if isinstance(value, (Rational, Float)):
        return value
    if _looks_like_sympy_number(value):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"Parameter '{param_name}' expects a non-empty number")
        try:
            return scalar(stripped)
        except Exception:
            try:
                return scalar(stripped)
            except Exception as exc:
                raise ValueError(
                    f"Parameter '{param_name}' expects a numeric value, got '{value}'"
                ) from exc
    raise ValueError(f"Parameter '{param_name}' expects a numeric value")


def _coerce_v3(value: Any, param_name: str) -> Any:
    from .rule import create_v3, scalar

    if _looks_like_v3_value(value):
        return create_v3(
            _coerce_number(value[0], f"{param_name}.x"),
            _coerce_number(value[1], f"{param_name}.y"),
            _coerce_number(value[2], f"{param_name}.z"),
        )
    if isinstance(value, dict):
        return create_v3(
            _coerce_number(value.get("x"), f"{param_name}.x"),
            _coerce_number(value.get("y"), f"{param_name}.y"),
            _coerce_number(value.get("z"), f"{param_name}.z"),
        )
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return create_v3(
            _coerce_number(value[0], f"{param_name}.x"),
            _coerce_number(value[1], f"{param_name}.y"),
            _coerce_number(value[2], f"{param_name}.z"),
        )
    raise ValueError(f"Parameter '{param_name}' expects a V3 value")


def _coerce_parameter_value(value: Any, descriptor: RenderParameterDescriptor) -> Any:
    if descriptor.kind == "boolean":
        return _coerce_bool(value, descriptor.name)
    if descriptor.kind == "number":
        coerced = _coerce_number(value, descriptor.name)
        if descriptor.minimum is not None and coerced < descriptor.minimum:
            raise ValueError(
                f"Parameter '{descriptor.name}' must be >= {descriptor.minimum}, got {coerced}"
            )
        if descriptor.maximum is not None and coerced > descriptor.maximum:
            raise ValueError(
                f"Parameter '{descriptor.name}' must be <= {descriptor.maximum}, got {coerced}"
            )
        return coerced
    if descriptor.kind == "v3":
        return _coerce_v3(value, descriptor.name)
    if descriptor.kind == "enum":
        coerced = str(value)
        if coerced not in descriptor.options:
            raise ValueError(
                f"Parameter '{descriptor.name}' must be one of {list(descriptor.options)}, got '{coerced}'"
            )
        return coerced
    return str(value)


def resolve_callable_render_parameters(
    callable_obj: Any,
    provided_values: Optional[Mapping[str, Any]],
    *,
    skip_first_parameter: bool = False,
) -> Tuple[List[RenderParameterDescriptor], Dict[str, Any]]:
    """Return (descriptors, resolved kwargs) for a callable.

    Resolved kwargs include defaults plus any provided overrides.
    """
    descriptors = discover_callable_render_parameters(
        callable_obj,
        skip_first_parameter=skip_first_parameter,
    )

    provided = dict(provided_values or {})
    resolved: Dict[str, Any] = {}
    for descriptor in descriptors:
        if descriptor.name in provided:
            value = provided[descriptor.name]
        else:
            value = descriptor.default_value
        if value is None:
            resolved[descriptor.name] = None
            continue
        resolved[descriptor.name] = _coerce_parameter_value(value, descriptor)

    return descriptors, resolved


def serialize_render_parameter_value(value: Any) -> Any:
    """Convert render parameter values to JSON-friendly primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _looks_like_v3_value(value):
        return {
            "x": serialize_render_parameter_value(value[0]),
            "y": serialize_render_parameter_value(value[1]),
            "z": serialize_render_parameter_value(value[2]),
        }
    if isinstance(value, (Rational, Float)):
        return str(value)
    if _looks_like_sympy_number(value):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serialize_render_parameter_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): serialize_render_parameter_value(item)
            for key, item in value.items()
        }
    return str(value)


@dataclass
class LibrarianModuleRecord:
    relative_path: str
    module_name: str
    pattern_list: Optional[List[Pattern]] = None
    warnings: List[str] = field(default_factory=list)
    load_error: Optional[str] = None
    load_error_traceback: Optional[str] = None
    static_info: Optional[ModuleStaticInfo] = None
    content_sha256: Optional[str] = None


@dataclass
class LibrarianScanResult:
    root_folder: str
    modules: List[LibrarianModuleRecord] = field(default_factory=list)

    @property
    def errors(self) -> List[str]:
        return [
            f"{module.relative_path}: {module.load_error}"
            for module in self.modules
            if module.load_error is not None
        ]

    @property
    def pattern_lists(self) -> List[List[Pattern]]:
        return [
            module.pattern_list
            for module in self.modules
            if module.pattern_list is not None
        ]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


_DEFAULT_SKIP_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".nox", ".eggs", ".idea", ".vscode", ".vscode-test",
    "oldcrap", "test-fixtures", "test_fixtures",
})

_DEFAULT_SKIP_PATH_SEGMENTS = (
    "site-packages", "htmlcov", "coverage", "step_test_output",
)

# Well-known third-party Python package directory names.  Any subdirectory
# with one of these names is treated as a vendored dependency and never
# scanned — kumiki's own deps (sympy, numpy, trimesh, manifold3d) plus other
# popular scientific packages.  This prevents vendored copies (e.g.
# ``fusion360/libs/numpy/``) from being walked.  Users can extend via
# ``.kigumi/config.json`` if they have a directory legitimately named after
# one of these packages.
_KNOWN_THIRD_PARTY_PACKAGE_DIRS = frozenset({
    # kumiki runtime deps
    "sympy", "numpy", "trimesh", "manifold3d",
    # common scientific / utility deps that often get vendored
    "mpmath", "scipy", "pandas", "matplotlib", "sklearn", "scikit_learn",
    "networkx", "shapely", "rtree", "pillow", "PIL",
    "cython", "Cython",
    # testing / packaging machinery that sometimes ends up vendored
    "pytest", "_pytest", "iniconfig", "pluggy", "exceptiongroup",
    "setuptools", "pkg_resources", "_distutils_hack", "wheel",
    "coverage", "tomli", "packaging",
})


def _load_workspace_skip_extras(root_folder: Path) -> Tuple[frozenset[str], Tuple[str, ...]]:
    """Read additional skip-dir names/path-segments from ``.kigumi/config.json``.

    Supported keys (both optional):
      * ``scan_skip_dirs``: list of directory names to skip (matched against
        ``Path.name``).
      * ``scan_skip_path_segments``: list of strings; a directory is skipped
        if any segment appears anywhere in its absolute path parts.
    """
    config_path = root_folder / ".kigumi" / "config.json"
    if not config_path.exists():
        return frozenset(), ()
    try:
        data = json.loads(config_path.read_text())
    except (OSError, ValueError):
        return frozenset(), ()
    if not isinstance(data, dict):
        return frozenset(), ()
    names = data.get("scan_skip_dirs") or []
    segs = data.get("scan_skip_path_segments") or []
    name_set = frozenset(str(n) for n in names if isinstance(n, str))
    seg_tuple = tuple(str(s) for s in segs if isinstance(s, str))
    return name_set, seg_tuple


def _should_skip_dir(
    name: str,
    full_path: Path,
    *,
    extra_names: frozenset[str] = frozenset(),
    extra_segments: Tuple[str, ...] = (),
) -> bool:
    if not name:
        return True
    if name in _DEFAULT_SKIP_DIR_NAMES or name in extra_names:
        return True
    if name in _KNOWN_THIRD_PARTY_PACKAGE_DIRS:
        return True
    if name.endswith(".egg-info") or name.endswith(".dist-info"):
        return True
    parts = full_path.parts
    if any(seg in parts for seg in _DEFAULT_SKIP_PATH_SEGMENTS):
        return True
    if extra_segments and any(seg in parts for seg in extra_segments):
        return True
    return False


def _discover_python_files(root_folder: Path) -> List[Path]:
    extra_names, extra_segments = _load_workspace_skip_extras(root_folder)
    python_files: List[Path] = []
    stack: List[Path] = [root_folder]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except (OSError, PermissionError):
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    if not _should_skip_dir(
                        entry.name,
                        entry,
                        extra_names=extra_names,
                        extra_segments=extra_segments,
                    ):
                        stack.append(entry)
                    continue
                if not entry.is_file() or entry.suffix != ".py":
                    continue
                if entry.name == "__init__.py":
                    continue
                python_files.append(entry)
            except OSError:
                continue
    python_files.sort()
    return python_files


def _make_dynamic_module_name(root_folder: Path, file_path: Path) -> str:
    try:
        relative = file_path.relative_to(root_folder).with_suffix("")
    except ValueError:
        relative = Path(file_path.stem)
    flattened = "_".join(relative.parts) or file_path.stem
    return f"{_DYNAMIC_MODULE_PREFIX}_{flattened}"


def _file_sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_module_from_path(
    root_folder: Path, file_path: Path
) -> Tuple[Optional[Any], Optional[str], Optional[str], str]:
    module_name = _make_dynamic_module_name(root_folder, file_path)
    attempted_file = str(file_path)

    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return None, f"{attempted_file}: Could not create import spec", None, module_name

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
        return module, None, None, module_name
    except Exception as exc:
        if module_name in sys.modules:
            del sys.modules[module_name]
        tb = traceback.format_exc()
        return None, f"{attempted_file}: {type(exc).__name__}: {exc}", tb, module_name


def _resolve_pattern_list(module: Any, warnings: List[str]) -> Optional[List[Pattern]]:
    """Return List[Pattern] from module.patterns if it's a valid pattern list."""
    if not hasattr(module, "patterns"):
        return None
    candidate = getattr(module, "patterns")
    if not isinstance(candidate, list):
        warnings.append(
            f"module.patterns exists but is {type(candidate).__name__}, expected list"
        )
        return None
    patterns: List[Pattern] = []
    for i, item in enumerate(candidate):
        if not isinstance(item, Pattern):
            warnings.append(
                f"module.patterns[{i}] is {type(item).__name__}, expected Pattern — skipping"
            )
            continue
        patterns.append(item)
    return patterns if patterns else None


# ---------------------------------------------------------------------------
# Per-file analysis (no imports)
# ---------------------------------------------------------------------------


def might_contain_kumiki_frame(file_path: str) -> bool:
    """Return True iff ``file_path`` has any module-level frame or patternbook
    entry detected by the AST analyzer."""
    info = analyze_file(file_path)
    return info.has_anything


# ---------------------------------------------------------------------------
# Scan API
# ---------------------------------------------------------------------------


def _scan_single_file(
    root: Path,
    file_path: Path,
) -> LibrarianModuleRecord:
    try:
        relative_path = str(file_path.relative_to(root))
    except ValueError:
        relative_path = str(file_path)
    module_name = _make_dynamic_module_name(root, file_path)
    static_info = analyze_file(str(file_path))
    sha = _file_sha256(file_path)
    record = LibrarianModuleRecord(
        relative_path=relative_path,
        module_name=module_name,
        static_info=static_info,
        content_sha256=sha,
    )

    if not static_info.has_anything:
        return record

    needs_import = bool(static_info.pattern_lists)
    if not needs_import:
        return record

    module, load_error, load_error_traceback, real_module_name = _load_module_from_path(
        root, file_path
    )
    record.module_name = real_module_name
    record.load_error = load_error
    record.load_error_traceback = load_error_traceback

    if module is None:
        return record

    if static_info.pattern_lists:
        record.pattern_list = _resolve_pattern_list(module, record.warnings)
    return record


def scan_library_folder(folder_path: str) -> LibrarianScanResult:
    """Scan *folder_path* recursively.

    Frame files are not imported — only their static info is captured.
    """
    root_folder = Path(folder_path).resolve()
    if not root_folder.exists() or not root_folder.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")

    result = LibrarianScanResult(root_folder=str(root_folder))
    for file_path in _discover_python_files(root_folder):
        record = _scan_single_file(root_folder, file_path)
        result.modules.append(record)
    return result


def scan_specific_files(
    file_paths: List[str],
    root_folder: str,
) -> LibrarianScanResult:
    root = Path(root_folder).resolve()
    result = LibrarianScanResult(root_folder=str(root))
    for fp_str in file_paths:
        file_path = Path(fp_str).resolve()
        record = _scan_single_file(root, file_path)
        result.modules.append(record)
    return result


# ---------------------------------------------------------------------------
# Index payload (JSON-friendly)
# ---------------------------------------------------------------------------


def _frame_record_for_index(
    abs_path: str,
    rec: LibrarianModuleRecord,
) -> Dict[str, Any]:
    static = rec.static_info
    all_frame_names = [entry.name for entry in (static.frames if static else [])]
    chosen = static.chosen_frame if static else None
    chosen_name = chosen.name if chosen is not None else None
    chosen_kind = chosen.kind if chosen is not None else None
    return {
        "file_path": abs_path,
        "relative_path": rec.relative_path,
        "module_name": rec.module_name,
        # New, type-aware fields:
        "chosen_frame_name": chosen_name,
        "chosen_frame_kind": chosen_kind,
        "all_frame_names": all_frame_names,
        "multiple_frames": bool(static and static.multiple_frames),
        "content_sha256": rec.content_sha256,
        "load_error": rec.load_error,
        "warnings": list(rec.warnings or []),
    }


def build_scan_index(scan_result: LibrarianScanResult) -> Dict[str, Any]:
    """Build a JSON-friendly index from a :class:`LibrarianScanResult`."""
    root_folder = Path(scan_result.root_folder).resolve()
    patternbooks: List[Dict[str, Any]] = []
    frame_examples: List[Dict[str, Any]] = []

    for rec in scan_result.modules:
        abs_path = str((root_folder / rec.relative_path).resolve())
        warnings = list(rec.warnings or [])
        static = rec.static_info

        if rec.pattern_list is not None or (static and static.pattern_lists):
            pl = rec.pattern_list or []
            patterns_payload = [
                {"path": p.path, "tags": list(p.tags), "pattern_type": p.pattern_type}
                for p in pl
            ]
            patternbooks.append({
                "file_path": abs_path,
                "relative_path": rec.relative_path,
                "module_name": rec.module_name,
                "patterns": patterns_payload,
                "pattern_names": [p.name for p in pl],
                "patternbook_loaded": rec.pattern_list is not None,
                "content_sha256": rec.content_sha256,
                "load_error": rec.load_error,
                "warnings": warnings,
            })

        if static and static.frames:
            frame_examples.append(_frame_record_for_index(abs_path, rec))

    patternbooks.sort(key=lambda item: item["relative_path"])
    frame_examples.sort(key=lambda item: item["relative_path"])

    return {
        "root_folder": str(root_folder),
        "patternbooks": patternbooks,
        "frame_examples": frame_examples,
    }


def scan_library_index(folder_path: str) -> Dict[str, Any]:
    return build_scan_index(scan_library_folder(folder_path))


def scan_specific_files_index(
    file_paths: List[str],
    root_folder: str,
) -> Dict[str, Any]:
    return build_scan_index(scan_specific_files(file_paths, root_folder))


def scan_workspace_index(workspace_root: str) -> Dict[str, Any]:
    """Walk a workspace root (with sensible skip-dirs) and return the index.

    This is the single entrypoint used by the kigumi extension: it owns
    directory traversal, AST analysis, and patternbook loading so the JS
    side never duplicates any scanning logic.
    """
    return scan_library_index(workspace_root)


# ---------------------------------------------------------------------------
# Pattern index files (JSON cache, keyed by per-file sha256)
# ---------------------------------------------------------------------------


PATTERN_INDEX_SCHEMA_VERSION = 1
WORKSPACE_INDEX_RELATIVE_PATH = ".kigumi/pattern_index.json"
PACKAGE_INDEX_FILENAME = "_pattern_index.json"


def _entry_from_static(static_frames: Iterable[StaticEntry]) -> List[Dict[str, Any]]:
    return [
        {"name": entry.name, "kind": entry.kind, "lineno": entry.lineno}
        for entry in static_frames
    ]


def _patternbook_payload(pattern_list: Optional[List[Pattern]]) -> Optional[Dict[str, Any]]:
    if pattern_list is None:
        return None
    return {
        "patterns": [
            {"path": p.path, "tags": list(p.tags), "pattern_type": p.pattern_type}
            for p in pattern_list
        ],
        "pattern_names": [p.name for p in pattern_list],
    }


def _entry_from_record(rec: LibrarianModuleRecord) -> Dict[str, Any]:
    static = rec.static_info
    frames = list(static.frames) if static else []
    chosen = static.chosen_frame if static else None

    entry: Dict[str, Any] = {
        "relative_path": rec.relative_path,
        "module_name": rec.module_name,
        "sha256": rec.content_sha256,
        "frames": _entry_from_static(frames),
        "chosen_frame_name": chosen.name if chosen is not None else None,
        "chosen_frame_kind": chosen.kind if chosen is not None else None,
        "multiple_frames": bool(static and static.multiple_frames),
        "warnings": list(rec.warnings or []),
        "load_error": rec.load_error,
        "patternbook": _patternbook_payload(rec.pattern_list),
    }

    return entry


def build_pattern_index(
    root_folder: str,
    *,
    prior_index: Optional[Dict[str, Any]] = None,
    load_patternbooks: bool = True,
) -> Dict[str, Any]:
    """Build a pattern index dict for *root_folder*.

    When *prior_index* is supplied, entries whose source ``sha256`` still
    matches are reused verbatim — which avoids re-importing unchanged modules.

    Frame files are never imported here; only pattern-list files are imported.

    The returned dict has two views over the same per-file ``entries``:
    each entry carries its own ``frames``/``chosen_frame_name``/``patternbook``
    fields, and the top-level ``frame_examples`` list is a flattened,
    sorted-by-path summary of every entry that has at least one frame —
    mirroring the ``frame_examples`` list :func:`build_scan_index` returns,
    so both index shapes expose frame examples the same way.
    """
    root = Path(root_folder).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {root_folder}")

    prior_entries: Dict[str, Dict[str, Any]] = {}
    if prior_index and isinstance(prior_index.get("entries"), dict):
        prior_entries = prior_index["entries"]

    entries: Dict[str, Dict[str, Any]] = {}
    for file_path in _discover_python_files(root):
        try:
            relative_path = str(file_path.relative_to(root))
        except ValueError:
            relative_path = str(file_path)

        sha = _file_sha256(file_path)
        cached = prior_entries.get(relative_path)
        if (
            cached is not None
            and sha is not None
            and cached.get("sha256") == sha
        ):
            entries[relative_path] = cached
            continue

        # No reusable cache: do a real scan of just this file.
        static = analyze_file(str(file_path))
        if not static.has_anything:
            continue

        record = _scan_single_file(root, file_path)
        entries[relative_path] = _entry_from_record(record)

    frame_examples = [
        {
            "relative_path": entry["relative_path"],
            "module_name": entry["module_name"],
            "chosen_frame_name": entry.get("chosen_frame_name"),
            "chosen_frame_kind": entry.get("chosen_frame_kind"),
            "all_frame_names": [f["name"] for f in entry.get("frames", [])],
            "multiple_frames": entry.get("multiple_frames", False),
        }
        for entry in entries.values()
        if entry.get("frames")
    ]
    frame_examples.sort(key=lambda item: item["relative_path"])

    return {
        "schema_version": PATTERN_INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_folder": str(root),
        "entries": entries,
        "frame_examples": frame_examples,
    }


def write_pattern_index(path: str, index: Dict[str, Any]) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(json.dumps(index, indent=2, sort_keys=True))


def read_pattern_index(path: str) -> Optional[Dict[str, Any]]:
    path_obj = Path(path)
    if not path_obj.exists():
        return None
    try:
        data = json.loads(path_obj.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != PATTERN_INDEX_SCHEMA_VERSION:
        return None
    return data


def refresh_pattern_index(root_folder: str, index_path: str) -> Dict[str, Any]:
    """Read the index at *index_path*, refresh it against *root_folder*, write it back."""
    prior = read_pattern_index(index_path)
    new_index = build_pattern_index(root_folder, prior_index=prior)
    write_pattern_index(index_path, new_index)
    return new_index


# ---------------------------------------------------------------------------
# Layered search roots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchRoot:
    name: str
    kind: str  # "workspace" | "kumiki" | "dep"
    root_path: Path


def _kumiki_package_root() -> Optional[Path]:
    spec = importlib.util.find_spec("kumiki")
    if spec is None or spec.origin is None:
        return None
    return Path(spec.origin).resolve().parent


def _dep_package_root(dist_name: str) -> Optional[Path]:
    try:
        dist = importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return None
    # Prefer top_level.txt
    try:
        top_text = dist.read_text("top_level.txt") or ""
    except Exception:
        top_text = ""
    top_pkgs = [line.strip() for line in top_text.splitlines() if line.strip()]
    if not top_pkgs:
        top_pkgs = [dist_name.replace("-", "_")]
    for top_pkg in top_pkgs:
        spec = importlib.util.find_spec(top_pkg)
        if spec is None or spec.origin is None:
            continue
        return Path(spec.origin).resolve().parent
    return None


def _dep_requires_kumiki(dist_name: str) -> bool:
    if dist_name.lower() == "kumiki":
        return True
    try:
        dist = importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return False
    requires = dist.requires or []
    for req in requires:
        # ``req`` looks like ``"kumiki>=0.1; python_version >= '3.10'"`` etc.
        head = req.split(";", 1)[0].strip()
        # Strip extras: ``kumiki[extra]>=0.1`` → ``kumiki``
        name = head.split("[", 1)[0]
        for sep in ("=", "<", ">", "!", "~", " "):
            name = name.split(sep, 1)[0]
        if name.strip().lower() == "kumiki":
            return True
    return False


def _read_workspace_config(workspace_root: Path) -> Dict[str, Any]:
    config_path = workspace_root / ".kigumi" / "config.json"
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def discover_search_roots(
    workspace_root: str,
    *,
    extra_dependency_names: Optional[Iterable[str]] = None,
) -> List[SearchRoot]:
    """Return ordered search roots: workspace, kumiki, then declared deps.

    A declared dependency is included only if it is both (a) listed in the
    workspace's ``.kigumi/config.json`` (key ``kumiki_dependencies``) or
    passed via *extra_dependency_names*, **and** (b) its installed metadata's
    ``Requires-Dist`` lists ``kumiki``.
    """
    workspace_path = Path(workspace_root).resolve()
    roots: List[SearchRoot] = [
        SearchRoot(name="workspace", kind="workspace", root_path=workspace_path)
    ]

    kumiki_root = _kumiki_package_root()
    if kumiki_root is not None and kumiki_root != workspace_path:
        roots.append(SearchRoot(name="kumiki", kind="kumiki", root_path=kumiki_root))

    config = _read_workspace_config(workspace_path)
    declared = list(config.get("kumiki_dependencies") or [])
    if extra_dependency_names:
        for name in extra_dependency_names:
            if name not in declared:
                declared.append(name)

    for dep_name in declared:
        if dep_name.lower() == "kumiki":
            continue
        if not _dep_requires_kumiki(dep_name):
            continue
        dep_root = _dep_package_root(dep_name)
        if dep_root is None:
            continue
        roots.append(SearchRoot(name=dep_name, kind="dep", root_path=dep_root))

    return roots


# ---------------------------------------------------------------------------
# Per-root index resolution (bundled-or-build)
# ---------------------------------------------------------------------------


def load_or_build_pattern_index_for_root(root: SearchRoot) -> Dict[str, Any]:
    """Return a pattern index for *root*.

    For kumiki/dep roots, prefer a bundled ``_pattern_index.json`` if it
    exists and is valid; otherwise scan the root.  For workspace roots we
    always scan (the workspace cache is managed via
    :func:`refresh_pattern_index` separately).
    """
    if root.kind in ("kumiki", "dep"):
        bundled = root.root_path / PACKAGE_INDEX_FILENAME
        cached = read_pattern_index(str(bundled))
        if cached is not None:
            return cached
    return build_pattern_index(str(root.root_path))


def scan_all_roots(
    workspace_root: str,
    *,
    extra_dependency_names: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Aggregate per-root pattern indexes in search-path order.

    The aggregated payload preserves every entry; conflicts (same chosen frame
    name across roots) are not collapsed — the UI decides what to surface.
    """
    roots = discover_search_roots(
        workspace_root, extra_dependency_names=extra_dependency_names
    )
    per_root: List[Dict[str, Any]] = []
    for root in roots:
        index = load_or_build_pattern_index_for_root(root)
        per_root.append({
            "name": root.name,
            "kind": root.kind,
            "root_path": str(root.root_path),
            "index": index,
        })
    return {
        "schema_version": PATTERN_INDEX_SCHEMA_VERSION,
        "workspace_root": str(Path(workspace_root).resolve()),
        "roots": per_root,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Multi-pattern grid: merge a pattern list into a single tiled Frame
# ──────────────────────────────────────────────────────────────────────────────

def _pattern_frame_xy_extent(frame: Any) -> "tuple[float, float, float, float]":
    """Return (min_x, min_y, max_x, max_y) of a frame's timbers without triangulating."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for ct in frame.cut_timbers:
        t = ct.timber
        bp = t.get_bottom_position_global()
        ld = t.get_length_direction_global()
        wd = t.get_width_direction_global()
        hd = t.get_height_direction_global()
        length = float(t.length)
        w = float(t.get_perfect_size()[0])
        h = float(t.get_perfect_size()[1])
        for sl in (0.0, length):
            for sw in (-w / 2, w / 2):
                for sh in (-h / 2, h / 2):
                    x = float(bp[0] + ld[0] * sl + wd[0] * sw + hd[0] * sh)
                    y = float(bp[1] + ld[1] * sl + wd[1] * sw + hd[1] * sh)
                    if x < min_x: min_x = x
                    if x > max_x: max_x = x
                    if y < min_y: min_y = y
                    if y > max_y: max_y = y
    if min_x == float("inf"):
        return (-0.5, -0.5, 0.5, 0.5)
    return (min_x, min_y, max_x, max_y)


def _pattern_grid_offsets(
    extents: "list[tuple[float, float, float, float]]",
    padding: float = 0.5,
) -> "list[tuple[float, float]]":
    """Return (dx, dy) per pattern to tile frames in a square-ish grid at origin.

    Each frame is centered within its grid cell; the whole grid is centered at (0, 0).
    """
    N = len(extents)
    cols = math.ceil(math.sqrt(N))
    rows = math.ceil(N / cols)

    widths  = [ex - wx for wx, wy, ex, ey in extents]
    heights = [ey - wy for wx, wy, ex, ey in extents]
    cx_list = [(wx + ex) / 2 for wx, wy, ex, ey in extents]
    cy_list = [(wy + ey) / 2 for wx, wy, ex, ey in extents]

    col_widths  = [0.0] * cols
    row_heights = [0.0] * rows
    for i in range(N):
        col_widths[i % cols]   = max(col_widths[i % cols],   widths[i])
        row_heights[i // cols] = max(row_heights[i // cols], heights[i])

    col_starts = [0.0] * cols
    for c in range(1, cols):
        col_starts[c] = col_starts[c - 1] + col_widths[c - 1] + padding

    row_starts = [0.0] * rows
    for r in range(1, rows):
        row_starts[r] = row_starts[r - 1] + row_heights[r - 1] + padding

    total_w = col_starts[-1] + col_widths[-1]
    total_h = row_starts[-1] + row_heights[-1]

    offsets = []
    for i in range(N):
        cell_cx = col_starts[i % cols]   + col_widths[i % cols]   / 2 - total_w / 2
        cell_cy = row_starts[i // cols]  + row_heights[i // cols] / 2 - total_h / 2
        offsets.append((cell_cx - cx_list[i], cell_cy - cy_list[i]))
    return offsets


def _translate_frame(frame: Any, dx: float, dy: float) -> Any:
    """Return a new Frame with every timber, accessory, footprint, and joint shifted by (dx, dy, 0).

    Cuts are stored in LOCAL timber coordinates so they follow the timber automatically.
    We maintain an old_cut → new_cut identity map so that source_joints.cuttings
    references are rewritten to point at the new cut objects — serialize_layers uses
    identity (`is`) checks to match joints to their timbers in the frame.
    """
    from .rule import Transform, create_v2, create_v3
    from .timber import CutTimber, Frame
    from .footprint import Footprint

    offset = create_v3(scalar(dx), scalar(dy), scalar(0))

    cut_map: Dict[int, Any] = {}  # id(old_cut) → new_cut

    new_cut_timbers = []
    for ct in frame.cut_timbers:
        t = ct.timber
        new_pos = t.get_bottom_position_global() + offset
        new_timber = replace(t, transform=Transform(position=new_pos, orientation=t.orientation))
        new_cuts = []
        for cut in ct.cuts:
            new_cut = replace(cut, timber=new_timber)
            cut_map[id(cut)] = new_cut
            new_cuts.append(new_cut)
        new_cut_timbers.append(CutTimber(timber=new_timber, cuts=new_cuts))

    new_accessories: List[Any] = []
    for acc in (frame.accessories or []):
        if hasattr(acc, "transform"):
            new_pos_acc = acc.transform.position + offset
            new_accessories.append(replace(acc, transform=Transform(position=new_pos_acc, orientation=acc.transform.orientation)))
        else:
            new_accessories.append(acc)

    new_footprints: List[Any] = []
    for fp in (getattr(frame, "footprints", None) or []):
        new_corners = tuple(create_v2(c[0] + scalar(dx), c[1] + scalar(dy)) for c in fp.corners)
        new_footprints.append(Footprint(corners=new_corners))

    # Rewrite source_joints so their cuttings dict uses the new cut objects,
    # preserving the identity relationship that serialize_layers depends on.
    new_source_joints: List[Any] = []
    for joint in (getattr(frame, "source_joints", None) or []):
        old_cuttings = getattr(joint, "cuttings", {})
        new_cuttings = {name: cut_map.get(id(cut), cut) for name, cut in old_cuttings.items()}
        new_source_joints.append(replace(joint, cuttings=new_cuttings))

    return Frame(
        cut_timbers=new_cut_timbers,
        accessories=new_accessories,
        footprints=new_footprints,
        source_joints=new_source_joints if new_source_joints else None,
    )


def build_pattern_grid_frame(pattern_list: List[Any], padding: float = 0.5) -> Any:
    """Render all patterns and merge into one Frame arranged in a square-ish grid at the origin.

    Each pattern is rendered at origin=(0,0,0). Its XY footprint is computed from
    timber bounding boxes, and each frame is then translated to its grid cell by
    rebuilding timbers and accessories at their new positions (rather than post-hoc
    vertex manipulation). The result is a single Frame that passes through the normal
    build_real_geometry path, so accessories, joints, and fallback geometry all work.
    """
    from .rule import create_v3
    from .timber import Frame

    if not pattern_list:
        raise ValueError("Pattern list is empty")

    origin = create_v3(scalar(0), scalar(0), scalar(0))

    frames: List[Any] = []
    for p in pattern_list:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = p.lambda_(origin)
            if hasattr(result, "cut_timbers") and hasattr(result, "accessories"):
                frames.append(result)
            else:
                print(f"[grid] skipping pattern '{getattr(p, 'name', '?')}': lambda returned {type(result).__name__}, expected Frame", file=sys.stderr)
        except Exception as exc:
            print(f"[grid] skipping pattern '{getattr(p, 'name', '?')}': {exc}", file=sys.stderr)

    if not frames:
        raise ValueError("No patterns produced a renderable Frame")

    extents = []
    for f in frames:
        try:
            extents.append(_pattern_frame_xy_extent(f))
        except Exception:
            extents.append((-0.5, -0.5, 0.5, 0.5))

    offsets = _pattern_grid_offsets(extents, padding=padding)

    all_cut_timbers: List[Any] = []
    all_accessories: List[Any] = []
    all_footprints: List[Any] = []
    all_source_joints: List[Any] = []
    for f, (dx, dy) in zip(frames, offsets):
        translated = _translate_frame(f, dx, dy)
        all_cut_timbers.extend(translated.cut_timbers)
        all_accessories.extend(translated.accessories or [])
        all_footprints.extend(getattr(translated, "footprints", None) or [])
        all_source_joints.extend(getattr(translated, "source_joints", None) or [])

    return Frame(
        cut_timbers=all_cut_timbers,
        accessories=all_accessories,
        footprints=all_footprints,
        source_joints=all_source_joints if all_source_joints else None,
    )
