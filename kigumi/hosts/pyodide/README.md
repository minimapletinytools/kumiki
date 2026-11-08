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

## Precision: kumiki's boxes

Manifold's WebAssembly build hands back float32 vertices. kumiki meshes a half space as a box 2 km
across and an infinite prism as 100 m long, and at a kilometre float32 is off by over a millimetre,
enough to lose a cut (a dovetailed sawhorse leg lost 57% of its volume). The browser version sets
them to 20 m and 10 m (`KUMIKI_TRIANGLES_HALF_SPACE_EXTENT`, `KUMIKI_TRIANGLES_PRISM_EXTENT`), with
which these frames match native kumiki to within 5e-7 of each timber's volume:

| Frame | Timbers | Mesh time, native | Mesh time, Pyodide |
| --- | --- | --- | --- |
| my_cute_frame | 4 | 0.02 s | 0.06 s |
| dovetailed_sawhorse | 5 | 0.02 s | 0.05 s |
| cat_corner_cot | 96 | 0.13 s | 0.25 s |
| oscarshed | 25 | 0.11 s | 0.24 s |
| tinyhouse120 | 75 | 0.52 s | 0.83 s |

But the cuts are fragile to those sizes natively too (with the same 20 m / 10 m, native loses cuts
on two sawhorse legs). The fix is for kumiki to size each box to the solid it cuts.

## Not here yet

- The agent and MCP (the agent needs its backend from a worker; MCP needs a server).
- Importing a .zip as a project.
- Pyodide and Manifold come from jsDelivr, and trimesh from PyPI: vendor them for working offline.
- kumiki's boxes sized to the solid (see above).

## Tests and tools

```sh
npm run build && env -u ELECTRON_RUN_AS_NODE ../../node_modules/.bin/electron test/browser-smoke.cjs
```

`test/browser-smoke.cjs` serves `dist/` and drives the app in Chromium (Electron as the browser
only):
1. It makes a project and builds its starter frame in a view, then opens the file in the editor.
2. It checks that a change reaches the browser's copy, and that Example Frames and kumiki's patterns
   are listed.
3. It builds the 75-timber tiny house.
4. It reloads, exports the .zip and checks it, reopens the project and deletes it.
5. It checks there are no policy violations or page errors.

Screenshots go to `test-artifacts/`.

- `test/node-runner.mjs`: the worker's Python in Node, to debug the runner bridge without a browser.
- `run-frame.mjs` and `compare.py`: build a frame in Pyodide (or natively) and print each timber's
  volume and faces, to compare the two; `record_booleans.py` records one leg's booleans.
