# Kigumi

Kigumi is the 3D viewer and CAD environment for [Kumiki](https://kumiki.build), an open-source programmatic CAD library for designing timber-framed structures and woodworking joinery in Python.

- **Website & Downloads:** [kumiki.build](https://kumiki.build)
- **Try in your browser:** [kumiki.build/try](https://kumiki.build/try/)
- **Documentation & API Reference:** [kumiki.build/docs](https://kumiki.build/docs/)
- **GitHub Repository:** [minimapletinytools/kumiki](https://github.com/minimapletinytools/kumiki)

## Prerequisites

To use the Kigumi VS Code extension, you need:

- **VS Code** (or Cursor / VSCodium) with the Kigumi extension installed
- **uv** or **Python** so Kigumi has something to bootstrap the Python virtual environment.
  - Preferred: install `uv` ahead of time: https://docs.astral.sh/uv/getting-started/installation/
  - Auto-bootstrap fallback: Kigumi tries `python3.13`, then `python3`/`python` (or `py -3.13`/`py -3` on Windows) and installs `uv` into a throwaway virtual environment at `.kigumi/uv-bootstrap/`

Kigumi does NOT require pre-installed packages. It handles dependency setup in a project-local virtual environment automatically.

## Initialization

Kigumi is built around the VS Code workspace (i.e. a folder) where all your Kumiki project files live.

To initialize a project, open a folder in VS Code that will be your workspace. Then open the Kigumi sidebar and click **Initialize Project**. This generates an example frame (`my_cute_frame.py`), AI agent authoring instructions (`.kigumi/docs/`), and a project settings file.

The sidebar also checks for Kumiki updates so you can update to the latest version.

The sidebar contains a project file explorer. *Click on a frame to open it in the Kigumi viewer*.

You can also use the *"Kigumi: Open Current File in Viewer"* command from the command palette (`Cmd/Ctrl + Shift + P`) to quickly open the current file.

The sidebar also contains a pattern book explorer which provides built-in examples of joints and structures you can build with Kumiki. You can view the source or duplicate any pattern into your workspace.

## Features

Once you open a frame, Kigumi renders an interactive 3D view alongside your Python code:

- **Live 3D inspection:** Select individual timbers, faces, edges, or joint features, and walk the CSG cut tree.
- **X-ray and section views:** Inspect internal mortises, tenons, pegs, wedges, and splines.
- **Parametric controls (Kiwari):** Adjust dimensions, angles, and counts live in the parameters panel.
- **2D shop drawings & measurements (beta):** View generated or coded elevation and piece drawings, add manual point-to-point measurements (`M`), and export sheets as PNG.
- **Assembly timeline (beta):** Scrub through the computed assembly/disassembly sequence to verify how joints slide together.
- **CAD export:** Export frames and timbers to STEP, STL, OBJ, and 3MF.

# Details

## Runtime Contract for Kumiki files

When Kigumi imports a Python module, it discovers functions decorated with `@frame` (or `@pattern` for pattern books). For older files, it also falls back to resolving:

1. `@frame`-decorated functions returning a `Frame`
2. Module-level `example`
3. `build_frame()` function
4. Module-level `patternbook`

`example` may be either:

- A frame-like value
- A callable returning a frame-like value
- A patternbook

If no supported entry point exists, the viewer returns an error.


## Project Discovery

Kigumi resolves project roots the same way for both "Render Kigumi" and "Initialize Current Project":

1. Start from the active Python file (when available) and walk upward.
2. If a folder contains `kumiki/`, treat it as local development mode (not relevant unless you are developingon kumiki)
3. If a folder contains `.kigumi/kumiki.yaml`, treat it as a normal Kigumi project.
4. If no marker is found, fall back to the workspace root (or file parent) and create `.kigumi/kumiki.yaml`.

This lets you open a single Python file and still bootstrap a runnable Kigumi project without manual setup first.

## First Run: Automatic Python Environment Setup

On first render in a project, Kumiki bootstraps a project-local environment automatically:

1. Finds project root by walking upward from the target file
2. Ensures `uv` is available (uses installed `uv` when present -- including the usual install locations that a GUI-launched editor's `PATH` can miss -- otherwise bootstraps it into `.kigumi/uv-bootstrap/`)
3. Creates `.venv` with `uv venv --python 3.13 .venv`
4. Installs required dependencies via `pip`:
   - Local dev checkout: `pip install -e <projectRoot>` (editable kumiki)
   - Non-local project: `pip install kumiki` (from PyPI)
  - Core packages: `sympy`, `numpy`, `trimesh`, `manifold3d`
5. Writes `.kigumi/kigumi.yaml` with Python path and setup metadata

On later runs, Kigumi reuses the configured interpreter from `.kigumi/kigumi.yaml` when available.

Note: If neither `uv` nor a working bootstrap Python launcher is available, initialization will fail with instructions to install `uv` manually.

## Pattern Browsing

Kumiki scans three sources:

- local project patterns in `<projectRoot>/patterns`
- shipped patterns bundled with `kumiki`
- patterns bundled with any other python dependency in your project


## License

Kigumi is under the [Elastic License 2.0](LICENSE). You may use, modify and redistribute it freely, including commercially, but you may not offer it to others as a hosted or managed service. Versions up to and including 0.7.2 were released under MPL-2.0 and remain so.

kumiki, the Python library kigumi runs, stays under the Mozilla Public License 2.0. Third-party files bundled with kigumi, such as those in `webview/vendor/`, keep their own licenses.
