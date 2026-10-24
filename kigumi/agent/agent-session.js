/**
 * The agent panel's conversation, run in the app's own process (never the page) on the built-in
 * agent loop (agent/agent-loop.js), with Kigumi's tools and the project's files.
 *
 * The panel and this talk in messages:
 *   panel -> here:  agent:ready, agent:prompt {text}, agent:stop, agent:clear,
 *                   agent:permissionAnswer {requestId, allow}, agent:setModel {id},
 *                   agent:signIn {provider}, agent:signOut
 *   here -> panel:  agent:state {models, model, via, account}, agent:busy {busy}, agent:text {text} (streamed),
 *                   agent:reasoning {text} (streamed), agent:tool {id, name, input},
 *                   agent:toolResult {id, isError, text}, agent:notice {text},
 *                   agent:permission {requestId, toolName, input}, agent:done {isError, error?, costUsd?},
 *                   agent:error {message}
 *
 * Requests go where agent/models.js routeModel says: an Anthropic or OpenRouter key from settings,
 * else Kigumi's backend when signed in.
 */

const { createKigumiTools } = require('./tools');
const { MODELS, findModel, routeModel } = require('./models');
const { runTurn, languageModelFor } = require('./agent-loop');

const SYSTEM_PROMPT = [
    'You are the agent inside Kigumi, an app for designing timber frames in Python with the kumiki',
    'library. The user sees their frame in 3D views and drawings while you work.',
    'Use describe_panel to see what they are looking at and have selected (start there when they say',
    '"this" or "the selected"). Read and edit the project\'s files with the file tools; after editing a',
    'frame file, refresh_view and read_view_log to check it built, and screenshot to look at the result.',
    'The kumiki docs are in .kigumi/docs/ in the project; read those and the project\'s patterns, not the',
    'kumiki package\'s source in .venv, which is large. Sizes from the tools are in metres, in world',
    'space. Keep replies short.',
].join(' ');

/** What to tell the user for a failed request. */
function describeFailure(error) {
    const status = error && (error.statusCode || (error.lastError && error.lastError.statusCode));
    if (status === 402) {
        return 'Out of credit.';
    }
    if (status === 401) {
        return 'Not signed in, or the API key was refused.';
    }
    return String((error && error.message) || error);
}

class AgentSession {
    /**
     * @param {object} options
     * @param {object} options.panels         a panel directory (panel-directory.js)
     * @param {(id: string, args?: object) => Promise<any>} options.run  an app command
     * @param {(message: object) => void} options.post  to the agent panel
     * @param {() => string|null} options.cwd           the workspace folder
     * @param {(key: string, fallback: any) => any} options.setting
     * @param {(key: string, value: any) => void} [options.setSetting]
     * @param {object[]} [options.fileTools]   tools for the project's files (agent/file-tools.js)
     * @param {object|null} [options.account]  the Kigumi account (agent/account.js)
     * @param {(route: object, options: {fetch?: typeof fetch}) => Promise<object>} [options.createModel]
     *     a language model for a route
     * @param {(line: string) => void} [options.log]
     */
    constructor({ panels, run, post, cwd, setting, setSetting = () => {}, fileTools = [], account = null,
        createModel = languageModelFor, log = () => {} }) {
        this.tools = [...createKigumiTools({ panels, run, workspaceFolders: () => [cwd()].filter(Boolean) }), ...fileTools];
        this.post = post;
        this.setting = setting;
        this.setSetting = setSetting;
        this.account = account;
        this.createModel = createModel;
        this.log = log;
        this.history = [];
        this.abort = null;
        this.pendingPermissions = new Map();
        this.nextPermission = 1;
    }

    get busy() {
        return this.abort !== null;
    }

    get model() {
        return findModel(this.setting('agent.model', ''));
    }

    /** Where requests for the chosen model go, or null. */
    route() {
        return routeModel(this.model, {
            anthropicKey: this.setting('agent.apiKey', ''),
            openrouterKey: this.setting('agent.openrouterApiKey', ''),
            backend: this.account && this.account.backend(),
        });
    }

    postState() {
        const route = this.route();
        this.post({
            type: 'agent:state',
            models: MODELS.map(({ id, label }) => ({ id, label })),
            model: this.model.id,
            via: route ? route.via : null,
            account: this.account ? this.account.state() : { configured: false },
        });
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
            this.history = [];
        } else if (message.type === 'agent:permissionAnswer') {
            const answer = this.pendingPermissions.get(message.requestId);
            this.pendingPermissions.delete(message.requestId);
            if (answer) answer(Boolean(message.allow));
        } else if (message.type === 'agent:setModel' && typeof message.id === 'string') {
            this.setSetting('agent.model', findModel(message.id).id);
            this.postState();
        } else if (message.type === 'agent:ready') {
            this.postState();
        } else if (message.type === 'agent:signIn' && this.account) {
            this.account.signIn(message.provider === 'google' ? 'google' : 'github')
                .catch((error) => this.post({ type: 'agent:error', message: `Could not sign in: ${error.message}` }));
        } else if (message.type === 'agent:signOut' && this.account) {
            void this.account.signOut().then(() => this.postState());
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
        const route = this.route();
        if (!route) {
            this.post({ type: 'agent:error', message: 'Sign in to use the agent, or set agent.openrouterApiKey '
                + '(or agent.apiKey, an Anthropic key) in settings.' });
            return;
        }
        const abort = new AbortController();
        this.abort = abort;
        this.post({ type: 'agent:busy', busy: true });
        try {
            const { history, costUsd } = await runTurn({
                model: await this.createModel(route, { fetch: route.via === 'backend' ? this.account.fetchWithToken : undefined }),
                images: this.model.images,
                tools: this.tools,
                system: SYSTEM_PROMPT,
                history: this.history,
                prompt: text,
                abortSignal: abort.signal,
                askPermission: (toolName, input) => this._askPermission(toolName, input),
                onEvent: (event) => this.post(event),
            });
            this.history = history;
            this.post({ type: 'agent:done', isError: false, costUsd });
        } catch (error) {
            // Keep what the turn did before it failed, so asking again carries on from there.
            if (error && Array.isArray(error.history)) this.history = error.history;
            if (abort.signal.aborted) {
                this.post({ type: 'agent:done', isError: false, stopped: true });
            } else {
                this.log(`[agent] ${(error && error.stack) || error}`);
                this.post({ type: 'agent:done', isError: true, error: describeFailure(error) });
            }
        } finally {
            this.abort = null;
            this.post({ type: 'agent:busy', busy: false });
            if (route.via === 'backend') {
                void this.account.refreshBalance().catch(() => {});
            }
        }
    }
}

module.exports = { AgentSession, SYSTEM_PROMPT, describeFailure };
