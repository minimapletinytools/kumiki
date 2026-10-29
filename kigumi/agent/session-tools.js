/**
 * The tools the agent session adds or wraps: the agent's to-do list; file edits that rebuild the
 * view showing the file and say whether it built, with the view before and after for the panel;
 * and file edits kept for undo (agent/checkpoints.js).
 */

const { z } = require('zod');

const EDIT_TOOLS = new Set(['write_file', 'edit_file']);

/** The build report's result as text for the agent, appended to an edit's own. */
function describeBuild(report) {
    if (!report || report.reason === 'session-not-found') return null;
    const lines = (report.entries || []).map((entry) => `${entry.level}: ${entry.message}`);
    if (report.error) lines.unshift(`error: ${report.error}`);
    return report.ok
        ? `The view of this file rebuilt without errors.${lines.length ? `\n${lines.join('\n')}` : ''}`
        : `The view of this file rebuilt with errors:\n${lines.join('\n').slice(0, 4000)}`;
}

/** The agent's to-do list for a long task; `onChange(items)` shows it. */
function todoTool(onChange) {
    return {
        name: 'update_todos',
        description: 'Set your to-do list for a task of several steps (the whole list each time), ticking off '
            + 'what is done. The user sees it pinned in the panel.',
        shape: {
            items: z.array(z.object({ text: z.string(), done: z.boolean().optional() })).describe('Every item, in order.'),
        },
        effect: 'read',
        run: async ({ items }) => {
            const todos = items.map(({ text, done }) => ({ text, done: Boolean(done) }));
            onChange(todos);
            const left = todos.filter((item) => !item.done).length;
            return [{ type: 'text', text: `To-do list updated: ${left} of ${todos.length} left.` }];
        },
    };
}

/**
 * `tool`, and when it writes or edits a file a view shows, that view rebuilt with the build's result
 * (one step for the agent where it took three), and the view before and after given to
 * `onPictures(toolCallId, before, after)`, for the panel only. `frames` is the host's (agent/frames.js).
 */
function withBuildCheck(tool, { files, frames, onPictures }) {
    if (!EDIT_TOOLS.has(tool.name)) return tool;
    const picture = (file) => (frames.picture ? frames.picture(file) : null);
    return {
        ...tool,
        run: async (args, context = {}) => {
            const target = files.resolve(args.file_path || '');
            const shown = frames.shows(target);
            const before = shown ? await picture(target) : null;
            const result = await tool.run(args, context);
            if (!shown) return result;
            const report = await frames.rebuild(target);
            const after = await picture(target);
            if (before && after && context.toolCallId) onPictures(context.toolCallId, before, after);
            const built = describeBuild(report);
            return built ? [...result, { type: 'text', text: built }] : result;
        },
    };
}

/** `tool`, keeping each file it writes as it was before the turn first changed it (`checkpoints()`). */
function withCheckpoints(tool, { files, checkpoints }) {
    if (!EDIT_TOOLS.has(tool.name)) return tool;
    return {
        ...tool,
        run: async (args, context) => {
            await checkpoints().beforeWrite(files.resolve(args.file_path || '', { write: true }));
            return tool.run(args, context);
        },
    };
}

module.exports = { todoTool, withBuildCheck, withCheckpoints, describeBuild };
