// The shortcuts: Go to File and Open in Viewer on Cmd/Ctrl+P and O; Go to File finds a file of the
// workspace by name and opens its source.

const path = require('path');

module.exports = {
    name: 'go-to-file',
    async run({ check, inShell, waitFor, runAppCommand, connection, FRAME }) {
        const { Menu } = require('electron');
        const menuItem = (label) => Menu.getApplicationMenu().items.flatMap((item) => item.submenu ? item.submenu.items : [])
            .find((item) => item.label === label);
        const goToFile = menuItem('Go to File…');
        const openInViewer = menuItem('Open in Viewer…');
        check('Go to File and Open in Viewer are on CmdOrCtrl+P and CmdOrCtrl+O',
            /P$/.test(goToFile && goToFile.accelerator || '') && /O$/.test(openInViewer && openInViewer.accelerator || ''),
            `${goToFile && goToFile.accelerator}, ${openInViewer && openInViewer.accelerator}`);
        const goingToFile = runAppCommand('kigumi.quickOpenFile');
        await waitFor(() => inShell('!document.getElementById("quickpick").hidden && document.querySelectorAll("#quickpick .item").length'), { timeoutMs: 30000 });
        await inShell(`(() => {
            const filter = document.getElementById('quickpick-filter');
            filter.value = ${JSON.stringify(path.basename(FRAME))};
            filter.dispatchEvent(new Event('input'));
            filter.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
        })()`);
        await goingToFile;
        const fileTab = await waitFor(() => {
            const active = connection().activePanel;
            return active && active.type === 'editor' ? active : null;
        }, { timeoutMs: 10000 }).catch(() => null);
        check('Go to File opens the file picked', fileTab && fileTab.filePath === FRAME, fileTab && fileTab.filePath);
    },
};
