# kigumi architecture: runner and app core (2026-10-29)

The agent got this treatment already (`archive/agent-architecture.md`). This is the same for the rest of
kigumi: what is there, what it should be, and an order that keeps it working at every step.

## What is there

| Piece | Size | Shape |
|---|---|---|
| `runner.py` | 5,563 lines | One module: ~650 lines of wire types, slot state, module loading and reload, kiwari parameter files, geometry and mesh serialisation, layers / CSG tree / assembly payloads, drawings and the drawings file (~600), measurements (~900), picking (~800), patterns, and `handle_request`: a 450-line if-chain over 30 commands. |
| `frame-view-session.js` | 1,597 | One class: runner lifecycle and refresh, a 236-line webview message chain, drawings and measurement relays, picking relays, session log, viewer settings, screenshots, error reporting. |
| `kigumi-app.js` | 1,089 | One closure, `createKigumiApp`, holding every command (viewer, sidebar and patterns, project setup, automation for the agent and MCP, screenshots) and the session map. |
| `runner-session.js` | 489 | The Python process and its protocol, plus project environment setup (venv, deps, version check, docs sync) that has nothing to do with the process. |
| `webview/viewer-app.js` | 2,849 | The viewer page's app class: rendering, selection, measuring wiring, panels, messages. Other webview files are already ES modules. |

What holds it together: 1,760 jest tests, 2,476 pytest tests (17 files reach into 66 runner names,
many private), the VS Code extension tests, the app scenarios, and the agent panel's Electron test.

## What it should be

### 1. runner.py becomes a package

```
kigumi/runner.py            entry point (launched by path) and the names tests use, re-exported
kigumi/kigumi_runner/
  wire.py                   the TypedDicts: what crosses the protocol
  protocol.py               emit_message, responses, errors, the stdin loop (main)
  state.py                  SlotState, RunnerState, resolving and rebuilding slots
  loading.py                loading a frame file, reloading changed project modules, @frame/@pattern resolution
  parameters.py             kiwari values and the parameters file beside the source
  geometry.py               meshes, build_real_geometry, frame summary, member keys, tags
  structure.py              layers, frame parts, CSG tree, assembly payload
  drawings.py               default and selection drawings, viewports, the drawings file
  measurements.py           add / update / delete / restore / resolve, anchors
  picking.py                at a point, by path, hover, candidates, highlights
  patterns.py               listing and finding patterns
  commands.py               COMMANDS = {"get_frame": handler, ...}, replacing handle_request's chain
```

- Pure geometry that is still in the runner (ray/mesh tests, candidate scoring) moves on into
  `kumiki.viewer.picking` / `kumiki.drawings`, as measuring and picking already partly did: the
  runner becomes the protocol adapter over kumiki, not a second library.
- Packaging: `electron-builder.yml` and `.vscodeignore` ship the package; `test/evals/build_frame.py`
  imports from it.
- Tests move from `runner.X` to the module that owns X, file by file; the re-exports shrink as they
  do. The one `monkeypatch.setattr(runner, ...)` has to patch the owning module.

### 2. One command list, checked on both sides

`commands.py`'s table is the runner's command list. `runner-session.js` gets one method per
command (`getFrame(slot)`, `findCsgAtPoint(...)`) instead of string `request('…')` calls spread
through frame-view-session, and a test reconciles the two lists, as `message-types.js` does for the
webview. Payload shapes stay in `wire.py`; the JS side documents them by reference.

### 3. frame-view-session.js splits by job

- `ViewerBridge`: the webview message table (types from `message-types.js`, one handler each),
  replacing the 236-line chain, with the same "unknown or malformed is ignored in one place" as the
  agent panel.
- `FrameRefresh`: runner lifecycle, refresh coalescing, milestones, error reporting.
- `SessionLog`: the session log file, `log` / `logBlock`, snapshots for the build report.
- Drawings, measurements and picking relays become handlers in the table, each a few lines over the
  runner method from §2.
- `FrameViewSession` keeps what a view is: its file, slot, panel, and those parts wired together.

### 4. kigumi-app.js splits by area

`createKigumiApp` composes: `SessionRegistry` (open / find / reveal / dispose sessions, today a map
and helpers inside the closure), and command groups each in its own module with
`register(app)`: viewer commands, sidebar and pattern commands, project commands, automation
commands (what the agent and MCP call), capture. `getHost()` stays the host seam.

### 5. Project environment out of the runner session

`ProjectEnvironment` (venv, missing deps, kumiki version check, docs sync, the `kigumi.yaml` record)
leaves `PythonRunnerSession`, which keeps the process and protocol. Fixes on the way: re-check after a
`.venv` is deleted (setup is cached for the app's life today), and decode stderr as a stream.

### 6. viewer-app.js, last

The 2,849-line class splits along the panels it already has (selection, measuring, drawing, layers,
assembly timeline) into modules it wires, with its message handling as a table like §3's. Highest
risk and least test cover: before it, extend the agent panel's Electron driver to load the viewer
page and drive selection and measuring, so the split has a net.

## Order and how

1. **runner package (§1)** — mechanical moves, no behaviour change; the re-exports keep every test
   green from the first commit. One PR, a commit per module moved.
2. **command table both sides (§2)**.
3. **frame-view-session (§3)**, then **kigumi-app (§4)**.
4. **ProjectEnvironment (§5)**.
5. **viewer test net, then viewer-app (§6)**.

Each step is a PR (they are review work), moves kept apart from behaviour changes so a diff of a
move is a diff of nothing but location. No rewrite to TypeScript or a framework; same languages,
same protocols.

## Decisions needed

- Package name for the runner modules (`kigumi_runner` above).
- Whether tests should keep importing `runner` (re-exports stay) or move to the owning modules
  (re-exports go; better long term, a bigger test diff).
- How far to push pure geometry from the runner into kumiki (§1, second bullet).
