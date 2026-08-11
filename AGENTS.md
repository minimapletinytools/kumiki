# Agent Instructions Hub

This is the canonical instruction entry point for AI coding agents in this repository.

## Core Instruction Files

- Kumiki concepts: `docs/concepts.md`
- Library authoring rules: `.github/instructions/authoring.instructions.md`
- Kigumi frontend rules: `.github/instructions/kigumi-viewer-frontend.instructions.md`
- Pattern/design usage rules: `docs/agent_usage_instructions.md`
    - this file is the same one our end users will use, however we also author examples and patterns internally so it's useful for kumiki development as well.
    - it references an `init-kumiki-project` skill at `docs/skills/init-kumiki-project/SKILL.md` -- that path is correct for end users (kigumi copies both files into a new project's `docs/`), but in this repo the skill itself actually lives at `kigumi/skills/init-kumiki-project/SKILL.md` (kigumi-only, bundled with the extension).


## Skills

- Repository-local Claude skills folder: `.claude/skills/`
- Kigumi's own skills (bundled with the extension, copied into new project workspaces): `kigumi/skills/`

Use relevant instruction files based on the files you are editing.

# Concepts

please see docs/concepts.md