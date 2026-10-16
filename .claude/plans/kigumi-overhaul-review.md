# Review: `feat/agent-panel`, and thoughts on the Kigumi panel overhaul (2026-10-12)

## What the branch is

Checked out in the `kumiki-monaco` worktree. Three commits on top of `main` (main was merged in):

1. `1795afe7` Monaco editor panel. This is the commit in open PR #77 (`feat/monaco-editor`).
2. `bc6fea5e` layout toggle buttons and an agent panel scaffold.
3. `cacf5f1e` a custom draggable macOS title bar.

About 700 lines of real change, plus 14 MB / 110 files of vendored Monaco (excluded from the VS Code
package by `.vscodeignore`, so it only ships in the standalone app).

## Review

### Agent panel: a UI mock, nothing behind it
- `agent-app.js` posts `{type: 'agentPrompt'}` and listens for `agentResponse`; nothing in the host
  handles either. No model, no tools, no streaming, no stop, no history.
- The toggle disposes the panel, so closing and reopening it throws the conversation away. Hide it
  instead.
- Hard-coded "Claude Agent" / "Kumiki Assistant" and suggestion chips that nothing answers.
- `agent.html` allows `'unsafe-inline'` scripts; the viewer uses nonces. Fine for a scaffold, worth
  tightening before it talks to a model.

### Editor (from #77)
- **Unsaved edits can be lost.** `ShellConnection` gained a `closeRequest` hook for confirm-on-close,
  but nothing passes one: closing a dirty tab just closes it.
- **External changes are ignored.** The editor handles `externalUpdate`, but the host never sends it,
  so a file changed on disk (by you elsewhere, or by an agent) isn't reflected. `pendingContent` in
  `openEditorTab` is written and never read.
- Monaco is vendored whole: every language and worker. Python, JSON, Markdown and the editor worker
  would do; or take it from npm and bundle.
- The theme is fixed at load (no switch with the system); `unsafe-eval` in the editor CSP is
  Monaco's loader, acceptable.
- Saving writes the file directly; the file watcher picks it up, so auto refresh works.

### Title bar
- macOS only (`hiddenInset`), but the custom `<header class="titlebar">` is rendered everywhere, so
  Windows and Linux get it *and* the native frame. Hide it off macOS, or go frameless everywhere.

### Tests
- A unit test for editor tab titles, and smoke-driver checks for the editor, the explorer toggle and
  the agent toggle. Reasonable for what is there.

### Verdict
Fine as a starting point, not mergeable as an agent. The editor half should land through #77 once
dirty-close and external updates are handled (and the vendor trimmed); the agent half is a placeholder
for the design below.

## Thoughts on the overhaul

### No general docking yet: agree
Make the layout data rather than DOM: a list of slots, and which panel instances sit in each. Each
panel type declares the slots it may go in (`panel-registry.js` already says one). Docking later is
then "let the user move a panel to another allowed slot", not a rewrite.

### Tabs: views and source files together
Recommended: **two linked groups in the centre**, a code group and a view group side by side, each
with its own tabs, the way VS Code users already work with a file and its preview. Linked by file:
activating a view tab brings its source forward in the code group, and opening a frame file opens
(or offers) its view. Either group can be collapsed to give the other the full width.

Alternatives considered:
- One tab per frame holding a code | view split. Neat for one file, awkward for patterns shared by
  several frames, and two views of one file.
- Separate tabs with a "go to source / view" link. Simplest, but you lose sight of one while using
  the other, which is the main reason to have both in one window.

The VS Code host gets this for free (editor groups), so only the standalone app needs to build it.

### Generic panels vs view-specific panels: yes, move the view's panels out
Today the tree, selection info, measurement list, kiwari panel and log are drawn inside the viewer's
own page, over and under the 3D canvas. Moving them into a **view inspector** panel (a fixed slot,
whose content follows the active view) is the right call:
- The canvas gets its space back; the panels become ordinary scrolling, resizable UI.
- The same inspector works in VS Code as a `WebviewView` in the sidebar or the bottom panel.
- It forces what the agent needs anyway: a protocol for "what is in this view, and what is selected".

The cost is real: those panels share in-memory stores with the scene (selection, hover, scene store,
measure draft). Moving them out means a **view-state protocol** between the viewer page and the
inspector (selection, hover, focused feature, tree, measurements; commands back). Do that protocol
first, then move panels one at a time, starting with the least interactive (kiwari, log), the tree
last.

### Agent panel
Needs everything, but most of it lines up with work already planned
(`.claude/plans/claude-agent-sdk-panel.md`):

- **Querying panels.** A host-level registry already exists (`ShellConnection` knows every panel). Add
  a small, host-neutral contract each panel answers: `describe()` (what it is: file, frame, drawing)
  and `selection()` (what is selected, as data). The viewer's answer can start from the "copy for AI"
  text builder (`webview/selection-copy.js`). Then the agent's tools are `list_panels`,
  `active_panel`, `panel_selection(id)`.
- **Make Kigumi's tools an MCP server.** Open file, refresh, read logs, camera, screenshot, list
  panels, selection, run diagnostics, all already exist as automation commands. Exposed over MCP:
  - the built-in panel (Claude Agent SDK in the Electron main process) is one client;
  - in VS Code, users' existing agents (Claude Code, Copilot, Cursor) drive Kigumi with no agent
    panel of ours;
  - "can it hook up to other AIs" becomes yes by construction.
- **The built-in agent loop:** Claude Agent SDK in the core process (keys and files stay out of the
  page), streaming events to the panel, tool approval for file writes, stop, and conversations kept
  per workspace.

### Web: backend and accounts
Decide where Python runs on the web first (`.claude/plans/kigumi-desktop-web-vscode.md`, Decision 1);
the agent's backend follows from it:
- **Desktop:** bring your own API key, stored locally. No accounts needed.
- **Web:** requests to a model have to go through our server (a key can't live in the browser), which
  means sign-in (an OAuth provider, or a hosted auth service), per-user quotas and billing. If Python
  runs server-side too, the agent loop runs next to it in the user's container; with Pyodide in the
  browser, the server only proxies the model.

Ship desktop first; web after the Python decision.

## Suggested order

1. Land the editor through #77: dirty-close confirm, external updates, trimmed vendor.
2. Panel contract (`describe`, `selection`) and the layout-as-data model.
3. Kigumi MCP server over the existing automation commands plus the panel contract.
4. Agent panel on the Claude Agent SDK, using those tools.
5. View-state protocol, then move the view's panels into the inspector, one at a time.
6. Linked code and view groups in the centre (standalone app).
7. Web, after the Python-on-the-web decision.
