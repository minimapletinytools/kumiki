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
without the prefix, plus `app.workspaceFolder` and `app.editorCommand` (e.g.
`"code -g {file}:{line}"`). Kigumi > Open Settings File (or the gear in the
status bar) opens it listing every key; edits apply without a restart. Auto
refresh on save defaults to on in the app. Logs are in
`<userData>/logs/kigumi.log`, rotated to `kigumi.1.log` past 5 MB.

## Signing

`electron-builder.yml` signs and notarizes when `CSC_LINK`, `CSC_KEY_PASSWORD`,
`APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD` and `APPLE_TEAM_ID` are set (the
`build-kigumi-app` workflow reads them from `KIGUMI_APP_*` secrets). Without
them builds are unsigned: macOS refuses a downloaded copy as "damaged" (for
testing, `xattr -cr Kigumi.app` clears the quarantine), and Windows shows
SmartScreen.
