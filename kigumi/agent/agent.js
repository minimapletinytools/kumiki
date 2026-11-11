/**
 * The agent's tools and instructions, built from what a host gives it. The app's agent panel, its
 * MCP server and the evals all build them here.
 *
 * A host is:
 *   files           the project's files (agent/project-files.js)
 *   frames          building frames (agent/frames.js)
 *   view            { panels, run, workspaceFolders } for the view tools (agent/tools.js); null headless
 *   projects        switching projects (agent/project-tools.js); null where Kigumi can't
 *   kumikiApi       (name, {members, source}) => Promise<string> (agent/kumiki-api.js); null without one
 *   kumikiSource()  the kumiki library's folder, which the agent may read; or null
 *   kumikiExamples() kumiki's example frames' folder; or null
 *   kumikiDocs()    kumiki's docs folder, for MCP clients (agent/kumiki-docs.js); or null
 *   systemPrompt    (kumikiSource, kumikiExamples) => string (agent/system-prompt.js)
 */

const { createKigumiTools } = require('./tools');
const { createProjectTools } = require('./project-tools');
const { createFileManagementTools } = require('./file-management-tools');
const { createFileTools } = require('./file-tools');
const { viewFrames, checkFrameTool, describeFrameTool } = require('./frames');
const { kumikiApiTool } = require('./kumiki-api');
const { kumikiDocsTool } = require('./kumiki-docs');
const { todoTool, withBuildCheck, withCheckpoints } = require('./session-tools');
const { PLAN_MODE_NOTE } = require('./permissions');

/** A host over the app's views. */
function viewHost({ panels, run, files, workspaceFolders = () => [files.root()].filter(Boolean), kumikiApi = null,
    kumikiSource = () => null, kumikiExamples = () => null, kumikiDocs = () => null, systemPrompt = () => '', projects = null }) {
    return { files, frames: viewFrames({ panels, run, files }), view: { panels, run, workspaceFolders, resolve: (file) => files.resolve(file) },
        kumikiApi, kumikiSource, kumikiExamples, kumikiDocs, systemPrompt, projects };
}

/** The tools any agent gets: the built-in one, and others over MCP. */
function sharedTools(host) {
    return [
        ...(host.view ? createKigumiTools(host.view) : []),
        ...(host.projects ? createProjectTools(host.projects) : []),
        checkFrameTool(host.frames),
        ...(host.frames.describe ? [describeFrameTool(host.frames)] : []),
        ...(host.kumikiApi ? [kumikiApiTool(host.kumikiApi)] : []),
    ];
}

/** Return the file tools supported by the host's project storage. */
function filesystemTools(host) {
    if (!host.files) return [];
    return [
        ...createFileTools({ files: host.files }),
        ...(host.files.create && host.files.deleteFile && host.files.rename
            ? createFileManagementTools({ files: host.files }) : []),
    ];
}

/**
 * Return MCP tools: the shared ones, kumiki's docs (the built-in agent reads .kigumi/docs/ instead),
 * and file access when the client cannot access the project directly.
 */
function mcpTools(host, { fileAccess = false } = {}) {
    return [...sharedTools(host), ...(host.kumikiDocs ? [kumikiDocsTool(host.kumikiDocs)] : []),
        ...(fileAccess ? filesystemTools(host) : [])];
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
    const fileTools = filesystemTools(host).map((tool) => withCheckpoints(
        withBuildCheck(tool, { files: host.files, frames: host.frames, onPictures }),
        { files: host.files, checkpoints }));
    return [...sharedTools(host), ...fileTools, todoTool(onTodos)];
}

/** The built-in agent's system prompt. */
function instructions(host, { planMode = false } = {}) {
    const prompt = host.systemPrompt(host.kumikiSource(), host.kumikiExamples());
    return planMode ? `${prompt}\n\n${PLAN_MODE_NOTE}` : prompt;
}

module.exports = { viewHost, sharedTools, mcpTools, agentTools, instructions };
