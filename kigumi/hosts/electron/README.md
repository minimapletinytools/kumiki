# Kigumi standalone app

The same Kigumi as the VS Code extension, in its own window: the explorer on
the left, one tab per open viewer, and a status bar. It runs `kigumi-app.js`
against the host in `electron-host.js`.

## Run, test, build

From `kigumi/`:

| Command | Does |
|---|---|
| `npm run app:start -- <project-folder>` | Run from source. Without a folder it reopens the last one. |
| `npm run test:app` | Opens this repo in the app and runs `test/app/smoke-driver.js` in it. Add `-- --app <packaged executable>` to test a build. |
| `npm run app:dist` | Bundles docs and a pinned uv, then builds installers into `dist-app/`. |

`test:app` needs the repo's `.venv` (`uv sync` at the repo root).

## Pieces

The window is a web page with a fixed layout -- explorer on the left, tabs in
the middle, an optional right panel, a status bar -- whose panels are iframes.
Only the transport and the window are Electron-specific, so the same shell
can later run in a browser.

- `../../webview/shell/`: the shell page (`shell.html`, `shell.js`), the
  quick pick, the Log panel, and `panel-bridge.js`, which gives each panel page
  `acquireVsCodeApi()` so the viewer and explorer run unchanged.
- `../../app-shell/`: the core's side, host-neutral. `panel-registry.js` lists
  panel types and their slots; `shell-connection.js` keeps panels, tabs and the
  quick pick in step with the shell page; `page-store.js` serves panel HTML.
- `app-window.js`: the BrowserWindow and the IPC transport (one channel,
  `kigumi:shell`, exposed to the page by `shell-preload.js`).
- `main.js`: startup, the `kigumi://app` protocol, menus, the Log panel.
- `electron-host.js`: the Host (see `../../host.js`).

Settings live in `<userData>/settings.json`: the extension's `kigumi.*` keys
without the prefix, plus `app.workspaceFolder`, `app.editorCommand` (e.g.
`"code -g {file}:{line}"`) and `app.filesExclude` (names the explorer's All Files leaves out). Kigumi > Open Settings File (or the gear in the
status bar) opens it listing every key; edits apply without a restart. Auto
refresh on save defaults to on in the app. Logs are in
`<userData>/logs/kigumi.log`, rotated to `kigumi.1.log` past 5 MB.

## Layout

The window's layout is data in `../../app-shell/shell-connection.js`:
- the explorer on the left, with an All Files tree of the workspace at the top (collapsed; a click opens a file's source, and a Python file's right-click menu opens it in a viewer);
- tabs in the centre, for views and source files alike (a view draws its own sidebar of panels: the tree, options, parameters, members and log; `../../webview/view-sidebar.js`);
- the agent on the right.

The title bar buttons show and hide the sides.

## Keyboard shortcuts

`keybindings.js` lists them in VS Code's keybinding shape (`{ key, mac, command }`), and the menus
take their accelerators from it. Not configurable yet.

| Key | Command |
|---|---|
| Cmd/Ctrl+P | Go to File: any file of the workspace, opened as source |
| Cmd/Ctrl+O | Open in Viewer: a Python file of the workspace, frames and patternbooks first |

## Agent and MCP

- **Agent panel** (the sparkle button, or Kigumi > Toggle Agent): the Claude Agent SDK, run in the
  app's main process (`../../agent/agent-session.js`). It uses `agent.apiKey` from settings if set,
  else the Claude login on this machine; `agent.model` picks a model. Tools that only look run without
  asking; anything else (editing files, running commands, moving the camera) asks in the panel.
  Hiding the panel keeps the conversation; the clear button starts a new one.
- **MCP server** (`../../agent/mcp-http.js`): with `mcp.enabled` on, Kigumi's tools are served at
  `http://127.0.0.1:<mcp.port>/mcp` (default port 7345) to any agent holding `mcp.token`, which is
  generated the first time. Turn it on from a view's options (beta features > MCP server); the MCP
  section there then copies the setup for Claude Code, Claude Desktop, Cursor or VS Code
  (`../../agent/mcp-setup.js`) and lists the clients seen in the last 10 minutes. Kigumi > Copy MCP
  Setup for Claude Code copies the `claude mcp add` line. Not in VS Code yet:
  `.claude/plans/vscode-mcp.md`.
- **The tools** (`../../agent/tools.js`): `get_workspace_folder`, `list_panels` (with each panel's file), `describe_panel` (what a panel shows and
  what is selected in it), `open_in_viewer`, `refresh_view`, `read_view_log`, `get_camera`,
  `set_camera`, `screenshot`. Panels answer through `../../agent/panel-directory.js`.

## Signing

`electron-builder.yml` signs and notarizes when `CSC_LINK`, `CSC_KEY_PASSWORD`,
`APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD` and `APPLE_TEAM_ID` are set (the
`build-kigumi-app` workflow reads them from `KIGUMI_APP_*` secrets). Without
them builds are unsigned: macOS refuses a downloaded copy as "damaged" (for
testing, `xattr -cr Kigumi.app` clears the quarantine), and Windows shows
SmartScreen.
