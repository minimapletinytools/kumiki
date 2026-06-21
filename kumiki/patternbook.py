"""
PatternBook - Helper structure for generating and organizing example patterns

This module provides a convenient way to organize multiple patterns (frames or CSG objects)
and raise them at different positions for visualization and testing.
"""

from sympy import Rational
import inspect
from typing import Any, List, Tuple, Optional, Callable, Union, Literal, Sequence
from dataclasses import dataclass, field, replace
from .rule import V3, create_v3, Transform
from .timber import Frame, CutTimber, Timber, Peg, Wedge, CSGAccessory, Joint, JointAccessory
from .cutcsg import CutCSG, translate_csg


# Type alias for pattern functions.
# The first positional argument is the pattern center (V3), followed by
# optional keyword parameters for parameterized rendering.
PatternLambda = Callable[..., Union[Frame, CutCSG]]


def _build_pattern_lambda_signature(source_func: Callable[..., Any]) -> inspect.Signature:
    """Build a callable signature for pattern lambdas.

    Pattern lambdas always take center as the first positional argument. Any
    additional parameters are copied from source_func after dropping its first
    parameter (the source position argument).
    """
    source_sig = inspect.signature(source_func)
    source_params = list(source_sig.parameters.values())

    center_param = inspect.Parameter(
        "center",
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=V3,
    )

    if not source_params:
        return inspect.Signature(parameters=[center_param], return_annotation=source_sig.return_annotation)

    trailing_params = source_params[1:]
    return inspect.Signature(
        parameters=[center_param, *trailing_params],
        return_annotation=source_sig.return_annotation,
    )


def make_pattern_from_joint(joint_func: Callable[..., Joint]) -> PatternLambda:
    """
    Convert a joint function (no args, returns a joint with cut_timbers and jointAccessories)
    to a pattern lambda that accepts center and returns a Frame with all timbers and
    accessories translated by center.
    """
    def pattern_lambda(center: V3, **pattern_kwargs: Any) -> Frame:
        joint = joint_func(**pattern_kwargs)
        translated_timbers: List[CutTimber] = []
        for cutting in joint.cuttings.values():
            new_position = cutting.timber.get_bottom_position_global() + center
            # Preserve the concrete timber subclass (RoundTimber, MeshTimber, etc.) — only override the transform.
            translated_timber = replace(
                cutting.timber,
                transform=Transform(position=new_position, orientation=cutting.timber.orientation),
            )
            translated_cut = replace(cutting, timber=translated_timber)
            translated_timbers.append(CutTimber(timber=translated_timber, cuts=[translated_cut]))

        translated_accessories: List[JointAccessory] = []
        if joint.jointAccessories:
            for accessory in joint.jointAccessories.values():
                if isinstance(accessory, Peg):
                    translated_transform = Transform(
                        position=accessory.transform.position + center,
                        orientation=accessory.transform.orientation
                    )
                    translated_accessories.append(Peg(
                        ticket=accessory.ticket,
                        transform=translated_transform,
                        size=accessory.size,
                        shape=accessory.shape,
                        forward_length=accessory.forward_length,
                        stickout_length=accessory.stickout_length
                    ))
                elif isinstance(accessory, Wedge):
                    translated_transform = Transform(
                        position=accessory.transform.position + center,
                        orientation=accessory.transform.orientation
                    )
                    translated_accessories.append(Wedge(
                        ticket=accessory.ticket,
                        transform=translated_transform,
                        base_width=accessory.base_width,
                        tip_width=accessory.tip_width,
                        height=accessory.height,
                        length=accessory.length,
                        stickout_length=accessory.stickout_length
                    ))
                elif isinstance(accessory, CSGAccessory):
                    translated_transform = Transform(
                        position=accessory.transform.position + center,
                        orientation=accessory.transform.orientation,
                    )
                    translated_accessories.append(CSGAccessory(
                        ticket=accessory.ticket,
                        transform=translated_transform,
                        positive_csg=accessory.positive_csg,
                    ))
                else:
                    translated_accessories.append(accessory)

        return Frame(cut_timbers=translated_timbers, accessories=translated_accessories)

    setattr(pattern_lambda, "__signature__", _build_pattern_lambda_signature(joint_func))
    return pattern_lambda


def make_pattern_from_frame(frame_func: Callable[..., Frame]) -> PatternLambda:
    """
    Convert a Frame-returning function (no args) to a pattern lambda that accepts center
    and returns a Frame with all timbers and accessories translated by center.
    """
    def pattern_lambda(center: V3, **pattern_kwargs: Any) -> Frame:
        frame = frame_func(**pattern_kwargs)
        translated_timbers = []
        for cut_timber in frame.cut_timbers:
            new_position = cut_timber.timber.get_bottom_position_global() + center
            # Preserve the concrete timber subclass (RoundTimber, MeshTimber, etc.) — only override the transform.
            translated_timber = replace(
                cut_timber.timber,
                transform=Transform(position=new_position, orientation=cut_timber.timber.orientation),
            )
            translated_timbers.append(CutTimber(timber=translated_timber, cuts=cut_timber.cuts))

        translated_accessories: List[JointAccessory] = []
        if frame.accessories:
            for accessory in frame.accessories:
                if isinstance(accessory, Peg):
                    translated_transform = Transform(
                        position=accessory.transform.position + center,
                        orientation=accessory.transform.orientation
                    )
                    translated_accessories.append(Peg(
                        ticket=accessory.ticket,
                        transform=translated_transform,
                        size=accessory.size,
                        shape=accessory.shape,
                        forward_length=accessory.forward_length,
                        stickout_length=accessory.stickout_length
                    ))
                elif isinstance(accessory, Wedge):
                    translated_transform = Transform(
                        position=accessory.transform.position + center,
                        orientation=accessory.transform.orientation
                    )
                    translated_accessories.append(Wedge(
                        ticket=accessory.ticket,
                        transform=translated_transform,
                        base_width=accessory.base_width,
                        tip_width=accessory.tip_width,
                        height=accessory.height,
                        length=accessory.length,
                        stickout_length=accessory.stickout_length
                    ))
                elif isinstance(accessory, CSGAccessory):
                    translated_transform = Transform(
                        position=accessory.transform.position + center,
                        orientation=accessory.transform.orientation,
                    )
                    translated_accessories.append(CSGAccessory(
                        ticket=accessory.ticket,
                        transform=translated_transform,
                        positive_csg=accessory.positive_csg,
                    ))
                else:
                    translated_accessories.append(accessory)

        return Frame(cut_timbers=translated_timbers, accessories=translated_accessories)

    setattr(pattern_lambda, "__signature__", _build_pattern_lambda_signature(frame_func))
    return pattern_lambda


def make_pattern_from_csg(csg_func: Callable[..., CutCSG]) -> PatternLambda:
    """
    Convert a CSG-returning function (no args) to a pattern lambda that accepts center
    and returns the CSG translated by center. Consistent with frame/joint patterns:
    the returned CSG is positioned at the given center.
    """
    def pattern_lambda(center: V3, **pattern_kwargs: Any) -> CutCSG:
        return translate_csg(csg_func(**pattern_kwargs), center)

    setattr(pattern_lambda, "__signature__", _build_pattern_lambda_signature(csg_func))
    return pattern_lambda


@dataclass(frozen=True)
class Pattern:
    """A single renderable pattern in the new pattern system.

    path: hierarchical path like "corner_joints/cut_plain_miter_joint".
          Each path segment is an implicit tag for filtering.
    lambda_: callable(center: V3, **kwargs) -> Frame | CutCSG
    tags: explicit tags. Special values: 'main' (default display when file opened),
          'poop' (hide from sidebar).
    pattern_type: 'frame' or 'csg'
    """
    path: str
    lambda_: PatternLambda
    tags: List[str] = field(default_factory=list)
    pattern_type: Literal['frame', 'csg'] = 'frame'

    @property
    def name(self) -> str:
        return self.path.split('/')[-1]

    @property
    def path_segments(self) -> List[str]:
        return self.path.split('/')

    def all_tags(self) -> List[str]:
        """Return all tags including implicit path segment tags."""
        return list(self.path_segments) + list(self.tags)

    def raise_at(self, center: Optional[Any] = None, **kwargs: Any) -> Any:
        """Raise this pattern at the given center (defaults to origin)."""
        if center is None:
            from sympy import Integer
            center = create_v3(Integer(0), Integer(0), Integer(0))
        return self.lambda_(center, **kwargs)


@dataclass(frozen=True)
class PatternMetadata:
    """
    Metadata describing a pattern in the pattern book.
    
    Attributes:
        pattern_name: Unique name for this pattern
        pattern_group_names: List of group names to organize related patterns
        pattern_type: Type of pattern - either 'frame' or 'csg'
    """
    pattern_name: str
    pattern_group_names: List[str] = field(default_factory=list)
    pattern_type: Literal['frame', 'csg'] = 'frame'
    
    def __post_init__(self):
        """Validate pattern type."""
        if self.pattern_type not in ['frame', 'csg']:
            raise ValueError(f"pattern_type must be 'frame' or 'csg', got: {self.pattern_type}")


@dataclass
class PatternBook:
    """
    A collection of patterns with functions to raise them at different positions.
    
    Patterns can be either Frame objects or CutCSG objects, and can be organized
    into groups for batch visualization with spacing.
    
    Attributes:
        patterns: List of (PatternMetadata, PatternLambda) pairs
    """
    patterns: List[Tuple[PatternMetadata, PatternLambda]] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate pattern names are unique."""
        names = [metadata.pattern_name for metadata, _ in self.patterns]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f"Duplicate pattern names found: {set(duplicates)}")
    
    def raise_pattern(
        self,
        pattern_name: str,
        center: Optional[V3] = None,
        **pattern_kwargs: Any,
    ) -> Union[Frame, CutCSG]:
        """
        Raise a single pattern by name at the specified center location.
        
        Args:
            pattern_name: Name of the pattern to raise
            center: Center location for the pattern (default: origin)
            
        Returns:
            Frame or CutCSG object at the specified location
            
        Raises:
            ValueError: If pattern_name is not found
        """
        if center is None:
            from sympy import Integer
            center = create_v3(Integer(0), Integer(0), Integer(0))
        
        # Find the pattern by name
        for metadata, pattern_lambda in self.patterns:
            if metadata.pattern_name == pattern_name:
                return pattern_lambda(center, **pattern_kwargs)
        
        # Pattern not found
        available_names = [m.pattern_name for m, _ in self.patterns]
        raise ValueError(f"Pattern '{pattern_name}' not found. Available patterns: {available_names}")
    
    def raise_pattern_group(
        self, 
        group_name: str, 
        separation_distance: Union[float, int, Rational],
        start_center: Optional[V3] = None
    ) -> Union[Frame, List[CutCSG]]:
        """
        Raise all patterns in a group, separated by the specified distance along the X-axis.
        
        For frame patterns: Breaks apart individual frames and builds a megaframe from all of them.
        For CSG patterns: Returns a list of CSG objects.
        
        Args:
            group_name: Name of the group to raise
            separation_distance: Distance between pattern centers along X-axis
            start_center: Starting center location (default: origin)
            
        Returns:
            For frame patterns: A single Frame containing all cut timbers from all patterns
            For CSG patterns: A list of CutCSG objects
            
        Raises:
            ValueError: If group_name is not found or if frame and CSG patterns are mixed
        """
        separation_distance, start_center = self._normalize_spacing_args(
            separation_distance,
            start_center,
        )
        
        # Find all patterns in the group (check if group_name is in pattern_group_names list)
        group_patterns = [
            (metadata, pattern_lambda) 
            for metadata, pattern_lambda in self.patterns 
            if group_name in metadata.pattern_group_names
        ]
        
        if not group_patterns:
            available_groups = self.list_groups()
            raise ValueError(f"Group '{group_name}' not found. Available groups: {available_groups}")
        
        # Check that all patterns in the group have the same type
        pattern_types = set(metadata.pattern_type for metadata, _ in group_patterns)
        if len(pattern_types) > 1:
            raise ValueError(
                f"Cannot mix frame and CSG patterns in the same group. "
                f"Group '{group_name}' contains types: {pattern_types}"
            )
        
        pattern_type = list(pattern_types)[0]
        
        # Raise all patterns with appropriate spacing
        results = self._raise_entries_with_spacing(
            group_patterns,
            separation_distance,
            start_center,
        )
        
        # Process results based on pattern type
        if pattern_type == 'frame':
            # Combine all frames into a megaframe
            frame_results = [result for result in results if isinstance(result, Frame)]
            if len(frame_results) != len(results):
                raise TypeError(
                    f"Group '{group_name}' contains non-frame results while pattern_type='frame'"
                )
            return self._combine_frames(frame_results, group_name)
        else:  # pattern_type == 'csg'
            # Return list of CSG objects
            csg_results = [result for result in results if isinstance(result, CutCSG)]
            if len(csg_results) != len(results):
                raise TypeError(
                    f"Group '{group_name}' contains non-CSG results while pattern_type='csg'"
                )
            return csg_results

    def raise_patternbook_as_frame(
        self,
        separation_distance: Union[float, int, Rational] = Rational(2),
        start_center: Optional[V3] = None,
    ) -> Frame:
        """Raise this PatternBook as a single combined Frame.

        Prefers ``raise_pattern_group`` when one group covers all patterns.
        Falls back to raising each frame pattern by position and combining.
        """
        pattern_names = self.list_patterns()
        if not pattern_names:
            raise ValueError("PatternBook is empty")

        if len(pattern_names) == 1:
            single = self.raise_pattern(pattern_names[0], center=start_center)
            return self._coerce_pattern_result_to_frame(single, pattern_names[0])

        separation_distance, start_center = self._normalize_spacing_args(
            separation_distance,
            start_center,
        )

        all_pattern_set = set(pattern_names)
        umbrella_group: Optional[str] = None
        for group_name in self.list_groups():
            if set(self.get_patterns_in_group(group_name)) >= all_pattern_set:
                umbrella_group = group_name
                break

        if umbrella_group is not None:
            grouped_result = self.raise_pattern_group(
                umbrella_group,
                separation_distance=separation_distance,
                start_center=start_center,
            )
            return self._coerce_pattern_result_to_frame(grouped_result, umbrella_group)

        results = self._raise_entries_with_spacing(
            self.patterns,
            separation_distance,
            start_center,
        )
        return self._combine_pattern_results_as_frame(results, "all_patterns")

    def _normalize_spacing_args(
        self,
        separation_distance: Union[float, int, Rational],
        start_center: Optional[V3],
    ) -> Tuple[Rational, V3]:
        if start_center is None:
            from sympy import Integer
            start_center = create_v3(Integer(0), Integer(0), Integer(0))

        if not isinstance(separation_distance, Rational):
            separation_distance = Rational(separation_distance)

        return separation_distance, start_center

    def _raise_entries_with_spacing(
        self,
        entries: List[Tuple[PatternMetadata, PatternLambda]],
        separation_distance: Rational,
        start_center: V3,
    ) -> List[Union[Frame, CutCSG]]:
        from sympy import Integer

        results: List[Union[Frame, CutCSG]] = []
        for i, (_metadata, pattern_lambda) in enumerate(entries):
            offset = create_v3(Integer(i) * separation_distance, Integer(0), Integer(0))
            center = start_center + offset
            results.append(pattern_lambda(center))
        return results

    def _coerce_pattern_result_to_frame(
        self,
        result: Union[Frame, CutCSG, List[CutCSG]],
        name: str,
    ) -> Frame:
        if isinstance(result, Frame):
            return result
        # hack CutCSG into a Frame so we can view CutCSG examples directly in the viewer
        # this is just for development, for examples, you should always wrap in a frame.
        if isinstance(result, CutCSG):
            return Frame(
                cut_timbers=[],
                accessories=[
                    CSGAccessory(
                        transform=Transform.identity(),
                        positive_csg=result,
                    )
                ],
                name=name,
            )
        if isinstance(result, list):
            return self._combine_pattern_results_as_frame(result, name)
        raise TypeError(
            f"Pattern '{name}' returned {type(result).__name__}, expected Frame or CutCSG"
        )

    def _combine_pattern_results_as_frame(
        self,
        results: Sequence[Union[Frame, CutCSG]],
        name: str,
    ) -> Frame:
        all_cut_timbers: List[CutTimber] = []
        all_accessories: List[JointAccessory] = []
        all_source_joints: List = []

        for result in results:
            if isinstance(result, Frame):
                all_cut_timbers.extend(result.cut_timbers)
                all_accessories.extend(result.accessories)
                if result.source_joints:
                    all_source_joints.extend(result.source_joints)
                continue
            if isinstance(result, CutCSG):
                all_accessories.append(
                    CSGAccessory(
                        transform=Transform.identity(),
                        positive_csg=result,
                    )
                )
                continue
            raise TypeError(
                f"PatternBook result {type(result).__name__} cannot be combined into a Frame"
            )

        return Frame(
            cut_timbers=all_cut_timbers,
            accessories=all_accessories,
            name=name,
            source_joints=all_source_joints or None,
        )
    
    def _combine_frames(self, frames: List[Frame], group_name: str) -> Frame:
        """
        Combine multiple Frame objects into a single megaframe.
        
        Extracts all cut_timbers and accessories from all frames and combines them
        into a single Frame object.
        
        Args:
            frames: List of Frame objects to combine
            group_name: Name for the combined frame
            
        Returns:
            A single Frame containing all cut timbers and accessories
        """
        all_cut_timbers = []
        all_accessories = []
        all_source_joints: List = []

        for frame in frames:
            all_cut_timbers.extend(frame.cut_timbers)
            all_accessories.extend(frame.accessories)
            if frame.source_joints:
                all_source_joints.extend(frame.source_joints)

        # Create megaframe
        megaframe = Frame(
            cut_timbers=all_cut_timbers,
            accessories=all_accessories,
            name=f"{group_name}_combined",
            source_joints=all_source_joints or None,
        )
        
        return megaframe
    
    def list_patterns(self) -> List[str]:
        """
        List all pattern names in the book.
        
        Returns:
            List of pattern names
        """
        return [metadata.pattern_name for metadata, _ in self.patterns]
    
    def list_groups(self) -> List[str]:
        """
        List all unique group names in the book.
        
        Returns:
            List of group names (flattened from all patterns)
        """
        groups = set()
        for metadata, _ in self.patterns:
            groups.update(metadata.pattern_group_names)
        return sorted(list(groups))
    
    def get_patterns_in_group(self, group_name: str) -> List[str]:
        """
        Get all pattern names in a specific group.
        
        Args:
            group_name: Name of the group
            
        Returns:
            List of pattern names in the group
        """
        return [
            metadata.pattern_name 
            for metadata, _ in self.patterns 
            if group_name in metadata.pattern_group_names
        ]
    
    def merge(self, other: 'PatternBook') -> 'PatternBook':
        """
        Merge another PatternBook into a new PatternBook.
        
        Args:
            other: Another PatternBook to merge with this one
            
        Returns:
            A new PatternBook containing patterns from both books
            
        Raises:
            ValueError: If there are duplicate pattern names
        """
        all_patterns = self.patterns + other.patterns
        return PatternBook(patterns=all_patterns)
    
    @staticmethod
    def merge_multiple(pattern_books: List['PatternBook']) -> 'PatternBook':
        """
        Merge multiple PatternBooks into a single PatternBook.
        
        Args:
            pattern_books: List of PatternBooks to merge
            
        Returns:
            A new PatternBook containing patterns from all books
            
        Raises:
            ValueError: If there are duplicate pattern names
        """
        all_patterns = []
        for book in pattern_books:
            all_patterns.extend(book.patterns)
        return PatternBook(patterns=all_patterns)
