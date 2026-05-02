"""
Example demonstrating the use of PatternBook for organizing and raising patterns.

PatternBook is a helper structure for organizing multiple patterns (frames or CSG objects)
and raising them at different positions for visualization and testing.
"""

from kumiki import *


def create_simple_post_pattern() -> PatternBook:
    """
    Example: Create a pattern book with simple vertical posts.
    """
    
    # Define pattern functions
    def make_short_post(center):
        """Create a short 4x4 post, 4 feet tall"""
        return Frame(
            cut_timbers=[
                CutTimber(
                    timber=timber_from_directions(
                        length=feet(4),
                        size=create_v2(inches(4), inches(4)),
                        bottom_position=center,
                        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
                        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
                        ticket="short_post"
                    ),
                    cuts=[]
                )
            ],
            ticket="short_post_frame"
        )
    
    def make_tall_post(center):
        """Create a tall 6x6 post, 8 feet tall"""
        return Frame(
            cut_timbers=[
                CutTimber(
                    timber=timber_from_directions(
                        length=feet(8),
                        size=create_v2(inches(6), inches(6)),
                        bottom_position=center,
                        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
                        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
                        ticket="tall_post"
                    ),
                    cuts=[]
                )
            ],
            ticket="tall_post_frame"
        )
    
    def make_wide_post(center):
        """Create a wide 8x8 post, 6 feet tall"""
        return Frame(
            cut_timbers=[
                CutTimber(
                    timber=timber_from_directions(
                        length=feet(6),
                        size=create_v2(inches(8), inches(8)),
                        bottom_position=center,
                        length_direction=create_v3(Integer(0), Integer(0), Integer(1)),  # Vertical
                        width_direction=create_v3(Integer(1), Integer(0), Integer(0)),
                        ticket="wide_post"
                    ),
                    cuts=[]
                )
            ],
            ticket="wide_post_frame"
        )
    
    # Create pattern book with grouped patterns
    patterns = [
        (PatternMetadata("short_post", "posts", "frame"), make_short_post),  # type: ignore[arg-type]
        (PatternMetadata("tall_post", "posts", "frame"), make_tall_post),  # type: ignore[arg-type]
        (PatternMetadata("wide_post", "posts", "frame"), make_wide_post),  # type: ignore[arg-type]
    ]
    
    return PatternBook(patterns=patterns)


def create_beam_patterns() -> PatternBook:
    """
    Example: Create a pattern book with horizontal beams of different sizes.
    """
    
    def make_small_beam(center):
        """Create a small 2x4 beam, 8 feet long"""
        return Frame(
            cut_timbers=[
                CutTimber(
                    timber=timber_from_directions(
                        length=feet(8),
                        size=create_v2(inches(2), inches(4)),
                        bottom_position=center,
                        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),  # Horizontal along X
                        width_direction=create_v3(0, 1, 0),
                        ticket="small_beam"
                    ),
                    cuts=[]
                )
            ],
            ticket="small_beam_frame"
        )
    
    def make_medium_beam(center):
        """Create a medium 4x6 beam, 10 feet long"""
        return Frame(
            cut_timbers=[
                CutTimber(
                    timber=timber_from_directions(
                        length=feet(10),
                        size=create_v2(inches(4), inches(6)),
                        bottom_position=center,
                        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),  # Horizontal along X
                        width_direction=create_v3(0, 1, 0),
                        ticket="medium_beam"
                    ),
                    cuts=[]
                )
            ],
            ticket="medium_beam_frame"
        )
    
    def make_large_beam(center):
        """Create a large 6x8 beam, 12 feet long"""
        return Frame(
            cut_timbers=[
                CutTimber(
                    timber=timber_from_directions(
                        length=feet(12),
                        size=create_v2(inches(6), inches(8)),
                        bottom_position=center,
                        length_direction=create_v3(Integer(1), Integer(0), Integer(0)),  # Horizontal along X
                        width_direction=create_v3(0, 1, 0),
                        ticket="large_beam"
                    ),
                    cuts=[]
                )
            ],
            ticket="large_beam_frame"
        )
    
    # Create pattern book with grouped patterns
    patterns = [
        (PatternMetadata("small_beam", "beams", "frame"), make_small_beam),  # type: ignore[arg-type]
        (PatternMetadata("medium_beam", "beams", "frame"), make_medium_beam),  # type: ignore[arg-type]
        (PatternMetadata("large_beam", "beams", "frame"), make_large_beam),  # type: ignore[arg-type]
    ]
    
    return PatternBook(patterns=patterns)


def create_csg_box_patterns() -> PatternBook:
    """
    Example: Create a pattern book with CSG box primitives.
    """
    
    def make_small_box(center):
        """Create a small 2x2x2 inch box"""
        size = inches(2)
        return RectangularPrism(
            size=create_v2(size, size),
            transform=Transform(position=center, orientation=Orientation.identity()),
            start_distance=-size / 2,
            end_distance=size / 2
        )
    
    def make_medium_box(center):
        """Create a medium 4x4x4 inch box"""
        size = inches(4)
        return RectangularPrism(
            size=create_v2(size, size),
            transform=Transform(position=center, orientation=Orientation.identity()),
            start_distance=-size / 2,
            end_distance=size / 2
        )
    
    def make_large_box(center):
        """Create a large 6x6x6 inch box"""
        size = inches(6)
        return RectangularPrism(
            size=create_v2(size, size),
            transform=Transform(position=center, orientation=Orientation.identity()),
            start_distance=-size / 2,
            end_distance=size / 2
        )
    
    # Create pattern book with grouped CSG patterns
    patterns = [
        (PatternMetadata("small_box", "boxes", "csg"), make_small_box),  # type: ignore[arg-type]
        (PatternMetadata("medium_box", "boxes", "csg"), make_medium_box),  # type: ignore[arg-type]
        (PatternMetadata("large_box", "boxes", "csg"), make_large_box),  # type: ignore[arg-type]
    ]
    
    return PatternBook(patterns=patterns)


def example_raise_single_pattern():
    """Example: Raise a single pattern at a specific location."""
    print("\n=== Example: Raise Single Pattern ===")
    
    book = create_simple_post_pattern()
    
    # Raise a single pattern at the origin
    frame = book.raise_pattern("tall_post")
    print(f"Raised pattern: {frame.tag}")
    print(f"  Number of timbers: {len(frame.cut_timbers)}")
    
    # Raise a pattern at a specific location
    center = create_v3(feet(10), feet(5), 0)
    frame2 = book.raise_pattern("wide_post", center=center)
    print(f"\nRaised pattern at custom location: {frame2.tag}")
    print(f"  Position: {frame2.cut_timbers[0].timber.transform.position.T}")
    
    return frame


def example_raise_pattern_group():
    """Example: Raise a group of patterns with spacing."""
    print("\n=== Example: Raise Pattern Group ===")
    
    book = create_simple_post_pattern()
    
    # List available groups
    print(f"Available groups: {book.list_groups()}")
    print(f"Patterns in 'posts' group: {book.get_patterns_in_group('posts')}")
    
    # Raise all patterns in the 'posts' group with 4-foot spacing
    combined_frame = book.raise_pattern_group("posts", separation_distance=feet(4))
    
    print(f"\nCombined frame: {combined_frame.name}")
    print(f"  Number of timbers: {len(combined_frame.cut_timbers)}")
    
    # Show positions of each timber
    for i, cut_timber in enumerate(combined_frame.cut_timbers):
        pos = cut_timber.timber.transform.position
        print(f"  Timber {i} ({cut_timber.timber.ticket.name}): position = {pos.T}")
    
    return combined_frame


def example_raise_csg_group():
    """Example: Raise a group of CSG patterns."""
    print("\n=== Example: Raise CSG Group ===")
    
    book = create_csg_box_patterns()
    
    # Raise all CSG patterns in the 'boxes' group with 1-foot spacing
    csg_list = book.raise_pattern_group("boxes", separation_distance=feet(1))
    
    print(f"Number of CSG objects: {len(csg_list)}")  # type: ignore[arg-type]
    
    # Show details of each CSG object
    for i, csg in enumerate(csg_list):  # type: ignore[arg-type]
        print(f"  CSG {i}: {type(csg).__name__}")
        print(f"    Position: {csg.transform.position.T}")
    
    return csg_list


def example_list_patterns():
    """Example: List all patterns and groups in a book."""
    print("\n=== Example: List Patterns ===")
    
    book = create_beam_patterns()
    
    print(f"All patterns: {book.list_patterns()}")
    print(f"All groups: {book.list_groups()}")
    
    # List patterns in each group
    for group_name in book.list_groups():
        patterns_in_group = book.get_patterns_in_group(group_name)
        print(f"  Group '{group_name}': {patterns_in_group}")
    
    return book


def create_patternbook_example_patternbook() -> PatternBook:
    """
    Create a patternbook containing all the example patterns.
    This follows the convention used by other example files for integration with run_examples.py
    """
    books = [
        create_simple_post_pattern(),
        create_beam_patterns(),
        create_csg_box_patterns(),
    ]
    
    return PatternBook.merge_multiple(books)


patternbook = create_patternbook_example_patternbook()


def main():
    """Run all examples."""
    print("=" * 60)
    print("PatternBook Examples")
    print("=" * 60)
    
    # Run examples
    example_raise_single_pattern()
    example_raise_pattern_group()
    example_raise_csg_group()
    example_list_patterns()
    
    print("\n" + "=" * 60)
    print("Examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
