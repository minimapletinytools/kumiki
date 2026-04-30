---
applyTo: "kumiki-viewer/**"
---

# Kumiki Viewer Frontend Agent Rules

## Goal
Keep frontend implementation migration-safe so Lit can be swapped to React later with minimal churn.

## Architecture Boundaries

- Keep framework-specific UI code isolated to webview UI adapter files.
- Keep viewer domain logic framework-agnostic wherever possible (state transforms, geometry update decisions, session protocol payload shaping).
- Do not mix VS Code extension lifecycle logic with UI framework logic.

## Framework Isolation Rules

- Lit imports (`lit`, `LitElement`, `html`, `css`) must stay inside viewer/webview UI adapter code.
- Do not import Lit into extension orchestration modules (`extension.js`, runner/watcher/session modules).
- If adding helpers used by both UI and non-UI code, place them in framework-neutral modules.

## Migration-Safe Conventions

- Treat the UI as an adapter layer over a stable data contract (`frame`, `geometry`, refresh messages).
- Keep message protocol explicit and versionable (message type + payload shape).
- Avoid coupling business logic to Lit lifecycle semantics; keep lifecycle methods thin and delegate to plain methods.
- Prefer pure utility functions for calculations and formatting where practical.

## Scope Discipline

- Implement only requested UX changes.
- Avoid introducing broad frontend dependencies unless explicitly requested.
- Keep the current Three.js scene behavior intact unless task requirements ask for a rendering behavior change.

## Running Tests

Always run viewer tests after making changes:
```bash
cd kumiki-viewer && npx jest && node ./test/run-extension-tests.js
```

- `npx jest` — unit tests (file-watcher, runner-protocol, selection-store)
- `node ./test/run-extension-tests.js` — VS Code extension host smoke tests (downloads a test VS Code instance, activates the extension, verifies commands register and execute)
