"""Prepare STL placement edits without overwriting changed or ambiguous source."""
import ast
import hashlib
from pathlib import Path


def _offset(text, line, column):
    lines = text.splitlines(keepends=True)
    return sum(len(part) for part in lines[:line - 1]) + len(lines[line - 1].encode()[:column].decode())


def prepare_edit(timber, placement, project_root, source_count=1):
    from kumiki.stl import STLPlacement
    configured = STLPlacement(**placement).to_dict()
    configuration = 'placement=' + repr(configured)
    source = timber.source
    if source is None or source_count != 1:
        raise ValueError('The creating call is missing or creates more than one timber. Update it manually or ask the agent.')
    path = Path(source.path).resolve()
    if not path.is_relative_to(Path(project_root).resolve()):
        raise ValueError('The creating call is outside this project. Update it manually or ask the agent.')
    with path.open(encoding="utf-8", newline="") as file:
        text = file.read()
    if hashlib.sha256(text.encode()).hexdigest() != source.digest:
        raise ValueError('The source changed since this frame was built. Refresh the frame before updating it.')
    matches = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Call)
               and node.lineno == source.line and ast.get_source_segment(text, node) == source.call]
    if len(matches) != 1:
        raise ValueError('Could not identify one creating call. Update it manually or ask the agent.')
    call = matches[0]
    if any(keyword.arg is None for keyword in call.keywords):
        raise ValueError('The creating call uses **kwargs. Update placement manually or ask the agent.')
    existing = next((keyword for keyword in call.keywords if keyword.arg == 'placement'), None)
    if existing:
        node = existing.value
        start = _offset(text, node.lineno, node.col_offset)
        end = _offset(text, node.end_lineno, node.end_col_offset)
        updated = text[:start] + repr(configured) + text[end:]
    else:
        # Insert after the last argument, before any trailing comma/comment.
        last = max([*call.args, *[k.value for k in call.keywords]], key=lambda n: (n.end_lineno, n.end_col_offset))
        end = _offset(text, last.end_lineno, last.end_col_offset)
        updated = text[:end] + ', ' + configuration + text[end:]
    ast.parse(updated)
    return {'path': str(path), 'expected': text, 'updated': updated, 'configuration': configuration}
