/**
 * The viewer's source as one text, for tests that read it: viewer-shared.js, viewer-app.js and its
 * mixins (the other viewer-*.js, viewer-panels.js aside).
 */

const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', 'webview');
const OWN = new Set(['viewer-shared.js', 'viewer-app.js', 'viewer-panels.js']);

function viewerSourceFiles() {
    return ['viewer-shared.js', 'viewer-app.js', ...fs.readdirSync(DIR)
        .filter((name) => /^viewer-.*\.js$/.test(name) && !OWN.has(name)).sort()];
}

function viewerSource() {
    return viewerSourceFiles().map((name) => fs.readFileSync(path.join(DIR, name), 'utf8')).join('\n');
}

module.exports = { viewerSource, viewerSourceFiles };
