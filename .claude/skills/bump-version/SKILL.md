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
4. Commit on `main`.
5. Create tag(s).
6. Push commit and tag(s) to origin.

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

## Commit and tag

Single commit message when both are bumped:

- `Release kumiki vX.Y.Z and kigumi vA.B.C`

Single-target messages:

- `Release kumiki vX.Y.Z`
- `Release kigumi vA.B.C`

Commands:

```bash
git add pyproject.toml kumiki/__init__.py kigumi/package.json
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

Do not trigger publishing in this skill.
