// File > Open Recent and the welcome page offer the project folders opened lately: the open one
// is remembered but not offered, nor is one that has gone.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { Menu } = require('electron');

module.exports = {
    name: 'recent-folders',
    async run({ check, settings, onShellCommand, waitFor }) {
        const open = settings.get('app.workspaceFolder');
        check('the open folder is the most recent', (settings.get('app.recentFolders') || [])[0] === open);

        const other = fs.mkdtempSync(path.join(os.tmpdir(), 'kigumi-recent-'));
        const before = settings.get('app.recentFolders');
        try {
            settings.set('app.recentFolders', [open, other, path.join(other, 'gone')]);
            const recentMenu = () => {
                const file = Menu.getApplicationMenu().items.find((item) => item.label === 'File');
                const recent = file && file.submenu.items.find((item) => item.label === 'Open Recent');
                return recent ? recent.submenu.items.map((item) => item.label) : null;
            };
            const labels = await waitFor(() => {
                const now = recentMenu();
                return now && now[0] && now[0].startsWith(path.basename(other)) ? now : null;
            }, { timeoutMs: 5000 }).catch(() => recentMenu());
            check('Open Recent lists the other folder, not the open one or one that has gone',
                labels && labels.length === 3 && labels[0].startsWith(path.basename(other)) && labels[2] === 'Clear Recently Opened',
                JSON.stringify(labels));

            await onShellCommand('clearRecentFolders');
            check('Clear Recently Opened empties the list',
                await waitFor(() => (recentMenu() || [])[0] === 'No Recent Folders', { timeoutMs: 5000 }).then(() => true, () => false));
        } finally {
            settings.set('app.recentFolders', before);
            fs.rmSync(other, { recursive: true, force: true });
        }
    },
};
