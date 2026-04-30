# Horsey Viewer

Horsey Viewer is a VS Code extension that renders GiraffeCAD frames from Python modules into an interactive webview.

It is designed for two workflows:

- Local GiraffeCAD development checkouts (repo root contains `giraffecad/`)
- Installed-package projects (project root contains `.giraffe.yaml`)

## What It Does

- Renders the currently open Python file with the command **Render Horsey**
- Watches files and refreshes the viewer when source changes
- Browses shipped and local pattern libraries with **Browse Patterns**
- Opens pattern results in separate tabs backed by one shared runner process
- Generates triangle mesh geometry in Python and streams JSON to the webview

## Runtime Contract for Python Files

When Horsey imports a Python module, it uses reflection to resolve what to render in this order:

1. Module-level `example`
2. `build_frame()` function
3. Module-level `patternbook`

`example` may be either:

- A frame-like value
- A callable returning a frame-like value
- A patternbook

If no supported entry point exists, the viewer returns an error.

## First Run: Automatic Python Environment Setup

On first render in a project, Horsey bootstraps a project-local environment automatically:

1. Finds project root by walking upward from the target file
2. Creates `.venv` if needed
3. Checks for required viewer dependencies (`sympy`, `numpy`, `trimesh`, `manifold3d`)
4. Installs dependencies when missing:
   - Local dev checkout: `pip install -e <projectRoot>[viewer]`
   - Non-local project: `pip install giraffecad[viewer]`
5. Writes `.horsey/project.yaml` with selected Python path and setup metadata

On later runs, Horsey reuses the configured interpreter from `.horsey/project.yaml` when available.

## Commands

- `Render Horsey` (`horsey-viewer.renderHorsey`)
- `Browse Patterns` (`horsey-viewer.browsePatterns`)
- `Unload Pattern Viewer` (`horsey-viewer.unloadPattern`)

Open the command palette and run any of the commands above.

## Pattern Browsing

Horsey scans two sources:

- Shipped patterns bundled with `giraffecad`
- Local project patterns in `<projectRoot>/patterns`

Pattern sessions are loaded into dedicated slots in the runner and displayed as separate viewer panels.

## Install and Run (Development)

From this folder:

```bash
npm install
```

Then in VS Code:

1. Open the `horsey-viewer` folder
2. Press `F5` (Run Extension)
3. In the Extension Development Host window, open a Python frame file
4. Run **Render Horsey**

## Quick Example

```python
from giraffecad.timber import *
from giraffecad.construction import *

def build_frame():
    timber = create_timber(
        bottom_position=create_v3(0, 0, 0),
        length=mm(1000),
        size=create_v2(mm(100), mm(100)),
        length_direction=create_v3(0, 0, 1),
        width_direction=create_v3(1, 0, 0),
        name="Demo Timber",
    )
    return Frame.from_joints([], [timber], name="Demo Frame")
```

## How The System Is Structured

- `extension.js`: command registration and session orchestration
- `frame-view-session.js`: panel lifecycle, refresh pipeline, file watching, webview messaging
- `runner-session.js`: Python process lifecycle and environment bootstrap
- `runner.py`: persistent stdio protocol server, module loading, pattern discovery, geometry build
- `webview/`: UI app and viewer components

The extension side is responsible for lifecycle/orchestration. The runner side is responsible for Python import, frame resolution, and geometry generation.

## Testing

From `horsey-viewer/`:

```bash
npm run test:unit
npm run test:runner
npm run test:ext
npm run test:all
```

Screenshot options for extension smoke tests:

- `HORSEY_EXT_SCREENSHOT_MODE=never`
- `HORSEY_EXT_SCREENSHOT_MODE=always`
- `HORSEY_EXT_SCREENSHOT_MODE=on-failure`
- `HORSEY_EXT_SCREENSHOT_DIR=/custom/path`

## Troubleshooting

### Render command does nothing

- Confirm the active editor is a Python file
- Save the file and rerun **Render Horsey**
- Open the `Horsey Viewer` output channel for logs

### Missing Python dependencies

- Run **Render Horsey** once and let auto bootstrap finish
- If your interpreter is non-standard, set `python_path` in `.horsey/project.yaml` to a valid Python executable

### Unsupported module shape

Expose one of:

- `example`
- `build_frame()`
- `patternbook`

### Pattern list is stale

Use the pattern browser refresh action (rescan) so modules are re-imported.
