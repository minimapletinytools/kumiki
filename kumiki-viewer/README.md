# Kumiki Viewer

Kumiki Viewer is a VS Code extension that renders Kumiki frames from Python modules into an interactive webview.

It is designed for two workflows:

- Local Kumiki development checkouts (repo root contains `kumiki/`)
- Installed-package projects (project root contains `.kumiki.yaml`)

## What It Does

- Renders the currently open Python file with the command **Render Kumiki**
- Watches files and refreshes the viewer when source changes
- Browses shipped and local pattern libraries with **Browse Patterns**
- Opens pattern results in separate tabs backed by one shared runner process
- Generates triangle mesh geometry in Python and streams JSON to the webview

## Runtime Contract for Python Files

When Kumiki imports a Python module, it uses reflection to resolve what to render in this order:

1. Module-level `example`
2. `build_frame()` function
3. Module-level `patternbook`

`example` may be either:

- A frame-like value
- A callable returning a frame-like value
- A patternbook

If no supported entry point exists, the viewer returns an error.

## First Run: Automatic Python Environment Setup

On first render in a project, Kumiki bootstraps a project-local environment automatically:

1. Finds project root by walking upward from the target file
2. Creates `.venv` if needed
3. Checks for required viewer dependencies (`sympy`, `numpy`, `trimesh`, `manifold3d`)
4. Installs dependencies when missing:
   - Local dev checkout: `pip install -e <projectRoot>[viewer]`
   - Non-local project: `pip install kumiki[viewer]`
5. Writes `.kumiki/project.yaml` with selected Python path and setup metadata

On later runs, Kumiki reuses the configured interpreter from `.kumiki/project.yaml` when available.

## Commands

- `Render Kumiki` (`kumiki-viewer.renderKumiki`)
- `Browse Patterns` (`kumiki-viewer.browsePatterns`)
- `Unload Pattern Viewer` (`kumiki-viewer.unloadPattern`)

Open the command palette and run any of the commands above.

## Pattern Browsing

Kumiki scans two sources:

- Shipped patterns bundled with `kumiki`
- Local project patterns in `<projectRoot>/patterns`

Pattern sessions are loaded into dedicated slots in the runner and displayed as separate viewer panels.

## Install and Run (Development)

From this folder:

```bash
npm install
```

Then in VS Code:

1. Open the `kumiki-viewer` folder
2. Press `F5` (Run Extension)
3. In the Extension Development Host window, open a Python frame file
4. Run **Render Kumiki**

## Quick Example

```python
from kumiki.timber import *
from kumiki.construction import *

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

From `kumiki-viewer/`:

```bash
npm run test:unit
npm run test:runner
npm run test:ext
npm run test:all
```

Screenshot options for extension smoke tests:

- `KUMIKI_EXT_SCREENSHOT_MODE=never`
- `KUMIKI_EXT_SCREENSHOT_MODE=always`
- `KUMIKI_EXT_SCREENSHOT_MODE=on-failure`
- `KUMIKI_EXT_SCREENSHOT_DIR=/custom/path`

## Troubleshooting

### Render command does nothing

- Confirm the active editor is a Python file
- Save the file and rerun **Render Kumiki**
- Open the `Kumiki Viewer` output channel for logs

### Missing Python dependencies

- Run **Render Kumiki** once and let auto bootstrap finish
- If your interpreter is non-standard, set `python_path` in `.kumiki/project.yaml` to a valid Python executable

### Unsupported module shape

Expose one of:

- `example`
- `build_frame()`
- `patternbook`

### Pattern list is stale

Use the pattern browser refresh action (rescan) so modules are re-imported.
