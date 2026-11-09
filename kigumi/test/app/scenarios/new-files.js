// New Frame (the last row of the frames list) and New File (a folder's right-click menu): each asks
// for a name in the quick pick's text box, makes the file, and opens it.

const fs = require('fs');
const path = require('path');

module.exports = {
    name: 'new-files',
    async run({ check, inShell, waitFor, capture, runAppCommand, connection, REPO }) {
        const frameFile = path.join(REPO, 'kigumi_app_test_frame.py');
        const folder = path.join(REPO, 'kigumi-app-test-new');
        const inExplorer = (body) => inShell(`(() => {
            const doc = document.querySelector("#slot-left iframe")?.contentDocument;
            if (!doc) return null;
            const row = (key) => doc.querySelector('.ks-row[data-key="' + CSS.escape(key) + '"]');
            ${body}
        })()`);
        const answer = async (text) => {
            const shown = await waitFor(() => inShell(`!document.getElementById('quickpick').hidden
                && document.getElementById('quickpick-filter').value`), { timeoutMs: 15000 }).catch(() => null);
            await inShell(`(() => {
                const input = document.getElementById('quickpick-filter');
                input.value = ${JSON.stringify(text)};
                input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
            })()`);
            return shown;
        };
        try {
            await waitFor(async () => {
                const snapshot = await runAppCommand('kigumi.testGetSidebarSnapshot', { forceRefresh: false });
                return snapshot && snapshot.state.workspaceRoot && !snapshot.state.isScanning ? snapshot : null;
            });
            await waitFor(() => inExplorer(`return !!row('frames-new');`), { timeoutMs: 10000 });
            await inExplorer(`row('frames-new').click(); return true;`);
            const suggested = await answer('Kigumi App Test Frame');
            const made = await waitFor(() => fs.existsSync(frameFile) || null, { timeoutMs: 10000 }).catch(() => false);
            const listed = await waitFor(() => inExplorer(`return !!row(${JSON.stringify(`frame-file:workspace:${frameFile}`)}) || null;`),
                { timeoutMs: 60000 }).catch(() => false);
            const shown = await waitFor(async () => {
                const snapshot = await runAppCommand('kigumi.testGetSessionSnapshot', { filePath: frameFile });
                return snapshot && snapshot.exists ? snapshot : null;
            }, { timeoutMs: 60000 }).catch(() => null);
            const source = made ? fs.readFileSync(frameFile, 'utf8') : '';
            check('New Frame asks for a name, then makes, lists and opens the frame',
                suggested === 'my_frame' && source.includes('def kigumi_app_test_frame(') && listed === true && Boolean(shown),
                `${suggested}, listed ${listed}, view ${Boolean(shown)}`);
            await capture('new-frame');

            await inExplorer(`const target = row('files-root');
                const box = target.getBoundingClientRect();
                target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: box.left + 10, clientY: box.top + 5 }));
                return true;`);
            const chose = await waitFor(() => inExplorer(`const item = [...doc.querySelectorAll('.ks-menu-item')]
                .find((one) => one.textContent.includes('New File'));
                if (!item) return false;
                item.click();
                return true;`), { timeoutMs: 10000 }).catch(() => false);
            const fileSuggested = await answer('kigumi-app-test-new/plan.txt');
            const newFile = path.join(folder, 'plan.txt');
            const fileMade = await waitFor(() => fs.existsSync(newFile) || null, { timeoutMs: 10000 }).catch(() => false);
            const opened = await waitFor(() => [...connection().panels.values()].some((panel) => panel.filePath === newFile) || null,
                { timeoutMs: 10000 }).catch(() => false);
            check('right-click > New File makes the file it is given and opens it',
                chose && fileSuggested === 'untitled.py' && fileMade === true && opened === true,
                `${fileSuggested}, made ${fileMade}, opened ${opened}`);
        } finally {
            fs.rmSync(frameFile, { force: true });
            fs.rmSync(folder, { recursive: true, force: true });
        }
    },
};
