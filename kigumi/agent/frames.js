/**
 * Building frames for the agent: the app's frames, built in its views, and the check_frame tool over
 * any host's frames.
 *
 * A host's frames are:
 *   shows(file)    whether a view shows the file, so editing it rebuilds that view
 *   check(file)    build the file, opening a view first if none shows it
 *   rebuild(file)  build a file a view shows, after an edit
 *   picture(file)  a picture of its view as a data URL, or null; optional
 *   describe(file, timber) where its timbers are (frame-description.js describeFrame), or with `timber` that
 *                  timber's faces and joints and the features they name; or { ok: false, … }; optional
 *   drawings(file, open) a view's drawings, after going to `open`; the active view's with no file; optional
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
        async describe(file, timber) {
            const target = resolved(file);
            if (!target) return { ok: false, reason: 'outside-project', filePath: file };
            const opened = await run('kigumi.automationOpenFileInViewer', { filePath: target });
            if (opened && opened.ok === false) return { ok: false, reason: opened.reason, filePath: file };
            const filePath = (opened && opened.filePath) || target;
            return timber ? run('kigumi.automationDescribeTimber', { filePath, timber })
                : run('kigumi.automationDescribeFrame', { filePath });
        },
        async drawings(file, open) {
            let target = null;
            if (file) {
                target = resolved(file);
                if (!target) return { ok: false, reason: 'outside-project', filePath: file };
                if (!this.shows(target)) {
                    const built = await this.check(target);
                    if (built && built.reason) return built;
                }
            }
            return run('kigumi.automationDrawings', { filePath: target || undefined, open });
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

const DESCRIBE_FRAME = 'Where a frame\'s timbers are, as YAML: for each timber its size, the centres of its two ends, '
    + 'the world direction each face (TOP, BOTTOM, RIGHT, LEFT, FRONT, BACK) looks, its box as cut, the timbers '
    + 'it touches and its joints; then whether every timber is connected. Metres, Z up. Use it after building '
    + 'to read off which face points where, rather than working it out, and to check joined timbers meet.';

/** The describe tool over `frames`: a built frame as YAML, or one timber's features; `name` for its old name. */
function describeTool(frames, name = 'describe') {
    const timbered = name === 'describe';
    return {
        name,
        description: timbered
            ? `${DESCRIBE_FRAME} Give timber (its path) for that timber instead: its faces' feature names, and each joint `
                + 'on it with the timbers it joins and the features it names, with their kumiki constants, to measure in a drawing.'
            : `${DESCRIBE_FRAME} The same as describe without a timber.`,
        shape: {
            file_path: z.string().describe('A .py frame file: relative to the project folder, or absolute inside it.'),
            ...(timbered ? { timber: z.string().optional().describe('A timber\'s path, as the frame description names it.') } : {}),
        },
        effect: 'run',
        run: async ({ file_path: filePath, timber }) => {
            const described = await frames.describe(filePath, timbered ? timber : undefined);
            const text = described && described.ok !== false && Array.isArray(described.timbers)
                ? formatFrameDescription(described) : JSON.stringify(described, null, 2);
            return [{ type: 'text', text }];
        },
    };
}

/** The describe_frame tool: describe without a timber, under the name it had before. */
function describeFrameTool(frames) {
    return describeTool(frames, 'describe_frame');
}

/** The drawings tool over `frames`: list a frame's drawings, or open one. */
function drawingsTool(frames) {
    return {
        name: 'drawings',
        description: 'A frame\'s drawings (those its code declares and those saved in the project), and which one '
            + 'its view shows. Give open (a drawing\'s name or id, or "3d" for the model) to show that one. Opens '
            + 'the frame in a view first if none shows it.',
        shape: {
            file_path: z.string().optional().describe('A .py frame file: relative to the project folder, or absolute inside it. Defaults to the active view\'s.'),
            open: z.string().optional().describe('A drawing\'s name or id to show, or "3d".'),
        },
        effect: 'run',
        run: async ({ file_path: filePath, open }) => [{ type: 'text', text: JSON.stringify(await frames.drawings(filePath, open), null, 2) }],
    };
}

module.exports = { viewFrames, checkFrameTool, describeTool, describeFrameTool, drawingsTool };
