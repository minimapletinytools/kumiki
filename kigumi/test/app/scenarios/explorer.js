// The explorer: the workspace scanned, and All Files opened folder by folder down to a frame,
// opened in a viewer from its right-click menu.

const path = require('path');

module.exports = {
    name: 'explorer',
    async run({ check, inShell, waitFor, capture, runAppCommand, connection, REPO, FRAME }) {
        const sidebar = await waitFor(async () => {
            const snapshot = await runAppCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: false });
            return snapshot && snapshot.state.workspaceRoot && !snapshot.state.isScanning ? snapshot : null;
        });
        const roots = sidebar.roots.map((root) => root.label);
        check('explorer scans the workspace', sidebar.state.frameCount > 0 && sidebar.state.workspacePatternbookCount > 0,
            `${sidebar.state.frameCount} frames, ${sidebar.state.workspacePatternbookCount} patternbooks`);
        check('explorer shows Frames and Patterns', roots.some((l) => l.startsWith('Frames')) && roots.some((l) => l.startsWith('Patterns')));
        const rows = await waitFor(() => inShell(
            'document.querySelector("#slot-left iframe")?.contentDocument?.querySelectorAll(".ks-row").length || 0'));
        check('the explorer panel renders in the left slot', rows > 0, `${rows} rows`);
        await capture('01-shell');

        const inExplorer = (body) => inShell(`(() => {
            const doc = document.querySelector("#slot-left iframe")?.contentDocument;
            if (!doc) return null;
            const row = (key) => doc.querySelector('.ks-row[data-key="' + CSS.escape(key) + '"]');
            ${body}
        })()`);
        const firstRow = await inExplorer(`const first = doc.querySelector('.ks-tree .ks-row');
            return first && { key: first.dataset.key, expanded: first.getAttribute('aria-expanded') };`);
        check('All files is the explorer\'s first row, collapsed', firstRow && firstRow.key === 'files-root' && firstRow.expanded === 'false',
            JSON.stringify(firstRow));
        const openFolder = async (key, child) => {
            await inExplorer(`row(${JSON.stringify(key)})?.querySelector('.ks-twistie')?.click(); return true;`);
            return waitFor(() => inExplorer(`return !!row(${JSON.stringify(child)});`), { timeoutMs: 10000 }).catch(() => false);
        };
        try {
            const rootListed = await openFolder('files-root', `file-folder:${path.join(REPO, 'patterns')}`);
            const venvHidden = await inExplorer(`return !row(${JSON.stringify(`file-folder:${path.join(REPO, '.venv')}`)});`);
            check('All files lists the workspace when opened, leaving out .venv', rootListed && venvHidden);
            await openFolder(`file-folder:${path.join(REPO, 'patterns')}`, `file-folder:${path.join(REPO, 'patterns', 'structures')}`);
            const frameListed = await openFolder(`file-folder:${path.join(REPO, 'patterns', 'structures')}`, `file:${FRAME}`);
            const frameIcon = await inExplorer(`return !!row(${JSON.stringify(`file:${FRAME}`)})?.querySelector('.codicon-fish2-very-sad');`);
            check('a frame in All files has the frame icon', frameListed && frameIcon);
            await inExplorer(`const target = row(${JSON.stringify(`file:${FRAME}`)});
                const box = target.getBoundingClientRect();
                target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: box.left + 10, clientY: box.top + 5 }));
                return true;`);
            const choseOpen = await waitFor(() => inExplorer(`const item = [...doc.querySelectorAll('.ks-menu-item')]
                .find((one) => one.textContent.includes('Open in Viewer'));
                if (!item) return false;
                item.click();
                return true;`), { timeoutMs: 10000 }).catch(() => false);
            const openedFromMenu = await waitFor(async () => {
                const snapshot = await runAppCommand('kigumi.testGetSessionSnapshot', { filePath: FRAME });
                return snapshot && snapshot.exists ? snapshot : null;
            }, { timeoutMs: 60000 }).catch(() => null);
            check('right-click > Open in Viewer on a frame in All files opens it', choseOpen && openedFromMenu && connection().tabs.tabs.length === 1);
        } finally {
            await inExplorer(`row('files-root')?.querySelector('.ks-twistie')?.click(); return true;`);
        }
    },
};
