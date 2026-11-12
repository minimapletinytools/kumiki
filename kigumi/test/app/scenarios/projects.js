// With a project open, the welcome page offers Browse Patterns and Browse Examples, which open the
// explorer on those trees; File has New, Open, Open Recent and Close Project, and no Open Frame File.

const { Menu } = require('electron');

module.exports = {
    name: 'projects',
    async run({ check, inShell, waitFor, connection, capture }) {
        const welcomeButtons = await waitFor(() => inShell(`(() => {
            const welcome = document.querySelector('#welcome');
            if (!welcome || welcome.hidden) return null;
            return [...welcome.querySelectorAll('#welcome-actions button')].map((button) => button.textContent);
        })()`), { timeoutMs: 10000 }).catch(() => null);
        check('the welcome page offers Browse Patterns and Browse Examples',
            JSON.stringify(welcomeButtons) === JSON.stringify(['Browse Patterns', 'Browse Examples']), JSON.stringify(welcomeButtons));

        const rowExpanded = (key) => inShell(`(() => {
            const doc = document.querySelector('#slot-left iframe')?.contentDocument;
            const row = doc && doc.querySelector('.ks-row[data-key="' + CSS.escape(${JSON.stringify(key)}) + '"]');
            return row ? row.getAttribute('aria-expanded') : null;
        })()`);
        const click = (label) => inShell(`[...document.querySelectorAll('#welcome-actions button')]
            .find((b) => b.textContent === ${JSON.stringify(label)}).click()`);
        const expandedSoon = (key) => waitFor(async () => connection().layout.left && await rowExpanded(key) === 'true',
            { timeoutMs: 10000 }).then(() => true, () => false);

        // Collapsed first, so the check sees Browse Patterns open it.
        await inShell(`document.querySelector('#slot-left iframe').contentDocument
            .querySelector('.ks-row[data-key="patterns-root"] .ks-twistie').click()`);
        await waitFor(async () => await rowExpanded('patterns-root') === 'false', { timeoutMs: 5000 }).catch(() => null);
        connection().setSideShown('left', false);
        await click('Browse Patterns');
        check('Browse Patterns opens the explorer with Patterns expanded', await expandedSoon('patterns-root'));
        await capture('03h-browse-patterns');

        // This repo's own examples are its workspace frames, so it has no examples tree: Browse Examples says why.
        connection().setSideShown('left', false);
        const hasExamples = await rowExpanded('example-frames-root') !== null;
        await click('Browse Examples');
        const examples = hasExamples
            ? await expandedSoon('example-frames-root')
            : await waitFor(() => inShell(`(document.querySelector('#status-message')?.textContent || '').includes('No examples')`),
                { timeoutMs: 5000 }).then(() => true, () => false);
        check('Browse Examples opens the examples, or says there are none', examples, hasExamples ? 'expanded' : 'none here');

        const file = Menu.getApplicationMenu().items.find((item) => item.label === 'File').submenu.items.map((item) => item.label);
        check('File has New, Open, Open Recent and Close Project, and no Open Frame File',
            ['New Project…', 'Open Project…', 'Open Recent', 'Close Project'].every((label) => file.includes(label))
            && !file.includes('Open Frame File…'), JSON.stringify(file));

        const menus = Menu.getApplicationMenu().items.map((item) => item.label);
        const copy = Menu.getApplicationMenu().items.flatMap((item) => item.submenu.items).find((item) => item.role === 'copy');
        check('the menus are Kigumi and File, with copy kept (hidden) for the edit keys on macOS',
            menus.length === 2 && menus.includes('Kigumi') && menus.includes('File')
                && (process.platform !== 'darwin' || (Boolean(copy) && copy.visible === false)), JSON.stringify(menus));
    },
};
