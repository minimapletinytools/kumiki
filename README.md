# HorseCoAD

HorseCoAD is a Code aided Design library for programmatically designing timber framed structures.

HorseCoAD is written as an **AI friendly** library meaning it was designed for use by AI agents.

## Setup

TODO viewer setup instructions
TODO pip package instructions

## trying out the exmaple

You've setup your tools and you're almost ready to make your first sawhorse.

But first, lets admire the one in the patterns folder

```python
from patterns.structures.kumiki_example import *
...
```

TODO finish

## your first kumiki

TODO finish

## for advanced students

TODO finish


# APPENDIX

## FreeCAD and Fusion360 usage

Rendering in FreeCAD and Fusion360 currently requires checking out the entire repo. We do not plan to work around this and support for these tools will be removed soon. 

To add your own examples, modify the respective example running file to point to your own example.

### FreeCAD Integration

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

### Fusion 360 Integration

To render the example in Autodesk Fusion 360:

#### 1. Setup Fusion 360 Script Environment

1. Navigate to the `fusion360/` directory in the project
2. Install local dependencies for Fusion 360's isolated Python environment:

```bash
cd fusion360
pip install --target libs sympy
```

#### 2. Add Script to Fusion 360

1. Open Autodesk Fusion 360
2. Go to **Design** workspace
3. Click **Utilities** → **ADD-INS** → **Scripts and Add-Ins** (or just `s` and type in "scripts and add-ins")
4. Click the **+** button next to "My Scripts"
5. Navigate to the `fusion360/` folder and select it
6. You should now see "giraffetest" in your scripts list

#### 3. Run the Script

1. Select "giraffetest" from the scripts list
2. Click **Run**
3. The script will:
   - Clear any existing design
   - Generate the sawhorse geometry using your selected example
   - Render all timbers as 3D components in Fusion 360
   - Apply proper transformations and positioning

#### 4. What You'll See

TODO
