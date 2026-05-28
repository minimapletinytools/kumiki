---
applyTo: "kigumi/**"
---

# Kigumi Frontend Agent Rules

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

## Theme System Policy

- Use a single theme registry for viewer appearance: background, UI chrome tokens, and default timber/accessory render profiles should be selected together.
- Do not add separate background-only presets alongside the unified theme selector.
- Do not reintroduce the `blueprint` viewer theme.
- Prefer semantic CSS variables (`--hv-*`) for UI colors; avoid adding new hard-coded color literals in component rules.

## Running Tests

Always run the fast baseline tests after Kigumi changes:
```bash
cd kigumi && npx jest && npm run test:ext:initial
```

- `npx jest` — unit tests (file-watcher, runner-protocol, selection-store)
- `npm run test:ext:initial` — fast integration checks for initial sidebar/viewer/panel correctness

If a touched feature has complex behavior, run targeted complex integration tests:
```bash
cd kigumi && npm run test:ext:complex:grep -- "<feature or test name>"
```

Examples:
- Sidebar grouping behavior: `cd kigumi && npm run test:ext:complex:grep -- "toggles sidebar grouping"`
- Multi-file viewer lifecycle: `cd kigumi && npm run test:ext:complex:grep -- "switches fixtures"`
- Existing milestone flow behavior: `cd kigumi && npm run test:ext:complex:grep -- "milestone fixture"`

Before merging broad Kigumi UI/session/protocol work, run the full complex suite:
```bash
cd kigumi && npm run test:ext:complex
```

Keep iteration fast:
- Baseline tests are mandatory for all Kigumi edits.
- Complex tests should be feature-targeted during active development and run fully before merge for high-impact changes.
