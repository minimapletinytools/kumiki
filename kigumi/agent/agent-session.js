/**
 * The agent panel's session, in the app's own process (never the page): its settings, conversations
 * and queued requests, and what it does with each message the panel sends. A turn is agent/turn.js;
 * tool permissions are agent/permission-gate.js.
 *
 * The panel and this talk in messages (webview/agent/protocol.js lists them):
 *   panel -> here:  agent/panel-messages.js, with each one's shape
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

const { agentTools } = require('./agent');
const { MODELS, findModel, routeModel } = require('./models');
const { languageModelFor } = require('./agent-loop');
const { Conversation } = require('./conversation');
const { PERMISSION_MODES, permissionMode } = require('./permissions');
const { PermissionGate } = require('./permission-gate');
const { parsePanelMessage } = require('./panel-messages');
const { runPanelTurn, describeFailure } = require('./turn');
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

/** A conversation's title: the start of its first request. */
const titleOf = (text) => (text.length > 60 ? `${text.slice(0, 57)}…` : text);


/** What the session does with each message the panel sends (agent/panel-messages.js), as `this`. */
const HANDLERS = {
    'agent:ready'() {
        this.postState();
        // The panel (re)loaded: show what it had, or, the first time, the latest conversation.
        if (this.conversation.log.length) {
            this.postRaw({ type: 'agent:replay', events: this.conversation.render() });
        } else if (!this.restored) {
            const latest = this._project() && this.conversations.list(this._project())[0];
            if (latest) this.openConversation(latest.id);
        }
        this.restored = true;
        if (this.busy) this.postRaw({ type: 'agent:busy', busy: true });
    },
    'agent:prompt'({ text, images }) {
        if (text.trim() || images.length) this.ask(text.trim(), images.slice(0, 4));
    },
    'agent:retry'() {
        this.ask(RETRY_PROMPT);
    },
    'agent:stop'() {
        this.stop();
    },
    'agent:clear'() {
        this.stop();
        this.startConversation();
    },
    'agent:unqueue'({ id }) {
        this.queue = this.queue.filter((queued) => queued.id !== id);
        this.postRaw({ type: 'agent:dequeued', id });
    },
    'agent:permissionAnswer'(answer) {
        this.permissions.answer(answer);
    },
    'agent:restore'({ turn, force }) {
        if (!this.busy) void this.restore(turn, { force: force === true });
    },
    'agent:setModel'({ id }) {
        this.setSetting('agent.model', findModel(id, this.models.list()).id);
        this.postState();
    },
    'agent:setSetting'({ key, value }) {
        if (!Object.hasOwn(PANEL_SETTINGS, key)) return;
        if (PANEL_SETTINGS[key].valid(value)) this.setSetting(key, value);
        this.postState();
    },
    'agent:listFiles'() {
        void this._listFiles().then((files) => this.postRaw({ type: 'agent:files', files }));
    },
    'agent:listConversations'() {
        this.postConversations();
    },
    'agent:openConversation'({ id }) {
        if (!this.busy) this.openConversation(id);
    },
    'agent:deleteConversation'({ id }) {
        if (this._project()) this.conversations.remove(this._project(), id);
        if (this.conversation.id === id) {
            this.stop();
            this.startConversation();
        }
        this.postConversations();
    },
    'agent:signIn'({ provider }) {
        if (!this.account) return;
        this.account.signIn(provider).catch((error) => this.postRaw({ type: 'agent:error', key: 'agent.error.signIn',
            params: { error: error.message }, message: `Could not sign in: ${error.message}` }));
    },
    'agent:signOut'() {
        if (this.account) void this.account.signOut().then(() => this.postState());
    },
};

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
            checkpoints: () => this.conversation.checkpoints,
            onTodos: (items) => this.post({ type: 'agent:todos', items }),
            onPictures: (id, before, after) => this.postRaw({ type: 'agent:toolImages', id, before, after }),
        });
        // Panel events the messages don't hold are kept in the log, to show them again when reopened.
        this.post = (message) => {
            if (this.conversation) this.conversation.keep(message);
            post(message);
        };
        this.postRaw = post;
        this.permissions = new PermissionGate({
            tools: () => this.tools,
            settings: () => ({ mode: this.panelSetting('agent.permissionMode'), alwaysAllow: this.panelSetting('agent.alwaysAllow'),
                planMode: this.panelSetting('agent.planMode') }),
            allowAlways: (toolName) => {
                const allowed = this.panelSetting('agent.alwaysAllow');
                if (!allowed.includes(toolName)) this.setSetting('agent.alwaysAllow', [...allowed, toolName]);
                this.postState();
            },
            knownFile: (input) => this._knownFile(input),
            post: (message) => this.post(message),
        });
        this.conversations = conversations;
        this.setting = setting;
        this.setSetting = setSetting;
        this.account = account;
        this.models = models;
        this.createModel = createModel;
        this.log = log;
        this.abort = null;
        // Requests typed while the agent works, run in order once it is done.
        this.queue = [];
        this.nextQueued = 1;
        this.restored = false;
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

    /** A message from the panel; one it may not send, or not in its shape, is ignored. */
    handle(message) {
        const parsed = parsePanelMessage(message);
        if (parsed) HANDLERS[parsed.type].call(this, parsed);
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
        const { restored, conflicts } = await this.conversation.checkpoints.restore(turn, { force });
        if (conflicts.length) {
            this.postRaw({ type: 'agent:restoreConflict', turn, files: conflicts });
            return;
        }
        this.post({ type: 'agent:restored', turn });
        this.post({ type: 'agent:notice', key: 'agent.notice.restored', params: { files: restored.join(', ') },
            text: `Put back as they were before that request: ${restored.join(', ')}. The agent is told so with your next message.` });
        // The model still thinks its edits are there; say otherwise when the conversation carries on.
        this.conversation.log.push({ note: 'undo', text: `The user undid your changes to ${restored.join(', ')}: those files are back as they were before.` });
        this._saveConversation(this.conversation, '');
    }

    /** The project conversations are kept for, when there is somewhere to keep them. */
    _project() {
        return this.conversations ? this.files.root() : null;
    }

    startConversation(conversation = new Conversation(this.files)) {
        this.conversation = conversation;
    }

    openConversation(id) {
        const found = this._project() && this.conversations.load(this._project(), id);
        if (!found) return;
        this.startConversation(Conversation.load(this.files, found));
        this.postRaw({ type: 'agent:replay', events: this.conversation.render() });
    }

    postConversations() {
        this.postRaw({
            type: 'agent:conversations',
            items: this._project() ? this.conversations.list(this._project()) : [],
            current: this.conversation.id,
        });
    }

    _saveConversation(conversation, firstText) {
        const project = this._project();
        if (!project) return;
        const now = new Date().toISOString();
        if (!conversation.id) {
            Object.assign(conversation, { id: globalThis.crypto.randomUUID(), title: titleOf(firstText), createdAt: now });
        }
        try {
            this.conversations.save(project, { ...conversation.toJSON(), model: this.model.id, updatedAt: now });
        } catch (error) {
            this.log(`[agent] could not save the conversation: ${error.message}`);
        }
    }

    stop() {
        if (this.abort) {
            this.abort.abort();
        }
        this.permissions.refuseAll();
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
        return this.conversation.checkpoints.wrote(target) || this.host.frames.shows(target);
    }

    /** What the user is looking at, or null. */
    _describe() {
        return this.host.view ? this.host.view.panels.describe() : Promise.resolve(null);
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

    /** Run `text` as a turn of the current conversation (agent/turn.js), then the next request queued. */
    async prompt(text, images = []) {
        if (this.busy) {
            this.ask(text, images);
            return;
        }
        const route = this.route();
        if (!route) {
            this.postRaw({ type: 'agent:error', key: 'agent.route.setKey',
                message: 'Sign in to use the agent, or set agent.openrouterApiKey in settings.' });
            return;
        }
        const abort = new AbortController();
        this.abort = abort;
        // The conversation this turn belongs to; if another starts meanwhile, the turn keeps out of it.
        const { conversation } = this;
        const ours = () => this.conversation === conversation;
        this.post({ type: 'agent:busy', busy: true });
        try {
            await runPanelTurn({
                conversation, text, images, host: this.host, tools: this.tools, profile: this.model,
                createModel: () => this.createModel(route, { fetch: route.via === 'backend' ? this.account.fetchWithToken : undefined }),
                settings: { maxOutputTokens: this.panelSetting('agent.maxOutputTokens'), planMode: this.panelSetting('agent.planMode') },
                askPermission: (toolName, input) => this.permissions.ask(toolName, input),
                describe: () => this._describe(),
                abortSignal: abort.signal,
                post: (event) => { if (ours()) this.post(event); },
                charged: (costUsd) => this._charged(route, costUsd),
                log: this.log,
            });
        } finally {
            this.abort = null;
            this.post({ type: 'agent:busy', busy: false });
            if (route.via === 'backend') {
                void this.account.refreshBalance().catch(() => {});
            }
            if (ours()) this._saveConversation(conversation, text);
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
