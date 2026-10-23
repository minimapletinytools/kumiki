// The header row every panel over the view wears: its name and the arrow that collapses it,
// on one line. On the left of the view the arrow leads (▸ selection); on the right it follows
// the name and points back into the view (camera ◂). Open, it points down either way.
//
// Anything else put in the header (a button) should stop its click, or the click collapses
// the panel too.
const ARROWS = {
    left: { collapsed: '▸', open: '▾' },
    right: { collapsed: '◂', open: '▾' },
};

function overlayHeader(label, { collapsed, onToggle, side = 'left', doc = globalThis.document } = {}) {
    const header = doc.createElement('div');
    header.className = `ov-header ov-header-${side}`;
    // Properties rather than attributes: the same thing in a browser, and all a test's fake
    // element has.
    header.role = 'button';
    header.ariaExpanded = collapsed ? 'false' : 'true';

    const arrow = doc.createElement('span');
    arrow.className = 'ov-chev';
    arrow.textContent = ARROWS[side][collapsed ? 'collapsed' : 'open'];
    const title = doc.createElement('span');
    title.className = 'ov-title';
    title.textContent = label;
    for (const part of side === 'right' ? [title, arrow] : [arrow, title]) {
        header.appendChild(part);
    }
    if (onToggle) {
        header.addEventListener('click', () => onToggle());
    }
    return header;
}

const exported = { overlayHeader, ARROWS };

export { overlayHeader, ARROWS };
