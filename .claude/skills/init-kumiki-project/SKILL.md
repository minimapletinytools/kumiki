---
name: init-kumiki-project
description: Check whether the current workspace is a kumiki project, initialize it if not, and confirm the setup is ready.
---

# Init Kumiki Project Skill

Use this skill when starting work in a workspace to verify it is a kumiki project and set it up if needed.

## Step 1: Decide if this is a kumiki project

A kumiki project is one of:
- An **empty folder** (or nearly empty — maybe just a `.git/`)
- A folder that already contains Python files with `from kumiki import *` or `import kumiki`
- A folder that already has a `.kigumi/` directory or `.venv/` with kumiki installed

**Stop and ask the user before proceeding** if the folder shows signs it belongs to something else:
- `package.json` or `node_modules/` at the root → likely a JS/TS project
- `pyproject.toml` or `setup.py` that defines a package *other than* a kumiki frame script
- Imports of non-kumiki frameworks (Django, Flask, FastAPI, numpy, torch, etc.) in existing `.py` files
- A populated git repo with a README describing a different project
- Many pre-existing files unrelated to timber framing

When in doubt, show the user a brief summary of what you see in the folder and ask them to confirm before touching anything.

## Step 2: Check if already initialized

A project is fully initialized when all of these are present:
- `.kigumi/kigumi.yaml` — written by Kigumi after a successful setup
- `.venv/bin/python3` (macOS/Linux) or `.venv\Scripts\python.exe` (Windows)
- `my_cute_frame.py` — starter example file

If all three exist, skip to Step 4.

## Step 3: Initialize via Kigumi

Run the VS Code command:

```
kigumi.initializeProjectInWorkspace
```

This command (title: **"Kigumi: Initialize Project"**) handles everything:
- Creates `.venv/` with Python 3.13 via `uv`
- Installs kumiki and its viewer dependencies
- Writes `.kigumi/kigumi.yaml`
- Creates `my_cute_frame.py` as a starter example
- Adds `.gitignore` entries (`.venv/`, `kigumi_exports/`, `.kigumi/logs/`)
- Creates agent instruction files (`AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.cursorrules`)

Wait for the command to complete (it shows a progress notification in VS Code). On success you will see: *"Kigumi workspace initialized and Kumiki was updated to latest."*

If it fails, check the Kigumi output channel for details and report the error to the user.

## Step 4: Resolve the kumiki package path and read concepts

```bash
.venv/bin/python3 -c "import kumiki, pathlib; print(pathlib.Path(kumiki.__file__).resolve().parent)"
```

On Windows: `.venv\Scripts\python.exe` instead of `.venv/bin/python3`.

Read `<that_path>/docs/concepts.md` to load Kumiki core concepts and architecture before doing any design work.

## What an initialized project looks like

```
my-project/
├── .venv/                  # Python venv with kumiki installed
├── .kigumi/
│   ├── kigumi.yaml         # Project metadata written by Kigumi on init
│   └── logs/               # Session logs (created on first run)
├── .gitignore              # Includes .venv/, kigumi_exports/, .kigumi/logs/
├── AGENTS.md               # Agent instruction pointer (created by Kigumi)
├── CLAUDE.md               # Claude instruction pointer (created by Kigumi)
├── my_cute_frame.py        # Starter example frame
└── *.py                    # Additional frame files the user creates
```

Key markers:
- `.venv/bin/python3` exists and `import kumiki` succeeds
- Python files use `from kumiki import *` and define functions typed `-> Frame`
- No `pyproject.toml` / `setup.py` for a library (these are scripts, not packages)
