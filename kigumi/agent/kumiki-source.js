/**
 * Where the project's Python imports kumiki from, for the agent to read: inside the project's
 * .venv for an installed kumiki, or the checkout an editable install points at.
 */

const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { getVenvPythonCandidates } = require('../python-env');

const SNIPPET = 'import os, kumiki; print(os.path.dirname(os.path.abspath(kumiki.__file__)))';

/** The project's own Python (its .venv's), or null. */
function projectPython(projectRoot) {
    return (projectRoot && getVenvPythonCandidates(projectRoot).find((candidate) => fs.existsSync(candidate))) || null;
}

/** The kumiki package's folder for the project at `projectRoot`, or null. */
function findKumikiSource(projectRoot) {
    const python = projectPython(projectRoot);
    if (!python) return Promise.resolve(null);
    return new Promise((resolve) => {
        execFile(python, ['-c', SNIPPET], { cwd: projectRoot, timeout: 20000 }, (error, stdout) => {
            const folder = !error && stdout.trim().split('\n').pop();
            resolve(folder && fs.existsSync(folder) ? folder : null);
        });
    });
}

/**
 * The example frames' folder for a kumiki package at `source`: inside it for an installed kumiki, or
 * the checkout's patterns/ beside it for an editable one. Null if neither.
 */
function kumikiExamples(source) {
    if (!source) return null;
    return [path.join(source, 'patterns'), path.join(source, '..', 'patterns')]
        .map((folder) => path.resolve(folder)).find((folder) => fs.existsSync(path.join(folder, 'structures'))) || null;
}

module.exports = { findKumikiSource, kumikiExamples, projectPython };
