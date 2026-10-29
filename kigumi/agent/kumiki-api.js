/**
 * The agent's kumiki_api tool: what kumiki says about a name (its signature, docstring and where it
 * is), asked of the project's Python (kumiki_api.py), rather than found by searching its source.
 */

const path = require('path');
const { execFile } = require('child_process');
const { z } = require('zod');

/**
 * @param {object} options
 * @param {() => string|null} options.python  the project's Python, with kumiki installed
 * @param {() => string|null} [options.cwd]
 * @param {object} [options.env]  e.g. PYTHONPATH for a kumiki checkout
 */
function createKumikiApiTool({ python, cwd = () => null, env = {} }) {
    return {
        name: 'kumiki_api',
        description: 'Look up a kumiki function, class or module by name, as a frame file uses it after `from kumiki '
            + 'import *` (e.g. "create_axis_aligned_timber", "ButtJointTimberArrangement", "Frame.from_joints", '
            + '"kumiki.construction"): its exact signature, docstring and where it is defined; a class\'s fields and '
            + 'methods; a module\'s members. Suggests close names if there is no such name. Use it before guessing '
            + 'arguments, instead of searching or reading kumiki\'s source.',
        shape: {
            name: z.string().describe('The name to look up.'),
            members: z.boolean().optional().describe('Also list its members, with a line on each.'),
            source: z.boolean().optional().describe('Also give its source code.'),
        },
        effect: 'read',
        run: ({ name, members, source }) => new Promise((resolve, reject) => {
            const command = python();
            if (!command) {
                reject(new Error("The project has no Python environment with kumiki yet."));
                return;
            }
            const args = [path.join(__dirname, 'kumiki_api.py'), name, ...(members ? ['--members'] : []), ...(source ? ['--source'] : [])];
            execFile(command, args, { cwd: cwd() || undefined, env: { ...process.env, ...env }, timeout: 60000, maxBuffer: 8 * 1024 * 1024 },
                (error, stdout, stderr) => {
                    const reply = stdout.trim().split('\n').pop();
                    if (!reply) {
                        reject(new Error(`kumiki_api failed: ${(stderr || (error && error.message) || 'no answer').slice(-500)}`));
                        return;
                    }
                    resolve([{ type: 'text', text: reply }]);
                });
        }),
    };
}

module.exports = { createKumikiApiTool };
