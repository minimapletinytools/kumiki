# Plan: Claude Agent SDK Panel for Kigumi

> **Context:** Embeds an AI assistant panel powered by the Claude Agent SDK into the right slot of the Kigumi standalone app. The SDK loop and tools execute on the backend (Node.js in Electron / container in Web), while the panel provides a streaming UI.

---

## 1. Objectives & Scope

- **Right Slot Chat Interface:** A dedicated right panel in the app shell (`slot-right`) that slides out and can be resized using the existing splitter.
- **Backend Execution Harness:** Run `@anthropic-ai/claude-agent-sdk` inside the Node.js core process (Electron main/core), keeping API keys, local filesystem access, and tool executions completely secure and isolated from browser DOM.
- **Kumiki Domain Tools:** Equip the agent with automation tools so it can inspect, modify, and verify parametric timber frames:
  - Read, write, and patch workspace files.
  - Run `runner.py` / inspect runner logs to diagnose syntax or solver errors.
  - Control the 3D viewer (open frame/pattern, trigger re-render).
  - Adjust camera view & take screenshots (giving multimodal Claude visual feedback on timber joints).
- **Human-in-the-Loop Permissions:** Approvals for modifying files on disk or executing shell commands.

---

## 2. Architecture & Communication Flow

```
┌────────────────────────────────────────────────────────┐
│ UI Shell (webview/agent/agent.html in iframe)          │
│                                                        │
│  • Message list (User, Assistant markdown, Tool chips) │
│  • Input prompt + Stop button                          │
│  • Tool approval confirmation dialogs                  │
└───────────────────────────┬────────────────────────────┘
                            │  postMessage / panel-bridge.js
                            │  ({ type: 'agent:prompt', text })
                            │  ({ type: 'agent:event', data: streamEvent })
┌───────────────────────────▼────────────────────────────┐
│ Kigumi Core (kigumi/agent/agent-session.js)            │
│                                                        │
│  Claude Agent SDK Harness                              │
│  ├── Model configuration (Claude 3.7 Sonnet)           │
│  ├── System prompt (Kumiki timber rules & concepts)    │
│  ├── Built-in tools: ReadFile, EditFile, ListFiles     │
│  └── Kigumi Custom Tools:                              │
│       • openInViewer(filePath)                         │
│       • refreshViewer()                                │
│       • setCamera(azimuth, elevation, distance)        │
│       • captureScreenshot()                            │
│       • runFrameDiagnosis(filePath)                    │
└────────────────────────────────────────────────────────┘
```

---

## 3. Implementation Steps

### Step 1: Dependencies & Settings Configuration
1. Add `@anthropic-ai/claude-agent-sdk` to `kigumi/package.json`.
2. Add agent configuration keys to `kigumi/hosts/electron/settings-store.js`:
   - `agent.apiKey`: User Anthropic API key (or fall back to `process.env.ANTHROPIC_API_KEY`).
   - `agent.model`: Default model (e.g. `claude-3-7-sonnet-20250219`).
   - `agent.autoApproveReadOnly`: Auto-approve read tools (default `true`).

### Step 2: Register Right Panel in App Shell
1. Update `kigumi/app-shell/panel-registry.js`:
   ```javascript
   const PANEL_TYPES = Object.freeze({
       explorer: { slot: 'left', icon: 'files' },
       viewer: { slot: 'center', icon: 'fish2-very-sad', redrawAfterReload: true },
       log: { slot: 'center', icon: 'output' },
       editor: { slot: 'center', icon: 'file-code' },
       agent: { slot: 'right', icon: 'sparkle' },
   });
   ```
2. In `webview/shell/shell.js`:
   - Add toggle button for Agent in the status bar or header.
   - When active, `slot-right` and `splitter-right` become visible (already implemented in `shell.js:renderPanels`).

### Step 3: Implement Agent Session in Core (`kigumi/agent/`)
Create `kigumi/agent/agent-session.js`:
1. **Initialize Agent Instance:**
   - Instantiate harness with user API key and system instructions (referencing `docs/agent_usage_instructions.md` and `docs/concepts.md`).
2. **Define Custom Kumiki Tools:**
   - `kumiki_open_viewer`: Calls `kigumiApp.openFile(filePath)`.
   - `kumiki_refresh`: Calls `session.requestRefresh()`.
   - `kumiki_set_camera`: Calls `session.setCamera(...)`.
   - `kumiki_screenshot`: Calls viewer screenshot API, returns image base64 data to Claude for visual analysis.
   - `kumiki_run_diagnosis`: Spawns runner on a frame file to return errors or geometry diagnostics.
3. **Event Streaming:**
   - As the agent loop progresses, serialize SDK events (`message_delta`, `tool_use`, `tool_result`, `done`) and forward them via `panelSurface.postMessage({ type: 'stream', ... })`.
4. **Permission Hooks:**
   - When the agent invokes a file edit or write tool, if permission is required, send `{ type: 'permission_request', id, tool, params }` to the UI and await response.

### Step 4: Webview UI (`webview/agent/`)
Create `webview/agent/agent.html` and `agent-app.js`:
1. **Chat Stream Rendering:**
   - Message list rendering markdown responses.
   - Collapsible tool invocation cards showing tool name, parameters, running status, and return output.
   - Thumbnail previews for image attachments / screenshots captured by the agent.
2. **Permission Prompts:**
   - Inline approval card: "[Agent wants to edit `patterns/my_bench.py`] [Allow] [Deny]".
3. **User Input Box:**
   - Textarea with autogrow, `Enter` to send, `Shift+Enter` for newline.
   - Stop generation button to abort active stream.
   - Quick prompt suggestions (e.g. "Fix syntax error in active frame", "Add mortise and tenon joint").

---

## 4. Verification & Testing

1. **Unit tests (`__tests__/agent-session.test.js`):**
   - Test tool invocation handling (mocking SDK calls).
   - Test permission gating and state streaming over IPC.
2. **Interactive smoke test (`test/app/smoke-driver.js`):**
   - Toggle open agent panel -> verify `slot-right` unhides and iframe loads.
   - Send mock prompt -> verify stream messages appear in the chat view.
   - Test tool trigger: verify `kumiki_open_viewer` successfully opens a center viewer tab.
