"""Generate virtual API reference pages for kumiki's public modules.

Derives the module list directly from the `from .X import *` (and the single
explicit `from .librarian import Param`) statements in kumiki/__init__.py --
i.e. exactly what makes up kumiki's flattened public namespace reachable via
`from kumiki import *`. Emits one mkdocstrings stub page per module under
reference/, plus a literate-nav SUMMARY.md.

Deliberately does NOT walk the whole kumiki/ source tree: kumiki has many
internal-only modules (assembly.py, ticket.py, most of librarian.py,
timber_shavings.py, example_shavings.py, kigumi_at_home.py, librarian_cli.py,
joints/workshop/shavings/router_table.py, ...) that are not re-exported by
kumiki/__init__.py and must not get a public reference page. Because the
module list is derived from kumiki/__init__.py's own imports, this script
stays in sync automatically as that file changes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import mkdocs_gen_files

REPO_ROOT = Path(__file__).resolve().parent.parent
INIT_PY = REPO_ROOT / "kumiki" / "__init__.py"
REFERENCE_ROOT = Path("reference")

NOTE_TEMPLATE = (
    '!!! note "Flat import path"\n'
    "    `kumiki/__init__.py` re-exports everything on this page via "
    "`from kumiki import *`, so every name below is also available directly "
    "as `kumiki.{example}` -- you do not need to import from the submodule "
    "path shown in the heading above.\n"
)


def _first_public_symbol(dotted_module: str) -> str | None:
    """Name of the first top-level, non-underscore class/function defined in
    a module -- used only to give the "flat import path" note a real,
    correct example instead of (incorrectly) the module's own filename."""
    module_path = (REPO_ROOT / "kumiki" / Path(*dotted_module.split("."))).with_suffix(".py")
    if not module_path.exists():
        return None
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            return node.name
    return None


def _iter_public_imports():
    """Yield (dotted_module, only_members) pairs from kumiki/__init__.py.

    only_members is None for `from .x import *` (document the whole module),
    or a list of names for `from .x import a, b` (document just those
    members). Leading-underscore names are always skipped.
    """
    tree = ast.parse(INIT_PY.read_text(), filename=str(INIT_PY))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.module is None:
            continue  # only `from .something import ...` matters here
        if any(alias.name == "*" for alias in node.names):
            yield node.module, None
        else:
            names = [a.name for a in node.names if not a.name.startswith("_")]
            if names:
                yield node.module, names


nav = mkdocs_gen_files.Nav()

for dotted_module, only_members in sorted(_iter_public_imports(), key=lambda t: t[0]):
    parts = tuple(dotted_module.split("."))
    doc_path = REFERENCE_ROOT / Path(*parts).with_suffix(".md")
    nav[parts] = doc_path.relative_to(REFERENCE_ROOT).as_posix()

    full_ident = f"kumiki.{dotted_module}"
    example_name = only_members[0] if only_members else (_first_public_symbol(dotted_module) or parts[-1])

    with mkdocs_gen_files.open(doc_path, "w") as fd:
        fd.write(f"# `{full_ident}`\n\n")
        fd.write(NOTE_TEMPLATE.format(example=example_name) + "\n")
        fd.write(f"::: {full_ident}\n")
        if only_members:
            fd.write("    options:\n")
            fd.write("      members:\n")
            for name in only_members:
                fd.write(f"        - {name}\n")

with mkdocs_gen_files.open(REFERENCE_ROOT / "SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
