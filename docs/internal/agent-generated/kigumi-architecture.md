# Kigumi architecture and code navigation

> **AGENT-GENERATED — supplemental, not human-authored policy.** Reviewed 2026-11-13 against `b7fdf0d8`. Existing instructions and user decisions take precedence. Source may have changed since this review.

Read the [frontend rules](../../../.github/instructions/kigumi-viewer-frontend.instructions.md) first. Paths below are relative to `kigumi/` unless otherwise specified. The shared application runs in VS Code, Electron, and a browser; host capabilities differ.

## Runtime boundaries

```text
VS Code / Electron / browser host adapter
                  |
          shared application + sessions
             |                  |
   Python runtime/runner     webview messages
             |                  |
       Kumiki Frame        viewer stores + UI + Three.js
```

`extension.js` activates the VS Code host. `host.js` exposes host services to shared modules. `kigumi-app.js` creates the shared application, registers commands, and manages frame and pattern sessions. `hosts/` supplies platform implementations. Core orchestration must not import VS Code or Lit to perform domain work.

The native orchestration modules use CommonJS; browser webview modules use ESM. The Pyodide build bundles shared orchestration with selected runtime replacements. A module being JavaScript does not mean it can use Node facilities in every host.

## Opening and rebuilding a frame

1. Discovery identifies a file and decorated entry without building every example.
2. The application obtains a view session and a Python runtime for the project.
3. `frame-view-session.js` coordinates build/refresh requests, watched dependencies, user state, and viewer updates.
4. `runner-session.js` correlates requests and responses from the native runner process. `runner.py` loads the entry and builds a Kumiki frame in a slot.
5. The viewer receives frame metadata and geometry. Additional meshes, features, drawing information, or exports may be requested later.
6. File changes, parameter changes, or explicit refreshes begin new work. Superseded work must not replace the current frame.

A session, runner process, runner slot, and webview panel are different lifetimes. Several sessions can share a runner. Disposing a view must release its own listeners and state without killing a runner another view owns.

## Orchestration and Python execution

| File | Responsibility |
| --- | --- |
| `frame-view-session.js` | Per-view refresh sequencing, watches, state, runner ownership, disposal |
| `runner-session.js` | Process startup, ready state, request IDs, response buffering, pending requests |
| `python-runtime.js` | Native runtime capability boundary for launching/executing Python |
| `runner.py` | Frame slots, import/reload, serialization, geometry, selection, drawings, assembly, export, finishing |
| `message-types.js` | Declared viewer/sidebar message vocabulary |
| `webview-request.js` | Correlated webview round trips, timeouts, and listener cleanup |
| `viewer.js`, `webview-html.js` | Viewer surface setup and page/resource generation |
| `export-requests.js` | Export request coordination |
| `file-watcher.js`, `frame-file-watcher.js` | Watching and translating changes into refresh work |

The native Python protocol is newline-delimited JSON with request correlation. Keep diagnostic output on stderr; stray stdout can corrupt protocol parsing. Process output chunks are not guaranteed to align with JSON lines.

`runner.py` is a long-lived process, not a fresh interpreter per frame. Slots separate frame content while imports and other process resources are shared. Reload and cache invalidation matter when code changes. Do not assume a slot identifier alone proves that an asynchronous result still belongs to the latest build.

Finishing jobs can outlive the initial frame response and can be superseded or cancelled. Preserve the existing cancellation/progress contract. Failure behavior and previous valid state are intentional concerns: distinguish a failed refresh from a successful empty frame.

Use `webview-request.js` for request/reply interactions that need correlation. A listener must settle at most once and be removed on success, failure, timeout, and disposal. Round-trip replies and ordinary view events have different dispatch needs.

## Host implementations

| Host | Entry points and platform work |
| --- | --- |
| VS Code | `hosts/vscode.js`, `extension.js`: workspace, settings, commands, panels, editor integration |
| Electron | `hosts/electron/main.js`, `electron-host.js`, `app-window.js`, `shell-preload.js`: windows, IPC, filesystem/dialog services |
| Browser | `hosts/pyodide/browser-host.js`, `worker/main.js`, `page/transport.js`: worker orchestration, page surfaces, virtual project files |

The files after each host directory in this table are in that same directory, except the explicitly named root entry files.

`app-shell/host-services.js` supplies reusable app services. `project-lifecycle.js` sequences project switches and unsaved-edit decisions. `panel-registry.js`, `page-store.js`, `editor-tabs.js`, and `tab-list.js` manage surfaces and editor state; settings, watching, logs, and inspection have separate modules alongside them.

Electron's preload/IPC boundary exposes application operations to renderer code. Keep native capabilities behind that boundary. Account storage, updates, recent folders, and window behavior belong in host modules, not viewer geometry modules.

The browser runs shared core logic in a worker. `hosts/pyodide/worker/python-runtime.js` and `python/kigumi_pyodide.py` connect it to Python. `worker/shims/` replaces selected Node facilities. `build.mjs` assembles the browser application and Python assets. `manifold3d.py` bridges mesh operations to Manifold Wasm.

Browser projects persist through `hosts/pyodide/page/web-projects.js` and IndexedDB; settings use browser storage. Saved agent conversations also persist in IndexedDB: `worker/main.js` restores them into the worker filesystem and sends updates back to the page. The worker filesystem itself is in memory. Browser execution does not have native subprocess/package-install capabilities. An executing synchronous Python call cannot simply be interrupted like a native child process; distinguish cancelling queued work from interrupting active computation.

## Discovery, environments, and project docs

| File | Responsibility |
| --- | --- |
| `project-root.js` | Recognize local library development versus configured projects |
| `python-env.js`, `python-toolchain.js` | Environment/dependency checks, Python and uv setup |
| `project-initializer.js` | Project configuration and starter files |
| `frame-scanner.js`, `discovery-adapter.js`, `dependency-discovery.py` | Entry/dependency discovery and library integration |
| `sidebar-model.js` | Sidebar model and grouping |
| `pattern-source-utils.js` | Find/copy pattern sources |
| `project-docs.js` | Synchronize library-version-matched documentation into projects |
| `scripts/prepare-bundled-instructions.js` | Prepare the bundled design-authoring instructions |

Discovery delegates to Kumiki's librarian rather than importing every frame to list it. Source changes can affect discovery, dependency watches, and build execution separately.

A user's project can use a different installed Kumiki version than this checkout. Environment resolution and documentation sync must respect that version. `project-docs.js` owns `.kigumi/docs/` and its marked AGENTS block; it does not own arbitrary user prose outside that block. The generated usage-instructions bundle comes from `docs/agent_usage_instructions.md`, not these internal supplements.

The starter embedded in `project-initializer.js` is checked against the repository's `patterns/structures/my_cute_frame.py`. Update the matching contract/test when changing that recipe.

## Viewer ownership

| Modules under `webview/` | Responsibility |
| --- | --- |
| `viewer-app.js` | Compose viewer behavior and UI |
| `viewer-rendering.js`, `scene-manager.js`, `scene-store.js` | Scene updates, geometry state, rendering resources |
| `selection-store.js`, `hover-state.js`, `feature-states.js`, `member-states.js` | Selection/hover and feature/member state |
| `layer-state-store.js`, `display-options-store.js` | Visibility and display choices |
| `viewer-picking.js`, `pick-tolerances.js`, `member-id-buffer.js` | Picking and hit interpretation |
| `input-controller.js`, `camera-controller.js`, `camera-controls.js` | Input and camera interaction |
| `viewer-measuring.js`, `measurements.js`, `measure-draft.js` | Measurement interaction and draft state |
| `viewer-drawings.js`, `drawing-panel.js`, `drawing-export.js` | Drawing views and export |
| `drawing-overlays.js`, `dimension-text.js` | Dimension display |
| `viewer-assembly.js`, `assembly-timeline.js` | Assembly playback |
| `kiwari-values.js`, `units.js`, `tag-index.js` | Parameter, unit, and tag presentation helpers |

Lit components adapt state to UI. Keep state transitions, geometry decisions, and protocol shaping usable without Lit. A Three.js object is a rendering resource, not the persistent identity of a Kumiki feature. Rebuilds can replace meshes while user selection still needs reconciliation against authored/resolved paths.

Geometry replacement also requires resource cleanup. Releasing a panel's JavaScript references alone may not dispose GPU buffers, materials, event listeners, or pending animation work. Use the lifecycle owned by the scene/session rather than adding independent cleanup timers.

Keep appearance changes within the existing theme registry and display settings. Background, UI tokens, and default material profiles should change together rather than acquiring separate hard-coded defaults.

## Agent tools and external integrations

`agent/agent-loop.js`, `agent-session.js`, `agent.js`, and the turn/request modules coordinate model interactions. `agent/tools.js` defines shared tools; project, session, frame, and file modules implement operations. `permission-gate.js` and `permissions.js` handle app permission decisions. Filesystem boundaries and permission decisions solve different problems and both must remain intact.

`agent/kumiki-api.js` and `kumiki_api.py` inspect runtime APIs. The source/search modules locate library source. `project-context.js`, `kumiki-docs.js`, and prompt modules assemble context. `conversation-store.js` and checkpoints manage conversation/edit history. `panel-directory.js` and `selection-history.js` expose app state to tools.

MCP shares application tools through `mcp-service.js`. Native HTTP transport lives in `mcp-http.js`; browser connectivity uses `mcp-relay.js`. Do not infer browser MCP support from an older README's limitations section. The relay's backend lives outside this repository; this review covers the client contract only.

## Tests, builds, and investigation routes

`__tests__/` covers modules and runner contracts with Jest. `test/` contains real VS Code initial/complex integration suites; `test/app/` covers Electron. `hosts/pyodide/test/` has browser and MCP smoke tests. Check each host's README/package scripts for prerequisites; browser MCP tests can require the separate backend.

The canonical baseline is `cd kigumi && npx jest && npm run test:ext:initial`. Add targeted complex tests for affected features and the full complex suite before merging broad UI/session/protocol changes. Real extension windows must remain visible for animation-frame-dependent tests.

`package.json` defines extension preparation, Electron distribution, and test commands. Electron packaging and the Pyodide build are different release paths. Do not treat a passing Jest run as proof that a browser bundle or packaged app works.

For stale frames, trace watcher → session refresh sequence → runner slot/reload → viewer update. For wrong picking, trace member identity → scene state → hit interpretation → selection store. For browser-only failures, inspect runtime capabilities and worker/page transport before adding host checks throughout shared code. For disappearing project edits, inspect project lifecycle, editor state, and persistence ownership together.
