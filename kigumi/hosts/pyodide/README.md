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
  page/web-projects.js: projects (IndexedDB),      worker/shims/: fs over Pyodide's files, Python
    settings (localStorage), the projects page       "processes" run in Pyodide, os, crypto, https
  page/transport.js: messages to the worker   ⇄  Pyodide: kumiki (a wheel built from this checkout),
    and panel pages shown as blobs                  manifold3d.py over Manifold's WebAssembly build,
                                                     python/kigumi_pyodide.py: runner.py, a request
                                                     at a time
```

- **The core is unchanged.** `build.mjs` bundles it with esbuild, with Node's modules played by
  `worker/shims/`: files are Pyodide's (in memory, the same ones Python sees), and spawning Python
  runs it in Pyodide (`python -c`, `-m`, a script, or `runner.py`, which `kigumi_pyodide.py` feeds
  one request at a time and whose background jobs run after each reply: Pyodide has no threads).
  Each bundled file gets its `__dirname` in Pyodide's file system, where `kigumi-files.json` puts
  `runner.py`, the page templates, the translations and the docs.
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

Manifold's WebAssembly build takes and hands back float32 vertices. kumiki meshes each half space
and open-ended prism as a box sized to the timber it cuts, so the coordinates stay small, and the
browser's timbers match native kumiki to within 1e-5 of each one's volume:

| Frame | Timbers | Mesh time, native | Mesh time, Pyodide |
| --- | --- | --- | --- |
| my_cute_frame | 4 | 0.03 s | 0.06 s |
| dovetailed_sawhorse | 5 | 0.03 s | 0.06 s |
| oscarshed | 25 | 0.16 s | 0.25 s |
| tinyhouse120 | 75 | 0.55 s | 0.85 s |

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
