# Kigumi on desktop, web and VS Code: one app, three hosts

> **Status: proposal, not started.** Written 2026-09-26 after the standalone
> Electron app shipped (#38, #39). Revisit before building an editor or agent
> panel, or anything web-facing.

## Context

Kigumi runs today in two hosts that share one core:

- **VS Code extension.** VS Code supplies the tabs, the code editor, the
  sidebar container and (via other extensions) an agent.
- **Standalone Electron app** (`kigumi/hosts/electron/`). A fixed window: the
  explorer on the left, one tab per viewer, a status bar.

What already exists and carries over:

- `kigumi-app.js`: every command, the viewer/pattern sessions, runners and the
  sidebar model, with no `vscode` import.
- `host.js`: the Host interface (messages, files, settings, watching, quick
  pick, viewer surfaces), implemented by `hosts/vscode.js` and
  `hosts/electron/electron-host.js`.
- Panels as *surfaces*: a page plus a message channel. The viewer and sidebar
  pages run unchanged under either host (`acquireVsCodeApi()` is provided by
  the Electron preload).
- Automation commands: open file, refresh, read logs, get/set camera,
  screenshot.

## Goal

The same product on **desktop, web and VS Code**. Desktop and web supply
themselves what VS Code gives the extension:

- **A folder to work in.** Desktop opens to a "no folder open" state with an
  Open Folder button (this exists). Web uses a project stored in the browser or
  on a backend.
- **A fixed layout:**
  - left: sidebar (explorer)
  - center: tabs holding the viewer, a code editor, the log, …
  - right: an agent
- **Generic panels.** Explorer, viewer, editor, agent and log are not special
  cases. Each is a panel type the layout places in a slot. The layout is fixed
  for now; making it user-arrangeable is out of scope.

## Decision 1: where Python runs on the web (decide first)

Everything ends in Python (`runner.py`, the scanners, kumiki). Two options:

1. **Pyodide in the browser** (Python compiled to WebAssembly, core in a Web
   Worker).
   - Web is static files: no backend, no untrusted code on our servers, no
     per-user compute.
   - Projects live in OPFS/IndexedDB; sync can come later.
   - **Unknown:** kumiki needs numpy, sympy, trimesh and manifold3d. numpy and
     sympy exist for Pyodide; whether trimesh and especially manifold3d (native
     geometry) do is unverified. STEP export (cadquery-ocp) almost certainly
     won't be available.
2. **A server with one sandboxed container per user**, running the existing
   Node core and Python (code-server's model).
   - Works with no code changes.
   - Users' Python runs on our machines: needs real isolation
     (Firecracker/Fly machines or similar), accounts, storage, per-user
     compute cost, and ongoing operation.

**Next step:** a 1–2 day spike. Load numpy, sympy, trimesh and manifold3d in
Pyodide and render a real frame (`patterns/structures/my_cute_frame.py`)
through `runner.py`'s requests. If it works, web needs no backend.

### About the "virtual filesystem"

It is less an abstraction layer than a placement choice. Python reads project
files through its own import system, so the core and Python must run where
the files physically are: the container's disk, or Pyodide's filesystem backed
by browser storage. The JS side also calls `fs` directly about 100 times
(`project-initializer.js` alone: 36). A `host.fs` abstraction is only needed if
the core ever runs apart from the files; neither option above requires it.

## Decision 2: build the shell, or ship VS Code

| Option | Desktop | Web | Fixed layout & generic panels | Cost |
|---|---|---|---|---|
| code-server / openvscode-server | — | ✓ | ✗ (VS Code's UI) | Needs the per-user server anyway. Open VSX only, not Microsoft's marketplace. |
| Own VS Code fork (like Cursor, Positron) | ✓ | ✓ | ✓ | Merging upstream VS Code forever; team-sized. |
| Eclipse Theia | ✓ | ✓ | Mostly | Same code targets Electron and browser. Runs VS Code extensions, so the current extension would mostly work inside it. Built-in AI agent framework; layout can be locked. But: large framework with its own DI (InversifyJS), large bundles, tied to Eclipse releases. |
| **Own shell (current path)** | ✓ | ✓ | ✓ exactly | We build the editor panel, agent panel and file handling. Never a general IDE. |

**Recommendation: own shell.** The layout described is a product, not an IDE.
Theia and forks mostly buy flexibility we don't want, at high maintenance cost,
and the seams the shell needs already exist. Two guardrails:

- **Don't compete with VS Code as an editor.** Embed Monaco for frame and
  pattern files, add Python language features later, and offer "Open in VS
  Code/Cursor". Keep the extension for people who live in an editor.
- **Revisit Theia if** users start asking for search across files, git, a
  terminal or extensions. That is a request for an IDE, and Theia is then
  cheaper than building one.

## Architecture

```
 UI shell (plain web page)                      Core (Node, or Pyodide in a worker)
 ┌─────────┬──────────────────────┬─────────┐    kigumi-app: commands, sessions,
 │ left    │ center: tabs         │ right   │    runners, sidebar model, agent tools
 │ panels  │ (viewer, editor,     │ panels  │ ◄──────────── message bus ──────────►
 │         │  log, …)             │ (agent) │    desktop: Electron IPC
 └─────────┴──────────────────────┴─────────┘    web: WebSocket (server) or postMessage (worker)
```

- **Panel registry.** A panel type = id, page, message protocol, allowed slots
  (left / center / right). The layout places panel instances into slots.
  Explorer, viewer, editor, agent and log are all entries.
- **One UI for desktop and web.** Today each panel is an Electron
  `WebContentsView`. Make them `<iframe>`s inside one shell page, so the Electron
  app becomes "the web shell in a window, with a Node core". Only the transport
  differs between desktop and web.
- **The Host interface becomes the UI↔core contract.** Its methods (messages,
  quick pick, confirm, progress, settings, watching, surfaces) are what travels
  over the bus.
- **The VS Code extension stays as it is.** It keeps using VS Code's own tabs,
  editor and sidebar container, and hosts only the explorer and viewer panels.

## Panels

- **Explorer** (exists): `sidebar-model.js`, `sidebar-controller.js` and
  `webview/sidebar/`.
- **Viewer** (exists): `webview/viewer.html`, one per open frame or pattern.
- **Log** (exists in the app): `hosts/electron/pages/log.html`.
- **Editor** (new): Monaco on the project's `.py` files.
  - Saving triggers the viewer's auto refresh; the app already defaults auto
    refresh on.
  - Python language features later (pyright or basedpyright over LSP via
    monaco-languageclient), which needs a language server in the core.
  - Viewer "go to error" and "view source" open the editor tab instead of an
    external editor (`host.openFileAt` / `host.showFile`).
- **Agent** (new): chat plus tool calls, right slot.
  - Tools: the existing automation commands (open in viewer, refresh, read
    logs, get/set camera, screenshot) plus read/write file, list patterns and
    "run this frame". An agent can then edit a design, render it and look at
    the result.
  - Desktop: Claude Agent SDK in the core, using the user's own API key.
  - Web: requests go through our backend, which then needs accounts and
    billing. Settle key handling and cost early; it shapes the web product.

## Order of work

1. **Pyodide spike** (Decision 1). Report which of numpy, sympy, trimesh and
   manifold3d load, and whether a real frame renders.
2. **Update this doc** with the outcome and the chosen core placement.
3. **Shell to iframes.** Move `hosts/electron/shell.js` panels from
   `WebContentsView`s to iframes in one shell page, and introduce the panel
   registry. Desktop behaviour stays the same; the smoke test
   (`npm run test:app`) must keep passing.
4. **Editor panel** (Monaco) for frame and pattern files.
5. **Agent panel** on desktop, with the automation commands as tools.
6. **Web deployment** on the placement from step 1.

## Still open from the app release list

Not blocked by this doc, but needed before a public desktop release:

- Release on version tag: attach the `build-kigumi-app` installers to a GitHub
  Release.
- A "new version available" check on launch (full auto-update needs signing).
- A test run on real Windows and Linux machines (CI only builds them).
- Apple Developer ID signing and notarization. Unsigned downloads are refused
  as "damaged" on macOS.
- `docs/internal/` is copied into packages and new user projects by
  `scripts/bundle-docs.js` and the extension's publish workflow; exclude it if
  it's meant to stay internal.
