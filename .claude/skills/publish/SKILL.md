---
name: publish
description: Trigger GitHub Actions publish workflows for kumiki and/or kigumi without changing versions.
---

# Publish Skill

Use this skill to trigger existing GitHub Actions publishing workflows only.

## Scope

- Does not bump versions.
- Does not create commits or tags.
- Only dispatches workflows.

## Workflows

- Kumiki: `.github/workflows/publish.yml`
- Kigumi: `.github/workflows/publish-kigumi.yml`

## Inputs

- `target`: `kumiki`, `kigumi`, or `both`
- For kumiki index:
  - `testpypi` (default)
  - `pypi`
- For kigumi prerelease:
  - `false` (default)
  - `true`

## Commands (GitHub CLI)

Ensure authenticated GH CLI first:

```bash
gh auth status
```

Trigger kumiki publish:

```bash
gh workflow run .github/workflows/publish.yml --ref main -f target=testpypi
```

Trigger kigumi publish:

```bash
gh workflow run .github/workflows/publish-kigumi.yml --ref main -f prerelease=false
```

Trigger both:

```bash
gh workflow run .github/workflows/publish.yml --ref main -f target=testpypi
gh workflow run .github/workflows/publish-kigumi.yml --ref main -f prerelease=false
```

## Verify dispatch

```bash
gh run list --workflow publish.yml --limit 5
gh run list --workflow publish-kigumi.yml --limit 5
```

Optionally stream a run:

```bash
gh run watch <run-id>
```

If GH CLI is unavailable, stop and ask user to install/authenticate `gh`.
