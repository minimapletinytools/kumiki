// The box requests are written in: sending (or queueing, while the agent works), images pasted or
// dropped in, @-mentions picked from a list, plan mode, and the keys: Enter sends, Escape stops,
// Up in an empty box brings back the last request.
import { t } from './i18n.js';

export class Composer {
    /**
     * @param {object} elements  input, sendButton, attachments, mentions, planToggle
     * @param {{post, isBusy: () => boolean, onSent: (text: string, imageUrls: string[]) => void}} deps
     */
    constructor({ input, sendButton, attachments, mentions, planToggle }, { post, isBusy, onSent }) {
        Object.assign(this, { input, sendButton, attachmentsEl: attachments, mentionsEl: mentions, planToggle, post, isBusy, onSent });
        this.attachments = [];
        this.lastSent = '';
        this.projectFiles = null;
        this.mentionChoices = [];
        this.mentionIndex = 0;
        this.bind();
    }

    bind() {
        const { input } = this;
        input.addEventListener('keydown', (event) => this.onKey(event));
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = `${Math.min(input.scrollHeight, 200)}px`;
            this.mentionIndex = 0;
            this.showMentions();
        });
        input.addEventListener('blur', () => setTimeout(() => this.hideMentions(), 100));
        input.addEventListener('paste', (event) => {
            const files = [...(event.clipboardData ? event.clipboardData.files : [])];
            if (files.some((file) => file.type.startsWith('image/'))) {
                event.preventDefault();
                this.attach(files);
            }
        });
        const box = input.closest('.input-box');
        box.addEventListener('dragover', (event) => event.preventDefault());
        box.addEventListener('drop', (event) => {
            event.preventDefault();
            this.attach([...event.dataTransfer.files]);
        });
        this.sendButton.addEventListener('click', () => (this.isBusy() ? this.post({ type: 'agent:stop' }) : this.send()));
        this.planToggle.addEventListener('click', () => this.post({
            type: 'agent:setSetting', key: 'agent.planMode', value: this.planToggle.getAttribute('aria-pressed') !== 'true',
        }));
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.isBusy() && event.target !== input) this.post({ type: 'agent:stop' });
        });
    }

    /** Send what is in the box (or `text`, from a suggestion); while the agent works it waits its turn. */
    send(text) {
        const prompt = (text !== undefined ? text : this.input.value).trim();
        const images = text !== undefined ? [] : this.attachments.splice(0);
        if (!prompt && !images.length) return;
        if (!this.isBusy()) this.onSent(prompt, images.map((image) => image.url));
        this.lastSent = prompt;
        this.input.value = '';
        this.input.style.height = 'auto';
        this.showAttachments();
        this.hideMentions();
        this.post({ type: 'agent:prompt', text: prompt, images: images.map(({ mediaType, data }) => ({ mediaType, data })) });
    }

    onKey(event) {
        if (!this.mentionsEl.hidden && this.mentionChoices.length) {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                const step = event.key === 'ArrowDown' ? 1 : this.mentionChoices.length - 1;
                this.mentionIndex = (this.mentionIndex + step) % this.mentionChoices.length;
                this.showMentions();
                return;
            }
            if (event.key === 'Enter' || event.key === 'Tab') {
                event.preventDefault();
                this.chooseMention(this.mentionChoices[this.mentionIndex]);
                return;
            }
            if (event.key === 'Escape') {
                event.preventDefault();
                this.hideMentions();
                return;
            }
        }
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.send();
        } else if (event.key === 'Escape' && this.isBusy()) {
            event.preventDefault();
            this.post({ type: 'agent:stop' });
        } else if (event.key === 'ArrowUp' && !this.input.value && this.lastSent) {
            event.preventDefault();
            this.input.value = this.lastSent;
        }
    }

    // Images pasted or dropped into the box go with the next request.
    attach(files) {
        for (const file of files) {
            if (!file.type.startsWith('image/') || this.attachments.length >= 4) continue;
            const reader = new FileReader();
            reader.onload = () => {
                const url = String(reader.result);
                this.attachments.push({ url, mediaType: file.type, data: url.slice(url.indexOf(',') + 1) });
                this.showAttachments();
            };
            reader.readAsDataURL(file);
        }
    }

    showAttachments() {
        this.attachmentsEl.hidden = !this.attachments.length;
        this.attachmentsEl.replaceChildren(...this.attachments.map((image, index) => {
            const chip = Object.assign(document.createElement('div'), { className: 'attachment' });
            const remove = Object.assign(document.createElement('button'), { type: 'button', textContent: '×', title: t('agent.remove') });
            remove.addEventListener('click', () => {
                this.attachments.splice(index, 1);
                this.showAttachments();
            });
            chip.append(Object.assign(document.createElement('img'), { src: image.url, alt: '' }), remove);
            return chip;
        }));
    }

    // @-mentions: a project file, or "selection", picked from a list as you type.
    mentionAtCaret() {
        const before = this.input.value.slice(0, this.input.selectionStart);
        const match = /(?:^|\s)@([\w./-]*)$/.exec(before);
        return match ? { query: match[1], start: this.input.selectionStart - match[1].length } : null;
    }

    /** The project's files, for the list (agent:files). */
    setFiles(files) {
        this.projectFiles = files;
        this.showMentions();
    }

    /** Forget the files listed, so the next @ asks again (a new conversation, maybe a new project). */
    forgetFiles() {
        this.projectFiles = null;
    }

    hideMentions() {
        this.mentionsEl.hidden = true;
        this.mentionChoices = [];
    }

    showMentions() {
        const at = this.mentionAtCaret();
        if (!at) return this.hideMentions();
        if (this.projectFiles === null) {
            this.projectFiles = [];
            this.post({ type: 'agent:listFiles' });
        }
        const query = at.query.toLowerCase();
        this.mentionChoices = ['selection', ...this.projectFiles]
            .map((name) => ({ name, at: name.toLowerCase().indexOf(query) }))
            .filter((choice) => choice.at >= 0)
            .sort((a, b) => (a.at === b.at ? a.name.length - b.name.length : a.at - b.at))
            .slice(0, 8)
            .map((choice) => choice.name);
        this.mentionIndex = Math.min(this.mentionIndex, Math.max(this.mentionChoices.length - 1, 0));
        this.mentionsEl.hidden = !this.mentionChoices.length;
        this.mentionsEl.replaceChildren(...this.mentionChoices.map((name, index) => {
            const option = Object.assign(document.createElement('div'), {
                className: 'mention' + (index === this.mentionIndex ? ' is-chosen' : ''),
                textContent: name === 'selection' ? t('agent.mention.selection') : `@${name}`,
            });
            option.addEventListener('mousedown', (event) => {
                event.preventDefault();
                this.chooseMention(name);
            });
            return option;
        }));
    }

    chooseMention(name) {
        const at = this.mentionAtCaret();
        if (!at) return;
        const caret = this.input.selectionStart;
        this.input.value = `${this.input.value.slice(0, at.start)}${name} ${this.input.value.slice(caret)}`;
        this.input.selectionStart = this.input.selectionEnd = at.start + name.length + 1;
        this.hideMentions();
        this.input.focus();
    }

    setBusy(busy) {
        this.sendButton.title = busy ? t('agent.stop') : t('agent.send');
        this.sendButton.firstElementChild.className = `codicon codicon-${busy ? 'debug-stop' : 'send'}`;
    }

    setPlanMode(planning) {
        this.planToggle.setAttribute('aria-pressed', String(planning));
        this.planToggle.classList.toggle('is-on', planning);
    }
}
