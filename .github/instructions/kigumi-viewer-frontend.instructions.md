---
applyTo: "kigumi/**"
---

# Kigumi Frontend Agent Rules

## General Coding Philosophy

Kigumi code is entirely agent coded, as such extra discipline is needed. Agents LOVE introducing ad-hoc fixes for issues the user reports. These should be avoided as much as possible. Instead always consider systemic changes that cover the edge cases by design and weigh their introduced complexity over tech debt of layered ad-hoc fixes. When modifying code, also look for existing ad-hoc changes that might have new opportunities to be expressed through better architectural decisions. It's an iteraive process as we better understand the system requirements.

## Architecture Boundaries

- Keep framework-specific UI code isolated to webview UI adapter files.
- Keep viewer domain logic framework-agnostic wherever possible (state transforms, geometry update decisions, session protocol payload shaping).
- Core logic should be platform agnostic, as we deploy to web, electron, and VSCode extension

## Framework Isolation Rules

- Lit imports (`lit`, `LitElement`, `html`, `css`) must stay inside viewer/webview UI adapter code.
- Do not import Lit into extension orchestration modules (`extension.js`, runner/watcher/session modules).
- If adding helpers used by both UI and non-UI code, place them in framework-neutral modules.

## Migration-Safe Conventions

- Treat the UI as an adapter layer over a stable data contract (`frame`, `geometry`, refresh messages), but don't be afraid to break this rule either, in which case a minor version bump is needed.
- Keep message protocol explicit and versionable (message type + payload shape).
- Avoid coupling business logic to Lit lifecycle semantics; keep lifecycle methods thin and delegate to plain methods.

## Scope Discipline

- Implement only requested UX changes.
- Avoid introducing broad frontend dependencies unless explicitly requested.

## Theme System Policy

- Use a single theme registry for viewer appearance: background, UI chrome tokens, and default timber/accessory render profiles should be selected together.

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

`npm run test:ext*` launches real VS Code extension-host windows on screen. Automation flows that wait on webview `requestAnimationFrame` (e.g. `kigumi.captureScreenshot`) can stall or time out if the OS moves focus away from those windows mid-run (e.g. alt-tabbing to another app) — rAF is suspended while a webview panel isn't visible/focused. If these tests hang or fail flakily, avoid switching windows/apps while they run before assuming it's a product bug.
