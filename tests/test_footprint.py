"""
Tests for footprint.py module.

This module contains tests for the Footprint class in the Kumiki system.
"""

import pytest
from sympy import Matrix
from kumiki.footprint import *
from kumiki.footprint import _segment_to_segment_distance
from kumiki import create_v2
from tests.testing_shavings import create_test_footprint


class TestFootprint:
    """Test Footprint class."""
    
    def test_footprint_creation(self):
        """Test basic footprint creation."""
        corners = [
            create_v2(0, 0),  # Use exact integers
            create_v2(1, 0),  # Use exact integers
            create_v2(1, 1),  # Use exact integers
            create_v2(0, 1)   # Use exact integers
        ]
        footprint = Footprint(tuple(corners))
        
        assert len(footprint.corners) == 4
        assert footprint.corners[0][0] == 0
        assert footprint.corners[0][1] == 0
    
    def test_footprint_sides(self):
        """Test sides() method."""
        corners = [
            create_v2(0, 0),
            create_v2(1, 0),
            create_v2(1, 1),
            create_v2(0, 1)
        ]
        footprint = Footprint(tuple(corners))
        
        sides = footprint.sides()
        
        assert len(sides) == 4
        # Check first side
        assert sides[0][0] == corners[0]
        assert sides[0][1] == corners[1]
        # Check last side wraps around
        assert sides[3][0] == corners[3]
        assert sides[3][1] == corners[0]
    
    def test_footprint_is_valid_valid_footprint(self):
        """Test is_valid() with a valid footprint."""
        corners = [
            create_v2(0, 0),
            create_v2(1, 0),
            create_v2(1, 1),
            create_v2(0, 1)
        ]
        footprint = Footprint(tuple(corners))
        
        assert footprint.is_valid() == True
    
    def test_footprint_is_valid_too_few_corners(self):
        """Test is_valid() with too few corners."""
        corners = [
            create_v2(0, 0),
            create_v2(1, 0)
        ]
        footprint = Footprint(tuple(corners))
        
        assert footprint.is_valid() == False
    
    def test_footprint_is_valid_self_intersecting(self):
        """Test is_valid() with self-intersecting sides."""
        corners = [
            create_v2(0, 0),
            create_v2(1, 1),
            create_v2(1, 0),
            create_v2(0, 1)
        ]
        footprint = Footprint(tuple(corners))
        
        assert footprint.is_valid() == False
    
    def test_footprint_contains_point_inside(self):
        """Test contains_point() with point inside."""
        corners = [
            create_v2(0, 0),
            create_v2(2, 0),
            create_v2(2, 2),
            create_v2(0, 2)
        ]
        footprint = Footprint(tuple(corners))
        
        assert footprint.contains_point(create_v2(1, 1)) == True
    
    def test_footprint_contains_point_outside(self):
        """Test contains_point() with point outside."""
        corners = [
            create_v2(0, 0),
            create_v2(2, 0),
            create_v2(2, 2),
            create_v2(0, 2)
        ]
        footprint = Footprint(tuple(corners))
        
        assert footprint.contains_point(create_v2(3, 3)) == False
    
    def test_footprint_nearest_corner(self):
        """Test nearest_corner() method."""
        corners = [
            create_v2(0, 0),
            create_v2(2, 0),
            create_v2(2, 2),
            create_v2(0, 2)
        ]
        footprint = Footprint(tuple(corners))
        
        # Point closest to corner 0
        idx, corner = footprint.nearest_corner(create_v2(Rational("0.1"), Rational("0.1")))
        assert idx == 0
        assert corner == corners[0]
        
        # Point closest to corner 2
        idx, corner = footprint.nearest_corner(create_v2(Rational("1.9"), Rational("1.9")))
        assert idx == 2
        assert corner == corners[2]
    
    def test_footprint_nearest_boundary(self):
        """Test nearest_boundary() method."""
        corners = [
            create_v2(0, 0),
            create_v2(2, 0),
            create_v2(2, 2),
            create_v2(0, 2)
        ]
        footprint = Footprint(tuple(corners))
        
        # Point closest to first side (bottom edge)
        idx, side, dist = footprint.nearest_boundary(create_v2(1, Rational("-0.5")))
        assert idx == 0
        assert side == (corners[0], corners[1])
        assert abs(dist - 0.5) < 1e-6
        
        # Point closest to third side (top edge)
        idx, side, dist = footprint.nearest_boundary(create_v2(1, Rational("2.5")))
        assert idx == 2
        assert side == (corners[2], corners[3])
        assert abs(dist - 0.5) < 1e-6
    
    def test_footprint_get_inward_normal(self):
        """Test get_inward_normal() method with exact arithmetic."""
        # Create a counter-clockwise square footprint using exact integers
        corners = [
            create_v2(0, 0),  # Bottom-left - exact integers
            create_v2(2, 0),  # Bottom-right - exact integers
            create_v2(2, 2),  # Top-right - exact integers
            create_v2(0, 2)   # Top-left - exact integers
        ]
        footprint = Footprint(tuple(corners))
        
        # Test bottom edge (should point up/inward: y+)
        # Returns Direction3D (V3)
        normal = footprint.get_inward_normal(0)
        assert zero_test(normal[0])
        assert normal[1] == Integer(1)
        assert zero_test(normal[2])
        
        # Test right edge (should point left/inward: x-)
        normal = footprint.get_inward_normal(1)
        assert normal[0] == Integer(-1)
        assert zero_test(normal[1])
        assert zero_test(normal[2])
        
        # Test top edge (should point down/inward: y-)
        normal = footprint.get_inward_normal(2)
        assert zero_test(normal[0])
        assert normal[1] == Integer(-1)
        assert zero_test(normal[2])
        
        # Test left edge (should point right/inward: x+)
        normal = footprint.get_inward_normal(3)
        assert normal[0] == Integer(1)
        assert zero_test(normal[1])
        assert zero_test(normal[2])
    
    def test_segment_to_segment_distance_parallel(self):
        """Test _segment_to_segment_distance with parallel segments."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 4),
            create_v2(0, 4)
        ]
        footprint = Footprint(tuple(corners))
        
        # Horizontal line parallel to bottom edge, 1 unit above
        line_start = create_v2(1, 1)
        line_end = create_v2(3, 1)
        
        # Calculate distance to bottom edge (y=0)
        seg_start = create_v2(0, 0)
        seg_end = create_v2(4, 0)
        
        distance = _segment_to_segment_distance(line_start, line_end, seg_start, seg_end)
        assert abs(distance - 1.0) < 1e-6
    
    def test_segment_to_segment_distance_intersecting(self):
        """Test _segment_to_segment_distance with intersecting segments."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 4),
            create_v2(0, 4)
        ]
        footprint = Footprint(tuple(corners))
        
        # Two segments that cross
        line1_start = create_v2(0, 0)
        line1_end = create_v2(2, 2)
        
        line2_start = create_v2(0, 2)
        line2_end = create_v2(2, 0)
        
        distance = _segment_to_segment_distance(line1_start, line1_end, line2_start, line2_end)
        assert zero_test(distance)
    
    def test_segment_to_segment_distance_perpendicular(self):
        """Test _segment_to_segment_distance with perpendicular segments."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 4),
            create_v2(0, 4)
        ]
        footprint = Footprint(tuple(corners))
        
        # Horizontal segment
        line1_start = create_v2(0, 0)
        line1_end = create_v2(2, 0)
        
        # Vertical segment offset by 1 unit
        line2_start = create_v2(3, 0)
        line2_end = create_v2(3, 2)
        
        distance = _segment_to_segment_distance(line1_start, line1_end, line2_start, line2_end)
        assert abs(distance - 1.0) < 1e-6
    
    def test_nearest_boundary_from_line_parallel(self):
        """Test nearest_boundary_from_line with a line parallel to a boundary."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 4),
            create_v2(0, 4)
        ]
        footprint = Footprint(tuple(corners))
        
        # Horizontal line parallel to bottom edge, 0.5 units above
        line_start = create_v2(1, Rational("0.5"))
        line_end = create_v2(3, Rational("0.5"))
        
        idx, side, dist = footprint.nearest_boundary_from_line(line_start, line_end)
        
        # Should be closest to bottom edge (index 0)
        assert idx == 0
        assert side == (corners[0], corners[1])
        assert abs(dist - 0.5) < 1e-6
    
    def test_nearest_boundary_from_line_perpendicular(self):
        """Test nearest_boundary_from_line with a line perpendicular to boundaries."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 4),
            create_v2(0, 4)
        ]
        footprint = Footprint(tuple(corners))
        
        # Vertical line outside and parallel to right edge
        line_start = create_v2(5, 1)
        line_end = create_v2(5, 3)
        
        idx, side, dist = footprint.nearest_boundary_from_line(line_start, line_end)
        
        # Should be closest to right edge (index 1)
        assert idx == 1
        assert side == (corners[1], corners[2])
        assert abs(dist - 1.0) < 1e-6
    
    def test_nearest_boundary_from_line_diagonal(self):
        """Test nearest_boundary_from_line with a diagonal line."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 4),
            create_v2(0, 4)
        ]
        footprint = Footprint(tuple(corners))
        
        # Diagonal line outside, closer to bottom edge
        line_start = create_v2(1, -1)
        line_end = create_v2(3, -1)
        
        idx, side, dist = footprint.nearest_boundary_from_line(line_start, line_end)
        
        # Should be closest to bottom edge (index 0)
        assert idx == 0
        assert abs(dist - 1.0) < 1e-6
    
    def test_nearest_boundary_from_line_intersecting(self):
        """Test nearest_boundary_from_line with a line that intersects the footprint."""
        corners = [
            create_v2(0, 0),
            create_v2(4, 0),
            create_v2(4, 4),
            create_v2(0, 4)
        ]
        footprint = Footprint(tuple(corners))
        
        # Line that crosses through the footprint
        line_start = create_v2(-1, 2)
        line_end = create_v2(5, 2)
        
        idx, side, dist = footprint.nearest_boundary_from_line(line_start, line_end)
        
        # Should have distance 0 since it intersects
        assert zero_test(dist)

