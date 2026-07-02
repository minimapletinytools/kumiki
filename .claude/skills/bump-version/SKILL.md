---
name: bump-version
description: Bump version for kumiki and/or kigumi, commit to main, create release tags, and push.
---

# Bump Version Skill

Use this skill when asked to bump version(s) for kumiki and/or kigumi and publish git tags.

## Defaults

- Target: both projects unless user specifies one.
- Bump type: `patch` unless user specifies `minor` or `major`.
- Branch: `main`.
- Tag format:
  - kumiki: `kumiki-v<version>`
  - kigumi: `kigumi-v<version>`

## Version coupling rule

**kumiki and kigumi must share the same major.minor version at all times.**
kigumi enforces this at runtime and will refuse to start if they diverge.

- Patch bumps (`0.3.1`, `0.3.2`, …) are independent — only bump the project that changed.
- **Minor (or major) bumps must always bump both projects together to the same major.minor.**
  This is required whenever kumiki introduces a breaking API change that kigumi depends on.
- When the user says "breaking change" or asks for a `minor`/`major` bump, always target `both`.

## Inputs

- `target`: `kumiki`, `kigumi`, or `both`
- `bump`: `patch` | `minor` | `major` (default `patch`)
- `explicit_version`: optional exact version string (e.g. `0.3.0`) — when set, skip the bump arithmetic and write this version directly. Requires `target=both` if used for a minor/major sync.

## Mandatory behavior

1. Ensure clean working tree before bumping:
   - `git status --porcelain`
   - If dirty, stop and ask user how to proceed.
2. Sync local `main`:
   - `git checkout main`
   - `git pull --ff-only`
3. Apply requested bump.
4. Update `CHANGELOG.md` (see below).
5. Commit on `main`.
6. Create tag(s).
7. Push commit and tag(s) to origin.

## Exact bump logic

If `explicit_version` is provided, use it directly instead of running bump arithmetic.

### kumiki

Files to update:

- `pyproject.toml` field `project.version`
- `kumiki/__init__.py` field `__version__`

Suggested command:

```bash
python3 - <<'PY'
import re
from pathlib import Path

bump = "patch"          # replace at runtime, or set new = "X.Y.Z" directly
explicit = ""           # replace with explicit_version if provided

pyproject = Path("pyproject.toml")
text = pyproject.read_text(encoding="utf-8")
m = re.search(r'(?m)^version = "([^"]+)"$', text)
current = m.group(1)
if explicit:
    new = explicit
else:
    major, minor, patch = map(int, current.split("."))
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new = f"{major}.{minor}.{patch}"
text = re.sub(r'(?m)^version = "[^"]+"$', f'version = "{new}"', text, count=1)
pyproject.write_text(text, encoding="utf-8")

init_py = Path("kumiki/__init__.py")
init_text = init_py.read_text(encoding="utf-8")
init_text = re.sub(r'(?m)^__version__\s*=\s*"[^"]+"$', f'__version__ = "{new}"', init_text, count=1)
init_py.write_text(init_text, encoding="utf-8")
print(new)
PY
```

Tag: `kumiki-v<new_version>`

### kigumi

File to update:

- `kigumi/package.json` field `version`

Suggested command:

```bash
node - <<'NODE'
const fs = require('fs');
const p = 'kigumi/package.json';
const bump = 'patch'; // replace at runtime
const explicit = '';   // replace with explicit_version if provided
const pkg = JSON.parse(fs.readFileSync(p, 'utf8'));
let newVersion;
if (explicit) {
  newVersion = explicit;
} else {
  let [major, minor, patch] = pkg.version.split('.').map(Number);
  if (bump === 'major') {
    major += 1; minor = 0; patch = 0;
  } else if (bump === 'minor') {
    minor += 1; patch = 0;
  } else {
    patch += 1;
  }
  newVersion = `${major}.${minor}.${patch}`;
}
pkg.version = newVersion;
fs.writeFileSync(p, `${JSON.stringify(pkg, null, 2)}\n`, 'utf8');
console.log(pkg.version);
NODE
```

Tag: `kigumi-v<new_version>`

## Updating CHANGELOG.md

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). One shared
changelog covers both projects; each release entry has `### kumiki` / `### kigumi`
subsections (omit whichever project wasn't part of this release).

1. Find the baseline to diff from — the most recent existing tag of either project:
   ```bash
   git tag --list 'kumiki-v*' 'kigumi-v*' --sort=-creatordate | head -1
   ```
2. Review what changed since that tag, scoped to each project's directory:
   ```bash
   git log --oneline <last_tag>..HEAD -- kumiki/ tests/ patterns/
   git log --oneline <last_tag>..HEAD -- kigumi/
   ```
3. Read the current `[Unreleased]` section in `CHANGELOG.md`. The user may have already hand-written
   entries there for important changes — do not duplicate anything already listed. Summarize only
   what's *not* already covered.
4. Write a **concise** summary using Keep a Changelog subheadings as needed (`Added`, `Changed`,
   `Fixed`, `Removed`, `Deprecated`, `Security`). It's fine to omit minor/internal changes — capture
   the major points: new features, notable fixes, and especially breaking changes.
   - **Breaking changes are mandatory to document.** For any breaking API change, add a short
     migration note (old call → new call, or what to rename/replace) directly under the entry.
5. Rewrite `CHANGELOG.md`:
   - Move the (now-filled-in) `[Unreleased]` content into a new dated section: `## [X.Y.Z] - YYYY-MM-DD`
     (use today's date). If both projects bumped to different versions in a patch-only release,
     title the section after whichever bump is the "headline" one, or use both, e.g.
     `## [kumiki 0.3.7 / kigumi 0.3.6] - YYYY-MM-DD` — use judgment; most releases bump both to the
     same version and a single version number in the header is fine.
   - Insert a fresh, empty `## [Unreleased]` section above it (just the heading, no subheadings —
     add those only when something is actually added there).

## Pre-commit: Regenerate agent context bundle

Before committing, always regenerate the bundled usage instructions (combines usage instructions + full API context):

```bash
cat docs/agent_usage_instructions.md docs/agent_context.md > kigumi/.generated/bundled-usage-instructions.md
```

Also update the `VERSION:X.Y.Z` line at the top of `docs/agent_context.md` to match the new kumiki version:

```bash
sed -i '' "s/^VERSION:[0-9.]*/VERSION:<new_version>/" docs/agent_context.md
```

## Commit and tag

Single commit message when both are bumped:

- `Release kumiki vX.Y.Z and kigumi vA.B.C`

Single-target messages:

- `Release kumiki vX.Y.Z`
- `Release kigumi vA.B.C`

Commands:

```bash
git add pyproject.toml kumiki/__init__.py kigumi/package.json docs/agent_context.md kigumi/.generated/bundled-usage-instructions.md CHANGELOG.md
git commit -m "<message>"
git tag -a "kumiki-vX.Y.Z" -m "Release kumiki vX.Y.Z"
git tag -a "kigumi-vA.B.C" -m "Release kigumi vA.B.C"
git push origin main
git push origin <tag1> <tag2>
```

Only create/push relevant tag(s) for selected targets.

## Validation

- `git show --name-only --stat HEAD`
- `git tag --list 'kumiki-v*' 'kigumi-v*' --sort=-creatordate | head`

Do not trigger publishing in this skill. Pushing the tags is sufficient — `release.yml` triggers automatically on tag push and routes jobs by tag prefix (kumiki-v* → kumiki jobs, kigumi-v* → kigumi jobs). Do NOT manually dispatch the workflow after pushing tags; doing so duplicates the publish step and causes a failure.
