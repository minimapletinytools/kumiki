#!/usr/bin/env node
// Writes kigumi/legacy-doc-hashes.json: for every file Kigumi ever copied into a project's
// docs/ (the repo's docs/ and kigumi/skills/, at any commit), the sha256 of each version.
// Updating a project removes an old docs/ file only if it hashes to one of these, so a
// file the user edited is never deleted. Kigumi stopped writing docs/ when the docs moved
// to .kigumi/docs, so this does not need regenerating for later changes.
const { execFileSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const repo = path.resolve(__dirname, '..', '..');
const git = (...args) => execFileSync('git', args, { cwd: repo, maxBuffer: 1 << 28 });

const hashes = {};
for (const line of git('rev-list', '--all', '--objects', '--', 'docs', 'kigumi/skills').toString().split('\n')) {
    const [sha, file] = line.split(' ');
    if (!file || !(file.startsWith('docs/') || file.startsWith('kigumi/skills/'))) continue;
    if (git('cat-file', '-t', sha).toString().trim() !== 'blob') continue;
    const relative = file.startsWith('docs/') ? file.slice('docs/'.length) : `skills/${file.slice('kigumi/skills/'.length)}`;
    const digest = crypto.createHash('sha256').update(git('cat-file', 'blob', sha)).digest('hex');
    (hashes[relative] = hashes[relative] || new Set()).add(digest);
}
const out = Object.fromEntries(Object.keys(hashes).sort().map((key) => [key, [...hashes[key]].sort()]));
fs.writeFileSync(path.join(__dirname, '..', 'legacy-doc-hashes.json'), `${JSON.stringify(out, null, 1)}\n`);
console.log(`${Object.keys(out).length} files, ${Object.values(out).reduce((n, v) => n + v.length, 0)} versions`);
