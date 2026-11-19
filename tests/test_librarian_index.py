"""Tests for the pattern-index build/refresh logic and search-root discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kumiki.librarian import (
    PATTERN_INDEX_SCHEMA_VERSION,
    SearchRoot,
    build_pattern_index,
    discover_search_roots,
    read_pattern_index,
    refresh_pattern_index,
    write_pattern_index,
)


FRAME_SOURCE = """
from kumiki import *

__title__ = "Frame A"


@frame
def build_frame(k: Kiwari) -> Frame:
    return Frame.from_joints([])
"""

PATTERN_LIST_SOURCE = """
from kumiki import Frame, pattern, pattern_folders

__title__ = {"en": "Things", "ja": "もの"}

pattern_folders({"things": {"en": "All things", "ja": "すべてのもの"}})


@pattern("things/a_thing", name={"en": "A thing", "ja": "ひとつのもの"}, tags=["main"])
def a_thing() -> Frame:
    return Frame(cut_timbers=[], name="Thing")
"""

EXPLODING_FRAME_SOURCE = """
from kumiki import *

raise RuntimeError("this module must not be imported during scan")


@frame
def build_frame(k: Kiwari) -> Frame:
    return Frame.from_joints([])
"""


@pytest.fixture()
def sample_root(tmp_path: Path) -> Path:
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "a.py").write_text(FRAME_SOURCE)
    (tmp_path / "frames" / "exploding.py").write_text(EXPLODING_FRAME_SOURCE)
    (tmp_path / "patterns").mkdir()
    (tmp_path / "patterns" / "b.py").write_text(PATTERN_LIST_SOURCE)
    (tmp_path / "unrelated.py").write_text("x = 1\n")
    return tmp_path


def test_build_pattern_index_shape(sample_root: Path):
    index = build_pattern_index(str(sample_root))
    assert index["schema_version"] == PATTERN_INDEX_SCHEMA_VERSION
    entries = index["entries"]

    # Frame files appear, including the exploding one (we never imported it).
    assert "frames/a.py" in entries
    assert "frames/exploding.py" in entries
    # Pattern list file appears.
    assert "patterns/b.py" in entries
    # Unrelated file is omitted.
    assert "unrelated.py" not in entries

    frame_entry = entries["frames/a.py"]
    assert frame_entry["chosen_frame_name"] == "build_frame"
    assert frame_entry["chosen_frame_kind"] == "function"
    assert frame_entry["sha256"]
    assert frame_entry["patternbook"] is None


def test_frame_files_never_imported_during_build(sample_root: Path):
    # If the build imported frames/exploding.py the RuntimeError at module
    # scope would propagate.  Building must succeed.
    index = build_pattern_index(str(sample_root))
    exploding = index["entries"]["frames/exploding.py"]
    assert exploding["chosen_frame_name"] == "build_frame"


def test_refresh_reuses_unchanged_entries(sample_root: Path, tmp_path: Path):
    index_path = tmp_path / "pattern_index.json"
    first = refresh_pattern_index(str(sample_root), str(index_path))
    first_pb_entry = first["entries"]["patterns/b.py"]

    # Touch only one file.
    (sample_root / "frames" / "a.py").write_text(FRAME_SOURCE + "\n# changed\n")
    second = refresh_pattern_index(str(sample_root), str(index_path))

    # Pattern list entry's sha unchanged → reused identity.
    second_pb_entry = second["entries"]["patterns/b.py"]
    assert second_pb_entry["sha256"] == first_pb_entry["sha256"]

    # Frame entry sha must differ.
    assert (
        second["entries"]["frames/a.py"]["sha256"]
        != first["entries"]["frames/a.py"]["sha256"]
    )


def test_read_write_round_trip(sample_root: Path, tmp_path: Path):
    index = build_pattern_index(str(sample_root))
    out = tmp_path / "out.json"
    write_pattern_index(str(out), index)
    loaded = read_pattern_index(str(out))
    assert loaded is not None
    assert loaded["entries"].keys() == index["entries"].keys()


def test_read_pattern_index_missing_returns_none(tmp_path: Path):
    assert read_pattern_index(str(tmp_path / "nope.json")) is None


def test_read_pattern_index_wrong_schema(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 999, "entries": {}}))
    assert read_pattern_index(str(bad)) is None


# ---------------------------------------------------------------------------
# Search roots
# ---------------------------------------------------------------------------


def test_discover_search_roots_workspace_first(tmp_path: Path):
    roots = discover_search_roots(str(tmp_path))
    assert roots[0].kind == "workspace"
    assert roots[0].root_path == tmp_path.resolve()
    # kumiki package should be discovered (we are running inside it).
    assert any(r.kind == "kumiki" for r in roots)


def test_unlisted_dep_is_excluded(tmp_path: Path):
    # No config, no extra → no dep roots.
    roots = discover_search_roots(str(tmp_path))
    assert not any(r.kind == "dep" for r in roots)


def test_listed_dep_without_requires_kumiki_is_excluded(tmp_path: Path):
    # sympy is installed but does not Require-Dist kumiki.
    config_dir = tmp_path / ".kigumi"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"kumiki_dependencies": ["sympy"]})
    )
    roots = discover_search_roots(str(tmp_path))
    assert not any(r.name == "sympy" for r in roots)


def test_extra_dependency_names_still_gated(tmp_path: Path):
    roots = discover_search_roots(
        str(tmp_path), extra_dependency_names=["sympy"]
    )
    assert not any(r.name == "sympy" for r in roots)


def test_index_carries_titles_and_names(sample_root: Path):
    index = build_pattern_index(str(sample_root))
    book = index["entries"]["patterns/b.py"]

    assert book["title"] == {"en": "Things", "ja": "もの"}
    assert book["patternbook"]["folder_names"] == {"things": {"en": "All things", "ja": "すべてのもの"}}
    assert book["patternbook"]["patterns"][0]["names"] == {"en": "A thing", "ja": "ひとつのもの"}
    frame = next(item for item in index["frame_examples"] if item["relative_path"] == "frames/a.py")
    assert frame["title"] == {"en": "Frame A"}


def test_scan_index_carries_titles_and_names(sample_root: Path):
    from kumiki.librarian import scan_library_index

    index = scan_library_index(str(sample_root))
    book = index["patternbooks"][0]

    assert (book["title"], book["folder_names"]["things"]["en"]) == ({"en": "Things", "ja": "もの"}, "All things")
    assert book["patterns"][0]["names"]["ja"] == "ひとつのもの"
    assert next(f for f in index["frame_examples"] if f["relative_path"] == "frames/a.py")["title"] == {"en": "Frame A"}


def test_a_title_that_is_not_literal_is_a_warning(tmp_path: Path):
    from kumiki.librarian import analyze_source

    info = analyze_source("NAME = 'x'\n__title__ = NAME\n", "f.py")

    assert info.title is None
    assert "__title__ is not used" in info.warnings[0]
