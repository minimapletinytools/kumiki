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

The generated nav is split into three groups, in this order: "Core" (the
non-joint modules users actually author designs against day to day), "Joints"
(all joint-cutting modules, broken out as their own top-level group since
there are so many of them), and "Supporting Reference" (lower-level/
internal-ish modules, looked up far less often) -- rather than one flat
alphabetical list. Modules not explicitly classified below fall back into
Supporting Reference automatically (with a Title Case guess at a display
name) so a newly-added top-level import in kumiki/__init__.py still gets a
page instead of being silently dropped.
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

# Non-joint modules users actually author designs against day to day -- listed first, under
# "Core". Ordered deliberately (not alphabetically): the rough order a design gets built in.
CORE_ORDER = ["footprint", "timber", "construction", "measuring", "rule"]

# joints.workshop.* always get their own top-level "Joints" group (right after Core, before
# Supporting Reference), with the "workshop" path segment (an implementation detail -- see
# kumiki/joints/workshop/) dropped from the nav. Ordered with the most commonly reached-for
# joints first.
JOINTS_ORDER = [
    "basic_joints",
    "mortise_and_tenon_joints",
    "butt_joints",
    "corner_joints",
    "cross_joints",
    "splice_joints",
    "board_joints",
    "multi_butt_joints",
    "compound_joints",
    "free_joints",
    "decorative_joints",
    "shavings",
]

# Lower-level or rarely-looked-up-directly modules -- listed after Core, under "Supporting
# Reference". Anything from kumiki/__init__.py not mentioned here or above still gets a page
# (appended here automatically), just with a guessed display name.
SUPPORTING_ORDER = ["cutcsg", "patternbook", "librarian", "triangles", "blueprint"]

DISPLAY_NAMES = {
    "cutcsg": "CutCSG",
    # "Pattern Book" (no suffix) is docs/patternbook.md's own top-level nav entry -- this is
    # the patternbook.py *module*'s API reference page, kept distinguishable from that.
    "patternbook": "Pattern Book (API)",
    "mortise_and_tenon_joints": "Mortise and Tenon Joints",
    "multi_butt_joints": "Multi-Butt Joints",
}


def _display_name(module_leaf: str) -> str:
    return DISPLAY_NAMES.get(module_leaf, module_leaf.replace("_", " ").title())


def _locally_defined_public_names(dotted_module: str) -> list[str]:
    """Names of top-level classes, functions, and constant assignments actually DEFINED in
    this module's own source -- as opposed to merely imported into it (e.g. via
    `from .x import *`) and thereby re-exported through its flat namespace.

    Needed because griffe's `Object.is_public` doesn't (yet -- see its own docstring/TODO)
    treat wildcard-imported names as non-public, so without an explicit `members:` list,
    mkdocstrings would also render everything each module's own `from .x import *`
    statements pull in onto ITS reference page (e.g. kumiki/timber.py's page would also
    list every name kumiki/rule.py's `from .rule import *` brings into scope there).
    Explicit `from .x import a, b` imports are already correctly excluded by mkdocstrings'
    `filters: public` option; this only needs to handle the wildcard case.

    Returns [] if the module file can't be found (mkdocstrings then falls back to its own
    default member selection).
    """
    module_path = (REPO_ROOT / "kumiki" / Path(*dotted_module.split("."))).with_suffix(".py")
    if not module_path.exists():
        return []
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(
                target.id for target in node.targets
                if isinstance(target, ast.Name) and not target.id.startswith("_")
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if not node.target.id.startswith("_"):
                names.append(node.target.id)
    return names


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


def _write_page(dotted_module: str, only_members: list[str] | None) -> str:
    """Write the mkdocstrings stub page for one module; return its doc path
    (relative to REFERENCE_ROOT, posix-style) for use as the nav link target."""
    parts = tuple(dotted_module.split("."))
    doc_path = REFERENCE_ROOT / Path(*parts).with_suffix(".md")

    full_ident = f"kumiki.{dotted_module}"
    members = only_members if only_members is not None else _locally_defined_public_names(dotted_module)
    example_name = members[0] if members else parts[-1]

    with mkdocs_gen_files.open(doc_path, "w") as fd:
        fd.write(f"# `{full_ident}`\n\n")
        fd.write(NOTE_TEMPLATE.format(example=example_name) + "\n")
        fd.write(f"::: {full_ident}\n")
        if members:
            fd.write("    options:\n")
            fd.write("      members:\n")
            for name in members:
                fd.write(f"        - {name}\n")

    return doc_path.relative_to(REFERENCE_ROOT).as_posix()


imports_by_module = dict(_iter_public_imports())
joints_prefix = "joints.workshop."
joints_modules = {
    dotted[len(joints_prefix):]: dotted for dotted in imports_by_module if dotted.startswith(joints_prefix)
}
remaining = {
    dotted for dotted in imports_by_module if not dotted.startswith(joints_prefix)
} - set(CORE_ORDER) - set(SUPPORTING_ORDER)

nav = mkdocs_gen_files.Nav()

for module_leaf in CORE_ORDER:
    if module_leaf not in imports_by_module:
        continue  # kumiki/__init__.py no longer imports this -- skip rather than error
    link = _write_page(module_leaf, imports_by_module[module_leaf])
    nav["Core", _display_name(module_leaf)] = link

for joints_leaf in JOINTS_ORDER:
    if joints_leaf not in joints_modules:
        continue
    dotted = joints_modules.pop(joints_leaf)
    link = _write_page(dotted, imports_by_module[dotted])
    nav["Joints", _display_name(joints_leaf)] = link

# Any joints.workshop.* module not explicitly ordered above (a new joint type added since
# this script was last updated) still gets a page, appended rather than dropped.
for joints_leaf in sorted(joints_modules):
    dotted = joints_modules[joints_leaf]
    link = _write_page(dotted, imports_by_module[dotted])
    nav["Joints", _display_name(joints_leaf)] = link

for module_leaf in SUPPORTING_ORDER:
    if module_leaf not in imports_by_module:
        continue
    link = _write_page(module_leaf, imports_by_module[module_leaf])
    nav["Supporting Reference", _display_name(module_leaf)] = link

# Anything from kumiki/__init__.py not explicitly classified above (e.g. a brand-new
# top-level import) -- still gets a page, filed under Supporting Reference by default.
for dotted in sorted(remaining):
    link = _write_page(dotted, imports_by_module[dotted])
    nav["Supporting Reference", _display_name(dotted.split(".")[-1])] = link

with mkdocs_gen_files.open(REFERENCE_ROOT / "SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
