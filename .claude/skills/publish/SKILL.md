---
name: publish
description: Trigger GitHub Actions publish workflows for kumiki and/or kigumi without changing versions.
---

# Publish Skill

Use this skill to trigger GitHub Actions release and publishing workflows.

## Scope

- Does not bump versions.
- Does not create commits or tags.
- Dispatches the unified release workflow or the lower-level publish workflows.

## Workflows

- Unified release: `.github/workflows/release.yml`
- Kumiki publish: `.github/workflows/publish.yml`
- Kigumi publish: `.github/workflows/publish-kigumi.yml`

## Inputs

- `tag`: optional git tag to release. Defaults to the most recent tag when omitted.
- `kumiki`: `true` / `false`
- `kumiki_publish`: `true` / `false`
- `kumiki_publish_target`: `testpypi` (default) or `pypi`
- `kumiki_release`: `true` / `false`
- `kigumi`: `true` / `false`
- `kigumi_publish_vscode`: `true` / `false`
- `kigumi_publish_ovsx`: `true` / `false`
- `kigumi_prerelease`: `true` / `false`
- `kigumi_release`: `true` / `false`

## Commands (GitHub CLI)

Ensure authenticated GH CLI first:

```bash
gh auth status
```

Trigger the unified release workflow:

```bash
gh workflow run .github/workflows/release.yml --ref main \
  -f tag=kumiki-v1.2.3 \
  -f kumiki=true \
  -f kumiki_publish=true \
  -f kumiki_publish_target=pypi \
  -f kumiki_release=true \
  -f kigumi=true \
  -f kigumi_publish_vscode=true \
  -f kigumi_publish_ovsx=true \
  -f kigumi_prerelease=false \
  -f kigumi_release=true
```

Trigger kumiki-only publish:

```bash
gh workflow run .github/workflows/publish.yml --ref main -f target=testpypi -f publish=true
```

Trigger kigumi-only publish:

```bash
gh workflow run .github/workflows/publish-kigumi.yml --ref main -f target=both -f publish=true -f prerelease=false
```

Trigger both lower-level publishes:

```bash
gh workflow run .github/workflows/publish.yml --ref main -f target=testpypi -f publish=true
gh workflow run .github/workflows/publish-kigumi.yml --ref main -f target=both -f publish=true -f prerelease=false
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
