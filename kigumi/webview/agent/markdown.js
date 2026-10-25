// A small Markdown renderer for the agent's replies: headings, paragraphs, lists, quotes, fenced
// code (with a copy button), and inline code, bold, italic and links. Everything is built as DOM
// nodes holding text, so nothing in a reply is ever read as HTML. Re-rendered as a reply streams.
import { t } from './i18n.js';

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\([^)\s]+\))/g;

function inline(text, into) {
    let last = 0;
    for (const match of text.matchAll(INLINE)) {
        if (match.index > last) into.appendChild(document.createTextNode(text.slice(last, match.index)));
        const token = match[0];
        let node;
        if (token.startsWith('`')) {
            node = document.createElement('code');
            node.textContent = token.slice(1, -1);
        } else if (token.startsWith('**') || token.startsWith('__')) {
            node = document.createElement('strong');
            inline(token.slice(2, -2), node);
        } else if (token.startsWith('*')) {
            node = document.createElement('em');
            inline(token.slice(1, -1), node);
        } else {
            const [, label, href] = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token);
            // Links don't navigate the panel; the address shows on hover.
            node = document.createElement('span');
            node.className = 'md-link';
            node.title = href;
            inline(label, node);
        }
        into.appendChild(node);
        last = match.index + token.length;
    }
    if (last < text.length) into.appendChild(document.createTextNode(text.slice(last)));
    return into;
}

function codeBlock(lines, language) {
    const wrap = document.createElement('div');
    wrap.className = 'md-code';
    const copy = document.createElement('button');
    copy.type = 'button';
    copy.className = 'md-copy';
    copy.textContent = t('agent.copy');
    const pre = document.createElement('pre');
    const code = document.createElement('code');
    code.textContent = lines.join('\n');
    if (language) code.dataset.language = language;
    copy.addEventListener('click', () => {
        navigator.clipboard.writeText(code.textContent).then(() => {
            copy.textContent = t('agent.copied');
            setTimeout(() => { copy.textContent = t('agent.copy'); }, 1200);
        }, () => {});
    });
    pre.appendChild(code);
    wrap.append(copy, pre);
    return wrap;
}

/** `text` as a fragment of rendered Markdown. */
export function render(text) {
    const out = document.createDocumentFragment();
    const lines = String(text).replace(/\r\n/g, '\n').split('\n');
    let paragraph = [];
    let list = null;

    const endParagraph = () => {
        if (!paragraph.length) return;
        out.appendChild(inline(paragraph.join(' '), document.createElement('p')));
        paragraph = [];
    };
    const endList = () => { list = null; };

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const fence = /^\s*```\s*([\w+-]*)\s*$/.exec(line);
        if (fence) {
            endParagraph();
            endList();
            const body = [];
            while (i + 1 < lines.length && !/^\s*```\s*$/.test(lines[i + 1])) body.push(lines[++i]);
            i += 1; // the closing fence, if it has come yet
            out.appendChild(codeBlock(body, fence[1]));
            continue;
        }
        const heading = /^(#{1,4})\s+(.*)$/.exec(line);
        if (heading) {
            endParagraph();
            endList();
            out.appendChild(inline(heading[2], document.createElement(`h${Math.min(heading[1].length + 2, 6)}`)));
            continue;
        }
        const item = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/.exec(line);
        if (item) {
            endParagraph();
            const tag = item[2] ? 'ol' : 'ul';
            if (!list || list.tagName.toLowerCase() !== tag) {
                list = document.createElement(tag);
                out.appendChild(list);
            }
            list.appendChild(inline(item[3], document.createElement('li')));
            continue;
        }
        const quote = /^>\s?(.*)$/.exec(line);
        if (quote) {
            endParagraph();
            endList();
            out.appendChild(inline(quote[1], document.createElement('blockquote')));
            continue;
        }
        if (!line.trim()) {
            endParagraph();
            endList();
            continue;
        }
        endList();
        paragraph.push(line.trim());
    }
    endParagraph();
    return out;
}

