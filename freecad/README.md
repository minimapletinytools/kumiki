# FreeCAD Example Scripts

This directory contains example scripts for rendering Kumiki models in FreeCAD.

## Quick Start

### Main Examples Runner (Recommended)
```python
# In FreeCAD: Macro → Macros → run_examples.py → Execute
```

The main runner provides access to **all examples** including CSG tests with automatic module reloading.

### Alternative: Standalone CSG Test
```python
# In FreeCAD: Macro → Macros → test_csg.py → Execute
```

You can also run CSG tests standalone, but it's easier to use `run_examples.py` with `EXAMPLE_TO_RENDER = 'csg'`.

## Why Use These Scripts?

Both scripts provide automatic module reloading:

✅ **No FreeCAD restart needed** - Make code changes and re-run the macro  
✅ **Reloads all modules** - Kumiki modules, renderers, and examples  
✅ **Saves development time** - Instant feedback on code changes

### Without Module Reloading
❌ Must restart FreeCAD after every code change  
❌ Python module caching prevents updates from being picked up  
❌ Slow development cycle

## File Structure

### Example Scripts
- **`run_examples.py`** - Main examples runner with module reload (USE THIS!)
  - Basic joints examples
  - Mortise and tenon examples
  - Oscar's Shed (complete structure)
  - CSG operation tests
- **`test_csg.py`** - Standalone CSG tests (optional, can also run via `run_examples.py`)

### Renderer
- **`giraffe_render_freecad.py`** - FreeCAD rendering engine for Kumiki

## Usage

### Method 1: FreeCAD GUI (Recommended)

1. Open FreeCAD
2. Go to **Macro → Macros...**
3. Navigate to this directory (`freecad/`)
4. Select `run_examples.py`
5. Click **Execute**

**Choosing Which Example to Render:**
- Edit `run_examples.py`
- Change the `EXAMPLE_TO_RENDER` variable at the top:
  - `'plain_joints'` - All plain joint types
  - `'mortise_and_tenon'` - Mortise and tenon joints with pegs
  - `'oscar_shed'` - Complete 8ft x 4ft timber frame shed
  - `'csg'` - CSG operation tests (also edit `CSG_EXAMPLE_TO_RENDER` for specific test)

**Making Changes:**
- Edit your code in any Kumiki module
- Re-run the same macro in FreeCAD
- Changes are automatically reloaded!

### Method 2: Command Line

```bash
# From the freecad/ directory
freecad run_examples.py
# or
freecad test_csg.py
```

## Available Examples

### 1. Plain Joints (`plain_joints`)
Demonstrates all basic joint types:
- Miter Joint (67°)
- Miter Joint (Face Aligned)
- Butt Joint
- Splice Joint
- House Joint

Examples are spaced 2m apart along the X axis.

### 2. Mortise and Tenon (`mortise_and_tenon`)
Shows mortise and tenon joints with accessories:
- Various tenon sizes and configurations
- Pegs (square and round)
- Through mortises
- Offset tenons

Configure which variants to render in `patterns/mortise_and_tenon_joint_examples.py`.

### 3. Oscar's Shed (`oscar_shed`)
Complete timber frame structure (8ft x 4ft):
- 4 mudsills with miter joints at corners
- 6 posts with mortise & tenon joints
- Side girts
- Front girt with mortise & tenon joints (including pegs) and splice joint
- Top plates with rafter pockets
- 3 joists
- 5 rafters

### 4. CSG Tests (`csg`)
Simple geometric tests for CSG operations:
- `'cube_cutout'` - Box with a smaller box cut out
- `'halfspace_cut'` - Box cut by a half-plane
- `'positioned_cube'` - Box positioned away from origin
- `'union_cubes'` - Two boxes unioned together
- `'hexagon_extrusion'` - Hexagonal prism

Edit `CSG_EXAMPLE_TO_RENDER` in `run_examples.py` to choose which test to run.

**Alternative:** You can also run `test_csg.py` standalone with its own `EXAMPLE_TO_RENDER` variable.

## What Gets Reloaded

The scripts reload modules in dependency order:

1. `kumiki.rule` - Core math/orientation
2. `kumiki.footprint` - 2D footprints
3. `kumiki.cutcsg` - CSG operations
4. `kumiki.timber` - Timber data structures
5. `kumiki.construction` - Construction functions
6. `kumiki.joints.plain_joints` - Plain joint functions
7. `kumiki.joints.mortise_and_tenon_joint` - Mortise & tenon functions
8. `giraffe` - Main API module
9. `giraffe_render_freecad` - FreeCAD renderer
10. `patterns.*` - All pattern modules

## Troubleshooting

**Import Errors:**
- Make sure you're running from the `freecad/` directory
- Check that the parent directory contains `kumiki/` and `patterns/`

**Module Not Reloading:**
- Check the console output to see which modules were reloaded
- If a module shows "not loaded yet", it will be imported fresh

**FreeCAD Crashes:**
- Some changes (like dataclass structure changes) may still require a FreeCAD restart
- For most code changes, the module reload should work fine

**Wrong Example Rendering:**
- Check the `EXAMPLE_TO_RENDER` variable at the top of `run_examples.py`
- Available options are printed if you specify an invalid example

## Output Example

```
======================================================================
Kumiki FreeCAD - Examples Runner
======================================================================

Reloading all Kumiki modules...
  ✓ Reloaded kumiki.rule
  ✓ Reloaded kumiki.timber
  ✓ Reloaded kumiki.construction
  ✓ Reloaded kumiki.joints.mortise_and_tenon_joint
  ✓ Reloaded giraffe_render_freecad
  ✓ Reloaded patterns.structures.oscarshed

Module reload complete.

Running example: oscar_shed

============================================================
Kumiki FreeCAD - Oscar's Shed
============================================================

Creating Oscar's Shed structure...
Total timbers created: 24

Rendering timbers in FreeCAD...
Successfully rendered 24/24 timbers

============================================================
Rendering Complete!
Successfully rendered 24/24 timbers
============================================================
```

## Tips

- Use **View → Standard Views** to change perspective
- Press **V** then **0** to view from front
- Press **V** then **2** to view from top
- Use middle mouse button to rotate view
- Use scroll wheel to zoom
- Check the **Model tree** on the left to see all components
- Individual timbers and cuts are organized in the tree for easy inspection
