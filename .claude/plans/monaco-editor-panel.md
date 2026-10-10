# Plan: Monaco Editor Panel for Kigumi

> **Context:** Integrates Monaco Editor into Kigumi standalone app as a center-tab panel so users can view and edit `.py` frame and pattern files directly without depending on external editors (VS Code / Cursor).

---

## 1. Objectives & Scope

- **Center Tab Integration:** Open `.py` files inside a center slot tab in the app shell alongside viewer tabs.
- **Save & Refresh Loop:** Saving (`Cmd+S` / `Ctrl+S`) writes to disk and naturally triggers the existing watcher / `onDocumentChange` auto-refresh pipeline.
- **Deep-linking & Navigation:** "View source" and "Go to error" from the viewer open or reveal the Monaco tab at the corresponding line instead of spawning an external editor.
- **Dirty State Tracking:** Show dirty state dot/indicator on tab title when edits are unsaved, with confirm-on-close protection.
- **Scope Boundary:** No complex full-IDE features (no Git integration, terminal, debugger, or extension marketplace). Python syntax highlighting, basic bracket matching, and auto-indentation are provided initially; full LSP/pyright can be added later via `monaco-languageclient`.

---

## 2. Architecture & File Layout

```
kigumi/
├── app-shell/
│   └── panel-registry.js          # Add 'editor' panel type (slot: 'center', icon: 'file-code')
├── hosts/
│   └── electron/
│       ├── electron-host.js       # Route openFileAt / showFile to connection.openEditor()
│       └── app-window.js / main.js
├── webview/
│   ├── editor/
│   │   ├── editor.html            # Hosts the Monaco editor container
│   │   ├── editor.css             # Theme syncing with Kigumi CSS variables
│   │   └── editor-app.js          # Monaco lifecycle, postMessage bridge, keyboard shortcuts
│   └── vendor/
│       └── monaco/                # Vendored or npm-bundled Monaco distribution
```

---

## 3. Implementation Steps

### Step 1: Package & Bundle Monaco
- Add `monaco-editor` to `kigumi/package.json` (or vendor minified assets under `webview/vendor/monaco/`).
- Configure Monaco web workers (`editor.worker.js`). In Electron/webview:
  - Serve workers locally or configure `window.MonacoEnvironment = { getWorkerUrl: ... }`.
  - Ensure the Content Security Policy in `webview/shell/shell.html` and `editor.html` allows worker scripts (`worker-src 'self' blob:;`).

### Step 2: Register Panel Type
In `kigumi/app-shell/panel-registry.js`:
```javascript
const PANEL_TYPES = Object.freeze({
    explorer: { slot: 'left', icon: 'files' },
    viewer: { slot: 'center', icon: 'fish2-very-sad', redrawAfterReload: true },
    log: { slot: 'center', icon: 'output' },
    editor: { slot: 'center', icon: 'file-code' },
});
```

### Step 3: Editor Webview Page (`webview/editor/`)
1. **`editor.html`**:
   - Embeds Monaco loader and stylesheet.
   - Contains a `#monaco-container` `<div>` taking 100% height and width.
2. **`editor-app.js`**:
   - Acquires the VS Code-compatible bridge via `window.acquireVsCodeApi()`.
   - Listens for messages from core:
     - `{ type: 'init', filePath, content, line }`: Instantiates Monaco model with language `python`, sets content, jumps to `line`.
     - `{ type: 'revealLine', line }`: Scrolls and centers cursor on `line`.
     - `{ type: 'externalUpdate', content }`: Updates content if changed outside while clean.
   - Listens for user interactions:
     - On text change: notifies core `{ type: 'dirty', isDirty: true }`.
     - On `Cmd+S` / `Ctrl+S` (action shortcut): posts `{ type: 'save', content: editor.getValue() }`.
   - Adapts to theme changes (syncing Monaco theme with `--vscode-editor-background`, `--vscode-editor-foreground`, etc.).

### Step 4: Core & Host Wiring (`editor-session.js` & `electron-host.js`)
1. **Editor Manager in Core (`kigumi-app.js` / `shell-connection.js`):**
   - Track open editor instances by `filePath`. If file is already open, activate its existing tab and jump to line instead of duplicating.
   - On `{ type: 'save', content }`:
     - Write content to disk using Node `fs.writeFileSync`.
     - Reset dirty state.
   - On `{ type: 'dirty', isDirty }`:
     - Update tab title in `TabList` (e.g. `● my_frame.py`).
2. **Redirect External Editor Calls in `electron-host.js`:**
   - Update `openFileAt(filePath, line)` and `showFile(filePath)` to call the app's internal editor opener first.
   - Retain `app.editorCommand` as an option via a user setting ("Open in External Editor" button or right-click context menu).

### Step 5: Dirty Buffer Handling on Tab Close / App Exit
- In `TabList` / `shell-connection.js`:
  - When closing an editor tab with unsaved changes, prompt the user with `host.confirm({ message: 'Do you want to save the changes you made to ...?', action: 'Save' })`.
  - Handle Save / Don't Save / Cancel choices cleanly.

---

## 4. Verification & Testing
1. **Unit tests (`__tests__/editor-panel.test.js`):** Test editor panel registration, state transitions, save messaging, and line jump events.
2. **Smoke testing (`test/app/smoke-driver.js`):**
   - Open frame file in viewer.
   - Click "View source" -> verify editor tab opens and is active.
   - Edit a parameter value in Monaco -> trigger Save -> verify viewer auto-refreshes with the updated geometry.
