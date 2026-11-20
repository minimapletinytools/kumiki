<!-- 🤖🤖🤖🤖🤖🤖 -->
# Kigumi workflows and what tests them

> **AGENT-GENERATED.** Written 2026-11-19 from the source and the tests. Each workflow lists what it
> assumes, the edge cases that have bitten or could, and the tests that cover them. A gap is an edge
> case nothing covers yet.

## Running the tests

| What | Command (in `kigumi/`) | Time |
| --- | --- | --- |
| Unit tests | `npm test`, or `npx jest <file>` | about 1 min |
| Core integration suites: the main workflow on the app and in VS Code | `npm run test:int -- core` | about 40 s |
| One suite, or several | `npm run test:int -- app:drawings vscode:parameters` | |
| Every suite on one host | `npm run test:int -- app` (or `vscode`, `web`) | app 45 s; web builds first |
| Everything CI runs | `npm run test:int -- all` | |
| The list, with what each covers | `npm run test:int -- --list` | |

Unit tests come first: a workflow's logic is tested where it lives, as a function or a store, and
the integration suites check that the pieces are wired together on each host. CI
(`.github/workflows/kigumi-tests.yml`) runs the unit tests and every integration suite, one job
per host. `web:mcp` needs a `kigumi-backend` checkout and runs only when named.

Integration suites by host: `app:*` are the standalone app's scenarios (`test/app/scenarios/`),
`vscode:*` the extension in VS Code (`test/suite/`), `web:*` Kigumi in a browser
(`hosts/pyodide/test/`). The Python side of every workflow that builds a frame is in `tests/`
(`test_kigumi_*` for the runner).

## Projects

**Open, make, switch and close a project.** One project is open at a time; switching replaces the
project's panels and keeps the app's own (log, settings).
- Assumes: a project is a folder marked by `.kigumi/kumiki.yaml`, an older `.kigumi.yaml`, or a
  kumiki checkout (local development).
- Edge cases: a frame outside the workspace (a shipped pattern) builds in the workspace's project;
  an older marker is honoured and not rewritten; switching is cancelled when a tab refuses to close;
  two switches at once run one after the other; a recent folder that has gone is not offered.
- Unit: `project-root`, `host-boundaries` (switches), `project-tools`, `recent-folders`.
- Integration: `app:projects`, `app:switch-project`, `app:recent-folders`, `vscode:initialization`.

**Initialize a project.** Kigumi makes the venv, installs kumiki and writes the agent docs.
- Assumes: uv, else a Python 3.10+ on PATH; kumiki's major.minor matches Kigumi's.
- Edge cases: no uv and no Python (asks before downloading uv; declining downloads nothing);
  concurrent callers share one prompt and one download; an existing `AGENTS.md` keeps its text;
  docs are re-synced only when kumiki's version changes; old `docs/` copies are removed only when
  unchanged.
- Unit: `project-initializer`, `python-toolchain`, `python-env`, `project-docs`.
- Integration: `vscode:initialization`.

## The explorer

**Scan and list frames, patterns, examples and files.**
- Assumes: a frame file has a module-level `@frame` or `@pattern` (or the old entry points).
- Edge cases: an uninitialized project is not scanned; a save that adds the first `@frame` lists
  the file and taking it out unlists it, without a rescan of everything; venvs, caches, `.git` and
  agent worktrees are ignored; names show in the app's language; keys are unique across the tree.
- Unit: `sidebar-model`, `sidebar-controller`, `sidebar-tree`, `frame-file-watcher`.
- Integration: `app:explorer`, `app:new-files`, `vscode:initial-state`, `vscode:fixture-switching`.

**New frame, new file, duplicate an example.**
- Edge cases: a name outside the project or one that exists is refused; files are never
  overwritten; a workspace pattern cannot be duplicated.
- Unit: `new-files`, `kigumi-app` (duplicate).
- Integration: `app:new-files`.

## Viewing a frame

**Open a frame in a view and build it.** The view's page shows at once in a loading state; the
runner (`runner.py`) builds the frame and sends its geometry.
- Assumes: one runner per main view; a pattern view can share it, so closing the main view hands
  the runner on rather than stopping it.
- Edge cases: a build that fails shows its error and where, in the user's file rather than the
  runner's; a view closed mid-build reports nothing; a hidden tab keeps its size (a 0 × 0 canvas
  is skipped); opening the same file again reuses its view.
- Unit: `runner-protocol` (with Python), `runner-errors`, `build-report`, `view-log-levels`,
  `view-log-noise`, `kigumi-app`, `app-shell`, `message-protocol`.
- Integration: `app:viewer`, `app:log`, `app:tabs-and-editors`, `vscode:initial-state`,
  `vscode:fixture-switching`, `web:browser`.
- Gap: on the website the view stays blank until its ~77 files load; no test times it.

**Rebuild on save.**
- Edge cases: rapid saves rebuild once, after they stop; a deleted file keeps its last build
  rather than failing to build; in a kumiki checkout a library change
  rebuilds too; with auto refresh off the view is still told and decides.
- Unit: `file-watcher`, `frame-file-watcher`, `view-log-levels` (the deleted file).
- Integration: `app:log` (a broken save), `web:browser` (a change reaches the browser's copy).

**Move the camera: mouse, trackpad, touch.**
- Edge cases: a two-finger drag pans and a pinch zooms; a trackpad pinch arrives as ctrl+wheel;
  the fit uses the narrower field of view (a phone held upright); a sheet pans and zooms instead of
  the camera; free and axis orbits never produce NaN.
- Unit: `camera-controller`, `camera-controls`, `touch-navigation`, `input-controller`,
  `scene-store`, `pick-tolerances`.
- Integration: `app:viewer` (touch), `web:phone` (pinch, two-finger pan).

**Select timbers and features.** A click asks the runner what is under the pointer; a hover asks
the same question first, so it shows what a click would take.
- Assumes: the click and the hover send the same request (`pickQuery`).
- Edge cases: `candidateIndex` 0 is a choice, null is "choose for me"; a selected timber wins the
  ray even when another hides it; Tab steps through the features at a point; a stale hover answer
  is dropped; a drawing has no timber selection; a locked member's row doesn't select it; a point
  within `eps` of one cut's edge, on a face another cut shares, is still surface (`close_around_it`
  tries each face of each solid -- the brokenbench dovetail tongue was unpickable without it).
- Unit: `pick-query`, `selection-store`, `hover-state`, `highlights`, `csg-tree-view`,
  `selection-visuals`, `feature-states`, `member-states`, `viewer-keys`, `context-menu`.
  Python: `test_kigumi_csg_navigation.py`, `test_kigumi_whole_ray.py`.
- Integration: `app:viewer` (right-click menus), `app:sidebar` (select from the list).
- Gap: no integration check clicks a timber in the canvas and sees it selected.

**The layers tree, tags and visibility.**
- Edge cases: hiding or locking one member leaves the others; a member that comes back is plain;
  the tree keeps its scroll through a rebuild; an accessory is a member like any other.
- Unit: `layers-*`, `layer-state-store`, `tag-index`, `tags`, `csg-tree-indent`, `display-options-store`.
- Integration: `app:sidebar` (the tree has the rail with nothing selected: the selection pane once
  filled it and hid the tree).

## Drawings and measurements

**Enter a drawing, measure, delete, undo.** Measurements are kept per drawing per frame in
`.kigumi/drawings/<frame>.json` beside the frame.
- Assumes: the runner settles what a measurement comes to; the view only draws it.
- Edge cases: undo and redo work though VS Code claims ctrl-Z first; they are refused while a
  measurement is half made; a deleted code measurement can be put back; an edge written either way
  round is one measurement; a plane square to the view is refused; a refresh measures again; a
  locked view tilted by a drag, the gizmo or a trackpad scroll springs back (a scroll has no
  release, so it waits for the scroll to stop).
- Unit: `measure-draft`, `measurements`, `measurement-*`, `undo-stacks`, `viewer-keys`,
  `key-match`, `drawing-panel-viewports`, `drawing-overlays`, `member-id-buffer`, `render-mode`,
  `dimension-text`, `units`, `scale-ruler`. Python: `test_measurement_*`, `test_kigumi_*drawings*`.
- Integration: `app:drawings` (dotted lines, export, outlines, tilt spring-back, undo and redo from
  the keyboard).

## Parameters (kiwari)

- Edge cases: a box that doesn't read sends nothing and says why; an optional parameter switched
  off sends nothing; untouched boxes follow the viewer's units; saved values go back to the frame
  they were saved for.
- Unit: `kiwari-values`. Python: `test_kigumi_kiwari_protocol.py`, `test_kigumi_frame_decorators.py`.
- Integration: `app:parameters`, `vscode:parameters`, `app:drawings` (a parameter change re-measures).

## Other frame tools

- **Assembly preview**: `assembly-timeline`, `feature-flags`; `vscode:assembly`.
- **Mesh (STL) timbers**: `stl-placement`; `app:stl-placement`.
- **Export (STL, 3MF, OBJ, STEP)**: the runner side is `tests/test_blueprint.py`.
  Gap: STEP needs cadquery-ocp, which neither CI nor the dev group installs, so its three tests
  are skipped everywhere. `export-requests` covers where exports go and the view closing mid-request.
- **Share links**: `publishes`, `shared-tools`; `app:shared`.

## The app around the views

- **Tabs, editors, read-only files**: `app-shell`, `host-boundaries`; `app:tabs-and-editors`.
  Edge cases: closing a tab asks first; a read-only file offers a copy; a change on disk reaches
  an open editor.
- **Layout and sides**: `view-sidebar`, `electron-host-parts` (tabs); `app:layout`.
- **Settings and language**: `electron-host-parts`, `i18n`; `app:settings`. Edge cases: a corrupt
  settings file is set aside, not overwritten; a half-saved file changes nothing.
- **Keyboard shortcuts**: `keybindings`, `key-match`, `viewer-keys`; `app:keyboard-shortcuts`,
  `app:go-to-file`, `app:quick-pick`.
- **The log**: `electron-host-parts` (log channel), `log-retention`, `boot-diagnostics`; `app:log`.
- **Updates**: `update-check`, `auto-update`; `app:layout` (the update button).
- **Crash recovery**: `app:crash-recovery`. Gap: skipped on Linux CI, where the forced crash leaves
  the window hung, so the app is never told and never reloads; not yet checked on a real Linux machine.

## The agent and MCP

**The built-in agent.**
- Assumes: requests go through the user's OpenRouter key, else the signed-in account.
- Edge cases: signed out, a prompt keeps its draft and offers sign-in; a tool that edits waits for
  permission; plan mode edits nothing; a stream cut short is continued, at most twice; a step limit
  counts steps before a continuation; only the newest screenshot is sent; large conversations are
  summarised; a turn that changed files can be undone; nothing outside the project is written, and
  never `.git`, `.venv`, `node_modules` or `.kigumi`; a pathological search is stopped; a reply's
  Markdown is drawn and any HTML in it stays text.
- Unit: `agent-loop`, `agent`, `agent-conversation`, `conversation-store`, `agent-protocol`,
  `agent-panel` (the page in Electron), `file-management-tools`, `system-prompt`, `kumiki-api`,
  `kumiki-source-tool`, `kumiki-docs`, `selection-history`, `account`.
- Integration: `app:agent`.

**MCP**: `agent` (the server), `mcp-relay`, `file-management-tools`; `app:mcp`, `web:mcp`.

## Kigumi in a browser

- Assumes: Kigumi's core and Python (Pyodide) share one Web Worker; a project lives in the
  browser's storage only.
- Edge cases: running Python can't be interrupted, so a cancelled request never starts; a project
  is exported as a .zip and opened again; a reload keeps the project.
- Unit: `pyodide-runtime`, `web-zip`.
- Integration: `web:browser`.

**On a phone**: one file at a time; a read-only file gets a Back button; the agent is a sheet.
- Unit: `choose-layout`, `touch-navigation`.
- Integration: `web:phone`.
