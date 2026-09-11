from __future__ import annotations

from pathlib import Path

from kumiki.librarian import _should_skip_dir


def test_default_skip_dirs_include_test_fixtures() -> None:
    assert _should_skip_dir("test-fixtures", Path("/tmp/workspace/test-fixtures")) is True
    assert _should_skip_dir("test_fixtures", Path("/tmp/workspace/test_fixtures")) is True
