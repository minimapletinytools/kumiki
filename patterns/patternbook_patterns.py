"""
Patternbook example patterns.
"""

from kumiki import *
from kumiki.patternbook import Pattern


def _make_short_post(center):
    return Frame(cut_timbers=[CutTimber(timber_from_directions(length=feet(4), size=create_v2(inches(4), inches(4)), bottom_position=center, length_direction=create_v3(Integer(0), Integer(0), Integer(1)), width_direction=create_v3(Integer(1), Integer(0), Integer(0)), ticket="short_post"), cuts=[])], name="Short Post")

def _make_tall_post(center):
    return Frame(cut_timbers=[CutTimber(timber_from_directions(length=feet(8), size=create_v2(inches(6), inches(6)), bottom_position=center, length_direction=create_v3(Integer(0), Integer(0), Integer(1)), width_direction=create_v3(Integer(1), Integer(0), Integer(0)), ticket="tall_post"), cuts=[])], name="Tall Post")

def _make_wide_post(center):
    return Frame(cut_timbers=[CutTimber(timber_from_directions(length=feet(6), size=create_v2(inches(8), inches(8)), bottom_position=center, length_direction=create_v3(Integer(0), Integer(0), Integer(1)), width_direction=create_v3(Integer(1), Integer(0), Integer(0)), ticket="wide_post"), cuts=[])], name="Wide Post")

def _make_small_beam(center):
    return Frame(cut_timbers=[CutTimber(timber_from_directions(length=feet(8), size=create_v2(inches(2), inches(4)), bottom_position=center, length_direction=create_v3(Integer(1), Integer(0), Integer(0)), width_direction=create_v3(Integer(0), Integer(1), Integer(0)), ticket="small_beam"), cuts=[])], name="Small Beam")

def _make_medium_beam(center):
    return Frame(cut_timbers=[CutTimber(timber_from_directions(length=feet(10), size=create_v2(inches(4), inches(6)), bottom_position=center, length_direction=create_v3(Integer(1), Integer(0), Integer(0)), width_direction=create_v3(Integer(0), Integer(1), Integer(0)), ticket="medium_beam"), cuts=[])], name="Medium Beam")

def _make_large_beam(center):
    return Frame(cut_timbers=[CutTimber(timber_from_directions(length=feet(12), size=create_v2(inches(6), inches(8)), bottom_position=center, length_direction=create_v3(Integer(1), Integer(0), Integer(0)), width_direction=create_v3(Integer(0), Integer(1), Integer(0)), ticket="large_beam"), cuts=[])], name="Large Beam")

def _make_small_box(center):
    size = inches(2)
    return RectangularPrism(size=create_v2(size, size), transform=Transform(position=center, orientation=Orientation.identity()), start_distance=-size / 2, end_distance=size / 2)

def _make_medium_box(center):
    size = inches(4)
    return RectangularPrism(size=create_v2(size, size), transform=Transform(position=center, orientation=Orientation.identity()), start_distance=-size / 2, end_distance=size / 2)

def _make_large_box(center):
    size = inches(6)
    return RectangularPrism(size=create_v2(size, size), transform=Transform(position=center, orientation=Orientation.identity()), start_distance=-size / 2, end_distance=size / 2)


patterns = [
    Pattern(path="patternbook_examples/short_post", lambda_=_make_short_post, pattern_type='frame', tags=['main', 'poop']),
    Pattern(path="patternbook_examples/tall_post", lambda_=_make_tall_post, pattern_type='frame', tags=['poop']),
    Pattern(path="patternbook_examples/wide_post", lambda_=_make_wide_post, pattern_type='frame', tags=['poop']),
    Pattern(path="patternbook_examples/small_beam", lambda_=_make_small_beam, pattern_type='frame', tags=['poop']),
    Pattern(path="patternbook_examples/medium_beam", lambda_=_make_medium_beam, pattern_type='frame', tags=['poop']),
    Pattern(path="patternbook_examples/large_beam", lambda_=_make_large_beam, pattern_type='frame', tags=['poop']),
    Pattern(path="patternbook_examples/small_box", lambda_=_make_small_box, pattern_type='csg', tags=['poop']),
    Pattern(path="patternbook_examples/medium_box", lambda_=_make_medium_box, pattern_type='csg', tags=['poop']),
    Pattern(path="patternbook_examples/large_box", lambda_=_make_large_box, pattern_type='csg', tags=['poop']),
]
