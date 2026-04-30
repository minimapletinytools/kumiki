# Kumiki Fusion 360 Integration

This directory contains a complete, self-contained Fusion 360 script for rendering timber frame structures created with Kumiki.

## QuickStart

To render the example in Autodesk Fusion 360:

#### 1. Setup Fusion 360 Script Environment

1. Navigate to the `fusion360/` directory in the project
2. Install local dependencies for Fusion 360's isolated Python environment:

```bash
cd fusion360
pip install --target libs sympy
```

#### 2. Add Script to Fusion 360

1. Open Autodesk Fusion 360 and open an assembly project (not a design project)
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

