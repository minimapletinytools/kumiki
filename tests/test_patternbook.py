"""
Tests for the PatternBook module
"""

import pytest
from sympy import Integer, Rational
from kumiki.rule import create_v3, create_v2, inches, Transform, Orientation
from kumiki.timber import timber_from_directions, Frame, CutTimber, CSGAccessory
from kumiki.cutcsg import RectangularPrism
from kumiki.patternbook import PatternMetadata, PatternBook, PatternLambda


def test_pattern_metadata_creation():
    """Test creating PatternMetadata objects."""
    # Basic metadata
    metadata1 = PatternMetadata(
        pattern_name="test_pattern",
        pattern_type="frame"
    )
    assert metadata1.pattern_name == "test_pattern"
    assert metadata1.pattern_group_names == []
    assert metadata1.pattern_type == "frame"
    
    # Metadata with single group
    metadata2 = PatternMetadata(
        pattern_name="test_pattern2",
        pattern_group_names=["test_group"],
        pattern_type="csg"
    )
    assert metadata2.pattern_group_names == ["test_group"]
    assert metadata2.pattern_type == "csg"
    
    # Metadata with multiple groups
    metadata3 = PatternMetadata(
        pattern_name="test_pattern3",
        pattern_group_names=["group_a", "group_b"],
        pattern_type="frame"
    )
    assert metadata3.pattern_group_names == ["group_a", "group_b"]
    assert metadata3.pattern_type == "frame"


def test_pattern_metadata_invalid_type():
    """Test that invalid pattern types raise ValueError."""
    with pytest.raises(ValueError, match="pattern_type must be"):
        PatternMetadata(
            pattern_name="test",
            pattern_type="invalid"  # type: ignore
        )


def test_pattern_book_creation_with_frames():
    """Test creating a PatternBook with frame patterns."""
    # Create a simple pattern function
    def make_simple_frame(center):
        timber = timber_from_directions(
            length=inches(24),
            size=create_v2(inches(2), inches(4)),
            bottom_position=center,
            length_direction=create_v3(1, 0, 0),  # East
            width_direction=create_v3(0, 1, 0),   # North
            ticket="test_timber"
        )
        cut_timber = CutTimber(timber=timber, cuts=[])
        return Frame(cut_timbers=[cut_timber], name="simple_frame")
    
    # Create pattern book
    metadata = PatternMetadata(pattern_name="simple", pattern_type="frame")
    book = PatternBook(patterns=[(metadata, make_simple_frame)])
    
    assert len(book.patterns) == 1
    assert book.list_patterns() == ["simple"]


def test_pattern_book_creation_with_csg():
    """Test creating a PatternBook with CSG patterns."""
    # Create a simple CSG pattern function
    def make_box(center):
        size = inches(2)
        return RectangularPrism(
            size=create_v2(size, size),
            transform=Transform(position=center, orientation=Orientation.identity()),
            start_distance=-size / Integer(2),
            end_distance=size / Integer(2)
        )
    
    # Create pattern book
    metadata = PatternMetadata(pattern_name="box", pattern_type="csg")
    book = PatternBook(patterns=[(metadata, make_box)])
    
    assert len(book.patterns) == 1
    assert book.list_patterns() == ["box"]


def test_pattern_book_duplicate_names():
    """Test that duplicate pattern names raise ValueError."""
    def make_frame1(center):
        timber = timber_from_directions(
            length=inches(24),
            size=create_v2(inches(2), inches(4)),
            bottom_position=center,
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0)
        )
        return Frame(cut_timbers=[CutTimber(timber=timber, cuts=[])])
    
    def make_frame2(center):
        return make_frame1(center)
    
    metadata1 = PatternMetadata(pattern_name="duplicate", pattern_type="frame")
    metadata2 = PatternMetadata(pattern_name="duplicate", pattern_type="frame")
    
    with pytest.raises(ValueError, match="Duplicate pattern names"):
        PatternBook(patterns=[(metadata1, make_frame1), (metadata2, make_frame2)])


def test_raise_pattern():
    """Test raising a single pattern."""
    def make_frame(center):
        timber = timber_from_directions(
            length=inches(24),
            size=create_v2(inches(2), inches(4)),
            bottom_position=center,
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="test_timber"
        )
        return Frame(cut_timbers=[CutTimber(timber=timber, cuts=[])])
    
    metadata = PatternMetadata(pattern_name="test", pattern_type="frame")
    book = PatternBook(patterns=[(metadata, make_frame)])
    
    # Raise at default position (origin)
    frame1 = book.raise_pattern("test")
    assert isinstance(frame1, Frame)
    assert len(frame1.cut_timbers) == 1
    
    # Raise at specific position
    center = create_v3(inches(10), inches(20), inches(30))
    frame2 = book.raise_pattern("test", center=center)
    assert isinstance(frame2, Frame)
    # Check that the timber's bottom position matches the center we provided
    assert frame2.cut_timbers[0].timber.transform.position == center


def test_raise_pattern_not_found():
    """Test that raising a non-existent pattern raises ValueError."""
    book = PatternBook(patterns=[])
    
    with pytest.raises(ValueError, match="Pattern 'nonexistent' not found"):
        book.raise_pattern("nonexistent")


def test_raise_pattern_group_frames():
    """Test raising a group of frame patterns."""
    def make_frame(name):
        def _make(center):
            timber = timber_from_directions(
                length=inches(24),
                size=create_v2(inches(2), inches(4)),
                bottom_position=center,
                length_direction=create_v3(1, 0, 0),
                width_direction=create_v3(0, 1, 0),
                ticket=name
            )
            return Frame(cut_timbers=[CutTimber(timber=timber, cuts=[])])
        return _make
    
    # Create pattern book with grouped patterns
    patterns = [
        (PatternMetadata("frame1", ["group_a"], "frame"), make_frame("timber1")),
        (PatternMetadata("frame2", ["group_a"], "frame"), make_frame("timber2")),
        (PatternMetadata("frame3", ["group_a"], "frame"), make_frame("timber3")),
    ]
    book = PatternBook(patterns=patterns)
    
    # Raise the group
    separation = inches(48)
    combined_frame = book.raise_pattern_group("group_a", separation)
    
    assert isinstance(combined_frame, Frame)
    assert len(combined_frame.cut_timbers) == 3
    assert combined_frame.name == "group_a_combined"
    
    # Check positions are separated correctly
    pos0 = combined_frame.cut_timbers[0].timber.transform.position
    pos1 = combined_frame.cut_timbers[1].timber.transform.position
    pos2 = combined_frame.cut_timbers[2].timber.transform.position
    
    assert (pos1 - pos0)[0] == separation  # X offset
    assert (pos2 - pos1)[0] == separation  # X offset


def test_raise_pattern_group_csg():
    """Test raising a group of CSG patterns."""
    def make_box(name):
        def _make(center):
            size = inches(2)
            return RectangularPrism(
                size=create_v2(size, size),
                transform=Transform(position=center, orientation=Orientation.identity()),
                start_distance=-size / 2,
                end_distance=size / 2
            )
        return _make
    
    # Create pattern book with grouped CSG patterns
    patterns = [
        (PatternMetadata("box1", ["group_b"], "csg"), make_box("box1")),
        (PatternMetadata("box2", ["group_b"], "csg"), make_box("box2")),
    ]
    book = PatternBook(patterns=patterns)
    
    # Raise the group
    separation = inches(12)
    csg_list = book.raise_pattern_group("group_b", separation)
    
    assert isinstance(csg_list, list)
    assert len(csg_list) == 2
    assert all(isinstance(obj, RectangularPrism) for obj in csg_list)


def test_raise_patternbook_as_frame_wraps_single_csg_pattern_as_accessory():
    """CSG-only patternbooks should still be viewable as a Frame."""

    def make_box(center):
        size = inches(2)
        return RectangularPrism(
            size=create_v2(size, size),
            transform=Transform(position=center, orientation=Orientation.identity()),
            start_distance=-size / Integer(2),
            end_distance=size / Integer(2)
        )

    metadata = PatternMetadata(pattern_name="box", pattern_type="csg")
    book = PatternBook(patterns=[(metadata, make_box)])

    frame = book.raise_patternbook_as_frame()

    assert isinstance(frame, Frame)
    assert len(frame.cut_timbers) == 0
    assert len(frame.accessories) == 1
    assert isinstance(frame.accessories[0], CSGAccessory)
    assert frame.name == "box"


def test_raise_patternbook_as_frame_combines_frame_and_csg_patterns():
    """Mixed frame/CSG patternbooks should combine into one viewable Frame."""

    def make_frame(center):
        timber = timber_from_directions(
            length=inches(24),
            size=create_v2(inches(2), inches(4)),
            bottom_position=center,
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0),
            ticket="test_timber"
        )
        return Frame(cut_timbers=[CutTimber(timber=timber, cuts=[])], name="simple_frame")

    def make_box(center):
        size = inches(2)
        return RectangularPrism(
            size=create_v2(size, size),
            transform=Transform(position=center, orientation=Orientation.identity()),
            start_distance=-size / Integer(2),
            end_distance=size / Integer(2)
        )

    patterns = [
        (PatternMetadata("frame1", [], "frame"), make_frame),
        (PatternMetadata("box1", [], "csg"), make_box),
    ]
    book = PatternBook(patterns=patterns)

    frame = book.raise_patternbook_as_frame(separation_distance=inches(12))

    assert isinstance(frame, Frame)
    assert len(frame.cut_timbers) == 1
    assert len(frame.accessories) == 1
    assert isinstance(frame.accessories[0], CSGAccessory)


def test_raise_pattern_group_mixed_types():
    """Test that mixing frame and CSG patterns in a group raises ValueError."""
    def make_frame(center):
        timber = timber_from_directions(
            length=inches(24),
            size=create_v2(inches(2), inches(4)),
            bottom_position=center,
            length_direction=create_v3(1, 0, 0),
            width_direction=create_v3(0, 1, 0)
        )
        return Frame(cut_timbers=[CutTimber(timber=timber, cuts=[])])
    
    def make_box(center):
        size = inches(2)
        return RectangularPrism(
            size=create_v2(size, size),
            transform=Transform(position=center, orientation=Orientation.identity()),
            start_distance=-size / Integer(2),
            end_distance=size / Integer(2)
        )
    
    # Create pattern book with mixed types in same group
    patterns = [
        (PatternMetadata("frame1", ["mixed_group"], "frame"), make_frame),
        (PatternMetadata("box1", ["mixed_group"], "csg"), make_box),
    ]
    book = PatternBook(patterns=patterns)
    
    # Should raise when trying to raise the mixed group
    with pytest.raises(ValueError, match="Cannot mix frame and CSG patterns"):
        book.raise_pattern_group("mixed_group", inches(12))


def test_raise_pattern_group_not_found():
    """Test that raising a non-existent group raises ValueError."""
    book = PatternBook(patterns=[])
    
    with pytest.raises(ValueError, match="Group 'nonexistent' not found"):
        book.raise_pattern_group("nonexistent", inches(12))


def test_list_patterns():
    """Test listing all patterns."""
    def dummy_func(center):
        return None
    
    patterns = [
        (PatternMetadata("pattern1", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern2", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern3", [], "csg"), dummy_func),
    ]
    book = PatternBook(patterns=patterns)
    
    pattern_names = book.list_patterns()
    assert len(pattern_names) == 3
    assert "pattern1" in pattern_names
    assert "pattern2" in pattern_names
    assert "pattern3" in pattern_names


def test_list_groups():
    """Test listing all groups."""
    def dummy_func(center):
        return None
    
    patterns = [
        (PatternMetadata("pattern1", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern2", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern3", ["group_b"], "csg"), dummy_func),
        (PatternMetadata("pattern4", [], "frame"), dummy_func),
    ]
    book = PatternBook(patterns=patterns)
    
    groups = book.list_groups()
    assert len(groups) == 2
    assert "group_a" in groups
    assert "group_b" in groups


def test_get_patterns_in_group():
    """Test getting patterns in a specific group."""
    def dummy_func(center):
        return None
    
    patterns = [
        (PatternMetadata("pattern1", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern2", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern3", ["group_b"], "csg"), dummy_func),
    ]
    book = PatternBook(patterns=patterns)
    
    group_a_patterns = book.get_patterns_in_group("group_a")
    assert len(group_a_patterns) == 2
    assert "pattern1" in group_a_patterns
    assert "pattern2" in group_a_patterns
    
    group_b_patterns = book.get_patterns_in_group("group_b")
    assert len(group_b_patterns) == 1
    assert "pattern3" in group_b_patterns


def test_patterns_with_multiple_groups():
    """Test patterns belonging to multiple groups."""
    def dummy_func(center):
        return None
    
    # Pattern1 is in both group_a and group_x
    # Pattern2 is only in group_a
    # Pattern3 is in both group_b and group_x
    patterns = [
        (PatternMetadata("pattern1", ["group_a", "group_x"], "frame"), dummy_func),
        (PatternMetadata("pattern2", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern3", ["group_b", "group_x"], "frame"), dummy_func),
    ]
    book = PatternBook(patterns=patterns)
    
    # Test list_groups flattens all groups
    groups = book.list_groups()
    assert len(groups) == 3
    assert "group_a" in groups
    assert "group_b" in groups
    assert "group_x" in groups
    
    # Test get_patterns_in_group finds patterns with that group
    group_a_patterns = book.get_patterns_in_group("group_a")
    assert len(group_a_patterns) == 2
    assert "pattern1" in group_a_patterns
    assert "pattern2" in group_a_patterns
    
    group_b_patterns = book.get_patterns_in_group("group_b")
    assert len(group_b_patterns) == 1
    assert "pattern3" in group_b_patterns
    
    group_x_patterns = book.get_patterns_in_group("group_x")
    assert len(group_x_patterns) == 2
    assert "pattern1" in group_x_patterns
    assert "pattern3" in group_x_patterns


def test_merge_pattern_books():
    """Test merging two PatternBooks."""
    def dummy_func(center):
        return None
    
    # Create first book
    patterns1 = [
        (PatternMetadata("pattern1", ["group_a"], "frame"), dummy_func),
        (PatternMetadata("pattern2", ["group_a"], "frame"), dummy_func),
    ]
    book1 = PatternBook(patterns=patterns1)
    
    # Create second book
    patterns2 = [
        (PatternMetadata("pattern3", ["group_b"], "csg"), dummy_func),
        (PatternMetadata("pattern4", ["group_b"], "csg"), dummy_func),
    ]
    book2 = PatternBook(patterns=patterns2)
    
    # Merge books
    merged_book = book1.merge(book2)
    
    # Check merged book has all patterns
    assert len(merged_book.list_patterns()) == 4
    assert "pattern1" in merged_book.list_patterns()
    assert "pattern2" in merged_book.list_patterns()
    assert "pattern3" in merged_book.list_patterns()
    assert "pattern4" in merged_book.list_patterns()
    
    # Check groups
    assert "group_a" in merged_book.list_groups()
    assert "group_b" in merged_book.list_groups()


def test_merge_multiple_pattern_books():
    """Test merging multiple PatternBooks at once."""
    def dummy_func(center):
        return None
    
    # Create three books
    book1 = PatternBook(patterns=[
        (PatternMetadata("pattern1", ["group_a"], "frame"), dummy_func),
    ])
    book2 = PatternBook(patterns=[
        (PatternMetadata("pattern2", ["group_b"], "frame"), dummy_func),
    ])
    book3 = PatternBook(patterns=[
        (PatternMetadata("pattern3", ["group_c"], "csg"), dummy_func),
    ])
    
    # Merge all books
    merged_book = PatternBook.merge_multiple([book1, book2, book3])
    
    # Check merged book has all patterns
    assert len(merged_book.list_patterns()) == 3
    assert "pattern1" in merged_book.list_patterns()
    assert "pattern2" in merged_book.list_patterns()
    assert "pattern3" in merged_book.list_patterns()
    
    # Check groups
    assert len(merged_book.list_groups()) == 3
    assert "group_a" in merged_book.list_groups()
    assert "group_b" in merged_book.list_groups()
    assert "group_c" in merged_book.list_groups()


def test_merge_duplicate_names_raises_error():
    """Test that merging books with duplicate pattern names raises an error."""
    def dummy_func(center):
        return None
    
    # Create two books with same pattern name
    book1 = PatternBook(patterns=[
        (PatternMetadata("duplicate", ["group_a"], "frame"), dummy_func),
    ])
    book2 = PatternBook(patterns=[
        (PatternMetadata("duplicate", ["group_b"], "frame"), dummy_func),
    ])
    
    # Should raise error when merging
    with pytest.raises(ValueError, match="Duplicate pattern names"):
        book1.merge(book2)