# Kigumi browser host prototype

Run from the repository root with Node 22+ and the project's Python environment
already installed (`uv sync`):

```sh
node kigumi/hosts/web/server.js .
```

Open **http://127.0.0.1:7346**. Select a frame or pattern in the explorer.
`PORT=8000 node kigumi/hosts/web/server.js /path/to/project` changes the port
and workspace. Settings and logs live in `~/.kigumi/web/`; workspace logs and
exports use the same paths as desktop Kigumi. There is no browser build step
or additional runtime dependency.

This prototype serves one trusted workspace to one controlling browser tab per
process. Reload restores open panels and refreshes views. Close the first tab
before opening another. After a network interruption, reload to reconnect.

## What runs where

```text
Browser: existing shell → panel iframes → existing viewer / Three.js
                 ↕ POST commands + server-sent events
Node: browser Host → createKigumiApp → existing sessions
                                              ↕ runner protocol
Python: existing project environment → Kumiki → geometry
```

`server.js` replaces Electron's custom protocol and IPC with HTTP, POST and
SSE. `browser-host.js` implements the existing Host interface. The shared
`ShellConnection`, `PageStore`, explorer, viewer, runner and Python geometry
code remain in use. SettingsStore, LogChannel and the glob matcher are imported
from `hosts/electron/`, but those modules have no Electron dependency; moving
them to a shared host directory can be a follow-up.

This works as a browser client with a server runtime. Static hosting alone
cannot run the current Node orchestration, Python subprocesses and project
filesystem. A fully in-browser implementation would need a separate Python/Wasm
runtime investigation, especially for native geometry dependencies such as
`manifold3d`.

## Current scope

The host supplies frame/pattern sessions, parameter messages, auto refresh on
workspace saves, quick picks, config updates, log streaming, and source previews.
Source previews are read-only snapshots; reopen a preview to read changes.
The existing export commands write files on the server; browser downloads and
uploads are not implemented. File/line navigation opens a source preview without
line positioning. Workspace selection happens at process startup. AI and MCP
panels are not wired here; their host-neutral modules can be connected after
the separate agent work lands. External links and clipboard writes use browser
APIs and remain subject to browser permission and popup policies.

The browser adapter allows template style attributes through `style-src-attr`;
the existing nonce policy for scripts remains in effect.

## Private remote prototype

Run this on a machine with the repository and Python environment installed,
then forward the same port over SSH:

```sh
# Remote machine, from the repository root:
node kigumi/hosts/web/server.js .

# Your local machine:
ssh -N -L 7346:127.0.0.1:7346 your-server
```

Open `http://127.0.0.1:7346` locally. Use the same local and remote port because
the host generates absolute URLs and validates the Host header. This SSH route
has not been exercised as part of the local prototype validation.

The server deliberately binds only to loopback. It checks Host, request origins
and the active browser client ID, bounds incoming messages, rejects a second
controller, and serves assets only within `webview/` (including symlink checks).
These are local browser boundaries, not user authentication or Python isolation.
Designs execute Python with the server account's filesystem and process access.

For a public hosted product, the next work is:

1. An authenticated workspace gateway that starts a separate worker/container
   per user/workspace. The current global Host makes one workspace per Node
   process the natural unit of isolation.
2. A restricted Python worker with resource limits, persistent project storage,
   and explicit upload/download flows. Keep credentials out of these workers.
3. A configured public origin and proxy routing for shell, assets, panels,
   POSTs and SSE. Disable proxy buffering and retain heartbeats for the stream.
4. A reconnect/replay protocol, session expiry and worker cleanup; multiple
   controlling browsers require an explicit collaboration model.
5. Source editing and the AI host adapter once those desktop interfaces settle.

No public service has been deployed by this prototype.

## Validation

```sh
cd kigumi
npx jest
npm run test:ext:initial

# With the web server already running on port 7346:
env -u ELECTRON_RUN_AS_NODE node_modules/.bin/electron test/web/browser-smoke.js
```

The browser smoke uses Electron only as a Chromium test harness, with no
preload, Node integration or Electron host in the page. It opens the HTTP app,
checks explorer rows, renders a two-timber Python fixture, reloads it and checks
the frame again. Its screenshot is `.artifacts/web/browser.png`.
