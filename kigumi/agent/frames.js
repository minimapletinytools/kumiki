/**
 * Building frames for the agent: the app's frames, built in its views, and the check_frame tool over
 * any host's frames.
 *
 * A host's frames are:
 *   shows(file)    whether a view shows the file, so editing it rebuilds that view
 *   check(file)    build the file, opening a view first if none shows it
 *   rebuild(file)  build a file a view shows, after an edit
 *   picture(file)  a picture of its view as a data URL, or null; optional
 * check and rebuild resolve to a build report: { ok, error, entries: [{ level, message }] }.
 */

const { z } = require('zod');

/** @param {{panels: object, run: (id: string, args?: object) => Promise<any>, files: object}} options */
function viewFrames({ panels, run, files }) {
    const resolved = (file) => {
        try {
            return files.resolve(file);
        } catch (_error) {
            return null;
        }
    };
    return {
        shows(file) {
            const target = resolved(file);
            return Boolean(target) && panels.list().some((panel) => panel.kind === 'viewer' && panel.filePath
                && resolved(panel.filePath) === target);
        },
        async check(file) {
            const opened = await run('kigumi.automationOpenFileInViewer', { filePath: file });
            if (opened && opened.ok === false) return { ok: false, reason: opened.reason, filePath: file };
            return run('kigumi.automationBuildReport', { filePath: (opened && opened.filePath) || file });
        },
        rebuild(file) {
            return Promise.resolve(run('kigumi.automationBuildReport', { filePath: file, reason: 'agent edit' }))
                .catch((error) => ({ ok: false, error: error.message, entries: [] }));
        },
        async picture(file) {
            try {
                const result = await run('kigumi.captureScreenshot', { filePath: file, includeData: true });
                return result && result.data ? `data:image/png;base64,${result.data}` : null;
            } catch (_error) {
                return null;
            }
        },
    };
}

/** The check_frame tool over `frames`. */
function checkFrameTool(frames) {
    return {
        name: 'check_frame',
        description: 'Build a Python frame file and say whether it built, with its warnings and errors. Opens '
            + 'it in a view first if none shows it.',
        shape: { file_path: z.string().describe('Absolute path to a .py frame file.') },
        effect: 'run',
        run: async ({ file_path: filePath }) => [{ type: 'text', text: JSON.stringify(await frames.check(filePath), null, 2) }],
    };
}

module.exports = { viewFrames, checkFrameTool };
