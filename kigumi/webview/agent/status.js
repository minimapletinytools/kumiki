// What the panel says about the session besides the conversation: what the agent is doing now,
// the models to choose from, where requests go (a key, or the Kigumi account), how full the
// conversation is, and the agent's to-do list.
import { t } from './i18n.js';

export class Status {
    constructor({ activity, activityLabel, modelSelect, routeNote, contextMeter, todos }, { post }) {
        Object.assign(this, { activity, activityLabel, modelSelect, routeNote, contextMeter, todos, post });
        modelSelect.addEventListener('change', () => post({ type: 'agent:setModel', id: modelSelect.value }));
    }

    setActivity(label) {
        this.activityLabel.textContent = label;
    }

    setBusy(busy) {
        this.activity.hidden = !busy;
        if (busy) this.setActivity(t('agent.activity.thinking'));
    }

    showModels(models, chosen) {
        this.modelSelect.replaceChildren(...models.map(({ id, label }) => Object.assign(document.createElement('option'), { value: id, textContent: label })));
        this.modelSelect.value = chosen;
    }

    linkButton(label, onClick) {
        const button = Object.assign(document.createElement('button'), { className: 'link-btn', textContent: label });
        button.addEventListener('click', onClick);
        return button;
    }

    // Where requests go: the user's own key, or the Kigumi account (signed in, or a way to sign in).
    showRoute(via, account) {
        const parts = [];
        else if (via === 'openrouter') parts.push(t('agent.route.openrouter'));
        else if (account.signedIn) {
            const left = typeof account.balanceUsd === 'number' ? ` · ${t('agent.route.left', { usd: account.balanceUsd.toFixed(2) })}` : '';
            parts.push(`${account.email || t('agent.route.signedIn')}${left} · `,
                this.linkButton(t('agent.route.signOut'), () => this.post({ type: 'agent:signOut' })));
        } else if (account.configured) {
            parts.push(`${t('agent.route.signIn')} `,
                this.linkButton('GitHub', () => this.post({ type: 'agent:signIn', provider: 'github' })),
                ' · ',
                this.linkButton('Google', () => this.post({ type: 'agent:signIn', provider: 'google' })));
        } else {
            parts.push(t('agent.route.setKey'));
        }
        this.routeNote.replaceChildren(...parts);
    }

    /** How full the conversation is, from the last step's input tokens. */
    showContext({ tokens, window: size }) {
        const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
        this.contextMeter.textContent = size ? t('agent.context.of', { tokens: short(tokens), window: short(size) }) : t('agent.context', { tokens: short(tokens) });
        this.contextMeter.title = t('agent.context.title');
        this.contextMeter.classList.toggle('is-high', Boolean(size) && tokens > size * 0.5);
    }

    clearContext() {
        this.contextMeter.textContent = '';
    }

    /** The agent's to-do list, pinned above the box. */
    showTodos(items) {
        this.todos.hidden = !items.length;
        if (!items.length) return this.todos.replaceChildren();
        const left = items.filter((item) => !item.done).length;
        const details = document.createElement('details');
        details.open = left > 0;
        details.appendChild(Object.assign(document.createElement('summary'), {
            textContent: left ? t('agent.todos.left', { left, total: items.length }) : t('agent.todos.done', { total: items.length }),
        }));
        const list = document.createElement('ul');
        for (const item of items) list.appendChild(Object.assign(document.createElement('li'), { className: item.done ? 'is-done' : '', textContent: item.text }));
        details.appendChild(list);
        this.todos.replaceChildren(details);
    }
}
