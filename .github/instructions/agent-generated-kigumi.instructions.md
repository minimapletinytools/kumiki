---
applyTo: "kigumi/**"
---

# Agent-generated Kigumi coding supplement

> **AGENT-GENERATED — supplemental, not human-authored policy.** Reviewed 2026-11-13 against `b7fdf0d8`. Existing instructions and user decisions take precedence. Source may have changed since this review.

This supplements [AGENTS.md](../../AGENTS.md), the [frontend rules](kigumi-viewer-frontend.instructions.md), and applicable [library authoring rules](authoring.instructions.md). See the [architecture guide](../../docs/internal/agent-generated/kigumi-architecture.md) for ownership and file locations.

**Existing rule** below refers to canonical instructions. **Agent recommendation** means guidance inferred from this review of the implementation. Kigumi is described by its existing instructions as agent-coded; these recommendations do not claim handwritten provenance.

## Choose the owner before adding behavior

**Existing rule:** Shared core logic is platform-agnostic; framework-specific UI belongs in adapters. Avoid layered ad-hoc fixes and unnecessary dependencies. Implement the requested UX scope.

**Agent recommendation:** Route a change to its owner: host capabilities to a host adapter, project switching to app-shell lifecycle, build state to the frame session, Python execution to the runtime/runner, viewer state to its store, and presentation to a UI adapter. Before adding a second event listener or cache, find the component that already owns that state.

Use host/runtime capabilities rather than scattering checks for Electron, VS Code, or browser throughout shared logic. Keep CommonJS orchestration and ESM webview boundaries compatible with their actual build paths. Browser code cannot assume native filesystem, child process, or package installation support.

## Make asynchronous ownership explicit

**Agent recommendation:** Each request needs a clear owner, completion path, and cancellation/disposal behavior. Use existing request IDs, refresh sequencing, and slot ownership rather than inventing parallel freshness flags. Distinguish process lifetime, slot lifetime, session lifetime, and panel lifetime.

After an asynchronous operation, check whether the owning session/build is still current before applying state. Unsubscribe watchers/listeners and settle pending requests on every terminal path. Disposing one session must not terminate a shared runner it does not own. Use `webview-request.js` for correlated webview round trips rather than duplicating timeout/listener code.

A timeout does not necessarily stop the underlying job. A browser cancellation may only cancel queued work. Preserve these distinctions in state transitions and user messages. For project switches, use the existing serialized lifecycle and unsaved-edit flow.

## Keep protocols explicit

**Existing rule:** Viewer contracts should remain explicit and versionable; coordinate intentional contract breaks with the versioning rule in the canonical frontend instructions.

**Agent recommendation:** Update message declarations, sender, receiver, and relevant tests together. Document payload meaning at the boundary, especially IDs, optional fields, units, and frame/slot ownership. Keep diagnostic output off Python protocol stdout. Buffer partial process output until complete JSON lines are available.

A successful transport response, successful frame build, and completed finishing job are different outcomes. Preserve useful errors and avoid mapping all failures to empty data. If a refresh fails, follow the existing previous-frame/error behavior rather than silently showing an apparently successful stale frame.

## Keep viewer state independent of components

**Existing rule:** Lit imports belong in webview UI adapters, not session/watcher/runner orchestration. Lifecycle methods stay thin; shared logic is framework-neutral.

**Agent recommendation:** Put selection, hover, visibility, parameter conversion, and geometry-update decisions in plain modules/stores. Components subscribe and render. Do not store authoritative feature identity only on a Three.js object or in a DOM attribute. Reconcile authored/resolved paths when the model is rebuilt.

Dispose rendering resources through their scene lifecycle when replacing geometry. Avoid timer-based fixes for ordering problems that should be represented in state. Keep temporary measurement drafts separate from committed measurements and respect the existing undo ownership.

**Existing rule:** Use the single theme registry for background, chrome, and default material profiles. Do not add isolated appearance defaults to fix one component.

## Respect project and persistence boundaries

**Agent recommendation:** Resolve the project's environment and installed Kumiki version before inspecting APIs or copying documentation. Do not assume the checkout's library version is the user's version. Use the existing project-root/configuration helpers.

`project-docs.js` owns its managed docs directory and marked instruction block. Preserve user text outside that block. New internal developer guidance should not accidentally enter project-facing instructions; `docs/internal/` is excluded from that sync.

Use host-backed persistence rather than raw filesystem calls in shared code. Specify whether new state is per-view, per-project, per-account, or application-wide. Verify that persistence exists on each supported host. In the browser, project files and saved conversations are persisted by the page; worker filesystem writes need the appropriate synchronization path to survive a reload.

Keep the embedded starter recipe and its tested repository counterpart consistent. When moving patterns or examples, check librarian discovery and sidebar behavior as well as the filesystem layout.

## Reuse tool implementations and permission boundaries

**Agent recommendation:** Reuse shared app tool operations across embedded-agent and MCP transports. Keep protocol/transport concerns out of geometry and project operations. Do not create a second implementation of file editing or frame checking for a new transport.

Honor both permission decisions and project path boundaries. One does not replace the other. Keep credentials and native capabilities behind the existing host/account/storage services. Test changes at the actual boundary touched; mocks of successful tool calls do not verify path handling or denied/cancelled operations.

The browser MCP relay depends on a separate backend. State that dependency when testing or documenting it, and avoid claiming client tests validate the server implementation.

## Comments and testing

**Existing rule:** Follow AGENTS.md for concise comments; explain non-obvious semantics rather than narrating code. Follow the frontend instructions for the mandatory Jest and initial extension baseline, targeted complex tests, and full complex testing before broad merges.

**Agent recommendation:** Test state transitions and contracts at their owning layer. High-value cases include out-of-order responses, disposal during a request, a failed refresh after a valid frame, shared-runner ownership, project switches with edits, and selection after geometry replacement. Add cases relevant to the change rather than duplicating every implementation branch.

Use real extension tests for panel/session behavior; Electron tests for native window/IPC behavior; browser smoke tests for worker/runtime/persistence behavior. A unit test with mocked Node facilities does not establish browser compatibility. Keep extension windows visible when tests depend on webview animation frames.

For documentation-only supplements outside `kigumi/`, source/link/diff checks suffice; do not claim runtime validation. For implementation changes, report which host and suites were actually exercised and any remaining limits.
