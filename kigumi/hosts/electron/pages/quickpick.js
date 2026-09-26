// A VS Code-style quick pick: type to filter, arrows to move, Enter to choose,
// Escape or a click outside to cancel.

(function () {
    'use strict';

    const api = window.kigumiShell;
    const filter = document.getElementById('filter');
    const list = document.getElementById('list');
    let items = [];
    let visible = [];
    let selected = 0;

    function choose(index) {
        api.send('quickpick:result', index);
    }

    function render() {
        const needle = filter.value.trim().toLowerCase();
        visible = [];
        let pendingSeparator = null;
        items.forEach((item, index) => {
            if (item.separator) {
                pendingSeparator = item;
                return;
            }
            const text = `${item.label} ${item.description || ''} ${item.detail || ''}`.toLowerCase();
            if (needle && !text.includes(needle)) return;
            if (pendingSeparator) {
                visible.push({ separator: pendingSeparator });
                pendingSeparator = null;
            }
            visible.push({ item, index });
        });
        const choices = visible.filter((row) => !row.separator);
        selected = Math.max(0, Math.min(selected, choices.length - 1));

        let choiceNumber = 0;
        list.replaceChildren(...visible.map((row) => {
            if (row.separator) {
                const element = document.createElement('div');
                element.className = 'separator';
                element.textContent = row.separator.label;
                return element;
            }
            const current = choiceNumber;
            choiceNumber += 1;
            const element = document.createElement('div');
            element.className = `item${current === selected ? ' is-selected' : ''}`;
            element.setAttribute('role', 'option');
            element.setAttribute('aria-selected', current === selected ? 'true' : 'false');
            const label = document.createElement('span');
            label.className = 'item-label';
            label.textContent = row.item.label;
            const description = document.createElement('span');
            description.className = 'item-description';
            description.textContent = row.item.description || '';
            element.append(label, description);
            if (row.item.detail) {
                const detail = document.createElement('span');
                detail.className = 'item-detail';
                detail.textContent = row.item.detail;
                element.append(detail);
            }
            element.addEventListener('click', () => choose(row.index));
            return element;
        }));
        if (choices.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'empty';
            empty.textContent = 'No matching items';
            list.append(empty);
        }
        const selectedElement = list.querySelector('.is-selected');
        if (selectedElement) selectedElement.scrollIntoView({ block: 'nearest' });
    }

    filter.addEventListener('input', () => {
        selected = 0;
        render();
    });

    filter.addEventListener('keydown', (event) => {
        const choices = visible.filter((row) => !row.separator);
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            selected = Math.min(choices.length - 1, selected + 1);
            render();
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            selected = Math.max(0, selected - 1);
            render();
        } else if (event.key === 'Enter') {
            event.preventDefault();
            if (choices[selected]) choose(choices[selected].index);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            choose(null);
        }
    });

    document.body.addEventListener('pointerdown', (event) => {
        if (!event.target.closest('.picker')) choose(null);
    });

    api.on('quickpick:show', (payload) => {
        items = payload.items || [];
        filter.placeholder = payload.placeholder || '';
        filter.value = '';
        selected = 0;
        render();
        filter.focus();
    });
})();
