/**
 * Shared frames (kigumi/publishes.js): frames opened from share links. They are read-only; an agent
 * reads them here, and copies one into the project to change it. agent/agent.js adds these where
 * the host can share (the standalone app and the browser).
 */

const fs = require('fs');
const path = require('path');
const { z } = require('zod');
const { numberedLines, MAX_READ_LINES } = require('./file-tools');

const text = (value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }];

/**
 * @param {object} options
 * @param {(commandId: string, args?: any) => Promise<any>} options.run  an app command
 * @param {() => string|null} options.root  the project folder open, or null
 */
function createSharedTools({ run, root }) {
    async function shared() {
        const list = await run('kigumi.listShared');
        if (!list) throw new Error('Sharing isn\'t available here.');
        return list;
    }
    async function find(id) {
        const entry = (await shared()).find((one) => one.id === id);
        if (!entry) throw new Error(`No shared frame ${id}. shared_frames lists them; open_shared adds one from its link.`);
        return entry;
    }
    const sharedId = z.string().describe('A shared frame\'s id, from shared_frames.');

    return [
        {
            name: 'shared_frames',
            description: 'Frames opened from share links: read-only copies of someone\'s frame, in the Shared '
                + 'section of the explorer. With no id, lists them; with an id, reads that frame\'s code. To '
                + 'change one, copy it into the project with copy_shared_to_project.',
            shape: {
                id: sharedId.optional(),
                offset: z.number().int().min(1).optional().describe('The first line to read (1-based).'),
                limit: z.number().int().min(1).max(MAX_READ_LINES).optional(),
            },
            effect: 'read',
            run: async ({ id, offset, limit }) => {
                if (!id) {
                    const list = await shared();
                    return text(list.length ? list.map(({ id: one, title, link, kumikiVersion, createdAt, entry }) => ({
                        id: one, title, file: entry, link, kumikiVersion, sharedOn: String(createdAt || '').slice(0, 10), readOnly: true,
                    })) : 'No shared frames are open. open_shared adds one from its link.');
                }
                const entry = await find(id);
                let file = entry.file;
                if (!entry.downloaded) file = await run('kigumi.viewSharedSource', id);
                const content = fs.readFileSync(file, 'utf8');
                return text(`${entry.title} (${entry.entry}, shared, read-only)\n${numberedLines(content, offset, limit)}`);
            },
        },
        {
            name: 'open_shared',
            description: 'Open a frame from a share link (https://kumiki.build/p/#…): download it, add it to '
                + 'the Shared frames, and build it in a view. Only when the user gives a link to open.',
            shape: { link: z.string().describe('The share link, or the shared frame\'s id.') },
            // Builds someone else's frame, running its Python.
            effect: 'run',
            run: async ({ link }) => {
                const file = await run('kigumi.openPublish', link);
                if (!file) throw new Error('That link couldn\'t be opened: Kigumi said why.');
                return text(`Opened ${path.basename(file)}, read-only. shared_frames reads its code.`);
            },
        },
        {
            name: 'copy_shared_to_project',
            description: 'Copy a shared frame into the open project, as a new file that can be changed, and '
                + 'open it in a view.',
            shape: { id: sharedId },
            effect: 'edit',
            run: async ({ id }) => {
                await find(id);
                if (!root()) throw new Error('No project is open: open or make one first.');
                const copied = await run('kigumi.copyPublishToProject', id);
                if (!copied) throw new Error('The shared frame couldn\'t be copied.');
                return text(`Copied to ${path.relative(root(), copied)}.`);
            },
        },
    ];
}

module.exports = { createSharedTools };
