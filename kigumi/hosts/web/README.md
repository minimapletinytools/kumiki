# Kigumi in a browser

Kigumi's shell, explorer, viewers and code editor, in a browser tab. A Node server runs Kigumi's
core and the Python runner on the loopback interface; the browser keeps your projects.

```sh
cd kigumi
npm run web:start                      # http://127.0.0.1:7346
node hosts/web/server.js --port 8000 --venv /path/to/venv --data ~/.kigumi/web
```

- `--venv`: the Python environment every web project uses, with kumiki and its viewer
  dependencies installed. Defaults to `$KIGUMI_WEB_VENV`, then this checkout's `.venv` (`uv sync`).
- `--data`: the server's settings, log, and the open project's working folder. Defaults to
  `~/.kigumi/web`.

Node 22+. No build step and no added dependencies.

One tab drives Kigumi at a time: opening it in another tab takes over, and the tab before says so,
with **Use here** to take it back.

## Projects live in the browser

The page with no project open lists the projects this browser holds (IndexedDB), with **New
Project**, and **Export .zip** and **Delete** for each. It says so plainly: files are saved to
browser storage, not to disk and not to the cloud. Export a project to keep a copy.

```text
Browser (IndexedDB: every project's files)
   │ open: the whole project ──►        ◄── web:files: each change, as it happens
Server: working folder <data>/projects/<id>/  (.venv → the shared environment)
   │ Kigumi's core, runner and Python, as in the desktop app
```

- **Opening** a project sends its files to the server, which writes them into a fresh working
  folder, links its `.venv` to the shared environment, and switches Kigumi to it in place, as the
  desktop app does.
- **Every change** in that folder (a save in the code editor, a drawing saved, a frame file the
  runner writes) goes back to the browser, so the browser's copy is always whole. Closing the
  tab loses nothing.
- **New Project** makes the working folder with the starter frame, `my_cute_frame.py`.
- **Exports** (STL and so on, written to `kigumi_exports/`) arrive as browser downloads.
- What travels: the project's text files (`.py`, `.json`, `.md`, `.yaml`, ...), including saved
  drawings in `.kigumi/drawings/`. Not the venv, caches, logs, or the docs Kigumi writes. A project
  is at most 2,000 files and 20 MB, each file at most 2 MB.
- The project page's button in the status bar (the project's name) closes the project and goes
  back to the list.

## Settings and the agent

Kigumi's settings are kept in the browser too (localStorage). The page sends them to the server
when it connects, and the server's settings file mirrors them; each change goes back to the
browser. A browser with none of its own starts from the defaults.

The status bar's gear turns settings on and off; **Agent panel** is one (off by default), as is the
checkbox in a view's options. Turned on, the agent opens on the right. Signing in to a Kigumi
account doesn't work in a browser yet (it ends on a `kigumi://` link), so the agent's chat area
asks for an OpenRouter key: paste one in its own settings (the gear in its panel). The key is kept
with the other settings, in this browser, and never shown again. Conversations and the model list
are kept on the server.

**MCP server** is in the gear's list and the explorer's Kigumi options, as in the app: Kigumi's tools for agents on the server's
machine (Claude Code and others), on `127.0.0.1` with a token. "Copy MCP setup for Claude Code"
puts the command that adds it on the clipboard. Turned on, Kigumi options shows its address to copy,
the setup to copy for each agent, and how many agents are connected.

The agent's project tools work here too, by name: `list_projects`, `new_project`, `open_project` and
`close_project`, for the built-in agent and over MCP. The page keeps the server told of the
browser's projects (names only); opening one asks the page to send it.

## Files

| File | |
| --- | --- |
| `server.js` | HTTP, POST and server-sent events in place of Electron's IPC; the projects; starts Kigumi. |
| `browser-host.js` | The Host (`../../host.js`) for the browser. Files open in the shared code editor tabs (`../../app-shell/editor-tabs.js`). |
| `project-files.js` | Which files travel; writing a project into the working folder safely; watching it. |
| `transport.js` | In the page: the connection to the server. |
| `web-projects.js` | In the page: the projects in IndexedDB, and the projects page. |
| `zip.js` | In the page (and in tests): the .zip an export downloads. |
| `web.css` | The projects page's styles. |

`SettingsStore`, `LogChannel` and the glob matcher come from `../electron/`; none of them uses
Electron.

## Boundaries

The server binds to loopback only. It checks the Host header and request origins, takes messages
only from the one browser tab it is serving (a second tab is turned away), bounds message sizes,
serves files only from `webview/` and its own page files, and refuses project paths that would
leave the working folder. These are local browser boundaries: there is no user authentication, and
frames run Python with the server account's access. A hosted version needs an authenticated
gateway and a sandboxed worker per user; see `.claude/plans/kigumi-web-port-findings.md`.

Not here yet: signing in to a Kigumi account (use an OpenRouter key), importing a .zip,
several tabs driving Kigumi at once, and reconnecting after the server restarts (reload the page).

## Tests

```sh
npx jest __tests__/web-host.test.js    # HTTP boundaries, project files, the zip
npm run test:web                       # end to end in Chromium (Electron as the browser only)
```

The end-to-end test starts the server on a fresh data folder:
1. It makes a project in the page and builds the starter frame in a view.
2. It checks that a change on the server reaches the browser's copy, and opens a file in the editor.
3. It closes the project and reloads the page.
4. It exports the .zip and checks its contents.
5. It reopens the project from the browser's copy and deletes it.

A screenshot goes to `.artifacts/web/browser.png`.
