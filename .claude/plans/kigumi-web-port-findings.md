# Kigumi web port: prototype findings

Status: a local browser host was prototyped and tested on 2026-10-24. It is
preserved separately from `main`; no public service has been deployed.

- Branch: [`codex/kigumi-web-prototype`](https://github.com/minimapletinytools/kumiki/tree/codex/kigumi-web-prototype)
- Prototype commit: `531e1520`
- Run/deployment notes: [`kigumi/hosts/web/README.md` on the prototype branch](https://github.com/minimapletinytools/kumiki/blob/codex/kigumi-web-prototype/kigumi/hosts/web/README.md)

This supplements [the earlier desktop/web/VS Code proposal](kigumi-desktop-web-vscode.md).
Its shell-to-iframes step already exists. This spike tested the server-backed
route; it did **not** test Pyodide or settle whether a fully browser-local
runtime is feasible.

## Main finding

Kigumi's existing shell and viewer can run in a normal browser without a
frontend rewrite. The practical route demonstrated here keeps the application
core in Node and geometry computation in the existing Python runner. Electron
is replaced by an HTTP server, browser transport and Host adapter.

The existing seams were sufficient:

- `kigumi-app.js` owns commands, viewer/pattern sessions and the sidebar.
- `host.js` defines the services supplied by VS Code or the standalone host.
- `app-shell/shell-connection.js` manages panels, tabs, messages and quick picks
  independently of Electron.
- `app-shell/page-store.js` stores generated panel HTML and injects
  `webview/shell/panel-bridge.js` so panels obtain `acquireVsCodeApi()`.
- `webview/shell/` already uses iframes for its explorer and viewer panels.
- Existing Python sessions can keep their project environment and runner
  protocol; the browser receives frame and geometry messages through the shell.

```text
Browser
  Existing app shell + explorer/viewer iframes + Three.js
                | HTTP POST commands / SSE responses
Node worker
  Browser Host + ShellConnection + createKigumiApp
                | Existing runner protocol
Python subprocess
  Project virtual environment + Kumiki + geometry dependencies
```

This does not produce a static-only deployment. The current core uses Node
filesystem/process APIs and Python subprocesses. A static frontend would still
need a server runtime, unless those responsibilities are separately ported.

## What the prototype adds

All implementation and test files are on the prototype branch, not `main`:

| File | Responsibility |
| --- | --- |
| `kigumi/hosts/web/server.js` | Serve shell, assets and generated panel pages; bridge HTTP/SSE to ShellConnection; start the existing app. |
| `kigumi/hosts/web/browser-host.js` | Implement workspace, file watching, config, dialogs, source previews and viewer surfaces through the existing Host interface. |
| `kigumi/hosts/web/transport.js` | Expose `window.kigumiShell`; order outgoing POSTs and receive server messages through EventSource. |
| `kigumi/hosts/web/source.css` | Style the text source preview using the existing app theme. |
| `kigumi/__tests__/web-host.test.js` | Check HTTP transport and browser access boundaries. |
| `kigumi/test/web/browser-smoke.js` | Exercise the HTTP app in Chromium, including frame rendering and page reload. |

The prototype adds no frontend framework or runtime dependency and changes no
existing shared implementation files. It imports SettingsStore, LogChannel and
the glob matcher from `hosts/electron/`; these modules have no Electron imports.
They should move into a shared host directory when this becomes maintained code.

The browser adapter also adds `style-src-attr 'unsafe-inline'` for existing
viewer template style attributes. It retains the existing nonce policy for
scripts. The final smoke run checked for CSP violations.

## How to reproduce

On the prototype branch, from the repository root, with Node 22+ and the
project's Python environment installed (`uv sync`):

```sh
node kigumi/hosts/web/server.js .
```

Open `http://127.0.0.1:7346` and select a frame or pattern in the explorer.
`PORT` changes the port; the positional argument selects the workspace.
Settings and the host log live in `~/.kigumi/web/`. The existing sessions still
write workspace logs and exports at their normal locations.

The host binds only to loopback. A private remote trial can use an SSH tunnel
with matching local and remote ports:

```sh
ssh -N -L 7346:127.0.0.1:7346 your-server
```

The server must already be running on the remote machine. Matching ports matter
because the prototype generates absolute URLs and validates the Host header.
The SSH route was documented but was not tested during the spike.

## Evidence and scope

Verified during the spike:

- The existing explorer renders its discovered frame/pattern rows over HTTP.
- `minimal_frame.py` runs through the existing Python runner and renders
  `Runner Test Frame`, with two timber rows and a WebGL canvas.
- Reloading the browser page restores the open viewer and renders the frame
  again. Existing sessions remain in the Node process across page reloads.
- The final Chromium smoke run passes without CSP violations. Electron is
  used only as the Chromium test harness; the page has no Electron preload or
  Node integration.
- All 1,643 unit tests passed, including five new web-host tests. The five
  initial VS Code extension integration checks also passed.
- HTTP tests cover cross-origin and unexpected Host rejection, the active
  browser client ID, a second controller, malformed/oversized messages,
  bidirectional transport, and asset traversal/symlink boundaries.

The adapter supplies existing pattern, parameter, file-refresh and export
message paths, but these were not all exercised end to end in the browser
smoke test. There was no public-hosting, proxy, load, multi-user or cross-browser
validation, and no full complex extension-suite run.

## Prototype limitations

- One trusted workspace and one controlling browser tab per process. The global
  Host makes separate Node processes the natural initial isolation boundary.
- A network interruption requires a page reload. There is no delivery replay,
  automatic session recovery or collaboration model. Page reload restoration
  is implemented; reliable reconnection is separate work.
- Source previews are read-only snapshots, limited to supported text files up
  to 2 MB. Close and reopen a preview to reread it. Line navigation does not
  position the preview at the requested line.
- The workspace is selected at startup. There are no browser upload, project
  creation or project-switching flows.
- Existing export commands write files on the server. Browser downloads are
  not implemented.
- Clipboard and external-link actions depend on browser permissions and popup
  policies. Desktop shortcut labels and actions also need a browser UX pass.
- Settings are stored on the server, rather than in an authenticated user
  profile. Settings-file edits require a host restart.
- The built-in AI agent and MCP are not wired into this host. Their ongoing
  implementation was deliberately kept separate; revisit the current desktop
  integration when connecting them to the web worker.

## Public deployment requirements

The prototype's loopback binding, origin/Host checks, browser client ID and
bounded messages are local browser boundaries. They are not user authentication
or a sandbox. Opening a design executes Python with the server account's
filesystem and process access.

For a hosted product, build around an authenticated workspace gateway and a
separate worker/container per user or workspace:

1. Authenticate access to every shell, panel, asset and transport route, and
   assign the user to their worker. Define session expiry and worker cleanup.
2. Isolate Python execution with filesystem boundaries and CPU/memory/process
   limits. Keep service credentials out of user-code workers. A separate Node
   process alone does not provide that security boundary.
3. Provide persistent project storage, installation of a compatible Kumiki
   environment, and explicit file upload/download flows.
4. Configure the public origin and proxy routes. Absolute URL generation and
   strict Host/Origin validation must agree with the externally visible URL;
   do not simply relax those checks. Preserve SSE heartbeats and disable proxy
   buffering for the stream.
5. Add reconnect/replay semantics and a policy for a second browser or device.
6. Bring across source editing and the agent host adapter, then exercise
   parameter changes, patterns, saves, exports and agent edits end to end.

Recommendation: use this server-backed prototype as the next hosted-product
spike. It proves that the current UI and geometry runtime can be reused. Keep a
Pyodide/native-geometry spike as a separate option if avoiding per-user server
compute is a product requirement; compatibility, filesystem integration and
runner changes remain unverified.
