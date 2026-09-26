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

- `main.js`: startup, the `kigumi://app` protocol, menus, the Log tab.
- `shell.js`: the window. The sidebar, each tab and the quick pick are
  WebContentsViews laid over `pages/shell.html`.
- `preload.js`: gives the viewer and sidebar pages `acquireVsCodeApi()`, so
  they run unchanged.
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
