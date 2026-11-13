# Kigumi in a browser

Kigumi as a static website: the app's shell, explorer, viewers and code editor in the page, and
Kigumi's core and kumiki running in the browser itself, in a Web Worker with Python in
[Pyodide](https://pyodide.org). Nothing runs on a server, so the built folder can go anywhere static
files are served, such as kumiki.build/try.

## Try it

```sh
cd kigumi/hosts/pyodide
npm install
npm run build        # dist/: the site, with kumiki built from this checkout (uv build)
npm run serve        # http://127.0.0.1:8123/
```

Open the page, make a project, and open its starter frame from the explorer. The first load fetches
Pyodide (from jsDelivr), kumiki's packages and trimesh (from PyPI), so it needs the network.

## How it works

```text
Page (dist/index.html)                         Web Worker (dist/worker.js)
  the app's shell, explorer, viewers, editor     Kigumi's core (kigumi-app, the runner session, ...)
  page/web-projects.js: projects (IndexedDB),      worker/: fs over Pyodide's files, Python
    settings (localStorage), the projects page       "processes" run in Pyodide, os, crypto, https
  page/transport.js: messages to the worker   ⇄  Pyodide: kumiki (a wheel built from this checkout),
    and panel pages shown as blobs                  manifold3d.py over Manifold's WebAssembly build,
                                                     python/kigumi_pyodide.py: runner.py, a request
                                                     at a time
```

- **The application and runner protocol are shared.** `build.mjs` selects the Pyodide implementation
  of `python-runtime.js`. Native hosts use Node subprocesses; the browser uses
  `worker/python-runtime.js` and `python/kigumi_pyodide.py`. Runner creation is explicit, independent
  of the script filename. Python is managed by the site build: projects need no placeholder venv,
  and package installation is unavailable. Queued calls can be cancelled, but executing synchronous
  Python cannot be interrupted without terminating the worker. Files still use the focused `fs`
  adapter over Pyodide's in-memory filesystem.
- **Shell behavior is shared.** `app-shell/host-services.js` supplies document state, panel inspection,
  settings access and file watching to desktop and browser hosts. `project-lifecycle.js` serializes
  project switches and confirms unsaved edits; hosts supply project persistence. Agent project
  context and log panels are shared too. Page stores supply their bridge URL and CSP source per instance.
- **Projects live in the browser** (IndexedDB), as the projects page says: not on disk and not in
  the cloud. Opening one writes its files into Pyodide's file system; every change there (an editor
  save, a saved drawing) goes back to the browser's copy. Export .zip downloads a project; files
  written to `kigumi_exports/` (an STL) download too. Settings are kept in localStorage.
- **manifold3d** has no Pyodide build, and kumiki uses only its booleans: `manifold3d.py` plays that
  part over npm `manifold-3d`, Manifold's own WebAssembly build.
- **Panel pages** are shown as blobs (there is no server to fetch them from). A blob page also gets
  the policy of the page that made it, so `index.html`'s content security policy allows inline
  scripts and styles; each panel's own policy still applies on top.

## Precision

Manifold's WebAssembly build takes and hands back float32 vertices, though it works in double.
`manifold3d.py` sets each mesh's vertices exactly, going in and coming out, through `warpBatch`,
which sees them as doubles: rounded to float32, a sliver triangle tilts, and the viewer shaded it as
a crease across a flat face (the dovetailed sawhorse's legs). With that, the browser's meshes match
native kumiki's, triangle for triangle, and each timber's volume to within 1e-7:

| Frame | Timbers | Mesh time, native | Mesh time, Pyodide |
| --- | --- | --- | --- |
| my_cute_frame | 4 | 0.03 s | 0.07 s |
| dovetailed_sawhorse | 5 | 0.03 s | 0.07 s |
| ki_kanji | 5 | 0.04 s | 0.08 s |
| oscarshed | 25 | 0.18 s | 0.28 s |
| tinyhouse120 | 75 | 0.58 s | 0.98 s |

## The agent

The agent panel is here as in the standalone app: off until **Agent panel** is turned on under
Kigumi options. It runs in the worker, and its requests go from there to OpenRouter (with the
user's own key) or to Kigumi's backend (signed in). Its tools work on the project in Pyodide's files
and ask Pyodide's Python about kumiki.

- **Signing in** opens the provider in a new tab, which comes back to `auth.html`; that hands the
  code to the Kigumi tab (a BroadcastChannel). If the browser blocks the tab, Kigumi's own tab goes
  instead, and `auth.html` brings it back to finish. The account's session is kept in localStorage.
- **For a site to sign in from**, two settings outside this repo name it: the Supabase project's
  redirect URLs need its `auth.html` (e.g. `https://kumiki.build/try/auth.html`), and kigumi-backend's
  `ALLOWED_ORIGINS` needs its origin. Without the second, signed-in requests and the model list are
  refused (the agent keeps its built-in model list); an OpenRouter key works anywhere.
- **Conversations** are kept only until the page is reloaded.

## Not here yet

- MCP: other agents connect to a server, and a web page can't be one. The standalone app has it.
- Importing a .zip as a project.
- Pyodide and Manifold come from jsDelivr, and trimesh from PyPI: vendor them for working offline.

## Tests and tools

```sh
npm run build && env -u ELECTRON_RUN_AS_NODE ../../node_modules/.bin/electron test/browser-smoke.cjs
```

`test/browser-smoke.cjs` serves `dist/` and drives the app in Chromium (Electron as the browser
only):
1. It makes a project and builds its starter frame in a view, then opens the file in the editor.
2. It checks that a change reaches the browser's copy, and that Example Frames and kumiki's patterns
   are listed.
3. It turns the agent on and checks its panel, its search, kumiki_api and project tools, and signing
   in: the provider's page asked for, and `auth.html` handing the code back.
4. It builds the 75-timber tiny house.
5. It reloads, exports the .zip and checks it, reopens the project and deletes it.
6. It checks there are no policy violations or page errors.

Screenshots go to `test-artifacts/`.

- `test/node-runner.mjs`: the worker's Python in Node, to debug the runner bridge without a browser.
- `run-frame.mjs` and `compare.py`: build a frame in Pyodide (or natively) and print each timber's
  volume and faces, to compare the two; `record_booleans.py` records one leg's booleans.

## Remote MCP

Sign in through the agent panel, enable MCP in the sidebar, and copy the setup for
an external agent. The browser opens an outbound WebSocket to `kigumi-backend` on
Cloudflare; the copied HTTPS URL and bearer token grant access to this tab's shared
Kigumi tools. Keep the tab open and awake while using it. Project tools and the full text-file workflow are available through this connection:
`list_files`, `search_files`, `read_file`, `write_file`, `edit_file`, `delete_file`, and
`rename_file`. Writes stay inside the open project and protect internal folders. `rename_file`
refuses collisions; `write_file` makes a file or replaces one. Writing a file creates
its parent folders, and renaming can move a file into another folder. Changes use the same browser
storage as the editor. Standalone MCP leaves file access to the client's local filesystem tools;
the built-in agent has these tools on both hosts.

Each tab gets its own relay session. Reloading the page creates a new URL and token;
sessions expire after 24 hours. After expiry, switch MCP off and on and copy the new
setup. Turning MCP off immediately closes the connection and aborts connection setup.
Failed credential revocations are kept locally and retried, including after sign-out.
The browser serializes remote operations and validates their arguments. Calls lost
on disconnect are not replayed; inspect the current state before retrying an edit.


Test the complete MCP flow with a sibling `kigumi-backend` checkout (or set
`KIGUMI_BACKEND_DIR` to its path), after installing both repositories' Node dependencies:

```sh
KIGUMI_BACKEND_URL=http://127.0.0.1:8789 KIGUMI_SUPABASE_URL=https://supabase.test KIGUMI_SUPABASE_KEY=test-public npm run build
env -u ELECTRON_RUN_AS_NODE ../../node_modules/.bin/electron test/mcp-smoke.cjs
```

The test seeds a signed-in test account, uses the real sidebar controls and shared
tools, and talks to a local Cloudflare Worker. It does not contact production auth
or require account secrets. The backend CI runs this cross-repository test. These
build-time variables also allow staging deployments; omit them for production.
