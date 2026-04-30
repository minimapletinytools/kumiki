"""
Kumiki Fusion 360 Examples Runner - automatically reloads all modules.

This script provides multiple example rendering functions with automatic module reloading,
so you can make changes to your code and re-run this script without restarting Fusion 360.

TO CHANGE WHICH EXAMPLE RENDERS:
Edit the EXAMPLE_TO_RENDER variable below (around line 44).
"""

import traceback
import adsk.core
import adsk.fusion
import sys
import os

# Add the local libs directory, current script directory, and parent directory to sys.path
script_dir = os.path.dirname(os.path.realpath(__file__))
libs_dir = os.path.join(script_dir, 'libs')
parent_dir = os.path.dirname(script_dir)

# Add paths in order of priority
if libs_dir not in sys.path:
    sys.path.insert(0, libs_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


# ============================================================================
# CONFIGURATION: Change this to render different examples
# ============================================================================
#EXAMPLE_TO_RENDER = 'plain_joints' 
#EXAMPLE_TO_RENDER = 'mortise_and_tenon'
#EXAMPLE_TO_RENDER = 'gooseneck'
EXAMPLE_TO_RENDER = 'oscar_shed'
#EXAMPLE_TO_RENDER = 'irrational_angles'
#EXAMPLE_TO_RENDER = 'csg'

# CSG Configuration (only used when EXAMPLE_TO_RENDER = 'csg')
CSG_EXAMPLE_TO_RENDER = 'cube_cutout'  # Options: 'cube_cutout', 'halfspace_cut', 'positioned_cube', 'lap_cut_timber', 'union_cubes', 'hexagon_extrusion', 'gooseneck_profile', 'shoulder_notch'

# Anthology PatternBook - will be initialized after module reload
ANTHOLOGY_PATTERN_BOOK = None

# DO NOT import Kumiki modules here at the top level!
# They will be imported AFTER reload inside the render functions.
# Importing here would create references to old classes that become stale after reload.
try:
    # Only test that sympy is available (it won't be reloaded)
    import sympy
    
    import_success = True
    import_error = None
except ImportError as e:
    # Handle import error gracefully for when running in Fusion 360
    import_success = False
    import_error = str(e)

# Initialize the global variables for the Application and UserInterface objects.
app = adsk.core.Application.get()
ui = app.userInterface


def create_anthology_pattern_book():
    """
    Create an anthology PatternBook containing all patterns from all example files.
    
    Returns:
        PatternBook: A single PatternBook with all patterns from all examples
    """
    from kumiki.patternbook import PatternBook
    from patterns.basic_joints_examples import create_basic_joints_patternbook
    from patterns.mortise_and_tenon_joint_examples import create_mortise_and_tenon_patternbook
    from patterns.construction_examples import create_construction_patternbook
    from patterns.structures.kumiki_example import create_kumiki_patternbook
    from patterns.structures.oscarshed import create_oscar_shed_patternbook
    from patterns.japanese_joints_example import create_japanese_joints_patternbook
    from patterns.irrational_angles_example import create_irrational_angles_patternbook
    from patterns.CSG_debug_examples import create_csg_examples_patternbook
    from patterns.patternbook_example import create_patternbook_example_patternbook
    
    # Create all individual pattern books
    books = [
        create_basic_joints_patternbook(),
        create_mortise_and_tenon_patternbook(),
        create_construction_patternbook(),
        create_kumiki_patternbook(),
        create_oscar_shed_patternbook(),
        create_japanese_joints_patternbook(),
        create_irrational_angles_patternbook(),
        create_csg_examples_patternbook(),
        create_patternbook_example_patternbook(),
    ]
    
    # Merge them all into one anthology book
    anthology_book = PatternBook.merge_multiple(books)
    
    print(f"Anthology PatternBook created with {len(anthology_book.list_patterns())} patterns")
    print(f"Available groups: {', '.join(anthology_book.list_groups())}")
    
    return anthology_book


def reload_all_modules():
    """Reload all Kumiki modules in dependency order."""
    print("="*70)
    print("Kumiki Fusion 360 - Examples Runner")
    print("="*70)
    print("\nReloading all Kumiki modules...")
    app.log("Reloading all Kumiki modules...")
    
    import importlib
    
    # AGGRESSIVE MODULE CLEANUP: Delete ALL Kumiki-related modules
    # This ensures no stale class references remain after reload
    modules_to_delete = []
    for module_name in list(sys.modules.keys()):
        # Delete any module that starts with our project prefixes
        if (module_name.startswith('kumiki') or 
            module_name.startswith('patterns') or 
            module_name == 'giraffe' or
            module_name.startswith('giraffe.') or
            module_name == 'giraffe_render_fusion360'):
            modules_to_delete.append(module_name)
    
    if app:
        app.log(f"  Deleting {len(modules_to_delete)} cached modules...")
    
    for module_name in modules_to_delete:
        del sys.modules[module_name]
    
    # List of modules to reload in dependency order
    modules_to_reload = [
        'kumiki',  # Reload the package itself first
        'kumiki.rule',
        'kumiki.footprint',
        'kumiki.cutcsg',
        'kumiki.timber',
        'kumiki.construction',
        'kumiki.rendering_utils',
        'kumiki.joints.joint_shavings',
        'kumiki.measuring',
        'kumiki.joints.plain_joints',
        'kumiki.joints.mortise_and_tenon_joint',
        'kumiki.joints.japanese_joints',
        'kumiki.patternbook',
        'giraffe',
        'patterns',  # Reload the patterns package
        'giraffe_render_fusion360',  # Add this so the rendering module itself gets reloaded
        'patterns.mortise_and_tenon_joint_examples',
        'patterns.basic_joints_examples',
        'patterns.structures.kumiki_example',
        'patterns.structures.oscarshed',
        'patterns.japanese_joints_example',
        'patterns.irrational_angles_example',
        'patterns.CSG_debug_examples',
        'patterns.patternbook_example',
    ]
    
    # Re-import all modules in dependency order
    for module_name in modules_to_reload:
        try:
            # Use __import__ to load the module fresh
            importlib.import_module(module_name)
        except Exception as e:
            print(f"  ⚠ Error reloading {module_name}: {e}")
            app.log(f"  ⚠ Error reloading {module_name}: {e}")
    
    print("\nModule reload complete.\n")
    app.log("Module reload complete.")
    
    # Create the master pattern book after reload
    global ANTHOLOGY_PATTERN_BOOK
    print("="*70)
    print("Creating Anthology PatternBook...")
    print("="*70)
    app.log("Creating Anthology PatternBook...")
    ANTHOLOGY_PATTERN_BOOK = create_anthology_pattern_book()
    print()


def render_plain_joints():
    """Render all plain joint examples using anthology PatternBook."""
    from giraffe_render_fusion360 import render_frame, clear_design
    from kumiki.rule import m
    
    print("="*60)
    print("Kumiki Fusion 360 - All Plain Joints")
    print("="*60)
    app.log("🦒 GIRAFFETEST: PLAIN JOINTS 🦒")
    
    # Use anthology pattern book
    print("\nRaising all patterns in 'plain_joints' group from anthology...")
    frame = ANTHOLOGY_PATTERN_BOOK.raise_pattern_group("plain_joints", separation_distance=m(2))
    
    print(f"Total timbers created: {len(frame.cut_timbers)}")
    
    # Clear and render
    print("\nClearing Fusion 360 design...")
    if not clear_design():
        print("Failed to prepare design - aborting rendering")
        return
    
    print("\nRendering timbers in Fusion 360...")
    success_count = render_frame(frame, "Joint")
    
    print("\n" + "="*60)
    print(f"Rendering Complete!")
    print(f"Successfully rendered {success_count}/{len(frame.cut_timbers)} timbers")
    print("="*60)
    
    ui.messageBox(
        f'Basic Joints rendering complete!\n\n' +
        f'Successfully rendered {success_count}/{len(frame.cut_timbers)} timbers',
        'Rendering Complete',
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType
    )


def render_mortise_and_tenon():
    """Render mortise and tenon joint examples with pegs using anthology PatternBook."""
    from giraffe_render_fusion360 import render_frame, clear_design
    from kumiki.rule import inches
    
    print("="*70)
    print("Kumiki Fusion 360 - Mortise and Tenon Joint Examples")
    print("="*70)
    app.log("🦒 GIRAFFETEST: MORTISE AND TENON 🦒")
    
    # Use anthology pattern book
    print("\nRaising all patterns in 'mortise_tenon' group from anthology...")
    frame = ANTHOLOGY_PATTERN_BOOK.raise_pattern_group("mortise_tenon", separation_distance=inches(72))
    
    print(f"Total timbers created: {len(frame.cut_timbers)}")
    print(f"Total accessories (pegs/wedges): {len(frame.accessories)}")
    
    # Clear and render
    print("\nClearing Fusion 360 design...")
    if not clear_design():
        print("Failed to prepare design - aborting rendering")
        return
    
    print("\nRendering timbers and accessories in Fusion 360...")
    success_count = render_frame(frame, "MortiseTenon")
    
    total_objects = len(frame.cut_timbers) + len(frame.accessories)
    print("\n" + "="*70)
    print(f"Rendering Complete!")
    print(f"Successfully rendered {success_count}/{total_objects} objects")
    print("="*70)
    
    ui.messageBox(
        f'Mortise and Tenon rendering complete!\n\n' +
        f'Successfully rendered {success_count}/{total_objects} objects\n' +
        f'({len(frame.cut_timbers)} timbers + {len(frame.accessories)} accessories)',
        'Rendering Complete',
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType
    )


def render_gooseneck():
    """Render Japanese gooseneck joint example using anthology PatternBook."""
    from giraffe_render_fusion360 import render_frame, clear_design
    
    print("="*70)
    print("Kumiki Fusion 360 - Japanese Gooseneck Joint")
    print("="*70)
    app.log("🦒 GIRAFFETEST: JAPANESE GOOSENECK 🦒")
    
    # Use anthology pattern book
    print("\nRaising 'gooseneck_simple' pattern from anthology...")
    frame = ANTHOLOGY_PATTERN_BOOK.raise_pattern("gooseneck_simple")
    
    print(f"Total timbers created: {len(frame.cut_timbers)}")
    
    # Clear and render
    print("\nClearing Fusion 360 design...")
    if not clear_design():
        print("Failed to prepare design - aborting rendering")
        return
    
    print("\nRendering timbers in Fusion 360...")
    success_count = render_frame(frame, "Gooseneck")
    
    print("\n" + "="*70)
    print(f"Rendering Complete!")
    print(f"Successfully rendered {success_count}/{len(frame.cut_timbers)} timbers")
    print("="*70)
    
    ui.messageBox(
        f'Japanese Gooseneck Joint rendering complete!\n\n' +
        f'Successfully rendered {success_count}/{len(frame.cut_timbers)} timbers\n\n' +
        f'Traditional Lapped Gooseneck Joint (腰掛鎌継ぎ)',
        'Rendering Complete',
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType
    )


def render_oscar_shed():
    """Render Oscar's Shed using anthology PatternBook."""
    from giraffe_render_fusion360 import render_frame, clear_design
    
    print("="*60)
    print("Kumiki Fusion 360 - Oscar's Shed")
    print("="*60)
    app.log("🦒 GIRAFFETEST: OSCAR'S SHED 🦒")
    
    # Use anthology pattern book
    print("\nRaising 'oscar_shed' pattern from anthology...")
    frame = ANTHOLOGY_PATTERN_BOOK.raise_pattern("oscar_shed")
    
    print(f"Total timbers created: {len(frame.cut_timbers)}")
    print(f"Total accessories (pegs): {len(frame.accessories)}")
    
    # Print bounding box information
    min_corner, max_corner = frame.get_bounding_box()
    size = max_corner - min_corner
    print(f"\nFrame bounding box size: {float(size[0]):.2f}\" x {float(size[1]):.2f}\" x {float(size[2]):.2f}\"")
    print(f"  X: {float(min_corner[0]):.2f}\" to {float(max_corner[0]):.2f}\"")
    print(f"  Y: {float(min_corner[1]):.2f}\" to {float(max_corner[1]):.2f}\"")
    print(f"  Z: {float(min_corner[2]):.2f}\" to {float(max_corner[2]):.2f}\"")
    
    # Clear and render
    print("\nClearing Fusion 360 design...")
    if not clear_design():
        print("Failed to prepare design - aborting rendering")
        return
    
    print("\nRendering timbers and accessories in Fusion 360...")
    success_count = render_frame(frame, "OscarShed_Timber")
    
    total_objects = len(frame.cut_timbers) + len(frame.accessories)
    print("\n" + "="*60)
    print(f"Rendering Complete!")
    print(f"Successfully rendered {success_count}/{total_objects} objects")
    print("="*60)
    
    ui.messageBox(
        f'Oscar\'s Shed rendering complete!\n\n' +
        f'Successfully rendered {success_count}/{total_objects} objects\n' +
        f'({len(frame.cut_timbers)} timbers + {len(frame.accessories)} accessories)\n\n' +
        f'8ft x 4ft timber frame structure',
        'Rendering Complete',
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType
    )


def render_irrational_angles():
    """Render irrational angles test examples using anthology PatternBook."""
    from giraffe_render_fusion360 import render_frame, clear_design
    
    print("="*70)
    print("Kumiki Fusion 360 - Irrational Angles Test")
    print("="*70)
    app.log("🦒 GIRAFFETEST: IRRATIONAL ANGLES 🦒")
    
    # Use anthology pattern book
    print("\nRaising 'irrational_angles_test' pattern from anthology...")
    frame = ANTHOLOGY_PATTERN_BOOK.raise_pattern("irrational_angles_test")
    
    print(f"Total timbers created: {len(frame.cut_timbers)}")
    
    # Clear and render
    print("\nClearing Fusion 360 design...")
    if not clear_design():
        print("Failed to prepare design - aborting rendering")
        return
    
    print("\nRendering timbers in Fusion 360...")
    success_count = render_frame(frame, "Irrational")
    
    print("\n" + "="*70)
    print(f"Rendering Complete!")
    print(f"Successfully rendered {success_count}/{len(frame.cut_timbers)} timbers")
    print("="*70)
    
    ui.messageBox(
        f'Irrational Angles Test rendering complete!\n\n' +
        f'Successfully rendered {success_count}/{len(frame.cut_timbers)} timbers\n\n' +
        f'Tests CSG alignment at irrational angles:\n' +
        f'• 37° (arbitrary)\n' +
        f'• 45° (√2)\n' +
        f'• 60° (√3)\n' +
        f'• Golden angle (arctan(φ))',
        'Rendering Complete',
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType
    )


def render_csg():
    """Render CSG examples from anthology PatternBook."""
    from giraffe_render_fusion360 import render_csg_pattern, clear_design
    from patterns.CSG_debug_examples import EXAMPLES
    
    print("="*70)
    print("Kumiki Fusion 360 - CSG Examples")
    print("="*70)
    app.log("🦒 GIRAFFETEST: CSG EXAMPLES 🦒")
    
    # Get example info
    if CSG_EXAMPLE_TO_RENDER not in EXAMPLES:
        print(f"ERROR: Unknown example '{CSG_EXAMPLE_TO_RENDER}'")
        print(f"Available examples: {list(EXAMPLES.keys())}")
        ui.messageBox(
            f'Unknown CSG example: {CSG_EXAMPLE_TO_RENDER}\n\n' +
            f'Available: {", ".join(EXAMPLES.keys())}',
            'Error',
            adsk.core.MessageBoxButtonTypes.OKButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType
        )
        return
    
    example_info = EXAMPLES[CSG_EXAMPLE_TO_RENDER]
    print(f"Example: {example_info['name']}")
    print(f"Description: {example_info['description']}")
    
    # Use anthology pattern book
    print(f"\nRaising '{CSG_EXAMPLE_TO_RENDER}' pattern from anthology...")
    csg = ANTHOLOGY_PATTERN_BOOK.raise_pattern(CSG_EXAMPLE_TO_RENDER)
    
    # Clear design
    print("\nClearing Fusion 360 design...")
    if not clear_design():
        print("Failed to prepare design - aborting rendering")
        return
    
    # Render CSG
    print("\nRendering CSG in Fusion 360...")
    success_count = render_csg_pattern(csg, CSG_EXAMPLE_TO_RENDER)
    
    print("\n" + "="*70)
    print(f"Rendering Complete!")
    print(f"Successfully rendered CSG: {CSG_EXAMPLE_TO_RENDER}")
    print("="*70)
    
    ui.messageBox(
        f'CSG rendering complete!\n\n' +
        f'Example: {example_info["name"]}\n' +
        f'Description: {example_info["description"]}',
        'Rendering Complete',
        adsk.core.MessageBoxButtonTypes.OKButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType
    )


def run(_context: str):
    """This function is called by Fusion when the script is run."""
    try:
        # Check for import errors first
        if not import_success:
            ui.messageBox(f'Import Error: {import_error}', 'Kumiki Import Failed')
            return

        # Reload all modules
        reload_all_modules()
        
        # Dispatch to the selected example
        examples = {
            'plain_joints': render_plain_joints,
            'mortise_and_tenon': render_mortise_and_tenon,
            'gooseneck': render_gooseneck,
            'oscar_shed': render_oscar_shed,
            'irrational_angles': render_irrational_angles,
            'csg': render_csg,
        }
        
        if EXAMPLE_TO_RENDER not in examples:
            error_msg = (
                f"ERROR: Unknown example '{EXAMPLE_TO_RENDER}'\n\n" +
                f"Available examples:\n" +
                "\n".join(f"  • {name}" for name in examples.keys()) +
                "\n\nEdit EXAMPLE_TO_RENDER in giraffetest.py to change the example."
            )
            print(error_msg)
            app.log(error_msg)
            ui.messageBox(error_msg, 'Configuration Error')
            return
        
        print(f"\nRunning example: {EXAMPLE_TO_RENDER}\n")
        app.log(f"Running example: {EXAMPLE_TO_RENDER}")
        examples[EXAMPLE_TO_RENDER]()
        
        print("\n" + "="*70)
        print("To render a different example, edit EXAMPLE_TO_RENDER in giraffetest.py")
        print(f"Available: {', '.join(examples.keys())}")
        print("="*70)

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}\n\n{traceback.format_exc()}"
        print(f"❌ {error_msg}")
        app.log(f"ERROR: {error_msg}")
        ui.messageBox(f'Unexpected error:\n{str(e)}', 'Kumiki Error')


def stop(_context: str):
    """This function is called by Fusion when the script is stopped."""
    try:
        print("Kumiki script stopped")
        app.log("Kumiki script stopped")
        
    except:  #pylint:disable=bare-except
        app.log(f'Stop failed:\n{traceback.format_exc()}')
