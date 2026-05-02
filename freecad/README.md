# FreeCAD Example Scripts

This directory contains example scripts for rendering Kumiki models in FreeCAD. This functionality is not officially supported. You can always export your designs as STEP files and import them in FreeCAD.

## Quick Start

To render structures in FreeCAD (open source, free):

1. **Install FreeCAD** (version 0.19 or later)
   - Download from https://www.freecad.org/
   - Or use package manager: `brew install freecad` (macOS)

2. **Set up macro folder** (one-time setup):
   - Open FreeCAD
   - Go to **Edit** → **Preferences** → **Python** → **Macro**
   - Click **Add** under "Macro path"
   - Navigate to and select: `/path/to/kumiki-proto/freecad`
   - Click **OK**

3. **Run the renderer**:
   - Open FreeCAD
   - Go to **Macro** → **Macros...**
   - Select `render_example.py` from the list
   - Click **Execute**
   
The rendered structure will appear in FreeCAD's 3D view!