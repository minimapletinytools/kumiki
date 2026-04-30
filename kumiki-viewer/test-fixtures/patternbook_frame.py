"""Test fixture: a module that exports a patternbook with two patterns."""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from kumiki.construction import create_timber
from kumiki.rule import create_v2, create_v3, mm
from kumiki.timber import Frame, CutTimber
from kumiki.patternbook import PatternBook, PatternMetadata, make_pattern_from_frame


def _build_small_frame():
    timber = create_timber(
        bottom_position=create_v3(mm(0), mm(0), mm(0)),
        length=mm(500),
        size=create_v2(mm(80), mm(80)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket="small_post",
    )
    return Frame(name="Small Pattern", cut_timbers=(CutTimber(timber=timber, cuts=()),), accessories=())


def _build_tall_frame():
    timber = create_timber(
        bottom_position=create_v3(mm(0), mm(0), mm(0)),
        length=mm(2000),
        size=create_v2(mm(120), mm(120)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        ticket="tall_post",
    )
    return Frame(name="Tall Pattern", cut_timbers=(CutTimber(timber=timber, cuts=()),), accessories=())


patternbook = PatternBook(patterns=[
    (PatternMetadata("small_post_pattern", ["test_group"]), make_pattern_from_frame(_build_small_frame)),
    (PatternMetadata("tall_post_pattern", ["test_group"]), make_pattern_from_frame(_build_tall_frame)),
])
