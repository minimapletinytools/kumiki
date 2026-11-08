/**
 * Tools for the project Kigumi has open: list recent ones, open one, make a new one, close it.
 * agent/agent.js adds them for a host that can switch projects (the standalone app). Switching
 * closes the old project's tabs and views; the agent's conversation carries on.
 */

const { z } = require('zod');

const text = (value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }];

/**
 * @param {object} projects
 * @param {() => string|null} projects.current  the project folder open, or null
 * @param {() => string[]} projects.recent  recently opened project folders, newest first
 * @param {(folder: string) => Promise<void>} projects.open  open an existing folder (throws if it isn't one)
 * @param {(folder: string) => Promise<void>} projects.create  make a new project folder, open it and set it up
 * @param {() => Promise<void>} projects.close  close the project, leaving none open
 * @param {boolean} [projects.byName]  projects are named rather than folders (the web version, whose
 *     projects live in the browser): `folder` is then a project's name
 */
function createProjectTools(projects) {
    const byName = projects.byName === true;
    const folder = (what, named) => z.string().describe(byName ? named : `${what} An absolute path.`);
    return [
        {
            name: 'list_projects',
            description: byName
                ? 'The project open in Kigumi, if any, and the others this browser holds, by name.'
                : 'The project folder open in Kigumi, if any, and the ones opened recently.',
            shape: {},
            effect: 'read',
            run: async () => text({ open: projects.current(), recent: projects.recent() }),
        },
        {
            name: 'open_project',
            description: 'Open an existing project folder in Kigumi, in place of the one open: its tabs and '
                + 'views close. Only when the user asks to switch projects.',
            shape: { folder: folder('The project folder.', 'The project\'s name, as list_projects gives it.') },
            effect: 'edit',
            run: async ({ folder: target }) => {
                await projects.open(target);
                return text(`Opened ${target}. File paths are now relative to it.`);
            },
        },
        {
            name: 'new_project',
            description: byName
                ? 'Make a new project in this browser, with a starter frame, and open it in Kigumi. Only when the '
                    + 'user asks for a new project.'
                : 'Make a new project (its venv, kumiki and a starter frame) and open it in Kigumi. A folder '
                    + 'that does not exist yet is made; setting up an existing one overwrites nothing. Only when the '
                    + 'user asks for a new project.',
            shape: { folder: folder('Where the new project goes, e.g. ~/Documents/shed written out in full.', 'The new project\'s name.') },
            effect: 'edit',
            run: async ({ folder: target }) => {
                await projects.create(target);
                return text(byName ? `Made and opened the project ${target}, with my_cute_frame.py to start from.`
                    : `Made and opened a project in ${target}, with my_cute_frame.py to start from.`);
            },
        },
        {
            name: 'close_project',
            description: 'Close the project open in Kigumi, leaving none open. Only when the user asks.',
            shape: {},
            effect: 'edit',
            run: async () => {
                await projects.close();
                return text('Closed the project; none is open now.');
            },
        },
    ];
}

module.exports = { createProjectTools };
