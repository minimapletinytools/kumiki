"""
Kumiki FreeCAD Examples Runner - uses PatternBook for unified rendering.

This script uses the Anthology PatternBook to render all examples with automatic module reloading,
so you can make changes to your code and re-run this macro without restarting FreeCAD.

SETUP (one-time):
1. Open FreeCAD
2. Go to Edit → Preferences → Python → Macro
3. Click "Add" under "Macro path"
4. Navigate to and select the freecad/ folder
5. Click OK

TO RUN:
1. Open FreeCAD
2. Go to Macro → Macros...
3. Select "run_examples.py" from the list
4. Click "Execute"

TO CHANGE WHAT RENDERS:
Edit the configuration variables below:
- RENDER_TYPE: Choose 'pattern' (single) or 'group' (multiple with spacing)
- PATTERN_NAME: Name of specific pattern to render (when RENDER_TYPE = 'pattern')
- GROUP_NAME: Name of pattern group to render (when RENDER_TYPE = 'group')
- SEPARATION_DISTANCE_METERS: Spacing between patterns in group mode
"""

import sys
import os
import importlib

# Add Kumiki to path
script_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)


# ============================================================================
# CONFIGURATION: Choose what to render using PatternBook
# ============================================================================

# RENDER_TYPE: 'pattern' or 'group'
# - 'pattern': Render a single pattern by name
# - 'group': Render all patterns in a group with spacing
RENDER_TYPE = 'group'
#RENDER_TYPE = 'pattern'

# PATTERN_NAME: Name of a specific pattern to render (when RENDER_TYPE = 'pattern')
# Examples of available patterns:
#PATTERN_NAME = 'miter_joint_face_aligned'
#PATTERN_NAME = 'butt_joint'
#PATTERN_NAME = 'splice_joint'
#PATTERN_NAME = 'mortise_and_tenon_simple'
#PATTERN_NAME = 'brace_joint'  # Brace joint with mortise and tenon connections
#PATTERN_NAME = 'dovetail_half_lap'
#PATTERN_NAME = 'oscar_shed'
#PATTERN_NAME = 'gooseneck_simple'
#PATTERN_NAME = 'shoulder_notch'
#PATTERN_NAME = 'short_post'
#PATTERN_NAME = 'honeycomb_shed'
#PATTERN_NAME = 'mitered_keyed_lap'
#PATTERN_NAME = 'brace_joint'
#PATTERN_NAME = 'sawhorse'
#PATTERN_NAME = 'irrational_angles'
#PATTERN_NAME = 'tongue_and_fork_butt_joint_138'

# GROUP_NAME: Name of a pattern group to render (when RENDER_TYPE = 'group')
#GROUP_NAME = 'plain_joints'
#GROUP_NAME = 'mortise_tenon'  # All mortise and tenon examples (brace_joint excluded until angled M&T is implemented)
GROUP_NAME = 'basic_joints'  # All simplified basic joint examples
#GROUP_NAME = 'japanese_joints'
#GROUP_NAME = 'posts'
#GROUP_NAME = 'csg'
#GROUP_NAME = 'double_butt_joints'

# SEPARATION_DISTANCE: Distance between patterns when rendering a group (in meters)
# Common values: m(1), m(2), feet(3), feet(4), inches(24)
SEPARATION_DISTANCE_METERS = 2.0  # 2 meters between patterns

# Anthology PatternBook - will be initialized after module reload
ANTHOLOGY_PATTERN_BOOK = None


def create_anthology_pattern_book():
    """
    Create an anthology PatternBook containing all patterns from all example files.
    
    Returns:
        PatternBook: A single PatternBook with all patterns from all examples
    """
    from kumiki.librarian import create_anthology_pattern_book_from_folder

    patterns_dir = os.path.join(parent_dir, 'patterns')
    anthology_book, scan_result = create_anthology_pattern_book_from_folder(patterns_dir)

    print(f"Scanned {len(scan_result.modules)} module files in {patterns_dir}")
    print(f"Loaded {len(scan_result.pattern_books)} PatternBooks")
    print(f"Loaded {len(scan_result.examples)} examples")

    if scan_result.errors:
        print(f"Encountered {len(scan_result.errors)} module import errors:")
        for module in scan_result.modules:
            if module.load_error is not None:
                print(f"  ⚠ {module.relative_path}: {module.load_error}")
                if module.load_error_traceback:
                    for line in module.load_error_traceback.splitlines():
                        print(f"    {line}")
    
    print(f"Anthology PatternBook created with {len(anthology_book.list_patterns())} patterns")
    print(f"Available groups: {', '.join(anthology_book.list_groups())}")
    
    return anthology_book


def reload_all_modules():
    """Reload all Kumiki modules in dependency order."""
    print("="*70)
    print("Kumiki FreeCAD - Examples Runner")
    print("="*70)
    print("\nReloading all Kumiki modules...")
    
    # AGGRESSIVE MODULE CLEANUP: Delete ALL Kumiki-related modules
    # This ensures no stale class references remain after reload
    modules_to_delete = []
    for module_name in list(sys.modules.keys()):
        # Delete any module that starts with our project prefixes
        if (module_name.startswith('kumiki') or 
            module_name.startswith('patterns') or 
            module_name.startswith('giraffe_librarian_dynamic') or
            module_name == 'giraffe' or
            module_name.startswith('giraffe.') or
            module_name == 'giraffe_render_freecad'):
            modules_to_delete.append(module_name)
    
    print(f"  Deleting {len(modules_to_delete)} cached modules...")
    
    for module_name in modules_to_delete:
        del sys.modules[module_name]
    
    # List of modules to reload in dependency order
    modules_to_reload = [
        'kumiki',  # Reload the package itself first
        'kumiki.rule',
        'kumiki.footprint',
        'kumiki.cutcsg',
        'kumiki.timber',
        'kumiki.measuring',
        'kumiki.construction',
        'kumiki.rendering_utils',
        'kumiki.joints.joint_shavings',
        'kumiki.joints.plain_joints',
        'kumiki.joints.basic_joints',
        'kumiki.joints.mortise_and_tenon_joint',
        'kumiki.joints.japanese_joints',
        'kumiki.patternbook',
        'kumiki.librarian',
        'patterns',  # Reload the patterns package
        'giraffe_render_freecad',
    ]
    
    # Re-import all modules in dependency order
    for module_name in modules_to_reload:
        try:
            # Use __import__ to load the module fresh
            importlib.import_module(module_name)
        except Exception as e:
            print(f"  ⚠ Error reloading {module_name}: {e}")
    
    print("\nModule reload complete.\n")
    
    # Create the anthology pattern book after reload
    global ANTHOLOGY_PATTERN_BOOK
    print("="*70)
    print("Creating Anthology PatternBook...")
    print("="*70)
    ANTHOLOGY_PATTERN_BOOK = create_anthology_pattern_book()
    print()


def render_from_patternbook():
    """
    Unified render function that uses the Anthology PatternBook.
    
    Renders either a single pattern or a group of patterns based on configuration.
    """
    from giraffe_render_freecad import render_frame, render_csg_shape, clear_document, get_active_document
    from kumiki.rule import m
    from kumiki.timber import Frame
    
    print("="*70)
    print("Kumiki FreeCAD - PatternBook Renderer")
    print("="*70)
    print()
    
    # Clear document first
    print("Clearing FreeCAD document...")
    clear_document()
    print()
    
    if RENDER_TYPE == 'pattern':
        # Render a single pattern
        print(f"Rendering pattern: '{PATTERN_NAME}'")
        print()
        
        # Check if pattern exists
        if PATTERN_NAME not in ANTHOLOGY_PATTERN_BOOK.list_patterns():
            print(f"ERROR: Pattern '{PATTERN_NAME}' not found!")
            print(f"Available patterns:")
            for group in sorted(ANTHOLOGY_PATTERN_BOOK.list_groups()):
                patterns = ANTHOLOGY_PATTERN_BOOK.get_patterns_in_group(group)
                print(f"  {group}: {', '.join(patterns)}")
            return
        
        # Raise the pattern
        result = ANTHOLOGY_PATTERN_BOOK.raise_pattern(PATTERN_NAME)
        
        # Render based on type
        if isinstance(result, Frame):
            print(f"Frame: {result.name}")
            print(f"  Timbers: {len(result.cut_timbers)}")
            print(f"  Accessories: {len(result.accessories)}")
            print()
            
            print("Rendering to FreeCAD...")
            success_count = render_frame(result)
            print(f"Successfully rendered {success_count}/{len(result.cut_timbers)} timbers")
            if result.accessories:
                print(f"Successfully rendered {len(result.accessories)} accessories")
        else:
            # CSG object
            print(f"CSG Type: {type(result).__name__}")
            print()
            
            print("Rendering CSG to FreeCAD...")
            doc = get_active_document()
            if not doc:
                print("ERROR: Could not get active document")
                return
            
            try:
                shape = render_csg_shape(result, timber=None, infinite_extent=10.0)
                if shape:
                    obj = doc.addObject("Part::Feature", f"CSG_{PATTERN_NAME}")
                    obj.Shape = shape
                    doc.recompute()
                    print("Successfully rendered CSG object")
                else:
                    print("ERROR: Failed to create shape")
            except Exception as e:
                print(f"ERROR during rendering: {e}")
                import traceback
                traceback.print_exc()
    
    elif RENDER_TYPE == 'group':
        # Render a group of patterns
        print(f"Rendering pattern group: '{GROUP_NAME}'")
        print(f"Separation distance: {SEPARATION_DISTANCE_METERS}m")
        print()
        
        # Check if group exists
        if GROUP_NAME not in ANTHOLOGY_PATTERN_BOOK.list_groups():
            print(f"ERROR: Group '{GROUP_NAME}' not found!")
            print(f"Available groups: {', '.join(sorted(ANTHOLOGY_PATTERN_BOOK.list_groups()))}")
            return
        
        # Get patterns in group
        patterns_in_group = ANTHOLOGY_PATTERN_BOOK.get_patterns_in_group(GROUP_NAME)
        print(f"Patterns in group: {', '.join(patterns_in_group)}")
        print()
        
        # Raise the group
        result = ANTHOLOGY_PATTERN_BOOK.raise_pattern_group(GROUP_NAME, separation_distance=m(SEPARATION_DISTANCE_METERS))
        
        # Result is always a Frame or list of CSG objects
        if isinstance(result, Frame):
            print(f"Combined frame: {result.name}")
            print(f"  Total timbers: {len(result.cut_timbers)}")
            print(f"  Total accessories: {len(result.accessories)}")
            print()
            
            print("Rendering to FreeCAD...")
            success_count = render_frame(result)
            print(f"Successfully rendered {success_count}/{len(result.cut_timbers)} timbers")
            if result.accessories:
                print(f"Successfully rendered {len(result.accessories)} accessories")
        else:
            # List of CSG objects
            print(f"Number of CSG objects: {len(result)}")
            print()
            
            print("Rendering CSG objects to FreeCAD...")
            doc = get_active_document()
            if not doc:
                print("ERROR: Could not get active document")
                return
            
            success_count = 0
            for i, csg in enumerate(result):
                try:
                    shape = render_csg_shape(csg, timber=None, infinite_extent=10.0)
                    if shape:
                        obj = doc.addObject("Part::Feature", f"CSG_{i}")
                        obj.Shape = shape
                        success_count += 1
                except Exception as e:
                    print(f"WARNING: Failed to render CSG {i}: {e}")
            
            doc.recompute()
            print(f"Successfully rendered {success_count}/{len(result)} CSG objects")
    
    else:
        print(f"ERROR: Invalid RENDER_TYPE '{RENDER_TYPE}'")
        print("Must be 'pattern' or 'group'")
        return
    
    print()
    print("="*70)
    print("Rendering Complete!")
    print("="*70)
    print()
    print("Tips:")
    print("  - Use View → Standard Views to change perspective")
    print("  - Check the Model tree on the left to see all components")
    print("  - Edit configuration variables at the top of run_examples.py to change what renders")
    print()
    print(f"Available groups: {', '.join(sorted(ANTHOLOGY_PATTERN_BOOK.list_groups()))}")


# All rendering is now done through render_from_patternbook()
# Old individual render functions have been removed


def main():
    """Main function - reload modules and render using PatternBook."""
    # Reload all modules first
    reload_all_modules()
    
    # Render using the unified PatternBook approach
    render_from_patternbook()


# Run when executed
if __name__ == "__main__":
    main()
else:
    # If imported as a module, also run main
    main()

