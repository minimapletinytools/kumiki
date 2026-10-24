/**
 * The agent panel's conversation, run in the app's own process (never the page) on the built-in
 * agent loop (agent/agent-loop.js), with Kigumi's tools and the project's files.
 *
 * The panel and this talk in messages:
 *   panel -> here:  agent:ready, agent:prompt {text}, agent:stop, agent:clear,
 *                   agent:permissionAnswer {requestId, allow}, agent:setModel {id},
 *                   agent:signIn {provider}, agent:signOut, agent:setSetting {key, value}
 *   here -> panel:  agent:state {models, model, via, account, settings}, agent:busy {busy}, agent:text {text} (streamed),
 *                   agent:reasoning {text} (streamed), agent:tool {id, name, input},
 *                   agent:toolResult {id, isError, text}, agent:notice {text},
 *                   agent:permission {requestId, toolName, input}, agent:done {isError, error?, costUsd?},
 *                   agent:error {message}
 *
 * Requests go where agent/models.js routeModel says: an Anthropic or OpenRouter key from settings,
 * else Kigumi's backend when signed in.
 */

const path = require('path');

const { createKigumiTools } = require('./tools');
const { MODELS, findModel, routeModel } = require('./models');
const { runTurn, languageModelFor } = require('./agent-loop');

/** The settings the panel's own menu sets, with their defaults. */
const PANEL_SETTINGS = { 'agent.bypassPermissions': false, 'agent.showOnStartup': true };

const SYSTEM_PROMPT = [
    'You are the agent inside Kigumi, an app for designing timber frames in Python with the kumiki',
    'library. The user sees their frame in 3D views and drawings while you work.',
    'Each message comes with what they are looking at (the active panel and its selection); use',
    'describe_panel for more. Find things with search_files rather than reading whole files. Editing a',
    'file a view shows rebuilds it, and the edit\'s result says whether it built; screenshot to look at it.',
    'The kumiki docs are in .kigumi/docs/ in the project; read those and the project\'s patterns, not the',
    'kumiki package\'s source in .venv, which is large. Sizes from the tools are in metres, in world',
    'space. Keep replies short.',
].join(' ');

/** The most of the active panel's description sent with a message. */
const MAX_CONTEXT_CHARS = 2000;

/** A message as sent: what the user is looking at, then what they wrote. */
function withContext(text, described) {
    if (!described) return text;
    const context = JSON.stringify(described);
    const shown = context.length > MAX_CONTEXT_CHARS ? `${context.slice(0, MAX_CONTEXT_CHARS)}…` : context;
    return `[What I'm looking at in Kigumi: ${shown}]\n\n${text}`;
}

/** The build report's result as text for the agent, appended to an edit's own. */
function describeBuild(report) {
    if (!report || report.reason === 'session-not-found') return null;
    const lines = (report.entries || []).map((entry) => `${entry.level}: ${entry.message}`);
    if (report.error) lines.unshift(`error: ${report.error}`);
    return report.ok
        ? `The view of this file rebuilt without errors.${lines.length ? `\n${lines.join('\n')}` : ''}`
        : `The view of this file rebuilt with errors:\n${lines.join('\n').slice(0, 4000)}`;
}

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
        this.tools = [...createKigumiTools({ panels, run, workspaceFolders: () => [cwd()].filter(Boolean) }),
            ...fileTools.map((tool) => this._buildingAfterEdits(tool, { panels, run, cwd }))];
        this.panels = panels;
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

    /**
     * `tool`, and when it writes or edits a file a view shows, that view rebuilt with the build's
     * result: one step for the agent where it took three (edit, refresh, read the log).
     */
    _buildingAfterEdits(tool, { panels, run, cwd }) {
        if (!['write_file', 'edit_file'].includes(tool.name)) return tool;
        return {
            ...tool,
            run: async (args) => {
                const result = await tool.run(args);
                const target = path.resolve(cwd() || '', args.file_path || '');
                const shown = panels.list().some((panel) => panel.kind === 'viewer' && panel.filePath
                    && path.resolve(panel.filePath) === target);
                if (!shown) return result;
                const report = await run('kigumi.automationBuildReport', { filePath: target, reason: 'agent edit' })
                    .catch((error) => ({ ok: false, error: error.message, entries: [] }));
                const built = describeBuild(report);
                return built ? [...result, { type: 'text', text: built }] : result;
            },
        };
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
            settings: Object.fromEntries(Object.entries(PANEL_SETTINGS)
                .map(([key, fallback]) => [key, this.setting(key, fallback) === true])),
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
        } else if (message.type === 'agent:setSetting' && message.key in PANEL_SETTINGS) {
            this.setSetting(message.key, Boolean(message.value));
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
        if (this.setting('agent.bypassPermissions', false) === true) {
            return Promise.resolve(true);
        }
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
                cacheMarks: Boolean(this.model.cacheMarks),
                tools: this.tools,
                system: SYSTEM_PROMPT,
                history: this.history,
                prompt: withContext(text, await this.panels.describe().catch(() => null)),
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

module.exports = { AgentSession, SYSTEM_PROMPT, describeFailure, withContext, describeBuild };
