/**
 * Kigumi's tools for agents: one list, served over MCP (agent/mcp-http.js) to any agent, and
 * in process to the built-in agent panel (agent/agent-session.js).
 *
 * Each tool is { name, description, shape, readOnly, run }, where `shape` is a zod raw shape
 * (both SDKs take one) and `run(args)` resolves to MCP content: [{ type: 'text', text }] or an
 * image. `readOnly` tools change nothing, so the agent panel runs them without asking.
 *
 * Kigumi-specific only: reading and editing files is the agent's own job.
 */

const fs = require('fs');
const { z } = require('zod');

const text = (value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }];

/**
 * @param {object} options
 * @param {ReturnType<typeof import('./panel-directory').createPanelDirectory>} options.panels
 * @param {(commandId: string, args?: object) => Promise<any>} options.run  an app command
 * @param {() => string[]} [options.workspaceFolders]  the folders open, the project first
 */
function createKigumiTools({ panels, run, workspaceFolders = () => [] }) {
    const panelId = z.string().optional()
        .describe('A panel id from list_panels. Defaults to the active panel, or the active view.');

    /** The automation commands pick a view by file, or by slot for a pattern. */
    function viewOptions(id) {
        const session = panels.viewSession(id);
        if (!session) {
            throw new Error(id ? `No open view with id ${id}` : 'No view is open. Open a frame file with open_in_viewer.');
        }
        return session.patternName
            ? { slotName: session.slotName, filePath: session.filePath }
            : { filePath: session.filePath };
    }

    return [
        {
            name: 'get_workspace_folder',
            description: 'The project folder open in Kigumi: where its frame files and patterns are, and '
                + 'what the file paths the other tools give are relative to.',
            shape: {},
            readOnly: true,
            run: async () => {
                const folders = workspaceFolders();
                return text({ workspaceFolder: folders[0] || null, workspaceFolders: folders });
            },
        },
        {
            name: 'list_panels',
            description: 'Every open Kigumi panel (3D views, code editors, the log), which one is active, '
                + 'and the file each shows.',
            shape: {},
            readOnly: true,
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
            readOnly: true,
            run: async ({ panel_id: id }) => {
                const described = await panels.describe(id);
                return text(described || { error: 'No such panel, and no panel is active.' });
            },
        },
        {
            name: 'open_in_viewer',
            description: 'Open a Python frame file in a Kigumi 3D view (or bring its view forward).',
            shape: { file_path: z.string().describe('Absolute path to a .py frame file.') },
            readOnly: false,
            run: async ({ file_path: filePath }) => text(await run('kigumi.automationOpenFileInViewer', { filePath })),
        },
        {
            name: 'refresh_view',
            description: 'Rebuild a view from its source file, after the file has been edited.',
            shape: { panel_id: panelId },
            readOnly: false,
            run: async ({ panel_id: id }) => text(await run('kigumi.automationRefreshSession', {
                ...viewOptions(id), reason: 'agent refresh',
            })),
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
            readOnly: true,
            run: async ({ panel_id: id, min_level: minLevel, contains }) => text(await run(
                'kigumi.automationReadSessionLogs', { ...viewOptions(id), minLevel, contains },
            )),
        },
        {
            name: 'get_camera',
            description: "A view's camera: where it looks from and at.",
            shape: { panel_id: panelId },
            readOnly: true,
            run: async ({ panel_id: id }) => text(await run('kigumi.automationGetCameraState', viewOptions(id))),
        },
        {
            name: 'set_camera',
            description: "Move a view's camera. Pass the state get_camera returns, changed as wanted.",
            shape: {
                panel_id: panelId,
                camera: z.record(z.string(), z.unknown()).describe('A camera state, as get_camera returns it.'),
            },
            readOnly: false,
            run: async ({ panel_id: id, camera }) => text(await run('kigumi.automationSetCameraState', {
                ...viewOptions(id), cameraState: camera,
            })),
        },
        {
            name: 'screenshot',
            description: 'A picture of a view as it is drawn now, to look at the model.',
            shape: { panel_id: panelId },
            readOnly: true,
            run: async ({ panel_id: id }) => {
                const result = await run('kigumi.captureScreenshot', viewOptions(id));
                const data = fs.readFileSync(result.screenshotPath).toString('base64');
                return [
                    { type: 'image', data, mimeType: 'image/png' },
                    ...text({ screenshotPath: result.screenshotPath, filePath: result.filePath }),
                ];
            },
        },
    ];
}

module.exports = { createKigumiTools };
