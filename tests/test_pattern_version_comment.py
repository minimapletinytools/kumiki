"""Every pattern file names the last kumiki version it ran correctly on."""

import re
from pathlib import Path

import pytest

PATTERNS = Path(__file__).resolve().parent.parent / "patterns"
VERSION_COMMENT = re.compile(r"# Last checked on kumiki \d+\.\d+\.\d+\n")


@pytest.mark.parametrize("path", sorted(p for p in PATTERNS.rglob("*.py") if "__pycache__" not in p.parts),
                         ids=lambda p: str(p.relative_to(PATTERNS)))
def test_first_line_names_a_kumiki_version(path):
    first_line = path.read_text(encoding="utf-8").splitlines(keepends=True)[0]
    assert VERSION_COMMENT.fullmatch(first_line), f"{path.name} starts with {first_line!r}"
