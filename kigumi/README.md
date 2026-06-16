# Kigumi

Kigumi is a VS Code extension that renders [kumiki](https://github.com/minimapletinytools/kumiki) frames. 

## Prerequisites

To use Kigumi, you need:

- **VS Code** with the Kigumi extension installed
- **uv** or **Python** so Kigumi has something to bootstrap the python virtual environment.
  - Preferred: install `uv` ahead of time: https://docs.astral.sh/uv/getting-started/installation/
  - Auto-bootstrap fallback: Kigumi tries `python3.13`, then `python3`/`python` (or `py -3.13`/`py -3` on Windows) to install uv

Kigumi does NOT require pre-installed packages. It handles dependency setup in a project-local virtual environment automatically.

## Initialization

Kigumi is built around the VSCode workspace (i.e. a folder) where all your kimuki project files live. 

To initialize a project, Open a folder in VScode that will be your workspace. Then open the Kigumi sidebar and hit the initialize project button. This will generate several files in your workspace including an example frame, agent instructions, and a project settings file.

The sidebar will also check for any Kimuki updates and you can optionally choose to update to the latest version.

The sidebar contains a project file explorer. *Click on a frame to open it in the Kigumi viewer*.

You can also use the *"Kigumi: Open Current File in Viewer"* command from the command palette to quickly open the current file. To open the command pallete press "cmd/ctrl + shift + p".

The sidebar also contains a pattern book explorer which provides various examples of things you can do with kumiki. You can also choose to view or clone the source of any pattern you like here.

## Usage

Once you open a project, it will create a new tab where you can view the frame. The viewer is pretty intuitive, and you can scroll down to see more options and features. 
Right now the viewer has mainly view-only features that you can play around. Write operations happen on the frame python file itself. 

In the future, there will be more interactive features in the viewer such as assembly, drawing generation, and measuring. 


# Details

## Runtime Contract for Kimuki files

When Kigumi imports a Python module, it uses reflection to resolve what to render in this order:

1. Module-level `example`
2. `build_frame()` function
3. Module-level `patternbook`

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
2. Ensures `uv` is available (uses installed `uv` when present, otherwise attempts to install it via Python)
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

