"""
Pure-AST static analyzer for kumiki source files.

Identifies module-level entries that produce a ``Frame`` or ``PatternBook`` —
either by typed annotation, by known constructor call, or by function return
annotation.  Detection is done without importing the file.  Recognition is
**type-based, not name-based**: the local identifier is irrelevant.

The analyzer resolves identifiers through the file's ``import`` statements so
aliased imports (``from kumiki import Frame as F``) are handled correctly.

Frames and patternbooks are only detected when they refer to kumiki's canonical
``Frame``/``PatternBook`` symbols.  We accept any kumiki submodule path
(``kumiki``, ``kumiki.timber``, ``kumiki.patternbook``, etc.) as a valid
provider — kumiki re-exports both at the top level.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


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
