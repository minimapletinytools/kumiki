// Keyboard shortcuts: the menus take their keys from them, Open Current File in Viewer opens the
// file in focus in a view, and the Keyboard Shortcuts tab changes a key, which the menus follow.

const { Menu } = require('electron');

module.exports = {
    name: 'keyboard-shortcuts',
    async run({ check, inShell, waitFor, capture, settings, runAppCommand, connection, FRAME }) {
        const items = (menu) => (menu ? menu.items.flatMap((item) => [item, ...items(item.submenu)]) : []);
        const menuItem = (label) => items(Menu.getApplicationMenu()).find((item) => item.label === label);
        const isMac = process.platform === 'darwin';

        const openCurrent = menuItem('Open Current File in Viewer');
        check('the File menu has Open Current File in Viewer, on cmd/ctrl+shift+o',
            Boolean(openCurrent) && openCurrent.accelerator === (isMac ? 'Shift+Cmd+O' : 'Ctrl+Shift+O'),
            openCurrent && openCurrent.accelerator);

        // The file in focus, in an editor, opens in a view.
        await runAppCommand('kigumi.viewPatternSource', { data: { sourceFile: FRAME } });
        await waitFor(() => (connection().activePanel || {}).type === 'editor', { timeoutMs: 10000 }).catch(() => null);
        openCurrent.click();
        const opened = await waitFor(async () => {
            const snapshot = await runAppCommand('kigumi.testGetSessionSnapshot', { filePath: FRAME });
            return snapshot && snapshot.exists ? snapshot : null;
        }, { timeoutMs: 60000 }).catch(() => null);
        // Built before going on, so the view isn't closed under a build still running.
        const built = opened ? await runAppCommand('kigumi.automationBuildReport', { filePath: FRAME }) : null;
        check('Open Current File in Viewer opens the editor\'s file in a view', Boolean(opened) && built && built.ok === true);

        // The Keyboard Shortcuts tab, from the Kigumi menu.
        menuItem('Keyboard Shortcuts…').click();
        const keysPanel = await waitFor(() => connection().findPanel((panel) => panel.type === 'keyboardShortcuts'), { timeoutMs: 5000 });
        const tab = `document.querySelector('iframe[name="${keysPanel.id}"]')?.contentDocument`;
        const rows = await waitFor(() => inShell(`${tab}?.querySelectorAll('.keys-table tr').length || 0`), { timeoutMs: 10000 }).catch(() => 0);
        check('Kigumi > Keyboard Shortcuts… opens a tab listing the commands and their keys', rows >= 10, `${rows} rows`);
        await capture('keyboard-shortcuts');

        // Change Open Current File in Viewer's key there: press Change, then the new keys.
        const pressedChange = await inShell(`(() => {
            const doc = ${tab};
            const row = [...doc.querySelectorAll('.keys-table tr')].find((one) => one.textContent.includes('Open Current File in Viewer'));
            const change = row && [...row.querySelectorAll('button')].find((one) => one.textContent === 'Change');
            if (!change) return 'no Change button: ' + (row ? row.textContent : 'no row');
            change.click();
            return true;
        })()`);
        const recordingFreesMenu = await waitFor(() => menuItem('Open Current File in Viewer').registerAccelerator === false || null,
            { timeoutMs: 5000 }).catch(() => false);
        await inShell(`(() => {
            const doc = ${tab};
            doc.defaultView.dispatchEvent(new doc.defaultView.KeyboardEvent('keydown',
                { key: 'e', code: 'KeyE', ctrlKey: true, altKey: true, bubbles: true }));
            return true;
        })()`);
        const saved = await waitFor(() => (settings.get('app.keybindings', {})['kigumi.openCurrentFileInViewer'] === 'ctrl+alt+e') || null,
            { timeoutMs: 5000 }).catch(() => false);
        const followed = await waitFor(() => {
            const item = menuItem('Open Current File in Viewer');
            return item.accelerator === 'Ctrl+Alt+E' && item.registerAccelerator !== false ? true : null;
        }, { timeoutMs: 5000 }).catch(() => false);
        check('a key pressed after Change is kept, and the menu follows it; while waiting, the menus let keys through',
            recordingFreesMenu === true && saved === true && followed === true,
            JSON.stringify({ pressedChange, recordingFreesMenu, saved, followed, accelerator: menuItem('Open Current File in Viewer').accelerator }));

        settings.set('app.keybindings', {});
        const reset = await waitFor(() => menuItem('Open Current File in Viewer').accelerator === (isMac ? 'Shift+Cmd+O' : 'Ctrl+Shift+O') || null,
            { timeoutMs: 5000 }).catch(() => false);
        check('reset, the key is the default again', reset === true);
        const keysTab = connection().findPanel((panel) => panel.type === 'keyboardShortcuts');
        if (keysTab) keysTab.dispose();
    },
};
