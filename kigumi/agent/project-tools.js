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
 */
function createProjectTools(projects) {
    const folder = (what) => z.string().describe(`${what} An absolute path.`);
    return [
        {
            name: 'list_projects',
            description: 'The project folder open in Kigumi, if any, and the ones opened recently.',
            shape: {},
            effect: 'read',
            run: async () => text({ open: projects.current(), recent: projects.recent() }),
        },
        {
            name: 'open_project',
            description: 'Open an existing project folder in Kigumi, in place of the one open: its tabs and '
                + 'views close. Only when the user asks to switch projects.',
            shape: { folder: folder('The project folder.') },
            effect: 'edit',
            run: async ({ folder: target }) => {
                await projects.open(target);
                return text(`Opened ${target}. File paths are now relative to it.`);
            },
        },
        {
            name: 'new_project',
            description: 'Make a new project (its venv, kumiki and a starter frame) and open it in Kigumi. A folder '
                + 'that does not exist yet is made; setting up an existing one overwrites nothing. Only when the '
                + 'user asks for a new project.',
            shape: { folder: folder('Where the new project goes, e.g. ~/Documents/shed written out in full.') },
            effect: 'edit',
            run: async ({ folder: target }) => {
                await projects.create(target);
                return text(`Made and opened a project in ${target}, with my_cute_frame.py to start from.`);
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
