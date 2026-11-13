# Agent-generated developer guides

> **AGENT-GENERATED — supplemental, not human-authored policy.** Reviewed 2026-11-13 against `b7fdf0d8`. Existing instructions and user decisions take precedence. Source may have changed since this review.

These guides describe the implementation and offer additional coding guidance. They do not replace, edit, or claim approval of the handwritten documentation. Read [AGENTS.md](../../../AGENTS.md), [concepts](../../concepts.md), [library authoring rules](../../../.github/instructions/authoring.instructions.md), [frontend rules](../../../.github/instructions/kigumi-viewer-frontend.instructions.md), and [design usage instructions](../../agent_usage_instructions.md) first.

## Guides

| System | Architecture and navigation | Supplemental conventions |
| --- | --- | --- |
| Kumiki | [Kumiki architecture](kumiki-architecture.md) | [Kumiki conventions](../../../.github/instructions/agent-generated-kumiki.instructions.md) |
| Kigumi | [Kigumi architecture](kigumi-architecture.md) | [Kigumi conventions](../../../.github/instructions/agent-generated-kigumi.instructions.md) |

The architecture guides describe current source behavior. The conventions distinguish existing rules, observed patterns, and agent recommendations. Neither observations nor recommendations override the canonical instructions.

## Review scope and limits

The review traced the major library layers, joint construction, discovery, drawings, feature solving, assembly, the Python runner, viewer state, host adapters, project lifecycle, agent tools, tests, and packaging. It sampled implementations and Git history across these areas. This is an architecture and authoring review, not a line-by-line correctness, security, or performance audit. Generated bundles, vendored dependencies, and the separate backend repository were not audited.

Authorship is uncertain: manual and agent-assisted changes share Git author identities. A missing agent trailer does not prove that a change was handwritten. The conventions cite small review-oriented commits as evidence of likely human intent; none is presented as confirmed handwritten code. Explicitly agent-assisted implementations are not evidence of human implementation style.

## Repository boundaries

| Path | Role |
| --- | --- |
| `kumiki/` | Python geometry, joinery, drawings, discovery, and export library |
| `patterns/` | Public reference patterns and structures; also executable examples |
| `hidden_structures/` | Internal fixtures and development structures |
| `tests/` | Python behavior and geometry tests |
| `kigumi/` | VS Code, Electron, and browser applications and their shared runner/viewer |
| `website/` | Astro website, shared views, English/Japanese content |
| `tools/` | Repository maintenance, including the packaged pattern index |
| `.github/workflows/` | Build, release, and validation automation |
| `.claude/plans/` | Historical plans; not current architectural authority |

Kumiki and Kigumi have different licenses; check the applicable license before moving code between packages. Vendored assets retain their own licensing requirements.

Website changes follow AGENTS.md: English in `website/src/i18n/en.json` is the source, changed entries are translated into `ja.json`, and user wording is preserved. These internal developer guides are English only.

## Maintaining these supplements

Update the relevant guide when ownership, protocol, discovery, or numerical behavior changes. Verify claims against source and tests rather than extending an old description by analogy. Keep the agent-generated notice and record the reviewed source revision. Do not promote an inferred convention into user policy without an explicit user decision.

The guides live under `docs/internal/` because `kigumi/project-docs.js` excludes that directory from project-facing documentation sync. The separate instruction files link here without modifying the canonical hub. Agents whose tooling does not discover supplemental instruction files can start from this index.
