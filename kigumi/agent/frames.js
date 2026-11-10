/**
 * Building frames for the agent: the app's frames, built in its views, and the check_frame tool over
 * any host's frames.
 *
 * A host's frames are:
 *   shows(file)    whether a view shows the file, so editing it rebuilds that view
 *   check(file)    build the file, opening a view first if none shows it
 *   rebuild(file)  build a file a view shows, after an edit
 *   picture(file)  a picture of its view as a data URL, or null; optional
 *   describe(file) where its timbers are (frame-description.js describeFrame), or { ok: false, … }; optional
 * check and rebuild resolve to a build report: { ok, error, entries: [{ level, message }] }. A file is
 * relative to the project folder or absolute; check refuses one outside the project and the folders
 * the agent may read.
 */

const { z } = require('zod');
const { formatFrameDescription } = require('../frame-description');

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
            const target = resolved(file);
            if (!target) return { ok: false, reason: 'outside-project', filePath: file };
            const opened = await run('kigumi.automationOpenFileInViewer', { filePath: target });
            if (opened && opened.ok === false) return { ok: false, reason: opened.reason, filePath: file };
            return run('kigumi.automationBuildReport', { filePath: (opened && opened.filePath) || target });
        },
        async describe(file) {
            const target = resolved(file);
            if (!target) return { ok: false, reason: 'outside-project', filePath: file };
            const opened = await run('kigumi.automationOpenFileInViewer', { filePath: target });
            if (opened && opened.ok === false) return { ok: false, reason: opened.reason, filePath: file };
            return run('kigumi.automationDescribeFrame', { filePath: (opened && opened.filePath) || target });
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
        shape: { file_path: z.string().describe('A .py frame file: relative to the project folder, or absolute inside it.') },
        effect: 'run',
        run: async ({ file_path: filePath }) => [{ type: 'text', text: JSON.stringify(await frames.check(filePath), null, 2) }],
    };
}

/** The describe_frame tool over `frames`: a built frame as YAML, or why there is none. */
function describeFrameTool(frames) {
    return {
        name: 'describe_frame',
        description: 'Where a frame\'s timbers are, as YAML: for each timber its size, the centres of its two ends, '
            + 'the world direction each face (TOP, BOTTOM, RIGHT, LEFT, FRONT, BACK) looks, its box as cut, the timbers '
            + 'it touches and its joints; then whether every timber is connected. Metres, Z up. Use it after building '
            + 'to read off which face points where, rather than working it out, and to check joined timbers meet.',
        shape: { file_path: z.string().describe('A .py frame file: relative to the project folder, or absolute inside it.') },
        effect: 'run',
        run: async ({ file_path: filePath }) => {
            const described = await frames.describe(filePath);
            const text = described && described.ok !== false && Array.isArray(described.timbers)
                ? formatFrameDescription(described) : JSON.stringify(described, null, 2);
            return [{ type: 'text', text }];
        },
    };
}

module.exports = { viewFrames, checkFrameTool, describeFrameTool };
