/**
 * The agent's tools and instructions, built from what a host gives it. The app's agent panel, its
 * MCP server and the evals all build them here.
 *
 * A host is:
 *   files           the project's files (agent/project-files.js)
 *   frames          building frames (agent/frames.js)
 *   view            { panels, run, workspaceFolders } for the view tools (agent/tools.js); null headless
 *   kumikiApi       (name, {members, source}) => Promise<string> (agent/kumiki-api.js); null without one
 *   kumikiSource()  the kumiki library's folder, which the agent may read; or null
 *   kumikiExamples() kumiki's example frames' folder; or null
 *   systemPrompt    (kumikiSource, kumikiExamples) => string (agent/system-prompt.js)
 */

const { createKigumiTools } = require('./tools');
const { createFileTools } = require('./file-tools');
const { viewFrames, checkFrameTool } = require('./frames');
const { kumikiApiTool } = require('./kumiki-api');
const { todoTool, withBuildCheck, withCheckpoints } = require('./session-tools');
const { PLAN_MODE_NOTE } = require('./permissions');

/** A host over the app's views. */
function viewHost({ panels, run, files, workspaceFolders = () => [files.root()].filter(Boolean), kumikiApi = null,
    kumikiSource = () => null, kumikiExamples = () => null, systemPrompt = () => '' }) {
    return { files, frames: viewFrames({ panels, run, files }), view: { panels, run, workspaceFolders, resolve: (file) => files.resolve(file) },
        kumikiApi, kumikiSource, kumikiExamples, systemPrompt };
}

/** The tools any agent gets: the built-in one, and others over MCP. */
function sharedTools(host) {
    return [
        ...(host.view ? createKigumiTools(host.view) : []),
        checkFrameTool(host.frames),
        ...(host.kumikiApi ? [kumikiApiTool(host.kumikiApi)] : []),
    ];
}

/**
 * The built-in agent's tools: the shared ones, file tools whose edits rebuild the view showing the
 * file and are kept for undo, and a to-do list.
 *
 * @param {object} host
 * @param {object} hooks
 * @param {() => object} hooks.checkpoints  the conversation's (agent/checkpoints.js)
 * @param {(items: object[]) => void} [hooks.onTodos]
 * @param {(toolCallId: string, before: string, after: string) => void} [hooks.onPictures]  a view before and after an edit
 */
function agentTools(host, { checkpoints, onTodos = () => {}, onPictures = () => {} }) {
    const fileTools = createFileTools({ files: host.files }).map((tool) => withCheckpoints(
        withBuildCheck(tool, { files: host.files, frames: host.frames, onPictures }),
        { files: host.files, checkpoints }));
    return [...sharedTools(host), ...fileTools, todoTool(onTodos)];
}

/** The built-in agent's system prompt. */
function instructions(host, { planMode = false } = {}) {
    const prompt = host.systemPrompt(host.kumikiSource(), host.kumikiExamples());
    return planMode ? `${prompt}\n\n${PLAN_MODE_NOTE}` : prompt;
}

module.exports = { viewHost, sharedTools, agentTools, instructions };
