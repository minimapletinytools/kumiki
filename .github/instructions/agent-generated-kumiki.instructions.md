---
applyTo: "kumiki/**,tests/**,patterns/**,hidden_structures/**"
---

# Agent-generated Kumiki coding supplement

> **AGENT-GENERATED — supplemental, not human-authored policy.** Reviewed 2026-11-13 against `b7fdf0d8`. Existing instructions and user decisions take precedence. Source may have changed since this review.

This supplements [AGENTS.md](../../AGENTS.md), the [library authoring rules](authoring.instructions.md), [concepts](../../docs/concepts.md), and [design usage instructions](../../docs/agent_usage_instructions.md). It does not replace them. See the [architecture guide](../../docs/internal/agent-generated/kumiki-architecture.md) for code navigation and the [review scope](../../docs/internal/agent-generated/README.md) for limitations.

## Reading the guidance

**Existing rule** means a requirement already stated in canonical instructions. **Observed convention** means an inference from code/history, with uncertain authorship. **Agent recommendation** is additional guidance from this review, not a claim about the user's handwritten style. Where older descriptions differ from current implementation, inspect source and resolve the specific discrepancy; do not silently rewrite authored prose.

## History evidence and uncertainty

Git author identities are shared by manual and agent-assisted work. These are candidate examples of human editing intent, not verified handwritten implementations. Links preserve the reviewed diffs; old paths need not exist today.

| Evidence | What it supports | Confidence and limit |
| --- | --- | --- |
| [`3e818861`, cleanup measurement](https://github.com/minimapletinytools/kumiki/commit/3e8188611d25770c1f80badef50bb000d5d7e971) | Explicit local/world conversion vocabulary and inward-positive face measurements; coordinated API/test changes | Likely editorial intent; authorship unconfirmed |
| [`8db31a2a`, review identity.py](https://github.com/minimapletinytools/kumiki/commit/8db31a2aa070f8b2d2ad861e722b4b4e0fa72887) | Concrete semantic descriptions, less abstract machinery, explicit duplicate-name behavior | Strong review-style evidence; still not proof of authorship |
| [`bdd128c3`, mark_plane_from_edge_in_direction](https://github.com/minimapletinytools/kumiki/commit/bdd128c3c4b0742214d2b2365b2baa6b6b2feafb) | Direct geometry calculation with named quantities and a domain-valued result | Weaker evidence; code may have been assisted |

The first two changes support conventions that also agree with current canonical instructions. The third is illustrative only. Do not copy incidental formatting, long historical docstrings, or an old implementation just because it appears in these commits. Explicitly agent-assisted changes such as `da686a8e` (float math migration) explain architecture but are not evidence of handwritten style.

## Keep operations concrete

**Existing rule:** Prefer simple functional operations on immutable data, using the types and helpers in `rule.py`. Avoid unnecessary abstraction and indirection.

**Observed convention:** The measurement and identity review changes favor concrete domain terms and visible transformations over general-purpose wrappers. A short calculation that locates a feature, projects a distance, and returns a marking is a useful model.

**Agent recommendation:** Start a helper at a repeated domain operation, not at a repeated line of syntax. Prefer an arrangement, marking, cutting, or feature reference over a dictionary whose keys recreate those types. Do not introduce a generic registry, inheritance hierarchy, or callback pipeline for one cutter. Conversely, reuse the existing build-a-butt and relief helpers when they already express the operation.

## Make geometry spaces visible

**Existing rule:** Global markings end in `_global`; local markings use `_<timber_name>_local` when multiple members are in scope. Document ambiguous orientation, units, and assumptions. Respect inward-positive face measurements and centerline-relative cross-section positions.

**Observed convention:** The measurement cleanup explicitly separates locating, marking, and scribing. These names communicate which coordinate description changes.

**Agent recommendation:** Establish one meaningful reference space for a calculation, then transform at explicit boundaries. Avoid passing a bare vector through multiple helpers while its space changes silently. Include a rotated or unequal-member case when a default or transformation could accidentally depend on the canonical example.

Use library comparison/normalization helpers where numerical tolerance matters. Current scalars are floats; do not revive assumptions of global symbolic exactness. The existing prohibition on epsilon offsets to hide CSG/Z-fighting errors still applies: comparison tolerance is not permission to deform modeled geometry.

## Preserve the construction/cutting boundary

**Existing rule:** Cutter names begin with `cut_`, take their arrangement first, return `Joint`, and put relief configuration last when supported. Validate constraints with informative errors. Supply end-cut metadata when applicable and add relief only when needed.

**Agent recommendation:** Put relationships between members in construction/arrangements and removed-solid calculations in cutters or shavings. A basic cutter should calculate defaults and delegate to the general implementation. Test defaults against different receiving depths and member orientations. Do not add an alignment-specific basic unless it materially simplifies the general basic.

Keep physical geometry, accessory creation, and assembly freedoms consistent, but do not infer one solely from the presence of another. A peg displayed in the right position does not prove that both holes or the allowed assembly directions are correct.

## Treat names as references

**Existing rule:** Use structural snake_case CSG labels, omit redundant kinds/joint names, avoid repeated labels along one path, and reserve `top_end_cut`/`bottom_end_cut` for generated end cuts.

**Observed convention:** The identity review distinguishes organization by authored name from disambiguation within a frame. A name can conflict; resolving it is a separate operation.

**Agent recommendation:** Keep runtime feature handles separate from serializable paths. Resolve paths against the current frame after rebuilds. Do not use a mesh index, object identity, or duplicate-name occurrence as an unconditional stable identifier. If changing labels, inspect selection, drawing, export, and tests that depend on the path.

## Keep lower layers independent

**Existing rule:** CSG imports nothing from drawings. Shared unbounded geometry belongs below both layers.

**Agent recommendation:** Put geometric freedom/constraint logic in CSG solving; adapt drawing measurements in `drawings/measure_solving.py`. Keep sheet placement and visibility out of core solid primitives. When measuring a feature on a cut member, distinguish its unbounded carrier from its surviving extent. Preserve unresolved-feature reporting from automatic dimensioning.

Do not make optional CAD/rendering dependencies mandatory for importing basic modeling APIs. Keep float-array/mesh conversion at explicit adapter boundaries, even though scalar calculations are already float-backed.

## Write only useful comments

**Existing rule:** Follow AGENTS.md: verb-first function docstrings, concise module descriptions, explicit non-obvious meanings and assumptions, one-line inline comments for non-obvious steps, and preserved TODOs. Put rationale/history in the PR or commit.

**Observed convention:** The identity review replaces metaphor and extended rationale with what a path means, how duplicate names resolve, and whether a referenced feature is guaranteed to exist.

**Agent recommendation:** Explain a non-obvious sign, coordinate space, tuple element, or failure condition. Do not restate a signature or narrate each algebraic operation. Leave user-authored prose alone for stylistic reasons. Discuss a correction first when the task's authorship constraints require it; uncertainty is not permission to classify prose as agent-written.

## Examples are executable teaching material

**Existing rule:** Follow the canonical pattern and whole-frame formats. Kiwari controls dimensions, positions, notches, and peg shapes; meaningful geometric configurations use variants. Keep folder paths free of simultaneous leaf/parent examples. Frame preambles explain purpose and demonstrated concepts. Public examples and development fixtures have separate locations.

**Agent recommendation:** Make each builder readable from placement through cutting. Prefer named dimensions and direct construction calls over a miniature framework inside an example. Declare only adjustable values that the example actually uses, return the resolved Kiwari, and keep structural-count parameters distinguishable from sizing parameters. Validate discovery as well as execution after reorganizing entries.

## Verification and review

**Existing rule:** Library/test changes require the full Python suite and type checking, as specified in [authoring rules](authoring.instructions.md). Joint tests must check real geometry. Never add/remove the hand-verified camel marker without user authorization, and do not delete marked tests.

**Agent recommendation:** Match evidence to the change: containment/boundary samples for cuts; transformed configurations for spaces; feature resolution for labels; discovery/build checks for examples; solver results for dimensions. A snapshot of node counts alone rarely proves a joint correct. Inspect rendered geometry for visual changes, following the existing screenshot instructions.

For documentation-only changes, check source claims, relative links, referenced paths, and whitespace. State that runtime tests were not run rather than implying that a source review verifies behavior.
