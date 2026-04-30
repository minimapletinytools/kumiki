"""
FreeCAD test script for CSG rendering.

This script tests the FreeCAD CSG renderer with simple geometric examples
to verify that CSG operations (Difference, Union, HalfSpace cuts) work correctly.

Usage:
    1. Open FreeCAD
    2. Macro -> Macros... -> Select this file -> Execute
    3. Change EXAMPLE_TO_RENDER to test different examples
"""

import sys
import os
import importlib

# Add Kumiki to path
script_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Also add the current directory (freecad/) to path for FreeCAD macro mode
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

print("="*70)
print("Kumiki FreeCAD - CSG Test")
print("="*70)
print("\nReloading all Kumiki modules...")

# List of modules to reload in dependency order
modules_to_reload = [
    'kumiki.rule',
    'kumiki.footprint',
    'kumiki.cutcsg',
    'kumiki.timber',
    'kumiki.construction',
    'giraffe',
    'giraffe_render_freecad',
    'patterns.CSG_debug_examples',
]

for module_name in modules_to_reload:
    if module_name in sys.modules:
        try:
            importlib.reload(sys.modules[module_name])
            print(f"  ✓ Reloaded {module_name}")
        except Exception as e:
            print(f"  ⚠ Error reloading {module_name}: {e}")
    else:
        print(f"  - {module_name} not loaded yet")

print("\nModule reload complete.\n")

# Import after reloading
from giraffe_render_freecad import render_csg_shape, clear_document, get_active_document
from patterns.CSG_debug_examples import EXAMPLES, get_example


# ============================================================================
# CONFIGURATION: Change this to test different examples
# ============================================================================
EXAMPLE_TO_RENDER = 'hexagon_extrusion'  # Options: 'cube_cutout', 'halfspace_cut', 'positioned_cube', 'union_cubes', 'hexagon_extrusion'


def render_csg_example(example_key: str):
    """
    Render a CSG example in FreeCAD.
    
    Args:
        example_key: Key from EXAMPLES dictionary
    """
    # Get example info
    if example_key not in EXAMPLES:
        print(f"ERROR: Unknown example '{example_key}'")
        print(f"Available examples: {list(EXAMPLES.keys())}")
        return
    
    example_info = EXAMPLES[example_key]
    print(f"Example: {example_info['name']}")
    print(f"Description: {example_info['description']}")
    print()
    
    # Get CSG object
    csg = get_example(example_key)
    print(f"CSG Type: {type(csg).__name__}")
    print()
    
    # Clear document
    print("Clearing FreeCAD document...")
    clear_document()
    print("Document cleared")
    print()
    
    # Get document
    doc = get_active_document()
    if not doc:
        print("ERROR: Could not get active document")
        return
    
    # Render CSG
    print("Rendering CSG...")
    try:
        # Use a reasonable extent for infinite geometry (10m = 10000mm)
        shape = render_csg_shape(csg, timber=None, infinite_extent=10.0)
        
        if shape is None:
            print("ERROR: Failed to create shape")
            return
        
        # Create FreeCAD object
        obj = doc.addObject("Part::Feature", f"CSG_{example_key}")
        obj.Shape = shape
        
        # Print bounding box info
        bbox = shape.BoundBox
        print(f"Shape created successfully!")
        print(f"Bounding box (mm):")
        print(f"  X: [{bbox.XMin:.1f}, {bbox.XMax:.1f}]  (width: {bbox.XLength:.1f})")
        print(f"  Y: [{bbox.YMin:.1f}, {bbox.YMax:.1f}]  (depth: {bbox.YLength:.1f})")
        print(f"  Z: [{bbox.ZMin:.1f}, {bbox.ZMax:.1f}]  (height: {bbox.ZLength:.1f})")
        print()
        
        doc.recompute()
        
    except Exception as e:
        print(f"ERROR during rendering: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("=" * 60)
    print("Rendering Complete!")
    print("=" * 60)
    print()
    print("Tips:")
    print("  - Use View -> Standard Views to change perspective")
    print("  - Check the bounding box dimensions to verify size")
    print("  - For cuts, verify that material was removed")
    print()
    print(f"To test another example, edit EXAMPLE_TO_RENDER in test_csg.py")
    print(f"Available: {', '.join(EXAMPLES.keys())}")


if __name__ == "__main__":
    render_csg_example(EXAMPLE_TO_RENDER)

