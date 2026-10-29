/**
 * The agent panel's conversation, run in the app's own process (never the page) on the built-in
 * agent loop (agent/agent-loop.js), with the tools and instructions agent/agent.js builds from a host.
 *
 * The panel and this talk in messages (webview/agent/protocol.js lists them):
 *   panel -> here:  agent:ready, agent:prompt {text, images?: [{mediaType, data}]}, agent:stop,
 *                   agent:clear, agent:permissionAnswer {requestId, allow, always?}, agent:setModel {id},
 *                   agent:restore {turn, force?}, agent:unqueue {id}, agent:retry, agent:listFiles,
 *                   agent:signIn {provider}, agent:signOut, agent:setSetting {key, value},
 *                   agent:listConversations, agent:openConversation {id}, agent:deleteConversation {id}
 *   here -> panel:  agent:state {models, model, via, account, settings, strings}, agent:busy {busy},
 *                   agent:text {text}, agent:reasoning {text} (both streamed), agent:tool {id, name, input},
 *                   agent:toolResult {id, isError, text}, agent:toolImages {id, before, after},
 *                   agent:notice {text, key?, params?}, agent:context {tokens, window},
 *                   agent:permission {requestId, toolName, input}, agent:done {isError, error?, costUsd?},
 *                   agent:error {message, key?, params?}, agent:conversations {items, current}, agent:replay {events},
 *                   agent:checkpoint {turn, files}, agent:restored {turn}, agent:restoreConflict {turn, files},
 *                   agent:queued {id, text}, agent:dequeued {id}, agent:userMessage {text, images},
 *                   agent:todos {items}, agent:files {files}
 *
 * Requests go where agent/models.js routeModel says: the OpenRouter key from settings, else
 * Kigumi's backend when signed in.
 */

const { agentTools, instructions } = require('./agent');
const { MODELS, findModel, routeModel } = require('./models');
const { runTurn, languageModelFor } = require('./agent-loop');
const { Checkpoints } = require('./checkpoints');
const { PERMISSION_MODES, PLAN_MODE_REFUSAL, permissionMode, decide } = require('./permissions');
const { promptContent } = require('./prompt-content');
const { describeBuild } = require('./session-tools');

/** The settings the panel's own menu sets: their defaults, and what a value must be. */
const PANEL_SETTINGS = {
    'agent.permissionMode': { fallback: 'ask', valid: (value) => PERMISSION_MODES.includes(value) },
    'agent.alwaysAllow': { fallback: [], valid: (value) => Array.isArray(value) && value.every((name) => typeof name === 'string') },
    'agent.showOnStartup': { fallback: true, valid: (value) => typeof value === 'boolean' },
    'agent.planMode': { fallback: false, valid: (value) => typeof value === 'boolean' },
    // The most one step may write, in tokens; the backend allows up to 32k.
    'agent.maxOutputTokens': { fallback: 8000, valid: (value) => [8000, 16000, 32000].includes(value) },
};

/** What the agent says to carry on after a turn that failed. */
const RETRY_PROMPT = 'Carry on from where you stopped.';

/** What the panel shows that a reopened conversation shows again. */
const SHOWN = new Set(['agent:userMessage', 'agent:text', 'agent:reasoning', 'agent:tool', 'agent:toolResult',
    'agent:notice', 'agent:done', 'agent:error', 'agent:checkpoint', 'agent:restored', 'agent:todos']);

/** A conversation's title: the start of its first request. */
const titleOf = (text) => (text.length > 60 ? `${text.slice(0, 57)}…` : text);

/** What to tell the user for a failed request: {key, text}, the key for the panel to show it in its language. */
function describeFailure(error) {
    const status = error && (error.statusCode || (error.lastError && error.lastError.statusCode));
    if (status === 402) {
        return { key: 'agent.error.noCredit', text: 'Out of credit.' };
    }
    if (status === 401) {
        return { key: 'agent.error.refused', text: 'Not signed in, or the API key was refused.' };
    }
    return { text: String((error && error.message) || error) };
}

class AgentSession {
    /**
     * @param {object} options
     * @param {object} options.host           what the agent works with (agent/agent.js)
     * @param {(message: object) => void} options.post  to the agent panel
     * @param {(key: string, fallback: any) => any} options.setting
     * @param {(key: string, value: any) => void} [options.setSetting]
     * @param {object|null} [options.account]  the Kigumi account (agent/account.js)
     * @param {{list: () => object[]}} [options.models]  the models offered (models.js createModelList)
     * @param {object|null} [options.conversations]  where past conversations are kept (conversation-store.js)
     * @param {(route: object, options: {fetch?: typeof fetch}) => Promise<object>} [options.createModel]
     * @param {(line: string) => void} [options.log]
     * @param {object} [options.strings]   the panel's strings in the app's language (the agent.* keys of i18n/locales)
     */
    constructor({ host, post, setting, setSetting = () => {}, account = null,
        conversations = null, createModel = languageModelFor, log = () => {}, strings = {}, models = { list: () => MODELS } }) {
        this.strings = Object.fromEntries(Object.entries(strings).filter(([key]) => key.startsWith('agent.')));
        this.host = host;
        this.files = host.files;
        this.tools = agentTools(host, {
            checkpoints: () => this.checkpoints,
            onTodos: (items) => this.post({ type: 'agent:todos', items }),
            onPictures: (id, before, after) => this.postRaw({ type: 'agent:toolImages', id, before, after }),
        });
        // Everything the panel shows of a conversation is also kept, to show it again when reopened.
        this.post = (message) => {
            if (SHOWN.has(message.type)) this.transcript.push(message);
            post(message);
        };
        this.postRaw = post;
        this.conversations = conversations;
        this.setting = setting;
        this.setSetting = setSetting;
        this.account = account;
        this.models = models;
        this.createModel = createModel;
        this.log = log;
        this.abort = null;
        this.pendingPermissions = new Map();
        this.nextPermission = 1;
        // Requests typed while the agent works, run in order once it is done.
        this.queue = [];
        this.nextQueued = 1;
        this.restored = false;
        // Changes when another conversation starts, so a turn still running can't write into it.
        this.generation = 0;
        this.startConversation();
    }

    get busy() {
        return this.abort !== null;
    }

    get model() {
        return findModel(this.setting('agent.model', ''), this.models.list());
    }

    /** Where requests for the chosen model go, or null. */
    route() {
        return routeModel(this.model, {
            openrouterKey: this.setting('agent.openrouterApiKey', ''),
            backend: this.account && this.account.backend(),
        });
    }

    postState() {
        const route = this.route();
        this.post({
            type: 'agent:state',
            models: this.models.list().map(({ id, label }) => ({ id, label })),
            model: this.model.id,
            via: route ? route.via : null,
            account: this.account ? this.account.state() : { configured: false },
            settings: Object.fromEntries(Object.keys(PANEL_SETTINGS).map((key) => [key, this.panelSetting(key)])),
            strings: this.strings,
        });
    }

    /** A setting the panel's menu sets, as it is or its default. */
    panelSetting(key) {
        const { fallback, valid } = PANEL_SETTINGS[key];
        const value = key === 'agent.permissionMode'
            ? permissionMode(this.setting(key, undefined), this.setting('agent.bypassPermissions', false))
            : this.setting(key, undefined);
        return valid(value) ? value : fallback;
    }

    /** Messages from the panel. */
    handle(message) {
        if (!message) return;
        if (message.type === 'agent:prompt' && typeof message.text === 'string' && (message.text.trim() || message.images)) {
            this.ask(message.text.trim(), Array.isArray(message.images) ? message.images.slice(0, 4) : []);
        } else if (message.type === 'agent:listFiles') {
            void this._listFiles().then((files) => this.postRaw({ type: 'agent:files', files }));
        } else if (message.type === 'agent:retry') {
            this.ask(RETRY_PROMPT);
        } else if (message.type === 'agent:unqueue') {
            this.queue = this.queue.filter((queued) => queued.id !== message.id);
            this.postRaw({ type: 'agent:dequeued', id: message.id });
        } else if (message.type === 'agent:restore' && Number.isInteger(message.turn)) {
            if (!this.busy) void this.restore(message.turn, { force: message.force === true });
        } else if (message.type === 'agent:stop') {
            this.stop();
        } else if (message.type === 'agent:clear') {
            this.stop();
            this.startConversation();
        } else if (message.type === 'agent:permissionAnswer') {
            const pending = this.pendingPermissions.get(message.requestId);
            this.pendingPermissions.delete(message.requestId);
            if (pending && message.allow && message.always) {
                const allowed = this.panelSetting('agent.alwaysAllow');
                if (!allowed.includes(pending.toolName)) this.setSetting('agent.alwaysAllow', [...allowed, pending.toolName]);
                this.postState();
            }
            if (pending) pending.answer(Boolean(message.allow));
        } else if (message.type === 'agent:setModel' && typeof message.id === 'string') {
            this.setSetting('agent.model', findModel(message.id, this.models.list()).id);
            this.postState();
        } else if (message.type === 'agent:setSetting' && message.key in PANEL_SETTINGS) {
            if (PANEL_SETTINGS[message.key].valid(message.value)) this.setSetting(message.key, message.value);
            this.postState();
        } else if (message.type === 'agent:listConversations') {
            this.postConversations();
        } else if (message.type === 'agent:openConversation' && typeof message.id === 'string') {
            if (!this.busy) this.openConversation(message.id);
        } else if (message.type === 'agent:deleteConversation' && typeof message.id === 'string') {
            if (this._project()) this.conversations.remove(this._project(), message.id);
            if (this.conversation && this.conversation.id === message.id) {
                this.stop();
                this.startConversation();
            }
            this.postConversations();
        } else if (message.type === 'agent:ready') {
            this.postState();
            // The panel (re)loaded: show what it had, or, the first time, the latest conversation.
            if (this.transcript.length) {
                this.postRaw({ type: 'agent:replay', events: this.transcript });
            } else if (!this.restored) {
                const latest = this._project() && this.conversations.list(this._project())[0];
                if (latest) this.openConversation(latest.id);
            }
            this.restored = true;
        } else if (message.type === 'agent:signIn' && this.account) {
            this.account.signIn(message.provider === 'google' ? 'google' : 'github')
                .catch((error) => this.post({ type: 'agent:error', key: 'agent.error.signIn', params: { error: error.message },
                    message: `Could not sign in: ${error.message}` }));
        } else if (message.type === 'agent:signOut' && this.account) {
            void this.account.signOut().then(() => this.postState());
        }
    }

    /** Every project file, for the panel's @-mention list. */
    async _listFiles() {
        try {
            return this.files.root() ? await this.files.list(undefined, 500) : [];
        } catch (_error) {
            return [];
        }
    }

    /** Put back the files the turns from `turn` on changed, unless some have changed since (then ask). */
    async restore(turn, { force = false } = {}) {
        const { restored, conflicts } = await this.checkpoints.restore(turn, { force });
        if (conflicts.length) {
            this.postRaw({ type: 'agent:restoreConflict', turn, files: conflicts });
            return;
        }
        this.post({ type: 'agent:restored', turn });
        this.post({ type: 'agent:notice', key: 'agent.notice.restored', params: { files: restored.join(', ') },
            text: `Put back as they were before that request: ${restored.join(', ')}. The agent is told so with your next message.` });
        // The model still thinks its edits are there; say otherwise when the conversation carries on.
        this.history.push({ role: 'user', content: `[I undid your changes to ${restored.join(', ')}: those files are back as they were before.]` },
            { role: 'assistant', content: 'Understood.' });
        this._saveConversation('');
    }

    /** The project conversations are kept for, when there is somewhere to keep them. */
    _project() {
        return this.conversations ? this.files.root() : null;
    }

    startConversation() {
        this.generation += 1;
        this.history = [];
        this.transcript = [];
        this.conversation = null;
        this.checkpoints = new Checkpoints(this.files);
        this.turn = 0;
    }

    openConversation(id) {
        const found = this._project() && this.conversations.load(this._project(), id);
        if (!found) return;
        this.startConversation();
        this.conversation = found;
        this.history = found.history || [];
        this.transcript = found.transcript || [];
        this.checkpoints = new Checkpoints(this.files, found.checkpoints || []);
        this.turn = found.turn || 0;
        this.postRaw({ type: 'agent:replay', events: this.transcript });
    }

    postConversations() {
        this.postRaw({
            type: 'agent:conversations',
            items: this._project() ? this.conversations.list(this._project()) : [],
            current: this.conversation ? this.conversation.id : null,
        });
    }

    _saveConversation(firstText) {
        const project = this._project();
        if (!project) return;
        const now = new Date().toISOString();
        if (!this.conversation) {
            this.conversation = { id: globalThis.crypto.randomUUID(), title: titleOf(firstText), createdAt: now };
        }
        Object.assign(this.conversation, { model: this.model.id, updatedAt: now, history: this.history,
            transcript: this.transcript, checkpoints: this.checkpoints.toJSON(), turn: this.turn });
        try {
            this.conversations.save(project, this.conversation);
        } catch (error) {
            this.log(`[agent] could not save the conversation: ${error.message}`);
        }
    }

    stop() {
        if (this.abort) {
            this.abort.abort();
        }
        for (const { answer } of this.pendingPermissions.values()) {
            answer(false);
        }
        this.pendingPermissions.clear();
        // Stopping drops what was waiting too.
        for (const queued of this.queue) this.postRaw({ type: 'agent:dequeued', id: queued.id });
        this.queue = [];
    }

    /** Whether a 'run' tool's file is one a view shows or the agent wrote; a tool with no file runs a view's. */
    _knownFile(input) {
        if (!input || !input.file_path) return true;
        let target;
        try {
            target = this.files.resolve(input.file_path);
        } catch (_error) {
            return false;
        }
        return this.checkpoints.wrote(target) || this.host.frames.shows(target);
    }

    /** What the user is looking at, or null. */
    _describe() {
        return this.host.view ? this.host.view.panels.describe() : Promise.resolve(null);
    }

    _askPermission(toolName, input) {
        // An unknown tool is treated as one that edits.
        const tool = this.tools.find((candidate) => candidate.name === toolName) || { name: toolName, effect: 'edit' };
        const decision = decide({
            mode: this.panelSetting('agent.permissionMode'),
            alwaysAllow: this.panelSetting('agent.alwaysAllow'),
            planMode: this.panelSetting('agent.planMode'),
        }, tool, { knownFile: tool.effect === 'run' && this._knownFile(input) });
        if (decision === 'refuse') return Promise.reject(new Error(PLAN_MODE_REFUSAL));
        if (decision === 'allow') return Promise.resolve(true);
        const requestId = this.nextPermission++;
        return new Promise((resolve) => {
            this.pendingPermissions.set(requestId, { toolName, answer: resolve });
            this.post({ type: 'agent:permission', requestId, toolName, input });
        });
    }

    /** A request from the panel: run now, or after the turn running, in the order asked. */
    ask(text, images = []) {
        if (!this.busy) {
            void this.prompt(text, images);
            return;
        }
        const id = this.nextQueued++;
        this.queue.push({ id, text, images });
        this.postRaw({ type: 'agent:queued', id, text });
    }

    /** What the user is charged for `costUsd` of model use: through the account, with its markup. */
    _charged(route, costUsd) {
        if (typeof costUsd !== 'number' || route.via !== 'backend') return costUsd;
        const markup = this.account && this.account.state().markup;
        return typeof markup === 'number' ? costUsd * markup : costUsd;
    }

    async prompt(text, images = []) {
        if (this.busy) {
            this.ask(text, images);
            return;
        }
        const route = this.route();
        if (!route) {
            this.post({ type: 'agent:error', key: 'agent.route.setKey',
                message: 'Sign in to use the agent, or set agent.openrouterApiKey in settings.' });
            return;
        }
        const abort = new AbortController();
        this.abort = abort;
        // The conversation this turn belongs to; if another starts meanwhile, the turn keeps out of it.
        const generation = this.generation;
        const ours = () => this.generation === generation;
        this.transcript.push({ type: 'agent:userMessage', text, images: images.length });
        this.turn += 1;
        const turn = this.turn;
        const checkpoints = this.checkpoints;
        checkpoints.begin(turn);
        this.post({ type: 'agent:busy', busy: true });
        try {
            const { history, costUsd } = await runTurn({
                model: await this.createModel(route, {
                    fetch: route.via === 'backend' ? this.account.fetchWithToken : undefined,
                    onWait: () => {
                        if (ours()) this.post({ type: 'agent:notice', key: 'agent.notice.waitingRequest',
                            text: 'Waiting for the previous model request to finish. You can press Stop to cancel.' });
                    },
                }),
                images: this.model.images,
                cacheMarks: Boolean(this.model.cacheMarks),
                contextWindow: this.model.contextWindow,
                maxOutputTokens: this.panelSetting('agent.maxOutputTokens'),
                tools: this.tools,
                files: this.files.root() ? this.files : null,
                system: instructions(this.host, { planMode: this.panelSetting('agent.planMode') }),
                history: this.history,
                prompt: await promptContent({ text, images, files: this.files, describe: () => this._describe(),
                    modelSeesImages: this.model.images }),
                abortSignal: abort.signal,
                askPermission: (toolName, input) => this._askPermission(toolName, input),
                onEvent: (event) => { if (ours()) this.post(event); },
            });
            if (ours()) {
                this.history = history;
                this.post({ type: 'agent:done', isError: false, costUsd: this._charged(route, costUsd) });
            }
        } catch (error) {
            if (ours()) {
                // Keep what the turn did before it failed, so asking again carries on from there.
                if (error && Array.isArray(error.history)) this.history = error.history;
                if (abort.signal.aborted) {
                    this.post({ type: 'agent:done', isError: false, stopped: true });
                } else {
                    this.log(`[agent] ${(error && error.stack) || error}`);
                    const failure = describeFailure(error);
                    this.post({ type: 'agent:done', isError: true, error: failure.text, errorKey: failure.key });
                }
            }
        } finally {
            const changed = await checkpoints.end();
            if (changed && ours()) this.post({ type: 'agent:checkpoint', ...changed });
            this.abort = null;
            this.post({ type: 'agent:busy', busy: false });
            if (route.via === 'backend') {
                void this.account.refreshBalance().catch(() => {});
            }
            if (ours()) this._saveConversation(text);
            const next = this.queue.shift();
            if (next) {
                this.postRaw({ type: 'agent:dequeued', id: next.id });
                this.postRaw({ type: 'agent:userMessage', text: next.text, images: next.images.length });
                void this.prompt(next.text, next.images);
            }
        }
    }
}

module.exports = { AgentSession, RETRY_PROMPT, describeFailure, describeBuild };
