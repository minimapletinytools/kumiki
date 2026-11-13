/**
 * Kigumi's view tools: the panels open, what they show, and each view's camera, log and picture.
 * agent/agent.js adds them to the agent's tools and the MCP server's.
 *
 * Each tool is { name, description, shape, effect, run }, where `shape` is a zod raw shape
 * (both SDKs take one), `effect` is what running it does (agent/permissions.js), and `run(args)`
 * resolves to MCP content: [{ type: 'text', text }] or an image.
 */

const { z } = require('zod');

const text = (value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }];

/**
 * @param {object} options
 * @param {ReturnType<typeof import('./panel-directory').createPanelDirectory>} options.panels
 * @param {(commandId: string, args?: object) => Promise<any>} options.run  an app command
 * @param {() => string[]} [options.workspaceFolders]  the folders open, the project first
 * @param {(file: string) => string} [options.resolve]  a file the agent names as an absolute path,
 *     throwing for one it may not use (agent/project-files.js resolve)
 * @param {boolean} [options.workspaceTool]  offer get_workspace_folder (not where list_projects says it)
 */
function createKigumiTools({ panels, run, workspaceFolders = () => [], resolve = (file) => file, workspaceTool = true }) {
    const panelId = z.string().optional()
        .describe('A panel id from list_panels. Defaults to the active panel, or the active view.');

    /** The automation commands pick a view by file, or by slot for a pattern. */
    function viewOptions(id) {
        const session = panels.viewSession(id);
        if (!session) {
            throw new Error(id ? `No open view with id ${id}` : 'No view is open. Open a frame file with check_frame.');
        }
        return session.patternName
            ? { slotName: session.slotName, filePath: session.filePath }
            : { filePath: session.filePath };
    }

    return [
        ...(workspaceTool ? [{
            name: 'get_workspace_folder',
            description: 'The project folder open in Kigumi: where its frame files and patterns are, and '
                + 'what the file paths the other tools give are relative to.',
            shape: {},
            effect: 'read',
            run: async () => {
                const folders = workspaceFolders();
                return text({ workspaceFolder: folders[0] || null, workspaceFolders: folders });
            },
        }] : []),
        {
            name: 'list_panels',
            description: 'Every open Kigumi panel (3D views, code editors, the log), which one is active, '
                + 'and the file each shows.',
            shape: {},
            effect: 'read',
            run: async () => {
                const active = panels.active();
                return text({ active: active ? active.id : null, panels: panels.list() });
            },
        },
        {
            name: 'describe_panel',
            description: 'What a panel shows and what is selected in it. For a view: the frame, whether it '
                + 'is in 3D or a drawing, and the selected timbers (sizes, positions in metres, tags) or '
                + 'the focused feature with the reference that finds it in code. For an editor: the file '
                + 'and the selected text.',
            shape: { panel_id: panelId },
            effect: 'read',
            run: async ({ panel_id: id }) => {
                const described = await panels.describe(id);
                return text(described || { error: 'No such panel, and no panel is active.' });
            },
        },
        {
            name: 'get_selection_history',
            description: 'What the user selected in the views lately, newest first (the last 20 at most): '
                + 'when, in which view and file, and the timbers or feature selected, as describe_panel gives '
                + 'them. Use it when the user refers to something they selected earlier. Give file_path to '
                + 'get only that file\'s selections.',
            shape: {
                limit: z.number().int().min(1).max(20).optional().describe('How many, newest first. Defaults to 20.'),
                file_path: z.string().optional().describe('Only selections in this frame file: relative to the project folder, or absolute inside it.'),
            },
            effect: 'read',
            run: async ({ limit, file_path: filePath }) => text({
                selections: panels.recentSelections(limit || 20, filePath ? resolve(filePath) : undefined),
            }),
        },
        {
            name: 'read_view_log',
            description: "A view's log: what the Python runner printed building the frame, including errors "
                + 'and tracebacks.',
            shape: {
                panel_id: panelId,
                min_level: z.enum(['debug', 'info', 'warning', 'error']).optional(),
                contains: z.string().optional().describe('Only entries containing this text.'),
            },
            effect: 'read',
            run: async ({ panel_id: id, min_level: minLevel, contains }) => text(await run(
                'kigumi.automationReadSessionLogs', { ...viewOptions(id), minLevel, contains },
            )),
        },
        {
            name: 'camera',
            description: "A view's camera: where it looks from and at. Give a state (as this returns it, changed "
                + 'as wanted) to move the camera there.',
            shape: {
                panel_id: panelId,
                set: z.record(z.string(), z.unknown()).optional().describe('A camera state to move to, as this tool returns it.'),
            },
            effect: 'ui',
            run: async ({ panel_id: id, set }) => {
                const options = viewOptions(id);
                if (set) await run('kigumi.automationSetCameraState', { ...options, cameraState: set });
                return text(await run('kigumi.automationGetCameraState', options));
            },
        },
        {
            name: 'screenshot',
            description: 'A picture of a view as it is drawn now, to look at the model.',
            shape: { panel_id: panelId },
            effect: 'read',
            run: async ({ panel_id: id }) => {
                const result = await run('kigumi.captureScreenshot', { ...viewOptions(id), includeData: true });
                return [
                    { type: 'image', data: result.data, mimeType: 'image/png' },
                    ...text({ screenshotPath: result.screenshotPath, filePath: result.filePath }),
                ];
            },
        },
    ];
}

module.exports = { createKigumiTools };
