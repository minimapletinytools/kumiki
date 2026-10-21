# Agent Instructions Hub

This is the canonical instruction entry point for AI coding agents in this repository.

## Core Instruction Files

- Kumiki concepts: `docs/concepts.md`
- Library authoring rules: `.github/instructions/authoring.instructions.md`
- Kigumi frontend rules: `.github/instructions/kigumi-viewer-frontend.instructions.md`
- Pattern/design usage rules: `docs/agent_usage_instructions.md`
    - this file is the same one our end users will use, however we also author examples and patterns internally so it's useful for kumiki development as well.
    - it references an `init-kumiki-project` skill at `.kigumi/docs/skills/init-kumiki-project/SKILL.md` -- that path is correct for end users (kigumi copies the installed kumiki's docs, plus the skill, into a project's `.kigumi/docs/`; see `kigumi/project-docs.js`), but in this repo the skill itself actually lives at `kigumi/skills/init-kumiki-project/SKILL.md` (kigumi-only, bundled with the extension).


## Skills

- Repository-local Claude skills folder: `.claude/skills/`
- Kigumi's own skills (bundled with the extension, copied into new project workspaces): `kigumi/skills/`

Use relevant instruction files based on the files you are editing.

## Comments

- A function's docstring plainly says what it does, and where useful what it is for, what it assumes, its arguments and what it returns. Less is more: leave out anything obvious from the name and signature.
- Say what the code does, not why it was built that way or what went wrong before; that belongs in the commit message or PR.

# Concepts

please see docs/concepts.md