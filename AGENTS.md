# Agent Instructions Hub

This is the canonical instruction entry point for AI coding agents in this repository.

## Core Instruction Files

- Kumiki concepts: `docs/concepts.md`
- Library authoring rules: `.github/instructions/authoring.instructions.md`
- Kigumi frontend rules: `.github/instructions/kigumi-viewer-frontend.instructions.md`
- Pattern/design usage rules: `docs/agent_usage_instructions.md`
    - this file is the same one our end users will use, however we also author examples and patterns internally so it's useful for kumiki development as well.


## Skills

- Repository-local Claude skills folder: `.claude/skills/`

Use relevant instruction files based on the files you are editing.

## Comments

Applies to all new and edited code.

- **Docstrings say what the function does**, starting with a verb: "Return the ...", "Raise ...", "Yield ...".
  One line when that is enough.
- Add lines only for what the name and signature don't say:
  - what each part of a returned tuple is, and when it returns None or raises;
  - what an argument means when it isn't obvious (its space: world or timber-local; its units);
  - assumptions the caller must meet ("`direction` must be unit").
- **Define any term a reader can't infer**, e.g. what "front" and "back" mean for a cross-section.
- Leave out: rationale, history ("used to", "was"), what went wrong before, alternatives considered,
  restating types, and metaphor. Put rationale in the commit message or PR.
- Inline comments: one line saying what a non-obvious step does. Keep TODOs.
- Module docstrings: a few lines on what the module contains.
- Less is more: no docstring at all beats one that repeats the name.

## Website translations

The website's text is in `website/src/i18n/`: `en.json` (English) and `ja.json` (Japanese). The
pages in `website/src/views/` read from them; `website/src/pages/` and `website/src/pages/ja/`
render each view in its language.

- `en.json` is the source. The user edits the English there, and their wording is kept as written.
- `ja.json` is always translated from `en.json`. When `en.json` changes (check
  `git log -p website/src/i18n/en.json`), translate every changed entry again from the English
  into `ja.json`. Don't change the Japanese on its own, and don't change the English to match it.
- Text added to a page goes into both files: the English in `en.json`, its translation in `ja.json`.
- Keep `{placeholders}` and HTML tags as they are. `npm run build` warns where the two files
  differ; a missing Japanese entry shows in English.
- The privacy policy and terms, and the docs, stay English only.

# Concepts

please see docs/concepts.md