"""
Patternbook example patterns.
"""

from kumiki import *


def _make_short_post(center):
    return Frame(cut_timbers=[CutTimber(create_timber(length=feet(4), size=create_v2(inches(4), inches(4)), bottom_position=center, length_direction=create_v3(scalar(0), scalar(0), scalar(1)), width_direction=create_v3(scalar(1), scalar(0), scalar(0)), ticket="short_post"), cuts=[])], name="Short Post")

def _make_tall_post(center):
    return Frame(cut_timbers=[CutTimber(create_timber(length=feet(8), size=create_v2(inches(6), inches(6)), bottom_position=center, length_direction=create_v3(scalar(0), scalar(0), scalar(1)), width_direction=create_v3(scalar(1), scalar(0), scalar(0)), ticket="tall_post"), cuts=[])], name="Tall Post")

def _make_wide_post(center):
    return Frame(cut_timbers=[CutTimber(create_timber(length=feet(6), size=create_v2(inches(8), inches(8)), bottom_position=center, length_direction=create_v3(scalar(0), scalar(0), scalar(1)), width_direction=create_v3(scalar(1), scalar(0), scalar(0)), ticket="wide_post"), cuts=[])], name="Wide Post")

def _make_small_beam(center):
    return Frame(cut_timbers=[CutTimber(create_timber(length=feet(8), size=create_v2(inches(2), inches(4)), bottom_position=center, length_direction=create_v3(scalar(1), scalar(0), scalar(0)), width_direction=create_v3(scalar(0), scalar(1), scalar(0)), ticket="small_beam"), cuts=[])], name="Small Beam")

def _make_medium_beam(center):
    return Frame(cut_timbers=[CutTimber(create_timber(length=feet(10), size=create_v2(inches(4), inches(6)), bottom_position=center, length_direction=create_v3(scalar(1), scalar(0), scalar(0)), width_direction=create_v3(scalar(0), scalar(1), scalar(0)), ticket="medium_beam"), cuts=[])], name="Medium Beam")

def _make_large_beam(center):
    return Frame(cut_timbers=[CutTimber(create_timber(length=feet(12), size=create_v2(inches(6), inches(8)), bottom_position=center, length_direction=create_v3(scalar(1), scalar(0), scalar(0)), width_direction=create_v3(scalar(0), scalar(1), scalar(0)), ticket="large_beam"), cuts=[])], name="Large Beam")

def _make_small_box(center):
    size = inches(2)
    return RectangularPrism(size=create_v2(size, size), transform=Transform(position=center, orientation=Orientation.identity()), start_distance=-size / 2, end_distance=size / 2)

def _make_medium_box(center):
    size = inches(4)
    return RectangularPrism(size=create_v2(size, size), transform=Transform(position=center, orientation=Orientation.identity()), start_distance=-size / 2, end_distance=size / 2)

def _make_large_box(center):
    size = inches(6)
    return RectangularPrism(size=create_v2(size, size), transform=Transform(position=center, orientation=Orientation.identity()), start_distance=-size / 2, end_distance=size / 2)


@pattern("patternbook_examples/short_post", tags=["main", "poop"])
def short_post_pattern() -> Frame:
    return _make_short_post(create_v3(0, 0, 0))


@pattern("patternbook_examples/tall_post", tags=["poop"])
def tall_post_pattern() -> Frame:
    return _make_tall_post(create_v3(0, 0, 0))


@pattern("patternbook_examples/wide_post", tags=["poop"])
def wide_post_pattern() -> Frame:
    return _make_wide_post(create_v3(0, 0, 0))


@pattern("patternbook_examples/small_beam", tags=["poop"])
def small_beam_pattern() -> Frame:
    return _make_small_beam(create_v3(0, 0, 0))


@pattern("patternbook_examples/medium_beam", tags=["poop"])
def medium_beam_pattern() -> Frame:
    return _make_medium_beam(create_v3(0, 0, 0))


@pattern("patternbook_examples/large_beam", tags=["poop"])
def large_beam_pattern() -> Frame:
    return _make_large_beam(create_v3(0, 0, 0))


@pattern("patternbook_examples/small_box", tags=["poop"])
def small_box_pattern() -> CutCSG:
    return _make_small_box(create_v3(0, 0, 0))


@pattern("patternbook_examples/medium_box", tags=["poop"])
def medium_box_pattern() -> CutCSG:
    return _make_medium_box(create_v3(0, 0, 0))


@pattern("patternbook_examples/large_box", tags=["poop"])
def large_box_pattern() -> CutCSG:
    return _make_large_box(create_v3(0, 0, 0))
