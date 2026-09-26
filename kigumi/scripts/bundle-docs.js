#!/usr/bin/env node
// Copies the repo's docs/ into kigumi/.kigumi/docs, where project-initializer
// looks for them in a packaged build (the extension's publish workflow does
// the same with rsync).
//
// EVERYTHING HERE SHIPS, twice over: into the package, and out of it again into
// every project the initializer sets up. docs/internal/ is the one folder that
// is ours rather than a user's, so it is left behind -- and left behind in all
// three places docs/ goes, the other two being the rsync in
// .github/workflows/publish-kigumi.yml and exclude_docs in mkdocs.yml, which
// would otherwise put it on the public site.

const fs = require('fs');
const path = require('path');

const source = path.join(__dirname, '..', '..', 'docs');
const target = path.join(__dirname, '..', '.kigumi', 'docs');

/** Folders under docs/ that are for us and not for whoever installs this. */
const INTERNAL = new Set(['internal']);

fs.rmSync(target, { recursive: true, force: true });
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.cpSync(source, target, {
    recursive: true,
    // Named relative to docs/, so a user's own `internal/` deeper in the tree
    // is not caught by the same name.
    filter: (from) => !INTERNAL.has(path.relative(source, from)),
});
console.log(`Bundled docs: ${source} -> ${target} (without ${[...INTERNAL].join(', ')})`);
