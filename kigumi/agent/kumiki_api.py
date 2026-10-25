"""What kumiki says about a name, for the agent's kumiki_api tool (agent/kumiki-api.js), as JSON:
its signature, docstring, and file and line; a class's fields and methods; a module's or class's
members; or close names when there is no such name.

    python kumiki_api.py NAME [--members] [--source]

NAME is as a frame file uses it after `from kumiki import *` ("create_axis_aligned_timber",
"Frame.from_joints"), or a module ("kumiki.construction").
"""

import contextlib
import dataclasses
import difflib
import importlib
import inspect
import io
import json
import re
import sys

MAX_DOC = 4000
MAX_SOURCE = 12000
MAX_MEMBERS = 200


def first_line(value):
    doc = inspect.getdoc(value) or ""
    return doc.strip().split("\n")[0][:160]


def resolve(name):
    """The object `name` names, and the names it could have meant if none."""
    import kumiki
    if name.startswith("kumiki"):
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            try:
                value = importlib.import_module(".".join(parts[:i]))
            except ImportError:
                continue
            for part in parts[i:]:
                value = getattr(value, part)
            return value, []
    exported = {key: getattr(kumiki, key) for key in dir(kumiki) if not key.startswith("_")}
    head, *rest = name.split(".")
    if head not in exported:
        return None, difflib.get_close_matches(head, exported, n=8, cutoff=0.5)
    value = exported[head]
    for part in rest:
        if not hasattr(value, part):
            members = [m for m in dir(value) if not m.startswith("_")]
            return None, [f"{head}.{m}" for m in difflib.get_close_matches(part, members, n=8, cutoff=0.5)]
        value = getattr(value, part)
    return value, []


def where(value):
    try:
        return f"{inspect.getsourcefile(value)}:{inspect.getsourcelines(value)[1]}"
    except (TypeError, OSError):
        return None


def signature(value):
    """`value`'s signature, kumiki's types by their plain names (Matrix, not kumiki.rule.Matrix)."""
    try:
        text = str(inspect.signature(value))
    except (TypeError, ValueError):
        return None
    return re.sub(r"\b(?:kumiki|typing)\.(?:\w+\.)*(\w+)", r"\1", text)


def members(value):
    named = [(key, getattr(value, key)) for key in dir(value) if not key.startswith("_")]
    if inspect.ismodule(value):
        # A module's own names, not everything it imported.
        named = [(key, member) for key, member in named if getattr(member, "__module__", value.__name__) == value.__name__]
    return [{"name": key, "kind": type(member).__name__, "summary": first_line(member)} for key, member in named][:MAX_MEMBERS]


def describe(name, with_members, with_source):
    value, suggestions = resolve(name)
    if value is None:
        return {"found": False, "name": name, "did_you_mean": suggestions}
    found = {"found": True, "name": name, "kind": "module" if inspect.ismodule(value) else type(value).__name__,
             "where": where(value)}
    if callable(value) and not inspect.ismodule(value):
        found["signature"] = signature(value)
    doc = inspect.getdoc(value)
    if doc:
        found["doc"] = doc[:MAX_DOC]
    if inspect.isclass(value):
        if dataclasses.is_dataclass(value):
            found["fields"] = [{"name": f.name, "type": str(f.type)} for f in dataclasses.fields(value)]
        found["methods"] = [{"name": key, "signature": signature(member), "summary": first_line(member)}
                            for key, member in inspect.getmembers(value, callable) if not key.startswith("_")][:MAX_MEMBERS]
        found["members_of"] = [m["name"] for m in members(value) if m["kind"] not in ("function", "method")][:50] or None
    if with_members or inspect.ismodule(value):
        found["members"] = members(value)
    if with_source:
        try:
            found["source"] = inspect.getsource(value)[:MAX_SOURCE]
        except (TypeError, OSError):
            found["source"] = None
    return {key: item for key, item in found.items() if item is not None}


if __name__ == "__main__":
    args = sys.argv[1:]
    name = next((arg for arg in args if not arg.startswith("--")), "")
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        try:
            result = describe(name, "--members" in args, "--source" in args)
        except Exception as error:
            result = {"found": False, "name": name, "error": f"{type(error).__name__}: {error}"}
    print(json.dumps(result))
