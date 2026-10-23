# Kigumi's MCP server under VS Code

Status: not started. The standalone app has it (Kigumi > Options > beta features > MCP server);
the VS Code extension does not.

## What exists

- `kigumi/agent/tools.js`: the tools, host-neutral. They need a panel directory (`app.panels`), a
  command runner (`app.commands[id](args)`) and the workspace folders.
- `kigumi/agent/mcp-http.js`: the HTTP server (stateless Streamable HTTP, bearer token, on
  127.0.0.1), with the clients it has seen.
- `kigumi/agent/mcp-setup.js`: the setup text for each agent.
- `kigumi/hosts/electron/main.js`: `syncMcpServer` (start, stop, restart on port change), the token,
  `mcpState`/`mcpControls`, and `copyMcpSetup`. The host hands `mcpControls` to the views as
  `host.mcp` (see `host.js`); the options panel shows the toggle and the MCP section only when it is
  there.
- `kigumi/.vscodeignore` leaves `agent/tools.js`, `agent/mcp-http.js` (and `agent/mcp-setup.js`,
  add it) out of the extension. The SDK and zod are already in `dependencies`.

## Steps

1. Move the host-neutral part of `syncMcpServer`, `mcpState`, `mcpControls` and `copyMcpSetup` out
   of `main.js` into `agent/mcp-controller.js`: given `settings` (get/set/onChange), a clipboard,
   a status line, the app and the workspace folders, it runs the server and returns `mcpControls`.
   `main.js` then calls it.
2. Settings: add `kigumi.mcp.enabled` (default false) and `kigumi.mcp.port` (default 7345) to
   `package.json`'s configuration, with nls strings. Keep the token out of settings: VS Code has
   `context.secrets` (SecretStorage); have the controller take a token getter.
3. In `extension.js`: build the controller over `vscode.workspace.getConfiguration('kigumi')`,
   `vscode.env.clipboard` and `context.secrets`, and pass its controls to the VS Code host
   (`hosts/vscode.js` gets an `mcp` property), so the views show the toggle and the section there too.
4. A command, "Kigumi: Copy MCP Setup", for the palette.
5. Take the agent files out of `.vscodeignore`.
6. Optional: register the server with VS Code itself
   (`vscode.lm.registerMcpServerDefinitionProvider`), so Copilot's agent mode finds it with no setup.

## What differs under VS Code

- `list_panels` lists only Kigumi's views: the VS Code host has no `listPanels`/`describePanel` for
  editor tabs. The view tools (camera, screenshot, log, refresh) work as in the app.
- One server per VS Code window: two windows on the same port would collide. Either a port per
  window (0, shown in the section) or only the first window serves.

## Tests

- The controller, with a fake settings store: start, stop, restart on a port change, token made once.
- `extension` tests: the setting starts the server; the copy command writes the setup.
