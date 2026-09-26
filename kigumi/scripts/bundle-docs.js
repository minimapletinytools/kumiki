#!/usr/bin/env node
// Copies the repo's docs/ into kigumi/.kigumi/docs, where project-initializer
// looks for them in a packaged build (the extension's publish workflow does
// the same with rsync).

const fs = require('fs');
const path = require('path');

const source = path.join(__dirname, '..', '..', 'docs');
const target = path.join(__dirname, '..', '.kigumi', 'docs');

fs.rmSync(target, { recursive: true, force: true });
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.cpSync(source, target, { recursive: true });
console.log(`Bundled docs: ${source} -> ${target}`);
