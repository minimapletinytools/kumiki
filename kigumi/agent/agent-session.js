/**
 * The agent panel's conversation, run in the app's own process (never the page) on the built-in
 * agent loop (agent/agent-loop.js), with Kigumi's tools and the project's files.
 *
 * The panel and this talk in messages:
 *   panel -> here:  agent:ready, agent:prompt {text}, agent:stop, agent:clear,
 *                   agent:permissionAnswer {requestId, allow, always?}, agent:setModel {id},
 *                   agent:restore {turn}, agent:unqueue {id}, agent:retry, agent:listFiles,
 *                   (agent:prompt may carry images: [{mediaType, data (base64)}])
 *                   agent:signIn {provider}, agent:signOut, agent:setSetting {key, value},
 *                   agent:listConversations, agent:openConversation {id}, agent:deleteConversation {id}
 *   here -> panel:  agent:state {models, model, via, account, settings}, agent:busy {busy}, agent:text {text} (streamed),
 *                   agent:reasoning {text} (streamed), agent:tool {id, name, input},
 *                   agent:toolResult {id, isError, text}, agent:notice {text}, agent:context {tokens, window},
 *                   agent:permission {requestId, toolName, input}, agent:done {isError, error?, costUsd?},
 *                   agent:error {message}
 *
 * Requests go where agent/models.js routeModel says: an Anthropic or OpenRouter key from settings,
 * else Kigumi's backend when signed in.
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');


const { z } = require('zod');

const { createKigumiTools } = require('./tools');
const { MODELS, findModel, routeModel } = require('./models');
const { runTurn, languageModelFor } = require('./agent-loop');

/**
 * How freely the agent changes things: ask before every tool that changes something, let it edit
 * files without asking (camera moves and the like still ask), or let it do everything.
 */
const PERMISSION_MODES = ['ask', 'edits', 'all'];
const FILE_EDIT_TOOLS = new Set(['write_file', 'edit_file']);

/** The settings the panel's own menu sets: their defaults, and what a value must be. */
const PANEL_SETTINGS = {
    'agent.permissionMode': { fallback: 'ask', valid: (value) => PERMISSION_MODES.includes(value) },
    'agent.alwaysAllow': { fallback: [], valid: (value) => Array.isArray(value) && value.every((name) => typeof name === 'string') },
    'agent.showOnStartup': { fallback: true, valid: (value) => typeof value === 'boolean' },
    'agent.planMode': { fallback: false, valid: (value) => typeof value === 'boolean' },
};

/** Added to the system prompt in plan mode, when nothing that changes anything runs. */
const PLAN_MODE_NOTE = 'Plan mode is on: look as much as you need, then propose a plan, and change nothing. Tools '
    + 'that change things are refused until the user turns plan mode off and asks you to go ahead.';

/** Most of a file an @-mention attaches, in characters. */
const MAX_MENTIONED_CHARS = 40000;

/** What the agent says to carry on after a turn that failed. */
const RETRY_PROMPT = 'Carry on from where you stopped.';

const SYSTEM_PROMPT = [
    'You are the agent inside Kigumi, an app for designing timber frames in Python with the kumiki',
    'library. The user sees their frame in 3D views and drawings while you work.',
    'Each message comes with what they are looking at (the active panel and its selection); use',
    'describe_panel for more. Find things with search_files rather than reading whole files. Editing a',
    'file a view shows rebuilds it, and the edit\'s result says whether it built; screenshot to look at it.',
    'The kumiki docs are in .kigumi/docs/ in the project; read those and the project\'s patterns, not the',
    'kumiki package\'s source in .venv, which is large. Sizes from the tools are in metres, in world',
    'space. For a task of several steps, keep a to-do list with update_todos and tick items off as you go.',
    'Keep replies short.',
].join(' ');

/** What the panel shows that a reopened conversation shows again. */
const SHOWN = new Set(['agent:userMessage', 'agent:text', 'agent:reasoning', 'agent:tool', 'agent:toolResult',
    'agent:notice', 'agent:done', 'agent:error', 'agent:checkpoint', 'agent:restored', 'agent:todos']);

/** A conversation's title: the start of its first request. */
const titleOf = (text) => (text.length > 60 ? `${text.slice(0, 57)}…` : text);

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
     * @param {object|null} [options.conversations]  where past conversations are kept (conversation-store.js)
     * @param {(route: object, options: {fetch?: typeof fetch}) => Promise<object>} [options.createModel]
     *     a language model for a route
     * @param {(line: string) => void} [options.log]
     */
    constructor({ panels, run, post, cwd, setting, setSetting = () => {}, fileTools = [], account = null,
        conversations = null, createModel = languageModelFor, log = () => {} }) {
        this.fileTools = fileTools;
        this.tools = [...createKigumiTools({ panels, run, workspaceFolders: () => [cwd()].filter(Boolean) }),
            ...fileTools.map((tool) => this._checkpointed(this._buildingAfterEdits(tool, { panels, run, cwd }), cwd)),
            this._todoTool()];
        this.panels = panels;
        // Everything the panel shows of a conversation is also kept, to show it again when reopened.
        this.post = (message) => {
            if (SHOWN.has(message.type)) this.transcript.push(message);
            post(message);
        };
        this.postRaw = post;
        this.cwd = cwd;
        this.conversations = conversations;
        this.conversation = null;
        this.transcript = [];
        this.restored = false;
        this.setting = setting;
        this.setSetting = setSetting;
        this.account = account;
        this.createModel = createModel;
        this.log = log;
        this.history = [];
        this.abort = null;
        this.pendingPermissions = new Map();
        this.nextPermission = 1;
        // Each turn's files as they were before it changed them: { turn, files: {path: content|null} }.
        this.checkpoints = [];
        this.turn = 0;
        this.changing = null;
        // Requests typed while the agent works, run in order once it is done.
        this.queue = [];
        this.nextQueued = 1;
    }

    /** `tool`, keeping each file it writes as it was before the turn first changed it. */
    _checkpointed(tool, cwd) {
        if (!FILE_EDIT_TOOLS.has(tool.name)) return tool;
        return {
            ...tool,
            run: async (args, context) => {
                const target = path.resolve(cwd() || '', args.file_path || '');
                if (this.changing && !(target in this.changing)) {
                    this.changing[target] = fs.existsSync(target) ? fs.readFileSync(target, 'utf8') : null;
                }
                return tool.run(args, context);
            },
        };
    }

    /** The agent's to-do list for a long task, shown pinned in the panel. */
    _todoTool() {
        return {
            name: 'update_todos',
            description: 'Set your to-do list for a task of several steps (the whole list each time), ticking off '
                + 'what is done. The user sees it pinned in the panel.',
            shape: {
                items: z.array(z.object({ text: z.string(), done: z.boolean().optional() })).describe('Every item, in order.'),
            },
            readOnly: true,
            run: async ({ items }) => {
                this.todos = items.map(({ text, done }) => ({ text, done: Boolean(done) }));
                this.post({ type: 'agent:todos', items: this.todos });
                const left = this.todos.filter((item) => !item.done).length;
                return [{ type: 'text', text: `To-do list updated: ${left} of ${this.todos.length} left.` }];
            },
        };
    }

    /** A picture of the view showing `filePath` as a data URL, or null. */
    async _viewPicture(run, filePath) {
        try {
            const result = await run('kigumi.captureScreenshot', { filePath });
            const data = fs.readFileSync(result.screenshotPath).toString('base64');
            return `data:image/png;base64,${data}`;
        } catch (_error) {
            return null;
        }
    }

    /** `text` with each @-mentioned project file attached (and @selection, what is selected in full). */
    async _withMentions(text) {
        const root = this.cwd();
        const attached = [];
        for (const [, written] of text.matchAll(/(?:^|\s)@([\w./-]+)/g)) {
            const mention = written.replace(/[.]+$/, ''); // the end of a sentence
            if (mention === 'selection') {
                const described = await this.panels.describe().catch(() => null);
                if (described) attached.push(`[What I have selected]\n${JSON.stringify(described, null, 1)}`);
                continue;
            }
            if (!root) continue;
            const file = path.resolve(root, mention);
            const inside = path.relative(root, file);
            if (inside.startsWith('..') || path.isAbsolute(inside) || !fs.existsSync(file) || !fs.statSync(file).isFile()) continue;
            const content = fs.readFileSync(file, 'utf8');
            const shown = content.length > MAX_MENTIONED_CHARS ? `${content.slice(0, MAX_MENTIONED_CHARS)}\n[…cut off]` : content;
            attached.push(`[The file ${inside}]\n\`\`\`\n${shown}\n\`\`\``);
        }
        return attached.length ? `${text}\n\n${attached.join('\n\n')}` : text;
    }

    /** Every project file, for the panel's @-mention list. */
    async _listFiles() {
        const lister = this.fileTools.find((tool) => tool.name === 'list_files');
        if (!lister) return [];
        try {
            const [listed] = await lister.run({});
            return listed.text.split('\n').filter((line) => line && !line.startsWith('('));
        } catch (_error) {
            return [];
        }
    }

    /** Put back the files the turns from `turn` on changed, as they were before it. */
    restore(turn) {
        const undone = this.checkpoints.filter((checkpoint) => checkpoint.turn >= turn).reverse();
        const files = new Set();
        for (const checkpoint of undone) {
            for (const [file, content] of Object.entries(checkpoint.files)) {
                if (content === null) fs.rmSync(file, { force: true });
                else fs.writeFileSync(file, content, 'utf8');
                files.add(file);
            }
        }
        this.checkpoints = this.checkpoints.filter((checkpoint) => checkpoint.turn < turn);
        this.post({ type: 'agent:restored', turn });
        this.post({ type: 'agent:notice', text: `Put back ${files.size} file${files.size === 1 ? '' : 's'} as `
            + 'they were before that request. The agent is told so with your next message.' });
        // The model still thinks its edits are there; say otherwise when the conversation carries on.
        this.history.push({ role: 'user', content: `[I undid your changes to ${[...files].map((file) => path.relative(this.cwd() || '', file)).join(', ')}: those files are back as they were before.]` },
            { role: 'assistant', content: 'Understood.' });
        this._saveConversation('');
    }

    /**
     * `tool`, and when it writes or edits a file a view shows, that view rebuilt with the build's
     * result: one step for the agent where it took three (edit, refresh, read the log).
     */
    _buildingAfterEdits(tool, { panels, run, cwd }) {
        if (!['write_file', 'edit_file'].includes(tool.name)) return tool;
        return {
            ...tool,
            run: async (args, context = {}) => {
                const target = path.resolve(cwd() || '', args.file_path || '');
                const shown = panels.list().some((panel) => panel.kind === 'viewer' && panel.filePath
                    && path.resolve(panel.filePath) === target);
                // The view before and after, for the panel only: the model isn't sent them.
                const before = shown ? await this._viewPicture(run, target) : null;
                const result = await tool.run(args, context);
                if (!shown) return result;
                const report = await run('kigumi.automationBuildReport', { filePath: target, reason: 'agent edit' })
                    .catch((error) => ({ ok: false, error: error.message, entries: [] }));
                const after = await this._viewPicture(run, target);
                if (before && after && context.toolCallId) {
                    this.postRaw({ type: 'agent:toolImages', id: context.toolCallId, before, after });
                }
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
            settings: Object.fromEntries(Object.keys(PANEL_SETTINGS).map((key) => [key, this.panelSetting(key)])),
        });
    }

    /** A setting the panel's menu sets, as it is or its default. Bypassing permissions was a switch once. */
    panelSetting(key) {
        const { fallback, valid } = PANEL_SETTINGS[key];
        const value = this.setting(key, undefined);
        if (valid(value)) return value;
        if (key === 'agent.permissionMode' && this.setting('agent.bypassPermissions', false) === true) return 'all';
        return fallback;
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
            if (!this.busy) this.restore(message.turn);
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
            this.setSetting('agent.model', findModel(message.id).id);
            this.postState();
        } else if (message.type === 'agent:setSetting' && message.key in PANEL_SETTINGS) {
            if (PANEL_SETTINGS[message.key].valid(message.value)) this.setSetting(message.key, message.value);
            this.postState();
        } else if (message.type === 'agent:listConversations') {
            this.postConversations();
        } else if (message.type === 'agent:openConversation' && typeof message.id === 'string') {
            if (!this.busy) this.openConversation(message.id);
        } else if (message.type === 'agent:deleteConversation' && typeof message.id === 'string') {
            this._project() && this.conversations.remove(this._project(), message.id);
            if (this.conversation && this.conversation.id === message.id) this.startConversation();
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
                .catch((error) => this.post({ type: 'agent:error', message: `Could not sign in: ${error.message}` }));
        } else if (message.type === 'agent:signOut' && this.account) {
            void this.account.signOut().then(() => this.postState());
        }
    }

    /** The project conversations are kept for, when there is somewhere to keep them. */
    _project() {
        return this.conversations ? this.cwd() : null;
    }

    startConversation() {
        this.todos = [];
        this.history = [];
        this.transcript = [];
        this.conversation = null;
        this.checkpoints = [];
        this.turn = 0;
    }

    openConversation(id) {
        const found = this._project() && this.conversations.load(this._project(), id);
        if (!found) return;
        this.conversation = found;
        this.history = found.history || [];
        this.transcript = found.transcript || [];
        this.checkpoints = found.checkpoints || [];
        this.turn = found.turn || this.checkpoints.reduce((last, checkpoint) => Math.max(last, checkpoint.turn), 0);
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
            this.conversation = { id: crypto.randomUUID(), title: titleOf(firstText), createdAt: now };
        }
        Object.assign(this.conversation, { model: this.model.id, updatedAt: now, history: this.history,
            transcript: this.transcript, checkpoints: this.checkpoints, turn: this.turn });
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

    _askPermission(toolName, input) {
        if (this.panelSetting('agent.planMode')) {
            return Promise.reject(new Error('Plan mode is on, so nothing that changes anything runs. Propose the change; '
                + 'the user will turn plan mode off and ask you to go ahead.'));
        }
        const mode = this.panelSetting('agent.permissionMode');
        if (mode === 'all' || (mode === 'edits' && FILE_EDIT_TOOLS.has(toolName))
            || this.panelSetting('agent.alwaysAllow').includes(toolName)) {
            return Promise.resolve(true);
        }
        const requestId = this.nextPermission++;
        return new Promise((resolve) => {
            this.pendingPermissions.set(requestId, { toolName, answer: resolve });
            this.post({ type: 'agent:permission', requestId, toolName, input });
        });
    }

    /** What a request sends: the text with mentions attached and what is in view, then any images. */
    async _promptContent(text, images) {
        const full = withContext(await this._withMentions(text), await this.panels.describe().catch(() => null));
        if (!images.length) return full;
        if (!this.model.images) {
            return `${full}\n\n[${images.length} image${images.length === 1 ? '' : 's'} attached, which this model can't see.]`;
        }
        return [{ type: 'text', text: full },
            ...images.map((image) => ({ type: 'image', image: image.data, mediaType: image.mediaType || 'image/png' }))];
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

    async prompt(text, images = []) {
        if (this.busy) {
            this.ask(text, images);
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
        this.transcript.push({ type: 'agent:userMessage', text, images: images.length });
        this.turn += 1;
        const turn = this.turn;
        this.changing = {};
        this.post({ type: 'agent:busy', busy: true });
        try {
            const { history, costUsd } = await runTurn({
                model: await this.createModel(route, { fetch: route.via === 'backend' ? this.account.fetchWithToken : undefined }),
                images: this.model.images,
                cacheMarks: Boolean(this.model.cacheMarks),
                contextWindow: this.model.contextWindow,
                tools: this.tools,
                system: this.panelSetting('agent.planMode') ? `${SYSTEM_PROMPT}\n\n${PLAN_MODE_NOTE}` : SYSTEM_PROMPT,
                history: this.history,
                prompt: await this._promptContent(text, images),
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
            const changed = this.changing;
            this.changing = null;
            if (Object.keys(changed).length) {
                this.checkpoints.push({ turn, files: changed });
                this.post({ type: 'agent:checkpoint', turn,
                    files: Object.keys(changed).map((file) => path.relative(this.cwd() || '', file)) });
            }
            this.abort = null;
            this.post({ type: 'agent:busy', busy: false });
            if (route.via === 'backend') {
                void this.account.refreshBalance().catch(() => {});
            }
            this._saveConversation(text);
            const next = this.queue.shift();
            if (next) {
                this.postRaw({ type: 'agent:dequeued', id: next.id });
                this.postRaw({ type: 'agent:userMessage', text: next.text, images: next.images.length });
                void this.prompt(next.text, next.images);
            }
        }
    }
}

module.exports = { AgentSession, SYSTEM_PROMPT, RETRY_PROMPT, describeFailure, withContext, describeBuild };
