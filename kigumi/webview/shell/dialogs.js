// The shell's two dialogs, the same in every layout: the quick pick (connection.pick and
// connection.ask) and the yes/no confirm (connection.confirm). Their markup is in shell.html.

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

/** Wire the dialogs to the core; returns what shows them. */
export function setupDialogs(core) {
    // ---------------------------------------------------------------------
    // Confirm
    // ---------------------------------------------------------------------

    let confirmRequest = null;

    function closeConfirm(ok) {
        if (confirmRequest === null) return;
        core.send({ type: 'confirm:result', requestId: confirmRequest, ok });
        confirmRequest = null;
        $('confirm').hidden = true;
    }

    function showConfirm({ requestId, message, detail, warning, action, cancel }) {
        closeConfirm(false);
        confirmRequest = requestId;
        $('confirm-message').textContent = message || '';
        $('confirm-detail').textContent = detail || '';
        $('confirm-detail').hidden = !detail;
        $('confirm-warning').textContent = warning || '';
        $('confirm-warning').hidden = !warning;
        $('confirm-ok').textContent = action || 'OK';
        $('confirm-cancel').textContent = cancel || 'Cancel';
        $('confirm').hidden = false;
        $('confirm-ok').focus();
    }

    $('confirm-ok').addEventListener('click', () => closeConfirm(true));
    $('confirm-cancel').addEventListener('click', () => closeConfirm(false));
    $('confirm').addEventListener('mousedown', (event) => {
        if (event.target === $('confirm')) closeConfirm(false);
    });
    $('confirm').addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            closeConfirm(false);
        }
    });

    // ---------------------------------------------------------------------
    // Quick pick
    // ---------------------------------------------------------------------

    // `input`: a text box (connection.ask) rather than a list to choose from.
    const quickpick = { requestId: null, items: [], visible: [], selected: 0, input: false, prompt: '' };
    const QUICKPICK_SHOWN = 300;

    function closeQuickPick(index, text) {
        if (quickpick.requestId === null) return;
        core.send({ type: 'quickpick:result', requestId: quickpick.requestId, index, ...(typeof text === 'string' ? { text } : {}) });
        quickpick.requestId = null;
        $('quickpick').hidden = true;
    }

    function renderQuickPick() {
        if (quickpick.input) {
            quickpick.visible = [];
            $('quickpick-list').replaceChildren(el('div', 'empty', quickpick.prompt));
            return;
        }
        const needle = $('quickpick-filter').value.trim().toLowerCase();
        quickpick.visible = [];
        let pendingSeparator = null;
        // Drawn up to a limit: a workspace's files can number in the thousands.
        let matched = 0;
        quickpick.items.forEach((item, index) => {
            if (item.separator) {
                pendingSeparator = item;
                return;
            }
            const text = `${item.label} ${item.description || ''} ${item.detail || ''}`.toLowerCase();
            if (needle && !text.includes(needle)) return;
            matched += 1;
            if (matched > QUICKPICK_SHOWN) return;
            if (pendingSeparator) {
                quickpick.visible.push({ separator: pendingSeparator });
                pendingSeparator = null;
            }
            quickpick.visible.push({ item, index });
        });
        const choices = quickpick.visible.filter((row) => !row.separator);
        quickpick.selected = Math.max(0, Math.min(quickpick.selected, choices.length - 1));

        let choice = 0;
        const list = $('quickpick-list');
        list.replaceChildren(...quickpick.visible.map((row) => {
            if (row.separator) return el('div', 'separator', row.separator.label);
            const current = choice;
            choice += 1;
            const element = el('div', `item${current === quickpick.selected ? ' is-selected' : ''}`);
            element.setAttribute('role', 'option');
            element.setAttribute('aria-selected', current === quickpick.selected ? 'true' : 'false');
            element.append(el('span', 'item-label', row.item.label), el('span', 'item-description', row.item.description || ''));
            if (row.item.detail) element.append(el('span', 'item-detail', row.item.detail));
            element.addEventListener('click', () => closeQuickPick(row.index));
            return element;
        }));
        if (choices.length === 0) list.append(el('div', 'empty', 'No matching items'));
        if (matched > QUICKPICK_SHOWN) list.append(el('div', 'empty', `${matched - QUICKPICK_SHOWN} more: type to narrow`));
        const selected = list.querySelector('.is-selected');
        if (selected) selected.scrollIntoView({ block: 'nearest' });
    }

    function showQuickPick({ requestId, placeholder, items, input, prompt, value }) {
        if (quickpick.requestId !== null) closeQuickPick(null);
        Object.assign(quickpick, { requestId, items: items || [], selected: 0, input: Boolean(input), prompt: prompt || '' });
        const filter = $('quickpick-filter');
        filter.placeholder = input ? '' : placeholder || '';
        filter.value = input ? value || '' : '';
        $('quickpick').hidden = false;
        renderQuickPick();
        filter.focus();
        if (input) {
            // The name selected without its extension, ready to type over.
            const dot = filter.value.lastIndexOf('.');
            filter.setSelectionRange(0, dot > 0 ? dot : filter.value.length);
        }
    }

    const filter = $('quickpick-filter');
    filter.addEventListener('input', () => {
        quickpick.selected = 0;
        renderQuickPick();
    });
    filter.addEventListener('keydown', (event) => {
        const choices = quickpick.visible.filter((row) => !row.separator);
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            quickpick.selected = Math.min(choices.length - 1, quickpick.selected + 1);
            renderQuickPick();
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            quickpick.selected = Math.max(0, quickpick.selected - 1);
            renderQuickPick();
        } else if (event.key === 'Enter') {
            event.preventDefault();
            if (quickpick.input) closeQuickPick(null, filter.value);
            else if (choices[quickpick.selected]) closeQuickPick(choices[quickpick.selected].index);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            closeQuickPick(null);
        }
    });
    $('quickpick').addEventListener('pointerdown', (event) => {
        if (!event.target.closest('.picker')) closeQuickPick(null);
    });

    return { showQuickPick, showConfirm };
}
