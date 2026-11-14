// The panel's settings row (Agent Settings and MCP: the MCP server, the built-in agent on or off,
// how freely it changes things, tools always allowed, the longest step, opening at startup, the key,
// how long past conversations are kept), past conversations, the banner saying plan mode is on, and
// the permission menu under the box.
import { t } from './i18n.js';

function ago(time) {
    const minutes = Math.round((Date.now() - new Date(time).getTime()) / 60000);
    if (minutes < 1) return t('agent.ago.now');
    if (minutes < 60) return t('agent.ago.minutes', { minutes });
    if (minutes < 60 * 24) return t('agent.ago.hours', { hours: Math.round(minutes / 60) });
    return new Date(time).toLocaleDateString();
}

function size(bytes) {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const el = (tag, className, textContent) => Object.assign(document.createElement(tag), className ? { className } : {},
    textContent !== undefined ? { textContent } : {});

export class Menus {
    /** `saved` and `save` keep whether the settings row is open, across reloads. */
    constructor(elements, { post, saved = {}, save = () => {} }) {
        Object.assign(this, elements, { post, save });
        const { settingsToggle, settingsCollapse, historyButton, historyMenu, startupToggle, outputLimit, retention, keyInput,
            mcpToggle, agentToggle, clearButton, permissionSelect } = elements;
        this.modeRadios = [...this.settingsMenu.querySelectorAll('input[name="permission-mode"]')];
        this.allowedTools = [];
        this.agentOn = true;
        this.rowOpen = saved.settingsOpen === true;
        const setOpen = (open) => {
            this.rowOpen = open;
            this.save({ settingsOpen: open });
            this.showRow();
        };
        settingsToggle.addEventListener('click', () => setOpen(!this.rowOpen));
        // At the bottom too: once the settings are open, their top can be a long way up.
        settingsCollapse.addEventListener('click', () => {
            setOpen(false);
            settingsToggle.scrollIntoView({ block: 'nearest' });
        });
        historyButton.addEventListener('click', () => {
            historyMenu.hidden = !historyMenu.hidden;
            if (!historyMenu.hidden) post({ type: 'agent:listConversations' });
        });
        const setSetting = (key, value) => post({ type: 'agent:setSetting', key, value });
        for (const radio of this.modeRadios) radio.addEventListener('change', () => setSetting('agent.permissionMode', radio.value));
        permissionSelect.addEventListener('change', () => setSetting('agent.permissionMode', permissionSelect.value));
        startupToggle.addEventListener('change', () => setSetting('agent.showOnStartup', startupToggle.checked));
        outputLimit.addEventListener('change', () => setSetting('agent.maxOutputTokens', Number(outputLimit.value)));
        retention.addEventListener('change', () => setSetting('agent.conversationRetentionDays', Number(retention.value)));
        mcpToggle.addEventListener('change', () => setSetting('mcp.enabled', mcpToggle.checked));
        agentToggle.addEventListener('change', () => setSetting('agent.enabled', agentToggle.checked));
        clearButton.addEventListener('click', () => {
            if (window.confirm(t('agent.settings.clearConfirm'))) post({ type: 'agent:clearConversations' });
        });
        // A key typed here is sent once, on Enter or leaving the box, and the box empties again.
        const sendKey = () => {
            if (!keyInput.value.trim()) return;
            setSetting('agent.openrouterApiKey', keyInput.value.trim());
            keyInput.value = '';
        };
        keyInput.addEventListener('change', sendKey);
        keyInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') sendKey(); });
        this.showRow();
    }

    /** Open or close the settings row; with the agent off it stays open, being all there is. */
    showRow() {
        const open = this.rowOpen || !this.agentOn;
        this.settingsMenu.hidden = !open;
        // What to do with a copied setup was for then: closing the settings puts it away.
        if (!open) for (const next of this.mcpDetails.querySelectorAll('.mcp-next')) next.hidden = true;
        // With the agent off there is nothing to collapse to.
        this.settingsCollapse.hidden = !this.agentOn;
        this.settingsToggle.setAttribute('aria-expanded', String(open));
        const chevron = this.settingsToggle.querySelector('.codicon');
        chevron.classList.toggle('codicon-chevron-down', open);
        chevron.classList.toggle('codicon-chevron-right', !open);
    }

    closeHistory() {
        this.historyMenu.hidden = true;
    }

    showSettings(settings, conversationBytes) {
        this.agentOn = settings['agent.enabled'] === true;
        document.body.classList.toggle('agent-off', !this.agentOn);
        this.agentToggle.checked = this.agentOn;
        this.mcpToggle.checked = settings['mcp.enabled'] === true;
        this.agentSettings.hidden = !this.agentOn;
        if (!this.agentOn) this.closeHistory();
        this.showRow();
        const mode = settings['agent.permissionMode'] || 'auto';
        for (const radio of this.modeRadios) radio.checked = radio.value === mode;
        this.permissionSelect.value = mode;
        this.startupToggle.checked = settings['agent.showOnStartup'] !== false;
        this.outputLimit.value = String(settings['agent.maxOutputTokens'] || 16000);
        this.retention.value = String(settings['agent.conversationRetentionDays'] ?? 30);
        this.usage.textContent = typeof conversationBytes === 'number' && conversationBytes > 0
            ? t('agent.settings.usage', { size: size(conversationBytes) }) : '';
        this.clearButton.hidden = !(conversationBytes > 0);
        const hasKey = settings['agent.openrouterApiKey'] === true;
        this.keyNote.replaceChildren(document.createTextNode(hasKey ? t('agent.settings.openrouterKey.saved') : t('agent.settings.openrouterKey.none')));
        if (hasKey) {
            const clear = el('button', 'link-btn', t('agent.settings.openrouterKey.clear'));
            clear.addEventListener('click', () => this.post({ type: 'agent:setSetting', key: 'agent.openrouterApiKey', value: '' }));
            this.keyNote.append(' ', clear);
        }
        // Whether it asks is shown under the box; plan mode, which refuses edits, also up here.
        const planning = settings['agent.planMode'] === true;
        this.banner.hidden = !this.agentOn || !planning;
        this.banner.textContent = planning ? t('agent.banner.plan') : '';
        this.banner.classList.toggle('is-plan', planning);
        // Tools allowed for good from a permission card, each with a way to take it back.
        this.allowedTools = settings['agent.alwaysAllow'] || [];
        const hint = this.allowedTools.length ? [el('div', 'settings-hint', t('agent.settings.alwaysAllowed'))] : [];
        this.alwaysAllowed.replaceChildren(...hint, ...this.allowedTools.map((name) => {
            const chip = el('span', 'allowed-tool', name);
            const remove = Object.assign(el('button', '', '×'), { type: 'button', title: t('agent.settings.askAgain', { tool: name }) });
            remove.addEventListener('click', () => this.post({ type: 'agent:setSetting', key: 'agent.alwaysAllow',
                value: this.allowedTools.filter((tool) => tool !== name) }));
            chip.appendChild(remove);
            return chip;
        }));
    }

    /** The MCP server, where the host runs one: whether it serves, the setups to copy, who is connected. */
    showMcp(state, { signedIn = true } = {}) {
        this.mcpSettings.hidden = !state;
        if (!state) return;
        this.mcpDetails.hidden = !state.enabled;
        if (!state.enabled) return this.mcpDetails.replaceChildren();
        if (!signedIn && document.body.classList.contains('host-web')) {
            return this.mcpDetails.replaceChildren(el('div', 'settings-hint-block', t('agent.mcp.signIn')));
        }
        if (!state.running) {
            return this.mcpDetails.replaceChildren(el('div', 'settings-hint-block', state.error || t('agent.mcp.starting')));
        }
        const clients = state.clients || [];
        const count = clients.length === 0 ? t('agent.mcp.agents.none')
            : clients.length === 1 ? t('agent.mcp.agents.one') : t('agent.mcp.agents.many', { count: clients.length });
        // What to do with what was just copied, under the buttons until another is copied.
        const next = el('div', 'settings-hint-block mcp-next');
        next.hidden = true;
        const copy = (clientId) => {
            this.post({ type: 'agent:copyMcpSetup', client: clientId });
            next.textContent = t(`agent.mcp.next.${clientId}`);
            next.hidden = false;
        };
        const all = Object.assign(el('button', 'mcp-setup-all', t('agent.mcp.copyAll')), { type: 'button' });
        all.addEventListener('click', () => copy('all'));
        const setups = el('div', 'mcp-setups');
        setups.append(...(state.setups || []).map((setup) => {
            const button = Object.assign(el('button', 'mcp-setup', setup.label), { type: 'button' });
            button.dataset.client = setup.id;
            button.addEventListener('click', () => copy(setup.id));
            return button;
        }));
        const agents = el('div', 'settings-hint-block', count);
        agents.title = clients.map((client) => client.name || client.id || '').join(', ');
        const serving = el('div', 'settings-hint-block mcp-url', t('agent.mcp.serving'));
        serving.title = state.url;
        this.mcpDetails.replaceChildren(serving, all, el('div', 'settings-hint-block', t('agent.mcp.copyFor')), setups, next, agents);
    }

    showConversations({ items = [], current }) {
        if (!items.length) {
            this.historyList.replaceChildren(el('div', 'history-empty', t('agent.history.empty')));
            return;
        }
        this.historyList.replaceChildren(...items.map((item) => {
            const row = el('div', 'history-item' + (item.id === current ? ' is-current' : ''));
            const open = Object.assign(el('button', 'history-open'), { type: 'button' });
            open.append(el('span', 'history-title', item.title || t('agent.history.untitled')), el('span', 'history-when', ago(item.updatedAt)));
            open.addEventListener('click', () => {
                this.post({ type: 'agent:openConversation', id: item.id });
                this.closeHistory();
            });
            const remove = Object.assign(el('button', 'icon-btn history-delete'), { type: 'button', title: t('agent.history.delete') });
            remove.appendChild(el('span', 'codicon codicon-trash'));
            remove.addEventListener('click', () => this.post({ type: 'agent:deleteConversation', id: item.id }));
            row.append(open, remove);
            return row;
        }));
    }
}
