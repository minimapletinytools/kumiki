# Installing Horsey Viewer

## Quick Install (Development Mode)

1. Open the `giraffeCAD-proto` project in VSCode

2. Press `F5` or go to **Run > Start Debugging**

   This will:
   - Open a new VSCode window with the extension loaded
   - The extension will be active in this development window

3. In the new window, open `horsey-viewer/test-frame.py`

4. Open the Command Palette (`Cmd+Shift+P` on Mac, `Ctrl+Shift+P` on Windows/Linux)

5. Type "Render Horsey" and select the command

6. A new panel should open showing the frame data!

## Install as Local Extension

To install the extension permanently in your VSCode:

### macOS / Linux

```bash
cd horsey-viewer
mkdir -p ~/.vscode/extensions/horsey-viewer
cp -r . ~/.vscode/extensions/horsey-viewer/
```

### Windows

```powershell
cd horsey-viewer
mkdir $env:USERPROFILE\.vscode\extensions\horsey-viewer
Copy-Item -Recurse -Force . $env:USERPROFILE\.vscode\extensions\horsey-viewer\
```

Then reload VSCode.

## Using the Extension

1. Create a Python file that defines a `build_frame()` function returning a `Frame` object

2. Open the file in VSCode

3. Run the **Render Horsey** command

4. The extension will:
   - Save your file
   - Run Python to import the file and call `build_frame()`
   - Display the Frame data in a new webview panel

## Requirements

- VSCode 1.60.0 or higher
- Python 3.6+
- GiraffeCAD project structure (with `giraffecad` directory)
- Virtual environment with required dependencies (`venv/bin/python`)

## Troubleshooting

**Error: "No module named 'sympy'"**
- Make sure you've activated the venv: `source venv/bin/activate`
- Or the extension will try to use `venv/bin/python` automatically

**Error: "Module does not have a 'build_frame' function"**
- Make sure your Python file has a function named `build_frame()` (not `raise()`)

**Error: "File not found"**
- Make sure the file is saved before running the command

**No output / Extension doesn't work**
- Check the VSCode Developer Tools console for errors: **Help > Toggle Developer Tools**
- Make sure you're in a Python file
