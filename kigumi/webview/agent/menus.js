// The panel's two menus: settings (how freely the agent changes things, tools always allowed,
// the longest step, opening at startup) and past conversations; and the banner saying when it isn't asking.
import { t } from './i18n.js';

const MODE_BANNERS = { auto: 'agent.banner.auto' };

function ago(time) {
    const minutes = Math.round((Date.now() - new Date(time).getTime()) / 60000);
    if (minutes < 1) return t('agent.ago.now');
    if (minutes < 60) return t('agent.ago.minutes', { minutes });
    if (minutes < 60 * 24) return t('agent.ago.hours', { hours: Math.round(minutes / 60) });
    return new Date(time).toLocaleDateString();
}

export class Menus {
    constructor({ settingsButton, settingsMenu, historyButton, historyMenu, historyList, alwaysAllowed, startupToggle, outputLimit, banner }, { post }) {
        Object.assign(this, { settingsButton, settingsMenu, historyButton, historyMenu, historyList, alwaysAllowed, startupToggle, outputLimit, banner, post });
        this.modeRadios = [...settingsMenu.querySelectorAll('input[name="permission-mode"]')];
        this.allowedTools = [];
        settingsButton.addEventListener('click', () => {
            historyMenu.hidden = true;
            settingsMenu.hidden = !settingsMenu.hidden;
            settingsButton.setAttribute('aria-expanded', String(!settingsMenu.hidden));
        });
        historyButton.addEventListener('click', () => {
            historyMenu.hidden = !historyMenu.hidden;
            settingsMenu.hidden = true;
            if (!historyMenu.hidden) post({ type: 'agent:listConversations' });
        });
        for (const radio of this.modeRadios) {
            radio.addEventListener('change', () => post({ type: 'agent:setSetting', key: 'agent.permissionMode', value: radio.value }));
        }
        startupToggle.addEventListener('change', () => post({ type: 'agent:setSetting', key: 'agent.showOnStartup', value: startupToggle.checked }));
        outputLimit.addEventListener('change', () => post({ type: 'agent:setSetting', key: 'agent.maxOutputTokens', value: Number(outputLimit.value) }));
    }

    closeHistory() {
        this.historyMenu.hidden = true;
    }

    showSettings(settings) {
        const mode = settings['agent.permissionMode'] || 'ask';
        for (const radio of this.modeRadios) radio.checked = radio.value === mode;
        this.startupToggle.checked = settings['agent.showOnStartup'] !== false;
        this.outputLimit.value = String(settings['agent.maxOutputTokens'] || 8000);
        const planning = settings['agent.planMode'] === true;
        this.banner.hidden = !planning && mode === 'ask';
        this.banner.textContent = planning ? t('agent.banner.plan') : MODE_BANNERS[mode] ? t(MODE_BANNERS[mode]) : '';
        this.banner.classList.toggle('is-plan', planning);
        // Tools allowed for good from a permission card, each with a way to take it back.
        this.allowedTools = settings['agent.alwaysAllow'] || [];
        const hint = this.allowedTools.length
            ? [Object.assign(document.createElement('div'), { className: 'settings-hint', textContent: t('agent.settings.alwaysAllowed') })] : [];
        this.alwaysAllowed.replaceChildren(...hint, ...this.allowedTools.map((name) => {
            const chip = Object.assign(document.createElement('span'), { className: 'allowed-tool', textContent: name });
            const remove = Object.assign(document.createElement('button'), { type: 'button', textContent: '×',
                title: t('agent.settings.askAgain', { tool: name }) });
            remove.addEventListener('click', () => this.post({ type: 'agent:setSetting', key: 'agent.alwaysAllow',
                value: this.allowedTools.filter((tool) => tool !== name) }));
            chip.appendChild(remove);
            return chip;
        }));
    }

    showConversations({ items = [], current }) {
        if (!items.length) {
            this.historyList.replaceChildren(Object.assign(document.createElement('div'), { className: 'history-empty', textContent: t('agent.history.empty') }));
            return;
        }
        this.historyList.replaceChildren(...items.map((item) => {
            const row = Object.assign(document.createElement('div'), { className: 'history-item' + (item.id === current ? ' is-current' : '') });
            const open = Object.assign(document.createElement('button'), { type: 'button', className: 'history-open' });
            open.append(Object.assign(document.createElement('span'), { className: 'history-title', textContent: item.title || t('agent.history.untitled') }),
                Object.assign(document.createElement('span'), { className: 'history-when', textContent: ago(item.updatedAt) }));
            open.addEventListener('click', () => {
                this.post({ type: 'agent:openConversation', id: item.id });
                this.closeHistory();
            });
            const remove = Object.assign(document.createElement('button'), { type: 'button', className: 'icon-btn history-delete', title: t('agent.history.delete') });
            remove.appendChild(Object.assign(document.createElement('span'), { className: 'codicon codicon-trash' }));
            remove.addEventListener('click', () => this.post({ type: 'agent:deleteConversation', id: item.id }));
            row.append(open, remove);
            return row;
        }));
    }
}
