// The app's settings: auto refresh on by default, settings.json edited by hand applies at once, and
// the Language menu, at Default (the system's language).

const fs = require('fs');
const { Menu } = require('electron');

module.exports = {
    name: 'settings',
    async run({ check, waitFor, settings }) {
        check('auto refresh defaults to on in the app', settings.get('viewer.autoRefreshOnFileChange') === true);
        const edited = { ...JSON.parse(fs.readFileSync(settings.filePath, 'utf8')), 'viewer.autoRefreshOnFileChange': false };
        fs.writeFileSync(settings.filePath, JSON.stringify(edited, null, 2));
        const applied = await waitFor(() => settings.get('viewer.autoRefreshOnFileChange') === false, { timeoutMs: 5000 })
            .then(() => true, () => false);
        check('editing settings.json applies without a restart', applied);

        const items = (menu) => (menu ? menu.items.flatMap((item) => [item, ...items(item.submenu)]) : []);
        const language = items(Menu.getApplicationMenu()).find((item) => item.label === 'Language');
        const choices = language ? language.submenu.items.map((item) => `${item.label}${item.checked ? ' *' : ''}`) : [];
        const top = Menu.getApplicationMenu().items.map((item) => item.label);
        const helpMenu = Menu.getApplicationMenu().items.find((item) => item.label === 'Help');
        const helpItems = helpMenu ? helpMenu.submenu.items.filter((item) => item.type !== 'separator').map((item) => item.label) : [];
        const all = items(Menu.getApplicationMenu()).map((item) => item.label);
        check('the menus are Kigumi, File and Help; Help links the website, the docs, Discord and GitHub Discussions; '
            + 'About Kigumi is in the Kigumi menu, and there is no Toggle Developer Tools',
            JSON.stringify(top) === JSON.stringify(process.platform === 'darwin' ? ['Kigumi', 'File', 'Help'] : ['File', 'Kigumi', 'Help'])
                && JSON.stringify(helpItems) === JSON.stringify(['Kumiki Website', 'Documentation', 'Discord', 'GitHub Discussions'])
                && all.includes('About Kigumi') && !all.includes('Toggle Developer Tools'),
            JSON.stringify({ top, helpItems }));
        check('the Language menu offers Default (checked), English and 日本語', settings.get('app.language') === 'default'
            && choices.join(', ') === 'Default (system language) *, English, 日本語', choices.join(', '));
    },
};
