/**
 * The agent panel's conversation: the Claude Agent SDK, run in the app's own process (never the
 * page), with Kigumi's tools served in process.
 *
 * The panel and this talk in messages:
 *   panel -> here:  agent:prompt {text}, agent:stop, agent:clear, agent:permissionAnswer {requestId, allow}
 *   here -> panel:  agent:busy {busy}, agent:text {text} (streamed), agent:tool {id, name, input},
 *                   agent:toolResult {id, isError, text}, agent:permission {requestId, toolName, input},
 *                   agent:done {isError, error?, costUsd?}, agent:error {message}
 *
 * Auth is the SDK's: an API key from settings or the environment, else the user's Claude login.
 */

const { createKigumiTools } = require('./tools');

/** Kigumi tools that only look, and the agent's own read-only tools: run without asking. */
const BUILT_IN_READ_ONLY = ['Read', 'Glob', 'Grep'];

const SYSTEM_PROMPT_APPEND = [
    'You are the agent inside Kigumi, an app for designing timber frames in Python with the kumiki',
    'library. The user sees their frame in 3D views and drawings while you work. Use the kigumi tools:',
    'describe_panel to see what they are looking at and have selected (start there when they say',
    '"this" or "the selected"), refresh_view after editing a frame file and read_view_log to check it',
    'built, screenshot to look at the result. Sizes from the tools are in metres, in world space.',
].join(' ');

function summarise(content) {
    if (typeof content === 'string') {
        return content;
    }
    if (Array.isArray(content)) {
        return content.map((part) => (part && part.type === 'text' ? part.text : part && part.type === 'image' ? '[image]' : ''))
            .filter(Boolean).join('\n');
    }
    return '';
}

/**
 * What one SDK message means for the panel, as zero or more panel messages. Text arrives as stream
 * deltas, so a finished assistant message contributes only its tool calls.
 */
function toPanelEvents(message) {
    if (!message || typeof message !== 'object') {
        return [];
    }
    if (message.type === 'stream_event' && !message.parent_tool_use_id) {
        const event = message.event || {};
        if (event.type === 'content_block_delta' && event.delta && event.delta.type === 'text_delta') {
            return [{ type: 'agent:text', text: event.delta.text }];
        }
        return [];
    }
    if (message.type === 'assistant' && !message.parent_tool_use_id) {
        return ((message.message && message.message.content) || [])
            .filter((block) => block.type === 'tool_use')
            .map((block) => ({ type: 'agent:tool', id: block.id, name: block.name, input: block.input }));
    }
    if (message.type === 'user' && !message.parent_tool_use_id) {
        const content = (message.message && message.message.content) || [];
        return (Array.isArray(content) ? content : [])
            .filter((block) => block.type === 'tool_result')
            .map((block) => ({
                type: 'agent:toolResult', id: block.tool_use_id, isError: Boolean(block.is_error),
                text: summarise(block.content).slice(0, 2000),
            }));
    }
    if (message.type === 'result') {
        const isError = message.subtype !== 'success' || Boolean(message.is_error);
        return [{
            type: 'agent:done',
            isError,
            error: isError ? (summarise(message.result) || (message.errors || []).join('\n') || message.subtype) : undefined,
            costUsd: typeof message.total_cost_usd === 'number' ? message.total_cost_usd : undefined,
        }];
    }
    return [];
}

class AgentSession {
    /**
     * @param {object} options
     * @param {object} options.panels         a panel directory (panel-directory.js)
     * @param {(id: string, args?: object) => Promise<any>} options.run  an app command
     * @param {(message: object) => void} options.post  to the agent panel
     * @param {() => string|null} options.cwd           the workspace folder
     * @param {(key: string, fallback: any) => any} options.setting
     * @param {string} [options.version]
     * @param {(line: string) => void} [options.log]
     */
    constructor({ panels, run, post, cwd, setting, version = '0.0.0', log = () => {} }) {
        this.tools = createKigumiTools({ panels, run, workspaceFolders: () => [cwd()].filter(Boolean) });
        this.post = post;
        this.cwd = cwd;
        this.setting = setting;
        this.version = version;
        this.log = log;
        this.sessionId = null;
        this.abort = null;
        this.pendingPermissions = new Map();
        this.nextPermission = 1;
    }

    get busy() {
        return this.abort !== null;
    }

    /** Messages from the panel. */
    handle(message) {
        if (!message) return;
        if (message.type === 'agent:prompt' && typeof message.text === 'string' && message.text.trim()) {
            void this.prompt(message.text.trim());
        } else if (message.type === 'agent:stop') {
            this.stop();
        } else if (message.type === 'agent:clear') {
            this.stop();
            this.sessionId = null;
        } else if (message.type === 'agent:permissionAnswer') {
            const answer = this.pendingPermissions.get(message.requestId);
            this.pendingPermissions.delete(message.requestId);
            if (answer) answer(Boolean(message.allow));
        }
    }

    stop() {
        if (this.abort) {
            this.abort.abort();
        }
        for (const answer of this.pendingPermissions.values()) {
            answer(false);
        }
        this.pendingPermissions.clear();
    }

    _askPermission(toolName, input) {
        const requestId = this.nextPermission++;
        return new Promise((resolve) => {
            this.pendingPermissions.set(requestId, resolve);
            this.post({ type: 'agent:permission', requestId, toolName, input });
        });
    }

    async prompt(text) {
        if (this.busy) {
            this.post({ type: 'agent:error', message: 'Still working on the last message. Stop it first.' });
            return;
        }
        const abort = new AbortController();
        this.abort = abort;
        this.post({ type: 'agent:busy', busy: true });
        try {
            const sdk = await import('@anthropic-ai/claude-agent-sdk');
            const kigumi = sdk.createSdkMcpServer({
                name: 'kigumi',
                version: this.version,
                tools: this.tools.map((tool) => sdk.tool(tool.name, tool.description, tool.shape,
                    async (args) => ({ content: await tool.run(args || {}) }))),
            });
            const readOnly = new Set([
                ...BUILT_IN_READ_ONLY,
                ...this.tools.filter((tool) => tool.readOnly).map((tool) => `mcp__kigumi__${tool.name}`),
            ]);
            const apiKey = this.setting('agent.apiKey', '');
            const model = this.setting('agent.model', '');
            const options = {
                abortController: abort,
                cwd: this.cwd() || undefined,
                mcpServers: { kigumi },
                includePartialMessages: true,
                permissionMode: 'default',
                settingSources: ['project'],
                // Looking is allowed; anything else asks the user in the panel.
                canUseTool: async (toolName, input) => (readOnly.has(toolName) || await this._askPermission(toolName, input)
                    ? { behavior: 'allow', updatedInput: input }
                    : { behavior: 'deny', message: 'The user said no.' }),
                systemPrompt: { type: 'preset', preset: 'claude_code', append: SYSTEM_PROMPT_APPEND },
                env: {
                    ...process.env,
                    CLAUDE_AGENT_SDK_CLIENT_APP: `kigumi/${this.version}`,
                    ...(apiKey ? { ANTHROPIC_API_KEY: apiKey } : {}),
                },
                ...(model ? { model } : {}),
                ...(this.sessionId ? { resume: this.sessionId } : {}),
            };
            for await (const message of sdk.query({ prompt: text, options })) {
                if (message.type === 'system' && message.subtype === 'init' && message.session_id) {
                    this.sessionId = message.session_id;
                }
                for (const event of toPanelEvents(message)) {
                    this.post(event);
                }
            }
        } catch (error) {
            if (abort.signal.aborted) {
                this.post({ type: 'agent:done', isError: false, stopped: true });
            } else {
                this.log(`[agent] ${(error && error.stack) || error}`);
                this.post({ type: 'agent:error', message: String((error && error.message) || error) });
            }
        } finally {
            this.abort = null;
            this.post({ type: 'agent:busy', busy: false });
        }
    }
}

module.exports = { AgentSession, toPanelEvents, SYSTEM_PROMPT_APPEND };
