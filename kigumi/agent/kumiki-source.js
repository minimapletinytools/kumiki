/**
 * Where the project's Python imports kumiki from, for the agent to read: inside the project's
 * .venv for an installed kumiki, or the checkout an editable install points at.
 */

const fs = require('fs');
const { execFile } = require('child_process');
const { getVenvPythonCandidates } = require('../python-env');

const SNIPPET = 'import os, kumiki; print(os.path.dirname(os.path.abspath(kumiki.__file__)))';

/** The kumiki package's folder for the project at `projectRoot`, or null. */
function findKumikiSource(projectRoot) {
    const python = projectRoot && getVenvPythonCandidates(projectRoot).find((candidate) => fs.existsSync(candidate));
    if (!python) return Promise.resolve(null);
    return new Promise((resolve) => {
        execFile(python, ['-c', SNIPPET], { cwd: projectRoot, timeout: 20000 }, (error, stdout) => {
            const folder = !error && stdout.trim().split('\n').pop();
            resolve(folder && fs.existsSync(folder) ? folder : null);
        });
    });
}

module.exports = { findKumikiSource };
