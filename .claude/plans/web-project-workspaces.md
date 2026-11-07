# Project workspaces on the web

Status: intent only, not started. Written down while building the standalone app's project page
(New Project, Open Project, Recent projects; `list_projects` / `new_project` / `open_project` /
`close_project` for the agent).

## What the user asked for

- The web version keeps projects in the browser's storage, and can hold several project workspaces.
- The project page says plainly, wherever a project is made or opened:
  "Your files are saved to browser storage, NOT to disk and NOT to the cloud. We don't do cloud files yet."
- Export to disk: save a whole project workspace as a .zip the user downloads.

## To work out when it starts

- Where the files live: IndexedDB (or the origin private file system) rather than localStorage, which
  is too small and synchronous. Ask for persistent storage (`navigator.storage.persist()`) so the
  browser doesn't evict it.
- How Python runs there (Pyodide?) and how kumiki gets into a browser project, in place of `.venv`.
- Import a .zip as a new project, as the other half of export.
- The same project page and agent tools as the app, over a different store: keep the page's
  New / Open / Recent and the tools' shape the same, so the agent instructions hold for both.
