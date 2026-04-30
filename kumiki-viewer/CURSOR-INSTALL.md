# Installing Horsey Viewer in Cursor

Cursor supports VSCode extensions since it's built on VSCode, but there are a few ways to use the extension:

## Option 1: Direct Installation (Easiest)

Since the extension is already in your project, you can install it directly:

```bash
cd /Users/peter.lu/kitchen/faucet/giraffeCAD-proto/horsey-viewer

# For macOS/Linux
mkdir -p ~/.vscode/extensions/horsey-viewer
cp -r . ~/.vscode/extensions/horsey-viewer/

# Also copy to Cursor's extensions directory
mkdir -p ~/.cursor/extensions/horsey-viewer
cp -r . ~/.cursor/extensions/horsey-viewer/
```

Then **reload Cursor** (Cmd+Shift+P → "Developer: Reload Window")

## Option 2: Development Mode (Testing)

1. **Open the `horsey-viewer` folder** as the workspace in Cursor:
   ```bash
   cd /Users/peter.lu/kitchen/faucet/giraffeCAD-proto/horsey-viewer
   cursor .
   ```

2. **Press F5** or go to **Run and Debug** sidebar (or Cmd+Shift+D)

3. Click **"Run Extension"**

4. A new Cursor/VSCode window will open with the extension loaded

5. In that new window, open your test file and run "Render Horsey"

## Option 3: Test Without Installing

You can also test the extension functionality without installing it as an extension:

```bash
cd /Users/peter.lu/kitchen/faucet/giraffeCAD-proto

# Test the runner directly
venv/bin/python horsey-viewer/runner.py horsey-viewer/test-frame.py
```

This will output the JSON that would be displayed in the webview.

## Quick Test Command

Once installed, test it works:

1. Open `horsey-viewer/test-frame.py` in Cursor
2. Press `Cmd+Shift+P` (Command Palette)
3. Type "Render Horsey"
4. Select the command
5. A new panel should open showing your frame!

## Troubleshooting

**Command not found**
- Try reloading Cursor: Cmd+Shift+P → "Developer: Reload Window"
- Check the extension is in the right directory

**Extension not loading in F5 mode**
- Make sure you opened the `horsey-viewer` directory itself, not the parent project
- Check the Output panel for errors: View → Output → Select "Extension Host"

**Python errors**
- The extension uses `venv/bin/python` from your project root
- Make sure your venv has all dependencies installed

## Verify Installation

After installation, you can verify the extension is loaded:

1. Cmd+Shift+P → "Developer: Show Running Extensions"
2. Look for "Horsey Viewer" in the list

Or check your extensions folder:
```bash
# Check if files are there
ls -la ~/.cursor/extensions/horsey-viewer/
```
